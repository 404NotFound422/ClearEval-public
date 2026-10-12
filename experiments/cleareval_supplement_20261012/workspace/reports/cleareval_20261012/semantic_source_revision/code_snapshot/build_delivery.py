"""Create examples, a standalone figure, and source/budget verification."""
import csv
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-only',action='store_true')
args=parser.parse_args()
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
from cce_scales_source_key_alias_v1 import source_key_alias
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES

rows=b.read(OUT/'semantic_04/results.json');before=b.read(OUT/'semantic_03/results.json')
annotations={r['cell_id']:r for r in b.read(OUT/'source_annotations_v3.json')['results']}
batch=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01'
cases={c['anonymous_answer_id']+'__r0':c for c in b.read(batch/'cases.json')['cases']}
checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})

check('terminology_clarification_changes_no_scores',all(a['cell_id']==z['cell_id'] and
    a['source_assisted_metrics']==z['source_assisted_metrics'] and
    [s['metrics'] for s in a['semantic_scenarios']]==[s['metrics'] for s in z['semantic_scenarios']]
    for a,z in zip(rows,before)))
b.save(OUT/'joint/latest_score_equivalence.json',{'source_of_joint_analysis':b.bind(OUT/'semantic_03/results.json'),
    'latest_semantic_metadata':b.bind(OUT/'semantic_04/results.json'),'all_score_vectors_identical':True,
    'reason':'TUJ1 wording clarified using a manufacturer counterexample; scored biological target and formulas unchanged.',
    'joint_analysis_reused_without_new_resampling':True})

bindings={}
for row in rows:
    for name in ['source_document','source_record','trial','lexical_post']:
        if row.get(name):bindings[row[name]['path']]=row[name]
    trial=b.read(row['trial']['path'])
    for v in trial['bound_artifacts']:bindings[v['path']]=v
    if row['cell_id'] in annotations:
        for name in ['original_source_document','source_mapping']:
            v=annotations[row['cell_id']][name];bindings[v['path']]=v
    candidates=[row['source_assisted_metrics']]+[s['metrics'] for s in row['semantic_scenarios']]
    for i,m in enumerate(candidates):
        check('raw_and_direct_unchanged:'+row['cell_id']+':'+str(i),all(m[k]==row['metrics'][k] for k in
            ['c_param','co_order','co_method','co_param','co_chem','sr','sp','Com','Cor']))
        if b.complete(m):
            expected=(.4*m['sr']+.6*m['c_param']/3,
                (m['co_order']/3+m['co_method']/2+m['co_param']/2+m['co_chem'])/4,
                ((m['s_method']/2.5+1)/2+m['s_label']/6+m['s_trans']/3+m['s_time']/3)/4)
            check('independent_aggregation:'+row['cell_id']+':'+str(i),
                all(math.isclose(m[k],v,rel_tol=1e-12,abs_tol=1e-14) for k,v in zip(['Com','Cor','Eff'],expected))
                and math.isclose(m['IA'],min(expected),rel_tol=1e-12)
                and math.isclose(m['HV'],math.prod(expected),rel_tol=1e-12))
    if row['cohort']=='E2_canonical_qwen_01':
        check('controlled_unchanged:'+row['cell_id'],row['source_assisted_metrics']==row['final_candidate_metrics'])
for binding in bindings.values():check('source_sha256:'+binding['path'],b.bind(binding['path'])==binding)

