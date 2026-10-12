"""Posthoc operation-record representation audit; never edits v11 or raw inputs.

Record presence and unresolved fields are separated only in a derived inventory.
Original phase, duration, repetition, scope, conditions and core coverage remain.
The original converter, project_legacy and offline scorer are always used.
"""
from __future__ import annotations
import argparse,copy,contextlib,io,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_runner_v11 as base
j=base.j;g=base.grounded;scoring=base.scoring
OUT=base.BASE/'operation_coverage_scope_diagnostic_v1'
VERSION='posthoc-operation-record-presence-v1'
def require(ok,why):
    if not ok:raise ValueError(why)
def bind(p):return base.bind(p)
def save_once(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(v if isinstance(v,bytes) else (j.canonical(v)+'\n').encode('utf8'))
def span_key(s):return (s['unit_id'],s['start'],s['end'],s['quote'],s['answer_sha256'])
def contains(a,b):return a['unit_id']==b['unit_id'] and a['start']<=b['start'] and b['end']<=a['end']
def exact_span(s,doc):
    return s['answer_sha256']==doc['answer_sha256'] and doc['text'][s['start']:s['end']]==s['quote']

def derive_audit(original,doc):
    """No keyword, answer ID, operation ID or reason-text rule chooses an unlock."""
    audit=copy.deepcopy(original);reg=g.candidate_registry(doc)
    require(original['source_binding']['candidate_registry_sha256']==reg['registry_sha256'],'ORIGINAL_REGISTRY_BINDING')
    operations=original['resolved']['operations'];rows=[]
    for row in audit['inventory']:
        if row['kind']!='operation_record_lead':continue
        lead=row['span'];require(exact_span(lead,doc),'SOURCE_LEAD_SPAN_CHANGED')
        expected=[r for r in reg['operation_candidates'] if contains(lead,r['span'])]
        returned=[o for o in operations if contains(lead,o['operation'])]
        require(all(exact_span(o['operation'],doc) for o in returned),'RETURNED_OPERATION_SPAN_CHANGED')
        keys={span_key(o['operation']) for o in returned}
        missing=[r['candidate_id'] for r in expected if span_key(r['span']) not in keys]
        # Whole source record cannot conceal an omitted second enumerated action.
        if expected:
            represented=not missing
            reason='all_enumerated_operation_extents_exactly_returned' if represented else 'enumerated_operation_extent_missing'
        else:
            # Permitted Unit fallback must represent the entire lead and have one
            # lexical action; uncertain/multi-action records remain unclassified.
            represented=any(span_key(o['operation'])==span_key(lead) for o in returned) and len(g.record_action_heads(lead['quote']))==1
            reason='exact_single_action_unit_fallback' if represented else 'no_complete_unique_record_representation'
        old=row['coverage_state'];overlap=[copy.deepcopy(r) for r in original['resolved']['coverage']['unresolved']
            if contains(r['evidence'],lead)]
        changed=old=='explicitly_unresolved' and represented
        if changed:row['coverage_state']='covered_operation_record'
        row['record_represented']=represented
        row['original_coverage_state']=old
        row['unresolved_field_records_preserved']=overlap
        rows.append({'candidate_id':row['candidate_id'],'source_span':copy.deepcopy(lead),
            'record_represented':represented,'reason':reason,'expected_operation_candidates':[r['candidate_id'] for r in expected],
            'returned_operation_ids':[o['id'] for o in returned],'missing_operation_candidates':missing,
            'original_coverage_state':old,'derived_coverage_state':row['coverage_state'],'changed':changed,
            'original_unresolved':overlap,'unresolved_reason_text_used_for_decision':False})
    require(audit['resolved']==original['resolved'],'RESOLVED_RECORD_OR_COVERAGE_CHANGED')
    require(audit['score_evidence']==original['score_evidence'],'DIRECT_EVIDENCE_CHANGED')
    audit['posthoc_record_representation_policy']={'version':VERSION,'record_audit':rows,
        'original_unresolved_preserved':True,'resolved_records_identical':True,'not_a_model_return':True,
        'original_candidate_accounting_preserved_as_historical':True,'scientific_completeness_confirmed':False}
    return audit,rows

def diagnose(raw,doc,case,step,expected_conversion=None,expected_numeric=None):
    require(g.rawsha(case['model_response'])==doc['answer_sha256'] and doc['source_id']==g.source_id_for_case(case),'EXACT_CASE_SOURCE')
    original=g.convert(raw,doc)
    if expected_conversion is not None:require(original==expected_conversion,'ORIGINAL_CONVERSION_REPLAY_MISMATCH')
    audit,rows=derive_audit(original['source_audit'],doc)
    derived=copy.deepcopy(original);derived['source_audit']=audit;derived['legacy_projection']=g.project_legacy(audit)
    derived['legacy_runner_payload']={'scores':copy.deepcopy(original['legacy_runner_payload']['scores']),
        'extraction':copy.deepcopy(derived['legacy_projection']['extraction'])}
    derived['legacy_runner_content']=g.canonical(derived['legacy_runner_payload'])
    derived['posthoc_diagnostic']={'version':VERSION,'not_a_new_model_response':True,'original_response_status_preserved':True,
        'change':'record presence separated from field uncertainty in derived inventory only','original_formulas_unchanged':True,
        'dependency_coverage_logic_changed':True,'new_model_requests':0,'expert_truth':False}
    require(original['wire_payload']==derived['wire_payload'] and original['raw_content_preserved']==derived['raw_content_preserved'],'RAW_CHANGED')
    oldext=copy.deepcopy(original['legacy_projection']['extraction']);newext=copy.deepcopy(derived['legacy_projection']['extraction'])
    oldext.pop('clearing_total_time_hours');newext.pop('clearing_total_time_hours')
    require(oldext==newext,'NON_TIME_EXTRACTION_CHANGED')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        before=scoring.score_conversion(case,original,base.BACKEND,step)
        after=scoring.score_conversion(case,derived,base.BACKEND,step)
    if expected_numeric is not None:
        require(all(scoring.same(before['metrics'][k],expected_numeric['metrics'][k]) for k in scoring.METRICS),'ORIGINAL_NUMERIC_REPLAY_MISMATCH')
    unchanged=scoring.DIRECT+['s_method','s_label','s_trans','sr','sp','Com','Cor']
    require(all(scoring.same(before['metrics'][k],after['metrics'][k]) for k in unchanged),'NON_TIME_NUMERIC_CHANGED')
    metrics=[{'metric':k,'original':before['metrics'][k],'posthoc':after['metrics'][k],
        'changed':not scoring.same(before['metrics'][k],after['metrics'][k])} for k in scoring.METRICS]
    return {'version':VERSION,'original_conversion':original,'derived_conversion':derived,
        'original_numeric':before,'posthoc_numeric':after,'record_audit':rows,'metric_comparison':metrics,
        'summary':{'status':'posthoc_diagnostic_only','changed_record_count':sum(r['changed'] for r in rows),
            'original_time_hours':original['legacy_projection']['time_calculation']['total_hours'],
            'posthoc_time_hours':derived['legacy_projection']['time_calculation']['total_hours'],
            'original_time_issues':original['legacy_projection']['time_calculation']['issues'],
            'posthoc_time_issues':derived['legacy_projection']['time_calculation']['issues'],
            'changed_metrics':[r['metric'] for r in metrics if r['changed']],
            'original_unresolved_preserved':True,'original_phase_scope_duration_repeat_conditions_preserved':True,
            'scientific_accuracy_improvement_established':False,'new_model_requests':0,'expert_confirmed':False}}

def write_result(out,result,inputs):
    require(not out.exists(),'NEW_DIAGNOSTIC_OUTPUT_ONLY');out.mkdir(parents=True)
    for key in ['original_conversion','derived_conversion','original_numeric','posthoc_numeric','record_audit','metric_comparison']:
        save_once(out/(key+'.json'),result[key])
    save_once(out/'summary.json',{**result['summary'],'version':VERSION,'inputs':inputs,
        'code':[bind(__file__),bind(g.__file__),bind(scoring.__file__),bind(base.dev7.__file__)],
        'outputs':[bind(p) for p in out.iterdir() if p.is_file()],
        'actual_command':[sys.executable,*sys.argv]})

def public_a01(out):
    # Caller scope only; the generic policy above contains no answer/record IDs.
    import cce_round2_subagent_judge_v3 as source
    plan,cases,matrix=source.validate(source.OUT)
    row=next(r for r in matrix if r['anonymous_answer_id']=='A01' and r['repeat_index']==0)
    obs=source.directory(source.OUT,row);terminal=j.read(obs/'terminal.json')
    require(terminal['status']=='success' and terminal['trial_id']==row['trial_id'] and terminal['identity']==row['identity'],'ACTUAL_TERMINAL_IDENTITY')
    base.verify_bindings(terminal['bound_artifacts']);receipt=source.checked_receipt(source.OUT,row)
    require(terminal['request_id']==receipt['request_id'],'ACTUAL_REQUEST_IDENTITY')
    dispatch=j.read(obs/'actual_dispatch_evidence.json');source.dispatch_evidence(dispatch,row)
    raw=(obs/'raw_response.txt').read_bytes();evidence=j.read(obs/'actual_return_evidence.json')
    source.submission_evidence(evidence,row,dispatch,raw)
    case=next(c for c in cases if c['case_id']==row['case_id']);doc=j.read(row['source_document']['path'])
    before=[bind(p) for p in [obs/'terminal.json',obs/'conversion.json',obs/'numeric_result.json',obs/'raw_response.txt',
        obs/'actual_return_evidence.json',obs/'actual_dispatch_evidence.json',obs/'request_receipt.json',
        Path(row['source_document']['path']),source.OUT/'plan.json',source.OUT/'matrix.json']]
    result=diagnose(raw.decode('utf8'),doc,case,row['step'],j.read(obs/'conversion.json'),j.read(obs/'numeric_result.json'))
    base.verify_bindings(before);write_result(out,result,before)
    print(j.canonical(result['summary']))

def self_check(out):
    require(not out.exists(),'NEW_SOFTWARE_OUTPUT_ONLY');out.mkdir(parents=True)
    cases,_=base.checked_cases();template=cases[0];checks=[]
    def check(name,ok):
        checks.append({'name':name,'pass':bool(ok)})
        require(ok,'SOFTWARE_CHECK:'+name)
    def fixture():
        d,p=g.synthetic_fixture();text=d['text'].replace('Synthetic clearing treatment','Incubate SYNTHETIC_SAMPLE').replace('Synthetic RI matching','Transfer SYNTHETIC_SAMPLE')
        c={'question_id':template['question_id'],'specific_question':template['specific_question'],
            'model_response':text,'references':[]};doc=g.document(c['model_response'],g.source_id_for_case(c));p['grounded_extraction']['source_id']=doc['source_id']
        reg=g.candidate_registry(doc);unit=reg['operation_candidates'][0]['span']['unit_id']
        return doc,p,c,unit
    doc,p,case,unit=fixture();step={'sr':.5,'sp':.25,'software_only':True}
    baseline=diagnose(g.canonical(p),doc,case,step)
    check('valid_input_all16_unchanged',not baseline['summary']['changed_metrics'])
    p['grounded_extraction']['coverage']['u']=[{'e':unit,'r':'A separate physical property is not specified; the operation and its duration are reported.'}]
    x=diagnose(g.canonical(p),doc,case,step)
    check('broad_unknown_field_does_not_erase_returned_operation',x['summary']['original_time_hours'] is None and x['summary']['posthoc_time_hours']==2.5)
    check('unresolved_and_all_resolved_records_exactly_retained',x['original_conversion']['source_audit']['resolved']==x['derived_conversion']['source_audit']['resolved'])
    check('direct_label_and_nontime_components_unchanged',all(not r['changed'] for r in x['metric_comparison'] if r['metric'] not in ['s_time','Eff','IA','HV']))
    write_result(out/'positive_software_only',x,[])
    for name,mutate,issue in [
        ('unknown_phase',lambda q:q['grounded_extraction']['operations'][0].update(p='unknown'),'unresolved_phase_scope'),
        ('missing_duration',lambda q:q['grounded_extraction']['operations'][0].update(d=None),'unknown_included_duration_or_repeat'),
        ('unknown_scope',lambda q:q['grounded_extraction']['operations'][0].update(s='unknown'),'unresolved_execution_scope'),
        ('core_partial',lambda q:q['grounded_extraction']['coverage'].update(c='partial'),'reported_core_operation_coverage_incomplete'),
        ('conditional_scope',lambda q:q['grounded_extraction']['operations'][0].update(s='conditional_or_future'),'conditional_operations_require_endpoint_resolution')]:
        q=copy.deepcopy(p);mutate(q);r=diagnose(g.canonical(q),doc,case,step)
        check(name+'_still_NA',r['summary']['posthoc_time_hours'] is None and any(issue in k for k in r['summary']['posthoc_time_issues']))
    q=copy.deepcopy(p);removed=q['grounded_extraction']['operations'].pop(0)
    q['grounded_extraction']['timeline']['o']=[i for i in q['grounded_extraction']['timeline']['o'] if i!=removed['i']]
    q['grounded_extraction']['precedence_edges']=[];r=diagnose(g.canonical(q),doc,case,step)
    check('omitted_operation_still_NA',r['summary']['posthoc_time_hours'] is None and 'source_action_records_not_all_classified' in r['summary']['posthoc_time_issues'])
    # The scope decision must not use the reason's keywords.
    q=copy.deepcopy(p);q['grounded_extraction']['coverage']['u'][0]['r']='Unknown RI, color, alpha, or another field.'
    r=diagnose(g.canonical(q),doc,case,step)
    check('reason_wording_irrelevant',r['summary']['posthoc_time_hours']==x['summary']['posthoc_time_hours'])
    # Two enumerated extents in one source unit: a returned first action cannot
    # erase a broad unresolved reference covering an omitted second action.
    mergedcase=copy.deepcopy(case);mergedcase['model_response']=case['model_response'].replace('\n2. ','; 2. ')
    mergeddoc=g.document(mergedcase['model_response'],g.source_id_for_case(mergedcase));q=copy.deepcopy(p)
    q['grounded_extraction']['source_id']=mergeddoc['source_id'];q['grounded_extraction']['timeline']['e']=None
    q['grounded_extraction']['precedence_edges']=[]
    reg=g.candidate_registry(mergeddoc)
    check('merged_source_fixture_has_two_same_unit_extents',len(reg['operation_candidates'])==2 and len({r['span']['unit_id'] for r in reg['operation_candidates']})==1)
    q['grounded_extraction']['operations']=q['grounded_extraction']['operations'][:1]
    q['grounded_extraction']['timeline']['o']=[q['grounded_extraction']['operations'][0]['i']]
    r=diagnose(g.canonical(q),mergeddoc,mergedcase,step)
    check('same_unit_missing_second_action_remains_NA',r['summary']['posthoc_time_hours'] is None and any(x['missing_operation_candidates'] and not x['record_represented'] for x in r['record_audit']))
    for title,addition,needle in [('unknown_repeat','2 hours; repeat several times','unknown_included_duration_or_repeat'),
                                  ('numeric_range','2-4 hours','nonunique_duration_range')]:
        altered=copy.deepcopy(case);altered['model_response']=case['model_response'].replace('for 2 hours.','for '+addition+'.')
        d=g.document(altered['model_response'],g.source_id_for_case(altered));q=copy.deepcopy(p);q['grounded_extraction']['source_id']=d['source_id']
        r=diagnose(g.canonical(q),d,altered,step)
        check(title+'_still_NA',r['summary']['posthoc_time_hours'] is None and any(needle in k for k in r['summary']['posthoc_time_issues']))
    save_once(out/'verification.json',{'status':'pass','checks':checks,'software_only':True,'new_model_requests':0,
        'actual_source_replays':0,'script':bind(__file__),'original_converter':bind(g.__file__),
        'original_numeric_adapter':bind(scoring.__file__),'actual_command':[sys.executable,*sys.argv]})
    print(j.canonical({'status':'pass','checks':len(checks),'actual_source_replays':0}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['self-check','public-a01']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();require(out.is_relative_to(OUT.resolve()),'DIAGNOSTIC_NAMESPACE_ONLY')
    if a.action=='self-check':self_check(out)
    else:public_a01(out)
if __name__=='__main__':main()
