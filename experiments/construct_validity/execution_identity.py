"""Identity of actual visible inputs and independently executed attempts.

A response replay/cache is useful engineering evidence, never a new repetition.
All fields are stable hashes; invocation identity is recorded separately.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from .contract import digest

VERSION = "execution-identity-v2"
PRIVATE_KEYS = {"private", "private_mapping", "control_expectations", "expected_judgment",
                "expert_ratings", "expert_labels", "gold_labels", "hidden_labels"}


def assert_public(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in PRIVATE_KEYS:
                raise ValueError("Private reference cannot enter actual visible input: " + key)
            assert_public(item)
    elif isinstance(value, list):
        for item in value:
            assert_public(item)


def public_context(material, protocol, phase="judge"):
    if phase == "extract":
        data = {"PROTOCOL": protocol}
    else:
        data = {"TASK": material["question"], "REQUIREMENTS": deepcopy(material["requirements"]),
                "PROTOCOL": protocol, "EVIDENCE_CARDS": deepcopy(material["cards"])}
    assert_public(data)
    return data


def information_hash(payload):
    """Ignore judge identity/options, retain exactly the visible messages and format."""
    assert_public(payload["messages"])
    return digest({"messages": payload["messages"], "format": payload.get("format")})


def execution_identity(payload, material, protocol, manifest, job):
    return {
        "schema_version": VERSION,
        "payload_sha256": digest(payload),
        "visible_information_sha256": information_hash(payload),
        "phase": job["phase"],
        "bindings": {
            "question_sha256": digest(material.get("question")),
            "protocol_sha256": digest(protocol),
            "requirements_sha256": digest(material.get("requirements", [])),
            "evidence_sha256": digest(material.get("cards", [])),
            "resource_sha256": digest(material.get("resource_list", {})),
            "frozen_files_sha256": digest(manifest.get("files", {})),
        },
        "judge": {"provider": manifest.get("provider", "ollama-loopback"),
                  "model": payload["model"], "revision": manifest["model_digest"],
                  "family": manifest.get("model_family", "UNDECLARED")},
        "sampling_sha256": digest(payload.get("options", {})),
    }


def verify_saved_request(request, result, expected_payload, expected_identity, endpoint):
    if request.get("endpoint") != endpoint:
        raise ValueError("Stored request endpoint differs from frozen endpoint")
    if request.get("payload") != expected_payload:
        raise ValueError("Stored request differs from reconstructed actual input")
    if request.get("payload_sha256") != digest(expected_payload):
        raise ValueError("Stored request self-hash differs")
    if result.get("payload_sha256") != request["payload_sha256"]:
        raise ValueError("Result is not bound to actual request")
    if request.get("execution_identity") != expected_identity:
        raise ValueError("Missing or different execution identity")
    if result.get("execution_identity_sha256") != digest(expected_identity):
        raise ValueError("Result execution identity differs")
    if result.get("model_digest") != expected_identity["judge"]["revision"]:
        raise ValueError("Result judge revision differs from frozen judge")


def repeat_diagnostic(records, planned):
    """Describe all outcomes. Scientific stability needs >=2 uncached live attempts."""
    if type(planned) is not int or planned < 1 or len(records) > planned:
        raise ValueError("Invalid planned repeat count")
    attempted = [r for r in records if r.get("status") != "NOT_ATTEMPTED"]
    live = [r for r in attempted if r.get("status") == "COMPLETE"
            and r.get("execution_origin") == "LIVE" and r.get("response_cache_hit") is False]
    invocation_ids = [r.get("invocation_id") for r in live]
    independent = bool(live) and all(isinstance(i, str) and i for i in invocation_ids)
    independent = independent and len(set(invocation_ids)) == len(invocation_ids)
    hashes = [r.get("payload_sha256") for r in attempted]
    visible_hashes = [r.get("visible_information_sha256") for r in attempted]
    payloads_fixed = len(attempted) >= 2 and all(hashes) and len(set(hashes)) == 1
    visible_fixed = len(attempted) >= 2 and all(visible_hashes) and len(set(visible_hashes)) == 1
    ready = len(live) >= 2 and independent and payloads_fixed and visible_fixed
    return {"planned": planned, "attempted": len(attempted),
            "technical_complete": sum(r.get("status") == "COMPLETE" for r in attempted),
            "independent_live_complete": len(live) if independent else 0,
            "all_planned_complete": len(live) == planned and independent,
            "identical_payloads": payloads_fixed if len(attempted) >= 2 else None,
            "identical_visible_information": visible_fixed if len(attempted) >= 2 else None,
            "failure_statuses": dict(Counter(r.get("status") for r in attempted if r.get("status") != "COMPLETE")),
            "execution_origins": dict(Counter(r.get("execution_origin", "UNDECLARED") for r in attempted)),
            "response_cache_hits": sum(r.get("response_cache_hit") is True for r in attempted),
            "repetition_status": "DESCRIPTIVE_INDEPENDENT_REPETITIONS" if ready else "NOT_ESTIMABLE",
            "scientific_validation": "PENDING_USER_EXPERT",
            "interpretation": "Technical failures retained; fixed mock/replay/cache is not model stability"}


def compare_judge_inputs(a, b):
    """Check equal actual information and declared distinct judge families."""
    fixed = a.get("visible_information_sha256") == b.get("visible_information_sha256")
    fixed = fixed and bool(a.get("visible_information_sha256"))
    ja, jb = a.get("judge", {}), b.get("judge", {})
    families = [ja.get("family"), jb.get("family")]
    declared = all(f and f != "UNDECLARED" for f in families)
    sampling_fixed = bool(a.get("sampling_sha256")) and a.get("sampling_sha256") == b.get("sampling_sha256")
    return {"same_visible_information": fixed, "same_sampling_configuration": sampling_fixed,
            "different_declared_families": declared and families[0] != families[1],
            "controlled_comparison_ready": fixed and sampling_fixed and declared and families[0] != families[1],
            "judge_configs": [ja, jb], "scientific_comparison_performed": False}
