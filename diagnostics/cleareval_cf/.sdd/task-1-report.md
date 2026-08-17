# Task 1 Report -- Seed selection + development/blind split (counterfactual-validity overlay)

Status: **DONE** (see "Concerns" for two factual notes against BASELINE_AUDIT.md)

Date: 2026-08-17. Branch: `cleareval-cf-validity`. Python 3.12 (conda env `YWB`),
Windows + Git Bash. All work is isolated under `diagnostics/cleareval_cf/`,
`tests/diagnostics/cleareval_cf/`, and the generated
`diagnostics/cleareval_cf/{manifests,reports}/`. **No production file was modified.**

## 1. Approach

1. **Empirical data check first.** Before writing any derivation rules I verified
   the frozen data shapes (question_final.json, 13 model_response files, 13
   evaluation_results files). This surfaced several facts that shaped the code
   (see Concerns 1-3): gemini-3-flash is missing qid 1 (not qid 29), 5 eval
   records carry `total_completeness_score`/`total_correctness_score` instead of
   `total_weighted_score`, 3 records have `critical_warnings: null`, and 3216 of
   3288 frozen evaluations have non-empty `critical_warnings`.
2. **Schemas first** (`schemas.py`): enums + dataclasses + strict validation +
   JSONL helpers + `BlindSplitAccessError`. All later tasks build on this.
3. **Selector** (`seed_selector.py`): mechanical derivations (scenario/method
   family/labeling), eligibility, CCE bucketing, greedy round-robin selection,
   seed-id assignment, RNG-driven split, split guard, DATA_SUMMARY.md generator.
4. **Tests** (unittest -- pytest is installed but its environment is broken, see
   Concern 4): schema unit tests + end-to-end selection tests that run the real
   pipeline twice into fresh temp dirs and assert byte-identity, counts, split
   isolation, guard behavior, and pool statistics.
5. **Real run** into `diagnostics/cleareval_cf/manifests/` + `reports/`, then the
   full test suite (51 tests, all pass).

## 2. Key decisions (all documented in code + DATA_SUMMARY.md)

- **scenario_type**: ERROR_CORRECTION first (regex `错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在`,
  60 questions), else COMPLEX_GENERATION if `len(marker_query_targets) >= 4` (96),
  else SIMPLE_GENERATION (97). Verified against real text.
- **clearing_method_family**: first-match priority keyword map over question text
  (17 rules incl. CUBIC/PEGASOS/iDISCO/FDISCO/uDISCO/3DISCO/DISCO/MACS/eFLASH/
  CLARITY/SHANEL/SeeDB/Scale/SWITCH/SOLVENT_BASED, UNKNOWN fallback). Question text
  rarely names a method, so UNKNOWN dominates -- that is a data fact, not a bug.
- **labeling_requirement**: text keywords (transgenic list / 抗体|免疫) +
  marker-name fallback (GFP|YFP|Thy1|tdTomato|Ai14|reporter|Cre); MIXED upgrade
  rule uses `n_targets >= 4` (multi-marker panels with a reporter), which is the
  documented role of marker_query_targets count.
- **Eligibility** (mechanical only): response record exists, response text
  non-empty, eval record exists, usable totals for all three parts (accepting the
  `total_*_score` field-name variants), `critical_warnings` empty/absent.
  Result: **71 eligible candidates** of 3289 tried. Rejections:
  critical_warnings_present 3216, missing_cc_score_totals 1 (gemini qid 29 has
  no completeness part at all), missing_response_record 1 (gemini qid 1).
- **CCE bucket**: equal-width thirds of the observed eligible range
  [9.2963, 26.2710] -> LOW < 14.9545, MID < 20.6128, HIGH >= 20.6128.
- **Selection**: RNG-free greedy round-robin; round r led by `DIMENSIONS[r % 5]`;
  lexicographic key `(count[lead], sum(other dims), question_id, source_model)`;
  seed ids SEED-001..024 assigned sorted by (stratum rank, qid, model).
- **Split**: `random.Random(20260817)` consumed ONLY by (a) stratum order draw
  (drawn: ERROR_CORRECTION, SIMPLE_GENERATION, COMPLEX_GENERATION) and (b) blind
  sampling within stratum. COMPLEX_GENERATION (drawn third) holds 4 development
  seeds; the other two hold 6 each. Dev 16 / blind 8, disjoint, re-verified by
  `SplitManifest.validate()`.
- **Gold guard at schema level**: `MutationProposal.validate()` raises if
  `APPROVED_GOLD` with empty `reviewer_ids` or `adjudication_status != ADJUDICATED`.
  Nothing in this task writes APPROVED_GOLD; all future mutation records default
  to PENDING_REVIEW (schema default + suite-wide rule documented).
- **Split guard**: `load_split_manifest(path, role)` (validates role) +
  `assert_split_access(path_or_seed, role, manifest)`; role=development raises
  `BlindSplitAccessError` for blind seed ids or file basenames containing a blind
  SEED-<NNN> token; role=blind unrestricted (one-directional by design).
- **Determinism**: sort_keys everywhere, UTF-8 + LF (`newline="\n"`), no
  timestamps, forward-slash normalized paths, fixed seed. Verified byte-identical
  across two runs in different directories for all three outputs.
- **question_mode**: constant `APPLICATION_PROTOCOL_DESIGN` (audit: all 253
  questions are single-format application/protocol-design prompts).

