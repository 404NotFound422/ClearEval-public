"""Posthoc complete-name boundary in explicitly declared label combinations.

Accepting a source-supported atomic name does not establish a target relation.
No raw ID/name/ordinal is rewritten. Charged/positive suffix identities retain
the old guards, and all original relation and endpoint-selection gates remain.
"""
import copy
import re
import types
from cce_record_namespace_scope_v1 import *
import cce_record_namespace_scope_v1 as namespace

ADAPTER_VERSION = 'source-declared-marker-combination-boundary-posthoc-v1'
DECLARED_LABEL_HEADER = re.compile(
    r'^\s*(?:\*\*|#{1,6}\s*)?\s*(?:Chosen\s+Labeling|Selected\s+Labeling|'
    r'所选[^:：\n]{0,50}(?:标记|荧光)[^:：\n]{0,50})\s*[:：]', re.I)
NEGATED_OR_ALTERNATIVE = re.compile(r'\b(?:not|without|either|alternative|instead|or)\b|不使用|不采用|备选|或者', re.I)


def declared_atomic_name_evidence(literal, doc):
    """A whole explicit Marker/Target field is source evidence, never a KB alias."""
    pattern = re.compile(r'(?<![\w])(?:Marker|Target|标记物|靶标)\s*[:：]\s*'
                         + re.escape(literal) + r'(?=\s*(?:[;；,，)）\]\n]|$))', re.I)
    evidence = []
    for unit in doc['units']:
        for match in pattern.finditer(unit['text']):
            # Match the field label case-insensitively, but require the name
            # value itself to have the same complete literal spelling.
            field = match.group(0)
            value = re.split(r'[:：]', field, maxsplit=1)[1].strip()
            if value != literal or NEGATED_OR_ALTERNATIVE.search(unit['text']):
                continue
            start = unit['start'] + match.start()
            end = unit['start'] + match.end()
            evidence.append({'unit_id':unit['unit_id'], 'start':start, 'end':end,
                             'quote':doc['text'][start:end], 'literal_name':literal,
                             'source_id':doc['source_id'], 'answer_sha256':doc['answer_sha256']})
    return evidence


def plus_boundary_audit(literal, start, end, doc):
    result = namespace.plus_boundary_audit(literal, start, end, doc)
    if not result['terminal_suffix_omitted']:
        return result
    unit = next(u for u in doc['units'] if u['start'] <= start and end <= u['end'])
    if not DECLARED_LABEL_HEADER.match(unit['text']) or NEGATED_OR_ALTERNATIVE.search(unit['text']):
        return result
    # The immediate + must have a following complete name-like right term.
    # A terminal +, '+ cells', 'NAD+ + X', and chemical ions cannot qualify.
    suffix = doc['text'][end+1:unit['end']]
    right = re.split(r'[\],;，；+\n]', suffix, maxsplit=1)[0].strip()
    parsed = namespace.paired_clause_syntax(literal + '+' + right)
    if parsed is None or parsed['left_complete_name'] != literal:
        return result
    anchors = declared_atomic_name_evidence(literal, doc)
    if not anchors:
        return result
    return {'is_separator':True, 'terminal_suffix_omitted':False,
        'reason':'explicit_label_combination_and_independent_complete_marker_field',
        'source_unit_id':unit['unit_id'], 'separator_offset':end,
        'selected_name_start':start, 'selected_name_end':end, 'selected_name_quote':doc['text'][start:end],
        'independent_atomic_name_evidence':anchors,
        'right_literal_not_created_as_entity':right, 'relation_not_inferred':True,
        'positive_cell_identity_not_asserted':True,
        'raw_name_and_ordinal_unchanged':True}


# Function-local dependency injection, no mutation of any imported module's
# globals. Their original code objects and every unrelated guard are reused.
name_occurrence_inventory = types.FunctionType(namespace.name_occurrence_inventory.__code__,
    {**namespace.name_occurrence_inventory.__globals__, 'plus_boundary_audit':plus_boundary_audit},
    name='name_occurrence_inventory')
bind_literal_name = types.FunctionType(namespace.bind_literal_name.__code__,
    {**namespace.bind_literal_name.__globals__, 'name_occurrence_inventory':name_occurrence_inventory},
    name='bind_literal_name')
_audit_expanded_payload = types.FunctionType(namespace._audit_expanded_payload.__code__,
    {**vars(namespace), 'bind_literal_name':bind_literal_name}, name='_audit_expanded_payload')
audit_payload = types.FunctionType(namespace.audit_payload.__code__,
    {**vars(namespace), '_audit_expanded_payload':_audit_expanded_payload}, name='audit_payload')
_convert = types.FunctionType(namespace._convert_namespace.__code__,
    {**vars(namespace), 'audit_payload':audit_payload}, name='_convert')


def convert(raw, doc):
    conversion = _convert(raw, doc)
    conversion['record_namespace_audit'] = namespace.namespace_audit(conversion['wire_payload'])
    bindings = []
    for group in ['method_mentions', 'entities']:
        for record in conversion['source_audit']['resolved'][group]:
            span = record['name']
            support = plus_boundary_audit(span['quote'], span['start'], span['end'], doc)
            if support.get('independent_atomic_name_evidence'):
                bindings.append({'record_type':group, 'raw_id':record['id'],
                    'raw_name_occurrence':record['name_occurrence'], 'support':support})
    conversion['marker_combination_boundary_audit'] = {
        'version':ADAPTER_VERSION, 'accepted_name_boundaries':bindings,
        'raw_response_changed':False, 'target_relation_inferred':False,
        'original_pair_policy_and_endpoint_gates_unchanged':True}
    return conversion
