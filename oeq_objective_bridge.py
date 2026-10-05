"""Bounded bridge from audited OEQ objective records to deterministic relations.

The bridge only compares caller-supplied numeric records.  It does not extract
values from prose, read model answers, consult a knowledge base, or evaluate
imaging outcomes.  Each record represents one complete single-method candidate;
objectives from different candidates or routes cannot be combined.
"""
from __future__ import annotations

from copy import deepcopy
import math

from experiments.construct_validity.contract import digest
from experiments.construct_validity.objectives import compare_candidates

VERSION = "oeq-objective-bridge-v1"

_VALUE_KINDS = {
    "RECORDED_OBSERVATION",
    "RECORDED_TARGET",
    "CANDIDATE_DECLARED_TARGET",
    "FORMULA_DERIVED_SUITABILITY_PROXY",
}
_RELATION_LABELS = {
    "A_DOMINATES",
    "B_DOMINATES",
    "TRADEOFF",
    "EQUIVALENT",
    "A_ONLY_FEASIBLE",
    "B_ONLY_FEASIBLE",
    "NEITHER_FEASIBLE",
    "NOT_COMPARABLE",
    "UNRESOLVED",
}
_IMAGING_OUTCOME_TYPES = {
    "IMAGING_OUTCOME",
    "IMAGING_RESULT",
    "IMAGING_PERFORMANCE",
    "IMAGING_QUALITY",
    "IMAGING_SIGNAL",
    "IMAGING_RESOLUTION",
    "IMAGING_CONTRAST",
    "IMAGING_SNR",
    "IMAGE_OUTCOME",
    "IMAGE_RESULT",
    "IMAGE_PERFORMANCE",
    "IMAGE_QUALITY",
    "IMAGE_SIGNAL",
    "IMAGE_RESOLUTION",
    "IMAGE_CONTRAST",
    "IMAGE_SNR",
    "SIGNAL_TO_NOISE_RATIO",
    "PSNR",
    "SSIM",
}
_NON_IMAGING_OUTCOME_TYPES = {
    "ELAPSED_TIME",
    "PROCESS_DURATION",
    "PROCESS_TIME",
    "RESOURCE_USE",
    "RESOURCE_CONSUMPTION",
    "MATERIAL_CONSUMPTION",
    "COST",
    "THROUGHPUT",
    "MATERIAL_YIELD",
    "SUITABILITY_PROXY",
    "CONSTRAINT_MARGIN",
    "METHOD_SUITABILITY",
    "MARKER_COMPATIBILITY",
    "FLUOROPHORE_PRESERVATION_REQUIREMENT",
    "REFRACTIVE_INDEX_DOMAIN_MATCH",
    "TASK_CONSTRAINT_SATISFACTION",
    "MORPHOLOGY_PRESERVATION_REQUIREMENT",
}
_NON_IMAGING_OBJECTIVE_SCOPES = {
    "OPERATIONAL_TIME",
    "OPERATIONAL_RESOURCE",
    "PROCESS_RESOURCE",
    "PROCESS_EFFICIENCY",
    "COMPLETE_CANDIDATE_OPERATIONAL",
    "NON_IMAGING_OPERATIONAL",
    "NON_IMAGING_TASK",
}
SCOPE_POLICY = {
    "version": "oeq-objective-non-imaging-scope-v1",
    "imaging_outcomes": "EXCLUDED_BY_EXPLICIT_TYPED_OBJECTIVE_CONTRACT",
    "dimension_names_interpreted": False,
    "allowed_non_imaging_outcome_types": sorted(_NON_IMAGING_OUTCOME_TYPES),
    "allowed_non_imaging_objective_scopes": sorted(_NON_IMAGING_OBJECTIVE_SCOPES),
    "unknown_explicit_types": "REJECT",
}
_UNIT_CONVERSIONS = {
    "h": ("duration", "h", 1.0),
    "hour": ("duration", "h", 1.0),
    "min": ("duration", "h", 1.0 / 60.0),
    "s": ("duration", "h", 1.0 / 3600.0),
    "day": ("duration", "h", 24.0),
    "ratio": ("fraction", "ratio", 1.0),
    "%": ("fraction", "ratio", 0.01),
    "mm": ("length", "mm", 1.0),
    "um": ("length", "mm", 0.001),
    "cm": ("length", "mm", 10.0),
}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _declared_scope(value):
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() not in {
            "unknown", "unresolved", "unspecified", "not reported", "none", "null"
        }
    if isinstance(value, dict):
        return bool(value) and all(_nonempty(key) and _declared_scope(item)
                                   for key, item in value.items())
    return False


