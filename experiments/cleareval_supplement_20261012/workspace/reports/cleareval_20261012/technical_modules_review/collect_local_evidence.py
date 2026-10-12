"""Read saved artifacts only; never import a scorer or invoke a model."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import math
import platform

ROOT = Path(r"C:\ClearEval")
HERE = Path(__file__).resolve().parent
DAY = ROOT / "reports/cleareval_20261012"
inputs = []


def read(relative):
    path = ROOT / relative
    raw = path.read_bytes()
    inputs.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    return json.loads(raw.decode("utf-8-sig"))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def inventory(relative):
    rows = read(relative)
    returned = [r for r in rows if isinstance(r.get("metrics"), dict)]
    complete = [r for r in returned if all(finite(r["metrics"].get(k)) for k in ("Com", "Cor", "Eff", "IA", "HV"))]
    unbranched = [r for r in complete if r.get("time_candidate_ledger", {}).get("single_unbranched_point") is True]
    return rows, {"positions": len(rows), "saved_returns_with_metrics": len(returned),
                  "numeric_complete_including_inherited_points": len(complete),
                  "numeric_complete_and_current_time_ledger_unbranched": len(unbranched),
                  "complete_cell_ids": [r["cell_id"] for r in complete],
                  "complete_unbranched_cell_ids": [r["cell_id"] for r in unbranched],
                  "finite_time_scores": sum(finite(r["metrics"].get("s_time")) for r in returned)}


language = read("reports/cleareval_20261012/step_language_probe/run_01/summary.json")
lang_rows = read("reports/cleareval_20261012/step_language_probe/run_01/results.json")
many_to_one = []
for row in lang_rows:
    if row["answer_id"] == "R3C07" and row["representation"] == "english_body_original_metadata" and row["threshold"] == .7:
        many_to_one = [{k: m[k] for k in ("reference_index", "generated_index", "similarity", "matched")}
                       for m in row["score"]["matches"] if m["matched"]]

canonical, current_counts = inventory("reports/cleareval_20261012/automatic_time_scope/canonical32_04/results.json")
archived, archive_counts = inventory("reports/cleareval_20261012/automatic_time_scope/archived67_04/results.json")
confirm = []
for row in canonical:
    if not row["cell_id"].startswith("R3C"):
        continue
    ledger = row.get("time_candidate_ledger", {})
    confirm.append({"cell_id": row["cell_id"], "question_id": row["question_id"],
                    "metrics": row["metrics"], "answer_sha256": row.get("answer_sha256"),
                    "current_time_point_hours": ledger.get("hours"),
                    "single_unbranched_point": ledger.get("single_unbranched_point"),
                    "candidate_point_applied": row.get("candidate_point_applied"),
                    "time_scenarios": [{k: s.get(k) for k in ("scenario_id", "selection", "bounds_hours", "hours")}
                                       for s in ledger.get("scenarios", [])],
                    "issues": ledger.get("issues", [])})

joint = read("reports/cleareval_20261012/automatic_time_scope/joint_01/summary.json")
dependency = read("reports/cleareval_20261012/automatic_time_scope/joint_01/source_dependency_audit.json")
threshold = read("reports/cleareval_20261012/automatic_time_scope/threshold_01/summary.json")
completion = read("reports/cleareval_20261012/automatic_time_scope/completion_audit.json")
versions = {}
for name in ("torch", "sentence-transformers", "transformers", "numpy", "scipy", "networkx", "pydantic", "jsonschema"):
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = "not installed in this Python environment"

for rel in (
    "ClearEval_Codex_Experiments_v1_20261008/FRAMEWORK_SPEC.md",
    "ClearEval_Codex_Experiments_v1_20261008/experiment_config.yaml",
    "ClearEval-public/scripts/cce_validation.py",
    "ClearEval-public/scripts/cce_grounded_offline_scoring_v1.py",
    "ClearEval-public/scripts/cce_scoped_midpoint_scorer_v1.py",
    "ClearEval-public/scripts/cce_selected_label_source_v1.py",
    "ClearEval-public/scripts/cce_source_time_ledger_v1.py",
    "reports/cleareval_20261012/automatic_time_scope/resolved_config.yaml",
):
    path = ROOT / rel
    inputs.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

output = {
    "scope": "Research inventory of saved results; all input experimental results predate this review.",
    "new_model_calls": 0, "new_embeddings": 0, "new_experimental_observations": 0,
    "new_expert_records": 0, "new_score_calculations": 0,
    "counts_are_not_accuracy": True,
    "language_probe_historical": language,
    "C07_english_at_0p7_matched_pairs": many_to_one,
    "current_cohort_counts": current_counts,
    "archive_counts": archive_counts,
    "exposed_confirmation_examples": confirm,
    "joint_historical": joint, "source_dependency_historical": dependency,
    "threshold_historical": threshold,
    "previous_completion_audit": {k: completion.get(k) for k in ("goal_complete", "actual_new_qualitative_pairs", "expert_records_added", "wetlab_rows_added")},
    "runtime": {"python": platform.python_version(), "packages": versions},
    "mathematical_illustrations_not_experiments": {
        "ordered_bootstrap_draws": {str(n): n ** n for n in (2, 3, 5)},
        "MC_standard_error_for_probability_p_0p5_B_2000": math.sqrt(.25 / 2000),
        "one_sided_95pct_binomial_lower_if_15_of_15_independent_successes": .05 ** (1/15),
    },
    "source_files": inputs,
}
(HERE / "LOCAL_EVIDENCE.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"current": {k: v for k, v in current_counts.items() if not isinstance(v, list)},
                  "archive": {k: v for k, v in archive_counts.items() if not isinstance(v, list)},
                  "source_files": len(inputs), "new_model_calls": 0}, ensure_ascii=False))
