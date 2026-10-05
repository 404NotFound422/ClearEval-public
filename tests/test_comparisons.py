"""Controlled comparison tests operate on new synthetic frozen attempts only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.construct_validity.comparisons import (
    compare_adjudicated_candidates, freeze_judge_comparison, same_information_guards)
from experiments.construct_validity.contract import digest, read, save
from experiments.construct_validity.local_runner import verify_manifest
from tests.test_analysis_identity import REPO, build_study


def context(status='SATISFIED'):
    return {'protocol': 'Preserve DiI in one fictional method.',
            'requirements': [{'id': 'R', 'text': 'The text preserves DiI.', 'kind': 'TEXT',
                              'necessary': True, 'scope': 'GLOBAL', 'evidence_ids': []}],
            'cards': [],
            'judgment': {'requirements': [{'id': 'R', 'status': status, 'basis': 'PROTOCOL_TEXT',
                                          'evidence_ids': [], 'quotes': ['Preserve DiI'],
                                          'reason': 'Synthetic text-state input'}],
                         'limitations': 'Not a scientific label'}}


def candidate(name, status='SATISFIED'):
    return {'id': name, 'task_id': 'SYN-PAIR', 'scenario': {'tissue': 'synthetic', 'scale': 'fixture'},
            'constraints': {'admissibility': 'SATISFIED'},
            'objectives': {'time': {'min': 1, 'max': 1, 'unit': 'h', 'direction': 'min'}},
            'evaluation_context': context(status)}


class DeterministicComparisonTests(unittest.TestCase):
    def test_guard_ablation_has_identical_actual_public_information(self):
        result = same_information_guards(context())
        self.assertTrue(result['same_actual_information'])
        self.assertEqual(len({m['visible_bundle_sha256'] for m in result['mechanisms']}), 1)
        self.assertEqual([m['observed']['overall'] for m in result['mechanisms']],
                         ['SATISFIED', 'SATISFIED'])
        self.assertIsNone(result['scientific_accuracy'])

    def test_private_gold_cannot_enter_adapter_input(self):
        value = context()
        value['expert_labels'] = {'R': 'SATISFIED'}
        with self.assertRaisesRegex(ValueError, 'Private reference'):
            same_information_guards(value)

    def test_supplied_feasibility_is_recomputed_from_requirements(self):
        a, b = candidate('A', 'VIOLATED'), candidate('B')
        # A's supplied SATISFIED cannot override its newly computed violation.
        result = compare_adjudicated_candidates(a, b)
        self.assertEqual(result['relationship'], 'B_ONLY_FEASIBLE')
        self.assertEqual(result['feasibility']['A'], 'VIOLATED')
        self.assertEqual(result['feasibility_audits'][0]['constraint_source'], 'RECOMPUTED_REQUIREMENTS')

    def test_different_requirement_contract_is_not_comparable(self):
        a, b = candidate('A'), candidate('B')
        b['evaluation_context']['requirements'][0]['text'] = 'A different task contract.'
        result = compare_adjudicated_candidates(a, b)
        self.assertEqual(result['relationship'], 'NOT_COMPARABLE')


class FrozenComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='comparison-test-', dir=REPO)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(REPO.resolve()))
        self.addCleanup(self.cleanup)
        self.manifest, self.jobs = build_study(self.root)
        self.judges = [
            {'id': 'A', 'model': 'fixture-A', 'revision': 'a' * 64, 'family': 'family-A'},
            {'id': 'B', 'model': 'fixture-B', 'revision': 'b' * 64, 'family': 'family-B'}]

    def cleanup(self):
        assert Path(self.temp.name).resolve().is_relative_to(REPO.resolve())
        self.temp.cleanup()

    def test_freeze_realized_answers_without_model_calls(self):
        result = freeze_judge_comparison(self.root, self.judges, self.root / 'comparison', repeats=2)
        self.assertEqual(result['model_calls_performed'], 0)
        self.assertFalse(result['scientific_comparison_performed'])
        self.assertEqual(result['planned_calls'], 4)
        self.assertTrue(result['information_checks'][0]['controlled_comparison_ready'])
        for plan in result['plans']:
            manifest = verify_manifest(Path(plan['path']))
            self.assertEqual(manifest['manifest_sha256'], plan['manifest_sha256'])
            self.assertEqual(len(read(Path(plan['path']) / 'jobs.json')), 2)
            material = read(Path(plan['path']) / 'materials.json')['M']
            self.assertNotIn('generation_job', material)
            self.assertIn('single clearing method', material['protocol'])

    def test_freeze_cannot_use_generated_answer_after_raw_chunks_removed(self):
        (self.root / 'attempts' / 'G' / 'a01' / 'chunks.jsonl').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            freeze_judge_comparison(self.root, self.judges, self.root / 'comparison', repeats=2)

    def test_freeze_cannot_accept_rehashed_generated_content(self):
        folder = self.root / 'attempts' / 'G' / 'a01'
        path = folder / 'content.txt'
        altered = path.read_text(encoding='utf-8') + ' Changed source answer.'
        path.write_text(altered, encoding='utf-8')
        result = read(folder / 'result.json')
        result['content_sha256'] = digest(altered)
        save(folder / 'result.json', result, immutable=False)
        with self.assertRaisesRegex(ValueError, 'transport'):
            freeze_judge_comparison(self.root, self.judges, self.root / 'comparison', repeats=2)


if __name__ == '__main__':
    unittest.main()
