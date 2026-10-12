"""Terminal-only, posthoc source diagnostics for frozen fw3 confirmation.

Read original metrics; never score, repair JSON, or change a frozen pipeline.
A saved valid time dependency view may be reconverted without scoring solely
to recover its source audit, with exact saved projection equality required.
"""
import argparse, collections, copy, csv, hashlib, json, re, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_grounded_extraction_v11 as g
import cce_fieldwise_scoring_v3 as fw
import cce_partial_components_v1 as partial

R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
BATCHES={'first7':('generation_confirmation_v2',7),'secondary8':('secondary_E5_confirmation_v1',8)}
FW_SHA='91d6dace49137e639e79acd0615977adead24dce6fda9328059c883e8ec470ce'
METRICS=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_time','s_trans','sr','sp','Com','Cor','Eff','IA','HV']
INPUTS={}
def require(x,m):
 if not x:raise AssertionError(m)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):
 p=Path(p).resolve();r={'path':str(p),'sha256':sha(p)};INPUTS[str(p)]=r;return r
def read(p):bind(p);return json.loads(Path(p).read_text(encoding='utf8'))
def text(p):bind(p);return Path(p).read_bytes().decode('utf8')
def verify(b):require(bind(b['path'])['sha256']==b['sha256'],'SOURCE_HASH_CHANGED:'+b['path'])
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def pairs(items):
 d={}
 for k,v in items:
  require(k not in d,'DUPLICATE_JSON_KEY:'+k);d[k]=v
 return d
def nonfinite(x):raise ValueError('NONFINITE_JSON:'+x)
def strict(s):return json.loads(s,object_pairs_hook=pairs,parse_constant=nonfinite)
def contains(a,b):return a and b and a['start']<=b['start'] and b['end']<=a['end']
def overlap(a,b):return a and b and a['start']<b['end'] and b['start']<a['end']
def lexical_hints(t):
 return [name for name,regex in [('storage',r'\bstor(?:e|age|ing)\b'),('imaging',r'\bimag(?:e|ing)\b'),
  ('conditional_or_future',r'\b(?:before|until|if|repeat|up to|after storage)\b'),
  ('labeling',r'\b(?:antibod|stain|label|dye)\w*')] if re.search(regex,t,re.I)]
def source_unit(doc,span):
 return next((u for u in doc['units'] if u['unit_id']==span.get('unit_id')),None)

