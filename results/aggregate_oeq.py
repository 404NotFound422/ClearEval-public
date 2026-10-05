"""Aggregate saved scores without model calls or scientific certification."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import re
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from .oeq_metrics import aggregate_items
except ImportError:
    from results.oeq_metrics import aggregate_items


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def aggregate_file(path, model_name=None):
    path = Path(path)
    items = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = [items]  # Historical single-record files remain inspectable.
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("OEQ result must be a list of result objects")
    contracts = {item.get("scoring_contract_sha256") for item in items}
    if len(contracts) > 1:
        raise ValueError("Mixed scoring contracts in OEQ results")
    digest = next(iter(contracts), None)
    manifest_path = Path(str(path) + ".manifest.json")
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict) or not isinstance(manifest.get("contract"), dict)
                or manifest.get("contract_sha256") != _hash(manifest["contract"])
                or (items and manifest["contract_sha256"] != digest)):
            raise ValueError("Scoring contract manifest mismatch")
        digest = manifest["contract_sha256"]
    benchmark_contract = bool(manifest and manifest["contract"].get("assessment_mode") == "benchmark")
    workflow_required = bool(manifest and manifest["contract"].get("workflow_diagnostics_required") is True)
    from benchmark_scoring import is_workflow_obligation_complete, workflow_sources_match_contract, summarize_workflow_diagnostics
    for item in items:
        ev = item.get("evaluation") or {}
        if not isinstance(ev, dict):
            raise ValueError("Malformed evaluation")
        requires_manifest = (ev.get("workflow_diagnostics_required") is True
                             or ev.get("scoring_status") in {"AUTOMATED_BENCHMARK_ESTIMATE", "BENCHMARK_UNRESOLVED"})
        if requires_manifest and not digest:
            raise ValueError("Automated benchmark estimate requires scoring contract")
        if requires_manifest and manifest is None:
            raise ValueError("Automated benchmark estimate requires scoring contract manifest")
        if workflow_required or ev.get("workflow_diagnostics_required") is True:
            if (not workflow_required or not is_workflow_obligation_complete(ev, allow_failure=True)
                    or not workflow_sources_match_contract(ev, manifest["contract"])):
                raise ValueError("Invalid bound workflow diagnostics or source manifest")
    for item in items:
        ev = item.get("evaluation", {})
        benchmark_candidate = isinstance(ev, dict) and (
            ev.get("scoring_status") in {"AUTOMATED_BENCHMARK_ESTIMATE", "BENCHMARK_UNRESOLVED"}
            or benchmark_contract and (ev.get("technical_status") == "VALID" or "scores" in ev))
        if benchmark_candidate:
            if not digest:
                raise ValueError("Automated benchmark estimate requires scoring contract")
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from benchmark_scoring import is_benchmark_record_complete
            if not is_benchmark_record_complete(ev):
                raise ValueError("Invalid automated benchmark estimate")
    contract = manifest["contract"] if manifest else None
    from oeq_robustness import sources_match_contract, summarize_reports
    robustness_required = bool(contract and contract.get("robustness_diagnostics_required") is True)
    if robustness_required:
        for item in items:
            ev = item.get("evaluation") or {}
            if ev.get("_error"):
                continue  # Technical failures remain in the planned denominator.
            if not sources_match_contract(ev, contract):
                raise ValueError("Invalid bound robustness diagnostics or numerical source manifest")
    if model_name is None:
        if contract and contract.get("model"):
            model_name = contract["model"]
        else:
            stem = path.stem
            match = re.fullmatch(r"(?:evaluation_results_|from_)(.+)_(\d+-shot(?:\+[^_]+)?)(?:_scoring)?", stem)
            if not match:
                raise ValueError("Cannot infer model name; provide model_name")
            model_name = match.group(1)
    states = {}
    for field in ("scoring_status", "score_interpretation", "scientific_status"):
        states[field + "_counts"] = dict(Counter(
            (item.get("evaluation") or {}).get(field, "UNSPECIFIED_HISTORICAL")
            if isinstance(item.get("evaluation"), dict) else "UNSPECIFIED_HISTORICAL"
            for item in items))
    return {"model_name": model_name, **aggregate_items(items),
            "source_result_filename": path.name,
            "scoring_contract_sha256": digest, "scoring_contract": contract,
            "provenance_status": "VERSIONED" if digest else "UNVERSIONED_HISTORICAL",
            **states,
            "workflow_diagnostics_summary": summarize_workflow_diagnostics(items, required=workflow_required),
            "robustness_summary": summarize_reports(items, required=robustness_required),
            "reporting_note": "Aggregated saved scores; automated estimates are not scientific certification."}


def write_stats(paths, output):
    rows = [aggregate_file(path) for path in sorted(map(Path, paths))]
    names = [row["model_name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate model: select one scoring run per model")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                              for row in rows), encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", default="dataset/Q+AR/result_scoring_v2")
    parser.add_argument("--setting", default="1-shot", help="Saved runner shot setting, e.g. 0-shot or 1-shot+KB-RAG")
    parser.add_argument("--output", default="results/oeq_stats_scoring_v2.jsonl")
    args = parser.parse_args()
    directory = Path(args.result_dir)
    paths = list(directory.glob(f"evaluation_results_*_{args.setting}.json"))
    paths.extend(directory.glob(f"from_*_{args.setting}_scoring.json"))
    if not paths:
        parser.error("No saved score results found for selected setting")
    rows = write_stats(paths, args.output)
    print(f"Wrote {len(rows)} rows -> {args.output}")
    print("Automated estimates are not scientific certification.")


if __name__ == "__main__":
    main()

