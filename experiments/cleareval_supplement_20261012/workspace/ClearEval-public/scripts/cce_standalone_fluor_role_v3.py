"""Source-local role projection; no target, molecular class or KB inference.

Keeps v2 intact. A direct-use predicate is evaluated in its own coordinated
clause, with separately recorded negative antibody-requirement context. A null
relation for an already validated native instance may share that native role
only when the source contains no associated antibody/detector use.
"""
from __future__ import annotations
import copy
import re
import cce_standalone_fluor_role_v2 as base

VERSION = 'source-standalone-fluor-role-v3-local-predicates'
KEY = 'standalone_fluor_role_v3'


def _local_clauses(unit):
    for clause in base._clauses(unit):
        text = clause['quote']
        inherited_nonaffirmative = bool(re.match(r'^\s*(?:for example|for illustration|such as|e\.g\.|alternatively|optionally|if\b|unless\b)', text, re.I))
        cuts = [0]
        # Only explicit coordination boundaries, not arbitrary word windows.
        for m in re.finditer(r'\s+(?:while|whereas|but)\s+|[,;]\s*and\s+(?=[A-Za-z][\w /+-]{0,50}\s+(?:serves?|stains?|provides?|is|are|utilizes?|labels?)\b)|\s+and\s+(?=[A-Za-z][\w /+-]{0,40}\s+(?:serves?|stains?|provides?|is|are|labels?)\b)', text, re.I):
            cuts.extend([m.start(), m.end()])
        cuts.append(len(text))
        for a, b in zip(cuts, cuts[1:]):
            value = text[a:b]
            if value.strip() and not re.fullmatch(r'\s*[,;]?\s*(?:and|while|whereas|but)?\s*', value, re.I):
                yield {'unit_id': clause['unit_id'], 'start': clause['start'] + a,
                       'end': clause['start'] + b, 'quote': value,
                       'inherited_nonaffirmative_scope': inherited_nonaffirmative}


def _predicate_scope(clause):
    """Do not treat absence of an antibody requirement as absence of dye use."""
    text = clause['quote']
    tail = re.search(r'\s+without\s+(?:requiring|using|the\s+need\s+for)\s+(?:complex\s+)?(?:immunolabell?ing|antibod(?:y|ies))\b[^.;\n]*[.;]?\s*$', text, re.I)
    if not tail:
        return clause, None
    bounded = dict(clause, end=clause['start'] + tail.start(), quote=text[:tail.start()])
    excluded = dict(clause, start=clause['start'] + tail.start(), quote=text[tail.start():])
    return bounded, excluded


def _role(clause, name):
    if base._role_clause(clause, name):
        return True
    n = re.escape(name)
    return bool(re.search(r'(?<![\w+\-])' + n + r'(?![\w+\-])\s+serves?\s+as\s+(?:an?\s+)?(?:nuclear\s+|fluorescent\s+)?(?:counterstain|direct\s+stain|direct\s+dye)\b', clause['quote'], re.I))


def _qualified_antibody_mentions(doc, name):
    pattern = re.compile(r'\banti[- ]' + re.escape(name) + r'(?![\w+\-])|(?<![\w+\-])' + re.escape(name) + r'(?:[- ]conjugated|\s+antibod(?:y|ies))\b', re.I)
    return [{'kind': 'qualified_antibody_name', 'unit': copy.deepcopy(u)}
            for u in doc['units'] if pattern.search(u['text'])]


def _linked_conflicts(units, index, name):
    findings = base._linked_context_conflicts(units, index, name)
    return [x for x in findings if not (x['kind'] == 'governing_adjacent_scope' and
            re.search(r'\b(?:uses?|serves?|provides?|labels?|stains?|is|are|was|were|utilizes?)\b', x['unit']['text'], re.I))]


def _instance(pair, projection, doc):
    reasons = []
    if pair.get('kind') != 'unresolved_relation' or pair.get('raw_relation_status') != 'unknown':
        reasons.append('not_unknown_relation')
    if pair.get('marker_literal') is not None or pair.get('reported_target_literal') is not None:
        reasons.append('reported_target_claim_retained')
    name, eid = pair.get('fluor_literal'), pair.get('entity_id')
    rows = [x for x in projection.get('occurrences', []) if x.get('entity_id') == eid]
    if not isinstance(name, str) or not name.strip() or len(rows) != 1:
        return None, reasons + ['literal_or_occurrence_not_unique']
    occurrence = rows[0]
    if occurrence.get('source_affirmative_use') is not True or occurrence.get('included_as_used_instance') is not True or occurrence.get('local_nonuse_audit', {}).get('excluded') is True:
        reasons.append('not_source_supported_used_instance')
    if not base._span_ok(occurrence.get('span'), doc, name):
        reasons.append('invalid_entity_source_span')
    if any(x.get('entity_id') == eid and (x.get('marker_literal') is not None or x.get('reported_target_literal') is not None) for x in projection['pairs']):
        reasons.append('same_occurrence_target_claim_retained')
    return occurrence, reasons


