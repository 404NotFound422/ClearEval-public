"""Posthoc fieldwise v5: source duration lexical/scope corrections, same formulas.

Keeps frozen v3/v4 and all raw answers unchanged. apply_conversion also permits
an independently audited source-namespace conversion to precede these time
annotations, rather than re-parsing and overwriting that conversion.
"""
from __future__ import annotations
import copy
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_fieldwise_scoring_v4 as previous
import cce_duration_scope_fix_v2 as duration_scope
ground, numeric, base = previous.ground, previous.numeric, previous.base
VERSION = 'fieldwise-scoring-v5-posthoc-duration-scope'


def apply_conversion(conversion, doc, case=None):
    cv = copy.deepcopy(conversion)
    audit, lexical = duration_scope.derive_audit(cv['source_audit'], doc)
    audit, core = previous.derive_audit(audit, doc)
    cv['source_audit'] = audit
    cv['legacy_projection'] = duration_scope.project_first_pass(audit)
    cv['legacy_runner_payload'] = {'scores': copy.deepcopy(cv['wire_payload']['scores']),
        'extraction': copy.deepcopy(cv['legacy_projection']['extraction'])}
    cv['legacy_runner_content'] = ground.canonical(cv['legacy_runner_payload'])
    cv['fieldwise_processing_v5'] = {'version': VERSION, 'duration_scope': lexical, 'core_coverage_scope': core,
        'raw_response_modified': False, 'candidate_ids_or_registry_reenumerated': False,
        'original_time_formula_unchanged': True, 'posthoc_not_frozen_confirmation_policy': True, 'new_model_requests': 0}
    return cv


def convert(raw, doc, case=None):
    return apply_conversion(previous.convert(raw, doc, case), doc, case)


def score_conversion(case, conversion, step):
    result = previous.score_conversion(case, conversion, step)
    result['processing_version'] = VERSION
    return result


def evaluate(raw, doc, case, step):
    cv = convert(raw, doc, case)
    return cv, score_conversion(case, cv, step)
