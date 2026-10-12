"""Source-role repair for standalone direct stains; no antigen/KB inference.

This is a post-hoc projection adapter. A named incubation alone is insufficient:
the source must also declare direct staining use or a direct/small-molecule dye
role. Antibody and native contexts are separate roles, including cross-sentence
secondary detection. Raw/model claims and unrelated uncertainty are retained.
"""
from __future__ import annotations
import copy
import hashlib
import re

VERSION = 'source-standalone-fluor-role-v2-source-context'
_NONUSE = re.compile(r"\b(?:not|no|without|never|avoid|omit\w*|optional\w*|alternativ\w*|either|unless|if|instead|may|could|might)\b|for example|such as|e\.g\.|例如|可选|不用", re.I)
_ANTIBODY = re.compile(r'\b(?:antibod\w*|immunoglobulin\w*|IgG|IgM|secondary|primary|conjugat\w*)\b|(?:^|\W)anti[- ]', re.I)
_NATIVE = re.compile(r'\b(?:native|endogenous|intrinsic|fluorescent protein|reporter protein)\b|内源', re.I)
_HEADER = re.compile(r'^\s*(?:\*{1,2})?(?:chosen|selected)\s+label(?:ing|ling)?\s*:', re.I)
_ACTION = r'(?:Incubation\s+with|Incubate\s+(?:(?:the\s+)?(?:sample|tissue|section)s?\s+)?with|(?:Counter)?stain\s+(?:(?:the\s+)?(?:sample|tissue|section)s?\s+)?with)'


def _sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def _literal(name):
    return re.compile(r'(?<![\w+\-])' + re.escape(name) + r'(?![\w+\-])')


def _clauses(unit):
    """Finite sentence/semicolon scope; preserve abbreviations and source offsets."""
    text = unit['text']
    header = _HEADER.match(text)
    if header:
        # List members have their own roles: a native reporter elsewhere in the
        # selected list must not turn a separate direct stain into a protein.
        start = header.end()
        depth = 0
        cuts = [start]
        for index in range(start, len(text)):
            char = text[index]
            if char == '(':
                depth += 1
            elif char == ')':
                depth = max(0, depth - 1)
            elif char in ',;' and depth == 0:
                cuts.append(index + 1)
        cuts.append(len(text))
        for a, b in zip(cuts, cuts[1:]):
            yield {'unit_id': unit['unit_id'], 'start': unit['start'] + a,
                   'end': unit['start'] + b, 'quote': text[a:b]}
        return
    cuts = [0]
    for m in re.finditer(r';|[.!?](?=\s+[A-Z*]|\s*$)', text):
        if re.search(r'(?:e\.g|i\.e)$', text[:m.start()], re.I):
            continue
        cuts.append(m.end())
    cuts.append(len(text))
    for a, b in zip(cuts, cuts[1:]):
        if text[a:b].strip():
            yield {'unit_id': unit['unit_id'], 'start': unit['start'] + a,
                   'end': unit['start'] + b, 'quote': text[a:b]}


def _span_ok(span, doc, quote=None):
    if not isinstance(span, dict):
        return False
    a, b = span.get('start'), span.get('end')
    if type(a) is not int or type(b) is not int or not (0 <= a < b <= len(doc['text'])):
        return False
    if span.get('answer_sha256', doc['answer_sha256']) != doc['answer_sha256']:
        return False
    value = span.get('quote', quote)
    return isinstance(value, str) and doc['text'][a:b] == value and (quote is None or value == quote)


def _role_clause(clause, name):
    """A source statement of direct use, not a claim of biological specificity."""
    text = clause['quote']
    n = re.escape(name)
    patterns = [
        # A named direct reagent is the grammatical subject of staining use.
        r'(?<![\w+\-])' + n + r'(?![\w+\-])\s+(?:stains?|counterstains?|labels?)\b',
        r'(?<![\w+\-])' + n + r'(?![\w+\-])\s+(?:provides?|is\s+used\s+for)\s+[^.;\n]{0,65}\blabell?ing\b',
        r'(?<![\w+\-])' + n + r'(?![\w+\-])\s+for\s+[^.;\n]{0,45}\b(?:labell?ing|staining)\b',
        r'\b(?:direct|standalone|small[- ]molecule)\s+(?:fluorescent\s+)?(?:dye|stain)\s+' + n + r'(?![\w+\-])',
        r'(?<![\w+\-])' + n + r'(?![\w+\-])\s+is\s+(?:a\s+)?(?:direct|standalone|small[- ]molecule)\s+(?:fluorescent\s+)?(?:dye|stain)\b',
    ]
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _direct_operation(unit, name):
    # Reagent must be the complete direct object, not a substring of a named
    # antibody, conjugate, composite list, or an object followed by "antibody".
    pattern = (r'^\s*(?:[-*]\s*)?(?:\d+(?:\.\d+)*[.)]?\s+)?' + _ACTION
               + r'\s+(?:1:\d+\s+)?(?P<name>' + re.escape(name) + r')(?P<tail>.*)$')
    match = re.match(pattern, unit['text'].strip(), re.I)
    if not match:
        return False
    tail = match.group('tail')
    if tail and not re.match(r'\s*(?:$|\(|in\b|at\b|for\b|\.|,\s*(?:Temperature|Time)\s*:)', tail, re.I):
        return False
    return not (_NONUSE.search(unit['text']) or _ANTIBODY.search(unit['text']) or _NATIVE.search(unit['text']))


