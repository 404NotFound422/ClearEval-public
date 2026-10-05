"""Process/record regressions with synthetic transport; no model calls or science oracle."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from .analysis import analyze
from .execution import attempt_records, run
from .io import ledger, read
from .metrics import group_metrics
from .prepare import load_cases, prepare, verify

HERE = Path(__file__).resolve().parent
PROTOCOL = 'Use one fictional SYN-ALPHA method. Preserve DiI.'
PUBLIC = {'protocol': PROTOCOL, 'requirements': [
    {'id': 'R1', 'text': 'The text states Preserve DiI.', 'kind': 'TEXT',
     'necessary': True, 'scope': 'GLOBAL', 'evidence_ids': []}], 'source_cards': []}
JUDGES = [{'id': 'Q', 'role': 'TEACHER', 'transport': 'OLLAMA_LOOPBACK',
    'model': 'fixture-only', 'family': 'fixture-family', 'revision': 'a' * 64,
    'params': {'temperature': 0, 'seed': 42, 'num_ctx': 8192, 'num_predict': 4096}}]
JUDGMENT = {'requirements': [{'id': 'R1', 'status': 'SATISFIED',
    'basis': 'PROTOCOL_TEXT', 'evidence_ids': [], 'quotes': ['Preserve DiI'],
    'reason': 'Synthetic software fixture only'}], 'limitations': 'No scientific label'}


def render_fixture(public):
    return 'Synthetic local prompt builder: ' + json.dumps(public, sort_keys=True)


def reject_grounding_fixture(public, parsed):
    raise ValueError('Synthetic bound-field-scope failure')


def response(payload, *, done=True):
    return json.dumps({'model': payload['model'], 'done': done,
        'done_reason': 'stop' if done else 'length',
        'response': json.dumps(JUDGMENT)}).encode('utf-8')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-test-', dir=HERE)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(HERE))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        assert Path(self.temp.name).resolve().is_relative_to(HERE)
        self.temp.cleanup()

    def plan(self, **changes):
        return prepare(self.root, cases=[{'id': 'C1', 'task_id': 'T1',
            'input': deepcopy(PUBLIC), 'input_sha256': __import__('experiments.evaluator_development_v2.io',
                fromlist=['digest']).digest(PUBLIC)}], judges=deepcopy(JUDGES),
            prompt='Synthetic teacher contract. Return a requirement JSON object.',
            label='synthetic-process-test', **changes)

    def test_terminal_length_nonterminal_and_unknown_reason_are_not_transport_failure(self):
        cases = [(True, 'length', 'OUTPUT_BUDGET_EXHAUSTED'),
                 (False, 'length', 'GENERATION_NON_TERMINAL'),
                 (True, None, 'UNSUPPORTED_COMPLETION_REASON'),
                 (True, 'cancelled', 'UNSUPPORTED_COMPLETION_REASON')]
        for cumulative_budget, (done, reason, code) in enumerate(cases, 1):
            with self.subTest(done=done, reason=reason):
                folder = self.plan()
                def incomplete(payload):
                    return json.dumps({'model':payload['model'], 'done':done,
                        'done_reason':reason,'response':json.dumps(JUDGMENT),'eval_count':8192,
                        'prompt_eval_count':6012}).encode('utf-8')
                run(folder, max_calls=cumulative_budget, acknowledge_failures=True, transport=incomplete)
                _, rows = attempt_records(folder)
                row = rows[0]
                self.assertEqual(row['technical_status'], 'FAILED')
                self.assertEqual(row['technical_stage'], 'GENERATION_COMPLETION')
                self.assertEqual(row['failure']['code'], code)
                self.assertEqual(row['generation_metadata']['done_reason'], reason)
                self.assertEqual(row['proposed_vector'], {})
                self.assertEqual(row['effective_vector'], {})
                self.assertEqual(row['parsed_judge_vector_status'], 'NOT_ASSESSED')
                self.assertTrue(row['response_sha256'])
                self.assertEqual(analyze(folder)['recorded_attempts'], 1)

    def test_failure_stays_in_ledger_and_resume_does_not_erase_or_redispatch(self):
        folder = self.plan()
        calls = []
        def broken(payload):
            calls.append(payload)
            return b'not JSON'
        first = run(folder, max_calls=1, transport=broken)
        self.assertEqual(first['model_calls_dispatched'], 0)
        events, initial = attempt_records(folder)
        self.assertEqual(initial[0]['technical_status'], 'FAILED')
        self.assertEqual(len(calls), 1)
        blocked = run(folder, max_calls=4, transport=lambda p: response(p))
        self.assertEqual(blocked['status'], 'FAILURE_REQUIRES_DIAGNOSIS')
        run(folder, max_calls=4, acknowledge_failures=True, retry_failed=True,
            transport=lambda p: response(p))
        _, records = attempt_records(folder)
        self.assertEqual(len(records), 4)
        self.assertEqual(sum(r['technical_status'] == 'FAILED' for r in records), 1)
        self.assertEqual(records[0], initial[0])
        summary = analyze(folder)
        self.assertEqual(summary['planned_trials'], 3)
        self.assertEqual(summary['groups'][0]['independent_complete'], 0)
        self.assertFalse(summary['groups'][0]['minimum_three_independent_complete'])

    def test_grounding_failure_retains_raw_model_vector_but_not_effective_credit(self):
        folder = self.plan(processors=[{'id': 'guard', 'entrypoint':
            'experiments.evaluator_development_v2.test_runner:reject_grounding_fixture'}])
        run(folder, max_calls=1, transport=lambda p: response(p))
        _, records = attempt_records(folder)
        row = records[0]
        self.assertEqual(row['technical_status'], 'FAILED')
        self.assertEqual(row['technical_stage'], 'GROUNDING_VALIDATION')
        self.assertEqual(row['parsed_judge_vector_status'], 'COMPLETE')
        self.assertEqual(row['proposed_vector'], {'R1': 'SATISFIED'})
        self.assertEqual(row['effective_vector'], {})
        self.assertTrue(row['parsed_sha256'])
        self.assertEqual(analyze(folder)['recorded_attempts'], 1)
        target = folder / 'attempts' / row['id'] / row['attempt_id']
        (target / 'response.json').unlink()
        with self.assertRaises((FileNotFoundError, ValueError)):
            analyze(folder)

    def test_failed_actual_proposal_metrics_remain_separate_from_effective_coverage(self):
        rows = [{'id': 'one-trial', 'origin': 'EXTERNAL_ACTUAL',
                 'technical_status': 'FAILED', 'parsed_judge_vector_status': 'COMPLETE',
                 'proposed_vector': {'R1': 'SATISFIED'}, 'effective_vector': {},
                 'structure_vector': {}, 'invocation_id': 'one', 'actual_revision': 'UNKNOWN'}]
        observed = group_metrics(rows, ['R1'], planned=3)
        self.assertEqual(observed['independent_complete'], 0)
        self.assertEqual(observed['technical_coverage'], 0)
        self.assertEqual(observed['independent_parsed_judge_vectors'], 1)
        self.assertAlmostEqual(observed['parsed_judge_vector_coverage'], 1/3)
        self.assertEqual(observed['proposed'][0]['observed_count'], 1)
        self.assertEqual(observed['effective'][0]['observed_count'], 0)
        rows.append({**rows[0], 'invocation_id': 'two'})
        retry = group_metrics(rows, ['R1'], planned=3)
        self.assertEqual(retry['parsed_judge_vector_attempts'], 2)
        self.assertEqual(retry['independent_parsed_judge_vectors'], 1)
        self.assertAlmostEqual(retry['parsed_judge_vector_coverage'], 1/3)

    def test_budget_ceiling_is_study_wide_across_new_rounds(self):
        calls = []
        def observed(payload):
            calls.append(payload)
            return response(payload)
        first = self.plan()
        run(first, max_calls=1, transport=observed)
        second = self.plan()
        run(second, max_calls=1, transport=observed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(attempt_records(second)[1], [])

    def test_server_prompt_builder_freezes_actual_bytes_and_source(self):
        folder = self.plan(prompt_builder='experiments.evaluator_development_v2.test_runner:render_fixture')
        self.assertEqual((folder / 'prompts/C1.txt').read_bytes().decode('utf-8'), render_fixture(PUBLIC))
        self.assertEqual(verify(folder)['prompt_builder'], 'experiments.evaluator_development_v2.test_runner:render_fixture')

    def test_default_run_cannot_send_a_model_request(self):
        with self.assertRaisesRegex(ValueError, 'explicit caller authorization'):
            run(self.plan(), max_calls=6)

    def test_terminal_length_response_is_failed_and_retained(self):
        folder = self.plan()
        run(folder, max_calls=1, transport=lambda p: response(p, done=False))
        _, records = attempt_records(folder)
        self.assertEqual(records[0]['technical_status'], 'FAILED')
        self.assertIn('terminal stop', records[0]['failure']['message'])

    def test_frozen_input_change_requires_a_new_round(self):
        folder = self.plan()
        path = folder / 'prompts/C1.txt'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'new round'):
            verify(folder)

    def test_removed_raw_or_parsed_artifacts_cannot_leave_completion_verified(self):
        folder = self.plan()
        run(folder, max_calls=1, transport=lambda p: response(p))
        _, records = attempt_records(folder)
        target = folder / 'attempts' / records[0]['id'] / records[0]['attempt_id']
        (target / 'parsed.json').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            analyze(folder)

    def test_eighth_round_limit_is_actual_registry_count(self):
        for _ in range(8):
            self.plan()
        with self.assertRaisesRegex(ValueError, 'Eight-round'):
            self.plan()
        self.assertEqual(len(ledger(self.root / 'rounds.jsonl')), 8)

    def test_unknown_vectors_have_zero_decisive_coverage_and_undefined_risk(self):
        records = [{'origin': 'OLLAMA_ACTUAL', 'technical_status': 'COMPLETE',
            'proposed_vector': {'R1': 'UNRESOLVED'}, 'effective_vector': {'R1': 'UNRESOLVED'},
            'invocation_id': f'synthetic-{i}', 'actual_revision': 'UNKNOWN'} for i in range(3)]
        observed = group_metrics(records, ['R1'], planned=3)
        self.assertEqual(observed['effective'][0]['decisive_coverage'], 0)
        self.assertIsNone(observed['effective'][0]['independent_error_risk'])
        self.assertIsNone(observed['effective'][0]['decisive_entropy_bits'])
        self.assertFalse(observed['version_stability_verifiable'])

    def test_public_field_extraction_input_keeps_original_hash_and_no_fake_requirement(self):
        from .io import digest
        public = {'protocol': 'Synthetic publication body.', 'requested_fields': ['temperature_C']}
        path = self.root / 'cases.json'
        path.write_text(json.dumps([{'id': 'F1', 'input': public, 'input_sha256': digest(public),
            'label_key': 'private-not-visible'}]), encoding='utf-8')
        cases = load_cases(path=path)
        self.assertEqual(cases[0]['input'], public)
        self.assertNotIn('label_key', cases[0])
        self.assertNotIn('requirements', cases[0]['input'])


if __name__ == '__main__':
    unittest.main()
