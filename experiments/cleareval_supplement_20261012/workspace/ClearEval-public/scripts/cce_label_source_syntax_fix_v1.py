"""Two source-syntax repairs; no KB values, entity splitting or raw repair.

The accepted entity and relation must still pass the original complete-name,
occurrence, local-clause, and declared-endpoint checks. This module does not
change native-signal evidence or infer missing targets.
"""
import copy
import re
import types

import cce_posthoc_name_boundary_v2 as previous_boundary
import cce_label_occurrence_diagnostic_v1 as labels

VERSION = 'source-syntax-numeric-designation-explicit-labeling-of-v1'
_NUMERIC_DESIGNATION = re.compile(r'[A-Za-z][A-Za-z0-9 _().-]*\s+[0-9]{3,4}/[0-9]{3,4}(?:\s*nm)?')
_ALTERNATIVE = re.compile(r'\b(?:either|neither|or|alternative|optional|instead|unless|if)\b|备选|可选|或者', re.I)
_NEGATIVE = re.compile(r"\b(?:not|never|without|avoid|omit|don['’]t)\b|不使用|不采用", re.I)


def numeric_designation(literal):
    """Preserve a complete source name with a terminal numeric slash token.

    This is a punctuation classification, not an alias, spectral measurement,
    or proof of biological atomicity. No component of the name is split off.
    """
    return bool(_NUMERIC_DESIGNATION.fullmatch(literal))


def name_atomicity(literal, support):
    result = copy.deepcopy(previous_boundary.namespace.name_atomicity(literal, support))
    if numeric_designation(literal) and 'slash_composite_syntax' in result['reasons']:
        result['reasons'].remove('slash_composite_syntax')
        result['state'] = 'unresolved_composite_syntax' if result['reasons'] else 'no_composite_syntax_detected_provisional'
        result['projection_eligible_provisional'] = not result['reasons']
        result['numeric_designation_audit'] = {'literal': literal,
            'full_literal_preserved': True, 'entities_split': False,
            'numeric_slash_is_not_by_itself_an_alternative_list': True,
            'semantic_atomicity_confirmed': False}
    return result


def affirmative_entity_use(name, text):
    old = previous_boundary.namespace.affirmative_entity_use(name, text)
    if old or not numeric_designation(name):
        return old
    # Only repair the existing Chosen/Selected-field slash test. An actual
    # alternative/negative/conditional group remains excluded. Removing the
    # literal here is a punctuation diagnostic, never a rewrite of the source.
    declared = bool(re.search(r'(?:chosen|selected)\s+(?:label(?:l?ing)?|marker|signal)s?\s*[:：][^\n]*' + re.escape(name), text, re.I))
    groups = [p for p in re.split(r'[,;，；]', text) if name in p]
    safe = bool(groups) and all(not _ALTERNATIVE.search(p) and not _NEGATIVE.search(p)
        and '/' not in p.replace(name, '') for p in groups)
    return declared and safe


def relation_policy(f, t, evidence, entities):
    old, why = previous_boundary.namespace.relation_policy(f, t, evidence, entities)
    if old or why != 'relationship_not_mechanically_explicit':
        return old, why
    text = evidence['quote']
    if _NEGATIVE.search(text) or _ALTERNATIVE.search(text):
        return False, 'explicit_labeling_of_has_negative_or_alternative_scope'
    # Adjacent exact endpoints around one fixed predicate: no wildcard can
    # consume a different fluor/target or an unrelated clause.
    pattern = (r'\buse\s+of\s+' + re.escape(f)
        + r'\s+allows\s+for\s+(?:(?:robust|specific|selective|direct|effective|efficient|strong|fluorescent)\s+){0,2}'
        + r'label(?:l)?ing\s+of\s+' + re.escape(t) + r'(?![\w+\-/])')
    if re.search(pattern, text, re.I):
        return True, 'explicit_use_of_allows_labeling_of_named_target_not_expert_confirmed'
    return False, why


# Rebind the original production functions in an isolated environment. No
# frozen module/global is changed, and the same occurrence/clause checks run.
_environment = {**previous_boundary._environment, 'name_atomicity': name_atomicity,
    'affirmative_entity_use': affirmative_entity_use, 'relation_policy': relation_policy}
