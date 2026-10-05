"""Formal source-scope controls, not scientific-plan or sample-entity gold."""
import unittest
from copy import deepcopy

from experiments.construct_validity.contract import validate_extraction
from experiments.construct_validity.fidelity import text_hash
from experiments.construct_validity.requirement_scope import (
    audit_requirement_quotes, resolve_scope, scope_contains_span,
)


def span(text, quote, start=None):
    start = text.index(quote) if start is None else start
    return dict(start=start, end=start + len(quote), quote=quote)


def fixture(first="blue", second="amber"):
    left = "## Choice " + first + "\nDECLARE_A\nSHARED\n\n"
    right = "## Choice " + second + "\nDECLARE_B\nSHARED\n"
    text = left + right
    raw = dict(schema_version="extraction-grounding-v2",
               branches=[
                   dict(id=first, mode="ALTERNATIVE", sample_id="declared-sample",
                        spans=[span(text, left, 0)]),
                   dict(id=second, mode="ALTERNATIVE", sample_id="declared-sample",
                        spans=[span(text, right, len(left))])],
               steps=[], labels=[], ri=[], limitations="")
    return text, raw, validate_extraction(raw, text, field_scope_policy="diagnostic")


def requirement(route=None, binding=None):
    req = dict(id="r", kind="TEXT", necessary=True, text="Formal declaration control", evidence_ids=[])
    if route is not None:
        req.update(scope="ROUTE", route_id=route)
    if binding is not None:
        req["literal_rule"] = dict(type="SOURCE_LITERAL_EQUALITY", protocol_binding=binding)
    return req


def record(*quotes, status="SATISFIED"):
    return dict(id="r", status=status, quotes=list(quotes))


