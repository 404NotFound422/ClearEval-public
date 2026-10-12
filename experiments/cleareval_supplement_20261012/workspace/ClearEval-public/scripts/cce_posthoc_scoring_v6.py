"""Development posthoc v6: add source-explicit typed parenthetical pairing."""
import copy
import cce_posthoc_scoring_v5 as previous
import cce_parenthetical_relation_candidate_v1 as parenthetical
from cce_posthoc_scoring_v5 import (ground,numeric,base,boundary,frozen_fw3,fw4,fw6,
    alias,labels,source_backend,time_scope,target_scope,capture_scoring_calls,source_binding,native)
VERSION='uniform-posthoc-v6-typed-parenthetical-source-pair-development'

def convert(raw,doc,case=None):
    return parenthetical.apply_conversion(previous.convert(raw,doc,case),doc,case)

def score_conversion(case,conversion,step):
    result=previous.score_conversion(case,conversion,step)
    result['processing_version']=VERSION
    captured=previous.previous.previous._CAPTURE.get()
    if captured:
        captured[-1]['parenthetical_relation_candidate']=copy.deepcopy(conversion.get('parenthetical_relation_candidate_v1'))
    return result

def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case)
    return cv,score_conversion(case,cv,step)
