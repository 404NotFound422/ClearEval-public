"""Compressed occurrence matching and credit accounting without repeat expansion."""
import numpy as np
from scipy.optimize import linprog, milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix, vstack, csr_matrix


def capacities(value):
    a=np.asarray(value,dtype=float)
    if a.ndim!=1 or np.any(~np.isfinite(a)) or np.any(a<0) or np.any(a!=np.rint(a)):
        raise ValueError('Capacities must be known nonnegative integer occurrence counts')
    return a.astype(np.int64)


def align(scores,reference_capacity,candidate_capacity,threshold=0.,*,preference=None):
    scores=np.asarray(scores,dtype=float);r=capacities(reference_capacity);c=capacities(candidate_capacity)
    if scores.shape!=(len(r),len(c)) or np.any(~np.isfinite(scores)):
        raise ValueError('Invalid finite score matrix')
    n,m=scores.shape
    if n==0 or m==0:return np.zeros((n,m),dtype=np.int64)
    constraints=lil_matrix((n+m,n*m),dtype=float)
    for i in range(n):constraints[i,i*m:(i+1)*m]=1
    for j in range(m):constraints[n+j,j::m]=1
    bounds=[(0,None) if v>threshold else (0,0) for v in scores.ravel()]
    solved=linprog(-(scores-threshold).ravel(),A_ub=constraints.tocsr(),b_ub=np.concatenate([r,c]),bounds=bounds,method='highs')
    if not solved.success:raise RuntimeError('Capacity matching solver failed')
    # The bipartite capacity matrix is totally unimodular for integer supplies.
    rounded=np.rint(solved.x)
    if np.max(np.abs(rounded-solved.x),initial=0)>1e-7:raise RuntimeError('Nonintegral matching')
    flow=rounded.astype(np.int64).reshape(n,m)
    assert np.all(flow.sum(1)<=r) and np.all(flow.sum(0)<=c)
    if flow.sum() and (n*m>1):
        # Lexicographic optimization: correspondence quality is fixed first.
        # A squared positional cost breaks ties between interchangeable rows;
        # it does not prohibit real crossings between distinct operations.
        quality=(scores-threshold).ravel()
        optimum=float(quality@flow.ravel())
        position=np.array([(i/max(n-1,1)-j/max(m-1,1))**2 for i in range(n) for j in range(m)])
        matrix=vstack([constraints.tocsr(),csr_matrix(quality.reshape(1,-1))]).tocsc()
        upper=np.concatenate([r,c,[np.inf]])
        lower=np.concatenate([np.full(n+m,-np.inf),[optimum-1e-10]])
        limits=Bounds(np.zeros(n*m),np.where(scores.ravel()>threshold,np.inf,0.))
        if preference is not None:
            preference=np.asarray(preference)
            if preference.shape!=scores.shape or not set(preference.ravel())<={0,1,2}:raise ValueError('Invalid evidence preference')
            evidence_cost=np.where(preference.ravel()==2,float(min(r.sum(),c.sum())+1),preference.ravel()).astype(float)
            evidence=milp(evidence_cost,integrality=np.ones(n*m),bounds=limits,
                          constraints=LinearConstraint(matrix,lower,upper),options={'mip_rel_gap':0.})
            if not evidence.success:raise RuntimeError('Evidence tie resolution failed')
            evidence_flow=np.rint(evidence.x).astype(np.int64)
            if np.max(np.abs(evidence.x-evidence_flow),initial=0)>1e-7:raise RuntimeError('Nonintegral evidence matching')
            if float(quality@evidence_flow)>=optimum-1e-9:
                cost=float(evidence_cost@evidence_flow)
                matrix=vstack([matrix,csr_matrix(evidence_cost.reshape(1,-1))]).tocsc()
                lower=np.append(lower,cost);upper=np.append(upper,cost)
                flow=evidence_flow.reshape(n,m)
        tie=milp(position,integrality=np.ones(n*m),bounds=Bounds(np.zeros(n*m),np.where(scores.ravel()>threshold,np.inf,0.)),
                 constraints=LinearConstraint(matrix,lower,upper),options={'mip_rel_gap':0.})
        if not tie.success:raise RuntimeError('Secondary capacity matching solver failed')
        selected=np.rint(tie.x).astype(np.int64).reshape(n,m)
        if np.max(np.abs(tie.x-selected.ravel()),initial=0)>1e-7:raise RuntimeError('Nonintegral secondary matching')
        # Never trade away a genuinely distinct operation score for proximity.
        if float(quality@selected.ravel())>=optimum-1e-9:flow=selected
        assert np.all(flow.sum(1)<=r) and np.all(flow.sum(0)<=c)
    return flow


