"""Prepare the fixed five development answers for v2 extraction review.

No generation transport is constructed. Reuse exact successful A02 trial bytes;
four new loopback requests remain planned until the coordinator releases service.
"""
import argparse, asyncio, copy, csv, hashlib, json, pathlib, shutil, sys, types

sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import cce_judges as judges
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'judges/local_extraction_dev_v2'
SOURCE=BASE/'judges/local_controls_supplement_v2'
HUMAN=BASE/'human_review'
REFS=BASE/'reference_recovery/supplement_bound/references_supplement_v2.json'

def require(ok,msg):
    if not ok:raise ValueError(msg)
def rawsha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def binding(p):return {'path':str(pathlib.Path(p).resolve()),'sha256':judges.filehash(p)}
def save(p,obj):judges.save(p,obj)
def csvread(p):
    with pathlib.Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def expected_input(case):
    return judges.digest({'question':case['specific_question'],'question_id':case['question_id'],
                          'protocol':case['model_response'],'references':case['references']})

def capture(runner,case):
    class Captured(BaseException):pass
    class CaptureOnly:
        model_name='offline_capture_no_transport'
        async def _acall(self,prompt):raise Captured(prompt)
    try:
        asyncio.run(runner.evaluate_response_with_teacher(CaptureOnly(),case['specific_question'],
            case['model_response'],runner.MODEL_SPACE_SIGNED,{'question_id':case['question_id']},None))
    except Captured as result:
        return str(result)+'\n\n[SUPPLIED REFERENCE EVIDENCE]\n'+judges.canonical(case['references'])+'\nUse only evidence applicable to the question and declared route; preserve uncertainty.\n'
    raise ValueError('Actual prompt capture did not reach the offline adapter')

