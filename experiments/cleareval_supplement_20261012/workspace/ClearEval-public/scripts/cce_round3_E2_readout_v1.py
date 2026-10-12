"""Describe all frozen E2 pairs and repeats; task-cluster resampling is descriptive."""
from __future__ import annotations
import argparse, collections, itertools, json, math, random, statistics, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_round3_runner_v2 as runner

R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
DIRECT=list(runner.base.scoring.DIRECT)
JUDGED=DIRECT+list(runner.base.scoring.EGES)


def delta(a,b):
    return b-a if runner.finite(a) and runner.finite(b) else None


def direction(value):
    return 'unknown' if value is None else ('equal' if abs(value)<=1e-12 else ('increase' if value>0 else 'decrease'))


def quantile(values,p):
    ordered=sorted(values);position=(len(ordered)-1)*p
    low=math.floor(position);high=math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


def main(args):
    batch=Path(args.batch).resolve();out=Path(args.out).resolve()
    plan,cases,matrix,contract=runner.validate(batch)
    pointer=runner.j.read(batch/'latest_analysis.json')
    runner.base.verify_bindings(list(pointer.values()))
    rows=runner.j.read(pointer['observations']['path'])
    assert len(rows)==24 and plan['repeats']==2 and len(cases)==12
    index={(r['case_id'],r['repeat_index']):r for r in rows}
    pairs=runner.j.read(R3/'representation_repair/controlled_panel_v1/pairs.json')
    assert set(index)=={(c['case_id'],r) for c in cases for r in range(2)}
    paired=[]
    for pair in pairs:
        for repeat in range(2):
            a=index[pair['baseline_case_id'],repeat];b=index[pair['variant_case_id'],repeat]
            observed=a['status']!='pending' and b['status']!='pending'
            diffs={k:delta(a['metrics'][k],b['metrics'][k]) if observed else None for k in runner.METRICS}
            invariance=all(diffs[k]==0 for k in DIRECT) if all(diffs[k] is not None for k in DIRECT) else None
            paired.append({**pair,'repeat_index':repeat,'observed_pair':observed,
                'baseline_trial_id':a['trial_id'],'variant_trial_id':b['trial_id'],
                'baseline_status':a['status'],'variant_status':b['status'],
                'baseline_metrics':a['metrics'],'variant_metrics':b['metrics'],'deltas':diffs,
                'directions':{k:direction(v) for k,v in diffs.items()},
                'all_five_direct_exactly_invariant':invariance,
                'both_complete_CCE':observed and a['complete_numeric_CCE'] and b['complete_numeric_CCE']})
    repeated=[]
    for case in cases:
        a,b=[index[case['case_id'],r] for r in range(2)]
        for metric in JUDGED:
            values=[r['metrics'][metric] for r in [a,b] if r['status']!='pending' and runner.finite(r['metrics'][metric])]
            done=[r['status']!='pending' for r in [a,b]]
            repeated.append({'case_id':case['case_id'],'question_id':case['question_id'],
                'metric':metric,'planned_repeats':2,'observed_repeats':sum(done),'available_values':len(values),
                'values':[r['metrics'][metric] if r['status']!='pending' else None for r in [a,b]],
                'both_finite':len(values)==2,'range':max(values)-min(values) if len(values)==2 else None,
                'sample_SD':statistics.stdev(values) if len(values)==2 else None,
                'missingness_transition':(runner.finite(a['metrics'][metric])!=runner.finite(b['metrics'][metric])) if all(done) else None,
                'both_missing':all(done) and len(values)==0})
    summaries={}
    for condition in ['numbering','merge','necessary_step_deletion']:
        rr=[r for r in paired if r['condition']==condition]
        summaries[condition]={'planned_pairs_with_repeats':len(rr),'observed_pairs':sum(r['observed_pair'] for r in rr),
            'independent_base_tasks':3,'all_direct_invariant':sum(r['all_five_direct_exactly_invariant'] is True for r in rr),
            'direct_invariance_unknown':sum(r['all_five_direct_exactly_invariant'] is None for r in rr),
            'complete_CCE_pairs':sum(r['both_complete_CCE'] for r in rr),
            'directions':{k:dict(collections.Counter(r['directions'][k] for r in rr)) for k in runner.METRICS}}
    # One observation per task carries its complete pair/repeat block. There are
    # three exposed tasks, not 18 independent pairs or 24 independent answers.
    resampled=[]; rng=random.Random(20261011)
    task_ids=sorted({c['question_id'] for c in cases})
    assert len(task_ids)==3
    bootstrap=[tuple(rng.choice(task_ids) for _ in task_ids) for _ in range(2000)]
    exact=list(itertools.product(task_ids,repeat=len(task_ids)))
    specifications=[('numbering',k) for k in DIRECT]+[('merge',k) for k in DIRECT]+[
        ('necessary_step_deletion',k) for k in ['c_param','sr','Com','co_order']]
    for condition,metric in specifications:
        bytask={q:[r['deltas'][metric] for r in paired if r['question_id']==q and r['condition']==condition] for q in task_ids}
        complete={q:statistics.mean(v) for q,v in bytask.items() if len(v)==2 and all(x is not None for x in v)}
        if len(complete)!=3:
            resampled.append({'condition':condition,'metric':metric,'status':'not_computed_incomplete_three_task_support',
                'available_tasks':list(complete),'planned_tasks':task_ids});continue
        record={'condition':condition,'metric':metric,'status':'descriptive_exposed_panel_only',
            'task_mean_deltas':complete,'observed_mean_delta':statistics.mean(complete.values())}
        for name,draws in [('bootstrap_2000',bootstrap),('exact_ordered_27',exact)]:
            values=[statistics.mean(complete[q] for q in draw) for draw in draws]
            record[name]={'draws':len(draws),'mean':statistics.mean(values),
                'percentile_2_5':quantile(values,.025),'percentile_97_5':quantile(values,.975),
                'minimum':min(values),'maximum':max(values),
                'decrease_fraction':sum(v < -1e-12 for v in values)/len(values),
                'equal_fraction':sum(abs(v)<=1e-12 for v in values)/len(values),
                'increase_fraction':sum(v > 1e-12 for v in values)/len(values)}
        resampled.append(record)
    summary={'status':'complete' if all(r['status']!='pending' for r in rows) else 'partial_snapshot',
        'planned_observations':24,'observed':sum(r['status']!='pending' for r in rows),
        'technical_success':sum(r['status']=='success' for r in rows),
        'complete_numeric_CCE':sum(r['complete_numeric_CCE'] for r in rows),
        'independent_base_tasks':3,'conditions':summaries,
        'repeatability':{'planned_judged_metric_groups':len(repeated),
            'both_finite_groups':sum(r['both_finite'] for r in repeated),
            'zero_range_among_both_finite':sum(r['both_finite'] and r['range']==0 for r in repeated),
            'nonzero_range_among_both_finite':sum(r['both_finite'] and r['range']!=0 for r in repeated),
            'missingness_transitions':sum(r['missingness_transition'] is True for r in repeated),
            'both_missing_groups':sum(r['both_missing'] for r in repeated),
            'SR_SP_excluded_from_judge_repeatability':True},
        'interpretation':['canonical input invariance is constructed at the system level',
            'same canonical payload calls are not independent tasks',
            'raw SR/SP and numeric formulas are unchanged',
            'resampling quantiles are descriptive sensitivity, not population-calibrated confidence intervals',
            'scientific accuracy and biological necessity require independent evidence'],
        'new_model_calls':0,'actual_command':[sys.executable,*sys.argv]}
    for name,obj in [('summary.json',summary),('paired_results.json',paired),('repeatability.json',repeated),
                     ('task_cluster_resampling.json',resampled),('bootstrap_task_draws.json',bootstrap),('exact_task_draws.json',exact)]:
        runner.save_once(out/name,obj)
    runner.save_once(out/'verification.json',{'status':'pass','new_model_calls':0,
        'source_bindings':[runner.bind(__file__),runner.bind(batch/'plan.json'),*pointer.values(),
            runner.bind(R3/'E2_prospective_analysis_plan_v1.json'),runner.bind(R3/'canonical_source_v1/validation_freeze.json'),
            runner.bind(R3/'representation_repair/controlled_panel_v1/pairs.json')],
        'output_bindings':[runner.bind(p) for p in sorted(out.glob('*.json'))]})
    print(json.dumps(summary,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args())
