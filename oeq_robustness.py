"""OEQ robustness diagnostics bound to existing numerical grading.

No provider calls, new knowledge population, imaging-result inference or
implicit conversion of a diagnostic into a replacement score.
"""
from copy import deepcopy
from collections import Counter
import hashlib
from pathlib import Path

from evaluation_contract import json_hash
from evaluator_integrity import audit_flat_extraction, validate_legacy_extraction
from experiments.construct_validity.fidelity import text_hash

VERSION = "oeq-robustness-v5"
INPUT_VERSION = "oeq-robustness-inputs-v1"
SET_VERSION = "oeq-robustness-input-set-v1"
ROOT = Path(__file__).resolve().parent
SIDECAR_FIELDS = ("robustness_diagnostics_required", "robustness_original_input",
                  "robustness_input_bundle", "robustness_numeric_binding",
                  "robustness_diagnostics", "robustness_diagnostics_sha256")
ALLOWED_INPUTS = {"schema_version", "question_sha256", "protocol_sha256",
                  "candidate_inventory", "manual_inventory", "manual_extraction",
                  "candidate_assessment", "objective_comparison", "quantity_role_claims"}


def validate_bundle(bundle, question, protocol):
    if bundle is None:
        return None
    if not isinstance(bundle, dict) or set(bundle) - ALLOWED_INPUTS:
        raise ValueError("Unknown robustness input structure")
    if (bundle.get("schema_version") != INPUT_VERSION
            or bundle.get("question_sha256") != json_hash(question)
            or bundle.get("protocol_sha256") != text_hash(protocol)):
        raise ValueError("Robustness inputs do not bind this original question and answer")
    json_hash(bundle)
    from oeq_fidelity_impact import audit_inventory, parse_candidate_json
    for field, role in (("candidate_inventory", "CANDIDATE_EXTRACTION"), ("manual_inventory", "MANUAL_REFERENCE")):
        value = bundle.get(field)
        if value is not None:
            if isinstance(value, str):
                parsed = parse_candidate_json(value)
                if parsed["status"] == "PARSE_FAILURE":
                    raise ValueError("Invalid inventory JSON before teacher request")
                value = parsed["value"]
            audit_inventory(protocol, value, role=role)
    if bundle.get("manual_extraction") is not None:
        validate_legacy_extraction(bundle["manual_extraction"])
    from oeq_quantity_audit import audit_quantity_role_inputs
    audit_quantity_role_inputs(protocol, bundle.get("quantity_role_claims"))
    return deepcopy(bundle)


def select_bundle(input_set, question, protocol):
    if input_set is None:
        return None
    if (not isinstance(input_set, dict)
            or set(input_set) != {"schema_version", "entries"}
            or input_set["schema_version"] != SET_VERSION
            or not isinstance(input_set["entries"], list)):
        raise ValueError("Expected a versioned robustness input set")
    keys = []
    for row in input_set["entries"]:
        if not isinstance(row, dict) or row.get("schema_version") != INPUT_VERSION or set(row)-ALLOWED_INPUTS:
            raise ValueError("Invalid robustness input-set entry")
        for name in ("question_sha256", "protocol_sha256"):
            v = row.get(name)
            if not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
                raise ValueError("Invalid robustness input binding")
        keys.append((row["question_sha256"], row["protocol_sha256"]))
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate robustness bindings")
    key = (json_hash(question), text_hash(protocol))
    selected = validate_bundle(input_set["entries"][keys.index(key)], question, protocol) if key in keys else None
    if selected is not None:
        # Reject invalid bound optional inputs before any teacher request.
        _candidate_diagnostics(selected, question, protocol)
        _objective_diagnostics(selected, question, protocol)
    return selected


def numeric_binding(evaluation, marker_query_targets=None):
    formulas = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                for name in ("OEQ_run_grading_new.py", "evaluation_contract.py", "results/oeq_metrics.py")}
    paths = ["dataset/Q+AR/src/model_space_signed.json", "KnowledgeBase/tissue.json",
             "KnowledgeBase/method_fluro_compati.json", "KnowledgeBase/time_kb.json",
             "KnowledgeBase/tissue_ri.json", "KnowledgeBase/method_sigma_ri.json",
             "KnowledgeBase/method_ri_ref.json"]
    knowledge = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    return {"formulas": formulas, "knowledge_base": knowledge,
            "context": {"quantitative_data": deepcopy(evaluation.get("quantitative_data")),
                        "user_preference_vector": deepcopy(evaluation.get("user_preference_vector")),
                        "marker_query_targets": deepcopy(marker_query_targets or []),
                        "base_scores": _scores(evaluation)}}


