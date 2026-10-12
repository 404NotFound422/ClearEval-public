"""Read-only exposed development audit. No model calls or numeric rescoring.

Raw local-source records and saved whole-conversion coverage are separate.
Internal time validation views retain every returned time dependency; they are
not repaired model responses and never replace a saved failed trial.
"""
import argparse, collections, copy, csv, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cce_audit_grounded_facts_v11 as checker
import cce_grounded_extraction_v11 as ground
import cce_partial_components_v1 as partial
import cce_round2_controls_source_audit_v11 as relations
import cce_generation_order_only_v1 as order
import cce_judges as j

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
DEFAULT=R/'generation_completion_fact_audit_v1'
INPUTS={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):
 p=Path(p).resolve();b={'path':str(p),'sha256':sha(p)};INPUTS[str(p)]=b;return b
def read(p):bind(p);return json.loads(Path(p).read_text(encoding='utf8'))
def text(p):bind(p);return Path(p).read_bytes().decode('utf8')
def require(x,m):
 if not x:raise AssertionError(m)
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def verify(b):require(sha(b['path'])==b['sha256'],'INPUT_HASH:'+b['path']);bind(b['path'])
def pairs(items):
 d={}
 for k,v in items:
  require(k not in d,'DUPLICATE_JSON_KEY:'+k);d[k]=v
 return d
def bad_constant(s):raise ValueError('NONFINITE_JSON:'+s)
DECODER=json.JSONDecoder(object_pairs_hook=pairs,parse_constant=bad_constant)
def entity_rows(audit):
 return [{'id':x['id'],'name':x['name'],'name_binding':x['name_binding'],
   'kind':x['raw_record']['k'],'usage':x['raw_record']['s']} for x in audit
   if x['group']=='entities' and x['valid_shape_and_local_source']]
def summarize_fact(fact,local,whole):
 return {'anonymous_answer_id':fact['anonymous_answer_id'],
  'whole_conversion_available':whole['conversion_available'],
  'name_denominator':len(local['names']),
  'raw_exact_source_bound_names':sum(x['status']=='exact' for x in local['names']),
  'whole_exact_names':sum(x['status']=='exact' for x in whole['names']),
  'initial_duration_denominator':len(local['durations']),
  'raw_record_bound_numeric_durations':sum(x['record_bound_numeric_retained'] is True for x in local['durations']),
  'raw_initial_scope_durations':sum(x['initial_scope_preserved'] is True for x in local['durations']),
  'whole_record_bound_numeric_durations':sum(x['record_bound_numeric_retained'] is True for x in whole['core_duration_components']),
  'fixed_relation_denominator':len(local['fixed_relations']),
  'raw_fixed_relation_mechanical_support':sum(x['mechanically_supported_raw_claim'] for x in local['fixed_relations']),
  'whole_fixed_relation_projection':sum(x['exact_legacy_projection_retained'] is True for x in whole['relations']),
  'fixed_ambiguity_denominator':len(local['ambiguities']),
  'raw_explicit_ambiguity_retained':sum(x['status']=='explicit_ambiguity_retained' for x in local['ambiguities']),
  'whole_explicit_ambiguity_retained':sum(x['status']=='explicit_ambiguity_retained' for x in whole['ambiguities'])}

def local_facts(raw,doc,fact):
 records,issues,duplicates=partial.records_audit(raw,doc,ground)
 ents=entity_rows(records);label_audit=relations.raw_relation_audit(raw,doc)
 wire=raw['grounded_extraction'];time_result=None;time_error=None
 try:
  view,view_meta=partial.neutral_view(raw,doc,ground,
   ['method_mentions','operations','precedence_edges','timeline','total_time_claims'],['t','c','u'])
  time_result=ground.convert(ground.canonical(view),doc)
 except Exception as exc:time_error=type(exc).__name__+': '+str(exc);view_meta=locals().get('view_meta')
 local={'records':records,'record_source_issues':issues,'duplicate_record_ids':duplicates,
  'all_asserted_relations':label_audit,'time_dependency_view':{'available':time_result is not None,
   'error':time_error,'provenance':view_meta,'not_a_complete_model_conversion':True}}
 if not fact:return local
 names=checker.old.name_audit(fact['explicit_names_to_retain'],ents,True)
 ops=time_result['source_audit']['resolved']['operations'] if time_result else []
 durations=checker.old.duration_audit(fact['time']['components'],ops,True,time_result is not None)
 fixed=[]
 for f in fact['explicitly_supported_label_relations']:
  found=[x for x in label_audit['rows'] if x.get('label')==f['label'] and x.get('target')==f['target']]
  fixed.append({'label':f['label'],'target':f['target'],'inventory_source_span':f['source_span'],
   'matching_raw_claims':found,'mechanically_supported_raw_claim':any(x['state']=='mechanical_gate_pass' for x in found),
   'not_expert_gold':True})
 # Only inspect explicit raw ambiguity declarations and source-bound entities.
 # An empty local projection is not a claim that whole serialization succeeded.
 unresolved=[]
 for u in wire['coverage']['u']:
  try:unresolved.append({'evidence':ground.resolve(ground._expand_ref(u['u']),doc),'raw':u})
  except (KeyError,ValueError):
   # The source schema, not a guessed alias, defines the compact unresolved key.
   expanded,_=ground.expand_wire_payload(raw,doc)
   unresolved=[{'evidence':ground.resolve(x['evidence'],doc),'raw':x} for x in expanded['grounded_extraction']['coverage']['unresolved']]
   break
 edge_rows=[{'fluor_entity_id':x['f'],'target_entity_id':x['t'],'status':x['s']} for x in wire['relations']]
 amb=checker.old.ambiguity_audit(fact['ambiguous_relations_or_alternatives'],
  {'entities':ents,'relations':edge_rows,'coverage':{'unresolved':unresolved}}, {}, True)
 for a in amb:a['whole_projection_available']=False;a['scope']='Raw explicit ambiguity only; empty local mapping is not successful serialization.'
 local.update(names=names,durations=durations,fixed_relations=fixed,ambiguities=amb)
 return local

