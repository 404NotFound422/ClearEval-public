# R3C02__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01/run/attempts/694051b84d0e328fb1bb6b0a752327c3a79380d0fa5f02802033b2d6c309f4ac_1/processing.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **NA h**；`candidate_point_applied=False`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 34.5 | 3 | 0.776599 | 0.733333 | 0.498318 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 3 |
| co_method | 2 |
| co_param | 1 |
| co_chem | 1 |
| s_method | 0.8409 |
| s_label | 3 |
| s_trans | 2.814647 |
| s_time | NA |
| sr | 0.333333 |
| sp | 0.138889 |
| Com | 0.733333 |
| Cor | 0.875 |
| Eff | NA |
| IA | NA |
| HV | NA |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP001 | core | 1.1 Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP002 | core | 1.2 Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP003 | core | 1.3 Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP004 | core | 1.4 Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP005 | core | 1.5 Incubation with 100% methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP006 | core | 1.6 Incubation with 100% methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP007 | core | 2.1 Incubation with chilled fresh 5% (vol/vol) H₂O₂ in methanol (1 volume 30% H₂O₂ + 5 volumes methanol).(Temperature: 4 ℃, T | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP008 | core | 3.1 Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP009 | core | 3.2 Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP010 | core | 3.3 Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP011 | core | 3.4 Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP012 | core | 3.5 Incubation with PBS + 0.2% (vol/vol) Triton X-100 (PBST).(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP013 | excluded | 4.1 Incubation with PBST + 20% (vol/vol) DMSO + 0.3 M glycine.(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| OP014 | excluded | 4.2 Incubation with PBST + 10% (vol/vol) DMSO + 6% (wt/vol) donkey serum.(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| OP015 | excluded | 5.1 Incubation with primary antibodies diluted in PBST + 5% (vol/vol) DMSO + 3% (wt/vol) donkey serum: anti-c-Fos (rabbit, 1: | — | saved explicit excluded phase |
| OP016 | excluded | 6.1 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP017 | excluded | 6.2 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP018 | excluded | 6.3 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP019 | excluded | 7.1 Incubation with species-specific secondary antibodies conjugated to Alexa Fluor dyes (e.g., anti-rabbit Alexa Fluor 488 f | — | saved explicit excluded phase |
| OP020 | excluded | 8.1 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP021 | excluded | 8.2 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP022 | excluded | 8.3 Incubation with PBST.(Temperature: 37 ℃, Time: 24 hours)  | — | source labeling/preparation heading |
| OP023 | core | 9.1 Incubation with 20% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP024 | core | 9.2 Incubation with 40% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP025 | core | 9.3 Incubation with 60% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP026 | core | 9.4 Incubation with 80% (vol/vol) methanol in PBS.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP027 | core | 9.5 Incubation with 100% methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP028 | core | 9.6 Incubation with 100% methanol.(Temperature: RT, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP029 | core | 10.1 Incubation with 1:2 (vol/vol) dichloromethane (DCM) : methanol.(Temperature: RT, Time: 30 minutes)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP030 | core | 10.2 Incubation with 100% DCM.(Temperature: RT, Time: 30 minutes)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP031 | core | 10.3 Incubation with 100% DCM.(Temperature: RT, Time: 30 minutes)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP032 | core | 11.1 Incubation with 100% (vol/vol) dibenzyl ether (DBE, Sigma 108014-1KG).(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP033 | core | 11.2 Incubation with fresh 100% DBE.(Temperature: RT, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP034 | core | 12.1 Prior to final DBE step, rehydrate briefly through methanol series to 80% methanol, then incubate with DAPI (1 µg/mL in  | — | one saved labeling record also contains an explicit core reagent transition; its duration must be separated |
| OP035 | core | 12.2 Re-dehydrate through methanol series (80% → 100%) and repeat steps 10.1–11.2.  | — | saved core phase, reconciled with explicit source heading |
| OP036 | core | 12.2 Re-dehydrate through methanol series (80% → 100%) and repeat steps 10.1–11.2.  | — | saved core phase, reconciled with explicit source heading |
| OP037 | excluded | 13.1 Mount cleared brain in glass-bottom dish or custom chamber filled with DBE for light-sheet or confocal microscopy.(Tempe | — | saved explicit excluded phase |

未决项：`[{"kind": "combined_labeling_and_core_transition_duration_unreported", "operation_id": "OP034"}, {"kind": "missing_or_unbound_operation_duration", "operation_id": "OP035"}, {"kind": "missing_or_unbound_operation_duration", "operation_id": "OP036"}]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
