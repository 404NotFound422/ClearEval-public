"""Recipe prose must not change the specimen-operation inventory or conditions."""
import unittest

from cleareval_scoring import scoring_v6
from test_claim_ownership import case_for,GOOD,BARE,pair_states,main_correctness


class InlineExecutionTests(unittest.TestCase):
    def test_parenthetical_stock_concentration_is_not_working_concentration(self):
        case=case_for(['Incubate in 5% v/v H2O2 in methanol (1 volume 30% v/v H2O2 + 5 volumes methanol).'])
        case.update(method='iDISCO+',reference_id='IDISCO_2014')
        case['reference_steps'][0]['text']='Incubate in 5% v/v H2O2 in methanol.'
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'PASS'})

    def test_wrong_explicit_working_concentration_still_fails(self):
        case=case_for(['Incubate in 6% v/v H2O2 in methanol (1 volume 30% v/v H2O2 + 4 volumes methanol).'])
        case.update(method='iDISCO+',reference_id='IDISCO_2014')
        case['reference_steps'][0]['text']='Incubate in 5% v/v H2O2 in methanol.'
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'FAIL'})

    def test_inconsistent_dilution_recipe_is_not_silently_ignored(self):
        case=case_for(['Incubate in 5% v/v H2O2 in methanol (1 volume 30% v/v H2O2 + 4 volumes methanol).'])
        case.update(method='iDISCO+',reference_id='IDISCO_2014')
        case['reference_steps'][0]['text']='Incubate in 5% v/v H2O2 in methanol.'
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'FAIL'})
        self.assertEqual(main_correctness(case,packet)['co_param']['value'],1)

    def test_preparation_repeat_does_not_repeat_specimen_operation(self):
        case=case_for([GOOD.replace(').','; mix 3 x with a spatula).')])
        packet=scoring_v6.score_branch(case)
        self.assertEqual(packet['occurrence']['metrics']['N_C'],1)
        self.assertEqual(packet['occurrence']['metrics']['correctness_Bio_SP'],1)

    def test_reference_recipe_prose_does_not_require_candidate_to_restate_it(self):
        case=case_for([BARE])
        case['reference_steps'][0]['text']=GOOD
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'PASS'})

    def test_wrong_inline_recipe_is_still_checked_after_projection(self):
        case=case_for([GOOD.replace('25% w/w urea','30% w/w urea')])
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'FAIL'})
        self.assertEqual(packet['written']['metrics']['N_C'],1)

    def test_containing_clause_is_a_recipe_definition(self):
        text='Incubate in full CUBIC-R1, containing 30% w/w urea, 25% w/w Quadrol and 15% w/w Triton X-100.'
        packet=scoring_v6.score_branch(case_for([text]))
        self.assertEqual(pair_states(packet),{'C1':'FAIL'})

    def test_named_stock_formula_does_not_change_execution_action(self):
        case=case_for([GOOD.replace(').','; mix in a clean vessel and store stock at room temperature).')])
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'PASS'})

    def test_prepare_in_one_sentence_then_use_in_another(self):
        case=case_for([BARE])
        case['candidate_steps'].insert(0,dict(id='P1',text='CUBIC-R1 was prepared with 30% w/w urea, 25% w/w Quadrol and 15% w/w Triton X-100.',heading='Reagent preparation',occurrences=1))
        case['answer']='\n'.join(s['text'] for s in case['candidate_steps'])
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet).get('C1'),'FAIL')
        self.assertEqual(packet['written']['metrics']['N_C'],1)

    def test_chinese_preparation_and_unicode_formula_keep_working_quantity(self):
        case=case_for(['Incubate in 5% H₂O₂ in methanol（配制：30% H₂O₂ : methanol = 1:5, vol/vol）.'])
        case.update(method='iDISCO+',reference_id='IDISCO_2014')
        case['reference_steps'][0]['text']='Incubate in 5% H2O2 in methanol.'
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'PASS'})

    def test_legacy_named_recipe_checks_also_have_per_use_ownership(self):
        good='Incubate in ClearSee (10% w/v xylitol, 15% w/v sodium deoxycholate, 25% w/v urea).'
        case=case_for([good,good.replace('25% w/v urea','30% w/v urea')])
        case.update(method='ClearSee',reference_id='CLEARSEE_2015')
        for ref in case['reference_steps']:ref['text']='Incubate in ClearSee.'
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'PASS','C2':'FAIL'})

    def test_repeated_stock_mention_still_owns_its_recipe(self):
        text=GOOD.replace(').','); replace with fresh CUBIC-R1 after use.').replace('25% w/w urea','30% w/w urea')
        self.assertEqual(pair_states(scoring_v6.score_branch(case_for([text]))),{'C1':'FAIL'})

    def test_seedb_extension_uses_the_same_local_recipe_ownership(self):
        case=case_for(['Incubate in SeeDB2-G (Omnipaque350).','Incubate in SeeDB2-G (70% w/v fructose in PBS).'])
        case.update(method='SeeDB2',reference_id='seedb2-author-protocol-2018')
        for ref in case['reference_steps']:ref['text']='Incubate in SeeDB2-G.'
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'PASS','C2':'FAIL'})
        self.assertEqual(main_correctness(case,packet)['co_method']['value'],1)

    def test_solution_qualifiers_do_not_hide_wrong_formulas(self):
        for name in ['CUBIC-R1 solution','CUBIC-R1 clearing solution','CUBIC-R1 solution I']:
            text=GOOD.replace('CUBIC-R1',name).replace('25% w/w urea','30% w/w urea')
            with self.subTest(name=name):
                self.assertEqual(pair_states(scoring_v6.score_branch(case_for([text]))),{'C1':'FAIL'})

    def test_dilution_ratio_is_checked_in_both_common_notations(self):
        for recipe,expected in [('用30% H2O2 按 1:5 稀释至 methanol 中','PASS'),
                                ('1:20 dilution of 30% H2O2 in methanol','FAIL'),
                                ('1 volume 30% H2O2 to 5 volumes methanol','PASS')]:
            with self.subTest(recipe=recipe):
                case=case_for(['Incubate in 5% H2O2 in methanol ('+recipe+').'])
                case.update(method='iDISCO+',reference_id='IDISCO_2014')
                case['reference_steps'][0]['text']='Incubate in 5% H2O2 in methanol.'
                self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':expected})

    def test_optional_recipe_basis_does_not_invalidate_explicit_working_basis(self):
        case=case_for(['Incubate in 5% v/v H2O2 in methanol (1 volume 30% H2O2 + 5 volumes methanol).'])
        case.update(method='iDISCO+',reference_id='IDISCO_2014')
        case['reference_steps'][0]['text']='Incubate in 5% v/v H2O2 in methanol.'
        packet=scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet),{'C1':'PASS'})
        self.assertEqual(packet['preparation_dilution_audit'][0]['status'],'UNKNOWN')

    def test_removed_stock_does_not_own_a_wash(self):
        case=case_for([GOOD.replace('25% w/w urea','30% w/w urea'),'Wash in PBS to remove residual CUBIC-R1.'])
        case['reference_steps'][1]['text']='Wash in PBS.'
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'FAIL','C2':'PASS'})

    def test_half_dilution_can_state_the_correct_stock_formula(self):
        text='Incubate in half-diluted CUBIC-R (45 wt% antipyrine, 30 wt% nicotinamide, diluted 1:1 with water).'
        case=case_for([text]);case.update(reference_id='CUBIC_2018')
        case['reference_steps'][0]['text']='Incubate in half-diluted CUBIC-R.'
        self.assertEqual(pair_states(scoring_v6.score_branch(case)),{'C1':'PASS'})


if __name__=='__main__':unittest.main()
