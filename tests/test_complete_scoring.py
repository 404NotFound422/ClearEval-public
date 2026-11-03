"""Regression cases for complete CCE composition; offline frozen data only."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cleareval_complete_scoring as s


class CompleteScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=s.read(s.DEFAULT_INPUT)['cases']
        cls.packets={(r['id'],r['branch']):r['packet'] for r in s.read(s.DEFAULT_VERIFIED)}
        cls.old={(r['input_id'],b['branch']):b['metrics'] for r in s.read(s.DEFAULT_PREVIOUS) for b in r['branches']}
        cls.policy=s.read(s.POLICY_PATH);cls.kb=s.read(s.KB_PATH)['rows']

    def fixture(self,ident):
        c=next(c for c in self.cases if c['id']==ident)
        return c,self.packets[c['id'],c['branch']],self.old[c['id'],c['branch']]

    def evaluate(self,ident):
        c,p,o=self.fixture(ident)
        return s.branch_score(c,p,o,self.policy,self.kb)['metrics']

    def test_exp026_known_defects_reach_aggregates(self):
        m=self.evaluate('EXPAND_026')
        self.assertEqual([m[k]['value'] for k in ['co_order','co_method','co_param']], [0,0,0])
        self.assertEqual(m['s_time']['nominal_hours'],11.25)
        self.assertEqual(m['Co']['value'],.25)
        self.assertLess(m['IA']['value'],.5)

    def test_time_reference_only_affects_effectiveness(self):
        c,p,o=self.fixture('EXPAND_026');p=copy.deepcopy(p)
        before=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        for pair in p['written']['pairs']:
            pair['effectiveness_reference_checks'].update(duration='PASS',temperature='FAIL')
        after=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        for k in ['co_order','co_method','co_param','Co']:self.assertEqual(before[k],after[k])

    def test_missing_dcm_transition_is_not_wrong_methanol(self):
        c,p,o=self.fixture('EXPAND_126');o=copy.deepcopy(o)
        o['co_method']['value']=2
        out=s.correctness(c,p,o,self.policy)
        self.assertNotIn('unmatched_material_identity',[f['field'] for f in out['co_method'].get('findings',[])])

    def test_missing_antibody_washes_affect_completeness(self):
        m=self.evaluate('EXPAND_174')
        self.assertLess(m['c_step']['value'],2*m['c_step']['base_coverage'])
        self.assertEqual(m['c_step']['missing_operations'],['post_primary_wash','post_secondary_wash'])

    def test_wrong_named_recipe_reaches_correctness(self):
        m=self.evaluate('EXPAND_107')
        self.assertLess(m['co_method']['value'],2)
        self.assertLess(m['Co']['value'],1)

    def test_pbs_preservation_never_deducts(self):
        c,p,o=self.fixture('EXPAND_130');p=copy.deepcopy(p)
        before=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        p['non_scoring_checks']={'concentration:literal:sodium_azide':'FAIL'}
        for pair in p['written']['pairs']:
            pair['non_scoring_checks']={'concentration:literal:sodium_azide':'FAIL'}
        after=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        self.assertEqual(before,after)

    def test_preparation_inventory_does_not_inflate_step_denominator(self):
        c,p,o=self.fixture('EXPAND_024');p=copy.deepcopy(p)
        before=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        p['preparation_steps']['candidate_steps'].append({'id':'extra-prep','text':'Prepare PBS.'})
        after=s.branch_score(c,p,o,self.policy,self.kb)['metrics']
        for k in ['c_step','cleareval_coverage','bio_sr','bio_sp']:self.assertEqual(before[k],after[k])

    def test_incomplete_answers_are_included_as_zero_completion(self):
        for ident in self.policy['incomplete_outputs']:
            m=self.evaluate(ident)
            self.assertEqual([m[k]['value'] for k in ['Com','Co','Eff','IA']], [0]*4)
            self.assertEqual(m['c_step']['status'],'INCOMPLETE_OUTPUT')

    def test_unresolved_reference_is_not_confirmed_failure(self):
        for ident,key,mid in [('EXPAND_157','s_time',1.5),('EXPAND_102','s_label',3)]:
            node=self.evaluate(ident)[key]
            self.assertEqual(node['value'],mid)
            self.assertEqual(node['status'],'PROVISIONAL')
            self.assertEqual(node['bounds'],[0,mid*2])

    def test_no_alignment_cannot_confirm_full_correctness(self):
        m=self.evaluate('EXPAND_102')
        for k in ['co_method','co_param']:
            self.assertEqual(m[k]['status'],'PROVISIONAL')
            self.assertEqual(m[k]['bounds'],[0,2])
            self.assertLess(m[k]['value'],2)

    def test_all193_then185_have_finite_coherent_scores(self):
        grouped={}
        for c in self.cases:
            self.assertEqual(hashlib.sha256(c['answer'].encode()).hexdigest(),c['answer_sha256'])
            row=s.branch_score(c,self.packets[c['id'],c['branch']],self.old[c['id'],c['branch']],self.policy,self.kb)
            grouped.setdefault(c['id'],[]).append(row)
        self.assertEqual(len(grouped),185)
        for rows in grouped.values():
            r=s.combine_branches(rows);m=r['metrics']
            for k,n in m.items():
                self.assertLessEqual(n['bounds'][0],n['value']+1e-12)
                self.assertLessEqual(n['value'],n['bounds'][1]+1e-12)
            self.assertAlmostEqual(m['IA']['value'],min(m[k]['value'] for k in ['Com','Co','Eff']))
            self.assertAlmostEqual(m['Co']['value'],sum(m[k]['value']/v for k,v in [('co_order',3),('co_method',2),('co_param',2),('co_chem',1)])/4)


if __name__=='__main__':
    unittest.main()
