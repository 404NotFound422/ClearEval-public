"""Versioned fieldwise scorer adding local source support for immunolabeling prep."""
from __future__ import annotations
import copy
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_fieldwise_scoring_v1 as previous
import cce_noncore_time_scope_v2 as noncore_context

VERSION = 'fieldwise-scoring-v2'
numeric, ground, base = previous.numeric, previous.ground, previous.base


def convert(raw, doc, case=None):
    conversion = previous.convert(raw, doc, case)
    audit, changes = noncore_context.derive_audit(conversion['source_audit'], doc)
    conversion['source_audit'] = audit
    projection = previous.project_first_pass(audit)
    conversion['legacy_projection'] = projection
    conversion['legacy_runner_payload'] = {'scores': copy.deepcopy(conversion['wire_payload']['scores']),
        'extraction': copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content'] = ground.canonical(conversion['legacy_runner_payload'])
    conversion['fieldwise_processing_v2'] = {'version': VERSION, 'source_context_changes': changes,
        'underlying_v1_processing_preserved': True, 'raw_response_modified': False,
        'new_model_requests': 0, 'original_numeric_functions_unchanged': True}
    return conversion


def score_conversion(case, conversion, step):
    result = previous.score_conversion(case, conversion, step)
    result['processing_version'] = VERSION
    return result


def evaluate(raw, doc, case, step):
    conversion = convert(raw, doc, case)
    return conversion, score_conversion(case, conversion, step)
