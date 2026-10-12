"""Recompute conditional CCE from the automatic source-time ledger, without calls."""
import csv,itertools,json,math,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent;BASE=OUT.parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import cce_analysis as analysis

rows=b.read(OUT/'canonical32_04/results.json');byid={r['cell_id']:r for r in rows}
prior={r['cell_id']:r for r in b.read(BASE/'semantic_source_revision/method_candidate_02/results.json')}
batch=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01'
cases={r['anonymous_answer_id']+'__r0':r for r in b.read(batch/'cases.json')['cases']}
models=['openai_claude-sonnet-4.6','openai_qwen3-max'];questions=['23','248']
dest=OUT/'joint_01';assert not dest.exists();checks=[];outputs=[];draws=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
def cohort(choices=None,unbranched=False):
    selected=[]
    for cid in ['R3C05__r0','R3C06__r0','R3C07__r0','R3C08__r0']:
        row,case=byid[cid],cases[cid]
        check('original_answer_identity:'+cid,prior[cid]['original_answer_sha256']==case['answer_sha256'])
        v=(choices or {}).get(cid,row['metrics'])
        if unbranched and not row['candidate_point_applied']:
            v={**v,'s_time':None,'Eff':None,'IA':None,'HV':None}
        selected.append({'cell_id':cid,'model':case['generator_model'],'question_id':str(row['question_id']),
            'question_sha256':case['question_sha256'],'answer_sha256':case['answer_sha256'],
            'identity_eligible':True,'formal_eligible':False,**v})
    return selected

strict,_=analysis.common_summary(cohort(unbranched=True),models,scope='automatic_unbranched_only',denominator=2)
inherited,_=analysis.common_summary(cohort(),models,scope='automatic_plus_inherited_C08_include_bleach',denominator=2)
b.save(dest/'unbranched_common_set.json',strict);b.save(dest/'inherited_point_common_set.json',inherited)
check('unbranched_common_set_empty',strict['common_question_ids']==[])
check('inherited_C08_point_only_q248',inherited['common_question_ids']==['248'])

oldmain=[r for r in b.read(BASE/'semantic_source_revision/joint_with_optional_bleach/results.json') if r['main_scope']]
for left,right in itertools.product(byid['R3C05__r0']['conditional_time_results'],byid['R3C08__r0']['conditional_time_results']):
    name='C05_'+left['scenario_id']+'__C08_'+right['scenario_id']
    selected=cohort({'R3C05__r0':left['metrics'],'R3C08__r0':right['metrics']})
    summary,index=analysis.common_summary(selected,models,scope='automatic_development_conditional',denominator=2)
    check('two_shared_tasks:'+name,summary['common_question_ids']==questions)
    previous=[r for r in oldmain if r['C05_hours']==left['hours'] and
        next(x for x in r['per_answer'] if x['cell_id']=='R3C08__r0')['s_time']==right['metrics']['s_time']]
    check('one_prior_source_assisted_scenario:'+name,len(previous)==1)
    check('all_joint_values_reproduced_automatically:'+name,summary['means']==previous[0]['joint']['means'])
    exact=[]
    for number,selection in enumerate(itertools.product(questions,repeat=2)):
        means={m:{k:math.fsum(index[m][q][k] for q in selection)/2 for k in analysis.SUMMARY_METRICS} for m in models}
        matrix,front=analysis.matrix_and_pareto(means)
        item={'scenario_id':name,'draw_id':number,'question_draw':list(selection),'weight':.25,
            'means':means,'nondominated':front,'dominance_matrix':matrix,
            'delta_mean_HV_Claude_minus_Qwen':means[models[0]]['HV']-means[models[1]]['HV']}
        exact.append(item);draws.append(item)
    check('exact_mean_equals_observed:'+name,all(math.isclose(
        math.fsum(r['means'][m][k] for r in exact)/4,summary['means'][m][k],abs_tol=1e-12)
        for m in models for k in analysis.SUMMARY_METRICS))
    outputs.append({'scenario_id':name,'C05_scenario':left['scenario_id'],'C08_scenario':right['scenario_id'],
        'C05_hours':left['hours'],'C08_hours':right['hours'],'C07_hours':byid['R3C07__r0']['time_candidate_ledger']['hours'],
        'per_answer':selected,'joint':summary,
        'exact_nondominance_frequency':{m:sum(m in r['nondominated'] for r in exact)/4 for m in models},
        'delta_mean_HV_Claude_minus_Qwen':summary['means'][models[0]]['HV']-summary['means'][models[1]]['HV'],
        'source_assisted_comparator_scenario':previous[0]['scenario_id'],
        'formal_result':False,'family_independence_established':False})
