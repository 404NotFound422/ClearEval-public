# Final-review fixes -- counterfactual-validity suite

Branch `cleareval-cf-validity`, base commit `efac378`. Scope: only
`diagnostics/cleareval_cf/` and `tests/diagnostics/cleareval_cf/`; no production
file modified. All 23 findings addressed below; every derived artifact
(manifests, reports, CSVs) was regenerated from the fixed code so data and prose
are consistent.

## Test command + result

```
python -m unittest discover -s tests -t .
----------------------------------------------------------------------
Ran 119 tests in 8.103s

OK
```

(Previously 100 tests; +19 new tests covering the findings.)

---

## CRITICAL

### 1. assemble_gold no longer leaks proposal expectations
- `review_gold.py` — `assemble_gold(package_rows, reviewer_id, ..., expert="A")`
  now reads ONLY the `reviewer_{expert}_*` label keys
  (`reviewer_A_expected_relation`, `reviewer_A_affected_cc_component`, …).
  It never falls back to the unprefixed programmatic fields
  (`expected_relation` / `expected_affected_components`) that
  `write_review_package` pre-fills; a row whose expert labels are empty is
  skipped (covered by 9.7). Enum label strings are coerced to members.
- New tests (`tests/.../test_review_gold_and_reports.py`): package→assemble→gold
  round trip proves proposal expectations cannot leak into Gold (including the
  case where the expert leaves the gold relation NULL while the programmatic
  relation is filled).

### 2. Development pair ids are DEV-MUT-* (no canonical collision)
- `schemas.py` `_PAIR_ID_RE` accepts `(?:DEV-)?MUT-\d{3,}`; `review_gold.py`
  `_PAIR_RE` likewise.
- `mutation_builder.build()` prefixes dev-scoped ids `DEV-MUT-001..048`.
- Regenerated `mutation_proposals_development.jsonl`, `dev_audit_runs.jsonl`,
  `dev_cce_scores.jsonl`, `PAPER_FIGURE_PAIRED_SHIFTS.csv`, `DEV_BUILD.md` —
  dev numbering and canonical `MUT-*` numbering are now disjoint (test in
  `test_mutations.py` asserts the namespaces are disjoint).

## IMPORTANT

### 3. Blind freeze pins the exact prompt revision (hash equality)
- `run_diagnostic_audit.freeze_prompt` is now one-shot: a second freeze raises
  `FreezeError`.
- `run_audit` (blind role) refuses unless `split.frozen_prompt_sha256 ==
  current_prompt_sha256()`; a drift/tuned prompt after the freeze raises
  `FreezeError`.
- Tests in `test_runners_and_scoring.py`: blind under a mismatched frozen hash
  refuses; re-freeze refused once frozen.

### 4. `_resolve_tissue_ri` ported verbatim from production
- `run_original_cce.py` — the method now mirrors `OEQ_run_grading_new.py`
  `_resolve_tissue_ri` branch-for-branch (placenta, stomach, intestine, lung,
  testis, whole-brain, embryo/hippocampus/retina/CNS/plant etc. in the exact
  production order). The "faithful copy" docstring is now true.

### 5. `[CRITICAL FORMAT RULE]` block copied verbatim
- `online_cce.py` now embeds the full production enforcement string
  (`OEQ_run_grading_new.py` `evaluate_response_with_teacher`), not the
  truncated placeholder.

