#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    import pandas as pd
except ImportError:
    pd = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze incidents from a CSV file.",
        usage="python analyze.py incidents-COMPANY.csv",
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="Path to the incidents CSV file.",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "native", "pandas"),
        default="auto",
        help="CSV reading engine. 'auto' uses pandas if available, otherwise native csv.",
    )
    return parser


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def count_by(rows: Iterable[dict[str, str]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        raw = row.get(key, "")
        value = (raw or "").strip()
        counter[value if value else "unknown"] += 1
    return counter


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def print_metric(label: str, value: str | int) -> None:
    print(f"{label:<56} {value}")


def print_counter(title: str, counter: Counter[str]) -> None:
    print_section(title)
    if not counter:
        print("(sin datos)")
        return

    for label, amount in counter.most_common():
        print_metric(f"- {label}", amount)


def export_results_csv(
    output_path: Path,
    *,
    total_processed: int,
    total_valid: int,
    total_invalid: int,
    category_counts: Counter[str],
    status_counts: Counter[str],
    country_counts: Counter[str],
    invalid_by_type: Counter[str],
    avg_closed_satisfaction: float | None,
) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "metric", "value"])

        writer.writerow(["totals", "total_processed_incidents", total_processed])
        writer.writerow(["totals", "total_valid_incidents", total_valid])
        writer.writerow(["totals", "total_invalid_incidents", total_invalid])
        writer.writerow(
            [
                "satisfaction",
                "average_satisfaction_closed_cases_with_score",
                (
                    f"{avg_closed_satisfaction:.2f}"
                    if avg_closed_satisfaction is not None
                    else "not_available"
                ),
            ]
        )

        for label, amount in category_counts.most_common():
            writer.writerow(["incidents_by_category", label, amount])

        for label, amount in status_counts.most_common():
            writer.writerow(["incidents_by_status", label, amount])

        for label, amount in country_counts.most_common():
            writer.writerow(["incidents_by_country", label, amount])

        for label, amount in invalid_by_type.most_common():
            writer.writerow(["invalid_records_by_problem_type", label, amount])


