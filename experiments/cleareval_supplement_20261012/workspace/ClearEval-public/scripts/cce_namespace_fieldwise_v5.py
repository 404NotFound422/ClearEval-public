"""Explicit posthoc composition: typed record IDs, frozen fw3, fw4, fw5.

No new prompt, return repair, original-status promotion, or numeric formula.
The raw return is parsed once; later stages derive audits on that conversion.
"""
import copy
import cce_record_namespace_fieldwise_v1 as namespace_fw3
import cce_fieldwise_scoring_v4 as fw4
import cce_fieldwise_scoring_v5 as fw5

VERSION = 'typed-record-namespace-plus-fieldwise-v5-posthoc-v1'
ground, numeric, base = fw5.ground, fw5.numeric, fw5.base


def convert(raw, doc, case=None):
    conversion = namespace_fw3.convert(raw, doc, case)
    audit, change = fw4.derive_audit(conversion['source_audit'], doc)
    conversion['source_audit'] = audit
    projection = fw4.previous.previous.previous.project_first_pass(audit)
    conversion['legacy_projection'] = projection
    conversion['legacy_runner_payload'] = {'scores': copy.deepcopy(conversion['wire_payload']['scores']),
                                          'extraction': copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content'] = ground.canonical(conversion['legacy_runner_payload'])
    conversion['fieldwise_processing_v4'] = {'version': fw4.VERSION, 'core_coverage_scope': change,
        'raw_response_modified': False, 'original_time_formula_unchanged': True, 'new_model_requests': 0}
    conversion = fw5.apply_conversion(conversion, doc, case)
    conversion['explicit_processing_composition'] = {
        'version': VERSION,
        'order': ['typed_record_namespace', 'frozen_fieldwise_v3', 'fieldwise_v4', 'fieldwise_v5'],
        'raw_reparsed_or_rewritten_between_layers': False,
        'original_confirmation_status_promoted': False,
        'label_boundary_policy_changed': False,
        'new_model_calls': 0,
    }
    return conversion


def score_conversion(case, conversion, step):
    result = fw5.score_conversion(case, conversion, step)
    result['processing_version'] = VERSION
    return result


def evaluate(raw, doc, case, step):
    conversion = convert(raw, doc, case)
    return conversion, score_conversion(case, conversion, step)
