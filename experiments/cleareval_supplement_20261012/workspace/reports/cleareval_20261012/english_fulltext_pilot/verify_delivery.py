"""Check delivered input/output provenance, source availability and pending request scope."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote

HERE=Path(__file__).resolve().parent
ROOT=Path(r"C:\ClearEval\ClearEval-public")
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def bind(p):return {"path":str(Path(p).resolve()),"sha256":hashlib.sha256(Path(p).read_bytes()).hexdigest()}
checks=[]
def check(name,x):
    if not x:raise AssertionError(name)
    checks.append({"name":name,"passed":True})

for filename in ["frozen_inputs.json","execution_freeze.json"]:
    f=read(HERE/filename)
    for b in f["inputs"]:
        check("frozen input:"+b["path"],bind(b["path"])==b)
    check("ledger:"+filename,bind(f["ledger"]["path"])==f["ledger"])
for b in read(HERE/"run_01/completion.json")["outputs"]:
    check("scoring output:"+b["path"],bind(b["path"])==b)
source_manifest=read(ROOT/"artifacts/cce_validation/optimizer_round3_20261011/confirmation_inputs_01/source_bindings.json")
for b in source_manifest["bindings"]:
    check("reference source:"+b["path"],bind(b["path"])==b)
summary=read(HERE/"summary.json")
check("result size",(summary["natural_answers"],summary["fulltext_positions"],summary["paired_differences"])==(8,28,12))
check("study provenance",summary["new_generative_requests"]==summary["new_full_CCE_judgments"]==summary["new_repeated_judgments"]==0)
qdir=HERE/"qwen_translation_pending"
qfreeze=read(qdir/"freeze.json")
for b in qfreeze["inputs"]:
    check("pending request input:"+b["path"],bind(b["path"])==b)
qplan=read(qdir/"plan.json")
matrix=read(qdir/"matrix.json")
check("pending budget scope",qplan["requested_additional_calls"]==len(matrix)==8 and qplan["proposed_package_limit"]==446)
check("pending not executed",qplan["new_requests_sent"]==0 and not (qdir/"authorization.json").exists())
for r in matrix:
    p=read(r["payload"]["path"])
    source=Path(r["source"]["path"]).read_bytes().decode("utf-8")
    check("full pending input:"+r["request_id"],p["prompt"].endswith(source))
    check("same Qwen configuration:"+r["request_id"],p["model"]==qplan["model_alias"] and p["options"]["temperature"]==0 and p["think"] is False)
    check("single structured translation:"+r["request_id"],p["format"]["required"]==["english_text"])
link_count=0
for filename in ["REPORT_zh.md","README.md","commands.md"]:
    p=HERE/filename
    for target in re.findall(r"\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
        if target.startswith(("http://","https://","#")):continue
        target=unquote(target.strip("<>" ).split("#")[0])
        check("document link:"+filename+":"+target,(p.parent/target).exists())
        link_count+=1
output={"passed":True,"checks":checks,"local_document_links":link_count,
        "source_files_verified":len(source_manifest["bindings"]),"new_generative_requests":0,
        "utc":datetime.now(timezone.utc).isoformat(),"actual_command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),
        "artifacts":[bind(HERE/f) for f in ["REPORT_zh.md","README.md","commands.md","summary.json","match_trace.json","baseline_comparison.csv"]]}
(HERE/"delivery_verification.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"passed":True,"checks":len(checks),"reference_source_files":len(source_manifest["bindings"]),"local_document_links":link_count,"new_generative_requests":0}))
