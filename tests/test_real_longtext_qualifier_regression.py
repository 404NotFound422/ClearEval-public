"""Regression guards for qualifier loss observed in real long-answer audits."""
from copy import deepcopy
import unittest
from experiments.construct_validity.fidelity import audit_facts, text_hash
from oeq_fidelity_impact import audit_inventory
from evaluator_integrity import FLAT_GROUNDING_VERSION, audit_flat_extraction

class QualifierCompletenessTests(unittest.TestCase):
    def fact(self,text,*,polarity=None):
        start=text.index('1 hours');fact={'field':'step.duration','value':1,'origin':'EXPLICIT',
              'start':start,'end':start+len('1 hours'),'quote':'1 hours','unit':'h'}
        if polarity is not None:fact['polarity']=polarity
        return fact
    def inventory(self,text,*,polarity=None,context=None):
        f=self.fact(text);ctx=context or text;left=text.index(ctx)
        fact={'path':'/protocol_time_hours/step_1','state':'REPORTED','value':1,'value_kind':'NUMBER','unit':'h',
              'support':{'kind':'EXPLICIT','spans':[{'start':f['start'],'end':f['end'],'quote':f['quote']}],
                         'context_span':{'start':left,'end':left+len(ctx),'quote':ctx},
                         'raw_value':'1 hours','transform':'TIME_TO_HOURS'}}
        if polarity is not None:fact['polarity']=polarity
        return {'schema_version':'oeq-fidelity-inventory-v1','original_text_sha256':text_hash(text),
          'field_scope':[fact['path']],'provenance':{'record_id':'qualifier-regression',
             'role':'CANDIDATE_EXTRACTION','independence':'NOT_APPLICABLE','assistance':[]},'facts':[fact]}
    def test_plain_numeric_fact_remains_faithful(self):
        text='1.1 Incubation (Time: 1 hours).'
        self.assertEqual(audit_facts([self.fact(text)],text)['status'],'FAITHFUL')
    def test_negated_number_requires_polarity(self):
        text='Do not perform this step: 1.1 Incubation (Time: 1 hours).'
        self.assertEqual(audit_facts([self.fact(text)],text)['status'],'UNRESOLVED')
    def test_conditional_number_requires_polarity(self):
        text='If the specimen is eligible, 1.1 Incubation (Time: 1 hours).'
        self.assertEqual(audit_facts([self.fact(text)],text)['status'],'UNRESOLVED')
    def test_explicit_matching_and_conflicting_polarity(self):
        for text,polarity in [('Do not perform this step (Time: 1 hours).','NEGATED'),
                               ('If eligible, perform this step (Time: 1 hours).','CONDITIONAL')]:
            with self.subTest(text=text):
                self.assertEqual(audit_facts([self.fact(text,polarity=polarity)],text)['status'],'FAITHFUL')
                self.assertEqual(audit_facts([self.fact(text,polarity='AFFIRMED')],text)['status'],'UNFAITHFUL')
    def test_inventory_time_transform_preserves_qualifier_unknown(self):
        for prefix in ['Do not perform this step: ','If the specimen is eligible, ']:
            text=prefix+'1.1 Incubation (Time: 1 hours).'
            result=audit_inventory(text,self.inventory(text),role='CANDIDATE_EXTRACTION')
            self.assertEqual(result['status'],'UNRESOLVED')
    def test_supplied_context_with_inherited_qualifier_is_scope_unresolved(self):
        for prefix in ['If the specimen is eligible:\n','Do not perform the following steps:\n']:
            text=prefix+'1.1 Incubation (Time: 1 hours).'
            result=audit_inventory(text,self.inventory(text,polarity='AFFIRMED'),role='CANDIDATE_EXTRACTION')
            self.assertEqual(result['status'],'UNRESOLVED')
            self.assertIn('/protocol_time_hours/step_1.context_scope',result['fact_audits'][0]['generic_audit']['unresolved_fields'])
    def test_inventory_explicit_matching_and_conflicting_polarity(self):
        for prefix,polarity in [('Do not perform this step: ','NEGATED'),
                                ('If the specimen is eligible, ','CONDITIONAL')]:
            text=prefix+'1.1 Incubation (Time: 1 hours).'
            with self.subTest(polarity=polarity):
                self.assertEqual(audit_inventory(text,self.inventory(text,polarity=polarity),role='CANDIDATE_EXTRACTION')['status'],'FAITHFUL')
                self.assertEqual(audit_inventory(text,self.inventory(text,polarity='AFFIRMED'),role='CANDIDATE_EXTRACTION')['status'],'UNFAITHFUL')
    def test_inherited_heading_with_explicit_polarity_is_not_false_mismatch(self):
        for prefix,polarity in [('If eligible:\n','CONDITIONAL'),('Do not perform the following steps:\n','NEGATED')]:
            text=prefix+'1.1 Incubation (Time: 1 hours).'
            result=audit_inventory(text,self.inventory(text,polarity=polarity),role='CANDIDATE_EXTRACTION')
            self.assertEqual(result['status'],'UNRESOLVED')
            self.assertEqual(result['issues'],[])
    def test_inherited_heading_does_not_hide_local_explicit_polarity_conflict(self):
        for text in ['If eligible:\nDo not perform this step (Time: 1 hours).',
                     'Do not perform the following steps:\nIf eligible, perform this step (Time: 1 hours).']:
            with self.subTest(text=text):
                result=audit_inventory(text,self.inventory(text,polarity='AFFIRMED'),role='CANDIDATE_EXTRACTION')
                self.assertEqual(result['status'],'UNFAITHFUL')
                self.assertTrue(result['issues'])
    def test_unrelated_later_fact_in_whole_context_does_not_negate_fact(self):
        text='1.1 Incubation (Time: 1 hours); no sample RI is reported.'
        result=audit_inventory(text,self.inventory(text),role='CANDIDATE_EXTRACTION')
        self.assertEqual(result['status'],'FAITHFUL')
    def test_unrelated_warning_outside_bound_context_does_not_negate_fact(self):
        clause='1.1 Incubation (Time: 1 hours).'
        text='Do not use unrelated protocol.\n'+clause
        result=audit_inventory(text,self.inventory(text,polarity='AFFIRMED',context=clause),role='CANDIDATE_EXTRACTION')
        self.assertEqual(result['status'],'FAITHFUL')

