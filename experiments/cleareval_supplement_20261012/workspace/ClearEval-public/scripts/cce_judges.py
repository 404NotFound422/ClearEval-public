"""CCE r2 full-text judge adapter. Explicit API execution, immutable trial identity, and resume.

Cases: JSON list (or {'cases': list}) with case_id, question_id,
specific_question and model_response. Optional references are appended as
evidence context to the judge prompt, never inserted into the protocol.
"""
from __future__ import annotations
import argparse, asyncio, collections, contextlib, csv, hashlib, io, json, math, os
from pathlib import Path
import statistics, sys, time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True
DEFAULT_OUT=ROOT/'artifacts/cce_validation/judges'
HIST=ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'

def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x): return hashlib.sha256(canonical(x).encode()).hexdigest()
def filehash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def redact(value,keys):
    if isinstance(value,dict):return {k:redact(v,keys) for k,v in value.items()}
    if isinstance(value,list):return [redact(v,keys) for v in value]
    if isinstance(value,str):
        for key in keys:
            if key:value=value.replace(key,'[REDACTED]')
    return value

def runtime(args):
    os.chdir(ROOT)
    import OEQ_run_grading_new as runner
    from experiments.judge_reliability import APIJudge
    runner.configure_question_snapshot(args.question_file)
    runner.DEMAND_FILE=str(args.demand_file)
    runner.DEMAND_MANIFEST=str(args.demand_manifest) if args.demand_manifest else None
    registry=runner.fixed_demands()
    return runner,APIJudge,registry

def model_configs(args):
    import yaml
    source=yaml.safe_load(Path(args.model_config).read_text(encoding='utf-8'))
    indexed={x['name']:x for x in source.get('models',[])}
    rows=[]
    for name in args.models:
        if name not in indexed:raise ValueError(f'Model absent from configuration: {name}')
        c=indexed[name]
        if str(c.get('type','')).lower()=='ollama':
            import urllib.request,urllib.parse
            host=c.get('host','http://127.0.0.1:11434')
            origin=urllib.parse.urlsplit(host)
            if origin.scheme!='http' or origin.hostname not in ('127.0.0.1','localhost','::1') or origin.username or origin.password:
                raise ValueError('Local substitute must use a loopback-only origin')
            from models.Ollama_LLM import LocalOllamaHTTPClient
            client=LocalOllamaHTTPClient(host,4)
            with client.opener.open(host.rstrip('/')+'/api/tags',timeout=4) as response:tags=json.load(response)
            with client.opener.open(host.rstrip('/')+'/api/version',timeout=4) as response:version=json.load(response)
            info=next((x for x in tags.get('models',[]) if x.get('name')==c.get('model_name')),None)
            if info is None:raise ValueError(f'Local model is not installed: {name}')
            if c.get('model_digest') and info.get('digest')!=c['model_digest']:raise ValueError('Local model digest differs from frozen configuration')
            context=c.get('num_ctx',32768);native=info.get('details',{}).get('context_length')
            if native and context>native:raise ValueError('Requested context exceeds native model context')
            public={'transport_kind':'ollama_loopback','model':c['model_name'],'host':host,'model_digest':info.get('digest'),
                    'service_version':version.get('version'),'model_details':info.get('details'),
                    'max_output_tokens':args.max_output_tokens or c.get('max_tokens',8192),'num_ctx':context,
                    'temperature':c.get('temperature',0.0) if args.temperature is None else args.temperature,
                    'enable_thinking':c.get('enable_thinking',False),'format':'json','timeout_seconds':args.timeout_seconds}
            rows.append({'name':name,'family':'llama' if 'llama' in c['model_name'].lower() else 'qwen','public':public,'credential':None})
            continue
        key=c.get('api_key')
        if not isinstance(key,str) or not key:raise ValueError(f'Missing configured API credential for {name}')
        # Existing APIJudge supports these documented public options. Models with
        # enable_thinking need an explicit compatible model selection instead of
        # silently dropping a configured provider flag.
        unsupported=[k for k in ('enable_thinking','top_p','frequency_penalty','presence_penalty') if k in c]
        if unsupported:raise ValueError(f'Existing APIJudge cannot preserve {name} options {unsupported}; choose an existing transport-compatible configuration')
        public={'transport_kind':'external_api','model':c.get('model_name'),'base_url':c.get('base_url'),
                'api_key_env':'CCE_JUDGE_'+hashlib.sha256(name.encode()).hexdigest()[:12].upper(),
                'token_parameter':'max_completion_tokens' if c.get('max_completion_tokens') else 'max_tokens',
                'max_output_tokens':args.max_output_tokens or c.get('max_completion_tokens') or c.get('max_tokens') or 8192,
                'temperature':c.get('temperature',0.7) if args.temperature is None else args.temperature,
                'reasoning_effort':None,'timeout_seconds':args.timeout_seconds}
        family='qwen' if 'qwen' in name.lower() else 'deepseek' if 'deepseek' in name.lower() else name
        rows.append({'name':name,'family':family,'public':public,'credential':key})
    return rows

