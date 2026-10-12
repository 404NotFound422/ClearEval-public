"""Unfrozen round-two E2/E4 scheduler; confirmation currently exposes only gates.

No import/inspection/--help action reads a sealed confirmation input. All actual
generation needs a root-selected completed development batch and a separate run
authorization. Historical frozen runners, scoring functions and budgets are used
without editing them. E2 is 21 fresh texts/15 pairs; E4 is five answers x two
judges x three repeats. Exact reuse never ignores a changed execution contract.
"""
from __future__ import annotations
import argparse,asyncio,contextlib,copy,csv,io,sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_runner_v10 as base
import cce_grounded_controls_v1 as old_controls
import cce_analyze_grounded_stability_dev_v1 as old_stability
j=base.j;budget=base.budget;grounded=base.grounded;scoring=base.scoring
require=base.require;bind=base.bind;BASE=base.BASE;BACKEND=base.BACKEND
MODEL_NAMES=[base.MODEL,'local_llama3_8b']
CONTROL_SOURCE=ROOT/'artifacts/cce_validation/judges/controls_contract_v2'
PAIR_SOURCE=ROOT/'artifacts/cce_validation/judges/local_controls_supplement_v2/pairs.json'
E4_MODEL_CONFIG=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_stability_dev_v1/model_config.json'

def source_paths(phase):
    require(phase in ['E2','E4'],'CONFIRMATION_BODIES_NOT_IMPLEMENTED_OR_RELEASED')
    return (CONTROL_SOURCE/'cases.json',BASE/'step_inputs_v1/E2.json') if phase=='E2' else (base.SOURCE_CASES,base.STEPS)

def checked_inputs(phase):
    source,steps_path=source_paths(phase);original=j.read(source)['cases'];steps=j.read(steps_path);cases=copy.deepcopy(original)
    require(len(cases)==(21 if phase=='E2' else 5) and len(steps)==len(cases),'FIXED_PHASE_SOURCE_COUNT')
    for index,c in enumerate(cases):
        c['anonymous_answer_id']=f'E2_{index+1:02d}' if phase=='E2' else c['anonymous_answer_id'];s=steps[c['case_id']]
        require(grounded.rawsha(c['model_response'])==c['answer_sha256']==s['answer_sha256'],'ANSWER_STEP_HASH')
        require(grounded.rawsha(c['specific_question'])==c['question_sha256']==s['question_sha256'],'QUESTION_STEP_HASH')
        require(j.digest(c['references'])==s['references_sha256'] and c['question_id']==s['question_id'],'REFERENCE_STEP_IDENTITY')
        require(s['threshold']==.7 and s['encoder']['model']=='all-mpnet-base-v2'
            and s['adapter_sha256']==j.filehash(ROOT/'scripts/cce_validation.py'),'ORIGINAL_STEP_CONFIGURATION')
        base.verify_bindings(s['provenance']);scoring.derive({},s,False)
    pairs=j.read(PAIR_SOURCE) if phase=='E2' else []
    if phase=='E2':
        require(len(pairs)==15 and len({p['pair_id'] for p in pairs})==15,'ORIGINAL_FIFTEEN_PAIRS')
        indexed={c['case_id']:c for c in cases}
        for p in pairs:
            a,b=(indexed[p[k]] for k in ['baseline_case_id','variant_case_id'])
            require(a['question_id']==b['question_id']==p['question_id'] and a['specific_question']==b['specific_question']
                and a['references']==b['references'],'PAIRED_INPUT_CONFIGURATION_CHANGED')
    return cases,steps,pairs

def terminal_summary(out,expected):
    summary=j.read(out/'completion_summary.json');verification=j.read(out/'analysis_verification.json')
    require(summary['status']=='experiment_complete_not_scientific_validation' and summary['planned_observations']==expected
        and summary['actual_observations']==expected and summary['pending']==0,'PREDECESSOR_NOT_ALL_TERMINAL')
    require(verification['status']=='pass','PREDECESSOR_ANALYSIS_NOT_VERIFIED')
    base.verify_bindings(verification['bindings']);base.verify_bindings(summary['bound_observations'])
    return summary

def selection_paths(args):
    paths=[Path(__file__),Path(base.__file__),Path(grounded.__file__),Path(scoring.__file__),Path(budget.__file__),budget.AUTH,
        *source_paths(args.phase),args.model_config,base.CHECKER,base.REVIEW,base.CONFIRMATION_METADATA,
        args.development_out/'plan.json',args.development_out/'expected_contract.json',args.development_out/'matrix.json',
        args.development_out/'completion_summary.json',args.development_out/'analysis_verification.json',
        args.development_out/'independent_fact_audit_v10/summary.json']
    if args.phase=='E2':paths += [PAIR_SOURCE,Path(old_controls.__file__)]
    else:paths += [Path(old_stability.__file__),args.E2_out/'plan.json',args.E2_out/'completion_summary.json',args.E2_out/'analysis_verification.json']
    return paths

