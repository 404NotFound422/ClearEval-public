"""Source-bound engineering controls; no scientific labels or teacher calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from experiments.construct_validity.source_conditions import diagnose, load_rules

ROOT = Path(__file__).absolute().parents[1]
METHODS = ['CUBIC','FDISCO','MACS','SeeDB2']
HEADER = 'Chosen Method: SeeDB2\n'
CURRENT_PROTOCOL = '**Chosen Method:** SeeDB2\uff1b**Chosen Labeling:** \u4fdd\u7559\u5df2\u5b8c\u6210\u5e76\u8d28\u63a7\u5408\u683c\u7684 DiI \u4e0e DiD \u819c\u793a\u8e2a\uff0c\u4e0d\u8ffd\u52a0\u6297\u4f53\u6216\u6838\u67d3\u6599\u3002\n**Justification:** SeeDB2 \u91c7\u7528\u6c34\u76f8\u9ad8\u6298\u5c04\u7387\u4ecb\u8d28\u8fdb\u884c\u6298\u5c04\u7387\u5339\u914d\uff0c\u53ef\u7701\u53bb\u4f1a\u62bd\u63d0\u819c\u8102\u53ca\u666e\u901a DiI/DiD \u7684\u6709\u673a\u6eb6\u5242\u8131\u6c34\u548c\u5f3a\u8131\u8102\u6b65\u9aa4\u3002\u5bf9\u4e24\u7c7b\u6837\u672c\u5206\u522b\u8fdb\u884c\u7f13\u6162\u6d53\u5ea6\u9012\u589e\u548c\u5e73\u8861\uff0c\u53ef\u5728\u4fdd\u7559\u4e24\u6761\u6765\u6e90\u9009\u62e9\u6027\u793a\u8e2a\u901a\u9053\u7684\u540c\u65f6\u6539\u5584\u900f\u660e\u5ea6\uff1bDiI \u4e0e DiD \u4fe1\u53f7\u4ec5\u5206\u522b\u4ee3\u8868\u5404\u81ea\u5c40\u7076\u653e\u7f6e\u4f4d\u7f6e\u51fa\u53d1\u7684\u819c\u8fde\u7eed\u6295\u5c04\u3002\n\n**Protocol Steps:**\n1 \u56fa\u5b9a\u540e\u5e73\u8861\u4e0e\u57fa\u7ebf\u8bb0\u5f55\n1.1 \u5c06\u5df2\u5b8c\u6210 DiI/DiD \u6269\u6563\u5e76\u8d28\u63a7\u5408\u683c\u7684\u810a\u9ad3\u6bb5\u7f6e\u4e8e PBS \u4e2d\u907f\u5149\u8f7b\u67d4\u6447\u52a8\u6d17\u6da4\uff0c\u6bcf\u6b21\u66f4\u6362\u65b0\u9c9c PBS\uff0c\u5171 3 \u6b21\u3002(Temperature: 4 \u2103, Time: 1 hour per wash)\n1.2 \u5c06\u5df2\u5b8c\u6210 DiI/DiD \u6269\u6563\u5e76\u8d28\u63a7\u5408\u683c\u7684\u8fde\u7eed\u8111\u5757\u7f6e\u4e8e PBS \u4e2d\u907f\u5149\u8f7b\u67d4\u6447\u52a8\u6d17\u6da4\uff0c\u6bcf\u6b21\u66f4\u6362\u65b0\u9c9c PBS\uff0c\u5171 3 \u6b21\u3002(Temperature: 4 \u2103, Time: 2 hours per wash)\n1.3 \u5728\u4e0d\u5207\u65ad\u6837\u672c\u7684\u6761\u4ef6\u4e0b\uff0c\u5206\u522b\u8bb0\u5f55\u810a\u9ad3\u6bb5\u548c\u8111\u5757\u4e2d DiI\u3001DiD \u7684\u8868\u9762\u57fa\u7ebf\u4fe1\u53f7\uff1b\u540e\u7eed\u5404\u6b65\u9aa4\u5747\u907f\u5149\u8fdb\u884c\u3002(Temperature: RT, Time: 30 minutes per sample)\n\n2 SeeDB2 \u6d53\u5ea6\u9012\u589e\u2014\u810a\u9ad3\u6bb5\n2.1 \u5c06\u5b8c\u6574\u810a\u9ad3\u6bb5\u6d78\u5165 25 vol% SeeDB2S \u5de5\u4f5c\u6db2\uff08\u4ee5 PBS \u7a00\u91ca\uff1bSeeDB2S \u4e3a iohexol \u57fa\u9ad8\u6298\u5c04\u7387\u4ecb\u8d28\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 24 hours)\n2.2 \u5c06\u810a\u9ad3\u6bb5\u8f6c\u5165 50 vol% SeeDB2S \u5de5\u4f5c\u6db2\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 24 hours)\n2.3 \u5c06\u810a\u9ad3\u6bb5\u8f6c\u5165 75 vol% SeeDB2S \u5de5\u4f5c\u6db2\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 24 hours)\n2.4 \u5c06\u810a\u9ad3\u6bb5\u8f6c\u5165 100% SeeDB2S\uff08RI = 1.52\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 48 hours)\n2.5 \u66f4\u6362\u65b0\u9c9c 100% SeeDB2S\uff0c\u7ee7\u7eed\u907f\u5149\u5e73\u8861\u81f3\u900f\u660e\u5ea6\u7a33\u5b9a\u3002(Temperature: 4 \u2103, Time: 24 hours)\n\n3 SeeDB2 \u6d53\u5ea6\u9012\u589e\u2014\u8fde\u7eed\u8111\u5757\n3.1 \u5c06\u5b8c\u6574\u8111\u5757\u6d78\u5165 25 vol% SeeDB2S \u5de5\u4f5c\u6db2\uff08\u4ee5 PBS \u7a00\u91ca\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 36 hours)\n3.2 \u5c06\u8111\u5757\u8f6c\u5165 50 vol% SeeDB2S \u5de5\u4f5c\u6db2\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 36 hours)\n3.3 \u5c06\u8111\u5757\u8f6c\u5165 75 vol% SeeDB2S \u5de5\u4f5c\u6db2\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 36 hours)\n3.4 \u5c06\u8111\u5757\u8f6c\u5165 100% SeeDB2S\uff08RI = 1.52\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 72 hours)\n3.5 \u66f4\u6362\u65b0\u9c9c 100% SeeDB2S\uff0c\u7ee7\u7eed\u907f\u5149\u5e73\u8861\u81f3\u900f\u660e\u5ea6\u7a33\u5b9a\u3002(Temperature: 4 \u2103, Time: 48 hours)\n\n4 \u819c\u67d3\u6599\u4fdd\u7559\u68c0\u67e5\n4.1 \u5c06\u810a\u9ad3\u6bb5\u4fdd\u6301\u6d78\u6ca1\u4e8e 100% SeeDB2S \u4e2d\uff0c\u6309\u4e0e\u57fa\u7ebf\u76f8\u540c\u7684\u91c7\u96c6\u8bbe\u7f6e\u5206\u522b\u68c0\u67e5 DiI \u4e0e DiD \u4fe1\u53f7\uff1b\u4ec5\u5728\u4e24\u901a\u9053\u7684\u5c40\u7076\u6765\u6e90\u548c\u8fde\u7eed\u7ea4\u7ef4\u4fe1\u53f7\u5747\u4fdd\u6301\u5408\u683c\u540e\u8fdb\u5165\u6210\u50cf\u3002(Temperature: RT, Time: 30 minutes)\n4.2 \u5c06\u8111\u5757\u4fdd\u6301\u6d78\u6ca1\u4e8e 100% SeeDB2S \u4e2d\uff0c\u6309\u4e0e\u57fa\u7ebf\u76f8\u540c\u7684\u91c7\u96c6\u8bbe\u7f6e\u5206\u522b\u68c0\u67e5 DiI \u4e0e DiD \u4fe1\u53f7\uff1b\u4ec5\u5728\u4e24\u901a\u9053\u7684\u5c40\u7076\u6765\u6e90\u548c\u8fde\u7eed\u7ea4\u7ef4\u4fe1\u53f7\u5747\u4fdd\u6301\u5408\u683c\u540e\u8fdb\u5165\u6210\u50cf\u3002(Temperature: RT, Time: 30 minutes)\n\n5 \u4fdd\u5b58\u4e0e\u6210\u50cf\u524d\u5904\u7406\n5.1 \u5c06\u810a\u9ad3\u6bb5\u548c\u8111\u5757\u5206\u522b\u5b8c\u5168\u6d78\u6ca1\u4e8e\u65b0\u9c9c 100% SeeDB2S \u4e2d\uff0c\u7f6e\u4e8e\u72ec\u7acb\u3001\u907f\u5149\u3001\u5bc6\u5c01\u5bb9\u5668\u4fdd\u5b58\u3002(Temperature: 4 \u2103, Time: up to 7 days)\n5.2 \u6210\u50cf\u524d\u5c06\u810a\u9ad3\u6bb5\u8fde\u540c SeeDB2S \u5e73\u8861\u81f3\u5ba4\u6e29\uff0c\u6cbf\u957f\u8f74\u65e0\u5f2f\u6298\u56fa\u5b9a\u4e8e\u4e0e RI 1.52 \u517c\u5bb9\u7684\u5149\u7247\u6210\u50cf\u8154\u4e2d\uff0c\u5e76\u4ee5\u987a\u5e8f\u626b\u63cf\u65b9\u5f0f\u5206\u522b\u91c7\u96c6 DiI \u4e0e DiD \u901a\u9053\u3002(Temperature: RT, Time: 1 hour)\n5.3 \u6210\u50cf\u524d\u5c06\u8111\u5757\u8fde\u540c SeeDB2S \u5e73\u8861\u81f3\u5ba4\u6e29\uff0c\u4fdd\u6301\u4e18\u8111\u81f3\u4f53\u611f\u76ae\u5c42\u7684\u539f\u6709\u65b9\u5411\u56fa\u5b9a\u4e8e\u72ec\u7acb\u7684 RI 1.52 \u517c\u5bb9\u6210\u50cf\u8154\u4e2d\uff0c\u5e76\u4ee5\u987a\u5e8f\u626b\u63cf\u65b9\u5f0f\u5206\u522b\u91c7\u96c6 DiI \u4e0e DiD \u901a\u9053\u3002(Temperature: RT, Time: 1 hour)'
REAL_DILUTIONS = ['2.1 \u5c06\u5b8c\u6574\u810a\u9ad3\u6bb5\u6d78\u5165 25 vol% SeeDB2S \u5de5\u4f5c\u6db2\uff08\u4ee5 PBS \u7a00\u91ca\uff1bSeeDB2S \u4e3a iohexol \u57fa\u9ad8\u6298\u5c04\u7387\u4ecb\u8d28\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 24 hours)', '3.1 \u5c06\u5b8c\u6574\u8111\u5757\u6d78\u5165 25 vol% SeeDB2S \u5de5\u4f5c\u6db2\uff08\u4ee5 PBS \u7a00\u91ca\uff09\u4e2d\u8f7b\u67d4\u6447\u52a8\u3002(Temperature: 4 \u2103, Time: 36 hours)']


def source_cards():
    registry = json.loads((ROOT/'KnowledgeBase/source_registry.json').read_text(encoding='utf-8-sig'))
    cards=[]
    for record in registry['sources']:
        if record['id'] not in {'SEEDB2_PROTOCOL_2018','SEEDB2_CORRECTION_2018'}:
            continue
        raw=(ROOT/record['snapshot']['text_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==record['snapshot']['text_sha256']
        cards.append({'id':record['id'],'identity':record['identity'],'passages':deepcopy(record['passages']),
            'source_document':{'text':raw.decode('utf-8'),'sha256':record['snapshot']['text_sha256'],
                'version':record['identity']['version']}})
    return cards


class SeeDB2SourceConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards=source_cards()
        cls.rules=load_rules(ROOT)
        cls.rules['rules']=[r for r in cls.rules['rules'] if r['id']=='SEEDB2S_PBS_PREPARATION_ROLE']

    def run_case(self,text,cards=None,rules=None):
        return diagnose(text,self.cards if cards is None else cards,self.rules if rules is None else rules,method_keys=METHODS)

    def test_two_actual_q165_spans_and_complete_current_protocol_are_local_risks(self):
        full=self.run_case(CURRENT_PROTOCOL)
        self.assertEqual(full['version'],'source-condition-diagnostics-v5')
        self.assertEqual(full['local_risk_count'],2)
        self.assertEqual(full['author_recipe_nonconformance_count'],0)
        self.assertEqual(full['potential_conflict_count'],0)
        self.assertEqual(full['review_required_count'],0)
        self.assertEqual([f['record_span']['quote'] for f in full['findings']],REAL_DILUTIONS)
        for literal in REAL_DILUTIONS:
            with self.subTest(literal=literal):
                result=self.run_case(HEADER+literal)
                self.assertEqual(result['local_risk_count'],1)
                f=result['findings'][0]
                self.assertEqual(f['typed_relation'],'LOCAL_POTENTIAL_RISK')
                self.assertEqual(f['relation_proof']['operation'],'DILUTE_EXISTING_SOLUTION')
                self.assertEqual(f['relation_proof']['stock_origin'],'NOT_PROVEN')
                self.assertFalse(f['changes_requirement_states'])
                self.assertIsNone(f['scientific_failure'])
                self.assertIsNone(result['independent_scientific_truth'])
                proof=f['source_proof']
                self.assertEqual(proof['source_passage_ids'],['PAGE12'])
                self.assertTrue(proof['guidance_span']['quote'].startswith('a. Tris-EDTA'))
                self.assertIn('from Histodenz powder.',proof['guidance_span']['quote'])
                self.assertIn('after long-term storage',proof['guidance_span']['quote'])
                self.assertIn('Pre-made SeeDB2',proof['recipe_span']['quote'])
                self.assertEqual(proof['correction_binding']['source_id'],'SEEDB2_CORRECTION_2018')
                span=f['record_span']
                self.assertEqual((HEADER+literal)[span['start']:span['end']],literal)

    def test_explicit_current_powder_preparation_only_gets_prohibition(self):
        cases=['Prepare SeeDB2S from Histodenz powder using PBS.',
            'Dissolve Histodenz powder in PBS to prepare SeeDB2S.',
            '\u7528 PBS \u6eb6\u89e3 Histodenz \u7c89\u672b\u914d\u5236 SeeDB2S\u3002']
        for operation in cases:
            with self.subTest(operation=operation):
                result=self.run_case(HEADER+operation)
                self.assertEqual(result['author_recipe_nonconformance_count'],1)
                self.assertEqual(result['local_risk_count'],0)
                self.assertEqual(result['potential_conflict_count'],0)
                self.assertEqual(result['findings'][0]['typed_relation'],'AUTHOR_RECIPE_EXPLICIT_PROHIBITION')
                self.assertFalse(result['findings'][0]['changes_requirement_states'])
                self.assertIsNone(result['findings'][0]['scientific_failure'])

    def test_preexisting_stock_origin_does_not_turn_dilution_into_powder_preparation(self):
        for operation in ['Dilute pre-made SeeDB2S with PBS.', 'Dilute SeeDB2S stock using 1x PBS.',
                'Dilute existing SeeDB2S solution with PBS.']:
            with self.subTest(operation=operation):
                result=self.run_case(HEADER+operation)
                self.assertEqual(result['local_risk_count'],1)
                self.assertEqual(result['author_recipe_nonconformance_count'],0)
        # An ancestry and dilution multi-clause record remains unproved, not a prohibition.
        result=self.run_case(HEADER+'Prepare SeeDB2S from Histodenz powder with Tris-EDTA, then dilute with PBS.')
        self.assertEqual(result['author_recipe_nonconformance_count'],0)
        self.assertEqual(result['review_required_count'],1)

    def test_wash_G_and_no_PBS_do_not_borrow_S_preparation_scope_or_certify_success(self):
        cases=['Wash the sample in PBS before SeeDB2S clearing.', 'Dilute SeeDB2G with PBS.',
            'Prepare SeeDB2G from Histodenz powder using PBS.', 'Wash the sample in PBS.\nUse SeeDB2S.',
            'Prepare SeeDB2S from Histodenz powder with Tris-EDTA.', 'Dilute SeeDB2S with ddH2O.']
        for operation in cases:
            with self.subTest(operation=operation):
                result=self.run_case(HEADER+operation)
                self.assertEqual(result['local_risk_count'],0)
                self.assertEqual(result['author_recipe_nonconformance_count'],0)
                self.assertIsNone(result['scientific_validation'])
                self.assertIn('NOT_SCIENTIFIC_COMPLIANCE',result['absence_of_warning_interpretation'])
        washes=HEADER+'\n'.join(line for line in CURRENT_PROTOCOL.splitlines() if line.startswith(('1.1 ','1.2 ')))
        self.assertEqual(self.run_case(washes)['findings'],[])

    def test_conditions_negation_other_method_and_unknown_syntax_stay_review(self):
        dilution='Dilute SeeDB2S with PBS.'
        cases=[HEADER+'If required:\n'+dilution,HEADER+'### If required\n'+dilution,
            HEADER+'FDISCO:\n'+dilution,HEADER+'Do not perform the following:\n'+dilution,
            HEADER+'Do not dilute the following:\n'+dilution,
            'Do not use PBS:\n'+HEADER+dilution,
            HEADER+'### Do not prepare with PBS\n'+dilution,
            HEADER+'Do not '+dilution,HEADER+dilution+'; not performed.',
            HEADER+dilution+', if required',HEADER+'SeeDB2S and PBS are listed reagents.',
            HEADER+'Dilute SeeDB2 with PBS.',HEADER+'Dilute SeeDB2S or SeeDB2G with PBS.',
            HEADER+'In FDISCO, '+dilution,'Chosen Method: FDISCO\n'+dilution,
            dilution,HEADER+'PBS washes accompany SeeDB2S stock preparation.',
            HEADER+'Previously prepared SeeDB2S from Histodenz powder using PBS.']
        for text in cases:
            with self.subTest(text=text):
                result=self.run_case(text)
                self.assertEqual(result['local_risk_count'],0)
                self.assertEqual(result['author_recipe_nonconformance_count'],0)
                self.assertGreater(result['review_required_count'],0)
                self.assertTrue(all(f['typed_relation']=='SCOPE_INSUFFICIENT' for f in result['findings']))

    def test_no_quantified_long_term_or_failure_inference_from_actual_records(self):
        result=self.run_case(CURRENT_PROTOCOL)
        for finding in result['findings']:
            self.assertIn('LONG_TERM_STORAGE_THRESHOLD_UNSPECIFIED',finding['source_scope_guards'])
            self.assertIn('CURRENT_PRECIPITATION_AND_IMAGING_FAILURE_UNPROVEN',finding['source_scope_guards'])
        self.assertEqual(len(result['findings']),2)
        self.assertTrue(all('5.1' not in f['record_span']['quote'] for f in result['findings']))

    def test_missing_either_source_cannot_bind_or_certify_a_warning(self):
        for missing in ['SEEDB2_PROTOCOL_2018','SEEDB2_CORRECTION_2018']:
            result=self.run_case(HEADER+REAL_DILUTIONS[0],cards=[c for c in self.cards if c['id']!=missing])
            self.assertEqual(result['rule_audits'][0]['status'],'SOURCE_NOT_SELECTED')
            self.assertEqual(result['local_risk_count'],0)
            self.assertEqual(result['findings'],[])
            self.assertIsNone(result['independent_scientific_truth'])

    def test_rule_identity_policy_version_correction_and_complete_span_tamper_rejected(self):
        changes=[('source_sha256','0'*64),('source_version','other'),('method_key','CUBIC'),
            ('medium_family','SeeDB2G'),('source_passage_ids',['PAGE11']),
            ('condition_type','UNSUPPORTED'),('decision_policy','MANDATORY_FAILURE'),('corrected_by','other')]
        for field,value in changes:
            rules=deepcopy(self.rules); rules['rules'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.run_case(HEADER+REAL_DILUTIONS[0],rules=rules)
        for field,value in [('source_sha256','0'*64),('source_version','other'),
                ('source_passage_ids',[]),('corrects_source_id','OTHER')]:
            rules=deepcopy(self.rules); rules['rules'][0]['correction_binding'][field]=value
            with self.subTest(correction_field=field),self.assertRaises(ValueError):
                self.run_case(HEADER+REAL_DILUTIONS[0],rules=rules)
        # Self-consistent shorter literal spans must fail, including keeping only the prohibition.
        for owner,key in [('rule','source_guidance_span'),('rule','source_recipe_span'),
                ('correction','source_guidance_span')]:
            rules=deepcopy(self.rules); target=rules['rules'][0]
            if owner=='correction': target=target['correction_binding']
            span=target[key]; span['start']+=1; span['quote']=span['quote'][1:]
            with self.subTest(span=key,owner=owner),self.assertRaises(ValueError):
                self.run_case(HEADER+REAL_DILUTIONS[0],rules=rules)

    def test_primary_page_and_full_document_tamper_rejected_even_when_self_rehashed(self):
        for source_id,pid in [('SEEDB2_PROTOCOL_2018','PAGE12'),('SEEDB2_CORRECTION_2018','PAGE1')]:
            cards=deepcopy(self.cards); card=next(c for c in cards if c['id']==source_id)
            passage=next(p for p in card['passages'] if p['id']==pid)
            passage['start']+=1; passage['quote']=passage['quote'][1:]
            passage['sha256']=hashlib.sha256(passage['quote'].encode()).hexdigest()
            with self.subTest(page=pid),self.assertRaises(ValueError):
                self.run_case(HEADER+REAL_DILUTIONS[0],cards=cards)
            cards=deepcopy(self.cards); card=next(c for c in cards if c['id']==source_id)
            card['source_document']['text']+='changed'
            new_hash=hashlib.sha256(card['source_document']['text'].encode()).hexdigest()
            card['source_document']['sha256']=new_hash
            rules=deepcopy(self.rules)
            binding=rules['rules'][0] if pid=='PAGE12' else rules['rules'][0]['correction_binding']
            binding['source_sha256']=new_hash
            with self.subTest(document=source_id),self.assertRaises(ValueError):
                self.run_case(HEADER+REAL_DILUTIONS[0],cards=cards,rules=rules)
        cards=deepcopy(self.cards); cards[0]['source_document']['version']='other'
        with self.assertRaises(ValueError):
            self.run_case(HEADER+REAL_DILUTIONS[0],cards=cards)


if __name__=='__main__':
    unittest.main()
