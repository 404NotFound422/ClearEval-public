"""Replay four saved source-time ledgers; expose every contribution and original formula.

This does not re-extract time from the newly translated answers.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\ClearEval\ClearEval-public")
DAY = HERE.parent
OUT = HERE / "time_examples"
OUT.mkdir(exist_ok=True)
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from evaluation_contract import time_score_details

def read(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def bind(p): return {"path": str(Path(p).resolve()), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def write(p, v): Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
def csvwrite(p, rows):
    with Path(p).open("w", encoding="utf-8-sig", newline="") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
checks=[]
def check(name, okay):
    assert okay, name
    checks.append({"name": name, "passed": True})

kbpath=ROOT / "KnowledgeBase/time_kb.json"
kb=read(kbpath)
lookup={key.casefold(): value for key,value in kb["lookup"].items()}
files={"canonical32_04/results.json": ["R3C04__r0", "R3C08__r0"], "archived67_04/results.json": ["FPC07", "FPC13"]}
scenario_rows, contribution_rows, operation_rows, sensitivity, examples, inputs=[],[],[],[],[],[bind(kbpath),bind(ROOT/"evaluation_contract.py"),bind(__file__)]

def metrics_at_time(hours, saved):
    f=saved["formula"]
    row=lookup[f["method_key"].casefold()][f["resolved_tier"]]
    value, formula=time_score_details(hours, row, f["requested_tier"])
    m=saved["metrics"]
    eff=((m["s_method"]/2.5+1)/2+m["s_label"]/6+m["s_trans"]/3+value/3)/4
    return {"hours":hours,"s_time":value,"Eff":eff,"IA":min(m["Com"],m["Cor"],eff),"HV":m["Com"]*m["Cor"]*eff,"formula":formula}

for relative, ids in files.items():
    path=DAY / "automatic_time_scope" / relative
    inputs.append(bind(path))
    rows=read(path)
    for cid in ids:
        r=next(x for x in rows if x["cell_id"]==cid)
        doc=read(r["source_document"]["path"])
        check("source document:"+cid,bind(r["source_document"]["path"])==r["source_document"])
        check("source text hash:"+cid, hashlib.sha256(doc["text"].encode("utf-8")).hexdigest()==doc["answer_sha256"])
        inputs.append(r["source_document"])
        ledger=r["time_candidate_ledger"]
        operations={op["operation_id"]:op for op in ledger["operations"]}
        for op in ledger["operations"]:
            span=op["source"]
            check("operation span:"+cid+op["operation_id"], doc["text"][span["start"]:span["end"]]==span["quote"])
            operation_rows.append({"case_id":cid,"operation_id":op["operation_id"],"role":op["scope"]["role"],
                                   "phase":op["raw_phase"],"scope_basis":op["scope"]["basis"],
                                   "branch_group":json.dumps(op.get("branch_group"),ensure_ascii=False),
                                   "duration_options":json.dumps(op.get("duration",{}).get("options",[]),ensure_ascii=False),
                                   "source_quote":span["quote"],"source_start":span["start"],"source_end":span["end"],
                                   "source_document":r["source_document"]["path"]})
        for s in ledger["scenarios"]:
            low=sum(c["bounds_hours"][0] for c in s["contributions"])
            high=sum(c["bounds_hours"][1] for c in s["contributions"])
            check("complete scenario:"+cid+s["scenario_id"],not s["issues"] and not s["unknown_duration_operations"])
            check("contribution sum:"+cid+s["scenario_id"],[low,high]==s["bounds_hours"])
            hours=(low+high)/2
            check("within-branch midpoint:"+cid+s["scenario_id"],hours==s["hours"])
            saved=next(x for x in r["conditional_time_results"] if x["scenario_id"]==s["scenario_id"])
            recalculated=metrics_at_time(hours,saved)
            for key in ["s_time","Eff","IA","HV"]:
                check("original formula replay:"+cid+s["scenario_id"]+key,math.isclose(recalculated[key],saved["metrics"][key],rel_tol=0,abs_tol=1e-12))
            scenario_rows.append({"case_id":cid,"scenario_id":s["scenario_id"],"selection":json.dumps(s["selection"],ensure_ascii=False),
                                  "bounds_low_hours":low,"bounds_high_hours":high,
                                  **{k:recalculated[k] for k in ["hours","s_time","Eff","IA","HV"]},
                                  "source_result":str(path),"new_extraction":False})
            for c in s["contributions"]:
                span=c["source"]
                check("time span:"+cid+s["scenario_id"]+c["operation_id"],doc["text"][span["start"]:span["end"]]==span["quote"])
                count=c["repeat_count"]
                check("repeat arithmetic:"+cid+s["scenario_id"]+c["operation_id"],
                      [count*x for x in c["duration_bounds_hours"]]==c["bounds_hours"])
                contribution_rows.append({"case_id":cid,"scenario_id":s["scenario_id"],"operation_id":c["operation_id"],
                                          "option_id":c["option_id"],"phase":operations[c["operation_id"]]["raw_phase"],
                                          "repeat_count":count,"low_hours":c["bounds_hours"][0],"high_hours":c["bounds_hours"][1],
                                          "point_hours":sum(c["bounds_hours"])/2,
                                          "source_quote":span["quote"],"source_start":span["start"],"source_end":span["end"],
                                          "source_document":r["source_document"]["path"]})
            if low!=high:
                for label,h in [("lower_endpoint",low),("upper_endpoint",high)]:
                    sensitivity.append({"case_id":cid,"scenario_id":s["scenario_id"],"kind":label,**metrics_at_time(h,saved),
                                        "interpretation":"range sensitivity; not an additional observation"})
        examples.append({"case_id":cid,"source_result":bind(path),"source_document":r["source_document"],
                         "source_answer_sha256":doc["answer_sha256"],"ledger":ledger,
                         "original_metrics":r["metrics"],"new_extraction":False,"expert_validated":False})

fpc13=next(e for e in examples if e["case_id"]=="FPC13")
cumulative=next(o for o in fpc13["ledger"]["operations"] if any(z["option_id"]=="source_cumulative_total" for z in o.get("duration",{}).get("options",[])))
check("FPC13 cumulative replaces initial", cumulative["duration"]["options"][0]["bounds_hours"]==[72.,72.])
c08=[s for s in scenario_rows if s["case_id"]=="R3C08__r0"]
check("C08 branches stay separate",sorted(s["hours"] for s in c08)==[20.,32.])
check("no fictitious branch midpoint",all(s["hours"]!=26 for s in c08))
write(OUT/"examples.json",examples)
write(OUT/"scenarios.json",scenario_rows)
write(OUT/"endpoint_sensitivity.json",sensitivity)
csvwrite(OUT/"scenarios.csv",scenario_rows)
csvwrite(OUT/"contributions.csv",contribution_rows)
csvwrite(OUT/"operations_including_excluded.csv",operation_rows)
write(OUT/"verification.json",{"passed":True,"checks":checks,"inputs":inputs,
                               "new_time_extractions":0,"new_model_calls":0,
                               "scope":"Recomputed sums and original numeric time formula on saved source interpretations; no independent scientific validation"})
write(OUT/"execution.json",{"utc":datetime.now(timezone.utc).isoformat(),"command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),
                            "cwd":str(Path.cwd()),"new_model_calls":0})
print(json.dumps({"examples":len(examples),"scenarios":len(scenario_rows),"contributions":len(contribution_rows),
                  "operation_records_including_excluded":len(operation_rows),"checks":len(checks),"new_time_extractions":0,
                  "results":scenario_rows},ensure_ascii=False))
