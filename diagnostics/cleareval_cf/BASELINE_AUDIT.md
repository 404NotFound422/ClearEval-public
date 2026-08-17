# ClearEval Baseline Audit (Phase 1 of counterfactual-validity upgrade)

Audit date: 2026-08-17. Method: full read of the scorer/aggregation code, prompts,
config, and structural Python summaries of all JSON data/KB files (per instructions,
large JSONs were summarized structurally with python; code files were read fully).

## Git commit audited

- Commit: `8a1f8de733d73e69a79fd1e3d950e0c603884937`
- Branch: `cleareval-cf-validity`

## MCQ count

- **2,588 items** in `dataset/MCQ/final/all_mcq_data.jsonl`
- sha256: `9d403100920be87afd9e356817382fb4da8f5bf05bf80133dd677c17798de981`
- Categories: Named Entity Recognition 533, Domain Knowledge Evaluation 1,350, Task Scenario Questions 705 (sums to 2,588; unique `question_id` = 2,588)
- Fields per record: `question_id`, `question`, `options`, `answers`, `answer_index`, `category`, `knowledge_point`, `specific`
- Also present: `dataset/MCQ/final/development.jsonl` (768), `validation.jsonl` (30); `dataset/MCQ/all_mcq_data_from_reagent.jsonl` (80, different/legacy file)
- README.md:5,108-117 and DATA_MANIFEST.md:36 claims match (2,588; 768-dev split).

## OEQ count

- **253 questions** in `dataset/Q+AR/src/question_final.json`
- sha256: `487c62e32e7096bf5963edbbf1af8ba2fa9d5a371702675a836b309a8cecbd9b`
- `question_id` 1..256, 253 unique (3 gaps). All 253 are single-format scenario prompts (no explicit question "mode/type" field; all are the Application/protocol-design type).
- Fields per record: `question_id` (int), `question` (str), `tissue_hierarchy_from_tissue_xlsx` (`tissue_inferred`, `tissue_tier_code`, `tissue_tier_label`), `marker_query_targets` (list of `{target_index, source_tissue_xlsx_row, marker_slot, marker_name, query_path, major_category, subcategory, structure_or_cell_subtype}`).
- Tier distribution (tissue_tier_code): T05 54, T07 39, T03 31, T06 28, T10 27, T04 25, T09 15, T02 11, T12 9, T01 6, T08 4, T11 4.
- Targets/question: 2 targets ×157, 4 ×92, 6 ×4.
- Other files in `dataset/Q+AR/src/`: `standard_response.json` (10 entries, unused by scoring), `restrict.py` (DEFAULT_RESTRICT: 3 keys — ClearingMethod/Dye_or_Fluorophore/Marker), `model_space.json` (18 methods, legacy V/W), `model_space_signed.json` (20 methods, active for S_method), `demand_vectors_all.json` (253 qids × 6 dims, used by build_rag_context.py).

## Teacher (judge) model and prompt version(s)

- **Teacher default: `openai_gpt-5.2-thinking`** — `OEQ_run_grading_new.py:1785` (`parser.add_argument("--teacher", default="openai_gpt-5.2-thinking")`); fallback `openai_gpt-4o` at `:1831-1832`.
- Config entry `config/config.yaml:44-49`: `name: openai_gpt-5.2-thinking`, `type: api`, `model_name: gpt-5.2`, `base_url: https://api.openai-proxy.org/v1`, `temperature: 0.0`, `enable_thinking: True`, `max_tokens: 8000`.
- Log evidence the frozen runs used this teacher: `dataset/Q+AR/logs/teacher_responses_2026-06-29.jsonl` (503 entries) and `teacher_responses_2026-07-01.jsonl` (2,568 entries) record `teacher_model: "gpt-5.2"` for 2,968 of 3,071 logged calls (the remaining 103 on 07-01 are `deepseek-chat` 2 + `deepseek-v4-pro` 101 — see anomalies below).
- Active prompt files:
  - `prompts/eval_oeq_teacher_rubric.txt` — the ACTIVE teacher rubric; loaded by `evaluate_response_with_teacher` at `OEQ_run_grading_new.py:1280-1283` (no version identifier beyond the filename).
  - `prompts/gen_protocol_template.py` — `TEST_MODEL_GENERATION_PROMPT` (generation prompt; `OEQ_run_grading_new.py:42`).
  - `prompts/parse_user_preference_vector.py` — `USER_PREFERENCE_PROMPT` (teacher-driven demand vector for S_method; `OEQ_run_grading_new.py:43,899`).
  - Inline `SELF_CHECK_PROMPT` defined in `OEQ_run_grading_new.py:866-882` (KB-RAG+self-check revision checklist).
  - `prompts/eval_teacher_protocol_review.py` — loaded at `OEQ_run_grading_new.py:736-748` but **vestigial**; its header says "Vestigial scoring-prompt module… exists only to satisfy the non-empty guard in load_prompt_method_generate()". The `prompt_template` it returns is passed around but never used to score (rubric .txt is used).
  - `prompts/eval_completeness_checklist.txt` — NOT referenced by any code in the repo (grep across *.py: no hits). Legacy standalone checklist.