def selection_gate(args):
    selected=j.read(args.selection)
    require(selected.get('status')=='selected_after_actual_development' and selected.get('selected_by')=='root_agent'
        and selected.get('candidate_version')==grounded.VERSION and selected.get('phase')==args.phase,'ROOT_FINAL_CANDIDATE_SELECTION_REQUIRED')
    base.verify_required(selected['bindings'],selection_paths(args))
    base.validate(args.development_out);terminal_summary(args.development_out,5)
    for row in j.read(args.development_out/'matrix.json'):base.terminal_identity(args.development_out,row)
    facts=j.read(args.development_out/'independent_fact_audit_v10/summary.json')
    require(facts['status']=='complete' and facts['fixed_answers']==5,'ACTUAL_DEVELOPMENT_FACT_REVIEW_REQUIRED')
    require(facts['explicit_names_denominator']==16 and facts['core_duration_denominator']==31,'FIXED_FACT_DENOMINATORS_CHANGED')
    base.verify_bindings(facts['inputs'])
    if args.phase=='E4':
        terminal_summary(args.E2_out,21)
        validate(args.E2_out)
    require(selected.get('reuse_mode')==args.reuse_mode,'ROOT_REUSE_MODE_MISMATCH')
    return selected

def model_contracts(config,phase):
    a,runner,api,registry=base.readonly_runtime()
    wanted=[base.MODEL] if phase=='E2' else MODEL_NAMES
    models=j.model_configs(SimpleNamespace(model_config=config,models=wanted,temperature=0.,max_output_tokens=8192,timeout_seconds=600))
    require([m['name'] for m in models]==wanted,'FIXED_MODELS_CHANGED')
    contracts={};baseline=j.read(base.BASE_CONTRACT)
    for model in models:
        p=model['public'];require(p['transport_kind']=='ollama_loopback' and p['num_ctx']==98304 and p['max_output_tokens']==8192
            and p['temperature']==0 and p['timeout_seconds']==600,'FIXED_GENERATION_SETTINGS')
        require(p['enable_thinking'] is False or p['enable_thinking'] is None,'THINKING_CONFIGURATION_TYPE')
        if model['name']==base.MODEL:require(p['enable_thinking'] is False and model['family']=='qwen','QWEN_CONFIG_CHANGED')
        else:require(p['enable_thinking'] is None and model['family']=='llama','LLAMA_CONFIG_CHANGED')
        value=j.contract(a,runner,registry,[model])
        require(all(value[k]==baseline[k] for k in base.SCIENCE_KEYS),'ORIGINAL_SCIENCE_CONTRACT_CHANGED')
        value['round2_extraction']={'version':grounded.VERSION,'module_sha256':j.filehash(grounded.__file__),
            'runner_sha256':j.filehash(__file__),'score_adapter_sha256':j.filehash(scoring.__file__),
            'wire_scores_unchanged':True,'decoder_schema':'source_specific_per_cell','max_attempts':1}
        contracts[model['name']]=value
    return contracts,models

def exact_reuse_qualification(source_contract,target_contract,source_payload,target_payload,source_case,target_case,source_step,target_step):
    tests={'complete_contract':source_contract==target_contract,'complete_HTTP_payload':source_payload==target_payload,
        'complete_source_case':source_case==target_case,'complete_step_evidence':source_step==target_step}
    return {'eligible':all(tests.values()),'checks':tests,'no_fields_ignored':True,'status_blind':True}

