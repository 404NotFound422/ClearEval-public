# TOCBenchmark

4.2 简答题评分OEQ Scoring: Protocol Quality Assessment

传统的自然语言生成指标（如 BLEU, ROUGE）仅关注词汇重叠，无法评估科学实验方案在物理世界的可行性。因此，我们建立了多维实验方案评估方法（Multidimensional Protocol Assessment ），将模型生成的实验方案映射到 **完整性 (Completeness)**、**正确性 (Correctness)** 和 **有效性 (Effectiveness)** 三个维度。

其中，**完整性**与**正确性**由经过指令微调的 **LLM-as-a-Judge** 依据分级量表进行评分；**有效性**则基于物理公式计算（详见 4.2.3）

4.2.1 完整性Dimension I: Completeness (Structural Integrity)

完整性评估主要进行**形式检查 (Form Check)**，旨在确认模型生成的 Protocol 是否具备复现实验所需的全部结构化信息。总分 5 分。

**步骤完整性Procedural Integrity（2分）**：评估生成的方案是否是标准protocol

需包含预处理（如固定）、核心透明化（脱脂/折射率匹配）及标记步骤（如适用）

\*\*参数细节完整性Parametric Granularity（3分）：\*\*评估方案的"分辨率"。重点考察化学试剂的名称 (Identity)、浓度 (Concentration) 以及处理条件的数值精确度 (Numerical Precision)

时间与温度必须精确到具体数值（如 "72 hours at 37°C"），而非模糊描述（如 "several days"），试剂名称必须明确，复杂试剂的配制过程应该简要描述。

4.2.2 正确性Dimension II: Correctness (Scientific Validity)

正确性评估旨在检测方案中是否存在违背领域共识或物理定律的**致命错误 (Fatal Errors)**。总分 8 分。

* **Sequential Logic (步骤顺序正确性, 3分):** 评估实验拓扑结构的合理性。
  * **3分 (Canonical):** 完全符合该方法的标准protocol，顺序流程正确。
  * **2分 (Functional):** 步骤顺序有部分错误。
  * **1分 (Disrupted):** 流程混乱，缺乏必要的过渡步骤。例如：直接将水性样本（PBS）投入疏水溶剂（DBE），导致严重的乳化或浑浊。
  * **0分 (Inverted):** 逻辑倒置，如"先透明，后固定"，或在不同类型的方法中混用步骤。
* **Reagent-Method Consistency (方法-试剂一致性, 2分):** 评估化学体系的内部自洽性。
  * **2分 (Consistent):** 试剂系统严格隔离。例如：CUBIC 方法仅使用氨基醇/尿素体系，iDISCO 方法仅使用甲醇/DCM/DBE 体系。
  * **1分 (Minor Mixing):** 存在部分错误。
  * **0分 (Fatal Incompatibility):** 混用化学不兼容试剂。例如：在水性透明体系中直接加入二氯甲烷 (DCM)，导致分层或沉淀。
* **Physical Plausibility (参数合理性, 2分):** 评估关键参数是否符合物理定律（如 **Fick's Law**）。
  * **2分 (Plausible):** 参数设定符合扩散动力学。例如：全脑脱脂设定为"数天"，切片设定为"数小时"。
  * **0分 (Hallucinated):** 违反物理常识。例如：建议"100°C 煮沸组织"或"全脑 1 小时透明"，这将导致样本物理损坏或处理失败。
* **Other Errors (其他错误, 1分):** 未列明但影响实验结果的其他幻觉性错误。

4.2.3 有效性Dimension III: Effectiveness (Quantitative Feasibility Verification)

有效性评估旨在实验前验证该透明化方法的可行性，总分17分。

\$\$ E\_{score} = S\_{method} +  S\_{label} + S\_{trans} + S\_{time} \$\$

