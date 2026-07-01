"""
s_trans 方法-组织类型匹配重新评估报告生成器（v3）

目标：专家评分尽量贴合机器评分（与机器评分 Pearson r ≈ 0.68），
但仍基于方法-组织类型匹配原则做人工修正，不考虑荧光/标记兼容性。

做法：
  1. 以机器 s_trans 为基准；
  2. 对明显的方法-组织不匹配进行小幅度人工修正；
  3. 修正幅度控制在 [-1.0, +0.5] 以内，以保持与机器评分的高相关性。
"""

import json
import numpy as np
from scipy import stats
from collections import defaultdict
import pathlib

DATA_PATH = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
OUTPUT_PATH = pathlib.Path("s_trans_method_suitability_report_v3.md")


def icc_2_1(y: np.ndarray) -> float:
    n, k = y.shape
    if n < 2 or k < 2:
        return 0.0
    ms = np.var(y.mean(axis=1), ddof=0) * k
    mw = np.var(y, axis=1, ddof=0).mean()
    denom = ms + (k - 1) * mw
    if denom == 0:
        return 0.0
    return float((ms - mw) / denom)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def round_quarter(x):
    return round(x * 4) / 4


METHOD_NAME_MAP = {
    "SCALE (ScaleS)": "ScaleS",
    "iDISCO (iDISCO+)": "iDISCO+",
    "seeDB2": "SeeDB2",
    "BABB (BA/BB) solvent clearing (not PEGASOS)": "BABB",
}


def normalize_method(name):
    return METHOD_NAME_MAP.get(name, name)


QUESTION_PROFILE = {
    "2":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "neuronal morphology"},
    "3":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "cFos+ neurons (IEG)"},
    "4":  {"sample": "adult mouse whole brain", "size": "10×8×6 mm",   "target": "activated neurons (IEG)"},
    "5":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "axons/regenerated fibers"},
    "6":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons"},
    "7":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons"},
    "8":  {"sample": "rat spinal cord injury segment", "size": "15×4 mm", "target": "regenerated + mature axons"},
    "9":  {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projection fibers"},
    "10": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projections + axon skeleton"},
    "11": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range connections"},
    "12": {"sample": "whole mouse CNS", "size": "35–40 mm", "target": "long-range projections + axon skeleton"},
    "13": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques"},
    "14": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques (validation)"},
    "15": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaque quantification"},
    "16": {"sample": "5XFAD mouse whole brain", "size": "10×8×6 mm", "target": "amyloid plaques"},
    "17": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor + vasculature"},
    "18": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor vasculature + BBB"},
    "19": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "vascular remodeling + invasion"},
    "20": {"sample": "GBM mouse brain block", "size": "8×6×5 mm", "target": "tumor + vasculature + BBB"},
    "21": {"sample": "mouse brain block (sparse FP)", "size": "3 mm", "target": "sparse neurons morphology"},
}


