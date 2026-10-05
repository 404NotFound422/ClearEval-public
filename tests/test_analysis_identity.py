"""Frozen synthetic E2E attempts: no model/network/expert annotation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.construct_validity.analysis import checked_attempt, summarize
from experiments.construct_validity.contract import digest, file_hash, read, save
from experiments.construct_validity.local_runner import run_job, verify_manifest
from experiments.construct_validity.fidelity import SCHEMA as EXTRACTION_SCHEMA

REPO = Path(__file__).resolve().parents[1]
MODULES = REPO / 'experiments' / 'construct_validity'
PROTOCOL = ('Use SYN-ALPHA as the single clearing method. Wash, label, clear, match, image and store '
            'with declared fictional materials. Preserve DiI. Physical performance remains unverified.')


class FakeResponse:
    def __init__(self, content, model):
        self.chunks = [json.dumps({'message': {'content': content}, 'done': True,
            'model': model, 'done_reason': 'stop', 'prompt_eval_count': 5,
            'eval_count': 3}).encode('utf-8') + b'\n']
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def __iter__(self):
        return iter(self.chunks)


def build_study(root):
    req = {'id': 'R', 'text': 'The single-method text states Preserve DiI.',
           'kind': 'TEXT', 'necessary': True, 'scope': 'GLOBAL', 'evidence_ids': []}
    material = {'root_task_id': 'SYN-T', 'kind': 'SYNTHETIC_ENGINEERING_ONLY',
                'question': 'Provide one fictional clearing method with DiI retained.',
                'protocol': PROTOCOL, 'generation_job': 'G',
                'resource_list': {}, 'requirements': [req], 'cards': []}
    generation_material = deepcopy(material)
    generation_material.pop('generation_job')
    jobs = [{'id': key, 'material_id': 'MG' if phase == 'generate' else 'M', 'phase': phase} for key, phase in
            [('G', 'generate'), ('E', 'extract'), ('J1', 'judge'), ('J2', 'judge')]]
    save(root / 'materials.json', {'MG': generation_material, 'M': material})
    save(root / 'jobs.json', jobs)
    (root / 'judge_prompt.txt').write_text('Synthetic judge contract; no science labels.', encoding='utf-8')
    (root / 'extract_prompt.txt').write_text('Synthetic exact-field extraction.', encoding='utf-8')
    (root / 'code').mkdir()
    for path in MODULES.glob('*.py'):
        (root / 'code' / path.name).write_bytes(path.read_bytes())
    manifest = {'version': 'SYNTHETIC-TEST', 'model': 'fixture-model', 'model_digest': 'a' * 64,
                'model_family': 'fixture-family', 'provider': 'offline-test',
                'origin': 'http://127.0.0.1:11434', 'options': {'temperature': 0},
                'phase_options': {'generate': {}, 'extract': {}, 'judge': {}},
                'read_timeout_seconds': 1, 'wall_limit_seconds': 30, 'max_calls': len(jobs),
                'files': {p.relative_to(root).as_posix(): file_hash(p)
                          for p in sorted(root.rglob('*')) if p.is_file()}}
    manifest['manifest_sha256'] = digest(manifest)
    save(root / 'manifest.json', manifest)
    verify_manifest(root)
    start = PROTOCOL.index('DiI')
    support = {'kind': 'EXPLICIT', 'raw_value': 'DiI', 'transform': 'IDENTITY',
               'spans': [{'start': start, 'end': start + 3, 'quote': 'DiI'}]}
    missing = {'kind': 'MISSING', 'raw_value': None, 'spans': []}
    extraction = {'schema_version': EXTRACTION_SCHEMA,
                  'branches': [{'id': 'main', 'mode': 'SERIAL', 'sample_id': 'fixture', 'spans': []}],
                  'labels': [{'id': 'L', 'branch': 'main', 'target': None, 'probe': 'DiI',
                              'fluorophore': None, 'channel': None, 'quote': 'Preserve DiI',
                              'assertion': {'polarity': 'AFFIRMED'},
                              'field_support': {'target': missing, 'probe': support,
                                                'fluorophore': missing, 'channel': missing}}],
                  'steps': [], 'ri': [], 'limitations': 'SYNTHETIC ONLY'}
    judgment = {'requirements': [{'id': 'R', 'status': 'SATISFIED', 'basis': 'PROTOCOL_TEXT',
                                 'evidence_ids': [], 'quotes': ['Preserve DiI'], 'reason': 'Synthetic text only'}],
                'limitations': 'No scientific label'}
    for job in jobs:
        content = (PROTOCOL if job['phase'] == 'generate' else
                   json.dumps(extraction if job['phase'] == 'extract' else judgment))
        result = run_job(root, manifest, job,
                         transport=lambda request, text=content: FakeResponse(text, manifest['model']))
        if result['status'] != 'COMPLETE':
            raise AssertionError(result)
    return manifest, jobs


class AnalysisIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='analysis-test-', dir=REPO)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(REPO.resolve()))
        self.addCleanup(self.cleanup)
        self.manifest, self.jobs = build_study(self.root)
        self.job = self.jobs[2]
        self.attempt = self.root / 'attempts' / self.job['id'] / 'a01'

    def cleanup(self):
        # Confirm the absolute recursive cleanup target remains in the workspace.
        assert Path(self.temp.name).resolve().is_relative_to(REPO.resolve())
        self.temp.cleanup()

    def test_normal_e2e_uses_frozen_inputs_and_mock_is_not_model_stability(self):
        summary = summarize(self.root)
        self.assertEqual(summary['statuses'], {'COMPLETE': 4})
        self.assertEqual(summary['new_generations_complete'], 1)
        self.assertEqual(summary['extractions_scoring_eligible'], 1)
        self.assertEqual(summary['valid_judgments'], 2)
        self.assertIsNone(summary['scientific_accuracy'])
        repeats = read(self.root / 'analysis' / 'repeat_results.json')
        self.assertEqual(repeats[0]['repetition_status'], 'NOT_ESTIMABLE')
        self.assertEqual(repeats[0]['independent_live_complete'], 0)

    def test_missing_raw_chunks_cannot_leave_completion_certified(self):
        (self.attempt / 'chunks.jsonl').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            checked_attempt(self.root, self.manifest, self.job)

    def test_missing_parsed_output_is_rejected(self):
        (self.attempt / 'parsed.json').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            checked_attempt(self.root, self.manifest, self.job)

    def test_content_self_hash_cannot_replace_transport_record(self):
        path = self.attempt / 'content.txt'
        altered = path.read_text(encoding='utf-8') + ' '
        path.write_text(altered, encoding='utf-8')
        result = read(self.attempt / 'result.json')
        result['content_sha256'] = digest(altered)
        save(self.attempt / 'result.json', result, immutable=False)
        with self.assertRaisesRegex(ValueError, 'transport'):
            checked_attempt(self.root, self.manifest, self.job)

    def test_rehashed_request_cannot_change_actual_frozen_information(self):
        request = read(self.attempt / 'request.json')
        request['payload']['messages'][-1]['content'] += ' changed task'
        request['payload_sha256'] = digest(request['payload'])
        save(self.attempt / 'request.json', request, immutable=False)
        result = read(self.attempt / 'result.json')
        result['payload_sha256'] = request['payload_sha256']
        save(self.attempt / 'result.json', result, immutable=False)
        with self.assertRaisesRegex(ValueError, 'reconstructed actual input'):
            checked_attempt(self.root, self.manifest, self.job)

    def test_invocation_must_match_started_attempt(self):
        result = read(self.attempt / 'result.json')
        result['invocation_id'] = 'different-invocation'
        save(self.attempt / 'result.json', result, immutable=False)
        with self.assertRaisesRegex(ValueError, 'Started attempt identity'):
            checked_attempt(self.root, self.manifest, self.job)


if __name__ == '__main__':
    unittest.main()