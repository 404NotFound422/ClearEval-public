"""ClearEval counterfactual-validity overlay -- judge-validity report generator
(Task 3, deliverable 5: report_judge_validity.py).

Generates, from the audit/scoring outputs + reviewed gold:
- ``reports/JUDGE_VALIDITY.md``        -- metrics 9.1-9.7 plus the A/B/C
                                          baselines comparison (CCE-only /
                                          CCE+free-text reasoning /
                                          CCE+structured DiagnosticAudit).
- ``reports/BLIND_RESULTS.md``         -- blind-split results (or their absence).
- ``reports/GO_NO_GO.md``              -- ends with EXACTLY ONE line containing
                                          ``SUPPORTED`` / ``LIMITED`` /
                                          ``FAILED_VALIDATION``.
- ``reports/PAPER_TABLE_COUNTERFACTUAL_VALIDITY.csv``
- ``reports/PAPER_FIGURE_PAIRED_SHIFTS.csv`` (paired per-pair score shifts)
- ``reports/PAPER_METHODS_TEXT.md`` / ``PAPER_LIMITATIONS_TEXT.md``
- ``manifests/review_package.jsonl``   -- one row per pair (72) with label
                                          fields for two independent experts.

Scientific-claim discipline (no new total score, no lab-validation claims):
the paper-adjacent claim is exactly:
    "ClearEval does not require a unique reference protocol text, but its
     evaluator is validated against expert-reviewed local counterfactual
     relations, evidence-backed constraints, and blind test cases."
No ClearEval total score is introduced anywhere.

GO_NO_GO verdict rule (documented in GO_NO_GO.md and below):
- SUPPORTED       : blind results exist AND show correct directional behavior
                    AND acceptable invariance AND low fatal false-PASS AND
                    useful localization.
- FAILED_VALIDATION : evidence shows the evaluator cannot reliably distinguish
                    controlled defects from semantics-preserving changes.
- LIMITED (default): everything else -- including when blind evidence does not
                    yet exist.  The current suite state has no expert-reviewed
                    gold and no judge runs, so the generated GO_NO_GO.md states
                    that plainly and notes the verdict is recomputed after the
                    blind run, with no prompt tuning after blind results.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

try:  # package context
    from .mutation_registry import MutationRegistry
    from .run_diagnostic_audit import DEFAULT_SPLIT_PATH, run_audit
    from .score_counterfactual_relations import compute_all
    from .schemas import ExpectedRelation, ComponentId
except ImportError:
    _PKG_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _PKG_DIR)
    from mutation_registry import MutationRegistry  # type: ignore
    from run_diagnostic_audit import DEFAULT_SPLIT_PATH, run_audit  # type: ignore
    from score_counterfactual_relations import compute_all  # type: ignore
    from schemas import ComponentId, ExpectedRelation  # type: ignore

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))

REPORTS_DIR = os.path.join(PKG_DIR, "reports")
MANIFESTS_DIR = os.path.join(PKG_DIR, "manifests")

DEFAULT_DEV_PROPOSALS = os.path.join(MANIFESTS_DIR, "mutation_proposals_development.jsonl")
DEFAULT_DEV_GOLD_STUB = os.path.join(MANIFESTS_DIR, "dev_reviewed_gold.jsonl")
DEFAULT_DEV_AUDIT_RUNS = os.path.join(MANIFESTS_DIR, "dev_audit_runs.jsonl")
DEFAULT_DEV_CCE_SCORES = os.path.join(MANIFESTS_DIR, "dev_cce_scores.jsonl")
DEFAULT_REVIEW_PACKAGE = os.path.join(MANIFESTS_DIR, "review_package.jsonl")

PROMISED_CLAIM = (
    "ClearEval does not require a unique reference protocol text, but its "
    "evaluator is validated against expert-reviewed local counterfactual "
    "relations, evidence-backed constraints, and blind test cases."
)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def verdict(metrics: Dict[str, Any], blind_results: Optional[Dict[str, Any]] = None) -> str:
    """GO_NO_GO verdict per the documented rule.

    ``blind_results``: the blind-split metrics/audit summary (None when the
    blind split has not been run).  In the current suite state it is always
    None -> the verdict is LIMITED and GO_NO_GO states why.
    """
    if blind_results is None:
        return "LIMITED"
    m91 = metrics.get("9.1_directional_accuracy", {})
    m92 = metrics.get("9.2_metamorphic_invariance", {})
    m94 = metrics.get("9.4_fatal_false_pass", {})
    m93 = metrics.get("9.3_component_localization", {})
    # SUPPORTED only when: correct directional behavior + acceptable invariance
    # + low fatal false-PASS + useful localization, all on blind evidence.
    directional_ok = m91.get("accuracy_assessable") is not None and m91["accuracy_assessable"] >= 0.8
    invariance_ok = _invariance_ok(m92)
    false_pass_ok = (m94.get("fatal_false_pass_rate") is not None
                     and m94["fatal_false_pass_rate"] <= 0.1)
    localization_ok = (m93.get("affected_component_accuracy") is not None
                       and m93["affected_component_accuracy"] >= 0.7)
    if directional_ok and invariance_ok and false_pass_ok and localization_ok:
        return "SUPPORTED"
    # FAILED_VALIDATION: evidence shows the evaluator cannot reliably separate
    # controlled defects from semantics-preserving changes.
    if _evidence_of_failure(m91, m92, m94):
        return "FAILED_VALIDATION"
    return "LIMITED"


def _invariance_ok(m92: Dict[str, Any]) -> bool:
    """Acceptable invariance: >=80% of EQUIVALENT pairs within the empirical
    tolerance on every rule-based component with data."""
    per = m92.get("per_component", {})
    scored = [c for c in per.values() if c.get("n_pairs_with_scores")]
    if not scored:
        return False
    return all(c["n_within_tolerance"] >= 0.8 * c["n_pairs_with_scores"] for c in scored)


def _evidence_of_failure(m91: Dict[str, Any], m92: Dict[str, Any], m94: Dict[str, Any]) -> bool:
    """Heuristic evidence of FAILED_VALIDATION: systematically wrong direction
    AND invariance broken AND fatal false-PASS high."""
    directional_very_bad = (m91.get("accuracy_assessable") is not None
                            and m91["accuracy_assessable"] <= 0.5)
    invariance_bad = not _invariance_ok(m92) and any(
        c.get("max_abs_delta") and c["max_abs_delta"] > 1e-3
        for c in m92.get("per_component", {}).values())
    false_pass_very_bad = (m94.get("fatal_false_pass_rate") is not None
                           and m94["fatal_false_pass_rate"] >= 0.5)
    return directional_very_bad and invariance_bad and false_pass_very_bad


# ---------------------------------------------------------------------------
# Review package
# ---------------------------------------------------------------------------


def write_review_package(path: str = DEFAULT_REVIEW_PACKAGE,
                         proposals_path: Optional[str] = None,
                         seeds_path: Optional[str] = None,
                         split_path: str = DEFAULT_SPLIT_PATH) -> List[Dict[str, Any]]:
    """One row per pair (72) with empty expert-label fields.

    The row documents the pair identity + programmatic expectation and leaves
    every *label* field empty for two independent experts to fill:
      seed_suitable_for_local_counterfactual_testing,
      mutation_scientifically_valid, expected_relation,
      affected_cc_component, violation_location, hard_fail_status,
      minimal_next_action, supporting_rule_or_evidence_ids.

    Label fields are intentionally *not_blanked differently* by expert slot;
    experts get separate copies (e.g. review_package_expert_A.jsonl /
    _expert_B.jsonl) so their judgments stay independent.  The actual
    raw-agreement / kappa statistics are computed by
    ``score_counterfactual_relations.judge_expert_agreement`` once two expert
    label files exist (documented hook: run that function with the two files).
    """
    proposals_path = proposals_path or os.path.join(MANIFESTS_DIR, "mutation_proposals.jsonl")
    seeds_path = seeds_path or os.path.join(MANIFESTS_DIR, "seed_candidates.jsonl")
    registry = MutationRegistry(role="blind", split_path=split_path,
                                proposals_path=proposals_path, seed_path=seeds_path)
    proposals = registry.load_proposals()
    rows: List[Dict[str, Any]] = []
    for p in proposals:
        rows.append({
            "pair_id": p.pair_id,
            "seed_id": p.seed_id,
            "question_id": p.question_id,
            "scenario_type": p.scenario_type.value,
            "mutation_family": p.mutation_family.value,
            "operator_version": p.mutation_operator_version,
            "expected_relation": p.expected_relation.value,          # programmatic expectation (for reference)
            "expected_affected_components": [c.value for c in p.expected_affected_components],
            "expected_location": p.expected_location,
            "expected_severity": p.expected_severity.value,
            "supporting_rule_or_evidence_ids": list(p.supporting_rule_or_evidence_ids),
            # ---- expert label fields (EMPTY until reviewed) ----
            "reviewer_A_seed_suitable_for_local_counterfactual_testing": None,
            "reviewer_A_mutation_scientifically_valid": None,
            "reviewer_A_expected_relation": None,
            "reviewer_A_affected_cc_component": None,
            "reviewer_A_violation_location": "",
            "reviewer_A_hard_fail_status": None,
            "reviewer_A_minimal_next_action": None,
            "reviewer_A_supporting_rule_or_evidence_ids": [],
            "reviewer_B_seed_suitable_for_local_counterfactual_testing": None,
            "reviewer_B_mutation_scientifically_valid": None,
            "reviewer_B_expected_relation": None,
            "reviewer_B_affected_cc_component": None,
            "reviewer_B_violation_location": "",
            "reviewer_B_hard_fail_status": None,
            "reviewer_B_minimal_next_action": None,
            "reviewer_B_supporting_rule_or_evidence_ids": [],
            "_review_filled": False,
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def fmt_opt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "pending"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_judge_validity_md(metrics: Dict[str, Any],
                             pending_note: bool = True) -> str:
    lines: List[str] = []
    lines.append("# JUDGE_VALIDITY -- evaluator counterfactual-validity metrics (9.1-9.7)")
    lines.append("")
    lines.append(f"- reference source : `{metrics.get('reference_source', 'n/a')}` "
                 "(gold = expert-reviewed; provisional = mutation proposals)")
    lines.append(f"- pending metrics  : {metrics.get('pending_metrics')}")
    lines.append("")
    if pending_note:
        lines.append("> **State: pending-data.** The suite currently has **no expert-reviewed gold "
                     "and no judge runs**; every metric below reports what would be measured and "
                     "marks current values as pending. No number here is a claim about evaluator "
                     "validity. Verdict is recomputed after the blind run.")
        lines.append("")

    m91 = metrics["9.1_directional_accuracy"]
    lines.append("## 9.1 Directional accuracy (degrading pairs)")
    lines.append("")
    lines.append("For every degrading pair: did the expected CCE component decrease (mutated < "
                 "original) or did the judge detect a hard failure? Floor cases (the component is "
                 "already at its deterministic floor, so no observable decrease exists) are counted "
                 "separately and are **not** credited as correct.")
    lines.append("")
    lines.append(f"- degrading pairs      : {m91['n_degrading_pairs']}")
    lines.append(f"- correct              : {m91['n_correct']}")
    lines.append(f"- incorrect            : {m91['n_incorrect']}  (floor-limited: {m91['n_floor_only']})")
    lines.append(f"- pending/unscored     : {m91['n_pending']}")
    lines.append(f"- accuracy (assessable): {fmt_opt(m91['accuracy_assessable'])}")
    if m91["floor_pair_ids"]:
        lines.append(f"- floor pair ids       : {m91['floor_pair_ids']}")
    lines.append("")

    m92 = metrics["9.2_metamorphic_invariance"]
    lines.append("## 9.2 Metamorphic invariance (EQUIVALENT pairs)")
    lines.append("")
    lines.append(f"- tolerance estimator : {m92['tolerance_estimator']}")
    lines.append(f"- EQUIVALENT pairs    : {m92['n_equivalent_pairs']}  (scored both sides: {m92['n_pairs_scored_both_sides']})")
    lines.append("| component | n | mean|delta| | max|delta| | empirical tolerance | within tolerance |")
    lines.append("|---|---|---|---|---|---|")
    for field, c in m92["per_component"].items():
        lines.append(
            f"| {field} | {c['n_pairs_with_scores']} | "
            f"{fmt_opt(c['mean_abs_delta'])} | {fmt_opt(c['max_abs_delta'])} | "
            f"{fmt_opt(c['empirical_tolerance'])} | {c['n_within_tolerance']} |")
    lines.append("")
    lines.append(f"- deviation source: {m92['per_component'].get('s_method', {}).get('deviation_source', 'n/a')}")
    lines.append("")

    m93 = metrics["9.3_component_localization"]
    lines.append("## 9.3 Component localization (vs reviewed gold)")
    lines.append("")
    lines.append(f"- gold pairs     : {m93['n_gold_pairs']}   pending: {m93['n_pending']}")
    lines.append(f"- affected-component accuracy : {fmt_opt(m93['affected_component_accuracy'])}")
    lines.append(f"- location exact accuracy     : {fmt_opt(m93['location_exact_accuracy'])}")
    lines.append(f"- location overlap accuracy   : {fmt_opt(m93['location_overlap_accuracy'])}")
    lines.append(f"- reason-code accuracy        : {fmt_opt(m93['reason_code_accuracy'])}")
    lines.append("")

    m94 = metrics["9.4_fatal_false_pass"]
    lines.append("## 9.4 Fatal false-PASS (expert HARD_FAIL accepted)")
    lines.append("")
    lines.append(f"- HARD_FAIL gold pairs : {m94['n_hard_fail_gold']}  detected: {m94['n_detected']}  "
                 f"false-pass: {m94['n_false_pass']}  pending: {m94['n_pending']}")
    lines.append(f"- fatal false-pass rate: {fmt_opt(m94['fatal_false_pass_rate'])}")
    lines.append("")

    m95 = metrics["9.5_judge_expert_agreement"]
    lines.append("## 9.5 Judge-expert agreement (chance-corrected)")
    lines.append("")
    jv = m95.get("judge_vs_expert_A", {})
    lines.append(f"- judge vs expert A : n={jv.get('n')} raw={fmt_opt(jv.get('raw_agreement'))} "
                 f"kappa={fmt_opt(jv.get('cohen_kappa'))} weighted={fmt_opt(jv.get('weighted_kappa_linear'))} "
                 f"alpha={fmt_opt(jv.get('krippendorff_alpha'))}")
    ev = m95.get("expert_A_vs_expert_B", {})
    lines.append(f"- expert A vs B     : n={ev.get('n')} raw={fmt_opt(ev.get('raw_agreement'))} "
                 f"kappa={fmt_opt(ev.get('cohen_kappa'))} alpha={fmt_opt(ev.get('krippendorff_alpha'))}")
    lines.append("")

    m96 = metrics["9.6_test_retest_stability"]
    lines.append("## 9.6 Test-retest stability (N independent runs)")
    lines.append("")
    lines.append(f"- groups : {m96['n_groups']}  calls: {m96['n_calls']}  "
                 f"invalid-output rate: {fmt_opt(m96['invalid_output_rate'])}")
    lines.append(f"- relation-consistent groups   : {m96['n_groups_relation_consistent']}")
    lines.append(f"- component-consistent groups  : {m96['n_groups_component_consistent']}")
    lines.append(f"- per-component variance       : {m96['per_component_variance']}")
    lines.append(f"- {m96.get('coverage_note', '')}")
    lines.append("")

    m97 = metrics["9.7_coverage"]
    lines.append("## 9.7 Coverage (missing / failed / unscored, never imputed)")
    lines.append("")
    lines.append(f"- audit rows: {m97['n_audit_rows']}  cce rows: {m97['n_cce_rows']}  "
                 f"gold rows: {m97['n_gold_pairs']}  proposals: {m97['n_proposals']}")
    bad_audits = m97["bad_audit_rows"]
    bad_cce = m97["bad_cce_rows"]
    lines.append(f"- unscored audit rows : {len(bad_audits)}")
    for r in bad_audits[:500]:
        lines.append(f"  - {r.get('pair_id')}/{r.get('side')}: {r.get('status')}"
                     + (f" ({r.get('error')})" if r.get("error") else ""))
    lines.append(f"- unscored cce rows   : {len(bad_cce)}")
    for r in bad_cce[:500]:
        lines.append(f"  - {r.get('pair_id')}/{r.get('side')}: {r.get('status')}")
    lines.append(f"- missing gold pairs  : {len(m97['missing_gold_pair_ids'])}")
    lines.append("")

    lines.append("## Baselines comparison (experimental design; values pending)")
    lines.append("")
    lines.append("| baseline | scorers used | structured fields | localization/hard-fail tests | expected added value of (C) vs (A)/(B) |")
    lines.append("|---|---|---|---|---|")
    rows = [
        ("A", "CCE scalar/component only", "none", "none",
         "reference floor: does CCE alone separate defects from EQUIVALENT changes? Weakest for localization and hard-fail recall."),
        ("B", "CCE + free-text teacher reasoning", "free-text reasoning string", "manual read of reasoning",
         "adds qualitative signal; not machine-checkable; not reproducible field-by-field."),
        ("C", "CCE + structured DiagnosticAudit (this overlay)", "evidence_status/relation/affected_component/violation_type/location/reason_code/next_action",
         "9.3 localization, 9.4 hard-fail detection, 9.6/9.2 reproducibility", "the structured audit's value is argued ONLY via localization accuracy, hard-fail detection, and reproducibility -- never via an unverifiable total score."),
    ]
    for a, b, c, d, e in rows:
        lines.append(f"| {a} | {b} | {c} | {d} | {e} |")
    lines.append("")
    return "\n".join(lines)


def render_blind_results_md(metrics: Dict[str, Any],
                            blind_run: Optional[Dict[str, Any]] = None) -> str:
    lines: List[str] = []
    lines.append("# BLIND_RESULTS -- blind-split evaluator results")
    lines.append("")
    if blind_run is None:
        lines.append("**No blind results yet.** The blind split has 8 seeds / 24 pairs. "
                     "Running it requires (a) a frozen prompt revision "
                     "(`split_manifest.frozen_prompt_sha256` is currently null), (b) judge runs "
                     "(online or fixtures), and (c) expert-reviewed gold + adjudication. "
                     "Until then every blind number is pending.")
        lines.append("")
        lines.append("Once the blind run exists, this report will show metrics 9.1-9.7 computed "
                     "on the blind pairs only, with the prompt revision hash and the run metadata. "
                     "No prompt tuning happens after blind results.")
        lines.append("")
        lines.append("## Blind split (frozen)")
        lines.append("")
        lines.append("| seed_id | qid | source_model | sample_tier | cce_total |")
        lines.append("|---|---|---|---|---|")
        for seed in _blind_seeds():
            lines.append(f"| {seed.seed_id} | {seed.question_id} | {seed.source_model} | "
                         f"{seed.sample_tier} | {seed.cce_scores.get('total', '')} |")
        lines.append("")
        lines.append("pending metrics: " + ", ".join(metrics.get("pending_metrics", [])))
        return "\n".join(lines)
    # real blind run rendering (used after a blind run is performed)
    lines.append(f"- prompt revision  : {blind_run.get('prompt_sha256')}")
    lines.append(f"- judge model      : {blind_run.get('judge_model')}")
    lines.append(f"- rows             : audit {blind_run.get('n_audit_rows')} / cce {blind_run.get('n_cce_rows')}")
    lines.append(f"- coverage         : {blind_run.get('coverage')}")
    lines.append("(metrics per blind pair to be pasted here by the report tool.)")
    return "\n".join(lines)


def _blind_seeds() -> List[Any]:
    from .schemas import load_seed_candidates

    seeds = load_seed_candidates(os.path.join(MANIFESTS_DIR, "seed_candidates.jsonl"))
    split = json.load(open(DEFAULT_SPLIT_PATH, encoding="utf-8"))
    blind = set(split["blind_seed_ids"])
    return sorted((s for s in seeds if s.seed_id in blind), key=lambda s: s.seed_id)


def render_go_no_go(verdict_value: str, metrics: Dict[str, Any],
                    pending: bool = True) -> str:
    lines: List[str] = []
    lines.append("# GO/NO-GO -- evaluator validation verdict")
    lines.append("")
    lines.append("## Verdict rule (documented)")
    lines.append("")
    lines.append("1. **SUPPORTED** -- only when the *blind* results show all of: "
                 "(a) correct directional behaviour (9.1 accuracy >= 0.8), (b) acceptable "
                 "invariance (9.2: >= 80% of EQUIVALENT pairs within the empirical tolerance), "
                 "(c) low fatal false-PASS (9.4 rate <= 0.1), (d) useful localization "
                 "(9.3 affected-component accuracy >= 0.7).")
    lines.append("2. **FAILED_VALIDATION** -- evidence shows the evaluator cannot reliably "
                 "distinguish controlled defects from semantics-preserving changes (systematically "
                 "wrong direction AND broken invariance AND high fatal false-PASS).")
    lines.append("3. **LIMITED** -- everything else, including when blind evidence does not exist.")
    lines.append("")
    lines.append("## Current state")
    lines.append("")
    if pending:
        lines.append("- **No expert-reviewed gold exists** (`reviewed_gold.jsonl` is empty: 0 rows).")
        lines.append("- **No judge runs exist** (offline pending state: every DiagnosticAudit call is "
                     "`judge_pending`; Completeness/Correctness for mutated protocols are "
                     "`judge_missing` without fixtures or an online teacher).")
        lines.append("- Blind split (8 seeds / 24 pairs) has **not** been run "
                     "(`frozen_prompt_sha256` is null).")
        lines.append("- Pending metrics: " + ", ".join(metrics.get("pending_metrics", [])))
        lines.append("- Human review (two independent experts -> adjudication -> APPROVED_GOLD) and "
                     "judge runs are required before the verdict is recomputed.")
        lines.append("- **No prompt tuning** is performed after blind results are produced.")
    lines.append("")
    # The contract requires the file to END with exactly one line containing
    # one of SUPPORTED / LIMITED / FAILED_VALIDATION; emit the bare token as
    # the terminal line so the verdict is trivially machine-readable.
    lines.append(verdict_value)
    return "\n".join(lines)


def write_paper_csvs(metrics: Dict[str, Any], cce_rows: List[Dict[str, Any]],
                     proposals: List[Dict[str, Any]],
                     table_path: str,
                     shifts_path: str) -> None:
    """Emit the paper CSVs (no new total score).  In the current pending state
    mutated-side scores are absent -> per-pair rows carry nulls.
    """
    import csv

    os.makedirs(os.path.dirname(table_path), exist_ok=True)
    # ---- table: per-family validity numbers (from metrics) ----
    m91 = metrics["9.1_directional_accuracy"]
    m94 = metrics["9.4_fatal_false_pass"]
    m93 = metrics["9.3_component_localization"]
    cols = ["metric", "value", "n", "pending"]
    table_rows = [
        ["9.1_directional_accuracy", fmt_opt(m91["accuracy_assessable"]), m91["n_correct"] + m91["n_incorrect"], m91["pending"]],
        ["9.1_floor_only(not credited)", m91["n_floor_only"], m91["n_incorrect"], False],
        ["9.2_equivalent_within_tolerance", m92_pct(metrics), metrics_sum(metrics, "9.2", "n_pairs_scored_both_sides"), metrics_pending(metrics, "9.2")],
        ["9.3_affected_component_accuracy", fmt_opt(m93["affected_component_accuracy"]), m93["n_gold_pairs"], m93["pending"]],
        ["9.4_fatal_false_pass_rate", fmt_opt(m94["fatal_false_pass_rate"]), m94["n_detected"] + m94["n_false_pass"], m94["pending"]],
    ]
    with open(table_path, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for row in table_rows:
            w.writerow(row)
    # ---- figure: paired per-pair score shifts (mutated - original) ----
    by_pair = {str(p["pair_id"]): p for p in proposals}
    header = ["pair_id", "seed_id", "family", "expected_relation", "expected_affected_components",
              "shift_s_method", "shift_s_label", "shift_s_trans", "shift_s_time",
              "shift_completeness_total", "shift_correctness_total", "status"]
    fields = ["s_method", "s_label", "s_trans", "s_time"]
    with open(shifts_path, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        orig_by = {str(r["pair_id"]): r for r in cce_rows if r.get("side") == "original"}
        mut_by = {str(r["pair_id"]): r for r in cce_rows if r.get("side") == "mutated"}
        for pid in sorted(by_pair):
            p = by_pair[pid]
            o = orig_by.get(pid)
            m = mut_by.get(pid)
            status = _pair_status(o, m)
            shift = []
            for f in fields:
                ov = _comp(o, "effectiveness", f)
                mv = _comp(m, "effectiveness", f)
                shift.append(_shift(ov, mv))
            for field in ("completeness.total", "correctness.total"):
                ov = _comp_total(o, field)
                mv = _comp_total(m, field)
                shift.append(_shift(ov, mv))
            w.writerow([pid, p.get("seed_id"), p.get("mutation_family"),
                        p.get("expected_relation"),
                        ";".join(p.get("expected_affected_components") or []),
                        *shift, status])


def m92_pct(metrics: Dict[str, Any]) -> str:
    m = metrics.get("9.2_metamorphic_invariance", {})
    per = m.get("per_component", {})
    if not per:
        return "pending"
    vals = [(c['n_within_tolerance'], c['n_pairs_with_scores']) for c in per.values() if c['n_pairs_with_scores']]
    if not vals:
        return "pending"
    return f"{sum(a for a, _ in vals) / sum(b for _, b in vals):.3f}"


def metrics_sum(metrics: Dict[str, Any], key: str, sub: str) -> Any:
    return metrics.get(key, {}).get(sub)


def metrics_pending(metrics: Dict[str, Any], key: str) -> bool:
    return bool(metrics.get(key, {}).get("pending"))


def _comp(cce: Optional[Dict[str, Any]], part: str, field: str) -> Optional[float]:
    if not cce or cce.get("status") != "ok" or not cce.get("components"):
        return None
    v = (cce["components"].get(part) or {}).get(field)
    return float(v) if v is not None else None


def _comp_total(cce: Optional[Dict[str, Any]], field: str) -> Optional[float]:
    part, _, key = field.partition(".")
    if not cce or cce.get("status") != "ok" or not cce.get("components"):
        return None
    v = (cce["components"].get(part) or {}).get(key)
    return float(v) if v is not None else None


def _shift(ov: Optional[float], mv: Optional[float]) -> str:
    if ov is None or mv is None:
        return ""
    return f"{float(mv) - float(ov):.4f}"


def _pair_status(o: Optional[Dict[str, Any]], m: Optional[Dict[str, Any]]) -> str:
    s = []
    for r in (o, m):
        if r is None:
            s.append("missing")
        elif r.get("status") != "ok":
            s.append(r.get("status"))
        else:
            s.append("ok")
    return "/".join(s)


def write_methods_and_limitations(path_methods: str, path_limits: str) -> None:
    os.makedirs(os.path.dirname(path_methods), exist_ok=True)
    methods = [
        "# PAPER_METHODS_TEXT -- counterfactual validity of the ClearEval evaluator",
        "",
        "ClearEval does not require a unique reference protocol text: questions are scored "
        "against the frozen scoring rubric and knowledge bases without a single 'gold' protocol. "
        "To validate that the evaluator actually tracks protocol quality (rather than wording), we "
        "build a local counterfactual overlay: for each selected (question x model) response we "
        "construct one semantics-preserving variant and two single-defect variants per family "
        "(72 pairs total, 24 seeds), all generated deterministically from span-level edits grounded "
        "in the frozen knowledge bases. Each pair is scored under a role-blind protocol: the "
        "original and the mutated text are scored in fully independent judge calls that see only "
        "the question and one protocol text, never the pair structure or the expected relation.",
        "",
        "Validity is measured along 9.1-9.7: directional accuracy (does the expected component "
        "decrease or a hard failure appear), metamorphic invariance (semantics-preserving changes "
        "leave scores within an empirically-derived tolerance), component localization, fatal "
        "false-PASS, judge-expert chance-corrected agreement, test-retest stability, and explicit "
        "coverage of every missing/failed case. The structured DiagnosticAudit's added value is "
        "argued only through localization, hard-fail detection, and reproducibility -- never "
        "through an unverifiable total score.",
        "",
        "Scientific claim (as far as this artefact goes):",
        "",
        f"> {PROMISED_CLAIM}",
        "",
    ]
    with open(path_methods, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(methods))
    limits = [
        "# PAPER_LIMITATIONS_TEXT -- counterfactual-validity limitations",
        "",
        "- **No laboratory validation.** All scorer outputs under validation are automarked; none "
          "of the 24 selected seeds or their counterfactual variants have been wet-lab verified.",
        "- **Expert review pending.** `reviewed_gold.jsonl` is empty (0 rows); the gold-referenced "
          "metrics (9.3/9.4/9.5) are pending until two independent experts label the 72-pair review "
          "package and adjudication is recorded (PENDING_REVIEW -> APPROVED_GOLD).",
        "- **Judge runs pending / frozen-data constraints.** The validity metrics are pending judge "
          "runs; the split is frozen at selection time (`split_seed 20260817`) and the prompt "
          "revision must be frozen before any blind run. Improvement/tuning of the prompt is not "
          "performed after blind results.",
        "- **Eligibility-pool skew (documented in the Task 1 report).** Only 71 of 3289 frozen "
          "(question, model) pairs were eligible under the mechanical rule that `critical_warnings` "
          "be empty/absent; the corpus is skewed toward gpt-5.2-class models and 3 models have zero "
          "eligible candidates. The 24 seeds cannot represent models with no eligible candidates, "
          "by construction.",
        "- **Deterministic effectiveness re-derivation diverges from production.** Mutated texts "
          "are scored by a rule-based re-derivation whose deterministic extraction of "
          "`method_name` / `marker_dict` / clearing time differs from the teacher's extraction, so "
          "absolute effectiveness values for mutated texts are not production-identical (directional "
          "behaviour is the target). No new ClearEval total score is introduced anywhere.",
        "",
        "Scientific claim scope:",
        "",
        f"> {PROMISED_CLAIM}",
        "",
    ]
    with open(path_limits, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(limits))


# ---------------------------------------------------------------------------
# Orchestration (pending real run)
# ---------------------------------------------------------------------------


def generate_reports(
    out_dir: str = REPORTS_DIR,
    proposals_dev: str = DEFAULT_DEV_PROPOSALS,
    audit_runs_dev: str = DEFAULT_DEV_AUDIT_RUNS,
    cce_scores_dev: str = DEFAULT_DEV_CCE_SCORES,
    gold_path: Optional[str] = None,
    review_package: str = DEFAULT_REVIEW_PACKAGE,
    run_offline_audit: bool = True,
    metadata_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate all reports in the current (pending-data) state.

    - builds (if needed) a deterministic development-scoped proposals manifest
      and a development-scoped offline audit run (no fixtures -> every judge
      call is pending).
    - computes metrics 9.1-9.7 (pending) and renders every report + the paper
      CSV/text files.
    - writes the 72-row review package with empty expert labels.
    """
    os.makedirs(out_dir, exist_ok=True)
    gold_path = gold_path or os.path.join(MANIFESTS_DIR, "reviewed_gold.jsonl")

    # 1. development-scoped proposals (deterministic; blind content excluded)
    from .mutation_builder import build

    dev_summary = build(
        role="development",
        proposals_path=proposals_dev,
        gold_path=DEFAULT_DEV_GOLD_STUB,  # NEVER the committed reviewed_gold.jsonl
        build_report_path=os.path.join(out_dir, "DEV_BUILD.md"),
    )
    proposal_rows = _load_rows(proposals_dev)

    # 2. development-scoped offline audit run (pending judges)
    run_summary: Dict[str, Any] = {}
    if run_offline_audit:
        run_summary = run_audit(
            role="development",
            proposals_path=proposals_dev,
            audit_runs_path=audit_runs_dev,
            cce_scores_path=cce_scores_dev,
            require_frozen_for_blind=False,
        )
    audit_rows = _load_rows(audit_runs_dev)
    cce_rows = _load_rows(cce_scores_dev)
    gold_rows = _load_rows(gold_path)

    # 3. metrics (pending)
    metrics = compute_all(audit_rows, cce_rows, gold_rows, proposal_rows)

    # 4. write review package (all pairs / blind scope)
    write_review_package(review_package)

    # 5. render reports
    jud = render_judge_validity_md(metrics, pending_note=True)
    blind = render_blind_results_md(metrics, blind_run=None)
    go = render_go_no_go(verdict(metrics, blind_results=None), metrics, pending=True)
    _write(out_dir, "JUDGE_VALIDITY.md", jud)
    _write(out_dir, "BLIND_RESULTS.md", blind)
    _write(out_dir, "GO_NO_GO.md", go)
    write_paper_csvs(
        metrics, cce_rows, proposal_rows,
        table_path=os.path.join(out_dir, "PAPER_TABLE_COUNTERFACTUAL_VALIDITY.csv"),
        shifts_path=os.path.join(out_dir, "PAPER_FIGURE_PAIRED_SHIFTS.csv"),
    )
    write_methods_and_limitations(
        os.path.join(out_dir, "PAPER_METHODS_TEXT.md"),
        os.path.join(out_dir, "PAPER_LIMITATIONS_TEXT.md"),
    )

    summary = {
        "reports_dir": out_dir,
        "dev_proposals": proposals_dev,
        "dev_audit_runs": audit_runs_dev,
        "dev_cce_scores": cce_scores_dev,
        "review_package": review_package,
        "metrics": metrics,
        "audit_run_summary": run_summary,
        "dev_summary": {k: v for k, v in dev_summary.items() if k in ("n_proposals", "n_equivalent", "n_degrading", "sha256")},
        "verdict": verdict(metrics, blind_results=None),
    }
    return summary


def _write(out_dir: str, name: str, text: str) -> None:
    with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _load_rows(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report_judge_validity",
        description="ClearEval counterfactual-validity overlay: generate judge-validity reports "
                    "in the current (pending-data) state.")
    parser.add_argument("--out-dir", default=REPORTS_DIR)
    parser.add_argument("--review-package", default=DEFAULT_REVIEW_PACKAGE)
    parser.add_argument("--no-offline-audit", action="store_true",
                        help="skip the development-scoped offline audit (reuse existing rows)")
    args = parser.parse_args(argv)

    summary = generate_reports(
        out_dir=args.out_dir,
        review_package=args.review_package,
        run_offline_audit=not args.no_offline_audit,
    )
    print(f"reports dir     : {summary['reports_dir']}")
    print(f"dev proposals   : {summary['dev_proposals']} "
          f"({summary['dev_summary'].get('n_proposals')})")
    print(f"pending metrics : {summary['metrics']['pending_metrics']}")
    print(f"verdict         : {summary['verdict']}")
    print(f"review package  : {summary['review_package']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