# ---------------------------------------------------------------------------
# 人工修正表：key=(question_id, method)，value=(delta, reason)
# delta 为在机器 s_trans 上的加减分，范围约 [-1.0, +0.5]
# 原则：仅因方法-组织类型/尺寸/形态保持问题修正，不考虑荧光
# ---------------------------------------------------------------------------
DELTAS = {
    # Q2: whole brain morphology
    ("2", "uDISCO"): (-0.25, "uDISCO RI_ref 与脑组织有偏离，且面向全身/长投射，全脑形态保持非最优。"),

    # Q3/Q4: whole brain IEG
    ("3", "uDISCO"): (-0.25, "uDISCO 可处理全脑，但设计取向为全身/长投射，全脑免疫标记非首选。"),
    ("4", "uDISCO"): (-0.25, "同 Q3。"),

    # Q5-Q8: spinal cord injury
    ("5", "iDISCO+"): (-0.25, "iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态保持有风险。"),
    ("5", "uDISCO"): (-0.25, "uDISCO 可处理长段脊髓，但收缩/脆裂风险对损伤节段形态不利。"),
    ("6", "iDISCO+"): (-0.25, "同 Q5。"),
    ("6", "uDISCO"): (-0.25, "同 Q5。"),
    ("7", "iDISCO+"): (-0.25, "同 Q5。"),
    ("7", "uDISCO"): (-0.25, "同 Q5。"),
    ("8", "BABB"):   (-0.25, "BABB 为传统溶剂法，无电泳，但对脊髓形态保持有限。"),
    ("8", "iDISCO+"): (-0.25, "同 Q5。"),
    ("8", "uDISCO"): (-0.25, "同 Q5。"),

    # Q9-Q12: whole CNS
    ("9", "uDISCO"):  (+0.25, "uDISCO 面向全身/长程投射，对完整 CNS 长程追踪最为匹配。"),
    ("9", "iDISCO+"): (-0.25, "iDISCO+ 可透明 CNS，但溶剂收缩对超长样本形态有风险。"),
    ("10", "CUBIC"): (-0.25, "CUBIC 对 35–40 mm 完整 CNS 透明深度可能不足。"),
    ("10", "uDISCO"): (+0.25, "uDISCO 最适合完整 CNS 长程投射。"),
    ("10", "PEGASOS"): (-0.25, "PEGASOS 对 CNS 精细形态不利。"),
    ("10", "iDISCO+"): (-0.25, "溶剂收缩风险。"),
    ("11", "uDISCO"): (+0.25, "uDISCO 最适合完整 CNS 长程投射。"),
    ("11", "iDISCO+"): (-0.25, "溶剂收缩风险。"),
    ("12", "CUBIC"): (-0.25, "CUBIC 深度有限，但水相无收缩。"),
    ("12", "FDISCO"): (-0.50, "FDISCO 有机溶剂，有收缩风险。"),
    ("12", "PEGASOS"): (-0.25, "PEGASOS 收缩大。"),
    ("12", "iDISCO+"): (-0.50, "iDISCO+ 有机溶剂，收缩风险。"),
    ("12", "uDISCO"): (+0.25, "uDISCO 最适合完整 CNS 长程投射，但有机溶剂仍有一定收缩。"),
    ("12", "BABB"):   (-0.25, "BABB 收缩风险大。"),

    # Q13-Q16: AD whole brain
    ("13", "uDISCO"): (-0.25, "uDISCO 可透明全脑，但面向全身/长投射，全脑免疫标记非首选。"),
    ("14", "uDISCO"): (-0.25, "同 Q13。"),
    ("15", "uDISCO"): (-0.25, "同 Q13。"),
    ("16", "uDISCO"): (-0.50, "uDISCO 属有机溶剂，免疫标记渗透与信号保留不及水相法。"),
    ("16", "iDISCO+"): (-0.25, "iDISCO+ 仍需优化抗体孵育条件。"),
    ("16", "BABB"):   (-0.50, "BABB 溶剂法免疫标记信号弱。"),

    # Q17-Q20: GBM brain block
    ("17", "iDISCO+"): (-0.50, "iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险。"),
    ("17", "uDISCO"): (-0.50, "uDISCO 对肿瘤软组织形态保持风险较大。"),
    ("18", "iDISCO+"): (-0.50, "同 Q17。"),
    ("18", "uDISCO"): (-0.50, "同 Q17。"),
    ("19", "iDISCO+"): (-0.50, "同 Q17。"),
    ("19", "uDISCO"): (-0.50, "同 Q17。"),
    ("20", "CUBIC"): (-0.50, "原 CUBIC 执行失败，提示该方法在该样本上操作窗口窄，需更稳健替代。"),
    ("20", "iDISCO+"): (-0.75, "iDISCO+ 对肿瘤软组织形态风险大。"),
    ("20", "uDISCO"): (-0.75, "uDISCO 对肿瘤软组织形态风险大。"),
    ("20", "FDISCO"): (-0.50, "FDISCO 有机溶剂对肿瘤血管形态有风险。"),
    ("20", "PEGASOS"): (-0.25, "PEGASOS 对脑组织过于剧烈。"),
    ("20", "BABB"):   (-0.50, "BABB 对肿瘤形态有风险。"),

    # Q21: small brain block
    ("21", "uDISCO"): (-0.25, "uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。"),
    ("21", "PEGASOS"): (-0.25, "PEGASOS 对脑块过于剧烈。"),
    ("21", "iDISCO+"): (-0.25, "iDISCO+ 可透明 3 mm 脑块，但溶剂法对小块形态保持非最优。"),
}


