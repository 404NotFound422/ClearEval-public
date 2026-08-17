# Task 3 Report -- final implementation: judge validity + role-blind audit +
# metrics + reports (counterfactual-validity overlay)

Status: **DONE** (current state = pending-data; verdict LIMITED as required)

Date: 2026-08-17. Branch: `cleareval-cf-validity`. Python 3.12 (conda `YWB`),
Windows + Git Bash. Work is isolated under `diagnostics/cleareval_cf/` and
`tests/diagnostics/cleareval_cf/`; **no production file was modified** (git
status shows only previously-untracked files; no commits made).

## 1. Approach

1. **Read production path first.** Confirmed the frozen scorer contract:
   `OEQ_run_grading_new.py` computes rule-based Effectiveness at import-loaded
   KBs, with Completeness/Correctness from the teacher
   (`openai_gpt-5.2-thinking`, model `gpt-5.2`, rubric
   `prompts/eval_oeq_teacher_rubric.txt`); tested whether importing the
   production module was practical (it is not: heavy import-time side effects --
   API SDK/config/KB loads -- and it stalled on ModelLoader imports), so the
   adapter is the task-sanctioned *read-only re-derivation* that calls
   production functions where possible and documents REUSE vs
   RE-IMPLEMENTATION precisely (run_original_cce.py module docstring).
2. **Read-only CCE adapter** (`run_original_cce.py`): KB loader mirroring the
   production import-time loads; faithful re-implementation of
   `calculate_effectiveness_score` + helpers (cited per function); deterministic
   extraction (method/time/marker_dict) with documented divergences; frozen
   production records consumed wholesale for seeded originals; canonical CCE
   record + strict judge-payload validation; `--verify-aggregation` re-runs the
   `results/aggregate_oeq.py` formula and compares with
   `results/oeq_stats_260223.jsonl`.
3. **Role-blind audit runner** (`run_diagnostic_audit.py`): two fully
   independent judge calls per pair (original / mutated), prompt = question +
   ONE protocol; offline fixture judge (can inject findings + C+C payloads),
   online teacher judge (lazy, never in tests); per-call metadata everywhere;
   split/freeze guard for blind.
4. **Metrics** (`score_counterfactual_relations.py`): stdlib estimators for
   9.1-9.7, component-aware, floor-aware, empty→pending safe;
   `review_gold.py` defines the GoldReview schema without touching Task 1
   `schemas.py`.
5. **Reports** (`report_judge_validity.py`): renders pending-state reports,
   paper CSVs, review package; GO/NO-GO verdict function with the documented
   rule; scientific claim exactly as specified.
6. **Tests** (`test_runners_and_scoring.py`) + full suite run; real reports
   regenerated in their pending-data state.

## 2. Key decisions (all documented in code)

1. **REUSE vs RE-IMPLEMENTED (adapter, documented)**:
   - REUSED read-only: the 8 KB files + `model_space_signed.json`,
     `demand_vectors_all.json`, `question_final.json`, the workflow audit JSONs,
     plus the repo's own `extract_clearing_time.py` and the overlay's
     `stated_method` / marker·dye lexicons.
   - RE-IMPLEMENTED (faithful copies, cited to production lines): the
     effectiveness stack (`calculate_effectiveness_score`, `find_signed_method`,
     `calculate_method_suitability`, marker/fluor matching, `_time_kb_row` with
     T07/T11 parent fallback, `_resolve_tissue_ri`). Offline path is stdlib;
     `--online` lazily imports `models.Model_Loader` and is never run by tests.
2. **Symmetric operational scoring.** Both sides of a pair are scored through
   the SAME local pipeline so the counterfactual delta is like-with-like;
   frozen production records are a separately reported calibration anchor and,
   for seeded *originals*, the source of the judge (Completeness/Correctness)
   payload. Verified empirically: 24/24 EQUIVALENT pairs produce **0 spurious
   changes** in the local effectiveness (metamorphic property backing 9.2).
3. **Documented divergences of the local re-derivation** (method_name from
   deterministic extractor, per-question `demand_vectors_all.json` preference
   vector, deterministic marker_dict / clearing-time) -- absolute values for
   mutated texts are not production-identical; directionality is the target.
