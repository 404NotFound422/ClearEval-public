"""Actual default CLI with fixed offline SDK fixtures and real current-task KB math.

These synthetic integration fixtures do not measure model or scientific accuracy.
No network/model experiment is performed; all SDK responses are fixed local text.
"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import OEQ_run_grading_new as runner
from benchmark_scoring import _record_hash, is_benchmark_complete
from evaluation_contract import json_hash
from results.aggregate_oeq import write_stats
from results.aggregate_rag_baseline import aggregate_file as rag_aggregate
from results.calculate_main_table_score import load_oeq

CURRENT = "dataset/Q+AR/src/question_final.json"
PROTOCOL = ("Chosen Method: CUBIC\nSynthetic fixture: clearing 48 hours; "
            "label NF200 with Alexa Fluor 647.\n" + "Fixed offline observation. " * 20)


def teacher_payload():
    return {"scores": {
        "completeness": {"c_step": {"score": 2}, "c_param": {"score": 3}},
        "correctness": {"co_order": {"score": 3}, "co_method": {"score": 2},
                        "co_param": {"score": 2}, "co_chem": {"score": 1}}},
        "extraction": {"method_name": "CUBIC", "marker_dict": {"Alexa Fluor 647": "NF200"},
                       "clearing_total_time_hours": 48}}


class BenchmarkActualCliTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = {name: getattr(runner, name) for name in (
            "QUESTION_FILE", "DEMAND_PROFILE", "DEMAND_FILE", "DEMAND_MANIFEST",
            "OEQ_SCORE_DIR", "OEQ_OUTPUT_DIR")}
        runner.DEMAND_PROFILE = "current-proposal"
        runner.configure_question_snapshot(CURRENT)
        self.qid = runner._QUESTION_LIST[0]["question_id"]

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(runner, name, value)
        runner.configure_question_snapshot(self.saved["QUESTION_FILE"])

    def fixture(self, directory, payload_factory=teacher_payload, protocol=PROTOCOL):
        class SDK:
            calls = []
            def __init__(self, **kwargs):
                pass
            def generate(self, **kwargs):
                SDK.calls.append(kwargs["model"])
                content = json.dumps(payload_factory()) if kwargs["model"] == "judge" else protocol
                return dict(response=content, done=True, done_reason="stop", eval_count=50)
            def close(self):
                pass
        directory = Path(directory)
        config = directory / "models.json"
        config.write_text(json.dumps({"models": [
            dict(name="candidate", type="Ollama", model_name="candidate", transport="sdk"),
            dict(name="judge", type="Ollama", model_name="judge", transport="sdk", format="json")]}),
            encoding="utf-8")
        responses, scores = directory / "responses", directory / "scores"
        args = ["--model-config", str(config), "--models", "candidate", "--teacher", "judge",
                "--qids", str(self.qid), "--question-file", CURRENT,
                "--response-dir", str(responses), "--score-dir", str(scores),
                "--eval-concurrency", "1", "--gen-concurrency", "1"]
        return SDK, args, scores / "evaluation_results_candidate_1-shot.json", responses / "from_candidate_1-shot.json"

    async def test_default_generation_teacher_cache_stats_and_real_kb(self):
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                first = json.loads(path.read_text(encoding="utf-8"))[0]
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                second = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(SDK.calls, ["candidate", "judge"])
            self.assertEqual(first, second)
            evaluation = second["evaluation"]
            self.assertTrue(is_benchmark_complete(evaluation, PROTOCOL))
            self.assertEqual(evaluation["scientific_status"], "UNRESOLVED")
            self.assertEqual(evaluation["demand_provenance"]["numeric_scale_status"],
                             "UNCALIBRATED_PROJECTION_FOR_REVIEW")
            self.assertEqual(evaluation["scores"]["effectiveness"]["s_label"]["score"], 0)
            self.assertEqual(evaluation["scores"]["effectiveness"]["s_time"]["computation"]["source"], "time_kb.json")
            self.assertFalse(evaluation["cce_eligible"])
            self.assertIsNone(evaluation["official_scores"])
            manifest = json.loads(Path(str(path) + ".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["contract"]["assessment_mode"], "benchmark")
            output = Path(tmp) / "stats.jsonl"
            row = write_stats([path], output)[0]
            table = load_oeq(output)["candidate"]
            rag = rag_aggregate(path)
            self.assertEqual(row["sample_count"], 1)
            self.assertEqual(table["I_A"], rag["I_A"])
            self.assertEqual(table["scientific_status_counts"], {"UNRESOLVED": 1})
            self.assertIn("AUTOMATED_BENCHMARK_ESTIMATE_NOT_SCIENTIFIC_CERTIFICATION",
                          table["score_interpretation_counts"])

    async def test_self_rehashed_effectiveness_tamper_replays_kb_and_calls_teacher_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                records = json.loads(path.read_text(encoding="utf-8"))
                ev = records[0]["evaluation"]
                original = ev["scores"]["effectiveness"]["s_time"]["score"]
                changed = 3 if original != 3 else 0
                ev["scores"]["effectiveness"]["s_time"]["score"] = changed
                ev["legacy_diagnostics"]["scores"]["effectiveness"]["s_time"]["score"] = changed
                ev["scores_sha256"] = json_hash(ev["scores"])
                ev["benchmark_record_sha256"] = _record_hash(ev)
                # Numeric-only rehash cannot repair the bound robustness score witness.
                self.assertFalse(is_benchmark_complete(ev, PROTOCOL))
                path.write_text(json.dumps(records), encoding="utf-8")
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                after = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(SDK.calls, ["candidate", "judge", "judge"])
            self.assertEqual(after["evaluation"]["scores"]["effectiveness"]["s_time"]["score"], original)
            self.assertEqual(len(after["previous_attempts"]), 1)

    async def test_changed_response_and_scoring_version_reject_before_teacher(self):
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                original = response_path.read_text(encoding="utf-8")
                responses = json.loads(original)
                responses[0]["model_response"] += " Changed local fixture."
                response_path.write_text(json.dumps(responses), encoding="utf-8")
                self.assertNotEqual(await runner.main(args + ["--eval-only"]), 0)
                self.assertEqual(SDK.calls, ["candidate", "judge"])
                response_path.write_text(original, encoding="utf-8")
                with patch.object(runner, "SCORING_VERSION", runner.SCORING_VERSION + "-changed-fixture"):
                    self.assertNotEqual(await runner.main(args + ["--eval-only"]), 0)
                self.assertEqual(SDK.calls, ["candidate", "judge"])


    async def test_manifest_prevents_scoring_status_downgrade_in_both_consumers(self):
        from results.aggregate_oeq import aggregate_file
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
            records = json.loads(path.read_text(encoding="utf-8"))
            records[0]["evaluation"]["scoring_status"] = "HISTORICAL"
            path.write_text(json.dumps(records), encoding="utf-8")
            for consumer in (aggregate_file, rag_aggregate):
                with self.subTest(consumer=consumer.__module__):
                    with self.assertRaisesRegex(ValueError, "Invalid automated"):
                        consumer(path)
            self.assertEqual(SDK.calls, ["candidate", "judge"])


    async def test_legal_teacher_null_is_terminal_unresolved_without_retry(self):
        from benchmark_scoring import is_benchmark_record_complete
        def proposal():
            value = teacher_payload()
            value["scores"]["correctness"]["co_param"] = {
                "score": None, "reasoning": "Synthetic fixture: applicability unresolved."}
            return value
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp, payload_factory=proposal)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                records = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                self.assertEqual(records, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(SDK.calls, ["candidate", "judge"])
            ev = records[0]["evaluation"]
            self.assertTrue(is_benchmark_record_complete(ev, PROTOCOL))
            self.assertEqual(ev["technical_status"], "VALID")
            self.assertEqual(ev["scoring_status"], "BENCHMARK_UNRESOLVED")
            self.assertTrue(ev["workflow_diagnostics_required"])
            self.assertEqual(ev["workflow_diagnostics"]["objective_diagnostics"]["status"], "U")
            self.assertNotIn("scores", ev)
            self.assertIsNone(ev["legacy_diagnostics"]["scores"]["correctness"]["co_param"]["score"])
            self.assertTrue(ev["unknown_components"])
            summary = json.loads(Path(str(path) + ".diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["benchmark_unresolved_count"], 1)
            self.assertEqual(summary["technical_valid_count"], 1)
            self.assertEqual(summary["technical_failure_count"], 0)
            self.assertEqual(summary["full_input_coverage"], 0)
            stats = write_stats([path], Path(tmp) / "stats.jsonl")[0]
            rag = rag_aggregate(path)
            self.assertEqual(stats["sample_count"], 0)
            self.assertEqual(stats["total_items"], 1)
            self.assertEqual(stats["coverage"], 0)
            self.assertIsNone(stats["application_index"])
            self.assertEqual(stats["scoring_status_counts"], {"BENCHMARK_UNRESOLVED": 1})
            self.assertEqual(rag["n"], 0)
            self.assertEqual(rag["total_items"], 1)

    async def test_missing_kb_compatibility_is_terminal_unresolved_without_retry(self):
        from benchmark_scoring import is_benchmark_record_complete
        def proposal():
            value = teacher_payload()
            value["extraction"]["marker_dict"] = {"FixtureUnlistedFluor": "C-FoS"}
            return value
        protocol = ("Chosen Method: CUBIC. Synthetic fixture: clearing 48 hours; "
                    "label C-FoS with FixtureUnlistedFluor. " + "Fixed offline observation. " * 20)
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, response_path = self.fixture(tmp, payload_factory=proposal, protocol=protocol)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                first = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                self.assertEqual(first, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(SDK.calls, ["candidate", "judge"])
            ev = first[0]["evaluation"]
            self.assertTrue(is_benchmark_record_complete(ev, protocol))
            self.assertEqual(ev["scoring_status"], "BENCHMARK_UNRESOLVED")
            self.assertTrue(ev["workflow_diagnostics_required"])
            self.assertEqual(ev["workflow_diagnostics"]["objective_diagnostics"]["status"], "U")
            self.assertIsNone(ev["legacy_diagnostics"]["scores"]["effectiveness"]["s_label"]["score"])
            stats = write_stats([path], Path(tmp) / "stats.jsonl")[0]
            self.assertEqual(stats["coverage"], 0)
            self.assertEqual(stats["total_items"], 1)

    async def test_malformed_scores_or_invented_stage_quote_remain_failures(self):
        def malformed():
            value = teacher_payload()
            del value["scores"]["correctness"]["co_param"]
            return value
        def invented_quote():
            value = teacher_payload()
            value["extraction"]["method_stages"] = [{
                "id": "stage", "method_name": "CUBIC", "quote": "invented absent fixture quote"}]
            return value
        def invented_quote_and_null():
            value = invented_quote()
            value["scores"]["correctness"]["co_param"] = {
                "score": None, "reasoning": "Fixture null cannot excuse an invented quotation."}
            return value
        for proposal in (malformed, invented_quote, invented_quote_and_null):
            with self.subTest(proposal=proposal.__name__), tempfile.TemporaryDirectory() as tmp:
                SDK, args, path, response_path = self.fixture(tmp, payload_factory=proposal)
                with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                    self.assertNotEqual(await runner.main(args), 0)
                ev = json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
                self.assertEqual(ev["technical_status"], "FAILED")
                self.assertNotIn("scores", ev)


    async def test_default_scientific_diagnostics_bound_to_sources_and_stats(self):
        from benchmark_scoring import is_workflow_obligation_complete, workflow_sources_match_contract
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
            ev = json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            contract = json.loads(Path(str(path) + ".manifest.json").read_text(encoding="utf-8"))["contract"]
            self.assertTrue(contract["workflow_diagnostics_required"])
            self.assertTrue(is_workflow_obligation_complete(ev, PROTOCOL))
            self.assertTrue(workflow_sources_match_contract(ev, contract))
            diag = ev["workflow_diagnostics"]
            self.assertEqual(diag["question_sha256"], json_hash(runner.fixed_demands().questions[str(self.qid)]))
            self.assertEqual(diag["scientific_status"], "U")
            self.assertEqual(diag["objective_diagnostics"]["relationship"], "UNRESOLVED")
            self.assertEqual(diag["candidate_necessity_diagnostics"]["status"], "U")
            self.assertNotIn("prompt", diag)
            self.assertTrue(diag["source_inventory"])
            for name, digest in diag["resource_bindings"].items():
                self.assertEqual(contract["source_sha256"][name], digest)
            for name, digest in diag["implementation_hashes"].items():
                self.assertEqual(contract["source_sha256"][name], digest)
            row = write_stats([path], Path(tmp) / "stats.jsonl")[0]
            self.assertEqual(row["workflow_diagnostics_summary"]["diagnostic_complete_count"], 1)
            self.assertEqual(row["workflow_diagnostics_summary"]["scientific_certified_count"], 0)
            self.assertIsNone(row["workflow_diagnostics_summary"]["scientific_accuracy"])
            self.assertEqual(load_oeq(Path(tmp) / "stats.jsonl")["candidate"]["workflow_diagnostics_summary"],
                             rag_aggregate(path)["workflow_diagnostics_summary"])
            self.assertEqual(SDK.calls, ["candidate", "judge"])

    async def test_sidecar_self_rehash_is_rebuilt_without_teacher_and_keeps_history(self):
        from results.aggregate_oeq import aggregate_file
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                records = json.loads(path.read_text(encoding="utf-8"))
                pristine = json.loads(json.dumps(records[0]["evaluation"]))
                ev = records[0]["evaluation"]
                diag = ev["workflow_diagnostics"]
                diag["candidate_necessity_diagnostics"]["status"] = "SATISFIED"
                diag["diagnostics_sha256"] = json_hash({k:v for k,v in diag.items() if k != "diagnostics_sha256"})
                ev["workflow_diagnostics_sha256"] = json_hash(diag)
                ev["benchmark_record_sha256"] = _record_hash(ev)
                path.write_text(json.dumps(records), encoding="utf-8")
                for consumer in (aggregate_file, rag_aggregate):
                    with self.assertRaisesRegex(ValueError, "workflow diagnostics"):
                        consumer(path)
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                repaired = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(SDK.calls, ["candidate", "judge"])
            self.assertEqual(repaired["evaluation"], pristine)
            self.assertEqual(len(repaired["previous_attempts"]), 1)
            self.assertEqual(repaired["previous_attempts"][0]["evaluation"]["workflow_diagnostics"]
                             ["candidate_necessity_diagnostics"]["status"], "SATISFIED")

    async def test_deleted_diagnostic_obligation_repaired_with_zero_extra_judge(self):
        from results.aggregate_oeq import aggregate_file
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
                records = json.loads(path.read_text(encoding="utf-8"))
                ev = records[0]["evaluation"]
                for key in list(ev):
                    if key.startswith("workflow_diagnostics"):
                        ev.pop(key)
                ev["benchmark_record_sha256"] = _record_hash(ev)
                path.write_text(json.dumps(records), encoding="utf-8")
                for consumer in (aggregate_file, rag_aggregate):
                    with self.assertRaisesRegex(ValueError, "workflow diagnostics"):
                        consumer(path)
                self.assertEqual(await runner.main(args + ["--eval-only"]), 0)
                repaired = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertTrue(repaired["evaluation"]["workflow_diagnostics_required"])
            self.assertEqual(SDK.calls, ["candidate", "judge"])
            self.assertEqual(len(repaired["previous_attempts"]), 1)

    async def test_deleted_manifest_is_rejected_in_all_result_consumers(self):
        from results.aggregate_oeq import aggregate_file
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
            output = Path(tmp) / "stats.jsonl"
            row = write_stats([path], output)[0]
            Path(str(path) + ".manifest.json").unlink()
            for consumer in (aggregate_file, rag_aggregate):
                with self.assertRaisesRegex(ValueError, "manifest"):
                    consumer(path)
            row["scoring_contract"] = None
            output.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest"):
                load_oeq(output)

    async def test_failed_teacher_retains_default_source_warning_and_full_denominator(self):
        protocol = PROTOCOL + "\nStore the sample in CUBIC-R+(M) (Temperature: 4 C, Time: 7 days)"
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp, payload_factory=lambda: "unfinished", protocol=protocol)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertNotEqual(await runner.main(args), 0)
            ev = json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            self.assertEqual(ev["technical_status"], "FAILED")
            self.assertEqual(ev["workflow_diagnostics"]["source_condition_diagnostics"]["potential_conflict_count"], 1)
            row = write_stats([path], Path(tmp) / "stats.jsonl")[0]
            self.assertEqual(row["sample_count"], 0)
            self.assertEqual(row["total_items"], 1)
            self.assertEqual(row["workflow_diagnostics_summary"]["diagnostic_complete_count"], 1)
            self.assertEqual(row["workflow_diagnostics_summary"]["source_guidance_potential_conflict_count"], 1)
            self.assertEqual(SDK.calls, ["candidate", "judge"])

    async def test_broken_source_diagnostics_fail_before_teacher_with_explicit_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}), patch(
                    "oeq_workflow_diagnostics.build_workflow_diagnostics", side_effect=ValueError("synthetic source hash failure")):
                self.assertNotEqual(await runner.main(args), 0)
            ev = json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            self.assertEqual(ev["failure_stage"], "WORKFLOW_DIAGNOSTICS")
            self.assertEqual(ev["technical_status"], "FAILED")
            self.assertEqual(SDK.calls, ["candidate"])
            output = Path(tmp) / "stats.jsonl"
            row = write_stats([path], output)[0]
            self.assertEqual(row["total_items"], 1)
            self.assertEqual(row["sample_count"], 0)
            self.assertEqual(row["workflow_diagnostics_summary"]["diagnostic_construction_failure_count"], 1)
            self.assertEqual(row["workflow_diagnostics_summary"]["diagnostic_missing_count"], 0)
            self.assertEqual(load_oeq(output), {})
            self.assertEqual(rag_aggregate(path)["workflow_diagnostics_summary"], row["workflow_diagnostics_summary"])


    async def test_main_table_score_cannot_borrow_a_construction_failure_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            SDK, args, path, _ = self.fixture(tmp)
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args), 0)
            output = Path(tmp) / "stats.jsonl"
            row = write_stats([path], output)[0]
            summary = row["workflow_diagnostics_summary"]
            summary.update(diagnostic_complete_count=0, diagnostic_construction_failure_count=1,
                           diagnostic_coverage=0)
            summary["summary_sha256"] = json_hash({k:v for k,v in summary.items() if k != "summary_sha256"})
            output.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage exceeds"):
                load_oeq(output)


if __name__ == "__main__":
    unittest.main()