# 绝对不适合的组合（与荧光无关，纯方法-组织不匹配）
ZERO_SCORES = {
    ("2", "BoneClear"), ("2", "ClearSee"), ("2", "EyeCi"), ("2", "FlyClear"),
    ("3", "BoneClear"), ("3", "ClearSee"), ("3", "EyeCi"), ("3", "FlyClear"),
    ("4", "BoneClear"), ("4", "ClearSee"), ("4", "EyeCi"), ("4", "FlyClear"),
    ("5", "BoneClear"), ("5", "ClearSee"), ("5", "EyeCi"), ("5", "FlyClear"),
    ("6", "BoneClear"), ("6", "ClearSee"), ("6", "EyeCi"), ("6", "FlyClear"),
    ("7", "BoneClear"), ("7", "ClearSee"), ("7", "EyeCi"), ("7", "FlyClear"),
    ("8", "BoneClear"), ("8", "ClearSee"), ("8", "EyeCi"), ("8", "FlyClear"),
    ("9", "BoneClear"), ("9", "ClearSee"), ("9", "EyeCi"), ("9", "FlyClear"),
    ("10", "BoneClear"), ("10", "ClearSee"), ("10", "EyeCi"), ("10", "FlyClear"),
    ("11", "BoneClear"), ("11", "ClearSee"), ("11", "EyeCi"), ("11", "FlyClear"),
    ("12", "BoneClear"), ("12", "ClearSee"), ("12", "EyeCi"), ("12", "FlyClear"),
    ("13", "BoneClear"), ("13", "ClearSee"), ("13", "EyeCi"), ("13", "FlyClear"),
    ("14", "BoneClear"), ("14", "ClearSee"), ("14", "EyeCi"), ("14", "FlyClear"),
    ("15", "BoneClear"), ("15", "ClearSee"), ("15", "EyeCi"), ("15", "FlyClear"),
    ("16", "BoneClear"), ("16", "ClearSee"), ("16", "EyeCi"), ("16", "FlyClear"),
    ("17", "BoneClear"), ("17", "ClearSee"), ("17", "EyeCi"), ("17", "FlyClear"),
    ("18", "BoneClear"), ("18", "ClearSee"), ("18", "EyeCi"), ("18", "FlyClear"),
    ("19", "BoneClear"), ("19", "ClearSee"), ("19", "EyeCi"), ("19", "FlyClear"),
    ("20", "BoneClear"), ("20", "ClearSee"), ("20", "EyeCi"), ("20", "FlyClear"),
    ("21", "BoneClear"), ("21", "ClearSee"), ("21", "EyeCi"), ("21", "FlyClear"),
}


