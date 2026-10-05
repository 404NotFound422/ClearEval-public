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



# Embedded Python with a ._pth file does not add the script directory.

if __name__ == "__main__":

    sys.path.insert(0, str(Path(__file__).resolve().parent))



from verified_marker_aliases import IDENTITY_VERSION, same_verified_target, marker_identity_conflict

from evaluation_contract import (

    SCORING_VERSION, FixedDemandRegistry, CurrentDemandRegistry, ensure_manifest, json_hash, sha256_file,

    time_score_details, time_reasoning,

)

from results.oeq_metrics import protocol_scores
from benchmark_scoring import (
    IncompleteBenchmarkScore, promote_benchmark_estimate, promote_unresolved_benchmark,
    is_benchmark_complete, is_benchmark_record_complete, summarize_benchmark_estimates,
)

from evaluator_integrity import (

    INTEGRITY_VERSION, JudgeFormatError, strip_json_fence, parse_judge_object,

    resolve_method, method_identity, validate_legacy_extraction,

    validate_score_proposals, extraction_field_states, legacy_integrity_audit, summarize_legacy_diagnostics,

)

from prompts.gen_protocol_template import TEST_MODEL_GENERATION_PROMPT

from prompts.parse_user_preference_vector import USER_PREFERENCE_PROMPT



OEQ_OUTPUT_DIR = 'dataset/Q+AR/model_response_scoring_v2'

OEQ_SCORE_DIR = 'dataset/Q+AR/result_scoring_v2'

QUESTION_FILE = 'dataset/Q+AR/src/question_final.json'

DEMAND_FILE = 'dataset/Q+AR/src/demand_vectors_all.json'

DEMAND_MANIFEST = None

DEMAND_PROFILE = 'fixed'

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

        _FIXED_DEMANDS = (CurrentDemandRegistry(QUESTION_FILE) if DEMAND_PROFILE == 'current-proposal'

                          else FixedDemandRegistry(QUESTION_FILE, DEMAND_FILE, DEMAND_MANIFEST))

    return _FIXED_DEMANDS





def _model_run_binding(model):

    """Public runtime options plus opaque config fingerprints; no keys/endpoints."""

    options = {}

    for field in ("model_name", "temperature", "max_tokens", "max_length", "top_p",

                  "frequency_penalty", "presence_penalty", "enable_thinking", "timeout", "transport", "format", "num_ctx", "seed"):

        value = getattr(model, field, None)

        if isinstance(value, (str, int, float, bool, dict, list)) or value is None:

            options[field] = value

    return {

        "configuration_sha256": getattr(model, "_configuration_sha256", None),

        "configuration_file_sha256": getattr(model, "_configuration_file_sha256", None),

        "effective_options": options,

        "adapter_source_sha256": {

            path: sha256_file(path) for path in (

                "models/Model_Loader.py", "models/Ollama_LLM.py",

                "models/OpenAI_Model.py", "models/GLM_Model.py",

                "models/Gemini_Model.py", "models/Huggingface_LLM.py",

            ) if Path(path).is_file()

        },

    }





def scoring_contract(teacher_model, assessment_mode="benchmark", task_contexts=None, robustness_inputs=None):

    paths = [

        'OEQ_run_grading_new.py', 'evaluation_contract.py', 'results/oeq_metrics.py',

        'verified_marker_aliases.py', 'evaluator_integrity.py',

        'prompts/eval_oeq_teacher_rubric.txt', 'dataset/Q+AR/src/model_space_signed.json',

        'KnowledgeBase/tissue.json', 'KnowledgeBase/method_fluro_compati.json',

        'KnowledgeBase/time_kb.json', 'KnowledgeBase/tissue_ri.json',

        'KnowledgeBase/method_sigma_ri.json', 'KnowledgeBase/method_ri_ref.json',

    ]

    if assessment_mode not in {'grounded', 'legacy', 'benchmark'}:

        raise ValueError('Unknown assessment mode')

    if assessment_mode == 'benchmark':

        paths.extend(['benchmark_scoring.py', 'oeq_workflow_diagnostics.py', 'oeq_robustness.py',
                      'oeq_fidelity_impact.py', 'oeq_objective_bridge.py', 'oeq_score_stability.py',
                      'oeq_quantity_audit.py', 'extract_clearing_time.py'])

    if assessment_mode in {'grounded', 'benchmark'}:

        paths.extend(['oeq_scientific.py', 'prompts/oeq_scientific_assessment.txt',

                      'experiments/evidence_materials/demand_migration.py',

                      'experiments/construct_validity/contract.py',

                      'experiments/construct_validity/fidelity.py',

                      'experiments/construct_validity/evidence.py',

                      'experiments/construct_validity/objectives.py',

                      'experiments/construct_validity/source_conditions.py',
                      'experiments/construct_validity/compact_grounding.py',
                      'experiments/construct_validity/task_state.py',
                       'experiments/construct_validity/task_function_presence.py',
                       'experiments/construct_validity/candidate_binding.py',
                       'experiments/construct_validity/answer_matching.py',
                      'experiments/construct_validity/requirement_scope.py',
                      'models/Ollama_LLM.py', 'models/Model_Loader.py',
                      'prompts/oeq_scientific_record_assessment.txt', 'prompts/oeq_record_output.schema.json'])

        if Path('KnowledgeBase/source_condition_rules.json').is_file():

            paths.append('KnowledgeBase/source_condition_rules.json')

        registry = Path('KnowledgeBase/source_registry.json')
        paths.append('KnowledgeBase/source_registry.json')

        if registry.is_file():

            for source in json.loads(registry.read_text(encoding='utf-8'))['sources']:

                snapshot = source.get('snapshot') or {}

                for key in ('raw_path', 'text_path'):

                    if snapshot.get(key):

                        paths.append(snapshot[key])

    return {

        'assessment_mode': assessment_mode,
        'workflow_diagnostics_required': assessment_mode == 'benchmark',
        'robustness_diagnostics_required': assessment_mode == 'benchmark',
        'robustness_inputs_sha256': json_hash(robustness_inputs) if robustness_inputs is not None else None,

        'task_contexts_sha256': json_hash(task_contexts) if task_contexts is not None else None,

        'scoring_version': SCORING_VERSION, **fixed_demands().provenance,

        'marker_identity_version': IDENTITY_VERSION,

        'integrity_version': INTEGRITY_VERSION,

        'teacher_model': getattr(teacher_model, 'model_name', 'unknown_teacher'),

        'teacher_runtime_binding': _model_run_binding(teacher_model),

        'source_registry_sha256': sha256_file("KnowledgeBase/source_registry.json")

        if Path("KnowledgeBase/source_registry.json").is_file() else None,

        'source_sha256': {path: sha256_file(path) for path in paths},

        'marker_specificity_sha256': sha256_file(_MARKER_SPECIFICITY_TIERS_PATH)

        if os.path.exists(_MARKER_SPECIFICITY_TIERS_PATH) else None,

        'fluorophore_evidence_sha256': sha256_file(_FLUOR_EVIDENCE_PATH)

        if os.path.exists(_FLUOR_EVIDENCE_PATH) else None,

    }



