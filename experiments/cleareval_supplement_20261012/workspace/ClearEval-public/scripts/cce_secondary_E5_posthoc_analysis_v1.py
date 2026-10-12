"""Fixed ten-row E5 analysis of uniform posthoc scores, separate from fw3.

No generation, source conversion, encoder or EGES recalculation occurs here.
The upstream replay has reinterpreted the original raw under explicit posthoc
rules. This analysis does not label those rules as prospective confirmation.
"""
import argparse,copy,json,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_secondary_E5_analysis_v2 as original

FROZEN=original.R2/'secondary_E5_analysis_v2/actual_01'
SCOPE='posthoc_uniform_scoring_same_secondary_fixed_ten_answers_not_new_confirmation'

def analyze(replay,out):
    original.require(not out.exists(),'NEW_OUTPUT_REQUIRED')
    meta=original.fixed_metadata()
    original_verification=original.read(FROZEN/'verification.json')
    original.verify_bindings(original_verification['bindings'])
    verification=original.read(replay/'verification.json');extra=original.read(replay/'implementation_addendum.json')
    original.require(verification['status']==extra['status']=='pass','COMPLETED_POSTHOC_REPLAY_REQUIRED')
    original.verify_bindings(verification['input_bindings']+verification['implementations']+extra['additional_implementation_bindings'])
    original.verify_bindings(verification['outputs']+extra['outputs'])
    summary0=original.read(replay/'summary.json')
    original.require(summary0['raw_returns']==67 and summary0['same_configuration_all67'],'UNIFORM_ALL67_REQUIRED')
    allrows=original.read(replay/'cells.json')
    lookup={r['anonymous_answer_id']:r for r in allrows if r['cohort'] in ['first7_posthoc','secondary8_posthoc']}
    frozen=original.read(FROZEN/'per_answer.json');rows=[];evidence=[]
    expected={r['confirmation_id']:r for r in meta['fixed_secondary_cohort']}
    for previous in frozen:
        aid=previous['anonymous_answer_id'];fixed=expected[aid];candidate=lookup[aid]
        original.require(previous['model']==fixed['model'] and previous['question_id']==fixed['question_id']==candidate['question_id'],'FIXED_GENERATOR_TASK')
        original.require(previous['answer_sha256']==fixed['answer_sha256'] and previous['question_sha256']==fixed['question_sha256'],'FROZEN_SOURCE_HASHES')
        original.require(candidate['status']==previous['status'] and candidate['original_metrics']=={k:previous[k] for k in original.METRICS},'ORIGINAL_STATUS_AND_METRICS_RETAINED')
        original.require(candidate['raw_sha256']==previous['raw_response']['sha256'],'EXACT_RETURN_BYTES')
        doc=previous['source_document']
        original.require(any(p['path']==doc['path'] and p['sha256']==doc['sha256'] for p in candidate['source_bindings']),'POSTHOC_SAME_SOURCE_DOCUMENT')
        value=candidate['posthoc_metrics'];steps={k:previous[k] for k in ['sr','sp']}
        original.require(all(value[k]==steps[k] for k in steps),'ORIGINAL_SR_SP')
        expected_derived=original.numeric.derive(value,steps,True)
        original.require(all(original.numeric.same(expected_derived[k],value[k]) for k in original.METRICS),'UNCHANGED_DERIVED_FORMULAS')
        row=copy.deepcopy(previous)
        row.update(value)
        row.update(original_frozen_metrics={k:previous[k] for k in original.METRICS},
            original_status=previous['status'],posthoc_full_conversion=candidate['posthoc_full_conversion'],
            posthoc_failure=candidate['posthoc_failure'],posthoc_record=candidate['posthoc_record'],
            numeric_processing_version=summary0['scorer_version'],
            raw_reinterpreted_under_posthoc_rules=True,original_confirmation_status_not_promoted=True,
            complete_CCE=all(original.original.finite(value[k]) for k in original.JOINT),
            missing_metrics=[k for k in original.METRICS if not original.original.finite(value[k])])
        rows.append(row);evidence.append(candidate['posthoc_record'])
    original.require(len(rows)==10 and set(r['anonymous_answer_id'] for r in rows)==set(expected),'ALL_TEN_FIXED')
    common,by=original.original.common_summary(rows,original.MODELS,scope=SCOPE,denominator=5,formal=False)
    formal,_=original.original.common_summary(rows,original.MODELS,scope=SCOPE,denominator=5,formal=True)
    formal['eligibility_interpretation']=original.FORMAL_POLICY_NOTE
    task,mc,exact=original.task_bootstrap(common,by)
    family,fd=original.original.family_bootstrap(common,by,original.REPEATS,original.SEED)
    family['mapping_evidence']=[{k:r[k] for k in ['model','question_id','reference_id','family_id']} for r in rows]
    family['eligibility_interpretation']=original.FORMAL_POLICY_NOTE
    catalog=original.read(original.STEPS/'references.json')['references']
    coverage=original.component_summary(rows)
    summary={'status':'completed_posthoc_secondary_analysis','planned_answers':10,'terminal_answers':10,
        'fixed_generator_models':original.MODELS,'generator_family_count':1,'fixed_question_ids':original.QIDS,
        'original_statuses':dict(Counter(r['original_status'] for r in rows)),
        'original_frozen_complete_CCE':sum(all(original.numeric.finite(r[k]) for k in original.JOINT) for r in frozen),
        'complete_CCE':sum(r['complete_CCE'] for r in rows),
        'metric_coverage':{k:sum(original.numeric.finite(r[k]) for r in rows) for k in original.METRICS},
        'common_n':common['common_n'],'common_question_ids':common['common_question_ids'],
        'conditional_means':common['means'],'empirical_nondominated':common['empirical_nondominated'],
        'task_bootstrap_status':task['status'],'family_bootstrap_status':family['status'],
        'formal_common_n':formal['common_n'],'formal_eligibility_interpretation':original.FORMAL_POLICY_NOTE,
        'posthoc_processor':summary0['scorer_version'],'all_ten_same_processor':True,
        'raw_model_outputs_reinterpreted_posthoc':True,'raw_text_or_original_scores_modified':False,
        'prospective_confirmation_claim':False,'scientific_accuracy_validated':False,
        'new_model_requests':0,'new_embeddings':0,'new_EGES_calculations_in_this_analysis':0}
    inputs=[original.bind(p) for p in [__file__,original.__file__,original.original.__file__,original.numeric.__file__,
        original.SELECTION,original.ADDENDUM,original.STEPS/'references.json']]
    inputs += [original.bind(FROZEN/n) for n in ['per_answer.json','summary.json','verification.json']]
    inputs += [original.bind(replay/n) for n in ['cells.json','summary.json','verification.json','implementation_addendum.json']]+evidence
    original.verify_bindings(inputs);out.mkdir(parents=True)
    for name,value in [('summary',summary),('per_answer',rows),('common_joint',common),('formal_common_joint',formal),
        ('component_common_sets',coverage),('task_bootstrap',task),('source_family_bootstrap',family),
        ('task_bootstrap_draws',mc),('task_exact_draws',exact),('source_family_bootstrap_draws',fd),
        ('source_overlap_diagnostic',original.overlap_diagnostic(catalog,common['common_question_ids']))]:
        original.write(out/(name+'.json'),value)
    original.csvwrite(out/'per_answer.csv',rows);original.csvwrite(out/'component_common_sets.csv',coverage)
    original.write(out/'verification.json',{'status':'pass','bindings':inputs,'fixed_ten_identity_and_status_preserved':True,
        'original_SR_SP_and_reference_qualification_preserved':True,'same_posthoc_configuration_all_ten':True,
        'raw_reinterpretation_occurred_in_bound_upstream_replay':True,'original_confirmation_unmodified':True,
        'actual_command':[sys.executable,*sys.argv],'new_model_requests':0,'new_embeddings':0})
    lines=['# 同一10份答案的独立后验E5分析','',
        '这些分数来自统一后验处理。上游确实重新解释了原raw，不是冻结fw3的前瞻确认结果。原status、原16分项、题干/答案hash、参考资格和SR/SP均保留；缺项仍为NA。',
        '',f"完整CCE：冻结原结果 {summary['original_frozen_complete_CCE']}/10，本后验 {summary['complete_CCE']}/10；共同有限任务 {common['common_question_ids']}，共{common['common_n']}/5。",
        '',f"任务重采样状态：{task['status']}；来源家族重采样状态：{family['status']}。仅共同完整任务才进入原common_summary与同步bootstrap，未以分项共同集拼造完整CCE。",
        '',original.FORMAL_POLICY_NOTE,'',
        '两个生成器同属Qwen，五题已暴露，样本按来源覆盖选择。后验修订后的可用率不是科学准确率或独立泛化证据；逐题IA/HV后再取均值，算法和原数值范围不变。',
        '', '[逐答案原值和后验值](per_answer.json) · [摘要](summary.json) · [验证](verification.json)']
    (out/'README_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replay',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();analyze(a.replay,a.out)
