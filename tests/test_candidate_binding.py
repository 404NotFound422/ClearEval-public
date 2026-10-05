"""Minimal synthetic complete-candidate regressions, never scientific labels."""
from copy import deepcopy
import unittest

from experiments.construct_validity.candidate_binding import audit_candidate_bindings, SCOPE
from experiments.construct_validity.contract import JUDGMENT_SCHEMA
from experiments.construct_validity.fidelity import SCHEMA
from experiments.construct_validity.task_state import propose_task_state, INITIAL_FIXATION
from oeq_scientific import apply_assessment, build_context
from tests.test_task_function_presence import span, support


def pipeline(*, b_action=False, shared_action=False):
    question = {"question": "Please include fixation in each complete alternative."}
    common = "Common declaration:\nChosen Method: FORMAL_METHOD\nPerform fixation.\n" if shared_action else ""
    a = "Choice A:\nChosen Method: FORMAL_METHOD\n"
    if not shared_action:
        a += "Perform fixation.\n"
    b = "Choice B:\nChosen Method: FORMAL_METHOD\n"
    if b_action:
        b += "Perform initial fixation.\n"
    b += "DECLARE_B.\n"
    protocol = common + a + b
    blocks = ([("main", "SERIAL", common)] if common else []) + [("a", "ALTERNATIVE", a), ("b", "ALTERNATIVE", b)]
    branches = [dict(id=rid, mode=mode, sample_id="same-opaque-key", spans=[span(protocol, block)])
                for rid, mode, block in blocks]
    global_req = next(r for r in propose_task_state(question)["requirements"]
                      if r["function"] == INITIAL_FIXATION)

    def local(route, token):
        return dict(id=route + "_complete", kind="TEXT", necessary=True, evidence_ids=[],
                    text="Declare " + token, scope="ROUTE", route_id=route,
                    literal_rule=dict(type="LITERAL_REQUIRED", text=token))

    requirements = [global_req, local("a", "DECLARE_A"), local("b", "DECLARE_B")]
    operations = [("main" if shared_action else "a", "Perform fixation")]
    if b_action:
        operations.append(("b", "Perform initial fixation"))
    operations.append(("b", "DECLARE_B"))
    steps = []
    for i, (branch, operation) in enumerate(operations):
        row = dict(id="s" + str(i), branch=branch, phase=None, operation=operation,
                   duration_text=None, quote=operation, assertion=dict(polarity="AFFIRMED"))
        row["field_support"] = {k: support(protocol, row[k]) for k in ("phase", "operation", "duration_text")}
        steps.append(row)
    extraction = dict(schema_version=SCHEMA, branches=branches, steps=steps, labels=[], ri=[],
                      limitations="Synthetic declaration fixture only.")
    context = build_context(question, protocol, study_context=dict(
        requirements=requirements, cards=[], method_keys=["FORMAL_METHOD"],
        route_methods={"a": "FORMAL_METHOD", "b": "FORMAL_METHOD"}, extraction_mode="literal_fields"))
    records = [dict(id=req["id"], status="SATISFIED", basis="PROTOCOL_TEXT", evidence_ids=[],
                    quotes=["Perform fixation" if req is global_req else "DECLARE_B"],
                    reason="Synthetic scope proposal.", evidence_checks=[]) for req in requirements]
    declarations = []
    for branch in branches:
        pos = protocol.index("FORMAL_METHOD", branch["spans"][0]["start"])
        declarations.append(dict(name="FORMAL_METHOD", branch=branch["id"],
                                 span=span(protocol, "FORMAL_METHOD", pos)))
    raw = dict(extraction=extraction, assessment=dict(schema_version=JUDGMENT_SCHEMA,
               requirements=records, limitations="Synthetic only."), objectives={},
               method_declarations=declarations)
    result = apply_assessment(raw, context, protocol)
    return context, raw, protocol, result


