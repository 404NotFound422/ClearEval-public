"""Offline numerical stability analysis for repeated OEQ grading.

Consumes an explicit trial ledger and saved evaluations. It never dispatches
requests or reads evaluator/teacher artifacts. All numeric scoring is delegated
to ``results.oeq_metrics.protocol_scores``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
import math
import statistics
from typing import Any, Iterable, Mapping

from results.oeq_metrics import METRIC_BLOCKS, protocol_scores

SCHEMA_VERSION = "oeq-score-stability-v2"
REQUIRED_BINDINGS = (
    "question_sha256", "protocol_sha256", "numeric_formula_sha256",
    "knowledge_base_sha256", "prompt_sha256", "request_settings_sha256",
)
REQUIRED_JUDGE_IDENTITY = ("family", "model", "revision", "digest")
INDEX_COMPONENTS = ("Com", "Cor", "Eff", "I_A")
RAW_COMPONENTS = tuple(metric for block in METRIC_BLOCKS.values() for metric in block)
COMPONENTS = (*RAW_COMPONENTS, *INDEX_COMPONENTS)
_FAILURES = {"error", "failed", "failure", "transport_error"}
_UNKNOWNS = {"u", "unknown", "unavailable", "unassessable", "numeric_unknown"}
_NOT_DISPATCHED = {"not_dispatched", "planned", "pending"}
_CACHE = {"cached", "cache_hit", "replay", "replayed"}
_NON_INDEPENDENT = (
    "duplicate_trial_record", "cached_or_replayed", "missing_invocation_id",
    "missing_request_id", "duplicate_invocation_id", "duplicate_request_id",
)


def _rows(value: Any, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get(field)
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    if not all(isinstance(row, Mapping) for row in value):
        raise TypeError(f"every {field} entry must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _bindings(row: Mapping[str, Any], where: str) -> dict[str, str]:
    value = row.get("bindings")
    if not isinstance(value, Mapping):
        raise ValueError(f"{where}.bindings must be an object")
    return {key: _text(value.get(key), f"{where}.bindings.{key}") for key in REQUIRED_BINDINGS}


def _judge(row: Mapping[str, Any], where: str) -> dict[str, str]:
    value = row.get("judge")
    if not isinstance(value, Mapping):
        raise ValueError(f"{where}.judge must be an object")
    return {key: _text(value.get(key), f"{where}.judge.{key}") for key in REQUIRED_JUDGE_IDENTITY}


def _judge_key(judge: Mapping[str, str]) -> tuple[str, str, str, str]:
    return tuple(judge[key] for key in REQUIRED_JUDGE_IDENTITY)  # type: ignore[return-value]


def _status(row: Mapping[str, Any]) -> str:
    return str(row.get("status", "completed")).strip().lower()


def _cached(row: Mapping[str, Any]) -> bool:
    cache_status = str(row.get("cache_status", "")).strip().lower()
    return bool(
        row.get("cached") is True or row.get("cache_hit") is True
        or row.get("replay_of") not in (None, "")
        or _status(row) in _CACHE or cache_status in _CACHE
    )


def _explicit_unknown(row: Mapping[str, Any]) -> bool:
    if _status(row) in _UNKNOWNS:
        return True
    for container in (row, row.get("evaluation")):
        if not isinstance(container, Mapping):
            continue
        for key in ("numeric_status", "score_status", "status"):
            value = str(container.get(key, "")).strip().lower()
            if value in _UNKNOWNS or "unknown" in value:
                return True
        if container.get("all_u") is True or container.get("unknown") is True:
            return True
    # Some exports preserve an all-U extraction by writing numeric zero into
    # every score while retaining U/unknown in a companion field. Such rows are
    # missing observations, not perfect zero-variance repeats.
    evaluation = row.get("evaluation")
    scores = evaluation.get("scores") if isinstance(evaluation, Mapping) else None
    if isinstance(evaluation, Mapping) and not isinstance(scores, Mapping):
        diagnostic = evaluation.get("legacy_diagnostics")
        scores = diagnostic.get("scores") if isinstance(diagnostic, Mapping) else None
    leaves = []
    if isinstance(scores, Mapping):
        for block_name, block in METRIC_BLOCKS.items():
            score_block = scores.get(block_name, {})
            for metric in block:
                leaf = score_block.get(metric) if isinstance(score_block, Mapping) else None
                if isinstance(leaf, Mapping):
                    leaves.append(leaf)
    if len(leaves) == len(RAW_COMPONENTS) and all(leaf.get("score") == 0 for leaf in leaves):
        def marked_unknown(leaf: Mapping[str, Any]) -> bool:
            return any(
                str(value).strip().lower() in _UNKNOWNS
                for key, value in leaf.items() if key != "score"
            )
        if all(marked_unknown(leaf) for leaf in leaves):
            return True
    return False


def _score_with_shared_formula(row: Mapping[str, Any]) -> Mapping[str, Any]:
    evaluation = row.get("evaluation")
    if (isinstance(evaluation, Mapping) and evaluation.get("technical_status") == "VALID"
            and not isinstance(evaluation.get("scores"), Mapping)):
        diagnostic = evaluation.get("legacy_diagnostics")
        if isinstance(diagnostic, Mapping) and isinstance(diagnostic.get("scores"), Mapping):
            return protocol_scores({"evaluation": {"scores": diagnostic["scores"]}})
    return protocol_scores(row)


def _values(scored: Mapping[str, Any]) -> dict[str, float]:
    return {
        **{key: float(scored["raw"][key]) for key in RAW_COMPONENTS},
        **{key: float(scored[key]) for key in INDEX_COMPONENTS},
    }


def _summary(values: Iterable[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "n": len(finite), "mean": statistics.fmean(finite) if finite else None,
        "sd": statistics.stdev(finite) if len(finite) >= 2 else None,
        "range": max(finite) - min(finite) if len(finite) >= 2 else None,
    }


def _summaries(rows: Iterable[Mapping[str, float]]) -> dict[str, dict[str, Any]]:
    rows = list(rows)
    return {key: _summary(row[key] for row in rows) for key in COMPONENTS}


def _score_agreement(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Pairwise exact score agreement; unknown pairs remain visible."""
    rows = list(rows)
    total = len(rows) * (len(rows) - 1) // 2
    component_results = {}
    for key in RAW_COMPONENTS:
        pairs = [
            (left["components"][key], right["components"][key])
            for left, right in combinations(rows, 2)
            if left.get("components") is not None and right.get("components") is not None
        ]
        component_results[key] = {
            "n_pairs_total": total, "n_pairs_numeric": len(pairs),
            "n_pairs_with_unknown": total - len(pairs),
            "exact_agreement": sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
        }
    vectors = [
        (left["components"], right["components"])
        for left, right in combinations(rows, 2)
        if left.get("components") is not None and right.get("components") is not None
    ]
    return {
        "n_observations": len(rows), "n_pairs_total": total,
        "n_pairs_numeric": len(vectors), "n_pairs_with_unknown": total - len(vectors),
        "complete_raw_vector_exact_agreement": (
            sum(all(a[key] == b[key] for key in RAW_COMPONENTS) for a, b in vectors) / len(vectors)
            if vectors else None
        ),
        "components": component_results,
    }