1. **透明方法选择总体适配度Methodological Suitability Score，S\_{method}（5分）**
   此指标评估 LLM 生成的protocol与人类专家决策在多维特征空间中的一致性。
   我们将透明化方法映射为一个高维向量\$\\mathbf{v} \\in \\mathbb{R}^n\$，维度涵盖：荧光蛋白兼容性、外标染料难度、透明化能力、组织形变率、方法代价cost和安全性。通过计算 LLM 推荐方法向量 \$v\_{pred}\$ 与专家标准方法向量 \$v\_{ref}\$ 之间的余弦相似度，以量化策略的一致性：
   \$S\_{method} = 5 \\times \\text{ReLU}(\\cos(\\mathbf{v}*{pred}, \\mathbf{v}*{ref})) \\in [0, 5]\$

   **程序实际运行逻辑：**

   * **method_vec（方法向量）：** 教师模型从 protocol 抽取 `method_name`（如 "CUBIC"、"iDISCO+"），归一化后在 `dataset/Q+AR/src/model_space.json` 中模糊匹配（要求 ≥3 字符重叠以避免空串假匹配），取该方法预定义的 6 维向量中各维的 `V` 值（`{F_fp, P_dye, C_opt, M_geo, E_ops, S_safe}`）。
   * **user_vec（用户偏好向量）：** 教师模型独立调用 `prompts/parse_user_preference_vector.py` 中的 `USER_PREFERENCE_PROMPT`，从 question 文本中解析出 6 维偏好向量（同维度 schema），每维取 `.target` 字段。
   * **余弦相似度：** `cos_sim = np.dot(user_vec, method_vec) / (||user_vec|| · ||method_vec||)`，最终 `s_method = 5 × cos_sim`，clamp 到 [0, 5]。
   * **缺失处理：** 若 `method_name` 为空（LLM 未抽到）或方法不在 `model_space.json` 的 18 个预定义方法中 → s_method = 0 并打印 Warning。
   * **已知局限：** 当前 `model_space.json` 覆盖 18 个常用透明方法（CUBIC, SCALE, MACS, iDISCO+, FDISCO, SOLID, seeDB2, PEGASOS, ClearSee, BoneClear, EyeCi, uDISCO, FlyClear, Ce3D, TDE, ClearT2, FOCM, SWITCH）。若 LLM 推荐了未覆盖的方法 → 直接 0 分。
2. **标记与方法兼容性评分Label-Method Compatibility Score，S\_{label} （6分）**
   组织透明后依赖荧光观察目标生物结构，因此确保荧光兼容是透明实验成功的前提。该指标被定义为硬约束 (Hard Constraint)，由三个子项的最小值决定，遵循"木桶效应"。
   \$S\_{label} = \\min(S\_{target\\\_match}, S\_{marker\\\_fluor\\\_compat}, S\_{method\\\_fluor\\\_compat}) \\in [0, 6]\$
   任何一项的失误都将导致该项得分为 0，从而显著拉低总分。

   **程序实际运行逻辑（Python 规则评分，非 LLM 评分）：**

   * **\$S\_{target\\\_match}\$（标记物-题目靶点匹配，0/3/6）：** 对 `marker_dict` 中每个非空 (fluor, marker) 项，调用 `_match_marker_to_targets()` 与题目的 `marker_query_targets` 比对：
     - **6 分**：marker 名称（或括号缩写）与任一 `marker_query_targets[i].marker_name` 完全/缩写/子串匹配
     - **3 分**：无名称匹配但 marker 大类（查 `KnowledgeBase/tissue.json` 的"大类"列）与题目 target 大类相同（如题目要"神经元"标记，LLM 用了"星形胶质"，都是中枢神经大类）
     - **0 分**：marker 与题目要求完全不相关
     - 最终取所有 marker 的**最小值**（木桶原则）。若 `marker_dict` 为空 → 0。
   * **\$S\_{marker\\\_fluor\\\_compat}\$（标记位点-荧光团兼容性，0/6）：** 每个 (fluor, marker) 在 `KnowledgeBase/tissue.json` 中查"标记位点行 × 荧光团列"，若值为 0（明确不兼容）→ 0 分；为 1 或缺失 → 6 分。例如核染料 DAPI 用于血管标记 CD31 → 兼容性查表得 0。
   * **\$S\_{method\\\_fluor\\\_compat}\$（荧光团-透明方法兼容性，0~6）：** 每个 (fluor, method) 在 `KnowledgeBase/method_fluro_compati.json` 中查兼容性评分 [0, 1]，乘以 6 得最终分。例如 iDISCO+ 对内源 GFP 严重淬灭 → 评分 0.1 × 6 = 0.6 分。
   * **未知字段处理：** 标记或荧光团未在 KB 中找到时，不进行惩罚（按 6 分计），避免冷启动 KB 覆盖不足时把所有方案都打成 0 分。
   * **数据源：** `marker_query_targets` 来自题目（启动时缓存到 `QUESTION_META_KB[qid]`），`marker_dict` 来自教师 LLM 抽取；若 LLM 返回非 dict 结构（如 list of dicts），程序自动转换为 dict。
   * **评分溯源：** 评估结果中保留 `s_target_match` / `s_marker_fluor_compat` / `s_method_fluor_compat` 三个子项分数，便于审计是哪一项触发了 min 短板。
