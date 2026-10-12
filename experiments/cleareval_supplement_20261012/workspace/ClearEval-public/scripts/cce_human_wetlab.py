"""Reproducible E1/E3 archive audit, assisted review packets and E6 planning.

This module does not call an API, generate expert labels, or invent observations.
All writes are confined to the requested output directory.  Review identities
are stored separately from the reviewer packet; historical score versions are
audited without choosing the version with better agreement.
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import hashlib
import html
import json
import math
import random
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
sys.path.insert(0, str(REPO))
ROOT = REPO / "artifacts/cce_validation"
FIELDS = {
    "c_step": ("completeness", 2), "c_param": ("completeness", 3),
    "co_order": ("correctness", 3), "co_method": ("correctness", 2),
    "co_param": ("correctness", 2), "co_chem": ("correctness", 1),
    "s_method": ("effectiveness", None), "s_label": ("effectiveness", 6),
    "s_trans": ("effectiveness", 3), "s_time": ("effectiveness", 3),
}
REVIEW_COLUMNS = ["answer_id", "split", "item", "machine_suggestion", "expert_decision",
                  "source_location", "correction_or_basis", "error_type", "reviewer_id",
                  "review_date", "review_status"]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, columns=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def digest(value):
    if isinstance(value, Path):
        value = value.read_bytes()
    elif not isinstance(value, (str, bytes)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def key(record):
    return (str(record["model_name"]).removesuffix("_1-shot"), str(record["question_id"]))


def scores(record, field):
    group, _ = FIELDS[field]
    value = record.get(group, {}).get(field)
    return value.get("score") if isinstance(value, dict) else value


def comment(record, field):
    group, _ = FIELDS[field]
    value = record.get(group, {}).get(field, {})
    return value.get("comment", "") if isinstance(value, dict) else ""


def audit(args):
    out = Path(args.out)
    result_dir = REPO / "dataset/Q+AR/result"
    paths = {"summary": result_dir / "Machine_vs_Human_Summary.json",
             "export": result_dir / "human_evaluation_scores.json",
             "ui_edit": result_dir / "human_evaluation_user_scores.json"}
    summary = read_json(paths["summary"])
    exported = {key(r): r for r in read_json(paths["export"])}
    edits = read_json(paths["ui_edit"])
    old_questions = {str(r["question_id"]): r for r in read_json(REPO / "dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json")}
    new_questions = {str(r["question_id"]): r for r in read_json(REPO / "dataset/Q+AR/src/question_final.json")}
    source_cache, score_cache, source_manifest, rows, pair_rows = {}, {}, {}, [], []
    for record in summary:
        model, qid = key(record)
        if model not in source_cache:
            source_path = REPO / f"dataset/Q+AR/model_response/from_{model}_1-shot.json"
            score_path = result_dir / f"evaluation_results_{model}_1-shot.json"
            source_cache[model] = {str(r["question_id"]): r for r in read_json(source_path)} if source_path.exists() else {}
            score_cache[model] = {str(r["question_id"]): r for r in read_json(score_path)} if score_path.exists() else {}
            for p in (source_path, score_path):
                source_manifest[str(p)] = digest(p) if p.exists() else None
        answer = source_cache[model].get(qid, {})
        current_score = score_cache[model].get(qid, {}).get("evaluation", {})
        human = record["human_evaluation"]
        export = exported.get((model, qid), {})
        question = record.get("specific_question", "")
        answer_text = record.get("model_response", "")
        row = {"answer_id": f"{model}_1-shot|{qid}", "model_name": model, "question_id": qid,
               "summary_question_sha256": digest(question), "summary_answer_sha256": digest(answer_text),
               "response_question_exact_match": question == answer.get("specific_question"),
               "response_answer_exact_match": answer_text == answer.get("model_response"),
               "old_question_exact_match": question == old_questions.get(qid, {}).get("question"),
               "current_question_exact_match": question == new_questions.get(qid, {}).get("question"),
               "score_question_exact_match": question == current_score.get("meta_data", {}).get("sample_info"),
               "has_grader_name": bool(human.get("grader_name")), "has_grading_time": bool(human.get("grading_time")),
               "has_separate_export": bool(export),
               "s_label_machine_adjustment_comment": "v1 expert rescore" in comment(human, "s_label"),
               "s_trans_machine_adjustment_comment": "v6 adjustment" in comment(human, "s_trans")}
        rows.append(row)
        archived_machine = record.get("machine_evaluation", {}).get("scores", {})
        for field, (group, maximum) in FIELDS.items():
            h, e = scores(human, field), scores(export, field)
            m, c = scores(archived_machine, field), scores(current_score.get("scores", {}), field)
            pair_rows.append({"answer_id": row["answer_id"], "question_id": qid, "field": field,
                              "summary_human": h, "separate_export_human": e,
                              "versions_equal": h == e, "archived_machine": m, "current_saved_machine": c,
                              "machine_difference_current_minus_archive": c-m if isinstance(m, (int,float)) and isinstance(c, (int,float)) else None,
                              "human_comment": comment(human, field),
                              "current_scale_max": maximum,
                              "human_mapping_applied": False})
    source_manifest.update({str(p): digest(p) for p in paths.values()})
    for p in [REPO / "rescore_label_trans.py", WORKSPACE / "review_artifacts/data_stats_audit.md"]:
        if p.exists():
            source_manifest[str(p)] = digest(p)
    ledger = []
    for field, (group, maximum) in FIELDS.items():
        pairs = [r for r in pair_rows if r["field"] == field]
        conflict_count = sum(not r["versions_equal"] for r in pairs)
        if field == "c_step":
            status, reason = "not_comparable_to_SR", "Historical 0-2 ordinal step score is not step-level recall ground truth."
        elif field == "s_method":
            status, reason = "pending_original_human_rubric", "Machine +2.5 translation is documented; human rubric provenance is unresolved. No human transformation applied."
        elif field in {"s_label", "s_trans"}:
            status, reason = "historical_calibration_only", "Saved summary comments and rescore script document machine-informed adjustment; not independent expert validation."
        elif conflict_count:
            status, reason = "version_conflict_pending_provenance", "The two saved human versions disagree; report both without selecting by agreement."
        else:
            status, reason = "historical_scale_aligned_descriptive", "Same numeric scale and equal saved human values; independent provenance and current evaluator evidence/config equivalence remain unverified."
        ledger.append({"field": field, "n_saved_pairs": len(pairs), "human_version_conflicts": conflict_count,
                       "status": status, "current_scale_max": maximum, "reason": reason,
                       "direct_current_independent_validation": False})
    report = {"status": "computed_archive_audit", "n_answers": len(rows),
              "n_unique_questions": len({r["question_id"] for r in rows}), "n_models": len(source_cache),
              "n_ui_edits_not_additional_answers": len(edits),
              "flags": {k: sum(bool(r[k]) for r in rows) for k in rows[0] if isinstance(rows[0][k], bool)},
              "human_version_conflicts": {r["field"]: r["human_version_conflicts"] for r in ledger},
              "human_s_method_values_summary": sorted({scores(r["human_evaluation"], "s_method") for r in summary}),
              "s_method_human_mapping": None,
              "independent_new_expert_labels": 0,
              "current_evaluator_human_agreement": None,
              "note": "Saved historic observations are real, but neither agreement nor machine-shift evidence resolves the human rubric and provenance. No complete human E or CCE is reconstructed."}
    write_csv(out / "archive_answer_provenance.csv", rows)
    write_csv(out / "archive_item_versions.csv", pair_rows)
    write_csv(out / "subitem_comparability.csv", ledger)
    from scipy.stats import pearsonr, spearmanr
    comparisons = []
    for field in FIELDS:
        pairs = [r for r in pair_rows if r["field"] == field]
        for version, human_key in (("summary", "summary_human"), ("separate_export", "separate_export_human")):
            values = [(r["archived_machine"], r[human_key]) for r in pairs if isinstance(r["archived_machine"], (int, float)) and isinstance(r[human_key], (int, float))]
            machine_values, human_values = zip(*values)
            variable = len(set(machine_values)) > 1 and len(set(human_values)) > 1
            comparisons.append({"field": field, "human_version": version, "n_answer_pairs": len(values),
                                "n_shared_questions": report["n_unique_questions"],
                                "MAE_original_scale": statistics.mean(abs(m-h) for m,h in values) if field != "s_method" else None,
                                "exact_equal_fraction_original_scale": sum(m == h for m,h in values)/len(values) if field != "s_method" else None,
                                "Pearson_original_saved_values": float(pearsonr(machine_values, human_values).statistic) if variable else None,
                                "Spearman_original_saved_values": float(spearmanr(machine_values, human_values).statistic) if variable else None,
                                "interpretation": "Historical descriptive association only; machine-informed labels/version conflicts are retained. No current-evaluator or independent-expert validation.",
                                "s_method_note": "Association on original scales only; no numerical agreement or human transformation" if field == "s_method" else ""})
    write_csv(out / "historical_descriptive_comparisons.csv", comparisons)
    write_json(out / "archive_audit.json", report)
    write_json(out / "archive_sources_sha256.json", source_manifest)
    text = "# E1 历史逐答案材料核对\n\n"
    text += f"实际恢复 {len(rows)} 份保存标签，来自 {report['n_unique_questions']} 题、{report['n_models']} 模型。UI 另有 {len(edits)} 条编辑记录，不追加为独立答案。\n\n"
    text += "保存的人评分数存在版本冲突，逐分项差异见 subitem_comparability.csv；s_label/s_trans 的全部 240 份 summary 历史字段有机器结果介入的明确记录，不能称为独立专家金标。历史两个版本与当时机器分数的描述性 MAE、相等比例及相关性并列保存于 historical_descriptive_comparisons.csv，不选择相关性较高的版本。240 个答案共享 20 题；没有将其当作 240 个独立任务推断区间。\n\n"
    text += "s_method 的机器平移关系不能证明人工量表含义。本次保留原值、不平移、不拼出完整人工 E 或 CCE。旧 c_step 保留历史等级含义，不转为人工 SR。输入全文、文件哈希及版本对应见 archive_answer_provenance.csv 和 archive_sources_sha256.json。\n\n"
    text += "论文意义：可明确恢复数量、实际独立问题分母和可复用边界；新增 SR/E3 的人审仍待一位专家按 5 开发＋15 留出完成。历史一致性不得被新的人审计划或当前新评分器自动继承。\n"
    (out / "ARCHIVE_FINDINGS.md").write_text(text, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def get_records(path):
    if str(path).endswith(".jsonl"):
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    data = read_json(path)
    if isinstance(data, list):
        return data
    for name in ("records", "answers", "references", "routes", "selection"):
        if isinstance(data.get(name), list):
            return data[name]
    raise ValueError(f"Expected a list or records/answers/references/routes/selection list: {path}")


def select(args):
    """Freeze an answer list from raw text/metadata, without consulting scores."""
    output = Path(args.out)
    if output.exists():
        print(json.dumps({"status": "reused_frozen_selection", "path": str(output), "sha256": digest(output)}))
        return
    questions_path = REPO / "dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json"
    questions = {str(r["question_id"]): r for r in read_json(questions_path)}
    models = ["gemini-3-flash", "gemini-3-pro"]
    answer_paths = {model: REPO / f"dataset/Q+AR/model_response/from_{model}_1-shot.json" for model in models}
    answers = {model: {str(r["question_id"]): r for r in read_json(p)} for model, p in answer_paths.items()}
    dev_ids = [2, 21, 22, 23, 248]
    selection = []
    for i, qid in enumerate(dev_ids):
        model = models[i % 2]
        family = "historical_whole_brain_morphology" if qid == 2 else "historical_sparse_3mm_reporter_longterm" if qid in {21,22,23} else "historical_whole_brain_AAV_tdTomato"
        selection.append({"question_id": qid, "model_name": model, "split": "audit_dev",
                          "answer_id": f"{model}_1-shot|{qid}", "task_family_id": family,
                          "source_family_id": "FDISCO_QI2019", "reference_ids": ["FDISCO_QI2019_FIXED_MOUSE_BRAIN_V1"],
                          "task_family_basis": "development_exposure_group"})
    candidates, exclusions = [], []
    for qid, question in questions.items():
        meta = question.get("tissue_hierarchy_from_tissue_xlsx", {})
        tissue, tier = meta.get("tissue_inferred", "unmapped"), meta.get("tissue_tier_code", "unmapped")
        for model in models:
            answer = answers[model].get(qid)
            reason = None
            if not answer:
                reason = "missing_answer"
            elif answer.get("specific_question") != question["question"]:
                reason = "historical_stem_mismatch"
            elif int(qid) in dev_ids or "脑" in tissue:
                reason = "conservative_exclusion_of_development_brain_task_groups"
            elif re.search(r"\bF[- ]?DISCO\b", answer["model_response"], re.IGNORECASE):
                reason = "development_FDISCO_route_source_exposure"
            if reason:
                exclusions.append({"model_name": model, "question_id": int(qid), "reason": reason})
                continue
            firstline = answer["model_response"].replace("\\n", "\n").splitlines()[0]
            candidates.append({"question_id": int(qid), "model_name": model, "tier": tier,
                               "tissue": tissue, "group": f"{tier}|{tissue}", "firstline": firstline,
                               "has_archived_human": 2 <= int(qid) <= 21,
                               "target_labels": question.get("marker_query_targets", [])})
    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    # Coverage allocation: rotate observed tiers, balance generation models,
    # and prefer one answer per conservative tissue group before reuse.
    tiers = sorted({r["tier"] for r in candidates})
    rng.shuffle(tiers)
    picked, used_qids, used_groups = [], set(), set()
    for i in range(15):
        desired_model = models[i % 2]
        target_tier = tiers[i % len(tiers)]
        available = [r for r in candidates if r["question_id"] not in used_qids]
        if not available:
            raise ValueError("Fewer than 15 distinct eligible historical tasks")
        available.sort(key=lambda r: (r["group"] in used_groups, r["tier"] != target_tier, r["model_name"] != desired_model, not r["has_archived_human"]))
        choice = available[0]
        used_qids.add(choice["question_id"])
        used_groups.add(choice["group"])
        picked.append(choice)
        selection.append({"question_id": choice["question_id"], "model_name": choice["model_name"],
                          "answer_id": f"{choice['model_name']}_1-shot|{choice['question_id']}",
                          "split": "audit_holdout", "task_family_id": "metadata_group:" + choice["group"],
                          "source_family_id": "unmapped", "reference_ids": [],
                          "task_family_basis": "conservative_tissue_metadata_group_not_verified_original_task_family",
                          "source_status": "source_missing", "holdout_scope": "preselected_extraction_review_candidates_pending_configuration_freeze_and_sources",
                          "stratum": {"tier": choice["tier"], "tissue": choice["tissue"], "model": choice["model_name"],
                                      "raw_route_declaration": choice["firstline"], "existing_target_labels": choice["target_labels"]}})
    sampling = {"seed": args.seed, "selection_uses_machine_scores": False, "selection_uses_human_scores": False,
                "rule": "Exclude all brain metadata groups and every raw answer mentioning FDISCO; rotate observed tissue tiers; prefer unique tissue groups, alternate models, then prefer existing archived-human tasks. Existing route/target labels recorded as coverage diagnostics, not a full crossed quota.",
                "candidate_answers": len(candidates), "candidate_questions": len({r['question_id'] for r in candidates}),
                "stratum_candidate_counts": dict(collections.Counter(r["tier"] for r in candidates)),
                "stratum_selected_counts": dict(collections.Counter(r["tier"] for r in picked)),
                "holdout_model_counts": dict(collections.Counter(r["model_name"] for r in picked)),
                "development_task_groups": 3, "development_source_families": 1,
                "independent_source_family_holdout_established": False,
                "limitations": "Holdout source links are currently absent; conservative metadata groups are not verified original base-task IDs. Local review sample is coverage-oriented, not a prevalence sample. Do not claim independent source-family confirmation yet.",
                "source_hashes": {str(p): digest(p) for p in [questions_path, *answer_paths.values()]}}
    write_json(output, {"sampling_plan": sampling, "selection": selection})
    write_csv(output.parent / "selection_exclusions.csv", exclusions)
    write_csv(output.parent / "holdout_candidate_pool.csv", [{**r, "target_labels": json.dumps(r["target_labels"], ensure_ascii=False)} for r in candidates])
    print(json.dumps({"status": "selection_frozen_before_new_scores", "dev_qids": dev_ids, "holdout_qids": [r["question_id"] for r in picked], "candidate_answers": len(candidates)}))


def build(args):
    selection_data = read_json(args.selection)
    selection = selection_data if isinstance(selection_data, list) else selection_data["selection"]
    counts = collections.Counter(r["split"] for r in selection)
    if counts != {"audit_dev": 5, "audit_holdout": 15}:
        raise ValueError(f"Fixed budget requires 5 audit_dev and 15 audit_holdout, received {dict(counts)}")
    selected_keys = [(r["model_name"], str(r["question_id"])) for r in selection]
    if len(set(selected_keys)) != 20:
        raise ValueError("Duplicate selected answers")
    out = Path(args.out)
    old_review_path = out / "reviewer/review_items.csv"
    old_fingerprint_path = out / "private/selection_fingerprint.json"
    if old_review_path.exists() and old_fingerprint_path.exists():
        old_rows = read_csv(old_review_path)
        if read_json(old_fingerprint_path).get("selection_sha256") != digest(selection_data) and any(r.get("expert_decision") for r in old_rows):
            raise ValueError("Selection changed after labels were entered. Use a new output directory.")
    reviewer = out / "reviewer"
    reviewer.mkdir(parents=True, exist_ok=True)
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    scored = get_records(args.scores) if args.scores else []
    score_lookup = {r.get("answer_id", ""): r for r in scored}
    suggestion_provenance = {}
    if args.scores:
        score_path = Path(args.scores)
        suggestion_provenance = {"suggestion_file_sha256": digest(score_path)}
        run_path = score_path.with_name(score_path.name.replace("_step_matches.json", "_run.json"))
        if run_path != score_path and run_path.exists():
            suggestion_provenance["config_hash"] = read_json(run_path).get("config_hash")
            suggestion_provenance["run_manifest_sha256"] = digest(run_path)
    references = get_records(args.references) if args.references else []
    ref_lookup = {r.get("reference_id", r.get("route_id", "")): r for r in references}
    cache, identity, review_rows, index_rows = {}, [], [], []
    for i, selected in enumerate(selection, 1):
        model = selected["model_name"].removesuffix("_1-shot")
        qid = str(selected["question_id"])
        source = Path(selected.get("response_path") or REPO / f"dataset/Q+AR/model_response/from_{model}_1-shot.json")
        if source not in cache:
            cache[source] = {str(r["question_id"]): r for r in read_json(source)}
        answer = cache[source][qid]
        blind = f"A{i:02d}"
        natural_id = selected.get("answer_id") or f"{model}_1-shot|{qid}"
        machine = score_lookup.get(natural_id, score_lookup.get(f"{model}__q{qid}", {}))
        ref_ids = selected.get("reference_ids", []) or machine.get("compatible_reference_ids", [])
        if not ref_ids and (machine.get("selected_reference_id") or machine.get("reference_id")):
            ref_ids = [machine.get("selected_reference_id") or machine.get("reference_id")]
        ref_records = [ref_lookup[r] for r in ref_ids if r in ref_lookup]
        # Explicit allowlist: never pass scores, model identities, old labels or machine totals.
        suggestions = {k: machine[k] for k in ("extraction", "extracted_fields", "generated_steps", "step_matches", "reference_step_matches", "route_selection_reason", "declared_route", "matches") if k in machine}
        packet = {"answer_id": blind, "split": selected["split"], "review_mode": "ASSISTED",
                  "task_text": answer["specific_question"], "answer_text": answer["model_response"],
                  "question_sha256": digest(answer["specific_question"]), "answer_sha256": digest(answer["model_response"]),
                  "references": ref_records, "machine_suggestions": suggestions,
                  "machine_suggestion_provenance": suggestion_provenance if suggestions else {},
                  "reference_library_sha256": digest(Path(args.references)) if args.references else None,
                  "machine_suggestions_status": "available" if suggestions else "pending_scoring_attachment",
                  "source_status": "available" if ref_records else "source_missing",
                  "expert_conclusions": {}}
        # References can contain metadata identities but must not expose answer-specific scores.
        write_json(reviewer / f"{blind}.json", packet)
        page = f"# 局部核查 {blind}\n\n分组：{selected['split']}；模式：ASSISTED；专家结论尚未填写。\n\n"
        page += "先阅读原题、原答案及来源，再查看机器建议。只纠正提取/对应关系，保留原答案中的科学问题；不将机器建议当作专家结论。\n\n"
        page += "## 原题\n\n" + answer["specific_question"] + "\n\n## 原答案全文\n\n" + answer["model_response"].replace("\\n", "\n")
        page += "\n\n## 参考来源与完整路线\n\n```json\n" + json.dumps(ref_records, ensure_ascii=False, indent=2) + "\n```\n"
        page += "\n## 机器建议（先阅读全文）\n\n```json\n" + json.dumps(suggestions, ensure_ascii=False, indent=2) + "\n```\n\n结论请填写 review_items.csv；空白表示未审。\n"
        (reviewer / f"{blind}.md").write_text(page, encoding="utf-8")
        identity.append({"answer_id": blind, "natural_answer_id": natural_id, "model_name": model,
                         "question_id": qid, "split": selected["split"],
                         "task_family_id": selected.get("task_family_id", "unmapped"),
                         "source_family_id": selected.get("source_family_id", "unmapped"),
                         "response_path": str(source), "response_file_sha256": digest(source),
                         "answer_sha256": packet["answer_sha256"], "question_sha256": packet["question_sha256"]})
        index_rows.append({"answer_id": blind, "split": selected["split"], "packet": f"{blind}.md", "source_status": packet["source_status"], "suggestions_status": packet["machine_suggestions_status"], "review_status": "not_reviewed"})
        for item in ("initial_conditions", "reference_applicability", "key_step_coverage", "extraction_method_route", "extraction_tissue_scale", "extraction_target_marker_relation", "extraction_time_stage_unit", "score_impact"):
            review_rows.append(dict(zip(REVIEW_COLUMNS, [blind, selected["split"], item, "See packet; suggestion is not expert conclusion", "", "", "", "", "", "", "not_reviewed"])))
    write_csv(private / "identity_manifest.csv", identity)
    write_csv(reviewer / "index.csv", index_rows)
    # Never overwrite labels already returned by a human.
    review_path = reviewer / "review_items.csv"
    if review_path.exists():
        with review_path.open(encoding="utf-8-sig", newline="") as stream:
            previous = list(csv.DictReader(stream))
        old = {(r["answer_id"], r["split"], r["item"]): r for r in previous}
        previous_identity = read_json(private / "selection_fingerprint.json") if (private / "selection_fingerprint.json").exists() else {}
        if previous_identity.get("selection_sha256") != digest(selection_data) and any(r.get("expert_decision") for r in previous):
            raise ValueError("Selection changed after labels were entered. Use a new output directory.")
        review_rows = [old.get((r["answer_id"], r["split"], r["item"]), r) for r in review_rows]
    write_csv(review_path, review_rows, REVIEW_COLUMNS)
    write_json(private / "selection_fingerprint.json", {"selection_sha256": digest(selection_data), "selection_source": str(Path(args.selection).resolve())})
    route_rows = [{"reference_id": r.get("reference_id", r.get("route_id", "")),
                   "source": json.dumps(r.get("sources", r.get("source", {"source_path": r.get("source_path"), "source_url": r.get("source_url"), "source_sha256": r.get("source_sha256")})), ensure_ascii=False),
                   "reference_status": r.get("status", r.get("reference_status", "source_extracted")),
                   "human_confirmation": r.get("human_review_status", "not_reviewed"),
                   "is_second_route": r.get("is_second_route", ""),
                   "counted_in_20_answer_budget": False,
                   "expert_decision": "", "reviewer_id": "", "review_date": ""} for r in references]
    ledger_path = out / "reference_construction_ledger.csv"
    if not ledger_path.exists():
        write_csv(ledger_path, route_rows, ["reference_id", "source", "reference_status", "human_confirmation", "is_second_route", "counted_in_20_answer_budget", "expert_decision", "reviewer_id", "review_date"])
    family_sets = {s: {r["task_family_id"] for r in identity if r["split"] == s} for s in counts}
    source_sets = {s: {r["source_family_id"] for r in identity if r["split"] == s} for s in counts}
    overlap = sorted(family_sets["audit_dev"] & family_sets["audit_holdout"])
    source_overlap = sorted(source_sets["audit_dev"] & source_sets["audit_holdout"])
    manifest = {"status": "needs_human_labels", "reviewer_count_budget": 1, "answer_count": 20,
                "split_counts": dict(counts), "review_mode": "ASSISTED", "model_identity_hidden": True,
                "machine_and_old_human_totals_hidden": True, "expert_decisions_prefilled": False,
                "task_family_overlap": overlap, "source_family_overlap": source_overlap,
                "independent_holdout_established": not overlap and not source_overlap and all(r["task_family_id"] != "unmapped" and r["source_family_id"] != "unmapped" for r in identity),
                "new_reference_construction_budget_separate": True,
                "pending_machine_suggestions": sum(r["suggestions_status"] != "available" for r in index_rows),
                "pending_source_packets": sum(r["source_status"] != "available" for r in index_rows),
                "sampling_plan": selection_data.get("sampling_plan") if isinstance(selection_data, dict) else None}
    write_json(out / "packet_manifest.json", manifest)
    (reviewer / "README.md").write_text("# 一位专家的 E1/E3 共用核查\n\n共 5 份开发、15 份留出。先完成开发；固定配置后才运行及审阅留出。只向专家提供本 reviewer 目录，private 目录含模型身份。ASSISTED 表示可以看到机器建议，不是独立盲评。\n\n先阅读各文件的原题和原答案全文，再核对参考与机器建议。在 review_items.csv 的 expert_decision 填写 成立／不成立／证据不足；补充原文位置、必要修正或依据、reviewer_id 和 review_date。review_status 使用 reviewed 或 needs_source；未审项留空并保留 not_reviewed。遗漏、错误绑定、单位错误、阶段错误可写入 error_type。\n\n题干已给出的信息无需在答案重复。只纠正提取与对应关系，保留方案本来的科学错误或含糊。key_step_coverage 是局部核查，不据此计算完整人工 SR。完整参考确认另用 reference_construction_ledger.csv，独立记录工作量。\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


def review_status(args):
    with Path(args.input).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    legal = {"成立", "不成立", "证据不足"}
    invalid = [i+2 for i, r in enumerate(rows) if r.get("expert_decision") and (r["expert_decision"] not in legal or not r.get("reviewer_id") or not r.get("review_date") or not r.get("source_location") or r.get("review_status") not in {"reviewed", "needs_source"})]
    if invalid:
        raise ValueError(f"Incomplete/invalid expert provenance at CSV rows {invalid}")
    report = {"status": "needs_human_labels", "review_mode": "ASSISTED", "splits": {}}
    for split in ("audit_dev", "audit_holdout"):
        subset = [r for r in rows if r["split"] == split]
        reviewed = [r for r in subset if r.get("expert_decision") in legal]
        extraction = [r for r in subset if r["item"].startswith("extraction_")]
        by_answer = collections.defaultdict(list)
        for r in extraction:
            by_answer[r["answer_id"]].append(r)
        complete = [v for v in by_answer.values() if all(r.get("expert_decision") in legal for r in v)]
        errors = sum(any(r.get("expert_decision") == "不成立" for r in v) for v in complete)
        report["splits"][split] = {"planned_answers": len({r["answer_id"] for r in subset}), "reviewed_answers_any_item": len({r["answer_id"] for r in reviewed}),
                                  "planned_items": len(subset), "reviewed_items": len(reviewed),
                                  "completed_extraction_answers": len(complete), "confirmed_extraction_error_answers": errors,
                                  "confirmed_extraction_error_fraction": errors/len(complete) if complete else None,
                                  "insufficient_evidence_items": sum(r["expert_decision"] == "证据不足" for r in reviewed),
                                  "manual_SR": None, "auto_faithful_score_comparison": "pending_corrected_fields_and_paired_rescoring"}
    if rows and all(r.get("expert_decision") in legal for r in rows):
        report["status"] = "local_review_returned_pending_impact_analysis"
    write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False))


def faithful_inputs(args):
    """Apply only source-quoted corrections actually returned by the expert."""
    labels = read_csv(args.review)
    corrections = get_records(args.corrections)
    if not corrections:
        write_json(args.out, {"status": "needs_human_labels", "applied_corrections": [], "records": [],
                              "note": "No expert correction supplied; no faithful values or effect estimates invented."})
        return
    auto = {r["answer_id"]: r for r in get_records(args.auto_extractions)}
    packets = {r["answer_id"]: r for r in [read_json(p) for p in Path(args.packets).glob("A*.json")]}
    lookup = {(r["answer_id"], r["item"]): r for r in labels}
    changed, applied = {}, []
    for correction in corrections:
        answer_id, item = correction["answer_id"], correction["item"]
        reviewed = lookup.get((answer_id, item), {})
        if not item.startswith("extraction_") or reviewed.get("expert_decision") != "不成立" or reviewed.get("review_status") != "reviewed" or not reviewed.get("reviewer_id") or not reviewed.get("review_date"):
            raise ValueError("Every correction must correspond to a source-located extraction error actually confirmed by the expert")
        if correction.get("reviewer_id") != reviewed["reviewer_id"] or correction.get("review_date") != reviewed["review_date"]:
            raise ValueError("Correction reviewer/date does not match returned review")
        packet = packets[answer_id]
        quote = correction.get("source_quote", "")
        if not quote or quote not in packet["answer_text"] and quote not in packet["task_text"]:
            raise ValueError("Correction source_quote must occur verbatim in the original answer or question; literature parameter insertion is not allowed")
        record = changed.setdefault(answer_id, copy.deepcopy(auto[answer_id]))
        if record.get("answer_sha256") != packet["answer_sha256"] or record.get("question_sha256") != packet["question_sha256"]:
            raise ValueError("Extraction record does not bind exactly to the original task and answer")
        if not record.get("config_hash"):
            raise ValueError("Freeze the scoring configuration before faithful-input preparation")
        path = correction["field_path"].split(".")
        if not path or any(p in {"answer_text", "model_response", "task_text", "specific_question", "scores", "config_hash", "reference_text"} for p in path):
            raise ValueError("Only extraction fields may be changed")
        node = record["extraction"]
        for part in path[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        leaf = int(path[-1]) if isinstance(node, list) else path[-1]
        operation = correction.get("operation", "replace")
        if operation not in {"replace", "add", "remove"}:
            raise ValueError("Correction operation must be replace/add/remove")
        exists = 0 <= leaf < len(node) if isinstance(node, list) else leaf in node
        if operation == "add" and exists:
            raise ValueError("Use replace for an existing extracted field")
        if operation != "add" and (not exists or node[leaf] != correction["original_value"]):
            raise ValueError("Original extraction value changed since expert review")
        if operation == "remove":
            del node[leaf]
        elif isinstance(node, list) and operation == "add":
            if leaf != len(node):
                raise ValueError("List add is append-only; use expert-confirmed replacement for other edits")
            node.append(correction["corrected_value"])
        else:
            node[leaf] = correction["corrected_value"]
        record["extraction_sha256"] = digest(record["extraction"])
        record["extraction_mode"] = "faithful_reviewed_fields_only"
        applied.append({"answer_id": answer_id, "item": item, "field_path": correction["field_path"],
                        "operation": operation, "reviewer_id": reviewed["reviewer_id"], "review_date": reviewed["review_date"],
                        "source_quote": quote, "original_answer_unchanged": True})
    write_json(args.out, {"status": "faithful_inputs_prepared_pending_same_config_rescoring", "applied_corrections": applied,
                          "review_file_sha256": digest(Path(args.review)), "correction_file_sha256": digest(Path(args.corrections)),
                          "records": list(changed.values()), "note": "Only reviewed extraction fields changed. Unreviewed fields are not human gold; original scientific errors remain."})


def paired_impact(args):
    manifest = read_json(args.faithful_inputs)
    if not manifest.get("applied_corrections"):
        write_json(args.out, {"status": "needs_human_labels", "paired_answers": 0, "paired_deltas": None})
        return
    auto = {r["answer_id"]: r for r in get_records(args.auto_scores)}
    faithful = {r["answer_id"]: r for r in get_records(args.faithful_scores)}
    labels = read_csv(args.review)
    if digest(Path(args.review)) != manifest["review_file_sha256"]:
        raise ValueError("Review file changed after faithful inputs were prepared")
    split = {r["answer_id"]: r["split"] for r in labels}
    paired = []
    for binding in manifest["records"]:
        answer_id = binding["answer_id"]
        if answer_id not in auto or answer_id not in faithful:
            paired.append({"answer_id": answer_id, "split": split[answer_id], "status": "pending_complete_auto_faithful_pair"})
            continue
        a, f = auto[answer_id], faithful[answer_id]
        for field in ("answer_sha256", "question_sha256", "config_hash"):
            if not a.get(field) or a[field] != f.get(field) or a[field] != binding.get(field):
                raise ValueError(f"Paired {field} mismatch for {answer_id}")
        if f.get("extraction_sha256") != binding["extraction_sha256"]:
            raise ValueError("Faithful score is not bound to expert-corrected extraction")
        for field in ("sr", "sp", "c_param", "co_order", "co_method", "co_param", "co_chem", "Com", "Cor", "s_method", "s_label", "s_trans", "s_time", "S_method", "S_label", "S_trans", "S_time", "Eff", "IA", "HV"):
            av, fv = a.get(field), f.get(field)
            paired.append({"answer_id": answer_id, "split": split[answer_id], "field": field,
                           "auto": av, "faithful_reviewed_fields": fv,
                           "field_present_auto": field in a, "field_present_faithful": field in f,
                           "delta": fv-av if isinstance(av,(int,float)) and isinstance(fv,(int,float)) else None,
                           "NA_created": av is not None and fv is None, "NA_resolved": av is None and fv is not None,
                           "reference_changed": a.get("reference_id") != f.get("reference_id"), "status": "computed_reviewed_field_impact"})
    write_json(args.out, {"status": "computed_with_pending_pairs" if any(r["status"].startswith("pending") for r in paired) else "computed_reviewed_field_impact",
                          "paired_answers": len({r["answer_id"] for r in paired if r["status"] == "computed_reviewed_field_impact"}),
                          "records": paired, "note": "Development and holdout remain separate. These are effects of reviewed-field corrections, not a fully manually corrected protocol or proof that unreviewed fields are correct."})


def power_n(effect, design, alpha=.05, target=.8):
    from scipy.stats import nct, t
    for n in range(3, 20001):
        df = n-1 if design == "paired" else 2*n-2
        noncentral = effect*math.sqrt(n if design == "paired" else n/2)
        critical = t.ppf(1-alpha/2, df)
        power = nct.sf(critical, df, noncentral) + nct.cdf(-critical, df, noncentral)
        if power >= target:
            return n, float(power)
    raise ValueError("Sample-size search exceeded limit")


def plan_wetlab(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for design in ("paired", "independent"):
        for effect in (.2, .35, .5, .65, .8, 1., 1.2):
            n, power = power_n(effect, design)
            for loss in (0., .1, .2):
                rows.append({"design": design, "assumed_standardized_effect": effect,
                             "effect_definition": "Delta/SD(D)" if design == "paired" else "Delta/SD_between",
                             "two_sided_alpha": .05, "target_power": .8, "achieved_power": power,
                             "required_complete_n": n, "n_unit": "independent_donors_with_complete_pairs" if design == "paired" else "independent_donors_per_arm",
                             "assumed_loss_fraction": loss, "planned_n_under_assumption": math.ceil(n/(1-loss)),
                             "status": "hypothetical_sensitivity_not_final_sample_size"})
    write_csv(out / "sample_size_sensitivity.csv", rows)
    config = {"status": "planned_wet_lab", "task_id": None, "task_scale": None,
              "sample_source": None, "initial_processing": None, "labeling_goal": None,
              "route_a_id": None, "route_b_id": None, "route_versions_and_CCE_frozen_before_observation": False,
              "design": None, "pairing_preserves_task_scale": None,
              "primary_endpoint": None, "primary_comparison": "route_B_minus_route_A", "primary_endpoint_unit": None,
              "roi_rule": None, "depth_rule": None, "exposure_laser_rule": None,
              "aggregation": "mean_within_donor_route_of_predefined_measurements", "technical_failure_rule": None,
              "meaningful_difference_Delta": None, "compatible_variability_SD": None,
              "variability_source": None, "planned_independent_n": None, "allocation_seed": 20261008,
              "alpha_two_sided": .05, "target_power": .8, "analysis_locked_before_observation": False,
              "measurement_analysis_blinded": True, "actual_sample_count": 0}
    config_path = out / "design_config.json"
    if not config_path.exists():
        write_json(config_path, config)
    for filename, columns in {
        "donor_roster.csv": ["donor_id", "stratum", "source_batch", "sample_scale", "eligible", "exclusion_reason"],
        "measurements.csv": ["donor_id", "route", "measurement_id", "endpoint", "value", "unit", "roi", "depth", "scan_id", "technical_failure", "failure_reason", "analyst_id", "observation_date"],
        "protocol_version_log.csv": ["route", "protocol_version", "protocol_sha256", "CCE_record_path", "score_before_observation", "execution_change", "rescored_record_path"],
    }.items():
        p = out / filename
        if not p.exists():
            write_csv(p, [], columns)
    sources = [{"path": str(WORKSPACE / "ClearEval_Codex_Experiments_v1_20261008/EXPERIMENT_DESIGN.md"), "section": "E6", "kind": "task_plan"},
               {"path": str(WORKSPACE / "ClearEval_Codex_Experiments_v1_20261008/prompts/P5_WETLAB.md"), "kind": "r2_execution_instructions"},
               {"path": str(WORKSPACE / "review_artifacts/experimental_validation_2026-09-24/实验验证结果报告.md"), "kind": "previous_audit", "finding": "No supplied individual wet-lab source observations; literature/time-KB records are not independent specimens."}]
    for r in sources:
        p = Path(r["path"])
        r["sha256"] = digest(p) if p.exists() else None
    write_json(out / "existing_plan_sources.json", sources)
    write_json(out / "wetlab_status.json", {"status": "planned_wet_lab", "real_measurement_rows": 0,
                                              "completed_experiments": 0, "sample_size_final": None,
                                              "planning_scenarios": len(rows),
                                              "remaining_minimum_inputs": ["actual_task_and_scale", "two_executable_route_versions", "available_donors_and_instrument", "primary_endpoint_and_measurement_rules", "meaningful_Delta_and_compatible_SD", "technical_failure_and_exclusion_rule", "real_measurements"]})
    (out / "WETLAB_PLAN.md").write_text("# E6 统计准备：planned_wet_lab\n\n已定位任务包 E6 与 P5 的既有设计要求；当前材料未提供可核对的供体清单、设备配置和样本级真实测量。保留一个成熟任务、两条完整路线、一个主要比较的范围，具体任务和执行路线待实验方填入 design_config.json。未替实验方选定 CNR 或制造最终样本数。\n\n生物学单位为独立供体/来源。只有分样保持原任务尺度时采用供体内配对，完整器官任务不得因切块方便而改变定义。视野、深度和重复扫描按观测前固定规则先汇总为供体×路线值。计划默认等权平均预定测量点，若实际设计不满足这一规则，应在观察结果前修改并固定。\n\n样本量表使用双侧非中心 t 分布功效，alpha=0.05、power=0.80；配对效应 dz=Delta/SD(D)，独立组效应 d=Delta/SD_between。表中效应量和 0/10/20% 损失率均为假设情景，不是观察值，也不是最终建议 n。缺少有意义差异和相容真实 SD 时不固定 n。\n\n先冻结任务、路线版本和 CCE、主要终点、ROI、深度、曝光/激光、汇总和失败规则，再随机分配。randomize 只接收真实 donor_roster.csv；配对设计随机分配样本槽位到两路线，独立设计在层内尽量平衡分配；成像文件使用盲码，身份密钥仅给执行人员。\n\n录入 measurements.csv 后运行 analyze-wetlab。先剔除按预定规则明确标记的技术失败，按供体×路线汇总；主效应为 B−A。配对使用供体内差值 t 区间，独立组使用 Welch t 区间，实际 n 按供体计。输出分布诊断，不根据显著性反复更换分析。未匹配配对和失败记录单列，不补零。一个任务的重复不能用于跨任务 EGES 预测相关性。\n\n当前结论：分析入口和 42 个样本量假设情景已准备；真实路线效应仍待数据，不能写作实验完成。\n", encoding="utf-8")
    print(json.dumps({"status": "planned_wet_lab", "planning_scenarios": len(rows), "real_observations": 0}))


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def randomize(args):
    config = read_json(args.config)
    roster = read_csv(args.input)
    if not roster:
        write_json(Path(args.out) / "randomization_status.json", {"status": "planned_wet_lab", "actual_units": 0, "reason": "empty_real_donor_roster"})
        return
    design = config.get("design")
    if design not in ("paired", "independent"):
        raise ValueError("Freeze actual paired/independent design in config before randomization")
    if design == "paired" and config.get("pairing_preserves_task_scale") is not True:
        raise ValueError("Paired allocation requires preservation of original task scale")
    units = [r for r in roster if r.get("eligible", "").lower() in {"true", "1", "yes"}]
    if len({r["donor_id"] for r in units}) != len(units) or any(not r["donor_id"] for r in units):
        raise ValueError("Donor ids must be nonempty and unique")
    rng = random.Random(config["allocation_seed"])
    strata = collections.defaultdict(list)
    for r in units:
        strata[r["stratum"]].append(r)
    allocations = []
    for stratum, members in sorted(strata.items()):
        rng.shuffle(members)
        start = rng.randrange(2)
        for i, unit in enumerate(members):
            routes = ["A", "B"] if design == "paired" else [["A", "B"][(i+start) % 2]]
            rng.shuffle(routes)
            for slot, route in enumerate(routes, 1):
                allocations.append({"donor_id": unit["donor_id"], "stratum": stratum, "sample_slot": slot, "route": route})
    rng.shuffle(allocations)
    for i, row in enumerate(allocations, 1):
        row["blind_sample_id"] = f"W{i:04d}"
    out = Path(args.out)
    if (out / "allocation_private.csv").exists():
        raise ValueError("Existing randomization retained; choose a new output directory to avoid reallocating real units")
    write_csv(out / "allocation_private.csv", allocations)
    write_csv(out / "analysis_blind_ids.csv", [{"blind_sample_id": r["blind_sample_id"], "measurement_completed": ""} for r in allocations])
    write_json(out / "randomization_status.json", {"status": "allocated_not_executed", "actual_units": len(units), "design": design, "roster_sha256": digest(Path(args.input)), "config_sha256": digest(Path(args.config)), "seed": config["allocation_seed"]})


def analyze_wetlab(args):
    config = read_json(args.config)
    rows = read_csv(args.input)
    if not rows:
        write_json(args.out, {"status": "planned_wet_lab", "real_measurement_rows": 0, "route_difference": None, "ci95": None, "independent_n": 0})
        return
    if not config.get("analysis_locked_before_observation") or not config.get("primary_endpoint"):
        raise ValueError("Real analysis requires pre-observation analysis lock and named primary endpoint")
    if config.get("aggregation") != "mean_within_donor_route_of_predefined_measurements":
        raise ValueError("Unsupported aggregation; implement and freeze the actual rule before analysis")
    if not config.get("technical_failure_rule"):
        raise ValueError("Freeze the technical-failure rule before exclusions")
    from scipy.stats import t, shapiro, levene
    values, excluded, seen = collections.defaultdict(list), [], set()
    for i, row in enumerate(rows, 2):
        if row["endpoint"] != config["primary_endpoint"]:
            continue
        identifier = (row["donor_id"], row["route"], row["measurement_id"])
        if identifier in seen or not all(identifier):
            raise ValueError(f"Missing/duplicate observation identifier on row {i}")
        seen.add(identifier)
        if row["route"] not in {"A", "B"}:
            raise ValueError(f"Unknown route on row {i}")
        if row.get("technical_failure", "").lower() in {"true", "1", "yes"}:
            if not row.get("failure_reason"):
                raise ValueError(f"Failure reason required on row {i}")
            excluded.append(row)
            continue
        if row.get("unit") != config.get("primary_endpoint_unit"):
            raise ValueError(f"Unit does not match frozen endpoint on row {i}")
        value = float(row["value"])
        if not math.isfinite(value):
            raise ValueError(f"Non-finite measurement on row {i}")
        values[(row["donor_id"], row["route"])].append(value)
    unit_values = {k: statistics.mean(v) for k, v in values.items()}
    a = {d: v for (d, route), v in unit_values.items() if route == "A"}
    b = {d: v for (d, route), v in unit_values.items() if route == "B"}
    design = config["design"]
    if design == "paired":
        if config.get("pairing_preserves_task_scale") is not True:
            raise ValueError("Original task scale must be preserved for paired analysis")
        common = sorted(a.keys() & b.keys())
        difference = [b[d]-a[d] for d in common]
        if len(difference) < 2:
            raise ValueError("At least two actual independent complete donor pairs are required")
        effect = statistics.mean(difference)
        se = statistics.stdev(difference)/math.sqrt(len(difference))
        df = len(difference)-1
        independent_n = len(difference)
        diagnostics = {"normality_of_differences_shapiro_p": float(shapiro(difference).pvalue) if 3 <= len(difference) <= 5000 and len(set(difference)) > 1 else None,
                       "unmatched_donors": sorted(a.keys() ^ b.keys()), "difference_values": difference}
    elif design == "independent":
        if a.keys() & b.keys():
            raise ValueError("Donor repeated in both arms of independent design")
        av, bv = list(a.values()), list(b.values())
        if min(len(av), len(bv)) < 2:
            raise ValueError("At least two actual independent donors per arm are required")
        va, vb = statistics.variance(av)/len(av), statistics.variance(bv)/len(bv)
        effect, se = statistics.mean(bv)-statistics.mean(av), math.sqrt(va+vb)
        df = (va+vb)**2/(va**2/(len(av)-1)+vb**2/(len(bv)-1)) if va+vb else len(av)+len(bv)-2
        independent_n = {"A": len(av), "B": len(bv)}
        diagnostics = {"normality_shapiro_p": {r: float(shapiro(v).pvalue) if 3 <= len(v) <= 5000 and len(set(v)) > 1 else None for r, v in (("A", av), ("B", bv))},
                       "variance_levene_p": float(levene(av, bv).pvalue) if len(set(av+bv)) > 1 else None}
    else:
        raise ValueError("Design must be paired or independent")
    half = float(t.ppf(.975, df))*se
    result = {"status": "computed_from_real_input", "design": design, "primary_comparison": "B_minus_A",
              "endpoint": config["primary_endpoint"], "unit": config["primary_endpoint_unit"],
              "independent_n": independent_n, "route_difference": effect, "ci95": [effect-half, effect+half],
              "real_measurement_rows": len(rows), "technical_failure_measurements": len(excluded),
              "donor_route_aggregates": [{"donor_id": d, "route": r, "value": v, "internal_measurement_count": len(values[(d,r)])} for (d,r), v in sorted(unit_values.items())],
              "diagnostics": diagnostics, "input_sha256": digest(Path(args.input)), "config_sha256": digest(Path(args.config)),
              "interpretation": "Route effect for this task; internal images are not independent n. Assumption diagnostics do not prove assumptions and do not trigger post hoc test selection. This is not a cross-task EGES validation."}
    write_json(args.out, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--out", default=ROOT / "human_review")
    p.set_defaults(run=audit)
    p = sub.add_parser("build")
    p.add_argument("--selection", required=True)
    p.add_argument("--scores")
    p.add_argument("--references")
    p.add_argument("--out", default=ROOT / "human_review")
    p.set_defaults(run=build)
    p = sub.add_parser("select")
    p.add_argument("--seed", type=int, default=20261008)
    p.add_argument("--out", default=ROOT / "human_review/selection.json")
    p.set_defaults(run=select)
    p = sub.add_parser("review-status")
    p.add_argument("--input", required=True)
    p.add_argument("--out", default=ROOT / "human_review/review_status.json")
    p.set_defaults(run=review_status)
    p = sub.add_parser("faithful-inputs")
    p.add_argument("--review", required=True)
    p.add_argument("--corrections", required=True)
    p.add_argument("--auto-extractions", required=True)
    p.add_argument("--packets", required=True)
    p.add_argument("--out", default=ROOT / "human_review/faithful_inputs.json")
    p.set_defaults(run=faithful_inputs)
    p = sub.add_parser("paired-impact")
    p.add_argument("--review", required=True)
    p.add_argument("--faithful-inputs", required=True)
    p.add_argument("--auto-scores", required=True)
    p.add_argument("--faithful-scores", required=True)
    p.add_argument("--out", default=ROOT / "human_review/paired_impact.json")
    p.set_defaults(run=paired_impact)
    p = sub.add_parser("plan-wetlab")
    p.add_argument("--out", default=ROOT / "wetlab")
    p.set_defaults(run=plan_wetlab)
    p = sub.add_parser("randomize")
    p.add_argument("--config", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", default=ROOT / "wetlab/allocation")
    p.set_defaults(run=randomize)
    p = sub.add_parser("analyze-wetlab")
    p.add_argument("--config", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", default=ROOT / "wetlab/analysis.json")
    p.set_defaults(run=analyze_wetlab)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
