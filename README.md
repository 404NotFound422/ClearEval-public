# ClearEval

ClearEval is a database-grounded benchmark for evaluating large language
models on tissue optical clearing (TOC). It measures static domain knowledge
with multiple-choice questions (MCQs) and the feasibility of generated wet-lab
protocols with open-ended questions (OEQs).

This anonymized artifact contains the released benchmark data, scoring
knowledge bases, model outputs, evaluation code, and aggregate results. It does
not contain manuscript sources, publication figures, submission material,
credentials, local environments, or superseded dataset-construction files.

## Benchmark overview

- **Knowledge track (MCQ):** 2,588 questions covering named entities, domain
  knowledge, and task scenarios. The released evaluation split contains 768
  questions.
- **Application track (OEQ):** 253 experiment-design scenarios requiring a full
  tissue-clearing protocol. Protocols are evaluated with the CCE framework:
  Completeness, Correctness, and Effectiveness.

Completeness and Correctness use a fixed LLM-judge rubric. Effectiveness is
computed from deterministic checks of method suitability, label compatibility,
refractive-index matching, and timing plausibility.

The aggregate indices are:

```text
I_K = mean(Tissue, Reagent, Method)
I_A = min(Completeness, Correctness, Effectiveness)
H_KA = 2 * I_K * I_A / (I_K + I_A)
```

## Repository layout

```text
.
|-- README.md
|-- requirements.txt
|-- OEQ_run_grading_new.py
|-- build_rag_context.py
|-- extract_clearing_time.py
|-- compare_teacher_model.py
|-- models/                         # Model-provider wrappers
|-- prompts/                        # Generation and judge prompts
|-- KnowledgeBase/
|   |-- article_chunk/              # Curated literature evidence
|   |-- tissue.json
|   |-- method_fluro_compati.json
|   |-- tissue_ri.json
|   |-- method_ri_ref.json
|   |-- method_sigma_ri.json
|   |-- time_kb.json
|   `-- method_time_tau.json
|-- dataset/
|   |-- MCQ/
|   |   |-- final/                  # Full dataset and evaluation split
|   |   `-- model_response/         # 13 evaluated model checkpoints
|   `-- Q+AR/
|       |-- src/                    # 253 OEQ scenarios and scoring metadata
|       |-- model_response/         # Generated protocols
|       `-- result/                 # CCE evaluation records
`-- results/                        # Aggregation scripts and released outputs
```

## Data inventory

### MCQ dataset

[`dataset/MCQ/final/all_mcq_data.jsonl`](dataset/MCQ/final/all_mcq_data.jsonl)
contains 2,588 questions:

| Category | Count |
| --- | ---: |
| Named Entity Recognition | 533 |
| Domain Knowledge Evaluation | 1,350 |
| Task Scenario Questions | 705 |
| **Total** | **2,588** |

[`dataset/MCQ/final/development.jsonl`](dataset/MCQ/final/development.jsonl)
is the 768-question evaluation split. Each checkpoint in
[`dataset/MCQ/model_response/`](dataset/MCQ/model_response/) contains one
response per question in that split. Intermediate source tables, draft splits,
and exploratory MCQ analysis files are intentionally excluded to keep the
released data boundary unambiguous.

This artifact supports inspection and aggregation of the released MCQ
responses. It does not include a standalone MCQ inference driver.

### OEQ dataset

[`dataset/Q+AR/src/question_final.json`](dataset/Q+AR/src/question_final.json)
contains 253 open-ended protocol-design scenarios. Each record includes the
tissue tier, inferred tissue label, and marker or target requirements used by
the deterministic Effectiveness scorer.

The current question stems and allowed-marker list were revised on 2026-09-13.
All 253 question IDs are preserved. See the
[revision record and before/after comparison](dataset/Q+AR/revisions/2026-09-13-stem-fixes/README.md)
for the changes, original snapshots, source references, and validation.
Released model responses and scores still correspond to the earlier inputs;
use a separate output directory for runs on the revised dataset.

### Scoring knowledge bases

| File | Purpose |
| --- | --- |
| `tissue.json` | Target-to-marker and fluorophore compatibility |
| `method_fluro_compati.json` | Fluorophore-to-method compatibility |
| `tissue_ri.json` | Tissue refractive-index references |
| `method_ri_ref.json` | Method refractive-index references |
| `method_sigma_ri.json` | Method-by-tier RI tolerance values |
| `time_kb.json` | Feasible method-by-tier timing intervals |
| `method_time_tau.json` | Timing sensitivity coefficients |

The seven scoring knowledge bases are accompanied by 18 method-level JSON files
under [`KnowledgeBase/article_chunk/`](KnowledgeBase/article_chunk/) containing
the curated literature evidence used for grounding.

### Wet-lab source-data boundary

The released `time_kb.json` and `time_kb.xlsx` contain 126 expert-reviewed
method-by-tier timing rows derived from 372 wet-lab records. The sample-level
372-record source table was not present in the source repository used to build
this artifact and is therefore not included.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

Inference requires model-provider credentials. Create `config/config.yaml`
locally and add the model definitions and API credentials required for your
run. This untracked local file is not part of the artifact.

No credentials are required to inspect the released datasets or rerun the
aggregation scripts against the included model outputs.

## OEQ generation and grading

Run commands from the repository root:

```bash
# Generate protocols for the revised questions without grading
python OEQ_run_grading_new.py --no-evaluation

