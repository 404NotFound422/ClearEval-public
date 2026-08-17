# JUDGE_VALIDITY -- evaluator counterfactual-validity metrics (9.1-9.7)

- reference source : `provisional` (gold = expert-reviewed; provisional = mutation proposals)
- pending metrics  : ['9.1', '9.2', '9.3', '9.4', '9.5', '9.6', '9.7']

> **State: pending-data.** The suite currently has **no expert-reviewed gold and no judge runs**; every metric below reports what would be measured and marks current values as pending. No number here is a claim about evaluator validity. Verdict is recomputed after the blind run.

## 9.1 Directional accuracy (degrading pairs)

For every degrading pair: did the expected CCE component decrease (mutated < original) or did the judge detect a hard failure? Floor cases (the component is already at its deterministic floor, so no observable decrease exists) are counted separately and are **not** credited as correct.

- degrading pairs      : 32
- correct              : 0
- incorrect            : 0  (floor-limited: 0)
- pending/unscored     : 32
- accuracy (assessable): pending

## 9.2 Metamorphic invariance (EQUIVALENT pairs)

- tolerance estimator : 95th percentile of |repeat - first| absolute deviations (empirical, not a fixed epsilon)
- EQUIVALENT pairs    : 16  (scored both sides: 0)
| component | n | mean|delta| | max|delta| | empirical tolerance | within tolerance |
|---|---|---|---|---|---|
| s_label | 0 | pending | pending | pending | 0 |
| s_trans | 0 | pending | pending | pending | 0 |
| s_method | 0 | pending | pending | pending | 0 |
| s_time | 0 | pending | pending | pending | 0 |
| completeness.total | 0 | pending | pending | pending | 0 |
| correctness.total | 0 | pending | pending | pending | 0 |

- deviation source: n/a (no repeats)

## 9.3 Component localization (vs reviewed gold)

- gold pairs     : 0   pending: 48
- affected-component accuracy : pending
- location exact accuracy     : pending
- location overlap accuracy   : pending
- reason-code accuracy        : pending

## 9.4 Fatal false-PASS (expert HARD_FAIL accepted)

- HARD_FAIL gold pairs : 0  detected: 0  false-pass: 0  pending: 0 (metric pending: no HARD_FAIL gold)
- fatal false-pass rate: pending

## 9.5 Judge-expert agreement (chance-corrected)

- judge vs expert A : n=0 raw=pending kappa=pending weighted=pending alpha=pending
- expert A vs B     : n=0 raw=pending kappa=pending alpha=pending

## 9.6 Test-retest stability (N independent runs)

- groups : 0  calls: 0  invalid-output rate: pending
- relation-consistent groups   : 0
- component-consistent groups  : 0
- per-component variance       : {}
- requires >= 2 repeat groups with judge findings

## 9.7 Coverage (missing / failed / unscored, never imputed)

