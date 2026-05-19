import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
from transformers import AutoTokenizer

# --- CONFIGURATION ---
### --- IMPORTANT: EDIT THIS LINE --- ###
JSONL_FILE_PATH = r'D:\YWB\TOCModelBenchmark\dataset\MCQ\final\development.jsonl'
# We use a standard tokenizer that reflects how many models process text.
TOKENIZER_MODEL = 'bert-base-uncased'

def create_visualizations(df_report, question_starts_counter, output_prefix='dataset_analysis'):
    """Generates and saves plots for the analysis report."""
    
    # 1. Token Length Distribution Plot
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, axes = plt.subplots(1, 3, figsize=(20, 6))
    fig.suptitle('Token Length Distributions', fontsize=20, weight='bold')

    sns.histplot(df_report.loc['Question', 'Values'], ax=axes[0], kde=True, bins=20, color='#577590')
    axes[0].set_title('Question Token Lengths')
    axes[0].set_xlabel('Tokens')
    
    sns.histplot(df_report.loc['Answer', 'Values'], ax=axes[1], kde=True, bins=20, color='#90be6d')
    axes[1].set_title('Correct Answer Token Lengths')
    axes[1].set_xlabel('Tokens')

    sns.histplot(df_report.loc['Distractor', 'Values'], ax=axes[2], kde=True, bins=20, color='#f8961e')
    axes[2].set_title('Distractor Token Lengths')
    axes[2].set_xlabel('Tokens')
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(f"{output_prefix}_token_distributions.png", dpi=300)
    plt.close(fig)

    # 2. Question Starting Word Plot
    common_starts = question_starts_counter.most_common(10)
    words, counts = zip(*common_starts)

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(x=list(counts), y=list(words), ax=ax, palette='viridis', orient='h')
    ax.set_title('Top 10 Question Starting Words', fontsize=18, weight='bold')
    ax.set_xlabel('Frequency')
    ax.set_ylabel('Starting Word')
    
    plt.tight_layout()
    fig.savefig(f"{output_prefix}_question_starts.png", dpi=300)
    plt.close(fig)
    
    print(f"\nVisualizations saved as '{output_prefix}_token_distributions.png' and '{output_prefix}_question_starts.png'")


def analyze_dataset(file_path, tokenizer_name):
    """
    Performs a comprehensive analysis of a JSONL Q&A dataset.
    """
    print(f"Loading tokenizer: '{tokenizer_name}'...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    except OSError:
        print(f"Error: Tokenizer model '{tokenizer_name}' not found. Please check the name or your internet connection.")
        return

    # Data storage
    question_lengths, answer_lengths, distractor_lengths = [], [], []
    num_options_list = []
    question_vocab, answer_vocab = Counter(), Counter()
    question_starts_counter = Counter()

    print(f"Analyzing dataset file: '{file_path}'...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                data = json.loads(line)

                # --- Question Analysis ---
                q_text = data.get('question', '')
                q_tokens = tokenizer.encode(q_text, add_special_tokens=False)
                question_lengths.append(len(q_tokens))
                question_vocab.update(q_tokens)
                
                first_word = q_text.split(' ')[0].strip().lower() if q_text else ''
                question_starts_counter[first_word] += 1

                # --- Answer & Distractor Analysis ---
                options = data.get('options', [])
                num_options_list.append(len(options))
                answer_idx = data.get('answer_index')

                if answer_idx is not None and 0 <= answer_idx < len(options):
                    for i, option_text in enumerate(options):
                        option_tokens = tokenizer.encode(option_text, add_special_tokens=False)
                        if i == answer_idx:
                            answer_lengths.append(len(option_tokens))
                            answer_vocab.update(option_tokens)
                        else:
                            distractor_lengths.append(len(option_tokens))

    except FileNotFoundError:
        print(f"FATAL: The file '{file_path}' was not found.")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        return

    if not question_lengths:
        print("FATAL: No questions were processed. The file might be empty or in the wrong format.")
        return

    # --- Build Report ---
    report_data = {
        'Total Questions': {'Value': len(question_lengths)},
        '--- Question Stats ---': {},
        'Question': {
            'Mean': np.mean(question_lengths), 'Median': np.median(question_lengths),
            'Std Dev': np.std(question_lengths), 'Min': np.min(question_lengths),
            'Max': np.max(question_lengths), 'Total Tokens': int(np.sum(question_lengths)),
            'Values': question_lengths
        },
        '--- Answer Stats ---': {},
        'Answer': {
            'Mean': np.mean(answer_lengths), 'Median': np.median(answer_lengths),
            'Std Dev': np.std(answer_lengths), 'Min': np.min(answer_lengths),
            'Max': np.max(answer_lengths), 'Total Tokens': int(np.sum(answer_lengths)),
            'Values': answer_lengths
        },
        '--- Distractor Stats ---': {},
        'Distractor': {
            'Mean': np.mean(distractor_lengths), 'Median': np.median(distractor_lengths),
            'Std Dev': np.std(distractor_lengths), 'Min': np.min(distractor_lengths),
            'Max': np.max(distractor_lengths),
            'Values': distractor_lengths
        },
        '--- MCQ Structure ---': {},
        'Options per Question': {
            'Mean': np.mean(num_options_list), 'Median': np.median(num_options_list),
            'Min': np.min(num_options_list), 'Max': np.max(num_options_list),
        },
        '--- Lexical Richness ---': {},
        'Question Vocabulary Size': {'Value': len(question_vocab)},
        'Question Type-Token Ratio (TTR)': {'Value': len(question_vocab) / sum(question_vocab.values()) if sum(question_vocab.values()) > 0 else 0},
        'Answer Vocabulary Size': {'Value': len(answer_vocab)},
        'Answer Type-Token Ratio (TTR)': {'Value': len(answer_vocab) / sum(answer_vocab.values()) if sum(answer_vocab.values()) > 0 else 0},
    }

    # Format for printing
    df_report = pd.DataFrame(report_data).T.fillna('')
    pd.options.display.float_format = '{:,.2f}'.format
    print("\n--- DATASET ANALYSIS REPORT ---")
    print(df_report.drop(columns=['Values'])) # Don't print the raw value lists

    # Generate and save plots
    create_visualizations(df_report, question_starts_counter)

if __name__ == "__main__":
    analyze_dataset(JSONL_FILE_PATH, TOKENIZER_MODEL)