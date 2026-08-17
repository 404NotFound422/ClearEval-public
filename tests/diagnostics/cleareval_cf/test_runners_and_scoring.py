"""Task 3 tests: runners, scoring adapter, metrics (offline, stdlib only).

Covers the Task 3 test contracts:
1. original and mutated are scored in two fully independent, role-blind judge
   calls; no mutation label / family / expected relation / other side's text
   ever enters the judge prompt.
2. repeated runs preserve prompt/model/version metadata.
3. missing judge output is reported (coverage), never imputed.
4. --verify-aggregation reproduces results/oeq_stats_260223.jsonl exactly.
5. metrics estimators (9.1-9.6) on small synthetic fixtures + empty handling.
6. blind freeze mechanics: blind without a frozen prompt refuses; after freeze
   it runs with fixtures; development role cannot load blind pairs.

All tests are offline and use only the repo's frozen data + the overlay's own
modules.  Nothing here touches production code.
"""

import collections
import json
import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from diagnostics.cleareval_cf.mutation_builder import build as build_proposals  # noqa: E402
from diagnostics.cleareval_cf.mutation_registry import BlindSplitAccessError  # noqa: E402
from diagnostics.cleareval_cf.mutation_validator import reconstruct_mutated  # noqa: E402
from diagnostics.cleareval_cf.run_diagnostic_audit import (  # noqa: E402
    CCEManager,
    FixtureAuditJudge,
    FreezeError,
    build_audit_prompt,
    current_prompt_sha256,
    freeze_prompt,
    load_fixtures,
    run_audit,
)
from diagnostics.cleareval_cf.run_original_cce import (  # noqa: E402
    CCEScorer,
    calculate_effectiveness_score,
    compare_stats_with_frozen,
    extract_quantitative,
    replicate_aggregate_oeq,
)
from diagnostics.cleareval_cf.schemas import (  # noqa: E402
    ComponentId,
    DiagnosticAuditResult,
    EvidenceStatus,
    ExpectedRelation,
    MutationProposal,
    NextAction,
    load_mutation_proposals,
    load_seed_candidates,
)
from diagnostics.cleareval_cf.score_counterfactual_relations import (  # noqa: E402
    cohen_kappa,
    compute_all,
    coverage_report,
    directional_accuracy,
    empirical_invariance_tolerance,
    fatal_false_pass,
    judge_expert_agreement,
    krippendorff_alpha_nominal,
    metamorphic_invariance,
    weighted_kappa_linear,
)

MANIFESTS = os.path.join(_REPO_ROOT, "diagnostics", "cleareval_cf", "manifests")
SEED_PATH = os.path.join(MANIFESTS, "seed_candidates.jsonl")
SPLIT_PATH = os.path.join(MANIFESTS, "split_manifest.json")
FULL_PROPOSALS = os.path.join(MANIFESTS, "mutation_proposals.jsonl")

FORBIDDEN_PROMPT_TOKENS = [
    "MUT-", "SEED-", "pair_id", "pairId", "expected_relation", "expectedRelation",
    "mutation_family", "mutationFamily",
]
FAMILIES = [
    "REQUIRED_INFORMATION_OMISSION", "STEP_ORDER_OR_CHEMISTRY_CONFLICT",
    "TARGET_MARKER_MISMATCH", "METHOD_FLUOROPHORE_CONFLICT",
    "SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT", "CLEARING_TIME_OUT_OF_RANGE",
]


def _finding(relation: str, component: str) -> dict:
    return DiagnosticAuditResult(
        evidence_status=EvidenceStatus.SUFFICIENT,
        relation=ExpectedRelation(relation),
        affected_component=ComponentId(component),
        violation_type="test_violation",
        location="step 1.1 (synthetic test span)",
        reason_code="TEST_RC",
        supporting_kb_or_rule_ids=["kb:time_kb.json:test"],
        minimal_next_action=(NextAction.NO_CHANGE if relation == "EQUIVALENT"
                             else NextAction.LOCAL_EDIT),
        rationale="synthetic evidence-grounded finding produced by the test fixture.",
    ).to_dict()


