"""Explicit post-hoc source reattachment; never rewrites model output or KB.

The three rules return derived occurrence records with source offsets. They
repair source selection/omission, not compatibility, target specificity, or
scientific applicability. A frozen v3 result is always retained by the caller.
"""
import copy
import hashlib
import re

import cce_posthoc_source_backend_v3 as backend
import cce_label_occurrence_diagnostic_v1 as labels

VERSION = 'source-binding-candidate-v1'
_DISQUALIFY = re.compile(r"\b(?:not|never|without|avoid|omit|neither|either|or|alternative|optional(?:ly)?|if|unless|may|might|can)\b|\bfor\s+(?:example|illustration)\b|\bsuch\s+as\b|\be\.g\.|不使用|不采用|备选|可选|如果|例如|比如", re.I)
_GLOBAL = re.compile(r'^\s*(?:\*\*)?(?:if|unless|either|neither)\b', re.I)
_NATIVE = r'(?:endogenous|native|intrinsic)'


def _span(doc, unit, start=None, end=None):
    a=unit['start'] if start is None else start
    b=unit['end'] if end is None else end
    return {'unit_id':unit['unit_id'],'start':a,'end':b,'quote':doc['text'][a:b],
      'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],
      'context_start':a,'context_end':b,'context':doc['text'][a:b]}


def _sentences(doc, unit):
    text=unit['text'];cuts=[0]
    for match in re.finditer(r'[.!?](?:\s+)(?=[A-Z])|;\s*',text):
        # Do not detach the proposition from its literal e.g. qualification.
        if text[:match.start()+1].lower().endswith(('e.g.','i.e.')):continue
        cuts.append(match.end())
    cuts.append(len(text))
    for a,b in zip(cuts,cuts[1:]):
        while a<b and text[a].isspace():a+=1
        while b>a and text[b-1].isspace():b-=1
        if a<b:yield _span(doc,unit,unit['start']+a,unit['start']+b)


def _complete(name, evidence, doc):
    return [m for m in backend.local_name_mentions(name,evidence,doc) if m['same_complete_literal']]


def _compact(s):
    return {k:s[k] for k in ['unit_id','start','end','quote','answer_sha256']}


def explicit_pair_candidates(fluor, target, doc, entities):
    """Only the unchanged relation policy can approve an existing claimed pair."""
    candidates=[]
    for unit in doc['units']:
        if fluor not in unit['text'] or target not in unit['text']:continue
        evidence=_span(doc,unit)
        audit=backend.relation_clause_support(fluor,target,evidence,doc,entities)
        if not audit['projection_supported']:continue
        selected=audit['candidate_clauses'][audit['selected_clause_index']]
        clause=selected['source_clause'];a,b=clause['start'],clause['end']
        candidates.append({'evidence':_span(doc,unit,a,b),'original_relation_policy':audit,
          'endpoint_spans':copy.deepcopy(audit['selected_mentions']),
          'rule':'existing_exact_endpoint_pair_original_policy_unique_source'})
    return candidates


def visualization_target_candidates(fluor, doc):
    """Read a literal object of one explicit predicate; no KB/adjacency inference."""
    candidates=[]
    pattern=re.compile(r'\buse\s+of\s+'+re.escape(fluor)+
      r'\s+allows\s+for\s+visualization\s+of\s+(?P<target>[^,.;:!?\n]+?)(?=\s+(?:in|on|within|to|for|while|which|that)\b|[,.;:!?\n]|$)',re.I)
    for unit in doc['units']:
        if fluor not in unit['text'] or _GLOBAL.search(unit['text']):continue
        for evidence in _sentences(doc,unit):
            if _DISQUALIFY.search(evidence['quote']):continue
            for match in pattern.finditer(evidence['quote']):
                literal=match.group('target').strip()
                if not literal or len(literal)>80 or re.search(r'\b(?:and|both|respectively)\b|[,;\[\]]',literal,re.I):continue
                a=evidence['start']+match.start('target');b=evidence['start']+match.end('target')
                while a<b and doc['text'][a].isspace():a+=1
                while b>a and doc['text'][b-1].isspace():b-=1
                target_span=_span(doc,unit,a,b)
                atomic=backend.name_atomicity(literal,evidence)
                fm,tm=_complete(fluor,evidence,doc),_complete(literal,evidence,doc)
                if not atomic['projection_eligible_provisional'] or len(fm)!=1 or len(tm)!=1:continue
                if (tm[0]['start'],tm[0]['end'])!=(a,b):continue
                candidates.append({'literal_target':literal,'evidence':evidence,
                  'target_span':target_span,'fluor_span':fm[0],
                  'rule':'explicit_use_allows_visualization_of_exact_object',
                  'derived_entity_not_a_model_return':True,'KB_or_alias_used':False})
    return candidates


