"""Independent offline E4 numeric/denominator review from original trial records.

Does not import the terminal analyzer or read held-out scientific records. Uses
the frozen five-answer step evidence, original raw trial score blocks, and an
independent implementation of aggregation/dispersion/paired comparison rules.
"""
from __future__ import annotations
from collections import Counter
import json
import math
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_output_contract_v1 as parent

BATCH=ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1'
ANALYSIS=BATCH/'analysis'
TOL=1e-12
GROUPS={'direct_judge':['c_param','co_order','co_method','co_param','co_chem'],
        'computed_EGES':['s_method','s_label','s_trans','s_time'],
        'deterministic_steps':['sr','sp'],'derived':['Com','Cor','Eff','IA','HV']}
METRICS=sum(GROUPS.values(),[])
MODELS=['local_qwen3_8b','local_llama3_8b']
IDS=['A01','A02','A03','A04','A05']
INPUTS={}


def no_network(*args,**kwargs):raise RuntimeError('Independent E4 review is offline')
def require(ok,why):
    if not ok:raise AssertionError(why)
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def same(a,b):
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(same(a[k],b[k]) for k in a)
    if isinstance(a,bool) or isinstance(b,bool):return type(a)==type(b) and a==b
    if a is None or b is None:return a is None and b is None
    if finite(a) and finite(b):return abs(a-b)<=TOL
    return a==b
def read(path):
    path=Path(path).resolve();INPUTS[str(path)]=j.filehash(path);return j.read(path)
def check_fields(actual,expected,label):
    for k,v in expected.items():require(k in actual and same(actual[k],v),label+':'+k)
def mean(values):return math.fsum(values)/len(values)
def cat(metric):return next(k for k,v in GROUPS.items() if metric in v)


def values_from_trial(trial,step):
    success=trial['status']=='success' and trial['evaluation'].get('technical_status')=='VALID' and not trial['evaluation'].get('_error')
    if not success:return {k:None for k in METRICS},False
    blocks=trial['evaluation']['legacy_diagnostics']['scores'];values={}
    for metric in GROUPS['direct_judge']+GROUPS['computed_EGES']:
        group='completeness' if metric=='c_param' else 'correctness' if metric.startswith('co_') else 'effectiveness'
        value=blocks[group][metric]['score'];values[metric]=value if finite(value) else None
    for k in ['sr','sp']:values[k]=step[k]
    cor=[values[k]/m if finite(values[k]) else None for k,m in zip(['co_order','co_method','co_param','co_chem'],[3,2,2,1])]
    eff=[(values['s_method']/2.5+1)/2 if finite(values['s_method']) else None]
    eff += [values[k]/m if finite(values[k]) else None for k,m in zip(['s_label','s_trans','s_time'],[6,3,3])]
    values['Cor']=mean(cor) if all(finite(v) for v in cor) else None
    values['Eff']=mean(eff) if all(finite(v) for v in eff) else None
    values['Com']=.4*values['sr']+.6*values['c_param']/3 if finite(values['sr']) and finite(values['c_param']) else None
    joint=[values[k] for k in ['Com','Cor','Eff']]
    values['IA']=min(joint) if all(finite(v) for v in joint) else None
    values['HV']=math.prod(joint) if all(finite(v) for v in joint) else None
    return values,True


