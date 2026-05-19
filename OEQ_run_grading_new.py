"""
代码目的：
该脚本旨在自动化组织透明化方案的生成与评分流程。它通过读取预设的问题集、限制条件和标准回答样例，构建Prompt输入给被测模型列表中的每一个模型，收集模型生成的实验方案，然后调用“教师模型”（通常也是高能力模型，如 GPT-4o 或 Gemini 3）根据详细的评分标准（Rubric）对生成的方案进行多维度的评分和点评。

处理步骤：
1. 加载配置：使用 `ModelLoader` 从 `config/config.yaml` 加载所有可用模型的配置。
2. 加载数据：
   - 从 `dataset/Q+AR/src/restrict.py` 加载限制条件。
   - 从 `dataset/Q+AR/src/questions.json` 加载测试问题。
   - 从 `dataset/Q+AR/src/standard_response.json` 加载标准回答样例。
3. 定义测试模型列表和教师模型。
4. 遍历测试模型列表：
   - 对每个模型，遍历所有问题，构建 Prompt。
   - 调用该模型获取回答。
   - 将回答保存为 `dataset/Q+AR/model_response/from_{model_name}.json`。
5. 遍历收集到的模型回答文件：
   - 调用教师模型，根据 Rubric 对回答进行评分。
   - 将评分结果保存为 `result/evaluation_results_{model_name}.json`。

输入：
- `config/config.yaml`: 配置文件，包含所有模型配置。
- `dataset/Q+AR/src/restrict.py`: 限制条件。
- `dataset/Q+AR/src/questions.json`: 问题列表。
- `dataset/Q+AR/src/standard_response.json`: 标准回答样例。
- `dataset/Q+AR/src/model_space.json`: 透明方法向量空间。
- `prompts/eval_teacher_protocol_review.py`: 评分标准 Prompt。

输出：
- `dataset/Q+AR/model_response/from_{model_name}.json`: 各个被测模型的回答。
- `result/evaluation_results_{model_name}.json`: 各个被测模型的评分结果。
"""

import json,datetime
import os
import re
import sys
import importlib.util
import asyncio
import numpy as np
import math
from models.Model_Loader import ModelLoader
from prompts.gen_protocol_template import TEST_MODEL_GENERATION_PROMPT
from prompts.parse_user_preference_vector import USER_PREFERENCE_PROMPT

OEQ_OUTPUT_DIR = 'dataset/Q+AR/model_response'
OEQ_SCORE_DIR = 'dataset/Q+AR/result'

# -------------------------------------------------------------------------
# Load KnowledgeBase for rule-based scoring
# -------------------------------------------------------------------------
with open('KnowledgeBase/tissue.json', 'r', encoding='utf-8') as f:
    TISSUE_KB = json.load(f)
with open('KnowledgeBase/method_fluro_compati.json', 'r', encoding='utf-8') as f:
    METHOD_FLUORO_KB = json.load(f)
with open('KnowledgeBase/time_kb.json', 'r', encoding='utf-8') as f:
    _TIME_KB_RAW = json.load(f)
with open('KnowledgeBase/method_time_tau.json', 'r', encoding='utf-8') as f:
    _TIME_TAU_RAW = json.load(f)
with open('KnowledgeBase/tissue_ri.json', 'r', encoding='utf-8') as f:
    _TISSUE_RI_RAW = json.load(f)
with open('KnowledgeBase/method_sigma_ri.json', 'r', encoding='utf-8') as f:
    _SIGMA_RI_RAW = json.load(f)
with open('KnowledgeBase/method_ri_ref.json', 'r', encoding='utf-8') as f:
    _METHOD_RI_REF_RAW = json.load(f)
# Question metadata (loaded once at startup; avoids per-call file I/O)
with open('dataset/Q+AR/src/question_final.json', 'r', encoding='utf-8') as f:
    _QUESTION_LIST = json.load(f)

# Flatten tissue_ri.json into a single tissue_key → RI table
_DEFAULT_TISSUE_RI: float = float(_TISSUE_RI_RAW["tissue_ri_database"].get("default_ri", 1.48))
_TISSUE_RI_TABLE: dict = {}
for _cat, _items in _TISSUE_RI_RAW["tissue_ri_database"]["tissues"].items():
    for _k, _v in _items.items():
        if _k != "note" and isinstance(_v, (int, float)):
            _TISSUE_RI_TABLE[_k] = float(_v)


def _resolve_tissue_ri(tissue_inferred: str) -> float:
    """Map Chinese tissue_inferred label → tissue native RI by keyword priority.

    Priority order: brain-context tumor → compound muscle → hard tissue →
    muscle/skin → visceral → neural/special. Falls back to default 1.48.
    """
    if not tissue_inferred:
        return _DEFAULT_TISSUE_RI
    s = tissue_inferred

    if "脑" in s and ("肿瘤" in s or "乳腺癌" in s or "转移" in s):
        return _TISSUE_RI_TABLE["brain_tumor"]
    if "骨骼肌" in s or "腓肠肌" in s or "椎旁肌" in s:
        return _TISSUE_RI_TABLE["skeletal_muscle"]
    if "牙" in s: return _TISSUE_RI_TABLE["tooth"]
    if "颅骨" in s or "股骨" in s or "骨髓" in s or "骨" in s: return _TISSUE_RI_TABLE["bone"]
    if "耳蜗" in s: return _TISSUE_RI_TABLE["cochlea"]
    if "皮肤" in s: return _TISSUE_RI_TABLE["skin"]
    if "心" in s: return _TISSUE_RI_TABLE["heart"]
    if "肌" in s: return _TISSUE_RI_TABLE["skeletal_muscle"]
    if "黑色素瘤" in s: return _TISSUE_RI_TABLE["melanoma"]
    if "石蜡" in s: return _TISSUE_RI_TABLE["tumor_paraffin"]
    if "淋巴结" in s: return _TISSUE_RI_TABLE["lymph_node"]
    if "乳腺癌" in s: return _TISSUE_RI_TABLE["breast_cancer"]
    if "前列腺" in s: return _TISSUE_RI_TABLE["prostate"]
    if "肝" in s: return _TISSUE_RI_TABLE["liver"]
    if "肾" in s: return _TISSUE_RI_TABLE["kidney"]
    if "脾" in s: return _TISSUE_RI_TABLE["spleen"]
    if "胰" in s: return _TISSUE_RI_TABLE["pancreas"]
    if "胎盘" in s: return _TISSUE_RI_TABLE["placenta"]
    if "胃" in s: return _TISSUE_RI_TABLE["stomach"]
    if "肠" in s and "类器官" not in s: return _TISSUE_RI_TABLE["intestine"]
    if "肺" in s: return _TISSUE_RI_TABLE["lung"]
    if "睾丸" in s: return _TISSUE_RI_TABLE["testis"]
    if "脂肪" in s: return _TISSUE_RI_TABLE["fat"]
    if "肿瘤" in s: return _TISSUE_RI_TABLE["tumor_dense"]
    if "全身" in s: return _TISSUE_RI_TABLE["kidney"]  # whole-body soft-tissue default
    if "类器官" in s or "果蝇" in s: return _TISSUE_RI_TABLE["organoid"]
    if "elegans" in s.lower(): return _TISSUE_RI_TABLE["celegans"]
    if "E14" in s: return _TISSUE_RI_TABLE["embryo_brain"]
    if "胚胎" in s: return _TISSUE_RI_TABLE["embryo_whole"]
    if "人脑" in s: return _TISSUE_RI_TABLE["human_brain_block"]
    if "海马" in s: return _TISSUE_RI_TABLE["hippocampus_ca1"]
    if "视网膜" in s or "眼球" in s: return _TISSUE_RI_TABLE["eye_retina"]
    if "脊髓" in s or "CNS" in s: return _TISSUE_RI_TABLE["spinal_cord"]
    if "斑马鱼" in s: return _TISSUE_RI_TABLE["zebrafish"]
    if "脑" in s: return _TISSUE_RI_TABLE["whole_brain"]
    if "植物" in s or "拟南芥" in s: return _TISSUE_RI_TABLE["plant"]
    return _DEFAULT_TISSUE_RI


