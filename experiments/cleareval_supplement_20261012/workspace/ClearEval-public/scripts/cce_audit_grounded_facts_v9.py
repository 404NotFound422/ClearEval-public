"""Independent v9 adapter over unchanged v7 measurement functions. Zero model calls.

Raw compact name presence, converted retention and all asserted relation failures
remain separate. This file does not repair returned values or recompute EGES.
"""
import argparse, ast, hashlib, json, sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts')]
import cce_audit_grounded_facts_v7 as old
import cce_grounded_extraction_v9 as grounded
BASE=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=BASE/'fact_audit_checker_v9'
DESIGN=BASE/'regression_design_v1'
GROUND_SHA='5026019e08128b939cdf446dcfd6d936bcefb56a351c86e69188c548e1efa135'
QUANTIFICATION_FUNCTIONS=['source_hours','name_audit','duration_audit','relation_audit','ambiguity_audit','ri_evidence_audit']
ORIGINAL_CHECKER_SHA='3cd4852f67c21dd2eef3bdd8114dcd8e07681261ac5aee40f1ee50e79a4492e8'
FINAL_FREEZE_AUTHORIZED=True
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(x,msg):
 if not x:raise ValueError(msg)
def measurements():
 # Calling the original functions avoids implementation drift or copied formulas.
 s=Path(old.__file__).read_text(encoding='utf8');tree=ast.parse(s)
 return {name:rawsha(ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)) for name in QUANTIFICATION_FUNCTIONS}
def verify_sources():
 require(sha(grounded.__file__)==GROUND_SHA,'V9_MODULE_DRIFT')
 if ORIGINAL_CHECKER_SHA:require(sha(old.__file__)==ORIGINAL_CHECKER_SHA,'ORIGINAL_MEASUREMENT_SOURCE_DRIFT')
 for rec in read(DESIGN/'freeze.json')['files']+read(DESIGN/'source_bindings.json'):
  require(sha(rec['path'])==rec['sha256'],'REGRESSION_SOURCE_DRIFT')
 return old.verify_inventory(require_module=False)
def raw_name_presence(expected,raw):
 if raw is None:return old.raw_name_presence(expected,None)
 try:
  payload=old.strict_raw_payload(raw);g=payload.get('grounded_extraction',{})
  require(isinstance(g,dict),'RAW_GROUNDED_NOT_OBJECT');ents=g.get('entities',[])
  require(isinstance(ents,list),'RAW_ENTITIES_NOT_ARRAY')
  carrier={'grounded_extraction':{'entities':[{'id':x.get('i'),'literal_name':x.get('n')} for x in ents if isinstance(x,dict)]}}
  result=old.raw_name_presence(expected,json.dumps(carrier,ensure_ascii=False))
  result.update(wire_name_keys={'i':'id','n':'literal_name'},raw_compact_response_sha256=rawsha(raw),
   renamed_for_original_measurement_only=True,does_not_establish_wire_schema_validity=True)
  return result
 except (ValueError,TypeError,AttributeError) as exc:
  result=old.raw_name_presence(expected,None);result['parse_error']=str(exc);return result
def self_check():
 inv,_,_=verify_sources();review=read(DESIGN/'v9_review/independent_review.json')
 require(review['status']=='pass' and review['module_sha256']==GROUND_SHA,'INDEPENDENT_REVIEW_NOT_PASS')
 controls=read(DESIGN/'v9_review/source_relation_software_replay.json')
 require(controls['status']=='pass' and controls['module_sha256']==GROUND_SHA and len(controls['rows'])==5 and all(r['pass'] for r in controls['rows']),'SOURCE_RELATION_SOFTWARE_CONTROLS_NOT_PASS')
 checks=[]
 def check(name,x):require(x,name);checks.append({'id':name,'pass':True})
 expected=[{'name':'SYNTHETIC_FULL_101'}]
 raw=json.dumps({'grounded_extraction':{'entities':[{'i':'e1','n':'SYNTHETIC_FULL_101'}]}})
 check('compact_raw_name_exact',raw_name_presence(expected,raw)['names'][0]['status']=='raw_literal_present')
 check('compact_raw_absence_not_zero',raw_name_presence(expected,raw.replace('FULL_101','FULL'))['names'][0]['status']=='raw_literal_absent')
 check('duplicate_raw_unavailable',raw_name_presence(expected,'{"grounded_extraction":{},"grounded_extraction":{}}')['names'][0]['status']=='unavailable')
 check('nonfinite_raw_unavailable',raw_name_presence(expected,'{"x":NaN}')['names'][0]['status']=='unavailable')
 check('original_fixed_denominators',inv['fixed_denominators']['explicit_selected_or_used_entity_names']==16 and inv['fixed_denominators']['source_core_duration_components']==31 and inv['fixed_denominators']['explicit_label_target_relations']==3 and inv['fixed_denominators']['ambiguity_groups']==2)
 v4=ast.parse(Path(old.V4_CHECKER).read_text(encoding='utf8'));original=ast.parse(Path(old.__file__).read_text(encoding='utf8'))
 for name in QUANTIFICATION_FUNCTIONS:
  nodes=[next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name) for t in [v4,original]]
  check('unchanged_measurement_'+name,ast.dump(nodes[0],include_attributes=False)==ast.dump(nodes[1],include_attributes=False))
 write(OUT/'software_probes.json',{'status':'pass','checks':checks,'count':len(checks),'checker_sha256':sha(__file__),
  'module_sha256':GROUND_SHA,'original_checker':bind(old.__file__),'measurement_AST':measurements(),
  'independent_review':bind(DESIGN/'v9_review/independent_review.json'),'source_relation_software_controls':bind(DESIGN/'v9_review/source_relation_software_replay.json'),'actual_command':[sys.executable,*sys.argv],
  'new_model_calls':0,'synthetic_not_scientific_results':True})
 print(json.dumps({'status':'software_pass_not_frozen','checks':len(checks),'new_model_calls':0}))
