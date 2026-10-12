"""Round-3 controller with explicit original and evaluation source documents.

Preparation reads the explicitly supplied cases. Only `run --allow-local-calls`
can invoke the local provider. No failed or interrupted request is retried.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, copy, csv, hashlib, importlib, io, json, math, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_runner_v11 as base
import cce_round3_budget as budget
j=base.j
DEFAULT_CANDIDATE='cce_generation_order_only_v1'
DEFAULT_PROCESSOR='cce_posthoc_components_v6'
METRICS=list(base.scoring.DIRECT)+list(base.scoring.EGES)+['sr','sp','Com','Cor','Eff','IA','HV']

def require(ok,reason):
    if not ok: raise ValueError(reason)
def ordered(value): return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
def bind(p): return {'path':str(Path(p).resolve()),'sha256':j.filehash(p)}
def save_once(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream: stream.write(ordered(value)+b'\n')
def bytes_once(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream: stream.write(value)
def finite(x): return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)
def module(name,api):
    require(name.startswith('cce_') and name.isidentifier(),'LOCAL_MODULE_NAME_REQUIRED')
    m=importlib.import_module(name)
    require(Path(m.__file__).resolve().parent==ROOT/'scripts','LOCAL_SCRIPT_MODULE_REQUIRED')
    require(all(callable(getattr(m,k,None)) for k in api),'MODULE_API_MISSING:'+name)
    return m
def dependencies(*modules):
    seen=set()
    def visit(m):
        name=getattr(m,'__name__','');p=getattr(m,'__file__',None)
        if not p or not name.startswith('cce_'):return
        p=Path(p).resolve()
        if p in seen:return
        seen.add(p)
        for value in vars(m).values():
            if hasattr(value,'__file__'):visit(value)
    for m in modules:visit(m)
    return sorted(seen,key=str)
def checked_cases(case_path,step_path):
    obj=j.read(case_path);cases=obj['cases'];steps=j.read(step_path)
    require(isinstance(cases,list) and cases,'NONEMPTY_CASES_REQUIRED')
    require(len({c['case_id'] for c in cases})==len(cases),'DUPLICATE_CASE_ID')
    require(set(steps)=={c['case_id'] for c in cases},'EXACT_STEP_CASE_SET_REQUIRED')
    for c in cases:
        s=steps[c['case_id']]
        require(base.grounded.rawsha(c['model_response'])==s['answer_sha256'],'ANSWER_STEP_BINDING')
        require(base.grounded.rawsha(c['specific_question'])==s['question_sha256'],'QUESTION_STEP_BINDING')
        require(j.digest(c['references'])==s['references_sha256'],'REFERENCE_STEP_BINDING')
        for k in ['answer_sha256','question_sha256']:
            if k in c:require(c[k]==s[k],'CASE_DECLARED_HASH_CHANGED:'+k)
        require(c['question_id']==s['question_id'] and s['threshold']==.7,'STEP_QUESTION_THRESHOLD')
        require(s['encoder']['model']=='all-mpnet-base-v2','STEP_ENCODER_CHANGED')
        require(s['adapter_sha256']==j.filehash(ROOT/'scripts/cce_validation.py'),'STEP_CORE_CHANGED')
        base.verify_bindings(s['provenance'])
        base.scoring.derive({},s,False)
    return cases,steps
def command_record(out,action,**kw):
    stamp=j.now().replace(':','').replace('.','_').replace('+','_')
    save_once(out/'commands'/f'{action}_{stamp}.json',{'actual_command':[sys.executable,*sys.argv],
        'created_utc':j.now(),'action':action,**kw})

def prepare(args):
    out=Path(args.out).resolve();require(not out.exists(),'NEW_OUTPUT_DIRECTORY_REQUIRED')
    require(type(args.repeats) is int and args.repeats>=1,'POSITIVE_REPEAT_COUNT')
    cases,steps=checked_cases(args.cases,args.steps)
    candidate=module(args.candidate,['schema_for_document','make_prompt','payload_for'])
    processor=module(args.processor,['independent_processing'])
    contract,models=base.science_contract(Path(args.model_config),True)
    require(len(models)==1,'ONE_QWEN_EVALUATOR_REQUIRED');public=models[0]['public']
    require(public['model']=='qwen3.8:27b-q8_0-local','CURRENT_AUTHORIZED_QWEN_ONLY')
    require(len(cases)*args.repeats<=budget.LIMITS[args.phase],'PLANNED_MATRIX_EXCEEDS_PHASE_ALLOCATION')
    budget.guard(args.phase,0,0)
    dep=dependencies(candidate,processor,base,budget)
    science_paths=[ROOT/p for p in contract['files']]+[ROOT/'KnowledgeBase/source_registry.json',
        ROOT/'dataset/Q+AR/src/demand_vectors_all.json',j.HIST,ROOT/'models/Ollama_LLM.py']
    inputs=[Path(__file__),Path(args.cases),Path(args.steps),Path(args.model_config),budget.AUTH,*dep,*science_paths]
    frozen=[bind(p) for p in dict.fromkeys(inputs)]
    processing_fingerprint=j.digest({'candidate':bind(candidate.__file__),
        'processor_dependencies':[bind(p) for p in dependencies(processor)],
        'candidate_dependencies':[bind(p) for p in dependencies(candidate)],
        'science':{k:contract[k] for k in base.SCIENCE_KEYS},'public_model':public})
    out.mkdir(parents=True)
    save_once(out/'cases.json',{'cases':cases});save_once(out/'steps.json',steps)
    bytes_once(out/'model_config.json',Path(args.model_config).read_bytes())
    save_once(out/'expected_contract.json',contract)
    matrix=[];assets=[]
    for c in cases:
        cid=c['case_id'];stem=j.digest({'case_id':cid})[:24]
        original_doc=base.grounded.document(c['model_response'],base.grounded.source_id_for_case(c))
        view_builder=getattr(candidate,'evaluation_document',None)
        doc=view_builder(c,original_doc) if callable(view_builder) else original_doc
        original_path=out/'original_source_documents'/(stem+'.json')
        save_once(original_path,original_doc)
        mapping_builder=getattr(candidate,'source_mapping',None)
        if callable(mapping_builder):
            mapping_path=out/'source_mappings'/(stem+'.json')
            save_once(mapping_path,mapping_builder(c,doc));assets.append(mapping_path)
        schema=candidate.schema_for_document(doc);prompt=candidate.make_prompt(c,doc)
        payload=candidate.payload_for(prompt,schema,public)
        require(payload['format']==schema and payload['prompt']==prompt,'PAYLOAD_SOURCE_CHANGED')
        require(list(schema['properties'])==['scores','score_evidence','grounded_extraction'],'SCORE_FIRST_SCHEMA_REQUIRED')
        files={k:out/folder/(stem+ext) for k,folder,ext in [('doc','source_documents','.json'),
            ('schema','schemas','.json'),('payload','request_payloads','.json'),('prompt','prompts','.txt')]}
        for k,v in [('doc',doc),('schema',schema),('payload',payload)]:save_once(files[k],v)
        bytes_once(files['prompt'],prompt.encode('utf8'))
        ordered_payload_sha256=hashlib.sha256(ordered(payload)).hexdigest()
        context_bound=len(prompt.encode('utf8'))+public['max_output_tokens']+256
        for repeat in range(args.repeats):
            cache_key=j.digest({'answer_sha256':steps[cid]['answer_sha256'],'question_sha256':steps[cid]['question_sha256'],
                'references_sha256':steps[cid]['references_sha256'],'step_sha256':j.digest(steps[cid]),
                'ordered_payload_sha256':ordered_payload_sha256,'processing_fingerprint':processing_fingerprint,'repeat_index':repeat})
            identity={'round_id':budget.ROUND,'phase':args.phase,'case_id':cid,'repeat_index':repeat,'attempt':1,
                'cache_key':cache_key,'batch_out':str(out),'contract_sha256':j.digest(contract)}
            matrix.append({'case_id':cid,'anonymous_answer_id':c.get('anonymous_answer_id',cid),
                'question_id':c['question_id'],'repeat_index':repeat,'identity':identity,
                'planned_trial_id':j.digest(identity),'cache_key':cache_key,'step':steps[cid],
                'assets':{k:bind(v) for k,v in files.items()},'ordered_payload_sha256':ordered_payload_sha256,
                'context_bound':context_bound,'fits_context':context_bound<=public['num_ctx']})
        assets.extend(files.values());assets.append(original_path)
    save_once(out/'matrix.json',matrix)
    frozen += [bind(p) for p in [out/n for n in ['cases.json','steps.json','model_config.json','expected_contract.json','matrix.json']]+assets]
    save_once(out/'plan.json',{'status':'frozen_before_generation','round_id':budget.ROUND,'phase':args.phase,
        'planned_observations':len(matrix),'case_count':len(cases),'repeats':args.repeats,'max_attempts':1,
        'candidate':args.candidate,'processor':args.processor,'processing_fingerprint':processing_fingerprint,
        'public_model':public,'judge':models[0]['name'],'frozen_inputs':frozen,
        'authorization':bind(budget.AUTH),'created_utc':j.now(),'context_overflow_cells':sum(not r['fits_context'] for r in matrix),
        'provider_response_kind':'parsed_provider_object; model response text preserved as UTF-8 bytes',
        'partial_components_are_not_full_success':True,'no_automatic_retries':True})
    validate(out);command_record(out,'prepare',new_model_requests=0)
    return {'status':'prepared','planned':len(matrix),'new_model_requests':0}

def validate(out,query_service=False):
    out=Path(out).resolve();p=j.read(out/'plan.json');base.verify_bindings(p['frozen_inputs'])
    require(p['round_id']==budget.ROUND and p['phase'] in budget.LIMITS and p['max_attempts']==1,'PLAN_ROUND_OR_PHASE')
    require(p['authorization']==bind(budget.AUTH),'PLAN_AUTHORIZATION_CHANGED');budget.authorization()
    cases,steps=checked_cases(out/'cases.json',out/'steps.json');matrix=j.read(out/'matrix.json');contract=j.read(out/'expected_contract.json')
    expected=[(c['case_id'],r) for c in cases for r in range(p['repeats'])]
    require([(r['case_id'],r['repeat_index']) for r in matrix]==expected,'FULL_PLANNED_MATRIX_CHANGED')
    require(len(matrix)==p['planned_observations'] and len(cases)==p['case_count'],'PLAN_COUNTS_CHANGED')
    for r in matrix:
        require(type(r['repeat_index']) is int and r['identity']['repeat_index']==r['repeat_index'],'TYPED_REPEAT_IDENTITY')
        require(r['identity']['phase']==p['phase'] and r['identity']['round_id']==budget.ROUND
                and r['identity']['case_id']==r['case_id'] and r['identity']['batch_out']==str(out),'CELL_IDENTITY')
        require(r['planned_trial_id']==j.digest(r['identity']) and r['identity']['cache_key']==r['cache_key'],'TRIAL_DIGEST')
        require(r['step']==steps[r['case_id']],'CELL_STEP_CHANGED')
        payload=j.read(r['assets']['payload']['path'])
        require(hashlib.sha256(ordered(payload)).hexdigest()==r['ordered_payload_sha256'],'ORDERED_PAYLOAD_CHANGED')
        require(list(payload['format']['properties'])==['scores','score_evidence','grounded_extraction'],'SCHEMA_ORDER_CHANGED')
    if query_service:
        actual,models=base.science_contract(out/'model_config.json',True)
        require(all(actual[k]==contract[k] for k in base.SCIENCE_KEYS+['models']),'RUNTIME_SCIENCE_OR_MODEL_CHANGED')
        require(models[0]['public']==p['public_model'],'PUBLIC_MODEL_CHANGED')
    return p,cases,matrix,contract

def terminal_path(out,row):return Path(out)/'run/trials'/(row['planned_trial_id']+'.json')
def attempt_path(out,row):return Path(out)/'run/attempts'/(row['planned_trial_id']+'_1')
def terminal(out,row,seen=None):
    seen=set() if seen is None else seen;path=terminal_path(out,row).resolve()
    require(path not in seen,'REUSE_CYCLE');seen.add(path)
    t=j.read(path);p=j.read(Path(out)/'plan.json')
    require(t['trial_id']==row['planned_trial_id'] and t['identity']==row['identity'] and t['case_id']==row['case_id'],'TERMINAL_IDENTITY')
    require(t['anonymous_answer_id']==row['anonymous_answer_id'] and type(t['attempt']) is int and t['attempt']==1,'TERMINAL_LABEL_ATTEMPT')
    require(type(t['repeat_index']) is int and t['repeat_index']==row['repeat_index'] and t['phase']==p['phase'],'TERMINAL_REPEAT_PHASE')
    require(t['status'] in ['success','partial','failed','local_failed'],'TERMINAL_STATUS')
    base.verify_bindings(t['bound_artifacts'])
    if t.get('source_kind')=='exact_success_cache':
        require(t['actual_request_made'] is False and t['status']=='success','REUSE_NOT_NEW_SUCCESS')
        binding=t['reuse']['source_terminal'];base.verify_bindings([binding]);sourceout=Path(t['reuse']['source_out'])
        sp,sc,sm,sct=validate(sourceout)
        hits=[x for x in sm if x['planned_trial_id']==t['reuse']['source_trial_id']]
        require(len(hits)==1 and hits[0]['cache_key']==row['cache_key'],'EXACT_REUSE_CACHE_KEY')
        source=terminal(sourceout,hits[0],seen)
        require(source['status']=='success' and t['metrics']==source['metrics'],'EXACT_REUSE_SUCCESS_AND_VALUES')
        require(binding==bind(terminal_path(sourceout,hits[0])),'EXACT_REUSE_LOCATION')
        return t
    attempt=attempt_path(out,row)
    if attempt.exists():base.verify_required(t['bound_artifacts'],[x for x in attempt.iterdir() if x.is_file()])
    ledger={x['request_id']:x for x in budget.counts()['requests']}
    if t['actual_request_made'] is False:
        require(t['status']=='local_failed' and t['failure_stage']=='LOCAL_CONTEXT_LIMIT' and not row['fits_context'],'LOCAL_FAILURE_BASIS')
        require(not (attempt/'request_receipt.json').exists() and not any(x.get('trial_id')==t['trial_id'] for x in ledger.values()),'LOCAL_FAILURE_HAS_REQUEST')
        require(t['metrics']==base.scoring.derive({},row['step'],False),'LOCAL_FAILURE_METRICS')
        return t
    require(t['actual_request_made'] is True,'ACTUAL_REQUEST_BOOLEAN')
    receipt=j.read(attempt/'request_receipt.json')
    require(type(receipt['attempt']) is int and receipt['attempt']==1 and receipt['trial_id']==t['trial_id'],'RECEIPT_TRIAL_ATTEMPT')
    require(receipt['phase']==p['phase'] and receipt['round_id']==budget.ROUND and receipt['model']==p['public_model']['model'],'RECEIPT_PHASE_MODEL')
    require(ledger.get(receipt['request_id'])==receipt and t['request_id']==receipt['request_id'],'RECEIPT_LEDGER')
    require((attempt/'http_request_payload.json').read_bytes()==Path(row['assets']['payload']['path']).read_bytes(),'ACTUAL_PAYLOAD_BYTES')
    rawpath=attempt/'raw_response.txt';providerpath=attempt/'provider_response.json'
    if rawpath.exists():
        raw=rawpath.read_bytes().decode('utf8');provider=j.read(providerpath)
        require(provider.get('response')==raw,'PROVIDER_RAW_TEXT')
        require(j.read(attempt/'raw_receipt.json')['raw_sha256']==j.filehash(rawpath),'RAW_RECEIPT')
    if t['status']=='success':require(t['provider_complete'] is True and t['full_conversion_success'] is True,'SUCCESS_REQUIRES_COMPLETE_PROVIDER_AND_CONVERSION')
    processing=attempt/'processing.json'
    if processing.exists():require(j.read(processing)['metrics']==t['metrics'],'PROCESSING_METRICS_CHANGED')
    else:require(t['metrics']==base.scoring.derive({},row['step'],False),'FAILURE_WITHOUT_PROCESSING_METRICS')
    return t

async def execute_cell(out,row,case,plan,processor):
    attempt=attempt_path(out,row);path=terminal_path(out,row)
    require(not path.exists() and not (attempt/'request_receipt.json').exists(),'CELL_ALREADY_STARTED')
    common={'trial_id':row['planned_trial_id'],'identity':row['identity'],'case_id':row['case_id'],
        'anonymous_answer_id':row['anonymous_answer_id'],'attempt':1,'repeat_index':row['repeat_index'],'phase':plan['phase'],
        'source_kind':'new_local_request','metrics':base.scoring.derive({},row['step'],False),
        'provider_complete':False,'full_conversion_success':False,'formal_eligible':False,'expert_confirmation':None}
    if not row['fits_context']:
        t={**common,'status':'local_failed','actual_request_made':False,'failure_stage':'LOCAL_CONTEXT_LIMIT',
            'errors':[{'reason':'Frozen full prompt exceeds configured context bound; no truncation or request'}],
            'bound_artifacts':[],'terminal_utc':j.now()}
        save_once(path,t);return t
    attempt.mkdir(parents=True,exist_ok=True)
    payload=j.read(row['assets']['payload']['path']);doc=j.read(row['assets']['doc']['path'])
    bytes_once(attempt/'http_request_payload.json',Path(row['assets']['payload']['path']).read_bytes())
    bytes_once(attempt/'prompt.txt',payload['prompt'].encode('utf8'))
    public=plan['public_model'];receipt=budget.reserve(plan['phase'],row['planned_trial_id'],public['model'],public['timeout_seconds'])
    save_once(attempt/'request_receipt.json',receipt)
    errors=[];provider=None;raw=None;processing=None;provider_complete=False;stage='PROVIDER_TRANSPORT'
    try:
        provider=await asyncio.to_thread(base.invoke_transport,public,payload)
        save_once(attempt/'provider_response.json',provider)
        raw=provider.get('response') if isinstance(provider,dict) else None
        if isinstance(raw,str):
            bytes_once(attempt/'raw_response.txt',raw.encode('utf8'))
            save_once(attempt/'raw_receipt.json',{'raw_sha256':j.filehash(attempt/'raw_response.txt'),
                'provider':bind(attempt/'provider_response.json'),'source_document':row['assets']['doc'],
                'response_kind':'model response text from parsed provider object; not original HTTP bytes','raw_unchanged':True})
        stage='PROVIDER_COMPLETION'
        try:base.validate_provider(provider,public);provider_complete=True
        except Exception as exc:errors.append({'stage':stage,'type':type(exc).__name__,'reason':str(exc)})
        # Wrong provider model must not be assigned to the frozen evaluator.
        require(isinstance(provider,dict) and provider.get('model')==public['model'],'PROVIDER_MODEL_IDENTITY_CHANGED')
        if isinstance(raw,str) and raw.strip():
            stage='COMPONENT_PROCESSING'
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                processing=processor.independent_processing(raw,doc,case,row['step'])
            require(isinstance(processing,dict) and set(processing['metrics'])==set(METRICS),'PROCESSOR_METRIC_CONTRACT')
            save_once(attempt/'processing.json',processing)
    except Exception as exc:errors.append({'stage':stage,'type':type(exc).__name__,'reason':str(exc)})
    full=bool(processing and processing.get('full_conversion_success') is True)
    metrics=processing['metrics'] if processing else common['metrics']
    has_component=any(finite(metrics[k]) for k in base.scoring.DIRECT+base.scoring.EGES)
    status='success' if provider_complete and full else ('partial' if has_component else 'failed')
    failure_stage=None if status=='success' else (errors[0]['stage'] if errors else 'COMPONENT_PROCESSING')
    if errors:save_once(attempt/'errors.json',errors)
    t={**common,'status':status,'actual_request_made':True,'request_id':receipt['request_id'],
       'provider_complete':provider_complete,'full_conversion_success':full,'metrics':metrics,
       'failure_stage':failure_stage,'errors':errors,'terminal_utc':j.now(),
       'bound_artifacts':[bind(p) for p in sorted(attempt.iterdir()) if p.is_file()]}
    save_once(path,t)
    print(j.canonical({'case_id':row['case_id'],'repeat':row['repeat_index'],'status':status,
        'provider_complete':provider_complete,'full_conversion_success':full,'request_index':receipt['package_request_index']}),flush=True)
    return t

def reuse_index(paths):
    index={}
    for path in paths:
        out=Path(path).resolve();plan,cases,matrix,contract=validate(out)
        for r in matrix:
            if not terminal_path(out,r).exists():continue
            t=terminal(out,r)
            if t['status']=='success':index.setdefault(r['cache_key'],(out,r,t))
    return index

async def run(args):
    require(args.allow_local_calls,'EXPLICIT_ROOT_LOCAL_CALL_FLAG_REQUIRED')
    require(type(args.max_new_calls) is int and args.max_new_calls>=0,'MAX_NEW_CALLS_NONNEGATIVE')
    out=Path(args.out).resolve();plan,cases,matrix,contract=validate(out,True)
    processor=module(plan['processor'],['independent_processing']);bycase={c['case_id']:c for c in cases}
    caches=reuse_index(args.reuse_from)
    started={x['trial_id'] for x in budget.counts()['requests']}
    for r in matrix:
        if terminal_path(out,r).exists():terminal(out,r)
        else:require(r['planned_trial_id'] not in started and not (attempt_path(out,r)/'request_receipt.json').exists(),'RESERVED_NONTERMINAL_NO_RETRY')
    calls=0;reused=0
    for r in matrix:
        if terminal_path(out,r).exists():continue
        if r['cache_key'] in caches:
            so,sr,st=caches[r['cache_key']]
            t=copy.deepcopy(st);t.update(trial_id=r['planned_trial_id'],identity=r['identity'],case_id=r['case_id'],
                anonymous_answer_id=r['anonymous_answer_id'],phase=plan['phase'],repeat_index=r['repeat_index'],
                actual_request_made=False,source_kind='exact_success_cache',bound_artifacts=[],terminal_utc=j.now(),
                reuse={'source_out':str(so),'source_trial_id':sr['planned_trial_id'],'source_terminal':bind(terminal_path(so,sr)),
                       'new_request_count':0,'same_observation_not_an_additional_independent_repeat':True})
            save_once(terminal_path(out,r),t);terminal(out,r);reused+=1;continue
        if r['fits_context'] and calls>=args.max_new_calls:break
        validate(out);budget.guard(plan['phase'],1 if r['fits_context'] else 0,plan['public_model']['timeout_seconds'] if r['fits_context'] else 0)
        await execute_cell(out,r,bycase[r['case_id']],plan,processor)
        calls+=int(r['fits_context'])
    command_record(out,'run',new_model_requests=calls,exact_success_reuses=reused)
    return {'new_model_requests':calls,'exact_success_reuses':reused,'planned_observations':len(matrix)}

def analyze(args):
    out=Path(args.out).resolve();plan,cases,matrix,contract=validate(out);rows=[];bindings=[]
    processor=module(plan['processor'],['independent_processing']);bycase={c['case_id']:c for c in cases}
    for r in matrix:
        data={'case_id':r['case_id'],'anonymous_answer_id':r['anonymous_answer_id'],'question_id':r['question_id'],
            'repeat_index':r['repeat_index'],'trial_id':r['planned_trial_id'],'status':'pending',
            'metrics':base.scoring.derive({},r['step'],False),'actual_request_made':False,'cache_reuse':False,
            'complete_numeric_CCE':False,'technical_and_numeric_complete':False}
        if terminal_path(out,r).exists():
            t=terminal(out,r);data.update({k:t[k] for k in ['status','metrics','actual_request_made','provider_complete','full_conversion_success','failure_stage']})
            data['cache_reuse']=t.get('source_kind')=='exact_success_cache'
            if not data['cache_reuse'] and (attempt_path(out,r)/'processing.json').exists():
                raw=(attempt_path(out,r)/'raw_response.txt').read_bytes().decode('utf8');doc=j.read(r['assets']['doc']['path'])
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):replay=processor.independent_processing(raw,doc,bycase[r['case_id']],r['step'])
                require(replay==j.read(attempt_path(out,r)/'processing.json'),'EXACT_COMPONENT_REPLAY_CHANGED')
            data['complete_numeric_CCE']=all(finite(data['metrics'][k]) for k in ['Com','Cor','Eff','IA','HV'])
            data['technical_and_numeric_complete']=t['status']=='success' and data['complete_numeric_CCE']
            bindings.extend([bind(terminal_path(out,r)),*t['bound_artifacts']])
        rows.append(data)
    complete=sum(x['status']!='pending' for x in rows)
    summary={'phase':plan['phase'],'planned_observations':len(rows),'actual_observations':complete,
       'technical_successes':sum(x['status']=='success' for x in rows),'partial_observations':sum(x['status']=='partial' for x in rows),
       'technical_failures':sum(x['status'] in ['failed','local_failed'] for x in rows),'pending':len(rows)-complete,
       'actual_new_requests':sum(x['actual_request_made'] for x in rows),'exact_success_reuses':sum(x['cache_reuse'] for x in rows),
       'complete_numeric_CCE':sum(x['complete_numeric_CCE'] for x in rows),
       'technical_and_numeric_complete':sum(x['technical_and_numeric_complete'] for x in rows),
       'component_coverage':{k:sum(x['status']!='pending' and finite(x['metrics'][k]) for x in rows) for k in METRICS},
       'status':'experiment_complete' if complete==len(rows) else 'incomplete','no_pending_cell_inferred_failed':True,
       'SR_SP_are_reused_deterministic_values_not_judge_repeatability':True,'scientific_correctness_not_certified':True}
    stamp=j.now().replace(':','').replace('.','_').replace('+','_');folder=out/'analysis'/stamp
    save_once(folder/'observations.json',rows);save_once(folder/'completion_summary.json',summary)
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'observations.csv').open('x',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['case_id','anonymous_answer_id','question_id','repeat_index','trial_id','status',*METRICS]);writer.writeheader()
        for x in rows:writer.writerow({**{k:x[k] for k in writer.fieldnames if k not in METRICS},**x['metrics']})
    verification={'status':'pass','all_planned_terminal':complete==len(rows),'original_frozen_inputs_verified':True,
        'numeric_replay_of_available_processing_verified':True,'bindings':[bind(out/'plan.json'),*bindings,
           bind(folder/'observations.json'),bind(folder/'observations.csv'),bind(folder/'completion_summary.json')],'new_model_calls':0}
    save_once(folder/'analysis_verification.json',verification)
    # Only a convenience pointer is mutable; every analysis snapshot is retained.
    j.save(out/'latest_analysis.json',{'summary':bind(folder/'completion_summary.json'),'verification':bind(folder/'analysis_verification.json'),
        'observations':bind(folder/'observations.json')})
    command_record(out,'analyze',new_model_requests=0,analysis_directory=str(folder));return summary

def cli():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    q=subs.add_parser('prepare');q.add_argument('--cases',type=Path,required=True);q.add_argument('--steps',type=Path,required=True)
    q.add_argument('--candidate',default=DEFAULT_CANDIDATE);q.add_argument('--processor',default=DEFAULT_PROCESSOR)
    q.add_argument('--phase',choices=list(budget.LIMITS),required=True);q.add_argument('--repeats',type=int,default=1)
    q.add_argument('--model-config',type=Path,default=base.DEFAULT_MODEL_CONFIG);q.add_argument('--out',type=Path,required=True)
    q=subs.add_parser('run');q.add_argument('--out',type=Path,required=True);q.add_argument('--allow-local-calls',action='store_true')
    q.add_argument('--max-new-calls',type=int,required=True);q.add_argument('--reuse-from',type=Path,nargs='*',default=[])
    q=subs.add_parser('analyze');q.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=prepare(a) if a.command=='prepare' else asyncio.run(run(a)) if a.command=='run' else analyze(a)
    print(j.canonical(result))
if __name__=='__main__':cli()
