
import json
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os

# 配置信息
INPUT_FILE = 'results/violin_data.json'  # 由 collect_violin_data.py 生成的输入文件
OUTPUT_DIR = 'results'                 # 输出目录

# 模型显示名称映射表
MODEL_NAME_MAP = {
    'openai_gpt-5.2-fast': 'GPT-5.2-Fast',
    'openai_gpt-5.2-thinking': 'GPT-5.2-Think',
    'gemini-3-flash': 'Gemini-3-Flash',
    'gemini-3-pro': 'Gemini-3-Pro',
    'openai_claude-sonnet-4.6': 'Claude-4.6-sonnet',
    'glm4.7-unthinking': 'GLM-4.7',
    'glm4.7-thinking': 'GLM-4.7-Think',
    'openai_deepseek-chat': 'DeepSeek-V3.2',
    'openai_deepseek-reasoner': 'DeepSeek-V3.2-Think',
    'openai_qwen3-max': 'Qwen3-Max',
    'openai_qwen3-235b': 'Qwen3-235B',
    'openai_qwen3-32b': 'Qwen3-32B',
    'openai_qwen3-14b': 'Qwen3-14B',
}

def set_nature_style():
    """
    设置 matplotlib 参数以模拟 Nature 期刊风格，针对单行出版布局进行了极大字号优化。
    """
    plt.rcParams['font.family'] = 'sans-serif'
    # 支持中英文显示的备选字体，首选 rival-sans
    plt.rcParams['font.sans-serif'] = ['rival-sans', 'Arial', 'Helvetica', 'DejaVu Sans', 'SimHei', 'Microsoft YaHei', 'SimSun']
    plt.rcParams['axes.unicode_minus'] = False 
    
    # 根据用户要求，设置巨大字体以满足高分辨率打印需求
    plt.rcParams['font.size'] = 26        # 基础字体
    plt.rcParams['axes.labelsize'] = 32   # 维度标签
    plt.rcParams['axes.titlesize'] = 44   # 图像标题
    plt.rcParams['xtick.labelsize'] = 26  # 刻度标签
    plt.rcParams['ytick.labelsize'] = 26  # 刻度标签
    plt.rcParams['legend.fontsize'] = 26  # 图例标签
    
    # 线条与边框加粗，配合大图
    plt.rcParams['axes.linewidth'] = 2.0
    plt.rcParams['grid.linewidth'] = 1.0
    plt.rcParams['lines.linewidth'] = 2.5
    
    # 分辨率提升至 600 DPI
    plt.rcParams['figure.dpi'] = 600
    plt.rcParams['savefig.dpi'] = 600
    
    # 去除顶部和右侧边框
    plt.rcParams['axes.spines.top'] = False
    plt.rcParams['axes.spines.right'] = False
    
    # 网格线配置
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.alpha'] = 0.15
    plt.rcParams['grid.linestyle'] = '--'

def remove_outliers(df, column, factor=1.5):
    """
    使用 IQR (四分位距) 方法剔除每个模型分组下的离群点。
    """
    df_cleaned = pd.DataFrame()
    if df.empty:
        return df
    removed_points = []
    for model in df['Model'].unique():
        subset = df[df['Model'] == model]
        if len(subset) < 4:
            df_cleaned = pd.concat([df_cleaned, subset])
            continue
        q1 = subset[column].quantile(0.25)
        q3 = subset[column].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        
        filtered = subset[(subset[column] >= lower_bound) & (subset[column] <= upper_bound)]
        outliers = subset[(subset[column] < lower_bound) | (subset[column] > upper_bound)]
        
        if not outliers.empty:
            removed_points.extend(outliers[column].tolist())
            
        df_cleaned = pd.concat([df_cleaned, filtered])
    
    if removed_points:
        print(f"列 {column} (factor={factor}) 剔除的点: {sorted(removed_points)}")
        
    return df_cleaned