def native_declaration_candidates(entity, doc):
    """A chosen occurrence plus a unique actual-use native declaration.

    Broad preservation/capability phrases are deliberately not this rule. No
    cellular target or chemical self-binding relation is inferred.
    """
    name=entity['literal_name'];nonuse=labels._explicit_nonuse(entity)
    chosen=bool(re.search(r'(?:chosen|selected)\s+(?:label(?:l?ing)?|marker|signal)s?\s*[:：]',entity['name']['context'],re.I))
    if not chosen or nonuse['excluded'] or not backend.affirmative_entity_use(name,entity['name']['context']):return []
    pattern=re.compile(r'\b(?:combination\s+of|use(?:d)?(?:\s+of)?|using|selected|chosen)\s+'+_NATIVE+r'\s+'+re.escape(name)+r'(?![\w+\-/])',re.I)
    candidates=[]
    for unit in doc['units']:
        if name not in unit['text'] or _GLOBAL.search(unit['text']):continue
        for evidence in _sentences(doc,unit):
            if _DISQUALIFY.search(evidence['quote']) or not pattern.search(evidence['quote']):continue
            mentions=_complete(name,evidence,doc)
            if len(mentions)!=1:continue
            candidates.append({'evidence':evidence,'name_span':mentions[0],
              'chosen_evidence':copy.deepcopy(entity['name']),
              'rule':'chosen_same_literal_and_unique_explicit_native_use_sentence',
              'raw_kind_preserved':entity['kind'],'biological_target_inferred':False,
              'scientific_preservation_confirmed':False})
    return candidates


def derive_candidates(conversion,doc):
    """Return proposals only; ambiguous/absent proposals remain visible."""
    g=conversion['source_audit']['resolved'];entities={e['id']:e for e in g['entities']}
    if conversion['source_audit']['source_binding']['answer_sha256']!=doc['answer_sha256']:
        raise ValueError('SOURCE_DOCUMENT_MISMATCH')
    proposals=[]
    for rr in g['relations']:
        if rr.get('projection_allowed'):continue
        ent=entities.get(rr['fluor_entity_id'])
        if not ent or labels._explicit_nonuse(ent)['excluded']:continue
        target=entities.get(rr.get('target_entity_id'))
        if target and rr['status']=='explicit':
            found=explicit_pair_candidates(ent['literal_name'],target['literal_name'],doc,list(entities.values()))
            kind='reattach_existing_pair'
        elif rr.get('target_entity_id') is None and rr['status']=='unknown':
            found=visualization_target_candidates(ent['literal_name'],doc)
            kind='derive_missing_target_from_explicit_predicate'
        else:continue
        proposals.append({'kind':kind,'record_id':rr['id'],'entity_id':ent['id'],
          'raw_record':copy.deepcopy(rr),'candidate_count':len(found),'candidates':found,
          'apply_unique_source_candidate':len(found)==1})
    projection=conversion['label_occurrence_projection']
    native_prior={x['record_id']:x for x in projection['native_audit']}
    for rr in g['intrinsic_signals']:
        if rr['status']!='source_declared' or native_prior.get(rr['id'],{}).get('native_identity_encoding_allowed'):continue
        ent=entities[rr['entity_id']];policy=rr['identity_policy']
        competing=[x for x in g['relations'] if x['fluor_entity_id']==ent['id'] and x['projection_allowed'] and x.get('target_entity_id') and entities[x['target_entity_id']]['literal_name']!=ent['literal_name']]
        found=[] if policy['source_conflicts'] or competing or not policy['atomic_name_projection_eligible'] else native_declaration_candidates(ent,doc)
        proposals.append({'kind':'reattach_native_declaration','record_id':rr['id'],'entity_id':ent['id'],
          'raw_record':copy.deepcopy(rr),'candidate_count':len(found),'candidates':found,
          'apply_unique_source_candidate':len(found)==1})
    return {'version':VERSION,'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],
      'proposals':proposals,'raw_modified':False,'new_scientific_values':False,'new_model_calls':0}


