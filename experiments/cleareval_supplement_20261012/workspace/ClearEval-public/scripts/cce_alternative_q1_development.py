"""Prepare/preflight/analyze one source-bound q1 alternative development pair.

This script never calls a generating model. The unchanged cce_judges.py runner
is the only execution entry; the coordinator controls its two-request budget.
"""
from __future__ import annotations
import argparse
import copy
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
OUT = BASE / "judges/local_alternative_q1_v1"
UDISCO = BASE / "reference_recovery/udisco_2016"
COHORT = BASE / "q1_extension_v1/cohort.json"
SOURCE_REFS = BASE / "expanded_tasks_v4/references.json"
SOURCE_CONFIG = BASE / "judges/local_controls_supplement_v2/local_config_snapshot.json"
LEDGER = BASE / "judges/request_ledger.jsonl"
PY = ROOT.parent / "review_artifacts/bioprobench_2026-09-29/python_portable/python.exe"
MAXIMA = helpers.MAXIMA
METRICS = helpers.METRICS
PROVENANCE_FIELDS = {"source_spans", "source_span", "source_anchor", "source_pages", "evidence_manifest_path", "source_conflicts_path", "evidence_ids", "prerequisite_source_span", "table_binding", "source_locations"}
TOP_PROVENANCE_FIELDS = {"source_path", "source_sha256", "source_url", "source_files", "parent_candidate", "parent_reference_id", "q1_applicability_record", "frozen", "freeze_scope", "source_candidate_binding", "scope_note_binding"}


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
        kept = {"reference_id", "route_id", "route_aliases", "question_ids", "continuous_conditions", "unknown_parameters", "unknowns", "excluded_aliases"}
        projected = {k: project_metadata(v) for k, v in ref.items() if k in kept}
        projected["source_scope"] = "Conditional author clearing-step coverage; scientific applicability pending, expert confirmation absent, formal eligibility false."
        require(all(s["required"] for s in ref["steps"]), "Nonuniform required status")
        projected["all_listed_steps_required_in_this_conditional_scope"] = True
        projected["steps"] = [{"step_id": s["step_id"], "text": s["text"], **({"notes": s["notes"]} if s.get("notes") else {})} for s in ref["steps"]]
        mapping = {"steps[].text": "identical text, IDs and order", "required": "all_listed_steps_required_in_this_conditional_scope",
            "source/status/build/confirmation metadata": "source_scope plus full_reference_sha256; full records remain in references_full.json"}
        if ref["route_id"] == "iDISCO+":
            app = ref["applicability"]
            app_keys = ["species", "tissue", "conditional_prerequisite", "label_choice_assessment", "outcomes_pending", "exact_question_dimensions_supported"]
            projected["applicability"] = {k: app[k] for k in app_keys}
            # Timing-status labels describe values/endpoints already in unchanged step text;
            # retain their exact distinct strings once, with explicit step membership.
            timing = {}
            for step in ref["steps"]:
                timing.setdefault(step["timing_status"], []).append(step["step_id"])
            projected["timing_status_by_step"] = timing
            mapping["applicability other fields"] = "repeated qid/scope/prerequisite/label-choice statements or source-review/version metadata; exact originals retained in full reference"
        else:
            # All numerical operation fields remain exact in a compact row table.
            numeric_keys = ["concentration_percent_vv", "time_literal", "duration_hours", "temperature_C", "temperature", "lower_bound_hours_exclusive", "endpoint"]
            projected["step_parameter_columns"] = numeric_keys
            projected["step_parameter_rows_in_step_order"] = [[s.get(k) for k in numeric_keys] for s in ref["steps"]]
            projected["missing_parameter_key_means_unspecified_not_zero"] = True
            projected["source_branch_notes"] = [s[k] for s in ref["steps"] for k in ["not_skipped_for_this_branch", "source_binding_rule"] if k in s]
            projected["unconfirmed_start_prerequisites_outside_step_denominator"] = [s["text"] for s in ref["scoring_start_prerequisites"]]
            projected["applicability"] = "Fixed/postfixed adult whole brain is stated; prior preparation and compatible activity labeling are not established. Whole-brain activity/IEG compatibility remains pending; c-Fos and Npas4 are not mandatory dual labels. Missing evidence does not prove incompatibility."
            projected["reagent_definitions"] = project_metadata(ref["reagent_definitions"])
            projected["reagent_handling_condition"] = project_metadata(ref["reagent_handling_condition"])
            projected["working_volume_context"] = project_metadata(ref["working_volume_context"])
            projected["terminal_storage"] = {k: v for k, v in ref["terminal_storage"].items() if k in ["medium", "temperature", "light", "duration_literal", "duration_hours"]}
            projected["terminal_storage_scope"] = "Same-medium ongoing condition, no new transfer/exchange counted; no fixed upper duration or task-specific fluorescence guarantee."
            projected["branch_choices"] = project_metadata(ref["branch_choices"])
            projected["source_conflict_columns"] = ["id", "field", "sources"]
            projected["source_conflict_rows"] = [[d[k] for k in ["id", "field", "sources"]] for d in ref["source_version_differences"]]
            projected["source_conflict_policy"] = "Use selected whole-organ table and D4 option as stated. Do not average versions, optimize by conflicting performance claims, repair D14/D15, or transfer half-brain/body timing; conflicts remain unresolved."
            mapping.update({"steps numerical fields": "step_parameter_columns + ordered rows; exact scalar values retained", "steps.not_skipped_for_this_branch/source_binding_rule": "source_branch_notes verbatim",
                "source_version_differences": "all IDs, fields and source values verbatim in source_conflict_rows; repeated decisions represented by branch_choices/source_conflict_policy/prerequisites",
                "terminal_storage duplicated status fields": "terminal_storage_scope; same medium, no exchange, no task guarantee retained",
                "initial_state/applicability/completeness": "applicability + source_scope + unconfirmed prerequisites + nine listed operations; full source has eleven operations"})
        projected["full_reference_sha256"] = judges.digest(ref)
        require([s["text"] for s in projected["steps"]] == [s["text"] for s in ref["steps"]], "Step text changed")
        require([s["step_id"] for s in projected["steps"]] == [s["step_id"] for s in ref["steps"]], "Step IDs changed")
        checks.append({"reference_id": ref["reference_id"], "full_reference_sha256": judges.digest(ref), "source_path": ref["source_path"], "source_sha256": ref["source_sha256"], "steps": len(ref["steps"]), "all_step_text_ID_order_equal": True, "all_scientific_conditions_and_unknowns_preserved": True, "deduplication_mapping": mapping})
        payload.append(projected)
    return payload, checks


