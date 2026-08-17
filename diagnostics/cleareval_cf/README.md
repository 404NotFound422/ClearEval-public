# ClearEval counterfactual-validity overlay

An isolated, stdlib-only, offline-capable diagnostic suite that validates the
ClearEval OEQ evaluator through **locally generated counterfactual protocol
pairs** (Task 1 seed selection, Task 2 mutation proposals, Task 3 judge
validity / role-blind audit / metrics). Everything lives under
`diagnostics/cleareval_cf/` and `tests/diagnostics/cleareval_cf/`; **no
production file is modified.**

- Task 1 — `seed_selector.py`: 24 question×model seeds, 16 development / 8
  blind split.
- Task 2 — `mutation_registry.py`, `mutation_builder.py`,
  `mutation_validator.py`: 72 span-level counterfactual proposals (24
  EQUIVALENT + 48 degrading, exactly 8 per family), Gold-guarded, split-aware.
- Task 3 — `run_original_cce.py` (read-only CCE adapter + aggregation
  verification), `run_diagnostic_audit.py` (role-blind audit runner + split /
  freeze guard), `score_counterfactual_relations.py` (metrics 9.1-9.7),
  `report_judge_validity.py` (reports + review package + GO/NO-GO), plus the
  `prompts/diagnostic_audit_v1.txt` judge prompt.

## Non-negotiables (boundaries this suite enforces)

1. **Offline, stdlib-only, deterministic.** No network in any test; the online
   teacher path is isolated (`online_cce.py`, `online_audit.py`) and never
   imported by tests.
2. **No production edits.** `OEQ_run_grading_new.py`, `results/`, `prompts/`,
   `dataset/`, `KnowledgeBase/` are only *read* (hash-pinned where relevant).
   The CCE adapter is a read-only re-derivation that documents exactly what is
   reused (KB files, `extract_clearing_time.py`, overlay extractors) vs
   re-implemented (the production effectiveness formulas, mirrored from
   `OEQ_run_grading_new.py`).
3. **The judge is role-blind.** A DiagnosticAudit call sees only
   `question_text` + ONE protocol text — never a pair, mutation family,
   expected relation, or label. Original and mutated are always scored in fully
   independent calls with no shared state.
4. **Metadata on every run.** scoring/audit rows carry teacher model, prompt
   file path + sha256, operator/schema version, timestamp, input sha256.
5. **No silent exclusion/imputation.** Missing, failed, or unscored cases are
   reported in the 9.7 coverage section of every report; no number is
   fabricated and no score is filled in.
6. **No new ClearEval total score.** The overlay never introduces a Total
   score; the paper-adjacent claim is scoped to evaluator validation
   (see `reports/PAPER_METHODS_TEXT.md`).
7. **Gold discipline.** Nothing fabricates `APPROVED_GOLD`; expert gold flows
   PENDING_REVIEW -> two reviewers -> adjudication -> APPROVED_GOLD
   (`reviewed_gold.jsonl` is currently empty = no gold yet).

## Directory map

```
diagnostics/cleareval_cf/
├── schemas.py               Task 1 contracts (enums, records, JSONL, guard errors)
├── seed_selector.py         seed selection + split + DATA_SUMMARY + split guard
├── mutation_registry.py     split-aware, Gold-guarded proposals gateway
├── mutation_builder.py      deterministic span operators -> 72 proposals
├── mutation_validator.py    manifest validation -> MUTATION_VALIDATION.md
├── review_gold.py           GoldReview schema + assemble from review packages
├── run_original_cce.py      read-only CCE adapter + --verify-aggregation
├── online_cce.py            --online teacher path (never imported by tests)
├── online_audit.py          --online DiagnosticAudit teacher path (never in tests)
├── run_diagnostic_audit.py  role-blind auditor + split/freeze guard
├── score_counterfactual_relations.py   9.1-9.7 estimators (stdlib)
├── report_judge_validity.py reports + review package + GO/NO-GO
├── prompts/diagnostic_audit_v1.txt     the DiagnosticAudit judge prompt
├── manifests/
│   ├── seed_candidates.jsonl           24 seeds
│   ├── split_manifest.json             development/blind + frozen_prompt_sha256 (null)
│   ├── mutation_proposals.jsonl        blind-scope artifact: 72 proposals
│   ├── mutation_proposals_development.jsonl  dev-scope build (48) for dev runs
│   ├── reviewed_gold.jsonl             empty stub = no gold yet
│   ├── review_package.jsonl            72 rows with empty expert labels
│   ├── dev_audit_runs.jsonl            pending-state dev audit judge calls (48x2)
│   ├── dev_cce_scores.jsonl            pending-state dev CCE scores (48x2)
│   └── dev_reviewed_gold.jsonl         empty stub for the dev-scoped build (the
│                                       committed reviewed_gold.jsonl is never touched)
│   (run_diagnostic_audit's defaults audit_runs.jsonl / cce_scores.jsonl are
│    written only when it is invoked directly with --audit-runs/--cce-scores)
├── reports/                 DATA_SUMMARY / MUTATION_BUILD / MUTATION_VALIDATION /
│                            AGGREGATION_VERIFICATION / JUDGE_VALIDITY / BLIND_RESULTS /
│                            GO_NO_GO / PAPER_*  (VALIDITY_METRICS.json is written only
│                            when score_counterfactual_relations.py is invoked as a CLI)
└── .sdd/                    task-1/2/3 reports
tests/diagnostics/cleareval_cf/   test_schemas / test_seed_selection /
                                  test_mutations / test_runners_and_scoring
```

