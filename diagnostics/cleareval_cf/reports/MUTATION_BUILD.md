# MUTATION_BUILD -- proposal construction report (Task 2)

- proposals out : `mutation_proposals.jsonl`
- gold stub out : `reviewed_gold.jsonl` (empty file = no gold approved yet)
- proposal count: 72 (equivalent 24, degrading 48)
- sha256 mutation_proposals.jsonl: 4007ec208f23b2a4a6dfe3e44b08244ebaa5eb94b28c4886a29cf94705b42731

All operators: `mutation_operator_version = v1.0`, span-level edits on the
seed `response_text`.  Every record is PENDING_REVIEW with empty reviewer_ids
and adjudication_status = PENDING (the suite never fabricates APPROVED_GOLD).
No ClearEval gold / expert labels / mutation labels / scorer thresholds are used.

## Family -> seed assignment (seeded RNG, documented)

Algorithm: `FAMILIES` = the 6 families in canonical order; `rng = random.Random(20260817)`; `order = list(range(24)); rng.shuffle(order)`; the seed at shuffled index `i` receives `FAMILIES[(2*i) % 6]` and `FAMILIES[(2*i+1) % 6]`.  This is the only RNG consumption of the builder.  Each family is used exactly 8 times; every seed gets exactly 2 distinct families.  The EQUIVALENT variant of a seed carries the seed's first assigned family as its control axis (documented convention; the relation field is the semantic marker, not the placeholder family).

**EQUIVALENT control-axis coverage convention:** `FAMILIES[(2*i) % 6]` cycles i over 24 seeds, so only 3 of the 6 families ever appear as the first assigned family (indices 0/2/4 -> REQUIRED_INFORMATION_OMISSION, TARGET_MARKER_MISMATCH, SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT).  The `mutation_family` value on an EQUIVALENT record is therefore a *placeholder control axis* only -- it is documented here and is never treated as a semantic claim about the mutation (the relation field is the semantic marker).

| seed_id | family 1 | family 2 |
|---|---|---|
| SEED-001 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-002 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-003 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-004 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-005 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-006 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-007 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-008 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-009 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-010 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-011 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-012 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-013 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-014 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-015 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-016 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-017 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-018 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-019 | CLEARING_TIME_OUT_OF_RANGE | METHOD_FLUOROPHORE_CONFLICT |
| SEED-020 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-021 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-022 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |
| SEED-023 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | TARGET_MARKER_MISMATCH |
| SEED-024 | REQUIRED_INFORMATION_OMISSION | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT |

Degrading-family balance over the full 24-seed plan:

| family | count |
|---|---|
| CLEARING_TIME_OUT_OF_RANGE | 8 |
| METHOD_FLUOROPHORE_CONFLICT | 8 |
| REQUIRED_INFORMATION_OMISSION | 8 |
| SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | 8 |
| STEP_ORDER_OR_CHEMISTRY_CONFLICT | 8 |
| TARGET_MARKER_MISMATCH | 8 |

## Operator expectations

| family | relation | severity |
|---|---|---|
| EQUIVALENT | EQUIVALENT | NONE |
| REQUIRED_INFORMATION_OMISSION | DEGRADED | MODERATE |
| STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | MODERATE |
| TARGET_MARKER_MISMATCH | DEGRADED | MODERATE |
| METHOD_FLUOROPHORE_CONFLICT | DEGRADED | MODERATE |
| SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | CRITICAL |
| CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | CRITICAL |

## Fallbacks used

| seed_id | family | operator | note |
|---|---|---|---|
| SEED-018 | CLEARING_TIME_OUT_OF_RANGE | clearing_time_out_of_range_v1.0 | no (method, tier) row in time_kb.json; used documented '45 days' gate |

## Per-pair operator log

| pair_id | seed_id | family | relation | operator | spans |
|---|---|---|---|---|---|
| MUT-001 | SEED-001 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-002 | SEED-001 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-003 | SEED-001 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-004 | SEED-002 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-005 | SEED-002 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-006 | SEED-002 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-007 | SEED-003 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-008 | SEED-003 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-009 | SEED-003 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-010 | SEED-004 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-011 | SEED-004 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-012 | SEED-004 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-013 | SEED-005 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-014 | SEED-005 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-015 | SEED-005 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-016 | SEED-006 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-017 | SEED-006 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-018 | SEED-006 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-019 | SEED-007 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-020 | SEED-007 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-021 | SEED-007 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-022 | SEED-008 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-023 | SEED-008 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-024 | SEED-008 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-025 | SEED-009 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-026 | SEED-009 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-027 | SEED-009 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-028 | SEED-010 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-029 | SEED-010 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-030 | SEED-010 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-031 | SEED-011 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-032 | SEED-011 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-033 | SEED-011 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-034 | SEED-012 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-035 | SEED-012 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-036 | SEED-012 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-037 | SEED-013 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-038 | SEED-013 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-039 | SEED-013 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-040 | SEED-014 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-041 | SEED-014 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-042 | SEED-014 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-043 | SEED-015 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-044 | SEED-015 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-045 | SEED-015 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-046 | SEED-016 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-047 | SEED-016 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-048 | SEED-016 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-049 | SEED-017 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-050 | SEED-017 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-051 | SEED-017 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-052 | SEED-018 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-053 | SEED-018 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-054 | SEED-018 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-055 | SEED-019 | CLEARING_TIME_OUT_OF_RANGE | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-056 | SEED-019 | CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | clearing_time_out_of_range_v1.0 | 1 |
| MUT-057 | SEED-019 | METHOD_FLUOROPHORE_CONFLICT | DEGRADED | method_fluorophore_conflict_v1.0 | 1 |
| MUT-058 | SEED-020 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-059 | SEED-020 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-060 | SEED-020 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-061 | SEED-021 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-062 | SEED-021 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-063 | SEED-021 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-064 | SEED-022 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-065 | SEED-022 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-066 | SEED-022 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
| MUT-067 | SEED-023 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-068 | SEED-023 | STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | step_order_swap_v1.0 | 2 |
| MUT-069 | SEED-023 | TARGET_MARKER_MISMATCH | DEGRADED | target_marker_replace_v1.0 | 1 |
| MUT-070 | SEED-024 | REQUIRED_INFORMATION_OMISSION | EQUIVALENT | equivalent_formatting_v1.0 | 1 |
| MUT-071 | SEED-024 | REQUIRED_INFORMATION_OMISSION | DEGRADED | omission_delete_duration_v1.0 | 1 |
| MUT-072 | SEED-024 | SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | sample_method_scope_v1.0 | 1 |
