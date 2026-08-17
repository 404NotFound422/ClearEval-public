"""ClearEval counterfactual-validity overlay -- validity metrics (Task 3,
deliverable 4: score_counterfactual_relations.py).

Computes the 9.1-9.7 validity metrics from the audit runs, CCE scores, and
the optional expert-reviewed gold, using only the stdlib:

  9.1 directional accuracy       -- for degrading pairs, did the expected CCE
                                    component decrease or a hard failure get
                                    detected?
  9.2 metamorphic invariance     -- EQUIVALENT pairs should show ~zero score
                                    change; empirical invariance tolerance is
                                    derived from the repeat-variation
                                    distribution of original CCE on repeated
                                    identical inputs (documented estimator;
                                    no arbitrary fixed epsilon).
  9.3 component localization     -- affected-component / location / reason-code
                                    accuracy vs reviewed gold.
  9.4 fatal false-PASS           -- fraction of expert-labeled HARD_FAIL
                                    mutations accepted / not detected as hard
                                    failure.
  9.5 judge-expert agreement     -- chance-corrected (Cohen's kappa / weighted
                                    kappa; Krippendorff alpha where
                                    appropriate) + raw agreement.
  9.6 test-retest stability      -- relation/component consistency, C/C
                                    variance, invalid-output rate over N
                                    independent runs.
  9.7 coverage                   -- every missing/failed/unscored case is
                                    enumerated, never silently excluded or
                                    imputed.

Every estimator is a pure function over plain lists of dicts, is stdlib-only,
handles empty/pending input by returning a documented pending/coverage result
(never crashing, never fabricating numbers), and is unit-tested on small
synthetic fixtures.

Reference source for expected relations/components: the expert-reviewed gold
when it exists (see ``review_gold.py``); otherwise the mutation proposals are
used and every metric is explicitly flagged ``provisional``.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # package context
    from .schemas import ExpectedRelation, ComponentId
except ImportError:
    _PKG_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _PKG_DIR)
    from schemas import ComponentId, ExpectedRelation  # type: ignore

PKG_DIR = os.path.dirname(os.path.abspath(__file__))

EFFECTIVENESS_FIELDS = {
    "s_method", "s_label", "s_trans", "s_time",
}
# Mapping from expected component -> score field(s) used by 9.1.
COMPONENT_TO_FIELDS = {
    "S_METHOD": ("s_method",),
    "S_LABEL": ("s_label",),
    "S_TRANS": ("s_trans",),
    "S_TIME": ("s_time",),
    "COMPLETENESS": ("completeness.total",),
    "CORRECTNESS": ("correctness.total",),
    "MULTIPLE": None,  # handled by the caller with the specific expected list
}

# Hard-error statuses that make a case "not scored" (coverage).
UNSCORED_STATUSES = {"judge_pending", "judge_failed", "parse_failed", "judge_missing",
                     "frozen_unusable", "cce_judge_missing", "cce_judge_failed"}


# ---------------------------------------------------------------------------
# Small generic helpers
# ---------------------------------------------------------------------------


def _component_value(cce: Optional[Dict[str, Any]], field: str) -> Optional[float]:
    """Read ``s_method`` / ``completeness.total`` etc. from a CCE record."""
    if not cce or cce.get("status") != "ok" or not cce.get("components"):
        return None
    comps = cce["components"]
    if field in EFFECTIVENESS_FIELDS:
        eff = comps.get("effectiveness") or {}
        v = eff.get(field)
        return float(v) if v is not None else None
    if field == "completeness.total":
        v = (comps.get("completeness") or {}).get("total")
        return float(v) if v is not None else None
    if field == "correctness.total":
        v = (comps.get("correctness") or {}).get("total")
        return float(v) if v is not None else None
    return None


def _finding_of(audit_rows: List[Dict[str, Any]], pair_id: str, side: str) -> Optional[Dict[str, Any]]:
    """Return the finding dict (or None) for one (pair, side) with status ok."""
    for row in audit_rows:
        if str(row.get("pair_id")) == str(pair_id) and row.get("side") == side:
            if row.get("status") == "ok" and isinstance(row.get("finding"), dict):
                return row["finding"]
            return None
    return None


def _score_pair(cce_rows: List[Dict[str, Any]], pair_id: str, side: str) -> Optional[Dict[str, Any]]:
    for row in cce_rows:
        if str(row.get("pair_id")) == str(pair_id) and row.get("side") == side:
            return row
    return None


def _scores_status(cce: Optional[Dict[str, Any]]) -> str:
    return (cce or {}).get("status", "missing")


def _relation_of(finding: Optional[Dict[str, Any]]) -> Optional[str]:
    return (finding or {}).get("relation")


def _affected_component_of(finding: Optional[Dict[str, Any]]) -> Optional[str]:
    return (finding or {}).get("affected_component")


# ---------------------------------------------------------------------------
# 9.1 directional accuracy
# ---------------------------------------------------------------------------


def directional_accuracy(
    audited_pairs: List[Dict[str, Any]],
    cce_rows: List[Dict[str, Any]],
    reference: List[Dict[str, Any]],
    source: str = "provisional",
) -> Dict[str, Any]:
    """9.1 -- for each degrading pair, did the expected CCE component decrease
    or a hard failure get detected?

    ``audited_pairs``: one dict per pair with keys {pair_id, expected_relation,
    expected_affected_components (list), mutated_finding (dict|None)}.
    ``reference``: rows {pair_id, expected_relation, expected_affected_components}.
    ``source``: "gold" or "provisional" (proposals) -- always labelled.

    A pair is *correct* when (criterion 1) the judge returned HARD_FAIL for the
    mutated side (and the reference expects a degradation), or (criterion 2)
    every expected component that maps to a score field strictly decreased
    (mutated < original); floor cases (component already at its deterministic
    floor so no decrease is observable) are counted separately and are NOT
    credited as correct.
    """
    by_ref = {str(r["pair_id"]): r for r in reference}
    detail: List[Dict[str, Any]] = []
    n_correct = n_incorrect = n_pending = n_floor_only = 0
    floor_keys = []
    for pair in audited_pairs:
        pid = str(pair["pair_id"])
        ref = by_ref.get(pid)
        exp_rel = (ref or pair).get("expected_relation")
        if exp_rel == ExpectedRelation.EQUIVALENT.value or exp_rel == "EQUIVALENT":
            continue  # not a degrading pair
        exp_comps = (ref or {}).get("expected_affected_components") or pair.get("expected_affected_components") or []
        orig = _score_pair(cce_rows, pid, "original")
        mutated = _score_pair(cce_rows, pid, "mutated")
        mutated_finding = pair.get("mutated_finding")

        missing = orig is None or mutated is None
        if mutated is not None and mutated.get("status") != "ok":
            missing = True
        if orig is not None and orig.get("status") != "ok":
            missing = True
        if missing:
            n_pending += 1
            detail.append({"pair_id": pid, "outcome": "pending",
                           "reason": f"scores missing/unscored (orig={_scores_status(orig)}, "
                                     f"mutated={_scores_status(mutated)})"})
            continue

        # criterion 1: hard-fail detected by the judge
        hard_fail_detected = _relation_of(mutated_finding) == ExpectedRelation.HARD_FAIL.value
        # criterion 2: expected component decreases
        drops: List[Tuple[str, Optional[float], Optional[float]]] = []
        floor_comp = False
        all_expected_drop = True
        any_observable = False
        for comp in exp_comps:
            fields = COMPONENT_TO_FIELDS.get(comp)
            if not fields:
                continue  # MULTIPLE -> rely on the component-level finding
            for field in fields:
                vo = _component_value(orig, field)
                vm = _component_value(mutated, field)
                if vo is None or vm is None:
                    continue
                drops.append((field, vo, vm))
                if vo > vm + 1e-9:
                    pass  # a drop occurred on this field
                any_observable = True
                if vm >= vo - 1e-9:
                    # no decrease on this field
                    if vo <= 1e-6:
                        floor_comp = True  # original already at floor -> no headroom
                    all_expected_drop = False
        if not any_observable:
            n_pending += 1
            detail.append({"pair_id": pid, "outcome": "pending",
                           "reason": "no expected component maps to an observable score field"})
            continue

        correct = bool(hard_fail_detected) or all_expected_drop
        if correct:
            n_correct += 1
            detail.append({"pair_id": pid, "outcome": "correct",
                           "hard_fail_detected": hard_fail_detected,
                           "drops": drops})
        elif floor_comp and not hard_fail_detected:
            n_floor_only += 1
            floor_keys.append(pid)
            detail.append({"pair_id": pid, "outcome": "undetected_floor",
                           "reason": "expected component already at floor locally; no headroom",
                           "drops": drops})
            n_incorrect += 1
        else:
            n_incorrect += 1
            detail.append({"pair_id": pid, "outcome": "undetected",
                           "hard_fail_detected": hard_fail_detected,
                           "drops": drops})

    assessable = n_correct + n_incorrect
    return {
        "metric": "9.1_directional_accuracy",
        "source": source,
        "n_degrading_pairs": len([p for p in audited_pairs
                                  if (by_ref.get(str(p["pair_id"])) or p).get("expected_relation")
                                  not in ("EQUIVALENT", ExpectedRelation.EQUIVALENT.value)]),
        "n_correct": n_correct,
        "n_incorrect": n_incorrect,
        "n_pending": n_pending,
        "n_floor_only": n_floor_only,
        "floor_pair_ids": sorted(floor_keys),
        "accuracy_assessable": (n_correct / assessable) if assessable else None,
        "detail": detail,
        "pending": assessable == 0,
    }


# ---------------------------------------------------------------------------
# 9.2 metamorphic invariance
# ---------------------------------------------------------------------------


def paired_deltas(pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> Dict[str, List[float]]:
    """Per-component (mutated - original) deltas for EQUIVALENT pairs."""
    out: Dict[str, List[float]] = {k: [] for k in EFFECTIVENESS_FIELDS}
    out["completeness.total"] = []
    out["correctness.total"] = []
    for orig, mutated in pairs:
        for field in list(EFFECTIVENESS_FIELDS) + ["completeness.total", "correctness.total"]:
            vo = _component_value(orig, field)
            vm = _component_value(mutated, field)
            if vo is not None and vm is not None:
                out[field].append(float(vm) - float(vo))
    return out


def repeat_deviation_distribution(repeat_scores: List[Dict[str, Any]],
                                  ) -> Dict[str, List[float]]:
    """Per-component |repeat - first| absolute deviations over N repeats of the
    identical input.  ``repeat_scores`` is a list of CCE records (same input,
    repeated judge calls)."""
    out: Dict[str, List[float]] = {k: [] for k in EFFECTIVENESS_FIELDS}
    out["completeness.total"] = []
    out["correctness.total"] = []
    if not repeat_scores:
        return out
    first = repeat_scores[0]
    for field in list(EFFECTIVENESS_FIELDS) + ["completeness.total", "correctness.total"]:
        v0 = _component_value(first, field)
        if v0 is None:
            continue
        for repeat in repeat_scores[1:]:
            vr = _component_value(repeat, field)
            if vr is not None:
                out[field].append(abs(float(vr) - float(v0)))
    return out


def empirical_invariance_tolerance(deviations: List[float],
                                   percentile: float = 95.0,
                                   minimum: float = 0.0) -> Optional[float]:
    """Documented estimator for the metamorphic-invariance tolerance.

    tolerance = ceil-ish 95th percentile of the observed |delta| distribution on
    repeated identical inputs (never an arbitrary fixed epsilon).  Returns None
    (pending) when there are no observations.  ``percentile`` is documented in
    the reports; ``minimum`` guards against a tolerance of zero on degenerate
    synthetic data where repeats are identical.
    """
    vals = sorted(float(d) for d in deviations if d is not None)
    if not vals:
        return None
    import math

    k = max(0, min(len(vals) - 1, int(math.ceil(percentile / 100.0 * len(vals)) - 1)))
    return float(max(minimum, vals[k]))


def metamorphic_invariance(
    equivalent_pairs: List[Dict[str, Any]],
    cce_rows: List[Dict[str, Any]],
    repeat_scores: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """9.2 -- EQUIVALENT pairs should have ~zero score delta; the invariance
    tolerance is *derived* from the repeat-variation distribution."""
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for pair in equivalent_pairs:
        orig = _score_pair(cce_rows, str(pair["pair_id"]), "original")
        mutated = _score_pair(cce_rows, str(pair["pair_id"]), "mutated")
        if orig and mutated and orig.get("status") == "ok" and mutated.get("status") == "ok":
            pairs.append((orig, mutated))
    deltas = paired_deltas(pairs)
    reps = repeat_scores or []
    devdist = repeat_deviation_distribution(reps)

    per_component: Dict[str, Any] = {}
    for field in list(EFFECTIVENESS_FIELDS) + ["completeness.total", "correctness.total"]:
        ds = deltas.get(field, [])
        tol = empirical_invariance_tolerance(devdist.get(field, []))
        n_ok = sum(1 for d in ds if abs(d) <= (tol if tol is not None else 0.0) + 1e-9)
        per_component[field] = {
            "n_pairs_with_scores": len(ds),
            "mean_abs_delta": (sum(abs(d) for d in ds) / len(ds)) if ds else None,
            "max_abs_delta": max((abs(d) for d in ds), default=None),
            "empirical_tolerance": tol,
            "n_within_tolerance": n_ok,
            "deviation_source": "n/a (no repeats)" if tol is None
                                else f"{len(devdist.get(field, []))} repeat observations",
        }
    return {
        "metric": "9.2_metamorphic_invariance",
        "tolerance_estimator": "95th percentile of |repeat - first| absolute deviations "
                               "(empirical, not a fixed epsilon)",
        "n_equivalent_pairs": len(equivalent_pairs),
        "n_pairs_scored_both_sides": len(pairs),
        "per_component": per_component,
        "pending": len(pairs) == 0 or not (repeat_scores or []),
    }


# ---------------------------------------------------------------------------
# 9.3 component localization
# ---------------------------------------------------------------------------


def _string_sim(a: str, b: str) -> float:
    """Tiny token-overlap similarity in [0,1] (stdlib)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = {t for t in str(a).lower().replace("(", " ").replace(")", " ").split() if len(t) >= 2 and not t.isdigit()}
    tb = {t for t in str(b).lower().replace("(", " ").replace(")", " ").split() if len(t) >= 2 and not t.isdigit()}
    if not ta or not tb:
        return float(a.strip().lower() == b.strip().lower())
    return len(ta & tb) / len(ta | tb)


