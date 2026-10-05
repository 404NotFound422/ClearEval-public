"""Independent-label separation and original-source grouping counterexamples."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluation_contract import json_hash
from experiments.evidence_materials.published_materials import (
    audit_input_separation, grouped_split, official_err_metrics, official_err_parse,
    build_parameter_facts, primary_materials, source_join, strict_err_parse,
)

UPSTREAM = Path(__file__).resolve().parents[1] / "experiments/evidence_materials/vendor"


class PublishedMaterialTests(unittest.TestCase):
    def test_original_source_duplicates_cannot_be_split_across_partitions(self):
        split = grouped_split(["doi:a", "doi:b", "doi:a", "doi:c"])
        self.assertEqual(len(split), 3)
        self.assertIn("development", split.values())
        self.assertIn("holdout", split.values())
        self.assertEqual(split, grouped_split(["doi:c", "doi:a", "doi:b"]))

    def test_one_source_is_not_falsely_claimed_as_holdout(self):
        self.assertEqual(grouped_split(["same"]), {"same": "UNASSIGNED_INSUFFICIENT_SOURCE_GROUPS"})

    def test_unique_full_protocol_join_uses_real_source_not_instance_id(self):
        rows = [{"id": "ERR-01", "corrected_text": "Add 15 microliters."}]
        protocols = [{"id": "original", "url": "doi:a", "protocol": "Step 1\nAdd 15   microliters.\nStep 2"}]
        joined, missing = source_join(rows, protocols)
        self.assertEqual(joined["ERR-01"]["id"], "original")
        self.assertFalse(missing)

    def test_nonunique_source_or_changed_units_are_not_guessed(self):
        rows = [{"id": "ERR-01", "corrected_text": "Add 15 microliters."}]
        protocols = [{"protocol": "Add 15 microliters."}, {"protocol": "Add 15 microliters."}]
        joined, unavailable = source_join(rows, protocols)
        self.assertFalse(joined)
        self.assertEqual(unavailable[0]["source_matches"], 2)
        joined, unavailable = source_join(rows, [{"protocol": "Add 15 milliliters."}])
        self.assertFalse(joined)
        self.assertEqual(unavailable[0]["source_matches"], 0)

    def test_gold_and_corrected_step_never_enter_model_input(self):
        payload = {"protocol": "Candidate", "source_cards": []}
        case = {"id": "x", "label_key": "x", "source_group": "doi:x", "split": "development",
                "input": payload, "input_sha256": json_hash(payload)}
        labels = [{"label_key": "x", "labels": {"is_correct": False}}]
        self.assertEqual(audit_input_separation([case], labels)["input_separation"], "VALID")
        contaminated = copy.deepcopy(case)
        contaminated["input"]["source_cards"] = [{"corrected_text": "hidden correction"}]
        contaminated["input_sha256"] = json_hash(contaminated["input"])
        with self.assertRaises(ValueError):
            audit_input_separation([contaminated], labels)

    def test_same_source_in_two_splits_is_rejected(self):
        payload = {"protocol": "Candidate"}
        cases = [{"id": str(i), "label_key": str(i), "source_group": "doi:a",
                  "split": split, "input": payload, "input_sha256": json_hash(payload)}
                 for i, split in enumerate(("development", "holdout"))]
        with self.assertRaises(ValueError):
            audit_input_separation(cases, [{"label_key": "0"}, {"label_key": "1"}])

    def test_actual_published_err_parser_and_metrics_are_reused_without_dependencies(self):
        self.assertTrue(official_err_parse("[ANSWER_START]True[ANSWER_END]", UPSTREAM))
        self.assertFalse(official_err_parse("[ANSWER_START]False[ANSWER_END]", UPSTREAM))
        metrics = official_err_metrics([False, True, False], [False, False, True], UPSTREAM)
        self.assertEqual(metrics["accuracy"], 1 / 3)
        self.assertEqual(metrics["recall"], 0.5)

    def test_ambiguous_official_parser_behavior_is_visible_not_silently_repaired(self):
        # The actual upstream heuristic accepts True when both tokens occur.
        self.assertTrue(official_err_parse("[ANSWER_START]True False[ANSWER_END]", UPSTREAM))
        with self.assertRaises(ValueError):
            strict_err_parse("[ANSWER_START]True False[ANSWER_END]")
        with self.assertRaises(ValueError):
            strict_err_parse("[ANSWER_START]False")

    def test_literal_source_validation_does_not_claim_scientific_applicability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "Published factual sentence."
            raw = b"<article>Published factual sentence.</article>"
            (root / "raw.html").write_bytes(raw)
            (root / "body.txt").write_bytes(body.encode())
            source = {"id": "PUBLICATION", "identity": {"doi": "doi:publication", "url": "https://example.org", "version": "v1"},
                      "snapshot": {"raw_path": "raw.html", "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                   "text_path": "body.txt", "text_sha256": hashlib.sha256(body.encode()).hexdigest()},
                      "passages": [{"id": "P1", "start": 0, "end": len(body), "quote": body,
                                    "sha256": hashlib.sha256(body.encode()).hexdigest()}]}
            (root / "KnowledgeBase").mkdir()
            registry = root / "KnowledgeBase/source_registry.json"
            registry.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            cases, labels, audit = primary_materials(root)
            self.assertFalse(labels[0]["independent_scientific_task_gold"])
            self.assertIsNone(labels[0]["scientific_applicability"])
            self.assertIsNone(labels[0]["wet_lab_success"])
            self.assertEqual(audit["scientific_necessity_validation"], "NOT_ESTABLISHED")
            source["passages"][0]["quote"] = "Fabricated quote."
            registry.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                primary_materials(root)


    def test_real_published_parameter_labels_are_literal_source_values_with_variant_scope(self):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "facts"
            manifest = build_parameter_facts(workspace, out)
            cases = [json.loads(line) for line in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
            labels = [json.loads(line) for line in (out / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(cases), 6)
            self.assertEqual(audit_input_separation(cases, labels)["input_separation"], "VALID")
            mapping = {row["label_key"]: row for row in labels}
            self.assertEqual(mapping["published-parameter:SEEDB2G_IMMERSION_RI"]["labels"]["refractive_index"], 1.46)
            self.assertEqual(mapping["published-parameter:SEEDB2S_IMMERSION_RI"]["labels"]["refractive_index"], 1.52)
            self.assertEqual(mapping["published-parameter:FDISCO_BEST_EGFP_ASSAY"]["labels"], {"temperature_C": 4.0, "pH": 9.0})
            for case in cases:
                label = mapping[case["label_key"]]
                body = case["input"]["protocol"]
                for support in label["field_support"].values():
                    self.assertEqual(body[support["start"]:support["end"]], support["quote"])
                self.assertFalse(label["scientific_quality_gold"])
                self.assertIsNone(label["wet_lab_success"])
            self.assertTrue(manifest["task_and_encoding_are_assistant_authored"])
            with self.assertRaises(ValueError):
                build_parameter_facts(workspace, out)


if __name__ == "__main__":
    unittest.main()
