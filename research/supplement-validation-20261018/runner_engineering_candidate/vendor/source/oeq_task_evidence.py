"""Fixed question/route evidence input for SR grading, independent of candidates.

This is a loading and projection boundary, not a scientific evidence generator.
It reuses construct_validity source cards/requirements and the existing SR
inventory. Source snapshots, explicit applicability, and reported instances are
retained without promoting them to scientific constraints or expert approval.
No candidate text, retrieval, model call, or output-score formula belongs here.
"""
from copy import deepcopy

from evaluation_contract import json_hash, sha256_file
from experiments.construct_validity.contract import read, validate_requirements, evaluate_formula
from experiments.construct_validity.evidence import validate_cards, _covered
from experiments.construct_validity.fidelity import validate_span
from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import freeze_inventory

SCHEMA = "fixed-task-evidence-v1"
PROJECTION_SCHEMA = "fixed-task-evidence-projection-v2-target-responsibilities"
HASH_FORMAT = "canonical-json-sha256-v1"
CORRECTNESS_METRICS = ("co_order", "co_method", "co_param", "co_chem")
METRICS = ("c_param",) + CORRECTNESS_METRICS
REFERENCE_ROLES = {"REPORTED_INSTANCE", "CONSTRAINT"}
BINDING_SCOPE = "FIXED_INPUT_BINDING_ONLY_NOT_SCIENTIFIC_CERTIFICATION"


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(name + " must be an object")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be nonempty text")
    return value


def _ids(value, name, allowed=None):
    if not isinstance(value, list):
        raise ValueError(name + " must be an explicit array")
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(name + " contains duplicate IDs")
    if allowed is not None and not set(value) <= set(allowed):
        raise ValueError(name + " references an unknown ID")
    return value


