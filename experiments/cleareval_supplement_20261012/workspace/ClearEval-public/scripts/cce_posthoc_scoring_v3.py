"""Uniform posthoc v3: v2 plus source time scope and target-catalog roles.

No model generation or raw rewriting. This configuration deliberately permits
previous false zeroes to become unknown. The original numeric formulas remain.
"""
import contextlib,contextvars,copy,types
import cce_posthoc_scoring_v2 as previous
import cce_source_cumulative_time_v1 as time_scope
import cce_target_catalog_role_fix_v2 as target_scope
import cce_label_occurrence_diagnostic_v1 as labels
import cce_posthoc_source_backend_v3 as source_backend

VERSION='uniform-posthoc-v3-source-record-syntax-time-scope-target-catalog'
ground,numeric,base=source_backend,previous.numeric,previous.base
boundary=source_backend
frozen_fw3,fw4,fw6,alias=previous.frozen_fw3,previous.fw4,previous.fw6,previous.alias
_CAPTURE=contextvars.ContextVar('posthoc_v3_scoring_calls',default=None)
_original=previous.previous
_convert_base=types.FunctionType(_original.convert.__code__,
    {**vars(_original),'boundary':boundary,'ground':ground,'VERSION':VERSION},
    name='convert_base_with_source_backend_v3',argdefs=_original.convert.__defaults__)

@contextlib.contextmanager
def capture_scoring_calls():
    calls=[];token=_CAPTURE.set(calls)
    try:yield calls
    finally:_CAPTURE.reset(token)

def convert(raw,doc,case=None):
    prior=_convert_base(raw,doc,case)
    result=time_scope.apply_conversion(prior,doc,case)
    assert result['wire_payload']==prior['wire_payload']
    assert result['label_occurrence_projection']==prior['label_occurrence_projection']
    result['label_occurrence_projection']=source_backend.syntax.derive_label_projection(result,doc,case)
    result['posthoc_v3_processing']={'version':VERSION,
      'order':['v2_source_name_boundaries','explicit_relation_and_numeric_designation_syntax',
        'attached_operation_parameter_binding','unchanged_fw3_fw4_fw6_processing',
        'protocol_time_scope_v2','source_cumulative_total_replaces_initial_contribution',
        'syntax_aware_occurrence_label_projection','target_catalog_role_v2_at_scoring'],
      'raw_modified':False,'posthoc_not_frozen_confirmation':True,'new_model_calls':0}
    return result

def score_conversion(case,conversion,step):
    old=previous.score_conversion(case,conversion,step)
    runner,registry=numeric.runtime()
    meta=runner.QUESTION_META_KB[registry.questions[str(case['question_id'])]['question_id']]
    targets=meta.get('marker_query_targets') or []
    before=copy.deepcopy(old['occurrence_label_calculation'])
    with alias.source_key_alias():
        after=target_scope.score_label_occurrences(labels.score_label_occurrences,
            conversion['label_occurrence_projection'],runner,old['quantitative_data'],
            old['user_preference_vector'],targets)
    result=copy.deepcopy(old)
    result['component_numeric_proposals']['s_label']=after['s_label']
    result['metrics']=numeric.derive(result['component_numeric_proposals'],step,True)
    result['complete_numeric_CCE']=all(numeric.finite(result['metrics'][k]) for k in ['Com','Cor','Eff'])
    result['processing_version']=VERSION
    result['label_before_target_catalog_role_fix']=before
    result['occurrence_label_calculation']=after
    result['posthoc_target_catalog_version']=target_scope.VERSION
    assert after['channels']['s_method_fluor_compat']==before['channels']['s_method_fluor_compat']
    stable=numeric.DIRECT+['s_method','s_trans','s_time','sr','sp','Com','Cor']
    assert all(result['metrics'][k]==old['metrics'][k] for k in stable)
    capture=_CAPTURE.get()
    if capture is not None:
        wire=conversion['wire_payload'];e=wire['grounded_extraction']
        capture.append({'scoring_call_index':len(capture),
          'input_view_sha256':ground.rawsha(ground.canonical(wire)),
          'source_binding':copy.deepcopy(conversion['source_audit']['source_binding']),
          'record_counts':{k:len(v) for k,v in e.items() if isinstance(v,list)},
          'before':before,'after':copy.deepcopy(after),
          'source_time_scope':copy.deepcopy(conversion.get('posthoc_protocol_time_scope_processing')),
          'metrics':copy.deepcopy(result['metrics']),
          'numeric_formula_unchanged':True,'raw_modified':False})
    return result

def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case)
    return cv,score_conversion(case,cv,step)
