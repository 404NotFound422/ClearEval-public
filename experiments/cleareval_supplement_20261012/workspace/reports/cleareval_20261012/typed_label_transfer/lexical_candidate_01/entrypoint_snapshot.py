"""Reparse 32 archived responses with a lexical candidate; never call a model."""
import copy
import csv
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
DEST=OUT/'lexical_candidate_01'
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
sys.path.insert(0,str(ROOT/'scripts'))
import cce_multilingual_name_boundary_v1 as lexical
import cce_canonical_components_v1 as processor
import cce_typed_label_scorer_v2 as typed
import cce_reported_operation_scope_v1 as scope
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES
from cce_scales_source_key_alias_v1 import source_key_alias
b=typed.base
rows=b.read(OUT/'scope_candidate_02/results.json')
policy=b.read(OUT.parent/'typed_label_revision/policy_with_sources.json')
config=b.read(OUT.parent/'scorer_revision/config.json')
plan={'entrypoint':b.bind(__file__),'lexical':b.bind(lexical.__file__),'source_scope':b.bind(scope.__file__),
    'typed_scorer':b.bind(typed.__file__),'inputs':b.bind(OUT/'scope_candidate_02/results.json'),
    'config':b.bind(OUT.parent/'scorer_revision/config.json'),'policy':b.bind(OUT.parent/'typed_label_revision/policy_with_sources.json'),
    'new_model_calls':0,'case_specific_source_annotations':0,'status':'exploratory_archived_response_reparse'}
if (DEST/'plan.json').exists():assert b.read(DEST/'plan.json')==plan
else:b.save(DEST/'plan.json',plan)
checks=[]
def check(name,passed):
    if not passed:raise AssertionError(name)
    checks.append({'name':name,'passed':True})

# Test lexical counterexamples before replay. They are not biological truth data.
def inventory(text,literal):
    doc=lexical.backend.document(text+'\n','lexical_synthetic')
    support=lexical.backend.resolve({'unit_id':'L0001'},doc)
    return lexical.name_occurrence_inventory(literal,support,doc)
for text,literal,accept in [
    ('置于BABB中','BABB',True),('TO-PRO-3 1–2 µM','TO-PRO-3',True),
    ('TO-PRO-3 0.5 µM','TO-PRO-3',True),('TO-PRO-3 1–2','TO-PRO-3',False),
    ('Alexa Fluor 647','Alexa Fluor',False),('GFP2','GFP',False),
    ('EGFP','GFP',False),('anti-GFP','GFP',False),('抗GFP','GFP',False),
    ('GFP+','GFP',False),('C-FoS','c-Fos',False),('于BABB和BABB中','BABB',False)]:
    check('lexical:'+text+':'+literal,bool(inventory(text,literal)['complete_occurrences'])==accept)
text='于BABB中; BABB.';inv=inventory(text,'BABB')
check('old_valid_ordinal_not_shifted',inv['complete_occurrences'][0]['start']==text.rindex('BABB'))

runner,registry=b.runtime();cases={};cells={}
for cohort in {r['cohort'] for r in rows}:
    batch=R3/cohort
    payload=b.read(batch/'cases.json');values=payload['cases'] if isinstance(payload,dict) else payload
    cases.update({c['case_id']:c for c in values})
    cells.update({c['planned_trial_id']:c for c in b.read(batch/'matrix.json')})