def inspect_time(cv,payload,doc):
 audit=cv['source_audit'];resolved=audit['resolved'];clock=cv['legacy_projection']['time_calculation']
 rawops=payload['grounded_extraction'].get('operations',[])
 pointers={x.get('i'):'/grounded_extraction/operations/'+str(i) for i,x in enumerate(rawops) if isinstance(x,dict)}
 operations=[]
 for o in resolved['operations']:
  operations.append({'id':o['id'],'raw_pointer':pointers.get(o['id']),'operation':o['operation'],
   'phase':o['phase'],'execution_scope':o['execution_scope'],'phase_support':o.get('phase_support'),
   'scope_gate':o.get('scope_gate'),'duration':o.get('duration'),'duration_binding':o.get('duration_binding'),
   'parsed_duration':o.get('parsed_duration'),'repeat_count':o.get('repeat_count'),
   'repeat_source_binding':o.get('repeat_source_binding'),'condition_evidence':o.get('condition_evidence')})
 candidates=[]
 for r in audit['inventory']:
  if r['kind'] not in ['duration','operation_record_lead','excluded_noncore_duration','dimensional_expression_lead']:continue
  s=r['span'];unit=source_unit(doc,s);cover=[o for o in operations if contains(o['operation'],s)]
  same=[o for o in operations if o['operation']['unit_id']==s.get('unit_id')]
  chosen=[o for o in operations if contains(o.get('duration'),s)]
  unresolved=[{'pointer':'/grounded_extraction/coverage/u/'+str(i),'record':u} for i,u in enumerate(resolved['coverage'].get('unresolved',[])) if overlap(u['evidence'],s)]
  blocked=(r['kind']=='duration' and r['coverage_state']!='covered_time_evidence') or (r['kind']=='operation_record_lead' and r['coverage_state']!='covered_operation_record')
  reasons=[]
  if blocked and not same:reasons.append('no_returned_operation_in_this_source_unit')
  if blocked and same and not cover:reasons.append('returned_same_unit_but_selected_extent_does_not_cover_candidate')
  if blocked and cover and not chosen and r['kind']=='duration':reasons.append('returned_operation_extent_contains_duration_but_no_matching_duration_reference')
  if unresolved:reasons.append('explicit_unresolved_record_overlaps_source_candidate')
  if any(o['phase']=='unknown' for o in cover):reasons.append('model_returned_unknown_phase')
  if any(o['execution_scope']=='unknown' for o in cover):reasons.append('model_returned_unknown_execution_scope')
  if any(o['phase'] in g.EXCLUDE for o in cover):reasons.append('returned_operation_declared_excluded_phase')
  if any(o['execution_scope']=='conditional_or_future' for o in cover):reasons.append('returned_operation_declared_conditional_or_future')
  if any(o.get('parsed_duration',{}).get('bounds_hours') is not None and o['parsed_duration']['bounds_hours'][0]!=o['parsed_duration']['bounds_hours'][1] for o in cover):reasons.append('returned_parsed_duration_is_nonunique_range')
  candidates.append({'candidate_id':r.get('candidate_id'),'kind':r['kind'],'coverage_state':r['coverage_state'],
   'causes_inventory_time_gate':blocked,'source_span':s,'source_unit':unit,
   'lexical_hints_only_not_scientific_phase_adjudication':lexical_hints(unit['text'] if unit else s['quote']),
   'covering_returned_operations':[{'id':o['id'],'raw_pointer':o['raw_pointer'],'phase':o['phase'],'execution_scope':o['execution_scope']} for o in cover],
   'same_unit_operation_ids':[o['id'] for o in same],'duration_reference_operation_ids':[o['id'] for o in chosen],
   'unresolved_source_records':unresolved,'mechanical_localization_categories':reasons,
   'whole_source_semantic_completeness_proven':False})
 return {'time_calculation':clock,'projected_total_hours':cv['legacy_projection']['extraction'].get('clearing_total_time_hours'),
  'model_coverage':payload['grounded_extraction'].get('coverage'),'resolved_coverage':resolved['coverage'],
  'operations':operations,'source_candidates':candidates,'blocking_inventory_candidates':[r for r in candidates if r['causes_inventory_time_gate']],
  'initial_known_contributions':clock.get('known_operation_contributions'),
  'interpretation':'Source-location and frozen application-gate diagnosis, not a new scoring decision or expert phase label.'}

def inspect_errors(payload,doc,result):
 if payload is None:return {'raw_parseable':False,'no_semantic_validation_after_parse_failure':True}
 try:
  rows,errors,duplicates=partial.records_audit(payload,doc,g)
 except Exception as exc:return {'raw_parseable':True,'record_audit_error':str(exc)}
 failures=[]
 for row in rows:
  if row['valid_shape_and_local_source']:continue
  f={k:row[k] for k in ['pointer','group','id','raw_record','errors','resolved_fields']}
  raw=row['raw_record'];support=row['resolved_fields'].get('u')
  if row['group'] in ['entities','method_mentions'] and support and isinstance(raw,dict) and isinstance(raw.get('n'),str):
   try:f['complete_name_occurrences']=g.name_occurrence_inventory(raw['n'],support,doc)
   except Exception as exc:f['name_occurrence_diagnostic_error']=str(exc)
  failures.append(f)
 return {'raw_parseable':True,'invalid_local_records':failures,'duplicate_record_ids':duplicates,
  'per_group_record_counts':dict(collections.Counter(x['group'] for x in rows)),
  'per_group_locally_source_valid_counts':dict(collections.Counter(x['group'] for x in rows if x['valid_shape_and_local_source'])),
  'source_valid_record_not_scientific_fact':True,'saved_component_views':result.get('views',{}),
  'saved_independent_direct':result.get('independent_direct'),'original_full_failure':result.get('full_conversion_or_scoring_failure')}

