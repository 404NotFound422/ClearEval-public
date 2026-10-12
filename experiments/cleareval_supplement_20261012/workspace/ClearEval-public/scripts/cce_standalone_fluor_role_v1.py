"""Development-only standalone fluor role projection; no target/KB inference."""
import copy,hashlib,re
VERSION='source-standalone-fluor-role-v1-development'
BAD=re.compile(r'\b(?:antibod\w*|secondary|primary|conjugat\w*|anti[- ]|optional\w*|alternativ\w*|not|without|instead|either)\b',re.I)
def proposal(pair,projection,doc):
    if pair.get('kind')!='unresolved_relation' or pair.get('raw_relation_status')!='unknown':return None
    if pair.get('marker_literal') is not None or pair.get('reported_target_literal') is not None:return None
    name=pair.get('fluor_literal');eid=pair.get('entity_id')
    if not isinstance(name,str) or not name.strip():return None
    occ=[x for x in projection['occurrences'] if x.get('entity_id')==eid]
    if len(occ)!=1:return None
    o=occ[0]
    if o.get('raw_kind')!='fluorophore' or o.get('source_affirmative_use') is not True or o.get('included_as_used_instance') is not True:return None
    if o.get('local_nonuse_audit',{}).get('excluded') is True:return None
    if any(x.get('fluor_literal')==name and (x.get('marker_literal') is not None or x.get('reported_target_literal') is not None) for x in projection['pairs']):return None
    literal=re.compile(r'(?<![\w-])'+re.escape(name)+r'(?![\w-])')
    action=re.compile(r'^\s*(?:[-*]\s*)?(?:\d+(?:\.\d+)*[.)]?\s+)?(?:Incubation\s+with|Incubate\s+with|Stain\s+with|Counterstain\s+with)\s+(?:1:\d+\s+)?'+re.escape(name)+r'(?![\w-])',re.I)
    mentions=[u for u in doc['units'] if literal.search(u['text'])]
    # An explicitly described antibody/conjugate or alternate usage is not
    # a standalone absence-of-target statement; no nearest-target propagation.
    if not mentions or any(BAD.search(u['text']) for u in mentions):return None
    operations=[u for u in mentions if action.search(u['text'])]
    if not operations:return None
    for u in operations:
        assert doc['text'][u['start']:u['end']]==u['text']
    return {'pair_id':pair['pair_id'],'entity_id':eid,'literal_name':name,
        'source_role':'affirmative_standalone_fluor_key_only','operation_evidence':copy.deepcopy(operations),
        'source_entity_evidence':copy.deepcopy(o['span']),
        'original_unknown_record_preserved':copy.deepcopy(pair),'target_added':False,
        'scientific_compatibility_added':False}

def apply_conversion(conversion,doc,case=None):
    if conversion.get('standalone_fluor_role_v1',{}).get('version')==VERSION:return copy.deepcopy(conversion)
    result=copy.deepcopy(conversion);p=result['label_occurrence_projection']
    assert hashlib.sha256(doc['text'].encode('utf8')).hexdigest()==doc['answer_sha256']==p['source_binding']['answer_sha256']
    assert doc['source_id']==p['source_binding']['source_id']
    changes=[]
    for pair in p['pairs']:
        change=proposal(pair,p,doc)
        if change:
            pair['kind']='source_key_only';pair['standalone_source_role_audit']=change
            changes.append(change)
    ids={x['pair_id'].split(':',1)[1] for x in changes}
    original=copy.deepcopy(p['explicit_label_uncertainties'])
    p['explicit_label_uncertainties']=[x for x in original if not (x.get('kind')=='reported_unresolved_relation' and x.get('relation_id') in ids)]
    view={};losses=[]
    for name in sorted({x['fluor_literal'] for x in p['pairs']}):
        rows=[x for x in p['pairs'] if x['fluor_literal']==name]
        known={x['marker_literal'] for x in rows if x['marker_literal'] is not None}
        unresolved=[x['pair_id'] for x in rows if x['marker_literal'] is None and x['kind'] not in ('source_key_only','source_native_fluor_key_only')]
        if len(known)==1:view[name]=next(iter(known))
        elif not known:view[name]=''
        if len(known)>1 or unresolved:losses.append({'literal_name':name,'supported_targets':sorted(known),'unresolved_pair_ids':unresolved,'single_value_cannot_represent_full_occurrence_graph':True})
    p.update(supported_local_dictionary_view=view,single_value_projection_losses=losses,lossless_single_value_projection=not losses)
    result['standalone_fluor_role_v1']={'version':VERSION,'changes':changes,'original_explicit_uncertainties':original,
        'raw_modified':False,'scores_recomputed':False,'posthoc_development_only':True,'new_calls':0}
    for key in ['wire_payload','source_audit','legacy_projection','legacy_runner_payload','legacy_runner_content']:
        if key in conversion:assert result[key]==conversion[key]
    return result
