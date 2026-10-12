"""Eight prospectively selected answers; unchanged v11 generation, frozen fieldwise processing.

prepare exports bodies only after writing a code/input freeze. run is explicit,
Qwen-only, one attempt, and shares the original locked budget. No old batch edits.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, copy, csv, io, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_runner_v11 as base
import cce_round2_confirmation_qwen_only_v1 as exporter
import cce_fieldwise_scoring_v1 as fw
j=base.j;budget=base.budget;g=base.grounded
R2=budget.OUT;OUT=R2/'fieldwise_confirmation_v1';SAMPLING=R2/'fieldwise_confirmation_sampling_v1'
STEP_ROOT=ROOT/'artifacts/cce_validation/method_family_steps_v1'
DEADLINE='2026-10-10T10:21:00+00:00';MODEL=base.MODEL
FIXED_FW='9bd6e7439dac00fae35ccb9667c13e09dd29aadbb3e0af5c1fbca46b5403f311'


def require(ok,msg):
    if not ok:raise ValueError(msg)
def bind(p):return base.bind(p)
def once(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(obj if isinstance(obj,bytes) else (j.canonical(obj)+'\n').encode('utf8'))
def save(p,obj):j.save(p,obj)
def finite(x):return type(x) in (int,float) and math.isfinite(x)
def csvrows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dependencies(contract):
    modules=[fw,fw.fieldwise_base,fw.operation_scope,fw.duration_scope,fw.noncore_scope,fw.labels,base,g,base.scoring,base.dev7,base.integrity,budget,j,exporter]
    return list(dict.fromkeys([Path(__file__),*[Path(m.__file__) for m in modules],*base.dependency_paths(contract),budget.AUTH]))
def install_clock(out):
    record=j.read(out/'time_window.json');expected=j.read(out/'preexport_freeze.json')
    require(bind(out/'time_window.json')==expected['time_window'],'TIME_RECORD_CHANGED')
    require(record['deadline_utc']==DEADLINE and record['original_authorization']==bind(budget.AUTH),'TIME_SCOPE_CHANGED')
    require(record['phase_limits']==budget.LIMITS and record['max_attempts']==1,'COUNT_LIMITS_CHANGED')
    def remaining():
        budget.authorization();require(bind(out/'time_window.json')==expected['time_window'],'TIME_RECORD_CHANGED_DURING_RUN')
        return (datetime.fromisoformat(DEADLINE)-datetime.now(timezone.utc)).total_seconds()
    budget.time_remaining=remaining
def reserve(out,tid):
    with j.ledger_lock(budget.LEDGER):
        count=budget.guard('confirmation',1,600);rid=j.digest({'trial_id':tid,'attempt':1})
        require(all(r.get('request_id')!=rid for r in j.ledger_rows(budget.LEDGER)),'CELL_ALREADY_RESERVED_NO_RETRY')
        row={'event':'request_started','request_id':rid,'trial_id':tid,'attempt':1,'model':MODEL,
            'started_utc':j.now(),'package_request_index':count['package']+1,'round_id':budget.ROUND,'phase':'confirmation',
            'authorization_sha256':budget.AUTH_SHA,'time_window_sha256':j.filehash(out/'time_window.json'),'effective_deadline_utc':DEADLINE}
        with budget.LEDGER.open('a',encoding='utf8') as f:f.write(j.canonical(row)+'\n')
    return row


def prepare(args):
    out=args.out
    require(not (out/'preexport_freeze.json').exists(),'PREPARATION_ALREADY_STARTED_NO_SILENT_REBUILD')
    require(j.filehash(fw.__file__)==FIXED_FW,'FIELDWISE_FINAL_CODE_CHANGED')
    selected=j.read(SAMPLING/'selection_metadata_frozen.json');summary=j.read(SAMPLING/'freeze_summary.json')
    require(j.filehash(SAMPLING/'selection_metadata_frozen.json')==summary['selection_metadata_sha256'],'SELECTION_CHANGED')
    require(summary['selected']==8 and selected['seed']=='20261010','FIXED_EIGHT_SELECTION')
    policy=j.read(SAMPLING/'policy.json');base.verify_bindings(list(policy['metadata_inputs'].values()))
    require(j.filehash(SAMPLING/'prepare_metadata.py')==selected['code_sha256'],'SAMPLER_CODE_CHANGED')
    contract,models=base.science_contract(args.model_config,True);public=models[0]['public']
    oldcontract=j.read(R2/'grounded_development_v11/expected_contract.json')
    require(contract['models']==oldcontract['models'],'ORIGINAL_QWEN_DIGEST_OR_OPTIONS_CHANGED')
    c=budget.counts();require(c['phase']['confirmation']+8<=budget.LIMITS['confirmation'],'EIGHT_CONFIRMATION_RESERVATIONS_UNAVAILABLE')
    out.mkdir(parents=True,exist_ok=True)
    once(out/'time_window.json',{'deadline_utc':DEADLINE,'no_new_dispatch_at_or_after_utc':'2026-10-10T10:10:30+00:00',
        'timeout_seconds':600,'guard_margin_seconds':30,'deadline_not_rolling':True,'original_authorization':bind(budget.AUTH),
        'phase_limits':budget.LIMITS,'max_attempts':1,'package_cap':394,'round_cap':100,'no_llama':True,
        'authorization_basis':'ROOT records the user continuation within the previously proposed fixed additional 90-minute window. Original AUTH bytes and count limits remain unchanged.',
        'new_entrypoint_scope':'eight frozen fieldwise confirmation identities; no new sampling or prompt tuning',
        'recorded_by':'prepare_entrypoint_under_root_execution','created_utc':j.now()})
    paths=dependencies(contract)+[SAMPLING/n for n in ['prepare_metadata.py','policy.json','selection_metadata_frozen.json','freeze_summary.json','feasibility_summary.json']]
    paths += [STEP_ROOT/n for n in ['references.json','plan.json','t070_per_answer.csv','t070_resolved_config.json','verification.json','run.json']]
    paths += [args.model_config,R2/'grounded_development_v11/expected_contract.json']
    pre={'status':'frozen_before_selected_answer_export','frozen_inputs':[bind(p) for p in dict.fromkeys(paths)],
        'time_window':bind(out/'time_window.json'),'selected_count':8,'raw_answer_bodies_read_before_this_record':0,'created_utc':j.now()}
    once(out/'preexport_freeze.json',pre);install_clock(out);budget.guard('confirmation',8,600)
    refs=j.read(STEP_ROOT/'references.json')['references'];refidx={r['reference_id']:r for r in refs}
    config=j.read(STEP_ROOT/'t070_resolved_config.json');table={r['answer_id']:r for r in csvrows(STEP_ROOT/'t070_per_answer.csv')}
    require(config['references_sha256']==j.filehash(STEP_ROOT/'references.json') and config['core_sha256']==j.filehash(ROOT/'scripts/cce_validation.py'),'ORIGINAL_STEP_CONFIGURATION_DRIFT')
    cases=[];steps={};locations=[]
    for r in selected['selection']:
        original,location=exporter.selected_record(ROOT/f"dataset/Q+AR/model_response/from_{r['model']}_1-shot.json",int(r['question_id']))
        require(g.rawsha(original['model_response'])==r['answer_sha256'] and g.rawsha(original['specific_question'])==r['question_sha256'],'SELECTED_QUESTION_ANSWER_BYTES_CHANGED')
        selected_refs=[copy.deepcopy(refidx[rid]) for rid in r['candidate_reference_ids']]
        aid=r['confirmation_id'];case={'case_id':'fieldwise_'+aid,'anonymous_answer_id':aid,'question_id':int(r['question_id']),
            'specific_question':original['specific_question'],'model_response':original['model_response'],
            'answer_sha256':r['answer_sha256'],'question_sha256':r['question_sha256'],'references':selected_refs,'formal_eligible':False,'expert_confirmation':None}
        s=table[r['answer_id']]
        require(s['answer_sha256']==r['answer_sha256'] and s['question_sha256']==r['question_sha256'],'STEP_ANSWER_BINDING')
        sr,sp=float(s['sr']),float(s['sp']);require(finite(sr) and finite(sp) and 0<=sr<=1 and 0<=sp<=1,'ORIGINAL_SR_SP_NOT_FINITE')
        require(s['reference_id'] in r['candidate_reference_ids'] and int(s['question_id'])==case['question_id'],'REFERENCE_SELECTION_BINDING')
        steps[case['case_id']]={'sr':sr,'sp':sp,'answer_sha256':r['answer_sha256'],'question_sha256':r['question_sha256'],'question_id':case['question_id'],
            'reference_id':s['reference_id'],'candidate_reference_ids':r['candidate_reference_ids'],'references_sha256':j.digest(selected_refs),
            'reference_catalog_file_sha256':j.filehash(STEP_ROOT/'references.json'),'threshold':config['threshold'],'encoder':config['encoder'],
            'adapter_sha256':config['core_sha256'],'step_config_sha256':j.filehash(STEP_ROOT/'t070_resolved_config.json'),
            'reuse_kind':'exact_original_question_answer_reference_conditional_SR_SP_no_new_encoder',
            'provenance':[bind(STEP_ROOT/n) for n in ['t070_per_answer.csv','t070_resolved_config.json','references.json','verification.json']]}
        cases.append(case);locations.append({'anonymous_answer_id':aid,'original_answer_id':r['answer_id'],**location})
    once(out/'cases.json',{'cases':cases});once(out/'step_inputs.json',steps);once(out/'source_identity_manifest.json',locations)
    once(out/'model_config.json',args.model_config.read_bytes())
    contract['fieldwise_confirmation']={'wire_version':g.VERSION,'postprocessor_version':fw.VERSION,'runner_sha256':j.filehash(__file__),
        'fieldwise_sha256':j.filehash(fw.__file__),'phase':'confirmation','max_attempts':1,'formal_eligible':False}
    once(out/'expected_contract.json',contract)
    matrix=[];generated=[]
    for case in cases:
        aid=case['anonymous_answer_id'];doc=g.document(case['model_response'],g.source_id_for_case(case));schema=g.schema_for_document(doc)
        prompt=g.make_prompt(case,doc);payload=base.payload_for(prompt,schema,public);bound=len(prompt.encode('utf8'))+8192+256
        files={'source_document':out/'source_documents'/f'{aid}.json','schema':out/'schemas'/f'{aid}.json','prompt':out/'prompts'/f'{aid}.txt','payload':out/'request_payloads'/f'{aid}.json'}
        for name,value in [('source_document',doc),('schema',schema),('prompt',prompt.encode('utf8')),('payload',payload)]:once(files[name],value)
        identity={'case_id':case['case_id'],'anonymous_answer_id':aid,'input_sha256':j.digest({'question':case['specific_question'],'question_id':case['question_id'],'protocol':case['model_response'],'references':case['references']}),
            'judge':MODEL,'repeat_index':0,'attempt':1,'contract_sha256':j.digest(contract),'payload_sha256':j.digest(payload),'round_id':budget.ROUND,'phase':'confirmation'}
        matrix.append({'anonymous_answer_id':aid,'case_id':case['case_id'],'identity':identity,'planned_trial_id':j.digest(identity),'attempt':1,
            'assets':{k:bind(v) for k,v in files.items()},'step':steps[case['case_id']],'conservative_context_bound':bound,'context_fits':bound<=98304})
        generated.extend(files.values())
    once(out/'matrix.json',matrix)
    boundpaths=[out/n for n in ['preexport_freeze.json','time_window.json','cases.json','step_inputs.json','source_identity_manifest.json','model_config.json','expected_contract.json','matrix.json']]+generated
    once(out/'plan.json',{'status':'frozen_before_generation','phase':'confirmation','planned_cells':8,'planned_new_requests_max':8,'max_attempts':1,
        'starting_counts':{k:v for k,v in c.items() if k!='requests'},'deadline_utc':DEADLINE,
        'frozen_inputs':pre['frozen_inputs']+[bind(p) for p in boundpaths],'source_body_export_count':8,'new_model_requests':0,
        'actual_prepare_command':[sys.executable,*sys.argv]})
    validate(out);print(j.canonical({'status':'prepared','planned':8,'context_fits':sum(r['context_fits'] for r in matrix),'new_model_requests':0,'plan_sha256':j.filehash(out/'plan.json')}))


def validate(out):
    p=j.read(out/'plan.json');require(p['planned_cells']==8 and p['max_attempts']==1 and p['phase']=='confirmation','PLAN_SCOPE')
    base.verify_bindings(p['frozen_inputs']);cases=j.read(out/'cases.json')['cases'];matrix=j.read(out/'matrix.json');contract=j.read(out/'expected_contract.json')
    require(len(cases)==len(matrix)==8 and [c['anonymous_answer_id'] for c in cases]==['FPC%02d'%i for i in range(1,9)],'FIXED_ORDER')
    for c,r in zip(cases,matrix):
        require(r['identity']['judge']==MODEL and r['identity']['phase']=='confirmation' and r['identity']['repeat_index']==0 and r['attempt']==1,'CELL_SCOPE')
        require(r['case_id']==c['case_id'] and j.digest(r['identity'])==r['planned_trial_id'],'CELL_IDENTITY')
        require(g.rawsha(c['model_response'])==c['answer_sha256']==r['step']['answer_sha256'] and g.rawsha(c['specific_question'])==c['question_sha256']==r['step']['question_sha256'],'FULL_INPUT_STEP_IDENTITY')
        doc=j.read(r['assets']['source_document']['path']);require(doc==g.document(c['model_response'],g.source_id_for_case(c)),'SOURCE_DOCUMENT_IDENTITY')
        payload=j.read(r['assets']['payload']['path']);prompt=Path(r['assets']['prompt']['path']).read_bytes().decode('utf8')
        require(payload==base.payload_for(prompt,g.schema_for_document(doc),contract['models'][0]['settings']) and j.digest(payload)==r['identity']['payload_sha256'],'PAYLOAD_IDENTITY')
        require(r['identity']['contract_sha256']==j.digest(contract),'CONTRACT_IDENTITY')
    return p,cases,matrix,contract


def recover_direct(raw,doc,step):
    """No raw repair. Independently keep valid direct proposals after a local failure."""
    values={};details={};payload=base.integrity.parse_judge_object(raw)
    require(isinstance(payload,dict) and set(payload)<= {'scores','score_evidence','grounded_extraction'},'SHARED_TOP_LEVEL_IDENTITY')
    e=payload['grounded_extraction'];require(e['source_id']==doc['source_id'] and e['schema_version']==g.VERSION,'SHARED_SOURCE_OR_WIRE_IDENTITY')
    schema=g.schema_for_document(doc);ev=payload.get('score_evidence',[])
    require(isinstance(ev,list) and all(isinstance(x,dict) and x.get('m') in g.DIRECT for x in ev),'SHARED_UNATTRIBUTABLE_EVIDENCE')
    for metric in g.DIRECT:
        try:
            group='completeness' if metric=='c_param' else 'correctness';record=payload['scores'][group][metric]
            g.validate_shape(record,schema['properties']['scores']['properties'][group]['properties'][metric]);rows=[x for x in ev if x['m']==metric]
            require(len(rows)==1,'EXACT_ONE_EVIDENCE_ROW');v=rows[0];g.validate_shape(v,schema['properties']['score_evidence']['items'])
            spans=[g.resolve(g._expand_ref(u),doc) for u in v['u']]
            require(v['b'] not in ['observed','mixed'] or spans,'OBSERVED_EVIDENCE_REQUIRED');require(v['r'].strip(),'EMPTY_RUBRIC_BASIS')
            values[metric]=record['score'];details[metric]={'value':record['score'],'evidence_role':'checked_scope' if v['b']=='absence' else v['b'],'scientific_validity':'not_established'}
        except Exception as exc:details[metric]={'value':None,'error':str(exc)}
    return base.scoring.derive(values,step,True),details


async def run(args):
    require(args.allow_local_calls,'EXPLICIT_RUN_FLAG_REQUIRED');p,cases,matrix,contract=validate(args.out);install_clock(args.out)
    actual,models=base.science_contract(args.out/'model_config.json',True)
    require(all(actual[k]==contract[k] for k in base.SCIENCE_KEYS+['models']),'SCIENCE_OR_MODEL_DRIFT')
    public=models[0]['public'];save(args.out/'actual_run_command.json',{'argv':[sys.executable,*sys.argv],'utc':j.now(),'plan':bind(args.out/'plan.json')})
    for c,r in zip(cases,matrix):
        tid=r['planned_trial_id'];at=args.out/'run/attempts'/f'{tid}_1';tp=args.out/'run/trials'/f'{tid}.json'
        if tp.exists():continue
        existing=[x for x in budget.counts()['requests'] if x.get('trial_id')==tid]
        if existing or (at/'request_receipt.json').exists():
            print(j.canonical({'cell':r['anonymous_answer_id'],'status':'reserved_nonterminal','action':'preserved_no_retry'}),flush=True)
            continue
        if not r['context_fits']:
            once(tp,{'trial_id':tid,'identity':r['identity'],'status':'local_not_requested','failure_stage':'CONTEXT_LIMIT','actual_request_made':False,'metrics':base.scoring.derive({},r['step'],False)});continue
        if budget.time_remaining()<=630:break
        base.verify_bindings(p['frozen_inputs']);payload=j.read(r['assets']['payload']['path']);doc=j.read(r['assets']['source_document']['path'])
        once(at/'http_request_payload.json',payload);receipt=reserve(args.out,tid);once(at/'request_receipt.json',receipt)
        stage='PROVIDER_TRANSPORT';raw=None;provider=None;cv=None;num=None;direct={};status='failed';metrics=base.scoring.derive({},r['step'],False);err=None
        try:
            provider=await asyncio.to_thread(base.invoke_transport,public,payload);once(at/'provider_response.json',provider)
            raw=provider.get('response') if isinstance(provider,dict) else None
            if isinstance(raw,str):once(at/'raw_response.txt',raw.encode('utf8'));once(at/'raw_receipt.json',{'raw_sha256':g.rawsha(raw),'source_document':r['assets']['source_document']})
            stage='PROVIDER_COMPLETION';raw=base.validate_provider(provider,public)
            stage='FIELDWISE_CONVERSION';cv=fw.convert(raw,doc,c);once(at/'conversion.json',cv)
            stage='FIELDWISE_NUMERIC_SCORING'
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):num=fw.score_conversion(c,cv,r['step'])
            once(at/'numeric.json',num);metrics=num['metrics'];status='success';stage=None
        except Exception as exc:
            err={'stage':stage,'type':type(exc).__name__,'reason':str(exc)};once(at/'error.json',err)
            if raw is not None and stage in ['FIELDWISE_CONVERSION','FIELDWISE_NUMERIC_SCORING']:
                try:metrics,direct=recover_direct(raw,doc,r['step']);once(at/'retained_direct_components.json',{'metrics':metrics,'direct':direct,'original_failure':err,'full_success':False})
                except Exception as sub:err['direct_recovery_failure']=str(sub)
        artifacts=[bind(x) for x in sorted(at.iterdir()) if x.is_file()]
        once(tp,{'trial_id':tid,'identity':r['identity'],'anonymous_answer_id':r['anonymous_answer_id'],'status':status,'failure_stage':stage,'error':err,
            'actual_request_made':True,'request_id':receipt['request_id'],'attempt':1,'terminal_utc':j.now(),'metrics':metrics,
            'bound_artifacts':artifacts,'formal_eligible':False,'expert_confirmed':False})
        print(j.canonical({'cell':r['anonymous_answer_id'],'status':status,'package_request_index':receipt['package_request_index']}),flush=True)


def analyze(args):
    p,cases,matrix,contract=validate(args.out);ledger=budget.counts();observations=[]
    for r in matrix:
        tid=r['planned_trial_id'];tp=args.out/'run/trials'/f'{tid}.json';reservations=[x for x in ledger['requests'] if x.get('trial_id')==tid]
        require(len(reservations)<=1,'DUPLICATE_CELL_RESERVATION')
        if tp.exists():
            t=j.read(tp);require(t['trial_id']==tid and t['identity']==r['identity'],'TERMINAL_IDENTITY');base.verify_bindings(t.get('bound_artifacts',[]))
            if t['actual_request_made']:
                require(len(reservations)==1 and t['request_id']==reservations[0]['request_id'],'TERMINAL_LEDGER_BINDING')
                require(reservations[0]['phase']=='confirmation' and reservations[0]['model']==MODEL,'REQUEST_MODEL_PHASE')
            else:require(not reservations,'LOCAL_FAILURE_RESERVED')
            status=t['status'];metrics=t['metrics'];failure=t.get('error') or t.get('failure_stage')
        else:status='reserved_nonterminal' if reservations else 'unstarted';metrics=base.scoring.derive({},r['step'],False);failure=None
        observations.append({'anonymous_answer_id':r['anonymous_answer_id'],'trial_id':tid,'status':status,'request_reserved':bool(reservations),'metrics':metrics,'failure':failure})
    terminal=all(r['status'] in ['success','failed','local_not_requested'] for r in observations)
    summary={'status':'complete' if terminal else 'partial','planned':8,'successful':sum(r['status']=='success' for r in observations),
        'failed':sum(r['status']=='failed' for r in observations),'local_not_requested':sum(r['status']=='local_not_requested' for r in observations),
        'pending':sum(r['status'] in ['reserved_nonterminal','unstarted'] for r in observations),'actual_requests':sum(r['request_reserved'] for r in observations),
        'package_requests':ledger['package'],'round_requests':ledger['round'],'complete_numeric_CCE':sum(all(finite(r['metrics'].get(k)) for k in ['Com','Cor','Eff']) for r in observations),
        'numeric_coverage':{k:sum(finite(r['metrics'].get(k)) for r in observations) for k in base.scoring.METRICS},
        'scope':'within exposed tasks and source families; answer-level prospective automatic confirmation','expert_returns':0,'formal_eligible':0,'new_analysis_model_requests':0}
    target=args.out/'analysis'/j.now().replace(':','').replace('+','_');target.mkdir(parents=True,exist_ok=False)
    once(target/'observations.json',observations);once(target/'completion_summary.json',summary)
    once(target/'verification.json',{'status':'pass','plan':bind(args.out/'plan.json'),'matrix':bind(args.out/'matrix.json'),
        'all_8_slots_preserved':True,'terminal':terminal,'source_and_output_bindings_verified':True,'numerical_replay_performed':False,'raw_not_repaired':True,'new_requests':0})
    print(j.canonical({'out':str(target),**summary}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','analyze']);p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--model-config',type=Path,default=R2/'grounded_development_v11/model_config.json');p.add_argument('--allow-local-calls',action='store_true')
    a=p.parse_args()
    if a.action=='prepare':prepare(a)
    elif a.action=='run':asyncio.run(run(a))
    else:analyze(a)
if __name__=='__main__':main()
