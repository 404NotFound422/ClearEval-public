"""Offline OEQ extraction-fidelity comparison and numerical score impact.

This module checks source binding and extraction agreement.  It does not call a
model/provider, establish scientific accuracy, or populate a knowledge base.
"""
from copy import deepcopy
from decimal import Decimal
import math

from evaluator_integrity import JudgeFormatError, _check_span, _transform, parse_judge_object
from evaluation_contract import json_hash
from experiments.construct_validity.fidelity import CONDITION, NEGATION, audit_facts, text_hash

INVENTORY_SCHEMA = "oeq-fidelity-inventory-v1"
IMPACT_SCHEMA = "oeq-extraction-score-impact-v1"
_ROLES = {"CANDIDATE_EXTRACTION", "MANUAL_REFERENCE"}
_STATES = {"REPORTED", "EXPLICIT_NULL"}
_VALUE_KINDS = {"ENTITY", "NUMBER", "TEXT"}
_FACT_REQUIRED = {"path", "state", "value", "value_kind", "support"}
_FACT_OPTIONAL = {"unit", "basis", "polarity", "scope"}
_ROOT_FIELDS = {"schema_version", "original_text_sha256", "field_scope", "provenance", "facts"}
_PROVENANCE_FIELDS = {"record_id", "role", "independence", "assistance"}
_BINDING_FIELDS = {"question", "knowledge_base", "formulas", "context"}
_SCORE_RECORD_FIELDS = {"status", "scorer_id", "scorer_revision", "binding_sha256",
                        "extraction_sha256", "inventory_sha256", "scores"}


def parse_candidate_json(candidate_text):
    """Parse one strict JSON object without repairing malformed output."""
    try:
        value = parse_judge_object(candidate_text)
    except (JudgeFormatError, TypeError, ValueError) as exc:
        return {"status": "PARSE_FAILURE", "value": None,
                "error": {"type": type(exc).__name__, "message": str(exc)}}
    return {"status": "PARSED", "value": value, "error": None}


def _same_value(left, right):
    if (type(left) in {int, float} and type(right) in {int, float}
            and not isinstance(left, bool) and not isinstance(right, bool)):
        return math.isfinite(left) and math.isfinite(right) and Decimal(str(left)) == Decimal(str(right))
    return type(left) is type(right) and left == right


