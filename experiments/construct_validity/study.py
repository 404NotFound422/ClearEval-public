"""Freeze a bounded development run and separate private authored expectations."""
from pathlib import Path

from . import VERSION
from .contract import digest, file_hash, read, save, validate_requirements
from .evidence import validate_cards
from .fidelity import SCHEMA as EXTRACTION_SCHEMA
from .contract import JUDGMENT_SCHEMA
from .materials import EXTRACT_PROMPT, JUDGE_PROMPT, controls, evidence_cards, revised_tasks


def prepare(workspace, output):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if (output/"manifest.json").exists():
        from .local_runner import verify_manifest
        return verify_manifest(output)
    output.mkdir(parents=True,exist_ok=True)
    tasks, cards, checks = revised_tasks(workspace), evidence_cards(workspace), controls()
    materials, jobs = {}, []
    card_map = {c["id"]:c for c in cards}
    save(output/"evidence_integrity.json", validate_cards(cards))
    for c in checks:
        materials[c["id"]] = {"root_task_id":c["source_group"], "kind":"AUTHORED_CONTROL", "question":"只评价列出的局部要求，不代表完整实验方案。",
                              "protocol":c["protocol"], "requirements":c["requirements"], "cards":[card_map[i] for i in c["card_ids"]]}
        jobs.append({"id":c["id"], "material_id":c["id"], "phase":"control"})
    for task in tasks:
        qid = task["question_id"]
        key = "Q"+str(qid)
        item = {"root_task_id":key, "track":task["track"], "kind":"NATURAL_DEVELOPMENT", "question":task["question"],
                "resource_list":task["resource_list"], "requirements":task["requirements"], "formula":task["formula"], "cards":cards}
        if qid in (79,165):
            previous = workspace/"review_artifacts/pilot_cpu_2026-09-28/attempts"/f"G{qid}"/"protocol.txt"
            item["protocol"] = previous.read_text(encoding="utf-8")
            item["protocol_origin"] = {"path":str(previous), "sha256":file_hash(previous), "reuse":"Previously exposed fixed answer, not a new generation"}
        else:
            materials["GEN"+key] = {k:v for k,v in item.items() if k not in {"requirements","formula","cards"}}
            item["generation_job"] = "G"+str(qid)
            jobs.append({"id":"G"+str(qid), "material_id":"GEN"+key, "phase":"generate"})
        materials[key] = item
    for task in tasks:
        jobs.append({"id":"J"+str(task["question_id"]), "material_id":task["root_task_id"], "phase":"judge"})
    for repetition in (2,3):
        for qid in (79,165):
            jobs.append({"id":f"J{qid}_R{repetition}", "material_id":f"Q{qid}", "phase":"judge"})
    for qid in (79,165):
        jobs.append({"id":"X"+str(qid), "material_id":f"Q{qid}", "phase":"extract"})
    # All expectations are separate from materials, and never serialized into a payload.
    save(output/"private/control_expectations.json",checks)
    save(output/"tasks.json",tasks)
    save(output/"evidence_cards.json",cards)
    save(output/"materials.json",materials)
    save(output/"jobs.json",jobs)
    (output/"judge_prompt.txt").write_text(JUDGE_PROMPT,encoding="utf-8")
    (output/"extract_prompt.txt").write_text(EXTRACT_PROMPT,encoding="utf-8")
    # Snapshot executed modules, so result reproduction does not depend on later edits.
    source = Path(__file__).parent
    for module_path in sorted(source.glob("*.py")):
        name = module_path.name
        target = output/"code"/name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes((source/name).read_bytes())
    m = {"version":VERSION, "contract_schemas":{"judgment":JUDGMENT_SCHEMA,"extraction":EXTRACTION_SCHEMA,"evidence":"source-grounding-v2"}, "purpose":"Development only; science reference and holdout pending human input",
         "model":"qwen3:8b", "model_digest":"500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41",
         "origin":"http://127.0.0.1:11434", "max_calls":len(jobs), "automatic_retries":0,
         "options":{"temperature":0, "seed":20260929, "num_gpu":0, "num_thread":12, "num_ctx":16384},
         "phase_options":{"generate":{"temperature":0.2,"num_predict":2048}, "judge":{"num_predict":2048},
                          "control":{"num_predict":512}, "extract":{"num_predict":2048}},
         "read_timeout_seconds":180, "wall_limit_seconds":1200,
         "planned_counts":{"controls":12,"new_generations":4,"reused_protocols":2,"natural_judgments":10,"extractions":2},
         "sampling":"Six previously inspected roots, three per task track, one local model; no model-family comparison",
         "deviation_from_original_plan":"Engineering expansion before domain review; 6 roots/1 model rather than 12 roots/3 model families. Existing q79/q165 fixed for within-answer diagnosis.",
         "stop_rule":"One attempt per job. Pause on transport failure; record parse/truncation failures and continue independent jobs. No result-dependent retry.",
         "independent_expert_labels":0,"wet_lab_experiments":0,"formal_holdout_roots":0}
    m["files"] = {p.relative_to(output).as_posix():file_hash(p) for p in sorted(output.rglob("*")) if p.is_file()}
    m["manifest_sha256"] = digest(m)
    save(output/"manifest.json",m)
    return m


def preflight(study):
    from .local_runner import build_payload, verify_manifest
    study = Path(study)
    m = verify_manifest(study)
    materials, jobs = read(study/"materials.json"), read(study/"jobs.json")
    issues = []
    validate_cards(read(study/"evidence_cards.json"))
    if len({j["id"] for j in jobs}) != len(jobs):
        issues.append("Duplicate job IDs")
    for key, material in materials.items():
        if "requirements" in material:
            validate_requirements(material["requirements"])
        if "expected" in material:
            issues.append("Authored reference leaked into model material")
    payloads = {}
    pending_dependencies = []
    for job in jobs:
        try:
            payload, _, _ = build_payload(study,m,job)
            payloads[job["id"]] = digest(payload)
        except FileNotFoundError:
            pending_dependencies.append(job["id"])
    for qid in (79,165):
        if len({payloads[f"J{qid}"],payloads[f"J{qid}_R2"],payloads[f"J{qid}_R3"]}) != 1:
            issues.append("Repeat payloads differ")
    result = {"engineering_ready":not issues,"issues":issues,"jobs":len(jobs),"payload_hashes":payloads,
              "generation_dependencies_not_yet_run":pending_dependencies,
              "formal_ready":False,"formal_blockers":["Independent task/evidence review", "Independent response ratings", "Verified source-grouped holdout"],
              "scientific_expectations":"Authored development controls only"}
    save(study/"preflight_report.json",result,immutable=False)
    return result

