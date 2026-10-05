"""Local quantity scope, full-source preservation and normal OEQ integration."""
from copy import deepcopy
from pathlib import Path
import json,unittest
from oeq_quantity_audit import audit_quantity_scope,sum_declared_duration_bounds
from extract_clearing_time import audit_duration_scope
from experiments.construct_validity.fidelity import text_hash


def bound_time(protocol,raw,hours):
    start=protocol.index(raw)
    return dict(method_name='iDISCO+',marker_dict={},clearing_total_time_hours=None,
        protocol_time_hours=[hours],field_support={'/protocol_time_hours/0':dict(kind='EXPLICIT',
            spans=[dict(start=start,end=start+len(raw),quote=raw)],
            context_span=dict(start=0,end=len(protocol),quote=protocol),raw_value=raw,transform='TIME_TO_HOURS')})


class QuantityScopeTests(unittest.TestCase):
    def test_original_r16_line_detects_dropped_repeat_even_if_raw_number_occurs(self):
        line='5.5 Incubation with methanol twice, each for 1 hour.(Temperature: RT, Time: 1 hours)'
        out=audit_quantity_scope(line,bound_time(line,'1 hours',1))
        self.assertEqual(out['records'][0]['reported_local_elapsed_bounds_h'],[2,2])
        self.assertEqual(out['flat_time_field_checks'][0]['status'],'CONTRADICTED_LOCAL_ELAPSED')
        self.assertIsNone(out['full_protocol_total_h'])
        self.assertFalse(out['numerical_scores_replaced'])

    def test_metadata_each_has_bounded_repeat_witness(self):
        line='3.4 Incubation with THF for 3 cycles.(Temperature: 4 ℃, Time: 12 hours each)'
        out=audit_duration_scope(line)
        self.assertEqual(out['total']['hours'],36)
        start,end=out['total']['span'];self.assertEqual(line[start:end],out['total']['quote'])
        self.assertEqual(audit_quantity_scope(line)['records'][0]['reported_local_elapsed_bounds_h'],[36,36])

    def test_repeat_metadata_without_each_does_not_guess(self):
        line='3.4 Incubation with THF for 3 cycles.(Temperature: 4 ℃, Time: 12 hours)'
        self.assertEqual(audit_duration_scope(line)['status'],'AMBIGUOUS')

    def test_total_metadata_not_double_multiplied(self):
        line='5.7 Incubate twice, each for 15 minutes.(Temperature: RT, Time: 0.5 hours)'
        out=audit_quantity_scope(line,bound_time(line,'0.5 hours',.5))
        self.assertEqual(out['flat_time_field_checks'][0]['status'],'CONSISTENT_LOCAL_ELAPSED_BOUNDS')

    def test_interval_remains_distinct_from_total_window(self):
        line='4.2 Wash for 6 hours, changing solution every 2 hours.(Temperature: RT, Time: 6 hours)'
        out=audit_quantity_scope(line,bound_time(line,'6 hours',6))
        self.assertEqual(out['records'][0]['local_duration_relation']['interval']['hours'],2)
        self.assertEqual(out['records'][0]['reported_local_elapsed_bounds_h'],[6,6])

    def test_range_preserved_instead_of_assuming_metadata_endpoint_is_only_value(self):
        line='6.1 Incubation for 15-30 minutes.(Temperature: RT, Time: 0.5 hours)'
        out=audit_quantity_scope(line)
        self.assertEqual(out['records'][0]['reported_local_elapsed_bounds_h'],[.25,.5])

    def test_condition_and_clipped_context_abstain(self):
        line='5.5 If needed, incubate twice, each for 1 hour.(Temperature: RT, Time: 1 hours)'
        self.assertEqual(audit_quantity_scope(line,bound_time(line,'1 hours',1))['flat_time_field_checks'][0]['status'],'UNRESOLVED')
        line='5.5 Incubate twice, each for 1 hour.(Temperature: RT, Time: 1 hours)'
        flat=bound_time(line,'1 hours',1);flat['field_support']['/protocol_time_hours/0']['context_span']=deepcopy(flat['field_support']['/protocol_time_hours/0']['spans'][0])
        self.assertEqual(audit_quantity_scope(line,flat)['flat_time_field_checks'][0]['status'],'UNRESOLVED')

    def test_exact_source_position_and_phase_heading_survive_unicode_and_crlf(self):
        text='前言😀\r\n5 Dehydration\r\n5.5 Incubate twice, each for 1 hour.\r\n'
        out=audit_quantity_scope(text);row=out['records'][0]
        self.assertEqual(text[row['source_span']['start']:row['source_span']['end']],row['source_span']['quote'])
        self.assertEqual(row['source_section']['quote'],'5 Dehydration')
        self.assertEqual(out['protocol_sha256'],text_hash(text))

    def test_declared_sum_excludes_unknown_and_rejects_duplicate_membership(self):
        text='5.1 Incubate for 1 hour.\n5.2 Incubate twice, each for 1 hour.\n'
        ledger=audit_quantity_scope(text);ids=[r['source_record_id'] for r in ledger['records']]
        result=sum_declared_duration_bounds(ledger,ids,protocol=text)
        self.assertEqual(result['bounds_h'],[3,3]);self.assertFalse(result['phase_and_candidate_membership_certified'])
        with self.assertRaises(ValueError):sum_declared_duration_bounds(ledger,[ids[0],ids[0]],protocol=text)
        ledger=audit_quantity_scope('5.1 Incubate until ready.\n')
        self.assertEqual(sum_declared_duration_bounds(ledger,[ledger['records'][0]['source_record_id']],protocol='5.1 Incubate until ready.\n')['status'],'UNRESOLVED')

    def test_negation_and_leading_condition_never_become_elapsed_contradictions(self):
        for text in ['1.1 Do not incubate for 2 hours.','If ready:\n1.1 Incubate for 2 hours.']:
            for value in (0,2):
                ledger=audit_quantity_scope(text,bound_time(text,'2 hours',value))
                self.assertEqual(ledger['flat_time_field_checks'][0]['status'],'UNRESOLVED')
                self.assertEqual(sum_declared_duration_bounds(ledger,[ledger['records'][0]['source_record_id']],protocol=text)['status'],'UNRESOLVED')

    def test_justification_mention_does_not_open_protocol_execution_condition(self):
        text='**Justification:** FP are not specified, and staining works without loss under certain conditions.\n1.1 Incubate for 2 hours.'
        ledger=audit_quantity_scope(text,bound_time(text,'2 hours',2))
        self.assertEqual(ledger['records'][0]['source_control_guards'],[])
        self.assertEqual(ledger['flat_time_field_checks'][0]['status'],'CONSISTENT_LOCAL_ELAPSED_BOUNDS')

    def test_metadata_aggregate_cannot_be_claimed_as_per_repeat_duration(self):
        from oeq_quantity_audit import audit_local_duration_claim
        text='5.7 Incubate twice, each for 15 minutes.(Temperature: RT, Time: 0.5 hours)'
        span={'start':0,'end':len(text),'quote':text}
        out=audit_local_duration_claim(text,span,{'per_repeat_h':.5,'repeat_count':2,'total_elapsed_h':.5})
        self.assertEqual([c['status'] for c in out['checks']],['VIOLATED','SATISFIED','SATISFIED'])
        self.assertIsNone(out['task_necessity'])
        self.assertIsNone(out['scientific_truth'])

    def test_scope_condition_does_not_cross_explicit_candidate_boundary(self):
        text='Candidate A\nIf ready:\n1.1 Incubate for 2 hours.\nCandidate B\n1.1 Incubate for 2 hours.'
        rows=audit_quantity_scope(text)['records']
        self.assertTrue(rows[0]['source_control_guards']);self.assertEqual(rows[1]['source_control_guards'],[])

    def test_markdown_candidate_boundary_preserves_local_condition(self):
        for heading in [('**Candidate A**','**Candidate B**'),('### Candidate A','### Candidate B')]:
            text=heading[0]+'\nIf ready:\n1.1 Incubate for 2 hours.\n'+heading[1]+'\n1.1 Incubate for 2 hours.'
            rows=audit_quantity_scope(text)['records']
            self.assertTrue(rows[0]['source_control_guards']);self.assertEqual(rows[1]['source_control_guards'],[])

    def test_arbitrary_step_word_cannot_bind_time_and_sum_rejects_tampered_ledger(self):
        text='1.1 Incubate for 2 hours.'
        self.assertEqual(audit_quantity_scope(text,bound_time(text,'Incubate',2))['flat_time_field_checks'][0]['status'],'UNRESOLVED')
        ledger=audit_quantity_scope(text);ledger['records'][0]['reported_local_elapsed_bounds_h']=[999,999]
        with self.assertRaises(ValueError):sum_declared_duration_bounds(ledger,[ledger['records'][0]['source_record_id']],protocol=text)

    def test_nested_witness_uses_explicit_local_basis_and_verified_absolute_span(self):
        text='前言😀\n1.1 Incubate twice, each for 2 hours.'
        row=audit_quantity_scope(text)['records'][0];audit=row['local_duration_relation']
        self.assertEqual(audit['offset_basis'],'STEP_LOCAL_UNICODE_CODEPOINTS')
        for item in audit.values():
            if isinstance(item,dict) and 'protocol_span' in item:
                span=item['protocol_span'];self.assertEqual(text[span['start']:span['end']],span['quote'])

    def test_repeated_step_number_does_not_join_different_candidate_sections(self):
        text='1 Candidate A\n1.1 Incubate for 1 hour.\n2 Candidate B\n1.1 Incubate for 2 hours.'
        records=audit_quantity_scope(text)['records']
        self.assertNotEqual(records[0]['source_record_id'],records[1]['source_record_id'])
        self.assertIsNone(records[0]['candidate_identity'])


