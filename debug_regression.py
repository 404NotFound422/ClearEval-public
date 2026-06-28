"""
对比修复前后对 openai_claude-sonnet-4.6 qid=1 的提取差异。
"""
import json
from extract_clearing_time import extract_clearing_time, is_core_step, parse_time_to_hours

path = "dataset/Q+AR/model_response/from_openai_claude-sonnet-4.6_1-shot.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

entry = next(e for e in data if e["question_id"] == 1)
protocol = entry["model_response"]

out_path = "results/clearing_time_analysis/debug_regression_claude_q1.txt"
with open(out_path, "w", encoding="utf-8") as out:
    out.write(f"Extracted hours: {extract_clearing_time(protocol)}\n\n")
    out.write("Line-by-line analysis:\n")
    lines = protocol.split("\n")
    in_section = False
    substep_pattern = __import__("re").compile(r"^\s*(\d+\.\d+|\(\d+\)|\([a-zA-Z]\))")
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            in_section = False
            continue
        core = is_core_step(line)
        t = parse_time_to_hours(line)
        is_substep = (
            substep_pattern.match(raw_line)
            or raw_line.startswith("  ")
            or raw_line.startswith("\t")
            or (parse_time_to_hours(line) is not None
                and any(w in line.lower() for w in ["incubation", "incubate", "wash", "rinse", "place", "immerse", "equilibrate"]))
        )
        if core:
            if t is None:
                in_section = True
                out.write(f"[SECTION] {line}\n")
            else:
                in_section = False
                out.write(f"[CORE+t]  t={t} | {line}\n")
        elif in_section and is_substep and t is not None:
            out.write(f"[SUB+t]   t={t} | {line}\n")

print(f"Debug output written to {out_path}")
