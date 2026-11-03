"""Portable main-entry and published-score integration checks."""
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cleareval_complete_scoring as scorer
from results.oeq_metrics import protocol_scores


class ReleaseTests(unittest.TestCase):
    def test_shared_main_aggregation_covers_every_answer(self):
        result=scorer.DEFAULT_OUTPUT
        scores={r['id']:r for r in scorer.read(result/'scores185.json.gz')}
        evaluations=scorer.read(result/'evaluations185.json.gz')
        self.assertEqual(len(evaluations),185)
        for item in evaluations:
            actual=protocol_scores(item); expected=scores[item['case_id']]['metrics']
            for key,alias in [('Com','Com'),('Co','Cor'),('Eff','Eff'),('IA','I_A')]:
                self.assertAlmostEqual(actual[alias],expected[key]['value'],places=12)
        table=scorer.read(result/'main_table.json')
        self.assertEqual(len(table),19)
        self.assertEqual(sum(r['sample_count'] for r in table),185)

    def test_default_entry_from_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'results'
            run=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'OEQ_run_grading_new.py'),
                                '--cached-checks','--output',str(output)],cwd=directory,
                               capture_output=True,text=True,encoding='utf8')
            self.assertEqual(run.returncode,0,run.stderr)
            expected=scorer.read(scorer.DEFAULT_OUTPUT/'scores185.json.gz')
            actual=scorer.read(output/'scores185.json.gz')
            self.assertEqual([(r['id'],r['metrics']) for r in expected],[(r['id'],r['metrics']) for r in actual])

    def test_portable_input_and_answer_bindings(self):
        receipt=scorer.read(scorer.BENCHMARK/'run_receipt.json')
        self.assertEqual(receipt['input_sha256'],scorer.sha(scorer.DEFAULT_INPUT))
        for case in scorer.read(scorer.DEFAULT_INPUT)['cases']:
            self.assertNotIn('case_path',case)
            self.assertNotIn('reference_path',case)
            self.assertTrue(case['tissue_tier_code'])
            self.assertEqual(hashlib.sha256(case['answer'].encode()).hexdigest(),case['answer_sha256'])

    def test_main_table_defaults_to_current_release(self):
        run=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'results/calculate_main_table_score.py')],
                           cwd=ROOT.parent,capture_output=True,text=True,encoding='utf8')
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('cleareval-benchmark-20261103-v1',run.stdout)
        self.assertIn('185 answers',run.stdout)


if __name__=='__main__':
    unittest.main()
