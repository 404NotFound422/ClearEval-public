"""Recompute development outcomes from frozen inputs and all stored attempts."""
from collections import Counter, defaultdict
import itertools
from pathlib import Path
from .audit import write_csv
from .contract import adjudicate, digest, parse_json, read, save, validate_extraction
from .execution_identity import execution_identity, repeat_diagnostic, verify_saved_request
from .local_runner import build_payload, local_origin, verify_manifest
from .statistics import entropy, paired_cluster_interval, zero_error_design


def checked_attempt(study, manifest, job):
    folder = study/"attempts"/job["id"]/"a01"
    if not (folder/"result.json").exists():
        started = read(folder/"started.json") if (folder/"started.json").exists() else {}
        return {**job, "job_id":job["id"], "status":"INTERRUPTED_UNCLOSED" if started else "NOT_ATTEMPTED",
                "execution_origin":started.get("execution_origin", "UNDECLARED"),
                "invocation_id":started.get("invocation_id")}, None
    result, request, started = (read(folder/name) for name in ("result.json", "request.json", "started.json"))
    payload, material, protocol = build_payload(study, manifest, job)
    identity = execution_identity(payload, material, protocol, manifest, job)
    verify_saved_request(request, result, payload, identity, local_origin(manifest["origin"])+"/api/chat")
    if (started.get("job") != job or started.get("manifest_sha256") != manifest["manifest_sha256"]
            or not started.get("invocation_id") or started["invocation_id"] != result.get("invocation_id")
            or started.get("execution_origin") != result.get("execution_origin")):
        raise ValueError("Started attempt identity differs from frozen job or result")
    for key in ("phase", "material_id"):
        if result.get(key) != job[key]:
            raise ValueError("Result job binding differs: " + key)
    if result.get("job_id") != job["id"] or result.get("root_task_id") != material["root_task_id"]:
        raise ValueError("Result task identity differs")
    if result.get("visible_information_sha256") != identity["visible_information_sha256"]:
        raise ValueError("Result visible information identity differs")
    text = (folder/"content.txt").read_text(encoding="utf-8")
    if digest(text) != result["content_sha256"]:
        raise ValueError("Stored content changed")
    if result["status"] == "COMPLETE" and not (folder/"chunks.jsonl").exists():
        raise ValueError("Complete attempt lacks original transport chunks")
    if (folder/"chunks.jsonl").exists():
        chunks = [parse_json(line) for line in (folder/"chunks.jsonl").read_text(encoding="utf-8").splitlines()]
        reconstructed = "".join(c.get("message",{}).get("content", "") for c in chunks)
        if reconstructed != text:
            raise ValueError("Content differs from recorded transport chunks")
        if result["status"] == "COMPLETE":
            terminal = next((c for c in reversed(chunks) if c.get("done")), None)
            if (terminal is None or terminal != read(folder/"terminal_response.json")
                    or terminal.get("done_reason") != "stop" or terminal.get("model") != manifest["model"]):
                raise ValueError("Terminal response differs from transport record")
    if result["status"] != "COMPLETE":
        return result, None
    if result.get("execution_origin") == "LIVE":
        for name in ("model_binding_before", "model_binding_after"):
            binding = result.get(name, {})
            if binding.get("model") != manifest["model"] or binding.get("digest") != manifest["model_digest"]:
                raise ValueError("Live completion lacks frozen model binding")
    if job["phase"] == "generate":
        return result, None
    value = parse_json(text)
    if value != read(folder/"parsed.json"):
        raise ValueError("Parsed output differs from original model content")
    fresh = (validate_extraction(value, protocol) if job["phase"] == "extract" else
             adjudicate(value, material["requirements"], protocol, material["cards"], material.get("formula")))
    if fresh != read(folder/"validated.json"):
        raise ValueError("Stored validation differs from deterministic recomputation")
    return result, fresh


