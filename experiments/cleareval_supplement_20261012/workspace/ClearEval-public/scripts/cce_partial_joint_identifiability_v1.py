"""Bounds from actual retained components; no missing score is imputed.

This explicitly separate diagnostic uses all five fixed secondary tasks. It
does not replace the complete-CCE Q* analysis or its pending bootstrap. Bounds
use only the original metric ranges/formulas, not a probabilistic missingness
model. The synchronized bootstrap resamples tasks and preserves each interval.
"""
from __future__ import annotations
import argparse
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import numpy as np
import cce_secondary_E5_analysis_v2 as analysis

JOINT = ['Com','Cor','Eff','IA','HV']
MODELS, QIDS = analysis.MODELS, analysis.QIDS


def bounds(row):
    """Return outer bounds under the published original component ranges."""
    assert all(analysis.numeric.finite(row[k]) for k in ['Com','Cor'])
    channels = {}
    for key, scale, offset in [('s_method',5,.5),('s_label',6,0),('s_trans',3,0),('s_time',3,0)]:
        value = row[key]
        if value is None:
            channels[key] = [0.,1.]
        else:
            transformed = value/scale + offset
            assert -1e-12 <= transformed <= 1+1e-12, (key,value)
            channels[key] = [transformed,transformed]
    low, high = [sum(v[i] for v in channels.values())/4 for i in [0,1]]
    c, r = row['Com'], row['Cor']
    result = {'Com':[c,c], 'Cor':[r,r], 'Eff':[low,high],
              'IA':[min(c,r,low),min(c,r,high)], 'HV':[c*r*low,c*r*high]}
    for key in JOINT:
        if row[key] is not None:
            assert all(math.isclose(row[key], x, rel_tol=1e-12, abs_tol=1e-12) for x in result[key])
    return result, channels


def mean_bounds(rows):
    return {m:{k:[sum(row['bounds'][k][i] for row in rows if row['model']==m)/sum(row['model']==m for row in rows)
                    for i in [0,1]] for k in JOINT} for m in MODELS}


def dominance(a,b):
    dimensions = ['Com','Cor','Eff']
    impossible = [k for k in dimensions if a[k][1] < b[k][0]-1e-12]
    if impossible:
        return {'state':'cannot_dominate', 'witness_dimensions':impossible}
    certain = all(a[k][0] >= b[k][1]-1e-12 for k in dimensions) and any(a[k][0] > b[k][1]+1e-12 for k in dimensions)
    if certain:
        return {'state':'dominates_for_every_admissible_completion','witness_dimensions':[]}
    if all(a[k][0]==a[k][1]==b[k][0]==b[k][1] for k in dimensions):
        return {'state':'cannot_dominate','witness_dimensions':['all_dimensions_equal']}
    return {'state':'unresolved_with_current_components','witness_dimensions':[]}


def identify(means):
    pairs = {a:{b:dominance(means[a],means[b]) for b in MODELS if a!=b} for a in MODELS}
    result = {}
    for model in MODELS:
        incoming = [pairs[other][model]['state'] for other in MODELS if other!=model]
        result[model] = {
            'guaranteed_nondominated':all(x=='cannot_dominate' for x in incoming),
            'not_ruled_out_as_nondominated':not any(x=='dominates_for_every_admissible_completion' for x in incoming)}
    return pairs,result


def resample(rows,draws):
    grouped={q:[r for r in rows if int(r['question_id'])==q] for q in QIDS}
    output=[]
    for index,draw in enumerate(draws):
        sample=[r for q in draw for r in grouped[int(q)]]
        means=mean_bounds(sample);pairs,identified=identify(means)
        for model in MODELS:
            output.append(dict(replicate=index,model=model,question_draws=[int(q) for q in draw],
                **identified[model],**{k+'_lower':means[model][k][0] for k in JOINT},
                **{k+'_upper':means[model][k][1] for k in JOINT}))
    return output


