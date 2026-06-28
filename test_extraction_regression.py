# 回归测试：确认修复不影响已有低缺失率模型的提取结果
from extract_clearing_time import extract_clearing_time
import json

models = ["openai_claude-sonnet-4.6", "openai_qwen3-14b", "openai_deepseek-reasoner", "gemini-3-flash"]

for model in models:
    path = f"dataset/Q+AR/model_response/from_{model}_1-shot.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n=== {model} ===")
    for e in data[:5]:
        h = extract_clearing_time(e["model_response"])
        print(f"  qid={e['question_id']}: {h}")
