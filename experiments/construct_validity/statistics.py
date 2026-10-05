"""Denominators and grouped uncertainty; development controls are not gold."""
from collections import Counter, defaultdict
import math
import random

def ratio(a,b):
    return a/b if b else None

def entropy(values):
    n=len(values)
    return -sum((c/n)*math.log2(c/n) for c in Counter(values).values()) if n else None

def risk_counts(rows):
    decisive={"SATISFIED","VIOLATED"}
    negatives=[r for r in rows if r.get("reference")=="VIOLATED"]
    positives=[r for r in rows if r.get("reference")=="SATISFIED"]
    accepted=[r for r in rows if r.get("prediction")=="SATISFIED" and r.get("reference") in decisive]
    counts={
        "false_accept":(sum(r.get("prediction")=="SATISFIED" for r in negatives),len(negatives)),
        "false_reject":(sum(r.get("prediction")=="VIOLATED" for r in positives),len(positives)),
        "accepted_risk":(sum(r["reference"]=="VIOLATED" for r in accepted),len(accepted)),
        "decisive_coverage":(sum(r.get("prediction") in decisive for r in rows),len(rows)),
        "technical_failure":(sum(r.get("prediction") is None for r in rows),len(rows))}
    return {k:{"numerator":a,"denominator":b,"value":ratio(a,b)} for k,(a,b) in counts.items()}

def percentile(values,q):
    values=sorted(values)
    if not values: return None
    pos=(len(values)-1)*q
    i=int(pos)
    f=pos-i
    return values[i]*(1-f)+values[min(i+1,len(values)-1)]*f

def paired_cluster_interval(rows,*,independent_reference=False,grouped_holdout=False,resamples=5000,seed=20260929):
    """Equal-source-group paired B-A mean; 10 groups is a reporting rule, not power assurance."""
    if not independent_reference or not grouped_holdout:
        return {"status":"NOT_ESTIMABLE","reason":"Independent reference / grouped holdout absent","estimate":None,"low":None,"high":None}
    grouped,seen=defaultdict(list),set()
    for row in rows:
        if not row.get("source_group") or not row.get("pair_id"): raise ValueError("Missing group or pair")
        if row["pair_id"] in seen: raise ValueError("Repeated judgments are not independent pairs")
        seen.add(row["pair_id"])
        if any(type(row.get(k)) not in {int,float} or not math.isfinite(row[k]) for k in ("a","b")): raise ValueError("Invalid paired value")
        grouped[row["source_group"]].append(row["b"]-row["a"])
    means=[sum(v)/len(v) for v in grouped.values()]
    n=len(means)
    estimate=sum(means)/n if n else None
    if n<10:
        return {"status":"INSUFFICIENT_INDEPENDENT_GROUPS","estimate":estimate,"groups":n,"low":None,"high":None,"reason":"Descriptive only; fewer than 10 groups"}
    if type(resamples) is not int or resamples<100: raise ValueError("At least 100 bootstrap replicates")
    rng=random.Random(seed)
    samples=[sum(rng.choices(means,k=n))/n for _ in range(resamples)]
    return {"status":"COMPUTED","estimate":estimate,"groups":n,"pairs":len(rows),"low":percentile(samples,.025),"high":percentile(samples,.975),"method":"Equal-source-group paired mean, cluster percentile bootstrap 95%","resamples":resamples,"seed":seed,"power_guaranteed":False}

def zero_error_design(target_rate,alpha=.05):
    if not 0<target_rate<1 or not 0<alpha<1: raise ValueError("Invalid probability")
    n=math.ceil(math.log(alpha)/math.log1p(-target_rate))
    return {"target_rate":target_rate,"one_sided_confidence":1-alpha,"minimum_independent_negatives_if_zero_errors":n,"assumptions":"Independent Bernoulli negative cases from target sampling distribution; not correlated variants"}
