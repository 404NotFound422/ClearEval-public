"""Expose existing numerical OEQ estimates without certifying scientific truth.

No model calls, no filled missing scores, and no replacement of the grounded
requirement evaluator. An estimate remains an uncalibrated model/KB assessment.
"""
import copy
import hashlib
import math

from evaluation_contract import json_hash
from evaluator_integrity import (
    FLAT_GROUNDING_VERSION, INTEGRITY_VERSION, audit_flat_extraction,
    parse_judge_object, validate_legacy_extraction, validate_score_proposals,
)
from results.oeq_metrics import METRIC_BLOCKS, aggregate_items, protocol_scores

BENCHMARK_ADAPTER_VERSION = "oeq-benchmark-estimate-v2"
BENCHMARK_STATUS = "AUTOMATED_BENCHMARK_ESTIMATE"
BENCHMARK_UNRESOLVED_STATUS = "BENCHMARK_UNRESOLVED"
BENCHMARK_INTERPRETATION = "AUTOMATED_BENCHMARK_ESTIMATE_NOT_SCIENTIFIC_CERTIFICATION"
HARD_ISSUES = {"FIELD_SUPPORT_COVERAGE", "FIELD_SUPPORT_INVALID", "INVALID_STAGE_QUOTE"}


class IncompleteBenchmarkScore(ValueError):
    """Valid proposal with explicitly unknown numerical components."""


def _unknown_components(scores):
    if not isinstance(scores, dict):
        raise ValueError("Missing numerical score object")
    unknown = []
    for group, fields in METRIC_BLOCKS.items():
        block = scores.get(group)
        if not isinstance(block, dict):
            raise ValueError("Missing numerical group: " + group)
        for key, maximum in fields.items():
            record = block.get(key)
            if not isinstance(record, dict) or "score" not in record:
                raise ValueError("Missing numerical component: " + key)
            value = record["score"]
            if value is None:
                unknown.append(group + "." + key)
            elif (isinstance(value, bool) or not isinstance(value, (int, float))
                  or not (-maximum if key == "s_method" else 0) <= value <= maximum
                  or not math.isfinite(value)):
                raise ValueError("Invalid numerical component: " + key)
    return unknown


def _record_hash(evaluation):
    return json_hash({key: value for key, value in evaluation.items()
                      if key != "benchmark_record_sha256"})


def _raw_fields(proposal):
    scores = proposal.get("scores") or {}
    extraction = proposal.get("extraction") or {}
    if not scores and any(key in proposal for key in ("C_step", "C_param", "total_completeness_score",
                                                "Co_order", "Co_method", "Co_param", "Co_chem")):
        scores = {
            "completeness": {"c_step": proposal.get("C_step", {}),
                             "c_param": proposal.get("C_param", {}),
                             "total_completeness_score": proposal.get("total_completeness_score", 0)},
            "correctness": {"co_order": proposal.get("Co_order", {}),
                            "co_method": proposal.get("Co_method", {}),
                            "co_param": proposal.get("Co_param", {}),
                            "co_chem": proposal.get("Co_chem", {}),
                            "critical_warnings": proposal.get("completeness_critical_warnings", []),
                            "total_correctness_score": proposal.get("total_correctness_score", 0)},
        }
    if not extraction and any(key in proposal for key in
                              ("marker_dict", "clearing_total_time_hours", "method_name")):
        extraction = {key: proposal[key] for key in (
            "marker_dict", "clearing_total_time_hours", "method_name", "reagent_ri_value",
            "sample_ri_value", "protocol_time_hours", "reasoning") if key in proposal}
    validate_legacy_extraction(extraction)
    validate_score_proposals(scores)
    return scores, extraction