def _finite_copy(value):
    try:
        json_hash(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Task evidence must contain finite JSON data") from exc
    return deepcopy(value)


def _role(record, name):
    role = record.get("reference_role")
    if role is not None and (not isinstance(role, str) or role not in REFERENCE_ROLES):
        raise ValueError(name + ".reference_role must be REPORTED_INSTANCE or CONSTRAINT")


def _passage_bindings(record, source_ids, cards, name):
    """Missing locations remain missing; supplied invalid locations are errors."""
    bindings = record.get("passage_ids", {})
    _object(bindings, name + ".passage_ids")
    if not set(bindings) <= set(source_ids):
        raise ValueError(name + " binds passages outside its declared sources")
    for sid, pids in bindings.items():
        passages = cards[sid].get("passages") or []
        if not isinstance(passages, list) or any(not isinstance(p, dict) or "id" not in p for p in passages):
            raise ValueError(name + " source passage definitions must be records with IDs")
        available = [p["id"] for p in passages]
        _ids(pids, name + ".passage_ids." + sid, available)


def _validate_route(route, route_id, requirements, cards):
    _object(route, "route")
    checks = _object(route.get("correctness_checks", {}), "correctness_checks")
    if not set(checks) <= set(CORRECTNESS_METRICS):
        raise ValueError("Unknown correctness metric")
    linked = []
    for metric, ids in checks.items():
        linked += _ids(ids, "correctness_checks." + metric, requirements)
    linked += _ids(route.get("parameter_requirements", []), "parameter_requirements", requirements)
    submetrics = _object(route.get("submetrics", {}), "submetrics")
    if not set(submetrics) <= set(METRICS):
        raise ValueError("Unknown submetric parent metric")
    for metric, groups in submetrics.items():
        _object(groups, "submetrics." + metric)
        for name, ids in groups.items():
            _text(name, "submetric name")
            linked += _ids(ids, "submetric requirement IDs", requirements)
    for rid in linked:
        req = requirements[rid]
        if req.get("scope", "GLOBAL") == "ROUTE" and req["route_id"] != route_id:
            raise ValueError("Metric requirement belongs to another route: " + rid)
    inventory = route.get("sr_inventory")
    if inventory is None:
        return
    freeze_inventory(inventory)
    if inventory["route_id"] != route_id:
        raise ValueError("Inventory route differs from selected fixed route")
    source_ids = {s["source_id"] for s in inventory["sources"]}
    if not source_ids <= set(cards):
        raise ValueError("Inventory references an unknown source card")
    for collection in ("reference_steps", "required_stages", "required_transitions"):
        for row in inventory[collection]:
            _role(row, collection)
            _passage_bindings(row, row["source_ids"], cards, collection)
            if collection == "reference_steps":
                _text(row.get("text"), "reference step text")
                origin = row.get("text_origin")
                if origin is not None and origin not in ("EXPLICIT", "DERIVED"):
                    raise ValueError("reference text_origin must be EXPLICIT or DERIVED")
            if "requirement_ids" in row:
                _ids(row["requirement_ids"], collection + ".requirement_ids", requirements)
                for rid in row["requirement_ids"]:
                    req = requirements[rid]
                    if req.get("scope", "GLOBAL") == "ROUTE" and req["route_id"] != route_id:
                        raise ValueError("Inventory requirement belongs to another route")


def validate_task_evidence(task):
    """Validate a fixed task, returning a detached copy, without choosing a route.

    Required task fields: schema_version, question_id, question, cards,
    requirements, routes. Each route retains an optional sr_inventory and fixed
    correctness_checks, parameter_requirements, and submetrics ID references.
    Empty/missing evidence is allowed and projects to explicit UNRESOLVED gates.
    Reference-step display text is not a source quotation by default. Optional
    text_origin=DERIVED preserves normalized/paraphrased text and its original
    cited passage spans without claiming semantic entailment. EXPLICIT declares
    literal source wording; only that declaration is checked for literal match.
    Inventory stage/transition REPORTED_INSTANCE roles support reference coverage
    only. They do not authorize scientific CONSTRAINT checks or certify necessity.
    """
    task = _finite_copy(_object(task, "task evidence"))
    if task.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported fixed task evidence schema")
    if isinstance(task.get("question_id"), bool) or not isinstance(task.get("question_id"), (str, int)):
        raise ValueError("question_id must be a string or integer")
    _text(str(task["question_id"]), "question_id")
    _text(task.get("question"), "question")
    # Candidate material has no input slot in this independently frozen object.
    if any(k in task for k in ("protocol", "candidate", "candidate_text", "model_protocol")):
        raise ValueError("Candidate text cannot be a fixed external evidence input")
    cards = task.get("cards")
    validate_cards(cards)
    card_map = {c["id"]: c for c in cards}
    requirements = task.get("requirements")
    if not isinstance(requirements, list):
        raise ValueError("requirements must be an explicit array")
    if requirements:
        validate_requirements(requirements)
    req_map = {r["id"]: r for r in requirements}
    if task.get("formula") is not None:
        evaluate_formula(task["formula"], {rid: "SATISFIED" for rid in req_map})
    for req in requirements:
        _role(req, "requirement")
        _ids(req.get("evidence_ids", []), "requirement.evidence_ids", card_map)
        _passage_bindings(req, req.get("evidence_ids", []), card_map, "requirement")
        if "question_span" in req:
            validate_span(task["question"], req["question_span"])
    routes = _object(task.get("routes"), "routes")
    for route_id, route in routes.items():
        _text(route_id, "route ID")
        _validate_route(route, route_id, req_map, card_map)
    for req in requirements:
        if req.get("scope", "GLOBAL") == "ROUTE" and req["route_id"] not in routes:
            raise ValueError("Requirement references an unknown route")
    return task


def _source_guards(record, source_ids, cards, audits, *, require_scope):
    guards = []
    if not source_ids:
        guards.append("SOURCE_EVIDENCE_MISSING")
    context = record.get("applicability")
    if require_scope and (not isinstance(context, dict) or not context):
        guards.append("REQUIREMENT_APPLICABILITY_UNBOUND")
    for sid in source_ids:
        audit = audits[sid]
        guards.extend(sid + ":" + guard for guard in audit["guards"])
        pids = record.get("passage_ids", {}).get(sid, [])
        if not pids:
            guards.append("SOURCE_PASSAGES_UNBOUND:" + sid)
        if isinstance(context, dict) and context:
            scope = cards[sid].get("applicability", {})
            if not all(k in scope and _covered(v, scope[k]) for k, v in context.items()):
                guards.append("SOURCE_APPLICABILITY_MISMATCH:" + sid)
            selected = [audit["passages"][pid] for pid in pids if pid in audit["passages"]]
            for field, field_audit in audit.get("scope_audits", {}).items():
                if not all(any(p["start"] <= s["start"] < s["end"] <= p["end"] for p in selected)
                           for s in field_audit["spans"]):
                    guards.append("SOURCE_SCOPE_OUTSIDE_CITED_PASSAGES:" + sid + ":" + field)
    return guards


def _gate(guards, **fields):
    return {"status": "UNRESOLVED" if guards else "BOUND", "guards": sorted(set(guards)),
            **fields, "binding_scope": BINDING_SCOPE, "scientific_truth": None}


def _requirement_gate(req, cards, audits):
    # A task quotation establishes an explicit task obligation, never science.
    if req["kind"] != "SCIENTIFIC" and req.get("question_span") is not None:
        return _gate([], requirement_ids=[req["id"]])
    guards = _source_guards(req, req.get("evidence_ids", []), cards, audits, require_scope=True)
    if req.get("reference_role") != "CONSTRAINT":
        guards.append("REPORTED_INSTANCE_NOT_CONSTRAINT" if req.get("reference_role") == "REPORTED_INSTANCE"
                      else "SOURCE_CONSTRAINT_ROLE_UNBOUND")
    return _gate(guards, requirement_ids=[req["id"]])


def _derived_projection(task, selected_route):
    routes = task["routes"]
    if selected_route is not None:
        _text(selected_route, "selected_route")
    if selected_route is not None and selected_route not in routes:
        raise ValueError("Selected route is not an exact fixed route ID")
    route = routes.get(selected_route, {})
    cards = {c["id"]: c for c in task["cards"]}
    audits = validate_cards(task["cards"])
    requirements = [r for r in task["requirements"] if r.get("scope", "GLOBAL") == "GLOBAL"
                    or r.get("route_id") == selected_route]
    req_audits = {r["id"]: _requirement_gate(r, cards, audits) for r in requirements}
    checks = {m: list(route.get("correctness_checks", {}).get(m, [])) for m in CORRECTNESS_METRICS}
    parameters = list(route.get("parameter_requirements", []))
    submetrics = deepcopy(route.get("submetrics", {}))
    gates = {}
    route_guards = ["ROUTE_NOT_SELECTED"] if selected_route is None else []
    for metric in METRICS:
        ids = list(parameters if metric == "c_param" else checks[metric])
        for group in submetrics.get(metric, {}).values():
            ids.extend(rid for rid in group if rid not in ids)
        guards = list(route_guards)
        if not ids:
            guards.append("FIXED_METRIC_REQUIREMENTS_MISSING")
        for rid in ids:
            guards.extend(rid + ":" + g for g in req_audits[rid]["guards"])
        gates[metric] = _gate(guards, requirement_ids=ids)
    inventory = deepcopy(route.get("sr_inventory"))
    inventory_guards = list(route_guards)
    reference_text_audit = {}
    if inventory is None:
        inventory_guards.append("FIXED_REFERENCE_INVENTORY_MISSING")
    else:
        for collection in ("reference_steps", "required_stages", "required_transitions"):
            for row in inventory[collection]:
                ident = row.get("reference_step_id", row.get("stage_id", row.get("transition_id")))
                local = _source_guards(row, row["source_ids"], cards, audits, require_scope=True)
                if collection == "reference_steps":
                    # Display text may translate, summarize, or normalize one or
                    # several operations. Only an explicit quotation claim is
                    # tested literally; passage fidelity is checked separately.
                    source_spans = [{"source_id": sid, **deepcopy(audits[sid]["passages"][pid])}
                        for sid in row["source_ids"]
                        for pid in row.get("passage_ids", {}).get(sid, [])
                        if pid in audits[sid]["passages"]]
                    origin = row.get("text_origin", "UNDECLARED")
                    literal_match = (any(row["text"] in span["quote"] for span in source_spans)
                                     if origin == "EXPLICIT" else None)
                    reference_text_audit[ident] = {"origin": origin, "source_spans": source_spans,
                        "literal_match": literal_match, "semantic_entailment": None}
                    if literal_match is False:
                        local.append("EXPLICIT_REFERENCE_TEXT_NOT_IN_CITED_SOURCE")
                # SR is coverage of this declared whole reference. Its stage
                # and transition inventory may describe a published instance;
                # that does not make its operations biologically necessary.
                # Scientific metric gates separately require CONSTRAINT roles.
                roles = ({"REPORTED_INSTANCE"} if collection == "reference_steps" else REFERENCE_ROLES)
                if row.get("reference_role") not in roles:
                    local.append("SOURCE_REFERENCE_ROLE_UNBOUND" if row.get("reference_role") is None
                                 else "SOURCE_REFERENCE_ROLE_MISMATCH")
                inventory_guards.extend(str(ident) + ":" + g for g in local)
    return {"schema_version": PROJECTION_SCHEMA, "question_id": task["question_id"],
            "question": task["question"], "selected_route": selected_route, "route_id": selected_route,
            "available_routes": list(routes), "route_status": "UNRESOLVED" if route_guards else "BOUND",
            "reference_id": inventory["reference_id"] if inventory else None,
            "cards": deepcopy(task["cards"]), "requirements": deepcopy(requirements),
            "fixed_requirements": deepcopy(task["requirements"]),
            "formula": deepcopy(task.get("formula")),
            "sr_inventory": inventory, "correctness_checks": checks, "parameter_requirements": parameters,
            "submetrics": submetrics, "evidence_audit": audits, "requirement_evidence": req_audits,
            "evidence_gates": gates, "inventory_evidence": _gate(inventory_guards,
                coverage_scope="SELECTED_REFERENCE_ONLY", physical_necessity_certified=False),
            "reference_text_audit": reference_text_audit,
            "binding_scope": BINDING_SCOPE, "scientific_truth": None}


def project_task_evidence(task, selected_route=None):
    """Select one whole fixed route, or retain an explicit unresolved selection.

    No route aliases, closest-name guessing, mixing of inventories, or candidate
    filtering is supported. Even a single available route needs explicit choice.
    """
    return _derived_projection(validate_task_evidence(task), selected_route)


def validate_selected_task_evidence(projection):
    """Recompute all derived gates; caller-written readiness flags never count.

    This checks the selected input snapshot's integrity, not authentication of a
    registry or its scientific truth. Production callers obtain it from .get().
    """
    supplied = _finite_copy(_object(projection, "selected task evidence"))
    if supplied.get("schema_version") != PROJECTION_SCHEMA:
        raise ValueError("Unsupported selected task evidence schema")
    selected = supplied.get("selected_route")
    available = _ids(supplied.get("available_routes"), "available_routes")
    if selected is not None and selected not in available:
        raise ValueError("Selected route is outside fixed available routes")
    route = {k: deepcopy(supplied.get(k)) for k in
             ("sr_inventory", "correctness_checks", "parameter_requirements", "submetrics")}
    task = {"schema_version": SCHEMA, "question_id": supplied.get("question_id"),
            "question": supplied.get("question"), "cards": supplied.get("cards"),
            "requirements": supplied.get("fixed_requirements"), "formula": supplied.get("formula"),
            "routes": {rid: (route if rid == selected else {}) for rid in available}}
    expected = project_task_evidence(task, selected)
    if supplied != expected:
        raise ValueError("Selected task evidence or recomputed evidence gates differ")
    return expected


class FixedTaskEvidenceRegistry:
    """Bind all fixed task evidence to an exact question snapshot and manifest.

    evidence_file is a JSON object keyed by question ID. The companion manifest
    (default: evidence_file + '.manifest.json') declares hash_format,
    questions_sha256, and task_evidence_sha256 using FixedDemandRegistry's
    canonical JSON hash convention. Missing data is explicit, never generated.
    """
    def __init__(self, question_file, evidence_file, manifest_file=None):
        manifest_file = manifest_file or str(evidence_file) + ".manifest.json"
        manifest, questions, evidence = read(manifest_file), read(question_file), read(evidence_file)
        if manifest.get("hash_format") != HASH_FORMAT:
            raise ValueError("Task evidence manifest must declare hash_format=" + HASH_FORMAT)
        self.provenance = {"questions_sha256": json_hash(questions), "task_evidence_sha256": json_hash(evidence),
                           "task_evidence_manifest_sha256": sha256_file(manifest_file), "hash_format": HASH_FORMAT,
                           "binding_scope": BINDING_SCOPE, "binding_note": manifest.get("binding_note", "")}
        for key in ("questions_sha256", "task_evidence_sha256"):
            if manifest.get(key) != self.provenance[key]:
                raise ValueError("Fixed-task evidence version mismatch: " + key)
        if not isinstance(questions, list) or any(not isinstance(q, dict) for q in questions):
            raise ValueError("Question snapshot must be an array of objects")
        self.questions = {}
        for q in questions:
            qid = q.get("question_id")
            if isinstance(qid, bool) or not isinstance(qid, (str, int)):
                raise ValueError("Invalid question ID")
            _text(str(qid), "question_id")
            _text(q.get("question"), "question")
            if str(qid) in self.questions:
                raise ValueError("Duplicate question IDs in selected snapshot")
            self.questions[str(qid)] = deepcopy(q)
        _object(evidence, "task evidence registry")
        if self.questions.keys() != evidence.keys():
            raise ValueError("Question IDs and fixed-task evidence IDs do not match")
        self._tasks = {}
        for qid, task in evidence.items():
            validated = validate_task_evidence(task)
            if str(validated["question_id"]) != qid or validated["question"] != self.questions[qid]["question"]:
                raise ValueError("Task evidence question differs from selected snapshot: " + qid)
            self._tasks[qid] = validated

    def get(self, qid, question_text, selected_route=None):
        question = self.questions.get(str(qid))
        if question is None or question["question"] != question_text:
            raise ValueError(f"Question {qid} text does not match selected snapshot; question_id alone is not a cache key")
        return project_task_evidence(self._tasks[str(qid)], selected_route)
