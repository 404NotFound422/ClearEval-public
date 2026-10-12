"""Fieldwise v3: distinguish complete nominal section titles from operations.

Only the derived audit changes. Original source, raw records, duration values,
coverage declarations, scoring functions and earlier versions are preserved.
"""
from __future__ import annotations
import copy
import re
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_fieldwise_scoring_v2 as previous

VERSION = 'fieldwise-scoring-v3'
numeric, ground, base = previous.numeric, previous.ground, previous.base
STRUCTURE = re.compile(r'^(?:#{1,6}\s+|(?:\d+(?:\.\d+)*[.)]?|[-*+])\s+)(.+?)\s*:?$')
NOMINAL = r'(?:dehydration|delipidation|decalcification|decolou?rization|fixation|immunolabeling|immunostaining|staining|permeabilization|blocking|clearing|storage|mounting|(?:refractive\s+index|RI)\s+matching)'
TITLE = re.compile(r'^' + NOMINAL + r'(?:\s+(?:and|&)\s+' + NOMINAL + r')*$', re.I)


def nominal_title(unit):
    match = STRUCTURE.fullmatch(unit['text'].strip())
    return bool(match and TITLE.fullmatch(match[1]))


def full_unit_span(span, unit, doc):
    """Require the complete trimmed unit, not a title-looking substring."""
    text = unit['text']
    start = unit['start'] + len(text) - len(text.lstrip())
    end = unit['end'] - (len(text) - len(text.rstrip()))
    return (span.get('unit_id') == unit['unit_id'] and span.get('start') == start
        and span.get('end') == end and span.get('quote') == text.strip()
        and doc['text'][start:end] == span['quote'])


def derive_audit(original, doc):
    if (original['source_binding']['source_id'] != doc['source_id']
            or original['source_binding']['answer_sha256'] != doc['answer_sha256']
            or ground.rawsha(doc['text']) != doc['answer_sha256']):
        raise ValueError('SOURCE_IDENTITY_MISMATCH')
    audit = copy.deepcopy(original)
    units = {u['unit_id']: u for u in doc['units'] if nominal_title(u)}
    changes, removed = [], []
    # An attached duration/repetition/condition is not discarded by a title
    # heuristic. It remains available to the existing dependency validator.
    for op in original['resolved']['operations']:
        unit = units.get(op['operation']['unit_id'])
        if not unit:
            continue
        if (not full_unit_span(op['operation'], unit, doc)
                or op.get('duration') is not None
                or op.get('repeat_evidence') is not None
                or op.get('repeat_count', 1) != 1
                or op.get('condition_evidence') is not None):
            units.pop(unit['unit_id'], None)
    for op in audit['resolved']['operations']:
        unit = units.get(op['operation']['unit_id'])
        if unit and full_unit_span(op['operation'], unit, doc):
            removed.append(op)
            changes.append({'interpretation': 'complete_nominal_section_title_not_action',
                'unit_id': unit['unit_id'], 'source_unit': copy.deepcopy(unit),
                'original_returned_record': copy.deepcopy(op), 'raw_record_preserved': True,
                'no_duration_imputed': True})
    ids = {o['id'] for o in removed}
    audit['resolved']['operations'] = [o for o in audit['resolved']['operations'] if o['id'] not in ids]
    audit['resolved']['timeline']['operation_ids'] = [i for i in audit['resolved']['timeline']['operation_ids'] if i not in ids]
    for row in audit['inventory']:
        unit = units.get(row['span']['unit_id'])
        if row['kind'] == 'operation_record_lead' and unit and full_unit_span(row['span'], unit, doc):
            changes.append({'interpretation': 'complete_nominal_section_title_inventory',
                'unit_id': unit['unit_id'], 'original_inventory_record': copy.deepcopy(row)})
            row['kind'] = 'section_heading_lead'
            row['coverage_state'] = 'classified_section_heading_not_operation'
    # Uncertainty, original partial coverage, real actions and all their
    # parameters remain. Removing a nominal title does not certify coverage.
    assert audit['resolved']['coverage'] == original['resolved']['coverage']
    audit['derived_nominal_section_titles_v3'] = {'version': VERSION, 'changes': changes,
        'coverage_declarations_unchanged': True, 'raw_source_and_registry_unchanged': True}
    return audit, changes


def convert(raw, doc, case=None):
    conversion = previous.convert(raw, doc, case)
    audit, changes = derive_audit(conversion['source_audit'], doc)
    conversion['source_audit'] = audit
    projection = previous.previous.project_first_pass(audit)
    conversion['legacy_projection'] = projection
    conversion['legacy_runner_payload'] = {'scores': copy.deepcopy(conversion['wire_payload']['scores']),
        'extraction': copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content'] = ground.canonical(conversion['legacy_runner_payload'])
    conversion['fieldwise_processing_v3'] = {'version': VERSION, 'nominal_title_changes': changes,
        'raw_response_modified': False, 'new_model_requests': 0,
        'original_numeric_functions_unchanged': True}
    return conversion


def score_conversion(case, conversion, step):
    result = previous.score_conversion(case, conversion, step)
    result['processing_version'] = VERSION
    return result


def evaluate(raw, doc, case, step):
    conversion = convert(raw, doc, case)
    return conversion, score_conversion(case, conversion, step)
