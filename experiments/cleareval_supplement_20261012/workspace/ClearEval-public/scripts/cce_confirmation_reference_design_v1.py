"""Offline catalog projection/size design. No sealed inputs or experiment freeze."""
from __future__ import annotations
import copy,csv,hashlib,io,json,re,socket,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_method_family_steps_v1 as family
import cce_stability_remediation_v2 as legacy
BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'confirmation_reference_design_v1'
CAT=ROOT/'artifacts/cce_validation/method_family_steps_v1/references.json'
DEV=BASE/'grounded_development_v3'
QIDS=[1,2,21,22,23,248]
FAMILIES=['FDISCO','PEGASOS','uDISCO','ScaleS','iDISCO+','CUBIC']
CONFIGURED_CONTEXT=98304 # Root pre-unsealing decision; this script changes no runner.
PURE_FIELDS={'source_path','source_sha256','source_url','supplement_url','evidence_manifest_path','source_conflicts_path',
 'evidence_ids','source_pages','source_workflow_step_id','human_confirmation','expert_confirmed','new_model_requests',
 'target_answer_bindings','reviewer'}
ANCHOR_PARENTS={'source_span','source_spans','source_anchor','prerequisite_source_span','source_passages','visual_evidence'}
ANCHOR_COORDINATES={'start','end','char_start','char_end','line_start','line_end','page','page_index','page_number','pageno','text_sha256','quote_sha256'}
FACTOR_NOTE='[LOSSLESS SHARED VALUES]\nIn this reference JSON, a sole {"$ref_value":"Vnnn"} object means the exact value in shared_values[Vnnn]. Expand recursively without changing values or list order. The references field retains every non-provenance scientific field.\n'

def require(ok,message):
 if not ok:raise ValueError(message)
def canonical(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),sort_keys=True,allow_nan=False)
def nbytes(v):return len(canonical(v).encode('utf8'))
def rawsha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode('utf8')).hexdigest()
def bind(p):return {'path':str(Path(p)),'sha256':rawsha(Path(p).read_bytes())}
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def table(p,rs):
 keys=list(dict.fromkeys(k for r in rs for k in r))
 with Path(p).open('w',newline='',encoding='utf-8-sig') as stream:
  writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
  for row in rs:writer.writerow({k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
def scalar_count(v):
 return sum(scalar_count(x) for x in v.values()) if isinstance(v,dict) else sum(scalar_count(x) for x in v) if isinstance(v,list) else 1

def provenance_reason(key,value,path):
 if key=='target_answer_bindings':return 'historical_construction_answer_identity_provenance_not_prompt_evidence'
 if key in PURE_FIELDS:return 'explicit_file_locator_or_review_provenance_field'
 if key.endswith('_sha256') and (value is None or isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)):
  return 'content_hash_locator'
 if key=='sha256' and isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value):return 'content_hash_locator'
 if (key=='path' or key.endswith('_path')) and isinstance(value,str) and (re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith('/')):return 'absolute_file_path_locator'
 if any(str(p) in ANCHOR_PARENTS for p in path) and key in ANCHOR_COORDINATES:return 'source_anchor_coordinate_not_protocol_parameter'
 return None

def project_reference(ref):
 moved=[]
 def walk(value,path):
  if isinstance(value,dict):
   result={}
   for k,v in value.items():
    reason=provenance_reason(k,v,path)
    if reason:moved.append({'path':path+[k],'value':copy.deepcopy(v),'reason':reason})
    else:result[k]=walk(v,path+[k])
   return result
  if isinstance(value,list):return [walk(v,path+[i]) for i,v in enumerate(value)]
  return value
 result=walk(ref,[]);hoisted=False
 steps=result.get('steps',[])
 if steps and all('required_scope' in s for s in steps) and len({canonical(s['required_scope']) for s in steps})==1:
  require('step_default_required_scope' not in result,'RESERVED_SCOPE_FIELD_COLLISION')
  result['step_default_required_scope']=copy.deepcopy(steps[0]['required_scope'])
  for s in steps:s.pop('required_scope')
  hoisted=True
 return result,{'reference_id':ref['reference_id'],'moved_provenance':moved,'uniform_required_scope_hoisted':hoisted}

