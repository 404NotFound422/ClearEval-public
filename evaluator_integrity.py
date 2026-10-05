"""Pure integrity safeguards for historical OEQ scoring; no model/network clients.

Structure, exact-source transformations and table identity are independently
observable. None of them alone certifies scientific applicability or formal CCE.
"""
import copy
import hashlib
import json
import math
import re
import unicodedata

INTEGRITY_VERSION = "legacy-integrity-v2-null-proposals"
FLAT_GROUNDING_VERSION = "flat-extraction-grounding-v2"


class JudgeFormatError(ValueError):
    """Technical judge output failure, distinct from a scientific unknown."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JudgeFormatError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise JudgeFormatError("Non-finite JSON number: " + value)


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise JudgeFormatError("Non-finite JSON number")
    return result


def strip_json_fence(text):
    """Unwrap one complete fence; never isolate/rewrite the first object."""
    if not isinstance(text, str):
        raise JudgeFormatError("Judge content must be text")
    value = text.strip()
    if value.startswith(("\x60\x60\x60", "~~~")):
        match = re.fullmatch(r"(\x60\x60\x60|~~~)(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n\1[ \t]*",
                             value, flags=re.IGNORECASE)
        if not match:
            raise JudgeFormatError("Incomplete or unsupported JSON fence")
        return match.group(2).strip()
    return value


def _validate_unicode(value):
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise JudgeFormatError("Unpaired unicode surrogate") from exc
    elif isinstance(value, dict):
        for key, child in value.items():
            _validate_unicode(key)
            _validate_unicode(child)
    elif isinstance(value, list):
        for child in value:
            _validate_unicode(child)


def parse_judge_object(text):
    """One object only: no duplicate keys, nonfinite numbers or silent repair."""
    try:
        result = json.loads(strip_json_fence(text), object_pairs_hook=_unique_pairs,
                            parse_constant=_reject_constant, parse_float=_finite_float)
    except json.JSONDecodeError as exc:
        raise JudgeFormatError("Invalid JSON: " + str(exc)) from exc
    if not isinstance(result, dict):
        raise JudgeFormatError("Judge JSON root must be an object")
    _validate_unicode(result)
    return result


def method_token(name):
    """Preserve digits and '+' so named protocol versions stay distinct."""
    if not isinstance(name, str):
        return ""
    return re.sub(r"[\s_\-\u2010-\u2015]", "", unicodedata.normalize("NFKC", name).casefold())


# Expand only an authored combined lookup key, not generic scientific synonyms.
_SOURCE_KEY_ALIASES = {"idisco(idisco+)": ("idisco", "idisco+")}


def resolve_method(name, keys):
    """Unique exact source key; no substrings or chemical-family fallback."""
    token, keys = method_token(name), list(keys)
    matches = [key for key in keys if token and method_token(key) == token]
    if not matches and token:
        matches = [key for key in keys if token in _SOURCE_KEY_ALIASES.get(method_token(key), ())]
    return matches[0] if len(matches) == 1 else None


def method_identity(name, keys, stages=None):
    keys = list(keys)
    if stages:
        return {"status": "COMPOSITE_UNREVIEWED", "resolved_key": None,
                "components": [{"stage_id": s["id"], "method_name": s["method_name"],
                                "resolved_key": resolve_method(s["method_name"], keys)} for s in stages],
                "reason": "Stage composition, order and scope need a reviewed rule"}
    key = resolve_method(name, keys)
    if key is not None:
        return {"status": "RESOLVED_SINGLE", "resolved_key": key, "components": []}
    text, components = unicodedata.normalize("NFKC", name or "").casefold(), []
    for key in keys:
        forms = [key] + list(_SOURCE_KEY_ALIASES.get(method_token(key), ()))
        if any(re.search(r"(?<![a-z0-9])" + re.escape(f.casefold()) + r"(?![a-z0-9+])", text) for f in forms):
            components.append(key)
    return {"status": "COMPOSITE_UNREVIEWED" if len(components) > 1 else
            ("UNKNOWN_METHOD" if name else "METHOD_UNREPORTED"), "resolved_key": None, "components": components}


def finite_nonnegative(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def validate_legacy_extraction(extraction):
    """Validate raw fields without coercion, imputation or adding missing facts."""
    if not isinstance(extraction, dict):
        raise JudgeFormatError("Teacher extraction must be an object")
    required = {"method_name", "marker_dict", "clearing_total_time_hours"}
    allowed = required | {"reagent_ri_value", "sample_ri_value", "protocol_time_hours", "reasoning",
                          "method_stages", "schema_version", "field_support"}
    if not required.issubset(extraction):
        raise JudgeFormatError("Teacher extraction missing required fields: " + ", ".join(sorted(required - extraction.keys())))
    if set(extraction) - allowed:
        raise JudgeFormatError("Unknown extraction fields: " + ", ".join(sorted(set(extraction) - allowed)))
    if extraction["method_name"] is not None and not isinstance(extraction["method_name"], str):
        raise JudgeFormatError("Teacher method_name must be a string or explicit null")
    markers = extraction["marker_dict"]
    if not isinstance(markers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in markers.items()):
        raise JudgeFormatError("Teacher marker_dict must map strings to strings")
    for key in ("clearing_total_time_hours", "reagent_ri_value", "sample_ri_value"):
        value = extraction.get(key)
        if value is not None and not finite_nonnegative(value):
            raise JudgeFormatError("Teacher " + key + " must be finite, nonnegative, or explicit null")
    if "protocol_time_hours" in extraction:
        value = extraction["protocol_time_hours"]
        if value is not None and (not isinstance(value, list) or any(not finite_nonnegative(v) for v in value)):
            raise JudgeFormatError("protocol_time_hours must be finite nonnegative hours array or null")
    if "reasoning" in extraction and not isinstance(extraction["reasoning"], str):
        raise JudgeFormatError("Extraction reasoning must be text")
    if "method_stages" in extraction and extraction["method_stages"] is not None:
        stages = extraction["method_stages"]
        if not isinstance(stages, list) or not stages:
            raise JudgeFormatError("method_stages must be nonempty array or explicit null")
        ids = set()
        for stage in stages:
            if (not isinstance(stage, dict) or set(stage) != {"id", "method_name", "quote"}
                    or any(not isinstance(stage[k], str) or not stage[k].strip() for k in stage)):
                raise JudgeFormatError("Method stage requires text id, method_name and exact quote")
            if stage["id"] in ids:
                raise JudgeFormatError("Duplicate method stage ID")
            ids.add(stage["id"])
    if "schema_version" in extraction and extraction["schema_version"] != FLAT_GROUNDING_VERSION:
        raise JudgeFormatError("Unsupported flat extraction schema_version")
    if "field_support" in extraction and not isinstance(extraction["field_support"], dict):
        raise JudgeFormatError("field_support must be an object")
    return extraction


def extraction_field_states(extraction):
    result = {}
    for field in ("method_name", "marker_dict", "clearing_total_time_hours", "reagent_ri_value",
                  "sample_ri_value", "protocol_time_hours", "method_stages"):
        if field not in extraction:
            state = "ABSENT"
        elif extraction[field] is None:
            state = "EXPLICIT_NULL"
        elif extraction[field] in ("", {}, []):
            state = "EXPLICIT_EMPTY"
        else:
            state = "REPORTED"
        result[field] = state
    return result


def validate_score_proposals(scores):
    maxima = {"completeness": {"c_step": 2, "c_param": 3},
              "correctness": {"co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1}}
    if not isinstance(scores, dict):
        raise JudgeFormatError("Teacher scores must be an object")
    for group, fields in maxima.items():
        block = scores.get(group)
        if not isinstance(block, dict):
            raise JudgeFormatError("Missing teacher score group: " + group)
        has_unknown = False
        for key, maximum in fields.items():
            record = block.get(key)
            if not isinstance(record, dict) or "score" not in record:
                raise JudgeFormatError("Missing teacher score: " + group + "." + key)
            value = record["score"]
            if value is None:
                reasoning = record.get("reasoning")
                if not isinstance(reasoning, str) or not reasoning.strip():
                    raise JudgeFormatError("Unknown teacher score needs reasoning: " + group + "." + key)
                has_unknown = True
            elif not finite_nonnegative(value) or value > maximum:
                raise JudgeFormatError("Invalid teacher score: " + group + "." + key)
        for key, value in block.items():
            if not key.startswith("total_"):
                continue
            if has_unknown:
                if value is not None:
                    raise JudgeFormatError("Unknown teacher group needs null total: " + group + "." + key)
            elif not finite_nonnegative(value) or value > sum(fields.values()):
                raise JudgeFormatError("Invalid teacher total: " + group + "." + key)
    return scores


def _pointer(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def _leaves(value, path=""):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            child_path = path + "/" + _pointer(key)
            # Dictionary marker keys also contain scientifically relevant labels.
            if path == "/marker_dict":
                yield child_path + "/@key", key
            for pair in _leaves(child, child_path):
                yield pair
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            for pair in _leaves(child, path + "/" + str(i)):
                yield pair
    else:
        yield path, value


def _check_span(span, text):
    if (not isinstance(span, dict) or set(span) != {"start", "end", "quote"}
            or isinstance(span.get("start"), bool) or isinstance(span.get("end"), bool)
            or not isinstance(span.get("start"), int) or not isinstance(span.get("end"), int)
            or not isinstance(span.get("quote"), str)
            or not 0 <= span["start"] < span["end"] <= len(text)
            or text[span["start"]:span["end"]] != span["quote"]):
        raise JudgeFormatError("Invalid exact source span")


_NEGATION = re.compile(r"\b(?:not|never|without|avoid|exclude|instead|cannot|don't|do\s+not)\b|不使用|不能|不用|禁止|避免", re.I)
_CONDITION = re.compile(r"\b(?:if|unless|provided that)\b|如果|若|仅当|待确认", re.I)
_TIME_UNIT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|小时|时|min|mins|minute|minutes|分钟|d|day|days|天)\s*$", re.I)


def _transform(raw, transform, path):
    if (path.startswith("/protocol_time_hours") or path == "/clearing_total_time_hours") and transform != "TIME_TO_HOURS":
        raise JudgeFormatError("Time extraction requires an explicit unit transform")
    if transform == "IDENTITY":
        if path.startswith("/protocol_time_hours") or path == "/clearing_total_time_hours":
            raise JudgeFormatError("Time extraction requires an explicit unit transform")
        return raw
    if transform == "STRIP":
        return raw.strip()
    if transform == "CASEFOLD":
        return raw.casefold()
    if transform == "NUMBER":
        if not re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", raw):
            raise JudgeFormatError("Invalid dimensionless source number")
        return float(raw)
    if transform == "TIME_TO_HOURS":
        match = _TIME_UNIT.fullmatch(raw)
        if not match:
            raise JudgeFormatError("Time source has no supported explicit unit")
        quantity, unit = float(match.group(1)), match.group(2).casefold()
        factor = 1 / 60 if unit in {"min", "mins", "minute", "minutes", "分钟"} else (
            24 if unit in {"d", "day", "days", "天"} else 1)
        return quantity * factor
    raise JudgeFormatError("Unsupported explicit transform")


def audit_flat_extraction(extraction, protocol):
    """Bridge flat fields to auditable explicit source transformations.

    Successful checks prove the supplied fields and transformations against their
    supplied clause spans. They do not certify omitted facts, contextual meaning,
    scientific truth or whole-protocol validity.
    """
    validate_legacy_extraction(extraction)
    if not isinstance(protocol, str):
        raise JudgeFormatError("Original protocol must be text")
    base = {"schema_version": FLAT_GROUNDING_VERSION,
            "answer_sha256": hashlib.sha256(protocol.encode("utf-8")).hexdigest(),
            "field_states": extraction_field_states(extraction), "facts": [], "issues": [],
            "omission_coverage": "NOT_CERTIFIED", "semantic_scope": "NOT_CERTIFIED"}
    if extraction.get("schema_version") != FLAT_GROUNDING_VERSION:
        return {**base, "fidelity_status": "LEGACY_STRUCTURE_ONLY", "validated": False}
    supports = extraction.get("field_support", {})
    fields = {k: v for k, v in extraction.items() if k not in {"schema_version", "field_support", "reasoning"}}
    expected = dict(_leaves(fields))
    if set(supports) != set(expected):
        base["issues"].append({"code": "FIELD_SUPPORT_COVERAGE", "missing": sorted(set(expected) - set(supports)),
                               "extra": sorted(set(supports) - set(expected))})
    for path, value in expected.items():
        support = supports.get(path)
        record = {"path": path, "value": value, "status": "UNRESOLVED"}
        try:
            if value is None or value in ({}, []):
                if support != {"kind": "MISSING"}:
                    raise JudgeFormatError("Explicit missing field needs MISSING support")
                record["status"] = "DECLARED_MISSING"
            else:
                if (not isinstance(support, dict) or set(support) != {"kind", "spans", "context_span", "raw_value", "transform"}
                        or support["kind"] != "EXPLICIT" or not isinstance(support["raw_value"], str)
                        or not isinstance(support["spans"], list) or len(support["spans"]) != 1):
                    raise JudgeFormatError("Explicit field requires one exact value span, clause context and transform")
                span, context = support["spans"][0], support["context_span"]
                _check_span(span, protocol)
                _check_span(context, protocol)
                if not context["start"] <= span["start"] < span["end"] <= context["end"]:
                    raise JudgeFormatError("Value span is outside clause context")
                if span["quote"] != support["raw_value"]:
                    raise JudgeFormatError("raw_value differs from original source span")
                # A supplied context cannot clip away the rest of the source
                # clause (e.g. quote only CUBIC from "Do not use CUBIC").
                delimiters = list(re.finditer(r"[。！？;；\n]|[.!?](?=\s|$)", protocol))
                left = max([d.end() for d in delimiters if d.end() <= span["start"]] or [0])
                right = min([d.start() for d in delimiters if d.start() >= span["end"]] or [len(protocol)])
                while left < right and protocol[left].isspace():
                    left += 1
                while right > left and protocol[right - 1].isspace():
                    right -= 1
                if context["start"] > left or context["end"] < right:
                    raise JudgeFormatError("Context clips the original clause")
                if _NEGATION.search(context["quote"]):
                    raise JudgeFormatError("Negated/alternative context requires independent semantic resolution")
                if _CONDITION.search(context["quote"]):
                    raise JudgeFormatError("Conditional context requires independent semantic resolution")
                transformed = _transform(support["raw_value"], support["transform"], path)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    equal = isinstance(transformed, (int, float)) and math.isclose(value, transformed, rel_tol=1e-12, abs_tol=1e-12)
                else:
                    equal = value == transformed
                if not equal:
                    raise JudgeFormatError("Extracted value differs from its declared source transform")
                record.update(status="FIELD_SUPPORT_VERIFIED", support=copy.deepcopy(support))
        except (JudgeFormatError, TypeError, KeyError) as exc:
            base["issues"].append({"code": "FIELD_SUPPORT_INVALID", "path": path, "detail": str(exc)})
        base["facts"].append(record)
    validated = not base["issues"]
    return {**base, "fidelity_status": "FIELD_SUPPORT_VERIFIED" if validated else "UNRESOLVED",
            "validated": validated}


def legacy_integrity_audit(extraction, protocol, effectiveness):
    fidelity = audit_flat_extraction(extraction, protocol)
    issues = list(fidelity["issues"])
    if not fidelity["validated"]:
        issues.append({"code": "EXTRACTION_FIDELITY_UNRESOLVED"})
    issues.append({"code": "REQUIREMENT_VALIDATION_NOT_BOUND",
                   "detail": "Numeric legacy rubric has no complete reviewed requirements/applicable-source judgments"})
    for stage in extraction.get("method_stages") or []:
        if stage["quote"] not in protocol:
            issues.append({"code": "INVALID_STAGE_QUOTE", "stage_id": stage["id"]})
    identity = effectiveness.get("method_identity", {})
    if identity.get("status") != "RESOLVED_SINGLE":
        issues.append({"code": identity.get("status", "METHOD_IDENTITY_UNKNOWN")})
    for field in ("s_method", "s_label", "s_time", "s_trans"):
        if effectiveness.get(field) is None:
            issues.append({"code": "UNKNOWN_COMPONENT", "component": field})
    return {"schema_version": INTEGRITY_VERSION, "technical_status": "VALID",
            "fidelity": fidelity, "scientific_status": "UNRESOLVED",
            "scoring_status": "LEGACY_DIAGNOSTIC_ONLY", "cce_eligible": False,
            "answer_sha256": fidelity["answer_sha256"], "issues": issues,
            "source_identity": "LOOKUP_IDENTITY_ONLY", "quote_authenticity": fidelity["fidelity_status"],
            "entailment": "NOT_CERTIFIED", "applicability": "NOT_CERTIFIED"}



def summarize_legacy_diagnostics(items):
    """Report pipeline/KB coverage without converting proposals into formal CCE."""
    if not isinstance(items, list):
        raise JudgeFormatError("Diagnostic summary needs a result array")
    components = {"completeness": {"c_step": (0, 2), "c_param": (0, 3)},
                  "correctness": {"co_order": (0, 3), "co_method": (0, 2), "co_param": (0, 2), "co_chem": (0, 1)},
                  "effectiveness": {"s_method": (-2.5, 2.5), "s_label": (0, 6), "s_trans": (0, 3), "s_time": (0, 3)}}
    stats = {group + "." + key: {"known_count": 0, "unknown_count": 0, "mean_proposal": None}
             for group, fields in components.items() for key in fields}
    values = {key: [] for key in stats}
    summary = {"schema_version": "legacy-diagnostic-summary-v1", "result_count": len(items),
               "technical_valid_count": 0, "technical_failure_count": 0, "legacy_diagnostic_count": 0,
               "other_record_count": 0, "formal_cce": None,
               "formal_cce_status": "NOT_COMPUTED_FROM_LEGACY_PROPOSALS",
               "scope": "Synthetic or stored pipeline diagnostics; score proposals are not scientific validation",
               "components": stats}
    for item in items:
        evaluation = item.get("evaluation") if isinstance(item, dict) else None
        if not isinstance(evaluation, dict) or not evaluation or evaluation.get("_error"):
            summary["technical_failure_count"] += 1
            continue
        if evaluation.get("technical_status") == "VALID":
            summary["technical_valid_count"] += 1
        if evaluation.get("scoring_status") != "LEGACY_DIAGNOSTIC_ONLY":
            summary["other_record_count"] += 1
            continue
        summary["legacy_diagnostic_count"] += 1
        blocks = evaluation.get("legacy_diagnostics", {}).get("scores", {})
        for group, fields in components.items():
            block = blocks.get(group, {})
            for key, (low, high) in fields.items():
                record = block.get(key, {}) if isinstance(block, dict) else {}
                value = record.get("score") if isinstance(record, dict) else None
                path = group + "." + key
                try:
                    valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                             and math.isfinite(value) and low <= value <= high)
                except OverflowError:
                    valid = False
                if valid:
                    values[path].append(value)
                    stats[path]["known_count"] += 1
                else:
                    stats[path]["unknown_count"] += 1
    for path, samples in values.items():
        stats[path]["mean_proposal"] = sum(samples) / len(samples) if samples else None
    from collections import Counter
    from results.oeq_metrics import protocol_scores
    identities = Counter(str(item.get("question_id")) for item in items if isinstance(item, dict))
    complete, excluded = [], []
    for item in items:
        if not isinstance(item, dict):
            excluded.append({"question_id": None, "reason": "invalid_record"})
            continue
        qid = item.get("question_id")
        evaluation = item.get("evaluation", {})
        if identities[str(qid)] != 1 or qid is None:
            excluded.append({"question_id": qid, "reason": "missing_or_duplicate_identity"})
            continue
        if (not isinstance(evaluation, dict) or evaluation.get("technical_status") != "VALID"
                or evaluation.get("scoring_status") != "LEGACY_DIAGNOSTIC_ONLY"):
            excluded.append({"question_id": qid, "reason": "not_completed_legacy_diagnostic"})
            continue
        scores = evaluation.get("legacy_diagnostics", {}).get("scores", {})
        try:
            indices = protocol_scores({"evaluation": {"scores": scores}})
        except ValueError as exc:
            excluded.append({"question_id": qid, "reason": str(exc)})
            continue
        complete.append({"question_id": qid, "indices": {key: indices[key] for key in ("Com", "Cor", "Eff", "I_A")}})
    summary["legacy_continuous_indices"] = {
        "status": "UNCALIBRATED_QUALITY_DIAGNOSTIC",
        "interpretation": "Legacy proposals only; no formal CCE, expert accuracy, or requirement validation claim.",
        "complete_count": len(complete), "excluded_count": len(excluded),
        "coverage": len(complete) / len(items) if items else None,
        "means": {key: sum(row["indices"][key] for row in complete) / len(complete) if complete else None
                  for key in ("Com", "Cor", "Eff", "I_A")},
        "records": complete, "excluded_records": excluded,
    }
    return summary
