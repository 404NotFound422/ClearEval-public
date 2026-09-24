import argparse
import json
import os
import sys
try:
    from .oeq_metrics import aggregate_items
except ImportError:
    from oeq_metrics import aggregate_items

"""
本脚本用于聚合问答题（OEQ）的评分结果。
主要功能：
1. 遍历指定目录下的所有模型评分文件。
2. 提取并归一化分数。
3. 处理实验数据中的标签错误。
4. 将统计结果保存为 JSONL 文件。

更新：增加了路径自动搜索逻辑，支持不同运行环境。
"""

# 默认评分结果目录：使用随仓库发布的全部 253 个场景的机器评分结果，
# 保证 oeq_stats 可由公开数据复现（主结果表 Table 2 的来源）。
DEFAULT_OEQ_DIR = r'dataset/Q+AR/result'
OUTPUT_FILE_NAME = 'oeq_stats_scoring_v2.jsonl'

def find_dir(dirname):
    """查找目录，尝试多种路径。"""
    search_paths = [
        dirname,
        os.path.join('..', dirname),
        os.path.join('results', dirname) # 针对误操作
    ]
    for path in search_paths:
        if os.path.isdir(path):
            return path
    return None

def aggregate_oeq(oeq_dir=None, output_file=None):
    if oeq_dir is None:
        oeq_dir = find_dir(DEFAULT_OEQ_DIR)
    if not oeq_dir:
        print(f"错误: 找不到评分结果目录 ({DEFAULT_OEQ_DIR})。")
        sys.exit(1)

    # 确定输出文件路径，默认存放在 results 目录下
    if output_file is None:
        output_dir = 'results'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, OUTPUT_FILE_NAME)

    results = []
    for filename in sorted(os.listdir(oeq_dir)):
        # The base aggregate uses only the 13 one-shot runs. RAG and
        # self-check variants are aggregated separately by aggregate_rag_baseline.py.
        if filename.startswith('evaluation_results_') and filename.endswith('_1-shot.json'):
            model_name = filename[len('evaluation_results_'):-len('.json')]
            if model_name.endswith('_0-shot'):
                model_name = model_name[:-len('_0-shot')]
            elif model_name.endswith('_1-shot'):
                model_name = model_name[:-len('_1-shot')]
            
            filepath = os.path.join(oeq_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.loads(f.read())
                
                results.append({"model_name": model_name, **aggregate_items(data)})
            except Exception as e:
                raise ValueError(f"Failed to aggregate {filename}: {e}") from e

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for res in results:
            f.write(json.dumps(res, ensure_ascii=False) + '\n')
            
    print(f"已将 {len(results)} 个模型的 OEQ 结果聚合至 {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate OEQ evaluation results.")
    parser.add_argument("--input-dir", default=None, help="Directory containing evaluation_results_*.json files")
    parser.add_argument("--output", default=None, help="Output JSONL file path")
    args = parser.parse_args()
    aggregate_oeq(oeq_dir=args.input_dir, output_file=args.output)
