# PAPER_LIMITATIONS_TEXT -- counterfactual-validity limitations

- **No laboratory validation.** All scorer outputs under validation are automarked; none of the 24 selected seeds or their counterfactual variants have been wet-lab verified.
- **Expert review pending.** `reviewed_gold.jsonl` is empty (0 rows); the gold-referenced metrics (9.3/9.4/9.5) are pending until two independent experts label the 72-pair review package and adjudication is recorded (PENDING_REVIEW -> APPROVED_GOLD).
- **Judge runs pending / frozen-data constraints.** The validity metrics are pending judge runs; the split is frozen at selection time (`split_seed 20260817`) and the prompt revision must be frozen before any blind run. Improvement/tuning of the prompt is not performed after blind results.
- **Eligibility-pool skew (documented in the Task 1 report).** Only 71 of 3289 frozen (question, model) pairs were eligible under the mechanical rule that `critical_warnings` be empty/absent; the corpus is skewed toward gpt-5.2-class models and 3 models have zero eligible candidates. The 24 seeds cannot represent models with no eligible candidates, by construction.
- **Deterministic effectiveness re-derivation diverges from production.** Mutated texts are scored by a rule-based re-derivation whose deterministic extraction of `method_name` / `marker_dict` / clearing time differs from the teacher's extraction, so absolute effectiveness values for mutated texts are not production-identical (directional behaviour is the target). The seeded ORIGINAL side on the audit path uses the frozen production CCE record, but any local re-derivation of an original's effectiveness can likewise diverge from the frozen totals; only the frozen seed CCE is bit-exact production. No new ClearEval total score is introduced anywhere.

Scientific claim scope:

> ClearEval does not require a unique reference protocol text, but its evaluator is designed to be validated against expert-reviewed local counterfactual relations, evidence-backed constraints, and blind test cases. Validation results are pending expert review of the counterfactual review package and a role-blind judge run.
