import json

"""
本脚本用于将 ClearEval 的聚合结果格式化为 LaTeX 表格行。
计算逻辑：
1. Knowledge (I_K): Tissue, Reagent, Method 的平均值。
2. Application (I_A): Completeness, Correctness, Effectiveness 的平均值。
3. Total: 2 * I_K * I_A / (I_K + I_A) (调和平均数)。
"""

def load_mcq(filepath):
    """加载 MCQ 统计数据并聚合为三个板块。"""
    data = {}
    try:
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
    except Exception as e:
        print(f"Error loading MCQ: {e}")
    return data

def load_oeq(filepath):
    """加载 OEQ 统计数据并聚合为三个板块。"""
    data = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                model = item['model_name']
                scores = item['average_scores']
                
                # 聚合逻辑
                completeness = (scores['c_step_norm'] + scores['c_param_norm']) / 2
                correctness = (scores['co_order_norm'] + scores['co_method_norm'] + scores['co_param_norm'] + scores['co_chem_norm']) / 4
                effectiveness = (scores['s_method_norm'] + scores['s_label_norm'] + scores['s_trans_norm'] + scores['s_time_norm']) / 4
                
                data[model] = {
                    'Completeness': completeness * 100,
                    'Correctness': correctness * 100,
                    'Effectiveness': effectiveness * 100
                }
    except Exception as e:
        print(f"Error loading OEQ: {e}")
    return data

def main():
    mcq_data = load_mcq('results/mcq_stats_20260222.jsonl')
    oeq_data = load_oeq('results/oeq_stats_260223.jsonl')

    # 定义 LaTeX 表格中的模型顺序及其对应的内部名称
    model_mapping = [
        ('GPT-5.2-Fast', 'openai_gpt-5.2-fast'),
        ('GPT-5.2-Thinking$^\dagger$', 'openai_gpt-5.2-thinking'),
        ('Gemini-3-Flash', 'gemini-3-flash'),
        ('Gemini-3-Pro', 'gemini-3-pro'),
        ('Claude-4.6-sonnet', 'openai_claude-sonnet-4.6'),
        ('GLM-5', 'glm4.7-unthinking'),
        ('GLM-5-thinking$^\dagger$', 'glm4.7-thinking'),
        ('DeepSeek-V3.2', 'openai_deepseek-chat'),
        ('DeepSeek-V3.2-thinking$^\dagger$', 'openai_deepseek-reasoner'),
        ('Qwen3-max', 'openai_qwen3-max'),
        ('Qwen3-235B-A22B', 'openai_qwen3-235b'),
        ('Qwen3-32B', 'openai_qwen3-32b'),
        ('Qwen3-14B', 'openai_qwen3-14b')
    ]

    for display_name, internal_name in model_mapping:
        mcq = mcq_data.get(internal_name, {})
        oeq = oeq_data.get(internal_name, {})
        
        row_vals = []
        
        # Knowledge (MCQ) 分数
        ik_vals = [mcq.get('Tissue'), mcq.get('Reagent'), mcq.get('Method')]
        row_vals.extend([f"{v:.1f}" if v is not None else "--" for v in ik_vals])
        
        # Application (OEQ) 分数
        ia_vals = [oeq.get('Completeness'), oeq.get('Correctness'), oeq.get('Effectiveness')]
        row_vals.extend([f"{v:.1f}" if v is not None else "--" for v in ia_vals])
        
        # Total (Harmonic Mean)
        if all(v is not None for v in ik_vals) and all(v is not None for v in ia_vals):
            ik = sum(ik_vals) / 3
            ia = sum(ia_vals) / 3
            if (ik + ia) > 0:
                total = 2 * ik * ia / (ik + ia)
                row_vals.append(f"{total:.1f}")
            else:
                row_vals.append("0.0")
        else:
            row_vals.append("--")
        
        # 生成 LaTeX 格式的一行数据
        latex_row = display_name + " & " + " & ".join(row_vals) + " \\\\"
        print(latex_row)

if __name__ == "__main__":
    main()
