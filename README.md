# ClearEval

**ClearEval** is a benchmark for evaluating Large Language Models (LLMs) on **tissue optical clearing** — the experimental discipline of rendering biological tissue transparent for volumetric fluorescence imaging. The benchmark is **dual-track**:

- **Track 1 — Multiple-Choice Questions (MCQ):** 2,588 questions probing factual and structured domain knowledge (entity recognition, reagent/method/tissue facts, and task-scenario reasoning).
- **Track 2 — Open-Ended Questions (OEQ):** 253 realistic experiment-design scenarios. Models must produce a full clearing **protocol**, which is then scored under the **CCE framework** — **C**ompleteness, **C**orrectness, and **E**ffectiveness.

Standard text-overlap metrics (BLEU, ROUGE) cannot judge whether a proposed wet-lab protocol is *physically feasible*. ClearEval instead combines an instruction-tuned **LLM-as-a-Judge** (for Completeness and Correctness) with **rule-based, physics-grounded scoring** (for Effectiveness), the latter computed against curated knowledge bases of reagent/method/tissue properties.

---

## Repository structure

```
.
├── OEQ_run_grading_new.py        # OEQ track: end-to-end generation + grading entry point
├── MCQ_async_test.py             # MCQ track: async inference harness
├── compare_teacher_model.py      # Judge-model agreement / comparison utilities
├── extract_clearing_time.py      # Helper: extract clearing-time fields from protocols
│
├── config/
│   ├── config.yaml               # Model roster + per-model API settings (no secrets committed)
│   ├── DataSet_Config.yaml       # Dataset registration for the loader
│   └── config_dataset_generate.py
│
├── models/                       # LLM client wrappers (one module per backend)
│   ├── Base_Models.py
│   ├── Model_Loader.py
│   ├── OpenAI_Model.py
│   ├── Gemini_Model.py
│   ├── GLM_Model.py
│   ├── Custom_LLM.py
│   ├── Huggingface_LLM.py
│   └── Ollama_LLM.py
│
├── prompts/                      # Judge rubrics and generation prompt templates
│   ├── eval_oeq_teacher_rubric.txt
│   ├── eval_completeness_checklist.txt
│   ├── gen_dataset_questions_standalone.txt
│   ├── gen_protocol_template.py
│   └── parse_user_preference_vector.py
│
├── KnowledgeBase/                # 7 JSON knowledge bases used by rule-based Effectiveness scoring
│   ├── tissue.json
│   ├── method_fluro_compati.json
│   ├── tissue_ri.json
│   ├── method_ri_ref.json
│   ├── method_sigma_ri.json
│   ├── time_kb.json
│   └── method_time_tau.json
│
├── dataset/
│   ├── Dataset_Loader.py
│   ├── dataset_generater.py
│   ├── MCQ/
│   │   ├── final/                # all_mcq_data.jsonl (2,588), development.jsonl, validation.jsonl
│   │   ├── data_source/          # source spreadsheets (reagent / tissue / dyes)
│   │   ├── model_response/       # per-model MCQ answer checkpoints
│   │   ├── format_dataset_all_in_one_jsonl.py
│   │   ├── metric_of_MCQs_gen_from_jsonl.py
│   │   ├── metric_of_MCQs_per_question_gen_from_jsonl.py
│   │   └── ring_map_gen_from_jsonl.py
│   └── Q+AR/                      # OEQ track ("Question + Auto-Rubric")
│       ├── src/
│       │   ├── question_final.json   # 253 OEQ scenarios + per-question metadata
│       │   ├── model_space.json      # method feature-vector space (Effectiveness S_method)
│       │   ├── standard_response.json
│       │   └── restrict.py
│       ├── model_response/       # generated protocols: from_<model>_<shot>.json
│       └── result/               # graded output: evaluation_results_<model>_<shot>.json
│
└── results/                      # Aggregation, scoring tables, and figures
    ├── aggregate_mcq.py
    ├── aggregate_oeq.py
    ├── calculate_main_table_score.py
    ├── compute_agreement.py
    ├── generate_latex_rows.py
    ├── collect_violin_data.py
    ├── plot_violin_charts.py
    ├── plot_combined_radar.py
    └── plot_alignment_combined.py
```

