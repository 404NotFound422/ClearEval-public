"""Same-candidate necessary support; GLOBAL source predicates retain their meaning.

This is an additional candidate eligibility audit, not a scope migration, source
entailment checker or scientific certificate. No public/common execution
dependency is inferred from main/SERIAL, names, sample keys or GLOBAL quotes.
"""
from copy import deepcopy

from .contract import STATES, validate_requirements
from .fidelity import text_hash
from .requirement_scope import resolve_scope
from .task_function_presence import assess_required_function, VERSION as ACTION_VERSION

VERSION = "same-candidate-necessary-binding-v1"
SCOPE = "SAME_DECLARED_CANDIDATE_NECESSARY_SUPPORT_NOT_SCIENTIFIC_SUCCESS"


def audit_candidate_bindings(requirements, requirement_results, route_results,
                             overall, protocol, extraction, fidelity=None):
    """Conservatively bind necessary GLOBAL support to each declared route.

    Original requirement states/scopes are retained. Required function actions
    are checked anew in that route's exact source domain. NOT_REQUIRED task
    applicability can be common without claiming any shared action. Reviewed
    science/common dependency bindings are unsupported by this finite module.
    Missing bindings abstain; they never create VIOLATED. Existing non-SAT
    overall/route decisions are not upgraded. No-route behavior is preserved.
    """
    validate_requirements(requirements)
    if (not isinstance(protocol, str) or overall not in STATES
            or not isinstance(requirement_results, list)
            or not isinstance(route_results, list)):
        raise ValueError("Original protocol, four-state decisions and route arrays required")
    req_ids = {r["id"] for r in requirements}
    if (any(not isinstance(r, dict) for r in requirement_results)
            or len(requirement_results) != len(req_ids)
            or {r.get("id") for r in requirement_results} != req_ids
            or any(r.get("effective_status") not in STATES for r in requirement_results)):
        raise ValueError("Complete unique effective requirement records required")
    route_ids = [r.get("route_id") for r in route_results if isinstance(r, dict)]
    if (len(route_ids) != len(route_results) or len(route_ids) != len(set(route_ids))
            or any(not isinstance(rid, str) or not rid for rid in route_ids)
            or any(r.get("status") not in STATES for r in route_results)):
        raise ValueError("Unique declared four-state route results required")
    records = {r["id"]: r for r in requirement_results}
    globals_ = [r for r in requirements if r["necessary"] and r.get("scope", "GLOBAL") == "GLOBAL"]
    audit = dict(version=VERSION, scope=SCOPE, protocol_sha256=text_hash(protocol),
                 original_overall=overall, global_requirement_ids=[r["id"] for r in globals_],
                 route_audits=[], scientific_truth=None, common_action_dependencies_supported=False,
                 complete_candidate_boundaries_certified=False,
                 policy="NO_GLOBAL_A_ACTION_PLUS_B_ROUTE_NO_IMPLICIT_COMMON_DEPENDENCY")
    output_routes = deepcopy(route_results)
    if not output_routes:
        audit["status"] = "NO_DECLARED_ROUTES_EXISTING_BEHAVIOR_PRESERVED"
        return dict(overall=overall, route_results=output_routes, audit=audit)

    for route in output_routes:
        rid = route["route_id"]
        scope = resolve_scope(dict(scope="ROUTE", route_id=rid), extraction, protocol)
        bindings = []
        for req in globals_:
            record, rule = records[req["id"]], req.get("literal_rule")
            binding = dict(requirement_id=req["id"], original_scope="GLOBAL",
                           original_global_status=record["effective_status"],
                           support_status="UNRESOLVED", guards=[], scientific_truth=None)
            if record["effective_status"] != "SATISFIED":
                binding["guards"] = ["GLOBAL_NECESSARY_REQUIREMENT_NOT_SATISFIED"]
            elif req["kind"] == "SCIENTIFIC":
                binding["guards"] = ["REVIEWED_SCIENTIFIC_CANDIDATE_BINDING_NOT_SUPPLIED"]
            elif not isinstance(rule, dict) or rule.get("type") != "TASK_INITIAL_FUNCTION":
                binding["guards"] = ["GLOBAL_REQUIREMENT_CANDIDATE_BINDING_TYPE_UNSUPPORTED"]
            else:
                check = record.get("verification")
                if (not isinstance(check, dict) or check.get("version") != ACTION_VERSION
                        or check.get("status") != "SATISFIED"
                        or check.get("protocol_sha256") != text_hash(protocol)
                        or check.get("required_function") != rule.get("function")
                        or check.get("scientific_truth") is not None):
                    binding["guards"] = ["ORIGINAL_GLOBAL_FUNCTION_CHECK_UNVERIFIED"]
                elif (rule.get("state_audit", {}).get("execution_obligation") == "NOT_REQUIRED"
                      and check.get("applicability_only") is True
                      and check.get("action_presence_certified") is False):
                    binding.update(support_status="SATISFIED",
                                   guards=["TASK_APPLICABILITY_ONLY_NOT_SHARED_ACTION"])
                elif rule.get("state_audit", {}).get("execution_obligation") != "REQUIRED":
                    binding["guards"] = ["GLOBAL_FUNCTION_APPLICABILITY_UNRESOLVED"]
                elif scope["scope_status"] != "RESOLVED":
                    binding["guards"] = ["CANDIDATE_SOURCE_REGION_UNRESOLVED", *scope["guards"]]
                elif fidelity is None:
                    binding["guards"] = ["CANDIDATE_ACTION_FIDELITY_NOT_SUPPLIED"]
                else:
                    local = assess_required_function(rule, extraction, protocol, fidelity,
                                                     source_scope=scope, route_id=rid)
                    binding["local_action_check"] = local
                    if local["status"] == "SATISFIED" and local["action_presence_certified"] is True:
                        binding.update(support_status="SATISFIED", guards=[])
                    else:
                        binding["guards"] = ["NECESSARY_ACTION_NOT_BOUND_TO_THIS_CANDIDATE", *local["guards"]]
            bindings.append(binding)
        bound = all(b["support_status"] == "SATISFIED" for b in bindings)
        original = route["status"]
        # Explicit local failures retain their original meaning. Lack of a
        # binding only prevents a candidate SAT; it never creates a failure.
        if original == "SATISFIED" and not bound:
            route["status"] = "UNRESOLVED"
        route["declared_requirement_status"] = original
        route["candidate_binding_status"] = "SATISFIED" if bound else "UNRESOLVED"
        route["candidate_binding_guards"] = ([] if bound else ["NECESSARY_GLOBAL_SUPPORT_NOT_BOUND_TO_CANDIDATE"])
        audit["route_audits"].append(dict(route_id=rid, original_route_status=original,
            effective_candidate_status=route["status"], global_support_bindings=bindings,
            source_scope=scope, scientific_truth=None))
    final = overall
    if overall == "SATISFIED" and not any(r["status"] == "SATISFIED" for r in output_routes):
        final = "UNRESOLVED"
    audit.update(status="CHECKED", effective_overall=final)
    return dict(overall=final, route_results=output_routes, audit=audit)
