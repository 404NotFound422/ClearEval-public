"""Versioned SR benchmark records, arithmetic replay, and cohort aggregation.

This is an opt-in numerical estimate contract. It never promotes an estimate to
scientific certification, modifies historical records, calls a model/encoder, or
uses the legacy teacher-score equality validator. Supplied cosine matrices are
retained with their actual canonical step text and fixed reference bindings.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
from collections import Counter

from evaluation_contract import json_hash
from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import (
    compose_cce, freeze_inventory, metrics_from_matrix, score_completeness,
    validate_step_metrics,
)
from results.oeq_metrics import METRIC_BLOCKS, MAX_SCORES, aggregate_items

LEGACY_SR_SCORING_VERSION = "oeq-sr-benchmark-v1"
SR_SCORING_VERSION = "oeq-sr-benchmark-continuous-v2"
SR_AGGREGATION_VERSION = "oeq-sr-mean-of-protocol-minima-continuous-v2"
SR_INTERPRETATION = "AUTOMATED_SR_BENCHMARK_ESTIMATE_NOT_SCIENTIFIC_CERTIFICATION"
SCORE_COMPONENTS = ("c_param", *METRIC_BLOCKS["correctness"], *METRIC_BLOCKS["effectiveness"])
PROPOSAL_COMPONENTS = ("c_param", *METRIC_BLOCKS["correctness"])


def _copy(value, label):
    try:
        json_hash(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(label + " must be finite JSON data") from exc
    return copy.deepcopy(value)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value


def _protocol_hash(protocol):
    if not isinstance(protocol, str):
        raise ValueError("protocol must be text")
    return hashlib.sha256(protocol.encode("utf-8")).hexdigest()


def score_only_output_schema():
    """One closed schema shared by provider output and constructor/replay."""
    def obj(properties):
        return {"type": "object", "additionalProperties": False,
                "required": list(properties), "properties": properties}

    def metric(maximum):
        return {"type": "object", "additionalProperties": False, "required": ["score"],
                "properties": {"score": {"type": ["number", "null"], "minimum": 0, "maximum": maximum},
                               "reasoning": {"type": "string"},
                               "missing_reason": {"type": "string", "minLength": 1, "pattern": r"\S"}},
                "allOf": [{"if": {"properties": {"score": {"type": "null"}}},
                           "then": {"required": ["missing_reason"]},
                           "else": {"not": {"required": ["missing_reason"]}}}]}

    return obj({
        "canonical_extraction_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "task_evidence_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "route_id": {"type": ["string", "null"]}, "reference_id": {"type": ["string", "null"]},
        "scores": obj({"completeness": obj({"c_param": metric(MAX_SCORES["c_param"])}),
                       "correctness": obj({key: metric(maximum) for key, maximum in
                                           METRIC_BLOCKS["correctness"].items()})})})


def _validate_score_schema(value, schema, path="score_proposal"):
    """Dependency-free validator for the exact keywords in our fixed schema.

    The schema itself supplies every field, range, and conditional. Keeping this
    small validator local avoids importing the assessment/runner in scoring.
    """
    types = {"object": isinstance(value, dict), "string": isinstance(value, str),
             "number": type(value) is int or (type(value) is float and math.isfinite(value)), "null": value is None}
    expected = schema.get("type")
    if expected is not None:
        expected = expected if isinstance(expected, list) else [expected]
        if not any(types[kind] for kind in expected):
            raise ValueError(path + " has invalid type")
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(path + " missing required field")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value) <= set(properties):
            raise ValueError(path + " contains extra roots or nested fields")
        for key, child in properties.items():
            if key in value:
                _validate_score_schema(value[key], child, path + "." + key)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(path + " is empty")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ValueError(path + " does not match required pattern")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(path + " is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(path + " exceeds maximum")
    for child in schema.get("allOf", []):
        _validate_score_schema(value, child, path)
    if "if" in schema:
        try:
            _validate_score_schema(value, schema["if"], path)
            matches = True
        except ValueError:
            matches = False
        _validate_score_schema(value, schema.get("then" if matches else "else", {}), path)
    if "not" in schema:
        try:
            _validate_score_schema(value, schema["not"], path)
        except ValueError:
            return
        raise ValueError(path + " has a forbidden field combination")


def validate_score_only_proposal(proposal):
    """Validate precisely the provider's closed score-only output contract."""
    if isinstance(proposal, dict) and "rubric_version" in proposal:
        from oeq_practical_scoring import validate_proposal
        return validate_proposal(proposal)
    _validate_score_schema(proposal, score_only_output_schema())
    return _copy(proposal, "score-only proposal")