def is_workflow_obligation_complete(evaluation, protocol=None, *, allow_failure=False):
    """Validate the sidecar obligation and original-input bindings, never truth."""
    try:
        if not isinstance(evaluation, dict) or evaluation.get("workflow_diagnostics_required") is not True:
            return False
        binding = evaluation.get("workflow_diagnostics_binding")
        if not isinstance(binding, dict) or set(binding) != {"question_sha256", "protocol_sha256"}:
            return False
        if any(not isinstance(value, str) or len(value) != 64
               or any(ch not in "0123456789abcdef" for ch in value) for value in binding.values()):
            return False
        if protocol is not None and hashlib.sha256(protocol.encode("utf-8")).hexdigest() != binding["protocol_sha256"]:
            return False
        for value in (evaluation.get("protocol_sha256"), (evaluation.get("integrity") or {}).get("answer_sha256")):
            if value is not None and value != binding["protocol_sha256"]:
                return False
        question_sha = (evaluation.get("meta_data") or {}).get("question_sha256")
        if question_sha is not None and question_sha != binding["question_sha256"]:
            return False
        diag = evaluation.get("workflow_diagnostics")
        if diag is None:
            failure = evaluation.get("workflow_diagnostics_failure")
            return bool(allow_failure and evaluation.get("technical_status") == "FAILED"
                        and evaluation.get("failure_stage") == "WORKFLOW_DIAGNOSTICS"
                        and isinstance(evaluation.get("_error"), str) and evaluation["_error"]
                        and "scores" not in evaluation and isinstance(failure, dict)
                        and failure.get("input_binding") == binding
                        and failure.get("error") == evaluation["_error"]
                        and failure.get("error_type") == evaluation.get("_error_type"))
        from oeq_workflow_diagnostics import is_workflow_diagnostics_complete
        return (is_workflow_diagnostics_complete(diag, protocol=protocol)
                and evaluation.get("workflow_diagnostics_sha256") == json_hash(diag)
                and all(diag.get(key) == value for key, value in binding.items()))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def workflow_sources_match_contract(evaluation, contract):
    """Match retained resource/implementation hashes to the run manifest."""
    if not is_workflow_obligation_complete(evaluation, allow_failure=True):
        return False
    diag = evaluation.get("workflow_diagnostics")
    if diag is None:
        return True  # Explicit construction failure contributes no score or source claim.
    sources = contract.get("source_sha256")
    if not isinstance(sources, dict):
        return False
    return all(sources.get(name) == digest for field in ("resource_bindings", "implementation_hashes")
               for name, digest in diag[field].items())


def summarize_workflow_diagnostics(items, *, required=False):
    """Keep missing/failed diagnostics in the full-input denominator."""
    from collections import Counter
    completed, failures, missing = [], 0, 0
    for item in items:
        ev = item.get("evaluation") if isinstance(item, dict) else None
        if is_workflow_obligation_complete(ev, allow_failure=True):
            if ev.get("workflow_diagnostics") is None:
                failures += 1
            else:
                completed.append(ev["workflow_diagnostics"])
        else:
            missing += 1
    result = dict(schema_version="oeq-workflow-summary-v1", required=required,
                  total_items=len(items), diagnostic_complete_count=len(completed),
                  diagnostic_construction_failure_count=failures, diagnostic_missing_count=missing,
                  diagnostic_coverage=len(completed) / len(items) if items else 0,
                  scientific_certified_count=0, scientific_accuracy=None, expert_consistency=None,
                  task_function_status_counts=dict(Counter(
                      row["diagnostic"]["status"] for diag in completed for row in diag["task_function_diagnostics"])),
                  objective_relation_counts=dict(Counter(
                      diag["objective_diagnostics"]["relationship"] for diag in completed)),
                  source_condition_local_risk_count=sum(
                      diag["source_condition_diagnostics"]["local_risk_count"] for diag in completed),
                  source_guidance_potential_conflict_count=sum(
                      diag["source_condition_diagnostics"]["potential_conflict_count"] for diag in completed),
                  source_author_recipe_nonconformance_count=sum(
                      diag["source_condition_diagnostics"]["author_recipe_nonconformance_count"] for diag in completed),
                  source_condition_review_required_count=sum(
                      diag["source_condition_diagnostics"]["review_required_count"] for diag in completed),
                  interpretation="DIAGNOSTIC_COVERAGE_IS_NOT_SCIENTIFIC_ACCURACY")
    result["summary_sha256"] = json_hash(result)
    return result


