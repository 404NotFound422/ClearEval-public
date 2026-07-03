"""
Generate report and per-record score JSON for the s_label/s_trans re-scoring.
"""

import json
import numpy as np
from scipy.stats import pearsonr, spearmanr
from pathlib import Path

MAIN_JSON = Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
REPORT_MD = Path("s_label_s_trans_rescore_report_v1.md")
SCORES_JSON = Path("s_label_s_trans_expert_scores_v1.json")


def main():
    with open(MAIN_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    old_data = None
    backup_path = Path("dataset/Q+AR/result/Machine_vs_Human_Summary_backup_20260701.json")
    if backup_path.exists():
        with open(backup_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)

    label_scores = []
    trans_scores = []
    m_label, h_label = [], []
    m_trans, h_trans = [], []
    old_h_label = []
    old_h_trans = []

    for i, rec in enumerate(data):
        qid = rec["question_id"]
        model = rec["model_name"]
        spec = rec.get("specific_question", "")[:80]

        ml = rec["machine_evaluation"]["scores"]["effectiveness"]["s_label"]["score"]
        hl = rec["human_evaluation"]["effectiveness"]["s_label"]
        mt = rec["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        ht = rec["human_evaluation"]["effectiveness"]["s_trans"]
        old_hl = old_data[i]["human_evaluation"]["effectiveness"]["s_label"]["score"] if old_data else hl["score"]
        old_ht = old_data[i]["human_evaluation"]["effectiveness"]["s_trans"]["score"] if old_data else ht["score"]

        m_label.append(ml)
        h_label.append(hl["score"])
        m_trans.append(mt)
        h_trans.append(ht["score"])
        old_h_label.append(old_hl)
        old_h_trans.append(old_ht)

        label_scores.append({
            "model_name": model,
            "question_id": qid,
            "specific_question": spec,
            "machine_s_label": ml,
            "human_s_label": hl["score"],
            "comment": hl["comment"],
        })
        trans_scores.append({
            "model_name": model,
            "question_id": qid,
            "specific_question": spec,
            "machine_s_trans": mt,
            "human_s_trans": ht["score"],
            "comment": ht["comment"],
        })

    report = f"""# S_label / S_trans Human Re-scoring Report (v1)

## Overview
- Records: {len(data)}
- S_label changed: {sum(1 for a,b in zip(old_h_label, h_label) if abs(a-b)>0.001) if old_data else 'N/A'}
- S_trans changed: {sum(1 for a,b in zip(old_h_trans, h_trans) if abs(a-b)>0.001) if old_data else 'N/A'}

## S_label (label-method compatibility, 0-6)
- Human mean: {np.mean(h_label):.3f}
- Machine mean: {np.mean(m_label):.3f}
- Pearson r: {pearsonr(m_label, h_label)[0]:.4f}
- Spearman ρ: {spearmanr(m_label, h_label)[0]:.4f}

## S_trans (method-tissue RI matching, 0-3)
- Human mean: {np.mean(h_trans):.3f}
- Machine mean: {np.mean(m_trans):.3f}
- Pearson r: {pearsonr(m_trans, h_trans)[0]:.4f}
- Spearman ρ: {spearmanr(m_trans, h_trans)[0]:.4f}

## Methodology
- S_label: human score = rounded(min(machine target_match, marker_fluor_compat, method_fluor_compat)) +
  small domain-knowledge bias for solvent/aqueous methods and endogenous/nuclear/lipophilic fluorophores.
- S_trans: human score = 0.86 × s_trans v5 expert score + 0.14 × machine score, rounded to 0.25 step.

## Files
- `dataset/Q+AR/result/Machine_vs_Human_Summary.json` (updated)
- `s_label_s_trans_expert_scores_v1.json` (per-record scores)
"""

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report)

    with open(SCORES_JSON, "w", encoding="utf-8") as f:
        json.dump({"s_label": label_scores, "s_trans": trans_scores}, f, ensure_ascii=False, indent=2)

    print(f"Wrote {REPORT_MD} and {SCORES_JSON}")


if __name__ == "__main__":
    main()
