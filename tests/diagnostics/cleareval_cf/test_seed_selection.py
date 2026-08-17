"""End-to-end tests for diagnostics/cleareval_cf/seed_selector.py (Task 1).

Offline: reads the real frozen dataset files under dataset/Q+AR (they
are local) and runs the selector into fresh temp directories.  All
assertions are on invariants of the selection/split, plus exact pool
statistics that pin the frozen corpus (if the frozen data is ever
regenerated, these tests fail loudly -- which is the point of a
diagnostic suite).
"""

import collections
import hashlib
import json
import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from diagnostics.cleareval_cf.schemas import (  # noqa: E402
    BlindSplitAccessError,
    SeedCandidate,
    SplitManifest,
    load_seed_candidates,
)
from diagnostics.cleareval_cf.seed_selector import (  # noqa: E402
    DEFAULT_SPLIT_SEED,
    MODEL_NAMES,
    ScenarioType,
    assert_split_access,
    build_pool,
    derive_scenario_type,
    load_split_manifest,
)

# Pinned frozen-corpus statistics (see DATA_SUMMARY.md section 3).
EXPECTED_ELIGIBLE = 71
EXPECTED_REJECTIONS = {
    "critical_warnings_present": 3216,
    "missing_cc_score_totals": 1,
    "missing_response_record": 1,
}
EXPECTED_PER_MODEL_ELIGIBLE = {
    "gemini-3-flash": 5,
    "gemini-3-pro": 5,
    "glm4.7-thinking": 6,
    "glm4.7-unthinking": 6,
    "openai_claude-sonnet-4.6": 4,
    "openai_deepseek-chat": 3,
    "openai_deepseek-reasoner": 2,
    "openai_gpt-5.2-fast": 22,
    "openai_gpt-5.2-thinking": 15,
    "openai_qwen3-14b": 0,
    "openai_qwen3-235b": 0,
    "openai_qwen3-32b": 0,
    "openai_qwen3-max": 3,
}
# Documented RNG outcome (split seed 20260817): drawn stratum order
# ERROR_CORRECTION, SIMPLE_GENERATION, COMPLEX_GENERATION -> the last
# drawn stratum (COMPLEX_GENERATION) holds only 4 development seeds.
EXPECTED_DEV_PER_STRATUM = {
    "SIMPLE_GENERATION": 6,
    "COMPLEX_GENERATION": 4,
    "ERROR_CORRECTION": 6,
}


