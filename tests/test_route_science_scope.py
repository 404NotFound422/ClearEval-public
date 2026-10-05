"""Independent source-only route science scope controls; no native data or API."""
from copy import deepcopy
from pathlib import Path
import unittest

from experiments.construct_validity.evidence import make_entailment_verification, scope_leaves
from experiments.construct_validity.fidelity import text_hash
from experiments.construct_validity.requirement_scope import audit_requirement_bindings
from oeq_scientific import apply_assessment, build_context, _requirement_fidelity


def span(text, value, start=None):
    start = text.index(value) if start is None else start
    return dict(start=start, end=start + len(value), quote=value)


def support(text, value, start=None):
    if value is None:
        return dict(kind='MISSING', raw_value=None, spans=[])
    return dict(kind='EXPLICIT', raw_value=value, transform='IDENTITY',
                spans=[span(text, value, start)])


def case(*, global_scope=False, both_v1=True, requirement_id='H', identity_rule=False):
    source = 'Synthetic M v1 preserves S in 1 to 3 cm at 4 C.'
    scope = dict(objects=['S'], method='M', method_version='v1',
                 size=dict(min=1, max=3, unit='cm'), conditions=dict(temperature='4 C'))
    actual = dict(objects=['S'], method='M', method_version='v1',
                  size=dict(value=2, unit='cm'), conditions=dict(temperature='4 C'))
    card = dict(schema_version='source-grounding-v2', id='E',
                identity=dict(url='https://example.org/synthetic', version='v1',
                              publication_status='CURRENT', correction_chain=[]),
                source_document=dict(text=source, sha256=text_hash(source), version='v1',
                                     url='https://example.org/synthetic'),
                passages=[dict(id='P', **span(source, source), sha256=text_hash(source))],
                applicability=scope,
                scope_support={key:support(source,str(value)) for key,value in scope_leaves(scope).items()})
    requirement = dict(id=requirement_id, text='Synthetic M v1 preserves S.', kind='SCIENTIFIC',
                       necessary=True, evidence_ids=['E'], applicability=actual,
                       protocol_fields=['method', 'method_version'])
    if not global_scope:
        requirement.update(scope='ROUTE', route_id='A')
    if identity_rule:
        requirement['literal_rule'] = dict(type='METHOD_IDENTITY_SINGLE')
    proof = make_entailment_verification(card, ['P'], requirement['text'], actual,
        lambda data: {'relation':'SUPPORTS'}, verifier_id='SYNTHETIC_CHECKER',
        verifier_revision='fixture-v1', response_origin='SYNTHETIC_ENGINEERING_FIXTURE')
    card['entailment_verifications'] = [proof]
    left = 'Use M v1 for S at 4 C.\n'
    right = left if both_v1 else 'Use M v2 for S at 4 C.\n'
    protocol = left + right
    branches = [dict(id=route,mode='ALTERNATIVE',sample_id='unverified',
                     spans=[span(protocol,line,start)])
                for route,line,start in [('A',left,0),('B',right,len(left))]]
    steps = []
    for route, line, start in [('A',left,0),('B',right,len(left))]:
        operation = 'M v1' if 'v1' in line else 'M v2'
        steps.append(dict(id='S'+route, branch=route, phase=None, operation=operation,
                          duration_text=None, quote=line, assertion={'polarity':'AFFIRMED'},
                          field_support=dict(phase=support(protocol,None),
                                             operation=support(protocol,operation,start+4),
                                             duration_text=support(protocol,None))))
    extraction = dict(schema_version='extraction-grounding-v2',branches=branches,
                      steps=steps,labels=[],ri=[],limitations='SYNTHETIC ONLY')
    record = dict(id=requirement_id,status='SATISFIED',basis='SUPPLIED_EVIDENCE',evidence_ids=['E'],
                  quotes=['Use M'],reason='Synthetic engineering only',evidence_checks=[dict(
                      source_id='E',passage_ids=['P'],claim=requirement['text'],relation='SUPPORTS',
                      verification_id=proof['id'],applicability=deepcopy(actual),protocol_bindings={
                          'method':dict(value='M',support=support(protocol,'M',4)),
                          'method_version':dict(value='v1',support=support(protocol,'v1',6))})])
    raw = dict(extraction=extraction,assessment=dict(schema_version='judgment-grounding-v2',
               requirements=[record],limitations='Synthetic only'),objectives={},
               method_declarations=[dict(name='M',branch=route,span=span(protocol,'M',start+4))
                                    for route,start in [('A',0),('B',len(left))]])
    context = build_context({},protocol,workspace=Path('not_existing'),study_context=dict(
        requirements=[requirement],cards=[card],route_methods={} if global_scope else {'A':'M'},
        method_keys=['M'],extraction_mode='literal_fields'))
    return protocol, context, raw


