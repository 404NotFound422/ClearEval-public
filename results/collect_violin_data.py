
import os
import json
import asyncio
import re
from models.Model_Loader import ModelLoader

# 配置信息
RESPONSE_DIR = 'dataset/Q+AR/model_response/260223'  # 模型回答存放目录
SCORE_DIR = 'dataset/Q+AR/score_results/260223'     # 评分结果存放目录
OUTPUT_FILE = 'results/violin_data.json'           # 数据处理后的输出文件
EXTRACTOR_MODEL_NAME = 'openai_gpt-4o'            # 用于提取参数的LLM模型名称
CONFIG_PATH = 'config/config.yaml'                 # 配置文件路径

SEM_LIMIT = 10 # API调用的并发限制

# 提取物理参数的提示词
EXTRACTION_PROMPT = """
你是一位组织光透明（Tissue Optical Clearing）领域的专家。请从以下透明方案中，提取用于“固定”和“透明/透明化”的累计时间。

说明：
1. “固定”（Fixation）时间包括任何明确提到固定（固定）或后固定的步骤。
2. “透明/透明化”（Clearing/Transparency）时间包括脱水（脱水）、脱脂（脱脂）和折射率匹配（透明/折射率匹配）等步骤。
3. 排除标记/染色（标记, 染色, 抗体, 孵育, 封闭）的时间、染色步骤之间的洗涤时间以及成像（成像）的时间。
4. 如果某一步骤同时包含透明和标记，请尽量仅估计透明部分的时间；如果无法区分，请包含在内并注明。
5. 如果时间以范围形式给出（例如 2-6 小时），请提供平均值（例如 4.0）。
6. 将所有时间转换为“小时”。（例如：1天 = 24小时，1周 = 168小时）。

仅返回一个包含以下键的 JSON 对象：
- fixation_time_hours: float
- clearing_time_hours: float

方案内容：
{protocol}
"""

async def extract_time_from_response(model_instance, protocol_text, semaphore):
    """
    调用LLM从方案文本中异步提取时间参数
    """
    async with semaphore:
        prompt = EXTRACTION_PROMPT.format(protocol=protocol_text)
        try:
            response = await model_instance._acall(prompt)
            content = response.get('content', '')
            # 从回答中匹配JSON对象
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data
            else:
                print(f"无法从回答中解析JSON: {content}")
                return None
        except Exception as e:
            print(f"调用LLM出错: {e}")
            return None

async def process_model(model_name, response_file, score_file, model_instance, semaphore):
    """
    处理单个模型的所有回答和评分数据
    """
    print(f"正在处理模型: {model_name}")
    
    # 读取模型生成的回答
    with open(response_file, 'r', encoding='utf-8') as f:
        responses = json.load(f)
    
    # 读取对应的评分结果，提取 s_label 分数
    scores_map = {}
    if os.path.exists(score_file):
        with open(score_file, 'r', encoding='utf-8') as f:
            scores_data = json.load(f)
            for item in scores_data:
                qid = item.get("question_id")
                if not qid and "evaluation" in item and "meta_data" in item["evaluation"]:
                    qid = item["evaluation"]["meta_data"].get("protocol_id")
                
                if qid:
                    # 提取 effectiveness 分类下的 s_label 分数
                    s_label = item.get("evaluation", {}).get("scores", {}).get("effectiveness", {}).get("s_label", {}).get("score")
                    if s_label is not None:
                        scores_map[qid] = s_label

    # 创建并行提取任务
    tasks = []
    for resp in responses:
        protocol = resp.get('model_response', '')
        tasks.append(extract_time_from_response(model_instance, protocol, semaphore))
    
    # 等待所有提取任务完成
    time_results = await asyncio.gather(*tasks)
    
    # 汇总结果
    results = []
    for i, resp in enumerate(responses):
        qid = resp.get('question_id')
        time_data = time_results[i]
        if time_data and qid in scores_map:
            results.append({
                "question_id": qid,
                "fixation_time": time_data.get('fixation_time_hours', 0),
                "clearing_time": time_data.get('clearing_time_hours', 0),
                "total_transparency_time": time_data.get('fixation_time_hours', 0) + time_data.get('clearing_time_hours', 0),
                "s_label": scores_map[qid]
            })
            
    return model_name, results

async def main():
    """
    主函数：加载模型并并行处理所有模型的数据
    """
    loader = ModelLoader(CONFIG_PATH)
    models = loader.load_models()
    if EXTRACTOR_MODEL_NAME not in models:
        print(f"配置文件中未找到提取模型: {EXTRACTOR_MODEL_NAME}")
        return
    
    extractor = models[EXTRACTOR_MODEL_NAME]
    semaphore = asyncio.Semaphore(SEM_LIMIT)
    
    all_data = {}
    
    # 自动匹配回答文件和评分结果文件
    model_files = []
    for filename in os.listdir(RESPONSE_DIR):
        if filename.startswith('from_') and filename.endswith('.json'):
            model_id = filename[len('from_'):-len('.json')]
            response_file = os.path.join(RESPONSE_DIR, filename)
            score_file = os.path.join(SCORE_DIR, f'evaluation_results_{model_id}.json')
            model_files.append((model_id, response_file, score_file))
    
    # 处理所有模型
    tasks = []
    for model_id, res_file, sc_file in model_files:
        tasks.append(process_model(model_id, res_file, sc_file, extractor, semaphore))
        
    model_results = await asyncio.gather(*tasks)
    
    for model_id, results in model_results:
        all_data[model_id] = results
        
    # 保存聚合后的数据，供绘图程序使用
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
        
    print(f"数据收集完成。已保存至 {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
