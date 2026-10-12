"""Publish the completed local delivery, or check its recorded files without scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/cce_validation"
R2 = OUT / "optimizer_round2_20261010"
WINDOW = R2 / "four_hour_extension_20261010"
DELIVERY = WINDOW / "delivery"
READOUT = DELIVERY / "current_readout_v2"
ARCHIVE = DELIVERY / "canonical_v3_before_source_recovery"
MANIFEST = DELIVERY / "canonical_delivery_manifest_v2.json"
PYTHON = Path("C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": sha(path)}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def local_link(label, path):
    return f"[{label}]({Path(path).as_posix()})"


def archive_current(paths):
    manifest = ARCHIVE / "manifest.json"
    if manifest.exists():
        old = read(manifest)
        for item in old["files"]:
            assert sha(item["archive"]) == item["sha256"], item["archive"]
        return old
    records = []
    for path in paths:
        if not path.exists():
            continue
        relative = path.relative_to(ROOT.parent)
        destination = ARCHIVE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        records.append({"original": str(path), "archive": str(destination), "sha256": sha(path)})
    result = {"saved_utc": datetime.now(timezone.utc).isoformat(), "files": records}
    write(manifest, result)
    return result


def check_current():
    manifest = read(MANIFEST)
    checked = manifest["current_files"] + manifest["scientific_inputs"] + [manifest["publisher"], manifest["dispatcher"]]
    for item in checked:
        assert sha(item["path"]) == item["sha256"], f"Changed: {item['path']}"
    ledger = [json.loads(s) for s in (OUT / "judges/request_ledger.jsonl").read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert len(ledger) == manifest["package_requests"]
    assert read(READOUT / "summary.json")["secondary_E5"]["complete_CCE"] == manifest["secondary_complete_CCE"]
    result = {"status": "pass", "checked_files": len(checked),
              "package_requests": len(ledger), "new_model_calls": 0, "scientific_results_recomputed": False,
              "overall_goal_complete": False, "delivery": str(DELIVERY / "REPORT_v4_zh.md")}
    print(json.dumps(result, ensure_ascii=False))
    return result


def main(publish=False):
    if not publish:
        return check_current()
    facts = read(READOUT / "summary.json")
    joint = facts["secondary_E5"]
    cohort = {row["cohort"]: row for row in facts["cohorts"]}
    verification = read(READOUT / "verification.json")
    for item in verification["bindings"]:
        assert sha(item["path"]) == item["sha256"], item["path"]
    assert verification["all67_direct_and_step_metrics_unchanged"]
    assert facts["uniform_raw_returns"] == 67
    assert facts["secondary_E5"]["metric_coverage"]["s_time"] == 10
    assert facts["expert_answers_returned"] == 0 and facts["wetlab"]["real_measurement_rows"] == 0
    now = datetime.now(timezone.utc).isoformat()
    current_paths = [ROOT.parent / "STATUS.md", R2 / "STATUS.md"] + [OUT / name for name in (
        "STATUS.md", "CURRENT_RESULTS_INDEX.md", "RESULTS_zh.md", "Methods_Results_en.md", "resolved_config_current.yaml",
        "resolved_config.yaml", "completion_audit_current.json", "remaining_dependencies.json", "commands.md", "budget.json")]
    archive_current(current_paths + [ROOT / "scripts/cce_report.py"])
    author = read(WINDOW / "authorization.json")
    model = read(OUT / "optimizer_20261010/grounded_development_v7/model_config.json")["models"][0]
    transport_path = DELIVERY / "canonical_transport_evidence_v1.json"
    transport = read(transport_path)
    phase_remaining = {phase: cap - facts["calls"]["phase"][phase] for phase, cap in author["phase_limits"].items()}
    stage = "four_hour_uniform_posthoc_v4_with_frozen_results_retained"
    scientific_paths = [READOUT / "summary.json", READOUT / "verification.json",
        DELIVERY / "REPORT_v4_zh.md", DELIVERY / "MANUSCRIPT_v4_EN.md",
        R2 / "posthoc_uniform_scoring_v4/actual_execution_01/summary.json",
        R2 / "posthoc_uniform_scoring_v4/actual_execution_01/verification.json",
        R2 / "posthoc_uniform_scoring_v4/actual_execution_01/implementation_addendum.json",
        R2 / "e4_cross_source_uniform_v4_v1/actual_execution_01/summary.json",
        R2 / "partial_joint_identifiability_posthoc_v1/independent_review_v4/review.json",
        DELIVERY / "E5_v4_independent_review.json",
        DELIVERY / "v4_difference_matrix_v1/revision02/summary.json",
        WINDOW / "figures_partial_posthoc_v4/provenance.json",
        WINDOW / "figures_complete_joint_posthoc_v4/provenance.json",
        DELIVERY / "final_blockers_by_answer_v4.md",
        DELIVERY / "final_blockers_by_answer_v4.json",
        DELIVERY / "figure_review_v4.json",
        R2 / "posthoc_uniform_scoring_v4/README_zh.md"]
    config = {
        "format_note": "JSON serialization is valid YAML 1.2", "version": stage, "execution_prompt_revision": "r2",
        "updated_utc": now, "historical_config_archive": str(ARCHIVE / "ClearEval-public/artifacts/cce_validation/resolved_config_current.yaml"),
        "local_evaluator": {**{key: value for key, value in model.items() if key != "format"},
            "base_declared_format": model["format"], "actual_current_Qwen_format": "schema_object",
            "actual_transport_evidence": binding(transport_path),
            "actual_transport_stages": [{"stage": row["stage"], "payloads_found": row["payloads_found"], "counts": row["counts"]} for row in transport["stages"]],
            "schema_order_ablation": binding(R2 / "generation_order_only_development_v1/exact_payload_comparison.json"),
            "transport_interpretation": "Base format=json was overridden by actual structured schemas; per-stage payloads, not the base declaration, specify decoding. Original FPC01 sorted schema differs from order-only and later confirmation.",
            "reported_family": "qwen35", "reported_parameters": "27.3B", "reported_quantization": "Q8_0",
            "published_model_identity_verified": False, "timeout_seconds": 600, "attempts_per_cell": 1},
        "second_evaluation_source": {"source": "actual Codex-agent submissions", "precise_backend": None,
            "decoding_settings": None, "verified_independent_model_family": False},
        "llama_current_evaluations_allowed": False, "earlier_round_llama_requests_retained_but_excluded": 3,
        "budget_authorization": author, "actual_counts": facts["calls"], "window_new_requests": 33,
        "remaining_total_request_capacity": 6, "remaining_phase_capacity": phase_remaining,
        "currently_phase_schedulable_requests": sum(phase_remaining.values()), "new_requests_scheduled": 0,
        "new_requests_by_source_in_window": {"local_Qwen": 22, "Codex": 11},
        "formulas": {"Com": "0.4*SR+0.6*c_param/3", "Cor": "(co_order/3+co_method/2+co_param/2+co_chem)/4",
            "Eff": "((s_method/2.5+1)/2+s_label/6+s_trans/3+s_time/3)/4", "IA": "min(Com,Cor,Eff)",
            "HV": "Com*Cor*Eff", "aggregation": "Compute IA/HV per answer, then average on the stated common set",
            "time": "3*exp(-0.5*(distance/tau)^2); tau=0.20*median below interval, 0.10*median above; within interval=3"},
        "step_matching": {"encoder": "sentence-transformers/all-mpnet-base-v2", "threshold": 0.7,
            "max_seq_length": 384, "original_SR_SP_retained": True, "reference_selection": "task/route-compatible full versions, max SR, max SP from same version, fixed order",
            "threshold_sensitivity": [0.6, 0.7, 0.8], "representation_normalization": "separate exposed development diagnostic only"},
        "scoring_versions": {"frozen": "fw3", "current_posthoc": facts["uniform_processor"],
            "raw_returns": 67, "prospective_confirmation": False, "full_input_implementation_bindings": str(scientific_paths[5]),
            "additional_helper_bindings": str(scientific_paths[6]), "original_raw_statuses_preserved": True},
        "secondary_cohort": {"models": facts["secondary_E5"]["fixed_generator_models"], "questions": [1, 2, 21, 22, 248],
            "selection": "coverage-directed; development-exposed; not independent random confirmation", "complete_CCE": facts["secondary_E5"]["complete_CCE"], "common_Qstar": facts["secondary_E5"]["common_question_ids"]},
        "resampling": {"draws": 2000, "seed": 20261010,
            "complete_common_tasks": {"n": joint["common_n"], "draws": 2000,
                "model_rows": 4000, "exact_ordered_draws": joint["common_n"] ** joint["common_n"],
                "exact_model_rows": 2 * joint["common_n"] ** joint["common_n"]},
            "partial_all_five_tasks": {"n": 5, "draws": 2000, "model_rows": 4000,
                "exact_ordered_draws": 3125, "exact_model_rows": 6250},
            "source_family": {"actual_draws": 0, "actual_model_rows": 0,
                "reason": "q22 selected reference family differs across the two generators; a unique task-family map is not established"},
            "synchronized_task_indices": True, "partial_bounds_are_not_imputed_points": True,
            "complete_Qstar_analysis_status": facts["secondary_E5"]["task_bootstrap_status"], "source_family_status": facts["secondary_E5"]["family_bootstrap_status"]},
        "human": {"experts": 1, "development": 5, "holdout": 15, "received": 0,
            "entry": str(OUT / "human_review/CURRENT_REVIEW_ENTRY.md"), "full_reference_work_recorded_separately": True},
        "wetlab": facts["wetlab"], "scientific_inputs": [binding(p) for p in scientific_paths]
    }
    for name in ("resolved_config_current.yaml", "resolved_config.yaml"):
        write(OUT / name, config)
    deps = {
        "updated_utc": now, "stage": stage, "overall_goal_complete": False,
        "expert_review": {"returned": 0, "planned": 20, "experts": 1, "entry": str(OUT / "human_review/CURRENT_REVIEW_ENTRY.md")},
        "current_joint_bottleneck": f"Time available in {joint['metric_coverage']['s_time']}/10; labeling undetermined in {10-joint['metric_coverage']['s_label']}/10. Known Com/Cor/SR/SP and other EGES fields retained.",
        "label_evidence": ["native reporter branch has no explicit original-rubric exemption", "marker/fluor columns and task scope gaps",
            "compound identity mappings not authored in source", "ambiguous or incorrect relation/source bindings in some raw returns"],
        "controlled_validity": ["q2 numbering changes c_param", "merged unchanged operations change original SR/SP",
            "step deletion decreases SR in only 1/3 pairs", "original co_param rubric does not uniquely cover every intermediate deviation"],
        "generalization": "Exposed small development cohorts; posthoc changes need independent confirmation after definitions freeze, within a newly specified budget/matrix.",
        "complete_references": "Source-derived conditional references remain separate from expert-confirmed scientific applicability; formal=false is not proof every source is unsuitable.",
        "historical_human_scale": "Authentic original s_method mapping and independence of machine-adjusted old labels unresolved.",
        "joint_main_scope": f"Historical 13-model common task is q2; current secondary complete common tasks are {joint['common_question_ids']}. No broad ranking supported.",
        "source_family_resampling": {"actual_status": joint['family_bootstrap_status'], "limitation": "Overlapping/mismatched source identities cannot supply invented independent family units."},
        "wetlab": facts["wetlab"], "model_requests_running": 0, "automatic_retries_planned": 0,
        "next_action": "Use final per-answer blocker evidence, obtain specified source/rubric decisions or real expert returns, then version and rerun only affected inputs. Preserve current results.",
        "independent_work_completed": ["67-return uniform replay", "final E2/E4/E5", "partial bounds and independent 10250-draw-row verification", "legacy alias recovery", "paper figures and report"]
    }
    write(OUT / "remaining_dependencies.json", deps)
    audit = {"status": "computations_delivered_scientific_validity_and_external_data_pending", "overall_goal_complete": False,
        "updated_utc": now, "package_requests": 388, "round_requests": 94, "window_requests": 33,
        "items": [
            {"goal": "source-traceable SR/SP pilot and expansion", "state": "executed_conditionally", "scope": "historical 77 answers/6 tasks/13 models; primary numerical50, same-method sensitivity66"},
            {"goal": "original formulas and known fields", "state": "verified_preserved", "scope": "all67 direct/Com/Cor/SR/SP equal frozen fw3"},
            {"goal": "E1/E3 shared expert review", "state": "prepared_0_of_20_received", "scope": "expert correction effects unavailable"},
            {"goal": "E2 full-text pairs", "state": "executed_with_failures_and_anomalies", "scope": f"21 texts,15 pairs,{facts['E2_complete_CCE_pairs']} complete CCE pairs; validity limitations remain"},
            {"goal": "reasonable alternate routes", "state": "9_candidates_7_numerical_pairs_0_expert_confirmed",
                "scope": "overall9 pairs: q21-23 subset6/6 after alias recovery plus q248 1/1; q1/q2 0/2. The alias batch has9 raw returns and6 pairs, not9 pairs. Legacy configuration separate from Qwen27b"},
            {"goal": "E4 repeated evaluation", "state": "executed", "scope": "Qwen14/15 and Codex12/12; no accuracy claim"},
            {"goal": "E5 complete common-set comparison", "state": "analyzed_with_coverage_limits", "scope": f"current {joint['complete_CCE']}/10 complete, Q*={joint['common_n']}/5; partial bounds separate"},
            {"goal": "E6 planning", "state": "implemented_no_real_measurements", "scope": "42 assumption scenarios; final N unknown"},
            {"goal": "paper delivery and reproducibility", "state": "delivered", "scope": "Chinese/English report, figures, exact commands, configuration and hashes"}],
        "remaining_scientific_work": deps["controlled_validity"] + deps["label_evidence"],
        "external_dependencies": ["expert review", "authentic historical label provenance", "wet-lab observations"],
        "no_score_imputation": True, "scientific_accuracy_established": False}
    write(OUT / "completion_audit_current.json", audit)
    write(OUT / "budget.json", {"package_limit": 394, "attempts_recorded": 388, "round_limit": 100, "round_attempts": 94,
        "remaining_request_capacity": 6, "phase_attempts": facts["calls"]["phase"], "phase_limits": author["phase_limits"],
        "remaining_phase_capacity": phase_remaining, "currently_phase_schedulable_requests": sum(phase_remaining.values()),
        "automatic_retries": False, "deadline_utc": author["deadline_utc"], "ledger": binding(OUT / "judges/request_ledger.jsonl"),
        "replay_plot_and_resample_new_requests": 0, "human_budget": {"experts": 1, "development": 5, "holdout": 15, "received": 0}})
    status = f"""# ClearEval 当前状态

