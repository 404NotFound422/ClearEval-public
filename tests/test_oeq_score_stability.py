import copy
import math
import unittest

from oeq_score_stability import analyze_score_stability, make_trial_plan


BINDINGS = {
    "question_sha256": "q" * 64,
    "protocol_sha256": "p" * 64,
    "numeric_formula_sha256": "f" * 64,
    "knowledge_base_sha256": "k" * 64,
    "prompt_sha256": "m" * 64,
    "request_settings_sha256": "s" * 64,
}
JUDGE_A = {"family": "family-a", "model": "model-a", "revision": "2026-01", "digest": "digest-a"}
JUDGE_B = {"family": "family-b", "model": "model-b", "revision": "2026-02", "digest": "digest-b"}


def evaluation(value=1.0):
    maxima = {
        "completeness": {"c_step": 2, "c_param": 3},
        "correctness": {"co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1},
        "effectiveness": {"s_method": 2.5, "s_label": 6, "s_trans": 3, "s_time": 3},
    }
    return {"scores": {block: {key: {"score": maximum * value} for key, maximum in metrics.items()}
                       for block, metrics in maxima.items()}}


def inputs(n=1):
    return [{"input_id": f"input-{i}", "bindings": {**BINDINGS, "question_sha256": str(i) * 64,
                                                       "protocol_sha256": chr(96 + i) * 64}}
            for i in range(1, n + 1)]


def record(plan_row, suffix, value=1.0, **extra):
    observed = evaluation(value)
    observed["extraction"] = {"method_name": "method-a"}
    return {**copy.deepcopy(plan_row), "invocation_id": f"inv-{suffix}", "request_id": f"req-{suffix}",
            "evaluation": observed, **extra}


class ScoreStabilityTests(unittest.TestCase):
    def test_plan_helper_is_deterministic_and_plan_only(self):
        plan = make_trial_plan(inputs(2), [JUDGE_A, JUDGE_B], 2)
        self.assertEqual(len(plan), 8)
        self.assertEqual(len({row["trial_id"] for row in plan}), 8)
        self.assertNotIn("request_id", plan[0])
        self.assertEqual(plan[0]["judge"], JUDGE_A)

    def test_planned_denominator_and_component_stats_keep_missing(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 5)
        unknown = record(plan[2], "3", 0.0, numeric_status="unknown")
        failed = record(plan[3], "4", status="failed", error={"kind": "timeout"})
        result = analyze_score_stability(plan, [record(plan[0], "1", 1.0), record(plan[1], "2", 0.0), unknown, failed])
        coverage = result["coverage"]
        self.assertEqual(coverage["planned_trials"], 5)
        self.assertEqual(coverage["not_dispatched_trials"], 1)
        self.assertEqual(coverage["independent_numeric_results"], 2)
        self.assertEqual(coverage["independent_missing_numeric_results"], 2)
        group = result["repeat_groups"][0]
        self.assertEqual(group["unknown_trials"], 1)
        self.assertEqual(group["failed_trials"], 1)
        self.assertEqual(group["components"]["I_A"]["mean"], 0.5)
        self.assertTrue(math.isclose(group["components"]["I_A"]["sd"], math.sqrt(0.5)))
        self.assertEqual(group["components"]["I_A"]["range"], 1.0)
        self.assertTrue(group["repetition_data_available"])
        self.assertIsNone(group["stable"])
        self.assertEqual(group["stability_status"], "PENDING_PREDECLARED_THRESHOLD")
        agreement = group["score_agreement"]
        self.assertEqual(agreement["n_pairs_total"], 6)
        self.assertEqual(agreement["n_pairs_numeric"], 1)
        self.assertEqual(agreement["n_pairs_with_unknown"], 5)
        self.assertIsNone(result["scientific_accuracy"])

    def test_duplicate_request_and_cached_replay_are_not_repeats(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 3)
        first = record(plan[0], "same")
        duplicate = record(plan[1], "two")
        duplicate["request_id"] = first["request_id"]
        cached = record(plan[2], "three", cached=True, replay_of=first["trial_id"])
        result = analyze_score_stability(plan, [first, duplicate, cached])
        group = result["repeat_groups"][0]
        self.assertEqual(group["independent_trials"], 1)
        self.assertFalse(group["repetition_data_available"])
        self.assertIsNone(group["stable"])
        self.assertEqual(group["stability_status"], "NOT_AVAILABLE")
        self.assertEqual(result["coverage"]["excluded_non_independent_records"], 2)
        self.assertEqual(result["coverage"]["planned_independent_numeric_coverage"], 1 / 3)
        self.assertIsNone(group["components"]["I_A"]["sd"])
        self.assertIsNone(group["components"]["I_A"]["range"])

    def test_same_family_models_do_not_create_cross_family_claim(self):
        second = {**JUDGE_B, "family": "openai"}
        first = {**JUDGE_A, "family": "openai"}
        plan = make_trial_plan(inputs(), [first, second], 1)
        result = analyze_score_stability(plan, [record(plan[0], "1"), record(plan[1], "2")])
        self.assertEqual(result["actual_families"], ["openai"])
        self.assertEqual(result["cross_family_comparisons"], [])
        self.assertEqual(result["cross_family_assessment"], "not_established_single_actual_family")

    def test_binding_or_exact_judge_change_is_rejected(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 1)
        for field in BINDINGS:
            with self.subTest(binding=field):
                changed = record(plan[0], field)
                changed["bindings"][field] = "changed"
                with self.assertRaisesRegex(ValueError, "frozen binding mismatch"):
                    analyze_score_stability(plan, [changed])
        changed = record(plan[0], "input")
        changed["input_id"] = "altered-input"
        with self.assertRaisesRegex(ValueError, "input_id mismatch"):
            analyze_score_stability(plan, [changed])
        changed = record(plan[0], "judge")
        changed["judge"]["revision"] = "silent-latest"
        with self.assertRaisesRegex(ValueError, "exact judge identity mismatch"):
            analyze_score_stability(plan, [changed])

    def test_same_actual_judge_cannot_claim_two_families(self):
        relabeled = {**JUDGE_A, "family": "invented-family"}
        with self.assertRaisesRegex(ValueError, "contradictory family declaration"):
            make_trial_plan(inputs(), [JUDGE_A, relabeled], 1)
        plan = make_trial_plan(inputs(), [JUDGE_A, JUDGE_B], 1)
        plan[1]["judge"].update(model=JUDGE_A["model"], revision=JUDGE_A["revision"],
                                digest=JUDGE_A["digest"])
        with self.assertRaisesRegex(ValueError, "contradictory family declaration"):
            analyze_score_stability(plan, [])

    def test_one_trial_per_different_family_is_descriptive_only(self):
        plan = make_trial_plan(inputs(), [JUDGE_A, JUDGE_B], 1)
        result = analyze_score_stability(plan, [record(plan[0], "a"), record(plan[1], "b")])
        comparison = result["cross_family_comparisons"][0]
        self.assertEqual(comparison["n_matched_frozen_inputs"], 1)
        self.assertEqual(comparison["n_matched_inputs_with_repeats_both_sides"], 0)
        self.assertFalse(comparison["repetition_data_available"])
        self.assertIsNone(comparison["stable"])
        self.assertEqual(comparison["stability_status"], "PENDING_PREDECLARED_THRESHOLD")
        self.assertEqual(result["cross_family_assessment"],
                         "comparison_data_available_stability_pending_predeclared_threshold")

    def test_cross_family_pairs_only_actual_same_inputs_and_unknown_stays_missing(self):
        plan = make_trial_plan(inputs(2), [JUDGE_A, JUDGE_B], 2)
        records = []
        for index, row in enumerate(plan):
            records.append(record(row, str(index), 1.0 if row["judge"] == JUDGE_A else 0.5))
        records[2]["numeric_status"] = "unknown"  # family B, input 1, first repeat
        result = analyze_score_stability(plan, records)
        comparison = result["cross_family_comparisons"][0]
        self.assertEqual(comparison["n_matched_frozen_inputs"], 2)
        self.assertEqual(comparison["n_matched_inputs_with_repeats_both_sides"], 1)
        self.assertEqual(comparison["component_deltas_right_minus_left"]["I_A"]["n"], 2)
        self.assertTrue(comparison["repetition_data_available"])
        self.assertIsNone(comparison["stable"])
        self.assertEqual(comparison["stability_status"], "PENDING_PREDECLARED_THRESHOLD")
        input_one = result["same_input_extraction_agreement"][0]["score_agreement"]
        self.assertEqual(input_one["n_pairs_total"], 6)
        self.assertEqual(input_one["n_pairs_numeric"], 3)
        self.assertEqual(input_one["n_pairs_with_unknown"], 3)

    def test_extraction_agreement_uses_extraction_not_equal_scores(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 2)
        left, right = record(plan[0], "extract-a"), record(plan[1], "extract-b")
        left["evaluation"]["extraction"]["method_name"] = "A"
        right["evaluation"]["extraction"]["method_name"] = "B"
        result = analyze_score_stability(plan, [left, right])
        group = result["repeat_groups"][0]
        self.assertEqual(group["score_agreement"]["complete_raw_vector_exact_agreement"], 1.0)
        self.assertEqual(group["extraction_agreement"]["exact_agreement"], 0.0)
        self.assertEqual(group["extraction_agreement"]["fields"]["method_name"]["exact_agreement"], 0.0)

    def test_missing_extraction_has_null_agreement(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 2)
        left, right = record(plan[0], "missing-a"), record(plan[1], "missing-b")
        left["evaluation"].pop("extraction")
        right["evaluation"].pop("extraction")
        agreement = analyze_score_stability(plan, [left, right])["repeat_groups"][0]["extraction_agreement"]
        self.assertEqual(agreement["n_pairs_with_extraction"], 0)
        self.assertIsNone(agreement["exact_agreement"])

    def test_technical_failure_cannot_fall_back_to_legacy_scores(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 2)
        failed = record(plan[0], "failed-legacy")
        failed["evaluation"] = {
            "technical_status": "FAILED", "_error": "malformed response",
            "extraction": {"method_name": "A"},
            "legacy_diagnostics": {"scores": evaluation(1.0)["scores"]},
        }
        result = analyze_score_stability(plan, [failed])
        group = result["repeat_groups"][0]
        self.assertEqual(group["failed_trials"], 1)
        self.assertEqual(group["numeric_trials"], 0)
        self.assertIsNone(group["components"]["I_A"]["mean"])
        self.assertEqual(group["extraction_agreement"]["n_pairs_with_extraction"], 0)
        self.assertEqual(result["coverage"]["independent_missing_numeric_results"], 1)

    def test_valid_legacy_diagnostic_still_uses_shared_formula(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 1)
        legacy = record(plan[0], "valid-legacy")
        legacy["evaluation"] = {
            "technical_status": "VALID", "extraction": {"method_name": "A"},
            "legacy_diagnostics": {"scores": evaluation(1.0)["scores"]},
        }
        group = analyze_score_stability(plan, [legacy])["repeat_groups"][0]
        self.assertEqual(group["numeric_trials"], 1)
        self.assertEqual(group["components"]["I_A"]["mean"], 1.0)

    def test_zero_placeholders_with_all_u_markers_are_missing(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 2)
        placeholder = record(plan[0], "placeholder", 0.0)
        for block in placeholder["evaluation"]["scores"].values():
            for leaf in block.values():
                leaf["extracted"] = "U"
        result = analyze_score_stability(plan, [placeholder])
        self.assertEqual(result["repeat_groups"][0]["numeric_trials"], 0)
        self.assertIsNone(result["repeat_groups"][0]["components"]["I_A"]["mean"])
        self.assertEqual(result["per_actual_judge"][0]["numeric_trials"], 0)

    def test_unmarked_all_u_is_not_converted_to_zero(self):
        plan = make_trial_plan(inputs(), [JUDGE_A], 2)
        bad = record(plan[0], "u")
        for block in bad["evaluation"]["scores"].values():
            for leaf in block.values():
                leaf["score"] = "U"
        result = analyze_score_stability(plan, [bad])
        group = result["repeat_groups"][0]
        self.assertEqual(group["numeric_trials"], 0)
        self.assertEqual(group["unknown_trials"], 1)
        self.assertIsNone(group["components"]["I_A"]["mean"])
        self.assertIsNone(group["components"]["I_A"]["sd"])


if __name__ == "__main__":
    unittest.main()