4. **Component-aware, floor-honest metrics.** 9.1 credits a degrading pair when
   the expected CCE component decreased *or* the judge returned HARD_FAIL;
   components already at their deterministic floor are counted separately as
   "undetected (floor)" and never credited. 9.4 (fatal false-PASS) is defined
   over gold HARD_FAIL; 9.2 derives invariance tolerance empirically (95th
   percentile of the |repeat-first| distribution, documented estimator, no
   fixed epsilon); 9.7 enumerates every missing/failed/unscored case.
5. **Metadata contract.** Every audit row and every CCE row carries teacher
   model, prompt file path + sha256, schema version, mutation-operator version,
   timestamp, and input sha256; repeated runs preserve them (tested).
6. **Split/freeze guard.** `--split development` refuses blind content
   (`BlindSplitAccessError`); `--split blind` requires
   `split_manifest.frozen_prompt_sha256` (single-revision freeze via
   `--freeze-prompt`, which writes the current `diagnostic_audit_v1.txt`
   sha256); the runner records the prompt sha256 on every row. The committed
   `split_manifest.json` stays unfrozen (no ad-hoc freeze).
7. **GO/NO-GO rule** (documented in file): SUPPORTED only when *blind* results
   show correct direction + acceptable invariance + low fatal false-PASS +
   useful localization; FAILED_VALIDATION when evidence shows the evaluator
   cannot separate controlled defects from semantics-preserving changes;
   LIMITED otherwise (including "no blind evidence yet"). The generated file
   states the pending situation plainly and **ends with exactly one line
   containing the token** (bare `LIMITED`).
8. **Review package** (72 rows, all pairs): programmatic expectation pre-filled,
   expert label fields empty under `reviewer_A_*` / `reviewer_B_*`; the
   raw-agreement / kappa hooks are documented in
   `score_counterfactual_relations.judge_expert_agreement`, which is computed
   once two expert label files exist (no guessed second expert).

## 3. Files created (Task 3)

| File | Purpose |
|---|---|
| `diagnostics/cleareval_cf/prompts/diagnostic_audit_v1.txt` | DiagnosticAudit judge prompt (version header `diagnostic_audit_v1`), strict JSON output of exactly the DiagnosticAudit fields, evidence-grounding + abstention, no pair/seed/mutation/expected-relation vocabulary |
| `diagnostics/cleareval_cf/run_original_cce.py` | read-only CCE adapter: REUSE/RE-IMPLEMENTATION documented, offsets, aggregation replication (`--verify-aggregation`) exact vs `oeq_stats_260223.jsonl` |
| `diagnostics/cleareval_cf/online_cce.py` | `--online` production-path scoring (lazy import; never in tests) |
| `diagnostics/cleareval_cf/run_diagnostic_audit.py` | role-blind audit runner: fixture/online judges, split/freeze guard, coverage, metadata, cce scoring per side |
| `diagnostics/cleareval_cf/online_audit.py` | `--online` DiagnosticAudit judge (lazy import; never in tests) |
| `diagnostics/cleareval_cf/score_counterfactual_relations.py` | stdlib estimators 9.1-9.7 + CLI (`VALIDITY_METRICS.json`) |
| `diagnostics/cleareval_cf/review_gold.py` | GoldReview schema + assemble_gold + JSONL IO (keeps Task 1 `schemas.py` untouched) |
| `diagnostics/cleareval_cf/report_judge_validity.py` | reports, paper CSVs/texts, review package, GO/NO-GO verdict |
| `diagnostics/cleareval_cf/README.md` | purpose, boundaries, directory map, run instructions, review + split/freeze protocols, scientific-claim statement |
| `manifests/mutation_proposals_development.jsonl` | deterministic dev-scoped build (48) backing dev-role runs |
| `manifests/review_package.jsonl` | 72 rows, expert labels empty |
| `manifests/dev_audit_runs.jsonl` / `dev_cce_scores.jsonl` / `dev_reviewed_gold.jsonl` | pending-state dev run artifacts |
| `reports/JUDGE_VALIDITY.md` `BLIND_RESULTS.md` `GO_NO_GO.md` `PAPER_TABLE_COUNTERFACTUAL_VALIDITY.csv` `PAPER_FIGURE_PAIRED_SHIFTS.csv` `PAPER_METHODS_TEXT.md` `PAPER_LIMITATIONS_TEXT.md` `AGGREGATION_VERIFICATION.md` `DEV_BUILD.md` | generated reports (pending-data state) |
| `tests/diagnostics/cleareval_cf/test_runners_and_scoring.py` | 28 Task 3 tests (8 contracts) |
| `diagnostics/cleareval_cf/.sdd/task-3-report.md` | this report |

