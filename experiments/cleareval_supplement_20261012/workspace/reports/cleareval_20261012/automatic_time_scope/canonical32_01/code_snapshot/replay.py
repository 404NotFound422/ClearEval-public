"""Uniform offline source-time replay; every changed score retains its ledger."""
import argparse,copy,csv,json,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');BASE=Path(__file__).resolve().parent.parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_source_time_ledger_v1 as candidate
import cce_scoped_midpoint_scorer_v1 as b
import cce_posthoc_components_v7 as components
from cce_grounded_offline_scoring_v1 import DIRECT,EGES,derive
from cce_scales_source_key_alias_v1 import source_key_alias

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',choices=['canonical32','archived67'],required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();assert not a.out.exists()
source_path=BASE/'automatic_label_relations'/f'{a.cohort}_03/results.json';rows=b.read(source_path)
priorrows=b.read(BASE/'semantic_source_revision/method_candidate_02/results.json') if a.cohort=='canonical32' else []
prior={r['cell_id']:r for r in priorrows}
evidence={r['cell_id']:r for r in b.read(BASE/'missing_score_diagnosis/evidence.json')['records']}
runner,registry=b.runtime();results=[];bound=[b.bind(x) for x in [__file__,candidate.__file__,source_path,candidate.ground.__file__,candidate.scopes.__file__,candidate.headings.__file__]]
ledger=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl';ledger_before=b.bind(ledger)

def score(row,hours):
    quantitative=copy.deepcopy(row['quantitative_data']);quantitative['total_time_hours']=hours
    q=registry.questions[str(row['question_id'])];demand=registry.get(row['question_id'],q['question'])
    with source_key_alias():numeric=runner.calculate_effectiveness_score(quantitative,demand,runner.MODEL_SPACE_SIGNED,{},[])
    return derive({**{k:row['metrics'][k] for k in DIRECT+EGES},'s_time':numeric['s_time']},{k:row['metrics'][k] for k in ['sr','sp']},True),numeric['time_computation']

for row in rows:
    if 'metrics' not in row:results.append(row);continue
    doc=b.read(row['source_document']['path']);post=b.read(row['post_record']['path']);cv=post.get('conversion');recovered=False
    bound.extend([row['source_document'],row['post_record']])
    if not cv and post.get('views',{}).get('time',{}).get('status')=='validated_dependency_view':
        rawref=prior[row['cell_id']]['raw_source'] if a.cohort=='canonical32' else evidence[row['cell_id']]['raw_response']
        payload=b.read(rawref['path']);bound.append(rawref)
        view,audit=components.original.partial.neutral_view(payload,doc,components.ground,['method_mentions','operations','timeline','precedence_edges','total_time_claims'],['t','c','u'])
        assert components.original.j.digest(view)==post['views']['time']['view_sha256']
        cv=components.ground.convert(components.ground.canonical(view),doc);recovered=True
    original=None;mapping=None;docpath=Path(row['source_document']['path'])
    original_path=docpath.parent.parent/'original_source_documents'/docpath.name
    mapping_path=docpath.parent.parent/'source_mappings'/docpath.name
    if original_path.exists() and mapping_path.exists():
        original=b.read(original_path);mapping=b.read(mapping_path);bound.extend([b.bind(original_path),b.bind(mapping_path)])
    candidate_ledger=candidate.build(cv,doc,original,mapping) if cv else None
    metrics=copy.deepcopy(row['metrics']);candidate_point=None;formula=None;conditional=[]
    if candidate_ledger and row.get('quantitative_data'):
        for scenario in candidate_ledger['scenarios']:
            if b.finite(scenario['hours']):
                value,calc=score(row,scenario['hours']);conditional.append({'scenario_id':scenario['scenario_id'],'hours':scenario['hours'],'metrics':value,'formula':calc})
        if candidate_ledger['single_unbranched_point']:
            candidate_point,formula=score(row,candidate_ledger['hours']);metrics=candidate_point
    stable=DIRECT+['sr','sp','Com','Cor','s_method','s_trans','s_label']
    assert all(metrics[k]==row['metrics'][k] for k in stable)
    results.append({**row,'baseline_metrics':row['metrics'],'metrics':metrics,'candidate_point_metrics':candidate_point,
        'time_candidate_ledger':candidate_ledger,'time_formula':formula,'conditional_time_results':conditional,
        'time_dependency_view_reconstructed':recovered,'candidate_point_applied':candidate_point is not None,
        'complete_numeric_CCE':b.complete(metrics),'time_changes':{k:{'before':row['metrics'][k],'after':v} for k,v in metrics.items() if v!=row['metrics'][k]}})

actual=[r for r in results if 'metrics' in r]
unique={r['path']:r for r in bound}
for path,ref in unique.items():assert b.bind(path)==ref
assert b.bind(ledger)==ledger_before
summary={'cohort':a.cohort,'saved_returns':len(actual),
    'unbranched_candidate_point_count':sum(r['candidate_point_applied'] for r in actual),
    's_time_available_before':sum(b.finite(r['baseline_metrics']['s_time']) for r in actual),
    's_time_available_after':sum(b.finite(r['metrics']['s_time']) for r in actual),
    'complete_before':sum(b.complete(r['baseline_metrics']) for r in actual),'complete_after':sum(b.complete(r['metrics']) for r in actual),
    'changed':[r['cell_id'] for r in actual if r['time_changes']],
    'candidate_not_applied':[{'cell_id':r['cell_id'],'issues':r['time_candidate_ledger']['issues'] if r['time_candidate_ledger'] else ['saved_time_dependency_unavailable'],
        'finite_scenarios':len(r['conditional_time_results'])} for r in actual if not r['candidate_point_applied']],
    'new_model_calls':0,'new_per_answer_author_annotations':0,'scientific_accuracy_claimed':False}
b.save(a.out/'results.json',results);b.save(a.out/'summary.json',summary)
b.save(a.out/'manifest.json',{'command':[sys.executable,*sys.argv],'bindings':list(unique.values()),'ledger':ledger_before,'new_model_calls':0,'version':candidate.VERSION})
(a.out/'code_snapshot').mkdir()
for file in [Path(__file__),Path(candidate.__file__)]: (a.out/'code_snapshot'/file.name).write_bytes(file.read_bytes())
with (a.out/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=['cell_id','cohort','question_id','candidate_point_applied','complete_numeric_CCE']+DIRECT+EGES+['sr','sp','Com','Cor','Eff','IA','HV']
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    for r in actual:writer.writerow({**{k:r[k] for k in fields if k in r},**r['metrics']})
print(json.dumps({k:v for k,v in summary.items() if k!='candidate_not_applied'},ensure_ascii=False,indent=2))
