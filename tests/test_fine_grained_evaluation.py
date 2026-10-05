"""Boundary regressions for guarded matching and strict error event metrics."""
from copy import deepcopy
import unittest
from experiments.construct_validity.answer_matching import summarize_answer_matching
from experiments.construct_validity.fidelity import text_hash
from experiments.construct_validity.fine_grained_metrics import audit_fact_source_bindings, error_event_metrics


def req(rid, route=None, necessary=True):
    out = dict(id=rid, kind='TEXT', text=rid, necessary=necessary, evidence_ids=[])
    if route is not None:
        out.update(scope='ROUTE', route_id=route)
    return out


def summary(requirements, states, routes, overall, **kwargs):
    return summarize_answer_matching(requirements,
        [dict(id=k, effective_status=v) for k, v in states.items()],
        [dict(route_id=k, status=v) for k, v in routes.items()], overall, 'a'*64, **kwargs)


class CandidateEndpointTests(unittest.TestCase):
    def test_one_satisfied_candidate_does_not_hide_failed_other_candidate(self):
        out = summary([req('a','A'),req('b','B')], {'a':'SATISFIED','b':'VIOLATED'},
                      {'A':'SATISFIED','B':'VIOLATED'}, 'SATISFIED')
        self.assertEqual(out['any_evaluated_candidate_status'],'SATISFIED')
        self.assertEqual(out['all_evaluated_candidates_status'],'VIOLATED')
        self.assertIsNone(out['all_recommended_candidates_status'])
        self.assertFalse(out['candidate_roles_certified'])

    def test_global_failure_blocks_locally_satisfied_candidates(self):
        out = summary([req('g'),req('a','A')], {'g':'VIOLATED','a':'SATISFIED'},
                      {'A':'SATISFIED'}, 'VIOLATED')
        self.assertEqual(out['matched_declared_candidate_ids'],[])
        self.assertEqual(out['locally_satisfied_declared_candidate_ids'],['A'])
        self.assertEqual(out['any_evaluated_candidate_status'],'VIOLATED')

    def test_unknown_candidate_remains_visible_when_another_satisfies(self):
        out = summary([req('a','A'),req('b','B')], {'a':'SATISFIED','b':'UNRESOLVED'},
                      {'A':'SATISFIED','B':'UNRESOLVED'}, 'SATISFIED')
        self.assertEqual(out['all_evaluated_candidates_status'],'UNRESOLVED')
        self.assertEqual(out['candidate_necessary_failures']['B'],[])

    def test_no_declared_candidate_is_not_invented(self):
        out = summary([req('g')],{'g':'SATISFIED'},{},'SATISFIED')
        self.assertIsNone(out['any_evaluated_candidate_status'])
        self.assertIsNone(out['all_evaluated_candidates_status'])

    def test_inconsistent_overall_sat_is_rejected(self):
        with self.assertRaises(ValueError):
            summary([req('g')],{'g':'VIOLATED'},{},'SATISFIED')

    def test_inconsistent_candidate_sat_is_rejected(self):
        with self.assertRaises(ValueError):
            summary([req('a','A')],{'a':'VIOLATED'},{'A':'SATISFIED'},'UNRESOLVED')

    def test_custom_restriction_is_respected_without_rejecting_correct_veto(self):
        requirements=[req('g'),req('extra',necessary=False)]
        states={'g':'SATISFIED','extra':'VIOLATED'}
        out=summary(requirements,states,{},'VIOLATED',requested_formula='extra')
        self.assertEqual(out['contract_status'],'VIOLATED')
        with self.assertRaises(ValueError):
            summary(requirements,states,{},'SATISFIED',requested_formula='extra')

    def test_identity_guard_may_conservatively_lower_sat(self):
        out=summary([req('a','A')],{'a':'SATISFIED'},{'A':'UNRESOLVED'},'UNRESOLVED')
        self.assertEqual(out['contract_status'],'UNRESOLVED')
        self.assertEqual(out['consistency_audit']['formula_status_before_candidate_guards'],'SATISFIED')
        self.assertFalse(out['consistency_audit']['negative_or_unknown_caller_decisions_recomputed'])

    def test_cross_candidate_requirements_do_not_make_a_witness(self):
        requirements=[req('a1','A'),req('a2','A'),req('b1','B'),req('b2','B')]
        out=summary(requirements,{'a1':'SATISFIED','a2':'VIOLATED','b1':'VIOLATED','b2':'SATISFIED'},
                    {'A':'VIOLATED','B':'VIOLATED'},'VIOLATED')
        self.assertEqual(out['matched_declared_candidate_ids'],[])
        self.assertEqual(out['any_evaluated_candidate_status'],'VIOLATED')

    def test_optional_failures_do_not_block_candidate_endpoints(self):
        out=summary([req('a','A'),req('optional',necessary=False)],
                    {'a':'SATISFIED','optional':'VIOLATED'},{'A':'SATISFIED'},'SATISFIED')
        self.assertEqual(out['all_evaluated_candidates_status'],'SATISFIED')


def unit(case_id, group='source_A'):
    return dict(case_id=case_id,source_group=group,task_id='T',answer_id='R',candidate_id='A',requirement_id=case_id)


def reference(plan, status='VIOLATED', necessary=True):
    return dict(plan,status=status,necessary=necessary,reference_basis='ENGINEERING_CONTROL',
                model_proposed_reference=False,entity_id='entity',condition_scope='local',
                polarity='contradicts',cause_id='cause')


