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
| s_time | 0 | pending | pending | pending | 0 |
| s_trans | 0 | pending | pending | pending | 0 |
| s_method | 0 | pending | pending | pending | 0 |
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

- HARD_FAIL gold pairs : 0  detected: 0  false-pass: 0  pending: 0
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
  - MUT-001/original: judge_pending
  - MUT-001/mutated: judge_pending
  - MUT-002/original: judge_pending
  - MUT-002/mutated: judge_pending
  - MUT-003/original: judge_pending
  - MUT-003/mutated: judge_pending
  - MUT-004/original: judge_pending
  - MUT-004/mutated: judge_pending
  - MUT-005/original: judge_pending
  - MUT-005/mutated: judge_pending
  - MUT-006/original: judge_pending
  - MUT-006/mutated: judge_pending
  - MUT-007/original: judge_pending
  - MUT-007/mutated: judge_pending
  - MUT-008/original: judge_pending
  - MUT-008/mutated: judge_pending
  - MUT-009/original: judge_pending
  - MUT-009/mutated: judge_pending
  - MUT-010/original: judge_pending
  - MUT-010/mutated: judge_pending
  - MUT-011/original: judge_pending
  - MUT-011/mutated: judge_pending
  - MUT-012/original: judge_pending
  - MUT-012/mutated: judge_pending
  - MUT-013/original: judge_pending
  - MUT-013/mutated: judge_pending
  - MUT-014/original: judge_pending
  - MUT-014/mutated: judge_pending
  - MUT-015/original: judge_pending
  - MUT-015/mutated: judge_pending
  - MUT-016/original: judge_pending
  - MUT-016/mutated: judge_pending
  - MUT-017/original: judge_pending
  - MUT-017/mutated: judge_pending
  - MUT-018/original: judge_pending
  - MUT-018/mutated: judge_pending
  - MUT-019/original: judge_pending
  - MUT-019/mutated: judge_pending
  - MUT-020/original: judge_pending
  - MUT-020/mutated: judge_pending
  - MUT-021/original: judge_pending
  - MUT-021/mutated: judge_pending
  - MUT-022/original: judge_pending
  - MUT-022/mutated: judge_pending
  - MUT-023/original: judge_pending
  - MUT-023/mutated: judge_pending
  - MUT-024/original: judge_pending
  - MUT-024/mutated: judge_pending
  - MUT-025/original: judge_pending
  - MUT-025/mutated: judge_pending
  - MUT-026/original: judge_pending
  - MUT-026/mutated: judge_pending
  - MUT-027/original: judge_pending
  - MUT-027/mutated: judge_pending
  - MUT-028/original: judge_pending
  - MUT-028/mutated: judge_pending
  - MUT-029/original: judge_pending
  - MUT-029/mutated: judge_pending
  - MUT-030/original: judge_pending
  - MUT-030/mutated: judge_pending
  - MUT-031/original: judge_pending
  - MUT-031/mutated: judge_pending
  - MUT-032/original: judge_pending
  - MUT-032/mutated: judge_pending
  - MUT-033/original: judge_pending
  - MUT-033/mutated: judge_pending
  - MUT-034/original: judge_pending
  - MUT-034/mutated: judge_pending
  - MUT-035/original: judge_pending
  - MUT-035/mutated: judge_pending
  - MUT-036/original: judge_pending
  - MUT-036/mutated: judge_pending
  - MUT-037/original: judge_pending
  - MUT-037/mutated: judge_pending
  - MUT-038/original: judge_pending
  - MUT-038/mutated: judge_pending
  - MUT-039/original: judge_pending
  - MUT-039/mutated: judge_pending
  - MUT-040/original: judge_pending
  - MUT-040/mutated: judge_pending
  - MUT-041/original: judge_pending
  - MUT-041/mutated: judge_pending
  - MUT-042/original: judge_pending
  - MUT-042/mutated: judge_pending
  - MUT-043/original: judge_pending
  - MUT-043/mutated: judge_pending
  - MUT-044/original: judge_pending
  - MUT-044/mutated: judge_pending
  - MUT-045/original: judge_pending
  - MUT-045/mutated: judge_pending
  - MUT-046/original: judge_pending
  - MUT-046/mutated: judge_pending
  - MUT-047/original: judge_pending
  - MUT-047/mutated: judge_pending
  - MUT-048/original: judge_pending
  - MUT-048/mutated: judge_pending
- unscored cce rows   : 48
  - MUT-001/mutated: judge_missing
  - MUT-002/mutated: judge_missing
  - MUT-003/mutated: judge_missing
  - MUT-004/mutated: judge_missing
  - MUT-005/mutated: judge_missing
  - MUT-006/mutated: judge_missing
  - MUT-007/mutated: judge_missing
  - MUT-008/mutated: judge_missing
  - MUT-009/mutated: judge_missing
  - MUT-010/mutated: judge_missing
  - MUT-011/mutated: judge_missing
  - MUT-012/mutated: judge_missing
  - MUT-013/mutated: judge_missing
  - MUT-014/mutated: judge_missing
  - MUT-015/mutated: judge_missing
  - MUT-016/mutated: judge_missing
  - MUT-017/mutated: judge_missing
  - MUT-018/mutated: judge_missing
  - MUT-019/mutated: judge_missing
  - MUT-020/mutated: judge_missing
  - MUT-021/mutated: judge_missing
  - MUT-022/mutated: judge_missing
  - MUT-023/mutated: judge_missing
  - MUT-024/mutated: judge_missing
  - MUT-025/mutated: judge_missing
  - MUT-026/mutated: judge_missing
  - MUT-027/mutated: judge_missing
  - MUT-028/mutated: judge_missing
  - MUT-029/mutated: judge_missing
  - MUT-030/mutated: judge_missing
  - MUT-031/mutated: judge_missing
  - MUT-032/mutated: judge_missing
  - MUT-033/mutated: judge_missing
  - MUT-034/mutated: judge_missing
  - MUT-035/mutated: judge_missing
  - MUT-036/mutated: judge_missing
  - MUT-037/mutated: judge_missing
  - MUT-038/mutated: judge_missing
  - MUT-039/mutated: judge_missing
  - MUT-040/mutated: judge_missing
  - MUT-041/mutated: judge_missing
  - MUT-042/mutated: judge_missing
  - MUT-043/mutated: judge_missing
  - MUT-044/mutated: judge_missing
  - MUT-045/mutated: judge_missing
  - MUT-046/mutated: judge_missing
  - MUT-047/mutated: judge_missing
  - MUT-048/mutated: judge_missing
- missing gold pairs  : 48

## Baselines comparison (experimental design; values pending)

| baseline | scorers used | structured fields | localization/hard-fail tests | expected added value of (C) vs (A)/(B) |
|---|---|---|---|---|
| A | CCE scalar/component only | none | none | reference floor: does CCE alone separate defects from EQUIVALENT changes? Weakest for localization and hard-fail recall. |
| B | CCE + free-text teacher reasoning | free-text reasoning string | manual read of reasoning | adds qualitative signal; not machine-checkable; not reproducible field-by-field. |
| C | CCE + structured DiagnosticAudit (this overlay) | evidence_status/relation/affected_component/violation_type/location/reason_code/next_action | 9.3 localization, 9.4 hard-fail detection, 9.6/9.2 reproducibility | the structured audit's value is argued ONLY via localization accuracy, hard-fail detection, and reproducibility -- never via an unverifiable total score. |