更新UTC：{now}。四小时授权固定止于2026-10-10 22:23:18北京时间。模型批次已终态；本轮计算和论文交付已完成，科学有效性及外部资料仍有具体缺口，整体目标未全部完成。

最新统一v4已处理67份已有返回。全部五项直接评分、Com、Cor和原SR/SP逐值等于冻结fw3。v3曾纠正32个目录错误零分；v4继续恢复原文已明确而引用/端点错误的关系，逐条保留来源和未知项。不同原因的零分分开解释；处理次数含重复与变体，不能算作独立任务。

E2实际21全文、15对；最新{cohort['E2']['posthoc_CCE']}/21完整CCE、{facts['E2_complete_CCE_pairs']}/15双端完整。顺序冲突和时长删除各3/3响应；纯编号漂移、合并敏感和步骤删除SR仅1/3下降仍是论文有效性问题。历史9个替代路线候选有7对完整数值（q21–23子批6对＋q248一对），专家确认0；字段修复子批的9份返回对应6对，不是总体9对。

E4为Qwen14/15实际返回、Codex12/12；直接分可算重复的25/25与19/25组极差均0，跨来源21/25组可比、3组均值不同。最新完整CCE分别{cohort['Qwen_repeats']['posthoc_CCE']}/14与{cohort['Codex']['posthoc_CCE']}/12，不能宣称科学准确性大幅提升。

