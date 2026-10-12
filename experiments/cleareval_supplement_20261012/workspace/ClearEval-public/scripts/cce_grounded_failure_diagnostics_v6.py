"""Offline diagnosis of all five terminal v6 development returns; no repair or call.

Execution requires the completed batch analysis and frozen independent fact
audit. Individual field probes never replace a failed conversion or score.
"""
from __future__ import annotations
import argparse,copy,hashlib,inspect,json,math,re,socket,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_extraction_v6 as g
import cce_audit_grounded_facts_v6 as fc
BASE=ROOT/'artifacts/cce_validation/optimizer_20261010';BATCH=BASE/'grounded_development_v6'
OUT=BASE/'grounded_v6_failure_diagnostics_v1'
MODULE_SHA='a2f79460464b03463f92910d3782abdbe35918e27a568eb94cf805f40786cd57'
CHECKER_SHA='6cdd65ebf1e34530e529e0be3e6185c1bf89f542af6a7e3dc35bcf3868f53634'
LEDGER=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl';IDS=['A01','A02','A03','A04','A05']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def require(v,s):
    if not v:raise ValueError(s)
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def probe(call):
    try:return {'passed':True,'value':call()}
    except Exception as exc:return {'passed':False,'error_type':type(exc).__name__,'error':str(exc)}
def save(p,v):
    with Path(p).open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def numeric_states(values):
    return {k:('NA' if not finite(v) else 'known_zero' if v==0 else 'numeric_nonzero') for k,v in values.items()}
