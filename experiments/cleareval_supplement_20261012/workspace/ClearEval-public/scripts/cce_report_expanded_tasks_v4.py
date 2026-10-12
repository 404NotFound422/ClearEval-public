"""Render the isolated q1 plus frozen v3 task composition without scoring.

This version is intentionally separate from the v3 report writer.  It reads
completed artifacts, preserves their individual configurations, and captures
the preceding current reports once before any replacement.  Importing this
module has no filesystem effects.
"""
from __future__ import annotations

import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/cce_validation"
VERSION = "expanded_tasks_v4"
PREFIX = "expanded_tasks_v4"
ANALYSIS = "analysis_expanded_tasks_v4"
FIGURES = "figures_expanded_tasks_v4"
GAPS = "common_set_gaps_v4"
Q1 = "q1_extension_v1"
ABLATION = "controls/paired_route_ablation_v3"
HIST = OUT / "historical_reports/supplement_v3_before_q1"
REPORTS = ["STATUS.md", "RESULTS_zh.md", "Methods_Results_en.md", "Abstract_en.md", "commands.md"]
METADATA = ["current_run_index.json", "resolved_config_current.yaml", "remaining_dependencies.json", "budget.json", "report_generation.json", "reference_recovery/reference_construction_current.json"]
INPUTS: dict[str, str] = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name, required=True, default=None):
    path = OUT / name
    if not path.exists():
        if required:
            raise FileNotFoundError("Required completed input is absent: " + str(path))
        return default
    INPUTS[str(name).replace("\\", "/")] = sha(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def textread(name):
    path = OUT / name
    INPUTS[str(name).replace("\\", "/")] = sha(path)
    return path.read_text(encoding="utf-8-sig")


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value.strip() if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value):
    return f"{value:.6f}" if finite(value) else "NA"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"] + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def snapshot():
    manifest = HIST / "snapshot_manifest.json"
    if manifest.exists():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        for name, digest in recorded["files"].items():
            if sha(HIST / name) != digest:
                raise ValueError("Historical v3 snapshot changed: " + name)
        return recorded
    current = json.loads((OUT / "current_run_index.json").read_text(encoding="utf-8-sig"))
    if current.get("version") != "supplement_v3_idisco":
        raise ValueError("First v4 capture must preserve the actual preceding v3 current reports")
    files = {}
    for name in REPORTS + METADATA:
        source, target = OUT / name, HIST / name
        raw = source.read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Unregistered historical bytes differ: " + name)
        if not target.exists():
            target.write_bytes(raw)
        assert sha(source) == sha(target)
        files[name] = sha(target)
    record = {"scope": "supplement_v3_before_q1_current_reports_and_metadata", "files": files,
              "byte_identical_at_capture": True, "created_utc": datetime.now(timezone.utc).isoformat(),
              "command": subprocess.list2cmdline([sys.executable, *sys.argv]), "old_result_batches_modified": False}
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def require_pass(value, name):
    if value.get("pass") is False or value.get("all_passed") is False or value.get("status") in ("failed", "pending", "running"):
        raise ValueError("Completed passing artifact required: " + name)


def load_completed_inputs():
    """Validate actual row identities before deriving any manuscript counts."""
    INPUTS.clear()
    batches = {t: read(f"{PREFIX}_t0{t}_per_answer.json") for t in (60, 70, 80)}
    prior = {t: read(f"supplement_v2_idisco_t0{t}_per_answer.json") for t in (60, 70, 80)}
    q1 = {t: read(f"{Q1}/t0{t}_per_answer.json") for t in (60, 70, 80)}
    counts = {}
    for threshold, rows in batches.items():
        actual_q1 = [r for r in q1[threshold] if r.get("answer_sha256")]
        missing_q1 = [r for r in q1[threshold] if not r.get("answer_sha256")]
        expected = {r["answer_id"]: r for r in prior[threshold] + actual_q1}
        observed = {r["answer_id"]: r for r in rows}
        assert len(expected) == len(rows) == len(observed), "Repeated or omitted actual-answer row"
        assert set(expected) == set(observed), "Composition has different actual answer IDs"
        for answer_id, old in expected.items():
            assert observed[answer_id] == old, answer_id
        assert not ({r["answer_id"] for r in missing_q1} & set(observed)), "Missing-answer placeholders entered actual-answer table"
        counts[threshold] = {
            "actual_answers": len(rows), "prior_actual_answers": len(prior[threshold]),
            "q1_actual_answers": len(actual_q1), "q1_missing_slots": len(missing_q1),
            "step_numeric": sum(finite(r.get("sr")) for r in rows),
            "q1_step_numeric": sum(finite(r.get("sr")) for r in actual_q1),
            "candidate_cce_numeric": sum(all(finite(r.get(m)) for m in ("Com", "Cor", "Eff", "IA", "HV")) for r in rows),
            "formal_eligible": sum(bool(r.get("formal_eligible")) for r in rows),
            "question_ids": sorted({r["question_id"] for r in rows}),
        }
    assert all({r["answer_id"] for r in batches[t]} == {r["answer_id"] for r in batches[70]} for t in batches)
    summary = read(f"{Q1}/summary.json")
    verification = read(f"{Q1}/verification.json")
    concordance = read(f"{Q1}/core_concordance.json")
    review = read(f"{Q1}/review.json")
    for value, name in ((verification, "q1 verification"), (concordance, "q1 core concordance")):
        require_pass(value, name)
    assert not review.get("blocking_findings")
    assert concordance["matching_observations"] == concordance["compared_observations"]
    assert len(review["driver_boundary_findings"]) == 2
    assert summary["new_api_requests"] == summary["new_judge_requests"] == 0
    ablation = read(ABLATION + "/summary.json")
    ablation_review = read(ABLATION + "/review.json")
    assert ablation_review["status"] == "pass_for_existing_three_pair_offline_diagnostic"
    for value in (ablation, ablation_review):
        assert value.get("new_judge_requests", value.get("new_model_requests")) == 0
    return {"batches": batches, "prior": prior, "q1": q1, "counts": counts,
            "q1_summary": summary, "q1_verification": verification, "q1_concordance": concordance,
            "q1_review": review, "ablation": ablation, "ablation_review": ablation_review}