def apply_conversion(conversion,doc,case=None):
    """Overlay only label projection; wire, resolved records and scores unchanged."""
    if conversion.get('source_binding_candidate_v1',{}).get('version')==VERSION:
        if conversion['source_audit']['source_binding']['answer_sha256']!=doc['answer_sha256']:
            raise ValueError('SOURCE_DOCUMENT_MISMATCH')
        return copy.deepcopy(conversion)
    result=copy.deepcopy(conversion);audit=derive_candidates(conversion,doc)
    p=result['label_occurrence_projection'];g=conversion['source_audit']['resolved']
    entities={e['id']:e for e in g['entities']};applied=[]
    for proposal in audit['proposals']:
        if not proposal['apply_unique_source_candidate']:continue
        candidate=proposal['candidates'][0];rid=proposal['record_id'];eid=proposal['entity_id'];kind=proposal['kind']
        if kind=='reattach_native_declaration':
            name=entities[eid]['literal_name'];pair_id='native:'+rid
            if any(x['pair_id']==pair_id for x in p['pairs']):continue
            # An empty-key-only placeholder is replaced only for this same
            # occurrence. Other unknown records and same-name uses are retained.
            p['pairs']=[x for x in p['pairs'] if not (x['entity_id']==eid and x['kind']=='source_key_only')]
            p['pairs'].append({'pair_id':pair_id,'entity_id':eid,'fluor_literal':name,'marker_literal':name,
              'reported_target_literal':None,'scope':'this_source_occurrence_only','kind':'source_native_identity_encoding',
              'evidence':_compact(candidate['evidence']),'target_propagated_to_other_occurrence':False,
              'biological_target_inferred':False,'derived_source_binding':copy.deepcopy(candidate)})
            for row in p['native_audit']:
                if row['record_id']==rid:
                    row['original_source_binding_before_candidate']=copy.deepcopy(row)
                    row['native_identity_encoding_allowed']=True;row['source_declared_signal_mode']='native'
                    row['evidence']=_compact(candidate['evidence']);row['derived_source_binding']=copy.deepcopy(candidate)
            p['explicit_label_uncertainties']=[x for x in p['explicit_label_uncertainties'] if not (x.get('kind')=='reported_unresolved_native_record' and x.get('record_id')==rid)]
        else:
            pair=next((x for x in p['pairs'] if x['pair_id']=='relation:'+rid),None)
            if pair is None:continue
            target=(entities[proposal['raw_record']['target_entity_id']]['literal_name'] if kind=='reattach_existing_pair' else candidate['literal_target'])
            other_targets={x['marker_literal'] for x in p['pairs'] if x['entity_id']==eid and x['pair_id']!=pair['pair_id'] and x.get('marker_literal') is not None}
            if other_targets and other_targets!={target}:
                proposal['not_applied_reason']='same_occurrence_distinct_supported_target_conflict';continue
            pair['original_projection_before_candidate']=copy.deepcopy(pair)
            pair['marker_literal']=target;pair['kind']='supported_relation';pair['evidence']=_compact(candidate['evidence'])
            pair['derived_source_binding']=copy.deepcopy(candidate)
            p['explicit_label_uncertainties']=[x for x in p['explicit_label_uncertainties'] if not (x.get('kind')=='reported_unresolved_relation' and x.get('relation_id')==rid)]
        applied.append({'kind':kind,'record_id':rid,'entity_id':eid,'evidence':_compact(candidate['evidence'])})
    # Rebuild only the display dictionary from the same occurrence pairs; this
    # does not feed the scorer, which still evaluates every pair independently.
    view={};losses=[]
    for name in sorted({x['fluor_literal'] for x in p['pairs']}):
        rows=[x for x in p['pairs'] if x['fluor_literal']==name]
        known={x['marker_literal'] for x in rows if x['marker_literal'] is not None};unknown=[x['pair_id'] for x in rows if x['marker_literal'] is None]
        if len(known)==1:view[name]=next(iter(known))
        elif not known:view[name]=''
        if len(known)>1 or unknown:losses.append({'literal_name':name,'supported_targets':sorted(known),'unresolved_pair_ids':unknown,'single_value_cannot_represent_full_occurrence_graph':True})
    p['supported_local_dictionary_view']=view;p['single_value_projection_losses']=losses;p['lossless_single_value_projection']=not losses
    p['source_binding_candidate_audit']={**audit,'applied':applied,'original_projection_preserved_in_input':True}
    result['source_binding_candidate_v1']={'version':VERSION,'applied':applied,'raw_modified':False,'scores_modified':False,'KB_values_added':False,'posthoc_not_model_quality':True}
    assert result['wire_payload']==conversion['wire_payload']
    assert result['source_audit']==conversion['source_audit']
    return result
