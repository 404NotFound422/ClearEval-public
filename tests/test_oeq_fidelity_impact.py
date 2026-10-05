"""Synthetic, offline tests for OEQ extraction fidelity and score impact."""
from copy import deepcopy
import json
import unittest

from evaluation_contract import json_hash
from experiments.construct_validity.fidelity import text_hash
from oeq_fidelity_impact import (
    INVENTORY_SCHEMA, audit_inventory, compare_inventories,
    evaluate_fidelity_impact, measure_score_impact, parse_candidate_json,
)


def span(text, quote, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(quote, start + 1)
    return {"start": start, "end": start + len(quote), "quote": quote}


def support(text, raw, transform="IDENTITY", occurrence=0):
    return {"kind": "EXPLICIT", "spans": [span(text, raw, occurrence)],
            "context_span": {"start": 0, "end": len(text), "quote": text},
            "raw_value": raw, "transform": transform}


def reported(path, value, kind, support_value, **metadata):
    result = {"path": path, "state": "REPORTED", "value": value,
              "value_kind": kind, "support": support_value}
    result.update(metadata)
    return result


def missing(path, kind="NUMBER"):
    return {"path": path, "state": "EXPLICIT_NULL", "value": None,
            "value_kind": kind, "support": {"kind": "MISSING"}}


def inventory(text, facts, *, role="CANDIDATE_EXTRACTION", scope=None,
              independence=None, assistance=None, record_id="fixture"):
    if independence is None:
        independence = "INDEPENDENT" if role == "MANUAL_REFERENCE" else "NOT_APPLICABLE"
    if assistance is None:
        assistance = []
    return {"schema_version": INVENTORY_SCHEMA,
            "original_text_sha256": text_hash(text),
            "field_scope": scope if scope is not None else [fact["path"] for fact in facts],
            "provenance": {"record_id": record_id, "role": role,
                           "independence": independence, "assistance": assistance},
            "facts": facts}


class StrictParsingAndAuditTests(unittest.TestCase):
    def setUp(self):
        self.text = "Use CUBIC for clearing for 24 h with Alexa 647."
        self.method = reported("/method_name", "CUBIC", "ENTITY", support(self.text, "CUBIC"))
        self.time = reported("/clearing_total_time_hours", 24, "NUMBER",
                             support(self.text, "24 h", "TIME_TO_HOURS"), unit="h")
        self.marker = reported("/marker_dict/Alexa 647/@key", "Alexa 647", "ENTITY",
                               support(self.text, "Alexa 647"))

    def test_strict_json_failure_is_distinct_from_null_and_not_reported(self):
        bad = parse_candidate_json('{"schema_version":1,"schema_version":2}')
        self.assertEqual(bad["status"], "PARSE_FAILURE")
        candidate = inventory(self.text, [missing("/sample_ri_value")],
                              scope=["/sample_ri_value", "/reagent_ri_value"])
        audited = audit_inventory(self.text, candidate, role="CANDIDATE_EXTRACTION")
        self.assertEqual(audited["field_states"]["/sample_ri_value"], "EXPLICIT_NULL")
        self.assertEqual(audited["field_states"]["/reagent_ri_value"], "NOT_REPORTED")

    def test_altered_original_span_entity_and_numeric_are_unfaithful(self):
        cases = []
        altered_span = deepcopy(self.method)
        altered_span["support"]["spans"][0]["start"] += 1
        cases.append(altered_span)
        altered_entity = deepcopy(self.method)
        altered_entity["value"] = "PEGASOS"
        cases.append(altered_entity)
        altered_number = deepcopy(self.time)
        altered_number["value"] = 25
        cases.append(altered_number)
        for fact in cases:
            with self.subTest(path=fact["path"], value=fact["value"]):
                audited = audit_inventory(self.text, inventory(self.text, [fact]),
                                          role="CANDIDATE_EXTRACTION")
                self.assertEqual(audited["status"], "UNFAITHFUL")
                self.assertEqual(audited["fact_audits"][0]["status"], "UNFAITHFUL")

    def test_unit_must_be_bound_to_the_same_numeric_source(self):
        altered = deepcopy(self.time)
        altered["unit"] = "min"
        audited = audit_inventory(self.text, inventory(self.text, [altered]),
                                  role="CANDIDATE_EXTRACTION")
        self.assertEqual(audited["status"], "UNFAITHFUL")
        self.assertIn(".unit", audited["issues"][0]["detail"])


class IndependentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.text = "Use CUBIC for clearing for 24 h; no sample RI is reported."
        self.method = reported("/method_name", "CUBIC", "ENTITY", support(self.text, "CUBIC"))
        self.time = reported("/clearing_total_time_hours", 24, "NUMBER",
                             support(self.text, "24 h", "TIME_TO_HOURS"), unit="h")
        self.ri_missing = missing("/sample_ri_value")
        self.scope = ["/method_name", "/clearing_total_time_hours", "/sample_ri_value"]

    def test_omission_and_extra_are_separate(self):
        manual = inventory(self.text, [self.method, self.time, self.ri_missing],
                           role="MANUAL_REFERENCE", scope=self.scope)
        claimed_ri = reported("/sample_ri_value", 1.45, "NUMBER",
                              support(self.text, "24", "NUMBER"))
        candidate = inventory(self.text, [self.time, claimed_ri], scope=self.scope)
        result = compare_inventories(self.text, candidate, manual)
        outcomes = {row["path"]: row["outcome"] for row in result["fields"]}
        self.assertEqual(outcomes["/method_name"], "OMISSION")
        self.assertEqual(outcomes["/sample_ri_value"], "EXTRA")
        self.assertEqual(result["extraction_agreement"], "DISAGREEMENT")
        self.assertIsNone(result["scientific_accuracy"])

    def test_missing_or_assisted_manual_reference_is_unavailable(self):
        candidate = inventory(self.text, [self.method, self.time], scope=self.scope)
        absent = compare_inventories(self.text, candidate, None)
        self.assertEqual(absent["status"], "UNAVAILABLE")
        self.assertEqual(absent["manual_audit"]["status"], "ABSENT")
        assisted = inventory(self.text, [self.method, self.time, self.ri_missing],
                             role="MANUAL_REFERENCE", scope=self.scope,
                             independence="ASSISTED", assistance=["candidate output shown"])
        compared = compare_inventories(self.text, candidate, assisted)
        self.assertEqual(compared["status"], "UNAVAILABLE")
        self.assertFalse(compared["manual_audit"]["reference_eligible"])
        self.assertEqual(compared["manual_audit"]["reference_status"], "ASSISTED_REFERENCE")

    def test_independent_annotation_with_unresolved_fact_is_not_a_usable_reference(self):
        text = "Apply CUBIC."
        fact = reported("/method_name", "CUBIC", "ENTITY", support(text, "CUBIC"),
                        scope="invented route")
        candidate = inventory(text, [fact])
        manual = inventory(text, [fact], role="MANUAL_REFERENCE")
        audited = audit_inventory(text, manual, role="MANUAL_REFERENCE")
        self.assertEqual(audited["status"], "UNRESOLVED")
        self.assertTrue(audited["annotation_independent"])
        self.assertFalse(audited["factually_resolved"])
        self.assertFalse(audited["reference_eligible"])
        self.assertEqual(audited["reference_status"], "INDEPENDENT_REFERENCE_UNRESOLVED")
        compared = compare_inventories(text, candidate, manual)
        self.assertEqual(compared["status"], "UNAVAILABLE")
        self.assertIsNone(compared["extraction_agreement"])

    def test_candidate_parse_failure_is_not_manual_absence(self):
        manual = inventory(self.text, [self.method, self.time, self.ri_missing],
                           role="MANUAL_REFERENCE", scope=self.scope)
        result = compare_inventories(self.text, "{broken", manual)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["candidate_audit"]["status"], "PARSE_FAILURE")
        self.assertTrue(result["manual_audit"]["reference_eligible"])