def load_batch(name,facts):
 out=R/name;plan=read(out/'plan.json')
 for b in plan['frozen_inputs']:verify(b)
 matrix=read(out/'matrix.json');cases=read(out/'cases.json')['cases'];contract=read(out/'expected_contract.json')
 require(len(matrix)==len(cases),'MATRIX_CASE_SIZE');result=[]
 ledger_path=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
 ledger=[json.loads(x) for x in text(ledger_path).splitlines() if x.strip()]
 for row,case in zip(matrix,cases):
  aid=row['anonymous_answer_id'];tid=row['planned_trial_id'];at=out/'run/attempts'/f'{tid}_1'
  for b in row['assets'].values():verify(b)
  trial=read(out/'run/trials'/f'{tid}.json')
  require(trial['status'] in ['success','failed'],'NONTERMINAL');require(trial['identity']==row['identity'],'TRIAL_IDENTITY')
  require(j.digest(row['identity'])==tid and row['identity']['contract_sha256']==j.digest(contract),'CONTRACT')
  for b in trial['bound_artifacts']:verify(b)
  receipt=read(at/'request_receipt.json');provider=read(at/'provider_response.json');rawtext=text(at/'raw_response.txt')
  require(provider['response']==rawtext,'PROVIDER_RAW');require(receipt['request_id']==trial['request_id'],'RECEIPT')
  require(receipt['trial_id']==tid and type(receipt['attempt']) is int and receipt['attempt']==1,'REQUEST_IDENTITY')
  require(sum(x.get('request_id')==receipt['request_id'] and x.get('trial_id')==tid for x in ledger)==1,'LEDGER_RECEIPT')
  require(read(at/'raw_receipt.json')['raw_sha256']==ground.rawsha(rawtext),'RAW_RECEIPT')
  require(read(at/'http_request_payload.json')==read(row['assets']['payload']['path']),'ACTUAL_PAYLOAD')
  doc=read(row['assets']['source_document']['path']);require(doc==ground.document(case['model_response'],ground.source_id_for_case(case)),'SOURCE_DOCUMENT')
  raw=DECODER.decode(rawtext);fact=facts.get(aid)
  if fact:require(doc['answer_sha256']==fact['source']['answer_sha256'] and ground.rawsha(case['specific_question'])==fact['source']['question_sha256'],'FIXED_INVENTORY_INPUT')
  cv=read(at/'conversion.json') if (at/'conversion.json').exists() else None
  if cv:require(cv['raw_response_sha256']==ground.rawsha(rawtext) and cv['wire_payload']==raw,'SAVED_CONVERSION_RAW')
  local=local_facts(raw,doc,fact)
  whole=checker.old.audit_case(fact,cv,doc['text']) if fact else None
  res={'batch':name,'anonymous_answer_id':aid,'trial_id':tid,'request_index':receipt['package_request_index'],
   'status':trial['status'],'error':trial['error'],'raw':bind(at/'raw_response.txt'),'source':row['assets']['source_document'],
   'provider_tokens':provider.get('eval_count'),'provider_done_reason':provider.get('done_reason'),
   'whole_conversion_available':cv is not None,'local_source_audit':local,'fixed_whole_conversion_audit':whole,
   'coverage':summarize_fact(fact,local,whole) if fact else None,
   'raw_entity_count':len(raw['grounded_extraction']['entities']),'raw_operation_count':len(raw['grounded_extraction']['operations']),
   'original_metrics':trial['metrics']}
  result.append((res,doc,raw,cv,case))
 return result

