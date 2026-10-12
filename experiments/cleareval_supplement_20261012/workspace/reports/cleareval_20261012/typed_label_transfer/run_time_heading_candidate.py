"""Replay time-scope corrections uniformly and retain all preceding results."""
import copy
import csv
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
DEST=OUT/'time_heading_candidate_01'
sys.path.insert(0,str(ROOT/'scripts'))
import cce_time_heading_scope_v1 as time_scope
import cce_typed_label_scorer_v2 as typed
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES
from cce_scales_source_key_alias_v1 import source_key_alias
b=typed.base
rows=b.read(OUT/'lexical_candidate_02/results.json')
plan={'entrypoint':b.bind(__file__),'time_scope':b.bind(time_scope.__file__),'base_scope':b.bind(time_scope.previous.__file__),
    'inputs':b.bind(OUT/'lexical_candidate_02/results.json'),
    'original_rubric':b.bind(ROOT/'prompts/eval_oeq_teacher_rubric.txt'),
    'new_model_calls':0,'new_per_answer_author_annotations':0,
    'scope':'exploratory original-rubric time interpretation on 32 archived returns'}
if (DEST/'plan.json').exists():assert b.read(DEST/'plan.json')==plan
else:b.save(DEST/'plan.json',plan)
runner,registry=b.runtime();results=[];checks=[]
def check(name,passed):
    if not passed:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
for row in rows:
    record=row.get('lexical_post') or row['source_record']
    post=b.read(record['path']);doc=b.read(row['source_document']['path'])
    metric=copy.deepcopy(row['lexical_candidate_metrics']);time=None
    if post.get('conversion'):
        time=time_scope.time_interpretation(post['conversion'],doc,post['numeric']['quantitative_data']['total_time_hours'])
        if b.finite(time['hours']):
            with source_key_alias():
                calc=runner.calculate_effectiveness_score({**post['numeric']['quantitative_data'],'total_time_hours':time['hours']},
                    post['numeric']['user_preference_vector'],runner.MODEL_SPACE_SIGNED,{},[])
            metric=derive({**{k:metric[k] for k in DIRECT+EGES},'s_time':calc['s_time']},{k:metric[k] for k in ['sr','sp']},True)
            time['original_numeric_time_computation']=calc['time_computation']
    check('non_time_components_preserved:'+row['cell_id'],all(metric[k]==row['lexical_candidate_metrics'][k]
          for k in DIRECT+['s_method','s_label','s_trans','sr','sp','Com','Cor']))
    if row['cohort']=='E2_canonical_qwen_01':
        check('E2_results_unchanged:'+row['cell_id'],metric==row['scope_candidate_metrics'])
    result={**row,'final_candidate_metrics':metric,'final_time_interpretation':time,
        'time_heading_changes':{k:{'before':row['lexical_candidate_metrics'][k],'after':v}
            for k,v in metric.items() if v!=row['lexical_candidate_metrics'][k]}}
    results.append(result);b.save(DEST/'records'/(row['cell_id']+'.json'),result)
byid={r['cell_id']:r for r in results}
check('R3C08_reported_core_32_hours',byid['R3C08__r0']['final_time_interpretation']['hours']==32)
check('R3C02_optional_core_branch_stays_unknown',byid['R3C02__r0']['final_time_interpretation']['hours'] is None)
check('R3C03_truncated_stays_unknown',byid['R3C03__r0']['final_candidate_metrics']['s_time'] is None)
row=byid['R3C08__r0'];post=b.read(row['source_record']['path']);doc=b.read(row['source_document']['path'])
item=next(x for x in post['conversion']['source_audit']['inventory'] if x.get('kind')=='operation_record_lead'
          and x.get('coverage_state')!='covered_operation_record')
broken=copy.deepcopy(post['conversion']);broken['source_audit']['resolved']['operations']=[]
check('bare_heading_without_recorded_children_not_ignored',not time_scope.title_evidence(item,broken,doc)['supported'])
changes=row['final_time_interpretation']['heading_scope_candidate']['changes']
wash=next(c for c in changes if c['rule']=='exclude_routine_antibody_labeling_washes_per_original_rubric')
check('seven_label_washes_only_exclude_42_hours',len(wash['removed_contributions'])==7
      and sum(x['lower_hours'] for x in wash['removed_contributions'])==42)
check('clearing_transition_wash_not_excluded',all(x['operation_id'] not in {'OP8','OP9','OP10','OP11','OP12'} for x in wash['removed_contributions']))
source_index=b.read(OUT.parent/'missing_score_diagnosis/evidence.json')['records']
for i in [3,7,11]:
    source=next(r for r in source_index if r['cell_id']==f'E2_{i:02d}__local_qwen27b_q8_development__r0')
    p=b.read(source['posthoc_record']['path']);d=b.read(source['source_document']['path'])
    check('deleted_duration_stays_unknown:'+str(i),time_scope.time_interpretation(p['conversion'],d,p['numeric']['quantitative_data']['total_time_hours'])['hours'] is None)
b.save(DEST/'results.json',results)
summary=[]
for cohort in sorted({r['cohort'] for r in results}):
    subset=[r for r in results if r['cohort']==cohort]
    summary.append({'cohort':cohort,'returns':len(subset),'full_conversion':sum(r['lexical_full_conversion'] for r in subset),
        'complete_CCE':sum(b.complete(r['final_candidate_metrics']) for r in subset),
        'label_available':sum(b.finite(r['final_candidate_metrics']['s_label']) for r in subset),
        'time_available':sum(b.finite(r['final_candidate_metrics']['s_time']) for r in subset)})
b.save(DEST/'summary.json',summary)
b.save(DEST/'verification.json',{'checks':checks,'checks_passed':len(checks)})
with (DEST/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['cohort','cell_id','original_status','lexical_full_conversion',*results[0]['metrics']])
    writer.writeheader()
    for r in results:writer.writerow({k:r[k] for k in ['cohort','cell_id','original_status','lexical_full_conversion']}|r['final_candidate_metrics'])
b.save(DEST/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0})
print(json.dumps({'summary':summary,'checks_passed':len(checks),'changed':[
    {'cell_id':r['cell_id'],'changes':r['time_heading_changes']} for r in results if r['time_heading_changes']]},ensure_ascii=False,indent=2))