def _linked_context_conflicts(units, index, name):
    """Explicit adjacent scope/coreference only; no nearest-primary target guess."""
    previous = next((u for u in reversed(units[:index]) if u['text'].strip()), None)
    following = next((u for u in units[index + 1:] if u['text'].strip()), None)
    conflicts = []
    # A previous primary step alone is a warning, not proof that a separately
    # declared direct stain is an antibody. A secondary/antibody heading does
    # govern the immediately subordinate named incubation.
    if previous:
        stripped = re.sub(r'^[\s*#\d.()\-]+|[\s*:]+$', '', previous['text'])
        heading = not re.search(r'\b(?:incubat\w*|wash\w*|stain\w*|add|apply|remove)\b', stripped, re.I)
        if heading and (_ANTIBODY.search(stripped) or _NATIVE.search(stripped) or _NONUSE.search(stripped)):
            conflicts.append({'kind': 'governing_adjacent_scope', 'unit': copy.deepcopy(previous)})
        if re.search(r'\b(?:this|the|following)\s+(?:secondary|antibody|conjugate|detector)\b|\b(?:secondary|antibody)\s+(?:detection|incubation)\s*[:.]?\s*$', previous['text'], re.I):
            conflicts.append({'kind': 'preceding_detector_scope', 'unit': copy.deepcopy(previous)})
    if following and re.search(r'\b(?:it|this\s+(?:reagent|signal|dye|label|step))\s+(?:is|was|binds?|detects?|recognizes?|labels?)\b', following['text'], re.I):
        if _ANTIBODY.search(following['text']) or _NATIVE.search(following['text']):
            conflicts.append({'kind': 'following_explicit_coreference', 'unit': copy.deepcopy(following)})
    return conflicts


def assess_pair(pair, projection, doc):
    audit = {'pair_id': pair.get('pair_id'), 'eligible': False, 'reasons': [],
             'operation_evidence': [], 'direct_role_evidence': [], 'conflicts': []}
    if pair.get('kind') != 'unresolved_relation' or pair.get('raw_relation_status') != 'unknown':
        audit['reasons'].append('not_unknown_relation'); return audit
    if pair.get('marker_literal') is not None or pair.get('reported_target_literal') is not None:
        audit['reasons'].append('reported_target_claim_retained'); return audit
    name, eid = pair.get('fluor_literal'), pair.get('entity_id')
    if not isinstance(name, str) or not name.strip():
        audit['reasons'].append('no_literal'); return audit
    occurrences = [x for x in projection.get('occurrences', []) if x.get('entity_id') == eid]
    if len(occurrences) != 1:
        audit['reasons'].append('occurrence_not_unique'); return audit
    occurrence = occurrences[0]
    if occurrence.get('raw_kind') != 'fluorophore' or occurrence.get('source_affirmative_use') is not True or occurrence.get('included_as_used_instance') is not True or occurrence.get('local_nonuse_audit', {}).get('excluded') is True:
        audit['reasons'].append('not_source_supported_used_fluor'); return audit
    if not _span_ok(occurrence.get('span'), doc, name):
        audit['reasons'].append('invalid_entity_source_span'); return audit
    if _ANTIBODY.search(name) or _NATIVE.search(name):
        audit['reasons'].append('name_declares_nonstandalone_role'); return audit
    if any(x.get('entity_id') == eid and (x.get('marker_literal') is not None or x.get('reported_target_literal') is not None) for x in projection['pairs']):
        audit['reasons'].append('same_occurrence_target_claim_retained'); return audit
    literal = _literal(name)
    for index, unit in enumerate(doc['units']):
        if not literal.search(unit['text']):
            continue
        clauses = [c for c in _clauses(unit) if literal.search(c['quote'])]
        for clause in clauses:
            if _ANTIBODY.search(clause['quote']) or _NATIVE.search(clause['quote']):
                audit['conflicts'].append({'kind': 'same_literal_nonstandalone_context', 'span': clause})
            # A distinct negative alternative is recorded without erasing an
            # affirmative current operation. It cannot itself establish use.
            if _NONUSE.search(clause['quote']):
                audit.setdefault('nonaffirmative_mentions', []).append(clause)
            elif not (_ANTIBODY.search(clause['quote']) or _NATIVE.search(clause['quote'])) and _role_clause(clause, name):
                audit['direct_role_evidence'].append(clause)
        if _direct_operation(unit, name):
            audit['operation_evidence'].append(copy.deepcopy(unit))
            audit['conflicts'] += _linked_context_conflicts(doc['units'], index, name)
    if not audit['operation_evidence']:
        audit['reasons'].append('no_affirmative_independent_operation')
    if not audit['direct_role_evidence']:
        audit['reasons'].append('direct_stain_role_not_source_declared')
    if audit['conflicts']:
        audit['reasons'].append('antibody_native_or_scope_conflict')
    audit['eligible'] = not audit['reasons']
    audit['source_role'] = 'source_declared_standalone_direct_staining_reagent' if audit['eligible'] else 'unresolved'
    audit['molecular_class_or_specificity_validated'] = False
    audit['target_added'] = False
    return audit


