"""Frozen 0.6/0.7/0.8 sensitivity from saved maxima; primary SR/SP stay intact."""
import csv,json,math,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
OUT=Path(__file__).resolve().parent;DEST=OUT/'threshold_01';assert not DEST.exists()
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import cce_analysis as analysis
from cce_grounded_offline_scoring_v1 import DIRECT,EGES,derive
thresholds=[.6,.7,.8];checks=[];records=[];candidates=[];joint=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
def score(rmax,gmax,t):
    return {'sr':sum(x>=t for x in rmax)/len(rmax),'sp':sum(x>=t for x in gmax)/len(gmax) if gmax else 0.,
        'reference_hits':sum(x>=t for x in rmax),'generated_hits':sum(x>=t for x in gmax)}
def metrics(values,steps):
    return derive({k:values[k] for k in DIRECT+EGES},{k:steps[k] for k in ['sr','sp']},True)
rows=b.read(OUT/'canonical32_04/results.json');byid={r['cell_id']:r for r in rows}
details=b.read(R3/'confirmation_inputs_01/selected_step_details.json')
saved=b.read(R3/'confirmation_qwen_01/steps.json')
cases={r['anonymous_answer_id']:r for r in b.read(R3/'confirmation_qwen_01/cases.json')['cases']}
steps={}
for d in details:
    aid=d['anonymous_answer_id'];cid=aid+'__r0';case=cases[aid];s=saved[d['case_id']]
    check('answer_question_identity:'+aid,s['answer_sha256']==case['answer_sha256'] and s['question_sha256']==case['question_sha256'])
    check('same_frozen_pool:'+aid,[r['reference_id'] for r in d['all_candidates']]==s['candidate_reference_ids'])
    for t in thresholds:
        pool=[]
        for c in d['all_candidates']:
            v=c['score'];rmax=[r['similarity'] for r in v['matches']];gmax=v['generated_max_similarity']
            check('maxima_dimensions:'+aid+':'+c['reference_id']+':'+str(t),len(rmax)==v['reference_n'] and len(gmax)==v['generated_n'])
            sc=score(rmax,gmax,t)
            if t==.7:check('candidate_baseline_exact:'+aid+':'+c['reference_id'],all(sc[k]==v[k] for k in ['sr','sp','reference_hits','generated_hits']))
            item={'cell_id':cid,'threshold':t,'reference_id':c['reference_id'],'version_id':c['version_id'],
                'fixed_order':c['fixed_order'],'reference_n':len(rmax),'generated_n':len(gmax),**sc}
            candidates.append(item);pool.append(item)
        winner=max(pool,key=lambda r:(r['sr'],r['sp'],-r['fixed_order']))
        steps[cid,t]=winner
        if t==.7:check('selected_baseline_exact:'+aid,all(winner[k]==s[k] for k in ['sr','sp','reference_id']))
        result=metrics(byid[cid]['metrics'],winner)
        if t==.7:check('primary_CCE_exact:'+aid,result==byid[cid]['metrics'])
        check('Cor_EGES_unchanged:'+aid+':'+str(t),all(result[k]==byid[cid]['metrics'][k] for k in DIRECT+EGES+['Cor','Eff']))
        records.append({'cell_id':cid,'question_id':str(case['question_id']),'model':case['generator_model'],'threshold':t,
            'selected_reference':winner['reference_id'],'reference_changed_from_primary':winner['reference_id']!=s['reference_id'],
            'primary_sr':s['sr'],'primary_sp':s['sp'],'metrics':result,'complete_numeric_CCE':b.complete(result)})

matrices=b.read(R3/'problem_cycles/step_matching_cycle01/matrices.json')
controlsteps=b.read(R3/'canonical_source_v1/inputs_01/steps.json')
control=[]
for mat in matrices:
    if mat['representation']!='original':continue
    s=controlsteps[mat['case_id']];arr=mat['similarities']
    check('controlled_reference:'+mat['case_id'],mat['reference_id']==s['reference_id'] and s['candidate_reference_ids']==[mat['reference_id']])
    rmax=[max(r) for r in arr];gmax=[max(r[j] for r in arr) for j in range(len(arr[0]))]
    for t in thresholds:
        sc=score(rmax,gmax,t)
        for rep in [0,1]:
            cid=f"R3E2_Q{mat['question_id']:03d}_{mat['condition']}__r{rep}"
            row=byid[cid];v=metrics(row['metrics'],sc)
            if t==.7:check('controlled_primary_exact:'+cid,v==row['metrics'])
            control.append({'cell_id':cid,'question_id':mat['question_id'],'condition':mat['condition'],'repeat_index':rep,'threshold':t,
                'primary_sr':row['metrics']['sr'],'primary_sp':row['metrics']['sp'],'metrics':v})