def assess_pair(pair, projection, doc):
    occurrence, reasons = _instance(pair, projection, doc)
    audit = {'pair_id': pair.get('pair_id'), 'eligible': False, 'reasons': reasons,
             'operation_evidence': [], 'direct_role_evidence': [], 'conflicts': [],
             'predicate_exclusion_context': [], 'target_added': False,
             'molecular_class_or_specificity_validated': False}
    if reasons:
        return audit
    name, eid = pair['fluor_literal'], pair['entity_id']
    literal = base._literal(name)
    native = [p for p in projection['pairs'] if p.get('entity_id') == eid and
              p.get('fluor_literal') == name and p.get('kind') == 'source_native_fluor_key_only' and
              p.get('native_is_not_target_assertion') is True and p.get('original_loop_empty_marker') is True and
              base._span_ok(p.get('evidence'), doc)]
    # Role is inherited from an already verified *same occurrence*, never from
    # a familiar reporter name or a model kind field alone.
    if native:
        audit['validated_native_pair_ids'] = [p['pair_id'] for p in native]
        audit['conflicts'] += _qualified_antibody_mentions(doc, name)
        for index, unit in enumerate(doc['units']):
            for original in _local_clauses(unit):
                clause, exclusion = _predicate_scope(original)
                if literal.search(clause['quote']) and base._ANTIBODY.search(clause['quote']):
                    audit['conflicts'].append({'kind': 'same_native_instance_detector_context', 'span': clause})
            if literal.search(unit['text']):
                audit['conflicts'] += [x for x in _linked_conflicts(doc['units'], index, name)
                                       if base._ANTIBODY.search(x.get('unit', {}).get('text', ''))]
        if audit['conflicts']:
            audit['reasons'].append('native_and_detector_roles_not_resolved')
        else:
            audit['eligible'] = True
            audit['source_role'] = 'existing_source_native_instance_null_relation'
        return audit
    if occurrence.get('raw_kind') != 'fluorophore' or base._ANTIBODY.search(name) or base._NATIVE.search(name):
        audit['reasons'].append('not_standalone_fluor_kind'); return audit
    audit['conflicts'] += _qualified_antibody_mentions(doc, name)
    for index, unit in enumerate(doc['units']):
        if not literal.search(unit['text']):
            continue
        for original in _local_clauses(unit):
            if not literal.search(original['quote']):
                continue
            clause, exclusion = _predicate_scope(original)
            if exclusion:
                audit['predicate_exclusion_context'].append(exclusion)
            if base._ANTIBODY.search(clause['quote']) or base._NATIVE.search(clause['quote']):
                audit['conflicts'].append({'kind': 'same_literal_nonstandalone_predicate', 'span': clause})
            elif not clause.get('inherited_nonaffirmative_scope') and not base._NONUSE.search(clause['quote']) and _role(clause, name):
                audit['direct_role_evidence'].append(clause)
            elif base._NONUSE.search(clause['quote']):
                audit.setdefault('nonaffirmative_mentions', []).append(clause)
        if base._direct_operation(unit, name):
            audit['operation_evidence'].append(copy.deepcopy(unit))
            audit['conflicts'] += _linked_conflicts(doc['units'], index, name)
            # A use-purpose in the actual independent operation is itself a
            # source declaration, even when formulation intervenes after name.
            if re.search(r'\bfor\s+(?:(?:nuclear|cellular|structural|fluorescent|direct)\s+){0,3}(?:labell?ing|staining|counterstaining)\b', unit['text'], re.I):
                audit['direct_role_evidence'].append({'unit_id': unit['unit_id'], 'start': unit['start'], 'end': unit['end'], 'quote': unit['text'], 'predicate': 'independent_operation_purpose'})
    if not audit['operation_evidence']:
        audit['reasons'].append('no_affirmative_independent_operation')
    if not audit['direct_role_evidence']:
        audit['reasons'].append('direct_stain_role_not_source_declared')
    if audit['conflicts']:
        audit['reasons'].append('antibody_native_or_scope_conflict')
    audit['eligible'] = not audit['reasons']
    audit['source_role'] = 'source_declared_standalone_direct_staining_reagent' if audit['eligible'] else 'unresolved'
    return audit


def apply_conversion(conversion, doc, case=None):
    if conversion.get(KEY, {}).get('version') == VERSION:
        return copy.deepcopy(conversion)
    result = copy.deepcopy(conversion)
    p = result['label_occurrence_projection']
    if not (base._sha(doc['text']) == doc['answer_sha256'] == p['source_binding']['answer_sha256'] and doc['source_id'] == p['source_binding']['source_id']):
        raise ValueError('SOURCE_BINDING_MISMATCH')
    if any(doc['text'][u['start']:u['end']] != u['text'] for u in doc['units']):
        raise ValueError('SOURCE_UNIT_MISMATCH')
    audits, changes = [], []
    for pair in p['pairs']:
        audit = assess_pair(pair, p, doc)
        audits.append(audit)
        if not audit['eligible']:
            continue
        changes.append({'pair_id': pair['pair_id'], 'original_pair': copy.deepcopy(pair), 'source_role_audit': copy.deepcopy(audit)})
        if audit['source_role'] == 'existing_source_native_instance_null_relation':
            pair.update(kind='source_native_fluor_key_only', native_is_not_target_assertion=True, original_loop_empty_marker=True,
                        native_null_relation_role_audit=audit)
        else:
            pair.update(kind='source_key_only', standalone_source_role_audit=audit)
    original = copy.deepcopy(p['explicit_label_uncertainties'])
    relation_ids = {x['pair_id'].split(':', 1)[1] for x in changes if x['pair_id'].startswith('relation:')}
    p['explicit_label_uncertainties'] = [x for x in original if not (x.get('kind') == 'reported_unresolved_relation' and x.get('relation_id') in relation_ids)]
    base._rebuild_view(p)
    result[KEY] = {'version': VERSION, 'assessments': audits, 'changes': changes,
                   'original_explicit_uncertainties': original, 'raw_modified': False,
                   'scores_recomputed': False, 'target_or_KB_values_added': False,
                   'scientific_validity_proven': False, 'new_calls': 0}
    for key in ('wire_payload', 'source_audit', 'legacy_projection', 'legacy_runner_payload', 'legacy_runner_content'):
        if key in conversion and result[key] != conversion[key]:
            raise AssertionError('ORIGINAL_RECORD_CHANGED:' + key)
    return result
