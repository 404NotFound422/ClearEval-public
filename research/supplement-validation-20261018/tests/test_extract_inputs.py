"""Tests for input provenance validation; synthetic fixture content only."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import extract_inputs as inputs


class InputSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        records = [{"question_id": i, "specific_question": f"question {i}",
                    "model_response": "A\n\nB", "prompt": "synthetic fixture",
                    "shot_type": "1-shot"} for i in range(20)]
        data = (json.dumps(records) + "\n").encode()
        (self.root / "source.json").write_bytes(data)
        self.manifest = {"source_files": [{"path": "source.json", "sha256": inputs.sha256(data),
                         "git_blob_sha1": inputs.git_blob_sha1(data), "bytes": len(data)}], "items": []}
        for i, record in enumerate(records):
            self.manifest["items"].append({"candidate_id": f"C{i+1:02d}", "question_id": i,
                "answer_id": f"synthetic-{i}", "method_declared": "synthetic", "source_path": "source.json",
                "source_record_index": i, "question_sha256": inputs.sha256(record["specific_question"].encode()),
                "answer_sha256": inputs.sha256(record["model_response"].encode()),
                "source_prompt_sha256": inputs.sha256(record["prompt"].encode()),
                "shot_type": "1-shot", "is_heldout": False, "selection_status": "CANDIDATE_NOT_FROZEN"})
        self.path = self.root / "manifest.json"

    def run_extract(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return inputs.extract(self.root, self.path)

    def test_exact_fixture_extraction(self):
        records = self.run_extract()
        self.assertEqual(len(records), 20)
        self.assertEqual(records[0]["model_response"], "A\n\nB")

    def test_source_byte_change_rejected(self):
        with (self.root / "source.json").open("ab") as handle:
            handle.write(b" ")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.run_extract()

    def test_record_identity_change_rejected(self):
        self.manifest["items"][0]["question_id"] = 900
        with self.assertRaisesRegex(ValueError, "Question identity"):
            self.run_extract()

    def test_text_hash_change_rejected(self):
        self.manifest["items"][0]["answer_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Source text checksum"):
            self.run_extract()

    def test_path_escape_rejected(self):
        for relative in ("../outside.json", str(self.root.parent / "outside.json")):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "escapes"):
                inputs.safe_source(self.root, relative)

    def test_false_holdout_claim_rejected(self):
        self.manifest["items"][0]["is_heldout"] = True
        with self.assertRaisesRegex(ValueError, "holdout/freeze"):
            self.run_extract()


if __name__ == "__main__":
    unittest.main(verbosity=2)