def load_frozen_context():
    """Keep actual E2/E3/E4 and human evidence in their unchanged versions."""
    names = {
        "e2": "judges/local_controls_supplement_v2/development_summary.json",
        "controls": "judges/local_controls_supplement_v2/control_summary.json",
        "e4": "judges/local_stability_supplement_v2/development_summary.json",
        "alt": "judges/local_alternative_development/development_summary.json",
        "e3": "human_review/rescoring/v4_dev_v2/summary.json",
        "identity": "human_review/rescoring/v4_dev_v2/identity_verification.json",
        "lineage": "human_review/lineage/summary.json",
        "human": "human_review/review_status.json",
        "local": "human_review/local_step_audit/summary.json",
        "impact": "human_review/review_impact_addendum/summary.json",
        "wet": "wetlab/wetlab_status.json",
        "local_verification": "judges/local_v2_verification.json",
        "prescreen": "controls/whole_brain_task_prescreen/audit.json",
        "q29": "inventory/partial_score_q29/audit.json",
        "source": "reference_recovery/idisco_plus_2016/source_manifest.json",
        "source_review": "reference_recovery/idisco_plus_2016/review/source_applicability_audit.json",
        "q248": "reference_recovery/idisco_plus_2016/review/q248_route_only_diagnostic/summary.json",
        "route_v3": "controls/supplement_v3_route_filter_diagnostic_summary.json",
    }
    context = {key: read(name) for key, name in names.items()}
    context["ledger"] = [json.loads(line) for line in textread("judges/request_ledger.jsonl").splitlines() if line.strip()]
    context["returned_items"] = sum(row["reviewed_items"] for row in context["human"]["splits"].values())
    context["returned_answers"] = sum(row["reviewed_answers_any_item"] for row in context["human"]["splits"].values())
    context["control_by_condition"] = {row["condition"]: row for row in context["controls"]}
    require_pass(context["local_verification"], "unchanged local v2 verification")
    return context


def retained_evidence_prose(frozen):
    e2, e3, e4, alt = (frozen[k] for k in ("e2", "e3", "e4", "alt"))
    controls = frozen["control_by_condition"]
    deletion = controls["necessary_step_deletion"]
    param = controls["necessary_parameter_deletion"]
    order = controls["evidence_supported_order_conflict"]
    merge = controls["adjacent_entry_merge"]
    equiv = controls["deterministic_equivalent_representation"]
    control_table = table(
        ["条件（冻结 supplement v2）", "完整对", "ΔSR", "ΔCom", "ΔCor", "ΔEff", "ΔIA", "ΔHV"],
        [[row["condition"], row["complete_pairs"], *[fmt(row.get("mean_delta_" + metric)) for metric in ("sr", "Com", "Cor", "Eff", "IA", "HV")]] for row in frozen["controls"]],
    )
    e2_zh = (
        f"E2 继续保留 supplement v2 的 {e2['technical_successful_cases']} 份全文评价和 {e2['complete_candidate_cce_pairs']} 对完整候选比较；"
        "它们来自3份源答案、2个任务家族、1个来源家族。基线与编辑后的全文在相同冻结配置下重新解析、提取和评分。"
        "这些输入显式只包含 FDISCO v2，新增任务绑定不改变它们，也不把版本重跑叠加为独立案例。"
        f"RI/保存模块删除仅 {deletion['negative_sr']}/{deletion['n_sr']} 对降低 SR；明确时间删除 {param['negative_c_param']}/{param['n_c_param']} 对降低 c_param；"
        f"顺序冲突 {order['negative_co_order']}/{order['n_co_order']} 对降低 co_order，{order['negative_Cor']}/{order['n_Cor']} 对降低 Cor，"
        f"却有 {order['negative_c_param']} 对 c_param 下降。相邻条目合并的 SR 下降/不变/上升各为 {merge['negative_sr']}/{merge['zero_sr']}/{merge['positive_sr']} 对。"
        "这支持分别报告覆盖、提取和联合指标的响应，不能把表述改变解释为方案质量改善。"
    )
    e2_zh += "\n\n" + control_table + "\n\n" + (
        f"表中均值显示六位小数，0.000000 不等于严格为零；等价编号的平均 ΔEff={equiv['mean_delta_Eff']:.9g}。"
        "[冻结逐对数据](judges/local_controls_supplement_v2/paired_results.csv)、[E2 图](figures_supplement_v2/controls_supplement_v2.png)。"
    )
    e4_zh = (
        f"E4 保留 supplement v2 的 {e4['actual_observations']} 个实际观测（两答案×两本地评价家族×三次），包括 {e4['successful_exact_reused_observations']} 条精确复用。"
        f"16 项指标、64 个重复分项组的有波动组数为 {e4['component_groups_with_variation']}，32 个评价器×指标排名记录的严格翻转数为 {e4['strict_rank_flip_metrics']}。"
        f"Llama {e4['rubric_example_copies']}/6 次复制量表示例并提取了错误路线，Qwen 6/6 无这两个标记。数值重复性不能证明忠实性或可靠性。"
        "[实际观测](judges/local_stability_supplement_v2/development_summary.json)、[E4 图](figures_supplement_v2/stability_supplement_v2.png)。"
    )
    e3_zh = (
        f"E3 的 v4_dev_v2 仍有 {e3['actual_auto_records']} 份实际开发提取和 {e3['guarded_identity_replay_pass']} 份原函数 identity 复核，"
        f"{e3['pending_auto_answers']} 份留出待定。路线/marker/总时间的实际字段判项为 {e3['direct_route_marker_total_time_item_rows']}；"
        f"组织/尺度 {e3['tissue_scale_partial_schema_rows']} 项只有原文与 sample_ri，旧 schema 无组织身份/尺寸字段，不能称完整抽取。"
        "protocol_time_hours 均为 null；A01 的真实 s_label=NA 继续使 Eff/IA/HV 为 NA，其他已知分项保留。"
        "纠错入口固定原需求、原科学选择及代码/输入哈希，能调用原 EGES；identity 核查不等于已观测专家纠错效果。"
        "[真实提取与核验](human_review/rescoring/v4_dev_v2/summary.json)。"
    )
    human_zh = (
        f"新增人工仍是一位专家、5份开发＋15份留出，步骤匹配与提取核查共用；原20答案/160判项已回传 {frozen['returned_items']} 项。"
        f"{frozen['lineage']['original_answers_hash_bound']} 份历史答案已绑定 {frozen['lineage']['versions']} 个 Git 历史版本，"
        "旧0..5约定不解决完整量表、专家身份和 signed scale 映射问题。"
        f"定向开发步骤判项 reviewed={frozen['local']['reviewed_rows']}；E1/E3 完整预定核查分母仍为0，错误率和纠错效果为NA。"
        "参考建设单独记录，不占用20份人工核查名额。"
        "[核查分母与影响](human_review/review_impact_addendum/summary.json)、[历史版本](human_review/lineage/summary.json)。"
    )
    alt_zh = (
        f"既有两来源替代开发批为 {alt['technical_successful_cases']}/{alt.get('planned_cases', 9)} 份技术成功、"
        f"{alt['complete_candidate_cce_pairs']}/{alt.get('candidate_pairs', 6)} 对完整描述性比较，正式合格 {alt['formal_completed_pairs']} 对。"
        "partial co_chemical 未自动映射为 co_chem。6个候选对仅覆盖3个题号/1任务家族，跨生成模型并共享基线；"
        "q1 的新增逐答案分数也不新增合理替代路线配对，因此仍不满足6–8个不同任务的合格替代路线比较。"
        "[真实替代结果](judges/local_alternative_development/development_summary.json)、[替代图](figures_supplement_v2/alternative_development_pairs.png)。"
    )
    retained_en = (
        f"The frozen supplement-v2 controls retained {e2['technical_successful_cases']} full-text evaluations and {e2['complete_candidate_cce_pairs']} complete candidate pairs from three source answers. "
        f"RI/storage deletion reduced SR in {deletion['negative_sr']}/{deletion['n_sr']} pairs, explicit-time deletion reduced parameter completeness in {param['negative_c_param']}/{param['n_c_param']}, "
        f"and order conflicts reduced the order score in {order['negative_co_order']}/{order['n_co_order']}. "
        "Merging unchanged operation text could raise or lower SR. The unchanged alternative batch yielded five complete descriptive pairs across only three question IDs in one task family, short of 6–8 qualified different-task comparisons. "
        "Adding a source-bound task does not add a validated alternative-route pair.\n\n"
        f"The local stability batch retained {e4['actual_observations']} observations, including {e4['successful_exact_reused_observations']} exact reuses. "
        "All 16 metrics had zero within-group ranges and no strict rank flips, but all six Llama extractions copied the rubric example and mismatched the answer route. "
        "Numerical repeatability did not establish extraction fidelity. Five actual development extractions passed original-function identity replays; A01 retained a missing label component and dependent Eff/IA/HV missingness. "
        "Fifteen holdouts remain pending. One expert and the 5-development/15-holdout shared-review design are unchanged; completed expert-review denominators are zero and correction effects remain NA. "
        "Source construction does not use these human-review slots. All retained experiments keep their actual reference/configuration versions and are not counted as new calls or independent cases."
    )
    return {"e2_zh": e2_zh, "e3_zh": e3_zh, "e4_zh": e4_zh, "human_zh": human_zh, "alt_zh": alt_zh, "retained_en": retained_en}


