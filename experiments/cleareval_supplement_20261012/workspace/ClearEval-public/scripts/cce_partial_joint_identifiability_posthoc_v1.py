"""Original partial-identifiability mathematics on an explicit posthoc E5 input.

This diagnostic never fills missing scores and never replaces complete-Q*.
"""
import argparse,itertools,json,math,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_partial_joint_identifiability_v1 as original
a=original.analysis

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    assert not args.out.exists(),'NEW_OUTPUT_REQUIRED'
    source=a.read(args.source/'per_answer.json');summary=a.read(args.source/'summary.json');verification=a.read(args.source/'verification.json')
    assert verification['status']=='pass' and summary['raw_model_outputs_reinterpreted_posthoc'] is True
    assert summary['prospective_confirmation_claim'] is False
    assert len(source)==10 and summary['terminal_answers']==10
    assert {(r['model'],int(r['question_id'])) for r in source}==set(itertools.product(original.MODELS,original.QIDS))
    bindings=[a.bind(args.source/n) for n in ['per_answer.json','summary.json','verification.json']]
    rows=[]
    for r in source:
        bounds,channels=original.bounds(r)
        rows.append({'anonymous_answer_id':r['anonymous_answer_id'],'model':r['model'],'question_id':r['question_id'],
          'original_status':r['original_status'],'frozen_confirmation_metrics':r['original_frozen_metrics'],
          'posthoc_input_metrics':{k:r[k] for k in a.METRICS},'bounds':bounds,
          'normalized_component_bounds':channels,'missing_posthoc_components':[k for k in channels if r[k] is None]})
    means=original.mean_bounds(rows);pairs,identified=original.identify(means)
    rng=original.np.random.default_rng(a.SEED)
    mc=original.resample(rows,rng.choice(original.QIDS,size=(a.REPEATS,len(original.QIDS)),replace=True))
    exact=original.resample(rows,itertools.product(original.QIDS,repeat=len(original.QIDS)))
    assert len(mc)==4000 and len(exact)==6250
    assert all(mc[i]['question_draws']==mc[i+1]['question_draws'] for i in range(0,len(mc),2))
    for model in original.MODELS:
        for key in original.JOINT:
            for suffix,i in [('lower',0),('upper',1)]:
                assert math.isclose(sum(r[key+'_'+suffix] for r in exact if r['model']==model)/3125,
                    means[model][key][i],rel_tol=1e-10,abs_tol=1e-12)
    output={'status':'completed_posthoc_partial_identifiability_diagnostic','fixed_tasks':original.QIDS,'fixed_models':original.MODELS,
      'actual_answers':10,'input_posthoc_complete_CCE':summary['complete_CCE'],'input_posthoc_common_n':summary['common_n'],
      'frozen_confirmation_complete_CCE':summary['original_frozen_complete_CCE'],
      'posthoc_processor':summary['posthoc_processor'],'mean_bounds':means,'dominance_partial_information':pairs,
      'identified_nondominance':identified,'task_resamples':2000,'seed':a.SEED,'exact_ordered_resamples':3125,
      'mc_identifiability_frequencies':original.frequencies(mc),'exact_identifiability_frequencies':original.frequencies(exact),
      'frequency_interpretation':'Frequency of synchronized task multisets guaranteed or not ruled out as nondominated over every allowed completion of missing components; not completed-score frontier probability.',
      'intervals':'Deterministic outer bounds holding available provisional inputs fixed. Not confidence intervals, attainable joint sets, missing-value imputation or scientific validity probabilities.',
      'complete_Qstar_analysis_not_replaced':True,'posthoc_not_new_confirmation':True,'new_model_calls':0,'new_embeddings':0}
    args.out.mkdir(parents=True)
    for name,value in [('summary',output),('per_answer_bounds',rows),('task_bootstrap_draws',mc),('task_exact_draws',exact)]:a.write(args.out/(name+'.json'),value)
    a.csvwrite(args.out/'per_answer_bounds.csv',[{**{k:r[k] for k in ['anonymous_answer_id','model','question_id','missing_posthoc_components']},
        **{key+'_lower':r['bounds'][key][0] for key in original.JOINT},**{key+'_upper':r['bounds'][key][1] for key in original.JOINT}} for r in rows])
    a.csvwrite(args.out/'task_bootstrap_draws.csv',mc);a.csvwrite(args.out/'task_exact_draws.csv',exact)
    a.verify_bindings(bindings)
    a.write(args.out/'verification.json',{'status':'pass','source_bindings':bindings,
      'script':a.bind(__file__),'unchanged_math_source':a.bind(original.__file__),
      'all_ten_original_statuses_and_frozen_metrics_retained':True,'known_points_exact':True,
      'exact_bootstrap_mean_equals_empirical_mean':True,'synchronized_task_draws':True,
      'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,'expert_validation':False})
    print(json.dumps(output,ensure_ascii=False))
if __name__=='__main__':main()