- audit rows: 96  cce rows: 96  gold rows: 0  proposals: 48
- unscored audit rows : 96
  - DEV-MUT-001/original: judge_pending
  - DEV-MUT-001/mutated: judge_pending
  - DEV-MUT-002/original: judge_pending
  - DEV-MUT-002/mutated: judge_pending
  - DEV-MUT-003/original: judge_pending
  - DEV-MUT-003/mutated: judge_pending
  - DEV-MUT-004/original: judge_pending
  - DEV-MUT-004/mutated: judge_pending
  - DEV-MUT-005/original: judge_pending
  - DEV-MUT-005/mutated: judge_pending
  - DEV-MUT-006/original: judge_pending
  - DEV-MUT-006/mutated: judge_pending
  - DEV-MUT-007/original: judge_pending
  - DEV-MUT-007/mutated: judge_pending
  - DEV-MUT-008/original: judge_pending
  - DEV-MUT-008/mutated: judge_pending
  - DEV-MUT-009/original: judge_pending
  - DEV-MUT-009/mutated: judge_pending
  - DEV-MUT-010/original: judge_pending
  - DEV-MUT-010/mutated: judge_pending
  - DEV-MUT-011/original: judge_pending
  - DEV-MUT-011/mutated: judge_pending
  - DEV-MUT-012/original: judge_pending
  - DEV-MUT-012/mutated: judge_pending
  - DEV-MUT-013/original: judge_pending
  - DEV-MUT-013/mutated: judge_pending
  - DEV-MUT-014/original: judge_pending
  - DEV-MUT-014/mutated: judge_pending
  - DEV-MUT-015/original: judge_pending
  - DEV-MUT-015/mutated: judge_pending
  - DEV-MUT-016/original: judge_pending
  - DEV-MUT-016/mutated: judge_pending
  - DEV-MUT-017/original: judge_pending
  - DEV-MUT-017/mutated: judge_pending
  - DEV-MUT-018/original: judge_pending
  - DEV-MUT-018/mutated: judge_pending
  - DEV-MUT-019/original: judge_pending
  - DEV-MUT-019/mutated: judge_pending
  - DEV-MUT-020/original: judge_pending
  - DEV-MUT-020/mutated: judge_pending
  - DEV-MUT-021/original: judge_pending
  - DEV-MUT-021/mutated: judge_pending
  - DEV-MUT-022/original: judge_pending
  - DEV-MUT-022/mutated: judge_pending
  - DEV-MUT-023/original: judge_pending
  - DEV-MUT-023/mutated: judge_pending
  - DEV-MUT-024/original: judge_pending
  - DEV-MUT-024/mutated: judge_pending
  - DEV-MUT-025/original: judge_pending
  - DEV-MUT-025/mutated: judge_pending
  - DEV-MUT-026/original: judge_pending
  - DEV-MUT-026/mutated: judge_pending
  - DEV-MUT-027/original: judge_pending
  - DEV-MUT-027/mutated: judge_pending
  - DEV-MUT-028/original: judge_pending
  - DEV-MUT-028/mutated: judge_pending
  - DEV-MUT-029/original: judge_pending
  - DEV-MUT-029/mutated: judge_pending
  - DEV-MUT-030/original: judge_pending
  - DEV-MUT-030/mutated: judge_pending
  - DEV-MUT-031/original: judge_pending
  - DEV-MUT-031/mutated: judge_pending
  - DEV-MUT-032/original: judge_pending
  - DEV-MUT-032/mutated: judge_pending
  - DEV-MUT-033/original: judge_pending
  - DEV-MUT-033/mutated: judge_pending
  - DEV-MUT-034/original: judge_pending
  - DEV-MUT-034/mutated: judge_pending
  - DEV-MUT-035/original: judge_pending
  - DEV-MUT-035/mutated: judge_pending
  - DEV-MUT-036/original: judge_pending
  - DEV-MUT-036/mutated: judge_pending
  - DEV-MUT-037/original: judge_pending
  - DEV-MUT-037/mutated: judge_pending
  - DEV-MUT-038/original: judge_pending
  - DEV-MUT-038/mutated: judge_pending
  - DEV-MUT-039/original: judge_pending
  - DEV-MUT-039/mutated: judge_pending
  - DEV-MUT-040/original: judge_pending
  - DEV-MUT-040/mutated: judge_pending
  - DEV-MUT-041/original: judge_pending
  - DEV-MUT-041/mutated: judge_pending
  - DEV-MUT-042/original: judge_pending
  - DEV-MUT-042/mutated: judge_pending
  - DEV-MUT-043/original: judge_pending
  - DEV-MUT-043/mutated: judge_pending
  - DEV-MUT-044/original: judge_pending
  - DEV-MUT-044/mutated: judge_pending
  - DEV-MUT-045/original: judge_pending
  - DEV-MUT-045/mutated: judge_pending
  - DEV-MUT-046/original: judge_pending
  - DEV-MUT-046/mutated: judge_pending
  - DEV-MUT-047/original: judge_pending
  - DEV-MUT-047/mutated: judge_pending
  - DEV-MUT-048/original: judge_pending
  - DEV-MUT-048/mutated: judge_pending
