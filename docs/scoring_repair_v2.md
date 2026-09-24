# OEQ scoring repair, first batch

This update removes inconsistent score computation and reporting while retaining
the archived generations, individual evaluations, and published tables.

## Scoring and reporting contract

`OEQ_run_grading_new.py` reads demand vectors from a fixed table. The adjacent
`demand_vectors_all.json.manifest.json` binds that table to the pre-2026-09-13
question snapshot by canonical JSON SHA-256 (`evaluation_contract.json_hash`),
so JSON whitespace and checkout line endings do not invalidate it. The binding freezes existing data; it does not
establish expert validity of the vectors. Revised questions need audited vectors
and a new manifest with `hash_format: canonical-json-sha256-v1`,
`questions_sha256`, and `demand_vectors_sha256`.

Before a teacher call, the question text must match that snapshot. Metadata
backfilling uses the same snapshot. The score stores the demand vector, extraction,
quantitative inputs, actual evaluation timestamp, and scoring version. Checkpoints
also record hashes of responses, rubric, scoring code, and active knowledge bases.
Changed inputs require a new output directory instead of reusing cached scores.

Time scoring and its explanation now come from one function in
`evaluation_contract.py`. The explanation records the actual KB window, median,
requested/resolved sample tier, deviation, and tolerance. The historical numerical
rule is retained:

```text
delta = max(t_min - t_actual, t_actual - t_max, 0)
tau = 0.10 * median if t_actual > t_max else 0.20 * median
S_time = 3 * exp(-0.5 * (delta / tau)^2)
```

Missing/invalid extracted time and missing KB data retain the previous zero-score
convention, but have separate status labels. They are not evidence of experimental
failure. The discrepancy with a symmetric-tolerance manuscript description remains
a scientific reporting decision; this patch does not silently change that policy.

All OEQ reporting now uses `results/oeq_metrics.py`:

```text
Com_i = 0.4 * c_step_i / 2 + 0.6 * c_param_i / 3
Cor_i = mean(co_order_i / 3, co_method_i / 2, co_param_i / 2, co_chem_i)
Eff_i = mean((s_method_i / 2.5 + 1) / 2, s_label_i / 6, s_trans_i / 3, s_time_i / 3)
I_A = mean_i(min(Com_i, Cor_i, Eff_i))
```

Only complete, finite, in-range score records enter these means. Failed/partial
records remain visible in coverage and exclusion counts. Duplicate question IDs
are excluded, including every copy. `coverage` means valid records divided by
records present in the input file; it cannot detect an entirely absent question
without a dataset roster. Check coverage against the expected 253 questions for a
full run. The archived Gemini-3-Flash base file has 252 records, of which 251 are
valid; this is not full benchmark coverage.

`I_A_min_of_means` preserves the old aggregation as an explicit diagnostic.
RAG deltas use common valid question IDs and reject known question-text/version
mismatches. Main-table and LaTeX exporters share the same loader; legacy aggregate
files are rejected because a mean of per-question minima cannot be reconstructed
from three overall means.

## Offline checks and reaggregation

Run from the repository root with Python 3.9 or newer. These commands need only
the Python standard library and do not call a model API:

```bash
python -m unittest discover -s tests -v
python results/aggregate_oeq.py --output results/oeq_stats_scoring_v2.jsonl
python results/calculate_main_table_score.py --oeq-file results/oeq_stats_scoring_v2.jsonl
python results/generate_latex_rows.py --oeq-file results/oeq_stats_scoring_v2.jsonl
python results/aggregate_rag_baseline.py --csv results/rag_baseline_summary_scoring_v2.csv
```

These commands reaggregate the saved scores. They do not apply the fixed-demand
scorer to the historical records. Keep that distinction in experimental reports.

## Regrading existing answers

The following command uses the configured teacher API and the original question
snapshot. It writes new evaluations and leaves archived evaluations intact:

```bash
python OEQ_run_grading_new.py --eval-only --models openai_gpt-5.2-fast --shot-types 1-shot 1-shot+KB-RAG 1-shot+KB-RAG+self-check --question-file dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json --response-dir dataset/Q+AR/model_response --score-dir dataset/Q+AR/result_scoring_v2 --qids 5 6 7
```

Remove `--qids` for the full dataset after the pilot is checked. Full API grading
still requires the dependencies in `requirements.txt` and local model configuration.
The new default scorer intentionally refuses the revised question file with the
old demand binding. Do not update only a hash to bypass this: first audit the
vectors against the revised scientific requirements.

## Remaining scientific work

This batch addresses fixed demands, time-score traceability, aggregation, and
cache versioning. Teacher extraction and completeness/correctness judgments still
vary between calls. The prompt example, RAG evidence consistency, required-target
coverage in label scoring, and pairing self-check with the same initial answer
need the next experimental revision. The score repair alone does not establish
that RAG or self-check improves biological protocol validity.