## 4. Real run (pending-data state)

```
$ python -m diagnostics.cleareval_cf.run_original_cce --verify-aggregation
recomputed : 13 / frozen 13   all exact : True   max abs diff: 0.0
report     : ...\reports\AGGREGATION_VERIFICATION.md

$ python -m diagnostics.cleareval_cf.report_judge_validity
dev proposals   : ...\manifests\mutation_proposals_development.jsonl (48)
pending metrics : ['9.1','9.2','9.3','9.4','9.5','9.6','9.7']
verdict         : LIMITED
review package  : ...\manifests\review_package.jsonl (72 rows, labels empty)
```

Offline dev audit coverage: 96 audit rows → 96 `judge_pending`; 96 CCE rows →
48 `ok` (seeded originals) + 48 `judge_missing` (mutated, no fixtures/online) --
all reported in 9.7, never imputed. `reviewed_gold.jsonl` remains 0 bytes.
Blind refusal verified: `--split blind` without a frozen prompt exits 2 with a
clear message.

## 5. Tests

```
$ python -m unittest discover -s tests -t .
Ran 100 tests in ~8s   OK        (51 Task1 + 21 Task2 + 28 Task3)
```

Task 3 tests cover: two independent judge calls per pair + no leakage (neither
prompt contains the other protocol; prompts differ only inside the protocol
slot; no pair/seed/family identifiers); metadata stability across repeated
runs; missing judge → coverage/judge_pending, never imputed; local-pipeline
invariance of all 24 EQUIVALENT pairs; exact aggregation replication (13/13,
max abs diff 0.0); metrics estimators on synthetic fixtures (directional
accuracy incl. hard-fail + floor + pending, Cohen/weighted kappa,
Krippendorff alpha, empirical tolerance from a repeat distribution, fatal
false-PASS, coverage) and empty-input pending behaviour; blind freeze mechanics
(blind without freeze refuses; dev cannot load blind pairs; freeze then blind
run with fixtures produces 144 rows).

## 6. Deviations / notes

- No deviations from the task spec. Small documented conventions:
  - 9.1 "expected component decreased" is defined over the specific score
    fields that map to each component; `MULTIPLE` relies on the judge's finding.
  - GO/NO-GO files end with a bare token line (`LIMITED`) so the terminal-line
    contract is trivially machine-checkable.
  - The dev-scoped build assigns its own sequential pair ids (MUT-001..048),
    so dev-role metrics ids differ from the blind manifest's ids -- both are
    internally consistent; the review package always uses the blind 72.
- pytest remains unusable (Task 1 concern); tests use unittest.
- No git commit was made (per instructions).

## 7. Concerns

1. **Local effectiveness fidelity vs production** is bounded and documented:
   deterministic extraction of `marker_dict`/clearing time differs from the
   teacher's, so several seeds sit at the s_label/s_time floor locally. This is
   the reason 9.1 counts floor cases separately rather than crediting them, and
   why GO/NO-GO gates on blind judge results, not on the deterministic numbers.
2. **No judge runs and no gold yet** -- everything pending; GO/NO-GO = LIMITED
   states exactly that, and recomputation after the blind run is the required
   next step. No prompt tuning after blind results.
3. **Blind freeze is an explicit event**: someone must run
   `--freeze-prompt` (or the store owner must set
   `split_manifest.frozen_prompt_sha256`) before any blind run; this is
   by design, not a gap.
4. **Eligibility skew** (from Task 1) is carried into the reports: 71 eligible
   of 3289 candidates, gpt-5.2-class-heavy; documented in
   PAPER_LIMITATIONS_TEXT.md.
5. Online paths (`online_cce.py`, `online_audit.py`) are implemented but
   unexecuted here (no keys / offline contract); they are lazy imports that
   never enter the test suite.

## 8. Re-run instructions

```
python -m diagnostics.cleareval_cf.run_original_cce --verify-aggregation
python -m diagnostics.cleareval_cf.report_judge_validity
python -m unittest discover -s tests -t .          # full suite (offline)
```
