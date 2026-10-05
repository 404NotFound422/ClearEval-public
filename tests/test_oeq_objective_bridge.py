"""Synthetic checks for the bounded OEQ objective relation bridge."""
from copy import deepcopy
import unittest

from oeq_objective_bridge import (
    build_objective_diagnostics,
    build_relation_binding,
)


def objective(low, high=None, *, unit="h", direction="min", kind="RECORDED_OBSERVATION",
              candidate="A", method="method-a", route="route-a", scope=None,
              basis="AUDITED_SYNTHETIC_RECORD", record=None, extra_provenance=None,
              objective_scope="OPERATIONAL_TIME", **extra):
    provenance = {
        "record_id": record or "record-" + candidate,
        "candidate_id": candidate,
        "method_id": method,
        "route_id": route,
        "source": "SYNTHETIC_TEST_FIXTURE",
    }
    provenance.update(extra_provenance or {})
    return {
        "min": low,
        "max": low if high is None else high,
        "unit": unit,
        "direction": direction,
        "measurement_scope": scope or {"phase": "complete candidate", "population": "fixture"},
        "measurement_basis": basis,
        "objective_scope": objective_scope,
        "value_kind": kind,
        "provenance": provenance,
        **extra,
    }


def candidate(cid, *, time=1, unit="h", quality=None, constraints="satisfied",
              scenario=None, kind="RECORDED_OBSERVATION", method=None, route=None):
    method = method or "method-" + cid.lower()
    route = route or "route-" + cid.lower()
    values = {
        "elapsed_time": objective(time, unit=unit, candidate=cid, method=method,
                                  route=route, kind=kind),
    }
    if quality is not None:
        values["resource_yield"] = objective(
            quality, unit="ratio", direction="max", candidate=cid,
            method=method, route=route, kind=kind,
            objective_scope="OPERATIONAL_RESOURCE", record="yield-" + cid,
        )
    value = {
        "id": cid,
        "task_id": "task-1",
        "scenario": scenario or {"sample": "same synthetic sample", "scale": "same"},
        "candidate_scope": {
            "kind": "SINGLE_METHOD_COMPLETE_CANDIDATE",
            "complete_candidate": True,
            "method_id": method,
            "route_id": route,
        },
        "objectives": values,
    }
    if constraints == "satisfied":
        value["constraints"] = {"complete_contract": "SATISFIED"}
    elif constraints == "violated":
        value["constraints"] = {"complete_contract": "VIOLATED"}
    elif constraints == "none-declared":
        value["constraints"] = {}
        value["no_hard_constraints_declared"] = True
    elif constraints != "missing":
        raise AssertionError("bad fixture")
    return value


