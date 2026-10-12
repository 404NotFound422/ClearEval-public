"""Small generation-completion development runner; actual requests require run.

Only the five public development answers and already exposed FPC01 are allowed.
The seven unrun confirmation answers are never opened. No original batch is edited.
"""
from __future__ import annotations
import argparse,asyncio,contextlib,copy,io,json,math,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_generation_order_only_v1 as candidate
import cce_round2_runner_v11 as base
import cce_fieldwise_confirmation_v1 as recovery
import cce_fieldwise_scoring_v1 as fw
import cce_four_hour_extension_20261010 as extension
j=base.j;budget=base.budget;g=base.grounded
R=budget.OUT;OUT=R/'generation_order_only_development_v1'
ALLOWED=['FPC01']
MODEL=base.MODEL
def require(ok,why):
    if not ok:raise ValueError(why)
def bind(p):return base.bind(p)
def write(p,obj):candidate.write_ordered_once(p,obj)
def writebytes(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(value)
def finite(x):return type(x) in (float,int) and math.isfinite(x)
def dependencies(contract):
    return list(dict.fromkeys([Path(__file__),Path(candidate.__file__),Path(candidate.ordered_tools.__file__),Path(extension.__file__),extension.RECORD,
        *recovery.dependencies(contract),R/'grounded_development_v11/expected_contract.json']))
def source_cases(ids):
    cases,steps=base.checked_cases();indexed={c['anonymous_answer_id']:copy.deepcopy(c) for c in cases};bindings=[bind(base.SOURCE_CASES),bind(base.STEPS)]
    if 'FPC01' in ids:
        # Metadata only from the eight-cell files. The original archive helper
        # decodes only the selected, already exposed answer object.
        sampling=R/'fieldwise_confirmation_sampling_v1';frozen=R/'fieldwise_confirmation_v1'
        selected=j.read(sampling/'selection_metadata_frozen.json');rows=[r for r in selected['selection'] if r['confirmation_id']=='FPC01'];require(len(rows)==1,'FPC01_SELECTION_IDENTITY')
        meta=rows[0];matrix=j.read(frozen/'matrix.json');old=[r for r in matrix if r['anonymous_answer_id']=='FPC01'];require(len(old)==1,'FPC01_FROZEN_IDENTITY');row=old[0]
        prior=j.read(frozen/'run/trials'/f"{row['planned_trial_id']}.json");require(prior['actual_request_made'] is True and prior['status']=='failed','FPC01_MUST_ALREADY_BE_EXPOSED')
        base.verify_bindings(prior['bound_artifacts']);base.verify_bindings(list(row['assets'].values()))
        obj,loc=recovery.exporter.selected_record(ROOT/f"dataset/Q+AR/model_response/from_{meta['model']}_1-shot.json",int(meta['question_id']))
        require(g.rawsha(obj['model_response'])==meta['answer_sha256']==row['step']['answer_sha256'],'FPC01_ANSWER_HASH')
        require(g.rawsha(obj['specific_question'])==meta['question_sha256']==row['step']['question_sha256'],'FPC01_QUESTION_HASH')
        refs=j.read(recovery.STEP_ROOT/'references.json')['references'];ri={r['reference_id']:r for r in refs};selectedrefs=[copy.deepcopy(ri[x]) for x in row['step']['candidate_reference_ids']]
        require(j.digest(selectedrefs)==row['step']['references_sha256'],'FPC01_REFERENCE_HASH')
        c={'case_id':row['case_id'],'anonymous_answer_id':'FPC01','question_id':int(meta['question_id']),
           'specific_question':obj['specific_question'],'model_response':obj['model_response'],'references':selectedrefs,
           'answer_sha256':meta['answer_sha256'],'question_sha256':meta['question_sha256'],'formal_eligible':False}
        indexed['FPC01']=c;steps[c['case_id']]=copy.deepcopy(row['step']);base.verify_bindings(row['step']['provenance'])
        bindings += [bind(sampling/'selection_metadata_frozen.json'),bind(frozen/'matrix.json'),bind(frozen/'run/trials'/f"{row['planned_trial_id']}.json"),bind(recovery.STEP_ROOT/'references.json')]
        bindings += row['step']['provenance'];bindings += list(row['assets'].values());bindings += prior['bound_artifacts']
    chosen=[indexed[i] for i in ids]
    return chosen,{c['case_id']:steps[c['case_id']] for c in chosen},bindings
def prepare(a):
    require(not (a.out/'plan.json').exists(),'NO_OVERWRITE_PREPARED_BATCH');require(len(set(a.ids))==len(a.ids) and set(a.ids)<=set(ALLOWED),'PUBLIC_DEVELOPMENT_IDS_ONLY')
    extension.install();budget.guard('development',len(a.ids),600)
    contract,models=base.science_contract(a.model_config,True);public=models[0]['public'];old=j.read(R/'grounded_development_v11/expected_contract.json')
    require(contract['models']==old['models'],'ORIGINAL_QWEN_SETTINGS_CHANGED')
    casevalues,steps,sourcebindings=source_cases(a.ids)
    codebindings=[bind(p) for p in dependencies(contract)]
    contract['generation_completion']={'candidate':candidate.CANDIDATE_VERSION,'wire_version':g.VERSION,
        'candidate_code':bind(candidate.__file__),'runner_code':bind(__file__),'fieldwise_code':bind(fw.__file__),
        'intervention':['preserve original schema property order in storage and HTTP; original prompt bytes unchanged'],
        'scope':'already exposed development answers; FPC01 is not confirmation for this candidate'}
    write(a.out/'expected_contract.json',contract);write(a.out/'cases.json',{'cases':casevalues});write(a.out/'step_inputs.json',steps)
    writebytes(a.out/'model_config.json',a.model_config.read_bytes());matrix=[];assets=[]
    for c in casevalues:
        aid=c['anonymous_answer_id'];doc=g.document(c['model_response'],g.source_id_for_case(c));spec=candidate.schema_for_document(doc)
        prompt=candidate.make_prompt(c,doc);payload=candidate.payload_for(prompt,spec,public);bound=len(prompt.encode('utf8'))+8192+256
        require(bound<=public['num_ctx'],'FULL_INPUT_CONTEXT_EXCEEDS_FROZEN_LIMIT:'+aid)
        paths={k:a.out/folder/f'{aid}.{suffix}' for k,folder,suffix in [('source_document','source_documents','json'),('schema','schemas','json'),('prompt','prompts','txt'),('payload','request_payloads','json')]}
        for k,value in [('source_document',doc),('schema',spec),('payload',payload)]:write(paths[k],value)
        writebytes(paths['prompt'],prompt.encode('utf8'));manifest=candidate.format_order_manifest(j.read(paths['payload']))
        require(manifest==candidate.format_order_manifest(payload),'STORAGE_CHANGED_ORDER')
        identity={'case_id':c['case_id'],'anonymous_answer_id':aid,'input_sha256':j.digest({'question':c['specific_question'],'question_id':c['question_id'],'protocol':c['model_response'],'references':c['references']}),
            'judge':MODEL,'repeat_index':0,'attempt':1,'phase':'development','round_id':budget.ROUND,
            'contract_sha256':j.digest(contract),'payload_sha256':j.digest(payload),'ordered_payload_sha256':manifest['ordered_payload_sha256'],'candidate':candidate.CANDIDATE_VERSION}
        matrix.append({'anonymous_answer_id':aid,'case_id':c['case_id'],'planned_trial_id':j.digest(identity),'identity':identity,
                       'assets':{k:bind(v) for k,v in paths.items()},'step':steps[c['case_id']],'order_manifest':manifest,'context_bound':bound})
        assets += list(paths.values())
    write(a.out/'matrix.json',matrix)
    frozen=codebindings+sourcebindings+[bind(p) for p in [a.out/n for n in ['expected_contract.json','cases.json','step_inputs.json','model_config.json','matrix.json']]+assets]
    write(a.out/'plan.json',{'status':'frozen_before_generation','ids':a.ids,'phase':'development','planned':len(a.ids),'max_attempts':1,
        'candidate_new_requests_max':len(a.ids),'global_development_remaining_max':10,'frozen_inputs':frozen,
        'deadline_utc':extension.DEADLINE,'original_phasecaps_unchanged':True,'created_utc':j.now(),'actual_command':[sys.executable,*sys.argv]})
    validate(a.out);print(j.canonical({'status':'prepared','ids':a.ids,'planned':len(a.ids),'new_model_calls':0,'plan':bind(a.out/'plan.json')}))
def validate(out):
    plan=j.read(out/'plan.json');base.verify_bindings(plan['frozen_inputs']);require(plan['phase']=='development' and plan['max_attempts']==1,'PLAN_SCOPE')
    cases=j.read(out/'cases.json')['cases'];matrix=j.read(out/'matrix.json');contract=j.read(out/'expected_contract.json')
    require([c['anonymous_answer_id'] for c in cases]==[r['anonymous_answer_id'] for r in matrix]==plan['ids'],'FIXED_ID_ORDER')
    for c,r in zip(cases,matrix):
        require(g.rawsha(c['model_response'])==c['answer_sha256']==r['step']['answer_sha256'],'ANSWER_STEP_HASH')
        require(g.rawsha(c['specific_question'])==c['question_sha256']==r['step']['question_sha256'],'QUESTION_STEP_HASH')
        require(j.digest(c['references'])==r['step']['references_sha256'],'REFERENCES_STEP_HASH')
        require(j.digest(r['identity'])==r['planned_trial_id'] and r['identity']['contract_sha256']==j.digest(contract),'TRIAL_IDENTITY')
        require(r['identity']['judge']==MODEL and r['identity']['phase']=='development' and r['identity']['attempt']==1,'CELL_SCOPE')
        doc=j.read(r['assets']['source_document']['path']);require(doc==g.document(c['model_response'],g.source_id_for_case(c)),'SOURCE_DOCUMENT')
        payload=j.read(r['assets']['payload']['path']);spec=candidate.schema_for_document(doc);prompt=Path(r['assets']['prompt']['path']).read_text(encoding='utf8')
        require(payload==candidate.payload_for(prompt,spec,contract['models'][0]['settings']),'PAYLOAD_VALUES')
        require(candidate.format_order_manifest(payload)==r['order_manifest'],'PAYLOAD_ORDER')
        require(r['identity']['ordered_payload_sha256']==r['order_manifest']['ordered_payload_sha256'],'ORDERED_IDENTITY')
    return plan,cases,matrix,contract
async def execute(out,c,r,public):
    tid=r['planned_trial_id'];at=out/'run/attempts'/f'{tid}_1';tp=out/'run/trials'/f'{tid}.json'
    payload=j.read(r['assets']['payload']['path']);doc=j.read(r['assets']['source_document']['path']);write(at/'http_request_payload.json',payload)
    require(candidate.format_order_manifest(j.read(at/'http_request_payload.json'))==r['order_manifest'],'ATTEMPT_ORDER_DRIFT')
    receipt=budget.reserve('development',tid,MODEL,public['timeout_seconds']);write(at/'request_receipt.json',receipt)
    stage='PROVIDER_TRANSPORT';status='failed';err=None;raw=None;metrics=base.scoring.derive({},r['step'],False)
    try:
        provider=await asyncio.to_thread(base.invoke_transport,public,payload);write(at/'provider_response.json',provider)
        raw=provider.get('response') if isinstance(provider,dict) else None
        if isinstance(raw,str):writebytes(at/'raw_response.txt',raw.encode('utf8'));write(at/'raw_receipt.json',{'raw_sha256':g.rawsha(raw),'source_document':r['assets']['source_document']})
        stage='PROVIDER_COMPLETION';raw=base.validate_provider(provider,public)
        stage='FIELDWISE_CONVERSION';cv=fw.convert(raw,doc,c);write(at/'conversion.json',cv)
        stage='FIELDWISE_NUMERIC_SCORING'
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):num=fw.score_conversion(c,cv,r['step'])
        write(at/'numeric.json',num);metrics=num['metrics'];status='success';stage=None
    except Exception as exc:
        err={'stage':stage,'type':type(exc).__name__,'reason':str(exc)}
        if raw is not None and stage in ['FIELDWISE_CONVERSION','FIELDWISE_NUMERIC_SCORING']:
            try:
                metrics,direct=recovery.recover_direct(raw,doc,r['step']);write(at/'retained_direct_components.json',{'direct':direct,'metrics':metrics,'whole_response_success':False})
            except Exception as sub:err['independent_direct_unavailable']=str(sub)
        write(at/'error.json',err)
    write(tp,{'trial_id':tid,'identity':r['identity'],'anonymous_answer_id':r['anonymous_answer_id'],'status':status,
        'failure_stage':stage,'error':err,'request_id':receipt['request_id'],'attempt':1,'actual_request_made':True,
        'metrics':metrics,'bound_artifacts':[bind(p) for p in sorted(at.iterdir()) if p.is_file()],
        'terminal_utc':j.now(),'formal_eligible':False,'expert_confirmed':False})
    print(j.canonical({'id':r['anonymous_answer_id'],'status':status,'request_index':receipt['package_request_index']}),flush=True)
