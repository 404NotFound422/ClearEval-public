"""DRAFT: strict component-scoped audit and original numeric dependency propagation.

No provider invocation, archive reader, batch rescore or approval writer exists.
Validation views are explicitly synthetic scaffolding, never repaired model raw.
Original source, all raw records and component-specific retained fields are saved.
An upstream failed observation is never reclassified as a full technical success.
"""
from __future__ import annotations
import argparse
import copy
import importlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_grounded_offline_scoring_v1 as original
import evaluator_integrity as integrity
j = original.j
VERSION = 'strict-partial-components-v1-draft'
DIRECT = original.DIRECT
EGES = original.EGES
GROUP = {'c_param': 'completeness', **{k: 'correctness' for k in DIRECT[1:]}}
ARRAYS = ['method_mentions', 'entities', 'relations', 'intrinsic_signals', 'operations', 'total_time_claims', 'ri_mentions']
DEPENDENCIES = {
    **{m: ['shared_identity', '/scores/' + GROUP[m] + '/' + m, '/score_evidence[metric=' + m + ']'] for m in DIRECT},
    's_method': ['shared_identity', 'complete_method_mentions', 'fixed_question_demand_and_method_vector'],
    's_trans': ['shared_identity', 'complete_method_mentions', 'fixed_question_tier_and_tissue_RI', 'fixed_method_RI_sigma_time_KB'],
    's_time': ['shared_identity', 'complete_method_mentions', 'all_operations_durations_repeats_phases_scopes', 'timeline_totals_full_source_coverage', 'fixed_tier_time_KB'],
    's_label': ['shared_identity', 'complete_method_mentions', 'entity_relation_intrinsic_graph', 'entity_coverage_and_identity_conflicts', 'fixed_target_and_compatibility_KB'],
    'Com': ['sr', 'c_param'], 'Cor': DIRECT[1:], 'Eff': EGES, 'IA': ['Com', 'Cor', 'Eff'], 'HV': ['Com', 'Cor', 'Eff'],
}


def require(value, why):
    if not value: raise ValueError(why)


def error(pointer, code, raw=None, scope=None):
    return {'pointer': pointer, 'code': str(code), 'raw_record': copy.deepcopy(raw), 'affected_scope': scope or [],
            'record_removed_from_original': False, 'scientific_error_proven': False}


def backend_science(backend):
    return getattr(backend, 'BACKEND', backend)


def shared_gate(raw, doc, case, backend, envelope):
    """Caller supplies actual committed provider/request/identity objects, not a pass flag."""
    ground = backend.grounded
    require(envelope['upstream_technical_status'] in ['success', 'failed', 'software_only_not_executed'], 'UPSTREAM_STATUS_REQUIRED')
    require(envelope['actual_request_made'] is True, 'COMPLETED_PROVIDER_REQUEST_REQUIRED')
    require(envelope['planned_identity'] == envelope['trial_identity'], 'TRIAL_IDENTITY_MISMATCH')
    identity = envelope['planned_identity']; tid = j.digest(identity); receipt = envelope['request_receipt']
    require(receipt['trial_id'] == tid and type(receipt['attempt']) is int and receipt['attempt'] == 1 and receipt['model'] == identity['judge'], 'REQUEST_RECEIPT_IDENTITY_MISMATCH')
    require(receipt['request_id'] == j.digest({'trial_id': tid, 'attempt': 1}), 'REQUEST_RECEIPT_HASH_MISMATCH')
    require(identity['input_sha256'] == j.digest({'question': case['specific_question'], 'question_id': case['question_id'],
        'protocol': case['model_response'], 'references': case.get('references', [])}), 'FULL_CASE_IDENTITY_MISMATCH')
    require(envelope['http_request_payload'] == envelope['expected_http_payload'], 'HTTP_PAYLOAD_MISMATCH')
    require(identity['payload_sha256'] == j.digest(envelope['http_request_payload']), 'HTTP_IDENTITY_HASH_MISMATCH')
    require(envelope['raw_response_sha256'] == ground.rawsha(raw), 'RAW_TEXT_HASH_MISMATCH')
    require(envelope['source_document_sha256'] == j.digest(doc), 'SOURCE_DOCUMENT_HASH_MISMATCH')
    require(doc == ground.document(case['model_response'], ground.source_id_for_case(case)), 'DOCUMENT_SOURCE_OR_UNIT_BINDING')
    require(envelope['expected_http_payload']['format'] == ground.schema_for_document(doc), 'SOURCE_SPECIFIC_SCHEMA_MISMATCH')
    public = envelope['expected_public_model']
    require(envelope['expected_http_payload'] == backend.payload_for(envelope['expected_http_payload']['prompt'], ground.schema_for_document(doc), public), 'MODEL_SETTINGS_PAYLOAD_MISMATCH')
    require(backend.validate_provider(envelope['provider_response'], public) == raw, 'RAW_PROVIDER_TEXT_MISMATCH')
    payload = integrity.parse_judge_object(raw)
    require(set(payload) <= {'scores', 'score_evidence', 'grounded_extraction'}, 'UNATTRIBUTED_TOP_LEVEL_FIELD')
    g = payload.get('grounded_extraction'); require(isinstance(g, dict), 'GROUNDED_EXTRACTION_OBJECT_REQUIRED')
    require(g.get('schema_version') == ground.VERSION and g.get('source_id') == doc['source_id'], 'SOURCE_OR_VERSION_MISMATCH')
    return payload