def _strip_markdown_fences(text: str) -> str:

    """Unwrap one complete fence without isolating or changing a JSON object."""

    return strip_json_fence(text)



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

    # Annotated names may resolve by an exact base/alias, never by a

    # numeric prefix (Alexa Fluor 6470 must not inherit AF647 compatibility).

    keys = {mapping[c] for c in _expand_marker_candidates(fluor_name) if c in mapping}

    return next(iter(keys)) if len(keys) == 1 else None





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

    # Annotated-base resolution may only select an exact declared dye name.

    mapping = {**specific_mapping, **coarse_mapping}

    keys = {mapping[c] for c in _expand_marker_candidates(fluor_name) if c in mapping}

    return next(iter(keys)) if len(keys) == 1 else None





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

    if marker_identity_conflict(name):

        return set()

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

    # A slash can join verified spelling aliases (CD31/PECAM1), not arbitrary targets.

    slash_parts = [_normalize_name(part) for part in re.split(r"[/?]", str(name))]

    if len(slash_parts) > 1 and all(slash_parts):

        for alias, equivalents in _MARKER_ALIASES.items():

            if all(part in {alias, *equivalents} for part in slash_parts):

                candidates.update({alias, *equivalents})

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

    # A known contradictory expansion cannot be rescued by stripping its annotation.

    if marker_identity_conflict(marker_name):

        return None

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

            # Shared prefixes (CD3/CD31, clone suffixes) do not establish identity.



        # Special reporter handling: if target is a reporter and fluor is a reporter fluorophore

        if fluor_name and _is_reporter_target(target_name) and _is_reporter_fluor(fluor_name):

            fluor_set = _expand_marker_candidates(fluor_name)

            reporter_base = re.sub(r"\breporter\b", "", str(target_name), flags=re.IGNORECASE).strip()

            if fluor_set & _expand_marker_candidates(reporter_base):

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

    """Exact table identity only: True/False/None remain distinct."""

    row = _tissue_by_marker.get(_normalize_name(marker_name))

    if not row:

        # Alias expansion may select one exact authored row; substrings may not.

        rows = [_tissue_by_marker[c] for c in _expand_marker_candidates(marker_name)

                if c in _tissue_by_marker]

        distinct = {id(r): r for r in rows}

        row = next(iter(distinct.values())) if len(distinct) == 1 else None

    if not row:

        return None

    col = _map_fluor_to_tissue_col(fluor_name)

    if not col:

        return None

    val = row.get(col)

    if val == 0:

        return False

    if val == 1:

        return True

    return None



def _get_method_fluor_compat(method_name, fluor_name):

    """Resolve exactly one authored method row; absent cells stay unknown."""

    method_key = resolve_method(method_name, _method_fluoro_by_method)

    row = _method_fluoro_by_method.get(method_key)

    if row is None:

        return None

    key = _map_fluor_to_method_key(fluor_name)

    val = row.get(key) if key else None

    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not 0 <= val <= 1:

        return None

    return float(val)





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

_TIME_SOURCE_SCOPE = {

    (row.get("method"), row.get("tier_code")): {

        key: row[key] for key in ("time_scope", "time_excludes_labeling") if key in row

    } for row in _TIME_KB_RAW.get("rows", []) if isinstance(row, dict)

}

TIME_KB_LOOKUP: dict = {}

for _method_key, _tiers in _TIME_KB_RAW.get("lookup", {}).items():

    TIME_KB_LOOKUP[_normalize_name(_method_key)] = {

        tier: dict(row, **_TIME_SOURCE_SCOPE.get((_method_key, tier), {}))

        for tier, row in _tiers.items()

    }



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

    if not isinstance(text, str):

        return False

    s = text.strip()

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

    """Require a current question/demand/source binding before using KB-RAG."""

    path = Path(RAG_CONTEXT_DIR) / f"rag_context_{qid}.json"

    if not path.is_file():

        raise ValueError(f"KB-RAG requested but context card is missing: {path}")

    try:

        card = parse_judge_object(path.read_text(encoding="utf-8"))

    except (OSError, ValueError) as exc:

        raise ValueError(f"KB-RAG context card cannot be parsed: {path}") from exc

    binding = card.get("input_binding")

    if not isinstance(binding, dict):

        raise ValueError(f"KB-RAG context card has no input_binding; rebuild it: {path}")

    if binding.get("schema_version") != "question-kb-rag-binding-v2":

        raise ValueError(f"KB-RAG context card has an unsupported binding version; rebuild it: {path}")

    checksum = card.get("card_content_sha256")

    payload = {key: value for key, value in card.items() if key != "card_content_sha256"}

    if not isinstance(checksum, str) or checksum != json_hash(payload):

        raise ValueError(f"KB-RAG card content checksum mismatch; rebuild it: {path}")

    index_path = Path(RAG_CONTEXT_DIR) / "rag_context_index.json"

    if index_path.is_file():

        try:

            index = parse_judge_object(index_path.read_text(encoding="utf-8"))

        except (OSError, ValueError) as exc:

            raise ValueError(f"KB-RAG card index cannot be parsed: {index_path}") from exc

        cards = index.get("cards")

        if not isinstance(cards, dict) or cards.get(path.name) != checksum:

            raise ValueError(f"KB-RAG card differs from its immutable index: {path}")

    matches = [q for q in _QUESTION_LIST if str(q.get("question_id")) == str(qid)]

    if len(matches) != 1:

        raise ValueError(f"KB-RAG question identity is missing or ambiguous: {qid}")

    question = matches[0]

    try:

        current_questions = json.loads(Path(QUESTION_FILE).read_text(encoding="utf-8"))

        if json_hash(current_questions) != json_hash(_QUESTION_LIST):

            raise ValueError("KB-RAG question file changed after loading; select a fresh explicit snapshot.")

        registry_snapshot = fixed_demands()

        if DEMAND_PROFILE == 'current-proposal':

            fresh = CurrentDemandRegistry(QUESTION_FILE)

            if fresh.provenance != registry_snapshot.provenance:

                raise ValueError('KB-RAG current-task projection changed after loading')

        else:

            current_vectors = json.loads(Path(DEMAND_FILE).read_text(encoding="utf-8"))

            if json_hash(current_vectors) != json_hash(registry_snapshot.vectors):

                raise ValueError("KB-RAG demand file changed after loading; select a fresh explicit snapshot.")

            manifest = DEMAND_MANIFEST or str(DEMAND_FILE) + ".manifest.json"

            if sha256_file(manifest) != registry_snapshot.provenance["demand_manifest_sha256"]:

                raise ValueError("KB-RAG demand manifest changed after loading.")

    except OSError as exc:

        raise ValueError("KB-RAG bound question/demand resource is missing or unreadable.") from exc

    if binding.get("question_sha256") != json_hash(question):

        raise ValueError(f"KB-RAG question metadata/version mismatch: {qid}")

    if binding.get("question_text_sha256") != json_hash(question["question"]):

        raise ValueError(f"KB-RAG question text mismatch: {qid}")

    vector = fixed_demands().get(qid, question["question"])

    if binding.get("demand_sha256") != json_hash(vector):

        raise ValueError(f"KB-RAG fixed-demand version mismatch: {qid}")

    sources = binding.get("kb_files_sha256")

    required = {

        "KnowledgeBase/tissue.json", "KnowledgeBase/method_fluro_compati.json",

        "KnowledgeBase/method_ri_ref.json", "KnowledgeBase/time_kb.json",

        "dataset/Q+AR/src/model_space_signed.json",

    }

    registry = "KnowledgeBase/source_registry.json"

    if Path(registry).is_file():

        required.add(registry)

    if not isinstance(sources, dict) or not required.issubset(sources):

        raise ValueError(f"KB-RAG source binding is incomplete: {qid}")

    workspace = Path(".").resolve()

    for source, expected_hash in sources.items():

        if not isinstance(source, str) or not isinstance(expected_hash, str):

            raise ValueError(f"KB-RAG source binding has invalid types: {qid}")

        source_path = Path(source).resolve()

        if not source_path.is_relative_to(workspace) or not source_path.is_file():

            raise ValueError(f"KB-RAG bound source is missing or outside the workspace: {source}")

        if sha256_file(source_path) != expected_hash:

            raise ValueError(f"KB-RAG source version mismatch: {source}")

    if registry in required and binding.get("source_registry_sha256") != sources[registry]:

        raise ValueError(f"KB-RAG source registry binding mismatch: {qid}")

    block = card.get("prompt_block")

    if not isinstance(block, str) or not block.strip():

        raise ValueError(f"KB-RAG context card has an empty prompt_block: {path}")

    key = (str(qid), json_hash(binding), sha256_file(path))

    if key not in _RAG_BLOCK_CACHE:

        _RAG_BLOCK_CACHE[key] = block

    return _RAG_BLOCK_CACHE[key]





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



