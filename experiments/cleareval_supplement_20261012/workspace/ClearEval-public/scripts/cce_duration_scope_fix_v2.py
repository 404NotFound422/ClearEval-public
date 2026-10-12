"""Derived duration lexical/scope audit; never re-enumerates frozen source IDs.

Ordinary `on` is not overnight. Compact uppercase ND in an explicit spatial
construction is not days. Original numeric formula and raw records are kept.
This is posthoc software, not a replacement for a frozen confirmation policy.
"""
from __future__ import annotations
import copy
import re
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_fieldwise_scoring_v1 as original
g = original.ground
VERSION = 'duration-lexical-and-noncore-scope-v2'
TIME_SLOT = re.compile(r'\b(?:time|duration)\s*[:=]\s*$', re.I)
TEMPORAL_PREDICATE = re.compile(r'\b(?:incubat\w*|wait\w*|soak\w*|hold|held|treat\w*|process\w*|complet\w*|finish\w*|last\w*)\b[^.;:\n]{0,70}\b(?:for|after|within|in)\s*$', re.I)
EXPLICIT_ON = re.compile(r'\b(?:incubat\w*|soak\w*|wait\w*)\b[^.;:\n]{0,60}\s$', re.I)
OVERNIGHT = re.compile(r'(?:overnight(?:\s*\(ON\))?|o\s*\.\s*n\s*\.?|o\s*/\s*n|\u8fc7\u591c)', re.I)
SPATIAL_PREPOSITION = re.compile(r'\b(?:in|into|as)\s*$', re.I)
DIMENSION_SLOT = re.compile(r'\b(?:dimensionality|dimensions?|spatial\s+representation)\s*[:=]\s*$', re.I)
CORE_ACTION = re.compile(r'\b(?:delipid\w*|decalcif\w*|decolor\w*|dehydrat\w*|clear(?:ing)?|equilibrat\w*|refractive\s+index\s+match\w*|RI\s+match\w*)\b|\u53bb\u8102|\u8131\u6c34|\u8131\u8272|\u8131\u9499|\u5e73\u8861|\u5339\u914d', re.I)
STORAGE_ACTION = re.compile(r'\b(?:store|stored|storing|storage)\b|\u50a8\u5b58|\u4fdd\u5b58', re.I)
MIXED_ACTION = re.compile(r';|\b(?:then|subsequently)\b|\band\s+(?:incubate|wash|transfer|treat|clear|equilibrate)\b', re.I)


def lexical_role(quote, left='', right=''):
    """Source syntax, not image-noun enumeration or answer identity."""
    q = quote.strip()
    if OVERNIGHT.fullmatch(q):
        return 'duration', 'explicit_overnight_expression'
    if q.casefold() == 'on':
        if q == 'ON' and (TIME_SLOT.search(left) or (EXPLICIT_ON.search(left) and re.match(r'^\s*(?:[.;,)]|$|at\b)', right, re.I))):
            return 'duration', 'uppercase_ON_in_explicit_duration_syntax'
        if q == 'on' and not TIME_SLOT.search(left) and re.match(r'^\s+\S', right):
            return 'non_duration_word_lead', 'lowercase_preposition_not_overnight'
        if re.search(r'\b(?:switch|turn|power)\s*$', left, re.I):
            return 'non_duration_word_lead', 'switch_state_not_overnight'
        return 'unresolved_duration_abbreviation', 'ON_requires_explicit_duration_context'
    if re.fullmatch(r'\d+D', q):
        # Preserve explicit temporal constructions and all spaced/lowercase d.
        if TIME_SLOT.search(left) or TEMPORAL_PREDICATE.search(left):
            return 'duration', 'explicit_temporal_syntax_has_priority'
        old_kind, old_reason = g.duration_role(q, left, right)
        if old_kind == 'dimensional_expression_lead':
            return old_kind, 'existing_original_spatial_classification'
        if SPATIAL_PREPOSITION.search(left) or DIMENSION_SLOT.search(left):
            return 'dimensional_expression_lead', 'compact_uppercase_ND_in_spatial_syntax'
    return 'duration', 'no_source_supported_non_duration_reclassification'


def strict_duration_value(quote, left='', right='', overnight_hours=8):
    kind, reason = lexical_role(quote, left, right)
    if kind != 'duration':
        return {'state': kind, 'bounds_hours': None, 'unique_hours': None, 'source_numeric': False, 'reason': reason}
    if OVERNIGHT.fullmatch(quote.strip()) or quote.strip() == 'ON':
        return {'state': 'legacy_overnight_convention', 'bounds_hours': [overnight_hours, overnight_hours],
            'unique_hours': overnight_hours, 'source_numeric': False, 'reason': 'original_rubric_eight_hour_convention'}
    return g.duration_value(quote)


def span_key(span):
    return (span['start'], span['end'])


def checked_span(span, doc, units):
    u = units[span['unit_id']]
    if span.get('answer_sha256') != doc['answer_sha256'] or not (u['start'] <= span['start'] < span['end'] <= u['end']) or doc['text'][span['start']:span['end']] != span['quote']:
        raise ValueError('SOURCE_DURATION_SPAN_CHANGED')
    return u, doc['text'][u['start']:span['start']], doc['text'][span['end']:u['end']]


