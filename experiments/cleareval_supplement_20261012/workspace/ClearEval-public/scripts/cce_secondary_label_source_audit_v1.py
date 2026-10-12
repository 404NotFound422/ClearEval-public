"""Read saved FPC09--16 source/label traces; never convert, score or request."""
from pathlib import Path
import ast, csv, hashlib, json, re, sys
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
SOURCE=R2/'secondary_E5_confirmation_v1'
OUT=R2/'secondary_label_source_diagnostic_v1'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p): return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def small(s): return {k:s[k] for k in ['unit_id','start','end','quote','answer_sha256'] if k in s}
def unit(doc,uid):
    x=next((u for u in doc['units'] if u['unit_id']==uid),None)
    if x is None:return None
    assert doc['text'][x['start']:x['end']]==x['text']
    return {'unit_id':uid,'start':x['start'],'end':x['end'],'quote':x['text'],'quote_sha256':hashlib.sha256(x['text'].encode()).hexdigest()}
def relationship(r):
    c=r.get('relation_clause_scope_audit') or {};e=r.get('declared_local_endpoint_occurrences') or {}
    return {**{k:r.get(k) for k in ['id','fluor_entity_id','target_entity_id','status','projection_allowed','mechanical_relation_state']},
      'evidence':small(r['evidence']),'clause_reason':c.get('reason'),
      'clauses':[{'source_clause':small(x['source_clause']),'reason':x.get('reason'),'projection_supported':x.get('projection_supported')} for x in c.get('candidate_clauses',[])],
      'endpoint_occurrences':{k:{q:v for q,v in (e.get(k) or {}).items() if q in ['valid','reason','occurrence','raw_substring_ordinal','span']} for k in ['fluor','target']},
      'both_endpoint_occurrences_valid':e.get('both_valid')}

def kb_index_audit():
    path=ROOT/'OEQ_run_grading_new.py';tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    # Execute only the original string normalizer, not the grading module.
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='_normalize_name')
    ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    norm=ns['_normalize_name'];kbpath=ROOT/'KnowledgeBase/tissue.json';rows=read(kbpath)
    fields=['推荐标志物 1','推荐标志物 2'];columns=['GFP/YFP','tdTomato/RFP ','DAPI/Hoechst','PI/Draq5 ','AlexaFluor 488','AlexaFluor 568/Cy3','AlexaFluor 647/Cy5 ','CD31','Lectin']
    index={}
    for i,row in enumerate(rows):
        for field in fields:
            name=row.get(field)
            if name:index.setdefault(norm(name),[]).append({'row_index':i,'marker_field':field,'authored_name':name,'scope':{k:row.get(k) for k in ['大类','亚类','结构/细胞类型']},'cells':{k:row.get(k) for k in columns}})
    duplicated={k:v for k,v in index.items() if len({r['row_index'] for r in v})>1}
    shadow=[];conflicts=[]
    for key,items in duplicated.items():
        last=items[-1]
        for col in columns:
            earlier=[r for r in items[:-1] if r['cells'][col] in (0,1)]
            values=sorted({r['cells'][col] for r in items if r['cells'][col] in (0,1)})
            if earlier and last['cells'][col] is None:
                shadow.append({'normalized_marker':key,'column':col,'earlier_authored_evidence':earlier,'last_row':last,'known_values':values,'scope_equivalence_verified':False})
            if len(values)>1:conflicts.append({'normalized_marker':key,'column':col,'values':values,'rows':items})
    from verified_marker_aliases import marker_identity_conflict
    helper_names=['_extract_parenthetical','_expand_marker_candidates','_map_fluor_to_tissue_col','_get_marker_fluor_compat']
    helper_nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in helper_names]
    aliases=next(n for n in tree.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='_MARKER_ALIASES')
    ns.update(re=re,marker_identity_conflict=marker_identity_conflict,_MARKER_ALIASES=ast.literal_eval(aliases.value),_FLUOR_TO_TISSUE_COL={})
    ns['_tissue_by_marker']={norm(row[field]):row for row in rows for field in fields if row.get(field)}
    exec(compile(ast.Module(body=helper_nodes,type_ignores=[]),str(path),'exec'),ns)
    lookups=[]
    for marker,fluor in [('MAP2','Alexa Fluor 488'),('NeuN','Alexa Fluor 594'),('NeuN (RBFOX3)','Alexa Fluor 594'),('NeuN (RBFOX3)','Alexa Fluor 488')]:
        candidates=ns['_expand_marker_candidates'](marker);column=ns['_map_fluor_to_tissue_col'](fluor)
        lookups.append({'marker':marker,'fluorophore':fluor,'exact_index_key':norm(marker),'exact_key_present':norm(marker) in index,
          'query_identity_candidates':sorted(candidates),'matching_index_keys':sorted(candidates & set(index)),
          'fluor_column':column,'original_lookup_value':ns['_get_marker_fluor_compat'](marker,fluor),
          'no_score_calculated':True})
    return {'source_bindings':[bind(path),bind(kbpath),bind(ROOT/'verified_marker_aliases.py')],'rows':len(rows),'unique_normalized_keys':len(index),
      'duplicate_keys':len(duplicated),'duplicate_key_rows':duplicated,'null_shadowed_key_columns':len(shadow),
      'null_shadowed_keys':len({r['normalized_marker'] for r in shadow}),'null_shadow_records':shadow,
      'conflicting_known_key_columns':conflicts,'MAP2_index_trace':index.get(norm('MAP2')),
      'NeuN_exact_key_present':norm('NeuN') in index,'NeuN_authored_rows':[r for v in index.values() for r in v if 'NeuN' in r['authored_name']],
      'external_fluor_mapping_file_exists':(ROOT/'workflow/s_label_audit/fluorophore_classification_for_review.json').exists(),
      'original_lookup_only_replays':lookups,
      'interpretation':'Last-row assignment loses earlier row information. This inventory does not establish equivalence of biological scopes and does not authorize maximum-value selection or fill absent columns.'}

