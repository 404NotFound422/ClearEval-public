# R3C01__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/reports/cleareval_20261012/typed_label_transfer/lexical_candidate_02/processing/R3C01__r0.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **34.5 h**；`candidate_point_applied=True`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 34.5 | 3 | 0.814099 | 0.733333 | 0.447754 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 3 |
| co_method | 2 |
| co_param | 0 |
| co_chem | 1 |
| s_method | 0.8409 |
| s_label | 3.9 |
| s_trans | 2.814647 |
| s_time | 3 |
| sr | 0.333333 |
| sp | 0.16 |
| Com | 0.733333 |
| Cor | 0.75 |
| Eff | 0.814099 |
| IA | 0.733333 |
| HV | 0.447754 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP001 | core | Incubation with 20% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP002 | core | Incubation with 40% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP003 | core | Incubation with 60% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP004 | core | Incubation with 80% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP005 | core | Incubation with 100% (vol/vol) methanol for 1 hour, repeat twice.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 3 | saved core phase, reconciled with explicit source heading |
| OP006 | core | Incubation with chilled fresh 5% H2O2 in methanol (1 volume 30% H2O2 to 5 volumes MeOH) overnight.(Temperature: 4 ℃, Time: 12 | [12.0, 12.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP007 | core | Incubation with 80% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP008 | core | Incubation with 60% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP009 | core | Incubation with 40% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP010 | core | Incubation with 20% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP011 | core | Incubation with PBS (Phosphate Buffered Saline) for 1 hour, repeat twice.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 3 | saved core phase, reconciled with explicit source heading |
| OP012 | excluded | Incubation with 0.2% Triton X-100, 20% DMSO, 0.3M Glycine in PBS for 24 hours.(Temperature: RT, Time: 24 hours)  | — | saved explicit excluded phase |
| OP013 | excluded | Incubation with 0.2% Triton X-100, 10% DMSO, 6% Normal Donkey Serum in PBS for 24 hours.(Temperature: RT, Time: 24 hours)  | — | saved explicit excluded phase |
| OP014 | excluded | Incubation with Rabbit anti-c-Fos antibody (1:1000) in PTwH (0.2% Tween-20, 10 mg/ml Heparin, 0.1% Sodium Azide in PBS) with  | — | saved explicit excluded phase |
| OP015 | excluded | Wash with PTwH for 1 day, changing solution at least 3 times.(Temperature: RT, Time: 24 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP016 | excluded | Incubation with Donkey anti-Rabbit Alexa Fluor 647 (1:500) in PTwH with 3% Normal Donkey Serum for 7-14 days with gentle shak | — | saved explicit excluded phase |
| OP017 | excluded | Wash with PTwH for 1 day, changing solution at least 3 times.(Temperature: RT, Time: 24 hours)  | — | wash section within explicit antibody/labeling sequence, including repeat-only records |
| OP018 | excluded | Incubation with DAPI (1 µg/ml) in PTwH for 2 days.(Temperature: RT, Time: 48 hours)  | — | saved explicit excluded phase |
| OP019 | core | Incubation with 20% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP020 | core | Incubation with 40% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP021 | core | Incubation with 60% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP022 | core | Incubation with 80% (vol/vol) methanol in distilled water for 1 hour.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP023 | core | Incubation with 100% (vol/vol) methanol for 1 hour, repeat twice.(Temperature: RT, Time: 1 hours)  | [1.0, 1.0] × 3 | saved core phase, reconciled with explicit source heading |
| OP024 | core | Incubation with Dichloromethane (DCM) for 30 minutes to clear until tissue is transparent, repeat once with fresh DCM.(Temper | [0.5, 0.5] × 2 | saved core phase, reconciled with explicit source heading |
| OP025 | core | Incubation with 100% (vol/vol) Dibenzyl Ether (DBE) until the tissue sinks and is fully transparent (approx. 15-30 minutes).  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP026 | excluded | Store in DBE for imaging.(Temperature: RT, Time: 0.5 hours)  | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