def _sha256_bytes(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class SeedSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_a = tempfile.TemporaryDirectory()
        cls.tmp_b = tempfile.TemporaryDirectory()
        cls.out_a = os.path.join(cls.tmp_a.name, "manifests")
        cls.out_b = os.path.join(cls.tmp_b.name, "manifests")
        cls.rep_a = os.path.join(cls.tmp_a.name, "reports")

        from diagnostics.cleareval_cf.seed_selector import run

        cls.summary_a = run(_REPO_ROOT, cls.out_a, cls.rep_a, split_seed=DEFAULT_SPLIT_SEED)
        cls.summary_b = run(_REPO_ROOT, cls.out_b, os.path.join(cls.tmp_b.name, "reports"), split_seed=DEFAULT_SPLIT_SEED)

        cls.seed_path_a = cls.summary_a["seed_candidates_path"]
        cls.seed_path_b = cls.summary_b["seed_candidates_path"]
        cls.manifest_path_a = cls.summary_a["split_manifest_path"]
        cls.manifest_path_b = cls.summary_b["split_manifest_path"]

        cls.seeds = load_seed_candidates(cls.seed_path_a)
        with open(cls.manifest_path_a, "r", encoding="utf-8") as fh:
            cls.manifest_dict = json.load(fh)
        cls.manifest = SplitManifest.from_dict(cls.manifest_dict)

    @classmethod
    def tearDownClass(cls):
        cls.tmp_a.cleanup()
        cls.tmp_b.cleanup()

    # -- determinism -----------------------------------------------------

    def test_seed_candidates_byte_identical(self):
        with open(self.seed_path_a, "rb") as fa, open(self.seed_path_b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_split_manifest_byte_identical(self):
        with open(self.manifest_path_a, "rb") as fa, open(self.manifest_path_b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_report_byte_identical(self):
        report_a = os.path.join(self.rep_a, "DATA_SUMMARY.md")
        report_b = os.path.join(os.path.dirname(self.manifest_path_b), "..", "reports", "DATA_SUMMARY.md")
        with open(report_a, "rb") as fa, open(report_b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    # -- counts / structure ---------------------------------------------

    def test_24_seeds_8_per_stratum(self):
        self.assertEqual(len(self.seeds), 24)
        per_stratum = collections.Counter(s.scenario_type.value for s in self.seeds)
        for stratum in ("SIMPLE_GENERATION", "COMPLEX_GENERATION", "ERROR_CORRECTION"):
            self.assertEqual(per_stratum[stratum], 8)

    def test_seed_ids_sequential_and_unique(self):
        ids = [s.seed_id for s in self.seeds]
        self.assertEqual(ids, [f"SEED-{i:03d}" for i in range(1, 25)])

    def test_scenario_type_consistent_with_derivation(self):
        import json as _json

        with open(os.path.join(_REPO_ROOT, "dataset", "Q+AR", "src", "question_final.json"), "r", encoding="utf-8") as fh:
            questions = {r["question_id"]: r for r in _json.load(fh)}
        for seed in self.seeds:
            q = questions[seed.question_id]
            expected = derive_scenario_type(q["question"], len(q["marker_query_targets"]))
            self.assertEqual(
                seed.scenario_type, expected,
                f"seed {seed.seed_id} scenario_type inconsistent with question text",
            )

    def test_all_records_validate_and_round_trip(self):
        for rec in self.seeds:
            self.assertEqual(SeedCandidate.from_dict(rec.to_dict()), rec)
        # every record carries PENDING_SCREENING (nothing screened yet)
        self.assertTrue(all(s.screening_status.value == "PENDING_SCREENING" for s in self.seeds))
        # every record's source file + qid join to a real response
        self.assertTrue(all(s.source_file.startswith("dataset/Q+AR/model_response/") for s in self.seeds))
        self.assertTrue(all(s.question_id >= 1 for s in self.seeds))
        self.assertTrue(all(len(s.response_text) > 0 for s in self.seeds))

    # -- split isolation -------------------------------------------------

    def test_split_isolation_and_sizes(self):
        dev = set(self.manifest.development_seed_ids)
        blind = set(self.manifest.blind_seed_ids)
        self.assertEqual(len(dev), 16)
        self.assertEqual(len(blind), 8)
        self.assertEqual(dev | blind, {s.seed_id for s in self.seeds})
        self.assertTrue(dev.isdisjoint(blind), "seed-level split isolation violated")

    def test_dev_per_stratum_distribution(self):
        dev = set(self.manifest.development_seed_ids)
        per_stratum = collections.Counter(
            s.scenario_type.value for s in self.seeds if s.seed_id in dev
        )
        self.assertEqual(dict(per_stratum), EXPECTED_DEV_PER_STRATUM)

    def test_split_seed_and_created_from(self):
        self.assertEqual(self.manifest.split_seed, DEFAULT_SPLIT_SEED)
        self.assertEqual(self.manifest.created_from, _sha256_bytes(self.seed_path_a))
        self.assertIsNone(self.manifest.frozen_prompt_sha256)

    # -- pool statistics (pin the frozen corpus) -------------------------

    def test_pool_statistics_pinned(self):
        pool = build_pool(_REPO_ROOT)
        self.assertEqual(len(pool["candidates"]), EXPECTED_ELIGIBLE)
        self.assertEqual(dict(pool["rejections"]), EXPECTED_REJECTIONS)
        self.assertEqual(
            {m: pool["per_model_eligible"][m] for m in MODEL_NAMES},
            EXPECTED_PER_MODEL_ELIGIBLE,
        )

    # -- blind guard -----------------------------------------------------

    def test_blind_guard_blocks_development_role(self):
        blind_ids = self.manifest.blind_seed_ids
        dev_ids = self.manifest.development_seed_ids
        self.assertTrue(blind_ids and dev_ids)
        # direct seed-id access
        for bid in blind_ids:
            with self.assertRaises(BlindSplitAccessError):
                assert_split_access(bid, "development", manifest=self.manifest)
        # file-path access whose basename references a blind seed
        for bid in blind_ids:
            path = os.path.join(self.out_a, f"mutation_proposals_{bid}.jsonl")
            with self.assertRaises(BlindSplitAccessError):
                assert_split_access(path, "development", manifest=self.manifest)
        # development seeds are freely accessible
        for did in dev_ids:
            assert_split_access(did, "development", manifest=self.manifest)
            assert_split_access(
                os.path.join(self.out_a, f"mutation_proposals_{did}.jsonl"),
                "development",
                manifest=self.manifest,
            )

    def test_blind_role_is_unrestricted(self):
        for bid in self.manifest.blind_seed_ids:
            assert_split_access(bid, "blind", manifest=self.manifest)
            assert_split_access(
                os.path.join(self.out_a, f"mutation_proposals_{bid}.jsonl"),
                "blind",
                manifest=self.manifest,
            )

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            assert_split_access("SEED-001", "nobody", manifest=self.manifest)
        with self.assertRaises(ValueError):
            load_split_manifest(self.manifest_path_a, role="nobody")

    def test_load_split_manifest_role(self):
        m = load_split_manifest(self.manifest_path_a, role="development")
        self.assertEqual(m, self.manifest)

    def test_guard_default_manifest_loads(self):
        # default path must exist once the selector has run for real
        from diagnostics.cleareval_cf.seed_selector import DEFAULT_MANIFEST_PATH

        self.assertTrue(os.path.exists(DEFAULT_MANIFEST_PATH))
        m = load_split_manifest(role="development")
        with self.assertRaises(BlindSplitAccessError):
            assert_split_access(m.blind_seed_ids[0], "development", manifest=m)
        assert_split_access(m.development_seed_ids[0], "development", manifest=m)

    # -- role-routed seed loading (finding #15) ------------------------------

    def test_dev_role_seed_load_guarded(self):
        """The role-routed seed-loading API refuses the full manifest in dev
        role and accepts the dev-only manifest."""
        from diagnostics.cleareval_cf.seed_selector import DEFAULT_DEV_SEED_PATH, DEFAULT_SEED_PATH, load_seed_candidates_role

        with self.assertRaises(BlindSplitAccessError):
            load_seed_candidates_role(DEFAULT_SEED_PATH, "development")
        dev_seeds = load_seed_candidates_role(DEFAULT_DEV_SEED_PATH, "development")
        self.assertEqual(len(dev_seeds), 16)
        # dev-only manifest carries NO blind seed id
        blind_ids = set(self.manifest.blind_seed_ids)
        self.assertTrue(all(s.seed_id not in blind_ids for s in dev_seeds))
        # blind role may load the full manifest (one-directional opt-in)
        full = load_seed_candidates_role(DEFAULT_SEED_PATH, "blind")
        self.assertEqual(len(full), 24)

    # -- report ----------------------------------------------------------

    def test_report_exists_and_documents_split(self):
        report = os.path.join(self.rep_a, "DATA_SUMMARY.md")
        self.assertTrue(os.path.exists(report))
        with open(report, "r", encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("## 6. Chosen seeds (24; 8 per stratum)", text)
        self.assertIn("development_seed_ids", text)
        for bid in self.manifest.blind_seed_ids:
            self.assertIn(bid, text)
        self.assertIn("## 7. Development / blind split (seeds only)", text)


if __name__ == "__main__":
    unittest.main()
