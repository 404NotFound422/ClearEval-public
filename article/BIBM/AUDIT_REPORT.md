# ClearEval (BIBM) 论文审查报告

审查对象：`article/BIBM/main.tex`（编译版 `main.pdf`，8 页）。
方法：5 个维度（数字/数据一致性、过度声称、阅读顺序、内部一致性、逻辑漏洞）并行排查，每条发现都由独立 agent 重新打开源文件与数据文件对抗式复核。
结果：29 条候选 → **19 条确认 + 1 条存疑**（9 条复核后被否决）。所有数字均从 `results/*.jsonl`、`dataset/Q+AR/result/*.json`、`article/BIBM/figures/fig_data/*.json` 复算核对。

---

## 修复进度（更新，编译已回到 8 页、无 undefined ref）

**已修复并重编译：**
- ✅ STRUCT-01 `91.1%`→`91.1\%`（引言乱码句）
- ✅ 池子大小：line 611 `3,272`→`3,287`、violin caption `253×13`→`3,287`
- ✅ IC-03 timing DB `84`→`126` 行
- ✅ OC2 "highly erratic"→"far more dispersed and model-dependent"（正文 + caption）
- ✅ LG-1 S_label=0 断言改为"86% 是 marker–target mismatch，~14% fluorophore 兼容性；quenching ~41% 绑定、~10% 归零"
- ✅ LG-2 I_K 定义改为显式"两级 macro（三大组各自 macro 后再平均）"
- ✅ **OC3（新增，见下）：§IV.D 方法锚定段重写，调和"S_method 高"与"锚定 iDISCO+"的矛盾**
- ✅ STRUCT-04 引言新增 `Fig.~\ref{fig:overview}` 交叉引用
- ✅ STRUCT-05 `sec: ClearEval-benchmark`（含空格）→`sec:benchmark`
- ✅ IC-04 `Qwen3-max`→`Qwen3-Max`；F5 表IV Qwen3-Max 1-shot 行 `87.1/72.6/53.7`→`87.0/72.5/53.6`

**✅ F1/F2 已应用（用户选择"重算，不加 caveat"）：** 主表 Eff/I_A/Total + 表IV Eff/I_A + 摘要/引言 + §IV 相关 prose 全部按新 `(F+1)/2` 重算；同时修复 `calculate_main_table_score.py:54` 与 `plot_combined_radar.py`（s_method 轴 rescale）并重生成 radar_chart.png。重编译 8 页、无 undefined ref。摘要头条 55.2→61.2。

### 🆕 OC3 — "S_method 高" 与 "模型集中锚定 iDISCO+" 的矛盾（已在正文调和）
数据判定：13 个模型 S_method 全挤在 0.69–0.76（跨度 0.07），`corr(熵,S_method)=+0.26`——**指标对"是否锚定"几乎不敏感**。最锚定的 Qwen3-14B（74% iDISCO+）S_method=0.732，与最多样的 Gemini-3-Flash（0.724）持平。原因：iDISCO+ 是高分万金油（被选时 mean S_method=0.78，仅 7% 冲突），场景又偏厚组织/全器官。
→ 论文原文把方法锚定当"bias overriding reasoning"（失败）来批评，却又说 S_method 高、method choice 没问题——自相矛盾。**已重写为：同一频率先验同时驱动方法锚定与标记选择；因 iDISCO+ 广谱适配，方法锚定基本无害（S_method 保持高，且该指标只反映"是否冲突"而非"是否逐场景推理"），先验的代价集中体现在标记上（S_label 崩溃）。** 这让叙事更自洽，也澄清了"S_method 高 ≠ 模型做了方法推理"。

### F1/F2 专节 — 主表重算结果（待决策）
把 Eff 的 method 项从"直接平均 signed F"改为论文公式 Eq.(2) 的 `(F+1)/2` 后（根因 `results/calculate_main_table_score.py:54`）：

