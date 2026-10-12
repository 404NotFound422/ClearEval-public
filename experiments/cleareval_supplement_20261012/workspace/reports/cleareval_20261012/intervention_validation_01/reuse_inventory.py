"""Inspect actual archived decompositions for the eight exposed source answers."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DAY = HERE.parent
REPO = Path(r"C:\ClearEval\ClearEval-public")
sys.path[:0] = [str(DAY / "english_fulltext_pilot/qwen_translation_pending"), str(REPO / "scripts")]
import score_translations as io
import cce_representation_repair_v3 as normalizer


def main():
    source_results = DAY / "automatic_time_scope/canonical32_04/results.json"
    ledger = REPO / "artifacts/cce_validation/judges/request_ledger.jsonl"
    before = io.bind(ledger)
    rows, bindings = [], [io.bind(source_results), io.bind(__file__), io.bind(Path(normalizer.__file__))]
    for old in io.read(source_results):
        if not old["cell_id"].startswith("R3C"):
            continue
        aid = old["cell_id"].split("__")[0]
        path = DAY / "english_fulltext_pilot/documents" / aid / "original.txt"
        bindings.extend([io.bind(path), old["source_document"], old["post_record"]])
        doc, post = io.read(old["source_document"]["path"]), io.read(old["post_record"]["path"])
        assert normalizer.canonicalize_full_text(io.text(path))["evaluation_text"] == doc["text"]
        conversion = post.get("conversion")
        row = {"answer_id": aid, "source": io.bind(path), "saved_source_document": old["source_document"], "saved_processing": old["post_record"],
               "same_canonical_source": True, "has_saved_conversion": conversion is not None, "expert_truth": False, "new_extraction": False}
        if conversion is None:
            row.update(raw_operations=None, source_bound_resolved_operations=None,
                       issue="This processing artifact has no successful conversion; no claim that the original model returned no content.")
        else:
            raw = conversion["raw_content_preserved"]
            assert hashlib.sha256(raw.encode()).hexdigest() == post["raw_sha256"]
            operations = json.loads(raw)["grounded_extraction"]["operations"]
            resolved = conversion["source_audit"]["resolved"]["operations"]
            for operation in resolved:
                span = operation["operation"]
                assert doc["text"][span["start"]:span["end"]] == span["quote"]
            row.update(raw_operations=len(operations), source_bound_resolved_operations=len(resolved), raw_response_sha256=post["raw_sha256"],
                       raw_operation_ids=[o["i"] for o in operations], completeness_or_accuracy_established=False)
        rows.append(row)
    for binding in bindings:
        assert io.bind(binding["path"]) == binding
    assert io.bind(ledger) == before
    result = {"rows": rows, "answers": len(rows), "same_canonical_sources": sum(r["same_canonical_source"] for r in rows),
              "directly_available_conversions": sum(r["has_saved_conversion"] for r in rows), "source_bound_resolved_operations": sum(r["source_bound_resolved_operations"] or 0 for r in rows),
              "interpretation": "Reuse inventory only. Source-bound records are not expert accuracy estimates; truncated or incomplete answers remain incomplete.",
              "bindings": bindings, "new_model_requests": 0}
    io.write(HERE / "decomposition_inventory.json", result)
    io.csvwrite(HERE / "decomposition_inventory.csv", [{k: r[k] for k in ["answer_id", "same_canonical_source", "has_saved_conversion", "raw_operations", "source_bound_resolved_operations"]} for r in rows])
    io.write(HERE / "reuse_execution.json", {"command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]), "completed_utc": datetime.now(timezone.utc).isoformat(), "ledger": before, "new_model_requests": 0})
    print(json.dumps({k: result[k] for k in ["answers", "same_canonical_sources", "directly_available_conversions", "source_bound_resolved_operations", "new_model_requests"]}))


if __name__ == "__main__":
    main()