def component_localization(pairs: List[Dict[str, Any]],
                           gold: List[Dict[str, Any]]) -> Dict[str, Any]:
    """9.3 -- affected-component / location / reason-code accuracy vs gold."""
    by_gold = {str(r.get("pair_id")): r for r in gold}
    rows: List[Dict[str, Any]] = []
    n_comp_exact = n_loc_exact = n_loc_overlap = n_rc_exact = 0
    n_pending = n_have_gold = 0
    for pair in pairs:
        pid = str(pair["pair_id"])
        g = by_gold.get(pid)
        my_finding = pair.get("mutated_finding")
        if g is None:
            n_pending += 1
            rows.append({"pair_id": pid, "outcome": "no_gold"})
            continue
        n_have_gold += 1
        if my_finding is None:
            rows.append({"pair_id": pid, "outcome": "no_finding"})
            continue
        comp_ok = (my_finding.get("affected_component") in (g.get("expected_affected_components") or [])
                   or my_finding.get("affected_component") == g.get("affected_component"))
        loc_exact = str(my_finding.get("location", "")).strip() == str(g.get("expected_location", "")).strip()
        loc_sim = _string_sim(my_finding.get("location", ""), g.get("expected_location", ""))
        rc_exact = str(my_finding.get("reason_code", "")).strip() == str(g.get("reason_code", "")).strip()
        n_comp_exact += 1 if comp_ok else 0
        n_loc_exact += 1 if loc_exact else 0
        n_loc_overlap += 1 if loc_sim >= 0.5 else 0
        n_rc_exact += 1 if rc_exact else 0
        rows.append({"pair_id": pid, "affected_component_ok": comp_ok,
                     "location_sim": round(loc_sim, 3), "reason_code_exact": rc_exact})
    assessable = n_have_gold
    return {
        "metric": "9.3_component_localization",
        "n_gold_pairs": n_have_gold,
        "n_pending": n_pending,
        "affected_component_accuracy": (n_comp_exact / assessable) if assessable else None,
        "location_exact_accuracy": (n_loc_exact / assessable) if assessable else None,
        "location_overlap_accuracy": (n_loc_overlap / assessable) if assessable else None,
        "reason_code_accuracy": (n_rc_exact / assessable) if assessable else None,
        "rows": rows,
        "pending": assessable == 0,
    }


