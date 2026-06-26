#!/usr/bin/env python3
"""Refresh effectiveness.s_time in the OEQ result files against the CURRENT
time_kb.json (rows format), using tier = question's tissue_tier_code and the
documented tolerance tau = 0.2 * median clearing time.

Report-only by default; pass --patch to write the updated scores back into
dataset/Q+AR/result/*.json (updates s_time.score, s_time.reasoning, and the
effectiveness total_weighted_score). Run from the repo root:
    python results/refresh_s_time.py            # report only
    python results/refresh_s_time.py --patch     # write changes
"""
import json, glob, re, math, sys, os, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def norm(s):
    if not s:
        return ""
    s = str(s).lower()
    for ch in (" ", "-", "_", "/", "\\"):
        s = s.replace(ch, "")
    return s


kb = json.load(open(os.path.join(ROOT, "KnowledgeBase/time_kb.json"), encoding="utf-8"))["rows"]
LUT = {(norm(r["method"]), r["tier_code"]):
       (r.get("clearing_time_min_h"), r.get("clearing_time_max_h"), r.get("clearing_time_median_h"))
       for r in kb}
Q = {q["question_id"]: q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_tier_code", "")
     for q in json.load(open(os.path.join(ROOT, "dataset/Q+AR/src/question_final.json"), encoding="utf-8"))}


def stime(t, lo, hi, med):
    if med is None or med <= 0 or lo is None or hi is None:
        return 0.0
    tau = 0.2 * med
    if t < lo:
        dt = lo - t
    elif t > hi:
        dt = t - hi
    else:
        dt = 0.0
    return 3.0 if dt == 0 else max(0.0, min(3.0, 3.0 * math.exp(-0.5 * (dt / tau) ** 2)))


PATCH = "--patch" in sys.argv
old, new = [], []
changed = gated = val_ok = val_tot = 0
for f in glob.glob(os.path.join(ROOT, "dataset/Q+AR/result/evaluation_results_*_*shot.json")):
    data = json.load(open(f, encoding="utf-8"))
    dirty = False
    for it in data:
        s = it["evaluation"].get("scores", {})
        e = s.get("effectiveness", {})
        stt = e.get("s_time")
        if not isinstance(stt, dict):
            continue
        m = re.search(r"Act:\s*([\d.]+)", stt.get("reasoning", ""))
        if not m:
            continue
        t = float(m.group(1))
        old_s = stt.get("score")
        tier = Q.get(it.get("question_id"), "")
        key = (norm(it["evaluation"].get("meta_data", {}).get("target_method", "")), tier)
        if key not in LUT:
            ns = 0.0
            gated += 1
            lo = hi = med = None
        else:
            lo, hi, med = LUT[key]
            ns = stime(t, lo, hi, med)
        old.append(old_s)
        new.append(ns)
        if abs(ns - (old_s or 0)) > 0.01:
            changed += 1
        mm = re.search(r"Ref Range:\s*\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", stt.get("reasoning", ""))
        if mm and key in LUT:
            if abs(float(mm.group(1)) - lo) < 0.01 and abs(float(mm.group(2)) - hi) < 0.01:
                val_tot += 1
                val_ok += (abs(ns - old_s) < 0.01)
        if PATCH:
            stt["score"] = round(ns, 4)
            tau_s = round(0.2 * med, 2) if med else None
            stt["reasoning"] = f"Time deviation score (refreshed vs current time_kb). Act: {t}, Ref Range: [{lo}, {hi}], tau=0.2*median={tau_s}"
            e["total_weighted_score"] = sum(
                (e[k]["score"] if isinstance(e.get(k), dict) else 0) for k in ("s_method", "s_label", "s_trans", "s_time"))
            dirty = True
    if PATCH and dirty:
        json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"n={len(old)}")
print(f"s_time mean /3: OLD={st.mean(old):.3f} -> NEW={st.mean(new):.3f}  "
      f"(norm OLD={st.mean(old)/3:.3f} -> NEW={st.mean(new)/3:.3f})")
print(f"changed={changed}  newly_gated_to_0 (no method x tier in current KB)={gated}")
print(f"VALIDATION (unchanged-window cases reproduce stored): {val_ok}/{val_tot}")
print("PATCHED result files." if PATCH else "REPORT ONLY -- rerun with --patch to write.")
