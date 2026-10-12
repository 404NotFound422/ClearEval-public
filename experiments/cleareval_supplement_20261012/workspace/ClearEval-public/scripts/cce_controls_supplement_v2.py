"""Freeze and analyze existing control texts against the supplement-derived references.

No scientific text is edited and no model transport is implemented here. Calls use
the existing cce_judges.py runner, with one attempt per distinct full text.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_alternative_development as helper
import cce_validation as scoring
import cce_judges as judges

BASE = ROOT / "artifacts/cce_validation"
OUT = BASE / "judges/local_controls_supplement_v2"
helper.OUT = OUT
save, table = helper.save, helper.table
PYTHON = helper.PYTHON
SOURCE_FILES = [BASE / "controls" / name for name in
                ["cases.json", "order_conflict_cases.json", "granularity_cases.json",
                 "edits.json", "order_conflict_edits.json", "granularity_edits.json"]]
REFS = BASE / "reference_recovery/supplement_bound/references_supplement_v2.json"
LEDGER = BASE / "judges/request_ledger.jsonl"
METRICS, MAXIMA = helper.METRICS, helper.MAXIMA


def prepare(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if any((OUT / "trials").glob("*.json")) or any((OUT / "attempts").glob("*/request_receipt.json")):
        raise ValueError("Existing requests freeze this batch")
    refs = [r for r in scoring.read(REFS)["references"] if r["route_id"] == "FDISCO"]
    assert len(refs) == 2
    raw_sets = [scoring.read(p)["cases"] for p in SOURCE_FILES[:3]]
    assert [len(x) for x in raw_sets] == [12, 6, 6]
    originals, origins, duplicate_ids = {}, {}, []
    for path, rows in zip(SOURCE_FILES, raw_sets):
        for row in rows:
            cid = row["case_id"]
            if cid in originals:
                assert all(row[k] == originals[cid][k] for k in ["model_response", "specific_question", "question_id"])
                duplicate_ids.append(cid)
            else:
                originals[cid] = row
                origins[cid] = str(path)
    assert len(originals) == 21 and len(duplicate_ids) == 3
    assert len({scoring.digest(c["model_response"]) for c in originals.values()}) == 21
    cases, mapping = [], {}
    for cid, source in originals.items():
        selected = [r for r in refs if source["question_id"] in r["question_ids"]]
        assert len(selected) == 1
        assert scoring.selected_route(source["model_response"], selected)[0] == "FDISCO"
        new_id = cid + "__supplement_v2"
        mapping[cid] = new_id
        cases.append({**source, "case_id": new_id, "source_case_id": cid,
                      "source_case_file": origins[cid], "references": selected,
                      "source_scope": source.get("scope"),
                      "scope": "supplement_v2_full_text_control_development_pending_expert",
                      "answer_source": origins[cid],
                      "answer_sha256": scoring.digest(source["model_response"]),
                      "question_sha256": scoring.digest(source["specific_question"]),
                      "formal_eligible": False, "expert_confirmation": None,
                      "reference_status": "source_extracted_not_expert_confirmed"})
    pairs = []
    for row in raw_sets[0]:
        if row["condition"] != "baseline":
            pairs.append({"baseline_case_id": row["base_id"] + "__baseline",
                          "variant_case_id": row["case_id"], "question_id": row["question_id"],
                          "condition": row["condition"], "source_edit_file": str(SOURCE_FILES[3])})
    for path, rows in [(SOURCE_FILES[4], raw_sets[1]), (SOURCE_FILES[5], raw_sets[2])]:
        lookup = {c["case_id"]: c for c in rows}
        for edit in scoring.read(path)["edits"]:
            pairs.append({"baseline_case_id": edit["baseline_case_id"],
                          "variant_case_id": edit["variant_case_id"], "question_id": edit["question_id"],
                          "condition": lookup[edit["variant_case_id"]]["condition"], "source_edit_file": str(path)})
    assert len(pairs) == 15
    for p in pairs:
        p["source_baseline_case_id"], p["source_variant_case_id"] = p["baseline_case_id"], p["variant_case_id"]
        p["pair_id"] = p["variant_case_id"] + "__supplement_v2_pair"
        p["baseline_case_id"], p["variant_case_id"] = mapping[p["baseline_case_id"]], mapping[p["variant_case_id"]]
        p.update(formal_eligible=False, formal_complete=False, expert_confirmation=None)
    local = scoring.read(helper.LOCAL_CONFIG)
    model = next(m for m in local["models"] if m["name"] == "local_qwen3_8b")
    assert model["host"] == "http://127.0.0.1:11434" and model["temperature"] == 0
    model["max_tokens"] = args.max_output_tokens
    snapshot = {"cases": cases, "pairs": pairs, "references": refs, "model_config": local}
    snapshot_id = scoring.digest(snapshot)
    save(f"preparations/{snapshot_id}/snapshot.json", snapshot)
    for name, obj in [("cases.json", {"cases": cases}), ("pairs.json", pairs),
                      ("references.json", {"references": refs}), ("local_config_snapshot.json", local)]:
        save(name, obj)
    checks = []
    for c in cases:
        prompt = helper.exact_runner_prompt(c)
        bound = len(prompt.encode("utf-8")) + model["max_tokens"] + 256
        checks.append({"case_id": c["case_id"], "prompt_sha256": scoring.digest(prompt),
                       "prompt_utf8_bytes": len(prompt.encode("utf-8")), "max_output_tokens": model["max_tokens"],
                       "template_reserve": 256, "conservative_context_bound": bound,
                       "configured_num_ctx": model["num_ctx"], "fits": bound <= model["num_ctx"]})
    save("offline_context_preflight.json", {"checks": checks, "all_fit": all(c["fits"] for c in checks), "model_requests": 0})
    common = ["--cases", str(OUT / "cases.json"), "--out", str(OUT), "--model-config", str(OUT / "local_config_snapshot.json"),
              "--models", "local_qwen3_8b", "--repeats", "1", "--temperature", "0", "--max-attempts", "1",
              "--max-calls", "21", "--timeout-seconds", "600", "--ledger", str(LEDGER), "--total-budget", "300"]
    plan = {"scope": "supplement_v2_existing_control_recomputation_provisional",
            "prepared_utc": datetime.now(timezone.utc).isoformat(), "snapshot_id": snapshot_id,
            "source_files": [{"path": str(p), "sha256": scoring.filehash(p)} for p in SOURCE_FILES + [REFS]],
            "frozen_files": {n: scoring.filehash(OUT / n) for n in ["cases.json", "pairs.json", "references.json", "local_config_snapshot.json"]},
            "step_adapter_sha256": scoring.filehash(ROOT / "scripts/cce_validation.py"),
            "helper_script_sha256": scoring.filehash(Path(helper.__file__)),
            "step_threshold": .7, "planned_distinct_full_texts": 21, "planned_pairs": 15,
            "source_answers": 3, "question_ids": [2, 21, 22], "task_families": 2, "source_families": 1,
            "same_batch_canonical_baselines_reused_for_granularity": duplicate_ids,
            "cross_version_trial_reuse": 0, "reference_filter": "declared_FDISCO_and_question_id",
            "reference_filter_scope": "conditional_route_diagnostic_not_protocol_quality_truth",
            "judge": "local_qwen3_8b", "temperature": 0, "repeats": 1, "maximum_attempts_each": 1,
            "planned_new_requests": 21, "output_budget": model["max_tokens"],
            "context_all_fit": all(c["fits"] for c in checks),
            "context_bound_min": min(c["conservative_context_bound"] for c in checks),
            "context_bound_max": max(c["conservative_context_bound"] for c in checks),
            "package_requests_at_preparation": sum(x.get("event") == "request_started" for x in judges.ledger_rows(LEDGER)),
            "formal_eligible": False, "confirmed_eligible_pairs": 0, "formal_completed_pairs": 0,
            "old_15_pairs_untouched": True, "not_15_new_independent_pairs": True,
            "preparation_argv": [str(PYTHON), "scripts/cce_controls_supplement_v2.py", "prepare", "--max-output-tokens", str(args.max_output_tokens)],
            "preflight_argv": [str(PYTHON), "scripts/cce_judges.py", "preflight"] + common,
            "run_argv": [str(PYTHON), "scripts/cce_judges.py", "run"] + common + ["--allow-api"],
            "analysis_argv": [str(PYTHON), "scripts/cce_controls_supplement_v2.py", "analyze"],
            "status": "prepared_context_verified" if all(c["fits"] for c in checks) else "context_limit_blocked"}
    save("plan.json", plan)
    commands(plan, executed=False)
    print(json.dumps({k: plan[k] for k in ["status", "planned_distinct_full_texts", "planned_pairs", "output_budget", "context_bound_min", "context_bound_max", "package_requests_at_preparation"]}))


def commands(plan, executed):
    lines = ["# Supplement-v2 controlled recomputation", "", "Execution status: " + plan["status"], "",
             "Original text and edit provenance remain in the frozen source files. Formal eligibility remains zero.", "", "```powershell"]
    for key in ["preparation_argv", "preflight_argv", "run_argv", "analysis_argv"]:
        lines.append("& " + " ".join("'" + s.replace("'", "''") + "'" for s in plan[key]))
    lines += ["```", "", "Actual run receipts and the shared request ledger establish request counts; planned commands alone do not."]
    (OUT / "commands.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalized(raw):
    return {k: ((v / MAXIMA[k] + 1) / 2 if k == "s_method" else v / MAXIMA[k]) if v is not None else None
            for k, v in raw.items() if k in MAXIMA}


def analyze(args):
    plan = scoring.read(OUT / "plan.json")
    for n, sha in plan["frozen_files"].items():
        assert scoring.filehash(OUT / n) == sha, n
    for source in plan["source_files"]:
        assert scoring.filehash(Path(source["path"])) == source["sha256"], source["path"]
    assert scoring.filehash(ROOT / "scripts/cce_validation.py") == plan["step_adapter_sha256"]
    assert scoring.filehash(Path(helper.__file__)) == plan["helper_script_sha256"]
    cases = scoring.read(OUT / "cases.json")["cases"]
    pairs = scoring.read(OUT / "pairs.json")
    trials = [scoring.read(p) for p in sorted((OUT / "trials").glob("*.json"))]
    indexed = {t["case_id"]: t for t in trials}
    assert len(indexed) == len(trials)
    assert all(t["judge"] == "local_qwen3_8b" and t["repeat_index"] == 0 and t["attempt"] == 1 for t in trials)
    encoder = helper.ScopedEncoder()
    config = {"encoder": encoder.identity, "threshold": .7, "adapter_version": scoring.VERSION,
              "adapter_sha256": plan["step_adapter_sha256"], "references_file_sha256": plan["frozen_files"]["references.json"],
              "filter": "question_id_and_declared_FDISCO"}
    save("step_config.json", config)
    example, records, steps, partial = helper.rubric_example(), [], [], []
    prompt_index = {c["case_id"]: c for c in scoring.read(OUT / "offline_context_preflight.json")["checks"]}
    runtime_checks, generation_checks = [], []
    for c in cases:
        refs, t = c["references"], indexed.get(c["case_id"])
        expected = judges.digest({"question": c["specific_question"], "question_id": c["question_id"], "protocol": c["model_response"], "references": refs})
        if t:
            assert t["full_text_input_sha256"] == expected and t["references_sha256"] == judges.digest(refs)
            attempt = OUT / "attempts" / f"{t['trial_id']}_{t['attempt']}"
            runtime_prompt = (attempt / "prompt.txt").read_text(encoding="utf-8")
            runtime_checks.append({"case_id": c["case_id"], "prompt_sha256_matches": scoring.digest(runtime_prompt) == prompt_index[c["case_id"]]["prompt_sha256"]})
            assert runtime_checks[-1]["prompt_sha256_matches"]
            provider_path = attempt / "provider_response.json"
            if provider_path.exists():
                provider = scoring.read(provider_path)
                generation_checks.append({"case_id": c["case_id"], "model": provider.get("model"),
                                          "done_reason": provider.get("done_reason"), "eval_count": provider.get("eval_count"),
                                          "output_budget": plan["output_budget"],
                                          "output_budget_exhausted": provider.get("done_reason") == "length" or
                                          (isinstance(provider.get("eval_count"), int) and provider["eval_count"] >= plan["output_budget"])})
        step = scoring.score_steps(c, refs, encoder, .7)
        steps.append({"case_id": c["case_id"], "answer_sha256": c["answer_sha256"], "step_config_sha256": scoring.digest(config),
                      "references_sha256": judges.digest(refs), "step_result": step})
        e = t.get("evaluation", {}) if t else {}
        raw = t.get("preserved_numeric_proposals", {}) if t else {}
        raw = {k: raw.get(k) for k in list(MAXIMA) + ["Cor", "Eff"]}
        if t:
            assert all(raw[k] == judges.proposals(e).get(k) for k in raw), "Preserved proposals disagree with upstream evaluation"
        com = .4 * step["sr"] + .6 * raw["c_param"] / 3 if step["sr"] is not None and raw["c_param"] is not None else None
        dims = [com, raw["Cor"], raw["Eff"]]
        nums = {**raw, "sr": step["sr"], "sp": step["sp"], "Com": com,
                "IA": min(dims) if all(x is not None for x in dims) else None,
                "HV": math.prod(dims) if all(x is not None for x in dims) else None}
        extraction = e.get("extraction")
        route = extraction.get("method_name") if isinstance(extraction, dict) else None
        flags = {"declared_route": step["route_id"], "extracted_route": route, "extraction_missing": not isinstance(extraction, dict),
                 "extracted_route_missing": not bool(route), "explicit_route_mismatch": bool(route and route.lower().replace("-", "") != "fdisco"),
                 "extraction_exactly_copies_rubric_example": extraction == example,
                 "interpretation": "Software observations; no expert labels or scientific validity conclusion"}
        complete = bool(t and t["status"] == "success" and t.get("actual_api_request_made") and t.get("new_extraction_available"))
        rec = {"case_id": c["case_id"], "source_case_id": c["source_case_id"], "base_id": c["base_id"],
               "condition": c["condition"], "question_id": c["question_id"], "generator_model": c["generator_model"],
               "answer_source": c["answer_source"], "answer_sha256": c["answer_sha256"], "question_sha256": c["question_sha256"],
               "full_text_input_sha256": expected, "references_sha256": judges.digest(refs), "reference_id": step["reference_id"],
               "reference_source_path": step.get("source_path"), "reference_source_url": step.get("source_url"),
               "reference_status": step.get("reference_status"), "step_config_sha256": scoring.digest(config),
               "trial_id": t.get("trial_id") if t else None, "trial_source": str(OUT / "trials" / (t["trial_id"] + ".json")) if t else None,
               "judge_config_sha256": t.get("pipeline_config_sha256") if t else None,
               "status": t.get("status") if t else "not_run", "technical_pipeline_complete": complete,
               "numeric_scope": "source_extracted_development_control_rerun", "formal_eligible": False,
               "upstream_cce_eligible": e.get("cce_eligible"), "official_scores": e.get("official_scores"),
               "official_scores_field_present": "official_scores" in e,
               "formal_scores": {k: None for k in ["sr", "sp", "Com", "Cor", "Eff", "IA", "HV"]},
               "formal_na_reasons": ["complete_applicable_reference_not_expert_confirmed", "controlled_edit_necessity_and_scope_pending_expert"],
               "upstream_integrity": e.get("integrity"),
               "upstream_status": {k: e.get(k) for k in ["technical_status", "scoring_status", "scientific_status"]},
               "failure_details": {k: e.get(k) for k in ["_error", "_error_type", "failure_stage"] if k in e},
               "raw_judgments": e.get("legacy_diagnostics", {}), "raw_teacher_content": e.get("teacher_generation", {}).get("content"),
               "extraction": extraction, "extraction_status": e.get("meta_data", {}).get("extraction_status"),
               "candidate_raw_and_derived": nums, "candidate_normalized_items": normalized(raw),
               "candidate_na_reasons": {k: step.get("step_missing_reason") if k in ["sr", "sp"] else "upstream_absent_or_dependency_missing" for k, v in nums.items() if v is None},
               "scientific_failure_flags": flags}
        if t and t["status"] != "success":
            provider_path = attempt / "provider_response.json"
            payload = None
            if provider_path.exists():
                response = scoring.read(provider_path).get("response", "")
                try:
                    payload = json.loads(response)
                except (ValueError, TypeError):
                    pass
            if isinstance(payload, dict):
                rec["raw_partial_payload"] = payload
                rec["partial_diagnostic_scope"] = "Observed fields only; no alias repair, trial repair, or complete-pipeline claim"
                for group, fields in payload.get("scores", {}).items():
                    if not isinstance(fields, dict):
                        continue
                    for key, item in fields.items():
                        if not isinstance(item, dict) or "score" not in item:
                            continue
                        value, maximum = item["score"], {"c_step": 2, **MAXIMA}.get(key)
                        recognized = maximum is not None
                        maximum = maximum if recognized else item.get("max_score")
                        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and isinstance(maximum, (int, float)) and maximum > 0 and (-maximum if key == "s_method" else 0) <= value <= maximum
                        partial.append({"case_id": c["case_id"], "trial_id": t["trial_id"], "field": key, "raw_value": value,
                                        "range_valid": valid, "contract_key_recognized": recognized,
                                        "normalized_value": ((value / maximum + 1) / 2 if key == "s_method" else value / maximum) if valid else None,
                                        "provider_response_path": str(provider_path), "provider_response_sha256": scoring.filehash(provider_path),
                                        "json_pointer": f"/response/scores/{group}/{key}/score", "reasoning": item.get("reasoning"),
                                        "partial_diagnostic_only": True, "formal_eligible": False, "not_substituted_into_trial": True})
        records.append(rec)
    by_id = {r["case_id"]: r for r in records}
    results = []
    for p in pairs:
        a, z = by_id[p["baseline_case_id"]], by_id[p["variant_case_id"]]
        same = all(a[k] == z[k] and a[k] is not None for k in ["judge_config_sha256", "step_config_sha256", "references_sha256", "question_sha256"])
        complete = same and a["technical_pipeline_complete"] and z["technical_pipeline_complete"]
        row = {**p, "technical_pipeline_complete": complete, "same_frozen_configuration": same,
               "scope": "same_existing_control_recomputed_with_supplement_v2_not_new_independent_pair",
               "judge_config_sha256": a["judge_config_sha256"], "step_config_sha256": a["step_config_sha256"], "references_sha256": a["references_sha256"]}
        for metric in METRICS:
            av, zv = a["candidate_raw_and_derived"].get(metric), z["candidate_raw_and_derived"].get(metric)
            row.update({"baseline_" + metric: av, "variant_" + metric: zv,
                        "delta_" + metric: zv - av if complete and av is not None and zv is not None else None})
        results.append(row)
    for name, value in [("per_case.json", records), ("paired_results.json", results), ("step_results.json", steps), ("partial_return_fields.json", partial)]:
        save(name, value)
    table("per_case.csv", [{k: r[k] for k in ["case_id", "source_case_id", "condition", "question_id", "status", "technical_pipeline_complete", "reference_id", "formal_eligible", "trial_id", "judge_config_sha256", "step_config_sha256"]} | r["candidate_raw_and_derived"] | {"norm_" + k: v for k, v in r["candidate_normalized_items"].items()} | r["scientific_failure_flags"] for r in records])
    table("paired_results.csv", results)
    if partial:
        table("partial_return_fields.csv", partial)
    save("scientific_failure_flags.json", [{"case_id": r["case_id"], **r["scientific_failure_flags"]} for r in records])
    condition_summary = []
    for condition in sorted({p["condition"] for p in results}):
        group = [p for p in results if p["condition"] == condition]
        row = {"condition": condition, "planned_pairs": len(group),
               "complete_pairs": sum(p["technical_pipeline_complete"] for p in group), "formal_eligible_pairs": 0}
        for metric in METRICS:
            deltas = [p["delta_" + metric] for p in group if p["delta_" + metric] is not None]
            row.update({"n_" + metric: len(deltas), "mean_delta_" + metric: sum(deltas) / len(deltas) if deltas else None,
                        "negative_" + metric: sum(v < -1e-12 for v in deltas),
                        "zero_" + metric: sum(abs(v) <= 1e-12 for v in deltas), "positive_" + metric: sum(v > 1e-12 for v in deltas)})
        condition_summary.append(row)
    save("control_summary.json", condition_summary)
    table("control_summary.csv", condition_summary)
    receipts = [scoring.read(p) for p in (OUT / "attempts").glob("*/request_receipt.json")]
    trial_ids = {t["trial_id"] for t in trials} | {r["trial_id"] for r in receipts}
    ledger = judges.ledger_rows(LEDGER)
    summary = {"planned_full_texts": 21, "actual_trial_count": len(trials), "source_answers": 3,
               "question_ids": [2, 21, 22], "task_families": 2, "source_families": 1, "controlled_pairs": 15,
               "same_batch_baselines_reused_for_granularity": 3, "cross_version_trial_reuse": 0,
               "technical_successful_cases": sum(r["technical_pipeline_complete"] for r in records),
               "technical_completed_pairs": sum(p["technical_pipeline_complete"] for p in results),
               "complete_candidate_cce_cases": sum(all(r["candidate_raw_and_derived"][k] is not None for k in ["Com", "Cor", "Eff"]) for r in records),
               "complete_candidate_cce_pairs": sum(p["technical_pipeline_complete"] and all(p.get(prefix + k) is not None for prefix in ["baseline_", "variant_"] for k in ["Com", "Cor", "Eff"]) for p in results),
               "confirmed_eligible_pairs": 0, "formal_completed_pairs": 0, "formal_eligible": False,
               "official_score_available_cases": sum(r["official_scores"] is not None for r in records),
               "condition_counts": dict(Counter(p["condition"] for p in results)),
               "explicit_route_mismatches": sum(r["scientific_failure_flags"]["explicit_route_mismatch"] for r in records),
               "rubric_example_copies": sum(r["scientific_failure_flags"]["extraction_exactly_copies_rubric_example"] for r in records),
               "new_requests_this_batch": sum(x.get("event") == "request_started" and x.get("trial_id") in trial_ids for x in ledger),
               "request_receipts_without_trial_result": sum(r["trial_id"] not in {t["trial_id"] for t in trials} for r in receipts),
               "output_budget_exhausted_count": sum(x["output_budget_exhausted"] for x in generation_checks),
               "package_requests_in_ledger": sum(x.get("event") == "request_started" for x in ledger),
               "scope": "Updated-reference recomputation of existing 15 control pairs, development only; old results untouched"}
    save("development_summary.json", summary)
    save("verification.json", {"all_passed": True, "source_and_frozen_file_hashes_verified": True,
                              "input_and_reference_trial_bindings_verified": True, "actual_prompt_hash_checks": runtime_checks,
                              "generation_checks": generation_checks, "observed_trial_count": len(trials),
                              "request_receipt_count": len(receipts), "all_planned_trials_present": len(trials) == 21,
                              "pair_configuration_checks": [{"pair_id": p["pair_id"], "same": p["same_frozen_configuration"]} for p in results],
                              "formal_eligible_pairs": 0})
    plan.update(status="computed_development" if summary["technical_successful_cases"] == 21 else "computed_development_with_failures",
                actual_new_requests=summary["new_requests_this_batch"], actual_technical_successful_cases=summary["technical_successful_cases"])
    save("plan.json", plan)
    commands(plan, executed=True)
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "analyze"])
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    args = parser.parse_args()
    prepare(args) if args.command == "prepare" else analyze(args)
