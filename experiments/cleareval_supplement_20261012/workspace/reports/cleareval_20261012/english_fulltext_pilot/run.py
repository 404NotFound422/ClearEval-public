"""Reparse every frozen full text and score unchanged raw SR/SP, entirely offline."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\ClearEval\ClearEval-public")
R3 = ROOT / "artifacts/cce_validation/optimizer_round3_20261011"
OUT = HERE / "run_01"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
for k in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"]: os.environ[k] = "1"
for k in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"]: os.environ[k] = "2"
def no_network(*args, **kwargs): raise RuntimeError("This full-text pilot uses local encoder assets only")
socket.create_connection = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
import cce_validation as core
import cce_method_family_steps_v1 as family

def read(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def write(p, x): Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
def bind(p): return {"path": str(Path(p).resolve()), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def table(p, rows):
    with Path(p).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

frozen = read(HERE / "execution_freeze.json")
prep = read(HERE / "frozen_inputs.json")
checks = []
def check(name, okay):
    if not okay: raise AssertionError(name)
    checks.append({"name": name, "passed": True})
for item in frozen["inputs"] + prep["inputs"] + [frozen["preparation_freeze"], frozen["ledger"]]:
    check("binding:"+item["path"], bind(item["path"]) == item)
if (OUT / "completion.json").exists():
    done = read(OUT / "completion.json")
    check("reused execution freeze", done["execution_freeze"] == bind(HERE / "execution_freeze.json"))
    for b in done["outputs"]: check("reused output:"+b["path"], bind(b["path"]) == b)
    print(json.dumps({"reused_successful_run": True, "new_generative_requests": 0})); sys.exit(0)
OUT.mkdir(exist_ok=True)
cases = {c["anonymous_answer_id"]: c for c in read(R3 / "confirmation_qwen_01/cases.json")["cases"]}
details = {d["anonymous_answer_id"]: d for d in read(R3 / "confirmation_inputs_01/selected_step_details.json")}
saved = read(R3 / "confirmation_qwen_01/steps.json")
records = read(HERE / "controls.json")
cache_used, cache_created = {}, {}

class ReusedEncoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.memo = {}
        self.local = HERE / "new_embedding_cache"
        self.local.mkdir(exist_ok=True)
        self.search = [self.cache, *family.CACHES, core.ASSETS / "assets/embedding_cache",
                       HERE.parent / "step_language_probe/new_embedding_cache", self.local]
    def encode(self, texts):
        vectors = []
        for text in texts:
            if text not in self.memo:
                key = core.digest([self.identity, text])+".npy"
                paths = [p / key for p in self.search if (p / key).exists()]
                if paths:
                    path = paths[0]
                    cache_used[str(path)] = bind(path)
                    vec = self.np.load(path)
                else:
                    vec = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                    path = self.local / key
                    self.np.save(path, vec)
                    cache_created[str(path)] = bind(path)
                self.memo[text] = vec
            vectors.append(self.memo[text])
        return self.np.asarray(vectors)

encoder = ReusedEncoder()
print(json.dumps({"state": "local_encoder_loaded", "identity": encoder.identity}), flush=True)
results, matrices, rows = [], [], []
for item in records:
    aid, rep, condition = item["answer_id"], item["representation"], item["condition"]
    case, old = cases[aid], details[aid]
    source = Path(item["document"]["path"]).read_bytes().decode("utf-8")
    answer = {**case, "model_response": source}
    method, declared, version, pool = family.resolve(answer, case["references"])
    steps = core.segment(source)
    check("encoder identity:"+aid, encoder.identity == saved[case["case_id"]]["encoder"])
    check("same full candidate pool:"+aid+rep+condition, [r["reference_id"] for r in pool] == old["candidate_reference_ids"])
    if rep == "original" and condition == "baseline":
        check("original full segmentation:"+aid, steps == old["generated_steps"])
        check("original method:"+aid, method == old["comparison_method_id"])
        check("original version:"+aid, version == old["version_selection"])
    candidates = []
    for i, ref in enumerate(pool):
        score = encoder.score(ref, steps, .7)
        score["reference_hits"] = sum(m["matched"] for m in score["matches"])
        score["generated_hits"] = sum(x >= .7 for x in score.get("generated_max_similarity", []))
        rtexts = [s["text"] if isinstance(s, dict) else s for s in ref["steps"]]
        gtexts = [s["text"] for s in steps]
        matrix = encoder.encode(rtexts) @ encoder.encode(gtexts).T
        matrices.append({"answer_id": aid, "representation": rep, "condition": condition,
                         "reference_id": ref["reference_id"], "reference_texts": rtexts,
                         "generated_texts": gtexts, "similarities": matrix.tolist(), "dtype": str(matrix.dtype)})
        if rep == "original" and condition == "baseline":
            prior = old["all_candidates"][i]["score"]
            check("original raw scores:"+aid+ref["reference_id"], all(score[k] == prior[k] for k in ["sr", "sp", "reference_hits", "generated_hits"]))
            check("original cosine maxima:"+aid+ref["reference_id"], max(abs(x["similarity"]-y["similarity"]) for x,y in zip(score["matches"], prior["matches"])) < 1e-6)
        candidates.append({"reference_id": ref["reference_id"], "version_id": ref["version_id"],
                           "fixed_order": i, "source_path": ref["source_path"], "source_url": ref.get("source_url"), "score": score})
    best = max(candidates, key=lambda x: (x["score"]["sr"], x["score"]["sp"], -x["fixed_order"]))
    result = {**item, "question_id": case["question_id"], "generator": case["generator_model"],
              "comparison_method_id": method, "declared_route": declared, "version_selection": version,
              "generated_steps": steps, "all_candidates": candidates, "selected": best,
              "formal_eligible": False, "scope": "fulltext step-metric development diagnostic"}
    results.append(result)
    row = {"answer_id": aid, "question_id": case["question_id"], "generator": case["generator_model"],
           "representation": rep, "condition": condition, "method": method, "reference_id": best["reference_id"],
           **{k: best["score"][k] for k in ["sr", "sp", "reference_hits", "reference_n", "generated_hits", "generated_n"]},
           "source_path": best["source_path"], "source_url": best["source_url"], "text_path": item["document"]["path"]}
    rows.append(row)
    write(OUT / "per_document_partial.json", results)
    print(json.dumps({k: row[k] for k in ["answer_id", "representation", "condition", "sr", "sp", "generated_n"]}), flush=True)

lookup = {(x["answer_id"], x["representation"], x["condition"]): x for x in results}
pairs = []
for r in results:
    if r["condition"] == "baseline": continue
    b = lookup[(r["answer_id"], r["representation"], "baseline")]
    br, vr = b["selected"], r["selected"]
    locked = next(c for c in r["all_candidates"] if c["reference_id"] == br["reference_id"])
    pairs.append({"answer_id": r["answer_id"], "representation": r["representation"], "condition": r["condition"],
                  "baseline_sr": br["score"]["sr"], "variant_sr": vr["score"]["sr"], "delta_sr": vr["score"]["sr"]-br["score"]["sr"],
                  "baseline_sp": br["score"]["sp"], "variant_sp": vr["score"]["sp"], "delta_sp": vr["score"]["sp"]-br["score"]["sp"],
                  "baseline_n": br["score"]["generated_n"], "variant_n": vr["score"]["generated_n"],
                  "reference_switched": br["reference_id"] != vr["reference_id"],
                  "locked_delta_sr": locked["score"]["sr"]-br["score"]["sr"],
                  "locked_delta_sp": locked["score"]["sp"]-br["score"]["sp"]})
check("request ledger unchanged", bind(frozen["ledger"]["path"]) == frozen["ledger"])
write(OUT / "results.json", results)
write(OUT / "similarity_matrices.json", matrices)
write(OUT / "pairs.json", pairs)
table(OUT / "per_document.csv", rows)
table(OUT / "pairs.csv", pairs)
write(OUT / "verification.json", {"checks": checks, "passed": True, "original_baselines_reproduced": 8,
                                   "new_generative_requests": 0, "implementation_checks_not_scientific_accuracy": True})
write(OUT / "encoder_provenance.json", {"identity": encoder.identity, "used_cache": list(cache_used.values()),
                                         "created_cache": list(cache_created.values()), "new_local_vectors": len(cache_created)})
write(OUT / "execution.json", {"utc": datetime.now(timezone.utc).isoformat(),
                               "command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]),
                               "cwd": str(Path.cwd()), "execution_freeze": bind(HERE / "execution_freeze.json"),
                               "new_generative_requests": 0, "ledger_after": bind(frozen["ledger"]["path"])})
write(OUT / "completion.json", {"execution_freeze": bind(HERE / "execution_freeze.json"),
                                "outputs": [bind(p) for p in OUT.iterdir() if p.is_file() and p.name != "completion.json"],
                                "rows": len(rows), "pairs": len(pairs), "status": "complete_step_metric_pilot"})
print(json.dumps({"complete": True, "rows": len(rows), "pairs": len(pairs), "new_local_vectors": len(cache_created), "new_generative_requests": 0}), flush=True)