---

## Figures, tables & data provenance

Every figure and table in the paper (`article/BIBM/main.tex`) maps to specific data
files and a generating script. See **[`DATA_MANIFEST.md`](DATA_MANIFEST.md)** for the
full *figure/table → data → script* mapping and a one-command reproduction recipe.

Exploratory, superseded, and backup artifacts have been moved to **[`archive/`](archive/)**
(see [`archive/README.md`](archive/README.md)); nothing there is needed to reproduce the
paper. Quick pointer:

| Paper element | Generating script |
|---|---|
| Main results table (13 models) | `results/calculate_main_table_score.py` |
| Radar chart (Fig. 2) | `results/plot_combined_radar.py` |
| Violin + method-usage heatmap | `results/plot_violin_and_heatmap.py` |
| Judge calibration table | `results/compute_agreement.py` |
| Table V (inference-time grounding) | `results/aggregate_rag_baseline.py` |

---

## Data card

### MCQ track (`dataset/MCQ/final/all_mcq_data.jsonl`, 2,588 items)

| Category | Count |
| --- | ---: |
| Named Entity Recognition | 533 |
| Domain Knowledge Evaluation | 1,350 |
| Task Scenario Questions | 705 |
| **Total** | **2,588** |

Each MCQ record contains: `question_id`, `question`, `options`, `answers`, `answer_index`, `category`, `knowledge_point`, and `specific`. The pre-split `development.jsonl` and `validation.jsonl` files are also provided.

### OEQ track (`dataset/Q+AR/src/question_final.json`, 253 scenarios)

253 open-ended experiment-design prompts. Each scenario carries the metadata used by the rule-based Effectiveness scorer, including the tissue tier code (`T01`–`T12`), an inferred tissue label, and the marker/target requirements for the question.

### Knowledge bases (`KnowledgeBase/`, 7 JSON files)

| File | Contents | Used by |
| --- | --- | --- |
| `tissue.json` | Marker-site × fluorophore compatibility matrix + category labels | `S_label` |
| `method_fluro_compati.json` | Fluorophore × clearing-method compatibility (0–1) | `S_label` |
| `tissue_ri.json` | Tissue type → intrinsic refractive index | `S_trans` |
| `method_ri_ref.json` | Clearing method → reference-sample RI (with citations) | `S_trans` |
| `method_sigma_ri.json` | (method × tier) → RI tolerance bandwidth σ | `S_trans` |
| `time_kb.json` | (method × tier) → feasible clearing-time interval [min, median, max] | `S_trans` gate + `S_time` |
| `method_time_tau.json` | (method × tier) → time-sensitivity coefficient τ | `S_time` |

---

## The CCE scoring framework (OEQ)

Each generated protocol is mapped onto three dimensions:

**Completeness (Structural Integrity).** A form check verifying that the protocol contains all structured information needed to reproduce the experiment — required procedural steps (pre-processing/fixation, core clearing, labeling) and parametric granularity (explicit reagent identities, concentrations, and numerical time/temperature values rather than vague descriptions). Scored by the LLM judge against a graded rubric.