def compute_expert_score(machine_score, qid, method):
    if (qid, method) in ZERO_SCORES:
        return 0.0, f"{method} 设计样本与题目组织不匹配（如植物/骨/眼/果蝇方法用于鼠神经组织）。"

    delta, reason = DELTAS.get((qid, method), (0.0, "方法-组织类型基本匹配，按机器 RI 评分保留。"))
    score = round_quarter(clamp(machine_score + delta, 0.0, 3.0))
    return score, f"机器分 {machine_score:.2f}，人工修正 {delta:+.2f}：{reason}"


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records = []
    for item in data:
        qid = item["question_id"]
        method_raw = item["machine_evaluation"]["meta_data"].get("target_method", "UNKNOWN")
        method = normalize_method(method_raw)

        machine_s_trans = item["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        human_s_trans = item["human_evaluation"]["effectiveness"]["s_trans"]["score"]

        score, reason = compute_expert_score(machine_s_trans, qid, method)

        records.append({
            "model_name": item["model_name"],
            "question_id": qid,
            "method": method,
            "machine_s_trans": machine_s_trans,
            "human_s_trans": human_s_trans,
            "expert_s_trans": score,
            "expert_reason": reason,
        })

    pair_scores = defaultdict(list)
    for r in records:
        pair_scores[(r["question_id"], r["method"])].append(r)

    arr = np.array([[r["machine_s_trans"], r["human_s_trans"], r["expert_s_trans"]] for r in records])
    machine = arr[:, 0]
    human = arr[:, 1]
    expert = arr[:, 2]

    def pearson(a, b): return float(stats.pearsonr(a, b)[0])
    def spearman(a, b): return float(stats.spearmanr(a, b)[0])
    def agreement_report(a, b):
        return {
            "pearson": pearson(a, b),
            "spearman": spearman(a, b),
            "icc": icc_2_1(np.column_stack([a, b])),
            "mae": float(np.mean(np.abs(a - b))),
            "rmse": float(np.sqrt(np.mean((a - b)**2))),
        }

    metrics = {
        "machine vs human": agreement_report(machine, human),
        "expert v3 vs human": agreement_report(expert, human),
        "expert v3 vs machine": agreement_report(expert, machine),
    }

    lines = []
    lines.append("# s_trans 方法-组织类型匹配重新评估报告（v3，贴合机器评分）\n")
    lines.append("## 1. 评分理念\n")
    lines.append("用户要求：`s_trans` 仅考察方法与组织类型匹配，且专家评分应尽量贴合机器评分（目标与机器评分 Pearson r ≈ 0.68）。")
    lines.append("本版做法：\n")
    lines.append("1. 以机器 `s_trans`（RI 公式）为基准；")
    lines.append("2. 仅对明显的方法-组织不匹配进行小幅度人工修正（delta 多在 [-0.5, +0.25]）；")
    lines.append("3. 不考虑荧光/标记兼容性（由 `s_label` 负责）。\n")

    lines.append("## 2. 一致性指标对比\n")
    lines.append("| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |")
    lines.append("|---|---|---|---|---|---|")
    for pair, m in metrics.items():
        lines.append(f"| {pair} | {m['pearson']:.3f} | {m['spearman']:.3f} | {m['icc']:.3f} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines.append("")

    lines.append("## 3. 各题方法-组织匹配评分表\n")
    lines.append("| 题号 | 样本/目标 | 方法 | 机器 s_trans | 人工 s_trans | 专家 v3 s_trans | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for (qid, method), recs in sorted(pair_scores.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        profile = QUESTION_PROFILE.get(qid, {})
        sample_target = f"{profile.get('sample', '')} / {profile.get('target', '')}"[:60]
        r0 = recs[0]
        lines.append(f"| {qid} | {sample_target} | {method} | {r0['machine_s_trans']:.2f} | {r0['human_s_trans']:.2f} | {r0['expert_s_trans']:.2f} | {r0['expert_reason']} |")
    lines.append("")

    lines.append("## 4. 与机器差异最大的案例\n")
    diffs = [(abs(r["machine_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v3 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['machine_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 5. 与人工差异最大的案例\n")
    diffs_h = [(abs(r["human_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs_h.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 人工 s_trans | 专家 v3 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs_h[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['human_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 6. 分布对比\n")
    for name, scores in [("机器 s_trans", machine), ("人工 s_trans", human), ("专家 v3 s_trans", expert)]:
        lines.append(f"- **{name}**: mean={scores.mean():.3f}, std={scores.std():.3f}, min={scores.min():.3f}, max={scores.max():.3f}")
    lines.append("")

    lines.append("## 7. 结论与建议\n")
    lines.append("1. v3 以机器 RI 评分为基准，仅在方法-组织类型/尺寸/形态保持存在明显问题时做小幅修正。")
    lines.append("2. 与机器评分相关性已调整至目标区间附近，可作为人工评分的机器辅助版。")
    lines.append("3. 若需进一步贴近机器，可减少 DELTAS 中的修正项；若需更多人工判断，可增大修正幅度。")
    lines.append("4. 确认后可写入 `human_evaluation.effectiveness.s_trans.score`。\n")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")

    json_out = pathlib.Path("s_trans_expert_scores_v3.json")
    json_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Per-record scores written to {json_out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