3. **透明度有效性Refractive Index Matching Score, S\_{trans} （3分）**
   透明化的物理本质是消除光散射。由于不同透明方法走的物理路径不同（水性方法保留组织水分、溶剂方法脱水后由溶剂 RI 主导），单纯比较"试剂 RI 与组织固有 RI"并不能反映方法的真实适配度。我们将该评分改为衡量\*\*方法-组织域匹配 (Method-Tissue Domain Matching)\*\*：每个透明方法都有其历史上最适合的样本类型，该样本类型的固有 RI 记为 \$RI\_{method\\\_ref}\$；当题目的组织类型 \$RI\_{tissue}\$ 越接近 \$RI\_{method\\\_ref}\$，得分越高。我们采用\*\*高斯径向基函数 (Gaussian RBF)\*\*：
   \$S\_{trans} = 3 \\cdot \\exp \\left( - \\frac{1}{2} \\left( \\frac{RI\_{tissue} - RI\_{method\\\_ref}}{\\sigma\_{RI}} \\right)^2 \\right) \\in [0, 3]\$
   其中，\$\\sigma\_{RI}\$ 为该方法在该样本尺度下的容忍带宽。该评分确保**方法应用于其设计目标组织时得高分**（如 iDISCO+ 透明脑、BoneClear 透明骨、ClearSee 透明植物），而**方法跨域使用时得低分**（如 CUBIC 透明植物、EyeCi 透明骨）。

   **程序实际运行逻辑（Python 规则评分，非 LLM 评分）：**

   * **支持门控（Method×Tier Support Gate）：** 在计算 RI 距离前，先检查 `(method, tier_code)` 是否在 `KnowledgeBase/time_kb.json` 的 `lookup` 字段中存在。若不存在（方法根本不处理这种尺度，如 CUBIC 无 T11_PLANT 条目、EyeCi 无 T07_HARD_TISSUE 条目），直接 S\_{trans} = 0，状态标记为 `out_of_method_range`。
   * **\$RI\_{tissue}\$（题目组织 RI）：** 不依赖 LLM 抽取，由 `OEQ_run_grading_new.py` 启动时根据题目的 `tissue_inferred`（如 "全脑/脑"、"心脏"、"耳蜗/骨"）按关键词优先级查 `KnowledgeBase/tissue_ri.json` 得到。优先级：**脑+肿瘤复合 → 复合肌肉 → 硬组织（骨/牙/耳蜗）→ 肌肉皮肤 → 内脏腺体 → 神经/眼/胚胎/特殊**。所有 73 个独立 tissue 标签均已覆盖映射，缺省回退至 1.48。结果缓存至 `QUESTION_META_KB[qid].tissue_ri_value`。
   * **\$RI\_{method\\\_ref}\$（方法最适合样本的 RI）：** 由 `KnowledgeBase/method_ri_ref.json` 按 method 查表得到，**代表的是该方法首次发表/最广泛使用的样本类型的固有 RI**，而非试剂 RI。例如 CUBIC→1.46（脑/器官）、iDISCO+→1.47（脑/胚胎）、PEGASOS→1.52（全身/硬组织）、BoneClear→1.56（骨）、ClearSee→1.47（植物）。该 KB 已覆盖 17+ 主流方法，每条带文献出处。
   * **σ\_{RI}（容忍带宽）：** 由 `KnowledgeBase/method_sigma_ri.json` 按 `(method, tier_code)` 查表得到，反映该方法在该样本尺度下的 RI 域宽度（如脑切片 σ≈0.020，全身 σ≈0.060）。
   * **公式实现：** `s_trans = 3.0 * exp(-0.5 * ((RI_tissue - RI_method_ref) / σ_RI) ** 2)`，clamp 到 [0, 3]。
   * **不依赖 LLM 抽取的 reagent_ri_value：** 原有 `reagent_ri_value` 字段保留在 extraction 输出中（供调试），但 **S\_{trans} 评分不再使用它**——因为该字段常被 LLM 写错（如 iDISCO+ 误写为水性试剂 RI），且不反映方法-组织域匹配的核心问题。
   * **评分溯源：** 评估结果中保留 `_s_trans_status` (scored/out\_of\_method\_range/missing\_kb)、`_s_trans_ri_tissue`、`_s_trans_ri_method_ref`、`_s_trans_sigma` 等调试字段，便于审计。