def frequencies(rows):
    return {m:{k:sum(r[k] for r in rows if r['model']==m)/sum(r['model']==m for r in rows)
                   for k in ['guaranteed_nondominated','not_ruled_out_as_nondominated']} for m in MODELS}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert not a.out.exists()
    source=analysis.read(a.source/'per_answer.json');summary=analysis.read(a.source/'summary.json')
    assert len(source)==10 and summary['terminal_answers']==10
    assert {(r['model'],int(r['question_id'])) for r in source}==set(itertools.product(MODELS,QIDS))
    source_bindings=[analysis.bind(a.source/name) for name in ['per_answer.json','summary.json','verification.json']]
    rows=[]
    for r in source:
        value,channels=bounds(r)
        rows.append(dict(anonymous_answer_id=r['anonymous_answer_id'],model=r['model'],question_id=r['question_id'],
            original_metrics={k:r[k] for k in analysis.METRICS},bounds=value,normalized_component_bounds=channels,
            missing_original_components=[k for k in channels if r[k] is None]))
    means=mean_bounds(rows);pairs,identified=identify(means)
    rng=np.random.default_rng(analysis.SEED)
    mc=resample(rows,rng.choice(QIDS,size=(analysis.REPEATS,len(QIDS)),replace=True))
    exact=resample(rows,itertools.product(QIDS,repeat=len(QIDS)))
    assert len(mc)==4000 and len(exact)==6250
    assert all(mc[i]['question_draws']==mc[i+1]['question_draws'] for i in range(0,len(mc),2))
    mc_freq,exact_freq=frequencies(mc),frequencies(exact)
    for model in MODELS:
        for k in JOINT:
            for suffix,i in [('lower',0),('upper',1)]:
                assert math.isclose(sum(r[k+'_'+suffix] for r in exact if r['model']==model)/3125,means[model][k][i],rel_tol=1e-10,abs_tol=1e-12)
    output=dict(status='completed_partial_identifiability_diagnostic',fixed_tasks=QIDS,fixed_models=MODELS,
        actual_answers=10,original_complete_CCE=summary['complete_CCE'],original_complete_common_n=summary['common_n'],
        scope='All five prespecified secondary tasks; conditional references; posthoc diagnostic. Not complete-Q* point estimation.',
        mean_bounds=means,dominance_partial_information=pairs,identified_nondominance=identified,
        task_resamples=2000,seed=analysis.SEED,exact_ordered_resamples=3125,
        mc_identifiability_frequencies=mc_freq,exact_identifiability_frequencies=exact_freq,
        frequency_interpretation='Bounds on conditional empirical nondominance frequency, not completed-score nondominance estimates or probabilities of scientific correctness.',
        intervals='Deterministic outer bounds from missing component ranges; neither confidence intervals nor point imputation. Unknown components may have dependencies not represented by these outer bounds.',
        original_scores_unchanged=True,new_model_calls=0,new_embeddings=0)
    a.out.mkdir(parents=True)
    for name,value in [('summary',output),('per_answer_bounds',rows),('task_bootstrap_draws',mc),('task_exact_draws',exact)]:
        analysis.write(a.out/(name+'.json'),value)
    analysis.csvwrite(a.out/'per_answer_bounds.csv',[{**{k:r[k] for k in ['anonymous_answer_id','model','question_id','missing_original_components']},
        **{k+'_lower':r['bounds'][k][0] for k in JOINT},**{k+'_upper':r['bounds'][k][1] for k in JOINT}} for r in rows])
    analysis.csvwrite(a.out/'task_bootstrap_draws.csv',mc)
    analysis.csvwrite(a.out/'task_exact_draws.csv',exact)
    analysis.verify_bindings(source_bindings)
    analysis.write(a.out/'verification.json',dict(status='pass',source_bindings=source_bindings,script=analysis.bind(__file__),
        actual_command=[sys.executable,*sys.argv],all_ten_original_rows_retained=True,known_points_exact=True,
        exact_bootstrap_mean_equals_empirical_mean=True,synchronized_task_draws=True,
        new_model_calls=0,expert_validation=False))
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    main()