def summarize(study, output=None):
    study = Path(study)
    output = Path(output) if output else study/"analysis"
    output.mkdir(parents=True, exist_ok=True)
    manifest = verify_manifest(study)
    jobs, materials = read(study/"jobs.json"), read(study/"materials.json")
    results, validated, extractions, details = [], {}, {}, []
    for job in jobs:
        result, fresh = checked_attempt(study, manifest, job)
        results.append(result)
        if fresh is None:
            continue
        if job["phase"] == "extract":
            extractions[job["id"]] = fresh
            continue
        validated[job["id"]] = fresh
        for row in fresh["requirements"]:
            details.append({"job_id":job["id"],"material_id":job["material_id"],"root_task_id":result["root_task_id"],
                           "requirement_id":row["id"],"proposed":row["proposed_status"],"effective":row["effective_status"],
                           "guards":";".join(row["guards"]),"reason":row["reason"]})
    result_rows = [{"job_id":r["job_id"],"phase":r["phase"],"material_id":r["material_id"],"status":r["status"],
                    "technical_status":r.get("technical_status"),"execution_origin":r.get("execution_origin"),
                    "seconds":r.get("elapsed_seconds"),"input_tokens":r.get("runtime",{}).get("prompt_eval_count"),
                    "output_tokens":r.get("runtime",{}).get("eval_count"),"overall":validated.get(r["job_id"],{}).get("overall"),
                    "failure":r.get("failure",{}).get("message")} for r in results]
    write_csv(output/"results.csv", result_rows)
    write_csv(output/"requirement_judgments.csv", details, fields=["job_id","material_id","root_task_id","requirement_id","proposed","effective","guards","reason"])
    checks = []
    control_path = study/"private/control_expectations.json"
    for check in read(control_path) if control_path.exists() else []:
        value = validated.get(check["id"])
        observed = {r["id"]:r["effective_status"] for r in value["requirements"]} if value else None
        checks.append({"id":check["id"],"expected":check["expected"],"observed":observed,
                       "match":observed == check["expected"] if observed is not None else None,
                       "provenance":check["expectation_provenance"]})
    groups, by_id = defaultdict(list), {r["job_id"]:r for r in results}
    for job in jobs:
        if job["phase"] == "judge":
            groups[job["material_id"]].append(job["id"])
    repeats = []
    for mid, ids in groups.items():
        if len(ids) < 2:
            continue
        records = [by_id[jid] for jid in ids]
        diagnostic = repeat_diagnostic(records, len(ids))
        available = [r["job_id"] for r in records if r["job_id"] in validated]
        live = [r["job_id"] for r in records if r["job_id"] in validated and r.get("execution_origin") == "LIVE"
                and r.get("response_cache_hit") is False]
        ready = diagnostic["repetition_status"] != "NOT_ESTIMABLE"
        rows = []
        for req in materials[mid]["requirements"]:
            states = [next(r["effective_status"] for r in validated[jid]["requirements"] if r["id"] == req["id"]) for jid in live] if ready else []
            pairs = list(itertools.combinations(states,2))
            rows.append({"id":req["id"],"states":states,"entropy_bits":entropy(states) if ready else None,
                         "pair_count":len(pairs),"flipped_pairs":sum(a != b for a,b in pairs) if ready else None})
        overall = [validated[jid]["overall"] for jid in live] if ready else []
        repeats.append({**diagnostic,"material_id":mid,"valid":len(available),"requirements":rows,
                        "technical_judgments":[{"job_id":jid,"execution_origin":by_id[jid].get("execution_origin"),"overall":validated[jid]["overall"]} for jid in available],
                        "overall_states":overall,"overall_entropy_bits":entropy(overall) if ready else None})
    ablation = [{"job_id":jid,"proposed_overall":v["proposed_overall"],"guarded_overall":v["overall"],
                 "changed_requirement_count":sum(r["proposed_status"] != r["effective_status"] for r in v["requirements"]),
                 "scope":"One saved proposal with admissibility guards; not separate model comparison"} for jid,v in validated.items()]
    save(output/"control_results.json", checks, immutable=False)
    save(output/"repeat_results.json", repeats, immutable=False)
    save(output/"guard_ablation.json", ablation, immutable=False)
    save(output/"extraction_audits.json", extractions, immutable=False)
    summary = {"manifest_sha256":manifest["manifest_sha256"],"planned_calls":len(jobs),
               "attempted_calls":sum((study/"attempts"/j["id"]/"a01/started.json").exists() for j in jobs),
               "statuses":dict(Counter(r["status"] for r in results)),
               "execution_origins":dict(Counter(r.get("execution_origin","UNDECLARED") for r in results if r["status"] != "NOT_ATTEMPTED")),
               "new_generations_complete":sum(r["phase"] == "generate" and r["status"] == "COMPLETE" for r in results),
               "natural_protocols_reused":sum("protocol_origin" in m for m in materials.values()),"valid_judgments":len(validated),
               "extractions_complete":len(extractions),"extractions_scoring_eligible":sum(v.get("scoring_eligible") is True for v in extractions.values()),
               "controls_planned":len(checks),"controls_valid":sum(c["observed"] is not None for c in checks),
               "controls_matching_authored_expectation":sum(c["match"] is True for c in checks),
               "request_seconds":round(sum(r.get("elapsed_seconds",0) for r in results),3),
               "input_tokens_reported_sum":sum(r.get("runtime",{}).get("prompt_eval_count",0) or 0 for r in results),
               "output_tokens_reported_sum":sum(r.get("runtime",{}).get("eval_count",0) or 0 for r in results),
               "attempts_without_usage":sum("runtime" not in r and r["status"] not in {"NOT_ATTEMPTED","INTERRUPTED_UNCLOSED"} for r in results),
               "guard_changed_requirements":sum(r["proposed"] != r["effective"] for r in details),
               "independent_expert_labels":0,"formal_holdout_roots":0,"wet_lab_experiments":0,
               "scientific_accuracy":None,"confidence_interval_status":"NOT_ESTIMABLE_WITHOUT_INDEPENDENT_REFERENCE",
               "all_saved_judgments_recomputed":True,"all_saved_extractions_recomputed":True,
               "model":manifest["model"],"model_digest":manifest["model_digest"]}
    save(output/"summary.json", summary, immutable=False)
    ci = paired_cluster_interval([])
    write_csv(output/"confidence_intervals.csv",[{"metric":"scientific_evaluator_difference","status":ci["status"],"estimate":None,"low":None,"high":None,"reason":ci["reason"]}])
    save(output/"sample_design_diagnostics.json",[zero_error_design(0.05),zero_error_design(0.01)],immutable=False)
    return summary


def read_payload_data(payload):
    return parse_json(payload["messages"][-1]["content"])