"""Exact source-region scope, independent of scientific or sample identity truth.

Offsets are Python Unicode code points in the unchanged protocol. Route regions
are supplied validated branch spans; short declarations are never extended.
"""
from copy import deepcopy

from .fidelity import text_hash, audit_field


VERSION = "requirement-source-scope-v1"
VALIDATION_SCOPE = (
    "Specified original source regions only; route completeness, sample_id "
    "entity semantics and scientific truth are not certified"
)


def _exact_span(span, protocol):
    if not isinstance(span, dict):
        return None
    start, end, quote = (span.get(key) for key in ("start", "end", "quote"))
    if (type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(protocol)
            or not isinstance(quote, str) or protocol[start:end] != quote):
        return None
    return {"start": start, "end": end, "quote": quote}


def _inside(span, region):
    return region["start"] <= span["start"] < span["end"] <= region["end"]


def _occurrences(quote, protocol):
    if not quote.strip():
        return []
    result, start = [], 0
    while (start := protocol.find(quote, start)) >= 0:
        result.append({"start": start, "end": start + len(quote), "quote": quote})
        start += 1
    return result


def resolve_scope(requirement, validated_extraction, protocol):
    """Resolve declared source bounds without certifying route/sample semantics.

    GLOBAL retains the whole-protocol source domain. ROUTE requires exactly one
    declared branch and all its original references to be resolved. An empty
    SERIAL/main declaration is not invented into a whole-protocol route region.
    """
    if not isinstance(requirement, dict) or not isinstance(protocol, str):
        raise ValueError("Requirement and protocol must retain their contract types")
    kind = requirement.get("scope", "GLOBAL")
    if kind not in {"GLOBAL", "ROUTE"}:
        raise ValueError("Requirement scope must be GLOBAL or ROUTE")
    result = dict(version=VERSION, scope=kind,
                  route_id=requirement.get("route_id") if kind == "ROUTE" else None,
                  regions=[], protocol_sha256=text_hash(protocol),
                  scope_status="RESOLVED", guards=[],
                  validation_scope=VALIDATION_SCOPE, sample_identity_certified=False,
                  scientific_truth=None)
    if kind == "GLOBAL":
        if protocol:
            result["regions"] = [{"start": 0, "end": len(protocol), "quote": protocol}]
        return result

    def unresolved(code):
        result["scope_status"] = "UNRESOLVED"
        if code not in result["guards"]:
            result["guards"].append(code)
        return result

    route = result["route_id"]
    if not isinstance(route, str) or not route:
        return unresolved("REQUIREMENT_ROUTE_ID_MISSING")
    if not isinstance(validated_extraction, dict):
        return unresolved("REQUIREMENT_ROUTE_NOT_DECLARED")
    audit = validated_extraction.get("field_audit", {})
    for container in (validated_extraction, audit):
        if isinstance(container, dict) and container.get("protocol_sha256") not in (None, result["protocol_sha256"]):
            return unresolved("REQUIREMENT_SCOPE_PROTOCOL_CHANGED")
    branches = validated_extraction.get("branches", [])
    if not isinstance(branches, list):
        return unresolved("REQUIREMENT_ROUTE_NOT_DECLARED")
    matches = [b for b in branches if isinstance(b, dict) and b.get("id") == route]
    if len(matches) != 1:
        return unresolved("REQUIREMENT_ROUTE_AMBIGUOUS" if matches else "REQUIREMENT_ROUTE_NOT_DECLARED")
    branch = matches[0]
    if branch.get("location_status") not in (None, "RESOLVED"):
        return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
    references = branch.get("quote_resolution", [])
    if not isinstance(references, list) or any(
            not isinstance(ref, dict) or ref.get("resolved_span") is None for ref in references):
        return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
    spans = branch.get("resolved_spans", branch.get("spans"))
    if not isinstance(spans, list) or not spans:
        return unresolved("REQUIREMENT_ROUTE_REGIONS_MISSING")
    regions = [_exact_span(span, protocol) for span in spans]
    if any(region is None for region in regions):
        return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
    # A partial resolution cannot silently drop an ambiguous branch fragment.
    proposed = branch.get("spans", [])
    if (not isinstance(proposed, list) or len(proposed) != len(regions)
            or references and len(references) != len(regions)):
        return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
    for index, region in enumerate(regions):
        original = proposed[index]
        if not isinstance(original, dict) or original.get("quote") != region["quote"]:
            return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
        if "start" in original or "end" in original:
            if _exact_span(original, protocol) != region:
                return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
        elif not references or _exact_span(references[index].get("resolved_span"), protocol) != region:
            return unresolved("REQUIREMENT_ROUTE_LOCATION_UNPROVEN")
    result["regions"] = deepcopy(regions)

    rule = requirement.get("literal_rule")
    if isinstance(rule, dict) and rule.get("type") == "SOURCE_LITERAL_EQUALITY":
        binding = rule.get("protocol_binding")
        if not isinstance(binding, dict):
            return unresolved("PROTOCOL_BINDING_ROUTE_UNPROVEN")
        if binding.get("branch") is not None and binding["branch"] != route:
            return unresolved("PROTOCOL_BINDING_ROUTE_CONFLICT")
        collection = binding.get("collection")
        rows = validated_extraction.get(collection, []) if isinstance(collection, str) else []
        if not isinstance(rows, list):
            return unresolved("PROTOCOL_BINDING_RECORD_UNRESOLVED")
        if binding.get("record_id") is not None:
            selected = [row for row in rows if isinstance(row, dict) and row.get("id") == binding["record_id"]]
        elif binding.get("branch") is not None:
            selected = [row for row in rows if isinstance(row, dict) and row.get("branch") == binding["branch"]]
        else:
            selected = []
        if len(selected) != 1:
            return unresolved("PROTOCOL_BINDING_RECORD_UNRESOLVED")
        if selected[0].get("branch") != route:
            return unresolved("PROTOCOL_BINDING_ROUTE_CONFLICT")
        for key in ("span", "entity_span", "dimension_span", "value_span"):
            if key in binding and not scope_contains_span(result, binding[key], protocol):
                return unresolved("PROTOCOL_BINDING_OUTSIDE_REQUIREMENT_SCOPE")
    return result