class RequirementScopeTests(unittest.TestCase):
    def setUp(self):
        self.text, self.raw, self.validated = fixture()

    def scope(self, route="blue"):
        return resolve_scope(requirement(route), self.validated, self.text)

    def test_global_preserves_whole_protocol_domain_and_quote_compatibility(self):
        scope = resolve_scope(requirement(), None, self.text)
        self.assertEqual(scope["scope_status"], "RESOLVED")
        self.assertEqual(scope["regions"], [span(self.text, self.text, 0)])
        self.assertTrue(scope_contains_span(scope, span(self.text, "DECLARE_B"), self.text))
        audit = audit_requirement_quotes(record(self.text), scope, self.text)
        self.assertEqual(audit["status"], "RESOLVED")
        self.assertTrue(audit["has_local_decisive_anchor"])

    def test_empty_global_does_not_fabricate_an_empty_source_region(self):
        scope = resolve_scope(requirement(), None, "")
        self.assertEqual(scope["scope_status"], "RESOLVED")
        self.assertEqual(scope["regions"], [])

    def test_route_positive_retains_exact_full_original_region(self):
        scope = self.scope()
        self.assertEqual(scope["scope_status"], "RESOLVED")
        self.assertEqual(scope["route_id"], "blue")
        self.assertEqual(scope["protocol_sha256"], text_hash(self.text))
        self.assertEqual(scope["regions"], self.raw["branches"][0]["spans"])
        local = span(self.text, "DECLARE_A")
        self.assertTrue(scope_contains_span(scope, local, self.text))
        audit = audit_requirement_quotes(record("DECLARE_A"), scope, self.text)
        self.assertEqual(audit["status"], "RESOLVED")
        self.assertEqual(audit["quote_audits"][0]["source_span"], local)

    def test_cross_route_declaration_cannot_borrow_a_global_occurrence(self):
        scope = self.scope()
        other = span(self.text, "DECLARE_B")
        self.assertFalse(scope_contains_span(scope, other, self.text))
        audit = audit_requirement_quotes(record("DECLARE_B"), scope, self.text)
        self.assertEqual(audit["status"], "UNRESOLVED")
        self.assertFalse(audit["has_local_decisive_anchor"])
        self.assertEqual(audit["quote_audits"][0]["occurrences"], [other])
        self.assertEqual(audit["quote_audits"][0]["local_occurrences"], [])
        self.assertIsNone(audit["quote_audits"][0]["source_span"])

    def test_two_partial_routes_never_manufacture_four_local_declarations(self):
        # This is a source-location control only, never an oracle for a plan.
        for route, accepted, rejected in [("blue", "DECLARE_A", "DECLARE_B"),
                                          ("amber", "DECLARE_B", "DECLARE_A")]:
            with self.subTest(route=route):
                scope = self.scope(route)
                self.assertEqual(audit_requirement_quotes(record(accepted), scope, self.text)["status"], "RESOLVED")
                self.assertEqual(audit_requirement_quotes(record(rejected), scope, self.text)["status"], "UNRESOLVED")

    def test_repeated_quote_accepts_actual_local_occurrence_without_choosing_global_first(self):
        audit = audit_requirement_quotes(record("SHARED"), self.scope("amber"), self.text)
        quote = audit["quote_audits"][0]
        self.assertEqual(audit["status"], "RESOLVED")
        self.assertEqual(len(quote["occurrences"]), 2)
        self.assertEqual(len(quote["local_occurrences"]), 1)
        self.assertEqual(quote["source_span"]["start"], self.text.rindex("SHARED"))
        self.assertTrue(quote["ambiguous_location"])
        self.assertFalse(quote["ambiguous_local_location"])

    def test_repeated_local_occurrences_are_preserved_without_fake_single_span(self):
        text = "TOKEN TOKEN\nOTHER"
        raw = deepcopy(self.raw)
        raw["branches"] = [
            dict(id="blue", mode="ALTERNATIVE", sample_id="s", spans=[span(text, "TOKEN TOKEN")]),
            dict(id="amber", mode="ALTERNATIVE", sample_id="s", spans=[span(text, "OTHER")])]
        validated = validate_extraction(raw, text, field_scope_policy="diagnostic")
        scope = resolve_scope(requirement("blue"), validated, text)
        audit = audit_requirement_quotes(record("TOKEN"), scope, text)
        self.assertEqual(audit["status"], "RESOLVED")
        self.assertEqual(len(audit["quote_audits"][0]["local_occurrences"]), 2)
        self.assertIsNone(audit["quote_audits"][0]["source_span"])

    def test_whole_protocol_quote_is_not_a_decisive_route_anchor(self):
        audit = audit_requirement_quotes(record(self.text), self.scope(), self.text)
        self.assertEqual(audit["status"], "UNRESOLVED")
        self.assertFalse(audit["has_local_decisive_anchor"])
        self.assertIn("PROTOCOL_WIDE_QUOTATION_NOT_LOCAL", audit["guards"])

    def test_local_quote_does_not_sanitize_another_outside_quote(self):
        audit = audit_requirement_quotes(record("DECLARE_A", "DECLARE_B"), self.scope(), self.text)
        self.assertTrue(audit["has_local_decisive_anchor"])
        self.assertEqual(audit["status"], "UNRESOLVED")
        self.assertIn("QUOTATION_OUTSIDE_REQUIREMENT_SCOPE", audit["guards"])

    def test_missing_and_empty_quotes_retain_raw_values_without_invented_source(self):
        for quotes in [(), ("",), ("   ",), ("ABSENT",)]:
            with self.subTest(quotes=quotes):
                raw = record(*quotes)
                before = deepcopy(raw)
                audit = audit_requirement_quotes(raw, self.scope(), self.text)
                self.assertEqual(raw, before)
                self.assertEqual(audit["status"], "UNRESOLVED")
                self.assertFalse(audit["has_local_decisive_anchor"])
                for item in audit["quote_audits"]:
                    self.assertEqual(item["occurrences"], [])
                    self.assertIsNone(item["source_span"])

    def test_missing_route_and_route_id_abstain(self):
        for req in [requirement("missing"), dict(requirement("blue"), route_id="")]:
            with self.subTest(req=req):
                scope = resolve_scope(req, self.validated, self.text)
                self.assertEqual(scope["scope_status"], "UNRESOLVED")
                self.assertEqual(scope["regions"], [])
                self.assertFalse(scope_contains_span(scope, span(self.text, "DECLARE_A"), self.text))

    def test_empty_serial_branch_is_not_invented_into_a_route_region(self):
        raw = deepcopy(self.raw)
        raw["branches"] = [dict(id="main", mode="SERIAL", sample_id="s", spans=[])]
        validated = validate_extraction(raw, self.text, field_scope_policy="diagnostic")
        scope = resolve_scope(requirement("main"), validated, self.text)
        self.assertEqual(scope["scope_status"], "UNRESOLVED")
        self.assertEqual(scope["regions"], [])

    def test_ambiguous_branch_and_partial_resolution_abstain_without_fake_regions(self):
        raw = deepcopy(self.raw)
        raw["branches"][0]["spans"] = [span(self.text, "DECLARE_A"), {"quote": "SHARED"}]
        validated = validate_extraction(raw, self.text, field_scope_policy="diagnostic")
        self.assertEqual(validated["branches"][0]["location_status"], "REVIEW_REQUIRED")
        before = deepcopy(validated)
        scope = resolve_scope(requirement("blue"), validated, self.text)
        self.assertEqual(scope["scope_status"], "UNRESOLVED")
        self.assertEqual(scope["regions"], [])
        self.assertEqual(validated, before)
        audit = audit_requirement_quotes(record("DECLARE_A"), scope, self.text)
        self.assertEqual(audit["status"], "UNRESOLVED")
        self.assertEqual(audit["quote_audits"][0]["local_occurrences"], [])

    def test_resolved_empty_list_never_falls_back_to_original_spans(self):
        validated = deepcopy(self.validated)
        validated["branches"][0]["resolved_spans"] = []
        self.assertEqual(resolve_scope(requirement("blue"), validated, self.text)["scope_status"], "UNRESOLVED")

    def test_short_declaration_span_is_not_expanded_into_surrounding_route(self):
        raw = deepcopy(self.raw)
        raw["branches"][0]["spans"] = [{"quote": "Choice blue"}]
        validated = validate_extraction(raw, self.text, field_scope_policy="diagnostic")
        scope = resolve_scope(requirement("blue"), validated, self.text)
        self.assertEqual(scope["regions"], [span(self.text, "Choice blue")])
        self.assertFalse(scope_contains_span(scope, span(self.text, "DECLARE_A"), self.text))

    def test_strict_validated_spans_are_supported_without_diagnostic_metadata(self):
        validated = validate_extraction(self.raw, self.text)
        scope = resolve_scope(requirement("blue"), validated, self.text)
        self.assertEqual(scope["scope_status"], "RESOLVED")
        self.assertEqual(scope["regions"], self.raw["branches"][0]["spans"])

    def test_disjoint_regions_do_not_authorize_a_span_across_the_gap(self):
        raw = deepcopy(self.raw)
        raw["branches"][0]["spans"] = [span(self.text, "DECLARE_A"), span(self.text, "SHARED")]
        validated = validate_extraction(raw, self.text, field_scope_policy="diagnostic")
        scope = resolve_scope(requirement("blue"), validated, self.text)
        self.assertTrue(scope_contains_span(scope, span(self.text, "DECLARE_A"), self.text))
        self.assertFalse(scope_contains_span(scope, span(self.text, "DECLARE_A\nSHARED"), self.text))

    def test_binding_record_and_branch_conflicts_stay_unresolved(self):
        validated = deepcopy(self.validated)
        validated["steps"] = [dict(id="A", branch="blue"), dict(id="B", branch="amber")]
        bindings = [
            dict(collection="steps", record_id="B"),
            dict(collection="steps", record_id="A", branch="amber"),
        ]
        for binding in bindings:
            with self.subTest(binding=binding):
                scope = resolve_scope(requirement("blue", binding), validated, self.text)
                self.assertEqual(scope["scope_status"], "UNRESOLVED")
                self.assertIn("PROTOCOL_BINDING_ROUTE_CONFLICT", scope["guards"])
                self.assertFalse(scope_contains_span(scope, span(self.text, "DECLARE_A"), self.text))

    def test_binding_local_record_passes_but_other_region_span_does_not(self):
        validated = deepcopy(self.validated)
        validated["steps"] = [dict(id="A", branch="blue")]
        binding = dict(collection="steps", record_id="A", branch="blue", span=span(self.text, "DECLARE_A"))
        self.assertEqual(resolve_scope(requirement("blue", binding), validated, self.text)["scope_status"], "RESOLVED")
        binding["span"] = span(self.text, "DECLARE_B")
        scope = resolve_scope(requirement("blue", binding), validated, self.text)
        self.assertEqual(scope["scope_status"], "UNRESOLVED")
        self.assertIn("PROTOCOL_BINDING_OUTSIDE_REQUIREMENT_SCOPE", scope["guards"])

    def test_missing_or_ambiguous_record_binding_abstains(self):
        for rows in [[], [dict(id="A", branch="blue"), dict(id="A", branch="blue")]]:
            with self.subTest(rows=rows):
                validated = deepcopy(self.validated)
                validated["steps"] = rows
                scope = resolve_scope(requirement("blue", dict(collection="steps", record_id="A")), validated, self.text)
                self.assertEqual(scope["scope_status"], "UNRESOLVED")

    def test_route_names_can_change_without_changing_source_scope_behavior(self):
        observed = []
        for names in [("blue", "amber"), ("route_9", "route_2"), ("甲", "乙")]:
            text, raw, validated = fixture(*names)
            outcomes = []
            for route, token in zip(names, ["DECLARE_A", "DECLARE_B"]):
                scope = resolve_scope(requirement(route), validated, text)
                outcomes.append((scope["scope_status"],
                                 audit_requirement_quotes(record(token), scope, text)["status"],
                                 audit_requirement_quotes(record("SHARED"), scope, text)["status"]))
            observed.append(outcomes)
        self.assertEqual(observed, [observed[0]] * len(observed))

    def test_scope_does_not_certify_declared_sample_identity_or_scientific_truth(self):
        scope = self.scope()
        self.assertFalse(scope["sample_identity_certified"])
        self.assertIsNone(scope["scientific_truth"])
        self.assertIn("sample_id", scope["validation_scope"])
        self.assertIn("not certified", scope["validation_scope"])

    def test_protocol_hash_and_exact_unicode_offsets_are_required(self):
        scope = self.scope()
        local = span(self.text, "DECLARE_A")
        self.assertFalse(scope_contains_span(scope, local, self.text + "\n"))
        self.assertFalse(scope_contains_span(scope, dict(local, quote="changed"), self.text))
        self.assertFalse(scope_contains_span(scope, dict(local, start=True), self.text))
        validated = deepcopy(self.validated)
        validated["field_audit"]["protocol_sha256"] = "changed"
        self.assertEqual(resolve_scope(requirement("blue"), validated, self.text)["scope_status"], "UNRESOLVED")

    def test_unknown_scopes_and_nontext_quotes_remain_contract_errors(self):
        with self.assertRaises(ValueError):
            resolve_scope(dict(requirement(), scope="OTHER"), self.validated, self.text)
        with self.assertRaises(ValueError):
            audit_requirement_quotes(record(42), self.scope(), self.text)


if __name__ == "__main__":
    unittest.main()

