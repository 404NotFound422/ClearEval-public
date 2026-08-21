"""
代码目的：
该脚本旨在评估不同“教师模型”（Teacher Models）在对同一组模型生成回答进行评分时的差异。
它复用了 `run_grading_new.py` 中的评分逻辑（包括完整性、正确性和有效性评分），
并将不同的教师模型应用于现有的模型回答文件（默认为 `dataset/Q+AR/model_response/from_openai_gpt-4o.json`）。

主要功能：
1. 加载现有的被测模型回答（Student Responses）。
2. 定义一组教师模型（例如 GPT-4o, GPT-5.2, Gemini-Pro 等）。
3. 让每个教师模型对同一组回答进行独立评分。
4. 保存每个教师模型的评分结果。
5. 生成对比报告，分析不同教师模型在打分倾向、严苛程度等方面的差异。

输入：
- `dataset/Q+AR/model_response/from_openai_gpt-4o.json`: 待评估的标准回答集。
- `config/config.yaml`: 模型配置。
- `prompts/eval_teacher_protocol_review.py`: 评分 Prompt。

输出：
- `result/teacher_comparison/eval_by_{teacher_name}.json`: 各个教师模型的详细评分。
- `result/teacher_comparison/summary.json`: 汇总对比报告。
"""

import json
import os
import sys
import importlib.util
import asyncio
import numpy as np
import math
from models.Model_Loader import ModelLoader

# 复用 run_grading_new.py 中的关键逻辑
# 为保持独立性，此处重新定义相关函数，实际工程中建议提取为公共模块

# -------------------------------------------------------------------------
# Prompt for User Preference Parsing
# -------------------------------------------------------------------------
USER_PREFERENCE_PROMPT = """
# Role Definition
You are an expert consultant in Tissue Optical Clearing (TOC) technology and an algorithm data engineer. Your task is to analyze unstructured "User Requirements" for biological tissue clearing and convert them into a structured "Feature Vector" for a recommendation system.

# Step1: Generate The 6-Dimensional Vector
You must evaluate the user's request based on the following 6 dimensions. For each dimension, you need to determine:
1. **Target Value (V)**: (float) The ideal physical parameter or functional state.
2. **Weight (W)**:(float) How strictly the user cares about this dimension (0 = Don't care, 0.5 = Preference, 1.0 = Strict Constraint).

##Vector Dimension Definitions:

### 1. fluorescence_protein_preservation (F_fp)
- **Definition**: The need to preserve endogenous fluorescence (e.g., GFP, YFP, tdTomato, DiI).
- **Target Value (V) Range [0.0 to 1.0]**:
- `0.0`: No fluorescence needed / Using immunolabeling / Dyes only.
- `1.0`: Maximum preservation required (Strict prevention of quenching).
- **Weight Logic**: If user mentions "GFP", "YFP" or "endogenous signal", W is usually 1.0. If doing "immunostaining only", W is 0.

### 2. dye_permeability (P_dye)
- **Definition**: The need for macromolecules (antibodies or dyes) to penetrate the tissue.
- **Target Value (V) Range [0.0 to 1.0]**:
- `0.0`: No immunolabeling need.
- `0.2`: slices immunolabeling required.
- `0.6`: Whole-mount Small dyes or stains.
- `1.0`: Whole-mount deep immunolabeling required.

### 3. Clearing Challenge / RI (C_opt)
- **Definition**: Difficulty of optical clearing based on tissue size, type, and age. (Correlates with Refractive Index requirements).
- **Target Value (V) Range [0.0 to 1.0]**:
- `0.2`: Thin sections / Embryos / Slices.
- `0.6`: Adult mouse brain / Soft organs.
- `1.0`: Whole body / Bones / Human brain blocks / Old fixed samples (Requires High RI solvent).

### 4. Geometric Preference (M_geo)
- **Definition**: Preference for sample size change.
- **Target Value (V) Range [0 to 2.0]**:
- `<1.0`: Shrinkage (Good for large samples, fast scanning, iDISCO style).
- `1.0`: Isotropic / Keep original size (Crucial for morphology analysis).
- `>1.0`: Expansion (ExM, for super-resolution).
- **Weight Logic**: If user says "don't care about deformation" or "just want to see inside", set W = 0.

### 5. Operational Economy (E_ops)
- **Definition**: Preference for speed, simplicity, and low cost versus complexity/time.
- **Target Value (V) Range [0.0 to 1.0]**:
- `0.0`: Quality First (Willing to wait weeks, complex steps ok).
- `1.0`: Speed First (Rapid screening, simple protocols, 1-2 days).

### 6. Safety & Compatibility (S_safe)
- **Definition**: Tolerance for toxic organic solvents or corrosive reagents.
- **Target Value (V) Range [0.0 to 1.0]**:
- `0.0`: Toxic solvents accepted (DBE, DCM, BABB).
- `1.0`: Must be non-toxic / Water-based / Microscope-friendly.

# Step2: Output Format
Return ONLY a valid JSON object. No markdown explanations outside the JSON.

```json
{
"user_input_vectors": {
    "fluorescence_protein_preservation": {"target": float, "weight": float},
    "dye_permeability":     {"target": float, "weight": float},
    "clearing_challenge":        {"target": float, "weight": float},
    "geometry_preference":       {"target": float, "weight": float},
    "operational_economy":       {"target": float, "weight": float},
    "safety_compatibility":      {"target": float, "weight": float}
}
}
```
now ,  the user's input is : {user_text}
"""