| 模型 | I_K | Eff 旧→新 | I_A 旧→新 | Total 旧→新 |
|------|-----|-----------|-----------|-------------|
| GPT-5.2-Fast | 91.1 | 55.2→**61.2** | 55.2→**61.2** | 68.7→**73.2** |
| GPT-5.2-Think | 90.5 | 54.4→60.5 | 54.4→60.5 | 68.0→72.5 |
| Gemini-3-Flash | 83.8 | 52.2→59.1 | 52.2→59.1 | 64.3→69.3 |
| Gemini-3-Pro | 84.2 | 46.6→53.1 | 46.6→53.1 | 60.0→65.1 |
| Claude-4.6 | 88.5 | 56.2→62.3 | 56.2→62.3 | 68.7→73.1 |
| GLM-4.7 | 84.3 | 53.4→60.6 | 53.4→60.6 | 65.4→70.6 |
| GLM-4.7-Think | 80.0 | 47.6→54.2 | 47.6→51.1(Com) | 59.7→62.3 |
| DeepSeek-V3.2 | 83.1 | 41.6→49.3 | 41.6→49.3 | 55.4→61.9 |
| DeepSeek-V3.2-Th | 87.5 | 41.3→49.0 | 41.3→49.0 | 56.1→62.9 |
| Qwen3-Max | 86.8 | 53.6→60.9 | 53.6→60.9 | 66.2→71.6 |
| Qwen3-235B | 82.6 | 50.1→56.4 | 50.1→52.4(Cor) | 62.3→64.1 |
| Qwen3-32B | 80.6 | 45.1→51.3 | 45.1→50.8(Cor) | 57.8→62.3 |
| Qwen3-14B | 79.9 | 46.8→53.5 | 35.3→35.3(Cor) | 48.9→48.9 |

- **摘要头条 55.2 → 61.2。** Eff 每个模型 +6~7pp（全部来自 S_method 0.46–0.52→0.73）。
- **排名**：top6 不变（GPT-5.2-Fast 仍第一）；中段 Gemini-3-Pro 升过 Qwen3-235B、DeepSeek-Th 升过 GLM-4.7-Think/Qwen3-32B。
- **叙事不变**：Eff 仍是多数模型瓶颈、S_label 仍是主导子失败、知识–执行差距仍大（91 vs 61）。Qwen3-14B I_A 不变（Correctness 绑定）。
- **⚠ 权衡**：修复本身正确（把 signed F 当 [0,1] 平均是 bug），但抬升的 Eff 完全靠"对锚定不敏感的宽松 S_method"（见 OC3）。若担心显得"数字变好看"，可在正文加一句 OC3 的 caveat。

---

## 优先级速览（按修复紧迫度）

| # | 级别 | 问题 | 位置 |
|---|------|------|------|
| 1 | 🔴 严重 | **S_method 指标三处取值不可调和**，表IV 每行内部自相矛盾，Eff/I_A/摘要数字用的是旧值 | 主表、摘要、图4、表IV |
| 2 | 🔴 严重 | **"Every S_label=0 是 target mismatch / quenching 从不归零" 被自己数据推翻**（头条结论支撑句） | line 582-584 |
| 3 | 🟠 主要 | **评测池大小一页内出现三个数**（3,272 / 3,289 / 真值 3,287） | line 575, 601, 611 |
| 4 | 🟠 主要 | **I_K 聚合口径含糊**，实际是两级 macro，审稿人 flat 复现会对不上 | line 271, 主表 |
| 5 | 🟠 主要 | **数据库清单表 timing "84 行" 与实际 126 行不符** | line 236 |
| 6 | 🟠 主要 | **radar caption "highly erratic" 过度声称**（实为系统性单调下降） | line 510, 570 |
| 7 | 🟡 次要 | LaTeX `%` 未转义，引言这句渲染成乱码 | line 136 |
| 8+ | 🟡 次要 | 舍入、命名、倒挂引用、未引用 label 等 6 项 | 见下 |
| ⚠ | 待确认 | **MCQ "2,588" vs 实际只评了 768 道**；"372 wet-lab records"/"400+ chunks" 无法溯源 | 摘要/引言 |