class FlatConditionalGuards(unittest.TestCase):
    def extraction(self,text):
        raw='1 hours';start=text.index(raw);path='/protocol_time_hours/0'
        support={'kind':'EXPLICIT','spans':[{'start':start,'end':start+len(raw),'quote':raw}],
                 'context_span':{'start':0,'end':len(text),'quote':text},
                 'raw_value':raw,'transform':'TIME_TO_HOURS'}
        return {'schema_version':FLAT_GROUNDING_VERSION,'method_name':None,'marker_dict':{},
                'clearing_total_time_hours':None,'protocol_time_hours':[1],
                'field_support':{'/method_name':{'kind':'MISSING'},'/marker_dict':{'kind':'MISSING'},
                  '/clearing_total_time_hours':{'kind':'MISSING'},path:support}}
    def test_conditional_time_requires_semantic_resolution_in_flat_bridge(self):
        for prefix in ['If eligible, ','Unless excluded, ','Provided that eligible, ','如果满足条件，']:
            text=prefix+'incubate for 1 hours'
            result=audit_flat_extraction(self.extraction(text),text)
            self.assertFalse(result['validated'])
            self.assertEqual(result['fidelity_status'],'UNRESOLVED')
            self.assertTrue(any('Conditional context' in item['detail'] for item in result['issues']))
    def test_plain_time_still_passes_flat_bridge(self):
        text='incubate for 1 hours'
        result=audit_flat_extraction(self.extraction(text),text)
        self.assertTrue(result['validated'],result['issues'])
    def test_negation_still_requires_semantic_resolution(self):
        text='Do not incubate for 1 hours'
        self.assertFalse(audit_flat_extraction(self.extraction(text),text)['validated'])

if __name__=='__main__':unittest.main()