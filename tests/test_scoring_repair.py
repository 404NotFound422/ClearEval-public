"""Offline regression checks for score semantics and version-safe resumption.

Run from the repository root: python -m unittest discover -s tests -v
No model clients, API keys, or network calls are needed.
"""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import OEQ_run_grading_new as runner
from evaluation_contract import FixedDemandRegistry, ensure_manifest, time_score_details
from results.oeq_metrics import aggregate_items, paired_deltas, protocol_scores
from results.calculate_main_table_score import load_oeq
from results.aggregate_rag_baseline import aggregate_file

OLD_QUESTIONS = 'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
DEMANDS = 'dataset/Q+AR/src/demand_vectors_all.json'


def scored_item(qid, com=1.0, cor=1.0, eff=1.0):
    return {'question_id': qid, 'evaluation': {'scores': {
        'completeness': {'c_step': {'score': 2 * com}, 'c_param': {'score': 3 * com}},
        'correctness': {key: {'score': maximum * cor} for key, maximum in
                        [('co_order', 3), ('co_method', 2), ('co_param', 2), ('co_chem', 1)]},
        'effectiveness': {'s_method': {'score': 2.5 * (2 * eff - 1)},
                          's_label': {'score': 6 * eff}, 's_trans': {'score': 3 * eff},
                          's_time': {'score': 3 * eff}},
    }}}


class AggregationTests(unittest.TestCase):
    def test_different_protocol_bottlenecks_are_not_hidden(self):
        agg = aggregate_items([scored_item(1, com=0), scored_item(2, cor=0)])
        self.assertEqual(agg['application_index'], 0)
        self.assertEqual(agg['indices']['I_A_min_of_means'], 0.5)

    def test_signed_method_extremes(self):
        self.assertEqual(protocol_scores(scored_item(1, eff=0))['s_method'], 0)
        self.assertEqual(protocol_scores(scored_item(1, eff=1))['s_method'], 1)

    def test_partial_scores_are_excluded_from_every_dimension(self):
        partial = scored_item(2, com=0)
        del partial['evaluation']['scores']['effectiveness']['s_time']
        agg = aggregate_items([scored_item(1), partial, {'question_id': 3, 'evaluation': {'_error': 'parse'}}])
        self.assertEqual(agg['sample_count'], 1)
        self.assertEqual(agg['coverage'], 1 / 3)
        self.assertEqual(agg['indices']['Com'], 1)
        self.assertEqual(len(agg['excluded_items']), 2)

    def test_duplicate_ids_do_not_double_weight_a_question(self):
        agg = aggregate_items([scored_item(1), scored_item('1'), scored_item(2)])
        self.assertEqual(agg['sample_count'], 1)
        self.assertEqual(len(agg['excluded_items']), 2)

    def test_bad_numeric_scores_are_not_clamped_or_zero_imputed(self):
        for value in (None, True, float('nan'), float('inf'), 4, -1):
            with self.subTest(value=value):
                item = scored_item(1)
                item['evaluation']['scores']['effectiveness']['s_time']['score'] = value
                agg = aggregate_items([item])
                self.assertEqual(agg['sample_count'], 0)
                self.assertIsNone(agg['application_index'])

    def test_failed_condition_remains_visible_in_csv_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'failed.json'
            path.write_text(json.dumps([{'question_id': 1, 'evaluation': {'_error': 'parse'}}]), encoding='utf-8')
            row = aggregate_file(path)
            self.assertEqual(row['n'], 0)
            self.assertEqual(row['coverage'], 0)
            self.assertIsNone(row['I_A'])

    def test_comparisons_use_shared_valid_ids(self):
        base = [scored_item(1, com=0, cor=0, eff=0), scored_item(2)]
        treatment = [scored_item(2, com=0.5, cor=0.5, eff=0.5),
                     {'question_id': 1, 'evaluation': {'_error': 'parse'}}]
        deltas = paired_deltas(base, treatment)
        self.assertEqual(deltas['n_paired'], 1)
        self.assertEqual(deltas['d_I_A'], -50)

    def test_revised_question_text_is_not_a_paired_observation(self):
        baseline, changed = scored_item(1), scored_item(1)
        baseline['evaluation']['meta_data'] = {'sample_info': 'original stem'}
        changed['evaluation']['meta_data'] = {'sample_info': 'revised stem'}
        with self.assertRaisesRegex(ValueError, 'Cannot pair'):
            paired_deltas([baseline], [changed])

    def test_main_table_requires_protocol_level_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'stats.jsonl'
            record = {'model_name': 'test', **aggregate_items([scored_item(1, com=0), scored_item(2, cor=0)])}
            path.write_text(json.dumps(record) + '\n', encoding='utf-8')
            self.assertEqual(load_oeq(path)['test']['I_A'], 0)
            del record['aggregation_version']
            path.write_text(json.dumps(record) + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'legacy aggregation'):
                load_oeq(path)


