"""Feasibility-first interval Pareto relations for explicit, comparable values.

This compares supplied values, never estimates scientific outcomes. Feasibility
first follows pymoo; scope, units and unknown guards are project additions.
"""
from __future__ import annotations

from copy import deepcopy
import math
from .contract import combine, digest

VERSION = "cleareval-objective-relations-v2"
_UNITS = {
    "h": ("duration", 1.0), "hour": ("duration", 1.0),
    "min": ("duration", 1 / 60), "s": ("duration", 1 / 3600),
    "day": ("duration", 24.0), "ratio": ("fraction", 1.0),
    "%": ("fraction", 0.01), "mm": ("length", 1.0),
    "um": ("length", 0.001), "cm": ("length", 10.0),
}


def _bounds(value):
    if not isinstance(value, dict):
        return None
    low, high = value.get("min"), value.get("max")
    if low is None or high is None:
        return None
    if not all(type(x) in {int, float} and math.isfinite(x) for x in (low, high)) or low > high:
        raise ValueError("Objective bounds must be finite ordered numbers")
    if value.get("direction") not in {"min", "max"}:
        raise ValueError("Every objective needs an explicit direction")
    if not isinstance(value.get("unit"), str) or not value["unit"].strip():
        raise ValueError("Every objective needs an explicit unit")
    family, factor = _UNITS.get(value["unit"], (value["unit"], 1.0))
    low, high = low * factor, high * factor
    if value["direction"] == "max":
        low, high = -high, -low
    return family, low, high


def _scope_declared(value):
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() not in {
            'unknown', 'unresolved', 'unspecified', 'not reported', 'none', 'null'}
    if isinstance(value, dict):
        return bool(value) and all(isinstance(k, str) and k.strip() and _scope_declared(v)
                                   for k,v in value.items())
    return False


def _feasibility(candidate, required):
    constraints = candidate.get("constraints")
    if not isinstance(constraints, dict):
        return "UNDER_SPECIFIED"
    if not required:
        if candidate.get("no_hard_constraints_declared") is not True:
            return "UNDER_SPECIFIED"
        return "SATISFIED"
    return combine([constraints.get(key, "UNDER_SPECIFIED") for key in required])


def compare_candidates(a, b, *, required_constraints=None, objective_names=None):
    """Compare complete, same-context values after hard requirements.

    Strict interval dominance must hold for every possible supplied value.
    Overlap remains unresolved. This does not certify scientific correctness.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("Two candidate objects required")
    for candidate in (a, b):
        if not isinstance(candidate.get("id"), str) or not candidate["id"]:
            raise ValueError("Candidate identity required")
    if a["id"] == b["id"]:
        raise ValueError("Candidate identities must differ")
    constraints_a, constraints_b = a.get("constraints", {}), b.get("constraints", {})
    if not isinstance(constraints_a, dict) or not isinstance(constraints_b, dict):
        raise ValueError("Constraints must be objects")
    extra_required = set(required_constraints) if required_constraints is not None else set()
    if any(not isinstance(k, str) or not k for k in extra_required):
        raise ValueError("Required constraint identifiers must be nonempty strings")
    required = sorted(extra_required | set(constraints_a) | set(constraints_b))
    fa, fb = _feasibility(a, required), _feasibility(b, required)
    result = {"version": VERSION, "candidate_ids": [a["id"], b["id"]],
              "candidate_hashes": [digest(a), digest(b)], "relationship": "UNRESOLVED",
              "feasibility": {a["id"]: fa, b["id"]: fb}, "required_constraints": required,
              "compared_objectives": {}, "reasons": [],
              "scientific_validation": "PENDING_USER_EXPERT",
              "interpretation": "Explicit supplied values, not measured scientific superiority"}
    if (not a.get("task_id") or a.get("task_id") != b.get("task_id")
            or not isinstance(a.get("scenario"), dict) or not a["scenario"]
            or a.get("scenario") != b.get("scenario")):
        result.update(relationship="NOT_COMPARABLE", reasons=["TASK_OR_SCENARIO_MISMATCH_OR_MISSING"])
        return result
    if fa == "SATISFIED" and fb == "VIOLATED":
        result.update(relationship="A_ONLY_FEASIBLE", reasons=["HARD_CONSTRAINT_FAILURE"])
        return result
    if fb == "SATISFIED" and fa == "VIOLATED":
        result.update(relationship="B_ONLY_FEASIBLE", reasons=["HARD_CONSTRAINT_FAILURE"])
        return result
    if fa == fb == "VIOLATED":
        result.update(relationship="NEITHER_FEASIBLE", reasons=["HARD_CONSTRAINT_FAILURE"])
        return result
    if fa != "SATISFIED" or fb != "SATISFIED":
        result["reasons"].append("HARD_CONSTRAINTS_NOT_ESTABLISHED")
        return result
    oa, ob = a.get("objectives"), b.get("objectives")
    if not isinstance(oa, dict) or not isinstance(ob, dict):
        result["reasons"].append("MISSING_OBJECTIVE_VALUES")
        return result
    names = sorted(set(objective_names) if objective_names is not None else set(oa) | set(ob))
    if not names or set(oa) != set(names) or set(ob) != set(names):
        result["reasons"].append("MISSING_OR_DIFFERENT_OBJECTIVES")
        return result
    pairs = []
    for name in names:
        left, right = oa[name], ob[name]
        ba, bb = _bounds(left), _bounds(right)
        if ba is None or bb is None:
            result["reasons"].append("MISSING_VALUE:" + name)
            continue
        if left["direction"] != right["direction"] or ba[0] != bb[0]:
            result["relationship"] = "NOT_COMPARABLE"
            result["reasons"].append("UNIT_OR_DIRECTION_MISMATCH:" + name)
            continue
        if not _scope_declared(left.get("measurement_scope")) or not _scope_declared(right.get("measurement_scope")):
            result["relationship"] = "NOT_COMPARABLE"
            result["reasons"].append("MISSING_MEASUREMENT_SCOPE:" + name)
            continue
        if (left.get("measurement_basis", "DECLARED") != right.get("measurement_basis", "DECLARED")
                or left.get("measurement_scope") != right.get("measurement_scope")):
            result["relationship"] = "NOT_COMPARABLE"
            result["reasons"].append("MEASUREMENT_BASIS_MISMATCH:" + name)
            continue
        pairs.append((ba[1:], bb[1:]))
        result["compared_objectives"][name] = {
            "a": deepcopy(left), "b": deepcopy(right), "canonical_unit_family": ba[0]}
    if result["reasons"]:
        return result
    if all(x[0] == x[1] == y[0] == y[1] for x, y in pairs):
        result["relationship"] = "EQUIVALENT"
    elif all(x[1] <= y[0] for x, y in pairs) and any(x[1] < y[0] for x, y in pairs):
        result["relationship"] = "A_DOMINATES"
    elif all(y[1] <= x[0] for x, y in pairs) and any(y[1] < x[0] for x, y in pairs):
        result["relationship"] = "B_DOMINATES"
    elif any(x[1] < y[0] for x, y in pairs) and any(y[1] < x[0] for x, y in pairs):
        result["relationship"] = "TRADEOFF"
    else:
        result["reasons"].append("OVERLAPPING_UNCERTAINTY_INTERVALS")
    return result
