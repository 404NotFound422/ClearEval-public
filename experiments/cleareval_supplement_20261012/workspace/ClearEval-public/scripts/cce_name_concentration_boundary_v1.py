"""Post-hoc boundary adapter: decimal concentration is not a name suffix.

The literal, ordinal, full-boundary checks, raw and frozen converter files remain
unchanged. This module does not change entities, aliases, targets or KB values.
"""
import re
VERSION='name-concentration-boundary-v1-posthoc'
CONCENTRATION=re.compile(r'^\s+(?:\d+(?:\.\d+)?|\.\d+)\s*(?:[%％]|[munpμµ]M\b|(?:micro|milli|nano|pico)?molar\b|(?:mg|ug|μg|µg|ng)\s*/\s*(?:ml|l)\b)',re.I)

def concentration_prefix(trailing):
    match=CONCENTRATION.match(trailing)
    return {'is_explicit_concentration':bool(match),'source_prefix':match.group() if match else None,
      'no_numeric_value_or_name_rewritten':True}

def bind_original(original):
    def omitted_numeric_name_suffix(trailing):
        if concentration_prefix(trailing)['is_explicit_concentration']:return False
        return original(trailing)
    return omitted_numeric_name_suffix