def prefix_entities(rawtext):
 m=re.search(r'"entities"\s*:\s*\[',rawtext);p=m.end();objects=[]
 while p<len(rawtext):
  while p<len(rawtext) and rawtext[p] in ', \r\n\t':p+=1
  try:o,p2=DECODER.raw_decode(rawtext,p)
  except (ValueError,AssertionError):break
  if not isinstance(o,dict):break
  objects.append(o);p=p2
 return objects

def fpc_audit(compact,ordered):
 original=R/'fieldwise_confirmation_v1';oldraw=next((original/'run/attempts').glob('*/raw_response.txt'))
 objs=prefix_entities(text(oldraw));unique={j.canonical({k:v for k,v in x.items() if k!='i'}):x for x in objs};doc=compact[1]
 require(doc==ordered[1],'FPC_SOURCE_CHANGED')
 old_validation=[]
 for i,x in enumerate(unique.values()):
  try:
   e=relations.resolved_entity(x,doc,ground.schema_for_document(doc)['properties']['grounded_extraction']['properties']['entities']['items'])
   old_validation.append({'raw_record':x,'valid_local_name':True,'name':e['name'],'usage':x['s']})
  except Exception as exc:old_validation.append({'raw_record':x,'valid_local_name':False,'error':str(exc)})
 # This source-led list is deliberately a narrow label/target/antibody check,
 # not an exhaustive new gold inventory or a denominator inferred from old output.
 source_names=['c-Fos','Alexa Fluor 647','DAPI','rabbit anti-c-Fos','donkey anti-rabbit Alexa Fluor 647','normal donkey serum']
 coverage=[]
 for name in source_names:
  occurrences=[{'start':m.start(),'end':m.end(),'quote':m.group(),
   'unit_id':next(u['unit_id'] for u in doc['units'] if u['start']<=m.start()<u['end'])}
   for m in re.finditer(re.escape(name),doc['text'])]
  require(occurrences,'SOURCE_NAME_ABSENT:'+name)
  r={'literal':name,'source_occurrences':occurrences,'scope':'blocking material' if name=='normal donkey serum' else 'chosen label/target or named antibody'}
  for label,item in [('compact',compact),('order_only',ordered)]:
   records=item[0]['local_source_audit']['records'];entities=[e for e in records if e['group']=='entities' and e['valid_shape_and_local_source'] and e['name']['quote']==name]
   op=[e for e in records if e['group']=='operations' and name in e['resolved_fields'].get('o',{}).get('quote','')]
   r[label]={'exact_source_bound_entity_records':[{'id':e['id'],'name':e['name'],'usage':e['raw_record']['s']} for e in entities],
    'also_inside_returned_operation_evidence':[e['id'] for e in op],
    'selected_or_used_status_not_inferred_from_name_presence':True}
  coverage.append(r)
 return {'source':compact[0]['source'],'old_raw':bind(oldraw),'old_complete_entity_prefix_count':len(objs),
  'old_unique_objects_ignoring_id':len(unique),'old_unique_local_name_valid':sum(x['valid_local_name'] for x in old_validation),
  'old_unique_record_validation':old_validation,'source_led_selected_name_check':coverage,
  'new':{label:{'entity_count':x[0]['raw_entity_count'],'operation_count':x[0]['raw_operation_count'],
   'tokens':x[0]['provider_tokens'],'all_relations':x[0]['local_source_audit']['all_asserted_relations'],
   'entity_records':[e for e in x[0]['local_source_audit']['records'] if e['group']=='entities']}
   for label,x in [('compact',compact),('order_only',ordered)]},
  'old_prefix_is_not_gold':True,'exhaustive_scientific_precision_or_recall':False,
  'interpretation':'Compare directly with source, not old repeated objects. Literal presence does not establish chosen/used status or antibody-to-target support.'}

