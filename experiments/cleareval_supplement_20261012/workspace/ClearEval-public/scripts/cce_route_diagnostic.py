"""Offline route-filter ablation; never writes scores into the primary CCE table.

The unrestricted branch retains question-specific candidate membership but removes
the declared-route filter. Its numeric outputs are algorithm diagnostics, not
evidence that an answer has a scientifically applicable reference.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as adapter


OUT = adapter.OUT
VERSION = "cce-route-filter-diagnostic-v1"
TOLERANCE = 1e-12
SCOPE = "offline_route_filter_ablation_only_not_scientific_coverage"


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nullable_equal(left, right):
    if left is None or right is None:
        return left is None and right is None
    if finite(left) and finite(right):
        return abs(left - right) <= TOLERANCE
    return left == right


def numeric_mean(rows, key):
    values = [row[key] for row in rows if finite(row.get(key))]
    return adapter.mean(values)


def summarize_group(rows):
    paired = [row for row in rows if finite(row["main_sr"]) and finite(row["unfiltered_sr"])]
    main_missing = [row for row in rows if row["main_sr"] is None]
    missing_with_number = [row for row in main_missing if finite(row["unfiltered_sr"])]
    return {
        "answer_n": len(rows),
        "main_sr_numeric_n": sum(finite(row["main_sr"]) for row in rows),
        "main_sr_missing_n": len(main_missing),
        "main_missing_reasons": dict(Counter(row["main_step_missing_reason"] for row in main_missing)),
        "unfiltered_algorithm_numeric_n": sum(finite(row["unfiltered_sr"]) for row in rows),
        "main_missing_with_unfiltered_algorithm_number_n": len(missing_with_number),
        "main_missing_with_positive_unfiltered_sr_n": sum(row["unfiltered_sr"] > 0 for row in missing_with_number),
        "main_missing_with_zero_unfiltered_sr_n": sum(row["unfiltered_sr"] == 0 for row in missing_with_number),
        "main_missing_unfiltered_sr_mean": numeric_mean(missing_with_number, "unfiltered_sr"),
        "main_missing_unfiltered_sp_mean": numeric_mean(missing_with_number, "unfiltered_sp"),
        "paired_main_numeric_n": len(paired),
        "paired_sr_delta_mean": numeric_mean(paired, "delta_sr_on_main_numeric_only"),
        "paired_sp_delta_mean": numeric_mean(paired, "delta_sp_on_main_numeric_only"),
        "paired_sr_changed_n": sum(abs(row["delta_sr_on_main_numeric_only"]) > TOLERANCE for row in paired),
        "paired_sp_changed_n": sum(abs(row["delta_sp_on_main_numeric_only"]) > TOLERANCE for row in paired),
        "scientific_coverage_added_n": 0,
        "formal_eligible": False,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=OUT / "pilot_per_answer.json")
    parser.add_argument("--run", type=Path, default=OUT / "pilot_run.json")
    parser.add_argument("--config", type=Path, default=OUT / "pilot_resolved_config.json")
    parser.add_argument("--references", type=Path, default=OUT / "pilot_references.json")
    parser.add_argument("--expected-rows", type=int, default=65)
    parser.add_argument("--output-prefix", type=Path, default=OUT / "controls/route_filter_diagnostic")
    args = parser.parse_args()

    primary_paths = {
        "pilot": args.pilot.resolve(), "run": args.run.resolve(),
        "config": args.config.resolve(), "references": args.references.resolve(),
        "adapter": Path(adapter.__file__).resolve(),
    }
    initial_hashes = {key: adapter.filehash(path) for key, path in primary_paths.items()}
    pilot = adapter.read(args.pilot)
    run = adapter.read(args.run)
    config = adapter.read(args.config)
    references = adapter.read(args.references)["references"]
    config_hash = adapter.digest(config)
    threshold = config["run_setting"]["actual_threshold"]
    require(len(pilot) == args.expected_rows == run["answer_n"], "Frozen pilot row count mismatch")
    require(config_hash == run["config_hash"], "Frozen config digest does not match pilot run")
    require(adapter.digest(references) == config["resolved"]["reference_digest"], "Frozen reference digest mismatch")
    require(initial_hashes["adapter"] == config["resolved"]["adapter_sha256"], "Adapter changed after frozen scoring")
    require(adapter.VERSION == config["run_setting"]["segmentation_version"], "Segmentation version mismatch")
    require(adapter.VERSION == config["resolved"]["adapter_version"], "Adapter version mismatch")
    require(len({r["reference_id"] for r in references}) == len(references), "Duplicate reference IDs")
    require(len({r["answer_id"] for r in pilot}) == len(pilot), "Duplicate answer IDs")
    require(len({(r["model"], int(r["question_id"])) for r in pilot}) == len(pilot), "Duplicate model/question rows")
    require(sorted({r["model"] for r in pilot}) == sorted(run["models"]), "Frozen model cohort mismatch")
    require(sorted({int(r["question_id"]) for r in pilot}) == sorted(run["tasks"]), "Frozen task cohort mismatch")

    # Verify frozen answer/question identities before loading the local encoder.
    source_cache, source_hashes, bound = {}, {}, []
    for row in pilot:
        require(row["config_hash"] == config_hash, "Mixed primary configurations")
        require(nullable_equal(row["threshold"], threshold), "Mixed primary thresholds")
        path = Path(row["answer_source"])
        if not path.is_absolute():
            path = adapter.ROOT / path
        path = path.resolve()
        source_key = str(path)
        if source_key not in source_cache:
            source_hashes[source_key] = adapter.filehash(path)
            records = adapter.read(path)
            index = {}
            for answer in records:
                index.setdefault(int(answer["question_id"]), []).append(answer)
            source_cache[source_key] = index
        matches = source_cache[source_key].get(int(row["question_id"]), [])
        require(len(matches) == 1, "Missing or ambiguous source answer: " + row["answer_id"])
        answer = matches[0]
        require(adapter.digest(answer["model_response"]) == row["answer_sha256"], "Answer hash mismatch: " + row["answer_id"])
        require(adapter.digest(answer["specific_question"]) == row["question_sha256"], "Question hash mismatch: " + row["answer_id"])
        bound.append((row, answer))

    encoder = adapter.Encoder()
    require(encoder.identity == run["encoder"], "Local encoder identity differs from frozen pilot")
    output_rows = []
    for main_row, answer in bound:
        # This reproduces the main branch as an integrity check; it is never saved
        # over the frozen score. It also carries forward the adapter parser guard.
        filtered = adapter.score_steps(answer, references, encoder, threshold)
        for key in ("sr", "sp", "reference_id", "route_id", "step_missing_reason"):
            require(nullable_equal(main_row.get(key), filtered.get(key)),
                    "Primary recomputation mismatch: " + main_row["answer_id"] + " field " + key)
        steps = adapter.segment(answer["model_response"])
        require(steps == filtered["generated_steps"], "Segmenter changed within evaluation")
        candidates = [(i, ref) for i, ref in enumerate(references)
                      if int(main_row["question_id"]) in ref["question_ids"]]
        compatible = [(i, ref) for i, ref in candidates if ref["route_id"] == filtered["route_id"]]
        selected = None
        scored = None
        selected_index = None
        diagnostic_reason = None
        score_ties = 0
        if filtered.get("parser_status") == "operation_text_present_but_unparsed":
            diagnostic_reason = "evaluator_failure:operation_text_present_but_unparsed"
        elif not candidates:
            diagnostic_reason = "reference_insufficient:no_question_specific_reference"
        else:
            numeric_candidates = [(encoder.score(ref, steps, threshold), ref, i) for i, ref in candidates]
            scored, selected, selected_index = max(numeric_candidates, key=lambda item: (item[0]["sr"], item[0]["sp"], -item[2]))
            score_ties = sum(item[0]["sr"] == scored["sr"] and item[0]["sp"] == scored["sp"] for item in numeric_candidates)
        diag_sr = scored["sr"] if scored else None
        diag_sp = scored["sp"] if scored else None
        selected_matches_route = selected is not None and selected["route_id"] == filtered["route_id"]
        out = {
            "answer_id": main_row["answer_id"], "model": main_row["model"],
            "question_id": int(main_row["question_id"]),
            "answer_sha256": main_row["answer_sha256"], "question_sha256": main_row["question_sha256"],
            "answer_source": main_row["answer_source"], "main_config_hash": config_hash,
            "threshold": threshold, "segmentation_version": adapter.VERSION,
            "main_numeric_scope": main_row["numeric_scope"],
            "main_formal_eligible": main_row["formal_eligible"],
            "main_route_id": main_row.get("route_id"),
            "main_reference_id": main_row.get("reference_id"),
            "main_reference_status": main_row.get("reference_status"),
            "main_sr": main_row["sr"], "main_sp": main_row["sp"],
            "main_step_missing_reason": main_row.get("step_missing_reason"),
            "main_limitation": main_row.get("limitation"),
            "primary_recomputation_matches": True,
            "parsed_step_n": len(steps),
            "question_candidate_n": len(candidates), "route_compatible_candidate_n": len(compatible),
            "question_candidate_reference_ids": [r["reference_id"] for _, r in candidates],
            "route_compatible_reference_ids": [r["reference_id"] for _, r in compatible],
            "unfiltered_reference_id": selected["reference_id"] if selected else None,
            "unfiltered_route_id": selected["route_id"] if selected else None,
            "unfiltered_reference_status": selected["status"] if selected else None,
            "unfiltered_reference_original_index": selected_index,
            "unfiltered_reference_matches_declared_route": selected_matches_route,
            "unfiltered_sr": diag_sr, "unfiltered_sp": diag_sp,
            "unfiltered_missing_reason": diagnostic_reason,
            "unfiltered_reference_step_n": scored.get("reference_n") if scored else None,
            "unfiltered_generated_step_n": scored.get("generated_n") if scored else None,
            "unfiltered_reference_truncated_n": scored.get("reference_truncated") if scored else None,
            "unfiltered_generated_truncated_n": scored.get("generated_truncated") if scored else None,
            "unfiltered_generated_cjk_step_n": scored.get("generated_cjk_steps") if scored else None,
            "sr_sp_tied_candidate_n": score_ties,
            "delta_sr_on_main_numeric_only": diag_sr - main_row["sr"] if finite(diag_sr) and finite(main_row["sr"]) else None,
            "delta_sp_on_main_numeric_only": diag_sp - main_row["sp"] if finite(diag_sp) and finite(main_row["sp"]) else None,
            "diagnostic_numeric_scope": SCOPE, "diagnostic_formal_eligible": False,
            "scientific_coverage_added": False, "main_na_preserved": main_row["sr"] is None,
        }
        output_rows.append(out)
        print(main_row["answer_id"] + ": diagnostic complete", flush=True)

    # No primary input can change unnoticed during this read-only diagnostic.
    final_hashes = {key: adapter.filehash(path) for key, path in primary_paths.items()}
    require(initial_hashes == final_hashes, "A frozen input changed during the diagnostic")
    require(all(adapter.filehash(path) == value for path, value in source_hashes.items()), "An answer source changed during the diagnostic")
    qids = sorted({row["question_id"] for row in output_rows})
    models = sorted({row["model"] for row in output_rows})
    summary = {
        "version": VERSION, "scope": SCOPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": subprocess.list2cmdline([sys.executable, *sys.argv]),
        "script_sha256": adapter.filehash(__file__),
        "inputs": {key: {"path": str(primary_paths[key]), "sha256": value} for key, value in initial_hashes.items()},
        "answer_source_hashes": source_hashes,
        "frozen_inputs_unchanged": True, "primary_recomputation_matches_all": True,
        "main_config_hash": config_hash, "encoder": encoder.identity, "threshold": threshold,
        "segmentation_version": adapter.VERSION,
        "selection_rule": "question-specific candidates; maximum SR, then maximum SP, then earliest index in frozen reference list",
        "single_reference_limitation": len(references) == 1,
        "reference_n": len(references), "route_n": len({ref["route_id"] for ref in references}),
        "source_family_n": len({ref["family_id"] for ref in references}),
        "reference_metadata": [{key: ref.get(key) for key in ("reference_id", "route_id", "question_ids", "family_id", "status", "source_path", "source_url")} for ref in references],
        "models": models, "question_ids": qids,
        "overall": summarize_group(output_rows),
        "by_model": [{"model": model, **summarize_group([row for row in output_rows if row["model"] == model])} for model in models],
        "by_question": [{"question_id": qid, **summarize_group([row for row in output_rows if row["question_id"] == qid])} for qid in qids],
        "new_model_api_calls": 0, "local_encoder_only": True,
        "primary_pilot_or_cce_written": False, "formal_eligible": False,
        "interpretation": [
            "Removing the declared-route filter can return similarity scores for answers lacking a compatible reference; these do not resolve the original reference-insufficient status.",
            ("The only reference is one source-derived development route, shared across five questions. Max-SR selection is trivial." if len(references) == 1 else "The frozen reference set has multiple source-derived development candidates. Wrong-route selection is an algorithm diagnostic; expert compatibility remains pending."),
            "Numeric comparisons use identical answers, segmenter, encoder, threshold, and frozen reference list. Missing main scores remain missing; no relaxed CCE, shared-question set, ranking, or scientific coverage is produced.",
        ],
    }
    prefix = args.output_prefix.resolve()
    adapter.table(prefix.with_suffix(".csv"), output_rows)
    adapter.write(prefix.with_suffix(".json"), {"summary": summary, "rows": output_rows})
    adapter.write(prefix.with_name(prefix.name + "_summary.json"), summary)
    overall = summary["overall"]
    note = (
        "# Offline route-filter diagnostic\n\n"
        f"Scope: `{SCOPE}`. No primary pilot/CCE file was changed.\n\n"
        f"Frozen cohort: {len(output_rows)} answers, {len(models)} models, {len(qids)} questions; "
        f"threshold {threshold:g}. The adapter, encoder, source answers, question hashes, and main scores were verified.\n\n"
        f"The main branch has {overall['main_sr_numeric_n']} numeric SR/SP results and "
        f"{overall['main_sr_missing_n']} unresolved results. Removing only the route filter returns "
        f"{overall['unfiltered_algorithm_numeric_n']} algorithmic numbers, including "
        f"{overall['main_missing_with_unfiltered_algorithm_number_n']} for previously unresolved answers; "
        f"{overall['main_missing_with_positive_unfiltered_sr_n']} of those have positive SR. "
        "The unresolved main results retain their original NA and missing reason. Scientific coverage added: 0.\n\n"
        f"Among {overall['paired_main_numeric_n']} answers with a numeric main result, "
        f"SR changed for {overall['paired_sr_changed_n']} and SP changed for {overall['paired_sp_changed_n']}.\n\n"
        f"The candidate universe contains {len(references)} reference route and "
        f"{summary['source_family_n']} source families. "
        + ("Max-SR selection is trivial in this single-reference run. " if len(references) == 1 else "Multiple-reference max-SR choices are retained per answer. ")
        +
        "This is evidence about filter behavior only; it cannot establish the accuracy of compatibility decisions "
        "or the quality of unrestricted reference selection. References remain development candidates pending expert review.\n\n"
        "Selection order: maximum SR, maximum SP, earliest frozen reference index. Only question-specific "
        "membership is retained in the unfiltered branch. No protocol text is exported.\n\n"
        f"Actual command:\n\n```powershell\n{summary['command']}\n```\n"
    )
    prefix.with_suffix(".md").write_text(note, encoding="utf-8")
    print("Saved " + str(prefix.with_suffix(".json")), flush=True)


if __name__ == "__main__":
    main()