def prepare(args):
    if (args.out/'plan.json').exists():validate(args.out);return
    require(not list((args.out/'run').glob('**/request_receipt.json')),'NO_PARTIAL_UNFROZEN_BATCH')
    selected=selection_gate(args);cases,steps,pairs=checked_inputs(args.phase)
    contracts,models=model_contracts(args.model_config,args.phase)
    development=j.read(args.development_out/'expected_contract.json')
    require(all(contracts[base.MODEL][k]==development[k] for k in base.SCIENCE_KEYS+['models']),'FOLLOWUP_AND_DEV_MODEL_SCIENCE_DIFFER')
    require(contracts[base.MODEL]['round2_extraction']['module_sha256']==development['round2_extraction']['module_sha256'],'FOLLOWUP_CONVERTER_DIFFERENT')
    args.out.mkdir(parents=True,exist_ok=True)
    j.save(args.out/'cases.json',{'cases':cases});j.save(args.out/'step_inputs.json',steps);j.save(args.out/'pairs.json',pairs)
    (args.out/'model_config.json').write_bytes(args.model_config.read_bytes());j.save(args.out/'expected_contract.json',contracts)
    matrix=[];generated=[];reuse_records=[]
    dev_cases={c['case_id']:c for c in j.read(args.development_out/'cases.json')['cases']}
    dev_matrix={r['case_id']:r for r in j.read(args.development_out/'matrix.json')}
    for c in cases:
        aid=c['anonymous_answer_id'];doc=grounded.document(c['model_response'],grounded.source_id_for_case(c))
        prompt=grounded.make_prompt(c,doc);schema=grounded.schema_for_document(doc)
        bound=len(prompt.encode('utf8'))+8192+256;require(bound<=98304,'CONTEXT_EXCEEDED_NO_TRUNCATION:'+aid)
        docpath=args.out/'source_documents'/f'{aid}.json';schemapath=args.out/'schemas'/f'{aid}.json';promptpath=args.out/'prompts'/f'{aid}.txt'
        j.save(docpath,doc);j.save(schemapath,schema);promptpath.parent.mkdir(parents=True,exist_ok=True);promptpath.write_bytes(prompt.encode('utf8'))
        generated.extend([docpath,schemapath,promptpath])
        for model in models:
            for repeat in range(1 if args.phase=='E2' else 3):
                key=f"{aid}__{model['name']}__r{repeat}";contract=contracts[model['name']]
                payload=base.payload_for(prompt,schema,model['public']);payloadpath=args.out/'request_payloads'/f'{key}.json';j.save(payloadpath,payload);generated.append(payloadpath)
                identity={'case_id':c['case_id'],'input_sha256':j.digest({'question':c['specific_question'],'question_id':c['question_id'],
                    'protocol':c['model_response'],'references':c['references']}),'judge':model['name'],'repeat_index':repeat,
                    'contract_sha256':j.digest(contract),'payload_sha256':j.digest(payload),'round_id':budget.ROUND,'phase':args.phase}
                reuse=None
                if args.phase=='E4' and model['name']==base.MODEL and repeat==0:
                    oldrow=dev_matrix[c['case_id']]
                    qualification=exact_reuse_qualification(development,contract,j.read(oldrow['assets']['payload']['path']),payload,
                        dev_cases[c['case_id']],c,oldrow['step'],steps[c['case_id']])
                    reuse_records.append({'anonymous_answer_id':aid,**qualification})
                    if args.reuse_mode=='exact5':
                        require(qualification['eligible'],'EXACT_REUSE_CONTRACT_MISMATCH_NO_AUTOMATIC_FRESH_FALLBACK:'+aid)
                        base.terminal_identity(args.development_out,oldrow)
                        reuse={'source_out':str(args.development_out),'source_cell':oldrow,'qualification':qualification}
                        identity=oldrow['identity']
                matrix.append({'cell_id':key,'anonymous_answer_id':aid,'case_id':c['case_id'],'question_id':c['question_id'],
                    'judge':model['name'],'repeat_index':repeat,'identity':identity,'planned_trial_id':j.digest(identity),'attempt':1,
                    'conservative_context_bound':bound,'step':steps[c['case_id']],'reuse':reuse,
                    'assets':{'source_document':bind(docpath),'schema':bind(schemapath),'prompt':bind(promptpath),'payload':bind(payloadpath)}})
    count=21 if args.phase=='E2' else 30;reused=sum(r['reuse'] is not None for r in matrix)
    require(len(matrix)==count and reused==(5 if args.reuse_mode=='exact5' else 0),'PLANNED_MATRIX_REUSE_COUNT')
    budget.guard(args.phase,count-reused,600);j.save(args.out/'matrix.json',matrix);j.save(args.out/'reuse_qualification.json',reuse_records)
    paths=[*selection_paths(args),args.selection,args.out/'cases.json',args.out/'step_inputs.json',args.out/'pairs.json',args.out/'model_config.json',
        args.out/'expected_contract.json',args.out/'matrix.json',args.out/'reuse_qualification.json',*generated]
    for contract in contracts.values():paths.extend(base.dependency_paths(contract))
    for s in steps.values():paths.extend(Path(r['path']) for r in s['provenance'])
    # Bind actual predecessor inputs/outputs, including all failures, without an accuracy threshold.
    for predecessor in [args.development_out]+([args.E2_out] if args.phase=='E4' else []):
        summary=j.read(predecessor/'completion_summary.json');paths.extend(Path(b['path']) for b in summary['bound_observations'])
    plan={'status':'frozen_before_generation','phase':args.phase,'candidate_version':grounded.VERSION,'planned_observations':count,
        'planned_new_requests':count-reused,'planned_reused_observations':reused,'max_attempts':1,'reuse_mode':args.reuse_mode,
        'fixed_answers':21 if args.phase=='E2' else 5,'planned_pairs':15 if args.phase=='E2' else None,
        'models':[m['name'] for m in models],'repeats':1 if args.phase=='E2' else 3,'source_selection':bind(args.selection),
        'frozen_inputs':[bind(p) for p in dict.fromkeys(Path(p).resolve() for p in paths)],'no_confirmation_bodies_read':True}
    j.save(args.out/'plan.json',plan);base.record(args.out,'prepare_'+args.phase,new_model_requests=0)
    print(j.canonical({'status':'prepared_not_generated','phase':args.phase,'planned':count,'new':count-reused,'reused':reused}))

