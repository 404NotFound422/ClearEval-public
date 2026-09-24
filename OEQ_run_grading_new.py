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

import json
import os
import re
import sys
import importlib.util
import asyncio
import math
from datetime import datetime, timezone
from pathlib import Path
from verified_marker_aliases import IDENTITY_VERSION, same_verified_target
from evaluation_contract import (
    SCORING_VERSION, FixedDemandRegistry, ensure_manifest, json_hash, sha256_file,
    time_score_details, time_reasoning,
)
from results.oeq_metrics import protocol_scores
from prompts.gen_protocol_template import TEST_MODEL_GENERATION_PROMPT
from prompts.parse_user_preference_vector import USER_PREFERENCE_PROMPT

OEQ_OUTPUT_DIR = 'dataset/Q+AR/model_response_scoring_v2'
OEQ_SCORE_DIR = 'dataset/Q+AR/result_scoring_v2'
QUESTION_FILE = 'dataset/Q+AR/src/question_final.json'
DEMAND_FILE = 'dataset/Q+AR/src/demand_vectors_all.json'
DEMAND_MANIFEST = None
_FIXED_DEMANDS = None
RAG_CONTEXT_DIR = 'dataset/Q+AR/rag_context'  # per-question KB-RAG cards (see build_rag_context.py)

# -------------------------------------------------------------------------
# Load KnowledgeBase for rule-based scoring
# -------------------------------------------------------------------------
with open('KnowledgeBase/tissue.json', 'r', encoding='utf-8') as f:
    TISSUE_KB = json.load(f)
with open('KnowledgeBase/method_fluro_compati.json', 'r', encoding='utf-8') as f:
    METHOD_FLUORO_KB = json.load(f)
with open('KnowledgeBase/time_kb.json', 'r', encoding='utf-8') as f:
    _TIME_KB_RAW = json.load(f)
with open('KnowledgeBase/tissue_ri.json', 'r', encoding='utf-8') as f:
    _TISSUE_RI_RAW = json.load(f)
with open('KnowledgeBase/method_sigma_ri.json', 'r', encoding='utf-8') as f:
    _SIGMA_RI_RAW = json.load(f)
with open('KnowledgeBase/method_ri_ref.json', 'r', encoding='utf-8') as f:
    _METHOD_RI_REF_RAW = json.load(f)
# Question metadata (loaded once at startup; avoids per-call file I/O)
with open(QUESTION_FILE, 'r', encoding='utf-8') as f:
    _QUESTION_LIST = json.load(f)

# Marker specificity tiers for target_match scoring (0/3/6)
_MARKER_SPECIFICITY_TIERS_PATH = 'workflow/s_label_audit/marker_specificity_tiers.json'
_MARKER_SPECIFICITY_TIERS: dict = {"tier_0": [], "tier_3": [], "tier_6": []}
if os.path.exists(_MARKER_SPECIFICITY_TIERS_PATH):
    try:
        _MARKER_SPECIFICITY_TIERS = json.load(open(_MARKER_SPECIFICITY_TIERS_PATH, encoding='utf-8'))
    except Exception:
        pass

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
    if "牙" in s:
        return _TISSUE_RI_TABLE["tooth"]
    if "颅骨" in s or "股骨" in s or "骨髓" in s or "骨" in s:
        return _TISSUE_RI_TABLE["bone"]
    if "耳蜗" in s:
        return _TISSUE_RI_TABLE["cochlea"]
    if "皮肤" in s:
        return _TISSUE_RI_TABLE["skin"]
    if "心" in s:
        return _TISSUE_RI_TABLE["heart"]
    if "肌" in s:
        return _TISSUE_RI_TABLE["skeletal_muscle"]
    if "黑色素瘤" in s:
        return _TISSUE_RI_TABLE["melanoma"]
    if "石蜡" in s:
        return _TISSUE_RI_TABLE["tumor_paraffin"]
    if "淋巴结" in s:
        return _TISSUE_RI_TABLE["lymph_node"]
    if "乳腺癌" in s:
        return _TISSUE_RI_TABLE["breast_cancer"]
    if "前列腺" in s:
        return _TISSUE_RI_TABLE["prostate"]
    if "肝" in s:
        return _TISSUE_RI_TABLE["liver"]
    if "肾" in s:
        return _TISSUE_RI_TABLE["kidney"]
    if "脾" in s:
        return _TISSUE_RI_TABLE["spleen"]
    if "胰" in s:
        return _TISSUE_RI_TABLE["pancreas"]
    if "胎盘" in s:
        return _TISSUE_RI_TABLE["placenta"]
    if "胃" in s:
        return _TISSUE_RI_TABLE["stomach"]
    if "肠" in s and "类器官" not in s:
        return _TISSUE_RI_TABLE["intestine"]
    if "肺" in s:
        return _TISSUE_RI_TABLE["lung"]
    if "睾丸" in s:
        return _TISSUE_RI_TABLE["testis"]
    if "脂肪" in s:
        return _TISSUE_RI_TABLE["fat"]
    if "肿瘤" in s:
        return _TISSUE_RI_TABLE["tumor_dense"]
    if "全身" in s:
        return _TISSUE_RI_TABLE["kidney"]  # whole-body soft-tissue default
    if "类器官" in s or "果蝇" in s:
        return _TISSUE_RI_TABLE["organoid"]
    if "elegans" in s.lower():
        return _TISSUE_RI_TABLE["celegans"]
    if "E14" in s:
        return _TISSUE_RI_TABLE["embryo_brain"]
    if "胚胎" in s:
        return _TISSUE_RI_TABLE["embryo_whole"]
    if "人脑" in s:
        return _TISSUE_RI_TABLE["human_brain_block"]
    if "海马" in s:
        return _TISSUE_RI_TABLE["hippocampus_ca1"]
    if "视网膜" in s or "眼球" in s:
        return _TISSUE_RI_TABLE["eye_retina"]
    if "脊髓" in s or "CNS" in s:
        return _TISSUE_RI_TABLE["spinal_cord"]
    if "斑马鱼" in s:
        return _TISSUE_RI_TABLE["zebrafish"]
    if "脑" in s:
        return _TISSUE_RI_TABLE["whole_brain"]
    if "植物" in s or "拟南芥" in s:
        return _TISSUE_RI_TABLE["plant"]
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


def configure_question_snapshot(path):
    """Update question metadata together; never backfill from a different snapshot."""
    global QUESTION_FILE, _QUESTION_LIST, QUESTION_META_KB, _FIXED_DEMANDS
    QUESTION_FILE = str(path)
    with open(QUESTION_FILE, encoding='utf-8') as f:
        _QUESTION_LIST = json.load(f)
    QUESTION_META_KB = {
        q['question_id']: {
            'tissue_tier_code': q.get('tissue_hierarchy_from_tissue_xlsx', {}).get('tissue_tier_code', ''),
            'tissue_inferred': q.get('tissue_hierarchy_from_tissue_xlsx', {}).get('tissue_inferred', ''),
            'tissue_ri_value': _resolve_tissue_ri(q.get('tissue_hierarchy_from_tissue_xlsx', {}).get('tissue_inferred', '')),
            'marker_query_targets': q.get('marker_query_targets', []),
        } for q in _QUESTION_LIST
    }
    _FIXED_DEMANDS = None


