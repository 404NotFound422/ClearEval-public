"""Metadata-only optimizer progress: dev, E2, E4 and primary; no generation.

Only matrices, terminal records, request metadata and public summaries are read.
No sealed sources, cases, prompts, provider bodies, extracted facts or scores are
exported. A pending terminal is not a claim that a process is alive.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'optimizer_20261010'
LEDGER=BASE/'judges/request_ledger.jsonl'
AUDIT=OUT/'status_updater_v2'
CORE_SHA='d272393ecbba84495e0430d01c0b52c4f69a6d9502147bdb071371dfed2bdc20'
V1_SHA='402e0ceee4ece9279757fab77ee769bb5378f9017069c6ff1b956accfd9dad48'

def require(ok,message):
    if not ok:raise ValueError(message)
def allowed(path):
    p=Path(path);s=str(p.resolve()).lower().replace('\\','/')
    require(not any(x in s for x in ['sealed_confirmation','confirmation_manifest','identity_key','/human_review/']),
            'protected_source_path_forbidden')
    return p
def read(path):return json.loads(allowed(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(allowed(path).read_bytes()).hexdigest()
def bind(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+'.status_v2.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    os.replace(temp,p)
def write_text(path,text):
    p=Path(path);temp=p.with_name(p.name+'.status_v2.tmp');temp.write_text(text,encoding='utf8',newline='\n');os.replace(temp,p)

def ledger_index(rows):
    requests=[r for r in rows if r.get('event')=='request_started']
    by_id={r['request_id']:r for r in requests}
    require(len(by_id)==len(requests),'duplicate_global_request_id')
    require(len({r['package_request_index'] for r in requests})==len(requests),'duplicate_package_request_index')
    by_trial={}
    for r in requests:by_trial.setdefault(r['trial_id'],[]).append(r)
    return requests,by_id,by_trial

def one_observation(directory,cell,by_id,by_trial,kind,reuses):
    tid=cell['planned_trial_id'];attempt=directory/'run/attempts'/f'{tid}_1'
    terminal_path=directory/'run/trials'/f'{tid}.json'
    received=sorted((directory/'run/attempts').glob(tid+'_*/request_receipt.json'))
    require(len(received)<=1,'unexpected_multiple_receipts:'+tid)
    receipt=read(received[0]) if received else None
    requests=by_trial.get(tid,[])
    require(len(requests)<=1,'unexpected_retry_in_fixed_matrix:'+tid)
    reserved=requests[0] if requests else None
    if receipt is not None:
        require(receipt==by_id.get(receipt['request_id']),'receipt_not_in_ledger_snapshot:'+tid)
        require(receipt['trial_id']==tid and receipt['attempt']==1,'receipt_identity_or_attempt:'+tid)
        require(receipt.get('judge',receipt.get('model'))==cell['identity']['judge'],'receipt_judge_mismatch:'+tid)
    if reserved is not None:
        require(reserved['attempt']==1 and reserved.get('judge',reserved.get('model'))==cell['identity']['judge'],'ledger_cell_identity_mismatch:'+tid)
    reservation_path=attempt/'request_reservation.json'
    if reservation_path.exists():
        require(read(reservation_path)==reserved,'reservation_not_actual_ledger_record:'+tid)
    t=read(terminal_path) if terminal_path.exists() else None
    local_no_dispatch=False;failure_stage=None;conversion_errors=[]
    if t is not None:
        require(t.get('trial_id')==tid and t.get('identity')==cell['identity'] and t.get('attempt')==1,'terminal_identity_mismatch:'+tid)
        require(t.get('status') in ['success','failed'],'nonterminal_status_in_terminal_file:'+tid)
        actual=t.get('actual_api_request_made')
        require(isinstance(actual,bool),'terminal_actual_request_flag_required:'+tid)
        require(actual==(receipt is not None),'terminal_receipt_dispatch_mismatch:'+tid)
        if not actual:
            require(t['status']=='failed','successful_observation_without_request:'+tid)
            local=attempt/'local_failure_record.json'
            require(bool(t.get('local_failure_reason')) or local.is_file(),'local_failure_requires_explicit_reason_or_record:'+tid)
            local_no_dispatch=True
        if kind=='primary':
            require(t.get('budget_reservation_made')==reservation_path.exists(),'primary_reservation_provenance_mismatch:'+tid)
        e=t.get('evaluation') or {}
        failure_stage=e.get('failure_stage') or (t.get('error') or {}).get('stage')
        # Preserve prior public-development status details only. Primary status
        # never exports source quotes, evaluation contents or conversion errors.
        if kind=='development':
            for k,v in e.items():
                if k.startswith('grounded_extraction_v') and isinstance(v,dict):conversion_errors.extend(v.get('conversion_errors',[]))
    is_reused=cell.get('disposition')=='exact_prior_observation_reused'
    reuse_verified=False
    if is_reused:
        require(kind=='E4' and tid in reuses and t is not None and receipt is not None,'reuse_manifest_or_terminal_missing:'+tid)
        r=reuses[tid]
        require(r['identity']==cell['identity'] and r['status']==t['status'] and r['original_request_id']==receipt['request_id'],
                'reused_observation_metadata_changed:'+tid)
        require(r['original_package_request_index']==receipt['package_request_index'] and cell['original_request_id']==receipt['request_id'],
                'reuse_request_identity_changed:'+tid)
        source=Path(r['reused_from'])
        require('/grounded_development_v' in source.as_posix() and '/run/trials/' in source.as_posix(),'reuse_source_not_public_development_trial')
        require(sha(source)==sha(terminal_path),'copied_reused_terminal_not_byte_identical:'+tid)
        listed={str(Path(x['path']).resolve()):x['sha256'] for x in r['original_files']}
        require(listed.get(str(source.resolve()))==sha(source),'original_trial_hash_not_bound_in_reuse_manifest')
        require(r.get('new_ledger_reservation') is False and r.get('all_source_reference_prompt_model_demand_KB_score_conversion_equal') is True,
                'complete_prior_reuse_proof_not_recorded')
        reuse_verified=True
    return {
        'anonymous_answer_id':cell.get('anonymous_answer_id'),'control_id':cell.get('control_id'),
        'trial_id':tid,'judge':cell['identity']['judge'],'repeat_index':cell['identity'].get('repeat_index',0),
        'disposition':'exact_prior_observation_reused' if is_reused else 'new_request',
        'request_id':reserved['request_id'] if reserved else None,
        'request_index':reserved['package_request_index'] if reserved else None,
        'budget_counted_reservation':reserved is not None,
        'provider_dispatch_receipt_present':receipt is not None,
        'status':t['status'] if t else 'no_terminal_record','failure_stage':failure_stage,
        'conversion_errors':conversion_errors,'local_failure_without_dispatch':local_no_dispatch,
        'local_failure_without_budget_reservation':local_no_dispatch and reserved is None,
        'reuse_metadata_and_copied_terminal_verified':reuse_verified,
        'terminal_sha256':sha(terminal_path) if t else None,
        'receipt_sha256':sha(received[0]) if receipt else None,
        'reservation_sha256':sha(reservation_path) if reservation_path.exists() else None}

def stage(directory,kind,planned,summary_relative,by_id,by_trial):
    matrix_path=directory/'matrix.json';matrix=read(matrix_path) if matrix_path.exists() else None
    common={'name':directory.name,'kind':kind,'planned_observations':planned,'matrix_present':matrix is not None,
        'matrix_sha256':sha(matrix_path) if matrix is not None else None,
        'expected_reused_observations':5 if kind=='E4' else 0,'expected_new_requests_maximum':25 if kind=='E4' else planned}
    if matrix is None:
        return {**common,'stage_status':'pending_not_prepared','requests_started':0,'new_budget_counted_requests':0,
            'new_provider_dispatch_receipts':0,'reused_observations':0,'request_backed_observations':0,
            'terminal_observations':0,'technical_successes':0,'technical_failures':0,'pending_terminal_records':planned,
            'local_failures_without_dispatch':0,'local_failures_without_budget_reservation':0,
            'analyzed':False,'analysis_complete':False,'completion_summary_sha256':None,
            'complete_numeric_after_component_gates':None,'fact_audit_summary_available':False,'fact_audit_complete':False,
            'fact_audit_summaries':[],'observations':[]}
    require(len(matrix)==planned and len({r['planned_trial_id'] for r in matrix})==planned,'matrix_denominator_or_duplicate:'+directory.name)
    reuse_path=directory/'reuse_manifest.json';reuses={r['trial_id']:r for r in read(reuse_path)} if reuse_path.exists() else {}
    observations=[one_observation(directory,r,by_id,by_trial,kind,reuses) for r in matrix]
    reused=[r for r in observations if r['disposition']=='exact_prior_observation_reused']
    if kind=='E4':require(len(reused)==5 and len(reuses)==5,'E4_actual_matrix_requires_five_exact_reuses')
    new=[r for r in observations if r['disposition']=='new_request']
    terminal=sum(r['status'] in ['success','failed'] for r in observations)
    success=sum(r['status']=='success' for r in observations)
    summary_path=directory/summary_relative
    summary=read(summary_path) if summary_path.exists() else None
    analysis_complete=False
    if summary:
        n=summary.get('actual_observations',summary.get('actual_terminal_observations',summary.get('actual_terminal_answers',summary.get('observations'))))
        if n is None and kind=='development' and summary.get('status')=='complete':
            # Earliest v1 summary declares only its planned denominator. Actual
            # terminals are still counted and required, never inferred from it.
            require(terminal==planned,'historical_complete_summary_missing_actual_terminals')
            n=summary.get('planned_observations')
        require(n is not None and n<=terminal,'summary_ahead_of_actual_terminal_metadata:'+directory.name)
        analysis_complete=n==planned
        if analysis_complete:
            known=summary.get('technical_successes',summary.get('successes',summary.get('technical_complete')))
            require(known==success,'summary_success_count_mismatch:'+directory.name)
    fact_paths=sorted(directory.glob('independent_fact_audit_v*/summary.json')) if kind=='development' else []
    fact_metadata=[{**bind(p),'status':read(p).get('status'),'fixed_answers':read(p).get('fixed_answers')} for p in fact_paths]
    new_count=sum(r['budget_counted_reservation'] for r in new)
    status=('analyzed_complete' if analysis_complete else 'terminal_pending_analysis' if terminal==planned else
            'incomplete_actual_batch' if new_count or terminal else 'prepared_not_started')
    return {**common,'stage_status':status,'requests_started':new_count,'new_budget_counted_requests':new_count,
        'new_provider_dispatch_receipts':sum(r['provider_dispatch_receipt_present'] for r in new),
        'reused_observations':len(reused),'reused_successes':sum(r['status']=='success' for r in reused),
        'reused_failures':sum(r['status']=='failed' for r in reused),
        'reuse_manifest_sha256':sha(reuse_path) if reuse_path.exists() else None,
        'request_backed_observations':sum(r['provider_dispatch_receipt_present'] for r in observations),
        'terminal_observations':terminal,'technical_successes':success,'technical_failures':sum(r['status']=='failed' for r in observations),
        'pending_terminal_records':planned-terminal,'local_failures_without_dispatch':sum(r['local_failure_without_dispatch'] for r in observations),
        'local_failures_without_budget_reservation':sum(r['local_failure_without_budget_reservation'] for r in observations),
        'analyzed':summary is not None,'analysis_complete':analysis_complete,
        'complete_numeric_after_component_gates':summary.get('complete_numeric_after_component_gates',summary.get('complete_numeric',summary.get('complete_numeric_CCE'))) if summary else None,
        'completion_summary_sha256':sha(summary_path) if summary else None,'summary_path':str(summary_path),
        'fact_audit_summary_available':bool(fact_paths),
        'fact_audit_complete':bool(fact_metadata) and all(x['status']=='complete' and x['fixed_answers']==planned for x in fact_metadata),
        'fact_audit_summaries':fact_metadata,
        'observations':observations}

def collect():
    ledger_bytes=LEDGER.read_bytes();ledger=[json.loads(x) for x in ledger_bytes.decode('utf8').splitlines() if x.strip()]
    requests,by_id,by_trial=ledger_index(ledger)
    plan=read(OUT/'plan.json');require(len(requests)<=plan['whole_package_request_limit'],'whole_package_budget_exceeded')
    dirs=[OUT/'model_probe_v1']+sorted(OUT.glob('grounded_development_v*'),key=lambda p:int(p.name.rsplit('v',1)[1]))
    stages=[stage(p,'development',5,'completion_summary.json',by_id,by_trial) for p in dirs if (p/'matrix.json').exists()]
    stages += [stage(OUT/'grounded_controls_v1','E2',21,'completion_summary.json',by_id,by_trial),
        stage(OUT/'grounded_stability_dev_v1','E4',30,'analysis/completion_summary.json',by_id,by_trial),
        stage(OUT/'grounded_confirmation_v3','primary',16,'completion_summary.json',by_id,by_trial)]
    # Duplicated references to original dev requests occur only in exact E4 reuse.
    new_ids=[r['request_id'] for s in stages for r in s['observations'] if r['budget_counted_reservation'] and r['disposition']=='new_request']
    require(len(new_ids)==len(set(new_ids)),'a_new_request_was_counted_in_multiple_stages')
    require(LEDGER.read_bytes()==ledger_bytes,'ledger_snapshot_changed_rerun_status_only')
    return ledger_bytes,requests,plan,stages

def main():
    require(sha(ROOT/'scripts/cce_validation.py')==CORE_SHA,'original_core_changed')
    require(sha(ROOT/'scripts/cce_optimizer_status_v1.py')==V1_SHA and sha(AUDIT/'cce_optimizer_status_v1_snapshot.py')==V1_SHA,'preserved_v1_changed')
    for attempt in range(3):
        try:ledger_bytes,requests,plan,stages=collect();break
        except (ValueError,json.JSONDecodeError) as exc:
            if attempt==2:raise
            if isinstance(exc,ValueError) and not any(x in str(exc) for x in ['ledger_snapshot_changed','receipt_not_in_ledger_snapshot']):raise
    now=datetime.now(timezone.utc).isoformat()
    phases={s['kind']:s for s in stages if s['kind']!='development'}
    selected=next(s for s in stages if s['name']=='grounded_development_v7')
    allocation=read(OUT/'grounded_v7_design_v1/budget_allocation_amendment.json')
    next_text=('开发v7已完成实际终态和独立事实审查；当前按固定最终配置完成E2，随后E4及主自动确认，所有失败保留。'
        if selected['analysis_complete'] else '完成开发v7实际终态和独立事实审查，再按固定后续矩阵执行。')
    if phases['E2']['analysis_complete']:next_text='E2实际分析已完成；继续E4真实重复及主自动确认，保留所有失败和组件NA。'
    if phases['E4']['analysis_complete']:next_text='E4实际分析已完成；等待root最终release后执行固定8×2主自动确认，禁止确认后调参。'
    if phases['primary']['analysis_complete']:next_text='各自动测量批次已分析；完成独立结果审查与最终报告，专家和真实湿数据依赖单列，不自动宣称全目标完成。'
    result={'status':'active','status_schema_version':'optimizer_status_v2','updated_utc':now,
        'requests':len(requests),'request_count_definition':'Unique real request_started ledger records; includes budget reservations that fail before dispatch. Exact reused observations do not add records.',
        'remaining_requests_under_original_cap':plan['whole_package_request_limit']-len(requests),
        'prospective_allocated_end_ceiling':allocation['max_total_if_all_phases_run'],
        'remaining_under_allocated_ceiling':allocation['max_total_if_all_phases_run']-len(requests),
        'unallocated_calls':allocation['unallocated_calls'],'unallocated_calls_authorize_retries':False,
        'optional_blind_execution_allowed':False,'ledger_snapshot_sha256':hashlib.sha256(ledger_bytes).hexdigest(),
        'deadline_utc':plan['deadline_utc'],'stages':stages,
        'selected_development_version':'v7','selected_development_analysis_complete':selected['analysis_complete'],
        'selected_development_facts_complete':selected['fact_audit_complete'],
        'followup_phase_states':{k:s['stage_status'] for k,s in phases.items()},
        'original_core_sha256_verified':CORE_SHA,'preserved_status_v1_sha256':V1_SHA,
        'human_expert_returns':0,'human_return_note':'No real expert return has been received in this optimization session; model-source review is separate.',
        'process_liveness':'Not inferred from missing or present terminal files. Root must poll its actual session before deciding to resume or restart.',
        'source_read_scope':'Only explicit public metadata, planned cell identity and terminal status/provenance; no sealed source, case text, prompt, provider body or scientific score export.',
        'next':next_text,'updater':bind(__file__),'new_model_requests_by_status_update':0}
    save(OUT/'STATUS.json',result)
    lines=['# ClearEval 当前优化阶段','',
        f'更新时间：{now}。全包账本实际计次 **{len(requests)}/300**；当前前瞻分配上限294，另6次未分配不授权重试。','',
        '[冻结总计划](optimizer_20261010/plan.json) · [动态状态与逐次证据](optimizer_20261010/STATUS.json) · [新增结果](optimizer_20261010/RESULTS_zh.md)','',
        '| 阶段 | 终态/计划 | 技术成功 | 技术失败 | 新计次 | 已复用 | 分析 |','|---|---:|---:|---:|---:|---:|---|']
    for s in stages:
        name=s['name'];label=name
        if s['matrix_present']:
            rel=s['summary_path'] if s['analyzed'] else str(OUT/name/'matrix.json')
            label=f"[{name}]({Path(rel).relative_to(BASE).as_posix()})"
        done='完成' if s['analysis_complete'] else '部分分析' if s['analyzed'] else '待实际终态后分析'
        lines.append(f"| {label} | {s['terminal_observations']}/{s['planned_observations']} | {s['technical_successes']} | {s['technical_failures']} | {s['new_budget_counted_requests']} | {s['reused_observations']} | {done} |")
    lines += ['',next_text,'',
        '“新计次”按全包唯一账本记录统计；E4已复用记录保留原trial/回执，不重复加请求。provider实际dispatch回执与账本reservation分列；主确认的明确本地失败可以没有回执，仍保留在16个观察分母中。',
        '技术成功不等于事实准确、完整数值或科学验证。开发v7的5/5技术通过与所有事实未决/NA分别报告，不因达到结构门而删除失败历史。',
        '没有终态只表示待完成，不能据此判断进程存活。原一位专家5+15保持，真实回传0；真实湿实验依赖单列。已记录的检索范围事件见[公开审计](optimizer_20261010/root_search_scope_audit_20261010.md)。','',
        '原主50/77、条件方法池66/77及192阶段图表见[历史入口](historical_reports/before_optimizer_at_192/CURRENT_RESULTS_INDEX.md)，不替换成当前候选结果。','',
        '状态更新命令：`python scripts/cce_optimizer_status_v2.py`。旧v1字节原样保留；本脚本不调用模型、不启动或重试任何任务。各实际实验命令见对应目录。','']
    write_text(BASE/'STATUS.md','\n'.join(lines))
    write_text(ROOT.parent/'STATUS.md','# ClearEval 当前状态\n\n见[当前优化状态](ClearEval-public/artifacts/cce_validation/STATUS.md)。\n\n'
        +f"账本计次{len(requests)}/300。开发v7分析{'完成' if selected['analysis_complete'] else '待完成'}；E2 {phases['E2']['stage_status']}，E4 {phases['E4']['stage_status']}，主确认 {phases['primary']['stage_status']}。\n\n"
        +'精确复用不重复计次，本地失败保留；技术通过不等于科学验证，专家回传0。文件状态不用于推测进程活性。\n')
    command_path=OUT/'status_actual_commands_v2.json';commands=read(command_path) if command_path.exists() else []
    commands.append({'utc':now,'argv':[sys.executable,*sys.argv],'cwd':str(ROOT),'script_sha256':sha(__file__),
        'ledger_snapshot_sha256':result['ledger_snapshot_sha256'],'requests_snapshot':len(requests),'new_model_requests':0,
        'outputs':[bind(p) for p in [OUT/'STATUS.json',BASE/'STATUS.md',ROOT.parent/'STATUS.md']]})
    save(command_path,commands)
    print(json.dumps({'status':'updated_metadata_only','requests':len(requests),'development_complete':selected['analysis_complete'],
        'followup':result['followup_phase_states'],'new_model_requests':0},ensure_ascii=False))

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
