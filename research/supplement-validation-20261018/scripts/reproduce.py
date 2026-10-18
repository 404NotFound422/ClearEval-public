#!/usr/bin/env python3
"""Reproduce the pure-format artifact and run its engineering tests offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import build_format_controls as controls
from extract_inputs import extract, write_records

ROOT = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(output: Path) -> dict:
    pairs = json.loads((output / "format_control_pairs.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "validation_summary.json").read_text(encoding="utf-8"))
    rows = []
    for pair in pairs:
        diff_path = output / pair["diff_path"]
        diff = json.loads(diff_path.read_text(encoding="utf-8"))
        rows.append({
            "candidate_id": pair["source_reference"]["candidate_id"],
            "pair_id": pair["pair_id"],
            "question_id": pair["source_reference"]["question_id"],
            "answer_id": pair["source_reference"]["answer_id"],
            "original_utf8_sha256": diff["original_utf8_sha256"],
            "variant_utf8_sha256": diff["variant_utf8_sha256"],
            "diff_json_sha256": digest(diff_path),
            **pair["validation"],
        })
    return {
        "status": summary["candidate_status"],
        "passing_pair_count": len(pairs),
        "original_line_count": summary["original_line_count"],
        "inserted_lf_count": summary["inserted_lf_count"],
        "variant_line_count": summary["variant_line_count"],
        "excluded_failure_count": summary["excluded_failure_count"],
        "scientific_scoring_runs": summary["new_scientific_scoring_runs"],
        "independent_holdout": False,
        "expert_gold": False,
        "frozen_shared20": False,
        "pairs": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT.parent.parent,
                        help="Checkout containing the three hash-pinned public source files")
    args = parser.parse_args()
    records = extract(args.repo_root)
    write_records(records, controls.DEFAULT_SOURCE)
    controls.build()
    verification = controls.verify()
    actual = metrics(controls.DEFAULT_OUTPUT)
    expected = json.loads((ROOT / "reports/expected_format_metrics.json").read_text(encoding="utf-8"))
    if actual != expected:
        raise ValueError("Generated text/diff hashes or structural metrics differ from the published baseline")
    controls.write_json(ROOT / "build/reproduced_format_metrics.json", actual)
    test = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    log = test.stdout + test.stderr
    (ROOT / "build/test_results.txt").write_text(log, encoding="utf-8")
    print(log, end="")
    if test.returncode:
        raise SystemExit(test.returncode)
    result = {
        "artifact_verification": verification,
        "published_metrics_exact_match": True,
        "format_regression_tests": 18,
        "input_safety_tests": 6,
        "test_process_exit_code": 0,
        "extracted_input_sha256": digest(controls.DEFAULT_SOURCE),
        "reproduced_metrics_sha256": digest(ROOT / "build/reproduced_format_metrics.json"),
        "encoder_calls": 0,
        "judge_calls": 0,
        "scientific_scoring_runs": 0,
    }
    controls.write_json(ROOT / "build/reproduction_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
