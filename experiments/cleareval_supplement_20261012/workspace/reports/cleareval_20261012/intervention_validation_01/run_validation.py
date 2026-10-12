"""Actual offline ablations of proposed improvements, with preserved old results."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DAY = HERE.parent
PILOT = DAY / "english_fulltext_pilot"
QWEN = PILOT / "qwen_translation_pending"
REPO = Path(r"C:\ClearEval\ClearEval-public")
sys.path[:0] = [str(HERE), str(QWEN), str(REPO / "scripts")]
import structural_view as view
import score_translations as io
import mechanism_checks as old_heading
import numpy as np


def maximum_matching(edges):
    matched = {}

    def augment(row, seen):
        for col in np.flatnonzero(edges[row]):
            col = int(col)
            if col in seen:
                continue
            seen.add(col)
            if col not in matched or augment(matched[col], seen):
                matched[col] = row
                return True
        return False

    for row in range(edges.shape[0]):
        augment(row, set())
    return sorted([{"reference_index": r, "generated_index": c} for c, r in matched.items()], key=lambda x: x["reference_index"])


def main():
    ledger = REPO / "artifacts/cce_validation/judges/request_ledger.jsonl"
    old_scores = QWEN / "scoring/results.json"
    bound = [io.bind(p) for p in [ledger, old_scores, HERE / "structural_view.py", Path(__file__), QWEN / "mechanism_checks.py", PILOT / "time_examples/examples.json", DAY / "qualitative_execution_03/matrix.json"]]
    bound += [io.bind(p) for p in sorted((PILOT / "documents").glob("*/original.txt"))]
    bound += [io.bind(PILOT / "controls" / aid / "original" / (condition + ".txt")) for aid in ["R3C04", "R3C07"] for condition in ["renumber_operations", "merge_adjacent_operations", "delete_reported_core_operations"]]
    bound += [io.bind(DAY / "automatic_time_scope/canonical32_04/results.json"), io.bind(REPO / "scripts/cce_representation_repair_v3.py")]
    plan = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "offline_development_ablation_before_new_results", "new_model_requests": 0,
            "expert_ground_truth": False, "fresh_holdout": False, "inputs": bound,
            "tests": ["full-source numbering and cross-reference input equality", "content-changing controls and roundtrip", "parameter-free parent heading counterexamples", "fixed-matrix phase mask and sentence-capacity ablation", "THF operation identity versus thresholded retrieval", "existing time arithmetic ablation", "prepared Cor prompt factor separation"],
            "main_scores_replaced": False, "encoder_or_threshold_changed": False,
            "interpretation": "Effect on inspected development cases only; no translation or Cor behavioral claim without new responses."}
    io.write(HERE / "plan.json", plan)
    out = HERE / "structural_views"
    out.mkdir(exist_ok=True)
    structure, negatives = [], []
    for path in sorted((PILOT / "documents").glob("*/original.txt")):
        aid = path.parent.name
        source = io.text(path)
        generated = view.renumber(source)
        existing = PILOT / "controls" / aid / "original/renumber_operations.txt"
        variant = io.text(existing) if existing.exists() else generated
        a, b = view.canonicalize(source), view.canonicalize(variant)
        for label, text, parsed in [("original", source, a), ("renumber", variant, b)]:
            (out / (aid + "_" + label + ".txt")).write_text(text, encoding="utf-8", newline="")
            (out / (aid + "_" + label + "_view.txt")).write_text(parsed["view"], encoding="utf-8", newline="")
            io.write(out / (aid + "_" + label + "_mapping.json"), {k: v for k, v in parsed.items() if k != "view"})
        same_refs = [(r["from_node"], r["target_node"]) for r in a["references"]] == [(r["from_node"], r["target_node"]) for r in b["references"]]
        question = io.text(path.parent / "question.txt")
        # Proposed exact request content, not a call or cached translation result.
        prompt_a = json.dumps({"question": question, "answer": a["view"]}, ensure_ascii=False, sort_keys=True)
        prompt_b = json.dumps({"question": question, "answer": b["view"]}, ensure_ascii=False, sort_keys=True)
        structure.append({"answer_id": aid, "source": io.bind(path), "control_origin": "previously_frozen_control" if existing.exists() else "new_protocol_outline_only_format_control",
                          "nodes": len(a["nodes"]), "cross_references": len(a["references"]), "same_view": a["view"] == b["view"], "same_reference_targets": same_refs,
                          "same_exact_proposed_request_content": prompt_a == prompt_b, "original_issues": a["issues"], "variant_issues": b["issues"], "roundtrip_exact": a["roundtrip_exact"] and b["roundtrip_exact"], "new_translation_performed": False})
        m = re.search(r"Time:\s*(\d+(?:\.\d+)?)", source)
        if m:
            changed = source[:m.start(1)] + str(float(m[1]) + 1) + source[m.end(1):]
            negatives.append({"answer_id": aid, "kind": "duration_change", "old": m[1], "new": str(float(m[1]) + 1), "distinguished": view.canonicalize(changed)["view"] != a["view"]})
        if a["nodes"]:
            leaf = next((n for n in a["nodes"] if n["parent_id"]), a["nodes"][0])
            changed = source[:leaf["start"]] + source[leaf["end"]:]
            negatives.append({"answer_id": aid, "kind": "remove_source_entry", "removed_source_quote": leaf["source_quote"], "distinguished": view.canonicalize(changed)["view"] != a["view"]})
        if a["references"]:
            broken = view.renumber(source, update_references=False)
            bv = view.canonicalize(broken)
            negatives.append({"answer_id": aid, "kind": "renumber_without_updating_references", "distinguished": bv["view"] != a["view"], "reported_issues": bv["issues"]})
    fixtures = [
        ("standalone_decimal_quantity", "Protocol Steps:\n3.1 % reagent\n", "Protocol Steps:\n4.1 % reagent\n", False),
        ("flat_reference_renumber", "Protocol Steps:\n1. Wash item.\n2. Repeat step 1.\n", "Protocol Steps:\n101. Wash item.\n102. Repeat step 101.\n", True),
        ("reference_target_changes", "Protocol Steps:\n1. Wash item.\n2. Transfer item.\n3. Repeat step 1.\n", "Protocol Steps:\n1. Wash item.\n2. Transfer item.\n3. Repeat step 2.\n", False),
        ("actual_quantity_after_label", "Protocol Steps:\n1 Stage\n1.1 Add 3.1 mL material.\n", "Protocol Steps:\n101 Stage\n101.1 Add 3.1 mL material.\n", True),
        ("repeat_count_changes", "Protocol Steps:\n1 Stage\n1.1 Repeat 2 times.\n", "Protocol Steps:\n101 Stage\n101.1 Repeat 3 times.\n", False),
        ("negation_changes", "Protocol Steps:\n1 Stage\n1.1 Do not wash.\n", "Protocol Steps:\n101 Stage\n101.1 Wash.\n", False),
        ("incomplete_remains_incomplete", "Protocol Steps:\n1 Washing\n1.1 Incubation with\n", "Protocol Steps:\n101 Washing\n101.1 Incubation with\n", True),
        ("modal_coexecution_reference", "Protocol Steps:\n1 Stage\n1.1 Wash item.\n1.2 与1.1可以共同执行。\n", "Protocol Steps:\n101 Stage\n101.1 Wash item.\n101.2 与101.1可以共同执行。\n", True),
    ]
    fixture_rows = []
    for name, a, b, expected in fixtures:
        av, bv = view.canonicalize(a), view.canonicalize(b)
        actual = av["view"] == bv["view"]
        fixture_rows.append({"name": name, "source_a": a, "source_b": b, "expected_same": expected, "actual_same": actual, "passed": actual == expected,
                             "basis": "explicitly constructed engineering contrast; not natural-answer or expert evidence"})
    io.write(HERE / "structure_results.json", structure)
    io.write(HERE / "content_controls.json", negatives)
    io.write(HERE / "structure_fixtures.json", fixture_rows)
    io.csvwrite(HERE / "structure_results.csv", [{k: v for k, v in r.items() if not isinstance(v, (dict, list))} for r in structure])

    titles = [
        ("true_heading", "1 Wash after primary\n1.1 Wash the sample in fresh buffer.\n", True),
        ("parent_is_operation", "1 Wash the sample thoroughly.\n1.1 Transfer it into fresh buffer.\n", False),
        ("parent_has_volume", "1 Add 5 mL buffer.\n1.1 Mix gently.\n", False),
        ("parent_has_non_numeric_duration", "1 Incubate the sample overnight.\n1.1 Wash the sample.\n", False),
        ("explicit_time_field", "1 Incubate the sample. (Time: 2 hours)\n1.1 Wash the sample.\n", False),
        ("parent_contains_negation", "1 Do not agitate the sample.\n1.1 Store it in the chamber.\n", False),
    ]
    heading_rows = []
    for name, text, expected in titles:
        actual = bool(old_heading.hierarchical_title_spans(text))
        heading_rows.append({"case": name, "source": text, "expected_parent_is_heading": expected, "old_filter_removes_parent": actual, "passes": actual == expected, "basis": "constructed structure challenge, not independent scientific ground truth"})
    io.write(HERE / "heading_counterexamples.json", heading_rows)

    scores = io.read(old_scores)
    matrices, identity_checks = [], []
    for r in scores:
        chosen = r["selected"]
        matrix = np.asarray(chosen["similarity_matrix"])
        edges = matrix >= .7
        assignments = maximum_matching(edges)
        record = {"request_id": r["request_id"], "answer_id": r["answer_id"], "condition": r["condition"], "fixed_reference_id": chosen["reference_id"],
                  "raw_sr": chosen["score"]["sr"], "raw_sp": chosen["score"]["sp"], "raw_reference_hits": int(edges.any(axis=1).sum()),
                  "one_sentence_capacity_matched_references": len(assignments), "one_sentence_capacity_rate": len(assignments) / len(matrix),
                  "assignments": assignments, "capacity_ablation_not_validated_operation_coverage": True, "main_scores_replaced": False}
        source = io.text(r["translation"]["path"])
        if r["answer_id"] == "R3C04":
            # Read the explicit heading from the full text even after its children
            # have been deleted. An empty section can still locate the phase.
            anchors = [{"start": m.start(), "end": m.end(), "source_quote": m[0]} for m in re.finditer(r"^[ \t]*(?:\*\*)?\d+[.)]?[ \t]+Dehydration before clearing[^\n]*", source, re.M | re.I)]
            if anchors:
                anchor = anchors[0]
                allowed = np.asarray([g["start"] >= anchor["start"] for g in r["generated_steps"]])
                masked = edges & allowed[None, :]
                record.update(phase_anchor={"start": anchor["start"], "end": anchor["end"], "quote": anchor["source_quote"]},
                              phase_scope_basis="post-immunolabeling clearing reference context; assistant-scoped diagnostic, not new expert label",
                              phase_masked_reference_hits=int(masked.any(axis=1).sum()), phase_masked_rate=float(masked.any(axis=1).mean()),
                              phase_masked_one_sentence_capacity=len(maximum_matching(masked)))
                record["removed_original_edges"] = [{"reference_index": int(i), "generated_index": int(j), "reference_text": chosen["score"]["matches"][i]["reference_text"],
                                                       "generated_text": r["generated_steps"][j]["text"], "similarity": float(matrix[i, j])} for i, j in zip(*np.where(edges & ~allowed[None, :]))]
                record["best_matches_after_phase_constraint"] = []
                for i in range(len(matrix)):
                    cols = np.flatnonzero(allowed)
                    j = int(cols[np.argmax(matrix[i, cols])])
                    record["best_matches_after_phase_constraint"].append({"reference_index": i, "generated_index": j,
                        "reference_text": chosen["score"]["matches"][i]["reference_text"], "generated_text": r["generated_steps"][j]["text"],
                        "similarity": float(matrix[i,j]), "matched": bool(edges[i,j])})
            else:
                record["phase_mask_missing_reason"] = "no_explicit_post_labeling_dehydration_anchor"
        else:
            for refidx in range(4):
                reftext = chosen["score"]["matches"][refidx]["reference_text"]
                concentration = re.search(r"(\d+)%", reftext)[1]
                pattern = re.compile(r"(?<!\d)" + concentration + r"%\s*(?:\(vol/vol\)\s*)?THF", re.I)
                candidates = []
                for j, g in enumerate(r["generated_steps"]):
                    for found in pattern.finditer(g["text"]):
                        candidates.append({"generated_index": j, "matched_literal": found[0], "generated_text": g["text"], "source_span": {"start": g["start"], "end": g["end"], "quote": source[g["start"]:g["end"]]},
                                           "similarity": float(matrix[refidx, j]), "similarity_rank": 1 + int((matrix[refidx] > matrix[refidx,j]).sum()), "passes_original_threshold": bool(edges[refidx, j])})
                identity_checks.append({"request_id": r["request_id"], "reference_index": refidx, "reference_text": reftext, "concentration_identity": concentration,
                                        "candidate_occurrences": candidates, "raw_best_match": chosen["score"]["matches"][refidx],
                                        "interpretation": "Same reported concentration and THF locate candidate operation identity only; not proof of full scientific correctness, conditions, or repetition coverage."})
        matrices.append(record)
    io.write(HERE / "fixed_matrix_ablations.json", matrices)
    io.csvwrite(HERE / "fixed_matrix_ablations.csv", [{k: r.get(k) for k in ["request_id", "raw_sr", "raw_sp", "raw_reference_hits", "one_sentence_capacity_matched_references", "one_sentence_capacity_rate", "phase_masked_reference_hits", "phase_masked_rate"]} for r in matrices])
    io.write(HERE / "operation_identity_evidence.json", identity_checks)

    import cce_representation_repair_v3 as old_normalizer
    old_results = io.read(DAY / "automatic_time_scope/canonical32_04/results.json")
    old_c07 = next(r for r in old_results if r["cell_id"] == "R3C07__r0")
    post = io.read(old_c07["post_record"]["path"])
    doc = io.read(old_c07["source_document"]["path"])
    original_c07 = io.text(PILOT / "documents/R3C07/original.txt")
    assert old_normalizer.canonicalize_full_text(original_c07)["evaluation_text"] == doc["text"]
    raw_content = post["conversion"]["raw_content_preserved"]
    assert hashlib.sha256(raw_content.encode("utf-8")).hexdigest() == post["raw_sha256"]
    # The archived wire schema uses i/o/p/d/r/s/c; resolved records use id/operation/phase.
    raw_operations = {o["i"]: o for o in json.loads(raw_content)["grounded_extraction"]["operations"]}
    recovered = []
    for op in post["conversion"]["source_audit"]["resolved"]["operations"]:
        span = op["operation"]
        if "THF" in span["quote"]:
            assert doc["text"][span["start"]:span["end"]] == span["quote"]
            recovered.append({"operation_id": op["id"], "source": span, "phase": op["phase"], "raw_model_record": raw_operations[op["id"]]})
    io.write(HERE / "existing_decomposition_reuse.json", {"answer_id": "R3C07", "source_document": old_c07["source_document"], "saved_processing": old_c07["post_record"],
             "original_source_matches_saved_canonical_document": True, "raw_response_sha256": post["raw_sha256"], "existing_distinct_THF_operations": recovered,
             "new_model_requests": 0, "expert_verified": False, "interpretation": "The archived model already separated the five THF operations. The current raw sentence score does not consume these operation identities; new baseline extraction is not needed to establish their presence."})

    time_rows = []
    for example in io.read(PILOT / "time_examples/examples.json"):
        document = io.read(example["source_document"]["path"])
        for scenario in example["ledger"]["scenarios"]:
            bounds = [sum(c["bounds_hours"][side] for c in scenario["contributions"]) for side in [0, 1]]
            assert bounds == scenario["bounds_hours"]
            for c in scenario["contributions"]:
                span = c["source"]
                assert document["text"][span["start"]:span["end"]] == span["quote"]
            time_rows.append({"case_id": example["case_id"], "scenario_id": scenario["scenario_id"], "recomputed_hours": sum(bounds) / 2, "bounds_hours": bounds,
                              "source_document": example["source_document"], "new_extraction": False, "expert_validated": example["expert_validated"]})
        if example["case_id"] == "FPC13":
            scenario = example["ledger"]["scenarios"][0]
            cumulative = next(c for c in scenario["contributions"] if c["option_id"] == "source_cumulative_total")
            operation = next(o for o in example["ledger"]["operations"] if o["operation_id"] == cumulative["operation_id"])
            provenance = next(o["source_cumulative_duration"] for o in operation["duration"]["options"] if o["option_id"] == "source_cumulative_total")
            initial_source = provenance["original_duration_ref"]
            assert document["text"][initial_source["start"]:initial_source["end"]] == initial_source["quote"]
            old_duration = provenance["original_parsed_duration"]["unique_hours"]
            assert float(re.fullmatch(r"([\d.]+)\s+hours?", initial_source["quote"])[1]) == old_duration
            current_total = scenario["hours"]
            time_rows.append({"case_id": "FPC13", "ablation": "ignore_same_stage_cumulative_relation", "initial_duration": old_duration, "source_cumulative_hours": sum(cumulative["bounds_hours"]) / 2,
                              "with_relation_hours": current_total, "keep_initial_only_hours": current_total - sum(cumulative["bounds_hours"]) / 2 + old_duration,
                              "add_initial_and_total_hours": current_total + old_duration, "source_evidence": cumulative["source"], "initial_source_evidence": initial_source,
                              "incoming_raw_parsed_duration_is_already_derived": operation["raw_parsed_duration"]["unique_hours"] == sum(cumulative["bounds_hours"])/2,
                              "new_extraction": False})
    io.write(HERE / "time_relation_checks.json", time_rows)

    prepared = io.read(DAY / "qualitative_execution_03/matrix.json")
    pairs = {}
    for item in prepared:
        pairs.setdefault(item["answer_id"], {})[item["condition"]] = item
    cor_rows = []
    for aid, pair in sorted(pairs.items()):
        c0, c1 = pair["C0"], pair["C1"]
        p0, p1 = [io.text(item["assets"]["prompt"]["path"]) for item in [c0, c1]]
        a, b = [io.read(item["assets"]["payload"]["path"]) for item in [c0, c1]]
        cor_rows.append({"answer_id": aid, "same_document": io.read(c0["assets"]["doc"]["path"]) == io.read(c1["assets"]["doc"]["path"]),
                         "same_non_prompt_payload": {k: v for k, v in a.items() if k != "prompt"} == {k: v for k, v in b.items() if k != "prompt"},
                         "old_uncertainty_contract_present": "[UNCERTAINTY CONTRACT]" in p0,
                         "revised_criterion_scope_present": "[JUDGMENT SCOPE AND MISSING EVIDENCE]" in p1,
                         "extra_label_instruction_added": "[LABEL ROLE CLARIFICATION]" not in p0 and "[LABEL ROLE CLARIFICATION]" in p1,
                         "old_percentage_deviation_rule_removed": "时间/浓度偏差在 50%" in p0 and "时间/浓度偏差在 50%" not in p1,
                         "prompt_paths": [c0["assets"]["prompt"]["path"], c1["assets"]["prompt"]["path"]],
                         "observed_new_Cor_effect": None, "reason": "Prepared two-condition bundle; no model response. Cannot isolate scope and evidence factors or establish efficacy."})
    ledger_rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8-sig").splitlines() if line]
    cor_round_requests = [r for r in ledger_rows if r.get("round_id") == "qualitative_correctness_pairs_20261012"]
    io.write(HERE / "cor_static_checks.json", {"pairs": cor_rows, "planned_legacy_requests": 10, "actual_round_requests": len(cor_round_requests), "candidate_two_by_two_executed": False})

    for binding in bound:
        assert io.bind(binding["path"]) == binding, binding["path"]
    summary = {"status": "completed_offline_development_tests", "natural_answers": len(structure), "previously_frozen_renumber_pairs": sum(r["control_origin"] == "previously_frozen_control" for r in structure),
               "equal_canonical_input_pairs": sum(r["same_exact_proposed_request_content"] for r in structure), "source_roundtrips_exact": sum(r["roundtrip_exact"] for r in structure),
               "content_changing_controls": len(negatives), "content_changes_distinguished": sum(r["distinguished"] for r in negatives),
               "structure_fixtures": len(fixture_rows), "structure_fixture_passes": sum(r["passed"] for r in fixture_rows),
               "heading_challenges": len(heading_rows), "heading_challenge_failures": sum(not r["passes"] for r in heading_rows),
               "fixed_matrix_rows": len(matrices), "new_model_requests": 0, "new_embeddings": 0, "new_expert_records": 0,
               "actual_Cor_candidate_requests": len(cor_round_requests), "whole_pipeline_efficacy_confirmed": False,
               "raw_SRSP_and_CCE_unchanged": True, "ledger_requests": len(ledger_rows)}
    io.write(HERE / "SUMMARY.json", summary)
    io.write(HERE / "execution.json", {"command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]), "completed_utc": datetime.now(timezone.utc).isoformat(), "inputs_unchanged": True, "ledger": io.bind(ledger), "new_model_requests": 0})
    print(json.dumps(summary))
    print(json.dumps([{k: r.get(k) for k in ["request_id", "raw_sr", "one_sentence_capacity_rate", "phase_masked_rate"]} for r in matrices]))


if __name__ == "__main__":
    main()
