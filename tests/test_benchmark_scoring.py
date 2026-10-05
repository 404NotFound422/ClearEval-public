"""Pure synthetic adapter checks; no runner, model client, native data or config."""
import copy
import json
import unittest

from benchmark_scoring import (BENCHMARK_INTERPRETATION, BENCHMARK_STATUS,
    is_benchmark_complete, promote_benchmark_estimate, summarize_benchmark_estimates)
from benchmark_scoring import (IncompleteBenchmarkScore, BENCHMARK_UNRESOLVED_STATUS,
    is_benchmark_record_complete, promote_unresolved_benchmark)
from evaluation_contract import json_hash
from evaluator_integrity import FLAT_GROUNDING_VERSION, legacy_integrity_audit, method_identity
from results.oeq_metrics import aggregate_items

PROTOCOL = "Use M1 for 2 days."
PROVENANCE = {"demand_profile": "current-proposal",
    "numeric_scale_status": "UNCALIBRATED_PROJECTION_FOR_REVIEW", "scientific_approval": None}


def span(text, quote):
    start = text.index(quote)
    return dict(start=start, end=start + len(quote), quote=quote)


def support(text, value, context, transform="IDENTITY"):
    return dict(kind="EXPLICIT", spans=[span(text, value)], context_span=span(text, context),
                raw_value=value, transform=transform)


def fixture(protocol=PROTOCOL, extraction=None, grounded=False):
    extraction = copy.deepcopy(extraction) if extraction is not None else dict(
        method_name="M1", marker_dict={}, clearing_total_time_hours=48)
    if grounded:
        context = protocol.rstrip(".")
        extraction.update(schema_version=FLAT_GROUNDING_VERSION, field_support={
            "/method_name": support(protocol, "M1", context),
            "/marker_dict": {"kind": "MISSING"},
            "/clearing_total_time_hours": support(protocol, "2 days", context, "TIME_TO_HOURS")})
    raw = {
        "completeness": {"c_step": {"score": 2}, "c_param": {"score": 3}, "total_completeness_score": 5},
        "correctness": {"co_order": {"score": 3}, "co_method": {"score": 2},
            "co_param": {"score": 2}, "co_chem": {"score": 1}, "critical_warnings": [],
            "total_correctness_score": 8}}
    scores = copy.deepcopy(raw)
    scores["effectiveness"] = {k: {"score": v} for k, v in
        dict(s_method=1.25, s_label=6, s_trans=3, s_time=3).items()}
    identity = method_identity(extraction["method_name"], ["M1", "M2"], extraction.get("method_stages"))
    effectiveness = {k: v["score"] for k, v in scores["effectiveness"].items()}
    effectiveness["method_identity"] = identity
    return dict(technical_status="VALID", scoring_status="LEGACY_DIAGNOSTIC_ONLY",
        scientific_status="UNRESOLVED", cce_eligible=False, official_scores=None,
        extraction=extraction, integrity=legacy_integrity_audit(extraction, protocol, effectiveness),
        meta_data={"demand_provenance": copy.deepcopy(PROVENANCE)},
        legacy_diagnostics=dict(scores=scores, raw_teacher_scores=raw, method_identity=identity,
            compatibility_audit=[]), teacher_generation=dict(technical_status="VALID",
            content=json.dumps(dict(scores=raw, extraction=extraction)), metadata={"finish_reason": "stop"}))


def refresh_teacher(evaluation):
    evaluation["teacher_generation"]["content"] = json.dumps(dict(
        scores=evaluation["legacy_diagnostics"]["raw_teacher_scores"], extraction=evaluation["extraction"]))


def refresh_record_hash(evaluation):
    evaluation["benchmark_record_sha256"] = json_hash({k: v for k, v in evaluation.items()
        if k != "benchmark_record_sha256"})