def _provider_generation_failed(metadata):

    if not isinstance(metadata, dict):

        return True

    status = metadata.get("technical_status")

    if status is not None and status not in ("VALID", "COMPLETE", "SUCCESS"):

        return True

    reason = metadata.get("finish_reason", metadata.get("done_reason"))

    if reason in ("length", "max_tokens", "limit", "content_filter", "tool_calls", "function_call"):

        return True

    provider = metadata.get("provider_response")

    return isinstance(provider, dict) and (

        provider.get("done") is False or provider.get("done_reason") in ("length", "max_tokens", "limit"))





def _is_valid_generated_entry(entry):

    """A long partial answer is still a technical failure."""

    if not isinstance(entry, dict) or not _is_valid_response(entry.get("model_response")):

        return False

    if entry.get("generation_status", "VALID") != "VALID":

        return False

    generation = entry.get("generation")

    if generation is not None:

        if not isinstance(generation, dict) or generation.get("technical_status") != "VALID":

            return False

        if _provider_generation_failed(generation.get("metadata", {})):

            return False

    for field in ("generation_metadata", "provider_metadata", "metadata"):

        if field in entry and _provider_generation_failed(entry[field]):

            return False

    return True





async def get_model_response(model_instance, prompt, return_data=False, validate_protocol=True):

    """Keep provider evidence and technical failures; legacy callers can request text."""

    started = datetime.now(timezone.utc).isoformat()

    monotonic = asyncio.get_running_loop().time()

    response_data, exception_type = None, None

    try:

        response_data = await model_instance._acall(prompt)

    except Exception as exc:

        exception_type = type(exc).__name__

        response_data = getattr(exc, "response_data", None)

        print(f"获取模型回答出错: {exception_type}")

    metadata = response_data.get("metadata", {}) if isinstance(response_data, dict) else {}

    content = response_data.get("content") if isinstance(response_data, dict) else None

    raw_content = response_data.get("raw_content") if isinstance(response_data, dict) else None

    failure = None

    if exception_type:

        failure = "PROVIDER_EXCEPTION"

    elif not isinstance(response_data, dict) or not isinstance(metadata, dict):

        failure = "INVALID_RESPONSE_STRUCTURE"

    elif _provider_generation_failed(metadata):

        failure = "PROVIDER_TECHNICAL_FAILURE"

    elif (not isinstance(content, str) or not content.strip()

          or (validate_protocol and not _is_valid_response(content))):

        failure = "EMPTY_OR_INVALID_CONTENT"

    record = {"content": content if failure is None else "",

        "raw_content": raw_content if isinstance(raw_content, str) else (content if isinstance(content, str) else None),

        "metadata": metadata if isinstance(metadata, dict) else {},

        "technical_status": "FAILED" if failure else "VALID", "failure_code": failure,

        "error_type": exception_type, "started_utc": started,

        "finished_utc": datetime.now(timezone.utc).isoformat(),

        "elapsed_seconds": asyncio.get_running_loop().time() - monotonic}

    return record if return_data else record["content"]





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





async def self_check_and_revise(model_instance, first_answer, rag_context_block, return_data=False):

    """A required self-check must complete technically; keep failed revision evidence."""

    prompt = SELF_CHECK_PROMPT.format(

        context=(rag_context_block or "(no retrieved context available)"), protocol=first_answer)

    revised = await get_model_response(model_instance, prompt, return_data=True)

    if return_data:

        return revised

    return revised["content"] if revised["technical_status"] == "VALID" else first_answer





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

    """An exact authored key or explicit source-key alias, never the first substring."""

    key = resolve_method(name, MODEL_SPACE_SIGNED)

    return MODEL_SPACE_SIGNED.get(key) if key is not None else None



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





def _marker_target_coverage(marker_pairs, target):

    """Lexical reference coverage only; never scientific requirement satisfaction."""

    outcomes = [_match_marker_to_targets(marker, [target], fluor_name=fluor)

                for fluor, marker in marker_pairs]

    # Preserve an explicit identity conflict rather than silently deleting it.

    conflicts = [marker_identity_conflict(marker) for _, marker in marker_pairs

                 if marker_identity_conflict(marker)]

    target_is_pnad = same_verified_target(target.get("marker_name", ""), "PNAd")

    if conflicts and target_is_pnad:

        matched, status = None, "UNKNOWN_IDENTITY_CONFLICT"

    else:

        matched = any(value is True for value in outcomes)

        status = "LEXICAL_ALIAS_MATCH" if matched else "NOT_MATCHED"

    return {"marker_name": target.get("marker_name", ""), "matched": matched,

            "status": status, "scientific_satisfaction": None,

            "identity_issues": conflicts if target_is_pnad else []}





