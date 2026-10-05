"""Pure source grounding, distinct from scientific truth.
Offsets are Python Unicode code points in the unchanged protocol, not bytes.
Legacy extraction remains diagnostic and is never upgraded implicitly.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import re

SCHEMA = "extraction-grounding-v2"
FACT_FIELDS = {
    "labels": ("target", "probe", "fluorophore", "channel"),
    "steps": ("phase", "operation", "duration_text"),
    "ri": ("solution", "value_text"),
}
NEGATION = re.compile(r"\b(?:not|no|without|never|omit|omitted)\b|不使用|不能|不得|没有|未提供|不含|不采用|不添加|不加入|无需|省略", re.I)
CONDITION = re.compile(r"\b(?:if|unless|provided that)\b|如果|若|仅当|待确认", re.I)


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_span(text, span):
    if not isinstance(span, dict) or set(span) != {"start", "end", "quote"}:
        raise ValueError("Span needs start, end and quote")
    start, end, quote = span["start"], span["end"], span["quote"]
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
            or not isinstance(quote, str) or text[start:end] != quote):
        raise ValueError("Source offset/quotation mismatch")
    return {**span, "quote_sha256": text_hash(quote)}


def _context(text, start, end):
    separators = "\n。;；!?！？"
    left, right = start, end
    while left and text[left - 1] not in separators:
        left -= 1
    while right < len(text) and text[right] not in separators:
        right += 1
    return {"start": left, "end": right, "quote": text[left:right]}


def _transform(raw, name):
    if name == "IDENTITY":
        return raw
    if name == "STRIP":
        return raw.strip()
    if name == "CASEFOLD":
        return raw.casefold()
    pattern, scale, suffix = {
        "MINUTES_TO_HOURS": (r"([0-9]+(?:\.[0-9]+)?)\s*(?:min|minutes?)", Decimal(60), " h"),
        "HOURS_TO_MINUTES": (r"([0-9]+(?:\.[0-9]+)?)\s*(?:h|hours?)", Decimal(60), " min"),
    }.get(name, (None, None, None))
    match = re.fullmatch(pattern, raw, re.I) if pattern else None
    if not match:
        raise ValueError("Unknown or inapplicable field transformation")
    try:
        number = (Decimal(match.group(1)) / scale if name == "MINUTES_TO_HOURS"
                  else Decimal(match.group(1)) * scale)
    except InvalidOperation as exc:
        raise ValueError("Invalid explicit unit value") from exc
    return format(number.normalize(), "f") + suffix


FIELD_SCOPE_POLICIES = {"strict", "diagnostic"}


def _check_scope_policy(policy):
    if policy not in FIELD_SCOPE_POLICIES:
        raise ValueError("Unknown field scope policy")


def _quote_regions(protocol, quote):
    regions, start = [], 0
    while (start := protocol.find(quote, start)) >= 0:
        regions.append({"start": start, "end": start + len(quote), "quote": quote})
        start += 1
    return regions



def quote_span_candidates(protocol, proposed, *, policy="diagnostic"):
    """Candidates are locations under consideration, never asserted support."""
    _check_scope_policy(policy)
    if isinstance(proposed, dict) and set(proposed) == {"quote"} and policy == "diagnostic":
        quote = proposed["quote"]
        if not isinstance(quote, str) or not quote:
            raise ValueError("Quote-only reference needs nonempty original text")
        candidates = _quote_regions(protocol, quote)
        if not candidates:
            raise ValueError("Quote-only reference absent from unchanged protocol")
        resolved = deepcopy(candidates[0]) if len(candidates) == 1 else None
        origin = "QUOTE_ONLY"
    else:
        checked = validate_span(protocol, proposed)
        resolved = {key: checked[key] for key in ("start", "end", "quote")}
        candidates, origin = [deepcopy(resolved)], "EXPLICIT_OFFSETS"
    return {"proposed_span": deepcopy(proposed), "origin": origin,
            "candidate_spans": candidates, "resolved_span": resolved,
            "rule": "GLOBAL_UNIQUE_LITERAL" if origin == "QUOTE_ONLY" and resolved else
                    "EXPLICIT_VALIDATED_OFFSETS" if resolved else "LOCATION_UNPROVEN"}


def _resolve_record_references(audited, quote, protocol, collection, regions, structure):
    occurrences = _quote_regions(protocol, quote)
    candidates = set(range(len(occurrences)))
    if regions:
        candidates &= {i for i, occurrence in enumerate(occurrences)
                       if any(_inside(occurrence, region) for region in regions)}
    for item in audited.values():
        refs = item.get("quote_resolution", {}).get("references", [])
        if not refs:
            continue
        local = {i for i, occurrence in enumerate(occurrences)
                 if all(any(_inside(candidate, occurrence) for candidate in ref["candidate_spans"])
                        for ref in refs)}
        if local:
            candidates &= local
    anchor = occurrences[next(iter(candidates))] if len(candidates) == 1 else None
    for field, item in audited.items():
        resolution = item.get("quote_resolution")
        if resolution is None:
            continue
        refs = resolution["references"]
        for ref in refs:
            if ref["resolved_span"] is not None or anchor is None:
                continue
            local = [candidate for candidate in ref["candidate_spans"] if _inside(candidate, anchor)]
            rule = "UNIQUE_LITERAL_IN_BOUND_RECORD"
            if not local and collection == "steps" and field == "phase":
                local = []
                for candidate in ref["candidate_spans"]:
                    proof = _phase_heading_proof(protocol, [candidate], anchor, structure)
                    if proof and (not regions or any(_inside({"start": proof["heading"]["start"],
                                                              "end": anchor["end"]}, region) for region in regions)):
                        local.append(candidate)
                rule = "UNIQUE_EXPLICIT_CONTROLLING_HEADING"
            if len(local) == 1:
                ref["resolved_span"], ref["rule"] = deepcopy(local[0]), rule
        item["spans"] = [validate_span(protocol, ref["resolved_span"]) for ref in refs
                         if ref["resolved_span"] is not None]
        item["contexts"] = [_context(protocol, span["start"], span["end"]) for span in item["spans"]]
        unresolved = any(ref["resolved_span"] is None for ref in refs)
        if not unresolved:
            item["issues"] = [issue for issue in item["issues"] if issue != "SOURCE_LOCATION_UNPROVEN"]
        elif "SOURCE_LOCATION_UNPROVEN" not in item["issues"]:
            item["issues"].append("SOURCE_LOCATION_UNPROVEN")
        if item["kind"] != "MISSING":
            item["status"] = "GROUNDED" if not item["issues"] else (
                "INFERRED" if item["kind"] == "INFERRED" else "REVIEW_REQUIRED")
        resolution.update(record_anchor=deepcopy(anchor),
                          status="RESOLVED" if not unresolved else "REVIEW_REQUIRED")

def _inside(span, region):
    return region["start"] <= span["start"] < span["end"] <= region["end"]


def _structure_lines(protocol):
    """Recognize formatting/number hierarchy only, never scientific stage names.

    A numbered parent requires a numbered descendant at the record. Markdown
    headings and standalone bold headings have explicit formatting boundaries.
    Every numbered sibling is a boundary, even if it looks like an operation.
    """
    lines, offset = [], 0
    for line in protocol.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        stripped = body.strip()
        markdown = re.fullmatch(r"(#{1,6})\s+(.+?)(?:\s+#+)?", stripped)
        bold = re.fullmatch(r"\*\*(.+?)\*\*", stripped)
        content = (markdown.group(2) if markdown else bold.group(1) if bold else stripped)
        content = content.strip()
        numbered = re.fullmatch(r"(\d+(?:\.\d+)*)(?:[.)])?\s+(.+)", content)
        lines.append({"start": offset, "end": offset + len(body), "quote": body,
                      "number": tuple(map(int, numbered.group(1).split("."))) if numbered else None,
                      "heading": "markdown" if markdown else "bold" if bold else None,
                      "level": len(markdown.group(1)) if markdown else 1 if bold else None})
        offset += len(line)
    return lines


def _phase_heading_proof(protocol, spans, record_anchor, structure):
    """Return an inspectable controlling heading proof or no proof.

    No aliases, title semantics or inferred entity relations authorize scope.
    A support span must lie in one heading line, and the unique record must be
    completely within that heading's bounded region. Number prefixes provide
    an additional parent/child check for ordinary numbered protocols.
    """
    if not spans or record_anchor is None:
        return None
    candidates = [line for line in structure if all(_inside(s, line) for s in spans)]
    if len(candidates) != 1:
        return None
    heading = candidates[0]
    if heading["end"] >= record_anchor["start"]:
        return None
    number, style = heading["number"], heading["heading"]
    if number is None and style is None:
        return None
    record_lines = [line for line in structure if _inside(record_anchor, line)]
    if number is not None:
        if len(record_lines) != 1:
            return None
        child = record_lines[0]["number"]
        if child is None or len(child) <= len(number) or child[:len(number)] != number:
            return None
    region_end = len(protocol)
    for line in structure:
        if line["start"] <= heading["start"]:
            continue
        # Other explicit headings cannot silently extend the numbered parent.
        heading_boundary = (line["heading"] is not None and
                            (style is None or line["heading"] != style or
                             line["level"] <= heading["level"]))
        numbered_boundary = (number is not None and line["number"] is not None
                             and len(line["number"]) <= len(number))
        if heading_boundary or numbered_boundary:
            region_end = line["start"]
            break
    region = {"start": heading["end"], "end": region_end}
    if not _inside(record_anchor, region):
        return None
    return {"rule": "EXPLICIT_PARENT_HEADING_REGION_V1", "heading": {
                key: heading[key] for key in ("start", "end", "quote")},
            "number_prefix": list(number) if number is not None else None,
            "heading_style": style, "region": region,
            "record_anchor": deepcopy(record_anchor)}


def _mark_scope_review(field_audit, code):
    if code not in field_audit["issues"]:
        field_audit["issues"].append(code)
    field_audit["status"] = "REVIEW_REQUIRED"


def _audit_record_scope(audited, quote, protocol, collection, regions, structure, policy):
    if policy == "diagnostic":
        _resolve_record_references(audited, quote, protocol, collection, regions, structure)
    occurrences = _quote_regions(protocol, quote)
    candidates = set(range(len(occurrences)))
    local_fields = {}
    for field, item in audited.items():
        if not item["spans"]:
            continue
        local = {index for index, occurrence in enumerate(occurrences)
                 if all(_inside(span, occurrence) for span in item["spans"])}
        if local:
            local_fields[field] = local
            candidates &= local
    anchor = deepcopy(occurrences[next(iter(candidates))]) if len(candidates) == 1 else None
    for field, item in audited.items():
        if not item["spans"]:
            item["scope_binding"] = {"rule": "NO_SUPPLIED_SOURCE_SPAN", "record_anchor": anchor}
            continue
        if field in local_fields and not candidates:
            _mark_scope_review(item, "FIELD_RECORD_OCCURRENCE_CONFLICT")
            proof = None
        elif anchor is not None and all(_inside(span, anchor) for span in item["spans"]):
            proof = {"rule": "RECORD_LOCAL_OFFSETS_V1", "record_anchor": anchor}
        elif anchor is None:
            _mark_scope_review(item, "RECORD_LOCATION_UNPROVEN")
            proof = None
        elif policy == "diagnostic" and collection == "steps" and field == "phase":
            proof = _phase_heading_proof(protocol, item["spans"], anchor, structure)
        else:
            proof = None
        if proof is None:
            if policy == "strict" and field not in local_fields:
                raise ValueError("Field support lies outside its record quotation")
            _mark_scope_review(item, "FIELD_SCOPE_UNPROVEN")
        if proof is not None and "heading" in proof and regions:
            inherited_extent = {"start": proof["heading"]["start"], "end": anchor["end"]}
            if not any(_inside(inherited_extent, region) for region in regions):
                _mark_scope_review(item, "FIELD_HEADING_BRANCH_SCOPE_UNPROVEN")
                proof = None
        if regions and (anchor is None or not any(_inside(anchor, region) for region in regions)
                        or any(not any(_inside(span, region) for region in regions)
                               for span in item["spans"])):
            _mark_scope_review(item, "FIELD_OUTSIDE_DECLARED_BRANCH")
            proof = None
        item["scope_binding"] = proof or {"rule": "UNPROVEN", "record_anchor": anchor}
    return anchor

def audit_field(value, support, protocol, *, row_quote=None, field_scope_policy="strict"):
    """Audit literal support; diagnostic policy never relaxes integrity checks."""
    _check_scope_policy(field_scope_policy)
    if not isinstance(support, dict):
        raise ValueError("Every field requires typed support")
    kind = support.get("kind")
    if kind not in {"EXPLICIT", "DERIVED", "INFERRED", "MISSING"}:
        raise ValueError("Unknown fact origin")
    spans = support.get("spans", [])
    if not isinstance(spans, list):
        raise ValueError("Field spans must be an array")
    references = [quote_span_candidates(protocol, span, policy=field_scope_policy) for span in spans]
    spans = [validate_span(protocol, ref["resolved_span"]) for ref in references if ref["resolved_span"] is not None]
    candidate_spans = [candidate for ref in references for candidate in ref["candidate_spans"]]
    issues = ["SOURCE_LOCATION_UNPROVEN"] if any(ref["resolved_span"] is None for ref in references) else []
    if value is None:
        if kind != "MISSING" or references or support.get("raw_value") is not None:
            raise ValueError("Null must explicitly record missingness, without invented support")
        return {"kind": kind, "status": "MISSING", "spans": [],
                "missingness": "EXTRACTOR_PROPOSAL_NOT_COMPLETENESS_PROOF", "issues": []}
    if not isinstance(value, str):
        raise ValueError("Facts must retain text values")
    if kind == "MISSING":
        raise ValueError("Present field cannot have missing origin")
    if kind == "INFERRED":
        issues.append("INFERRED_FIELD_NOT_ELIGIBLE")
    else:
        raw = support.get("raw_value")
        if not isinstance(raw, str) or not raw or not references or not any(raw in s["quote"] for s in candidate_spans):
            raise ValueError("Field value has no bound original text")
        transform = support.get("transform", "IDENTITY")
        if kind == "EXPLICIT" and transform != "IDENTITY":
            raise ValueError("Normalized values must declare DERIVED origin")
        if _transform(raw, transform) != value:
            raise ValueError("Extracted field differs from its stated transformation")
    if row_quote is not None and spans:
        if not isinstance(row_quote, str) or not row_quote:
            raise ValueError("Record quotation must be nonempty text")
        if not any(all(_inside(span, region) for span in spans)
                   for region in _quote_regions(protocol, row_quote)):
            if field_scope_policy == "strict":
                raise ValueError("Field support lies outside its record quotation")
            issues.append("FIELD_SCOPE_UNPROVEN")
    contexts = [_context(protocol, s["start"], s["end"]) for s in spans]
    return {"kind": kind, "status": "GROUNDED" if not issues else ("INFERRED" if kind == "INFERRED" else "REVIEW_REQUIRED"),
            "spans": spans, "contexts": contexts, "raw_value": support.get("raw_value"),
            "transform": support.get("transform", "IDENTITY"), "issues": issues,
            **({"candidate_spans": candidate_spans, "quote_resolution": {
                "references": references, "status": "REVIEW_REQUIRED" if issues else "RESOLVED"}}
               if field_scope_policy == "diagnostic" else {})}


def audit_extraction(value, protocol, *, field_scope_policy="strict"):
    """Keep source integrity strict; diagnostic scope gaps require field review.

    Record-local containment certifies positions, not entity/dimension semantics.
    Supplied branch spans are bounded regions; declaration-only anchors cannot
    silently authorize the rest of a route. Parent-heading inheritance is the
    sole cross-record structural rule and applies only to step phase metadata.
    """
    _check_scope_policy(field_scope_policy)
    if not isinstance(protocol, str) or not isinstance(value, dict):
        raise ValueError("Protocol and extraction types differ from contract")
    strict = value.get("schema_version") == SCHEMA
    if value.get("schema_version") not in {None, SCHEMA}:
        raise ValueError("Unknown extraction schema; explicit migration required")
    result = deepcopy(value)
    facts, issues = [], []
    previous_operation_start, operation_spans = -1, set()
    branches = value.get("branches", [{"id": "main", "mode": "SERIAL", "sample_id": "main", "spans": []}])
    branch_resolutions, unproven_branches = {}, set()
    if strict:
        if not isinstance(branches, list) or not branches:
            raise ValueError("Explicit branch declarations required")
        if any(not isinstance(b, dict) for b in branches):
            raise ValueError("Invalid branch declaration schema")
        ids = [b.get("id") for b in branches]
        if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
            raise ValueError("Invalid branch identity")
        for branch in branches:
            if (branch.get("mode") not in {"SERIAL", "ALTERNATIVE"}
                    or not isinstance(branch.get("sample_id"), str) or not branch["sample_id"]):
                raise ValueError("Branch must retain alternative/serial and sample identity")
            spans = branch.get("spans")
            if not isinstance(spans, list):
                raise ValueError("Branch declaration spans required")
            if not spans and not (len(branches) == 1 and branch["id"] == "main" and branch["mode"] == "SERIAL"):
                raise ValueError("Named alternatives require original branch anchors")
            refs = [quote_span_candidates(protocol, span, policy=field_scope_policy) for span in spans]
            branch_resolutions[branch["id"]] = refs
            if any(ref["resolved_span"] is None for ref in refs):
                unproven_branches.add(branch["id"])
                issues.append({"branch": branch["id"], "code": "BRANCH_LOCATION_UNPROVEN"})
            if field_scope_policy == "diagnostic":
                diagnosed = next(b for b in result["branches"] if b["id"] == branch["id"])
                diagnosed.update(quote_resolution=deepcopy(refs),
                    resolved_spans=[deepcopy(ref["resolved_span"]) for ref in refs if ref["resolved_span"] is not None],
                    location_status="REVIEW_REQUIRED" if branch["id"] in unproven_branches else "RESOLVED")
    branch_map = {b["id"]: b for b in branches}
    branch_regions = {b["id"]:[validate_span(protocol, ref["resolved_span"])
                              for ref in branch_resolutions.get(b["id"], []) if ref["resolved_span"] is not None]
                      for b in branches}
    structure = _structure_lines(protocol) if field_scope_policy == "diagnostic" else []
    for collection, fields in FACT_FIELDS.items():
        rows = value.get(collection)
        if not isinstance(rows, list):
            raise ValueError("Extraction collections must be arrays")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("Invalid extraction record")
            if not strict:
                issues.append({"collection": collection, "index": index, "code": "LEGACY_FIELDS_UNVERIFIED"})
                continue
            if row.get("branch") not in branch_map:
                raise ValueError("Record branch was not declared")
            support = row.get("field_support")
            if not isinstance(support, dict) or set(support) != set(fields):
                raise ValueError("Every factual field needs its own support")
            quote = row.get("quote")
            if not isinstance(quote, str) or not quote or quote not in protocol:
                raise ValueError("Record quotation absent from unchanged protocol")
            assertion = row.get("assertion")
            if not isinstance(assertion, dict) or assertion.get("polarity") not in {"AFFIRMED", "NEGATED", "CONDITIONAL"}:
                raise ValueError("Record must retain assertion polarity")
            audited = {}
            for field in fields:
                if field not in row:
                    raise ValueError("Missing factual field is distinct from explicit null")
                audited[field] = audit_field(row[field], support[field], protocol, field_scope_policy=field_scope_policy)
            regions = branch_regions[row["branch"]]
            record_anchor = _audit_record_scope(audited, quote, protocol, collection,
                                               regions, structure, field_scope_policy)
            if row["branch"] in unproven_branches:
                for item in audited.values():
                    if item["kind"] != "MISSING":
                        _mark_scope_review(item, "BRANCH_LOCATION_UNPROVEN")
            for field, item in audited.items():
                for issue in item["issues"]:
                    issues.append({"collection": collection, "index": index, "field": field, "code": issue})
            for field, item in audited.items():
                local_contexts = [c["quote"] for c in item.get("contexts", [])]
                for code, violated in (
                    ("NEGATION_CONTEXT_NOT_PRESERVED", any(NEGATION.search(c) for c in local_contexts)
                     and assertion["polarity"] == "AFFIRMED"),
                    ("CONDITIONAL_CONTEXT_NOT_PRESERVED", any(CONDITION.search(c) for c in local_contexts)
                     and assertion["polarity"] != "CONDITIONAL")):
                    if violated:
                        _mark_scope_review(item, code)
                        issues.append({"collection": collection, "index": index, "field": field, "code": code})
            if collection == "steps" and audited["operation"]["status"] == "GROUNDED":
                positions = [(span["start"],span["end"]) for span in audited["operation"]["spans"]]
                position = min(start for start,end in positions)
                if position < previous_operation_start:
                    _mark_scope_review(audited["operation"], "SOURCE_OPERATION_ORDER_CHANGED")
                    issues.append({"collection":collection,"index":index,"field":"operation","code":"SOURCE_OPERATION_ORDER_CHANGED"})
                if any(pair in operation_spans for pair in positions):
                    _mark_scope_review(audited["operation"], "SOURCE_OPERATION_OCCURRENCE_REUSED")
                    issues.append({"collection":collection,"index":index,"field":"operation","code":"SOURCE_OPERATION_OCCURRENCE_REUSED"})
                previous_operation_start = position
                operation_spans.update(positions)
            # Preserve source order and duplicate operations; never sort/deduplicate.
            facts.append({"collection": collection, "index": index, "id": row.get("id"),
                          "branch": row["branch"], "sample_id": branch_map[row["branch"]]["sample_id"],
                          "assertion": deepcopy(assertion), "record_anchor": record_anchor, "fields": audited})
    if strict and not facts and protocol.strip():
        issues.append({"code": "EMPTY_EXTRACTION_NOT_COMPLETENESS_PROOF"})
    status = "GROUNDED" if strict and not issues else ("REVIEW_REQUIRED" if strict else "LEGACY_STRUCTURE_ONLY")
    return {"schema_version": SCHEMA if strict else "legacy-v1", "protocol_sha256": text_hash(protocol),
            "fidelity_status": status, "scoring_eligible": strict and not issues, "facts": facts,
            "field_scope_policy": field_scope_policy, "field_scope_rules_version": "structural-field-scope-v2",
            "issues": issues, "validated": result,
            "scope": "Literal/declared derivation fidelity only; completeness and scientific truth are not certified"}



# Public lexical normalizations, not a scientific ontology. Unrecognized phase
# metadata stays unresolved rather than borrowing scope from a method name.
_PHASE_ALIASES = {
    "label_preparation": ("标签准备", "标记准备", "label preparation", "labelling", "labeling"),
    "storage": ("存储", "保存", "storage"),
    "processing": ("光透明", "透明处理", "处理温度", "processing", "clearing"),
    "pretreatment": ("前处理", "预处理", "pretreatment", "pre-treatment"),
    "postprocessing": ("终处理", "后处理", "postprocessing", "post-processing"),
    "imaging": ("成像", "imaging"),
    "method": ("方案", "方法身份", "method", "protocol"),
}
_UNIT_PATTERNS = {
    "degC": r"(?:°\s*C|℃|degC)",
    "percent": r"(?:vol\s*%|wt\s*%|%|percent)",
    "h": r"(?:h|hours?)\b", "min": r"(?:min|minutes?)\b",
    "mm": r"mm\b", "cm": r"cm\b", "um": r"(?:um|μm|µm)\b",
}
_UNIT_EQUIVALENTS = {"°C":"degC", "℃":"degC", "%":"percent", "hour":"h", "minutes":"min"}
_BASIS_PATTERNS = {
    "v/v": r"(?:\bvol\s*%|v\s*/\s*v|体积百分比)",
    "w/v": r"(?:w\s*/\s*v|质量[／/]体积|质量体积百分比)",
    "w/w": r"(?:\bwt\s*%|w\s*/\s*w|质量百分比)",
}


def _literal_present(value, quote):
    if type(value) in {int, float}:
        if type(value) is float and (value != value or abs(value) == float("inf")):
            return False
        return any(Decimal(m.group()) == Decimal(str(value))
                   for m in re.finditer(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", quote))
    if isinstance(value,str) and value:
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])",quote) is not None
    return False


def _phase_at(protocol, start, end):
    left = protocol.rfind(chr(10),0,start) + 1
    right = protocol.find(chr(10),end)
    line = protocol[left:right if right >= 0 else len(protocol)]
    # A named heading controls its full line, including clauses beyond a ';'.
    heading = re.split(r"[：:]",line,maxsplit=1)[0]
    found = [phase for phase,aliases in _PHASE_ALIASES.items()
             if any(alias.casefold() in heading.casefold() for alias in aliases)]
    if len(found) == 1:
        return found[0], {"start":left,"end":right if right >= 0 else len(protocol),"quote":line}
    local = protocol[start:end]
    found = [phase for phase,aliases in _PHASE_ALIASES.items()
             if any(alias.casefold() in local.casefold() for alias in aliases)]
    return (found[0] if len(found) == 1 else None), {"start":left,"end":right if right >= 0 else len(protocol),"quote":line}


def audit_facts(facts, protocol, required_fields=None):
    """Mechanical typed-fact audit for protocol quantities and qualifiers.

    Legacy fact rows can be diagnosed without inventing missing support. The
    returned status covers only supplied fields. Public required_fields checks
    presence, not complete scientific interpretation. No model/API calls occur.
    """
    if not isinstance(protocol,str) or not isinstance(facts,list):
        raise ValueError("Protocol text and factual array required")
    if required_fields is not None and (not isinstance(required_fields,list)
            or any(not isinstance(f,str) or not f for f in required_fields)
            or len(required_fields) != len(set(required_fields))):
        raise ValueError("Required fields must be explicit unique identifiers")
    audits, mismatches, unresolved, seen = [], [], [], set()
    for index, fact in enumerate(facts):
        if not isinstance(fact,dict) or not isinstance(fact.get("field"),str) or not fact["field"]:
            raise ValueError("Each fact needs an explicit field identifier")
        field = fact["field"]
        seen.add(field)
        local, unknown = [], []
        try:
            span = validate_span(protocol,{key:fact.get(key) for key in ("start","end","quote")})
        except ValueError:
            local.append(field + ".span")
            audits.append({"index":index,"field":field,"issues":local,"scope":"INVALID_SOURCE_SPAN"})
            mismatches.extend(local)
            continue
        quote = span["quote"]
        kind = fact.get("origin",fact.get("kind","EXPLICIT"))
        value = fact.get("value")
        if "value" not in fact:
            local.append(field + ".missing")
        elif kind in {"INFERRED","MISSING"} or value is None:
            unknown.append(field + ".unverified_missingness_or_inference")
        elif kind == "DERIVED":
            try:
                grounded = audit_field(str(value),fact.get("support"),protocol,row_quote=quote)
                if grounded["status"] != "GROUNDED":
                    unknown.append(field + ".inferred")
            except ValueError:
                local.append(field)
        elif kind != "EXPLICIT":
            raise ValueError("Unknown generic fact origin")
        elif not _literal_present(value,quote):
            local.append(field)
        # Explicit metadata needs an explicit phase anchor or recognized lexical
        # heading. A citation or unanchored hand-written scope cannot replace it.
        phase, phase_anchor = _phase_at(protocol,span["start"],span["end"])
        if "scope" in fact:
            proposed_scope = fact["scope"]
            scope_support = fact.get("scope_support")
            if scope_support is not None:
                try:
                    bound_scope = audit_field(proposed_scope,scope_support,protocol)
                    if bound_scope["status"] != "GROUNDED":
                        unknown.append(field + ".scope")
                    if any(not phase_anchor["start"] <= span["start"] < span["end"] <= phase_anchor["end"]
                           for span in bound_scope["spans"]):
                        local.append(field + ".scope")
                    if phase is not None and proposed_scope != phase:
                        local.append(field + ".scope")
                except ValueError:
                    local.append(field + ".scope")
            elif phase is None:
                unknown.append(field + ".scope")
            elif proposed_scope != phase:
                local.append(field + ".scope")
        context = _context(protocol,span["start"],span["end"])
        condition = bool(CONDITION.search(context["quote"]))
        negated = bool(NEGATION.search(context["quote"]))
        polarity = fact.get("polarity")
        normalized_polarity = {"positive":"AFFIRMED","negative":"NEGATED","conditional":"CONDITIONAL",
                               "AFFIRMED":"AFFIRMED","NEGATED":"NEGATED","CONDITIONAL":"CONDITIONAL"}.get(polarity)
        if polarity is not None:
            if normalized_polarity is None:
                raise ValueError("Unknown generic assertion polarity")
            expected_polarity = "CONDITIONAL" if condition else ("NEGATED" if negated else "AFFIRMED")
            if normalized_polarity != expected_polarity:
                local.append(field + ".polarity")
        elif condition or negated:
            # A literal number can survive a change of assertion just as an
            # entity can. Missing qualifier metadata is not affirmative support.
            unknown.append(field + ".polarity")
        if "unit" in fact:
            unit = _UNIT_EQUIVALENTS.get(fact["unit"],fact["unit"])
            pattern = _UNIT_PATTERNS.get(unit)
            if pattern is None:
                unknown.append(field + ".unit")
            elif not re.search(pattern,quote,re.I):
                local.append(field + ".unit")
            elif type(value) in {int,float} and kind == "EXPLICIT":
                quantities = re.finditer(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*" + pattern,quote,re.I)
                if not any(Decimal(m.group(1)) == Decimal(str(value)) for m in quantities):
                    local.append(field + ".unit")
        if "basis" in fact:
            found_basis = [basis for basis,pattern in _BASIS_PATTERNS.items() if re.search(pattern,quote,re.I)]
            if len(found_basis) != 1:
                unknown.append(field + ".basis")
            elif found_basis[0] != fact["basis"]:
                local.append(field + ".basis")
        audits.append({"index":index,"field":field,"origin":kind,"span":span,
                       "source_phase":phase,"phase_anchor":phase_anchor,"assertion_context":context,
                       "issues":local,"unresolved":unknown})
        mismatches.extend(local)
        unresolved.extend(unknown)
    if required_fields is not None:
        mismatches.extend(field + ".missing" for field in required_fields if field not in seen)
    status = "UNFAITHFUL" if mismatches else ("UNRESOLVED" if unresolved else "FAITHFUL")
    return {"schema_version":"generic-fidelity-v1","protocol_sha256":text_hash(protocol),
            "status":status,"mismatch_fields":sorted(set(mismatches)),"unresolved_fields":sorted(set(unresolved)),
            "audits":audits,"completeness":"DECLARED_FIELD_PRESENCE_ONLY" if required_fields is not None else "NOT_ESTABLISHED",
            "required_fields":deepcopy(required_fields),"scientific_validation":"PENDING_USER_EXPERT",
            "scope":"Literal values, registered lexical metadata and declared transforms; no completeness or scientific truth certification"}


def diagnose_extraction(value, protocol):
    """Scan independent failures without producing certified extracted facts."""
    errors, locations = [], []
    def reference(path, span):
        try:
            result = quote_span_candidates(protocol, span)
            locations.append(dict(path=path, **result))
        except (ValueError, TypeError) as exc:
            errors.append(dict(path=path, message=str(exc), type=type(exc).__name__))
    if not isinstance(value, dict):
        return dict(hard_errors=[dict(path="extraction",message="Extraction must be an object",type="ValueError")],
                    locations=[],certification=False,scientific_truth=None)
    branches = value.get("branches", [])
    if isinstance(branches, list):
        for bi, branch in enumerate(branches):
            if isinstance(branch, dict) and isinstance(branch.get("spans"), list):
                for si, span in enumerate(branch["spans"]):
                    reference(f"extraction.branches[{bi}].spans[{si}]", span)
    fields_scanned = 0
    for collection, fields in FACT_FIELDS.items():
        rows = value.get(collection)
        if not isinstance(rows, list):
            errors.append(dict(path="extraction."+collection,message="Collection must be an array",type="ValueError"))
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(dict(path=f"extraction.{collection}[{index}]",message="Record must be an object",type="ValueError"))
                continue
            supports = row.get("field_support", {})
            for field in fields:
                fields_scanned += 1
                path = f"extraction.{collection}[{index}].{field}"
                support = supports.get(field) if isinstance(supports, dict) else None
                if isinstance(support, dict) and isinstance(support.get("spans"), list):
                    for si, span in enumerate(support["spans"]):
                        reference(f"{path}.support.spans[{si}]", span)
                try:
                    if field not in row:
                        raise ValueError("Missing factual field differs from explicit null")
                    audit_field(row[field],support,protocol,field_scope_policy="diagnostic")
                except (ValueError, TypeError) as exc:
                    errors.append(dict(path=path,message=str(exc),type=type(exc).__name__))
    return dict(schema_version="extraction-failure-diagnostics-v1",protocol_sha256=text_hash(protocol),
                fields_scanned=fields_scanned,hard_errors=errors,locations=locations,
                ambiguous_locations=sum(ref["resolved_span"] is None for ref in locations),
                certification=False,scientific_truth=None,
                scope="INDEPENDENT_LOCATION_AND_DECLARED_TRANSFORM_SCAN_NOT_VALIDATED_EXTRACTION")
