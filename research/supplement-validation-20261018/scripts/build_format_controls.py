#!/usr/bin/env python3
"""Build candidate format controls using only LF insertion at existing blank lines.

No content analysis, external services, scores, or scientific labels are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path


STATUS = "FORMAT_INVARIANCE_CANDIDATE"
TRANSFORM = "insert_one_lf_after_each_existing_empty_lf_line_v1"
ALLOWED_WHITESPACE = " \t\r\n"
DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "build/inputs/candidate20_original_pairs.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "build/format_controls"
PROTECTED_NAMES = (
    "candidate20_original_pairs.json",
    "V3_planned_98_structural_ledger.json",
    "V3_planned_98_structural_ledger.csv",
)
EXPECTED_RELATION = {
    "textual_content_and_correspondence": "UNCHANGED_BY_CONSTRUCTION",
    "scientific_score_label": None,
    "expert_gold": False,
    "independent_holdout": False,
    "llm_scores_required_to_be_exactly_equal": False,
    "note": "Only format invariance is a candidate expectation. No scientific judgment or scoring was performed; raw LLM scores need not be identical without a separately specified deterministic normalization.",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def strip_allowed_whitespace(text: str) -> str:
    return text.translate(str.maketrans("", "", ALLOWED_WHITESPACE))


def make_variant(original: str, candidate_id: str) -> tuple[str, dict]:
    """Keep every original line exact; insert LF after exact LF-only lines."""
    if not isinstance(original, str) or not original:
        raise ValueError("Original answer must be a nonempty string")
    output_lines: list[str] = []
    mappings: list[dict] = []
    operations: list[dict] = []
    offset = 0
    for original_line, line in enumerate(original.splitlines(keepends=True), 1):
        output_lines.append(line)
        mappings.append({
            "original_line_id": f"{candidate_id}:L{original_line:04d}",
            "original_line_1based": original_line,
            "variant_line_1based": len(output_lines),
            "original_line_utf8_sha256": sha256_text(line),
        })
        offset += len(line)
        if line == "\n":
            output_lines.append("\n")
            operations.append({
                "operation": "insert",
                "original_codepoint_offset_0based": offset,
                "after_original_line_1based": original_line,
                "inserted_text": "\n",
                "variant_inserted_line_1based": len(output_lines),
            })
    if not operations:
        raise ValueError("No existing exact LF-only blank line; excluded without fallback")
    variant = "".join(output_lines)
    diff = {
        "schema_version": 1,
        "transform": TRANSFORM,
        "offset_unit": "Python Unicode code points in original text; apply insertions in descending offset order",
        "original_utf8_sha256": sha256_text(original),
        "variant_utf8_sha256": sha256_text(variant),
        "allowed_whitespace_codepoints": ["U+0020", "U+0009", "U+000D", "U+000A"],
        "whitespace_stripped_sha256": sha256_text(strip_allowed_whitespace(original)),
        "original_line_map": mappings,
        "operations": operations,
    }
    validate_variant(original, variant, diff, candidate_id)
    return variant, diff


def apply_diff(original: str, diff: dict) -> str:
    result = original
    for op in reversed(diff["operations"]):
        if op["operation"] != "insert" or op["inserted_text"] != "\n":
            raise ValueError("Only single-LF insert operations are allowed")
        offset = op["original_codepoint_offset_0based"]
        if not isinstance(offset, int) or not 0 <= offset <= len(original):
            raise ValueError("Invalid original insertion offset")
        result = result[:offset] + op["inserted_text"] + result[offset:]
    return result


def validate_variant(original: str, variant: str, diff: dict, candidate_id: str) -> dict:
    """Fail closed on any unexpected edit, even if a weaker check would pass."""
    if original == variant:
        raise ValueError("Variant must contain a real format change")
    if strip_allowed_whitespace(original) != strip_allowed_whitespace(variant):
        raise ValueError("Non-whitespace content differs")
    if re.findall(r"\S+", original) != re.findall(r"\S+", variant):
        raise ValueError("Whitespace-delimited token sequence differs")
    if diff["transform"] != TRANSFORM:
        raise ValueError("Unexpected transform")
    if diff["original_utf8_sha256"] != sha256_text(original):
        raise ValueError("Original hash differs")
    if diff["variant_utf8_sha256"] != sha256_text(variant):
        raise ValueError("Variant hash differs")
    if diff["whitespace_stripped_sha256"] != sha256_text(strip_allowed_whitespace(original)):
        raise ValueError("Whitespace-stripped hash differs")
    original_lines = original.splitlines(keepends=True)
    variant_lines = variant.splitlines(keepends=True)
    expected_operations: list[dict] = []
    expected_mappings: list[dict] = []
    expected_lines: list[str] = []
    offset = 0
    for index, line in enumerate(original_lines, 1):
        expected_lines.append(line)
        expected_mappings.append({
            "original_line_id": f"{candidate_id}:L{index:04d}",
            "original_line_1based": index,
            "variant_line_1based": len(expected_lines),
            "original_line_utf8_sha256": sha256_text(line),
        })
        offset += len(line)
        if line == "\n":
            expected_lines.append("\n")
            expected_operations.append({
                "operation": "insert",
                "original_codepoint_offset_0based": offset,
                "after_original_line_1based": index,
                "inserted_text": "\n",
                "variant_inserted_line_1based": len(expected_lines),
            })
    if not expected_operations:
        raise ValueError("No permitted blank-line insertion")
    if diff["operations"] != expected_operations:
        raise ValueError("Insertion patch differs from the exact permitted transform")
    if diff["original_line_map"] != expected_mappings:
        raise ValueError("Original line mapping changed or incomplete")
    if variant != "".join(expected_lines) or variant_lines != expected_lines:
        raise ValueError("Original line contents or their order changed")
    if apply_diff(original, diff) != variant:
        raise ValueError("Machine-readable patch does not reproduce variant")
    for mapping in expected_mappings:
        i, j = mapping["original_line_1based"] - 1, mapping["variant_line_1based"] - 1
        if original_lines[i] != variant_lines[j]:
            raise ValueError("Mapped original line not preserved verbatim")
    recovered_lines = list(variant_lines)
    for op in reversed(expected_operations):
        if recovered_lines.pop(op["variant_inserted_line_1based"] - 1) != "\n":
            raise ValueError("Reverse patch does not remove a single empty LF line")
    if "".join(recovered_lines) != original:
        raise ValueError("Reverse patch did not recover original verbatim")
    return {
        "result": "PASS",
        "non_whitespace_characters_identical": True,
        "whitespace_delimited_token_sequence_identical": True,
        "all_original_lines_verbatim_and_in_order": True,
        "forward_patch_exact": True,
        "reverse_patch_exact": True,
        "original_line_count": len(original_lines),
        "variant_line_count": len(variant_lines),
        "inserted_lf_count": len(expected_operations),
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_OUTPUT) -> dict:
    source = source.resolve()
    output = output.resolve()
    if source.parent == output:
        raise ValueError("Output must not be the input directory")
    source_bytes = source.read_bytes()
    records = json.loads(source_bytes)
    if not isinstance(records, list) or len(records) != 20:
        raise ValueError("Expected exactly 20 candidate source records")
    ids = [r["candidate_id"] for r in records]
    if len(set(ids)) != 20:
        raise ValueError("Candidate IDs must be unique")
    protected_before = {
        name: sha256_bytes((source.parent / name).read_bytes())
        for name in PROTECTED_NAMES if (source.parent / name).exists()
    }
    pairs, failures = [], []
    for index, original_record in enumerate(records):
        cid = original_record["candidate_id"]
        try:
            if not re.fullmatch(r"C\d{2}", cid):
                raise ValueError("Unexpected candidate ID format")
            original = original_record["model_response"]
            variant, diff = make_variant(original, cid)
            validation = validate_variant(original, variant, diff, cid)
            variant_record = deepcopy(original_record)
            variant_record["model_response"] = variant
            if {k: v for k, v in variant_record.items() if k != "model_response"} != {
                k: v for k, v in original_record.items() if k != "model_response"
            }:
                raise ValueError("Original metadata changed")
            pair_id = f"{cid}_FORMAT_LF_V1"
            diff_path = f"diffs/{pair_id}.json"
            pair = {
                "pair_id": pair_id,
                "candidate_status": STATUS,
                "original_input_id": f"{cid}_ORIGINAL",
                "variant_input_id": pair_id,
                "source_reference": {
                    "source_json_name": source.name,
                    "source_json_sha256": sha256_bytes(source_bytes),
                    "source_array_index_0based": index,
                    "candidate_id": cid,
                    "question_id": original_record["question_id"],
                    "answer_id": original_record["answer_id"],
                    "source_path": original_record["source_path"],
                    "source_record_index": original_record["source_record_index"],
                },
                "original_record": original_record,
                "variant_record": variant_record,
                "diff_path": diff_path,
                "validation": validation,
                "expected_relation": deepcopy(EXPECTED_RELATION),
            }
            pairs.append(pair)
            write_json(output / diff_path, diff)
            write_json(output / f"pairs/{pair_id}.json", pair)
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"candidate_id": cid, "source_array_index_0based": index,
                             "status": "EXCLUDED_FAIL_CLOSED", "reason": str(exc)})
    output.mkdir(parents=True, exist_ok=True)
    (output / "original_source_snapshot.json").write_bytes(source_bytes)
    write_json(output / "format_control_pairs.json", pairs)
    write_json(output / "failures.json", failures)
    protected_after = {
        name: sha256_bytes((source.parent / name).read_bytes())
        for name in protected_before
    }
    if protected_before != protected_after:
        raise ValueError("Source or planned-98 ledger changed during generation")
    summary = {
        "schema_version": 1,
        "candidate_status": STATUS,
        "source_json_sha256": sha256_bytes(source_bytes),
        "source_candidate_count": len(records),
        "passing_pair_count": len(pairs),
        "excluded_failure_count": len(failures),
        "inserted_lf_count": sum(p["validation"]["inserted_lf_count"] for p in pairs),
        "original_line_count": sum(p["validation"]["original_line_count"] for p in pairs),
        "variant_line_count": sum(p["validation"]["variant_line_count"] for p in pairs),
        "protected_input_sha256_before": protected_before,
        "protected_input_sha256_after": protected_after,
        "protected_inputs_unchanged": True,
        "no_encoder_or_judge_calls": True,
        "new_scientific_scoring_runs": 0,
        "expert_gold": False,
        "independent_holdout": False,
        "frozen_shared20": False,
        "planned98_ledger_modified": False,
        "must_reconcile_if_source_candidates_change": True,
        "verification_command": "python scripts/build_format_controls.py --verify",
    }
    write_json(output / "validation_summary.json", summary)
    verify(source, output)
    return summary


def verify(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_OUTPUT) -> dict:
    source_bytes = source.read_bytes()
    snapshot = (output / "original_source_snapshot.json").read_bytes()
    if snapshot != source_bytes:
        raise ValueError("Source candidates changed: rebuild/reconcile before using this draft")
    records = json.loads(source_bytes)
    pairs = json.loads((output / "format_control_pairs.json").read_text(encoding="utf-8"))
    failures = json.loads((output / "failures.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "validation_summary.json").read_text(encoding="utf-8"))
    if len(pairs) + len(failures) != len(records):
        raise ValueError("Candidate coverage does not reconcile")
    indices = [p["source_reference"]["source_array_index_0based"] for p in pairs]
    indices += [f["source_array_index_0based"] for f in failures]
    if sorted(indices) != list(range(len(records))):
        raise ValueError("Duplicate or missing source correspondence")
    if {p.name for p in (output / "pairs").glob("*.json")} != {f"{p['pair_id']}.json" for p in pairs}:
        raise ValueError("Stale, missing, or extra per-pair artifacts")
    if {p.name for p in (output / "diffs").glob("*.json")} != {f"{p['pair_id']}.json" for p in pairs}:
        raise ValueError("Stale, missing, or extra diff artifacts")
    for pair in pairs:
        ref = pair["source_reference"]
        record = records[ref["source_array_index_0based"]]
        if pair["original_record"] != record:
            raise ValueError("Original record differs from source")
        for key in ("candidate_id", "question_id", "answer_id", "source_path", "source_record_index"):
            if ref[key] != record[key]:
                raise ValueError(f"Source correspondence mismatch: {key}")
        if ref["source_json_sha256"] != sha256_bytes(source_bytes):
            raise ValueError("Source hash mismatch")
        if pair["candidate_status"] != STATUS:
            raise ValueError("Unapproved status")
        if pair["expected_relation"] != EXPECTED_RELATION:
            raise ValueError("Unapproved scientific/score/holdout expectation")
        expected_id = f"{record['candidate_id']}_FORMAT_LF_V1"
        if (pair["pair_id"], pair["original_input_id"], pair["variant_input_id"], pair["diff_path"]) != (
            expected_id, f"{record['candidate_id']}_ORIGINAL", expected_id, f"diffs/{expected_id}.json"
        ):
            raise ValueError("Pair identity or diff correspondence changed")
        expected_variant_record = deepcopy(record)
        diff = json.loads((output / pair["diff_path"]).read_text(encoding="utf-8"))
        expected_variant_record["model_response"] = apply_diff(record["model_response"], diff)
        if pair["variant_record"] != expected_variant_record:
            raise ValueError("Variant contains an unauthorized content or metadata change")
        checks = validate_variant(record["model_response"], pair["variant_record"]["model_response"], diff, record["candidate_id"])
        if pair["validation"] != checks:
            raise ValueError("Stored validation does not match recomputed checks")
        single_pair = json.loads((output / "pairs" / f"{pair['pair_id']}.json").read_text(encoding="utf-8"))
        if single_pair != pair:
            raise ValueError("Per-pair artifact differs from aggregate")
    for name, expected in summary["protected_input_sha256_before"].items():
        if sha256_bytes((source.parent / name).read_bytes()) != expected:
            raise ValueError(f"Protected source/ledger changed: {name}")
    if summary["source_json_sha256"] != sha256_bytes(source_bytes):
        raise ValueError("Summary source hash mismatch")
    if summary["passing_pair_count"] != len(pairs) or summary["excluded_failure_count"] != len(failures):
        raise ValueError("Summary counts mismatch")
    if summary["protected_input_sha256_before"] != summary["protected_input_sha256_after"]:
        raise ValueError("Protection hash record mismatch")
    for key in ("inserted_lf_count", "original_line_count", "variant_line_count"):
        if summary[key] != sum(p["validation"][key] for p in pairs):
            raise ValueError(f"Summary count mismatch: {key}")
    if summary["candidate_status"] != STATUS or summary["source_candidate_count"] != len(records):
        raise ValueError("Summary status or source count mismatch")
    for key in ("expert_gold", "independent_holdout", "frozen_shared20", "planned98_ledger_modified"):
        if summary[key] is not False:
            raise ValueError(f"Unapproved claim: {key}")
    for key in ("protected_inputs_unchanged", "no_encoder_or_judge_calls", "must_reconcile_if_source_candidates_change"):
        if summary[key] is not True:
            raise ValueError(f"Required boundary not preserved: {key}")
    if summary["new_scientific_scoring_runs"] != 0:
        raise ValueError("Scientific scoring is out of scope")
    return {"verification": "PASS", "passing_pair_count": len(pairs), "excluded_failure_count": len(failures)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true", help="Read-only validation; rejects stale source candidates")
    args = parser.parse_args()
    result = verify(args.source, args.output) if args.verify else build(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