def make_adapter(public,APIJudge):
    if public.get('transport_kind')!='ollama_loopback':return APIJudge(public)
    from models.Ollama_LLM import OllamaLLM
    class LocalAdapter:
        model_name=public['model']
        def __init__(self):
            self.last_response=None;self.last_error=None
            self.client=OllamaLLM(self.model_name,max_length=public['max_output_tokens'],temperature=public['temperature'],
                host=public['host'],timeout=public['timeout_seconds'],format=public['format'],
                enable_thinking=public['enable_thinking'],transport='http')
            original=self.client.client.generate
            def configured(**kwargs):
                kwargs['options']['num_ctx']=public['num_ctx']
                response=original(**kwargs);self.last_response=response
                return response
            self.client.client.generate=configured
        async def _acall(self,prompt):
            try:return await self.client._acall(prompt)
            except Exception as exc:
                self.last_error=exc
                raise
    return LocalAdapter()

def cases_from(path,registry):
    if not path:return []
    obj=read(path); cases=obj.get('cases',[]) if isinstance(obj,dict) else obj
    if not isinstance(cases,list):raise ValueError('Cases must be a JSON list or a cases list')
    out=[]; seen=set()
    for index,c in enumerate(cases):
        cid=c.get('case_id',c.get('id'))
        if not isinstance(cid,str) or not cid or cid in seen:raise ValueError(f'Missing/duplicate case_id at row {index}')
        seen.add(cid); qid=c.get('question_id'); stem=c.get('specific_question',c.get('question'))
        protocol=c.get('model_response',c.get('protocol'))
        if not isinstance(protocol,str) or not protocol.strip():raise ValueError(f'Missing full answer text: {cid}')
        registry.get(qid,stem)
        row={**c,'case_id':cid,'question_id':qid,'specific_question':stem,'model_response':protocol}
        row['input_sha256']=digest({'question':stem,'question_id':qid,'protocol':protocol,'references':c.get('references')})
        out.append(row)
    return out

