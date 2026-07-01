#!/usr/bin/env python3
"""Re-score effectiveness.s_method with the SIGNED method-fit metric.

Design (confirmed 2026-07-01):
  * per-axis capability from model_space V, mapped to
      - SIGNED [-1,+1] on F_fp / P_dye / M_geo / S_safe   (2*norm - 1;  quench/harm < 0, benefit > 0)
      - MAGNITUDE [0,1] on C_opt / E_ops                   (capability, cannot actively harm)
  * demand weight x2 on F_fp and P_dye (the two labeling axes -- most decisive for method choice)
  * need-weighted signed benefit  b = sum(w*demand*cap) / sum(w*demand)  in [-1,1]
  * raw score = 2.5 * b  in [-2.5,+2.5];  max_score = 2.5  ->  normalizes to symmetric [-1,+1]
    (a bad method choice therefore PENALIZES Effectiveness; Effectiveness is clamped at 0 downstream).

Per-scenario demand vectors (v_pred) are extracted once via the teacher and cached to
dataset/Q+AR/src/demand_vectors_all.json.  Run from repo root:
    python results/refresh_s_method.py            # extract (cached) + report
    python results/refresh_s_method.py --patch     # also write scores into the eval files
    python results/refresh_s_method.py --refresh    # force re-extraction of demand vectors
"""
import json, glob, os, sys, asyncio
import numpy as np
sys.path.insert(0, r"d:/YWB/ClearEval-public")
os.chdir(r"d:/YWB/ClearEval-public")
from OEQ_run_grading_new import get_user_preference_vector
from models.Model_Loader import ModelLoader

ROOT = r"d:/YWB/ClearEval-public"
CACHE = os.path.join(ROOT, "dataset/Q+AR/src/demand_vectors_all.json")
# SIGNED capability space: F_fp/P_dye/M_geo/E_ops/S_safe in [-1,+1] (+ helps the objective,
# - actively harms it); C_opt is a non-negative clearing-power magnitude [0,1].
MS = json.load(open(ROOT + "/dataset/Q+AR/src/model_space_signed.json", encoding="utf-8"))["methods"]
DIMS = [("fluorescence_protein_preservation", "F_fp"), ("dye_permeability", "P_dye"),
        ("clearing_challenge", "C_opt"), ("geometry_preference", "M_geo"),
        ("operational_economy", "E_ops"), ("safety_compatibility", "S_safe")]
DWEIGHT = 2.0    # emphasis multiplier applied to the WINNING labeling axis (F_fp xor P_dye)
MAXSCORE = 2.5   # score in [-2.5,+2.5] -> normalizes to symmetric [-1,+1]


def _norm(s):
    s = str(s or "").lower()
    for ch in " -_/()":
        s = s.replace(ch, "")
    return s.replace("+", "")


def find_method(name):
    nl = _norm(name)
    if not nl:
        return None
    for k, v in MS.items():
        kl = _norm(k)
        if (nl in kl or kl in nl) and min(len(nl), len(kl)) >= 3:
            return v
    # keyword fallback: free-text organic-solvent descriptions -> canonical solvent profile
    for kw, canon in (("3disco", "3DISCO"), ("thf", "3DISCO"), ("dbe", "3DISCO"),
                      ("dcm", "3DISCO"), ("babb", "BABB"), ("benzyl", "BABB"),
                      ("ethylcinnamate", "BABB"), ("idisco", "iDISCO (iDISCO+)"),
                      ("solvent", "3DISCO")):
        if kw in nl and canon in MS:
            return MS[canon]
    return None


def _dem(demand, long):
    o = demand.get(long) or {}
    return float(o.get("target", 0) or 0), float(o.get("weight", 0) or 0)


def s_method_signed(demand, mv):
    """Need-weighted SIGNED method-fit.

    demand strength per axis  ds = scenario_weight * target  (silent axis -> W=0 -> drops out).
    capability cap read directly from the SIGNED model_space (+ helps / - harms; C_opt magnitude).
    The two labeling axes F_fp/P_dye are MUTUALLY EXCLUSIVE: the axis with the larger weighted
    demand is emphasized (xDWEIGHT), the other is zeroed (no double labeling penalty).
    score = MAXSCORE * sum(ds*cap)/sum(ds)  in [-MAXSCORE, +MAXSCORE].
    """
    if not demand or not mv:
        return None
    t_fp, w_fp = _dem(demand, "fluorescence_protein_preservation")
    t_pd, w_pd = _dem(demand, "dye_permeability")
    mult = {"F_fp": 1.0, "P_dye": 1.0}
    if w_fp * t_fp >= w_pd * t_pd:
        mult["F_fp"], mult["P_dye"] = DWEIGHT, 0.0
    else:
        mult["F_fp"], mult["P_dye"] = 0.0, DWEIGHT
    num = den = 0.0
    for long, short in DIMS:
        t, w = _dem(demand, long)
        if short == "M_geo":
            t = min(t, 1.0)   # isotropy demand treated as unipolar preserve-need
        ds = mult.get(short, 1.0) * w * t
        if ds <= 0:
            continue
        num += ds * float(mv.get(short, 0) or 0)
        den += ds
    return round(MAXSCORE * (num / den), 4) if den > 0 else None


