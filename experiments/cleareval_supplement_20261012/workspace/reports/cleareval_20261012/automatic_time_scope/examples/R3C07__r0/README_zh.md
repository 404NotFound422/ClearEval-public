# R3C07__r0：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录](C:/ClearEval/reports/cleareval_20261012/typed_label_transfer/lexical_candidate_02/processing/R3C07__r0.json)。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **8.5 h**；`candidate_point_applied=True`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
| S000 | 8.5 | 0.069699 | 0.584177 | 0.541667 | 0.189858 |

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
| c_param | 3 |
| co_order | 2 |
| co_method | 1 |
| co_param | 0 |
| co_chem | 1 |
| s_method | 0.1263 |
| s_label | 5.1 |
| s_trans | 2.814647 |
| s_time | 0.069699 |
| sr | 0 |
| sp | 0 |
| Com | 0.6 |
| Cor | 0.541667 |
| Eff | 0.584177 |
| IA | 0.541667 |
| HV | 0.189858 |

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
| O1 | excluded | 1.1 将已4% PFA固定的成年小鼠全脑置于1× PBS中充分漂洗，去除残余固定液。(Temperature: 4 ℃, Time: 3 × 1 hour)  | — | saved explicit excluded phase |
| O2 | excluded | 2.1 将脑组织置于含0.2% (vol/vol) Triton X-100的1× PBS（PBST）中振荡渗透。(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| O3 | excluded | 2.2 更换新鲜PBST继续渗透。(Temperature: 37 ℃, Time: 24 hours)  | — | saved explicit excluded phase |
| O4 | excluded | 3.1 将脑组织置于封闭液（5% (vol/vol) 正常驴血清 + 0.2% Triton X-100 + 0.1% (wt/vol) NaN₃ in 1× PBS）中振荡封闭。(Temperature: 37 ℃, Time: 24 hours) | — | saved explicit excluded phase |
| O5 | excluded | 4.1 将脑组织置于含抗β-III Tubulin（TUJ1）兔多克隆抗体（1:500稀释于封闭液）的溶液中，轻柔振荡孵育。(Temperature: 37 ℃, Time: 48 hours)  | — | saved explicit excluded phase |
| O6 | excluded | 4.2 用PBST洗涤，去除未结合一抗。(Temperature: RT, Time: 5 × 1 hour)  | — | saved explicit excluded phase |
| O7 | excluded | 5.1 将脑组织置于含驴抗兔 Alexa Fluor 647二抗（1:500稀释于封闭液）的溶液中，避光振荡孵育。(Temperature: 37 ℃, Time: 48 hours)  | — | saved explicit excluded phase |
| O8 | excluded | 5.2 用PBST洗涤，去除未结合二抗。(Temperature: RT, Time: 5 × 1 hour)  | — | saved explicit excluded phase |
| O9 | excluded | 5.3 用1× PBS终洗。(Temperature: RT, Time: 2 × 30 min)  | — | saved explicit excluded phase |
| O10 | core | 6.1 将脑组织置于50% (vol/vol) THF（四氢呋喃）水溶液（用NaOH调pH至9–10，以保护荧光蛋白）中振荡脱水。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O11 | core | 6.2 将脑组织置于70% (vol/vol) THF水溶液（pH 9–10）中振荡脱水。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O12 | core | 6.3 将脑组织置于80% (vol/vol) THF水溶液（pH 9–10）中振荡脱水。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O13 | core | 6.4 将脑组织置于100% THF（无水，pH 9–10，加少量NaOH）中振荡脱水，第一次。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O14 | core | 6.5 将脑组织置于100% THF（无水，pH 9–10）中振荡脱水，第二次（更换新鲜THF）。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O15 | core | 7.1 将脑组织置于BABB（苯甲醇:苯甲酸苄酯 = 1:2, vol/vol）中振荡，完成脱脂并开始RI匹配，直至组织完全透明（通常30–60 min）。(Temperature: 4 ℃, Time: 1 hour)  | [1.0, 1.0] × 1 | saved core phase, reconciled with explicit source heading |
| O16 | core | 8.1 将透明脑组织转移至新鲜BABB（RI ≈ 1.56）中，避光静置平衡，确保组织完全透明且无气泡。(Temperature: 4 ℃, Time: 2 hours)  | [2.0, 2.0] × 1 | saved core phase, reconciled with explicit source heading |
| O17 | core | 8.2 再次更换新鲜BABB，确认组织完全透明，准备成像。(Temperature: 4 ℃, Time: 30 min)  | [0.5, 0.5] × 1 | saved core phase, reconciled with explicit source heading |
| O18 | excluded | 9.1 将透明脑组织转移至适配光片显微镜样品槽的BABB中，使用折射率匹配的浸没介质（RI = 1.56）固定样品位置，避免气泡。(Temperature: RT, Time: 即刻成像)  | — | saved explicit excluded phase |
| O19 | excluded | 9.2 若需短期保存，将样品密封于BABB中，避光、4 ℃保存（建议1周内完成成像，以防荧光信号衰减）。(Temperature: 4 ℃, Time: ≤ 7 days)  | — | saved explicit excluded phase |

未决项：`[]`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