def freeze():
 require(FINAL_FREEZE_AUTHORIZED,'ROOT_FREEZE_AUTHORIZATION_REQUIRED');self_check()
 require(not (OUT/'freeze.json').exists(),'FREEZE_ALREADY_EXISTS')
 write(OUT/'freeze.json',{'status':'frozen_before_v9_generation','checker_sha256':sha(__file__),
  'grounded_module':bind(grounded.__file__),'software_probes':bind(OUT/'software_probes.json'),
  'original_checker':bind(old.__file__),'inventory':bind(old.INVENTORY),'measurement_AST':measurements(),
  'regression_facts':bind(DESIGN/'expected_facts.json'),'independent_review':bind(DESIGN/'v9_review/independent_review.json'),
  'source_relation_software_controls':bind(DESIGN/'v9_review/source_relation_software_replay.json'),
  'new_model_calls':0,'actual_command':[sys.executable,*sys.argv]})
def analyze(batch):
 inv,sources,inventory_checks=verify_sources();f=read(OUT/'freeze.json')
 require(f['checker_sha256']==sha(__file__) and f['measurement_AST']==measurements(),'FROZEN_CHECKER_DRIFT')
 for key in ['grounded_module','original_checker','inventory','regression_facts','independent_review','software_probes','source_relation_software_controls']:
  require(sha(f[key]['path'])==f[key]['sha256'],'FROZEN_INPUT_DRIFT:'+key)
 require(batch.resolve().is_relative_to(BASE),'BATCH_OUTSIDE_ROUND2');require(not any(x in str(batch).lower() for x in ['confirmation','holdout','sealed']),'FORBIDDEN_BATCH_SCOPE')
 cases=read(batch/'cases.json')['cases'];matrix=read(batch/'matrix.json')
 require([x['anonymous_answer_id'] for x in cases]==old.IDS and {x['anonymous_answer_id'] for x in matrix}==set(old.IDS) and len(matrix)==5,'EXACT_ORIGINAL_FIVE_REQUIRED')
 cells={x['anonymous_answer_id']:x for x in matrix};indexed={x['anonymous_answer_id']:x for x in cases}
 trials={aid:read(batch/'run/trials'/f"{c['planned_trial_id']}.json") for aid,c in cells.items()}
 require(all(t['status'] in ['success','failed'] for t in trials.values()),'ALL_FIVE_TERMINAL_REQUIRED')
 files=[Path(__file__),Path(old.__file__),old.INVENTORY,OUT/'freeze.json',batch/'cases.json',batch/'matrix.json',batch/'expected_contract.json']
 rows=[];all_relations=[]
 for fact in inv['cases']:
  aid=fact['anonymous_answer_id'];case=indexed[aid];cell=cells[aid];t=trials[aid]
  require(all(case[k]==sources[aid][k] for k in ['case_id','question_id','specific_question','model_response']),'ORIGINAL_SOURCE_IDENTITY')
  require(t['identity']==cell['identity'] and t['case_id']==case['case_id'],'ACTUAL_TRIAL_IDENTITY')
  doc_path=batch/'source_documents'/f'{aid}.json';doc=read(doc_path)
  require(doc==grounded.document(case['model_response'],grounded.source_id_for_case(case)),'SOURCE_DOCUMENT_REPLAY')
  attempt=batch/'run/attempts'/f"{cell['planned_trial_id']}_1";receipt_path=attempt/'request_receipt.json';receipt=read(receipt_path)
  require(receipt['trial_id']==cell['planned_trial_id'] and receipt['attempt']==1,'ACTUAL_RECEIPT_IDENTITY')
  provider=attempt/'provider_response.json';raw=read(provider).get('response') if provider.exists() else None
  meta=(t.get('evaluation',{}).get('grounded_extraction_v9') or {});cv=meta.get('conversion')
  if cv is not None:
   require(isinstance(raw,str) and cv==grounded.convert(raw,doc),'SAVED_CONVERSION_EXACT_REPLAY')
   require(cv['raw_response_sha256']==rawsha(raw) and cv['scores_preserved_exactly'],'RAW_AND_SCORE_SUBTREE_PRESERVED')
  row=old.audit_case(fact,cv,case['model_response']);row['raw_name_presence']=raw_name_presence(fact['explicit_names_to_retain'],raw)
  row['actual_trial']={'state':'auditable_conversion' if cv is not None else 'actual_trial_without_valid_conversion','trial_id':cell['planned_trial_id'],
   'trial_status':t['status'],'request_id':receipt['request_id'],'conversion_errors':meta.get('conversion_errors')}
  row['source_answer_sha256']=rawsha(case['model_response']);rows.append(row)
  if cv is not None:
   g=cv['source_audit']['resolved'];ent={e['id']:e['name']['quote'] for e in g['entities']}
   for r in g['relations']:
    label=ent[r['fluor_entity_id']];target=ent.get(r['target_entity_id']);ev=r['evidence'];text=doc['text'][ev['start']:ev['end']]
    require(text==ev['quote'],'RELATION_EVIDENCE_REPLAY')
    all_relations.append({'answer_id':aid,'relation_id':r['id'],'label':label,'target':target,'raw_status':r['status'],
     'endpoint_literals_present':target is not None and label in text and target in text,
     'explicit_endpoint_missing':r['status']=='explicit' and not(target is not None and label in text and target in text),
     'projection_allowed':r['projection_allowed'],'actual_gate':r['mechanical_relation_state'],
     'source_gate_status':('explicit_passed_current_gate' if r['projection_allowed'] else 'explicit_rejected_current_gate') if r['status']=='explicit' else r['status'],
     'is_scientific_precision':False})
  files += [doc_path,batch/'run/trials'/f"{cell['planned_trial_id']}.json",receipt_path]
  if provider.exists():files.append(provider)
 summary={'status':'complete','fixed_answers':5,'auditable_conversions':sum(r['conversion_available'] for r in rows),
  'explicit_names_denominator':16,'name_states':dict(Counter(n['status'] for r in rows for n in r['names'])),
  'raw_name_presence_separate':{'fixed_denominator':16,'states':dict(Counter(n['status'] for r in rows for n in r['raw_name_presence']['names'])),
   'does_not_count_as_conversion_or_source_validity':True},
  'core_duration_denominator':31,'literal_numeric_components_retained':sum(d['literal_source_numeric_value_retained'] is True for r in rows for d in r['core_duration_components']),
  'record_bound_numeric_components_retained':sum(d['record_bound_numeric_retained'] is True for r in rows for d in r['core_duration_components']),
  'core_initial_scope_retained':sum(bool(d['initial_scope_preserved']) for r in rows for d in r['core_duration_components']),
  'explicit_relation_denominator':3,'exact_endpoint_edges_retained':sum(bool(e['edge_retained']) for r in rows for e in r['relations']),
  'exact_relation_projections_retained':sum(bool(e['exact_legacy_projection_retained']) for r in rows for e in r['relations']),
  'ambiguity_group_denominator':2,'ambiguity_states':dict(Counter(a['status'] for r in rows for a in r['ambiguities'])),
  'all_converted_raw_relations':{'claims':len(all_relations),'explicit_endpoint_missing':sum(r['explicit_endpoint_missing'] for r in all_relations),
   'states':dict(Counter(r['source_gate_status'] for r in all_relations)),
   'projection_allowed':sum(r['projection_allowed'] for r in all_relations),'failed_conversions_not_in_this_claim_denominator':5-sum(r['conversion_available'] for r in rows),
   'mere_endpoint_presence_does_not_prove_pair_or_scientific_correctness':True},
  'bundle':'Relative to v8, v9 adds a generic zero-based local endpoint-occurrence instruction and fictional example. Source gates, compact wire, measurement functions and scientific rules remain unchanged. Real v8 and v9 returns are separate batches; software capability is not an observed improvement.',
  'measurement_AST':measurements(),'inputs':[bind(p) for p in dict.fromkeys(files)],'actual_command':[sys.executable,*sys.argv],
  'new_model_calls':0,'EGES_rescored':False,'expert_labels_created':0,'scientific_accuracy_claimed':False}
 dest=batch/'independent_fact_audit_v9';require(not (dest/'summary.json').exists(),'DO_NOT_OVERWRITE_AUDIT')
 write(dest/'per_answer.json',rows);write(dest/'all_converted_relation_claims.json',all_relations);write(dest/'summary.json',summary);write(dest/'inventory_verification.json',inventory_checks)
 print(json.dumps({k:summary[k] for k in ['status','auditable_conversions','name_states','record_bound_numeric_components_retained','exact_relation_projections_retained','ambiguity_states','new_model_calls']}))
def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--self-check',action='store_true');g.add_argument('--freeze',action='store_true');g.add_argument('--analyze',action='store_true');p.add_argument('--batch-out',type=Path);a=p.parse_args()
 if a.self_check:self_check()
 elif a.freeze:freeze()
 else:require(a.batch_out is not None,'BATCH_REQUIRED');analyze(a.batch_out)
if __name__=='__main__':main()
