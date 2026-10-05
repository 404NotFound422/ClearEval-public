"""Declared requirement matching and necessary failures, separate from numeric means.

This module summarizes existing guarded decisions. It invents no source evidence,
scientific labels, alternative boundaries, or reference-text matching criteria.
"""
from copy import deepcopy
from .contract import (STATES, admissibility_formula, combine, evaluate_formula,
                       validate_requirements)

VERSION = "answer-requirement-matching-v2"


def unavailable_answer_matching(protocol_sha256):
    return dict(schema_version=VERSION, protocol_sha256=protocol_sha256,
                contract_status="UNRESOLVED", scope="DECLARED_REQUIREMENT_CONTRACT",
                reason="BOUND_STRUCTURED_REQUIREMENT_ASSESSMENT_NOT_SUPPLIED",
                global_necessary_failures=[], candidate_necessary_failures={},
                matched_declared_candidate_ids=[], requirement_decisions=None,
                any_evaluated_candidate_status=None, all_evaluated_candidates_status=None,
                all_recommended_candidates_status=None, consistency_audit=None,
                reference_text_similarity_used=False, scientific_accuracy=None,
                full_candidate_scientific_validation=None)


def summarize_answer_matching(requirements, records, route_results, overall, protocol_sha256,
                              *, requested_formula=None):
    validate_requirements(requirements)
    if overall not in STATES:
        raise ValueError("Guarded four-state overall decision required")
    ids={r["id"] for r in requirements}
    if (not isinstance(records,list) or len(records)!=len(ids)
            or any(not isinstance(r,dict) for r in records)
            or {r.get("id") for r in records}!=ids
            or any(r.get("effective_status") not in STATES for r in records)):
        raise ValueError("Complete unique guarded requirement results required")
    by_id={r["id"]:r for r in records}
    expected_routes={r["route_id"] for r in requirements
                     if r["necessary"] and r.get("scope","GLOBAL")=="ROUTE"}
    if (not isinstance(route_results,list) or len(route_results)!=len(expected_routes)
            or any(not isinstance(r,dict) for r in route_results)
            or {r.get("route_id") for r in route_results}!=expected_routes
            or any(r.get("status") not in STATES for r in route_results)):
        raise ValueError("Complete unique guarded candidate decisions required")
    states = {rid: record["effective_status"] for rid, record in by_id.items()}
    formula_status = evaluate_formula(admissibility_formula(requirements, requested_formula), states)
    # Identity/binding guards may lower SAT to unknown; extra restrictions may
    # reject a satisfied mandatory contract. Do not upgrade caller decisions.
    for route in route_results:
        local = [states[r["id"]] for r in requirements
                 if r["necessary"] and r.get("scope", "GLOBAL") == "ROUTE"
                 and r["route_id"] == route["route_id"]]
        if route["status"] == "SATISFIED" and combine(local) != "SATISFIED":
            raise ValueError("Candidate SAT contradicts its necessary requirement decisions")
    if overall == "SATISFIED" and (formula_status != "SATISFIED"
            or (route_results and not any(r["status"] == "SATISFIED" for r in route_results))):
        raise ValueError("Overall SAT contradicts the final formula or guarded candidates")
    global_states = [states[r["id"]] for r in requirements
                     if r["necessary"] and r.get("scope", "GLOBAL") == "GLOBAL"]
    global_status = combine(global_states) if global_states else "SATISFIED"
    candidate_decisions = [dict(route_id=r["route_id"], status=r["status"],
        global_and_candidate_necessary_status=combine([global_status, r["status"]]))
        for r in route_results]
    candidate_states = [r["global_and_candidate_necessary_status"] for r in candidate_decisions]
    decisions=[]
    for req in requirements:
        record=by_id[req["id"]]
        decisions.append(dict(id=req["id"],necessary=req["necessary"],
            scope=req.get("scope","GLOBAL"),route_id=req.get("route_id"),
            status=record["effective_status"],guards=deepcopy(record.get("guards",[]))))
    global_failures=[r["id"] for r in decisions
                     if r["necessary"] and r["scope"]=="GLOBAL" and r["status"]=="VIOLATED"]
    candidate_failures={rid:[r["id"] for r in decisions
                            if r["necessary"] and r["route_id"]==rid and r["status"]=="VIOLATED"]
                        for rid in sorted(expected_routes)}
    return dict(schema_version=VERSION,protocol_sha256=protocol_sha256,
        contract_status=overall,scope="DECLARED_REQUIREMENT_CONTRACT",
        global_necessary_failures=global_failures,
        candidate_necessary_failures=candidate_failures,
        matched_declared_candidate_ids=[r["route_id"] for r in candidate_decisions
            if r["global_and_candidate_necessary_status"] == "SATISFIED"],
        locally_satisfied_declared_candidate_ids=[r["route_id"] for r in route_results
            if r["status"] == "SATISFIED"],
        candidate_decisions=candidate_decisions,
        global_necessary_status=global_status,
        any_evaluated_candidate_status=combine(candidate_states, "any") if candidate_states else None,
        all_evaluated_candidates_status=combine(candidate_states) if candidate_states else None,
        all_recommended_candidates_status=None,
        candidate_aggregate_scope="NECESSARY_REQUIREMENTS_AND_GUARDED_DECLARED_CANDIDATES_ONLY",
        candidate_roles_certified=False,
        additional_answer_restrictions_in_contract_status=True,
        consistency_audit=dict(formula_status_before_candidate_guards=formula_status,
            positive_claims_checked=True, negative_or_unknown_caller_decisions_recomputed=False,
            scientific_truth_authenticated=False),
        pending_necessary_requirement_ids=[r["id"] for r in decisions
            if r["necessary"] and r["status"] in {"UNDER_SPECIFIED","UNRESOLVED"}],
        optional_requirement_failures=[r["id"] for r in decisions
            if not r["necessary"] and r["status"]=="VIOLATED"],
        requirement_decisions=decisions,
        policy="GLOBAL_HARD_FAILURE_BLOCKS_ALL;ALTERNATIVE_FAILURE_STAYS_LOCAL;UNKNOWN_IS_NOT_DETECTED_ERROR",
        numerical_mean_overrides_failure=False,reference_text_similarity_used=False,
        scientific_accuracy=None,full_candidate_scientific_validation=None)