for _name in previous_boundary.previous._functions:
    _old = getattr(previous_boundary.namespace, _name)
    _new = types.FunctionType(_old.__code__, _environment, name=_name,
        argdefs=_old.__defaults__, closure=_old.__closure__)
    _new.__kwdefaults__ = _old.__kwdefaults__
    _environment[_name] = _new
    globals()[_name] = _new

_boundary_convert = types.FunctionType(previous_boundary.previous.first.convert.__code__,
    {**vars(previous_boundary.previous.first), '_convert': _environment['_convert_namespace'],
     'ADAPTER_VERSION': VERSION}, name='source_boundary_convert')
convert_source = types.FunctionType(previous_boundary.convert.__code__,
    {**vars(previous_boundary), '_boundary_convert': _boundary_convert}, name='convert_source')
boundary = types.SimpleNamespace(**{**vars(previous_boundary), **{n: _environment[n]
    for n in previous_boundary.previous._functions}, 'name_atomicity': name_atomicity,
    'affirmative_entity_use': affirmative_entity_use, 'relation_policy': relation_policy,
    'convert': convert_source, 'ADAPTER_VERSION': VERSION,
    '_environment': _environment, '_boundary_convert': _boundary_convert})

_label_ground = types.SimpleNamespace(**{**vars(labels.ground),
    'affirmative_entity_use': affirmative_entity_use})
derive_label_projection = types.FunctionType(labels.derive_label_projection.__code__,
    {**vars(labels), 'ground': _label_ground}, name='derive_label_projection',
    argdefs=labels.derive_label_projection.__defaults__)


def build_backend(base):
    """Compose onto the concentration/source-boundary backend, without mutation."""
    environment = {**base._environment, 'name_atomicity': name_atomicity,
        'affirmative_entity_use': affirmative_entity_use, 'relation_policy': relation_policy}
    for name in base.previous._functions:
        old = getattr(base.namespace, name)
        new = types.FunctionType(old.__code__, environment, name=name,
            argdefs=old.__defaults__, closure=old.__closure__)
        new.__kwdefaults__ = old.__kwdefaults__
        environment[name] = new
    inner = types.FunctionType(base.previous.first.convert.__code__,
        {**vars(base.previous.first), '_convert': environment['_convert_namespace'],
         'ADAPTER_VERSION': VERSION}, name='source_boundary_convert')
    convert = types.FunctionType(base.convert.__code__,
        {**vars(base), '_boundary_convert': inner}, name='convert_source')
    return types.SimpleNamespace(**{**vars(base), **{n: environment[n]
        for n in base.previous._functions}, 'name_atomicity': name_atomicity,
        'affirmative_entity_use': affirmative_entity_use, 'relation_policy': relation_policy,
        'convert': convert, 'ADAPTER_VERSION': VERSION,
        '_environment': environment, '_boundary_convert': inner})


def make_scorer(previous):
    """Isolated v2+syntax adapter for the fifteen-return sensitivity check.

    `previous` is posthoc v2. The eventual combined scorer is owned by the
    independent reviewer; this check does not mutate its in-progress v3.
    """
    original_v1 = previous.previous
    convert_v2 = types.FunctionType(original_v1.convert.__code__,
        {**vars(original_v1), 'boundary': boundary, 'ground': boundary},
        name='convert_v2_with_source_syntax', argdefs=original_v1.convert.__defaults__)

    def convert(raw, doc, case=None):
        cv = convert_v2(raw, doc, case)
        cv['label_occurrence_projection'] = derive_label_projection(cv, doc, case)
        cv['source_syntax_repair'] = {'version': VERSION, 'raw_modified': False,
            'full_name_or_target_inferred': False, 'KB_value_added': False,
            'native_evidence_rebound': False, 'original_time_and_numeric_functions_unchanged': True}
        return cv

    return types.SimpleNamespace(**{**vars(previous), 'VERSION': VERSION,
        'ground': boundary, 'boundary': boundary, 'convert': convert})
