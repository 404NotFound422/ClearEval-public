"""Posthoc source-occurrence coverage, separated from cosine match quality.

The v1 eligibility graph is unchanged. This is not scientific necessity or
semantic equivalence certification. Canonical/source granularity is unchanged.
"""
from copy import deepcopy
import math
from scipy.optimize import linear_sum_assignment
from oeq_capacity_matching import capacity_metrics, validate_capacity_record

VERSION='identity-role-occurrence-presence-v2-20261015'


def presence_metrics(inventory, similarities, pair, *, provenance,
                     compatibility_exceptions=None):
    previous=capacity_metrics(inventory,similarities,pair,provenance=provenance,
                              compatibility_exceptions=compatibility_exceptions)
    nr,ng=previous['reference_n'],previous['generated_n']
    # Any increase in cardinality dominates the maximum possible total cosine
    # difference (at most min(nr,ng), allowing the pinned float roundoff).
    bonus=(nr+1)*2.0
    weights=[[0.0]*(ng+nr) for _ in range(nr)]
    for e in previous['eligibility_edges']:
        i,j=e['reference_index'],e['generated_index']
        weights[i][j]=bonus+max(0.0,similarities[i][j]) if e['eligible'] else -1.0
    ri,gi=linear_sum_assignment(weights,maximize=True)
    selected={i:j for i,j in zip(ri.tolist(),gi.tolist()) if j<ng and weights[i][j]>0}
    matches=[];gains=[0.0]*ng
    for i,ref in enumerate(inventory['reference_steps']):
        j=selected.get(i);sim=similarities[i][j] if j is not None else None
        if j is not None:gains[j]=max(0.0,sim)
        matches.append({'reference_index':i,'reference_step_id':ref['reference_step_id'],
                        'generated_index':j,'generated_step_id':previous['generated_step_ids'][j] if j is not None else None,
                        'similarity':sim,'presence_credit':int(j is not None),
                        'status':'ELIGIBLE_ASSIGNED' if j is not None else 'UNMATCHED_SOURCE_OCCURRENCE'})
    count=len(selected);out=deepcopy(previous)
    out.update(metric_contract_version=VERSION,matching_contract=VERSION,
               sr=count/nr if nr else 0.0,source_occurrence_coverage=count/nr if nr else 0.0,
               matched_reference_count=count,matches=matches,assigned_candidate_credit=gains,
               assigned_cosine_quality=math.fsum(gains)/count if count else None,
               assigned_cosine_sum=math.fsum(gains),
               objective='LEXICOGRAPHIC_ELIGIBLE_CARDINALITY_THEN_COSINE',
               sr_definition='COMPATIBILITY_ALIAS_ONLY; PRINCIPAL_METRIC_IS_source_occurrence_coverage',
               sr_compatibility_alias_for='source_occurrence_coverage',
               sp_definition='UNCHANGED_V1_ELIGIBLE_CANDIDATE_COSINE_RELEVANCE_MEAN',
               presence_is_not_scientific_necessity=True,
               unresolved_evidence_policy='UNRESOLVED_EDGES_RETAINED; UNMATCHED_IS_NOT_PROVEN_SCIENTIFIC_ABSENCE',
               development_status='POSTHOC_AFTER_V1_INDEPENDENT_RESULTS; NOT_INDEPENDENTLY_CONFIRMED')
    validate_presence_record(out)
    return out


def validate_presence_record(metrics):
    if metrics.get('metric_contract_version')!=VERSION or metrics.get('matching_contract')!=VERSION:
        raise ValueError('Presence matching contract mismatch')
    nr,ng=metrics['reference_n'],metrics['generated_n'];matches=metrics['matches'];used=[]
    if len(matches)!=nr or [r['reference_index'] for r in matches]!=list(range(nr)):
        raise ValueError('Every fixed reference occurrence must be retained')
    eligible={(e['reference_index'],e['generated_index']) for e in metrics['eligibility_edges'] if e['eligible']}
    count=0
    for r in matches:
        i,j=r['reference_index'],r['generated_index']
        if j is None:
            if r['presence_credit']!=0 or r['generated_step_id'] is not None:raise ValueError('Unmatched presence credit')
        else:
            if type(j)is not int or not 0<=j<ng or j in used or (i,j) not in eligible:raise ValueError('Invalid capacity/eligibility')
            if r['presence_credit']!=1 or r['generated_step_id']!=metrics['generated_step_ids'][j]:raise ValueError('Invalid occurrence identity')
            used.append(j);count+=1
    if count!=metrics['matched_reference_count'] or metrics['sr']!=(count/nr if nr else 0):
        raise ValueError('Presence aggregate mismatch')
    if metrics['source_occurrence_coverage']!=metrics['sr']:raise ValueError('Coverage alias mismatch')
    expected=math.fsum(metrics['generated_max_similarity'])/ng if ng else 0
    if not math.isclose(expected,metrics['sp'],abs_tol=1e-12):raise ValueError('Candidate relevance mismatch')
    return deepcopy(metrics)