def validate(out):
    plan=j.read(out/'plan.json');require(plan['phase'] in ['E2','E4'] and plan['max_attempts']==1,'FROZEN_PHASE_CHANGED')
    base.verify_bindings(plan['frozen_inputs']);cases=j.read(out/'cases.json')['cases'];steps=j.read(out/'step_inputs.json')
    matrix=j.read(out/'matrix.json');contracts=j.read(out/'expected_contract.json');indexed={c['case_id']:c for c in cases}
    require(len(matrix)==plan['planned_observations']==(21 if plan['phase']=='E2' else 30),'MATRIX_DENOMINATOR')
    require(len({(r['case_id'],r['judge'],r['repeat_index']) for r in matrix})==len(matrix),'DUPLICATE_MATRIX_CELL')
    for row in matrix:
        c=indexed[row['case_id']];require(row['planned_trial_id']==j.digest(row['identity']),'TRIAL_HASH_CHANGED')
        base.verify_bindings(list(row['assets'].values()));doc=j.read(row['assets']['source_document']['path'])
        require(doc==grounded.document(c['model_response'],grounded.source_id_for_case(c)),'SOURCE_DOCUMENT_DRIFT')
        require(j.read(row['assets']['schema']['path'])==grounded.schema_for_document(doc),'PER_SOURCE_DECODER_DRIFT')
        public=contracts[row['judge']]['models'][0]['settings'];prompt=Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
        require(j.read(row['assets']['payload']['path'])==base.payload_for(prompt,grounded.schema_for_document(doc),public),'ACTUAL_REQUEST_CONFIGURATION_DRIFT')
        require(row['step']==steps[c['case_id']] and row['step']['answer_sha256']==grounded.rawsha(c['model_response'])
            and row['step']['question_sha256']==grounded.rawsha(c['specific_question']) and row['step']['references_sha256']==j.digest(c['references']),'STEP_SOURCE_DRIFT')
        require(row['identity']['contract_sha256']==j.digest(contracts[row['judge']]),'MODEL_FULL_CONTRACT_IDENTITY')
        if row['reuse']:
            old=row['reuse'];source=Path(old['source_out']);base.validate(source)
            sourcecase=next(c for c in j.read(source/'cases.json')['cases'] if c['case_id']==row['case_id'])
            q=exact_reuse_qualification(j.read(source/'expected_contract.json'),contracts[row['judge']],
                j.read(old['source_cell']['assets']['payload']['path']),j.read(row['assets']['payload']['path']),sourcecase,c,old['source_cell']['step'],row['step'])
            require(q['eligible'] and q==old['qualification'],'EXACT_REUSE_EVIDENCE_DRIFT')
    return plan,cases,matrix,contracts

def preflight(args):
    plan,cases,matrix,expected=validate(args.out);actual,models=model_contracts(args.out/'model_config.json',plan['phase'])
    require(actual==expected,'ENTIRE_RUNTIME_CONTRACT_CHANGED')
    value={'status':'pass','phase':plan['phase'],'planned_observations':len(matrix),'actual_model_metadata':models,
        'bindings':[bind(args.out/'plan.json'),bind(args.out/'matrix.json'),bind(args.out/'expected_contract.json'),bind(__file__)],
        'new_model_requests':0,'scientific_acceptance':False}
    p=args.out/'preflight.json'
    if p.exists():require(j.read(p)==value,'PREFLIGHT_CHANGED')
    else:j.save(p,value)
    base.record(args.out,'preflight_'+plan['phase'],new_model_requests=0);print(j.canonical({'status':'pass','new_model_requests':0}))