class BenchmarkScoringTests(unittest.TestCase):
    def test_unknown_science_and_legacy_fidelity_allow_complete_estimate(self):
        original = fixture()
        before = copy.deepcopy(original)
        promoted = promote_benchmark_estimate(original, PROTOCOL)
        self.assertEqual(original, before)
        self.assertNotIn("scores", original)
        self.assertEqual(promoted["scores"], original["legacy_diagnostics"]["scores"])
        self.assertEqual(promoted["scoring_status"], BENCHMARK_STATUS)
        self.assertEqual(promoted["score_interpretation"], BENCHMARK_INTERPRETATION)
        self.assertEqual(promoted["scientific_status"], "UNRESOLVED")
        self.assertFalse(promoted["cce_eligible"])
        self.assertIsNone(promoted["official_scores"])
        self.assertEqual(promoted["demand_provenance"], PROVENANCE)
        self.assertEqual(promoted["integrity"]["fidelity"]["fidelity_status"], "LEGACY_STRUCTURE_ONLY")
        self.assertTrue(is_benchmark_complete(promoted, PROTOCOL))
        self.assertTrue(is_benchmark_complete(promoted))
        self.assertEqual(aggregate_items([dict(question_id=1, evaluation=promoted)])["sample_count"], 1)

    def test_grounded_fields_allow_estimate_without_scientific_certification(self):
        promoted = promote_benchmark_estimate(fixture(grounded=True), PROTOCOL)
        self.assertTrue(promoted["integrity"]["fidelity"]["validated"])
        self.assertTrue(is_benchmark_complete(promoted, PROTOCOL))
        self.assertFalse(promoted["cce_eligible"])

    def test_explicit_provenance_preserves_numbers_and_is_copied(self):
        source = fixture()
        provenance = dict(demand_profile="fixed", questions_sha256="synthetic-only")
        promoted = promote_benchmark_estimate(source, PROTOCOL, provenance)
        provenance["demand_profile"] = "changed-after-promotion"
        self.assertEqual(promoted["demand_provenance"]["demand_profile"], "fixed")
        self.assertEqual(promoted["scores"], source["legacy_diagnostics"]["scores"])

    def test_same_method_stages_are_unreviewed_without_true_identity_conflict(self):
        extraction = dict(method_name="M1", marker_dict={}, clearing_total_time_hours=48,
            method_stages=[dict(id="a", method_name="M1", quote="M1"),
                           dict(id="b", method_name="M1", quote="M1")])
        source = fixture(extraction=extraction)
        self.assertEqual(source["legacy_diagnostics"]["method_identity"]["status"], "COMPOSITE_UNREVIEWED")
        self.assertTrue(is_benchmark_complete(promote_benchmark_estimate(source, PROTOCOL), PROTOCOL))

    def test_true_method_conflicts_rejected_even_with_complete_numeric_proposals(self):
        protocol = "Use M1 then M2 for 2 days."
        cases = [dict(method_name="M1 -> M2", marker_dict={}, clearing_total_time_hours=48),
            dict(method_name="M1", marker_dict={}, clearing_total_time_hours=48,
                method_stages=[dict(id="a", method_name="M1", quote="M1"),
                               dict(id="b", method_name="M2", quote="M2")])]
        for extraction in cases:
            with self.subTest(extraction=extraction), self.assertRaises(ValueError):
                promote_benchmark_estimate(fixture(protocol, extraction), protocol)

    def test_absent_stage_quote_rejected(self):
        extraction = dict(method_name="M1", marker_dict={}, clearing_total_time_hours=48,
            method_stages=[dict(id="a", method_name="M1", quote="invented")])
        with self.assertRaises(ValueError):
            promote_benchmark_estimate(fixture(extraction=extraction), PROTOCOL)

    def test_bad_support_cannot_be_hidden_by_stale_audit(self):
        for mutation in ("offset", "quote", "coverage", "magnitude"):
            with self.subTest(mutation=mutation):
                source = fixture(grounded=True)
                supports = source["extraction"]["field_support"]
                if mutation == "offset":
                    supports["/method_name"]["spans"][0]["start"] += 1
                elif mutation == "quote":
                    supports["/method_name"]["spans"][0]["quote"] = "M2"
                elif mutation == "coverage":
                    del supports["/method_name"]
                else:
                    source["extraction"]["clearing_total_time_hours"] = 2
                refresh_teacher(source)
                with self.assertRaises(ValueError):
                    promote_benchmark_estimate(source, PROTOCOL)

    def test_support_without_schema_rejected(self):
        source = fixture(grounded=True)
        del source["extraction"]["schema_version"]
        refresh_teacher(source)
        with self.assertRaisesRegex(ValueError, "schema version"):
            promote_benchmark_estimate(source, PROTOCOL)

    def test_wrong_protocol_rejected(self):
        source = fixture()
        with self.assertRaises(ValueError):
            promote_benchmark_estimate(source, PROTOCOL + " Changed instruction.")
        promoted = promote_benchmark_estimate(source, PROTOCOL)
        self.assertFalse(is_benchmark_complete(promoted, PROTOCOL + " Changed instruction."))

    def test_all_components_reject_null_nonfinite_boolean_and_out_of_range(self):
        for group, keys in dict(completeness=("c_step", "c_param"),
            correctness=("co_order", "co_method", "co_param", "co_chem"),
            effectiveness=("s_method", "s_label", "s_trans", "s_time")).items():
            for key in keys:
                for value in (None, True, float("nan"), float("inf"), 100, -100):
                    with self.subTest(group=group, key=key, value=value):
                        source = fixture()
                        source["legacy_diagnostics"]["scores"][group][key]["score"] = value
                        with self.assertRaises(ValueError):
                            promote_benchmark_estimate(source, PROTOCOL)

    def test_failed_generation_and_changed_raw_proposals_rejected(self):
        for mutation in ("technical", "provider", "json", "raw_teacher_scores", "extraction"):
            with self.subTest(mutation=mutation):
                source = fixture()
                if mutation == "technical":
                    source["technical_status"] = "FAILED"
                elif mutation == "provider":
                    source["teacher_generation"]["technical_status"] = "FAILED"
                elif mutation == "json":
                    source["teacher_generation"]["content"] = '{"unfinished":'
                elif mutation == "raw_teacher_scores":
                    source["legacy_diagnostics"]["raw_teacher_scores"]["completeness"]["c_step"]["score"] = 1
                else:
                    source["extraction"]["method_name"] = "M2"
                with self.assertRaises(ValueError):
                    promote_benchmark_estimate(source, PROTOCOL)

    def test_corrupt_hashes_and_scientific_certification_markers_rejected(self):
        source = promote_benchmark_estimate(fixture(), PROTOCOL)
        for key, value in (("scores_sha256", "bad"), ("teacher_generation_sha256", "bad"),
            ("benchmark_record_sha256", "bad"), ("benchmark_adapter_version", "bad"),
            ("score_interpretation", "scientifically-certified"), ("scientific_status", "SATISFIED"),
            ("cce_eligible", True), ("official_scores", {"CCE": 1})):
            with self.subTest(key=key):
                changed = copy.deepcopy(source)
                changed[key] = value
                refresh_record_hash(changed)
                if key == "benchmark_record_sha256":
                    changed[key] = value
                self.assertFalse(is_benchmark_complete(changed, PROTOCOL))

    def test_rehashed_score_changes_still_fail_against_original_proposal(self):
        changed = promote_benchmark_estimate(fixture(), PROTOCOL)
        changed["scores"]["completeness"]["c_step"]["score"] = 1
        changed["scores_sha256"] = json_hash(changed["scores"])
        refresh_record_hash(changed)
        self.assertFalse(is_benchmark_complete(changed, PROTOCOL))
        changed["legacy_diagnostics"]["scores"]["completeness"]["c_step"]["score"] = 1
        refresh_record_hash(changed)
        self.assertFalse(is_benchmark_complete(changed, PROTOCOL))

    def test_historical_flat_teacher_output_preserves_the_same_numeric_proposal(self):
        source = fixture()
        raw = source["legacy_diagnostics"]["raw_teacher_scores"]
        flat = dict(source["extraction"])
        for group, mapping in {
            "completeness": {"c_step": "C_step", "c_param": "C_param"},
            "correctness": {"co_order": "Co_order", "co_method": "Co_method",
                            "co_param": "Co_param", "co_chem": "Co_chem"},
        }.items():
            for key, target in mapping.items():
                flat[target] = raw[group][key]
        flat["total_completeness_score"] = raw["completeness"]["total_completeness_score"]
        flat["total_correctness_score"] = raw["correctness"]["total_correctness_score"]
        flat["completeness_critical_warnings"] = raw["correctness"]["critical_warnings"]
        source["teacher_generation"]["content"] = json.dumps(flat)
        promoted = promote_benchmark_estimate(source, PROTOCOL)
        self.assertEqual(promoted["scores"], source["legacy_diagnostics"]["scores"])
        self.assertTrue(is_benchmark_complete(promoted, PROTOCOL))
    def test_summary_retains_failed_inputs_and_nonformal_interpretation(self):
        source = promote_benchmark_estimate(fixture(), PROTOCOL)
        summary = summarize_benchmark_estimates([dict(question_id=1, evaluation=source),
            dict(question_id=2, evaluation=dict(technical_status="FAILED", _error="parse"))])
        self.assertEqual(summary["benchmark_estimate_count"], 1)
        self.assertEqual(summary["technical_failure_count"], 1)
        self.assertEqual(summary["full_input_coverage"], 0.5)
        self.assertEqual(summary["coverage"], 0.5)
        self.assertEqual(summary["total_items"], 2)
        self.assertEqual(summary["score_interpretation"], BENCHMARK_INTERPRETATION)
        self.assertIsNone(summary["formal_cce"])



