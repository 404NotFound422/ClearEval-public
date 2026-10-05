"""Finite source-bound action declarations, never scientific-success inference.

Existing scientific fields only: legacy extraction is never upgraded. Missing
finite vocabulary coverage cannot establish a violation or scientific omission.
"""
from copy import deepcopy
import re

from .fidelity import SCHEMA, audit_field, text_hash
from .requirement_scope import resolve_scope, scope_contains_span
from .task_state import (
    INITIAL_FIXATION, MEMBRANE_LABEL_DIFFUSION, PRE_CLEARING_INITIAL_LABEL_QC,
    LYMPHOCYTE_T_B_DISCRIMINATION,
)

VERSION = "declared-task-function-action-v1"
SCOPE = "DECLARED_FUNCTION_ACTION_NOT_SCIENTIFIC_SUCCESS"
# Finite declaration tokens, not recipes, measured outcomes or gold labels.
_OBJECTS = {
    INITIAL_FIXATION: r"(?:固定|\bfixation\b)",
    MEMBRANE_LABEL_DIFFUSION: r"(?:膜内扩散|膜(?:内)?标记扩散|\bmembrane(?:[- ]label)? diffusion\b)",
    PRE_CLEARING_INITIAL_LABEL_QC: (
        r"(?:(?:初始|独立|透明前)(?:标记)?(?:质控|QC)"
        r"|\b(?:initial|independent|pre[- ]clearing) (?:label )?(?:QC|quality control)\b)"
    ),
}
_VERB = r"(?:\b(?:perform|include|complete|schedule|conduct|carry out)\b\s+(?:(?:the|a|an|initial)\s+)*|(?:进行|执行|完成|安排|包括|包含|纳入)(?:初始)?)"
_ACTION = {
    key: re.compile(_VERB + obj + r"|" + obj + r"\s+(?:will|shall|must)\s+be\s+(?:performed|completed|conducted)\b", re.I)
    for key, obj in _OBJECTS.items()
}
_ACTION[INITIAL_FIXATION] = re.compile(
    _ACTION[INITIAL_FIXATION].pattern + r"|\bfix\s+(?:the\s+)?(?:sample|specimen|tissue)\b", re.I)
_CONDITIONAL = re.compile(r"\b(?:if|unless|provided that|when needed|conditional(?:ly)?|may|might|could|optional)\b|若|如果|如需|必要时|假如|仅当|可选|可能", re.I)
_NEGATED = re.compile(r"\b(?:not|no|never|without|omit(?:ted)?|skip|refuse|avoid|exclude(?:d)?|decline)\b|不|无需|省略|拒绝|跳过", re.I)
_UNKNOWN = re.compile(r"\b(?:unknown|unclear|unresolved|uncertain|not known)\b|未知|不明确|尚不清楚|无法确认|待确认", re.I)
_MENTION = re.compile(r"\b(?:mention(?:ed)?|discuss(?:ion)?|consider|example|reported|quote|quoting|previously|already|phrase|word|heading|title|term|description|citation|reference|says|appears|literature|source|author|recommend(?:s|ed|ation)?)\b|仅提及|讨论|考虑|示例|引述|文献|作者|建议|已完成|已经完成|此前|[\"“”‘’']", re.I)


def _exact(span, protocol):
    if not isinstance(span, dict):
        return None
    start, end, quote = (span.get(k) for k in ("start", "end", "quote"))
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(protocol)
            or not isinstance(quote, str) or protocol[start:end] != quote):
        return None
    return dict(start=start, end=end, quote=quote)


def _source_context(protocol, span):
    # Retain comma conditions and a preceding conditional heading across lines.
    # A newline does not establish that a condition or negation has closed.
    boundaries = "。;；.!?！？"
    start, end = span["start"], span["end"]
    while start > 0 and protocol[start - 1] not in boundaries:
        start -= 1
    while end < len(protocol) and protocol[end] not in boundaries:
        end += 1
    return dict(start=start, end=end, quote=protocol[start:end])



def _governing_headings(protocol, span):
    """Retain prior conditional/unknown/reference headings for scope review.

    Closing a governing heading requires proof outside this finite checker;
    neither a numbered step, blank line nor a later full stop proves closure.
    This deliberately conservative scan may abstain on otherwise valid plans.
    """
    result = []
    for match in re.finditer(r"[^\r\n]+", protocol[:span["start"]]):
        line = match.group()
        stripped = line.strip().lstrip("#*- ").strip()
        heading = stripped.endswith((":", "："))
        leading_condition = (_CONDITIONAL.match(stripped) is not None
                             and not stripped.endswith((".", "。", ";", "；", "!", "?", "！", "？")))
        if (heading or leading_condition) and any(
                p.search(line) for p in (_CONDITIONAL, _NEGATED, _UNKNOWN, _MENTION)):
            result.append(dict(start=match.start(), end=match.end(), quote=line))
    return result