results=[]
for row in rows:
    oldpost=b.read(row['source_record']['path']);doc=b.read(row['source_document']['path'])
    raw_path=Path(row['source_record']['path']).parent/'raw_response.txt'
    raw=raw_path.read_text(encoding='utf-8')
    check('raw_hash:'+row['cell_id'],b.bind(raw_path)['sha256']==oldpost['raw_sha256'])
    with lexical.use_candidate() as wiring:
        post=processor.independent_processing(raw,doc,cases[row['case_id']],cells[row['saved_trial_id']]['step'])
    check('candidate_binding_restored:'+row['cell_id'],lexical.backend.name_occurrence_inventory is lexical.ORIGINAL)
    check('existing_finite_primary_values:'+row['cell_id'],all(post['metrics'][k]==v
          for k,v in row['primary_metrics'].items() if b.finite(v)))
    if oldpost.get('conversion'):
        check('successful_conversion_retained:'+row['cell_id'],bool(post.get('conversion')))
    staged=typed.replay_row({**row,'metrics':post['metrics']},post,policy,config,runner,registry,doc=doc)
    metric=staged['metrics'];time=None;changed=[];label=staged.get('label_derivation')
    if post.get('conversion'):
        candidate=copy.deepcopy(post)
        candidate['conversion']['label_occurrence_projection'],changed=scope.repeated_secondary_projection(post['conversion'],doc,policy)
        staged=typed.replay_row({**row,'metrics':metric},candidate,policy,config,runner,registry,doc=doc)
        metric=staged['metrics'];label=staged.get('label_derivation')
        time=scope.time_interpretation(post['conversion'],doc,post['numeric']['quantitative_data']['total_time_hours'])
        if b.finite(time['hours']) and metric['s_time'] is None:
            with source_key_alias():
                calc=runner.calculate_effectiveness_score({**post['numeric']['quantitative_data'],'total_time_hours':time['hours']},
                    post['numeric']['user_preference_vector'],runner.MODEL_SPACE_SIGNED,{},[])
            metric=derive({**{k:metric[k] for k in DIRECT+EGES},'s_time':calc['s_time']},{k:metric[k] for k in ['sr','sp']},True)
            time['original_numeric_time_computation']=calc['time_computation']
    previous=row['scope_candidate_metrics']
    check('previous_scoped_finite_values:'+row['cell_id'],all(metric[k]==v for k,v in previous.items() if b.finite(v)))
    saved=None
    if row['original_status']=='partial':
        saved=DEST/'processing'/(row['cell_id']+'.json');b.save(saved,post)
    result={**row,'lexical_candidate_metrics':metric,'lexical_full_conversion':post['full_conversion_success'],
        'lexical_post':b.bind(saved) if saved else None,'lexical_label_derivation':label,
        'lexical_time_interpretation':time,'lexical_relation_resolution':changed,
        'lexical_failure':post.get('full_conversion_or_scoring_failure'),'lexical_wiring':wiring,
        'lexical_changes':{k:{'before':previous[k],'after':v} for k,v in metric.items() if v!=previous[k]},
        'raw_source':b.bind(raw_path),'new_model_calls':0}
    results.append(result)
    if row['original_status']=='partial':print(json.dumps({k:result[k] for k in ['cell_id','lexical_full_conversion','lexical_failure','lexical_changes']},ensure_ascii=False))
b.save(DEST/'results.json',results)
summary=[]
for cohort in sorted({r['cohort'] for r in rows}):
    subset=[r for r in results if r['cohort']==cohort]
    summary.append({'cohort':cohort,'returns':len(subset),'complete_CCE':sum(b.complete(r['lexical_candidate_metrics']) for r in subset),
        'full_conversion':sum(r['lexical_full_conversion'] for r in subset),
        'label_available':sum(b.finite(r['lexical_candidate_metrics']['s_label']) for r in subset),
        'time_available':sum(b.finite(r['lexical_candidate_metrics']['s_time']) for r in subset)})
b.save(DEST/'summary.json',summary)
b.save(DEST/'verification.json',{'checks':checks,'passed':len(checks),'new_model_calls':0})
with (DEST/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['cohort','cell_id','original_status','lexical_full_conversion',*results[0]['metrics']])
    writer.writeheader()
    for r in results:writer.writerow({k:r[k] for k in ['cohort','cell_id','original_status','lexical_full_conversion']}|r['lexical_candidate_metrics'])
b.save(DEST/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0})
print(json.dumps({'summary':summary,'checks_passed':len(checks)},ensure_ascii=False))
