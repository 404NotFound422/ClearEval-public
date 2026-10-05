"""Repeat diagnostics retain planned denominators and unknown coverage."""
import math
from collections import Counter
from itertools import combinations
from .io import digest

STATES = ('SATISFIED', 'VIOLATED', 'UNDER_SPECIFIED', 'UNRESOLVED')


def entropy(values):
    if not values:
        return None
    counts = Counter(values)
    return -sum((n / len(values)) * math.log2(n / len(values)) for n in counts.values())


def requirement_metrics(vectors, requirement_ids, planned):
    result = []
    for key in requirement_ids:
        observed = [vector.get(key) for vector in vectors if vector.get(key) in STATES]
        decisive = [value for value in observed if value in STATES[:2]]
        pairs = list(combinations(observed, 2))
        result.append({'id': key, 'planned_repeats': planned, 'observed_count': len(observed),
            'decisive_count': len(decisive),
            'decisive_coverage': len(decisive) / planned if planned else None,
            'all_state_entropy_bits': entropy(observed),
            'decisive_entropy_bits': entropy(decisive),
            'pairwise_flip_rate': sum(a != b for a, b in pairs) / len(pairs) if pairs else None,
            'independent_error_risk': None,
            'risk_reason': 'Independent reference labels are not part of repeat diagnostics'})
    return result


def group_metrics(records, requirements, planned):
    independent = [r for r in records if r.get('origin') in ('OLLAMA_ACTUAL', 'EXTERNAL_ACTUAL')
                   and r.get('technical_status') == 'COMPLETE']
    parsed_attempts = [r for r in records if r.get('origin') in ('OLLAMA_ACTUAL', 'EXTERNAL_ACTUAL')
              and (r.get('parsed_judge_vector_status') == 'COMPLETE' or r.get('technical_status') == 'COMPLETE')]
    latest = {}
    for row in parsed_attempts:
        latest[row.get('id', row['invocation_id'])] = row
    parsed = list(latest.values())
    raw = [r['proposed_vector'] for r in parsed]
    effective = [r['effective_vector'] for r in independent]
    digests = {r.get('actual_revision') for r in independent}
    ids = {r['invocation_id'] for r in independent}
    return {'planned_trials': planned, 'attempts': len(records),
        'independent_complete': len(independent),
        'technical_coverage': len(independent) / planned if planned else None,
        'independent_parsed_judge_vectors': len(parsed),
        'parsed_judge_vector_attempts': len(parsed_attempts),
        'parsed_judge_vector_coverage': len(parsed) / planned if planned else None,
        'parsed_vector_scope': 'MODEL_PROPOSALS_ONLY_NOT_VERIFIED_EFFECTIVE_STATES',
        'failed_attempts': sum(r.get('technical_status') == 'FAILED' for r in records),
        'cache_or_fake_count': sum(r.get('origin') not in ('OLLAMA_ACTUAL', 'EXTERNAL_ACTUAL') for r in records),
        'distinct_independent_invocations': len(ids),
        'version_stability_verifiable': len(digests) == 1 and None not in digests and 'UNKNOWN' not in digests,
        'minimum_three_independent_complete': len(independent) >= 3 and len(ids) == len(independent),
        'proposed': requirement_metrics(raw, requirements, planned),
        'effective': requirement_metrics(effective, requirements, planned),
        'structure': structure_metrics(independent, records, planned),
        'scientific_accuracy': None}


def structure_metrics(independent, all_records, planned):
    fields = sorted({key for record in all_records for key in record.get('structure_vector', {})})
    result = []
    for field in fields:
        cells = [r.get('structure_vector', {}).get(field, {'present': False, 'value': None}) for r in independent]
        values = [digest(cell['value']) for cell in cells if cell.get('present') and cell.get('value') is not None]
        pairs = list(combinations(values, 2))
        result.append({'field': field, 'planned_repeats': planned, 'non_null_observed': len(values),
            'observed_coverage': len(values) / planned if planned else None,
            'exact_value_entropy_bits': entropy(values),
            'exact_value_flip_rate': sum(a != b for a, b in pairs) / len(pairs) if pairs else None,
            'interpretation': 'Typed JSON value reproducibility only; no correctness/reference claim'})
    return result
