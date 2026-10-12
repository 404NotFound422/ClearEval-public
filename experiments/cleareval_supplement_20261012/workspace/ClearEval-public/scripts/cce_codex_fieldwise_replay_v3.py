"""Versioned read-only snapshots of the 12 public Codex development slots.

Original imports/statuses are preserved. Pending returns are not opened. No
provider is invented for agent-authored files, and no model request is possible.
"""
from __future__ import annotations
import argparse,contextlib,copy,io,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_codex_repeat_extension_v1 as extension
import cce_fieldwise_scoring_v3 as fw
import cce_fieldwise_confirmation_v1 as independent_direct
import cce_partial_components_v1 as partial
old=extension.old;j=old.j;base=old.base;g=old.g
OUT=old.budget.OUT/'codex_fieldwise_replay_v3'
VERSION='codex-public-fieldwise-replay-v3'
def require(ok,why):
    if not ok:raise ValueError(why)
def bind(p):return old.bind(p)
def save(p,value):old.once(p,value)
def silent(fn,*args):
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return fn(*args)
def independent_processing(raw,doc,case,step):
    """Never modifies raw. Internal views supply only their explicit component."""
    result={'raw_sha256':g.rawsha(raw),'processing_version':fw.VERSION,'full_conversion_success':False,
        'original_technical_status_promoted':False,'expert_truth':False,'raw_repaired':False,'views':{},'new_model_calls':0}
    try:
        cv=fw.convert(raw,doc,case);num=silent(fw.score_conversion,case,cv,step)
        result.update(full_conversion_success=True,conversion=cv,numeric=num,metrics=num['metrics'],processing_status='full_fieldwise_conversion')
        return result
    except Exception as e:result['full_conversion_or_scoring_failure']={'type':type(e).__name__,'reason':str(e)}
    metrics=base.scoring.derive({},step,False)
    try:metrics,evidence=independent_direct.recover_direct(raw,doc,step);result['independent_direct']=evidence
    except Exception as e:result['independent_direct_error']=str(e)
    try:
        payload=base.integrity.parse_judge_object(raw)
        require(isinstance(payload,dict) and set(payload)<={'scores','score_evidence','grounded_extraction'},'UNATTRIBUTABLE_TOP_LEVEL')
        extraction=payload['grounded_extraction'];require(isinstance(extraction,dict),'EXTRACTION_OBJECT')
        require(extraction['source_id']==doc['source_id'] and extraction['schema_version']==g.VERSION,'SOURCE_OR_WIRE_IDENTITY')
        require(doc==g.document(case['model_response'],g.source_id_for_case(case)),'EXACT_SOURCE_DOCUMENT')
        spec=g.schema_for_document(doc)['properties']['grounded_extraction']['properties']
        require(not(set(extraction)-set(spec)),'UNATTRIBUTABLE_EXTRACTION_FIELDS')
        records,issues,duplicates=partial.records_audit(payload,doc,g)
        result.update(record_audit=records,record_errors=issues,duplicate_ids=duplicates)
        views=[('method',['method_mentions'],[],['s_method','s_trans'],{'method_mentions'}),
            ('time',['method_mentions','operations','timeline','precedence_edges','total_time_claims'],['t','c','u'],['s_time'],{'method_mentions','operations','total_time_claims'}),
            ('label',['method_mentions','entities','relations','intrinsic_signals'],['e','u'],['s_label'],{'method_mentions','entities','relations','intrinsic_signals'})]
        for name,keep,coverage,components,groups in views:
            item={'components':components,'status':'invalid_or_unknown_dependency','internal_view_only':True,'model_raw_modified':False}
            result['views'][name]=item
            try:
                require(not any(r['group'] in groups and r.get('id') in duplicates for r in records if isinstance(r.get('id'),str)),'DUPLICATE_ID_TAINTS_DEPENDENCY')
                view,audit=partial.neutral_view(payload,doc,g,keep,coverage)
                # Relevant records and full relevant coverage remain byte-value
                # identical. Unrelated placeholders are never model facts.
                cv=fw.convert(g.canonical(view),doc,case);num=silent(fw.score_conversion,case,cv,step)
                item.update(status='validated_dependency_view',view_audit=audit,view_sha256=j.digest(view),
                    projected_extraction=cv['legacy_projection']['extraction'],component_gate_notes=num.get('component_gate_notes'),
                    component_values={k:num['metrics'][k] for k in components})
                for key in components:metrics[key]=num['metrics'][key]
            except Exception as e:item['error']={'type':type(e).__name__,'reason':str(e)}
        result['name_binding_failures']=[]
        for record in records:
            if record['group'] not in ['method_mentions','entities'] or record['valid_shape_and_local_source']:continue
            r=record['raw_record'];support=record['resolved_fields'].get('u');entry={'pointer':record['pointer'],'raw_record':r,'errors':record['errors']}
            if support and isinstance(r,dict) and isinstance(r.get('n'),str):
                entry['source_unit']={k:support[k] for k in ['unit_id','start','end','quote'] if k in support}
                entry['source_context']=support.get('context')
                entry['complete_name_occurrences']=g.name_occurrence_inventory(r['n'],support,doc)
            result['name_binding_failures'].append(entry)
    except Exception as e:result['independent_extraction_unavailable']={'type':type(e).__name__,'reason':str(e)}
    result['metrics']=base.scoring.derive(metrics,step,True)
    result['processing_status']='partial_dependency_replay'
    return result
