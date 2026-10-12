# FPC07：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/uniform_v7/actual_01/cells/first7_posthoc/FPC07/posthoc.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **33.5 h**；`candidate_point_applied=True`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 33.5 | 0.401793 | 0.242261 | 0.242261 | 0.125617 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 2 |
| co_method | 1 |
| co_param | 1 |
| co_chem | 1 |
| s_method | -0.38 |
| s_label | 0 |
| s_trans | 1.233337 |
| s_time | 0.401793 |
| sr | 0.444444 |
| sp | 0.272727 |
| Com | 0.777778 |
| Cor | 0.666667 |
| Eff | 0.242261 |
| IA | 0.242261 |
| HV | 0.125617 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP01 | core | 1.1 Incubation with 50% (vol/vol) methanol in distilled water. (Temperature: RT, Time: 3 hours)    | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP02 | core | 1.2 Incubation with 80% (vol/vol) methanol in distilled water. (Temperature: RT, Time: 3 hours)    | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP03 | core | 1.3 Incubation with 100% (vol/vol) methanol. (Temperature: RT, Time: 3 hours)    | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP04 | core | 1.4 Incubation with 100% (vol/vol) methanol. (Temperature: RT, Time: 3 hours)    | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP05 | core | 1.5 Incubation with 100% (vol/vol) dichloromethane (DCM). (Temperature: RT, Time: 30 minutes)    | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP06 | excluded | 2.1 Incubation with staining solution containing Phalloidin conjugated to Alexa Fluor 647 (1:200 dilution) in methanol. (Temp | — | saved explicit excluded phase |
| OP07 | excluded | 2.2 Wash with 100% (vol/vol) methanol. (Temperature: RT, Time: 1 hour)    | — | saved explicit excluded phase |
| OP08 | excluded | 2.3 Wash with 100% (vol/vol) methanol. (Temperature: RT, Time: 1 hour)    | — | saved explicit excluded phase |
| OP09 | core | 3.1 Incubation with BABB-D (1 part Benzyl Alcohol, 2 parts Benzyl Benzoate, 0.04% w/v Diphenyl ether). (Temperature: RT, Time | [3.0, 3.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP10 | core | 3.2 Incubation with fresh BABB-D. (Temperature: RT, Time: Until tissue is transparent, typically 12-24 hours)    | [12.0, 24.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP11 | excluded | 4.1 Store sample in fresh BABB-D at 4°C protected from light until imaging. (Temperature: 4°C, Time: Long-term) | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
