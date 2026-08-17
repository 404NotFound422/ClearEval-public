# GO/NO-GO -- evaluator validation verdict

## Verdict rule (documented)

1. **SUPPORTED** -- only when the *blind* results show all of: (a) correct directional behaviour (9.1 accuracy >= 0.8), (b) acceptable invariance (9.2: >= 80% of EQUIVALENT pairs within the empirical tolerance), (c) low fatal false-PASS (9.4 rate <= 0.1), (d) useful localization (9.3 affected-component accuracy >= 0.7).
2. **FAILED_VALIDATION** -- evidence shows the evaluator cannot reliably distinguish controlled defects from semantics-preserving changes (systematically wrong direction AND broken invariance AND high fatal false-PASS).
3. **LIMITED** -- everything else, including when blind evidence does not exist.

## Current state

- **No expert-reviewed gold exists** (`reviewed_gold.jsonl` is empty: 0 rows).
- **No judge runs exist** (offline pending state: every DiagnosticAudit call is `judge_pending`; Completeness/Correctness for mutated protocols are `judge_missing` without fixtures or an online teacher).
- Blind split (8 seeds / 24 pairs) has **not** been run (`frozen_prompt_sha256` is null).
- Pending metrics: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
- Human review (two independent experts -> adjudication -> APPROVED_GOLD) and judge runs are required before the verdict is recomputed.
- **No prompt tuning** is performed after blind results are produced.

LIMITED