"""Replay the same source-only label candidate over two archived cohorts."""
import argparse,copy,csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
BASE=Path(__file__).resolve().parent.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
import cce_selected_label_source_v1 as candidate
import cce_scoped_midpoint_scorer_v1 as b
import cce_typed_label_scorer_v2 as typed
from cce_grounded_offline_scoring_v1 import DIRECT,EGES,derive
from cce_scales_source_key_alias_v1 import source_key_alias

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--cohort',choices=['canonical32','archived67'],required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();assert not a.out.exists()
policy_path=BASE/'typed_label_revision/policy_with_sources.json';config_path=BASE/'scorer_revision/config.json'
policy,config=b.read(policy_path),b.read(config_path)
source_path=BASE/('semantic_source_revision/method_candidate_02/results.json' if a.cohort=='canonical32' else 'typed_label_revision/with_pair_sources/results.json')
rows=b.read(source_path);sources={r['cell_id']:r for r in b.read(BASE/'missing_score_diagnosis/evidence.json')['records']}
runner,registry=b.runtime();results=[];checks=[];bindings=[b.bind(x) for x in [__file__,candidate.__file__,policy_path,config_path,source_path,typed.__file__,ROOT/'OEQ_run_grading_new.py',ROOT/'KnowledgeBase/tissue.json']]
ledger_path=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl';ledger=ledger_path.read_bytes()

for row in rows:
    if a.cohort=='archived67' and row.get('status')=='no_saved_return':
        results.append({'cell_id':row['cell_id'],'status':'no_saved_return','source_row':row});continue
    old=copy.deepcopy(row['method_candidate_metrics'] if a.cohort=='canonical32' else row['metrics'])
    docref=row.get('source_document') or sources[row['cell_id']]['source_document']
    doc=b.read(docref['path']);assert b.bind(docref['path'])==docref
    postref=(row.get('lexical_post') or row['source_record']) if a.cohort=='canonical32' else sources[row['cell_id']]['posthoc_record']
    post=b.read(postref['path']);assert b.bind(postref['path'])==postref
    bindings.extend([docref,postref])
    proposal=candidate.extract(doc,policy);metric=copy.deepcopy(old);label=None;trace=[]
    q=registry.questions[str(row['question_id'])];meta=runner.QUESTION_META_KB[q['question_id']]
    quantitative=copy.deepcopy(row.get('method_candidate_quantitative_data') or row.get('quantitative_data'))
    if quantitative is None and post.get('views',{}).get('method',{}).get('projected_extraction'):
        quantitative={'method_name':post['views']['method']['projected_extraction']['method_name'],
            'tissue_ri_value':meta.get('tissue_ri_value'),'sample_tier':meta.get('tissue_tier_code'),'total_time_hours':None}
    decision='candidate_outside_declared_grammar'
    if proposal['ready'] and quantitative:
        projection=typed.project_annotation(proposal,doc)
        demand=registry.get(row['question_id'],q['question'])
        with source_key_alias(),typed.using_lookup(runner,meta['marker_query_targets'],config.get('task_marker_scopes',{}).get(str(row['question_id']),{}),policy) as trace:
            label=typed.score_labels(projection,runner,quantitative,demand,meta['marker_query_targets'],policy,{},doc)
        # This is an independently calculated candidate, not a zero/NA replacement
        # hidden in the prior result. Keep both values and all dependency evidence.
        metric=derive({**{k:old[k] for k in DIRECT+EGES},'s_label':label['s_label']},{k:old[k] for k in ['sr','sp']},True)
        decision='source_rule_applied'
    elif proposal['ready']:decision='selected_method_dependency_unavailable'
    assert all(metric[k]==old[k] for k in DIRECT+['sr','sp','s_method','s_trans','s_time','Com','Cor'])
    for relation in proposal['relations']:
        for span in relation['source_spans']:b.verify_span(doc['text'],span)
    changes={k:{'before':old[k],'after':v} for k,v in metric.items() if v!=old[k]}
    results.append({'cell_id':row['cell_id'],'cohort':row['cohort'],'question_id':row['question_id'],
        'baseline_metrics':old,'metrics':metric,'complete_numeric_CCE':b.complete(metric),
        'source_document':docref,'post_record':postref,'answer_sha256':doc['answer_sha256'],
        'proposal':proposal,'decision':decision,'label_derivation':label,'lookup_trace':trace,
        'changes':changes,'quantitative_data':quantitative,'new_model_calls':0,'new_per_answer_author_annotations':0})
    checks.append({'cell_id':row['cell_id'],'original_direct_SR_SP_and_other_EGES_unchanged':True,'all_source_spans_match':True})

actual=[r for r in results if 'metrics' in r]
assert ledger_path.read_bytes()==ledger
unique={x['path']:x for x in bindings}
for path,ref in unique.items():assert b.bind(path)==ref
summary={'cohort':a.cohort,'actual_saved_returns':len(actual),'distinct_sources':len({r['answer_sha256'] for r in actual}),
    'ready_source_lists':sum(r['proposal']['ready'] for r in actual),'automatically_applied':sum(r['decision']=='source_rule_applied' for r in actual),
    'label_available_before':sum(b.finite(r['baseline_metrics']['s_label']) for r in actual),
    'label_available_after':sum(b.finite(r['metrics']['s_label']) for r in actual),
    'complete_before':sum(b.complete(r['baseline_metrics']) for r in actual),
    'complete_after':sum(b.complete(r['metrics']) for r in actual),
    'changed_cells':[r['cell_id'] for r in actual if r['changes']],
    'complete_lost':[r['cell_id'] for r in actual if b.complete(r['baseline_metrics']) and not b.complete(r['metrics'])],
    'new_model_calls':0,'new_per_answer_author_annotations':0,
    'interpretation':'development replay on exposed source texts; source rule agreement is not independent accuracy or new evaluator repeatability'}
b.save(a.out/'results.json',results);b.save(a.out/'summary.json',summary)
b.save(a.out/'verification.json',{'checks':checks,'source_bindings_verified':len(unique),'ledger_unchanged':True,'ledger_sha256':hashlib.sha256(ledger).hexdigest()})
b.save(a.out/'manifest.json',{'command':[sys.executable,*sys.argv],'bindings':list(unique.values()),'new_model_calls':0,'scorer_rules':candidate.VERSION})
(a.out/'code_snapshot').mkdir()
for f in [Path(__file__),Path(candidate.__file__)]: (a.out/'code_snapshot'/f.name).write_bytes(f.read_bytes())
with (a.out/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=['cell_id','cohort','question_id','decision','complete_numeric_CCE']+DIRECT+EGES+['sr','sp','Com','Cor','Eff','IA','HV']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in actual:w.writerow({**{k:r[k] for k in fields if k in r},**r['metrics']})
print(json.dumps(summary,ensure_ascii=False,indent=2))