# ---------------------------------------------------------------------------
# 9.4 fatal false-PASS
# ---------------------------------------------------------------------------


def fatal_false_pass(pairs: List[Dict[str, Any]],
                     gold: List[Dict[str, Any]]) -> Dict[str, Any]:
    """9.4 -- fraction of expert-labeled HARD_FAIL mutations accepted.

    "accepted" = the judge returned a non-HARD_FAIL relation for the mutated
    side OR returned next_action == NO_CHANGE with relation EQUIVALENT, i.e. it
    is not detected as a hard failure.
    """
    by_gold = {str(r.get("pair_id")): r for r in gold}
    hard_fail_gold = [p for p in pairs if (by_gold.get(str(p["pair_id"])) or {}).get("expected_relation")
                      == ExpectedRelation.HARD_FAIL.value
                      or (by_gold.get(str(p["pair_id"])) or {}).get("hard_fail_status") is True]
    detected = undis = pending = 0
    rows: List[Dict[str, Any]] = []
    for pair in hard_fail_gold:
        pid = str(pair["pair_id"])
        finding = pair.get("mutated_finding")
        if finding is None:
            pending += 1
            rows.append({"pair_id": pid, "outcome": "pending"})
            continue
        hard = _relation_of(finding) == ExpectedRelation.HARD_FAIL.value
        if not hard:
            undis += 1
            rows.append({"pair_id": pid, "outcome": "false_pass",
                         "judge_relation": _relation_of(finding)})
        else:
            detected += 1
            rows.append({"pair_id": pid, "outcome": "detected"})
    total_scored = detected + undis
    return {
        "metric": "9.4_fatal_false_pass",
        "n_hard_fail_gold": len(hard_fail_gold),
        "n_detected": detected,
        "n_false_pass": undis,
        "n_pending": pending,
        "fatal_false_pass_rate": (undis / total_scored) if total_scored else None,
        "rows": rows,
        "pending": total_scored == 0,
    }