def unknown_fixture(*paths):
    source = fixture()
    scores = source["legacy_diagnostics"]["scores"]
    raw = source["legacy_diagnostics"]["raw_teacher_scores"]
    for group, key in paths or (("effectiveness", "s_time"),):
        scores[group][key]["score"] = None
        if group in raw:
            scores[group][key]["reasoning"] = "Explicitly unknown synthetic assessment."
            raw[group][key] = copy.deepcopy(scores[group][key])
            total = "total_completeness_score" if group == "completeness" else "total_correctness_score"
            scores[group][total] = raw[group][total] = None
    effectiveness = {key: record["score"] for key, record in scores["effectiveness"].items()}
    effectiveness["method_identity"] = source["legacy_diagnostics"]["method_identity"]
    source["integrity"] = legacy_integrity_audit(source["extraction"], PROTOCOL, effectiveness)
    refresh_teacher(source)
    return source


class UnresolvedBenchmarkTests(unittest.TestCase):
    def assertHardError(self, source, promoter=promote_benchmark_estimate):
        with self.assertRaises(ValueError) as raised:
            promoter(source, PROTOCOL)
        self.assertNotIsInstance(raised.exception, IncompleteBenchmarkScore)

    def test_valid_unknown_is_a_technical_terminal_record_without_numeric_imputation(self):
        source = unknown_fixture()
        before = copy.deepcopy(source)
        with self.assertRaises(IncompleteBenchmarkScore):
            promote_benchmark_estimate(source, PROTOCOL)
        record = promote_unresolved_benchmark(source, PROTOCOL)
        self.assertEqual(source, before)
        self.assertEqual(record["technical_status"], "VALID")
        self.assertEqual(record["scoring_status"], BENCHMARK_UNRESOLVED_STATUS)
        self.assertEqual(record["unknown_components"], ["effectiveness.s_time"])
        self.assertNotIn("scores", record)
        self.assertNotIn("_error", record)
        self.assertEqual(record["legacy_diagnostics"]["scores"], source["legacy_diagnostics"]["scores"])
        self.assertIsNone(record["legacy_diagnostics"]["scores"]["effectiveness"]["s_time"]["score"])
        self.assertEqual(record["teacher_generation"], source["teacher_generation"])
        self.assertEqual(record["scientific_status"], "UNRESOLVED")
        self.assertFalse(record["cce_eligible"])
        self.assertIsNone(record["official_scores"])
        self.assertEqual(record["demand_provenance"], PROVENANCE)
        self.assertTrue(is_benchmark_record_complete(record, PROTOCOL))
        self.assertTrue(is_benchmark_record_complete(record))
        self.assertFalse(is_benchmark_complete(record, PROTOCOL))
        self.assertEqual(aggregate_items([dict(question_id=1, evaluation=record)])["sample_count"], 0)

    def test_teacher_unknown_with_reasoning_and_null_total_is_preserved(self):
        source = unknown_fixture(("completeness", "c_step"))
        with self.assertRaises(IncompleteBenchmarkScore):
            promote_benchmark_estimate(source, PROTOCOL)
        record = promote_unresolved_benchmark(source, PROTOCOL)
        self.assertEqual(record["unknown_components"], ["completeness.c_step"])
        self.assertTrue(is_benchmark_record_complete(record, PROTOCOL))
        self.assertIsNone(record["legacy_diagnostics"]["scores"]["completeness"]["total_completeness_score"])

    def test_multiple_unknowns_and_signed_method_boundaries_are_supported(self):
        source = unknown_fixture(("effectiveness", "s_method"), ("effectiveness", "s_time"))
        record = promote_unresolved_benchmark(source, PROTOCOL)
        self.assertEqual(record["unknown_components"], ["effectiveness.s_method", "effectiveness.s_time"])
        for value in (-2.5, 0, 2.5):
            with self.subTest(s_method=value):
                source = unknown_fixture()
                source["legacy_diagnostics"]["scores"]["effectiveness"]["s_method"]["score"] = value
                record = promote_unresolved_benchmark(source, PROTOCOL)
                self.assertTrue(is_benchmark_record_complete(record, PROTOCOL))
                self.assertEqual(record["legacy_diagnostics"]["scores"]["effectiveness"]["s_method"]["score"], value)

    def test_complete_numbers_cannot_be_relabelled_unresolved(self):
        with self.assertRaises(ValueError):
            promote_unresolved_benchmark(fixture(), PROTOCOL)

    def test_bad_quote_and_true_method_conflict_are_not_hidden_by_null(self):
        for mutation in ("quote", "method_conflict"):
            with self.subTest(mutation=mutation):
                source = unknown_fixture()
                if mutation == "quote":
                    source["extraction"]["method_stages"] = [dict(id="a", method_name="M1", quote="invented")]
                else:
                    source["legacy_diagnostics"]["method_identity"] = method_identity("M1 -> M2", ["M1", "M2"])
                refresh_teacher(source)
                self.assertHardError(source)
                self.assertHardError(source, promote_unresolved_benchmark)

    def test_bad_field_support_is_not_hidden_by_null(self):
        source = fixture(grounded=True)
        source["legacy_diagnostics"]["scores"]["effectiveness"]["s_time"]["score"] = None
        source["extraction"]["field_support"]["/method_name"]["spans"][0]["start"] += 1
        refresh_teacher(source)
        self.assertHardError(source)
        self.assertHardError(source, promote_unresolved_benchmark)

    def test_missing_component_or_score_object_is_not_an_explicit_unknown(self):
        for mutation in ("component", "score_key", "score_object", "list_object"):
            with self.subTest(mutation=mutation):
                source = unknown_fixture()
                if mutation == "component":
                    del source["legacy_diagnostics"]["scores"]["effectiveness"]["s_trans"]
                elif mutation == "score_key":
                    del source["legacy_diagnostics"]["scores"]["effectiveness"]["s_trans"]["score"]
                elif mutation == "score_object":
                    del source["legacy_diagnostics"]["scores"]
                else:
                    source["legacy_diagnostics"]["scores"] = []
                self.assertHardError(source)
                self.assertHardError(source, promote_unresolved_benchmark)

    def test_late_invalid_number_is_not_hidden_by_an_earlier_null(self):
        for value in (False, "3", float("inf"), float("nan"), 3.001, -0.001, 10 ** 1000):
            with self.subTest(value=value):
                source = unknown_fixture(("effectiveness", "s_method"))
                source["legacy_diagnostics"]["scores"]["effectiveness"]["s_time"]["score"] = value
                self.assertHardError(source)
                self.assertHardError(source, promote_unresolved_benchmark)

    def test_unknown_component_list_hash_and_partial_score_tampering_are_rejected(self):
        original = promote_unresolved_benchmark(unknown_fixture(), PROTOCOL)
        for mutation in ("unknown", "score_hash", "record_hash", "partial", "injected_score", "missing_scores"):
            with self.subTest(mutation=mutation):
                record = copy.deepcopy(original)
                if mutation == "unknown":
                    record["unknown_components"] = ["effectiveness.s_trans"]
                elif mutation == "score_hash":
                    record["scores_sha256"] = "bad"
                elif mutation == "record_hash":
                    record["benchmark_record_sha256"] = "bad"
                elif mutation == "partial":
                    record["legacy_diagnostics"]["scores"]["effectiveness"]["s_time"]["score"] = 0
                elif mutation == "injected_score":
                    record["scores"] = fixture()["legacy_diagnostics"]["scores"]
                else:
                    del record["legacy_diagnostics"]["scores"]
                    record["scores_sha256"] = json_hash(None)
                refresh_record_hash(record)
                if mutation == "record_hash":
                    record["benchmark_record_sha256"] = "bad"
                self.assertFalse(is_benchmark_record_complete(record, PROTOCOL))

    def test_summary_distinguishes_technical_completion_and_numeric_coverage(self):
        scored = promote_benchmark_estimate(fixture(), PROTOCOL)
        unknown = promote_unresolved_benchmark(unknown_fixture(), PROTOCOL)
        summary = summarize_benchmark_estimates([
            dict(question_id=1, evaluation=scored), dict(question_id=2, evaluation=unknown),
            dict(question_id=3, evaluation=dict(technical_status="FAILED", _error="parse"))])
        self.assertEqual(summary["technical_valid_count"], 2)
        self.assertEqual(summary["technical_failure_count"], 1)
        self.assertEqual(summary["benchmark_unresolved_count"], 1)
        self.assertEqual(summary["benchmark_estimate_count"], 1)
        self.assertEqual(summary["total_items"], 3)
        self.assertEqual(summary["coverage"], 1 / 3)
        self.assertEqual(summary["full_input_coverage"], 1 / 3)
        self.assertIsNone(summary["formal_cce"])
        self.assertTrue(any(item["reason"] == "explicitly_unknown_components"
                            for item in summary["excluded_items"]))

if __name__ == "__main__":
    unittest.main()



