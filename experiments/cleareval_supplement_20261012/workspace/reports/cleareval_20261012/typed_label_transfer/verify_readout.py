"""Check source-scope replay and summarize the actual paired archived returns."""
import copy
import csv
import itertools
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
DEST=OUT/'scope_candidate_02'
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
sys.path.insert(0,str(ROOT/'scripts'))
import cce_reported_operation_scope_v1 as scope
import cce_typed_label_scorer_v2 as typed
b=typed.base
rows=b.read(DEST/'results.json')
actual={r['cell_id']:r for r in rows}
checks=[]


def check(name,ok,detail=None):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True,'detail':detail})


def sources(identifier):
    row=actual[identifier]
    return b.read(row['source_record']['path']),b.read(row['source_document']['path'])


def csv_write(path,items):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(items[0]));writer.writeheader();writer.writerows(items)


# Ground truth for these checks is the archived payload, not a rewritten answer.
bindings={x['path']:x for x in b.read(OUT/'actual_01/source_bindings.json')}
for row in rows:
    for key in ['source_record','source_document','trial']:
        binding=row[key];bindings[binding['path']]=binding
check('all_bound_source_and_raw_files_unchanged',all(b.bind(p)==v for p,v in bindings.items()),len(bindings))
unchanged=typed.DIRECT+['s_method','s_trans','sr','sp','Com','Cor']
check('non_target_metrics_exactly_preserved',all(r['scope_candidate_metrics'][k]==r['primary_metrics'][k]
      for r in rows for k in unchanged),len(rows)*len(unchanged))
check('old_finite_time_values_preserved',all(r['scope_candidate_metrics']['s_time']==r['primary_metrics']['s_time']
      for r in rows if b.finite(r['primary_metrics']['s_time'])))
first=b.read(OUT/'scope_candidate_01/results.json')
check('duplicate_reference_robustness_fix_does_not_change_actual_results',all(a['scope_candidate_metrics']==z['scope_candidate_metrics']
      for a,z in zip(first,rows)))
for row in rows:
    trial=b.read(row['trial']['path'])
    check('original_terminal_state_preserved:'+row['cell_id'],trial['status']==row['original_status'])

# Deleting a duration remains different from deleting an entire workflow module.
old_index=b.read(OUT.parent/'missing_score_diagnosis/evidence.json')['records']
for number in [3,7,11]:
    identifier=f'E2_{number:02d}__local_qwen27b_q8_development__r0'
    source=next(r for r in old_index if r['cell_id']==identifier)
    post=b.read(source['posthoc_record']['path']);doc=b.read(source['source_document']['path'])
    outcome=scope.time_interpretation(post['conversion'],doc,post['numeric']['quantitative_data']['total_time_hours'])
    check('deleted_duration_not_invented:'+identifier,outcome['hours'] is None)
check('truncated_answer_retains_missing_time',actual['R3C03__r0']['scope_candidate_metrics']['s_time'] is None)
check('optional_route_not_silently_selected',actual['R3C02__r0']['scope_candidate_metrics']['s_time'] is None)
check('unclassified_source_actions_not_ignored',actual['R3C08__r0']['scope_candidate_metrics']['s_time'] is None)
check('unknown_durations_not_filled',actual['R3C05__r0']['scope_candidate_metrics']['s_time'] is None)
check('source_scoped_144_hours_supported',actual['R3C06__r0']['scope_time_interpretation']['hours']==144)
for q,h in [(2,60),(21,36),(22,20)]:
    r=actual[f'R3E2_Q{q:03d}_necessary_step_deletion__r0']
    check('module_deletion_reported_hours_and_unknown_endpoint:'+str(q),r['scope_time_interpretation']['hours']==h
          and r['scope_time_interpretation']['complete_experimental_endpoint_duration'] is None)
for q in [21,22]:
    value=actual[f'R3E2_Q{q:03d}_necessary_step_deletion__r0']['scope_candidate_metrics']['s_time']
    check('small_positive_not_zeroed:'+str(q),0<value<1e-20,value)

# Source-heading counterexample: an explicit core phase must not be excluded
# because an upstream phase classifier happened to call it preparation.
for heading,expected in [('Immunolabeling',True),('Delipidation',False),('Clearing and staining',False)]:
    text=heading+'\nIncubation with solution\n'
    start=text.index('Incubation')
    operation={'operation':{'start':start,'end':len(text),'quote':text[start:]}}
    result=scope.preparation_evidence(operation,{'text':text})
    check('heading_scope_counterexample:'+heading,result['supported']==expected)

