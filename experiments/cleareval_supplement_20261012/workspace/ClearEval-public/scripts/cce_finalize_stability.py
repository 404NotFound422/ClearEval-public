"""Descriptive stability from actual local judge responses, retaining failure flags."""
import collections
import json
import math
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import OUT,read,write,table,digest,mean

def main():
    directory=OUT/'judges/local_stability'
    steps={s['case_id']:s for s in read(OUT/'controls/step_results.json')}
    rows=[]
    for path in sorted((directory/'trials').glob('*.json')):
        t=read(path);step=steps.get(t['case_id'])
        if not step:continue
        n=t.get('preserved_numeric_proposals',{});ev=t.get('evaluation',{});ex=ev.get('extraction',{})
        successful=t.get('status')=='success'
        cp=n.get('c_param');sr=step['sr']
        com=.4*sr+.6*cp/3 if cp is not None and sr is not None else None
        dims=[com,n.get('Cor'),n.get('Eff')]
        expected_route=step['step_result'].get('route_id');actual_route=ex.get('method_name')
        agrees=actual_route.casefold()==expected_route.casefold() if isinstance(actual_route,str) and isinstance(expected_route,str) else None
        row={'case_id':t['case_id'],'question_id':t['question_id'],'judge':t['judge'],'judge_family':t['judge_family'],
            'repeat_index':t['repeat_index'],'trial_id':t['trial_id'],'status':t['status'],
            'config_hash':t['pipeline_config_sha256'],'input_hash':t['full_text_input_sha256'],'reference_id':step['reference_id'],
            'sr':sr,'sp':step['sp'],**n,'Com':com,'IA':min(dims) if all(x is not None for x in dims) else None,
            'HV':math.prod(dims) if all(x is not None for x in dims) else None,
            'extraction_sha256':t.get('extraction_sha256'),'explicit_route':expected_route,'extracted_route':actual_route,
            'explicit_route_extraction_agrees':agrees,'extracted_time_hours':ex.get('clearing_total_time_hours'),
            'scientific_validity':'evaluator_failure_explicit_route_mismatch' if agrees is False else 'not_expert_validated',
            'formal_eligible':False,'numeric_scope':'current_local_substitute_diagnostic','trial_source':str(path)}
        rows.append(row)
    groups=collections.defaultdict(list)
    for row in rows:groups[(row['case_id'],row['judge'],row['config_hash'])].append(row)
    spread=[];metrics=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']
    for (cid,judge,conf),g in groups.items():
        for metric in metrics:
            vals=[r[metric] for r in g if isinstance(r.get(metric),(float,int)) and math.isfinite(r[metric])]
            spread.append({'case_id':cid,'judge':judge,'config_hash':conf,'metric':metric,'observations':len(g),'finite_n':len(vals),
                'mean':mean(vals),'sd':statistics.stdev(vals) if len(vals)>1 else None,'range':max(vals)-min(vals) if vals else None,
                'score_changed':len(set(vals))>1,'na_varied':0<len(vals)<len(g),'reference_varied':len({r['reference_id'] for r in g})>1,
                'extraction_distinct_n':len({r['extraction_sha256'] for r in g}),'interpretation':'within-current-configuration repetition; not accuracy validation'})
    cross=[]
    qgroups=collections.defaultdict(dict)
    for row in rows:qgroups[(row['case_id'],row['repeat_index'])][row['judge_family']]=row
    for (cid,rep),g in qgroups.items():
        if not {'qwen','llama'}<=set(g):continue
        a,b=g['qwen'],g['llama']
        cross.append({'case_id':cid,'repeat_index':rep,'qwen_trial':a['trial_id'],'llama_trial':b['trial_id'],
            'qwen_route_agrees':a['explicit_route_extraction_agrees'],'llama_route_agrees':b['explicit_route_extraction_agrees'],
            **{'llama_minus_qwen_'+m:b[m]-a[m] if b.get(m) is not None and a.get(m) is not None else None for m in ['Com','Cor','Eff','IA','HV']}})
    status={'planned_observations':12,'observations':len(rows),'technical_success':sum(r['status']=='success' for r in rows),
        'independent_answers':len({r['case_id'] for r in rows}),'judge_families':sorted({r['judge_family'] for r in rows}),
        'reuse_policy':'Two E2 Qwen baseline real requests are prespecified repeat0; all other repeats are new requests; deterministic rescoring is not counted.',
        'explicit_route_mismatches':sum(r['explicit_route_extraction_agrees'] is False for r in rows),
        'mismatches_by_family':dict(collections.Counter(r['judge_family'] for r in rows if r['explicit_route_extraction_agrees'] is False)),
        'completed_three_repeat_groups':sum(len(g)==3 for g in groups.values()),'cross_family_paired_observations':len(cross),
        'mean_cross_family_delta_Eff':mean([r['llama_minus_qwen_Eff'] for r in cross if r['llama_minus_qwen_Eff'] is not None]),
        'score_range_max':max((s['range'] for s in spread if s['range'] is not None),default=None),
        'scope':'development, current substitute; retained numerical proposals include explicitly flagged extraction failures; no validated primary CCE claim',
        'scientific_validation_complete':False}
    write(directory/'cce_stability_summary.json',status);write(directory/'cce_per_observation.json',rows)
    table(directory/'cce_per_observation.csv',rows);table(directory/'audited_cce_repeat_spread.csv',spread);table(directory/'audited_cross_family_deltas.csv',cross)
    print(json.dumps(status,ensure_ascii=True))

if __name__=='__main__':main()