def canonical_route_status(extraction, route_id):
    """A selected route exists only when canonical branches explicitly say so."""
    if not isinstance(extraction, dict):
        raise ValueError("canonical_extraction must be an object")
    if route_id is not None:
        _text(route_id, "route_id")
    branches = extraction.get("branches")
    if branches is not None and (not isinstance(branches, list)
            or any(not isinstance(branch, dict) for branch in branches)):
        raise ValueError("Canonical branches must be an explicit list of objects")
    ids = [_text(branch.get("id"), "canonical branch ID") for branch in branches or []]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate canonical branch ID")
    reason = ("CANONICAL_ROUTE_NOT_SELECTED" if route_id is None else
              "CANONICAL_BRANCHES_UNDECLARED" if branches is None else
              "CANONICAL_SELECTED_ROUTE_ABSENT" if route_id not in ids else None)
    return {"status": "UNRESOLVED" if reason else "BOUND", "selected_route": route_id,
            "declared_routes": ids, "guards": [reason] if reason else []}


def canonical_step_view(extraction, route_id):
    """Exactly the selected canonical steps, in canonical order, without filling.

    The representation is the retained literal quote, not an independent model
    paraphrase. Other routes are never pooled into one reference denominator.
    """
    if not isinstance(extraction, dict) or not isinstance(extraction.get("steps"), list):
        raise ValueError("canonical_extraction.steps must be an explicit list")
    if route_id is not None:
        _text(route_id, "route_id")
    route = canonical_route_status(extraction, route_id)
    seen, result = set(), []
    for step in extraction["steps"]:
        if not isinstance(step, dict):
            raise ValueError("canonical steps must be objects")
        sid = _text(step.get("id"), "canonical step ID")
        if sid in seen:
            raise ValueError("Duplicate canonical step ID")
        seen.add(sid)
        _text(step.get("branch"), "canonical step branch")
        _text(step.get("quote"), "canonical step quote")
        if route["status"] == "BOUND" and step["branch"] == route_id:
            result.append({"id": sid, "text": step["quote"]})
    return result


def _bindings(canonical_extraction, task_evidence):
    return {
        "canonical_extraction_sha256": json_hash(canonical_extraction),
        "task_evidence_sha256": json_hash(task_evidence),
        "route_id": task_evidence["route_id"],
        "reference_id": task_evidence["reference_id"],
    }


