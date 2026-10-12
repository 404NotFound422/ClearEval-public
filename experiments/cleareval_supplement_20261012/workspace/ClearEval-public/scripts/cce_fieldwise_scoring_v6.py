"""Independent posthoc v6: fw5 plus explicit noncore removal/blocking context."""
import copy,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_fieldwise_scoring_v5 as previous
import cce_noncore_time_scope_v3 as noncore_scope
ground,numeric,base=previous.ground,previous.numeric,previous.base
duration_scope=previous.duration_scope
VERSION='fieldwise-scoring-v6-posthoc-noncore-context'

def apply_conversion(conversion,doc,case=None):
 cv=copy.deepcopy(conversion);audit,changes=noncore_scope.derive_audit(cv['source_audit'],doc)
 cv['source_audit']=audit
 cv=previous.apply_conversion(cv,doc,case)
 cv['fieldwise_processing_v6']={'version':VERSION,'noncore_phase_support':changes,'raw_response_modified':False,'original_numeric_formulas_unchanged':True,'posthoc_not_frozen_confirmation':True,'new_model_calls':0}
 return cv
def convert(raw,doc,case=None):return apply_conversion(previous.convert(raw,doc,case),doc,case)
def score_conversion(case,conversion,step):
 result=previous.score_conversion(case,conversion,step);result['processing_version']=VERSION;return result
def evaluate(raw,doc,case,step):
 cv=convert(raw,doc,case);return cv,score_conversion(case,cv,step)
