"""Bounded posthoc assignment-only candidate. No scientific equivalence certification."""
IMPLEMENTATION_VERSION = 'bounded-quantity-presence-v1-20261018'
import re
import math
import numbers

MAX_REFERENCE_N = 64
MAX_GENERATED_N = 128

def quantity(row):
    """Conservative decimal percent parser; unsupported quantity syntax is unknown."""
    from decimal import Decimal
    text=row.get('operation',row.get('scoring_text','')).lower()
    if text.count('%') != 1:
        return None
    # Do not match a suffix inside an exponent, fraction, signed value or range.
    m=re.search(r'(?<![\w.,/+−–—-])(\d+(?:\.\d+)?|\.\d+)\s*%\s*\(?\s*(vol/vol|v/v|wt/vol|w/v|wt/wt|w/w)(?![\w/])',text)
    if not m:
        return None
    prefix=text[:m.start()]
    if re.search(r'(?:[\d.,]\s*[-−–—/,:+]\s*|(?:\d|%)\s+to\s+|[<>=~≈≤≥±+−–—-]\s*)$',prefix):
        return None
    basis={'vol/vol':'v/v','wt/vol':'w/v','wt/wt':'w/w'}.get(m[2],m[2])
    # Decimal construction and fixed formatting preserve all supplied digits.
    # Avoid Decimal.normalize(), which can round under the active context.
    value=format(Decimal(m[1]),'f')
    if '.' in value:
        value=value.rstrip('0').rstrip('.')
    return (value,basis)

def validate_inputs(old, pair, matrix):
    """Bounded audited fixed-matrix contract. Missing edges mean ineligible."""
    nr, ng = old['reference_n'], old['generated_n']
    if type(nr) is not int or type(ng) is not int or not (0 <= nr <= MAX_REFERENCE_N and 0 <= ng <= MAX_GENERATED_N):
        raise ValueError('graph dimensions outside audited bounds: reference 0..64, generated 0..128')
    refs, gens = pair['reference']['operations'], pair['candidate']['operations']
    if len(refs) != nr or len(gens) != ng:
        raise ValueError('operation counts do not match declared dimensions')
    for rows in (refs, gens):
        ids = [r['id'] for r in rows]
        if any(not isinstance(x, str) or not x for x in ids):
            raise ValueError('operation IDs must be nonempty strings')
        if any(not isinstance(r.get('operation',r.get('scoring_text','')), str) for r in rows):
            raise ValueError('operation text must be a string')
    if len(matrix) != nr or any(len(row) != ng for row in matrix):
        raise ValueError('matrix dimensions do not match operation counts')
    for row in matrix:
        for value in row:
            if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
                raise ValueError('matrix values must be finite real numbers')
            if not -1.000001 <= value <= 1.000001:
                raise ValueError('cosine domain is [-1,1] with 1e-6 roundoff; out-of-domain values are rejected')
    seen = set()
    for edge in old['eligibility_edges']:
        i, j = edge['reference_index'], edge['generated_index']
        if type(i) is not int or type(j) is not int or not (0 <= i < nr and 0 <= j < ng):
            raise ValueError('edge index outside matrix dimensions')
        if (i,j) in seen:
            raise ValueError('duplicate eligibility edge')
        seen.add((i,j))
        if type(edge['eligible']) is not bool:
            raise ValueError('eligible must be boolean')
        if any(not isinstance(edge.get(k), str) or not edge[k] for k in ('reference_identity','generated_identity')):
            raise ValueError('edge identities must be nonempty strings')


def align(old,pair,matrix):
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    validate_inputs(old,pair,matrix)
    nr,ng=old['reference_n'],old['generated_n']
    refs=pair['reference']['operations'];gens=pair['candidate']['operations']
    qref=list(map(quantity,refs));qgen=list(map(quantity,gens))
    # Any one cardinality credit dominates all possible exact-identity credits.
    w=np.zeros((nr,ng+nr),dtype=int);w[:,:ng]=-1000000
    for e in old['eligibility_edges']:
        i,j=e['reference_index'],e['generated_index']
        if e['eligible']:
            exact=qref[i] is not None and qref[i]==qgen[j] and e['reference_identity']==e['generated_identity'] and e['reference_identity']!='unresolved'
            w[i,j]=nr+1+int(exact)
    def solve(force=None):
        a=w.copy()
        if force is not None:
            i,j=force;a[i,:]=-1000000;a[i,j]=w[i,j]
        ri,ci=linear_sum_assignment(a,maximize=True)
        return int(a[ri,ci].sum()),dict(zip(ri.tolist(),ci.tolist()))
    optimum,_=solve()
    possible=[]
    for i in range(nr):
        js=[j for j in range(ng) if w[i,j]>0 and solve((i,j))[0]==optimum]
        absent=solve((i,ng+i))[0]==optimum
        possible.append({'reference_step_id':refs[i]['id'],'possible_generated_indices':js,'can_be_unmatched':absent,'forced_unmatched_within_objective':absent and not js,'localization_ambiguous':absent and bool(js),'assignment_ambiguous':len(js)+int(absent)>1})
    # Preserve integer objective exactly; bounded cosine can only break ties.
    display=w.astype(float)*(2*nr+2)
    for i in range(nr):
        for j in range(ng):
            if w[i,j]>0:display[i,j]+=float(matrix[i][j])
    ri,ci=linear_sum_assignment(display,maximize=True)
    selected={int(i):int(j) for i,j in zip(ri,ci) if j<ng and w[i,j]>0}
    if any(j < ng and w[i,j] <= 0 for i,j in zip(ri,ci)) or int(sum(w[i,j] for i,j in zip(ri,ci))) != optimum:
        raise RuntimeError('display assignment violated the exact primary/secondary optimum')
    return {'status':'POSTHOC_ASSIGNMENT_ONLY_NOT_INDEPENDENT','objective':'MAX_CARDINALITY_THEN_EXPLICIT_QUANTITY_IDENTITY','coverage':len(selected)/nr if nr else 0,'matched_count':len(selected),'representative_matches':selected,'representative_missing':[refs[i]['id'] for i in range(nr) if i not in selected],'possible_states':possible,'scientific_unique_absence_certified':False,'quantity_signatures':{'reference':qref,'candidate':qgen}}