def _validate_json(value):
    """Use the project canonicalizer as the strict JSON/finite-value guard."""
    digest(value)


def _selection(value, label):
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        raise ValueError(label + " must be an array of identifiers")
    try:
        selected = list(value)
    except TypeError as error:
        raise ValueError(label + " must be an array of identifiers") from error
    if any(not _nonempty(item) for item in selected):
        raise ValueError(label + " identifiers must be nonempty strings")
    return sorted(set(selected))


def _typed_token(value):
    if not isinstance(value, str):
        return value
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _validate_objective(candidate, name, value):
    if not _nonempty(name) or not isinstance(value, dict):
        raise ValueError("Objective names and records must be nonempty/object values")
    low, high = value.get("min"), value.get("max")
    if (type(low) not in {int, float} or type(high) not in {int, float}
            or not math.isfinite(low) or not math.isfinite(high) or low > high):
        raise ValueError("Objective bounds must be finite ordered numbers: " + name)
    if value.get("direction") not in {"min", "max"}:
        raise ValueError("Objective direction must be min or max: " + name)
    if not _nonempty(value.get("unit")):
        raise ValueError("Objective unit is required: " + name)
    if not _declared_scope(value.get("measurement_scope")):
        raise ValueError("Objective measurement_scope is required: " + name)
    if not _nonempty(value.get("measurement_basis")):
        raise ValueError("Objective measurement_basis is required: " + name)
    kind = value.get("value_kind")
    if kind not in _VALUE_KINDS:
        raise ValueError("Objective value_kind is invalid: " + name)

    # Scope is established only through a controlled typed contract.  Dimension
    # names are deliberately not interpreted because time/resource fields may be
    # necessary attributes of an otherwise in-scope candidate.
    typed = []
    for field in ("outcome_type", "target_type"):
        if field not in value:
            continue
        token = _typed_token(value[field])
        if token in _IMAGING_OUTCOME_TYPES:
            raise ValueError("Imaging-result objectives are outside this bridge: " + name)
        if token not in _NON_IMAGING_OUTCOME_TYPES:
            raise ValueError("Unknown explicit objective outcome type: " + name)
        typed.append(token)
    scoped = None
    if "objective_scope" in value:
        scoped = _typed_token(value["objective_scope"])
        if scoped in _IMAGING_OUTCOME_TYPES:
            raise ValueError("Imaging-result objectives are outside this bridge: " + name)
        if scoped not in _NON_IMAGING_OBJECTIVE_SCOPES:
            raise ValueError("Unknown explicit objective scope: " + name)
    if not typed and scoped is None:
        raise ValueError("Explicit non-imaging objective semantic contract required: " + name)

    provenance = value.get("provenance")
    if not isinstance(provenance, dict) or not _nonempty(provenance.get("record_id")):
        raise ValueError("Objective provenance with record_id is required: " + name)
    scope = candidate["candidate_scope"]
    if provenance.get("candidate_id") != candidate["id"]:
        raise ValueError("Objective provenance candidate_id mismatch: " + name)
    if provenance.get("method_id") != scope["method_id"]:
        raise ValueError("Objective provenance method_id mismatch: " + name)
    if "route_id" in scope and provenance.get("route_id") != scope["route_id"]:
        raise ValueError("Objective provenance route_id mismatch: " + name)
    if kind == "FORMULA_DERIVED_SUITABILITY_PROXY":
        if (not _nonempty(provenance.get("formula_id"))
                or not isinstance(provenance.get("input_record_ids"), list)
                or not provenance["input_record_ids"]
                or any(not _nonempty(item) for item in provenance["input_record_ids"])):
            raise ValueError("Formula proxy needs formula_id and input_record_ids: " + name)
    _validate_json(value)


