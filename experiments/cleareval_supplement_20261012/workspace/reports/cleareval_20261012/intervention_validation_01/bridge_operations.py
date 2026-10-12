"""Reuse actual source-bound model operation records on two saved translations.

An auxiliary baseline-only bridge. No model calls, new embeddings, edited
answers, expert labels, or changes to the existing main scoring artifacts.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DAY = HERE.parent
QWEN = DAY / "english_fulltext_pilot/qwen_translation_pending"
REPO = Path(r"C:\ClearEval\ClearEval-public")
sys.path[:0] = [str(QWEN), str(REPO / "scripts")]
import score_translations as io
import cce_representation_repair_v3 as previous_view
import numpy as np


def main():
    old_path = DAY / "automatic_time_scope/canonical32_04/results.json"
    score_path = QWEN / "scoring/results.json"
    ledger = REPO / "artifacts/cce_validation/judges/request_ledger.jsonl"
    bindings = [io.bind(old_path), io.bind(score_path), io.bind(ledger), io.bind(__file__)]
    old = {r["cell_id"]: r for r in io.read(old_path)}
    results = []
    for r in io.read(score_path):
        if r["condition"] != "baseline":
            continue
        aid = r["answer_id"]
        archived = old[aid + "__r0"]
        doc = io.read(archived["source_document"]["path"])
        post = io.read(archived["post_record"]["path"])
        source = io.text(r["source"]["path"])
        english = io.text(r["translation"]["path"])
        assert previous_view.canonicalize_full_text(source)["evaluation_text"] == doc["text"]
        assert io.core.segment(english) == r["generated_steps"]
        bindings.extend([r["source"], r["translation"], archived["source_document"], archived["post_record"]])
        units = {u["unit_id"]: u for u in doc["units"]}
        translation_units = {u["unit_id"]: u for u in r["translation_audit"]["unit_pairs"]}
        translated_operations = []
        for op in post["conversion"]["source_audit"]["resolved"]["operations"]:
            origin = op["operation"]
            assert doc["text"][origin["start"]:origin["end"]] == origin["quote"]
            label = re.match(r"\s*(\d+(?:\.\d+)*)\s+", units[origin["unit_id"]]["text"])[1]
            paired = translation_units[label]
            indices = [i for i, g in enumerate(r["generated_steps"]) if paired["english"]["start"] <= g["start"] < paired["english"]["end"]]
            assert indices, (aid, label)
            translated_operations.append({"operation_id": op["id"], "source_label": label, "original_evidence": origin,
                                           "translation_evidence": paired["english"], "generated_indices": indices})
        kept = sorted({i for op in translated_operations for i in op["generated_indices"]})
        candidates = []
        for c in r["all_candidates"]:
            matrix = np.asarray(c["similarity_matrix"])[:, kept]
            rh = int((matrix.max(axis=1) >= .7).sum())
            gh = int((matrix.max(axis=0) >= .7).sum())
            candidates.append({"reference_id": c["reference_id"], "fixed_order": c["fixed_order"], "reference_hits": rh, "reference_n": matrix.shape[0],
                               "generated_hits": gh, "generated_n": matrix.shape[1], "sr": rh / matrix.shape[0], "sp": gh / matrix.shape[1]})
        best = max(candidates, key=lambda c: (c["sr"], c["sp"], -c["fixed_order"]))
        removed = [{"generated_index": i, "text": g["text"], "start": g["start"], "end": g["end"]} for i, g in enumerate(r["generated_steps"]) if i not in kept]
        results.append({"request_id": r["request_id"], "answer_id": aid, "raw_sr": r["selected"]["score"]["sr"], "raw_sp": r["selected"]["score"]["sp"],
                        "raw_generated_n": len(r["generated_steps"]), "reused_model_operations": len(translated_operations), "operation_to_translation": translated_operations,
                        "excluded_parser_entries": removed, "candidate_all_references": candidates, "candidate_selected": best,
                        "interpretation": "Operation inventory transferred using actual numbered-source/translation alignment. Assistant-reviewed translation; no expert accuracy claim.",
                        "main_scores_replaced": False})
    for b in bindings:
        assert io.bind(b["path"]) == b
    io.write(HERE / "operation_bridge_results.json", {"results": results, "bindings": bindings, "new_model_requests": 0, "new_embeddings": 0, "new_expert_records": 0})
    io.write(HERE / "bridge_execution.json", {"command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]), "completed_utc": datetime.now(timezone.utc).isoformat(), "new_model_requests": 0})
    print(json.dumps([{"answer_id": r["answer_id"], "raw_n": r["raw_generated_n"], "reused_operations": r["reused_model_operations"], "excluded": len(r["excluded_parser_entries"]), "candidate_sr": r["candidate_selected"]["sr"], "candidate_sp": r["candidate_selected"]["sp"]} for r in results]))


if __name__ == "__main__":
    main()