def direct_audit(payload, doc, ground):
    result = {}; issues = []; schema = ground.schema_for_document(doc)
    scores = payload.get('scores'); evidence = payload.get('score_evidence'); indexed = {m: [] for m in DIRECT}; global_evidence = []
    if not isinstance(evidence, list): global_evidence.append(error('/score_evidence', 'EVIDENCE_ARRAY_REQUIRED', evidence, DIRECT))
    else:
        for i, row in enumerate(evidence):
            metric = row.get('m') if isinstance(row, dict) else None
            if not isinstance(metric, str) or metric not in indexed:
                global_evidence.append(error('/score_evidence/' + str(i), 'UNATTRIBUTABLE_EVIDENCE_RECORD', row, DIRECT))
            else: indexed[metric].append((i, row))
    issues += global_evidence
    try: integrity.validate_score_proposals(scores)
    except Exception as exc: issues.append(error('/scores', exc, scores, ['whole_output_only; each dependent direct record audited separately']))
    for metric in DIRECT:
        pointer = '/scores/' + GROUP[metric] + '/' + metric; local = []; spans = []; record = None; value = None
        try:
            require(isinstance(scores, dict) and isinstance(scores.get(GROUP[metric]), dict), 'MISSING_CANONICAL_SCORE_GROUP')
            record = scores[GROUP[metric]].get(metric)
            spec = schema['properties']['scores']['properties'][GROUP[metric]]['properties'][metric]
            ground.validate_shape(record, spec, pointer)
            require(isinstance(record, dict) and 'score' in record, 'SCORE_RECORD_REQUIRED')
            value = record['score']; maximum = spec['properties']['score']['maximum']
            require(value is None or integrity.finite_nonnegative(value) and value <= maximum, 'ORIGINAL_SCORE_RANGE')
            require(value is not None or isinstance(record.get('reasoning'), str) and bool(record['reasoning'].strip()), 'NULL_SCORE_REQUIRES_REASON')
            require(not global_evidence, 'UNATTRIBUTABLE_SCORE_EVIDENCE_BLOCKS_DIRECT_SET')
            require(len(indexed[metric]) == 1, 'EXACTLY_ONE_METRIC_EVIDENCE_REQUIRED')
            index, ev = indexed[metric][0]; ground.validate_shape(ev, schema['properties']['score_evidence']['items'])
            spans = [ground.resolve(ground._expand_ref(ref), doc) for ref in ev['u']]
            require(ev['b'] not in ['observed', 'mixed'] or bool(spans), 'OBSERVED_SCORE_EVIDENCE_REQUIRES_SPAN')
            require(ev['b'] != 'absence' or not spans, 'ABSENCE_EVIDENCE_IS_NOT_A_QUOTED_PRESENT_FACT')
            require(bool(ev['r'].strip()), 'EMPTY_SCORE_RUBRIC_BASIS')
        except Exception as exc:
            local.append(error(pointer, exc, {'score': record, 'evidence': indexed[metric]}, [metric])); value = None
        issues += local
        result[metric] = {'value': value, 'status': 'invalid_dependency' if local else 'explicit_unknown' if value is None else 'validated_numeric_proposal_not_scientific_truth',
            'record': copy.deepcopy(record), 'evidence_records': copy.deepcopy(indexed[metric]), 'resolved_spans': spans, 'errors': local,
            'dependencies': DEPENDENCIES[metric], 'scientific_validity': 'not_established'}
    return result, issues


