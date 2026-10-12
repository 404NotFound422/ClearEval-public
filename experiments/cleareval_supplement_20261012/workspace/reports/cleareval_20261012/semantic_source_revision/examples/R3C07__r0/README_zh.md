# R3C07__r0 全流程

生成模型：openai_claude-sonnet-4.6；题目：248。

[题干](question.txt) → [原答案](original_answer.txt) → [规范化视图](canonical_answer.txt) → [存档评价器返回](archived_judge_response.json) → [来源分解、取值及全部分支](full_flow.json)。

| Com | Cor | Eff | IA | HV |
|---|---|---|---|---|
| 0.6 | 0.541666667 | 0.584177176 | 0.541666667 | 0.189857582 |

单值解释：`explicit_setpoint`。

| 来源解释/分支 | 小时 | Eff | HV |
|---|---|---|---|
| explicit_setpoint | 8.5 | 0.584177176 | 0.189857582 |
| typical_range_sensitivity | 8.25 | 0.58390622 | 0.189769522 |

作者辅助分解不计作独立评价器调用或专家回执；旧直接评分、原 SR/SP 和数值公式保留。