def restore_reference(projected,audit):
 result=copy.deepcopy(projected)
 if audit['uniform_required_scope_hoisted']:
  scope=result.pop('step_default_required_scope')
  for step in result['steps']:step['required_scope']=copy.deepcopy(scope)
 for item in audit['moved_provenance']:
  cursor=result
  for token in item['path'][:-1]:cursor=cursor[token]
  require(item['path'][-1] not in cursor,'PROVENANCE_RESTORE_COLLISION');cursor[item['path'][-1]]=copy.deepcopy(item['value'])
 return result

def factor(values):
 """Optional reversible shared-value JSON representation, not an approved prompt."""
 counts=Counter();objects={}
 def count(v):
  if isinstance(v,dict):
   require('$ref_value' not in v,'SHARED_VALUE_RESERVED_KEY_COLLISION')
   for x in v.values():count(x)
  elif isinstance(v,list):
   for x in v:count(x)
  if isinstance(v,(dict,list,str)):
   key=canonical(v)
   if len(key.encode('utf8'))>=100:counts[key]+=1;objects[key]=v
 count(values)
 candidates=sorted([k for k,v in counts.items() if v>=2],key=lambda k:(len(k.encode('utf8')),k))
 ids={key:f'V{i:03}' for i,key in enumerate(candidates,1)}
 def encode(v,skip=None):
  key=canonical(v)
  if key in ids and key!=skip:return {'$ref_value':ids[key]}
  if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
  if isinstance(v,list):return [encode(x) for x in v]
  return v
 encoded=encode(values);definitions={ids[k]:encode(objects[k],skip=k) for k in candidates}
 used=set()
 def visit(v):
  if isinstance(v,dict):
   if set(v)=={'$ref_value'}:
    key=v['$ref_value']
    if key not in used:used.add(key);visit(definitions[key])
   else:
    for x in v.values():visit(x)
  elif isinstance(v,list):
   for x in v:visit(x)
 visit(encoded)
 return {'shared_values':{k:v for k,v in definitions.items() if k in used},'references':encoded}

def expand(bundle):
 def decode(v,stack=()):
  if isinstance(v,dict):
   if set(v)=={'$ref_value'}:
    key=v['$ref_value'];require(key not in stack,'SHARED_VALUE_CYCLE');return decode(bundle['shared_values'][key],stack+(key,))
   return {k:decode(x,stack) for k,x in v.items()}
  if isinstance(v,list):return [decode(x,stack) for x in v]
  return v
 return decode(bundle['references'])

def dev_overheads():
 cases=read(DEV/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==['A01','A02','A03','A04','A05'],'DEV_SCOPE_CHANGED')
 rows=[];bindings=[bind(DEV/'cases.json')]
 for case in cases:
  path=DEV/'prompts'/f"{case['anonymous_answer_id']}.txt";text=path.read_text(encoding='utf8');suffix=legacy.reference_suffix(case)
  require(text.endswith(suffix),'ORIGINAL_REFERENCE_SUFFIX_MISMATCH')
  prefix=text[:-len(suffix)];refs=canonical(case['references'])
  require(refs in suffix,'ORIGINAL_REFERENCE_JSON_CANONICAL_DIFFERENCE')
  overhead=len(suffix.encode('utf8'))-len(refs.encode('utf8'))
  rows.append({'answer_id':case['anonymous_answer_id'],'question_id':case['question_id'],
    'question_utf8_bytes':len(case['specific_question'].encode('utf8')),'answer_utf8_bytes':len(case['model_response'].encode('utf8')),
    'full_prompt_utf8_bytes':len(text.encode('utf8')),'nonreference_prompt_utf8_bytes':len(prefix.encode('utf8')),
    'original_reference_json_utf8_bytes':len(refs.encode('utf8')),'reference_wrapper_utf8_bytes':overhead,
    'original_context_bound':len(text.encode('utf8'))+8192+256,'new_context_measurement':False})
  bindings.append(bind(path))
 return rows,bindings