def contract(args,runner,registry,models):
    paths=['scripts/cce_judges.py','OEQ_run_grading_new.py','experiments/judge_reliability.py','models/Ollama_LLM.py',
           'evaluation_contract.py','evaluator_integrity.py','results/oeq_metrics.py','verified_marker_aliases.py',
           'prompts/eval_oeq_teacher_rubric.txt','dataset/Q+AR/src/model_space_signed.json',
           'KnowledgeBase/tissue.json','KnowledgeBase/method_fluro_compati.json','KnowledgeBase/time_kb.json',
           'KnowledgeBase/tissue_ri.json','KnowledgeBase/method_ri_ref.json','KnowledgeBase/method_sigma_ri.json']
    for attribute in ('_MARKER_SPECIFICITY_TIERS_PATH','_FLUOR_EVIDENCE_PATH'):
        value=getattr(runner,attribute,None)
        if value and (ROOT/value).is_file():paths.append(value)
    return {'adapter_version':'cce-r2-full-text-judge-v1','scoring_version':runner.SCORING_VERSION,
            'evaluation_identity':'local_substitute_diagnostic' if all(m['public'].get('transport_kind')=='ollama_loopback' for m in models) else 'current_substitute_diagnostic',
            'historical_evaluator_unavailable':True,
            'score_scope':'Preserved numerical proposals; upstream official_scores/cce_eligible are retained',
            'demands':registry.provenance,'models':[{'name':m['name'],'family':m['family'],'settings':m['public']} for m in models],
            'files':{p:filehash(ROOT/p) for p in paths},'source_registry_sha256':filehash(ROOT/'KnowledgeBase/source_registry.json'),
            'reference_prompt_policy':'append full supplied reference JSON after unchanged runner prompt',
            'primary_result_trial_rule':'trial repeat_index=0; never select best repeat'}

@contextlib.contextmanager
def ledger_lock(path):
    lock=Path(str(path)+'.lock');lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def ledger_rows(path):
    if not Path(path).exists():return []
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]

def reserve_request(args,trial_id,attempt,model):
    path=args.ledger
    with ledger_lock(path):
        rows=ledger_rows(path)
        used=sum(x.get('event')=='request_started' for x in rows)+args.external_request_count
        if used>=min(args.total_budget,300):raise RuntimeError('Package API request budget exhausted')
        row={'event':'request_started','request_id':digest({'trial_id':trial_id,'attempt':attempt}),
             'trial_id':trial_id,'attempt':attempt,'model':model,'started_utc':now(),'package_request_index':used+1}
        with Path(path).open('a',encoding='utf-8') as stream:stream.write(canonical(row)+'\n')
    return row

def proposals(evaluation):
    scores=evaluation.get('legacy_diagnostics',{}).get('scores') or evaluation.get('scores') or {}
    values={}
    blocks={'completeness':{'c_param':3},'correctness':{'co_order':3,'co_method':2,'co_param':2,'co_chem':1},
            'effectiveness':{'s_method':2.5,'s_label':6,'s_trans':3,'s_time':3}}
    for block,metrics in blocks.items():
        for metric,maximum in metrics.items():
            value=scores.get(block,{}).get(metric,{}).get('score')
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):value=None
            if value is not None and not (-maximum if metric=='s_method' else 0)<=value<=maximum:value=None
            values[metric]=value
    def mean(keys,maxima):
        vs=[values[k]/maximum if values[k] is not None else None for k,maximum in zip(keys,maxima)]
        return sum(vs)/len(vs) if all(v is not None for v in vs) else None
    values['Cor']=mean(['co_order','co_method','co_param','co_chem'],[3,2,2,1])
    eff=[(values['s_method']/2.5+1)/2 if values['s_method'] is not None else None,
         values['s_label']/6 if values['s_label'] is not None else None,
         values['s_trans']/3 if values['s_trans'] is not None else None,
         values['s_time']/3 if values['s_time'] is not None else None]
    values['Eff']=sum(eff)/4 if all(v is not None for v in eff) else None
    return values

def preflight(args):
    runner,APIJudge,registry=runtime(args);models=model_configs(args);cases=cases_from(args.cases,registry)
    c=contract(args,runner,registry,models)
    result={'status':'ready','api_requests_made':0,'cases':len(cases),'repeats':args.repeats,
            'planned_trials':len(cases)*len(models)*args.repeats,'first_attempt_requests':len(cases)*len(models)*args.repeats,
            'maximum_requests_with_retries':len(cases)*len(models)*args.repeats*args.max_attempts,
            'contract':c,'contract_sha256':digest(c),
            'fixed_question_snapshot_matches':True,'credentials_present':True,
            'configured_historical_teacher_present':False,
            'package_budget':min(args.total_budget,300),'external_request_count':args.external_request_count,
            'ledger_request_count':sum(x.get('event')=='request_started' for x in ledger_rows(args.ledger))}
    save(args.out/'preflight.json',result)
    print(canonical({k:v for k,v in result.items() if k!='contract'}))
    return runner,APIJudge,registry,models,cases,c