def main():
    """
    主程序：加载数据，处理格式，生成优化后的合并小提琴图。
    """
    if not os.path.exists(INPUT_FILE):
        print(f"错误: 找不到输入文件 {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    
    # 将 JSON 数据展开为 DataFrame 格式
    rows = []
    available_model_ids = set()
    for model_id, samples in all_data.items():
        base_id = model_id.replace('_1-shot', '').replace('_0-shot', '')
        available_model_ids.add(base_id)
        
        if base_id in MODEL_NAME_MAP:
            model_display_name = MODEL_NAME_MAP[base_id]
        else:
            model_display_name = base_id.replace('openai_', '')
            
        for s in samples:
            rows.append({
                'Model': model_display_name,
                'Transparency Time (h)': s['total_transparency_time'],
                'Label Score (s_label)': s['s_label']
            })
    
    df = pd.DataFrame(rows)
    if df.empty:
        print("没有可供绘制的数据。")
        return
    
    # 动态过滤 MODEL_ORDER，只保留实际有数据的模型，并按映射表顺序排列
    MODEL_ORDER = [MODEL_NAME_MAP[mid] for mid in MODEL_NAME_MAP.keys() if mid in available_model_ids]
    
    # 确保只包含定义的模型
    df = df[df['Model'].isin(MODEL_ORDER)]
    
    if df.empty:
        print("警告: 过滤后没有模型匹配。请检查 MODEL_NAME_MAP 的键。")
        return

    set_nature_style()
    
    # 剔除离群点
    # 对透明时间使用更大的 factor (10.0)，以保留 0-200h 范围内的有效数据，仅剔除极端异常值
    df_time = remove_outliers(df, 'Transparency Time (h)', factor=10.0)
    # 对标记分数使用标准 factor (2.0)
    df_label = remove_outliers(df, 'Label Score (s_label)', factor=2.0)
    
    print(f"透明时间: 从 {len(df)} 个点中剔除了 {len(df) - len(df_time)} 个离群点。")
    print(f"标记分数: 从 {len(df)} 个点中剔除了 {len(df) - len(df_label)} 个离群点。")

    # 显著增大 figsize 以容纳巨大字体而不重叠 (例如 28x14)
    fig, axes = plt.subplots(1, 2, figsize=(28, 14))
    
    # 使用 husl 调色盘
    palette = sns.color_palette("husl", len(MODEL_ORDER))

    # 图表 1: 透明时间分布
    sns.violinplot(data=df_time, x='Model', y='Transparency Time (h)', order=MODEL_ORDER, 
                   hue='Model', legend=False, palette=palette, inner='box', linewidth=1.2, ax=axes[0], alpha=0.3)
    sns.stripplot(data=df_time, x='Model', y='Transparency Time (h)', order=MODEL_ORDER, 
                  size=4.0, color='.2', alpha=0.2, jitter=True, ax=axes[0])
    axes[0].set_title('Transparency Time\n(Fixation + Clearing)', fontweight='bold', pad=30)
    axes[0].set_ylabel('Time (Hours)', fontweight='bold', labelpad=25)
    axes[0].set_xlabel('')
    # 正确设置刻度和对齐
    axes[0].set_xticks(range(len(MODEL_ORDER)))
    axes[0].set_xticklabels(MODEL_ORDER, rotation=45, ha='right', rotation_mode='anchor')

    # 图表 2: 标记分数分布
    sns.violinplot(data=df_label, x='Model', y='Label Score (s_label)', order=MODEL_ORDER, 
                   hue='Model', legend=False, palette=palette, inner='box', linewidth=1.2, ax=axes[1], alpha=0.3)
    sns.stripplot(data=df_label, x='Model', y='Label Score (s_label)', order=MODEL_ORDER, 
                  size=4.0, color='.2', alpha=0.2, jitter=True, ax=axes[1])
    axes[1].set_title('Labeling Score (s_label)', fontweight='bold', pad=30)
    axes[1].set_ylabel('Score (0-6)', fontweight='bold', labelpad=25)
    axes[1].set_xlabel('')
    axes[1].set_xticks(range(len(MODEL_ORDER)))
    axes[1].set_xticklabels(MODEL_ORDER, rotation=45, ha='right', rotation_mode='anchor')

    # 紧凑布局并留出底部空间给倾斜标签
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    output_path = os.path.join(OUTPUT_DIR, 'combined_violin_plots.png')
    plt.savefig(output_path)
    plt.close()
    
    print(f"优化后的图表已保存至 {output_path}")

if __name__ == "__main__":
    main()