def scope_contains_span(scope, span, protocol=None):
    """Require one complete occurrence inside one resolved original region.

    Supplying protocol also verifies exact text/hash integrity. Disjoint regions
    are never joined to manufacture support across an intervening source area.
    """
    if not isinstance(scope, dict) or scope.get("scope_status") != "RESOLVED":
        return False
    regions = scope.get("regions", [])
    if not isinstance(regions, list) or not isinstance(span, dict):
        return False
    if protocol is not None:
        if not isinstance(protocol, str) or scope.get("protocol_sha256") != text_hash(protocol):
            return False
        span = _exact_span(span, protocol)
        regions = [_exact_span(region, protocol) for region in regions]
        if span is None or any(region is None for region in regions):
            return False
    else:
        bounds = [span, *regions]
        if any(not isinstance(item, dict) or type(item.get("start")) is not int
               or type(item.get("end")) is not int or not 0 <= item["start"] < item["end"] for item in bounds):
            return False
    return any(_inside(span, region) for region in regions)


def audit_requirement_quotes(record, scope, protocol):
    """Keep raw quotations and all exact occurrences; audit route-local support.

    Repetition outside the route does not invalidate a real local occurrence.
    A quote of the entire protocol is never a decisive local route anchor.
    """
    if not isinstance(record, dict) or not isinstance(record.get("quotes"), list):
        raise ValueError("Requirement quotations must be an array")
    if not isinstance(protocol, str) or not isinstance(scope, dict):
        raise ValueError("Protocol and resolved scope must retain their contract types")
    guards = list(scope.get("guards", []))
    valid_scope = (scope.get("scope_status") == "RESOLVED"
                   and scope.get("protocol_sha256") == text_hash(protocol))
    if not valid_scope:
        guards.append("REQUIREMENT_SCOPE_UNRESOLVED")
    audits, local_anchor = [], False
    for quote in record["quotes"]:
        if not isinstance(quote, str):
            raise ValueError("Protocol quotations must be text")
        occurrences = _occurrences(quote, protocol)
        local = [span for span in occurrences if scope_contains_span(scope, span, protocol)] if valid_scope else []
        whole_protocol = scope.get("scope") == "ROUTE" and quote == protocol
        eligible = bool(local) and not whole_protocol
        if not occurrences:
            status = "INVALID_PROTOCOL_QUOTATION"
        elif not valid_scope:
            status = "REQUIREMENT_SCOPE_UNRESOLVED"
        elif whole_protocol:
            status = "PROTOCOL_WIDE_QUOTATION_NOT_LOCAL"
        elif not local:
            status = "QUOTATION_OUTSIDE_REQUIREMENT_SCOPE"
        else:
            status = "ANCHORED_IN_SCOPE"
        if status != "ANCHORED_IN_SCOPE":
            guards.append(status)
        local_anchor |= eligible
        audits.append(dict(quote=quote, status=status, occurrences=occurrences,
                           local_occurrences=local, eligible_local_anchor=eligible,
                           source_span=deepcopy(local[0]) if eligible and len(local) == 1 else None,
                           ambiguous_location=len(occurrences) > 1,
                           ambiguous_local_location=len(local) > 1))
    if record.get("status") in {"SATISFIED", "VIOLATED"} and not local_anchor:
        guards.append("MISSING_DECISIVE_LOCAL_PROTOCOL_ANCHOR")
    guards = sorted(set(guards))
    return dict(version=VERSION, scope_status="RESOLVED" if valid_scope else "UNRESOLVED",
                status="UNRESOLVED" if guards else "RESOLVED", guards=guards,
                quote_audits=audits, has_local_decisive_anchor=local_anchor,
                protocol_sha256=text_hash(protocol), validation_scope=VALIDATION_SCOPE)