---

## 一、严重问题（投稿前必须修）

### 🔴 F1+F2 — S_method 指标口径混乱，Eff/I_A/摘要数字全部受影响
这是最严重的一处"数据对不上"，涉及论文头条数字。

**证据链：**
- **表IV 每一行内部自相矛盾。** 例如 GPT-5.2-Fast 1-shot 行显示 `S_m=0.76, S_lab=0.32, S_tr=0.67, S_ti=0.70, Eff=55.2`。但论文自己的公式 Eq.(2) 是 `Eff = (S_method+S_label+S_trans+S_time)/4`，代入应得 **61.3**，不是 55.2。9 行全部偏 −5.0 ~ −7.5。
- **根因：** 主表与表IV 的 Eff 列是用**旧** s_method（`score/2.5 ≈ 0.46–0.52`，来自 `oeq_stats_260223.jsonl`）算的——代入能精确复现 55.2；但正文 §IV.D、图4、表IV **显示**的是**新** signed `S_method=(F_method+1)/2 ≈ 0.73–0.76`。同一个量，显示值和参与计算的值不是一个东西。
- **同一个 S_method 在数据文件里有三个不可调和的取值：** base 加权均值 **0.462** / 图4 池均值 **0.731** / v2 文件 **0.887**。
- **后果：** 若统一改用新 s_method 重算，Eff/I_A 会上升 **约 +6~+10 分**（GPT-5.2-Fast 55.2→64.7、Claude 56.2→65.9、Qwen3-14B 46.8→57.1），**摘要头条"55.2"和整个模型排名都会变**。

**修复：** 全局只用**一个** S_method 定义（与 §IV.D/图4 宣称的 `S_method=0.73`、ICC 0.82 一致），重算整张主表的 Eff/I_A/Total（调和平均需一并重算）、表IV、摘要与引言里的所有下游数字。根因文件：`results/calculate_main_table_score.py:54`。
（注：ICC 0.82 本身溯源正确，`agreement_stats.json` s_method icc=0.816；出错的是 S_method 的**量级**，不是 ICC。）

### 🔴 LG-1 — "S_label=0 全是 target mismatch / quenching 从不归零" 是错的
这两句是绝对化断言，且直接支撑论文头条发现（摘要、引言贡献点 3、结论）。

- 正文 line 582-584：*"Every S_label=0 is a target mismatch; the quenching check often binds (~44%) but stays high (4.2/6) and never zeros."*
- **repo 自己的数据推翻它：** 1,752 个 `S_label=0` 中，只有 1,516（86.5%）是 target mismatch；**237 个（13.5%）** target_match 非零、是被 fluorophore 兼容性检查归零的。quenching check（`s_method_fluor_compat`）**确实**有 **317 次（9.6%）归零**——"never zeros" 不成立。
- 括号里的近似值（~44%、4.2/6）没问题；错的只是两个绝对化子句。

**修复（保留头条结论、只让子句为真）：** 改为 *"86% (1516/1753) of S_label=0 cases are marker–target mismatch; the remaining ~14% are fluorophore-compatibility failures. The quenching check binds in ~41% of protocols, staying high on average (4.2/6) but zeroing in ~10% of cases."*

---

## 二、评测池大小：一页内三个数对不上（🟠 主要，数据一致性）

同一个评测池（253 场景 × 13 模型）在 §IV.D 内被写成三个互不相等的数：

