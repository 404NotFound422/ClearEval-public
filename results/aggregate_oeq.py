import json
import os
import sys

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
OUTPUT_FILE_NAME = 'oeq_stats_260223.jsonl'

# 归一化满分标准
MAX_SCORES = {
    'c_step': 2, 'c_param': 3, 'co_order': 3, 'co_method': 2,
    'co_param': 2, 'co_chem': 1, 's_method': 5, 's_label': 6,
    's_trans': 3, 's_time': 3
}

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

def aggregate_oeq():
    oeq_dir = find_dir(DEFAULT_OEQ_DIR)
    if not oeq_dir:
        print(f"错误: 找不到评分结果目录 ({DEFAULT_OEQ_DIR})。")
        sys.exit(1)

    # 确定输出文件路径，默认存放在 results 目录下
    output_dir = 'results'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_file = os.path.join(output_dir, OUTPUT_FILE_NAME)

    results = []
    for filename in os.listdir(oeq_dir):
        if filename.startswith('evaluation_results_') and filename.endswith('.json'):
            model_name = filename[len('evaluation_results_'):-len('.json')]
            if model_name.endswith('_0-shot'):
                model_name = model_name[:-len('_0-shot')]
            elif model_name.endswith('_1-shot'):
                model_name = model_name[:-len('_1-shot')]
            
            filepath = os.path.join(oeq_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.loads(f.read())
                
                metrics = {k: [] for k in MAX_SCORES.keys()}
                eval_list = data if isinstance(data, list) else [data]
                
                for item in eval_list:
                    eval_obj = item.get('evaluation', {})
                    scores_obj = eval_obj.get('scores', {})
                    
                    comp = scores_obj.get('completeness', {})
                    for m in ['c_step', 'c_param']:
                        val = comp.get(m, {}).get('score')
                        if val is not None: metrics[m].append(float(val))
                    
                    corr = scores_obj.get('correctness', {})
                    for m in ['co_order', 'co_method', 'co_param', 'co_chem']:
                        val = corr.get(m, {}).get('score')
                        if val is not None: metrics[m].append(float(val))
                        
                    eff = scores_obj.get('effectiveness', {})
                    for m in ['s_method', 's_label', 's_trans', 's_time']:
                        val = eff.get(m, {}).get('score')
                        if val is not None: metrics[m].append(float(val))
                
                if not any(metrics.values()):
                    continue
                
                avg_scores = {}
                for m, vals in metrics.items():
                    avg = sum(vals) / len(vals) if vals else 0
                    avg_scores[m] = avg
                    avg_scores[f"{m}_norm"] = avg / MAX_SCORES[m] if MAX_SCORES[m] > 0 else 0
                
                results.append({
                    "model_name": model_name,
                    "average_scores": avg_scores,
                    "sample_count": len(next(iter(metrics.values()))) if metrics.values() else 0
                })
            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")

    with open(output_file, 'w', encoding='utf-8') as f:
        for res in results:
            f.write(json.dumps(res, ensure_ascii=False) + '\n')
            
    print(f"已将 {len(results)} 个模型的 OEQ 结果聚合至 {output_file}")

if __name__ == "__main__":
    aggregate_oeq()
