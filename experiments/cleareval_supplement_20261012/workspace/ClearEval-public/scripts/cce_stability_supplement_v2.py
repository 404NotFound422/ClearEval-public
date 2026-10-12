"""Freeze and analyze the original two-answer stability design using v2 evidence.

The existing local runner performs all new calls. The two exactly identical Qwen
repeat-zero observations are copied with provenance from the v2 control batch.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_alternative_development as helper
import cce_validation as scoring
import cce_judges as judges

BASE = ROOT / "artifacts/cce_validation"
OUT = BASE / "judges/local_stability_supplement_v2"
SOURCE = BASE / "judges/local_controls_supplement_v2"
helper.OUT = OUT
save, table = helper.save, helper.table
LEDGER = BASE / "judges/request_ledger.jsonl"
METRICS, MAXIMA = helper.METRICS, helper.MAXIMA


def commands(plan):
    lines = ["# Executed/planned v2 stability commands", "", "Status: " + plan["status"], "",
             "Two fixed answers, two judge families, three repeats; copied repeat-zero observations are counted once.", "", "```powershell"]
    for key in ["prepare_argv", "preflight_argv", "run_argv", "analyze_argv"]:
        lines.append("& " + " ".join("'" + x.replace("'", "''") + "'" for x in plan[key]))
    (OUT / "commands.md").write_text("\n".join(lines + ["```", ""]) + "\n", encoding="utf-8")


def prepare(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if any((OUT / "trials").glob("*.json")):
        raise ValueError("Existing observations freeze this stability batch")
    source_summary = scoring.read(SOURCE / "development_summary.json")
    assert source_summary["actual_trial_count"] == 21
    cases = [c for c in scoring.read(SOURCE / "cases.json")["cases"] if c["question_id"] in [2, 21] and c["condition"] == "baseline" and c["source_case_id"].endswith("__baseline")]
    assert len(cases) == 2 and {c["question_id"] for c in cases} == {2, 21}
    local = scoring.read(SOURCE / "local_config_snapshot.json")
    assert {m["name"] for m in local["models"]} == {"local_qwen3_8b", "local_llama3_8b"}
    assert all(m["max_tokens"] == 8192 and m["temperature"] == 0 and m["host"] == "http://127.0.0.1:11434" for m in local["models"])
    checks = []
    for c in cases:
        prompt = helper.exact_runner_prompt(c)
        for m in local["models"]:
            bound = len(prompt.encode("utf-8")) + m["max_tokens"] + 256
            checks.append({"case_id": c["case_id"], "judge": m["name"], "prompt_sha256": scoring.digest(prompt),
                           "conservative_context_bound": bound, "num_ctx": m["num_ctx"], "max_output_tokens": 8192,
                           "fits": bound <= m["num_ctx"]})
    assert all(c["fits"] for c in checks), "No truncation allowed; contact parent if context exceeds bound"
    save("cases.json", {"cases": cases})
    save("local_config_snapshot.json", local)
    save("offline_context_preflight.json", {"checks": checks, "all_fit": True, "model_requests": 0})
    source_trials = [scoring.read(p) for p in (SOURCE / "trials").glob("*.json")]
    reuse = []
    for c in cases:
        expected = judges.digest({"question": c["specific_question"], "question_id": c["question_id"], "protocol": c["model_response"], "references": c["references"]})
        matches = [t for t in source_trials if t["case_id"] == c["case_id"] and t["judge"] == "local_qwen3_8b" and t["repeat_index"] == 0]
        assert len(matches) == 1
        t = matches[0]
        assert t["full_text_input_sha256"] == expected and t["references_sha256"] == judges.digest(c["references"])
        source_trial = SOURCE / "trials" / (t["trial_id"] + ".json")
        destination = OUT / "trials" / source_trial.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source_trial, destination)
        src_attempt = SOURCE / "attempts" / f"{t['trial_id']}_{t['attempt']}"
        dst_attempt = OUT / "attempts" / src_attempt.name
        shutil.copytree(src_attempt, dst_attempt)
        reuse.append({"case_id": c["case_id"], "trial_id": t["trial_id"], "source_trial_path": str(source_trial),
                      "source_trial_sha256": scoring.filehash(source_trial), "copy_sha256": scoring.filehash(destination),
                      "source_attempt_path": str(src_attempt), "status": t["status"],
                      "successful_exact_reuse": t["status"] == "success", "repeat_index": 0,
                      "input_sha256": expected, "judge_contract_sha256": t["identity"]["contract_sha256"],
                      "new_request": False, "failed_repeat_zero_will_not_be_retried": t["status"] != "success"})
    source_steps = [s for s in scoring.read(SOURCE / "step_results.json") if s["case_id"] in {c["case_id"] for c in cases}]
    assert len(source_steps) == 2
    save("step_results.json", source_steps)
    save("reuse_manifest.json", reuse)
    common = ["--cases", str(OUT / "cases.json"), "--out", str(OUT), "--model-config", str(OUT / "local_config_snapshot.json"),
              "--models", "local_qwen3_8b", "local_llama3_8b", "--repeats", "3", "--temperature", "0",
              "--max-attempts", "1", "--max-calls", "10", "--timeout-seconds", "600", "--ledger", str(LEDGER), "--total-budget", "300"]
    plan = {"prepared_utc": datetime.now(timezone.utc).isoformat(), "status": "prepared_context_verified",
            "scope": "same_two_answers_stability_recomputed_with_supplement_v2_evidence_pending_expert",
            "question_ids": [2, 21], "source_answers": 2, "task_families": 2, "source_families": 1,
            "judge_families": 2, "repeats_per_judge_per_answer": 3, "planned_observations": 12,
            "successful_exact_reused_observations": sum(x["successful_exact_reuse"] for x in reuse),
            "planned_new_requests": 10, "max_attempts": 1, "temperature": 0, "output_budget": 8192,
            "formal_eligible": False, "formal_completed_observations": 0,
            "source_control_batch": str(SOURCE), "source_case_file_sha256": scoring.filehash(SOURCE / "cases.json"),
            "source_step_file_sha256": scoring.filehash(SOURCE / "step_results.json"),
            "frozen_files": {n: scoring.filehash(OUT / n) for n in ["cases.json", "local_config_snapshot.json", "reuse_manifest.json", "step_results.json"]},
            "step_adapter_sha256": scoring.filehash(ROOT / "scripts/cce_validation.py"),
            "package_requests_at_preparation": sum(r.get("event") == "request_started" for r in judges.ledger_rows(LEDGER)),
            "prepare_argv": [str(helper.PYTHON), "scripts/cce_stability_supplement_v2.py", "prepare"],
            "preflight_argv": [str(helper.PYTHON), "scripts/cce_judges.py", "preflight"] + common,
            "run_argv": [str(helper.PYTHON), "scripts/cce_judges.py", "run"] + common + ["--allow-api"],
            "analyze_argv": [str(helper.PYTHON), "scripts/cce_stability_supplement_v2.py", "analyze"],
            "context_bound_max": max(c["conservative_context_bound"] for c in checks), "context_all_fit": True,
            "no_post_result_case_selection": True, "old_stability_results_not_overwritten_or_pooled": True}
    save("plan.json", plan)
    commands(plan)
    print(json.dumps({k: plan[k] for k in ["status", "planned_observations", "planned_new_requests", "successful_exact_reused_observations", "context_bound_max", "package_requests_at_preparation"]}))


def analyze(args):
    plan = scoring.read(OUT / "plan.json")
    for n, sha in plan["frozen_files"].items():
        assert scoring.filehash(OUT / n) == sha
    assert scoring.filehash(ROOT / "scripts/cce_validation.py") == plan["step_adapter_sha256"]
    cases = {c["case_id"]: c for c in scoring.read(OUT / "cases.json")["cases"]}
    steps = {s["case_id"]: s for s in scoring.read(OUT / "step_results.json")}
    reuse = {r["trial_id"]: r for r in scoring.read(OUT / "reuse_manifest.json")}
    trials = [scoring.read(p) for p in (OUT / "trials").glob("*.json")]
    preflight_contract = scoring.read(OUT / "preflight.json")["contract"]
    example, rows, records, runtimes = helper.rubric_example(), [], [], []
    seen = set()
    for t in trials:
        key = (t["case_id"], t["judge"], t["repeat_index"])
        assert key not in seen and t["repeat_index"] in [0, 1, 2] and t["attempt"] == 1
        seen.add(key)
        c = cases[t["case_id"]]
        expected = judges.digest({"question": c["specific_question"], "question_id": c["question_id"], "protocol": c["model_response"], "references": c["references"]})
        assert t["full_text_input_sha256"] == expected and t["references_sha256"] == judges.digest(c["references"])
        model_contract = next(m for m in preflight_contract["models"] if m["name"] == t["judge"])
        expected_contract = judges.digest({**preflight_contract, "models": [model_contract]})
        assert t["identity"]["contract_sha256"] == expected_contract
        assert t["trial_id"] == judges.digest({"case_id": c["case_id"], "input_sha256": expected,
                                               "judge": t["judge"], "repeat_index": t["repeat_index"],
                                               "contract_sha256": expected_contract})
        if t["trial_id"] in reuse:
            assert scoring.filehash(OUT / "trials" / (t["trial_id"] + ".json")) == reuse[t["trial_id"]]["source_trial_sha256"]
        e, s = t["evaluation"], steps[t["case_id"]]["step_result"]
        raw = t["preserved_numeric_proposals"]
        assert raw == judges.proposals(e)
        com = .4 * s["sr"] + .6 * raw["c_param"] / 3 if s["sr"] is not None and raw["c_param"] is not None else None
        dims = [com, raw["Cor"], raw["Eff"]]
        nums = {**raw, "sr": s["sr"], "sp": s["sp"], "Com": com,
                "IA": min(dims) if all(v is not None for v in dims) else None,
                "HV": math.prod(dims) if all(v is not None for v in dims) else None}
        ext = e.get("extraction")
        route = ext.get("method_name") if isinstance(ext, dict) else None
        flags = {"extraction_missing": not isinstance(ext, dict), "extracted_route": route,
                 "explicit_route_mismatch": bool(route and route.lower().replace("-", "") != "fdisco"),
                 "extraction_exactly_copies_rubric_example": ext == example}
        elapsed = (datetime.fromisoformat(t["finished_utc"]) - datetime.fromisoformat(t["started_utc"])).total_seconds()
        attempt = OUT / "attempts" / f"{t['trial_id']}_{t['attempt']}"
        prompt_sha = scoring.digest((attempt / "prompt.txt").read_text(encoding="utf-8"))
        assert prompt_sha == scoring.digest(helper.exact_runner_prompt(c))
        provider = scoring.read(attempt / "provider_response.json") if (attempt / "provider_response.json").exists() else {}
        runtime = {"trial_id": t["trial_id"], "case_id": t["case_id"], "judge": t["judge"], "repeat_index": t["repeat_index"],
                   "exact_reused": t["trial_id"] in reuse, "wall_seconds": elapsed, "provider_total_seconds": provider.get("total_duration", 0) / 1e9,
                   "output_tokens": provider.get("eval_count"), "done_reason": provider.get("done_reason")}
        runtimes.append(runtime)
        complete = t["status"] == "success" and t.get("actual_api_request_made") and t.get("new_extraction_available")
        row = {"case_id": t["case_id"], "question_id": c["question_id"], "judge": t["judge"], "repeat_index": t["repeat_index"],
               "trial_id": t["trial_id"], "status": t["status"], "technical_pipeline_complete": bool(complete),
               "exact_reused": t["trial_id"] in reuse, "formal_eligible": False, "reference_id": s["reference_id"],
               "input_sha256": expected, "references_sha256": t["references_sha256"],
               "judge_contract_sha256": t["identity"]["contract_sha256"], "pipeline_config_sha256": t["pipeline_config_sha256"],
               "step_config_sha256": steps[t["case_id"]]["step_config_sha256"],
               "extraction_sha256": t["extraction_sha256"], "wall_seconds": elapsed, **nums, **flags}
        rows.append(row)
        records.append({**row, "source_trial_path": str(OUT / "trials" / (t["trial_id"] + ".json")),
                        "candidate_raw_and_derived": nums, "raw_judgments": e.get("legacy_diagnostics", {}),
                        "candidate_normalized_items": {k: ((v / MAXIMA[k] + 1) / 2 if k == "s_method" else v / MAXIMA[k]) if v is not None else None for k, v in raw.items() if k in MAXIMA},
                        "raw_teacher_content": e.get("teacher_generation", {}).get("content"), "extraction": ext,
                        "official_scores": e.get("official_scores"), "official_scores_field_present": "official_scores" in e,
                        "upstream_cce_eligible": e.get("cce_eligible"), "upstream_integrity": e.get("integrity"),
                        "formal_scores": {k: None for k in ["sr", "sp", "Com", "Cor", "Eff", "IA", "HV"]},
                        "formal_na_reasons": ["reference_and_extraction_not_expert_confirmed"],
                        "candidate_na_reasons": {k: "upstream_or_dependency_missing" for k, v in nums.items() if v is None},
                        "failure_details": {k: e.get(k) for k in ["_error", "_error_type", "failure_stage"] if k in e}})
    spread, flips = [], []
    for cid in cases:
        for judge in ["local_qwen3_8b", "local_llama3_8b"]:
            group = [r for r in rows if r["case_id"] == cid and r["judge"] == judge]
            for metric in METRICS:
                values = [r[metric] for r in group if r["technical_pipeline_complete"] and r[metric] is not None]
                spread.append({"case_id": cid, "question_id": cases[cid]["question_id"], "judge": judge, "metric": metric,
                               "planned_repeats": 3, "observed_repeats": len(group), "finite_repeats": len(values), "na_repeats": 3 - len(values),
                               "mean": statistics.mean(values) if values else None, "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
                               "min": min(values) if values else None, "max": max(values) if values else None,
                               "range": max(values) - min(values) if values else None, "distinct_values": len(set(values)),
                               "distinct_extractions": len({r["extraction_sha256"] for r in group if r["technical_pipeline_complete"]}),
                               "distinct_references": len({r["reference_id"] for r in group}), "formal_eligible": False})
    for judge in ["local_qwen3_8b", "local_llama3_8b"]:
        for metric in METRICS:
            differences = []
            for repeat in range(3):
                two = {r["question_id"]: r for r in rows if r["judge"] == judge and r["repeat_index"] == repeat}
                delta = two[2][metric] - two[21][metric] if all(q in two and two[q]["technical_pipeline_complete"] and two[q][metric] is not None for q in [2, 21]) else None
                differences.append(delta)
            signs = [None if v is None else 1 if v > 1e-12 else -1 if v < -1e-12 else 0 for v in differences]
            flips.append({"judge": judge, "metric": metric, "question_2_minus_21": differences, "rank_directions": signs,
                          "strict_rank_flip": -1 in signs and 1 in signs, "direction_or_tie_changes": len({v for v in signs if v is not None}) > 1,
                          "finite_pair_repeats": sum(v is not None for v in signs), "formal_eligible": False})
    for name, value in [("per_observation.json", records), ("repeat_components.json", spread), ("rank_flips.json", flips), ("runtime.json", runtimes)]:
        save(name, value)
    table("per_observation.csv", rows)
    table("repeat_components.csv", spread)
    table("rank_flips.csv", flips)
    table("runtime.csv", runtimes)
    new_ids = {t["trial_id"] for t in trials} - set(reuse)
    ledger = judges.ledger_rows(LEDGER)
    summary = {"planned_observations": 12, "actual_observations": len(trials), "source_answers": 2, "question_ids": [2, 21],
               "judge_families": 2, "repeats": 3, "successful_exact_reused_observations": sum(r["exact_reused"] and r["technical_pipeline_complete"] for r in rows),
               "technical_successful_observations": sum(r["technical_pipeline_complete"] for r in rows),
               "complete_candidate_cce_observations": sum(all(r[k] is not None for k in ["Com", "Cor", "Eff"]) for r in rows),
               "new_requests_this_batch": sum(r.get("event") == "request_started" and r.get("trial_id") in new_ids for r in ledger),
               "package_requests_in_ledger": sum(r.get("event") == "request_started" for r in ledger),
               "formal_completed_observations": 0, "formal_eligible": False,
               "explicit_route_mismatches": sum(r["explicit_route_mismatch"] for r in rows),
               "rubric_example_copies": sum(r["extraction_exactly_copies_rubric_example"] for r in rows),
               "strict_rank_flip_metrics": sum(r["strict_rank_flip"] for r in flips),
               "component_groups_with_variation": sum(r["range"] is not None and r["range"] > 1e-12 for r in spread),
               "old_v1_observations_not_pooled": True, "scope": "conditional two-answer local stability development, no extraction accuracy or cross-judge validity claim"}
    save("development_summary.json", summary)
    save("verification.json", {"all_passed": True, "all_planned_observations_present": len(trials) == 12,
                              "exact_input_reference_prompt_and_reuse_hashes_verified": True,
                              "fixed_two_answer_design": True, "no_retries": all(t["attempt"] == 1 for t in trials),
                              "formal_eligible": False})
    plan.update(status="computed_development" if len(trials) == 12 else "computed_development_with_missing_observations",
                actual_new_requests=summary["new_requests_this_batch"], actual_observations=len(trials),
                analysis_script_sha256=scoring.filehash(Path(__file__)))
    save("plan.json", plan)
    commands(plan)
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "analyze"])
    args = parser.parse_args()
    prepare(args) if args.command == "prepare" else analyze(args)