# Question ID → metadata precomputed once. Used by process_model (write-time) and
# evaluate_response_with_teacher (backfill path for legacy entries lacking these fields).
QUESTION_META_KB: dict = {
    q["question_id"]: {
        "tissue_tier_code":     q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_tier_code", ""),
        "tissue_inferred":      q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_inferred", ""),
        "tissue_ri_value":      _resolve_tissue_ri(q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_inferred", "")),
        "marker_query_targets": q.get("marker_query_targets", []),
    }
    for q in _QUESTION_LIST
}

def _strip_markdown_fences(text: str) -> str:
    """Strip ```json / ```JSON / leading-whitespace fences from LLM output.
    Also attempts to isolate the first JSON object/array if the LLM wrapped it
    in explanatory prose (e.g. 'Here is the JSON: {...}').
    Uses bracket-matching to avoid grabbing trailing prose that happens to contain }.
    """
    if not text:
        return ""
    s = text.strip()
    import re
    # Remove leading fence
    m = re.match(r"^[`~]{3}\s*[jJ][sS][oO][nN]?\s*\n?", s)
    if m:
        s = s[m.end():]
    # Remove trailing fence
    s = re.sub(r"\n?[`~]{3}\s*$", "", s)
    s = s.strip()
    # If there's still surrounding prose, use bracket-matching to extract JSON
    m_start = re.search(r"[\{\[]", s)
    if m_start:
        start_idx = m_start.start()
        bracket = s[start_idx]
        end_bracket = "}" if bracket == "{" else "]"
        depth = 0
        end_idx = None
        for i, ch in enumerate(s[start_idx:], start=start_idx):
            if ch == bracket:
                depth += 1
            elif ch == end_bracket:
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx is not None:
            s = s[start_idx:end_idx + 1]
    return s.strip()


def _coerce_str(val, default: str = "") -> str:
    """Return val as str, or default if None/empty/non-stringable."""
    if val is None:
        return default
    try:
        s = str(val).strip()
        return s if s else default
    except Exception:
        return default


def _coerce_float(val, default: float = 0.0) -> float:
    """Return val as float, or default if None/non-numeric. Handles "1.48" string from LLM."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _normalize_name(name):
    """归一化名称：小写、去空格、去常见连字符"""
    if not name:
        return ""
    s = str(name).lower()
    for ch in " -_–—/\\":
        s = s.replace(ch, "")
    return s


def _extract_parenthetical(name):
    """提取括号内的缩写，如 'β-III Tubulin (TUJ1)' -> ['tuj1']"""
    import re
    matches = re.findall(r'\(([^)]+)\)', str(name))
    return [_normalize_name(m) for m in matches]


def _map_fluor_to_tissue_col(fluor_name):
    """将大模型返回的荧光团名称映射到 tissue.json 的列名"""
    s = _normalize_name(fluor_name)
    # 先按空格分割，取第一个词尝试精确匹配
    first_word = s.split()[0] if s else ""
    mapping = {
        "gfp": "GFP/YFP", "egfp": "GFP/YFP", "yfp": "GFP/YFP",
        "tdtomato": "tdTomato/RFP ", "rfp": "tdTomato/RFP ", "mcherry": "tdTomato/RFP ", "mrfp": "tdTomato/RFP ",
        "dapi": "DAPI/Hoechst", "hoechst": "DAPI/Hoechst",
        "pi": "PI/Draq5 ", "draq5": "PI/Draq5 ",
        "alexafluor488": "AlexaFluor 488", "alexa488": "AlexaFluor 488",
        "alexafluor568": "AlexaFluor 568/Cy3", "alexa568": "AlexaFluor 568/Cy3", "cy3": "AlexaFluor 568/Cy3",
        "alexafluor647": "AlexaFluor 647/Cy5 ", "alexa647": "AlexaFluor 647/Cy5 ", "cy5": "AlexaFluor 647/Cy5 ",
        "cd31": "CD31", "lectin": "Lectin",
    }
    # 尝试完整匹配
    if s in mapping:
        return mapping[s]
    # 尝试前缀匹配
    for k, v in mapping.items():
        if s.startswith(k) or k in s:
            return v
    return None


def _map_fluor_to_method_key(fluor_name):
    """将大模型返回的荧光团名称映射到 method_fluro_compati.json 的键名"""
    s = _normalize_name(fluor_name)
    mapping = {
        "gfp": "GFP", "egfp": "EGFP", "yfp": "YFP",
        "tdtomato": "tdTomato", "rfp": "RFP", "mcherry": "mCherry", "mrfp": "mRFP",
        "alexafluor": "Alexa Fluor", "alexa": "Alexa Fluor",
        "dapi": "DAPI", "hoechst": "Hoechst",
        "pi": "Propidium iodide", "propidiumiodide": "Propidium iodide",
        "draq5": "TO-PRO-3", "topro3": "TO-PRO-3",
        "dii": "DiI", "dio": "DiO", "did": "DiD",
        "phalloidin": "Phalloidin", "alphabungarotoxin": "alpha-bungarotoxin",
        "lectin": "Lectin", "ib4": "IB4",
        "scrirenaissance2200": "SCRI Renaissance 2200",
    }
    if s in mapping:
        return mapping[s]
    for k, v in mapping.items():
        if s.startswith(k) or k in s:
            return v
    return None


def _match_marker_to_targets(marker_name, marker_query_targets):
    """检查 marker_name 是否与 marker_query_targets 中任一 marker_name 匹配"""
    norm_marker = _normalize_name(marker_name)
    norm_abbreviations = _extract_parenthetical(marker_name)
    for target in marker_query_targets:
        target_name = target.get("marker_name", "")
        norm_target = _normalize_name(target_name)
        target_abbrevs = _extract_parenthetical(target_name)
        # 直接匹配
        if norm_marker == norm_target:
            return True
        # 缩写匹配
        if norm_marker in target_abbrevs or norm_target in norm_abbreviations:
            return True
        # 子串匹配（容忍部分差异）
        if norm_marker in norm_target or norm_target in norm_marker:
            # 避免过短的子串误匹配（如 'a' in 'map2'）
            if len(norm_marker) >= 3 and len(norm_target) >= 3:
                return True
    return False


def _get_tissue_major_category(marker_name):
    """根据标记位点名称查找 tissue.json 对应的大类"""
    row = _tissue_by_marker.get(_normalize_name(marker_name))
    if row:
        return row.get("大类", "")
    # 尝试用子串/缩写再次查找
    norm = _normalize_name(marker_name)
    abbrevs = _extract_parenthetical(marker_name)
    for key, row in _tissue_by_marker.items():
        if norm in key or key in norm:
            if len(norm) >= 3 and len(key) >= 3:
                return row.get("大类", "")
        for abbr in abbrevs:
            if abbr in key:
                return row.get("大类", "")
    return ""


def _get_marker_fluor_compat(marker_name, fluor_name):
    """从 tissue.json 查标记位点-荧光团兼容性。返回 True(兼容)/False(不兼容)/None(未知)"""
    row = _tissue_by_marker.get(_normalize_name(marker_name))
    if not row:
        # 再次尝试模糊查找
        norm = _normalize_name(marker_name)
        for key, r in _tissue_by_marker.items():
            if norm in key or key in norm:
                if len(norm) >= 3 and len(key) >= 3:
                    row = r
                    break
    if not row:
        return None
    col = _map_fluor_to_tissue_col(fluor_name)
    if not col:
        return None
    val = row.get(col)
    if val == 0:
        return False
    # 值为 1 或缺失均视为兼容
    return True


def _get_method_fluor_compat(method_name, fluor_name):
    """从 method_fluro_compati.json 查荧光团-方法兼容性评分 (0~1)。未找到返回 None"""
    row = None
    norm_method = _normalize_name(method_name)
    # 精确或部分匹配 method
    for key, r in _method_fluoro_by_method.items():
        if norm_method == key or norm_method in key or key in norm_method:
            row = r
            break
    if not row:
        return None
    key = _map_fluor_to_method_key(fluor_name)
    if not key:
        return None
    val = row.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# -------------------------------------------------------------------------
# Build lookup indexes (after helper functions are defined)
# -------------------------------------------------------------------------
_tissue_by_marker = {}
for row in TISSUE_KB:
    for key in ["推荐标志物 1", "推荐标志物 2"]:
        val = row.get(key)
        if val:
            _tissue_by_marker[_normalize_name(val)] = row

_method_fluoro_by_method = {}
for row in METHOD_FLUORO_KB:
    method = row.get("method", "")
    if method:
        _method_fluoro_by_method[_normalize_name(method)] = row

# 构建 time_kb 查询索引：{normalize(method): {tier_code: {...}}}
TIME_KB_LOOKUP: dict = {}
for _method_key, _tiers in _TIME_KB_RAW.get("lookup", {}).items():
    TIME_KB_LOOKUP[_normalize_name(_method_key)] = _tiers

# 构建 τ 查询索引：{normalize(method): {tier_code: tau_hours}}
TIME_TAU_KB: dict = {}
for _method_key, _tiers in _TIME_TAU_RAW.get("tau", {}).items():
    TIME_TAU_KB[_normalize_name(_method_key)] = _tiers

# 构建 σ_RI 查询索引：{normalize(method): {tier_code: sigma}}
SIGMA_RI_KB: dict = {}
for _method_key, _tiers in _SIGMA_RI_RAW.get("sigma_RI", {}).items():
    SIGMA_RI_KB[_normalize_name(_method_key)] = _tiers

# 构建 RI_ref 查询索引：{normalize(method): ri_ref_float}
# RI_ref = native RI of the sample type each method was designed for (NOT reagent RI)
METHOD_RI_REF_KB: dict = {
    _normalize_name(_k): float(_v["ri"])
    for _k, _v in _METHOD_RI_REF_RAW.get("ri_ref", {}).items()
}


def _is_valid_response(text: str) -> bool:
    """Return True if the model response appears to be a real protocol, not an empty/error string."""
    if text is None:
        return False
    s = str(text).strip()
    if not s:
        return False
    # Heuristic: very short responses are likely errors or refusals
    if len(s) < 20:
        return False
    # Heuristic: if the response starts with common error indicators
    lower = s.lower()
    if lower.startswith(("error", "internal server error", "rate limit", "timeout",
                         "bad gateway", "service unavailable", "connection error",
                         "sorry", "i'm sorry")):
        return False
    return True


def load_prompt_method_generate():
    """
    动态加载评分 Prompt。
    """
    prompt_path = 'prompts/eval_teacher_protocol_review.py'
    try:
        spec = importlib.util.spec_from_file_location("prompt_method_generate", prompt_path)
        prompt_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prompt_module)
        return prompt_module.prompt
    except Exception as e:
        print(f"加载评分Prompt出错: {e}")
        return ""

def load_restrictions():
    """
    方法目的及步骤：
    动态加载 Python 配置文件中的限制条件。
    """
    restrict_path = 'dataset/Q+AR/src/restrict.py'
    try:
        spec = importlib.util.spec_from_file_location("restrict", restrict_path)
        restrict_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(restrict_module)
        return restrict_module.DEFAULT_RESTRICT
    except Exception as e:
        print(f"加载限制条件出错: {e}")
        return {}

def load_data():
    """
    方法目的及步骤：
    加载问题集、标准回答样例数据集和方法空间数据。
    """
    with open('dataset/Q+AR/src/question_final.json', 'r', encoding='utf-8') as f:
        questions = json.load(f)
    with open('dataset/Q+AR/src/standard_response.json', 'r', encoding='utf-8') as f:
        standard_responses = json.load(f)
    with open('dataset/Q+AR/src/model_space.json', 'r', encoding='utf-8') as f:
        model_space = json.load(f)
    return questions, standard_responses, model_space

def generate_model_prompt(question, restrictions, standard_responses=None, shot_type="1-shot"):
    """
    方法目的及步骤：
    构建发送给被测模型的 Prompt 字符串。
    使用 prompts/gen_protocol_template.py 中的 TEST_MODEL_GENERATION_PROMPT 模板，
    并将 dataset/Q+AR/src/restrict.py 中的限制条件格式化填入。
    
    Args:
        question (dict): 当前处理的问题对象。
        restrictions (dict): 限制条件字典（来自 load_restrictions() 加载的 DEFAULT_RESTRICT）。
        standard_responses (list): 标准回答列表（已废弃，保留参数以兼容调用方）。
        shot_type (str): "0-shot" 或 "1-shot"（已废弃，模板已内置 1-shot 示例）。
    """
    # 格式化限制条件（DEFAULT_RESTRICT 的值是 set，里面包着一个顿号分隔的字符串）
    restrict_lines = []
    for key, value in restrictions.items():
        if isinstance(value, set):
            # set 中通常只有一个字符串元素
            value_str = next(iter(value))
        else:
            value_str = str(value)
        restrict_lines.append(f"{key}:{{{value_str}}}")
    restrict_str = "\n".join(restrict_lines)
    
    # 使用模板并替换占位符
    prompt = TEST_MODEL_GENERATION_PROMPT.replace("[specific_question]", question['question'])
    prompt = prompt.replace("{{restrictions}}", restrict_str)
    
    return prompt

async def get_model_response(model_instance, prompt):
    try:
        response_data = await model_instance._acall(prompt)
        return response_data.get("content", "")
    except Exception as e:
        print(f"获取模型回答出错: {e}")
        return ""

async def get_user_preference_vector(teacher_model, question_text):
    """
    利用 Teacher Model 生成用户偏好向量
    """
    prompt = USER_PREFERENCE_PROMPT.replace("{user_text}", question_text)
    try:
        response_data = await teacher_model._acall(prompt)
        # Defensive: some APIs may return {"content": null} instead of missing key
        raw_content = response_data.get("content", "") if response_data else ""
        content = (raw_content or "").strip()
        # 清理 Markdown
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        
        data = json.loads(content.strip())
        return data.get("user_input_vectors", {})
    except Exception as e:
        print(f"获取用户偏好向量出错: {e}")
        return {}

def calculate_cosine_similarity(vec1, vec2):
    """
    计算两个向量的余弦相似度
    """
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)

def calculate_effectiveness_score(quantitative_data, user_pref_vector_dict, model_space, marker_dict, marker_query_targets):
    """
    计算有效性评分 E_score
    """
    # 权重
    w1, w2, w3, w4 = 1.0, 1.0, 1.0, 1.0
    
    # 1. S_method: 透明方法选择总体适配度
    method_name = _coerce_str(quantitative_data.get("method_name"), default="")

    # 查找 method_vector
    # model_space.json 结构: {"methods": {"CUBIC": {"F_fp": {"V": x, "W": y}, ...}, ...}}
    # 需要处理大小写或部分匹配
    method_vector_dict = {}
    found_method = False

    if method_name:  # Skip lookup entirely if LLM didn't extract a method name
        mn_low = method_name.lower()
        for key, val in model_space.get("methods", {}).items():
            kl = key.lower()
            # Require at least 3-char overlap to avoid empty-string false matches
            if (mn_low in kl or kl in mn_low) and min(len(mn_low), len(kl)) >= 3:
                method_vector_dict = val
                found_method = True
                break

    if not found_method:
        # 如果没找到，给一个默认低分或0分
        if method_name:
            print(f"Warning: Method '{method_name}' not found in model_space. Using default vector (0).")
        s_method = 0.0
    else:
        # 构建向量
        # 顺序: F_fp, P_dye, C_opt, M_geo, E_ops, S_safe
        # User Pref Map:
        # fluorescence_protein_preservation -> F_fp
        # dye_permeability -> P_dye
        # clearing_challenge -> C_opt
        # geometry_preference -> M_geo
        # operational_economy -> E_ops
        # safety_compatibility -> S_safe
        
        user_vec = []
        method_vec = []
        
        mapping = [
            ("fluorescence_protein_preservation", "F_fp"),
            ("dye_permeability", "P_dye"),
            ("clearing_challenge", "C_opt"),
            ("geometry_preference", "M_geo"),
            ("operational_economy", "E_ops"),
            ("safety_compatibility", "S_safe")
        ]
        
        for user_key, method_key in mapping:
            u_val = user_pref_vector_dict.get(user_key, {}).get("target", 0.0)
            m_val = method_vector_dict.get(method_key, {}).get("V", 0.0)
            user_vec.append(u_val)
            method_vec.append(m_val)
            
        cos_sim = calculate_cosine_similarity(user_vec, method_vec)
        s_method = 5 * cos_sim
        s_method = max(0.0, min(5.0, s_method)) # Clamp to [0, 5]

    # 2. S_label: 标记与方法兼容性评分 (Python 规则计算)
    # 步骤2.1: s_target_match — 标记位点与 question 要求的匹配度
    target_match_scores = []
    for fluor, marker in marker_dict.items():
        if not marker or not str(marker).strip():
            continue
        if _match_marker_to_targets(marker, marker_query_targets):
            target_match_scores.append(6.0)
        else:
            # 查 tissue.json 看是否同一大类
            marker_major = _get_tissue_major_category(marker)
            # 取 question 中第一个 target 的大类作为参考（通常同 question 的 targets 大类一致）
            question_major = ""
            if marker_query_targets:
                question_major = marker_query_targets[0].get("major_category", "")
            if marker_major and question_major and marker_major == question_major:
                target_match_scores.append(3.0)
            else:
                target_match_scores.append(0.0)
    s_target_match = min(target_match_scores) if target_match_scores else 0.0

    # 步骤2.2: s_marker_fluor_compat — 标记位点与荧光团兼容性 (tissue.json)
    marker_fluor_scores = []
    for fluor, marker in marker_dict.items():
        if not marker or not str(marker).strip():
            continue
        compat = _get_marker_fluor_compat(marker, fluor)
        if compat is False:
            marker_fluor_scores.append(0.0)
        else:
            # 兼容或未知均给满分（未知时不应 penalize）
            marker_fluor_scores.append(6.0)
    s_marker_fluor_compat = min(marker_fluor_scores) if marker_fluor_scores else 6.0

    # 步骤2.3: s_method_fluor_compat — 荧光团与透明方法兼容性 (method_fluro_compati.json)
    method_fluor_scores = []
    for fluor, marker in marker_dict.items():
        compat_val = _get_method_fluor_compat(method_name, fluor)
        if compat_val is None:
            method_fluor_scores.append(6.0)  # 未知时不 penalize
        else:
            method_fluor_scores.append(compat_val * 6.0)
    s_method_fluor_compat = min(method_fluor_scores) if method_fluor_scores else 6.0

    s_label = min(s_target_match, s_marker_fluor_compat, s_method_fluor_compat)
    s_label = max(0.0, min(6.0, s_label)) # Clamp to [0, 6]

    # Shared lookups for S_trans and S_time (method × sample tier)
    tier_code  = quantitative_data.get("sample_tier", "")
    method_key = _normalize_name(method_name)

    # 3. S_trans: 透明度有效性 (KB-based, method-domain matching)
    # 公式: S_trans = 3 * exp(-0.5 * ((RI_question_tissue - RI_method_ref) / σ_RI)²)
    # 语义: "the method's best-suited sample matches the question's tissue type"
    # RI_question_tissue → tissue_ri.json 按题目 tissue_inferred 查表（题目固定）
    # RI_method_ref      → method_ri_ref.json 按 method 查表（每个方法历史最适合样本的 RI）
    # σ_RI               → method_sigma_ri.json 按 (method, tier_code) 查表
    # 支持门控: 若 (method, tier_code) 不在 time_kb.json 的 lookup 中 → 0 分
    #          （例如 CUBIC 透明植物 T11、EyeCi 透明骨 T07）
    ri_tissue = quantitative_data.get("tissue_ri_value", 0.0)
    ri_method_ref = METHOD_RI_REF_KB.get(method_key)
    sigma_ri = SIGMA_RI_KB.get(method_key, {}).get(tier_code) if tier_code else None
    time_kb_supported = bool(TIME_KB_LOOKUP.get(method_key, {}).get(tier_code))

    if not time_kb_supported:
        # 方法不支持该样本尺度（time_kb 无该 method×tier 条目）→ 直接 0 分
        s_trans = 0.0
        _s_trans_sigma = sigma_ri
        _s_trans_status = "out_of_method_range"
    elif ri_method_ref is None or sigma_ri is None or float(sigma_ri) == 0.0 or not ri_tissue:
        # KB 数据缺失（方法不在 method_ri_ref.json 或 σ KB） → 0
        s_trans = 0.0
        _s_trans_sigma = sigma_ri
        _s_trans_status = "missing_kb"
    else:
        _s_trans_sigma = float(sigma_ri)
        exponent = -0.5 * ((float(ri_tissue) - float(ri_method_ref)) / _s_trans_sigma) ** 2
        s_trans = 3.0 * math.exp(exponent)
        s_trans = max(0.0, min(3.0, s_trans))
        _s_trans_status = "scored"

    # 4. S_time: 时间效率评分
    # 公式: S_time = 3 * exp(-0.5 * (Δt / τ)²)
    # t_min / t_max 来自 time_kb.json（方法×样本tier）
    # τ 来自 method_time_tau.json（τ = 0.20 × t_median，绝对小时值）
    # tier_code 由题目定义传入，不依赖 LLM 提取
    t_act = _coerce_float(quantitative_data.get("total_time_hours"), default=0.0)

    tier_data = TIME_KB_LOOKUP.get(method_key, {}).get(tier_code)
    tau_val   = TIME_TAU_KB.get(method_key, {}).get(tier_code)

    if tier_data is None or tau_val is None or float(tau_val) == 0.0:
        # 无 KB 条目（方法×tier 组合不支持）→ 得 0 分
        s_time = 0.0
        _s_time_t_min = _s_time_t_max = _s_time_tau = None
    elif t_act <= 0.0:
        # LLM 未抽到时间或抽到 0 → 无法评分 → 0
        s_time = 0.0
        _s_time_t_min = float(tier_data["clearing_time_min_h"])
        _s_time_t_max = float(tier_data["clearing_time_max_h"])
        _s_time_tau   = float(tau_val)
    else:
        _s_time_t_min = float(tier_data["clearing_time_min_h"])
        _s_time_t_max = float(tier_data["clearing_time_max_h"])
        _s_time_tau   = float(tau_val)

        if t_act < _s_time_t_min:
            delta_t = _s_time_t_min - t_act
        elif t_act > _s_time_t_max:
            delta_t = t_act - _s_time_t_max
        else:
            delta_t = 0.0

        if delta_t == 0.0:
            s_time = 3.0
        else:
            s_time = 3.0 * math.exp(-0.5 * (delta_t / _s_time_tau) ** 2)

    s_time = max(0.0, min(3.0, s_time))

    # 总分
    e_score = w1 * s_method + w2 * s_label + w3 * s_trans + w4 * s_time

    return {
        "s_method": s_method,
        "s_label": s_label,
        "s_trans": s_trans,
        "s_time": s_time,
        "total_effectiveness_score": e_score,
        "s_target_match": s_target_match,
        "s_marker_fluor_compat": s_marker_fluor_compat,
        "s_method_fluor_compat": s_method_fluor_compat,
        # 调试信息
        "_s_time_ref_source": "time_kb+tau_kb" if (tier_data and tau_val) else "missing_kb",
        "_s_time_t_min":  _s_time_t_min,
        "_s_time_t_max":  _s_time_t_max,
        "_s_time_tau":    _s_time_tau,
        "_s_time_t_act":  t_act,
        "_s_time_tier":   tier_code,
        # S_trans 调试信息
        "_s_trans_status":        _s_trans_status,
        "_s_trans_ri_tissue":     ri_tissue,
        "_s_trans_ri_method_ref": ri_method_ref,
        "_s_trans_sigma":         _s_trans_sigma,
    }

def _log_teacher_response(teacher_model_name, qid, prompt_len, raw_content, status, detail=""):
    """Append a structured log entry for every teacher-model call to enable post-hoc debugging.
    The FULL raw teacher response is persisted to a separate file so it can be inspected / replayed later."""
    import datetime
    log_dir = 'dataset/Q+AR/logs'
    raw_dir = os.path.join(log_dir, 'raw')
    os.makedirs(raw_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_filename = f'{teacher_model_name}_q{qid}_{ts}.txt'
    raw_path = os.path.join(raw_dir, raw_filename)

    # Persist the FULL raw teacher response for later audit / replay
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(raw_content if raw_content else "")

    log_path = os.path.join(log_dir, f'teacher_responses_{datetime.date.today().isoformat()}.jsonl')
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "teacher_model": teacher_model_name,
        "question_id": qid,
        "prompt_length": prompt_len,
        "raw_content_path": raw_path,
        "raw_content_preview": raw_content[:500] if raw_content else "",
        "raw_content_full_length": len(raw_content) if raw_content else 0,
        "status": status,   # "success", "json_parse_failed", "exception", "empty_content"
        "detail": detail,
    }
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


async def evaluate_response_with_teacher(teacher_model, question_text, model_protocol, model_space, question_meta, prompt_template):
    """
    方法目的及步骤：
    调用教师模型对生成的实验方案进行评分。
    步骤：
    1. 构建包含详细评分标准（Rubric）、问题文本和模型生成的方案的 Prompt。
    2. 调用教师模型实例进行评估。
    3. 解析返回的 JSON 字符串为字典。

    输入参数数据类型及说明：
    - teacher_model: 教师模型实例。
    - question_text (str): 原始问题文本。
    - model_protocol (str): 被测模型生成的实验方案文本。

    输出类型及说明：
    - (dict): 包含各项评分和评论的字典对象。
    """
    teacher_model_name = getattr(teacher_model, 'model_name', 'unknown_teacher')
    qid = question_meta.get('question_id')
    rubric_path = 'prompts/eval_oeq_teacher_rubric.txt'
    try:
        with open(rubric_path, 'r', encoding='utf-8') as f:
            rubric = f.read()
    except Exception as e:
        print(f"加载评分标准文件出错 ({rubric_path}): {e}")
        return {}
    # 辅助提取：尝试从 model_protocol 中提取声明的方法名
    method_name = "Unknown"
    m = re.search(r'(?:\*\*)?Chosen Method:\*?\s*([^\n]+)', model_protocol, re.IGNORECASE)
    if m:
        method_name = m.group(1).strip()

    # 辅助提取：尝试从 question_text 中提取样本尺寸描述
    sample_size = ""
    size_match = re.search(
        r'\d+\s*mm\s*[×xX]\s*\d+\s*mm\s*[×xX]\s*\d+\s*mm|'
        r'\d+[-–~]\d+\s*mm|'
        r'\d+\s*μm|'
        r'\d+\s*cm',
        question_text
    )
    if size_match:
        sample_size = size_match.group(0)

    # Enforce strict output format to prevent LLM from emitting flat/legacy JSON
    format_enforcement = (
        "\n[CRITICAL FORMAT RULE]\n"
        "Your ENTIRE response must be a SINGLE valid JSON object. "
        "Use the EXACT nested structure shown in the final example below. "
        "Do NOT output separate JSON blocks for each section. "
        "Do NOT put keys like C_step, Co_order, or marker_dict at the top level. "
        "They MUST be nested inside 'scores.completeness', 'scores.correctness', and 'extraction'.\n\n"
    )

    prompt = (
        rubric
        .replace("{{question_text}}", question_text)
        .replace("{{model_generated_protocol}}", model_protocol)
        .replace("{{method_name}}", method_name)
        .replace("{{sample_size}}", sample_size)
    )
    # Insert format enforcement just before the rubric sections begin
    prompt = prompt.replace("1. 完整性评估 Prompt (Completeness)", format_enforcement + "1. 完整性评估 Prompt (Completeness)")

    # Backfill question_meta from QUESTION_META_KB for legacy entries that lack the new fields.
    # All four fields (tissue_tier_code, tissue_inferred, tissue_ri_value, marker_query_targets)
    # come from question_final.json — fully reconstructible from question_id alone.
    qid = question_meta.get("question_id")
    kb_meta = QUESTION_META_KB.get(qid, {})
    if not question_meta.get("tissue_tier_code"):
        question_meta["tissue_tier_code"] = kb_meta.get("tissue_tier_code", "")
    if not question_meta.get("tissue_inferred"):
        question_meta["tissue_inferred"]  = kb_meta.get("tissue_inferred", "")
    if not question_meta.get("tissue_ri_value"):
        question_meta["tissue_ri_value"]  = kb_meta.get("tissue_ri_value", _DEFAULT_TISSUE_RI)
    if not question_meta.get("marker_query_targets"):
        question_meta["marker_query_targets"] = kb_meta.get("marker_query_targets", [])

    # 1. 获取 User Preference Vector
    user_pref_vector = await get_user_preference_vector(teacher_model, question_text)
    
    # # 2. 构建 Evaluation Prompt
    # prompt = prompt_template.replace("{{protocol_content}}", model_protocol)
    # prompt = prompt.replace("{{method_name}}", "Derived from protocol") # 让LLM自己判断
    # prompt = prompt.replace("{{sample_info}}", question_text) # 使用问题描述作为样本信息

    try:
        response_data = await teacher_model._acall(prompt)
        content = response_data.get("content", "").strip()

        # Guard against completely empty teacher responses
        if not content:
            _log_teacher_response(teacher_model_name, qid, len(prompt), "", "empty_content", "Teacher returned empty content string")
            return {
                "_error": "Teacher returned empty content",
                "_raw_content_preview": "",
                "_question_id": qid,
            }

        # 清理 Markdown — robust: handle ```json / ```JSON / leading whitespace
        content_stripped = _strip_markdown_fences(content)

        # Sanitize invalid \uXXXX escapes that some LLMs occasionally emit
        def _sanitize_unicode_escapes(s: str) -> str:
            """Replace malformed backslash-u escapes (e.g. \\u followed by fewer than 4 hex digits)
            with a placeholder to prevent json.JSONDecodeError."""
            def _fix_match(m):
                seq = m.group(1)
                if len(seq) == 4 and all(c in '0123456789abcdefABCDEF' for c in seq):
                    return m.group(0)  # valid escape, keep as-is
                return '\ufffd'  # replacement character for invalid escape
            return re.sub(r'\\u([0-9a-fA-F]{0,4})', _fix_match, s)

        content_sanitized = _sanitize_unicode_escapes(content_stripped)

        try:
            llm_output = json.loads(content_sanitized)
        except json.JSONDecodeError as je:
            _log_teacher_response(teacher_model_name, qid, len(prompt), content, "json_parse_failed", str(je))
            print(f"[evaluate] JSON parse failed for qid={qid}: {je}")
            print(f"[evaluate] raw content (first 500 chars): {content[:500]!r}")
            return {
                "_error": f"JSON parse failed: {je}",
                "_raw_content_preview": content[:2000],
                "_question_id": qid,
            }

        # 修复：适配新 prompt 输出格式 (scores + extraction)
        scores_block = llm_output.get("scores", {})
        extraction   = llm_output.get("extraction", {})

        # Fallback: Teacher 模型有时会输出旧版扁平格式（没有 scores/extraction 嵌套），
        # 此时 C_step / Co_order / marker_dict 等直接位于顶层
        if not scores_block:
            if any(k in llm_output for k in ("C_step", "C_param", "total_completeness_score",
                                              "Co_order", "Co_method", "Co_param", "Co_chem")):
                scores_block = {
                    "completeness": {
                        "c_step": llm_output.get("C_step", {}),
                        "c_param": llm_output.get("C_param", {}),
                        "total_completeness_score": llm_output.get("total_completeness_score", 0),
                    },
                    "correctness": {
                        "co_order": llm_output.get("Co_order", {}),
                        "co_method": llm_output.get("Co_method", {}),
                        "co_param": llm_output.get("Co_param", {}),
                        "co_chem": llm_output.get("Co_chem", {}),
                        "critical_warnings": llm_output.get("completeness_critical_warnings", []),
                        "total_correctness_score": llm_output.get("total_correctness_score", 0),
                    },
                }
        if not extraction and any(k in llm_output for k in ("marker_dict", "clearing_total_time_hours", "method_name")):
            extraction = {
                "marker_dict": llm_output.get("marker_dict", {}),
                "clearing_total_time_hours": llm_output.get("clearing_total_time_hours"),
                "method_name": llm_output.get("method_name", ""),
                "reagent_ri_value": llm_output.get("reagent_ri_value"),
                "sample_ri_value": llm_output.get("sample_ri_value"),
                "protocol_time_hours": llm_output.get("protocol_time_hours"),
                "reasoning": llm_output.get("reasoning", ""),
            }

        completeness = scores_block.get("completeness", {})
        correctness  = scores_block.get("correctness", {})

        # 从 extraction 构建 quantitative_data，兼容旧计算逻辑
        # 注意：tissue_ri_value 和 sample_tier 来自题目定义 (question_final.json + tissue_ri.json),
        # 不再依赖 LLM 抽取；reagent_ri_value 仍由 LLM 从 protocol 中抽取。
        # 防御性 None→default 转换：LLM 经常输出 "key": null，.get(key, default) 会返回 None 而非 default
        quantitative_data = {
            "method_name":         _coerce_str(extraction.get("method_name"),        default=""),
            "reagent_ri_value":    _coerce_float(extraction.get("reagent_ri_value"), default=0.0),
            "tissue_ri_value":     _coerce_float(question_meta.get("tissue_ri_value"), default=0.0),
            "total_time_hours":    _coerce_float(extraction.get("clearing_total_time_hours"), default=0.0),
            "protocol_time_hours": extraction.get("protocol_time_hours") or [],
            "sample_tier":         _coerce_str(question_meta.get("tissue_tier_code"), default=""),
        }
        marker_dict          = extraction.get("marker_dict") or {}
        if not isinstance(marker_dict, dict):
            # Some LLMs return marker_dict as a list of dicts → coerce
            if isinstance(marker_dict, list):
                marker_dict = {item.get("fluorophore", str(i)): item.get("marker", "")
                               for i, item in enumerate(marker_dict) if isinstance(item, dict)}
            else:
                marker_dict = {}
        marker_query_targets = question_meta.get("marker_query_targets") or []
        
        # 3. 计算有效性分数
        effectiveness_scores = calculate_effectiveness_score(
            quantitative_data, user_pref_vector, model_space, marker_dict, marker_query_targets
        )
        
        # 4. 组装最终结果
        final_result = {
            "meta_data": {
                "protocol_id": question_meta.get("question_id", "unknown"),
                "sample_info": question_text,
                "target_method": quantitative_data.get("method_name", "unknown"),
                "generated_timestamp": "2025-12-15T00:00:00Z" # 模拟时间戳
            },
            "scores": {
                "completeness": completeness,
                "correctness": correctness,
                "effectiveness": {
                    "s_method": {
                        "score": effectiveness_scores["s_method"],
                        "max_score": 5,
                        "description": "透明方法选择适配度",
                        "reasoning": f"Cos distance based score. Method: {quantitative_data.get('method_name')}"
                    },
                    "s_label": {
                        "score": effectiveness_scores["s_label"],
                        "max_score": 6,
                        "description": "标记与方法兼容性",
                        "reasoning": f"target_match={effectiveness_scores.get('s_target_match', 'N/A'):.1f}, marker_fluor_compat={effectiveness_scores.get('s_marker_fluor_compat', 'N/A'):.1f}, method_fluor_compat={effectiveness_scores.get('s_method_fluor_compat', 'N/A'):.1f}. marker_dict={marker_dict}"
                    },
                    "s_trans": {
                        "score": effectiveness_scores["s_trans"],
                        "max_score": 3,
                        "description": "方法-组织 RI 域匹配度",
                        "reasoning": (
                            f"Method-tissue domain match. "
                            f"RI_tissue(question)={effectiveness_scores.get('_s_trans_ri_tissue')}, "
                            f"RI_method_ref(best-suited sample)={effectiveness_scores.get('_s_trans_ri_method_ref')}, "
                            f"σ_RI={effectiveness_scores.get('_s_trans_sigma')}, "
                            f"tier={quantitative_data.get('sample_tier')}, "
                            f"status={effectiveness_scores.get('_s_trans_status')}"
                        )
                    },
                    "s_time": {
                        "score": effectiveness_scores["s_time"],
                        "max_score": 3,
                        "description": "时间效率评分",
                        "reasoning": f"Time deviation score. Act: {quantitative_data.get('total_time_hours')}, Ref Range: {quantitative_data.get('protocol_time_hours')}"
                    },
                    "total_weighted_score": effectiveness_scores["total_effectiveness_score"]
                }
            }
        }

        _log_teacher_response(teacher_model_name, qid, len(prompt), content, "success", f"completeness_score={completeness.get('total_completeness_score', 'N/A')}, correctness_score={correctness.get('total_correctness_score', 'N/A')}")
        return final_result

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _log_teacher_response(teacher_model_name, qid, len(prompt), content if 'content' in dir() else "", "exception", f"{type(e).__name__}: {e}")
        print(f"评估回答出错 (qid={qid}): {e}")
        print(tb)
        return {"_error": str(e), "_error_type": type(e).__name__, "_traceback": tb}

async def process_model(model_name, model_instance, questions, restrictions, standard_responses, shot_type="1-shot", gen_concurrency=4):
    """
    处理单个被测模型：生成所有问题的回答并保存。
    自动检测已有文件中缺失或无效（空/error）的题目并补充。
    支持并发生成以加速 API 调用。
    """
    print(f"\n--- 开始处理被测模型: {model_name} (Shot: {shot_type}) ---")
    
    os.makedirs(OEQ_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OEQ_OUTPUT_DIR, f'from_{model_name}_{shot_type}.json')
    
    # 加载已有进度，过滤掉无效/空回答
    model_outputs = []
    answered_ids = set()
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                raw_outputs = json.load(f)
            valid_outputs = []
            invalid_ids = []
            for item in raw_outputs:
                if _is_valid_response(item.get('model_response')):
                    valid_outputs.append(item)
                    answered_ids.add(item['question_id'])
                else:
                    invalid_ids.append(item['question_id'])
            model_outputs = valid_outputs
            if invalid_ids:
                print(f"[{model_name}] 检测到 {len(invalid_ids)} 个无效/空回答，将重新生成: {invalid_ids}")
                # 立即重写文件，只保留有效回答，避免后续追加产生重复
                _atomic_write_json(output_path, model_outputs)
            print(f"[{model_name}] 检测到已有进度，已完成 {len(model_outputs)}/{len(questions)} 个有效问题。")
        except Exception as e:
            print(f"[{model_name}] 加载已有回答失败，将重新开始: {e}")
            model_outputs = []
            answered_ids = set()

    pending_questions = [q for q in questions if q["question_id"] not in answered_ids]
    if not pending_questions:
        print(f"[{model_name}] 所有问题已有有效回答，无需生成。")
        return model_outputs

    print(f"[{model_name}] 待生成 {len(pending_questions)} 题，并发上限 {gen_concurrency}")
    sem = asyncio.Semaphore(gen_concurrency)
    lock = asyncio.Lock()

    async def _gen_one(q):
        async with sem:
            prompt = generate_model_prompt(q, restrictions, standard_responses, shot_type=shot_type)
            response_text = await get_model_response(model_instance, prompt)
            output_entry = {
                "question_id": q["question_id"],
                "specific_question": q["question"],
                "marker_query_targets": q.get("marker_query_targets", []),
                "tissue_tier_code": q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_tier_code", ""),
                "tissue_inferred":  q.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_inferred", ""),
                "tissue_ri_value":  QUESTION_META_KB.get(q["question_id"], {}).get("tissue_ri_value", 0.0),
                "prompt": prompt,
                "restrictions": str(restrictions),
                "model_response": response_text,
                "shot_type": shot_type
            }
            async with lock:
                # 双重检查，避免并发条件下重复写入同一题
                current_ids = {e["question_id"] for e in model_outputs}
                if q["question_id"] not in current_ids:
                    model_outputs.append(output_entry)
                    _atomic_write_json(output_path, model_outputs)
                    print(f"[{model_name}] 问题 {q['question_id']} 回答已保存 (当前进度: {len(model_outputs)}/{len(questions)})")
            return output_entry

    await asyncio.gather(*[_gen_one(q) for q in pending_questions])
    print(f"[{model_name}] 全部回答已保存至 {output_path}")
    return model_outputs

def _atomic_write_json(path, obj):
    """Write obj to path atomically (write .tmp then os.replace) so a crash mid-write cannot corrupt the file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)


