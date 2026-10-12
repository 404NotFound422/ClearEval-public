"""Make a compact, source-addressable readout from the completed full-text run."""
from collections import Counter
from pathlib import Path
import csv
import hashlib
import json

HERE=Path(__file__).resolve().parent
RUN=HERE/"run_01"
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def bind(p):return {"path":str(Path(p).resolve()),"sha256":hashlib.sha256(Path(p).read_bytes()).hexdigest()}
results=read(RUN/"results.json")
docs={r["answer_id"]:r for r in read(HERE/"documents.json")}
lookup={(r["answer_id"],r["representation"],r["condition"]):r for r in results}
baselines=[]
trace=[]
for aid,d in docs.items():
    b=lookup[(aid,"original","baseline")]["selected"]["score"]
    e=lookup[(aid,"english_author","baseline")]["selected"]["score"]
    baselines.append({"answer_id":aid,"question_id":d["question_id"],"generator":d["generator"],
                      "original_sr":b["sr"],"original_sp":b["sp"],"original_step_n":b["generated_n"],
                      "english_sr":e["sr"],"english_sp":e["sp"],"english_step_n":e["generated_n"],
                      "english_reference_hits":e["reference_hits"],"english_reference_n":e["reference_n"],
                      "english_generated_hits":e["generated_hits"],"delta_sr":e["sr"]-b["sr"],"delta_sp":e["sp"]-b["sp"],
                      "translation_is_verbatim":d["English_is_verbatim"],"expert_verified":False})
    if aid not in ["R3C04","R3C07"]:continue
    alignment=read(d["alignment_path"])
    for condition in ["baseline","delete_reported_core_operations"]:
        r=lookup[(aid,"english_author",condition)]
        for m in r["selected"]["score"]["matches"]:
            if not m["matched"]:continue
            step=r["generated_steps"][m["generated_index"]]
            # Original baseline offsets are meaningful only in the baseline text.
            line=next((x for x in alignment if x["english_start"]<=step["start"]<x["english_end"]),None) if condition=="baseline" else None
            trace.append({"answer_id":aid,"condition":condition,"reference_id":r["selected"]["reference_id"],
                          **m,"source_unit_id":line["unit_id"] if line else None,
                          "original_source_line":line["source"] if line else None,
                          "input_document":r["document"],"reference_source_path":r["selected"]["source_path"],
                          "reference_source_url":r["selected"]["source_url"]})
checks=[]
def check(name,x):
    assert x,name
    checks.append({"name":name,"passed":True})
c4=lookup[("R3C04","english_author","baseline")]["selected"]["score"]
d4=lookup[("R3C04","english_author","delete_reported_core_operations")]["selected"]["score"]
c7=lookup[("R3C07","english_author","baseline")]["selected"]["score"]
d7=lookup[("R3C07","english_author","delete_reported_core_operations")]["selected"]["score"]
check("C04 extra title and raw denominator",c4["generated_n"]==37 and c4["generated_hits"]==12 and c4["sp"]==12/37)
check("C04 deletion preserves numerator",d4["sr"]==c4["sr"]==1/3 and d4["generated_hits"]==12 and d4["generated_n"]==31)
check("C07 many reference rows reuse one generated instance",len({m["generated_index"] for m in c7["matches"] if m["matched"]})==1 and c7["reference_hits"]==4)
check("C07 block deletion response",d7["sr"]==d7["sp"]==0 and c7["sr"]==4/7)
pairs=read(RUN/"pairs.json")
check("12 real fulltext pairs",len(pairs)==12)
check("no adaptive reference switching",not any(p["reference_switched"] for p in pairs))
check("all renumber raw scores unchanged",all(p["delta_sr"]==p["delta_sp"]==0 for p in pairs if p["condition"]=="renumber_operations"))
summary={"natural_answers":8,"question_ids":sorted({r["question_id"] for r in baselines}),
         "generator_models":sorted({r["generator"] for r in baselines}),"fulltext_positions":len(results),
         "distinct_fulltext_hashes":len({r["document"]["sha256"] for r in results}),"paired_differences":len(pairs),
         "substantive_nonEnglish_answers":2,"additional_answer_with_one_Chinese_label_word":1,
         "baseline_results":baselines,"pair_results":pairs,"new_generative_requests":0,
         "original_baselines_reproduced":8,"new_local_vectors":read(RUN/"encoder_provenance.json")["new_local_vectors"],
         "new_full_CCE_judgments":0,"new_repeated_judgments":0,"expert_returns":0,
         "interpretation":"Translation changes raw matches; uncorrected phase/instance and segmentation errors persist. Higher scores do not establish higher evaluation accuracy.",
         "checks":checks,"inputs":[bind(RUN/"results.json"),bind(RUN/"pairs.json"),bind(HERE/"documents.json"),bind(__file__)]}
write(HERE/"summary.json",summary)
write(HERE/"match_trace.json",trace)
with (HERE/"baseline_comparison.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(baselines[0]));w.writeheader();w.writerows(baselines)
print(json.dumps({k:summary[k] for k in ["natural_answers","fulltext_positions","distinct_fulltext_hashes","paired_differences","new_local_vectors","new_generative_requests"]}))
