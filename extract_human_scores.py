"""Extract human evaluation scores into standalone files.

Reads ``dataset/Q+AR/result/Machine_vs_Human_Summary.json`` and writes:
- ``dataset/Q+AR/result/human_evaluation_scores.json``
- ``dataset/Q+AR/result/human_evaluation_scores.csv``

The JSON preserves the original nested structure plus identifiers.  The CSV
flattens the CCE scores into spreadsheet-friendly columns.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


DATA_PATH = Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
OUT_DIR = DATA_PATH.parent
JSON_OUT = OUT_DIR / "human_evaluation_scores.json"
CSV_OUT = OUT_DIR / "human_evaluation_scores.csv"


def flatten_score_group(group: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Flatten one CCE score group into CSV columns."""
    flat: dict[str, Any] = {}
    for key, value in group.items():
        if key == "total_score":
            flat[f"{prefix}_total"] = value
        elif isinstance(value, dict):
            flat[f"{prefix}_{key}"] = value.get("score")
            comment = value.get("comment")
            if comment:
                flat[f"{prefix}_{key}_comment"] = comment
        else:
            flat[f"{prefix}_{key}"] = value
    return flat


def extract_human_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract model/question id plus human_evaluation from each record."""
    out: list[dict[str, Any]] = []
    for record in records:
        he = record.get("human_evaluation") or {}
        item = {
            "model_name": record.get("model_name"),
            "question_id": record.get("question_id"),
            "grader_name": he.get("grader_name"),
            "grading_time": he.get("grading_time"),
            "overall_total_score": he.get("overall_total_score"),
            "overall_comment": he.get("overall_comment"),
            "completeness": he.get("completeness", {}),
            "correctness": he.get("correctness", {}),
            "effectiveness": he.get("effectiveness", {}),
        }
        out.append(item)
    return out


def to_csv_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert nested human-evaluation records into flat CSV rows."""
    rows: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {
            "model_name": record["model_name"],
            "question_id": record["question_id"],
            "grader_name": record["grader_name"],
            "grading_time": record["grading_time"],
            "overall_total_score": record["overall_total_score"],
            "overall_comment": record["overall_comment"],
        }
        row.update(flatten_score_group(record["completeness"], "completeness"))
        row.update(flatten_score_group(record["correctness"], "correctness"))
        row.update(flatten_score_group(record["effectiveness"], "effectiveness"))
        rows.append(row)
    return rows


def main() -> None:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw_records = json.load(f)

    human_records = extract_human_records(raw_records)

    # Write JSON
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(human_records, f, ensure_ascii=False, indent=2)

    # Write CSV
    rows = to_csv_rows(human_records)
    if rows:
        fieldnames = list(rows[0].keys())
        with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"Extracted {len(human_records)} human-evaluation records.")
    print(f"JSON: {JSON_OUT.resolve()}")
    print(f"CSV:  {CSV_OUT.resolve()}")


if __name__ == "__main__":
    main()
