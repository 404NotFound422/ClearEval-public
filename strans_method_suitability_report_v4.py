"""
s_trans 方法-组织类型匹配重新评估报告生成器（v4）

目标：专家评分既保留人工方法-组织判断，又与机器评分保持 Pearson r ≈ 0.68。
做法：
  1. 复用 v2 的专家判断分数（严格方法-组织匹配，不考虑荧光）；
  2. 与机器 s_trans 按权重 α 混合：expert_v4 = α * machine + (1-α) * expert_v2；
  3. 通过网格搜索确定 α，使 expert_v4 与 machine 的 Pearson r 最接近 0.68。
"""

import json
import numpy as np
from scipy import stats
from collections import defaultdict
import pathlib

DATA_PATH = pathlib.Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")
V2_JSON_PATH = pathlib.Path("s_trans_expert_scores_v2.json")
OUTPUT_PATH = pathlib.Path("s_trans_method_suitability_report_v4.md")


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


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    v2_records = { (r["model_name"], r["question_id"]): r for r in json.loads(V2_JSON_PATH.read_text(encoding="utf-8")) }

    records = []
    for item in data:
        qid = item["question_id"]
        model_name = item["model_name"]
        method = item["machine_evaluation"]["meta_data"].get("target_method", "UNKNOWN")
        machine = item["machine_evaluation"]["scores"]["effectiveness"]["s_trans"]["score"]
        human = item["human_evaluation"]["effectiveness"]["s_trans"]["score"]
        v2_rec = v2_records.get((model_name, qid))
        v2_score = v2_rec["expert_s_trans"] if v2_rec else machine
        v2_reason = v2_rec["expert_reason"] if v2_rec else ""
        records.append({
            "model_name": model_name,
            "question_id": qid,
            "method": method,
            "machine_s_trans": machine,
            "human_s_trans": human,
            "expert_v2_s_trans": v2_score,
            "expert_v2_reason": v2_reason,
        })

    machine_arr = np.array([r["machine_s_trans"] for r in records])
    v2_arr = np.array([r["expert_v2_s_trans"] for r in records])

    # search alpha
    best_alpha = None
    best_diff = float("inf")
    target_r = 0.68
    for alpha in np.arange(0.0, 1.01, 0.01):
        blended = alpha * machine_arr + (1 - alpha) * v2_arr
        r = stats.pearsonr(blended, machine_arr)[0]
        diff = abs(r - target_r)
        if diff < best_diff:
            best_diff = diff
            best_alpha = alpha

    alpha = best_alpha
    expert_v4 = alpha * machine_arr + (1 - alpha) * v2_arr
    expert_v4_rounded = np.array([round_quarter(clamp(x, 0.0, 3.0)) for x in expert_v4])

    for r, score in zip(records, expert_v4_rounded):
        r["expert_s_trans"] = float(score)

    human_arr = np.array([r["human_s_trans"] for r in records])

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
        "expert v4 vs human": agreement_report(expert_v4_rounded, human_arr),
        "expert v4 vs machine": agreement_report(expert_v4_rounded, machine_arr),
        "expert v2 vs machine": agreement_report(v2_arr, machine_arr),
    }

    pair_scores = defaultdict(list)
    for r in records:
        pair_scores[(r["question_id"], r["method"])].append(r)

    lines = []
    lines.append("# s_trans 方法-组织类型匹配重新评估报告（v4，目标 r≈0.68 贴合机器）\n")
    lines.append("## 1. 评分理念\n")
    lines.append("用户要求：专家评分应尽量贴合机器评分，Pearson r 目标约 0.68；同时仍基于方法-组织类型匹配，不考虑荧光/标记兼容性。")
    lines.append("本版做法：\n")
    lines.append("1. 以 v2 的专家判断（严格方法-组织匹配）为基础；")
    lines.append("2. 与机器 `s_trans` 线性混合：`expert_v4 = α * machine + (1-α) * expert_v2`；")
    lines.append(f"3. 通过网格搜索确定 **α = {alpha:.2f}**，使 expert_v4 与机器评分的 Pearson r 最接近 0.68。\n")

    lines.append("## 2. 一致性指标对比\n")
    lines.append("| 对比 | Pearson r | Spearman ρ | ICC(2,1) | MAE | RMSE |")
    lines.append("|---|---|---|---|---|---|")
    for pair, m in metrics.items():
        lines.append(f"| {pair} | {m['pearson']:.3f} | {m['spearman']:.3f} | {m['icc']:.3f} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines.append("")

    lines.append("## 3. 各题方法-组织匹配评分表\n")
    lines.append("| 题号 | 方法 | 机器 s_trans | 专家 v2 s_trans | 专家 v4 s_trans | 人工 s_trans | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for (qid, method), recs in sorted(pair_scores.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        r0 = recs[0]
        lines.append(f"| {qid} | {method} | {r0['machine_s_trans']:.2f} | {r0['expert_v2_s_trans']:.2f} | {r0['expert_s_trans']:.2f} | {r0['human_s_trans']:.2f} | {r0['expert_v2_reason']} |")
    lines.append("")

    lines.append("## 4. 与机器差异最大的案例\n")
    diffs = [(abs(r["machine_s_trans"] - r["expert_s_trans"]), r) for r in records]
    diffs.sort(key=lambda x: x[0], reverse=True)
    lines.append("| 模型 | 题号 | 方法 | 机器 s_trans | 专家 v4 s_trans | 差异 | 专家理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d, r in diffs[:20]:
        lines.append(f"| {r['model_name']} | {r['question_id']} | {r['method']} | {r['machine_s_trans']:.2f} | {r['expert_s_trans']:.2f} | {d:.2f} | {r['expert_v2_reason']} |")
    lines.append("")

    lines.append("## 5. 分布对比\n")
    for name, scores in [("机器 s_trans", machine_arr), ("专家 v2 s_trans", v2_arr), ("专家 v4 s_trans", expert_v4_rounded), ("人工 s_trans", human_arr)]:
        lines.append(f"- **{name}**: mean={scores.mean():.3f}, std={scores.std():.3f}, min={scores.min():.3f}, max={scores.max():.3f}")
    lines.append("")

    lines.append("## 6. 结论与建议\n")
    lines.append(f"1. v4 通过 α={alpha:.2f} 混合，使专家评分与机器评分 Pearson r 达到 {metrics['expert v4 vs machine']['pearson']:.3f}，接近目标 0.68。")
    lines.append("2. 混合后的分数既保留了人工方法-组织判断，又避免了与机器公式评分偏离过大。")
    lines.append("3. 若希望更依赖机器，可增大 α；若希望更多人工判断，可减小 α。")
    lines.append("4. 确认后可写入 `human_evaluation.effectiveness.s_trans.score`。\n")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")

    json_out = pathlib.Path("s_trans_expert_scores_v4.json")
    json_out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Per-record scores written to {json_out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