## 3. Files created

| File | Purpose |
|---|---|
| `diagnostics/cleareval_cf/schemas.py` | enums, SeedCandidate / MutationProposal / SplitManifest / DiagnosticAuditResult / TextSpan / SurfaceEdit dataclasses, validation, JSONL I/O, BlindSplitAccessError |
| `diagnostics/cleareval_cf/seed_selector.py` | derivations, eligibility, greedy selection, split, split guard, DATA_SUMMARY generator, CLI (`python -m diagnostics.cleareval_cf.seed_selector` and `python diagnostics/cleareval_cf/seed_selector.py` both work) |
| `diagnostics/cleareval_cf/manifests/seed_candidates.jsonl` | 24 SeedCandidate records (8 per stratum) |
| `diagnostics/cleareval_cf/manifests/split_manifest.json` | dev 16 / blind 8 seed ids, split_seed 20260817, created_from sha256, frozen_prompt_sha256: null |
| `diagnostics/cleareval_cf/reports/DATA_SUMMARY.md` | strata definitions+counts, input hashes (27 files), eligibility rules+rejection table, per-model/per-stratum pools, CCE range/boundaries, derivation rules, selection algorithm, 24-seed tables, split details, output hashes |
| `tests/__init__.py`, `tests/diagnostics/__init__.py`, `tests/diagnostics/cleareval_cf/__init__.py` | test package scaffolding (needed for `unittest discover`) |
| `tests/diagnostics/cleareval_cf/test_schemas.py` | 33 schema-level tests (round trips, enum/format validation, TextSpan self-verification, Gold guard, SplitManifest invariants, JSONL error reporting) |
| `tests/diagnostics/cleareval_cf/test_seed_selection.py` | 18 end-to-end tests (determinism, counts, split isolation, guard, pinned pool stats) |
| `diagnostics/cleareval_cf/.sdd/task-1-report.md` | this report |

## 4. Test command + output tail

pytest is installed but its environment is broken (ImportError on
`opentelemetry.exporter.otlp.proto.grpc` inside the conda env), so per the task
instruction tests use **unittest**.

```
$ python -m unittest discover -s tests -t . -v
...
test_pool_statistics_pinned ... ok
test_report_byte_identical ... ok
test_seed_ids_sequential_and_unique ... ok
test_split_isolation_and_sizes ... ok
test_split_manifest_byte_identical ... ok
test_unknown_role_rejected ... ok
----------------------------------------------------------------------
Ran 51 tests in 3.324s

OK
```

Real run:
```
$ python -m diagnostics.cleareval_cf.seed_selector
seeds written : ...\diagnostics\cleareval_cf\manifests\seed_candidates.jsonl (24)
per stratum   : {'SIMPLE_GENERATION': 8, 'COMPLEX_GENERATION': 8, 'ERROR_CORRECTION': 8}
eligible pool : 71  rejections: {'missing_response_record': 1, 'critical_warnings_present': 3216, 'missing_cc_score_totals': 1}
dev seeds     : 16  blind seeds: 8
created_from  : ce696175d7a546de8c2f8e7d8974aaa1e53d2b2ed6f5a3b793e683fbb5010f49
```

## 5. Deviations / notes

- No deviations from the task spec; two factual corrections to
  BASELINE_AUDIT.md are recorded under Concerns.
- `ExpectedSeverity` (NONE/MINOR/MODERATE/CRITICAL) and `question_mode` were
  specified as documented conventions since the task did not pin their vocabularies.
- `source_file` is stored relative to `data_root` with forward slashes.

## 6. Concerns

1. **Audit correction (gemini-3-flash)**: BASELINE_AUDIT.md says gemini-3-flash
   is missing qid 29; empirically its response/eval files are missing **qid 1**
   (qids 237/246/247 do not exist in question_final.json at all), and its qid-29
   eval record exists but its completeness part is absent (rejected by
   `missing_cc_score_totals`). Audit's "251 usable" is actually 252 usable once
   the `total_*_score` field-name variant is normalized (per spec's "totals
   present" rule, mechanical).
2. **Audit correction (pool size)**: with the task-mandated eligibility rule
   "critical_warnings empty or absent", only **71** of 3289 candidate pairs are
   eligible, because 3216 frozen evaluations carry >= 1 critical warning. The
   pool is heavily skewed toward openai_gpt-5.2-fast (22) / gpt-5.2-thinking (15);
   openai_qwen3-14b/235b/32b have 0 eligible candidates (all their records carry
   warnings). This is a property of the frozen data, not of the selection; the
   pool statistics are pinned in tests so any data regeneration is noticed.
   If a larger pool is ever desired, the critical-warnings rule would need a
   task-level decision (e.g. "warnings not related to scoring components").
3. **Selection coverage**: the 24 seeds span 9 of 13 models and a wide tier/
   family/labeling/CCE mix (see DATA_SUMMARY.md section 6); models with zero
   eligible candidates cannot appear, by construction.
4. **pytest unusable in this environment** (broken opentelemetry import inside
   the conda env; not fixable without touching the environment). Tests are
   written with `unittest` and remain pytest-discoverable if the env is repaired.
5. No git commit was made (per instructions).

## 7. Re-run instructions

```
python -m diagnostics.cleareval_cf.seed_selector        # regenerate manifests + report
python -m unittest discover -s tests -t .               # full test suite (offline)
```
