"""Semantic boundary fixtures and checks against unchanged archived evidence."""
import hashlib,json,math,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent;BASE=OUT.parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_source_time_ledger_v1 as c
import cce_scoped_midpoint_scorer_v1 as b
from cce_grounded_offline_scoring_v1 import DIRECT,EGES
checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
def fixture(lines,mode='serial'):
    text='';units=[];ops=[]
    for i,(line,phase) in enumerate(lines):
        line+='\n';unit={'unit_id':f'L{i+1:04d}','start':len(text),'end':len(text)+len(line),'text':line};units.append(unit);text+=line
        if phase:ops.append({'id':f'O{len(ops)+1}','operation':{**{k:unit[k] for k in ['unit_id','start','end']},'quote':line},
            'phase':phase,'execution_scope':'initial','duration':None,'parsed_duration':{'bounds_hours':None},'repeat_count':1})
    doc={'text':text,'units':units,'answer_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
    cv={'source_audit':{'resolved':{'operations':ops,'timeline':{'mode':mode}},'inventory':[]}}
    return cv,doc
def calc(lines,mode='serial'):
    cv,d=fixture(lines,mode);return c.build(cv,d)
def one(text):return calc([(text,'clearing_treatment')])
def times(result):return sorted(s['hours'] for s in result['scenarios'] if s['hours'] is not None)

check('hours_days_minutes_units',calc([('Incubate. (Time: 2 days)','clearing_treatment'),('Equilibrate. (Time: 30 min)','ri_matching')])['hours']==48.5)
check('finite_range_midpoint',one('Incubate. (Time: 2–4 hours)')['hours']==3)
check('numeric_multiplication',one('Incubate. (Time: 2 × 1.5 hours)')['hours']==3)
check('literal_repeat_twice_means_initial_plus_two',one('Incubate for 1 hour, repeat twice. (Time: 1 hour)')['hours']==3)
check('repeat_once_means_two',one('Incubate for 30 min, repeat once. (Time: 0.5 hours)')['hours']==1)
check('again_separate_operation_is_not_optional',calc([('Incubate. (Time: 1 hour)','ri_matching'),('Again exchange and incubate. (Time: 1 hour)','ri_matching')])['hours']==2)
check('explicit_total_not_multiplied_again',one('重复 1.1 共 6 次（总时间 36 hours）。(Time: 36 hours)')['hours']==36)
check('each_requires_count',one('Incubate. (Time: 2 hours each)')['hours'] is None)
check('missing_duration_not_zero',one('Incubate until clear.')['hours'] is None)
check('overnight_rubric_default',one('Incubate. (Time: overnight)')['hours']==8)
check('numeric_field_precedes_unspecified_overnight',one('Incubate overnight. (Time: 12 hours)')['hours']==12)
check('same_field_overnight_with_numeric_definition',one('Incubate. (Time: overnight, 12 hours)')['hours']==12)
x=one('Incubate. (Time: 4–6 hours or overnight)')
check('disjunction_not_averaged',x['hours'] is None and times(x)==[5,8])
x=calc([('Incubate. (Time: 2 hours)','clearing_treatment'),('If needed, incubate for another 4 hours. (Time: 4 hours)','ri_matching')])
check('optional_branch_enumerated',x['hours'] is None and times(x)==[2,6])
check('compatible_prose_range_explicit_setpoint',one('Incubate until clear (usually 30–60 min). (Time: 1 hour)')['hours']==1)
x=one('Incubate for 2 hours. (Time: 1 hour)')
check('contradictory_prose_does_not_become_one_confident_point',x['hours'] is None and times(x)==[1,2])
check('comma_inside_Time_field_does_not_erase_range',one('Incubate. (Time: until transparent, typically 12–24 hours)')['hours']==18)
check('recurrence_interval_not_added',one('Incubate. (Time: 48 hours, replace every 12 hours)')['hours']==48)
check('one_sided_duration_not_fixed_value',one('Incubate. (Time: at least 2 hours)')['hours'] is None)
check('negative_duration_not_absolute_value',one('Incubate. (Time: -2 hours)')['hours'] is None)
check('labeling_and_storage_excluded',calc([('Incubate antibodies. (Time: 48 hours)','antibody_incubation'),
    ('Incubate clearing reagent. (Time: 2 hours)','clearing_treatment'),('Store. (Time: up to 6 months)','storage')])['hours']==2)
x=calc([('1 一抗孵育',None),('Incubate. (Time: 48 hours)','antibody_incubation'),('2 Washes',None),
    ('Repeat wash six times. (Time: 36 hours)','reagent_transition_wash'),('3 Clearing',None),('Incubate. (Time: 2 hours)','clearing_treatment')])
check('wash_repetition_inherits_labeling_scope',x['hours']==2)
x=calc([('1 Rehydration',None),('Incubate in PBS. (Time: 3 hours)','reagent_transition_wash')])
check('core_transition_PBS_not_dropped',x['hours']==3)
x=calc([('Incubate. (Time: 2 hours)','clearing_treatment'),('Optional rehydrate briefly and stain. (Time: 24 hours)','staining')])
check('optional_mixed_transition_retains_unknown',x['hours'] is None and times(x)==[2] and len(x['scenarios'])==2)
check('parallel_schedule_not_summed_as_serial',calc([('Incubate. (Time: 2 hours)','clearing_treatment')],mode='parallel')['hours'] is None)
cv,doc=fixture([('Incubate until transparent (15–30 min).','ri_matching'),('Store for imaging. (Time: 0.5 hours)','storage')])
original_text='1.1 Incubate until transparent (15–30 min). Store for imaging. (Time: 0.5 hours)\n'
original={'text':original_text,'answer_sha256':hashlib.sha256(original_text.encode('utf-8')).hexdigest(),
    'units':[{'unit_id':'L0001','start':0,'end':len(original_text),'text':original_text}]}
mapping={'evaluation_units_to_original':[{'evaluation_unit_id':u['unit_id'],'original_unit_ids':['L0001']} for u in doc['units']]}
check('original_parent_Time_assigned_once',c.build(cv,doc,original,mapping)['hours']==.5)
fixture_count=len(checks)

can=b.read(OUT/'canonical32_04/results.json');old=b.read(OUT/'archived67_04/results.json')
author={r['cell_id']:r for r in b.read(BASE/'semantic_source_revision/semantic_04/results.json')}
bindings={};span_count=0
for cohort,rows in [('canonical32',can),('archived67',old)]:
    manifest=b.read(OUT/(cohort+'_04')/'manifest.json')
    for ref in manifest['bindings']:bindings[ref['path']]=ref
    for r in rows:
        if 'metrics' not in r:continue
        check('unchanged_components:'+cohort+':'+r['cell_id'],all(r['metrics'][k]==r['baseline_metrics'][k] for k in DIRECT+['sr','sp','Com','Cor','s_method','s_trans','s_label']))
        check('no_existing_time_score_lost:'+cohort+':'+r['cell_id'],not b.finite(r['baseline_metrics']['s_time']) or b.finite(r['metrics']['s_time']))
        t=r.get('time_candidate_ledger')
        if not t:continue
        d=b.read(r['source_document']['path'])
        originalpath=Path(r['source_document']['path']).parent.parent/'original_source_documents'/Path(r['source_document']['path']).name
        originaldoc=b.read(originalpath) if originalpath.exists() else None
        for op in t['operations']:
            b.verify_span(d['text'],op['source']);span_count+=1
            for option in op.get('duration',{}).get('options',[]):
                span=option['source'];sd=originaldoc if originaldoc and span.get('answer_sha256')==originaldoc['answer_sha256'] else d
                b.verify_span(sd['text'],span);span_count+=1
        for s in t['scenarios']:
            ids=[p['operation_id'] for p in s['contributions']]
            check('unique_counted_operations:'+cohort+':'+r['cell_id']+':'+s['scenario_id'],len(ids)==len(set(ids)))
            if s['hours'] is not None:
                lower=sum(p['bounds_hours'][0] for p in s['contributions']);upper=sum(p['bounds_hours'][1] for p in s['contributions'])
                check('exact_midpoint_arithmetic:'+cohort+':'+r['cell_id']+':'+s['scenario_id'],s['hours']==(lower+upper)/2)
for path,ref in bindings.items():check('source_binding:'+path,b.bind(path)==ref)
check('24_controlled_all_metrics_unchanged',all(not r['time_changes'] for r in can if r['cell_id'].startswith('R3E2')))
for cid,hours in [('R3C01__r0',34.5),('R3C04__r0',72),('R3C07__r0',8.5)]:
    r=next(r for r in can if r['cell_id']==cid)
    check('automatic_hours_match_prior_source_reading:'+cid,r['time_candidate_ledger']['hours']==hours)
    check('CCE_equal_prior_source_assisted:'+cid,r['metrics']==author[cid]['source_assisted_metrics'])
for cid in ['E2_03__local_qwen27b_q8_development__r0','E2_07__local_qwen27b_q8_development__r0','E2_11__local_qwen27b_q8_development__r0']:
    r=next(r for r in old if r['cell_id']==cid)
    check('real_duration_deletion_not_imputed:'+cid,r['time_candidate_ledger']['hours'] is None and r['metrics']['s_time'] is None)
r=next(r for r in old if r['cell_id']=='FPC13')
check('real_cumulative_72_not_reset_to_initial_48',r['time_candidate_ledger']['hours']==158 and not r['time_changes'])
check('four_actual_C05_branches',times(next(r for r in can if r['cell_id']=='R3C05__r0')['time_candidate_ledger'])==[14,17,18,21])
check('C08_optional_bleach_changes_time',times(next(r for r in can if r['cell_id']=='R3C08__r0')['time_candidate_ledger'])==[20,32])
check('C02_missing_conditional_transitions_remain_missing',times(next(r for r in can if r['cell_id']=='R3C02__r0')['time_candidate_ledger'])==[34.5])
b.save(OUT/'validation.json',{'checks':checks,'checks_passed':len(checks),'synthetic_boundary_examples':fixture_count,
    'verified_source_spans':span_count,'source_files_verified':len(bindings),'new_model_calls':0,
    'prior_assistant_concordance_not_independent_accuracy':True})
print(json.dumps({'checks_passed':len(checks),'synthetic_examples':fixture_count,'source_spans':span_count,'source_files':len(bindings),'new_model_calls':0}))