def _check_bindings(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise ValueError(label + " differs from actual input: " + key)


def _component(record, key):
    if not isinstance(record, dict) or "score" not in record:
        raise ValueError("Missing explicit score proposal: " + key)
    value = record["score"]
    reason = record.get("missing_reason")
    if value is None:
        reason = reason or record.get("reasoning")
        _text(reason, key + " missing reason")
        return None, reason
    maximum = MAX_SCORES[key]
    minimum = -maximum if key == "s_method" else 0
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError("Invalid numerical component: " + key)
    if reason is not None:
        raise ValueError("Known numerical component has missing_reason: " + key)
    return float(value), None


def _provenance(record_id, protocol_sha256, source_id):
    return {"status": "caller_bound", "run_record_id": record_id,
            "answer_id": protocol_sha256, "source_record_id": source_id}


def _step_metrics(request, extraction, evidence, binding, record_id, protocol_sha256, *, legacy=False):
    if legacy:
        from experiments.cce_completeness_revision_20261013.sr_completeness_legacy_v1 import metrics_from_matrix, validate_step_metrics
    else:
        from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import metrics_from_matrix, validate_step_metrics
        if request.get("matching_contract", "independent_row_column_maxima_raw_cosine_mean") != "independent_row_column_maxima_raw_cosine_mean":
            raise ValueError("Incompatible continuous matching contract")
        if "threshold" in request:
            raise ValueError("Continuous SR/SP does not accept threshold; old inputs require legacy replay")
    _check_bindings(request, binding, "step_request")
    inventory = evidence["sr_inventory"]
    if inventory is not None:
        inventory = freeze_inventory(inventory)
    if inventory is not None and (inventory["route_id"] != binding["route_id"]
            or inventory["reference_id"] != binding["reference_id"]):
        raise ValueError("Evidence inventory and selected route/reference differ")
    if "inventory" in request and request["inventory"] != inventory:
        raise ValueError("step_request inventory differs from fixed evidence")
    generated = canonical_step_view(extraction, binding["route_id"])
    if request.get("generated_steps") != generated:
        raise ValueError("step_request generated_steps differ from actual canonical extraction")
    reference_rows = inventory["reference_steps"] if inventory is not None else []
    reference_ids = [row["reference_step_id"] for row in reference_rows]
    reference_texts = [_text(row.get("text"), "reference step text")
                       for row in reference_rows]
    if request.get("reference_step_ids") != reference_ids:
        raise ValueError("step_request must bind every fixed reference row in order")
    if request.get("reference_step_texts") != reference_texts:
        raise ValueError("step_request reference text differs from fixed evidence")
    provenance = _provenance(record_id, protocol_sha256,
                             inventory["inventory_id"] if inventory is not None else "unresolved_reference")
    if ("similarities" in request) == ("step_metrics" in request):
        raise ValueError("Supply exactly one of similarities or unknown step_metrics")
    if "similarities" in request:
        if inventory is None or binding["route_id"] is None:
            raise ValueError("A matrix requires an explicitly selected complete reference inventory")
        encoder = request.get("encoder")
        if not isinstance(encoder, dict):
            raise ValueError("Retained cosine matrix requires encoder identity")
        for key in ("id", "revision"):
            _text(encoder.get(key), "encoder." + key)
        if encoder.get("input_representation") != "canonical_step_quote":
            raise ValueError("Encoder representation must be canonical_step_quote")
        step = metrics_from_matrix(inventory, request["similarities"],
                                   [row["id"] for row in generated],
                                   provenance=provenance,
                                   **({"threshold": request.get("threshold", 0.7)} if legacy else {}))
    else:
        supplied = request["step_metrics"]
        if not isinstance(supplied, dict) or supplied.get("sr") is not None or supplied.get("sp") is not None:
            raise ValueError("Known SR/SP require the retained complete cosine matrix")
        if "sr" not in supplied or "sp" not in supplied:
            raise ValueError("Unknown step_metrics require explicit sr and sp nulls")
        step = validate_step_metrics({
            **supplied, "sr": None, "sp": None, "route_id": binding["route_id"],
            "reference_id": binding["reference_id"], "provenance": provenance,
            **({"reference_n": len(reference_ids)} if inventory is not None else {}),
            **({"generated_n": len(generated)} if binding["route_id"] is not None else {}),
            "generated_step_ids": [row["id"] for row in generated],
            "input_mode": "explicitly_unavailable_matrix",
        }, inventory)
    route = canonical_route_status(extraction, binding["route_id"])
    step["canonical_route_status"] = route
    if route["status"] != "BOUND":
        for key in ("sr", "sp"):
            step[key] = None
            step[key + "_missing_reason"] = "Canonical route unresolved: " + "; ".join(route["guards"])
        step.pop("generated_n", None)
        step.pop("empty_generated_convention", None)
        step["matching_status"] = "NOT_SCORED_UNRESOLVED_CANONICAL_ROUTE"
        step = validate_step_metrics(step, inventory)
    gate = evidence["inventory_evidence"]
    if gate["status"] != "BOUND" and any(step[key] is not None for key in ("sr", "sp")):
        step["unqualified_matching_diagnostics"] = {"sr": step["sr"], "sp": step["sp"],
                                                  "included_in_Com": False}
        for key in ("sr", "sp"):
            step[key] = None
            step[key + "_missing_reason"] = "Fixed inventory evidence unresolved: " + "; ".join(gate["guards"])
        step = validate_step_metrics(step, inventory)
    return step


def validate_step_request(step_request, canonical_extraction, task_evidence):
    """Validate the matrix binding before any score-only judge is called."""
    from oeq_task_evidence import validate_selected_task_evidence
    evidence = validate_selected_task_evidence(task_evidence)
    binding = _bindings(canonical_extraction, evidence)
    _step_metrics(step_request, canonical_extraction, evidence, binding,
                  "input_validation", "input_validation")
    return _copy(step_request, "step request")


def _compute(*, protocol, canonical_extraction, task_evidence, score_proposal,
             step_request, effectiveness_scores, effectiveness_input, record_id,
             legacy_evaluation, legacy=False):
    if legacy:
        from experiments.cce_completeness_revision_20261013.sr_completeness_legacy_v1 import score_completeness, compose_cce
    else:
        from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import score_completeness, compose_cce
    from oeq_task_evidence import validate_selected_task_evidence

    protocol_sha = _protocol_hash(protocol)
    evidence = validate_selected_task_evidence(task_evidence)
    if evidence != task_evidence:
        raise ValueError("Task evidence must be the complete validated selected projection")
    extraction = _copy(canonical_extraction, "canonical extraction")
    binding = _bindings(extraction, evidence)
    canonical_step_view(extraction, binding["route_id"])
    for collection in ("steps", "labels", "ri"):
        rows = extraction.get(collection, [])
        if not isinstance(rows, list):
            raise ValueError("Canonical " + collection + " must be a list")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("quote"), str) or row["quote"] not in protocol:
                raise ValueError("Canonical quotation is absent from original protocol")
    if extraction.get("protocol_sha256", protocol_sha) != protocol_sha:
        raise ValueError("Canonical extraction is bound to another protocol")
    validate_score_only_proposal(score_proposal)
    _check_bindings(score_proposal, binding, "score_proposal")
    if not isinstance(effectiveness_scores, dict):
        raise ValueError("effectiveness_scores must be an explicit numerical block")
    if not isinstance(effectiveness_input, dict):
        raise ValueError("Retain the canonical effectiveness input projection")
    _check_bindings(effectiveness_input, {
        "canonical_extraction_sha256": binding["canonical_extraction_sha256"],
        "selected_route": binding["route_id"],
    }, "effectiveness_input")
    if "projection" not in effectiveness_input:
        raise ValueError("effectiveness_input must retain its actual projection")
    proposal_scores = score_proposal.get("scores")
    if not isinstance(proposal_scores, dict) or set(proposal_scores) != {"completeness", "correctness"}:
        raise ValueError("score_proposal.scores must contain only completeness and correctness")
    if not isinstance(proposal_scores["completeness"], dict) or set(proposal_scores["completeness"]) != {"c_param"}:
        raise ValueError("The new completeness proposal contains only c_param; C_step is historical")
    if not isinstance(proposal_scores["correctness"], dict) or set(proposal_scores["correctness"]) != set(METRIC_BLOCKS["correctness"]):
        raise ValueError("The correctness proposal must contain exactly the original four components")
    raw, missing, components = {}, {}, {}
    route = canonical_route_status(extraction, binding["route_id"])
    for key in SCORE_COMPONENTS:
        if key in METRIC_BLOCKS["effectiveness"]:
            source = effectiveness_scores
        else:
            block = "completeness" if key == "c_param" else "correctness"
            source = proposal_scores.get(block)
            if not isinstance(source, dict):
                raise ValueError("Missing numerical proposal group: " + block)
        value, reason = _component(source.get(key), key)
        guards = []
        revised_co = (score_proposal.get("rubric_version") == "practical-rubric-v1-20261015"
                      and key in METRIC_BLOCKS["correctness"])
        if key in PROPOSAL_COMPONENTS and not revised_co:
            gate = evidence["evidence_gates"][key]
            if gate["status"] != "BOUND":
                value = None
                guards = list(gate.get("guards") or ["EVIDENCE_BINDING_UNRESOLVED"])
                reason = "Fixed evidence unresolved: " + "; ".join(guards)
        if route["status"] != "BOUND":
            value = None
            guards = sorted(set(guards + route["guards"]))
            reason = "Canonical route unresolved: " + "; ".join(guards)
        raw[key] = value
        if value is None:
            missing[key] = reason
        components[key] = {"score": value, "missing_reason": reason,
                           "guards": guards, "proposal_retained": True}
    normalized = {key: (value / MAX_SCORES[key] if value is not None else None)
                  for key, value in raw.items()}
    if normalized["s_method"] is not None:
        normalized["s_method"] = (normalized["s_method"] + 1) / 2
    dimensions, dimension_reasons = {}, {}
    for name, group in (("Cor", "correctness"), ("Eff", "effectiveness")):
        unknown = [key for key in METRIC_BLOCKS[group] if raw[key] is None]
        dimensions[name] = (None if unknown else
                            sum(normalized[key] for key in METRIC_BLOCKS[group]) / 4)
        dimension_reasons[name] = ("Unknown components: " + ", ".join(unknown)) if unknown else None
    step = _step_metrics(step_request, extraction, evidence, binding, record_id, protocol_sha, legacy=legacy)
    historical = None
    historical_reason = "not_supplied"
    historical_provenance = None
    if isinstance(legacy_evaluation, dict):
        old_scores = (legacy_evaluation.get("legacy_diagnostics") or {}).get("scores")
        if not isinstance(old_scores, dict):
            old_scores = legacy_evaluation.get("scores") or {}
        old = (old_scores.get("completeness") or {}).get("c_step")
        if isinstance(old, dict) and "score" in old:
            try:
                historical, historical_reason = _component(old, "c_step")
            except ValueError:
                historical, historical_reason = None, "Invalid or unexplained legacy C_step; original record retained"
            old_answer = legacy_evaluation.get("protocol_sha256")
            if old_answer is None and isinstance(legacy_evaluation.get("integrity"), dict):
                old_answer = legacy_evaluation["integrity"].get("answer_sha256")
            historical_provenance = {
                "status": "archive_linked" if old_answer is not None else "unresolved",
                "run_record_id": legacy_evaluation.get("record_id"),
                "answer_id": old_answer, "source_record_id": "retained_legacy_evaluation",
            }
    completeness = score_completeness(
        step, raw["c_param"], c_param_provenance=_provenance(record_id, protocol_sha, "score_proposal"),
        c_param_missing_reason=missing.get("c_param"), historical_c_step=historical,
        historical_c_step_missing_reason=historical_reason,
        historical_c_step_provenance=historical_provenance)
    composed = compose_cce(completeness, correctness=dimensions["Cor"],
                           effectiveness=dimensions["Eff"],
                           correctness_missing_reason=dimension_reasons["Cor"],
                           effectiveness_missing_reason=dimension_reasons["Eff"])
    for key in ("sr", "sp"):
        if step[key] is None:
            missing[key] = step[key + "_missing_reason"]
    calculated = {"raw": raw, "normalized": normalized, "Com": composed["Com"],
                  "Cor": composed["Cor"], "Eff": composed["Eff"],
                  "I_A": composed["IA"], "HV": composed["HV"],
                  "sr": step["sr"], "sp": step["sp"],
                  **{key: normalized[key] for key in METRIC_BLOCKS["effectiveness"]}}
    return {"input_binding": {**binding, "protocol_sha256": protocol_sha},
            "component_scores": components, "calculated_scores": calculated,
            "completeness_calculation": completeness,
            "aggregate_missing_reasons": composed["aggregate_missing_reasons"],
            "unknown_components": missing}