for row in rows:
    if row['cohort']!='confirmation_qwen_01':continue
    cell=row['cell_id'];case=cases[cell];folder=OUT/'examples'/cell;folder.mkdir(parents=True,exist_ok=True)
    (folder/'original_answer.txt').write_text(case['model_response'],encoding='utf-8')
    (folder/'question.txt').write_text(case['specific_question'],encoding='utf-8')
    doc=b.read(row['source_document']['path'])
    (folder/'canonical_answer.txt').write_text(doc['text'],encoding='utf-8')
    oldpost=b.read(row['source_record']['path'])
    rawpath=Path(row['source_record']['path']).parent/'raw_response.txt'
    shutil.copyfile(rawpath,folder/'archived_judge_response.json')
    b.save(folder/'full_flow.json',{'generator':case['generator_model'],'question_id':case['question_id'],
        'original_answer_sha256':case['answer_sha256'],'canonical_answer_sha256':doc['answer_sha256'],
        'sources':{'case_file':b.bind(batch/'cases.json'),'original_dataset':b.bind(case['answer_source']),
            'canonical_document':row['source_document'],'archived_judge_response':b.bind(rawpath),
            'archived_processing':row['source_record'],'lexical_reparse':row.get('lexical_post')},
        'archived_metrics':row['metrics'],'automatic_candidate_metrics':row['method_candidate_metrics'],
        'source_assisted_metrics':row['source_assisted_metrics'],'annotation':annotations.get(cell),
        'label_derivation':row.get('source_assisted_label_derivation') or row['label_derivation'],
        'time_scenarios':row['semantic_scenarios'],'prior_time_interpretation':row.get('final_time_interpretation'),
        'quantitative_inputs':row.get('semantic_quantitative_inputs'),
        'original_full_conversion_success':oldpost.get('full_conversion_success'),
        'original_judge_JSON_not_rewritten':True,'new_model_calls':0,'expert_validated':False})
    m=row['source_assisted_metrics']
    body=f"# {cell} 全流程\n\n生成模型：{case['generator_model']}；题目：{case['question_id']}。\n\n"
    body+='[题干](question.txt) → [原答案](original_answer.txt) → [规范化视图](canonical_answer.txt) → [存档评价器返回](archived_judge_response.json) → [来源分解、取值及全部分支](full_flow.json)。\n\n'
    body+='| Com | Cor | Eff | IA | HV |\n|---|---|---|---|---|\n'
    body+='| '+' | '.join('NA' if m[k] is None else f'{m[k]:.9g}' for k in ['Com','Cor','Eff','IA','HV'])+' |\n\n'
    if row.get('primary_scenario_id'):body+=f"单值解释：`{row['primary_scenario_id']}`。\n\n"
    if row['semantic_scenarios']:
        body+='| 来源解释/分支 | 小时 | Eff | HV |\n|---|---|---|---|\n'
        for s in row['semantic_scenarios']:
            values=[s['time_derivation']['hours'],s['metrics']['Eff'],s['metrics']['HV']]
            body+='| '+s['scenario_id']+' | '+' | '.join('NA' if v is None else f'{v:.9g}' for v in values)+' |\n'
    body+='\n作者辅助分解不计作独立评价器调用或专家回执；旧直接评分、原 SR/SP 和数值公式保留。\n'
    (folder/'README_zh.md').write_text(body,encoding='utf-8')

# One source-declared optional branch in an already scored record: preserve the
# original 32-hour value, while actually evaluating the alternative 20-hour input.
runner,registry=b.runtime();r=next(r for r in rows if r['cell_id']=='R3C08__r0')
post=b.read(r['source_record']['path']);sens=[]
for hours in [20,32]:
    with source_key_alias():
        numeric=runner.calculate_effectiveness_score({**post['numeric']['quantitative_data'],'total_time_hours':hours},
            post['numeric']['user_preference_vector'],runner.MODEL_SPACE_SIGNED,{},[])
    metric=r['source_assisted_metrics']
    updated=derive({**{k:metric[k] for k in DIRECT+EGES},'s_time':numeric['s_time']},
        {k:metric[k] for k in ['sr','sp']},True)
    sens.append({'scenario_id':'include_optional_bleach' if hours==32 else 'omit_optional_bleach',
        'hours':hours,'s_time':numeric['s_time'],'metrics':updated,'time_computation':numeric['time_computation']})
check('C08_optional_branch_changes_actual_time_score',sens[0]['s_time']!=sens[1]['s_time'])
check('C08_included_branch_exactly_reuses_prior_values',sens[1]['metrics']==r['source_assisted_metrics'])
doc=b.read(r['source_document']['path'])
b.save(OUT/'numeric_sensitivities.json',{'C08_optional_bleaching':sens,
    'basis':'Source L0012 makes the 12-hour bleach optional; all other reported core contributions sum to 20 h.',
    'source':r['source_document'],'source_units':[u for u in doc['units'] if u['unit_id'] in ['L0012','L0013']],
    'source_assistant_analysis':True,'expert_validated':False,
    'hypothesis_of_time_score_invariance_rejected_by_actual_calculation':True,
    'original_finite_score_preserved_as_included_branch':True})