def audit_requirement_bindings(record, scope, protocol):
    """Bind all supplied protocol applicability fields to their source domain.

    External source passages retain the external document domain. This checks
    original protocol support only; it does not certify applicability semantics.
    """
    if not isinstance(record, dict) or not isinstance(scope, dict):
        raise ValueError("Binding audit requires record and resolved scope")
    if scope.get("scope") != "ROUTE":
        return dict(status="RESOLVED", guards=[], bindings=[],
                    scope="GLOBAL_EXISTING_EVIDENCE_AUDIT", scientific_truth=None)
    guards, audits = list(scope.get("guards", [])), []
    if scope.get("scope_status") != "RESOLVED" or scope.get("protocol_sha256") != text_hash(protocol):
        guards.append("PROTOCOL_BINDING_REQUIREMENT_SCOPE_UNRESOLVED")
    checks = record.get("evidence_checks", [])
    if not isinstance(checks, list):
        raise ValueError("Evidence checks must be an array")
    for check_index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError("Evidence checks must retain objects")
        bindings = check.get("protocol_bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("Protocol bindings must be an object")
        for field, binding in bindings.items():
            local = []
            if not isinstance(binding, dict):
                local.append("PROTOCOL_APPLICABILITY_FIELD_UNBOUND_IN_REQUIREMENT_SCOPE")
                field_audit = None
            else:
                try:
                    field_audit = audit_field(binding.get("value"), binding.get("support"), protocol)
                except ValueError:
                    field_audit = None
                    local.append("PROTOCOL_APPLICABILITY_FIELD_INVALID_IN_REQUIREMENT_SCOPE")
                if field_audit is not None:
                    spans = field_audit.get("spans", [])
                    if field_audit["status"] != "GROUNDED" or not spans:
                        local.append("PROTOCOL_APPLICABILITY_FIELD_UNPROVEN_IN_REQUIREMENT_SCOPE")
                    if any(not scope_contains_span(scope, span, protocol) for span in spans):
                        local.append("PROTOCOL_APPLICABILITY_FIELD_OUTSIDE_REQUIREMENT_SCOPE")
            guards.extend(local)
            audits.append(dict(check_index=check_index, field=field,
                               original_binding=deepcopy(binding), field_audit=deepcopy(field_audit),
                               status="UNRESOLVED" if local else "RESOLVED", guards=local))
    return dict(version=VERSION, status="UNRESOLVED" if guards else "RESOLVED",
                guards=sorted(set(guards)), bindings=audits,
                protocol_sha256=text_hash(protocol), validation_scope=VALIDATION_SCOPE,
                scientific_truth=None)
