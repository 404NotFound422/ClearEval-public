import json
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, RegularPolygon
from matplotlib.path import Path
from matplotlib.projections.polar import PolarAxes
from matplotlib.projections import register_projection
from matplotlib.spines import Spine
from matplotlib.transforms import Affine2D

"""
本脚本用于绘制 MCQ 和 OEQ 基准测试结果的对比雷达图。
针对极端清晰度及 MICCAI 论文格式进行了最终终极优化：
1. 字体：统一使用 rival-sans 字体（如果不可用则回退至 Arial/DejaVu Sans）。
2. 巨型字体：标题 44，维度标签 32，图例/刻度 26。
3. 3行紧凑图例：将模型重新排列为 6 列 x 3 行，并垂直对齐公司。
4. 空间控制：增加画布尺寸至 26x20 英寸，通过 set_position 压缩子图高度并下移，确保标题和底部图例有充足显示空间。
"""


def radar_factory(num_vars, frame='circle'):
    theta = np.linspace(0, 2*np.pi, num_vars, endpoint=False)
    class RadarAxes(PolarAxes):
        name = 'radar'
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set_theta_offset(np.pi / 2)
        def fill(self, *args, closed=True, **kwargs):
            return super().fill(*args, closed=closed, **kwargs)
        def plot(self, *args, **kwargs):
            lines = super().plot(*args, **kwargs)
            for line in lines:
                self._close_line(line)
        def _close_line(self, line):
            x, y = line.get_data()
            if x[0] != x[-1]:
                x = np.concatenate((x, [x[0]]))
                y = np.concatenate((y, [y[0]]))
                line.set_data(x, y)
        def set_varlabels(self, labels):
            self.set_thetagrids(np.degrees(theta), labels)
        def _gen_axes_patch(self):
            if frame == 'circle':
                return Circle((0.5, 0.5), 0.5)
            elif frame == 'polygon':
                return RegularPolygon((0.5, 0.5), num_vars, radius=0.5, edgecolor="k")
            else:
                raise ValueError("Unknown value for 'frame': %s" % frame)
        def _gen_axes_spines(self):
            if frame == 'circle':
                return super()._gen_axes_spines()
            elif frame == 'polygon':
                spine = Spine(axes=self, spine_type='circle', path=Path.unit_regular_polygon(num_vars))
                spine.set_transform(Affine2D().scale(.5).translate(.5, .5) + self.transAxes)
                return {'polar': spine}
            else:
                raise ValueError("Unknown value for 'frame': %s" % frame)
    register_projection(RadarAxes)
    return theta

# ----------------------------------------------------------------------
# 数据加载与预处理 (Data Loading and Preprocessing)
# ----------------------------------------------------------------------
OEQ_STATS_FILE = 'results/oeq_stats_260223.jsonl'
MCQ_STATS_FILE = 'results/mcq_stats_20260222.jsonl'

OEQ_DIMENSIONS = [
    'Comp.\n(Step)', 'Comp.\n(Param)', 
    'Corr.\n(Order)', 'Corr.\n(Method)', 'Corr.\n(Param)', 'Corr.\n(Chem)',
    'Eff.\n(Trans.)', 'Eff.\n(Time)', 'Eff.\n(Label)', 'Eff.\n(Method)'
]

OEQ_MAPPING = {
    'Comp.\n(Step)': 'c_step_norm',
    'Comp.\n(Param)': 'c_param_norm',
    'Corr.\n(Order)': 'co_order_norm',
    'Corr.\n(Method)': 'co_method_norm',
    'Corr.\n(Param)': 'co_param_norm',
    'Corr.\n(Chem)': 'co_chem_norm',
    'Eff.\n(Trans.)': 's_trans_norm',
    'Eff.\n(Time)': 's_time_norm',
    'Eff.\n(Label)': 's_label_norm',
    'Eff.\n(Method)': 's_method_norm'
}

MCQ_LABEL_MAP = {
    "Tissues & Markers (Tissue/Site)": "Tis.\n(Site)",
    "Tissues & Markers (Marker/Target)": "Tis.\n(Target)",
    "Reagents (Name/Abbr)": "Reag.\n(Name)",
    "Reagents (Func/App)": "Reag.\n(Func.)",
    "Method (Name/Cat)": "Meth.\n(Cat.)",
    "Method (Char/App)": "Meth.\n(Char.)",
    "Method (Selection)": "Meth.\n(Select.)",
    "Method (Protocol/Param)": "Meth.\n(Param.)",
    "Method (Full Design)": "Meth.\n(Design)"
}

MODEL_NAME_MAP = {
    'openai_gpt-5.2-fast': 'GPT-5.2-Fast',
    'openai_gpt-5.2-thinking': 'GPT-5.2-Think',
    'gemini-3-flash': 'Gemini-3-Flash',
    'gemini-3-pro': 'Gemini-3-Pro',
    'openai_deepseek-chat': 'DeepSeek-Chat',
    'openai_deepseek-reasoner': 'DeepSeek-Think',
    'openai_qwen3-max': 'Qwen3-Max',
    'openai_qwen3-235b': 'Qwen3-235B',
    'openai_qwen3-32b': 'Qwen3-32B',
    'openai_qwen3-14b': 'Qwen3-14B',
    'openai_claude-sonnet-4.6': 'Claude-4.6-sonnet',
    'glm4.7-unthinking': 'GLM-4.7',
    'glm4.7-thinking': 'GLM-4.7-Think'
}

LEGEND_GRID = [
    ['GPT-5.2-Fast', 'Gemini-3-Flash', 'DeepSeek-Chat', 'Qwen3-Max', 'Qwen3-32B', 'Claude-4.6-sonnet'],
    ['GPT-5.2-Think', 'Gemini-3-Pro', 'DeepSeek-Think', 'Qwen3-235B', 'Qwen3-14B', 'GLM-4.7']
]