def load_prompt_method_generate():
    """动态加载评分 Prompt"""
    prompt_path = 'prompts/eval_teacher_protocol_review.py'
    try:
        spec = importlib.util.spec_from_file_location("prompt_method_generate", prompt_path)
        prompt_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prompt_module)
        return prompt_module.prompt
    except Exception as e:
        print(f"加载评分Prompt出错: {e}")
        return ""

def load_data_and_resources():
    """加载所需的数据资源"""
    # 1. 加载模型空间
    with open('dataset/Q+AR/src/model_space.json', 'r', encoding='utf-8') as f:
        model_space = json.load(f)
    
    # 2. 加载待评估的学生模型回答
    # 默认使用 from_openai_gpt-4o.json 作为基准
    student_response_path = 'dataset/Q+AR/model_response/from_openai_gpt-4o.json'
    if not os.path.exists(student_response_path):
        print(f"Warning: {student_response_path} not found.")
        student_responses = []
    else:
        with open(student_response_path, 'r', encoding='utf-8') as f:
            student_responses = json.load(f)
            
    return student_responses, model_space

async def get_user_preference_vector(teacher_model, question_text):
    """利用 Teacher Model 生成用户偏好向量"""
    prompt = USER_PREFERENCE_PROMPT.replace("{user_text}", question_text)
    try:
        response_data = await teacher_model._acall(prompt)
        content = response_data.get("content", "").strip()
        if content.startswith("```json"): content = content[7:]
        elif content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        data = json.loads(content.strip())
        return data.get("user_input_vectors", {})
    except Exception as e:
        print(f"[{teacher_model.model_name}] 获取用户偏好向量出错: {e}")
        return {}

def calculate_cosine_similarity(vec1, vec2):
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0: return 0.0
    return dot_product / (norm1 * norm2)


def calculate_method_suitability(user_pref_vector_dict, method_vector_dict, sigma=0.6,
                                  hard_constraint_threshold=0.7,
                                  hard_constraint_penalty=0.75):
    """
    计算方法适配度 S_method（改进版）。

    原实现使用未加权的余弦相似度，导致所有方法的得分都集中在 4.0-5.0 区间，
    无法区分专家判为合适/不合适的方法（ICC ≈ 0.04）。改进点：

    1. 改用加权欧氏距离，直接惩罚用户重视维度上的失配。
    2. 同时引入用户权重（weight）和方法权重（W），忽视不重要或不可靠的维度。
    3. 对 M_geo 做统一尺度归一化（用户 target ∈ [0,2]，方法 V ∈ [0.5,1.5]）。
    4. 对用户严格约束维度（weight ≥ 0.9）出现显著失配时施加额外惩罚。

    参数:
        sigma: 高斯核容忍度，越大对失配越宽容。
        hard_constraint_threshold: 严格约束维度的失配阈值。
        hard_constraint_penalty: 每次违反严格约束的惩罚乘数。

    返回: float, 范围 [0, 5]
    """
    mapping = [
        ("fluorescence_protein_preservation", "F_fp"),
        ("dye_permeability", "P_dye"),
        ("clearing_challenge", "C_opt"),
        ("geometry_preference", "M_geo"),
        ("operational_economy", "E_ops"),
        ("safety_compatibility", "S_safe"),
    ]

    diffs = []
    weights = []
    hard_violations = 0

    for user_key, method_key in mapping:
        u_entry = user_pref_vector_dict.get(user_key, {}) or {}
        u_val = float(u_entry.get("target", 0.0) or 0.0)
        u_w = float(u_entry.get("weight", 0.0) or 0.0)

        m_entry = method_vector_dict.get(method_key, {}) or {}
        m_val = float(m_entry.get("V", 0.0) or 0.0)
        m_w = float(m_entry.get("W", 0.0) or 0.0)

        # 统一 M_geo 尺度
        if method_key == "M_geo":
            u_val = u_val / 2.0
            m_val = (m_val - 0.5) / 1.0
            m_val = max(0.0, min(1.0, m_val))

        diff = abs(u_val - m_val)
        w = u_w * m_w

        diffs.append(diff)
        weights.append(w)

        if u_w >= 0.9 and diff > 0.5:
            hard_violations += 1

    diffs = np.array(diffs, dtype=float)
    weights = np.array(weights, dtype=float)
    weights_sum = weights.sum()

    if weights_sum == 0:
        return 0.0

    weighted_rmsd = np.sqrt(np.sum(weights * diffs ** 2) / weights_sum)
    sim = np.exp(-weighted_rmsd ** 2 / (2 * sigma ** 2))

    if hard_violations > 0:
        sim *= hard_constraint_penalty ** min(hard_violations, 2)

    s_method = 5.0 * sim
    return float(max(0.0, min(5.0, s_method)))