def run_gate(args):
    state=validate(args.out);pre=j.read(args.out/'preflight.json');require(pre['status']=='pass','PREFLIGHT_NOT_PASS');base.verify_bindings(pre['bindings'])
    authorization=j.read(args.run_authorization)
    require(authorization.get('status')=='approved_for_local_run' and authorization.get('authorized_by')=='root_agent'
        and authorization.get('phase')==state[0]['phase'],'ROOT_PHASE_RUN_AUTHORIZATION_REQUIRED')
    base.verify_required(authorization['bindings'],[args.out/'plan.json',args.out/'preflight.json',args.out/'matrix.json',args.out/'expected_contract.json',Path(__file__)])
    actual,_=model_contracts(args.out/'model_config.json',state[0]['phase']);require(actual==state[3],'ENTIRE_RUN_CONTRACT_CHANGED')
    return state

async def execute_cell(out,phase,row,case,public):
    tid=row['planned_trial_id'];attempt=out/'run/attempts'/f'{tid}_1';terminal=out/'run/trials'/f'{tid}.json'
    require(row['reuse'] is None and not terminal.exists() and not (attempt/'request_receipt.json').exists(),'CELL_ALREADY_STARTED_OR_REUSED')
    payload=j.read(row['assets']['payload']['path']);doc=j.read(row['assets']['source_document']['path'])
    attempt.mkdir(parents=True,exist_ok=True);j.save(attempt/'http_request_payload.json',payload);(attempt/'prompt.txt').write_bytes(payload['prompt'].encode('utf8'))
    receipt=budget.reserve(phase,tid,row['judge'],public['timeout_seconds']);j.save(attempt/'request_receipt.json',receipt)
    cv=None;numeric=None;errors=[];status='failed';stage='PROVIDER_TRANSPORT';provider=None
    try:
        provider=await asyncio.to_thread(base.invoke_transport,public,payload);j.save(attempt/'provider_response.json',provider)
        raw=provider.get('response') if isinstance(provider,dict) else None
        if isinstance(raw,str):
            (attempt/'raw_source_bound_content.txt').write_bytes(raw.encode('utf8'))
            j.save(attempt/'raw_source_bound_receipt.json',{'raw_response_sha256':grounded.rawsha(raw),
                'raw_text_file_sha256':j.filehash(attempt/'raw_source_bound_content.txt'),'source_document':row['assets']['source_document'],
                'provider_response_kind':'parsed_provider_object_not_network_bytes','raw_text_unchanged':True})
        stage='PROVIDER_COMPLETION';raw=base.validate_provider(provider,public)
        stage='SOURCE_BOUND_CONVERSION';cv=grounded.convert(raw,doc)
        require(cv['legacy_runner_payload']['scores']==base.integrity.parse_judge_object(raw)['scores'],'DIRECT_SCORE_SUBTREE_CHANGED')
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
    trial={'trial_id':tid,'case_id':case['case_id'],'anonymous_answer_id':row['anonymous_answer_id'],'identity':row['identity'],
        'judge':row['judge'],'repeat_index':row['repeat_index'],'phase':phase,'attempt':1,'status':status,'request_id':receipt['request_id'],
        'actual_request_made':True,'terminal_utc':j.now(),'evaluation':{'technical_status':'SUCCESS' if status=='success' else 'FAILED',
            'failure_stage':stage,'grounded_extraction_v10':{'conversion':cv,'conversion_errors':errors,'raw_return_modified':False,'legacy_parser_fallback_used':False},
            'numeric_result':numeric,'metrics':numeric['metrics'] if status=='success' else scoring.derive({},row['step'],False)},
        'bound_artifacts':[bind(p) for p in sorted(attempt.iterdir()) if p.is_file()],'formal_eligible':False,'expert_confirmation':None}
    j.save(terminal,trial);print(j.canonical({'phase':phase,'answer':row['anonymous_answer_id'],'judge':row['judge'],'repeat':row['repeat_index'],
        'status':status,'failure_stage':stage,'package_request_index':receipt['package_request_index']}),flush=True)
    return trial

def trial_location(out,row):
    return Path(row['reuse']['source_out']) if row['reuse'] else out