def verified_terminal(row,case):
    source=Path(row['source_out']);dest=old.directory(source,row);tp=dest/'terminal.json';terminal=j.read(tp)
    require(terminal['cell_id']==row['cell_id'] and terminal['trial_id']==row['trial_id'] and terminal['identity']==row['identity'],'ORIGINAL_TERMINAL_IDENTITY')
    require(type(terminal['attempt']) is int and terminal['attempt']==1,'ORIGINAL_ATTEMPT')
    base.verify_bindings(terminal['bound_artifacts']);base.verify_bindings([row['packet'],row['source_document']])
    receipt=old.checked_receipt(source,row);require(receipt['request_id']==terminal['request_id'],'ORIGINAL_RESERVATION')
    dispatch=j.read(dest/'actual_dispatch_evidence.json');old.dispatch_evidence(dispatch,row)
    require(dispatch['actual_agent_id']==terminal['actual_agent_id'],'ORIGINAL_AGENT_IDENTITY')
    rawpath=dest/'raw_response.txt';rawbytes=rawpath.read_bytes();raw=rawbytes.decode('utf8')
    original_submission=old.safe_submission(row['submission_path'],old.submission_path(source,row['cell_id']),source)
    require(rawbytes==original_submission.read_bytes() and old.handoff.rawsha(rawbytes)==terminal['raw_sha256'],'COMMITTED_RAW_AND_SUBMISSION_EXACT')
    old.submission_evidence(j.read(dest/'actual_return_evidence.json'),row,dispatch,rawbytes)
    doc=j.read(row['source_document']['path']);require(doc==g.document(case['model_response'],g.source_id_for_case(case)),'SOURCE_DOCUMENT_IDENTITY')
    require(case['answer_sha256']==row['step']['answer_sha256'] and case['question_sha256']==row['step']['question_sha256']
        and j.digest(case['references'])==row['step']['references_sha256'],'STEP_INPUT_IDENTITY')
    base.verify_bindings(row['step']['provenance'])
    sources=[bind(tp),bind(rawpath),bind(original_submission),bind(dest/'request_receipt.json'),bind(dest/'actual_dispatch_evidence.json'),bind(dest/'actual_return_evidence.json'),row['source_document'],row['packet']]
    return terminal,raw,doc,sources