def calculate_effectiveness_score(quantitative_data, user_pref_vector_dict, model_space, marker_dict, marker_query_targets):

    """Legacy numerical diagnostics; unavailable evidence is nullable, never full credit."""

    def nullable_min(values):

        if not values:

            return None

        if any(v == 0 for v in values):

            return 0.0

        if any(v is None for v in values):

            return None

        return min(values)



    method_name = quantitative_data.get("method_name")

    stages = quantitative_data.get("method_stages")

    identity = method_identity(method_name, MODEL_SPACE_SIGNED, stages)

    vector = find_signed_method(method_name) if identity["status"] == "RESOLVED_SINGLE" else None

    s_method = calculate_method_suitability(user_pref_vector_dict, vector) if vector is not None else None

    marker_pairs, _, _ = _preprocess_marker_dict(marker_dict)

    target_scores, marker_scores, method_scores = [], [], []

    compatibility_audit = []

    for fluor, marker in marker_pairs:

        if marker:

            if marker_identity_conflict(marker):

                target_scores.append(None)

            elif _match_marker_to_targets(marker, marker_query_targets, fluor_name=fluor):

                target_scores.append(6.0)

            else:

                specificity = _classify_marker_specificity(marker, fluor, marker_query_targets)

                major = _get_tissue_major_category(marker)

                question_major = marker_query_targets[0].get("major_category", "") if marker_query_targets else ""

                target_scores.append(0.0 if specificity == 0 else

                                     (3.0 if specificity == 3 or (major and major == question_major) else 0.0))

            compat = False if _is_penalty_fluor(fluor) else _get_marker_fluor_compat(marker, fluor)

            marker_scores.append(0.0 if compat is False else (6.0 if compat is True else None))

            compatibility_audit.append({"kind": "marker_fluor", "marker": marker, "fluorophore": fluor,

                                        "source": "KnowledgeBase/tissue.json", "value": compat,

                                        "status": "UNKNOWN" if compat is None else "TABLE_REPORTED"})

        # Every named stage is inspected, even though no composition score is inferred.

        stage_names = [stage["method_name"] for stage in stages] if stages else (

            identity["components"] if identity["status"] == "COMPOSITE_UNREVIEWED" else [method_name])

        for stage_name in stage_names:

            compat = 0.0 if _is_penalty_fluor(fluor) else _get_method_fluor_compat(stage_name, fluor)

            compatibility_audit.append({"kind": "method_fluor", "method_name": stage_name, "fluorophore": fluor,

                                        "source": "KnowledgeBase/method_fluro_compati.json", "value": compat,

                                        "status": "UNKNOWN" if compat is None else "TABLE_REPORTED"})

            if identity["status"] == "RESOLVED_SINGLE":

                method_scores.append(None if compat is None else 6.0 * compat)

    # A mismatched optional/reference channel is not proof that the conflicted

    # required identity failed. Keep that identity uncertainty through aggregation.

    identity_unresolved = any(marker_identity_conflict(marker) for _, marker in marker_pairs)

    s_target_match = None if identity_unresolved else nullable_min(target_scores)

    s_marker_fluor_compat = nullable_min(marker_scores)

    s_method_fluor_compat = nullable_min(method_scores)

    s_label = nullable_min([s_target_match, s_marker_fluor_compat, s_method_fluor_compat])

    marker_coverage_audit = {

        "reference_targets": [_marker_target_coverage(marker_pairs, target) for target in marker_query_targets],

        "requirement_semantics": "Lexical reference coverage only, not scientific satisfaction; reviewed AND/OR requirements remain necessary",

        "unmatched_reported_markers": [marker or fluor for fluor, marker in marker_pairs

            if not _match_marker_to_targets(marker, marker_query_targets, fluor_name=fluor)],

    }

    tier_code = quantitative_data.get("sample_tier")

    resolved_time = resolve_method(method_name, TIME_KB_LOOKUP) if identity["status"] == "RESOLVED_SINGLE" else None

    method_key = resolved_time or ""

    ri_key = resolve_method(method_name, METHOD_RI_REF_KB) if identity["status"] == "RESOLVED_SINGLE" else None

    sigma_key = resolve_method(method_name, SIGMA_RI_KB) if identity["status"] == "RESOLVED_SINGLE" else None

    ri_tissue = quantitative_data.get("tissue_ri_value")

    ri_method_ref = METHOD_RI_REF_KB.get(ri_key)

    sigma = SIGMA_RI_KB.get(sigma_key, {}).get(tier_code) if tier_code else None

    tier_data = _time_kb_row(method_key, tier_code)

    if not tier_data:

        s_trans, trans_status = None, "missing_kb_or_unresolved_method"

    elif any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0

             for v in (ri_tissue, ri_method_ref, sigma)):

        s_trans, trans_status = None, "missing_or_invalid_reference"

    else:

        s_trans = 3.0 * math.exp(-0.5 * ((ri_tissue - ri_method_ref) / sigma) ** 2)

        trans_status = "legacy_proxy_scored"

    actual_time = quantitative_data.get("total_time_hours")

    s_time, time_details = time_score_details(actual_time, tier_data, tier_code)

    if tier_data is not None:

        time_details["resolved_tier"] = next(

            (key for key, row in TIME_KB_LOOKUP.get(method_key, {}).items() if row is tier_data), tier_code)

    time_details["method_key"] = method_key

    components = [s_method, s_label, s_trans, s_time]

    total = sum(components) if all(v is not None for v in components) else None

    return {"s_method": s_method, "s_label": s_label, "s_trans": s_trans, "s_time": s_time,

            "total_effectiveness_score": total, "s_target_match": s_target_match,

            "s_marker_fluor_compat": s_marker_fluor_compat, "s_method_fluor_compat": s_method_fluor_compat,

            "method_identity": identity, "compatibility_audit": compatibility_audit,

            "marker_coverage_audit": marker_coverage_audit, "time_computation": time_details,

            "_s_time_ref_source": time_details["source"], "_s_time_t_min": time_details["min_hours"],

            "_s_time_t_max": time_details["max_hours"], "_s_time_tau": time_details["tau_hours"],

            "_s_time_t_act": time_details["actual_hours"], "_s_time_tier": tier_code,

            "_s_trans_status": trans_status, "_s_trans_ri_tissue": ri_tissue,

            "_s_trans_ri_method_ref": ri_method_ref, "_s_trans_sigma": sigma}



def validate_teacher_extraction(extraction):

    """Validate raw teacher fields; no defaults, type coercion or hidden inference."""

    return validate_legacy_extraction(extraction)



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





async def evaluate_response_with_teacher(teacher_model, question_text, model_protocol, model_space, question_meta, prompt_template, *, recorded_generation=None):

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

        return {"_error": "Unable to read grading rubric", "_error_type": type(e).__name__,

                "technical_status": "FAILED", "failure_stage": "RUBRIC_LOAD"}

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

        if recorded_generation is None:

            teacher_generation = await get_model_response(

                teacher_model, prompt, return_data=True, validate_protocol=False)

        else:

            import copy

            teacher_generation = copy.deepcopy(recorded_generation)

        content = teacher_generation["content"].strip()

        if teacher_generation["technical_status"] != "VALID":

            raw = teacher_generation.get("raw_content") or ""

            _log_teacher_response(teacher_model_name, qid, len(prompt), raw,

                                  "teacher_generation_failed", teacher_generation["failure_code"])

            return {

                "_error": "Teacher generation failed: " + teacher_generation["failure_code"],

                "_error_type": teacher_generation.get("error_type"),

                "technical_status": "FAILED",

                "failure_stage": "EMPTY_CONTENT" if teacher_generation["failure_code"] == "EMPTY_OR_INVALID_CONTENT" else "TEACHER_GENERATION",

                "teacher_generation": teacher_generation, "_question_id": qid,

            }



        try:

            llm_output = parse_judge_object(content)

        except JudgeFormatError as je:

            _log_teacher_response(teacher_model_name, qid, len(prompt), content, "json_parse_failed", str(je))

            return {"_error": str(je), "_error_type": "JudgeFormatError",

                    "technical_status": "FAILED", "failure_stage": "JSON_PARSE",

                    "_raw_content_preview": content[:2000], "_question_id": qid,

                    "teacher_generation": teacher_generation}



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

        validate_score_proposals(scores_block)



        completeness = scores_block.get("completeness", {})

        correctness  = scores_block.get("correctness", {})



        # Raw nulls and optional absence remain observable. No inferred KB parameter

        # is ever inserted into the model's extracted answer.

        quantitative_data = {

            "method_name": extraction["method_name"],

            "tissue_ri_value": question_meta.get("tissue_ri_value"),

            "total_time_hours": extraction["clearing_total_time_hours"],

            "sample_tier": question_meta.get("tissue_tier_code"),

        }

        for source, target in (("reagent_ri_value", "reagent_ri_value"),

                               ("protocol_time_hours", "protocol_time_hours"),

                               ("method_stages", "method_stages")):

            if source in extraction:

                quantitative_data[target] = extraction[source]

        marker_dict = extraction["marker_dict"]

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

                "extraction_status": extraction_field_states(extraction),

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

                        "reasoning": f"target_match={effectiveness_scores.get('s_target_match')}, marker_fluor_compat={effectiveness_scores.get('s_marker_fluor_compat')}, method_fluor_compat={effectiveness_scores.get('s_method_fluor_compat')}. marker_dict={marker_dict}"

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



        integrity = legacy_integrity_audit(extraction, model_protocol, effectiveness_scores)

        # Keep numerical proposals reviewable while protecting formal downstream

        # aggregation: this legacy representation is not the new evaluator.

        final_result["legacy_diagnostics"] = {

            "scope": "Legacy numeric proposals; not formal CCE or scientific validity",

            "scores": final_result.pop("scores"),

            "method_identity": effectiveness_scores["method_identity"],

            "compatibility_audit": effectiveness_scores["compatibility_audit"],

            "raw_teacher_scores": scores_block,

        }

        final_result["teacher_generation"] = teacher_generation

        final_result.update(technical_status="VALID", scoring_status=integrity["scoring_status"],

                            scientific_status=integrity["scientific_status"], cce_eligible=False,

                            official_scores=None, integrity=integrity)

        if recorded_generation is None:

            _log_teacher_response(teacher_model_name, qid, len(prompt), content, "diagnostic_complete",

                                  "Legacy proposals recorded; formal CCE withheld by integrity guards")

        return final_result



    except Exception as e:

        import traceback

        tb = traceback.format_exc()

        _log_teacher_response(teacher_model_name, qid, len(prompt), content if 'content' in dir() else "", "exception", f"{type(e).__name__}: {e}")

        print(f"评估回答出错 (qid={qid}): {e}")

        print(tb)

        return {"_error": str(e), "_error_type": type(e).__name__, "_traceback": tb,

                "technical_status": "FAILED", "failure_stage": "OUTPUT_VALIDATION",

                "teacher_generation": teacher_generation if "teacher_generation" in locals() else None}



