"""Network-free engineering counterexamples for the integrated legacy entry.

The entry function is loaded from its actual source AST with synthetic dependencies,
so testing cannot import any model client or depend on API credentials/static data.
"""
import ast
import asyncio
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import unittest
from datetime import datetime, timezone

import evaluator_integrity as integrity
from evaluator_integrity import (
    JudgeFormatError, FLAT_GROUNDING_VERSION, parse_judge_object, resolve_method,
    method_identity, validate_legacy_extraction, extraction_field_states,
    audit_flat_extraction, legacy_integrity_audit,
)
from evaluation_contract import time_score_details, time_reasoning


def span(text, quote):
    start = text.index(quote)
    return {"start": start, "end": start + len(quote), "quote": quote}


def support(text, value, context, transform="IDENTITY"):
    return {"kind": "EXPLICIT", "spans": [span(text, value)],
            "context_span": span(text, context), "raw_value": value, "transform": transform}


def grounded_fixture():
    text = "Use CUBIC for clearing for 2 days. Label NF200 with Alexa Fluor 647."
    first, second = text.split(". ")[:2]
    second = second.rstrip(".")
    extraction = {"schema_version": FLAT_GROUNDING_VERSION, "method_name": "CUBIC",
                  "clearing_total_time_hours": 48, "marker_dict": {"Alexa Fluor 647": "NF200"}}
    extraction["field_support"] = {
        "/method_name": support(text, "CUBIC", first),
        "/clearing_total_time_hours": support(text, "2 days", first, "TIME_TO_HOURS"),
        "/marker_dict/Alexa Fluor 647/@key": support(text, "Alexa Fluor 647", second),
        "/marker_dict/Alexa Fluor 647": support(text, "NF200", second),
    }
    return extraction, text


