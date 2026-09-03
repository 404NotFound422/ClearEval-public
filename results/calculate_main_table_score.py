import argparse
import json

"""
本脚本用于根据聚合后的数据计算 ClearEval 总结表格中的各项指标。
评分维度聚合逻辑：
1. Knowledge (MCQ) - Index I_K:
   - Tissue: Tissues & Markers (Tissue/Site) 和 (Marker/Target) 的平均值。
   - Reagent: Reagents (Name/Abbr) 和 (Func/App) 的平均值。
   - Method: 5 个方法相关细分维度的平均值。
   - I_K = (Tissue + Reagent + Method) / 3

2. Application (OEQ) - Index I_A:
   - Completeness: c_step 与 c_param 的 40/60 加权（Step Integrity 0.4, Param Detail 0.6，与论文 Table 一致）。
   - Correctness: co_order, co_method, co_param, co_chem 的平均值。
   - Effectiveness: s_method, s_label, s_trans, s_time 的平均值。
   - I_A = min(Completeness, Correctness, Effectiveness)  # 瓶颈/最弱环

3. Total Score:
   - Harmonic Mean: Score = 2 * I_K * I_A / (I_K + I_A)
"""

def load_mcq(filepath):
    """加载 MCQ 统计数据并聚合为三个板块。"""
    data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            model = item['model']
            stats = item['stats']
            tissue = (stats['Tissues & Markers (Tissue/Site)'] + stats['Tissues & Markers (Marker/Target)']) / 2
            reagent = (stats['Reagents (Name/Abbr)'] + stats['Reagents (Func/App)']) / 2
            method = (stats['Method (Name/Cat)'] + stats['Method (Char/App)'] + stats['Method (Selection)'] + stats['Method (Protocol/Param)'] + stats['Method (Full Design)']) / 5
            data[model] = {
                'Tissue': tissue * 100,
                'Reagent': reagent * 100,
                'Method': method * 100
            }
    return data

def load_oeq(filepath):
    """加载 OEQ 统计数据并聚合为三个板块。"""
    data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            model = item['model_name']
            scores = item['average_scores']
            
            # 聚合逻辑
            completeness = 0.4 * scores['c_step_norm'] + 0.6 * scores['c_param_norm']
            correctness = (scores['co_order_norm'] + scores['co_method_norm'] + scores['co_param_norm'] + scores['co_chem_norm']) / 4
            # Rescale signed method fit from [-1, 1] to [0, 1] before averaging.
            s_method_01 = (scores['s_method_norm'] + 1) / 2
            effectiveness = (s_method_01 + scores['s_label_norm'] + scores['s_trans_norm'] + scores['s_time_norm']) / 4
            
            data[model] = {
                'Completeness': completeness * 100,
                'Correctness': correctness * 100,
                'Effectiveness': effectiveness * 100
            }
    return data

def main(oeq_file='results/oeq_stats_260223.jsonl'):
    mcq_data = load_mcq('results/mcq_stats_20260222.jsonl')
    oeq_data = load_oeq(oeq_file)

    # 模型名称映射（内部名称到展示名称）
    model_mapping = {
        'GPT-5.2-Fast': 'openai_gpt-5.2-fast',
        'GPT-5.2-Thinking': 'openai_gpt-5.2-thinking',
        'Gemini-3-Flash': 'gemini-3-flash',
        'Gemini-3-Pro': 'gemini-3-pro',
        'Claude-4.6-sonnet': 'openai_claude-sonnet-4.6',
        'GLM-5': 'glm4.7-unthinking',
        'GLM-5-thinking': 'glm4.7-thinking',
        'DeepSeek-V3.2': 'openai_deepseek-chat',
        'DeepSeek-V3.2-thinking': 'openai_deepseek-reasoner',
        'Qwen3-max': 'openai_qwen3-max',
        'Qwen3-235B-A22B': 'openai_qwen3-235b',
        'Qwen3-32B': 'openai_qwen3-32b',
        'Qwen3-14B': 'openai_qwen3-14b'
    }

    print(f"{'模型名称':<25} | {'组织':<6} | {'试剂':<6} | {'方法':<6} | {'完整':<6} | {'准确':<6} | {'有效':<6} | {'总分':<6}")
    print("-" * 85)

    for display_name, internal_name in model_mapping.items():
        mcq = mcq_data.get(internal_name, {})
        oeq = oeq_data.get(internal_name, {})
        
        i_k_vals = [mcq.get('Tissue'), mcq.get('Reagent'), mcq.get('Method')]
        i_a_vals = [oeq.get('Completeness'), oeq.get('Correctness'), oeq.get('Effectiveness')]
        
        row = [display_name]
        row.extend([f"{v:>6.1f}" if v is not None else f"{'--':>6}" for v in i_k_vals])
        row.extend([f"{v:>6.1f}" if v is not None else f"{'--':>6}" for v in i_a_vals])
        
        if all(v is not None for v in i_k_vals) and all(v is not None for v in i_a_vals):
            i_k = sum(i_k_vals) / 3
            i_a = min(i_a_vals)  # Bottleneck (weakest-link) Application Index.
            if (i_k + i_a) > 0:
                total = 2 * i_k * i_a / (i_k + i_a)
                row.append(f"{total:>6.1f}")
            else:
                row.append(f"{0.0:>6.1f}")
        else:
            row.append(f"{'--':>6}")
            
        print(" | ".join(row))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate main table scores.")
    parser.add_argument("--oeq-file", default="results/oeq_stats_260223.jsonl", help="Path to OEQ stats JSONL")
    args = parser.parse_args()
    main(oeq_file=args.oeq_file)
