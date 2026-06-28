import json
import re
import os

# 核心步骤关键词（用于判断某行是否属于统计范围）
CORE_STEP_KEYWORDS = [
    "delipid", "脱脂",
    "decalcif", "脱钙",
    "decolor", "脱色", "漂白", "bleach", "bleaching",
    "refractive index", "ri match", "折射率匹配", "ri匹配", "折射率",
    "clearing reagent", "透明化", "透明试剂",
    "脱水", "dehydrat",
    "水合", "rehydrat",
    "dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd",
]

# 排除步骤关键词
EXCLUDE_KEYWORDS = [
    "pfa", "固定", "fixation", "fix",
    "一抗", "primary antibody", "primary",
    "二抗", "secondary antibody", "secondary",
    "染色", "stain", "staining",
    "成像", "image", "imaging", "microscop",
    "封片", "mount", "mounting",
    "切片", "section", "sectioning",
    "灌注", "perfusion",
]

# 特别排除：常规PBS清洗（但试剂转换中的清洗不排除）
EXCLUDE_WASH_KEYWORDS = [
    "pbs 清洗", "pbs清洗", "pbs wash", "漂洗", "洗涤",
]


def _clean_text_for_time_parsing(text):
    """预处理文本，移除容易误匹配为时间的模式"""
    # 移除比例，如 1:500, 1:1000
    text = re.sub(r'\d+\s*:\s*\d+', '', text)
    # 移除浓度单位
    text = re.sub(r'\d+\s*(?:mg/mL|ug/mL|μg/mL|wt/vol|vol/vol|wt/vol|v/v|w/v)', '', text, flags=re.IGNORECASE)
    # 移除稀释关键词
    text = re.sub(r'dilution|diluted|minimum|maximum', '', text, flags=re.IGNORECASE)
    return text


def parse_time_to_hours(text):
    """从单个子步骤文本中提取所有时间并求和（小时）"""
    total = 0.0
    text = _clean_text_for_time_parsing(text)
    text_lower = text.lower()

    # 处理 overnight / 过夜
    if "overnight" in text_lower or "overnight (on)" in text_lower or "过夜" in text:
        total += 8.0

    # 处理范围，如 "5-7 days", "2-3 h", "1~2天", "5至7天"
    range_pattern = re.compile(
        r'(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*(h|hr|hour|hours|小时|天|day|days|min|minute|minutes|分钟)',
        re.IGNORECASE
    )
    for m in range_pattern.finditer(text):
        v1, v2, unit = float(m.group(1)), float(m.group(2)), m.group(3).lower()
        avg = (v1 + v2) / 2.0
        total += convert_unit(avg, unit)

    # 处理单一数值，但要排除已匹配的范围部分
    text_without_ranges = range_pattern.sub('', text)

    # 使用更严格的匹配：要求单位前后是单词边界或标点，避免 dilution 中的 d 被匹配
    single_pattern = re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:\b)(h|hr|hour|hours|小时|天|day|days|min|minute|minutes|分钟)(?:\b|[^a-zA-Z])',
        re.IGNORECASE
    )
    for m in single_pattern.finditer(text_without_ranges):
        val, unit = float(m.group(1)), m.group(2).lower()
        total += convert_unit(val, unit)

    return total if total > 0 else None


def convert_unit(val, unit):
    unit = unit.lower()
    if unit in ('min', 'minute', 'minutes', '分钟'):
        return val / 60.0
    elif unit in ('h', 'hr', 'hour', 'hours', '小时'):
        return val
    elif unit in ('day', 'days', '天'):
        return val * 24.0
    return val


def is_core_step(text):
    """判断该步骤是否属于透明化核心流程"""
    text_lower = text.lower()

    # 先检查排除项
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text_lower:
            return False

    # 特别排除常规清洗
    is_wash = any(kw in text_lower for kw in EXCLUDE_WASH_KEYWORDS)
    if is_wash:
        # 如果清洗步骤同时包含核心试剂名称，则视为试剂转换清洗，不排除
        has_core_reagent = any(kw in text_lower for kw in ["dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd", "甲醇", "乙醇", "meoh", "etoh"])
        if not has_core_reagent:
            return False

    # 检查是否包含核心步骤关键词
    for kw in CORE_STEP_KEYWORDS:
        if kw.lower() in text_lower:
            return True

    return False


def extract_clearing_time(protocol_text):
    """从完整 protocol 文本中提取透明化核心流程总耗时（小时）"""
    if not protocol_text:
        return None

    total_hours = 0.0
    has_valid_step = False

    # 按行分割，同时尝试识别子步骤（如 1.1, 2.1）
    lines = protocol_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_core_step(line):
            hours = parse_time_to_hours(line)
            if hours is not None:
                total_hours += hours
                has_valid_step = True

    return total_hours if has_valid_step else None


def process_model_file(filepath):
    """处理单个模型回答文件，返回 {question_id: hours} 的字典"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = {}
    for entry in data:
        qid = entry.get("question_id")
        protocol = entry.get("model_response", "")
        hours = extract_clearing_time(protocol)
        results[qid] = hours
    return results


def main():
    files = [
        "dataset/Q+AR/model_response/from_gemini-3-flash_1-shot.json",
        "dataset/Q+AR/model_response/from_gemini-3-pro_1-shot.json",
        "dataset/Q+AR/model_response/from_glm4.7-thinking_1-shot.json",
        "dataset/Q+AR/model_response/from_glm4.7-unthinking_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_claude-sonnet-4.6_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_deepseek-chat_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_deepseek-reasoner_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_gpt-5.2-fast_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_gpt-5.2-thinking_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_qwen3-14b_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_qwen3-32b_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_qwen3-235b_1-shot.json",
        "dataset/Q+AR/model_response/from_openai_qwen3-max_1-shot.json",
    ]

    all_results = {}
    model_names = []

    for fp in files:
        if not os.path.exists(fp):
            print(f"[SKIP] File not found: {fp}")
            continue
        model_name = os.path.basename(fp).replace("from_", "").replace("_1-shot.json", "")
        model_names.append(model_name)
        print(f"[PROCESSING] {model_name} ...")
        results = process_model_file(fp)
        all_results[model_name] = results
        valid_count = sum(1 for v in results.values() if v is not None)
        print(f"  -> Valid: {valid_count}/{len(results)}")

    # 保存为 JSON
    output_path = "dataset/Q+AR/model_response/clearing_time_stats.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_path}")

    # 输出统计摘要
    print("\n" + "="*80)
    print("SUMMARY: Average clearing time per model (hours)")
    print("="*80)
    for model_name in model_names:
        res = all_results.get(model_name, {})
        values = [v for v in res.values() if v is not None]
        if values:
            avg = sum(values) / len(values)
            min_v = min(values)
            max_v = max(values)
            median = sorted(values)[len(values)//2]
            print(f"{model_name:40s}  avg={avg:8.1f}  median={median:8.1f}  min={min_v:8.1f}  max={max_v:8.1f}  n={len(values)}")
        else:
            print(f"{model_name:40s}  NO DATA")


if __name__ == "__main__":
    main()
