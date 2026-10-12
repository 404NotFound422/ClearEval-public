"""Versioned lexical candidate for Han adjacency and explicit concentration ranges.

Exact model literals, source units and original occurrence ordinals are retained.
This locates text; it does not assign a reagent's biological role or relationship.
"""
import copy
import re
import types
from contextlib import contextmanager
import cce_posthoc_source_backend_v3 as backend

VERSION='multilingual-name-boundary-v1'
NUMBER=r'(?:\d+(?:\.\d+)?|\.\d+)'
CONCENTRATION=re.compile(r'^\s+'+NUMBER+r'(?:\s*[-–—~至]\s*'+NUMBER+r')?\s*'
    r'(?:[%％]|[munpμµ]M(?![A-Za-z0-9_])|(?:micro|milli|nano|pico)?molar\b|'
    r'(?:mg|ug|μg|µg|ng)\s*/\s*(?:ml|l)(?![A-Za-z0-9_]))',re.I)
ORIGINAL=backend.name_occurrence_inventory


def han(character):
    return bool(character) and ('\u3400'<=character<='\u9fff' or '\U00020000'<=character<='\U0003134f')


def name_occurrence_inventory(literal,support,doc):
    inventory=copy.deepcopy(ORIGINAL(literal,support,doc))
    # Archived ordinals were declared against the old complete-name inventory.
    # Preserve every successful binding; do not renumber its earlier mentions.
    if inventory['complete_occurrences']:
        return inventory
    original_inventory=copy.deepcopy(inventory)
    changes=[];hits=[];rejected=[]
    for match in inventory['all_exact_occurrences']:
        start,end=match['start'],match['end'];reasons=list(match['reasons']);removed=[]
        before=doc['text'][start-1] if start else ''
        after=doc['text'][end:end+1]
        if ('CLIPPED_NAME_START' in reasons and han(before) and before!='抗'
                and re.fullmatch(r'[A-Za-z0-9]',literal[0])):
            reasons.remove('CLIPPED_NAME_START');removed.append('Han_prose_adjacent_to_Latin_name_start')
        if ('CLIPPED_NAME_END' in reasons and han(after)
                and re.fullmatch(r'[A-Za-z0-9]',literal[-1])):
            reasons.remove('CLIPPED_NAME_END');removed.append('Han_prose_adjacent_to_Latin_name_end')
        concentration=CONCENTRATION.match(doc['text'][end:support['context_end']])
        if 'OMITTED_DISTINGUISHING_NUMERIC_SUFFIX' in reasons and concentration:
            reasons.remove('OMITTED_DISTINGUISHING_NUMERIC_SUFFIX');removed.append('explicit_concentration_with_unit')
        if removed:
            changes.append({'start':start,'end':end,'quote':match['quote'],'original_reasons':match['reasons'],
                'resolved_reasons':removed,'remaining_reasons':reasons,
                'source_concentration':concentration.group() if concentration else None})
        match.update(reasons=reasons,boundary_accepted=not reasons,
                     complete_name_ordinal=None if reasons else len(hits))
        (rejected if reasons else hits).append(copy.deepcopy(match))
    if len(hits)!=1:
        return original_inventory
    inventory.update(complete_occurrences=hits,rejected_substring_occurrences=rejected,
        complete_occurrence_count=len(hits),index_basis='complete_literal_occurrences_after_'+VERSION,
        boundary_rules_relaxed=bool(changes),lexical_changes=changes,
        literal_and_raw_ordinal_unchanged=True,relationship_pairing_not_inferred=True)
    return inventory


@contextmanager
def use_candidate():
    """Temporarily bind the same predicate in every existing cloned helper.

    Offline sequential use only. The original modules on disk remain untouched.
    """
    environments={id(backend._environment):backend._environment}
    for value in vars(backend).values():
        if isinstance(value,types.FunctionType):environments[id(value.__globals__)]=value.__globals__
    changed=[]
    for environment in environments.values():
        if environment.get('name_occurrence_inventory') is ORIGINAL:
            environment['name_occurrence_inventory']=name_occurrence_inventory;changed.append(environment)
    previous_attribute=backend.name_occurrence_inventory
    backend.name_occurrence_inventory=name_occurrence_inventory
    try:
        yield {'version':VERSION,'rebound_environments':len(changed)}
    finally:
        for environment in changed:environment['name_occurrence_inventory']=ORIGINAL
        backend.name_occurrence_inventory=previous_attribute