class ScoreImpactTests(unittest.TestCase):
    def setUp(self):
        self.text = "Use CUBIC. Clearing step: 24 h. Total protocol: 48 h."
        method = reported("/method_name", "CUBIC", "ENTITY", support(self.text, "CUBIC"))
        candidate_time = reported("/clearing_total_time_hours", 24, "NUMBER",
                                  support(self.text, "24 h", "TIME_TO_HOURS"), unit="h")
        manual_time = reported("/clearing_total_time_hours", 48, "NUMBER",
                               support(self.text, "48 h", "TIME_TO_HOURS"), unit="h")
        scope = ["/method_name", "/clearing_total_time_hours"]
        self.candidate_inventory = inventory(self.text, [method, candidate_time], scope=scope)
        self.manual_inventory = inventory(self.text, [method, manual_time],
                                          role="MANUAL_REFERENCE", scope=scope)
        self.comparison = compare_inventories(self.text, self.candidate_inventory, self.manual_inventory)
        self.binding = {"question": {"id": "synthetic", "text": "Synthetic only"},
                        "knowledge_base": {"version": "fixture", "rows": []},
                        "formulas": {"effectiveness": "frozen-fixture-v1"},
                        "context": {"question_meta": {}, "userpref": {}, "model_space": {}}}
        self.candidate_extraction = {"method_name": "CUBIC", "marker_dict": {},
                                     "clearing_total_time_hours": 24}
        self.manual_extraction = {"method_name": "CUBIC", "marker_dict": {},
                                  "clearing_total_time_hours": 48}

    @staticmethod
    def scorer(extraction, binding):
        del binding
        return {"completeness": {"c_step": {"score": 2}, "total": 2},
                "correctness": {"co_method": {"score": 2}, "total": 2},
                "effectiveness": {"s_time": {"score": extraction["clearing_total_time_hours"] / 24},
                                  "s_trans": {"score": None}}}

    def test_callback_reports_per_score_delta_and_propagates_unknown(self):
        impact = measure_score_impact(
            self.comparison, self.binding, scorer=self.scorer,
            scorer_id="synthetic-existing-scorer", scorer_revision="v1",
            candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            frozen_score_paths=("completeness", "correctness"))
        self.assertEqual(impact["status"], "AVAILABLE")
        self.assertEqual(impact["score_differences"]["/effectiveness/s_time"]["delta_manual_minus_candidate"], 1)
        self.assertEqual(impact["score_differences"]["/effectiveness/s_trans"]["status"], "UNAVAILABLE")
        self.assertFalse(impact["frozen_violations"])
        self.assertIn("HYPOTHETICAL", impact["interpretation"])
        self.assertIsNone(impact["scientific_accuracy"])

    def test_equal_explicit_null_is_frozen_but_delta_stays_unavailable(self):
        impact = measure_score_impact(
            self.comparison, self.binding, scorer=self.scorer,
            scorer_id="synthetic-existing-scorer", scorer_revision="v1",
            candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            frozen_score_paths=("completeness", "correctness", "/effectiveness/s_trans"))
        self.assertEqual(impact["status"], "AVAILABLE")
        self.assertFalse(impact["frozen_violations"])
        unknown = impact["score_differences"]["/effectiveness/s_trans"]
        self.assertTrue(unknown["candidate_present"])
        self.assertTrue(unknown["manual_present"])
        self.assertIsNone(unknown["delta_manual_minus_candidate"])
        self.assertEqual(unknown["status"], "UNAVAILABLE")
        self.assertEqual(
            impact["score_differences"]["/effectiveness/s_time"]["delta_manual_minus_candidate"], 1)

        def null_to_number(extraction, binding):
            del binding
            value = None if extraction["clearing_total_time_hours"] == 24 else 1
            return {"effectiveness": {"s_trans": {"score": value}}}

        changed = measure_score_impact(
            self.comparison, self.binding, scorer=null_to_number,
            scorer_id="null-transition", scorer_revision="v1",
            candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            frozen_score_paths=("/effectiveness/s_trans",))
        self.assertEqual(changed["status"], "INVALID_FROZEN_SCORES")
        self.assertIn("/effectiveness/s_trans", changed["frozen_violations"])

        missing = measure_score_impact(
            self.comparison, self.binding, scorer=self.scorer,
            scorer_id="synthetic-existing-scorer", scorer_revision="v1",
            candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            frozen_score_paths=("/absent_score_group",))
        self.assertEqual(missing["status"], "INVALID_FROZEN_SCORES")
        self.assertIn("/absent_score_group/<missing>", missing["frozen_violations"])

    def test_manual_extraction_absent_or_inconsistent_makes_impact_unavailable(self):
        missing_manual = measure_score_impact(
            self.comparison, self.binding, scorer=self.scorer, scorer_id="s", scorer_revision="1",
            candidate_extraction=self.candidate_extraction)
        self.assertEqual(missing_manual["status"], "UNAVAILABLE")
        altered = deepcopy(self.manual_extraction)
        altered["clearing_total_time_hours"] = 47
        inconsistent = measure_score_impact(
            self.comparison, self.binding, scorer=self.scorer, scorer_id="s", scorer_revision="1",
            candidate_extraction=self.candidate_extraction, manual_extraction=altered)
        self.assertEqual(inconsistent["status"], "UNAVAILABLE")
        self.assertEqual(inconsistent["manual_consistency"]["status"], "INCONSISTENT")

    def test_uninventoried_flat_input_drift_cannot_be_attributed_to_extraction(self):
        candidate_inventory = deepcopy(self.candidate_inventory)
        manual_inventory = deepcopy(candidate_inventory)
        manual_inventory["provenance"].update(
            role="MANUAL_REFERENCE", independence="INDEPENDENT", assistance=[])
        comparison = compare_inventories(self.text, candidate_inventory, manual_inventory)
        self.assertEqual(comparison["extraction_agreement"], "AGREEMENT")

        def hidden_parameter_scorer(extraction, binding):
            del binding
            return {"effectiveness": {"s_time": {"score": extraction.get("hidden_parameter", 0)}}}

        for candidate_hidden, manual_hidden in ((0, 100), (None, 100)):
            with self.subTest(candidate_hidden=candidate_hidden):
                candidate_extraction = deepcopy(self.candidate_extraction)
                manual_extraction = deepcopy(self.candidate_extraction)
                if candidate_hidden is not None:
                    candidate_extraction["hidden_parameter"] = candidate_hidden
                manual_extraction["hidden_parameter"] = manual_hidden
                impact = measure_score_impact(
                    comparison, self.binding, scorer=hidden_parameter_scorer,
                    scorer_id="hidden-fixture", scorer_revision="v1",
                    candidate_extraction=candidate_extraction,
                    manual_extraction=manual_extraction,
                    frozen_score_paths=("completeness", "correctness"))
                self.assertEqual(impact["status"], "UNAVAILABLE")
                self.assertEqual(impact["input_change_audit"]["status"], "UNATTRIBUTED_CHANGES")
                self.assertEqual(impact["input_change_audit"]["issues"][0]["path"], "/hidden_parameter")

    def test_approved_records_require_the_same_binding_and_scorer(self):
        digest = json_hash(self.binding)
        base = {"status": "APPROVED_FROZEN", "scorer_id": "s", "scorer_revision": "1",
                "binding_sha256": digest,
                "extraction_sha256": json_hash(self.candidate_extraction),
                "inventory_sha256": self.comparison["candidate_audit"]["inventory_sha256"],
                "scores": {"effectiveness": {"s_time": {"score": 1}}}}
        manual = deepcopy(base)
        manual["extraction_sha256"] = json_hash(self.manual_extraction)
        manual["inventory_sha256"] = self.comparison["manual_audit"]["inventory_sha256"]
        manual["scores"]["effectiveness"]["s_time"]["score"] = 2
        impact = measure_score_impact(
            self.comparison, self.binding, candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            candidate_score_record=base, manual_score_record=manual)
        self.assertEqual(impact["status"], "AVAILABLE")
        self.assertEqual(impact["score_differences"]["/effectiveness/s_time"]["delta_manual_minus_candidate"], 1)
        for digest_field in ("extraction_sha256", "inventory_sha256"):
            with self.subTest(digest_field=digest_field):
                tampered = deepcopy(manual)
                tampered[digest_field] = "wrong"
                rejected_digest = measure_score_impact(
                    self.comparison, self.binding, candidate_extraction=self.candidate_extraction,
                    manual_extraction=self.manual_extraction,
                    candidate_score_record=base, manual_score_record=tampered)
                self.assertEqual(rejected_digest["status"], "UNAVAILABLE")
        manual["binding_sha256"] = "wrong"
        rejected = measure_score_impact(
            self.comparison, self.binding, candidate_extraction=self.candidate_extraction,
            manual_extraction=self.manual_extraction,
            candidate_score_record=base, manual_score_record=manual)
        self.assertEqual(rejected["status"], "UNAVAILABLE")

    def test_convenience_api_keeps_missing_score_reference_unavailable(self):
        result = evaluate_fidelity_impact(self.text, self.candidate_inventory,
                                          self.manual_inventory, binding=self.binding)
        self.assertEqual(result["comparison"]["status"], "AVAILABLE")
        self.assertEqual(result["score_impact"]["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
