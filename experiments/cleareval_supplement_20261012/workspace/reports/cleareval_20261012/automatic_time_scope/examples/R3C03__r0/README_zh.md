# R3C03__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01/run/attempts/63d649b2d794cd6acc214c4c902f3433adbbb057599a6c694cf6c333a1c3de8b_1/processing.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **NA h**；`candidate_point_applied=False`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|


5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 0 |
| co_order | NA |
| co_method | NA |
| co_param | NA |
| co_chem | 1 |
| s_method | 2.425 |
| s_label | 3 |
| s_trans | 1.233337 |
| s_time | NA |
| sr | 0 |
| sp | 0 |
| Com | 0 |
| Cor | NA |
| Eff | NA |
| IA | NA |
| HV | NA |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| OP01 | unknown | 1 Washing  | — | source does not resolve saved unknown phase |
| OP02 | unknown | 1.1 Incubation with  | — | source does not resolve saved unknown phase |

未决项：`[{"kind": "source_schedule_not_serial", "mode": "unknown"}, {"kind": "unknown_operation_scope", "operation_id": "OP01"}, {"kind": "unknown_operation_scope", "operation_id": "OP02"}, {"kind": "no_reported_core_incubations"}]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