ci={(r['question_id'],r['condition'],r['repeat_index'],r['threshold']):r for r in control};pairs=[]
for r in control:
    if r['condition']=='baseline':continue
    base=ci[r['question_id'],'baseline',r['repeat_index'],r['threshold']]
    delta={k:r['metrics'][k]-base['metrics'][k] for k in ['sr','sp',*analysis.SUMMARY_METRICS]}
    pairs.append({'question_id':r['question_id'],'condition':r['condition'],'repeat_index':r['repeat_index'],
        'threshold':r['threshold'],'baseline_cell_id':base['cell_id'],'variant_cell_id':r['cell_id'],**{'delta_'+k:v for k,v in delta.items()}})
    if r['condition']=='numbering':check('numbering_invariance:'+r['cell_id']+':'+str(r['threshold']),all(abs(x)<=1e-12 for x in delta.values()))

for scene in b.read(OUT/'joint_01/results.json'):
    for t in thresholds:
        selected=[]
        for r in scene['per_answer']:
            sc=steps[r['cell_id'],t];selected.append({**r,**metrics(r,sc),'selected_reference':sc['reference_id']})
        result,index=analysis.common_summary(selected,scene['joint']['model_cohort'],scope='timing_and_threshold_development_sensitivity',denominator=2)
        check('common_tasks_same_across_thresholds:'+scene['scenario_id']+':'+str(t),result['common_question_ids']==['23','248'])
        if t==.7:check('primary_joint_exact:'+scene['scenario_id'],result['means']==scene['joint']['means'])
        a,c=scene['joint']['model_cohort']
        joint.append({'scenario_id':scene['scenario_id'],'C05_hours':scene['C05_hours'],'C08_hours':scene['C08_hours'],
            'threshold':t,'per_answer':selected,'joint':result,'delta_mean_HV_Claude_minus_Qwen':result['means'][a]['HV']-result['means'][c]['HV']})

coverage=[]
for t in thresholds:
    sub=[r for r in records if r['threshold']==t]
    coverage.append({'threshold':t,'answers':len(sub),'sr_sp_available':sum(b.finite(r['metrics']['sr']) and b.finite(r['metrics']['sp']) for r in sub),
        'numeric_CCE_with_inherited_branch_points':sum(r['complete_numeric_CCE'] for r in sub),
        'unbranched_numeric_CCE':sum(r['complete_numeric_CCE'] and byid[r['cell_id']]['candidate_point_applied'] for r in sub),
        'reference_changes':sum(r['reference_changed_from_primary'] for r in sub)})
summary={'scope':'exposed development sensitivity, no threshold chosen from outcomes','primary_threshold_preserved':.7,
    'thresholds':thresholds,'coverage':coverage,'actual_confirmation_answers':8,'controlled_return_rows':24,
    'derived_confirmation_settings':len(records),'derived_control_settings':len(control),'derived_control_pairs':len(pairs),
    'joint_scenarios':len(joint),'same_joint_tasks_across_all_settings':['23','248'],
    'two_generators_nondominated_at_each_threshold':{str(t):all(len(r['joint']['empirical_nondominated'])==2 for r in joint if r['threshold']==t) for t in thresholds},
    'HV_delta_range_by_threshold':{str(t):[min(r['delta_mean_HV_Claude_minus_Qwen'] for r in joint if r['threshold']==t),max(r['delta_mean_HV_Claude_minus_Qwen'] for r in joint if r['threshold']==t)] for t in thresholds},
    'new_model_calls':0,'new_embeddings':0,'new_pairwise_similarities':0,'source_family_blocks':1,'independent_accuracy_claimed':False}
for name,data in [('confirmation.json',records),('candidates.json',candidates),('controlled.json',control),('controlled_pairs.json',pairs),('joint.json',joint),('summary.json',summary),('verification.json',{'checks_passed':len(checks),'checks':checks})]:b.save(DEST/name,data)
for name,data in [('confirmation',records),('controlled',control)]:
    flat=[{**{k:v for k,v in r.items() if k!='metrics'},**r['metrics']} for r in data]
    with (DEST/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
with (DEST/'controlled_pairs.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
b.save(DEST/'manifest.json',{'command':[sys.executable,*sys.argv],'inputs':[b.bind(p) for p in [__file__,
    ROOT/'scripts/cce_validation.py',analysis.__file__,OUT/'canonical32_04/results.json',OUT/'joint_01/results.json',
    R3/'confirmation_inputs_01/selected_step_details.json',R3/'confirmation_qwen_01/steps.json',R3/'confirmation_qwen_01/cases.json',
    R3/'problem_cycles/step_matching_cycle01/matrices.json',R3/'canonical_source_v1/inputs_01/steps.json']]})
print(json.dumps(summary,ensure_ascii=False,indent=2))
