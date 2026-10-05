"""Read-only source inventory, per-record bindings and conservative exposure audit."""
from collections import Counter
import csv
import re
from pathlib import Path
import subprocess

from .contract import digest, file_hash, read, save


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def jsonl(path, records):
    import json
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in records), encoding="utf-8")


def stem_binding(text, qid, old, current):
    matches = [name for name, table in (("OLD", old), ("CURRENT", current))
               if table.get(qid, {}).get("question") == text]
    return "+".join(matches) if matches else "EMBEDDED_ONLY"


def ngrams(text, n=5):
    compact = re.sub(r"\s+", "", text)
    return {compact[i:i+n] for i in range(max(0, len(compact) - n + 1))}


def run_audit(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Restrict to benchmark assets. No credential/config directories are read.
    paths = []
    for base in ("dataset/Q+AR", "KnowledgeBase", "prompts", "results", "tests"):
        paths.extend(p for p in (repo/base).rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl", ".py", ".txt", ".csv", ".md", ".xlsx"})
    paths += [repo/p for p in ("OEQ_run_grading_new.py", "evaluation_contract.py", "verified_marker_aliases.py", "README.md", "requirements.txt")]
    inventory = [{"path": p.relative_to(repo).as_posix(), "bytes": p.stat().st_size,
                  "sha256": file_hash(p), "role": p.relative_to(repo).parts[0]} for p in sorted(set(paths))]
    write_csv(output/"asset_inventory.csv", inventory)
    git_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False)
    head = git_result.stdout.strip() if git_result.returncode == 0 else None
    source = {"repository_head": head, "files": {x["path"]: x["sha256"] for x in inventory},
              "scope": "Listed benchmark assets only; no external inference or credentials", "hash_format": "file-byte-sha256"}
    source["manifest_sha256"] = digest(source)
    save(output/"source_manifest.json", source)
    old = {str(q["question_id"]): q for q in read(repo/"dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json")}
    current = {str(q["question_id"]): q for q in read(repo/"dataset/Q+AR/src/question_final.json")}
    bindings, source_responses = [], {}
    for path in sorted((repo/"dataset/Q+AR/model_response").glob("*.json")):
        data = read(path)
        if not isinstance(data, list):
            continue
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            qid, text, prompt = str(entry.get("question_id")), entry.get("specific_question"), entry.get("prompt")
            if not isinstance(text, str):
                binding, admission = "MISSING_EMBEDDED_STEM", "QUARANTINE"
            else:
                binding = stem_binding(text, qid, old, current)
                admission = "LEGACY_REPLAY_ONLY" if isinstance(prompt, str) and text in prompt else "QUARANTINE_INCOMPLETE_PROMPT"
            row = {"file": path.relative_to(repo).as_posix(), "record_index": index, "question_id": qid,
                   "record_sha256": digest(entry), "embedded_question_sha256": digest(text),
                   "prompt_sha256": digest(prompt), "response_sha256": digest(entry.get("model_response")),
                   "snapshot_binding": binding, "prompt_contains_embedded_question": isinstance(prompt, str) and isinstance(text, str) and text in prompt,
                   "admission": admission, "runtime_provenance": "NOT_RECONSTRUCTED_FROM_MODEL_FILENAME"}
            bindings.append(row)
            source_responses.setdefault((path.name, qid), []).append(entry)
    write_csv(output/"legacy_answer_bindings.csv", bindings)
    score_bindings, reaggregates = [], []
    from results.oeq_metrics import aggregate_items
    for path in sorted((repo/"dataset/Q+AR/result").glob("evaluation_results_*.json")):
        entries = read(path)
        if not isinstance(entries, list):
            continue
        agg = aggregate_items(entries)
        reaggregates.append({"file": path.name, "saved_count": len(entries),
                             "valid_count": agg["sample_count"], "coverage": agg["coverage"],
                             "IA": agg["application_index"], "scope": "Reaggregation of saved automatic scores, not a new judgment"})
        response_name = path.name.replace("evaluation_results_", "from_", 1)
        for index, entry in enumerate(entries):
            ev = entry.get("evaluation", {})
            text = ev.get("meta_data", {}).get("sample_info") if isinstance(ev, dict) else None
            qid = str(entry.get("question_id"))
            responses = source_responses.get((response_name, qid), [])
            matching = [r for r in responses if isinstance(text, str) and r.get("specific_question") == text]
            score_bindings.append({"file": path.relative_to(repo).as_posix(), "record_index": index,
                "question_id": qid, "record_sha256": digest(entry),
                "snapshot_binding": stem_binding(text, qid, old, current) if isinstance(text, str) else "MISSING_EMBEDDED_STEM",
                "matching_response_stems": len(matching),
                "admission": "DESCRIPTIVE_SAVED_SCORE_ONLY",
                "protocol_binding": "NOT_VERIFIED_WITHOUT_RESPONSE_HASH_OR_RAW_JUDGE_REQUEST"})
    write_csv(output/"legacy_score_bindings.csv", score_bindings)
    save(output/"legacy_reaggregates.json", reaggregates)

    dev_ids = {"3", "79", "122", "145", "157", "165"}
    exposure = []
    for qid, q in current.items():
        source_rows = sorted({t.get("source_tissue_xlsx_row") for t in q.get("marker_query_targets", [])
                              if isinstance(t.get("source_tissue_xlsx_row"), int)})
        exposure.append({"question_id": qid, "question_sha256": digest(q["question"]),
            "root_task_id": "Q" + qid, "split": "DEVELOPMENT" if qid in dev_ids else "PUBLIC_EXPLORATORY",
            "public_exposure": True, "prior_development_exposure": "CONFIRMED" if qid in dev_ids else "NOT_FULLY_RECONSTRUCTED",
            "primary_source_group": None, "worksheet_rows": source_rows,
            "source_review": "PENDING_TASK_SPECIFIC_PRIMARY_SOURCE_REVIEW", "holdout_eligible": False})
    jsonl(output/"task_source_audit.jsonl", exposure)
    write_csv(output/"exposure_audit.csv", [{**r, "worksheet_rows": ";".join(map(str,r["worksheet_rows"]))} for r in exposure])
    save(output/"split_manifest.json", {"assignments": {r["root_task_id"]: r["split"] for r in exposure},
         "formal_holdout": [], "reason": "All released tasks are public; provenance and prior exposure are incompletely reconstructed. No task is silently promoted to independent holdout.",
         "source_grouping_status": "PENDING_DOMAIN_REVIEW", "pretraining_contamination": "UNOBSERVABLE"})
    grams = {qid: ngrams(q["question"]) for qid, q in current.items()}
    similarities = []
    ids = list(current)
    for i, left in enumerate(ids):
        for right in ids[i+1:]:
            union = grams[left] | grams[right]
            similarity = len(grams[left] & grams[right]) / len(union) if union else 1
            if similarity >= 0.80:
                similarities.append({"left": left, "right": right, "jaccard_character_5gram": round(similarity, 6),
                                     "decision": "CANDIDATE_FOR_MANUAL_GROUPING_NOT_SEMANTIC_EQUIVALENCE"})
    save(output/"near_duplicate_candidates.json", {"threshold": 0.80, "pairs": similarities,
         "source_overlap_checked": False, "note": "Negative text result cannot establish absence of conceptual/source leakage"})
    cells = []
    for row in read(repo/"KnowledgeBase/method_fluro_compati.json"):
        for signal, value in row.items():
            if signal != "method":
                cells.append({"method": row["method"], "signal": signal, "legacy_value": value,
                    "primary_source": None, "conditions": None, "scientific_status": "UNRESOLVED_PROVENANCE",
                    "admission": "LEGACY_DIAGNOSTIC_ONLY_NOT_SCIENTIFIC_REFERENCE"})
    write_csv(output/"kb_compatibility_audit.csv", cells)
    time_rows = []
    for row in read(repo/"KnowledgeBase/time_kb.json")["rows"]:
        flags = []
        if row.get("time_excludes_labeling") == "yes" and "包括固定、透化/染色" in row.get("time_scope", ""):
            flags.append("CONFLICTING_TIME_SCOPE")
        if str(row.get("review_status", "")).startswith("removed"):
            flags.append("REMOVED_REFERENCE")
        if not row.get("source_url"):
            flags.append("NO_SOURCE_URL")
        time_rows.append({"lookup_key": row["lookup_key"], "source_url": row.get("source_url"),
            "flags": ";".join(flags), "scientific_review": "PENDING_SOURCE_AND_ACTUAL_BRANCH_REVIEW",
            "admission": "QUARANTINE" if flags else "UNVERIFIED_REFERENCE"})
    write_csv(output/"kb_time_audit.csv", time_rows)
    summary = {"assets": len(inventory), "answer_records": len(bindings),
        "answer_bindings": dict(Counter(r["snapshot_binding"] for r in bindings)),
        "answer_admission": dict(Counter(r["admission"] for r in bindings)),
        "score_records": len(score_bindings), "current_tasks": len(current),
        "changed_stems": sum(q["question"] != old.get(qid, {}).get("question") for qid, q in current.items()),
        "compatibility_cells": len(cells), "time_rows": len(time_rows),
        "time_scope_conflicts": sum("CONFLICTING_TIME_SCOPE" in r["flags"] for r in time_rows),
        "near_duplicate_candidates": len(similarities), "independent_holdout_roots": 0,
        "independent_expert_labels": 0, "raw_wet_lab_records_verified": 0,
        "source_hashes_unchanged": all(file_hash(repo/r["path"]) == r["sha256"] for r in inventory)}
    save(output/"audit_summary.json", summary)
    lines = ["# 历史材料冻结与复算\n", "本次仅复算保存的自动评分，不补造历史请求或独立专家标签。\n",
             f"盘点 {len(inventory)} 份文件、{len(bindings)} 条回答、{len(score_bindings)} 条评分。逐条绑定结果见 CSV；无法确认完整提示的回答隔离。",
             "题号或模型文件名不足以重建真实推理配置。保存分数即使题干相符，也不自动视为已绑定完整回答及评价请求。",
             f"当前 {len(current)} 题中 {summary['changed_stems']} 条相对旧快照改变。旧结果只用于各自输入的描述性复算，不用于当前题干的模型排名。",
             f"兼容性表 {len(cells)} 个单元格保留原值，但均缺本表内逐单元格来源和条件；不解释为已证实错误，也不作为新版科学判定的独立参照。",
             f"时间表 {len(time_rows)} 行中 {summary['time_scope_conflicts']} 行存在时间范围字段冲突。",
             "所有公开任务保留曝光记录；来源家族尚未审定，正式独立保留集为空。未取得的 372 条湿实验原始记录不计入已复现。"]
    (output/"legacy_reproduction_report.md").write_text("\n\n".join(lines)+"\n", encoding="utf-8")
    return summary