def build_sr_benchmark_record(*, protocol, canonical_extraction, task_evidence,
                              score_proposal, step_request, effectiveness_scores,
                              effectiveness_input, legacy_evaluation=None,
                              raw_generations=None, record_id=None, _legacy_replay=False):
    """Build a new record, retaining all raw inputs without rewriting legacy data.

    Validation is reproducible input binding and arithmetic, not proof that an
    encoder or judge is scientifically accurate. Effectiveness is supplied by
    the unchanged rule calculator; its actual canonical projection is retained
    so the runner can replay that calculator on cache reads.
    """
    if record_id is None:
        record_id = "sr:" + _protocol_hash(protocol)
    _text(record_id, "record_id")
    if raw_generations is not None:
        if not isinstance(raw_generations, dict):
            raise ValueError("raw_generations must be an object or null")
        if "score_only" in raw_generations:
            from evaluator_integrity import parse_judge_object
            generation = raw_generations["score_only"]
            if not isinstance(generation, dict) or generation.get("technical_status") != "VALID":
                raise ValueError("Original score-only generation is not valid")
            if parse_judge_object(generation.get("content")) != score_proposal:
                raise ValueError("Score proposal differs from retained original generation")
    inputs = _copy(dict(protocol=protocol, canonical_extraction=canonical_extraction,
                        task_evidence=task_evidence, score_proposal=score_proposal,
                        step_request=step_request, effectiveness_scores=effectiveness_scores,
                        effectiveness_input=effectiveness_input,
                        legacy_evaluation=legacy_evaluation), "scoring inputs")
    computed = _compute(**inputs, record_id=record_id, legacy=_legacy_replay)
    version = LEGACY_SR_SCORING_VERSION if _legacy_replay else SR_SCORING_VERSION
    if score_proposal.get("rubric_version") == "practical-rubric-v1-20261015":
        if _legacy_replay:
            raise ValueError("Revised rubric cannot masquerade as legacy replay")
        version = "oeq-sr-practical-v3-20261015"
    complete = computed["calculated_scores"]["I_A"] is not None
    return {
        "scoring_contract_version": version,
        "benchmark_adapter_version": version,
        "record_id": record_id, "technical_status": "VALID",
        "scoring_status": "AUTOMATED_BENCHMARK_ESTIMATE" if complete else "BENCHMARK_UNRESOLVED",
        "score_interpretation": SR_INTERPRETATION,
        "scientific_status": "UNRESOLVED", "cce_eligible": False,
        "official_scores": None, "scientific_certified": False,
        "raw_generations": _copy(raw_generations, "raw generations"),
        **inputs, **computed,
    }


