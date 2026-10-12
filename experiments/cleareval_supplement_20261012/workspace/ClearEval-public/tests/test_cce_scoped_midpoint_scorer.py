"""Regression checks for actual ClearEval source/lookup and duration failures."""
import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_scoped_midpoint_scorer_v1 as scorer


class ScopedMidpointRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner, cls.registry = scorer.runtime()
        report = ROOT.parent/'reports/cleareval_20261012'
        cls.config = scorer.read(report/'scorer_revision/config.json')
        cls.annotations = {r['id']:r for r in scorer.read(report/'llm_decomposition.json')['results']}
        cls.post = {k:scorer.read(v['baseline_v7']['path']) for k,v in cls.annotations.items()}

    def test_actual_map2_row_order_does_not_change_task_selected_score(self):
        old_rows = self.runner.TISSUE_KB
        first = scorer.score_record(self.post['FPC03'],21,self.config,self.runner,self.registry)
        try:
            self.runner.TISSUE_KB = list(reversed(old_rows))
            reverse = scorer.score_record(self.post['FPC03'],21,self.config,self.runner,self.registry)
        finally:
            self.runner.TISSUE_KB = old_rows
        self.assertEqual(first['metrics'],reverse['metrics'])
        self.assertAlmostEqual(first['metrics']['s_label'],1.2)
        self.assertAlmostEqual(first['metrics']['Eff'],0.34507812539055827)

    def test_real_range_is_scored_at_time_midpoint_not_score_midpoint(self):
        ann = self.annotations['FPC07']
        doc = scorer.read(ann['source_document']['path'])
        r = scorer.score_record(self.post['FPC07'],248,self.config,self.runner,self.registry,ann,doc)
        self.assertEqual(r['time_derivation']['hours'],33.5)
        self.assertAlmostEqual(r['metrics']['Eff'],0.24226083290564213)
        ends = r['time_sensitivity'][0], r['time_sensitivity'][-1]
        self.assertNotAlmostEqual(r['metrics']['Eff'],sum(v['Eff'] for v in ends)/2)

    def test_range_rule_does_not_conceal_missing_operation_or_optional_branch(self):
        saved = self.post['FPC07']['conversion']['legacy_projection']['time_calculation']
        self.assertEqual(scorer.time_input(saved,None)['hours'],33.5)
        for issue in ['unknown_included_duration_or_repeat:missing', 'optional_initial_core_branch_not_selected']:
            changed=copy.deepcopy(saved);changed['issues'].append(issue)
            self.assertIsNone(scorer.time_input(changed,None)['hours'])
        changed=copy.deepcopy(saved);changed['known_operation_contributions'].pop()
        self.assertIsNone(scorer.time_input(changed,None)['hours'])

    def test_edited_answer_cannot_reuse_old_semantic_source_quotes(self):
        ann = self.annotations['FPC07']
        doc = scorer.read(ann['source_document']['path'])
        changed=copy.deepcopy(ann)
        changed['relations'][0]['source_spans'][0]['quote'] += ' altered'
        with self.assertRaisesRegex(ValueError,'Source quote'):
            scorer.semantic_projection(changed,doc)
        changed=copy.deepcopy(ann);changed['answer_sha256']='wrong-answer'
        with self.assertRaisesRegex(ValueError,'different answer'):
            scorer.semantic_projection(changed,doc)

    def test_scope_failure_restores_original_helpers(self):
        match,compat=self.runner._match_marker_to_targets,self.runner._get_marker_fluor_compat
        bad={'map2':{'scope':{'大类':'absent','亚类':'absent','结构/细胞类型':'absent'}}}
        with self.assertRaisesRegex(ValueError,'absent'):
            with scorer.task_lookup(self.runner,[],bad):
                self.runner._get_marker_fluor_compat('MAP2','Alexa Fluor 647')
        self.assertIs(match,self.runner._match_marker_to_targets)
        self.assertIs(compat,self.runner._get_marker_fluor_compat)


if __name__ == '__main__':
    unittest.main()