def neutral_view(payload, doc, ground, keep, coverage_fields=(), overrides=None):
    """No neutral field may supply a published fact, direct value or numeric zero."""
    raw = payload['grounded_extraction']
    blank_score = {'score': None, 'reasoning': 'INTERNAL_UNUSED_VALIDATION_SCAFFOLD; not model output or a scientific value.'}
    scores = {'completeness': {k: copy.deepcopy(blank_score) for k in ['c_step', 'c_param']},
        'correctness': {k: copy.deepcopy(blank_score) for k in DIRECT[1:]}}
    g = {k: [] for k in ARRAYS}
    g.update(schema_version=ground.VERSION, source_id=doc['source_id'], precedence_edges=[],
        timeline={'m': 'unknown', 'o': [], 'e': None, 'c': 'unknown'}, coverage={'e': 'unknown', 't': 'unknown', 'c': 'unknown', 'u': []})
    for field in keep:
        require(field in raw, 'MISSING_DEPENDENCY_FIELD:' + field); g[field] = copy.deepcopy(raw[field])
    for field in coverage_fields:
        require(isinstance(raw.get('coverage'), dict) and field in raw['coverage'], 'MISSING_COVERAGE_DEPENDENCY:' + field)
        g['coverage'][field] = copy.deepcopy(raw['coverage'][field])
    if overrides:
        for field, value in overrides.items(): g[field] = copy.deepcopy(value)
    view = {'scores': scores, 'score_evidence': [{'m': m, 'u': [], 'b': 'insufficient', 'r': 'INTERNAL_UNUSED_VALIDATION_SCAFFOLD'} for m in DIRECT],
        'grounded_extraction': g}
    retained = {'/grounded_extraction/' + k: j.digest(raw[k]) for k in keep if not overrides or k not in overrides}
    retained.update({'/grounded_extraction/coverage/' + k: j.digest(raw['coverage'][k]) for k in coverage_fields})
    for path, sha in retained.items():
        value = view
        for key in path.strip('/').split('/'): value = value[key]
        require(j.digest(value) == sha, 'RELEVANT_RAW_DEPENDENCY_CHANGED')
    return view, {'model_raw': False, 'internal_validation_only': True, 'source_text_changed': False,
        'retained_raw_dependency_hashes': retained, 'synthetic_scaffolding': {'scores': scores, 'score_evidence': view['score_evidence'],
            'unrelated_extraction_fields': {k: v for k, v in g.items() if k not in keep and k not in ['source_id', 'schema_version', 'coverage']},
            'unretained_coverage_fields': {k: v for k, v in g['coverage'].items() if k not in coverage_fields}},
        'omitted_unrelated_raw_fields': {k: copy.deepcopy(v) for k, v in raw.items() if k not in keep and k not in ['source_id', 'schema_version']},
        'record_subset_overrides': copy.deepcopy(overrides), 'never_a_complete_or_repaired_model_conversion': True}


def convert_view(payload, doc, ground, name, keep, coverage=(), overrides=None):
    output = {'name': name, 'status': 'invalid_dependency', 'value': None, 'conversion': None, 'view_audit': None, 'error': None}
    try:
        view, audit = neutral_view(payload, doc, ground, keep, coverage, overrides)
        output['view_audit'] = audit; output['validation_view_sha256'] = j.digest(view)
        output['conversion'] = ground.convert(ground.canonical(view), doc); output['status'] = 'validated_dependency_view'
    except Exception as exc: output['error'] = error('/grounded_extraction', exc, None, [name])
    return output