class FineGrainedMetricTests(unittest.TestCase):
    def test_wrong_cause_binding_and_optional_status_not_credited_as_critical_detection(self):
        plans=[unit(str(i),'source_A' if i<2 else 'source_B') for i in range(7)]
        refs=[reference(p) for p in plans]
        refs[4]['status']='SATISFIED'; refs[5]['necessary']=False
        refs[6]['model_proposed_reference']=True
        preds=[deepcopy(r) for r in refs]
        preds[1]['cause_id']='wrong'; preds[2]['condition_scope']='other-candidate'
        preds[3]['status']=None; preds[4]['status']='VIOLATED'; preds[6]['status']='SATISFIED'
        out=error_event_metrics(plans,preds,refs,reference_basis='ENGINEERING_CONTROL')
        self.assertEqual(out['strict_error_event_recall']['value'],1/4)
        self.assertEqual(out['strict_error_event_precision']['value'],1/4)
        self.assertEqual(out['status_only_error_recall']['value'],3/4)
        self.assertEqual(out['technical_failure']['value'],1/7)
        self.assertEqual(out['reference_coverage']['value'],6/7)
        self.assertEqual(out['counts']['cause_or_binding_mismatch'],2)
        self.assertEqual(out['source_macro_strict_recall'],.25)

    def test_wrong_candidate_is_not_a_true_positive_even_with_correct_error_label(self):
        p=unit('x'); ref=reference(p); pred=dict(ref,candidate_id='B')
        out=error_event_metrics([p],[pred],[ref],reference_basis='ENGINEERING_CONTROL')
        self.assertEqual(out['counts']['strict_tp'],0)
        self.assertEqual(out['counts']['strict_fp'],1)
        self.assertEqual(out['counts']['strict_fn'],1)

    def test_abstention_and_missing_prediction_stay_in_frozen_denominators(self):
        plans=[unit('x'),unit('y')]; refs=[reference(p) for p in plans]
        pred=dict(refs[0],status='UNRESOLVED')
        out=error_event_metrics(plans,[pred],refs,reference_basis='ENGINEERING_CONTROL')
        self.assertEqual(out['strict_error_event_recall']['denominator'],2)
        self.assertEqual(out['technical_failure']['value'],.5)
        self.assertEqual(out['decisive_coverage']['value'],0)
        self.assertIsNone(out['strict_error_event_precision']['value'])

    def test_model_proposal_cannot_become_independent_reference(self):
        p=unit('x'); ref=reference(p)
        ref.update(reference_basis='INDEPENDENT_REVIEW',independently_reviewed=True,
                   review_id='claimed',model_proposed_reference=True)
        out=error_event_metrics([p],[ref],[ref])
        self.assertEqual(out['reference_coverage']['value'],0)
        self.assertIsNone(out['strict_error_event_recall']['value'])

    def test_unknown_reference_is_not_a_confirmed_false_positive(self):
        p=unit('x'); ref=reference(p,status='UNRESOLVED'); pred=dict(ref,status='VIOLATED')
        out=error_event_metrics([p],[pred],[ref],reference_basis='ENGINEERING_CONTROL')
        self.assertEqual(out['counts']['unknown_reference'],1)
        self.assertEqual(out['counts']['strict_fp'],0)
        self.assertIsNone(out['strict_error_event_precision']['value'])
        self.assertEqual(out['reference_coverage']['value'],1)

    def test_empty_or_null_fact_source_ids_are_invalid(self):
        text='abc'; package=dict(sources=[dict(source_id=None,answer_sha256=text_hash(text))],facts=[])
        with self.assertRaises(ValueError): audit_fact_source_bindings(package,{None:text})
        package=dict(sources=[dict(source_id='R',answer_sha256=text_hash(text))],facts=[dict(fact_id='',source_id='R')])
        with self.assertRaises(ValueError): audit_fact_source_bindings(package,{'R':text})

    def test_duplicate_and_unplanned_rows_are_not_silently_deduplicated(self):
        p=unit('x')
        with self.assertRaises(ValueError):error_event_metrics([p,p],[],[])
        with self.assertRaises(ValueError):error_event_metrics([p],[dict(reference(unit('y')))],[])

    def test_source_binding_does_not_certify_a_semantic_value(self):
        text='甲目标→通道A'; sid='R'
        package=dict(sources=[dict(source_id=sid,answer_sha256=text_hash(text))], facts=[
            dict(fact_id='f',source_id=sid,type='TARGET_ENTITY',model_proposed_reference=True,
                 scientific_gold=False,canonical_value_or_object={'entity':'deliberately unverified'},
                 field_spans=[dict(field='entity',start=0,end=3,quote=text[:3],context=text,
                                  context_start=0,context_end=len(text))])])
        out=audit_fact_source_bindings(package,{sid:text})
        self.assertEqual(out['field_span_binding']['value'],1)
        self.assertIsNone(out['extraction_semantic_accuracy'])
        self.assertIsNone(out['full_content_recall'])
        tampered=deepcopy(package);tampered['facts'][0]['field_spans'][0]['quote']='错'
        self.assertEqual(audit_fact_source_bindings(tampered,{sid:text})['field_span_binding']['value'],0)

    def test_changed_complete_answer_invalidates_otherwise_matching_local_quote(self):
        text='abc'; package=dict(sources=[dict(source_id='R',answer_sha256=text_hash(text))],facts=[
            dict(fact_id='f',source_id='R',type='SCOPE',field_spans=[
                dict(field='f',start=0,end=1,quote='a',context=text,context_start=0,context_end=3)])])
        self.assertEqual(audit_fact_source_bindings(package,{'R':'abcd'})['fact_binding']['value'],0)


if __name__=='__main__': unittest.main()