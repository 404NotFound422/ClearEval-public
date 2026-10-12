"""Finite source-role scope repair, without target or molecular-class inference.

Operation purposes belong to their own sentence/coordinated clause. Quoted or
rejected propositions cannot establish affirmative use. The v2/v3 source and
occurrence gates are retained; old role-modified projections require a fresh
conversion from the original raw record rather than an implicit graph rewind.
"""
from __future__ import annotations
import copy
import re
import cce_standalone_fluor_role_v3 as previous

base = previous.base
VERSION = 'source-standalone-fluor-role-v4-bound-predicate-scope'
KEY = 'standalone_fluor_role_v4'

_QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)|‘[^’\n]*’|`[^`\n]*`')
_REJECTED = re.compile(r'\b(?:false|incorrect|untrue|wrong)\s+that\b', re.I)
_CONDITIONAL_START = re.compile(r'^\s*(?:for example|for illustration|such as|e\.g\.|alternatively|optionally|if\b|unless\b)', re.I)
_COORDINATION = re.compile(
    r'\s+(?:while|whereas|but)\s+|[,;]\s*(?:and\s+)?(?=[A-Za-z][\w /+-]{0,50}\s+(?:serves?|stains?|provides?|is|are|utilizes?|labels?)\b)'
    r'|\s+and\s+(?=[A-Za-z][\w /+-]{0,40}\s+(?:serves?|stains?|provides?|is|are|labels?)\b)', re.I)
_PURPOSE = re.compile(r'\bfor\s+(?:(?:nuclear|cellular|structural|fluorescent|direct)\s+){0,3}(?:labell?ing|staining|counterstaining)\b', re.I)
_SCOPE_HEADING = re.compile(
    r'^\s*(?:the\s+)?(?:primary|secondary|antibody|conjugate|detector|native)\b[^:.;\n]*'
    r'\b(?:is|are|was|were)\s+(?:performed|conducted|carried\s+out)\s+(?:as\s+follows|below)\s*:\s*$', re.I)


def _protected_ranges(text):
    """Do not cut a parenthetical formulation or a quoted proposition in half."""
    ranges = [(m.start(), m.end()) for m in _QUOTED.finditer(text)]
    depth, start = 0, None
    for index, char in enumerate(text):
        if any(a <= index < b for a, b in ranges):
            continue
        if char == '(':
            if depth == 0:
                start = index
            depth += 1
        elif char == ')' and depth:
            depth -= 1
            if depth == 0:
                ranges.append((start, index + 1))
    if depth:
        ranges.append((start, len(text)))
    return ranges


def _sentence_clauses(unit):
    if base._HEADER.match(unit['text']):
        yield from base._clauses(unit)
        return
    text = unit['text']
    protected = _protected_ranges(text)
    cuts = [0]
    for match in re.finditer(r';|[.!?](?=\s|$)', text):
        if any(a <= match.start() < b for a, b in protected):
            continue
        if re.search(r'(?:e\.g|i\.e)$', text[:match.start()], re.I):
            continue
        cuts.append(match.end())
    cuts.append(len(text))
    for a, b in zip(cuts, cuts[1:]):
        if text[a:b].strip():
            yield dict(unit_id=unit['unit_id'], start=unit['start'] + a,
                       end=unit['start'] + b, quote=text[a:b])


def _local_clauses(unit):
    for sentence in _sentence_clauses(unit):
        text = sentence['quote']
        # A condition/example controls its coordinated propositions. Quoted
        # text stays intact, including any rejection outside the closing quote.
        inherited = bool(_CONDITIONAL_START.match(text) or
                         re.match(r'^\s*(?:it\s+is\s+)?(?:false|incorrect|untrue|wrong)\s+that\b', text, re.I))
        protected = _protected_ranges(text)
        cuts = [0]
        for match in _COORDINATION.finditer(text):
            if not any(a <= match.start() < b for a, b in protected):
                cuts.extend([match.start(), match.end()])
        cuts.append(len(text))
        for a, b in zip(cuts, cuts[1:]):
            value = text[a:b]
            if value.strip() and not re.fullmatch(r'\s*[,;]?\s*(?:and|while|whereas|but)?\s*', value, re.I):
                yield dict(unit_id=sentence['unit_id'], start=sentence['start'] + a,
                           end=sentence['start'] + b, quote=value,
                           inherited_nonaffirmative_scope=inherited)


def _nonaffirmative(clause, name):
    text = clause['quote']
    literal = base._literal(name)
    return bool(clause.get('inherited_nonaffirmative_scope') or
                base._NONUSE.search(text) or _REJECTED.search(text) or
                any(literal.search(m.group()) for m in _QUOTED.finditer(text)))


def _linked_conflicts(units, index, name):
    findings = previous._linked_conflicts(units, index, name)
    preceding = next((u for u in reversed(units[:index]) if u['text'].strip()), None)
    if preceding:
        text = re.sub(r'^[\s*#\d.()\-]+', '', preceding['text'])
        if _SCOPE_HEADING.match(text) and not any(
                x['kind'] == 'governing_adjacent_scope' and x['unit'] == preceding for x in findings):
            findings.append({'kind': 'governing_adjacent_scope', 'unit': copy.deepcopy(preceding)})
    return findings


def _operation_purpose(clause, name):
    """A purpose adjunct must attach to this operation's complete object."""
    text = clause['quote']
    protected = _protected_ranges(text)
    reagent = base._literal(name).search(text)
    for purpose in _PURPOSE.finditer(text):
        if any(a <= purpose.start() < b for a, b in protected):
            continue
        between = text[reagent.end():purpose.start()]
        # An intervening subordinate reagent/predicate makes the attachment
        # unresolved. This is syntax only, with no reagent-name knowledge.
        between = _QUOTED.sub('', between)
        between = re.sub(r'\([^)]*\)', '', between)
        if not re.search(r'\b(?:with|using|containing|contains?|which|that|is|are|was|were|stains?|labels?|provides?)\b', between, re.I):
            return True
    return False


def assess_pair(pair, projection, doc):
    occurrence, reasons = previous._instance(pair, projection, doc)
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
    if native:
        audit['validated_native_pair_ids'] = [p['pair_id'] for p in native]
        audit['conflicts'] += previous._qualified_antibody_mentions(doc, name)
        for index, unit in enumerate(doc['units']):
            for original in _local_clauses(unit):
                clause, exclusion = previous._predicate_scope(original)
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
        audit['reasons'].append('not_standalone_fluor_kind')
        return audit
    audit['conflicts'] += previous._qualified_antibody_mentions(doc, name)
    for index, unit in enumerate(doc['units']):
        if not literal.search(unit['text']):
            continue
        for original in _local_clauses(unit):
            if not literal.search(original['quote']):
                continue
            clause, exclusion = previous._predicate_scope(original)
            if exclusion:
                audit['predicate_exclusion_context'].append(exclusion)
            nonaffirmative = _nonaffirmative(clause, name)
            if base._ANTIBODY.search(clause['quote']) or base._NATIVE.search(clause['quote']):
                audit['conflicts'].append({'kind': 'same_literal_nonstandalone_predicate', 'span': clause})
            elif not nonaffirmative and previous._role(clause, name):
                audit['direct_role_evidence'].append(clause)
            elif nonaffirmative:
                audit.setdefault('nonaffirmative_mentions', []).append(clause)
            operation = {k: clause[k] for k in ('unit_id', 'start', 'end')}
            operation['text'] = clause['quote']
            if not nonaffirmative and base._direct_operation(operation, name):
                audit['operation_evidence'].append(operation)
                audit['conflicts'] += _linked_conflicts(doc['units'], index, name)
                if _operation_purpose(clause, name):
                    audit['direct_role_evidence'].append(dict(clause, predicate='independent_operation_purpose'))
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
    if any(conversion.get(key, {}).get('changes') for key in
           ('standalone_fluor_role_v1', 'standalone_fluor_role_v2', 'standalone_fluor_role_v3')):
        raise ValueError('PRIOR_ROLE_MODIFIED_PROJECTION_REQUIRES_V6_RAW_RECONVERSION')
    result = copy.deepcopy(conversion)
    projection = result['label_occurrence_projection']
    if not (base._sha(doc['text']) == doc['answer_sha256'] == projection['source_binding']['answer_sha256'] and doc['source_id'] == projection['source_binding']['source_id']):
        raise ValueError('SOURCE_BINDING_MISMATCH')
    if any(doc['text'][u['start']:u['end']] != u['text'] for u in doc['units']):
        raise ValueError('SOURCE_UNIT_MISMATCH')
    audits, changes = [], []
    for pair in projection['pairs']:
        audit = assess_pair(pair, projection, doc)
        audits.append(audit)
        if not audit['eligible']:
            continue
        changes.append({'pair_id': pair['pair_id'], 'original_pair': copy.deepcopy(pair), 'source_role_audit': copy.deepcopy(audit)})
        if audit['source_role'] == 'existing_source_native_instance_null_relation':
            pair.update(kind='source_native_fluor_key_only', native_is_not_target_assertion=True, original_loop_empty_marker=True,
                        native_null_relation_role_audit=audit)
        else:
            pair.update(kind='source_key_only', standalone_source_role_audit=audit)
    original = copy.deepcopy(projection['explicit_label_uncertainties'])
    relation_ids = {x['pair_id'].split(':', 1)[1] for x in changes if x['pair_id'].startswith('relation:')}
    projection['explicit_label_uncertainties'] = [x for x in original if not (x.get('kind') == 'reported_unresolved_relation' and x.get('relation_id') in relation_ids)]
    base._rebuild_view(projection)
    result[KEY] = {'version': VERSION, 'assessments': audits, 'changes': changes,
                   'original_explicit_uncertainties': original, 'raw_modified': False,
                   'scores_recomputed': False, 'target_or_KB_values_added': False,
                   'scientific_validity_proven': False, 'new_calls': 0}
    for key in ('wire_payload', 'source_audit', 'legacy_projection', 'legacy_runner_payload', 'legacy_runner_content'):
        if key in conversion and result[key] != conversion[key]:
            raise AssertionError('ORIGINAL_RECORD_CHANGED:' + key)
    return result