async def run(args):
    if not args.allow_api:raise ValueError('run requires --allow-api; preflight is offline')
    runner,APIJudge,registry,models,cases,c=preflight(args)
    if not cases:raise ValueError('No cases to run')
    if args.max_calls<1:raise ValueError('--max-calls must be positive')
    keys=[m['credential'] for m in models];made=0;runhash=digest(c)
    save(args.out/'contracts'/f'{runhash}.json',c)
    previous_environment={model['public']['api_key_env']:os.environ.get(model['public']['api_key_env']) for model in models if model['credential']}
    for model in models:
        if model['credential']:os.environ[model['public']['api_key_env']]=model['credential']
    try:
        for repeat in range(args.repeats):
            for case in cases:
                for model in models:
                    # Judge-local settings keep successful trials reusable when
                    # adding another judge to a later invocation.
                    one_contract={**c,'models':[{'name':model['name'],'family':model['family'],'settings':model['public']}]}
                    identity={'case_id':case['case_id'],'input_sha256':case['input_sha256'],
                              'judge':model['name'],'repeat_index':repeat,'contract_sha256':digest(one_contract)}
                    trial=digest(identity);dest=args.out/'trials'/f'{trial}.json'
                    if dest.exists() and read(dest).get('status')=='success':continue
                    previous=[x for x in ledger_rows(args.ledger) if x.get('trial_id')==trial and x.get('event')=='request_started']
                    for attempt in range(len(previous)+1,args.max_attempts+1):
                        if made>=args.max_calls:
                            print(canonical({'stopped':'batch_request_limit','new_requests':made}));analyze(args);return
                        started=now();attempt_dir=args.out/'attempts'/f'{trial}_{attempt}'
                        attempt_dir.mkdir(parents=True,exist_ok=True)
                        api=make_adapter(model['public'],APIJudge)
                        reference=case.get('references')
                        class Instrumented:
                            model_name=api.model_name
                            async def _acall(self,prompt):
                                nonlocal made
                                if reference is not None:
                                    prompt += '\n\n[SUPPLIED REFERENCE EVIDENCE]\n'+canonical(reference)+'\nUse only evidence applicable to the question and declared route; preserve uncertainty.\n'
                                if model['public'].get('transport_kind')=='ollama_loopback':
                                    bound=len(prompt.encode('utf-8'))+model['public']['max_output_tokens']+256
                                    if bound>model['public']['num_ctx']:
                                        raise ValueError('Conservative prompt byte bound plus output/template reserve exceeds frozen local context')
                                    save(attempt_dir/'context_check.json',{'prompt_unicode_characters':len(prompt),
                                        'prompt_utf8_bytes':len(prompt.encode('utf-8')),'conservative_context_bound':bound,
                                        'configured_num_ctx':model['public']['num_ctx'],'max_output_tokens':model['public']['max_output_tokens'],
                                        'status':'full_prompt_and_output_fit_conservative_bound'})
                                (attempt_dir/'prompt.txt').write_text(prompt,encoding='utf-8')
                                request=reserve_request(args,trial,attempt,model['name']);made+=1
                                save(attempt_dir/'request_receipt.json',request)
                                try:
                                    answer=await api._acall(prompt)
                                finally:
                                    if api.last_response is not None:save(attempt_dir/'provider_response.json',redact(api.last_response,keys))
                                    if api.last_error is not None:
                                        save(attempt_dir/'provider_error.json',{'error_type':type(api.last_error).__name__,
                                            'category':getattr(api.last_error,'kind',None),'http_status':getattr(api.last_error,'status',None)})
                                body=api.last_response or {}
                                answer['metadata']={**answer.get('metadata',{}),**{k:body.get(k) for k in ['id','model','created','usage','system_fingerprint'] if k in body}}
                                return answer
                        def log_teacher(name,qid,prompt_len,content,status,detail=''):
                            save(attempt_dir/'runner_log.json',redact({'teacher':name,'question_id':qid,'prompt_length':prompt_len,
                                'content':content,'status':status,'detail':detail},keys))
                        runner._log_teacher_response=log_teacher
                        evaluation=await runner.evaluate_response_with_teacher(Instrumented(),case['specific_question'],
                            case['model_response'],runner.MODEL_SPACE_SIGNED,{'question_id':case['question_id']},None)
                        complete=evaluation.get('technical_status')=='VALID' and not evaluation.get('_error')
                        row={'trial_id':trial,'identity':identity,'case_id':case['case_id'],'question_id':case['question_id'],
                             'base_id':case.get('base_id'),'condition':case.get('condition','natural'),
                             'generator_model':case.get('generator_model'),'judge':model['name'],'judge_family':model['family'],
                             'repeat_index':repeat,'attempt':attempt,'started_utc':started,'finished_utc':now(),
                             'status':'success' if complete else 'failed','evaluation_identity':c['evaluation_identity'],
                             'pipeline_config_sha256':digest({**c,'models':[]}),
                             'full_text_input_sha256':case['input_sha256'],'references_sha256':digest(reference),
                             'prompt_sha256':filehash(attempt_dir/'prompt.txt') if (attempt_dir/'prompt.txt').exists() else None,
                             'actual_api_request_made':(attempt_dir/'request_receipt.json').exists(),
                             'full_text_submitted_for_reextraction':(attempt_dir/'request_receipt.json').exists(),
                             'new_extraction_available':isinstance(evaluation.get('extraction'),dict),
                             'upstream_cce_eligible':evaluation.get('cce_eligible'),
                             'preserved_numeric_proposals':proposals(evaluation),'evaluation':evaluation,
                             'extraction_sha256':digest(evaluation.get('extraction')),
                             'actual_returned_model':(api.last_response or {}).get('model'),
                             'provider_fingerprint':(api.last_response or {}).get('system_fingerprint','UNKNOWN')}
                        row=redact(row,keys);save(attempt_dir/'result.json',row);save(dest,row)
                        print(canonical({'case_id':case['case_id'],'judge':model['name'],'repeat':repeat,'attempt':attempt,
                                         'status':row['status'],'batch_new_requests':made}),flush=True)
                        if complete:break
    finally:
        for name,value in previous_environment.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value
    analyze(args)

