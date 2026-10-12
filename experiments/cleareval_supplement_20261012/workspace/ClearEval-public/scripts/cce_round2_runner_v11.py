"""Round-two source-bound development runner. Importing this file does no I/O.

Only the fixed public five-answer development phase is currently implemented.
The old scoring adapter, source converter and independent checker remain separate.
No successful or failed cell is retried. A reserved nonterminal cell blocks resume.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, csv, io, json, sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_round2_budget as budget
import cce_grounded_extraction_v11 as grounded
import cce_grounded_development_v7 as dev7
import cce_grounded_offline_scoring_v1 as scoring
import evaluator_integrity as integrity

BASE=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
DEFAULT_OUT=BASE/'grounded_development_v11'
SOURCE_CASES=dev7.OUT/'cases.json'
STEPS=BASE/'step_inputs_v1/development.json'
DEFAULT_MODEL_CONFIG=dev7.OUT/'model_config.json'
CHECKER=BASE/'fact_audit_checker_v11/freeze.json'
REVIEW=BASE/'regression_design_v1/v11_review/independent_review.json'
CONFIRMATION_METADATA=BASE/'confirmation_sampling_v1/freeze_summary.json'
BASE_CONTRACT=ROOT/'artifacts/cce_validation/optimizer_20261010/model_probe_v1/expected_contract.json'
IDS=['A01','A02','A03','A04','A05']
MODEL='local_qwen27b_q8_development'
SCIENCE_KEYS=['files','demands','source_registry_sha256','scoring_version']
BACKEND=SimpleNamespace(grounded=grounded,gate_components=dev7.gate_components,evidence_state=dev7.evidence_state)

def require(ok,reason):
    if not ok:raise ValueError(reason)

def bind(p):return {'path':str(Path(p).resolve()),'sha256':j.filehash(p)}

def verify_bindings(rows):
    require(isinstance(rows,list),'BINDINGS_MUST_BE_LIST')
    for row in rows:require(j.filehash(row['path'])==row['sha256'],'BOUND_FILE_CHANGED:'+row['path'])

def verify_required(rows,paths):
    verify_bindings(rows);indexed={str(Path(r['path']).resolve()):r['sha256'] for r in rows}
    for p in paths:require(indexed.get(str(Path(p).resolve()))==j.filehash(p),'REQUIRED_BINDING_MISSING:'+str(p))

def readonly_runtime():
    a=SimpleNamespace(question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',demand_manifest=None)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        runner,api,registry=j.runtime(a)
    return a,runner,api,registry

def model_args(config):
    return SimpleNamespace(model_config=config,models=[MODEL],temperature=0.,max_output_tokens=8192,timeout_seconds=600)

def science_contract(config,query_service):
    a,runner,api,registry=readonly_runtime()
    if query_service:models=j.model_configs(model_args(config))
    else:
        raise ValueError('ACTUAL_READ_ONLY_MODEL_VERIFICATION_REQUIRED')
    require(len(models)==1 and models[0]['name']==MODEL and models[0]['family']=='qwen','FIXED_DEVELOPMENT_MODEL')
    p=models[0]['public']
    require(p['transport_kind']=='ollama_loopback' and p['num_ctx']==98304 and p['max_output_tokens']==8192
        and p['temperature']==0 and p['timeout_seconds']==600 and p['enable_thinking'] is False,'DEVELOPMENT_GENERATION_CONFIG_CHANGED')
    contract=j.contract(a,runner,registry,models);baseline=j.read(BASE_CONTRACT)
    require(all(contract[k]==baseline[k] for k in SCIENCE_KEYS),'ORIGINAL_SCIENCE_CONTRACT_CHANGED')
    return contract,models

def checked_cases(path=SOURCE_CASES,step_path=STEPS):
    cases=j.read(path)['cases'];steps=j.read(step_path)
    require([c['anonymous_answer_id'] for c in cases]==IDS and len(steps)==5,'FIXED_FIVE_CASES_REQUIRED')
    for c in cases:
        s=steps[c['case_id']]
        require(grounded.rawsha(c['model_response'])==c['answer_sha256']==s['answer_sha256'],'ANSWER_STEP_BINDING')
        require(grounded.rawsha(c['specific_question'])==c['question_sha256']==s['question_sha256'],'QUESTION_STEP_BINDING')
        require(j.digest(c['references'])==s['references_sha256'],'REFERENCE_STEP_BINDING')
        require(c['question_id']==s['question_id'] and s['threshold']==.7 and s['encoder']['model']=='all-mpnet-base-v2','ORIGINAL_STEP_CONFIGURATION')
        require(s['adapter_sha256']==j.filehash(ROOT/'scripts/cce_validation.py'),'ORIGINAL_STEP_CORE_CHANGED')
        verify_bindings(s['provenance'])
        scoring.derive({},s,False)
    return cases,steps

def decision_required(config):
    return [Path(__file__),SOURCE_CASES,STEPS,config,Path(grounded.__file__),CHECKER,REVIEW,
        CONFIRMATION_METADATA,Path(budget.__file__),budget.AUTH,Path(scoring.__file__),Path(dev7.__file__),BASE_CONTRACT]

def check_decision(path,config):
    decision=j.read(path)
    require(decision.get('status')=='approved_before_prepare' and decision.get('selected_by')=='root_agent'
        and decision.get('phase')=='development' and decision.get('candidate_version')==grounded.VERSION,'ROOT_PREPARE_DECISION_REQUIRED')
    verify_required(decision['bindings'],decision_required(config))
    checker=j.read(CHECKER);review=j.read(REVIEW);confirmation=j.read(CONFIRMATION_METADATA)
    require(checker['status']=='frozen_before_v11_generation' and checker['grounded_module']['sha256']==j.filehash(grounded.__file__), 'FROZEN_CHECKER_MODULE_BINDING')
    require(checker['checker_sha256']==j.filehash(ROOT/'scripts/cce_audit_grounded_facts_v11.py'),'CHECKER_CODE_DRIFT')
    for key in ['grounded_module','software_probes','original_checker','inventory','regression_facts','independent_review','source_relation_software_controls']:
        verify_bindings([checker[key]])
    require(review['status']=='pass' and review['module_sha256']==j.filehash(grounded.__file__),'INDEPENDENT_SOURCE_REVIEW_REQUIRED')
    require(confirmation['selected_count']==8 and confirmation['forbid_development_use'] is True
        and confirmation['selected_bodies_released'] is False,'NEW_CONFIRMATION_METADATA_FREEZE_REQUIRED')
    budget.authorization()
    return decision

def payload_for(prompt,schema,public):
    payload={'model':public['model'],'prompt':prompt,'format':schema,'stream':False,
        'options':{'num_ctx':public['num_ctx'],'num_predict':public['max_output_tokens'],'temperature':public['temperature']}}
    if public['enable_thinking'] is not None:payload['think']=public['enable_thinking']
    return payload

def dependency_paths(contract):
    paths=[ROOT/p for p in contract['files']]+[ROOT/'KnowledgeBase/source_registry.json',j.HIST,
        ROOT/'dataset/Q+AR/src/demand_vectors_all.json',ROOT/'scripts/cce_audit_grounded_facts_v11.py']
    for module in list(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p:
            p=Path(p).resolve()
            if p.suffix=='.py' and p.is_relative_to(ROOT) and p.is_file():paths.append(p)
    checker=j.read(CHECKER)
    paths.extend(Path(checker[k]['path']) for k in ['grounded_module','software_probes','original_checker','inventory','regression_facts','independent_review','source_relation_software_controls'])
    return list(dict.fromkeys(paths))

def record(out,action,**details):
    p=out/'actual_commands.json';rows=j.read(p) if p.exists() else []
    rows.append({'utc':j.now(),'action':action,'argv':[sys.executable,*sys.argv],'runner_sha256':j.filehash(__file__),**details});j.save(p,rows)

def prepare(args):
    out=args.out
    if (out/'plan.json').exists():validate(out);print(j.canonical({'status':'frozen_plan_reused','new_model_requests':0}));return
    require(not list((out/'run').glob('**/request_receipt.json')),'REQUESTS_EXIST_WITHOUT_PLAN')
    decision=check_decision(args.decision,args.model_config);cases,steps=checked_cases()
    budget.guard('development',5,600)
    contract,models=science_contract(args.model_config,True);public=models[0]['public']
    out.mkdir(parents=True,exist_ok=True)
    (out/'cases.json').write_bytes(SOURCE_CASES.read_bytes());(out/'step_inputs.json').write_bytes(STEPS.read_bytes())
    (out/'model_config.json').write_bytes(args.model_config.read_bytes())
    contract['round2_extraction']={'version':grounded.VERSION,'module_sha256':j.filehash(grounded.__file__),
        'runner_sha256':j.filehash(__file__),'score_adapter_sha256':j.filehash(scoring.__file__),
        'wire_scores_unchanged':True,'decoder_schema':'source_specific_per_cell','max_attempts':1}
    j.save(out/'expected_contract.json',contract)
    matrix=[];generated=[]
    for c in cases:
        aid=c['anonymous_answer_id'];doc=grounded.document(c['model_response'],grounded.source_id_for_case(c))
        schema=grounded.schema_for_document(doc);prompt=grounded.make_prompt(c,doc)
        bound=len(prompt.encode('utf8'))+8192+256;require(bound<=98304,'CONTEXT_EXCEEDS_FROZEN_LIMIT_NO_TRUNCATION:'+aid)
        paths={'source_document':out/'source_documents'/f'{aid}.json','schema':out/'schemas'/f'{aid}.json',
            'prompt':out/'prompts'/f'{aid}.txt','payload':out/'request_payloads'/f'{aid}.json'}
        j.save(paths['source_document'],doc);j.save(paths['schema'],schema)
        paths['prompt'].parent.mkdir(parents=True,exist_ok=True);paths['prompt'].write_bytes(prompt.encode('utf8'))
        payload=payload_for(prompt,schema,public);j.save(paths['payload'],payload)
        identity={'case_id':c['case_id'],'input_sha256':j.digest({'question':c['specific_question'],'question_id':c['question_id'],
            'protocol':c['model_response'],'references':c['references']}),'judge':MODEL,'repeat_index':0,
            'contract_sha256':j.digest(contract),'payload_sha256':j.digest(payload),'round_id':budget.ROUND}
        matrix.append({'anonymous_answer_id':aid,'case_id':c['case_id'],'question_id':c['question_id'],'identity':identity,
            'planned_trial_id':j.digest(identity),'attempt':1,'conservative_context_bound':bound,
            'prompt_raw_sha256':grounded.rawsha(prompt),'assets':{k:bind(v) for k,v in paths.items()},'step':steps[c['case_id']]})
        generated.extend(paths.values())
    j.save(out/'matrix.json',matrix)
    paths=decision_required(args.model_config)+[args.decision,*dependency_paths(contract),out/'cases.json',out/'step_inputs.json',
        out/'model_config.json',out/'expected_contract.json',out/'matrix.json',*generated]
    for s in steps.values():paths.extend(Path(r['path']) for r in s['provenance'])
    plan={'status':'frozen_before_generation','phase':'development','candidate_version':grounded.VERSION,'planned_observations':5,
        'planned_new_requests':5,'max_attempts':1,'num_ctx':98304,'max_output_tokens':8192,'temperature':0,'timeout_seconds':600,
        'starting_counts':{k:v for k,v in budget.counts().items() if k!='requests'},'source_decision':bind(args.decision),
        'frozen_inputs':[bind(p) for p in dict.fromkeys(Path(p).resolve() for p in paths)],
        'new_confirmation_bodies_read':False,'old_confirmation_bodies_read':False,'expert_holdout_read':False}
    j.save(out/'plan.json',plan);record(out,'prepare',new_model_requests=0)
    print(j.canonical({'status':'prepared_five_not_generated','plan':str(out/'plan.json'),'new_model_requests':0}))

def validate(out):
    plan=j.read(out/'plan.json');require(plan['phase']=='development' and plan['planned_observations']==5 and plan['max_attempts']==1,'PLAN_SCOPE_CHANGED')
    verify_bindings(plan['frozen_inputs']);cases,steps=checked_cases(out/'cases.json',out/'step_inputs.json')
    matrix=j.read(out/'matrix.json');contract=j.read(out/'expected_contract.json')
    require([r['anonymous_answer_id'] for r in matrix]==IDS,'MATRIX_DENOMINATOR_CHANGED')
    for row,c in zip(matrix,cases):
        require(row['planned_trial_id']==j.digest(row['identity']) and row['case_id']==c['case_id'],'TRIAL_IDENTITY_CHANGED')
        verify_bindings(list(row['assets'].values()))
        doc=j.read(row['assets']['source_document']['path']);prompt=Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
        require(doc==grounded.document(c['model_response'],grounded.source_id_for_case(c)),'SOURCE_DOCUMENT_DRIFT')
        require(j.read(row['assets']['schema']['path'])==grounded.schema_for_document(doc),'DYNAMIC_SCHEMA_DRIFT')
        public=contract['models'][0]['settings']
        require(j.read(row['assets']['payload']['path'])==payload_for(prompt,grounded.schema_for_document(doc),public),'FROZEN_PAYLOAD_DRIFT')
        require(row['step']==steps[c['case_id']] and grounded.rawsha(prompt)==row['prompt_raw_sha256'],'CELL_SOURCE_BINDING')
    return plan,cases,matrix,contract

def preflight(args):
    plan,cases,matrix,expected=validate(args.out)
    actual,models=science_contract(args.out/'model_config.json',True)
    require(all(actual[k]==expected[k] for k in SCIENCE_KEYS+['models']),'ACTUAL_SCIENCE_OR_MODEL_DRIFT')
    result={'status':'pass','scope':'read_only_preflight_not_scientific_acceptance','planned_observations':5,
        'bindings':[bind(args.out/'plan.json'),bind(args.out/'matrix.json'),bind(args.out/'expected_contract.json'),bind(__file__)],
        'actual_model_metadata':models,'original_science_keys_equal':SCIENCE_KEYS,'new_model_requests':0,'utc':j.now()}
    p=args.out/'preflight.json'
    if p.exists():
        old=j.read(p);require(old['bindings']==result['bindings'] and old['actual_model_metadata']==models,'PREFLIGHT_DRIFT');result=old
    else:j.save(p,result)
    record(args.out,'preflight',new_model_requests=0);print(j.canonical({'status':'pass','new_model_requests':0}))

def run_gate(out,authorization):
    values=validate(out);pre=j.read(out/'preflight.json');require(pre['status']=='pass','PREFLIGHT_REQUIRED');verify_bindings(pre['bindings'])
    auth=j.read(authorization)
    require(auth.get('status')=='approved_for_local_run' and auth.get('authorized_by')=='root_agent','ROOT_RUN_AUTHORIZATION_REQUIRED')
    verify_required(auth['bindings'],[out/'plan.json',out/'preflight.json',Path(__file__),out/'expected_contract.json',out/'matrix.json'])
    actual,_=science_contract(out/'model_config.json',True);expected=values[3]
    require(all(actual[k]==expected[k] for k in SCIENCE_KEYS+['models']),'RUN_CONTRACT_OR_MODEL_DRIFT')
    return values

def invoke_transport(public,payload):
    from models.Ollama_LLM import LocalOllamaHTTPClient
    client=LocalOllamaHTTPClient(public['host'],public['timeout_seconds'])
    try:return client.generate(**payload)
    finally:client.close()

def validate_provider(provider,public):
    require(isinstance(provider,dict),'PROVIDER_OBJECT_REQUIRED')
    require(provider.get('model')==public['model'],'PROVIDER_MODEL_IDENTITY_CHANGED')
    require(provider.get('done') is True,'PROVIDER_INCOMPLETE')
    reason=provider.get('done_reason');count=provider.get('eval_count')
    require(reason not in ['length','max_tokens','limit'],'PROVIDER_OUTPUT_LIMIT')
    require(bool(reason) or not (type(count) is int and count>=public['max_output_tokens']),'PROVIDER_LIMIT_WITHOUT_STOP')
    raw=provider.get('response');require(isinstance(raw,str) and bool(raw.strip()),'PROVIDER_CONTENT_EMPTY')
    return raw

async def execute_cell(out,row,case,public):
    tid=row['planned_trial_id'];attempt=out/'run/attempts'/f'{tid}_1';terminal=out/'run/trials'/f'{tid}.json'
    require(not terminal.exists() and not (attempt/'request_receipt.json').exists(),'CELL_ALREADY_STARTED_NO_RETRY')
    payload=j.read(row['assets']['payload']['path']);doc=j.read(row['assets']['source_document']['path'])
    attempt.mkdir(parents=True,exist_ok=True);j.save(attempt/'http_request_payload.json',payload)
    (attempt/'prompt.txt').write_bytes(payload['prompt'].encode('utf8'))
    receipt=budget.reserve('development',tid,MODEL,public['timeout_seconds']);j.save(attempt/'request_receipt.json',receipt)
    cv=None;numeric=None;errors=[];status='failed';stage='PROVIDER_TRANSPORT';provider=None
    try:
        provider=await asyncio.to_thread(invoke_transport,public,payload)
        j.save(attempt/'provider_response.json',provider)
        raw=provider.get('response') if isinstance(provider,dict) else None
        if isinstance(raw,str):
            (attempt/'raw_source_bound_content.txt').write_bytes(raw.encode('utf8'))
            j.save(attempt/'raw_source_bound_receipt.json',{'raw_response_sha256':grounded.rawsha(raw),
                'raw_text_file_sha256':j.filehash(attempt/'raw_source_bound_content.txt'),'source_document':row['assets']['source_document'],
                'provider_response_kind':'parsed_provider_object_not_network_bytes','raw_text_unchanged':True})
        stage='PROVIDER_COMPLETION';raw=validate_provider(provider,public)
        stage='SOURCE_BOUND_CONVERSION';cv=grounded.convert(raw,doc)
        require(cv['legacy_runner_payload']['scores']==integrity.parse_judge_object(raw)['scores'],'SCORE_SUBTREE_CHANGED')
        j.save(attempt/'source_bound_conversion.json',cv);j.save(attempt/'projected_legacy_payload.json',cv['legacy_runner_payload'])
        (attempt/'projected_legacy_content.txt').write_bytes(cv['legacy_runner_content'].encode('utf8'))
        stage='ORIGINAL_OFFLINE_NUMERIC_SCORING'
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):numeric=scoring.score_conversion(case,cv,BACKEND,row['step'])
        j.save(attempt/'numeric_result.json',numeric);status='success';stage=None
    except Exception as exc:
        error={'stage':stage,'type':type(exc).__name__,'reason':str(exc),'legacy_parser_fallback_permitted':False,
            'provider_object_available':provider is not None,'actual_request_reserved':True}
        if hasattr(exc,'source_name_occurrence_audit'):
            error['source_name_occurrence_audit']=exc.source_name_occurrence_audit
        errors.append(error);j.save(attempt/'failure.json',error)
        if stage=='SOURCE_BOUND_CONVERSION':j.save(attempt/'source_bound_conversion_error.json',error)
    metrics=numeric['metrics'] if status=='success' else scoring.derive({},row['step'],False)
    trial={'trial_id':tid,'case_id':case['case_id'],'anonymous_answer_id':row['anonymous_answer_id'],'identity':row['identity'],
        'attempt':1,'status':status,'terminal_utc':j.now(),'request_id':receipt['request_id'],'actual_request_made':True,
        'evaluation':{'technical_status':'SUCCESS' if status=='success' else 'FAILED','failure_stage':stage,
            'grounded_extraction_v11':{'conversion':cv,'conversion_errors':errors,'raw_return_modified':False,
                'legacy_parser_fallback_used':False},'numeric_result':numeric,'metrics':metrics},
        'bound_artifacts':[bind(p) for p in sorted(attempt.iterdir()) if p.is_file()],
        'formal_eligible':False,'expert_confirmation':None}
    j.save(terminal,trial)
    print(j.canonical({'answer':row['anonymous_answer_id'],'status':status,'failure_stage':stage,'package_request_index':receipt['package_request_index']}),flush=True)
    return trial

def terminal_identity(out,row):
    tid=row['planned_trial_id'];p=out/'run/trials'/f'{tid}.json';attempt=out/'run/attempts'/f'{tid}_1'
    t=j.read(p);require(t['trial_id']==tid and t['identity']==row['identity'] and t['case_id']==row['case_id'] and t['attempt']==1,'TERMINAL_IDENTITY_DRIFT')
    require(t['status'] in ['success','failed'],'NONTERMINAL_TRIAL');verify_bindings(t['bound_artifacts'])
    receipt=j.read(attempt/'request_receipt.json');require(receipt['trial_id']==tid and receipt['attempt']==1 and receipt['model']==MODEL,'RECEIPT_IDENTITY_DRIFT')
    ledger={r['request_id']:r for r in budget.counts()['requests']}
    require(ledger.get(receipt['request_id'])==receipt and t['request_id']==receipt['request_id'],'LEDGER_RECEIPT_DRIFT')
    require(j.read(attempt/'http_request_payload.json')==j.read(row['assets']['payload']['path']),'ACTUAL_PAYLOAD_DRIFT')
    return t

async def run(args):
    require(args.allow_local_calls,'EXPLICIT_LOCAL_CALL_FLAG_REQUIRED')
    require(type(args.max_new_calls) is int and 1<=args.max_new_calls<=5,'MAX_NEW_CALLS_RANGE')
    plan,cases,matrix,contract=run_gate(args.out,args.run_authorization)
    ledger=budget.counts()['requests'];started={r['trial_id'] for r in ledger}
    for row in matrix:
        terminal=args.out/'run/trials'/f"{row['planned_trial_id']}.json"
        if terminal.exists():terminal_identity(args.out,row)
        else:require(row['planned_trial_id'] not in started and not (args.out/'run/attempts'/f"{row['planned_trial_id']}_1/request_receipt.json").exists(),'RESERVED_NONTERMINAL_CELL_REQUIRES_SEPARATE_INTERRUPTION_EVIDENCE_NO_RETRY')
    made=0
    for row,c in zip(matrix,cases):
        if (args.out/'run/trials'/f"{row['planned_trial_id']}.json").exists():continue
        if made>=args.max_new_calls:break
        validate(args.out);budget.guard('development',1,600)
        await execute_cell(args.out,row,c,contract['models'][0]['settings']);made+=1
    record(args.out,'run',new_model_requests=made);print(j.canonical({'status':'run_pass_ended_without_retry','new_model_requests':made,'planned_observations':5}))

def analyze(args):
    plan,cases,matrix,contract=validate(args.out);rows=[];bindings=[];replay_success=0
    for row,c in zip(matrix,cases):
        p=args.out/'run/trials'/f"{row['planned_trial_id']}.json";metrics=scoring.derive({},row['step'],False)
        if not p.exists():
            rows.append({'anonymous_answer_id':row['anonymous_answer_id'],'case_id':c['case_id'],'question_id':c['question_id'],
                'trial_id':row['planned_trial_id'],'status':'pending','metrics':metrics,'technical_executable':False,'complete_numeric_CCE':False});continue
        t=terminal_identity(args.out,row);attempt=args.out/'run/attempts'/f"{row['planned_trial_id']}_1";e=t['evaluation'];cv=e['grounded_extraction_v11']['conversion']
        provider_path=attempt/'provider_response.json';raw_path=attempt/'raw_source_bound_content.txt'
        if raw_path.exists():
            raw=raw_path.read_bytes().decode('utf8');require(j.read(provider_path).get('response')==raw,'RAW_PROVIDER_TEXT_CHANGED')
            require(j.read(attempt/'raw_source_bound_receipt.json')['raw_response_sha256']==grounded.rawsha(raw),'RAW_TEXT_RECEIPT_DRIFT')
        if t['status']=='success':
            public=contract['models'][0]['settings'];validate_provider(j.read(provider_path),public)
            replay=grounded.convert(raw,j.read(row['assets']['source_document']['path']))
            require(replay==cv==j.read(attempt/'source_bound_conversion.json'),'FULL_RAW_CONVERSION_REPLAY_FAILED')
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):numeric=scoring.score_conversion(c,replay,BACKEND,row['step'])
            require(numeric==e['numeric_result']==j.read(attempt/'numeric_result.json'),'ORIGINAL_NUMERIC_REPLAY_FAILED')
            metrics=numeric['metrics'];replay_success+=1
        require(metrics==e['metrics'],'SAVED_METRICS_OR_FAILURE_NA_CHANGED')
        rows.append({'anonymous_answer_id':row['anonymous_answer_id'],'case_id':c['case_id'],'question_id':c['question_id'],
            'trial_id':row['planned_trial_id'],'status':t['status'],'technical_executable':t['status']=='success',
            'failure_stage':e['failure_stage'],'metrics':metrics,'component_gated_proposals':{k:metrics[k] for k in scoring.DIRECT+scoring.EGES},
            'evidence_state':dev7.evidence_state(cv),'complete_numeric_CCE':t['status']=='success' and all(scoring.finite(metrics[k]) for k in ['Com','Cor','Eff','IA','HV']),
            'source_fact_acceptance':'requires_separate_frozen_checker','deterministic_steps_retained':True,'formal_eligible':False})
        bindings.extend([bind(p),*t['bound_artifacts']])
    terminal=sum(r['status']!='pending' for r in rows);success=sum(r['status']=='success' for r in rows)
    j.save(args.out/'per_answer.json',rows)
    with (args.out/'per_answer.csv').open('w',encoding='utf8',newline='') as f:
        fields=['anonymous_answer_id','case_id','question_id','trial_id','status','failure_stage',*scoring.METRICS];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({**{k:r.get(k) for k in fields if k not in scoring.METRICS},**r['metrics']})
    summary={'status':'experiment_complete_not_scientific_validation' if terminal==5 else 'partial_experiment_not_scientific_validation',
        'planned_observations':5,'actual_observations':terminal,'technical_successes':success,'technical_failures':terminal-success,'pending':5-terminal,
        'complete_numeric_CCE':sum(r['complete_numeric_CCE'] for r in rows),'fixed_answer_denominator':5,
        'component_coverage':{k:sum(scoring.finite(r['metrics'][k]) for r in rows if r['status']!='pending') for k in scoring.METRICS},
        'raw_conversion_and_numeric_replays':replay_success,'bound_observations':bindings,
        'fact_acceptance_status':'pending_separate_frozen_checker','expert_returns':0,'new_model_requests_from_analysis':0}
    j.save(args.out/'completion_summary.json',summary)
    j.save(args.out/'analysis_verification.json',{'status':'pass','all_five_terminal':terminal==5,'planned_observations':5,
        'terminal_observations':terminal,'successful_raw_numeric_replays':replay_success,'failure_SR_SP_retained_other_metrics_NA':True,
        'bindings':[bind(args.out/'plan.json'),bind(args.out/'matrix.json'),bind(args.out/'per_answer.json'),bind(args.out/'completion_summary.json')],
        'science_acceptance_not_implied':True,'new_model_requests':0})
    record(args.out,'analyze',terminal_observations=terminal,new_model_requests=0);print(j.canonical({k:v for k,v in summary.items() if k!='bound_observations'}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run','analyze'])
    p.add_argument('--out',type=Path,default=DEFAULT_OUT);p.add_argument('--model-config',type=Path,default=DEFAULT_MODEL_CONFIG)
    p.add_argument('--decision',type=Path);p.add_argument('--run-authorization',type=Path)
    p.add_argument('--allow-local-calls',action='store_true');p.add_argument('--max-new-calls',type=int,default=5)
    args=p.parse_args();args.out=args.out.resolve();require(args.out.is_relative_to(BASE),'OUTPUT_MUST_BE_NEW_ROUND_NAMESPACE')
    if args.decision is None:args.decision=args.out/'root_decision.json'
    if args.run_authorization is None:args.run_authorization=args.out/'root_run_authorization.json'
    if args.action=='run':asyncio.run(run(args))
    else:globals()[args.action](args)

if __name__=='__main__':main()