# ---------------------------------------------------------------------------
# 9.5 judge-expert agreement (chance corrected)
# ---------------------------------------------------------------------------


def cohen_kappa(labels_a: Sequence[Optional[str]], labels_b: Sequence[Optional[str]]) -> Optional[float]:
    """Cohen's kappa on two parallel label sequences (both must be aligned and
    only pairs with both labels non-None participate)."""
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    n = len(pairs)
    cats = sorted({a for a, b in pairs} | {b for a, b in pairs})
    agree = sum(1 for a, b in pairs if a == b)
    pa = agree / n
    # marginal probabilities
    from collections import Counter

    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if pe == 1.0:
        return 1.0
    return (pa - pe) / (1.0 - pe) if (1.0 - pe) != 0 else None


def weighted_kappa_linear(labels_a: Sequence[Optional[str]], labels_b: Sequence[Optional[str]],
                          ordering: Sequence[str]) -> Optional[float]:
    """Weighted kappa with linear weights over an ordered category list."""
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    pos = {c: i for i, c in enumerate(ordering)}
    n = len(pairs)
    obs = sum(abs(pos[a] - pos[b]) / (len(ordering) - 1) for a, b in pairs) / n
    from collections import Counter

    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[a] / n) * (cb[b] / n) * abs(pos[a] - pos[b]) / (len(ordering) - 1)
             for a in ordering for b in ordering) if len(ordering) > 1 else 0.0
    if pe == 0.0 and obs == 0.0:
        return 1.0
    return 1.0 - (obs / pe) if pe != 0 else None


