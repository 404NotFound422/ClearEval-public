"""Task 3 tests for the gold workflow + report verdicts (final-review #16).

Covers:
1. ``assemble_gold(expert)`` reads ONLY the ``reviewer_{expert}_*`` label keys
   of a review-package row -- the programmatic proposal expectation under the
   unprefixed names (``expected_relation`` etc.) can NEVER leak into Gold
   (Critical finding #1).
2. ``GoldReview.from_dict`` is strict about the review fields (missing/unknown
   ``adjudication_status`` raises, finding #20).
3. ``write_review_package`` emits one row per full-corpus pair with empty
   ``reviewer_A_*`` / ``reviewer_B_*`` labels and ``_review_filled=False``.
4. ``verdict()`` evaluates the BLIND metrics when blind results are provided,
   not the development metrics (finding #8).

Offline; only reads the committed manifests (read-only) + stdlib.
"""

import json
import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from diagnostics.cleareval_cf.report_judge_validity import (  # noqa: E402
    verdict,
    write_review_package,
)
from diagnostics.cleareval_cf.review_gold import (  # noqa: E402
    GoldReview,
    ValidationError,
    assemble_gold,
)


def _row(prefix: str = "reviewer_A_", **overrides) -> dict:
    """A minimal-but-valid review-package row with one expert's labels filled."""
    row = {
        "pair_id": "MUT-001",
        "seed_id": "SEED-001",
        "question_id": 1,
        # programmatic proposal expectation (pre-filled by write_review_package)
        "expected_relation": "DEGRADED",
        "expected_affected_components": ["S_TIME"],
        "expected_location": "step 1.1 (programmatic)",
        "_review_filled": True,
        prefix + "seed_suitable_for_local_counterfactual_testing": True,
        prefix + "mutation_scientifically_valid": True,
        prefix + "expected_relation": "HARD_FAIL",
        prefix + "affected_cc_component": "S_TIME",
        prefix + "violation_location": "step 1.1 (expert location)",
        prefix + "hard_fail_status": True,
        prefix + "minimal_next_action": "LOCAL_EDIT",
        prefix + "supporting_rule_or_evidence_ids": ["kb:time_kb.json:x"],
        "reviewer_B_seed_suitable_for_local_counterfactual_testing": None,
        "reviewer_B_mutation_scientifically_valid": None,
        "reviewer_B_expected_relation": None,
        "reviewer_B_affected_cc_component": None,
        "reviewer_B_violation_location": "",
        "reviewer_B_hard_fail_status": None,
        "reviewer_B_minimal_next_action": None,
        "reviewer_B_supporting_rule_or_evidence_ids": [],
    }
    row.update(overrides)
    return row


class AssembleGoldTests(unittest.TestCase):
    """Critical finding #1: proposal expectations must never leak into Gold."""

    def test_assemble_gold_reads_only_expert_key(self):
        row = _row()
        gold = assemble_gold([row], reviewer_id="reviewer-1", expert="A")
        self.assertEqual(len(gold), 1)
        g = gold[0]
        # gold label comes from reviewer_A_expected_relation, NOT the proposal
        self.assertEqual(g.expected_relation.value, "HARD_FAIL")
        self.assertEqual(g.affected_component.value, "S_TIME")
        self.assertEqual(g.violation_location, "step 1.1 (expert location)")
        self.assertTrue(g.hard_fail_status)
        self.assertEqual(g.minimal_next_action.value, "LOCAL_EDIT")
        self.assertEqual(g.supporting_rule_or_evidence_ids, ["kb:time_kb.json:x"])
        self.assertEqual(g.reviewer_id, "reviewer-1")
        self.assertEqual(g.adjudication_status.value, "PENDING")

    def test_proposal_expectation_cannot_leak_into_gold(self):
        """Even when the expert leaves the gold relation NULL, the pre-filled
        programmatic expected_relation must NOT appear in gold (the old code
        silently mirrored it)."""
        row = _row()
        row["reviewer_A_expected_relation"] = None
        row["reviewer_A_affected_cc_component"] = None
        row["reviewer_A_violation_location"] = ""
        row["reviewer_A_hard_fail_status"] = None
        row["reviewer_A_minimal_next_action"] = None
        row["reviewer_A_supporting_rule_or_evidence_ids"] = []
        # only the flag fields remain filled -> row converts with no relation
        gold = assemble_gold([row], reviewer_id="reviewer-1", expert="A")
        self.assertEqual(len(gold), 1)
        self.assertIsNone(gold[0].expected_relation)
        self.assertIsNone(gold[0].affected_component)
        self.assertEqual(gold[0].violation_location, "")
        self.assertIsNone(gold[0].hard_fail_status)
        self.assertIsNone(gold[0].minimal_next_action)
        # a fully-empty expert row is skipped entirely (covered by 9.7)
        blank = _row()
        for k in list(blank):
            if k.startswith("reviewer_A_") and k != "reviewer_A_supporting_rule_or_evidence_ids":
                blank[k] = None
            elif k.startswith("reviewer_A_"):
                blank[k] = []
        self.assertEqual(assemble_gold([blank], "r", expert="A"), [])

    def test_expert_slots_are_independent(self):
        row_a = _row(prefix="reviewer_A_", _review_filled=True,
                     reviewer_A_expected_relation="EQUIVALENT",
                     reviewer_B_expected_relation="HARD_FAIL")
        ga = assemble_gold([row_a], "reviewer-a", expert="A")
        gb = assemble_gold([row_a], "reviewer-b", expert="B")
        self.assertEqual(len(ga), 1)
        self.assertEqual(len(gb), 1)
        self.assertEqual(ga[0].expected_relation.value, "EQUIVALENT")
        self.assertEqual(gb[0].expected_relation.value, "HARD_FAIL")
        self.assertEqual(ga[0].reviewer_id, "reviewer-a")
        self.assertEqual(gb[0].reviewer_id, "reviewer-b")
        with self.assertRaises(ValueError):
            assemble_gold([row_a], "r", expert="C")

    def test_adjudicated_requires_review_trail(self):
        rows = [_row()]
        gold = assemble_gold(rows, "reviewer-1", adjudicated=True,
                             gold_note="both experts and adjudicator agree")
        self.assertEqual(gold[0].adjudication_status.value, "ADJUDICATED")
        self.assertEqual(gold[0].gold_note, "both experts and adjudicator agree")
        # adjudicated without a gold_note is refused
        with self.assertRaises(ValidationError):
            assemble_gold(rows, "reviewer-1", adjudicated=True, gold_note="")

    def test_gold_review_strict_review_fields(self):
        d = {
            "pair_id": "MUT-001", "seed_id": "SEED-001", "question_id": 1,
            "expected_relation": "HARD_FAIL", "reviewer_id": "r",
            "adjudication_status": "ADJUDICATED", "gold_note": "evidence",
        }
        g = GoldReview.from_dict(d)
        self.assertEqual(g.adjudication_status.value, "ADJUDICATED")
        # missing adjudication_status -> ValidationError (not silent PENDING)
        missing = {k: v for k, v in d.items() if k != "adjudication_status"}
        with self.assertRaises(ValidationError):
            GoldReview.from_dict(missing)
        # unknown adjudication_status -> ValidationError
        with self.assertRaises(ValidationError):
            GoldReview.from_dict({**d, "adjudication_status": "MAYBE"})
        # round trip
        self.assertEqual(GoldReview.from_dict(g.to_dict()), g)