async def evaluate_benchmark_response(teacher_model, entry, model_space, prompt_template, *, recorded_generation=None, robustness_inputs=None):
    """Bind deterministic scientific diagnostics before any numerical judge call."""
    import hashlib
    from oeq_workflow_diagnostics import build_workflow_diagnostics
    registry = fixed_demands()
    registry.get(entry['question_id'], entry['specific_question'])
    question = registry.questions[str(entry['question_id'])]
    binding = {'question_sha256': json_hash(question),
               'protocol_sha256': hashlib.sha256(entry['model_response'].encode('utf-8')).hexdigest()}
    attached = {'workflow_diagnostics_required': True, 'workflow_diagnostics_binding': binding}
    try:
        workflow = build_workflow_diagnostics(question, entry['model_response'])
    except (ValueError, TypeError, KeyError, OSError) as exc:
        error = str(exc)
        return {**attached, '_error': error, '_error_type': type(exc).__name__,
                'technical_status': 'FAILED', 'failure_stage': 'WORKFLOW_DIAGNOSTICS',
                'workflow_diagnostics_failure': {'input_binding': binding, 'error': error,
                                                 'error_type': type(exc).__name__},
                'scientific_status': 'UNRESOLVED', 'cce_eligible': False, 'official_scores': None}
    from oeq_robustness import validate_bundle
    robustness_inputs = validate_bundle(robustness_inputs, question, entry['model_response'])
    attached.update(workflow_diagnostics=workflow, workflow_diagnostics_sha256=json_hash(workflow))
    try:
        diagnostic = await evaluate_response_with_teacher(
            teacher_model, entry['specific_question'], entry['model_response'],
            model_space, entry, prompt_template, recorded_generation=recorded_generation,
        )
    except Exception as exc:
        return {**attached, '_error': str(exc), '_error_type': type(exc).__name__,
                'technical_status': 'FAILED', 'failure_stage': 'BENCHMARK_TEACHER',
                'scientific_status': 'UNRESOLVED', 'cce_eligible': False, 'official_scores': None}
    diagnostic.update(attached)
    if diagnostic.get('_error'):
        diagnostic['technical_status'] = 'FAILED'
        return diagnostic
    try:
        from oeq_robustness import attach_report
        diagnostic = attach_report(diagnostic, question, entry['model_response'], robustness_inputs,
                                   marker_query_targets=entry.get('marker_query_targets'))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        diagnostic.update(_error=str(exc), _error_type=type(exc).__name__,
                          technical_status='FAILED', failure_stage='ROBUSTNESS_VALIDATION')
        return diagnostic
    try:
        return promote_benchmark_estimate(diagnostic, entry['model_response'], registry.provenance)
    except IncompleteBenchmarkScore:
        return promote_unresolved_benchmark(diagnostic, entry['model_response'], registry.provenance)
    except (ValueError, TypeError, KeyError) as exc:
        diagnostic.update(_error=str(exc), _error_type=type(exc).__name__,
                          technical_status='FAILED', failure_stage='BENCHMARK_VALIDATION')
        return diagnostic


async def _benchmark_cached_complete(evaluation, entry, model_space, prompt_template, robustness_inputs=None):
    """Rebuild scientific sidecars and KB math from originals, with zero judge calls.

    A solely missing/changed sidecar is repaired in place; numerical changes
    retain the existing retry behavior. The caller persists a repair history.
    """
    import copy
    from benchmark_scoring import _record_hash
    def numerical_view(value):
        result = copy.deepcopy(value)
        for key in ('workflow_diagnostics_required', 'workflow_diagnostics_binding',
                    'workflow_diagnostics', 'workflow_diagnostics_sha256', 'workflow_diagnostics_failure'):
            result.pop(key, None)
        from oeq_robustness import SIDECAR_FIELDS
        for key in SIDECAR_FIELDS:
            result.pop(key, None)
        result.pop('benchmark_record_sha256', None)
        result.get('meta_data', {}).pop('evaluated_timestamp', None)
        return result
    numerical = numerical_view(evaluation)
    numerical['benchmark_record_sha256'] = _record_hash(numerical)
    if not is_benchmark_record_complete(numerical, entry['model_response']):
        return False
    recomputed = await evaluate_benchmark_response(
        None, entry, model_space, prompt_template,
        recorded_generation=evaluation['teacher_generation'], robustness_inputs=robustness_inputs,
    )
    if (not is_benchmark_record_complete(recomputed, entry['model_response'])
            or numerical_view(recomputed) != numerical_view(evaluation)):
        return False
    # Preserve the recorded timestamp when a deterministic diagnostic is repaired.
    if evaluation.get('meta_data', {}).get('evaluated_timestamp') is not None:
        recomputed['meta_data']['evaluated_timestamp'] = evaluation['meta_data']['evaluated_timestamp']
        recomputed['benchmark_record_sha256'] = _record_hash(recomputed)
    if recomputed != evaluation:
        evaluation.clear()
        evaluation.update(recomputed)
    return True


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

        'model_runtime_binding': _model_run_binding(model_instance),

        'integrity_source_sha256': sha256_file("evaluator_integrity.py"),

        'source_registry_sha256': sha256_file("KnowledgeBase/source_registry.json")

        if Path("KnowledgeBase/source_registry.json").is_file() else None,

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

                if _is_valid_generated_entry(item):

                    valid_outputs.append(item)

                    answered_ids.add(item['question_id'])

                else:

                    invalid_ids.append(item['question_id'])

            model_outputs = raw_outputs

            if invalid_ids:

                print(f"[{model_name}] 检测到 {len(invalid_ids)} 个技术失败/无效回答，将重新生成并保留记录: {invalid_ids}")

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

            first_generation = await get_model_response(model_instance, prompt, return_data=True)

            first_response = first_generation["content"]

            generation = first_generation

            sc_applied = False

            stage_attempts = [first_generation]

            if use_sc and first_generation["technical_status"] == "VALID":

                generation = await self_check_and_revise(model_instance, first_response, rag_block, return_data=True)

                stage_attempts.append(generation)

                sc_applied = generation["technical_status"] == "VALID"

            response_text = generation["content"]

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

                "generation_status": generation["technical_status"],

                "generation": generation,

                "generation_attempts": stage_attempts,

                "shot_type": shot_type,

                "rag_grounded": use_rag,

                "self_check_applied": sc_applied,

            }

            if use_sc:

                output_entry["first_response"] = first_response

            async with lock:

                previous_index = next((index for index, entry in enumerate(model_outputs)

                                       if entry["question_id"] == q["question_id"]), None)

                if previous_index is None:

                    model_outputs.append(output_entry)

                else:

                    previous = model_outputs[previous_index]

                    if _is_valid_generated_entry(previous):

                        return previous

                    prior = previous.get("generation_attempts")

                    if not isinstance(prior, list):

                        prior = [{"content": previous.get("model_response"), "metadata": previous.get("metadata", {}),

                                  "technical_status": "FAILED", "failure_code": "INVALID_CACHED_RESPONSE"}]

                    output_entry["generation_attempts"] = prior + stage_attempts

                    model_outputs[previous_index] = output_entry

                _atomic_write_json(output_path, model_outputs)

                print(f"[{model_name}] 问题 {q['question_id']} 已保存，技术状态={output_entry['generation_status']}")

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







def _grounded_context(entry, task_contexts=None):

    from oeq_scientific import build_context

    registry = fixed_demands()

    registry.get(entry['question_id'], entry['specific_question'])

    question = registry.questions[str(entry['question_id'])]

    study = None

    if task_contexts is not None:

        if not isinstance(task_contexts, dict):

            raise ValueError('Task contexts must map question IDs to frozen objects')

        study = task_contexts.get(str(entry['question_id']))

        if not isinstance(study, dict):

            raise ValueError('Selected question lacks an explicit frozen task context')

        if not study.get('question_sha256') or not study.get('protocol_sha256'):

            raise ValueError('Explicit task context must bind both question and protocol hashes')

    return build_context(question, entry['model_response'], study_context=study)