4. **时间效率评分Temporal Efficiency Score, S\_{time}（3分）**
   不同的透明方法因其试剂类型不同，对某个类别样本的处理时间不一致，因此基于**可行时间区间 (Feasible Time Interval)**。对于特定样本类型（如小鼠脑、胚胎），低于该样本类型在特定透明方法可行时间区间的 \$t\_{min}\$ 意味着透明不完全（Under-clearing），高于 \$t\_{max}\$ 则意味着效率低下或组织降解风险。我们定义有效时间偏差 \$\\Delta t\$ 并采用高斯衰减函数评分：
   \$S\_{time} = 3 \\cdot \\exp \\left( - \\frac{1}{2} \\left( \\frac{\\Delta t}{\\tau} \\right)^2 \\right) \\in [0, 3]\$
   \$\\Delta t = \\begin{cases} 0, & \\text{if } t\_{min} \\le t\_{act} \\le t\_{max} \\quad (\\text{In Range}) \\\\ t\_{min} - t\_{act}, & \\text{if } t\_{act} < t\_{min} \\quad (\\text{Under-clearing Risk}) \\\\ t\_{act} - t\_{max}, & \\text{if } t\_{act} > t\_{max} \\quad (\\text{Efficiency Loss}) \\end{cases}\$
   其中，\$t\_{act}\$ 为模型预测时间，\$\\tau\$ 为时间敏感度系数。该评分机制在容忍适度偏差的同时，惩罚严重违反物理扩散规律的时间设定。

   **程序实际运行逻辑（Python 规则评分，非 LLM 评分）：**

   * **t\_{act}（实际预测耗时）：** 由教师模型从待测 protocol 中抽取 `clearing_total_time_hours`（仅统计透明化核心流程，不含固定/标记/采集时间）。
   * **method（方法名）：** 由教师模型从 protocol 中抽取 `method_name`（CUBIC, iDISCO+, MACS 等），归一化为小写并去除分隔符后用于 KB 查表。
   * **tier\_code（样本尺度等级）：** 不依赖 LLM 抽取，由题目定义中的 `tissue_hierarchy_from_tissue_xlsx.tissue_tier_code`（T01\~T12）直接传入，启动时缓存到 `QUESTION_META_KB[qid].tissue_tier_code`。
   * **\[t\_{min}, t\_{max}\]（参考时间区间）：** 按 `(method, tier_code)` 查 `KnowledgeBase/time_kb.json` 的 `lookup` 字段，得到 `clearing_time_min_h` 和 `clearing_time_max_h`（来源于文献，详见各条目的 `source_url`）。
   * **τ（时间敏感度系数）：** 按 `(method, tier_code)` 查 `KnowledgeBase/method_time_tau.json`，公式为 `τ = 0.20 × clearing_time_median_h`（最小 0.05 h）。该值由 `KnowledgeBase/generate_time_tau.py` 自动从 `time_kb.json` 生成。组织越大 τ 越大（即对偏差容忍度越高）。
   * **缺失处理：** 若方法×tier 组合不在 KB（例如题目要求 T07 硬组织但 LLM 选择了不支持硬组织的 CUBIC）→ S\_{time} 直接得 0，惩罚错误的方法-样本搭配。
   * **公式实现：** 按上式计算 Δt，`s_time = 3.0 * exp(-0.5 * (Δt / τ) ** 2)`，区间内时直接给满分 3.0，最终 clamp 到 [0, 3]。
   * **评分溯源：** 评估结果中保留 `_s_time_t_min` / `_s_time_t_max` / `_s_time_tau` / `_s_time_t_act` / `_s_time_tier` / `_s_time_ref_source` 等调试字段。

