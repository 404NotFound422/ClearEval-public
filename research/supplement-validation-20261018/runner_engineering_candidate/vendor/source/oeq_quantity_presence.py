"""Explicit bounded quantity-identity assignment consumed by existing arithmetic.

The audited assignment implementation is reused unchanged. No eligibility edge,
coverage definition, SP policy, score formula, or default route is changed.
"""
from copy import deepcopy
import math
from oeq_presence_matching import presence_metrics, validate_presence_record, VERSION as OLD_VERSION
from oeq_quantity_assignment import align

VERSION = 'identity-role-occurrence-quantity-presence-v3-20261016'


def quantity_presence_metrics(inventory, similarities, pair, *, provenance,
                              compatibility_exceptions=None):
    previous = presence_metrics(inventory, similarities, pair, provenance=provenance,
                                compatibility_exceptions=compatibility_exceptions)
    assignment = align(previous, pair, similarities)
    selected = assignment['representative_matches']
    matches, gains = [], [0.0] * previous['generated_n']
    for i, ref in enumerate(inventory['reference_steps']):
        j = selected.get(i)
        sim = similarities[i][j] if j is not None else None
        if j is not None:
            gains[j] = sim
        matches.append({'reference_index': i, 'reference_step_id': ref['reference_step_id'],
                        'generated_index': j,
                        'generated_step_id': previous['generated_step_ids'][j] if j is not None else None,
                        'similarity': sim, 'presence_credit': int(j is not None),
                        'status': 'ELIGIBLE_ASSIGNED' if j is not None else 'UNMATCHED_SOURCE_OCCURRENCE'})
    count = len(selected)
    if count != previous['matched_reference_count']:
        raise RuntimeError('Quantity tie-break changed the maximal presence cardinality')
    out = deepcopy(previous)
    out.update(metric_contract_version=VERSION, matching_contract=VERSION,
               matches=matches, assigned_candidate_credit=gains,
               assigned_cosine_quality=math.fsum(gains)/count if count else None,
               assigned_cosine_sum=math.fsum(gains),
               objective=assignment['objective'], quantity_assignment=assignment,
               localization_policy='ALL_PRIMARY_SECONDARY_OPTIMA; COSINE_SELECTS_DISPLAY_ONLY',
               scientific_unique_absence_certified=False,
               development_status='OPT_IN_FIXED_INPUT_CONSUMER_INTEGRATION; NOT_END_TO_END_VALIDATION')
    validate_quantity_presence_record(out)
    return out


def validate_quantity_presence_record(metrics):
    if metrics.get('metric_contract_version') != VERSION or metrics.get('matching_contract') != VERSION:
        raise ValueError('Quantity presence matching contract mismatch')
    legacy_shape = deepcopy(metrics)
    legacy_shape.update(metric_contract_version=OLD_VERSION, matching_contract=OLD_VERSION)
    validate_presence_record(legacy_shape)
    assignment = metrics['quantity_assignment']
    if assignment['coverage'] != metrics['source_occurrence_coverage'] or assignment['matched_count'] != metrics['matched_reference_count']:
        raise ValueError('Quantity assignment coverage differs from consumed metrics')
    if assignment.get('scientific_unique_absence_certified') is not False or metrics.get('scientific_unique_absence_certified') is not False:
        raise ValueError('Quantity assignment cannot certify scientific absence')
    selected = {int(i): j for i, j in assignment['representative_matches'].items()}
    expected = {r['reference_index']: r['generated_index'] for r in metrics['matches'] if r['generated_index'] is not None}
    if selected != expected:
        raise ValueError('Displayed assignment differs from consumed metrics')
    states = assignment['possible_states']
    if [s['reference_step_id'] for s in states] != [r['reference_step_id'] for r in metrics['matches']]:
        raise ValueError('Every reference occurrence must retain its possible states')
    missing = [r['reference_step_id'] for r in metrics['matches'] if r['generated_index'] is None]
    if assignment['representative_missing'] != missing:
        raise ValueError('Representative missing identities disagree')
    for row, state in zip(metrics['matches'], states):
        js, absent = state['possible_generated_indices'], state['can_be_unmatched']
        if any(type(j) is not int or not 0 <= j < metrics['generated_n'] for j in js) or len(set(js)) != len(js) or type(absent) is not bool:
            raise ValueError('Invalid possible assignment states')
        if row['generated_index'] is None and not absent or row['generated_index'] is not None and row['generated_index'] not in js:
            raise ValueError('Displayed assignment is outside possible states')
        for field, value in [('forced_unmatched_within_objective', absent and not js),
                             ('localization_ambiguous', absent and bool(js)),
                             ('assignment_ambiguous', len(js) + int(absent) > 1)]:
            if state[field] != value:
                raise ValueError('Inconsistent assignment ambiguity flag')
    return deepcopy(metrics)