### 6. Krippendorff alpha implemented correctly
- `score_counterfactual_relations.krippendorff_alpha_nominal` now uses the
  coincidence-matrix expectation `D_exp = Σ n_c(n−n_c)/(n(n−1))` with
  `n = 2·n_units` (was an N²-form Scott's-pi-like formula).
- Test with a hand-computed known value: units (A,A),(A,A),(A,B),(B,A),(B,B)
  ⇒ α = 0.25 (Scott's pi would be 0.23077; the test pins the distinction).

### 7. Gold-referenced metrics gated on ADJUDICATED
- `compute_all` filters gold to `adjudication_status == ADJUDICATED` for
  9.1/9.3/9.4/9.5; non-adjudicated gold → metrics report pending
  (`n_non_adjudicated_gold_pairs` surfaced, and named per-pair in 9.7
  `non_adjudicated_gold_pair_ids`).
- Test: PENDING gold does not feed 9.3/9.4/9.5; same rows ADJUDICATED do.

### 8. `verdict()` evaluates the blind metrics
- `report_judge_validity.verdict` now evaluates the blind metrics when
  present (`blind_results` with a `"metrics"` key or a bare metrics dict);
  a blind-run summary with no metrics is not enough evidence → LIMITED.
- Tests: dev metrics unassessable + blind metrics good ⇒ SUPPORTED;
  blind metrics bad ⇒ FAILED_VALIDATION.

### 9. Coverage enumerates pairs absent from audit/CCE manifests
- `coverage_report` emits `missing_audit_pair_ids` / `missing_cce_pair_ids`
  (`proposal_pair_ids − observed`) plus `missing_pair_ids`; `all_scored` and
  `pending` incorporate them.
- Test: a proposal with no audit/CCE rows is explicitly listed.

### 10. Stratum counts computed at runtime (correct 60/70/123)
- `seed_selector.write_data_summary` derives the question-level counts from
  `question_final.json` via `derive_scenario_type` (was hardcoded 60/96/97.
  Verified 60/70/123). Module docstring updated. `DATA_SUMMARY.md` regenerated.

### 11. Undeclared-edit detection diffs the real persisted text
- `MutationProposal.mutated_text` (full mutated text) is persisted by the
  builder; `detect_undeclared_edits` diffs it against the seed text with the
  declared spans masked (real check). The old reconstruction-masked comparison
  is kept only as a legacy fallback for manifests without `mutated_text`.
- Validation report wording updated ("persisted mutated full text is diffed",
  fallbacks "persisted on proposal records").

### 12. Papers/README future-scope the validity claim
- `PROMISED_CLAIM` (and README + regenerated PAPER_METHODS_TEXT /
  PAPER_LIMITATIONS_TEXT) now say the evaluator is "designed to be validated …
  Validation results are pending expert review … and a role-blind judge run."

### 13. PAPER_TABLE includes every metric as a row
- `write_paper_csvs` emits rows for 9.1 (incl. sub-metrics), 9.2, 9.3, 9.4,
  9.5 (raw/kappa for expert A and A-vs-B), 9.6, 9.7 (missing audit/cce pairs,
  all_scored) with explicit pending markers. CSV regenerated.

### 14. 9.1 sub-metrics + A/B/C baselines generated from data
- 9.1 now reports `n_correct_by_score_drop` / `n_correct_by_hard_fail` (and in
  the per-pair detail). `baseline_comparison()` computes a per-baseline table
  from the 9.1/9.2/9.3/9.4 metrics + audit/CCE row counts with explicit pending
  handling (no fabricated numbers); `compute_all` returns `baselines_A_B_C` and
  JUDGE_VALIDITY.md renders it from data.

### 15. Dev-only seed manifest + role-routed seed loading
- `seed_selector` ships `seed_candidates_development.jsonl` (16 dev rows, no
  blind content).
- New `load_seed_candidates_role(path, role, split_path)` routes seed loading
  through the split guard: development role loading the full manifest raises
  `BlindSplitAccessError`. `MutationRegistry` uses it; `mutation_builder.build`
  and `run_diagnostic_audit.run_audit` route the development default to the dev
  manifest (proposals are never silently swapped — pointing dev role at the
  full 72-record manifest still raises). `load_proposals` in dev role raises
  `BlindSplitAccessError` for any blind-seed reference before the containment
  check.
- Tests in `test_seed_selection.py` + updated registry/runner tests.

### 16. Tests for review_gold / write_review_package / verdict
- New `tests/diagnostics/cleareval_cf/test_review_gold_and_reports.py`
  (assemble_gold expert-scoping, proposal-leak, gold schema strictness, 72-row
  empty-label package, verdict blind-metric paths).

## MINOR

### 17. `_sm_norm` for `find_signed_method`
- `run_original_cce.py` adds production `_sm_norm` (strips `()`/`+`) and uses
  it inside `find_signed_method` (was `_normalize_name`), matching production.

### 18. Dead code removed
- `run_diagnostic_audit.py`: `PROMT_DIR` typo constant.
- `run_original_cce.py`: uncalled `score_frozen_original` and the overwritten
  `keys = [...]` line in `compare_stats_with_frozen`.
- `mutation_validator.py`: unused `relation_problems` block and the markdown
  `_read_fallbacks` parser (fallbacks now read from manifest fields).
- `score_counterfactual_relations.py`: no-op `if vo > vm: pass` and unused
  `valid_groups_with_cc`.
- `review_gold.py`: dead `HARD_FAIL/hard_fail_status` no-op block.
- `online_audit.py`: unused `run_meta` parameter removed from
  `online_audit_call` (and its call site).

### 19. `gold_note` lives in a dedicated field
- `MutationProposal.gold_note` added; `promote_to_gold` writes evidence there
  and leaves `expected_location` untouched. Test updated.

### 20. Missing/unknown review fields raise
- `MutationProposal.from_dict` requires `review_status` / `reviewer_ids` /
  `adjudication_status` (KeyError → ValidationError; unknown enum → error).
- `GoldReview.from_dict` requires a valid `adjudication_status`. Tests added.

### 21. Report nits
- PAPER_TABLE 9.2 pending flag fixed (was an inconsistent `False` due to the
  `metrics_sum`/`metrics_pending` short-key bug; keys mapped to full metric keys).
- JUDGE_VALIDITY 9.4 shows a "metric pending: no HARD_FAIL gold" marker when
  gold is empty.
- DEV_BUILD.md no longer copies the MUTATION_BUILD title (titled
  "DEV_BUILD -- development-scoped …" with the DEV-MUT namespace note).
- BASELINE_AUDIT.md: gemini-3-flash's missing qid corrected to **1** in both
  mentions (verified against the data: response/eval files are missing qid 1).
- README.md no longer lists the non-existent `VALIDITY_METRICS.json` as a
  committed report (notes it is CLI-generated).
- PAPER_METHODS_TEXT "…two single-defect variants per family" → "per seed".
- PAPER_LIMITATIONS_TEXT states the seeded originals' effectiveness is
  re-derived and can diverge from the frozen totals.

### 22. Fallback metadata persisted on the proposal
- `operator_fallback_used` / `operator_fallback_note` persisted on every
  record; EQUIVALENT placeholder-family coverage convention (3 of 6 families)
  documented in the build report; validator reads fallbacks from the manifest.

### 23. Test hygiene
- Temp dirs no longer created inside the committed `manifests/`
  (`tempfile.mkdtemp()` without `dir=MANIFESTS`).
- Per-seed structure assertion added (1 EQUIVALENT + 2 degrading per seed).

---

## Verified regenerated artifacts (inputs → outputs consistent)
- `seed_candidates.jsonl` / `split_manifest.json` byte-identical to committed
  (determinism re-verified); `seed_candidates_development.jsonl` new (16 rows).
- `mutation_proposals.jsonl` / `mutation_proposals_development.jsonl`
  (DEV-MUT ids; `mutated_text` + fallback fields persisted).
- `MUTATION_BUILD.md` / `DEV_BUILD.md` / `MUTATION_VALIDATION.md`.
- Dev audit + CCE runs (`dev_audit_runs.jsonl`, `dev_cce_scores.jsonl`).
- `AGGREGATION_VERIFICATION.md` (all_exact True, max diff 0.0).
- `DATA_SUMMARY.md` (strata 60/70/123), `JUDGE_VALIDITY.md`, `BLIND_RESULTS.md`,
  `GO_NO_GO.md` (= LIMITED), `PAPER_TABLE…csv`, `PAPER_FIGURE…csv`,
  `PAPER_METHODS_TEXT.md`, `PAPER_LIMITATIONS_TEXT.md`, `review_package.jsonl`.
