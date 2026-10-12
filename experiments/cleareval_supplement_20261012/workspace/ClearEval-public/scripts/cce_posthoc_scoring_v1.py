"""Uniform posthoc scorer: typed IDs, source name boundary, fw6, source alias.

This is not the frozen confirmation scorer. Raw names, IDs, ordinals, scores,
and original statuses are never rewritten. No generation entry point exists.
"""
import copy
import cce_marker_combination_boundary_v2 as boundary
import cce_record_namespace_fieldwise_v1 as frozen_fw3
import cce_fieldwise_scoring_v4 as fw4
import cce_fieldwise_scoring_v6 as fw6
import cce_scales_source_key_alias_v1 as alias

VERSION='uniform-posthoc-typed-namespace-source-boundary-fw6-source-alias-v1'
ground,numeric,base=boundary,fw6.numeric,fw6.base

def convert(raw,doc,case=None):
    conversion=frozen_fw3.apply_frozen_fieldwise_v3(boundary.convert(raw,doc),doc,case)
    audit,change=fw4.derive_audit(conversion['source_audit'],doc)
    conversion['source_audit']=audit
    projection=fw4.previous.previous.previous.project_first_pass(audit)
    conversion['legacy_projection']=projection
    conversion['legacy_runner_payload']={'scores':copy.deepcopy(conversion['wire_payload']['scores']),
        'extraction':copy.deepcopy(projection['extraction'])}
    conversion['legacy_runner_content']=ground.canonical(conversion['legacy_runner_payload'])
    conversion['fieldwise_processing_v4']={'version':fw4.VERSION,'core_coverage_scope':change,
        'raw_response_modified':False,'original_time_formula_unchanged':True,'new_model_requests':0}
    conversion=fw6.apply_conversion(conversion,doc,case)
    conversion['uniform_posthoc_processing']={'version':VERSION,
        'order':['typed_record_namespace','source_declared_name_boundary','frozen_fieldwise_v3',
                 'fieldwise_v4','fieldwise_v6_including_v5','authored_ScaleS_source_key_at_scoring'],
        'raw_modified':False,'original_confirmation_status_promoted':False,
        'relation_inferred_from_name_boundary':False,'posthoc_not_prospective_validation':True,
        'new_model_calls':0}
    return conversion

def score_conversion(case,conversion,step):
    result=alias.score_with_alias(fw6.score_conversion,case,conversion,step)
    result['processing_version']=VERSION
    return result

def evaluate(raw,doc,case,step):
    conversion=convert(raw,doc,case)
    return conversion,score_conversion(case,conversion,step)
