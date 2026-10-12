# FPC08：从原文到分数

[题目](question.txt) → [原提交全文](submitted_answer.txt) → [实际提取来源](scoring_source.txt) → [逐条关系、原文位置和查表记录](evidence.json)。

本例的处理决定为 `source_rule_applied`。原 LLM 返回保存在 [post_record](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011/uniform_v7/actual_01/cells/first7_posthoc/FPC08/posthoc.json)；它的直接分数和原 SR/SP 均沿用。候选只从全文所选列表提取标签关系，调用原 EGES 分通道函数，再用原公式聚合；未重新请求模型。

| 染料或信号 | 靶标/角色 | 来源解释 |
|---|---|---|
| Alexa Fluor 488 | GFP | explicit selected target + fluorophore; antibody carrier/clone not required |
| Alexa Fluor 568 | Phalloidin | explicit selected target + fluorophore; antibody carrier/clone not required |

| 分项 | 实际候选值 |
|---|---:|
| c_param | 3 |
| co_order | 2 |
| co_method | 2 |
| co_param | 2 |
| co_chem | 1 |
| s_method | 1.5278 |
| s_label | 0 |
| s_trans | 3 |
| s_time | 3.799e-14 |
| sr | 0.571429 |
| sp | 0.363636 |
| Com | 0.828571 |
| Cor | 0.916667 |
| Eff | 0.45139 |
| IA | 0.45139 |
| HV | 0.342841 |

缺项、候选不适用原因和每个来源区间均见 evidence.json。NA 没有改成 0；FPC08 的 0 来自原靶标匹配函数的实际输出。完整数值结果与科学有效性分别判断，旧 LLM Correctness 也不代表本轮认可其理由。