def _validate_inventory_schema(protocol, inventory, expected_role):
    if not isinstance(protocol, str) or not isinstance(inventory, dict):
        raise ValueError("Protocol text and inventory object required")
    if set(inventory) != _ROOT_FIELDS or inventory.get("schema_version") != INVENTORY_SCHEMA:
        raise ValueError("Wrong/unknown inventory schema")
    if inventory["original_text_sha256"] != text_hash(protocol):
        raise ValueError("Inventory is not bound to the unchanged original text")
    scope = inventory["field_scope"]
    if (not isinstance(scope, list) or any(not isinstance(p, str) or not p.startswith("/") for p in scope)
            or len(scope) != len(set(scope))):
        raise ValueError("field_scope must contain unique JSON-pointer paths")
    provenance = inventory["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_FIELDS:
        raise ValueError("Wrong inventory provenance schema")
    if (provenance["role"] not in _ROLES or provenance["role"] != expected_role
            or not isinstance(provenance["record_id"], str) or not provenance["record_id"]
            or provenance["independence"] not in {"INDEPENDENT", "ASSISTED", "NOT_APPLICABLE"}
            or not isinstance(provenance["assistance"], list)
            or any(not isinstance(item, str) or not item for item in provenance["assistance"])):
        raise ValueError("Invalid inventory provenance")
    facts = inventory["facts"]
    if not isinstance(facts, list):
        raise ValueError("Inventory facts must be an array")
    paths = []
    for fact in facts:
        if not isinstance(fact, dict) or not _FACT_REQUIRED.issubset(fact) or set(fact) - (_FACT_REQUIRED | _FACT_OPTIONAL):
            raise ValueError("Wrong inventory fact schema")
        path = fact["path"]
        if not isinstance(path, str) or path not in scope:
            raise ValueError("Fact path must be declared in field_scope")
        paths.append(path)
        if fact["state"] not in _STATES or fact["value_kind"] not in _VALUE_KINDS:
            raise ValueError("Invalid fact state or value kind")
        if fact["state"] == "EXPLICIT_NULL":
            if fact["value"] is not None or fact["support"] != {"kind": "MISSING"}:
                raise ValueError("Explicit null requires value=null and typed MISSING support")
        else:
            value = fact["value"]
            if fact["value_kind"] == "NUMBER":
                if isinstance(value, bool) or type(value) not in {int, float} or not math.isfinite(value):
                    raise ValueError("NUMBER fact needs a finite JSON number")
            elif not isinstance(value, str) or not value:
                raise ValueError("ENTITY/TEXT fact needs nonempty text")
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate inventory fact path")


def _audit_reported_fact(protocol, fact):
    support = fact["support"]
    if (not isinstance(support, dict)
            or set(support) != {"kind", "spans", "context_span", "raw_value", "transform"}
            or support.get("kind") != "EXPLICIT"
            or not isinstance(support.get("spans"), list) or len(support["spans"]) != 1
            or not isinstance(support.get("raw_value"), str) or not support["raw_value"]):
        raise ValueError("Reported fact requires one explicit flat-support span and transform")
    span, context = support["spans"][0], support["context_span"]
    _check_span(span, protocol)
    _check_span(context, protocol)
    if not context["start"] <= span["start"] < span["end"] <= context["end"]:
        raise ValueError("Fact span lies outside its declared context")
    if span["quote"] != support["raw_value"]:
        raise ValueError("raw_value differs from the original source span")
    try:
        transformed = _transform(support["raw_value"], support["transform"], fact["path"])
    except JudgeFormatError as exc:
        raise ValueError(str(exc)) from exc
    if not _same_value(transformed, fact["value"]):
        raise ValueError("Inventory value differs from its declared source transform")
    if support["transform"] == "TIME_TO_HOURS" and fact.get("unit") not in {None, "h"}:
        raise ValueError(f"{fact['path']}.unit must be h after TIME_TO_HOURS")

    # Reuse the generic typed audit for entity boundaries, numeric/unit pairing,
    # assertion polarity, basis and explicit lexical scope when no normalization
    # separates the stored value from the literal source value.
    generic = {"field": fact["path"], "value": fact["value"], "origin": "EXPLICIT",
               "start": span["start"], "end": span["end"], "quote": span["quote"]}
    for name in ("unit", "basis", "polarity", "scope"):
        if fact.get(name) is not None:
            generic[name] = fact[name]
    audit = audit_facts([generic], protocol)
    if support["transform"] != "IDENTITY":
        # The declared transform has already bound the normalized value. Generic
        # literal matching sees that normalized value rather than the raw span.
        ignored = {fact["path"]}
        if support["transform"] == "TIME_TO_HOURS":
            ignored.add(fact["path"] + ".unit")
        audit["mismatch_fields"] = [item for item in audit["mismatch_fields"] if item not in ignored]
        if audit["mismatch_fields"]:
            audit["status"] = "UNFAITHFUL"
        elif audit["unresolved_fields"]:
            audit["status"] = "UNRESOLVED"
        else:
            audit["status"] = "FAITHFUL"
    # A qualifying heading on the immediately preceding nonempty line can
    # govern this step while the generic line-local context misses it. The
    # declared support must already include that heading. Do not scan later
    # facts or infer scope from unrelated warnings elsewhere in the answer.
    local_context = audit["audits"][0].get("assertion_context", {})
    local_start = local_context.get("start", context["start"])
    prefix = protocol[context["start"]:local_start] if context["start"] < local_start else ""
    preceding_lines = [line for line in prefix.splitlines() if line.strip()]
    heading = preceding_lines[-1].strip() if preceding_lines else ""
    if heading.endswith((":", "：")) and (CONDITION.search(heading) or NEGATION.search(heading)):
        polarity_path = fact["path"] + ".polarity"
        # The local affirmative inference cannot decide an inherited heading's
        # scope. Keep independent value/unit mismatches and defer only polarity.
        local_quote = local_context.get("quote", "")
        defer_local_affirmative = not (CONDITION.search(local_quote) or NEGATION.search(local_quote))
        if defer_local_affirmative:
            audit["mismatch_fields"] = [item for item in audit["mismatch_fields"] if item != polarity_path]
        scope_path = fact["path"] + ".context_scope"
        audit["unresolved_fields"] = sorted(set(audit["unresolved_fields"] + [scope_path]))
        for row in audit["audits"]:
            if defer_local_affirmative:
                row["issues"] = [item for item in row.get("issues", []) if item != polarity_path]
            row["unresolved"] = sorted(set(row.get("unresolved", []) + [scope_path]))
        audit["inherited_qualifier_diagnostic"] = {
            "heading": heading, "status": "QUALIFIER_SCOPE_UNRESOLVED",
            "policy": "SUPPLIED_CONTEXT_IMMEDIATE_COLON_HEADING_ONLY"}
        audit["status"] = "UNFAITHFUL" if audit["mismatch_fields"] else "UNRESOLVED"
    if audit["status"] == "UNFAITHFUL":
        raise ValueError("; ".join(audit["mismatch_fields"]))
    return {"status": audit["status"], "generic_audit": audit,
            "span": deepcopy(span), "context_span": deepcopy(context),
            "transform": support["transform"]}


def audit_inventory(protocol, inventory, *, role):
    """Audit an explicit candidate or manual inventory against original text."""
    _validate_inventory_schema(protocol, inventory, role)
    fact_audits, issues, unresolved = [], [], []
    for fact in inventory["facts"]:
        if fact["state"] == "EXPLICIT_NULL":
            fact_audits.append({"path": fact["path"], "state": "EXPLICIT_NULL",
                                "status": "DECLARED_MISSING",
                                "missingness": "ANNOTATOR_DECLARATION_NOT_COMPLETENESS_PROOF",
                                "issues": []})
            continue
        try:
            detail = _audit_reported_fact(protocol, fact)
            fact_issues = []
            if detail["status"] == "UNRESOLVED":
                unresolved_item = {"path": fact["path"], "code": "FIELD_AUDIT_UNRESOLVED",
                                   "detail": deepcopy(detail["generic_audit"].get("unresolved_fields", []))}
                unresolved.append(unresolved_item)
                fact_issues.append(unresolved_item)
            fact_audits.append({"path": fact["path"], "state": "REPORTED",
                                "status": detail["status"], "issues": fact_issues, **detail})
        except (ValueError, TypeError, KeyError) as exc:
            issue = {"path": fact["path"], "code": "SOURCE_BINDING_INVALID", "detail": str(exc)}
            issues.append(issue)
            fact_audits.append({"path": fact["path"], "state": "REPORTED",
                                "status": "UNFAITHFUL", "issues": [issue]})
    provenance = inventory["provenance"]
    independent_manual = (role == "MANUAL_REFERENCE"
                          and provenance["independence"] == "INDEPENDENT"
                          and provenance["assistance"] == [])
    factually_resolved = not issues and not unresolved
    status = "UNFAITHFUL" if issues else ("UNRESOLVED" if unresolved else "FAITHFUL")
    reference_eligible = independent_manual and factually_resolved
    if role != "MANUAL_REFERENCE":
        reference_status = "NOT_APPLICABLE"
    elif provenance["independence"] == "ASSISTED" or provenance["assistance"]:
        reference_status = "ASSISTED_REFERENCE"
    elif independent_manual and issues:
        reference_status = "INDEPENDENT_REFERENCE_INVALID"
    elif independent_manual and unresolved:
        reference_status = "INDEPENDENT_REFERENCE_UNRESOLVED"
    elif reference_eligible:
        reference_status = "INDEPENDENT_REFERENCE"
    else:
        reference_status = "INVALID_REFERENCE"
    return {"schema_version": INVENTORY_SCHEMA, "status": status,
            "protocol_sha256": text_hash(protocol), "role": role,
            "field_scope": deepcopy(inventory["field_scope"]),
            "field_states": {path: (next((f["state"] for f in inventory["facts"] if f["path"] == path),
                                          "NOT_REPORTED")) for path in inventory["field_scope"]},
            "facts": deepcopy(inventory["facts"]), "fact_audits": fact_audits,
            "inventory_sha256": json_hash(inventory),
            "issues": issues, "unresolved": unresolved, "provenance": deepcopy(provenance),
            "annotation_independent": independent_manual,
            "factually_resolved": factually_resolved,
            "reference_eligible": reference_eligible,
            "reference_status": reference_status,
            "scientific_accuracy": None,
            "scope": "SOURCE_BINDING_AND_EXTRACTION_INVENTORY_ONLY"}


def _invalid_audit(role, status, error):
    return {"status": status, "role": role, "reference_eligible": False,
            "reference_status": "INVALID_REFERENCE" if role == "MANUAL_REFERENCE" else "NOT_APPLICABLE",
            "annotation_independent": False, "factually_resolved": False,
            "field_scope": [], "field_states": {}, "facts": [], "fact_audits": [],
            "inventory_sha256": None,
            "issues": [{"code": status, "detail": error}], "unresolved": [],
            "scientific_accuracy": None}


def _load_candidate(candidate):
    if isinstance(candidate, str):
        parsed = parse_candidate_json(candidate)
        return parsed["value"], parsed
    if isinstance(candidate, dict):
        return candidate, {"status": "PARSED_OBJECT", "value": deepcopy(candidate), "error": None}
    return None, {"status": "PARSE_FAILURE", "value": None,
                  "error": {"type": "TypeError", "message": "Candidate inventory must be JSON text or an object"}}


def _fact_map(audit):
    return {fact["path"]: fact for fact in audit.get("facts", [])}


def _fact_issue_paths(audit):
    return {issue.get("path") for issue in audit.get("issues", [])}


def _fact_unresolved_paths(audit):
    return {issue.get("path") for issue in audit.get("unresolved", [])}


def compare_inventories(protocol, candidate_inventory, manual_inventory):
    """Compare extraction inventories; agreement is never scientific accuracy."""
    candidate_value, parse = _load_candidate(candidate_inventory)
    if parse["status"] == "PARSE_FAILURE":
        candidate_audit = _invalid_audit("CANDIDATE_EXTRACTION", "PARSE_FAILURE", parse["error"]["message"])
    else:
        try:
            candidate_audit = audit_inventory(protocol, candidate_value, role="CANDIDATE_EXTRACTION")
        except (ValueError, TypeError, KeyError) as exc:
            candidate_audit = _invalid_audit("CANDIDATE_EXTRACTION", "INVALID_SCHEMA", str(exc))
    if manual_inventory is None:
        manual_audit = _invalid_audit("MANUAL_REFERENCE", "ABSENT", "No manual reference supplied")
    else:
        try:
            manual_audit = audit_inventory(protocol, manual_inventory, role="MANUAL_REFERENCE")
        except (ValueError, TypeError, KeyError) as exc:
            manual_audit = _invalid_audit("MANUAL_REFERENCE", "INVALID_SCHEMA", str(exc))

    base = {"schema_version": INVENTORY_SCHEMA, "protocol_sha256": text_hash(protocol),
            "candidate_parse": parse, "candidate_audit": candidate_audit,
            "manual_audit": manual_audit, "scientific_accuracy": None,
            "interpretation": "EXTRACTION_AGREEMENT_WITH_INDEPENDENT_MANUAL_INVENTORY"}
    if not manual_audit.get("reference_eligible") or candidate_audit["status"] in {"PARSE_FAILURE", "INVALID_SCHEMA"}:
        return {**base, "status": "UNAVAILABLE", "fields": [], "extraction_agreement": None,
                "reason": "Independent valid manual reference and parseable candidate are required"}

    candidate_facts, manual_facts = _fact_map(candidate_audit), _fact_map(manual_audit)
    candidate_bad, manual_bad = _fact_issue_paths(candidate_audit), _fact_issue_paths(manual_audit)
    candidate_unresolved = _fact_unresolved_paths(candidate_audit)
    fields = []
    for path in manual_audit["field_scope"]:
        candidate = candidate_facts.get(path)
        manual = manual_facts.get(path)
        cstate = candidate["state"] if candidate else "NOT_REPORTED"
        mstate = manual["state"] if manual else "NOT_REPORTED"
        reasons = []
        if path in manual_bad:
            outcome, reasons = "UNAVAILABLE", ["MANUAL_SOURCE_BINDING_INVALID"]
        elif mstate == "REPORTED" and cstate in {"NOT_REPORTED", "EXPLICIT_NULL"}:
            outcome = "OMISSION"
        elif mstate == "EXPLICIT_NULL" and cstate == "REPORTED":
            outcome = "EXTRA"
            if path in candidate_bad:
                reasons = ["CANDIDATE_SOURCE_BINDING_INVALID"]
        elif path in candidate_bad:
            outcome, reasons = "MISMATCH", ["CANDIDATE_SOURCE_BINDING_INVALID"]
        elif path in candidate_unresolved:
            outcome, reasons = "UNAVAILABLE", ["CANDIDATE_FIELD_UNRESOLVED"]
        elif mstate in {"EXPLICIT_NULL", "NOT_REPORTED"}:
            outcome = "UNAVAILABLE"
            reasons = ["MANUAL_VALUE_UNKNOWN"]
        elif cstate != "REPORTED":
            outcome = "OMISSION"
        else:
            qualifiers = ("value_kind", "unit", "basis", "polarity", "scope")
            equal = _same_value(candidate["value"], manual["value"])
            equal = equal and all(candidate.get(key) == manual.get(key) for key in qualifiers)
            outcome = "MATCH" if equal else "MISMATCH"
        fields.append({"path": path, "candidate_state": cstate, "manual_state": mstate,
                       "candidate_value": deepcopy(candidate.get("value")) if candidate else None,
                       "manual_value": deepcopy(manual.get("value")) if manual else None,
                       "outcome": outcome, "reasons": reasons})
    for path in candidate_audit["field_scope"]:
        if path not in set(manual_audit["field_scope"]):
            candidate = candidate_facts.get(path)
            fields.append({"path": path,
                           "candidate_state": candidate["state"] if candidate else "NOT_REPORTED",
                           "manual_state": "OUT_OF_SCOPE",
                           "candidate_value": deepcopy(candidate.get("value")) if candidate else None,
                           "manual_value": None, "outcome": "UNAVAILABLE",
                           "reasons": ["OUTSIDE_MANUAL_FIELD_SCOPE"]})
    counts = {name: sum(row["outcome"] == name for row in fields)
              for name in ("MATCH", "MISMATCH", "OMISSION", "EXTRA", "UNAVAILABLE")}
    agreement = ("DISAGREEMENT" if any(counts[key] for key in ("MISMATCH", "OMISSION", "EXTRA")) else
                 "PARTIAL_UNAVAILABLE" if counts["UNAVAILABLE"] else "AGREEMENT")
    return {**base, "status": "AVAILABLE", "fields": fields,
            "extraction_agreement": agreement, "counts": counts, "reason": None}


def _pointer(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def _flat_leaves(value, path=""):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            child_path = path + "/" + _pointer(key)
            if path == "/marker_dict":
                yield child_path + "/@key", key
            yield from _flat_leaves(child, child_path)
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from _flat_leaves(child, path + "/" + str(index))
    else:
        yield path, value


def _semantic_extraction(extraction):
    if not isinstance(extraction, dict):
        raise ValueError("Flat extraction must be an object")
    ignored = {"schema_version", "field_support", "reasoning"}
    return {key: deepcopy(value) for key, value in extraction.items() if key not in ignored}


def _extraction_values(extraction):
    return dict(_flat_leaves(_semantic_extraction(extraction)))


def _check_extraction_consistency(audit, extraction):
    values, facts = _extraction_values(extraction), _fact_map(audit)
    issues = []
    for path in audit.get("field_scope", []):
        fact = facts.get(path)
        if fact is None:
            if path in values:
                issues.append({"path": path, "code": "INVENTORY_NOT_REPORTED_BUT_EXTRACTION_HAS_VALUE"})
        elif path not in values or not _same_value(fact["value"], values[path]):
            issues.append({"path": path, "code": "INVENTORY_EXTRACTION_VALUE_MISMATCH",
                           "inventory_value": deepcopy(fact["value"]),
                           "extraction_value": deepcopy(values.get(path))})
    return {"status": "CONSISTENT" if not issues else "INCONSISTENT", "issues": issues}


def _audit_extraction_changes(comparison, candidate_extraction, manual_extraction):
    candidate_values = _extraction_values(candidate_extraction)
    manual_values = _extraction_values(manual_extraction)
    compared = {row["path"]: row for row in comparison.get("fields", [])}
    changes, issues = [], []
    for path in sorted(set(candidate_values) | set(manual_values)):
        candidate_present, manual_present = path in candidate_values, path in manual_values
        candidate_value, manual_value = candidate_values.get(path), manual_values.get(path)
        if candidate_present and manual_present and _same_value(candidate_value, manual_value):
            continue
        comparison_row = compared.get(path)
        attributable = (comparison_row is not None
                        and comparison_row.get("outcome") in {"MISMATCH", "OMISSION", "EXTRA"})
        record = {"path": path,
                  "candidate_state": "PRESENT" if candidate_present else "ABSENT",
                  "manual_state": "PRESENT" if manual_present else "ABSENT",
                  "candidate_value": deepcopy(candidate_value),
                  "manual_value": deepcopy(manual_value),
                  "inventory_outcome": comparison_row.get("outcome") if comparison_row else None,
                  "status": "ATTRIBUTED_TO_INVENTORY_COMPARISON" if attributable else "UNBOUND"}
        changes.append(record)
        if not attributable:
            issues.append({"path": path, "code": "UNBOUND_SCORE_INPUT_CHANGE",
                           "detail": "Changed flat-extraction leaf lacks an available inventory comparison"})
    return {"status": "ATTRIBUTED" if not issues else "UNATTRIBUTED_CHANGES",
            "changes": changes, "issues": issues,
            "candidate_semantic_sha256": json_hash(_semantic_extraction(candidate_extraction)),
            "manual_semantic_sha256": json_hash(_semantic_extraction(manual_extraction))}


def _flatten_scores(value, path=""):
    result = {}
    if isinstance(value, dict):
        if "score" in value:
            score = value["score"]
            if score is not None and (isinstance(score, bool) or type(score) not in {int, float} or not math.isfinite(score)):
                raise ValueError("Score leaves must be finite numbers or explicit null")
            result[path or "/score"] = score
        else:
            for key, child in value.items():
                result.update(_flatten_scores(child, path + "/" + _pointer(key)))
    elif value is None or (type(value) in {int, float} and not isinstance(value, bool)):
        if value is not None and not math.isfinite(value):
            raise ValueError("Score leaves must be finite")
        result[path or "/score"] = value
    return result


def _unavailable_impact(binding, reason, **extra):
    digest = json_hash(binding) if isinstance(binding, dict) else None
    return {"schema_version": IMPACT_SCHEMA, "status": "UNAVAILABLE",
            "binding_sha256": digest, "score_differences": {}, "reason": reason,
            "scientific_accuracy": None,
            "interpretation": "HYPOTHETICAL_EXTRACTION_IMPACT_WITH_OTHER_SCORE_INPUTS_FROZEN", **extra}


def _validate_binding(binding):
    if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
        raise ValueError("Binding must contain exactly question, knowledge_base, formulas and context")
    return json_hash(binding)


def _validate_score_record(record, binding_sha256, extraction_sha256, inventory_sha256):
    if not isinstance(record, dict) or set(record) != _SCORE_RECORD_FIELDS:
        raise ValueError("Wrong approved score record schema")
    if record["status"] != "APPROVED_FROZEN" or record["binding_sha256"] != binding_sha256:
        raise ValueError("Score record is not approved for this exact question/KB/formula/context binding")
    if record["extraction_sha256"] != extraction_sha256:
        raise ValueError("Score record is not bound to the supplied semantic flat extraction")
    if record["inventory_sha256"] != inventory_sha256:
        raise ValueError("Score record is not bound to the audited extraction inventory")
    if not isinstance(record["scorer_id"], str) or not record["scorer_id"] or not isinstance(record["scorer_revision"], str) or not record["scorer_revision"]:
        raise ValueError("Score record needs scorer identity and revision")
    return deepcopy(record["scores"])


def measure_score_impact(comparison, binding, *, scorer=None, scorer_id=None, scorer_revision=None,
                         candidate_extraction=None, manual_extraction=None,
                         candidate_score_record=None, manual_score_record=None,
                         frozen_score_paths=()):
    """Re-score only fully inventoried flat-extraction changes under one binding."""
    try:
        binding_sha256 = _validate_binding(binding)
    except (ValueError, TypeError) as exc:
        return _unavailable_impact(binding, str(exc))
    if not isinstance(comparison, dict) or comparison.get("status") != "AVAILABLE" or not comparison.get("manual_audit", {}).get("reference_eligible"):
        return _unavailable_impact(binding, "Available comparison with resolved independent manual reference required")
    if (scorer is None) == (candidate_score_record is None and manual_score_record is None):
        return _unavailable_impact(binding, "Provide either one scorer callback or both approved score records")
    candidate_consistency = manual_consistency = input_change_audit = None
    try:
        if candidate_extraction is None or manual_extraction is None:
            return _unavailable_impact(binding, "Both flat extractions are required to bind score impact")
        candidate_consistency = _check_extraction_consistency(comparison["candidate_audit"], candidate_extraction)
        manual_consistency = _check_extraction_consistency(comparison["manual_audit"], manual_extraction)
        if candidate_consistency["status"] != "CONSISTENT" or manual_consistency["status"] != "CONSISTENT":
            return _unavailable_impact(binding, "Inventory and flat extraction differ",
                                       candidate_consistency=candidate_consistency,
                                       manual_consistency=manual_consistency)
        input_change_audit = _audit_extraction_changes(comparison, candidate_extraction, manual_extraction)
        if input_change_audit["status"] != "ATTRIBUTED":
            return _unavailable_impact(binding, "Flat-extraction inputs changed outside the audited inventory comparison",
                                       candidate_consistency=candidate_consistency,
                                       manual_consistency=manual_consistency,
                                       input_change_audit=input_change_audit)
        candidate_semantic = _semantic_extraction(candidate_extraction)
        manual_semantic = _semantic_extraction(manual_extraction)
        if scorer is not None:
            if not callable(scorer) or not isinstance(scorer_id, str) or not scorer_id or not isinstance(scorer_revision, str) or not scorer_revision:
                raise ValueError("Frozen scorer callback needs explicit identity and revision")
            candidate_scores = scorer(deepcopy(candidate_semantic), deepcopy(binding))
            manual_scores = scorer(deepcopy(manual_semantic), deepcopy(binding))
            scorer_meta = {"id": scorer_id, "revision": scorer_revision, "mode": "CALLBACK"}
        else:
            if candidate_score_record is None or manual_score_record is None:
                return _unavailable_impact(binding, "Both approved score records are required")
            candidate_scores = _validate_score_record(
                candidate_score_record, binding_sha256,
                input_change_audit["candidate_semantic_sha256"],
                comparison["candidate_audit"]["inventory_sha256"])
            manual_scores = _validate_score_record(
                manual_score_record, binding_sha256,
                input_change_audit["manual_semantic_sha256"],
                comparison["manual_audit"]["inventory_sha256"])
            pair = {(candidate_score_record["scorer_id"], candidate_score_record["scorer_revision"]),
                    (manual_score_record["scorer_id"], manual_score_record["scorer_revision"])}
            if len(pair) != 1:
                raise ValueError("Approved records use different scorer identities or revisions")
            scorer_meta = {"id": candidate_score_record["scorer_id"],
                           "revision": candidate_score_record["scorer_revision"], "mode": "APPROVED_RECORDS"}
        candidate_flat, manual_flat = _flatten_scores(candidate_scores), _flatten_scores(manual_scores)
        if (input_change_audit["candidate_semantic_sha256"] == input_change_audit["manual_semantic_sha256"]
                and candidate_flat != manual_flat):
            raise ValueError("Identical bound extractions produced different scores under one scorer revision")
        paths = sorted(set(candidate_flat) | set(manual_flat))
        differences = {}
        for path in paths:
            candidate_present, manual_present = path in candidate_flat, path in manual_flat
            candidate_value, manual_value = candidate_flat.get(path), manual_flat.get(path)
            common = {"candidate": candidate_value, "manual": manual_value,
                      "candidate_present": candidate_present, "manual_present": manual_present}
            if not candidate_present or not manual_present or candidate_value is None or manual_value is None:
                differences[path] = {**common, "delta_manual_minus_candidate": None,
                                     "status": "UNAVAILABLE"}
            else:
                differences[path] = {**common,
                                     "delta_manual_minus_candidate": manual_value - candidate_value,
                                     "status": "COMPUTED"}
        if not isinstance(frozen_score_paths, (list, tuple)) or any(not isinstance(p, str) for p in frozen_score_paths):
            raise ValueError("frozen_score_paths must be text paths")
        frozen_violations = []
        for prefix in frozen_score_paths:
            normalized = prefix if prefix.startswith("/") else "/" + prefix
            matched = False
            for path, detail in differences.items():
                if path == normalized or path.startswith(normalized + "/"):
                    matched = True
                    equal_number = (detail["status"] == "COMPUTED"
                                    and detail["delta_manual_minus_candidate"] == 0)
                    equal_explicit_null = (detail["candidate_present"] and detail["manual_present"]
                                           and detail["candidate"] is None and detail["manual"] is None)
                    if not (equal_number or equal_explicit_null):
                        frozen_violations.append(path)
            if not matched:
                frozen_violations.append(normalized + "/<missing>")
        status = "INVALID_FROZEN_SCORES" if frozen_violations else "AVAILABLE"
        return {"schema_version": IMPACT_SCHEMA, "status": status,
                "binding_sha256": binding_sha256,
                "binding_component_sha256": {key: json_hash(binding[key]) for key in sorted(binding)},
                "scorer": scorer_meta, "score_differences": differences,
                "frozen_score_paths": list(frozen_score_paths),
                "frozen_violations": sorted(set(frozen_violations)),
                "candidate_consistency": candidate_consistency,
                "manual_consistency": manual_consistency,
                "input_change_audit": input_change_audit,
                "reason": "Frozen score paths changed" if frozen_violations else None,
                "scientific_accuracy": None,
                "interpretation": "HYPOTHETICAL_EXTRACTION_IMPACT_WITH_OTHER_SCORE_INPUTS_FROZEN"}
    except Exception as exc:
        return _unavailable_impact(binding, str(exc), candidate_consistency=candidate_consistency,
                                   manual_consistency=manual_consistency,
                                   input_change_audit=input_change_audit)

def evaluate_fidelity_impact(protocol, candidate_inventory, manual_inventory, *, binding=None, **score_options):
    """Compose inventory comparison and optional, strictly bound score impact."""
    comparison = compare_inventories(protocol, candidate_inventory, manual_inventory)
    impact = (_unavailable_impact({}, "No score binding supplied") if binding is None else
              measure_score_impact(comparison, binding, **score_options))
    return {"comparison": comparison, "score_impact": impact,
            "scientific_accuracy": None,
            "scope": "EXTRACTION_FIDELITY_AND_BOUND_NUMERICAL_SCORE_SENSITIVITY"}
