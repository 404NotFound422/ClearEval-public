# Marker 与 Fluorophore 评分精细化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 S_label 的 `target_match` 与 `marker_fluor_compat` 评分对“描述性/过宽 marker”更严格，对荧光团映射更基于证据，并提供可人工审核的分级表与 LLM fallback。

**Architecture:** 在 `OEQ_run_grading_new.py` 中引入显式分级表（`specific=6`, `incomplete_but_reasonable=3`, `vague/descriptive=0`），代码规则优先，规则无法覆盖时调用小模型做二/三分类；荧光团映射改为“逐染料证据表”，由子智能体为常见未映射染料查找与 tissue.json 现有列的兼容性依据（文献、光谱、化学家族），不再按颜色通道泛化映射。

**Tech Stack:** Python 3.12, JSON, OpenAI/Kimi-compatible small model API (`openai_gpt-5.2-fast` or local small model), `OEQ_run_grading_new.py`.

## Global Constraints

- 所有改动必须通过 `python -m py_compile` 与 `ruff check`。
- 不得删除 `dataset/Q+AR/result/original_backup/` 中的原始结果备份。
- 任何 patch 到 `evaluation_results_*.json` 的操作必须先备份当前版本。
- Hansen 溶解性参数数据由用户提供，本计划在收到数据前不实现 Task 4。

---

## Task 1: 制定并固化 Marker 特异性分级表

**Files:**
- Create: `workflow/s_label_audit/marker_specificity_tiers.json`
- Reference: `workflow/s_label_audit/marker_kb_supplement_suggestions.json`
- Reference: `workflow/s_label_audit/s_label_zero_samples_for_review.jsonl`

**Interfaces:**
- Consumes: subagent-generated marker supplement suggestions
- Produces: a JSON file with three explicit lists: `tier_6` (proper markers/aliases), `tier_3` (incomplete but inferable), `tier_0` (vague/descriptive)

- [ ] **Step 1: 收集候选 marker 并分类**

从 `marker_kb_supplement_suggestions.json` 和 `s_label_zero_samples_for_review.jsonl` 中提取所有出现过的 marker 字符串，按以下规则预分类：

```json
{
  "tier_6": [
    "IB4 lectin", "TH (Tyrosine Hydroxylase)", "Brn3a (POU4F1)",
    "Podocin/NPHS2", "alpha-SMA", "Lectin (IB4)"
  ],
  "tier_3": [
    "Alexa Fluor (unspecified)", "Alexa Fluor (secondary)",
    "GFP reporter (unspecified)", "endogenous reporter"
  ],
  "tier_0": [
    "endogenous tracer", "nuclei", "细胞核", "神经元/神经纤维",
    "血管腔面/灌流标记", "endogenous", "reporter signal"
  ]
}
```

分类原则：
- `tier_6`: 能唯一对应一个具体蛋白/结构的 marker 名或公认别名。
- `tier_3`: 信息不完整，但能合理推断其意图（如指定了荧光团家族但未指定波长、明确是 reporter 但未说明具体荧光蛋白）。
- `tier_0`: 纯描述词、过宽概念、无法锁定具体 marker。

- [ ] **Step 2: 人工复核并写入 JSON 文件**

将预分类结果写入 `workflow/s_label_audit/marker_specificity_tiers.json`，供后续代码读取。该文件应被视为需要用户持续维护的配置表。

---

## Task 2: 实现 Marker 特异性分级逻辑与 LLM Fallback

**Files:**
- Modify: `OEQ_run_grading_new.py:265-480` (matching helpers)
- Create: `workflow/s_label_audit/test_marker_tiers.py` (quick sanity tests)

**Interfaces:**
- Consumes: `marker_specificity_tiers.json`
- Produces: `_classify_marker_specificity(marker_str) -> int` (0/3/6)
- Produces: `_match_marker_to_targets(...)` returns `(matched: bool, score: float)` or keeps returning bool with caller using tier score

- [ ] **Step 1: 加载分级表**

在 `OEQ_run_grading_new.py` 中新增：