def _validate_candidate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("Candidate records must be objects")
    if not _nonempty(candidate.get("id")) or not _nonempty(candidate.get("task_id")):
        raise ValueError("Candidate id and task_id are required")
    if not isinstance(candidate.get("scenario"), dict) or not candidate["scenario"]:
        raise ValueError("Candidate scenario must be an explicit nonempty object")
    scope = candidate.get("candidate_scope")
    if (not isinstance(scope, dict)
            or scope.get("kind") != "SINGLE_METHOD_COMPLETE_CANDIDATE"
            or scope.get("complete_candidate") is not True
            or not _nonempty(scope.get("method_id"))):
        raise ValueError("Each record must be one complete single-method candidate")
    if "route_id" in scope and not _nonempty(scope["route_id"]):
        raise ValueError("Declared route_id must be a nonempty string")
    for field in ("objective_scope", "outcome_type", "target_type"):
        if _typed_token(scope.get(field)) in _IMAGING_OUTCOME_TYPES:
            raise ValueError("Imaging-result candidates are outside this bridge")
    if any(isinstance(scope.get(field), (list, tuple, set))
           for field in ("method_id", "route_id")):
        raise ValueError("Candidate method and route identities must be singular")
    constraints = candidate.get("constraints")
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError("Candidate constraints must be an object when supplied")
    if "no_hard_constraints_declared" in candidate and type(candidate["no_hard_constraints_declared"]) is not bool:
        raise ValueError("no_hard_constraints_declared must be boolean")
    if constraints and candidate.get("no_hard_constraints_declared") is True:
        raise ValueError("A candidate cannot declare constraints and no hard constraints")
    objectives = candidate.get("objectives")
    if objectives is not None:
        if not isinstance(objectives, dict):
            raise ValueError("Candidate objectives must be an object when supplied")
        for name, value in objectives.items():
            _validate_objective(candidate, name, value)
    _validate_json(candidate)


def _canonical_objective(value):
    unit = value["unit"]
    family, canonical_unit, factor = _UNIT_CONVERSIONS.get(unit, (unit, unit, 1.0))
    conversion = "EXPLICIT_UNIT_TABLE" if unit in _UNIT_CONVERSIONS else "IDENTITY_SAME_DECLARED_UNIT_ONLY"
    return {
        "raw": deepcopy(value),
        "canonical": {
            "min": value["min"] * factor,
            "max": value["max"] * factor,
            "unit": canonical_unit,
            "unit_family": family,
            "direction": value["direction"],
        },
        "canonicalization": {
            "conversion": conversion,
            "factor": factor,
            "source_fields": ["min", "max", "unit"],
        },
        "value_kind": value["value_kind"],
        "provenance": deepcopy(value["provenance"]),
    }


