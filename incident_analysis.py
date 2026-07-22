from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


class CSVInputError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code

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

EXPECTED_CSV_COLUMNS = STRICT_REQUIRED_FIELDS + ("satisfaction_score",)


def to_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


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


def count_by(rows: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        raw = row.get(key, "")
        value = to_text(raw)
        counter[value if value else "unknown"] += 1
    return counter


def count_status_summary(rows: list[dict[str, Any]]) -> Counter[str]:
    summary: Counter[str] = Counter()
    for row in rows:
        status = to_text(row.get("status"))
        key = STATUS_GROUPS.get(status, "unknown")
        summary[key] += 1
    return summary


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


def average_closed_satisfaction(rows: list[dict[str, object]]) -> float | None:
    satisfaction_values = [
        value
        for value in (
            to_int(to_text(row.get("satisfaction_score")))
            for row in rows
            if to_text(row.get("status")) == "CLOSED"
        )
        if value is not None
    ]
    if not satisfaction_values:
        return None
    return round(sum(satisfaction_values) / len(satisfaction_values), 2)


def summarize_rows(rows: list[dict[str, object]]) -> dict[str, Any]:
    valid_rows, invalid_by_type, invalid_records = split_valid_invalid(rows)
    return {
        "total_processed_incidents": len(rows),
        "total_valid_incidents": len(valid_rows),
        "total_invalid_incidents": invalid_records,
        "invalid_records_by_problem_type": dict(invalid_by_type),
        "incidents_by_category": dict(count_by(valid_rows, "category")),
        "incidents_by_status": dict(count_status_summary(valid_rows)),
        "incidents_by_country": dict(count_by(valid_rows, "country")),
        "average_satisfaction_closed_cases_with_score": average_closed_satisfaction(valid_rows),
    }


def summary_to_csv_text(summary: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "metric", "value"])

    writer.writerow(["totals", "total_processed_incidents", summary["total_processed_incidents"]])
    writer.writerow(["totals", "total_valid_incidents", summary["total_valid_incidents"]])
    writer.writerow(["totals", "total_invalid_incidents", summary["total_invalid_incidents"]])

    avg_closed_satisfaction = summary["average_satisfaction_closed_cases_with_score"]
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

    for label, amount in sorted(
        summary["incidents_by_category"].items(), key=lambda item: item[1], reverse=True
    ):
        writer.writerow(["incidents_by_category", label, amount])

    for label, amount in sorted(
        summary["incidents_by_status"].items(), key=lambda item: item[1], reverse=True
    ):
        writer.writerow(["incidents_by_status", label, amount])

    for label, amount in sorted(
        summary["incidents_by_country"].items(), key=lambda item: item[1], reverse=True
    ):
        writer.writerow(["incidents_by_country", label, amount])

    for label, amount in sorted(
        summary["invalid_records_by_problem_type"].items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        writer.writerow(["invalid_records_by_problem_type", label, amount])

    return buffer.getvalue()


def read_csv_text(text: str) -> list[dict[str, str]]:
    if not text.strip():
        raise CSVInputError("The uploaded file is empty.", status_code=400)

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CSVInputError(
            "CSV format is invalid: the file does not contain headers.",
            status_code=422,
        )

    fieldnames = [field.strip() for field in reader.fieldnames if field is not None]
    missing_columns = [column for column in EXPECTED_CSV_COLUMNS if column not in fieldnames]
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise CSVInputError(
            f"CSV format is invalid: missing required columns: {missing_text}.",
            status_code=422,
        )

    rows = list(reader)
    if not rows:
        raise CSVInputError(
            "CSV format is invalid: the file does not contain data rows.",
            status_code=422,
        )

    for line_number, row in enumerate(rows, start=2):
        if None in row:
            raise CSVInputError(
                f"CSV format is invalid near line {line_number}: too many fields.",
                status_code=422,
            )

        malformed_columns = [column for column in EXPECTED_CSV_COLUMNS if row.get(column) is None]
        if malformed_columns:
            malformed_text = ", ".join(malformed_columns)
            raise CSVInputError(
                f"CSV format is invalid near line {line_number}: missing values due to malformed row in columns: {malformed_text}.",
                status_code=422,
            )

    return rows


def read_csv_file(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)