新两生成模型同五题：时间{joint['metric_coverage']['s_time']}/10，标签{joint['metric_coverage']['s_label']}/10，完整CCE{joint['complete_CCE']}/10，共同完整题{joint['common_n']}/5（{joint['common_question_ids']}）。共同完整两题实际完成2000次同步任务抽样及4种穷举，全部五题的部分界另完成2000次抽样及3125种穷举；两者分母不同。来源家族因同题跨模型来源不一致尚未抽样（0行）。两模型Com/Cor方向相反支持小队列的条件性互不支配，不作全库排名。

台账全包388/394，本轮94/100；开发27、E2 21、E4 30、确认16。四小时新增33次（Qwen22、Codex11）；本窗口无Llama，较早3条仅存历史并排除当前验证。总计次余额6，但既定阶段上限只余开发3次；无在途或新计划请求，不自动重试，时间延期未增加调用上限。

仍待：具体标记关系/知识库和native量表含义、表示稳健性、来源适用性及独立确认；一位专家5＋15回传0/20；湿实验0观测。现有指标不因缺一项整份清零。

{local_link('详细设计、例子、排查与论文问题', DELIVERY / 'REPORT_v4_zh.md')} · {local_link('最终真实数值', READOUT / 'README_zh.md')} · {local_link('英文Methods/Results', DELIVERY / 'MANUSCRIPT_v4_EN.md')} · {local_link('当前索引', OUT / 'CURRENT_RESULTS_INDEX.md')}。

