import asyncio
import json
import os
import traceback
from datetime import datetime

from models.Model_Loader import ModelLoader
from dataset.Dataset_Loader import DatasetLoader
from services.TOC_Benchmark import TOCBenchmark

# 文件路径配置
config_file_path = 'config/config.yaml'
dataset_config_file_path = 'config/DataSet_Config.yaml'

# 创建结果保存目录
results_dir = 'results'
os.makedirs(results_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
result_filename = os.path.join(results_dir, f"benchmark_results_{timestamp}.jsonl")
detailed_results_filename = os.path.join(results_dir, f"detailed_results_{timestamp}.txt")

# 全局写锁，用于在并发评测时安全地保存结果
file_write_lock = asyncio.Lock()

async def run_benchmark_for_model(model_name, model_instance, benchmark, result_filename, detailed_results_filename, model_semaphore):
    """
    单个模型的评测逻辑，包含并发控制和结果保存。
    """
    async with model_semaphore:
        print(f"\n>>> 开始对模型进行评测: {model_name}")
        try:
            # 定义断点文件路径
            checkpoint_file = os.path.join(results_dir, f"checkpoint_{model_name}.jsonl")
            # 执行异步评测
            results, answers = await benchmark.evaluate_model_async(model_name, model_instance, checkpoint_file=checkpoint_file)
            
            print(f"\n<<< 模型 {model_name} 评测完成")
            print(f"[{model_name}] 总准确率: {results['overall_accuracy']:.2%}")

            # 使用异步锁确保文件写入不冲突
            async with file_write_lock:
                # 构建并保存结果摘要 (JSONL 格式)
                result_entry = {
                    'model_name': model_name,
                    **results
                }
                with open(result_filename, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(result_entry, ensure_ascii=False) + '\n')

                # 保存详细的回答记录 (TXT 格式)
                with open(detailed_results_filename, 'a', encoding='utf-8') as f:
                    f.write(f"\n\n{'='*50}\n")
                    f.write(f"Model: {model_name}\n")
                    f.write(f"Overall Accuracy: {results['overall_accuracy']:.2%}\n")
                    f.write(f"Total Time Cost: {results['total_time_cost']:.2f} seconds\n")
                    f.write(f"Total Tokens Used: {json.dumps(results['total_tokens_used'])}\n")
                    f.write(f"{'='*50}\n\n")

                    for ans_detail in answers:
                        f.write(f"Question ID: {ans_detail.get('question_id', 'N/A')}\n")
                        f.write(f"Knowledge Point: {ans_detail.get('knowledge_point', 'N/A')}\n")
                        f.write(f"Question: {ans_detail.get('question', 'N/A')}\n")
                        f.write(f"Correct Answer: {ans_detail.get('answer', 'N/A')}\n")
                        f.write(f"Model Solution: {ans_detail.get('solution', 'N/A')}\n")
                        f.write(f"Time Cost: {ans_detail.get('time_cost', 'N/A'):.2f}s\n")
                        f.write(f"Tokens Used: {json.dumps(ans_detail.get('tokens_used', 'N/A'))}\n\n")

        except Exception as e:
            print(f"!!! 模型 {model_name} 评测出错: {str(e)}")
            traceback.print_exc()
            async with file_write_lock:
                error_result = {
                    'model_name': model_name,
                    'error': str(e),
                }
                with open(result_filename, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(error_result, ensure_ascii=False) + '\n')

async def main():
    # 1. 加载模型配置
    model_loader = ModelLoader(config_path=config_file_path)
    models = model_loader.load_models()

    # 2. 加载数据集
    dataset_loader = DatasetLoader(dataset_config_path=dataset_config_file_path)
    dataset = dataset_loader.load_dataset()
    development_data = dataset.get('development_data')
    validation_data = dataset.get('validation_data')

    # 3. 初始化基准测试服务
    benchmark = TOCBenchmark(development_data, validation_data)

    # 4. 配置需要评测的模型列表
    '''
    model_list = [
        "openai_gpt-5.2-fast",      
        "openai_gpt-5.2-thinking",    
        "gemini-3-pro", 
        "gemini-3-flash",
        "openai_claude-sonnet-4.6",
        "glm4.7-thinking",
        "glm4.7-unthinking",
        "openai_deepseek-chat",
        "openai_deepseek-reasoner",
        "openai_qwen3-max",
        "openai_qwen3-235b",
        "openai_qwen3-32b",
        "openai_qwen3-14b"
    ]
    '''

    model_list = [
        "openai_gpt-5.2-fast",
        "openai_gpt-5.2-thinking",
        "gemini-3-pro", 
        "gemini-3-flash",
        "openai_claude-sonnet-4.6",
        "glm4.7-thinking",
        "glm4.7-unthinking",
        "openai_deepseek-chat",
        "openai_deepseek-reasoner",
        "openai_qwen3-max",
        "openai_qwen3-235b",
        "openai_qwen3-32b",
        "openai_qwen3-14b"
    ]

    # 设置模型层级的并发限制 (同时评测多少个模型)
    # 内部 TOCBenchmark 还会对单个模型请求进行并发控制 (默认并发 5)
    model_concurrency_limit = 3 
    model_semaphore = asyncio.Semaphore(model_concurrency_limit)

    # 5. 创建并发评测任务
    tasks = []
    for model_name in model_list:
        if model_name not in models:
            print(f"--- 模型 {model_name} 未在配置中找到，跳过。 ---")
            continue
        
        tasks.append(run_benchmark_for_model(
            model_name, 
            models[model_name], 
            benchmark, 
            result_filename, 
            detailed_results_filename, 
            model_semaphore
        ))

    # 并发运行所有选定的模型评测
    if tasks:
        await asyncio.gather(*tasks)

    print("\n" + "="*50)
    print("所有模型评测任务已结束。")
    print(f"摘要结果已保存至: {result_filename}")
    print(f"详细记录已保存至: {detailed_results_filename}")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