def source_scope_projection():
    """Bind only author operations 03-11; keep the unbound source immutable."""
    candidate_path = UDISCO / "candidate.json"
    require(judges.filehash(candidate_path) == "7165e118c8f21c677c487e53651afad148f69e51b70de2df9d0628ef1d23a7fa", "Reviewed source candidate changed")
    parent = judges.read(candidate_path)["references"][0]
    require(parent["question_ids"] == [] and len(parent["steps"]) == 11, "Unexpected unbound source scope")
    checks = []
    def check_spans(obj):
        if isinstance(obj, dict):
            if {"text_file", "start", "end", "quote"} <= set(obj):
                text = Path(obj["text_file"]["path"]).read_text(encoding="utf-8")
                require(judges.filehash(obj["text_file"]["path"]) == obj["text_file"]["sha256"], "Source page text changed")
                require(text[obj["start"]:obj["end"]] == obj["quote"], "Source span mismatch")
                require(core.digest(obj["quote"]) == obj["quote_sha256"], "Source quote changed")
                checks.append({"text_path": obj["text_file"]["path"], "start": obj["start"], "end": obj["end"], "quote_sha256": obj["quote_sha256"]})
            for v in obj.values(): check_spans(v)
        elif isinstance(obj, list):
            for v in obj: check_spans(v)
    check_spans(parent)
    for source in parent["source_files"]:
        require(judges.filehash(source["path"]) == source["sha256"], "Author source PDF changed")
    ref = copy.deepcopy(parent)
    ref["reference_id"] = "UDISCO_2016_AUTHOR_D4_CLEARING_Q1_CONDITIONAL_V1"
    ref["question_ids"] = [1]
    ref["requires_explicit_task_binding"] = False
    ref["steps"] = copy.deepcopy(parent["steps"][2:])
    require([s["step_id"] for s in ref["steps"]] == [f"UDISCO16-PASSIVE-{n:02d}" for n in range(3, 12)], "Unexpected step projection")
    ref["initial_state"] = "Fixed and postfixed adult whole brain. Author preclear wash and meninge removal are unconfirmed prerequisites outside this clearing-only denominator, not operations established by the question. Compatible activity labeling is also unconfirmed."
    ref["source_scope"] = "source_only_conditional: author operations 03-11 plus terminal storage conditions; not a complete task solution or expert-confirmed biological necessity"
    ref["scoring_start_prerequisites"] = [{"source_step_id": s["step_id"], "text": s["text"], "confirmed_by_question": False, "included_in_step_denominator": False, "source_spans": s.get("source_spans", [])} for s in parent["steps"][:2]]
    ref["applicability"] = {"question_ids": [1], "fixation_and_postfixation_complete": True,
        "task_requested_scope": "clearing, RI matching and storage/pre-imaging only",
        "whole_brain_activity_label_compatibility": "pending",
        "preclear_wash_and_meninge_removal_already_completed": "not_established",
        "label_or_reporter_already_present": "not_established",
        "q1_requires_cFos_and_Npas4_dual_label": False,
        "scientific_task_solution_or_reasonable_alternative_confirmed": False,
        "missing_task_specific_evidence_is_not_proof_of_incompatibility": True}
    ref["completeness"] = {**parent["completeness"], "sample_operation_count": 9, "parent_source_operation_count": 11,
        "sequence_scope": "author clearing-only projection; not the full postfixed workflow"}
    ref["source_version_differences"] = judges.read(UDISCO / "source_version_differences.json")
    ref["source_candidate_binding"] = binding(candidate_path)
    ref["scope_note_binding"] = binding(UDISCO / "conditional_scoring_scope_note.md")
    ref["terminal_storage"] = copy.deepcopy(parent["terminal_storage"])
    require(ref["steps"] == parent["steps"][2:], "Scientific operation data changed")
    idisco = next(r for r in judges.read(SOURCE_REFS)["references"] if r["route_id"] == "iDISCO+" and r["question_ids"] == [1])
    save("source_scope_review.json", {"status": "pass_for_conditional_clearing_projection_only", "reviewer": "assistant_not_human_expert",
        "udisco_parent": binding(candidate_path), "checked_source_spans": checks,
        "source_images_visually_reviewed": [binding(UDISCO / "source_pages/protocol_p05.png"), binding(UDISCO / "source_pages/thesis_p070.png")],
        "source_table_column": "adult whole organs including brain; not half brain", "source_version_differences": binding(UDISCO / "source_version_differences.json"),
        "D4_selection": "first author table option, not performance optimization; source performance wording conflict remains unresolved",
        "D14_D15_footnote_conflict": "retained, not silently corrected; selected D4 identity agrees",
        "table_vs_common_prose_timing": "selected table values retained; other source values retained as conflicts, not blended",
        "parent_step_count": 11, "scored_step_count": 9, "preclear_operations_01_02": "unconfirmed start prerequisites, outside denominator",
        "terminal_storage": "retained as continuous condition, no invented transfer or exchange",
        "idisco_q1_reference_object_reused_exactly": True, "source_only_conditional": True,
        "formal_eligible": False, "expert_confirmations": 0, "new_model_requests": 0})
    return [idisco, ref]