def _scores(evaluation):
    return deepcopy(evaluation.get("scores") or evaluation.get("legacy_diagnostics", {}).get("scores") or {})


def _candidate_diagnostics(inputs, question, protocol):
    supplied = (inputs or {}).get("candidate_assessment")
    if supplied is None:
        return {"status": "UNRESOLVED", "reason": "BOUND_STRUCTURED_CANDIDATE_ASSESSMENT_NOT_SUPPLIED",
                "independent_reference_count": 0, "scientific_accuracy": None}
    if (not isinstance(supplied, dict) or set(supplied)-{"context", "proposal", "independent_reference", "contract_review"}
            or not isinstance(supplied.get("context"), dict) or not isinstance(supplied.get("proposal"), dict)):
        raise ValueError("Bound candidate context and structured proposal required")
    from oeq_scientific import apply_assessment
    context = supplied["context"]
    if context.get("question_sha256") != json_hash(question):
        raise ValueError("Candidate assessment has a different question")
    assessment = apply_assessment(supplied["proposal"], context, protocol)
    reference = supplied.get("independent_reference")
    check = {"status": "UNAVAILABLE", "independent_reference_count": 0, "label_agreement": None}
    if reference is not None:
        if not isinstance(reference, dict):
            raise ValueError("Candidate reference must be an object")
        bound = (reference.get("question_sha256") == json_hash(question)
                 and reference.get("protocol_sha256") == text_hash(protocol)
                 and reference.get("context_sha256") == context["context_sha256"])
        independent = (reference.get("independence") == "INDEPENDENT"
                       and reference.get("assistance") == "NONE"
                       and isinstance(reference.get("reviewer_id"), str) and bool(reference["reviewer_id"].strip())
                       and isinstance(reference.get("record_id"), str) and bool(reference["record_id"].strip()))
        target = reference.get("target")
        from experiments.construct_validity.contract import combine
        predicted = assessment["overall"]
        valid_target = target in {"REVIEWED_REQUIREMENT_CONTRACT", "COMPLETE_SCIENTIFIC_ACCEPTABILITY"}
        if target == "COMPLETE_SCIENTIFIC_ACCEPTABILITY":
            contract_review = supplied.get("contract_review") or {}
            full_reviewed = (isinstance(contract_review, dict)
                and contract_review.get("scope") == "FULL_SINGLE_METHOD_CANDIDATE"
                and contract_review.get("context_sha256") == context["context_sha256"]
                and contract_review.get("independence") == "INDEPENDENT"
                and contract_review.get("assistance") == "NONE"
                and isinstance(contract_review.get("reviewer_id"), str) and bool(contract_review["reviewer_id"].strip())
                and isinstance(contract_review.get("record_id"), str) and bool(contract_review["record_id"].strip()))
            valid_target = valid_target and full_reviewed
            # A scientific subset cannot override missing hard conditions or
            # the existing whole-candidate/route binding guards.
            predicted = combine([assessment["overall"], assessment["scientific_applicability_decision"]["status"]])
        if bound and independent and valid_target and reference.get("label") in {"SATISFIED", "VIOLATED"}:
            check.update(status="INDEPENDENT_REFERENCE_AVAILABLE", independent_reference_count=1,
                         label_agreement=predicted == reference["label"], predicted=predicted,
                         reference_label=reference["label"], target=target)
        else:
            check["reason"] = "REFERENCE_NOT_INDEPENDENT_KNOWN_OR_INPUT_BOUND"
        check["reference"] = deepcopy(reference)
    return {"status": assessment["overall"], "assessment": assessment,
            "reference_validation": check, "independent_reference_count": check["independent_reference_count"],
            "scientific_accuracy": None}


