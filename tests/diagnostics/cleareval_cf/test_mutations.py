"""End-to-end tests for the Task 2 mutation overlay
(diagnostics/cleareval_cf/{mutation_builder, mutation_registry,
mutation_validator}.py).

Offline tests that run the real pipeline against the committed seed/split
manifests into fresh temp directories.  Covered invariants:

- 24 EQUIVALENT + 48 degrading = 72 records; degrading pairs balanced exactly
  8 per mutation_family; every seed hosts exactly 2 distinct families.
- Every record is PENDING_REVIEW with empty reviewer_ids / PENDING
  adjudication.
- Span integrity: re-applying declared spans to the seed response_text
  reproduces the mutated text exactly, no undeclared differences exist
  (masked comparison), EQUIVALENT pairs respect the empty changed_field_paths
  + surface_edits contract.  A negative test proves an undeclared edit /
  tampered span IS detected.
- Gold guard: promote_to_gold refuses without reviewers/evidence; a forged
  APPROVED_GOLD manifest is rejected at load.
- Split guard: development role cannot load the full 72-record manifest
  (BlindSplitAccessError); a development-only build loads fine and exposes
  exactly 16 dev seeds.
- Determinism: building twice produces byte-identical jsonl.
"""

import collections
import dataclasses
import filecmp
import json
import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from diagnostics.cleareval_cf.mutation_builder import (  # noqa: E402
    build,
    family_assignment,
)
from diagnostics.cleareval_cf.mutation_registry import (  # noqa: E402
    BlindSplitAccessError,
    MutationRegistry,
    ValidationError,
)
from diagnostics.cleareval_cf.mutation_validator import (  # noqa: E402
    check_equivalent,
    check_span_integrity,
    detect_undeclared_edits,
    validate_manifest,
)
from diagnostics.cleareval_cf.schemas import (  # noqa: E402
    AdjudicationStatus,
    ExpectedRelation,
    MutationFamily,
    MutationProposal,
    ReviewStatus,
    load_mutation_proposals,
    load_seed_candidates,
)

MANIFESTS = os.path.join(_REPO_ROOT, "diagnostics", "cleareval_cf", "manifests")
SEED_PATH = os.path.join(MANIFESTS, "seed_candidates.jsonl")
SPLIT_PATH = os.path.join(MANIFESTS, "split_manifest.json")
REPORTS = os.path.join(_REPO_ROOT, "diagnostics", "cleareval_cf", "reports")

FAMILIES = [
    "CLEARING_TIME_OUT_OF_RANGE",
    "METHOD_FLUOROPHORE_CONFLICT",
    "REQUIRED_INFORMATION_OMISSION",
    "SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT",
    "STEP_ORDER_OR_CHEMISTRY_CONFLICT",
    "TARGET_MARKER_MISMATCH",
]

SPLIT_RNG_SEED = 20260817


def _build_to(tmp, role="blind"):
    return build(
        seed_path=SEED_PATH,
        split_path=SPLIT_PATH,
        role=role,
        proposals_path=os.path.join(tmp, "mutation_proposals.jsonl"),
        gold_path=os.path.join(tmp, "reviewed_gold.jsonl"),
        build_report_path=os.path.join(tmp, "MUTATION_BUILD.md"),
    )