def _grounded_complete(evaluation, context=None, protocol=None):

    from oeq_scientific import VERSION

    if not isinstance(evaluation, dict) or evaluation.get('_error'):

        return False

    assessment = evaluation.get('grounded_assessment')

    if (evaluation.get('technical_status') != 'VALID'

            or evaluation.get('scoring_status') != 'GROUNDED_REQUIREMENT_ASSESSMENT'

            or evaluation.get('cce_eligible') is not False

            or evaluation.get('official_scores') is not None or 'scores' in evaluation

            or not isinstance(assessment, dict) or assessment.get('schema_version') != VERSION

            or assessment.get('technical_status') != 'VALID'

            or not isinstance(assessment.get('requirement_results'), list)

            or evaluation.get('assessment_sha256') != json_hash(assessment)):

        return False

    condition_diagnostics = evaluation.get('source_condition_diagnostics')

    if (not isinstance(condition_diagnostics, dict)

            or evaluation.get('source_condition_diagnostics_sha256') != json_hash(condition_diagnostics)

            or assessment.get('source_condition_diagnostics') != condition_diagnostics):

        return False

    generation = evaluation.get('teacher_generation')

    if (not isinstance(generation, dict) or generation.get('technical_status') != 'VALID'

            or evaluation.get('teacher_generation_sha256') != json_hash(generation)

            or not isinstance(evaluation.get('teacher_proposal'), dict)):

        return False

    try:

        proposal = parse_judge_object(generation['content'])

        if proposal != evaluation['teacher_proposal']:

            return False

        if context is None:

            return all(key in assessment for key in ('extraction_fidelity', 'extraction', 'route_results',

                       'overall', 'source_consistency_decision', 'text_completeness_decision',

                       'scientific_applicability_decision', 'objectives', 'abstention_reason'))

        if (assessment.get('context_sha256') != context['context_sha256']

                or evaluation.get('prompt_sha256') != context['prompt_sha256'] or protocol is None):

            return False

        from oeq_scientific import apply_assessment

        return apply_assessment(proposal, context, protocol) == assessment

    except (ValueError, KeyError, TypeError, StopIteration):

        return False







async def evaluate_grounded_response(teacher_model, entry, context=None):

    """One structured teacher call followed by actual source/field/requirement guards."""

    from oeq_scientific import apply_assessment

    context = context or _grounded_context(entry)

    generation = await get_model_response(teacher_model, context['prompt'],

                                          return_data=True, validate_protocol=False)

    result = {'technical_status': 'FAILED', 'scoring_status': 'GROUNDED_REQUIREMENT_ASSESSMENT',

              'cce_eligible': False, 'official_scores': None, 'teacher_generation': generation,

              'question_sha256': context['question_sha256'], 'protocol_sha256': context['protocol_sha256'],

              'context_sha256': context['context_sha256'], 'prompt_sha256': context['prompt_sha256'],

              'demand_provenance': fixed_demands().provenance,

              'teacher_generation_sha256': json_hash(generation),

              'source_condition_diagnostics': context['source_condition_diagnostics'],

              'source_condition_diagnostics_sha256': json_hash(context['source_condition_diagnostics'])}

    if generation['technical_status'] != 'VALID':

        result.update(_error='Teacher generation failed: '+generation['failure_code'],

                      failure_stage='TEACHER_GENERATION')

        return result

    try:

        structured = parse_judge_object(generation['content'])

    except (ValueError, TypeError) as exc:

        result.update(_error=str(exc), _error_type=type(exc).__name__, failure_stage='STRUCTURED_PARSE')

        return result

    result['teacher_proposal'] = structured

    try:

        assessment = apply_assessment(structured, context, entry['model_response'])

    except (ValueError, TypeError, KeyError, StopIteration) as exc:

        result.update(_error=str(exc), _error_type=type(exc).__name__, failure_stage='GROUNDING_VALIDATION')

        from oeq_scientific import diagnose_assessment

        try:

            result['grounding_diagnostics'] = diagnose_assessment(structured,entry['model_response'])

            result['grounding_diagnostics_sha256'] = json_hash(result['grounding_diagnostics'])

        except (ValueError,TypeError,KeyError) as diagnostic_error:

            result['diagnostic_error'] = {'message':str(diagnostic_error),'type':type(diagnostic_error).__name__}

        return result

    result.update(technical_status='VALID', grounded_assessment=assessment,

                  assessment_sha256=json_hash(assessment),

                  scientific_status=assessment['scientific_applicability_decision']['status'],

                  meta_data={'teacher_model': getattr(teacher_model,'model_name','unknown_teacher'),

                             'sample_info': entry['specific_question']})

    return result





def summarize_grounded_assessments(items, contexts=None):

    from collections import Counter

    valid = [item['evaluation'] for item in items if _grounded_complete(item.get('evaluation'))]

    reqs = [r for ev in valid for r in ev['grounded_assessment']['requirement_results']]

    states = Counter(r['effective_status'] for r in reqs)

    n = len(reqs)

    decisions = states['SATISFIED'] + states['VIOLATED']

    expected = sum(len(c['requirements']) for c in contexts.values()) if contexts is not None else None

    condition_reports = [item['evaluation']['source_condition_diagnostics'] for item in items

                         if isinstance(item.get('evaluation',{}).get('source_condition_diagnostics'),dict)

                         and item['evaluation'].get('source_condition_diagnostics_sha256') == json_hash(item['evaluation']['source_condition_diagnostics'])]

    return {'source_condition_diagnostic_record_count': len(condition_reports),

            'source_guidance_potential_conflict_count': sum(r['potential_conflict_count'] for r in condition_reports),
            'source_local_potential_risk_count': sum(r.get('local_risk_count', 0) for r in condition_reports),
            'source_author_recipe_nonconformance_count': sum(r.get('author_recipe_nonconformance_count', 0) for r in condition_reports),

            'source_guidance_relation_review_count': sum(r['review_required_count'] for r in condition_reports),

            'source_guidance_scope': 'LOCAL_AUTHOR_RECOMMENDATIONS_NOT_SCIENTIFIC_FAILURE_OR_SUCCESS',

            'assessment_mode': 'grounded', 'selected_record_count': len(items),

            'technical_valid_count': len(valid), 'technical_failure_count': len(items)-len(valid),

            'requirement_count': n, 'effective_status_counts': dict(states),

            'decided_requirement_count': decisions,

            'valid_record_requirement_decision_coverage': decisions/n if n else None,

            'expected_requirement_count': expected,

            'not_assessed_requirement_count': expected-n if expected is not None else None,

            'full_input_requirement_decision_coverage': decisions/expected if expected else None,

            'requirement_decision_coverage': decisions/expected if expected else None,

            'independent_scientific_accuracy': None, 'formal_cce': None,

            'formal_cce_status': 'REQUIRES_INDEPENDENT_SCIENTIFIC_VALIDATION',

            'extraction_inventory_count': sum(ev['grounded_assessment']['extraction_fidelity'].get('independently_declared_fields') is not None for ev in valid),

            'experimental_success_claim': None}