| 位置 | 写法 | 含义 |
|------|------|------|
| line 601（violin caption） | `253×13 protocols` | 3,289 |
| line 575（诊断段开头） | "all 253 scenarios and 13 models" | 隐含 3,289 |
| line 611（method path-dependence） | "43% of all **3,272** choices" | 3,272 |
| **真值** | `fig4_violin.json` n / `oeq_stats` sample_count 之和 / 原始 target_method 计数 | **3,287** |

- Gemini-3-Flash 实际只评了 **251/253**（论文脚注 line 529-531 自己承认），所以真值是 `12×253 + 251 = 3,287`，不是干净的 3,289。
- **43% 这个比例是对的**（iDISCO+ = 1411/3287 = 42.9%），错的是分母。3,272 在任何数据文件里都不存在。

**修复：** line 575 / 601 / 611 统一用 **3,287**（并与 251/253 脚注呼应）。
（这一簇对应确认项 F3、STRUCT-02、IC-01、IC-02、F4、LG-5，是同一根因的不同表现。）

---

## 三、其他主要问题（🟠）

### LG-2 — I_K 聚合口径含糊，审稿人复现会对不上
- line 271 定义：*"I_K is the macro-averaged accuracy over MCQ categories."* MCQ 题库有 **9 个叶子类**，"macro over categories" 最自然的读法是 9 类均值。
- **但实际算的是 3 大组（Tissue/Reagent/Method）均值再平均**，等于给 Method 的 5 个叶子类各降权到 1/15（vs Tissue 叶子 1/6）。
- 两种口径数字不同：flat mean-of-9 vs 表里 mean-of-3——GPT-5.2-Fast 91.9 vs **91.1**、Gemini-3-Flash 86.3 vs **83.8**、Claude 90.6 vs **88.5**。审稿人拿 `mcq_stats` 按"macro over categories"复算会得到不一样的数并质疑。

**修复：** 明确写成"三大组精度的均值（两级 macro）"，或改为 9 类 flat macro 并更新数字。使口径可复现。

### IC-03 — 数据库清单表 timing "84 行" 与实际不符
- line 236（Table I db_inventory）："Timing database (τ): **84** (method, tier) rows"。
- 实际 `KnowledgeBase/time_kb.json` 有 **126 行**（unique (method,tier)=126、方法数=17、粗 tier=12）。84 无法由任何自然分组得到。

**修复：** 改成 126（或明确说明在数 17 methods × 12 tiers 的哪一种）。

### OC2 — radar caption "highly erratic" 过度声称（图声称太大）
- line 510 / 570："Application performance is highly erratic" / "CCE scores are highly erratic"。
- 但数据是**系统性、随模型规模近乎单调下降**的：I_A 只在 35.3–56.2 窄带内（CV 0.13），Eff CV 仅 0.10；caption 点名的 CCE 子指标恰恰是**方差最小**的几个轴（s_method CV 0.10、s_trans CV 0.05）。"erratic"（杂乱无章/随机）名不副实，实际只是"比 MCQ 分散 ~3.4×"。

**修复：** 改为 "far more dispersed" 或 "highly variable and model-dependent"。

---

## 四、次要问题（🟡，可快速修）