def fixed_demands():
    global _FIXED_DEMANDS
    if _FIXED_DEMANDS is None:
        _FIXED_DEMANDS = FixedDemandRegistry(QUESTION_FILE, DEMAND_FILE, DEMAND_MANIFEST)
    return _FIXED_DEMANDS


def scoring_contract(teacher_model):
    paths = [
        'OEQ_run_grading_new.py', 'evaluation_contract.py', 'results/oeq_metrics.py',
        'verified_marker_aliases.py',
        'prompts/eval_oeq_teacher_rubric.txt', 'dataset/Q+AR/src/model_space_signed.json',
        'KnowledgeBase/tissue.json', 'KnowledgeBase/method_fluro_compati.json',
        'KnowledgeBase/time_kb.json', 'KnowledgeBase/tissue_ri.json',
        'KnowledgeBase/method_sigma_ri.json', 'KnowledgeBase/method_ri_ref.json',
    ]
    return {
        'scoring_version': SCORING_VERSION, **fixed_demands().provenance,
        'marker_identity_version': IDENTITY_VERSION,
        'teacher_model': getattr(teacher_model, 'model_name', 'unknown_teacher'),
        'source_sha256': {path: sha256_file(path) for path in paths},
        'marker_specificity_sha256': sha256_file(_MARKER_SPECIFICITY_TIERS_PATH)
        if os.path.exists(_MARKER_SPECIFICITY_TIERS_PATH) else None,
        'fluorophore_evidence_sha256': sha256_file(_FLUOR_EVIDENCE_PATH)
        if os.path.exists(_FLUOR_EVIDENCE_PATH) else None,
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


# Fluorophore evidence-based mapping and penalty list (loaded after _normalize_name is defined)
_FLUOR_EVIDENCE_PATH = 'workflow/s_label_audit/fluorophore_classification_for_review.json'
_FLUOR_TO_TISSUE_COL: dict = {}
_PENALTY_FLUORS: set = set()
_MARKER_REDIRECT_FLUORS: set = set()
if os.path.exists(_FLUOR_EVIDENCE_PATH):
    try:
        _fluor_evidence = json.load(open(_FLUOR_EVIDENCE_PATH, encoding='utf-8'))
        for entry in _fluor_evidence.get('tissue_mappings', []):
            fluor = entry.get('fluor')
            target = entry.get('target_column')
            if fluor and target:
                _FLUOR_TO_TISSUE_COL[_normalize_name(fluor)] = target
        for entry in _fluor_evidence.get('penalty_list', []):
            fluor = entry.get('fluor')
            if fluor:
                _PENALTY_FLUORS.add(_normalize_name(fluor))
        for entry in _fluor_evidence.get('marker_redirects', []):
            fluor = entry.get('fluor')
            if fluor:
                _MARKER_REDIRECT_FLUORS.add(_normalize_name(fluor))
    except Exception:
        _FLUOR_TO_TISSUE_COL = {}
        _PENALTY_FLUORS = set()
        _MARKER_REDIRECT_FLUORS = set()


def _classify_marker_specificity(marker_str, fluor_str=None, marker_query_targets=None):
    """Return 0/3/6 specificity score for a marker string.

    The tier table is a supplement for markers that did not match the question
    targets directly.  Vague/descriptive terms receive 0, incomplete-but-inferable
    terms receive 3, and concrete markers receive 6 (which then allows a
    major-category partial-credit fallback in the caller).
    """
    if not marker_str:
        return 0
    norm = _normalize_name(marker_str)
    lower = marker_str.lower()

    # Exact normalized match against tiers
    tier_0_norm = {_normalize_name(m) for m in _MARKER_SPECIFICITY_TIERS.get("tier_0", [])}
    tier_3_norm = {_normalize_name(m) for m in _MARKER_SPECIFICITY_TIERS.get("tier_3", [])}
    tier_6_norm = {_normalize_name(m) for m in _MARKER_SPECIFICITY_TIERS.get("tier_6", [])}
    if norm in tier_0_norm:
        return 0
    if norm in tier_3_norm:
        return 3
    if norm in tier_6_norm:
        return 6

    # Substring / containment match for tier entries that contain qualifiers
    # (e.g. "Alexa Fluor" inside "Alexa Fluor (unspecified)").
    for vague in _MARKER_SPECIFICITY_TIERS.get("tier_0", []):
        if vague and (vague.lower() in lower or lower in vague.lower()):
            return 0
    for incomplete in _MARKER_SPECIFICITY_TIERS.get("tier_3", []):
        if incomplete and (incomplete.lower() in lower or lower in incomplete.lower()):
            return 3
    for specific in _MARKER_SPECIFICITY_TIERS.get("tier_6", []):
        if specific and (specific.lower() in lower or lower in specific.lower()):
            return 6

    # Marker not catalogued: treat as a specific marker so the caller can still
    # apply the major-category fallback.  This avoids penalising concrete marker
    # names that are absent from the tier table.
    return 6


def _extract_parenthetical(name):
    """提取括号内的缩写，如 'β-III Tubulin (TUJ1)' -> ['tuj1']"""
    import re
    matches = re.findall(r'\(([^)]+)\)', str(name))
    return [_normalize_name(m) for m in matches]


def _map_fluor_to_tissue_col(fluor_name):
    """将大模型返回的荧光团名称映射到 tissue.json 的列名"""
    s = _normalize_name(fluor_name)
    if not s:
        return None
    # 1. Hard-coded canonical mappings
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
    if s in mapping:
        return mapping[s]
    # 2. Evidence-based mapping from fluorophore_evidence_suggestions.json
    if s in _FLUOR_TO_TISSUE_COL:
        return _FLUOR_TO_TISSUE_COL[s]
    # 3. Prefix / substring fallback
    for k, v in mapping.items():
        if s.startswith(k) or k in s:
            return v
    return None


def _is_penalty_fluor(fluor_name):
    """Return True for fluorophores that are not real fluorophores/marker pairs (e.g. 'Alexa Fluor' unspecified)."""
    return _normalize_name(fluor_name) in _PENALTY_FLUORS


def _preprocess_marker_dict(marker_dict):
    """Move fluorophore keys that are actually markers to the marker value side.

    Returns a tuple (preprocessed_pairs, has_marker_without_fluor, has_fluor_without_marker).
    preprocessed_pairs is a list of (fluor_str, marker_str) to preserve duplicates.
    """
    preprocessed = []
    has_marker_without_fluor = False
    has_fluor_without_marker = False
    for fluor, marker in marker_dict.items():
        fluor_str = str(fluor).strip() if fluor else ""
        marker_str = str(marker).strip() if marker else ""
        if fluor_str and _normalize_name(fluor_str) in _MARKER_REDIRECT_FLUORS:
            # The fluorophore field contains a marker name; move it to marker side
            preprocessed.append(("", fluor_str))
            if not marker_str:
                has_marker_without_fluor = True
            continue
        preprocessed.append((fluor_str, marker_str))
        if fluor_str and not marker_str:
            has_fluor_without_marker = True
        if marker_str and not fluor_str:
            has_marker_without_fluor = True
    return preprocessed, has_marker_without_fluor, has_fluor_without_marker


def _map_fluor_to_method_key(fluor_name):
    """将大模型返回的荧光团名称映射到 method_fluro_compati.json 的键名"""
    s = _normalize_name(fluor_name)
    if not s:
        return None
    # 1. Specific dye mappings (checked before coarse families)
    specific_mapping = {
        # Alexa Fluor series
        "alexafluor405": "Alexa Fluor 405",
        "alexafluor488": "Alexa Fluor 488",
        "alexa488": "Alexa Fluor 488",
        "alexafluor546": "Alexa Fluor 546",
        "alexafluor555": "Alexa Fluor 555",
        "alexafluor568": "Alexa Fluor 568",
        "alexafluor594": "Alexa Fluor 594",
        "alexafluor633": "Alexa Fluor 633",
        "alexafluor647": "Alexa Fluor 647",
        "alexafluor680": "Alexa Fluor 680",
        "alexafluor750": "Alexa Fluor 750",
        # Common organic dyes
        "fitc": "FITC",
        "fluorescein": "FITC",
        "tritc": "TRITC",
        "cy3": "Cy3",
        "cy5": "Cy5",
        # DyLight series
        "dylight405": "DyLight 405",
        "dylight488": "DyLight 488",
        "dylight550": "DyLight 550",
        "dylight594": "DyLight 594",
        "dylight649": "DyLight 649",
        # iFluor series
        "ifluor594": "iFluor 594",
        "ifluor647": "iFluor 647",
        # Others
        "pe": "PE",
        "calcofluorwhite": "Calcofluor White",
        "calcofluor": "Calcofluor White",
        "neurotrace500": "NeuroTrace 500",
        "neurotrace": "NeuroTrace 500",
    }
    if s in specific_mapping:
        return specific_mapping[s]
    # 2. Coarse family mappings
    coarse_mapping = {
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
    if s in coarse_mapping:
        return coarse_mapping[s]
    # 3. Prefix fallback (avoid short-key substring false matches like "pe" in "specified")
    for k, v in specific_mapping.items():
        if s.startswith(k):
            return v
    for k, v in coarse_mapping.items():
        if s.startswith(k):
            return v
    return None


# Marker alias table for semantic equivalence beyond string normalization.
# Key: normalized marker name; Value: list of normalized equivalent names.
_MARKER_ALIASES: dict = {
    # Reporter fluorophores
    "gfp": ["gfp", "egfp", "gfp/yfp"],
    "egfp": ["egfp", "gfp", "gfp/yfp"],
    "yfp": ["yfp", "gfp", "gfp/yfp"],
    "rfp": ["rfp", "tdtomato", "mcherry", "mrfp"],
    "tdtomato": ["tdtomato", "rfp", "mcherry"],
    "mcherry": ["mcherry", "rfp", "tdtomato"],
    "tdtomatoreporter": ["tdtomato", "rfp", "mcherry"],
    # Neuronal markers
    "tuj1": ["tuj1", "βiiitubulin", "tubulinβiii", "tubulinbeta3", "beta3tubulin", "tubulinβ3"],
    "βiiitubulin": ["βiiitubulin", "tuj1", "tubulinβiii", "tubulinbeta3", "beta3tubulin"],
    "map2": ["map2", "microtubuleassociatedprotein2"],
    "neun": ["neun", "rbfox3"],
    "rbfox3": ["rbfox3", "neun"],
    "pgp95": ["pgp95", "pgp9.5", "proteingeneproduct9.5", "ubiquitincarboxylterminalhydrolase1"],
    "pgp9.5": ["pgp9.5", "pgp95", "proteingeneproduct9.5"],
    "neurofilament": ["neurofilament", "nf200", "nf"],
    "nf200": ["nf200", "neurofilament"],
    # Immediate early genes / activity markers
    "cfos": ["cfos", "c-fos", "fos"],
    "c-fos": ["c-fos", "cfos", "fos"],
    "fos": ["fos", "cfos", "c-fos"],
    "npas4": ["npas4"],
    # Vascular / endothelial markers
    "cd31": ["cd31", "pecam1"],
    "pecam1": ["pecam1", "cd31"],
    "lectin": ["lectin", "ib4", "isolectin"],
    "ib4": ["ib4", "lectin", "isolectin"],
    # Lipophilic dyes
    "dii": ["dii", "dio", "did", "di"],
    "dio": ["dio", "dii", "did", "di"],
    "did": ["did", "dii", "dio", "di"],
    # Neuromuscular / muscle
    "alphabungarotoxin": ["alphabungarotoxin", "bungarotoxin", "achr"],
    "bungarotoxin": ["bungarotoxin", "alphabungarotoxin", "achr"],
    "phalloidin": ["phalloidin", "f-actin", "factin", "f-actin"],
    "factin": ["factin", "f-actin", "phalloidin"],
    # Cytokeratins
    "pancytokeratin": ["pancytokeratin", "ck", "cytokeratin"],
    "ck7": ["ck7", "cytokeratin7"],
    "ck19": ["ck19", "cytokeratin19"],
}


def _expand_marker_candidates(name):
    """Return a set of normalized candidate names for a marker, including aliases."""
    import re
    norm = _normalize_name(name)
    if not norm:
        return set()
    candidates = {norm}
    # Add the base name with parenthetical content stripped, half- AND full-width, incl. a
    # stray unclosed paren (e.g. "Lectin (AF488/…未指定)" -> "lectin", "Lectin (AF488" -> "lectin")
    base = _normalize_name(re.sub(r"\s*[\(（][^)）]*[\)）]?", "", str(name)))
    if base and base != norm:
        candidates.add(base)
    # Add the leading token before the first paren / Chinese-or-ASCII comma / semicolon
    lead = _normalize_name(re.split(r"[\(（,，、;；]", str(name))[0])
    if lead and lead not in candidates:
        candidates.add(lead)
    # Add parenthetical abbreviations
    candidates.update(_extract_parenthetical(name))
    # Add aliases
    for key, equivalents in _MARKER_ALIASES.items():
        if key in candidates:
            candidates.update(equivalents)
    # Reverse lookup: if a value equivalent is in candidates, add its key
    expanded = set(candidates)
    for key, equivalents in _MARKER_ALIASES.items():
        if expanded & set(equivalents):
            expanded.add(key)
            expanded.update(equivalents)
    return expanded


def _is_reporter_fluor(fluor_name):
    """判断荧光团是否为常见的内源/外源报告基因荧光蛋白"""
    s = _normalize_name(fluor_name)
    return any(x in s for x in ["gfp", "egfp", "yfp", "rfp", "tdtomato", "mcherry", "mrfp"])


def _is_reporter_target(target_name):
    """判断题目 target 是否为 reporter 类型标记"""
    s = _normalize_name(target_name)
    return "reporter" in s or "Դ" in target_name  # include Chinese source/reporter


def _split_marker_value(value):
    """Split a marker value that may contain multiple markers separated by delimiters.
    Handles Chinese punctuation (、，；／·) and conjunctions so re-worded multi-marker
    strings like 'MAP2、Nestin' or 'IB4/Lectin (…)' are split into matchable tokens."""
    import re
    if not value:
        return []
    parts = re.split(r"[;/,、，；／·]|\band\b|\bor\b|和|或", str(value))
    return [p.strip() for p in parts if p.strip()]


def _match_marker_to_targets(marker_name, marker_query_targets, fluor_name=None):
    """检查 marker_name（及可选的 fluor_name）是否与 marker_query_targets 中任一 marker_name 匹配。

    改进点：
    1. 引入同义词/别名表，处理 GFP/EGFP、TUJ1/β-III Tubulin、CD31/PECAM1 等。
    2. marker_dict 的 value 可能为描述性文字或包含多个 marker，拆分后分别匹配。
    3. marker_dict 的 key 有时就是 marker（尤其 reporter），也作为候选。
    4. reporter 靶标（EGFP reporter 等）与 reporter 荧光团直接匹配。
    """
    # Collect all candidate strings: the main marker, split parts, and fluor key if provided
    candidate_names = []
    if marker_name and str(marker_name).strip():
        candidate_names.append(str(marker_name).strip())
        candidate_names.extend(_split_marker_value(marker_name))
    if fluor_name and str(fluor_name).strip():
        candidate_names.append(str(fluor_name).strip())

    # Precompute expanded candidate sets
    candidate_sets = [_expand_marker_candidates(c) for c in candidate_names]

    for target in marker_query_targets:
        target_name = target.get("marker_name", "")
        if not target_name:
            continue
        # Verified clone-to-target identity is separate from substring heuristics.
        # It establishes target recognition, not staining/secondary compatibility.
        if any(same_verified_target(candidate, target_name) for candidate in candidate_names):
            return True
        norm_target = _normalize_name(target_name)
        target_abbrevs = _extract_parenthetical(target_name)
        target_candidates = _expand_marker_candidates(target_name)

        for cand_set in candidate_sets:
            # Direct normalized match or alias match
            if cand_set & target_candidates:
                return True
            # Abbreviation match
            if cand_set & set(target_abbrevs):
                return True
            # Substring match (avoid short tokens)
            for cand in cand_set:
                if len(cand) < 3:
                    continue
                for tc in target_candidates:
                    if len(tc) < 3:
                        continue
                    if cand in tc or tc in cand:
                        return True

        # Special reporter handling: if target is a reporter and fluor is a reporter fluorophore
        if fluor_name and _is_reporter_target(target_name) and _is_reporter_fluor(fluor_name):
            fluor_set = _expand_marker_candidates(fluor_name)
            # Match fluor against target name (e.g. EGFP vs EGFP reporter, tdTomato vs mCherry/RFP reporter)
            for fc in fluor_set:
                if len(fc) >= 3 and (fc in norm_target or norm_target in fc):
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
    with open(QUESTION_FILE, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    with open('dataset/Q+AR/src/standard_response.json', 'r', encoding='utf-8') as f:
        standard_responses = json.load(f)
    with open('dataset/Q+AR/src/model_space.json', 'r', encoding='utf-8') as f:
        model_space = json.load(f)
    return questions, standard_responses, model_space


def _shot_flags(shot_type):
    """Map a shot_type token to (use_rag, use_self_check).

    '1-shot'                     -> (False, False)  (unchanged baseline)
    '1-shot+KB-RAG'              -> (True,  False)
    '1-shot+KB-RAG+self-check'   -> (True,  True)
    """
    st = (shot_type or "").lower()
    use_rag = ("kb-rag" in st) or ("kbrag" in st) or ("rag" in st)
    use_sc = ("self-check" in st) or ("selfcheck" in st) or ("self_check" in st)
    return use_rag, use_sc


_RAG_BLOCK_CACHE: dict = {}


def _load_rag_context_block(qid):
    """Load the pre-rendered KB-RAG prompt block for a question id (cached). '' if absent."""
    if qid in _RAG_BLOCK_CACHE:
        return _RAG_BLOCK_CACHE[qid]
    path = os.path.join(RAG_CONTEXT_DIR, f'rag_context_{qid}.json')
    block = ""
    if os.path.exists(path):
        try:
            block = json.load(open(path, encoding='utf-8')).get("prompt_block", "")
        except Exception:
            block = ""
    _RAG_BLOCK_CACHE[qid] = block
    return block


def generate_model_prompt(question, restrictions, standard_responses=None, shot_type="1-shot", rag_context_block=""):
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
        rag_context_block (str): 可选的 KB-RAG 检索上下文。为空时行为与原 1-shot 完全一致；
            非空时在 "Your Task Steps" 之前注入一段非泄漏的领域 grounding。
    """
    # 格式化限制条件（DEFAULT_RESTRICT 的值是 set，里面包着一个顿号分隔的字符串）
    restrict_lines = []
    for key, value in restrictions.items():
        if isinstance(value, set):
            # set 中通常只有一个字符串元素
            value_str = '、'.join(sorted(value))
        else:
            value_str = str(value)
        restrict_lines.append(f"{key}:{{{value_str}}}")
    restrict_str = "\n".join(restrict_lines)

    # 使用模板并替换占位符
    prompt = TEST_MODEL_GENERATION_PROMPT.replace("[specific_question]", question['question'])
    prompt = prompt.replace("{{restrictions}}", restrict_str)

    # KB-RAG: 在任务步骤前注入检索到的知识库上下文（若提供）。
    if rag_context_block:
        anchor = "**Your Task Steps:**"
        block = (
            "\n" + rag_context_block.strip() + "\n"
            "Use the retrieved knowledge-base context above as domain grounding: choose a "
            "target-specific marker for each required labeling target, pair it with a "
            "fluorophore/method combination marked compatible, and select a clearing method "
            "that is established for this sample tier. The context deliberately omits exact "
            "refractive-index and timing values.\n\n"
        )
        prompt = prompt.replace(anchor, block + anchor, 1)

    return prompt

async def get_model_response(model_instance, prompt):
    try:
        response_data = await model_instance._acall(prompt)
        return response_data.get("content", "")
    except Exception as e:
        print(f"获取模型回答出错: {e}")
        return ""


# Fixed self-check checklist (cheap alternative to self-consistency): one grounded
# review + single revision. Targets the known failure modes without leaking numbers.
SELF_CHECK_PROMPT = """You previously produced the tissue-clearing protocol below. Before finalizing, run this fixed checklist against the retrieved knowledge-base context and your own protocol, then output a single corrected protocol.

{context}

--- YOUR CURRENT PROTOCOL ---
{protocol}
--- END OF YOUR CURRENT PROTOCOL ---

Checklist (fix any item that fails; do not introduce new violations):
1. Target match: does each fluorescent marker you chose correspond to a target-specific marker for the required labeling target (not a pan-lineage marker and not a bare nuclear counterstain)?
2. Marker-fluorophore compatibility: is each marker paired with a compatible fluorophore (avoid any pair listed as 'avoid')?
3. Method-fluorophore compatibility: is your fluorophore choice compatible with the chosen clearing method (avoid statuses marked 'avoid')?
4. Method-tier support: is the chosen clearing method established for this sample tier (per the feasibility list)?
5. Timing plausibility: is the clearing time order-of-magnitude appropriate for this sample tier?
6. RI / medium: is the clearing-medium family appropriate (e.g. do not rely on endogenous fluorescent proteins together with an FP-quenching solvent method)?

Output the FULL corrected protocol in the EXACT same format as before (starting with '**Chosen Method:**', then '**Chosen Labeling:**', then '**Justification:**', then '**Protocol Steps:**'), even if you make no changes. Output only the protocol, with no commentary about the checklist."""


async def self_check_and_revise(model_instance, first_answer, rag_context_block):
    """One grounded self-check + single revision. Returns the first answer unchanged if
    the revised output is empty/invalid."""
    prompt = SELF_CHECK_PROMPT.format(
        context=(rag_context_block or "(no retrieved context available)"),
        protocol=first_answer,
    )
    revised = await get_model_response(model_instance, prompt)
    return revised if _is_valid_response(revised) else first_answer

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
    计算两个向量的余弦相似度（保留备用）
    """
    import numpy as np  # Optional legacy helper; the grading path is standard-library only.
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


# ---- SIGNED method-fit (ported from results/refresh_s_method.py, 2026-07-01) ----
# Capability space: F_fp/P_dye/M_geo/E_ops/S_safe in [-1,+1] (+ helps the objective,
# - actively harms it); C_opt is a non-negative clearing-power magnitude [0,1].
_MS_SIGNED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "dataset/Q+AR/src/model_space_signed.json")
try:
    with open(_MS_SIGNED_PATH, encoding="utf-8") as _f:
        MODEL_SPACE_SIGNED = json.load(_f).get("methods", {})
except Exception as _e:  # pragma: no cover
    print(f"Warning: could not load model_space_signed.json ({_e}); s_method will gate to 0.")
    MODEL_SPACE_SIGNED = {}

_SM_DIMS = [("fluorescence_protein_preservation", "F_fp"), ("dye_permeability", "P_dye"),
            ("clearing_challenge", "C_opt"), ("geometry_preference", "M_geo"),
            ("operational_economy", "E_ops"), ("safety_compatibility", "S_safe")]
S_METHOD_MAX = 2.5   # signed score normalizes to symmetric [-1,+1]
_SM_DWEIGHT = 2.0    # emphasis on the winning labeling axis (F_fp xor P_dye)


def _sm_norm(s):
    s = str(s or "").lower()
    for ch in " -_/()":
        s = s.replace(ch, "")
    return s.replace("+", "")


def find_signed_method(name):
    """Match an extracted method name to a signed capability vector (with organic-solvent fallback)."""
    nl = _sm_norm(name)
    if not nl:
        return None
    for k, v in MODEL_SPACE_SIGNED.items():
        kl = _sm_norm(k)
        if (nl in kl or kl in nl) and min(len(nl), len(kl)) >= 3:
            return v
    for kw, canon in (("3disco", "3DISCO"), ("thf", "3DISCO"), ("dbe", "3DISCO"),
                      ("dcm", "3DISCO"), ("babb", "BABB"), ("benzyl", "BABB"),
                      ("ethylcinnamate", "BABB"), ("idisco", "iDISCO (iDISCO+)"),
                      ("solvent", "3DISCO")):
        if kw in nl and canon in MODEL_SPACE_SIGNED:
            return MODEL_SPACE_SIGNED[canon]
    return None


def calculate_method_suitability(user_pref_vector_dict, method_vector_dict, **kwargs):
    """SIGNED need-weighted method-fit, in [-2.5, +2.5] (max_score 2.5).

    demand strength  ds = scenario_weight * target  (silent axis -> W=0 -> drops out);
    capability read directly from the SIGNED model_space (+ helps / - harms; C_opt magnitude).
    The two labeling axes F_fp/P_dye are MUTUALLY EXCLUSIVE: the axis with the larger weighted
    demand is emphasized (xDWEIGHT), the other zeroed. score = 2.5 * sum(ds*cap)/sum(ds).
    Returns 0.0 (neutral) if no axis is constrained. (kwargs absorbed for backward-compatible calls.)
    """
    if not user_pref_vector_dict or not method_vector_dict:
        return 0.0

    def _dem(longk):
        o = user_pref_vector_dict.get(longk, {}) or {}
        return float(o.get("target", 0) or 0), float(o.get("weight", 0) or 0)

    t_fp, w_fp = _dem("fluorescence_protein_preservation")
    t_pd, w_pd = _dem("dye_permeability")
    mult = {"F_fp": 1.0, "P_dye": 1.0}
    if w_fp * t_fp >= w_pd * t_pd:
        mult["F_fp"], mult["P_dye"] = _SM_DWEIGHT, 0.0
    else:
        mult["F_fp"], mult["P_dye"] = 0.0, _SM_DWEIGHT

    num = den = 0.0
    for longk, short in _SM_DIMS:
        t, w = _dem(longk)
        if short == "M_geo":
            t = min(t, 1.0)   # isotropy demand treated as unipolar preserve-need
        ds = mult.get(short, 1.0) * w * t
        if ds <= 0:
            continue
        num += ds * float(method_vector_dict.get(short, 0) or 0)
        den += ds
    if den <= 0:
        return 0.0
    return float(round(S_METHOD_MAX * (num / den), 4))


# T07/T11 questions tag the PARENT tier, but several methods are stored in the KB only under
# finer sub-tiers (T07A/B, T11A/B). Mirror results/refresh_s_time.py: fall back to the sub-tier
# with the SHORTEST median (so over-long proposals are penalized, not excused).
_PARENT_SUB = {
    "T07_HARD_TISSUE_BONE_TOOTH_COCHLEA": ["T07A_SMALL_HARD_TISSUE_BONE_TOOTH", "T07B_LARGE_HARD_TISSUE_BONE_COCHLEA"],
    "T11_PLANT_WHOLE_SEEDLING": ["T11A_PLANT_LEAF_SMALL_SEEDLING", "T11B_PLANT_WHOLE_SEEDLING_ROOT"],
}


def _time_kb_row(method_key, tier_code):
    """time_kb window dict for (normalized method, tier) with T07/T11 parent-tier fallback
    (shortest-median sub-tier), matching results/refresh_s_time.py."""
    row = TIME_KB_LOOKUP.get(method_key, {}).get(tier_code)
    if row is not None:
        return row
    subs = _PARENT_SUB.get(tier_code)
    if subs:
        cands = [TIME_KB_LOOKUP[method_key][s] for s in subs
                 if TIME_KB_LOOKUP.get(method_key, {}).get(s, {}).get("clearing_time_median_h") is not None]
        if cands:
            return min(cands, key=lambda v: v["clearing_time_median_h"])
    return None


def calculate_effectiveness_score(quantitative_data, user_pref_vector_dict, model_space, marker_dict, marker_query_targets):
    """
    计算有效性评分 E_score
    """
    # 权重
    w1, w2, w3, w4 = 1.0, 1.0, 1.0, 1.0
    
    # 1. S_method: 透明方法选择总体适配度
    method_name = _coerce_str(quantitative_data.get("method_name"), default="")

    # 查找 signed 容量向量（model_space_signed.json，结构 {"methods": {"CUBIC": {"F_fp": x, ...}}}）
    # 通过 find_signed_method 做大小写/部分匹配 + 有机溶剂兜底（BABB/3DISCO 等）
    method_vector_dict = find_signed_method(method_name)

    if method_vector_dict is None:
        # 未匹配到方法：s_method 记为中性 0（signed 区间 [-2.5,+2.5] 的零点）
        if method_name:
            print(f"Warning: Method '{method_name}' not found in signed model_space. s_method=0.")
        s_method = 0.0
    else:
        s_method = calculate_method_suitability(user_pref_vector_dict, method_vector_dict)

    # 2. S_label: 标记与方法兼容性评分 (Python 规则计算)
    # Preprocess: fluorophore keys that are actually markers get moved to marker side,
    # and detect imbalanced entries (marker without fluorophore or vice versa).
    marker_pairs, has_marker_without_fluor, has_fluor_without_marker = _preprocess_marker_dict(marker_dict)

    # 步骤2.1: s_target_match — 标记位点与 question 要求的匹配度
    target_match_scores = []
    for fluor_str, marker_str in marker_pairs:
        # Preserve original behavior: entries without an explicit marker value are not scored.
        if not marker_str:
            continue
        if _match_marker_to_targets(marker_str, marker_query_targets, fluor_name=fluor_str):
            target_match_scores.append(6.0)
        else:
            # Determine specificity tier: 0 = vague/descriptive, 3 = incomplete but inferable, 6 = specific marker
            specificity = _classify_marker_specificity(marker_str, fluor_str, marker_query_targets)
            if specificity == 0:
                target_match_scores.append(0.0)
            elif specificity == 3:
                # Incomplete but reasonable -> half credit
                target_match_scores.append(3.0)
            else:
                # Specific marker: check tissue.json major_category for partial credit
                marker_major = _get_tissue_major_category(marker_str)
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
    for fluor_str, marker_str in marker_pairs:
        if not marker_str:
            continue
        if _is_penalty_fluor(fluor_str):
            marker_fluor_scores.append(0.0)
            continue
        compat = _get_marker_fluor_compat(marker_str, fluor_str)
        if compat is False:
            marker_fluor_scores.append(0.0)
        else:
            # 兼容或未知均给满分（未知时不应 penalize）
            marker_fluor_scores.append(6.0)
    s_marker_fluor_compat = min(marker_fluor_scores) if marker_fluor_scores else 6.0

    # 步骤2.3: s_method_fluor_compat — 荧光团与透明方法兼容性 (method_fluro_compati.json)
    method_fluor_scores = []
    for fluor_str, marker_str in marker_pairs:
        if _is_penalty_fluor(fluor_str):
            method_fluor_scores.append(0.0)
            continue
        compat_val = _get_method_fluor_compat(method_name, fluor_str)
        if compat_val is None:
            method_fluor_scores.append(6.0)  # 未知时不 penalize
        else:
            method_fluor_scores.append(compat_val * 6.0)
    s_method_fluor_compat = min(method_fluor_scores) if method_fluor_scores else 6.0

    s_label = min(s_target_match, s_marker_fluor_compat, s_method_fluor_compat)
    s_label = max(0.0, min(6.0, s_label)) # Clamp to [0, 6]
    # The source table calls these recommended markers, not universally required
    # targets. Expose coverage without silently converting alternatives to AND.
    marker_coverage_audit = {
        'reference_targets': [
            {'marker_name': target.get('marker_name', ''),
             'matched': any(_match_marker_to_targets(marker, [target], fluor_name=fluor)
                            for fluor, marker in marker_pairs)}
            for target in marker_query_targets],
        'requirement_semantics': 'recommended-target metadata; AND/OR requirements require question-specific review',
        'unmatched_reported_markers': [marker or fluor for fluor, marker in marker_pairs
                                     if not _match_marker_to_targets(marker, marker_query_targets, fluor_name=fluor)],
    }

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
    time_kb_supported = bool(_time_kb_row(method_key, tier_code))

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

    # 4. S_time: one computation supplies both the score and its explanation.
    # This version retains the historical asymmetric tolerance (0.20 / 0.10).
    t_act = _coerce_float(quantitative_data.get('total_time_hours'), default=0.0)
    tier_data = _time_kb_row(method_key, tier_code)
    s_time, time_details = time_score_details(t_act, tier_data, tier_code)
    if tier_data is not None:
        time_details['resolved_tier'] = next(
            (key for key, row in TIME_KB_LOOKUP.get(method_key, {}).items() if row is tier_data), tier_code
        )
    time_details['method_key'] = method_key

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
        "marker_coverage_audit": marker_coverage_audit,
        'time_computation': time_details,
        '_s_time_ref_source': time_details['source'],
        '_s_time_t_min': time_details['min_hours'],
        '_s_time_t_max': time_details['max_hours'],
        '_s_time_tau': time_details['tau_hours'],
        '_s_time_t_act': time_details['actual_hours'],
        '_s_time_tier': tier_code,
        # S_trans 调试信息
        "_s_trans_status":        _s_trans_status,
        "_s_trans_ri_tissue":     ri_tissue,
        "_s_trans_ri_method_ref": ri_method_ref,
        "_s_trans_sigma":         _s_trans_sigma,
    }

def validate_teacher_extraction(extraction):
    """Missing output fields are judge failures; explicit null remains observable."""
    if not isinstance(extraction, dict):
        raise ValueError('Teacher extraction must be an object')
    required = {'method_name', 'marker_dict', 'clearing_total_time_hours'}
    if not required.issubset(extraction):
        raise ValueError('Teacher extraction missing required fields: ' + ', '.join(sorted(required - extraction.keys())))
    if extraction['method_name'] is not None and not isinstance(extraction['method_name'], str):
        raise ValueError('Teacher method_name must be a string or explicit null')
    markers = extraction['marker_dict']
    if not isinstance(markers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in markers.items()):
        raise ValueError('Teacher marker_dict must map strings to strings')
    for key in ('clearing_total_time_hours', 'reagent_ri_value', 'sample_ri_value'):
        value = extraction.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                  not math.isfinite(value) or value < 0):
            raise ValueError(f'Teacher {key} must be finite, nonnegative, or explicit null')


