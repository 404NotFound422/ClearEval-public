# FPC16：从原文到分数

[题目](question.txt) → [原提交全文](submitted_answer.txt) → [实际提取来源](scoring_source.txt) → [逐条关系、原文位置和查表记录](evidence.json)。

本例的处理决定为 `source_rule_applied`。原 LLM 返回保存在 [post_record](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/uniform_v7/actual_01/cells/secondary8_posthoc/FPC16/posthoc.json)；它的直接分数和原 SR/SP 均沿用。候选只从全文所选列表提取标签关系，调用原 EGES 分通道函数，再用原公式聚合；未重新请求模型。

| 染料或信号 | 靶标/角色 | 来源解释 |
|---|---|---|
| tdTomato | 不需要外部 marker | explicit standalone signal in chosen list; external target-pair channel not applicable |
| DiI | 不需要外部 marker | explicit standalone signal in chosen list; external target-pair channel not applicable |

| 分项 | 实际候选值 |
|---|---:|
| c_param | 3 |
| co_order | 2 |
| co_method | 1 |
| co_param | 1 |
| co_chem | 1 |
| s_method | -0.4313 |
| s_label | 1.2 |
| s_trans | 2.814647 |
| s_time | 0 |
| sr | 0.111111 |
| sp | 0.117647 |
| Com | 0.644444 |
| Cor | 0.666667 |
| Eff | 0.387989 |
| IA | 0.387989 |
| HV | 0.166692 |

缺项、候选不适用原因和每个来源区间均见 evidence.json。NA 没有改成 0；FPC08 的 0 来自原靶标匹配函数的实际输出。完整数值结果与科学有效性分别判断，旧 LLM Correctness 也不代表本轮认可其理由。
