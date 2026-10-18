"""Dependency-free, development-only SR completeness scoring boundary.

Extracts the row/column maximum matching and Com formula from archived
scripts/cce_validation.py (Encoder.score and build_row). Does not extract,
encode, review references, call a model, or modify production score records.
All stage/source identifiers are caller-supplied; no biological requirements
or scientific validity are inferred by this module.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

VERSION = "cce-sr-completeness-continuous-v2"
INVENTORY_VERSION = "route-required-stage-inventory-v1"
PROVENANCE_STATUSES = {"synthetic_fixture", "archive_linked", "caller_bound", "unresolved"}
FORMULA = "Com = 0.4 * SR + 0.6 * (C_param / 3)"
# Eight binary32 ULPs at 1 accommodate normalized float32 dot products exported
# as JSON/Python floats (also covering binary64 roundoff). Endpoint-only policy:
# Continuous v2 preserves raw values and propagates this allowance to SR/SP
# and the weighted Com endpoint. Legacy v1 remains separately replayable.
COSINE_ENDPOINT_ROUNDOFF = 8 * 2.0**-23


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _number(value, name, minimum, maximum):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not minimum <= value <= maximum or not math.isfinite(value)):
        raise ValueError(f"{name} must be finite numeric in [{minimum}, {maximum}]")
    return float(value)


def _json_copy(value, name):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain finite JSON data") from exc
    return copy.deepcopy(value)


def _cosine(value):
    value = _number(value, "similarity", -1 - COSINE_ENDPOINT_ROUNDOFF,
                    1 + COSINE_ENDPOINT_ROUNDOFF)
    return value  # Preserve raw float32 endpoint roundoff; never clip or map.


def _ids(value, name, *, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{name} must be a {'possibly empty' if allow_empty else 'nonempty'} list")
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"{name} contains duplicate IDs")
    return set(value)


def _nullable(value, name, maximum, reason, minimum=0):
    if value is None:
        _text(reason, name + " missing reason")
        return None
    if reason is not None:
        raise ValueError(f"Known {name} cannot have a missing reason")
    return _number(value, name, minimum, maximum)


def _provenance(value, name):
    if not isinstance(value, dict) or value.get("status") not in PROVENANCE_STATUSES:
        raise ValueError(f"{name}.status must describe the input provenance")
    for key in ("run_record_id", "answer_id", "source_record_id"):
        if key not in value:
            raise ValueError(f"{name}.{key} must be explicit (string or null)")
        if value[key] is not None:
            _text(value[key], name + "." + key)
    if value["status"] == "caller_bound" and any(
            value[key] is None for key in ("run_record_id", "answer_id", "source_record_id")):
        raise ValueError(f"{name}: caller_bound requires run, answer and source record IDs")
    return _json_copy(value, name)


def freeze_inventory(inventory):
    """Validate and copy one complete route-scoped inventory, never synthesize it.

    Reference steps are the SR denominator. Required stages and transitions
    retain source and reference-step bindings, but introduce no new weights.
    'frozen_development' is a versioned input contract, not expert certification.
    The caller owns reference applicability and immutable run storage.
    """
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be an object")
    if inventory.get("schema_version") != INVENTORY_VERSION:
        raise ValueError("Unsupported inventory schema_version")
    if inventory.get("status") != "frozen_development":
        raise ValueError("Inventory must be explicitly frozen_development")
    for key in ("inventory_id", "route_id", "reference_id", "reference_status"):
        _text(inventory.get(key), key)
    sources = inventory.get("sources")
    if not isinstance(sources, list) or not sources or any(not isinstance(x, dict) for x in sources):
        raise ValueError("sources must be a nonempty list of source records")
    source_ids = _ids([x.get("source_id") for x in sources], "source IDs")
    for source in sources:
        _text(source.get("locator"), "source locator")

    steps = inventory.get("reference_steps")
    if not isinstance(steps, list) or not steps or any(not isinstance(x, dict) for x in steps):
        raise ValueError("Empty or invalid reference is not a complete route")
    step_ids = _ids([x.get("reference_step_id") for x in steps], "reference step IDs")

    def bound_sources(record):
        if not _ids(record.get("source_ids"), "record source_ids") <= source_ids:
            raise ValueError("Record references an undeclared source ID")

    for step in steps:
        bound_sources(step)
    stages = inventory.get("required_stages")
    transitions = inventory.get("required_transitions")
    if not isinstance(stages, list) or not stages or any(not isinstance(x, dict) for x in stages):
        raise ValueError("required_stages must be a nonempty list")
    if not isinstance(transitions, list) or any(not isinstance(x, dict) for x in transitions):
        raise ValueError("required_transitions must be an explicit list (possibly empty)")
    stage_ids = _ids([x.get("stage_id") for x in stages], "stage IDs")
    _ids([x.get("transition_id") for x in transitions], "transition IDs", allow_empty=True)
    accounted_for = set()
    for record in stages + transitions:
        bound_sources(record)
        linked = _ids(record.get("reference_step_ids"), "record reference_step_ids")
        if not linked <= step_ids:
            raise ValueError("Record references a step outside the selected whole reference")
        accounted_for |= linked
    if accounted_for != step_ids:
        raise ValueError("Every reference step must be bound to a required stage or transition")
    for transition in transitions:
        if (transition.get("from_stage_id") not in stage_ids
                or transition.get("to_stage_id") not in stage_ids):
            raise ValueError("Transition endpoints must be stages in the selected inventory")
        if transition["from_stage_id"] == transition["to_stage_id"]:
            raise ValueError("Transition endpoints must be distinct")
    return _json_copy(inventory, "inventory")


def metrics_from_matrix(inventory, similarities, generated_step_ids, *,
                        provenance):
    """Score supplied cosine similarities, reference rows x generated columns.

    Matching averages raw independent row/column maxima, not one-to-one
    assignment or order validation. Empty generated output gets SR=SP=0 by
    the archived convention. A missing/failed matrix must use explicit null
    metrics via validate_step_metrics, never an empty-output substitute.
    """
    inventory = freeze_inventory(inventory)
    _ids(generated_step_ids, "generated_step_ids", allow_empty=True)
    nref, ngen = len(inventory["reference_steps"]), len(generated_step_ids)
    if not isinstance(similarities, list) or len(similarities) != nref:
        raise ValueError("Matrix must include every selected reference row")
    matrix = []
    for row in similarities:
        if not isinstance(row, list) or len(row) != ngen:
            raise ValueError("Matrix columns must match generated_step_ids exactly")
        matrix.append([_cosine(x) for x in row])
    rmax = [max(row) for row in matrix] if ngen else []
    gmax = [max(row[j] for row in matrix) for j in range(ngen)]
    matches = []
    for i, reference in enumerate(inventory["reference_steps"]):
        j = matrix[i].index(rmax[i]) if ngen else None
        matches.append({"reference_index": i,
                        "reference_step_id": reference["reference_step_id"],
                        "generated_index": j,
                        "generated_step_id": generated_step_ids[j] if j is not None else None,
                        "similarity": rmax[i] if ngen else None})
    result = {"route_id": inventory["route_id"], "reference_id": inventory["reference_id"],
              "sr": math.fsum(rmax) / nref if ngen else 0.0,
              "sp": math.fsum(gmax) / ngen if ngen else 0.0,
              "reference_n": nref, "generated_n": ngen,
              "sr_missing_reason": None, "sp_missing_reason": None,
              "matches": matches,
              "metric_contract_version": VERSION,
              "generated_step_ids": list(generated_step_ids),
              "generated_max_similarity": gmax,
              "matching_contract": "independent_row_column_maxima_raw_cosine_mean",
              "cosine_endpoint_roundoff_allowance": COSINE_ENDPOINT_ROUNDOFF,
              "cosine_endpoint_policy": "preserve_raw_within_roundoff_allowance",
              "input_mode": "supplied_cosine_matrix", "provenance": provenance,
              "empty_generated_convention": "SR=0, SP=0"}
    return validate_step_metrics(result, inventory)


def validate_step_metrics(metrics, inventory=None):
    """Validate supplied SR/SP and preserve all selected-reference metadata.

    This checks numerical/schema consistency, not whether an encoder, parser,
    reference selection, or scientific stage inventory is valid. Known SR/SP
    require a complete frozen inventory. Unknown values require reasons.
    Archived step_missing_reason is retained and accepted for both nulls.
    """
    if not isinstance(metrics, dict) or "sr" not in metrics or "sp" not in metrics:
        raise ValueError("Both sr and sp must be explicit (numeric or null)")
    result = _json_copy(metrics, "step metrics")
    if "threshold" in metrics:
        raise ValueError("Continuous SR/SP cannot contain a threshold; use explicit legacy replay")
    capacity_version = "identity-role-capacity-v1-20261015"
    presence_version = "identity-role-occurrence-presence-v2-20261015"
    quantity_version = "identity-role-occurrence-quantity-presence-v3-20261016"
    metric_version = metrics.get("metric_contract_version", VERSION)
    if metric_version == quantity_version:
        from oeq_quantity_presence import validate_quantity_presence_record
        validate_quantity_presence_record(metrics)
    if metric_version == presence_version:
        from oeq_presence_matching import validate_presence_record
        validate_presence_record(metrics)
    if metric_version == capacity_version:
        from oeq_capacity_matching import validate_capacity_record
        validate_capacity_record(metrics)
    if any(metrics[k] is not None for k in ("sr", "sp")) and metrics.get("metric_contract_version") not in (VERSION, capacity_version, presence_version, quantity_version):
        raise ValueError("Known continuous SR/SP require explicit metric_contract_version")
    if metric_version not in (VERSION, capacity_version, presence_version, quantity_version):
        raise ValueError("Incompatible SR/SP metric contract")
    result["metric_contract_version"] = metric_version
    for key in ("sr", "sp"):
        reason = metrics.get(key + "_missing_reason", metrics.get("step_missing_reason"))
        result[key] = _nullable(metrics[key], key, 1 + COSINE_ENDPOINT_ROUNDOFF, reason,
                                minimum=-1 - COSINE_ENDPOINT_ROUNDOFF)
        result[key + "_missing_reason"] = reason
    result["provenance"] = _provenance(metrics.get("provenance"), "step provenance")
    if inventory is None:
        inventory = metrics.get("inventory")
    if inventory is None:
        if any(result[k] is not None for k in ("sr", "sp")):
            raise ValueError("Known SR/SP require a complete frozen route inventory")
        result["inventory"] = None
    else:
        inventory = freeze_inventory(inventory)
        if metrics.get("inventory") is not None and metrics["inventory"] != inventory:
            raise ValueError("Supplied inventory differs from retained metric inventory")
        for key in ("route_id", "reference_id"):
            if metrics.get(key) != inventory[key]:
                raise ValueError(f"{key} does not match selected inventory")
        if metrics.get("reference_n", len(inventory["reference_steps"])) != len(inventory["reference_steps"]):
            raise ValueError("reference_n must include the whole selected reference")
        result["inventory"] = inventory
        result["reference_n"] = len(inventory["reference_steps"])
    for key in ("route_id", "reference_id"):
        if key not in result:
            raise ValueError(f"{key} must be explicit (string or null)")
        if result[key] is not None:
            _text(result[key], key)
    for key in ("reference_n", "generated_n"):
        if key in metrics and (type(metrics[key]) is not int or metrics[key] < 0):
            raise ValueError(f"{key} must be a nonnegative integer")
    if metrics.get("generated_n") == 0 and any(result[k] not in (None, 0) for k in ("sr", "sp")):
        raise ValueError("Empty generated output cannot have nonzero SR/SP")
    result.setdefault("input_mode", "precomputed_metrics")
    return result


def score_completeness(step_metrics, c_param, *, c_param_provenance,
                       inventory=None, c_param_missing_reason=None,
                       historical_c_step=None,
                       historical_c_step_missing_reason=None,
                       historical_c_step_provenance=None):
    """Compute Com using SR and C_param only; all values remain diagnostic.

    Historical C_step is on its original 0..2 scale and never contributes to
    Com. Its provenance is separate. A null SP does not invalidate known SR;
    a null SR or C_param always makes Com null without renormalization.
    """
    step = validate_step_metrics(step_metrics, inventory)
    param = _nullable(c_param, "c_param", 3, c_param_missing_reason)
    param_provenance = _provenance(c_param_provenance, "c_param provenance")
    if historical_c_step is None and historical_c_step_missing_reason is None:
        historical_c_step_missing_reason = "not_supplied"
    historical = _nullable(historical_c_step, "historical_c_step", 2,
                           historical_c_step_missing_reason)
    if historical_c_step_provenance is not None:
        historical_c_step_provenance = _provenance(historical_c_step_provenance, "historical provenance")
    elif historical is not None:
        raise ValueError("Known historical C_step requires its own provenance")
    for key in ("run_record_id", "answer_id"):
        left, right = step["provenance"][key], param_provenance[key]
        if left is not None and right is not None and left != right:
            raise ValueError(f"SR and C_param have different {key}")
    missing = {}
    if step["sr"] is None:
        missing["sr"] = step["sr_missing_reason"]
    if param is None:
        missing["c_param"] = c_param_missing_reason
    com = None if missing else 0.4 * step["sr"] + 0.6 * (param / 3)
    is_presence = step.get("metric_contract_version") in ("identity-role-occurrence-presence-v2-20261015", "identity-role-occurrence-quantity-presence-v3-20261016")
    return {"schema_version": "source-occurrence-completeness-v2-20261015" if is_presence else VERSION,
            **({"principal_step_metric": "source_occurrence_coverage", "source_occurrence_coverage": step["source_occurrence_coverage"],
                "metric_change": "NEW_SOURCE_OCCURRENCE_COUNT_COVERAGE; NOT_LEGACY_CONTINUOUS_SR"} if is_presence else {}),
            "raw_numeric_ranges": {"sr_sp_mathematical": [-1, 1], "Com_mathematical": [-0.4, 1],
                                   "cosine_roundoff_allowance": COSINE_ENDPOINT_ROUNDOFF,
                                   "Com_roundoff_allowance": 0.4 * COSINE_ENDPOINT_ROUNDOFF},
            "numeric_scope": "development_diagnostic_only", "formal_eligible": False,
            "scientific_certified": False,
            "interpretation": "reference_relative_matching_is_not_scientific_coverage_validation",
            "formula": "Com = 0.4 * source_occurrence_coverage + 0.6 * (C_param / 3)" if is_presence else FORMULA,
            "weights": {("source_occurrence_coverage" if is_presence else "sr"): 0.4, "c_param_normalized": 0.6},
            "sr": step["sr"], "sp": step["sp"], "c_param": param,
            "c_param_normalized": param / 3 if param is not None else None,
            "Com": com, "Com_missing_reasons": missing,
            "c_param_missing_reason": c_param_missing_reason,
            "step_metrics": step, "c_param_provenance": param_provenance,
            "input_binding_verified_by_adapter": False,
            "historical_diagnostics": {"c_step": historical, "maximum": 2,
                                       "missing_reason": historical_c_step_missing_reason,
                                       "provenance": historical_c_step_provenance,
                                       "included_in_Com": False},
            "sp_included_in_Com": False}


def compose_cce(completeness, *, correctness, effectiveness,
                correctness_missing_reason=None, effectiveness_missing_reason=None):
    """Optional aggregation boundary: retain supplied normalized Cor/Eff.

    Never rescales or recomputes Correctness/Effectiveness. IA and HV use the
    archived min/product contract only when all three dimensions are known.
    Callers must enforce provenance/eligibility for Cor/Eff before this call.
    """
    if not isinstance(completeness, dict) or completeness.get("schema_version") not in (VERSION, "source-occurrence-completeness-v2-20261015"):
        raise ValueError("Expected this adapter's completeness result")
    com = completeness.get("Com")
    if com is not None:
        com = _number(com, "Com", -0.4 * (1 + COSINE_ENDPOINT_ROUNDOFF),
                      1 + 0.4 * COSINE_ENDPOINT_ROUNDOFF)
    elif not completeness.get("Com_missing_reasons"):
        raise ValueError("Unknown Com requires reasons")
    cor = _nullable(correctness, "Cor", 1, correctness_missing_reason)
    eff = _nullable(effectiveness, "Eff", 1, effectiveness_missing_reason)
    reasons = {}
    if com is None:
        reasons["Com"] = completeness["Com_missing_reasons"]
    if cor is None:
        reasons["Cor"] = correctness_missing_reason
    if eff is None:
        reasons["Eff"] = effectiveness_missing_reason
    if com is not None and not 0 <= com <= 1 + 0.4 * COSINE_ENDPOINT_ROUNDOFF:
        reasons["Com_aggregation_domain"] = "Raw continuous Com outside unchanged [0,1] IA/HV domain; policy decision required"
    dims = [com, cor, eff]
    return {"completeness": _json_copy(completeness, "completeness result"),
            "Com": com, "Cor": cor, "Eff": eff,
            "IA": min(dims) if not reasons else None,
            "HV": math.prod(dims) if not reasons else None,
            "aggregate_missing_reasons": reasons, "formal_eligible": False,
            "numeric_scope": "development_diagnostic_only"}


def score_request(request):
    """JSON boundary. Exactly one of a full matrix or precomputed metrics."""
    if not isinstance(request, dict):
        raise ValueError("Request must be an object")
    if ("similarities" in request) == ("step_metrics" in request):
        raise ValueError("Supply exactly one of similarities or step_metrics")
    if "threshold" in request:
        raise ValueError("Continuous SR/SP cannot contain a threshold; use explicit legacy replay")
    if "similarities" in request:
        step = metrics_from_matrix(request["inventory"], request["similarities"],
                                   request["generated_step_ids"],
                                   provenance=request["step_provenance"])
    else:
        step = validate_step_metrics(request["step_metrics"], request.get("inventory"))
    options = {key: request[key] for key in (
        "c_param_missing_reason", "historical_c_step", "historical_c_step_missing_reason",
        "historical_c_step_provenance") if key in request}
    return score_completeness(step, request["c_param"],
                              c_param_provenance=request["c_param_provenance"], **options)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local JSON request, matrix or precomputed metrics")
    parser.add_argument("--output", type=Path, help="Write a new result; refuses to overwrite")
    args = parser.parse_args(argv)
    try:
        result = score_request(json.loads(args.input.read_text(encoding="utf-8")))
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(text)
        else:
            print(text, end="")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Invalid scoring request: {exc}\n")


if __name__ == "__main__":
    main()
