"""
Convert time_kb.xlsx to time_kb.json for use in OEQ_run_grading_new.py

Reads the 'reviewed_supported_rows' sheet and outputs two formats:
1. A flat list (same structure as tissue.json / method_fluro_compati.json)
2. A nested lookup dict keyed by lookup_key (method|tier_code) for O(1) access
"""

import openpyxl
import json
import os

XLSX_PATH = os.path.join(os.path.dirname(__file__), "time_kb.xlsx")
JSON_PATH = os.path.join(os.path.dirname(__file__), "time_kb.json")

def convert():
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb["reviewed_supported_rows"]

    headers = [cell.value for cell in ws[1]]

    # ── flat list ──────────────────────────────────────────────────────────────
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:          # skip empty trailing rows
            continue
        obj = {}
        for h, v in zip(headers, row):
            obj[h] = v
        rows.append(obj)

    # ── nested lookup dict  (method → tier_code → timing fields) ──────────────
    # Only keep the fields needed by the scoring formula:
    #   clearing_time_min_h, clearing_time_median_h, clearing_time_max_h
    # plus metadata that callers might want.
    lookup = {}
    for r in rows:
        method = r["method"]
        tier   = r["tier_code"]
        if method not in lookup:
            lookup[method] = {}
        lookup[method][tier] = {
            "tier_label":              r["tier_label"],
            "supported":               r["supported"],
            "clearing_time_min_h":     r["clearing_time_min_h"],
            "clearing_time_median_h":  r["clearing_time_median_h"],
            "clearing_time_max_h":     r["clearing_time_max_h"],
            "time_unit":               r["time_unit"],
            "time_excludes_labeling":  r["time_excludes_labeling"],
            "confidence":              r["confidence"],
        }

    output = {
        "schema_version": "time_kb_v1",
        "description": (
            "Clearing-time reference ranges (hours) per method × sample-size tier. "
            "Converted from time_kb.xlsx (reviewed_supported_rows sheet). "
            "Use clearing_time_min_h / clearing_time_max_h as t_min / t_max "
            "in the S_time Gaussian scoring formula."
        ),
        "time_unit": "hours",
        "time_excludes_labeling": True,
        "rows": rows,          # flat list  – mirrors tissue.json style
        "lookup": lookup,      # nested dict – O(1) access by method+tier
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] Written {len(rows)} rows to {JSON_PATH}")
    print(f"     Methods  : {sorted(lookup.keys())}")
    print(f"     Tiers    : {sorted({t for m in lookup.values() for t in m})}")

if __name__ == "__main__":
    convert()
