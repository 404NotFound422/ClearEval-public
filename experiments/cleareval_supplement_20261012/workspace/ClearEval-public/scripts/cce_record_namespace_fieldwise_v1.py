"""Posthoc typed-ID conversion followed by exactly the frozen fw3 transforms.

Original confirmation status is never promoted. This is a separate processor.
Time candidates can compose on the returned conversion through their explicit
apply_conversion interface, without decoding or rewriting a second raw return.
"""
import copy
import cce_record_namespace_scope_v1 as namespace
import cce_fieldwise_scoring_v1 as first
import cce_fieldwise_scoring_v2 as second
import cce_fieldwise_scoring_v3 as third

VERSION = 'typed-record-namespace-with-frozen-fw3-posthoc-v1'
ground, numeric, base = third.ground, third.numeric, third.base


def apply_frozen_fieldwise_v3(conversion, doc, case=None):
    """Same order and functions as fw1 -> fw2 -> fw3, no raw mutation."""
    audit, record_changes = first.operation_scope.derive_audit(conversion['source_audit'], doc)
    audit, duration_changes = first.duration_scope.derive_audit(audit, doc)
    audit, noncore_changes = first.noncore_scope.derive_audit(audit, doc)
    empty_changes = first.separate_empty_modules(audit, doc)
    rubric_changes = first.apply_time_rubric(audit)
    conversion['source_audit'] = audit
    projection = first.project_first_pass(audit)
    conversion['legacy_projection'] = projection
    conversion['legacy_runner_payload'] = {'scores': copy.deepcopy(conversion['wire_payload']['scores']),
                                            'extraction': copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content'] = ground.canonical(conversion['legacy_runner_payload'])
    conversion['label_occurrence_projection'] = first.labels.derive_label_projection(conversion, doc, case)
    conversion['fieldwise_processing'] = {'version': first.VERSION, 'wire_version': ground.VERSION,
        'operation_records_changed': [r for r in record_changes if r['changed']],
        'duration_candidates_reclassified': duration_changes, 'noncore_time_scope_changes': noncore_changes,
        'empty_modules_are_protocol_omissions': empty_changes, 'original_rubric_time_conventions': rubric_changes,
        'primary_time_scope': first.TIME_SCOPE, 'raw_response_modified': False, 'new_model_requests': 0}
    audit, context_changes = second.noncore_context.derive_audit(audit, doc)
    conversion['fieldwise_processing_v2'] = {'version': second.VERSION,
        'source_context_changes': context_changes, 'underlying_v1_processing_preserved': True,
        'raw_response_modified': False, 'new_model_requests': 0, 'original_numeric_functions_unchanged': True}
    audit, title_changes = third.derive_audit(audit, doc)
    conversion['source_audit'] = audit
    projection = first.project_first_pass(audit)
    conversion['legacy_projection'] = projection
    conversion['legacy_runner_payload'] = {'scores': copy.deepcopy(conversion['wire_payload']['scores']),
                                            'extraction': copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content'] = ground.canonical(conversion['legacy_runner_payload'])
    conversion['fieldwise_processing_v3'] = {'version': third.VERSION,
        'nominal_title_changes': title_changes, 'raw_response_modified': False,
        'new_model_requests': 0, 'original_numeric_functions_unchanged': True}
    conversion['namespace_processing'] = {'version': VERSION, 'original_confirmation_status_promoted': False,
                                          'raw_ids_changed': False, 'scoring_formula_changed': False}
    return conversion


def convert(raw, doc, case=None):
    return apply_frozen_fieldwise_v3(namespace.convert(raw, doc), doc, case)


def score_conversion(case, conversion, step):
    result = third.score_conversion(case, conversion, step)
    result['processing_version'] = VERSION
    return result


def evaluate(raw, doc, case, step):
    conversion = convert(raw, doc, case)
    return conversion, score_conversion(case, conversion, step)