def records_audit(payload, doc, ground):
    g = payload['grounded_extraction']; spec = ground.schema_for_document(doc)['properties']['grounded_extraction']['properties']
    rows = []; issues = []; byid = {}; duplicate_ids = set()
    for group in ARRAYS:
        values = g.get(group)
        if not isinstance(values, list):
            issues.append(error('/grounded_extraction/' + group, 'RECORD_ARRAY_REQUIRED', values, [group])); continue
        for i, raw in enumerate(values):
            pointer = '/grounded_extraction/' + group + '/' + str(i)
            row = {'pointer': pointer, 'group': group, 'raw_record': copy.deepcopy(raw), 'id': raw.get('i') if isinstance(raw, dict) else None,
                'valid_shape_and_local_source': False, 'resolved_fields': {}, 'errors': []}
            if isinstance(row['id'], str):
                if row['id'] in byid: duplicate_ids.add(row['id'])
                byid.setdefault(row['id'], []).append(pointer)
            try:
                ground.validate_shape(raw, spec[group]['items'], pointer)
                for field in {'method_mentions': ['u'], 'entities': ['u'], 'relations': ['e'], 'intrinsic_signals': ['u'],
                    'operations': ['o', 'd', 'r', 'c'], 'total_time_claims': ['d'], 'ri_mentions': ['v']}[group]:
                    if raw[field] is not None: row['resolved_fields'][field] = ground.resolve(ground._expand_ref(raw[field]), doc)
                if group in ['method_mentions', 'entities']:
                    row['name'], row['name_binding'] = ground.bind_literal_name(raw['n'], row['resolved_fields']['u'], doc, raw['a'])
                row['valid_shape_and_local_source'] = True
            except Exception as exc: row['errors'].append(error(pointer, exc, raw, [group]))
            rows.append(row)
    for row in rows:
        if isinstance(row['id'], str) and row['id'] in duplicate_ids:
            row['valid_shape_and_local_source'] = False
            row['errors'].append(error(row['pointer'], 'DUPLICATE_GLOBAL_RECORD_ID', row['raw_record'], [row['group']]))
        issues += row['errors']
    return rows, issues, {i: byid[i] for i in sorted(duplicate_ids)}


def raw_runtime(case):
    runner, registry = original.runtime(); demand = registry.get(case['question_id'], case['specific_question'])
    meta = runner.QUESTION_META_KB[registry.questions[str(case['question_id'])]['question_id']]
    return runner, demand, meta


def eges_call(context, method, markers, hours):
    runner, demand, meta = context
    quantitative = {'method_name': method, 'tissue_ri_value': meta.get('tissue_ri_value'), 'total_time_hours': hours,
                    'sample_tier': meta.get('tissue_tier_code')}
    value = runner.calculate_effectiveness_score(quantitative, demand, runner.MODEL_SPACE_SIGNED, markers, meta.get('marker_query_targets') or [])
    return {'quantitative_data': quantitative, 'marker_dict': copy.deepcopy(markers), 'user_preference_vector': demand,
            'original_EGES_result': value, 'function': 'unchanged calculate_effectiveness_score', 'new_model_requests': 0}


def field_projection(view, field):
    return view['conversion']['legacy_projection']['extraction'][field] if view['conversion'] else None


