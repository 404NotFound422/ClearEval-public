"""Conditional two-generator readout using the existing CCE aggregation.

Two shared tasks permit exhaustive enumeration of all four ordered bootstrap
draws. No Monte Carlo repetitions or independent-sample inference are needed.
"""
import csv
import itertools
import json
import math
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import cce_analysis as analysis

rows=b.read(OUT/'semantic_03/results.json');byid={r['cell_id']:r for r in rows}
batch=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01'
cases={c['anonymous_answer_id']+'__r0':c for c in b.read(batch/'cases.json')['cases']}
models=['openai_claude-sonnet-4.6','openai_qwen3-max'];questions=['23','248']
dest=OUT/'joint_with_optional_bleach';outputs=[];draws=[];checks=[]

def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append({'name':name,'passed':True})

def cohort(choices):
    result=[]
    for ident in ['R3C05__r0','R3C06__r0','R3C07__r0','R3C08__r0']:
        row,case=byid[ident],cases[ident]
        check('original_answer_identity:'+ident,row['original_answer_sha256']==case['answer_sha256'])
        values=choices.get(ident,row['source_assisted_metrics'])
        result.append({'model':case['generator_model'],'question_id':row['question_id'],
            'question_sha256':case['question_sha256'],'answer_sha256':case['answer_sha256'],
            'cell_id':ident,'identity_eligible':True,'formal_eligible':False,**values})
    return result

# Reuse the main-project definition: average per-answer IA and HV.
before,_=analysis.common_summary(cohort({'R3C05__r0':byid['R3C05__r0']['method_candidate_metrics'],
    'R3C07__r0':byid['R3C07__r0']['method_candidate_metrics']}),models,
    scope='automatic_candidate_before_source_assistance',denominator=2)
single,_=analysis.common_summary(cohort({}),models,scope='source_assisted_single_value_subset',denominator=2)
b.save(dest/'before.json',before);b.save(dest/'single_value_subset.json',single)

for left,right,bleach in itertools.product(byid['R3C05__r0']['semantic_scenarios'],byid['R3C07__r0']['semantic_scenarios'],
        b.read(OUT/'numeric_sensitivities.json')['C08_optional_bleaching']):
    scenario=left['scenario_id']+'___'+right['scenario_id']+'___'+bleach['scenario_id']
    selected=cohort({'R3C05__r0':left['metrics'],'R3C07__r0':right['metrics'],'R3C08__r0':bleach['metrics']})
    summary,by=analysis.common_summary(selected,models,scope='conditional_source_assisted_posthoc',denominator=2)
    check('two_common_tasks:'+scenario,summary['common_question_ids']==questions)
    exact=[]
    for index,question_draw in enumerate(itertools.product(questions,repeat=2)):
        means={m:{k:math.fsum(by[m][q][k] for q in question_draw)/2 for k in analysis.SUMMARY_METRICS} for m in models}
        matrix,front=analysis.matrix_and_pareto(means)
        draw={'scenario_id':scenario,'draw_id':index,'question_draw':list(question_draw),
            'weight':.25,'means':means,'nondominated':front,'dominance_matrix':matrix,
            'delta_mean_HV_Claude_minus_Qwen':means[models[0]]['HV']-means[models[1]]['HV']}
        draws.append(draw);exact.append(draw)
    freq={m:sum(m in d['nondominated'] for d in exact)/4 for m in models}
    check('exact_bootstrap_mean_equals_original:'+scenario,all(
        math.isclose(math.fsum(d['means'][m][k] for d in exact)/4,summary['means'][m][k],abs_tol=1e-12)
        for m in models for k in analysis.SUMMARY_METRICS))
    outputs.append({'scenario_id':scenario,'C05_scenario':left['scenario_id'],'C07_scenario':right['scenario_id'],
        'C08_scenario':bleach['scenario_id'],
        'main_scope':left['scenario_id'].endswith('__with_preimaging') and right['scenario_id']=='explicit_setpoint',
        'C05_hours':left['time_derivation']['hours'],'C07_hours':right['time_derivation']['hours'],
        'per_answer':selected,'joint':summary,'exact_nondominance_frequency':freq,
        'delta_mean_HV_Claude_minus_Qwen':summary['means'][models[0]]['HV']-summary['means'][models[1]]['HV'],
        'resampling':'all 2^2=4 ordered question draws, pairing both models within each draw',
        'family_independence_established':False,'formal_result':False})

main=[r for r in outputs if r['main_scope']]
check('eight_main_timing_branches',len(main)==8)
check('HV_order_changes_across_explicit_branches',min(r['delta_mean_HV_Claude_minus_Qwen'] for r in main)<0<max(r['delta_mean_HV_Claude_minus_Qwen'] for r in main))
check('both_models_nondominated_on_shared_two_tasks',all(set(r['joint']['empirical_nondominated'])==set(models) for r in outputs))
b.save(dest/'results.json',outputs);b.save(dest/'exact_draws.json',draws)
b.save(dest/'verification.json',{'checks_passed':len(checks),'checks':checks})
with (dest/'model_means.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=['scenario_id','main_scope','model','common_n','nondominated',*analysis.SUMMARY_METRICS,'exact_nondominance_frequency']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in outputs:
        for m in models:w.writerow({'scenario_id':r['scenario_id'],'main_scope':r['main_scope'],'model':m,'common_n':2,
            'nondominated':m in r['joint']['empirical_nondominated'],**r['joint']['means'][m],
            'exact_nondominance_frequency':r['exact_nondominance_frequency'][m]})
summary={'scope':'post-hoc source-assisted conditional comparison, not new prospective confirmation',
    'generators':models,'shared_tasks':questions,'automatic_complete_common_tasks_before':before['common_question_ids'],
    'single_value_common_tasks_after':single['common_question_ids'],
    'conditional_complete_common_tasks':questions,'main_timing_scenarios':8,'all_scope_and_setpoint_scenarios':len(outputs),
    'exact_draws_per_scenario':4,'draws_are_not_new_observations':True,
    'aggregate_definition':main[0]['joint']['aggregation'],
    'Qwen_mean_HV_by_optional_bleach':{r['C08_scenario']:r['joint']['means'][models[1]]['HV'] for r in main},
    'Claude_main_scope_mean_HV_values':[{'scenario':r['C05_scenario'],'C08_scenario':r['C08_scenario'],'value':r['joint']['means'][models[0]]['HV'],
        'delta_from_Qwen':r['delta_mean_HV_Claude_minus_Qwen']} for r in main],
    'pareto_result':'both generators nondominated in all 32 declared scenarios',
    'exact_nondominance_frequency':main[0]['exact_nondominance_frequency'],
    'family_independence_established':False,'population_confidence_interval_claimed':False,'new_model_calls':0}
b.save(dest/'summary.json',summary)
b.save(dest/'manifest.json',{'entrypoint':b.bind(__file__),'scores':b.bind(OUT/'semantic_03/results.json'),
    'optional_bleach_sensitivity':b.bind(OUT/'numeric_sensitivities.json'),
    'identity':b.bind(batch/'cases.json'),'original_analysis':b.bind(analysis.__file__),
    'command':[sys.executable,*sys.argv]})
print(json.dumps(summary,ensure_ascii=False,indent=2))
