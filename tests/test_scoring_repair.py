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
        score, detail = time_score_details(0, self.row, 'T')
        self.assertEqual(score, 0)
        self.assertEqual(detail['status'], 'missing_or_invalid_time')
        self.assertEqual(time_score_details(30, None, 'T')[1]['status'], 'missing_kb')
        self.assertEqual(time_score_details(float('nan'), self.row, 'T')[1]['status'], 'missing_or_invalid_time')

    def test_all_published_time_windows_are_accepted(self):
        for method, tiers in runner.TIME_KB_LOOKUP.items():
            for tier, row in tiers.items():
                with self.subTest(method=method, tier=tier):
                    score, detail = time_score_details(row['clearing_time_median_h'], row, tier)
                    self.assertEqual(score, 3)
                    self.assertEqual(detail['status'], 'scored')


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


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
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
        eff = result['scores']['effectiveness']
        detail = eff['s_time']['computation']
        self.assertNotIn('9999', eff['s_time']['reasoning'])
        self.assertIn(str(detail['min_hours']), eff['s_time']['reasoning'])
        self.assertEqual(result['extraction']['protocol_time_hours'], [9999, 10000])
        expected = runner.calculate_method_suitability(runner.fixed_demands().get(5, self.question['question']),
                                                       runner.find_signed_method('iDISCO+'))
        self.assertEqual(eff['s_method']['score'], expected)
        self.assertNotIn('generated_timestamp', result['meta_data'])

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

    async def test_resume_reuses_unchanged_scores_but_rejects_changed_response(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            entry = self.response()
            path = await runner.evaluate_responses('test', [entry], self.teacher, {}, '')
            original = Path(path).read_bytes()
            await runner.evaluate_responses('test', [entry], self.teacher, {}, '')
            self.assertEqual(self.teacher.calls, 1)
            changed = {**entry, 'model_response': entry['model_response'] + ' changed'}
            with self.assertRaisesRegex(ValueError, 'Response changed'):
                await runner.evaluate_responses('test', [changed], self.teacher, {}, '')
            self.assertEqual(Path(path).read_bytes(), original)
            self.assertEqual(self.teacher.calls, 1)

    async def test_resuming_subset_preserves_other_failure_records(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            entry = self.response()
            path = await runner.evaluate_responses('test', [entry], self.teacher, {}, '')
            saved = json.loads(Path(path).read_text(encoding='utf-8'))
            saved.append({'question_id': 6, 'evaluation': {'_error': 'fixture parse failure'},
                          'scoring_contract_sha256': saved[0]['scoring_contract_sha256'],
                          'response_sha256': 'other-input'})
            saved[0]['evaluation'] = {'_error': 'retry selected item'}
            Path(path).write_text(json.dumps(saved), encoding='utf-8')
            await runner.evaluate_responses('test', [entry], self.teacher, {}, '')
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

    async def test_generation_resume_keeps_subset_and_rejects_changed_prompt_inputs(self):
        q6 = next(q for q in runner._QUESTION_LIST if q['question_id'] == 6)
        mock_generate = AsyncMock(return_value=self.response()['model_response'])
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