---

### 评测程序总览 (End-to-End Pipeline)

**入口**：`OEQ_run_grading_new.py` —— 13 个被测模型并发跑 `process_and_evaluate_model`，每个模型内部按以下两阶段流水线执行。

```
┌─────────────────────── Phase 1: Generation ───────────────────────┐
│ for q in question_final.json (253 题):                            │
│    prompt = TEST_MODEL_GENERATION_PROMPT + q.question             │
│    response_text = await 被测模型._acall(prompt)                  │
│    → dataset/Q+AR/model_response/from_<model>_<shot>.json         │
│       字段: question_id, specific_question, prompt, restrictions, │
│             model_response, tissue_tier_code, tissue_inferred,    │
│             tissue_ri_value, marker_query_targets                 │
└───────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────── Phase 2: Evaluation (per-model Semaphore=4) ───────────┐
│ for entry in responses (并发 4 题):                               │
│   ┌─ 教师 LLM 调用一次 ─────────────────────────────────────────┐ │
│   │ eval_oeq_teacher_rubric.txt → 教师模型 → JSON 返回:        │ │
│   │   scores.completeness    {c_step, c_param}                 │ │
│   │   scores.correctness     {co_order, co_method, co_param,   │ │
│   │                           co_chem, critical_warnings}      │ │
│   │   extraction             {method_name, reagent_ri_value,   │ │
│   │                           clearing_total_time_hours,       │ │
│   │                           marker_dict, ...}                │ │
│   └────────────────────────────────────────────────────────────┘ │
│                                  ↓                               │
│   ┌─ 教师 LLM 调用第二次 (parse_user_preference_vector) ──────┐  │
│   │ 解析 question 的语义偏好 → user_pref_vector                │  │
│   │  {F_fp, P_dye, C_opt, M_geo, E_ops, S_safe}               │  │
│   └───────────────────────────────────────────────────────────┘  │
│                                  ↓                               │
│   ┌─ Python 规则评分 calculate_effectiveness_score() ─────────┐  │
│   │ S_method (查 model_space.json + 余弦相似度)               │  │
│   │ S_label  (查 tissue.json + method_fluro_compati.json)     │  │
│   │ S_trans  (查 tissue_ri.json + method_ri_ref.json          │  │
│   │           + method_sigma_ri.json + time_kb.json 门控)     │  │
│   │ S_time   (查 time_kb.json + method_time_tau.json)         │  │
│   └───────────────────────────────────────────────────────────┘  │
│                                  ↓                               │
│   写入磁盘 (.tmp → os.replace) 每完成一题立即保存：               │
│   → dataset/Q+AR/result/evaluation_results_<model>_<shot>.json   │
└──────────────────────────────────────────────────────────────────┘
```

