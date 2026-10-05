"""Explicit evidence, requirement, extraction and time contracts.

Validation establishes data integrity and admissibility, not scientific truth.
The model's proposal and every deterministic guard are retained separately.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .evidence import check_scientific_support, validate_cards
from .fidelity import SCHEMA as EXTRACTION_SCHEMA, audit_extraction

STATES = {"SATISFIED", "VIOLATED", "UNDER_SPECIFIED", "UNRESOLVED"}
BASES = {"PROTOCOL_TEXT", "SUPPLIED_EVIDENCE", "MODEL_KNOWLEDGE", "MISSING"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Non-finite JSON constant: " + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def read(path):
    return parse_json(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value, *, immutable=True):
    path = Path(path)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if read(path) != value:
            raise ValueError("Refusing to change frozen file: " + str(path))
        return
    # x-mode prevents concurrent replacement of an immutable artifact.
    with path.open("x" if immutable else "w", encoding="utf-8", newline="\n") as f:
        f.write(data)


def anchors(text, quote):
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError("Empty quotation")
    offsets, start = [], 0
    while (start := text.find(quote, start)) >= 0:
        offsets.append({"start": start, "end": start + len(quote),
                        "line": text.count("\n", 0, start) + 1})
        start += len(quote)
    if not offsets:
        raise ValueError("Quotation absent from protocol")
    return {"quote": quote, "occurrences": offsets,
            "ambiguous_location": len(offsets) > 1}


def combine(states, operator="all"):
    """Four-state necessary conjunction / complete-route disjunction."""
    values = list(states)
    if not values or any(s not in STATES for s in values):
        raise ValueError("Nonempty valid states required")
    if operator == "all":
        if "VIOLATED" in values:
            return "VIOLATED"
        if all(s == "SATISFIED" for s in values):
            return "SATISFIED"
    elif operator == "any":
        if "SATISFIED" in values:
            return "SATISFIED"
        if all(s == "VIOLATED" for s in values):
            return "VIOLATED"
    else:
        raise ValueError("Invalid logical operator")
    return "UNDER_SPECIFIED" if "UNDER_SPECIFIED" in values else "UNRESOLVED"


def evaluate_formula(formula, values):
    if isinstance(formula, str):
        if formula not in values:
            raise ValueError("Unbound formula requirement: " + formula)
        return values[formula]
    if not isinstance(formula, dict) or len(formula) != 1:
        raise ValueError("Invalid requirement formula")
    op, children = next(iter(formula.items()))
    if op not in {"all", "any"} or not isinstance(children, list) or not children:
        raise ValueError("Invalid requirement formula")
    return combine([evaluate_formula(child, values) for child in children], op)


JUDGMENT_SCHEMA = "judgment-grounding-v2"


def validate_requirements(requirements):
    if not requirements or not isinstance(requirements, list):
        raise ValueError("No requirements")
    ids = [r.get("id") for r in requirements if isinstance(r, dict)]
    if len(ids) != len(requirements) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid/duplicate requirement IDs")
    for r in requirements:
        if r.get("kind") not in {"TEXT", "COMPLETENESS", "SCIENTIFIC"}:
            raise ValueError("Invalid requirement kind")
        if not isinstance(r.get("necessary"), bool) or not isinstance(r.get("text"), str) or not r["text"].strip():
            raise ValueError("Invalid requirement definition")
        if not isinstance(r.get("evidence_ids", []), list) or any(not isinstance(e, str) for e in r.get("evidence_ids", [])):
            raise ValueError("Invalid evidence allowlist")
        scope = r.get("scope", "GLOBAL")
        if scope not in {"GLOBAL", "ROUTE"}:
            raise ValueError("Requirement scope must be GLOBAL or ROUTE")
        if scope == "ROUTE" and (not isinstance(r.get("route_id"), str) or not r["route_id"]):
            raise ValueError("Route requirement lacks route identity")
    return set(ids)


def admissibility_formula(requirements, requested=None):
    """Global hard conditions AND one complete route; caller OR cannot bypass them."""
    validate_requirements(requirements)
    globals_, routes = [], {}
    for r in requirements:
        if not r["necessary"]:
            continue
        if r.get("scope", "GLOBAL") == "GLOBAL":
            globals_.append(r["id"])
        else:
            routes.setdefault(r["route_id"], []).append(r["id"])
    clauses = list(globals_)
    if routes:
        clauses.append({"any": [{"all": ids} for ids in routes.values()]})
    if not clauses:
        raise ValueError("At least one necessary condition is required")
    mandatory = {"all": clauses}
    if requested is None or requested == mandatory:
        return mandatory
    # Validate every reference; preserve requested logic as an additional restriction.
    evaluate_formula(requested, {r["id"]: "SATISFIED" for r in requirements})
    return {"all": [mandatory, deepcopy(requested)]}


def adjudicate(value, requirements, protocol, cards, formula=None, *, evidence_guard=True,
               quotation_policy="strict"):
    """Preserve proposals; diagnostic quotation gaps cannot authorize decisions.

    Diagnostic mode retains invalid protocol quotations per requirement without
    transferring them to evidence cards or guessing replacement source spans.
    Schema, quotation types and evidence/offset integrity stay strict. The
    quotation guard also applies when evidence_guard is disabled for ablation.
    """
    if quotation_policy not in {"strict", "diagnostic"}:
        raise ValueError("Unknown requirement quotation policy")
    expected = validate_requirements(requirements)
    strict = isinstance(value, dict) and value.get("schema_version") == JUDGMENT_SCHEMA
    roots = {"requirements", "limitations"} | ({"schema_version"} if strict else set())
    if not isinstance(value, dict) or set(value) != roots:
        raise ValueError("Wrong/unknown judgment schema; explicit migration required")
    records = value["requirements"]
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("Wrong requirement count")
    if any(not isinstance(r, dict) for r in records) or {r.get("id") for r in records} != expected:
        raise ValueError("Requirement IDs differ")
    if not isinstance(value["limitations"], str):
        raise ValueError("Invalid limitations")
    by_id = {r["id"]: r for r in requirements}
    card_audits = validate_cards(cards)
    card_ids = set(card_audits)
    results = []
    for r in records:
        fields = {"id", "status", "basis", "evidence_ids", "quotes", "reason"}
        if strict:
            fields.add("evidence_checks")
        if set(r) != fields or r["status"] not in STATES or r["basis"] not in BASES:
            raise ValueError("Wrong requirement record schema")
        if not isinstance(r["reason"], str) or not r["reason"].strip():
            raise ValueError("Missing rationale")
        if not isinstance(r["evidence_ids"], list) or any(not isinstance(e, str) or e not in card_ids for e in r["evidence_ids"]):
            raise ValueError("Unknown source identifier")
        if len(r["evidence_ids"]) != len(set(r["evidence_ids"])):
            raise ValueError("Duplicate evidence citation")
        if not isinstance(r["quotes"], list):
            raise ValueError("Invalid quotes")
        spans, quote_audits, quotation_guards = [], [], []
        for quote in r["quotes"]:
            if not isinstance(quote, str):
                raise ValueError("Protocol quotations must be text")
            try:
                anchor = anchors(protocol, quote)
            except ValueError:
                if quotation_policy == "strict":
                    raise
                quotation_guards.append("INVALID_PROTOCOL_QUOTATION")
                quote_audits.append({"quote": quote, "status": "INVALID_PROTOCOL_QUOTATION",
                                     "source_span": None, "occurrences": [],
                                     "reason": "EMPTY_QUOTATION" if not quote.strip()
                                               else "QUOTATION_ABSENT_FROM_UNCHANGED_PROTOCOL"})
            else:
                spans.append(anchor)
                occurrence = anchor["occurrences"][0] if len(anchor["occurrences"]) == 1 else None
                quote_audits.append({"quote": quote, "status": "ANCHORED",
                                     "source_span": ({"start": occurrence["start"],
                                                      "end": occurrence["end"], "quote": quote}
                                                     if occurrence else None),
                                     "occurrences": deepcopy(anchor["occurrences"]),
                                     "ambiguous_location": anchor["ambiguous_location"]})
        if r["status"] in {"SATISFIED", "VIOLATED"} and not spans:
            if quotation_policy == "strict":
                raise ValueError("Decisive judgment requires a protocol anchor")
            quotation_guards.append("MISSING_DECISIVE_PROTOCOL_ANCHOR")
        req, guards, effective = by_id[r["id"]], list(quotation_guards), r["status"]
        evidence_audit = None
        if r["basis"] == "MISSING" and r["status"] in {"SATISFIED", "VIOLATED"}:
            guards.append("MISSING_BASIS")
            effective = "UNDER_SPECIFIED"
        invalid_topic = set(r["evidence_ids"]) - set(req.get("evidence_ids", []))
        if invalid_topic:
            guards.append("SOURCE_OUTSIDE_REQUIREMENT_SCOPE")
        if r["basis"] == "SUPPLIED_EVIDENCE" and not r["evidence_ids"]:
            guards.append("UNBOUND_EVIDENCE_BASIS")
        if req["kind"] == "SCIENTIFIC" and r["status"] in {"SATISFIED", "VIOLATED"}:
            applicable = set(r["evidence_ids"]) & set(req.get("evidence_ids", []))
            if r["basis"] != "SUPPLIED_EVIDENCE" or not applicable:
                guards.append("SCIENTIFIC_DECISION_WITHOUT_APPLICABLE_SOURCE")
            if not strict:
                guards.append("LEGACY_JUDGMENT_STRUCTURE_ONLY")
            else:
                evidence_audit = check_scientific_support(r, req, cards, protocol)
                guards.extend(evidence_audit["guards"])
            operations = req.get("joint_operations", [])
            if not isinstance(operations,list) or any(not isinstance(op,str) or not op for op in operations):
                raise ValueError("Declared joint method identities must be strings")
            if len(set(operations)) > 1:
                guards.append("MULTI_METHOD_COMBINATION_OUT_OF_SCOPE")
            if operations and (not isinstance(req.get("applicability"), dict)
                               or req["applicability"].get("operations") != operations):
                guards.append("JOINT_SERIAL_OPERATIONS_SUPPORT_UNBOUND")
        if evidence_guard and guards and effective not in {"UNDER_SPECIFIED", "UNRESOLVED"}:
            effective = "UNRESOLVED"
        if not evidence_guard:
            effective = r["status"]
        if quotation_guards and effective in {"SATISFIED", "VIOLATED"}:
            effective = "UNRESOLVED"
        results.append({**deepcopy(r), "proposed_status": r["status"],
                        "effective_status": effective, "guards": sorted(set(guards)), "anchors": spans,
                        "evidence_audit": evidence_audit,
                        **({"protocol_quote_audits": quote_audits} if quotation_policy == "diagnostic" else {})})
    proposed = {r["id"]: r["proposed_status"] for r in results}
    effective = {r["id"]: r["effective_status"] for r in results}
    safe_formula = admissibility_formula(requirements, formula)
    return {"schema_version": JUDGMENT_SCHEMA if strict else "legacy-v1",
            "requirements": results, "formula": safe_formula, "requested_formula": deepcopy(formula),
            "formula_policy": "GLOBAL_NECESSARY_AND_COMPLETE_ROUTE_OR; requested formula can only add restrictions",
            "proposed_overall": evaluate_formula(safe_formula, proposed),
            "requested_overall": evaluate_formula(formula, proposed) if formula is not None else None,
            "overall": evaluate_formula(safe_formula, effective),
            "technical_status": "VALID", "limitations": value["limitations"],
            "evidence_guard": evidence_guard, "source_audits": card_audits,
            "decision_scope": "SOURCE_GROUNDED_MODEL_PROPOSAL" if strict else "LEGACY_STRUCTURE_ONLY",
            "scientific_validation": "PENDING_INDEPENDENT_REFERENCE",
            "expert_validation_owner": "USER",
            "citation_validation": "Identity, snapshot hash/span, relation proposal and declared applicability; truth not certified",
            **({"quotation_policy": quotation_policy} if quotation_policy == "diagnostic" else {})}


def validate_extraction(value, protocol, *, field_scope_policy="strict"):
    """Validate integrity; diagnostic scope gaps remain ineligible field audits."""
    strict = isinstance(value, dict) and value.get("schema_version") == EXTRACTION_SCHEMA
    roots = {"labels", "steps", "ri", "limitations"} | ({"schema_version", "branches"} if strict else set())
    if not isinstance(value, dict) or set(value) != roots:
        raise ValueError("Wrong/unknown extraction schema; explicit migration required")
    if not isinstance(value["limitations"], str):
        raise ValueError("Invalid extraction limitations")
    schemas = {
        "labels": {"id", "branch", "target", "probe", "fluorophore", "channel", "quote"},
        "steps": {"id", "branch", "phase", "operation", "duration_text", "quote"},
        "ri": {"branch", "solution", "value_text", "quote"},
    }
    output = deepcopy(value)
    for key, base_fields in schemas.items():
        fields = base_fields | ({"field_support", "assertion"} if strict else set())
        rows = output[key]
        if not isinstance(rows, list):
            raise ValueError("Extraction must use arrays")
        ids = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError("Wrong extraction record schema: " + key)
            if any(row[k] is not None and not isinstance(row[k], str) for k in base_fields):
                raise ValueError("Extraction factual fields must be text or explicit null")
            if not row["branch"]:
                raise ValueError("Missing branch identity")
            if "id" in base_fields:
                if not row["id"]:
                    raise ValueError("Empty extraction ID")
                ids.append(row["id"])
            row["anchors"] = anchors(protocol, row["quote"])
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate extraction IDs")
    audit = audit_extraction(value, protocol, field_scope_policy=field_scope_policy)
    if strict and field_scope_policy == "diagnostic":
        output["branches"] = deepcopy(audit["validated"]["branches"])
    output["field_audit"] = {k: v for k, v in audit.items() if k != "validated"}
    output["validation_scope"] = audit["scope"]
    output["scoring_eligible"] = audit["scoring_eligible"]
    return output


def finite_number(value, *, positive=False):
    return (type(value) in {int, float} and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def duration_bounds(steps):
    """Elapsed-time bounds from a fully specified dependency DAG, in hours.