def _log_teacher_response(teacher_model_name, qid, prompt_len, raw_content, status, detail=""):
    """Append a structured log entry for every teacher-model call to enable post-hoc debugging.
    The FULL raw teacher response is persisted to a separate file so it can be inspected / replayed later."""
    import datetime
    log_dir = os.path.join(OEQ_SCORE_DIR, 'logs')
    raw_dir = os.path.join(log_dir, 'raw')
    os.makedirs(raw_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
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
    m = re.search(r'^\s*(?:\*\*)?Chosen\s+Method:\s*(?:\*\*)?\s*([^\r\n]+)',
                  model_protocol, re.IGNORECASE | re.MULTILINE)
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

    substitutions = {'question_text': question_text, 'model_generated_protocol': model_protocol,
                     'method_name': method_name, 'sample_size': sample_size or 'Read from QUESTION; do not infer missing dimensions.'}
    prompt = re.sub(r'\{\{(question_text|model_generated_protocol|method_name|sample_size)\}\}',
                    lambda match: substitutions[match.group(1)], rubric)
    # Insert format enforcement just before the rubric sections begin
    prompt = prompt.replace("1. 完整性评估 Prompt (Completeness)", format_enforcement + "1. 完整性评估 Prompt (Completeness)")

    # Fixed vectors are bound to the selected question snapshot before any API call.
    user_pref_vector = fixed_demands().get(qid, question_text)
    snapshot_qid = fixed_demands().questions[str(qid)]['question_id']
    question_meta = {**question_meta, **QUESTION_META_KB[snapshot_qid]}

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
            extraction = {key: llm_output[key] for key in
                          ('marker_dict', 'clearing_total_time_hours', 'method_name', 'reagent_ri_value',
                           'sample_ri_value', 'protocol_time_hours', 'reasoning') if key in llm_output}

        validate_teacher_extraction(extraction)

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
                "evaluated_timestamp": datetime.now(timezone.utc).isoformat(),
                "scoring_version": SCORING_VERSION,
                "judge_prompt_sha256": json_hash(prompt),
                "extraction_status": {
                    'method': 'reported' if extraction['method_name'] else 'explicitly_unreported',
                    'clearing_time': 'reported' if extraction['clearing_total_time_hours'] is not None else 'explicitly_unreported',
                    'markers': 'reported' if extraction['marker_dict'] else 'explicitly_empty',
                },
                "question_sha256": json_hash(fixed_demands().questions[str(qid)]),
                "demand_provenance": fixed_demands().provenance,
            },
            "extraction": extraction,
            "quantitative_data": quantitative_data,
            "user_preference_vector": user_pref_vector,
            "scores": {
                "completeness": completeness,
                "correctness": correctness,
                "effectiveness": {
                    "s_method": {
                        "score": effectiveness_scores["s_method"],
                        "max_score": 2.5,
                        "description": "透明方法选择适配度",
                        "reasoning": f"Signed need-weighted method-fit [-2.5,+2.5] (F_fp xor P_dye x2; caps signed; fixed demand lookup). Method: {quantitative_data.get('method_name')}",
                        "demand_vector": user_pref_vector,
                    },
                    "s_label": {
                        "score": effectiveness_scores["s_label"],
                        "max_score": 6,
                        "description": "标记与方法兼容性",
                        "coverage_audit": effectiveness_scores['marker_coverage_audit'],
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
                        "reasoning": time_reasoning(effectiveness_scores['time_computation']),
                        "computation": effectiveness_scores['time_computation'],
                    },
                    "total_weighted_score": effectiveness_scores["total_effectiveness_score"]
                }
            }
        }

        # A partial/invalid judge result must be recorded as a failure and retried.
        protocol_scores({'evaluation': final_result})
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
    generation_contract = {
        'version': SCORING_VERSION, 'model': model_name, 'shot_type': shot_type,
        'questions_sha256': sha256_file(QUESTION_FILE),
        'template_sha256': sha256_file('prompts/gen_protocol_template.py'),
        'runner_sha256': sha256_file(__file__),
        'restrictions': {key: sorted(value) if isinstance(value, set) else value
                         for key, value in restrictions.items()},
    }
    if any(_shot_flags(shot_type)):
        generation_contract['rag_sha256'] = {
            path.name: sha256_file(path) for path in sorted(Path(RAG_CONTEXT_DIR).glob('rag_context_*.json'))
        }
    ensure_manifest(output_path, generation_contract)
    
    # 加载已有进度，过滤掉无效/空回答
    model_outputs = []
    answered_ids = set()
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                raw_outputs = json.load(f)
            valid_outputs = []
            invalid_ids = []
            seen_ids = set()
            snapshot = {q['question_id']: q['question'] for q in _QUESTION_LIST}
            for item in raw_outputs:
                qid = item['question_id']
                if qid in seen_ids or item.get('specific_question') != snapshot.get(qid):
                    raise ValueError(f'Duplicate or mismatched cached question {qid}')
                seen_ids.add(qid)
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
            raise ValueError(f"Cannot safely resume {output_path}: {e}") from e

    pending_questions = [q for q in questions if q["question_id"] not in answered_ids]
    if not pending_questions:
        print(f"[{model_name}] 所有问题已有有效回答，无需生成。")
        selected = {q['question_id'] for q in questions}
        return [entry for entry in model_outputs if entry['question_id'] in selected]

    use_rag, use_sc = _shot_flags(shot_type)
    if use_rag or use_sc:
        print(f"[{model_name}] setting flags: KB-RAG={use_rag}, self-check={use_sc}")

    print(f"[{model_name}] 待生成 {len(pending_questions)} 题，并发上限 {gen_concurrency}")
    sem = asyncio.Semaphore(gen_concurrency)
    lock = asyncio.Lock()

    async def _gen_one(q):
        async with sem:
            rag_block = _load_rag_context_block(q["question_id"]) if use_rag else ""
            if use_rag and not rag_block:
                raise ValueError(f"Missing RAG context for question {q['question_id']}; cannot label this run KB-RAG.")
            prompt = generate_model_prompt(q, restrictions, standard_responses,
                                           shot_type=shot_type, rag_context_block=rag_block)
            first_response = await get_model_response(model_instance, prompt)
            response_text = first_response
            sc_applied = False
            if use_sc and _is_valid_response(first_response):
                response_text = await self_check_and_revise(model_instance, first_response, rag_block)
                sc_applied = True
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
                "shot_type": shot_type,
                "rag_grounded": use_rag,
                "self_check_applied": sc_applied,
            }
            if use_sc:
                output_entry["first_response"] = first_response
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
    selected = {q['question_id'] for q in questions}
    return [entry for entry in model_outputs if entry['question_id'] in selected]

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
    # Validate the entire selected input before making any teacher calls.
    response_by_id = {entry['question_id']: entry for entry in responses}
    if len(response_by_id) != len(responses):
        raise ValueError('Duplicate response question IDs')
    for entry in responses:
        fixed_demands().get(entry['question_id'], entry['specific_question'])
    contract = {**scoring_contract(teacher_model), 'model': model_name, 'setting': shot_type}
    contract_hash = ensure_manifest(result_path, contract)

    # 加载已有评分进度（将空 evaluation {} 或包含 _error 的视为未完成）
    results = []
    evaluated_ids = set()
    if os.path.exists(result_path):
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                raw_results = json.load(f)
            seen_ids = set()
            for item in raw_results:
                qid = item['question_id']
                if item.get('scoring_contract_sha256') != contract_hash:
                    raise ValueError(f'Scoring contract changed for question {qid}')
                if qid in response_by_id and item.get('response_sha256') != json_hash(response_by_id[qid]):
                    raise ValueError(f'Response changed for question {qid}; select a new score directory')
                if qid in seen_ids:
                    raise ValueError(f'Duplicate cached score for question {qid}')
                seen_ids.add(qid)
                if qid not in response_by_id:
                    results.append(item)  # Preserve other subsets, including their failures.
                    continue
                ev = item.get('evaluation')
                if not ev or not isinstance(ev, dict) or ev.get('_error'):
                    continue
                try:
                    protocol_scores(item)
                except ValueError:
                    continue
                results.append(item)
                evaluated_ids.add(item['question_id'])
            skipped = len(raw_results) - len(results)
            if skipped:
                print(f"[{model_name}] 检测到已有进度 {len(raw_results)} 条，其中 {skipped} 条为空/失败/评分不完整，将重新评估。有效 {len(results)}/{len(responses)} 个。")
            else:
                print(f"[{model_name}] 检测到已有评分进度，已完成 {len(results)}/{len(responses)} 个评估。")
        except Exception as e:
            raise ValueError(f"Cannot safely resume {result_path}: {e}") from e

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
        result_entry = {"question_id": qid, "evaluation": score,
                        "scoring_contract_sha256": contract_hash,
                        "response_sha256": json_hash(entry)}
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
            all_qids = {q['question_id'] for q in questions}
            valid_responses = [r for r in responses if r.get('question_id') in all_qids
                               and _is_valid_response(r.get('model_response'))]
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
                    saved_results = json.load(f)
                selected_ids = {q['question_id'] for q in questions}
                for item in saved_results:
                    if item.get('question_id') not in selected_ids:
                        continue
                    try:
                        protocol_scores(item)
                    except ValueError:
                        continue
                    summary['n_evaluated'] += 1
                if summary['n_evaluated'] < len(questions):
                    summary['error'] = f"Incomplete grading: {summary['n_evaluated']}/{len(questions)} valid scores"
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
    global RAG_CONTEXT_DIR, OEQ_SCORE_DIR, OEQ_OUTPUT_DIR, DEMAND_FILE, DEMAND_MANIFEST
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
    parser.add_argument("--rag-dir", default=None,
                        help="Override the KB-RAG context directory (e.g. dataset/Q+AR/rag_context_v2)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N questions (dev subset, applies to gen + eval)")
    parser.add_argument("--qids", nargs="*", type=int, default=None,
                        help="Only run these specific question ids (stratified sample; overrides --limit)")
    parser.add_argument("--score-dir", default=None,
                        help="Override the evaluation-results output dir (keeps canonical results untouched)")
    parser.add_argument('--response-dir', default=None,
                        help='Generation output directory, or existing responses for --eval-only')
    parser.add_argument('--question-file', default=QUESTION_FILE,
                        help='Question snapshot matching the responses and fixed demand manifest')
    parser.add_argument('--demand-vectors', default=DEMAND_FILE)
    parser.add_argument('--demand-manifest', default=None,
                        help='Default: <demand-vectors>.manifest.json; binds vectors to a question snapshot')
    args = parser.parse_args(argv)

    if args.eval_only and args.no_evaluation:
        print("错误：--eval-only 和 --no-evaluation 互斥")
        return 2

    if args.rag_dir:
        RAG_CONTEXT_DIR = args.rag_dir
        _RAG_BLOCK_CACHE.clear()
        print(f"KB-RAG context dir: {RAG_CONTEXT_DIR}")
    if args.score_dir:
        OEQ_SCORE_DIR = args.score_dir
        os.makedirs(OEQ_SCORE_DIR, exist_ok=True)
        print(f"score output dir: {OEQ_SCORE_DIR}")
    if args.response_dir:
        OEQ_OUTPUT_DIR = args.response_dir
    for directory, historical, writing in (
        (OEQ_SCORE_DIR, 'dataset/Q+AR/result', not args.no_evaluation),
        (OEQ_OUTPUT_DIR, 'dataset/Q+AR/model_response', not args.eval_only),
    ):
        if writing and Path(directory).resolve().is_relative_to(Path(historical).resolve()):
            parser.error(f'Historical output directory is read-only for this runner: {historical}')
    DEMAND_FILE, DEMAND_MANIFEST = args.demand_vectors, args.demand_manifest
    configure_question_snapshot(args.question_file)
    if not args.no_evaluation:
        try:
            fixed_demands()  # Fail on version mismatch before initializing network clients.
        except (ValueError, OSError) as exc:
            parser.error(str(exc))

    # 1. 加载模型管理器
    from models.Model_Loader import ModelLoader
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
    if args.qids:
        idset = set(args.qids)
        questions = [q for q in questions if q["question_id"] in idset]
        print(f"[dev] restricting to {len(questions)} specified question ids")
    elif args.limit:
        questions = questions[:args.limit]
        print(f"[dev] limiting to first {len(questions)} questions")
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
