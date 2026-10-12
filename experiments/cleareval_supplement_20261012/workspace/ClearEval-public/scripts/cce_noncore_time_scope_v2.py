"""Support source-declared immunolabeling preparation using local action context.

This is a derived phase-support annotation. It changes no raw classification,
duration, repetition, operation, coverage declaration, registry ID, or formula.
An isolated preparation or a mixed clearing action stays unresolved.
"""
from __future__ import annotations
import copy
import re
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_noncore_time_scope_fix_v1 as previous

g = previous.g
VERSION = 'source-context-noncore-time-scope-v2'
PREFIX = re.compile(r'^\s*(?:#{1,6}\s*)?(?:(?:\d+(?:\.\d+)*[.)]?|[-*+])\s+)?')
NEGATED = re.compile(r'\b(?:not|without|either|instead|alternative|optional)\b', re.I)
ANTIBODY = re.compile(r'\bincubat\w*\s+with\s+(?:(?:primary|secondary)\s+)?antibod(?:y|ies)\b|\b(?:antibody|immuno)[- ]?stain\w*\b', re.I)
PREPARATION = re.compile(r'^incubat\w*\s+with\s+(?:permeabilization|blocking)\s+solution\b', re.I)
WASH = re.compile(r'^(?:wash|rinse)\b.*\b(?:washing\s+buffer|PBS|phosphate[- ]buffered\s+saline)\b', re.I)
HEADING = re.compile(r'^(?:immunolabeling|immunostaining|permeabilization\s+and\s+blocking)\s*$', re.I)


def source_role(text):
    text = PREFIX.sub('', text.strip(), count=1)
    if HEADING.fullmatch(text):
        return 'section_heading'
    if previous.CORE.search(text):
        return 'core_or_mixed_action'
    if NEGATED.search(text):
        return 'uncertain_or_negated_action'
    if ANTIBODY.search(text):
        return 'explicit_antibody_action'
    if PREPARATION.search(text):
        return 'preparation_action'
    if WASH.search(text) and not re.search(r'\b(?:transition|exchange|switch|replace|transfer)\b', text, re.I):
        return 'washing_action'
    return 'other_action'


def derive_audit(original, doc):
    previous.require(original['source_binding']['source_id'] == doc['source_id']
        and original['source_binding']['answer_sha256'] == doc['answer_sha256']
        and g.rawsha(doc['text']) == doc['answer_sha256'], 'SOURCE_IDENTITY_MISMATCH')
    audit = copy.deepcopy(original)
    registry = g.candidate_registry(doc)
    source_records = []
    candidates = [{'candidate_id': row['candidate_id'], 'span': row['span'], 'origin': 'frozen_source_registry'}
        for row in registry['operation_candidates']]
    existing_extents = {(row['span']['start'], row['span']['end'], row['span']['quote']) for row in candidates}
    for op in original['resolved']['operations']:
        span = op['operation']
        if (span['start'], span['end'], span['quote']) not in existing_extents:
            candidates.append({'candidate_id': 'returned_record:' + op['id'], 'span': span,
                'origin': 'already_source_bound_returned_operation'})
            existing_extents.add((span['start'], span['end'], span['quote']))
    for row in sorted(candidates, key=lambda x: (x['span']['start'], x['span']['end'])):
        s = row['span']
        previous.require(doc['text'][s['start']:s['end']] == s['quote'], 'SOURCE_OPERATION_EXTENT_CHANGED')
        role = source_role(s['quote'])
        # A heading is not an action barrier; the actual source extent remains
        # in the unmodified registry and is not re-enumerated.
        if role != 'section_heading':
            source_records.append({'candidate_id': row['candidate_id'], 'span': copy.deepcopy(s),
                'origin': row['origin'], 'role': role})
    allowed = {'preparation_action', 'washing_action', 'explicit_antibody_action'}
    changes = []
    for op in audit['resolved']['operations']:
        if op['phase'] != 'labeling_preparation' or op['phase_support']['supported']:
            continue
        if op['phase_support'].get('possible_core_function'):
            continue
        span = op['operation']
        previous.require(doc['text'][span['start']:span['end']] == span['quote'], 'RETURNED_OPERATION_EXTENT_CHANGED')
        positions = [i for i, row in enumerate(source_records)
            if (row['span']['start'], row['span']['end'], row['span']['quote']) == (span['start'], span['end'], span['quote'])]
        if len(positions) != 1:
            continue
        index = positions[0]
        if source_records[index]['role'] not in allowed:
            continue
        left, right = index, index + 1
        while left and source_records[left - 1]['role'] in allowed:
            left -= 1
        while right < len(source_records) and source_records[right]['role'] in allowed:
            right += 1
        block = source_records[left:right]
        anchors = [row for row in block if row['role'] == 'explicit_antibody_action']
        # A preparatory action needs a subsequent source-declared antibody
        # action. Washes may precede, intervene, or follow that local block.
        if source_records[index]['role'] == 'preparation_action':
            anchors = [row for row in anchors if row['span']['start'] > span['end']]
        if not anchors:
            continue
        old = copy.deepcopy(op['phase_support'])
        evidence = {'basis': 'contiguous_source_declared_immunolabeling_actions',
            'source_operation_candidate_id': source_records[index]['candidate_id'],
            'source_role': source_records[index]['role'], 'source_operation': copy.deepcopy(span),
            'antibody_anchors': copy.deepcopy(anchors), 'context_action_candidates': copy.deepcopy(block),
            'left_boundary_role': source_records[left-1]['role'] if left else 'document_start',
            'right_boundary_role': source_records[right]['role'] if right < len(source_records) else 'document_end',
            'question_used_to_invent_answer_fact': False, 'original_phase_unchanged': True,
            'interpretation_scope': 'rubric_core_time_exclusion_not_biological_inertness_or_protocol_validity'}
        op['phase_support']['supported'] = True
        op['phase_support']['original_v1_support'] = old
        op['phase_support']['source_context_support_v2'] = evidence
        changes.append({'operation_id': op['id'], 'original_support': old, 'derived_supported': True, **evidence})
    old, new = copy.deepcopy(original['resolved']), copy.deepcopy(audit['resolved'])
    for resolved in [old, new]:
        for op in resolved['operations']:
            op.pop('phase_support', None)
    previous.require(old == new and original['inventory'] == audit['inventory']
        and original['source_binding'] == audit['source_binding'], 'UNRELATED_RESOLVED_DATA_CHANGED')
    audit['derived_noncore_context_v2'] = {'version': VERSION, 'changes': changes,
        'registry_sha256': registry['registry_sha256'], 'source_records': source_records,
        'no_phase_duration_repeat_or_coverage_rewritten': True, 'scientific_phase_gold': False}
    return audit, changes
