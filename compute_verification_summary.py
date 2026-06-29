"""
计算 glm4.7-thinking 人工校验摘要。
"""
import pandas as pd

df = pd.read_csv("results/clearing_time_analysis/manual_verification_glm47.csv", encoding="utf-8-sig")

# 只统计脚本和人工都有数值的样本
valid = df.dropna(subset=["script_hours", "manual_hours"]).copy()
valid["diff_hours"] = (valid["script_hours"] - valid["manual_hours"]).abs()
valid["relative_diff_pct"] = valid["diff_hours"] / valid["manual_hours"] * 100

print("=" * 60)
print("glm4.7-thinking 人工校验摘要")
print("=" * 60)
print(f"校验样本数：{len(df)}")
print(f"双方都有数值的样本数：{len(valid)}")
print(f"平均绝对差异：{valid['diff_hours'].mean():.2f} h")
print(f"平均相对差异：{valid['relative_diff_pct'].mean():.1f}%")
print(f"差异在 ±10% 内的样本数：{(valid['relative_diff_pct'] <= 10).sum()}/{len(valid)}")
print(f"差异在 ±20% 内的样本数：{(valid['relative_diff_pct'] <= 20).sum()}/{len(valid)}")
print()
print("详细对比：")
print(valid[["question_id", "script_hours", "manual_hours", "diff_hours", "relative_diff_pct", "notes"]].to_string(index=False))

# 排除因分析+protocol重复导致离群的 54、78 号
filtered = valid[~valid["question_id"].isin([54, 78])]
print()
print("=" * 60)
print("排除分析/协议重复离群样本 (qid=54, 78) 后：")
print("=" * 60)
print(f"样本数：{len(filtered)}")
print(f"平均绝对差异：{filtered['diff_hours'].mean():.2f} h")
print(f"平均相对差异：{filtered['relative_diff_pct'].mean():.1f}%")
print(f"差异在 ±10% 内的样本数：{(filtered['relative_diff_pct'] <= 10).sum()}/{len(filtered)}")
