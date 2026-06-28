"""
查看 qwen3-14b qid=1 的 protocol，判断 75h 是否合理。
"""
import json
from extract_clearing_time import extract_clearing_time

path = "dataset/Q+AR/model_response/from_openai_qwen3-14b_1-shot.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

entry = next(e for e in data if e["question_id"] == 1)
protocol = entry["model_response"]

out_path = "results/clearing_time_analysis/inspect_qwen_q1.txt"
with open(out_path, "w", encoding="utf-8") as out:
    out.write(f"Extracted hours: {extract_clearing_time(protocol)}\n\n")
    out.write(protocol)

print(f"Written to {out_path}")
