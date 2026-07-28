#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None

from incident_analysis import read_csv_file, summarize_rows, summary_to_csv_text


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


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def print_metric(label: str, value: str | int) -> None:
    print(f"{label:<56} {value}")


def print_counter(title: str, counter: dict[str, int]) -> None:
    print_section(title)
    if not counter:
        print("(sin datos)")
        return

    for label, amount in sorted(counter.items(), key=lambda item: item[1], reverse=True):
        print_metric(f"- {label}", amount)


def export_results_csv(
    output_path: Path,
    summary: dict[str, Any],
) -> None:
    output_path.write_text(summary_to_csv_text(summary), encoding="utf-8")


def load_rows_native(csv_path: Path) -> list[dict[str, str]]:
    return read_csv_file(csv_path)


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

def analyze(csv_path: Path, engine: str) -> int:
    if not csv_path.exists() or not csv_path.is_file():
        print(f"Error: file not found: {csv_path}", file=sys.stderr)
        return 1

    if csv_path.suffix.lower() != ".csv":
        print(f"Error: expected a .csv file, received: {csv_path.name}", file=sys.stderr)
        return 1

    try:
        rows, selected_engine = load_rows(csv_path, engine)
    except Exception as exc:
        print(f"Error: unable to read CSV: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("No incidents found in the input file.")
        return 0

    summary: dict[str, Any] = summarize_rows(rows)
    category_counts = summary["incidents_by_category"]
    status_counts = summary["incidents_by_status"]
    country_counts = summary["incidents_by_country"]
    invalid_by_type = summary["invalid_records_by_problem_type"]
    avg_satisfaction = summary["average_satisfaction_closed_cases_with_score"]

    print("=" * 72)
    print("INCIDENTS ANALYSIS SUMMARY")
    print("=" * 72)

    print_section("Execution")
    print_metric("File", csv_path)
    print_metric("Reader engine", selected_engine)

    print_section("Processing totals")
    print_metric("Total processed incidents", summary["total_processed_incidents"])
    print_metric("Total valid incidents", summary["total_valid_incidents"])
    print_metric("Total invalid incidents", summary["total_invalid_incidents"])

    if invalid_by_type:
        print_counter("Invalid records by problem type", invalid_by_type)

    if summary["total_valid_incidents"]:
        print_counter("Incidents by category", category_counts)
        print_counter("Incidents by status (abierto/cerrado/descartado)", status_counts)
        print_counter("Incidents by country", country_counts)
    else:
        print_section("Incidents by category/status/country")
        print("No valid incidents available for analysis.")

    if avg_satisfaction is not None:
        print_section("Closed cases satisfaction")
        print_metric(
            "Average satisfaction score for closed cases with recorded score",
            f"{avg_satisfaction:.2f}",
        )
    else:
        print_section("Closed cases satisfaction")
        print_metric(
            "Average satisfaction score for closed cases with recorded score",
            "not available",
        )

    answer = input("\nDesea exportar los resultados a CSV? [s/n]: ").strip().lower()
    if answer == "s":
        output_path = Path("results.csv")
        try:
            export_results_csv(output_path, summary)
        except OSError as exc:
            print(f"Error: no se pudo escribir el fichero de resultados: {exc}", file=sys.stderr)
            return 1
        print(f"Resultados exportados en: {output_path.resolve()}")
    else:
        print("Exportacion omitida.")

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return analyze(args.csv_path, args.engine)


if __name__ == "__main__":
    raise SystemExit(main())