"""Engineering checks only; no scientific success or semantic reference labels."""
from copy import deepcopy
import unittest

from experiments.construct_validity.contract import validate_extraction
from experiments.construct_validity.fidelity import SCHEMA, audit_field


def support(text, raw, start=None, kind="EXPLICIT", transform="IDENTITY"):
    if raw is None:
        return {"kind": "MISSING", "raw_value": None, "spans": []}
    start = text.index(raw) if start is None else start
    return {"kind": kind, "raw_value": raw, "transform": transform,
            "spans": [{"start": start, "end": start + len(raw), "quote": raw}]}


def extraction(text, quote, operation, phase=None, duration=None):
    fields = {"phase": phase, "operation": operation, "duration_text": duration}
    row = {"id": "s1", "branch": "main", "quote": quote,
           "assertion": {"polarity": "AFFIRMED"}, **fields,
           "field_support": {key: support(text, value) for key, value in fields.items()}}
    return {"schema_version": SCHEMA,
            "branches": [{"id": "main", "mode": "SERIAL", "sample_id": "main", "spans": []}],
            "labels": [], "steps": [row], "ri": [], "limitations": "Engineering fixture only"}


def diagnostic(value, text):
    return validate_extraction(value, text, field_scope_policy="diagnostic")


def fields(result):
    return result["field_audit"]["facts"][0]["fields"]