def is_workflow_summary_complete(summary, total_items):
    try:
        if (type(total_items) is not int or total_items < 0
                or not isinstance(summary, dict) or summary.get("schema_version") != "oeq-workflow-summary-v1"
                or summary.get("required") is not True or summary.get("total_items") != total_items
                or summary.get("scientific_certified_count") != 0 or summary.get("scientific_accuracy") is not None
                or summary.get("expert_consistency") is not None
                or summary.get("interpretation") != "DIAGNOSTIC_COVERAGE_IS_NOT_SCIENTIFIC_ACCURACY"):
            return False
        counts = [summary.get(key) for key in ("diagnostic_complete_count", "diagnostic_construction_failure_count", "diagnostic_missing_count")]
        if any(type(value) is not int or value < 0 for value in counts) or sum(counts) != total_items or counts[2] != 0:
            return False
        return (summary.get("diagnostic_coverage") == (counts[0] / total_items if total_items else 0)
                and summary.get("summary_sha256") == json_hash({key:value for key,value in summary.items() if key != "summary_sha256"}))
    except (TypeError, ValueError, OverflowError):
        return False


def _validate_basis(evaluation, protocol=None, *, allow_incomplete=False):
    if (not isinstance(evaluation, dict) or evaluation.get("_error")
            or evaluation.get("technical_status") != "VALID"):
        raise ValueError("No technically valid numerical proposal")
    if (evaluation.get("workflow_diagnostics_required") is True
            or any(key in evaluation for key in ("workflow_diagnostics", "workflow_diagnostics_binding", "workflow_diagnostics_sha256"))):
        if not is_workflow_obligation_complete(evaluation, protocol):
            raise ValueError("Missing or invalid bound workflow diagnostics")
    diagnostics = evaluation.get("legacy_diagnostics")
    integrity = evaluation.get("integrity")
    if (not isinstance(diagnostics, dict) or not isinstance(integrity, dict)
            or integrity.get("schema_version") != INTEGRITY_VERSION):
        raise ValueError("Missing versioned numerical integrity audit")
    generation = evaluation.get("teacher_generation")
    if not isinstance(generation, dict) or generation.get("technical_status") != "VALID":
        raise ValueError("Missing valid original teacher generation")
    proposal = parse_judge_object(generation.get("content"))
    raw_scores, raw_extraction = _raw_fields(proposal)
    if (raw_extraction != evaluation.get("extraction")
            or raw_scores != diagnostics.get("raw_teacher_scores")):
        raise ValueError("Numerical proposal differs from original teacher output")
    if ("field_support" in raw_extraction
            and raw_extraction.get("schema_version") != FLAT_GROUNDING_VERSION):
        raise ValueError("Supplied field support lacks its required schema version")
    scores = diagnostics.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("Missing numerical score object")
    if any(scores.get(group) != raw_scores.get(group)
           for group in ("completeness", "correctness")):
        raise ValueError("Teacher score groups differ from original proposal")
    issues = integrity.get("issues")
    if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
        raise ValueError("Malformed integrity issues")
    if HARD_ISSUES.intersection(issue.get("code") for issue in issues):
        raise ValueError("Invalid original quotation or field support")
    identity = diagnostics.get("method_identity")
    if not isinstance(identity, dict):
        raise ValueError("Missing method identity")
    components = identity.get("components", [])
    if not isinstance(components, list):
        raise ValueError("Malformed method identity components")
    resolved = {component.get("resolved_key") if isinstance(component, dict) else component
                for component in components}
    resolved.discard(None)
    if len(resolved) > 1:
        raise ValueError("Multiple method identities cannot inherit one numerical estimate")
    if protocol is not None:
        if not isinstance(protocol, str):
            raise ValueError("Original protocol must be text")
        digest = hashlib.sha256(protocol.encode("utf-8")).hexdigest()
        if integrity.get("answer_sha256") != digest:
            raise ValueError("Numerical audit is bound to another protocol")
        fidelity = audit_flat_extraction(raw_extraction, protocol)
        if fidelity != integrity.get("fidelity") or fidelity.get("issues"):
            raise ValueError("Original protocol field audit differs or has hard errors")
        if any(stage["quote"] not in protocol
               for stage in raw_extraction.get("method_stages") or []):
            raise ValueError("Invalid original method stage quote")
    unknown = _unknown_components(scores)
    if unknown and not allow_incomplete:
        raise IncompleteBenchmarkScore("Explicitly unknown numerical components: " + ", ".join(unknown))
    if not unknown:
        protocol_scores({"evaluation": {"scores": scores}})
    return scores