dependency=b.read(BASE/'semantic_source_revision/joint/source_dependency_audit.json')
for ref in dependency['source_bindings']:check('dependency_input_hash:'+ref['path'],b.bind(ref['path'])==ref)
check('one_connected_source_block',dependency['component_n']==1)
check('all_eight_scenarios',len(outputs)==8)
check('both_models_nondominated',all(set(r['joint']['empirical_nondominated'])==set(models) for r in outputs))
check('branch_sensitive_HV_order',min(r['delta_mean_HV_Claude_minus_Qwen'] for r in outputs)<0<max(r['delta_mean_HV_Claude_minus_Qwen'] for r in outputs))
summary={'scope':'automatic development replay; archived direct Cor retained; conditional, not prospective confirmation',
    'actual_generator_answers':4,'paired_tasks':questions,'generators':models,
    'unbranched_common_tasks':strict['common_question_ids'],'inherited_C08_point_common_tasks':inherited['common_question_ids'],
    'conditional_common_tasks':questions,'automatic_timing_scenarios':8,
    'exact_question_draws_per_scenario':4,'total_derived_draws':len(draws),'new_observations':0,
    'independent_source_blocks':dependency['component_n'],'population_confidence_interval_claimed':False,
    'both_models_nondominated_in_all_scenarios':True,'new_model_calls':0,
    'prior_source_assisted_main_scenarios_numerically_reproduced':8,
    'aggregation':outputs[0]['joint']['aggregation'],
    'values':[{'C05_hours':r['C05_hours'],'C08_hours':r['C08_hours'],
        'Claude_mean_HV':r['joint']['means'][models[0]]['HV'],'Qwen_mean_HV':r['joint']['means'][models[1]]['HV'],
        'delta_HV':r['delta_mean_HV_Claude_minus_Qwen']} for r in outputs]}
b.save(dest/'results.json',outputs);b.save(dest/'exact_draws.json',draws);b.save(dest/'summary.json',summary)
b.save(dest/'verification.json',{'checks_passed':len(checks),'checks':checks})
b.save(dest/'source_dependency_audit.json',dependency)
with (dest/'model_means.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['scenario_id','C05_hours','C08_hours','model','common_n','nondominated',*analysis.SUMMARY_METRICS,'exact_nondominance_frequency']);w.writeheader()
    for r in outputs:
        for m in models:w.writerow({'scenario_id':r['scenario_id'],'C05_hours':r['C05_hours'],'C08_hours':r['C08_hours'],
            'model':m,'common_n':2,'nondominated':m in r['joint']['empirical_nondominated'],**r['joint']['means'][m],
            'exact_nondominance_frequency':r['exact_nondominance_frequency'][m]})
b.save(dest/'manifest.json',{'command':[sys.executable,*sys.argv],'inputs':[b.bind(x) for x in [
    __file__,analysis.__file__,OUT/'canonical32_04/results.json',batch/'cases.json',
    BASE/'semantic_source_revision/method_candidate_02/results.json',
    BASE/'semantic_source_revision/joint_with_optional_bleach/results.json',
    BASE/'semantic_source_revision/joint/source_dependency_audit.json']]})
print(json.dumps(summary,ensure_ascii=False,indent=2))
