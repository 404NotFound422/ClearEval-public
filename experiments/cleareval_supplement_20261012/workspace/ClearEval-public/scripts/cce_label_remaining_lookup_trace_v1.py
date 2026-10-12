"""Trace stored-label unknowns to exact original KB columns, without scoring."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_offline_scoring_v1 as numeric
import cce_target_catalog_role_fix_v2 as fix
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=R2/'target_catalog_role_fix_v2/remaining_lookup_trace.json'
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def main():
    runner,registry=numeric.runtime();rows=[]
    for qid,method,full in [(22,'iDISCO+','Phalloidin-Alexa Fluor 647'),(22,'CUBIC','Phalloidin-Alexa Fluor 488')]:
        targets=runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]['marker_query_targets']
        method_key=runner.resolve_method(method,runner._method_fluoro_by_method)
        authored=runner._method_fluoro_by_method[method_key]
        related={k:v for k,v in authored.items() if 'phalloidin' in k.lower() or 'alexa' in k.lower() and ('488' in k or '647' in k)}
        mapped=runner._map_fluor_to_method_key(full)
        rows.append({'question_id':qid,'method':method,'source_complete_fluor_name':full,
          'normalized_full_name':runner._normalize_name(full),'existing_identity_candidates':sorted(runner._expand_marker_candidates(full)),
          'mapped_method_column':mapped,'original_method_lookup_value':runner._get_method_fluor_compat(method,full),
          'authored_related_columns_not_substituted':related,
          'full_normalized_key_present':any(runner._normalize_name(k)==runner._normalize_name(full) for k in authored),
          'native_GFP_marker_lookup':fix.marker_scope_lookup(runner,'GFP','GFP',targets),
          'native_GFP_method_lookup':{'column':runner._map_fluor_to_method_key('GFP'),'value':runner._get_method_fluor_compat(method,'GFP')},
          'interpretation':'Individual fluorophore and conjugate-reagent columns do not establish a value for the full compound without an authored mapping. No compound is split into aliases here.'})
    result={'status':'exact_lookup_trace_complete','records':rows,'no_score_recomputed':True,'no_KB_values_added':True,'new_model_requests':0,
      'bindings':[bind(Path(__file__)),bind(runner.__file__),bind(ROOT/'KnowledgeBase/method_fluro_compati.json'),bind(ROOT/'KnowledgeBase/tissue.json'),bind(fix.__file__)],
      'actual_command':'python scripts/cce_label_remaining_lookup_trace_v1.py'}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps([{'method':r['method'],'name':r['source_complete_fluor_name'],'mapped':r['mapped_method_column'],'related':r['authored_related_columns_not_substituted'],'native_scope_status':r['native_GFP_marker_lookup']['status']} for r in rows],ensure_ascii=True))
if __name__=='__main__':main()