**Correctness (Scientific Validity).** Detects fatal errors that violate domain consensus or physical law — step ordering, reagent/method chemical consistency, and physical plausibility of key parameters (e.g., diffusion-time sanity per Fick's law). Scored by the LLM judge.

**Effectiveness (Quantitative Feasibility).** A deterministic, rule-based score computed from the knowledge bases:

```
E_score = S_method + S_label + S_trans + S_time
```

- **`S_method`** — cosine similarity between the recommended method's feature vector (from `model_space.json`) and the user-preference vector parsed from the question.
- **`S_label`** — a hard "weakest-link" minimum over target match, marker–fluorophore compatibility, and fluorophore–method compatibility (`tissue.json`, `method_fluro_compati.json`).
- **`S_trans`** — a Gaussian RBF on method–tissue refractive-index domain matching, gated by method/tier support (`tissue_ri.json`, `method_ri_ref.json`, `method_sigma_ri.json`, `time_kb.json`).
- **`S_time`** — a Gaussian decay penalizing predicted clearing times that fall outside the feasible interval for the method/tissue tier (`time_kb.json`, `method_time_tau.json`).

The LLM judge supplies the structured `extraction` fields (method name, marker dictionary, clearing time) that drive the rule-based scores; question-level metadata (tier code, tissue label, target markers) comes directly from the dataset and does not depend on the model under test.

---

## Setup

```bash
pip install -r requirements.txt
```

Configure the model roster and API credentials in `config/config.yaml` (no credentials are committed to this repository — add your own). All commands below are run from the repository root.

---

## Running the OEQ track

The OEQ pipeline (protocol generation + CCE grading) is driven by a single entry point:

```bash
# Full run: generate protocols for the configured models, then grade them
python OEQ_run_grading_new.py

# Grade only, using existing generations in dataset/Q+AR/model_response/
python OEQ_run_grading_new.py --eval-only

# Generate only (skip grading)
python OEQ_run_grading_new.py --no-evaluation

# Restrict to specific models
python OEQ_run_grading_new.py --eval-only --models <model_a> <model_b>

# Choose the judge ("teacher") model and per-model grading concurrency
python OEQ_run_grading_new.py --eval-only --teacher <judge_model> --eval-concurrency 8
```

Key CLI options:

| Option | Default | Description |
| --- | --- | --- |
| `--models` | all configured | Restrict to specific model names (must exist in `config/config.yaml`) |
| `--shot-types` | `1-shot` | Which shot setting(s) to run |
| `--teacher` | judge model in code | Judge ("teacher") model used for Completeness/Correctness + extraction |
| `--eval-concurrency` | `4` | Concurrent questions graded per model |
| `--gen-concurrency` | `4` | Concurrent generations per model |
| `--eval-only` | off | Skip generation; grade existing responses |
| `--no-evaluation` | off | Generate only; skip grading (mutually exclusive with `--eval-only`) |

**Outputs.** Generations are written to `dataset/Q+AR/model_response/from_<model>_<shot>.json`; graded results to `dataset/Q+AR/result/evaluation_results_<model>_<shot>.json`. Results are written incrementally (atomic replace) per question, so an interrupted run resumes by skipping already-graded `question_id`s.

Each graded record stores the per-dimension breakdown (`completeness`, `correctness`, `effectiveness`) with sub-scores and judge reasoning, plus audit fields tracing each rule-based Effectiveness sub-score.

---

## KB-RAG 检索上下文（推理时基线）

推理时实验（Table V）中的 `+KB-RAG` 与 `+KB-RAG+self-check` 两种设置，会在提示词前**拼接一张按场景生成、且不泄漏答案的知识库卡片**。每个 Application 场景生成一个 JSON，并且**对所有模型完全相同**——检索只依据场景元数据（scenario metadata），从不依赖任何模型的输出，因此不会给某个模型“开小灶”。

```bash
python build_rag_context.py                  # -> dataset/Q+AR/rag_context/rag_context_<qid>.json（253 个）
python build_rag_context.py --check-leakage  # 断言任何 prompt 中都不出现被隐藏的数值答案键
```

### 每个上下文文件包含什么

| 字段 | 内容 |
|---|---|
| `scenario_slot_card` | 组织、样本尺寸档位、标记目标、定性需求 |
| `target_marker_cards` | 每个目标对应的**候选 marker 集合**（正确答案在集合内，但不被单独指出） |
| `candidate_method_cards` | 适配该样本档位的透明化方法，每个附一行优点/局限 |
| `compatibility_records` | marker↔荧光团、method↔荧光团 兼容性，标注为 `{compatible / caution / avoid}` |
| `feasibility_card` | 按档位的可行性 + **粗粒度**相对清除速度 |
| `prompt_block` | 真正拼接进模型提示词的渲染文本（由上述字段组装而成） |

### 泄漏策略——为什么“给上下文”≠“给答案”

**暴露的**（定性领域知识）：方法族与样本档位支持、一行优点/局限、目标→marker 的*候选集合*、marker/method↔荧光团 兼容标签、粗粒度相对清除速度。

**隐藏的**（评分器的数值答案键——绝不写入 `prompt_block`）：确切清除时间窗 `[t_min, t_max]`／中位时间、`τ`、`σ_RI`、各方法 `RI_ref` 及组织 RI 值、marker 特异性档位（0/3/6）、金标准/参考协议、“最佳方法”标签、既往模型输出、专家评分。

候选方法排序用的是在需求轴上的**粗粒度符号规则过滤** + 硬性样本档位支持过滤；它刻意**不复用**评分器的 `S_method` 加权 RBF 公式。因此 KB-RAG 提供的是*候选范围与定性兼容性*，而非评分答案——模型仍必须自己给出具体、可行的选择，而评分器的数值阈值始终不可见。

### 渲染后的 `prompt_block` 示例

场景：**小鼠软组织器官，5–20 mm**（档位 `T05`），标记**生殖细胞/生殖系（germ cells / germline）**。

```
=== Retrieved Knowledge-Base Context (numeric RI/time answer keys withheld) ===
[Scenario] Tissue: 性腺 (gonad) | Sample tier: 软组织器官 5–20 mm (T05)
Labeling target(s): 生殖细胞/生殖系 (germ cells / germline)
Requirements: 需要抗体/染料深层穿透；高清除力（致密组织）；保持形态（尽量少收缩）。

[Target -> marker candidates]  (正确答案在集合内)
- 生殖细胞/生殖系: DDX4 / VASA, SYCP3, CD31 / PECAM1, Lectin / IB4
  strategy: 目标特异性免疫染色 (anti-<marker>) 或匹配的基因报告
  caution: 泛谱系/结构性 marker 或核染料 (DAPI) 都不是目标特异性标记

[Candidate clearing methods for this sample tier]  (可选任一成熟方法)
1. uDISCO  [有机溶剂, 高RI]  支持深层穿透、对致密组织清除力强、较快；
   局限: 淬灭内源荧光蛋白（改用抗体/染料）、有收缩风险、有机溶剂有害（需通风橱）
2. iDISCO+ [有机溶剂]        支持深层穿透、清除力强、较快；
   局限: 淬灭荧光蛋白、收缩风险、溶剂有害
3. PEGASOS [有机溶剂, 高RI]  ...
```

模型仍需自己选定一个*具体*的 marker、一个兼容的清除方法、一个 RI 条件，以及一个落在（隐藏的）证据时间窗内的时间——这正是 CCE 的 Effectiveness 子分所检查的。这也解释了为何 KB-RAG 主要提升 `S_label`（marker–target 匹配变容易），却没有把 RI/时间的答案键交出去。

### 三个设置的消融设计（为什么是 3 个版本）

这是一个**用同一套 CCE 评分器**做的、受控的 grounding 消融——不是对 prompt/agent 的全面搜索。三个设置**逐级叠加**，用来把“帮助”归因到具体来源；对**所有模型使用同一张卡片**（不做 per-model 调参），以保证公平：

| 设置 | 加了什么 | 想隔离的问题 |
|---|---|---|
| `1-shot` | 无 grounding，仅靠模型自身知识 + 一个示例 | 模型“裸考”能做到什么 |
| `+KB-RAG` | 前置那张不泄漏答案的场景卡片 | 在数值答案键仍隐藏的前提下，给“候选范围 + 定性兼容性”是否有用 |
| `+KB-RAG+self-check` | 在 grounding 基础上，用**一张固定的可行性 checklist 自查并修订一次** | 廉价的自我批判能否在 grounding 之上再进一步 |

覆盖能力谱的 3 个模型：**GPT-5.2-Fast**、**Qwen3-Max**（两个强模型）、**Qwen3-14B**（弱模型）。此外还测过 3 种**检索变体**（需求排序 / RI-家族感知排序 / RI 感知 + 定性时间提示），见下方「发现 5」；正文只报告未做 per-model 调参的、已发布的 KB-RAG 设置。

### 结果（253 个 Application 场景；Com/Cor/Eff/I_A 为百分比，四个 Eff 子分为 [0,1] 归一化均值）

| 模型 | 设置 | Com | Cor | Eff | I_A | S_method | S_label | S_trans | S_time | ΔI_A | ΔS_label |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT-5.2-Fast | 1-shot | 97.0 | 84.4 | 61.2 | 61.2 | 0.76 | 0.32 | 0.67 | 0.70 | — | — |
| | +KB-RAG | 94.2 | 79.0 | 62.3 | 62.3 | 0.79 | 0.45 | 0.67 | 0.57 | +1.1 | +0.13 |
| | +KB-RAG+SC | 92.0 | 80.2 | 63.2 | **63.2** | 0.79 | 0.60 | 0.60 | 0.54 | +2.0 | +0.28 |
| Qwen3-Max | 1-shot | 87.0 | 72.5 | 60.9 | **60.9** | 0.71 | 0.40 | 0.64 | 0.69 | — | — |
| | +KB-RAG | 85.1 | 73.4 | 57.8 | 57.8 | 0.77 | 0.50 | 0.56 | 0.49 | −3.0 | +0.10 |
| | +KB-RAG+SC | 85.2 | 73.6 | 58.6 | 58.6 | 0.76 | 0.56 | 0.57 | 0.45 | −2.3 | +0.16 |
| Qwen3-14B | 1-shot | 58.4 | 35.3 | 53.5 | 35.3 | 0.73 | 0.28 | 0.66 | 0.46 | — | — |
| | +KB-RAG | 63.1 | 41.8 | 59.8 | 41.8 | 0.73 | 0.52 | 0.66 | 0.48 | +6.5 | +0.24 |
| | +KB-RAG+SC | 63.3 | 42.4 | 60.6 | **42.4** | 0.73 | 0.55 | 0.66 | 0.49 | +7.1 | +0.27 |

复现：`python results/aggregate_rag_baseline.py`（读 `dataset/Q+AR/result/evaluation_results_<model>_<setting>.json`，写出 `results/rag_baseline_summary.csv`）。注意 `I_A = min(Com, Cor, Eff)`，`S_method` 列已按 `(F+1)/2` 折算到 [0,1]。

### 发现

**发现 1 —— grounding 稳定且大幅修好 `S_label`（marker↔target），这是唯一对每个模型都一致、且最大的效应。** 到 `+KB-RAG+self-check` 时：GPT-5.2-Fast 0.32→0.60、Qwen3-Max 0.40→0.56、Qwen3-14B 0.28→0.55。这印证了 Failure Analysis（§IV.D）的诊断：marker–target 错配是第一大、且**可修复**的失败模式（那里 86% 的 `S_label=0` 是 marker–target 错配）。

**发现 2 —— I_A 的净收益被 `min(Com,Cor,Eff)` 这道门“卡”住：grounding 只有抬高了当前的“瓶颈指标”才会真正提升 I_A。**
- 弱模型 **Qwen3-14B**：瓶颈是 **Correctness**（35.3）。grounding 把 Cor 拉到 42.4 → I_A **+7.1**，收益最大。
- 强模型：瓶颈是 **Effectiveness**。GPT Eff 61.2→63.2（+2.0，S_label 的涨盖过了其它损失）；Qwen3-Max Eff 60.9→58.6（**−2.3**，S_label 的涨被反噬掉）。

**发现 3 —— grounding 带来一个 Effectiveness 内部的权衡：强模型 `S_label`↑ 的同时 `S_time`/`S_trans`↓。**
- GPT：S_time 0.70→0.54，S_trans 0.67→0.60。
- Qwen3-Max：S_time 0.69→0.45，S_trans 0.64→0.57（跌得最狠）。
- Qwen3-14B：**没有**这种回退（S_time 0.46→0.49 略升；S_trans 0.665→0.656 几乎持平，仅微降 ~0.01）——因为它本来就低，有上升空间。
- 解读（机制为假设，非因果证明）：卡片给出一份候选**菜单**（marker + method），只隐藏 RI/时间的**精确**数值答案键。关键的是——卡片里其实**已经**包含一份粗粒度的 per-method 清除时间提示（见「改进方向 1」），可强模型的 S_time 仍然回退。这说明问题**不在“信息不够”**，而在 grounding 让 marker 选择变得显眼后，强模型把推理注意力从时间/RI 校准上挪开了。也就是说 grounding **改变了四个轴之间的平衡**，而非把每个轴都抬高。

**发现 4 —— self-check 有用，但消不掉这个权衡。** `+SC` 会再给 `S_label` 一个提升（GPT 0.45→0.60）和小幅 I_A 收益，但 `S_time`/`S_trans` 仍被压低。一张**全局** checklist ≠ 针对性地把时间修回来。

**发现 5 —— 没有任何一个检索变体能同时抬高全部四个 Eff 子分。** 三种变体里 label 总能改善，RI/timing 则随 method 上下文变化。这是一个结构性结论：四个可行性轴是**耦合**的，简单的 grounding 只是在它们之间做取舍。

### 改进方向

1. **把已有的时间提示从“软提示”升级为“硬锚”，并补上目前真正缺失的 RI-家族匹配先验。** 需要澄清一个事实：默认 `+KB-RAG` 卡片其实**已经**给了粗粒度的 per-method 清除时间档位（出现在 Card C、18-方法 mini-index、Card E 可行性提示三处，由 `_method_time_bucket` 生成，只隐藏精确小时数），所以 S_time 的回退是**在已有时间提示的前提下**发生的——单纯“再暴露一个时间档位”是无效的（同理，method 侧的粗粒度 RI 档位也已通过 `high-RI`/`aqueous` 家族标签暴露）。真正**被 withhold** 的是**组织侧的 RI-家族匹配指引**（`_tissue_ri_band` / “RI guidance” 行 + RI 感知重排序，目前只在 `--ri-aware` 变体里）。因此诚实的方向是：(a) 把这条组织侧 RI-家族匹配先验并入默认卡片；(b) 把已有的时间提示从“软提示”升级为“硬锚”——例如给出一个 per-method 的可行时间**窗口**、要求模型的总清除时间落在其中，而不是“暴露一个本已隐藏的时间档位”。
2. **让 self-check 变成“针对性/指标感知”的**，而不是一张全局 checklist——直接盯住回退的那个子分（例如“你是否仍保留了可行的清除时间？”）。
3. **grounding 预算按模型自适应。** 对弱模型（瓶颈 = correctness）是明确净收益；对强模型（瓶颈 = effectiveness 平衡）可能净负——应**选择性**施加。
4. **method/label/RI/time 的联合优化**（四个耦合轴）——超出本 benchmark 范围，但是自然的下一步：完整文献检索 + agentic 协议优化。

### 结论

Grounding 是一个**定点修复**，不是万能加分：它能果断解决 marker–target 问题，但端到端的协议可行性仍取决于对四个耦合约束的平衡——这也正是 I_A 要用 `min(·)` 跨多项可行性检查的原因。

---

## Running the MCQ track

MCQ model responses are stored per model under `dataset/MCQ/model_response/` (one checkpoint file per model), and the evaluated dataset lives in `dataset/MCQ/final/`. Async inference is orchestrated by `MCQ_async_test.py`. Dataset statistics (token-length distributions, per-category breakdowns) can be regenerated with:

```bash
python dataset/MCQ/metric_of_MCQs_gen_from_jsonl.py
python dataset/MCQ/metric_of_MCQs_per_question_gen_from_jsonl.py
```

---

## Aggregation and final scores

The `results/` scripts turn raw per-model outputs into the reported tables and figures:

```bash
# Aggregate MCQ accuracy per knowledge dimension
python results/aggregate_mcq.py

# Aggregate OEQ scores (normalized per CCE sub-dimension)
python results/aggregate_oeq.py

# Combine into the main results table
#   Knowledge index  I_K  (from MCQ)
#   Application index I_A  (from OEQ: Completeness / Correctness / Effectiveness)
#   Total = harmonic mean: 2 * I_K * I_A / (I_K + I_A)
python results/calculate_main_table_score.py

# Judge/human agreement statistics
python results/compute_agreement.py

# Figures
python results/plot_combined_radar.py
python results/plot_violin_charts.py
python results/plot_alignment_combined.py
```

Some aggregation scripts contain a default input filename near the top of the file; adjust it to point at your own run before executing.

---

## License and citation

This repository is released for academic peer review under **double-blind anonymity**. Author, affiliation, and contact information, as well as the formal citation, are intentionally withheld during the review period and will be added in the camera-ready release.

> **Anonymized note:** Please do not attempt to de-anonymize the authors. A license and a BibTeX citation entry will be provided upon publication.
