"""Freeze paired, full-document edits before encoding or observing their scores."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\ClearEval\ClearEval-public")
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import cce_validation as core
import cce_method_family_steps_v1 as family

def read(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
def bind(p): return {"path": str(Path(p).resolve()), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def text(p): return Path(p).read_bytes().decode("utf-8")

specs = {
    "R3C04": {"merge": [47, 48], "delete": list(range(47, 53)),
               "crossrefs": {29: "5.1", 33: "6.1", 40: "8.1"},
               "deletion_target": "Reported post-labeling dehydration sequence, steps 10.1–10.6; earlier pretreatment dehydration retained"},
    "R3C07": {"merge": [28, 29], "delete": list(range(28, 33)), "crossrefs": {},
               "deletion_target": "Reported THF dehydration sequence, steps 6.1–6.5"},
}
documents = read(HERE / "documents.json")
frozen = read(HERE / "frozen_inputs.json")
for b in frozen["inputs"] + [frozen["ledger"]]:
    assert bind(b["path"]) == b
cases = {c["anonymous_answer_id"]: c for c in read(frozen["inputs"][0]["path"])["cases"]}
records, preflight = [], []
lead = re.compile(r"^(\s*(?:\*\*)?)(\d+)(\.\d+(?:\.\d+)*|)(\s+)")

for d in documents:
    aid = d["answer_id"]
    for representation, path_key in [("original", "original_path"), ("english_author", "english_path")]:
        source = text(d[path_key])
        answer = {**cases[aid], "model_response": source}
        method, declared, version, pool = family.resolve(answer, cases[aid]["references"])
        preflight.append({"answer_id": aid, "representation": representation,
                          "basic_reference_only_resolver": core.selected_route(source, cases[aid]["references"])[0],
                          "existing_family_resolver": method, "version": version,
                          "candidate_ids": [r["reference_id"] for r in pool],
                          "parsed_steps": len(core.segment(source))})
        records.append({"answer_id": aid, "representation": representation, "condition": "baseline",
                        "document": bind(d[path_key]), "edits": []})
        if aid not in specs:
            continue
        spec = specs[aid]
        original_lines = source.splitlines(keepends=True)
        for condition in ["renumber_operations", "merge_adjacent_operations", "delete_reported_core_operations"]:
            lines = original_lines.copy()
            edits = []
            if condition == "renumber_operations":
                for i, line in enumerate(lines):
                    old = line
                    m = lead.match(line)
                    if m:
                        line = lead.sub(lambda x: x[1]+str(int(x[2])+100)+x[3]+x[4], line, count=1)
                    if i in spec["crossrefs"]:
                        ref = spec["crossrefs"][i]
                        head, tail = ref.split(".", 1)
                        assert line.count(ref) == 1
                        line = line.replace(ref, str(int(head)+100)+"."+tail, 1)
                    if line != old:
                        lines[i] = line
                        edits.append({"source_line_index": i, "before": old, "after": line})
            elif condition == "merge_adjacent_operations":
                i, j = spec["merge"]
                assert j == i+1
                m = lead.match(lines[j])
                assert m
                # Retain the first operation label and both complete bodies, in order.
                joined = lines[i].rstrip("\r\n ")+" "+lines[j][m.end():]
                edits.append({"source_line_indices": [i, j], "before": lines[i]+lines[j], "after": joined})
                lines[i], lines[j] = joined, ""
            else:
                for i in spec["delete"]:
                    assert lead.match(lines[i]) and "Time:" in lines[i]
                    edits.append({"source_line_index": i, "before": lines[i], "after": ""})
                    lines[i] = ""
            edited = "".join(lines)
            assert edited != source
            folder = HERE / "controls" / aid / representation
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (condition+".txt")
            path.write_text(edited, encoding="utf-8", newline="")
            records.append({"answer_id": aid, "representation": representation, "condition": condition,
                            "document": bind(path), "baseline_document": bind(d[path_key]), "edits": edits,
                            "deletion_target": spec["deletion_target"] if condition.startswith("delete") else None,
                            "expert_verified": False})

assert len(records) == 28
write(HERE / "controls.json", records)
write(HERE / "interface_preflight.json", {
    "observed_before_scoring": True, "rows": preflight,
    "decision": "Reuse existing cce_method_family_steps_v1.resolve, which generated archived scores; do not replace it with the lower-level reference-only resolver.",
    "new_parser_or_route_fix": False,
    "C04_heading_issue": "Full English nuclear-staining heading passes existing word-count/operation heuristic: 36 to 37 parsed steps. Retained without tuning translation or parser.",
})
write(HERE / "execution_plan.json", {
    "created_utc": datetime.now(timezone.utc).isoformat(), "frozen_before_scores": True,
    "conditions": ["baseline", "renumber_operations", "merge_adjacent_operations", "delete_reported_core_operations"],
    "full_text_positions": 28, "paired_differences": 12, "natural_answer_n": 8,
    "threshold": .7, "route_resolver": "unchanged cce_method_family_steps_v1.resolve",
    "segmentation": "unchanged cce_validation.segment on each edited full text",
    "reference_policy": "all compatible complete versions; max SR, same-version SP, fixed order; additionally report baseline-reference-locked deltas",
    "deletion_scope": "Author-defined reported core blocks, not newly expert-confirmed mandatory-operation adjudications",
    "scientific_claims": "development diagnostic, not new full-CCE evaluation, not independent translation verification",
    "new_generative_requests": 0, "control_specs": specs,
})
paths = [Path(__file__), HERE / "controls.json", HERE / "execution_plan.json", HERE / "interface_preflight.json",
         HERE / "run.py", Path(family.__file__), ROOT / "scripts/cce_expand_references_v5.py"]
paths += [Path(r["document"]["path"]) for r in records]
assets = core.ASSETS / "assets/all-mpnet-base-v2"
paths += [p for p in assets.rglob("*") if p.is_file()]
write(HERE / "execution_freeze.json", {"inputs": [bind(p) for p in dict.fromkeys(paths)],
                                      "preparation_freeze": bind(HERE / "frozen_inputs.json"),
                                      "ledger": frozen["ledger"], "frozen_before_scoring": True})
print(json.dumps({"full_text_positions": len(records), "paired_differences": 12,
                  "existing_family_resolver_reused": True, "new_generative_requests": 0}))
