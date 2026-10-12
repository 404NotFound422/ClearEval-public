"""Prepare and analyze an explicitly provisional, source-bound local judge batch.

This script never calls a model or edits scientific answer/reference text. The
separate existing cce_judges.py runner executes the frozen nine-request matrix.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_validation as scoring
import cce_judges as judges

BASE = ROOT / "artifacts/cce_validation"
OUT = BASE / "judges/local_alternative_development"
LOCAL_CONFIG = BASE / "judges/local_config.json"
SOURCE_CASES = BASE / "controls/alternative_route_candidate_cases.json"
SOURCE_PAIRS = BASE / "controls/alternative_route_candidate_pairs.json"
REFERENCES = BASE / "reference_recovery/references_two_source_development.json"
PYTHON = ROOT.parent / "review_artifacts/bioprobench_2026-09-29/python_portable/python.exe"
METRICS = ["sr", "sp", "c_param", "co_order", "co_method", "co_param", "co_chem",
           "s_method", "s_label", "s_trans", "s_time", "Com", "Cor", "Eff", "IA", "HV"]
MAXIMA = {"c_param": 3, "co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1,
          "s_method": 2.5, "s_label": 6, "s_trans": 3, "s_time": 3}


def save(name, value):
    scoring.write(OUT / name, value)


def table(name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    (OUT / name).write_text(stream.getvalue(), encoding="utf-8-sig")


def exact_runner_prompt(case):
    """Capture the actual upstream prompt without a model transport or request."""
    import OEQ_run_grading_new as runner
    runner.configure_question_snapshot(judges.HIST)

    class Captured(BaseException):
        pass

    class CaptureOnly:
        model_name = "offline_prompt_capture_no_model"

        async def _acall(self, prompt):
            raise Captured(prompt)

    try:
        asyncio.run(runner.evaluate_response_with_teacher(
            CaptureOnly(), case["specific_question"], case["model_response"],
            runner.MODEL_SPACE_SIGNED, {"question_id": case["question_id"]}, None))
    except Captured as captured:
        return (str(captured) + "\n\n[SUPPLIED REFERENCE EVIDENCE]\n" +
                judges.canonical(case["references"]) +
                "\nUse only evidence applicable to the question and declared route; preserve uncertainty.\n")
    raise RuntimeError("Upstream runner did not reach the offline capture adapter")


def prepare(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if any((OUT / "trials").glob("*.json")) or any((OUT / "attempts").glob("*/request_receipt.json")):
        raise ValueError("Existing trials freeze this batch; do not reprepare it")
    refs = scoring.read(args.references)["references"]
    original = scoring.read(SOURCE_CASES)["cases"]
    original_pairs = scoring.read(SOURCE_PAIRS)
    if len(original) != 9 or len(original_pairs) != 6 or len(refs) != 2:
        raise ValueError("Expected frozen nine answers, six candidate pairs and two references")
    local = scoring.read(LOCAL_CONFIG)
    model = next(m for m in local["models"] if m["name"] == "local_qwen3_8b")
    if model["host"] != "http://127.0.0.1:11434" or model["temperature"] != 0:
        raise ValueError("Expected existing temperature-zero loopback configuration")
    if args.max_output_tokens is not None:
        if args.max_output_tokens < 1:
            raise ValueError("Output budget must be positive")
        model["max_tokens"] = args.max_output_tokens
    cases, mapping = [], {}
    for source_case in original:
        cid = source_case["case_id"].replace("__alternative_route_candidate", "__alternative_development")
        mapping[source_case["case_id"]] = cid
        case = {**source_case, "case_id": cid, "source_case_id": source_case["case_id"],
                "condition": "alternative_route_development_natural_answer",
                "scope": "development_computation_only_not_confirmed_reasonable_route_pair",
                "references": refs, "formal_eligible": False,
                "expert_confirmation": None, "reference_status": "source_extracted_not_expert_confirmed"}
        for field, text in [("answer_sha256", case["model_response"]),
                            ("question_sha256", case["specific_question"])]:
            if scoring.digest(text) != case[field]:
                raise ValueError("Source answer/question hash mismatch")
        cases.append(case)
    pairs = [{**p, "source_pair_id": p["pair_id"],
              "pair_id": p["pair_id"].replace("__candidate", "__development"),
              "baseline_case_id": mapping[p["baseline_case_id"]],
              "alternative_case_id": mapping[p["alternative_case_id"]],
              "formal_eligible": False, "expert_confirmation": None} for p in original_pairs]
    snapshot = {"cases": cases, "pairs": pairs, "references": refs}
    snapshot_id = scoring.digest(snapshot)
    save(f"preparations/{snapshot_id}/snapshot.json", snapshot)
    save("cases.json", {"cases": cases})
    save("pairs.json", pairs)
    save("references.json", {"references": refs})
    save("local_config_snapshot.json", local)
    prompt_checks = []
    for case in cases:
        prompt = exact_runner_prompt(case)
        bound = len(prompt.encode("utf-8")) + model["max_tokens"] + 256
        prompt_checks.append({"case_id": case["case_id"], "prompt_sha256": scoring.digest(prompt),
                              "prompt_utf8_bytes": len(prompt.encode("utf-8")),
                              "max_output_tokens": model["max_tokens"], "template_reserve": 256,
                              "conservative_context_bound": bound, "configured_num_ctx": model["num_ctx"],
                              "fits": bound <= model["num_ctx"], "model_requests": 0})
    save("offline_context_preflight.json", {"checks": prompt_checks,
         "all_fit": all(x["fits"] for x in prompt_checks), "model_requests": 0,
         "capture": "actual runner prompt captured before model call; exact existing evidence suffix appended"})
    command_base = (f"& '{PYTHON}' scripts/cce_judges.py {{command}} "
                    f"--cases '{OUT / 'cases.json'}' --out '{OUT}' "
                    f"--model-config '{OUT / 'local_config_snapshot.json'}' --models local_qwen3_8b "
                    f"--repeats 1 --temperature 0 --max-attempts 1 --max-calls 9 --timeout-seconds 600 "
                    f"--ledger '{BASE / 'judges/request_ledger.jsonl'}' --total-budget 300")
    prepare_command = f"& '{PYTHON}' scripts/cce_alternative_development.py prepare --references '{args.references}'"
    if args.max_output_tokens is not None:
        prepare_command += f" --max-output-tokens {args.max_output_tokens}"
    plan = {"scope": "development_only_pending_reference_and_expert_confirmation",
            "prepared_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id, "source_case_file_sha256": scoring.filehash(SOURCE_CASES),
            "source_pair_file_sha256": scoring.filehash(SOURCE_PAIRS),
            "source_reference_file": str(args.references), "source_reference_file_sha256": scoring.filehash(args.references),
            "case_file_sha256": scoring.filehash(OUT / "cases.json"),
            "reference_file_sha256": scoring.filehash(OUT / "references.json"),
            "source_model_config_sha256": scoring.filehash(LOCAL_CONFIG),
            "batch_model_config_sha256": scoring.filehash(OUT / "local_config_snapshot.json"),
            "batch_output_budget_override": args.max_output_tokens,
            "step_threshold": .7, "step_adapter_sha256": scoring.filehash(ROOT / "scripts/cce_validation.py"),
            "package_request_count_at_preparation": sum(x.get("event") == "request_started" for x in judges.ledger_rows(BASE / "judges/request_ledger.jsonl")),
            "judge": "local_qwen3_8b", "generator_models": sorted({c["generator_model"] for c in cases}),
            "unique_source_answers": 9, "candidate_pairs": 6, "question_ids": [21, 22, 23],
            "task_families": 1, "source_families": 2, "shared_baselines": 3,
            "repeats": 1, "temperature": 0, "maximum_attempts_each": 1,
            "planned_new_requests": 9, "maximum_new_requests": 9,
            "confirmed_eligible_pairs": 0, "formal_completed_pairs": 0,
            "formal_eligible": False, "counts_towards_original_controls": False,
            "status": "prepared_context_verified" if all(x["fits"] for x in prompt_checks) else "context_limit_blocked",
            "context_all_fit": all(x["fits"] for x in prompt_checks),
            "preparation_command": prepare_command,
            "preflight_command": command_base.format(command="preflight"),
            "run_command": command_base.format(command="run") + " --allow-api",
            "r2_basis": "Source-extracted development computations may precede expert confirmation; formal eligibility remains pending."}
    save("plan.json", plan)
    (OUT / "commands.md").write_text(
        "# Alternative-route development commands\n\nPreparation completed; model commands below are planned until execution receipts are recorded.\n\n"
        "```powershell\n" + prepare_command + "\n"
        + plan["preflight_command"] + "\n" + plan["run_command"] + "\n"
        + f"& '{PYTHON}' scripts/cce_alternative_development.py analyze\n```\n", encoding="utf-8")
    print(json.dumps({k: plan[k] for k in ["status", "snapshot_id", "planned_new_requests", "context_all_fit"]}))
    print(json.dumps({"context_bound_min": min(x["conservative_context_bound"] for x in prompt_checks),
                      "context_bound_max": max(x["conservative_context_bound"] for x in prompt_checks),
                      "configured_num_ctx": model["num_ctx"]}))


class ScopedEncoder(scoring.Encoder):
    """Read exact old embeddings; all new vectors remain in this owned directory."""
    def encode(self, texts):
        vectors = []
        destination = OUT / "embedding_cache"
        destination.mkdir(exist_ok=True)
        for text in texts:
            key = scoring.digest([self.identity, text]) + ".npy"
            shared, local = self.cache / key, destination / key
            if shared.exists():
                vector = self.np.load(shared)
            elif local.exists():
                vector = self.np.load(local)
            else:
                vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                self.np.save(local, vector)
            vectors.append(vector)
        return self.np.asarray(vectors)


def rubric_example():
    text = (ROOT / "prompts/eval_oeq_teacher_rubric.txt").read_text(encoding="utf-8")
    matches = []
    for marker in re.finditer(r"\{", text):
        try:
            value, _ = json.JSONDecoder().raw_decode(text[marker.start():])
            if isinstance(value, dict) and "extraction" in value and "scores" in value:
                matches.append(value["extraction"])
        except ValueError:
            pass
    if not matches:
        raise ValueError("No rubric example extraction found")
    return matches[-1]


def analyze(args):
    cases = scoring.read(OUT / "cases.json")["cases"]
    pairs = scoring.read(OUT / "pairs.json")
    plan = scoring.read(OUT / "plan.json")
    assert scoring.filehash(OUT / "cases.json") == plan["case_file_sha256"]
    refs = scoring.read(OUT / "references.json")["references"]
    assert scoring.filehash(OUT / "references.json") == plan["reference_file_sha256"]
    assert scoring.filehash(ROOT / "scripts/cce_validation.py") == plan["step_adapter_sha256"]
    trials = [scoring.read(p) for p in sorted((OUT / "trials").glob("*.json"))]
    indexed = {}
    for t in trials:
        if t["repeat_index"] != 0 or t["judge"] != "local_qwen3_8b":
            raise ValueError("Unexpected repeat or judge")
        if t["case_id"] in indexed:
            raise ValueError("Multiple trial identities for the same frozen case")
        indexed[t["case_id"]] = t
    encoder = ScopedEncoder()
    step_config = {"encoder": encoder.identity, "threshold": .7,
                   "adapter_sha256": scoring.filehash(ROOT / "scripts/cce_validation.py"),
                   "adapter_version": scoring.VERSION, "reference_sha256": scoring.digest(refs)}
    save("step_config.json", step_config)
    example = rubric_example()
    archive_path = BASE / "pilot_per_answer.json"
    archived = {r["answer_id"]: r for r in scoring.read(archive_path)}
    records, flats, steps, archive_comparisons, partial_fields = [], [], [], [], []
    for case in cases:
        expected = judges.digest({"question": case["specific_question"], "question_id": case["question_id"],
                                  "protocol": case["model_response"], "references": case["references"]})
        trial = indexed.get(case["case_id"])
        if trial and (trial["full_text_input_sha256"] != expected or trial["references_sha256"] != judges.digest(refs)):
            raise ValueError("Full-text/reference mismatch")
        step = scoring.score_steps(case, refs, encoder, .7)
        steps.append({"case_id": case["case_id"], "answer_sha256": case["answer_sha256"],
                      "step_config_sha256": scoring.digest(step_config), "step_result": step})
        evaluation = trial.get("evaluation", {}) if trial else {}
        teacher_content = evaluation.get("teacher_generation", {}).get("content")
        try:
            teacher_payload = json.loads(teacher_content) if teacher_content else None
        except (ValueError, TypeError):
            teacher_payload = None
        teacher_numbers = judges.proposals({"scores": teacher_payload.get("scores", {})}) if isinstance(teacher_payload, dict) else {}
        raw = trial.get("preserved_numeric_proposals", {}) if trial else {}
        extraction = evaluation.get("extraction")
        raw = {k: raw.get(k) for k in MAXIMA} | {k: raw.get(k) for k in ["Cor", "Eff"]}
        normalized = {k: ((v / MAXIMA[k] + 1) / 2 if k == "s_method" else v / MAXIMA[k]) if v is not None else None
                      for k, v in raw.items() if k in MAXIMA}
        com = .4 * step["sr"] + .6 * raw["c_param"] / 3 if step["sr"] is not None and raw["c_param"] is not None else None
        dims = [com, raw["Cor"], raw["Eff"]]
        numbers = {**raw, "sr": step["sr"], "sp": step["sp"], "Com": com,
                   "IA": min(dims) if all(v is not None for v in dims) else None,
                   "HV": math.prod(dims) if all(v is not None for v in dims) else None}
        route = extraction.get("method_name") if isinstance(extraction, dict) else None
        flags = {"declared_route": step["route_id"], "extracted_route": route,
                 "extracted_route_missing": not bool(route),
                 "explicit_route_mismatch": bool(route and route.lower().replace("-", "") != str(step["route_id"]).lower().replace("-", "")),
                 "extraction_missing": not isinstance(extraction, dict),
                 "extraction_exactly_copies_rubric_example": extraction == example,
                 "rubric_example_extraction_sha256": judges.digest(example),
                 "interpretation": "Software observations only; no expert extraction labels or scientific validity conclusion"}
        complete = bool(trial and trial["status"] == "success" and trial.get("actual_api_request_made") and trial.get("new_extraction_available"))
        record = {"case_id": case["case_id"], "source_case_id": case["source_case_id"],
                  "generator_model": case["generator_model"], "question_id": case["question_id"],
                  "answer_source": case["answer_source"], "answer_sha256": case["answer_sha256"],
                  "question_sha256": case["question_sha256"], "full_text_input_sha256": expected,
                  "references_sha256": judges.digest(refs), "reference_id": step["reference_id"],
                  "reference_source_path": step.get("source_path"), "reference_source_url": step.get("source_url"),
                  "reference_family_id": step.get("family_id"),
                  "reference_status": step.get("reference_status"), "step_config_sha256": scoring.digest(step_config),
                  "trial_id": trial.get("trial_id") if trial else None,
                  "trial_source": str(OUT / "trials" / (trial["trial_id"] + ".json")) if trial else None,
                  "judge_config_sha256": trial.get("pipeline_config_sha256") if trial else None,
                  "status": trial.get("status") if trial else "not_run",
                  "technical_pipeline_complete": complete, "numeric_scope": "development_provisional_not_reasonable_route_validation",
                  "formal_eligible": False, "upstream_cce_eligible": evaluation.get("cce_eligible"),
                  "official_scores": evaluation.get("official_scores"),
                  "official_scores_field_present": "official_scores" in evaluation,
                  "formal_scores": {k: None for k in ["sr", "sp", "Com", "Cor", "Eff", "IA", "HV"]},
                  "formal_na_reasons": ["complete_applicable_references_not_expert_confirmed", "natural_answers_not_confirmed_as_reasonable_routes"],
                  "upstream_integrity": evaluation.get("integrity"),
                  "upstream_status": {k: evaluation.get(k) for k in ["technical_status", "scoring_status", "scientific_status"]},
                  "failure_details": {k: evaluation.get(k) for k in ["_error", "_error_type", "failure_stage"] if k in evaluation},
                  "raw_judgments": evaluation.get("legacy_diagnostics", {}),
                  "raw_teacher_content": teacher_content,
                  "raw_teacher_payload": teacher_payload,
                  "raw_teacher_partial_numbers": teacher_numbers,
                  "raw_teacher_partial_normalized": {k: ((v / MAXIMA[k] + 1) / 2 if k == "s_method" else v / MAXIMA[k]) if v is not None else None
                                                     for k, v in teacher_numbers.items() if k in MAXIMA},
                  "raw_teacher_partial_scope": "Observed raw proposals, including invalid-schema payloads; never substituted for validated candidates or official scores",
                  "extraction": extraction, "extraction_status": evaluation.get("meta_data", {}).get("extraction_status"),
                  "candidate_raw_and_derived": numbers, "candidate_normalized_items": normalized,
                  "candidate_na_reasons": {k: step.get("step_missing_reason") if k in ["sr", "sp"] else "upstream_value_absent_or_unresolved_or_dependency_missing"
                                           for k, v in numbers.items() if v is None},
                  "scientific_failure_flags": flags}
        if trial and trial["status"] != "success":
            provider_path = OUT / "attempts" / f"{trial['trial_id']}_{trial['attempt']}" / "provider_response.json"
            provider = scoring.read(provider_path)
            response = provider.get("response", "")
            try:
                payload = json.loads(response)
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                source_meta = {"case_id": case["case_id"], "trial_id": trial["trial_id"],
                               "provider_response_path": str(provider_path),
                               "provider_response_sha256": scoring.filehash(provider_path),
                               "provider_string_field": "response",
                               "response_text_sha256": scoring.digest(response),
                               "technical_status": "failed", "partial_diagnostic_only": True,
                               "formal_eligible": False, "not_substituted_into_trial": True}
                observed = set()
                for group, values in payload.get("scores", {}).items():
                    if not isinstance(values, dict):
                        continue
                    for field, item in values.items():
                        if not isinstance(item, dict) or "score" not in item:
                            continue
                        observed.add(field)
                        value, maximum = item.get("score"), ({"c_step": 2, **MAXIMA}).get(field)
                        mapped = maximum is not None
                        if maximum is None:
                            maximum = item.get("max_score")
                        valid = (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                                 and isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and maximum > 0
                                 and (-maximum if field == "s_method" else 0) <= value <= maximum)
                        partial_fields.append({**source_meta, "field": field,
                            "parsed_response_json_pointer": f"/scores/{group}/{field}/score", "raw_value": value,
                            "range_valid": valid, "contract_key_recognized": mapped,
                            "normalized_value": ((value / maximum + 1) / 2 if field == "s_method" else value / maximum) if valid else None,
                            "status": "observed_contract_field" if mapped else "observed_noncanonical_key_not_mapped",
                            "reasoning": item.get("reasoning"), "na_reason": None if valid else "invalid_or_unknown_range"})
                partial_numbers = judges.proposals({"scores": payload.get("scores", {})})
                partial_numbers.update({"sr": step["sr"], "sp": step["sp"]})
                cp = partial_numbers["c_param"]
                partial_numbers["Com"] = .4 * step["sr"] + .6 * cp / 3 if step["sr"] is not None and cp is not None else None
                partial_numbers.update({"IA": None, "HV": None})
                record["partial_diagnostic_numeric"] = partial_numbers
                record["partial_diagnostic_raw_extraction"] = payload.get("extraction")
                record["partial_diagnostic_scope"] = "Exact raw-return fields plus independently known provisional steps; upstream failed result unchanged; never a complete pipeline"
                for field in ["co_chem", "sr", "sp", "Com", "Cor", "Eff", "IA", "HV"]:
                    if field in observed:
                        continue
                    value = partial_numbers.get(field)
                    reason = ("expected_key_absent; co_chemical is retained separately without alias repair" if field == "co_chem" else
                              "depends_on_missing_contract_item" if field == "Cor" else
                              "upstream_effectiveness_not_evaluated_after_output_validation_failure" if field == "Eff" else
                              "incomplete_CCE_dependency" if field in ["IA", "HV"] else step.get("step_missing_reason"))
                    partial_fields.append({**source_meta, "field": field, "parsed_response_json_pointer": None,
                        "raw_value": value, "range_valid": value is not None, "contract_key_recognized": True,
                        "normalized_value": value if field in ["sr", "sp", "Com", "Cor", "Eff", "IA", "HV"] else None,
                        "status": "derived_from_known_fields_only" if value is not None else "NA",
                        "reasoning": None, "na_reason": reason if value is None else None,
                        "step_config_sha256": scoring.digest(step_config)})
        records.append(record)
        natural_id = case["source_case_id"].removesuffix("__alternative_route_candidate")
        old = archived.get(natural_id)
        if old:
            if old["answer_sha256"] != case["answer_sha256"] or old["question_sha256"] != case["question_sha256"]:
                raise ValueError("Archived descriptive components refer to a different input")
            old_metrics = list(MAXIMA) + ["Cor", "Eff"]
            comparison = {"case_id": case["case_id"], "answer_id": natural_id,
                          "archive_file": str(archive_path), "archive_file_sha256": scoring.filehash(archive_path),
                          "archive_score_source": old.get("score_source"),
                          "historical_score_binding": old.get("historical_score_binding"),
                          "scope": "descriptive_archive_vs_current_substitute_settings_differ_not_accuracy_validation",
                          "formal_eligible": False}
            for metric in old_metrics:
                av, nv = old.get(metric), numbers.get(metric)
                comparison.update({"archive_" + metric: av, "current_candidate_" + metric: nv,
                                   "delta_" + metric: nv - av if av is not None and nv is not None else None})
            archive_comparisons.append(comparison)
        flats.append({k: record[k] for k in ["case_id", "generator_model", "question_id", "status", "technical_pipeline_complete", "reference_id", "formal_eligible", "trial_id", "judge_config_sha256", "step_config_sha256"]}
                     | numbers | {"norm_" + k: v for k, v in normalized.items()} | flags)
    by_id = {r["case_id"]: r for r in records}
    pair_results = []
    for pair in pairs:
        a, z = by_id[pair["baseline_case_id"]], by_id[pair["alternative_case_id"]]
        same = all(a[k] == z[k] and a[k] is not None for k in ["judge_config_sha256", "step_config_sha256", "references_sha256", "question_sha256"])
        complete = same and a["technical_pipeline_complete"] and z["technical_pipeline_complete"]
        entry = {"pair_id": pair["pair_id"], "question_id": pair["question_id"],
                 "baseline_case_id": a["case_id"], "alternative_case_id": z["case_id"],
                 "technical_pipeline_complete": complete, "same_frozen_configuration": same,
                 "eligible_confirmed": False, "formal_complete": False, "formal_eligible": False,
                 "scope": "descriptive_cross_generator_candidate_comparison_shared_baselines_not_route_causal_effect",
                 "judge_config_sha256": a["judge_config_sha256"], "step_config_sha256": a["step_config_sha256"],
                 "references_sha256": a["references_sha256"]}
        for metric in METRICS:
            av, zv = a["candidate_raw_and_derived"].get(metric), z["candidate_raw_and_derived"].get(metric)
            entry.update({"baseline_" + metric: av, "alternative_" + metric: zv,
                          "delta_" + metric: zv - av if complete and av is not None and zv is not None else None})
        pair_results.append(entry)
    save("step_results.json", steps)
    save("per_case.json", records)
    table("per_case.csv", flats)
    save("paired_results.json", pair_results)
    table("paired_results.csv", pair_results)
    table("archive_component_comparison.csv", archive_comparisons)
    save("partial_return_fields.json", partial_fields)
    table("partial_return_fields.csv", partial_fields)
    save("scientific_failure_flags.json", [{"case_id": r["case_id"], **r["scientific_failure_flags"]} for r in records])
    ledger = judges.ledger_rows(BASE / "judges/request_ledger.jsonl")
    receipts = [scoring.read(p) for p in (OUT / "attempts").glob("*/request_receipt.json")]
    trial_ids = {t["trial_id"] for t in trials} | {r["trial_id"] for r in receipts}
    summary = {"planned_cases": 9, "source_answers": 9, "question_ids": [21, 22, 23], "task_families": 1,
               "source_families": 2, "shared_baselines": 3, "candidate_pairs": 6,
               "technical_successful_cases": sum(r["technical_pipeline_complete"] for r in records),
               "technical_completed_candidate_pairs": sum(p["technical_pipeline_complete"] for p in pair_results),
               "complete_candidate_cce_cases": sum(all(r["candidate_raw_and_derived"].get(k) is not None for k in ["Com", "Cor", "Eff"]) for r in records),
               "complete_candidate_cce_pairs": sum(p["technical_pipeline_complete"] and all(p.get(prefix + k) is not None for prefix in ["baseline_", "alternative_"] for k in ["Com", "Cor", "Eff"]) for p in pair_results),
               "confirmed_eligible_pairs": 0, "formal_completed_pairs": 0, "formal_eligible": False,
               "official_score_available_cases": sum(r["official_scores"] is not None for r in records),
               "explicit_route_mismatches": sum(r["scientific_failure_flags"]["explicit_route_mismatch"] for r in records),
               "extractions_available_for_route_and_example_checks": sum(isinstance(r["extraction"], dict) for r in records),
               "partial_failure_records": sum("partial_diagnostic_numeric" in r for r in records),
               "rubric_example_copies": sum(r["scientific_failure_flags"]["extraction_exactly_copies_rubric_example"] for r in records),
               "new_requests_this_batch": sum(x.get("event") == "request_started" and x.get("trial_id") in trial_ids for x in ledger),
               "request_receipts_without_trial_result": sum(r["trial_id"] not in {t["trial_id"] for t in trials} for r in receipts),
               "package_requests_in_ledger": sum(x.get("event") == "request_started" for x in ledger),
               "counts_towards_original_controls": False,
               "scope": "Real full-text local computations; provisional comparisons only, no confirmed reasonable-route acceptance or causal claim"}
    save("development_summary.json", summary)
    plan["status"] = "computed_development_with_partial_failure" if summary["technical_successful_cases"] < 9 else "computed_development"
    plan["actual_new_requests"] = summary["new_requests_this_batch"]
    plan["actual_technical_successful_cases"] = summary["technical_successful_cases"]
    plan["current_results"] = "development_summary.json"
    save("plan.json", plan)
    (OUT / "commands.md").write_text(
        "# Executed alternative-route development commands\n\n"
        "Prepare and preflight completed. The frozen local run made nine requests with one allowed attempt per answer. "
        "The execution receipt contains the exact invoked argument arrays; analysis is deterministic and adds no requests.\n\n"
        "```powershell\n" + plan["preparation_command"] + "\n" + plan["preflight_command"] + "\n"
        + plan["run_command"] + "\n"
        + f"& '{PYTHON}' scripts/cce_alternative_development.py analyze\n```\n\n"
        + f"Technical successes: {summary['technical_successful_cases']}/9; complete descriptive pairs: {summary['technical_completed_candidate_pairs']}/6; formal eligible pairs: 0.\n",
        encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "analyze"])
    parser.add_argument("--references", type=Path, default=REFERENCES)
    parser.add_argument("--max-output-tokens", type=int)
    arguments = parser.parse_args()
    prepare(arguments) if arguments.command == "prepare" else analyze(arguments)
