"""Source-declared direct-stain roles on the unchanged original scoring formula."""
import copy
import cce_posthoc_scoring_v6 as previous
import cce_posthoc_scoring_v3 as capture_owner
import cce_standalone_fluor_role_v2 as standalone
from cce_posthoc_scoring_v6 import (ground, numeric, base, boundary, frozen_fw3, fw4, fw6,
    alias, labels, source_backend, time_scope, target_scope, capture_scoring_calls,
    source_binding, native, parenthetical)

VERSION = 'uniform-posthoc-v7-source-declared-standalone-fluor-role'


def convert(raw, doc, case=None):
    return standalone.apply_conversion(previous.convert(raw, doc, case), doc, case)


def score_conversion(case, conversion, step):
    doc = ground.document(case['model_response'], ground.source_id_for_case(case))
    cv = standalone.apply_conversion(conversion, doc, case)
    result = previous.score_conversion(case, cv, step)
    result['processing_version'] = VERSION
    result['standalone_fluor_role_v2'] = copy.deepcopy(cv['standalone_fluor_role_v2'])
    captured = capture_owner._CAPTURE.get()
    if captured:
        captured[-1]['standalone_fluor_role'] = copy.deepcopy(cv['standalone_fluor_role_v2'])
    return result


def evaluate(raw, doc, case, step):
    cv = convert(raw, doc, case)
    return cv, score_conversion(case, cv, step)
