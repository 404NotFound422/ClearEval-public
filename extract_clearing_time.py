import json
import re
import os

# 核心步骤关键词（用于判断某行是否属于统计范围）
CORE_STEP_KEYWORDS = [
    "delipid", "脱脂",
    "decalcif", "脱钙",
    "decolor", "脱色", "漂白", "bleach", "bleaching",
    "refractive index", "ri match", "ri 匹配", "折射率匹配", "ri匹配", "折射率",
    "clearing reagent", "透明化", "透明试剂", "optical clearing",
    "脱水", "dehydrat", "去脂",
    "水合", "rehydrat",
    "dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd", "seedb",
]

# 排除步骤关键词
EXCLUDE_KEYWORDS = [
    "pfa", "固定", "fixation", "fix",
    "一抗", "primary antibody", "primary",
    "二抗", "secondary antibody", "secondary",
    "染色", "stain", "staining",
    # "成像/封片" 常作为 RI 匹配后的用途描述出现，不在全局排除；
    # 真正的成像/封片章节通常不含核心透明化关键词，不会误识别。
    "sectioning", "perfusion", "灌注",
    # 注意："切片"被移除，因为透明化子步骤中常出现"将切片置于/浸入/洗涤"等操作描述；
    # 真正的切片制备操作通常由 "sectioning" 或上下文判断。
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
    text = _clean_text_for_time_parsing(text)
    text_lower = text.lower()

    # 优先处理 "(Temperature: ..., Time: X unit)" 格式，避免与行首的 "for X hour" 重复计数
    temp_time_pattern = re.compile(
        r'\(Temperature:[^)]*Time:\s*(\d+(?:\.\d+)?)\s*(?:[-~至到]\s*(\d+(?:\.\d+)?))?\s*'
        r'(h|hr|hour|hours|小时|天|day|days|min|minute|minutes|分钟)\s*\)',
        re.IGNORECASE,
    )
    m = temp_time_pattern.search(text)
    if m:
        v1 = float(m.group(1))
        v2 = m.group(2)
        unit = m.group(3).lower()
        if v2 is not None:
            val = (v1 + float(v2)) / 2.0
        else:
            val = v1
        return convert_unit(val, unit)

    total = 0.0

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
        has_core_reagent = any(kw in text_lower for kw in ["dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd", "seedb", "甲醇", "乙醇", "meoh", "etoh"])
        if not has_core_reagent:
            return False

    # 检查是否包含核心步骤关键词
    for kw in CORE_STEP_KEYWORDS:
        if kw.lower() in text_lower:
            # 对"去脂"增加上下文检查：若出现在"为后续去脂做准备/降低后续去脂"等
            # 目的说明中，不因此将预处理步骤误判为核心去脂步骤。
            if kw == "去脂":
                if re.search(r"(为|为了|后续|降低|促进).*去脂|去脂.*(与|和|抗体|进入|造成|准备)", text_lower):
                    continue
            return True

    return False


def extract_clearing_time(protocol_text):
    """从完整 protocol 文本中提取透明化核心流程总耗时（小时）"""
    if not protocol_text:
        return None

    total_hours = 0.0
    has_valid_step = False
    in_core_section = False

    # 用于识别子步骤：1.1 / (a) / (1) 等编号，或行首缩进
    substep_pattern = re.compile(r"^\s*(\d+\.\d+|\(\d+\)|\([a-zA-Z]\))")
    # 章节标题模式：如 "1 Dehydration"、"**1 Pre-treatment"、"1. Dehydration"、"1. **Pretreatment**"
    section_header_pattern = re.compile(
        r"^\s*(?:\*\*)?\d+(?:\.\s*|\s+)(?:\*\*)?\s*[A-Za-z\u4e00-\u9fff\(]",
        re.UNICODE,
    )
    # 在核心章节内排除非透明化子步骤时，允许“imaging/mount”等作为 RI 匹配后的用途描述，
    # 因此使用比全局 EXCLUDE_KEYWORDS 更窄的列表
    section_exclude_keywords = [
        kw for kw in EXCLUDE_KEYWORDS
        if kw.lower() not in ("image", "imaging", "microscop", "mount", "mounting")
    ]

    # 子步骤中需出现核心试剂或核心动作，才认为属于透明化流程
    core_reagents = ["dbb", "dbe", "babb", "eci", "rims", "scale", "cubic", "macs", "solid", "fdisco", "seebd", "seedb", "tde", "甲醇", "乙醇", "meoh", "etoh"]
    # 扩展：常见溶剂/脱水剂/透明试剂也视为核心试剂
    core_solvents = [
        "methanol", "ethanol", "dcm", "dichloromethane", "dbp",
        "benzyl alcohol", "benzyl benzoate", "tissue clearing", "optical clearing",
        "qudio", "uftf", "sucrose", "glycerol", "peg", "fructose",
    ]
    # 核心动作/阶段（含常见缩写、连字符变体）
    core_actions = [
        "dehydrat", "rehydrat", "delipid", "bleach", "bleaching", "decolor",
        "脱色", "漂白", "脱脂", "脱钙", "脱水", "去脂", "水合",
        "refractive index", "ri matching", "ri-matching", "ri match", "ri-match", "ri 匹配",
        "折射率", "clearing reagent", "透明化", "透明试剂",
    ]

    # 按行分割，同时尝试识别子步骤（如 1.1, 2.1）
    lines = protocol_text.split('\n')

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            # 核心章节内的空行通常只是格式间距，不立即退出核心章节模式，
            # 这样可兼容 "章节标题\n\n子步骤" 的排版。
            continue

        core = is_core_step(line)
        if core:
            hours = parse_time_to_hours(line)
            if hours is not None:
                total_hours += hours
                has_valid_step = True
                in_core_section = False
            elif section_header_pattern.match(line):
                # 该行是核心章节标题（如 "1 Dehydration"），进入子步骤收集模式
                in_core_section = True
            else:
                in_core_section = False
            continue

        if in_core_section:
            # 判断是否为当前章节下的子步骤
            is_substep = (
                substep_pattern.match(raw_line)
                or raw_line.startswith("  ")
                or raw_line.startswith("\t")
                or parse_time_to_hours(line) is not None
            )
            if is_substep:
                text_lower = line.lower()
                # 排除非透明化子步骤（固定、染色、抗体等）；成像/封片词允许作为 RI 匹配用途描述
                excluded = any(kw.lower() in text_lower for kw in section_exclude_keywords)
                # 排除不含核心试剂的常规清洗
                is_plain_wash = (
                    any(kw in text_lower for kw in EXCLUDE_WASH_KEYWORDS)
                    and not any(kw in text_lower for kw in core_reagents)
                    and not any(kw in text_lower for kw in core_solvents)
                )
                # 子步骤需与透明化相关：包含核心试剂、核心溶剂或核心动作关键词。
                # 对于已确认的核心章节，子步骤若非明确的非透明化操作（固定、染色、抗体、
                # 常规清洗），即视为该核心流程的一部分，不再额外要求每行都含核心关键词。
                has_core_context = (
                    any(kw in text_lower for kw in core_reagents)
                    or any(kw in text_lower for kw in core_solvents)
                    or any(kw in text_lower for kw in core_actions)
                )
                if not excluded and not is_plain_wash and (has_core_context or in_core_section):
                    hours = parse_time_to_hours(line)
                    if hours is not None:
                        total_hours += hours
                        has_valid_step = True
            else:
                # 非子步骤行，结束当前核心章节
                in_core_section = False

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
