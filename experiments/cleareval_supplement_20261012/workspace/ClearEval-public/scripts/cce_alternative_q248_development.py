"""Source-guided q248 development pair; prepare/preflight/analyze only.

Generation is exclusively through the unchanged cce_judges.py entry, under the
coordinator's two-request budget. This is not a second archived natural answer.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import math
import re
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import cce_judges as judges
import cce_validation as core
import cce_alternative_q2_development as q2
import cce_alternative_development as helpers

BASE = ROOT / "artifacts/cce_validation"
OUT = BASE / "judges/local_alternative_q248_v1"
CONSTRUCTION = BASE / "controls/source_guided_q248_v1"
AUDIT = BASE / "controls/alternative_task_expansion_audit_v1"
REFS = BASE / "reference_recovery/supplement_bound/question_248_references.json"
CONFIG = BASE / "judges/local_controls_supplement_v2/local_config_snapshot.json"
LEDGER = BASE / "judges/request_ledger.jsonl"
PY = q2.PY

# Deterministic format adaptation of the eight already frozen source operations.
# No parameter was estimated from the task or from any generated answer.
OPERATIONS = [
    ("1 Decolorization", "1.1", "Incubation with 25% (wt/vol) Quadrol, with shaking at approximately 100 rpm; refresh the medium daily. (Temperature: 37 ℃, Time: 2 days)", {"Quadrol_wt_vol_percent": 25, "temperature_C": 37, "shaking_rpm_approx": 100, "time_days": 2, "refresh": "daily"}),
    ("2 Delipidation", "2.1", "Incubation with 30% (vol/vol) tert-butanol containing 3% (wt/vol) Quadrol, with shaking at approximately 100 rpm. (Temperature: 37 ℃, Time: 4 hours)", {"tert_butanol_vol_vol_percent": 30, "Quadrol_wt_vol_percent": 3, "temperature_C": 37, "shaking_rpm_approx": 100, "time_hours": 4}),
    (None, "2.2", "Incubation with 50% (vol/vol) tert-butanol containing 3% (wt/vol) Quadrol, with shaking at approximately 100 rpm. (Temperature: 37 ℃, Time: 6 hours)", {"tert_butanol_vol_vol_percent": 50, "Quadrol_wt_vol_percent": 3, "temperature_C": 37, "shaking_rpm_approx": 100, "time_hours": 6}),
    (None, "2.3", "Incubation with 70% (vol/vol) tert-butanol containing 3% (wt/vol) Quadrol, with shaking at approximately 100 rpm. (Temperature: 37 ℃, Time: 24 hours)", {"tert_butanol_vol_vol_percent": 70, "Quadrol_wt_vol_percent": 3, "temperature_C": 37, "shaking_rpm_approx": 100, "time_hours": 24}),
    ("3 Dehydration", "3.1", "Incubation with tB-PEG dehydration solution, with shaking at approximately 100 rpm; refresh the medium daily. (Temperature: 37 ℃, Time: 2 days)", {"medium": "tB-PEG dehydration solution", "temperature_C": 37, "shaking_rpm_approx": 100, "time_days": 2, "refresh": "daily"}),
    ("4 RI Matching and Clearing", "4.1", "Brief rinsing with BB-PEG clearing medium before clearing. (Temperature: not specified in the selected source step, Time: brief; no numeric duration specified)", {"medium": "BB-PEG", "temperature_C": None, "time_hours": None, "duration_qualifier": "brief"}),
    (None, "4.2", "Incubation with BB-PEG clearing medium, with shaking at approximately 100 rpm, until transparent. (Temperature: 37 ℃, Time: 1 day recommended for adult brain)", {"medium": "BB-PEG", "temperature_C": 37, "shaking_rpm_approx": 100, "time_days_recommended": 1, "endpoint": "until transparent"}),
    ("5 Preservation", "5.1", "Storage in the clearing medium, covered with aluminum foil. (Temperature: RT, Time: no fixed storage duration specified)", {"medium": "clearing medium", "light_protection": "aluminum foil", "temperature": "room temperature", "time_hours": None}),
]


def require(ok, message):
    if not ok: raise ValueError(message)


def save(name, obj): judges.save(OUT / name, obj)
def bind(path): return {"path": str(path), "sha256": judges.filehash(path)}


def runner_args(command):
    return types.SimpleNamespace(command=command, cases=OUT / "cases.json", out=OUT, model_config=OUT / "local_config_snapshot.json", models=["local_qwen3_8b"], question_file=judges.HIST, demand_file=ROOT / "dataset/Q+AR/src/demand_vectors_all.json", demand_manifest=None, ledger=LEDGER, total_budget=300, external_request_count=0, max_calls=2, max_attempts=1, repeats=1, temperature=0.0, max_output_tokens=8192, timeout_seconds=600, allow_api=False)


def runner_argv(command):
    argv = ["scripts/cce_judges.py", command, "--cases", str(OUT / "cases.json"), "--out", str(OUT), "--model-config", str(OUT / "local_config_snapshot.json"), "--models", "local_qwen3_8b", "--repeats", "1", "--temperature", "0", "--max-output-tokens", "8192", "--max-attempts", "1", "--max-calls", "2", "--timeout-seconds", "600", "--ledger", str(LEDGER), "--total-budget", "300"]
    return argv + (["--allow-api"] if command == "run" else [])


def validate():
    plan = judges.read(OUT / "plan.json")
    for item in plan["frozen_files"]:
        require(judges.filehash(item["path"]) == item["sha256"], "Frozen drift: " + item["path"])
    cases = judges.read(OUT / "cases.json")["cases"]
    full = judges.read(OUT / "references_full.json")["references"]
    payload = judges.read(OUT / "reference_context.json")
    expected, _ = q2.project_references(full)
    require(payload == expected and all(c["references"] == payload for c in cases), "Reference projection drift")
    for c in cases:
        require(core.digest(c["model_response"]) == c["answer_sha256"] and core.digest(c["specific_question"]) == c["question_sha256"], "Full text changed")
    return plan, cases, full, payload


def prepare():
    OUT.mkdir(parents=True, exist_ok=True); CONSTRUCTION.mkdir(parents=True, exist_ok=True)
    if (OUT / "plan.json").exists():
        plan, _, _, _ = validate(); print(judges.canonical({"status": "reused_unchanged_preparation", "snapshot_id": plan["snapshot_id"], "new_model_requests": 0})); return
    require(not list((OUT / "trials").glob("*.json")), "Cannot reprepare existing trials")
    matrix = judges.read(AUDIT / "route_answer_matrix.json")
    candidates = sorted([r for r in matrix if r["question_id"] == 248 and r.get("route") == "FDISCO"], key=lambda x: x["model_rank"])
    first = candidates[0]
    require(first["model"] == "gemini-3-flash" and first["model_rank"] == 1 and first["selected_for_route"], "Fixed cohort first route representative changed")
    protected = {int(r["question_id"]) for r in judges.read(BASE / "human_review/selection.json")["selection"] if r["split"] == "audit_holdout"}
    require(248 not in protected, "Protected question")
    archive = Path(first["answer_source"]); span = first["answer_object"]
    with archive.open("rb") as f:
        f.seek(span["object_byte_start_inclusive"]); raw = f.read(span["object_byte_end_exclusive"] - span["object_byte_start_inclusive"])
    require(hashlib.sha256(raw).hexdigest() == span["object_bytes_sha256"], "Archive object drift")
    answer = json.loads(raw); original = answer["model_response"]; question = answer["specific_question"]
    require(int(answer["question_id"]) == 248 and core.digest(original) == first["answer_sha256"] and core.digest(question) == first["question_sha256"], "Original identity mismatch")
    label_line = next(line for line in original.splitlines() if line.startswith("**Chosen Labeling:**"))
    require(label_line == "**Chosen Labeling:** [tdTomato, β-III Tubulin (TUJ1) + Alexa Fluor 647]", "Original label selection changed")
    full = judges.read(REFS)["references"]
    require({r["route_id"] for r in full} == {"FDISCO", "PEGASOS"}, "Expected fixed whole-brain route pair")
    peg = next(r for r in full if r["route_id"] == "PEGASOS")
    require(len(peg["steps"]) == 8 and peg["reference_id"] == "PEGASOS_SUPPLEMENT_V2_WHOLE_BRAIN", "Expected eight-step v2 whole-brain reference")
    for r in full:
        require(248 in r["question_ids"] and judges.filehash(r["source_path"]) == r["source_sha256"], "Source binding drift")
    header = "**Chosen Method:** PEGASOS\n" + label_line + "\n**Justification:** Conditional PEGASOS clearing, RI matching and preservation for the fixed adult whole mouse brain, retaining the requested native tdTomato and selected TUJ1-Alexa Fluor 647 targets.\n**Applicability:** Native tdTomato retention and TUJ1-Alexa Fluor 647 compatibility require confirmation. The question establishes fixation but does not establish completed TUJ1 labeling; upstream labeling preparation is outside this downstream sequence.\n\n**Protocol Steps:**\n"
    pieces = [header]; mappings = []
    for i, (heading, number, text, facts) in enumerate(OPERATIONS):
        if heading: pieces.append(heading + "\n")
        start = sum(len(x) for x in pieces)
        line = number + " " + text
        pieces.append(line + ("\n" if i < 7 else ""))
        mappings.append({"source_reference_id": peg["reference_id"], "source_step_id": peg["steps"][i]["step_id"], "source_step_index": i, "source_text": peg["steps"][i]["text"], "source_text_sha256": core.digest(peg["steps"][i]["text"]), "source_anchor": peg["steps"][i]["source_anchor"], "new_number": number, "new_line": line, "new_start": start, "new_end": start + len(line), "new_line_sha256": core.digest(line), "source_derived_parameter_facts": facts, "adaptation": "Operation-level paraphrase in the original answer's numbered Temperature/Time format; no parameter interpolation or added operation."})
    variant = "".join(pieces)
    for m in mappings: require(variant[m["new_start"]:m["new_end"]] == m["new_line"], "Mapping offset wrong")
    require(label_line in variant and "anti-tdTomato" not in variant and "Indefinite" not in variant, "Native label or unsupported duration changed")
    parsed = core.segment(variant)
    require(len(parsed) == 8, "Format adapter did not yield exactly eight operations")
    require(all(m["new_line"].split(" ", 1)[1] == parsed[i]["text"] for i, m in enumerate(mappings)), "Parsed operation differs from constructed text")
    require(all(m["new_line"].split(" ", 1)[1] != m["source_text"] for m in mappings), "Verbatim reference-step copying")
    char_edits = [{"tag": tag, "old_start": a, "old_end": b, "new_start": c, "new_end": d, "old_text": original[a:b], "new_text": variant[c:d]} for tag, a, b, c, d in difflib.SequenceMatcher(None, original, variant, autojunk=False).get_opcodes()]
    require("".join(x["old_text"] for x in char_edits) == original and "".join(x["new_text"] for x in char_edits) == variant, "Edit roundtrip failed")
    payload, projection = q2.project_references(full)
    runner, registry, contract, settings = q2.existing_runtime.frozen_runtime()
    registry.get(248, question)
    local_model = next(m for m in judges.read(CONFIG)["models"] if m["name"] == "local_qwen3_8b")
    require(settings["max_output_tokens"] == 8192 and settings["num_ctx"] == 40960 and settings["temperature"] == 0, "Frozen settings drift")
    texts = [("baseline", original, "FDISCO", "archived_baseline"), ("source_guided_PEGASOS", variant, "PEGASOS", "deterministic_source_guided_edit")]
    cases = []
    for suffix, text, route, origin in texts:
        cases.append({"case_id": first["answer_id"] + "__q248_route_" + suffix + "_v1", "source_case_id": first["answer_id"], "base_id": first["answer_id"], "question_id": 248, "specific_question": question, "model_response": text, "generator_model": first["model"] if origin == "archived_baseline" else "source_guided_edit_of_" + first["model"], "original_generator_model": first["model"], "answer_origin": origin, "source_guided": origin != "archived_baseline", "declared_route": route, "answer_source": str(archive) if origin == "archived_baseline" else str(CONSTRUCTION / "variant.txt"), "answer_sha256": core.digest(text), "question_sha256": core.digest(question), "references": payload, "condition": "baseline" if origin == "archived_baseline" else "source_guided_conditional_alternative_route", "scope": "development_only_not_confirmed_reasonable_alternative", "formal_eligible": False, "expert_confirmation": None})
    contexts = []
    for c in cases:
        prompt = helpers.exact_runner_prompt(c); bound = len(prompt.encode("utf-8")) + 8192 + 256
        require(bound <= 40960, "Prompt exceeds frozen context; do not run")
        contexts.append({"case_id": c["case_id"], "prompt_raw_sha256": core.digest(prompt), "prompt_utf8_bytes": len(prompt.encode("utf-8")), "max_output_tokens": 8192, "template_reserve": 256, "conservative_context_bound": bound, "configured_num_ctx": 40960, "fits": True, "model_requests": 0})
    pair = {"pair_id": "q248__FDISCO_vs_source_guided_PEGASOS__development_v1", "question_id": 248, "baseline_case_id": cases[0]["case_id"], "alternative_case_id": cases[1]["case_id"], "routes": ["FDISCO", "PEGASOS"], "source_guided": True, "formal_eligible": False, "reasonable_alternative_confirmed": False, "causal_scope": "A deterministic source-guided route replacement of one archived answer changes multiple scientific choices; not an independently generated natural alternative or isolated route effect."}
    construction = {"status": "structural_source_mapping_pass_scientific_applicability_pending", "source_guided": True, "source_answers": 1, "baseline": first, "question_sha256": core.digest(question), "baseline_sha256": core.digest(original), "variant_sha256": core.digest(variant), "label_line_preserved_verbatim": label_line, "native_tdTomato_not_replaced_with_antibody": True, "initial_labeling_completion": "not_established_by_question_pending", "step_count": 8, "source_step_mapping": mappings, "character_diff_all_segments": char_edits, "edit_roundtrip": "pass", "original_baseline_unchanged": True, "source_reference_file": bind(REFS), "construction_script": bind(Path(__file__)), "unknowns_preserved": ["Brief rinse has no numeric duration or explicit temperature in the selected operation", "Storage duration is not fixed and is not declared indefinite", "Task-specific native tdTomato plus TUJ1-Alexa Fluor 647 and completed upstream labeling remain unconfirmed"], "scientific_changes": ["FDISCO dehydration/DBE route replaced with the complete eight-operation source-bound PEGASOS branch", "Route-specific justification replaced; original chosen labeling line retained", "Unsupported baseline indefinite storage and additional imaging-chamber duration are not carried into the source-derived branch"], "construction_validation_scope": "No new scientific compatibility, parameter correctness or biological necessity is certified.", "reference_coupling_warning": "The variant was built from the very source used for SR/SP. Any high similarity reflects source-guided construction, not independent evidence of a scientifically successful alternative.", "new_model_requests": 0, "new_expert_labels": 0}
    judges.save(CONSTRUCTION / "construction.json", construction)
    (CONSTRUCTION / "baseline.txt").write_text(original, encoding="utf-8", newline="\n")
    (CONSTRUCTION / "variant.txt").write_text(variant, encoding="utf-8", newline="\n")
    judges.save(CONSTRUCTION / "validation.json", {"status": "pass_structure_and_source_mapping_only", "baseline_raw_sha_equal": True, "question_raw_sha_equal": True, "label_line_exact": True, "operations_mapped": 8, "parsed_operations": 8, "verbatim_reference_step_copies": 0, "character_diff_roundtrip": True, "no_extra_operation_or_interpolated_parameter": True, "expert_validation": False})
    for name, value in [("cases.json", {"cases": cases}), ("pairs.json", [pair]), ("references_full.json", {"references": full}), ("reference_context.json", payload), ("local_config_snapshot.json", {"models": [local_model]}), ("frozen_judge_contract.json", contract), ("offline_context_preflight.json", {"checks": contexts, "all_fit": True, "model_requests": 0}), ("reference_projection_verification.json", {"status": "pass", "checks": projection, "same_payload_for_both": True}), ("construction_validation.json", {"source_guided": True, "status": "structural_pass_scientific_pending", "construction": bind(CONSTRUCTION / "construction.json"), "validation": bind(CONSTRUCTION / "validation.json"), "expert_confirmed": False})]: save(name, value)
    frozen = [OUT / name for name in ["cases.json", "pairs.json", "references_full.json", "reference_context.json", "local_config_snapshot.json", "frozen_judge_contract.json", "offline_context_preflight.json", "reference_projection_verification.json", "construction_validation.json"]] + [CONSTRUCTION / name for name in ["construction.json", "validation.json", "baseline.txt", "variant.txt"]] + [REFS, CONFIG, AUDIT / "route_answer_matrix.json", BASE / "human_review/selection.json", Path(__file__), ROOT / "scripts/cce_judges.py", ROOT / "scripts/cce_validation.py", ROOT / "scripts/cce_alternative_q2_development.py"]
    count = sum(x.get("event") == "request_started" for x in judges.ledger_rows(LEDGER))
    plan = {"status": "prepared_not_run", "source_guided": True, "construction_validation": bind(OUT / "construction_validation.json"), "question_ids": [248], "source_answers": 1, "full_text_cases": 2, "candidate_pairs": 1, "new_distinct_question_beyond_old_alternatives_and_q2": True, "natural_archived_alternative_pair": False, "judge": "local_qwen3_8b", "repeats": 1, "repeat_index": 0, "max_attempts": 1, "max_calls": 2, "temperature": 0, "max_output_tokens": 8192, "num_ctx": 40960, "timeout_seconds": 600, "planned_new_requests": 2, "actual_new_requests_at_prepare": 0, "historical_trial_reuse": 0, "total_budget": 300, "package_request_count_at_preparation": count, "step_threshold": .7, "frozen_contract_sha256": judges.digest(contract), "frozen_files": [bind(p) for p in frozen], "formal_eligible": False, "expert_confirmations": 0, "scientific_applicability": "pending native tdTomato plus TUJ1 labeling compatibility and initial labeling completion", "reference_coupling_warning": construction["reference_coupling_warning"], "snapshot_id": judges.digest({"cases": cases, "full_references": full, "contract": contract, "construction_sha256": judges.filehash(CONSTRUCTION / "construction.json")})}
    save("plan.json", plan)
    save("execution_commands.json", {"python": str(PY), "cwd": str(ROOT), "actually_executed": [{"stage": "prepare", "argv": ["scripts/cce_alternative_q248_development.py", "prepare"], "model_requests": 0}], "planned_not_executed": {"preflight": ["scripts/cce_alternative_q248_development.py", "preflight"], "run": runner_argv("run"), "analyze": ["scripts/cce_alternative_q248_development.py", "analyze"]}, "new_requests": 0, "budget_owner": "root coordinator"})
    commands = [q2.shell_command(["scripts/cce_alternative_q248_development.py", c]) for c in ["prepare", "preflight"]] + [q2.shell_command(runner_argv("run")), q2.shell_command(["scripts/cce_alternative_q248_development.py", "analyze"])]
    (OUT / "EXECUTION.md").write_text("# q248 source-guided development commands\n\nOnly prepare/preflight are authorized here; root reviews and executes the maximum two fresh requests. Existing `--allow-api` selects the frozen local loopback transport.\n\n```powershell\n" + "\n".join(commands) + "\n```\n", encoding="utf-8")
    (OUT / "README.md").write_text("# q248 来源指导的条件性路线变体\n\n基线为固定13模型顺序首份 Gemini Flash/FDISCO 原答案；变体按既有 PEGASOS 整脑8步参考改写为原答案编号与 Temperature/Time 格式。两份全文均计划重新提取评价，尚未调用。保留 native tdTomato 和原 TUJ1 + Alexa Fluor 647 标签行；未假定已完成 TUJ1 标记，不以抗 tdTomato 替代原生信号。\n\n这是同一原答案的来源指导编辑，不是另一份自然存档答案。标签兼容性、初始标记前提及完整功能合理性仍待确认。源参考同时用于构造和 SR/SP，因此高相似度不能作为独立科学成功证据。未知清洗时长及保存时长不补造。\n\n参见 [冻结计划](plan.json)、[构造核验入口](construction_validation.json)、[两份全文](cases.json)、[完整原参考](references_full.json)、[共同提示参考](reference_context.json)、[静态上下文](offline_context_preflight.json)、[执行状态](execution_commands.json)和[命令](EXECUTION.md)。\n", encoding="utf-8")
    (CONSTRUCTION / "README.md").write_text("# q248 source-guided 构造记录\n\n[construction.json](construction.json) 保存原文身份、每条源操作至改写段落的映射、参数事实、全部字符编辑区间及双向复原核验；[baseline.txt](baseline.txt) 为原文不变基线，[variant.txt](variant.txt) 为8步确定性编辑。\n\n[validation.json](validation.json) 仅验证结构、来源映射和字段保持，不是专家金标或方案有效性证明。原生 tdTomato 与 TUJ1 标签适用性待定，生成评分请求为0。\n", encoding="utf-8")
    validate(); print(judges.canonical({"status": "prepared_not_run", "source_guided": True, "source_answers": 1, "full_text_cases": 2, "mapped_operations": 8, "context_bounds": [c["conservative_context_bound"] for c in contexts], "planned_new_requests": 2, "new_requests": 0}))


def preflight():
    plan, _, _, _ = validate(); *_, contract = judges.preflight(runner_args("preflight"))
    require(contract == judges.read(OUT / "frozen_judge_contract.json") and judges.digest(contract) == plan["frozen_contract_sha256"], "Live contract drift")
    log = judges.read(OUT / "execution_commands.json"); log["actually_executed"].append({"stage": "preflight", "argv": ["scripts/cce_alternative_q248_development.py", "preflight"], "model_requests": 0, "same_frozen_contract": True}); log["planned_not_executed"].pop("preflight", None); save("execution_commands.json", log)
    save("preflight_verification.json", {"status": "pass", "model_requests": 0, "cases": 2, "same_frozen_contract": True, "static_context_all_fit": True, "source_guided": True})


def analyze():
    plan, cases, full, payload = validate()
    trials = [judges.read(p) for p in sorted((OUT / "trials").glob("*.json"))]
    require(trials and len(trials) <= 2, "Expected one or two actual trial records")
    by_id = {t["case_id"]: t for t in trials}; require(len(by_id) == len(trials) and set(by_id) <= {c["case_id"] for c in cases}, "Trial identity drift")
    helpers.OUT = OUT; encoder = helpers.ScopedEncoder()
    step_config = {"encoder": encoder.identity, "threshold": .7, "adapter_sha256": core.filehash(ROOT / "scripts/cce_validation.py"), "full_reference_sha256": judges.digest(full), "prompt_reference_sha256": judges.digest(payload)}
    example = helpers.rubric_example(); records = []; step_rows = []
    for c in cases:
        t = by_id.get(c["case_id"]); expected = judges.digest({"question": c["specific_question"], "question_id": 248, "protocol": c["model_response"], "references": payload})
        if t:
            require(t["judge"] == "local_qwen3_8b" and t["repeat_index"] == 0 and t["attempt"] == 1, "Unexpected trial settings")
            require(t["full_text_input_sha256"] == expected and t["references_sha256"] == judges.digest(payload), "Trial input drift")
            require(t["identity"]["contract_sha256"] == plan["frozen_contract_sha256"] and judges.digest(t["identity"]) == t["trial_id"], "Trial contract drift")
        step = core.score_steps(c, full, encoder, .7); step_rows.append({"case_id": c["case_id"], "answer_sha256": c["answer_sha256"], "step_config_sha256": judges.digest(step_config), "step_result": step})
        raw = t.get("preserved_numeric_proposals", {}) if t else {}; nums = {k: raw.get(k) for k in list(helpers.MAXIMA) + ["Cor", "Eff"]}
        nums.update({"sr": step["sr"], "sp": step["sp"], "Com": .4 * step["sr"] + .6 * nums["c_param"] / 3 if step["sr"] is not None and nums["c_param"] is not None else None})
        dims = [nums["Com"], nums["Cor"], nums["Eff"]]; nums.update({"IA": min(dims) if all(v is not None for v in dims) else None, "HV": math.prod(dims) if all(v is not None for v in dims) else None})
        evaluation = t.get("evaluation", {}) if t else {}; extraction = evaluation.get("extraction"); route = extraction.get("method_name") if isinstance(extraction, dict) else None
        aliases = next(r["route_aliases"] for r in full if r["route_id"] == c["declared_route"]); norm = lambda v: str(v).lower().replace("-", "").replace(" ", "")
        flags = {"extraction_missing": not isinstance(extraction, dict), "explicit_route_mismatch": bool(route and norm(route) not in {norm(a) for a in aliases}), "rubric_example_copy": extraction == example}
        complete = bool(t and t["status"] == "success" and t.get("actual_api_request_made") and t.get("new_extraction_available"))
        records.append({"case_id": c["case_id"], "question_id": 248, "generator_model": c["generator_model"], "answer_origin": c["answer_origin"], "source_guided": c["source_guided"], "construction_validation": plan["construction_validation"], "declared_route": c["declared_route"], "answer_sha256": c["answer_sha256"], "question_sha256": c["question_sha256"], "reference_id": step["reference_id"], "full_reference_sha256": judges.digest(full), "prompt_reference_sha256": judges.digest(payload), "step_config_sha256": judges.digest(step_config), "trial_id": t.get("trial_id") if t else None, "judge_contract_sha256": t["identity"]["contract_sha256"] if t else None, "status": t["status"] if t else "not_run", "technical_pipeline_complete": complete, "candidate_numeric_proposals_and_derived": nums, "extraction": extraction, "scientific_failure_flags": flags, "scientific_validity": "pending_expert_applicability_and_source_guided_construction_bias" if not any(flags.values()) else "evaluator_failure_flagged", "formal_eligible": False, "upstream_cce_eligible": evaluation.get("cce_eligible"), "official_scores": evaluation.get("official_scores"), "formal_scores": {k: None for k in ["Com", "Cor", "Eff", "IA", "HV"]}, "NA_reasons": {k: "not_run" if t is None else "upstream_missing_or_evaluator_failure; inspect original trial" for k, v in nums.items() if v is None}, "raw_trial_path": str(OUT / "trials" / (t["trial_id"] + ".json")) if t else None})
    a, b = records; same = all(a[k] == b[k] and a[k] is not None for k in ["question_sha256", "judge_contract_sha256", "step_config_sha256", "prompt_reference_sha256", "full_reference_sha256"]); complete = same and all(r["technical_pipeline_complete"] for r in records)
    pair = {**judges.read(OUT / "pairs.json")[0], "same_frozen_configuration": same, "technical_pipeline_complete": complete, "formal_completed": False, "construction_validation": plan["construction_validation"], "metrics": {}}
    for metric in helpers.METRICS:
        av, bv = [r["candidate_numeric_proposals_and_derived"][metric] for r in records]; pair["metrics"][metric] = {"baseline": av, "alternative": bv, "delta": bv - av if complete and av is not None and bv is not None else None}
    ledger = judges.ledger_rows(LEDGER); ids = {t["trial_id"] for t in trials} | {judges.read(p)["trial_id"] for p in (OUT / "attempts").glob("*/request_receipt.json")}; attempts = [x for x in ledger if x.get("event") == "request_started" and x.get("trial_id") in ids]; require(len(attempts) <= 2, "Budget exceeded")
    summary = {"status": "actual_development_results", "source_guided": True, "construction_validation": plan["construction_validation"], "question_ids": [248], "source_answers": 1, "full_text_cases": 2, "candidate_pairs": 1, "natural_archived_alternative_pair": False, "technical_successful_cases": sum(r["technical_pipeline_complete"] for r in records), "technical_completed_candidate_pairs": int(complete), "complete_candidate_cce_pairs": int(complete and all(r["candidate_numeric_proposals_and_derived"][k] is not None for r in records for k in ["Com", "Cor", "Eff"])), "scientific_failure_flagged_cases": sum(any(r["scientific_failure_flags"].values()) for r in records), "new_requests_this_batch": len(attempts), "package_requests_in_ledger": sum(x.get("event") == "request_started" for x in ledger), "request_indices": [x["package_request_index"] for x in attempts], "formal_completed_pairs": 0, "expert_confirmation": 0, "reasonable_alternative_confirmed": False, "source_scope": "conditional source-guided development; native label/second label applicability pending; source-construction coupling prevents independent scientific-success inference"}
    for name, value in [("step_config.json", step_config), ("step_results.json", step_rows), ("per_case.json", records), ("paired_results.json", [pair]), ("development_summary.json", summary)]: save(name, value)
    log = judges.read(OUT / "execution_commands.json"); log["actually_executed"].append({"stage": "analyze", "argv": ["scripts/cce_alternative_q248_development.py", "analyze"], "model_requests": 0}); log["planned_not_executed"].pop("analyze", None); log["actual_request_receipt_count"] = len(attempts); log["new_requests"] = len(attempts); save("execution_commands.json", log)
    print(judges.canonical(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("command", choices=["prepare", "preflight", "analyze"]); args = parser.parse_args()
    {"prepare": prepare, "preflight": preflight, "analyze": analyze}[args.command]()
