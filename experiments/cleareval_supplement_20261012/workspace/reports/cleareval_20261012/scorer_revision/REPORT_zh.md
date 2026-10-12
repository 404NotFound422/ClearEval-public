# 评分器修订与结论更正

2026-10-12。完整评分器在工程上可以修复；本轮已实现通用的离线评分入口，并处理全部 67 份存档返回。现有证据支持修正“缺分意味着模型不能分解或框架无法评分”的判断，也支持保留一个明确界限：两例成功不代表全体答案已经可以全自动完整评分。

## 1. 本轮真实结果

固定采用既有 `uniform_v7/actual_01/cells.json` 的全部 68 个位置，其中 67 个有返回、1 个取消且没有返回。65 份有完整的结构化数值输入，完成原函数重新计算；另 2 份只有局部输入，保留其实际已知分数并记录缺口。新增模型调用 0、专家记录 0。

| 同一批记录上的设置 | 完整单值 CCE | 原完整结果丢失数 | 变化来源 |
|---|---:|---:|---|
| 既有 v7 | 8/67 | — | 本轮逐记录核对的基线 |
| 通用查表范围＋时间中点规则 | 9/67 | 0 | FPC03 获得标签分；FPC07 获得时间分 |
| 上述规则＋前次两份原文重新分解 | 10/67 | 0 | FPC07 的标记关系获得来源明确的投影 |

这里“完整”要求 Com、Cor、Eff、IA、HV 全部有数值。仅 Eff 有值的记录未计入完整 CCE。67 是存档评价返回数，包含同一答案的重复评价和受控变体，不能当成 67 个独立自然答案。

FPC03 的完整分数为 `(Com, Cor, Eff) = (0.4444, 0.5833, 0.3451)`；FPC07 为 `(0.7778, 0.6667, 0.2423)`。新通用入口与前次逐例复算完全一致。原来完整的 8 份，其全部分数字段均逐值保持一致。

[仅规则结果](rules_only/summary.json) · [接入重新分解后的结果](with_decomposition/summary.json) · [逐答案 CSV](with_decomposition/per_answer.csv) · [逐条完整记录](with_decomposition/results.json)。

## 2. 哪些结论必须修正

| 原先过宽的解释 | 目前证据支持的解释 |
|---|---|
| 标签 NA 就是知识库没有兼容知识 | 应先区分索引覆盖、适用范围选择、别名/列映射、真实无记录；FPC03 是已有记录未被正确使用 |
| 这些答案无法获得完整 CCE | 两份示例在明确的取值规则下已经获得完整单值 CCE；旧入口的失败不能推广为不可评分 |
| 模型无法分解出所需信息 | 当前会话模型能完成两份有原文依据的分解；通用评分入口能接收并复算这些分解 |
| 时间有范围就只能 NA | 对明确有限范围可以采用统一的中点约定，并保存端点敏感性；未给上界或操作缺时长仍需另外处理 |
| 两例跑通意味着评分器全部修好 | 本轮全批次回放仅从 8/67 到 10/67，广泛自动覆盖仍不足 |

原有稳定性分析也要按实际配置解释。此次离线重算确认的是输入、规则和数值计算的一致性；没有新增独立模型请求，不能据此声称模型重复评价稳定性提高。

## 3. 根因需要再精确一层

原始 `OEQ_run_grading_new.py` 的单键索引确实让后面的 MAP2 / CA1 null 覆盖了通用神经元行的 1。但当前 v7 还加了一层 `cce_target_catalog_role_fix_v2.py`：它已保存多条原记录，却要求题目列出的所有候选范围都具有兼容值。

因此，对 q21，通用神经元行有 1、CA1 辅助行未知，v7 仍给 NA。完整修复包含两部分：保留多行记录；明确本任务所评价的适用范围。不能只说把字典覆盖问题改掉就修好了当前 v7。

本轮对 q21 的 MAP2 固定选择“中枢神经 / 神经元结构 / 神经元(通用)”，依据题干的稀疏脑神经元形态和树突目标及其登记参考路径。该配置对 q21 的所有模型、重复和变体一致应用，并保留其他候选行。它是开发阶段的任务解释，没有根据最终得分选最高行。

## 4. 已实现的通用评分入口

