"""Keep the original phase policy, with optional/optionally both non-mandatory.

The v1 source and its original replay remain unchanged. This is one explicit
lexical revision, not a reclassification of already frozen confirmation data.
"""
import re,types
from cce_protocol_time_scope_v1 import *
import cce_protocol_time_scope_v1 as previous

VERSION='posthoc-protocol-time-scope-v2-optional-adverb'
OPTIONAL=re.compile(r'\boptional(?:ly)?\b|\bskip\s+if\b',re.I)
_env={**vars(previous),'OPTIONAL':OPTIONAL,'VERSION':VERSION}
first_imaging_ri_support=types.FunctionType(previous.first_imaging_ri_support.__code__,_env,name='first_imaging_ri_support')
_env['first_imaging_ri_support']=first_imaging_ri_support
derive_audit=types.FunctionType(previous.derive_audit.__code__,_env,name='derive_audit')
project=previous.project