def _objective_diagnostics(inputs, question, protocol):
    from oeq_objective_bridge import build_objective_diagnostics
    supplied = (inputs or {}).get("objective_comparison")
    if supplied is None:
        return build_objective_diagnostics()
    if not isinstance(supplied, dict) or set(supplied)-{
            "candidate_records", "independent_relation", "required_constraints", "objective_names"}:
        raise ValueError("Unknown objective-comparison input")
    records = supplied.get("candidate_records")
    if records is not None:
        if not isinstance(records, list) or len(records) != 2:
            raise ValueError("Objective bridge requires two complete candidates")
        if any(not isinstance(r, dict) or r.get("task_id") != json_hash(question) for r in records):
            raise ValueError("Objective records do not bind the current task")
        if not any(r.get("protocol_sha256", r.get("id")) == text_hash(protocol) for r in records):
            raise ValueError("Objective pair does not contain the current complete answer")
    return build_objective_diagnostics(candidate_records=records,
              independent_relation=supplied.get("independent_relation"),
              required_constraints=supplied.get("required_constraints"),
              objective_names=supplied.get("objective_names"))


def _numeric_input_matches(evaluation, question, protocol):
    qh, ph = json_hash(question), text_hash(protocol)
    if (evaluation.get("meta_data", {}).get("question_sha256") != qh
            or evaluation.get("integrity", {}).get("answer_sha256") != ph):
        return False
    if evaluation.get("protocol_sha256") not in (None, ph):
        return False
    if evaluation.get("workflow_diagnostics_required") is True:
        return evaluation.get("workflow_diagnostics_binding") == {
            "question_sha256": qh, "protocol_sha256": ph}
    return True


def build_report(question, protocol, evaluation, inputs=None, *, binding=None, scorer=None):
    if not _numeric_input_matches(evaluation, question, protocol):
        raise ValueError("Robustness originals differ from the existing numerical input bindings")
    inputs = validate_bundle(inputs, question, protocol)
    binding = deepcopy(binding if binding is not None else numeric_binding(evaluation))
    flat = evaluation.get("extraction")
    fidelity = (audit_flat_extraction(flat, protocol) if isinstance(flat, dict) else
                {"fidelity_status": "UNAVAILABLE", "validated": False, "reason": "NO_EXTRACTED_FIELDS"})
    from oeq_quantity_audit import audit_quantity_scope
    quantity_audit = audit_quantity_scope(protocol, flat)
    from oeq_quantity_audit import audit_quantity_role_inputs
    role_audit = audit_quantity_role_inputs(protocol, (inputs or {}).get("quantity_role_claims"))
    from oeq_fidelity_impact import compare_inventories, measure_score_impact
    comparison = {"status": "UNAVAILABLE", "reason": "INDEPENDENT_ORIGINAL_TEXT_INVENTORIES_NOT_SUPPLIED",
                  "extraction_agreement": None, "scientific_accuracy": None}
    impact = {"status": "UNAVAILABLE", "reason": "INDEPENDENT_MANUAL_EXTRACTION_NOT_SUPPLIED",
              "score_differences": {}, "scientific_accuracy": None}
    candidate_inventory = (inputs or {}).get("candidate_inventory")
    manual_inventory = (inputs or {}).get("manual_inventory")
    if candidate_inventory is not None or manual_inventory is not None:
        comparison = compare_inventories(protocol, candidate_inventory, manual_inventory)
        manual_flat = (inputs or {}).get("manual_extraction")
        if manual_flat is not None:
            validate_legacy_extraction(manual_flat)
        if scorer is not None:
            impact = measure_score_impact(comparison, {"question": question, **binding},
                     scorer=scorer, scorer_id="cleareval-existing-formulas",
                     scorer_revision=json_hash(binding["formulas"]),
                     candidate_extraction=flat, manual_extraction=manual_flat,
                     frozen_score_paths=("completeness", "correctness"))
    candidate_diagnostics = _candidate_diagnostics(inputs, question, protocol)
    from experiments.construct_validity.answer_matching import unavailable_answer_matching
    matching = candidate_diagnostics.get("assessment", {}).get("answer_matching")
    if matching is None:
        matching = unavailable_answer_matching(text_hash(protocol))
    result = {"schema_version": VERSION, "technical_status": "VALID",
              "question_sha256": json_hash(question), "protocol_sha256": text_hash(protocol),
              "inputs_sha256": json_hash(inputs), "numeric_binding_sha256": json_hash(binding),
              "numerical_scores_sha256": json_hash(_scores(evaluation)),
              "flat_extraction_audit": fidelity, "fidelity_comparison": comparison,
              "quantity_scope_diagnostics": quantity_audit,
              "quantity_role_diagnostics": role_audit,
              "extraction_score_impact": impact,
              "candidate_diagnostics": candidate_diagnostics,
              "answer_matching_diagnostics": deepcopy(matching),
              "objective_diagnostics": _objective_diagnostics(inputs, question, protocol),
              "stability": {"status": "NOT_ESTIMATED_FROM_SINGLE_GRADE",
                            "independent_repeats": 0, "cross_family_comparison": None,
                            "analyzer": "oeq_score_stability.analyze_score_stability"},
              "policy": "EXISTING_NUMERICAL_SCORES_WITH_BOUND_ROBUSTNESS_DIAGNOSTICS",
              "imaging_results_evaluated": False, "scientific_accuracy": None}
    return result


