"""Execute the eight approved, frozen local translation requests once each.

Raw HTTP returns precede interpretation. No automatic retries or translation repair.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=Path(r"C:\ClearEval\ClearEval-public")
LEDGER=ROOT/"artifacts/cce_validation/judges/request_ledger.jsonl"
BUDGET=ROOT/"artifacts/cce_validation/budget.json"
ROUND="fulltext_english_translation_20261012"
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/"scripts"))
import cce_judges as j

def now():return datetime.now(timezone.utc)
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def bind(p):return {"path":str(Path(p).resolve()),"sha256":hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def frozen_inputs():
    f=read(HERE/"freeze.json")
    for b in f["inputs"]:
        assert bind(b["path"])==b,"Prepared input changed: "+b["path"]
    a=read(HERE/"authorization.json")
    assert a["status"]=="explicit_user_approval_recorded" and a["user_reply"]=="好的，继续"
    assert (a["starting_package_requests"],a["authorized_new_requests"],a["new_package_limit"])==(438,8,446)
    assert a["prepared_freeze"]==bind(HERE/"freeze.json")
    assert a["automatic_retries"] is False
    assert (datetime.fromisoformat(a["deadline_utc"])-datetime.fromisoformat(a["start_utc"])).total_seconds()==7200
    return a
def counts():
    prefix=(HERE/"ledger_before_execution.jsonl").read_bytes()
    assert LEDGER.read_bytes().startswith(prefix),"Historical request ledger changed"
    requests=[r for r in j.ledger_rows(LEDGER) if r.get("event")=="request_started"]
    own=[r for r in requests if r.get("round_id")==ROUND]
    return requests,own
def budget_snapshot(a):
    allrows,own=counts()
    value={"round_id":ROUND,"attempts_recorded":len(allrows),"package_limit":446,
           "round_attempts":len(own),"round_limit":8,"remaining_request_capacity":min(8-len(own),446-len(allrows)),
           "authorization":bind(HERE/"authorization.json"),"ledger":bind(LEDGER),"deadline_utc":a["deadline_utc"],
           "automatic_retries":False,"human_budget":{"experts":1,"development":5,"holdout":15}}
    save(HERE/"budget_snapshot.json",value)
    save(BUDGET,value)
    return value
def metadata(model):
    host=model["host"]
    assert host=="http://127.0.0.1:11434"
    with urllib.request.urlopen(host+"/api/version",timeout=15) as r:version=json.load(r)
    with urllib.request.urlopen(host+"/api/tags",timeout=15) as r:tags=json.load(r)
    selected=[m for m in tags["models"] if m["name"]==model["model_name"]]
    assert len(selected)==1 and selected[0]["digest"]==model["model_digest"],"Local model identity changed"
    return {"checked_utc":now().isoformat(),"host":host,"version":version,"model":selected[0],"generation_requests":0}
def worker(payload_path,raw_path,timeout):
    data=Path(payload_path).read_bytes()
    request=urllib.request.Request("http://127.0.0.1:11434/api/generate",data=data,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(request,timeout=timeout) as response:
        raw=response.read()
        Path(raw_path).write_bytes(raw)
    print(json.dumps({"http_return_bytes":len(raw)}),flush=True)

def interpret(row,raw_path,terminal):
    # Preserve the raw response even if this local interpretation fails.
    outer=read(raw_path)
    content=outer.get("response")
    if not isinstance(content,str):raise ValueError("HTTP JSON has no string response")
    response_path=raw_path.parent/"response_content.txt"
    response_path.write_text(content,encoding="utf-8",newline="")
    obj=json.loads(content)
    if not isinstance(obj,dict) or set(obj)!={"english_text"} or not isinstance(obj["english_text"],str):
        raise ValueError("Translation JSON does not match the frozen schema")
    english=obj["english_text"]
    if not english.strip():raise ValueError("Translation text is empty")
    translated=raw_path.parent/"english_text.txt"
    translated.write_text(english,encoding="utf-8",newline="")
    return {**terminal,"status":"returned_translation_pending_fidelity_review","translation":bind(translated),
            "raw_response":bind(raw_path),"response_content":bind(response_path),
            "model_response_metadata":{k:outer.get(k) for k in ["model","created_at","done","done_reason","total_duration","load_duration","prompt_eval_count","prompt_eval_duration","eval_count","eval_duration"]},
            "source":row["source"],"payload":row["payload"],"fidelity_review_completed":False}

def run():
    a=frozen_inputs()
    model=read(HERE/"model_config.json")
    rows=read(HERE/"matrix.json")
    assert len(rows)==8
    live=metadata(model)
    save(HERE/"runtime_preflight.json",live)
    seal={"inputs":[bind(__file__),bind(Path(j.__file__)),bind(HERE/"authorization.json"),bind(HERE/"freeze.json"),bind(HERE/"runtime_preflight.json")],
          "actual_command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),"cwd":str(Path.cwd()),"pid":os.getpid(),"started_utc":now().isoformat()}
    stamp=now().strftime("%Y%m%dT%H%M%S")
    save(HERE/"execution_records"/(stamp+".json"),seal)
    deadline=datetime.fromisoformat(a["deadline_utc"])
    budget_snapshot(a)
    completed=[]
    for row in rows:
        folder=HERE/"returns"/row["request_id"]
        folder.mkdir(parents=True,exist_ok=True)
        terminal_path=folder/"terminal.json"
        if terminal_path.exists():
            prior=read(terminal_path)
            assert prior["payload"]==row["payload"]
            if prior.get("translation"):assert bind(prior["translation"]["path"])==prior["translation"]
            completed.append(prior)
            print(json.dumps({"request_id":row["request_id"],"state":"existing_terminal_reused"}),flush=True)
            continue
        frozen_inputs()
        trial=j.digest({"round_id":ROUND,"request_id":row["request_id"],"payload":row["payload"],"freeze":a["prepared_freeze"]})
        with j.ledger_lock(LEDGER):
            allrows,own=counts()
            assert len(allrows)==438+len(own),"Other request activity needs reconciliation"
            if any(r.get("trial_id")==trial for r in allrows):
                raise RuntimeError("A prior attempt has no terminal; inspect its raw return/process. No automatic retry.")
            remaining=(deadline-now()).total_seconds()
            if len(allrows)>=446 or len(own)>=8 or remaining<=1:
                print(json.dumps({"state":"approved_limit_reached","budget":budget_snapshot(a)}),flush=True)
                break
            request={"event":"request_started","request_id":j.digest({"trial_id":trial,"attempt":1}),"trial_id":trial,
                     "attempt":1,"model":model["model_name"],"started_utc":now().isoformat(),"package_request_index":len(allrows)+1,
                     "round_id":ROUND,"phase":"fulltext_translation","observation_id":row["request_id"],
                     "authorization_sha256":bind(HERE/"authorization.json")["sha256"],"payload_sha256":row["payload"]["sha256"]}
            with LEDGER.open("a",encoding="utf-8",newline="") as f:f.write(j.canonical(request)+"\n")
        budget_snapshot(a)
        terminal={"request_id":row["request_id"],"answer_id":row["answer_id"],"condition":row["condition"],
                  "request":request,"payload":row["payload"],"source":row["source"],"attempt":1,"actual_new_request":True}
        save(folder/"started.json",terminal)
        raw_path=folder/"http_response.json"
        print(json.dumps({"request_id":row["request_id"],"state":"request_started","package_count":request["package_request_index"]}),flush=True)
        started=time.monotonic()
        try:
            remaining=(deadline-now()).total_seconds()
            command=[sys.executable,"-X","utf8",str(Path(__file__).resolve()),"--worker",row["payload"]["path"],str(raw_path),str(max(1,remaining))]
            process=subprocess.run(command,capture_output=True,timeout=max(.1,remaining))
            (folder/"worker_stdout.txt").write_bytes(process.stdout)
            (folder/"worker_stderr.txt").write_bytes(process.stderr)
            if process.returncode!=0:raise RuntimeError("HTTP worker exited "+str(process.returncode)+"; see worker_stderr.txt")
            terminal=interpret(row,raw_path,terminal)
        except subprocess.TimeoutExpired as exc:
            terminal.update(status="authorized_time_limit_reached",error_type=type(exc).__name__,error="Hard two-hour batch deadline reached; request not retried")
            if exc.stdout:(folder/"worker_stdout.txt").write_bytes(exc.stdout)
            if exc.stderr:(folder/"worker_stderr.txt").write_bytes(exc.stderr)
        except Exception as exc:
            terminal.update(status="request_or_translation_format_failure",error_type=type(exc).__name__,error=str(exc))
            if raw_path.exists():terminal["raw_response"]=bind(raw_path)
        terminal.update(finished_utc=now().isoformat(),wall_seconds=time.monotonic()-started)
        save(terminal_path,terminal)
        completed.append(terminal)
        state=budget_snapshot(a)
        save(HERE/"progress.json",{"completed":completed,"remaining_observation_ids":[r["request_id"] for r in rows if not (HERE/"returns"/r["request_id"]/"terminal.json").exists()],"budget":state})
        print(json.dumps({"request_id":row["request_id"],"state":terminal["status"],"seconds":round(terminal["wall_seconds"],2)}),flush=True)
    save(HERE/"execution_summary.json",{"finished_utc":now().isoformat(),"terminals":completed,"budget":budget_snapshot(a),
                                       "fresh_fidelity_reviews":0,"new_full_CCE_judgments":0,"automatic_retries":False})
    print(json.dumps({"state":"batch_finished","completed_positions":len(completed),"budget":budget_snapshot(a)}),flush=True)

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--worker":worker(sys.argv[2],sys.argv[3],float(sys.argv[4]))
    else:run()
