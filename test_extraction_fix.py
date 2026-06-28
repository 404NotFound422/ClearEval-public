# 临时复现/验证脚本：glm4.7-thinking question_id=1 修复前后对比
from extract_clearing_time import extract_clearing_time
import json

with open("dataset/Q+AR/model_response/from_glm4.7-thinking_1-shot.json", "r", encoding="utf-8") as f:
    data = json.load(f)

entry = next(e for e in data if e["question_id"] == 1)
hours = extract_clearing_time(entry["model_response"])
print(f"question_id=1 extracted hours: {hours}")
assert hours is not None and hours > 0, "修复后应返回正数"