def make_formula_scorer():
    """Replay the existing four formulas with teacher Com/Cor fixed."""
    def scorer(extraction, frozen_binding):
        from OEQ_run_grading_new import calculate_effectiveness_score
        validate_legacy_extraction(extraction)
        frozen = frozen_binding["context"]
        q = deepcopy(frozen["quantitative_data"])
        q["method_name"] = extraction["method_name"]
        q["total_time_hours"] = extraction["clearing_total_time_hours"]
        for key in ("method_stages", "reagent_ri_value", "protocol_time_hours"):
            q.pop(key, None)
            if key in extraction:
                q[key] = deepcopy(extraction[key])
        computed = calculate_effectiveness_score(q, frozen["user_preference_vector"], {},
                     extraction["marker_dict"], frozen["marker_query_targets"])
        scores = deepcopy(frozen["base_scores"])
        for key in ("s_method", "s_label", "s_trans", "s_time"):
            scores["effectiveness"][key]["score"] = computed[key]
        return scores
    return scorer


def attach_report(evaluation, question, protocol, inputs=None, *, marker_query_targets=None):
    result = deepcopy(evaluation)
    inputs = validate_bundle(inputs, question, protocol)
    binding = numeric_binding(evaluation, marker_query_targets)
    result.update(robustness_diagnostics_required=True,
                  robustness_original_input={"question": deepcopy(question), "protocol": protocol},
                  robustness_input_bundle=deepcopy(inputs), robustness_numeric_binding=binding)
    report = build_report(question, protocol, evaluation, inputs, binding=binding, scorer=make_formula_scorer())
    result.update(robustness_diagnostics=report, robustness_diagnostics_sha256=json_hash(report))
    return result


def is_report_complete(evaluation):
    try:
        if evaluation.get("robustness_diagnostics_required") is not True:
            return False
        original = evaluation["robustness_original_input"]
        if not isinstance(original, dict) or set(original) != {"question", "protocol"}:
            return False
        report = evaluation["robustness_diagnostics"]
        question, protocol = original["question"], original["protocol"]
        if not _numeric_input_matches(evaluation, question, protocol):
            return False
        inputs = validate_bundle(evaluation["robustness_input_bundle"], question, protocol)
        binding = evaluation["robustness_numeric_binding"]
        if (set(binding) != {"formulas", "knowledge_base", "context"}
                or set(binding["formulas"]) != {"OEQ_run_grading_new.py", "evaluation_contract.py", "results/oeq_metrics.py"}
                or set(binding["knowledge_base"]) != {
                    "dataset/Q+AR/src/model_space_signed.json", "KnowledgeBase/tissue.json",
                    "KnowledgeBase/method_fluro_compati.json", "KnowledgeBase/time_kb.json",
                    "KnowledgeBase/tissue_ri.json", "KnowledgeBase/method_sigma_ri.json",
                    "KnowledgeBase/method_ri_ref.json"}
                or binding["context"].get("base_scores") != _scores(evaluation)
                or binding["context"].get("quantitative_data") != evaluation.get("quantitative_data")
                or binding["context"].get("user_preference_vector") != evaluation.get("user_preference_vector")):
            return False
        if (report.get("schema_version") != VERSION or report.get("technical_status") != "VALID"
                or report.get("question_sha256") != json_hash(question)
                or report.get("protocol_sha256") != text_hash(protocol)
                or report.get("inputs_sha256") != json_hash(inputs)
                or report.get("numeric_binding_sha256") != json_hash(binding)
                or report.get("numerical_scores_sha256") != json_hash(_scores(evaluation))
                or evaluation["robustness_diagnostics_sha256"] != json_hash(report)):
            return False
        if any(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != h
               for group in ("formulas", "knowledge_base") for path,h in binding[group].items()):
            return False
        # Exact replay includes every status/null/policy field and the impact;
        # a forged status cannot choose which validation checks are skipped.
        rebuilt = build_report(question, protocol, evaluation, inputs, binding=binding,
                               scorer=make_formula_scorer())
        if rebuilt != report:
            return False
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError):
        return False