def source_supported_storage(row, operations, doc, units):
    s = row['span']; u = units[s['unit_id']]
    start = u['start'] + len(u['text']) - len(u['text'].lstrip())
    end = u['end'] - (len(u['text']) - len(u['text'].rstrip()))
    matched = [o for o in operations if o['phase'] == 'storage' and o['operation']['unit_id'] == u['unit_id']
        and o['operation']['start'] == start and o['operation']['end'] == end
        and o['operation']['quote'] == doc['text'][start:end]]
    if len(matched) != 1 or not STORAGE_ACTION.search(u['text']) or CORE_ACTION.search(u['text']) or MIXED_ACTION.search(u['text']):
        return None
    return {'operation_id': matched[0]['id'], 'source_unit': copy.deepcopy(u), 'basis': 'whole_source_record_explicit_storage_without_core_or_mixed_action'}


def derive_audit(original_audit, doc):
    sb = original_audit['source_binding']
    if sb['source_id'] != doc['source_id'] or sb['answer_sha256'] != doc['answer_sha256'] or g.rawsha(doc['text']) != doc['answer_sha256']:
        raise ValueError('SOURCE_IDENTITY_MISMATCH')
    audit = copy.deepcopy(original_audit); units = {u['unit_id']: u for u in doc['units']}
    ops = audit['resolved']['operations']; changes = []; rejected = {}; usage = []
    for r in audit['inventory']:
        if r['kind'] != 'duration':
            continue
        u, left, right = checked_span(r['span'], doc, units)
        kind, reason = lexical_role(r['span']['quote'], left, right)
        storage = source_supported_storage(r, ops, doc, units) if kind == 'duration' and r.get('coverage_state') != 'covered_time_evidence' else None
        if storage:
            kind, reason = 'excluded_noncore_duration', 'source_bound_storage_duration_outside_initial_core'
        if kind == 'duration':
            continue
        old = copy.deepcopy(r)
        r['kind'] = 'duration' if kind == 'unresolved_duration_abbreviation' else kind
        r['coverage_state'] = 'unresolved_duration_abbreviation' if kind == 'unresolved_duration_abbreviation' else 'classified_noncore_or_nonduration_source_expression'
        r['original_candidate_kind'] = old['kind']; r['original_coverage_state'] = old.get('coverage_state')
        r['derived_duration_role_reason'] = reason
        changes.append({'candidate_id': r['candidate_id'], 'original_record': old, 'derived_kind': kind,
            'reason': reason, 'storage_source_support': storage, 'candidate_id_and_original_registry_hash_preserved': True})
        if kind != 'excluded_noncore_duration':
            rejected[span_key(r['span'])] = {'kind': kind, 'reason': reason, 'span': r['span']}
    # Audit every returned reference, even if inventory membership/state differs.
    for o in ops:
        d = o.get('duration')
        if not d:
            continue
        u, left, right = checked_span(d, doc, units)
        kind, reason = lexical_role(d['quote'], left, right)
        item = {'record_type': 'operation', 'record_id': o['id'], 'duration_span': copy.deepcopy(d), 'lexical_kind': kind, 'reason': reason}
        if kind != 'duration':
            item['original_parsed_duration'] = copy.deepcopy(o['parsed_duration'])
            o['parsed_duration'] = {'state': 'source_reference_not_a_verified_duration', 'bounds_hours': None,
                'unique_hours': None, 'source_numeric': False, 'lexical_reason': reason}
            item['derived_parsed_duration'] = copy.deepcopy(o['parsed_duration'])
            item['local_time_unknown_no_replacement_reference'] = True
        usage.append(item)
    invalid_claims = []
    for claim in audit['resolved']['total_time_claims']:
        d = claim['duration']; u, left, right = checked_span(d, doc, units)
        kind, reason = lexical_role(d['quote'], left, right)
        usage.append({'record_type': 'total_claim', 'record_id': claim['id'], 'duration_span': copy.deepcopy(d), 'lexical_kind': kind, 'reason': reason})
        if kind != 'duration':
            invalid_claims.append({'id': claim['id'], 'span': copy.deepcopy(d), 'kind': kind, 'reason': reason})
    if [r['candidate_id'] for r in audit['inventory']] != [r['candidate_id'] for r in original_audit['inventory']]:
        raise ValueError('CANDIDATE_ID_CHANGED')
    audit['derived_duration_scope_v2'] = {'version': VERSION, 'changes': changes, 'returned_reference_audit': usage,
        'invalid_total_claims': invalid_claims, 'raw_and_registry_unchanged': True,
        'other_coverage_phase_scope_repeat_and_numeric_formula_unchanged': True}
    return audit, audit['derived_duration_scope_v2']


def project_first_pass(audit):
    projection = original.project_first_pass(audit)
    invalid = audit.get('derived_duration_scope_v2', {}).get('invalid_total_claims', [])
    if invalid:
        time = projection['time_calculation']; ids = {x['id'] for x in invalid}
        for c in time['claims']:
            if c['id'] in ids:
                c.update(state='source_reference_not_a_verified_duration', bounds_hours=None, unique_hours=None, source_numeric=False)
        time['issues'] = sorted(set(time['issues'] + ['total_claim_references_non_duration_source:' + x['id'] for x in invalid]))
        time['total_hours'] = None
        projection['extraction']['clearing_total_time_hours'] = None
        projection['component_input_state']['s_time'] = 'partial'
    return projection
