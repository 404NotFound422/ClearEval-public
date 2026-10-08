"""Focused integrity and transformation checks; stdlib only, no inference."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE))

from mutations import all_variants, mutate_steps
from summarize import ValidationError, summarize


class DiagnosticTests(unittest.TestCase):
    def test_saved_observation_scope_and_counts(self):
        result = summarize()
        self.assertEqual(result["fixture_integrity"], "PASSED")
        self.assertEqual(result["gen"]["scoring_inputs"], 300)
        self.assertEqual(result["protocols"]["total_calls"], 66)
        self.assertEqual(result["protocols"]["independent_expert_labels"], 0)
        fourteen = result["protocols"]["models"]["qwen3:14b"]
        self.assertEqual(fourteen["effective_states"]["UNRESOLVED"], 7)
        self.assertEqual(fourteen["effective_states"]["TECHNICAL_FAILURE"], 7)
        self.assertEqual(fourteen["matched_13"]["err_same_evidence"]["decisive"], 13)

    def test_tampered_fixture_fails_hash_verification(self):
        with tempfile.TemporaryDirectory(prefix="integrity-test-", dir=PACKAGE) as directory:
            test_package = Path(directory)
            shutil.copytree(PACKAGE / "fixtures", test_package / "fixtures")
            shutil.copyfile(PACKAGE / "source_manifest.json", test_package / "source_manifest.json")
            fixture = test_package / "fixtures/selfcheck_pairs.csv"
            original = fixture.read_bytes()
            altered = original.replace(b"33.33333333333333", b"34.33333333333333", 1)
            self.assertNotEqual(original, altered)
            self.assertEqual(len(original), len(altered))
            fixture.write_bytes(altered)
            with self.assertRaisesRegex(ValidationError, "SHA-256 mismatch"):
                summarize(test_package)

    def test_inconsistent_pair_fails_even_with_updated_fixture_hash(self):
        with tempfile.TemporaryDirectory(prefix="field-test-", dir=PACKAGE) as directory:
            test_package = Path(directory)
            shutil.copytree(PACKAGE / "fixtures", test_package / "fixtures")
            fixture = test_package / "fixtures/selfcheck_pairs.csv"
            reader = csv.DictReader(io.StringIO(fixture.read_text(encoding="utf-8")))
            rows, fields = list(reader), reader.fieldnames
            rows[0]["IA_after"] = "46"
            with fixture.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            data = fixture.read_bytes()
            manifest = json.loads((PACKAGE / "source_manifest.json").read_text(encoding="utf-8"))
            manifest["fixtures"]["fixtures/selfcheck_pairs.csv"] = {
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            (test_package / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "difference does not match"):
                summarize(test_package)

    def test_mutations_preserve_original_input(self):
        steps = ["First step.", "Wait 2 hours.", "Last step."]
        outputs = all_variants(steps)
        self.assertEqual(steps, ["First step.", "Wait 2 hours.", "Last step."])
        self.assertEqual(outputs["reverse_steps"]["prediction"], steps[::-1])
        self.assertEqual(outputs["duplicate_steps"]["prediction"], steps + steps)
        self.assertEqual(outputs["drop_alternating_steps"]["prediction"], steps[::2])
        self.assertEqual(outputs["multiply_parameters_by_10"]["prediction"][1], "Wait 20 hours.")

    def test_unit_boundaries_and_unchanged_text(self):
        changed = mutate_steps(["Wait 0.5 hours; use 2 µL. Item 3 remains."], "multiply_parameters_by_10")
        self.assertEqual(changed["prediction"], ["Wait 5 hours; use 20 µL. Item 3 remains."])
        self.assertEqual(changed["parameters_changed"], 2)
        zero = mutate_steps(["Wait 0 hours."], "multiply_parameters_by_10")
        self.assertEqual(zero["parameters_changed"], 1)
        self.assertFalse(zero["text_changed"])
        unsupported = mutate_steps(["Measure 2 kg; item 4."], "multiply_parameters_by_10")
        self.assertFalse(unsupported["text_changed"])

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(TypeError):
            mutate_steps("One string", "identity")
        with self.assertRaises(TypeError):
            mutate_steps([None], "identity")
        with self.assertRaises(ValueError):
            mutate_steps([], "unknown")


if __name__ == "__main__":
    unittest.main()
