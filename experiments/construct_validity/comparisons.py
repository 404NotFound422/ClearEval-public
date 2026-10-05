"""Controlled development interfaces; no benchmark or remote API is invoked."""
from copy import deepcopy
from pathlib import Path
import re
from .contract import adjudicate, digest, file_hash, read, save
from .execution_identity import assert_public, compare_judge_inputs, execution_identity
from .local_runner import build_payload, local_origin, verify_manifest
from .objectives import compare_candidates


def same_information_guards(bundle):
    """Compare two mechanisms using the identical stored proposal and context."""
    assert_public(bundle)
    required = {"judgment", "requirements", "protocol", "cards"}
    if not required <= set(bundle):
        raise ValueError("Complete proposal and public context required")
    records = []
    for name, enabled in (("proposal_without_evidence_guards", False), ("source_guarded", True)):
        actual = deepcopy(bundle)
        value = adjudicate(actual["judgment"], actual["requirements"], actual["protocol"],
                           actual["cards"], actual.get("formula"), evidence_guard=enabled)
        records.append({"adapter":name, "visible_bundle_sha256":digest(actual), "observed":value})
    return {"bundle_sha256":digest(bundle), "same_actual_information":len({r["visible_bundle_sha256"] for r in records}) == 1,
            "mechanisms":records, "interpretation":"Deterministic guard ablation on one proposal, not separate model judgments",
            "scientific_accuracy":None}


def compare_adjudicated_candidates(a, b):
    """Bind feasibility to freshly recomputed requirement decisions, including routes."""
    candidates, audits = [], []
    for item in (a, b):
        context = item["evaluation_context"]
        assert_public(context)
        value = adjudicate(context["judgment"], context["requirements"], context["protocol"],
                           context["cards"], context.get("formula"))
        candidate = {k:deepcopy(v) for k,v in item.items() if k not in {"evaluation_context", "constraints"}}
        candidate["constraints"] = {"admissibility":value["overall"]}
        candidates.append(candidate)
        audits.append({"candidate_id":item["id"], "evaluation_context_sha256":digest(context),
                       "protocol_sha256":digest(context["protocol"]), "adjudication":value,
                       "supplied_constraints":item.get("constraints"), "constraint_source":"RECOMPUTED_REQUIREMENTS"})
    # Different task contracts cannot establish a same-task dominance relationship.
    contracts = [digest({"requirements":x["evaluation_context"]["requirements"],
                         "formula":x["evaluation_context"].get("formula"),
                         "cards":x["evaluation_context"]["cards"]}) for x in (a,b)]
    result = compare_candidates(*candidates)
    if contracts[0] != contracts[1]:
        result.update(relationship="NOT_COMPARABLE", reasons=["DIFFERENT_REQUIREMENT_OR_EVIDENCE_CONTRACT"])
    result["feasibility_audits"] = audits
    return result


def freeze_judge_comparison(study, judges, output, repeats=3):
    """Freeze separate local plans with identical answers, context and sampling.

    All requested models must already exist locally when the plans are run.
    This function performs no inference and does not install any model.
    """
    if type(repeats) is not int or not 2 <= repeats <= 20:
        raise ValueError("Explicit repeat count must be 2..20")
    if not isinstance(judges, list) or len(judges) < 2:
        raise ValueError("At least two declared judge configurations required")
    identifiers = [j.get("id") for j in judges]
    if len(set(identifiers)) != len(judges):
        raise ValueError("Judge identifiers must be unique")
    for judge in judges:
        if (not isinstance(judge.get("id"),str) or not re.fullmatch(r"[A-Za-z0-9_-]+", judge["id"])
                or not judge.get("model") or not re.fullmatch(r"[0-9a-fA-F]{64}",judge.get("revision",""))
                or not judge.get("family") or judge["family"] == "UNDECLARED"):
            raise ValueError("Judge needs id, model, frozen SHA256 revision and family")
        local_origin(judge.get("origin", "http://127.0.0.1:11434"))
    if len({j["family"] for j in judges}) < 2:
        raise ValueError("Cross-family plans require at least two declared families")
    study, output = Path(study), Path(output)
    base = verify_manifest(study)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new comparison directory")
    output.mkdir(parents=True, exist_ok=True)
    materials, jobs = read(study/"materials.json"), read(study/"jobs.json")
    realized, selected = {}, []
    for job in jobs:
        if job["phase"] not in {"judge", "control"} or job["material_id"] in realized:
            continue
        _, item, protocol = build_payload(study, base, job)
        item = deepcopy(item)
        item.pop("generation_job", None)
        item["protocol"] = protocol
        assert_public(item)
        realized[job["material_id"]] = item
        selected.append(job["material_id"])
    if not selected:
        raise ValueError("No fixed completed answers available")
    plans, identities = [], {}
    for judge in judges:
        folder = output/judge["id"]
        save(folder/"materials.json", realized)
        planned = [{"id":f"D{n}_R{r}","material_id":mid,"phase":"judge"}
                   for n,mid in enumerate(selected) for r in range(1,repeats+1)]
        save(folder/"jobs.json", planned)
        for name in ("judge_prompt.txt", "extract_prompt.txt"):
            (folder/name).write_bytes((study/name).read_bytes())
        source = Path(__file__).parent
        (folder/"code").mkdir()
        for p in source.glob("*.py"):
            (folder/"code"/p.name).write_bytes(p.read_bytes())
        manifest = deepcopy(base)
        manifest.pop("manifest_sha256", None)
        manifest.update(model=judge["model"], model_digest=judge["revision"], model_family=judge["family"],
                        provider="ollama-loopback", origin=judge.get("origin", "http://127.0.0.1:11434"),
                        max_calls=len(planned), purpose="Fixed-input cross-family development plan; no formal benchmark",
                        planned_counts={"judge":len(planned)}, comparison_source_sha256=base["manifest_sha256"],
                        sampling="Fixed shared answers and context; identical options across declared families")
        manifest["files"] = {p.relative_to(folder).as_posix():file_hash(p) for p in sorted(folder.rglob("*")) if p.is_file()}
        manifest["manifest_sha256"] = digest(manifest)
        save(folder/"manifest.json", manifest)
        payload,item,protocol = build_payload(folder,manifest,planned[0])
        identities[judge["id"]] = execution_identity(payload,item,protocol,manifest,planned[0])
        plans.append({"id":judge["id"],"path":str(folder),"calls":len(planned),"manifest_sha256":manifest["manifest_sha256"]})
    checks = [compare_judge_inputs(identities[identifiers[0]],identities[jid]) for jid in identifiers[1:]]
    index = {"plans":plans,"information_checks":checks,"planned_calls":sum(p["calls"] for p in plans),
             "model_calls_performed":0,"expert_labels":0,"scientific_comparison_performed":False,
             "run_command":"python -B -m experiments.construct_validity run --study <plan> --max-new <1..28>"}
    save(output/"comparison_plan.json", index)
    return index