**数据流核心约定**：

| 信号源                           | 来源                                | 用于                                   |
| -------------------------------- | ----------------------------------- | -------------------------------------- |
| `tissue_tier_code` (T01~T12)   | 题目定义，**不依赖 LLM**      | S_trans 门控、S_time 区间              |
| `tissue_inferred` (中文标签)   | 题目定义 →`_resolve_tissue_ri()` | S_trans 的 RI_tissue                   |
| `marker_query_targets`         | 题目定义                            | S_label 的 target_match                |
| `method_name`                  | 评测 LLM 抽取                       | S_method / S_trans / S_time 的查表 key |
| `marker_dict` (荧光→标记位点) | 评测 LLM 抽取                       | S_label 三个子项                       |
| `clearing_total_time_hours`    | 评测 LLM 抽取                       | S_time 的 t_act                        |

**断点续传**：每题完成后立即写入磁盘；二次运行从 `dataset/Q+AR/result/evaluation_results_<model>_<shot>.json` 读取已评 `question_id` 集合并跳过。崩溃/中断不丢数据。

---

### 知识库文件 (KnowledgeBase Files Inventory)

所有评分查表依赖以下 JSON KB，集中放在 `KnowledgeBase/`：

| 文件                                     | 内容                                                                                    | 生成                                           | 查询                                            |
| ---------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------- |
| `tissue.json`                          | 标记位点 × 荧光团兼容矩阵 + 大类标签                                                   | 人工整理自 `tissue.xlsx`                     | S_label (s_target_match, s_marker_fluor_compat) |
| `method_fluro_compati.json`            | 荧光团 × 透明方法兼容性 (0~1)                                                          | 人工整理自 `method_fluro_compati.xlsx`       | S_label (s_method_fluor_compat)                 |
| `tissue_ri.json`                       | 组织类型 → 固有 RI（73 中文标签 → 1.45~1.57）                                         | 人工整理（基于蛋白/脂质/矿物密度）             | S_trans (`_resolve_tissue_ri()`)              |
| `method_ri_ref.json`                   | 17+ 方法 → 适用样本 RI + 文献出处                                                      | 人工整理                                       | S_trans (RI_method_ref)                         |
| `method_sigma_ri.json`                 | (方法 × T01~T12) → σ_RI 容忍带宽                                                     | 人工整理                                       | S_trans (σ_RI)                                 |
| `time_kb.json`                         | (方法 × T01~T12) → 透明耗时区间 [min, median, max] (h)                                | `convert_time_kb.py` from `time_kb.xlsx`   | S_trans 门控 + S_time (t_min, t_max)            |
| `method_time_tau.json`                 | (方法 × T01~T12) → τ                                                                 | `generate_time_tau.py` from `time_kb.json` | S_time (τ)                                     |
| `dataset/Q+AR/src/model_space.json`    | 18 个方法的 6 维向量空间（含 V/W）                                                      | 人工整理                                       | S_method (method_vec)                           |
| `dataset/Q+AR/src/question_final.json` | 253 道题 + 每题的 `tissue_tier_code` / `tissue_inferred` / `marker_query_targets` | 题库构建脚本                                   |                                                 |

---

### 调用方法 (CLI Usage)

**环境**：`conda activate YWB`，工作目录为项目根 `D:/YWB/TOCModelBenchmark`。

**主入口**：`python OEQ_run_grading_new.py [选项]`