def main():
    socket.create_connection=no_network;socket.socket.connect=no_network;socket.socket.connect_ex=no_network
    before=parent.request_count()
    plan=read(BATCH/'plan.json');matrix=read(BATCH/'matrix.json');cases=read(BATCH/'cases.json')['cases']
    original_steps={r['case_id']:r for r in read(parent.DEV/'step_results.json')}
    observations=read(ANALYSIS/'observations.json');reported={r['trial_id']:r for r in observations}
    require(len(matrix)==len(reported)==30 and len(cases)==5,'fixed_matrix_shape')
    require(plan['metrics']['tolerance']==TOL,'frozen_tolerance')
    case_by_id={c['case_id']:c for c in cases};lookup={};numeric_slot_checks=0;failures=[]
    for cell in matrix:
        tid=cell['planned_trial_id'];trial=read(BATCH/'run/trials'/f'{tid}.json')
        require(trial['identity']==cell['identity'] and tid==j.digest(cell['identity']),'exact_trial_identity')
        case=case_by_id[trial['case_id']];aid=case['anonymous_answer_id'];step=original_steps[case['case_id']]
        require(step['input_sha256']==case['answer_sha256'],'step_input_identity')
        expected,success=values_from_trial(trial,step);r=reported[tid]
        check_fields(r,expected,'raw_trial_to_analysis_observation');numeric_slot_checks+=len(METRICS)
        check_fields(r,{'anonymous_answer_id':aid,'judge':trial['judge'],'repeat_index':trial['repeat_index'],
                       'full_pipeline_success':success,'status':trial['status']},'observation_metadata')
        require(r['original_step_evidence']['sr']==step['sr'] and r['original_step_evidence']['sp']==step['sp'],'original_steps_not_separately_retained')
        for metric in GROUPS['direct_judge']+GROUPS['computed_EGES']+['Cor','Eff']:
            require(same(trial['preserved_numeric_proposals'][metric],expected[metric]),'trial_proposal_formula_mismatch')
        if not success:
            require(all(r[k] is None and r['numeric_NA_reasons'][k]=='technical_pipeline_failure' for k in METRICS),'failure_imputed_or_not_marked_NA')
            failures.append({'anonymous_answer_id':aid,'judge':trial['judge'],'repeat_index':trial['repeat_index'],
                'reused':cell['disposition']=='exact_prior_observation_reused','all_16_NA':True,'original_steps_retained_separately':True})
        lookup[aid,trial['judge'],trial['repeat_index']]=expected
    require(numeric_slot_checks==480 and len(lookup)==30 and len(failures)==2,'all_observations_and_failures')
    rw={(r['anonymous_answer_id'],r['judge'],r['metric']):r for r in read(ANALYSIS/'within.json')}
    rb={(r['anonymous_answer_id'],r['metric']):r for r in read(ANALYSIS/'between.json')}
    rp={(r['anonymous_answer_id'],r['metric'],r['repeat_index']):r for r in read(ANALYSIS/'same_repeat_pairs.json')}
    require((len(rw),len(rb),len(rp))==(160,80,240),'all_group_denominators')
    within=[];between=[];pairs=[]
    for aid in IDS:
        for judge in MODELS:
            for metric in METRICS:
                values=[lookup[aid,judge,i][metric] for i in range(3)];valid=[x for x in values if finite(x)];n=len(valid)
                spread=max(valid)-min(valid) if n>=2 else None
                avg=mean(valid) if n else None
                sd=math.sqrt(math.fsum((v-avg)**2 for v in valid)/(n-1)) if n>=2 else None
                row={'category':cat(metric),'planned_n':3,'finite_n':n,'coverage':'complete_three' if n==3 else 'partial' if n else 'no_finite',
                     'values_by_repeat':values,'mean':avg,'sample_sd':sd,'min':min(valid) if n else None,'max':max(valid) if n else None,
                     'range':spread,'nonzero_range':spread>TOL if spread is not None else None,
                     'complete_three_nonzero_range':spread>TOL if n==3 else None}
                check_fields(rw[aid,judge,metric],row,'within');within.append(row)
        for metric in METRICS:
            a=[lookup[aid,MODELS[0],i][metric] for i in range(3)];b=[lookup[aid,MODELS[1],i][metric] for i in range(3)]
            deltas=[y-x if finite(x) and finite(y) else None for x,y in zip(a,b)];valid=[d for d in deltas if finite(d)]
            complete=all(finite(x) for x in a+b);md=mean(b)-mean(a) if complete else None
            row={'category':cat(metric),'planned_paired_repeats':3,'qwen_finite_n':sum(finite(v) for v in a),
                'llama_finite_n':sum(finite(v) for v in b),'finite_same_repeat_pairs':len(valid),
                'paired_deltas_llama_minus_qwen':deltas,'different_same_repeat_pairs':sum(abs(d)>TOL for d in valid),
                'any_same_repeat_difference':any(abs(d)>TOL for d in valid) if valid else None,
                'max_abs_paired_delta':max(abs(d) for d in valid) if valid else None,'both_complete_three':complete,
                'complete_qwen_mean':mean(a) if complete else None,'complete_llama_mean':mean(b) if complete else None,
                'complete_mean_delta_llama_minus_qwen':md,'complete_mean_difference':abs(md)>TOL if complete else None}
            check_fields(rb[aid,metric],row,'between');between.append(row)
            for repeat,(av,bv,d) in enumerate(zip(a,b,deltas)):
                row={'category':cat(metric),'qwen_value':av,'llama_value':bv,'both_finite':finite(d),
                     'llama_minus_qwen':d,'different':abs(d)>TOL if finite(d) else None}
                check_fields(rp[aid,metric,repeat],row,'same_repeat_pair');pairs.append(row)
    categories=[]
    for category in GROUPS:
        ww=[r for r in within if r['category']==category];bb=[r for r in between if r['category']==category];pp=[r for r in pairs if r['category']==category]
        categories.append({'category':category,'within_planned_groups':len(ww),'within_complete_three':sum(r['finite_n']==3 for r in ww),
            'within_partial':sum(0<r['finite_n']<3 for r in ww),'within_no_finite':sum(r['finite_n']==0 for r in ww),
            'within_range_evaluable':sum(r['range'] is not None for r in ww),'within_nonzero_range':sum(r['nonzero_range'] is True for r in ww),
            'within_complete_nonzero_range':sum(r['complete_three_nonzero_range'] is True for r in ww),
            'maximum_evaluable_range':max((r['range'] for r in ww if r['range'] is not None),default=None),
            'between_planned_groups':len(bb),'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in bb),
            'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in bb),
            'between_both_complete_three':sum(r['both_complete_three'] for r in bb),
            'between_complete_mean_different':sum(r['complete_mean_difference'] is True for r in bb),
            'planned_same_repeat_metric_pairs':len(pp),'finite_same_repeat_metric_pairs':sum(r['both_finite'] for r in pp),
            'different_same_repeat_metric_pairs':sum(r['different'] is True for r in pp)})
    actual_categories=read(ANALYSIS/'category_summary.json');require(same(categories,actual_categories),'category_aggregation_mismatch')
    summary=read(ANALYSIS/'completion_summary.json')
    expected_summary={'actual_observations':30,'technical_successful_observations':28,'technical_failed_observations':2,
        'exact_reused_observations':sum(c['disposition']=='exact_prior_observation_reused' for c in matrix),
        'new_requests_this_batch':sum(c['disposition']=='new_request_planned' for c in matrix),
        'metric_categories':GROUPS,'categories':categories,'within_groups':len(within),'between_groups':len(between),
        'same_repeat_metric_pairs':len(pairs),'within_complete_three':sum(r['finite_n']==3 for r in within),
        'within_partial':sum(0<r['finite_n']<3 for r in within),'within_no_finite':sum(r['finite_n']==0 for r in within),
        'within_range_evaluable':sum(r['range'] is not None for r in within),'within_nonzero_range':sum(r['nonzero_range'] is True for r in within),
        'within_complete_nonzero_range':sum(r['complete_three_nonzero_range'] is True for r in within),
        'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in between),
        'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in between),
        'between_both_complete_three':sum(r['both_complete_three'] for r in between),
        'between_complete_mean_different':sum(r['complete_mean_difference'] is True for r in between),
        'finite_same_repeat_metric_pairs':sum(r['both_finite'] for r in pairs),'different_same_repeat_metric_pairs':sum(r['different'] is True for r in pairs)}
    check_fields(summary,expected_summary,'completion_summary')
    old=ROOT/'artifacts/cce_validation/judges/stability_remediation_v2/analysis'
    old_within=read(old/'repeat_components.json');old_between=read(old/'cross_family_comparison.json')
    require(len(old_within)==64 and len(old_between)==32,'historical_group_identity')
    require({r['question_id'] for r in old_within}=={2,21},'historical_two_questions')
    for path,digest in INPUTS.items():require(j.filehash(path)==digest,'read_input_changed')
    require(parent.request_count()==before,'review_made_request')
    receipt={'status':'pass','created_utc':j.now(),'reviewer':'independent main_scope_expand agent; terminal analyzer authored by reference_recovery',
        'numeric_comparison_tolerance':TOL,'raw_trial_metric_slots_checked':numeric_slot_checks,
        'within_groups_checked':len(within),'between_groups_checked':len(between),'same_repeat_pairs_checked':len(pairs),
        'recomputed_counts':expected_summary,'failure_retention':failures,
        'dependency_assessment':{'direct_judge_metrics':5,'computed_EGES_metrics':4,'deterministic_reused_step_metrics':2,'derived_metrics':5,
            'Com_dependencies':['sr','c_param'],'Cor_dependencies':['co_order','co_method','co_param','co_chem'],
            'Eff_dependencies':['s_method','s_label','s_trans','s_time'],'IA_and_HV_dependencies':['Com','Cor','Eff'],
            '160_metric_groups_are_not_160_independent_answers':True,'independent_answers':5,
            'deterministic_steps_are_not_independent_judge_agreement':True,
            'do_not_add_derived_metric_disagreements_as_independent_errors':True},
        'historical_version_boundary':{'old_within_groups':64,'old_between_groups':32,'old_source':str(old),
            'new_within_groups':160,'new_between_groups':80,'observations_not_pooled':True,
            'note':'Old within two-answer groups and cross-judge groups remain a different prompt experiment. A separate old rank_flips file also has 32 rows but is not a cross-judge group denominator.'},
        'paper_claim_limits':['6/144 nonzero within-group ranges includes direct, EGES and dependent aggregate metrics; it is not six independent evaluation errors.',
            'Sixteen A04/Qwen groups have only one finite repeat. Their range and sample SD are NA, not zero.',
            '33/80 is any matched-repeat difference; 27/64 is the difference of complete three-repeat judge means. These are distinct denominators.',
            '81/208 finite matched-repeat metric pairs differs from 240 planned slots; missing pairs are not disagreements or zeros.',
            '28/30 structural/full-pipeline success does not establish faithful identity or target assignment; see A04_repeat_trace.json.',
            'Fixed five exposed development answers do not establish held-out stability or expert agreement.'],
        'blocking_findings':[],'new_judge_requests':0,'heldout_scientific_outputs_read':0,'formal_eligible':False,
        'script':parent.bind(__file__),'analyzer_source':parent.bind(ROOT/'scripts/cce_analyze_identity_stability_dev_v1.py'),
        'input_bindings':[{'path':p,'sha256':h} for p,h in INPUTS.items()],
        'actual_command':[sys.executable,*sys.argv]}
    j.save(BATCH/'analysis_independent_review.json',receipt)
    lines=['# E4 终态独立复算','',
        '核验通过，无阻断问题。独立从 30 条实际 trial 的原评分块和 5 份原步骤证据重建 480 个指标槽，未导入终态分析器计算函数；所有输入哈希未变，新增调用 0。','',
        '- 160 个组内组：144 组完整三次，16 组仅一次有效；后者范围/标准差为 NA，未伪装成零波动。可算范围的 144 组中 6 组非零。',
        '- 80 个跨评价器组均至少有一次双方有效，33 组至少一次不同；仅 64 组双方都完整三次，其中 27 组均值不同。',
        '- 240 个逐 repeat 指标配对槽中 208 个双方有效，81 个不同；32 个缺失配对未补零。',
        '- A04/Qwen repeat 0、1 两次失败全部 16 指标为 NA，原 SR/SP 独立证据另存，没有选择 repeat 2 替换。','',
        '5 个直接分项、4 个 EGES 分项、2 个确定性步骤指标和 5 个派生量分层一致。Com、Cor、Eff 依赖其上游分项，IA/HV 又依赖三维；不能把这些差异重复当成独立错误，也不能把 160/80 个指标组说成独立任务数。','',
        '旧 stability_remediation_v2 的 64/32 组与本轮 160/80 组未混合。旧 rank_flips 也有 32 行，但它是另一种分母，不能拿来替代跨评价器组。','',
        '28/30 技术成功不等于科学准确；A04 的完整名称与目标对应风险见 [逐观察取证](A04_repeat_trace.md)。范围仅固定五份公开开发答案，未增加或检查留出科学输出。','',
        '[完整数字、输入哈希与核验脚本记录](analysis_independent_review.json)','',
        '```powershell',f"& '{sys.executable}' scripts/cce_review_identity_stability_dev_v1.py",'```']
    (BATCH/'analysis_independent_review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(j.canonical({'status':'pass','raw_metric_slots':480,'within':160,'between':80,'same_repeat':240,
        'new_judge_requests':0,'review_sha256':j.filehash(BATCH/'analysis_independent_review.json')}))


if __name__=='__main__':main()
