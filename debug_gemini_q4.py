"""
分析 gemini-3-flash qid=4 提取变化原因。
"""
import json
import re
from extract_clearing_time import extract_clearing_time, is_core_step, parse_time_to_hours, EXCLUDE_KEYWORDS, EXCLUDE_WASH_KEYWORDS

path = "dataset/Q+AR/model_response/from_gemini-3-flash_1-shot.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

entry = next(e for e in data if e["question_id"] == 4)
protocol = entry["model_response"]

out_path = "results/clearing_time_analysis/debug_gemini_q4.txt"
substep_pattern = re.compile(r"^\s*(\d+\.\d+|\(\d+\)|\([a-zA-Z]\))")
section_header_pattern = re.compile(
    r"^\s*(?:\*\*)?\d+(?:\.\s+|\s+|\.)[A-Za-z\u4e00-\u9fff]",
    re.UNICODE,
)
action_words = ["incubation", "incubate", "wash", "rinse", "place", "immerse", "equilibrate"]
core_reagents = ["dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd", "甲醇", "乙醇", "meoh", "etoh"]

with open(out_path, "w", encoding="utf-8") as out:
    out.write(f"Extracted hours: {extract_clearing_time(protocol)}\n\n")
    out.write("Line-by-line analysis:\n")
    lines = protocol.split("\n")
    in_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            in_section = False
            continue
        core = is_core_step(line)
        t = parse_time_to_hours(line)
        if core:
            if t is not None:
                in_section = False
                out.write(f"[CORE+t]  t={t} | {line}\n")
            elif section_header_pattern.match(line):
                in_section = True
                out.write(f"[SECTION] {line}\n")
            else:
                in_section = False
                out.write(f"[CORE-]   {line}\n")
            continue

        if in_section:
            is_substep = (
                substep_pattern.match(raw_line)
                or raw_line.startswith("  ")
                or raw_line.startswith("\t")
                or (t is not None and any(w in line.lower() for w in action_words))
            )
            if is_substep and t is not None:
                text_lower = line.lower()
                excluded = any(kw.lower() in text_lower for kw in EXCLUDE_KEYWORDS)
                is_plain_wash = (
                    any(kw in text_lower for kw in EXCLUDE_WASH_KEYWORDS)
                    and not any(kw in text_lower for kw in core_reagents)
                )
                if excluded:
                    out.write(f"[SUB-ex]  t={t} | {line}\n")
                elif is_plain_wash:
                    out.write(f"[SUB-pw]  t={t} | {line}\n")
                else:
                    out.write(f"[SUB+t]   t={t} | {line}\n")
            elif is_substep:
                out.write(f"[SUB]     {line}\n")
            else:
                in_section = False
                out.write(f"[ENDSEC]  {line}\n")

print(f"Debug output written to {out_path}")
