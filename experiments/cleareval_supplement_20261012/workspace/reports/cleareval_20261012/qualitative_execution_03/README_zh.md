# 五份开发答案的定性 Correctness 成对验证

状态：请求、执行入口和分析入口已准备；实际请求 0/10，实际配对 0/5。历史 438 次额度已用尽，上一授权窗口已经结束。本包尚无新授权。

目标是实测用户明确的职责划分：LLM 审查结构、顺序、方法与试剂逻辑以及常识性物理/化学问题；EGES 负责原有数值有效性。保存每个分项的来源、判断理由和原始返回，判断缺分是否减少以及理由是否遵循约定。分数升高不是成功条件。

| 项目 | 安排 |
|---|---|
| 真实答案 | 已使用的 A01–A05，题目 q2、q21、q22、q23、q248；不是新留出样本 |
| C0 | 原规范化全文评分 prompt |
| C1 | 同一全文、参考和结构，替换不确定性要求与 co_param 判项，删除原数值偏差对齐指令，加入标签职责说明 |
| 调用 | 每答案每条件一次，共 10 次；固定随机顺序并相邻执行同答案的两个条件；不自动重试 |
| 模型 | 本地别名 qwen3.8:27b-q8_0-local；服务元数据 family=qwen35、27.3B、Q8_0；不将别名称作已核实的公开版本 |
| 环境 | 服务 0.40.3；与历史准备时 0.40.1 的差异已记录，模型和生成设置逐项相同；本次两个条件同时使用新环境 |
| 预算提案 | 新增最多 10 次、2 小时；全包上限 438→448；先达到者停止；只覆盖本次五组 |
| 保留 | 原 SR/SP、四项 Cor 量表及聚合、EGES 数值公式、原始返回和既有结果；人工仍为一位专家 5＋15 |

C1 同时调整 Correctness 职责与标签说明，因此这是**成套 prompt 修订**的效果验证，不能把所有变化单独归因于 co_param。一条件仅一次也不能用来证明评价器随机稳定性提高。

评价将分别报告：技术返回/结构转换、五个直接分项可用率、理由是否仍以文献时长偏差重复判分、标签与时间提取、完整 CCE、同答案差值。若可用率提高但来源理由不成立，仍判作待修复。没有实际输出时不预填成功结果。

准备核查已通过：10 份请求、5 个配对的来源/步骤/结构/模型设置相同，只有声明的 prompt 修改；当前模型元数据一致。缺少本次授权时，执行入口在生成请求之前终止，账本哈希未变。一次准备错误（旧评分器相对路径）及一次预检差异（服务更新）分别保留在相邻的 qualitative_execution_01 和 02 中。

可审查材料：[计划](plan.json)、[配对表](pairs.json)、[请求矩阵](matrix.json)、[冻结文件清单](freeze.json)、[当前环境](runtime_preflight.json)、[未授权不调用检查](authorization_guard_check.json)。现有详细逐答案 prompt 差异位于 [A01](../typed_label_transfer/qualitative_canonical_pending/A01/prompt.diff)、[A02](../typed_label_transfer/qualitative_canonical_pending/A02/prompt.diff)、[A03](../typed_label_transfer/qualitative_canonical_pending/A03/prompt.diff)、[A04](../typed_label_transfer/qualitative_canonical_pending/A04/prompt.diff)、[A05](../typed_label_transfer/qualitative_canonical_pending/A05/prompt.diff)。

实际已执行 prepare、preflight 和缺授权检查；analysis 只统计实际文件，不触发调用。授权后的运行命令尚未执行：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\ClearEval-public\scripts\cce_qualitative_pair_runner_v1.py' run --out 'C:\ClearEval\reports\cleareval_20261012\qualitative_execution_03' --max-new-calls 10
```

执行入口只读取据实记录的用户授权，不自行延长截止时间或增加调用次数。
