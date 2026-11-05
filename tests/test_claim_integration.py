import copy,unittest
import cleareval_complete_scoring as s
from cleareval_scoring import scoring_v5,scoring_v6

def example():
    return {'id':'constructed-unmatched-recipe','branch':'selected','method':'CUBIC',
       'reference_id':'CUBIC_2015','question':'Clear fixed tissue.',
       'answer':'1. Incubate in CUBIC-R0 (20 vol% MXDA, 15% w/v sorbitol).',
       'reference_steps':[{'id':'R1','text':'Incubate in full CUBIC-R1.','heading':'Tissue Optical Clearing','occurrences':1}],
       'candidate_steps':[{'id':'C1','text':'Incubate in CUBIC-R0 (20 vol% MXDA, 15% w/v sorbitol).','heading':'Tissue Optical Clearing','occurrences':1}]}

class ClaimIntegrationTests(unittest.TestCase):
    def test_unmatched_conflict_reaches_complete_correctness(self):
        c=example();p=scoring_v6.score_branch(c)
        self.assertFalse(p['written']['pairs'])
        self.assertEqual(p['independent_recipe_findings'][0]['owner'],'co_method')
        old={k:{'value':v} for k,v in [('co_order',3),('co_method',2),('co_param',2),('co_chem',1)]}
        out=s.correctness(c,p,old,{'order_resolutions':{}})
        self.assertEqual(out['co_method']['value'],1)
        self.assertEqual(out['co_method']['status'],'DETERMINED')
        self.assertEqual(out['co_method']['findings'][0]['field'],'declared_recipe:independent_claim')

    def test_correct_named_recipe_keeps_all_credit(self):
        c=example();text='Incubate in full CUBIC-R1 (25% w/w urea, 25% w/w Quadrol, 15% w/w Triton X-100).'
        c['answer']=text;c['candidate_steps'][0]['text']=text
        before=scoring_v5.score_branch(c);after=scoring_v6.score_branch(c)
        self.assertFalse(after['independent_recipe_findings'])
        self.assertEqual(after['written']['metrics']['confirmed_correct_credit'],1)
        self.assertEqual(before['written']['metrics']['correctness_Bio_SR'],after['written']['metrics']['correctness_Bio_SR'])

    def test_new_checks_recalculate_bio_intervals(self):
        c=example();c['candidate_steps'][0]['text']='Incubate in full CUBIC-R1 (30% w/v SDS, 50% v/v DMSO).'
        c['answer']=c['candidate_steps'][0]['text'];p=scoring_v6.score_branch(c)
        for mode in ['written','occurrence']:
            self.assertEqual(p[mode]['metrics']['confirmed_correct_credit'],0)
            self.assertEqual(p[mode]['metrics']['correctness_Bio_SR_lower'],0)
            self.assertEqual(p[mode]['metrics']['correctness_Bio_SP_lower'],0)

    def test_preparation_definition_does_not_increase_denominator(self):
        c=example();c['candidate_steps'][0]['text']='Incubate in CUBIC-R0.'
        c['candidate_steps'].append({'id':'P1','text':'Prepare CUBIC-R0: 20 vol% MXDA, 15% w/v sorbitol.','heading':'Preparation','occurrences':1})
        c['answer']='\n'.join(x['text'] for x in c['candidate_steps']);p=scoring_v6.score_branch(c)
        self.assertEqual(p['written']['metrics']['N_C'],1)
        self.assertEqual(len(p['independent_recipe_findings']),1)

    def test_time_change_does_not_change_claim_result(self):
        c=example();a=scoring_v6.score_branch(c)
        c['candidate_steps'][0]['text']+=' (Time: 1 h; Temperature: 4 C)';c['answer']=c['candidate_steps'][0]['text']
        b=scoring_v6.score_branch(c)
        self.assertEqual(a['independent_recipe_findings'],b['independent_recipe_findings'])

    def test_both_correct_variants_keep_credit_through_full_step_scorer(self):
        c=example();c['reference_id']='CUBIC_2019'
        formulas=[('N','nicotinamide'),('M','N-methylnicotinamide')]
        c['candidate_steps']=[{'id':f'C{i+1}','text':f'Incubate in full CUBIC-R+({variant}) (45% w/w antipyrine, 30% w/w {ingredient}, 0.5% v/v N-butyldiethanolamine).','heading':'RI Matching','occurrences':1} for i,(variant,ingredient) in enumerate(formulas)]
        c['reference_steps']=[dict(st,id=f'R{i+1}') for i,st in enumerate(c['candidate_steps'])]
        c['answer']='\n'.join(st['text'] for st in c['candidate_steps'])
        p=scoring_v6.score_branch(c)
        self.assertEqual(p['written']['metrics']['confirmed_correct_credit'],2)
        self.assertFalse(p['independent_recipe_findings'])

    def test_existing_expert_recipe_decision_is_preserved(self):
        cases=s.read(s.DEFAULT_INPUT)['cases']
        c=next(c for c in cases if c['id']=='EXPAND_156')
        ds=s.read(s.DEFAULT_INPUT.with_name('adjudications.json'))
        p=scoring_v6.score_branch(c,ds)
        reviews=[d for d in p['human_adjudications'] if d['field']=='declared_recipe:cubic_rplus']
        self.assertEqual(len(reviews),1)
        self.assertEqual(reviews[0]['state'],'FAIL')
        self.assertEqual(p['correctness_recipe_audit']['cubic_rplus']['status'],'FAIL')

if __name__=='__main__':unittest.main()