def payload_comparison():
 out=R/'grounded_development_v11';matrix=read(out/'matrix.json');cases=read(out/'cases.json')['cases'];contract=read(out/'expected_contract.json');rows=[]
 for r,c in zip(matrix,cases):
  at=out/'run/attempts'/f"{r['planned_trial_id']}_1";actual=read(at/'http_request_payload.json')
  for b in r['assets'].values():verify(b)
  doc=read(r['assets']['source_document']['path']);prompt=text(r['assets']['prompt']['path'])
  expected=order.payload_for(prompt,order.schema_for_document(doc),contract['models'][0]['settings'])
  # Original frozen prompt is explicitly checked against the factory's prompt.
  expected_prompt=order.make_prompt(c,doc)
  if isinstance(expected_prompt,tuple):expected_prompt=expected_prompt[0]
  require(prompt==expected_prompt,'ORIGINAL_PROMPT_FACTORY')
  same_values=actual==expected;same_order=order.ordered_json(actual['format'])==order.ordered_json(expected['format'])
  require(same_values and same_order,'ORIGINAL_DEVELOPMENT_ORDER_FACTORY')
  rows.append({'anonymous_answer_id':r['anonymous_answer_id'],'actual_payload':bind(at/'http_request_payload.json'),
   'all_JSON_values_equal_order_only_factory':same_values,'recursive_ordered_schema_equal_factory':same_order,
   'original_prompt_exact_factory':True,'actual_schema_key_order':list(actual['format']['properties'])})
 old=read(R/'fieldwise_confirmation_v1/diagnostic_01/diagnostic.json')
 oldpath=Path(next(x['actual_payload']['path'] for x in old['payload_rows'] if x['stage']=='confirmation' and x['actual_payload']))
 op=read(oldpath);np=read(next((R/'generation_order_only_development_v1/run/attempts').glob('*/http_request_payload.json')))
 require(op==np,'ORDER_ONLY_VALUES_NOT_IDENTICAL');require(op['prompt']==np['prompt'],'ORDER_ONLY_PROMPT')
 return {'development5':rows,'FPC01_original_vs_order_only':{'all_JSON_values_equal':True,'prompt_exact_equal':True,
  'recursive_ordered_schema_equal':order.ordered_json(op['format'])==order.ordered_json(np['format']),
  'old_payload':bind(oldpath),'new_payload':bind(next((R/'generation_order_only_development_v1/run/attempts').glob('*/http_request_payload.json')))},
  'causal_boundary':'One exposed answer, one new generation per variant; observed completion difference is not a general guarantee. Compact additionally changes instructions.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=DEFAULT);a=ap.parse_args()
 require(not a.out.exists(),'NEW_OUTPUT_REQUIRED');a.out.mkdir(parents=True)
 inv,src,checks=checker.verify_sources();bind(checker.old.INVENTORY)
 for mod in [checker,checker.old,ground,partial,relations,order]:bind(mod.__file__)
 bind(__file__);facts={x['anonymous_answer_id']:x for x in inv['cases']}
 compact=load_batch('generation_completion_development_v1',facts);ordered=load_batch('generation_order_only_development_v1',{})
 fpc=fpc_audit(next(x for x in compact if x[0]['anonymous_answer_id']=='FPC01'),ordered[0]);payloads=payload_comparison()
 rows=[x[0]['coverage'] for x in compact if x[0]['coverage']];totals={k:sum(r[k] for r in rows) for k in rows[0] if k not in ['anonymous_answer_id','whole_conversion_available']}
 summary={'status':'completed_source_audit','compact_cells':6,'compact_success':sum(x[0]['status']=='success' for x in compact),
  'compact_failed':sum(x[0]['status']=='failed' for x in compact),'fixed_development_answers':5,
  'whole_conversion_available_development':sum(r['whole_conversion_available'] for r in rows),'fixed_totals':totals,
  'per_answer':rows,'all_structured_relation_states':dict(collections.Counter(y['state'] for x in compact for y in x[0]['local_source_audit']['all_asserted_relations']['rows'])),
  'order_only_FPC01_status':ordered[0][0]['status'],'new_model_calls':0,'numeric_rescoring_calls':0,
  'expert_returns':0,'scientific_accuracy_proven':False,'whole_conversion_failure_never_reclassified_as_success':True}
 write(a.out/'summary.json',summary);write(a.out/'per_answer.json',[x[0] for x in compact]+[ordered[0][0]])
 write(a.out/'FPC01_source_comparison.json',fpc);write(a.out/'payload_order_comparison.json',payloads)
 with (a.out/'fixed_coverage.csv').open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write(a.out/'verification.json',{'status':'pass','inputs':list(INPUTS.values()),'inventory_denominators':inv['fixed_denominators'],
  'measurement_functions':checker.measurements(),'all_inputs_unchanged':all(sha(x['path'])==x['sha256'] for x in INPUTS.values()),
  'outputs':[{'path':str(p),'sha256':sha(p)} for p in a.out.iterdir() if p.is_file()],
  'execution_command':sys.argv,'no_unrun_confirmation_inputs_read':True,'new_model_calls':0,'numeric_rescoring_calls':0})
 print(json.dumps(summary,ensure_ascii=False));print('summary_sha256',sha(a.out/'summary.json'))
if __name__=='__main__':main()