def promote_benchmark_estimate(evaluation, protocol, demand_provenance=None):
    """Copy a complete checked numerical proposal; raise on hard/missing inputs."""
    scores = _validate_basis(evaluation, protocol)
    result = copy.deepcopy(evaluation)
    result.update(
        scores=copy.deepcopy(scores), scoring_status=BENCHMARK_STATUS,
        score_interpretation=BENCHMARK_INTERPRETATION,
        scientific_status="UNRESOLVED", cce_eligible=False, official_scores=None,
        benchmark_adapter_version=BENCHMARK_ADAPTER_VERSION,
        scores_sha256=json_hash(scores),
        teacher_generation_sha256=json_hash(result["teacher_generation"]),
        protocol_sha256=result["integrity"]["answer_sha256"],
        demand_provenance=copy.deepcopy(demand_provenance if demand_provenance is not None
                                        else result.get("meta_data", {}).get("demand_provenance", {})),
    )
    result["benchmark_record_sha256"] = _record_hash(result)
    return result


def promote_unresolved_benchmark(evaluation, protocol, demand_provenance=None):
    """Keep a valid but numerically incomplete record as a completed diagnostic."""
    scores = _validate_basis(evaluation, protocol, allow_incomplete=True)
    unknown = _unknown_components(scores)
    if not unknown:
        raise ValueError("A complete numerical proposal is not an unresolved record")
    result = copy.deepcopy(evaluation)
    result.pop("scores", None)
    result.update(
        scoring_status=BENCHMARK_UNRESOLVED_STATUS, score_interpretation=BENCHMARK_INTERPRETATION,
        scientific_status="UNRESOLVED", cce_eligible=False, official_scores=None,
        benchmark_adapter_version=BENCHMARK_ADAPTER_VERSION, unknown_components=unknown,
        scores_sha256=json_hash(scores), teacher_generation_sha256=json_hash(result["teacher_generation"]),
        protocol_sha256=result["integrity"]["answer_sha256"],
        demand_provenance=copy.deepcopy(demand_provenance if demand_provenance is not None
                                        else result.get("meta_data", {}).get("demand_provenance", {})),
    )
    result["benchmark_record_sha256"] = _record_hash(result)
    return result