def frozen_runtime():
    args=types.SimpleNamespace(question_file=judges.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',demand_manifest=None)
    runner,_,registry=judges.runtime(args)
    preflight=judges.read(SOURCE/'preflight.json');contract=preflight['contract']
    require(len(contract['models'])==1 and contract['models'][0]['name']=='local_qwen3_8b','Expected single frozen Qwen judge')
    model=contract['models'][0];settings=model['settings']
    require(settings['transport_kind']=='ollama_loopback' and settings['host']=='http://127.0.0.1:11434' and
        settings['max_output_tokens']==8192 and settings['temperature']==0 and settings['num_ctx']==40960 and
        settings['enable_thinking'] is False and settings['timeout_seconds']==600,'Frozen main-judge settings differ')
    models=[{'name':model['name'],'family':model['family'],'public':settings,'credential':None}]
    current=judges.contract(args,runner,registry,models)
    require(current==contract and judges.digest(contract)==preflight['contract_sha256'],'Current source/evidence/demands differ from original v2 contract')
    return runner,registry,contract,settings

def prepare(args):
    identities=csvread(HUMAN/'private/identity_manifest.csv')
    dev=[r for r in identities if r['split']=='audit_dev']
    require([r['answer_id'] for r in dev]==['A01','A02','A03','A04','A05'] and len(identities)==20,'Fixed 5+15 identities changed')
    runner,registry,contract,settings=frozen_runtime()
    refs=judges.read(REFS)['references'];source_cases=judges.read(SOURCE/'cases.json')['cases']
    source_trials=[(p,judges.read(p)) for p in (SOURCE/'trials').glob('*.json')]
    local=judges.read(SOURCE/'local_config_snapshot.json')
    qwen=next(m for m in local['models'] if m['name']=='local_qwen3_8b')
    require(qwen['model_digest']==settings['model_digest'] and qwen['max_tokens']==8192 and qwen['temperature']==0,'Model configuration source differs')
    cases=[];rows=[];reused=[];context=[];sources={}
    for key,path in [('identities',HUMAN/'private/identity_manifest.csv'),('selection',HUMAN/'selection.json'),
                     ('references',REFS),('source_cases',SOURCE/'cases.json'),('source_model_config',SOURCE/'local_config_snapshot.json')]:
        sources[key]=binding(path)
    for ident in dev:
        aid=ident['answer_id'];qid=int(ident['question_id']);ap=pathlib.Path(ident['response_path'])
        require(judges.filehash(ap)==ident['response_file_sha256'],'Original response file changed')
        records=[r for r in judges.read(ap) if int(r['question_id'])==qid]
        require(len(records)==1,'Answer question ID not unique')
        original=records[0]
        require(rawsha(original['model_response'])==ident['answer_sha256'] and rawsha(original['specific_question'])==ident['question_sha256'],'Original answer/question hash differs')
        packet=judges.read(HUMAN/'reviewer'/f'{aid}.json')
        require(packet['answer_id']==aid and packet['answer_text']==original['model_response'] and packet['task_text']==original['specific_question'],'Existing anonymous packet text differs')
        registry.get(qid,original['specific_question'])
        selected=[r for r in refs if r['route_id']=='FDISCO' and qid in r['question_ids']]
        require(len(selected)==1,'Expected exactly one question-applicable FDISCO reference')
        cid=ident['model_name']+'__q'+str(qid)+'__baseline__supplement_v2'
        case={'case_id':cid,'base_id':ident['model_name']+'__q'+str(qid),'condition':'baseline','generator_model':ident['model_name'],
            'question_id':qid,'specific_question':original['specific_question'],'model_response':original['model_response'],
            'answer_sha256':ident['answer_sha256'],'question_sha256':ident['question_sha256'],'references':selected,
            'anonymous_answer_id':aid,'split':'audit_dev','formal_eligible':False,'expert_confirmation':None,
            'scope':'fixed_five_development_actual_extraction_input_not_expert_labels'}
        inp=expected_input(case);contract_sha=judges.digest(contract)
        trial_identity={'case_id':cid,'input_sha256':inp,'judge':'local_qwen3_8b','repeat_index':0,'contract_sha256':contract_sha}
        trial_id=judges.digest(trial_identity)
        exact=[]
        for path,trial in source_trials:
            if trial.get('status')=='success' and trial.get('identity')==trial_identity:exact.append((path,trial))
        require(len(exact)<=1,'More than one exact successful source trial')
        prompt=capture(runner,case);prompt_sha=rawsha(prompt)
        bound=len(prompt.encode('utf-8'))+8192+256
        require(bound<=40960,'Full prompt plus output budget exceeds frozen context')
        context.append({'answer_id':aid,'case_id':cid,'prompt_raw_sha256':prompt_sha,'prompt_utf8_bytes':len(prompt.encode('utf-8')),
                        'max_output_tokens':8192,'template_reserve':256,'conservative_context_bound':bound,'num_ctx':40960,'fits':True})
        if exact:
            path,trial=exact[0]
            require(aid=='A02','Unexpected reusable trial outside the prespecified exact A02 match')
            source=next(c for c in source_cases if c['case_id']==cid)
            require(source['specific_question']==case['specific_question'] and source['model_response']==case['model_response'] and source['references']==selected,'Source case differs from original dev answer or v2 reference')
            require(trial['trial_id']==trial_id and trial['full_text_input_sha256']==inp and trial['references_sha256']==judges.digest(selected),'Actual trial identity differs')
            require(trial['actual_api_request_made'] and trial['full_text_submitted_for_reextraction'] and trial['new_extraction_available'],'Actual source trial does not prove full prompt/extraction')
            require(trial['extraction_sha256']==judges.digest(trial['evaluation']['extraction']),'Actual extraction hash differs')
            runner.validate_teacher_extraction(trial['evaluation']['extraction'])
            attempt=SOURCE/'attempts'/f"{trial_id}_{trial['attempt']}"
            require(judges.filehash(attempt/'prompt.txt')==trial['prompt_sha256'],'Persisted original prompt bytes differ from actual trial')
            require((attempt/'prompt.txt').read_text(encoding='utf-8')==prompt,'Actual original prompt differs from current captured prompt')
            receipt=judges.read(attempt/'request_receipt.json')
            ledger=judges.ledger_rows(BASE/'judges/request_ledger.jsonl')
            matching=[r for r in ledger if r['request_id']==receipt['request_id']]
            require(len(matching)==1 and matching[0]==receipt,'Original request not uniquely bound to total ledger')
            reused.append({'answer_id':aid,'trial_id':trial_id,'source_trial':binding(path),
                           'source_request_id':receipt['request_id'],'trial_identity':trial_identity,
                           'persisted_prompt':binding(attempt/'prompt.txt'),'logical_prompt_raw_utf8_sha256':prompt_sha,
                           'prompt_newline_note':'Original Windows text file uses CRLF; compare its byte SHA to trial and universal-newline decoded full prompt to the actual current runner capture.',
                           'copied_byte_for_byte':True,'new_requests':0})
        rows.append({'answer_id':aid,'case_id':cid,'question_id':qid,'answer_sha256':ident['answer_sha256'],'question_sha256':ident['question_sha256'],
                     'input_sha256':inp,'references_sha256':judges.digest(selected),'reference_id':selected[0]['reference_id'],
                     'trial_id':trial_id,'trial_identity':trial_identity,'status':'exact_actual_trial_reused' if exact else 'pending_service_release_new_request',
                     'planned_new_requests':0 if exact else 1})
        sources['answer_'+aid]=binding(ap);sources['packet_'+aid]=binding(HUMAN/'reviewer'/f'{aid}.json')
        cases.append(case)
    require(len(reused)==1 and reused[0]['answer_id']=='A02' and sum(r['planned_new_requests'] for r in rows)==4,'Expected A02 exact reuse and four planned new requests')
    payload={'cases':cases};plan={'scope':'five_fixed_development_answers_only_no_holdout_requests','status':'prepared_waiting_for_coordinator_service_release',
        'source_bindings':sources,'preparation_script':binding(__file__),'judge_contract':contract,'judge_contract_sha256':judges.digest(contract),
        'case_snapshot_sha256':judges.digest(payload),'model_config_snapshot_sha256':judges.digest(local),
        'fixed_development_answers':5,'holdout_selected_but_not_submitted':15,'actual_reused_extractions':1,'planned_new_requests':4,
        'maximum_new_requests':4,'new_model_requests_during_preparation':0,'expert_labels_added':0,'formal_eligible':False,
        'rows':rows,'reuse':reused,'context_checks':context,'static_context_all_fit':True,
        'live_service_identity_check':'Deferred until service release; do not run until fresh preflight contract equals this frozen contract.'}
    if (args.out/'plan.json').exists():require(judges.read(args.out/'plan.json')==plan,'Preparation source changed; do not overwrite frozen plan')
    else:save(args.out/'plan.json',plan)
    for name,obj in [('cases.json',payload),('local_config_snapshot.json',local),('frozen_judge_contract.json',contract),
                     ('offline_context_preflight.json',{'checks':context,'all_fit':True,'model_requests':0}),('reuse_manifest.json',reused)]:
        dest=args.out/name
        if dest.exists():require(judges.read(dest)==obj,'Frozen output differs: '+name)
        else:save(dest,obj)
    for reuse in reused:
        dest=args.out/'trials'/f"{reuse['trial_id']}.json";dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():require(judges.filehash(dest)==reuse['source_trial']['sha256'],'Existing reused trial bytes differ')
        else:shutil.copyfile(reuse['source_trial']['path'],dest)
    command=(f"& '{sys.executable}' scripts/cce_judges.py {{command}} --cases '{args.out/'cases.json'}' --out '{args.out}' "
             f"--model-config '{args.out/'local_config_snapshot.json'}' --models local_qwen3_8b --repeats 1 --temperature 0 "
             f"--max-output-tokens 8192 --max-attempts 1 --max-calls 4 --timeout-seconds 600 "
             f"--ledger '{BASE/'judges/request_ledger.jsonl'}' --total-budget 300")
    save(args.out/'execution_commands.json',{'actual_prepare':{'executable':sys.executable,'argv':sys.argv},
        'planned_preflight_not_executed':command.format(command='preflight'),
        'planned_run_not_executed':command.format(command='run')+' --allow-api',
        'required_before_run':'Coordinator releases local service; live preflight contract SHA must equal frozen_judge_contract.json digest.',
        'new_requests':0})
    (args.out/'README.md').write_text('''# E3 固定 5 份开发答案：v2 自动提取准备

只准备原 selection 中 A01–A05；15 份留出不提交。原题、原答案、匿名身份和原 160 行专家表不变。每题只附适用的 FDISCO v2 参考。此目录为内部执行材料，含模型身份；不能直接作为专家匿名附件。

A02 精确复用 local_controls_supplement_v2 的实际成功 baseline trial，case ID、全文、单路线参考、原 rubric、固定需求、模型 digest、8192 输出预算、temperature=0 和全部配置均一致。原 trial 字节复制不改身份；单独 reuse_manifest.json 记录来源，未重复写总 ledger。

A01、A03、A04、A05 各计划一次真实全文请求，共最多 4 次。当前仅完成静态上下文检查，没有调用生成服务。须等待协调者释放本机服务，再执行实时 preflight 并确认 contract SHA 与 frozen_judge_contract.json 相同；不同则停止，不能静默重打 A02。

全部 5 份实际提取成功前，报告仍保留原“1 条 identity、19 pending”；这里的准备不是新增专家核查或纠错效果。后续匿名附件只能包含匿名 ID、原文、真实 extraction 和来源摘要，不显示模型或分数。

实际 prepare 及尚未执行的命令见 execution_commands.json。当前新增模型请求 0、专家标签 0。
''',encoding='utf-8')
    print(json.dumps({'status':plan['status'],'dev_answers':5,'exact_A02_reuse':1,'planned_new_requests':4,
        'context_bound_min':min(r['conservative_context_bound'] for r in context),'context_bound_max':max(r['conservative_context_bound'] for r in context),
        'num_ctx':40960,'new_model_requests':0}))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare'])
    parser.add_argument('--out',type=pathlib.Path,default=OUT);args=parser.parse_args();prepare(args)
if __name__=='__main__':main()
