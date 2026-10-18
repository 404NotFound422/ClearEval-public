#!/usr/bin/env python3
"""Restore exact old question/demand bindings only; does not make source/task choices."""
import argparse,json,pathlib
import runner as R

def build(pairs_path,questions_path,demand_path,manifest_path,out):
    from evaluation_contract import FixedDemandRegistry
    reg=FixedDemandRegistry(questions_path,demand_path,manifest_path);questions=R.read(questions_path);by={q['question_id']:q for q in questions};native=R.runtime();rows=[]
    for pair in R.read(pairs_path):
        q=by[pair['question_id']]
        if q['question']!=pair['specific_question']:raise ValueError('Original text differs from historical fixed-demand snapshot')
        h=R.digest(q);hier=q.get('tissue_hierarchy_from_tissue_xlsx',{})
        ri=native._resolve_tissue_ri_reference(hier.get('tissue_inferred',''))
        metadata={'tissue_tier_code':hier.get('tissue_tier_code',''),'tissue_inferred':hier.get('tissue_inferred',''),'tissue_ri_value':ri['value'],'tissue_ri_reference':ri,'marker_query_targets':q.get('marker_query_targets',[])}
        rows.append({'case_id':pair['candidate_id'],'question':q,'protocol':pair['model_response'],'question_sha256':h,'protocol_sha256':R.text_sha(pair['model_response']),
          'metadata_binding':{'question_sha256':h,'value':metadata,'origin':'ORIGINAL_QUESTION_FIELDS_PLUS_EXISTING_RI_TABLE_LOOKUP','object_id':None,
            'scope':'QUESTION_LEVEL_ONLY; must bind to an explicit evaluation object before executing','source_sha256':R.sha(questions_path),'ri_table_sha256':R.sha(R.SOURCE/'KnowledgeBase/tissue_ri.json')},
          'demand_binding':{'question_sha256':h,'value':reg.get(q['question_id'],q['question']),'origin':'EXACT_HISTORICAL_FIXED_DEMAND_REGISTRY','provenance':reg.provenance},
          'matching_contract':'bounded-quantity-presence-v1-20261018','evaluation_object':None,'reference':None,
          'readiness':'INPUT_BINDINGS_ONLY_NOT_EXECUTION_READY','remaining':['explicit object/route with original-text scope','same-original-task source evidence binding','approved source constructor','frozen encoder/judge configuration'],
          'not_recovered_B_identity':True,'no_new_model_encoder_or_score_calls':True})
    result={'schema_version':R.VERSION,'status':'BINDINGS_ONLY_NOT_FROZEN_OR_SCORED','cases':rows,'fixed_registry_provenance':reg.provenance,'input_files':{str(p):R.sha(p) for p in [pairs_path,questions_path,demand_path,manifest_path]},'model_calls':0,'encoder_calls':0,'score_calls':0}
    R.write(out,result);return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['pairs','questions','demand','demand-manifest','out']:p.add_argument('--'+k,required=True,type=pathlib.Path)
    a=p.parse_args();r=build(a.pairs,a.questions,a.demand,a.demand_manifest,a.out);print(json.dumps({'status':r['status'],'count':len(r['cases'])}))
