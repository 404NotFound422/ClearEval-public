import json
import os
import re
import sys

"""
本脚本用于聚合多选题（MCQ）的基准测试结果。
主要功能：
1. 从基准测试结果文件和各个模型的 checkpoint 文件中提取数据。
2. 统计各模型在不同知识维度上的准确率。
3. 将知识维度映射为精简的标签。
4. 将统计结果保存为 JSONL 文件，供后续绘图使用。

更新：增加了路径自动搜索逻辑，支持从根目录或 results 目录运行。
"""

# 默认文件名
DEFAULT_RESULTS_FILE = 'benchmark_results_20260222_124734.jsonl'
OUTPUT_FILE_NAME = 'mcq_stats_20260222.jsonl'

# 知识维度到绘图标签的映射
mcq_dimension_mapping = {
    "Tissue Features & Labeling Sites": "Tissues & Markers (Tissue/Site)",
    "Marker Features & Targets": "Tissues & Markers (Marker/Target)",
    "Reagent Names & Abbreviations": "Reagents (Name/Abbr)",
    "Reagent Functions & Applications": "Reagents (Func/App)",
    "Method Names & Categories": "Method (Name/Cat)",
    "Method Characteristics & Applications": "Method (Char/App)",
    "Method Selection": "Method (Selection)",
    "Protocol Steps & Parameters": "Method (Protocol/Param)",
    "Full-Process Design": "Method (Full Design)"
}

def find_file(filename):
    """在当前目录及其 results 子目录中查找文件。"""
    search_paths = [
        filename,
        os.path.join('results', filename),
        os.path.join('..', filename),
        os.path.join('..', 'results', filename)
    ]
    for path in search_paths:
        if os.path.exists(path):
            return path
    return None

def extract_answer(text):
    """从模型生成的文本中提取答案选项（A-H）。"""
    if not text:
        return None
    patterns = [
        r'\[([A-H])\]',
        r'\(([A-H])\)',
        r'The answer is ([A-H])',
        r'选项([A-H])',
        r'^([A-H])$',
        r'(?i)answer:?\s*([A-H])',
        r'([A-H])是正确选项',
        r'([A-H]) is correct'
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text))
        if match:
            return match.group(1).upper()
    return None

def aggregate_mcq():
    # 确定结果文件路径
    results_file = find_file(DEFAULT_RESULTS_FILE)
    if not results_file:
        # 尝试自动查找任何 benchmark_results_*.jsonl
        import glob
        all_jsonls = glob.glob("results/benchmark_results_*.jsonl") + glob.glob("benchmark_results_*.jsonl")
        if all_jsonls:
            # 选最新的一个
            results_file = sorted(all_jsonls)[-1]
            print(f"警告: 未找到 {DEFAULT_RESULTS_FILE}，自动匹配到最新文件: {results_file}")
        else:
            print(f"错误: 找不到基准测试结果文件 ({DEFAULT_RESULTS_FILE})。")
            sys.exit(1)

    # 确定输出文件路径
    results_dir = os.path.dirname(results_file) if os.path.dirname(results_file) else 'results'
    output_file = os.path.join(results_dir, OUTPUT_FILE_NAME)

    models = []
    with open(results_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'model_name' in data:
                    models.append(data['model_name'])
            except:
                continue
    
    # 也检查 checkpoint 文件
    checkpoint_dir = results_dir
    for filename in os.listdir(checkpoint_dir):
        if filename.startswith('checkpoint_') and filename.endswith('.jsonl'):
            model_name = filename[len('checkpoint_'):-len('.jsonl')]
            models.append(model_name)
            
    models = sorted(list(set(models)))
    all_results = []
    
    for model_name in models:
        checkpoint_file = os.path.join(checkpoint_dir, f"checkpoint_{model_name}.jsonl")
        if not os.path.exists(checkpoint_file):
            continue
            
        dimension_stats = {label: {'correct': 0, 'total': 0} for label in mcq_dimension_mapping.values()}
        seen_questions = set()
        
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    qid = entry.get('question_id')
                    if qid in seen_questions: continue
                    seen_questions.add(qid)
                    
                    specific = entry.get('specific') or entry.get('knowledge_point') or entry.get('category')
                    if specific in mcq_dimension_mapping:
                        label = mcq_dimension_mapping[specific]
                        prediction = extract_answer(entry.get('solution', ''))
                        gt = entry.get('answers')
                        
                        dimension_stats[label]['total'] += 1
                        if prediction == gt:
                            dimension_stats[label]['correct'] += 1
                except:
                    continue
        
        total_q = sum(d['total'] for d in dimension_stats.values())
        if total_q == 0:
            continue
            
        stats = {}
        for label, counts in dimension_stats.items():
            correct = counts['correct']
            total = counts['total']
            stats[label] = correct / total if total > 0 else 0
            
        all_results.append({"model": model_name, "stats": stats})
        
    with open(output_file, 'w', encoding='utf-8') as f:
        for res in all_results:
            f.write(json.dumps(res, ensure_ascii=False) + '\n')
        
    print(f"已将 {len(all_results)} 个模型的 MCQ 结果聚合至 {output_file}")

if __name__ == "__main__":
    aggregate_mcq()