# Relationship counterexamples are modified copies, not additional experiments.
post,doc=sources('R3E2_Q022_necessary_step_deletion__r0')
conv=post['conversion'];policy=b.read(OUT.parent/'typed_label_revision/policy_with_sources.json')
projection,changed=scope.repeated_secondary_projection(conv,doc,policy)
check('actual_repeated_secondary_has_single_existing_channel',len(changed)==1 and changed[0]['sole_source_target']=='MAP2')
ambiguous=copy.deepcopy(conv)
ambiguous['source_audit']['resolved']['entities'].append({'id':'synthetic_other_target','kind':'target','usage':'used','literal_name':'TH'})
check('different_used_target_prevents_unique_channel_inference',not scope.repeated_secondary_projection(ambiguous,doc,policy)[1])
partial=copy.deepcopy(conv);partial['source_audit']['resolved']['coverage']['entities']='partial'
check('unknown_entity_coverage_not_treated_as_single_target',not scope.repeated_secondary_projection(partial,doc,policy)[1])
conflict=copy.deepcopy(conv)
for pair in conflict['label_occurrence_projection']['pairs']:
    if pair['kind']=='unresolved_relation':pair['same_occurrence_distinct_target_conflict']=True
check('explicit_conflict_not_collapsed',not scope.repeated_secondary_projection(conflict,doc,policy)[1])
different=copy.deepcopy(conv)
for pair in different['label_occurrence_projection']['pairs']:
    if pair['kind']=='unresolved_relation':pair['fluor_literal']='Alexa Fluor 594'
check('different_fluorophore_not_resolved_by_another_channel',not scope.repeated_secondary_projection(different,doc,policy)[1])
duplicates=copy.deepcopy(conv)
unknown=next(p for p in duplicates['label_occurrence_projection']['pairs'] if p['kind']=='unresolved_relation')
for n in range(3):
    extra=copy.deepcopy(unknown);extra['pair_id']='synthetic_repeat_'+str(n)
    duplicates['label_occurrence_projection']['pairs'].append(extra)
left=scope.repeated_secondary_projection(duplicates,doc,policy)
duplicates['label_occurrence_projection']['pairs'].reverse()
right=scope.repeated_secondary_projection(duplicates,doc,policy)
semantic=lambda item:sorted((p['pair_id'],p['kind'],p.get('marker_literal')) for p in item['pairs'])
check('several_references_order_invariant',len(left[1])==4 and len(right[1])==4 and semantic(left[0])==semantic(right[0]))
check('replay_did_not_modify_original_conversion',post==b.read(actual['R3E2_Q022_necessary_step_deletion__r0']['source_record']['path']))

bytrial={r['saved_trial_id']:r for r in rows}
pairs=[]
for source in b.read(R3/'E2_canonical_readout_complete_01/paired_results.json'):
    left,right=[bytrial[source[k]] for k in ['baseline_trial_id','variant_trial_id']]
    values=[r['scope_candidate_metrics'] for r in [left,right]]
    result={k:source[k] for k in ['pair_id','question_id','condition','repeat_index','scientific_necessity','expected']}
    result.update(baseline_cell_id=left['cell_id'],variant_cell_id=right['cell_id'],
        both_complete_CCE=all(b.complete(m) for m in values),
        original_fulltexts_different=left['original_answer_sha256']!=right['original_answer_sha256'],
        canonical_fulltexts_identical=left['answer_sha256']==right['answer_sha256'])
    for metric in values[0]:
        a,z=[m[metric] for m in values]
        result['baseline_'+metric]=a;result['variant_'+metric]=z
        result['delta_'+metric]=z-a if b.finite(a) and b.finite(z) else None
    pairs.append(result)
check('18_real_paired_observations_complete',len(pairs)==18 and all(p['both_complete_CCE'] for p in pairs))
check('all_variants_bind_different_submitted_fulltexts',all(p['original_fulltexts_different'] for p in pairs))
csv_write(DEST/'controlled_pairs.csv',pairs);b.save(DEST/'controlled_pairs.json',pairs)

# Repeat groups are answer x metric. The two repetitions are not independent
# tasks; canonical-equivalent inputs are not intrinsic model robustness tests.
groups=defaultdict(list)
for row in rows:
    if row['cohort']=='E2_canonical_qwen_01':groups[row['anonymous_answer_id']].append(row)
repeats=[]
for answer,group in groups.items():
    check('exactly_two_original_requests:'+answer,len(group)==2)
    for metric in group[0]['scope_candidate_metrics']:
        values=[r['scope_candidate_metrics'][metric] for r in group]
        repeats.append({'answer':answer,'metric':metric,'numeric_count':sum(b.finite(v) for v in values),
            'range':max(values)-min(values) if all(b.finite(v) for v in values) else None,
            'values':json.dumps(values),'new_repeat_calls':0})
