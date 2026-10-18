"""Four evidence layers: identity, immutable source spans, entailment proposal,
and explicit applicability. None authenticates science or an expert's identity.
Legacy bibliography/assistant claim cards cannot authorize decisive science.
"""
from copy import deepcopy
import math
import json
from urllib.parse import urlsplit
from .fidelity import audit_field, text_hash, validate_span

SCHEMA = "source-grounding-v2"


def scope_leaves(value, prefix=""):
    if isinstance(value, dict):
        return {p: v for k, item in value.items() for p, v in scope_leaves(item, prefix + ("." if prefix else "") + str(k)).items()}
    if isinstance(value, list):
        return {p: v for i, item in enumerate(value) for p, v in scope_leaves(item, prefix + "." + str(i)).items()}
    return {prefix: value}


RELATIONS = {"SUPPORTS", "REFUTES", "NOINFO"}
CHECK_ORIGINS = {"OFFLINE_CHECKER_RESULT", "SYNTHETIC_ENGINEERING_FIXTURE", "USER_MANUAL_REFERENCE"}


def _identity(value):
    return text_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def entailment_input(card, passage_ids, claim, applicability):
    indexed = {p["id"]:p for p in card.get("passages",[])}
    if not passage_ids or any(pid not in indexed for pid in passage_ids):
        raise ValueError("Entailment input needs existing primary passages")
    return {"source_id":card["id"],"source_sha256":card["source_document"]["sha256"],
            "source_version":card["identity"]["version"],"passage_ids":list(passage_ids),
            "premise":chr(10).join(indexed[pid]["quote"] for pid in passage_ids),
            "hypothesis":claim,"applicability":deepcopy(applicability),
            "correction_sha256s":[c["sha256"] for c in card["identity"].get("correction_chain",[])],
            "corrections":deepcopy(card["identity"].get("correction_chain",[]))}


def make_entailment_verification(card, passage_ids, claim, applicability, verifier, *,
                                verifier_id, verifier_revision, response_origin):
    """Explicit checker adapter. Never called by adjudicate; no built-in network.
    Caller freezes returned artifact before main judgment. Synthetic fixtures are
    identified as such; a separate model result is not expert/scientific truth.
    """
    audit = validate_cards([card])[card["id"]]
    if not audit["fulltext"]:
        raise ValueError("Entailment checker requires the versioned primary fulltext snapshot")
    if response_origin not in CHECK_ORIGINS or not verifier_id or not verifier_revision:
        raise ValueError("Explicit checker provenance required")
    data = entailment_input(card,passage_ids,claim,applicability)
    response = verifier(deepcopy(data))
    if not isinstance(response,dict) or response.get("relation") not in RELATIONS:
        raise ValueError("Checker must report SUPPORTS, REFUTES or NOINFO")
    artifact = {"input":data,"input_sha256":_identity(data),"relation":response["relation"],
                "raw_result":deepcopy(response),"verifier":{"id":verifier_id,"revision":verifier_revision,
                "response_origin":response_origin},"scientific_validation":"PENDING_USER_REFERENCE"}
    artifact["id"] = _identity(artifact)
    return artifact


def _checked_verification(check, card, passage_ids, claim, context):
    proofs = card.get("entailment_verifications",[])
    if not isinstance(proofs,list) or any(not isinstance(p,dict) for p in proofs):
        raise ValueError("Frozen entailment checks must be an array")
    proof = next((p for p in proofs if p.get("id") == check.get("verification_id")),None)
    if proof is None:
        return ["SEPARATE_ENTAILMENT_CHECK_UNBOUND"]
    if proof.get("id") != _identity({k:v for k,v in proof.items() if k != "id"}):
        raise ValueError("Frozen entailment artifact changed")
    data = entailment_input(card,passage_ids,claim,context)
    if proof.get("input") != data or proof.get("input_sha256") != _identity(data):
        return ["ENTAILMENT_CHECK_INPUT_MISMATCH"]
    verifier = proof.get("verifier",{})
    if not isinstance(verifier,dict):
        raise ValueError("Entailment verifier provenance must be an object")
    if (not verifier.get("id") or not verifier.get("revision")
            or verifier.get("response_origin") not in CHECK_ORIGINS):
        return ["ENTAILMENT_CHECK_PROVENANCE_UNBOUND"]
    if (not isinstance(proof.get("raw_result"),dict) or proof.get("relation") not in RELATIONS
            or proof["raw_result"].get("relation") != proof["relation"]):
        raise ValueError("Frozen entailment relation differs from raw checker result")
    if proof["relation"] != check["relation"]:
        return ["MAIN_PROPOSAL_DISAGREES_WITH_SEPARATE_ENTAILMENT_CHECK"]
    return []


