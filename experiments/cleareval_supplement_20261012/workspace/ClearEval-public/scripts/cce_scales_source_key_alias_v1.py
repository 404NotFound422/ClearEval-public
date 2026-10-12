"""Resolve ScaleS to the explicitly authored combined source key.

The source table and existing build_rag_context.py already identify ScaleS as
SCALE (ScaleS).  This adapter changes lookup identity only; it supplies no
method vector, physical property, duration, or score.  Plain SCALE and other
Scale variants are deliberately not added as aliases.  Use synchronously.
"""
from contextlib import contextmanager
import evaluator_integrity as integrity

VERSION = 'scales-authored-source-key-alias-v1'
SOURCE_KEY = 'SCALE (ScaleS)'
ALIAS = 'ScaleS'


@contextmanager
def source_key_alias():
    original = integrity._SOURCE_KEY_ALIASES
    expanded = dict(original)
    token = integrity.method_token(SOURCE_KEY)
    expanded[token] = tuple(dict.fromkeys((*expanded.get(token, ()), integrity.method_token(ALIAS))))
    integrity._SOURCE_KEY_ALIASES = expanded
    try:
        yield {'version': VERSION, 'source_key': SOURCE_KEY, 'alias': ALIAS,
               'numeric_tables_unchanged': True, 'original_numeric_functions_unchanged': True}
    finally:
        integrity._SOURCE_KEY_ALIASES = original


def score_with_alias(score_function, case, conversion, step):
    with source_key_alias() as evidence:
        result = score_function(case, conversion, step)
    result['method_source_key_alias'] = evidence
    return result
