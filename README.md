# ClearEval

**ClearEval** is a benchmark for evaluating Large Language Models (LLMs) on **tissue optical clearing** — the experimental discipline of rendering biological tissue transparent for volumetric fluorescence imaging. The benchmark is **dual-track**:

- **Track 1 — Multiple-Choice Questions (MCQ):** 2,588 questions probing factual and structured domain knowledge (entity recognition, reagent/method/tissue facts, and task-scenario reasoning).
- **Track 2 — Open-Ended Questions (OEQ):** 253 realistic experiment-design scenarios. Models must produce a full clearing **protocol**, which is then scored under the **CCE framework** — **C**ompleteness, **C**orrectness, and **E**ffectiveness.

Standard text-overlap metrics (BLEU, ROUGE) cannot judge whether a proposed wet-lab protocol is *physically feasible*. ClearEval instead combines an instruction-tuned **LLM-as-a-Judge** (for Completeness and Correctness) with **rule-based, physics-grounded scoring** (for Effectiveness), the latter computed against curated knowledge bases of reagent/method/tissue properties.

---

## Repository structure

```
.
├── OEQ_run_grading_new.py        # OEQ track: end-to-end generation + grading entry point
├── MCQ_async_test.py             # MCQ track: async inference harness
├── compare_teacher_model.py      # Judge-model agreement / comparison utilities
├── extract_clearing_time.py      # Helper: extract clearing-time fields from protocols
│
├── config/
│   ├── config.yaml               # Model roster + per-model API settings (no secrets committed)
│   ├── DataSet_Config.yaml       # Dataset registration for the loader
│   └── config_dataset_generate.py
│
├── models/                       # LLM client wrappers (one module per backend)
│   ├── Base_Models.py
│   ├── Model_Loader.py
│   ├── OpenAI_Model.py
│   ├── Gemini_Model.py
│   ├── GLM_Model.py
│   ├── Custom_LLM.py
│   ├── Huggingface_LLM.py
│   └── Ollama_LLM.py
│
├── prompts/                      # Judge rubrics and generation prompt templates
│   ├── eval_oeq_teacher_rubric.txt
│   ├── eval_completeness_checklist.txt
│   ├── gen_dataset_questions_standalone.txt
│   ├── gen_protocol_template.py
│   └── parse_user_preference_vector.py
│
├── KnowledgeBase/                # 7 JSON knowledge bases used by rule-based Effectiveness scoring
│   ├── tissue.json
│   ├── method_fluro_compati.json
│   ├── tissue_ri.json
│   ├── method_ri_ref.json
│   ├── method_sigma_ri.json
│   ├── time_kb.json
│   └── method_time_tau.json
│
├── dataset/
│   ├── Dataset_Loader.py
│   ├── dataset_generater.py
│   ├── MCQ/
│   │   ├── final/                # all_mcq_data.jsonl (2,588), development.jsonl, validation.jsonl
│   │   ├── data_source/          # source spreadsheets (reagent / tissue / dyes)
│   │   ├── model_response/       # per-model MCQ answer checkpoints
│   │   ├── format_dataset_all_in_one_jsonl.py
│   │   ├── metric_of_MCQs_gen_from_jsonl.py
│   │   ├── metric_of_MCQs_per_question_gen_from_jsonl.py
│   │   └── ring_map_gen_from_jsonl.py
│   └── Q+AR/                      # OEQ track ("Question + Auto-Rubric")
│       ├── src/
│       │   ├── question_final.json   # 253 OEQ scenarios + per-question metadata
│       │   ├── model_space.json      # method feature-vector space (Effectiveness S_method)
│       │   ├── standard_response.json
│       │   └── restrict.py
│       ├── model_response/       # generated protocols: from_<model>_<shot>.json
│       └── result/               # graded output: evaluation_results_<model>_<shot>.json
│
└── results/                      # Aggregation, scoring tables, and figures
    ├── aggregate_mcq.py
    ├── aggregate_oeq.py
    ├── calculate_main_table_score.py
    ├── compute_agreement.py
    ├── generate_latex_rows.py
    ├── collect_violin_data.py
    ├── plot_violin_charts.py
    ├── plot_combined_radar.py
    └── plot_alignment_combined.py
```

---

## Data card

### MCQ track (`dataset/MCQ/final/all_mcq_data.jsonl`, 2,588 items)

| Category | Count |
| --- | ---: |
| Named Entity Recognition | 533 |
| Domain Knowledge Evaluation | 1,350 |
| Task Scenario Questions | 705 |
| **Total** | **2,588** |

Each MCQ record contains: `question_id`, `question`, `options`, `answers`, `answer_index`, `category`, `knowledge_point`, and `specific`. The pre-split `development.jsonl` and `validation.jsonl` files are also provided.

### OEQ track (`dataset/Q+AR/src/question_final.json`, 253 scenarios)

253 open-ended experiment-design prompts. Each scenario carries the metadata used by the rule-based Effectiveness scorer, including the tissue tier code (`T01`–`T12`), an inferred tissue label, and the marker/target requirements for the question.

### Knowledge bases (`KnowledgeBase/`, 7 JSON files)

| File | Contents | Used by |
| --- | --- | --- |
| `tissue.json` | Marker-site × fluorophore compatibility matrix + category labels | `S_label` |
| `method_fluro_compati.json` | Fluorophore × clearing-method compatibility (0–1) | `S_label` |
| `tissue_ri.json` | Tissue type → intrinsic refractive index | `S_trans` |
| `method_ri_ref.json` | Clearing method → reference-sample RI (with citations) | `S_trans` |
| `method_sigma_ri.json` | (method × tier) → RI tolerance bandwidth σ | `S_trans` |
| `time_kb.json` | (method × tier) → feasible clearing-time interval [min, median, max] | `S_trans` gate + `S_time` |
| `method_time_tau.json` | (method × tier) → time-sensitivity coefficient τ | `S_time` |

