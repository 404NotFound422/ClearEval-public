"""Synthetic fixtures test collection/analysis; they are never research results."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from experiments import judge_reliability as pilot
from evaluation_contract import json_hash
import OEQ_run_grading_new as scorer


class PrepareAndImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.study = Path(cls.temp.name) / 'study'
        with redirect_stdout(io.StringIO()):
            cls.plan = pilot.prepare(cls.study)
        cls.items = pilot.read_json(cls.study / 'private/items.json')
        cls.key = pilot.read_json(cls.study / 'private/blinding_key.json')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_sample_has_matched_conditions_and_balanced_models(self):
        self.assertEqual(len({item['question_id'] for item in self.items}), 12)
        self.assertEqual(len({item['tissue_tier'] for item in self.items}), 12)
        self.assertEqual(pilot.Counter(item['model'] for item in self.items), {model: 12 for model in pilot.MODELS})
        groups = pilot.defaultdict(list)
        for item in self.items:
            groups[item['question_id'], item['model']].append(item['setting'])
        self.assertTrue(all(set(settings) == set(pilot.SETTINGS) for settings in groups.values()))

    def test_reviewer_packet_preserves_text_without_source_metadata(self):
        by_id = {item['item_id']: item for item in self.items}
        for reviewer in ('A', 'B'):
            data = pilot.read_json(self.study / f'reviewer_{reviewer}/cases.json')
            self.assertEqual(len(data['cases']), 40)
            mapping = {row['blind_id']: row for row in self.key if row['reviewer_id'] == reviewer}
            for case in data['cases']:
                self.assertEqual(set(case), {'blind_id', 'question', 'protocol', 'restrictions'})
                original = by_id[mapping[case['blind_id']]['item_id']]
                self.assertEqual(json_hash(case['protocol']), original['protocol_sha256'])
            groups = pilot.defaultdict(list)
            for row in mapping.values():
                groups[row['item_id']].append(row['position'])
            repeated = [positions for positions in groups.values() if len(positions) > 1]
            self.assertEqual(len(repeated), 4)
            self.assertTrue(all(abs(a - b) >= 10 for a, b in repeated))
            html = (self.study / f'reviewer_{reviewer}/index.html').read_text(encoding='utf-8')
            embedded = html.split('<script id="data" type="application/json">')[1].split('</script>')[0]
            self.assertEqual(json.loads(embedded), data)

    def test_preparation_is_reproducible_and_refuses_another_sample(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(pilot.prepare(self.study), self.plan)
            with self.assertRaisesRegex(ValueError, 'differs'):
                pilot.prepare(self.study, seed=20260922)

    def test_no_collected_data_does_not_become_zero_score_evidence(self):
        with redirect_stdout(io.StringIO()):
            summary = pilot.analyze(self.study)
        self.assertEqual(summary['judge_attempts'], 0)
        self.assertEqual(summary['human_common_unique_protocols'], 0)
        self.assertIsNone(summary['pooled_within_protocol_sd_I_A_points'])
        self.assertIsNone(summary['human_quadratic_weighted_kappa_0_4'])
        self.assertIsNone(summary['condition_contrasts'][0]['mean_delta_points'])

    def test_blank_rating_template_remains_incomplete(self):
        ratings, audit = pilot.read_ratings([self.study / 'reviewer_A/ratings_template.csv'], self.plan, self.key)
        self.assertFalse(ratings)
        self.assertEqual(pilot.Counter(row['status'] for row in audit), {'incomplete': 40})

    def test_changed_frozen_protocol_and_schedule_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            study = Path(tmp)
            pilot.prepare(study)
            plan, items, schedule = pilot.load_validated_study(study)
            path = study / 'private/items.json'
            originals = path.read_bytes()
            changed = list(items.values())
            changed[0]['protocol'] += ' changed'
            changed[0]['protocol_sha256'] = json_hash(changed[0]['protocol'])
            pilot.write_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'Frozen protocol changed'):
                pilot.load_validated_study(study)
            path.write_bytes(originals)
            pilot.write_json(study / 'private/call_schedule.json', schedule[1:] + schedule[:1])
            with self.assertRaisesRegex(ValueError, 'schedule changed'):
                pilot.load_validated_study(study)

    def test_rating_import_rejects_unknown_and_duplicate_assignments(self):
        template = self.study / 'reviewer_A/ratings_template.csv'
        with self.assertRaisesRegex(ValueError, 'Duplicate imported'):
            pilot.read_ratings([template, template], self.plan, self.key)
        path = self.study / 'invalid_ratings.json'
        pilot.write_json(path, {'package_id': self.plan['package_id'], 'ratings': [
            {'package_id': 'another package', 'reviewer_id': 'A', 'blind_id': 'unknown'}]})
        with self.assertRaisesRegex(ValueError, 'Unknown/mismatched'):
            pilot.read_ratings([path], self.plan, self.key)

    def test_human_duplicates_are_not_extra_primary_observations(self):
        path = self.study / 'synthetic_ratings.json'
        rows = [{'package_id': self.plan['package_id'], 'reviewer_id': row['reviewer_id'],
                 'blind_id': row['blind_id'], 'overall_feasibility': str(int(row['item_id'][1:]) % 5),
                 'rationale': 'Synthetic test fixture, not an expert assessment.'} for row in self.key]
        pilot.write_json(path, {'package_id': self.plan['package_id'], 'ratings': rows})
        with redirect_stdout(io.StringIO()):
            result = pilot.analyze(self.study, rating_paths=[path])
        self.assertEqual(result['human_common_unique_protocols'], 36)
        self.assertEqual(result['human_quadratic_weighted_kappa_0_4'], 1)
        self.assertEqual([entry['n_pairs'] for entry in result['human_duplicate_consistency']], [4, 4])
        self.assertEqual(result['human_condition_contrasts'][0]['n_human_scenario_pairs'], 12)


class StatisticsTests(unittest.TestCase):
    def test_rank_correlation_handles_ties_and_constants(self):
        self.assertEqual(pilot.rank([1, 1, 4]), [1.5, 1.5, 3])
        self.assertAlmostEqual(pilot.spearman([1, 2, 3], [3, 2, 1]), -1)
        self.assertIsNone(pilot.spearman([1, 1, 1], [2, 3, 4]))

    def test_weighted_kappa_and_bootstrap(self):
        self.assertEqual(pilot.quadratic_kappa([0, 1, 2, 3, 4], [0, 1, 2, 3, 4]), 1)
        self.assertLess(pilot.quadratic_kappa([0, 1, 2, 3, 4], [4, 3, 2, 1, 0]), 0)
        self.assertIsNone(pilot.quadratic_kappa([2, 2], [2, 2]))
        self.assertEqual(pilot.bootstrap_mean_ci([2, 2, 2]), [2, 2])


class FixtureJudge:
    calls = 0

    def __init__(self, config):
        self.model_name = config['model']
        self.last_response = None
        self.last_error = None

    async def _acall(self, prompt):
        type(self).calls += 1
        self.last_response = {'model': self.model_name, 'usage': {'total_tokens': 0}}
        scores = {'completeness': {'c_step': {'score': 2}, 'c_param': {'score': 3}},
                  'correctness': {key: {'score': value} for key, value in
                                  [('co_order', 3), ('co_method', 2), ('co_param', 2), ('co_chem', 1)]}}
        return {'content': json.dumps({'scores': scores, 'extraction': {
            'method_name': 'CUBIC', 'clearing_total_time_hours': 96, 'marker_dict': {'GFP': 'GFP'}}})}


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_canary_and_resume_preserve_all_independent_replicates(self):
        original_questions, original_score_dir = scorer.QUESTION_FILE, scorer.OEQ_SCORE_DIR
        FixtureJudge.calls = 0
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(pilot, 'APIJudge', FixtureJudge), \
                    patch.object(scorer, '_log_teacher_response'), redirect_stdout(io.StringIO()):
                study, run = Path(tmp) / 'study', Path(tmp) / 'run'
                pilot.prepare(study)
                config = {'model': 'synthetic-test-only', 'concurrency': 3}
                self.assertEqual(await pilot.run_judge(study, run, config, max_calls=1), 0)
                self.assertEqual(FixtureJudge.calls, 1)
                self.assertEqual(await pilot.run_judge(study, run, config), 0)
                self.assertEqual(FixtureJudge.calls, 108)
                self.assertEqual(await pilot.run_judge(study, run, config), 0)
                self.assertEqual(FixtureJudge.calls, 108)
                summary = pilot.analyze(study, run)
                self.assertEqual(summary['judge_protocols_with_all_3_repeats'], 36)
                self.assertEqual(summary['pooled_within_protocol_sd_I_A_points'], 0)
                # A copied result must not count as another independent observation.
                first = next(run.glob('repeat_*/*.json'))
                copied = first.with_name('unexpected.json')
                copied.write_bytes(first.read_bytes())
                with self.assertRaisesRegex(ValueError, 'path/identity mismatch'):
                    pilot.analyze(study, run)
                copied.unlink()
                failed = pilot.read_json(first)
                failed['evaluation'] = {'_error': 'synthetic failure'}
                pilot.write_json(first, failed)
                self.assertEqual(await pilot.run_judge(study, run, config), 2)
                self.assertEqual(FixtureJudge.calls, 108)
        finally:
            scorer.configure_question_snapshot(original_questions)
            scorer.OEQ_SCORE_DIR = original_score_dir

    def test_api_client_rejects_credentials_in_endpoint(self):
        with patch.dict(os.environ, {'TEST_PILOT_API_KEY': 'synthetic-test-only'}):
            with self.assertRaisesRegex(ValueError, 'without embedded credentials'):
                pilot.APIJudge({'model': 'fixture', 'base_url': 'https://secret@example.com/v1', 'api_key_env': 'TEST_PILOT_API_KEY'})

    def test_api_failures_are_sanitized_and_reasoning_temperature_can_be_omitted(self):
        config = {'model': 'fixture', 'base_url': 'https://example.com/v1', 'api_key_env': 'TEST_PILOT_API_KEY',
                  'temperature': None, 'reasoning_effort': 'high', 'token_parameter': 'max_completion_tokens',
                  'max_output_tokens': 1000, 'timeout_seconds': 5}
        with patch.dict(os.environ, {'TEST_PILOT_API_KEY': 'synthetic-secret'}), \
                patch.object(pilot.urllib.request, 'build_opener') as opener:
            for body, kind in [(b'not json', 'invalid_api_json'),
                               (b'{"model":"fixture","choices":[{"finish_reason":"length"}]}', 'output_truncated'),
                               (b'{"model":"fixture","choices":[{"finish_reason":"content_filter"}]}', 'incomplete_api_response')]:
                opener.return_value.open.return_value = io.BytesIO(body)
                judge = pilot.APIJudge(config)
                with self.subTest(kind=kind), self.assertRaises(pilot.SafeAPIError):
                    judge.request('synthetic prompt')
                self.assertEqual(judge.last_error.kind, kind)
                request = opener.return_value.open.call_args.args[0]
                self.assertNotIn('temperature', json.loads(request.data))
            opener.return_value.open.side_effect = urllib.error.HTTPError(
                'https://example.com', 401, 'synthetic-secret', {}, io.BytesIO(b'synthetic-secret'))
            judge = pilot.APIJudge(config)
            with self.assertRaises(pilot.SafeAPIError) as caught:
                judge.request('synthetic prompt')
            self.assertNotIn('synthetic-secret', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