def krippendorff_alpha_nominal(labels_a: Sequence[Optional[str]],
                               labels_b: Sequence[Optional[str]]) -> Optional[float]:
    """Krippendorff's alpha (nominal, 2 coders) -- chance-corrected agreement.

    alpha = 1 - D_obs / D_exp where D_obs is observed disagreement and D_exp is
    expected disagreement under independence (for nominal data the standard
    formula reduces to a form of Scott's pi with the same marginal structure).
    """
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    n = len(pairs)
    cats = sorted({a for a, b in pairs} | {b for a, b in pairs})
    counts = {c: sum(1 for a, b in pairs if a == c) + sum(1 for a, b in pairs if b == c) for c in cats}
    do = 0.0
    for a, b in pairs:
        do += 0.0 if a == b else 1.0
    p_a = do / n  # observed proportion of disagreement
    # expected disagreement under independence (nominal)
    de = 0.0
    for a in cats:
        for b in cats:
            if a != b:
                de += (counts[a] / (2 * n)) * (counts[b] / (2 * n))
    if de == 0 and p_a == 0:
        return 1.0
    if de == 0:
        return None
    return 1.0 - (p_a / de) if de != 0 else None


def judge_expert_agreement(judge_labels: Sequence[Optional[str]],
                           expert_a: Sequence[Optional[str]],
                           expert_b: Sequence[Optional[str]]) -> Dict[str, Any]:
    """9.5 -- judge vs expert (and expert A vs expert B where available)."""
    out: Dict[str, Any] = {
        "metric": "9.5_judge_expert_agreement",
        "n_labeled": len([1 for a, b in zip(judge_labels, expert_a) if a is not None and b is not None]),
        "pending": True,
    }
    # judge vs expert A
    jv = cohen_kappa(judge_labels, expert_a)
    wv = weighted_kappa_linear(judge_labels, expert_a, ["EQUIVALENT", "DEGRADED", "HARD_FAIL"])
    ka = krippendorff_alpha_nominal(judge_labels, expert_a)
    raw = None
    n = len([1 for a, b in zip(judge_labels, expert_a) if a is not None and b is not None])
    if n:
        raw = sum(1 for a, b in zip(judge_labels, expert_a)
                  if a is not None and b is not None and a == b) / n
        out["pending"] = False
    out["judge_vs_expert_A"] = {
        "n": n,
        "raw_agreement": raw,
        "cohen_kappa": jv,
        "weighted_kappa_linear": wv,
        "krippendorff_alpha": ka,
    }
    # expert A vs expert B (two independent experts)
    ne = len([1 for a, b in zip(expert_a, expert_b) if a is not None and b is not None])
    out["expert_A_vs_expert_B"] = {
        "n": ne,
        "raw_agreement": (sum(1 for a, b in zip(expert_a, expert_b)
                              if a is not None and b is not None and a == b) / ne) if ne else None,
        "cohen_kappa": cohen_kappa(expert_a, expert_b),
        "krippendorff_alpha": krippendorff_alpha_nominal(expert_a, expert_b),
    }
    return out


