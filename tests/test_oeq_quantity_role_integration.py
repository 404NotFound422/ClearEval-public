"""Bound source quantity roles in normal OEQ; no scientific model accuracy claims."""
from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from oeq_quantity_audit import ROLE_INPUT_VERSION,audit_quantity_role_inputs
from experiments.construct_validity.fidelity import text_hash
from evaluation_contract import json_hash


def supplied(text,claim=None):
    return {'schema_version':ROLE_INPUT_VERSION,'records':[{'record_id':'model-step-1',
        'source_span':{'start':0,'end':len(text),'quote':text},
        'claim':claim or {'per_repeat_h':.5,'repeat_count':2}}]}


class RoleInputTests(unittest.TestCase):
    def test_real_role_error_reaches_bound_field_audit(self):
        text='5.7 Action twice, each for 15 minutes.(Time: 0.5 hours)'
        out=audit_quantity_role_inputs(text,supplied(text))
        self.assertEqual(out['status_counts'],{'VIOLATED':1,'SATISFIED':1})
        self.assertEqual(out['confirmed_contradiction_count'],1)
        self.assertEqual(out['independent_reference_count'],0)
        self.assertIsNone(out['scientific_accuracy'])
        self.assertFalse(out['numerical_scores_replaced'])

    def test_valid_fragment_is_unresolved_not_complete_step_proof(self):
        text='5.7 If needed, action twice, each for 15 minutes.(Time: 0.5 hours)'
        fragment='each for 15 minutes';i=text.index(fragment)
        value=supplied(text,{'per_repeat_h':.25})
        value['records'][0]['source_span']={'start':i,'end':i+len(fragment),'quote':fragment}
        out=audit_quantity_role_inputs(text,value)
        self.assertEqual(out['status_counts'],{'UNRESOLVED':1})
        self.assertEqual(out['records'][0]['audit']['checks'][0]['reason'],'COMPLETE_ORIGINAL_NUMBERED_STEP_NOT_BOUND')

    def test_invalid_claim_rejected_even_when_source_role_unknown(self):
        text='1.1 Action until ready.'
        for claim in [{'per_repeat_h':True},{'total_elapsed_h':-1},{'range_h':[2,1]},
                      {'range_h':[0,float('inf')]},{'interval_h':'2 hours'}]:
            with self.subTest(claim=claim),self.assertRaises(ValueError):
                audit_quantity_role_inputs(text,supplied(text,claim))

    def test_duplicate_records_or_fields_cannot_inflate_metrics(self):
        text='1.1 Action for 2 hours.';value=supplied(text,{'total_elapsed_h':2})
        value['records'].append(deepcopy(value['records'][0]))
        with self.assertRaises(ValueError):audit_quantity_role_inputs(text,value)
        value['records'][1]['record_id']='another-name'
        with self.assertRaises(ValueError):audit_quantity_role_inputs(text,value)

    def test_bundle_validation_precedes_teacher_and_binds_full_original(self):
        from oeq_robustness import INPUT_VERSION,SET_VERSION,select_bundle
        question={'question_id':1,'question':'A fixed engineering task.'}
        text='1.1 Action for 2 hours.'
        bundle={'schema_version':INPUT_VERSION,'question_sha256':json_hash(question),
                'protocol_sha256':text_hash(text),'quantity_role_claims':supplied(text,{'total_elapsed_h':True})}
        with self.assertRaises(ValueError):select_bundle({'schema_version':SET_VERSION,'entries':[bundle]},question,text)
        bundle['quantity_role_claims']=supplied(text,{'total_elapsed_h':2})
        self.assertEqual(select_bundle({'schema_version':SET_VERSION,'entries':[bundle]},question,text),bundle)
        with self.assertRaises(ValueError):
            from oeq_robustness import validate_bundle
            validate_bundle(bundle,question,text+' Changed.')


class NormalRoleFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_oeq_saves_role_violation_counts_and_rejects_rehashed_tamper(self):
        import OEQ_run_grading_new as runner
        import test_oeq_benchmark_integration as fixture
        from oeq_robustness import INPUT_VERSION,SET_VERSION,is_report_complete
        from benchmark_scoring import _record_hash
        from results.aggregate_oeq import aggregate_file
        helper=fixture.BenchmarkActualCliTests()
        saved={n:getattr(runner,n) for n in ('QUESTION_FILE','DEMAND_PROFILE','DEMAND_FILE','DEMAND_MANIFEST','OEQ_SCORE_DIR','OEQ_OUTPUT_DIR')}
        try:
            runner.DEMAND_PROFILE='current-proposal';runner.configure_question_snapshot(fixture.CURRENT)
            question=runner._QUESTION_LIST[0];helper.qid=question['question_id']
            line='5.7 Action twice, each for 15 minutes.(Time: 0.5 hours)'
            protocol='**Chosen Method:** CUBIC\n'+line+'\n'+('Fixed offline engineering observation. '*20)
            role=supplied(line);start=protocol.index(line)
            role['records'][0]['source_span']={'start':start,'end':start+len(line),'quote':line}
            with tempfile.TemporaryDirectory() as tmp:
                sdk,args,path,_=helper.fixture(tmp,protocol=protocol)
                bundle={'schema_version':INPUT_VERSION,'question_sha256':json_hash(question),
                        'protocol_sha256':text_hash(protocol),'quantity_role_claims':role}
                inp=Path(tmp)/'roles.json';inp.write_text(json.dumps({'schema_version':SET_VERSION,'entries':[bundle]}),encoding='utf-8')
                with patch.dict('sys.modules',{'ollama':SimpleNamespace(Client=sdk)}):
                    self.assertEqual(await runner.main(args+['--robustness-inputs',str(inp)]),0)
                ev=json.loads(path.read_text('utf-8'))[0]['evaluation']
                self.assertEqual(ev['robustness_diagnostics']['quantity_role_diagnostics']['status_counts'],{'VIOLATED':1,'SATISFIED':1})
                self.assertTrue(is_report_complete(ev))
                summary=aggregate_file(path)['robustness_summary']
                self.assertEqual(summary['quantity_role_field_check_count'],2)
                self.assertEqual(summary['quantity_role_status_counts'],{'VIOLATED':1,'SATISFIED':1})
                self.assertEqual(summary['answers_with_quantity_role_contradiction'],1)
                self.assertEqual(sdk.calls,['candidate','judge'])
                self.assertIsNone(ev['official_scores'])
                forged=deepcopy(ev)
                forged['robustness_diagnostics']['quantity_role_diagnostics']['records'][0]['audit']['checks'][0]['status']='SATISFIED'
                forged['robustness_diagnostics_sha256']=json_hash(forged['robustness_diagnostics'])
                forged['benchmark_record_sha256']=_record_hash(forged)
                self.assertFalse(is_report_complete(forged))
        finally:
            for n,v in saved.items():setattr(runner,n,v)
            runner.configure_question_snapshot(saved['QUESTION_FILE'])



