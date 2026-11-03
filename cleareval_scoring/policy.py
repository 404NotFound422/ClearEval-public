"""User-defined correctness: operations, sequence, critical materials and concentrations.

Other conditions are evidence for effectiveness assessment. Missing core facts
remain REVIEW; no unobserved fact is converted into a correct/incorrect label.
"""
from copy import deepcopy
from pathlib import Path
import sys


from . import component as engine

VERSION='cleareval-correctness-scope-20261102-v3'
CORE={'material_identity','action','polarity','execution_branch','stock_dilution',
      'internal_material_consistency','declared_process_order','reference_sequence'}
OTHER={'duration','temperature','pH','agitation'}
PROPERTY_FIELDS={'refractive_index_variant'}

def combine(states):
    return 'FAIL' if 'FAIL' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'PASS'

def is_core(field):
    return field in CORE or field.startswith(('concentration:','declared_recipe:'))

def project_recipe(audit):
    """Keep composition/ratio checks; remove physical-property checks before aggregation."""
    if audit.get('status') in ('NAME_ONLY','UNSUPPORTED'):
        return dict(status='NOT_APPLICABLE',claims=[],property_checks={})
    claims=[];properties={}
    for ci,claim in enumerate(audit.get('claims',[])):
        variants=[]
        for variant in claim.get('variants',[]):
            checks={k:v for k,v in variant['checks'].items() if k not in PROPERTY_FIELDS}
            for key,value in variant['checks'].items():
                if key in PROPERTY_FIELDS:
                    properties[f"claim{ci+1}:{variant.get('variant','')}:{key}"]=value
            variants.append(dict(variant=variant.get('variant',''),checks=checks,
                                 status=combine(list(checks.values())) if checks else 'NOT_APPLICABLE'))
        active=[v for v in variants if v['status']!='NOT_APPLICABLE']
        state=('NOT_APPLICABLE' if not active else 'PASS' if any(v['status']=='PASS' for v in active)
               else 'FAIL' if all(v['status']=='FAIL' for v in active) else 'UNKNOWN')
        claims.append(dict(status=state,variants=variants,claim=claim.get('claim',{})))
    active=[x['status'] for x in claims if x['status']!='NOT_APPLICABLE']
    return dict(status=combine(active) if active else 'NOT_APPLICABLE',claims=claims,property_checks=properties)

def project_packet(original):
    packet=deepcopy(original)
    packet.update(version=VERSION,engine_version=original['version'],
                  correctness_scope=['步骤/动作','顺序','关键试剂/配方组成','浓度/配比'],
                  check_scope=sorted(CORE)+['concentration:*','declared_recipe:composition_and_ratio'],
                  effectiveness_check_scope=['duration','temperature','pH','agitation','refractive_index_variant'],
                  effectiveness_status='NOT_ADJUDICATED',
                  effectiveness_note='参考条件比对保留为证据；样本适用性需另行判别，不直接作为有效性结论。')
    projected_recipes={k:project_recipe(a) for k,a in original['recipe_audit'].items()}
    packet['correctness_recipe_audit']=projected_recipes
    for mode in ['written','occurrence']:
        pairs=packet[mode]['pairs']
        for pair in pairs:
            correctness={};other={}
            for field,value in pair['checks'].items():
                if field.startswith('declared_recipe:'):
                    name=field.split(':',1)[1];audit=projected_recipes[name]
                    if audit['status']!='NOT_APPLICABLE':correctness[field]=audit['status']
                    for key,status in audit['property_checks'].items():other['recipe_property:'+name+':'+key]=status
                elif is_core(field):correctness[field]=value
                else:other[field]=value
            state=combine(list(correctness.values()))
            pair.update(legacy_all_conditions_status=pair['verification'],verification=state,checks=correctness,
                        correctness_checks=correctness,
                        correctness_status='REVIEW' if state=='UNKNOWN' else state,
                        effectiveness_reference_checks=other,
                        effectiveness_status='NOT_ADJUDICATED')
        old=packet[mode]['metrics'];confirmed=sum(p['count'] for p in pairs if p['correctness_status']=='PASS')
        pending=sum(p['count'] for p in pairs if p['correctness_status']=='REVIEW')
        failed=sum(p['count'] for p in pairs if p['correctness_status']=='FAIL')
        def ratio(n,d):return n/d if d else None
        metrics=dict(N_R=old['N_R'],N_C=old['N_C'],operation_SR=old['operation_SR'],operation_SP=old['operation_SP'],
                     confirmed_correct_credit=confirmed,correctness_review_credit=pending,explicit_wrong_credit=failed,
                     matched_credit=sum(p['count'] for p in pairs),reference_unmatched=old['N_R']-sum(p['count'] for p in pairs),
                     candidate_unmatched=old['N_C']-sum(p['count'] for p in pairs))
        for key,den in [('Bio_SR',old['N_R']),('Bio_SP',old['N_C'])]:
            lo,hi=ratio(confirmed,den),ratio(confirmed+pending,den)
            if not original['scope_complete']:lo=hi=None
            metrics['correctness_'+key+'_lower']=lo
            metrics['correctness_'+key+'_upper']=hi
            metrics['correctness_'+key]=lo if pending==0 else None
        packet[mode]['legacy_all_conditions_metrics']=old
        packet[mode]['metrics']=metrics
    return packet

def score_branch(case):
    from . import resolution, robustness
    resolution.install(engine)
    robustness.install(engine)
    normalized=robustness.normalize_case(case)
    packet=project_packet(engine.score_branch(normalized))
    packet['resolution_version']=resolution.VERSION
    packet['robustness_version']=robustness.VERSION
    packet['answer_surface_edits']=normalized.get('_answer_surface_edits',[])
    return packet

def apply_to_result(result,case):
    output=deepcopy(result)
    output.setdefault('supplementary_components',{})['correctness_scope_v1']=score_branch(case)
    return output
