# R3C05__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01/run/attempts/f0b0e2eb7fece9c21556c0926cded22c36952b36758b8bff4cd711eae7c2d14e_1/processing.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **NA h**；`candidate_point_applied=False`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 14 | 0.131811 | 0.551447 | 0.551447 | 0.482516 |
| S001 | 17 | 9.8811e-09 | 0.540463 | 0.540463 | 0.472905 |
| S002 | 18 | 1.8306e-12 | 0.540463 | 0.540463 | 0.472905 |
| S003 | 21 | 9.8724e-28 | 0.540463 | 0.540463 | 0.472905 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 3 |
| co_method | 2 |
| co_param | 1 |
| co_chem | 1 |
| s_method | -0.45 |
| s_label | 5.1 |
| s_trans | 2.705553 |
| s_time | NA |
| sr | 1 |
| sp | 0.275862 |
| Com | 1 |
| Cor | 0.875 |
| Eff | NA |
| IA | NA |
| HV | NA |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP001 | excluded | 1.1 Wash fixed 3 mm brain blocks (post-fixed in 4% PFA) 3× with 1× PBS. (Temperature: RT, Time: 10 min per wash)  | — | saved explicit excluded phase |
| OP002 | excluded | 1.2 Permeabilization and blocking: incubate tissue in blocking/permeabilization buffer [0.5% (vol/vol) Triton X-100, 10% (vol | — | saved explicit excluded phase |
| OP003 | excluded | 1.3 Primary antibody incubation: incubate with anti-MAP2 rabbit polyclonal antibody [1:500 dilution in antibody diluent: 0.5% | — | saved explicit excluded phase |
| OP004 | excluded | 1.4 Wash 5× with 1× PBS containing 0.1% (vol/vol) Tween-20 (PBST). (Temperature: RT, Time: 1 hour per wash)  | — | saved explicit excluded phase |
| OP005 | excluded | 1.5 Secondary antibody incubation: incubate with donkey anti-rabbit Alexa Fluor 647-conjugated secondary antibody [1:500 dilu | — | saved explicit excluded phase |
| OP006 | excluded | 1.6 Wash 5× with PBST. (Temperature: RT, Time: 1 hour per wash)  | — | saved explicit excluded phase |
| OP007 | excluded | 1.7 Post-immunostaining fixation: incubate in 4% (wt/vol) PFA in 1× PBS to crosslink antibodies in place. (Temperature: RT, T | — | saved explicit excluded phase |
| OP008 | excluded | 1.8 Wash 3× with 1× PBS. (Temperature: RT, Time: 10 min per wash)  | — | saved explicit excluded phase |
| OP009 | core | 2.1 Incubation with 30% (vol/vol) tetrahydrofuran (THF) in ddH₂O (freshly prepared, stabilizer-free THF). (Temperature: 4 °C, | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP010 | core | 2.2 Incubation with 50% (vol/vol) THF in ddH₂O. (Temperature: 4 °C, Time: 1 hour, with gentle shaking)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP011 | core | 2.3 Incubation with 70% (vol/vol) THF in ddH₂O. (Temperature: 4 °C, Time: 1 hour, with gentle shaking)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP012 | core | 2.4 Incubation with 80% (vol/vol) THF in ddH₂O. (Temperature: 4 °C, Time: 1 hour, with gentle shaking)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP013 | core | 2.5 Incubation with 100% (vol/vol) THF (anhydrous). (Temperature: 4 °C, Time: 1 hour, with gentle shaking)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP014 | core | 2.6 Repeat incubation with fresh 100% (vol/vol) THF (anhydrous). (Temperature: 4 °C, Time: 1 hour, with gentle shaking)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP015 | core | 3.1 Incubation with dichloromethane (DCM, 100%, anhydrous) for delipidation. (Temperature: 4 °C, Time: 30 min, with gentle sh | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP016 | untimed_handling | 3.2 Remove DCM completely by aspiration; do not allow tissue to dry.  | — | explicit handling without an incubation or equilibration duration; elapsed handling time not estimated |
| OP017 | core | 4.1 Incubation with dibenzyl ether (DBE, 100%, Sigma-Aldrich 108014) — first exchange. (Temperature: 4 °C, Time: 2 hours, wit | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP018 | core | 4.2 Incubation with fresh DBE (100%) — second exchange until tissue is fully transparent. (Temperature: 4 °C, Time: 4–6 hours | [4.0, 6.0] × 1；[8, 8] × 1 | saved core phase, reconciled with explicit source heading |
| OP019 | core | 4.3 Verify optical transparency visually; tissue should appear fully clear. If residual opacity remains, replace with fresh D | [4.0, 4.0] × 1 | saved core phase, reconciled with explicit source heading |
| OP020 | excluded | 5.1 Transfer cleared tissue to a sealed glass vial filled with fresh 100% DBE (RI = 1.56). Ensure complete submersion and abs | — | saved explicit excluded phase |
| OP021 | excluded | 5.2 Label vials with sample ID, clearing date, and antibody/fluorophore information.  | — | saved explicit excluded phase |
| OP022 | excluded | Store upright in a light-tight container at 4 °C.  | — | saved explicit excluded phase |
| OP023 | excluded | 5.3 Inspect samples every 4–6 weeks for clarity and potential DBE evaporation; replenish DBE if volume decreases.  | — | saved explicit excluded phase |
| OP024 | core | 6.1 Remove sample from storage DBE; transfer to a fresh glass vial with 100% DBE for equilibration. (Temperature: RT, Time: 3 | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| OP025 | excluded | 6.2 Mount sample in a custom imaging chamber (e.g., FEP tube or glass-bottom dish) filled with 100% DBE (RI = 1.56) compatibl | — | saved explicit excluded phase |
| OP026 | excluded | 6.3 For light-sheet fluorescence microscopy (LSFM): use a long-working-distance objective corrected for RI = 1.56 (e.g., CLAR | — | saved explicit excluded phase |
| OP027 | excluded | 6.4 For confocal imaging: use an oil-immersion or RI-matched objective; apply a coverslip with DBE as mounting medium and sea | — | saved explicit excluded phase |
| OP028 | excluded | 6.5 After imaging, return sample to sealed glass vial with fresh DBE for continued storage at 4 °C if repeat imaging is plann | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
