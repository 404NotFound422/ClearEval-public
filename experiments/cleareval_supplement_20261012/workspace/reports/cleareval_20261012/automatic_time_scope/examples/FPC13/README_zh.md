# FPC13：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/uniform_v7/actual_01/cells/secondary8_posthoc/FPC13/posthoc.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **158 h**；`candidate_point_applied=True`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 158 | 0.000003 | 0.62361 | 0.4 | 0.135116 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 2 |
| co_order | 2 |
| co_method | 0 |
| co_param | 1 |
| co_chem | 1 |
| s_method | 0.9722 |
| s_label | 4.8 |
| s_trans | 3 |
| s_time | 0.000003 |
| sr | 0 |
| sp | 0 |
| Com | 0.4 |
| Cor | 0.541667 |
| Eff | 0.62361 |
| IA | 0.4 |
| HV | 0.135116 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP0001 | core | 1.1 Incubation with 10% (vol/vol) glycerol in PBS (Temperature: RT, Time: 12 hours)    | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0002 | core | 1.2 Incubation with 20% (vol/vol) glycerol in PBS (Temperature: RT, Time: 12 hours)    | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0003 | core | 1.3 Incubation with 30% (vol/vol) glycerol in PBS (Temperature: RT, Time: 12 hours)  | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0004 | core | 2.1 Incubation with PBS (Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0005 | core | 3.1 Incubation with CUBIC-U (50 mM NaCl, 100 mM choline chloride, 0.5% wt/vol TX-100, 0.2% wt/vol BSA in PBS) (Temperature: 3 | [72.0, 72.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0006 | core | 4.1 Incubation with CUBIC-R (50 mM NaCl, 100 mM choline chloride, 0.2% wt/vol BSA in PBS) (Temperature: RT, Time: 24 hours)  | [24.0, 24.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0007 | excluded | 5.1 Incubation with 0.1% Triton X-100 in PBS for permeabilization (Temperature: RT, Time: 1 hour)    | — | saved explicit excluded phase |
| OP0008 | excluded | 5.2 Incubation with 1% BSA in PBS for blocking (Temperature: RT, Time: 1 hour)    | — | saved explicit excluded phase |
| OP0009 | excluded | 5.3 Incubation with primary antibody: anti-MAP2 (1:500 dilution in 1% BSA/PBS) (Temperature: 4 °C, Time: 48 hours)    | — | saved explicit excluded phase |
| OP0010 | excluded | 5.4 Incubation with secondary antibody: Alexa Fluor 488-conjugated anti-IgG (1:1000 dilution in 1% BSA/PBS) (Temperature: RT, | — | saved explicit excluded phase |
| OP0011 | excluded | 5.5 Incubation with PBS for washing (Temperature: RT, Time: 3 × 1 hour)  | — | saved explicit excluded phase |
| OP0012 | core | 6.1 Incubation with CUBIC-R (50 mM NaCl, 100 mM choline chloride, 0.2% wt/vol BSA in PBS) (Temperature: RT, Time: 24 hours)  | [24.0, 24.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP0013 | excluded | 7.1 Store in CUBIC-R at 4 °C for long-term preservation or proceed to imaging    | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
