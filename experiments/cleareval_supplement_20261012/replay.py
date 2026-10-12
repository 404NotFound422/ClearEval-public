"""Portable offline replay of frozen ClearEval development diagnostics."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DAY = HERE / "workspace/reports/cleareval_20261012"
CHECKS = DAY / "intervention_validation_01"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def equal_number(actual, expected):
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"Recalculation differs: {actual!r} != {expected!r}")


def maximum_matching(edges):
    matched = {}

    def augment(row, seen):
        for col, edge in enumerate(edges[row]):
            if not edge or col in seen:
                continue
            seen.add(col)
            if col not in matched or augment(matched[col], seen):
                matched[col] = row
                return True
        return False

    for row in range(len(edges)):
        augment(row, set())
    return len(matched)


def proportions(matrix):
    edges = [[value >= 0.7 for value in row] for row in matrix]
    reference_hits = sum(any(row) for row in edges)
    generated_hits = sum(any(row[col] for row in edges) for col in range(len(edges[0])))
    return edges, reference_hits / len(edges), generated_hits / len(edges[0])


def main():
    manifest = read(HERE / "snapshot_manifest.json")
    mismatches = []
    for row in manifest["files"]:
        path = HERE / row["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            mismatches.append(row["path"])
    if mismatches:
        raise ValueError(f"Snapshot mismatch: {mismatches}")

    spec = importlib.util.spec_from_file_location("checkpoint_structural_view", CHECKS / "structural_view.py")
    view = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(view)
    structure_count, negative_count = 0, 0
    for result in read(CHECKS / "structure_results.json"):
        aid = result["answer_id"]
        a = (CHECKS / "structural_views" / f"{aid}_original.txt").read_text(encoding="utf-8")
        b = (CHECKS / "structural_views" / f"{aid}_renumber.txt").read_text(encoding="utf-8")
        av, bv = view.canonicalize(a), view.canonicalize(b)
        assert av["view"] == bv["view"]
        assert av["roundtrip_exact"] and bv["roundtrip_exact"]
        structure_count += 1
        duration = re.search(r"Time:\s*(\d+(?:\.\d+)?)", a)
        if duration:
            changed = a[:duration.start(1)] + str(float(duration[1]) + 1) + a[duration.end(1):]
            assert view.canonicalize(changed)["view"] != av["view"]
            negative_count += 1
        if av["nodes"]:
            leaf = next((n for n in av["nodes"] if n["parent_id"]), av["nodes"][0])
            changed = a[:leaf["start"]] + a[leaf["end"]:]
            assert view.canonicalize(changed)["view"] != av["view"]
            negative_count += 1
        if av["references"]:
            assert view.canonicalize(view.renumber(a, update_references=False))["view"] != av["view"]
            negative_count += 1
    assert (structure_count, negative_count) == (8, 19)
    fixtures = read(CHECKS / "structure_fixtures.json")
    for item in fixtures:
        same = view.canonicalize(item["source_a"])["view"] == view.canonicalize(item["source_b"])["view"]
        assert same == item["expected_same"]

    scores = read(DAY / "english_fulltext_pilot/qwen_translation_pending/scoring/results.json")
    ablations = {r["request_id"]: r for r in read(CHECKS / "fixed_matrix_ablations.json")}
    matrix_results = []
    for record in scores:
        selected = record["selected"]
        edges, sr, sp = proportions(selected["similarity_matrix"])
        equal_number(sr, selected["score"]["sr"])
        equal_number(sp, selected["score"]["sp"])
        old = ablations[record["request_id"]]
        capacity = maximum_matching(edges)
        assert capacity == old["one_sentence_capacity_matched_references"]
        result = {"request_id": record["request_id"], "raw_sr": sr, "raw_sp": sp,
                  "sentence_capacity_auxiliary": capacity / len(edges)}
        if record["answer_id"] == "R3C04":
            relative = record["translation"]["path"].replace("\\", "/").split("reports/cleareval_20261012/", 1)[1]
            text = (DAY / relative).read_text(encoding="utf-8")
            anchor = re.search(r"^[ \t]*(?:\*\*)?\d+[.)]?[ \t]+Dehydration before clearing[^\n]*", text, re.M | re.I)
            assert anchor is not None
            allowed = [g["start"] >= anchor.start() for g in record["generated_steps"]]
            masked = [[edge and allowed[col] for col, edge in enumerate(row)] for row in edges]
            phase_hits = sum(any(row) for row in masked)
            assert phase_hits == old["phase_masked_reference_hits"]
            assert maximum_matching(masked) == old["phase_masked_one_sentence_capacity"]
            result["phase_auxiliary"] = phase_hits / len(edges)
        matrix_results.append(result)

    bridges = []
    for item in read(CHECKS / "operation_bridge_results.json")["results"]:
        selected = item["candidate_selected"]
        equal_number(selected["reference_hits"] / selected["reference_n"], selected["sr"])
        equal_number(selected["generated_hits"] / selected["generated_n"], selected["sp"])
        assert item["reused_model_operations"] == selected["generated_n"]
        assert item["raw_generated_n"] - len(item["excluded_parser_entries"]) == selected["generated_n"]
        bridges.append({"answer_id": item["answer_id"], "raw_generated_n": item["raw_generated_n"],
                        "bridge_generated_n": selected["generated_n"], "auxiliary_sr": selected["sr"], "auxiliary_sp": selected["sp"]})
    result = {"verified_exported_files": len(manifest["files"]), "normalization_pairs_recomputed": structure_count,
              "content_changes_distinguished": negative_count, "constructed_structure_pairs": len(fixtures),
              "fixed_matrix_recalculations": matrix_results, "operation_bridge_arithmetic": bridges,
              "new_model_requests": 0, "new_embeddings": 0, "expert_validation": False,
              "meaning": "Portable source/artifact and arithmetic replay, not new end-to-end evaluation or scientific accuracy validation."}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
