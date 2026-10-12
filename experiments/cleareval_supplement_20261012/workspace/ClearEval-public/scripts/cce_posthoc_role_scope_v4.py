"""Source-role v4 candidate using the unchanged numeric formula from v6.

Both entry points avoid the v7 adapter, which would reapply role v2 after v4.
Original raw/doc inputs are required for a previously role-modified projection.
"""
import copy
import cce_posthoc_scoring_v6 as previous
import cce_posthoc_scoring_v3 as capture_owner
import cce_standalone_fluor_role_v4 as standalone
from cce_posthoc_scoring_v6 import (ground, numeric, base, boundary, frozen_fw3, fw4, fw6,
    alias, labels, source_backend, time_scope, target_scope, capture_scoring_calls,
    source_binding, native, parenthetical)

VERSION = 'secondary-source-local-role-v4-original-numeric-formula'


def convert(raw, doc, case=None):
    return standalone.apply_conversion(previous.convert(raw, doc, case), doc, case)


def score_conversion(case, conversion, step):
    doc = ground.document(case['model_response'], ground.source_id_for_case(case))
    cv = standalone.apply_conversion(conversion, doc, case)
    result = previous.score_conversion(case, cv, step)
    result['processing_version'] = VERSION
    result[standalone.KEY] = copy.deepcopy(cv[standalone.KEY])
    captured = capture_owner._CAPTURE.get()
    if captured:
        captured[-1][standalone.KEY] = copy.deepcopy(cv[standalone.KEY])
        captured[-1]['role_scope_v4_projection'] = copy.deepcopy(cv['label_occurrence_projection'])
    return result


def evaluate(raw, doc, case, step):
    cv = convert(raw, doc, case)
    return cv, score_conversion(case, cv, step)