external=b.read(OUT.parent/'typed_label_transfer/external_state.json')
all_external=[external['budget']['ledger'],*external['human_inputs'],external['wetlab_source']]
for binding in all_external:check('external_inputs_unchanged:'+binding['path'],b.bind(binding['path'])==binding)
external['verification_this_stage']='ledger, expert input and wet-lab file hashes checked; unchanged values reused'
b.save(OUT/'external_state.json',external)
if args.data_only:
    b.save(OUT/'delivery_data_verification.json',{'checks_passed':len(checks),'checks':checks,
        'source_files_verified':len(bindings),'examples':8,'new_model_calls':0})
    print(json.dumps({'data_prepared':True,'checks_passed':len(checks),'source_files_verified':len(bindings)}))
    sys.exit(0)

# Standalone export for the paper supplement.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
joint=b.read(OUT/'joint_with_optional_bleach/results.json');main=[r for r in joint if r['main_scope']]
models=['openai_claude-sonnet-4.6','openai_qwen3-max']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
    'pdf.fonttype':42,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,2,figsize=(10.8,4.1),layout='constrained',gridspec_kw={'width_ratios':[1,1.3]})
axis=axes[0];dims=['Com','Cor','Eff'];x=np.arange(3)
for i,model in enumerate(models):
    values=np.array([[r['joint']['means'][model][k] for k in dims] for r in main])
    lo,hi=values.min(axis=0),values.max(axis=0)
    axis.vlines(x+(i-.5)*.16,lo,hi,color=['#0072B2','#D55E00'][i],linewidth=4,alpha=.6)
    axis.scatter(x+(i-.5)*.16,values[0],color=['#0072B2','#D55E00'][i],s=42,
        label=['Claude Sonnet 4.6','Qwen3-max'][i],zorder=3)
axis.set_xticks(x,dims);axis.set_ylim(.45,1.0);axis.set_ylabel('Mean score on the same 2 tasks')
axis.set_title('A  CCE trade-off across timing branches',loc='left',fontsize=11)
axis.legend(frameon=False,loc='upper right',fontsize=9)
axis.text(.01,.015,'Bars: source branches, not confidence intervals.',transform=axis.transAxes,fontsize=8)
axis.grid(axis='y',alpha=.15)
axis=axes[1];labels=['4–6 h, no extra step','4–6 h, extra step','Overnight, no extra step','Overnight, extra step']
included=[r for r in main if r['C08_scenario']=='include_optional_bleach']
omitted=[r for r in main if r['C08_scenario']=='omit_optional_bleach']
delta=[r['delta_mean_HV_Claude_minus_Qwen'] for r in included]
other=[r['delta_mean_HV_Claude_minus_Qwen'] for r in omitted]
axis.axvline(0,color='#666666',lw=1)
axis.plot(delta,np.arange(4)-.10,'o',color='#0072B2',label='C08 includes optional bleach')
axis.plot(other,np.arange(4)+.10,'s',color='#D55E00',label='C08 omits optional bleach')
axis.set_yticks(np.arange(4),labels);axis.invert_yaxis();axis.set_xlim(-.006,.015)
axis.set_xticks([-.005,0,.005,.010,.015])
axis.set_ylim(4.05,-.4)
axis.legend(frameon=False,fontsize=8,loc='lower right')
axis.set_xlabel('Mean per-answer HV: Claude − Qwen')
axis.set_title('B  Scalar ordering changes with a source branch',loc='left',fontsize=11)
axis.grid(axis='x',alpha=.15)
fig.suptitle('Source-assisted sensitivity analysis; 2 tasks, no new model calls',fontsize=12)
folder=OUT/'figures';folder.mkdir(exist_ok=True)
for suffix in ['png','pdf','svg']:fig.savefig(folder/('conditional_joint_sensitivity.'+suffix),dpi=200)
plt.close(fig)
b.save(folder/'data.json',{'joint_results':b.bind(OUT/'joint_with_optional_bleach/results.json'),'main_scenarios':[r['scenario_id'] for r in main],
    'caption':'Four C05 timing branches crossed with the two optional-bleach branches of C08; prescribed pre-imaging conditioning and C07 explicit setpoint. Both models are nondominated in all eight scenarios. Range bars are source-branch sensitivity, not statistical confidence intervals.'})
b.save(OUT/'delivery_verification.json',{'checks_passed':len(checks),'checks':checks,
    'source_files_verified':len(bindings),'examples':8,'new_model_calls':0,
    'source_bindings':list(bindings.values()),'figure_visual_inspection':'pending',
    'command':[sys.executable,*sys.argv]})
print(json.dumps({'checks_passed':len(checks),'source_files_verified':len(bindings),'examples':8,
    'figure':str(folder/'conditional_joint_sensitivity.png'),'new_model_calls':0}))