def load_rows_native(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_rows_pandas(csv_path: Path) -> list[dict[str, str]]:
    if pd is None:
        raise RuntimeError("pandas is not installed in this environment")
    dataframe = pd.read_csv(csv_path)
    return dataframe.fillna("").to_dict(orient="records")


def load_rows(csv_path: Path, engine: str) -> tuple[list[dict[str, str]], str]:
    if engine == "native":
        return load_rows_native(csv_path), "native"

    if engine == "pandas":
        return load_rows_pandas(csv_path), "pandas"

    if pd is not None:
        return load_rows_pandas(csv_path), "pandas"
    return load_rows_native(csv_path), "native"


ALLOWED_STATUS = {"OPEN", "CLOSED", "DISCARDED"}
ALLOWED_COUNTRY = {"ES", "US"}
ALLOWED_CUSTOMER_TYPE = {"B2B", "B2C"}

STATUS_GROUPS = {
    "OPEN": "abierto",
    "CLOSED": "cerrado",
    "DISCARDED": "descartado",
}

INCIDENT_ID_PATTERN = re.compile(r"^TRF-\d{6}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

STRICT_REQUIRED_FIELDS = (
    "incident_id",
    "date",
    "country",
    "customer_type",
    "tracking_number",
    "carrier",
    "category",
    "description",
    "status",
    "customer_email",
)


def is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def to_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("+"):
        text = text[1:]
    if not text.isdigit():
        return None
    return int(text)


def validate_row(row: dict[str, object]) -> list[str]:
    errors: list[str] = []

    for field in STRICT_REQUIRED_FIELDS:
        if not to_text(row.get(field)):
            errors.append(f"missing_field:{field}")

    status = to_text(row.get("status"))
    if status and status not in ALLOWED_STATUS:
        errors.append("out_of_range:status")

    incident_id = to_text(row.get("incident_id"))
    if incident_id and not INCIDENT_ID_PATTERN.fullmatch(incident_id):
        errors.append("invalid_format:incident_id")

    date_value = to_text(row.get("date"))
    if date_value and not is_iso_date(date_value):
        errors.append("invalid_format:date")

    country = to_text(row.get("country"))
    if country and country not in ALLOWED_COUNTRY:
        errors.append("out_of_range:country")

    customer_type = to_text(row.get("customer_type"))
    if customer_type and customer_type not in ALLOWED_CUSTOMER_TYPE:
        errors.append("out_of_range:customer_type")

    tracking_number = to_text(row.get("tracking_number"))
    if tracking_number and len(tracking_number) < 8:
        errors.append("invalid_format:tracking_number")

    description = to_text(row.get("description"))
    if description and len(description) < 5:
        errors.append("invalid_format:description")

    email = to_text(row.get("customer_email"))
    if email and not EMAIL_PATTERN.fullmatch(email):
        errors.append("invalid_format:customer_email")

    score_raw = to_text(row.get("satisfaction_score"))
    if status == "CLOSED" and not score_raw:
        errors.append("missing_field:satisfaction_score_for_closed")

    if score_raw:
        score = to_int(score_raw)
        if score is None:
            errors.append("invalid_format:satisfaction_score")
        elif score < 1 or score > 5:
            errors.append("out_of_range:satisfaction_score")

    return errors


def split_valid_invalid(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], Counter[str], int]:
    valid_rows: list[dict[str, object]] = []
    invalid_by_type: Counter[str] = Counter()
    invalid_records = 0

    for row in rows:
        errors = validate_row(row)
        if errors:
            invalid_records += 1
            invalid_by_type.update(errors)
        else:
            valid_rows.append(row)

    return valid_rows, invalid_by_type, invalid_records


def count_status_summary(rows: list[dict[str, object]]) -> Counter[str]:
    summary: Counter[str] = Counter()
    for row in rows:
        status = to_text(row.get("status"))
        key = STATUS_GROUPS.get(status)
        if key:
            summary[key] += 1
        else:
            summary["unknown"] += 1
    return summary


def analyze(csv_path: Path, engine: str) -> int:
    if not csv_path.exists() or not csv_path.is_file():
        print(f"Error: file not found: {csv_path}")
        return 1

    if csv_path.suffix.lower() != ".csv":
        print(f"Error: expected a .csv file, received: {csv_path.name}")
        return 1

    try:
        rows, selected_engine = load_rows(csv_path, engine)
    except Exception as exc:
        print(f"Error: unable to read CSV: {exc}")
        return 1

    if not rows:
        print("No incidents found in the input file.")
        return 0

    valid_rows, invalid_by_type, invalid_records = split_valid_invalid(rows)

    category_counts = count_by(valid_rows, "category")
    status_counts = count_status_summary(valid_rows)
    country_counts = count_by(valid_rows, "country")

    satisfaction_values = [
        value
        for value in (
            to_int(row.get("satisfaction_score"))
            for row in valid_rows
            if to_text(row.get("status")) == "CLOSED"
        )
        if value is not None
    ]

    print("=" * 72)
    print("INCIDENTS ANALYSIS SUMMARY")
    print("=" * 72)

    print_section("Execution")
    print_metric("File", csv_path)
    print_metric("Reader engine", selected_engine)

    print_section("Processing totals")
    print_metric("Total processed incidents", len(rows))
    print_metric("Total valid incidents", len(valid_rows))
    print_metric("Total invalid incidents", invalid_records)

    if invalid_by_type:
        print_counter("Invalid records by problem type", invalid_by_type)

    if valid_rows:
        print_counter("Incidents by category", category_counts)
        print_counter("Incidents by status (abierto/cerrado/descartado)", status_counts)
        print_counter("Incidents by country", country_counts)
    else:
        print_section("Incidents by category/status/country")
        print("No valid incidents available for analysis.")

    if satisfaction_values:
        avg_satisfaction = sum(satisfaction_values) / len(satisfaction_values)
        print_section("Closed cases satisfaction")
        print_metric(
            "Average satisfaction score for closed cases with recorded score",
            f"{avg_satisfaction:.2f}",
        )
    else:
        avg_satisfaction = None
        print_section("Closed cases satisfaction")
        print_metric(
            "Average satisfaction score for closed cases with recorded score",
            "not available",
        )

    answer = input("\nDesea exportar los resultados a CSV? [s/n]: ").strip().lower()
    if answer == "s":
        output_path = Path("results.csv")
        export_results_csv(
            output_path,
            total_processed=len(rows),
            total_valid=len(valid_rows),
            total_invalid=invalid_records,
            category_counts=category_counts,
            status_counts=status_counts,
            country_counts=country_counts,
            invalid_by_type=invalid_by_type,
            avg_closed_satisfaction=avg_satisfaction,
        )
        print(f"Resultados exportados en: {output_path.resolve()}")
    else:
        print("Exportacion omitida.")

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return analyze(args.csv_path, args.engine)


if __name__ == "__main__":
    raise SystemExit(main())