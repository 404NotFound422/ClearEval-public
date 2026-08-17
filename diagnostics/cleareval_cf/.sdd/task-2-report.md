# Task 2 Report -- Mutation proposals: registry + builder + validator
(counterfactual-validity overlay)

Status: **DONE**

Date: 2026-08-17. Branch: `cleareval-cf-validity`. Python 3.12, Windows + Git Bash.
All work is isolated under `diagnostics/cleareval_cf/` and
`tests/diagnostics/cleareval_cf/`. **No production file was modified**
(git status shows only the previously-untracked `diagnostics/`, `tests/` and
unchanged pre-existing untracked files; no commits made, per instructions).

## 1. Deliverables produced

| File | Purpose |
|---|---|
| `diagnostics/cleareval_cf/mutation_registry.py` | split-aware, Gold-guarded registry: loads/validates proposal+seed manifests, re-enforces the Gold guard at load and at `promote_to_gold(...)` (refuses empty reviewers / missing adjudication evidence), enforces the development/blind split guard (development role cannot load the full 72-record manifest -> `BlindSplitAccessError`), balance/introspection helpers (`counts_by_family/split/expected_relation`, `per_seed_families`). |
| `diagnostics/cleareval_cf/mutation_builder.py` | deterministic span-level operators; builds 72 proposals (24 EQUIVALENT + 48 degrading, exactly 8 per family); writes `manifests/mutation_proposals.jsonl` + empty `manifests/reviewed_gold.jsonl` + build report. `role` = development/blind; the full-corpus build is a blind-role operation. |
| `diagnostics/cleareval_cf/mutation_validator.py` | validates the manifest (schema/lifecycle, 8-per-family balance, split containment, span integrity with no-undeclared-differences masked check, EQUIVALENT contract, evidence spot-check against real KB rows) and writes `reports/MUTATION_VALIDATION.md`. |
| `diagnostics/cleareval_cf/manifests/mutation_proposals.jsonl` | **72 records** (MUT-001..072), all `PENDING_REVIEW` / `reviewer_ids=[]` / `adjudication_status=PENDING`; sha256 `e5718e862dfff97adf66411db9c8a8a35b73830b524d122e142954df4a99d950`. |
| `diagnostics/cleareval_cf/manifests/reviewed_gold.jsonl` | empty stub (0 records) = "no human-reviewed gold yet"; JSONL cannot hold a comment header, documented in the registry/build-report instead. |
| `diagnostics/cleareval_cf/reports/MUTATION_BUILD.md` | assignment algorithm, family->seed table, operator expectations, per-pair operator log, fallbacks, sha256. |
| `diagnostics/cleareval_cf/reports/MUTATION_VALIDATION.md` | counts, balance table, per-pair span-integrity log, fallbacks, violations (PASS, 0 problems). |
| `tests/diagnostics/cleareval_cf/test_mutations.py` | 21 unittest tests (see section 4). |
| `diagnostics/cleareval_cf/.sdd/task-2-report.md` | this report. |

## 2. Key decisions (documented in code)

1. **Span convention (newly pinned)**: `original_text_spans` offsets are into the
   seed `response_text`; `mutated_text_spans` offsets are into the *mutated*
   text (schema left this open; this task fixes it). `apply_edits()` applies
   disjoint (start,end,new) edits in original coordinates and returns both the
   mutated text and the mutated-span offsets. Every mutated span is non-empty
   (schema requires `0 <= start < end`), so deletion-family mutations replace a
   clause with a short non-empty marker ("Time: unspecified") rather than an
   empty slice.