async def evaluate_responses(

    model_name,

    responses,

    teacher_model,

    model_space,

    prompt_template,

    shot_type="1-shot",

    eval_concurrency=4,

    assessment_mode="benchmark",

    task_contexts=None,

    robustness_inputs=None,

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

    contexts = ({entry['question_id']: _grounded_context(entry, task_contexts) for entry in responses}

                if assessment_mode == 'grounded' else {})

    from oeq_robustness import select_bundle
    robustness_bundles = {
        entry['question_id']: select_bundle(robustness_inputs,
            fixed_demands().questions[str(entry['question_id'])], entry['model_response'])
        for entry in responses} if assessment_mode == 'benchmark' else {}
    contract = {**scoring_contract(teacher_model, assessment_mode, task_contexts, robustness_inputs),

                'model': model_name, 'setting': shot_type}

    contract_hash = ensure_manifest(result_path, contract)



    # 加载已有评分进度（将空 evaluation {} 或包含 _error 的视为未完成）

    results = []

    evaluated_ids = set()

    retry_histories = {}
    cache_diagnostics_rebuilt = False

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

                results.append(item)  # Persist all existing records until their own replacement is ready.

                if qid not in response_by_id:

                    continue

                retry_histories[qid] = list(item.get('previous_attempts', [])) + [

                    {key:value for key,value in item.items() if key != 'previous_attempts'}]

                ev = item.get('evaluation')

                if not ev or not isinstance(ev, dict) or ev.get('_error'):

                    continue

                # Scientific unknowns are completed diagnostic records, not

                # transient judge failures. Resume must not repeatedly call a judge.

                if assessment_mode == 'grounded':

                    if not _grounded_complete(ev, contexts[qid], response_by_id[qid]['model_response']):

                        continue

                elif assessment_mode == 'benchmark':

                    import copy
                    original_cache = copy.deepcopy(item)
                    if not await _benchmark_cached_complete(ev, response_by_id[qid], model_space, prompt_template, robustness_bundles[qid]):

                        continue
                    if ev != original_cache['evaluation']:
                        item.setdefault('previous_attempts', []).append({
                            key: value for key, value in original_cache.items() if key != 'previous_attempts'})
                        cache_diagnostics_rebuilt = True

                elif ev.get("scoring_status") == "LEGACY_DIAGNOSTIC_ONLY":

                    if (ev.get("technical_status") != "VALID" or ev.get("cce_eligible") is not False

                            or ev.get("official_scores") is not None or "scores" in ev

                            or not isinstance(ev.get("legacy_diagnostics"), dict)

                            or not isinstance(ev.get("integrity"), dict)

                            or ev["integrity"].get("schema_version") != INTEGRITY_VERSION):

                        continue

                else:

                    try:

                        protocol_scores(item)

                    except ValueError:

                        continue

                evaluated_ids.add(item['question_id'])

            skipped = len(raw_results) - len(results)

            if skipped:

                print(f"[{model_name}] 检测到已有进度 {len(raw_results)} 条，其中 {skipped} 条为空/失败/评分不完整，将重新评估。有效 {len(results)}/{len(responses)} 个。")

            else:

                print(f"[{model_name}] 检测到已有评分进度，已完成 {len(results)}/{len(responses)} 个评估。")

        except Exception as e:

            raise ValueError(f"Cannot safely resume {result_path}: {e}") from e



    def write_diagnostic_summary():

        selected_results = [r for r in results if r.get('question_id') in response_by_id]

        if assessment_mode == 'grounded':

            summary = summarize_grounded_assessments(selected_results, contexts)

        elif assessment_mode == 'benchmark':

            summary = summarize_benchmark_estimates(selected_results)

        else:

            summary = summarize_legacy_diagnostics(selected_results)

        summary["scoring_contract_sha256"] = contract_hash

        summary["source_result_filename"] = os.path.basename(result_path)

        _atomic_write_json(result_path + ".diagnostics.json", summary)



    if cache_diagnostics_rebuilt:
        _atomic_write_json(result_path, results)
    pending = [e for e in responses if e.get('question_id') not in evaluated_ids]

    if not pending:

        write_diagnostic_summary()

        print(f"[{model_name}] 所有 {len(responses)} 题已评估，跳过。")

        return result_path



    print(f"[{model_name}] 待评估 {len(pending)} 题（总 {len(responses)}），并发上限 {eval_concurrency}")



    sem = asyncio.Semaphore(eval_concurrency)

    persist_lock = asyncio.Lock()  # serialize writes to results list + file

    completed = [len(evaluated_ids)]      # mutable counter for closures



    async def _one(entry):

        qid = entry.get('question_id')

        async with sem:

            try:

                if assessment_mode == 'grounded':

                    score = await evaluate_grounded_response(teacher_model, entry, contexts[qid])

                elif assessment_mode == 'benchmark':

                    score = await evaluate_benchmark_response(teacher_model, entry, model_space, prompt_template, robustness_inputs=robustness_bundles[qid])

                else:

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

                        "response_sha256": json_hash(entry),

                        "previous_attempts": retry_histories.get(qid, [])}

        async with persist_lock:

            results[:] = [r for r in results if r.get('question_id') != qid]

            results.append(result_entry)

            completed[0] += 1

            _atomic_write_json(result_path, results)

            print(f"[{model_name}] 评估完成 {completed[0]}/{len(responses)} (qid={qid})")

        return result_entry



    await asyncio.gather(*(_one(e) for e in pending), return_exceptions=False)

    write_diagnostic_summary()



    print(f"[{model_name}] 评估结果已保存至 {result_path} (共 {len(results)} 条)")

    return result_path