def main():
 socket.create_connection=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('OFFLINE_ONLY'))
 OUT.mkdir(parents=True,exist_ok=True)
 catalog=read(CAT);refs=catalog['references'];require(len(refs)==11,'CATALOG_EXPECTED_ELEVEN')
 inputs=[bind(CAT),bind(__file__),bind(Path(family.__file__)),bind(ROOT/'scripts/cce_alternative_q2_development.py'),bind(ROOT/'scripts/cce_stability_remediation_v2.py')]
 projected=[];audits=[];inventory=[];field_accounting=[]
 for r in refs:
  p,a=project_reference(r);require(restore_reference(p,a)==r,'LOSSLESS_REFERENCE_RESTORE_FAILED')
  require([(s['step_id'],s['text']) for s in p['steps']]==[(s['step_id'],s['text']) for s in r['steps']],'STEP_ID_TEXT_ORDER_CHANGED')
  required=['version_id','task_scope_bindings','initial_state','initial_sample_state','scope_stage_start','prerequisites','scoring_start_prerequisites']
  for key in required:
   if key in r:require(p[key]==r[key] or restore_reference(p,a)[key]==r[key],'REQUIRED_SCIENCE_FIELD_CHANGED')
  projected.append(p);audits.append(a)
  for key,value in r.items():
   direct=next((x for x in a['moved_provenance'] if x['path']==[key]),None)
   nested=[x for x in a['moved_provenance'] if x['path'][0]==key and len(x['path'])>1]
   field_accounting.append({'reference_id':r['reference_id'],'original_top_level_field':key,
     'disposition':'explicit_provenance_sidecar' if direct else 'retained_with_documented_nested_provenance_moves' if nested else 'retained_verbatim_or_uniform_scope_hoist',
     'original_value_sha256':rawsha(canonical(value)),'original_value_bytes':nbytes(value),
     'documented_nested_moves':len(nested),'full_value_after_restore_equal':restore_reference(p,a)[key]==value,
     'field_absence_not_created_or_filled':True})
  inventory.append({'reference_id':r['reference_id'],'method':r['comparison_method_id'],'version_id':r['version_id'],
    'question_ids':r['question_ids'],'steps':len(r['steps']),'raw_json_bytes':nbytes(r),'projected_json_bytes':nbytes(p),
    'moved_provenance_fields':len(a['moved_provenance']),'moved_scalar_values':sum(scalar_count(x['value']) for x in a['moved_provenance']),
    'roundtrip_original_object_exact':True,'step_text_id_order_exact':True,
    'scope_and_start_fields_present':[k for k in required if k in r],'scope_and_start_fields_absent_not_inferred':[k for k in required if k not in r],
    'formal_eligible':r['formal_eligible']})
 byid={r['reference_id']:p for r,p in zip(refs,projected)}
 overhead,devbindings=dev_overheads();inputs+=devbindings
 maxbase=max(x['nonreference_prompt_utf8_bytes'] for x in overhead);wrapper=max(x['reference_wrapper_utf8_bytes'] for x in overhead)
 projection_rows=[];pools=[];probe_rows=[]
 for qid in QIDS:
  for method in FAMILIES:
   answer={'question_id':qid,'model_response':'Chosen Method: '+method+'\nSYNTHETIC SIZE PROBE; NO BIOLOGICAL OPERATIONS.'}
   got,declared,version,pool=family.resolve(answer,refs)
   require(got==method and version['status']=='version_unspecified','GENERIC_ROUTE_POOL_PROBE_FAILED')
   selected=[byid[r['reference_id']] for r in pool];packed=factor(selected);require(expand(packed)==selected,'SHARED_VALUES_NOT_LOSSLESS')
   poolkey=f'q{qid}_{method.replace("+","plus")}';pooldir=OUT/'pool_payloads';pooldir.mkdir(exist_ok=True)
   write(pooldir/(poolkey+'_scientific.json'),selected);write(pooldir/(poolkey+'_factored.json'),packed)
   sizes={'raw_catalog_objects':nbytes(pool),'all_nonprovenance_science':nbytes(selected),
     'shared_value_factoring':nbytes(packed)+len(FACTOR_NOTE.encode('utf8'))}
   row={'question_id':qid,'method':method,'pool_n':len(pool),'reference_ids':[r['reference_id'] for r in pool],
     'version_ids':sorted({r['version_id'] for r in pool}),'steps_per_reference':[len(r['steps']) for r in pool],
     'generic_pool_only_not_actual_confirmation_selection':True,'scientific_task_applicability_confirmed':False}
   for name,size in sizes.items():
    bound=maxbase+wrapper+size+8192+256
    row.update({name+'_reference_bytes':size,name+'_dev_max_context_bound':bound,name+'_fits_dev_max_bound':bool(pool) and bound<=40960})
    row[name+'_fits_98304_dev_max_bound']=bool(pool) and bound<=CONFIGURED_CONTEXT
   pools.append(row)
   for aid in overhead:
    for name,size in sizes.items():
     bound=aid['nonreference_prompt_utf8_bytes']+wrapper+size+8192+256
     projection_rows.append({'size_probe_only':True,'question_id_scope':qid,'method':method,'pool_n':len(pool),
       'dev_envelope_answer_id':aid['answer_id'],'representation':name,'nonreference_prompt_bytes':aid['nonreference_prompt_utf8_bytes'],
       'references_with_representation_note_bytes':size,'reference_wrapper_bytes':wrapper,'output_reserve':8192,'template_reserve':256,
       'context_bound':bound,'historical_diagnostic_context':40960,'fits_40960_bound':bool(pool) and bound<=40960,
       'configured_context':CONFIGURED_CONTEXT,'fits_98304_bound':bool(pool) and bound<=CONFIGURED_CONTEXT,
       'empty_pool_is_not_coverage':not bool(pool)})
 # Explicit author aliases constrain pools; unsupported/ambiguous versions are not
 # filled by a generic family fallback. These are synthetic identity-only probes.
 for ref in refs:
  for alias in ref.get('version_aliases',[])[:1]:
   qid=ref['question_ids'][0];a={'question_id':qid,'model_response':'Chosen Method: '+ref['comparison_method_id']+'\n'+alias}
   method,declared,version,pool=family.resolve(a,refs)
   probe_rows.append({'kind':'explicit_frozen_author_alias','question_id':qid,'method':method,'alias':alias,
     'version_status':version['status'],'pool_reference_ids':[r['reference_id'] for r in pool]})
 for method in FAMILIES:
  a={'question_id':2,'model_response':'Chosen Method: '+method+'\nprotocol version: UNREGISTERED_SYNTHETIC_VERSION'}
  _,_,v,pool=family.resolve(a,refs);require(not pool,'UNKNOWN_EXPLICIT_VERSION_FALLBACK')
  probe_rows.append({'kind':'unsupported_explicit_version','method':method,'version_status':v['status'],'pool_n':0})
 (OUT/'catalog_snapshot.json').write_bytes(CAT.read_bytes())
 write(OUT/'projected_all_references.json',projected);write(OUT/'provenance_moves_and_scope_hoists.json',audits)
 write(OUT/'catalog_inventory.json',inventory);table(OUT/'catalog_inventory.csv',inventory)
 write(OUT/'field_accounting.json',field_accounting);table(OUT/'field_accounting.csv',field_accounting)
 write(OUT/'pool_matrix.json',pools);table(OUT/'pool_matrix.csv',pools)
 write(OUT/'context_components.json',projection_rows);table(OUT/'context_components.csv',projection_rows)
 write(OUT/'dev_prompt_overheads.json',overhead);write(OUT/'synthetic_version_pool_checks.json',probe_rows)
 (OUT/'shared_values_explanation.txt').write_text(FACTOR_NOTE,encoding='utf8')
 synthetic={'reference_id':'SOFTWARE_ONLY','steps':[{'step_id':'s1','text':'opaque action A','required_scope':'same'},
   {'step_id':'s2','text':'opaque action B','required_scope':'same'}],
   'initial_state':{'unregistered_scientific_field':{'start':3,'unknown':None}},
   'prerequisites':[{'text':'An unverified prerequisite','source_span':{'start':5,'end':8,'quote':'ABC','scientific_qualifier':'retain'}}]}
 sp,sa=project_reference(synthetic)
 require(restore_reference(sp,sa)==synthetic and sp['initial_state']==synthetic['initial_state'],'UNKNOWN_SCIENTIFIC_FIELD_LOSS')
 require(sp['prerequisites'][0]['source_span']=={'quote':'ABC','scientific_qualifier':'retain'},'SOURCE_QUOTE_OR_QUALIFIER_LOSS')
 mixed=copy.deepcopy(synthetic);mixed['steps'][1]['required_scope']='different';mp,ma=project_reference(mixed)
 require(not ma['uniform_required_scope_hoisted'] and restore_reference(mp,ma)==mixed,'NONUNIFORM_SCOPE_REWRITTEN')
 require(expand(factor([sp,sp]))==[sp,sp],'SYNTHETIC_SHARED_ROUNDTRIP')
 write(OUT/'projection_verification.json',{'status':'pass','actual_references_roundtrip':11,'actual_steps_unchanged':102,
   'top_level_fields_accounted':len(field_accounting),'all_original_fields_have_a_destination':True,
   'unknown_scientific_fields_default_retained':True,'anchor_quotes_and_scientific_qualifiers_retained':True,
   'uniform_scope_hoist_only':True,'mixed_scope_not_hoisted':True,'shared_values_roundtrip_exact':True,
   'scientific_applicability_or_prompt_comprehension_validated':False,'new_model_requests':0})
 summary={'status':'offline_reference_design_not_confirmation_freeze','catalog':bind(CAT),'reference_branches':11,'comparison_methods':len(FAMILIES),
   'qids':QIDS,'method_qid_cells':len(pools),'nonempty_method_qid_cells':sum(bool(r['pool_n']) for r in pools),
   'maximum_eligible_generic_pool':max(r['pool_n'] for r in pools),'maximum_true_versions_in_any_pool':max(len(r['version_ids']) for r in pools),
   'historical_answer_identity_bindings_explicitly_moved_to_provenance':True,
   'raw_catalog_utf8_bytes':CAT.stat().st_size,'raw_canonical_references_utf8_bytes':nbytes(refs),
   'nonprovenance_scientific_references_utf8_bytes':nbytes(projected),'max_development_nonreference_prompt_bytes':maxbase,
   'reference_wrapper_bytes':wrapper,'output_reserve':8192,'template_reserve':256,
   'available_reference_bytes_at_dev_max':40960-maxbase-wrapper-8192-256,
   'available_reference_bytes_at_98304_dev_max':CONFIGURED_CONTEXT-maxbase-wrapper-8192-256,
   'configured_context_root_preunsealing_decision':CONFIGURED_CONTEXT,
   'dev_max_fit_nonempty_pools':{name:sum(r['pool_n']>0 and r[name+'_fits_dev_max_bound'] for r in pools) for name in ['raw_catalog_objects','all_nonprovenance_science','shared_value_factoring']},
   'dev_max_fit_nonempty_pools_at_98304':{name:sum(r['pool_n']>0 and r[name+'_fits_98304_dev_max_bound'] for r in pools) for name in ['raw_catalog_objects','all_nonprovenance_science','shared_value_factoring']},
   'projection_11_original_objects_roundtrip_exact':True,'all_102_steps_text_ID_order_preserved':sum(len(r['steps']) for r in refs)==102,
   'top_level_fields_explicitly_accounted':len(field_accounting),
   'actual_step_count':sum(len(r['steps']) for r in refs),'absent_initial_or_prerequisite_fields_not_inferred':True,
   'shared_factoring_roundtrip_exact_in_all36_pools':True,'shared_factoring_model_comprehension_validated':False,
   'basis':'existing exposed five v3 prompt prefix envelopes; byte bound is conservative and not exact service tokenization',
   'future_v4_prompt_status':'not used; its removal of duplicate output-type catalog may change overhead, must be measured separately',
   'sealed_confirmation_fit_claimed':False,'actual_confirmation_answers_read':0,'new_model_requests':0,'new_embeddings':0,
   'confirmation_plan_or_release_created':False,'reference_policy_selected':False,'formal_eligible':False,
   'no_prompt_truncation_or_runtime_configuration_mutation':True,
   'actual_command':[sys.executable,*sys.argv],'inputs':inputs}
 write(OUT/'summary.json',summary)
 require(inputs==[bind(x['path']) for x in inputs],'INPUT_CHANGED_DURING_READONLY_DESIGN')
 print(canonical({k:v for k,v in summary.items() if k not in ['inputs','actual_command','catalog']}))

if __name__=='__main__':main()