```python
_MARKER_SPECIFICITY_TIERS: dict = json.load(
    open('workflow/s_label_audit/marker_specificity_tiers.json', encoding='utf-8')
)


def _classify_marker_specificity(marker_str: str) -> int:
    """Return 0/3/6 based on explicit tiers; -1 if unknown."""
    norm = _normalize_name(marker_str)
    if norm in _MARKER_SPECIFICITY_TIERS.get('tier_0', []):
        return 0
    if norm in _MARKER_SPECIFICITY_TIERS.get('tier_3', []):
        return 3
    if norm in _MARKER_SPECIFICITY_TIERS.get('tier_6', []):
        return 6
    # substring match for tier_0 vague phrases
    for vague in _MARKER_SPECIFICITY_TIERS.get('tier_0', []):
        if vague in marker_str or marker_str in vague:
            return 0
    return -1  # needs LLM fallback
```

- [ ] **Step 2: 在 target_match 计分循环中应用分级**

修改 `calculate_effectiveness_score` 中 target_match 计分循环：

```python
for fluor, marker in marker_dict.items():
    marker_str = str(marker).strip() if marker else ""
    fluor_str = str(fluor).strip() if fluor else ""
    if not marker_str:
        continue

    specificity = _classify_marker_specificity(marker_str)
    if specificity == -1:
        specificity = _llm_classify_marker_specificity(marker_str, fluor_str, marker_query_targets)

    if _match_marker_to_targets(marker_str, marker_query_targets, fluor_name=fluor_str):
        target_match_scores.append(6.0)
    else:
        # tier_0 直接 0 分，不再尝试 major_category 回退
        if specificity == 0:
            target_match_scores.append(0.0)
        else:
            marker_major = _get_tissue_major_category(marker_str)
            question_major = marker_query_targets[0].get("major_category", "") if marker_query_targets else ""
            if marker_major and question_major and marker_major == question_major:
                target_match_scores.append(3.0)
            else:
                target_match_scores.append(0.0)
```

- [ ] **Step 3: 实现 LLM fallback**

新增函数 `_llm_classify_marker_specificity(marker_str, fluor_str, marker_query_targets) -> int`：

```python
async def _llm_classify_marker_specificity(marker_str, fluor_str, marker_query_targets):
    prompt = (
        "You are classifying a marker description from a microscopy protocol.\n"
        "Classify the following marker into one of:\n"
        "- 6: a specific, named marker (e.g., MAP2, CD31, GFP reporter)\n"
        "- 3: incomplete but inferable (e.g., 'Alexa Fluor' without wavelength, 'endogenous reporter')\n"
        "- 0: vague/descriptive, not a marker (e.g., 'nuclei', 'vascular lumen label', 'cells')\n\n"
        f"marker: {marker_str}\n"
        f"fluorophore: {fluor_str}\n"
        f"question targets: {[t.get('marker_name') for t in marker_query_targets]}\n\n"
        "Return only the integer 0, 3, or 6."
    )
    # Use a fast/cheap model; fallback to 0 on error
    try:
        # model call placeholder - use ModelLoader or direct API
        response = await _small_model_acall(prompt)
        score = int(response.strip())
        if score in (0, 3, 6):
            return score
    except Exception:
        pass
    return 0
```

注意：`calculate_effectiveness_score` 当前是同步函数。需要决定：
- 方案 A：将 `_llm_classify_marker_specificity` 设计为同步调用（用 `asyncio.run` 或阻塞调用）。
- 方案 B：把 target_match 评分改为异步，但这会波及调用链。

推荐方案 A：在 fallback 函数内部用 `asyncio.run()` 包装一个小的 async helper，或直接使用项目的 `ModelLoader` 同步接口（如果存在）。

- [ ] **Step 4: 验证测试**

运行：

```bash
python workflow/s_label_audit/test_marker_tiers.py
```

测试覆盖：
- `nuclei` → 0
- `血管腔面/灌流标记` → 0
- `Alexa Fluor (unspecified)` → 3
- `IB4 lectin` → 6
- `MAP2` → 6 (通过现有别名表)

---

## Task 3: 建立荧光团证据型映射框架