2. **Operator set / expected relation** (`mutation_operator_version = v1.0`),
   each implemented as explicit span-level edits on the seed text:
   - `equivalent_formatting_v1.0` -> EQUIVALENT (wording/formatting only;
     `changed_field_paths=[]`, change lives in `surface_edits`; severity NONE).
   - `omission_delete_duration_v1.0` -> REQUIRED_INFORMATION_OMISSION (DEGRADED,
     MODERATE): a step's declared `Time: <value>` replaced by "Time: unspecified".
   - `step_order_swap_v1.0` -> STEP_ORDER_OR_CHEMISTRY_CONFLICT (DEGRADED,
     MODERATE): swaps two adjacent numbered sub-steps of a section.
   - `target_marker_replace_v1.0` -> TARGET_MARKER_MISMATCH (DEGRADED, MODERATE):
     a mention of a question target marker replaced by a marker not in the
     question's marker_query_targets (deterministic distractor pool).
   - `method_fluorophore_conflict_v1.0` -> METHOD_FLUOROPHORE_CONFLICT (DEGRADED,
     MODERATE): a compatible fluorophore replaced by one the KB rates <= 0.25
     for the stated method (evidence `method_fluro_compati.json`).
   - `sample_method_scope_v1.0` -> SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT (HARD_FAIL,
     CRITICAL): stated method replaced by the KB method whose reference RI is
     furthest from the sample's native RI; cites `method_ri_ref.json`,
     `tissue_ri.json` and, when the (replacement, tier) row does not exist, the
     `time_kb.json` support gate.
   - `clearing_time_out_of_range_v1.0` -> CLEARING_TIME_OUT_OF_RANGE (HARD_FAIL,
     CRITICAL): dominant (labeling-free, clearing-chemistry-context) duration
     replaced with a value strictly above the KB `[min,max]` (max_h + 24h), or
     the documented `45 days` constant under the UNSUPPORTED gate.
   Rationale: HARD_FAIL is reserved for the two *scope* violations the KB says
   are unsupported (method-vs-sample scope, time-vs-(method,tier) scope); the
   four local-content defects are DEGRADED. Severity/stereotype never consult
   scorer thresholds.

3. **Family -> seed assignment** (seeded RNG, documented in MUTATION_BUILD.md):
   `FAMILIES` = canonical order of the 6; `rng=random.Random(20260817)`;
   `order=list(range(24)); rng.shuffle(order)`; seed at index `i` gets
   `FAMILIES[(2i)%6]` and `FAMILIES[(2i+1)%6]` -> each family exactly 8 times,
   every seed exactly 2 distinct families. This is the builder's only RNG use;
   verified byte-identical across reruns.

4. **EQUIVALENT conventions** (schema-forced, documented):
   - Placeholder `mutation_family` = the seed's first assigned family (the
     matched control axis); `expected_relation=EQUIVALENT` is the semantic
     marker, and the validator never treats it as a degrading record.
   - `expected_affected_components` must be non-empty per schema; for EQUIVALENT
     it is set to `[S_METHOD]` with `expected_severity=NONE` documented as the
     "no impact" marker.
   - Every EQUIVALENT change is recorded in `surface_edits` (1:1 with the span
     edits) and `changed_field_paths` is empty; the validator verifies this.

5. **Role semantics / split guard**: the builder exposes development (48 records,
   dev seeds only) and blind (72 records, all seeds) roles. The delivered
   manifest is a blind-role artifact (it contains blind seeds by design).
   Development-role consumers use `MutationRegistry(role="development")`, which
   (a) raises `BlindSplitAccessError` if asked to load a manifest referencing
   blind seeds and (b) exposes only the 16 development seeds. All registry
   introspection + `promote_to_gold` are role-aware (calling them in
   development role on the full manifest raises).

6. **Gold guard**: enforced at schema construction, at registry load, and at
   `promote_to_gold(pair_id, reviewer_ids, adjudication_evidence)` which
   refuses empty reviewers / empty evidence / re-promotion; on success writes
   `review_status=APPROVED_GOLD`, sets `reviewer_ids`, `adjudication_status=
   ADJUDICATED` and appends `gold_note:` to `expected_location`. A forged
   manifest (APPROVED_GOLD without reviewers) is rejected at load in tests.

7. **Evidence id grammar + spot-check**: `kb:<file>:<key>` with files
   `time_kb.json` (`method|tier`, or `method|UNSUPPORTED:tier`), 
   `method_fluro_compati.json` (method), `method_ri_ref.json` (method),
   `tissue_ri.json` (tissue leaf incl. `default_ri`). The validator loads each
   referenced file and resolves every key (exact, or token-overlap tier,
   consistent with the builder). The three evidence-backed families must carry
   >= 1 evidence id (degrading records only).

8. **Tissue RI canonicalization**: `tissue_ri.json` stores "brain" as a group
   without a scalar, so `brain` -> `whole_brain` (1.46) for both the RI used in
   the scope-gap computation and the evidence id.

