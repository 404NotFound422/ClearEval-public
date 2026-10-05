"""Synthetic declaration/source-boundary checks: no model, labels or network."""
from copy import deepcopy
import unittest

from experiments.construct_validity.contract import validate_extraction
from experiments.construct_validity.fidelity import SCHEMA, text_hash
from experiments.construct_validity.requirement_scope import resolve_scope
from experiments.construct_validity.task_function_presence import assess_required_function, SCOPE
from experiments.construct_validity.task_state import (
    INITIAL_FIXATION as FIX, MEMBRANE_LABEL_DIFFUSION as DIFF,
    PRE_CLEARING_INITIAL_LABEL_QC as QC, LYMPHOCYTE_T_B_DISCRIMINATION as TB,
)


def span(text, quote, start=None):
    start = text.index(quote) if start is None else start
    return dict(start=start, end=start + len(quote), quote=quote)


def support(text, value):
    if value is None:
        return dict(kind="MISSING", raw_value=None, spans=[])
    return dict(kind="EXPLICIT", raw_value=value, transform="IDENTITY",
                spans=[span(text, value)])


def fixture(text="Perform fixation.", operations=None, polarities=None, branches=None):
    operations = [text.rstrip(".")] if operations is None else operations
    polarities = ["AFFIRMED"] * len(operations) if polarities is None else polarities
    branches = [dict(id="main", mode="SERIAL", sample_id="sample", spans=[])] if branches is None else branches
    rows = []
    for i, (operation, polarity) in enumerate(zip(operations, polarities)):
        branch = branches[min(i, len(branches) - 1)]["id"]
        row = dict(id="s" + str(i), branch=branch, phase=None, operation=operation,
                   duration_text=None, quote=operation, assertion=dict(polarity=polarity))
        row["field_support"] = {key: support(text, row[key]) for key in ("phase", "operation", "duration_text")}
        rows.append(row)
    raw = dict(schema_version=SCHEMA, branches=branches, steps=rows, labels=[], ri=[],
               limitations="Synthetic declaration fixture; not scientific evidence.")
    validated = validate_extraction(raw, text, field_scope_policy="diagnostic")
    return validated, validated["field_audit"]


def rule(function=FIX, obligation="REQUIRED", state="UNKNOWN"):
    return dict(type="TASK_INITIAL_FUNCTION", function=function,
                state_audit=dict(function=function, execution_obligation=obligation, state=state))


