#!/usr/bin/env python3
"""
prep_data.py — Thin data preparation helper for Customer Master AI.

Reads local CSV files and converts them to JSON records suitable for
API upload or review. Contains ZERO business logic — file I/O only.

Usage:
    python prep_data.py customers.csv              # preview as JSON
    python prep_data.py customers.csv output.json   # save to file
"""

import csv
import json
import sys
import os


def csv_to_records(filepath: str) -> list[dict]:
    """Read a CSV file and return a list of dict records."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    if len(sys.argv) < 2:
        print("Usage: python prep_data.py <input.csv> [output.json]")
        print()
        print("Converts a CSV file to JSON records for review or upload.")
        sys.exit(1)

    input_path = sys.argv[1]
    records = csv_to_records(input_path)

    output = json.dumps(records, indent=2, ensure_ascii=False)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {len(records)} records to {output_path}")
    else:
        print(output)
        print(f"\n--- {len(records)} records ---")


if __name__ == "__main__":
    main()