def validate_sr_benchmark_record(record, protocol=None):
    """Replay the new contract; return a detached validated copy or raise.

    No legacy numerical equality is required. Original legacy input, if any,
    remains a separate diagnostic. Science fields are deliberately fail closed.
    """
    if not isinstance(record, dict) or record.get("scoring_contract_version") not in (SR_SCORING_VERSION, LEGACY_SR_SCORING_VERSION, "oeq-sr-practical-v3-20261015"):
        raise ValueError("Expected a versioned SR benchmark record")
    if record.get("_error"):
        raise ValueError("SR record contains an evaluation error")
    if "scores" in record:
        raise ValueError("SR records must not masquerade as legacy score objects")
    if protocol is not None and record.get("protocol") != protocol:
        raise ValueError("SR record is bound to another protocol")
    try:
        rebuilt = build_sr_benchmark_record(_legacy_replay=record["scoring_contract_version"] == LEGACY_SR_SCORING_VERSION, **{key: record[key] for key in (
            "protocol", "canonical_extraction", "task_evidence", "score_proposal",
            "step_request", "effectiveness_scores", "effectiveness_input",
            "legacy_evaluation", "raw_generations", "record_id")})
    except KeyError as exc:
        raise ValueError("Missing retained SR record input: " + str(exc)) from exc
    for key, value in rebuilt.items():
        if key not in record or record[key] != value:
            raise ValueError("SR record failed replay: " + key)
    return _copy(record, "SR benchmark record")