def clean_model_name(name):
    return MODEL_NAME_MAP.get(name, name)

def load_data():
    oeq_data = {}
    if os.path.exists(OEQ_STATS_FILE):
        with open(OEQ_STATS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                name = clean_model_name(item['model_name'])
                scores = []
                for dim in OEQ_DIMENSIONS:
                    key = OEQ_MAPPING[dim]
                    val = item['average_scores'].get(key, 0)
                    scores.append(val * 100)
                oeq_data[name] = scores

    mcq_data = {}
    mcq_labels_abbreviated = []
    if os.path.exists(MCQ_STATS_FILE):
        with open(MCQ_STATS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                name = clean_model_name(item['model'])
                raw_dims = list(item['stats'].keys())
                if not mcq_labels_abbreviated:
                    mcq_labels_abbreviated = [MCQ_LABEL_MAP.get(d, d) for d in raw_dims]
                
                scores = [item['stats'].get(d, 0) * 100 for d in raw_dims]
                mcq_data[name] = scores
    
    return oeq_data, OEQ_DIMENSIONS, mcq_data, mcq_labels_abbreviated

# ----------------------------------------------------------------------
# 绘图逻辑 (Plotting)
# ----------------------------------------------------------------------
def plot_combined():
    oeq_data, oeq_labels, mcq_data, mcq_labels = load_data()
    
    if not oeq_data or not mcq_data:
        print("错误: 数据不足，无法绘图。")
        return

    present_models = set(oeq_data.keys()) & set(mcq_data.keys())  # only models with both MCQ and OEQ (drops glm4.7-thinking)
    
    colors_cycle = plt.cm.tab20.colors
    color_map = {
        'GPT-5.2-Fast': colors_cycle[0], 'GPT-5.2-Think': colors_cycle[1],
        'Gemini-3-Flash': colors_cycle[2], 'Gemini-3-Pro': colors_cycle[3],
        'DeepSeek-Chat': colors_cycle[4], 'DeepSeek-Think': colors_cycle[5],
        'Qwen3-Max': colors_cycle[6], 'Qwen3-235B': colors_cycle[7],
        'Qwen3-32B': colors_cycle[8], 'Qwen3-14B': colors_cycle[9],
        'Claude-4.6-sonnet': colors_cycle[10],
        'GLM-4.7': colors_cycle[12], 'GLM-4.7-Think': colors_cycle[13]
    }

    plt.style.use('fast')
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['rival-sans', 'Arial', 'DejaVu Sans'],
        'font.size': 26,
        'axes.labelsize': 32,
        'axes.titlesize': 44,
        'legend.fontsize': 26,
        'grid.color': '#CCCCCC',
        'grid.linewidth': 1.5,
    })

    fig = plt.figure(figsize=(26, 20), dpi=300)

    # 子图 1: Knowledge Performance (MCQ)
    theta_mcq = radar_factory(len(mcq_labels), frame='polygon')
    ax1 = fig.add_subplot(1, 2, 1, projection='radar')
    ax1.set_title('Knowledge Performance', pad=140)
    ax1.set_varlabels(mcq_labels)
    ax1.set_rlim(0, 100)
    ax1.set_rticks([20, 40, 60, 80, 100])
    ax1.tick_params(pad=80, labelsize=26)
    
    ax1.set_position([0.08, 0.42, 0.38, 0.42])
    
    for row in LEGEND_GRID:
        for model in row:
            if model and model in mcq_data:
                ax1.plot(theta_mcq, mcq_data[model], color=color_map.get(model, 'gray'), linewidth=6, label=model)
                ax1.fill(theta_mcq, mcq_data[model], facecolor=color_map.get(model, 'gray'), alpha=0.05)

    # 子图 2: Application Performance (OEQ)
    theta_oeq = radar_factory(len(oeq_labels), frame='polygon')
    ax2 = fig.add_subplot(1, 2, 2, projection='radar')
    ax2.set_title('Application Performance', pad=140)
    ax2.set_varlabels(oeq_labels)
    ax2.set_rlim(0, 100)
    ax2.set_rticks([20, 40, 60, 80, 100])
    ax2.tick_params(pad=80, labelsize=26)
    
    ax2.set_position([0.54, 0.42, 0.38, 0.42])

    for row in LEGEND_GRID:
        for model in row:
            if model and model in oeq_data:
                ax2.plot(theta_oeq, oeq_data[model], color=color_map.get(model, 'gray'), linewidth=6, label=model)
                ax2.fill(theta_oeq, oeq_data[model], facecolor=color_map.get(model, 'gray'), alpha=0.05)

    ncol = len(LEGEND_GRID[0])
    handles_map = {h.get_label(): h for h in ax1.get_legend_handles_labels()[0]}
    
    final_handles = []
    final_labels = []
    for row in LEGEND_GRID:
        for model in row:
            if model and model in present_models:
                final_handles.append(handles_map[model])
                final_labels.append(model)
            else:
                final_handles.append(plt.Line2D([0], [0], color='none', label=''))
                final_labels.append('')

    fig.legend(final_handles, final_labels, loc='lower center', ncol=ncol, 
               bbox_to_anchor=(0.5, 0.12), frameon=False, columnspacing=1.2, handletextpad=0.5)

    output_path = 'results/combined_radar_chart.png'
    plt.savefig(output_path, facecolor='white', dpi=300, bbox_inches='tight')
    print(f"对比雷达图已保存至 {output_path}")

if __name__ == "__main__":
    plot_combined()