---

## The CCE scoring framework (OEQ)

Each generated protocol is mapped onto three dimensions:

**Completeness (Structural Integrity).** A form check verifying that the protocol contains all structured information needed to reproduce the experiment — required procedural steps (pre-processing/fixation, core clearing, labeling) and parametric granularity (explicit reagent identities, concentrations, and numerical time/temperature values rather than vague descriptions). Scored by the LLM judge against a graded rubric.

**Correctness (Scientific Validity).** Detects fatal errors that violate domain consensus or physical law — step ordering, reagent/method chemical consistency, and physical plausibility of key parameters (e.g., diffusion-time sanity per Fick's law). Scored by the LLM judge.

**Effectiveness (Quantitative Feasibility).** A deterministic, rule-based score computed from the knowledge bases:

```
E_score = S_method + S_label + S_trans + S_time
```

- **`S_method`** — cosine similarity between the recommended method's feature vector (from `model_space.json`) and the user-preference vector parsed from the question.
- **`S_label`** — a hard "weakest-link" minimum over target match, marker–fluorophore compatibility, and fluorophore–method compatibility (`tissue.json`, `method_fluro_compati.json`).
- **`S_trans`** — a Gaussian RBF on method–tissue refractive-index domain matching, gated by method/tier support (`tissue_ri.json`, `method_ri_ref.json`, `method_sigma_ri.json`, `time_kb.json`).
- **`S_time`** — a Gaussian decay penalizing predicted clearing times that fall outside the feasible interval for the method/tissue tier (`time_kb.json`, `method_time_tau.json`).

The LLM judge supplies the structured `extraction` fields (method name, marker dictionary, clearing time) that drive the rule-based scores; question-level metadata (tier code, tissue label, target markers) comes directly from the dataset and does not depend on the model under test.

---

## Setup

```bash
pip install -r requirements.txt
```

Configure the model roster and API credentials in `config/config.yaml` (no credentials are committed to this repository — add your own). All commands below are run from the repository root.

---

## Running the OEQ track

The OEQ pipeline (protocol generation + CCE grading) is driven by a single entry point:

```bash
# Full run: generate protocols for the configured models, then grade them
python OEQ_run_grading_new.py

# Grade only, using existing generations in dataset/Q+AR/model_response/
python OEQ_run_grading_new.py --eval-only

# Generate only (skip grading)
python OEQ_run_grading_new.py --no-evaluation

# Restrict to specific models
python OEQ_run_grading_new.py --eval-only --models <model_a> <model_b>

# Choose the judge ("teacher") model and per-model grading concurrency
python OEQ_run_grading_new.py --eval-only --teacher <judge_model> --eval-concurrency 8
```

Key CLI options:

| Option | Default | Description |
| --- | --- | --- |
| `--models` | all configured | Restrict to specific model names (must exist in `config/config.yaml`) |
| `--shot-types` | `1-shot` | Which shot setting(s) to run |
| `--teacher` | judge model in code | Judge ("teacher") model used for Completeness/Correctness + extraction |
| `--eval-concurrency` | `4` | Concurrent questions graded per model |
| `--gen-concurrency` | `4` | Concurrent generations per model |
| `--eval-only` | off | Skip generation; grade existing responses |
| `--no-evaluation` | off | Generate only; skip grading (mutually exclusive with `--eval-only`) |

**Outputs.** Generations are written to `dataset/Q+AR/model_response/from_<model>_<shot>.json`; graded results to `dataset/Q+AR/result/evaluation_results_<model>_<shot>.json`. Results are written incrementally (atomic replace) per question, so an interrupted run resumes by skipping already-graded `question_id`s.

Each graded record stores the per-dimension breakdown (`completeness`, `correctness`, `effectiveness`) with sub-scores and judge reasoning, plus audit fields tracing each rule-based Effectiveness sub-score.

---

## Running the MCQ track

MCQ model responses are stored per model under `dataset/MCQ/model_response/` (one checkpoint file per model), and the evaluated dataset lives in `dataset/MCQ/final/`. Async inference is orchestrated by `MCQ_async_test.py`. Dataset statistics (token-length distributions, per-category breakdowns) can be regenerated with:

```bash
python dataset/MCQ/metric_of_MCQs_gen_from_jsonl.py
python dataset/MCQ/metric_of_MCQs_per_question_gen_from_jsonl.py
```

---

## Aggregation and final scores

The `results/` scripts turn raw per-model outputs into the reported tables and figures:

```bash
# Aggregate MCQ accuracy per knowledge dimension
python results/aggregate_mcq.py

# Aggregate OEQ scores (normalized per CCE sub-dimension)
python results/aggregate_oeq.py

# Combine into the main results table
#   Knowledge index  I_K  (from MCQ)
#   Application index I_A  (from OEQ: Completeness / Correctness / Effectiveness)
#   Total = harmonic mean: 2 * I_K * I_A / (I_K + I_A)
python results/calculate_main_table_score.py

# Judge/human agreement statistics
python results/compute_agreement.py

# Figures
python results/plot_combined_radar.py
python results/plot_violin_charts.py
python results/plot_alignment_combined.py
```

Some aggregation scripts contain a default input filename near the top of the file; adjust it to point at your own run before executing.

---

## License and citation

This repository is released for academic peer review under **double-blind anonymity**. Author, affiliation, and contact information, as well as the formal citation, are intentionally withheld during the review period and will be added in the camera-ready release.

> **Anonymized note:** Please do not attempt to de-anonymize the authors. A license and a BibTeX citation entry will be provided upon publication.
