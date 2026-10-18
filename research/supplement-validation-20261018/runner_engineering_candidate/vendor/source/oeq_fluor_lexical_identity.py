"""Lexical singular/plural class suffix removal only, registry-bound.
Does not infer a spectral model, target assignment, channel or compatibility.
"""
import re
VERSION='registry-bound-class-suffix-v1-20261015'
def lookup_identity(value, registry_keys):
 if not isinstance(value,str):return value,None
 # Identity normalization is deliberately narrower than aliases/synonyms.
 match=re.fullmatch(r'(.+?)\s+(?:dye|dyes|fluorophore|fluorophores)',value.strip(),re.I)
 if not match:return value,None
 base=match.group(1)
 if base not in registry_keys:return value,None
 return base,{'version':VERSION,'source_value':value,'lookup_value':base,
  'rule':'EXACT_REGISTERED_ENTITY_PLUS_GENERIC_CLASS_SUFFIX',
  'specific_model_inferred':False,'channel_inferred':False,
  'meaning':'Same lexical registry entity only; table benchmark lookup is not scientific certification.'}