class StructuralFieldScopeTests(unittest.TestCase):
    def test_normal_local_record_and_explicit_units_remain_literal_grounded(self):
        text = "1.1 Wash for 120 min"
        value = extraction(text, text, "Wash", duration="120 min")
        result = diagnostic(value, text)
        self.assertTrue(result["scoring_eligible"])
        self.assertEqual(fields(result)["duration_text"]["scope_binding"]["rule"], "RECORD_LOCAL_OFFSETS_V1")
        self.assertIn("scientific truth", result["validation_scope"])

    def test_numbered_phase_heading_proves_scope_with_real_offsets(self):
        text = "1 Preparation\n1.1 Wash for 120 min\n2 Imaging\n2.1 Image"
        value = extraction(text, "1.1 Wash for 120 min", "Wash", "1 Preparation", "120 min")
        result = diagnostic(value, text)
        phase = fields(result)["phase"]
        self.assertEqual(phase["status"], "GROUNDED")
        self.assertEqual(phase["scope_binding"]["number_prefix"], [1])
        self.assertEqual(phase["scope_binding"]["region"]["end"], text.index("2 Imaging"))
        self.assertTrue(result["scoring_eligible"])
        with self.assertRaisesRegex(ValueError, "outside its record"):
            validate_extraction(value, text)

    def test_bold_and_markdown_heading_formats_have_bounded_scope(self):
        for heading, sibling in (("**Preparation**", "**Imaging**"),
                                 ("## Preparation", "## Imaging"),
                                 ("**1 Preparation**", "**2 Imaging**")):
            with self.subTest(heading=heading):
                text = heading + "\n1.1 Wash\n" + sibling + "\n2.1 Image"
                value = extraction(text, "1.1 Wash", "Wash", "Preparation")
                result = diagnostic(value, text)
                self.assertEqual(fields(result)["phase"]["status"], "GROUNDED")
                self.assertEqual(fields(result)["phase"]["scope_binding"]["region"]["end"], text.index(sibling))

    def test_arbitrary_english_line_is_not_guessed_to_be_heading(self):
        text = "Preparation\nWash"
        result = diagnostic(extraction(text, "Wash", "Wash", "Preparation"), text)
        self.assertEqual(fields(result)["phase"]["status"], "REVIEW_REQUIRED")
        self.assertFalse(result["scoring_eligible"])

    def test_wrong_numbered_sibling_heading_stays_field_local_unresolved(self):
        text = "1 Preparation\n1.1 Wash\n2 Imaging\n2.1 Image"
        value = extraction(text, "2.1 Image", "Image", "1 Preparation")
        result = diagnostic(value, text)
        self.assertEqual(fields(result)["phase"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(fields(result)["operation"]["status"], "GROUNDED")
        self.assertFalse(result["scoring_eligible"])
        self.assertEqual(result["field_audit"]["fidelity_status"], "REVIEW_REQUIRED")

    def test_wrong_bold_sibling_heading_cannot_inherit(self):
        text = "**Preparation**\nWash\n**Imaging**\nImage"
        result = diagnostic(extraction(text, "Image", "Image", "Preparation"), text)
        self.assertEqual(fields(result)["phase"]["scope_binding"]["rule"], "UNPROVEN")
        self.assertFalse(result["scoring_eligible"])

    def test_identical_word_at_other_entity_position_is_not_local(self):
        text = "A: Wash\nB: Wash"
        value = extraction(text, "A: Wash", "Wash")
        value["steps"][0]["field_support"]["operation"] = support(text, "Wash", text.rindex("Wash"))
        result = diagnostic(value, text)
        self.assertEqual(fields(result)["operation"]["status"], "REVIEW_REQUIRED")
        self.assertFalse(result["scoring_eligible"])
        with self.assertRaisesRegex(ValueError, "outside its record"):
            validate_extraction(value, text)
        with self.assertRaisesRegex(ValueError, "outside its record"):
            audit_field("Wash", value["steps"][0]["field_support"]["operation"], text, row_quote="A: Wash")

    def test_repeated_record_needs_common_actual_occurrence_for_all_fields(self):
        text = "Wash 10 min\nWash 10 min"
        value = extraction(text, "Wash 10 min", "Wash", duration="10 min")
        value["steps"][0]["field_support"]["duration_text"] = support(text, "10 min", text.rindex("10 min"))
        result = diagnostic(value, text)
        self.assertFalse(result["scoring_eligible"])
        self.assertIsNone(result["field_audit"]["facts"][0]["record_anchor"])
        self.assertIn("FIELD_RECORD_OCCURRENCE_CONFLICT", fields(result)["operation"]["issues"])
        self.assertIn("FIELD_RECORD_OCCURRENCE_CONFLICT", fields(result)["duration_text"]["issues"])
        value["steps"][0]["field_support"]["operation"] = support(text, "Wash", text.rindex("Wash"))
        self.assertTrue(diagnostic(value, text)["scoring_eligible"])

    def test_cross_record_label_binding_is_reviewed_without_entity_guess(self):
        text = "A probe P\nB channel green"
        row = {"id": "L1", "branch": "main", "target": "A", "probe": "P", "fluorophore": None,
               "channel": "green", "quote": "A probe P", "assertion": {"polarity": "AFFIRMED"}}
        row["field_support"] = {key: support(text, row[key]) for key in ("target", "probe", "fluorophore", "channel")}
        value = extraction("Wash", "Wash", "Wash")
        value["steps"] = []; value["labels"] = [row]
        result = diagnostic(value, text)
        self.assertEqual(fields(result)["channel"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(fields(result)["target"]["status"], "GROUNDED")
        self.assertFalse(result["scoring_eligible"])

    def test_declared_branch_cannot_borrow_same_word_or_heading(self):
        text = "1 Preparation\n1.1 Wash\n2 Imaging\n2.1 Wash"
        value = extraction(text, "2.1 Wash", "Wash", "1 Preparation")
        value["steps"][0]["branch"] = "B"
        value["branches"] = [{"id": name, "mode": "ALTERNATIVE", "sample_id": "s",
                              "spans": [{"start": start, "end": end, "quote": text[start:end]}]}
                             for name, start, end in (("A", 0, text.index("2 Imaging")),
                                                      ("B", text.index("2 Imaging"), len(text)))]
        value["steps"][0]["field_support"]["operation"] = support(text, "Wash", text.rindex("Wash"))
        result = diagnostic(value, text)
        self.assertFalse(result["scoring_eligible"])
        self.assertIn("FIELD_OUTSIDE_DECLARED_BRANCH", fields(result)["phase"]["issues"])
        self.assertEqual(fields(result)["operation"]["status"], "GROUNDED")

    def test_negation_and_condition_are_retained_as_field_review(self):
        for text, polarity, code in (("Do not Wash", "NEGATED", "NEGATION_CONTEXT_NOT_PRESERVED"),
                                     ("If ready, Wash", "CONDITIONAL", "CONDITIONAL_CONTEXT_NOT_PRESERVED")):
            with self.subTest(text=text):
                value = extraction(text, "Wash", "Wash")
                result = diagnostic(value, text)
                self.assertFalse(result["scoring_eligible"])
                self.assertEqual(fields(result)["operation"]["status"], "REVIEW_REQUIRED")
                self.assertIn(code, fields(result)["operation"]["issues"])
                value["steps"][0]["assertion"]["polarity"] = polarity
                self.assertTrue(diagnostic(value, text)["scoring_eligible"])

    def test_exact_offsets_units_transforms_and_schema_stay_technical_failures(self):
        text = "1 Preparation\n1.1 Wash for 120 min"
        base = extraction(text, "1.1 Wash for 120 min", "Wash", "1 Preparation", "120 min")
        offset = deepcopy(base)
        offset["steps"][0]["field_support"]["operation"]["spans"][0]["start"] += 1
        unit = deepcopy(base)
        unit["steps"][0]["duration_text"] = "2 h"
        unit["steps"][0]["field_support"]["duration_text"]["kind"] = "DERIVED"
        unit["steps"][0]["field_support"]["duration_text"]["transform"] = "HOURS_TO_MINUTES"
        transform = deepcopy(base)
        transform["steps"][0]["duration_text"] = "3 h"
        transform["steps"][0]["field_support"]["duration_text"]["kind"] = "DERIVED"
        transform["steps"][0]["field_support"]["duration_text"]["transform"] = "MINUTES_TO_HOURS"
        schema = deepcopy(base)
        del schema["steps"][0]["duration_text"]
        for value in (offset, unit, transform, schema):
            with self.subTest(value=value), self.assertRaises(ValueError):
                diagnostic(value, text)
        correct = deepcopy(transform)
        correct["steps"][0]["duration_text"] = "2 h"
        self.assertTrue(diagnostic(correct, text)["scoring_eligible"])

    def test_disjoint_branch_anchors_do_not_prove_inherited_heading_region(self):
        text = "1 Preparation\n1.1 Wash\n1.2 Dry"
        value = extraction(text, "1.2 Dry", "Dry", "1 Preparation")
        value["branches"][0]["spans"] = [
            {"start": start, "end": end, "quote": text[start:end]}
            for start, end in ((0, text.index("1.1 Wash")), (text.index("1.2 Dry"), len(text)))]
        result = diagnostic(value, text)
        self.assertFalse(result["scoring_eligible"])
        self.assertIn("FIELD_HEADING_BRANCH_SCOPE_UNPROVEN", fields(result)["phase"]["issues"])
        self.assertEqual(fields(result)["operation"]["status"], "GROUNDED")

    def test_operation_order_failure_is_visible_on_the_affected_field(self):
        text = "Wash; Dry"
        value = extraction(text, "Dry", "Dry")
        second = extraction(text, "Wash", "Wash")["steps"][0]
        second["id"] = "s2"
        value["steps"].append(second)
        result = diagnostic(value, text)
        operation = result["field_audit"]["facts"][1]["fields"]["operation"]
        self.assertEqual(operation["status"], "REVIEW_REQUIRED")
        self.assertIn("SOURCE_OPERATION_ORDER_CHANGED", operation["issues"])
        self.assertFalse(result["scoring_eligible"])

    def test_invalid_policy_fails_instead_of_silent_relaxation(self):
        with self.assertRaisesRegex(ValueError, "scope policy"):
            validate_extraction(extraction("Wash", "Wash", "Wash"), "Wash", field_scope_policy="permissive")


if __name__ == "__main__":
    unittest.main()