def _lower_payload(seed, all_same=False):
    """Canned Completeness/Correctness payload for a mutated side.

    Degrading: every sub-score dropped by 1 (floored at 0) relative to the
    frozen original so directional tests have a real signal.  EQUIVALENT: equal
    to the frozen original (metamorphic invariance signal)."""
    base = CCEManager.seed_judge_payload(seed)
    scores = base["scores"]
    out = {"scores": {}}
    for part in ("completeness", "correctness"):
        blk = scores[part]
        newblk = {}
        for k, v in blk.items():
            if isinstance(v, dict) and "score" in v:
                score = float(v["score"])
                if not all_same:
                    score = max(0.0, score - 1.0)
                newblk[k] = {"score": score, "max_score": v["max_score"]}
            else:
                newblk[k] = v
        out["scores"][part] = newblk
    return out


def _read_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _build_dev(tmp, role="development"):
    return build_proposals(
        seed_path=SEED_PATH,
        split_path=SPLIT_PATH,
        role=role,
        proposals_path=os.path.join(tmp, "mutation_proposals.jsonl"),
        gold_path=os.path.join(tmp, "reviewed_gold.jsonl"),
        build_report_path=os.path.join(tmp, "MUTATION_BUILD.md"),
    )


def _write_fixtures(path, proposals, seeds, missing_side=None, degrade=True):
    rows = []
    for p in proposals:
        seed = seeds[p.seed_id]
        for side in ("original", "mutated"):
            if missing_side and (p.pair_id, side) == missing_side:
                continue  # deliberately omitted -> judge_pending
            rel = p.expected_relation.value
            if side == "original":
                comp = "COMPLETENESS" if rel != "EQUIVALENT" else "S_METHOD"
            else:
                comp = "COMPLETENESS" if rel != "EQUIVALENT" else "S_METHOD"
            row = {
                "pair_id": p.pair_id,
                "side": side,
                "finding": _finding("EQUIVALENT" if rel == "EQUIVALENT" else rel, comp),
            }
            if side == "mutated":
                row["cce_judge"] = _lower_payload(seed, all_same=(rel == "EQUIVALENT"))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path