def aggregate(flow,identity,verification,reference_capacity,candidate_capacity):
    flow=np.asarray(flow);identity=np.asarray(identity);verification=np.asarray(verification)
    r=capacities(reference_capacity);c=capacities(candidate_capacity)
    if flow.shape!=(len(r),len(c)) or flow.shape!=identity.shape or flow.shape!=verification.shape:
        raise ValueError('Shape mismatch')
    if np.any(flow<0) or np.any(flow!=np.rint(flow)) or np.any(flow.sum(1)>r) or np.any(flow.sum(0)>c):
        raise ValueError('Reused or invalid occurrence capacity')
    statuses={'PASS','FAIL','UNKNOWN'}
    if not set(identity.ravel())<=statuses or not set(verification.ravel())<=statuses:raise ValueError('Invalid status')
    identity_count=int(flow[identity=='PASS'].sum())
    verified_count=int(flow[(identity=='PASS')&(verification=='PASS')].sum())
    unknown_count=int(flow[(identity!='FAIL')&(verification!='FAIL')&((identity=='UNKNOWN')|(verification=='UNKNOWN'))].sum())
    ratio=lambda n,d:float(n/d) if d else None
    return {'N_R':int(r.sum()),'N_C':int(c.sum()),'identity_credit':identity_count,'verified_credit':verified_count,'unknown_aligned':unknown_count,
            'operation_SR':ratio(identity_count,r.sum()),'operation_SP':ratio(identity_count,c.sum()),
            'verified_Bio_SR':ratio(verified_count,r.sum()),'verified_Bio_SP':ratio(verified_count,c.sum()),
            'conditional_SR_upper':ratio(verified_count+unknown_count,r.sum()),'conditional_SP_upper':ratio(verified_count+unknown_count,c.sum())}


def self_check():
    # Equivalent descriptions: one row repeated three times vs three singleton rows.
    grouped=align([[.9]],[3],[3],.5)
    split=align([[.9],[.9],[.9]],[1,1,1],[3],.5)
    first=aggregate(grouped,[['PASS']],[['PASS']],[3],[3])
    second=aggregate(split,[['PASS'],['PASS'],['PASS']],[['PASS'],['PASS'],['PASS']],[1,1,1],[3])
    assert first==second and first['verified_credit']==3
    scarce=align([[.9],[.9],[.9]],[1,1,1],[1],.5)
    assert scarce.sum()==1
    wrong=aggregate([[1]],[['PASS']],[['FAIL']],[1],[1])
    unknown=aggregate([[1]],[['PASS']],[['UNKNOWN']],[1],[1])
    assert wrong['identity_credit']==1 and wrong['verified_credit']==0 and unknown['verified_credit']==0
    assert unknown['conditional_SR_upper']==1 and wrong['conditional_SR_upper']==0
    huge=align([[.9]],[1000000],[1000000],.5)
    assert huge.shape==(1,1) and int(huge[0,0])==1000000
    tied=align([[.9,.9],[.9,.9]],[2,1],[1,2],.5)
    assert tied.sum()==3
    rejected=False
    try:aggregate([[2]],[['PASS']],[['PASS']],[1],[1])
    except ValueError:rejected=True
    assert rejected
    return {'split_merge_invariance':True,'candidate_capacity_conserved':True,'failed_or_unknown_not_credited':True,
            'million_repeats_without_expansion':True,'integer_tied_transport':True,'duplicate_credit_rejected':True,
            'grouped_example':first,'wrong_parameter_example':wrong,'unknown_parameter_example':unknown}


if __name__=='__main__':
    import json
    print(json.dumps(self_check()))