def refs(value,path='$'):
    if isinstance(value,dict):
        keys=set(value)
        if 'candidate_id' in keys:yield path,('CandidateRef_'+str(value['candidate_id'])[:1]),value
        elif 'clause_id' in keys:yield path,'ClauseRef_Q',value
        elif 'unit_id' in keys:yield path,'UnitRef' if keys=={'unit_id'} else 'ForbiddenRawOrMalformedRef',value
        else:
            for k,v in value.items():yield from refs(v,path+'.'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from refs(v,f'{path}[{i}]')
def offset_checks(value,doc,path='$'):
    rows=[]
    if isinstance(value,dict):
        if all(k in value for k in ['start','end','quote']):
            a,b=value['start'],value['end'];quote=value['quote'];valid=type(a) is int and type(b) is int and isinstance(quote,str) and 0<=a<=b<=len(doc['text']) and doc['text'][a:b]==quote
            if 'answer_sha256' in value:valid=valid and value['answer_sha256']==doc['answer_sha256']
            if 'quote_sha256' in value:valid=valid and value['quote_sha256']==g.rawsha(quote)
            rows.append({'field':path,'start':a,'end':b,'quote_sha256':g.rawsha(quote) if isinstance(quote,str) else None,'exact_source_slice':valid})
        for k,v in value.items():rows.extend(offset_checks(v,doc,path+'.'+k))
    elif isinstance(value,list):
        for i,v in enumerate(value):rows.extend(offset_checks(v,doc,f'{path}[{i}]'))
    return rows
def anchor(fn):return {'path':str(Path(g.__file__).resolve()),'function':fn.__name__,'line':inspect.getsourcelines(fn)[1],'sha256':MODULE_SHA}
def gate():
    # Completion metadata is read before any current return or trial contents.
    summary_path=BATCH/'completion_summary.json';facts_path=BATCH/'independent_fact_audit_v6/summary.json'
    require(summary_path.exists() and facts_path.exists(),'WAIT_FOR_ROOT_TERMINAL_ANALYSIS_AND_FROZEN_FACT_AUDIT')
    summary,facts=read(summary_path),read(facts_path)
    require(summary['status']=='experiment_complete_not_scientific_validation' and summary['actual_observations']==5,'BATCH_NOT_COMPLETE')
    require(facts['status']=='complete' and facts['fixed_answers']==5,'FACT_REVIEW_NOT_COMPLETE')
    require([facts[k] for k in ['explicit_names_denominator','core_duration_denominator','explicit_relation_denominator','ambiguity_group_denominator']]==[16,31,3,2],'FACT_DENOMINATOR_DRIFT')
    require(sha(g.__file__)==MODULE_SHA and sha(fc.__file__)==CHECKER_SHA,'FROZEN_IMPLEMENTATION_CHANGED')
    matrix=read(BATCH/'matrix.json');require(len(matrix)==5 and {c['anonymous_answer_id'] for c in matrix}==set(IDS),'MATRIX_CHANGED')
    for cell in matrix:require((BATCH/'run/trials'/f"{cell['planned_trial_id']}.json").exists(),'NONTERMINAL_MATRIX')
    return summary,facts,matrix
def trace(aid,cell,case,official,fact,ledger):
    tid=cell['planned_trial_id'];attempt=BATCH/'run/attempts'/f'{tid}_1';trial_path=BATCH/'run/trials'/f'{tid}.json'
    trial=read(trial_path);require(trial['status'] in ['success','failed'] and trial['identity']==cell['identity'] and trial['trial_id']==tid and trial['attempt']==1,'TRIAL_IDENTITY_OR_TERMINAL_STATE')
    require(official['trial_id']==tid and official['status']==trial['status'],'OFFICIAL_ANALYSIS_IDENTITY')
    doc_path=BATCH/'source_documents'/f'{aid}.json';doc=read(doc_path)
    require(doc==g.document(case['model_response'],g.source_id_for_case(case)),'FIXED_SOURCE_DOCUMENT_DRIFT')
    receipt=read(attempt/'request_receipt.json');require(receipt==ledger[receipt['request_id']] and receipt['trial_id']==tid and receipt['attempt']==1,'REAL_RECEIPT_LEDGER_MISMATCH')
    require(receipt['package_request_index']==official['request_index'],'REQUEST_INDEX_MISMATCH')
    dependencies=[Path(__file__),Path(g.__file__),Path(fc.__file__),BATCH/'matrix.json',BATCH/'cases.json',BATCH/'expected_contract.json',BATCH/'completion_summary.json',BATCH/'per_answer.json',BATCH/'independent_fact_audit_v6/summary.json',BATCH/'independent_fact_audit_v6/per_answer.json',doc_path,trial_path,*sorted(p for p in attempt.glob('*') if p.is_file())]
    bindings=[bind(p) for p in dependencies]
    http_path=attempt/'http_request_payload.json';transport={'recorded':http_path.exists()}
    if http_path.exists():
        http=read(http_path);require(http['format']==g.schema(),'ACTUAL_SCHEMA_DRIFT')
        require(http['options']['num_ctx']==98304 and http['options']['num_predict']==8192 and http['options']['temperature']==0,'ACTUAL_OPTIONS_DRIFT')
        require(g.rawsha(http['prompt'])==cell['prompt_raw_sha256'],'HTTP_PROMPT_DRIFT')
        require(sha(attempt/'prompt.txt')==cell['prompt_file_sha256']==trial['prompt_sha256'],'PROMPT_FILE_DRIFT')
        require((attempt/'prompt.txt').read_text(encoding='utf8')==http['prompt'],'PROMPT_STRING_DRIFT')
        transport.update(prompt_string_sha256=g.rawsha(http['prompt']),prompt_file_sha256=sha(attempt/'prompt.txt'),schema_equal=True,num_ctx=98304)
    rawpath=attempt/'raw_source_bound_content.txt';conversion_path=attempt/'source_bound_conversion.json';error_path=attempt/'source_bound_conversion_error.json'
    actual_conversion=read(conversion_path) if conversion_path.exists() else None
    result={'anonymous_answer_id':aid,'status':'terminal_read_only_development_diagnostic','technical_status':trial['status'],'trial_id':tid,'request_index':receipt['package_request_index'],'source_answer_sha256':doc['answer_sha256'],'actual_first_error':read(error_path) if error_path.exists() else None,
      'actual_trial_failure_stage':(trial.get('evaluation') or {}).get('failure_stage'),'actual_trial_error':(trial.get('evaluation') or {}).get('_error'),
      'source_bound_return_available':rawpath.exists(),'transport_identity':transport,'original_numeric_proposals':official['raw_original_numeric_proposals'],'component_gated_proposals':official['component_gated_proposals'],
      'numeric_state_per_component':numeric_states(official['component_gated_proposals']),'component_gate_notes':official['component_gate_notes'],'evidence_state':official['evidence_state'],
      'frozen_fact_audit':fact,'input_bindings':bindings,'new_model_calls':0,'expert_confirmation':False,'raw_or_score_changes':False,'source_chain_verified':True,
      'limits':'Field-level diagnostics of an invalid return do not bypass failed conversion, supply corrected scores, validate biological relationships, or certify source semantics.'}
    if not rawpath.exists():
        result.update(status='terminal_no_source_bound_return',source_fields_unavailable_reason='No original source-bound text was saved; absence of fields is not inferred.')
        return result
    raw=rawpath.read_bytes().decode('utf8');provider=read(attempt/'provider_response.json');raw_receipt=read(attempt/'raw_source_bound_receipt.json')
    require(provider['response']==raw and raw_receipt['raw_response_sha256']==raw_receipt['raw_text_file_sha256']==sha(rawpath),'RAW_PROVIDER_RECEIPT_DRIFT')
    require(raw_receipt['source_document_sha256']==sha(doc_path),'RAW_SOURCE_DOCUMENT_DRIFT')
    result['provider_metadata']={k:provider.get(k) for k in ['done','done_reason','prompt_eval_count','eval_count']}
    parsed=probe(lambda:g.integrity.parse_judge_object(raw));result['strict_parse']={k:v for k,v in parsed.items() if k!='value'}
    if not parsed['passed']:
        require(actual_conversion is None,'STRICT_PARSE_FAILURE_WITH_VALID_CONVERSION');result['status']='terminal_strict_parse_failure';return result
    payload=parsed['value'];shape=probe(lambda:g.validate_shape(payload,g.schema()));result['shape_validation']=shape
    replay=probe(lambda:g.convert(raw,doc));result['actual_conversion_replay']={'passed':replay['passed'],'error':replay.get('error'),'existing_conversion_equal':actual_conversion is not None and replay.get('value')==actual_conversion}
    if actual_conversion is not None:require(replay['passed'] and replay['value']==actual_conversion,'ACTUAL_CONVERSION_REPLAY_DIFFERS')
    elif error_path.exists():require(not replay['passed'] and replay['error']==read(error_path)['reason'],'ORIGINAL_CONVERSION_FAILURE_NOT_REPRODUCED')
    reg=g.candidate_registry(doc);reference_rows=[]
    for path,kind,reference in refs(payload):reference_rows.append({'field':path,'reference_kind':kind,'raw_reference':reference,**probe(lambda r=reference:g.resolve(r,doc,reg))})
    result['source_references']=reference_rows;result['source_ref_counts']=dict(Counter(r['reference_kind'] for r in reference_rows));result['source_ref_resolution_failures']=sum(not r['passed'] for r in reference_rows)
    if not shape['passed']:
        result.update(status='terminal_schema_failure',raw_field_diagnostics_scope='Only parse and source-reference resolution. Invalid schema does not establish valid operations, names, relations, or coverage.')
        return result
    ex=payload['grounded_extraction'];names=[]
    for group in ['method_mentions','entities']:
        for ent in ex[group]:
            support=probe(lambda:g.resolve(ent['supporting_evidence'],doc,reg))
            binding=probe(lambda:g.bind_literal_name(ent['literal_name'],support['value'],doc,ent['name_occurrence'])) if support['passed'] else support
            names.append({'group':group,'id':ent['id'],'literal_name':ent['literal_name'],'kind':ent.get('kind'),'usage':ent['usage'],'name_occurrence':ent['name_occurrence'],'support':support,'binding':binding,'identity_or_usage_scientifically_confirmed':False})
    operations=[]
    actual_ops={o['id']:o for o in actual_conversion['source_audit']['resolved']['operations']} if actual_conversion else {}
    for op in ex['operations']:
        operation=probe(lambda:g.resolve(op['operation'],doc,reg));duration=probe(lambda:g.resolve(op['duration'],doc,reg)) if op['duration'] else None
        parsed_duration=probe(lambda:g.duration_value(duration['value']['quote'])) if duration and duration['passed'] else None
        binding=probe(lambda:g.record_binding(operation['value'],duration['value'],doc)) if operation['passed'] and duration and duration['passed'] else None
        repeat=probe(lambda:g.resolve(op['repeat_evidence'],doc,reg)) if op['repeat_evidence'] else None
        row={'id':op['id'],'raw_phase':op['phase'],'raw_execution_scope':op['execution_scope'],'operation':operation,'duration':duration,'literal_duration_parse':parsed_duration,
         'independent_source_hours':fc.source_hours(duration['value']['quote']) if duration and duration['passed'] else None,'individual_duration_binding':binding,'repeat_evidence':repeat,'raw_condition_evidence':op['condition_evidence'],
         'actual_resolved_operation':actual_ops.get(op['id']),'diagnostic_only_no_scope_or_score_repair':True}
        operations.append(row)
    relations=[];entities={e['id']:e for e in ex['entities']}
    for rel in ex['relations']:
        evidence=probe(lambda:g.resolve(rel['evidence'],doc,reg));f=entities.get(rel['fluor_entity_id']);t=entities.get(rel['target_entity_id'])
        policy=probe(lambda:g.relation_clause_support(f['literal_name'],t['literal_name'],evidence['value'],doc,ex['entities'])) if f and t and evidence['passed'] else None
        relations.append({'raw_record':rel,'source_evidence':evidence,'individual_clause_policy':policy,'actual_resolved_relation':next((r for r in actual_conversion['source_audit']['resolved']['relations'] if r['id']==rel['id']),None) if actual_conversion else None,'field_probe_does_not_bypass_full_failure':actual_conversion is None})
    ri=[]
    for r in ex['ri_mentions']:
        resolved=probe(lambda:g.resolve(r['value'],doc,reg));ri.append({'raw_record':r,'source':resolved,'parser':probe(lambda:g.parse_ri_literal(resolved['value']['quote'])) if resolved['passed'] else None})
    fixed_components=[]
    # Raw source references are independently counted even when full conversion failed.
    # They are never added to the frozen checker's effective-conversion numerator.
    inventory=read(fc.INVENTORY);original=next(f for f in inventory['cases'] if f['anonymous_answer_id']==aid)
    for component in original['time']['components']:
        matches=[];expected=component['duration_span']
        for op in operations:
            d=op['duration'];s=d.get('value') if d and d['passed'] else None
            if s and expected['start']<=s['start'] and s['end']<=expected['end'] and fc.same(op['independent_source_hours'],component['hours']):
                matches.append({'operation_id':op['id'],'source_numeric_value_equal':True,'record_binding_valid':bool(op['individual_duration_binding'] and op['individual_duration_binding']['passed'] and op['individual_duration_binding']['value']['valid']),'raw_phase':op['raw_phase'],'raw_execution_scope':op['raw_execution_scope']})
        fixed_components.append({'step_label':component['step_label'],'hours':component['hours'],'source_span':expected,'raw_exact_numeric_mentions':matches,'raw_reference_present':bool(matches),'counts_as_valid_conversion_retention':False})
    source_objects={'references':reference_rows,'names':names,'operations':operations,'relations':relations,'RI':ri,'actual_conversion':actual_conversion}
    offsets=offset_checks(source_objects,doc);require(all(r['exact_source_slice'] for r in offsets),'DIAGNOSTIC_SOURCE_OFFSET_REPLAY_FAILED')
    result.update(name_bindings=names,name_binding_failures=sum(not x['binding']['passed'] for x in names),operations=operations,relations=relations,RI=ri,raw_intrinsic_signals=ex['intrinsic_signals'],raw_coverage=ex['coverage'],raw_timeline=ex['timeline'],raw_precedence_edges=ex['precedence_edges'],
       raw_fixed_duration_diagnostics=fixed_components,raw_fixed_numeric_reference_count=sum(x['raw_reference_present'] for x in fixed_components),
       actual_legacy_projection=actual_conversion['legacy_projection'] if actual_conversion else None,
       exact_source_offset_checks=offsets,original_and_derived_offsets_all_pass=True,
       code_anchors=[anchor(fn) for fn in [g.resolve,g.bind_literal_name,g.record_binding,g.repeat_source_binding,g.repeat_count,g.compute_time,g.intrinsic_policy,g.relation_clause_support,g.audit_payload]])
    projection=actual_conversion['legacy_projection'] if actual_conversion else None
    result['diagnostic_findings']={
        'valid_conversion_available':actual_conversion is not None,
        'raw_name_binding_failures':result['name_binding_failures'],
        'raw_source_reference_failures':result['source_ref_resolution_failures'],
        'raw_fixed_numeric_mentions':result['raw_fixed_numeric_reference_count'],
        'fixed_numeric_denominator_for_answer':len(fixed_components),
        'converted_initial_time_bounds':projection['time_calculation']['initial_scope_candidate_bounds_hours'] if projection else None,
        'converted_primary_time':projection['time_calculation']['total_hours'] if projection else None,
        'unchanged_time_gate_reasons':projection['time_calculation']['issues'] if projection else None,
        'unchanged_projection_gate_reasons':projection['projection_issues'] if projection else None,
        'resolved_operation_phases':dict(Counter(o['phase'] for o in actual_ops.values())) if actual_conversion else None,
        'resolved_operation_scopes':dict(Counter(o['execution_scope'] for o in actual_ops.values())) if actual_conversion else None,
        'repeat_binding_or_omission_unresolved_operations':[o['id'] for o in actual_ops.values() if o['repeat_count'] is None] if actual_conversion else None,
        'intrinsic_decisions':projection.get('intrinsic_identity_conversion',[]) if projection else None,
        'frozen_inventory_time_scope_comparison':fact['time_scope_comparison'],
        'no_semantic_correction_or_true_total_inferred':True}
    return result
def self_check():
    require(numeric_states({'a':0,'b':None,'c':2,'d':False})=={'a':'known_zero','b':'NA','c':'numeric_nonzero','d':'NA'},'ZERO_NA_TEST')
    kinds=list(refs({'a':{'candidate_id':'O0001'},'b':{'clause_id':'Q0001'},'c':{'unit_id':'L0001'},'d':{'unit_id':'L0001','quote':'X','occurrence':0}}))
    require([r[1] for r in kinds]==['CandidateRef_O','ClauseRef_Q','UnitRef','ForbiddenRawOrMalformedRef'],'REFERENCE_TYPE_TEST')
    d=g.document('FICTIONAL\r\nONLY\n','SYNTHETIC');checks=offset_checks({'start':0,'end':9,'quote':'FICTIONAL','answer_sha256':d['answer_sha256']},d)
    require(checks[0]['exact_source_slice'],'OFFSET_TEST')
    OUT.mkdir(parents=True,exist_ok=True);save(OUT/'software_checks.json',{'status':'pass','synthetic_checks':3,'real_return_files_read':False,'new_model_calls':0,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]})
    print(json.dumps({'status':'software_checks_pass','checks':3,'new_model_calls':0}))
