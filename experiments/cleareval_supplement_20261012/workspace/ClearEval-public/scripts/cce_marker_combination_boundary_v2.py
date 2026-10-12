"""Use one source name boundary consistently, without changing pair policy.

Version 1 and its actual replay remain retained. This revision rebinds only
the existing complete-name helpers' dependencies; their code is unchanged.
"""
import types
from cce_marker_combination_boundary_v1 import *
import cce_marker_combination_boundary_v1 as first

ADAPTER_VERSION='source-declared-marker-combination-boundary-posthoc-v2'
_environment={**vars(namespace),'plus_boundary_audit':plus_boundary_audit}
_functions=['name_occurrence_inventory','bind_literal_name','local_name_mentions',
            'relation_clause_support','exact_identity_mention_coverage','intrinsic_policy',
            '_endpoint_occurrence_audit','_audit_expanded_payload','audit_payload','_convert_namespace']
for _name in _functions:
    _old=getattr(namespace,_name)
    _new=types.FunctionType(_old.__code__,_environment,name=_name,argdefs=_old.__defaults__,closure=_old.__closure__)
    _new.__kwdefaults__=_old.__kwdefaults__
    _environment[_name]=_new
    globals()[_name]=_new

_convert=_environment['_convert_namespace']
convert=types.FunctionType(first.convert.__code__,
    {**vars(first),'_convert':_convert,'ADAPTER_VERSION':ADAPTER_VERSION},name='convert')

# Exact original semantic predicates and selected-clause equality are retained.
relation_policy=namespace.relation_policy
_selected_clause_endpoint_audit=namespace._selected_clause_endpoint_audit
