"""Uniform posthoc v4: v3 plus separately recorded source reattachment.

Never modifies frozen raw returns, existing resolved claims, KB or time values.
"""
import copy
import cce_posthoc_scoring_v3 as previous
import cce_source_binding_candidate_v1 as source_binding
from cce_posthoc_scoring_v3 import (ground,numeric,base,boundary,frozen_fw3,fw4,fw6,
    alias,labels,source_backend,time_scope,target_scope,capture_scoring_calls)

VERSION='uniform-posthoc-v4-derived-source-binding'

def convert(raw,doc,case=None):
    original=previous.convert(raw,doc,case)
    result=source_binding.apply_conversion(original,doc,case)
    for key,value in original.items():
        if key!='label_occurrence_projection':assert result[key]==value
    result['posthoc_v4_processing']={'version':VERSION,'raw_modified':False,
      'source_resolved_claims_modified':False,'KB_values_added':False,
      'same_configuration_all_returns':True,'posthoc_not_frozen_confirmation':True}
    return result

def score_conversion(case,conversion,step):
    result=previous.score_conversion(case,conversion,step)
    result['processing_version']=VERSION
    captured=previous._CAPTURE.get()
    if captured:
        captured[-1]['source_binding_candidate']=copy.deepcopy(conversion.get('source_binding_candidate_v1'))
        captured[-1]['source_binding_proposals']=copy.deepcopy(conversion['label_occurrence_projection'].get('source_binding_candidate_audit'))
    return result

def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case)
    return cv,score_conversion(case,cv,step)
