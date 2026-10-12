"""Frozen five-development-answer E4 diagnostic using unchanged identity_v2.

Preparation/preflight are metadata and prompt capture only. The original failed
A04 repeat-zero observation is retained. No held-out material is accessed.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, io, json, shutil, sys, urllib.request
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_output_identity_v2 as identity
import cce_output_contract_v1 as parent
import cce_alternative_development as helper
import cce_judges as j

OUT=ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1'
RUN=OUT/'run';MODELS=['local_qwen3_8b','local_llama3_8b'];IDS=['A01','A02','A03','A04','A05']
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']
DERIVED=['Com','Cor','Eff','IA','HV']

def require(ok,why):
    if not ok:raise ValueError(why)

def args(allow=False):
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'local_config_snapshot.json',
        models=MODELS,question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None,ledger=parent.LEDGER,total_budget=300,external_request_count=0,max_calls=25,
        max_attempts=1,repeats=3,temperature=0.0,max_output_tokens=8192,timeout_seconds=600,allow_api=allow)

def record(action,**details):
    p=OUT/'actual_execution_commands.json';rows=j.read(p) if p.exists() else []
    cmd=[sys.executable,'scripts/cce_identity_stability_dev_v1.py',action]
    if action=='run':cmd+=['--allow-local-calls']
    rows.append({'utc':j.now(),'argv':cmd,'cwd':str(ROOT),'script_sha256':j.filehash(__file__),
                 'package_requests_snapshot':parent.request_count(),**details});j.save(p,rows)

def validate():
    identity.validate();identity.require_probes();plan=j.read(OUT/'plan.json')
    for entry in plan['frozen_inputs']+plan['reused_original_files']:
        require(j.filehash(entry['path'])==entry['sha256'],'frozen_input_changed:'+entry['path'])
    require(plan['planned_observations']==30 and plan['planned_new_requests']==25 and plan['reused_observations']==5,'fixed_matrix_changed')
    return plan

@contextlib.contextmanager
def frozen_runtime():
    """Use unchanged v2 wrapper, with orchestration-only contract drift rejection."""
    expected=j.read(OUT/'expected_scientific_contract.json')
    with identity.wrapper():
        previous=j.contract
        def guarded(*a,**kw):
            actual=previous(*a,**kw)
            require(actual==expected,'runtime_science_or_model_contract_drift_before_request')
            return actual
        j.contract=guarded
        try:yield
        finally:j.contract=previous

def verify_copied_observations():
    for reuse in j.read(OUT/'reuse_manifest.json'):
        for original in reuse['original_files']:
            source=Path(original['path']);target=RUN/source.relative_to(identity.RUN)
            require(target.exists() and j.filehash(target)==original['sha256'],'copied_observation_sidecar_drift')

def verify_reuse(cases,contract,copy=False):
    oldpre=j.read(identity.OUT/'preflight_verification.json')
    original_contract=j.read(identity.RUN/'preflight.json')['contract']
    qmodel=next(m for m in contract['models'] if m['name']=='local_qwen3_8b')
    single={**contract,'models':[qmodel]}
    require(single==original_contract and j.digest(single)==oldpre['contract_sha256'],'Qwen_science_contract_not_exactly_identical')
    require({**contract,'models':[]}=={**original_contract,'models':[]},'shared_science_configuration_changed')
    ledger={x['request_id']:x for x in j.ledger_rows(parent.LEDGER) if x.get('event')=='request_started'}
    source={t['case_id']:(p,t) for p in (identity.RUN/'trials').glob('*.json') for t in [j.read(p)]}
    require(set(source)=={c['case_id'] for c in cases},'original_five_trials_missing_or_extra')
    reuse=[];protected=[]
    for c in cases:
        aid=c['anonymous_answer_id'];p,t=source[c['case_id']]
        expected={'case_id':c['case_id'],'input_sha256':c['input_sha256'],'judge':'local_qwen3_8b',
                  'repeat_index':0,'contract_sha256':j.digest(single)}
        require(t['identity']==expected and t['trial_id']==j.digest(expected),'repeat_zero_original_trial_identity_changed')
        require(t['attempt']==1 and t['repeat_index']==0 and t['actual_api_request_made'],'real_one_attempt_required')
        require(t['full_text_input_sha256']==c['input_sha256'] and t['references_sha256']==j.digest(c['references']),'original_full_input_or_reference_changed')
        require(t['pipeline_config_sha256']==j.digest({**single,'models':[]}),'original_pipeline_hash_changed')
        require(t['actual_returned_model']==qmodel['settings']['model'],'actual_returned_model_changed')
        attempt=identity.RUN/'attempts'/f"{t['trial_id']}_1";receipt=j.read(attempt/'request_receipt.json')
        require(receipt==ledger.get(receipt['request_id']) and receipt['trial_id']==t['trial_id'] and receipt['attempt']==1,'original_receipt_not_in_global_ledger')
        prompt=(identity.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf8')
        require((attempt/'prompt.txt').read_text(encoding='utf8')==prompt and j.filehash(attempt/'prompt.txt')==t['prompt_sha256'],'transmitted_prompt_not_exact')
        require(prompt==(OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf8'),'new_expected_prompt_changed')
        require(j.read(attempt/'result.json')==t,'attempt_trial_disagreement')
        require((attempt/'provider_response.json').exists(),'original_completed_provider_payload_missing')
        files=[p,*sorted(x for x in attempt.rglob('*') if x.is_file())]
        protected.extend(files)
        row={'anonymous_answer_id':aid,'question_id':c['question_id'],'case_id':c['case_id'],
             'trial_id':t['trial_id'],'identity':expected,'status':t['status'],'attempt':1,
             'reused_from':str(p),'original_trial_sha256':j.filehash(p),'original_request_id':receipt['request_id'],
             'original_package_request_index':receipt['package_request_index'],'prompt_sha256':t['prompt_sha256'],
             'full_text_input_sha256':c['input_sha256'],'references_sha256':t['references_sha256'],
             'same_input_reference_prompt_model_demand_and_science_contract':True,
             'new_ledger_reservation':False,'failed_observation_retained_without_retry':t['status']=='failed',
             'original_files':[parent.bind(x) for x in files]}
        if copy:
            dest=RUN/'trials'/p.name;dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():require(dest.read_bytes()==p.read_bytes(),'reused_trial_destination_changed')
            else:shutil.copyfile(p,dest)
            for original in files[1:]:
                target=RUN/'attempts'/attempt.name/original.relative_to(attempt);target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():require(target.read_bytes()==original.read_bytes(),'reused_attempt_destination_changed')
                else:shutil.copyfile(original,target)
            row['copied_to']=str(dest);row['copy_byte_identical']=True
        reuse.append(row)
    require([r['anonymous_answer_id'] for r in reuse]==IDS,'fixed_development_order')
    require(sum(r['status']=='failed' for r in reuse)==1 and next(r for r in reuse if r['status']=='failed')['anonymous_answer_id']=='A04','source_negative_result_not_retained')
    return reuse,protected

def metadata_show(models):
    rows=[]
    from models.Ollama_LLM import LocalOllamaHTTPClient
    for model in models:
        public=model['public'];host=public['host'];client=LocalOllamaHTTPClient(host,4)
        body=json.dumps({'model':public['model']}).encode('utf8')
        request=urllib.request.Request(host.rstrip('/')+'/api/show',data=body,headers={'Content-Type':'application/json'},method='POST')
        with client.opener.open(request,timeout=10) as response:data=json.load(response)
        context={k:v for k,v in data.get('model_info',{}).items() if k.endswith('.context_length')}
        require(context and min(context.values())>=public['num_ctx'],'native_model_context_unknown_or_too_small')
        p=OUT/'model_metadata'/f"{model['name']}_show.json";j.save(p,data)
        rows.append({'judge':model['name'],'model':public['model'],'digest':public['model_digest'],
            'native_context_fields':context,'configured_context':public['num_ctx'],'show_response':parent.bind(p),
            'metadata_endpoint_only':True,'generation_endpoint_called':False})
    return rows

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():validate();record('prepare',status='frozen_plan_reused',new_requests=0);return
    identity.validate();identity.require_probes();before=parent.request_count()
    require(before+25<=300,'insufficient_remaining_budget')
    for name in ['cases.json','local_config_snapshot.json','final_output_schema.json']:(OUT/name).write_bytes((identity.OUT/name).read_bytes())
    cases=j.read(OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==IDS,'five_development_ids_changed')
    frozen=[Path(__file__),OUT/'cases.json',OUT/'local_config_snapshot.json',OUT/'final_output_schema.json',
        identity.OUT/'plan.json',identity.OUT/'preflight_verification.json',identity.OUT/'software_probes.json',
        identity.OUT/'analysis/completion_summary.json',Path(identity.__file__),Path(parent.__file__),
        Path(helper.__file__),identity.RUN/'preflight.json']
    prompt_checks=[]
    for c in cases:
        aid=c['anonymous_answer_id']
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):prompt=identity.transform(helper.exact_runner_prompt(c))
        original=(identity.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf8')
        require(prompt==original,'captured_final_prompt_not_identity_v2')
        require(prompt.endswith(parent.v2.reference_suffix(c)),'same_complete_reference_suffix')
        for k in ['specific_question','model_response']:require(prompt.count(c[k])==1,'original_fulltext_not_exactly_once')
        require(parent.rawsha(c['model_response'])==c['answer_sha256'] and parent.rawsha(c['specific_question'])==c['question_sha256'],'original_fulltext_hash')
        bound=len(prompt.encode('utf8'))+8192+256;require(bound<=40960,'full_context_exceeds_frozen_limit')
        p=OUT/'prompts'/f'{aid}_prompt.txt';p.parent.mkdir(exist_ok=True);p.write_text(prompt,encoding='utf8');frozen.extend([p,identity.OUT/'prompts'/f'{aid}_prompt.txt'])
        prompt_checks.append({'anonymous_answer_id':aid,'question_id':c['question_id'],'case_id':c['case_id'],
            'answer_sha256':c['answer_sha256'],'question_sha256':c['question_sha256'],'references_sha256':j.digest(c['references']),
            'prompt_sha256':j.filehash(p),'prompt_byte_identical_to_existing_identity_v2':True,'conservative_context_bound':bound})
    with identity.wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,prepared,contract=j.preflight(args())
    require([m['name'] for m in models]==MODELS,'fixed_judges_changed')
    meta=metadata_show(models);j.save(OUT/'model_context_verification.json',meta);frozen.append(OUT/'model_context_verification.json')
    frozen.extend(Path(r['show_response']['path']) for r in meta)
    j.save(OUT/'expected_scientific_contract.json',contract);frozen.append(OUT/'expected_scientific_contract.json')
    reuse,protected=verify_reuse(prepared,contract,copy=True);j.save(OUT/'reuse_manifest.json',reuse);frozen.append(OUT/'reuse_manifest.json')
    original_contract=j.read(identity.RUN/'preflight.json')['contract'];j.save(RUN/'contracts'/f'{j.digest(original_contract)}.json',original_contract)
    cells=[]
    for repeat in range(3):
        for c in prepared:
            for model in contract['models']:
                one={**contract,'models':[model]};ident={'case_id':c['case_id'],'input_sha256':c['input_sha256'],'judge':model['name'],'repeat_index':repeat,'contract_sha256':j.digest(one)}
                old=next((r for r in reuse if r['trial_id']==j.digest(ident)),None)
                cells.append({'anonymous_answer_id':c['anonymous_answer_id'],'question_id':c['question_id'],
                    'identity':ident,'planned_trial_id':j.digest(ident),'attempt':1,'disposition':'exact_prior_observation_reused' if old else 'new_request_planned',
                    'original_status':old['status'] if old else None,'original_request_id':old['original_request_id'] if old else None})
    require(len(cells)==len({r['planned_trial_id'] for r in cells})==30 and sum(r['disposition']=='new_request_planned' for r in cells)==25,'actual_cell_matrix')
    j.save(OUT/'matrix.json',cells);frozen.append(OUT/'matrix.json')
    plan={'schema':'identity-stability-development-diagnostic-v1','status':'frozen_before_new_generation','created_utc':j.now(),
        'original_prompt_version':'output_identity_v2','no_further_prompt_intervention':True,
        'scientific_wrapper':str(Path(identity.__file__).resolve()),'wrapper_source_sha256':j.filehash(identity.__file__),
        'source_selection':'Original fixed A01-A05, selected before these diagnostic results; includes A04 failure; no heldout.',
        'anonymous_ids':IDS,'question_ids':[c['question_id'] for c in prepared],'judges':MODELS,
        'repeats_per_case_judge':3,'planned_observations':30,'reused_observations':5,'planned_new_requests':25,
        'reused_successes':4,'reused_failures':1,'max_attempts':1,'temperature':0,'max_output_tokens':8192,
        'num_ctx':40960,'timeout_seconds':600,'decoder_format':'json','total_budget':300,'package_requests_snapshot':before,
        'request_order':'repeat, fixed A-id, fixed judge order; no success/score-based selection',
        'sequence_gate':'Run only after root review and E2 completion; no generation during prepare/preflight.',
        'gate_interpretation':'The earlier 4/5 structural gate remains failed. This is an independent exposed-development failure/stability diagnostic, not promotion to holdout or proof of repair.',
        'scientific_contract_sha256':j.digest(contract),'prompt_checks':prompt_checks,
        'metrics':{'direct_judge_scores':DIRECT,'computed_EGES':EGES,'deterministic_reused_steps':['SR','SP'],
             'derived_aggregates':DERIVED,'tolerance':1e-12,
             'dependency_boundary':'SR/SP are unchanged deterministic inputs; EGES and composites are derived, not independent direct-judge agreement evidence.',
             'missingness_rule':'All 30 planned cells retained. Failures are NA, never zero. Report coverage/complete-repeat denominators separately for each metric.',
             'within_judge':'5 cases x 2 judges x 3 actual observations; raw score and failure reproducibility.',
             'between_judges':'Five fixed answers; paired actual observations and complete-group means with explicit valid denominators.',
             'no_best_repeat_selection':True},
        'no_expert_packet_replacement':True,'formal_eligible':False,'expert_returns':0,
        'frozen_inputs':[parent.bind(p) for p in dict.fromkeys(frozen)],
        'reused_original_files':[parent.bind(p) for p in dict.fromkeys(protected)],
        'planned_run_not_executed':[sys.executable,'scripts/cce_identity_stability_dev_v1.py','run','--allow-local-calls']}
    j.save(OUT/'plan.json',plan);validate();require(parent.request_count()==before,'prepare_reserved_request')
    record('prepare',status='completed_zero_generation',new_requests=0,reused_observations=5,planned_new_requests=25)
    (OUT/'README.md').write_text('# 固定五份开发答案的 E4 重复诊断（待运行）\n\n5 答案 × 2 评价器 × 3 次真实观测，共 30 格。严格复用 output_identity_v2 的 5 个 Qwen repeat 0 原 trial 与侧车；其中 A04 失败原样保留，不重试、不换样本。仅剩 25 个新请求待根代理审查并待 E2 结束后执行。\n\n提示、量表、知识库、EGES、解析器及已有 identity_v2 wrapper 全部不改。5/5 门槛仍未通过；本批限已公开开发材料的失败复现与稳定性诊断，不推广到留出或人工建议版本。SR/SP 为复用的确定性值，不计独立 judge 一致性证据。所有失败和 NA 保留，直接评分、EGES 与派生指标分开列出。\n\n[冻结计划](plan.json)、[30 格矩阵](matrix.json)、[5 条原身份复用清单](reuse_manifest.json)、[实际预检](preflight_verification.json)、[命令记录](actual_execution_commands.json)。\n\n命令：`python scripts/cce_identity_stability_dev_v1.py prepare`，随后 `python scripts/cce_identity_stability_dev_v1.py preflight`。待授权运行命令：`python scripts/cce_identity_stability_dev_v1.py run --allow-local-calls`。新增 judge：0。\n',encoding='utf8')
    print(j.canonical({'status':'prepared_zero_generation','planned_observations':30,'reused':5,'new_calls_planned':25,'new_requests':0}))

def preflight():
    plan=validate();before=parent.request_count()
    with frozen_runtime(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    require(contract==j.read(OUT/'expected_scientific_contract.json'),'current_model_or_science_contract_changed')
    reuse,_=verify_reuse(cases,contract)
    copied=j.read(OUT/'reuse_manifest.json')
    for old,new in zip(copied,reuse):
        require({k:v for k,v in old.items() if k not in ['copied_to','copy_byte_identical']}==new,'reuse_binding_changed')
        require(j.filehash(old['copied_to'])==old['original_trial_sha256'],'copied_trial_not_exact')
    require(len(list((RUN/'trials').glob('*.json')))==5,'preflight_must_precede_new_trials')
    verify_copied_observations()
    require(parent.request_count()==before,'preflight_reserved_request')
    result={'status':'pass','plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'scientific_contract_sha256':j.digest(contract),'planned_observations':30,'exact_reused_observations':5,
        'reused_successes':4,'reused_failures':1,'planned_new_requests':25,'max_attempts':1,
        'local_metadata_only':True,'generation_endpoint_called':False,'new_requests':0,
        'same_prompt_and_science_per_model_contract':True,'strict_parser_preserved':True,
        'A04_failed_repeat_zero_retained_without_retry':True,'original_5_of_5_gate_passed':False,
        'root_generation_authorization_still_required':True,'package_requests_snapshot':before}
    j.save(OUT/'preflight_verification.json',result);record('preflight',status='pass',new_requests=0)
    print(j.canonical(result))

async def run():
    validate();pre=j.read(OUT/'preflight_verification.json')
    require(pre['status']=='pass' and pre['plan_sha256']==j.filehash(OUT/'plan.json') and pre['script_sha256']==j.filehash(__file__),'current_preflight_required')
    ids={r['planned_trial_id'] for r in j.read(OUT/'matrix.json') if r['disposition']=='new_request_planned'}
    before=sum(x.get('event')=='request_started' and x['trial_id'] in ids for x in j.ledger_rows(parent.LEDGER))
    verify_copied_observations()
    with frozen_runtime():await j.run(args(True))
    after=sum(x.get('event')=='request_started' and x['trial_id'] in ids for x in j.ledger_rows(parent.LEDGER))
    require(after<=25,'fixed_new_request_cap_exceeded');validate()
    record('run',status='runner_returned',new_requests=after-before,total_new_requests_for_this_batch=after)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run']);p.add_argument('--allow-local-calls',action='store_true');parsed=p.parse_args()
    if parsed.action=='run':require(parsed.allow_local_calls,'explicit_local_call_authorization_required');asyncio.run(run())
    else:{'prepare':prepare,'preflight':preflight}[parsed.action]()
