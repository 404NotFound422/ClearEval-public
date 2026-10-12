"""Evaluate a source-scope candidate against all 32 fixed archived returns."""
import copy
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_reported_operation_scope_v1 as scope
import cce_typed_label_scorer_v2 as typed
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES
from cce_scales_source_key_alias_v1 import source_key_alias
b=typed.base


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=OUT/'scope_candidate_02')
    args=parser.parse_args()
    rows=b.read(OUT/'actual_01/results.json')
    config=b.read(OUT.parent/'scorer_revision/config.json')
    policy=b.read(OUT.parent/'typed_label_revision/policy_with_sources.json')
    runner,registry=b.runtime()
    dest=args.out
    plan={'entrypoint':b.bind(__file__),'scope_candidate':b.bind(scope.__file__),
        'typed_scorer':b.bind(typed.__file__),'inputs':b.bind(OUT/'actual_01/results.json'),
        'policy':b.bind(OUT.parent/'typed_label_revision/policy_with_sources.json'),
        'config':b.bind(OUT.parent/'scorer_revision/config.json'),
        'version':scope.VERSION,
        'new_model_calls':0,'new_author_annotations':0,
        'scientific_claim':'exploratory source-scope interpretation; original outcomes are retained'}
    if (dest/'plan.json').exists():
        assert b.read(dest/'plan.json')==plan,'Use a new output directory for a changed configuration'
    else:
        b.save(dest/'plan.json',plan)
    results=[]
    for row in rows:
        original=copy.deepcopy(row)
        previous=row['typed_midpoint_metrics']
        post=b.read(row['source_record']['path'])
        doc=b.read(row['source_document']['path'])
        changes=[];time=None
        if post.get('conversion'):
            projection,changes=scope.repeated_secondary_projection(post['conversion'],doc,policy)
            candidate=copy.deepcopy(post)
            candidate['conversion']['label_occurrence_projection']=projection
            row['metrics']=previous
            result=typed.replay_row(row,candidate,policy,config,runner,registry,doc=doc)
            metric=result['metrics']
            time=scope.time_interpretation(post['conversion'],doc,post['numeric']['quantitative_data']['total_time_hours'])
            if b.finite(time['hours']) and previous['s_time'] is None:
                with source_key_alias():
                    numeric=runner.calculate_effectiveness_score({**post['numeric']['quantitative_data'],'total_time_hours':time['hours']},
                        post['numeric']['user_preference_vector'],runner.MODEL_SPACE_SIGNED,{},[])
                metric=derive({**{k:metric[k] for k in DIRECT+EGES},'s_time':numeric['s_time']},
                              {k:metric[k] for k in ['sr','sp']},True)
                time['original_numeric_time_computation']=numeric['time_computation']
        else:
            result=None;metric=previous
        assert all(metric[k]==previous[k] for k in DIRECT+['s_method','s_trans','sr','sp','Com','Cor'])
        original.update(scope_candidate_metrics=metric,scope_time_interpretation=time,
            repeated_channel_resolution=changes,scope_label_derivation=result.get('label_derivation') if result else None,
            scope_changes={k:{'before':previous[k],'after':v} for k,v in metric.items() if previous[k]!=v},
            original_raw_untouched=True,new_model_calls=0,new_author_annotations=0)
        b.save(dest/'records'/row['cohort']/(row['saved_trial_id']+'.json'),original)
        results.append(original)
    b.save(dest/'results.json',results)
    summary=[]
    for cohort in sorted({r['cohort'] for r in results}):
        subset=[r for r in results if r['cohort']==cohort]
        for condition in ['primary_metrics','typed_midpoint_metrics','scope_candidate_metrics']:
            summary.append({'cohort':cohort,'condition':condition,'returns':len(subset),
                'complete_CCE':sum(b.complete(r[condition]) for r in subset),
                's_label_available':sum(r[condition]['s_label'] is not None for r in subset),
                's_time_available':sum(r[condition]['s_time'] is not None for r in subset)})
    b.save(dest/'summary.json',summary)
    fields=['cohort','cell_id','condition',*results[0]['metrics']]
    with (dest/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in results:
            for condition in ['primary_metrics','typed_midpoint_metrics','scope_candidate_metrics']:
                w.writerow({k:row[k] for k in fields[:2]}|{'condition':condition}|row[condition])
    b.save(dest/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0,'new_author_annotations':0})
    print(json.dumps({'summary':summary,'changed_cells':[{k:r[k] for k in ['cell_id','scope_changes']}
         for r in results if r['scope_changes']]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