class CandidateBindingTests(unittest.TestCase):
    def test_a_action_plus_complete_b_never_forms_complete_candidate(self):
        context, raw, protocol, result = pipeline()
        self.assertEqual(result["overall"], "UNRESOLVED")
        self.assertEqual(result["objectives"]["constraints"]["complete_contract"], "UNRESOLVED")
        global_record = result["requirement_results"][0]
        self.assertEqual(global_record["effective_status"], "SATISFIED")
        self.assertEqual([e["branch"] for e in global_record["verification"]["action_evidence"]], ["a"])
        routes = {r["route_id"]: r for r in result["route_results"]}
        self.assertEqual(routes["b"]["declared_requirement_status"], "SATISFIED")
        self.assertEqual(routes["b"]["status"], "UNRESOLVED")
        self.assertEqual(routes["a"]["status"], "UNDER_SPECIFIED")
        audit = result["candidate_binding_audit"]
        self.assertEqual(audit["scope"], SCOPE)
        binding = audit["route_audits"][1]["global_support_bindings"][0]
        self.assertIn("NECESSARY_ACTION_NOT_BOUND_TO_THIS_CANDIDATE", binding["guards"])
        self.assertIsNone(audit["scientific_truth"])

    def test_action_within_complete_b_preserves_declared_candidate_satisfaction(self):
        _, _, _, result = pipeline(b_action=True)
        self.assertEqual(result["overall"], "SATISFIED")
        self.assertEqual(result["objectives"]["constraints"]["complete_contract"], "SATISFIED")
        route = next(r for r in result["route_results"] if r["route_id"] == "b")
        self.assertEqual(route["status"], "SATISFIED")
        self.assertEqual(route["candidate_binding_status"], "SATISFIED")
        audit = result["candidate_binding_audit"]["route_audits"][1]["global_support_bindings"][0]
        self.assertEqual([e["branch"] for e in audit["local_action_check"]["action_evidence"]], ["b"])
        self.assertIsNone(result["experimental_success_claim"])
        self.assertEqual(result["scientific_applicability_decision"]["status"], "UNRESOLVED")

    def test_main_serial_same_sample_key_is_not_a_shared_execution_dependency(self):
        _, _, _, result = pipeline(shared_action=True)
        self.assertEqual(result["overall"], "UNRESOLVED")
        self.assertEqual(result["objectives"]["constraints"]["complete_contract"], "UNRESOLVED")
        global_record = result["requirement_results"][0]
        self.assertEqual(global_record["effective_status"], "SATISFIED")
        self.assertEqual([e["branch"] for e in global_record["verification"]["action_evidence"]], ["main"])
        self.assertFalse(result["candidate_binding_audit"]["common_action_dependencies_supported"])
        self.assertFalse(result["candidate_binding_audit"]["complete_candidate_boundaries_certified"])

    def direct_inputs(self):
        context, raw, protocol, result = pipeline(b_action=True)
        return context["requirements"], result["requirement_results"], result["route_results"], protocol, raw["extraction"], result["extraction_fidelity"]

    def test_no_routes_preserves_existing_decision_without_upgrade(self):
        reqs, records, _, protocol, extraction, fidelity = self.direct_inputs()
        for status in ("UNRESOLVED", "UNDER_SPECIFIED", "VIOLATED", "SATISFIED"):
            checked = audit_candidate_bindings(reqs, records, [], status, protocol, extraction, fidelity)
            self.assertEqual(checked["overall"], status)
            self.assertEqual(checked["route_results"], [])
            self.assertEqual(checked["audit"]["status"], "NO_DECLARED_ROUTES_EXISTING_BEHAVIOR_PRESERVED")

    def test_necessary_global_science_without_reviewed_binding_is_unknown(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        reqs = deepcopy(reqs)
        reqs[0]["kind"] = "SCIENTIFIC"
        checked = audit_candidate_bindings(reqs, records, routes, "SATISFIED", protocol, extraction, fidelity)
        self.assertEqual(checked["overall"], "UNRESOLVED")
        for route in checked["audit"]["route_audits"]:
            self.assertIn("REVIEWED_SCIENTIFIC_CANDIDATE_BINDING_NOT_SUPPLIED", route["global_support_bindings"][0]["guards"])

    def test_other_global_binding_types_are_explicitly_unsupported(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        reqs = deepcopy(reqs)
        reqs[0]["literal_rule"] = dict(type="LITERAL_REQUIRED", text="Perform fixation")
        checked = audit_candidate_bindings(reqs, records, routes, "SATISFIED", protocol, extraction, fidelity)
        self.assertEqual(checked["overall"], "UNRESOLVED")
        self.assertIn("GLOBAL_REQUIREMENT_CANDIDATE_BINDING_TYPE_UNSUPPORTED",
                      checked["audit"]["route_audits"][1]["global_support_bindings"][0]["guards"])

    def test_missing_fidelity_cannot_authorize_candidate_binding(self):
        reqs, records, routes, protocol, extraction, _ = self.direct_inputs()
        checked = audit_candidate_bindings(reqs, records, routes, "SATISFIED", protocol, extraction)
        self.assertEqual(checked["overall"], "UNRESOLVED")
        self.assertIn("CANDIDATE_ACTION_FIDELITY_NOT_SUPPLIED",
                      checked["audit"]["route_audits"][1]["global_support_bindings"][0]["guards"])

    def test_not_required_applicability_does_not_claim_shared_action(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        reqs, records = deepcopy(reqs), deepcopy(records)
        reqs[0]["literal_rule"]["state_audit"].update(execution_obligation="NOT_REQUIRED", state="EXPLICITLY_DONE")
        from experiments.construct_validity.task_function_presence import assess_required_function
        records[0]["verification"] = assess_required_function(reqs[0]["literal_rule"], None, protocol, None)
        checked = audit_candidate_bindings(reqs, records, routes, "SATISFIED", protocol, extraction, fidelity)
        self.assertEqual(checked["overall"], "SATISFIED")
        self.assertFalse(checked["audit"]["common_action_dependencies_supported"])
        self.assertIn("TASK_APPLICABILITY_ONLY_NOT_SHARED_ACTION",
                      checked["audit"]["route_audits"][1]["global_support_bindings"][0]["guards"])

    def test_existing_non_satisfied_states_are_never_upgraded(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        for status in ("UNRESOLVED", "UNDER_SPECIFIED", "VIOLATED"):
            checked = audit_candidate_bindings(reqs, records, routes, status, protocol, extraction, fidelity)
            self.assertEqual(checked["overall"], status)
        changed = deepcopy(routes)
        changed[1]["status"] = "VIOLATED"
        checked = audit_candidate_bindings(reqs, records, changed, "UNRESOLVED", protocol, extraction, fidelity)
        self.assertEqual(checked["route_results"][1]["status"], "VIOLATED")

    def test_original_scopes_states_and_inputs_are_preserved(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        before = deepcopy((reqs, records, routes, extraction, fidelity))
        checked = audit_candidate_bindings(reqs, records, routes, "SATISFIED", protocol, extraction, fidelity)
        self.assertEqual((reqs, records, routes, extraction, fidelity), before)
        self.assertNotIn("scope", reqs[0])
        self.assertEqual(checked["audit"]["route_audits"][0]["global_support_bindings"][0]["original_scope"], "GLOBAL")

    def test_invalid_structural_inputs_fail_loudly(self):
        reqs, records, routes, protocol, extraction, fidelity = self.direct_inputs()
        with self.assertRaises(ValueError):
            audit_candidate_bindings(reqs, [], routes, "SATISFIED", protocol, extraction, fidelity)
        with self.assertRaises(ValueError):
            audit_candidate_bindings(reqs, records, routes + routes, "SATISFIED", protocol, extraction, fidelity)
        with self.assertRaises(ValueError):
            audit_candidate_bindings(reqs, records, routes, "UNKNOWN", protocol, extraction, fidelity)


if __name__ == "__main__":
    unittest.main()