def build():
    data = load_completed_inputs()
    run = read(VERSION + "/run.json")
    plan = read(VERSION + "/plan.json")
    verification = read(VERSION + "/verification.json")
    refs = read(VERSION + "/references.json")["references"]
    config = read(PREFIX + "_t070_resolved_config.json")
    source_configs = [read("supplement_v2_idisco_t070_resolved_config.json"), read(Q1 + "/t070_resolved_config.json")]
    for item, name in ((run, "composition run"), (verification, "composition verification")):
        require_pass(item, name)
    assert run["composition_plan_sha256"] == sha(OUT / VERSION / "plan.json")
    for path, digest in run["output_sha256"].items():
        assert sha(path) == digest, path
    for path, digest in plan["input_sha256"].items():
        assert sha(path) == digest, path
    assert verification["rows_checked"] == sum(len(rows) for rows in data["batches"].values())
    assert all(all(row[key] for key in ("full_text_and_stem_identity", "archived_components_preserved", "original_core_route_and_candidate_pool_unchanged")) for row in verification["checks"])
    assert all(row["old_and_added_rows_deep_equal"] for row in run["batches"])
    assert run["new_model_requests"] == run["new_scoring_rows"] == run["new_embeddings"] == 0
    grid = read(VERSION + "/t070_grid.json")
    fixed = read(ANALYSIS + "/revised_full_fixed_cohort.json")
    subset = read(ANALYSIS + "/pilot_participating_subset.json")
    previous_subset = read("analysis_supplement_v3/pilot_participating_subset.json")
    gaps = read(GAPS + "/summary.json")
    thresholds = read(ANALYSIS + "/threshold_sensitivity.json")
    coverage = read(ANALYSIS + "/dataset_coverage_metadata.json")
    figure_qa = read(ANALYSIS + "/figure_visual_qa.json")
    analysis_run = read(ANALYSIS + "/analysis_run.json")
    plot_run = read(FIGURES + "/q1_plot_run.json")
    require_pass(figure_qa, "figure QA")
    assert not analysis_run["formula_mismatches"]
    for key in ("common_question_ids", "means", "empirical_nondominated", "dominance_matrix", "bootstrap"):
        assert subset[key] == previous_subset[key], "Prespecified comparison changed: " + key
    frozen = load_frozen_context()
    prose = retained_evidence_prose(frozen)
    q1_language = read(Q1 + "/language_and_truncation.json")
    q1_archive = read(Q1 + "/archive_component_verification.json")
    require_pass(q1_archive, "q1 archive component verification")
    q1_source = read("reference_recovery/q1_idisco_plus_2016_applicability/source_applicability.json")
    primary = data["counts"][70]
    pilot = data["batches"][70]
    q1_actual = [row for row in data["q1"][70] if row.get("answer_sha256")]
    missing_q1 = [row for row in data["q1"][70] if not row.get("answer_sha256")]
    count = gaps["state_counts"]
    assert count["provisional_CCE_numeric"] == primary["candidate_cce_numeric"]
    assert count["screened_reference_insufficient"] == sum(row.get("step_missing_reason") == "reference_insufficient" for row in pilot)
    assert sum(count.values()) == gaps["expected_cells"]
    assert len(grid) == primary["actual_answers"] + len(missing_q1)
    assert primary["question_ids"] == plan["question_ids"]
    assert len(refs) == run["reference_branches"]
    models_with_values = {row["model"] for row in pilot if finite(row.get("sr"))}
    model_n = run["fixed_model_n"]
    routes, families = sorted({r["route_id"] for r in refs}), sorted({r["family_id"] for r in refs})
    calls = len(frozen["ledger"])
    budget_limit = source_configs[0]["budget"]["default_max_additional_api_requests"]
    means = subset["means"]
    flash, pro = means["gemini-3-flash"], means["gemini-3-pro"]
    q1_table = table(["q1 存档模型", "SR", "SP", "Com", "Cor", "Eff", "IA", "HV"],
                     [[row["model"], *[fmt(row.get(metric)) for metric in ("sr", "sp", "Com", "Cor", "Eff", "IA", "HV")]] for row in q1_actual])
    mean_table = table(["预先指定模型（共同5题）", "Com", "Cor", "Eff", "IA", "HV"],
                       [[model, *[fmt(scores[metric]) for metric in ("Com", "Cor", "Eff", "IA", "HV")]] for model, scores in means.items()])
    cjk = [row for row in q1_language["answers"] if row["answer_present"] and row["parsed_cjk_steps"]]
    language_note = "；".join(f"{row['answer_id']} 解析 {row['parsed_steps']} 步（中文 {row['parsed_cjk_steps']} 步）" for row in cjk)
    ablation = data["ablation"]
    first = (
        f"本轮把历史 q1 活动神经元任务与已恢复的 iDISCO+ 2016 来源绑定，完成固定 {model_n} 模型的独立三阈值评分："
        f"q1 有 {primary['q1_actual_answers']} 份真实存档答案、{primary['q1_missing_slots']} 个缺答格，其中 {primary['q1_step_numeric']} 份得到暂定 SR/SP 和候选 CCE。"
        f"将这些成功结果与原 {primary['prior_actual_answers']} 份 v3 结果逐对象原样组合后，当前 {len(primary['question_ids'])} 个题号、{primary['actual_answers']} 份真实答案中有 {primary['step_numeric']} 份步骤数值、"
        f"{primary['candidate_cce_numeric']} 份候选 CCE，正式合格 {primary['formal_eligible']} 份。"
        "新增的是任务绑定和可评价覆盖，没有新增独立来源家族，也不是生成模型改善。原参数完整性、Correctness、EGES 和各行配置哈希保持原样；本轮没有新增模型请求。"
    )
    common = (
        f"固定 {model_n} 模型×{gaps['question_count']} 题共 {gaps['expected_cells']:,} 格：暂定 CCE 数值 {count['provisional_CCE_numeric']}、筛选后参考不足 {count['screened_reference_insufficient']}、"
        f"新步骤评分未运行 {count['revised_steps_not_run']:,}、缺答 {count['answer_missing']}。"
        f"{len(models_with_values)}/{model_n} 个模型至少有一份数值，但全队列数值 Q*={len(gaps['numeric_common_question_ids'])}、正式 Q*={len(gaps['formal_common_question_ids'])}。"
        "每个模型局部有分不等于共享可比题集；未运行也不等于参考不存在。"
    )
    scope = (
        "q1 原题允许自行选择适当标记，再给出透明/RI/保存及成像前处理；元数据的 cFos/Npas4 推荐不能升级成必须双标。"
        "已固定不等于已完成免疫标记。新增分支沿用已封审的9个透明/RI/保存操作，上游免疫是进入该分支的条件，不扩大题干评分分母。"
        "单一适当 IEG 策略在题目允许范围内，但行为后至固定间隔未知，未据此确认任意活动标记的实验效果。"
        f"当前 {len(refs)} 个来源参考分支来自 {len(routes)} 条路线和 {len(families)} 个来源家族，均为 source_extracted 候选、专家确认0。"
        "q1 与 q2 共用 Renier 2016 来源家族；没有把 generic iDISCO 自动合并为 iDISCO+，也没有改变原 FDISCO/PEGASOS 四分支。"
    )
    driver = (
        f"q1 的 {data['q1_concordance']['compared_observations']} 个实际答案×阈值观测与原 core 入口在路线、参考、NA、解析、SR/SP、匹配和截断上全部一致，"
        f"使用 {data['q1_concordance']['cached_unique_vectors']} 个缓存向量、0新向量。组合阶段还用完整6分支集合核对 {verification['rows_checked']} 个答案×阈值的原 core 路线/候选池，"
        "并核对原文、题干和存档分项身份；这一步是精确复用核验，不是再次计算所有语义分数。"
        "有限实测一致不代表 driver 普适等价：q1 v1 的首行/全角冒号声明 gate 与原 core 不同，且把所有非缺答的空解析判为 evaluator_failure，而原 core 对真正无操作的相容空答案可计0。"
        "当前实际答案全部解析非空，这两个边界没有改变本批结果；未来输入不能直接沿用该 driver 的未验证边界。"
    )
    ablation_note = (
        f"在既有 v2 RI/保存模块删除的全部 {ablation['pairs']} 对、{ablation['full_texts']} 份全文上，新增离线筛选诊断精确重现原解析与筛选 SR/SP。"
        f"有筛选和无筛选都仅 {ablation['filtered_deletion_sr_drop_pairs']}/{ablation['pairs']} 对 SR 下降，"
        f"跨路线选择 {ablation['pairs_with_cross_route_selection']} 对，ΔSR 不同 {ablation['pairs_with_different_deletion_sr_delta']} 对。"
        "这是阴性诊断：当前三对没有显示跨路线借用或筛选改变删除效应，不能据此声称 cross-route 机制已验证。"
        "没有新 judge 请求、独立实验对或主 CCE 改写；编辑必要性与来源适用仍待专家确认。"
    )
    rd = frozen["route_v3"]["overall"]
    route_history = (
        f"此前 v3 对65份原答案的无筛选诊断仍单独保留：其 {rd['main_sr_missing_n']} 份主参考不足中 {rd['main_missing_with_positive_unfiltered_sr_n']} 份得到正 SR，"
        f"{rd['main_missing_with_zero_unfiltered_sr_n']} 份为0；原 {rd['paired_main_numeric_n']} 份有分答案中 SR 和 SP 各改变 {rd['paired_sr_changed_n']} 和 {rd['paired_sp_changed_n']} 份。"
        "这些是65份旧范围的诊断数，不是当前77份的无筛选统计，也不回填主 NA。"
    )
    next_step = (
        "下一项独立工作是继续 CUBIC-HV 与 SOLID 的准确版本、完整方法和题目条件绑定；新取回附件及来源候选尚未进入本轮评分或参考计数。"
        "q13–15 的标记目标和输出范围逐题核查，不把元数据推荐或来源线索直接升级为合格替代方案。"
        "专家回传后可用既有 guarded 入口计算真实纠错影响；其余未运行行继续按参考与任务绑定逐步扩展。"
    )
    figures = [f"[{stem}]({FIGURES}/{stem}.png)" for stem in ("q1_step_thresholds", "coverage", "threshold_sensitivity", "development_cce_projections", "dataset_category_coverage") if (OUT / FIGURES / (stem + ".png")).exists()]
    figures += ["[E2 冻结 v2](figures_supplement_v2/controls_supplement_v2.png)", "[E4 冻结 v2](figures_supplement_v2/stability_supplement_v2.png)", "[替代开发 v2](figures_supplement_v2/alternative_development_pairs.png)", "[此前 q2 来源扩展 v3](figures_supplement_v3/idisco_reference_expansion.png)"]
    commands = []
    for name, value in ((VERSION + "/run.json", run), (ANALYSIS + "/analysis_run.json", analysis_run), (GAPS + "/summary.json", gaps), (FIGURES + "/q1_plot_run.json", plot_run), (ANALYSIS + "/figure_visual_qa.json", figure_qa), (ABLATION + "/summary.json", ablation)):
        command = value.get("actual_command") or value.get("command")
        if isinstance(command, str):
            commands.append({"source": name, "command": command, "status": value.get("status", "completed_artifact_present")})
    commands.insert(0, {"source": Q1 + "/actual_commands.ps1", "command": textread(Q1 + "/actual_commands.ps1").strip(), "status": "completed_q1_summary_verification_and_core_concordance_present"})
    deps = {
        "expert_review": "One expert, 5 development + 15 holdout shared step/extraction review; zero returns, completed-review rates and correction effects remain NA.",
        "reference_validation": f"{len(refs)} task-bound branches from {len(families)} source families remain source-extracted candidates, not expert-confirmed gold. q1/q2 immunolabeling is conditional; 3 mm schedules remain unknown; native tdTomato preservation is not established for the iDISCO+ q248 branch.",
        "q1_driver_boundary": config["q1_driver_limits"],
        "cohort_coverage": count, "common_numeric_questions": gaps["numeric_common_question_ids"], "common_formal_questions": gaps["formal_common_question_ids"],
        "language_matching": "English all-mpnet-base-v2 is not independently validated for Chinese steps. Nonempty Chinese answers can score zero without truncation.",
        "alternative_routes": "Five complete descriptive candidate pairs cover three question IDs in one task family; q1 scoring adds no qualified alternative pair. Broader exact-source/task bindings are in progress and excluded from current coverage.",
        "extraction_effect": "Five identity replays verify software; expert-corrected effects and 15 holdout audits remain pending, with incomplete legacy tissue/size fields.",
        "historical_human_scale": "Historical 0..5 labels do not establish original full rubric, expert identity or signed-scale mapping.",
        "historical_q29": "Two raw score blocks were recovered but raw/stored co_chem conflict and incomplete identity prevent silent score repair.",
        "evaluator_validity": "The local diagnostic evaluator is not the unavailable historical judge; six rubric-copy failures preclude a reliability claim.",
        "wetlab": frozen["wet"]["remaining_minimum_inputs"],
        "next_independent_work": next_step,
    }
    budget = {"limit": budget_limit, "attempts_recorded": calls, "remaining_request_capacity": budget_limit - calls,
              "model_attempts": dict(collections.Counter(row["model"] for row in frozen["ledger"])), "retries_counted": True,
              "reused_observations_count_as_new_requests": False,
              "expert_budget": {"experts": 1, "development": 5, "holdout": 15, "returned_answers_any_item": frozen["returned_answers"], "returned_items": frozen["returned_items"]},
              "reference_construction_separate": True, "ledger_sha256": sha(OUT / "judges/request_ledger.jsonl")}
    outputs = {}
    outputs["RESULTS_zh.md"] = f"""# ClearEval r2 当前补充结果：任务扩展 v4

{first}

{q1_table}

上表只列真实 q1 答案；Gemini Flash 缺答保留在固定网格，未制造答案或补0。DeepSeek Chat 明确选择 uDISCO，缺少该任务的相容参考，SR/SP/Com/IA/HV 保持 NA，原 Cor/Eff 保留。{language_note}；两份 GPT 答案在三个阈值均 SR/SP=0，但解析不空且无步骤截断，不能解释为没有操作。English all-mpnet-base-v2 的跨语言匹配仍待独立验证。[q1 实际结果]({Q1}/RESULTS.md)、[语言核查]({Q1}/language_and_truncation.json)、[当前逐答案表]({PREFIX}_t070_per_answer.csv)。

{scope} [q1 条件绑定](reference_recovery/q1_idisco_plus_2016_applicability/source_applicability.json)、[独立反审]({Q1}/review.json)、[当前来源集合]({VERSION}/references.json)。此前 iDISCO+ 论文 supplement 的28个已固定后来源操作与9个评分操作分开，April 2016 Bench 参数分歧未静默合并。q248 要求的原生 tdTomato 荧光不能由免疫信号/自发荧光证据替代；新增 iDISCO+ 主分支仍不绑定 q248，原 FDISCO/PEGASOS 绑定不变，4份 route-only 诊断不计 CCE 或覆盖。[来源边界](reference_recovery/idisco_plus_2016/README.md)、[q248 独立诊断](reference_recovery/idisco_plus_2016/review/q248_route_only_diagnostic/summary.json)。

{driver} [原 core 对照]({Q1}/core_concordance.json)、[组合核验]({VERSION}/verification.json)、[实际配置]({PREFIX}_t070_resolved_config.json)。每阈值组合表 {primary['actual_answers']} 行与局部固定网格 {len(grid)} 格分开保存；组合动作新计算评分行数为0，不能把复制现有评分称为新模型评价。

{common} [全格缺口]({GAPS}/cell_status.csv)、[全量新/历史覆盖]({ANALYSIS}/joint_summary.json)。q29 的两个完整 raw 块与后存层 co_chem 有0/1冲突，未选择有利层或补 Cor/Eff。[只读核查](inventory/partial_score_q29/audit.json)。

{mean_table}

Gemini Pro 当前有 {subset['per_model_eligible_n']['gemini-3-pro']} 题数值，Flash 有 {subset['per_model_eligible_n']['gemini-3-flash']} 题；预先指定双模型共同集仍是 {subset['common_n']} 题，逐题 IA/HV 均值、非支配结果和 bootstrap 与 v3 逐值不变。该子集非支配模型为 {', '.join(subset['empirical_nondominated'])}，不构成全队列排名。2,000 次同步来源家族 bootstrap 仍仅 {subset['bootstrap']['source_family_count']} 个家族，状态 {subset['bootstrap']['status']}。阈值比较按每指标各阈值共同有限值交集；SR/SP 分母均为 {thresholds['common_finite_pairs_by_metric']['sr']}。每模型覆盖题数不同，不能把阈值图当共同任务排名。[共同题集]({ANALYSIS}/pilot_participating_subset.json)、[阈值诊断]({ANALYSIS}/threshold_sensitivity.json)。

{ablation_note} [逐对诊断]({ABLATION}/paired_results.csv)、[独立侧审]({ABLATION}/review.json)。

{prose['e2_zh']}

{prose['alt_zh']}

{prose['e4_zh']}

{prose['human_zh']} {prose['e3_zh']}

{route_history} [旧65份范围的筛选诊断](controls/supplement_v3_route_filter_diagnostic_summary.json)。

原领域覆盖分析仍使用 {coverage['mcq_final']['rows']:,} 道 MCQ 与 {coverage['qar_historical']['question_rows']} 道开放题的实际分类、组织和尺度字段；缺失字段保持缺失。[分类覆盖 CSV]({ANALYSIS}/dataset_coverage.csv)。湿实验真实测量 {frozen['wet']['real_measurement_rows']} 行、假设功效情景 {frozen['wet']['planning_scenarios']} 个，不能声称 CCE 已预测实验效果。[湿实验计划](wetlab/WETLAB_PLAN.md)。

图表：{'、'.join(figures)}。本轮 {figure_qa['render_sets']} 套图中 {figure_qa['directly_viewed_renders']} 张实际目视，其他6张PNG与已检查渲染字节一致；q1阈值图核对 {figure_qa['new_answer_rows_checked']} 行，阈值汇总核对 {figure_qa['threshold_summary_rows_checked']} 行。历史 v1 控制/稳定图镜像不是当前 v2 结果或新实验。[图表 QA]({ANALYSIS}/figure_visual_qa.json)。

{next_step} [来源预筛](reference_recovery/amyloid_task_source_prescreen/README.md)。全包实际模型请求 {calls}/{budget_limit}，本轮新增0；专家回传和湿实验效果仍待定。[实际命令](commands.md)、[当前索引](current_run_index.json)、[剩余依赖](remaining_dependencies.json)、[v3 字节快照](historical_reports/supplement_v3_before_q1/snapshot_manifest.json)。
"""
    outputs["Methods_Results_en.md"] = f"""# ClearEval supplementary methods and results: task expansion v4

ClearEval retained its original parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring (EGES). Source-bound BioProBench Step Recall/Precision used all-mpnet-base-v2 at cosine threshold 0.7 with 0.6/0.8 sensitivity analyses. Task scope and declared route restricted references; maximum SR, then SP and frozen order resolved candidates. Com=0.4 SR+0.6 c_param/3; SP was reported separately. IA=min(Com,Cor,Eff) and zero-reference HV=Com×Cor×Eff were computed per answer before averaging. Unknown components propagated to dependent metrics without zero imputation. Dominance tolerance remained 1e-12.

The q1 extension froze all {model_n} generators before examining scores and recovered {primary['q1_actual_answers']} existing answers; Gemini Flash had no q1 answer. The original task allowed an appropriate selected activity marker followed by clearing/RI/storage instructions, rather than requiring both metadata-recommended IEGs. The nine-operation iDISCO+ branch was conditioned on prior immunolabeling, which was not assumed completed. It shared the already recovered 2016 source family with q2 and added no independent source family. Generic iDISCO was not merged into iDISCO+. Eleven route-compatible answers yielded provisional steps; the answer declaring uDISCO retained reference-insufficient NA and available archived quality components. Two Chinese answers parsed into 38 and 34 nonempty steps, respectively, but had zero SR/SP at all three thresholds without truncation. Cross-language semantic accuracy remains unvalidated. [q1 source and results]({Q1}/RESULTS.md).

The actual q1 semantic results matched the original core on {data['q1_concordance']['matching_observations']}/{data['q1_concordance']['compared_observations']} answer-by-threshold observations. This finite concordance does not establish universal driver equivalence: declaration handling and the empty-parse branch differ. All present answers in this batch had nonempty parses. The composition additionally checked original-core route/candidate-pool invariance, full-text/stem identity and preserved archived components for {verification['rows_checked']} answer-by-threshold rows, without new embeddings or semantic scoring. Each old and added row, including its original configuration hash, was retained exactly. Missing-answer placeholders were kept only in grids. [Core concordance]({Q1}/core_concordance.json), [composition verification]({VERSION}/verification.json).

At each threshold, the composition contains {primary['actual_answers']} actual answers from {len(primary['question_ids'])} tasks, with {primary['step_numeric']} provisional SR/SP and {primary['candidate_cce_numeric']} candidate CCE values. Formal eligibility remains {primary['formal_eligible']}. The full {model_n}-model × {gaps['question_count']}-question grid contains {count['provisional_CCE_numeric']} provisional CCE cells, {count['screened_reference_insufficient']} screened reference-insufficient cells, {count['revised_steps_not_run']} unrun revised-step cells and {count['answer_missing']} missing answer. Every generator has at least one numerical answer, but the numeric and formal common sets both remain empty; a revised full-cohort ranking is unsupported. [Current per-answer results]({PREFIX}_t070_per_answer.csv), [grid audit]({GAPS}/summary.json).

The prespecified two-Gemini common set remained the same five questions despite Pro having six individually eligible questions and Flash five. Mean IA/HV remained {fmt(flash['IA'])}/{fmt(flash['HV'])} for Flash and {fmt(pro['IA'])}/{fmt(pro['HV'])} for Pro. Means, the nondominated set and 2,000 synchronized source-family bootstrap results were unchanged. The bootstrap still had one source family and was degenerate. Threshold summaries used metric-specific finite intersections; different per-model task coverage precludes reading them as a shared-task ranking. [Joint analysis]({ANALYSIS}/joint_summary.json).

An additional offline filter diagnostic used all three existing RI/storage-deletion pairs, preserving their six full texts and original filtered values. Both filtered and unrestricted scoring detected an SR decrease in only one pair, with zero cross-route selections and zero differences in SR deltas. This negative result does not demonstrate a cross-route failure mechanism. It added no judge requests, independent pairs or primary CCE changes. The earlier unrestricted-reference diagnostic remains explicitly limited to its original 65-answer v3 batch; its values were not pooled into a new 77-answer ablation. [Paired diagnostic]({ABLATION}/summary.json).

{prose['retained_en']} [Frozen controls](judges/local_controls_supplement_v2/control_summary.json), [human-review effects](human_review/review_impact_addendum/summary.json).

All {len(refs)} reference branches from {len(families)} source families remain source-extracted development candidates. The 2016 article supplement and dated bench version remain distinct; native tdTomato preservation in q248 is unsupported for the added iDISCO+ branch, whose route-only diagnostics do not enter primary coverage or CCE. New CUBIC-HV/SOLID source recovery is outside this scoring version. Historical human-scale provenance and signed-scale mapping remain unresolved. Wet-lab measurement rows remain {frozen['wet']['real_measurement_rows']}. Recorded model requests remain {calls}; q1 scoring, composition, analysis and this report added none. [Current index](current_run_index.json).
"""
    outputs["Abstract_en.md"] = f"""# Draft abstract: supplementary development evidence

Fixed-sample tissue-clearing protocol selection and generation require matching sample scale and labeling with imaging and preservation goals. ClearEval assesses procedural coverage and tradeoffs through parameter completeness and correctness, including omitted operations, missing parameters and order errors; Evidence-Grounded Effectiveness Scoring relates proposed choices to task-specific evidence. We added source-bound Step Recall and Step Precision without changing those original components. We examined {primary['actual_answers']} archived answers from {model_n} models across {len(primary['question_ids'])} tasks using source candidates from three families. {primary['step_numeric']} answers yielded provisional step scores and {primary['candidate_cce_numeric']} candidate CCE values, including {primary['q1_step_numeric']} newly evaluated answers from an activity-mapping task that reused an existing source family. The fixed-cohort common set remained empty. A prespecified two-model, five-question comparison was unchanged and retained a degenerate single-family bootstrap. Frozen full-text controls yielded {frozen['e2']['complete_candidate_cce_pairs']} descriptive pairs, revealing nonresponses to parameter omissions and order conflicts and sensitivity to step granularity. Removing route filtering in three existing deletion pairs did not change their SR effects. Repeated local evaluation was numerically stable, but rubric-copy extraction failures prevented reliability claims. Cross-language matching, expert correction effects, broader qualified alternative-route comparisons and wet-lab outcomes remain unresolved. These results expand traceable partial evaluation while identifying limits on model ranking and experimental predictive claims.
"""
    outputs["STATUS.md"] = f"""# ClearEval r2 当前状态：任务扩展 v4

{first}

{common}

q1 的原 core 实际结果对照为 {data['q1_concordance']['matching_observations']}/{data['q1_concordance']['compared_observations']}；组合另核 {verification['rows_checked']} 行原 core 路线/候选池及存档身份，保留原配置哈希。声明 gate 与空解析的两个未泛化边界继续明确记录。新增三对筛选诊断为阴性：有/无筛选都仅1对SR下降，无跨路线选择或ΔSR差异；未增加独立对。[q1 审阅]({Q1}/review.json)、[组合核验]({VERSION}/verification.json)、[阴性诊断]({ABLATION}/summary.json)。

冻结实验继续复用：E2 {frozen['e2']['complete_candidate_cce_pairs']} 对，E4 {frozen['e4']['actual_observations']} 观测，E3 {frozen['e3']['actual_auto_records']} 份实际开发提取，替代路线 {frozen['alt']['complete_candidate_cce_pairs']} 对完整描述比较；版本保持各自 v2，不累计为新实验。人工仍 {frozen['returned_items']} 回传判项、15留出待定；湿实验 {frozen['wet']['real_measurement_rows']} 真实测量。全包模型请求 {calls}/{budget_limit}，本轮新增0。

{next_step} [来源预筛](reference_recovery/amyloid_task_source_prescreen/README.md)、[E1/E3 分母](human_review/review_impact_addendum/summary.json)、[剩余依赖](remaining_dependencies.json)。

详细结果见 [RESULTS_zh.md](RESULTS_zh.md)，机器入口为 [current_run_index.json](current_run_index.json)。`python scripts/cce_report.py` 检测已完成组合后优先进入 v4 生成器；[实际命令](commands.md)仅列已执行记录。更新前 v3 主报告与 current 元数据已[按字节快照](historical_reports/supplement_v3_before_q1/snapshot_manifest.json)，旧评分文件不变。
"""
    lines = ["# 本阶段已实际执行的命令", "", "仅收录有完成产物支撑的实际命令。q1 离线评分、原 core 对照、组合、分析和诊断不产生新模型请求。此前执行记录见 [v3 命令快照](historical_reports/supplement_v3_before_q1/commands.md)。", ""]
    for command in commands:
        lines += [f"来源 [{command['source']}]({command['source']})；状态 `{command['status']}`。", "", "```powershell", command["command"], "```", ""]
    lines += ["本次报告成功生成的实际命令、代码和全部输入/输出哈希见 [report_generation.json](report_generation.json)。报告生成器不调用模型、编码器或评分入口。"]
    outputs["commands.md"] = "\n".join(lines)
    outputs["remaining_dependencies.json"] = deps
    outputs["budget.json"] = budget
    outputs["reference_recovery/reference_construction_current.json"] = {
        "scope": "expanded_tasks_v4_source_extracted_candidates_not_expert_gold", "source_extracted_route_candidates": len(routes), "source_families": len(families),
        "task_specific_branches": [{"reference_id": r["reference_id"], "question_ids": r["question_ids"], "steps": len(r["steps"]), "status": r["status"], "formal_eligible": False} for r in refs],
        "reference_manifest": VERSION + "/references.json", "expert_confirmed_routes": 0, "human_confirmation": None, "formal_eligible": False,
        "separate_construction_records": ["reference_recovery/supplement_bound/construction_run.json", "reference_recovery/idisco_plus_2016/reference_construction_v1.json", "reference_recovery/q1_idisco_plus_2016_applicability/source_applicability.json"],
        "q1_reference_manifest": Q1 + "/references.json", "q1_reference_reuses_existing_source_family": True,
        "question_ids": primary["question_ids"], "pilot_actual_answer_links": primary["actual_answers"], "pilot_numeric_answer_links": primary["step_numeric"],
        "expert_minutes": None, "reference_construction_separate_from_20_answer_budget": True,
        "in_progress_sources_excluded": ["CUBIC-HV", "SOLID"], "remaining": deps["reference_validation"],
        "historical_availability_audit": "Main-text v1 availability prose is historical. Previously recovered official supplements remain available; new task/reference construction is versioned independently.",
    }
    outputs["resolved_config_current.yaml"] = {
        "format_note": "JSON serialization is valid YAML 1.2", "version": VERSION, "composition_configuration": config,
        "original_source_configurations": source_configs, "row_configuration_hashes_preserved": True,
        "current_execution": {"primary_run": VERSION + "/run.json", "primary": PREFIX + "_t070_per_answer.json", "reference": VERSION + "/references.json", "joint_analysis": ANALYSIS,
                              "frozen_controls": "judges/local_controls_supplement_v2", "frozen_stability": "judges/local_stability_supplement_v2", "frozen_extraction": "human_review/rescoring/v4_dev_v2",
                              "report_generator": "scripts/cce_report_expanded_tasks_v4.py", "formal_eligible": False},
    }
    outputs["current_run_index.json"] = {
        "version": VERSION, "formal_eligible": False, "primary": PREFIX + "_t070_per_answer.json", "thresholds": [f"{PREFIX}_t0{t}_per_answer.json" for t in (60, 70, 80)],
        "composition": VERSION + "/run.json", "plan": VERSION + "/plan.json", "grid": VERSION + "/t070_grid.json", "reference": VERSION + "/references.json", "score_verification": VERSION + "/verification.json",
        "q1_results": Q1 + "/summary.json", "q1_review": Q1 + "/review.json", "q1_core_concordance": Q1 + "/core_concordance.json", "q1_language_diagnostic": Q1 + "/language_and_truncation.json",
        "q1_source_applicability": "reference_recovery/q1_idisco_plus_2016_applicability/source_applicability.json", "q1_driver_limitations": config["q1_driver_limits"],
        "analysis": ANALYSIS + "/joint_summary.json", "gap_audit": GAPS + "/summary.json", "figure_qa": ANALYSIS + "/figure_visual_qa.json",
        "actual_counts": primary, "old_and_added_rows_deep_equal": True, "row_configuration_hashes_preserved": True, "added_independent_source_families": 0,
        "paired_route_ablation": ABLATION + "/summary.json", "paired_route_ablation_review": ABLATION + "/review.json", "paired_route_ablation_new_independent_pairs": 0,
        "frozen_controls": {"path": "judges/local_controls_supplement_v2", "version": "supplement_v2", "summary": frozen["e2"]},
        "frozen_stability": {"path": "judges/local_stability_supplement_v2", "version": "supplement_v2", "summary": frozen["e4"]},
        "frozen_extraction": {"path": "human_review/rescoring/v4_dev_v2", "summary": frozen["e3"], "identity": frozen["identity"]},
        "frozen_alternatives": {"path": "judges/local_alternative_development", "summary": frozen["alt"]},
        "review_impact": "human_review/review_impact_addendum/summary.json", "source_prescreen": "reference_recovery/amyloid_task_source_prescreen/README.md",
        "q248_diagnostic": "reference_recovery/idisco_plus_2016/review/q248_route_only_diagnostic/summary.json", "q248_diagnostic_enters_primary_CCE": False,
        "historical_reports": "historical_reports/supplement_v3_before_q1", "request_attempts": calls, "new_model_requests": 0, "recorded_commands": commands, "input_sha256": dict(INPUTS),
    }
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    outputs = build()
    if args.check_only:
        print(json.dumps({"status": "render_checked_without_writes", "outputs": len(outputs), "input_files": len(INPUTS), "new_model_requests": 0}))
        return
    snapshot()
    for name, value in outputs.items():
        save(name, value)
    save("report_generation.json", {
        "status": "completed", "version": VERSION, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "command": subprocess.list2cmdline([sys.executable, *sys.argv]), "script_sha256": sha(__file__),
        "dispatcher_sha256": sha(ROOT / "scripts/cce_report.py"), "inputs": dict(INPUTS),
        "outputs": {name: sha(OUT / name) for name in outputs}, "new_model_requests": 0, "old_result_batches_modified": False,
    })
    print(json.dumps({"status": "expanded_tasks_v4_reports_refreshed", "outputs": len(outputs), "requests_in_ledger": outputs["budget.json"]["attempts_recorded"], "new_model_requests": 0}))


if __name__ == "__main__":
    main()