def validate_cards(cards, source_documents=None):
    if not isinstance(cards, list):
        raise ValueError("Evidence cards must be an array")
    ids = [c.get("id") for c in cards if isinstance(c, dict)]
    if len(ids) != len(cards) or any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid/duplicate evidence identities")
    audits = {}
    for card in cards:
        if card.get("schema_version") not in {None, SCHEMA}:
            raise ValueError("Unknown evidence schema; explicit migration required")
        if card.get("schema_version") != SCHEMA:
            audits[card["id"]] = {"status": "LEGACY_METADATA_ONLY", "identity": False,
                                  "fulltext": False, "passages": {}, "guards": ["SOURCE_TEXT_UNBOUND"]}
            continue
        identity = card.get("identity", {})
        url = identity.get("url")
        if (not isinstance(url, str) or urlsplit(url).scheme not in {"https", "http"}
                or not urlsplit(url).hostname or not isinstance(identity.get("version"), str)
                or not identity["version"].strip()):
            raise ValueError("Versioned source identity required")
        document = card.get("source_document")
        if document is None and source_documents is not None:
            document = source_documents.get(card.get("document_id"))
        if not isinstance(document, dict) or not isinstance(document.get("text"), str):
            audits[card["id"]] = {"status": "UNRESOLVED", "identity": True,
                                  "fulltext": False, "passages": {}, "guards": ["SOURCE_TEXT_UNBOUND"]}
            continue
        text = document["text"]
        if document.get("sha256") != text_hash(text):
            raise ValueError("Fulltext snapshot hash mismatch")
        if document.get("version") != identity["version"] or document.get("url") != url:
            raise ValueError("Fulltext and cited source version/identity differ")
        passages = card.get("passages")
        if not isinstance(passages, list) or not passages:
            raise ValueError("Source locators must contain immutable passages")
        indexed = {}
        for passage in passages:
            pid = passage.get("id")
            if not isinstance(pid, str) or not pid or pid in indexed:
                raise ValueError("Invalid/duplicate passage ID")
            span = validate_span(text, {k: passage.get(k) for k in ("start", "end", "quote")})
            if passage.get("sha256") != span["quote_sha256"]:
                raise ValueError("Source passage hash mismatch")
            indexed[pid] = {**span, "id": pid}
        guards = []
        publication = identity.get("publication_status", "UNKNOWN")
        if publication not in {"CURRENT", "CORRECTED", "RETRACTED", "UNKNOWN"}:
            raise ValueError("Invalid publication/correction status")
        if publication in {"RETRACTED", "UNKNOWN"}:
            guards.append("SOURCE_PUBLICATION_STATUS_" + publication)
        corrections = identity.get("correction_chain", [])
        if not isinstance(corrections, list):
            raise ValueError("Correction chain must be an array")
        if publication == "CORRECTED" and not corrections:
            guards.append("CORRECTION_CHAIN_UNBOUND")
        for correction in corrections:
            if (not isinstance(correction, dict) or not isinstance(correction.get("text"), str)
                    or correction.get("sha256") != text_hash(correction["text"])
                    or not isinstance(correction.get("url"), str)
                    or not isinstance(correction.get("version"), str)):
                raise ValueError("Correction snapshot identity/hash missing")
        scope = card.get("applicability")
        scope_audits = {}
        if not isinstance(scope, dict) or not scope:
            guards.append("SOURCE_APPLICABILITY_UNBOUND")
        else:
            grounding = card.get("scope_support", {})
            if not isinstance(grounding, dict):
                raise ValueError("Source scope support must be an object")
            for path, item in scope_leaves(scope).items():
                if path not in grounding:
                    guards.append("SOURCE_SCOPE_FIELD_UNBOUND:" + path)
                    continue
                if item is None or type(item) is bool:
                    guards.append("SOURCE_SCOPE_FIELD_NOT_LITERAL:" + path)
                    continue
                audited = audit_field(str(item), grounding[path], text)
                scope_audits[path] = audited
                if audited["status"] != "GROUNDED":
                    guards.append("SOURCE_SCOPE_FIELD_INFERRED:" + path)
        audits[card["id"]] = {"status": "BOUND" if not guards else "UNRESOLVED", "identity": True,
                              "fulltext": True, "source_sha256": document["sha256"],
                              "source_version": identity["version"], "passages": indexed, "scope_audits": scope_audits,
                              "guards": guards, "publication_status": publication,
                              "origin_authentication": "SUPPLIED_SNAPSHOT_NOT_INDEPENDENTLY_AUTHENTICATED"}
    return audits


def _covered(actual, supported):
    if isinstance(supported, list):
        values = actual if isinstance(actual, list) else [actual]
        return bool(values) and all(item in supported for item in values)
    if isinstance(supported, dict) and {"min", "max", "unit"} <= set(supported):
        if not isinstance(actual, dict) or actual.get("unit") != supported["unit"]:
            return False
        low, high = actual.get("min", actual.get("value")), actual.get("max", actual.get("value"))
        numbers = (low, high, supported["min"], supported["max"])
        return (all(type(v) in {int, float} and math.isfinite(v) for v in numbers)
                and supported["min"] <= low <= high <= supported["max"])
    if isinstance(supported, dict):
        return (isinstance(actual, dict) and bool(actual)
                and all(key in supported and _covered(value, supported[key]) for key, value in actual.items()))
    return type(actual) is type(supported) and actual == supported


