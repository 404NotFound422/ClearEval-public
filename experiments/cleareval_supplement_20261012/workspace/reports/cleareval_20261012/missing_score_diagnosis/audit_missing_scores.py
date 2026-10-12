"""Read saved results and source evidence; never invoke or modify a scorer/model."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path("C:/ClearEval")
REPO = ROOT / "ClearEval-public"
OUT = Path(__file__).resolve().parent
RESULTS = OUT.parent / "scorer_revision/with_decomposition/results.json"
CELLS = REPO / "artifacts/cce_validation/optimizer_round3_20261011/uniform_v7/actual_01/cells.json"
OBS = REPO / "artifacts/cce_validation/optimizer_round2_20261010/grounded_controls_v11/observations.csv"
snapshots = {}
cache = {}
checks = Counter()


def read_bytes(path, expected=None):
    path = Path(path).resolve()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None:
        assert digest == expected, (str(path), "input hash mismatch")
        checks["bound_file_hash_matches"] += 1
    snapshots[str(path)] = digest
    return data


def load(path, expected=None):
    path = str(Path(path).resolve())
    if path not in cache:
        cache[path] = json.loads(read_bytes(path, expected).decode("utf-8-sig"))
    elif expected is not None:
        assert snapshots[path] == expected, (path, "cached input hash mismatch")
        checks["bound_file_hash_matches"] += 1
    return cache[path]


def pointer(path):
    path = str(Path(path).resolve())
    return {"path": path, "sha256": snapshots[path]}


def category(row):
    if row["metrics"]["s_label"] is not None:
        return "label_available"
    lab = row.get("label_derivation")
    dep = row.get("remaining_dependencies", {})
    if not lab:
        return "partial_record"
    if lab.get("original_occurrence_numeric_label") is not None:
        return "numeric_minimum_then_withheld"
    if dep.get("compatibility") and dep.get("label_relations"):
        return "lookup_and_relation"
    if dep.get("compatibility"):
        return "lookup_only"
    if dep.get("label_relations"):
        return "relation_only"
    return "empty_applicable_channels"


results = load(RESULTS)
cells = {c["cell_id"]: c for c in load(CELLS)}
observations = list(csv.DictReader(read_bytes(OBS).decode("utf-8-sig").splitlines()))
records = []
documents = {}
raw_records = {}
cancelled = []

for row in results:
    cell = cells[row["cell_id"]]
    if not cell.get("posthoc_record"):
        cancelled.append({"cell_id": row["cell_id"], "status": row["status"]})
        continue
    post_path = cell["posthoc_record"]["path"]
    post = load(post_path, cell["posthoc_record"]["sha256"])
    assert row["source_record"]["sha256"] == cell["posthoc_record"]["sha256"]
    checks["same_posthoc_input"] += 1
    raw_binding = next(b for b in cell["source_bindings"]
                       if Path(b["path"]).name in ("raw_response.txt", "raw_source_bound_content.txt")
                       and b["sha256"] == cell["raw_sha256"])
    raw = load(raw_binding["path"], raw_binding["sha256"])
    raw_records[row["cell_id"]] = raw
    source_id = raw.get("grounded_extraction", {}).get("source_id")
    matched = []
    for binding in cell["source_bindings"]:
        if "source_documents" not in Path(binding["path"]).parts:
            continue
        doc = load(binding["path"], binding["sha256"])
        answer_hash = row.get("answer_sha256")
        if (answer_hash and doc["answer_sha256"] == answer_hash) or (
            not answer_hash and doc["source_id"] == source_id
        ):
            matched.append((binding["path"], doc))
    assert matched, (row["cell_id"], "no source matching this answer")
    assert len({d["answer_sha256"] for _, d in matched}) == 1
    doc_path, doc = matched[0]
    assert hashlib.sha256(doc["text"].encode("utf-8")).hexdigest() == doc["answer_sha256"]
    assert all(doc["text"][u["start"]:u["end"]] == u["text"] for u in doc["units"])
    assert source_id == doc["source_id"]
    checks["answer_and_unit_binding"] += 1
    documents[row["cell_id"]] = doc
    lab = row.get("label_derivation", {})
    dep = row.get("remaining_dependencies", {})
    cor = raw["scores"]["correctness"]
    for key in ("co_order", "co_method", "co_param", "co_chem"):
        assert cor[key]["score"] == row["metrics"][key], (row["cell_id"], key)
        checks["direct_correctness_raw_value_preserved"] += 1
    lookup = [{k: x.get(k) for k in ("marker", "fluorophore", "status", "value", "column",
                                    "selected_row_indices", "per_scope_evidence")}
              for x in row.get("compatibility_lookup_trace", [])]
    control = next((o for o in observations
                    if o.get("anonymous_answer_id") == row["anonymous_answer_id"]), None)
    # CSV may call this identifier answer_id. Retain only identifiers, not stale scores.
    if control is None:
        control = next((o for o in observations
                        if row["anonymous_answer_id"] in (o.get("answer_id"), o.get("blind_id"))), None)
    records.append({
        "cell_id": row["cell_id"], "cohort": row["cohort"],
        "anonymous_answer_id": row["anonymous_answer_id"], "question_id": row["question_id"],
        "source_document": pointer(doc_path), "answer_sha256": doc["answer_sha256"],
        "posthoc_record": pointer(post_path), "raw_response": pointer(raw_binding["path"]),
        "raw_is_valid_json": True,
        "metrics": row["metrics"], "complete_numeric_CCE": row["complete_numeric_CCE"],
        "missing_components": [k for k in ("Cor", "s_label", "s_time") if row["metrics"][k] is None],
        "label_category": category(row), "label_channels": lab.get("channels"),
        "label_min_before_publication_gate": lab.get("original_occurrence_numeric_label"),
        "label_uncertainties": dep.get("label_relations", []),
        "compatibility_issues": dep.get("compatibility", []), "lookup_trace": lookup,
        "time_derivation": row.get("time_derivation"),
        "raw_missing_correctness": {k: cor[k] for k in ("co_order", "co_method", "co_param", "co_chem")
                                    if cor[k]["score"] is None},
        "full_conversion_failure": post.get("full_conversion_or_scoring_failure"),
        "source_Time_field_count": doc["text"].count("Time:"),
        "control_identity": {k: v for k, v in (control or {}).items()
                             if k in ("answer_id", "anonymous_answer_id", "case_id", "response_id", "source_id", "blind_id")},
    })

metric_counts = {k: sum(r["metrics"][k] is None for r in records)
                 for k in ("Com", "Cor", "s_method", "s_label", "s_trans", "s_time", "Eff")}
label_counts = Counter(r["label_category"] for r in records if r["metrics"]["s_label"] is None)
combos = Counter("+".join(r["missing_components"]) or "complete" for r in records)
assert len(records) == 67 and len(cancelled) == 1
assert metric_counts == {"Com": 0, "Cor": 11, "s_method": 0, "s_label": 56,
                         "s_trans": 0, "s_time": 6, "Eff": 56}
assert dict(label_counts) == {"relation_only": 21, "lookup_only": 9, "lookup_and_relation": 12,
                             "empty_applicable_channels": 7, "partial_record": 2,
                             "numeric_minimum_then_withheld": 5}
assert combos == {"s_label": 40, "Cor+s_label": 10, "Cor": 1, "s_label+s_time": 6, "complete": 10}
assert all(r["cohort"] == "Codex" and r["raw_missing_correctness"]["co_param"]["score"] is None
           for r in records if r["metrics"]["Cor"] is None)
checks["descriptive_count_partitions"] += 4

selections = {
    "E2_01": ["L0002", "L0003"], "E2_03": ["L0007"],
    "E2_07": ["L0007"], "E2_11": ["L0007"],
    "A03": ["L0002", "L0009", "L0011"],
    "A04": ["L0002", "L0003", "L0012", "L0014"],
    "A05__codex_unobserved__r1": ["L0002", "L0003", "L0006"],
    "FPC02": ["L0014", "L0015"],
    "FPC04": ["L0015", "L0019", "L0069", "L0075", "L0077", "L0083"],
    "FPC05": ["L0006", "L0007", "L0008", "L0009", "L0019", "L0028", "L0029", "L0033"],
    "FPC09": ["L0002"],
    "FPC13": ["L0002", "L0003", "L0025", "L0026"],
    "FPC16": ["L0002", "L0003"],
    "A01__codex_unobserved__r1": ["L0002", "L0003"],
}
examples = []
for key, units in selections.items():
    record = next(r for r in records if r["cell_id"] == key or r["anonymous_answer_id"] == key)
    doc = documents[record["cell_id"]]
    selected = [u for u in doc["units"] if u["unit_id"] in units]
    assert len(selected) == len(units)
    examples.append({"example": key, "cell_id": record["cell_id"],
                     "source_document": record["source_document"], "source_units": selected})

fpc16 = raw_records["FPC16"]["grounded_extraction"]
ids = {e["i"] for e in fpc16["entities"]}
dangling = [{"relation": r, "missing_entity_ids": [r[k] for k in ("f", "t")
             if r.get(k) is not None and r[k] not in ids]} for r in fpc16["relations"]]
dangling = [r for r in dangling if r["missing_entity_ids"]]
assert dangling[0]["missing_entity_ids"] == ["axonal"]
a01 = raw_records["A01__codex_unobserved__r1"]["grounded_extraction"]
pi = next(e for e in a01["entities"] if e["n"] == "PI")
line = next(u["text"] for u in documents["A01__codex_unobserved__r1"]["units"] if u["unit_id"] == pi["u"])
pi_detail = {"raw_entity": pi, "source_unit": line,
             "substring_count": len(list(re.finditer("PI", line))),
             "complete_word_count": len(list(re.finditer(r"(?<!\w)PI(?!\w)", line))),
             "note": "Simple lexical check; full conversion was not rerun. Complete-name indexing is zero based."}
assert pi_detail["substring_count"] == 2 and pi_detail["complete_word_count"] == 1 and pi["a"] == 1
checks["partial_record_specific_evidence"] += 2

source_code = {
    "publication_gate": (REPO / "scripts/cce_label_occurrence_diagnostic_v1.py", 202, 203),
    "complete_name_index": (REPO / "scripts/cce_grounded_extraction_fieldwise_base_v1.py", 850, 863),
    "correctness_rubric": (REPO / "prompts/eval_oeq_teacher_rubric.txt", 193, 203),
}
code_evidence = {}
for key, (path, start, end) in source_code.items():
    lines = read_bytes(path).decode("utf-8-sig").splitlines()
    code_evidence[key] = {**pointer(path), "first_line": start, "last_line": end,
                          "text": "\n".join(lines[start - 1:end])}
tissue = load(REPO / "KnowledgeBase/tissue.json")
table_columns = sorted({k for row in tissue for k in row})
assert not any("594" in c for c in table_columns)
checks["no_594_column_in_current_tissue_table"] += 1

evidence = {
    "purpose": "Missing-score diagnosis for user decision; no score or policy changes",
    "scope": "Same 68 historical slots as the prior scorer-revision report; 67 saved returns, not independent answers",
    "new_model_calls": 0, "new_expert_records": 0, "scoring_reexecuted": False,
    "results_source": pointer(RESULTS), "cells_source": pointer(CELLS),
    "saved_returns": len(records), "cancelled_without_return": cancelled,
    "complete_numeric_CCE": sum(r["complete_numeric_CCE"] for r in records),
    "missing_metric_counts": metric_counts, "exclusive_label_categories": dict(label_counts),
    "exclusive_missing_combinations": dict(combos),
    "records": records, "examples": examples, "code_evidence": code_evidence,
    "partial_record_details": {"FPC16": dangling, "A01__codex_unobserved__r1": pi_detail},
    "tissue_table": {**pointer(REPO / "KnowledgeBase/tissue.json"), "columns": table_columns},
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
columns = ["cell_id", "cohort", "question_id", "complete_numeric_CCE", "label_category",
           "missing_components", "Com", "Cor", "Eff", "s_label", "s_time", "source_path", "raw_response_path"]
with (OUT / "per_record.csv").open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=columns)
    writer.writeheader()
    for r in records:
        writer.writerow({**{k: r[k] for k in columns if k in r},
                         "missing_components": ";".join(r["missing_components"]),
                         **{k: r["metrics"][k] for k in ("Com", "Cor", "Eff", "s_label", "s_time")},
                         "source_path": r["source_document"]["path"],
                         "raw_response_path": r["raw_response"]["path"]})
for path, digest in snapshots.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, (path, "input changed")
checks["input_files_unchanged"] = len(snapshots)
verification = {"status": "PASS", "analysis_status": "ANALYZED_NOT_NEW_SCORER_VALIDATION",
                "checks": dict(checks), "inputs": snapshots,
                "new_model_calls": 0, "scoring_reexecuted": False}
(OUT / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"saved_returns": len(records), "complete_numeric_CCE": evidence["complete_numeric_CCE"],
                  "missing_counts": metric_counts, "exclusive_label_categories": dict(label_counts),
                  "checks": dict(checks), "new_model_calls": 0}, ensure_ascii=False))