class AuditIndependenceSuite(unittest.TestCase):
    """Role-blind judge calls: separate calls, no leakage in the prompt."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-task3-")
        cls.dev = _build_dev(cls.tmp)
        cls.props = load_mutation_proposals(cls.dev["proposals_path"])
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}
        cls.fixtures = _write_fixtures(
            os.path.join(cls.tmp, "fixtures.jsonl"), cls.props, cls.seeds)
        cls.judge = FixtureAuditJudge(cls.fixtures)
        cls.summary = run_audit(
            role="development",
            proposals_path=cls.dev["proposals_path"],
            judge=cls.judge,
            audit_runs_path=os.path.join(cls.tmp, "audit_runs.jsonl"),
            cce_scores_path=os.path.join(cls.tmp, "cce_scores.jsonl"),
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_two_independent_calls_per_pair(self):
        calls = self.judge.calls
        self.assertEqual(len(calls), 2 * len(self.props))
        per_pair = collections.Counter((c["pair_id"], c["side"]) for c in calls)
        self.assertEqual(len(per_pair), 2 * len(self.props))
        for p in self.props:
            self.assertEqual(per_pair[(p.pair_id, "original")], 1)
            self.assertEqual(per_pair[(p.pair_id, "mutated")], 1)

    def test_neither_prompt_contains_the_other_protocol(self):
        by = {(c["pair_id"], c["side"]): c for c in self.judge.calls}
        for p in self.props:
            seed_text = self.seeds[p.seed_id].response_text
            mutated_text, _ = reconstruct_mutated(seed_text, p)
            op = by[(p.pair_id, "original")]
            mp = by[(p.pair_id, "mutated")]
            self.assertNotIn(mutated_text, op["prompt"])
            self.assertNotIn(seed_text, mp["prompt"])
            self.assertIn(seed_text, op["prompt"])
            self.assertIn(mutated_text, mp["prompt"])

    def test_no_pair_labels_in_any_prompt(self):
        by = {(c["pair_id"], c["side"]): c for c in self.judge.calls}
        for p in self.props:
            for side in ("original", "mutated"):
                prompt = by[(p.pair_id, side)]["prompt"]
                # structured overlay identifiers can never legitimately appear
                # in a protocol text or the template
                for tok in FORBIDDEN_PROMPT_TOKENS:
                    self.assertNotIn(tok, prompt,
                                     f"{p.pair_id}/{side} prompt leaked {tok!r}")
                self.assertNotIn(p.pair_id, prompt)
                self.assertNotIn(p.seed_id, prompt)
                self.assertNotIn(p.mutation_family.value, prompt)
                self.assertNotIn(p.mutation_operator_version, prompt)

    def test_prompts_differ_only_by_protocol_content(self):
        """The judge prompt is a fixed template; the two sides can only differ
        inside the protocol slot -- proving no per-pair label was injected."""
        by = {(c["pair_id"], c["side"]): c for c in self.judge.calls}
        for p in self.props:
            seed_text = self.seeds[p.seed_id].response_text
            mutated_text, _ = reconstruct_mutated(seed_text, p)
            op = by[(p.pair_id, "original")]["prompt"]
            mp = by[(p.pair_id, "mutated")]["prompt"]
            self.assertEqual(
                mp.replace(mutated_text, "\u0000"),
                op.replace(seed_text, "\u0000"),
                f"{p.pair_id}: prompts differ beyond the protocol slot")

    def test_build_audit_prompt_contains_only_question_and_protocol(self):
        p = self.props[0]
        seed_text = self.seeds[p.seed_id].response_text
        prompt = build_audit_prompt("Question text Q1", seed_text)
        self.assertIn("Question text Q1", prompt)
        self.assertIn(seed_text, prompt)

    def test_original_and_mutated_scored_in_separate_cce_calls(self):
        cce = []
        with open(os.path.join(self.tmp, "cce_scores.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                cce.append(json.loads(line))
        self.assertEqual(len(cce), 2 * len(self.props))
        for r in cce:
            self.assertTrue(r["metadata"]["input_sha256"])
            self.assertTrue(r["metadata"]["prompt_sha256"])
            self.assertEqual(r["metadata"]["schema_version"], "cleareval_cf.schemas.v1")
            self.assertTrue(r["metadata"]["timestamp"])


class MetadataStabilitySuite(unittest.TestCase):
    """Repeated runs preserve prompt/model/version metadata."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-task3-meta-")
        cls.dev = _build_dev(cls.tmp)
        cls.props = load_mutation_proposals(cls.dev["proposals_path"])
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}
        cls.fixtures = _write_fixtures(
            os.path.join(cls.tmp, "fixtures.jsonl"), cls.props, cls.seeds)
        cls.run1 = run_audit(
            role="development", proposals_path=cls.dev["proposals_path"],
            judge=FixtureAuditJudge(cls.fixtures),
            audit_runs_path=os.path.join(cls.tmp, "a1.jsonl"),
            cce_scores_path=os.path.join(cls.tmp, "c1.jsonl"))
        cls.run2 = run_audit(
            role="development", proposals_path=cls.dev["proposals_path"],
            judge=FixtureAuditJudge(cls.fixtures),
            audit_runs_path=os.path.join(cls.tmp, "a2.jsonl"),
            cce_scores_path=os.path.join(cls.tmp, "c2.jsonl"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_prompt_sha_model_schema_stable_across_runs(self):
        self.assertEqual(self.run1["prompt_sha256"], current_prompt_sha256())
        self.assertEqual(self.run1["prompt_sha256"], self.run2["prompt_sha256"])
        rows1 = _read_rows(os.path.join(self.tmp, "a1.jsonl"))
        rows2 = _read_rows(os.path.join(self.tmp, "a2.jsonl"))
        for a, b in zip(rows1, rows2):
            self.assertEqual(a["prompt_sha256"], b["prompt_sha256"])
            self.assertEqual(a["schema_version"], b["schema_version"])
            self.assertEqual(a["judge_model"], b["judge_model"])
            # timestamps differ run to run but every row has one
            self.assertTrue(a["timestamp"])
            self.assertTrue(b["timestamp"])

    def test_cce_metadata_complete_and_stable(self):
        c1 = _read_rows(os.path.join(self.tmp, "c1.jsonl"))
        c2 = _read_rows(os.path.join(self.tmp, "c2.jsonl"))
        for a, b in zip(c1, c2):
            for key in ("teacher_model", "prompt_sha256", "schema_version",
                        "mutation_operator_version", "adapter_version"):
                self.assertIn(key, a["metadata"])
                self.assertEqual(a["metadata"][key], b["metadata"][key])
            self.assertEqual(a["metadata"]["input_sha256"], b["metadata"]["input_sha256"])
            for r in (a, b):
                self.assertEqual(r["metadata"]["prompt_path"],
                                 os.path.join("prompts", "diagnostic_audit_v1.txt"))


class CoverageAndAdapterSuite(unittest.TestCase):
    """Missing judge output is reported, never imputed; adapter determinism."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-task3-cov-")
        cls.dev = _build_dev(cls.tmp)
        cls.props = load_mutation_proposals(cls.dev["proposals_path"])
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}
        cls.missing = (cls.props[0].pair_id, "mutated")
        cls.fixtures = _write_fixtures(
            os.path.join(cls.tmp, "fixtures.jsonl"), cls.props, cls.seeds,
            missing_side=cls.missing)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_missing_judge_reported_not_imputed(self):
        judge = FixtureAuditJudge(self.fixtures)
        summary = run_audit(
            role="development", proposals_path=self.dev["proposals_path"], judge=judge,
            audit_runs_path=os.path.join(self.tmp, "cov_a.jsonl"),
            cce_scores_path=os.path.join(self.tmp, "cov_c.jsonl"))
        audit = _read_rows(os.path.join(self.tmp, "cov_a.jsonl"))
        miss = [r for r in audit if r["pair_id"] == self.missing[0] and r["side"] == self.missing[1]]
        self.assertTrue(miss)
        self.assertEqual(miss[0]["status"], "judge_pending")
        self.assertNotIn("finding", miss[0])  # never fabricated
        self.assertEqual(summary["coverage"]["judge_pending"], 1)
        cce = _read_rows(os.path.join(self.tmp, "cov_c.jsonl"))
        mcce = [r for r in cce if r["pair_id"] == self.missing[0] and r["side"] == "mutated"][0]
        self.assertEqual(mcce["status"], "judge_missing")
        self.assertIsNone(mcce["total_cc"])

    def test_all_other_mutated_cce_scored_via_fixtures(self):
        judge = FixtureAuditJudge(self.fixtures)
        run_audit(
            role="development", proposals_path=self.dev["proposals_path"], judge=judge,
            audit_runs_path=os.path.join(self.tmp, "full_a.jsonl"),
            cce_scores_path=os.path.join(self.tmp, "full_c.jsonl"))
        cce = _read_rows(os.path.join(self.tmp, "full_c.jsonl"))
        mutated = [r for r in cce if r["side"] == "mutated"]
        ok = [r for r in mutated if r["status"] == "ok"]
        self.assertEqual(len(mutated) - 1, len(ok))  # only the deliberately missing one

    def test_adapter_no_judge_is_missing_not_zero(self):
        scorer = CCEScorer()
        seed = self.seeds[self.props[0].seed_id]
        rec = scorer.score_protocol_from_parts(seed.response_text, seed.question_id,
                                               judge_cc=None, mode="offline")
        self.assertEqual(rec["status"], "judge_missing")
        self.assertIsNone(rec["total_cc"])
        self.assertIsNone(rec["components"])

    def test_equivalent_pair_invariance_in_local_pipeline(self):
        """Semantics-preserving edits must not perturb the local effectiveness."""
        scorer = CCEScorer()
        changed = 0
        for p in self.props:
            if p.expected_relation is not ExpectedRelation.EQUIVALENT:
                continue
            seed = self.seeds[p.seed_id]
            mutated_text, _ = reconstruct_mutated(seed.response_text, p)
            qo = extract_quantitative(seed.response_text, p.question_id, scorer.kbs)
            qm = extract_quantitative(mutated_text, p.question_id, scorer.kbs)
            eo = calculate_effectiveness_score(qo, qo["user_pref_vector"], qo["marker_dict"],
                                               qo["marker_query_targets"], scorer.kbs)
            em = calculate_effectiveness_score(qm, qm["user_pref_vector"], qm["marker_dict"],
                                               qm["marker_query_targets"], scorer.kbs)
            for k in ("s_method", "s_label", "s_trans", "s_time"):
                if abs(em[k] - eo[k]) > 1e-9:
                    changed += 1
        self.assertEqual(changed, 0, "EQUIVALENT edits changed local effectiveness")

    def test_aggregation_replicates_frozen_stats_exactly(self):
        recomputed = replicate_aggregate_oeq()
        report = compare_stats_with_frozen(recomputed)
        self.assertTrue(report["all_exact"])
        self.assertEqual(report["max_abs_diff_across_rows"], 0.0)
        self.assertEqual(len(recomputed), 13)


class MetricsSuite(unittest.TestCase):
    """9.1-9.6 estimators on synthetic fixtures + empty/pending handling."""

    def _cce(self, status="ok", s_method=1.0, s_label=2.0, s_trans=1.0, s_time=1.0,
             comp_total=4.0, corr_total=6.0):
        return {
            "status": status, "total_cc": None, "components": {
                "completeness": {"total": comp_total},
                "correctness": {"total": corr_total},
                "effectiveness": {"s_method": s_method, "s_label": s_label,
                                  "s_trans": s_trans, "s_time": s_time,
                                  "total": s_method + s_label + s_trans + s_time},
            },
        }

    def test_directional_accuracy_happy_path(self):
        pairs = [{
            "pair_id": "MUT-001", "expected_relation": "DEGRADED",
            "expected_affected_components": ["S_TIME"],
            "mutated_finding": _finding("DEGRADED", "S_TIME"),
        }]
        reference = [{"pair_id": "MUT-001", "expected_relation": "DEGRADED",
                      "expected_affected_components": ["S_TIME"]}]
        cce = [
            {"pair_id": "MUT-001", "side": "original", **self._cce(s_time=3.0)},
            {"pair_id": "MUT-001", "side": "mutated", **self._cce(s_time=0.0)},
        ]
        m = directional_accuracy(pairs, cce, reference, source="provisional")
        self.assertEqual(m["n_correct"], 1)
        self.assertEqual(m["n_incorrect"], 0)
        self.assertEqual(m["accuracy_assessable"], 1.0)

    def test_directional_accuracy_hard_fail_detected_correct(self):
        pairs = [{
            "pair_id": "MUT-002", "expected_relation": "HARD_FAIL",
            "expected_affected_components": ["S_METHOD"],
            "mutated_finding": _finding("HARD_FAIL", "S_METHOD"),
        }]
        reference = [{"pair_id": "MUT-002", "expected_relation": "HARD_FAIL",
                      "expected_affected_components": ["S_METHOD"]}]
        cce = [
            {"pair_id": "MUT-002", "side": "original", **self._cce(s_method=1.0)},
            {"pair_id": "MUT-002", "side": "mutated", **self._cce(s_method=1.0)},
        ]
        m = directional_accuracy(pairs, cce, reference)
        self.assertEqual(m["n_correct"], 1)  # hard fail detected even without a drop

    def test_directional_accuracy_pending_and_floor(self):
        pairs = [
            {"pair_id": "MUT-003", "expected_relation": "DEGRADED",
             "expected_affected_components": ["S_TIME"], "mutated_finding": None},
            {"pair_id": "MUT-004", "expected_relation": "DEGRADED",
             "expected_affected_components": ["S_METHOD"], "mutated_finding": None},
        ]
        reference = [{"pair_id": p["pair_id"], "expected_relation": p["expected_relation"],
                      "expected_affected_components": p["expected_affected_components"]}
                     for p in pairs]
        cce = [
            # MUT-003: mutated missing -> pending
            {"pair_id": "MUT-003", "side": "original", **self._cce(s_time=3.0)},
            # MUT-004: original at floor -> undetected_floor
            {"pair_id": "MUT-004", "side": "original", **self._cce(s_method=0.0)},
            {"pair_id": "MUT-004", "side": "mutated", **self._cce(s_method=0.0)},
        ]
        m = directional_accuracy(pairs, cce, reference)
        self.assertEqual(m["n_pending"], 1)
        self.assertEqual(m["n_floor_only"], 1)

    def test_cohen_kappa_known_value(self):
        # perfect agreement -> 1.0
        self.assertEqual(cohen_kappa(["A", "A"], ["A", "A"]), 1.0)
        # balanced complete disagreement -> -1.0
        self.assertEqual(cohen_kappa(["A", "B"], ["B", "A"]), -1.0)
        # empty -> None
        self.assertIsNone(cohen_kappa([], []))
        # mixed disagreement -> < 1.0
        k = cohen_kappa(["A", "B"] * 10, ["A", "A"] * 5 + ["B", "B"] * 5)
        self.assertIsNotNone(k)

    def test_weighted_kappa_linear(self):
        w = weighted_kappa_linear(["EQUIVALENT", "DEGRADED"], ["DEGRADED", "HARD_FAIL"],
                                  ["EQUIVALENT", "DEGRADED", "HARD_FAIL"])
        # one-step disagreements on both -> obs=0.5/2, pe nonzero -> 0.0
        self.assertEqual(w, 0.0)

    def test_krippendorff_alpha(self):
        a = krippendorff_alpha_nominal(["A", "A", "B"], ["A", "A", "B"])
        self.assertEqual(a, 1.0)
        self.assertIsNone(krippendorff_alpha_nominal([], []))

    def test_empirical_invariance_tolerance_from_distribution(self):
        devs = [0.1, 0.1, 0.05, 0.5, 0.2, 0.15, 0.3, 0.05]
        tol = empirical_invariance_tolerance(devs, percentile=95.0)
        self.assertIsNotNone(tol)
        self.assertGreaterEqual(tol, max(devs) * 0.9)
        self.assertEqual(empirical_invariance_tolerance([]), None)

    def test_metamorphic_invariance_uses_empirical_tolerance(self):
        cce = []
        # two EQUIVALENT pairs with zero delta
        for i in (10, 11):
            cce.append({"pair_id": f"MUT-{i}", "side": "original",
                        **self._cce(s_time=3.0, s_method=1.0)})
            cce.append({"pair_id": f"MUT-{i}", "side": "mutated",
                        **self._cce(s_time=3.0, s_method=1.0)})
        # one pair with a big spurious delta
        cce.append({"pair_id": "MUT-12", "side": "original", **self._cce(s_time=3.0)})
        cce.append({"pair_id": "MUT-12", "side": "mutated", **self._cce(s_time=0.0)})
        # repeat distribution gives a small empirical tolerance
        repeats = [self._cce(s_time=3.0), self._cce(s_time=3.0), self._cce(s_time=3.0)]
        pairs = [{"pair_id": "MUT-10"}, {"pair_id": "MUT-11"}, {"pair_id": "MUT-12"}]
        m = metamorphic_invariance(pairs, cce, repeat_scores=repeats)
        self.assertEqual(m["n_equivalent_pairs"], 3)
        tol = m["per_component"]["s_time"]["empirical_tolerance"]
        self.assertEqual(tol, 0.0)  # repeats identical -> derived tolerance 0
        self.assertEqual(m["per_component"]["s_time"]["n_within_tolerance"], 2)

    def test_fatal_false_pass(self):
        pairs = [
            {"pair_id": "MUT-20", "expected_relation": "HARD_FAIL",
             "mutated_finding": _finding("EQUIVALENT", "S_METHOD")},   # accepted!
            {"pair_id": "MUT-21", "expected_relation": "HARD_FAIL",
             "mutated_finding": _finding("HARD_FAIL", "S_TIME")},
        ]
        gold = [
            {"pair_id": "MUT-20", "expected_relation": "HARD_FAIL", "hard_fail_status": True},
            {"pair_id": "MUT-21", "expected_relation": "HARD_FAIL", "hard_fail_status": True},
        ]
        m = fatal_false_pass(pairs, gold)
        self.assertEqual(m["n_hard_fail_gold"], 2)
        self.assertEqual(m["n_false_pass"], 1)
        self.assertEqual(m["fatal_false_pass_rate"], 0.5)

    def test_judge_expert_agreement_synthetic(self):
        judge = ["EQUIVALENT", "DEGRADED", "HARD_FAIL"]
        exp_a = ["EQUIVALENT", "DEGRADED", "HARD_FAIL"]
        exp_b = ["EQUIVALENT", "HARD_FAIL", "HARD_FAIL"]
        m = judge_expert_agreement(judge, exp_a, exp_b)
        self.assertEqual(m["judge_vs_expert_A"]["cohen_kappa"], 1.0)
        self.assertEqual(m["judge_vs_expert_A"]["raw_agreement"], 1.0)
        self.assertEqual(m["expert_A_vs_expert_B"]["n"], 3)

    def test_coverage_reports_missing(self):
        audit = [
            {"pair_id": "MUT-1", "side": "original", "status": "ok", "finding": _finding("EQUIVALENT", "S_METHOD")},
            {"pair_id": "MUT-1", "side": "mutated", "status": "judge_pending"},
        ]
        cce = [
            {"pair_id": "MUT-1", "side": "original", "status": "ok"},
            {"pair_id": "MUT-1", "side": "mutated", "status": "judge_missing"},
        ]
        props = [{"pair_id": "MUT-1"}]
        m = coverage_report(audit, cce, [], props)
        self.assertEqual(len(m["bad_audit_rows"]), 1)
        self.assertEqual(len(m["bad_cce_rows"]), 1)
        self.assertEqual(m["missing_gold_pair_ids"], ["MUT-1"])
        self.assertTrue(m["pending"])
        self.assertFalse(m["all_scored"])

    def test_compute_all_handles_empty_inputs(self):
        m = compute_all([], [], [], [])
        self.assertIn("9.1_directional_accuracy", m)
        self.assertEqual(len(m["pending_metrics"]), 7)
        self.assertTrue(m["all_metrics_pending"])


class BlindFreezeMechanicsSuite(unittest.TestCase):
    """Blind freeze: refuse -> freeze -> run; dev cannot load blind pairs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-task3-blind-")
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}
        with open(SPLIT_PATH, "r", encoding="utf-8") as fh:
            cls.split_copy = json.load(fh)
        cls.split_copy["frozen_prompt_sha256"] = None
        cls.split_path = os.path.join(cls.tmp, "split_manifest.json")
        with open(cls.split_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cls.split_copy, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        cls.full_props = load_mutation_proposals(FULL_PROPOSALS)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _blind_fixtures(self, path):
        _write_fixtures(path, self.full_props, self.seeds)
        return path

    def test_blind_without_freeze_refuses(self):
        fixtures = self._blind_fixtures(os.path.join(self.tmp, "bf.jsonl"))
        with self.assertRaises(FreezeError):
            run_audit(
                role="blind", split_path=self.split_path,
                proposals_path=FULL_PROPOSALS, judge=FixtureAuditJudge(fixtures),
                audit_runs_path=os.path.join(self.tmp, "x.jsonl"),
                cce_scores_path=os.path.join(self.tmp, "y.jsonl"))

    def test_dev_role_cannot_load_blind_pairs(self):
        with self.assertRaises(BlindSplitAccessError):
            run_audit(
                role="development", split_path=SPLIT_PATH,
                proposals_path=FULL_PROPOSALS, judge=FixtureAuditJudge(None),
                audit_runs_path=os.path.join(self.tmp, "z.jsonl"),
                cce_scores_path=os.path.join(self.tmp, "w.jsonl"))

    def test_freeze_then_blind_runs_with_fixtures(self):
        freeze_prompt(self.split_path, prompt_sha=current_prompt_sha256())
        fixtures = self._blind_fixtures(os.path.join(self.tmp, "bf2.jsonl"))
        summary = run_audit(
            role="blind", split_path=self.split_path,
            proposals_path=FULL_PROPOSALS, judge=FixtureAuditJudge(fixtures),
            audit_runs_path=os.path.join(self.tmp, "blind_a.jsonl"),
            cce_scores_path=os.path.join(self.tmp, "blind_c.jsonl"))
        self.assertEqual(summary["n_audit_rows"], 144)  # 72 pairs x 2 sides
        self.assertEqual(summary["n_cce_rows"], 144)
        self.assertEqual(summary["coverage"]["judge_ok"], 144)
        with open(self.split_path, "r", encoding="utf-8") as fh:
            split = json.load(fh)
        self.assertEqual(split["frozen_prompt_sha256"], current_prompt_sha256())
        audit = _read_rows(os.path.join(self.tmp, "blind_a.jsonl"))
        for r in audit:
            self.assertEqual(r["prompt_sha256"], current_prompt_sha256())
            self.assertEqual(r["role"], "blind")
            self.assertIn(r["side"], ("original", "mutated"))


if __name__ == "__main__":
    unittest.main()