class RouteScienceScopeTests(unittest.TestCase):
    def evaluate(self, protocol, context, raw):
        before=deepcopy(raw)
        result=apply_assessment(raw,context,protocol)
        self.assertEqual(raw,before)
        return result,result['requirement_results'][0]

    def test_complete_route_with_repeated_local_values_is_accepted(self):
        text,context,raw=case()
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'SATISFIED')
        self.assertEqual(record['requirement_scope_audit']['status'],'RESOLVED')
        self.assertFalse(record['source_scope']['sample_identity_certified'])
        self.assertIsNone(result['experimental_success_claim'])

    def test_same_value_explicit_other_route_offset_is_rejected(self):
        text,context,raw=case()
        raw['assessment']['requirements'][0]['evidence_checks'][0]['protocol_bindings']['method_version']['support']=support(text,'v1',text.rindex('v1'))
        result,record=self.evaluate(text,context,raw)
        self.assertTrue(result['extraction_fidelity']['scoring_eligible'])
        self.assertEqual(record['requirement_scope_audit']['status'],'RESOLVED')
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertIn('PROTOCOL_APPLICABILITY_FIELD_OUTSIDE_REQUIREMENT_SCOPE',record['guards'])

    def test_extra_binding_cannot_borrow_another_route(self):
        text,context,raw=case()
        raw['assessment']['requirements'][0]['evidence_checks'][0]['protocol_bindings']['extra']=dict(value='v1',support=support(text,'v1',text.rindex('v1')))
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertIn('PROTOCOL_APPLICABILITY_FIELD_OUTSIDE_REQUIREMENT_SCOPE',record['guards'])

    def test_mixed_local_and_other_support_spans_are_rejected(self):
        text,context,raw=case()
        binding=raw['assessment']['requirements'][0]['evidence_checks'][0]['protocol_bindings']['method']
        binding['support']['spans'].append(span(text,'M',text.rindex('M')))
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertIn('PROTOCOL_APPLICABILITY_FIELD_OUTSIDE_REQUIREMENT_SCOPE',record['guards'])

    def test_own_route_field_damage_remains_ineligible(self):
        text,context,raw=case()
        raw['extraction']['steps'][0]['field_support']['operation']=support(text,'M v1',text.rindex('M v1'))
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertFalse(record['requirement_fidelity_audit']['scoring_eligible'])
        self.assertIn('EXTRACTION_FIDELITY_REVIEW_REQUIRED',record['guards'])

    def test_other_route_field_damage_does_not_block_complete_route(self):
        text,context,raw=case()
        raw['extraction']['steps'][1]['field_support']['operation']=support(text,'M v1',4)
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'SATISFIED')
        self.assertFalse(result['extraction_fidelity']['scoring_eligible'])
        self.assertTrue(record['requirement_fidelity_audit']['scoring_eligible'])

    def test_global_keeps_full_extraction_fidelity_guard(self):
        text,context,raw=case(global_scope=True)
        self.assertEqual(self.evaluate(text,context,raw)[0]['overall'],'SATISFIED')
        raw['extraction']['steps'][1]['field_support']['operation']=support(text,'M v1',4)
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertFalse(record['requirement_fidelity_audit']['scoring_eligible'])
        self.assertEqual(record['requirement_fidelity_audit']['scope'],'GLOBAL')

    def test_unlocated_structural_issue_and_local_branch_issue_remain_blocking(self):
        text,context,raw=case()
        fidelity=self.evaluate(text,context,raw)[0]['extraction_fidelity']
        for issue in [dict(code='UNLOCATED_STRUCTURAL_ERROR'),dict(branch='A',code='BRANCH_LOCATION_UNPROVEN')]:
            with self.subTest(issue=issue):
                changed=deepcopy(fidelity)
                changed['issues'].append(issue)
                changed['scoring_eligible']=False
                self.assertFalse(_requirement_fidelity(changed,context['requirements'][0])['scoring_eligible'])

    def test_malformed_extra_binding_never_becomes_resolved(self):
        text,context,raw=case()
        resolved=self.evaluate(text,context,raw)[1]['source_scope']
        for binding in [None,[],dict(value='M',support=None),
                        dict(value='M',support=dict(kind='UNKNOWN',spans=[])),
                        dict(value='M',support=dict(kind='EXPLICIT',raw_value='M',spans={})),
                        dict(value=None,support=dict(kind='MISSING',raw_value=None,spans=[])),
                        dict(value='M',support=dict(kind='INFERRED',spans=[]))]:
            with self.subTest(binding=binding):
                record=deepcopy(raw['assessment']['requirements'][0])
                record['evidence_checks'][0]['protocol_bindings']['extra']=binding
                self.assertEqual(audit_requirement_bindings(record,resolved,text)['status'],'UNRESOLVED')
                candidate=deepcopy(raw)
                candidate['assessment']['requirements'][0]=record
                self.assertEqual(self.evaluate(text,context,candidate)[0]['overall'],'UNRESOLVED')

    def test_malformed_binding_container_and_check_remain_contract_errors(self):
        text,context,raw=case()
        scope=self.evaluate(text,context,raw)[1]['source_scope']
        for checks in [{},[None],[dict(protocol_bindings=[])]]:
            with self.subTest(checks=checks):
                with self.assertRaises(ValueError):
                    audit_requirement_bindings(dict(evidence_checks=checks),scope,text)

    def test_missing_route_facts_cannot_qualify_science(self):
        text,context,raw=case()
        raw['extraction']['steps']=raw['extraction']['steps'][1:]
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(result['overall'],'UNRESOLVED')
        self.assertFalse(record['requirement_fidelity_audit']['scoring_eligible'])

    def test_method_identity_scientific_requirement_keeps_identity_gate(self):
        text,context,raw=case(requirement_id='METHOD_IDENTITY_SCI',identity_rule=True)
        self.assertEqual(self.evaluate(text,context,raw)[0]['overall'],'SATISFIED')
        raw['method_declarations']=raw['method_declarations'][1:]
        result,record=self.evaluate(text,context,raw)
        self.assertEqual(record['effective_status'],'UNRESOLVED')
        self.assertIn('SINGLE_METHOD_IDENTITY_NOT_ESTABLISHED',record['guards'])


if __name__=='__main__':
    unittest.main()
