"""
分析 dataset/Q+AR/model_response/clearing_time_stats.json，
按模型和组织（tissue tier label）统计透明时间并生成图表。
"""
import json
import base64
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 设置中文字体（Windows 优先 SimHei / Microsoft YaHei）
for font_name in ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]:
    try:
        plt.rcParams["font.sans-serif"] = [font_name]
        plt.rcParams["axes.unicode_minus"] = False
        break
    except Exception:
        continue

# 路径配置
STATS_PATH = Path("dataset/Q+AR/model_response/clearing_time_stats.json")
QUESTIONS_PATH = Path("dataset/Q+AR/src/question_final.json")
OUTPUT_DIR = Path("results/clearing_time_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_tissue_mapping(questions_path):
    """读取 question_id -> tissue_label 映射。"""
    with open(questions_path, "r", encoding="utf-8") as f:
        questions = json.load(f)
    mapping = {}
    for q in questions:
        qid = q.get("question_id")
        th = q.get("tissue_hierarchy_from_tissue_xlsx", {})
        label = th.get("tissue_tier_label", "未知组织")
        mapping[qid] = label
    return mapping


def load_clearing_time_stats(stats_path):
    """读取 clearing_time_stats.json。"""
    with open(stats_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dataframe(stats, tissue_mapping):
    """构建包含模型、问题、组织、透明时长的 DataFrame。"""
    rows = []
    for model, qid_hours in stats.items():
        for qid_str, hours in qid_hours.items():
            qid = int(qid_str)
            tissue = tissue_mapping.get(qid, "未知组织")
            rows.append(
                {
                    "model": model,
                    "question_id": qid,
                    "tissue": tissue,
                    "clearing_time_hours": hours,
                }
            )
    df = pd.DataFrame(rows)
    # 仅保留成功提取到时间的记录用于统计
    df_valid = df.dropna(subset=["clearing_time_hours"]).copy()
    df_valid["clearing_time_hours"] = df_valid["clearing_time_hours"].astype(float)
    return df, df_valid


def summarize_by_model(df_valid):
    """按模型汇总统计量。"""
    summary = (
        df_valid.groupby("model")["clearing_time_hours"]
        .agg(["count", "mean", "median", "min", "max", "std"])
        .reset_index()
    )
    summary = summary.sort_values("mean", ascending=False)
    summary.columns = [
        "模型",
        "样本数",
        "平均透明时间(h)",
        "中位数(h)",
        "最小值(h)",
        "最大值(h)",
        "标准差(h)",
    ]
    return summary


def summarize_by_tissue(df_valid):
    """按组织汇总统计量。"""
    summary = (
        df_valid.groupby("tissue")["clearing_time_hours"]
        .agg(["count", "mean", "median", "min", "max", "std"])
        .reset_index()
    )
    summary = summary.sort_values("mean", ascending=False)
    summary.columns = [
        "组织",
        "样本数",
        "平均透明时间(h)",
        "中位数(h)",
        "最小值(h)",
        "最大值(h)",
        "标准差(h)",
    ]
    return summary


def summarize_by_model_tissue(df_valid):
    """按模型 x 组织透视平均透明时间。"""
    pivot = df_valid.pivot_table(
        index="tissue",
        columns="model",
        values="clearing_time_hours",
        aggfunc="mean",
    )
    return pivot


def plot_model_box(df_valid, output_dir):
    """箱线图：每个模型的透明时间分布。"""
    plt.figure(figsize=(14, 7))
    order = (
        df_valid.groupby("model")["clearing_time_hours"]
        .median()
        .sort_values(ascending=False)
        .index
    )
    sns.boxplot(
        data=df_valid,
        x="model",
        y="clearing_time_hours",
        order=order,
        palette="Set2",
        showfliers=True,
    )
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("模型", fontsize=12)
    plt.ylabel("透明时间（小时）", fontsize=12)
    plt.title("各模型透明时间分布（箱线图）", fontsize=14)
    plt.tight_layout()
    path = output_dir / "model_boxplot.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def plot_model_bar(summary_model, output_dir):
    """柱状图：每个模型的平均透明时间。"""
    plt.figure(figsize=(12, 6))
    sns.barplot(
        data=summary_model,
        x="模型",
        y="平均透明时间(h)",
        palette="viridis",
        order=summary_model["模型"],
    )
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("模型", fontsize=12)
    plt.ylabel("平均透明时间（小时）", fontsize=12)
    plt.title("各模型平均透明时间对比", fontsize=14)
    plt.tight_layout()
    path = output_dir / "model_avg_bar.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def plot_tissue_bar(summary_tissue, output_dir):
    """柱状图：每个组织的平均透明时间。"""
    plt.figure(figsize=(12, 6))
    sns.barplot(
        data=summary_tissue,
        x="组织",
        y="平均透明时间(h)",
        palette="magma",
        order=summary_tissue["组织"],
    )
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("组织", fontsize=12)
    plt.ylabel("平均透明时间（小时）", fontsize=12)
    plt.title("各组织平均透明时间对比", fontsize=14)
    plt.tight_layout()
    path = output_dir / "tissue_avg_bar.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def plot_heatmap(pivot, output_dir):
    """热力图：模型 x 组织平均透明时间。"""
    plt.figure(figsize=(max(14, len(pivot.columns) * 0.8), max(10, len(pivot) * 0.6)))
    # 对行和列按均值排序，便于观察模式
    row_order = pivot.mean(axis=1).sort_values(ascending=False).index
    col_order = pivot.mean(axis=0).sort_values(ascending=False).index
    pivot_sorted = pivot.loc[row_order, col_order]
    sns.heatmap(
        pivot_sorted,
        annot=True,
        fmt=".1f",
        cmap="YlOrRd",
        linewidths=0.5,
        cbar_kws={"label": "平均透明时间（小时）"},
    )
    plt.xlabel("模型", fontsize=12)
    plt.ylabel("组织", fontsize=12)
    plt.title("各模型在不同组织上的平均透明时间热力图", fontsize=14)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    path = output_dir / "model_tissue_heatmap.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def plot_tissue_box(df_valid, output_dir):
    """箱线图：每个组织的透明时间分布。"""
    plt.figure(figsize=(14, 7))
    order = (
        df_valid.groupby("tissue")["clearing_time_hours"]
        .median()
        .sort_values(ascending=False)
        .index
    )
    sns.boxplot(
        data=df_valid,
        x="tissue",
        y="clearing_time_hours",
        order=order,
        palette="Set3",
        showfliers=True,
    )
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("组织", fontsize=12)
    plt.ylabel("透明时间（小时）", fontsize=12)
    plt.title("各组织透明时间分布（箱线图）", fontsize=14)
    plt.tight_layout()
    path = output_dir / "tissue_boxplot.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def plot_missing_rate(df, output_dir):
    """各模型透明时间提取缺失率。"""
    missing = (
        df.groupby("model")
        .apply(lambda x: x["clearing_time_hours"].isna().sum() / len(x) * 100, include_groups=False)
        .reset_index(name="missing_rate")
    )
    missing = missing.sort_values("missing_rate", ascending=False)
    plt.figure(figsize=(12, 6))
    sns.barplot(data=missing, x="model", y="missing_rate", palette="Reds_r")
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("模型", fontsize=12)
    plt.ylabel("缺失率（%）", fontsize=12)
    plt.title("各模型透明时间提取缺失率", fontsize=14)
    plt.tight_layout()
    path = output_dir / "missing_rate.png"
    plt.savefig(path, dpi=300)
    plt.close()
    return path


def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def generate_html_report(output_dir, summary_model, summary_tissue, chart_paths, df, df_valid):
    """生成一个包含所有汇总表和图表的 HTML 报告。"""
    total = len(df)
    valid = len(df_valid)
    missing_rate = (total - valid) / total * 100 if total else 0

    model_table = summary_model.to_html(index=False, classes="table", border=0)
    tissue_table = summary_tissue.to_html(index=False, classes="table", border=0)

    chart_sections = []
    titles = {
        "model_boxplot.png": "各模型透明时间分布（箱线图）",
        "model_avg_bar.png": "各模型平均透明时间对比",
        "tissue_avg_bar.png": "各组织平均透明时间对比",
        "model_tissue_heatmap.png": "各模型在不同组织上的平均透明时间热力图",
        "tissue_boxplot.png": "各组织透明时间分布（箱线图）",
        "missing_rate.png": "各模型透明时间提取缺失率",
    }
    for p in chart_paths:
        name = p.name
        title = titles.get(name, name)
        b64 = img_to_base64(p)
        chart_sections.append(
            f"<h2>{title}</h2>\n<img src=\"data:image/png;base64,{b64}\" alt=\"{title}\" />\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>透明时间统计分析报告</title>
    <style>
        body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; margin: 40px; color: #333; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; margin-top: 40px; border-bottom: 2px solid #ecf0f1; padding-bottom: 8px; }}
        .summary {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0; }}
        .table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        .table th, .table td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
        .table th {{ background: #3498db; color: white; text-align: center; }}
        .table tr:nth-child(even) {{ background: #f2f2f2; }}
        img {{ max-width: 100%; height: auto; border: 1px solid #ddd; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <h1>透明时间统计分析报告</h1>
    <div class="summary">
        <p><strong>总记录数：</strong>{total}</p>
        <p><strong>成功提取透明时间记录数：</strong>{valid}</p>
        <p><strong>缺失率：</strong>{missing_rate:.2f}%</p>
        <p><strong>模型数：</strong>{df['model'].nunique()}</p>
        <p><strong>组织类别数：</strong>{df['tissue'].nunique()}</p>
    </div>

    <h2>按模型汇总</h2>
    {model_table}

    <h2>按组织汇总</h2>
    {tissue_table}

    {"\n".join(chart_sections)}
</body>
</html>
"""
    report_path = output_dir / "clearing_time_report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path


def main():
    print("=" * 80)
    print("透明时间统计分析")
    print("=" * 80)

    stats = load_clearing_time_stats(STATS_PATH)
    tissue_mapping = load_tissue_mapping(QUESTIONS_PATH)
    df, df_valid = build_dataframe(stats, tissue_mapping)

    print(f"总记录数：{len(df)}")
    print(f"成功提取透明时间的记录数：{len(df_valid)}")
    print(f"缺失率：{(len(df) - len(df_valid)) / len(df) * 100:.2f}%")
    print(f"模型数：{df['model'].nunique()}")
    print(f"组织类别数：{df['tissue'].nunique()}")
    print()

    # 汇总表
    summary_model = summarize_by_model(df_valid)
    summary_tissue = summarize_by_tissue(df_valid)
    pivot = summarize_by_model_tissue(df_valid)

    # 保存 CSV
    summary_model.to_csv(OUTPUT_DIR / "summary_by_model.csv", index=False, encoding="utf-8-sig")
    summary_tissue.to_csv(OUTPUT_DIR / "summary_by_tissue.csv", index=False, encoding="utf-8-sig")
    pivot.to_csv(OUTPUT_DIR / "mean_hours_model_tissue.csv", encoding="utf-8-sig")

    # 保存 JSON
    with open(OUTPUT_DIR / "summary_by_model.json", "w", encoding="utf-8") as f:
        json.dump(summary_model.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "summary_by_tissue.json", "w", encoding="utf-8") as f:
        json.dump(summary_tissue.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

    print("【按模型汇总】")
    print(summary_model.to_string(index=False))
    print()

    print("【按组织汇总】")
    print(summary_tissue.to_string(index=False))
    print()

    # 绘图
    print("正在生成图表...")
    paths = []
    paths.append(plot_model_box(df_valid, OUTPUT_DIR))
    paths.append(plot_model_bar(summary_model, OUTPUT_DIR))
    paths.append(plot_tissue_bar(summary_tissue, OUTPUT_DIR))
    paths.append(plot_heatmap(pivot, OUTPUT_DIR))
    paths.append(plot_tissue_box(df_valid, OUTPUT_DIR))
    paths.append(plot_missing_rate(df, OUTPUT_DIR))

    print("图表已保存到：")
    for p in paths:
        print(f"  - {p}")

    # HTML 报告
    report_path = generate_html_report(
        OUTPUT_DIR, summary_model, summary_tissue, paths, df, df_valid
    )
    print(f"\nHTML 报告已保存到：{report_path}")

    print()
    print(f"所有结果已保存到目录：{OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
