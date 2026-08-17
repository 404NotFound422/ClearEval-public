# PAPER_METHODS_TEXT -- counterfactual validity of the ClearEval evaluator

ClearEval does not require a unique reference protocol text: questions are scored against the frozen scoring rubric and knowledge bases without a single 'gold' protocol. To validate that the evaluator actually tracks protocol quality (rather than wording), we build a local counterfactual overlay: for each selected (question x model) response we construct one semantics-preserving variant and two single-defect variants per seed (72 pairs total, 24 seeds), all generated deterministically from span-level edits grounded in the frozen knowledge bases. Each pair is scored under a role-blind protocol: the original and the mutated text are scored in fully independent judge calls that see only the question and one protocol text, never the pair structure or the expected relation.

Validity is measured along 9.1-9.7: directional accuracy (does the expected component decrease or a hard failure appear), metamorphic invariance (semantics-preserving changes leave scores within an empirically-derived tolerance), component localization, fatal false-PASS, judge-expert chance-corrected agreement, test-retest stability, and explicit coverage of every missing/failed case. The structured DiagnosticAudit's added value is argued only through localization, hard-fail detection, and reproducibility -- never through an unverifiable total score.

Scientific claim (as far as this artefact goes):

> ClearEval does not require a unique reference protocol text, but its evaluator is designed to be validated against expert-reviewed local counterfactual relations, evidence-backed constraints, and blind test cases. Validation results are pending expert review of the counterfactual review package and a role-blind judge run.
