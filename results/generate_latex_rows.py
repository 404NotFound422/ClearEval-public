import argparse
try:
    from .calculate_main_table_score import load_mcq, load_oeq
except ImportError:
    from calculate_main_table_score import load_mcq, load_oeq

"""
本脚本用于将 ClearEval 的聚合结果格式化为 LaTeX 表格行。
计算逻辑：
1. Knowledge (I_K): Tissue, Reagent, Method 的平均值。
2. Application (I_A): 每题先取三个维度的最小值，再在完整评分题目间取平均。
3. Total: 2 * I_K * I_A / (I_K + I_A) (调和平均数)。
"""

def main(oeq_file='results/oeq_stats_scoring_v2.jsonl'):
    mcq_data = load_mcq('results/mcq_stats_20260222.jsonl')
    oeq_data = load_oeq(oeq_file)

    # 定义 LaTeX 表格中的模型顺序及其对应的内部名称
    model_mapping = [
        ('GPT-5.2-Fast', 'openai_gpt-5.2-fast'),
        (r'GPT-5.2-Thinking$^\dagger$', 'openai_gpt-5.2-thinking'),
        ('Gemini-3-Flash', 'gemini-3-flash'),
        ('Gemini-3-Pro', 'gemini-3-pro'),
        ('Claude-4.6-sonnet', 'openai_claude-sonnet-4.6'),
        ('GLM-5', 'glm4.7-unthinking'),
        (r'GLM-5-thinking$^\dagger$', 'glm4.7-thinking'),
        ('DeepSeek-V3.2', 'openai_deepseek-chat'),
        (r'DeepSeek-V3.2-thinking$^\dagger$', 'openai_deepseek-reasoner'),
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
            ia = oeq['I_A']
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
    parser = argparse.ArgumentParser(description="Generate LaTeX rows with the shared OEQ scoring contract.")
    parser.add_argument('--oeq-file', default='results/oeq_stats_scoring_v2.jsonl')
    main(oeq_file=parser.parse_args().oeq_file)
