"""Remove the added reporter self-target encoding from a derived label view.

Native use remains source evidence. It is not a marker/target assertion. The
original EGES loop already supports a fluorophore key with an empty marker.
No original wire, source audit, legacy output, KB or numeric function changes.
"""
import copy
VERSION='native-fluor-key-only-original-loop-v1'


def apply_conversion(conversion,doc=None,case=None):
    if conversion.get('native_fluor_key_only_v1',{}).get('version')==VERSION:
        return copy.deepcopy(conversion)
    result=copy.deepcopy(conversion)
    projection=result['label_occurrence_projection']
    changes=[]
    for pair in projection['pairs']:
        if pair['kind']!='source_native_identity_encoding':
            continue
        if pair.get('reported_target_literal') is not None or pair['marker_literal']!=pair['fluor_literal']:
            raise ValueError('NATIVE_ENCODING_SHAPE_NOT_RECOGNIZED')
        original=copy.deepcopy(pair)
        pair['marker_literal']=None
        pair['kind']='source_native_fluor_key_only'
        pair['original_native_identity_encoding']=original
        pair['native_is_not_target_assertion']=True
        pair['original_loop_empty_marker']=True
        changes.append({'pair_id':pair['pair_id'],'entity_id':pair['entity_id'],
          'fluor_literal':pair['fluor_literal'],
          'before_original_function_input':{pair['fluor_literal']:pair['fluor_literal']},
          'after_original_function_input':{pair['fluor_literal']:''},
          'evidence':copy.deepcopy(pair['evidence']),
          'target_inferred':False,'scientific_compatibility_value_added':False})
    # Rebuild the inspection view. Unknown relations keep their own records and
    # publication uncertainty; they never become key-only merely by this rule.
    view={};losses=[]
    for name in sorted({p['fluor_literal'] for p in projection['pairs']}):
        rows=[p for p in projection['pairs'] if p['fluor_literal']==name]
        known={p['marker_literal'] for p in rows if p['marker_literal'] is not None}
        unresolved=[p['pair_id'] for p in rows if p['marker_literal'] is None and p['kind'] not in ('source_key_only','source_native_fluor_key_only')]
        if len(known)==1:view[name]=next(iter(known))
        elif not known:view[name]=''
        if len(known)>1 or unresolved:
            losses.append({'literal_name':name,'supported_targets':sorted(known),
              'unresolved_pair_ids':unresolved,'single_value_cannot_represent_full_occurrence_graph':True})
    projection['supported_local_dictionary_view']=view
    projection['single_value_projection_losses']=losses
    projection['lossless_single_value_projection']=not losses
    projection['native_fluor_key_only_processing']={'version':VERSION,'changes':changes,
      'source_native_declaration_preserved':True,'original_unknown_records_preserved':True}
    result['native_fluor_key_only_v1']={'version':VERSION,'changes':changes,
      'raw_modified':False,'source_audit_modified':False,'legacy_output_modified':False,
      'scores_modified_by_this_helper':False,'native_only_label_not_given_full_credit':True,
      'scope':'derived label projection only; original empty-marker loop semantics',
      'new_model_calls':0}
    for key in ['wire_payload','source_audit','legacy_projection','legacy_runner_payload','legacy_runner_content']:
        if key in conversion:assert result[key]==conversion[key]
    assert projection['explicit_label_uncertainties']==conversion['label_occurrence_projection']['explicit_label_uncertainties']
    return result
