# ClearEval — Data & Figure/Table Manifest

This document maps **every figure and table in the paper** (`article/BIBM/main.tex`)
to the exact data files and the script that produces it, so reviewers can trace and
reproduce each result. Anything not listed here is exploratory/superseded and lives
under [`archive/`](archive/) (see [`archive/README.md`](archive/README.md)); nothing in
`archive/` is needed to reproduce the paper.

All paths are relative to the repository root. Effectiveness uses the signed method
suitability `S_method = (F_method + 1) / 2 ∈ [0,1]` consistently across the main table,
Table IV, the violin plot, and the radar chart.

---

## Figure / table → data → script

| Paper element (label) | Figure/table file | Source data | Generating script |
|---|---|---|---|
| **Fig. 1** — Overview (`fig:overview`) | `article/BIBM/figures/overview.png` | — (schematic diagram) | hand-authored, no script |
| **Table** — Feasibility DB inventory (`tab:db_inventory`) | in-text table | `KnowledgeBase/*.json` (see below) + 372 wet-lab records + 400+ literature chunks | hand-authored from KB counts |
| **Table** — CCE metric hierarchy (`tab:metrics`) | in-text table | — (conceptual) | hand-authored |
| **Table** — Judge calibration (`tab:calib`, and full `tab:calibfull`) | in-text table | `results/agreement_stats.json` ← `dataset/Q+AR/result/human_evaluation_scores.json` + `Machine_vs_Human_Summary.json` (n=240: 20 scenarios × 12 models) | `results/compute_agreement.py` |
| **Table** — Main results, 13 models (`tab:main_results_total`) | in-text table | OEQ: `results/oeq_stats_260223.jsonl`; MCQ: `results/mcq_stats_20260222.jsonl` | `results/calculate_main_table_score.py` (LaTeX rows: `results/generate_latex_rows.py`) |
| **Fig. 2** — Radar, MCQ vs CCE (`fig:radar_chart`) | `article/BIBM/figures/radar_chart.png` | `results/oeq_stats_260223.jsonl` + `results/mcq_stats_20260222.jsonl` | `results/plot_combined_radar.py` → `results/combined_radar_chart.png` (copied into `figures/`) |
| **Fig.** — Effectiveness sub-metric violins (`fig:violin_limits`) | `article/BIBM/figures/violin_plots.png` | `dataset/Q+AR/result/evaluation_results_*_1-shot.json` (13 models); cached: `figures/fig_data/fig4_violin.json` | `results/plot_violin_and_heatmap.py` (data: `results/export_fig_data.py`) |
| **Fig.** — Clearing-method usage heatmap (`fig:method_usage`) | `article/BIBM/figures/method_usage.png` | same 13 eval files + `dataset/Q+AR/src/model_space_signed.json`; cached: `figures/fig_data/fig3_heatmap.json` | `results/plot_violin_and_heatmap.py` (data: `results/export_fig_data.py`) |
| **Table IV** — Inference-time grounding (`tab:inference_time`) | in-text table | `dataset/Q+AR/result/evaluation_results_{gpt-5.2-fast,qwen3-max,qwen3-14b}_1-shot{,+KB-RAG,+KB-RAG+self-check}.json` (9 files) | `results/aggregate_rag_baseline.py` → `results/rag_baseline_summary.csv` |

---

## Upstream data (how the aggregated stats are produced)

| Aggregated file | Produced by | From |
|---|---|---|
| `results/oeq_stats_260223.jsonl` (per-model OEQ sub-metric norms) | `results/aggregate_oeq.py` | the 13 base `dataset/Q+AR/result/evaluation_results_*_1-shot.json` |
| `results/mcq_stats_20260222.jsonl` (per-category MCQ accuracy) | `results/aggregate_mcq.py` | MCQ model responses on the 768-question development split |
| `results/agreement_stats.json` (ICC/QWK/α calibration) | `results/compute_agreement.py` | human vs automated scores on the 20-scenario × 12-model calibration subset |

## Knowledge bases (feed the deterministic Effectiveness sub-metrics)

Located in `KnowledgeBase/`:

| File | Content | Effectiveness sub-metric |
|---|---|---|
| `time_kb.json` (126 method×tier rows) + `method_time_tau.json` | clearing-time windows & tolerances | `S_time` |
| `method_ri_ref.json` + `method_sigma_ri.json` + `tissue_ri.json` | refractive-index references & tolerances | `S_trans` |
| `method_fluro_compati.json` | marker × method fluorophore compatibility | `S_label` |
| `tissue.json` | tissue & target table | `S_label` / task construction |
| `dataset/Q+AR/src/model_space_signed.json` | method capability vectors (20 methods × axes) | `S_method` |

---

## Reproduce the paper numbers (run order, from repo root)

```bash
# 1. aggregate raw model evaluations -> per-model stats
python results/aggregate_oeq.py         # -> results/oeq_stats_260223.jsonl
python results/aggregate_mcq.py         # -> results/mcq_stats_20260222.jsonl
python results/compute_agreement.py     # -> results/agreement_stats.json

# 2. main results table (Com/Cor/Eff/I_A/I_K/Total for 13 models)
python results/calculate_main_table_score.py

# 3. figures
python results/plot_combined_radar.py       # -> results/combined_radar_chart.png (Fig. 2)
python results/export_fig_data.py           # -> figures/fig_data/{fig3_heatmap,fig4_violin}.json
python results/plot_violin_and_heatmap.py   # -> figures/{violin_plots,method_usage}.png

# 4. Table IV (inference-time grounding)
python results/aggregate_rag_baseline.py    # -> results/rag_baseline_summary.csv
```

`figures/*.png` used by the manuscript are copied into `article/BIBM/figures/`.