async def evaluate_responses(
    model_name,
    responses,
    teacher_model,
    model_space,
    prompt_template,
    shot_type="1-shot",
    eval_concurrency=4,
):
    """
    使用教师模型对某个模型的回答集进行评分。

    - 内部用 asyncio.Semaphore 控制并发（默认 4 个/模型）
    - 每完成一题立即原子写盘，崩溃后可断点续传
    - 保存路径 = 读取路径 = OEQ_SCORE_DIR/evaluation_results_<model>_<shot>.json
    """
    print(f"\n--- 开始评估模型回答: {model_name} (Shot: {shot_type}, concurrency={eval_concurrency}) ---")
    os.makedirs(OEQ_SCORE_DIR, exist_ok=True)
    result_path = os.path.join(OEQ_SCORE_DIR, f'evaluation_results_{model_name}_{shot_type}.json')

    # 加载已有评分进度（将空 evaluation {} 或包含 _error 的视为未完成）
    results = []
    evaluated_ids = set()
    if os.path.exists(result_path):
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                raw_results = json.load(f)
            for item in raw_results:
                ev = item.get('evaluation')
                if not ev or not isinstance(ev, dict) or ev.get('_error'):
                    continue
                scores = ev.get('scores', {})
                if not scores.get('completeness') or not scores.get('correctness'):
                    continue
                results.append(item)
                evaluated_ids.add(item['question_id'])
            skipped = len(raw_results) - len(results)
            if skipped:
                print(f"[{model_name}] 检测到已有进度 {len(raw_results)} 条，其中 {skipped} 条为空/失败/评分不完整，将重新评估。有效 {len(results)}/{len(responses)} 个。")
            else:
                print(f"[{model_name}] 检测到已有评分进度，已完成 {len(results)}/{len(responses)} 个评估。")
        except Exception as e:
            print(f"[{model_name}] 加载已有评估结果失败，将重新开始: {e}")
            results = []
            evaluated_ids = set()

    pending = [e for e in responses if e.get('question_id') not in evaluated_ids]
    if not pending:
        print(f"[{model_name}] 所有 {len(responses)} 题已评估，跳过。")
        return result_path

    print(f"[{model_name}] 待评估 {len(pending)} 题（总 {len(responses)}），并发上限 {eval_concurrency}")

    sem = asyncio.Semaphore(eval_concurrency)
    persist_lock = asyncio.Lock()  # serialize writes to results list + file
    completed = [len(results)]      # mutable counter for closures

    async def _one(entry):
        qid = entry.get('question_id')
        async with sem:
            try:
                score = await evaluate_response_with_teacher(
                    teacher_model, entry['specific_question'], entry['model_response'],
                    model_space, entry, prompt_template,
                )
            except Exception as exc:
                # evaluate_response_with_teacher should catch its own exceptions and return {"_error": ...},
                # but belt-and-suspenders here for unexpected propagation
                score = {"_error": str(exc), "_error_type": type(exc).__name__}
        result_entry = {"question_id": qid, "evaluation": score}
        async with persist_lock:
            results.append(result_entry)
            completed[0] += 1
            _atomic_write_json(result_path, results)
            print(f"[{model_name}] 评估完成 {completed[0]}/{len(responses)} (qid={qid})")
        return result_entry

    await asyncio.gather(*(_one(e) for e in pending), return_exceptions=False)

    print(f"[{model_name}] 评估结果已保存至 {result_path} (共 {len(results)} 条)")
    return result_path