class TimeScoringTests(unittest.TestCase):
    row = {'clearing_time_min_h': 20, 'clearing_time_max_h': 40, 'clearing_time_median_h': 30}

    def test_both_window_boundaries_receive_full_score(self):
        for actual in (20, 30, 40):
            score, detail = time_score_details(actual, self.row, 'T')
            self.assertEqual(score, 3)
            self.assertEqual(detail['delta_hours'], 0)

    def test_asymmetric_tolerances_are_explicit(self):
        faster, under = time_score_details(14, self.row, 'T')
        slower, over = time_score_details(46, self.row, 'T')
        self.assertAlmostEqual(faster, 3 * math.exp(-0.5))
        self.assertAlmostEqual(slower, 3 * math.exp(-2))
        self.assertEqual(under['tau_hours'], 6)
        self.assertEqual(over['tau_hours'], 3)

    def test_missing_extraction_is_distinguished_from_missing_kb(self):
        score, detail = time_score_details(None, self.row, 'T')
        self.assertIsNone(score)
        self.assertEqual(detail['status'], 'missing_or_invalid_time')
        self.assertEqual(time_score_details(30, None, 'T')[1]['status'], 'missing_kb')
        self.assertEqual(time_score_details(float('nan'), self.row, 'T')[1]['status'], 'missing_or_invalid_time')

    def test_all_published_time_windows_are_accepted(self):
        for method, tiers in runner.TIME_KB_LOOKUP.items():
            for tier, row in tiers.items():
                with self.subTest(method=method, tier=tier):
                    score, detail = time_score_details(row['clearing_time_median_h'], row, tier)
                    if method in ("boneclear", "switch") and ("染色步骤" in row.get("time_scope", "")):
                        self.assertIsNone(score)
                        self.assertEqual(detail["status"], "time_scope_conflict")
                    else:
                        self.assertEqual(score, 3)
                        self.assertEqual(detail['status'], 'scored')

    def test_explicit_time_scope_conflict_preserves_window_but_blocks_score(self):
        row = {"clearing_time_min_h": 1, "clearing_time_median_h": 2, "clearing_time_max_h": 3,
               "time_excludes_labeling": "yes", "time_scope": "包括固定、染色步骤、洗涤"}
        score, detail = time_score_details(2, row, "synthetic")
        self.assertIsNone(score)
        self.assertEqual(detail["status"], "time_scope_conflict")
        self.assertEqual((detail["min_hours"], detail["median_hours"], detail["max_hours"]), (1, 2, 3))
        row["time_scope"] = "包括脱脂、洗涤；不含免疫/染料标记步骤"
        self.assertEqual(time_score_details(2, row, "synthetic")[0], 3)
        row["time_scope"] = "Includes fixation and staining; before imaging"
        self.assertIsNone(time_score_details(2, row, "synthetic")[0])
        row["time_scope"] = "Includes washing, excluding labeling"
        self.assertEqual(time_score_details(2, row, "synthetic")[0], 3)