**Files:**
- Create: `workflow/s_label_audit/fluorophore_evidence_framework.md`
- Create: `workflow/s_label_audit/fluor_evidence_subagent_prompt.md`
- Create: `workflow/s_label_audit/launch_fluor_evidence_subagents.py`
- Reference: `workflow/s_label_audit/fluor_mapping_supplement_suggestions.json`

**Interfaces:**
- Consumes: list of unmapped fluorophores from S_label=0 cases
- Produces: `workflow/s_label_audit/fluorophore_evidence_suggestions.json` with evidence links/reasoning

- [ ] **Step 1: 挑选需要证据的未映射荧光团**

从 `fluor_mapping_supplement_suggestions.json` 中过滤出 `action == "map_to_existing"` 或 `new_column` 的条目，去除明显可忽略的（如未指定波长的 Alexa Fluor），得到需要逐染料查证据的列表。

- [ ] **Step 2: 编写子智能体 prompt**

`fluor_evidence_subagent_prompt.md` 要求子智能体：
- 对给定染料，搜索/回忆其光谱特性（激发/发射峰）、化学结构类别、透明化方法兼容性证据。
- 判断它是否可以归入 tissue.json 的某一现有列（需提供理由，不建议简单按颜色分类）。
- 如果不确定，标记为 `needs_expert_review`。

- [ ] **Step 3: 并行派发子智能体**

`launch_fluor_evidence_subagents.py` 按染料分批派发（每批 5-10 个染料），收集结果到 `fluorophore_evidence_suggestions.json`。

- [ ] **Step 4: 人工审核后再改代码**

在子智能体返回证据前，**不修改** `_map_fluor_to_tissue_col`。证据文件生成后，由用户审核哪些映射可以接受，再进入 Task 5 更新代码。

---

## Task 4: 集成 Hansen 溶解性参数数据

**Files:**
- TBD: user-provided Hansen data file
- Modify: `OEQ_run_grading_new.py` fluor mapping helpers

**Interfaces:**
- Consumes: user-provided Hansen solubility parameters for dyes
- Produces: `_find_closest_fluor_by_hansen(unknown_dye) -> target_column`

- [ ] **Step 1: 等待用户提供数据格式**

数据至少应包含：
- dye name
- δD, δP, δH (dispersion, polar, hydrogen-bonding Hansen parameters)
- 或至少一个可计算距离的向量

- [ ] **Step 2: 实现 Hansen 相似性查找**

```python
def _hansen_distance(d1, d2):
    return ((d1['dD'] - d2['dD'])**2 * 4 +
            (d1['dP'] - d2['dP'])**2 +
            (d1['dH'] - d2['dH'])**2) ** 0.5
```

对未知染料，在已知染料中找 Hansen 距离最近的，并返回其对应 tissue.json 列。

- [ ] **Step 3: 与证据映射合并优先级**

优先顺序：
1. 显式别名/证据映射
2. Hansen 相似性映射（仅当距离低于阈值）
3. 返回 None（不惩罚）

---

## Task 5: 重新评分并输出审核包

**Files:**
- Modify: `workflow/s_label_audit/patch_s_label_scores.py`
- Create: `workflow/s_label_audit/s_label_zero_samples_for_review_v2.jsonl`
- Create: `workflow/s_label_audit/s_label_zero_samples_for_review_v2.md`

- [ ] **Step 1: 备份当前 patched 结果**

将当前 `dataset/Q+AR/result/evaluation_results_*.json` 复制到 `dataset/Q+AR/result/patched_v1_backup/`。

- [ ] **Step 2: 运行 patch 脚本**

```bash
python workflow/s_label_audit/patch_s_label_scores.py
```

- [ ] **Step 3: 提取新的 S_label=0 样本**

```bash
python workflow/s_label_audit/extract_s_label_zero_for_review.py
```

输出文件后缀改为 `_v2` 以区分版本。

- [ ] **Step 4: 对比 v1 → v2 的变化**

生成 `workflow/s_label_audit/s_label_v1_vs_v2_comparison.json`：
- 总体 S_label 均值变化
- 每模型 S_label=0 数量变化
- target_match 子分分布变化

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-30-marker-fluor-refinement.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

**Blocked item:** Task 4 requires user-provided Hansen solubility data.

**Which approach, and should I start with Task 1 & 2 now while waiting for Hansen data?**
