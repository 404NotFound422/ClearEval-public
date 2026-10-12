"""Post-hoc offline interventions separating numbering, wording, headers and parsing.

Preserves original Qwen returns and raw scores. No generative requests.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
import subprocess

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE))
import score_translations as s
OUT=HERE/"mechanism_checks"

def shift_labels(value,delta):
    return re.sub(r"^([ \t]*(?:\*\*)?)(\d+)(?=[. \t])",lambda m:m[1]+str(int(m[2])+delta),value,flags=re.M)

def hierarchical_title_spans(text):
    lines=text.splitlines(keepends=True);parsed=[];offset=0
    for line in lines:
        clean=line.strip().replace("**","")
        m=re.match(r"^(\d+(?:\.\d+)*)\s+(.+)",clean)
        parsed.append({"start":offset,"end":offset+len(line),"line":line,
                       "label":m[1] if m else None,"body":m[2] if m else None})
        offset+=len(line)
    titles=[]
    for i,line in enumerate(parsed):
        label=line["label"]
        if not label or "." in label:continue
        # Parameter-bearing parent operations are retained. This is a narrow
        # explicit-hierarchy diagnostic, not a universal semantic heading detector.
        if re.search(r"Temperature:|Time:|\d\s*(?:%|hours?\b|days?\b|min\b|℃|°)",line["body"],re.I):continue
        following=[]
        for later in parsed[i+1:]:
            if later["label"] and "." not in later["label"]:break
            if later["label"]:following.append(later["label"])
        if any(x.startswith(label+".") for x in following):titles.append(line)
    return titles

def main():
    OUT.mkdir(exist_ok=True)
    raw=s.read(HERE/"scoring/results.json")
    by={r["request_id"]:r for r in raw}
    b=by["T05_R3C07_baseline"];r=by["T06_R3C07_renumber_operations"]
    base=s.text(b["translation"]["path"]);ren=s.text(r["translation"]["path"])
    variants=[("baseline_wording_base_numbers",base,b,False),
              ("baseline_wording_shifted_numbers",shift_labels(base,100),b,True),
              ("renumber_wording_base_numbers",shift_labels(ren,-100),r,True),
              ("renumber_wording_shifted_numbers",ren,r,False),
              ("renumber_wording_label_translation_only",ren.replace("内源荧光","endogenous fluorescence"),r,True)]
    ledger=s.ROOT/"artifacts/cce_validation/judges/request_ledger.jsonl"
    before=s.bind(ledger)
    plan={"created_utc":datetime.now(timezone.utc).isoformat(),"stage":"posthoc_development_mechanism_isolation",
          "not_prospective_confirmation":True,"freeze_before_counterfactual_scores":True,
          "interventions":["C07 two actual translation wordings crossed with two numbering schemes",
                           "C07 translate only the residual pre-Protocol label word, leaving scoring text fixed",
                           "Eight returned full texts: compare unchanged parser with explicit parameter-free parent-heading filter"],
          "threshold":.7,"new_generative_calls":0,"raw_Qwen_results_modified":False,
          "hierarchy_candidate_scope":"Only parent numbered lines followed by numbered child entries, with no bound time/temperature/numerical parameters; retain source spans",
          "candidate_not_main_scoring":True,"inputs":[s.bind(HERE/"scoring/results.json"),s.bind(__file__),s.bind(HERE/"score_translations.py")],
          "ledger_before":before}
    s.write(OUT/"plan.json",plan)
    checks=[]
    def check(name,ok):
        assert ok,name
        checks.append({"name":name,"passed":True})
    cases={x["anonymous_answer_id"]:x for x in s.read(s.R3/"confirmation_qwen_01/cases.json")["cases"]}
    encoder=s.CachedEncoder()
    counter=[]
    for name,value,origin,synthetic in variants:
        path=OUT/(name+".txt");path.write_text(value,encoding="utf-8",newline="")
        steps=s.core.segment(value)
        case=cases["R3C07"]
        method,declared,version,pool=s.family.resolve({**case,"model_response":value},case["references"])
        check("same C07 route:"+name,method=="FDISCO" and len(pool)==1)
        score=encoder.score(pool[0],steps,.7)
        counter.append({"condition":name,"document":s.bind(path),"origin_translation":origin["translation"],
                        "synthetic_offline_intervention":synthetic,"score":score,"generated_steps":steps})
    cb={r["condition"]:r for r in counter}
    for left,right in [("baseline_wording_base_numbers","baseline_wording_shifted_numbers"),
                       ("renumber_wording_base_numbers","renumber_wording_shifted_numbers"),
                       ("renumber_wording_shifted_numbers","renumber_wording_label_translation_only")]:
        check("same parsed text:"+left+right,[x["text"] for x in cb[left]["generated_steps"]]==[x["text"] for x in cb[right]["generated_steps"]])
        check("same raw SR/SP:"+left+right,all(cb[left]["score"][k]==cb[right]["score"][k] for k in ["sr","sp"]))
    for name,origin in [("baseline_wording_base_numbers",b),("renumber_wording_shifted_numbers",r)]:
        check("reproduce actual return:"+name,all(cb[name]["score"][k]==origin["selected"]["score"][k] for k in ["sr","sp"]))
    hierarchy=[]
    for result in raw:
        value=s.text(result["translation"]["path"])
        steps=s.core.segment(value)
        check("reparse full Qwen text:"+result["request_id"],steps==result["generated_steps"])
        title_by={t["start"]:t for t in hierarchical_title_spans(value)}
        kept=[x for x in steps if x["start"] not in title_by]
        removed=[{"old_generated_index":i,"step":x,"title_evidence":title_by[x["start"]],
                  "old_generated_max_similarity":result["selected"]["score"]["generated_max_similarity"][i]}
                 for i,x in enumerate(steps) if x["start"] in title_by]
        case=cases[result["answer_id"]]
        method,declared,version,pool=s.family.resolve({**case,"model_response":value},case["references"])
        candidates=[{"reference_id":ref["reference_id"],"fixed_order":i,"score":encoder.score(ref,kept,.7)} for i,ref in enumerate(pool)]
        best=max(candidates,key=lambda c:(c["score"]["sr"],c["score"]["sp"],-c["fixed_order"]))
        hierarchy.append({"request_id":result["request_id"],"answer_id":result["answer_id"],"condition":result["condition"],
                          "raw_sr":result["selected"]["score"]["sr"],"raw_sp":result["selected"]["score"]["sp"],"raw_n":len(steps),
                          "candidate_sr":best["score"]["sr"],"candidate_sp":best["score"]["sp"],"candidate_n":len(kept),
                          "removed_heading_n":len(removed),"removed_headings":removed,"candidate_selection":best,
                          "candidate_all_references":candidates,"candidate_steps":kept,"main_score_replaced":False})
    margins=[]
    for left,right in zip(b["selected"]["score"]["matches"],r["selected"]["score"]["matches"]):
        margins.append({"reference_index":left["reference_index"],"reference_text":left["reference_text"],
                        "baseline_cosine":left["similarity"],"renumber_translation_cosine":right["similarity"],
                        "cosine_difference":right["similarity"]-left["similarity"],"baseline_margin_to_threshold":left["similarity"]-.7,
                        "renumber_margin_to_threshold":right["similarity"]-.7,
                        "baseline_generated_text":left["generated_text"],"renumber_generated_text":right["generated_text"],
                        "threshold_crossed":left["matched"]!=right["matched"]})
    check("no generative request or ledger change",s.bind(ledger)==before)
    s.write(OUT/"numbering_wording_factorial.json",counter)
    s.write(OUT/"hierarchy_diagnostic.json",hierarchy)
    s.write(OUT/"threshold_crossings.json",margins)
    s.csvwrite(OUT/"factorial.csv",[{"condition":r["condition"],"synthetic_offline_intervention":r["synthetic_offline_intervention"],
                                      "sr":r["score"]["sr"],"sp":r["score"]["sp"],"generated_n":r["score"]["generated_n"]} for r in counter])
    s.csvwrite(OUT/"hierarchy.csv",[{k:r[k] for k in ["request_id","answer_id","condition","raw_sr","raw_sp","raw_n","candidate_sr","candidate_sp","candidate_n","removed_heading_n"]} for r in hierarchy])
    s.write(OUT/"verification.json",{"passed":True,"checks":checks,"new_generative_requests":0,"ledger_after":s.bind(ledger),
                                      "new_local_vectors":len(encoder.created),"cached_vector_sources":list(encoder.used.values()),"plan":s.bind(OUT/"plan.json")})
    s.write(OUT/"execution.json",{"command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),"finished_utc":datetime.now(timezone.utc).isoformat(),"new_generative_requests":0})
    print(json.dumps({"factorial":[{"condition":r["condition"],"sr":r["score"]["sr"],"sp":r["score"]["sp"]} for r in counter],
                      "hierarchy":[{k:r[k] for k in ["request_id","raw_n","candidate_n","candidate_sr","candidate_sp"]} for r in hierarchy],
                      "new_local_vectors":len(encoder.created),"new_generative_requests":0}),flush=True)

if __name__=="__main__":main()
