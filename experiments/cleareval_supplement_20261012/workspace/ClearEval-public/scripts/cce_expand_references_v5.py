"""Add one conditional q1 uDISCO reference; replay original archive components.

No judge, network request, new embedding, core edit, or previous batch write.
Only the six already exposed question IDs are decoded from source archives.
"""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_validation as core

ART = ROOT / "artifacts/cce_validation"
DEST = ART / "expanded_references_v5"
OLD = ART / "expanded_tasks_v4"
PAIR = ART / "judges/local_alternative_q1_v1"
QIDS = [1, 2, 21, 22, 23, 248]
TARGET = "openai_deepseek-chat__q1"
RAW = ["c_step", "c_param", "co_order", "co_method", "co_param", "co_chem", "s_method", "s_label", "s_trans", "s_time", "Cor", "Eff", "historical_Com", "score_missing_reasons"]
NUMERIC = RAW + ["sr", "sp", "Com", "IA", "HV"]
THRESHOLDS = [.6, .7, .8]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, obj):
    core.write(path, obj)


def bind(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def no_network(*args, **kwargs):
    raise RuntimeError("v5 expansion forbids all network access")


def object_spans(data):
    assert data.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"[")
    depth = 0; quoted = False; escaped = False; start = None
    for pos, byte in enumerate(data):
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
            continue
        if byte == 34: quoted = True
        elif byte in (123, 91):
            if byte == 123 and depth == 1: start = pos
            depth += 1
        elif byte in (125, 93):
            depth -= 1
            if byte == 125 and depth == 1 and start is not None:
                yield start, pos + 1
                start = None
    assert depth == 0 and not quoted


def authorized_records(path):
    data = Path(path).read_bytes(); found = {}; locations = {}; skipped = 0
    for start, end in object_spans(data):
        prefix = data[start:min(end, start + 160)]
        match = re.search(rb'(?m)^\s*"question_id"\s*:\s*(\d+)\s*[,}]', prefix)
        assert match is not None, (str(path), start, "No safe qid prefix")
        qid = int(match.group(1))
        if qid not in QIDS:
            skipped += 1
            continue
        record = json.loads(data[start:end])
        assert int(record["question_id"]) == qid and qid not in found
        found[qid] = record
        locations[qid] = {"object_byte_start_inclusive": start, "object_byte_end_exclusive": end, "object_bytes_sha256": hashlib.sha256(data[start:end]).hexdigest()}
    return found, {"source": bind(path), "decoded_authorized_records": len(found), "skipped_records_without_JSON_decoding": skipped, "decoded_holdout_records": 0, "locations": locations}


def collect_source_bindings(refs):
    bindings = {}; anchored = 0
    def visit(obj):
        nonlocal anchored
        if isinstance(obj, dict):
            pairs = [("path", "sha256"), ("source_path", "source_sha256"), ("pdf_path", "pdf_sha256"), ("text_path", "text_sha256")]
            for key, hk in pairs:
                if key in obj and hk in obj and isinstance(obj[key], str):
                    path = Path(obj[key])
                    assert path.is_file() and sha(path) == obj[hk], str(path)
                    bindings[str(path.resolve())] = obj[hk]
            for key in ["evidence_manifest_path", "source_conflicts_path"]:
                if obj.get(key):
                    path = Path(obj[key]); bindings[str(path.resolve())] = sha(path)
            if {"quote", "start", "end", "text_file"} <= set(obj):
                path = Path(obj["text_file"]["path"])
            elif {"quote", "start", "end", "text_path"} <= set(obj):
                path = Path(obj["text_path"])
            else: path = None
            if path:
                text = path.read_text(encoding="utf-8")
                assert text[obj["start"]:obj["end"]] == obj["quote"]
                assert core.digest(obj["quote"]) == obj["quote_sha256"]
                anchored += 1
            for v in obj.values(): visit(v)
        elif isinstance(obj, list):
            for v in obj: visit(v)
    visit(refs)
    return bindings, anchored


