"""Immutable completed v6/v7 development comparison; zero model calls."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'grounded_v7_stage_report_v1';LEDGER=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
METRICS=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time']
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def require(v,s):
    if not v:raise ValueError(s)
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def state(v):return 'NA' if not finite(v) else 'zero' if v==0 else 'nonzero'
def metric_summary(rows):
    return {k:{**dict(Counter(state(r['component_gated_proposals'].get(k)) for r in rows)),
        'numeric':sum(finite(r['component_gated_proposals'].get(k)) for r in rows),'denominator':len(rows)} for k in METRICS+['Eff']}
def gate():
    paths=[BASE/'grounded_development_v7/completion_summary.json',BASE/'grounded_development_v7/independent_fact_audit_v7/summary.json',BASE/'grounded_v7_failure_diagnostics_v1/summary_5of5.json']
    require(all(p.exists() for p in paths),'WAIT_FOR_ALL_FIVE_TERMINAL_ANALYSIS_FACTS_AND_SOURCE_DIAGNOSIS')
    s,f,d=map(read,paths)
    require(s['actual_observations']==f['fixed_answers']==d['fixed_answers']==5 and f['status']=='complete' and d['status']=='complete_five_terminal_source_diagnostics','CURRENT_FIVE_INCOMPLETE')
def self_check():
    rows=[{'component_gated_proposals':{k:v for k in METRICS+['Eff']}} for v in [0,None,2,False,0.0]]
    m=metric_summary(rows)
    require(all(v=={'zero':2,'NA':2,'nonzero':1,'numeric':3,'denominator':5} for v in m.values()),'KNOWN_ZERO_NA_DENOMINATOR_CHECK')
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/'software_checks.json';require(not p.exists(),'SOFTWARE_CHECK_ALREADY_RECORDED')
    p.write_text(json.dumps({'status':'pass','synthetic_checks':1,'actual_outputs_read':False,'new_model_calls':0,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]},indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'synthetic_metric_accounting_pass','actual_outputs_read':False,'new_model_calls':0}))
def main():
    gate();require(not (OUT/'comparison.json').exists(),'CURRENT_REPORT_IMMUTABLE_USE_NEW_VERSION')
    before=LEDGER.read_bytes();ledger={r['request_id']:r for r in map(json.loads,before.decode('utf8').splitlines())}
    inputs=[Path(__file__)];versions=[];first_cases=first_contract=None;flat=[]
    for version in ['v6','v7']:
        folder=BASE/('grounded_development_'+version)
        paths=[folder/n for n in ['completion_summary.json','per_answer.json','cases.json','matrix.json','expected_contract.json']]+[folder/('independent_fact_audit_'+version)/n for n in ['summary.json','per_answer.json']]
        summary,rows,cases,matrix,contract,facts,factrows=map(read,paths)
        require(summary['actual_observations']==facts['fixed_answers']==len(rows)==len(matrix)==len(factrows)==5,'FIXED_FIVE_CHANGED')
        require(facts['status']=='complete','FACT_AUDIT_INCOMPLETE')
        require([facts[k] for k in ['explicit_names_denominator','core_duration_denominator','explicit_relation_denominator','ambiguity_group_denominator']]==[16,31,3,2],'FIXED_FACT_DENOMINATOR_CHANGED')
        if first_cases is None:first_cases,first_contract=cases,contract
        else:
            require(cases==first_cases,'FULL_INPUT_CASES_CHANGED')
            require(all(contract[k]==first_contract[k] for k in ['files','demands','scoring_version','source_registry_sha256']),'ORIGINAL_SCIENTIFIC_CONTRACT_CHANGED')
            require(contract['models'][0]['name']==first_contract['models'][0]['name'],'MODEL_CHANGED')
            require({k:v for k,v in contract['models'][0]['settings'].items() if k!='format'}=={k:v for k,v in first_contract['models'][0]['settings'].items() if k!='format'},'NON_SCHEMA_GENERATION_SETTINGS_CHANGED')
        for b in summary['bound_observations']+facts['inputs']:
            require(sha(b['path'])==b['sha256'],'ACTUAL_RESULT_BINDING_CHANGED:'+b['path']);inputs.append(Path(b['path']))
        keyed={r['trial_id']:r for r in rows};require(len(keyed)==5,'DUPLICATE_TRIAL');terminals=[]
        for cell in matrix:
            tid=cell['planned_trial_id'];row=keyed[tid];tp=folder/'run/trials'/f'{tid}.json';rp=folder/'run/attempts'/f'{tid}_1/request_receipt.json';trial,receipt=read(tp),read(rp)
            require(trial['identity']==cell['identity'] and trial['trial_id']==tid and trial['status']==row['status'] and trial['status'] in ['success','failed'] and trial['attempt']==1,'TRIAL_IDENTITY_OR_STATUS_CHANGED')
            require(receipt==ledger[receipt['request_id']] and receipt['trial_id']==tid and receipt['attempt']==1 and receipt['package_request_index']==row['request_index'],'REQUEST_RECEIPT_CHANGED')
            values=row['component_gated_proposals'];require(row['numeric_component_count']==sum(finite(values[k]) for k in METRICS),'NUMERIC_COUNT_MISMATCH')
            if trial['status']=='failed':require(all(values[k] is None for k in METRICS),'FAILED_TRIAL_NUMERIC_LEAK')
            terminals.append({'answer':row['anonymous_answer_id'],'request_index':row['request_index'],'trial_id':tid,'status':row['status'],'failure_stage':row['failure_stage'],'conversion_errors':row['grounded_conversion_errors'],
                'numeric_components':row['numeric_component_count'],'complete_numeric':row['complete_numeric_after_component_gates'],'component_values':values,'component_states':{k:state(values.get(k)) for k in METRICS+['Eff']},
                'gate_notes':row['component_gate_notes'],'evidence_state':row['evidence_state'],'zero_is_mathematical_output_not_source_validity_proof':True})
            for metric in METRICS+['Eff']:flat.append({'version':version,'answer':row['anonymous_answer_id'],'request_index':row['request_index'],'status':row['status'],'metric':metric,'value':values.get(metric),'state':state(values.get(metric))})
            inputs.extend([tp,rp])
        metrics=metric_summary(rows)
        require(all(metrics[k]['numeric']==summary['per_component_numeric'][k] for k in METRICS),'COMPONENT_COVERAGE_MISMATCH')
        require(sum(r['status']=='success' for r in rows)==summary['technical_successes'],'TECHNICAL_COUNT_MISMATCH')
        versions.append({'version':version,'technical_successes':summary['technical_successes'],'technical_failures':summary['technical_failures'],'complete_numeric':summary['complete_numeric_after_component_gates'],'all_five_denominator':5,
            'names_exact':facts['name_states'].get('exact',0),'name_states':facts['name_states'],'duration_literal_retained':facts['literal_numeric_components_retained'],'duration_record_bound_retained':facts['record_bound_numeric_components_retained'],
            'duration_initial_scope_retained':facts['core_initial_scope_retained'],'duration_states':facts['core_duration_states'],'legacy_duration_diagnostics_not_primary':facts['legacy_only'],
            'relation_edges_retained':facts['exact_endpoint_edges_retained'],'relation_projection_retained':facts['exact_relation_projections_retained'],'ambiguity_states':facts['ambiguity_states'],'ambiguity_retained':facts['ambiguity_states'].get('explicit_ambiguity_retained',0),
            'raw_name_presence_separate':facts['raw_name_presence_separate'],'intrinsic_audit_separate':facts['intrinsic_identity_separate_from_fixed_relation_inventory'],
            'primary_time_NA_despite_all_inventory_numeric_components_retained':facts['answers_primary_NA_despite_all_inventory_numeric_components_retained'],
            'per_component_numeric_zero_NA':metrics,'num_ctx':contract['models'][0]['settings']['num_ctx'],'terminal_observations':terminals})
        inputs.extend(paths)
        for name in ['actual_commands.json','analysis_verification.json']:
            if (folder/name).exists():inputs.append(folder/name)
    diagnosis_path=BASE/'grounded_v7_failure_diagnostics_v1/summary_5of5.json';diagnosis=read(diagnosis_path)
    require(diagnosis['technical_successes']==versions[-1]['technical_successes'],'SOURCE_DIAGNOSTIC_COUNTS_DIFFER')
    for b in diagnosis['traces']:require(sha(b['path'])==b['sha256'],'SOURCE_TRACE_CHANGED');inputs.append(Path(b['path']))
    budget_path=BASE/'grounded_v7_design_v1/budget_allocation_amendment.json';budget=read(budget_path)
    require((budget['previous_development_total'],budget['development_total'],budget['v7_new_requests'],budget['global_limit'])==(35,40,5,300),'PROSPECTIVE_BUDGET_AMENDMENT_CHANGED')
    inputs.extend([diagnosis_path,budget_path,BASE/'grounded_v7_design_v1/root_decision.json',BASE/'fact_audit_checker_v7/freeze.json',BASE/'fact_audit_checker_v7/software_probes.json',BASE/'confirmation_reference_design_v1/revision_02/integrity_amendment.json',BASE/'root_search_scope_audit_20261010.md'])
    require(LEDGER.read_bytes().startswith(before),'LEDGER_PREFIX_CHANGED')
    current=versions[-1];t01=current['technical_successes']==5
    result={'status':'completed_same_five_development_comparison_not_scientific_validation','versions':versions,'T01_v7':'pass' if t01 else 'fail',
       'fixed_fact_denominators':{'names':16,'initial_duration_components':31,'explicit_dye_target_pairs':3,'ambiguities':2},
       'same_five_full_inputs':True,'same_model_and_settings_except_decoder_schema':True,'single_factor_ablation':False,'mathematical_zero_is_not_proof_of_faithful_source_input':True,
       'bundle_changes':['existing O source extents expose eligible D/P identifiers from unchanged v6 binding guards','generic prompt clarification of explicit chosen method, untimed-operation retention, and separate whole/core coverage'],
       'unchanged':['original direct-score rubric, Correctness and parameter-completeness scales','original EGES implementation, demands and knowledge base','original arithmetic, native-policy, operation/repeat binding and coverage functions','context98304,temperature0,output8192 and model','fixed 16/31/3/2 inventory'],
       'source_diagnosis':bind(diagnosis_path),'original_development_budget_deviation':'25 -> 30 for v5 -> 35 for v6 -> 40 for v7; dated before each batch, global ceiling300 unchanged','budget_amendment':bind(budget_path),'optional_blind_disabled_before_confirmation':budget['optional_blind_execution_allowed'] is False,'budget_allocated_maximum':budget['max_total_if_all_phases_run'],'unallocated_calls_do_not_authorize_retries':not budget['unallocated_calls_authorize_retries'],
       'new_model_requests_for_this_report':0,'new_expert_labels':0,'scientific_acceptance_established':False,'full_goal_complete':False,
       'inputs':[bind(p) for p in dict.fromkeys(inputs)],'actual_command':[sys.executable,*sys.argv],'script_sha256':sha(__file__)}
    lines=['# v7 真实开发比较','',f"同五份答案均已终态：v7 技术成功 {current['technical_successes']}/5，失败 {current['technical_failures']}/5；完整九项数值 {current['complete_numeric']}/5。T01 {'通过' if t01 else '未通过'}。此结果不证明科学准确性。",'',
      '| 同五份开发答案 | v6 | v7 |','|---|---:|---:|']
    table=[('技术成功','technical_successes',5),('完整九项数值','complete_numeric',5),('有效转换中的精确名称','names_exact',16),('有效转换中的时间原值','duration_literal_retained',31),('时间原值与操作绑定','duration_record_bound_retained',31),('初始范围声明保留','duration_initial_scope_retained',31),('明确关系原端点保留','relation_edges_retained',3),('明确关系投影保留','relation_projection_retained',3),('明确歧义保留','ambiguity_retained',2)]
    for label,key,den in table:lines.append(f"| {label} | {versions[0][key]}/{den} | {current[key]}/{den} |")
    lines.extend(['','对论文的意义：这组结果检验同一批明确事实能否在来源引用、转换和评分之间保留下来。失败不从分母中剔除；原始返回里出现名称或数值，不计作失败转换后的有效事实保留。主时间为 NA 时，仍单独报告已经保留的初始分量。','','| 分项 | v6 数值 / 5 | v6 零 / NA | v7 数值 / 5 | v7 零 / NA |','|---|---:|---:|---:|---:|'])
    for k in METRICS+['Eff']:
        a,b=[v['per_component_numeric_zero_NA'][k] for v in versions];lines.append(f"| {k} | {a['numeric']}/5 | {a.get('zero',0)} / {a.get('NA',0)} | {b['numeric']}/5 | {b.get('zero',0)} / {b.get('NA',0)} |")
    lines.extend(['','零是原函数在实际输入上的数学输出，不能单凭零声称输入忠实或任务满足；NA、合法未知、技术失败及明确事实丢失分别保留。旧 v1 的短引文包含判据只放在 legacy_only，不能用它误称已经按原值、操作记录绑定保留的时间丢失。','','| 答案 | v7 请求 | 技术状态 | 数值分项 / 9 | 首个失败阶段 |','|---|---:|---|---:|---|'])
    for r in current['terminal_observations']:lines.append(f"| {r['answer']} | {r['request_index']} | {r['status']} | {r['numeric_components']} | {r['failure_stage'] or '无技术失败'} |")
    lines.extend(['','v6 与 v7 使用相同五份全文、参考、模型及生成参数（上下文 98304、输出 8192、温度 0）。v7 在既有 O 元数据中展示原绑定规则允许的 D/P ID，并澄清直接选择方法、保留未定时长操作、分别声明 whole/core 覆盖。原 O/P 来源边界、重复遗漏门、月份不支持、算术、原生标记政策及覆盖函数均未变，也不自动修复返回。这是元数据与提示的组合改动，不能把结果归于单个原因。原量表、EGES、知识库和需求保持不变。','','开发预算在生成前从 35 增至 40；最初 25 次条款的连续偏离完整披露，全包上限仍为 300。当前分配总上限 294，6 次未分配额度不授权重试；可选盲化代理评测在确认集解封前已禁用，不能依据确认结果重启。这里反复使用的五份开发答案不能证明独立泛化，专家状态仍为 0。原摘要间接哈希缺口和检索范围事件见既有完整性记录，未在本报告中抹除。','',
      '[逐答案真实结果](../grounded_development_v7/per_answer.json) · [冻结事实核查](../grounded_development_v7/independent_fact_audit_v7/summary.json) · [五份来源诊断](../grounded_v7_failure_diagnostics_v1/README.md) · [完整数字与来源](comparison.json) · [分项 CSV](component_states.csv)',''])
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'comparison.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    (OUT/'RESULTS_zh.md').write_text('\n'.join(lines),encoding='utf8')
    with (OUT/'component_states.csv').open('x',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    print(json.dumps({'status':result['status'],'T01_v7':result['T01_v7'],'technical_successes':current['technical_successes'],'complete_numeric':current['complete_numeric'],'new_model_calls':0}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--self-check',action='store_true');p.add_argument('--analyze-completed',action='store_true');a=p.parse_args();require(a.self_check!=a.analyze_completed,'CHOOSE_ONE_ACTION');self_check() if a.self_check else main()