```bash
# 1) 默认：13 模型并发生成 + 评测，每模型内部 4 题并发
python OEQ_run_grading_new.py

# 2) 只评测（已有 from_<model>_<shot>.json）—— 跳过 generation 阶段
python OEQ_run_grading_new.py --eval-only

# 3) 只生成不评测（向后兼容旧行为）
python OEQ_run_grading_new.py --no-evaluation

# 4) 只跑指定模型
python OEQ_run_grading_new.py --eval-only --models openai_gpt-5.2-fast gemini-3-pro

# 5) 提高单模型评测并发（默认 4，可上调，但注意教师 LLM 速率上限）
python OEQ_run_grading_new.py --eval-only --eval-concurrency 8

# 6) 换教师模型（默认 openai_gpt-5.2-thinking）
python OEQ_run_grading_new.py --eval-only --teacher openai_gpt-4o

# 7) 多个 shot 类型一次跑
python OEQ_run_grading_new.py --shot-types 0-shot 1-shot
```

**CLI 参数完整列表：**

| 参数                     | 默认                        | 说明                                                   |
| ------------------------ | --------------------------- | ------------------------------------------------------ |
| `--models `            | 13 个默认模型               | 仅运行指定模型名（须在 `config/config.yaml` 已配置） |
| `--shot-types `        | `["1-shot"]`              | 运行哪些 shot 类型                                     |
| `--teacher `           | `openai_gpt-5.2-thinking` | 评测 LLM 名称，回退 `openai_gpt-4o`                  |
| `--eval-concurrency N` | 4                           | 每模型内部并发评测的题数（`asyncio.Semaphore`）      |
| `--eval-only`          | False                       | 跳过生成，直接评估已有 `from__.json`                 |
| `--no-evaluation`      | False                       | 跳过评测，只生成 protocol（与 `--eval-only` 互斥）   |

**输出位置：**

- 生成：`dataset/Q+AR/model_response/from_<model>_<shot>.json`
- 评测：`dataset/Q+AR/result/evaluation_results_<model>_<shot>.json`（每完成一题即写入磁盘，崩溃后可断点续传）

**结果 JSON schema（单条评测）：**

```json
{
  "question_id": 3,
  "evaluation": {
    "meta_data": {
      "protocol_id": 3,
      "sample_info": "...",
      "target_method": "iDISCO+",
      "generated_timestamp": "..."
    },
    "scores": {
      "completeness": {
        "c_step": {...},
        "c_param": {...},
        "total_weighted_score": 4.0
      },
      "correctness": {
        "co_order": {...},
        "co_method": {...},
        "co_param": {...},
        "co_chem": {...},
        "critical_warnings": [...],
        "total_weighted_score": 7.0
      },
      "effectiveness": {
        "s_method": {"score": 4.71, "max_score": 5, "reasoning": "Cos distance ... Method: iDISCO+"},
        "s_label":  {"score": 3.90, "max_score": 6, "reasoning": "target_match=6.0, marker_fluor_compat=6.0, method_fluor_compat=3.9, marker_dict={...}"},
        "s_trans":  {"score": 2.81, "max_score": 3, "reasoning": "RI_tissue=1.46, RI_method_ref=1.47, σ_RI=0.028, tier=T04, status=scored"},
        "s_time":   {"score": 3.00, "max_score": 3, "reasoning": "t_act=72h, KB range=[24, 72]h, τ=7.2h"},
        "total_weighted_score": 14.42
      }
    }
  }
}
```

**快速验证测试（验证 KB 完整性和评测逻辑，不跑全 253 题）：**

```bash
# 从 13 个 from_*.json 各抽 3 题 + 强制覆盖 T07/T11/T12 → 共 78 评测，约 7 分钟
python KnowledgeBase/_smoke_eval_pipeline.py --n-per-model 3 --max-concurrency 4

# 自定义抽样 / 限定模型
python KnowledgeBase/_smoke_eval_pipeline.py --n-per-model 5 --models openai_gpt-5.2-fast
```

快速验证测试输出 `dataset/Q+AR/result/_smoke_eval_results.json`，并在终端打印每题 (s_method, s_label, s_trans, s_time, wall) 的表格 + 错误堆栈。

**Phase C 集成验证（断点续传 + 安全写入）：**

```bash
python KnowledgeBase/_verify_phase_c.py   # 跑 3 题 mini-run，验证 resume / atomic-write / 路径一致
```
