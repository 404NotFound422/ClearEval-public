"""Generic synthetic source fixtures only; no native candidates or labels."""
from copy import deepcopy
import json
import unittest

from experiments.construct_validity.compact_grounding import (
    SCHEMA, build_compact_extraction_input, build_compact_prompt_view,
    build_record_catalog, expand_record_refs,
)
from experiments.construct_validity.contract import validate_extraction


def proposal(protocol):
    catalog = build_record_catalog(protocol)
    return {"schema_version": SCHEMA, "protocol_sha256": catalog["protocol_sha256"],
            "branches": [{"id": "main", "mode": "SERIAL", "sample_id": "sample", "spans": []}],
            "labels": [], "steps": [{"id": "S" + str(i + 1), "record_id": record["record_id"], "branch": "main"}
                                     for i, record in enumerate(catalog["records"])],
            "ri": [], "limitations": "Synthetic formatting fixture; no scientific certification."}


class CompactGroundingTests(unittest.TestCase):
    def test_catalog_is_lossless_and_byte_bound_even_with_chinese_crlf(self):
        text = "序言，重复词。\r\n# 甲\r\n1. 重复词；Time: 2 min\r\n2. 重复词。\r\n"
        catalog = build_record_catalog(text)
        self.assertEqual("".join(s["quote"] for s in catalog["segments"]), text)
        self.assertEqual(catalog["protocol_utf8_bytes"], len(text.encode("utf-8")))
        for segment in catalog["segments"]:
            self.assertEqual(text.encode("utf-8")[segment["byte_start"]:segment["byte_end"]].decode("utf-8"), segment["quote"])
        self.assertEqual(catalog, build_record_catalog(text))
        self.assertNotEqual(catalog["records"][0]["record_id"], build_record_catalog(text + " ")["records"][0]["record_id"])

    def test_parentheading_and_same_record_time_expand_to_real_validation(self):
        text = "1 Parent block\n1.1 Move generic object; Time: 2 min\n1.2 Keep generic object; 时长：3 min"
        result = expand_record_refs(proposal(text), text)
        rows = result["expanded"]["steps"]
        self.assertEqual(rows[0]["phase"], "1 Parent block")
        self.assertEqual([r["duration_text"] for r in rows], ["2 min", "3 min"])
        audit = validate_extraction(result["expanded"], text, field_scope_policy="diagnostic")
        self.assertTrue(audit["scoring_eligible"])
        self.assertEqual(audit["field_audit"]["facts"][0]["fields"]["phase"]["scope_binding"]["rule"], "EXPLICIT_PARENT_HEADING_REGION_V1")

    def test_chinese_negation_condition_and_repeated_tokens_are_preserved(self):
        text = "# 任意格式阶段\n1. 不使用重复词；时间：2 min\n2. 如果允许，使用重复词；时间：3 min\n3. 使用重复词"
        payload, original = proposal(text), deepcopy(proposal(text))
        result = expand_record_refs(payload, text)
        self.assertEqual(payload, original)
        self.assertEqual(result["raw_payload"], original)
        self.assertEqual([r["assertion"]["polarity"] for r in result["expanded"]["steps"]], ["NEGATED", "CONDITIONAL", "AFFIRMED"])
        self.assertTrue(result["validated"]["scoring_eligible"])
        self.assertIsNone(result["expanded"]["steps"][2]["duration_text"])
        self.assertEqual(result["validated"]["field_audit"]["facts"][2]["fields"]["duration_text"]["status"], "MISSING")

    def test_full_continuation_block_and_ambiguous_time_stay_literal(self):
        text = "1 Parent\n1.1 Move generic object.\n  Keep the full qualifier; Time: 2 min; Duration: 4 min\n1.2 Finish"
        result = expand_record_refs(proposal(text), text)
        row = result["expanded"]["steps"][0]
        self.assertEqual(row["operation"], "1.1 Move generic object.\n  Keep the full qualifier; Time: 2 min; Duration: 4 min")
        self.assertIsNone(row["phase"])
        self.assertIsNone(row["duration_text"])
        self.assertEqual(row["field_support"]["operation"]["raw_value"], row["operation"])

    def test_unknown_hash_catalog_omitted_key_and_value_rewrites_rejected(self):
        text, valid = "1. Move a generic object; Time: 2 min", proposal("1. Move a generic object; Time: 2 min")
        mutations = [lambda p: p.update(protocol_sha256="0" * 64),
                     lambda p: p["steps"][0].update(record_id="unknown"),
                     lambda p: p["steps"][0].pop("branch"),
                     lambda p: p["steps"][0].update(operation="edited")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = deepcopy(valid)
                mutation(changed)
                with self.assertRaises(ValueError):
                    expand_record_refs(changed, text)
        catalog = build_record_catalog(text)
        catalog["segments"][0]["quote"] = "edited"
        with self.assertRaises(ValueError):
            expand_record_refs(valid, text, catalog=catalog)

    def test_omissions_report_coverage_without_completeness_claim(self):
        text = "Unnumbered prose remains uninterpreted.\n1. Move\n2. Keep"
        payload = proposal(text)
        omitted = payload["steps"].pop()
        result = expand_record_refs(payload, text)
        self.assertEqual(result["coverage"]["omitted_record_ids"], [omitted["record_id"]])
        self.assertFalse(result["coverage"]["extraction_completeness_certified"])
        self.assertTrue(result["coverage"]["unclassified_source_segments"])

    def test_two_method_branches_cannot_reuse_or_borrow_records(self):
        text = "# Method Alpha\n1. Move\n# Method Beta\n2. Keep"
        boundary, payload = text.index("# Method Beta"), proposal(text)
        payload["branches"] = [
            {"id": "A", "mode": "ALTERNATIVE", "sample_id": "sample", "spans": [{"start": 0, "end": boundary, "quote": text[:boundary]}]},
            {"id": "B", "mode": "ALTERNATIVE", "sample_id": "sample", "spans": [{"start": boundary, "end": len(text), "quote": text[boundary:]}]},
        ]
        payload["steps"][0]["branch"] = "A"
        payload["steps"][1]["branch"] = "B"
        result = expand_record_refs(payload, text)
        self.assertTrue(result["validated"]["scoring_eligible"])
        wrong = deepcopy(payload)
        wrong["steps"][1]["branch"] = "A"
        with self.assertRaises(ValueError):
            expand_record_refs(wrong, text)
        repeated = deepcopy(payload)
        repeated["steps"][1]["record_id"] = repeated["steps"][0]["record_id"]
        with self.assertRaises(ValueError):
            expand_record_refs(repeated, text)

    def test_reorder_duplicate_ids_and_legacy_compatibility(self):
        text, payload = "1. Move\n2. Keep", proposal("1. Move\n2. Keep")
        reordered = deepcopy(payload)
        reordered["steps"].reverse()
        duplicate = deepcopy(payload)
        duplicate["steps"][1]["id"] = duplicate["steps"][0]["id"]
        for changed in (reordered, duplicate):
            with self.assertRaises(ValueError):
                expand_record_refs(changed, text)
        legacy = {"labels": [], "steps": [], "ri": [], "limitations": "Synthetic legacy."}
        self.assertFalse(validate_extraction(legacy, text)["scoring_eligible"])

    def test_strict_label_support_is_not_relaxed_by_parent_rule(self):
        text, payload = "1. Move TOKEN", proposal("1. Move TOKEN")
        payload["labels"] = [{"id": "L", "branch": "main", "target": None, "probe": "TOKEN",
                              "fluorophore": None, "channel": None, "quote": text,
                              "assertion": {"polarity": "AFFIRMED"},
                              "field_support": {field: {"kind": "MISSING", "raw_value": None, "spans": []}
                                                for field in ("target", "probe", "fluorophore", "channel")}}]
        payload["labels"][0]["field_support"]["probe"] = {"kind": "EXPLICIT", "raw_value": "TOKEN", "spans": [{"quote": "TOKEN"}]}
        with self.assertRaises(ValueError):
            expand_record_refs(payload, text)

    def test_lossless_prompt_view_aliases_and_parenthesized_named_time(self):
        text = "?????\r\n# ????\r\n1. Move (Time: 24 hours) keep qualifier.\r\n2. Keep; Time: 48 hours) unexplained suffix"
        catalog = build_record_catalog(text)
        view = build_compact_prompt_view(catalog)
        self.assertEqual(view["schema_version"], "source-record-prompt-view-v1")
        self.assertEqual("".join(s["quote"] for s in view["segments"]), text)
        self.assertEqual(view["protocol_sha256"], catalog["protocol_sha256"])
        rows = [segment for segment in view["segments"] if segment["id"].startswith("R")]
        self.assertEqual([r["id"] for r in rows], ["R001", "R002"])
        self.assertEqual(rows[0]["parentheading"], "H001")
        start, end = rows[0]["metadataTime"]
        self.assertEqual(text[start:end], "24 hours")
        self.assertNotIn("value", rows[0])
        self.assertIsNone(rows[1]["metadataTime"])
        review_start, review_end = rows[1]["metadataTime_review"]
        self.assertEqual(text[review_start:review_end], "48 hours) unexplained suffix")
        for segment in view["segments"]:
            self.assertEqual(segment["quote"], text[segment["start"]:segment["end"]])
        prompt = build_compact_extraction_input(text)["prompt"]
        self.assertEqual(prompt.count("Move (Time: 24 hours) keep qualifier."), 1)
        self.assertNotIn(catalog["records"][0]["record_id"], prompt)
        result = expand_record_refs(proposal(text), text)
        self.assertEqual(result["expanded"]["steps"][0]["duration_text"], "24 hours")
        self.assertIsNone(result["expanded"]["steps"][1]["duration_text"])
        self.assertEqual(result["coverage"]["time_metadata_review"][0]["metadataTime"]["value"], "48 hours) unexplained suffix")

    def test_aliases_are_exact_and_bound_to_rebuilt_protocol_hash(self):
        text = "1. Move original object"
        payload = proposal(text)
        payload["steps"][0]["record_id"] = "R001"
        result = expand_record_refs(payload, text)
        self.assertEqual(result["raw_payload"]["steps"][0]["record_id"], "R001")
        self.assertEqual(result["reference_audits"][0]["record_id"], build_record_catalog(text)["records"][0]["record_id"])
        self.assertEqual(result["reference_audits"][0]["protocol_sha256"], payload["protocol_sha256"])
        with self.assertRaises(ValueError):
            expand_record_refs(payload, "1. Move another object")
        for alias in ("R1", "R000", "R002", "H001"):
            changed = deepcopy(payload)
            changed["steps"][0]["record_id"] = alias
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                expand_record_refs(changed, text)

    def test_alias_and_long_id_mix_cannot_reuse_or_cross_branches(self):
        text = "# Method Alpha\n1. Move\n# Method Beta\n2. Keep"
        boundary, payload = text.index("# Method Beta"), proposal(text)
        payload["branches"] = [
            {"id": "A", "mode": "ALTERNATIVE", "sample_id": "sample", "spans": [{"start": 0, "end": boundary, "quote": text[:boundary]}]},
            {"id": "B", "mode": "ALTERNATIVE", "sample_id": "sample", "spans": [{"start": boundary, "end": len(text), "quote": text[boundary:]}]},
        ]
        first_long_id = payload["steps"][0]["record_id"]
        payload["steps"][0].update(record_id="R001", branch="A")
        payload["steps"][1]["branch"] = "B"
        result = expand_record_refs(payload, text)
        self.assertTrue(result["validated"]["scoring_eligible"])
        self.assertEqual(result["coverage"]["selected_record_ids"][0], first_long_id)
        duplicate = deepcopy(payload)
        duplicate["steps"][1]["record_id"] = first_long_id
        with self.assertRaises(ValueError):
            expand_record_refs(duplicate, text)
        wrong_branch = deepcopy(payload)
        wrong_branch["steps"][1].update(record_id="R002", branch="A")
        with self.assertRaises(ValueError):
            expand_record_refs(wrong_branch, text)

    def test_complexity_report_counts_real_serialized_bytes_only(self):
        text = "# 阶段\n1. 移动普通物体；Time: 2 min"
        result = expand_record_refs(proposal(text), text)
        lengths = result["length_model"]
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(lengths["catalog_bytes"], len(encode(result["catalog"])))
        self.assertEqual(lengths["catalog_plus_refs_bytes"], lengths["catalog_bytes"] + lengths["refs_bytes"])
        self.assertEqual(lengths["expanded_bytes"], len(encode(result["expanded"])))
        self.assertEqual(lengths["prompt_view_bytes"], len(encode(build_compact_prompt_view(result["catalog"]))))
        self.assertEqual(lengths["input_only_saved_bytes"], lengths["catalog_bytes"] - lengths["prompt_view_bytes"])
        self.assertIsNone(lengths["speed_or_token_estimate"])
        self.assertIn("SOURCE_CATALOG_JSON", build_compact_extraction_input(text)["prompt"])



    def test_fullwidth_time_container_closes_before_trailing_source(self):
        text = "1. Move \uff08Time: 2 min\uff09 preserve suffix\n2. Keep; Time: 3 min\uff09 unexplained suffix"
        result = expand_record_refs(proposal(text), text)
        self.assertEqual(result["expanded"]["steps"][0]["duration_text"], "2 min")
        self.assertEqual(result["expanded"]["steps"][0]["operation"], text.split("\n")[0])
        self.assertIsNone(result["expanded"]["steps"][1]["duration_text"])
        review = result["coverage"]["time_metadata_review"][0]["metadataTime"]
        self.assertEqual(review["value"], "3 min\uff09 unexplained suffix")
        self.assertEqual(text[review["start"]:review["end"]], review["value"])
        self.assertTrue(result["validated"]["scoring_eligible"])

    def test_proven_parent_condition_or_negation_preserves_assertion(self):
        for heading, polarity in (("# If needed", "CONDITIONAL"),
                                  ("# Do not perform", "NEGATED")):
            text = heading + "\n1. Move generic object; Time: 2 min"
            with self.subTest(heading=heading):
                result = expand_record_refs(proposal(text), text)
                row = result["expanded"]["steps"][0]
                self.assertEqual(row["phase"], heading)
                self.assertEqual(row["assertion"]["polarity"], polarity)
                self.assertTrue(result["validated"]["scoring_eligible"])

if __name__ == "__main__":
    unittest.main()