class ObjectiveBridgeTests(unittest.TestCase):
    def test_missing_records_abstain_without_inventing_values(self):
        result = build_objective_diagnostics()
        self.assertEqual(result["status"], "U")
        self.assertEqual(result["relationship"], "UNRESOLVED")
        self.assertIn("AUDITED_OBJECTIVE_RECORDS_NOT_SUPPLIED", result["reasons"])
        self.assertIsNone(result["objective_records"])
        self.assertFalse(result["imaging_outcomes_evaluated"])

    def test_safe_unit_conversion_preserves_raw_value_and_provenance(self):
        a = candidate("A", time=2, unit="h")
        b = candidate("B", time=120, unit="min")
        marker = {"record_id": "record-B", "candidate_id": "B", "method_id": "method-b",
                  "route_id": "route-b", "source": "USER_AUDITED_TABLE", "row": 7}
        b["objectives"]["elapsed_time"]["provenance"] = marker
        result = build_objective_diagnostics([a, b])
        self.assertEqual(result["relationship"], "EQUIVALENT")
        self.assertEqual(result["status"], "S")
        normalized = result["objective_records"]["B"]["elapsed_time"]
        self.assertEqual(normalized["raw"]["unit"], "min")
        self.assertEqual(normalized["raw"]["min"], 120)
        self.assertEqual(normalized["canonical"]["unit"], "h")
        self.assertEqual(normalized["canonical"]["min"], 2)
        self.assertEqual(normalized["provenance"], marker)
        self.assertEqual(result["candidate_records"][1]["objectives"]["elapsed_time"]["provenance"], marker)

    def test_incompatible_unit_scenario_and_measurement_context_abstain(self):
        cases = []
        a, b = candidate("A"), candidate("B", time=2)
        b["objectives"]["elapsed_time"]["unit"] = "operations"
        cases.append((a, b, "UNIT_OR_DIRECTION_MISMATCH:elapsed_time"))
        a, b = candidate("A"), candidate("B", time=2, scenario={"sample": "other", "scale": "same"})
        cases.append((a, b, "TASK_OR_SCENARIO_MISMATCH_OR_MISSING"))
        a, b = candidate("A"), candidate("B", time=2)
        b["objectives"]["elapsed_time"]["measurement_scope"] = {
            "phase": "partial candidate", "population": "fixture"
        }
        cases.append((a, b, "MEASUREMENT_BASIS_MISMATCH:elapsed_time"))
        for left, right, reason in cases:
            with self.subTest(reason=reason):
                result = build_objective_diagnostics([left, right])
                self.assertEqual(result["status"], "U")
                self.assertEqual(result["relationship"], "NOT_COMPARABLE")
                self.assertIn(reason, result["reasons"])

    def test_no_constraints_declaration_is_distinct_from_missing_constraints(self):
        missing = build_objective_diagnostics([
            candidate("A", constraints="missing"), candidate("B", constraints="missing")
        ])
        self.assertEqual(missing["relationship"], "UNRESOLVED")
        self.assertIn("HARD_CONSTRAINTS_NOT_ESTABLISHED", missing["reasons"])
        declared = build_objective_diagnostics([
            candidate("A", constraints="none-declared"),
            candidate("B", time=2, constraints="none-declared"),
        ])
        self.assertEqual(declared["relationship"], "A_DOMINATES")

    def test_feasibility_precedes_objective_values(self):
        result = build_objective_diagnostics([
            candidate("A", time=99, constraints="satisfied"),
            candidate("B", time=1, constraints="violated"),
        ], required_constraints=["complete_contract"])
        self.assertEqual(result["relationship"], "A_ONLY_FEASIBLE")
        self.assertEqual(result["comparison"]["feasibility"], {
            "A": "SATISFIED", "B": "VIOLATED"
        })

    def test_pareto_dominance_tradeoff_and_overlap_uncertainty(self):
        dominates = build_objective_diagnostics([
            candidate("A", time=1, quality=.9), candidate("B", time=2, quality=.8)
        ])
        self.assertEqual(dominates["relationship"], "A_DOMINATES")
        tradeoff = build_objective_diagnostics([
            candidate("A", time=1, quality=.7), candidate("B", time=2, quality=.8)
        ])
        self.assertEqual(tradeoff["relationship"], "TRADEOFF")
        a, b = candidate("A", time=1), candidate("B", time=2)
        a["objectives"]["elapsed_time"].update(min=1, max=3)
        b["objectives"]["elapsed_time"].update(min=2, max=4)
        uncertain = build_objective_diagnostics([a, b])
        self.assertEqual(uncertain["status"], "U")
        self.assertEqual(uncertain["relationship"], "UNRESOLVED")
        self.assertIn("OVERLAPPING_UNCERTAINTY_INTERVALS", uncertain["reasons"])

    def test_independent_label_requires_exact_binding_and_no_assistance(self):
        records = [candidate("A", time=1), candidate("B", time=2)]
        binding = build_relation_binding(records)
        base_ref = {
            **binding,
            "label": "A_DOMINATES",
            "independence": "INDEPENDENT",
            "annotation_pass": "FIRST_PASS",
            "assistance": "NONE",
            "reviewer_id": "fixture-reviewer",
            "provenance": {"record_id": "review-1"},
        }
        missing = build_objective_diagnostics(records)
        self.assertEqual(missing["independent_relation_count"], 0)
        self.assertEqual(missing["independent_relation"]["status"], "UNAVAILABLE")
        self.assertIn("INDEPENDENT_RELATION_NOT_SUPPLIED",
                      missing["independent_relation"]["reasons"])
        counted = build_objective_diagnostics(records, base_ref)
        self.assertEqual(counted["independent_relation_count"], 1)
        self.assertEqual(counted["independent_relation"]["status"], "COUNTED")
        self.assertTrue(counted["independent_relation"]["agreement_with_computed_relation"])
        gate_cases = [
            ("independence", None, "INDEPENDENCE_NOT_EXPLICITLY_DECLARED"),
            ("annotation_pass", None, "FIRST_PASS_ANNOTATION_NOT_DECLARED"),
            ("assistance", None, "ASSISTED_RELATION_NOT_INDEPENDENT"),
            ("reviewer_id", "", "INDEPENDENT_REVIEWER_ID_MISSING"),
        ]
        for field, replacement, reason in gate_cases:
            gated_ref = deepcopy(base_ref)
            if replacement is None:
                gated_ref.pop(field)
            else:
                gated_ref[field] = replacement
            gated = build_objective_diagnostics(records, gated_ref)
            with self.subTest(hard_gate=field):
                self.assertEqual(gated["independent_relation_count"], 0)
                self.assertEqual(gated["independent_relation"]["status"], "UNAVAILABLE")
                self.assertEqual(gated["independent_relation"]["reference"], gated_ref)
                self.assertIn(reason, gated["independent_relation"]["reasons"])
        no_record_ref = deepcopy(base_ref)
        no_record_ref["provenance"].pop("record_id")
        no_record = build_objective_diagnostics(records, no_record_ref)
        self.assertEqual(no_record["independent_relation_count"], 0)
        self.assertEqual(no_record["independent_relation"]["status"], "UNAVAILABLE")
        self.assertEqual(no_record["independent_relation"]["reference"], no_record_ref)
        self.assertIn("INDEPENDENT_RELATION_RECORD_ID_MISSING",
                      no_record["independent_relation"]["reasons"])
        assisted_ref = {**base_ref, "assistance": "MODEL_ASSISTED"}
        assisted = build_objective_diagnostics(records, assisted_ref)
        self.assertEqual(assisted["independent_relation_count"], 0)
        self.assertEqual(assisted["independent_relation"]["status"], "UNAVAILABLE")
        self.assertIn("ASSISTED_RELATION_NOT_INDEPENDENT",
                      assisted["independent_relation"]["reasons"])
        mismatched_ref = deepcopy(base_ref)
        mismatched_ref["objective_data_sha256"] = "0" * 64
        mismatched = build_objective_diagnostics(records, mismatched_ref)
        self.assertEqual(mismatched["independent_relation_count"], 0)
        self.assertIn("INDEPENDENT_RELATION_BINDING_MISMATCH:objective_data_sha256",
                      mismatched["independent_relation"]["reasons"])

    def test_value_kinds_distinguish_declared_recorded_and_formula_proxy(self):
        a = candidate("A", kind="RECORDED_TARGET")
        b = candidate("B", kind="CANDIDATE_DECLARED_TARGET")
        mixed = build_objective_diagnostics([a, b])
        self.assertEqual(mixed["relationship"], "NOT_COMPARABLE")
        self.assertIn("VALUE_KIND_MISMATCH:elapsed_time", mixed["reasons"])
        self.assertTrue(mixed["contains_recorded_objective_data"])

        a = candidate("A", kind="FORMULA_DERIVED_SUITABILITY_PROXY")
        b = candidate("B", time=2, kind="FORMULA_DERIVED_SUITABILITY_PROXY")
        for item in (a, b):
            item["objectives"]["elapsed_time"]["provenance"].update(
                formula_id="formula-v1", input_record_ids=["input-1"])
        proxy = build_objective_diagnostics([a, b])
        self.assertEqual(proxy["relationship"], "A_DOMINATES")
        self.assertTrue(proxy["contains_formula_derived_suitability_proxy"])
        self.assertFalse(proxy["contains_recorded_objective_data"])

        a = candidate("A", time=.8, kind="FORMULA_DERIVED_SUITABILITY_PROXY")
        b = candidate("B", time=.7, kind="FORMULA_DERIVED_SUITABILITY_PROXY")
        for item in (a, b):
            value = item["objectives"].pop("elapsed_time")
            value.update(
                unit="ratio",
                direction="max",
                outcome_type="METHOD_SUITABILITY",
                objective_scope="NON_IMAGING_TASK",
            )
            value["provenance"].update(
                formula_id="method-suitability-v1",
                input_record_ids=["explicit-task-constraints"],
            )
            item["objectives"]["method_suitability"] = value
        suitability = build_objective_diagnostics([a, b])
        self.assertEqual(suitability["relationship"], "A_DOMINATES")
        self.assertTrue(suitability["contains_formula_derived_suitability_proxy"])
        self.assertFalse(suitability["contains_recorded_objective_data"])
        for cid in ("A", "B"):
            record = suitability["objective_records"][cid]["method_suitability"]
            self.assertEqual(record["value_kind"], "FORMULA_DERIVED_SUITABILITY_PROXY")
            self.assertEqual(record["raw"]["outcome_type"], "METHOD_SUITABILITY")
            self.assertEqual(record["raw"]["objective_scope"], "NON_IMAGING_TASK")

    def test_cross_candidate_or_route_cherry_picking_is_rejected(self):
        a, b = candidate("A"), candidate("B")
        a["objectives"]["elapsed_time"]["provenance"]["candidate_id"] = "B"
        with self.assertRaisesRegex(ValueError, "candidate_id mismatch"):
            build_objective_diagnostics([a, b])
        a, b = candidate("A"), candidate("B")
        b["objectives"]["elapsed_time"]["provenance"]["route_id"] = "route-a"
        with self.assertRaisesRegex(ValueError, "route_id mismatch"):
            build_objective_diagnostics([a, b])
        a, b = candidate("A"), candidate("B")
        a["candidate_scope"]["method_id"] = ["method-a", "method-b"]
        with self.assertRaisesRegex(ValueError, "single-method"):
            build_objective_diagnostics([a, b])

    def test_explicit_imaging_results_rejected_without_name_guessing(self):
        a, b = candidate("A"), candidate("B", time=2)
        a["objectives"]["elapsed_time"]["outcome_type"] = "IMAGE_RESOLUTION"
        with self.assertRaisesRegex(ValueError, "Imaging-result"):
            build_objective_diagnostics([a, b])

        a, b = candidate("A"), candidate("B", time=2)
        a["objectives"]["elapsed_time"]["outcome_type"] = "NOVEL_SCORE_TYPE"
        with self.assertRaisesRegex(ValueError, "Unknown explicit objective outcome type"):
            build_objective_diagnostics([a, b])

        a, b = candidate("A"), candidate("B", time=2)
        a["objectives"]["elapsed_time"].pop("objective_scope")
        with self.assertRaisesRegex(ValueError, "semantic contract required"):
            build_objective_diagnostics([a, b])

        # A dimension name alone is not interpreted as an imaging result.  This
        # operational duration is explicitly scoped and remains comparable.
        a, b = candidate("A"), candidate("B", time=2)
        for item in (a, b):
            item["objectives"]["image_processing_time"] = item["objectives"].pop("elapsed_time")
            item["objectives"]["image_processing_time"]["objective_scope"] = "OPERATIONAL_RESOURCE"
        result = build_objective_diagnostics([a, b])
        self.assertEqual(result["relationship"], "A_DOMINATES")
        self.assertFalse(result["scope_policy"]["dimension_names_interpreted"])
        self.assertEqual(result["scope_policy"]["unknown_explicit_types"], "REJECT")

        # A controlled outcome type can supply the semantic contract without a
        # separate scope field.
        for item in (a, b):
            value = item["objectives"]["image_processing_time"]
            value.pop("objective_scope")
            value["outcome_type"] = "PROCESS_TIME"
        typed = build_objective_diagnostics([a, b])
        self.assertEqual(typed["relationship"], "A_DOMINATES")


if __name__ == "__main__":
    unittest.main()