class VersionTests(unittest.TestCase):
    def test_binding_survives_json_whitespace_and_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / 'questions.json'
            data = json.loads(Path(OLD_QUESTIONS).read_text(encoding='utf-8'))
            copied.write_bytes(json.dumps(data, indent=1).replace('\n', '\r\n').encode('utf-8'))
            registry = FixedDemandRegistry(copied, DEMANDS)
            self.assertEqual(len(registry.questions), 253)

    def test_fixed_demands_are_copies_and_require_exact_question(self):
        registry = FixedDemandRegistry(OLD_QUESTIONS, DEMANDS)
        qid, question = next(iter(registry.questions.items()))
        vector = registry.get(qid, question['question'])
        vector['clearing_challenge']['target'] = 999
        self.assertNotEqual(registry.get(qid, question['question'])['clearing_challenge']['target'], 999)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            registry.get(qid, question['question'] + 'changed')

    def test_revised_questions_cannot_reuse_old_vector_binding(self):
        with self.assertRaisesRegex(ValueError, 'version mismatch'):
            FixedDemandRegistry('dataset/Q+AR/src/question_final.json', DEMANDS)

    def test_unversioned_and_changed_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'output.json'
            path.write_text('original', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unversioned'):
                ensure_manifest(path, {'version': 2})
            self.assertEqual(path.read_text(encoding='utf-8'), 'original')
            new_path = Path(tmp) / 'new.json'
            first = ensure_manifest(new_path, {'version': 2})
            self.assertEqual(first, ensure_manifest(new_path, {'version': 2}))
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                ensure_manifest(new_path, {'version': 3})


class FakeTeacher:
    model_name = 'offline-fixture'

    def __init__(self):
        self.calls = 0

    async def _acall(self, prompt):
        self.calls += 1
        scores = scored_item(1)['evaluation']['scores']
        return {'content': json.dumps({'scores': scores, 'extraction': {
            'method_name': 'iDISCO+', 'clearing_total_time_hours': 35,
            'protocol_time_hours': [9999, 10000], 'marker_dict': {'Alexa Fluor 647': 'NF200'},
        }})}


class FakeGenerator:
    model_name = "offline-generator"

    def __init__(self):
        self._acall = AsyncMock()


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_profile = runner.DEMAND_PROFILE
        runner.DEMAND_PROFILE = "fixed"
        self.previous_question_file = runner.QUESTION_FILE
        self.previous_demands, self.previous_manifest = runner.DEMAND_FILE, runner.DEMAND_MANIFEST
        runner.DEMAND_FILE, runner.DEMAND_MANIFEST = DEMANDS, None
        runner.configure_question_snapshot(OLD_QUESTIONS)
        self.question = next(q for q in runner._QUESTION_LIST if q['question_id'] == 5)
        self.teacher = FakeTeacher()
        self.log_patch = patch.object(runner, '_log_teacher_response')
        self.log_patch.start()

    def tearDown(self):
        self.log_patch.stop()
        runner.DEMAND_PROFILE = self.previous_profile
        runner.DEMAND_FILE, runner.DEMAND_MANIFEST = self.previous_demands, self.previous_manifest
        runner.configure_question_snapshot(self.previous_question_file)

    def response(self, q=None):
        q = q or self.question
        return {'question_id': q['question_id'], 'specific_question': q['question'],
                'model_response': '**Chosen Method:** iDISCO+\n**Protocol Steps:** ' + 'fixture ' * 40}

    async def test_one_judge_call_fixed_demand_and_actual_time_explanation(self):
        entry = self.response()
        with patch.object(runner, 'get_user_preference_vector', side_effect=AssertionError('live inference forbidden')):
            result = await runner.evaluate_response_with_teacher(
                self.teacher, entry['specific_question'], entry['model_response'], {}, entry, '')
        self.assertNotIn('_error', result)
        self.assertEqual(self.teacher.calls, 1)
        eff = result['legacy_diagnostics']['scores']['effectiveness']
        detail = eff['s_time']['computation']
        self.assertNotIn('9999', eff['s_time']['reasoning'])
        self.assertIn(str(detail['min_hours']), eff['s_time']['reasoning'])
        self.assertEqual(result['extraction']['protocol_time_hours'], [9999, 10000])
        self.assertFalse(result['cce_eligible'])
        self.assertIsNone(result['official_scores'])
        self.assertNotIn('scores', result)
        self.assertEqual(result['integrity']['fidelity']['fidelity_status'], 'LEGACY_STRUCTURE_ONLY')
        expected = runner.calculate_method_suitability(runner.fixed_demands().get(5, self.question['question']),
                                                       runner.find_signed_method('iDISCO+'))
        self.assertEqual(eff['s_method']['score'], expected)
        self.assertNotIn('generated_timestamp', result['meta_data'])

    async def test_normal_process_reports_completed_diagnostics_without_science_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runner, "OEQ_SCORE_DIR", tmp), patch.object(runner, "process_model", return_value=[self.response()]):
                summary = await runner.process_and_evaluate_model(
                    "offline-local", object(), [self.question], {}, [], self.teacher, {}, "",
                    shot_type="1-shot", eval_concurrency=1, gen_concurrency=1, assessment_mode="legacy")
            self.assertIsNone(summary["error"])
            self.assertEqual(summary["n_evaluated"], 1)
            self.assertEqual(summary["n_legacy_diagnostics"], 1)
            self.assertEqual(summary["n_official_scores"], 0)
            sidecar = json.loads((Path(tmp) / "evaluation_results_offline-local_1-shot.json.diagnostics.json").read_text(encoding="utf-8"))
            indices = sidecar["legacy_continuous_indices"]
            self.assertEqual(indices["status"], "UNCALIBRATED_QUALITY_DIAGNOSTIC")
            self.assertEqual(indices["complete_count"], 1)
            self.assertEqual(set(indices["means"]), {"Com", "Cor", "Eff", "I_A"})
            self.assertIsNone(sidecar["formal_cce"])

    async def test_normal_main_loads_config_generates_grades_and_saves_diagnostics(self):
        from types import SimpleNamespace
        class SDKClient:
            calls = []
            def __init__(self, **kwargs):
                pass
            def generate(self, **kwargs):
                SDKClient.calls.append(kwargs["model"])
                if kwargs["model"] == "offline-teacher":
                    payload = {"scores": scored_item(1)["evaluation"]["scores"], "extraction": {
                        "method_name": "iDISCO+", "clearing_total_time_hours": 35,
                        "marker_dict": {"Alexa Fluor 647": "NF200"}}}
                    content = json.dumps(payload)
                else:
                    content = "**Chosen Method:** iDISCO+\n**Protocol Steps:** " + "offline fixture " * 40
                return {"response": content, "done": True, "done_reason": "stop", "eval_count": 20}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "models.json"
            config.write_text(json.dumps({"models": [
                {"name": "offline-local", "type": "Ollama", "model_name": "offline-generator", "transport": "sdk"},
                {"name": "offline-teacher", "type": "Ollama", "model_name": "offline-teacher", "transport": "sdk", "format": "json"},
            ]}), encoding="utf-8")
            responses, scores = Path(tmp) / "responses", Path(tmp) / "scores"
            with patch.dict("sys.modules", {"ollama": SimpleNamespace(Client=SDKClient)}), patch.object(
                    runner, "OEQ_OUTPUT_DIR", str(responses)), patch.object(runner, "OEQ_SCORE_DIR", str(scores)):
                code = await runner.main([
                    "--assessment-mode", "legacy", "--model-config", str(config), "--models", "offline-local", "--teacher", "offline-teacher",
                    "--question-file", OLD_QUESTIONS, "--demand-vectors", DEMANDS, "--qids", "5",
                    "--gen-concurrency", "1", "--eval-concurrency", "1",
                    "--response-dir", str(responses), "--score-dir", str(scores),
                ])
            self.assertEqual(code, 0)
            self.assertEqual(SDKClient.calls, ["offline-generator", "offline-teacher"])
            self.assertTrue((responses / "from_offline-local_1-shot.json").is_file())
            sidecar = json.loads((scores / "evaluation_results_offline-local_1-shot.json.diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(sidecar["technical_valid_count"], 1)
            self.assertEqual(sidecar["legacy_continuous_indices"]["complete_count"], 1)
            self.assertIsNone(sidecar["formal_cce"])

    async def test_preflight_only_creates_no_clients_and_reports_missing_config(self):
        from models.Model_Loader import ModelLoader
        with patch.object(ModelLoader, "load_models", side_effect=AssertionError("client construction forbidden")):
            code = await runner.main(["--preflight-only", "--question-file", OLD_QUESTIONS,
                                     "--demand-vectors", DEMANDS, "--model-config", "nonexistent-model-config.json"])
        self.assertEqual(code, 2)

    async def test_teacher_successful_provider_metadata_is_preserved(self):
        entry = self.response()
        content = json.dumps({"scores": scored_item(1)["evaluation"]["scores"],
            "extraction": {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": None}})
        teacher = FakeGenerator()
        metadata = {"technical_status": "VALID", "finish_reason": "stop", "completion_tokens": 123}
        teacher._acall.return_value = {"content": content, "metadata": metadata}
        result = await runner.evaluate_response_with_teacher(
            teacher, entry["specific_question"], entry["model_response"], {}, entry, "")
        self.assertEqual(result["technical_status"], "VALID")
        self.assertEqual(result["teacher_generation"]["metadata"], metadata)
        self.assertEqual(result["teacher_generation"]["raw_content"], content)

    async def test_teacher_valid_json_with_failed_metadata_is_not_completed(self):
        entry = self.response()
        content = json.dumps({"scores": scored_item(1)["evaluation"]["scores"],
            "extraction": {"method_name": None, "marker_dict": {}, "clearing_total_time_hours": None}})
        teacher = FakeGenerator()
        teacher._acall.return_value = {"content": content,
            "metadata": {"technical_status": "FAILED", "finish_reason": "length"}}
        result = await runner.evaluate_response_with_teacher(
            teacher, entry["specific_question"], entry["model_response"], {}, entry, "")
        self.assertEqual(result["technical_status"], "FAILED")
        self.assertEqual(result["failure_stage"], "TEACHER_GENERATION")
        self.assertEqual(result["teacher_generation"]["raw_content"], content)
        self.assertNotIn("legacy_diagnostics", result)
        self.assertEqual(teacher._acall.await_count, 1)

    async def test_teacher_exception_partial_and_safe_metadata_are_preserved(self):
        entry = self.response()
        partial = '{"scores": {"completeness":'
        class OutputError(ValueError):
            def __init__(self):
                super().__init__("Bearer test-private-credential")
                self.response_data = {"content": "", "raw_content": partial,
                    "metadata": {"technical_status": "FAILED", "finish_reason": "length"}}
        teacher = FakeGenerator()
        teacher._acall.side_effect = OutputError()
        result = await runner.evaluate_response_with_teacher(
            teacher, entry["specific_question"], entry["model_response"], {}, entry, "")
        self.assertEqual(result["technical_status"], "FAILED")
        self.assertEqual(result["teacher_generation"]["raw_content"], partial)
        self.assertEqual(result["teacher_generation"]["metadata"]["finish_reason"], "length")
        self.assertNotIn("test-private-credential", json.dumps(result))
        self.assertNotIn("legacy_diagnostics", result)
        self.assertEqual(teacher._acall.await_count, 1)

    async def test_bad_question_fails_before_judge_call(self):
        entry = self.response()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            await runner.evaluate_response_with_teacher(self.teacher, 'different question', entry['model_response'], {}, entry, '')
        self.assertEqual(self.teacher.calls, 0)

    async def test_missing_extraction_is_failure_not_zero_quality(self):
        entry = self.response()
        teacher = AsyncMock()
        teacher.model_name = 'synthetic-test-only'
        teacher._acall.return_value = {'content': json.dumps({'scores': scored_item(1)['evaluation']['scores']})}
        result = await runner.evaluate_response_with_teacher(
            teacher, entry['specific_question'], entry['model_response'], {}, entry, '')
        self.assertIn('missing required fields', result['_error'])
        self.assertNotIn('scores', result)

    def test_explicit_unknown_extraction_is_distinct_from_malformed_output(self):
        valid = {'method_name': None, 'marker_dict': {}, 'clearing_total_time_hours': None}
        runner.validate_teacher_extraction(valid)
        for key, value in [('marker_dict', []), ('clearing_total_time_hours', True),
                           ('clearing_total_time_hours', float('nan')), ('method_name', 7)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                runner.validate_teacher_extraction({**valid, key: value})

    def test_final_rubric_schema_is_valid_json(self):
        text = Path('prompts/eval_oeq_teacher_rubric.txt').read_text(encoding='utf-8')
        example = text.split('Now, please analyze the MODEL_PROTOCOL carefully and output a JSON object:')[1]
        value = json.loads(example[:example.rfind('}') + 1].strip())
        self.assertIsInstance(value['meta_data']['sample_info'], str)
        self.assertIsNone(value['extraction']['protocol_time_hours'])

    async def test_single_method_pipeline_writes_explicit_diagnostics_and_kb_coverage(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            entry = self.response()
            path = await runner.evaluate_responses('single-method-smoke', [entry], self.teacher, {}, '', assessment_mode='legacy')
            records = json.loads(Path(path).read_text(encoding='utf-8'))
            summary = json.loads(Path(path + '.diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['technical_valid_count'], 1)
            self.assertEqual(summary['technical_failure_count'], 0)
            self.assertEqual(summary['legacy_diagnostic_count'], 1)
            self.assertEqual(summary['components']['effectiveness.s_method']['known_count'], 1)
            self.assertIsNone(summary['formal_cce'])
            self.assertEqual(summary['formal_cce_status'], 'NOT_COMPUTED_FROM_LEGACY_PROPOSALS')
            self.assertFalse(records[0]['evaluation']['cce_eligible'])
            self.assertEqual(aggregate_items(records)['sample_count'], 0)
            await runner.evaluate_responses('single-method-smoke', [entry], self.teacher, {}, '', assessment_mode='legacy')
            self.assertEqual(self.teacher.calls, 1)

    async def test_resume_reuses_unchanged_scores_but_rejects_changed_response(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            entry = self.response()
            path = await runner.evaluate_responses('test', [entry], self.teacher, {}, '', assessment_mode='legacy')
            original = Path(path).read_bytes()
            await runner.evaluate_responses('test', [entry], self.teacher, {}, '', assessment_mode='legacy')
            self.assertEqual(self.teacher.calls, 1)
            changed = {**entry, 'model_response': entry['model_response'] + ' changed'}
            with self.assertRaisesRegex(ValueError, 'Response changed'):
                await runner.evaluate_responses('test', [changed], self.teacher, {}, '', assessment_mode='legacy')
            self.assertEqual(Path(path).read_bytes(), original)
            self.assertEqual(self.teacher.calls, 1)

    async def test_resuming_subset_preserves_other_failure_records(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            entry = self.response()
            path = await runner.evaluate_responses('test', [entry], self.teacher, {}, '', assessment_mode='legacy')
            saved = json.loads(Path(path).read_text(encoding='utf-8'))
            saved.append({'question_id': 6, 'evaluation': {'_error': 'fixture parse failure'},
                          'scoring_contract_sha256': saved[0]['scoring_contract_sha256'],
                          'response_sha256': 'other-input'})
            saved[0]['evaluation'] = {'_error': 'retry selected item'}
            Path(path).write_text(json.dumps(saved), encoding='utf-8')
            await runner.evaluate_responses('test', [entry], self.teacher, {}, '', assessment_mode='legacy')
            after = json.loads(Path(path).read_text(encoding='utf-8'))
            self.assertEqual({item['question_id'] for item in after}, {5, 6})
            self.assertEqual(next(item for item in after if item['question_id'] == 6), saved[1])

    async def test_eval_only_honors_selected_question_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_OUTPUT_DIR', tmp):
            entries = [self.response(), self.response(next(q for q in runner._QUESTION_LIST if q['question_id'] == 6))]
            Path(tmp, 'from_test_1-shot.json').write_text(json.dumps(entries), encoding='utf-8')
            summary = await runner.process_and_evaluate_model(
                'test', None, [self.question], {}, [], None, {}, '', skip_generation=True, skip_evaluation=True)
            self.assertEqual(summary['n_generated'], 1)
            self.assertIsNone(summary['error'])

    async def test_empty_actual_provider_output_is_failed_and_does_not_count_as_generated(self):
        model = FakeGenerator()
        model._acall.return_value = {"content": ""}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "OEQ_OUTPUT_DIR", tmp):
            summary = await runner.process_and_evaluate_model(
                "empty-provider", model, [self.question], {}, [], None, {}, "", skip_evaluation=True)
            rows = json.loads(Path(tmp, "from_empty-provider_1-shot.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["n_generated"], 0)
        self.assertEqual(summary["missing_or_invalid_generation_ids"], [5])
        self.assertIn("Incomplete generation", summary["error"])
        self.assertEqual(rows[0]["generation_status"], "FAILED")
        self.assertEqual(rows[0]["generation"]["failure_code"], "EMPTY_OR_INVALID_CONTENT")
        self.assertEqual(model._acall.await_count, 1)

    async def test_successful_provider_metadata_is_preserved(self):
        model = FakeGenerator()
        metadata = {"technical_status": "VALID", "finish_reason": "stop", "prompt_tokens": 12, "completion_tokens": 34}
        model._acall.return_value = {"content": self.response()["model_response"], "metadata": metadata}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "OEQ_OUTPUT_DIR", tmp):
            summary = await runner.process_and_evaluate_model(
                "valid-provider", model, [self.question], {}, [], None, {}, "", skip_evaluation=True)
            row = json.loads(Path(tmp, "from_valid-provider_1-shot.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(summary["n_generated"], 1)
        self.assertIsNone(summary["error"])
        self.assertEqual(row["generation"]["metadata"], metadata)
        self.assertEqual(row["generation_status"], "VALID")

    async def test_partial_exception_response_is_preserved_and_only_explicit_resume_retries(self):
        import contextlib
        import io
        partial = self.response()["model_response"] + "partial unfinished tail"
        class OutputError(ValueError):
            def __init__(self):
                super().__init__("Bearer test-private-credential")
                self.response_data = {"content": "", "raw_content": partial,
                    "metadata": {"technical_status": "FAILED", "finish_reason": "length"}}
        model = FakeGenerator()
        model._acall.side_effect = [OutputError(), {"content": self.response()["model_response"],
                "metadata": {"technical_status": "VALID", "finish_reason": "stop"}}]
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "OEQ_OUTPUT_DIR", tmp), contextlib.redirect_stdout(stdout):
            first = await runner.process_and_evaluate_model(
                "partial-provider", model, [self.question], {}, [], None, {}, "", skip_evaluation=True)
            failure = json.loads(Path(tmp, "from_partial-provider_1-shot.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(model._acall.await_count, 1)
            second = await runner.process_and_evaluate_model(
                "partial-provider", model, [self.question], {}, [], None, {}, "", skip_evaluation=True)
            row = json.loads(Path(tmp, "from_partial-provider_1-shot.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(first["n_generated"], 0)
        self.assertIsNotNone(first["error"])
        self.assertEqual(failure["generation"]["raw_content"], partial)
        self.assertEqual(failure["generation"]["metadata"]["finish_reason"], "length")
        self.assertEqual(second["n_generated"], 1)
        self.assertIsNone(second["error"])
        self.assertEqual(len(row["generation_attempts"]), 2)
        self.assertEqual(row["generation_attempts"][0]["raw_content"], partial)
        self.assertNotIn("test-private-credential", stdout.getvalue())
        self.assertNotIn("test-private-credential", json.dumps(row))
        self.assertEqual(model._acall.await_count, 2)

    async def test_long_content_with_failed_provider_metadata_is_not_scored(self):
        model = FakeGenerator()
        model._acall.return_value = {"content": self.response()["model_response"],
            "metadata": {"technical_status": "FAILED", "finish_reason": "length"}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "OEQ_OUTPUT_DIR", tmp), \
                patch.object(runner, "OEQ_SCORE_DIR", tmp), patch.object(runner, "evaluate_responses", AsyncMock()) as score:
            summary = await runner.process_and_evaluate_model(
                "failed-provider", model, [self.question], {}, [], self.teacher, {}, "")
            self.assertEqual(score.await_args.args[1], [])
        self.assertEqual(summary["n_generated"], 0)
        self.assertIsNotNone(summary["error"])
        self.assertEqual(self.teacher.calls, 0)

    async def test_eval_only_rejects_cached_partial_despite_nonempty_text(self):
        entry = dict(self.response(), metadata={"finish_reason": "length", "technical_status": "FAILED"})
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "OEQ_OUTPUT_DIR", tmp):
            source = Path(tmp, "from_cached-partial_1-shot.json")
            source.write_text(json.dumps([entry]), encoding="utf-8")
            original = source.read_bytes()
            summary = await runner.process_and_evaluate_model(
                "cached-partial", None, [self.question], {}, [], None, {}, "",
                skip_generation=True, skip_evaluation=True)
            self.assertEqual(source.read_bytes(), original)
        self.assertEqual(summary["n_generated"], 0)
        self.assertIsNotNone(summary["error"])

    async def test_missing_generated_question_fails_generate_only_summary(self):
        q6 = next(q for q in runner._QUESTION_LIST if q["question_id"] == 6)
        with patch.object(runner, "process_model", return_value=[self.response()]):
            summary = await runner.process_and_evaluate_model(
                "missing-question", None, [self.question, q6], {}, [], None, {}, "", skip_evaluation=True)
        self.assertEqual(summary["n_generated"], 1)
        self.assertEqual(summary["missing_or_invalid_generation_ids"], [6])
        self.assertIsNotNone(summary["error"])

    async def test_main_generate_only_returns_failure_for_actual_empty_acall(self):
        from models.Model_Loader import ModelLoader
        model = FakeGenerator()
        model.model_name = "offline-empty"
        model._acall.return_value = {"content": "", "metadata": {"finish_reason": "stop"}}
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "models.json"
            config.write_text(json.dumps({"models": [{"name": "offline-empty", "type": "Ollama", "model_name": "offline-empty"}]}), encoding="utf-8")
            responses = Path(tmp) / "responses"
            with patch.object(ModelLoader, "load_models", return_value={"offline-empty": model}), \
                    patch.object(runner, "OEQ_OUTPUT_DIR", str(responses)):
                code = await runner.main([
                    "--no-evaluation", "--model-config", str(config), "--models", "offline-empty",
                    "--question-file", OLD_QUESTIONS, "--demand-vectors", DEMANDS, "--qids", "5",
                    "--response-dir", str(responses), "--gen-concurrency", "1"])
            row = json.loads((responses / "from_offline-empty_1-shot.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(code, 1)
        self.assertEqual(row["generation_status"], "FAILED")

    async def test_generation_resume_keeps_subset_and_rejects_changed_prompt_inputs(self):
        q6 = next(q for q in runner._QUESTION_LIST if q['question_id'] == 6)
        mock_generate = AsyncMock(return_value={'content': self.response()['model_response'], 'technical_status': 'VALID', 'metadata': {}})
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_OUTPUT_DIR', tmp), \
                patch.object(runner, 'get_model_response', mock_generate):
            await runner.process_model('test', None, [self.question, q6], {}, [])
            selected = await runner.process_model('test', None, [self.question], {}, [])
            self.assertEqual([entry['question_id'] for entry in selected], [5])
            self.assertEqual(mock_generate.await_count, 2)
            with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
                await runner.process_model('test', None, [self.question], {'new': {'restriction'}}, [])
            self.assertEqual(mock_generate.await_count, 2)


if __name__ == '__main__':
    unittest.main()
