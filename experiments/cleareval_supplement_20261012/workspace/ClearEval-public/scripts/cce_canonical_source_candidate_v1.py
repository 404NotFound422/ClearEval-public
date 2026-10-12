"""Evaluate a complete canonical source with an exact map to the submitted answer.

The frozen structural normalizer changes only recognized list prefixes and white
space. Question, references, rubric, schema order and generation options survive.
Source IDs and offsets in model output refer to this evaluation document. The
original answer, its raw SR/SP and a character map are kept outside the prompt.
"""
from __future__ import annotations
import copy
import cce_source_alignment_prompt_candidate_v1 as base
import cce_representation_repair_v3 as representation

CANDIDATE_VERSION = 'canonical-full-source-v1-on-source-alignment-v1'
ground = base.original


def __getattr__(name):
    return getattr(base, name)


def evaluation_case(case):
    view = representation.canonicalize_full_text(case['model_response'])
    result = copy.deepcopy(case)
    result['model_response'] = view['evaluation_text']
    result['answer_sha256'] = view['evaluation_view_sha256']
    return result


def evaluation_document(case, original_doc=None):
    if original_doc is not None:
        expected = ground.document(case['model_response'], ground.source_id_for_case(case))
        if original_doc != expected:
            raise ValueError('ORIGINAL_SOURCE_DOCUMENT_MISMATCH')
    evaluated = evaluation_case(case)
    return ground.document(evaluated['model_response'], ground.source_id_for_case(evaluated))


def schema_for_document(doc):
    return base.schema_for_document(doc)


def make_prompt(case, doc):
    evaluated = evaluation_case(case)
    if doc != evaluation_document(case):
        raise ValueError('CANONICAL_SOURCE_DOCUMENT_MISMATCH')
    return base.make_prompt(evaluated, doc)


def payload_for(prompt, spec, public):
    return base.payload_for(prompt, spec, public)


def source_mapping(case, doc):
    if doc != evaluation_document(case):
        raise ValueError('CANONICAL_SOURCE_DOCUMENT_MISMATCH')
    view = representation.canonicalize_full_text(case['model_response'])
    original = ground.document(case['model_response'], ground.source_id_for_case(case))
    units = []
    for unit in doc['units']:
        ranges = representation.original_ranges(view, unit['start'], unit['end'])
        units.append({
            'evaluation_unit_id': unit['unit_id'],
            'evaluation_start': unit['start'], 'evaluation_end': unit['end'],
            'original_character_ranges': ranges,
            'original_unit_ids': [u['unit_id'] for u in original['units']
                if any(a < u['end'] and b > u['start'] for a, b in ranges)],
        })
    return {
        'candidate_version': CANDIDATE_VERSION,
        'original_source_id': original['source_id'],
        'evaluation_source_id': doc['source_id'],
        'original_question_sha256': ground.rawsha(case['specific_question']),
        'offset_convention': 'Python Unicode code points; end exclusive',
        'model_citations_use_evaluation_offsets': True,
        'original_SRSP_not_recomputed_from_canonical_text': True,
        'evaluation_units_to_original': units, **view,
    }


def map_resolved_spans(value, view, doc):
    """A sidecar for resolved model citations; never relabel canonical offsets."""
    rows = []
    def visit(item, path):
        if isinstance(item, dict):
            if (item.get('source_id') == doc['source_id']
                    and type(item.get('start')) is int and type(item.get('end')) is int):
                start, end = item['start'], item['end']
                rows.append({'processing_path': path, 'evaluation_start': start,
                    'evaluation_end': end,
                    'evaluation_quote': doc['text'][start:end],
                    'original_character_ranges': representation.original_ranges(view, start, end)})
            for key, child in item.items():
                visit(child, path + [key])
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, path + [index])
    visit(value, [])
    return rows
