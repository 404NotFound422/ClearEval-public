"""Prepare/preflight/analyze one source-bound q2 alternative development pair.

This script never calls a generating model. The unchanged cce_judges.py runner
is the only execution entry; the coordinator controls its two-request budget.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_judges as judges
import cce_validation as core
import cce_alternative_development as helpers
import cce_extraction_dev_v2 as existing_runtime

BASE = ROOT / "artifacts/cce_validation"
OUT = BASE / "judges/local_alternative_q2_v1"
AUDIT = BASE / "controls/alternative_task_expansion_audit_v1"
SOURCE_REFS = BASE / "expanded_tasks_v4/references.json"
SOURCE_CONFIG = BASE / "judges/local_controls_supplement_v2/local_config_snapshot.json"
LEDGER = BASE / "judges/request_ledger.jsonl"
PY = ROOT.parent / "review_artifacts/bioprobench_2026-09-29/python_portable/python.exe"
MAXIMA = helpers.MAXIMA
METRICS = helpers.METRICS
PROVENANCE_FIELDS = {"source_spans", "source_span", "source_anchor", "source_pages", "evidence_manifest_path", "source_conflicts_path", "evidence_ids", "prerequisite_source_span"}
SCIENCE_FIELDS = ["reference_id", "route_id", "route_aliases", "question_ids", "continuous_conditions", "applicability", "unknown_parameters", "status", "human_confirmation", "formal_eligible", "source_scope", "completeness_status", "excluded_aliases"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(name, value):
    judges.save(OUT / name, value)


def binding(path):
    return {"path": str(path), "sha256": judges.filehash(path)}


def project_metadata(value):
    if isinstance(value, dict):
        return {k: project_metadata(v) for k, v in value.items() if k not in PROVENANCE_FIELDS}
    if isinstance(value, list):
        return [project_metadata(v) for v in value]
    return value


def project_references(full):
    payload = []
    checks = []
    for ref in full:
        projected = {k: project_metadata(ref[k]) for k in SCIENCE_FIELDS if k in ref}
        scopes = {s["required_scope"] for s in ref["steps"]}
        require(len(scopes) == 1, "Cannot deduplicate nonuniform required scopes")
        projected["step_default_required_scope"] = next(iter(scopes))
        projected["steps"] = [{k: project_metadata(v) for k, v in s.items() if k not in PROVENANCE_FIELDS | {"required_scope", "source_workflow_step_id"}} for s in ref["steps"]]
        projected["full_reference_sha256"] = judges.digest(ref)
        require([s["text"] for s in projected["steps"]] == [s["text"] for s in ref["steps"]], "Step text changed")
        require([s["step_id"] for s in projected["steps"]] == [s["step_id"] for s in ref["steps"]], "Step IDs changed")
        for original, retained in zip(ref["steps"], projected["steps"]):
            for key in set(original) - PROVENANCE_FIELDS - {"required_scope", "source_workflow_step_id"}:
                require(retained[key] == project_metadata(original[key]), "Scientific step value changed")
        checks.append({"reference_id": ref["reference_id"], "full_reference_sha256": judges.digest(ref), "source_path": ref["source_path"], "source_sha256": ref["source_sha256"], "steps": len(ref["steps"]), "all_step_text_ID_order_equal": True, "all_non_provenance_step_fields_equal_except_deduplicated_scope": True, "all_scientific_conditions_and_unknowns_preserved": True, "scope_deduplicated_without_rewording": True})
        payload.append(projected)
    return payload, checks


def runner_args(command):
    return types.SimpleNamespace(command=command, cases=OUT / "cases.json", out=OUT,
        model_config=OUT / "local_config_snapshot.json", models=["local_qwen3_8b"],
        question_file=judges.HIST, demand_file=ROOT / "dataset/Q+AR/src/demand_vectors_all.json", demand_manifest=None,
        ledger=LEDGER, total_budget=300, external_request_count=0, max_calls=2, max_attempts=1, repeats=1,
        temperature=0.0, max_output_tokens=8192, timeout_seconds=600, allow_api=False)


def command_arguments(command):
    args = ["scripts/cce_judges.py", command, "--cases", str(OUT / "cases.json"), "--out", str(OUT),
        "--model-config", str(OUT / "local_config_snapshot.json"), "--models", "local_qwen3_8b", "--repeats", "1",
        "--temperature", "0", "--max-output-tokens", "8192", "--max-attempts", "1", "--max-calls", "2",
        "--timeout-seconds", "600", "--ledger", str(LEDGER), "--total-budget", "300"]
    if command == "run":
        args.append("--allow-api")
    return args


def shell_command(args):
    return "& '" + str(PY) + "' " + " ".join("'" + str(a).replace("'", "''") + "'" for a in args)


def validate_frozen():
    plan = judges.read(OUT / "plan.json")
    for item in plan["frozen_files"]:
        require(judges.filehash(item["path"]) == item["sha256"], "Frozen file drift: " + item["path"])
    cases = judges.read(OUT / "cases.json")["cases"]
    full = judges.read(OUT / "references_full.json")["references"]
    payload = judges.read(OUT / "reference_context.json")
    expected, _ = project_references(full)
    require(payload == expected and all(c["references"] == payload for c in cases), "Reference context projection drift")
    for case in cases:
        require(core.digest(case["model_response"]) == case["answer_sha256"], "Answer edited")
        require(core.digest(case["specific_question"]) == case["question_sha256"], "Question edited")
    return plan, cases, full, payload


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "plan.json").exists():
        plan, _, _, _ = validate_frozen()
        print(judges.canonical({"status": "reused_unchanged_preparation", "planned_new_requests": 2, "snapshot_id": plan["snapshot_id"], "new_model_requests": 0}))
        return
    require(not any((OUT / "trials").glob("*.json")), "Existing trials prevent preparation")
    selected = next(x for x in judges.read(AUDIT / "candidate_pairs.json") if x["question_id"] == 2)
    require([x["model"] for x in selected["answers"]] == ["gemini-3-flash", "openai_claude-sonnet-4.6"], "Fixed first-model selection changed")
    require(selected["routes"] == ["FDISCO", "iDISCO+"], "Route selection changed")
    require(judges.read(AUDIT / "verification.json")["status"] == "pass", "Candidate audit failed")
    full = [r for r in judges.read(SOURCE_REFS)["references"] if 2 in r["question_ids"] and r["route_id"] in selected["routes"]]
    require(len(full) == 2, "Expected two complete conditional q2 branches")
    for ref in full:
        require(judges.filehash(ref["source_path"]) == ref["source_sha256"], "Source bytes changed")
    payload, equivalence = project_references(full)
    runner, registry, frozen_contract, settings = existing_runtime.frozen_runtime()
    require(settings["max_output_tokens"] == 8192 and settings["num_ctx"] == 40960 and settings["temperature"] == 0, "Frozen Qwen settings changed")
    local = judges.read(SOURCE_CONFIG)
    qwen = next(x for x in local["models"] if x["name"] == "local_qwen3_8b")
    cases, contexts, evidence = [], [], []
    for item, route in zip(selected["answers"], selected["routes"]):
        archive = Path(item["answer_source"])
        source = item["answer_object"]
        with archive.open("rb") as handle:
            handle.seek(source["object_byte_start_inclusive"])
            raw = handle.read(source["object_byte_end_exclusive"] - source["object_byte_start_inclusive"])
        require(hashlib.sha256(raw).hexdigest() == source["object_bytes_sha256"], "Selected raw object changed")
        answer = json.loads(raw)
        require(int(answer["question_id"]) == 2, "Only q2 is authorized in this pair")
        require(core.digest(answer["model_response"]) == item["answer_sha256"] and core.digest(answer["specific_question"]) == item["question_sha256"], "Source identity mismatch")
        registry.get(2, answer["specific_question"])
        case = {"case_id": item["answer_id"] + "__alternative_q2_v1", "source_case_id": item["answer_id"], "base_id": item["answer_id"],
            "question_id": 2, "specific_question": answer["specific_question"], "model_response": answer["model_response"],
            "generator_model": item["model"], "declared_route": route, "answer_source": str(archive),
            "answer_sha256": item["answer_sha256"], "question_sha256": item["question_sha256"], "references": payload,
            "condition": "alternative_route_development_natural_answer", "formal_eligible": False, "expert_confirmation": None,
            "scope": "new_q2_descriptive_pair_conditional_sources_pending_scientific_applicability"}
        prompt = helpers.exact_runner_prompt(case)
        full_prompt = helpers.exact_runner_prompt({**case, "references": full})
        bound = len(prompt.encode("utf-8")) + settings["max_output_tokens"] + 256
        contexts.append({"case_id": case["case_id"], "exact_prompt_sha256": core.digest(prompt), "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            "max_output_tokens": 8192, "template_reserve": 256, "conservative_context_bound": bound, "configured_num_ctx": 40960,
            "fits": bound <= 40960, "unprojected_full_reference_bound": len(full_prompt.encode("utf-8")) + 8192 + 256,
            "capture": "actual unchanged runner prompt intercepted before transport plus exact supplied evidence suffix", "model_requests": 0})
        evidence.append({**item, "case_id": case["case_id"], "whole_answer_unchanged": True, "historical_scores_reused_as_new_extraction": False})
        cases.append(case)
    require(all(x["fits"] for x in contexts), "Conservative context bound exceeded; no generation permitted")
    require(cases[0]["specific_question"] == cases[1]["specific_question"] and cases[0]["references"] == cases[1]["references"], "Pair question/reference mismatch")
    pair = {"pair_id": "q2__FDISCO_vs_iDISCOplus__development_v1", "question_id": 2,
        "baseline_case_id": cases[0]["case_id"], "alternative_case_id": cases[1]["case_id"], "routes": selected["routes"],
        "source_pair_id": selected["pair_id"], "formal_eligible": False, "reasonable_alternative_confirmed": False,
        "causal_scope": "Two archived natural answers from different generators; descriptive comparison, not isolated route causality."}
    save("cases.json", {"cases": cases})
    save("pairs.json", [pair])
    save("references_full.json", {"references": full})
    save("reference_context.json", payload)
    save("local_config_snapshot.json", {"models": [qwen]})
    save("frozen_judge_contract.json", frozen_contract)
    save("source_answer_provenance.json", evidence)
    save("reference_projection_verification.json", {"status": "pass", "checks": equivalence,
        "full_reference_file": binding(OUT / "references_full.json"), "projected_reference_file": binding(OUT / "reference_context.json"),
        "rule": "Keep every step text/ID/order and non-provenance scientific value, all continuous conditions, applicability clauses and unknowns. Move source byte/page anchors and file metadata to the complete frozen references. Store identical per-step required_scope once per reference without rewriting. Source-workflow cross-reference IDs remain in full references.",
        "prompt_reference_is_metadata_projection": True, "not_a_new_scientific_reference": True, "full_payload_equal_for_both_cases": True,
        "removed_provenance_key_names": sorted(PROVENANCE_FIELDS), "model_requests": 0})
    save("offline_context_preflight.json", {"status": "pass", "checks": contexts, "all_fit": True, "model_requests": 0})
    frozen_files = [OUT / x for x in ["cases.json", "pairs.json", "references_full.json", "reference_context.json", "local_config_snapshot.json", "frozen_judge_contract.json", "source_answer_provenance.json", "reference_projection_verification.json", "offline_context_preflight.json"]]
    frozen_files += [SOURCE_REFS, SOURCE_CONFIG, AUDIT / "candidate_pairs.json", AUDIT / "verification.json", Path(__file__), ROOT / "scripts/cce_judges.py", ROOT / "scripts/cce_validation.py", ROOT / "scripts/cce_alternative_development.py"]
    before = sum(x.get("event") == "request_started" for x in judges.ledger_rows(LEDGER))
    plan = {"status": "prepared_not_run", "question_ids": [2], "source_answers": 2, "candidate_pairs": 1,
        "new_distinct_question_beyond_old_alternative_batch": True, "source_families": 2, "same_full_reference_set_for_both": True,
        "same_projected_reference_payload_for_both": True, "judge": "local_qwen3_8b", "repeat_index": 0, "repeats": 1,
        "temperature": 0, "max_output_tokens": 8192, "num_ctx": 40960, "max_attempts": 1, "max_calls": 2, "timeout_seconds": 600,
        "planned_new_requests": 2, "new_requests_at_preparation": 0, "historical_trial_reuse": 0, "package_total_budget": 300,
        "package_request_count_at_preparation": before, "expected_package_count_if_both_attempts_made": before + 2,
        "step_threshold": 0.7, "frozen_contract_sha256": judges.digest(frozen_contract),
        "frozen_files": [binding(p) for p in frozen_files], "formal_eligible": False, "expert_confirmations": 0,
        "scientific_dependencies": ["iDISCO+ requires appropriately immunolabeled starting material; q2 only establishes fixation", "Task-specific labels, morphology and route reasonableness await separate assessment", "Source-extracted operation coverage is not expert-confirmed scientific necessity"],
        "snapshot_id": judges.digest({"cases": cases, "pairs": [pair], "full_references": full, "contract": frozen_contract})}
    save("plan.json", plan)
    command_log = {"actually_executed": [{"stage": "prepare", "argv": [str(Path(__file__)), "prepare"], "model_requests": 0}],
        "planned_not_executed": {"preflight": [str(Path(__file__)), "preflight"], "run": command_arguments("run"), "analyze": [str(Path(__file__)), "analyze"]},
        "python": str(PY), "working_directory": str(ROOT), "budget_owner": "root coordinator", "new_requests": 0}
    save("execution_commands.json", command_log)
    commands = [shell_command(["scripts/cce_alternative_q2_development.py", "prepare"]), shell_command(["scripts/cce_alternative_q2_development.py", "preflight"]), shell_command(command_arguments("run")), shell_command(["scripts/cce_alternative_q2_development.py", "analyze"])]
    (OUT / "EXECUTION.md").write_text("# q2 development pair execution\n\nPrepare/preflight are non-generating checks. Run/analyze remain planned until their actual receipts exist. The coordinator owns the maximum two new requests. The runner's legacy `--allow-api` switch enables the frozen loopback transport; no external API is configured.\n\n```powershell\n" + "\n".join(commands) + "\n```\n\nBoth complete original answers use the same projected reference evidence and frozen Qwen settings. Full references remain separately bound by raw file hash. No historical score is substituted for fresh extraction.\n", encoding="utf-8")
    (OUT / "README.md").write_text("# q2 条件性替代路线开发配对\n\n固定 Gemini Flash/FDISCO 与 Claude Sonnet/iDISCO+ 两份原答案，新增一个不同题号。当前只完成准备；未完成任何新增评价。完整步骤文本、适用前提、持续条件及 unknowns 全部保留，重复来源定位元数据从共同提示移到单独冻结原参考；不得把此投影视为新的生物学方案。\n\nQwen 设置与 v2 主评相同：temperature 0、输出 8192、num_ctx 40960、repeat 0、每份最多一次、超时 600 秒。原始富元数据提示超出保守界，显式无损投影后两份均满足；没有截断全文、扩大上下文或降低输出预算。\n\n来源/标记适用性、专家确认及正式合理替代资格仍为 pending。不同生成模型的自然答案比较不是纯路线因果效应。当前新增请求为 0，计划最多 2 次，由根代理统一执行。\n\n参见 [计划](plan.json)、[原始参考](references_full.json)、[共同提示参考](reference_context.json)、[投影核验](reference_projection_verification.json)、[原文来源](source_answer_provenance.json)、[静态上下文](offline_context_preflight.json)、[实际/待执行命令状态](execution_commands.json)和[命令](EXECUTION.md)。\n", encoding="utf-8")
    validate_frozen()
    print(judges.canonical({"status": "prepared_not_run", "cases": 2, "candidate_pairs": 1, "context_bounds": [x["conservative_context_bound"] for x in contexts], "planned_new_requests": 2, "package_requests": before, "new_requests": 0}))


def preflight():
    plan, _, _, _ = validate_frozen()
    _, _, _, _, cases, contract = judges.preflight(runner_args("preflight"))
    require(contract == judges.read(OUT / "frozen_judge_contract.json"), "Live service or frozen judge contract drift")
    require(judges.digest(contract) == plan["frozen_contract_sha256"] and len(cases) == 2, "Preflight matrix drift")
    log = judges.read(OUT / "execution_commands.json")
    log["actually_executed"].append({"stage": "preflight", "argv": [str(Path(__file__)), "preflight"], "model_requests": 0, "live_loopback_identity_verified": True, "contract_sha256": judges.digest(contract)})
    log["planned_not_executed"].pop("preflight", None)
    save("execution_commands.json", log)
    save("preflight_verification.json", {"status": "pass", "cases": 2, "same_frozen_contract": True, "all_static_context_bounds_fit": True, "model_requests": 0, "live_read_only_service_checks": ["/api/tags", "/api/version"], "contract_sha256": judges.digest(contract), "generation_executed": False})


def analyze():
    plan, cases, full, payload = validate_frozen()
    trials = [judges.read(p) for p in sorted((OUT / "trials").glob("*.json"))]
    require(trials, "No actual trial exists; do not report preparation as completed evaluation")
    require(len(trials) <= 2, "Unexpected extra trials")
    indexed = {t["case_id"]: t for t in trials}
    require(len(indexed) == len(trials) and set(indexed) <= {c["case_id"] for c in cases}, "Trial case identity mismatch")
    helpers.OUT = OUT  # Scope helper embedding writes to this new batch only.
    encoder = helpers.ScopedEncoder()
    step_config = {"encoder": encoder.identity, "threshold": 0.7, "adapter_sha256": core.filehash(ROOT / "scripts/cce_validation.py"), "full_reference_sha256": judges.digest(full), "prompt_reference_sha256": judges.digest(payload)}
    example = helpers.rubric_example()
    records, step_rows = [], []
    for case in cases:
        trial = indexed.get(case["case_id"])
        expected_input = judges.digest({"question": case["specific_question"], "question_id": 2, "protocol": case["model_response"], "references": payload})
        if trial:
            require(trial["judge"] == "local_qwen3_8b" and trial["repeat_index"] == 0 and trial["attempt"] == 1, "Unexpected model/repeat/attempt")
            require(trial["full_text_input_sha256"] == expected_input and trial["references_sha256"] == judges.digest(payload), "Trial text/reference drift")
            require(trial["identity"]["contract_sha256"] == plan["frozen_contract_sha256"], "Trial judge contract drift")
            require(judges.digest(trial["identity"]) == trial["trial_id"], "Trial ID not derived from exact identity")
        step = core.score_steps(case, full, encoder, 0.7)
        step_rows.append({"case_id": case["case_id"], "answer_sha256": case["answer_sha256"], "step_config_sha256": judges.digest(step_config), "step_result": step})
        raw = trial.get("preserved_numeric_proposals", {}) if trial else {}
        numbers = {k: raw.get(k) for k in list(MAXIMA) + ["Cor", "Eff"]}
        numbers.update({"sr": step["sr"], "sp": step["sp"], "Com": .4 * step["sr"] + .6 * numbers["c_param"] / 3 if step["sr"] is not None and numbers["c_param"] is not None else None})
        dims = [numbers["Com"], numbers["Cor"], numbers["Eff"]]
        numbers.update({"IA": min(dims) if all(x is not None for x in dims) else None, "HV": math.prod(dims) if all(x is not None for x in dims) else None})
        evaluation = trial.get("evaluation", {}) if trial else {}
        extraction = evaluation.get("extraction")
        extracted_route = extraction.get("method_name") if isinstance(extraction, dict) else None
        aliases = next(r["route_aliases"] for r in full if r["route_id"] == case["declared_route"])
        normalize = lambda v: str(v).lower().replace("-", "").replace(" ", "")
        flags = {"extraction_missing": not isinstance(extraction, dict), "explicit_route_mismatch": bool(extracted_route and normalize(extracted_route) not in {normalize(a) for a in aliases}), "rubric_example_copy": extraction == example}
        complete = bool(trial and trial["status"] == "success" and trial.get("actual_api_request_made") and trial.get("new_extraction_available"))
        records.append({"case_id": case["case_id"], "question_id": 2, "generator_model": case["generator_model"], "declared_route": case["declared_route"], "answer_sha256": case["answer_sha256"], "question_sha256": case["question_sha256"], "reference_id": step["reference_id"], "full_reference_sha256": judges.digest(full), "prompt_reference_sha256": judges.digest(payload), "step_config_sha256": judges.digest(step_config), "trial_id": trial.get("trial_id") if trial else None, "judge_contract_sha256": trial["identity"]["contract_sha256"] if trial else None, "status": trial["status"] if trial else "not_run", "technical_pipeline_complete": complete, "candidate_numeric_proposals_and_derived": numbers, "extraction": extraction, "scientific_failure_flags": flags, "scientific_validity": "pending_expert_and_applicability" if not any(flags.values()) else "evaluator_failure_flagged", "formal_eligible": False, "upstream_cce_eligible": evaluation.get("cce_eligible"), "official_scores": evaluation.get("official_scores"), "formal_scores": {k: None for k in ["Com", "Cor", "Eff", "IA", "HV"]}, "NA_reasons": {k: "not_run" if trial is None else "upstream_missing_or_evaluator_failure; inspect original trial" for k, v in numbers.items() if v is None}, "raw_trial_path": str(OUT / "trials" / (trial["trial_id"] + ".json")) if trial else None})
    left, right = records
    same = all(left[k] == right[k] and left[k] is not None for k in ["question_sha256", "judge_contract_sha256", "step_config_sha256", "prompt_reference_sha256", "full_reference_sha256"])
    complete = same and all(r["technical_pipeline_complete"] for r in records)
    pair = {**judges.read(OUT / "pairs.json")[0], "same_frozen_configuration": same, "technical_pipeline_complete": complete, "formal_completed": False, "metrics": {}}
    for metric in METRICS:
        a, b = [r["candidate_numeric_proposals_and_derived"][metric] for r in records]
        pair["metrics"][metric] = {"baseline": a, "alternative": b, "delta": b - a if complete and a is not None and b is not None else None}
    ledger = judges.ledger_rows(LEDGER)
    ids = {t["trial_id"] for t in trials}
    receipts = [judges.read(p) for p in (OUT / "attempts").glob("*/request_receipt.json")]
    ids |= {r["trial_id"] for r in receipts}
    count = sum(x.get("event") == "request_started" and x.get("trial_id") in ids for x in ledger)
    require(count <= 2, "Two-request budget exceeded")
    summary = {"status": "actual_development_results", "question_ids": [2], "source_answers": 2, "candidate_pairs": 1, "technical_successful_cases": sum(r["technical_pipeline_complete"] for r in records), "technical_completed_candidate_pairs": int(complete), "complete_candidate_cce_pairs": int(complete and all(r["candidate_numeric_proposals_and_derived"][k] is not None for r in records for k in ["Com", "Cor", "Eff"])), "scientific_failure_flagged_cases": sum(any(r["scientific_failure_flags"].values()) for r in records), "new_requests_this_batch": count, "package_requests_in_ledger": sum(x.get("event") == "request_started" for x in ledger), "formal_completed_pairs": 0, "expert_confirmation": 0, "reasonable_alternative_confirmed": False, "source_scope": "conditional source coverage; different natural answers/generators; no causal route or expert-validity claim"}
    for name, value in [("step_config.json", step_config), ("step_results.json", step_rows), ("per_case.json", records), ("paired_results.json", [pair]), ("development_summary.json", summary)]:
        save(name, value)
    log = judges.read(OUT / "execution_commands.json")
    log["actually_executed"].append({"stage": "analyze", "argv": [str(Path(__file__)), "analyze"], "model_requests": 0})
    log["planned_not_executed"].pop("analyze", None)
    log["actual_request_receipt_count"] = count
    log["actual_trial_paths"] = [str(OUT / "trials" / (t["trial_id"] + ".json")) for t in trials]
    save("execution_commands.json", log)
    print(judges.canonical(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "preflight", "analyze"])
    args = parser.parse_args()
    {"prepare": prepare, "preflight": preflight, "analyze": analyze}[args.command]()
