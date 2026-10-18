"""Opt-in occurrence-capacity matching of a selected reported-source route.

No reference changes, new encoder calls, parameter equality tests, or claims of
scientific necessity. Unknown identities remain explicit, not inferred synonyms.
This contract is deliberately distinct from archived independent cosine maxima.
"""
from copy import deepcopy
import math
import re
from oeq_atomic_alignment import annotate, eligibility, composition
from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import metrics_from_matrix

IMPLEMENTATION_VERSION = 'bounded-source-identity-v2-exact-operation-20261018'
VERSION = 'identity-role-capacity-v1-20261015'
UNKNOWN = 'unresolved'


def identity(row):
    text = row.get('operation', row.get('scoring_text', '')).lower()
    text = re.sub('[‐‑‒–—−]', '-', text)
    # Named formulations are entities, not concentrations or numeric parameters.
    formulations = set(re.findall(r'\bmacs\s*-\s*r\s*([012])\b', text))
    if len(formulations) == 1:
        return 'macs-r' + next(iter(formulations))
    if len(formulations) > 1:
        return UNKNOWN
    return composition(dict(row, operation=text))


def literal_operation_text(row):
    """Literal original source row, excluding only its structural number/whitespace.

    Do not casefold, NFKC, remove parameters, negate, translate, or infer chemistry.
    Virtual occurrence slots retain raw_text of their original numbered source row.
    """
    text = row.get('raw_text', row.get('operation', ''))
    text = re.sub(r'^\s*\d+(?:\.\d+)*[.)、]?\s+', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def identity_relation(reference, candidate):
    """Identity/operation evidence only; independent role, stage, modality gates remain."""
    ai, bi = identity(reference), identity(candidate)
    result = {'reference_identity': ai, 'generated_identity': bi,
              'chemical_identity_status': 'UNRESOLVED' if UNKNOWN in (ai, bi) else 'RESOLVED_EXISTING_VOCABULARY'}
    if ai != UNKNOWN and bi != UNKNOWN:
        return dict(result, status='CONFIRMED' if ai == bi else 'CONFLICT',
                    basis='EXISTING_REAGENT_IDENTITY_OR_ALIAS',
                    reason='same_existing_identity' if ai == bi else 'explicit_reagent_identity_conflict')
    if ai == bi == UNKNOWN:
        a, b = literal_operation_text(reference), literal_operation_text(candidate)
        if a and a == b:
            return dict(result, status='CONFIRMED', basis='EXACT_OPERATION_TEXT',
                        reason='same_literal_operation_without_chemical_identification')
    return dict(result, status='UNRESOLVED', basis='INSUFFICIENT_IDENTITY_OR_LITERAL_OPERATION_EVIDENCE',
                reason='identity_evidence_unresolved')


def _rows(rows):
    """Use frozen role annotations; infer only absent annotations for old routes."""
    inferred = annotate(rows)
    out = []
    for old, new in zip(rows, inferred):
        new.update(old)
        new['matching_identity'] = identity(new)
        out.append(new)
    return out


def _exception_map(exceptions, inventory, refs, gens):
    result = {}
    for e in exceptions or []:
        if e.get('reference_id') != inventory['reference_id'] or e.get('route_id') != inventory['route_id']:
            raise ValueError('Compatibility evidence must bind selected route and reference')
        if not e.get('evidence_locator') or not e.get('rationale'):
            raise ValueError('Compatibility exception requires inspectable evidence and rationale')
        key = (e.get('reference_step_id'), e.get('generated_step_id'))
        if key[0] not in {r['id'] for r in refs} or key[1] not in {g['id'] for g in gens}:
            raise ValueError('Compatibility exception must bind actual operation IDs')
        if key in result:
            raise ValueError('Duplicate compatibility exception')
        result[key] = deepcopy(e)
    return result


def capacity_metrics(inventory, similarities, pair, *, provenance,
                     compatibility_exceptions=None, identity_role_guards=True):
    from scipy.optimize import linear_sum_assignment
    refs, gens = _rows(pair['reference']['operations']), _rows(pair['candidate']['operations'])
    archived = metrics_from_matrix(inventory, similarities, [g['id'] for g in gens], provenance=provenance)
    if [r['id'] for r in refs] != [r['reference_step_id'] for r in inventory['reference_steps']]:
        raise ValueError('Reference row order differs from frozen inventory')
    if [r['scoring_text'] for r in refs] != [r['text'] for r in inventory['reference_steps']]:
        raise ValueError('Reference text differs from frozen inventory')
    # One explicitly atomized occurrence supplies at most one reference occurrence.
    # Extra dummy columns leave unsupported rows unmatched, with zero credit.
    nr, ng = len(refs), len(gens)
    exceptions = _exception_map(compatibility_exceptions, inventory, refs, gens)
    weights = [[0.0] * (ng + nr) for _ in refs]
    edges, unknown = [], []
    for i, a in enumerate(refs):
        for j, b in enumerate(gens):
            reasons = eligibility(a, b)['reasons'] if identity_role_guards else []
            ai, bi = a['matching_identity'], b['matching_identity']
            relation = identity_relation(a, b)
            if identity_role_guards and relation['status'] != 'CONFIRMED':
                reasons.append(relation['reason'])
                if relation['status'] == 'UNRESOLVED':
                    unknown.append({'reference_index': i, 'generated_index': j, **relation})
            exception = exceptions.get((a['id'], b['id']))
            if exception:
                reasons = [r for r in reasons if r not in {'explicit_reagent_identity_conflict', 'identity_evidence_unresolved', 'role_conflict', 'pure_mixed_solvent_conflict'}]
            if reasons:
                weights[i][j] = -1.0
            else:
                weights[i][j] = max(0.0, similarities[i][j])
            edges.append({'reference_index': i, 'generated_index': j, 'eligible': not reasons,
                          'reasons': reasons, 'reference_identity': ai, 'generated_identity': bi,
                          'identity_relation': relation, 'compatibility_evidence': exception})
    ri, gi = linear_sum_assignment(weights, maximize=True)
    matches = []
    selected = {}
    for i, j in zip(ri.tolist(), gi.tolist()):
        if j < ng and weights[i][j] > 0:
            selected[i] = j
    gains = [0.0] * ng
    for i, ref in enumerate(refs):
        j = selected.get(i)
        value = max(0.0, similarities[i][j]) if j is not None else 0.0
        if j is not None:
            gains[j] = value
        matches.append({'reference_index': i, 'reference_step_id': ref['id'],
                        'generated_index': j, 'generated_step_id': gens[j]['id'] if j is not None else None,
                        'similarity': value, 'status': 'ASSIGNED' if j is not None else 'UNMATCHED'})
    total = math.fsum(gains)
    relevance = [max(0.0, max(weights[i][j] for i in range(nr))) for j in range(ng)] if nr else [0.0]*ng
    out = deepcopy(archived)
    out.update(sr=total/nr if nr else 0.0, sp=math.fsum(relevance)/ng if ng else 0.0,
               matches=matches, generated_max_similarity=relevance, assigned_candidate_credit=gains,
               precision_policy="ELIGIBLE_COLUMN_MAXIMA_EXTRA_VALID_OCCURRENCES_NOT_ZEROED",
               metric_contract_version=VERSION, matching_contract=VERSION,
               capacity_policy='ONE_PER_EXPLICIT_ATOMIC_OCCURRENCE',
               unmatched_credit=0.0, negative_cosine_policy='ZERO_OPTION_BEATS_NEGATIVE_EDGE',
               guard_mode='identity_role_capacity' if identity_role_guards else 'capacity_only',
               eligibility_edges=edges, unresolved_identity_edges=unknown,
               interpretation='REPORTED_SOURCE_OCCURRENCE_ALIGNMENT_NOT_SCIENTIFIC_NECESSITY',
               compatible_substitution_policy='EXPLICIT_BOUND_EVIDENCE_EXCEPTION',
               reference_denominator_unchanged=True)
    return out


def validate_capacity_record(metrics):
    """Schema/capacity consistency only; callers replay text/matrix for provenance."""
    if metrics.get('matching_contract') != VERSION or metrics.get('metric_contract_version') != VERSION:
        raise ValueError('Capacity contract mismatch')
    nr, ng = metrics['reference_n'], metrics['generated_n']
    matches = metrics['matches']
    if len(matches) != nr or [r['reference_index'] for r in matches] != list(range(nr)):
        raise ValueError('Capacity result must retain every reference row in order')
    used = []; total = 0.0
    for row in matches:
        j, val = row['generated_index'], row['similarity']
        if j is None:
            if val != 0 or row['generated_step_id'] is not None:
                raise ValueError('Unmatched occurrence has nonzero credit')
        else:
            if type(j) is not int or not 0 <= j < ng or j in used:
                raise ValueError('Generated occurrence capacity exceeded')
            if metrics['generated_step_ids'][j] != row['generated_step_id'] or not 0 < val <= 1.000001:
                raise ValueError('Invalid matched occurrence')
            used.append(j)
        total += val
    for field, expected in [('sr', total/nr if nr else 0), ('sp', math.fsum(metrics['generated_max_similarity'])/ng if ng else 0)]:
        if not math.isclose(metrics[field], expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('Capacity aggregate mismatch')
    return deepcopy(metrics)