def snapshot(a):
    plan,cases,extras=extension.validate(extension.OUT);matrix=j.read(extension.OUT/'matrix.json')
    require(len(matrix)==12 and [r['cell_id'] for r in matrix]==plan['fixed_order'],'FIXED_TWELVE_MATRIX')
    bycase={c['case_id']:c for c in cases};at_start=j.now()
    # Snapshot availability before reading any return. Slots which finish later
    # remain pending in this snapshot and may enter a later immutable snapshot.
    availability={r['cell_id']:(old.directory(Path(r['source_out']),r)/'terminal.json').exists() for r in matrix}
    out=a.out/at_start.replace(':','').replace('+','_');out.mkdir(parents=True,exist_ok=False)
    dependencies=[Path(__file__),Path(fw.__file__),Path(fw.previous.__file__),Path(fw.previous.noncore_context.__file__),Path(fw.previous.previous.__file__),Path(partial.__file__),Path(independent_direct.__file__),
        Path(g.__file__),Path(old.__file__),Path(extension.__file__),Path(base.scoring.__file__),extension.OUT/'plan.json',extension.OUT/'matrix.json']
    deps=[bind(p) for p in dependencies];observations=[];inputs=[]
    for r in matrix:
        common={'cell_id':r['cell_id'],'anonymous_answer_id':r['anonymous_answer_id'],'repeat_index':r['repeat_index'],
            'trial_id':r['trial_id'],'disposition':r['disposition'],'model_backend_observed':False,'same_provider_contract_as_Qwen':False}
        if not availability[r['cell_id']]:
            observations.append({**common,'original_status':'pending','processing_status':'pending_no_return_opened','metrics':base.scoring.derive({},r['step'],False)});continue
        terminal,raw,doc,bindings=verified_terminal(r,bycase[r['case_id']]);inputs+=bindings
        processed=independent_processing(raw,doc,bycase[r['case_id']],r['step'])
        save(out/'per_cell'/f"{r['cell_id']}.json",{'source_bindings':bindings,'original_failure':terminal.get('failure'),**processed})
        observations.append({**common,'original_status':terminal['status'],'original_failure':terminal.get('failure'),'original_metrics':terminal['metrics'],
            'raw_sha256':terminal['raw_sha256'],'processing_status':processed['processing_status'],'full_fieldwise_conversion_success':processed['full_conversion_success'],
            'metrics':processed['metrics'],'name_binding_failures':processed.get('name_binding_failures',[]),'per_cell':bind(out/'per_cell'/f"{r['cell_id']}.json")})
    base.verify_bindings(deps+inputs)
    terminalrows=[r for r in observations if r['original_status']!='pending']
    summary={'version':VERSION,'as_of_utc':at_start,'finished_utc':j.now(),'planned_slots':12,'terminal_at_start':len(terminalrows),'pending':12-len(terminalrows),
        'original_success':sum(r['original_status']=='success' for r in terminalrows),'original_failed':sum(r['original_status']=='failed' for r in terminalrows),
        'full_fieldwise_conversion_success':sum(r.get('full_fieldwise_conversion_success',False) for r in terminalrows),
        'partial_dependency_replay':sum(r['processing_status']=='partial_dependency_replay' for r in terminalrows),
        'numeric_coverage_planned_12':{k:sum(base.scoring.finite(r['metrics'][k]) for r in observations) for k in base.scoring.METRICS},
        'complete_numeric_CCE':sum(all(base.scoring.finite(r['metrics'][k]) for k in ['Com','Cor','Eff']) for r in observations),
        'source_kind':'agent_authored_file_submission','backend_model_temperature_decoder_unknown':True,'expert_returns':0,'scientific_acceptance':False,
        'original_terminal_statuses_preserved':True,'new_model_calls':0,'raw_repaired':False,'unrun_confirmation_bodies_read':0}
    save(out/'observations.json',observations);save(out/'summary.json',summary)
    save(out/'verification.json',{'status':'pass_readonly_source_chain','dependencies':deps,'input_bindings':inputs,'all_12_slots_retained':True,
        'source_files_unchanged_after_replay':True,'actual_command':[sys.executable,*sys.argv],'original_outputs_overwritten':False,'new_model_calls':0})
    lines=['# Codex public 12-slot fieldwise replay','',f"Snapshot {at_start}: {summary['terminal_at_start']} original terminal slots, {summary['pending']} pending. Original success/failure statuses are retained.",'',
        'Full returns use the same fixed fieldwise v3 processor. A failed full conversion is not promoted. Independently validated direct scores are retained, including explicit nulls. Method, time and label use separate internal dependency views only if all of their relevant original records, global-ID constraints and coverage pass. Unrelated validation scaffolding is not model output and never supplies a score. Original source and raw files are unchanged.',
        '', 'Pending slots were not opened. This is a posthoc software replay of public development observations, not a new model result or expert judgment. The Codex backend/model/temperature/decoder remain unobserved.']
    for r in terminalrows:
        if r.get('name_binding_failures'):
            lines += ['',f"## {r['cell_id']}",f"Original failure: {r['original_failure']}",f"Retained metrics: `{j.canonical(r['metrics'])}`",'Exact name/source/ordinal evidence is retained in the per-cell JSON. No ordinal, name or source reference was changed.']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(j.canonical({'out':str(out),'summary_sha256':j.filehash(out/'summary.json'),**summary}))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['snapshot']);p.add_argument('--out',type=Path,default=OUT);snapshot(p.parse_args())
if __name__=='__main__':main()
