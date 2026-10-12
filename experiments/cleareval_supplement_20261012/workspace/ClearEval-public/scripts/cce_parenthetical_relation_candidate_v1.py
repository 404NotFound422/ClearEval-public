"""Restore an already-declared target (fluor) pair in a chosen-label field.

No entities, aliases, KB values or model claims are created. Native declarations
are not this rule. Both typed endpoints and their original exact source positions
must already exist. Original wire/source audit remains intact.
"""
import copy,re
VERSION='parenthetical-typed-selected-label-pair-v1'
_DISQUALIFY=re.compile(r'\b(?:not|no|never|without|avoid|omit|neither|either|or|alternative|optional(?:ly)?|if|unless|may|might|can|native|endogenous|intrinsic)\b|\bfor\s+example\b|\bsuch\s+as\b|\be\.g\.',re.I)
_CHOSEN=re.compile(r'(?:chosen|selected)\s+label(?:l?ing)?\s*[:：]',re.I)

def candidate_for_relation(relation,entities,doc):
    if relation.get('status')!='explicit' or relation.get('projection_allowed'):return None
    f=entities.get(relation.get('fluor_entity_id'));t=entities.get(relation.get('target_entity_id'))
    if not f or not t or f['kind']!='fluorophore' or t['kind']!='target':return None
    if f['usage']!='used' or t['usage']!='used':return None
    endpoint=relation.get('declared_local_endpoint_occurrences',{})
    if not endpoint.get('both_valid'):return None
    fs=endpoint['fluor']['span'];ts=endpoint['target']['span']
    if fs['unit_id']!=ts['unit_id'] or fs['start']<=ts['end']:return None
    unit=next((u for u in doc['units'] if u['unit_id']==fs['unit_id']),None)
    if unit is None:return None
    text=unit['text']
    if not _CHOSEN.search(text) or _DISQUALIFY.search(text):return None
    for entity,s in [(f,fs),(t,ts)]:
        if not endpoint['fluor' if entity is f else 'target']['valid']:return None
        if s['answer_sha256']!=doc['answer_sha256'] or doc['text'][s['start']:s['end']]!=entity['literal_name']:return None
    pattern=re.compile(re.escape(t['literal_name'])+r'\s*\(\s*'+re.escape(f['literal_name'])+r'\s*\)')
    found=list(pattern.finditer(text))
    if len(found)!=1:return None
    m=found[0];a=unit['start']+m.start();b=unit['start']+m.end()
    if a!=ts['start'] or not re.fullmatch(r'\s*\(\s*',doc['text'][ts['end']:fs['start']]) or not re.fullmatch(r'\s*\)',doc['text'][fs['end']:b]):return None
    return {'rule':VERSION,'target_entity_id':t['id'],'fluor_entity_id':f['id'],
      'literal_target':t['literal_name'],'literal_fluor':f['literal_name'],
      'source_span':{'unit_id':unit['unit_id'],'start':a,'end':b,'quote':doc['text'][a:b],'answer_sha256':doc['answer_sha256']},
      'target_span':copy.deepcopy(ts),'fluor_span':copy.deepcopy(fs),
      'typed_roles_are_model_claims_not_expert_gold':True,'new_entity_or_KB_value':False}

def apply_conversion(conversion,doc,case=None):
    result=copy.deepcopy(conversion)
    if result.get('parenthetical_relation_candidate_v1',{}).get('version')==VERSION:return result
    assert conversion['source_audit']['source_binding']['answer_sha256']==doc['answer_sha256']
    g=conversion['source_audit']['resolved'];entities={e['id']:e for e in g['entities']};p=result['label_occurrence_projection'];applied=[]
    for relation in g['relations']:
        candidate=candidate_for_relation(relation,entities,doc)
        if candidate is None:continue
        pair=next((x for x in p['pairs'] if x['pair_id']=='relation:'+relation['id']),None)
        if pair is None or pair['kind']!='unresolved_relation':continue
        target=candidate['literal_target']
        other={x['marker_literal'] for x in p['pairs'] if x['entity_id']==pair['entity_id'] and x['pair_id']!=pair['pair_id'] and x.get('marker_literal') is not None}
        if other and other!={target}:continue
        pair['original_parenthetical_projection']=copy.deepcopy(pair)
        pair.update(marker_literal=target,kind='supported_relation',evidence=copy.deepcopy(candidate['source_span']),parenthetical_source_derivation=candidate)
        p['explicit_label_uncertainties']=[x for x in p['explicit_label_uncertainties'] if not (x.get('kind')=='reported_unresolved_relation' and x.get('relation_id')==relation['id'])]
        applied.append({'record_id':relation['id'],'candidate':candidate})
    if applied:
        view={};losses=[]
        for name in sorted({x['fluor_literal'] for x in p['pairs']}):
            rr=[x for x in p['pairs'] if x['fluor_literal']==name];known={x['marker_literal'] for x in rr if x['marker_literal'] is not None}
            unknown=[x['pair_id'] for x in rr if x['marker_literal'] is None and x['kind'] not in ('source_key_only','source_native_fluor_key_only')]
            if len(known)==1:view[name]=next(iter(known))
            elif not known:view[name]=''
            if len(known)>1 or unknown:losses.append({'literal_name':name,'supported_targets':sorted(known),'unresolved_pair_ids':unknown})
        p.update(supported_local_dictionary_view=view,single_value_projection_losses=losses,lossless_single_value_projection=not losses)
    result['parenthetical_relation_candidate_v1']={'version':VERSION,'applied':applied,'raw_modified':False,'resolved_claims_modified':False,'new_model_calls':0,'KB_values_added':False}
    assert result['wire_payload']==conversion['wire_payload'] and result['source_audit']==conversion['source_audit']
    return result