## CCE component definitions (verbatim from code/prompts)

Score universe: Completeness + Correctness are LLM-judge sub-scores (from `prompts/eval_oeq_teacher_rubric.txt`); Effectiveness is deterministic (`OEQ_run_grading_new.py:1038-1227`).

**Completeness (judge; rubric lines 50-96):**
- `C_step` ∈ {0,1,2} — "步骤模块完整性" (2=perfect, 1=minor gaps, 0=missing key module; rubric.txt:72-76)
- `C_param` ∈ {0,1,2,3} — "参数细节完整性" (3=supplementary-level detail, 0=unexecutable; rubric.txt:90-96)
- `total_completeness_score` = C_step + C_param, max 5 (rubric example `"total_weighted_score": 5.0`, rubric.txt:290; stored as `total_weighted_score`).

**Correctness (judge; rubric lines 139-191):**
- `Co_order` ∈ {0,1,2,3} (rubric.txt:139-151), `Co_method` ∈ {0,1,2} (:153-165), `Co_param` ∈ {0,1,2} (:167-177), `Co_chem` ∈ {0,1} (:179-191). Sum max = 8 (rubric example `"total_weighted_score": 8.0`, :318).

**Effectiveness (deterministic; `OEQ_run_grading_new.py`):**
- `E_score = w1*S_method + w2*S_label + w3*S_trans + w4*S_time`, `w1=w2=w3=w4=1.0` (:1043-1044, `e_score = ...` :1204). Max = 2.5 + 6 + 3 + 3 = **14.5**.
- `S_method` ∈ [−2.5, +2.5] — signed need-weighted method-fit: `score = S_METHOD_MAX * sum(ds*cap)/sum(ds)` with `S_METHOD_MAX = 2.5` (:946), dims `F_fp/P_dye/C_opt/M_geo/E_ops/S_safe` from `model_space_signed.json`; the two labeling axes F_fp/P_dye are mutually exclusive, winner weighted ×2.0 (`_SM_DWEIGHT`, :947, :993-997); unmatched method → 0.0 neutral (:1052-1056).
- `S_label` ∈ [0,6] — `s_label = min(s_target_match, s_marker_fluor_compat, s_method_fluor_compat)`, clamped `max(0.0, min(6.0, s_label))` (:1122-1123). Components: `s_target_match` ∈ {0,3,6} (specificity tiers 0/3/6 with major-category partial credit, :1066-1091), `s_marker_fluor_compat` ∈ {0,6} (tissue.json 0-cells → 0, else 6; unknown → 6, :1094-1107), `s_method_fluor_compat` = `compat_val * 6.0` ∈ [0,6] (method_fluro_compati.json; unknown → 6, :1110-1120).
- `S_trans` ∈ [0,3] — `s_trans = 3.0 * exp(-0.5 * ((RI_tissue - RI_method_ref)/sigma_RI)**2)` (:1154-1155), gated: (method,tier) not in `time_kb.json` lookup → 0 ("out_of_method_range", :1142-1146); missing RI/σ data → 0 ("missing_kb", :1147-1151). RI_tissue from question metadata via `_resolve_tissue_ri` (:88-170, tissue_ri.json, default 1.48); RI_method_ref from method_ri_ref.json; σ from method_sigma_ri.json.
- `S_time` ∈ [0,3] — `s_time = 3.0 * exp(-0.5 * (delta_t/tau)**2)` (:1199); delta_t = distance of extracted `clearing_total_time_hours` outside [t_min, t_max] from time_kb.json (:1186-1194); **τ is derived, not looked up**: `tau = 0.2*median` if under/inside, `0.1*median` if over (asymmetric, over-long penalized 2×; :1166, :1184-1194); no time extracted or no KB row → 0 (:1171-1180). T07/T11 parent-tier fallback to shortest-median sub-tier (:1017-1035).
- Note: `method_time_tau.json` is loaded (`TIME_TAU_KB`, :700-702) but **never used** in scoring — its τ values are dead data on this path (the KB's own k_factor=0.2 is hard-coded in the scorer).

**Indices (results/calculate_main_table_score.py):**
- `Completeness = 0.4*c_step_norm + 0.6*c_param_norm` (:51); `Correctness = mean(co_order_norm, co_method_norm, co_param_norm, co_chem_norm)` (:52); `s_method_01 = (s_method_norm + 1)/2` (:54); `Effectiveness = mean(s_method_01, s_label_norm, s_trans_norm, s_time_norm)` (:55); all ×100.
- `I_A = min(Completeness, Correctness, Effectiveness)` (:101; also README.md:307, main.tex:278).
- `I_K = (Tissue + Reagent + Method)/3` (:100); Tissue/Reagent/Method are means of 2/2/5 MCQ sub-dimensions from `results/mcq_stats_20260222.jsonl` (:31-33).
- `Total = 2 * I_K * I_A / (I_K + I_A)` harmonic mean (:103; main.tex:426).

## Aggregation formulas (verbatim)

`results/aggregate_oeq.py` — reads every `dataset/Q+AR/result/evaluation_results_*.json`:
- `MAX_SCORES = {'c_step': 2, 'c_param': 3, 'co_order': 3, 'co_method': 2, 'co_param': 2, 'co_chem': 1, 's_method': 2.5, 's_label': 6, 's_trans': 3, 's_time': 3}` (:23-27)
- Per sub-metric: `avg = sum(vals)/len(vals)`; `avg_scores[f"{m}_norm"] = avg / MAX_SCORES[m]` (:98-101); record `{model_name, average_scores, sample_count}` → `results/oeq_stats_260223.jsonl` (:103-113).

`results/calculate_main_table_score.py` (quoted above): `completeness = 0.4*c_step_norm + 0.6*c_param_norm` (:51); `correctness = (co_order_norm+co_method_norm+co_param_norm+co_chem_norm)/4` (:52); `s_method_01 = (s_method_norm+1)/2` (:54); `effectiveness = (s_method_01+s_label_norm+s_trans_norm+s_time_norm)/4` (:55); `i_k = sum(i_k_vals)/3` (:100); `i_a = min(i_a_vals)` (:101); `total = 2*i_k*i_a/(i_k+i_a)` (:103).

`results/compute_agreement.py` — agreement only (no score aggregation): reads `dataset/Q+AR/result/Machine_vs_Human_Summary.json` (240 records) and computes Pearson r, Spearman ρ, ICC(2,1), QWK, Krippendorff α per sub-dimension + aggregates + Overall; writes `results/agreement_stats.json` (:119-154).

## Knowledge-base files used by the OEQ scorer

Loaded at import time in `OEQ_run_grading_new.py` (:52-65) unless noted:

| File | Record count / schema | sha256 |
|---|---|---|
| `KnowledgeBase/tissue.json` | 112 rows; marker-site × fluorophore compat matrix + 大类/亚类 categories | `6786bb3b94cd9f07deea0f3fc3535cb6b566c0e9f3753be6ddd978dd1629c5e8` |
| `KnowledgeBase/method_fluro_compati.json` | 17 methods × 44 fluorophore keys (0-1) | `3c1b66ad96eb46c6ab8fb01563b193ec5657fbb9b0b9de627d51b7d43b461aeb` |
| `KnowledgeBase/time_kb.json` | 126 rows; `{lookup: 17 methods × tiers {clearing_time_min/median/max_h}}` | `5a7c04e3bad4963bb07f11c5675b55f2281068ea88e925f15a41715149c4ab11` |
| `KnowledgeBase/method_time_tau.json` | `tau` table, 17 methods (LOADED BUT UNUSED in scoring) | `0ddaa0672a789b7dad9d2b2e1b61452c14155e14a6de3f058bcfad5b3949913b` |
| `KnowledgeBase/tissue_ri.json` | 5 categories (brain/viscera_soft/muscle_fibrous/hard_tissue/special), default_ri 1.48 | `686a3f0e36cc35f33d3db64a4f06745a4b1cc5670753893c533cd998fd47852d` |
| `KnowledgeBase/method_sigma_ri.json` | `sigma_RI`, 18 methods × tiers | `250c87f3a530178c9bb88b7649d99ad6969e638d0e8ae513664761ce7cc444e9` |
| `KnowledgeBase/method_ri_ref.json` | `ri_ref`, 18 methods `{ri, primary_sample, source}` | `fbf59e62140749ba84f740efbee8b3818550d1eab3afe6b8d290195ffaa3b332` |
| `workflow/s_label_audit/marker_specificity_tiers.json` | tier_0 76, tier_3 13, tier_6 65 (optional; loaded if present, :71-77) | `707a9a6bd888bc0841205ed6fbb8fca6bafbc2997a6cf1014d35c0bb2c9005bf` |
| `workflow/s_label_audit/fluorophore_classification_for_review.json` | tissue_mappings 35, marker_redirects 23, penalty_list 35 (optional; :255-278) | `9f3b908a4723f9720e7bada34e152fdd2329b225b90335e0788e3877e08e5878` |
| `dataset/Q+AR/src/model_space_signed.json` | 20 methods × 6 signed dims (F_fp/P_dye/C_opt/M_geo/E_ops/S_safe) | `4db74aa19acf918d4236ba4e420356713db6ec55a396899d1e197432a256db19` |
| `dataset/Q+AR/src/model_space.json` | 18 methods legacy V/W space (loaded in `load_data()` :774 but unused for S_method) | `c0290e2ba207282cb2c250a2c5776981743a034ed80affd386ef2e91c2d85e94` |
| `dataset/Q+AR/src/demand_vectors_all.json` | 253 qids × 6 dims `{target, weight}` — used by `build_rag_context.py:57` (not the scorer) | `c2e63a6f8e4e253faa76ef046128fcb194ae4a70fa07e15bc22824a0665edfea` |
| `dataset/Q+AR/src/question_final.json` | 253 (see OEQ count) | `487c62e3...` |
| `dataset/Q+AR/src/standard_response.json` | 10 entries (loaded :772, unused in scoring) | `00f104b26a98457034c69ed1aebfc6807fb0add2e5ed4e74fd451a5ed3905ef4` |
| `dataset/Q+AR/src/restrict.py` | DEFAULT_RESTRICT, 3 keys (loaded :755-763) | `169a38f554aafd1ea57a8787d8159aff8d29322432a4744f8a22b9ba85974fb9` |

`build_rag_context.py` additionally reads: `KnowledgeBase/method_ri_ref.json` (`ri_ref`), `time_kb.json` (`lookup`), `tissue.json`, `method_fluro_compati.json`, `model_space_signed.json`, `demand_vectors_all.json`, `question_final.json` (:56-62). It writes 253 `dataset/Q+AR/rag_context/rag_context_<qid>.json` (all 253 present).

`KnowledgeBase/article_chunk/` (18 per-method files, 163 method-fact records, 659 text spans, 893 reference entries) is **not read by any code** (grep: no hits). `KnowledgeBase/time_kb.xlsx` and `convert_time_kb.py` are provenance artifacts (converter), also not read by the scorer.

## Frozen OEQ model outputs inventory (inputs to seed selection later)

Primary graded outputs — `dataset/Q+AR/result/evaluation_results_<model>_<shot>.json`:
- **13 base `1-shot` files** (n=253 each except `gemini-3-flash` n=252, qid 1 missing, and the missing qid-1 record means that model has 251 usable scored records): gemini-3-flash, gemini-3-pro, glm4.7-thinking, glm4.7-unthinking, openai_claude-sonnet-4.6, openai_deepseek-chat, openai_deepseek-reasoner, openai_gpt-5.2-fast, openai_gpt-5.2-thinking, openai_qwen3-14b, openai_qwen3-235b, openai_qwen3-32b, openai_qwen3-max.
- **9 Table-IV RAG files** (3 models × {1-shot, 1-shot+KB-RAG, 1-shot+KB-RAG+self-check}; n=253 each): openai_gpt-5.2-fast, openai_qwen3-max, openai_qwen3-14b.
- Record schema (all eval files): `{question_id, evaluation: {meta_data: {protocol_id, sample_info, target_method, generated_timestamp}, scores: {completeness: {c_step{score,max_score,description,reasoning}, c_param{...}, total_weighted_score[, comment]}, correctness: {co_order,co_method,co_param,co_chem (each {score,max_score,...}), critical_warnings, total_weighted_score[, comment]}, effectiveness: {s_method{score,max_score:2.5,...}, s_label{score,max_score:6,...}, s_trans{score,max_score:3,...}, s_time{score,max_score:3,...}, total_weighted_score}}}}`. Some models' files include `comment` in completeness/correctness; not all do.
- Scenario type (tissue_tier_code etc.) is NOT in eval records — join via `question_id` to `question_final.json` (`tissue_hierarchy_from_tissue_xlsx`, `marker_query_targets`).
- Model responses: `dataset/Q+AR/model_response/from_<model>_<shot>.json` — 13 base (n=253 except gemini-3-flash 252) + 9 RAG files (n=253) + exploratory v2/v3 variants (openai_gpt-5.2-fast KB-RAG-v2 29, KB-RAG-v3 15, qwen3-max kbrag-v1/v2 50). Base fields: `{question_id, specific_question, model_response, prompt, restrictions, shot_type}`; RAG variants add `marker_query_targets, tissue_tier_code, tissue_inferred, tissue_ri_value, rag_grounded, self_check_applied[, first_response]`.
- Human calibration: `dataset/Q+AR/result/Machine_vs_Human_Summary.json` — **240 records = 12 models × 20 scenarios** (qids '2'..'21', string ids; glm4.7-thinking not included). Fields: `{question_id, model_name, model_response, specific_question, restrictions, machine_evaluation{meta_data,scores}, human_evaluation{completeness,correctness,effectiveness,grader_name,grading_time,overall_comment,overall_total_score}}`. Plus `human_evaluation_scores.json/.csv`, `human_evaluation_user_scores.json`.
- Aggregates: `results/oeq_stats_260223.jsonl` (13 model rows, `{model_name, average_scores{c_*_norm, co_*_norm, s_*_norm}, sample_count}`), `results/mcq_stats_20260222.jsonl` (13 rows × 9 knowledge dims), `results/agreement_stats.json` (14 keys), `results/rag_baseline_summary.csv` (9 rows: model,setting,n,total_items,Com,Cor,Eff,I_A,s_method,s_label,s_trans,s_time,d_I_A,d_s_label).
- Patched-score simulations (S_label audit): `workflow/s_label_audit/simulate_evaluation_results_<model>_1-shot.tsv` (253 lines each) + `_summary.json` (13 each) — patched S_label rescoring vs stored.
- Teacher call logs: `dataset/Q+AR/logs/teacher_responses_2026-06-29.jsonl` (503), `2026-07-01.jsonl` (2,568); full raw teacher responses in `dataset/Q+AR/logs/raw/<model>_q<id>_<ts>.txt` (fields: timestamp, teacher_model, question_id, prompt_length, raw_content_path, raw_content_preview, status, detail).
- MCQ frozen outputs: `dataset/MCQ/model_response/checkpoint_<model>.jsonl` (13 models).

## Missing or conflicting files / prose-vs-code discrepancies

1. **`dataset/Q+AR/src/questions.json` does not exist**, but the docstring of `OEQ_run_grading_new.py:10` says questions are loaded from it; the code actually loads `question_final.json` (:67, :770). Stale docstring.
2. **`README.md:78-81` (repo tree) lists `results/collect_violin_data.py`, `results/plot_violin_charts.py`, `results/plot_alignment_combined.py`** — none exist in `results/` (they were moved to `archive/results/`, per archive/README.md). Actual `results/` also contains `plot_violin_and_heatmap.py`, `export_fig_data.py`, `aggregate_rag_baseline.py` which the tree omits.
3. **S_method prose vs code**: `README.md:151` describes `S_method` as "cosine similarity between the recommended method's feature vector (from `model_space.json`) and the user-preference vector". The code (`OEQ_run_grading_new.py:975-1011`) uses a **signed need-weighted fit** over `model_space_signed.json` in [−2.5, +2.5], not cosine similarity; `model_space.json` is unused for scoring. DATA_MANIFEST.md:10 already documents the signed formula — README section is stale. README.md:148 `E_score = S_method + S_label + S_trans + S_time` is still correct (weights = 1).
4. **`method_time_tau.json` is loaded but its τ values are never used**: `TIME_TAU_KB` is built (`OEQ_run_grading_new.py:700-702`) and no other read exists; S_time derives τ as 0.2×/0.1× the time_kb median (:1166, :1186-1194). README.md:154 and DATA_MANIFEST.md:45 say `method_time_tau.json` feeds `S_time` — misleading.
5. **`prompts/eval_completeness_checklist.txt` is not referenced by any code** (grep: no hits in *.py). README.md:38 lists it as a judge rubric/prompt asset. Legacy artifact.
6. **`prompts/eval_teacher_protocol_review.py` is vestigial** — loaded at `OEQ_run_grading_new.py:736-748` only to pass a non-empty guard; the file's own header says the active rubric is `eval_oeq_teacher_rubric.txt`. The docstring at `OEQ_run_grading_new.py:26` calls it "评分标准 Prompt" (stale).
7. **"372 wet-lab records + 400+ literature chunks" (DATA_MANIFEST.md:20, main.tex:73/129/215) is not verifiable from the repo**: `KnowledgeBase/article_chunk/` holds 18 files / 163 records / 659 text spans / 893 reference entries (≈"400+ chunks" only if counting references); no file with 372 records was found (dataset/MCQ/data_source xlsx total 139 data rows; time_kb has 126 rows). Possibly an external/uncommitted source; flagged as unverifiable, not reconciled.
8. **Teacher-log anomaly**: `dataset/Q+AR/logs/teacher_responses_2026-07-01.jsonl` records `deepseek-chat` (2) and `deepseek-v4-pro` (101) as teacher_model, while the canonical 13-model evaluation files' bulk (2,465 on 07-01) is `gpt-5.2`. `deepseek-v4-pro` is not in `DEFAULT_MODEL_LIST` (OEQ_run_grading_new.py:1758-1772). Likely exploratory calls; no evidence the canonical files were graded by a different teacher, but the two dates differ in volume (503 vs 2,568).
9. **`gemini-3-flash` is incomplete**: the response and evaluation files each have 252 records, qid 1 missing (verified against the data); `oeq_stats_260223.jsonl` sample_count = 251 for this model. README.md:297 table is unaffected (all other models n=253).
10. **`Machine_vs_Human_Summary.json` covers 12 models, not 13** (glm4.7-thinking absent) — consistent with compute_agreement.py's "12 models × 20 protocols" (n=240), so not an internal conflict, but note it if the paper implies 13.
11. Minor: `question_final.json` `question_id` are ints; `Machine_vs_Human_Summary.json` question_ids are strings. Eval/response files use ints. Join key types differ across artifacts.
12. README.md:43 says KnowledgeBase/ contains "7 JSON knowledge bases used by rule-based Effectiveness scoring" — the 7 listed files exist; additionally the scorer loads 2 workflow/ audit JSONs and model_space_signed.json, so the "7" is the KB inventory, not the full scorer input set (prose simplification, not an error).
13. `eval_completeness_checklist.txt` and `gen_dataset_questions_standalone.txt` (README.md:38-39) both exist; the latter is generation-only (not part of the OEQ grading path).

## Hash table (sha256) — scorer / result / prompt / data files

| File | sha256 |
|---|---|
| OEQ_run_grading_new.py | `6bb81632583d25fdc87f830969e23d4abe4f9bb15c04fcc900f2ce09a2036158` |
| build_rag_context.py | `4a8df154bbad4999e0e0afb1b8f5de1d35f6c79402cecc8fe1d7cc94a3295da9` |
| results/aggregate_oeq.py | `fbd72792d53c6fdf82a704e63295a41b3c346587f1fb758894c04032e31bc745` |
| results/calculate_main_table_score.py | `05c5375688592b061f8cb5a4a85b0be646741e58355e623782890017cbbe5608` |
| results/compute_agreement.py | `ba161cea8cb9936710ef29169bfc037dc625b23f38b36da6fe5a47cb78824166` |
| prompts/eval_oeq_teacher_rubric.txt | `9179da6b9311cd499cf14001a1135fe5026ccb140ed57e0f0fc5f7fdfe5a3572` |
| prompts/eval_completeness_checklist.txt | `48bd73ba24c45c22d9def44227bc0f5127f87ad61ca73e84201d3f9c29e8a3d2` |
| prompts/eval_teacher_protocol_review.py | `6cde886e801a10e20bf6ccbec55636ec19003c429a5c8ab8ca2ea2c94e5e1a48` |
| prompts/gen_protocol_template.py | `e9be6f85490a3fffc34027ffb90d77028f8a8f8b72cdcf514967f5b5d1281173` |
| prompts/parse_user_preference_vector.py | `f654d2d478a32c5a25328def9c13c8e1348172c28cdece2a27b2ca5dda52c5f2` |
| dataset/Q+AR/src/question_final.json | `487c62e32e7096bf5963edbbf1af8ba2fa9d5a371702675a836b309a8cecbd9b` |
| dataset/Q+AR/src/standard_response.json | `00f104b26a98457034c69ed1aebfc6807fb0add2e5ed4e74fd451a5ed3905ef4` |
| dataset/Q+AR/src/restrict.py | `169a38f554aafd1ea57a8787d8159aff8d29322432a4744f8a22b9ba85974fb9` |
| dataset/Q+AR/src/model_space_signed.json | `4db74aa19acf918d4236ba4e420356713db6ec55a396899d1e197432a256db19` |
| dataset/Q+AR/src/model_space.json | `c0290e2ba207282cb2c250a2c5776981743a034ed80affd386ef2e91c2d85e94` |
| dataset/Q+AR/src/demand_vectors_all.json | `c2e63a6f8e4e253faa76ef046128fcb194ae4a70fa07e15bc22824a0665edfea` |
| dataset/MCQ/final/all_mcq_data.jsonl | `9d403100920be87afd9e356817382fb4da8f5bf05bf80133dd677c17798de981` |
| KnowledgeBase/tissue.json | `6786bb3b94cd9f07deea0f3fc3535cb6b566c0e9f3753be6ddd978dd1629c5e8` |
| KnowledgeBase/method_fluro_compati.json | `3c1b66ad96eb46c6ab8fb01563b193ec5657fbb9b0b9de627d51b7d43b461aeb` |
| KnowledgeBase/time_kb.json | `5a7c04e3bad4963bb07f11c5675b55f2281068ea88e925f15a41715149c4ab11` |
| KnowledgeBase/method_time_tau.json | `0ddaa0672a789b7dad9d2b2e1b61452c14155e14a6de3f058bcfad5b3949913b` |
| KnowledgeBase/tissue_ri.json | `686a3f0e36cc35f33d3db64a4f06745a4b1cc5670753893c533cd998fd47852d` |
| KnowledgeBase/method_sigma_ri.json | `250c87f3a530178c9bb88b7649d99ad6969e638d0e8ae513664761ce7cc444e9` |
| KnowledgeBase/method_ri_ref.json | `fbf59e62140749ba84f740efbee8b3818550d1eab3afe6b8d290195ffaa3b332` |
| workflow/s_label_audit/marker_specificity_tiers.json | `707a9a6bd888bc0841205ed6fbb8fca6bafbc2997a6cf1014d35c0bb2c9005bf` |
| workflow/s_label_audit/fluorophore_classification_for_review.json | `9f3b908a4723f9720e7bada34e152fdd2329b225b90335e0788e3877e08e5878` |
| config/config.yaml | `78833e1bdf239d7a605b82041257d3e73278f03504e3ccb3ebf76a8de853955a` |
| config/DataSet_Config.yaml | `e30278bb3ed23e81396c4cb432731d6775287caa75526fc04b3ee9ded78e37ae` |

Note: hashes of the 13+9 evaluation JSONs and 22+ model_response JSONs are not tabulated here (25+ files); they were structurally inventoried above. If byte-level pinning of frozen outputs is needed for phase 2, hash them at that point (files are unmodified since inventory).
