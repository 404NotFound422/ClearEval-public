"""Posthoc typed record namespaces; raw IDs and all source gates are retained.

Only the record-uniqueness key changes from id to (record type, id).
The three copied functions retain the original source checks verbatim.
No model, batch reader, generation command, or original-file mutation exists.
"""
from cce_grounded_extraction_fieldwise_base_v1 import *
import cce_grounded_extraction_fieldwise_base_v1 as original
import cce_partial_components_v1 as partial

_expanded_schema = original._expanded_schema
_endpoint_occurrence_audit = original._endpoint_occurrence_audit
_selected_clause_endpoint_audit = original._selected_clause_endpoint_audit
ADAPTER_VERSION = 'typed-record-namespace-posthoc-v1'
BASE_SOURCE_SHA256 = '2656c2219b7af5f7495ba8297fa1fbdfea5224e06ce79d695159377f2f0180ca'


def _audit_expanded_payload(payload,doc):
    require(rawsha(doc['text'])==doc['answer_sha256'] and document(doc['text'],doc['source_id'])['units']==doc['units'],'DOCUMENT_HASH_OR_UNIT_BINDING')
    validate_shape(payload,_expanded_schema());integrity.validate_score_proposals(payload['scores'])
    g=payload['grounded_extraction'];require(g['source_id']==doc['source_id'],'SOURCE_ID_MISMATCH')
    registry=candidate_registry(doc);score_evidence=copy.deepcopy(payload['score_evidence'])
    require(len(score_evidence)==len(DIRECT) and {e['metric'] for e in score_evidence}==set(DIRECT),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    for e in score_evidence:
        e['answer_spans']=[resolve(s,doc,registry) for s in e['answer_spans']]
        if e['basis'] in ['observed','mixed']:require(bool(e['answer_spans']),'OBSERVED_SCORE_EVIDENCE_REQUIRES_SPAN')
        # An absence citation identifies inspected source scope; it is not a
        # claim that the missing parameter is present, nor proof of global absence.
        if e['basis']=='absence':
            e['citation_role']='checked_scope'
            e['absence_claim_verified']=False
            e['checked_scope_extent']='cited_units_only' if e['answer_spans'] else 'unspecified'
            e['rubric_application_verified']=False
        require(bool(e['rubric_basis'].strip()),'EMPTY_SCORE_RUBRIC_BASIS')
    result=copy.deepcopy(g);allids=set();used_spans=[]
    def resolved(ref):
        value=resolve(ref,doc,registry);used_spans.append(value);return value
    for group,fields in [('method_mentions',['supporting_evidence']),('entities',['supporting_evidence']),('relations',['evidence']),
        ('intrinsic_signals',['evidence']),('operations',['operation','duration','repeat_evidence','condition_evidence']),('total_time_claims',['duration']),('ri_mentions',['value'])]:
        for r in result[group]:
            require((group,r['id']) not in allids,'DUPLICATE_RECORD_ID');allids.add((group,r['id']))
            for field in fields:
                if r[field] is not None:
                    r[field]=resolved(r[field]);candidate=r[field].get('candidate_reference')
                    if field=='duration':require(candidate and candidate['kind']=='duration','CANDIDATE_KIND_NOT_DURATION_EVIDENCE')
                    if group=='ri_mentions' and field=='value':require(candidate and candidate['kind']=='ri_value_lead','CANDIDATE_KIND_NOT_RI_EVIDENCE')
                    if field=='operation' and candidate:require(candidate['kind']=='operation_span','CANDIDATE_KIND_NOT_OPERATION_EVIDENCE')
                    if field=='repeat_evidence':require(candidate and candidate['kind']=='repeat_literal','CANDIDATE_KIND_NOT_REPEAT_EVIDENCE')
            if 'literal_name' in r:
                r['name'],r['name_binding']=bind_literal_name(r['literal_name'],r['supporting_evidence'],doc,r['name_occurrence'])
                used_spans.append(r['name'])
    if result['timeline']['relation_evidence'] is not None:result['timeline']['relation_evidence']=resolved(result['timeline']['relation_evidence'])
    for r in result['coverage']['unresolved']:r['evidence']=resolved(r['evidence'])
    entities={e['id']:e for e in result['entities']};ops={o['id']:o for o in result['operations']}
    result['duplicate_literal_identity_audit']=[{'literal_name':name,'entity_ids':[e['id'] for e in result['entities'] if e['name']['quote']==name],
        'records_preserved_not_silently_merged':True,'semantic_equivalence_confirmed':False}
        for name in sorted({e['name']['quote'] for e in result['entities']}) if sum(e['name']['quote']==name for e in result['entities'])>1]
    for e in result['entities']:
        if e['usage']=='mentioned':e['mentioned_usage_support']=mentioned_usage_support(e)
    usage_gaps=[]
    for name in sorted({e['name']['quote'] for e in result['entities']}):
        if any(e['name']['quote']==name and e['usage']=='used' for e in result['entities']):continue
        for unit in doc['units']:
            if name not in unit['text'] or not affirmative_entity_use(name,unit['text']):continue
            context=resolve_span({'unit_id':unit['unit_id'],'quote':unit['text'].strip(),'occurrence':0},doc)
            if any(m['same_complete_literal'] for m in local_name_mentions(name,context,doc)):
                usage_gaps.append({'exact_name':name,'unit_id':unit['unit_id'],'start':unit['start'],'end':unit['end'],
                    'reason':'affirmative_source_occurrence_without_any_used_entity_record','model_usage_not_silently_overridden':True})
    result['affirmative_entity_usage_gaps']=usage_gaps
    for r in result['relations']:
        require(r['fluor_entity_id'] in entities and (r['target_entity_id'] is None or r['target_entity_id'] in entities),'RELATION_DANGLING_ENTITY')
        require(r['target_entity_id'] is not None or r['status'] in ['unknown','ambiguous'],'EXPLICIT_RELATION_REQUIRES_TARGET')
        f=entities[r['fluor_entity_id']];t=entities[r['target_entity_id']] if r['target_entity_id'] is not None else None
        mentions={'fluor':local_name_mentions(f['name']['quote'],r['evidence'],doc),
                  'target':local_name_mentions(t['name']['quote'],r['evidence'],doc) if t else []}
        r['relation_evidence_mentions']=mentions;r['primary_entity_spans_preserved']=True
        scope=relation_clause_support(f['name']['quote'],t['name']['quote'],r['evidence'],doc,result['entities']) if t else None
        r['relation_clause_scope_audit']=scope
        r['relation_local_mentions']=scope['selected_mentions'] if scope else mentions
        if t is None:ok,why=False,'unknown_target_endpoint_not_projected'
        elif not f['name_binding']['atomicity']['projection_eligible_provisional'] or not t['name_binding']['atomicity']['projection_eligible_provisional']:ok,why=False,'endpoint_name_atomicity_unresolved'
        elif f['kind'] not in ['fluorophore','fluorescent_protein']:ok,why=False,'label_endpoint_kind_unresolved'
        elif f['id']==t['id']:ok,why=False,'self_target_identity_not_supported'
        else:ok,why=scope['projection_supported'],scope['reason']
        r['projection_allowed']=r['status']=='explicit' and ok;r['mechanical_relation_state']=why
        r['entity_type_and_relation_role_distinct']=True
        r['unsupported_claim_retained_not_repaired']=r['status']=='explicit' and not r['projection_allowed']
    for record in result['intrinsic_signals']:
        require(record['entity_id'] in entities,'INTRINSIC_DANGLING_ENTITY')
        record['identity_policy']=intrinsic_policy(record,entities[record['entity_id']],result['relations'],doc,result['entities'])
    duration_spans=[]
    for o in result['operations']:
        op=o['operation']
        if o['duration']:
            d=o['duration'];op=o['operation']
            binding=record_binding(op,d,doc);o['duration_binding']=binding
            key=(d['start'],d['end']);require(key not in duration_spans,'REUSED_DURATION_DOUBLE_COUNT');duration_spans.append(key)
            literal=duration_value(d['quote']);o['raw_literal_parsed_duration']=literal
            nonadditive=next((r['kind'] for r in registry['records'] if r['kind'] in ['dimensional_expression_lead','recurrence_interval_lead'] and r['span']['start']==d['start'] and r['span']['end']==d['end']),None)
            o['parsed_duration']=literal if binding['valid'] and not nonadditive else {'state':nonadditive+'_not_operation_duration' if nonadditive else 'unresolved_operation_record_binding','bounds_hours':None,'unique_hours':None}
            o['legacy_overnight_comparison']=duration_value(d['quote'],8)
        else:o['parsed_duration']={'state':'missing','bounds_hours':None,'unique_hours':None}
        if o['phase']=='labeling_preparation':o['phase_support']=labeling_preparation_basis(o['operation'],doc)
        if o['repeat_evidence']:
            require(o['operation']['unit_id']==o['repeat_evidence']['unit_id'],'REPEAT_OUTSIDE_OPERATION_RECORD')
            o['repeat_source_binding']=repeat_source_binding(o['operation'],o['repeat_evidence'],doc,registry)
        if o['condition_evidence']:
            require(o['operation']['unit_id']==o['condition_evidence']['unit_id'],'CONDITION_OUTSIDE_OPERATION_RECORD')
        conditional_pattern=r'\bif\b|\bwhen needed\b|\bas needed\b|\bafter storage\b|\bre[- ]equilibrat\w*\b|\bagain\b|\brepeated\b|\bfuture\b|如需|如果|再次|再平衡|保存后'
        conditional_cue=re.search(conditional_pattern,o['operation']['context'],re.I)
        o['scope_gate']={'conditional_cue_detected':bool(conditional_cue),
            'conditional_scope_supported':bool(o['condition_evidence'] and re.search(conditional_pattern,o['condition_evidence']['quote'],re.I))}
        o['repeat_count']=repeat_count(o['repeat_evidence'])
        if o['repeat_evidence'] and not o['repeat_source_binding']['valid']:
            o['repeat_count']=None;o['repeat_uncertainty']='repeat_source_extent_binding_unresolved'
        if not o['repeat_evidence']:
            declarations=[r for r in registry['repeat_declarations'] if op['start']<=r['span']['start'] and r['span']['end']<=op['end']]
            if declarations:
                o['repeat_count']=None;o['repeat_uncertainty']='explicit_repetition_declaration_without_bound_P_reference'
                o['repeat_missing_reference_audit']={'source_declarations':copy.deepcopy(declarations),
                    'selected_operation_extent':{'start':op['start'],'end':op['end'],'unit_id':op['unit_id']},
                    'default_single_performance_withheld':True,'repeat_arithmetic_changed':False}
        repeat_context=o['operation']['context'] if o.get('duration_binding',{}).get('mode')=='same_source_record_unique_action_and_duration' else o['operation']['quote']
        if o['duration'] and re.search(r'\beach\b|每',repeat_context,re.I) and not o['repeat_evidence']:
            o['repeat_count']=None;o['repeat_uncertainty']='each_without_explicit_count'
    members=result['timeline']['operation_ids'];require(len(members)==len(set(members)) and set(members)<=set(ops),'TIMELINE_DUPLICATE_OR_DANGLING_OPERATION')
    result['timeline_proposal']=copy.deepcopy(result['timeline'])
    derived=[o['id'] for o in sorted(result['operations'],key=lambda x:x['operation']['start']) if o['phase'] in INCLUDE and o['execution_scope']=='initial']
    result['timeline']['operation_ids']=derived
    result['timeline_derivation']={'model_proposed_operation_ids':members,'program_initial_operation_ids':derived,
        'excluded_from_proposal':[i for i in members if i not in derived],'added_from_declared_initial_operations':[i for i in derived if i not in members],
        'same_members_and_order':members==derived,'raw_proposal_preserved':True,'phase_and_scope_semantics_verified':False}
    graph={k:[] for k in ops}
    for e in result['precedence_edges']:
        require(e['before_id'] in ops and e['after_id'] in ops,'EDGE_DANGLING_OPERATION');e['evidence']=resolved(e['evidence'])
        graph[e['before_id']].append(e['after_id'])
        e['direction_agrees_with_document_order']=ops[e['before_id']]['operation']['start']<ops[e['after_id']]['operation']['start']
        before,after=ops[e['before_id']]['operation'],ops[e['after_id']]['operation']
        same_unit=e['evidence']['unit_id']==before['unit_id']==after['unit_id']
        endpoints_covered=e['evidence']['start']<=before['start'] and before['end']<=e['evidence']['end'] and e['evidence']['start']<=after['start'] and after['end']<=e['evidence']['end']
        cue=bool(re.search(r'\bbefore\b|\bafter\b|\bthen\b|\bfollowed by\b|之后|之前|然后',e['evidence']['quote'],re.I))
        e['source_dependency_support']={'same_source_unit':same_unit,'both_operation_spans_covered':endpoints_covered,'explicit_dependency_cue':cue,
            'mechanically_supported':same_unit and endpoints_covered and cue,'adjacent_numbering_alone_sufficient':False}
        e['scientific_dependency_verified']=False;e['used_for_time_aggregation']=False
    done=set();active=set()
    def visit(node):
        require(node not in active,'CYCLIC_TIME_GRAPH')
        if node in done:return
        active.add(node)
        for child in graph[node]:visit(child)
        active.remove(node);done.add(node)
    cyclic=False
    try:
        for node in graph:visit(node)
    except ValueError as exc:
        require(str(exc)=='CYCLIC_TIME_GRAPH','UNEXPECTED_GRAPH_ERROR');cyclic=True
    result['precedence_audit']={'cyclic_model_proposal':cyclic,'backward_document_order_edges':sum(not e['direction_agrees_with_document_order'] for e in result['precedence_edges']),
        'unsupported_dependency_claims':sum(not e['source_dependency_support']['mechanically_supported'] for e in result['precedence_edges']),
        'model_edges_used_for_aggregation':False,'program_uses_declared_schedule_and_source_order_convention':True}
    inventory=copy.deepcopy(registry['records'])
    substantive=[s for o in result['operations'] for s in [o['duration']] if s]+[t['duration'] for t in result['total_time_claims']]
    unresolved=[r['evidence'] for r in result['coverage']['unresolved']]
    for r in inventory:
        s=r['span']
        cross_identity=exact_identity_mention_coverage(r,result['entities'],doc) if r['kind'] in ['numbered_name_lead','known_marker_name_lead'] else None
        if any(v['start']<=s['start'] and s['end']<=v['end'] for v in substantive if r['kind']=='duration'):state='covered_time_evidence'
        elif any(v['start']<=s['start'] and s['end']<=v['end'] for v in unresolved):state='explicitly_unresolved'
        elif r['kind'] in ['numbered_name_lead','known_marker_name_lead'] and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['entities']):
            matching=[v for v in result['entities'] if v['name']['start']<=s['start'] and s['end']<=v['name']['end']]
            eligible=[v for v in matching if v['name_binding']['atomicity']['projection_eligible_provisional']]
            state='entity_name_atomicity_unresolved' if not eligible else 'covered_entity_name' if any(v['usage']=='used' for v in eligible) else 'classified_entity_nonused_or_unknown'
        elif cross_identity and cross_identity['covered']:
            state='covered_repeated_exact_entity_identity';r['cross_mention_identity_coverage']=cross_identity
        elif r['kind']=='known_method_name_lead' and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['method_mentions']):state='classified_method_name'
        elif r['kind']=='dimensional_expression_lead':state='classified_non_duration_dimensional_expression'
        elif r['kind']=='recurrence_interval_lead':state='classified_non_additive_recurrence_interval'
        elif r['kind']=='action_section_heading_lead':state='source_section_heading_with_decimal_child_records'
        elif r['kind']=='operation_record_lead' and any(o['operation']['unit_id']==s['unit_id'] for o in result['operations']):state='covered_operation_record'
        elif r['kind'] not in ['duration','numbered_name_lead','known_marker_name_lead','known_method_name_lead'] and any(v['start']<=s['start'] and s['end']<=v['end'] for v in used_spans):state='covered_supplied_span'
        else:state='uncovered_candidate'
        r['coverage_state']=state
    return {'source_binding':{'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],'candidate_registry_sha256':registry['registry_sha256'],'enumerator_version':VERSION},'resolved':result,
            'score_evidence':score_evidence,'score_evidence_semantic_validity':'not_certified; source quotes do not establish correct rubric application',
            'inventory':inventory,'software_span_valid':True,'scientific_completeness_certified':False}

def audit_payload(payload,doc):
    expanded,endpoints=expand_wire_payload(payload,doc)
    audit=_audit_expanded_payload(expanded,doc);entities={r['id']:r for r in audit['resolved']['entities']}
    for relation in audit['resolved']['relations']:
        claimed=endpoints[relation['id']]
        f=_endpoint_occurrence_audit(entities[relation['fluor_entity_id']],relation['evidence'],claimed['fluor_occurrence'],doc)
        t=_endpoint_occurrence_audit(entities.get(relation['target_entity_id']),relation['evidence'],claimed['target_occurrence'],doc)
        fc=_selected_clause_endpoint_audit(f,'fluor',relation.get('relation_clause_scope_audit'))
        tc=_selected_clause_endpoint_audit(t,'target',relation.get('relation_clause_scope_audit'))
        valid=f['valid'] and t['valid'] and fc['valid'] and tc['valid']
        relation['declared_local_endpoint_occurrences']={'fluor':f,'target':t,'both_valid':valid,
            'policy_selected_clause_binding':{'fluor':fc,'target':tc},
            'original_pair_policy_also_required':True,'model_claims_not_repaired':True}
        if not valid:
            relation['projection_allowed']=False
            relation['mechanical_relation_state']='declared_local_endpoint_occurrences_not_supported'
            relation['unsupported_claim_retained_not_repaired']=relation['status']=='explicit'
    registry=candidate_registry(doc);known_units={r['span']['unit_id'] for r in registry['operation_candidates']}
    audit['operation_catalog_gaps']=[{'operation_id':r['id'],'unit_id':r['operation']['unit_id'],
        'reason':'model_identified_operation_in_unit_without_pre_enumerated_O','phase_not_inferred':True}
        for r in audit['resolved']['operations'] if r['operation']['unit_id'] not in known_units]
    audit['candidate_accounting']=candidate_accounting(audit,doc)
    audit['compact_wire_version']=VERSION
    return audit

def _convert_namespace(raw,doc):
    parsed=integrity.parse_judge_object(raw)
    expanded,endpoints=expand_wire_payload(parsed,doc)
    audit=audit_payload(parsed,doc);projection=project_legacy(audit)
    legacy={'scores':copy.deepcopy(parsed['scores']),'extraction':projection['extraction']}
    return {'raw_response_sha256':rawsha(raw),'raw_content_preserved':raw,'wire_payload':parsed,
        'wire_payload_sha256':rawsha(canonical(parsed)),'expanded_payload':expanded,
        'expanded_payload_sha256':rawsha(canonical(expanded)),'explicit_endpoint_selection':endpoints,
        'source_audit':audit,'legacy_projection':projection,'legacy_runner_payload':legacy,
        'legacy_runner_content':canonical(legacy),'transformation_is_explicit_not_raw_identity':True,
        'scores_preserved_exactly':legacy['scores']==parsed['scores'],'formal_eligible':False,'expert_confirmed':False}


REFERENCE_TARGET_TYPES = {
    'relations.f': 'entities', 'relations.t': 'entities',
    'intrinsic_signals.e': 'entities', 'timeline.o': 'operations',
    'precedence_edges.b': 'operations', 'precedence_edges.a': 'operations',
}


def namespace_audit(payload):
    """Expose typed keys separately; never replace an original string ID."""
    records = []
    by_literal = {}
    for group in partial.ARRAYS:
        for index, record in enumerate(payload['grounded_extraction'].get(group, [])):
            identifier = record.get('i') if isinstance(record, dict) else None
            row = {'record_type': group, 'raw_id': identifier,
                   'derived_internal_key': [group, identifier],
                   'raw_pointer': '/grounded_extraction/' + group + '/' + str(index)}
            records.append(row)
            if isinstance(identifier, str):
                by_literal.setdefault(identifier, []).append(row)
    collisions = []
    for identifier, occurrences in by_literal.items():
        if len(occurrences) > 1:
            types = [r['record_type'] for r in occurrences]
            collisions.append({'raw_id': identifier, 'occurrences': occurrences,
                'cross_type_only': len(types) == len(set(types)),
                'same_type_collision': len(types) != len(set(types))})
    return {'version': ADAPTER_VERSION, 'records': records, 'collisions': collisions,
        'reference_target_types': REFERENCE_TARGET_TYPES,
        'same_type_duplicates_rejected_even_if_equal': True,
        'raw_ids_renamed': False, 'records_deduplicated': False,
        'source_registry_ids_are_separate_typed_references': True,
        'semantic_source_validation_unchanged': True}


def convert(raw, doc):
    result = _convert_namespace(raw, doc)
    result['record_namespace_audit'] = namespace_audit(result['wire_payload'])
    return result


def records_audit(payload, doc, ground=original):
    """Reuse every local source check, replacing only global duplicate scope.

    The third return value lists typed conflicts rather than a global ID set.
    Callers must use ``dependency_has_duplicate`` so an unrelated record type
    cannot taint a component sharing the same literal ID.
    """
    rows, old_issues, _ = partial.records_audit(payload, doc, ground)
    typed = {}
    for row in rows:
        if isinstance(row['id'], str):
            typed.setdefault((row['group'], row['id']), []).append(row['pointer'])
    duplicates = {key: paths for key, paths in typed.items() if len(paths) > 1}
    issues = [x for x in old_issues if x.get('code') != 'DUPLICATE_GLOBAL_RECORD_ID'
              and x.get('pointer') not in {r['pointer'] for r in rows}]
    for row in rows:
        row['errors'] = [x for x in row['errors'] if x.get('code') != 'DUPLICATE_GLOBAL_RECORD_ID']
        key = (row['group'], row['id']) if isinstance(row['id'], str) else None
        row['derived_internal_key'] = list(key) if key else None
        row['same_type_duplicate'] = key in duplicates if key else False
        if row['same_type_duplicate']:
            row['errors'].append(partial.error(row['pointer'], 'DUPLICATE_RECORD_ID_WITHIN_TYPE',
                                              row['raw_record'], [row['group']]))
        row['valid_shape_and_local_source'] = not row['errors']
        issues.extend(row['errors'])
    conflicts = [{'record_type': key[0], 'raw_id': key[1], 'pointers': paths}
                 for key, paths in sorted(duplicates.items())]
    return rows, issues, conflicts


def dependency_has_duplicate(records, groups):
    return any(row['group'] in groups and row['same_type_duplicate'] for row in records)