def terminal_identity(out,row):
    source=trial_location(out,row)
    if row['reuse']:return base.terminal_identity(source,row['reuse']['source_cell'])
    tid=row['planned_trial_id'];attempt=source/'run/attempts'/f'{tid}_1';t=j.read(source/'run/trials'/f'{tid}.json')
    require(t['trial_id']==tid and t['identity']==row['identity'] and t['case_id']==row['case_id'] and t['attempt']==1
        and t['judge']==row['judge'] and t['repeat_index']==row['repeat_index'],'ACTUAL_TERMINAL_IDENTITY')
    require(t['status'] in ['success','failed'],'ACTUAL_TRIAL_NOT_TERMINAL');base.verify_bindings(t['bound_artifacts'])
    receipt=j.read(attempt/'request_receipt.json');require(receipt['trial_id']==tid and receipt['attempt']==1 and receipt['model']==row['judge'],'ACTUAL_RECEIPT_IDENTITY')
    ledger={r['request_id']:r for r in budget.counts()['requests']}
    require(receipt==ledger.get(receipt['request_id']) and t['request_id']==receipt['request_id'],'ACTUAL_REQUEST_LEDGER_IDENTITY')
    require(j.read(attempt/'http_request_payload.json')==j.read(row['assets']['payload']['path']),'ACTUAL_PAYLOAD_CHANGED')
    return t

async def run(args):
    require(args.allow_local_calls,'EXPLICIT_LOCAL_CALL_FLAG_REQUIRED');plan,cases,matrix,contracts=run_gate(args)
    require(type(args.max_new_calls) is int and 1<=args.max_new_calls<=plan['planned_new_requests'],'MAX_NEW_CALLS_LIMIT')
    started={r['trial_id'] for r in budget.counts()['requests']};indexed={c['case_id']:c for c in cases}
    for row in matrix:
        source=trial_location(args.out,row);terminal=source/'run/trials'/f"{row['planned_trial_id']}.json"
        if terminal.exists():terminal_identity(args.out,row)
        else:require(not row['reuse'] and row['planned_trial_id'] not in started
            and not (args.out/'run/attempts'/f"{row['planned_trial_id']}_1/request_receipt.json").exists(),'RESERVED_NONTERMINAL_CELL_NO_RETRY')
    made=0
    for row in matrix:
        if (trial_location(args.out,row)/'run/trials'/f"{row['planned_trial_id']}.json").exists():continue
        if made>=args.max_new_calls:break
        validate(args.out);budget.guard(plan['phase'],1,600)
        await execute_cell(args.out,plan['phase'],row,indexed[row['case_id']],contracts[row['judge']]['models'][0]['settings']);made+=1
    base.record(args.out,'run_'+plan['phase'],new_model_requests=made)
    print(j.canonical({'status':'run_ended_no_retry','phase':plan['phase'],'new_model_requests':made,'planned_observations':len(matrix)}))

def read_observations(out,plan,cases,matrix,contracts):
    indexed={c['case_id']:c for c in cases};rows=[];bindings=[];replays=0
    for row in matrix:
        source=trial_location(out,row);tid=row['planned_trial_id'];terminal=source/'run/trials'/f'{tid}.json'
        metrics=scoring.derive({},row['step'],False);status='pending';stage=None;cv=None
        if terminal.exists():
            t=terminal_identity(out,row);status=t['status'];e=t['evaluation'];stage=e['failure_stage'];cv=e['grounded_extraction_v10']['conversion']
            attempt=source/'run/attempts'/f'{tid}_1';rawpath=attempt/'raw_source_bound_content.txt'
            if rawpath.exists():
                raw=rawpath.read_bytes().decode('utf8');require(j.read(attempt/'provider_response.json')['response']==raw,'RAW_PROVIDER_TEXT_CHANGED')
                require(j.read(attempt/'raw_source_bound_receipt.json')['raw_response_sha256']==grounded.rawsha(raw),'RAW_RECEIPT_CHANGED')
            if status=='success':
                base.validate_provider(j.read(attempt/'provider_response.json'),contracts[row['judge']]['models'][0]['settings'])
                replay=grounded.convert(raw,j.read(row['assets']['source_document']['path']));require(replay==cv==j.read(attempt/'source_bound_conversion.json'),'SOURCE_CONVERSION_REPLAY')
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):numeric=scoring.score_conversion(indexed[row['case_id']],replay,BACKEND,row['step'])
                require(numeric==e['numeric_result']==j.read(attempt/'numeric_result.json'),'ORIGINAL_NUMERIC_REPLAY');metrics=numeric['metrics'];replays+=1
            require(e['metrics']==metrics,'SUCCESS_OR_FAILURE_METRICS_DRIFT');bindings += [bind(terminal),*t['bound_artifacts']]
        rows.append({'anonymous_answer_id':row['anonymous_answer_id'],'case_id':row['case_id'],'question_id':row['question_id'],'judge':row['judge'],
            'repeat_index':row['repeat_index'],'trial_id':tid,'status':status,'failure_stage':stage,'reused':bool(row['reuse']),
            'technical_executable':status=='success','complete_numeric_CCE':status=='success' and all(scoring.finite(metrics[k]) for k in ['Com','Cor','Eff']),
            'metrics':metrics,**metrics,'evidence_state':base.dev7.evidence_state(cv),'judge_contract_sha256':j.digest(contracts[row['judge']]),
            'step_config_sha256':row['step']['step_config_sha256'],'references_sha256':row['step']['references_sha256'],
            'question_sha256':row['step']['question_sha256'],'formal_eligible':False})
    return rows,bindings,replays