9. **Fallbacks**: one documented fallback in the real run -- SEED-018
   (SeeDB2, T09_HUMAN_DENSE_CLINICAL_BLOCK has no time_kb.json row) uses the
   UNSUPPORTED gate constant "45 days". Listed in MUTATION_BUILD.md and mirrored
   into MUTATION_VALIDATION.md. No operator ever fails silently; every fallback
   is declarative and span-recorded.

## 3. Real run (canonical artifacts)

```
$ python -m diagnostics.cleareval_cf.mutation_builder --role blind
proposals  : ...manifests\mutation_proposals.jsonl (72 records)
equivalent : 24  degrading: 48
fallbacks  : 1 -> SEED-018:CLEARING_TIME_OUT_OF_RANGE

$ python -m diagnostics.cleareval_cf.mutation_validator
valid        : True     families: all 8 each
relations    : {'EQUIVALENT': 24, 'DEGRADED': 32, 'HARD_FAIL': 16}
span fails   : 0   evidence fails: 0   fallbacks: 1
```

Family balance: CLEARING_TIME_OUT_OF_RANGE 8, METHOD_FLUOROPHORE_CONFLICT 8,
REQUIRED_INFORMATION_OMISSION 8, SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT 8,
STEP_ORDER_OR_CHEMISTRY_CONFLICT 8, TARGET_MARKER_MISMATCH 8. Split counts:
48 development / 24 blind. `mutation_proposals.jsonl` sha256
`e5718e862dfff97adf66411db9c8a8a35b73830b524d122e142954df4a99d950`
(byte-identical across reruns, verified).

## 4. Tests

`python -m unittest discover -s tests -t .` -> **72 tests, OK** (51 Task 1 +
21 Task 2). New tests cover: 72/24/48 totals, 8-per-family balance, exactly two
distinct families per seed, PENDING_REVIEW lifecycle + sequential MUT-001..072,
span integrity + no-undeclared-edits for all 72, negative detection of a
tampered/lengthened mutated span and of an original span that doesn't slice the
seed, EQUIVALENT contract, Gold guard (promote rejects empty reviewers/evidence;
forged APPROVED_GOLD rejected at load), split guard (development role rejects
the full manifest; a development-only build loads and exposes 16 seeds),
seeded-and-balanced assignment, byte-identical double build, and the committed
manifest passing the full validator.

## 5. Deviations / notes

- No deviations from the task spec; two documented conventions (4) were forced
  by the existing schema's non-empty `expected_affected_components` list.
- pytest remains unusable in this env (Task 1 concern 4); tests use unittest.
- `reviewed_gold.jsonl` is empty by design (JSONL has no comment syntax); the
  "empty file == no gold approved" convention is documented in the registry
  docstring and MUTATION_BUILD.md.

## 6. Concerns

1. **EQUIVALENT placeholder family**: EQUIVALENT records carry the seed's first
   assigned family as a documented control axis; anyone reading the manifest
   must filter by `expected_relation` (never by family) to count defects. The
   validator only ever balances degrading records.
2. **SEED-016/018** are analysis-draft responses; their stated method is
   extracted by count-based fallback (SEED-016 -> TDE, SEED-018 -> SeeDB2 via
   "Final Choice"). Documented in MUTATION_BUILD.md; span targets remain
   single-line and label-free after the newline-exclusion fix.
3. **Duration parsing** (`_estimate_hours`) is a heuristic (ranges -> max,
   `A×B` multiplied) used only to select the target span and to size the
   out-of-range replacement; it never feeds any scorer threshold, and all
   mutations are grounded in time_kb.json rows, not in scorer logic.
4. **No Kaggle-style gold leakage**: generation used only the frozen seed
   `response_text`, the question text + `marker_query_targets` (part of the
   prompt), and the KnowledgeBase files. CCE/gold/expert scores were never read
   by any Task 2 module path.
5. No git commit was made (per instructions).

## 7. Re-run instructions

```
python -m diagnostics.cleareval_cf.mutation_builder --role blind   # 72 proposals + build report
python -m diagnostics.cleareval_cf.mutation_validator               # writes MUTATION_VALIDATION.md
python -m unittest discover -s tests -t .                           # full suite (offline)
```