async def run(a):
    require(a.allow_local_calls,'EXPLICIT_MODEL_CALL_FLAG_REQUIRED');plan,cases,matrix,contract=validate(a.out);extension.install()
    requested=plan['ids'] if a.ids is None else a.ids;require(len(set(requested))==len(requested) and set(requested)<=set(plan['ids']),'PREPARED_IDS_ONLY')
    current,models=base.science_contract(a.out/'model_config.json',True)
    require(all(current[k]==contract[k] for k in base.SCIENCE_KEYS+['models']),'SCIENCE_OR_MODEL_DRIFT')
    log=a.out/'run_commands'/f"{j.now().replace(':','').replace('+','_')}.json";write(log,{'argv':[sys.executable,*sys.argv],'ids':requested,'deadline_utc':extension.DEADLINE})
    for c,r in zip(cases,matrix):
        if r['anonymous_answer_id'] not in requested:continue
        tid=r['planned_trial_id'];tp=a.out/'run/trials'/f'{tid}.json';at=a.out/'run/attempts'/f'{tid}_1'
        if tp.exists():continue
        if any(x.get('trial_id')==tid for x in budget.counts()['requests']) or (at/'request_receipt.json').exists():
            print(j.canonical({'id':r['anonymous_answer_id'],'status':'reserved_nonterminal_no_retry'}),flush=True);continue
        if budget.time_remaining()<=630:break
        base.verify_bindings(plan['frozen_inputs']);await execute(a.out,c,r,models[0]['public'])