# ---------------------------------------------------------------------------
# 9.6 test-retest stability
# ---------------------------------------------------------------------------


def test_retest_stability(repeat_groups: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """9.6 -- N independent runs of the same input: relation-label consistency,
    affected-component consistency, Completeness/Correctness variance and the
    invalid-output rate.

    ``repeat_groups``: one list of audit-run rows (or finding dicts) per input,
    e.g. the per-repeat runs of the same original protocol.
    """
    n_groups = len(repeat_groups)
    total_calls = sum(len(g) for g in repeat_groups)
    invalid = 0
    relation_agree = component_agree = 0
    comp_vars: Dict[str, List[float]] = {}
    valid_groups_with_cc = 0
    for group in repeat_groups:
        findings = [r for r in group if r.get("status") == "ok"]
        invalid += len(group) - len(findings)
        if len(findings) >= 2:
            rels = {f.get("finding", {}).get("relation") for f in findings}
            comps = {f.get("finding", {}).get("affected_component") for f in findings}
            rel_ok = len(rels) == 1 and None not in rels
            comp_ok = len(comps) == 1 and None not in comps
            relation_agree += 1 if rel_ok else 0
            component_agree += 1 if comp_ok else 0
            # Completeness/Correctness variance over repeated CCE records in the group
            for field in ("completeness.total", "correctness.total"):
                vals = []
                for r in group:
                    cce = r.get("cce")
                    v = _component_value(cce, field) if cce else None
                    if v is not None:
                        vals.append(v)
                if len(vals) >= 2:
                    mean = sum(vals) / len(vals)
                    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
                    comp_vars.setdefault(field, []).append(var)
                    valid_groups_with_cc += 1
    return {
        "metric": "9.6_test_retest_stability",
        "n_groups": n_groups,
        "n_calls": total_calls,
        "invalid_output_rate": (invalid / total_calls) if total_calls else None,
        "n_groups_relation_consistent": relation_agree,
        "n_groups_component_consistent": component_agree,
        "per_component_variance": {k: (sum(v) / len(v) if v else None) for k, v in comp_vars.items()},
        "pending": n_groups < 2,
        "coverage_note": "requires >= 2 repeat groups with judge findings",
    }


# ---------------------------------------------------------------------------
# 9.7 coverage
# ---------------------------------------------------------------------------


def coverage_report(audit_rows: List[Dict[str, Any]],
                    cce_rows: List[Dict[str, Any]],
                    gold_rows: List[Dict[str, Any]],
                    proposals: List[Dict[str, Any]],
                    repeat_rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """9.7 -- enumerate every missing / failed / unscored / pending case."""
    bad_audits = [r for r in audit_rows if r.get("status") not in ("ok",)]
    bad_cce = [r for r in cce_rows if r.get("status") != "ok"]
    gold_pair_ids = {str(r.get("pair_id")) for r in gold_rows}
    proposal_pair_ids = [str(p.get("pair_id")) for p in proposals]
    missing_gold = [pid for pid in proposal_pair_ids if pid not in gold_pair_ids]
    bad_repeats = [r for r in (repeat_rows or []) if r.get("status") != "ok"]
    no_input_data = not (audit_rows or cce_rows or gold_rows or proposals or repeat_rows)
    return {
        "metric": "9.7_coverage",
        "n_audit_rows": len(audit_rows),
        "n_cce_rows": len(cce_rows),
        "n_gold_pairs": len(gold_pair_ids),
        "n_proposals": len(proposal_pair_ids),
        "bad_audit_rows": [{"pair_id": r.get("pair_id"), "side": r.get("side"),
                            "status": r.get("status"), "error": r.get("error", "")} for r in bad_audits],
        "bad_cce_rows": [{"pair_id": r.get("pair_id"), "side": r.get("side"),
                          "status": r.get("status"), "error": r.get("error", "")} for r in bad_cce],
        "missing_gold_pair_ids": sorted(missing_gold),
        "bad_repeat_rows": [{"status": r.get("status")} for r in bad_repeats],
        "all_scored": not (bad_audits or bad_cce),
        "pending": no_input_data or bool(bad_audits or bad_cce or missing_gold),
    }


# ---------------------------------------------------------------------------
# Aggregation of all metrics (convenience)
# ---------------------------------------------------------------------------


def compute_all(
    audit_rows: List[Dict[str, Any]],
    cce_rows: List[Dict[str, Any]],
    gold_rows: List[Dict[str, Any]],
    proposals: List[Dict[str, Any]],
    repeat_rows: Optional[List[Dict[str, Any]]] = None,
    gold_expert_a: Optional[List[Dict[str, Any]]] = None,
    gold_expert_b: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute the 9.1-9.7 metrics over a self-consistent set of artifacts.

    All inputs are plain dicts/lists.  Returns a JSON-serializable dict with
    one entry per metric plus a top-level ``pending`` summary and the coverage
    report.  Never raises on empty input (each metric reports pending).
    """
    # build the pair-level view used by 9.1/9.3/9.4
    pair_ids = sorted({r.get("pair_id") for r in proposals})
    by_ref = {str(p.get("pair_id")): p for p in proposals}
    gold_ref = {str(g.get("pair_id")): g for g in gold_rows}
    audited_pairs: List[Dict[str, Any]] = []
    for pid in pair_ids:
        ref = gold_ref.get(pid) or by_ref.get(pid) or {}
        audited_pairs.append({
            "pair_id": pid,
            "expected_relation": ref.get("expected_relation"),
            "expected_affected_components": (ref.get("expected_affected_components")
                                             or ref.get("affected_component") and [ref["affected_component"]]
                                             or []),
            "mutated_finding": _finding_of(audit_rows, pid, "mutated"),
        })

    reference_source = "gold" if gold_rows else "provisional"
    m91 = directional_accuracy(audited_pairs, cce_rows, proposals, source=reference_source)
    equivalent_pairs = [
        {"pair_id": p.get("pair_id")}
        for p in proposals
        if p.get("expected_relation") in ("EQUIVALENT", ExpectedRelation.EQUIVALENT.value)
    ]
    m92 = metamorphic_invariance(equivalent_pairs, cce_rows, repeat_scores=_repeat_cce(repeat_rows))
    m93 = component_localization(audited_pairs, gold_rows)
    m94 = fatal_false_pass(audited_pairs, gold_rows)
    judge_rel_labels = [(_finding_of(audit_rows, pid, "mutated") or {}).get("relation")
                        for pid in pair_ids]
    gold_rel_labels = [_gold_rel(gold_rows, pid) for pid in pair_ids]
    expert_b_rel_labels: List[Optional[str]] = []
    if gold_expert_b:
        expert_b_rel_labels = [(_gold_find(gold_expert_b, pid, "expected_relation")) for pid in pair_ids]
    else:
        expert_b_rel_labels = [None] * len(pair_ids)
    m95 = judge_expert_agreement(judge_rel_labels, gold_rel_labels, expert_b_rel_labels)
    m96 = test_retest_stability(_repeat_groups(repeat_rows))
    m97 = coverage_report(audit_rows, cce_rows, gold_rows, proposals, repeat_rows)

    pending_list = [k for k, m in (("9.1", m91), ("9.2", m92), ("9.3", m93), ("9.4", m94),
                                   ("9.5", m95), ("9.6", m96), ("9.7", m97)) if m.get("pending")]
    return {
        "reference_source": reference_source,
        "9.1_directional_accuracy": m91,
        "9.2_metamorphic_invariance": m92,
        "9.3_component_localization": m93,
        "9.4_fatal_false_pass": m94,
        "9.5_judge_expert_agreement": m95,
        "9.6_test_retest_stability": m96,
        "9.7_coverage": m97,
        "pending_metrics": sorted(pending_list),
        "all_metrics_pending": sorted(pending_list) == ["9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7"],
    }


def _repeat_cce(repeat_rows: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    if not repeat_rows:
        return None
    return [r for r in repeat_rows if r.get("cce") is not None]


def _repeat_groups(repeat_rows: Optional[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
    if not repeat_rows:
        return []
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in repeat_rows:
        key = str(r.get("group_id", "default"))
        groups.setdefault(key, []).append(r)
    return list(groups.values())


def _gold_rel(gold_rows: List[Dict[str, Any]], pid: str) -> Optional[str]:
    return _gold_find(gold_rows, pid, "expected_relation")


def _gold_find(gold_rows: List[Dict[str, Any]], pid: str, key: str) -> Optional[str]:
    for g in gold_rows:
        if str(g.get("pair_id")) == pid:
            return g.get(key)
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_AUDIT_RUNS = os.path.join(PKG_DIR, "manifests", "audit_runs.jsonl")
DEFAULT_CCE_SCORES = os.path.join(PKG_DIR, "manifests", "cce_scores.jsonl")
DEFAULT_GOLD = os.path.join(PKG_DIR, "manifests", "reviewed_gold.jsonl")
DEFAULT_PROPOSALS = os.path.join(PKG_DIR, "manifests", "mutation_proposals.jsonl")
DEFAULT_OUT = os.path.join(PKG_DIR, "reports", "VALIDITY_METRICS.json")


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(
        prog="score_counterfactual_relations",
        description="ClearEval counterfactual-validity overlay: compute 9.1-9.7 validity metrics.")
    parser.add_argument("--audit-runs", default=DEFAULT_AUDIT_RUNS)
    parser.add_argument("--cce-scores", default=DEFAULT_CCE_SCORES)
    parser.add_argument("--gold", default=DEFAULT_GOLD)
    parser.add_argument("--proposals", default=DEFAULT_PROPOSALS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    audit_rows = _load_rows(args.audit_runs)
    cce_rows = _load_rows(args.cce_scores)
    gold_rows = _load_rows(args.gold)
    proposals = _load_rows(args.proposals)
    metrics = compute_all(audit_rows, cce_rows, gold_rows, proposals)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        _json.dump(metrics, fh, ensure_ascii=False, sort_keys=True, indent=2)
    print(f"reference source : {metrics['reference_source']}")
    print(f"pending metrics  : {metrics['pending_metrics']}")
    print(f"written          : {args.out}")
    return 0


def _load_rows(path: str) -> List[Dict[str, Any]]:
    import json

    rows: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


if __name__ == "__main__":
    sys.exit(main())
