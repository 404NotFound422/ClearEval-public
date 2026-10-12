"""Apply the fixed typed-label scorer to later archived batches, without calls.

No answer-specific annotations or new lookup rules. Retains original terminal
states and scores alongside label-only and generic-midpoint replay conditions.
"""
from __future__ import annotations
import argparse
import copy
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_typed_label_scorer_v2 as typed
b=typed.base
VERSION='typed-label-fixed-rule-transfer-v1'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batches',nargs='+',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    plan={'version':VERSION,'batches':[b.bind(batch/'matrix.json') for batch in args.batches],
        'config':b.bind(args.config),'policy':b.bind(args.policy),'scorer':b.bind(typed.__file__),
        'midpoint_scorer':b.bind(b.__file__),'entrypoint':b.bind(__file__),
        'new_model_calls':0,'new_author_annotations':0,'interpretation':'post-hoc transfer to later archived returns, not new prospective confirmation',
        'conditions':['archived_primary','typed_labels_only','typed_labels_and_generic_midpoint'],
        'allowed_changes':['s_label','s_time','Eff','IA','HV'],'original_SR_SP_retained':True}
    if (args.out/'plan.json').exists():
        assert b.read(args.out/'plan.json')==plan,'Fixed transfer configuration changed; use a new output directory'
    else:
        b.save(args.out/'plan.json',plan)
    config,policy=b.read(args.config),b.read(args.policy)
    runner,registry=b.runtime()
    results=[];bindings={}
    for batch in args.batches:
        for cell in b.read(batch/'matrix.json'):
            tid=cell['planned_trial_id']
            trial_path=batch/'run/trials'/(tid+'.json')
            post_path=batch/'run/attempts'/(tid+'_1')/'processing.json'
            for name,binding in cell['assets'].items():
                assert b.bind(binding['path'])==binding,('asset changed',name)
                bindings[binding['path']]=binding
            trial,post,doc=b.read(trial_path),b.read(post_path),b.read(cell['assets']['doc']['path'])
            assert trial['metrics']==post['metrics']
            for binding in trial['bound_artifacts']:
                assert b.bind(binding['path'])==binding
                bindings[binding['path']]=binding
            raw=trial['metrics']
            row={'cell_id':cell['anonymous_answer_id']+'__r'+str(cell['repeat_index']),
                'cohort':batch.name,'question_id':cell['question_id'],'case_id':cell['case_id'],
                'anonymous_answer_id':cell['anonymous_answer_id'],'repeat_index':cell['repeat_index'],
                'metrics':raw,'complete_numeric_CCE':b.complete(raw),
                'original_status':trial['status'],'source_record':b.bind(post_path),
                'source_document':cell['assets']['doc'],'answer_sha256':doc['answer_sha256'],
                'original_answer_sha256':cell['step']['answer_sha256'],
                'trial':b.bind(trial_path),'saved_trial_id':tid}
            if post.get('conversion'):
                row['quantitative_data']=post['numeric']['quantitative_data']
                calc=post['conversion']['legacy_projection']['time_calculation']
                row['time_derivation']={'hours':row['quantitative_data']['total_time_hours'],
                                        'issues':calc.get('issues',[]),'original_calculation':calc}
            labels=typed.replay_row(row,post,policy,config,runner,registry,doc=doc)
            if post.get('conversion'):
                time=b.score_record(post,cell['question_id'],config,runner,registry,doc=doc)
                midpoint=typed.replay_row({**row,**time},post,policy,config,runner,registry,doc=doc)
            else:
                midpoint=copy.deepcopy(labels)
            result={**row,'version':VERSION,'primary_metrics':raw,
                'typed_label_metrics':labels['metrics'],'typed_midpoint_metrics':midpoint['metrics'],
                'label_replay_status':labels['typed_replay_status'],
                'label_derivation':labels.get('label_derivation'),
                'compatibility_lookup_trace':labels.get('compatibility_lookup_trace'),
                'midpoint_time_derivation':midpoint.get('time_derivation'),
                'remaining_dependencies':midpoint.get('remaining_dependencies'),
                'original_technical_status_preserved':True,'new_model_calls':0,'new_author_annotations':0}
            for condition in ['typed_label_metrics','typed_midpoint_metrics']:
                assert all(result[condition][k]==raw[k] for k in typed.DIRECT+['s_method','s_trans','sr','sp','Com','Cor'])
            assert labels['metrics']['s_time']==raw['s_time']
            b.save(args.out/'records'/batch.name/(tid+'.json'),result)
            results.append(result)
    summary=[]
    for batch in args.batches:
        subset=[r for r in results if r['cohort']==batch.name]
        for condition in ['primary_metrics','typed_label_metrics','typed_midpoint_metrics']:
            summary.append({'cohort':batch.name,'condition':condition,'returns':len(subset),
                'original_full_success':sum(r['original_status']=='success' for r in subset),
                'complete_CCE':sum(b.complete(r[condition]) for r in subset),
                's_label_available':sum(r[condition]['s_label'] is not None for r in subset),
                's_time_available':sum(r[condition]['s_time'] is not None for r in subset),
                'Cor_available':sum(r[condition]['Cor'] is not None for r in subset),
                'new_model_calls':0,'new_author_annotations':0})
    b.save(args.out/'results.json',results)
    b.save(args.out/'summary.json',summary)
    b.save(args.out/'source_bindings.json',list(bindings.values()))
    with (args.out/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['cohort','cell_id','question_id','original_status','condition',*results[0]['metrics']]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in results:
            for condition in ['primary_metrics','typed_label_metrics','typed_midpoint_metrics']:
                writer.writerow({**{k:row[k] for k in fields[:4]},'condition':condition,**row[condition]})
    assert all(b.bind(path)==binding for path,binding in bindings.items())
    b.save(args.out/'execution.json',{'command':[sys.executable,*sys.argv],'plan':b.bind(args.out/'plan.json'),
        'returns':len(results),'source_files_verified':len(bindings),'new_model_calls':0,'new_author_annotations':0})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
