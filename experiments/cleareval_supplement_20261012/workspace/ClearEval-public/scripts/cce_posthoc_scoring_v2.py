"""Uniform v2 composition: existing posthoc v1 plus concentration name boundary."""
import types
import cce_posthoc_scoring_v1 as previous
import cce_posthoc_name_boundary_v2 as boundary

VERSION='uniform-posthoc-v2-explicit-concentration-name-boundary'
ground,numeric,base=boundary,previous.numeric,previous.base
frozen_fw3,fw4,fw6,alias=previous.frozen_fw3,previous.fw4,previous.fw6,previous.alias
convert=types.FunctionType(previous.convert.__code__,
    {**vars(previous),'boundary':boundary,'ground':boundary,'VERSION':VERSION},name='convert',argdefs=previous.convert.__defaults__)
score_conversion=types.FunctionType(previous.score_conversion.__code__,
    {**vars(previous),'VERSION':VERSION},name='score_conversion')
def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case)
    return cv,score_conversion(case,cv,step)
