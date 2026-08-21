#!/usr/bin/env python3
"""Per-dimension automated-vs-expert agreement for the ClearEval CCE metrics.

Reads dataset/Q+AR/result/Machine_vs_Human_Summary.json (240 paired records =
12 models x 20 OEQ protocols) and reports, for each CCE sub-dimension and the
three CCE aggregates + overall: Pearson r (95% CI, Fisher z), Spearman rho,
ICC(2,1) (two-way random, absolute agreement, single rater), quadratic-weighted
Cohen kappa, and interval Krippendorff alpha.

ICC and Krippendorff are hand-rolled (no pingouin dependency). Run:
    python results/compute_agreement.py
Outputs a markdown table to stdout and results/agreement_stats.json.
"""
import json, math, os
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "dataset", "Q+AR", "result", "Machine_vs_Human_Summary.json")

SUBDIMS = {
    "c_step": ("completeness", "c_step"), "c_param": ("completeness", "c_param"),
    "co_order": ("correctness", "co_order"), "co_method": ("correctness", "co_method"),
    "co_param": ("correctness", "co_param"), "co_chem": ("correctness", "co_chem"),
    "s_method": ("effectiveness", "s_method"), "s_label": ("effectiveness", "s_label"),
    "s_trans": ("effectiveness", "s_trans"), "s_time": ("effectiveness", "s_time"),
}


def m_sub(rec, dim, key):
    val = rec["machine_evaluation"]["scores"][dim][key]
    return val["score"] if isinstance(val, dict) else val


def h_sub(rec, dim, key):
    return rec["human_evaluation"][dim][key]["score"]


def m_agg(rec, dim):
    return rec["machine_evaluation"]["scores"][dim]["total_weighted_score"]


def h_agg(rec, dim):
    return rec["human_evaluation"][dim]["total_score"]


def icc_2_1(m, h):
    """ICC(2,1): two-way random, absolute agreement, single rater. k=2 raters."""
    Y = np.column_stack([m, h]).astype(float)
    n, k = Y.shape
    grand = Y.mean()
    row = Y.mean(axis=1)
    col = Y.mean(axis=0)
    SSR = k * np.sum((row - grand) ** 2)            # between subjects
    SSC = n * np.sum((col - grand) ** 2)            # between raters
    SST = np.sum((Y - grand) ** 2)
    SSE = SST - SSR - SSC
    MSR = SSR / (n - 1)
    MSC = SSC / (k - 1)
    MSE = SSE / ((n - 1) * (k - 1))
    denom = MSR + (k - 1) * MSE + (k / n) * (MSC - MSE)
    return float((MSR - MSE) / denom) if denom != 0 else float("nan")


def krippendorff_interval(m, h):
    """Interval Krippendorff alpha for 2 coders, complete data."""
    m = np.asarray(m, float); h = np.asarray(h, float)
    Do = np.mean((m - h) ** 2)
    X = np.concatenate([m, h]); N = X.size
    De = (2 * N * np.sum(X ** 2) - 2 * (np.sum(X)) ** 2) / (N * (N - 1))
    return float(1 - Do / De) if De != 0 else float("nan")


def quad_weighted_kappa(m, h):
    """Quadratic-weighted Cohen kappa on rounded integer scores."""
    a = np.rint(np.asarray(m, float)).astype(int)
    b = np.rint(np.asarray(h, float)).astype(int)
    cats = np.arange(min(a.min(), b.min()), max(a.max(), b.max()) + 1)
    K = len(cats)
    if K < 2:
        return float("nan")
    idx = {c: i for i, c in enumerate(cats)}
    O = np.zeros((K, K))
    for x, y in zip(a, b):
        O[idx[x], idx[y]] += 1
    W = np.zeros((K, K))
    for i in range(K):
        for j in range(K):
            W[i, j] = (i - j) ** 2 / (K - 1) ** 2
    hist_a = O.sum(axis=1); hist_b = O.sum(axis=0)
    E = np.outer(hist_a, hist_b) / O.sum()
    num = np.sum(W * O); den = np.sum(W * E)
    return float(1 - num / den) if den != 0 else float("nan")


def pearson_ci(m, h):
    r, _ = stats.pearsonr(m, h)
    n = len(m)
    if n < 4 or abs(r) >= 1:
        return r, float("nan"), float("nan")
    z = np.arctanh(r); se = 1 / math.sqrt(n - 3)
    lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
    return float(r), float(lo), float(hi)


def stats_for(m, h):
    m = np.asarray(m, float); h = np.asarray(h, float)
    r, lo, hi = pearson_ci(m, h)
    rho, _ = stats.spearmanr(m, h)
    return {
        "n": int(len(m)), "pearson_r": round(r, 3), "ci95": [round(lo, 3), round(hi, 3)],
        "spearman_rho": round(float(rho), 3), "icc_2_1": round(icc_2_1(m, h), 3),
        "qwk": round(quad_weighted_kappa(m, h), 3),
        "krippendorff_alpha": round(krippendorff_interval(m, h), 3),
    }


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    rows = {}
    # sub-dimensions
    for name, (dim, key) in SUBDIMS.items():
        m, h = [], []
        for rec in data:
            try:
                mv, hv = m_sub(rec, dim, key), h_sub(rec, dim, key)
                if mv is None or hv is None:
                    continue
                m.append(mv); h.append(hv)
            except (KeyError, TypeError):
                continue
        rows[name] = stats_for(m, h)
    # aggregates
    for dim, label in [("completeness", "Completeness"), ("correctness", "Correctness"),
                       ("effectiveness", "Effectiveness")]:
        m, h = [], []
        for rec in data:
            try:
                m.append(m_agg(rec, dim)); h.append(h_agg(rec, dim))
            except (KeyError, TypeError):
                continue
        rows[label] = stats_for(m, h)
    # overall
    m, h = [], []
    for rec in data:
        try:
            m.append(sum(m_agg(rec, d) for d in ("completeness", "correctness", "effectiveness")))
            h.append(rec["human_evaluation"]["overall_total_score"])
        except (KeyError, TypeError):
            continue
    rows["Overall"] = stats_for(m, h)

    json.dump(rows, open(os.path.join(HERE, "agreement_stats.json"), "w"), indent=2)

    order = ["c_step", "c_param", "Completeness", "co_order", "co_method", "co_param",
             "co_chem", "Correctness", "s_method", "s_label", "s_trans", "s_time",
             "Effectiveness", "Overall"]
    print(f"N records = {len(data)} (12 models x 20 protocols)\n")
    print("| Dimension | n | Pearson r [95% CI] | Spearman | ICC(2,1) | QWK | Kripp. alpha |")
    print("|---|---|---|---|---|---|---|")
    for k in order:
        s = rows[k]
        print(f"| {k} | {s['n']} | {s['pearson_r']:.3f} [{s['ci95'][0]:.2f},{s['ci95'][1]:.2f}] | "
              f"{s['spearman_rho']:.3f} | {s['icc_2_1']:.3f} | {s['qwk']:.3f} | {s['krippendorff_alpha']:.3f} |")


if __name__ == "__main__":
    main()