[评分器代码](../../../ClearEval-public/scripts/cce_scoped_midpoint_scorer_v1.py)接收存档评价记录、固定问题配置以及可选的来源明确的语义分解，执行以下过程：

1. 读取已保存的直接评分和原始 SR/SP，并核对记录哈希。
2. 复用已完成的全文解析；同一答案可接入独立保存的 LLM/作者重新分解，逐条核对原文引用与答案身份。
3. 对明确的完整有限时长范围取中点；输出总时长、计入操作、原范围和取值理由。
4. 按任务声明的组织范围查询全部知识记录；保留所选行、未选行、单元格和值来源。
5. 调用原 EGES 数值公式，保留原参数完整性和 Correctness 量表，计算 Com、Cor、Eff、IA/HV。
6. 输出逐答案 JSON/CSV、时间敏感性及未决分项的具体原因。

数值逻辑中没有 FPC03/FPC07 特判，题目范围放在[配置](config.json)，语义分解作为数据输入。ScaleS 的已有来源别名映射继续复用。新的入口使用版本独立的输出目录，原评价器和冻结历史结果仍可复现。

该入口已可用于有完整输入的评分和存档批量回放。新答案的模型生成、模型重新分解请求仍由既有调用层承担；本轮没有重新测试在线端到端调用，也没有增加 Qwen/Llama 请求。

## 5. 当前仍影响完整覆盖的问题

| 分项 | 67 份存档返回中的缺值数 | 含义 |
|---|---:|---|
| Com | 0 | 原步骤值和参数完整性均保留 |
| Cor | 11 | 参数正确性等直接分项仍有未决输入 |
| s_method | 0 | 方法适配可计算 |
| s_trans | 0 | RI 参考匹配可计算 |
| s_label | 56 | 当前最主要的缺分来源 |
| s_time | 6 | 仍有操作缺时长、阶段归属或分支未确定 |
| Eff | 56 | 受标签等缺项影响 |

标签缺值记录中，38 份仍带明确的未决关系记录，21 份存在知识查询/适用范围问题，9 份没有上述两类标记，主要是空的目标/marker 通道或仅存局部转换；这些类别有重叠，不能相加作为独立数量。

下一阶段应优先处理三类具体问题：

- **标记角色及适用性。** 原生荧光蛋白、直接染料、抗体—荧光团的关系结构不同。需要明确原标签三个通道何时适用，保存该判断依据；避免将“此关系不适用”与“缺少关系证据”混为一类。
- **语义分解的覆盖。** 将模型已能完成的来源分解接入统一流程，重点处理跨句共指、标记试剂与真实靶标的关系、时间阶段和重复次数。原文引用核对用于确认来源，不应冒充语义理解本身。
- **真实参考缺口及直接判分。** 列出缺少的具体波长列/适用记录，以及 11 份 Cor 缺项的原因；按统一规则处理，继续保留已知分数。

中点规则已经接入。其他问题需要各自的受控验证；不能用补零、补满分或只报告两例来证明它们已解决。

## 6. 验证与实际命令

五项针对性测试均通过：实际 MAP2 案例在知识行顺序反转后分数不变；时长中点先代入非线性公式；缺时长/可选分支不伪装为闭区间；修改原文引用不能复用旧分解；查询异常后恢复原函数。

[测试代码](../../../ClearEval-public/tests/test_cce_scoped_midpoint_scorer.py) · [批量产物核验](verification.json) · [核验脚本](verify_revision.py)。运行中发现并修正了两个接口问题：2 份局部记录没有完整 `numeric` 对象；ScaleS 需要继续接入已有别名适配。两项都没有通过清空其他分数处理。

以下命令均在 `C:\ClearEval\ClearEval-public` 下执行成功：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'scripts\cce_scoped_midpoint_scorer_v1.py' --cells 'artifacts\cce_validation\optimizer_round3_20261011\uniform_v7\actual_01\cells.json' --config 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\config.json' --out 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\rules_only'

& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'scripts\cce_scoped_midpoint_scorer_v1.py' --cells 'artifacts\cce_validation\optimizer_round3_20261011\uniform_v7\actual_01\cells.json' --config 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\config.json' --decompositions 'C:\ClearEval\reports\cleareval_20261012\llm_decomposition.json' --out 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\with_decomposition'

& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 -m unittest discover -s tests -p 'test_cce_scoped_midpoint_scorer.py' -v

& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\verify_revision.py'
```
