# R3C04__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/reports/cleareval_20261012/typed_label_transfer/lexical_candidate_02/processing/R3C04__r0.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **72 h**；`candidate_point_applied=True`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 72 | 3 | 0.853304 | 0.6 | 0.511982 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 3 |
| co_method | 2 |
| co_param | 2 |
| co_chem | 1 |
| s_method | 2.375 |
| s_label | 3 |
| s_trans | 2.814647 |
| s_time | 3 |
| sr | 0 |
| sp | 0 |
| Com | 0.6 |
| Cor | 1 |
| Eff | 0.853304 |
| IA | 0.6 |
| HV | 0.511982 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| O1 | core | 1.1 20% (vol/vol) 甲醇/水溶液浸泡，轻摇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O2 | core | 1.2 40% (vol/vol) 甲醇/水溶液浸泡，轻摇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O3 | core | 1.3 60% (vol/vol) 甲醇/水溶液浸泡，轻摇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O4 | core | 1.4 80% (vol/vol) 甲醇/水溶液浸泡，轻摇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O5 | core | 1.5 100% (vol/vol) 甲醇浸泡，轻摇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O6 | core | 1.6 新鲜 100% (vol/vol) 甲醇再次浸泡。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O7 | core | 2.1 5% H2O2 in 甲醇（体积比：30% H2O2 : 甲醇 = 1 : 5）避光浸泡。(Temperature: 4 ℃, Time: 12–16 hours)  | [12.0, 16.0] × 1 | saved core phase, reconciled with explicit source heading |
| O8 | core | 3.1 80% (vol/vol) 甲醇/水溶液浸泡。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O9 | core | 3.2 60% (vol/vol) 甲醇/水溶液浸泡。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O10 | core | 3.3 40% (vol/vol) 甲醇/水溶液浸泡。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O11 | core | 3.4 20% (vol/vol) 甲醇/水溶液浸泡。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O12 | core | 3.5 1×PBS 浸泡。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O13 | excluded | 4.1 渗透液：PBS + 0.2% (vol/vol) Triton X-100 + 20% (vol/vol) DMSO + 0.3 M Glycine，轻摇。(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| O14 | excluded | 4.2 封闭液：PBS + 0.2% Triton X-100 + 10% (vol/vol) DMSO + 6% (vol/vol) 正常驴血清（NDS），轻摇。(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| O15 | excluded | 5.1 一抗孵育液：PBS + 0.2% Triton X-100 + 5% DMSO + 3% NDS + 0.01% (w/v) NaN3；加入 NeuN (RBFOX3) 一抗 1:200。(Temperature: 37 ℃, Time: 5 | — | saved explicit excluded phase |
| O16 | excluded | 5.2 同一孵育液中加入 β-III Tubulin (TUJ1) 一抗 1:300（与5.1可同管共孵育）。(Temperature: 37 ℃, Time: 5–7 days)  | — | saved explicit excluded phase |
| O17 | excluded | 6.1 洗涤液：PBS + 0.2% Triton X-100 + 0.01% NaN3，轻摇换液。(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| O18 | excluded | 6.2 重复 6.1 共 6 次（总洗涤约 36 hours）。(Temperature: RT, Time: 36 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| O19 | excluded | 7.1 二抗孵育液：PBS + 0.2% Triton X-100 + 3% NDS + 0.01% NaN3；加入驴抗鼠/兔（按一抗宿主匹配）Alexa Fluor 647 二抗 1:400（分别对应NeuN与TUJ1；若两一抗宿主不同可同管共孵育 | — | saved explicit excluded phase |
| O20 | excluded | 8.1 PBS + 0.2% Triton X-100 + 0.01% NaN3 洗涤，轻摇换液。(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| O21 | excluded | 8.2 重复 8.1 共 6 次（总洗涤约 36 hours）。(Temperature: RT, Time: 36 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| O22 | excluded | 9.1 TO-PRO-3 1–2 µM（在PBS + 0.2% Triton X-100中），避光轻摇。(Temperature: RT, Time: 12–24 hours)  | — | saved explicit excluded phase |
| O23 | excluded | 9.2 PBS 洗涤 3 次。(Temperature: RT, Time: 2 hours each)  | — | source labeling/preparation heading |
| O24 | core | 10.1 20% 甲醇/水。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O25 | core | 10.2 40% 甲醇/水。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O26 | core | 10.3 60% 甲醇/水。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O27 | core | 10.4 80% 甲醇/水。(Temperature: RT, Time: 1.5 hours)  | [1.5, 1.5] × 1 | saved core phase, reconciled with explicit source heading |
| O28 | core | 10.5 100% 甲醇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O29 | core | 10.6 新鲜 100% 甲醇。(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O30 | core | 11.1 66% (vol/vol) 二氯甲烷(DCM)/33% 甲醇混合液浸泡。(Temperature: RT, Time: 3 hours)  | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| O31 | core | 11.2 100% DCM 浸泡。(Temperature: RT, Time: 2 × 1.5 hours)  | [1.5, 1.5] × 2 | saved core phase, reconciled with explicit source heading |
| O32 | core | 12.1 100% 二苄醚（DBE, RI≈1.56）预浸泡。(Temperature: RT, Time: 3 hours, Light: protected)  | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| O33 | core | 12.2 新鲜 100% DBE 继续浸泡至完全透明（全脑通常需要）。(Temperature: RT, Time: 12–24 hours, Light: protected)  | [12.0, 24.0] × 1 | saved core phase, reconciled with explicit source heading |
| O34 | excluded | 13.1 样本全程浸没于新鲜 100% DBE，避光密封保存（尽量充满容器减少氧化）。(Temperature: RT or 4 ℃, Time: up to 1–2 weeks)  | — | saved explicit excluded phase |
| O35 | core | 13.2 光片成像前更换一次新鲜 DBE 并静置脱气泡/沉降。(Temperature: RT, Time: 1–2 hours)  | [1.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O36 | excluded | 13.3 成像介质与物镜匹配：使用 RI≈1.56 的DBE兼容成像腔与密封材料；样本固定于支架后直接进行全脑光片扫描。(Temperature: RT, Time: per imaging session)  | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
