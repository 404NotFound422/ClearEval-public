"""Unchanged component dependency processing with the role-only candidate."""
import types
import cce_posthoc_components_v6 as previous
import cce_posthoc_role_scope_v3 as scoring
from cce_posthoc_components_v6 import original, ground, isolation, label_isolation_source

_process=types.FunctionType(original.independent_processing.__code__,
    {**vars(original),'fw':scoring,'g':ground},name='role_scope_v3_component_base')
independent_processing=types.FunctionType(previous.independent_processing.__code__,
    {**vars(previous),'scoring':scoring,'_process':_process},name='role_scope_v3_components')