class NormalMainFlowQuantityTests(unittest.IsolatedAsyncioTestCase):
    async def test_quantity_audit_saved_and_counted_in_normal_oeq_without_extra_judge(self):
        from types import SimpleNamespace
        import tempfile
        from unittest.mock import patch
        import OEQ_run_grading_new as runner
        import test_oeq_benchmark_integration as fixture
        from oeq_robustness import is_report_complete
        from results.aggregate_oeq import aggregate_file
        helper=fixture.BenchmarkActualCliTests()
        saved={name:getattr(runner,name) for name in ('QUESTION_FILE','DEMAND_PROFILE','DEMAND_FILE','DEMAND_MANIFEST','OEQ_SCORE_DIR','OEQ_OUTPUT_DIR')}
        try:
            runner.DEMAND_PROFILE='current-proposal';runner.configure_question_snapshot(fixture.CURRENT)
            helper.qid=runner._QUESTION_LIST[0]['question_id']
            protocol='**Chosen Method:** CUBIC\n5 Dehydration\n5.5 Incubate twice, each for 1 hour. '+('Existing offline SDK fixture. '*20)
            with tempfile.TemporaryDirectory() as tmp:
                sdk,args,path,_=helper.fixture(tmp,protocol=protocol)
                with patch.dict('sys.modules',{'ollama':SimpleNamespace(Client=sdk)}):
                    self.assertEqual(await runner.main(args),0)
                ev=json.loads(path.read_text(encoding='utf-8'))[0]['evaluation']
                diag=ev['robustness_diagnostics']['quantity_scope_diagnostics']
                self.assertEqual(diag['records'][0]['reported_local_elapsed_bounds_h'],[2,2])
                self.assertTrue(is_report_complete(ev))
                self.assertEqual(aggregate_file(path)['robustness_summary']['quantity_source_record_count'],1)
                self.assertEqual(sdk.calls,['candidate','judge'])
                forged=deepcopy(ev);forged['robustness_diagnostics']['quantity_scope_diagnostics']['records'][0]['reported_local_elapsed_bounds_h']=[999,999]
                from evaluation_contract import json_hash
                from benchmark_scoring import _record_hash
                forged['robustness_diagnostics_sha256']=json_hash(forged['robustness_diagnostics']);forged['benchmark_record_sha256']=_record_hash(forged)
                self.assertFalse(is_report_complete(forged))
        finally:
            for name,value in saved.items():setattr(runner,name,value)
            runner.configure_question_snapshot(saved['QUESTION_FILE'])


if __name__=='__main__':unittest.main()