class ProductDurationRoleTests(unittest.TestCase):
    def audit(self,text,claim):
        return audit_quantity_role_inputs(text,supplied(text,claim))['records'][0]['audit']

    def checks(self,text,claim):
        return {row['role']:row for row in self.audit(text,claim)['checks']}

    def test_range_product_preserves_bounds_and_scalar_uncertainty(self):
        text='1.1 Action (Time: 2 × 1.5–2 h)'
        out=self.checks(text,{'per_repeat_h':[1.5,2],'repeat_count':2,'total_elapsed_h':[3,4]})
        self.assertEqual({v['status'] for v in out.values()},{'SATISFIED'})
        out=self.checks(text,{'per_repeat_h':1.75})
        self.assertEqual(out['per_repeat_h']['status'],'UNRESOLVED')
        self.assertEqual(out['per_repeat_h']['reason'],'SOURCE_RANGE_DOES_NOT_CERTIFY_EXACT_ROLE_VALUE')

    def test_unicode_source_duration_ranges(self):
        for dash in ('–','—','至','到'):
            with self.subTest(dash=dash):
                out=self.checks(f'1.1 Action (Time: 2{dash}4 h)',{'range_h':[2,4]})
                self.assertEqual(out['range_h']['status'],'SATISFIED')

    def test_declared_total_and_product_overlap_does_not_certify_elapsed(self):
        from extract_clearing_time import audit_duration_scope
        text='1.1 Action (Time: 6 × 6–12 h；总计3–4 days)'
        raw=audit_duration_scope(text)
        self.assertEqual(raw['product_declared_total_relation'],'OVERLAPPING_DIFFERENT_BOUNDS')
        self.assertIsNone(raw['total'])
        out=self.checks(text,{'per_repeat_h':[6,12],'repeat_count':6,'range_h':[72,96],'total_elapsed_h':72})
        self.assertEqual(out['per_repeat_h']['status'],'SATISFIED')
        self.assertEqual(out['repeat_count']['status'],'SATISFIED')
        self.assertEqual(out['range_h']['status'],'SATISFIED')
        self.assertEqual(out['total_elapsed_h']['status'],'UNRESOLVED')

    def test_product_plus_extra_action_cannot_certify_full_step_elapsed(self):
        text='1.1 Action 2 × 1.5–2 h then wash for 1 h.'
        out=self.checks(text,{'per_repeat_h':[1.5,2],'repeat_count':2,'total_elapsed_h':[3,4]})
        self.assertEqual(out['per_repeat_h']['status'],'SATISFIED')
        self.assertEqual(out['repeat_count']['status'],'SATISFIED')
        self.assertEqual(out['total_elapsed_h']['status'],'UNRESOLVED')

    def test_metadata_and_interval_do_not_certify_product_elapsed(self):
        for text,claim in [
            ('1.1 Action 2 × 2 h. (Time: 9 hours)',{'per_repeat_h':2,'repeat_count':2,'total_elapsed_h':4}),
            ('1.1 Action 2 × 2 h every 8 h.',{'per_repeat_h':2,'repeat_count':2,'total_elapsed_h':4,'interval_h':8})]:
            with self.subTest(text=text):
                out=self.checks(text,claim)
                self.assertEqual(out['per_repeat_h']['status'],'SATISFIED')
                self.assertEqual(out['repeat_count']['status'],'SATISFIED')
                self.assertEqual(out['total_elapsed_h']['status'],'UNRESOLVED')
                if 'interval_h' in out:self.assertEqual(out['interval_h']['status'],'SATISFIED')

    def test_multiple_products_remain_unresolved(self):
        out=self.checks('1.1 Action 2 × 2 h then 3 × 1 h.',{'per_repeat_h':2,'repeat_count':2,'total_elapsed_h':7})
        self.assertEqual({v['status'] for v in out.values()},{'UNRESOLVED'})

if __name__=='__main__':unittest.main()