def is_benchmark_record_complete(evaluation, protocol=None):
    """Technical completion includes a valid explicit numerical unknown."""
    if isinstance(evaluation, dict) and evaluation.get("robustness_diagnostics_required") is True:
        from oeq_robustness import is_report_complete
        if not is_report_complete(evaluation):
            return False
    if is_benchmark_complete(evaluation, protocol):
        return True
    try:
        if (not isinstance(evaluation, dict)
                or evaluation.get("scoring_status") != BENCHMARK_UNRESOLVED_STATUS
                or evaluation.get("score_interpretation") != BENCHMARK_INTERPRETATION
                or evaluation.get("benchmark_adapter_version") != BENCHMARK_ADAPTER_VERSION
                or evaluation.get("scientific_status") != "UNRESOLVED"
                or evaluation.get("cce_eligible") is not False
                or evaluation.get("official_scores") is not None
                or "official_scores" not in evaluation or "scores" in evaluation
                or evaluation.get("teacher_generation_sha256") != json_hash(evaluation.get("teacher_generation"))
                or evaluation.get("benchmark_record_sha256") != _record_hash(evaluation)):
            return False
        scores = _validate_basis(evaluation, protocol, allow_incomplete=True)
        unknown = _unknown_components(scores)
        return bool(unknown) and (
            evaluation.get("unknown_components") == unknown
            and evaluation.get("scores_sha256") == json_hash(scores)
            and evaluation.get("protocol_sha256") == evaluation["integrity"].get("answer_sha256"))
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def is_benchmark_complete(evaluation, protocol=None):
    """Check the estimate contract; runner also replays KB arithmetic on resume."""
    if isinstance(evaluation, dict) and evaluation.get("robustness_diagnostics_required") is True:
        from oeq_robustness import is_report_complete
        if not is_report_complete(evaluation):
            return False
    try:
        if (not isinstance(evaluation, dict)
                or evaluation.get("scoring_status") != BENCHMARK_STATUS
                or evaluation.get("score_interpretation") != BENCHMARK_INTERPRETATION
                or evaluation.get("benchmark_adapter_version") != BENCHMARK_ADAPTER_VERSION
                or evaluation.get("scientific_status") != "UNRESOLVED"
                or evaluation.get("cce_eligible") is not False
                or evaluation.get("official_scores") is not None
                or "official_scores" not in evaluation
                or evaluation.get("scores_sha256") != json_hash(evaluation.get("scores"))
                or evaluation.get("teacher_generation_sha256") != json_hash(evaluation.get("teacher_generation"))
                or evaluation.get("benchmark_record_sha256") != _record_hash(evaluation)):
            return False
        basis = _validate_basis(evaluation, protocol)
        if evaluation["scores"] != basis:
            return False
        if evaluation.get("protocol_sha256") != evaluation["integrity"].get("answer_sha256"):
            return False
        protocol_scores({"evaluation": evaluation})
        return True
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def summarize_benchmark_estimates(items):
    valid, completed, excluded = [], [], []
    for item in items:
        if isinstance(item, dict) and is_benchmark_record_complete(item.get("evaluation")):
            completed.append(item)
            if is_benchmark_complete(item["evaluation"]):
                valid.append(item)
            else:
                excluded.append({"question_id": item.get("question_id"),
                                 "reason": "explicitly_unknown_components",
                                 "components": item["evaluation"]["unknown_components"]})
        else:
            excluded.append({"question_id": item.get("question_id") if isinstance(item, dict) else None,
                             "reason": "incomplete_benchmark_estimate"})
    aggregate = aggregate_items(valid)
    aggregate.update(
        schema_version="benchmark-estimate-summary-v1", assessment_mode="benchmark",
        result_count=len(items), total_items=len(items),
        coverage=aggregate["sample_count"] / len(items) if items else 0,
        technical_valid_count=len(completed),
        technical_failure_count=len(items)-len(completed),
        benchmark_unresolved_count=len(completed)-len(valid),
        benchmark_estimate_count=aggregate["sample_count"],
        score_interpretation=BENCHMARK_INTERPRETATION,
        scientific_status="UNRESOLVED", formal_cce=None,
        formal_cce_status="INDEPENDENT_SCIENTIFIC_VALIDATION_PENDING",
        full_input_coverage=aggregate["sample_count"] / len(items) if items else 0,
    )
    aggregate["workflow_diagnostics_summary"] = summarize_workflow_diagnostics(
        items, required=any((item.get("evaluation") or {}).get("workflow_diagnostics_required") is True for item in items if isinstance(item, dict)))
    from oeq_robustness import summarize_reports
    aggregate["robustness_summary"] = summarize_reports(items, required=any(
        (item.get("evaluation") or {}).get("robustness_diagnostics_required") is True for item in items))
    aggregate["excluded_items"] += excluded
    return aggregate