def main():
    matrix=read(SOURCE/'matrix.json');assert [r['anonymous_answer_id'] for r in matrix]==['FPC%02d'%i for i in range(9,17)]
    records=[]
    for row in matrix:
        aid=row['anonymous_answer_id'];tid=row['planned_trial_id'];attempt=SOURCE/'run/attempts'/(tid+'_1')
        paths={'document':SOURCE/'source_documents'/(aid+'.json'),'raw':attempt/'raw_response.txt','components':attempt/'component_result.json','trial':SOURCE/'run/trials'/(tid+'.json')}
        doc=read(paths['document']);raw=read(paths['raw']);value=read(paths['components']);trial=read(paths['trial']);ex=raw['grounded_extraction']
        assert ex['source_id']==doc['source_id']
        assert hashlib.sha256(doc['text'].encode()).hexdigest()==doc['answer_sha256']
        cv=value.get('conversion',{});resolved=cv.get('source_audit',{}).get('resolved',{})
        lp=cv.get('label_occurrence_projection',{});calc=value.get('numeric',{}).get('occurrence_label_calculation',{})
        entity_ids={r.get('f') for r in ex['relations']}|{r.get('t') for r in ex['relations']}|{r.get('e') for r in ex['intrinsic_signals']}
        entities=[r for r in ex['entities'] if r['i'] in entity_ids or r['k'] in ['fluorophore','fluorescent_protein','target','antibody']]
        cited={r['u'] for r in entities}|{r['e'] for r in ex['relations']}|{r['u'] for r in ex['intrinsic_signals']}
        entry={'anonymous_answer_id':aid,'trial_id':tid,'status':trial.get('status'),'processing_status':value['processing_status'],
          'bindings':{k:bind(v) for k,v in paths.items()},'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],
          'metrics':value['metrics'],'raw_entities_label_relevant':entities,'raw_relations':ex['relations'],'raw_intrinsic_signals':ex['intrinsic_signals'],
          'raw_coverage':ex['coverage'],'cited_source_units':[unit(doc,u) for u in sorted(cited) if u.startswith('L')],
          'saved_resolved_relations':[relationship(r) for r in resolved.get('relations',[])],
          'saved_projection':{k:lp.get(k) for k in ['occurrences','pairs','native_audit','explicit_label_uncertainties','supported_local_dictionary_view','single_value_projection_losses']},
          'saved_label_calculation':calc,'full_failure':value.get('full_conversion_or_scoring_failure'),
          'record_errors':value.get('record_errors',[]),'duplicate_ids':value.get('duplicate_ids',{}),
          'name_binding_failures':value.get('name_binding_failures',[]),
          'label_dependency_view':{k:v for k,v in value.get('views',{}).get('label',{}).items() if k!='view_audit'},
          'partial_view_trace_limit':'Partial dependency views save metric/extraction and input hashes, not their occurrence-label calculation or resolved relation trace. Empty legacy marker_dict is not evidence the occurrence adapter discarded every relationship.' if not cv else None}
        save(OUT/(aid+'.json'),entry);records.append(entry)
    kb=kb_index_audit();save(OUT/'tissue_index_audit.json',kb)
    summary={'status':'read_only_saved_evidence_audit_complete','answers':8,'full_conversion':sum(r['processing_status']=='full_fieldwise_conversion' for r in records),
      'partial_dependency':sum(r['processing_status']=='partial_dependency_replay' for r in records),
      'numeric_label':sum(r['metrics']['s_label'] is not None for r in records),'numeric_label_ids':[r['anonymous_answer_id'] for r in records if r['metrics']['s_label'] is not None],
      'new_model_requests':0,'new_conversion_or_scoring_replay':0,'expert_validation':False,'matrix':bind(SOURCE/'matrix.json'),
      'code_bindings':[bind(Path(__file__)),bind(ROOT/'scripts/cce_label_occurrence_diagnostic_v1.py'),bind(ROOT/'scripts/cce_codex_fieldwise_replay_v2.py'),bind(ROOT/'scripts/cce_grounded_extraction_v11.py')],
      'outputs':[bind(OUT/(r['anonymous_answer_id']+'.json')) for r in records]+[bind(OUT/'tissue_index_audit.json')],
      'actual_command':'python scripts/cce_secondary_label_source_audit_v1.py','kb_duplicate_keys':kb['duplicate_keys'],'kb_null_shadowed_keys':kb['null_shadowed_keys'],'kb_null_shadowed_key_columns':kb['null_shadowed_key_columns']}
    save(OUT/'summary.json',summary)
    with (OUT/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['anonymous_answer_id','status','processing_status','s_label','raw_relations','accepted_saved_relations','full_failure'])
        w.writeheader()
        for r in records:w.writerow({'anonymous_answer_id':r['anonymous_answer_id'],'status':r['status'],'processing_status':r['processing_status'],'s_label':r['metrics']['s_label'],'raw_relations':len(r['raw_relations']),'accepted_saved_relations':sum(x['projection_allowed'] for x in r['saved_resolved_relations']) if r['processing_status']=='full_fieldwise_conversion' else None,'full_failure':(r['full_failure'] or {}).get('reason')})
    print(json.dumps({k:v for k,v in summary.items() if k not in ['outputs','code_bindings']},ensure_ascii=True))
if __name__=='__main__':main()