No topology is inferred. Unknown duration/topology stays unknown. Parallel
steps contribute the longest path, repetitions multiply explicit bounds.
"""
    if not steps:
        return {"status": "UNDER_SPECIFIED", "min_h": None, "max_h": None}
    by_id = {s["id"]: s for s in steps}
    if len(by_id) != len(steps):
        raise ValueError("Duplicate step IDs")
    visiting, solved = set(), {}

    def visit(sid):
        if sid in visiting:
            raise ValueError("Cyclic duration dependencies")
        if sid not in by_id:
            raise ValueError("Unknown duration dependency")
        if sid in solved:
            return solved[sid]
        visiting.add(sid)
        s = by_id[sid]
        deps = s.get("after")
        if not isinstance(deps, list):
            result = None
        else:
            previous = [visit(d) for d in deps]
            low, high, repeat = s.get("min_h"), s.get("max_h"), s.get("repeat", 1)
            if (not finite_number(low) or not finite_number(high) or low > high
                    or type(repeat) is not int or repeat < 1 or any(p is None for p in previous)):
                result = None
            else:
                result = (max((p[0] for p in previous), default=0) + low * repeat,
                          max((p[1] for p in previous), default=0) + high * repeat)
        visiting.remove(sid)
        solved[sid] = result
        return result

    values = [visit(sid) for sid in by_id]
    if any(v is None for v in values):
        return {"status": "UNDER_SPECIFIED", "min_h": None, "max_h": None}
    return {"status": "EXPLICIT", "min_h": max(v[0] for v in values),
            "max_h": max(v[1] for v in values)}


def time_diagnostic(actual, rows, method, tier, scope):
    """Versioned symmetric tau=0.20 diagnostic; never a success probability."""
    detail = {"policy": "symmetric-median-0.20-explicit-tier-and-scope-v1", "score": None}
    matches = [r for r in rows if r.get("method") == method and r.get("tier_code") == tier
               and r.get("time_scope") == scope and r.get("supported") is True
               and not str(r.get("review_status", "")).startswith("removed")]
    if len(matches) != 1:
        return {**detail, "status": "UNRESOLVED", "reason": "Missing or ambiguous exact tier/scope"}
    row = matches[0]
    low, high, median = (row.get(k) for k in ("clearing_time_min_h", "clearing_time_max_h", "clearing_time_median_h"))
    if not all(finite_number(v) for v in (low, high, median)) or not low <= median <= high or median <= 0:
        return {**detail, "status": "UNRESOLVED", "reason": "Invalid reference interval"}
    if not finite_number(actual, positive=True):
        return {**detail, "status": "UNDER_SPECIFIED", "reason": "No explicit positive duration"}
    delta, tau = max(low - actual, actual - high, 0), 0.20 * median
    return {**detail, "status": "COMPUTED_DIAGNOSTIC", "score": 3 * math.exp(-0.5 * (delta / tau) ** 2),
            "tau_h": tau, "delta_h": delta, "probability": False}


def ri_diagnostic(solution, actual_ri, reference_ri):
    if not solution or not finite_number(actual_ri, positive=True):
        return {"status": "UNDER_SPECIFIED", "difference": None}
    if not finite_number(reference_ri, positive=True):
        return {"status": "UNRESOLVED", "difference": None}
    return {"status": "COMPUTED_DIAGNOSTIC", "difference": abs(actual_ri - reference_ri),
            "scientific_compatibility": "NOT_ESTABLISHED_BY_RI_ALONE"}

