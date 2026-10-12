"""Apply one fieldwise scoring configuration to all public v11 returns.

Reuses actual model returns, full source documents and unchanged original SR/SP.
Writes separate revised results; it does not make model requests or overwrite
archived scores. Includes both arms of all 15 existing controlled pairs.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import cce_fieldwise_scoring_v1 as scorer
import cce_operation_coverage_scope_batch_v1 as inputs

numeric = scorer.numeric
ROUND = inputs.base.BASE


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def table(out, name, rows):
    save(out / (name + ".json"), rows)
    if rows:
        with (out / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)


def complete(metrics):
    return metrics is not None and all(numeric.finite(metrics[k]) for k in ("Com", "Cor", "Eff"))


def compare_pairs(cells):
    indexed = {c["case_id"]: c for c in cells if c["cohort"] == "E2"}
    pairs = inputs.j.read(ROUND / "grounded_controls_v11/pairs.json")
    rows = []
    for pair in pairs:
        before, after = indexed[pair["baseline_case_id"]], indexed[pair["variant_case_id"]]
        for side in ["original", "revised"]:
            b, v = before[side + "_metrics"], after[side + "_metrics"]
            for metric in numeric.METRICS:
                bv, vv = None if b is None else b[metric], None if v is None else v[metric]
                rows.append({"pair_id": pair["pair_id"], "condition": pair["condition"],
                    "question_id": pair["question_id"], "processing": side, "metric": metric,
                    "baseline": bv, "variant": vv,
                    "delta": vv - bv if numeric.finite(bv) and numeric.finite(vv) else None,
                    "both_full_CCE": complete(b) and complete(v)})
    return rows


def repeats(cells):
    grouped = defaultdict(list)
    for cell in cells:
        if cell["cohort"] == "Qwen_repeats":
            grouped[cell["anonymous_answer_id"]].append(cell)
    rows = []
    for aid, group in sorted(grouped.items()):
        for side in ["original", "revised"]:
            for metric in numeric.METRICS:
                values = [c[side + "_metrics"][metric] for c in group if c[side + "_metrics"] is not None and numeric.finite(c[side + "_metrics"][metric])]
                rows.append({"answer": aid, "processing": side, "metric": metric,
                    "finite_repeats": len(values), "planned_repeats": len(group),
                    "complete_three_repeats": len(values) == 3,
                    "range": max(values) - min(values) if len(values) >= 2 else None,
                    "deterministic_step_metric": metric in ("sr", "sp")})
    return rows


def run(out):
    if out.exists():
        raise FileExistsError("Use a new output directory; original runs are retained.")
    out.mkdir(parents=True)
    code_paths = [Path(__file__), Path(scorer.__file__), Path(scorer.fieldwise_base.__file__),
        Path(scorer.operation_scope.__file__), Path(scorer.labels.__file__), Path(numeric.__file__)]
    code_paths.append(Path(scorer.duration_scope.__file__))
    code_paths.append(Path(scorer.noncore_scope.__file__))
    implementation = [inputs.bind(p) for p in code_paths]
    save(out / "run_config.json", {"processing_version": scorer.VERSION, "implementation": implementation,
        "cohorts": ["development", "E2", "Qwen_repeats"], "new_model_requests": 0,
        "actual_command": [sys.executable, *sys.argv]})
    records = inputs.load_public_records()
    cells, errors = [], []
    for record in records:
        cell = {k: record[k] for k in ["cohort", "cell_id", "anonymous_answer_id", "trial_id", "judge", "repeat_index"]}
        cell.update(case_id=record["case"]["case_id"], question_id=record["case"]["question_id"],
            original_status=record["status"], original_metrics=record["original_metrics"],
            revised_metrics=None, revised_status="not_requested", error=None)
        if record["raw"] is None:
            cell["revised_metrics"] = record["original_metrics"]
            cell["revised_status"] = record["status"]
        else:
            try:
                conversion, result = scorer.evaluate(record["raw"], record["doc"], record["case"], record["step"])
                if conversion["raw_content_preserved"] != record["raw"]:
                    raise AssertionError("RAW_RETURN_CHANGED")
                for metric in ["sr", "sp"]:
                    if not numeric.same(result["metrics"][metric], record["original_metrics"][metric]):
                        raise AssertionError("ORIGINAL_STEP_VALUE_CHANGED:" + metric)
                if record["status"] == "success":
                    for metric in numeric.DIRECT + ["s_method", "s_trans", "Com", "Cor"]:
                        if not numeric.same(result["metrics"][metric], record["original_metrics"][metric]):
                            raise AssertionError("UNRELATED_COMPONENT_CHANGED:" + metric)
                folder = out / "cells" / record["cohort"] / record["cell_id"]
                save(folder / "conversion.json", conversion)
                save(folder / "numeric_result.json", result)
                cell.update(revised_metrics=result["metrics"], revised_status="scored",
                    label_unknown_pairs=result["occurrence_label_calculation"]["unknown_pairs_retained"],
                    label_remaining_issues=result["occurrence_label_calculation"].get("explicit_label_uncertainties", []),
                    time_remaining_issues=conversion["legacy_projection"]["time_calculation"]["issues"],
                    result_path=str(folder / "numeric_result.json"))
            except Exception as exc:
                cell["revised_status"] = "processing_error"
                cell["error"] = {"type": type(exc).__name__, "reason": str(exc)}
                cell["revised_metrics"] = numeric.derive({}, record["step"], False)
                errors.append({"trial_id": cell["trial_id"], **cell["error"]})
        cell["original_complete_CCE"] = complete(cell["original_metrics"])
        cell["revised_complete_CCE"] = complete(cell["revised_metrics"])
        cells.append(cell)
        print(json.dumps({k: cell[k] for k in ["cohort", "anonymous_answer_id", "repeat_index", "revised_status", "revised_complete_CCE", "error"]}), flush=True)
    # Give all table rows the same columns without altering any score values.
    keys = list(dict.fromkeys(k for c in cells for k in c))
    cells = [{k: c.get(k) for k in keys} for c in cells]
    aggregates = []
    for cohort in ["development", "E2", "Qwen_repeats"]:
        group = [c for c in cells if c["cohort"] == cohort]
        row = {"cohort": cohort, "planned": len(group), "actual_raw_returns": sum(c["revised_status"] != "user_cancelled_no_retry" for c in group),
            "revised_scored": sum(c["revised_status"] == "scored" for c in group), "processing_errors": sum(c["error"] is not None for c in group)}
        for side in ["original", "revised"]:
            row[side + "_complete_CCE"] = sum(c[side + "_complete_CCE"] for c in group)
            for metric in numeric.METRICS:
                row[side + "_" + metric + "_finite"] = sum(c[side + "_metrics"] is not None and numeric.finite(c[side + "_metrics"][metric]) for c in group)
        aggregates.append(row)
    table(out, "cells", cells)
    table(out, "cohort_summary", aggregates)
    table(out, "paired_results", compare_pairs(cells))
    table(out, "repeat_stability", repeats(cells))
    save(out / "errors.json", errors)
    inputs.base.verify_bindings(implementation)
    bindings = inputs.unique_bindings([p for r in records for p in r["paths"]])
    inputs.base.verify_bindings(bindings)
    save(out / "summary.json", {"status": "completed" if not errors else "completed_with_processing_errors",
        "cohorts": aggregates, "new_model_requests": 0, "original_files_modified": False,
        "analysis_scope": "same_configuration_posthoc_reprocessing", "errors": errors,
        "input_bindings": bindings, "implementation": implementation, "actual_command": [sys.executable, *sys.argv]})
    print(json.dumps({"status": "completed", "cohorts": aggregates, "errors": errors}), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.out.resolve()))
