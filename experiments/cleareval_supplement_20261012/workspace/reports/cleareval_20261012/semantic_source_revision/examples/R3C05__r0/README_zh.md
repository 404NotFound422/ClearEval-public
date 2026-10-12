# R3C05__r0 全流程

生成模型：openai_claude-sonnet-4.6；题目：23。

[题干](question.txt) → [原答案](original_answer.txt) → [规范化视图](canonical_answer.txt) → [存档评价器返回](archived_judge_response.json) → [来源分解、取值及全部分支](full_flow.json)。

| Com | Cor | Eff | IA | HV |
|---|---|---|---|---|
| 1 | 0.875 | NA | NA | NA |

| 来源解释/分支 | 小时 | Eff | HV |
|---|---|---|---|
| finite_range__extra_0__with_preimaging | 14 | 0.551447023 | 0.482516145 |
| finite_range__extra_0__initial_RI_ready | 13.5 | 0.583568196 | 0.510622171 |
| finite_range__extra_1__with_preimaging | 18 | 0.54046279 | 0.472904941 |
| finite_range__extra_1__initial_RI_ready | 17.5 | 0.54046279 | 0.472904941 |
| overnight_default__extra_0__with_preimaging | 17 | 0.54046279 | 0.472904942 |
| overnight_default__extra_0__initial_RI_ready | 16.5 | 0.540462823 | 0.47290497 |
| overnight_default__extra_1__with_preimaging | 21 | 0.54046279 | 0.472904941 |
| overnight_default__extra_1__initial_RI_ready | 20.5 | 0.54046279 | 0.472904941 |

作者辅助分解不计作独立评价器调用或专家回执；旧直接评分、原 SR/SP 和数值公式保留。
