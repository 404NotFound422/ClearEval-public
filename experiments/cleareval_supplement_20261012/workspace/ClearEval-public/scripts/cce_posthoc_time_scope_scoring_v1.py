"""Source-scoped time-only posthoc extension of the locked uniform v1 scorer."""
import copy
import cce_posthoc_scoring_v1 as previous
import cce_protocol_time_scope_v1 as scope

VERSION='uniform-posthoc-v1-plus-protocol-time-scope-v1'
ground,numeric,base=previous.ground,previous.numeric,previous.base


def apply_conversion(original,doc,case=None):
    conversion=copy.deepcopy(original)
    audit,record=scope.derive_audit(original['source_audit'],doc)
    derived=scope.project(audit)
    conversion['source_audit']=audit
    projection=conversion['legacy_projection']
    projection['time_calculation']=derived['time_calculation']
    projection['extraction']['clearing_total_time_hours']=derived['extraction']['clearing_total_time_hours']
    projection['component_input_state']['s_time']=derived['component_input_state']['s_time']
    conversion['legacy_runner_payload']['extraction']=copy.deepcopy(projection['extraction'])
    conversion['legacy_runner_content']=ground.canonical(conversion['legacy_runner_payload'])
    conversion['posthoc_protocol_time_scope_processing']={'version':VERSION,'source_scope_changes':record,
        'raw_modified':False,'original_numeric_formula_changed':False,'new_model_calls':0}
    for key in original['legacy_projection']['extraction']:
        if key!='clearing_total_time_hours':
            assert projection['extraction'][key]==original['legacy_projection']['extraction'][key]
    assert conversion['wire_payload']==original['wire_payload']
    return conversion


def convert(raw,doc,case=None):
    return apply_conversion(previous.convert(raw,doc,case),doc,case)


def score_conversion(case,conversion,step):
    result=previous.score_conversion(case,conversion,step)
    result['processing_version']=VERSION
    return result
