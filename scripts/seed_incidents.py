from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from tinydb import Query, TinyDB

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SERVICE_DIR = ROOT_DIR / "services" / "incidents-api"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from incident_analysis import read_csv_file  # noqa: E402  (reuses the Hito 07 CSV validation logic)
from models import IncidentCreate, IncidentResponse  # noqa: E402

DEFAULT_CSV_PATH = ROOT_DIR / "data" / "raw" / "incidents_history.csv"
DEFAULT_DB_PATH = SERVICE_DIR / "suppliers.json"

# Maps the legacy Hito 07 CSV statuses onto the Hito 10 Incident lifecycle.
# "in_progress" has no historical equivalent, so it never appears in seeded rows.
LEGACY_STATUS_MAP = {
    "OPEN": "open",
    "CLOSED": "resolved",
    "DISCARDED": "discarded",
}


def build_incident_document(row: dict[str, str]) -> dict[str, object] | None:
    incident_id = row.get("incident_id", "").strip()
    legacy_status = row.get("status", "").strip()
    new_status = LEGACY_STATUS_MAP.get(legacy_status)

    if new_status is None:
        print(f"Skipped {incident_id or '(sin id)'}: unmapped legacy status '{legacy_status}'.")
        return None

    category = row.get("category", "").strip()
    payload = {
        "title": f"{category or 'incidencia'} ({incident_id or 'sin-id'})",
        "description": row.get("description", "").strip(),
        "category": category,
        "origin": "customer",
        "branch": "central",
    }

    try:
        validated_input = IncidentCreate(**payload)
    except ValueError as exc:
        print(f"Skipped {incident_id or '(sin id)'}: {exc}")
        return None

    incident = IncidentResponse(**validated_input.model_dump(), status=new_status)
    document = incident.model_dump(mode="json")

    date_value = row.get("date", "").strip()
    if date_value:
        try:
            parsed_date = datetime.strptime(date_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            document["created_at"] = parsed_date.isoformat()
            document["updated_at"] = parsed_date.isoformat()
        except ValueError:
            print(f"Skipped {incident_id or '(sin id)'}: invalid date '{date_value}'.")
            return None

    document["source_incident_id"] = incident_id or None
    return document


def seed_incidents(csv_path: Path, db_path: Path) -> tuple[int, int]:
    rows = read_csv_file(csv_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    inserted_count = 0
    skipped_count = 0

    with TinyDB(db_path) as db:
        incidents_table = db.table("incidents")
        incident_query = Query()

        for row in rows:
            document = build_incident_document(row)
            if document is None:
                skipped_count += 1
                continue

            source_incident_id = document["source_incident_id"]
            if source_incident_id and incidents_table.contains(
                incident_query.source_incident_id == source_incident_id
            ):
                continue

            incidents_table.insert(document)
            inserted_count += 1

    return inserted_count, skipped_count


def main() -> None:
    raw_csv_path = os.environ.get("INCIDENTS_CSV_PATH")
    csv_path = Path(raw_csv_path) if raw_csv_path else DEFAULT_CSV_PATH

    raw_db_path = os.environ.get("TINYDB_PATH")
    db_path = Path(raw_db_path) if raw_db_path else DEFAULT_DB_PATH

    if not csv_path.exists():
        print(
            f"CSV file not found at {csv_path}. Set INCIDENTS_CSV_PATH to point at the historical CSV.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        inserted_count, skipped_count = seed_incidents(csv_path, db_path)
    except OSError as exc:
        print(f"Could not read the CSV file or write the database: {exc}", file=sys.stderr)
        sys.exit(1)
    except csv.Error as exc:
        print(f"The CSV file at {csv_path} is malformed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Seeded {inserted_count} incidents into {db_path} ({skipped_count} invalid rows skipped).")


if __name__ == "__main__":
    main()