def check_scientific_support(record, requirement, cards, protocol):
    audits = validate_cards(cards)
    card_map = {c["id"]: c for c in cards}
    checks = record.get("evidence_checks", [])
    if not isinstance(checks, list):
        raise ValueError("Evidence checks must be an array")
    guards, details = [], []
    if not checks:
        return {"guards": ["ENTAILMENT_PROPOSAL_UNBOUND"], "checks": [], "certified_truth": False}
    expected_context = requirement.get("applicability")
    if not isinstance(expected_context, dict) or not expected_context:
        guards.append("REQUIREMENT_APPLICABILITY_UNBOUND")
    required_fields = requirement.get("protocol_fields", [])
    if not isinstance(required_fields, list) or any(not isinstance(f, str) for f in required_fields):
        raise ValueError("Protocol applicability field names invalid")
    desired_relation = "SUPPORTS" if record["status"] == "SATISFIED" else "REFUTES"
    valid_relation = False
    for check in checks:
        if not isinstance(check, dict) or check.get("relation") not in RELATIONS:
            raise ValueError("Evidence relation needs SUPPORTS, REFUTES or NOINFO")
        source_id = check.get("source_id")
        if source_id not in record["evidence_ids"] or source_id not in card_map:
            raise ValueError("Evidence check references an unbound source")
        card, audit, local = card_map[source_id], audits[source_id], []
        local.extend(audit["guards"])
        if source_id not in requirement.get("evidence_ids", []):
            local.append("SOURCE_OUTSIDE_REQUIREMENT_SCOPE")
        if check.get("claim") != requirement["text"]:
            local.append("ENTAILMENT_CLAIM_DIFFERS_FROM_REQUIREMENT")
        pids = check.get("passage_ids")
        if not isinstance(pids, list) or not pids or any(pid not in audit["passages"] for pid in pids):
            local.append("ENTAILMENT_SOURCE_RATIONALE_UNBOUND")
        else:
            if len(pids) != len(set(pids)):
                raise ValueError("Duplicate citation passage")
            selected = [audit["passages"][pid] for pid in pids]
            for field, field_audit in audit.get("scope_audits", {}).items():
                if not all(any(p["start"] <= span["start"] < span["end"] <= p["end"] for p in selected)
                           for span in field_audit["spans"]):
                    local.append("SOURCE_SCOPE_OUTSIDE_CITED_RATIONALE:" + field)
        context = check.get("applicability")
        if not isinstance(context, dict) or not context or context != expected_context:
            local.append("APPLICABILITY_DIFFERS_FROM_REQUIREMENT")
        elif (not isinstance(card.get("applicability"), dict)
              or not all(k in card["applicability"] and _covered(v, card["applicability"][k]) for k, v in context.items())):
            local.append("SOURCE_OBJECT_VERSION_SIZE_OR_CONDITIONS_MISMATCH")
        bindings = check.get("protocol_bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("Protocol bindings must be an object")
        for field in required_fields:
            binding = bindings.get(field)
            if not isinstance(binding, dict) or field not in (context or {}):
                local.append("PROTOCOL_APPLICABILITY_FIELD_UNBOUND:" + field)
                continue
            actual = context[field]
            if not isinstance(actual, str) or binding.get("value") != actual:
                local.append("PROTOCOL_APPLICABILITY_FIELD_DIFFERS:" + field)
                continue
            field_audit = audit_field(actual, binding.get("support"), protocol)
            if field_audit["status"] != "GROUNDED":
                local.append("PROTOCOL_APPLICABILITY_FIELD_INFERRED:" + field)
        if check["relation"] != desired_relation:
            local.append("EVIDENCE_RELATION_DOES_NOT_SUPPORT_DECISION")
        if isinstance(pids,list) and pids and all(pid in audit["passages"] for pid in pids):
            local.extend(_checked_verification(check,card,pids,requirement["text"],context))
        if card.get("identity", {}).get("publication_status") == "CORRECTED":
            expected = [c["sha256"] for c in card["identity"].get("correction_chain", [])]
            if check.get("correction_sha256s") != expected:
                local.append("ENTAILMENT_OMITS_CORRECTION_CHAIN")
        if not local:
            valid_relation = True
        details.append({"source_id": source_id, "relation": check["relation"], "claim": check.get("claim"),
                        "passage_ids": deepcopy(pids), "applicability": deepcopy(context), "guards": local,
                        "verification_id":check.get("verification_id"),
                        "semantic_status": "SEPARATE_CHECKER_RESULT_NOT_INDEPENDENT_SCIENTIFIC_TRUTH"})
    # Invalid additional evidence remains visible and cannot silently be ignored.
    guards.extend(g for detail in details for g in detail["guards"])
    if not valid_relation:
        guards.append("NO_BOUND_APPLICABLE_ENTAILMENT_PROPOSAL")
    return {"guards": sorted(set(guards)), "checks": details, "certified_truth": False,
            "scope": "Source presence, declared applicability and explicit relation proposal; scientific validity pending user review"}