class TaskFunctionPresenceTests(unittest.TestCase):
    def assess(self, text="Perform fixation.", function=FIX, **kwargs):
        extraction, fidelity = fixture(text)
        result = assess_required_function(rule(function), extraction, text, fidelity, **kwargs)
        self.assertEqual(result["scope"], SCOPE)
        self.assertIsNone(result["scientific_truth"])
        self.assertNotEqual(result["status"], "VIOLATED")
        return result

    def test_explicit_english_and_chinese_actions(self):
        cases = [
            (FIX, "Perform fixation."), (FIX, "Fix the sample."),
            (FIX, "进行固定。"), (FIX, "安排初始固定。"),
            (DIFF, "Include membrane-label diffusion."), (DIFF, "进行膜内扩散。"),
            (QC, "Perform independent label QC."), (QC, "进行独立标记质控。"),
            (FIX, "Fixation will be performed."),
        ]
        for function, text in cases:
            with self.subTest(text=text):
                result = self.assess(text, function)
                self.assertEqual(result["status"], "SATISFIED")
                self.assertTrue(result["action_presence_certified"])
                anchor = result["action_evidence"][0]["action_span"]
                self.assertEqual(text[anchor["start"]:anchor["end"]], anchor["quote"])

    def test_nominal_mentions_do_not_certify_actions(self):
        for text in ("Fixation is important.", "Discuss fixation.", "Mention perform fixation.",
                     "Example: perform fixation.", "Initial label QC.", "Consider fixation."):
            with self.subTest(text=text):
                self.assertEqual(self.assess(text, QC if text.startswith("Initial") else FIX)["status"], "UNRESOLVED")

    def test_explicit_refusal_is_unknown_not_violated(self):
        for text in ("Do not perform fixation.", "Refuse to perform fixation.", "Omit fixation.",
                     "不进行固定。", "本方案不纳入固定。"):
            with self.subTest(text=text):
                self.assertEqual(self.assess(text)["status"], "UNRESOLVED")

    def test_conditional_or_unknown_context_remains_unknown(self):
        for text in ("If needed, perform fixation.", "If needed:\nPerform fixation.",
                     "Perform fixation when needed.", "May perform fixation.",
                     "Unknown scope: perform fixation.", "若有需要，进行固定。"):
            with self.subTest(text=text):
                self.assertEqual(self.assess(text)["status"], "UNRESOLVED")

    def test_short_span_cannot_hide_condition_outside_requirement_region(self):
        text = "If needed, perform fixation."
        extraction, fidelity = fixture(text, ["perform fixation"])
        scope = dict(scope="GLOBAL", scope_status="RESOLVED", route_id=None,
                     protocol_sha256=text_hash(text), regions=[span(text, "perform fixation")])
        result = assess_required_function(rule(), extraction, text, fidelity, source_scope=scope)
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_assertion_polarities_are_preserved(self):
        for polarity in ("NEGATED", "CONDITIONAL"):
            extraction, fidelity = fixture(polarities=[polarity])
            self.assertEqual(assess_required_function(rule(), extraction, "Perform fixation.", fidelity)["status"], "UNRESOLVED")

    def test_no_operations_is_under_specified_not_scientific_omission(self):
        text = "A description."
        extraction, fidelity = fixture(text, [])
        result = assess_required_function(rule(), extraction, text, fidelity)
        self.assertEqual(result["status"], "UNDER_SPECIFIED")
        self.assertIn("NOT_COMPLETENESS_PROOF", result["coverage"])
        self.assertFalse(result["action_presence_certified"])

    def test_unsupported_vocabulary_never_becomes_violation(self):
        self.assertEqual(self.assess("Undertake an initial stabilization.")["status"], "UNRESOLVED")
        extraction, fidelity = fixture()
        result = assess_required_function(rule("UNSUPPORTED_FUNCTION"), extraction, "Perform fixation.", fidelity)
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_required_goal_is_never_literal_certified(self):
        self.assertEqual(self.assess("Perform T/B cell discrimination.", TB)["status"], "UNRESOLVED")

    def test_not_required_is_applicability_only_and_allows_repeat(self):
        extraction, fidelity = fixture()
        for function in (FIX, TB):
            result = assess_required_function(rule(function, "NOT_REQUIRED", "EXPLICITLY_DONE"),
                                             extraction, "Perform fixation.", fidelity)
            self.assertEqual(result["status"], "SATISFIED")
            self.assertTrue(result["applicability_only"])
            self.assertFalse(result["action_presence_certified"])
            self.assertFalse(result["repetition_prohibited"])

    def test_unresolved_task_obligation_cannot_be_rescued_by_action(self):
        extraction, fidelity = fixture()
        for current in (rule(obligation="UNRESOLVED"), rule(state="CONDITIONAL"), rule(state="CONFLICTING")):
            self.assertEqual(assess_required_function(current, extraction, "Perform fixation.", fidelity)["status"], "UNRESOLVED")

    def test_task_function_or_metadata_conflict_abstains(self):
        extraction, fidelity = fixture()
        current = rule()
        current["state_audit"]["function"] = QC
        self.assertEqual(assess_required_function(current, extraction, "Perform fixation.", fidelity)["status"], "UNRESOLVED")
        current = rule()
        current["state_audit"]["metadata_conflict"] = True
        self.assertEqual(assess_required_function(current, extraction, "Perform fixation.", fidelity)["status"], "UNRESOLVED")

    def test_legacy_extraction_is_never_adapted(self):
        extraction = dict(steps=[dict(operation="Perform fixation")])
        result = assess_required_function(rule(), extraction, "Perform fixation.", dict(facts=[]))
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertIn("LEGACY_OR_UNVERIFIED_EXTRACTION", result["guards"])

    def test_wrong_protocol_hash_and_malformed_fidelity_abstain(self):
        extraction, fidelity = fixture()
        for field, value in (("protocol_sha256", "bad"), ("facts", None), ("issues", None)):
            bad = deepcopy(fidelity)
            bad[field] = value
            self.assertEqual(assess_required_function(rule(), extraction, "Perform fixation.", bad)["status"], "UNRESOLVED")

    def test_bad_field_fidelity_and_local_issues_abstain(self):
        extraction, fidelity = fixture()
        for change in ("status", "kind", "issue"):
            bad = deepcopy(fidelity)
            operation = bad["facts"][0]["fields"]["operation"]
            if change == "status":
                operation["status"] = "REVIEW_REQUIRED"
            elif change == "kind":
                operation["kind"] = "INFERRED"
            else:
                bad["issues"].append(dict(collection="steps", index=0, field="operation", code="SOURCE_OPERATION_ORDER_CHANGED"))
            self.assertEqual(assess_required_function(rule(), extraction, "Perform fixation.", bad)["status"], "UNRESOLVED")

    def test_forged_audit_cannot_bypass_original_field_support(self):
        extraction, fidelity = fixture()
        for change in ("value", "span", "raw_value", "assertion", "index"):
            bad_extraction, bad_fidelity = deepcopy(extraction), deepcopy(fidelity)
            if change == "value":
                bad_extraction["steps"][0]["operation"] = "Perform independent label QC"
            elif change == "span":
                bad_extraction["steps"][0]["field_support"]["operation"]["spans"][0]["quote"] = "bad"
            elif change == "raw_value":
                bad_fidelity["facts"][0]["fields"]["operation"]["raw_value"] = "bad"
            elif change == "assertion":
                bad_extraction["steps"][0]["assertion"]["polarity"] = "NEGATED"
            else:
                bad_fidelity["facts"][0]["index"] = True
            self.assertEqual(assess_required_function(rule(), bad_extraction, "Perform fixation.", bad_fidelity)["status"], "UNRESOLVED")

    def test_bad_audited_exact_span_abstains(self):
        extraction, fidelity = fixture()
        for key, value in (("start", True), ("start", 999), ("quote", "bad")):
            bad = deepcopy(fidelity)
            bad["facts"][0]["fields"]["operation"]["spans"][0][key] = value
            self.assertEqual(assess_required_function(rule(), extraction, "Perform fixation.", bad)["status"], "UNRESOLVED")

    def test_invalid_scope_hash_bounds_status_and_route_abstain(self):
        text = "Perform fixation."
        extraction, fidelity = fixture(text)
        scope = resolve_scope({}, extraction, text)
        for key, value in (("protocol_sha256", "bad"), ("scope_status", "UNRESOLVED"), ("regions", None), ("scope", "UNKNOWN")):
            bad = deepcopy(scope)
            bad[key] = value
            self.assertEqual(assess_required_function(rule(), extraction, text, fidelity, bad)["status"], "UNRESOLVED")
        bad = deepcopy(scope)
        bad["regions"][0]["start"] = True
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity, bad)["status"], "UNRESOLVED")
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity, scope, "other")["status"], "UNRESOLVED")

    def route_fixture(self):
        left, right = "Choice A:\nDiscuss fixation.\n", "Choice B:\nPerform fixation."
        text = left + right
        branches = [
            dict(id="a", mode="ALTERNATIVE", sample_id="s", spans=[span(text, left)]),
            dict(id="b", mode="ALTERNATIVE", sample_id="s", spans=[span(text, right)]),
        ]
        extraction, fidelity = fixture(text, ["Discuss fixation", "Perform fixation"], branches=branches)
        return text, extraction, fidelity

    def test_other_route_cannot_supply_action(self):
        text, extraction, fidelity = self.route_fixture()
        scope = resolve_scope(dict(scope="ROUTE", route_id="a"), extraction, text)
        result = assess_required_function(rule(), extraction, text, fidelity, scope, "a")
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertFalse(result["action_presence_certified"])

    def test_local_route_positive_ignores_other_route_nominal_mention(self):
        text, extraction, fidelity = self.route_fixture()
        scope = resolve_scope(dict(scope="ROUTE", route_id="b"), extraction, text)
        result = assess_required_function(rule(), extraction, text, fidelity, scope, "b")
        self.assertEqual(result["status"], "SATISFIED")
        self.assertEqual(result["action_evidence"][0]["branch"], "b")

    def test_route_id_without_scope_resolves_only_declared_regions(self):
        text, extraction, fidelity = self.route_fixture()
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity, route_id="b")["status"], "SATISFIED")
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity, route_id="missing")["status"], "UNRESOLVED")

    def test_partial_region_cannot_extend_to_later_action(self):
        text, extraction, fidelity = self.route_fixture()
        scope = resolve_scope(dict(scope="ROUTE", route_id="b"), extraction, text)
        scope["regions"] = [span(text, "Choice B:")]
        result = assess_required_function(rule(), extraction, text, fidelity, scope, "b")
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_disjoint_spans_cannot_manufacture_an_action(self):
        text = "Perform rinsing. Fixation is discussed."
        extraction, fidelity = fixture(text, ["Fixation"])
        support = extraction["steps"][0]["field_support"]["operation"]
        support["spans"] = [span(text, "Perform"), span(text, "Fixation")]
        operation = fidelity["facts"][0]["fields"]["operation"]
        # Supplying independently real fragments cannot create 'perform fixation'.
        operation["spans"] = [span(text, "Perform"), span(text, "Fixation")]
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity)["status"], "UNRESOLVED")

    def test_positive_plus_refusal_remains_unknown(self):
        text = "Perform fixation. Do not perform fixation."
        extraction, fidelity = fixture(text, ["Perform fixation", "Do not perform fixation"],
                                      polarities=["AFFIRMED", "NEGATED"])
        result = assess_required_function(rule(), extraction, text, fidelity)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertFalse(result["action_presence_certified"])

    def test_whole_support_span_cannot_borrow_unrelated_operation(self):
        text = "Perform fixation and rinsing."
        extraction, fidelity = fixture(text, ["rinsing"])
        self.assertEqual(assess_required_function(rule(), extraction, text, fidelity)["status"], "UNRESOLVED")


    def test_governing_heading_survives_numbered_steps_and_sentence_breaks(self):
        for heading in ("If needed:", "If needed", "Unknown scope:", "Excluded actions:", "Literature example:"):
            text = heading + "\nStep 1. Perform fixation."
            extraction, fidelity = fixture(text, ["Perform fixation"])
            result = assess_required_function(rule(), extraction, text, fidelity)
            self.assertEqual(result["status"], "UNRESOLVED", heading)
            self.assertIn("FUNCTION_SOURCE_HEADING_SCOPE_UNRESOLVED", result["guards"])
            self.assertFalse(result["action_presence_certified"])
            self.assertTrue(result["context_review_spans"])

    def test_clipped_route_region_cannot_hide_governing_heading(self):
        text = "If needed:\nChoice A:\nStep 1. Perform fixation."
        branch_text = "Choice A:\nStep 1. Perform fixation."
        branches = [dict(id="a", mode="SERIAL", sample_id="s", spans=[span(text, branch_text)])]
        extraction, fidelity = fixture(text, ["Perform fixation"], branches=branches)
        scope = resolve_scope(dict(scope="ROUTE", route_id="a"), extraction, text)
        result = assess_required_function(rule(), extraction, text, fidelity, scope, "a")
        self.assertEqual(result["status"], "UNRESOLVED")

    def test_quoted_and_reference_occurrences_never_certify_current_action(self):
        for text in ('The phrase "Perform fixation" appears.', "The heading says perform fixation.",
                     'Source recommendation: perform fixation.', "'Perform fixation'"):
            with self.subTest(text=text):
                self.assertEqual(self.assess(text)["status"], "UNRESOLVED")

    def test_original_refusal_omitted_from_extraction_still_blocks_credit(self):
        text = "Perform fixation. Do not perform fixation."
        extraction, fidelity = fixture(text, ["Perform fixation"])
        result = assess_required_function(rule(), extraction, text, fidelity)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertIn("FUNCTION_EXPLICIT_SOURCE_REFUSAL_REQUIRES_REVIEW", result["guards"])
        self.assertFalse(result["action_presence_certified"])

    def test_other_function_refusal_does_not_block_local_action(self):
        text = "Do not perform independent label QC; perform fixation."
        extraction, fidelity = fixture(text, ["perform fixation"])
        result = assess_required_function(rule(), extraction, text, fidelity)
        self.assertEqual(result["status"], "SATISFIED")

    def test_inputs_preserved_and_result_deterministic(self):
        extraction, fidelity = fixture()
        current = rule()
        before = deepcopy((current, extraction, fidelity))
        a = assess_required_function(current, extraction, "Perform fixation.", fidelity)
        b = assess_required_function(current, extraction, "Perform fixation.", fidelity)
        self.assertEqual(a, b)
        self.assertEqual((current, extraction, fidelity), before)

    def test_invalid_rule_or_protocol_types_raise(self):
        extraction, fidelity = fixture()
        for current in (None, {}, dict(type="OTHER"), dict(type="TASK_INITIAL_FUNCTION")):
            with self.assertRaises(ValueError):
                assess_required_function(current, extraction, "Perform fixation.", fidelity)
        with self.assertRaises(ValueError):
            assess_required_function(rule(), extraction, None, fidelity)


if __name__ == "__main__":
    unittest.main()
