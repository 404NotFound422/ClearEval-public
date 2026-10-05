"""Deterministic OEQ workflow sidecars; data integrity is not scientific truth.

This module never calls a judge, changes scores, infers measured objectives,
or certifies complete candidate boundaries from prose. Build errors are visible
ValueErrors for the caller to persist as technical failures.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

import oeq_scientific
from experiments.construct_validity import objectives, source_conditions, task_state
from experiments.construct_validity import task_function_presence
from experiments.construct_validity.contract import digest, parse_json, validate_requirements
from experiments.construct_validity.fidelity import text_hash

VERSION = "oeq-workflow-diagnostics-v1"
INPUT_BINDING_VERSION = "oeq-workflow-input-binding-v1"
ROOT = Path(__file__).resolve().parent
_HASH = re.compile(r"[0-9a-f]{64}")
_RESOURCE_PATHS = (
    "KnowledgeBase/source_registry.json",
    "KnowledgeBase/source_condition_rules.json",
    "KnowledgeBase/method_ri_ref.json",
)


def _is_hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _validate_json(value):
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Diagnostic inputs require string JSON object keys")
        for item in value.values():
            _validate_json(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("Diagnostic inputs must be JSON values")
    digest(value)  # Reject NaN, infinity, and invalid Unicode without rewriting.


def _validate_inputs(question_meta, protocol):
    if not isinstance(question_meta, dict):
        raise ValueError("Original question metadata must be an object")
    question_text = question_meta.get("question", question_meta.get("text"))
    if not isinstance(question_text, str) or not question_text.strip():
        raise ValueError("Original nonempty question text is required")
    if not isinstance(protocol, str) or not protocol.strip():
        raise ValueError("Original nonempty protocol text is required")
    _validate_json(question_meta)
    text_hash(protocol)
    return question_text


def _dependency_versions():
    return {
        "scientific_context": oeq_scientific.VERSION,
        "task_state": task_state.VERSION,
        "task_function_presence": task_function_presence.VERSION,
        "source_conditions": source_conditions.VERSION,
        "objective_relations": objectives.VERSION,
    }


def _implementation_hashes():
    paths = {
        "oeq_workflow_diagnostics.py": Path(__file__),
        "oeq_scientific.py": Path(oeq_scientific.__file__),
        "experiments/construct_validity/task_state.py": Path(task_state.__file__),
        "experiments/construct_validity/task_function_presence.py": Path(task_function_presence.__file__),
        "experiments/construct_validity/source_conditions.py": Path(source_conditions.__file__),
        "experiments/construct_validity/objectives.py": Path(objectives.__file__),
    }
    for name in (
        "evaluator_integrity.py",
        "oeq_quantity_audit.py",
        "extract_clearing_time.py",
        "experiments/construct_validity/contract.py",
        "experiments/construct_validity/evidence.py",
        "experiments/construct_validity/fidelity.py",
        "experiments/construct_validity/compact_grounding.py",
        "experiments/construct_validity/requirement_scope.py",
        "experiments/construct_validity/candidate_binding.py",
        "experiments/construct_validity/answer_matching.py",
    ):
        paths[name] = ROOT / name
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def _resources(workspace):
    bindings, values = {}, {}
    for name in _RESOURCE_PATHS:
        path = (workspace / name).resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            raise ValueError("Workflow diagnostic resource missing or outside workspace: " + name)
        data = path.read_bytes()
        bindings[name] = hashlib.sha256(data).hexdigest()
        values[name] = parse_json(data.decode("utf-8-sig"))
        if not isinstance(values[name], dict):
            raise ValueError("Workflow diagnostic resource must be a JSON object: " + name)
    registry = values[_RESOURCE_PATHS[0]]
    methods = values[_RESOURCE_PATHS[2]].get("ri_ref")
    if not isinstance(methods, dict) or not methods:
        raise ValueError("Versioned method reference inventory required")
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list) or not registry["sources"]:
        raise ValueError("Nonempty frozen source registry required")
    sources, seen = {}, set()
    metadata_only = []
    for source in registry["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Registered source must be an object")
        sid, identity = source.get("id"), source.get("identity")
        if not isinstance(sid, str) or not sid or sid in seen or not isinstance(identity, dict):
            raise ValueError("Invalid or duplicate registered source identity")
        seen.add(sid)
        if not isinstance(identity.get("version"), str) or not identity["version"].strip():
            raise ValueError("Registered source version required")
        snapshot = source.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            raise ValueError("Registered source snapshot must be an object")
        relative = snapshot.get("text_path")
        if not relative:
            if source.get("passages"):
                raise ValueError("Registered evidence passages have no fulltext snapshot: " + sid)
            metadata_only.append({
                "id": sid, "version": identity["version"],
                "status": "METADATA_ONLY_NOT_SOURCE_EVIDENCE",
                "registered_source_sha256": digest(source),
            })
            continue
        if not isinstance(relative, str) or not isinstance(source.get("passages"), list) or not source["passages"]:
            raise ValueError("Declared source snapshot needs frozen passages: " + sid)
        path = (workspace / relative).resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            raise ValueError("Source snapshot missing or outside workspace: " + sid)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if not _is_hash(snapshot.get("text_sha256")) or actual != snapshot["text_sha256"]:
            raise ValueError("Source snapshot hash mismatch: " + sid)
        name = path.relative_to(workspace).as_posix()
        bindings[name] = actual
        sources[sid] = (source, name)
    if not sources:
        raise ValueError("No frozen fulltext source evidence available")
    return bindings, sources, metadata_only


def _unresolved_objectives():
    return {
        "status": "U",
        "relationship": "UNRESOLVED",
        "measurements": None,
        "constraints": None,
        "no_hard_constraints_declared": None,
        "reasons": [
            "TYPED_AUDITED_OBJECTIVE_MEASUREMENTS_NOT_SUPPLIED",
            "HARD_CONSTRAINT_CONTRACT_NOT_AUDITED",
            "COMPLETE_CANDIDATE_BOUNDARIES_NOT_AUDITED",
            "SAME_SCENARIO_AND_MEASUREMENT_BASIS_NOT_AUDITED",
        ],
        "policy": "NO_LEGACY_CCE_AS_MEASUREMENT_NO_IMPLICIT_NUMERIC_EXTRACTION",
    }


def _unresolved_candidate():
    return {
        "status": "U",
        "complete_candidate_boundaries": None,
        "necessary_requirements_satisfied": None,
        "reasons": [
            "COMPLETE_CANDIDATE_BOUNDARIES_NOT_AUDITED",
            "PROVISIONAL_R_CONTRACTS_NOT_ADJUDICATED",
            "NO_AUDITED_EXTRACTION_OR_REQUIREMENT_EVIDENCE_SUPPLIED",
        ],
        "policy": "NO_KEYWORD_OR_SINGLE_STEP_PROOF_OF_COMPLETE_CANDIDATE",
    }


def build_workflow_diagnostics(question_meta, protocol, workspace=None):
    """Build a compact sidecar using existing deterministic scientific audits.

    Provisional task applicability and local source warnings remain useful
    diagnostics. Scientific quality, objectives, and full candidate sufficiency
    remain U until independent typed inputs and assessments are supplied.
    """
    try:
        question_text = _validate_inputs(question_meta, protocol)
        workspace = Path(workspace or ROOT).resolve()
        bindings, registered, metadata_only = _resources(workspace)
        context = oeq_scientific.build_context(question_meta, protocol, workspace)
        question_sha, protocol_sha = digest(question_meta), text_hash(protocol)
        if context.get("question_sha256") != question_sha or context.get("protocol_sha256") != protocol_sha:
            raise ValueError("Scientific context input binding mismatch")
        cards = context.get("audit_cards")
        if not isinstance(cards, list) or not cards:
            raise ValueError("Scientific source inventory unavailable")
        selected = set(context["retrieval"]["selected_source_ids"])
        inventory = []
        for card in cards:
            sid = card["id"]
            if sid not in registered:
                raise ValueError("Scientific card not in frozen source registry")
            source, name = registered[sid]
            inventory.append({
                "id": sid, "version": card["identity"]["version"],
                "source_sha256": card["source_document"]["sha256"],
                "snapshot_path": name, "snapshot_file_sha256": bindings[name],
                "card_sha256": digest(card), "registered_source_sha256": digest(source),
                "selected": sid in selected, "method": card.get("method"),
            })
        if len({row["id"] for row in inventory}) != len(inventory) or set(registered) != {row["id"] for row in inventory}:
            raise ValueError("Frozen fulltext source inventory incomplete or duplicate")
        inventory.sort(key=lambda row: row["id"])
        requirements = deepcopy(context["requirements"])
        validate_requirements(requirements)
        function_diagnostics = []
        for requirement in requirements:
            rule = requirement.get("literal_rule")
            if isinstance(rule, dict) and rule.get("type") == "TASK_INITIAL_FUNCTION":
                function_diagnostics.append({
                    "requirement_id": requirement["id"],
                    "diagnostic": task_function_presence.assess_required_function(
                        rule, None, protocol, None),
                })
        conditions = deepcopy(context["source_condition_diagnostics"])
        if conditions.get("protocol_sha256") != protocol_sha:
            raise ValueError("Source condition diagnostic input binding mismatch")
        if conditions.get("rules_file_sha256") != bindings["KnowledgeBase/source_condition_rules.json"]:
            raise ValueError("Source condition rules changed during workflow audit")
        for name, expected_hash in bindings.items():
            if hashlib.sha256((workspace / name).read_bytes()).hexdigest() != expected_hash:
                raise ValueError("Workflow source resources changed during audit: " + name)
        versions, implementation = _dependency_versions(), _implementation_hashes()
        binding = {
            "schema_version": INPUT_BINDING_VERSION,
            "question_sha256": question_sha, "protocol_sha256": protocol_sha,
            "resource_binding_sha256": digest(bindings),
            "source_inventory_sha256": digest(inventory),
            "implementation_sha256": digest(implementation),
            "dependency_versions_sha256": digest(versions),
        }
        result = {
            "schema_version": VERSION, "technical_status": "VALID",
            "scientific_status": "U",
            "question_sha256": question_sha, "question_text_sha256": text_hash(question_text),
            "protocol_sha256": protocol_sha, "input_binding": binding,
            "origin": "DETERMINISTIC_PROVISIONAL_WORKFLOW_DIAGNOSTICS",
            "scientific_context_version": context["schema_version"],
            "scientific_context_sha256": context["context_sha256"],
            "dependency_versions": versions, "implementation_hashes": implementation,
            "provisional_r_contracts": requirements,
            "task_state_audit": deepcopy(context["task_state_audit"]),
            "task_function_diagnostics": function_diagnostics,
            "source_condition_diagnostics": conditions,
            "source_inventory": inventory,
            "metadata_only_source_inventory": metadata_only,
            "source_inventory_sha256": digest(inventory),
            "resource_bindings": bindings, "resource_binding_sha256": digest(bindings),
            "source_retrieval": {key: deepcopy(value) for key, value in context["retrieval"].items()
                                 if key != "source_inventory"},
            "candidate_necessity_diagnostics": _unresolved_candidate(),
            "objective_diagnostics": _unresolved_objectives(),
            "scientific_gold": None, "expert_consistency": None,
            "wet_lab_success": None,
            "interpretation": "TECHNICAL_COMPLETION_IS_NOT_SCIENTIFIC_CERTIFICATION",
        }
        result["diagnostics_sha256"] = digest(result)
        return result
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError("Cannot build workflow diagnostics: " + str(error)) from error



_SCIENTIFIC_FLAGS = {
    "scientific_gold", "scientific_truth", "scientific_validation",
    "independent_scientific_truth", "expert_consistency", "expert_agreement",
    "wet_lab_success", "scientific_accuracy", "scientific_success",
    "scientific_certified", "certified_scientific_truth", "certified_truth",
}


def _scientific_flags_are_unset(value):
    if isinstance(value, dict):
        return all(
            (key not in _SCIENTIFIC_FLAGS or item is None)
            and _scientific_flags_are_unset(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_scientific_flags_are_unset(item) for item in value)
    return True


def _task_audit_is_consistent(state, requirements, question_sha, text_sha):
    if (state.get("provisional") is not True
            or state.get("scientific_gold", True) is not None):
        return False
    audits, task_requirements = state.get("functions"), state.get("requirements")
    if not isinstance(audits, dict) or set(audits) != set(task_state.FUNCTIONS):
        return False
    if not isinstance(task_requirements, list):
        return False
    contract_map = {r["id"]: r for r in requirements}
    expected_ids = set()
    for name, audit in audits.items():
        if (not isinstance(audit, dict) or audit.get("function") != name
                or audit.get("provisional") is not True
                or audit.get("scientific_truth", True) is not None
                or audit.get("question_sha256") != question_sha
                or audit.get("question_text_sha256") != text_sha):
            return False
        if audit.get("mention_status") == "NOT_MENTIONED":
            continue
        rid = "TASK_INITIAL_FUNCTION_" + name
        expected_ids.add(rid)
        requirement = contract_map.get(rid)
        if (not isinstance(requirement, dict)
                or requirement.get("function") != name
                or requirement.get("necessity_status") != audit.get("execution_obligation")
                or requirement.get("applicability_status") != audit.get("applicability_status")
                or requirement.get("necessary") is not (audit.get("execution_obligation") != "NOT_REQUIRED")
                or requirement.get("literal_rule") != {
                    "type": "TASK_INITIAL_FUNCTION", "function": name,
                    "state_audit": audit,
                }):
            return False
    if (len(task_requirements) != len(expected_ids)
            or {r["id"] for r in task_requirements} != expected_ids
            or any(r != contract_map.get(r["id"]) for r in task_requirements)):
        return False
    contract_ids = {r["id"] for r in requirements
                    if isinstance(r.get("literal_rule"), dict)
                    and r["literal_rule"].get("type") == "TASK_INITIAL_FUNCTION"}
    return contract_ids == expected_ids

def is_workflow_diagnostics_complete(diag, question_meta=None, protocol=None):
    """Validate artifact integrity/completion, never certify scientific quality.

    This unkeyed digest does not authenticate externally rewritten artifacts.
    Callers must rebuild from original inputs/current resources before trusting
    cache contents, rather than accepting a self-rehashed external replacement.
    """
    try:
        if not isinstance(diag, dict) or diag.get("schema_version") != VERSION:
            return False
        if not _scientific_flags_are_unset(diag):
            return False
        if diag.get("technical_status") != "VALID" or diag.get("scientific_status") != "U":
            return False
        frozen = {key: value for key, value in diag.items() if key != "diagnostics_sha256"}
        if digest(frozen) != diag.get("diagnostics_sha256"):
            return False
        if diag.get("dependency_versions") != _dependency_versions() or diag.get("implementation_hashes") != _implementation_hashes():
            return False
        if diag.get("scientific_context_version") != oeq_scientific.VERSION or not _is_hash(diag.get("scientific_context_sha256")):
            return False
        for key in ("question_sha256", "question_text_sha256", "protocol_sha256"):
            if not _is_hash(diag.get(key)):
                return False
        if question_meta is not None:
            text = _validate_inputs(question_meta, protocol if protocol is not None else "binding-check")
            if digest(question_meta) != diag["question_sha256"] or text_hash(text) != diag["question_text_sha256"]:
                return False
        if protocol is not None and (not isinstance(protocol, str) or not protocol.strip() or text_hash(protocol) != diag["protocol_sha256"]):
            return False
        inventory, resources = diag.get("source_inventory"), diag.get("resource_bindings")
        if not isinstance(inventory, list) or not inventory or not isinstance(resources, dict):
            return False
        ids = set()
        for source in inventory:
            if (not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]
                    or source["id"] in ids or not isinstance(source.get("version"), str) or not source["version"]
                    or type(source.get("selected")) is not bool
                    or any(not _is_hash(source.get(key)) for key in ("source_sha256", "snapshot_file_sha256", "card_sha256", "registered_source_sha256"))
                    or resources.get(source.get("snapshot_path")) != source["snapshot_file_sha256"]):
                return False
            ids.add(source["id"])
        if (any(name not in resources for name in _RESOURCE_PATHS)
                or any(not isinstance(name, str) or not _is_hash(value) for name, value in resources.items())
                or digest(inventory) != diag.get("source_inventory_sha256")
                or digest(resources) != diag.get("resource_binding_sha256")):
            return False
        expected_binding = {
            "schema_version": INPUT_BINDING_VERSION,
            "question_sha256": diag["question_sha256"], "protocol_sha256": diag["protocol_sha256"],
            "resource_binding_sha256": digest(resources), "source_inventory_sha256": digest(inventory),
            "implementation_sha256": digest(diag["implementation_hashes"]),
            "dependency_versions_sha256": digest(diag["dependency_versions"]),
        }
        if diag.get("input_binding") != expected_binding:
            return False
        requirements = diag.get("provisional_r_contracts")
        validate_requirements(requirements)
        state, conditions = diag.get("task_state_audit"), diag.get("source_condition_diagnostics")
        if (not isinstance(state, dict) or state.get("schema_version") != task_state.VERSION
                or state.get("question_sha256") != diag["question_sha256"]
                or state.get("question_text_sha256") != diag["question_text_sha256"]
                or not isinstance(conditions, dict) or conditions.get("version") != source_conditions.VERSION
                or conditions.get("scientific_validation", True) is not None
                or conditions.get("independent_scientific_truth", True) is not None
                or conditions.get("protocol_sha256") != diag["protocol_sha256"]
                or conditions.get("rules_file_sha256") != resources["KnowledgeBase/source_condition_rules.json"]
                or conditions.get("absence_of_warning_interpretation") != "NO_WARNING_IS_NOT_SCIENTIFIC_COMPLIANCE_OR_SUCCESS"
                or not isinstance(conditions.get("findings"), list)
                or not isinstance(conditions.get("rule_audits"), list)
                or any(f.get("changes_requirement_states") is not False for f in conditions["findings"])):
            return False
        if not _task_audit_is_consistent(state, requirements, diag["question_sha256"], diag["question_text_sha256"]):
            return False
        if (diag.get("objective_diagnostics") != _unresolved_objectives()
                or diag.get("candidate_necessity_diagnostics") != _unresolved_candidate()
                or any(diag.get(key, True) is not None for key in ("scientific_gold", "expert_consistency", "wet_lab_success"))):
            return False
        functions = diag.get("task_function_diagnostics")
        required_functions = {r["id"] for r in requirements
                              if isinstance(r.get("literal_rule"), dict)
                              and r["literal_rule"].get("type") == "TASK_INITIAL_FUNCTION"}
        if (not isinstance(functions, list) or len(functions) != len(required_functions)
                or {f["requirement_id"] for f in functions} != required_functions):
            return False
        contract_map = {r["id"]: r for r in requirements}
        for function in functions:
            rule = contract_map[function["requirement_id"]]["literal_rule"]
            # With no extraction/fidelity this API exits before inspecting any
            # protocol operation. Only the protocol hash needs restoration when
            # the caller supplies no original text.
            expected = task_function_presence.assess_required_function(
                rule, None, protocol if protocol is not None else "binding-check", None)
            expected["protocol_sha256"] = diag["protocol_sha256"]
            if function["diagnostic"] != expected:
                return False
        return True
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError, ValueError):
        return False