def prepare():
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / "plan.json").exists():
        verify_plan()
        print("Reused unchanged frozen v5 plan; no scoring or judge request.")
        return
    assert not (DEST / "run.json").exists()
    cohort = load(ART / "cohort_frozen.json")
    models = cohort["models"]
    assert len(models) == 13
    protected = {int(x["question_id"]) for x in load(ART / "human_review/selection.json")["selection"] if x["split"] == "audit_holdout"}
    assert len(protected) == 15 and not protected.intersection(QIDS)
    previous = load(OLD / "references.json")["references"]
    added = next(r for r in load(PAIR / "references_full.json")["references"] if r["route_id"] == "uDISCO")
    parent = load(ART / "reference_recovery/udisco_2016/candidate.json")["references"][0]
    assert added["steps"] == parent["steps"][2:] and len(added["steps"]) == 9
    assert parent["question_ids"] == [] and added["question_ids"] == [1]
    assert added["terminal_storage"] == parent["terminal_storage"]
    assert all(not x["confirmed_by_question"] and not x["included_in_step_denominator"] for x in added["scoring_start_prerequisites"])
    assert added["formal_eligible"] is False and added["human_confirmation"] is None
    assert added["scientific_sufficiency_confirmed"] is False
    refs = previous + [copy.deepcopy(added)]
    assert len(previous) == 6 and len({r["reference_id"] for r in refs}) == 7
    ref_obj = {"schema_version": "conditional-reference-expansion-v5", "references": refs,
        "scope": "Original six branches unchanged plus source-only conditional q1 uDISCO clearing 03-11. Actual core rescoring/candidate-pool validation at three thresholds; no scientific gold or same-start-state claim.",
        "formal_eligible": False, "human_confirmation": None,
        "scope_history": "Earlier q1_applicability.json keeps its broader activation caution. This later narrow projection follows conditional_scoring_scope_note.md, with 01/02 and activity labeling unconfirmed; it does not reverse the scientific applicability judgment."}
    write(DEST / "references.json", ref_obj)
    sources, anchors = collect_source_bindings(refs)
    files = [Path(__file__), ROOT / "scripts/cce_validation.py", ART / "cohort_frozen.json", ART / "human_review/selection.json", OLD / "references.json", OLD / "plan.json", OLD / "run.json", OLD / "verification.json", PAIR / "references_full.json", PAIR / "plan.json", PAIR / "review.json", DEST / "references.json", ART / "q1_extension_v1/core_concordance.json", ART / "reference_recovery/udisco_2016/conditional_scoring_scope_note.md", ART / "reference_recovery/udisco_2016/q1_applicability.json", ART / "historical_reports/followup_at_89/request_ledger_at_89.jsonl"]
    for t in THRESHOLDS:
        tag = f"t{round(t*100):03d}"
        files += [ART / f"expanded_tasks_v4_{tag}_per_answer.json", ART / f"expanded_tasks_v4_{tag}_resolved_config.json", OLD / f"{tag}_grid.json", ART / f"supplement_v2_idisco_{tag}_step_matches.json", ART / f"q1_extension_v1/{tag}_step_matches.json", ART / f"q1_extension_v1/{tag}_resolved_config.json"]
    for model in models:
        files += [ROOT / "dataset/Q+AR/model_response" / f"from_{model}_1-shot.json", ROOT / "dataset/Q+AR/result" / f"evaluation_results_{model}_1-shot.json"]
    for path in files: sources[str(path.resolve())] = sha(path)
    old_plan = load(OLD / "plan.json")
    for path, expected in old_plan["input_sha256"].items():
        assert sha(path) == expected, path
    plan = {"schema_version": "conditional-reference-expansion-v5", "created_utc": datetime.now(timezone.utc).isoformat(), "input_sha256": sources,
        "models": models, "question_ids": QIDS, "thresholds": THRESHOLDS, "actual_answer_n": 77, "grid_n": 78,
        "target_answer_id": TARGET, "new_reference_id": added["reference_id"], "new_source_family": added["family_id"],
        "source_scope": "Only q1 adult-whole-brain conditional clearing steps 03-11; preclear wash, meninge removal and IEG/activity labeling remain unconfirmed prerequisites. Storage is a continuous condition. Different reference branches do not imply identical starting states.",
        "expected_changes_before_scoring": {"exact_row_reuse_if_core_equal": 65, "route_metadata_only_refresh_if_numeric_equal": 11, "new_reference_scored_answer": 1},
        "score_policy": "Use original core.score_steps and original archive score through core.build_row. Preserve historical c_param/Correctness/EGES; never import new Qwen numeric proposals.",
        "reuse_policy": "For every actual answer and threshold, replay old and new reference pools with exact cached vectors, reparse full text, and rebuild archive components. Reuse an original row object only after all original-core output and numerical fields are unchanged. Route-only changes get a new v5 config identity.",
        "cache_policy": "Read shared existing MPNet cache and q1 development-pair cache only; no new vector inference; save actual file bindings used.",
        "protected_holdout_qids": sorted(protected), "holdout_answers_or_scores_decoded": 0,
        "source_anchor_spans_verified_at_freeze": anchors, "new_judge_requests": 0, "new_expert_labels": 0, "formal_eligible": False,
        "budget_accounting": "Package ledger snapshot at 89 is bound; other agents may issue already authorized holdout requests concurrently. This script disables network and has no judge entry. Do not assert live global ledger unchanged.",
        "actual_prepare_command": subprocess.list2cmdline([sys.executable, *sys.argv])}
    write(DEST / "plan.json", plan)
    print(json.dumps({"status": "frozen_before_scoring", "actual_answers": 77, "thresholds": 3, "reference_branches": 7, "new_judge_requests": 0, "plan_sha256": sha(DEST / "plan.json")}, ensure_ascii=True))


