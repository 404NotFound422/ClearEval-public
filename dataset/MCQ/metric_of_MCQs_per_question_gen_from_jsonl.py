import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
from transformers import AutoTokenizer
from tabulate import tabulate # 导入用于生成漂亮表格的库

# --- CONFIGURATION ---
### --- Data path resolves relative to this script (edit if your layout differs) --- ###
import os
JSONL_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'final', 'development.jsonl')
TOKENIZER_MODEL = 'bert-base-uncased'

def create_visualizations(df_report, question_starts_counter, correct_answer_ranks, output_prefix='dataset_analysis'):
    """为分析报告生成并保存图表。"""
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # 1. Token长度分布图 (问题 vs 所有选项)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    fig.suptitle('Global Token Length Distributions', fontsize=20, weight='bold')
    sns.histplot(df_report.loc['Question', 'Values'], ax=axes[0], kde=True, bins=20, color='#577590')
    axes[0].set_title('Question Token Lengths')
    axes[0].set_xlabel('Tokens')
    sns.histplot(df_report.loc['All Options', 'Values'], ax=axes[1], kde=True, bins=20, color='#f9a03f')
    axes[1].set_title('All Option Token Lengths')
    axes[1].set_xlabel('Tokens')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{output_prefix}_token_distributions.png", dpi=300)
    plt.close(fig)

    # 2. 问题起始词图
    common_starts = question_starts_counter.most_common(10)
    words, counts = zip(*common_starts)
    fig_q, ax_q = plt.subplots(figsize=(12, 7))
    sns.barplot(x=list(counts), y=list(words), ax=ax_q, palette='viridis', orient='h')
    ax_q.set_title('Top 10 Question Starting Words', fontsize=18, weight='bold')
    ax_q.set_xlabel('Frequency')
    ax_q.set_ylabel('Starting Word')
    plt.tight_layout()
    fig_q.savefig(f"{output_prefix}_question_starts.png", dpi=300)
    plt.close(fig_q)

    # 3. 答案长度偏见分析图
    fig_bias, axes_bias = plt.subplots(1, 2, figsize=(18, 7))
    fig_bias.suptitle('Per-Question Answer Length Bias Analysis', fontsize=20, weight='bold')
    sns.histplot(df_report.loc['Answer vs. Distractor Length Diff', 'Values'], ax=axes_bias[0], kde=True, bins=25, color='#d62728')
    axes_bias[0].axvline(0, color='black', linestyle='--', linewidth=2)
    axes_bias[0].set_title('Answer Length - Avg. Distractor Length', pad=15)
    axes_bias[0].set_xlabel('Token Length Difference (Correct - Avg. Distractor)')
    axes_bias[0].set_ylabel('Frequency')
    if correct_answer_ranks:
        ranks, rank_counts = zip(*sorted(correct_answer_ranks.items()))
        sns.barplot(x=list(ranks), y=list(rank_counts), ax=axes_bias[1], palette='coolwarm')
        axes_bias[1].set_title('Rank of Correct Answer by Length', pad=15)
        axes_bias[1].set_xlabel('Rank (1=Longest)')
        axes_bias[1].set_ylabel('Frequency')
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig_bias.savefig(f"{output_prefix}_length_bias.png", dpi=300)
    plt.close(fig_bias)
    
    # 位置偏见图已被移除
    print(f"\nVisualizations saved as '{output_prefix}_token_distributions.png', '{output_prefix}_question_starts.png', and '{output_prefix}_length_bias.png'")