def select_natural_answers(full):
    cohort = judges.read(COHORT)
    require(len(cohort["models"]) == 13, "Expected fixed 13-model cohort")
    rows, found, archives = [], {"iDISCO+": [], "uDISCO": []}, []
    for rank, model in enumerate(cohort["models"], 1):
        path = ROOT / "dataset/Q+AR/model_response" / ("from_" + model + "_1-shot.json")
        require(judges.filehash(path) == cohort["input_files"][str(path.relative_to(ROOT))], "Archive changed")
        archives.append(binding(path))
        raw = path.read_bytes(); text = raw.decode("utf-8-sig"); bom = 3 if raw.startswith(b"\xef\xbb\xbf") else 0
        decoder = json.JSONDecoder(); position = text.index("[") + 1; matches = []
        while position < len(text):
            while position < len(text) and text[position] in " \t\r\n,": position += 1
            if text[position] == "]": break
            obj, end = decoder.raw_decode(text, position)
            if str(obj.get("question_id")) == "1":
                start_byte = bom + len(text[:position].encode("utf-8")); end_byte = bom + len(text[:end].encode("utf-8"))
                matches.append((obj, {"object_byte_start_inclusive": start_byte, "object_byte_end_exclusive": end_byte, "object_bytes_sha256": hashlib.sha256(raw[start_byte:end_byte]).hexdigest()}))
            position = end
        require(len(matches) <= 1, "Ambiguous duplicate q1 answer")
        if not matches:
            rows.append({"model": model, "model_rank": rank, "status": "answer_missing"}); continue
        answer, locator = matches[0]
        require(core.digest(answer["specific_question"]) == "ac7743003caa89284c89474dab866f9fa2f7ea709519726e06e1fe63ce7a7300", "Historical q1 identity mismatch")
        route, declaration = core.selected_route(answer["model_response"], full)
        item = {"answer_id": model + "__q1", "model": model, "model_rank": rank,
            "answer_sha256": core.digest(answer["model_response"]), "question_sha256": core.digest(answer["specific_question"]),
            "answer_source": str(path), "answer_object": locator, "declared_route": route,
            "route_declaration": declaration, "reference_id": next((r["reference_id"] for r in full if r["route_id"] == route), None)}
        rows.append(item)
        if route in found: found[route].append(item)
    require(found["iDISCO+"] and len(found["uDISCO"]) == 1, "Expected at least one iDISCO+ and unique uDISCO source answer")
    selected = [found[r][0] for r in ["iDISCO+", "uDISCO"]]
    require([r["model"] for r in selected] == ["gemini-3-pro", "openai_deepseek-chat"], "First-model deterministic selection changed")
    save("selection.json", {"rule": "fixed original 13-model order; first actual complete archived q1 answer for each explicit route, no score-dependent selection",
        "models": cohort["models"], "rows": rows, "selected": selected, "archive_bindings": archives,
        "generic_iDISCO_not_aliased_to_iDISCO_plus": True, "prior_scores_read_for_selection": False,
        "source_only_conditional": True, "formal_eligible": False})
    return {"pair_id": "q1__iDISCOplus_vs_uDISCO__source_only_conditional", "routes": ["iDISCO+", "uDISCO"], "answers": selected}, archives


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
    full = source_scope_projection()
    selected, archive_bindings = select_natural_answers(full)
    require(len(full) == 2, "Expected two conditional q1 clearing branches")
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
        require(int(answer["question_id"]) == 1, "Only q1 is authorized in this pair")
        require(core.digest(answer["model_response"]) == item["answer_sha256"] and core.digest(answer["specific_question"]) == item["question_sha256"], "Source identity mismatch")
        registry.get(1, answer["specific_question"])
        case = {"case_id": item["answer_id"] + "__alternative_q1_v1", "source_case_id": item["answer_id"], "base_id": item["answer_id"],
            "question_id": 1, "specific_question": answer["specific_question"], "model_response": answer["model_response"],
            "generator_model": item["model"], "declared_route": route, "answer_source": str(archive),
            "answer_sha256": item["answer_sha256"], "question_sha256": item["question_sha256"], "references": payload,
            "condition": "alternative_route_development_natural_answer", "formal_eligible": False, "expert_confirmation": None,
            "scope": "source_only_conditional_q1_clearing_pair_pending_whole_brain_activity_label_applicability",
            "source_only_conditional": True, "scoring_start_prerequisites_confirmed": False,
            "scoring_scope": {"uDISCO": "author steps 03-11; 01/02 are unconfirmed start prerequisites outside denominator; storage remains continuous condition", "iDISCO+": "existing q1 nine-step conditional clearing reference unchanged; prior immunolabeling not established by question"}}
        prompt = helpers.exact_runner_prompt(case)
        full_prompt = helpers.exact_runner_prompt({**case, "references": full})
        bound = len(prompt.encode("utf-8")) + settings["max_output_tokens"] + 256
        contexts.append({"case_id": case["case_id"], "exact_prompt_sha256": core.digest(prompt), "prompt_utf8_bytes": len(prompt.encode("utf-8")),
            "max_output_tokens": 8192, "template_reserve": 256, "conservative_context_bound": bound, "configured_num_ctx": 40960,
            "fits": bound <= 40960, "unprojected_full_reference_bound": len(full_prompt.encode("utf-8")) + 8192 + 256,
            "capture": "actual unchanged runner prompt intercepted before transport plus exact supplied evidence suffix", "model_requests": 0})
        evidence.append({**item, "case_id": case["case_id"], "whole_answer_unchanged": True, "historical_scores_reused_as_new_extraction": False})
        cases.append(case)
    save("offline_context_preflight.json", {"status": "pass" if all(x["fits"] for x in contexts) else "context_exceeded_not_prepared", "checks": contexts, "all_fit": all(x["fits"] for x in contexts), "model_requests": 0})
    require(all(x["fits"] for x in contexts), "Conservative context bound exceeded; no generation permitted")
    require(cases[0]["specific_question"] == cases[1]["specific_question"] and cases[0]["references"] == cases[1]["references"], "Pair question/reference mismatch")
    pair = {"pair_id": "q1__iDISCOplus_vs_uDISCO__development_v1", "question_id": 1,
        "baseline_case_id": cases[0]["case_id"], "alternative_case_id": cases[1]["case_id"], "routes": selected["routes"],
        "source_pair_id": selected["pair_id"], "formal_eligible": False, "reasonable_alternative_confirmed": False, "source_only_conditional": True,
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
        "rule": "Keep exact step text/ID/order, all numerical operation values, reagent definitions, continuous conditions, scientific unknowns and source-conflict values. Store repeated parameter keys in a column/row table; consolidate repeated applicability and scope statements with explicit field mapping. Source/build/review metadata and original wording remain in full references bound by hash. Check the per-reference deduplication_mapping for the representation of each group.",
        "prompt_reference_is_metadata_projection": True, "not_a_new_scientific_reference": True, "full_payload_equal_for_both_cases": True,
        "removed_provenance_key_names": sorted(PROVENANCE_FIELDS), "model_requests": 0})
    save("offline_context_preflight.json", {"status": "pass", "checks": contexts, "all_fit": True, "model_requests": 0})
    frozen_files = [OUT / x for x in ["cases.json", "pairs.json", "references_full.json", "reference_context.json", "local_config_snapshot.json", "frozen_judge_contract.json", "source_answer_provenance.json", "reference_projection_verification.json", "offline_context_preflight.json"]]
    frozen_files += [SOURCE_REFS, SOURCE_CONFIG, COHORT, UDISCO / "candidate.json", UDISCO / "conditional_scoring_scope_note.md", UDISCO / "q1_applicability.json", UDISCO / "source_version_differences.json", UDISCO / "table1_evidence.json", OUT / "selection.json", OUT / "source_scope_review.json", Path(__file__), ROOT / "scripts/cce_judges.py", ROOT / "scripts/cce_validation.py", ROOT / "scripts/cce_alternative_development.py"]
    frozen_files += [Path(item["path"]) for item in archive_bindings]
    before = sum(x.get("event") == "request_started" for x in judges.ledger_rows(LEDGER))
    plan = {"status": "prepared_not_run", "question_ids": [1], "source_answers": 2, "candidate_pairs": 1,
        "new_distinct_question_beyond_old_alternative_batch": True, "source_families": 2, "same_full_reference_set_for_both": True,
        "same_projected_reference_payload_for_both": True, "judge": "local_qwen3_8b", "repeat_index": 0, "repeats": 1,
        "temperature": 0, "max_output_tokens": 8192, "num_ctx": 40960, "max_attempts": 1, "max_calls": 2, "timeout_seconds": 600,
        "planned_new_requests": 2, "new_requests_at_preparation": 0, "historical_trial_reuse": 0, "package_total_budget": 300,
        "package_request_count_at_preparation": before, "expected_package_count_if_both_attempts_made": before + 2,
        "step_threshold": 0.7, "frozen_contract_sha256": judges.digest(frozen_contract),
        "frozen_files": [binding(p) for p in frozen_files], "formal_eligible": False, "expert_confirmations": 0,
        "source_only_conditional": True, "scored_operations_per_route": {"iDISCO+": 9, "uDISCO": 9},
        "udisco_full_source_operation_count": 11, "preclear_01_02_completion_confirmed": False,
        "scientific_dependencies": ["iDISCO+ requires appropriately immunolabeled starting material; q1 only establishes fixation", "uDISCO author preclear wash and meninge removal are unconfirmed start prerequisites outside this clearing denominator", "Whole-brain activity labeling and IEG compatibility for both actual answers remain pending; native FP or slice immunolabel evidence cannot establish it", "D4 is the first author table option; D4/D15 performance and D14/D15 naming conflicts remain unresolved", "Task-specific labels, morphology and route reasonableness await separate assessment", "Source-extracted operation coverage is not expert-confirmed scientific necessity"],
        "snapshot_id": judges.digest({"cases": cases, "pairs": [pair], "full_references": full, "contract": frozen_contract})}
    save("plan.json", plan)
    command_log = {"actually_executed": [{"stage": "prepare", "argv": [str(Path(__file__)), "prepare"], "model_requests": 0}],
        "planned_not_executed": {"preflight": [str(Path(__file__)), "preflight"], "run": command_arguments("run"), "analyze": [str(Path(__file__)), "analyze"]},
        "python": str(PY), "working_directory": str(ROOT), "budget_owner": "root coordinator", "new_requests": 0}
    save("execution_commands.json", command_log)
    commands = [shell_command(["scripts/cce_alternative_q1_development.py", "prepare"]), shell_command(["scripts/cce_alternative_q1_development.py", "preflight"]), shell_command(command_arguments("run")), shell_command(["scripts/cce_alternative_q1_development.py", "analyze"])]
    (OUT / "EXECUTION.md").write_text("# q1 development pair execution\n\nPrepare/preflight are non-generating checks. Run/analyze remain planned until their actual receipts exist. The coordinator owns the maximum two new requests. The runner's legacy `--allow-api` switch enables the frozen loopback transport; no external API is configured.\n\n```powershell\n" + "\n".join(commands) + "\n```\n\nBoth complete original answers use the same projected reference evidence and frozen Qwen settings. Full references remain separately bound by raw file hash. No historical score is substituted for fresh extraction.\n", encoding="utf-8")
    (OUT / "README.md").write_text("# q1 条件性清除路线开发配对\n\n按冻结13模型顺序选每路线首份真实全文：Gemini Pro/iDISCO+ 与 DeepSeek Chat/uDISCO。当前仅准备与预检，未完成新增评价；来源和全脑活动标记适用性仍 pending，不能称合理替代已确认。\n\nuDISCO 只投影作者第03–11项九个清除操作，参数与文本原样；01/02初洗、去膜作为未确认起点前提，题干未确认已完成。保存保持同介质持续条件。iDISCO+ 原q1九步参考对象逐字复用，进入分支前免疫标记同样未由题干确认。D4取作者表首先列出分支，不依据性能择优；D4/D15性能及D14/D15名称冲突保留。\n\n完整答案不编辑；共同参考投影只去来源定位元数据、去重复范围文字，科学条件、配液定义、未知与冲突保留。全参考和原候选单独哈希绑定，v4主评分不变。Qwen temperature0、8192输出、40960上下文、repeat0、attempt1，每份一次，计划最多2新请求。不同模型自然答案只作描述比较，不是路线因果效应。专家0、正式0。\n\n参见 [计划](plan.json)、[选择记录](selection.json)、[来源范围核对](source_scope_review.json)、[完整参考](references_full.json)、[共同提示参考](reference_context.json)、[投影核验](reference_projection_verification.json)、[答案来源](source_answer_provenance.json)、[上下文检查](offline_context_preflight.json)和[执行状态](execution_commands.json)。\n", encoding="utf-8")
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
        expected_input = judges.digest({"question": case["specific_question"], "question_id": 1, "protocol": case["model_response"], "references": payload})
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
        records.append({"case_id": case["case_id"], "question_id": 1, "generator_model": case["generator_model"], "declared_route": case["declared_route"], "answer_sha256": case["answer_sha256"], "question_sha256": case["question_sha256"], "reference_id": step["reference_id"], "source_only_conditional": True, "scoring_scope": case["scoring_scope"], "scoring_start_prerequisites_confirmed": False, "full_reference_sha256": judges.digest(full), "prompt_reference_sha256": judges.digest(payload), "step_config_sha256": judges.digest(step_config), "trial_id": trial.get("trial_id") if trial else None, "judge_contract_sha256": trial["identity"]["contract_sha256"] if trial else None, "status": trial["status"] if trial else "not_run", "technical_pipeline_complete": complete, "candidate_numeric_proposals_and_derived": numbers, "extraction": extraction, "scientific_failure_flags": flags, "scientific_validity": "pending_expert_and_applicability" if not any(flags.values()) else "evaluator_failure_flagged", "formal_eligible": False, "upstream_cce_eligible": evaluation.get("cce_eligible"), "official_scores": evaluation.get("official_scores"), "formal_scores": {k: None for k in ["Com", "Cor", "Eff", "IA", "HV"]}, "NA_reasons": {k: "not_run" if trial is None else "upstream_missing_or_evaluator_failure; inspect original trial" for k, v in numbers.items() if v is None}, "raw_trial_path": str(OUT / "trials" / (trial["trial_id"] + ".json")) if trial else None})
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
    summary = {"status": "actual_development_results", "question_ids": [1], "source_answers": 2, "candidate_pairs": 1, "technical_successful_cases": sum(r["technical_pipeline_complete"] for r in records), "technical_completed_candidate_pairs": int(complete), "complete_candidate_cce_pairs": int(complete and all(r["candidate_numeric_proposals_and_derived"][k] is not None for r in records for k in ["Com", "Cor", "Eff"])), "scientific_failure_flagged_cases": sum(any(r["scientific_failure_flags"].values()) for r in records), "new_requests_this_batch": count, "package_requests_in_ledger": sum(x.get("event") == "request_started" for x in ledger), "formal_completed_pairs": 0, "expert_confirmation": 0, "reasonable_alternative_confirmed": False, "source_only_conditional": True, "source_scope": "conditional clearing operations only; start prerequisites and whole-brain activity labeling unconfirmed; different natural generators; no causal route or expert-validity claim"}
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