下一条恢复命令只检查已有交付与台账，不调用模型：

```powershell
Set-Location C:\\ClearEval\\ClearEval-public
& '{PYTHON}' -X utf8 scripts/cce_finalize_four_hour_delivery_v2.py --check
```

{local_link('此前入口逐文件存档', ARCHIVE / 'manifest.json')}。输入或配置未变的成功结果直接复用。
"""
    for path in (ROOT.parent / "STATUS.md", R2 / "STATUS.md", OUT / "STATUS.md"):
        write(path, status)
    index = "# 当前结果入口\n\n最终版本：" + stage + "。冻结、历史和后验版本分别保留。\n\n"
    links = [("中文实验设计、结果与未解决问题", DELIVERY / "REPORT_v4_zh.md"), ("英文Methods/Results及摘要", DELIVERY / "MANUSCRIPT_v4_EN.md"),
        ("当前逐组数值和15个受控配对", READOUT / "README_zh.md"), ("67份统一回放及具体来源修复", R2 / "posthoc_uniform_scoring_v4/README_zh.md"),
        ("最终E4真实重复及分母", R2 / "e4_cross_source_uniform_v4_v1/actual_execution_01/README_zh.md"),
        ("两生成器五题逐答案", R2 / "secondary_E5_posthoc_analysis_v1/actual_v4_01/per_answer.csv"),
        ("共同完整两题CCE三投影PDF", WINDOW / "figures_complete_joint_posthoc_v4/complete_cce_three_projections.pdf"),
        ("部分信息三投影PDF", WINDOW / "figures_partial_posthoc_v4/partial_cce_three_projections.pdf"),
        ("共同完整题集及重采样独立核验", DELIVERY / "E5_v4_independent_review.json"),
        ("独立部分信息复算", R2 / "partial_joint_identifiability_posthoc_v1/independent_review_v4/review.json"),
        ("v3至v4全部数值差异与来源实例", DELIVERY / "v4_difference_matrix_v1/revision02/README_zh.md"),
        ("最新逐答案问题及已恢复字段", DELIVERY / "final_blockers_by_answer_v4.md"),
        ("九个历史替代路线对图及全部分项", WINDOW / "figures_alternatives_v1/revision02/CAPTION_zh_en.md"),
        ("时间零分原公式诊断", WINDOW / "time_explanation_final_v3/README_zh.md"),
        ("既有产物盘点（v3快照）", DELIVERY / "ARTIFACT_INVENTORY_zh.md"),
        ("历史别名恢复", R2 / "legacy_alternative_alias_v1/README_zh.md"), ("一位专家5+15当前入口", OUT / "human_review/CURRENT_REVIEW_ENTRY.md"),
        ("湿实验计划状态", OUT / "wetlab/wetlab_status.json"), ("实际命令", OUT / "commands.md"),
        ("当前配置", OUT / "resolved_config_current.yaml"), ("剩余依赖", OUT / "remaining_dependencies.json"), ("完成度审计", OUT / "completion_audit_current.json")]
    index += "\n".join("- " + local_link(label, path) for label, path in links)
    write(OUT / "CURRENT_RESULTS_INDEX.md", index)
    write(OUT / "RESULTS_zh.md", "# ClearEval 当前中文结果\n\n" + local_link("完整报告：实验设计、真实结果、例子及未解决问题", DELIVERY / "REPORT_v4_zh.md") + "\n\n" +
          local_link("最终数值与逐对数据", READOUT / "README_zh.md") + f"。当前后验67份；新两模型五题完整CCE{joint['complete_CCE']}/10、Q*={joint['common_n']}/5。旧稿已逐字存档，未覆盖科学原结果。\n")
    write(OUT / "Methods_Results_en.md", "# Current supplementary Methods and Results\n\n" + local_link("Full English manuscript text and provisional abstract", DELIVERY / "MANUSCRIPT_v4_EN.md") + "\n\n" +
          f"Final uniform postprocessing: 67 returns; secondary two-generator cohort: {joint['complete_CCE']}/10 complete CCE, {joint['common_n']} common complete tasks. Frozen analyses and original returns remain separate.\n")
    command_sources = [R2 / "posthoc_uniform_scoring_v4/actual_execution_01/verification.json",
        R2 / "secondary_E5_posthoc_analysis_v1/actual_v4_01/verification.json", R2 / "partial_joint_identifiability_posthoc_v1/actual_v4_01/verification.json",
        R2 / "legacy_alternative_alias_v1/actual_01/verification.json", READOUT / "verification.json",
        WINDOW / "figures_partial_posthoc_v4/provenance.json",
        WINDOW / "figures_complete_joint_posthoc_v4/provenance.json",
        WINDOW / "time_explanation_final_v3/summary.json"]
    commands = "# 已实际执行的命令与恢复入口\n\n工作目录 `C:/ClearEval/ClearEval-public`。本页离线命令均有成功实际运行产物；不会再次调用评价器。原始模型请求的版本与终态保留在绑定文件中，勿因恢复而重启批次。\n\n"
    for source in command_sources:
        argv = read(source)["actual_command"]
        command = "& '" + argv[0] + "' -X utf8 " + " ".join(argv[1:])
        commands += local_link("实际运行记录", source) + "\n\n```powershell\n" + command + "\n```\n\n"
    commands += local_link("最终E4实际命令", R2 / "e4_cross_source_uniform_v4_v1/actual_execution_01/README_zh.md") + "\n\n"
    commands += local_link("本轮之前的实际命令档案", ARCHIVE / "ClearEval-public/artifacts/cce_validation/commands.md") + "\n\n"
    commands += "本轮交付更新与只读恢复检查（实际成功后记录于delivery manifest）：\n\n```powershell\n" + f"& '{PYTHON}' -X utf8 scripts/cce_finalize_four_hour_delivery_v2.py --publish\n& '{PYTHON}' -X utf8 scripts/cce_finalize_four_hour_delivery_v2.py --check\n```\n\n"
    commands += f"现有报告入口也已实际验证并转至同一当前publisher：`& '{PYTHON}' -X utf8 scripts/cce_report.py`。\n\n"
    commands += "评分输出使用新版本目录；已存在的成功产物按保存哈希复用。本命令页不把尚未运行的专家或湿实验分析写成已完成。\n"
    write(OUT / "commands.md", commands)
    manifest = {"generated_utc": now, "package_requests": 388, "round_requests": 94, "overall_goal_complete": False, "secondary_complete_CCE": facts["secondary_E5"]["complete_CCE"],
        "current_files": [binding(p) for p in current_paths], "scientific_inputs": [binding(p) for p in scientific_paths],
        "archive_manifest": binding(ARCHIVE / "manifest.json"), "publisher": binding(Path(__file__)),
        "dispatcher": binding(ROOT / "scripts/cce_report.py"),
        "actual_command": [str(PYTHON), "-X", "utf8", "scripts/cce_finalize_four_hour_delivery_v2.py", "--publish"],
        "new_model_requests": 0, "raw_answers_or_scores_overwritten": False}
    write(MANIFEST, manifest)
    return check_current()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--publish", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    main(publish=args.publish)