async def process_and_evaluate_model(

    model_name, model_instance, questions, restrictions, standard_responses,

    teacher_model, model_space, prompt_template, shot_type="1-shot",

    eval_concurrency=4, gen_concurrency=4, skip_generation=False, skip_evaluation=False,

    assessment_mode="benchmark", task_contexts=None, robustness_inputs=None,

):

    """Per-model pipeline: generate (optionally) then evaluate (optionally).



    - skip_generation=True 用于 --eval-only 模式：直接读取已有的 from_<model>_<shot>.json

    - skip_evaluation=True 用于 --no-evaluation 模式：只生成不评测（旧行为）

    Returns dict {model, shot, n_generated, n_evaluated, error}.

    """

    summary = {"model": model_name, "shot": shot_type, "n_generated": 0, "n_evaluated": 0,

               "n_legacy_diagnostics": 0, "n_grounded_assessments": 0, "n_official_scores": 0,

               "n_benchmark_scores": 0, "n_benchmark_unresolved": 0, "error": None}

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

                               and _is_valid_generated_entry(r)]

            resp_qids = {r['question_id'] for r in valid_responses}

            missing_qids = sorted(all_qids - resp_qids)

            if missing_qids:

                print(

                    f"[{model_name}] WARNING: --eval-only 模式下检测到 {len(missing_qids)} 题缺失/无效 "

                    f"(Missing IDs: {missing_qids})，将继续评估已有的 {len(valid_responses)} 条有效回答。"

                    f"如需补齐缺失题目，请重新运行（不带 --eval-only）。"

                )

            print(f"[{model_name}] --eval-only: 跳过生成，从 {response_path} 加载 {len(valid_responses)} 条有效回答")

        else:

            responses = await process_model(

                model_name, model_instance, questions, restrictions, standard_responses, shot_type=shot_type,

                gen_concurrency=gen_concurrency,

            )

        all_qids = {q["question_id"] for q in questions}

        from collections import Counter

        counts = Counter(entry.get("question_id") for entry in (responses or []) if isinstance(entry, dict))

        expected_questions = {question["question_id"]: question["question"] for question in questions}

        valid_responses = [

            entry for entry in (responses or []) if isinstance(entry, dict)

            and entry.get("question_id") in all_qids and counts[entry.get("question_id")] == 1

            and entry.get("specific_question") == expected_questions[entry["question_id"]]

            and _is_valid_generated_entry(entry)

        ]

        valid_ids = {entry["question_id"] for entry in valid_responses}

        missing_qids = sorted(all_qids - valid_ids)

        summary["n_generated"] = len(valid_ids)

        summary["missing_or_invalid_generation_ids"] = missing_qids

        summary["n_generation_failed"] = len(missing_qids)

        if missing_qids:

            summary["error"] = f"Incomplete generation: {len(valid_ids)}/{len(all_qids)} usable complete responses; missing/invalid IDs={missing_qids}"

        responses = valid_responses



        # Evaluation phase

        if skip_evaluation:

            print(f"[{model_name}] --no-evaluation: 跳过评估")

        else:

            await evaluate_responses(

                model_name, responses, teacher_model, model_space, prompt_template,

                shot_type=shot_type, eval_concurrency=eval_concurrency,

                assessment_mode=assessment_mode, task_contexts=task_contexts, robustness_inputs=robustness_inputs,

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

                    evaluation = item.get("evaluation", {})

                    if assessment_mode == 'benchmark':
                        from benchmark_scoring import is_workflow_obligation_complete
                        if not is_workflow_obligation_complete(evaluation):
                            continue

                        if is_benchmark_complete(evaluation):

                            summary['n_benchmark_scores'] += 1

                            summary['n_evaluated'] += 1

                        elif is_benchmark_record_complete(evaluation):

                            summary['n_benchmark_unresolved'] += 1

                            summary['n_evaluated'] += 1

                        continue

                    if assessment_mode == 'grounded':

                        if _grounded_complete(evaluation):

                            summary['n_grounded_assessments'] += 1

                            summary['n_evaluated'] += 1

                        continue

                    legacy_complete = (

                        evaluation.get("technical_status") == "VALID"

                        and evaluation.get("scoring_status") == "LEGACY_DIAGNOSTIC_ONLY"

                        and evaluation.get("cce_eligible") is False

                        and isinstance(evaluation.get("legacy_diagnostics"), dict)

                    )

                    if legacy_complete:

                        summary["n_legacy_diagnostics"] += 1

                        summary["n_evaluated"] += 1

                        continue

                    # An incomplete diagnostic must not become an official score

                    # merely because it happens to contain numeric fields.

                    continue

                if summary['n_evaluated'] < len(questions):

                    grading_error = f"Incomplete technical grading: {summary['n_evaluated']}/{len(questions)} completed records"

                    summary["error"] = (summary["error"] + "; " + grading_error) if summary["error"] else grading_error

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

    global RAG_CONTEXT_DIR, OEQ_SCORE_DIR, OEQ_OUTPUT_DIR, DEMAND_FILE, DEMAND_MANIFEST, DEMAND_PROFILE

    import argparse

    parser = argparse.ArgumentParser(

        description="OEQ benchmark: generate model responses, then score via teacher LLM. "

                    "By default runs generation followed by concurrent evaluation per model.",

    )

    parser.add_argument("--model-config", default="config/config.yaml",

                        help="Model configuration path (YAML, or JSON without a YAML dependency)")

    parser.add_argument("--preflight-only", action="store_true",

                        help="Read-only resources/version/configuration check; creates no clients or model requests")

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

    parser.add_argument('--assessment-mode', choices=['benchmark', 'grounded', 'legacy'], default='benchmark',

                        help='Default: numerical benchmark estimates, with scientific validation status retained; grounded returns requirement diagnoses; legacy retains historical diagnostics')

    parser.add_argument('--task-contexts', help='Explicit frozen per-question contexts, each bound to unchanged question and protocol')
    parser.add_argument('--robustness-inputs',
                        help='Optional bound manual extraction, complete-candidate and objective inputs for numerical benchmark grading')

    parser.add_argument('--demand-profile', choices=['current-proposal', 'fixed'], default=None,

                        help='Default: current-proposal for current questions (uncalibrated estimates); --demand-vectors or legacy mode select strictly version-bound fixed vectors')

    parser.add_argument('--demand-vectors', default=None)

    parser.add_argument('--demand-manifest', default=None,

                        help='Default: <demand-vectors>.manifest.json; binds vectors to a question snapshot')

    args = parser.parse_args(argv)

    args.demand_profile = args.demand_profile or ('fixed' if args.demand_vectors or args.assessment_mode == 'legacy' else 'current-proposal')

    if args.demand_profile == 'current-proposal' and (args.demand_vectors or args.demand_manifest):

        parser.error('Current task projection does not accept a historical vector/manifest override')

    args.demand_vectors = args.demand_vectors or 'dataset/Q+AR/src/demand_vectors_all.json'

    robustness_inputs = None
    if args.robustness_inputs:
        if args.assessment_mode != 'benchmark':
            parser.error('--robustness-inputs apply only to numerical benchmark grading')
        robustness_inputs = parse_judge_object(Path(args.robustness_inputs).read_text(encoding='utf-8-sig'))
    task_contexts = None

    if args.task_contexts and args.assessment_mode != 'grounded':

        parser.error('--task-contexts apply only to grounded requirement assessment')

    if args.task_contexts:

        task_contexts = parse_judge_object(Path(args.task_contexts).read_text(encoding='utf-8-sig'))



    if args.eval_only and args.no_evaluation:

        print("错误：--eval-only 和 --no-evaluation 互斥")

        return 2



    from oeq_preflight import run_preflight

    preflight = run_preflight(

        workspace=".", question_file=args.question_file, demand_file=args.demand_vectors,

        demand_manifest=args.demand_manifest, model_config=args.model_config, require_model=True,

        demand_profile=args.demand_profile,

    )

    if args.preflight_only:

        print(json.dumps(preflight, ensure_ascii=False, indent=2))

        return 0 if preflight["technical_ready"] else 2

    if not preflight["technical_ready"]:

        print(json.dumps(preflight, ensure_ascii=False, indent=2))

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

    DEMAND_PROFILE = args.demand_profile

    print(f'Assessment mode: {args.assessment_mode}; demand profile: {DEMAND_PROFILE}')

    if DEMAND_PROFILE == 'current-proposal':

        print('Current-task projection: reproducible, scientific scales awaiting expert calibration.')

    configure_question_snapshot(args.question_file)

    if not args.no_evaluation:

        try:

            fixed_demands()  # Fail on version mismatch before initializing network clients.

        except (ValueError, OSError) as exc:

            parser.error(str(exc))



    # 1. 加载模型管理器

    from models.Model_Loader import ModelLoader

    loader = ModelLoader(args.model_config)

    available_names = {row["name"] for row in loader.config["models"]}

    if args.models:

        model_list = [name.strip() for name in args.models]

        if any(name not in available_names for name in model_list):

            parser.error("Requested model names are absent from --model-config.")

    else:

        model_list = [name for name in DEFAULT_MODEL_LIST if name in available_names]

        if not model_list:

            parser.error("No default benchmark models exist in this configuration; select --models explicitly.")

    selected_names = set(model_list)

    if not args.no_evaluation:

        if args.teacher not in available_names:

            parser.error("Requested --teacher is absent from --model-config; select a configured teacher explicitly.")

        selected_names.add(args.teacher)

    try:

        models = loader.load_models(selected_names)

    except (ImportError, ValueError, KeyError) as exc:

        parser.error(f"Cannot initialize selected model adapters: {type(exc).__name__}. Check provider dependencies and configuration fields.")

    shot_types = args.shot_types



    # 2. 教师模型选择

    teacher_model = None

    if not args.no_evaluation:

        teacher_model_name = args.teacher

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

                assessment_mode=args.assessment_mode, task_contexts=task_contexts, robustness_inputs=robustness_inputs,

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

            print(f"  completed benchmark estimates={s.get('n_benchmark_scores', 0)}; numerical unknowns={s.get('n_benchmark_unresolved', 0)}; grounded assessments={s.get('n_grounded_assessments', 0)}; legacy diagnostics={s.get('n_legacy_diagnostics', 0)}; formal score records={s.get('n_official_scores', 0)}")





    # 7. 关闭客户端

    print("\n--- 正在清理模型连接池 ---")

    for name, model_instance in models.items():

        try:

            if hasattr(model_instance, "aclose"):

                await model_instance.aclose()

            elif hasattr(model_instance, "client") and hasattr(model_instance.client, "close"):

                import inspect

                result = model_instance.client.close()

                if inspect.isawaitable(result):

                    await result

        except Exception:

            pass



    n_err = sum(1 for s in summaries if isinstance(s, Exception) or (isinstance(s, dict) and s.get("error")))

    return 0 if n_err == 0 else 1





if __name__ == "__main__":

    sys.exit(asyncio.run(main()))