async def process_and_evaluate_model(
    model_name, model_instance, questions, restrictions, standard_responses,
    teacher_model, model_space, prompt_template, shot_type="1-shot",
    eval_concurrency=4, gen_concurrency=4, skip_generation=False, skip_evaluation=False,
):
    """Per-model pipeline: generate (optionally) then evaluate (optionally).

    - skip_generation=True 用于 --eval-only 模式：直接读取已有的 from_<model>_<shot>.json
    - skip_evaluation=True 用于 --no-evaluation 模式：只生成不评测（旧行为）
    Returns dict {model, shot, n_generated, n_evaluated, error}.
    """
    summary = {"model": model_name, "shot": shot_type, "n_generated": 0, "n_evaluated": 0, "error": None}
    try:
        # Generation phase
        if skip_generation:
            response_path = os.path.join(OEQ_OUTPUT_DIR, f'from_{model_name}_{shot_type}.json')
            if not os.path.exists(response_path):
                summary["error"] = f"--eval-only but {response_path} does not exist"
                return summary
            with open(response_path, 'r', encoding='utf-8') as f:
                responses = json.load(f)
            # 验证完整性：过滤无效并检查缺失
            valid_responses = [r for r in responses if _is_valid_response(r.get('model_response'))]
            all_qids = {q['question_id'] for q in questions}
            resp_qids = {r['question_id'] for r in valid_responses}
            missing_qids = sorted(all_qids - resp_qids)
            if missing_qids:
                print(
                    f"[{model_name}] WARNING: --eval-only 模式下检测到 {len(missing_qids)} 题缺失/无效 "
                    f"(Missing IDs: {missing_qids})，将继续评估已有的 {len(valid_responses)} 条有效回答。"
                    f"如需补齐缺失题目，请重新运行（不带 --eval-only）。"
                )
            responses = valid_responses
            print(f"[{model_name}] --eval-only: 跳过生成，从 {response_path} 加载 {len(responses)} 条有效回答")
        else:
            responses = await process_model(
                model_name, model_instance, questions, restrictions, standard_responses, shot_type=shot_type,
                gen_concurrency=gen_concurrency,
            )
            # 再次确认完整性
            all_qids = {q['question_id'] for q in questions}
            resp_qids = {r['question_id'] for r in responses}
            missing_qids = sorted(all_qids - resp_qids)
            if missing_qids:
                print(f"[{model_name}] 警告: 生成阶段结束后仍缺失 {len(missing_qids)} 题: {missing_qids}")
        summary["n_generated"] = len(responses) if responses else 0

        # Evaluation phase
        if skip_evaluation:
            print(f"[{model_name}] --no-evaluation: 跳过评估")
        else:
            await evaluate_responses(
                model_name, responses, teacher_model, model_space, prompt_template,
                shot_type=shot_type, eval_concurrency=eval_concurrency,
            )
            # Count actual saved evaluations
            result_path = os.path.join(OEQ_SCORE_DIR, f'evaluation_results_{model_name}_{shot_type}.json')
            if os.path.exists(result_path):
                with open(result_path, 'r', encoding='utf-8') as f:
                    summary["n_evaluated"] = len(json.load(f))
    except Exception as exc:
        import traceback
        summary["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"
    return summary

DEFAULT_MODEL_LIST = [
    "openai_gpt-5.2-fast",
    "openai_gpt-5.2-thinking",
    "gemini-3-pro",
    "gemini-3-flash",
    "openai_claude-sonnet-4.6",
    #"glm4.7-thinking",
    "glm4.7-unthinking",
    "openai_deepseek-chat",
    "openai_deepseek-reasoner",
    "openai_qwen3-max",
    "openai_qwen3-235b",
    "openai_qwen3-32b",
    "openai_qwen3-14b",
]


async def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="OEQ benchmark: generate model responses, then score via teacher LLM. "
                    "By default runs generation followed by concurrent evaluation per model.",
    )
    parser.add_argument("--models", nargs="*", default=None,
                        help=f"Model names to run (default: {len(DEFAULT_MODEL_LIST)} models from DEFAULT_MODEL_LIST)")
    parser.add_argument("--shot-types", nargs="*", default=["1-shot"],
                        help='Shot types to test (default: ["1-shot"])')
    parser.add_argument("--teacher", default="openai_gpt-5.2-thinking",
                        help="Teacher model name (default: openai_gpt-5.2-thinking)")
    parser.add_argument("--eval-concurrency", type=int, default=4,
                        help="Per-model concurrent teacher-LLM calls (default: 4)")
    parser.add_argument("--gen-concurrency", type=int, default=4,
                        help="Per-model concurrent generation calls (default: 4)")
    parser.add_argument("--eval-only", action="store_true",
                        help="Skip generation phase, evaluate existing from_<model>.json files only")
    parser.add_argument("--no-evaluation", action="store_true",
                        help="Skip evaluation phase, only generate responses (legacy behavior)")
    args = parser.parse_args(argv)

    if args.eval_only and args.no_evaluation:
        print("错误：--eval-only 和 --no-evaluation 互斥")
        return 2

    # 1. 加载模型管理器
    loader = ModelLoader('config/config.yaml')
    models = loader.load_models()

    model_list = args.models if args.models else DEFAULT_MODEL_LIST
    shot_types = args.shot_types

    # 2. 教师模型选择
    teacher_model = None
    if not args.no_evaluation:
        teacher_model_name = args.teacher
        if teacher_model_name not in models:
            print(f"错误: 教师模型 {teacher_model_name} 未在配置文件中找到，回退尝试 openai_gpt-4o")
            teacher_model_name = "openai_gpt-4o"
            if teacher_model_name not in models:
                print("无法找到合适的教师模型，终止")
                return 2
        teacher_model = models[teacher_model_name]
        print(f"教师模型: {teacher_model_name}")

    # 3. 加载数据
    questions, standard_responses, model_space = load_data()
    restrictions = load_restrictions()
    prompt_template = load_prompt_method_generate()

    if not prompt_template:
        print("错误: 无法加载评分Prompt，终止执行。")
        return 2

    # 4. 模式提示
    mode = "eval-only" if args.eval_only else ("generate-only" if args.no_evaluation else "generate+evaluate")
    valid_models = [m for m in model_list if m in models]
    print(f"\n--- 模式={mode}，并发评测 {len(valid_models)} 模型 × {len(shot_types)} shot ---")
    print(f"   模型: {valid_models}")
    if args.no_evaluation is False:
        print(f"   每模型评估并发: {args.eval_concurrency}")

    # 5. 构建并发任务（每个模型一个 process_and_evaluate_model）
    tasks = []
    task_info = []
    for model_name in model_list:
        if model_name not in models:
            print(f"跳过未知模型: {model_name} (请检查 config.yaml)")
            continue
        for shot_type in shot_types:
            t = process_and_evaluate_model(
                model_name, models[model_name], questions, restrictions, standard_responses,
                teacher_model, model_space, prompt_template, shot_type=shot_type,
                eval_concurrency=args.eval_concurrency,
                gen_concurrency=args.gen_concurrency,
                skip_generation=args.eval_only,
                skip_evaluation=args.no_evaluation,
            )
            tasks.append(t)
            task_info.append((model_name, shot_type))

    summaries = []
    if tasks:
        print(f"\n共创建 {len(tasks)} 个并发任务，同时启动...\n")
        summaries = await asyncio.gather(*tasks, return_exceptions=True)

    # 6. 汇总
    print("\n" + "=" * 100)
    print("RUN SUMMARY")
    print("=" * 100)
    print(f"{'model':<32}  {'shot':<8}  {'generated':>10}  {'evaluated':>10}  status")
    print("-" * 100)
    for (model_name, shot_type), s in zip(task_info, summaries):
        if isinstance(s, Exception):
            print(f"{model_name:<32}  {shot_type:<8}  {'?':>10}  {'?':>10}  EXC: {type(s).__name__}: {s}")
        else:
            status = "OK" if not s.get("error") else f"ERR: {s['error'][:80]}"
            print(f"{model_name:<32}  {shot_type:<8}  {s.get('n_generated', 0):>10}  {s.get('n_evaluated', 0):>10}  {status}")

    # 7. 关闭客户端
    print("\n--- 正在清理模型连接池 ---")
    for name, model_instance in models.items():
        if hasattr(model_instance, 'client') and hasattr(model_instance.client, 'close'):
            try:
                await model_instance.client.close()
            except Exception:
                pass

    n_err = sum(1 for s in summaries if isinstance(s, Exception) or (isinstance(s, dict) and s.get("error")))
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