def _rebuild_view(projection):
    view, losses = {}, []
    for name in sorted({x['fluor_literal'] for x in projection['pairs']}):
        rows = [x for x in projection['pairs'] if x['fluor_literal'] == name]
        known = {x['marker_literal'] for x in rows if x['marker_literal'] is not None}
        unresolved = [x['pair_id'] for x in rows if x['marker_literal'] is None and x['kind'] not in ('source_key_only', 'source_native_fluor_key_only')]
        if len(known) == 1:
            view[name] = next(iter(known))
        elif not known:
            view[name] = ''
        if len(known) > 1 or unresolved:
            losses.append({'literal_name': name, 'supported_targets': sorted(known), 'unresolved_pair_ids': unresolved, 'single_value_cannot_represent_full_occurrence_graph': True})
    projection.update(supported_local_dictionary_view=view, single_value_projection_losses=losses, lossless_single_value_projection=not losses)


def apply_conversion(conversion, doc, case=None):
    if conversion.get('standalone_fluor_role_v2', {}).get('version') == VERSION:
        return copy.deepcopy(conversion)
    result = copy.deepcopy(conversion)
    projection = result['label_occurrence_projection']
    if not (_sha(doc['text']) == doc['answer_sha256'] == projection['source_binding']['answer_sha256'] and doc['source_id'] == projection['source_binding']['source_id']):
        raise ValueError('SOURCE_BINDING_MISMATCH')
    for unit in doc['units']:
        if doc['text'][unit['start']:unit['end']] != unit['text']:
            raise ValueError('SOURCE_UNIT_MISMATCH')
    audits, changes = [], []
    for pair in projection['pairs']:
        audit = assess_pair(pair, projection, doc)
        audits.append(audit)
        if audit['eligible']:
            changes.append({'pair_id': pair['pair_id'], 'original_pair': copy.deepcopy(pair), 'source_role_audit': copy.deepcopy(audit)})
            pair['kind'] = 'source_key_only'
            pair['standalone_source_role_audit'] = audit
    original_uncertainties = copy.deepcopy(projection['explicit_label_uncertainties'])
    relation_ids = {x['pair_id'].split(':', 1)[1] for x in changes if x['pair_id'].startswith('relation:')}
    projection['explicit_label_uncertainties'] = [x for x in original_uncertainties if not (x.get('kind') == 'reported_unresolved_relation' and x.get('relation_id') in relation_ids)]
    _rebuild_view(projection)
    result['standalone_fluor_role_v2'] = {'version': VERSION, 'assessments': audits, 'changes': changes,
        'original_explicit_uncertainties': original_uncertainties, 'raw_modified': False, 'scores_recomputed': False,
        'target_or_KB_values_added': False, 'chemical_class_or_scientific_validity_proven': False, 'new_calls': 0}
    for key in ('wire_payload', 'source_audit', 'legacy_projection', 'legacy_runner_payload', 'legacy_runner_content'):
        if key in conversion and result[key] != conversion[key]:
            raise AssertionError('ORIGINAL_RECORD_CHANGED:' + key)
    return result