def analyze_dataset(file_path, tokenizer_name):
    """对一个JSONL格式的问答数据集进行全面分析。"""
    print(f"Loading tokenizer: '{tokenizer_name}'...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    except OSError:
        print(f"Error: Tokenizer model '{tokenizer_name}' not found. Please check the name or your internet connection.")
        return

    # 数据存储
    question_lengths, all_option_lengths = [], []
    answer_lengths, distractor_lengths = [], [] # 保留以进行长度差异分析
    num_options_list = []
    question_vocab, answer_vocab = Counter(), Counter()
    question_starts_counter = Counter()

    # 偏见分析数据存储
    length_differences, length_ratios = [], []
    correct_answer_ranks = Counter()
    answer_position_counter = Counter()

    print(f"Analyzing dataset file: '{file_path}'...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                data = json.loads(line)
                q_text = data.get('question', '')
                q_tokens = tokenizer.encode(q_text, add_special_tokens=False)
                question_lengths.append(len(q_tokens))
                question_vocab.update(q_tokens)
                first_word = q_text.split(' ')[0].strip().lower() if q_text else ''
                question_starts_counter[first_word] += 1
                options = data.get('options', [])
                num_options_list.append(len(options))
                answer_idx = data.get('answer_index')

                if answer_idx is not None and 0 <= answer_idx < len(options):
                    answer_position_counter[answer_idx] += 1
                    current_option_tokens = [tokenizer.encode(opt, add_special_tokens=False) for opt in options]
                    current_option_lengths = [len(t) for t in current_option_tokens]
                    all_option_lengths.extend(current_option_lengths)
                    correct_len = current_option_lengths[answer_idx]
                    correct_tokens = current_option_tokens[answer_idx]
                    distractor_lens_current = [l for i, l in enumerate(current_option_lengths) if i != answer_idx]
                    answer_lengths.append(correct_len)
                    answer_vocab.update(correct_tokens)
                    distractor_lengths.extend(distractor_lens_current)

                    if distractor_lens_current:
                        avg_distractor_len = np.mean(distractor_lens_current)
                        length_differences.append(correct_len - avg_distractor_len)
                        sorted_lens = sorted(current_option_lengths, reverse=True)
                        try: rank = sorted_lens.index(correct_len) + 1; correct_answer_ranks[rank] += 1
                        except ValueError:
                            for i, length in enumerate(sorted_lens):
                                if length == correct_len: correct_answer_ranks[i + 1] += 1; break
    except FileNotFoundError: print(f"FATAL: The file '{file_path}' was not found."); return
    except Exception as e: print(f"An error occurred: {e}"); return
    if not question_lengths: print("FATAL: No questions were processed."); return

    # --- 构建报告 ---
    total_questions = len(question_lengths)
    report_data = {
        'Total Questions': {'Value': total_questions},
        '--- Question Stats ---': {},
        'Question': {'Mean': np.mean(question_lengths), 'Median': np.median(question_lengths), 'Std Dev': np.std(question_lengths), 'Min': np.min(question_lengths), 'Max': np.max(question_lengths), 'Total Tokens': int(np.sum(question_lengths)), 'Values': question_lengths},
        '--- Option Stats (All) ---': {},
        'All Options': {'Mean': np.mean(all_option_lengths) if all_option_lengths else 0, 'Median': np.median(all_option_lengths) if all_option_lengths else 0, 'Std Dev': np.std(all_option_lengths) if all_option_lengths else 0, 'Min': np.min(all_option_lengths) if all_option_lengths else 0, 'Max': np.max(all_option_lengths) if all_option_lengths else 0, 'Values': all_option_lengths},
        '--- MCQ Structure ---': {},
        'Options per Question': {'Mean': np.mean(num_options_list), 'Median': np.median(num_options_list), 'Min': np.min(num_options_list), 'Max': np.max(num_options_list)},
        '--- Lexical Richness ---': {},
        'Question Vocabulary Size': {'Value': len(question_vocab)},
        'Question TTR': {'Value': len(question_vocab) / sum(question_vocab.values()) if sum(question_vocab.values()) > 0 else 0},
        'Answer Vocabulary Size': {'Value': len(answer_vocab)},
        'Answer TTR': {'Value': len(answer_vocab) / sum(answer_vocab.values()) if sum(answer_vocab.values()) > 0 else 0},
        '--- Answer Bias Analysis ---': {},
        'Answer vs. Distractor Length Diff': {'Mean': np.mean(length_differences) if length_differences else 0, 'Median': np.median(length_differences) if length_differences else 0, 'Std Dev': np.std(length_differences) if length_differences else 0, 'Values': length_differences},
        'Correct Answer Length Rank Freq': {'Value': ', '.join([f'Rank {r}: {c}' for r, c in sorted(correct_answer_ranks.items())])},
    }

    # 格式化打印主报告
    df_report = pd.DataFrame(report_data).T.fillna('')
    pd.options.display.float_format = '{:,.2f}'.format
    print("\n--- DATASET ANALYSIS REPORT ---")
    print(df_report.drop(columns=['Values']))

    # --- 修改部分: 打印答案位置分布的统计表 ---
    print("\n\n--- Correct Answer Positional Bias ---")
    if answer_position_counter and total_questions > 0:
        table_headers = ['Option', 'Frequency', 'Percentage']
        table_data = []
        
        # 按位置顺序 (0, 1, 2...) 对数据排序
        for pos, count in sorted(answer_position_counter.items()):
            label = chr(65 + pos)  # 0 -> 'A', 1 -> 'B', etc.
            percentage = (count / total_questions) * 100
            table_data.append([label, count, f"{percentage:.2f}%"])
        
        # 添加总计行
        table_data.append(['---', '---', '---'])
        table_data.append(['Total', total_questions, '100.00%'])
        
        # 使用tabulate打印漂亮的表格
        print(tabulate(table_data, headers=table_headers, tablefmt='pretty'))
    else:
        print("No answer position data to display.")

    # 生成并保存图表
    create_visualizations(df_report, question_starts_counter, correct_answer_ranks)

if __name__ == "__main__":
    analyze_dataset(JSONL_FILE_PATH, TOKENIZER_MODEL)