def verify_plan():
    plan = load(DEST / "plan.json")
    for path, expected in plan["input_sha256"].items():
        assert sha(path) == expected, "Frozen input changed: " + path
    return plan


class CacheOnlyEncoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.used = {}; self.memo = {}
        self.allowed_caches = [ART / "embedding_cache", PAIR / "embedding_cache"]

    def encode(self, texts):
        result = []
        for text in texts:
            key = core.digest([self.identity, text]) + ".npy"
            if key not in self.memo:
                paths = [p / key for p in self.allowed_caches if (p / key).exists()]
                assert paths, "Required cached vector missing; no new inference permitted: " + key
                path = paths[0]
                if len(paths) > 1:
                    assert all(sha(p) == sha(path) for p in paths)
                self.memo[key] = self.np.load(path)
                self.used[str(path)] = sha(path)
            result.append(self.memo[key])
        return self.np.asarray(result)


def pool(refs, qid, route):
    return [r for r in refs if qid in r["question_ids"] and r["route_id"] == route]


def run():
    plan = verify_plan()
    if (DEST / "run.json").exists():
        previous = load(DEST / "run.json")
        assert previous["plan_sha256"] == sha(DEST / "plan.json")
        assert all(sha(path) == expected for path, expected in previous["output_sha256"].items())
        print("Reused unchanged completed v5 results; 0 requests and 0 new computations.")
        return
    socket.create_connection = no_network; socket.socket.connect = no_network
    old_refs = load(OLD / "references.json")["references"]
    new_refs = load(DEST / "references.json")["references"]
    assert new_refs[:-1] == old_refs
    source_bindings, source_anchor_n = collect_source_bindings(new_refs)
    source_access = []; originals = {}
    original_rows = {r["answer_id"]: r for r in load(ART / "expanded_tasks_v4_t070_per_answer.json")}
    for model in plan["models"]:
        ap = ROOT / "dataset/Q+AR/model_response" / f"from_{model}_1-shot.json"
        sp = ROOT / "dataset/Q+AR/result" / f"evaluation_results_{model}_1-shot.json"
        answers, access_a = authorized_records(ap); scores, access_s = authorized_records(sp)
        source_access += [{"kind": "answer", **access_a}, {"kind": "score", **access_s}]
        for qid, answer in answers.items():
            aid = model + "__q" + str(qid); saved = original_rows[aid]; score = scores[qid]
            assert core.digest(answer["model_response"]) == saved["answer_sha256"]
            assert core.digest(answer["specific_question"]) == saved["question_sha256"]
            assert score["evaluation"]["meta_data"]["sample_info"] == answer["specific_question"]
            assert Path(saved["answer_source"]).resolve() == ap.resolve() and Path(saved["score_source"]).resolve() == sp.resolve()
            originals[aid] = (answer, score, ap, sp)
    assert set(originals) == set(original_rows) and len(originals) == 77
    encoder = CacheOnlyEncoder()
    concordance = {(r["answer_id"], r["threshold"]): r["core_result"] for r in load(ART / "q1_extension_v1/core_concordance.json")["records"]}
    products = {}; checks = []; batches = []; target_results = []
    for threshold in THRESHOLDS:
        tag = f"t{round(threshold*100):03d}"
        old_path = ART / f"expanded_tasks_v4_{tag}_per_answer.json"
        saved_rows = load(old_path)
        saved_steps = {r["answer_id"]: r for r in load(ART / f"supplement_v2_idisco_{tag}_step_matches.json")}
        old_q1_cfg = load(ART / f"q1_extension_v1/{tag}_resolved_config.json")
        assert old_q1_cfg["encoder"] == encoder.identity
        config = {"schema_version": "conditional-reference-expansion-v5", "actual_threshold": threshold, "encoder": encoder.identity,
            "parser_version": core.VERSION, "adapter_sha256": sha(ROOT / "scripts/cce_validation.py"), "driver_sha256": sha(__file__),
            "reference_file": str(DEST / "references.json"), "reference_file_sha256": sha(DEST / "references.json"), "reference_digest": core.digest(new_refs),
            "plan_sha256": sha(DEST / "plan.json"), "source_per_answer_file": str(old_path), "source_per_answer_sha256": sha(old_path),
            "source_config_hashes_preserved_on_exact_reused_rows": sorted({r["config_hash"] for r in saved_rows}),
            "archive_component_policy": "Original historical score record only; no new Qwen scores; filename-model/qid/exact-stem binding still lacks original evaluator answer hash.",
            "new_reference_scientific_status": "source-only conditional clearing; start prerequisites and whole-brain IEG pending; expert0/formal0", "formal_eligible": False}
        config_hash = core.digest(config)
        rows = []; step_rows = []; categories = {"exact_row_reuse": [], "route_metadata_refresh": [], "new_reference_score": []}
        for saved in saved_rows:
            aid = saved["answer_id"]; answer, score, ap, sp = originals[aid]; qid = int(answer["question_id"])
            before = core.score_steps(answer, old_refs, encoder, threshold)
            after = core.score_steps(answer, new_refs, encoder, threshold)
            original_step = concordance[(aid, threshold)] if qid == 1 else {k: v for k, v in saved_steps[aid].items() if k != "answer_id"}
            assert before == original_step, "Original core result changed: " + aid
            before_row = core.build_row(saved["model"], answer, score, before, ap, sp, threshold, saved["config_hash"])
            for key in before_row:
                if key != "numeric_scope": assert before_row[key] == saved[key], (aid, key, before_row[key], saved.get(key))
            after_row = core.build_row(saved["model"], answer, score, after, ap, sp, threshold, config_hash)
            assert all(after_row[k] == saved[k] for k in RAW), "Original archive component changed"
            old_pool = pool(old_refs, qid, before["route_id"]); new_pool = pool(new_refs, qid, after["route_id"])
            numeric_equal = all(after_row[k] == saved[k] for k in NUMERIC)
            na_equal = after_row["step_missing_reason"] == saved["step_missing_reason"] and after_row["score_missing_reasons"] == saved["score_missing_reasons"]
            if aid == TARGET:
                assert not old_pool and len(new_pool) == 1 and after["reference_id"] == plan["new_reference_id"]
                assert saved["sr"] is None and after_row["sr"] is not None
                category = "new_reference_score"
            elif before == after:
                assert numeric_equal and na_equal and old_pool == new_pool
                category = "exact_row_reuse"
            else:
                assert numeric_equal and na_equal and not old_pool and not new_pool
                assert before["route_id"] is None and after["route_id"] == "uDISCO"
                assert {k: v for k, v in before.items() if k != "route_id"} == {k: v for k, v in after.items() if k != "route_id"}
                category = "route_metadata_refresh"
            categories[category].append(aid)
            if category == "exact_row_reuse":
                row = copy.deepcopy(saved)
                assert row == saved
            else:
                row = after_row
                row["numeric_scope"] = "v5_conditional_reference_expansion_provisional_archive_linked"
            assert row["formal_eligible"] is False
            rows.append(row); step_rows.append({"answer_id": aid, **after})
            entry = {"answer_id": aid, "threshold": threshold, "category": category, "old_route": before["route_id"], "new_route": after["route_id"], "old_candidate_pool": [r["reference_id"] for r in old_pool], "new_candidate_pool": [r["reference_id"] for r in new_pool], "raw_text_and_stem_bound": True, "old_core_result_exact": True, "archive_components_equal": True, "numerics_unchanged": numeric_equal, "NA_reasons_unchanged": na_equal, "old_row_config_hash": saved["config_hash"], "new_row_config_hash": row["config_hash"], "answer_sha256": row["answer_sha256"], "question_sha256": row["question_sha256"]}
            checks.append(entry)
            if category == "new_reference_score":
                target_results.append({"threshold": threshold, "row": row, "reference_hits": sum(x["matched"] for x in after["matches"]), "reference_n": after["reference_n"], "generated_hits": sum(x >= threshold for x in after["generated_max_similarity"]), "generated_n": after["generated_n"], "max_similarity": max(after["generated_max_similarity"]), "prior_reference_reason": saved["step_missing_reason"], "new_reference_reason": after["step_missing_reason"], "new_Qwen_numeric_scores_used": False})
        assert {k: len(v) for k, v in categories.items()} == {"exact_row_reuse": 65, "route_metadata_refresh": 11, "new_reference_score": 1}
        assert sum(r["sr"] is not None for r in rows) == 39 and sum(r["HV"] is not None for r in rows) == 39
        old_grid = load(OLD / f"{tag}_grid.json"); indexed = {r["answer_id"]: r for r in rows}
        grid = [indexed[r["answer_id"]] if r["answer_id"] in indexed else r for r in old_grid]
        assert len(grid) == 78 and sum(r["answer_sha256"] is None for r in grid) == 1
        base = ART / f"expanded_references_v5_{tag}"
        products[Path(str(base) + "_per_answer.json")] = rows
        products[Path(str(base) + "_resolved_config.json")] = config
        products[DEST / f"{tag}_step_matches.json"] = step_rows
        products[DEST / f"{tag}_grid.json"] = grid
        batches.append({"threshold": threshold, "per_answer_path": str(Path(str(base) + "_per_answer.json")), "config_path": str(Path(str(base) + "_resolved_config.json")), "actual_answers": 77, "numeric_SR": 39, "numeric_candidate_CCE": 39, "reference_insufficient": sum(r["step_missing_reason"] == "reference_insufficient" for r in rows), "missing_grid_slots": 1, "categories": categories, "other_76_numeric_and_NA_unchanged": True})
    assert len(checks) == 231
    verification = {"status": "pass", "actual_answers": 77, "thresholds": 3, "core_old_and_new_result_comparisons": 231, "checks": checks, "cached_vectors_read_only": encoder.used,
        "actual_archive_access": source_access, "source_files_rehashed": source_bindings, "source_spans_verified": source_anchor_n,
        "network_disabled": True, "new_embeddings": 0, "new_judge_requests": 0, "holdout_records_decoded": 0, "expert_labels_added": 0,
        "limitations": ["Original archive score components do not become fresh extraction by reuse.", "Score archive has filename/model/qid/exact-stem binding but lacks original answer-hash/evaluator provenance.", "Expanded source-only coverage does not establish activity-label applicability, scientific correctness, or formal gold.", "uDISCO SR0 is a numeric threshold result for a nonempty parsed answer, not a missing reference or total scientific failure."]}
    products[DEST / "verification.json"] = verification
    products[DEST / "added_answer_results.json"] = target_results
    products[DEST / "source_scope_review.json"] = {"status": "pass_for_conditional_clearing_development_only", "independent_assistant_scope_check": "Separate subagent /root/inventory_reuse/v5_scope_check read references and scope note only; no answers/scores/holdout read.", "source_note": bind(ART / "reference_recovery/udisco_2016/conditional_scoring_scope_note.md"), "boundary": plan["source_scope"], "older_q1_applicability_caution_not_overturned": True, "different_branch_starting_states_not_identical": True, "expert_confirmation": 0}
    assert not any(path.exists() for path in products), "Output already exists; do not overwrite frozen success"
    for path, obj in products.items():
        write(path, obj)
        if path.name.endswith("_per_answer.json"): core.table(path.with_suffix(".csv"), obj)
    outputs = {str(p): sha(p) for p in products}
    outputs.update({str(p.with_suffix('.csv')): sha(p.with_suffix('.csv')) for p in products if p.name.endswith('_per_answer.json')})
    verify_plan()
    run_record = {"status": "complete_pass", "completed_utc": datetime.now(timezone.utc).isoformat(), "plan_sha256": sha(DEST / "plan.json"), "actual_command": subprocess.list2cmdline([sys.executable, *sys.argv]), "batches": batches,
        "reference_branches": 7, "source_families": sorted({r["family_id"] for r in new_refs}), "actual_answers": 77, "task_n": 6, "model_n": 13,
        "new_numeric_answer_count": 1, "new_numeric_answer_threshold_observations": 3, "other_76_numeric_NA_unchanged_each_threshold": True,
        "exact_row_reuse_each_threshold": 65, "route_metadata_only_refresh_each_threshold": 11, "new_embeddings": 0, "cached_unique_vectors": len(encoder.used), "new_judge_requests": 0, "new_expert_labels": 0, "formal_eligible_count": 0,
        "archive_score_used": "Original historical score file, not the new q1 Qwen pair trial", "budget_snapshot": "Frozen historical package count 89; live ledger may advance independently", "output_sha256": outputs}
    write(DEST / "run.json", run_record)
    lines = ["# v5 条件性参考覆盖扩展", "", "仅加入 q1 uDISCO 的作者清除 03–11 条件分支，原 v4 六分支与所有旧产物保持原样。固定 6 题、13 模型、77 份实际答案；一格缺答继续保留。新增模型请求 0、新 embedding 0、专家 0、正式 gold 0。", "", "原 core 在三个阈值上实际复算 77 份旧/新候选池，共 231 项比较：每档 65 行逐字段原样复用，11 行只更新 route_id（null→uDISCO）及版本/范围元数据，数值与 NA 均不变；仅 DeepSeek Chat q1 新增参考评分。它的参数完整性、Correctness 和 EGES 来自原存档评分，并非最近 Qwen 返回。", "", "主候选 SR/CCE 数值覆盖均由 38/77 增为 39/77；参考不足由 39 减为 38。这是开发覆盖变化，不是科学有效性提升。", "", "| 阈值 | 新增答案 SR | SP | Com | Cor | Eff | IA | HV |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in target_results:
        r = item["row"]
        lines.append("| " + str(item["threshold"]) + " | " + " | ".join(format(r[k], ".9g") for k in ["sr", "sp", "Com", "Cor", "Eff", "IA", "HV"]) + " |")
    lines += ["", "uDISCO 原候选 11 项未修改；评分仅用 03–11。01/02 初洗、去膜及活动标签仍未确认，持续保存不额外造操作；不同方法的参考起点不同。旧 q1 适用性记录的总体谨慎结论不被翻转，此处采用后续范围说明允许的限定清除投影。", "", "原始分项仍只有文件名/model/qid/精确题干绑定，不能补称原 evaluator 及答案 hash 已完全恢复。旧 SR0/新 SR0 的解释也不同：有完整参考的 0 是阈值结果，不是缺参考。", "", "当前 live ledger 可能因根代理的独立人工留出准备调用增加；本批冻结的是 89 次历史快照，代码禁用网络且无 judge 调用入口，不声称全包请求数不变。", "", "证据：[计划](plan.json)、[参考](references.json)、[逐项核验](verification.json)、[新增答案三档结果](added_answer_results.json)、[执行记录](run.json)。", "", "实际执行命令（工作目录 C:/ClearEval/ClearEval-public）：", "", "```powershell", "& '" + sys.executable + "' scripts/cce_expand_references_v5.py prepare", "& '" + sys.executable + "' scripts/cce_expand_references_v5.py run", "```", ""]
    (DEST / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (DEST / "EXECUTION.md").write_text("# 实际命令\n\nprepare 在任何 v5 评分之前冻结 plan；run 使用原 core、只读缓存和原 archive scores，网络被禁用。\n\n```powershell\n& '" + sys.executable + "' scripts/cce_expand_references_v5.py prepare\n& '" + sys.executable + "' scripts/cce_expand_references_v5.py run\n```\n\n完整实际 argv/cwd/source hashes 见 plan.json 与 run.json。新增 judge 0、新向量 0，旧结果文件未改。\n", encoding="utf-8")
    print(json.dumps({"status": "complete_pass", "actual_answers": 77, "thresholds": 3, "rows_checked": 231, "numeric_SR_each_threshold": 39, "numeric_CCE_each_threshold": 39, "exact_reuse_each_threshold": 65, "route_only_refresh_each_threshold": 11, "new_answer_scored": 1, "new_judge_requests": 0, "new_embeddings": 0}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    arguments = parser.parse_args()
    {"prepare": prepare, "run": run}[arguments.command]()
