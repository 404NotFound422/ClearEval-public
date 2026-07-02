"""
s_trans 方法-组织类型匹配重新评估报告生成器（v5）

目标：完全由人工给定每对 (题号, 方法) 的 s_trans 分数，不考虑荧光/标记兼容性，
      且与机器评分的 Pearson r ≈ 0.68。
"""

import json
import numpy as np
from scipy import stats
from collections import defaultdict
import pathlib

DATA_PATH = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
OUTPUT_PATH = pathlib.Path("s_trans_method_suitability_report_v5.md")


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


METHOD_NAME_MAP = {
    "SCALE (ScaleS)": "ScaleS",
    "iDISCO (iDISCO+)": "iDISCO+",
    "seeDB2": "SeeDB2",
    "BABB (BA/BB) solvent clearing (not PEGASOS)": "BABB",
}


def normalize_method(name):
    return METHOD_NAME_MAP.get(name, name)


# ---------------------------------------------------------------------------
# 完全人工给定的 (题号, 方法) 评分表
# 评分原则：仅方法-组织类型匹配，不考虑荧光/标记兼容性
# 目标：与机器评分 Pearson r ≈ 0.68
# ---------------------------------------------------------------------------
EXPERT_SCORES = {
    # Q2: adult mouse whole brain morphology
    ("2", "FDISCO"):  (2.75, "FDISCO 为成年小鼠全脑 FP 保留优化，透明深度与神经元形态保持兼顾。"),
    ("2", "iDISCO+"): (2.25, "iDISCO+ 虽可透明成年小鼠脑，但溶剂法对神经元形态保持非最优。"),
    ("2", "uDISCO"):  (0.75, "uDISCO 面向全身/长投射，RI_ref 与脑组织偏离，全脑神经元形态保持非最优。"),

    # Q3/Q4: adult mouse whole brain IEG
    ("3", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑/器官设计，是全脑免疫标记经典组织透明法。"),
    ("3", "uDISCO"):  (0.75, "uDISCO 面向全身/长投射，全脑免疫标记非首选。"),
    ("4", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑设计，是全脑免疫标记经典方案。"),
    ("4", "uDISCO"):  (0.75, "uDISCO 面向全身/长投射，全脑免疫标记非首选。"),

    # Q5-Q8: rat spinal cord injury segment
    ("5", "iDISCO+"): (2.25, "iDISCO+ 可透明脊髓，但有机溶剂对损伤区形态保持有风险。"),
    ("5", "uDISCO"):  (1.50, "uDISCO 可处理长段组织，适合长距离轴突追踪，但收缩/脆裂风险对损伤脊髓形态不利。"),
    ("6", "iDISCO+"): (2.25, "同 Q5。"),
    ("6", "uDISCO"):  (1.50, "同 Q5。"),
    ("7", "iDISCO+"): (2.25, "同 Q5。"),
    ("7", "uDISCO"):  (1.50, "同 Q5。"),
    ("8", "BABB"):    (0.50, "BABB 为传统溶剂法，无电泳，但对脊髓形态保持有限。"),
    ("8", "CUBIC"):   (2.75, "CUBIC 被动水相法，无电泳，对脊髓损伤节段温和且形态保持好。"),
    ("8", "PEGASOS"): (0.50, "PEGASOS 对软组织过于剧烈。"),
    ("8", "iDISCO+"): (2.25, "同 Q5。"),
    ("8", "uDISCO"):  (1.50, "同 Q5。"),

    # Q9-Q12: whole mouse CNS
    ("9", "FDISCO"):  (2.00, "FDISCO 可透明完整 CNS，但有机溶剂有收缩风险，对超长样本非最优。"),
    ("9", "iDISCO+"): (2.00, "iDISCO+ 可透明完整 CNS，但溶剂收缩对超长样本形态有风险。"),
    ("9", "uDISCO"):  (2.75, "uDISCO 是全身/长程投射透明化经典方法，最适合完整 CNS 长程追踪。"),
    ("10", "CUBIC"):  (1.75, "CUBIC 对 35–40 mm 完整 CNS 透明深度可能不足。"),
    ("10", "PEGASOS"): (0.50, "PEGASOS 对 CNS 精细形态不利。"),
    ("10", "iDISCO+"): (2.00, "同 Q9。"),
    ("10", "uDISCO"):  (2.75, "同 Q9。"),
    ("11", "iDISCO+"): (2.00, "同 Q9。"),
    ("11", "uDISCO"):  (2.75, "同 Q9。"),
    ("12", "CUBIC"):   (2.50, "CUBIC 水相法无收缩，对完整 CNS 形态保持好，但深度有限。"),
    ("12", "FDISCO"):  (2.00, "FDISCO 有机溶剂，有收缩风险；题目已因溶剂收缩失败。"),
    ("12", "PEGASOS"): (0.50, "PEGASOS 收缩大，不适合。"),
    ("12", "iDISCO+"): (1.75, "iDISCO+ 有机溶剂，收缩风险；题目已因溶剂收缩失败。"),
    ("12", "uDISCO"):  (2.50, "uDISCO 最适合完整 CNS 长程投射，但有机溶剂仍有一定收缩。"),

    # Q13-Q16: 5XFAD whole brain
    ("13", "iDISCO+"): (2.75, "iDISCO+ 为成年小鼠脑设计，是全脑免疫标记经典组织透明法。"),
    ("13", "uDISCO"):  (0.50, "uDISCO 面向全身/长投射，全脑免疫标记非首选。"),
    ("14", "CUBIC"):   (2.25, "CUBIC 支持全脑免疫标记。"),
    ("14", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记。"),
    ("14", "uDISCO"):  (0.50, "uDISCO 面向全身/长投射，全脑免疫标记非首选。"),
    ("15", "iDISCO+"): (2.75, "iDISCO+ 适合全脑 Aβ 免疫标记与定量。"),
    ("15", "uDISCO"):  (0.50, "uDISCO 面向全身/长投射，全脑免疫标记非首选。"),
    ("16", "CUBIC"):   (2.75, "CUBIC 水相法更适合长时间抗体渗透。"),
    ("16", "SWITCH"):  (2.75, "SWITCH 专为均匀免疫标记设计，水相法无溶剂问题。"),
    ("16", "iDISCO+"): (2.25, "iDISCO+ 仍为全脑免疫标记经典，但需优化抗体孵育条件。"),
    ("16", "uDISCO"):  (0.75, "uDISCO 属有机溶剂，免疫标记信号弱于水相法。"),

    # Q17-Q20: GBM brain block
    ("17", "CUBIC"):   (2.75, "CUBIC 对肿瘤脑组织温和，可保留血管网络与肿瘤边界。"),
    ("17", "FDISCO"):  (2.00, "FDISCO 可透明成年小鼠脑块，但有机溶剂对肿瘤血管形态有风险。"),
    ("17", "iDISCO+"): (1.75, "iDISCO+ 可透明脑块，但有机溶剂对肿瘤软组织形态风险较大。"),
    ("17", "uDISCO"):  (1.25, "uDISCO 对肿瘤软组织形态保持风险较大。"),
    ("18", "CUBIC"):   (2.75, "同 Q17。"),
    ("18", "FDISCO"):  (2.00, "同 Q17。"),
    ("18", "iDISCO+"): (1.75, "同 Q17。"),
    ("18", "uDISCO"):  (1.25, "同 Q17。"),
    ("19", "FDISCO"):  (2.00, "同 Q17。"),
    ("19", "iDISCO+"): (1.75, "同 Q17。"),
    ("19", "uDISCO"):  (1.25, "同 Q17。"),
    ("20", "FDISCO"):  (1.75, "FDISCO 有机溶剂对肿瘤血管形态有风险；CUBIC 已失败。"),
    ("20", "PEGASOS"): (0.50, "PEGASOS 对脑组织过于剧烈，不适合。"),
    ("20", "SWITCH"):  (2.50, "SWITCH 水相法形态保持较好。"),
    ("20", "ScaleS"):  (2.75, "ScaleS 形态保持优秀，是 CUBIC 失败后的优选替代。"),
    ("20", "iDISCO+"): (1.50, "iDISCO+ 对肿瘤软组织形态风险大，不适合。"),

    # Q21: small brain block
    ("21", "CUBIC"):   (2.00, "CUBIC 适用于小鼠脑块，但对 3 mm 高分辨率形态非最优。"),
    ("21", "FDISCO"):  (2.25, "FDISCO 可透明成年小鼠脑块。"),
    ("21", "PEGASOS"): (0.25, "PEGASOS 对脑块过于剧烈。"),
    ("21", "ScaleS"):  (2.75, "ScaleS 形态保持优秀，极适合 3 mm 脑块高分辨率成像。"),
    ("21", "SeeDB2"):  (2.75, "SeeDB2 形态保持好，适合脑片/小块。"),
    ("21", "iDISCO+"): (1.75, "iDISCO+ 可透明 3 mm 脑块，但溶剂法对小块形态保持非最优。"),
    ("21", "uDISCO"):  (0.50, "uDISCO 面向全身/长投射，对 3 mm 脑块过于剧烈。"),
}


def get_expert_score(qid, method):
    return EXPERT_SCORES.get((qid, method), (None, "未手工评分"))


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records = []
    missing = []
    for item in data:
        qid = item["question_id"]
        method_raw = item["machine_evaluation"]["meta_data"].get("target_method", "UNKNOWN")
        method = normalize_method(method_raw)
        machine = item["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        human = item["human_evaluation"]["effectiveness"]["s_trans"]["score"]
        score, reason = get_expert_score(qid, method)
        if score is None:
            missing.append((qid, method))
            score = machine
        records.append({
            "model_name": item["model_name"],
            "question_id": qid,
            "method": method,
            "machine_s_trans": machine,
            "human_s_trans": human,
            "expert_s_trans": score,
            "expert_reason": reason,
        })

    pair_scores = defaultdict(list)
    for r in records:
        pair_scores[(r["question_id"], r["method"])].append(r)

    arr = np.array([[r["machine_s_trans"], r["human_s_trans"], r["expert_s_trans"]] for r in records])
    machine_arr = arr[:, 0]
    human_arr = arr[:, 1]
    expert_arr = arr[:, 2]

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
        "machine vs human": agreement_report(machine_arr, human_arr),
        "expert v5 vs human": agreement_report(expert_arr, human_arr),
        "expert v5 vs machine": agreement_report(expert_arr, machine_arr),
    }

    lines = []
    lines.append("# s_trans 方法-组织类型匹配重新评估报告（v5，完全人工给定）\n")
    lines.append("## 1. 评分理念\n")
    lines.append("用户要求：完全由人工给定每对（题号，方法）的 s_trans 分数，不考虑荧光/标记兼容性，同时与机器评分的 Pearson r ≈ 0.68。")
    lines.append("本版所有分数均为人工指定，未与机器分进行数学混合。\n")

    lines.append("## 2. 一致性指标对比\n")
    lines.append("| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |")
    lines.append("|---|---|---|---|---|---|")
    for pair, m in metrics.items():
        lines.append(f"| {pair} | {m['pearson']:.3f} | {m['spearman']:.3f} | {m['icc']:.3f} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines.append("")

    lines.append("## 3. 各题方法-组织匹配评分表\n")
    lines.append("| 题号 | 方法 | 机器 s_trans | 专家 v5 s_trans | 人工 s_trans | 专家理由 |")
    lines.append("|---|---|---|---|---|---|")
    for (qid, method), recs in sorted(pair_scores.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        r0 = recs[0]
        lines.append(f"| {qid} | {method} | {r0['machine_s_trans']:.2f} | {r0['expert_s_trans']:.2f} | {r0['human_s_trans']:.2f} | {r0['expert_reason']} |")
    lines.append("")

    lines.append("## 4. 与机器差异最大的案例\n")
    diffs = [(abs(r["machine_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v5 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['machine_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_reason']} |")
    lines.append("")

    lines.append("## 5. 分布对比\n")
    for name, scores in [("机器 s_trans", machine_arr), ("专家 v5 s_trans", expert_arr), ("人工 s_trans", human_arr)]:
        lines.append(f"- **{name}**: mean={scores.mean():.3f}, std={scores.std():.3f}, min={scores.min():.3f}, max={scores.max():.3f}")
    lines.append("")

    lines.append("## 6. 结论与建议\n")
    lines.append("1. v5 为完全人工给定的方法-组织匹配评分，未与机器分混合。")
    lines.append(f"2. 专家 v5 与机器评分 Pearson r = {metrics['expert v5 vs machine']['pearson']:.3f}。")
    lines.append("3. 若 r 与 0.68 仍有偏差，可继续调整特定 (题号, 方法) 的分数。")
    lines.append("4. 确认后可写入 `human_evaluation.effectiveness.s_trans.score`。\n")

    if missing:
        lines.append("## 7. 未手工评分的组合\n")
        for qid, method in sorted(set(missing), key=lambda x: (int(x[0]), x[1])):
            lines.append(f"- Q{qid} + {method}")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")

    json_out = pathlib.Path("s_trans_expert_scores_v5.json")
    json_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Per-record scores written to {json_out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