def main():
    summary,facts,matrix=gate();require(not (OUT/'summary_5of5.json').exists(),'EXISTING_DIAGNOSTIC_IS_IMMUTABLE')
    def deny(*a,**kw):raise RuntimeError('REAL_SOCKET_FORBIDDEN')
    socket.socket=deny;socket.create_connection=deny
    ledger_bytes=LEDGER.read_bytes();ledger={r['request_id']:r for r in map(json.loads,ledger_bytes.decode('utf8').splitlines())}
    cases={c['anonymous_answer_id']:c for c in read(BATCH/'cases.json')['cases']};official={r['anonymous_answer_id']:r for r in read(BATCH/'per_answer.json')};factrows={r['anonymous_answer_id']:r for r in read(BATCH/'independent_fact_audit_v6/per_answer.json')}
    rows=[trace(c['anonymous_answer_id'],c,cases[c['anonymous_answer_id']],official[c['anonymous_answer_id']],factrows[c['anonymous_answer_id']],ledger) for c in matrix]
    require(len(rows)==5 and {r['anonymous_answer_id'] for r in rows}==set(IDS),'DIAGNOSTIC_DENOMINATOR')
    for r in rows:require(all(sha(v['path'])==v['sha256'] for v in r['input_bindings']),'INPUT_MUTATION_DURING_OFFLINE_DIAGNOSIS')
    require(LEDGER.read_bytes().startswith(ledger_bytes),'LEDGER_PREFIX_MUTATED');OUT.mkdir(parents=True,exist_ok=True)
    for r in rows:
        save(OUT/(r['anonymous_answer_id']+'_trace.json'),r)
        lines=['# '+r['anonymous_answer_id']+' terminal source diagnosis','',f"Technical status: {r['technical_status']}; actual request {r['request_index']}. Original output and scores are unchanged.",'',f"Failure stage: {r['actual_trial_failure_stage'] or 'none'}. Diagnostic path: {r['status']}.",'',
          'Numeric values, known zeros, and NA are separate in `numeric_state_per_component`. Raw numeric references do not count as retained facts after a failed conversion. Exact source offsets do not establish scientific correctness.','',
          'Full source, prompt, provider, receipt and trial bindings are in the accompanying JSON. Software field probes retain the original scope, coverage and unresolved issues; no corrected payload or score is created.','']
        if 'diagnostic_findings' in r:
            finding=r['diagnostic_findings'];lines.extend([
              f"Raw fixed numeric references: {finding['raw_fixed_numeric_mentions']}/{finding['fixed_numeric_denominator_for_answer']} (separate from converted retention).",
              f"Converted initial bounds: {finding['converted_initial_time_bounds']}; unqualified primary time: {finding['converted_primary_time']}.",
              'Actual time gate reasons: `'+json.dumps(finding['unchanged_time_gate_reasons'],ensure_ascii=False)+'`.',
              'Actual projection gate reasons: `'+json.dumps(finding['unchanged_projection_gate_reasons'],ensure_ascii=False)+'`.',
              'Repeat binding/omission unresolved operation IDs: `'+json.dumps(finding['repeat_binding_or_omission_unresolved_operations'],ensure_ascii=False)+'`.',
              'These are the observed program gates; they do not decide which source interpretation is scientifically correct.',''])
        (OUT/(r['anonymous_answer_id']+'_trace.md')).write_text('\n'.join(lines),encoding='utf8')
    result={'status':'complete_five_terminal_source_diagnostics','fixed_answers':5,'technical_successes':sum(r['technical_status']=='success' for r in rows),'technical_failures':sum(r['technical_status']=='failed' for r in rows),
       'request_indices':[r['request_index'] for r in rows],'facts_summary':bind(BATCH/'independent_fact_audit_v6/summary.json'),'fixed_fact_denominators':[16,31,3,2],
       'traces':[bind(OUT/(aid+'_trace.json')) for aid in IDS],
       'raw_fixed_numeric_reference_count':sum(r.get('raw_fixed_numeric_reference_count',0) for r in rows),'raw_reference_diagnostic_available_answers':sum('raw_fixed_duration_diagnostics' in r for r in rows),
       'raw_diagnostic_is_not_converted_retention':True,'valid_conversion_record_bound_retention':facts['record_bound_numeric_components_retained'],
       'reference_kind_counts':dict(sum((Counter(r.get('source_ref_counts',{})) for r in rows),Counter())),
       'scientific_validity_confirmed':False,'expert_labels':0,'new_model_calls':0,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'summary_5of5.json',result)
    (OUT/'README.md').write_text('# V6 terminal source diagnostics\n\nAll five original returns are retained. These records separate technical status, raw source references, valid converted facts, numeric zero, and NA. Field-level probes never repair or replace failed trials.\n\n'+ '\n'.join(f'- [{aid}](./{aid}_trace.md) · [exact bindings](./{aid}_trace.json)' for aid in IDS)+'\n\nNo expert accuracy or generalization claim is made.\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ['status','fixed_answers','technical_successes','technical_failures','new_model_calls']}))
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--self-check',action='store_true');ap.add_argument('--analyze-completed',action='store_true');args=ap.parse_args();require(args.self_check != args.analyze_completed,'CHOOSE_ONE_ACTION')
    self_check() if args.self_check else main()
