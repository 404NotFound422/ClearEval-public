"""Strict local-only tests, including tampering that weak normalization misses."""

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_format_controls as controls


class FormatControlsTests(unittest.TestCase):
    SAMPLE = "1. Keep item A (do not replace).\n\n2. Keep item B 3 times, if enabled.\n"

    def test_exact_lf_insertion_only(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        self.assertEqual(variant, self.SAMPLE.replace("\n\n", "\n\n\n"))
        self.assertEqual(controls.apply_diff(self.SAMPLE, diff), variant)
        self.assertEqual(controls.validate_variant(self.SAMPLE, variant, diff, "C01")["result"], "PASS")

    def test_original_whitespace_within_lines_untouched(self):
        original = "  A\tB  C\n\n D\t E  "
        variant, diff = controls.make_variant(original, "C02")
        self.assertEqual(variant, "  A\tB  C\n\n\n D\t E  ")
        controls.validate_variant(original, variant, diff, "C02")

    def test_consecutive_empty_lines_each_receive_one_lf(self):
        original = "A\n\n\nB"
        variant, diff = controls.make_variant(original, "C03")
        self.assertEqual(variant, "A\n\n\n\n\nB")
        self.assertEqual(len(diff["operations"]), 2)

    def test_non_ascii_content_is_not_normalized(self):
        original = "α ① 候选\n\nＢ 1.0"
        variant, diff = controls.make_variant(original, "C04")
        self.assertEqual(controls.strip_allowed_whitespace(original), controls.strip_allowed_whitespace(variant))
        self.assertEqual(controls.apply_diff(original, diff), variant)

    def test_no_exact_empty_lf_line_fails_without_fallback(self):
        for original in ["A B", "A\n  \nB", "A\r\n\r\nB", ""]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                controls.make_variant(original, "C01")

    def test_mutation_of_non_whitespace_is_rejected(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        for tampered in [variant.replace("3 times", "4 times"), variant.replace("not ", ""), variant.replace("A", "Z", 1)]:
            with self.subTest(tampered=tampered), self.assertRaises(ValueError):
                controls.validate_variant(self.SAMPLE, tampered, diff, "C01")

    def test_word_joining_is_rejected_even_when_stripped_equal(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        tampered = variant.replace("item A", "itemA")
        self.assertEqual(controls.strip_allowed_whitespace(self.SAMPLE), controls.strip_allowed_whitespace(tampered))
        with self.assertRaises(ValueError):
            controls.validate_variant(self.SAMPLE, tampered, diff, "C01")

    def test_unapproved_inline_space_change_is_rejected(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        tampered = variant.replace("Keep item", "Keep  item", 1)
        diff["variant_utf8_sha256"] = controls.sha256_text(tampered)
        with self.assertRaises(ValueError):
            controls.validate_variant(self.SAMPLE, tampered, diff, "C01")

    def test_line_reordering_is_rejected(self):
        original = "A\n\nB\n"
        variant, diff = controls.make_variant(original, "C01")
        with self.assertRaises(ValueError):
            controls.validate_variant(original, variant.replace("A", "X").replace("B", "A").replace("X", "B"), diff, "C01")

    def test_incomplete_or_changed_line_mapping_is_rejected(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        for edit in ("drop", "move", "identity"):
            broken = deepcopy(diff)
            if edit == "drop":
                broken["original_line_map"].pop()
            elif edit == "move":
                broken["original_line_map"][0]["variant_line_1based"] += 1
            else:
                broken["original_line_map"][0]["original_line_id"] = "C99:L0001"
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                controls.validate_variant(self.SAMPLE, variant, broken, "C01")

    def test_patch_wrong_location_or_non_lf_is_rejected(self):
        variant, diff = controls.make_variant(self.SAMPLE, "C01")
        for field, value in [("inserted_text", "\nX"), ("original_codepoint_offset_0based", 1), ("operation", "replace")]:
            broken = deepcopy(diff)
            broken["operations"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                controls.validate_variant(self.SAMPLE, variant, broken, "C01")

    def test_all_current_20_candidate_pairs_and_files(self):
        result = controls.verify()
        self.assertEqual(result, {"verification": "PASS", "passing_pair_count": 20, "excluded_failure_count": 0})

    def test_source_candidate_change_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "candidate20_original_pairs.json"
            records = json.loads(controls.DEFAULT_SOURCE.read_text(encoding="utf-8"))
            records.reverse()
            source.write_text(json.dumps(records), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Source candidates changed"):
                controls.verify(source, controls.DEFAULT_OUTPUT)

    def test_unapproved_expectation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            shutil.copytree(controls.DEFAULT_OUTPUT, output)
            path = output / "format_control_pairs.json"
            pairs = json.loads(path.read_text(encoding="utf-8"))
            pairs[0]["expected_relation"]["expert_gold"] = True
            controls.write_json(path, pairs)
            with self.assertRaisesRegex(ValueError, "Unapproved scientific"):
                controls.verify(controls.DEFAULT_SOURCE, output)

    def test_stale_extra_pair_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            shutil.copytree(controls.DEFAULT_OUTPUT, output)
            controls.write_json(output / "pairs/STALE.json", {})
            with self.assertRaisesRegex(ValueError, "Stale, missing, or extra per-pair"):
                controls.verify(controls.DEFAULT_SOURCE, output)

    def test_summary_count_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            shutil.copytree(controls.DEFAULT_OUTPUT, output)
            path = output / "validation_summary.json"
            summary = json.loads(path.read_text(encoding="utf-8"))
            summary["inserted_lf_count"] += 1
            controls.write_json(path, summary)
            with self.assertRaisesRegex(ValueError, "Summary count mismatch"):
                controls.verify(controls.DEFAULT_SOURCE, output)

    def test_summary_gold_claim_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            shutil.copytree(controls.DEFAULT_OUTPUT, output)
            path = output / "validation_summary.json"
            summary = json.loads(path.read_text(encoding="utf-8"))
            summary["expert_gold"] = True
            controls.write_json(path, summary)
            with self.assertRaisesRegex(ValueError, "Unapproved claim"):
                controls.verify(controls.DEFAULT_SOURCE, output)

    def test_failed_candidate_is_excluded_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir, output = root / "source", root / "output"
            source_dir.mkdir()
            records = json.loads(controls.DEFAULT_SOURCE.read_text(encoding="utf-8"))
            records[0]["model_response"] = "Synthetic test string without a blank line."
            source = source_dir / "candidate20_original_pairs.json"
            controls.write_json(source, records)
            summary = controls.build(source, output)
            failures = json.loads((output / "failures.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["passing_pair_count"], 19)
            self.assertEqual(summary["excluded_failure_count"], 1)
            self.assertEqual(failures[0]["candidate_id"], records[0]["candidate_id"])
            self.assertEqual(failures[0]["status"], "EXCLUDED_FAIL_CLOSED")
            self.assertFalse((output / "pairs/C01_FORMAT_LF_V1.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