# Grade included generations against their original question snapshot
python OEQ_run_grading_new.py --eval-only --question-file dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json --response-dir dataset/Q+AR/model_response --score-dir dataset/Q+AR/result_scoring_v2
```

Useful options include `--models`, `--teacher`, `--eval-concurrency`,
`--gen-concurrency`, `--shot-types`, `--qids`, and `--limit`.
New outputs default to `dataset/Q+AR/model_response_scoring_v2/` and
`dataset/Q+AR/result_scoring_v2/`. Version manifests prevent incompatible resumes.

The fixed demand table is bound to the original question snapshot. Scoring the
revised questions requires audited demand vectors and a matching manifest;
reusing the old binding fails before model calls. See the
[scoring repair notes](docs/scoring_repair_v2.md) for formulas, scope, and commands.

### Inference-time grounding baseline

```bash
python build_rag_context.py
python build_rag_context.py --check-leakage
```

Context cards are generated from scenario metadata only. They do not depend on
the output of the model being evaluated.

## Reaggregating released scores

The following commands use the included model outputs and do not call external
model APIs:

The OEQ aggregate now averages the per-protocol minimum. Outputs use new
`*_scoring_v2` filenames; archived paper tables retain their original values.
Reaggregation does not rerun the teacher or change individual scores.

```bash
# Aggregate the 13 base one-shot runs
python results/aggregate_mcq.py
python results/aggregate_oeq.py

# Recompute judge-versus-human agreement
python results/compute_agreement.py

# Print the combined benchmark scores
python results/calculate_main_table_score.py

# Recompute the inference-time grounding summary
python results/aggregate_rag_baseline.py
```
The default OEQ assessment mode is `benchmark`. It writes checked numerical estimates and retains scientific validation as `UNRESOLVED`; the current-question demand projection is explicitly uncalibrated. A valid explicit unknown becomes a completed `BENCHMARK_UNRESOLVED` record, contributes to the coverage denominator, and is not replaced with zero. Use `--assessment-mode grounded` for source-bound requirement diagnoses and `--assessment-mode legacy` for historical diagnostics. Fixed historical demand vectors require a matching question snapshot. Keep a new score directory when changing the assessment contract.


## Validation status

The repeat-grading pilot and its collection safeguards are documented in
[docs/judge_blind_pilot.md](docs/judge_blind_pilot.md). The current scoring contract
is `cleareval-fixed-demand-v4-marker-identity`, which also records a source-backed
MECA-79/PNAd target-recognition rule. Scoring versions and archived outputs remain
separate; repeatability does not establish scientific validity.

The reduced artifact is checked before publication for JSON/JSONL validity,
Python syntax, MCQ checkpoint coverage, deterministic aggregate reproduction,
broken documentation links, sensitive strings, and unexpected generated or
cache files.

## Anonymity and licensing

This artifact is provided for double-blind academic review. Author,
affiliation, contact, and formal citation information are intentionally
withheld. Please do not attempt to identify the authors.

No open-source license is granted by this review snapshot. A license and formal
citation will be added to the final public release.