def pair_results(rows,pairs,steps):
    indexed={r['case_id']:r for r in rows};result=[]
    for p in pairs:
        a,b=(indexed[p[k]] for k in ['baseline_case_id','variant_case_id'])
        same=all(a[k]==b[k] and a[k] is not None for k in ['judge_contract_sha256','step_config_sha256','references_sha256','question_sha256'])
        both=same and a['technical_executable'] and b['technical_executable'];terminal=a['status']!='pending' and b['status']!='pending'
        row={**p,'same_frozen_configuration':same,'both_arms_technical_complete':both,'baseline_status':a['status'],'variant_status':b['status'],
            'pair_state':'pending' if not terminal else 'available' if both else 'failed_arm','complete_numeric_pair':both and a['complete_numeric_CCE'] and b['complete_numeric_CCE']}
        for metric in scoring.METRICS:
            av,bv=a['metrics'][metric],b['metrics'][metric];available=same and scoring.finite(av) and scoring.finite(bv) and (metric in ['sr','sp'] or both)
            row.update({'baseline_'+metric:av,'variant_'+metric:bv,'available_'+metric:available,'delta_'+metric:bv-av if available else None})
        sa,sb=steps[p['baseline_case_id']],steps[p['variant_case_id']]
        singleton=sa['candidate_reference_ids']==sb['candidate_reference_ids']==[sa['reference_id']] and sb['reference_id']==sa['reference_id']
        row['adaptive_vs_fixed_baseline_reference']={'identical_singleton_pool_verified':singleton,'baseline_reference_id':sa['reference_id'],
            'variant_selected_reference_id':sb['reference_id'],'reference_switch':sb['reference_id']!=sa['reference_id'],
            'fixed_baseline_variant_sr':sb['sr'] if singleton else None,'fixed_baseline_variant_sp':sb['sp'] if singleton else None,
            'no_new_embedding_or_reference_selection':True,'limitation':None if singleton else 'Fixed-reference score not available from verified cached inputs.'}
        row['response_observations']=old_controls.anomaly_observations(row);result.append(row)
    require(len(result)==15,'ALL_FIFTEEN_PAIRS_REQUIRED');return result