def calculate_effectiveness_score(quantitative_data, user_pref_vector_dict, model_space):
    """计算有效性评分 E_score (复用 run_grading_new.py 逻辑)"""
    w1, w2, w3, w4 = 1.0, 1.0, 1.0, 1.0
    
    # 1. S_method
    method_name = quantitative_data.get("method_name", "")
    method_vector_dict = {}
    found_method = False
    
    for key, val in model_space.get("methods", {}).items():
        if method_name.lower() in key.lower() or key.lower() in method_name.lower():
            method_vector_dict = val
            found_method = True
            break
            
    if not found_method:
        s_method = 0.0
    else:
        s_method = calculate_method_suitability(
            user_pref_vector_dict, method_vector_dict, sigma=0.6,
            hard_constraint_threshold=0.7,
            hard_constraint_penalty=0.75
        )

    # 2. S_label
    fluor_suitable = quantitative_data.get("fluor_suitable_score", [])
    fluor_compatible = quantitative_data.get("fluor_compatible_score", [])
    s_target_match = min(fluor_suitable) if fluor_suitable else 0.0
    s_method_compat = min(fluor_compatible) if fluor_compatible else 0.0
    s_label = max(0.0, min(6.0, min(s_target_match, s_method_compat)))

    # 3. S_trans
    ri_reagent = quantitative_data.get("reagent_ri_value", 0.0)
    ri_sample = quantitative_data.get("sample_ri_value", 0.0)
    sigma_ri = 0.03
    if ri_sample == 0.0: s_trans = 0.0
    else:
        exponent = -0.5 * ((ri_reagent - ri_sample) / sigma_ri) ** 2
        s_trans = max(0.0, min(3.0, 3 * math.exp(exponent)))

    # 4. S_time
    t_act = quantitative_data.get("total_time_hours", 0.0)
    protocol_time = quantitative_data.get("protocol_time_hours", [])
    if len(protocol_time) >= 2:
        t_min, t_max = min(protocol_time), max(protocol_time)
    elif len(protocol_time) == 1:
        t_min = t_max = protocol_time[0]
    else:
        t_min = t_max = 0.0
        
    delta_t = 0.0
    t_ref = 1.0
    if t_act < t_min:
        delta_t = t_min - t_act
        t_ref = t_min
    elif t_act > t_max:
        delta_t = t_act - t_max
        t_ref = t_max
    
    k = 0.2
    if delta_t == 0.0: s_time = 3.0
    else:
        if t_ref == 0: t_ref = 1.0
        exponent = -0.5 * (delta_t / (k * t_ref)) ** 2
        s_time = max(0.0, min(3.0, 3 * math.exp(exponent)))

    e_score = w1 * s_method + w2 * s_label + w3 * s_trans + w4 * s_time
    return {
        "s_method": s_method,
        "s_label": s_label,
        "s_trans": s_trans,
        "s_time": s_time,
        "total_effectiveness_score": e_score
    }