def load_source_functions(names, namespace):
    source = Path("OEQ_run_grading_new.py").read_text(encoding="utf-8")
    nodes = [node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError("Actual legacy function missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "OEQ_run_grading_new.py", "exec"), namespace)
    return namespace


class JsonIntegrityTests(unittest.TestCase):
    def test_braces_and_escaped_quotes_in_strings_are_not_truncated(self):
        value = {"reason": 'A } is inside a string; literal \" and [ are preserved', "nested": {"x": 1}}
        self.assertEqual(parse_judge_object(json.dumps(value)), value)

    def test_complete_fence_is_unwrapped_without_modifying_json(self):
        self.assertEqual(parse_judge_object("\x60\x60\x60JSON\n{\"x\":\"}\"}\n\x60\x60\x60"), {"x": "}"})
        self.assertEqual(parse_judge_object("~~~json\n{\"x\":1}\n~~~"), {"x": 1})

    def test_duplicate_keys_at_every_depth_are_technical_failures(self):
        for text in ('{"x":1,"x":2}', '{"x":{"method":"A","method":"B"}}'):
            with self.subTest(text=text), self.assertRaises(JudgeFormatError):
                parse_judge_object(text)

    def test_nonfinite_and_float_overflow_are_rejected(self):
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e400}'):
            with self.subTest(text=text), self.assertRaises(JudgeFormatError):
                parse_judge_object(text)

    def test_invalid_unicode_is_not_repaired(self):
        for text in (r'{"x":"\u12zz"}', r'{"x":"\ud800"}'):
            with self.subTest(text=text), self.assertRaises(JudgeFormatError):
                parse_judge_object(text)
        self.assertEqual(parse_judge_object(r'{"x":"\ud83d\ude00"}')["x"], "\U0001f600")

    def test_multiple_roots_prose_arrays_and_partial_fences_are_rejected(self):
        for text in ('{"x":1} {"x":2}', 'Here is {"x":1}', '[]', 'null',
                     "\x60\x60\x60json\n{\"x\":1}", '{"x":1} trailing'):
            with self.subTest(text=text), self.assertRaises(JudgeFormatError):
                parse_judge_object(text)


class MethodIdentityTests(unittest.TestCase):
    def test_method_versions_are_not_substring_aliases(self):
        keys = ["SeeDB2", "ClearT2", "iDISCO+", "3DISCO"]
        self.assertIsNone(resolve_method("SeeDB", keys))
        self.assertIsNone(resolve_method("ClearT", keys))
        self.assertIsNone(resolve_method("iDISCO", keys))
        self.assertEqual(resolve_method("SeeDB2", keys), "SeeDB2")
        self.assertIsNone(resolve_method("THF solvent", keys))

    def test_combined_authored_source_key_is_explicitly_resolved(self):
        self.assertEqual(resolve_method("iDISCO+", ["iDISCO (iDISCO+)"]), "iDISCO (iDISCO+)")
        self.assertIsNone(resolve_method("SeeDB2 optimized variant", ["SeeDB2"]))

    def test_multiple_methods_do_not_return_first_vector(self):
        result = method_identity("CUBIC -> iDISCO+", ["CUBIC", "iDISCO+"])
        self.assertEqual(result["status"], "COMPOSITE_UNREVIEWED")
        self.assertIsNone(result["resolved_key"])
        self.assertEqual(result["components"], ["CUBIC", "iDISCO+"])

    def test_explicit_stages_remain_unreviewed_as_a_composition(self):
        stages = [{"id": "s1", "method_name": "CUBIC", "quote": "CUBIC"},
                  {"id": "s2", "method_name": "iDISCO+", "quote": "iDISCO+"}]
        result = method_identity("CUBIC", ["CUBIC", "iDISCO+"], stages)
        self.assertEqual(result["status"], "COMPOSITE_UNREVIEWED")
        self.assertEqual([s["resolved_key"] for s in result["components"]], ["CUBIC", "iDISCO+"])


class FlatExtractionTests(unittest.TestCase):
    def test_missing_null_and_empty_are_distinct_without_imputation(self):
        value = {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": None}
        before = copy.deepcopy(value)
        validate_legacy_extraction(value)
        states = extraction_field_states(value)
        self.assertEqual(states["method_name"], "EXPLICIT_NULL")
        self.assertEqual(states["marker_dict"], "EXPLICIT_EMPTY")
        self.assertEqual(states["protocol_time_hours"], "ABSENT")
        self.assertEqual(value, before)
        with self.assertRaises(JudgeFormatError):
            validate_legacy_extraction({"method_name": None, "marker_dict": {}})

    def test_bad_optional_fields_and_unknown_fields_fail(self):
        value = {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": None}
        cases = [("protocol_time_hours", "48"), ("protocol_time_hours", [True]), ("protocol_time_hours", [math.nan]),
                 ("reagent_ri_value", "1.48"), ("clearing_total_time_hours", True), ("extra_parameter", 10)]
        for key, field in cases:
            with self.subTest(key=key, field=field), self.assertRaises(JudgeFormatError):
                validate_legacy_extraction({**value, key: field})

    def test_grounded_fields_with_explicit_units_can_pass(self):
        value, protocol = grounded_fixture()
        result = audit_flat_extraction(value, protocol)
        self.assertTrue(result["validated"], result["issues"])
        self.assertEqual(result["fidelity_status"], "FIELD_SUPPORT_VERIFIED")
        self.assertEqual(result["omission_coverage"], "NOT_CERTIFIED")
        self.assertEqual(result["semantic_scope"], "NOT_CERTIFIED")

    def test_true_quote_does_not_certify_a_different_field_value(self):
        value, protocol = grounded_fixture()
        value["marker_dict"]["Alexa Fluor 647"] = "CD31"
        result = audit_flat_extraction(value, protocol)
        self.assertFalse(result["validated"])
        self.assertTrue(any(i.get("path") == "/marker_dict/Alexa Fluor 647" for i in result["issues"]))

    def test_unit_and_magnitude_changes_are_caught(self):
        value, protocol = grounded_fixture()
        value["clearing_total_time_hours"] = 2
        self.assertFalse(audit_flat_extraction(value, protocol)["validated"])
        value["clearing_total_time_hours"] = 48
        value["field_support"]["/clearing_total_time_hours"] = support(protocol, "2", protocol.split(".")[0], "NUMBER")
        self.assertFalse(audit_flat_extraction(value, protocol)["validated"])

    def test_context_cannot_clip_away_a_negation(self):
        protocol = "Do not use CUBIC."
        value = {"schema_version": FLAT_GROUNDING_VERSION, "method_name": "CUBIC",
                 "marker_dict": {}, "clearing_total_time_hours": None,
                 "field_support": {"/method_name": support(protocol, "CUBIC", "Do not use CUBIC"),
                                   "/marker_dict": {"kind": "MISSING"},
                                   "/clearing_total_time_hours": {"kind": "MISSING"}}}
        self.assertFalse(audit_flat_extraction(value, protocol)["validated"])
        value["field_support"]["/method_name"] = support(protocol, "CUBIC", "CUBIC")
        result = audit_flat_extraction(value, protocol)
        self.assertFalse(result["validated"])
        self.assertTrue(any("clips" in i.get("detail", "") for i in result["issues"]))

    def test_offsets_must_resolve_to_the_declared_answer(self):
        value, protocol = grounded_fixture()
        value["field_support"]["/method_name"]["spans"][0]["start"] += 1
        self.assertFalse(audit_flat_extraction(value, protocol)["validated"])

    def test_field_support_must_cover_keys_values_and_all_raw_facts(self):
        value, protocol = grounded_fixture()
        del value["field_support"]["/marker_dict/Alexa Fluor 647/@key"]
        self.assertFalse(audit_flat_extraction(value, protocol)["validated"])

    def test_legacy_structure_is_not_falsely_migrated(self):
        result = audit_flat_extraction({"method_name": "CUBIC", "marker_dict": {},
                                       "clearing_total_time_hours": 48}, "Use CUBIC for 48 hours.")
        self.assertFalse(result["validated"])
        self.assertEqual(result["fidelity_status"], "LEGACY_STRUCTURE_ONLY")

    def test_stage_quote_is_not_scientific_evidence_if_absent_from_answer(self):
        extraction = {"method_name": "CUBIC", "marker_dict": {}, "clearing_total_time_hours": None,
                      "method_stages": [{"id": "s1", "method_name": "CUBIC", "quote": "invented CUBIC stage"}]}
        result = legacy_integrity_audit(extraction, "Use CUBIC.", {})
        self.assertIn("INVALID_STAGE_QUOTE", {i["code"] for i in result["issues"]})

    def test_huge_numbers_fail_stably_without_python_overflow(self):
        value = {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": 10 ** 1000}
        with self.assertRaises(JudgeFormatError):
            validate_legacy_extraction(value)

    def test_grounded_fields_do_not_alone_create_formal_cce(self):
        value, protocol = grounded_fixture()
        result = legacy_integrity_audit(value, protocol, {"method_identity": {"status": "RESOLVED_SINGLE"}})
        self.assertTrue(result["fidelity"]["validated"])
        self.assertFalse(result["cce_eligible"])
        self.assertIn("REQUIREMENT_VALIDATION_NOT_BOUND", {i["code"] for i in result["issues"]})


class LegacyLookupTests(unittest.TestCase):
    def namespace(self):
        ns = {"math": math, "resolve_method": resolve_method,
              "_normalize_name": lambda s: str(s or "").casefold().replace(" ", ""),
              "_expand_marker_candidates": lambda s: {str(s).casefold()},
              "_map_fluor_to_tissue_col": lambda f: "AF647",
              "_map_fluor_to_method_key": lambda f: "AF647",
              "_method_fluoro_by_method": {"seedb2": {"method": "SeeDB2", "AF647": 1}},
              "_tissue_by_marker": {"nf200": {"AF647": None}},
              "MODEL_SPACE_SIGNED": {"SeeDB2": {"F_fp": 1}}}
        return load_source_functions({"_get_method_fluor_compat", "_get_marker_fluor_compat", "find_signed_method"}, ns)

    def test_actual_method_lookup_does_not_confuse_seedb_with_seedb2(self):
        ns = self.namespace()
        self.assertIsNone(ns["_get_method_fluor_compat"]("SeeDB", "Alexa Fluor 647"))
        self.assertEqual(ns["_get_method_fluor_compat"]("SeeDB2", "Alexa Fluor 647"), 1)
        self.assertIsNone(ns["find_signed_method"]("SeeDB"))
        self.assertIsNone(ns["find_signed_method"]("SeeDB2 -> 3DISCO"))

    def test_actual_missing_marker_cell_stays_unknown(self):
        ns = self.namespace()
        self.assertIsNone(ns["_get_marker_fluor_compat"]("NF200", "Alexa Fluor 647"))
        ns["_tissue_by_marker"]["nf200"]["AF647"] = 0
        self.assertIs(ns["_get_marker_fluor_compat"]("NF200", "Alexa Fluor 647"), False)

    def test_explicit_zero_hours_is_not_imputed_missing_time(self):
        row = {"clearing_time_min_h": 20, "clearing_time_max_h": 40, "clearing_time_median_h": 30}
        score, detail = time_score_details(0, row, "T")
        self.assertEqual(detail["status"], "scored")
        self.assertEqual(detail["actual_hours"], 0)
        self.assertIsNotNone(score)
        self.assertLess(score, 3)
        self.assertIsNone(time_score_details(None, row, "T")[0])

    def test_missing_time_reference_is_unknown_and_bool_is_invalid(self):
        row = {"clearing_time_min_h": 20, "clearing_time_max_h": 40, "clearing_time_median_h": 30}
        self.assertIsNone(time_score_details(30, None, "T")[0])
        self.assertIsNone(time_score_details(None, row, "T")[0])
        self.assertIsNone(time_score_details(True, row, "T")[0])


class LegacyEffectivenessTests(unittest.TestCase):
    def namespace(self):
        from verified_marker_aliases import marker_identity_conflict, same_verified_target
        row = {"clearing_time_min_h": 20, "clearing_time_max_h": 40, "clearing_time_median_h": 30}
        ns = {"marker_identity_conflict": marker_identity_conflict,
              "same_verified_target": same_verified_target, "math": math, "method_identity": method_identity, "resolve_method": resolve_method,
              "find_signed_method": lambda name: {"F_fp": 1},
              "calculate_method_suitability": lambda *args: 1,
              "MODEL_SPACE_SIGNED": {"CUBIC": {"F_fp": 1}, "iDISCO+": {"F_fp": -1}},
              "_preprocess_marker_dict": lambda value: (list(value.items()), False, False),
              "_match_marker_to_targets": lambda *args, **kwargs: True,
              "_is_penalty_fluor": lambda value: False,
              "_get_marker_fluor_compat": lambda *args: None,
              "_get_method_fluor_compat": lambda name, fluor: 1 if name == "CUBIC" else 0,
              "_time_kb_row": lambda method, tier: row if method else None,
              "TIME_KB_LOOKUP": {"CUBIC": {"T": row}},
              "METHOD_RI_REF_KB": {"CUBIC": 1.48}, "SIGMA_RI_KB": {"CUBIC": {"T": 0.1}},
              "time_score_details": time_score_details}
        return load_source_functions({"calculate_effectiveness_score", "_marker_target_coverage"}, ns)

    def calculate(self, name="CUBIC", stages=None):
        data = {"method_name": name, "sample_tier": "T", "tissue_ri_value": 1.48, "total_time_hours": 30}
        if stages is not None:
            data["method_stages"] = stages
        return self.namespace()["calculate_effectiveness_score"](
            data, {}, {}, {"AF647": "NF200"}, [{"marker_name": "NF200"}])

    def test_unknown_compatibility_is_neither_perfect_nor_quality_failure(self):
        result = self.calculate()
        self.assertIsNone(result["s_marker_fluor_compat"])
        self.assertIsNone(result["s_label"])
        self.assertIsNone(result["total_effectiveness_score"])
        self.assertEqual(result["compatibility_audit"][0]["status"], "UNKNOWN")

    def test_serial_method_diagnostics_check_each_stage_without_averaging(self):
        stages = [{"id": "s1", "method_name": "CUBIC", "quote": "CUBIC"},
                  {"id": "s2", "method_name": "iDISCO+", "quote": "iDISCO+"}]
        result = self.calculate(stages=stages)
        rows = [r for r in result["compatibility_audit"] if r["kind"] == "method_fluor"]
        self.assertEqual([(r["method_name"], r["value"]) for r in rows], [("CUBIC", 1), ("iDISCO+", 0)])
        self.assertEqual(result["method_identity"]["status"], "COMPOSITE_UNREVIEWED")
        self.assertIsNone(result["s_method"])
        self.assertIsNone(result["s_method_fluor_compat"])
        self.assertIsNone(result["s_trans"])
        self.assertIsNone(result["s_time"])

    def test_unnamed_composite_does_not_inherit_first_method_score(self):
        result = self.calculate("CUBIC -> iDISCO+")
        self.assertEqual(result["method_identity"]["status"], "COMPOSITE_UNREVIEWED")
        self.assertEqual(len([r for r in result["compatibility_audit"] if r["kind"] == "method_fluor"]), 2)
        self.assertIsNone(result["s_method"])


class SyntheticLegacyEntryTests(unittest.IsolatedAsyncioTestCase):
    def namespace(self):
        class Registry:
            questions = {"1": {"question_id": 1, "question": "fixture question"}}
            provenance = {"source": "synthetic fixture only"}

            def get(self, qid, text):
                if qid != 1 or text != "fixture question":
                    raise ValueError("Question snapshot mismatch")
                return {}

        def diagnostic(quantitative, *args):
            self.last_quantitative = quantitative
            return {"s_method": None, "s_label": None, "s_trans": None, "s_time": None,
                    "total_effectiveness_score": None, "method_identity": {"status": "UNKNOWN_METHOD"},
                    "compatibility_audit": [], "marker_coverage_audit": {},
                    "time_computation": time_score_details(None, None, "T")[1]}
        ns = {"re": re, "json": json, "datetime": datetime, "timezone": timezone, "asyncio": asyncio,
              "SCORING_VERSION": "synthetic-engineering-fixture",
              "QUESTION_META_KB": {1: {"tissue_ri_value": 1.48, "tissue_tier_code": "T", "marker_query_targets": []}},
              "fixed_demands": lambda: Registry(), "calculate_effectiveness_score": diagnostic,
              "_log_teacher_response": lambda *args, **kwargs: None,
              "json_hash": lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
              "time_reasoning": time_reasoning}
        ns.update({name: getattr(integrity, name) for name in (
            "parse_judge_object", "JudgeFormatError", "validate_score_proposals",
            "validate_legacy_extraction", "extraction_field_states", "legacy_integrity_audit")})
        return load_source_functions({"evaluate_response_with_teacher", "validate_teacher_extraction",
            "get_model_response", "_provider_generation_failed", "_is_valid_response"}, ns)

    def scores(self):
        return {"completeness": {"c_step": {"score": 2}, "c_param": {"score": 3}},
                "correctness": {k: {"score": v} for k, v in
                                (("co_order", 3), ("co_method", 2), ("co_param", 2), ("co_chem", 1))}}

    async def grade(self, extraction=None, protocol=None, raw=None):
        class Teacher:
            model_name = "offline-synthetic-only"

            async def _acall(self, prompt):
                return {"content": raw}
        if raw is None:
            raw = json.dumps({"scores": self.scores(), "extraction": extraction})
        ns = self.namespace()
        return await ns["evaluate_response_with_teacher"](Teacher(), "fixture question",
                protocol or "fixture protocol", {}, {"question_id": 1}, "")

    async def test_actual_async_entry_does_not_publish_unsupported_full_scores(self):
        value = {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": None}
        result = await self.grade(value)
        self.assertNotIn("_error", result)
        self.assertEqual(result["technical_status"], "VALID")
        self.assertEqual(result["scientific_status"], "UNRESOLVED")
        self.assertFalse(result["cce_eligible"])
        self.assertIsNone(result["official_scores"])
        self.assertNotIn("scores", result)
        self.assertEqual(result["legacy_diagnostics"]["scores"]["completeness"]["c_step"]["score"], 2)
        self.assertIsNone(result["quantitative_data"]["total_time_hours"])
        self.assertNotIn("protocol_time_hours", result["quantitative_data"])
        self.assertTrue(result["integrity"]["issues"])

    async def test_actual_async_entry_accepts_field_support_as_a_separate_audit(self):
        value, text = grounded_fixture()
        result = await self.grade(value, text)
        self.assertNotIn("_error", result)
        self.assertTrue(result["integrity"]["fidelity"]["validated"])
        self.assertEqual(result["integrity"]["fidelity"]["fidelity_status"], "FIELD_SUPPORT_VERIFIED")
        self.assertFalse(result["cce_eligible"])

    async def test_bad_format_is_technical_failure_without_quality_scores(self):
        result = await self.grade(raw='{"scores":{}, "scores":{}}')
        self.assertEqual(result["technical_status"], "FAILED")
        self.assertEqual(result["failure_stage"], "JSON_PARSE")
        self.assertNotIn("legacy_diagnostics", result)
        self.assertNotIn("scores", result)


def q4_score_shape(qid):
    # Exact score/null pattern observed in the frozen real Q4 teacher judgments.
    scores = {"completeness": {"c_step": {"score": 0 if qid == 79 else 1},
                               "c_param": {"score": 3}, "total_weighted_score": 3 if qid == 79 else 4},
              "correctness": {"co_order": {"score": 1 if qid == 79 else 3},
                              "co_method": {"score": 1 if qid == 79 else None,
                                            "reasoning": "Final optional matching-medium composition unresolved."},
                              "co_param": {"score": None,
                                           "reasoning": "Whole-organ parameter applicability lacks validation."},
                              "co_chem": {"score": 1}, "total_weighted_score": None}}
    return scores


class UnknownScoreContractTests(unittest.TestCase):
    def test_real_q4_null_patterns_are_preserved_without_imputation(self):
        for qid in (79, 165):
            scores = q4_score_shape(qid)
            before = copy.deepcopy(scores)
            self.assertIs(integrity.validate_score_proposals(scores), scores)
            self.assertEqual(scores, before)
            self.assertIsNone(scores["correctness"]["co_param"]["score"])
            self.assertIsNone(scores["correctness"]["total_weighted_score"])

    def test_unknown_group_rejects_any_supplied_numeric_or_invalid_total(self):
        for key in ("total_weighted_score", "total_correctness_score"):
            for total in (0, 3, True, "unknown", float("nan")):
                scores = q4_score_shape(165)
                scores["correctness"][key] = total
                with self.subTest(key=key, total=total), self.assertRaises(JudgeFormatError):
                    integrity.validate_score_proposals(scores)

    def test_unknown_needs_explicit_score_and_nonempty_reasoning(self):
        for record in ({}, {"reasoning": "missing score"}, {"score": None},
                       {"score": None, "reasoning": " "}, {"score": None, "reasoning": 2}):
            scores = q4_score_shape(79)
            scores["correctness"]["co_param"] = record
            with self.subTest(record=record), self.assertRaises(JudgeFormatError):
                integrity.validate_score_proposals(scores)

    def test_known_scores_still_reject_bool_out_of_range_and_nonfinite(self):
        for value in (True, False, -1, 3, float("nan"), float("inf"), "2"):
            scores = q4_score_shape(79)
            scores["correctness"]["co_method"]["score"] = value
            with self.subTest(value=value), self.assertRaises(JudgeFormatError):
                integrity.validate_score_proposals(scores)
        scores = q4_score_shape(79)
        scores["correctness"]["co_param"]["score"] = 0
        scores["correctness"]["total_weighted_score"] = 3
        integrity.validate_score_proposals(scores)
        scores["correctness"]["total_weighted_score"] = None
        with self.assertRaises(JudgeFormatError):
            integrity.validate_score_proposals(scores)


class Q4UnknownProductionResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_production_accepts_null_q4_shapes_and_resumes_without_rejudging(self):
        import tempfile
        from unittest.mock import patch
        import OEQ_run_grading_new as runner
        root = Path(runner.__file__).parent
        question_path = root / "dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json"
        questions = [q for q in json.loads(question_path.read_text(encoding="utf-8"))
                     if q["question_id"] in (79, 165)]
        outputs = {}
        entries = []
        for question in questions:
            qid = question["question_id"]
            extraction = {"method_name": "MACS", "clearing_total_time_hours": 72 if qid == 79 else None,
                          "reagent_ri_value": 1.51, "sample_ri_value": None, "protocol_time_hours": None,
                          "marker_dict": ({"Alexa Fluor 647": "CD31 (PECAM1)",
                                           "Alexa Fluor 488": "CD45", "DAPI": ""} if qid == 79
                                          else {"DiI": "", "DiD": ""})}
            outputs[qid] = json.dumps({"scores": q4_score_shape(qid), "extraction": extraction})
            entries.append({"question_id": qid, "specific_question": question["question"],
                            "model_response": "MACS; fixed sample; " + ("CD31/CD45/DAPI; 72 hours" if qid == 79
                                                                       else "DiI/DiD; final RI time unspecified")})
        class Teacher:
            model_name = "offline-real-q4-shape-regression"
            calls = 0
            async def _acall(self, prompt):
                self.calls += 1
                qid = next(q["question_id"] for q in questions if q["question"] in prompt)
                return {"content": outputs[qid]}
        teacher = Teacher()
        saved = {name: getattr(runner, name) for name in
                 ("QUESTION_FILE", "_QUESTION_LIST", "QUESTION_META_KB", "_FIXED_DEMANDS")}
        try:
            runner.configure_question_snapshot(str(question_path))
            with tempfile.TemporaryDirectory() as temp, patch.object(runner, "OEQ_SCORE_DIR", temp):
                path = await runner.evaluate_responses("q4-shape", entries, teacher, {}, "", eval_concurrency=1, assessment_mode='legacy')
                first = teacher.calls
                rows = json.loads(Path(path).read_text(encoding="utf-8"))
                self.assertEqual(first, 2)
                for row in rows:
                    evaluation = row["evaluation"]
                    self.assertNotIn("_error", evaluation)
                    self.assertEqual(evaluation["technical_status"], "VALID")
                    self.assertEqual(evaluation["scoring_status"], "LEGACY_DIAGNOSTIC_ONLY")
                    self.assertIsNone(evaluation["official_scores"])
                    block = evaluation["legacy_diagnostics"]["scores"]["correctness"]
                    self.assertIsNone(block["co_param"]["score"])
                    self.assertIsNone(block["total_weighted_score"])
                diagnostics = json.loads(Path(path + ".diagnostics.json").read_text(encoding="utf-8"))
                self.assertEqual(diagnostics["technical_valid_count"], 2)
                self.assertEqual(diagnostics["components"]["correctness.co_param"]["unknown_count"], 2)
                await runner.evaluate_responses("q4-shape", entries, teacher, {}, "", eval_concurrency=1, assessment_mode='legacy')
                self.assertEqual(teacher.calls, first)
        finally:
            for name, value in saved.items():
                setattr(runner, name, value)


if __name__ == "__main__":
    unittest.main()

