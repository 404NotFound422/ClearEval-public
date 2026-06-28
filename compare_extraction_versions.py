"""
比较原始提取逻辑与修复后的提取逻辑在各模型上的表现。
"""
import json
import sys

# 动态加载两个版本的模块
import importlib.util

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

original = load_module("extract_clearing_time_original.py", "original")
fixed = load_module("extract_clearing_time.py", "fixed")

models = [
    "gemini-3-flash",
    "gemini-3-pro",
    "glm4.7-thinking",
    "glm4.7-unthinking",
    "openai_claude-sonnet-4.6",
    "openai_deepseek-chat",
    "openai_deepseek-reasoner",
    "openai_gpt-5.2-fast",
    "openai_gpt-5.2-thinking",
    "openai_qwen3-14b",
    "openai_qwen3-32b",
    "openai_qwen3-235b",
    "openai_qwen3-max",
]

out_path = "results/clearing_time_analysis/extraction_comparison.csv"
with open(out_path, "w", encoding="utf-8-sig") as out:
    out.write("model,question_id,original_hours,fixed_hours,diff\n")
    for model in models:
        path = f"dataset/Q+AR/model_response/from_{model}_1-shot.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        changes = 0
        for e in data:
            qid = e["question_id"]
            o = original.extract_clearing_time(e["model_response"])
            f_ = fixed.extract_clearing_time(e["model_response"])
            if (o is None) != (f_ is None) or (o is not None and f_ is not None and abs(o - f_) > 0.001):
                changes += 1
            out.write(f"{model},{qid},{o if o is not None else ''},{f_ if f_ is not None else ''},{(f_-o) if o is not None and f_ is not None else ''}\n")
        print(f"{model}: {changes}/253 changed")

print(f"\nDetailed comparison written to {out_path}")