async def evaluate_single_response(teacher_model, response_entry, model_space, prompt_template):
    """
    使用指定的 Teacher Model 评估单个回答
    """
    question_text = response_entry['specific_question']
    model_protocol = response_entry['model_response']
    
    # 1. Get Preferences (Teacher specific)
    user_pref_vector = await get_user_preference_vector(teacher_model, question_text)
    
    # 2. Evaluation Prompt
    prompt = prompt_template.replace("{{protocol_content}}", model_protocol)
    prompt = prompt.replace("{{method_name}}", "Derived from protocol")
    prompt = prompt.replace("{{sample_info}}", question_text)

    try:
        response_data = await teacher_model._acall(prompt)
        content = response_data.get("content", "").strip()
        if content.startswith("```json"): content = content[7:]
        elif content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        
        llm_output = json.loads(content.strip())
        
        qualitative = llm_output.get("qualitative_analysis", {})
        quantitative = llm_output.get("quantitative_data", {})
        
        # 3. Calculate Scores
        eff_scores = calculate_effectiveness_score(quantitative, user_pref_vector, model_space)
        
        # Extract Completeness and Correctness scores for summary
        c_step = qualitative.get("completeness", {}).get("c_step", {}).get("score", 0)
        c_param = qualitative.get("completeness", {}).get("c_param", {}).get("score", 0)
        co_order = qualitative.get("correctness", {}).get("co_order", {}).get("score", 0)
        co_method = qualitative.get("correctness", {}).get("co_method", {}).get("score", 0)
        co_param = qualitative.get("correctness", {}).get("co_param", {}).get("score", 0)
        co_chem = qualitative.get("correctness", {}).get("co_chem", {}).get("score", 0)

        # Normalize Completeness (Max 5) and Correctness (Max 8)
        completeness_total = c_step + c_param
        correctness_total = co_order + co_method + co_param + co_chem
        
        result = {
            "question_id": response_entry['question_id'],
            "scores": {
                "completeness": qualitative.get("completeness", {}),
                "correctness": qualitative.get("correctness", {}),
                "effectiveness": {
                    "details": eff_scores,
                    "total_score": eff_scores["total_effectiveness_score"]
                }
            },
            "summary_scores": {
                "C": completeness_total,
                "Co": correctness_total,
                "E": eff_scores["total_effectiveness_score"]
            }
        }
        return result
        
    except Exception as e:
        print(f"[{teacher_model.model_name}] 评估 {response_entry['question_id']} 出错: {e}")
        return None

async def run_teacher_comparison():
    config_path = 'config/config.yaml'
    
    # 1. Load Models
    loader = ModelLoader(config_path)
    models = loader.load_models()
    
    # 定义要比较的教师模型列表
    # 确保这些名称在 config.yaml 中存在
    teacher_candidates = ["openai_gpt-4o", "openai_gpt-5.2", "gemini-2.5-pro"]
    active_teachers = {name: models[name] for name in teacher_candidates if name in models}
    
    if not active_teachers:
        print("未找到有效的教师模型，请检查配置。")
        return

    print(f"将对比以下教师模型: {list(active_teachers.keys())}")
    
    # 2. Load Resources
    student_responses, model_space = load_data_and_resources()
    if not student_responses:
        return
    
    prompt_template = load_prompt_method_generate()
    if not prompt_template:
        return

    comparison_summary = {} # {teacher_name: {avg_C: ..., avg_Co: ..., avg_E: ..., results: []}}
    output_base_dir = 'result/teacher_comparison'
    os.makedirs(output_base_dir, exist_ok=True)
    
    # 3. Iterate Teachers
    for teacher_name, teacher_model in active_teachers.items():
        print(f"\n>>> 正在运行教师模型: {teacher_name} ...")
        teacher_results = []
        
        c_scores = []
        co_scores = []
        e_scores = []
        
        for entry in student_responses:
            print(f"   评估问题: {entry['question_id']}")
            res = await evaluate_single_response(teacher_model, entry, model_space, prompt_template)
            if res:
                teacher_results.append(res)
                c_scores.append(res['summary_scores']['C'])
                co_scores.append(res['summary_scores']['Co'])
                e_scores.append(res['summary_scores']['E'])
        
        # 保存该教师的详细结果
        output_path = os.path.join(output_base_dir, f'eval_by_{teacher_name}.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(teacher_results, f, indent=4, ensure_ascii=False)
        
        # 统计
        avg_c = np.mean(c_scores) if c_scores else 0
        avg_co = np.mean(co_scores) if co_scores else 0
        avg_e = np.mean(e_scores) if e_scores else 0
        
        comparison_summary[teacher_name] = {
            "average_completeness_score": float(avg_c),
            "average_correctness_score": float(avg_co),
            "average_effectiveness_score": float(avg_e),
            "num_samples": len(c_scores)
        }
        print(f"   [{teacher_name}] 完成。Avg C={avg_c:.2f}, Avg Co={avg_co:.2f}, Avg E={avg_e:.2f}")

    # 4. Save Summary
    summary_path = os.path.join(output_base_dir, 'summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(comparison_summary, f, indent=4, ensure_ascii=False)
    
    print(f"\n对比完成！汇总报告已保存至: {summary_path}")

if __name__ == "__main__":
    asyncio.run(run_teacher_comparison())
