"""Import archived judgments as archived proposals, never newly inferred labels."""
from copy import deepcopy
from pathlib import Path
from .contract import adjudicate,file_hash,read,save

def replay_guards(workspace,output):
    workspace,output=Path(workspace),Path(output)
    parent=workspace/"review_artifacts/pilot_cpu_2026-09-28"
    tasks={t["question_id"]:t for t in read(parent/"tasks.json")}
    cards=read(parent/"evidence_cards.json")
    records=[]
    for qid in (79,165):
        task=tasks[qid]
        requirements=[]
        for req in task["requirements"]:
            requirements.append({**req,"necessary":True,
                "kind":"SCIENTIFIC" if req["id"] in {"R1","R3"} else "COMPLETENESS",
                "evidence_ids":(["E_HEV"] if qid==79 else ["E_FDISCO","E_MACS"]) if req["id"]=="R1" else [],
                "review_status":"PROVISIONAL_MIGRATION_NOT_EXPERT_GOLD"})
        protocol=(parent/"attempts"/f"G{qid}"/"protocol.txt").read_text(encoding="utf-8")
        for jid in (f"J{qid}",f"J{qid}_R2"):
            path=parent/"attempts"/jid/"parsed_judgment.json"
            value=read(path)
            revised=adjudicate(value,requirements,protocol,cards)
            records.append({"source_job":jid,"source_sha256":file_hash(path),
                "scope":"Offline application of guards to stored proposals; no new LLM response; original compound criteria retained for this diagnostic only",
                "result":revised})
    save(output/"archived_guard_replay.json",records)
    r1=[next(r for r in item["result"]["requirements"] if r["id"]=="R1") for item in records]
    summary={"archived_judgments":len(records),"original_R1_satisfied":sum(r["proposed_status"]=="SATISFIED" for r in r1),
        "guarded_R1_unresolved":sum(r["effective_status"]=="UNRESOLVED" for r in r1),
        "new_model_calls":0,"scientific_accuracy_change":None,
        "limit":"Abstention guards expose unsupported acceptance; independent validation of correctness and coverage is still required."}
    save(output/"archived_guard_summary.json",summary)
    return summary
