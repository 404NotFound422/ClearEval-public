#!/usr/bin/env python3
"""Recover exact candidate text from hash-pinned files in a local public checkout.

No network, credentials, model, encoder, or scientific scoring is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "metadata/candidate20_manifest.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def safe_source(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Source path escapes the selected repository root")
    return path


def extract(repo_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {}
    for ref in manifest["source_files"]:
        path = safe_source(repo_root, ref["path"])
        data = path.read_bytes()
        if sha256(data) != ref["sha256"] or git_blob_sha1(data) != ref["git_blob_sha1"]:
            raise ValueError(f"Public source checksum mismatch: {ref['path']}")
        if len(data) != ref["bytes"]:
            raise ValueError("Public source size mismatch")
        sources[ref["path"]] = json.loads(data)
    items = manifest["items"]
    if len(items) != 20 or len({r["candidate_id"] for r in items}) != 20:
        raise ValueError("Expected exactly 20 distinct candidate records")
    records = []
    for item in items:
        record = sources[item["source_path"]][item["source_record_index"]]
        if record["question_id"] != item["question_id"]:
            raise ValueError("Question identity differs at the pinned source index")
        for field, expected_key in (("specific_question", "question_sha256"),
                                    ("model_response", "answer_sha256"),
                                    ("prompt", "source_prompt_sha256")):
            if sha256(record[field].encode("utf-8")) != item[expected_key]:
                raise ValueError(f"Source text checksum mismatch: {field}")
        if record["shot_type"] != item["shot_type"]:
            raise ValueError("Archived shot type differs")
        if item["is_heldout"] is not False or item["selection_status"] != "CANDIDATE_NOT_FROZEN":
            raise ValueError("Unsupported holdout/freeze claim")
        records.append({
            "candidate_id": item["candidate_id"],
            "question_id": item["question_id"],
            "answer_id": item["answer_id"],
            "method_declared": item["method_declared"],
            "specific_question": record["specific_question"],
            "model_response": record["model_response"],
            "source_path": item["source_path"],
            "source_record_index": item["source_record_index"],
        })
    return records


def write_records(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = extract(args.repo_root, args.manifest)
    write_records(records, args.output)
    print(json.dumps({"extracted_candidates": len(records), "sha256": sha256(args.output.read_bytes())}))


if __name__ == "__main__":
    main()