def snapshot(a):
 require(a.terminal_authorized,'ROOT_TERMINAL_AUTHORIZATION_REQUIRED');batch,n=BATCHES[a.batch];out=R/batch
 require(sha(fw.__file__)==FW_SHA,'FROZEN_FW3_DRIFT')
 matrix=read(out/'matrix.json');plan=read(out/'plan.json');require(len(matrix)==n and plan['planned']==n,'PLANNED_DENOMINATOR')
 # Metadata-only gate before reading any live batch source or raw.
 trials=[]
 for row in matrix:
  path=out/'run/trials'/f"{row['planned_trial_id']}.json";require(path.exists(),'NOT_ALL_TERMINAL:'+row['anonymous_answer_id'])
  t=read(path);require(t['status'] in ['success','partial_components','failed'],'NONTERMINAL_STATUS')
  require(t['identity']==row['identity'] and t['trial_id']==row['planned_trial_id'],'TRIAL_IDENTITY');trials.append(t)
 for b in plan['frozen_inputs']:verify(b)
 cases=read(out/'cases.json')['cases'];require(len(cases)==n,'CASE_DENOMINATOR')
 dest=a.out or R/'confirmation_source_diagnostic_v1'/batch/j.now().replace(':','').replace('+','_')
 require(not dest.exists(),'NEW_DIAGNOSTIC_DIRECTORY_REQUIRED');dest.mkdir(parents=True)
 bind(__file__);bind(g.__file__);bind(fw.__file__);bind(partial.__file__)
 ledgerpath=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl';ledger=[json.loads(x) for x in text(ledgerpath).splitlines() if x.strip()]
 observations=[];flat=[];reconstructed=0
 for row,case,trial in zip(matrix,cases,trials):
  aid=row['anonymous_answer_id'];tid=row['planned_trial_id'];at=out/'run/attempts'/f'{tid}_1'
  for b in trial['bound_artifacts']:verify(b)
  for b in row['assets'].values():verify(b)
  require(case['case_id']==row['case_id'],'CASE_IDENTITY')
  doc=read(row['assets']['source_document']['path']);require(doc==g.document(case['model_response'],g.source_id_for_case(case)),'SOURCE_DOCUMENT')
  require(g.rawsha(case['model_response'])==row['step']['answer_sha256'],'SOURCE_STEP_HASH')
  rec=read(at/'request_receipt.json');require(rec['trial_id']==tid and rec['request_id']==trial['request_id'] and type(rec['attempt']) is int and rec['attempt']==1,'REQUEST_IDENTITY')
  require(sum(x.get('request_id')==rec['request_id'] and x.get('trial_id')==tid for x in ledger)==1,'LEDGER_BINDING')
  result=read(at/'component_result.json') if (at/'component_result.json').exists() else {}
  provider=read(at/'provider_response.json') if (at/'provider_response.json').exists() else None
  raw=text(at/'raw_response.txt') if (at/'raw_response.txt').exists() else None
  if raw is not None:require(provider and provider.get('response')==raw,'PROVIDER_RAW')
  parse_error=None
  try:payload=strict(raw) if raw is not None else None
  except Exception as exc:payload=None;parse_error=str(exc)
  if result:require(result['metrics']==trial['metrics'] and result['raw_sha256']==g.rawsha(raw),'SAVED_COMPONENT_RESULT')
  require(all(trial['metrics'][k]==row['step'][k] for k in ['sr','sp']),'ORIGINAL_SR_SP')
  cv=result.get('conversion');cv_origin='saved_full_conversion' if cv else None;time_error=None
  if not cv and result.get('views',{}).get('time',{}).get('status')=='validated_dependency_view':
   try:
    view,viewmeta=partial.neutral_view(payload,doc,g,['method_mentions','operations','timeline','precedence_edges','total_time_claims'],['t','c','u'])
    saved=result['views']['time'];require(j.digest(view)==saved['view_sha256'],'TIME_VIEW_BYTES')
    cv=fw.convert(g.canonical(view),doc,case)
    require(cv['legacy_projection']['extraction']==saved['projected_extraction'],'TIME_VIEW_PROJECTION_REPLAY')
    cv_origin='reconstructed_exact_saved_time_dependency_view_without_scoring';reconstructed+=1
   except Exception as exc:cv=None;time_error=str(exc)
  time=inspect_time(cv,payload,doc) if cv and payload else None
  errors=inspect_errors(payload,doc,result)
  item={'anonymous_answer_id':aid,'question_id':case['question_id'],'trial_id':tid,'request_index':rec['package_request_index'],
   'original_status':trial['status'],'original_error':trial['error'],'original_failure_stage':trial['failure_stage'],
   'original_metrics':trial['metrics'],'raw_direct_scores':payload.get('scores') if isinstance(payload,dict) else None,
   'raw_parse_error':parse_error,'provider_done_reason':provider.get('done_reason') if provider else None,
   'provider_output_tokens':provider.get('eval_count') if provider else None,'raw':bind(at/'raw_response.txt') if raw else None,
   'source':row['assets']['source_document'],'time_conversion_origin':cv_origin,'time_view_reconstruction_error':time_error,
   'time_diagnostic':time,'local_record_failures':errors,'saved_numeric_component_gate_notes':result.get('numeric',{}).get('component_gate_notes'),
   'new_score_computed':False,'posthoc_confirmation_diagnostic':True,'scientific_gold':False}
  observations.append(item)
  flat.append({'anonymous_answer_id':aid,'question_id':case['question_id'],'original_status':trial['status'],**trial['metrics'],
   'whole_failure_reason':(result.get('full_conversion_or_scoring_failure') or trial.get('error') or {}).get('reason'),
   'time_issues':json.dumps(time['time_calculation']['issues'],ensure_ascii=False) if time else None,
   'blocking_duration_ids':json.dumps([x['candidate_id'] for x in time['blocking_inventory_candidates'] if x['kind']=='duration']) if time else None,
   'time_diagnostic_available':time is not None})
  write(dest/(aid+'_diagnostic.json'),item)
 summary={'status':'completed_posthoc_source_diagnostic','batch':batch,'planned_cells':n,'terminal_cells':len(trials),
  'original_status_counts':dict(collections.Counter(x['original_status'] for x in observations)),
  'numeric_coverage':{k:sum(isinstance(x['original_metrics'].get(k),(int,float)) and not isinstance(x['original_metrics'].get(k),bool) for x in observations) for k in METRICS},
  'time_issue_counts':dict(collections.Counter(i for x in observations if x['time_diagnostic'] for i in x['time_diagnostic']['time_calculation']['issues'])),
  'full_conversion_error_counts':dict(collections.Counter((x['local_record_failures'].get('original_full_failure') or {}).get('reason') for x in observations if x['local_record_failures'].get('original_full_failure'))),
  'time_audits_reconstructed_without_scoring':reconstructed,'new_model_calls':0,'numeric_scoring_calls':0,'rules_changed_after_unblinding':False,
  'source_classification_is_posthoc_diagnostic_not_prospective_validation':True}
 write(dest/'summary.json',summary)
 with (dest/'metrics_and_reasons.csv').open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 write(dest/'verification.json',{'status':'pass','inputs':list(INPUTS.values()),'source_and_trial_hashes_checked':True,
  'original_scores_and_raw_unchanged':True,'all_batch_slots_retained':True,'new_model_calls':0,'numeric_scoring_calls':0,
  'actual_command':sys.argv,'outputs':[{'path':str(p),'sha256':sha(p)} for p in dest.iterdir() if p.is_file()]})
 print(j.canonical({'out':str(dest),**summary}))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',choices=BATCHES,required=True);p.add_argument('--out',type=Path);p.add_argument('--terminal-authorized',action='store_true');snapshot(p.parse_args())
if __name__=='__main__':main()
