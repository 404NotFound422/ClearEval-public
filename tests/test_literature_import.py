"""Provenance and scientific-boundary regressions for the literature addition."""
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'KnowledgeBase/literature_evidence/2026-11-11'


class LiteratureImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((RELEASE / 'manifest.json').read_text(encoding='utf8'))
        cls.records = cls.manifest['records']
        cls.archive = zipfile.ZipFile(RELEASE / 'source_release.zip')

    @classmethod
    def tearDownClass(cls):
        cls.archive.close()

    def card(self, pid):
        return json.loads((ROOT / f'KnowledgeBase/article_chunk/Evidence_{pid}_result.json').read_text(encoding='utf8'))

    def test_inventory_and_source_status_are_preserved(self):
        self.assertEqual(len(self.records), 119)
        self.assertEqual(len({r['paper_id'] for r in self.records}), 119)
        self.assertEqual(len({r['doi'].lower() for r in self.records}), 119)
        self.assertEqual(sum(r['source_default_eligible'] for r in self.records), 9)
        source = {r['paper_id']: r for r in json.loads(self.archive.read('active_index.json'))['records']}
        for r in self.records:
            self.assertEqual(r['source_release_status'], source[r['paper_id']]['release_status'])
            self.assertEqual(r['selected_files'], source[r['paper_id']]['active_scientific_files'])
            self.assertEqual(r['required_supporting_files'], source[r['paper_id']]['required_supporting_files'])

    def test_every_card_has_science_and_numbered_reference_pairs(self):
        for r in self.records:
            card = self.card(r['paper_id'])
            self.assertGreater(sum(v for k, v in r['projected_sections'].items() if k != 'Note'), 0, r['paper_id'])
            for key, section in card.items():
                if isinstance(section, dict):
                    self.assertEqual(set(section), {'Text', 'Text_Reference'})
                    self.assertTrue(section['Text_Reference'])
                else:
                    for i, row in enumerate(section, 1):
                        self.assertEqual(set(row), {f'Text{i}', f'Text{i}_Reference'})
                        self.assertTrue(row[f'Text{i}'])
                        self.assertTrue(row[f'Text{i}_Reference'])

    def test_all_scientific_pointers_resolve_to_pinned_source_bytes(self):
        cache = {}
        for r in self.records:
            for binding in r['bindings']:
                name = binding['source_path']
                if name not in cache:
                    raw = self.archive.read(name)
                    cache[name] = hashlib.sha256(raw).hexdigest(), json.loads(raw)
                digest, value = cache[name]
                self.assertEqual(digest, binding['source_sha256'])
                for token in binding['json_pointer'].split('/')[1:]:
                    token = token.replace('~1', '/').replace('~0', '~')
                    value = value[int(token)] if isinstance(value, list) else value[token]

    def test_superseded_area_volume_claim_is_not_revived(self):
        card = self.card('M009')
        text = json.dumps(card, ensure_ascii=False)
        self.assertIn('C19R', text)
        self.assertNotIn('claim_status: superseded', text)
        record = next(r for r in self.records if r['paper_id'] == 'M009')
        self.assertFalse(any(b['json_pointer'] == '/claims/18' for b in record['bindings']))

    def test_current_roots_do_not_include_historical_science(self):
        forbidden = ('/historical_evidence/', '/frozen_record/', '/baseline_scientific_record/', '/frozen_candidate_scientific_record/')
        for r in self.records:
            for b in r['bindings']:
                self.assertFalse(any(t in b['json_pointer'] for t in forbidden), (r['paper_id'], b))

    def test_required_modality_correction_and_null_semantics(self):
        text = json.dumps(self.card('REV_38159104'), ensure_ascii=False)
        self.assertIn('only MPFM', text)
        self.assertIn('not_a_universal_performance_rule: true', text)
        self.assertIn('null (as recorded in source)', json.dumps(self.card('APP204')))
        self.assertNotIn('not reported (null in source)', json.dumps(self.card('APP204')))

    def test_reviewed_addendum_supersedes_frozen_duplicate(self):
        record = next(r for r in self.records if r['paper_id'] == 'M_N0050')
        self.assertFalse(any(b['source_path'].endswith('/frozen_R1_addendum_v1.json') for b in record['bindings']))
        self.assertTrue(any(b['source_path'].endswith('/canonical_addendum_reviewed.json') for b in record['bindings']))
        self.assertIn('Do not retrieve old combined statement', json.dumps(self.card('M_N0050')))


if __name__ == '__main__':
    unittest.main()
