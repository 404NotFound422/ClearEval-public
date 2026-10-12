**按用户澄清修正标签语义与 CCE 分工**

2026-10-12。本次核对了 Git HEAD `ea9975260ef3b42eecb61239bb17c78250e60af3`、初始提交 `025f43f` 的原 prompt、当前工作区差异，以及原标签评分代码。下面修正上一份诊断中解释过宽的地方；没有重新评分，没有新增模型调用。

**1．MAP2 是靶标，AF488 是荧光团；一抗应称 anti-MAP2。**

`MAP2+Alexa Fluor 488` 表示靶标—荧光读出组合，仅凭这个简写不能唯一判断荧光团偶联在一抗还是二抗上。直接偶联 AF488 的 anti-MAP2 一抗确实存在，见 [Abcam ab225316](https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-488-map2-antibody-epr19691-neuronal-marker-ab225316)。

对前面举的 FPC13，正文已经分别写了 anti-MAP2 一抗和 AF488-conjugated anti-IgG 二抗，所以该答案采用的是间接免疫标记的表述。无论直接还是间接标记，在原框架要求的抽取粒度上都可表示为：

```json
{"Alexa Fluor 488": "MAP2"}
```

原 prompt 3.1 明确说明，字典用于拆分靶点和荧光团，没有要求以完整抗体宿主、克隆和二抗特异性信息作为这条关系的成立前提。因此，FPC13 的已声明 MAP2–AF488 关系不应仅因二抗被另一个实体分类器标成 unknown 而丢失标签分。真实的一抗/二抗矛盾可以单独审查；未报告全部试剂细节不能自动等同于存在矛盾。

**2．原生 GFP 本身就是荧光蛋白，无需补一个外部 marker。**

`{"GFP": ""}` 可以是正常、完整的原生荧光表示。这里空 marker 表示不涉及外加的靶标—染料偶联关系，不是抽取失败。应保留原生信号类型及方法对 GFP 的兼容评价；只有答案确实采用 anti-GFP 扩增时，才增加抗体标记路线。

代码核对还发现：Git HEAD 原函数跳过空 marker 的抗体配伍计算，但把空目标集合默认设为 0；后来的 nullable 改造则把它变为 None。两种写法都没有明确表达原生荧光的通道适用性。不能把“旧版得到 0、新版得到 NA”解释为原生 GFP 不满足标记条件。

修订方向是把不适用的抗体配伍通道排除出该类型的聚合。题目目标是否由 GFP 标记的细胞或结构覆盖，可依据题干和答案已声明的标记对象评价，不应强制捏造 GFP→GFP 关系来让函数运行。

**3．采纳 AF 系列近似作为明确的判断规则，并优先使用已有具体记录。**

用户允许 AF594 参考 AF 系列作近似判断。该近似应记录为作者声明的家族规则，用于通用抗体—荧光标记配伍判断，并保留 AF594 原名称。已有具体染料或方法记录时优先使用具体记录；已知的不兼容记录不能被家族近似覆盖。

当前 MAP2–AF594 案例已有比近似更直接的材料：[Abcam ab302832](https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-594-map2-antibody-epr19691-neuronal-marker-ab302832)就是 AF594 偶联的 anti-MAP2 一抗。这支持该靶标的 AF594 标记组合可以存在，不等于证明任意克隆、样本和透明条件下的效果。

仓库的 `method_fluro_compati.json` 也已列出 AF594，17 个方法均有相应单元格。例如既存表中的 FDISCO–AF594 为 0.85。缺口发生在另一张组织/标志物表没有 594 列，不能扩大成“整个评分器没有 AF594 知识”。上述数值是已有知识表值，本轮没有重新验证它的原始实验来源。

[Thermo Fisher 的 AF 系列说明](https://www.thermofisher.com/us/en/home/references/molecular-probes-the-handbook/fluorophores-and-their-amine-reactive-derivatives/alexa-fluor-dyes-spanning-the-visible-and-infrared-spectrum.html)支持这些染料用于蛋白偶联，同时列出各成员不同的光谱和荧光性质。因此，通用配伍可以使用声明的家族近似，具体透明方法下的保留数值仍优先用该染料已有记录，不能将所有 AF 数值强制设成相同。

**4．LLM 负责按量表审查并提取，EGES 负责有效性的数值计算。**

核对发现，原 prompt 本身包含 `co_order`、`co_method`、`co_param`、`co_chem` 四项，并非只检查 JSON 格式。其中原始 `co_param` 确实有“偏差在 50% 以内”的文字。这里存在参数合理性与数值有效性之间的职责重叠，需要明确，而不能声称原稿没有该条款。

用户本次明确的分工应落实为：

| 模块 | 负责判断 | 不应额外要求 |
|---|---|---|
| LLM 完整性审查 | 必需信息、参数是否写明、表达是否可执行 | 对每个已写出的数值证明实验最优 |
| LLM Correctness | 流程逻辑、方法—试剂一致性、明显不合理参数及安全常识 | 对整个方案给出长期信号/形态保持的湿实验成功证明 |
| LLM 提取 | 方法、荧光—靶标、时间与其他实际输入，保存取值依据 | 用精确型号/文献逐项一致作为所有关系可提取的前提 |
| EGES | 方法适配、标记兼容、RI 参考匹配和时间适配的数值计算 | 把缺少一个附加语义标签传播成所有已知分项不可用 |

Cor 的四项和汇总公式可以保留，按用户澄清限定为结构、逻辑和常识审查。原 prompt 中 50% 的定量落档条款需要在后续修订中明确改写或归位，避免同时要求“只作常识审查”与“必须按精确参考计算偏差”。这项职责调整应说明版本，不应把旧 null 直接填成某个分数。

**关于之前“为什么突然缺分”的进一步更正**

Git 原版及初始提交均没有 `[UNCERTAINTY CONTRACT]`；当前工作区的 prompt 增加了这一整段，要求证据不足时直接判项及依赖汇总均为 null。[保存的差异](original_scope_evidence/current_prompt_diff.txt)可直接查看。

原版标签函数还明确写了“兼容或未知均给满分（未知时不应 penalize）”，当前版本将部分未知改成 NA，并叠加了关系发布限制。**因此这次新增的证据要求、适用性处理和缺值传播规则，是必须审查的原因；不能把所有缺分都归咎于原框架或模型能力。**

这些代码差异能够说明判分约束发生了变化，但尚未通过同输入的 prompt 对照证明 11 份 Cor 缺项各有多少由新增约束造成。前面的“原始返回确实为 null”仍成立；“所以模型本身无法判分”不成立。

本次落实的是诊断与后续规则的修正，原 10/67 仍是上一配置的记录，不是按这四点重新评分后的结果。下一轮实现应按这些职责逐项修复，再对同一批来源做一致回放，报告真实变化。

**本次证据与实际命令**

[Git 原 prompt 快照](original_scope_evidence/original_prompt_HEAD.txt) · [原版/现版与 AF594 表值证据](original_scope_evidence/evidence.json) · [核对脚本](audit_original_scope.py)。

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\missing_score_diagnosis\audit_original_scope.py'
```