- unscored cce rows   : 48
  - DEV-MUT-001/mutated: judge_missing
  - DEV-MUT-002/mutated: judge_missing
  - DEV-MUT-003/mutated: judge_missing
  - DEV-MUT-004/mutated: judge_missing
  - DEV-MUT-005/mutated: judge_missing
  - DEV-MUT-006/mutated: judge_missing
  - DEV-MUT-007/mutated: judge_missing
  - DEV-MUT-008/mutated: judge_missing
  - DEV-MUT-009/mutated: judge_missing
  - DEV-MUT-010/mutated: judge_missing
  - DEV-MUT-011/mutated: judge_missing
  - DEV-MUT-012/mutated: judge_missing
  - DEV-MUT-013/mutated: judge_missing
  - DEV-MUT-014/mutated: judge_missing
  - DEV-MUT-015/mutated: judge_missing
  - DEV-MUT-016/mutated: judge_missing
  - DEV-MUT-017/mutated: judge_missing
  - DEV-MUT-018/mutated: judge_missing
  - DEV-MUT-019/mutated: judge_missing
  - DEV-MUT-020/mutated: judge_missing
  - DEV-MUT-021/mutated: judge_missing
  - DEV-MUT-022/mutated: judge_missing
  - DEV-MUT-023/mutated: judge_missing
  - DEV-MUT-024/mutated: judge_missing
  - DEV-MUT-025/mutated: judge_missing
  - DEV-MUT-026/mutated: judge_missing
  - DEV-MUT-027/mutated: judge_missing
  - DEV-MUT-028/mutated: judge_missing
  - DEV-MUT-029/mutated: judge_missing
  - DEV-MUT-030/mutated: judge_missing
  - DEV-MUT-031/mutated: judge_missing
  - DEV-MUT-032/mutated: judge_missing
  - DEV-MUT-033/mutated: judge_missing
  - DEV-MUT-034/mutated: judge_missing
  - DEV-MUT-035/mutated: judge_missing
  - DEV-MUT-036/mutated: judge_missing
  - DEV-MUT-037/mutated: judge_missing
  - DEV-MUT-038/mutated: judge_missing
  - DEV-MUT-039/mutated: judge_missing
  - DEV-MUT-040/mutated: judge_missing
  - DEV-MUT-041/mutated: judge_missing
  - DEV-MUT-042/mutated: judge_missing
  - DEV-MUT-043/mutated: judge_missing
  - DEV-MUT-044/mutated: judge_missing
  - DEV-MUT-045/mutated: judge_missing
  - DEV-MUT-046/mutated: judge_missing
  - DEV-MUT-047/mutated: judge_missing
  - DEV-MUT-048/mutated: judge_missing
- missing audit pairs : 0 []
- missing cce pairs   : 0 []
- missing gold pairs  : 48
- non-adjudicated gold rows: 0

## Baselines comparison (A/B/C -- generated from data)

- pending: True  (A/B/C are generated from the per-baseline signal present in the auditing artefacts. Pending rows mean the input data for that baseline does not exist yet (no judge runs / no gold) -- no number is imputed.)

| baseline | scorers | structured fields | 9.1 acc | 9.2 within-tol% | 9.3 loc acc | 9.4 false-pass | observation |
|---|---|---|---|---|---|---|---|
| A | CCE | none | pending | pending | pending | pending | reference floor: does CCE alone separate defects from EQUIVALENT changes? Weakest for localization and hard-fail recall. |
| B | CCE + free-text reasoning | free-text | pending | pending | pending | pending | adds qualitative signal; not machine-checkable; not reproducible field-by-field. Manual read of free-text (not machine-checkable). |
| C | CCE + structured DiagnosticAudit | evidence/relation/affected_component/type/location/reason_code/next_action | pending | pending | pending | pending | structured audit is argued ONLY via localization, hard-fail detection, and reproducibility -- never an unverifiable total score. |