def assess_required_function(rule, extraction, protocol, fidelity,
                             source_scope=None, route_id=None):
    """Check affirmed finite action presence, or NOT_REQUIRED applicability.

    U/UNDER_SPECIFIED preserve absent scope, fidelity, vocabulary and task
    applicability. No VIOLATED status is emitted. Required T/B goals need
    scientific evidence elsewhere. Inputs and source offsets are never changed.
    """
    if not isinstance(rule, dict) or rule.get("type") != "TASK_INITIAL_FUNCTION":
        raise ValueError("TASK_INITIAL_FUNCTION literal rule required")
    if not isinstance(protocol, str):
        raise ValueError("Unchanged protocol text required")
    audit = rule.get("state_audit")
    if not isinstance(audit, dict):
        raise ValueError("Original task-state audit required")
    function = rule.get("function")
    obligation = audit.get("execution_obligation")
    result = dict(version=VERSION, status="UNRESOLVED", scope=SCOPE,
                  required_function=function, execution_obligation=obligation,
                  task_state=audit.get("state"), route_id=route_id,
                  protocol_sha256=text_hash(protocol), scientific_truth=None,
                  action_presence_certified=False, guards=[], action_evidence=[], context_review_spans=[],
                  coverage="FINITE_DECLARATION_VOCABULARY_NOT_COMPLETENESS_PROOF")

    def finish(*guards, status="UNRESOLVED"):
        result.update(status=status, guards=list(dict.fromkeys(guards)))
        return result

    if audit.get("function", function) != function or audit.get("metadata_conflict"):
        return finish("TASK_FUNCTION_STATE_CONFLICT")
    if audit.get("state") in {"CONDITIONAL", "CONFLICTING"} or obligation not in {"REQUIRED", "NOT_REQUIRED"}:
        return finish("TASK_FUNCTION_APPLICABILITY_UNRESOLVED")
    if function not in {*_OBJECTS, LYMPHOCYTE_T_B_DISCRIMINATION}:
        return finish("FUNCTION_OUTSIDE_FINITE_VOCABULARY")
    if obligation == "NOT_REQUIRED":
        result["applicability_only"] = True
        result["repetition_prohibited"] = False
        return finish("NOT_REQUIRED_DOES_NOT_PROHIBIT_REPETITION", status="SATISFIED")
    if function == LYMPHOCYTE_T_B_DISCRIMINATION:
        return finish("FUNCTION_GOAL_REQUIRES_SCIENTIFIC_EVIDENCE")
    if function not in _ACTION:
        return finish("FUNCTION_OUTSIDE_FINITE_VOCABULARY")
    if not isinstance(extraction, dict) or extraction.get("schema_version") != SCHEMA:
        return finish("LEGACY_OR_UNVERIFIED_EXTRACTION")
    if (not isinstance(fidelity, dict) or fidelity.get("schema_version") != SCHEMA
            or fidelity.get("protocol_sha256") != text_hash(protocol)
            or not isinstance(fidelity.get("facts"), list)
            or not isinstance(fidelity.get("issues"), list)):
        return finish("FUNCTION_FIDELITY_UNVERIFIED_OR_INPUT_CHANGED")
    if source_scope is None:
        req = {"scope": "ROUTE", "route_id": route_id} if route_id is not None else {}
        source_scope = resolve_scope(req, extraction, protocol)
    if (not isinstance(source_scope, dict) or source_scope.get("scope_status") != "RESOLVED"
            or source_scope.get("protocol_sha256") != text_hash(protocol)
            or source_scope.get("scope") not in {"GLOBAL", "ROUTE"}
            or source_scope.get("scope") == "ROUTE" and not isinstance(source_scope.get("route_id"), str)
            or not isinstance(source_scope.get("regions"), list)
            or any(_exact(s, protocol) is None for s in source_scope["regions"])):
        return finish("REQUIREMENT_SOURCE_REGION_UNRESOLVED")
    scoped_route = source_scope.get("route_id") if source_scope.get("scope") == "ROUTE" else None
    if route_id is not None and scoped_route != route_id:
        return finish("REQUIREMENT_ROUTE_SCOPE_CONFLICT")
    route_id = scoped_route if scoped_route is not None else route_id
    result["route_id"] = route_id
    result["source_scope"] = deepcopy(source_scope)
    rows = extraction.get("steps")
    if not isinstance(rows, list):
        return finish("FUNCTION_STEP_COLLECTION_UNVERIFIED")
    relevant, guards = False, []
    # Negative declarations may have been omitted from the extraction. Keep
    # original scoped refusals visible without using token matches for credit.
    for region in source_scope["regions"]:
        for mention in re.finditer(_OBJECTS[function], region["quote"], re.I):
            token = dict(start=region["start"] + mention.start(),
                         end=region["start"] + mention.end(), quote=mention.group())
            context = _source_context(protocol, token)
            if _NEGATED.search(context["quote"]):
                guards.append("FUNCTION_EXPLICIT_SOURCE_REFUSAL_REQUIRES_REVIEW")
                if context not in result["context_review_spans"]:
                    result["context_review_spans"].append(context)
    for fact in fidelity["facts"]:
        if not isinstance(fact, dict) or fact.get("collection") != "steps":
            continue
        if route_id is not None and fact.get("branch") != route_id:
            guards.append("FUNCTION_ACTION_IN_OTHER_ROUTE")
            continue
        relevant = True
        index = fact.get("index")
        if type(index) is not int or not 0 <= index < len(rows) or not isinstance(rows[index], dict):
            guards.append("FUNCTION_FACT_RECORD_UNVERIFIED")
            continue
        row = rows[index]
        fields = fact.get("fields")
        operation = fields.get("operation") if isinstance(fields, dict) else None
        if (not isinstance(operation, dict) or operation.get("status") != "GROUNDED"
                or operation.get("kind") not in {"EXPLICIT", "DERIVED"}
                or operation.get("issues")
                or row.get("id") != fact.get("id") or row.get("branch") != fact.get("branch")
                or row.get("assertion") != fact.get("assertion")):
            guards.append("FUNCTION_OPERATION_FIDELITY_UNVERIFIED")
            continue
        if any(not isinstance(i, dict) or (
                i.get("collection") is None or i.get("collection") == "steps" and i.get("index") == index
                and i.get("field") in {None, "operation"}) for i in fidelity["issues"]):
            guards.append("FUNCTION_OPERATION_FIDELITY_UNVERIFIED")
            continue
        assertion = fact.get("assertion")
        if not isinstance(assertion, dict) or assertion.get("polarity") != "AFFIRMED":
            guards.append("FUNCTION_ACTION_NOT_AFFIRMED")
            continue
        try:
            support = row.get("field_support", {}).get("operation")
            verified = audit_field(row.get("operation"), support, protocol,
                                   row_quote=row.get("quote"), field_scope_policy="diagnostic")
        except (ValueError, TypeError, AttributeError):
            guards.append("FUNCTION_OPERATION_FIDELITY_UNVERIFIED")
            continue
        spans = operation.get("spans")
        exact_spans = [_exact(s, protocol) for s in spans] if isinstance(spans, list) else []
        verified_spans = [_exact(s, protocol) for s in verified.get("spans", [])]
        if (verified.get("status") != "GROUNDED" or not exact_spans or None in exact_spans
                or exact_spans != verified_spans
                or operation.get("raw_value") != verified.get("raw_value")
                or operation.get("transform") != verified.get("transform")
                or operation.get("kind") != verified.get("kind")):
            guards.append("FUNCTION_OPERATION_FIDELITY_UNVERIFIED")
            continue
        if not all(scope_contains_span(source_scope, s, protocol) for s in exact_spans):
            guards.append("FUNCTION_ACTION_OUTSIDE_REQUIREMENT_SOURCE_REGION")
            continue
        raw = verified.get("raw_value", "")
        if not re.search(_OBJECTS[function], raw, re.I) and not (
                function == INITIAL_FIXATION and _ACTION[function].search(raw)):
            continue
        for span in exact_spans:
            context = _source_context(protocol, span)
            headings = _governing_headings(protocol, span)
            if headings:
                guards.append("FUNCTION_SOURCE_HEADING_SCOPE_UNRESOLVED")
                for heading in headings:
                    if heading not in result["context_review_spans"]:
                        result["context_review_spans"].append(heading)
                continue
            if any(p.search(context["quote"]) for p in (_CONDITIONAL, _NEGATED, _UNKNOWN, _MENTION)):
                guards.append("FUNCTION_ACTION_CONTEXT_REQUIRES_REVIEW")
                continue
            match = _ACTION[function].search(span["quote"])
            if match:
                anchor = dict(start=span["start"] + match.start(), end=span["start"] + match.end(), quote=match.group())
                result["action_evidence"].append(dict(record_id=fact.get("id"), index=index,
                    branch=fact.get("branch"), operation_span=span, action_span=anchor,
                    source_context=context))
            else:
                guards.append("FUNCTION_MENTION_NOT_FINITE_ACTION_DECLARATION")
    if result["action_evidence"] and any(g in {
            "FUNCTION_ACTION_CONTEXT_REQUIRES_REVIEW", "FUNCTION_ACTION_NOT_AFFIRMED",
            "FUNCTION_SOURCE_HEADING_SCOPE_UNRESOLVED", "FUNCTION_EXPLICIT_SOURCE_REFUSAL_REQUIRES_REVIEW",
            "FUNCTION_OPERATION_FIDELITY_UNVERIFIED", "FUNCTION_FACT_RECORD_UNVERIFIED"} for g in guards):
        return finish(*guards, "FUNCTION_ACTION_DEPENDENCIES_REQUIRE_REVIEW")
    if result["action_evidence"]:
        result["action_presence_certified"] = True
        return finish(*guards, status="SATISFIED")
    return finish(*(guards or ["FUNCTION_NOT_FOUND_IN_VERIFIED_FINITE_ACTION_VOCABULARY"]),
                  status="UNRESOLVED" if relevant or guards else "UNDER_SPECIFIED")