csv_write(DEST/'repeat_groups.csv',repeats)

# For n=3 tasks, all 27 ordered bootstrap draws can be enumerated. The 2000
# simulations are retained only to connect to prior reporting, never as n=2000.
resampling=[]
for condition in sorted({p['condition'] for p in pairs}):
    for metric in ['sr','sp','Com','Cor','Eff','IA','HV']:
        task_values={}
        for q in sorted({p['question_id'] for p in pairs}):
            vals=[p['delta_'+metric] for p in pairs if p['condition']==condition and p['question_id']==q]
            task_values[str(q)]=statistics.mean(vals)
        values=list(task_values.values());n=len(values)
        exact=sorted(statistics.mean(draw) for draw in itertools.product(values,repeat=n))
        rng=random.Random(20261012)
        sampled=sorted(statistics.mean(rng.choices(values,k=n)) for _ in range(2000))
        percentile=lambda arr,p:arr[max(0,math.ceil(p*len(arr))-1)]
        resampling.append({'condition':condition,'metric':metric,'distinct_tasks':n,'task_mean_deltas':task_values,
            'mean_delta':statistics.mean(values),'exact_ordered_draws':len(exact),
            'exact_percentile_2_5':percentile(exact,.025),'exact_percentile_97_5':percentile(exact,.975),
            'simulation_draws':2000,'seed':20261012,'simulation_percentile_2_5':percentile(sampled,.025),
            'simulation_percentile_97_5':percentile(sampled,.975),
            'interpretation':'descriptive three-task paired sensitivity; source-family independence is not established; no population guarantee or new model calls'})
b.save(DEST/'paired_task_resampling.json',resampling)

condition_summary=[]
for condition in sorted({p['condition'] for p in pairs}):
    subset=[p for p in pairs if p['condition']==condition]
    condition_summary.append({'condition':condition,'actual_paired_observations':len(subset),
        'distinct_task_pairs':len({p['question_id'] for p in subset}),
        'all_direct_equal':sum(all(p['delta_'+k]==0 for k in typed.DIRECT) for p in subset),
        'all_EGES_equal':sum(all(p['delta_'+k]==0 for k in typed.EGES) for p in subset),
        'all_CCE_equal':sum(all(p['delta_'+k]==0 for k in ['Com','Cor','Eff','IA','HV']) for p in subset),
        'SR_SP_equal':sum(all(p['delta_'+k]==0 for k in ['sr','sp']) for p in subset),
        'HV_decreases':sum(p['delta_HV']<0 for p in subset),
        'by_task':[{'question_id':p['question_id'],**{k:p[k] for k in p if k.startswith('delta_')}}
                   for p in subset if p['repeat_index']==0]})
summary={'candidate':scope.VERSION,'archived_returns':len(rows),'new_calls':0,
    'complete_CCE_definition':'finite Com, Cor, Eff, IA, HV under explicitly declared reported-operation scope',
    'not_new_prospective_confirmation':True,'conditions':condition_summary,
    'original_answer_texts':len({r['original_answer_sha256'] for r in rows}),
    'canonical_answer_texts':len({r['answer_sha256'] for r in rows}),
    'repeat_groups':{'core_metric_groups':len([r for r in repeats if r['metric'] in typed.DIRECT+typed.EGES]),
        'all_16_metric_groups':len(repeats),'all_numeric':sum(r['numeric_count']==2 for r in repeats),
        'exact_zero_range':sum(r['range']==0 for r in repeats),'original_requests':24,'new_requests':0},
    'remaining_confirmation':[{'cell_id':r['cell_id'],'missing':[k for k in ['Cor',*typed.EGES] if r['scope_candidate_metrics'][k] is None],
        'original_status':r['original_status'],'time_issues':(r.get('scope_time_interpretation') or {}).get('issues')}
        for r in rows if r['cohort']=='confirmation_qwen_01' and not b.complete(r['scope_candidate_metrics'])],
    'checks_passed':len(checks),'source_files_verified':len(bindings)}
b.save(DEST/'verification.json',{'entrypoint':b.bind(__file__),'checks':checks,'source_bindings':list(bindings.values())})
b.save(DEST/'readout.json',summary)
b.save(DEST/'readout_execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0,'results':b.bind(DEST/'results.json')})
print(json.dumps(summary,ensure_ascii=False,indent=2))