class MutationBuilderSuite(unittest.TestCase):
    """Full-corpus (blind) build: counts, balance, per-seed families."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-builder-")
        cls.summary = _build_to(cls.tmp)
        cls.props = load_mutation_proposals(cls.summary["proposals_path"])
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_counts_72_24_48(self):
        self.assertEqual(len(self.props), 72)
        eq = [p for p in self.props if p.expected_relation is ExpectedRelation.EQUIVALENT]
        deg = [p for p in self.props if p.expected_relation is not ExpectedRelation.EQUIVALENT]
        self.assertEqual(len(eq), 24)
        self.assertEqual(len(deg), 48)
        rel = collections.Counter(p.expected_relation.value for p in self.props)
        self.assertEqual(rel["EQUIVALENT"], 24)
        self.assertEqual(rel["DEGRADED"], 32)
        self.assertEqual(rel["HARD_FAIL"], 16)

    def test_family_balance_8_each(self):
        deg = [p for p in self.props if p.expected_relation is not ExpectedRelation.EQUIVALENT]
        counts = collections.Counter(p.mutation_family.value for p in deg)
        self.assertEqual(set(counts), set(FAMILIES))
        for fam in FAMILIES:
            self.assertEqual(counts[fam], 8, f"family {fam} not balanced")

    def test_each_seed_two_distinct_families(self):
        by_seed = collections.defaultdict(list)
        for p in self.props:
            if p.expected_relation is not ExpectedRelation.EQUIVALENT:
                by_seed[p.seed_id].append(p.mutation_family.value)
        self.assertEqual(len(by_seed), 24)
        for sid, fams in by_seed.items():
            self.assertEqual(len(fams), 2, sid)
            self.assertEqual(len(set(fams)), 2, f"{sid} repeated a family: {fams}")
            self.assertIn(sid, self.seeds)

    def test_all_pending_review_and_sequential_ids(self):
        ids = [p.pair_id for p in sorted(self.props, key=lambda p: p.pair_id)]
        self.assertEqual(ids, [f"MUT-{i:03d}" for i in range(1, 73)])
        for p in self.props:
            self.assertIs(p.review_status, ReviewStatus.PENDING_REVIEW)
            self.assertEqual(p.reviewer_ids, [])
            self.assertIs(p.adjudication_status, AdjudicationStatus.PENDING)

    def test_mutated_text_differs_from_seed(self):
        for p in self.props:
            seed_text = self.seeds[p.seed_id].response_text
            ok, _ = check_span_integrity(seed_text, p)
            self.assertTrue(ok, p.pair_id)

    def test_equivalent_contract(self):
        eq = [p for p in self.props if p.expected_relation is ExpectedRelation.EQUIVALENT]
        self.assertEqual(len(eq), 24)
        for p in eq:
            ok, msg = check_equivalent(self.seeds[p.seed_id].response_text, p)
            self.assertTrue(ok, f"{p.pair_id}: {msg}")


class MutationIntegritySuite(unittest.TestCase):
    """Span reconstruction + negative (undeclared/tampered) detection."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-integrity-")
        cls.props = load_mutation_proposals(_build_to(cls.tmp)["proposals_path"])
        cls.seeds = {s.seed_id: s for s in load_seed_candidates(SEED_PATH)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _two_span_pair(self):
        return next(
            p for p in self.props
            if len(p.original_text_spans) >= 2
            and p.expected_relation is not ExpectedRelation.EQUIVALENT
        )

    def test_no_undeclared_edits_all_pairs(self):
        for p in self.props:
            self.assertFalse(
                detect_undeclared_edits(self.seeds[p.seed_id].response_text, p),
                f"{p.pair_id} has undeclared differences",
            )

    def test_original_spans_slice_seed_exactly(self):
        for p in self.props:
            seed_text = self.seeds[p.seed_id].response_text
            for s in p.original_text_spans:
                self.assertEqual(seed_text[s.start:s.end], s.text, p.pair_id)

    def test_negative_tampered_mutated_span_detected(self):
        p = self._two_span_pair()
        seed_text = self.seeds[p.seed_id].response_text
        # baseline clean
        self.assertFalse(detect_undeclared_edits(seed_text, p))
        # tamper: lengthen the first mutated span -> reconstruction must differ
        spans = list(p.mutated_text_spans)
        spans[0] = dataclasses.replace(spans[0], text=spans[0].text + "!")
        tampered = dataclasses.replace(p, mutated_text_spans=spans)
        self.assertTrue(detect_undeclared_edits(seed_text, tampered))
        ok, _ = check_span_integrity(seed_text, tampered)
        self.assertFalse(ok, "tampered span must fail span integrity")

    def test_negative_tampered_original_span_detected(self):
        p = self._two_span_pair()
        seed_text = self.seeds[p.seed_id].response_text
        spans = list(p.original_text_spans)
        spans[0] = dataclasses.replace(spans[0], text="")
        tampered = dataclasses.replace(p, original_text_spans=spans)
        ok, _ = check_span_integrity(seed_text, tampered)
        self.assertFalse(ok, "original span that does not slice the seed must fail")

    def test_forged_extra_change_detected(self):
        """Manually extend the mutated span with an undeclared insertion."""
        p = self._two_span_pair()
        seed_text = self.seeds[p.seed_id].response_text
        spans = list(p.mutated_text_spans)
        original = spans[0].text
        spans[0] = dataclasses.replace(spans[0], text="__FORGED__" + original)
        forged = dataclasses.replace(p, mutated_text_spans=spans)
        self.assertTrue(detect_undeclared_edits(seed_text, forged))


class MutationRegistrySuite(unittest.TestCase):
    """Gold guard + split guard against a full-corpus build."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-registry-")
        _build_to(cls.tmp)
        cls.props_path = os.path.join(cls.tmp, "mutation_proposals.jsonl")
        cls.dev_tmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-registry-dev-")
        cls.dev = _build_to(cls.dev_tmp, role="development")
        cls.dev_path = cls.dev["proposals_path"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(cls.dev_tmp, ignore_errors=True)

    def _reg(self, role, proposals_path):
        return MutationRegistry(
            role=role,
            seed_path=SEED_PATH,
            proposals_path=proposals_path,
            split_path=SPLIT_PATH,
        )

    def test_development_role_rejects_full_manifest(self):
        reg = self._reg("development", self.props_path)
        with self.assertRaises(BlindSplitAccessError):
            reg.load_proposals()

    def test_blind_role_loads_full_manifest(self):
        reg = self._reg("blind", self.props_path)
        self.assertEqual(len(reg.load_proposals()), 72)
        self.assertEqual(len(reg.seeds), 24)

    def test_development_build_loads_under_development_role(self):
        reg = self._reg("development", self.dev_path)
        props = reg.load_proposals()
        self.assertEqual(len(props), 48)
        self.assertEqual(len(reg.seeds), 16)
        for p in props:
            self.assertEqual(reg.split_of(p.seed_id), "development")

    def test_counts_introspection(self):
        reg = self._reg("blind", self.props_path)
        by_rel = reg.counts_by_expected_relation()
        self.assertEqual(by_rel, {"EQUIVALENT": 24, "DEGRADED": 32, "HARD_FAIL": 16})
        by_split = reg.counts_by_split()
        self.assertEqual(by_split, {"development": 48, "blind": 24})
        by_fam = reg.counts_by_family()
        self.assertEqual(sum(by_fam.values()), 72)

    def test_promote_to_gold_requires_reviewers(self):
        reg = self._reg("blind", self.props_path)
        with self.assertRaises(ValidationError):
            reg.promote_to_gold("MUT-001", [], "some note")
        with self.assertRaises(ValidationError):
            reg.promote_to_gold("MUT-001", ["reviewer-1"], "   ")

    def test_promote_to_gold_succeeds_with_review_trail(self):
        reg = self._reg("blind", self.props_path)
        prom = reg.promote_to_gold("MUT-001", ["reviewer-1", "reviewer-2"], "human adjudication evidence")
        self.assertIs(prom.review_status, ReviewStatus.APPROVED_GOLD)
        self.assertEqual(prom.reviewer_ids, ["reviewer-1", "reviewer-2"])
        self.assertIs(prom.adjudication_status, AdjudicationStatus.ADJUDICATED)
        self.assertIn("gold_note: human adjudication evidence", prom.expected_location)
        # the registry now refuses a second promotion of the same pair
        with self.assertRaises(ValidationError):
            reg.promote_to_gold("MUT-001", ["another"], "again")

    def test_forged_approved_gold_rejected_at_load(self):
        props = load_mutation_proposals(self.props_path)
        forged = props[0].to_dict()
        forged["review_status"] = ReviewStatus.APPROVED_GOLD.value
        forged["reviewer_ids"] = []
        forged["adjudication_status"] = AdjudicationStatus.PENDING.value
        path = os.path.join(self.tmp, "forged_gold.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(forged, ensure_ascii=False, sort_keys=True) + "\n")
        reg = self._reg("blind", path)
        with self.assertRaises(ValidationError):
            reg.load_proposals()


class MutationDeterminismSuite(unittest.TestCase):
    """Byte-identical reruns and the committed-manifest end-to-end check."""

    def test_build_twice_byte_identical(self):
        d1 = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-det1-")
        d2 = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-det2-")
        try:
            p1 = _build_to(d1)["proposals_path"]
            p2 = _build_to(d2)["proposals_path"]
            self.assertTrue(filecmp.cmp(p1, p2, shallow=False))
            with open(p1, "rb") as fh1, open(p2, "rb") as fh2:
                self.assertEqual(fh1.read(), fh2.read())
        finally:
            shutil.rmtree(d1, ignore_errors=True)
            shutil.rmtree(d2, ignore_errors=True)

    def test_family_assignment_seeded_and_balanced(self):
        seed_ids = sorted(s.seed_id for s in load_seed_candidates(SEED_PATH))
        a1 = family_assignment(seed_ids)
        a2 = family_assignment(seed_ids)
        self.assertEqual(a1, a2)
        self.assertEqual(len(a1), 24)
        counts = collections.Counter(f for v in a1.values() for f in v)
        for fam in FAMILIES:
            self.assertEqual(counts[fam], 8)

    def test_committed_manifest_validates(self):
        proposals = os.path.join(MANIFESTS, "mutation_proposals.jsonl")
        self.assertTrue(os.path.isfile(proposals), "committed manifest must exist")
        build_report = os.path.join(REPORTS, "MUTATION_BUILD.md")
        if not os.path.isfile(build_report):
            build_report = ""
        vtmp = tempfile.mkdtemp(dir=MANIFESTS, prefix=".test-val-")
        try:
            summary = validate_manifest(
                proposals_path=proposals,
                seeds_path=SEED_PATH,
                split_path=SPLIT_PATH,
                build_report_path=build_report,
                validation_report_path=os.path.join(vtmp, "MUTATION_VALIDATION.md"),
            )
        finally:
            shutil.rmtree(vtmp, ignore_errors=True)
        self.assertTrue(summary["valid"], summary["problems"])
        self.assertEqual(summary["relations"], {"EQUIVALENT": 24, "DEGRADED": 32, "HARD_FAIL": 16})


if __name__ == "__main__":
    unittest.main()