def is_sr_benchmark_record_complete(record, protocol=None):
    """Terminal technical record; explicit numerical unknowns are still complete."""
    try:
        if record.get("scoring_contract_version") not in (SR_SCORING_VERSION, "oeq-sr-practical-v3-20261015"):
            return False
        validate_sr_benchmark_record(record, protocol)
        return True
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return False


def aggregate_sr_items(items):
    """Same complete-case joint cohort policy as legacy, with explicit nulls.

    Never average available dimensions into a row overall. A row with unknown
    Com, Cor, or Eff contributes coverage but not joint indices. Every repeated
    question ID is excluded. Per-component diagnostics have their own counts.
    """
    items = items if isinstance(items, list) else [items]
    versions = {item.get("evaluation", {}).get("scoring_contract_version") for item in items
                if isinstance(item, dict) and isinstance(item.get("evaluation"), dict)
                and not item["evaluation"].get("_error")}
    if None in versions:
        raise ValueError("Legacy and SR scoring contracts cannot be aggregated")
    if len(versions) > 1:
        raise ValueError("Mixed scoring contracts cannot be aggregated")
    version = next(iter(versions), SR_SCORING_VERSION)
    if version not in (SR_SCORING_VERSION, "oeq-sr-practical-v3-20261015"):
        raise ValueError("Unsupported scoring contract: " + str(version))
    for item in items:
        ev = item.get("evaluation") if isinstance(item, dict) else None
        if isinstance(ev, dict) and ev.get("scoring_contract_version") not in (None, version):
            raise ValueError("Mixed scoring contracts cannot be aggregated")
        if isinstance(ev, dict) and ev.get("scoring_contract_version") is None and not ev.get("_error"):
            raise ValueError("Legacy and SR scoring contracts cannot be aggregated")
    counts = Counter(str(item.get("question_id")) for item in items if isinstance(item, dict))
    valid, complete, excluded = [], [], []
    for index, item in enumerate(items):
        qid = item.get("question_id") if isinstance(item, dict) else None
        try:
            if qid is None:
                raise ValueError("missing_question_id")
            if counts[str(qid)] != 1:
                raise ValueError("duplicate_question_id")
            record = validate_sr_benchmark_record(item.get("evaluation"), item.get("model_response"))
            if str(record["task_evidence"]["question_id"]) != str(qid):
                raise ValueError("question_id differs from fixed evidence")
            row = record["calculated_scores"]
            valid.append(row)
            if row["I_A"] is None:
                raise ValueError(("unknown_components:" if record["unknown_components"] else "aggregate_domain:")
                                 + ",".join(record["unknown_components"] or record["aggregate_missing_reasons"]))
            complete.append(row)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            excluded.append({"index": index, "question_id": qid, "reason": str(exc)})
    n = len(complete)
    averages = {}
    for key in SCORE_COMPONENTS:
        avg = math.fsum(row["raw"][key] for row in complete) / n if n else None
        averages[key] = avg
        # Retain the legacy signed component-average display convention.
        averages[key + "_norm"] = avg / MAX_SCORES[key] if avg is not None else None
    indices = {key: math.fsum(row[key] for row in complete) / n if n else None
               for key in ("Com", "Cor", "Eff", "I_A", "HV", *METRIC_BLOCKS["effectiveness"])}
    indices["I_A_min_of_means"] = min(indices[key] for key in ("Com", "Cor", "Eff")) if n else None
    component_coverage = {}
    for key in (*SCORE_COMPONENTS, "sr", "sp", "Com", "Cor", "Eff", "I_A"):
        values = [(row["raw"][key] if key in SCORE_COMPONENTS else row[key]) for row in valid]
        known = [value for value in values if value is not None]
        component_coverage[key] = {
            "known_count": len(known), "missing_or_invalid_count": len(items) - len(known),
            "coverage": len(known) / len(items) if items else 0.0,
            "diagnostic_known_mean": math.fsum(known) / len(known) if known else None,
            "mean_scope": "COMPONENT_ONLY_NOT_JOINT_COHORT",
        }
    return {
        "aggregation_version": (SR_AGGREGATION_VERSION if version == SR_SCORING_VERSION
                                else "oeq-practical-mean-of-protocol-minima-v1"),
        "scoring_contract_version": version,
        "score_interpretation": SR_INTERPRETATION,
        "scientific_status": "UNRESOLVED", "cce_eligible": False, "official_scores": None,
        "average_scores": averages, "indices": indices,
        "application_index": indices["I_A"], "sample_count": n,
        "technical_valid_count": len(valid), "total_items": len(items),
        "coverage": n / len(items) if items else 0.0,
        "excluded_items": excluded, "component_coverage": component_coverage,
    }


def aggregate_versioned_items(items):
    """Dispatch homogeneous batches; legacy data keeps its exact old behavior."""
    items = items if isinstance(items, list) else [items]
    versions = {item.get("evaluation", {}).get("scoring_contract_version")
                for item in items if isinstance(item, dict) and isinstance(item.get("evaluation"), dict)
                and not item["evaluation"].get("_error")}
    if len(versions) > 1:
        raise ValueError("Mixed scoring contracts cannot be aggregated")
    version = next(iter(versions), None)
    if version is None:
        return aggregate_items(items)
    if version not in (SR_SCORING_VERSION, "oeq-sr-practical-v3-20261015"):
        raise ValueError("Unsupported scoring contract: " + str(version))
    return aggregate_sr_items(items)
