"""Source-recipe controls for promotion; no new model generation."""
import unittest
from cleareval_scoring import operation_claims as claims,operations

def audit(texts,method='CUBIC',ref='CUBIC_2019'):
    steps=[{'id':f'C{i+1}','text':text,'heading':'Tissue Optical Clearing','occurrences':1} for i,text in enumerate(texts)]
    case={'method':method,'reference_id':ref,'candidate_steps':steps,'answer':'\n'.join(texts)}
    return claims.audit(case,{'logical_candidate_steps':steps})

class ClaimReleaseTests(unittest.TestCase):
    def test_correct_source_recipes(self):
        fixtures=[
          ('CUBIC_2015','CUBIC-R1 (25% w/w urea, 25% w/w Quadrol, 15% w/w Triton X-100)'),
          ('CUBIC_2015','CUBIC-R2 (25% w/w urea, 50% w/w sucrose, 10% w/w triethanolamine)'),
          ('CUBIC_2015','CUBIC-R2 (25% w/w urea, 50% w/w sucrose, 10% w/w triethanolamine, 0.1% v/v Triton X-100)'),
          ('CUBIC_2019','CUBIC-L (10% w/w N-butyldiethanolamine, 10% w/w Triton X-100)'),
          ('CUBIC_2019','CUBIC-R+(N) (45% w/w antipyrine, 30% w/w nicotinamide, 0.5% v/v N-butyldiethanolamine)'),
          ('CUBIC_2019','CUBIC-R+(M) (45% w/w antipyrine, 30% w/w N-methylnicotinamide, 0.5% v/v N-butyldiethanolamine)'),
          ('CUBIC_2018','CUBIC-R (45% w/w antipyrine, 30% w/w nicotinamide)'),
          ('CUBIC_2018','CUBIC-RA (45% w/w antipyrine, 30% w/w N-methylnicotinamide, 0.5% v/v N-butyldiethanolamine)')]
        for ref,text in fixtures:
            with self.subTest(recipe=text):self.assertEqual(audit(['Incubate in '+text],ref=ref)[0]['status'],'PASS')

    def test_distinct_named_variants_do_not_share_definitions(self):
        findings=audit([
            'Incubate sample A in CUBIC-R+(N) (45% w/w antipyrine, 30% w/w nicotinamide, 0.5% v/v N-butyldiethanolamine).',
            'Incubate sample B in CUBIC-R+(M) (45% w/w antipyrine, 30% w/w N-methylnicotinamide, 0.5% v/v N-butyldiethanolamine).'])
        self.assertEqual([x['status'] for x in findings],['PASS','PASS'])

    def test_nested_unit_parentheses_keep_the_full_recipe(self):
        findings=audit(['Incubate in CUBIC-R1 (25% (wt/wt) urea, 25% (wt/wt) Quadrol, 15% (wt/wt) Triton X-100).'],ref='CUBIC_2015')
        self.assertEqual(findings[0]['status'],'PASS')

    def test_no_false_conflicts_from_other_contexts(self):
        fixtures=[
          ('CUBIC','CUBIC_2015','Incubate in half-diluted CUBIC-R1 (12.5% w/w urea).'),
          ('CUBIC','CUBIC_2015','Incubate in CUBIC-R10.'),
          ('CUBIC','CUBIC_2015','Incubate in CUBIC-R0 (30% w/v sucrose, 0.1% v/v Triton X-100).'),
          ('CUBIC','CUBIC_2015','Incubate in CUBIC-R1 (25% w/w urea, 25% w/w Quadrol, 15% w/w Triton X-100); wash in PBS with 0.1% sodium azide.'),
          ('FDISCO','fdisco2019','Wash out 20% DMSO before FDISCO.'),
          ('FDISCO','fdisco2019','Incubate primary antibody in 5% DMSO.'),
          ('FDISCO','fdisco2019','Dehydrate in 50% THF.'),
          ('FDISCO','fdisco2019','Use pure DBE for RI matching.'),
          ('BoneClear','BONECLEAR_2019','Incubate in BoneClear Solution A.')]
        for method,ref,text in fixtures:
            with self.subTest(text=text):self.assertNotEqual(audit([text],method,ref)[0]['status'],'FAIL')

    def test_explicit_errors_still_detected(self):
        fixtures=[
          ('CUBIC','CUBIC_2015','CUBIC-R0 (20 vol% MXDA, 15% w/v sorbitol)'),
          ('CUBIC','CUBIC_2015','CUBIC-R10 (30% w/v SDS, 50% v/v DMSO)'),
          ('CUBIC','CUBIC_2015','CUBIC-R1 (30% w/w urea, 25% w/w Quadrol, 15% w/w Triton X-100)'),
          ('CUBIC','CUBIC_2015','CUBIC-R2 (25% w/w urea, 50% w/w sucrose, 10% w/w triethanolamine, 2% v/v Triton X-100)'),
          ('CUBIC','CUBIC_2018','CUBIC-R (30% w/v SDS, 50% v/v DMSO)'),
          ('CUBIC','CUBIC_2019','CUBIC-R+(N) (45% w/w antipyrine, 30% w/w N-methylnicotinamide, 0.5% v/v N-butyldiethanolamine)'),
          ('FDISCO','fdisco2019','FDISCO (70% w/v DMSO, 30% v/v benzyl alcohol)'),
          ('FDISCO','fdisco2019','FDISCO-R0 (30 vol% DMSO, 70 vol% BSA)')]
        for method,ref,text in fixtures:
            with self.subTest(text=text):self.assertEqual(audit(['Incubate in '+text],method,ref)[0]['status'],'FAIL')

    def test_numeric_name_boundaries(self):
        for text in ['CUBIC-R10','CUBIC-R21','reagent 10','reagent 20']:
            with self.subTest(text=text):
                self.assertFalse({x['id'] for x in operations.mentions(text,'CUBIC')} & {'cubic_r1','cubic_r2'})

    def test_existing_chemical_dictionary_is_reused(self):
        wrong='Incubate in CUBIC-L (10 wt% N-butylethanolamine, 10 wt% Triton X-100).'
        result=audit([wrong])[0]
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['claims'][0]['variants'][0]['checks']['extra:butylethanolamine'],'FAIL')
        correct='Incubate in CUBIC-R2 (25 wt% urea, 50 wt% sucrose, 10 wt% 2,2\',2\'\'-nitrilotriethanol).'
        self.assertEqual(audit([correct],ref='CUBIC_2015')[0]['status'],'PASS')

if __name__=='__main__':unittest.main()