def sources_match_contract(evaluation, contract):
    try:
        if not is_report_complete(evaluation) or contract.get("robustness_diagnostics_required") is not True:
            return False
        source_hashes = contract["source_sha256"]
        binding = evaluation["robustness_numeric_binding"]
        return all(source_hashes.get(path) == h
                   for group in ("formulas", "knowledge_base") for path, h in binding[group].items())
    except (ValueError, TypeError, KeyError):
        return False


def summarize_reports(items, *, required=False):
    reports = []
    failures = []
    for index, item in enumerate(items):
        ev = item.get("evaluation") or {}
        if is_report_complete(ev):
            reports.append(ev["robustness_diagnostics"])
        elif required or ev.get("robustness_diagnostics_required"):
            failures.append({"index": index, "question_id": item.get("question_id"),
                             "reason": "ROBUSTNESS_REPORT_UNAVAILABLE_OR_INVALID"})
    return {"schema_version": VERSION, "required": required, "planned_records": len(items),
            "report_count": len(reports), "report_coverage": len(reports)/len(items) if items else 0,
            "failure_records": failures,
            "independent_fidelity_reference_count": sum(
                r["fidelity_comparison"].get("manual_audit", {}).get("reference_eligible") is True for r in reports),
            "independent_candidate_reference_count": sum(
                r["candidate_diagnostics"].get("independent_reference_count", 0) for r in reports),
            "independent_objective_relation_count": sum(
                r["objective_diagnostics"].get("independent_relation_count", 0) for r in reports),
            "answer_matching_contract_status_counts":dict(Counter(
                r["answer_matching_diagnostics"]["contract_status"] for r in reports)),
            "answers_with_global_necessary_failure":sum(bool(
                r["answer_matching_diagnostics"].get("global_necessary_failures")) for r in reports),
            "any_evaluated_candidate_status_counts":dict(Counter(
                r["answer_matching_diagnostics"]["any_evaluated_candidate_status"] for r in reports
                if r["answer_matching_diagnostics"].get("any_evaluated_candidate_status") is not None)),
            "all_evaluated_candidates_status_counts":dict(Counter(
                r["answer_matching_diagnostics"]["all_evaluated_candidates_status"] for r in reports
                if r["answer_matching_diagnostics"].get("all_evaluated_candidates_status") is not None)),
            "candidate_aggregate_answer_count":sum(
                r["answer_matching_diagnostics"].get("any_evaluated_candidate_status") is not None for r in reports),
            "quantity_source_record_count":sum(r["quantity_scope_diagnostics"]["record_count"] for r in reports),
            "answers_with_local_time_contradiction":sum(r["quantity_scope_diagnostics"]["contradicted_local_time_field_count"]>0 for r in reports),
            "quantity_role_input_answer_count":sum(r["quantity_role_diagnostics"]["status"]=="VALID_SOURCE_ROLE_AUDIT" for r in reports),
            "quantity_role_field_check_count":sum(r["quantity_role_diagnostics"]["field_check_count"] for r in reports),
            "quantity_role_status_counts":dict(sum((Counter(r["quantity_role_diagnostics"]["status_counts"]) for r in reports), Counter())),
            "answers_with_quantity_role_contradiction":sum(r["quantity_role_diagnostics"]["confirmed_contradiction_count"]>0 for r in reports),
            "matching_interpretation":"DECLARED_REQUIREMENT_CONTRACTS_NOT_SCIENTIFIC_ACCURACY",
            "new_model_queries": 0, "scientific_accuracy": None}