def build_relation_binding(candidate_records, *, required_constraints=None,
                           objective_names=None):
    """Return the exact binding an external independent label must reference."""
    if not isinstance(candidate_records, (list, tuple)) or len(candidate_records) != 2:
        raise ValueError("Exactly two candidate records are required for a relation binding")
    records = [deepcopy(item) for item in candidate_records]
    for candidate in records:
        _validate_candidate(candidate)
    if records[0]["id"] == records[1]["id"]:
        raise ValueError("Candidate identities must differ")
    required = _selection(required_constraints, "required_constraints")
    names = _selection(objective_names, "objective_names")
    comparison_input = {
        "candidate_records": records,
        "required_constraints": required,
        "objective_names": names,
    }
    return {
        "schema_version": VERSION,
        "task_id": records[0]["task_id"] if records[0]["task_id"] == records[1]["task_id"] else None,
        "candidate_ids": [item["id"] for item in records],
        "candidate_hashes": [digest(item) for item in records],
        "objective_data_sha256": digest([item.get("objectives") for item in records]),
        "comparison_input_sha256": digest(comparison_input),
    }


def _independent_label(ref, binding, relationship):
    result = {
        "supplied": ref is not None,
        "status": "UNAVAILABLE",
        "label": None,
        "counted_as_independent": False,
        "agreement_with_computed_relation": None,
        "reasons": [],
        "reference": deepcopy(ref),
    }
    if ref is None:
        result["reasons"] = ["INDEPENDENT_RELATION_NOT_SUPPLIED"]
        return result
    if not isinstance(ref, dict):
        raise ValueError("independent_relation must be an object when supplied")
    label = ref.get("label")
    if label not in _RELATION_LABELS:
        raise ValueError("Unknown independent relation label")
    result["label"] = label
    if ref.get("independence") != "INDEPENDENT":
        result["reasons"].append("INDEPENDENCE_NOT_EXPLICITLY_DECLARED")
    if ref.get("annotation_pass") != "FIRST_PASS":
        result["reasons"].append("FIRST_PASS_ANNOTATION_NOT_DECLARED")
    if ref.get("assistance") != "NONE":
        result["reasons"].append("ASSISTED_RELATION_NOT_INDEPENDENT")
    if not _nonempty(ref.get("reviewer_id")):
        result["reasons"].append("INDEPENDENT_REVIEWER_ID_MISSING")
    provenance = ref.get("provenance")
    if not isinstance(provenance, dict) or not _nonempty(provenance.get("record_id")):
        result["reasons"].append("INDEPENDENT_RELATION_RECORD_ID_MISSING")
    if binding is None:
        result["reasons"].append("RELATION_BINDING_UNAVAILABLE")
    elif binding["task_id"] is None:
        result["reasons"].append("SAME_TASK_BINDING_NOT_ESTABLISHED")
    else:
        for key in ("task_id", "candidate_ids", "candidate_hashes",
                    "objective_data_sha256", "comparison_input_sha256"):
            if ref.get(key) != binding[key]:
                result["reasons"].append("INDEPENDENT_RELATION_BINDING_MISMATCH:" + key)
    if not result["reasons"]:
        result.update(
            status="COUNTED",
            counted_as_independent=True,
            agreement_with_computed_relation=(label == relationship if relationship is not None else None),
        )
    return result


def _unavailable(candidate_records, independent_relation, reason):
    label = _independent_label(independent_relation, None, None)
    return {
        "schema_version": VERSION,
        "status": "U",
        "relationship": "UNRESOLVED",
        "reasons": [reason],
        "candidate_ids": None,
        "candidate_hashes": None,
        "candidate_records": deepcopy(candidate_records),
        "objective_records": None,
        "relation_binding": None,
        "comparison": None,
        "independent_relation": label,
        "independent_relation_count": 0,
        "contains_formula_derived_suitability_proxy": None,
        "contains_recorded_objective_data": None,
        "imaging_outcomes_evaluated": False,
        "scope_policy": deepcopy(SCOPE_POLICY),
        "scientific_truth": None,
        "policy": "CALLER_SUPPLIED_TYPED_RECORDS_ONLY_NO_PROSE_OR_CCE_INFERENCE",
    }