def write_table(out,name,rows):
    j.save(out/(name+'.json'),rows)
    if rows:
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/(name+'.csv')).open('w',encoding='utf8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
            for r in rows:writer.writerow({k:j.canonical(v) if isinstance(v,(dict,list)) else v for k,v in r.items()})

def analyze(args):
    plan,cases,matrix,contracts=validate(args.out);rows,bindings,replays=read_observations(args.out,plan,cases,matrix,contracts)
    write_table(args.out,'observations',rows);write_table(args.out,'per_answer',rows)
    terminal=sum(r['status']!='pending' for r in rows);success=sum(r['status']=='success' for r in rows);extras={}
    if plan['phase']=='E2':
        pairs=pair_results(rows,j.read(args.out/'pairs.json'),j.read(args.out/'step_inputs.json'));write_table(args.out,'per_pair',pairs)
        extras={'planned_pairs':15,'technical_complete_pairs':sum(p['both_arms_technical_complete'] for p in pairs),
            'complete_numeric_pairs':sum(p['complete_numeric_pair'] for p in pairs),'all_pairs_same_contract':all(p['same_frozen_configuration'] for p in pairs)}
        conditions=[]
        for name in sorted({p['condition'] for p in pairs}):
            group=[p for p in pairs if p['condition']==name];entry={'condition':name,'planned_pairs':len(group),
                'technical_complete_pairs':sum(p['both_arms_technical_complete'] for p in group),'complete_numeric_pairs':sum(p['complete_numeric_pair'] for p in group)}
            for metric in scoring.METRICS:
                values=[p['delta_'+metric] for p in group if p['available_'+metric]]
                entry.update({metric+'_available_pairs':len(values),metric+'_negative':sum(v < -1e-12 for v in values),
                    metric+'_unchanged':sum(abs(v)<=1e-12 for v in values),metric+'_positive':sum(v>1e-12 for v in values)})
            conditions.append(entry)
        write_table(args.out,'condition_results',conditions);extras['condition_results']=conditions
    else:
        # Pending cells occupy their original slots; step values are known independently.
        stats=old_stability.summarize(rows,base.IDS,MODEL_NAMES)
        for name in ['within','between','same_repeat_pairs','category_summary','common_numeric_by_repeat']:write_table(args.out,name,stats[name])
        j.save(args.out/'common_numeric_all_six.json',stats['common_numeric_all_six'])
        extras={'within_groups':160,'between_groups':80,'same_repeat_metric_pairs':240,'answer_denominator':5,
            'metric_groups_are_not_independent_answers':True,'cached_steps_not_judge_stability_success':True,
            'category_summary':stats['category_summary'],'common_numeric_all_six':stats['common_numeric_all_six']}
    summary={'status':'experiment_complete_not_scientific_validation' if terminal==len(matrix) else 'partial_experiment_not_scientific_validation',
        'phase':plan['phase'],'planned_observations':len(matrix),'actual_observations':terminal,'technical_successes':success,'technical_failures':terminal-success,
        'pending':len(matrix)-terminal,'planned_new_requests':plan['planned_new_requests'],'planned_reused_observations':plan['planned_reused_observations'],
        'complete_numeric_CCE':sum(r['complete_numeric_CCE'] for r in rows),'component_coverage':{k:sum(scoring.finite(r[k]) for r in rows if r['status']!='pending') for k in scoring.METRICS},
        'raw_conversion_and_numeric_replays':replays,'bound_observations':bindings,'source_fact_acceptance':'requires_separate_review',
        'new_model_requests_from_analysis':0,'expert_returns':0,**extras}
    j.save(args.out/'completion_summary.json',summary)
    j.save(args.out/'analysis_verification.json',{'status':'pass','all_planned_terminal':terminal==len(matrix),'planned_observations':len(matrix),
        'terminal_observations':terminal,'successful_raw_numeric_replays':replays,'failure_SR_SP_retained_other_metrics_NA':True,
        'bindings':[bind(args.out/'plan.json'),bind(args.out/'matrix.json'),bind(args.out/'observations.json'),bind(args.out/'completion_summary.json')],
        'science_acceptance_not_implied':True,'new_model_requests':0})
    base.record(args.out,'analyze_'+plan['phase'],terminal_observations=terminal,new_model_requests=0)
    print(j.canonical({k:v for k,v in summary.items() if k not in ['bound_observations','condition_results','category_summary']}))

def confirmation_gate_design():
    return {'status':'interface_design_only_no_input_release','planned_observations':16,'answer_denominator':8,'models':MODEL_NAMES,
        'max_attempts':1,'phase':'confirmation','required_before_any_body_read':['root_final_candidate_selection',
            'final_development_facts_and_terminal_summary','all_21_E2_terminal_and_verification','all_30_E4_terminal_and_verification',
            'prospective_new_eight_metadata_freeze','root_final_configuration_no_post_confirmation_tuning',
            'frozen_reference_catalog_projection_policy_original_encoder_and_threshold','root_final_release_and_controller_hash'],
        'release_input_interface':'root supplies metadata-only eight path/SHA descriptors after final authorization',
        'body_reader_implemented':False,'body_reads':0,'old_confirmation_reuse_allowed':False,'new_model_requests':0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run','analyze','confirmation-design'])
    p.add_argument('--phase',choices=['E2','E4'],default='E2');p.add_argument('--out',type=Path);p.add_argument('--model-config',type=Path)
    p.add_argument('--development-out',type=Path,default=base.DEFAULT_OUT);p.add_argument('--E2-out',type=Path,default=BASE/'grounded_controls_v10')
    p.add_argument('--selection',type=Path);p.add_argument('--run-authorization',type=Path);p.add_argument('--reuse-mode',choices=['fresh','exact5'],default='fresh')
    p.add_argument('--allow-local-calls',action='store_true');p.add_argument('--max-new-calls',type=int,default=1)
    a=p.parse_args()
    if a.action=='confirmation-design':print(j.canonical(confirmation_gate_design()));return
    a.out=(a.out or BASE/('grounded_controls_v10' if a.phase=='E2' else 'grounded_stability_v10')).resolve();require(a.out.is_relative_to(BASE),'NEW_ROUND_OUTPUT_ONLY')
    a.model_config=a.model_config or (base.DEFAULT_MODEL_CONFIG if a.phase=='E2' else E4_MODEL_CONFIG)
    a.selection=a.selection or a.out/'root_selection.json';a.run_authorization=a.run_authorization or a.out/'root_run_authorization.json'
    require(a.phase=='E4' or a.reuse_mode=='fresh','E2_MUST_USE_ALL_TWENTY_ONE_NEW_REQUESTS')
    if a.action=='run':asyncio.run(run(a))
    else:globals()[a.action](a)

if __name__=='__main__':main()