- **STRUCT-01 — LaTeX 转义 bug（建议优先修）：** `main.tex:136` 写的是 `91.1%` 未加反斜杠。`%` 在 LaTeX 里是注释符，导致引言这句渲染成乱码 *"…achieves 91.1Index but only 55.2…"*（后半句被吞、下一行拼接上来）。摘要 line 70 写的是正确的 `91.1\%`。**改：`91.1%` → `91.1\%`。**
- **F5 — 两表舍入不一致：** 表IV Qwen3-Max 1-shot 行 `87.1/72.6/53.7`，主表同一模型 `87.0/72.5/53.6`。源数据是 86.957/72.527/53.560，**主表对、表IV 每项 +0.1**。（另两个模型两表一致。）改表IV 该行为 87.0/72.5/53.6/53.6。
- **STRUCT-04 — overview 图倒挂引用：** 全宽 overview 图放在引言顶部（page 1，line 85），但**第一次也是唯一一次引用**在 §III（line 206），引言里从未提及。审稿人常挑"图先于引用出现"。建议在引言介绍 ClearEval 处加一句 `Fig.~\ref{fig:overview}`。
- **STRUCT-05 — 三个未引用的 section label：** `sec:related`(154)、`sec: ClearEval-benchmark`(203)、`sec:discussion`(691) 定义了但从未 `\ref`；其中 `sec: ClearEval-benchmark` 的 key 里**含空格**（隐患）。建议删除或重命名为 `sec:benchmark`。
- **IC-04 — 大小写不一致：** 主表 line 555 写 `Qwen3-max`（小写 m），其余全文都是 `Qwen3-Max`。
- **IC-05 — DeepSeek 命名不一致：** 主表 `DeepSeek-V3.2` / `DeepSeek-V3.2-Think`，图（heatmap）与 caption line 623 里是 `DeepSeek` / `DeepSeek-Think`，掉了版本号。建议统一或加一句注明。
- **LG-6 — 等权重未论证：** 校准最差的 S_label（ICC 0.51）与校准最好的 S_method（ICC 0.82）在 Effectiveness 里**等权 25%**，且 S_label 是 hard-min、驱动了 12/13 个模型的 I_A 瓶颈，论文没为"为何保留弱校准的 S_label 于等权"辩护。建议补一句正当性说明（可引用 86% 的 S_label=0 是确定性 target mismatch 作为"低 ICC 仍可信"的依据）。

---

## 五、需作者确认的数据溯源项（未列为确认 finding，但重要）

- ⚠ **MCQ 数量 2,588 vs 768：** 数据显示 13 个模型实际只在 **768 道 MCQ**（development split）上评测，全题库 2,588、validation split 仅 30。若论文把"2,588"当作**实际评测规模**表述，则不准确；若是指题库规模则可接受。**请核对摘要/引言里 2,588 的语境。**
- **"372 wet-lab records"：** 未能在数据文件里定位到单一带标签的来源（最接近的是 `time_kb.json` 126 条文献派生 timing 行，但那是文献综述派生、非原始 wet-lab）。
- **"400+ literature chunks"：** 未找到单一 chunk 计数文件（RAG context 是 253 个场景文件、1171 candidate cards / 506 compatibility records）。
- **db_inventory 表 "20 methods" vs timing KB 只覆盖 17 methods**：timing KB 未覆盖全部 20 方法 × 全部 tier；若别处声称"全覆盖"需修正。

---

## 六、阅读顺序整体评价

- 重排后的顺序（fig1 → DB清单表 → 校准 → 主结果 → radar → violin → heatmap → 表IV）**基本合理**；"先校准证明可信、再展示结果"逻辑通顺，无前向依赖问题。
- order 维度的实质问题集中在：**overview 图倒挂引用**（STRUCT-04）与**池子数散落不一致**（§IV.D，见第二节）。

---

## 附：被检查但判定不成立/存疑的项

- **OC1（否决）** — "static knowledge close to saturation"：复核认为对 top 模型（88–91%）基本可接受，未列为问题。
- **LG-7（存疑）** — repo 里的 `results/smethod_validation_60_v2.json`（n=60，本地 qwen3:8b 评判）里，新 signed S_method 的 ICC=−0.496，表面上与正文 ICC 0.82 矛盾；但复核发现那是**未 rescale 的原始值 vs 1–5 人评的尺度偏移伪影**，不是论文部署的 [0,1] 指标。建议：要么在附录注明这是小样本本地模型探针、要么从 release 移除该消融文件，避免有 repo 访问权的审稿人误会为"挑数据"。

---

## 安全备注
`config/config.yaml` 含明文 API key（数据侧扫描顺带发现）。按既定要求：**不改明文 key，只需确认已在 `.gitignore` 中忽略**。