def build_objective_diagnostics(candidate_records=None, independent_relation=None, *,
                                required_constraints=None, objective_names=None):
    """Evaluate a bounded pair of complete candidates using supplied records.

    Missing records return U.  Structurally false claims (mixed candidate/route
    provenance, multi-method candidates, or typed imaging-result objectives)
    raise ValueError instead of being silently downgraded or inferred.
    """
    if candidate_records is None or candidate_records == []:
        return _unavailable(candidate_records, independent_relation,
                            "AUDITED_OBJECTIVE_RECORDS_NOT_SUPPLIED")
    if not isinstance(candidate_records, (list, tuple)):
        raise ValueError("candidate_records must be a two-item array")
    if len(candidate_records) != 2:
        return _unavailable(candidate_records, independent_relation,
                            "EXACTLY_TWO_COMPLETE_CANDIDATE_RECORDS_REQUIRED")

    records = [deepcopy(item) for item in candidate_records]
    for candidate in records:
        _validate_candidate(candidate)
    if records[0]["id"] == records[1]["id"]:
        raise ValueError("Candidate identities must differ")
    required_constraints = _selection(required_constraints, "required_constraints")
    objective_names = _selection(objective_names, "objective_names")
    binding = build_relation_binding(
        records,
        required_constraints=required_constraints,
        objective_names=objective_names,
    )
    normalized = {
        candidate["id"]: {
            name: _canonical_objective(value)
            for name, value in (candidate.get("objectives") or {}).items()
        }
        for candidate in records
    }

    comparison = compare_candidates(
        records[0], records[1],
        required_constraints=required_constraints,
        objective_names=objective_names,
    )
    reasons = list(comparison["reasons"])
    selected = (sorted(set(objective_names)) if objective_names is not None
                else sorted(set(records[0].get("objectives") or {})
                            | set(records[1].get("objectives") or {})))
    left, right = records[0].get("objectives") or {}, records[1].get("objectives") or {}
    if not reasons and all(name in left and name in right for name in selected):
        for name in selected:
            if left[name]["value_kind"] != right[name]["value_kind"]:
                reasons.append("VALUE_KIND_MISMATCH:" + name)
            elif (left[name]["value_kind"] == "FORMULA_DERIVED_SUITABILITY_PROXY"
                  and left[name]["provenance"]["formula_id"]
                  != right[name]["provenance"]["formula_id"]):
                reasons.append("FORMULA_ID_MISMATCH:" + name)
        if reasons:
            comparison["relationship"] = "NOT_COMPARABLE"
            comparison["reasons"] = reasons
            comparison["compared_objectives"] = {}

    relationship = comparison["relationship"]
    relation_available = relationship not in {"UNRESOLVED", "NOT_COMPARABLE"}
    label = _independent_label(independent_relation, binding, relationship)
    all_values = [value for objectives in normalized.values() for value in objectives.values()]
    return {
        "schema_version": VERSION,
        "status": "S" if relation_available else "U",
        "relationship": relationship,
        "reasons": list(comparison["reasons"]),
        "candidate_ids": binding["candidate_ids"],
        "candidate_hashes": binding["candidate_hashes"],
        "candidate_records": records,
        "objective_records": normalized,
        "relation_binding": binding,
        "comparison": comparison,
        "independent_relation": label,
        "independent_relation_count": 1 if label["counted_as_independent"] else 0,
        "contains_formula_derived_suitability_proxy": any(
            item["value_kind"] == "FORMULA_DERIVED_SUITABILITY_PROXY" for item in all_values),
        "contains_recorded_objective_data": any(
            item["value_kind"] in {"RECORDED_OBSERVATION", "RECORDED_TARGET"}
            for item in all_values),
        "imaging_outcomes_evaluated": False,
        "scope_policy": deepcopy(SCOPE_POLICY),
        "scientific_truth": None,
        "policy": "CALLER_SUPPLIED_TYPED_RECORDS_ONLY_NO_PROSE_OR_CCE_INFERENCE",
    }


# Descriptive alias for callers that prefer an action name.
evaluate_objective_relation = build_objective_diagnostics