def zero_witnesses(payload, doc, ground, records, method, context):
    """Only a separately supported original zero can determine a partial minimum.

    Invalid records are never dropped to claim a complete label graph. Each key
    is a limited zero proof; identity aliases, endpoint damage and scope conflicts
    taint it. Nonzero incomplete scores are never promoted.
    """
    raw = payload['grounded_extraction']; runner = context[0]; proofs = []; taint = []
    ents = [r for r in records if r['group'] == 'entities']; bad = [r for r in ents if not r['valid_shape_and_local_source']]
    if any(not isinstance(raw.get(k), list) for k in ['entities', 'relations', 'intrinsic_signals']):
        return [], [{'reason': 'complete_label_container_unavailable'}]
    if any(not isinstance(r.get('raw_record'), dict) or not isinstance(r['raw_record'].get('n'), str) for r in bad):
        return [], [{'reason': 'unlocalizable_bad_entity_identity_taints_all_label_keys'}]
    def fingerprints(name):
        return {x for x in [runner._normalize_name(name), runner._map_fluor_to_tissue_col(name), runner._map_fluor_to_method_key(name)] if x}
    valid = [r for r in ents if r['valid_shape_and_local_source'] and r.get('name_binding', {}).get('atomicity', {}).get('projection_eligible_provisional')]
    candidates = sorted({r['raw_record']['n'] for r in valid if r['raw_record']['s'] == 'used' and r['raw_record']['k'] in ['fluorophore', 'fluorescent_protein']})
    for name in candidates:
        same = [r for r in ents if isinstance(r['raw_record'], dict) and r['raw_record'].get('n') == name]
        ids = {r['id'] for r in same if isinstance(r['id'], str)}
        collision = [r['pointer'] for r in bad if fingerprints(name) & fingerprints(r['raw_record']['n']) or
                     runner._normalize_name(name) in runner._normalize_name(r['raw_record']['n']) or runner._normalize_name(r['raw_record']['n']) in runner._normalize_name(name)]
        unsafe = [r for r in same if not r['valid_shape_and_local_source'] or r['raw_record']['s'] != 'used' or
                  r['raw_record']['k'] not in ['fluorophore', 'fluorescent_protein'] or not r.get('name_binding', {}).get('atomicity', {}).get('projection_eligible_provisional')]
        support = [r for r in same if r.get('name') and ground.affirmative_entity_use(name, r['name']['context']) and not
            re.search(r'\b(?:not|without|either|alternative|if|unless|may|can|like)\b|/|备选|不使用|如果|例如', r['name']['context'], re.I)]
        if collision or unsafe or not support:
            taint.append({'legacy_key': name, 'reason': 'identity_alias_usage_or_source_scope_not_independently_clean', 'related_bad_pointers': collision}); continue
        if any(not isinstance(x, dict) or not isinstance(x.get('f'), str) for x in raw['relations']):
            taint.append({'legacy_key': name, 'reason': 'unattributable_relation_taints_all_keys'}); continue
        relations = [x for x in raw['relations'] if x.get('f') in ids]
        if any(x.get('t') is not None and not isinstance(x.get('t'), str) for x in relations):
            taint.append({'legacy_key': name, 'reason': 'malformed_connected_target_identity'}); continue
        targets = {x.get('t') for x in relations if x.get('t') is not None}
        entity_subset = [x for x in raw['entities'] if isinstance(x, dict) and isinstance(x.get('i'), str) and x.get('i') in ids | targets]
        if any(not isinstance(x, dict) or not isinstance(x.get('e'), str) for x in raw['intrinsic_signals']):
            taint.append({'legacy_key': name, 'reason': 'unattributable_intrinsic_taints_all_keys'}); continue
        intrinsics = [x for x in raw['intrinsic_signals'] if x.get('e') in ids]
        view = convert_view(payload, doc, ground, 'zero_witness:' + name, ['method_mentions'], (),
            {'entities': entity_subset, 'relations': relations, 'intrinsic_signals': intrinsics})
        if not view['conversion']:
            taint.append({'legacy_key': name, 'reason': 'connected_identity_graph_failed', 'error': view['error']}); continue
        cv = view['conversion']; projected = cv['legacy_projection']['extraction']['marker_dict']
        # Exactly one unchanged key, no alias merge or synthetic marker input.
        if set(projected) != {name}:
            taint.append({'legacy_key': name, 'reason': 'zero_island_projection_not_exact_single_key'}); continue
        calc = eges_call(context, method, projected, None); replay = calc['original_EGES_result']
        rejected = [x for x in cv['source_audit']['resolved']['relations'] if not x['projection_allowed']]
        intrinsic_bad = [x for x in cv['legacy_projection']['intrinsic_identity_conversion'] if not x['legacy_same_name_projection_applied']]
        allowed_channels = ['s_method_fluor_compat']
        if not rejected and not intrinsic_bad: allowed_channels += ['s_target_match', 's_marker_fluor_compat']
        channels = [k for k in allowed_channels if replay[k] == 0]
        if channels:
            proofs.append({'legacy_key': name, 'value': 0.0, 'original_zero_channels': channels, 'original_EGES_call': calc,
                'source_entity_pointers': [r['pointer'] for r in same], 'validation_view': view,
                'zero_determines_original_nonnegative_nullable_min': True, 'complete_label_graph_claimed': False,
                'unsupported_relationship_does_not_supply_target_zero': bool(rejected), 'scientific_validity': 'not_established'})
    return proofs, taint


