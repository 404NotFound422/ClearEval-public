"""Offline saved-score -> stats -> actual consumer regressions; synthetic data only."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from results.aggregate_oeq import aggregate_file, write_stats, _hash
from results.aggregate_rag_baseline import aggregate_file as rag_aggregate
from results.calculate_main_table_score import load_oeq
from results.oeq_metrics import MAX_SCORES, METRIC_BLOCKS


def scored(qid, com=1, cor=1, eff=1):
    values = {"completeness": com, "correctness": cor, "effectiveness": eff}
    return {"question_id": qid, "evaluation": {"scores": {
        block: {key: {"score": maximum * (2 * eff - 1 if key == "s_method" else values[block])}
                for key, maximum in metrics.items()}
        for block, metrics in METRIC_BLOCKS.items()}}}


class StatsIntegrationTests(unittest.TestCase):
    def save(self, directory, items, model="synthetic"):
        path = Path(directory) / f"evaluation_results_{model}_1-shot.json"
        path.write_text(json.dumps(items), encoding="utf-8")
        manifest = Path(str(path) + ".manifest.json")
        if any(item.get("scoring_contract_sha256") == _hash({"fixture": 1}) for item in items):
            manifest.write_text(json.dumps({"contract": {"fixture": 1},
                "contract_sha256": _hash({"fixture": 1})}), encoding="utf-8")
        elif manifest.exists():
            manifest.unlink()  # Only this temporary fixture's generated manifest.
        return path

    def test_saved_scores_cli_stats_main_table_and_rag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.save(tmp, [scored(1, com=0), scored(2, cor=0)])
            output = Path(tmp) / "stats.jsonl"
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", "results/aggregate_oeq.py",
                 "--result-dir", tmp, "--output", str(output)],
                capture_output=True, text=True, check=True)
            self.assertIn("not scientific certification", completed.stdout)
            row = json.loads(output.read_text(encoding="utf-8"))
            table = load_oeq(output)["synthetic"]
            rag = rag_aggregate(path)
            self.assertEqual(row["application_index"], 0)
            self.assertEqual(table["I_A"], rag["I_A"])
            self.assertEqual(table["I_A_min_of_means"], 50)
            self.assertEqual(row["provenance_status"], "UNVERSIONED_HISTORICAL")
            self.assertEqual(table["scientific_status_counts"], {"UNSPECIFIED_HISTORICAL": 2})

    def test_protocol_validation_is_preserved(self):
        missing = scored(2)
        del missing["evaluation"]["scores"]["effectiveness"]["s_time"]
        bad = scored(3)
        bad["evaluation"]["scores"]["effectiveness"]["s_time"]["score"] = 4
        with tempfile.TemporaryDirectory() as tmp:
            row = aggregate_file(self.save(tmp, [scored(1), missing, bad, scored(4), scored("4")]))
            self.assertEqual(row["sample_count"], 1)
            self.assertEqual(row["total_items"], 5)
            self.assertEqual(row["coverage"], 0.2)
            self.assertEqual(len(row["excluded_items"]), 4)

    def test_mixed_contracts_and_duplicate_model_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = scored(1), scored(2)
            first["scoring_contract_sha256"] = "v1"
            second["scoring_contract_sha256"] = "v2"
            path = self.save(tmp, [first, second])
            with self.assertRaisesRegex(ValueError, "Mixed scoring"):
                aggregate_file(path)
            path = self.save(tmp, [scored(1)])
            another = Path(tmp) / "from_synthetic_1-shot_scoring.json"
            another.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            output = Path(tmp) / "out.jsonl"
            with self.assertRaisesRegex(ValueError, "Duplicate model"):
                write_stats([path, another], output)
            self.assertFalse(output.exists())

    def test_manifest_is_verified_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract = {"model": "synthetic", "setting": "1-shot", "scoring_version": "fixture-v1"}
            item = scored(1)
            item["scoring_contract_sha256"] = _hash(contract)
            path = self.save(tmp, [item])
            manifest = Path(str(path) + ".manifest.json")
            manifest.write_text(json.dumps({"contract": contract, "contract_sha256": _hash(contract)}),
                                encoding="utf-8")
            row = aggregate_file(path)
            self.assertEqual(row["scoring_contract"], contract)
            self.assertEqual(row["scoring_contract_sha256"], _hash(contract))
            contract["scoring_version"] = "changed"
            manifest.write_text(json.dumps({"contract": contract, "contract_sha256": item["scoring_contract_sha256"]}),
                                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                aggregate_file(path)


    def promoted(self, qid):
        from benchmark_scoring import promote_benchmark_estimate
        from evaluator_integrity import legacy_integrity_audit
        protocol = "Use synthetic method for 48 hours."
        extraction = {"method_name": "synthetic", "marker_dict": {},
                      "clearing_total_time_hours": 48}
        scores = scored(qid, com=0.5, cor=0.75, eff=0.25)["evaluation"]["scores"]
        raw = {key: copy.deepcopy(scores[key]) for key in ("completeness", "correctness")}
        identity = {"status": "RESOLVED_SINGLE", "components": [{"resolved_key": "synthetic"}]}
        integrity = legacy_integrity_audit(extraction, protocol, {
            "method_identity": identity, **{key: scores["effectiveness"][key]["score"]
                                           for key in METRIC_BLOCKS["effectiveness"]}})
        evaluation = {"technical_status": "VALID", "extraction": extraction,
                      "teacher_generation": {"technical_status": "VALID",
                                             "content": json.dumps({"scores": raw, "extraction": extraction})},
                      "legacy_diagnostics": {"scores": scores, "raw_teacher_scores": raw,
                                             "method_identity": identity},
                      "integrity": integrity}
        return {"question_id": qid, "scoring_contract_sha256": _hash({"fixture": 1}),
                "evaluation": promote_benchmark_estimate(
                    evaluation, protocol, {"numeric_scale_status": "UNCALIBRATED_PROJECTION_FOR_REVIEW"})}

    def test_promoted_estimate_reaches_actual_consumers_with_scope(self):
        from benchmark_scoring import BENCHMARK_INTERPRETATION
        with tempfile.TemporaryDirectory() as tmp:
            item = self.promoted(1)
            path = self.save(tmp, [item])
            output = Path(tmp) / "stats.jsonl"
            row = write_stats([path], output)[0]
            table = load_oeq(output)["synthetic"]
            rag = rag_aggregate(path)
            self.assertEqual(row["sample_count"], 1)
            self.assertEqual(table["I_A"], 25)
            self.assertEqual(table["I_A"], rag["I_A"])
            self.assertEqual(table["scientific_status_counts"], {"UNRESOLVED": 1})
            self.assertEqual(table["score_interpretation_counts"], {BENCHMARK_INTERPRETATION: 1})
            self.assertFalse(item["evaluation"]["cce_eligible"])
            self.assertIsNone(item["evaluation"]["official_scores"])

    def test_promoted_tampering_or_missing_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pristine = self.promoted(1)
            for field, value in (("official_scores", {}), ("cce_eligible", True),
                                 ("scientific_status", "CERTIFIED"),
                                 ("score_interpretation", None), ("scores_sha256", "changed")):
                with self.subTest(field=field):
                    item = copy.deepcopy(pristine)
                    item["evaluation"][field] = value
                    with self.assertRaisesRegex(ValueError, "Invalid automated"):
                        aggregate_file(self.save(tmp, [item]))
            item = copy.deepcopy(pristine)
            del item["scoring_contract_sha256"]
            with self.assertRaisesRegex(ValueError, "requires scoring contract"):
                aggregate_file(self.save(tmp, [item]))


    def test_rag_cli_retains_scope_and_valid_pair_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = [self.promoted(1), self.promoted(2)]
            treatment = [self.promoted(1), {"question_id": 2,
                         "scoring_contract_sha256": baseline[0]["scoring_contract_sha256"],
                         "evaluation": {"_error": "synthetic failure"}}]
            base = self.save(tmp, baseline)
            treatment_path = Path(tmp) / "evaluation_results_synthetic_1-shot+KB-RAG.json"
            treatment_path.write_text(json.dumps(treatment), encoding="utf-8")
            Path(str(treatment_path) + ".manifest.json").write_text(json.dumps({
                "contract": {"fixture": 1}, "contract_sha256": _hash({"fixture": 1})}), encoding="utf-8")
            output = Path(tmp) / "rag.csv"
            completed = subprocess.run([sys.executable, "-X", "utf8", "-B",
                "results/aggregate_rag_baseline.py", "--result-dir", tmp,
                "--models", "synthetic", "--csv", str(output)],
                capture_output=True, text=True, check=True)
            self.assertIn("not scientific certification", completed.stdout)
            with output.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["n_paired"], "1")
            self.assertEqual(rows[1]["coverage"], "0.5")
            self.assertEqual(json.loads(rows[1]["scientific_status_counts"])["UNRESOLVED"], 1)
            self.assertEqual(rows[1]["provenance_status"], "VERSIONED")
            broken = copy.deepcopy(treatment)
            broken[0]["evaluation"]["official_scores"] = {}
            treatment_path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid automated"):
                rag_aggregate(treatment_path)

    def test_rag_pair_rejects_incompatible_versions_and_stems(self):
        from results.aggregate_rag_baseline import checked_pair
        baseline = [scored(1)]
        treatment = [scored(1)]
        left = {"scoring_contract_sha256": "left", "scoring_contract": {
            "model": "synthetic", "setting": "1-shot", "scoring_version": "v1"}}
        right = {"scoring_contract_sha256": "right", "scoring_contract": {
            "model": "synthetic", "setting": "1-shot+KB-RAG", "scoring_version": "v1"}}
        self.assertEqual(checked_pair(baseline, treatment, left, right)["n_paired"], 1)
        right["scoring_contract"]["scoring_version"] = "v2"
        with self.assertRaisesRegex(ValueError, "contract versions"):
            checked_pair(baseline, treatment, left, right)
        right["scoring_contract"]["scoring_version"] = "v1"
        baseline[0]["evaluation"]["meta_data"] = {"question_sha256": "before"}
        treatment[0]["evaluation"]["meta_data"] = {"question_sha256": "after"}
        with self.assertRaisesRegex(ValueError, "Cannot pair"):
            checked_pair(baseline, treatment, left, right)
        with self.assertRaisesRegex(ValueError, "versioned and unversioned"):
            checked_pair(baseline, treatment, left, {})
        with self.assertRaisesRegex(ValueError, "without manifests"):
            checked_pair(baseline, treatment,
                         {"scoring_contract_sha256": "a"}, {"scoring_contract_sha256": "b"})

    def test_historical_single_record_rag_shape_remains_unversioned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "historical.json"
            path.write_text(json.dumps(scored(1)), encoding="utf-8")
            row = rag_aggregate(path)
            self.assertEqual(row["n"], 1)
            self.assertEqual(row["provenance_status"], "UNVERSIONED_HISTORICAL")

    def test_stats_cli_selects_explicit_shot_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evaluation_results_synthetic_0-shot.json"
            path.write_text(json.dumps([scored(1)]), encoding="utf-8")
            output = Path(tmp) / "stats.jsonl"
            subprocess.run([sys.executable, "-X", "utf8", "-B",
                "results/aggregate_oeq.py", "--result-dir", tmp, "--setting", "0-shot",
                "--output", str(output)], capture_output=True, text=True, check=True)
            self.assertEqual(load_oeq(output)["synthetic"]["sample_count"], 1)


if __name__ == "__main__":
    unittest.main()

