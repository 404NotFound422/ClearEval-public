"""Score actual Qwen full-text translations; retain machine fidelity flags separately."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import re
import socket
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PILOT=HERE.parent
ROOT=Path(r"C:\ClearEval\ClearEval-public")
R3=ROOT/"artifacts/cce_validation/optimizer_round3_20261011"
OUT=HERE/"scoring"
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/"scripts"))
for k in ["HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE","HF_HUB_DISABLE_TELEMETRY"]:os.environ[k]="1"
for k in ["OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"]:os.environ[k]="2"
def no_network(*args,**kwargs):raise RuntimeError("Translation scoring is offline")
socket.create_connection=no_network;socket.socket.connect=no_network;socket.socket.connect_ex=no_network
import cce_validation as core
import cce_method_family_steps_v1 as family

def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def bind(p):return {"path":str(Path(p).resolve()),"sha256":hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def text(p):return Path(p).read_bytes().decode("utf-8")
def csvwrite(p,rows):
    if not rows:return
    with Path(p).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def units(value):
    hits=list(re.finditer(r"^\s*(?:\*\*)?(\d+(?:\.\d+)*)(?:[.)])?\s+",value,re.M))
    result=[]
    if not hits:return [{"unit_id":"HEADER","start":0,"end":len(value),"text":value}]
    result.append({"unit_id":"HEADER","start":0,"end":hits[0].start(),"text":value[:hits[0].start()]})
    for i,h in enumerate(hits):
        end=hits[i+1].start() if i+1<len(hits) else len(value)
        result.append({"unit_id":h.group(1),"start":h.start(),"end":end,"text":value[h.start():end]})
    return result
def number_tokens(value):
    return Counter(re.findall(r"\d+(?:\.\d+)?",value))
def time_fields(value):
    return re.findall(r"\bTime\s*[:：]\s*([^\n)]*)",value,re.I)
def time_signature(value):
    v=value.lower().replace("–","-").replace("—","-")
    v=re.sub(r"\b(?:hours?|hrs?|h)\b","hour",v)
    v=re.sub(r"\b(?:minutes?|mins?)\b","minute",v)
    v=re.sub(r"\bdays?\b","day",v)
    # Numeric values, their order, and literal time units. Semantics need source review too.
    return re.findall(r"\d+(?:\.\d+)?|hour|minute|day|week|×|≤|≥",v)
def audit(source,english):
    su,eu=units(source),units(english)
    same_ids=[u["unit_id"] for u in su]==[u["unit_id"] for u in eu]
    pairs=[]
    if same_ids:
        for a,b in zip(su,eu):
            na,nb=number_tokens(a["text"]),number_tokens(b["text"])
            ta,tb=time_fields(a["text"]),time_fields(b["text"])
            pairs.append({"unit_id":a["unit_id"],"source":a,"english":b,
                          "number_tokens_equal":na==nb,"source_only_number_tokens":dict(na-nb),"english_only_number_tokens":dict(nb-na),
                          "source_time_fields":ta,"english_time_fields":tb,
                          "time_signatures_equal":[time_signature(t) for t in ta]==[time_signature(t) for t in tb]})
    sn,en=number_tokens(source),number_tokens(english)
    return {"same_numbered_unit_sequence":same_ids,"source_unit_ids":[u["unit_id"] for u in su],"english_unit_ids":[u["unit_id"] for u in eu],
            "whole_text_number_tokens_equal":sn==en,"source_only_number_tokens":dict(sn-en),"english_only_number_tokens":dict(en-sn),
            "CJK_remaining":len(re.findall(r"[\u4e00-\u9fff]",english)),"unit_pairs":pairs,
            "number_flag_units":[p["unit_id"] for p in pairs if not p["number_tokens_equal"]],
            "time_flag_units":[p["unit_id"] for p in pairs if not p["time_signatures_equal"]],
            "machine_checks_establish_scientific_fidelity":False,"author_semantic_review":"pending","expert_verified":False}

class CachedEncoder(core.Encoder):
    def __init__(self):
        super().__init__();self.memo={};self.used={};self.created={}
        self.local=HERE/"new_embedding_cache";self.local.mkdir(exist_ok=True)
        self.search=[self.cache,*family.CACHES,core.ASSETS/"assets/embedding_cache",PILOT.parent/"step_language_probe/new_embedding_cache",PILOT/"new_embedding_cache",self.local]
    def encode(self,texts):
        vectors=[]
        for t in texts:
            if t not in self.memo:
                key=core.digest([self.identity,t])+".npy"
                matches=[c/key for c in self.search if (c/key).exists()]
                if matches:
                    path=matches[0];vec=self.np.load(path);self.used[str(path)]=bind(path)
                else:
                    vec=self.model.encode([t],normalize_embeddings=True,show_progress_bar=False)[0]
                    path=self.local/key;self.np.save(path,vec);self.created[str(path)]=bind(path)
                self.memo[t]=vec
            vectors.append(self.memo[t])
        return self.np.asarray(vectors)

def main():
    OUT.mkdir(exist_ok=True)
    old=read(PILOT/"run_01/results.json")
    old_by={(r["answer_id"],r["representation"],r["condition"]):r for r in old}
    cases={r["anonymous_answer_id"]:r for r in read(R3/"confirmation_qwen_01/cases.json")["cases"]}
    for f in ["freeze.json"]:
        for b in read(HERE/f)["inputs"]:assert bind(b["path"])==b
    # Original ledger has legitimately advanced; source/scoring files stay immutable.
    for b in read(PILOT/"execution_freeze.json")["inputs"]:assert bind(b["path"])==b
    for b in read(PILOT/"run_01/completion.json")["outputs"]:assert bind(b["path"])==b
    schema={"threshold":.7,"core":bind(Path(core.__file__)),"family":bind(Path(family.__file__)),
            "script":bind(__file__),"baseline_results":bind(PILOT/"run_01/results.json")}
    encoder=None;results=[];rows=[];missing=[]
    for request in read(HERE/"matrix.json"):
        rid=request["request_id"]
        terminal_path=HERE/"returns"/rid/"terminal.json"
        if not terminal_path.exists():missing.append({"request_id":rid,"reason":"not_yet_returned"});continue
        terminal=read(terminal_path)
        if not terminal.get("translation"):
            missing.append({"request_id":rid,"reason":terminal["status"]});continue
        assert bind(terminal["translation"]["path"])==terminal["translation"]
        key=core.digest([schema,bind(terminal_path),terminal["translation"]])
        saved_path=OUT/(rid+".json")
        if saved_path.exists():
            result=read(saved_path)
            assert result["calculation_identity"]==key,"Changed score input; use a separate result version"
        else:
            english=text(terminal["translation"]["path"]);source=text(request["source"]["path"])
            aid=request["answer_id"];case=cases[aid]
            method,declared,version,pool=family.resolve({**case,"model_response":english},case["references"])
            steps=core.segment(english)
            if encoder is None:
                encoder=CachedEncoder()
                assert encoder.identity==read(PILOT/"run_01/encoder_provenance.json")["identity"]
            candidates=[]
            for i,ref in enumerate(pool):
                score=encoder.score(ref,steps,.7)
                score["reference_hits"]=sum(m["matched"] for m in score["matches"])
                score["generated_hits"]=sum(v>=.7 for v in score.get("generated_max_similarity",[]))
                rt=[s["text"] if isinstance(s,dict) else s for s in ref["steps"]]
                gt=[s["text"] for s in steps]
                matrix=(encoder.encode(rt)@encoder.encode(gt).T).tolist() if gt else [[] for _ in rt]
                candidates.append({"reference_id":ref["reference_id"],"version_id":ref["version_id"],"fixed_order":i,
                                   "source_path":ref["source_path"],"source_url":ref.get("source_url"),"score":score,"similarity_matrix":matrix})
            best=max(candidates,key=lambda c:(c["score"]["sr"],c["score"]["sp"],-c["fixed_order"])) if candidates else None
            result={"request_id":rid,"answer_id":aid,"question_id":case["question_id"],"generator_model":case["generator_model"],
                    "representation":"qwen_fulltext_English","condition":request["condition"],"source":request["source"],
                    "translation":terminal["translation"],"terminal":bind(terminal_path),"calculation_identity":key,
                    "method":method,"declared_route":declared,"version_selection":version,"generated_steps":steps,
                    "all_candidates":candidates,"selected":best,"missing_reason":None if best else "route_or_reference_unresolved",
                    "translation_audit":audit(source,english),"score_eligibility":"raw_diagnostic_pending_translation_review",
                    "fresh_full_CCE_judgment":False,"expert_verified":False}
            write(saved_path,result)
        results.append(result)
        score=result["selected"]["score"] if result["selected"] else {}
        old_r=old_by[(result["answer_id"],"original",result["condition"])]["selected"]["score"]
        author=old_by[(result["answer_id"],"english_author",result["condition"])]["selected"]["score"]
        a=result["translation_audit"]
        row={"request_id":rid,"answer_id":result["answer_id"],"condition":result["condition"],"original_sr":old_r["sr"],"original_sp":old_r["sp"],
             "author_english_sr":author["sr"],"author_english_sp":author["sp"],"qwen_english_sr":score.get("sr"),"qwen_english_sp":score.get("sp"),
             "reference_hits":score.get("reference_hits"),"reference_n":score.get("reference_n"),"generated_hits":score.get("generated_hits"),"generated_n":score.get("generated_n"),
             "same_numbered_unit_sequence":a["same_numbered_unit_sequence"],"numbers_equal":a["whole_text_number_tokens_equal"],
             "number_flag_units":";".join(a["number_flag_units"]),"time_flag_units":";".join(a["time_flag_units"]),"CJK_remaining":a["CJK_remaining"],
             "raw_diagnostic_only_pending_fidelity_review":True,"translation_path":result["translation"]["path"]}
        rows.append(row)
        print(json.dumps({k:row[k] for k in ["request_id","qwen_english_sr","qwen_english_sp","generated_n","numbers_equal","number_flag_units","time_flag_units"]}),flush=True)
    pairs=[]
    by={(r["answer_id"],r["condition"]):r for r in results}
    for r in results:
        if r["condition"]=="baseline" or not r["selected"]:continue
        b=by.get((r["answer_id"],"baseline"))
        if not b or not b["selected"]:continue
        bs,rs=b["selected"],r["selected"]
        lock=next((c for c in r["all_candidates"] if c["reference_id"]==bs["reference_id"]),None)
        pairs.append({"answer_id":r["answer_id"],"condition":r["condition"],"baseline_sr":bs["score"]["sr"],"variant_sr":rs["score"]["sr"],
                      "delta_sr":rs["score"]["sr"]-bs["score"]["sr"],"baseline_sp":bs["score"]["sp"],"variant_sp":rs["score"]["sp"],
                      "delta_sp":rs["score"]["sp"]-bs["score"]["sp"],"reference_switched":bs["reference_id"]!=rs["reference_id"],
                      "locked_delta_sr":lock["score"]["sr"]-bs["score"]["sr"] if lock else None,
                      "locked_delta_sp":lock["score"]["sp"]-bs["score"]["sp"] if lock else None,
                      "translation_validity":"pending_source_review","new_full_CCE_pair":False})
    write(OUT/"results.json",results);write(OUT/"pairs.json",pairs)
    csvwrite(OUT/"per_translation.csv",rows);csvwrite(OUT/"pairs.csv",pairs)
    write(OUT/"summary.json",{"scored_translations":len(results),"pending_or_failed":missing,"pairs":len(pairs),
                               "all_machine_number_checks_pass":all(r["translation_audit"]["whole_text_number_tokens_equal"] for r in results),
                               "new_generative_calls_by_scorer":0,"fidelity_review":"pending_author_semantic_review","config":schema})
    record={"utc":datetime.now(timezone.utc).isoformat(),"command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),"cwd":str(Path.cwd()),
            "config":schema,"scored_rows":len(results),"pending":missing,"new_generative_requests":0,
            "new_local_vectors_this_execution":len(encoder.created) if encoder else 0,
            "new_vector_files":list(encoder.created.values()) if encoder else [],"used_vectors":list(encoder.used.values()) if encoder else []}
    write(OUT/"executions"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+".json"),record)
    print(json.dumps({"scored":len(results),"pending":len(missing),"pairs":len(pairs),"new_generative_requests":0}),flush=True)

if __name__=="__main__":main()