def _extraction(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    evaluation = row.get("evaluation")
    value = evaluation.get("extraction") if isinstance(evaluation, Mapping) else None
    return deepcopy(value) if isinstance(value, Mapping) else None


def _extraction_agreement(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare saved extraction payloads, never scores or metadata proxies."""
    rows = list(rows)
    total = len(rows) * (len(rows) - 1) // 2
    pairs = [
        (left["extraction"], right["extraction"])
        for left, right in combinations(rows, 2)
        if left.get("extraction") is not None and right.get("extraction") is not None
    ]
    fields = sorted({field for row in rows for field in (row.get("extraction") or {})})
    field_results = {}
    for field in fields:
        field_pairs = [
            (left[field], right[field]) for left, right in pairs
            if field in left and field in right
        ]
        field_results[field] = {
            "n_pairs": len(field_pairs),
            "n_pairs_with_missing": total - len(field_pairs),
            "exact_agreement": (
                sum(a == b for a, b in field_pairs) / len(field_pairs) if field_pairs else None
            ),
        }
    return {
        "n_observations": len(rows), "n_pairs_total": total,
        "n_pairs_with_extraction": len(pairs),
        "n_pairs_with_missing_extraction": total - len(pairs),
        "exact_agreement": sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
        "fields": field_results,
    }


def _technical_failure(row: Mapping[str, Any]) -> bool:
    if _status(row) in _FAILURES or row.get("error") or row.get("api_error"):
        return True
    evaluation = row.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return False
    technical_status = evaluation.get("technical_status")
    return bool(evaluation.get("_error") or technical_status not in (None, "VALID"))

def make_trial_plan(inputs: list[Mapping[str, Any]], judges: list[Mapping[str, Any]], repeats: int) -> list[dict[str, Any]]:
    """Create a deterministic plan-only ledger. This function never dispatches."""
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    if not isinstance(inputs, list) or not inputs or not isinstance(judges, list) or not judges:
        raise ValueError("inputs and judges must be non-empty lists")
    normalized_inputs, seen_inputs = [], set()
    for index, row in enumerate(inputs):
        if not isinstance(row, Mapping):
            raise TypeError("each input must be an object")
        input_id = _text(row.get("input_id"), f"inputs[{index}].input_id")
        if input_id in seen_inputs:
            raise ValueError(f"duplicate input_id: {input_id}")
        seen_inputs.add(input_id)
        normalized_inputs.append((input_id, _bindings(row, f"inputs[{index}]")))
    normalized_judges, seen_judges, judge_core_families = [], set(), {}
    for index, value in enumerate(judges):
        if not isinstance(value, Mapping):
            raise TypeError("each judge must be an object")
        judge = {key: _text(value.get(key), f"judges[{index}].{key}") for key in REQUIRED_JUDGE_IDENTITY}
        key = _judge_key(judge)
        if key in seen_judges:
            raise ValueError("duplicate exact judge identity")
        core = (judge["model"], judge["revision"], judge["digest"])
        if core in judge_core_families and judge_core_families[core] != judge["family"]:
            raise ValueError("contradictory family declaration for the same model/revision/digest")
        judge_core_families[core] = judge["family"]
        seen_judges.add(key)
        normalized_judges.append(judge)
    return [
        {"trial_id": f"{input_id}::j{number}::r{repeat}", "input_id": input_id,
         "bindings": deepcopy(bindings), "judge": deepcopy(judge), "repeat": repeat}
        for input_id, bindings in normalized_inputs
        for number, judge in enumerate(normalized_judges, 1)
        for repeat in range(1, repeats + 1)
    ]


def analyze_score_stability(
    planned_trials: list[Mapping[str, Any]] | Mapping[str, Any],
    completed_records: list[Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    """Analyze records against immutable planned trials, entirely offline."""
    planned, completed = _rows(planned_trials, "planned_trials"), _rows(completed_records, "completed_records")
    if not planned:
        raise ValueError("planned_trials must not be empty")
    plan_by_id, input_bindings, judge_core_families = {}, {}, {}
    for index, raw in enumerate(planned):
        where = f"planned_trials[{index}]"
        trial_id, input_id = _text(raw.get("trial_id"), f"{where}.trial_id"), _text(raw.get("input_id"), f"{where}.input_id")
        if trial_id in plan_by_id:
            raise ValueError(f"duplicate planned trial_id: {trial_id}")
        bindings, judge = _bindings(raw, where), _judge(raw, where)
        core = (judge["model"], judge["revision"], judge["digest"])
        if core in judge_core_families and judge_core_families[core] != judge["family"]:
            raise ValueError("contradictory family declaration for the same model/revision/digest")
        judge_core_families[core] = judge["family"]
        if input_id in input_bindings and input_bindings[input_id] != bindings:
            raise ValueError(f"frozen bindings differ within input_id {input_id}")
        input_bindings[input_id] = bindings
        plan_by_id[trial_id] = {"trial_id": trial_id, "input_id": input_id, "bindings": bindings, "judge": judge}

    seen_invocations, seen_requests, seen_trials = set(), set(), set()
    dispatched, observations, audit = set(), [], []
    for index, raw in enumerate(completed):
        where = f"completed_records[{index}]"
        trial_id = _text(raw.get("trial_id"), f"{where}.trial_id")
        if trial_id not in plan_by_id:
            raise ValueError(f"completed record has unplanned trial_id: {trial_id}")
        plan = plan_by_id[trial_id]
        input_id = _text(raw.get("input_id"), f"{where}.input_id")
        if input_id != plan["input_id"]:
            raise ValueError(f"input_id mismatch for trial {trial_id}")
        if _bindings(raw, where) != plan["bindings"]:
            raise ValueError(f"frozen binding mismatch for trial {trial_id}")
        if _judge(raw, where) != plan["judge"]:
            raise ValueError(f"exact judge identity mismatch for trial {trial_id}")
        status = _status(raw)
        if status in _NOT_DISPATCHED:
            audit.append({"trial_id": trial_id, "record_index": index, "status": "not_dispatched"})
            continue
        dispatched.add(trial_id)
        invocation, request, reason = raw.get("invocation_id"), raw.get("request_id"), None
        if trial_id in seen_trials:
            reason = "duplicate_trial_record"
        elif _cached(raw):
            reason = "cached_or_replayed"
        elif not isinstance(invocation, str) or not invocation.strip():
            reason = "missing_invocation_id"
        elif not isinstance(request, str) or not request.strip():
            reason = "missing_request_id"
        elif invocation.strip() in seen_invocations:
            reason = "duplicate_invocation_id"
        elif request.strip() in seen_requests:
            reason = "duplicate_request_id"
        seen_trials.add(trial_id)
        if reason:
            audit.append({"trial_id": trial_id, "record_index": index, "status": reason})
            continue
        seen_invocations.add(invocation.strip())
        seen_requests.add(request.strip())
        components, numeric_status = None, "numeric"
        if _technical_failure(raw):
            numeric_status = "failed"
        elif _explicit_unknown(raw):
            numeric_status = "unknown"
        else:
            try:
                components = _values(_score_with_shared_formula(raw))
            except ValueError as exc:
                numeric_status = "unknown" if "missing_or_invalid" in str(exc) else "invalid_numeric"
        observations.append({
            "trial_id": trial_id, "input_id": input_id, "judge": plan["judge"],
            "judge_key": _judge_key(plan["judge"]), "numeric_status": numeric_status,
            "components": components, "extraction": None if numeric_status == "failed" else _extraction(raw),
        })
        audit.append({"trial_id": trial_id, "record_index": index, "status": numeric_status})

    group_plan, group_observed = defaultdict(list), defaultdict(list)
    for row in plan_by_id.values():
        group_plan[row["input_id"], _judge_key(row["judge"])].append(row)
    for row in observations:
        group_observed[row["input_id"], row["judge_key"]].append(row)
    repeat_groups = []
    for key in sorted(group_plan):
        input_id, judge_key = key
        plan_rows, observed = group_plan[key], group_observed[key]
        numeric = [row for row in observed if row["components"] is not None]
        statuses = Counter(row["numeric_status"] for row in observed)
        repeat_groups.append({
            "input_id": input_id, "bindings": deepcopy(input_bindings[input_id]),
            "judge": dict(zip(REQUIRED_JUDGE_IDENTITY, judge_key)),
            "planned_trials": len(plan_rows),
            "dispatched_trials": sum(row["trial_id"] in dispatched for row in plan_rows),
            "independent_trials": len(observed), "numeric_trials": len(numeric),
            "failed_trials": statuses["failed"],
            "unknown_trials": statuses["unknown"] + statuses["invalid_numeric"],
            "repetition_data_available": len(numeric) >= 2,
            "stable": None,
            "stability_status": "PENDING_PREDECLARED_THRESHOLD" if len(numeric) >= 2 else "NOT_AVAILABLE",
            "components": _summaries(row["components"] for row in numeric),
            "extraction_agreement": _extraction_agreement(observed),
            "score_agreement": _score_agreement(observed),
        })

    by_input = defaultdict(list)
    for row in observations:
        by_input[row["input_id"]].append(row)
    input_agreement = [
        {"input_id": input_id, "bindings": deepcopy(input_bindings[input_id]),
         "extraction_agreement": _extraction_agreement(by_input[input_id]),
         "score_agreement": _score_agreement(by_input[input_id])}
        for input_id in sorted(input_bindings)
    ]

    actual_judges = sorted({row["judge_key"] for row in observations})
    per_actual_judge = []
    for judge_key in actual_judges:
        planned_for_judge = [row for row in plan_by_id.values() if _judge_key(row["judge"]) == judge_key]
        observed_for_judge = [row for row in observations if row["judge_key"] == judge_key]
        numeric_for_judge = [row for row in observed_for_judge if row["components"] is not None]
        judge_groups = [row for row in repeat_groups if _judge_key(row["judge"]) == judge_key]
        per_actual_judge.append({
            "judge": dict(zip(REQUIRED_JUDGE_IDENTITY, judge_key)),
            "planned_trials": len(planned_for_judge),
            "independent_trials": len(observed_for_judge),
            "numeric_trials": len(numeric_for_judge),
            "inputs_with_numeric_repeats": sum(row["repetition_data_available"] for row in judge_groups),
            "components": _summaries(row["components"] for row in numeric_for_judge),
        })
    comparisons = []
    for left_key, right_key in combinations(actual_judges, 2):
        left_judge, right_judge = dict(zip(REQUIRED_JUDGE_IDENTITY, left_key)), dict(zip(REQUIRED_JUDGE_IDENTITY, right_key))
        if left_judge["family"] == right_judge["family"]:
            continue
        left = {input_id: [r for r in group_observed[input_id, left_key] if r["components"] is not None] for input_id in input_bindings}
        right = {input_id: [r for r in group_observed[input_id, right_key] if r["components"] is not None] for input_id in input_bindings}
        matched = sorted(input_id for input_id in input_bindings if left[input_id] and right[input_id])
        repeated = [i for i in matched if len(left[i]) >= 2 and len(right[i]) >= 2]
        deltas, paired = {key: [] for key in COMPONENTS}, []
        for input_id in matched:
            delta = {}
            for component in COMPONENTS:
                a = statistics.fmean(row["components"][component] for row in left[input_id])
                b = statistics.fmean(row["components"][component] for row in right[input_id])
                delta[component] = b - a
                deltas[component].append(delta[component])
            paired.append({"input_id": input_id, "left_numeric_trials": len(left[input_id]),
                           "right_numeric_trials": len(right[input_id]), "right_minus_left": delta})
        comparisons.append({
            "left_judge": left_judge, "right_judge": right_judge,
            "n_matched_frozen_inputs": len(matched),
            "n_matched_inputs_with_repeats_both_sides": len(repeated),
            "comparison_data_available": bool(matched),
            "repetition_data_available": bool(repeated),
            "stable": None,
            "stability_status": "PENDING_PREDECLARED_THRESHOLD" if matched else "NOT_AVAILABLE",
            "component_deltas_right_minus_left": {key: _summary(value) for key, value in deltas.items()},
            "paired_inputs": paired,
        })

    audit_counts = Counter(row["status"] for row in audit)
    numeric_count, independent_count, planned_count = sum(r["components"] is not None for r in observations), len(observations), len(plan_by_id)
    actual_families = sorted({row["judge"]["family"] for row in observations})
    if not actual_families:
        family_assessment = "not_established_no_actual_judges"
    elif len(actual_families) < 2:
        family_assessment = "not_established_single_actual_family"
    elif not comparisons or not any(row["n_matched_frozen_inputs"] for row in comparisons):
        family_assessment = "not_established_no_actual_matched_frozen_inputs"
    else:
        family_assessment = "comparison_data_available_stability_pending_predeclared_threshold"
    return {
        "schema_version": SCHEMA_VERSION, "scope": "offline_descriptive_score_stability",
        "scientific_accuracy": None, "independent_gold_validation": None,
        "predeclared_stability_thresholds": None,
        "coverage": {
            "planned_trials": planned_count, "dispatched_planned_trials": len(dispatched),
            "not_dispatched_trials": planned_count - len(dispatched),
            "independent_attempts": independent_count, "independent_numeric_results": numeric_count,
            "independent_missing_numeric_results": independent_count - numeric_count,
            "planned_dispatch_coverage": len(dispatched) / planned_count,
            "planned_independent_numeric_coverage": numeric_count / planned_count,
            "excluded_non_independent_records": sum(audit_counts[key] for key in _NON_INDEPENDENT),
            "status_counts": dict(sorted(audit_counts.items())),
        },
        "repeat_groups": repeat_groups, "same_input_extraction_agreement": input_agreement,
        "actual_judge_count": len(actual_judges), "per_actual_judge": per_actual_judge, "actual_families": actual_families,
        "cross_family_assessment": family_assessment, "cross_family_comparisons": comparisons,
        "record_audit": audit,
        "interpretation": (
            "Results describe extraction-to-formula score behavior on frozen observed inputs. "
            "They do not measure scientific accuracy or create an independent gold standard. "
            "Missing and unknown scores are never imputed as zero. No stability threshold was predeclared, so stability remains pending."
        ),
    }


__all__ = ["COMPONENTS", "REQUIRED_BINDINGS", "REQUIRED_JUDGE_IDENTITY", "SCHEMA_VERSION",
           "analyze_score_stability", "make_trial_plan"]