class WriteReviewPackageTests(unittest.TestCase):
    def test_writes_72_rows_with_empty_expert_labels(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(tmp.name, "review_package.jsonl")
            rows = write_review_package(path)
            self.assertEqual(len(rows), 72)
            with open(path, "r", encoding="utf-8") as fh:
                on_disk = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(len(on_disk), 72)
            # programmatic expectation IS prefilled (for the reviewer's reference)...
            self.assertTrue(all("expected_relation" in r for r in on_disk))
            # ...but every expert label field is empty and unfilled
            for r in on_disk:
                self.assertFalse(r["_review_filled"])
                for key in ("reviewer_A_expected_relation",
                            "reviewer_B_expected_relation",
                            "reviewer_A_affected_cc_component",
                            "reviewer_B_affected_cc_component",
                            "reviewer_A_mutation_scientifically_valid",
                            "reviewer_B_minimal_next_action"):
                    self.assertIn(key, r)
                self.assertIsNone(r["reviewer_A_expected_relation"])
                self.assertIsNone(r["reviewer_B_expected_relation"])
            # the full package round-trips on ALL pair ids with zero gold
            # (nothing leaks into gold from an unfilled package)
            self.assertEqual(assemble_gold(on_disk, "nobody", expert="A"), [])
            self.assertEqual(assemble_gold(on_disk, "nobody", expert="B"), [])
        finally:
            tmp.cleanup()


class VerdictTests(unittest.TestCase):
    """Finding #8: verdict() must evaluate the blind metrics when provided."""

    def _metrics(self, acc=0.9, inv_ok=True, false_pass=0.05, loc=0.9):
        per = {"s_time": {"n_pairs_with_scores": 2, "n_within_tolerance": 2}}
        if not inv_ok:
            per["s_time"] = {"n_pairs_with_scores": 2, "n_within_tolerance": 0,
                             "max_abs_delta": 0.5}
        return {
            "9.1_directional_accuracy": {"accuracy_assessable": acc},
            "9.2_metamorphic_invariance": {"per_component": per},
            "9.4_fatal_false_pass": {"fatal_false_pass_rate": false_pass},
            "9.3_component_localization": {"affected_component_accuracy": loc},
        }

    def test_verdict_evaluates_blind_metrics_not_dev(self):
        # dev metrics alone would be LIMITED; the blind metrics support SUPPORTED
        dev = {"9.1_directional_accuracy": {"accuracy_assessable": None},
               "9.2_metamorphic_invariance": {"per_component": {}},
               "9.4_fatal_false_pass": {"fatal_false_pass_rate": None},
               "9.3_component_localization": {"affected_component_accuracy": None}}
        self.assertEqual(verdict(dev, blind_results=None), "LIMITED")
        blind = {"metrics": self._metrics(acc=0.9)}
        self.assertEqual(verdict(dev, blind_results=blind), "SUPPORTED")
        # a blind-run summary without metrics is not enough evidence
        self.assertEqual(verdict(dev, blind_results={"n_audit_rows": 0}), "LIMITED")
        # plain metrics dict (compute_all output) also works
        self.assertEqual(verdict(dev, blind_results=self._metrics(acc=0.9)), "SUPPORTED")

    def test_verdict_failure_paths(self):
        good = self._metrics()
        self.assertEqual(verdict({}, blind_results={"metrics": good}), "SUPPORTED")
        bad = self._metrics(acc=0.4, inv_ok=False, false_pass=0.9, loc=0.5)
        self.assertEqual(verdict({}, blind_results={"metrics": bad}), "FAILED_VALIDATION")


if __name__ == "__main__":
    unittest.main()
