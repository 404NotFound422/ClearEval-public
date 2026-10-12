"""Uniform posthoc v5: native fluorescence uses the original empty-marker loop."""
import copy
import cce_posthoc_scoring_v4 as previous
import cce_native_fluor_key_only_v1 as native
from cce_posthoc_scoring_v4 import (ground,numeric,base,boundary,frozen_fw3,fw4,fw6,
    alias,labels,source_backend,time_scope,target_scope,capture_scoring_calls,source_binding)

VERSION='uniform-posthoc-v5-native-key-only-original-contract'

def convert(raw,doc,case=None):
    cv=previous.convert(raw,doc,case)
    return native.apply_conversion(cv,doc,case)

def score_conversion(case,conversion,step):
    # This also applies uniformly to the isolated label dependency view. Its
    # derived null target is never passed into the source-rebinding candidate.
    cv=native.apply_conversion(conversion)
    result=previous.score_conversion(case,cv,step)
    result['processing_version']=VERSION
    result['native_fluor_key_only_v1']=copy.deepcopy(cv['native_fluor_key_only_v1'])
    captured=previous.previous._CAPTURE.get()
    if captured:
        captured[-1]['native_fluor_key_only']=copy.deepcopy(cv['native_fluor_key_only_v1'])
    return result

def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case)
    return cv,score_conversion(case,cv,step)