def analyze(a):
    p,cases,matrix,contract=validate(a.out);counts=budget.counts();rows=[]
    for r in matrix:
        tid=r['planned_trial_id'];path=a.out/'run/trials'/f'{tid}.json';reservations=[x for x in counts['requests'] if x.get('trial_id')==tid]
        require(len(reservations)<=1,'DUPLICATE_ATTEMPT')
        if path.exists():
            t=j.read(path);require(t['identity']==r['identity'] and t['trial_id']==tid and t['actual_request_made'] is True,'TERMINAL_IDENTITY')
            require(len(reservations)==1 and reservations[0]['request_id']==t['request_id'] and reservations[0]['phase']=='development' and reservations[0]['model']==MODEL,'RECEIPT_BINDING')
            base.verify_bindings(t['bound_artifacts']);row={k:t[k] for k in ['status','failure_stage','error','metrics']}
        else:row={'status':'reserved_nonterminal' if reservations else 'unstarted','failure_stage':None,'error':None,'metrics':base.scoring.derive({},r['step'],False)}
        rows.append({'anonymous_answer_id':r['anonymous_answer_id'],'trial_id':tid,'reserved':bool(reservations),**row})
    summary={'planned':len(rows),'success':sum(x['status']=='success' for x in rows),'failed':sum(x['status']=='failed' for x in rows),
        'pending':sum(x['status'] not in ['success','failed'] for x in rows),'actual_requests':sum(x['reserved'] for x in rows),'package_requests':counts['package'],
        'numeric_coverage':{k:sum(finite(x['metrics'].get(k)) for x in rows) for k in base.scoring.METRICS},
        'complete_numeric_CCE':sum(all(finite(x['metrics'].get(k)) for k in ['Com','Cor','Eff']) for x in rows),
        'scope':'exposed development only; no new confirmation evidence','expert_returns':0,'new_analysis_model_calls':0}
    dest=a.out/'analysis'/j.now().replace(':','').replace('+','_');write(dest/'observations.json',rows);write(dest/'summary.json',summary)
    write(dest/'verification.json',{'status':'pass_identity_and_hashes','plan':bind(a.out/'plan.json'),'all_planned_slots_retained':True,'numerical_replay':False,'new_model_calls':0})
    print(j.canonical({'out':str(dest),**summary}))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','analyze']);p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--ids',nargs='+',choices=ALLOWED);p.add_argument('--model-config',type=Path,default=R/'grounded_development_v11/model_config.json');p.add_argument('--allow-local-calls',action='store_true')
    a=p.parse_args()
    if a.action=='prepare':
        if a.ids is None:a.ids=ALLOWED.copy()
        prepare(a)
    elif a.action=='run':asyncio.run(run(a))
    else:analyze(a)
if __name__=='__main__':main()
