"""Real cached-answer regressions for the integration issues found in full replay."""
import unittest
import cleareval_complete_scoring as s
from cleareval_scoring import scoring_v6


class HistoricalClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=s.read(s.DEFAULT_INPUT)['cases']
        cls.decisions=s.read(s.DEFAULT_INPUT.with_name('adjudications.json'))
        cls.previous={(r['input_id'],b['branch']):b['metrics'] for r in s.read(s.DEFAULT_PREVIOUS) for b in r['branches']}
        cls.policy=s.read(s.POLICY_PATH)

    def evaluate(self,ident):
        case=next(c for c in self.cases if c['id']==ident)
        packet=scoring_v6.score_branch(case,self.decisions)
        score=s.correctness(case,packet,self.previous[case['id'],case['branch']],self.policy)
        return case,packet,score

    def test_wrong_clearsee_solution_formula_still_deducts(self):
        _,packet,score=self.evaluate('EXPAND_107')
        self.assertLess(score['co_method']['value'],2)
        self.assertEqual(packet['written']['metrics']['confirmed_correct_credit'],0)

    def test_wrong_focm_and_ce3d_formulas_remain_detected(self):
        for ident in ['EXPAND_009','EXPAND_183']:
            with self.subTest(ident=ident):
                _,packet,score=self.evaluate(ident)
                self.assertTrue(packet['independent_recipe_findings'])
                self.assertLess(min(score['co_method']['value'],score['co_param']['value']),2)

    def test_impossible_dilution_is_not_hidden_by_correct_working_label(self):
        _,packet,score=self.evaluate('EXPAND_167')
        self.assertEqual(packet['preparation_dilution_audit'][0]['status'],'FAIL')
        self.assertEqual(score['co_param']['value'],1)

    def test_chinese_dilution_and_unrelated_babb_do_not_create_new_review(self):
        for ident in ['EXPAND_112','EXPAND_139']:
            with self.subTest(ident=ident):
                _,_,score=self.evaluate(ident)
                self.assertEqual(score['co_param']['value'],2)
                self.assertEqual(score['co_param']['status'],'DETERMINED')

    def test_remaining_declaration_forms_are_bound_to_their_uses(self):
        for ident in ['EXPAND_016','EXPAND_004','EXPAND_169','EXPAND_024','EXPAND_138','EXPAND_108','EXPAND_159','EXPAND_172']:
            with self.subTest(ident=ident):
                _,packet,_=self.evaluate(ident)
                self.assertFalse([a for a in packet['operation_claim_audit']
                                  if a['reason']=='LEGACY_CLAIM_RETAINED_PENDING_BINDING'])

    def test_staining_additive_does_not_redefine_clearsee_stock(self):
        _,packet,score=self.evaluate('EXPAND_105')
        self.assertEqual(score['co_param']['value'],2)
        self.assertEqual(score['co_param']['status'],'DETERMINED')
        self.assertFalse(packet['independent_recipe_unresolved'])

    def test_f1_preserves_the_same_step_uncertainty_as_sr_and_sp(self):
        case,packet,_=self.evaluate('EXPAND_138')
        row=s.branch_score(case,packet,self.previous[case['id'],case['branch']],self.policy,s.read(s.KB_PATH)['rows'])
        m=packet['written']['metrics'];den=m['N_R']+m['N_C']
        self.assertGreater(m['correctness_review_credit'],0)
        self.assertEqual(row['metrics']['bio_f1']['bounds'],
                         [2*m['confirmed_correct_credit']/den,2*(m['confirmed_correct_credit']+m['correctness_review_credit'])/den])
        self.assertEqual(row['metrics']['bio_f1']['status'],'PROVISIONAL')


if __name__=='__main__':unittest.main()