def analyze(args):
    rows=[read(p) for p in sorted((args.out/'trials').glob('*.json'))] if (args.out/'trials').exists() else []
    attempts=[read(p) for p in sorted((args.out/'attempts').glob('*/result.json'))] if (args.out/'attempts').exists() else []
    ledger=ledger_rows(args.ledger)
    groups=collections.defaultdict(list)
    for row in rows:
        groups[(row['case_id'],row['judge'],row['identity']['input_sha256'],row['identity']['contract_sha256'])].append(row)
    spread=[];flat=[]
    for row in rows:
        flat.append({k:row.get(k) for k in ['trial_id','case_id','question_id','base_id','condition','generator_model','judge','judge_family','repeat_index','attempt','status','actual_returned_model','upstream_cce_eligible','pipeline_config_sha256','full_text_input_sha256']}|row.get('preserved_numeric_proposals',{}))
    for (case_id,judge,input_sha256,contract_sha256),rs in groups.items():
        good=[r for r in rs if r['status']=='success'];metrics=sorted({k for r in good for k in r['preserved_numeric_proposals']})
        for metric in metrics:
            vals=[r['preserved_numeric_proposals'].get(metric) for r in good]
            vals=[v for v in vals if v is not None]
            spread.append({'case_id':case_id,'question_id':rs[0]['question_id'],'judge':judge,'metric':metric,
                           'input_sha256':input_sha256,'judge_contract_sha256':contract_sha256,
                           'successful_pipeline_repeats':len(good),'finite_metric_repeats':len(vals),
                           'mean':statistics.mean(vals) if vals else None,'sample_sd':statistics.stdev(vals) if len(vals)>1 else None,
                           'min':min(vals) if vals else None,'max':max(vals) if vals else None,
                           'range':max(vals)-min(vals) if vals else None,
                           'distinct_extractions':len({r['extraction_sha256'] for r in good})})
    def csvsave(name,records):
        if not records:return
        fields=list(dict.fromkeys(k for r in records for k in r));stream=io.StringIO(newline='')
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(records)
        (args.out/name).write_text(stream.getvalue(),encoding='utf-8-sig')
    args.out.mkdir(parents=True,exist_ok=True);csvsave('trials.csv',flat);csvsave('repeat_spread.csv',spread)
    summary={'scope':'current substitute diagnostic; full-text pipeline calls only, no deterministic reruns counted as repeats',
             'ledger_total_new_requests':sum(x.get('event')=='request_started' for x in ledger),
             'attempt_results':len(attempts),'successful_attempts':sum(r['status']=='success' for r in attempts),
             'failed_attempts':sum(r['status']=='failed' and r.get('actual_api_request_made') for r in attempts),
             'local_failures_without_api_request':sum(not r.get('actual_api_request_made') for r in attempts),'trials':len(rows),
             'successful_trials':sum(r['status']=='success' for r in rows),'failed_trials':sum(r['status']=='failed' for r in rows),
             'distinct_question_ids':len({str(r['question_id']) for r in rows}),
             'judge_families':sorted({r['judge_family'] for r in rows}),
             'primary_result_trial_rule':'repeat_index=0, never best repeat',
             'held_out_human_validation':'pending; no synthetic expert labels',
             'stability_inference':'descriptive only; trials on one question are not independent questions'}
    save(args.out/'summary.json',summary);save(args.out/'repeat_spread.json',spread)
    print(canonical(summary))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','run','analyze'])
    p.add_argument('--cases',type=Path)
    p.add_argument('--out',type=Path,default=DEFAULT_OUT)
    p.add_argument('--model-config',type=Path,default=ROOT/'config/config.yaml')
    p.add_argument('--models',nargs='+',default=['openai_qwen-max','openai_deepseek-chat'])
    p.add_argument('--question-file',type=Path,default=HIST)
    p.add_argument('--demand-file',type=Path,default=ROOT/'dataset/Q+AR/src/demand_vectors_all.json')
    p.add_argument('--demand-manifest',type=Path)
    p.add_argument('--ledger',type=Path,default=DEFAULT_OUT/'request_ledger.jsonl')
    p.add_argument('--total-budget',type=int,default=300)
    p.add_argument('--external-request-count',type=int,default=0)
    p.add_argument('--max-calls',type=int,default=2)
    p.add_argument('--max-attempts',type=int,choices=[1,2],default=2)
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--temperature',type=float)
    p.add_argument('--max-output-tokens',type=int)
    p.add_argument('--timeout-seconds',type=int,default=120)
    p.add_argument('--allow-api',action='store_true')
    args=p.parse_args()
    if args.repeats<1 or args.repeats>3:p.error('--repeats must be in 1..3')
    try:
        if args.command=='preflight':preflight(args)
        elif args.command=='run':asyncio.run(run(args))
        else:analyze(args)
    except Exception as exc:
        # Only static adapter validation messages are printed; arbitrary provider
        # exception bodies are intentionally suppressed.
        if isinstance(exc,ValueError):print(canonical({'status':'blocked','error_type':type(exc).__name__,'reason':str(exc)}));return 2
        print(canonical({'status':'blocked','error_type':type(exc).__name__}));return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