## How to run

Offline (no network). From the repo root with the conda `YWB` env:

```
python -m unittest discover -s tests -t .          # full suite (Task 1+2+3)

# Task 1
python -m diagnostics.cleareval_cf.seed_selector

# Task 2
python -m diagnostics.cleareval_cf.mutation_builder --role blind
python -m diagnostics.cleareval_cf.mutation_validator

# Task 3 -- verify production aggregation is unchanged (exact fixture-equivalence)
python -m diagnostics.cleareval_cf.run_original_cce --verify-aggregation

# Task 3 -- pending reports + review package
python -m diagnostics.cleareval_cf.report_judge_validity
```

Online (manual only; requires the configured teacher / API keys; NEVER run in
tests):

```
python -m diagnostics.cleareval_cf.run_diagnostic_audit --split development --online --fixtures <path>
python -m diagnostics.cleareval_cf.run_original_cce --online ...
```

## Review workflow (gold)

1. `manifests/review_package.jsonl` — one row per pair (72), programmatic
   expectation pre-filled, **expert label fields empty**.
2. Two independent experts fill separate copies (`reviewer_A_*` /
   `reviewer_B_*` columns, or split into two files) covering:
   seed suitable for local counterfactual testing? / mutation scientifically
   valid? / expected_relation / affected CCE component / violation location /
   hard-fail status / minimal next action / supporting rule or evidence.
3. Adjudication resolves disagreements; the adjudicated rows become
   `reviewed_gold.jsonl` (via `review_gold.assemble_gold` + registry
   `promote_to_gold`), status `APPROVED_GOLD` with reviewer ids + gold note.
4. `score_counterfactual_relations.py` then turns gold into 9.3/9.4/9.5
   statistics; 9.5 (judge-expert agreement) also computes raw agreement +
   Cohen's kappa / weighted kappa / Krippendorff alpha **when two expert label
   files exist** (that is the documented hook -- the tool does not guess the
   second expert).

## Split / freeze protocol

- Seeds are split 16 development / 8 blind at selection time
  (`split_seed 20260817`); development-role tooling can never see blind pairs
  (`BlindSplitAccessError`).
- The DiagnosticAudit prompt is versioned (`prompts/diagnostic_audit_v1.txt`,
  header `diagnostic_audit_v1`). Running the **blind** split requires
  `split_manifest.frozen_prompt_sha256` to be set: run
  `run_diagnostic_audit --split blind --freeze-prompt` first. This is the
  single-revision freeze so no prompt tuning happens after blind results.
- Development runs may iterate on the prompt freely; blind runs record the
  frozen prompt sha256 on every row.

## Scientific-claim statement

The paper-adjacent artefacts (PAPER_METHODS_TEXT.md / PAPER_LIMITATIONS_TEXT.md
/ PAPER_TABLE / PAPER_FIGURE) make exactly this claim and no more:

> "ClearEval does not require a unique reference protocol text, but its
> evaluator is designed to be validated against expert-reviewed local
> counterfactual relations, evidence-backed constraints, and blind test
> cases. Validation results are pending expert review of the counterfactual
> review package and a role-blind judge run."

No laboratory validation is claimed; no new ClearEval total score is
introduced; the limitations section records the pending expert review, the
frozen-data eligibility-pool skew (documented in the Task 1 report), and the
deterministic-effectiveness re-derivation divergence (including that the
seeded originals' effectiveness is re-derived and can diverge from the frozen
totals).

## Current state

`GO_NO_GO.md` = **LIMITED**: no expert-reviewed gold (0 rows), no judge runs
(all audit judges pending), no blind results. The verdict is recomputed after
the blind run; no prompt tuning after blind results.

## Tests

`python -m unittest discover -s tests -t .` runs the full Task 1+2+3 suite
offline (119 tests: Task 1 seed/selection 55, Task 2 mutations 23, Task 3
runners/metrics/reports 41). pytest is installed in the conda env but its
environment is broken (opentelemetry import error), so unittest is used.
