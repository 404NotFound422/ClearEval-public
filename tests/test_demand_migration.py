"""Meaningful migration counterexamples; synthetic tasks, no model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evaluation_contract import DEMAND_AXES, FixedDemandRegistry, json_hash
from experiments.evidence_materials.demand_migration import (
    derive_question, generate_bundle, validate_derivation, version_audit,
)


def question(text, qid=1, tier="T03_SMALL_WHOLE_SAMPLE_1_5MM"):
    return {"question_id": qid, "question": text,
            "tissue_hierarchy_from_tissue_xlsx": {"tissue_tier_code": tier},
            "marker_query_targets": []}


class DemandMigrationTests(unittest.TestCase):
    def test_generic_antibody_output_instructions_are_not_a_label_constraint(self):
        row = derive_question(question("定性观察三维结构。请仅输出 protocol，列出必要的标记前处理、探针/抗体孵育与洗涤。"))
        self.assertEqual(row["vector"]["dye_permeability"]["weight"], 0)
        self.assertEqual(row["vector"]["geometry_preference"]["weight"], 0)
        self.assertTrue(row["requirements"])

    def test_completed_qc_label_is_retained_without_requiring_repetition(self):
        row = derive_question(question("全组织免疫染色已完成且质控合格，无需重复。"))
        self.assertEqual(row["vector"]["dye_permeability"]["weight"], 0)
        self.assertTrue(row["completed_label_clauses"])
        self.assertIn("无需重复", row["requirements"][0]["support"]["quote"])

    def test_negated_reporter_is_not_a_positive_fp_demand(self):
        row = derive_question(question("不需要保留内源GFP荧光，采用抗体标记。"))
        self.assertEqual(row["vector"]["fluorescence_protein_preservation"]["weight"], 0)

    def test_true_explicit_reporter_has_exact_original_clause(self):
        q = question("必须保留内源GFP荧光。定性观察三维结构。")
        row = derive_question(q)
        self.assertEqual(row["vector"]["fluorescence_protein_preservation"], {"target": 1.0, "weight": 1.0})
        support = row["axis_audits"]["fluorescence_protein_preservation"]["evidence"][0]
        self.assertEqual(q["question"][support["start"]:support["end"]], support["quote"])
        self.assertIsNone(row["scientific_approval"])

    def test_large_tier_is_not_misassigned_to_dye_penetration(self):
        row = derive_question(question("仅观察报告荧光。", tier="T06_LONG_CNS_OR_TUBULAR_15_80MM"))
        self.assertEqual(row["vector"]["clearing_challenge"]["target"], 1.0)
        self.assertEqual(row["vector"]["dye_permeability"]["weight"], 0)
        self.assertEqual(row["axis_audits"]["clearing_challenge"]["status"], "METADATA_WITH_UNCALIBRATED_SCALE")

    def test_unknown_tier_is_not_silently_defaulted_as_required(self):
        row = derive_question(question("定性观察。", tier="UNKNOWN"))
        self.assertEqual(row["vector"]["clearing_challenge"]["weight"], 0)

    def test_forged_support_and_numeric_edit_are_rejected(self):
        q = question("必须保留内源GFP荧光。")
        row = derive_question(q)
        row["axis_audits"]["fluorescence_protein_preservation"]["evidence"][0]["quote"] = "made up"
        with self.assertRaises(ValueError):
            validate_derivation(q, row)
        row = derive_question(q)
        row["vector"]["dye_permeability"]["weight"] = 1
        with self.assertRaises(ValueError):
            validate_derivation(q, row)

    def test_revised_same_id_and_metadata_are_counted_separately(self):
        old = question("原始任务。")
        new = question("新任务。")
        new["marker_query_targets"] = [{"marker_name": "CD31"}]
        audit = version_audit([old], [new])
        self.assertEqual(audit["changed_records"], 1)
        self.assertEqual(audit["changed_field_counts"], {"marker_query_targets": 1, "question": 1})

    def test_new_bundle_derives_instead_of_rebinding_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before, current = [question("旧任务。")], [question("必须保留内源GFP荧光。")]
            previous = {"1": {axis: {"target": 9.0, "weight": 9.0} for axis in DEMAND_AXES}}
            values = {"before.json": before, "current.json": current, "old.json": previous,
                      "old.manifest.json": {"hash_format": "canonical-json-sha256-v1",
                                            "questions_sha256": json_hash(before),
                                            "demand_vectors_sha256": json_hash(previous)}}
            for name, value in values.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            originals = {name: (root / name).read_bytes() for name in values}
            args = [root / name for name in ("before.json", "current.json", "old.json", "old.manifest.json")]
            result = generate_bundle(*args, root / "new")
            self.assertEqual(result["new_vectors_different_from_old"], 1)
            self.assertFalse(result["default_inputs_changed"])
            registry = FixedDemandRegistry(root / "current.json", root / "new/demand_vectors.json")
            self.assertEqual(registry.get(1, current[0]["question"])["fluorescence_protein_preservation"]["weight"], 1.0)
            manifest = json.loads((root / "new/demand_vectors.json.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["review_status"], "PENDING_USER_EXPERT")
            self.assertIsNone(manifest["scientific_approval"])
            self.assertEqual(originals, {name: (root / name).read_bytes() for name in values})
            with self.assertRaises(ValueError):
                generate_bundle(*args, root / "new")

    def test_wrong_previous_binding_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (("before.json", [question("old")]), ("current.json", [question("new")]),
                                ("old.json", {}), ("manifest.json", {})):
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                generate_bundle(root / "before.json", root / "current.json", root / "old.json",
                                root / "manifest.json", root / "new")
            self.assertFalse((root / "new").exists())


if __name__ == "__main__":
    unittest.main()