def audit_components(raw, doc, case, backend, step, envelope):
    ground = backend.grounded; result = {'version': VERSION, 'raw_response_sha256': ground.rawsha(raw), 'raw_content_preserved': raw,
        'source_document_sha256': j.digest(doc), 'source_case_sha256': j.digest(case), 'shared_gate': {'pass': False},
        'dependency_manifest': DEPENDENCIES, 'component_rows': {}, 'record_errors': [], 'records': [], 'validation_views': {},
        'upstream_technical_status': envelope.get('upstream_technical_status'), 'upstream_failure': copy.deepcopy(envelope.get('upstream_failure')),
        'whole_technical_success': False, 'partial_results_count_as_full_success': False, 'formal_eligible': False, 'expert_confirmed': False,
        'new_model_requests': 0, 'scientific_validity': 'not_established', 'score_arithmetic_changed': False}
    values = {k: None for k in DIRECT + EGES}
    try: payload = shared_gate(raw, doc, case, backend, envelope)
    except Exception as exc:
        result['record_errors'].append(error('/', exc, None, DIRECT + EGES)); result['metrics'] = original.derive(values, step, True)
        result['component_rows'] = {k: {'value': None, 'status': 'blocked_by_shared_identity_or_JSON_gate', 'dependencies': DEPENDENCIES[k]} for k in values}
        return result
    result['shared_gate'] = {'pass': True, 'provider_complete_original_parser_and_source_identity': True,
        'envelope_sha256': j.digest(envelope), 'input_science_identity_supplied_by_frozen_caller': True}
    direct, errors = direct_audit(payload, doc, ground); result['component_rows'].update(direct); result['record_errors'] += errors
    values.update({k: direct[k]['value'] for k in DIRECT})
    rows, issues, dup = records_audit(payload, doc, ground); result['records'] = rows; result['record_errors'] += issues
    result['duplicate_id_groups'] = dup
    spec_keys = set(ground.schema_for_document(doc)['properties']['grounded_extraction']['properties'])
    extra = set(payload['grounded_extraction']) - spec_keys
    if extra: result['record_errors'].append(error('/grounded_extraction', 'UNATTRIBUTABLE_EXTRACTION_FIELDS:' + ','.join(sorted(extra)), None, EGES))
    views = {
        'method': convert_view(payload, doc, ground, 'method', ['method_mentions']),
        'time': convert_view(payload, doc, ground, 'time', ['operations', 'timeline', 'precedence_edges', 'total_time_claims'], ['t', 'c', 'u']),
        'label': convert_view(payload, doc, ground, 'label', ['method_mentions', 'entities', 'relations', 'intrinsic_signals'], ['e', 'u']),
        'ri_record_audit_only': convert_view(payload, doc, ground, 'ri_record_audit_only', ['ri_mentions']),
    }
    # Global ID namespace conflicts taint each implicated component; no dict overwrite.
    component_groups = {'method': {'method_mentions'}, 'time': {'operations', 'total_time_claims'},
        'label': {'method_mentions', 'entities', 'relations', 'intrinsic_signals'}, 'ri_record_audit_only': {'ri_mentions'}}
    for name, view in views.items():
        duplicates = [r['pointer'] for r in rows if isinstance(r['id'], str) and r['id'] in dup and r['group'] in component_groups[name]]
        if duplicates or extra:
            view['conversion'] = None; view['status'] = 'invalid_dependency'
            view['error'] = error('/grounded_extraction', 'DUPLICATE_ID_OR_UNATTRIBUTABLE_EXTRACTION_FIELD', duplicates, [name])
        if view['error']: result['record_errors'].append(view['error'])
    result['validation_views'] = views
    method = field_projection(views['method'], 'method_name'); total = field_projection(views['time'], 'clearing_total_time_hours')
    # Keep per-operation evidence even when the full time dependency graph fails.
    known_ops = []
    for row in rows:
        if row['group'] != 'operations' or not row['valid_shape_and_local_source']: continue
        op = row['raw_record']
        v = convert_view(payload, doc, ground, 'operation_record_only:' + str(op['i']), [], (), {'operations': [op],
            'timeline': {'m': 'serial', 'o': [op['i']], 'e': None, 'c': 'unknown'}})
        if v['conversion']:
            known_ops.append({'pointer': row['pointer'], 'resolved_operation': v['conversion']['source_audit']['resolved']['operations'][0],
                'total_time_claimed': False, 'validation_view_audit': v['view_audit']})
        else: row['errors'].append(v['error']); result['record_errors'].append(v['error'])
    result['known_operation_records_not_an_aggregate_total'] = known_ops
    context = raw_runtime(case)
    base_calc = eges_call(context, method, {}, total if views['time']['conversion'] else None); result['method_time_original_EGES_call'] = base_calc
    replay = base_calc['original_EGES_result']
    values['s_method'] = replay['s_method'] if method is not None else None
    values['s_trans'] = replay['s_trans'] if method is not None else None
    values['s_time'] = replay['s_time'] if method is not None and views['time']['conversion'] else None
    result['method_dependency'] = {'projected_method': method, 'raw_method_identity': replay['method_identity'],
        'unknown_method_not_replaced': True, 'raw_RI_not_used_by_original_s_trans': True,
        's_time_needs_method_KB_even_when_operation_total_is_known': True}
    # A failed method dependency differs from a valid, explicitly unavailable
    # method. The latter remains None in the original function; no placeholder
    # is invented. Its independent supported target/marker zero can still define
    # the original nullable minimum despite unknown method compatibility.
    if views['method']['conversion'] and views['label']['conversion']:
        cv = views['label']['conversion']; mapping = cv['legacy_projection']['extraction']['marker_dict']
        label_calc = eges_call(context, method, mapping, None); result['label_original_EGES_call'] = label_calc
        gated, notes = backend_science(backend).gate_components({**values, **{k: label_calc['original_EGES_result'][k] for k in EGES}}, cv, label_calc['original_EGES_result'])
        values['s_label'] = gated['s_label']; result['label_original_component_gate_notes'] = notes
    else:
        proofs, taint = zero_witnesses(payload, doc, ground, rows, method, context) if not extra and views['method']['conversion'] else ([], [{'reason': 'invalid_method_dependency_or_unattributable_extraction_field'}])
        result['label_zero_witnesses'] = proofs; result['label_taint_audit'] = taint
        values['s_label'] = 0.0 if proofs else None
    for key in EGES:
        result['component_rows'][key] = {'value': values[key], 'status': 'available_provisional_not_scientific_truth' if values[key] is not None else 'NA_invalid_or_unknown_dependency',
            'dependencies': DEPENDENCIES[key], 'known_zero_requires_original_supported_witness': key == 's_label'}
    # Exact original successful path wins; this asserts preservation rather than
    # pretending the synthetic views are the model's complete original conversion.
    try:
        complete = ground.convert(raw, doc)
        original_result = original.score_conversion(case, complete, backend_science(backend), step)
        result['original_full_conversion_replayed'] = True; result['original_full_numeric_result'] = original_result
        original_values = original_result['component_gated_proposals']
        require(all(original.same(values[k], original_values[k]) for k in DIRECT + EGES), 'VALID_INPUT_COMPONENT_IDENTITY_REGRESSION')
        result['original_full_formula_same'] = all(original.same(original.derive(values, step, True)[k], original_result['metrics'][k]) for k in original.METRICS)
        require(result['original_full_formula_same'], 'VALID_INPUT_FORMULA_IDENTITY_REGRESSION')
        result['whole_technical_success'] = envelope['upstream_technical_status'] == 'success'
    except ValueError as exc:
        if 'IDENTITY_REGRESSION' in str(exc): raise
        result['original_full_conversion_replayed'] = False; result['original_full_error_retained'] = str(exc)
    result['partial_component_execution'] = not result['whole_technical_success'] and any(v is not None for v in values.values())
    result['metrics'] = original.derive(values, step, True)
    result['complete_numeric_CCE'] = all(original.finite(result['metrics'][k]) for k in ['Com', 'Cor', 'Eff', 'IA', 'HV'])
    result['raw_payload_unchanged'] = integrity.parse_judge_object(raw) == payload
    result['original_input_source_unchanged'] = doc == ground.document(case['model_response'], ground.source_id_for_case(case))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['describe'])
    p.parse_args()
    print(j.canonical({'version': VERSION, 'scope': 'all_five_direct_and_all_four_EGES_dependencies', 'dependencies': DEPENDENCIES,
        'validation_views_are_not_raw': True, 'no_archive_or_model_entrypoint': True, 'new_model_requests': 0, 'frozen': False}))


if __name__ == '__main__': main()
