"""Version-aware report assembly; default draft only, no experiments or generation.

The immutable 136-request snapshot anchors historical results. A current ledger
snapshot is checked against known new trial identities and actual receipts. The
live ledger is never required to retain its historical 136-request hash.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, re, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/cce_validation'
HIST=BASE/'historical_reports/before_method_family_at_136'
STAGE=BASE/'method_family_followup_v1';DRAFT=STAGE/'report_draft'
VERSION='method_family_conditional_and_frozen_prompt_development_v1'
INPUTS={}
def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(b):return hashlib.sha256(b).hexdigest()
def canonical(o):return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(o):return rawsha(canonical(o).encode('utf8'))
def bind(p):
    p=Path(p).resolve();INPUTS[str(p)]=sha(p);return p
def read(p):return json.loads(bind(p).read_text(encoding='utf-8-sig'))
def save(p,o):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s.strip()+'\n',encoding='utf8')
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def ledger_lines(raw):return [json.loads(s) for s in raw.decode('utf8').splitlines() if s.strip()]
def relative(p,base):return os.path.relpath(Path(p),base).replace('\\','/')

BATCHES={
 'output_contract_v1':{'n':5,'new':5,'summary':'analysis/completion_summary.json','verification':'analysis/analysis_verification.json'},
 'output_identity_v2':{'n':5,'new':5,'summary':'analysis/completion_summary.json','verification':'analysis/analysis_verification.json'},
 'controls_contract_v2':{'n':21,'new':21,'summary':'development_summary.json','verification':'verification.json'},
 'identity_stability_dev_v1':{'n':30,'new':25,'summary':'analysis/completion_summary.json','verification':'analysis/analysis_verification.json'},
}

def known_batches():
    batches={};owners={}
    for name,spec in BATCHES.items():
        base=BASE/'judges'/name;plan=read(base/'plan.json');pre=read(base/'preflight_verification.json')
        require(pre['plan_sha256']==sha(base/'plan.json'),'preflight_plan_binding:'+name)
        cells=read(base/'matrix.json') if name=='identity_stability_dev_v1' else pre['planned_trials']
        require(len(cells)==spec['n'],'planned_matrix_size:'+name)
        for cell in cells:
            tid=cell['planned_trial_id'];require(digest(cell['identity'])==tid,'planned_trial_hash')
            is_reuse=cell.get('disposition')=='exact_prior_observation_reused'
            if is_reuse:
                require(tid in owners and owners[tid]['batch']=='output_identity_v2','reuse_not_original_identity_v2')
            else:
                require(tid not in owners,'duplicate_new_trial_identity')
                owners[tid]={'batch':name,'base':base,'identity':cell['identity'],'attempt':cell['attempt']}
        batches[name]={'base':base,'plan':plan,'cells':cells,'spec':spec}
    return batches,owners

def audit_ledger(batches,owners):
    path=BASE/'judges/request_ledger.jsonl';raw=path.read_bytes();rows=ledger_lines(raw)
    prior=ledger_lines((HIST/'judges/request_ledger.jsonl').read_bytes())
    require(len(prior)==136 and rows[:136]==prior,'immutable_136_ledger_prefix')
    require(all(r.get('event')=='request_started' for r in rows),'unexpected_ledger_event')
    require([r['package_request_index'] for r in rows]==list(range(1,len(rows)+1)),'ledger_indices_not_contiguous')
    require(len({r['request_id'] for r in rows})==len(rows)<=300,'duplicate_or_over_budget_requests')
    checks=[]
    for r in rows[136:]:
        tid=r['trial_id'];require(tid in owners,'unknown_post136_trial:'+tid);owner=owners[tid]
        require(r['attempt']==owner['attempt']==1 and r['model']==owner['identity']['judge'],'unplanned_retry_or_model')
        require(r['request_id']==digest({'trial_id':tid,'attempt':1}),'receipt_identity')
        p=owner['base']/'run/attempts'/f'{tid}_1/request_receipt.json'
        present=p.exists()
        if present:require(read(p)==r,'actual_receipt_ledger_mismatch')
        checks.append({'package_request_index':r['package_request_index'],'request_id':r['request_id'],'trial_id':tid,
                       'batch':owner['batch'],'receipt_present':present,'state':'receipt_bound' if present else 'started_pending_receipt'})
    return raw,rows,checks

def observe_batch(name,item,ledger):
    base=item['base'];index={r['request_id']:r for r in ledger};records=[]
    for cell in item['cells']:
        tid=cell['planned_trial_id'];p=base/'run/trials'/f'{tid}.json'
        if not p.exists():continue
        t=read(p);require(t['trial_id']==tid and t['identity']==cell['identity'],'trial_matrix_mismatch:'+name)
        receipt=read(base/'run/attempts'/f'{tid}_1/request_receipt.json')
        require(receipt==index.get(receipt['request_id']) and t['attempt']==1,'batch_receipt_unbound')
        require(t['actual_api_request_made'] and t['full_text_submitted_for_reextraction'],'observation_not_actual')
        require(sha(bind(base/'run/attempts'/f'{tid}_1/prompt.txt'))==t['prompt_sha256'],'transmitted_prompt_hash')
        records.append({'trial_id':tid,'status':t['status'],'judge':t['judge'],'repeat_index':t['repeat_index'],
                        'request_index':receipt['package_request_index'],'is_reused':cell.get('disposition')=='exact_prior_observation_reused'})
    summary_path=base/item['spec']['summary'];verify_path=base/item['spec']['verification']
    summary=read(summary_path) if summary_path.exists() else None
    verification=read(verify_path) if verify_path.exists() else None
    terminal=len(records)==item['spec']['n'];analyzed=terminal and summary is not None and verification is not None
    if analyzed:
        require(verification.get('status') in ['pass','complete_pass','verified'],'batch_analysis_not_pass:'+name)
        if name=='identity_stability_dev_v1':
            require(summary['actual_observations']==len(records) and summary['technical_successful_observations']==sum(r['status']=='success' for r in records)
                and summary['technical_failed_observations']==sum(r['status']=='failed' for r in records),'E4_summary_actual_count_mismatch')
        elif name=='controls_contract_v2':
            require(summary['actual_trial_count']==len(records) and summary['technical_successful_cases']==sum(r['status']=='success' for r in records),'E2_summary_actual_count_mismatch')
        else:require(summary['full_pipeline_successes']==sum(r['status']=='success' for r in records),'five_dev_summary_actual_count_mismatch')
    if terminal:state='complete_analyzed' if analyzed else 'runner_complete_analysis_pending'
    else:state='running' if any(not r['is_reused'] for r in records) else 'planned_pending_generation'
    data={'state':state,'planned_observations':item['spec']['n'],'actual_observations':len(records),
          'pipeline_successes':sum(r['status']=='success' for r in records),'failures_retained':sum(r['status']=='failed' for r in records),
          'planned_new_requests':item['spec']['new'],'new_requests_observed':sum(not r['is_reused'] for r in records),
          'reused_observations':sum(r['is_reused'] for r in records),'runner_terminal':terminal,'analysis_complete':analyzed,
          'source':relative(base,BASE),'summary_path':relative(summary_path,BASE) if summary else None,
          'verification_path':relative(verify_path,BASE) if verification else None,'summary':summary,
          'formal_eligible':False,'expert_confirmation':False,'records':records}
    if name=='identity_stability_dev_v1':
        reuse=read(base/'reuse_manifest.json');require(len(reuse)==5,'five_existing_observations_required')
        for x in reuse:require(sha(bind(x['copied_to']))==x['original_trial_sha256']==sha(bind(x['reused_from'])),'reuse_not_byte_exact')
        data['original_failed_repeat_zero_retained']=any(r['is_reused'] and r['status']=='failed' for r in records)
        require(data['original_failed_repeat_zero_retained'],'failed_repeat_zero_disappeared')
    return data

def main(publish=False):
    global INPUTS
    INPUTS={};out=BASE if publish else DRAFT;out.mkdir(parents=True,exist_ok=True)
    actual_command=[sys.executable,*sys.argv]
    actual_command_text=subprocess.list2cmdline(actual_command)
    snapshot=read(HIST/'snapshot_manifest.json')
    for r in snapshot['files']:require(sha(bind(HIST/r['relative_path']))==r['sha256'],'historical_snapshot_changed')
    inherited=read(HIST/'current_run_index.json')
    stable=[]
    for name,h in inherited['input_sha256'].items():
        if name=='judges/request_ledger.jsonl':continue
        require(sha(bind(BASE/name))==h,'unchanged_historical_source_drift:'+name);stable.append(name)
    batches,owners=known_batches();rawledger,ledger,ledgerchecks=audit_ledger(batches,owners)
    states={name:observe_batch(name,item,ledger) for name,item in batches.items()}
    if publish:
        require(all(s['analysis_complete'] for s in states.values()),'publish_requires_all_four_actual_analyses')
        require(len(ledger)==136+sum(x['new'] for x in BATCHES.values())==192,'publish_requires_complete_known_192_requests')
        require(all(r['receipt_present'] for r in ledgerchecks),'publish_requires_all_actual_receipts')
    n=len(ledger);utc=datetime.now(timezone.utc).isoformat()
    mainrun=read(BASE/'expanded_references_v7/run.json');oldrows=read(BASE/'expanded_references_v7_t070_per_answer.json')
    mf=read(BASE/'method_family_steps_v1/run.json');mfreview=read(BASE/'method_family_steps_v1/independent_review/review.json')
    require(mfreview['status']=='pass' and len(oldrows)==77 and sum(finite(r['sr']) for r in oldrows)==50,'historical_main_or_new_review')
    require(all(b['numeric_SR_SP']==66 and b['remaining_NA']==11 and b['new_numeric_from_v7_NA']==16 and b['multiple_candidate_answers']==27 for b in mf['batches']),'method_family_counts')
    for p,h in mf['output_sha256'].items():require(sha(bind(p))==h,'method_family_executed_output_changed')
    norm=read(BASE/'representation_normalization_v1/summary.json');normreview=read(BASE/'representation_normalization_v1/independent_review/review.json')
    require(normreview['status']=='pass' and norm['case_n']==21 and norm['unique_pairs']==15,'normalization_counts')
    for p,h in normreview['input_sha256'].items():require(sha(bind(p))==h,'normalization_review_input_drift')
    expert=read(BASE/'human_review/versioned_review_v1/preflight.json')
    require(expert['version_acknowledgements']==expert['reviewed_extraction_rows']==0,'new_expert_returns_require_updated_analysis')
    require(read(BASE/'human_review/versioned_review_v1/received_receipts.json')['records']==[],'new_version_receipts_require_updated_analysis')
    require(read(BASE/'human_review/expert_extraction_corrections.json')==[],'new_human_corrections_require_updated_analysis')
    require(sha(bind(BASE/'human_review/reviewer/review_items.csv'))==expert['review_input']['sha256'],'original_160_review_template_changed')
    literature=bind(STAGE/'PUBLISHED_METHODS_zh.md');visual=read(STAGE/'visual_review.json')
    for item in visual['items']:require(sha(bind(BASE/item['path']))==item['sha256'] and item['result']=='pass','visual_review_binding')
    for ext in ['png','svg','pdf','csv']:bind(BASE/f'figures_method_family_steps_v1/method_family_sr_matrix.{ext}')
    for p in ['judges/output_identity_v2/independent_review.json','judges/controls_contract_v2/eges_recomputation_verification.json',
              'judges/identity_stability_dev_v1/A04_repeat_trace.json']:
        if (BASE/p).exists():read(BASE/p)
    bind(BASE/'judges/identity_stability_dev_v1/A04_repeat_trace.md')
    e4_independent=BASE/'judges/identity_stability_dev_v1/analysis_independent_review.json'
    e4_independent_md=e4_independent.with_suffix('.md')
    e4_independent_ready=e4_independent.exists() and e4_independent_md.exists()
    if e4_independent_ready:
        require(read(e4_independent)['status']=='pass','E4_independent_review_not_pass');bind(e4_independent_md)
    if publish:require(e4_independent_ready,'publish_requires_final_E4_independent_recomputation')
    a01_paths=[BASE/'judges/identity_stability_dev_v1/A01_variation_trace.json',BASE/'judges/identity_stability_dev_v1/analysis/A01_variation_trace.json']
    a01_paths=[p for p in a01_paths if p.exists() and p.with_suffix('.md').exists()]
    require(len(a01_paths)<=1,'ambiguous_A01_trace_version')
    a01_trace=a01_paths[0] if a01_paths else None
    if a01_trace:read(a01_trace);bind(a01_trace.with_suffix('.md'))
    bind(BASE/'method_family_reference_seedb_v1/README.md')
    e2=states['controls_contract_v2'];e4=states['identity_stability_dev_v1'];control=None
    if e2['analysis_complete']:
        control=read(BASE/'judges/controls_contract_v2/control_summary.json')
        require(e2['summary']['technical_completed_pairs']==e2['summary']['complete_candidate_cce_pairs']==15,'E2_actual_pairs')
    lnk=lambda label,p:f'[{label}]({relative(BASE/p,out)})'
    nowlink=lambda label,p:f'[{label}]({p})'
    mf_link=lnk('逐答案 SR/SP、命中数与分母','method_family_steps_v1/t070_per_answer.csv')
    main_link=lnk('历史主 50/77','expanded_references_v7_t070_per_answer.csv')
    src_link=lnk('方法版本规则和完整候选','method_family_steps_v1/README.md')
    review_link=lnk('独立缓存复算','method_family_steps_v1/independent_review/review.md')
    lit_link=lnk('已发表文献对照','method_family_followup_v1/PUBLISHED_METHODS_zh.md')
    fig_link=lnk('SR 矩阵与分母','figures_method_family_steps_v1/method_family_sr_matrix.png')
    norm_link=lnk('分割诊断及其边界','representation_normalization_v1/independent_review/review.md')
    human_link=lnk('原版本绑定人工入口','human_review/CURRENT_REVIEW_ENTRY.md')
    e2_link=lnk('E2 配对明细','judges/controls_contract_v2/paired_results.csv') if control else lnk('E2 冻结计划','judges/controls_contract_v2/plan.json')
    e4_link=lnk('E4 终态分析','judges/identity_stability_dev_v1/analysis/completion_summary.json') if e4['analysis_complete'] else lnk('E4 冻结矩阵及复用','judges/identity_stability_dev_v1/plan.json')
    if control:
        ci={r['condition']:r for r in control}
        e2text=(f"E2 新配置对旧 21 份全文重新提取与评分，实际 {e2['pipeline_successes']}/21 技术及数值成功，形成 15/15 同配置配对；只来自 q2/q21/q22 三份源答案。必要步骤删除的 SR 仅 {ci['necessary_step_deletion']['negative_sr']}/3 下降；参数删除的 c_param {ci['necessary_parameter_deletion']['zero_c_param']}/3 不变；顺序冲突的 co_order {ci['evidence_supported_order_conflict']['negative_co_order']}/3 下降、Cor {ci['evidence_supported_order_conflict']['negative_Cor']}/3 下降。等价编号 SR/SP 均不变但 Cor {ci['deterministic_equivalent_representation']['negative_Cor']}/3 下降。相邻条目合并的 SR 下降/不变/上升分别为 {ci['adjacent_entry_merge']['negative_sr']}/{ci['adjacent_entry_merge']['zero_sr']}/{ci['adjacent_entry_merge']['positive_sr']}。这是原 core 的真实结果，不能用独立 normalizer 的零差替换。")
        e2_english_response=(f"Responses remained limited: SR decreased for {ci['necessary_step_deletion']['negative_sr']}/3 necessary-step deletions, c_param decreased for {ci['necessary_parameter_deletion']['negative_c_param']}/3 parameter deletions, and equivalent numbering reduced Cor in {ci['deterministic_equivalent_representation']['negative_Cor']}/3 pairs despite unchanged SR/SP.")
    else:e2text=f"E2 状态为 {e2['state']}，已见 {e2['actual_observations']}/21 真实终态记录；配对分析未完成，相关效果保持待定。"
    if not control:e2_english_response='Controlled-response estimates remain pending completed pair analysis.'
    e4text=(f"E4 固定五份开发答案 × 两评价器 × 三次观测，共 {e4['actual_observations']}/30 真实记录：{e4['pipeline_successes']} 技术成功、{e4['failures_retained']} 失败；{e4['reused_observations']} 条原 Qwen repeat 0 精确复用，本批新增 {e4['new_requests_observed']}/25。"+
            ("稳定性终态分析已完成，原始指标、派生指标和 NA 分母分别保留。" if e4['analysis_complete'] else "稳定性终态分析仍待定，不能从运行成功数推出一致性。")+
            "A04 原失败保留；个别后续重复通过严格格式，不能证明身份、目标关系或科学提取已修复。SR/SP 为复用确定性值，不能当作独立 judge 一致性证据。")
    stability_zh='稳定性统计未终态，数值待定。';stability_en='Stability estimates remain pending terminal analysis.'
    a01_text=''
    if e4['analysis_complete']:
        s=e4['summary'];cats={r['category']:r for r in s['categories']};direct=cats['direct_judge']
        require(s['within_groups']==160 and s['within_complete_three']+s['within_partial']+s['within_no_finite']==160 and s['between_groups']==80,'E4_group_denominators')
        require(s['tolerance']==1e-12 and s['no_best_repeat_selection'] and s['no_mixed_prompt_versions'],'E4_comparison_policy')
        for name in ['within.json','between.json','same_repeat_pairs.json','observations.json']:
            read(BASE/'judges/identity_stability_dev_v1/analysis'/name)
        if a01_trace:
            variations=[r for r in read(BASE/'judges/identity_stability_dev_v1/analysis/within.json') if r['nonzero_range']]
            require(len(variations)==6 and {r['anonymous_answer_id'] for r in variations}=={'A01'},'A01_variation_scope_changed')
            a01_text=('本批 6 个非零范围均来自 A01：同一全文的重复时长提取和一个直接评分发生变化，再经固定 EGES 与联合公式传递到派生指标；原函数身份重放一致。哪一个时长提取忠实仍待核查，不能择一当真。'+lnk('A01 上游变化与下游传播核查',relative(a01_trace.with_suffix('.md'),BASE))+'。')
        stability_zh=(f"五项直接评分的组内完整三重复为 {direct['within_complete_three']}/50 组，其中 {direct['within_complete_nonzero_range']} 组存在非零范围；另 {direct['within_partial']} 组仅一次有效，不把范围 NA 写成零。跨评价器 {direct['between_any_pair_different']}/{direct['between_any_pair_evaluable']} 个答案×直接指标组至少一次同 repeat 有差异；仅限双方三次均完整的组，均值差异为 {direct['between_complete_mean_different']}/{direct['between_both_complete_three']}。四项 EGES、两项确定性 SR/SP 和五项派生指标另列；合计 160 组内组有 {s['within_complete_three']} 完整、{s['within_partial']} 部分，非零范围 {s['within_nonzero_range']}/{s['within_range_evaluable']}。合计跨评价器任意有效配对差异 {s['between_any_pair_different']}/{s['between_any_pair_evaluable']} 组、同 repeat 实际指标对差异 {s['different_same_repeat_metric_pairs']}/{s['finite_same_repeat_metric_pairs']}、完整均值差异 {s['between_complete_mean_different']}/{s['between_both_complete_three']}。容差 1e-12。这些指标依赖同一批 5 答案，不能当成独立样本数。")
        stability_en=(f"For the five direct scores, {direct['within_complete_nonzero_range']}/{direct['within_complete_three']} complete three-repeat groups had nonzero range; {direct['within_partial']} additional groups contained only one valid observation and had NA range. Across judges, {direct['between_any_pair_different']}/{direct['between_any_pair_evaluable']} answer-by-direct-score groups differed in at least one matched repeat; complete three-repeat means differed in {direct['between_complete_mean_different']}/{direct['between_both_complete_three']} groups. Across all dependent metrics, {s['within_nonzero_range']}/{s['within_range_evaluable']} evaluable within-judge groups varied, and complete cross-judge means differed in {s['between_complete_mean_different']}/{s['between_both_complete_three']} groups (tolerance 1e-12). These groups are not independent answer samples.")
        e4text+=' A04 的 Qwen repeat 0/1 失败、repeat 2 结构通过；完整名称出现仍不确认其目标赋值。'
    technical_table='\n'.join(f"| {name} | {s['actual_observations']}/{s['planned_observations']} | {s['pipeline_successes']} | {s['failures_retained']} | {s['new_requests_observed']} | {s['state']} |" for name,s in states.items())
    zh=f'''# ClearEval r2 本轮结果（{'草稿' if not publish else '实际产物汇总'}）

历史主结果保留 **50/77**；本轮同方法完整作者候选的条件性敏感性分析为 **66/77**，新增 16 份数值、11 份仍 NA。固定 13 模型、6 题共有 77 份存档答案及 1 个缺失槽位，27 份实际比较两个版本。两类数值不可合并为“新主 gold”。{main_link}；{mf_link}；{fig_link}。

泛称方法仅在同方法、适用范围已明确标为条件性的完整作者版本间比较，先选整份 SR 最大，再按同份 SP、固定顺序打破平局；没有逐步拼接。显式不受支持版本保持 NA。SR 表示对当前候选的最好操作覆盖，不识别实际采用版本，也不证明样本/标记、存储目标或全任务科学适用性。11 NA 分为 1 路线未识别、1 显式版本不支持、9 缺完整相容候选。{src_link}。

三个阈值 0.6/0.7/0.8 均 66 数值；主阈值固定 0.7。全部 77 份原参数完整性、Correctness 和 EGES 保持，新 Com/IA/HV 只是更换步骤覆盖后的条件性敏感性计算，未按新参考重判原科学分项。独立复算 231 行旧 core 结果、297 次候选/控制评分，实际分母与同参考 SR/SP 均一致；无新 judge。固定模型共同题集仍仅 q2，三阈值前沿数 6/5/4，无新 bootstrap，不作全基准排名推断。{review_link}。

参考池与分割是不同诊断。此前跨路线无筛选 max 在 q2 将删除前后都选为 uDISCO 的 8/9，掩盖自身 FDISCO 的 6/7→5/7。本轮同方法三对控制均为 FDISCO 单候选，没有切换，不能当作多版本稳健性验证。独立词面归一化对 21 全文、15 原配对重算，3 个合并对的规范单位相同，SR/SP 差归零；原 segmenter 已选中操作流的非空白内容及顺序保持，但不证明原 segmenter 未漏内容或参数归属正确，也未改主算法或 E2 core。{norm_link}。

输出契约 v1 与完整名称提示 v2 各新增 5 次固定开发请求，均 4 成功/1 失败；A04 同值重复键仍被严格拒绝。v2 单次失败结果不被后续重复替换。两批均未达到原 5/5 推广门槛，未据此推广留出或更改专家建议版本；这些负结果与原数据全部保留。{lnk('两版本独立核验','judges/output_identity_v2/independent_review.md')}。

{e2text} {e2_link}。

{e4text} {e4_link}。

{stability_zh} {lnk('A04 原文与真实重复返回核查','judges/identity_stability_dev_v1/A04_repeat_trace.md')}。

{lnk('E4 独立逐槽与分母复算','judges/identity_stability_dev_v1/analysis_independent_review.md') if e4_independent_ready else 'E4 独立逐槽与分母复算尚待完成；当前不将其计为已验证。'}

{a01_text}

| 本轮批次 | 实际观测/预定 | 技术成功 | 失败保留 | 本批新增请求 | 状态 |
|---|---:|---:|---:|---:|---|
{technical_table}

截至本次账本快照共 **{n}/300** 次请求，剩 **{300-n}**；136 条历史前缀与本轮 {n-136} 条已知后缀均核验，复用不重复计请求。报告自身不产生模型请求。{nowlink('预算和回执审计','budget.json')}。

专家仍一位、固定 5 开发＋15 留出、原 160 行，真实回传 0；建议版本仍是原 5 开发及统一留出 v2（14 成功、A15 失败），不得用本轮结果悄悄替换。步骤与提取共用审阅；局部被审分母、完整参考建设和正式任务适用性分别记录。历史人工 s_method 0..5 与现 signed 量表映射仍无认证依据，不能平移；湿实验实际观测仍为 0，但不阻断可独立计算工作。{human_link}；{nowlink('剩余依赖','remaining_dependencies.json')}。

本轮文献对照区分既有研究方法、实际实现和待验证迁移；不能从多语种文献反推当前英文零 SR 的原因。{lit_link}。SeeDB2 正文与勘误已恢复，但完整切片流程不能直接作为未切片 3 mm 脑块的参考；这是来源进展，未新增数值。{lnk('SeeDB2 适用范围缺口','method_family_reference_seedb_v1/README.md')}。
'''
    en=f'''# Supplementary Methods and Results: versioned development follow-up

The historical primary table remains 50/77 numerically complete CCE observations. A separate conditional same-method analysis covers 66/77 archived answers from 13 generators and six development tasks, adding 16 numerical values and retaining 11 NA values. Twenty-seven answers have two complete author-version candidates. Generic method declarations maximize whole-reference SR, then the same reference's SP and frozen order; unsupported explicit versions remain NA. This estimates best available procedural coverage, not protocol identity or expert-confirmed task applicability. {lnk('Source policy and all candidates','method_family_steps_v1/README.md')}

The original segmenter, all-mpnet-base-v2 encoder and thresholds 0.6/0.7/0.8 (primary 0.7) are unchanged. Archived parameter completeness, correctness and EGES remain unchanged for all 77 answers. Com = 0.4 SR + 0.6 c_param/3; IA and HV are calculated per answer, with NA propagated. The resulting CCE values combine changed step coverage with unrejudged archived scientific components and are conditional sensitivity results. Independent cache replay reproduced 231 old rows and 297 whole-candidate/control scores. The common set remains q2 alone; Pareto counts are 6/5/4, with no new bootstrap draws or broad ranking claim. {lnk('Independent numerical review','method_family_steps_v1/independent_review/review.json')}

A separate lexical normalization probe reparsed 21 exposed control texts forming 15 original pairs. All three adjacent-entry merge pairs recovered identical normalized units and zero SR/SP differences. Preservation is limited to the operation stream selected by the original segmenter; this does not certify completeness or semantic parameter attachment. The probe did not replace the primary or E2 segmenter. The three same-method deletion controls have only one candidate each, so absence of reference switching does not validate multiversion robustness. {lnk('Normalization review','representation_normalization_v1/independent_review/review.md')}

Two fixed-five prompt-contract batches each produced four strict pipeline successes and one duplicate-key failure. The failed five-of-five gate remains failed. A later repeated structural success does not establish corrected marker identity or target relationships; no output was silently repaired or selected by score. These exposed-development experiments do not alter the human suggestion package. {lnk('Two-batch independent review','judges/output_identity_v2/independent_review.json')}

The new E2 batch has {e2['actual_observations']}/21 actual observations, {e2['pipeline_successes']} pipeline successes and {e2['failures_retained']} retained failures; analysis state is {e2['state']}. The 15 planned pairs originate from only three answers. Original full texts, references and frozen identity-v2 prompt are used for both arms, with fresh extraction and no historical-baseline substitution. {e2_english_response} {e2_link}

E4 has {e4['actual_observations']}/30 observations, {e4['pipeline_successes']} successes and {e4['failures_retained']} failures; analysis state is {e4['state']}. The fixed five answers, two evaluators and three repeats retain the failed A04 observation. Five original Qwen repeat-zero records are reused with exact trial/receipt/prompt provenance; {e4['new_requests_observed']}/25 new calls are recorded. Failures remain NA. Five direct scores, four computed EGES components and five aggregates must be distinguished; deterministic reused SR/SP are not independent judge-agreement evidence. {e4_link}

{stability_en}

{lnk('Independent E4 slot and denominator replay','judges/identity_stability_dev_v1/analysis_independent_review.md') if e4_independent_ready else 'Independent E4 slot and denominator replay is pending.'} {lnk('Actual A04 repeat trace','judges/identity_stability_dev_v1/A04_repeat_trace.md')}

The one-expert five-development/fifteen-holdout review has zero real returns. The existing version-bound package, nineteen automatic inputs, A15 gap and original 160-item template remain unchanged. Historical scale mapping is unresolved. Wet-lab plans and analysis entry points are available, but no real biological observations are claimed. SeeDB2's primary paper and correction were recovered, but the complete slice workflow cannot directly support an unsectioned 3-mm block reference; no numerical coverage was added. The report records {n}/300 actual requests and validates the unchanged 136-request prefix plus known new receipts. {human_link} {lit_link}
'''
    abstract=f'''# Draft abstract: bounded supplementary evidence

We added source-bound Step Recall (SR) and Step Precision (SP) while preserving archived parameter completeness, correctness and EGES. In a separate same-method sensitivity analysis of 77 answers from 13 generators and six development tasks, complete conditional author references produced 66 numerical results, compared with 50 in the unchanged historical primary table; 27 answers had two version candidates. Explicit unsupported versions remained NA. Independent cache replay verified selection, denominators and CCE arithmetic. Lexical normalization removed merge-induced SR/SP differences in three reused development pairs, without establishing semantic extraction accuracy. Two five-answer output-contract interventions each retained one strict duplicate-key failure. Fresh E2 controls yielded {e2['pipeline_successes']}/{e2['planned_observations']} technical successes, while E4 has {e4['pipeline_successes']}/{e4['actual_observations']} successful observations and {e4['failures_retained']} retained failures. Controlled responses and cross-judge agreement remained limited; scientific repair is not inferred from format success. The fixed-model common set remains one task, expert review is pending, and no wet-lab effects are claimed. These results identify conditional coverage gains and unresolved evaluator sensitivity rather than validated full-benchmark rankings.
'''
    status=f'''# ClearEval r2 当前状态（{'报告草稿' if not publish else '已核产物'}）

当前账本快照 **{n}/300**，剩 **{300-n}**。历史主表 50/77 保留；同方法条件敏感性 66/77、11 NA、16 新增、27 双版本。正式科学确认仍 0。

词面诊断完成 21 全文/15 原配对；三个合并对差归零，只适用于独立归一化条件。输出契约与名称规则两批仍各 4/5，不宣称修复。

E2：{e2['state']}，{e2['actual_observations']}/21 真实观测、{e2['pipeline_successes']} 成功。E4：{e4['state']}，{e4['actual_observations']}/30 真实观测、{e4['pipeline_successes']} 成功、{e4['failures_retained']} 失败；5 旧观测精确复用。

从[当前结果索引](CURRENT_RESULTS_INDEX.md)、[结果](RESULTS_zh.md)、[实际命令](commands.md)继续。专家 5＋15 原包不改；旧量表、适用性与真实湿数据依赖见[清单](remaining_dependencies.json)。未回传不填 0。总体目标仍未宣称完成。
'''
    for name,text in [('RESULTS_zh.md',zh),('Methods_Results_en.md',en),('Abstract_en.md',abstract),('STATUS.md',status)]:write(out/name,text)
    actualcommands=[]
    for name in BATCHES:
        p=BASE/'judges'/name/'actual_execution_commands.json'
        if p.exists():actualcommands.append({'batch':name,'path':str(p),'records':read(p)})
    for p in [BASE/'method_family_steps_v1/execution_commands.json',BASE/'representation_normalization_v1/execution.json']:
        if p.exists():actualcommands.append({'batch':p.parent.name,'path':str(p),'records':read(p)})
    for p in [BASE/'judges/identity_stability_dev_v1/analysis/actual_execution.json',BASE/'judges/identity_stability_dev_v1/analysis/actual_execution_commands.json']:
        if p.exists():actualcommands.append({'batch':'E4 analysis','path':str(p),'records':read(p)})
    commandlinks='\n'.join('- '+lnk(x['batch'],relative(x['path'],BASE)) for x in actualcommands)
    write(out/'commands.md',f'''# 实际执行与可复现入口

工作目录 `C:/ClearEval/ClearEval-public`，Python 为 `C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe`。

以下链接是实际命令日志；计划中的命令不能据此视为已经运行。

{commandlinks}

本报告实际调用：`{actual_command_text}`；本次 publish=`{str(publish).lower()}`。默认只生成 `method_family_followup_v1/report_draft/`；显式发布要求全部真实批次终态分析、E4 独立核验及已知 192 条账本通过后才写 canonical。不调用模型，不重算科学分数。

独立重现入口：`python scripts/cce_report_method_family_v1.py`（草稿）；发布入口可用 `python scripts/cce_report_method_family_v1.py --publish` 或经已更新 dispatcher 调用 `main(publish=True)`。这行是重现说明，不冒充本次实际命令。
''')
    remaining=read(HIST/'remaining_dependencies.json')
    remaining.update(report_stage=VERSION,expert_review='One expert; unchanged five-development/fifteen-holdout selection and version-bound package; zero actual returns.',
        historical_main={'numeric':50,'NA':27,'stage':'expanded_references_v7','unchanged':True},
        same_method_conditional={'numeric':66,'NA':11,'new_numeric':16,'two_version_answers':27,'formal_eligible':0,'scientific_components_rejudged':False},
        next_independent_work=('All frozen development batches and their E2/E4 analyses are complete. Next work requires actual version-bound expert returns or specific missing source/applicability/legacy-scale evidence; no further prompt tuning or automatic holdout promotion.' if all(s['analysis_complete'] for s in states.values()) else 'Complete the explicitly pending E2/E4 analysis; real version-bound expert returns and specific source/applicability/legacy-scale evidence remain separate dependencies.'),
        current_E2_state=e2['state'],current_E4_state=e4['state'],
        evaluator_validity='Technical success does not establish extraction fidelity. Fixed-five gates remain 4/5; controlled sensitivity and repeated failures are reported independently.',
        segmentation_boundary='Normalization only preserves the original segmenter-selected operation stream in exposed development controls; core and heldout parsing unchanged.',
        method_version_boundary='Generic-method maxSR is conditional coverage, not protocol-version identification; 3 deletion controls have one candidate each.',
        main_scientific_results_replaced=False,expert_suggestion_version_replaced=False,wetlab_is_computational_blocker=False)
    save(out/'remaining_dependencies.json',remaining)
    budget=read(HIST/'budget.json');budget.update(attempts_recorded=n,remaining_request_capacity=300-n,
        model_attempts=dict(Counter(r['model'] for r in ledger)),ledger_sha256=rawsha(rawledger),ledger_snapshot_time_utc=utc,
        historical_prefix_requests=136,new_requests_since_snapshot=n-136,
        ledger_prefix_and_known_suffix_verified=True,reused_observations_count_as_new_requests=False,
        report_new_requests=0,batch_progress={k:{x:s[x] for x in ['state','actual_observations','new_requests_observed','reused_observations']} for k,s in states.items()})
    save(out/'budget.json',budget);(out/'ledger_snapshot.jsonl').write_bytes(rawledger)
    save(out/'ledger_audit.json',{'status':'pass','snapshot_sha256':rawsha(rawledger),'prefix_requests':136,'suffix_requests':n-136,'suffix_checks':ledgerchecks,'read_at_utc':utc})
    index=copy.deepcopy(inherited)
    index.update(version=VERSION,report_stage=VERSION,artifact_base=str(BASE),report_directory=str(out),draft=not publish,
        previous_report_index='historical_reports/before_method_family_at_136/current_run_index.json',
        main_scoring_stage='expanded_references_v7',primary='expanded_references_v7_t070_per_answer.json',
        historical_main_result_preserved=True,request_attempts=n,new_model_requests=n-136,
        conditional_method_family={'primary':'method_family_steps_v1/t070_per_answer.json','run':'method_family_steps_v1/run.json',
            'reference':'method_family_steps_v1/references.json','policy':'method_family_steps_v1/policy.json',
            'independent_review':'method_family_steps_v1/independent_review/review.json','numeric':66,'NA':11,'new_numeric':16,'two_versions':27,'formal_eligible':False},
        representation_normalization={'summary':'representation_normalization_v1/summary.json','independent_review':'representation_normalization_v1/independent_review/review.json','main_parser_replaced':False},
        prompt_diagnostic_batches=states,published_methods='method_family_followup_v1/PUBLISHED_METHODS_zh.md',
        new_SR_figure='figures_method_family_steps_v1/method_family_sr_matrix.png',visual_review='method_family_followup_v1/visual_review.json',
        E4_A04_repeat_trace={'json':'judges/identity_stability_dev_v1/A04_repeat_trace.json','markdown':'judges/identity_stability_dev_v1/A04_repeat_trace.md'},
        E4_independent_recomputation={'ready':e4_independent_ready,'json':relative(e4_independent,BASE) if e4_independent_ready else None,'markdown':relative(e4_independent_md,BASE) if e4_independent_ready else None},
        E4_A01_upstream_variation={'ready':a01_trace is not None,'json':relative(a01_trace,BASE) if a01_trace else None,'markdown':relative(a01_trace.with_suffix('.md'),BASE) if a01_trace else None},
        report_input_binding_policy='Historical immutable inputs checked except live ledger; current ledger snapshot verifies the old 136-prefix and actual known suffix. No historical hash is required for mutable current reports.',
        input_sha256=dict(INPUTS))
    save(out/'current_run_index.json',index)
    cfg=read(HIST/'resolved_config_current.yaml')
    cfg.update(version=VERSION,previous_configuration_snapshot='historical_reports/before_method_family_at_136/resolved_config_current.yaml',
        current_execution={'historical_primary':index['primary'],'conditional_primary':'method_family_steps_v1/t070_per_answer.json','package_requests':n},
        method_family_conditional_configuration=read(BASE/'method_family_steps_v1/t070_resolved_config.json'),
        original_main_composition_preserved=True,representation_normalization_primary_algorithm_changed=False,
        identity_development_followup={k:{'plan':f'judges/{k}/plan.json','state':s['state'],'expert_suggestion_replaced':False} for k,s in states.items()})
    save(out/'resolved_config_current.yaml',cfg)
    audit=read(HIST/'completion_audit_current.json');audit.update(report_stage=VERSION,package_requests=n,
        overall_goal_complete=False,conditional_method_numeric=66,historical_main_numeric=50,
        new_batches={k:s['state'] for k,s in states.items()},new_expert_returns=0,new_model_requests_this_phase=n-136,
        remaining_computational_analysis=[k for k,s in states.items() if not s['analysis_complete']],
        no_formal_scientific_gold_claim=True,wetlab_is_computational_blocker=False)
    audit['items'].extend([
        {'goal':'Same-method complete author versions','state':'conditional_sensitivity_computed_not_primary_replacement','counts':'66/77 numeric;16 added;27 two-version answers;11 NA','evidence':'method_family_steps_v1/run.json'},
        {'goal':'Representation normalization development probe','state':'completed_on_21_texts_15_reused_pairs_not_primary_parser','evidence':'representation_normalization_v1/independent_review/review.json'},
        {'goal':'Frozen identity_v2 E2 fresh full-text assessment','state':e2['state'],'evidence':'judges/controls_contract_v2/development_summary.json'},
        {'goal':'Fixed-five two-judge repeated development diagnostic','state':e4['state'],'evidence':'judges/identity_stability_dev_v1/analysis/completion_summary.json'}])
    save(out/'completion_audit_current.json',audit)
    save(out/'current_activity.json',{'status':'completed_frozen_development_followup_scientific_dependencies_pending' if all(s['analysis_complete'] for s in states.values()) else 'development_results_partially_analyzed',
        'stage':VERSION,'requests':n,'overall_goal_complete':False,'new_report_model_requests':0,'draft':not publish})
    write(out/'CURRENT_RESULTS_INDEX.md',f'''# 当前结果索引

本索引生成于 {utc}，请求快照 {n}/300。{'这是独立草稿，未改 canonical。' if not publish else '这是本轮已核产物汇总。'}

- [中文结果](RESULTS_zh.md)、[英文 Methods/Results](Methods_Results_en.md)、[摘要草稿](Abstract_en.md)。
- {main_link}；{mf_link}；{src_link}；{fig_link}；{review_link}。
- {norm_link}；{e2_link}；{e4_link}。
- {lit_link}；{human_link}。
- [预算](budget.json)、[账本前缀/后缀核验](ledger_audit.json)、[配置](resolved_config_current.yaml)、[机器索引](current_run_index.json)、[剩余依赖](remaining_dependencies.json)、[报告核验](report_verification_method_family_v1.json)。

历史主与条件性敏感性分表；正式科学确认 0，专家回传 0。不混用不同提示版本，不从重复中择优。
''')
    # This verification file is referenced by the index but excluded from its own hash map.
    save(out/'report_verification_method_family_v1.json',{'status':'being_finalized'})
    outputs=[out/name for name in ['RESULTS_zh.md','Methods_Results_en.md','Abstract_en.md','STATUS.md','commands.md','CURRENT_RESULTS_INDEX.md',
        'current_run_index.json','resolved_config_current.yaml','remaining_dependencies.json','completion_audit_current.json','budget.json','current_activity.json','ledger_snapshot.jsonl','ledger_audit.json']]
    links=[]
    for p in outputs:
        if p.suffix!='.md':continue
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf8')):
            if '://' in link or link.startswith('#'):continue
            target=(p.parent/link.split('#')[0]).resolve();require(target.exists(),'broken_generated_local_link:'+str(target))
            links.append({'document':p.name,'link':link})
    require(all(sha(p)==h for p,h in INPUTS.items()),'bound_report_input_changed_during_assembly')
    # Bind generator and publish/draft mode; verify no hidden model/score execution occurs.
    verification={'status':'pass','draft':not publish,'publish':publish,'actual_command':actual_command,
        'generator_sha256':sha(__file__),'created_utc':utc,'package_requests_snapshot':n,'historical_main_numeric':50,'conditional_numeric':66,
        'fixed13_common_question_ids':[2],'new_report_model_requests':0,'new_report_embeddings':0,'scientific_scores_recomputed':False,
        'snapshot_136_files_verified':len(snapshot['files']),'historical_unchanged_inputs_verified':len(stable),'actual_local_links_checked':len(links),
        'all_four_batch_analysis_complete':all(s['analysis_complete'] for s in states.values()),'expert_packet_unchanged':True,
        'input_sha256':INPUTS,'output_sha256':{p.name:sha(p) for p in outputs},'local_links':links}
    save(out/'report_verification_method_family_v1.json',verification);save(out/'report_generation.json',verification)
    if publish:write(ROOT.parent/'STATUS.md','# ClearEval 当前状态\n\n最新入口：[本轮结果索引](ClearEval-public/artifacts/cce_validation/CURRENT_RESULTS_INDEX.md)。\n\n'+f'实际请求 {n}/300；历史主 50/77 与条件敏感性 66/77 分列。专家和科学适用性仍待定。')
    print(json.dumps({'status':'pass','draft':not publish,'out':str(out),'requests':n,'historical_main':50,'conditional':66,'links':len(links),'batch_states':{k:s['state'] for k,s in states.items()}},ensure_ascii=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true');options=parser.parse_args();main(publish=options.publish)