def _degeneracy_report(demand):
    """Print de-saturation + argmax(non-degeneracy) diagnostics over the demand vectors."""
    dvs = [d for d in demand.values() if d]
    print(f"\n=== demand de-saturation ({len(dvs)} scenarios) ===")
    print(f"{'axis':6} | {'tgt_mean':>8} {'w_mean':>7} | frac(w>0)")
    for long, short in DIMS:
        ts = [_dem(d, long)[0] for d in dvs]
        ws = [_dem(d, long)[1] for d in dvs]
        act = (sum(1 for w in ws if w > 0) / len(ws)) if ws else 0
        print(f"{short:6} | {np.mean(ts):8.3f} {np.mean(ws):7.3f} | {act:.1%}")
    wins, fp_n, dye_n = {}, 0, 0
    for d in dvs:
        t_fp, w_fp = _dem(d, "fluorescence_protein_preservation")
        t_pd, w_pd = _dem(d, "dye_permeability")
        if w_fp * t_fp >= w_pd * t_pd:
            fp_n += 1
        else:
            dye_n += 1
        best, bs = None, -1e9
        for k, mv in MS.items():
            s = s_method_signed(d, mv)
            if s is not None and s > bs:
                bs, best = s, k
        wins[best] = wins.get(best, 0) + 1
    print("\n=== argmax distribution (non-degeneracy) ===")
    for k, c in sorted(wins.items(), key=lambda x: -x[1]):
        print(f"  {str(k):22} {c:4} ({c/len(dvs):.0%})")
    print(f"# distinct winners = {len(wins)};  ME split: FP={fp_n} dye={dye_n}")


# scenario text by question_id (source of truth = question_final.json)
Q_TEXT = {}
for q in json.load(open(ROOT + "/dataset/Q+AR/src/question_final.json", encoding="utf-8")):
    Q_TEXT[str(q.get("question_id"))] = q.get("question") or q.get("specific_question") or ""


async def extract_all(qid_text, refresh):
    cache = json.load(open(CACHE, encoding="utf-8")) if (os.path.exists(CACHE) and not refresh) else {}
    todo = [q for q in qid_text if q not in cache or not cache.get(q)]
    if todo:
        print(f"extracting {len(todo)} demand vectors via teacher (openai_gpt-5.2-thinking)...")
        teacher = ModelLoader(ROOT + "/config/config.yaml").load_models()["openai_gpt-5.2-thinking"]
        sem = asyncio.Semaphore(6)

        async def one(qid):
            async with sem:
                v = await get_user_preference_vector(teacher, qid_text[qid])
                return qid, v
        done = 0
        for coro in asyncio.as_completed([one(q) for q in todo]):
            qid, v = await coro
            cache[qid] = v
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(todo)}")
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"wrote {CACHE} ({sum(1 for v in cache.values() if v)}/{len(cache)} non-empty)")
    return cache


def main():
    patch = "--patch" in sys.argv
    files = glob.glob(ROOT + "/dataset/Q+AR/result/evaluation_results_*_*shot.json")
    qid_text = {}
    for f in files:
        for it in json.load(open(f, encoding="utf-8")):
            qid = str(it.get("question_id"))
            if qid not in qid_text:
                qid_text[qid] = Q_TEXT.get(qid) or it["evaluation"].get("meta_data", {}).get("sample_info", "")
    demand = asyncio.run(extract_all(qid_text, "--refresh" in sys.argv))
    _degeneracy_report(demand)

    old, new = [], []
    gated = 0
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        dirty = False
        for it in data:
            e = it["evaluation"].get("scores", {}).get("effectiveness", {})
            sm = e.get("s_method")
            if not isinstance(sm, dict):
                continue
            meth = it["evaluation"].get("meta_data", {}).get("target_method", "")
            mv = find_method(meth)
            d = demand.get(str(it.get("question_id")))
            ns = s_method_signed(d, mv)
            if ns is None:
                ns = 0.0
                gated += 1
            old.append(sm.get("score"))
            new.append(ns)
            if patch:
                sm["score"] = ns
                sm["max_score"] = MAXSCORE
                sm["reasoning"] = ("Signed method-fit (need-weighted ds=W*target; winning "
                                   "labeling axis F_fp xor P_dye x2; caps signed [-1,1], "
                                   f"C_opt magnitude). Method: {meth}")
                e["total_weighted_score"] = sum(
                    (e[k]["score"] if isinstance(e.get(k), dict) else 0) for k in ("s_method", "s_label", "s_trans", "s_time"))
                dirty = True
        if patch and dirty:
            json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    old = np.array([x for x in old if x is not None], float)
    new = np.array(new, float)
    print(f"\nn={len(new)}  gated_to_0 (no demand/method)={gated}")
    print(f"OLD s_method: mean={old.mean():.3f} (max 5 -> norm {old.mean()/5:.3f})")
    print(f"NEW s_method: mean={new.mean():.3f} (max {MAXSCORE} -> norm {new.mean()/MAXSCORE:+.3f})  "
          f"range [{new.min():.2f}, {new.max():.2f}]")
    print("PATCHED result files." if patch else "REPORT ONLY -- rerun with --patch to write.")


if __name__ == "__main__":
    main()
