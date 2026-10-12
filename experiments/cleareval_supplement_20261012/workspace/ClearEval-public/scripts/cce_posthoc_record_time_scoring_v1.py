"""Uniform, posthoc attached-record and source-cumulative time composition."""
import copy,types
import cce_posthoc_scoring_v2 as previous
import cce_posthoc_scoring_v2 as source_base
import cce_attached_operation_parameters_v1 as boundary
import cce_posthoc_time_scope_scoring_v1 as time_scope
import cce_protocol_time_scope_v2 as phase_scope
import cce_source_cumulative_time_v1 as cumulative

VERSION='uniform-posthoc-attached-parameters-source-cumulative-time-v1'
ground,numeric,base=boundary,previous.numeric,previous.base
_base_convert=types.FunctionType(source_base.convert.__code__,
    {**source_base.convert.__globals__,'boundary':boundary,'ground':boundary},name='convert',argdefs=source_base.convert.__defaults__)
_apply_scope=types.FunctionType(time_scope.apply_conversion.__code__,
    {**time_scope.apply_conversion.__globals__,'scope':phase_scope},name='apply_conversion',argdefs=time_scope.apply_conversion.__defaults__)

def apply_conversion(original,doc,case=None):
    return cumulative.apply_conversion(original,doc,case)

def convert(raw,doc,case=None):
    return apply_conversion(_base_convert(raw,doc,case),doc,case)

def score_conversion(case,conversion,step):
    result=previous.score_conversion(case,conversion,step)
    result['processing_version']=VERSION
    return result
