# R3C08__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01/run/attempts/0b141ce2a9d2aaf5c4a8a565c784aec2ae4df43a763021f315b541fb2e5885ee_1/processing.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **NA h**；`candidate_point_applied=False`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 20 | 2.570991 | 0.627238 | 0.627238 | 0.402478 |
| S001 | 32 | 3 | 0.662989 | 0.662989 | 0.425418 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 3 |
| co_method | 2 |
| co_param | 1 |
| co_chem | 1 |
| s_method | -0.4313 |
| s_label | 1.8 |
| s_trans | 2.814647 |
| s_time | 3 |
| sr | 0.333333 |
| sp | 0.114286 |
| Com | 0.733333 |
| Cor | 0.875 |
| Eff | 0.662989 |
| IA | 0.662989 |
| HV | 0.425418 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP1 | core | Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP2 | core | Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP3 | core | Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP4 | core | Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP5 | core | Incubation with 100% (vol/vol) methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP6 | core | Incubation with 100% (vol/vol) methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP7 | core | Incubation with chilled fresh 5% (vol/vol) H₂O₂ in methanol (1 volume 30% H₂O₂ to 5 volumes MeOH).(Temperature: 4 ℃, Time: 12 | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP8 | core | Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP9 | core | Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP10 | core | Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP11 | core | Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP12 | core | Incubation with PBS + 0.2% (vol/vol) Triton X-100 (PBT).(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP13 | excluded | Incubation with PBT + 20% (vol/vol) DMSO + 0.3 M glycine.(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| OP14 | excluded | Incubation with PBT + 10% (vol/vol) DMSO + 6% (wt/vol) donkey serum (blocking buffer).(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| OP15 | excluded | Incubation with anti-β-III Tubulin (TUJ1) primary antibody diluted 1:500 in blocking buffer.(Temperature: 37 ℃, Time: 72 hour | — | saved explicit excluded phase |
| OP16 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP17 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP18 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP19 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP20 | excluded | Incubation with Alexa Fluor 647-conjugated donkey anti-mouse IgG (H+L) diluted 1:300 in blocking buffer.(Temperature: 37 ℃, T | — | saved explicit excluded phase |
| OP21 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP22 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP23 | excluded | Incubation with PBT.(Temperature: RT, Time: 6 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP24 | core | Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP25 | core | Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP26 | core | Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP27 | core | Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP28 | core | Incubation with 100% (vol/vol) methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP29 | core | Incubation with 100% (vol/vol) methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP30 | core | Incubation with dichloromethane (DCM).(Temperature: RT, Time: 30 minutes)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP31 | core | Incubation with dichloromethane (DCM).(Temperature: RT, Time: 30 minutes)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP32 | core | Incubation with 100% (vol/vol) dibenzyl ether (DBE, Sigma 108014-1KG) without shaking.(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP33 | excluded | Transfer brain to glass vial filled with fresh DBE and store at RT in the dark until light-sheet imaging.(Temperature: RT, Ti | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
