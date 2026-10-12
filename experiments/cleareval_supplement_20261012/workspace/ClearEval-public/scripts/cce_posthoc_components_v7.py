"""Reuse tested per-component processing with the source-role v7 adapter."""
import types
import cce_posthoc_components_v6 as previous
import cce_posthoc_scoring_v7 as scoring
from cce_posthoc_components_v6 import original, ground, isolation, label_isolation_source

_process = types.FunctionType(original.independent_processing.__code__,
    {**vars(original), 'fw': scoring, 'g': ground}, name='independent_processing_v7_base')
independent_processing = types.FunctionType(previous.independent_processing.__code__,
    {**vars(previous), 'scoring': scoring, '_process': _process}, name='independent_processing_v7')
