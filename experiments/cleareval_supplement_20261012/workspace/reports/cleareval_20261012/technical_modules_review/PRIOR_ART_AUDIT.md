# 最近似工作检查：哪些可以借用，哪些需要重新验证

2026-10-12。读取论文方法与公开源码，未安装、训练或运行外部模型。

## Thoth / SCORE 的身份与阅读范围

ICLR 2026 正式会议页面确认已发表：[会议记录](https://proceedings.iclr.cc/paper_files/paper/2026/hash/7721f1fea280e9ffae528dc78c732576-Abstract-Conference.html)。方法细节读取的是 [arXiv v1](https://arxiv.org/html/2510.15600v1) 的 §3.2–3.3、附录 C/F；会议 PDF 的访问未成功，不能声称逐字比较过终版与 v1。代码读取 [公开 main 分支 eval/eval_batch.py](https://raw.githubusercontent.com/manglu097/Thoth/main/eval/eval_batch.py)，为访问当日版本，未固定远端 commit。

论文的原子动作、对象、参数表示和结构化顺序/语义评价，是 ClearEval 必须对照的近似技术。奖励阶段包含格式与内容一致性门槛；附录评价又区分步骤数、顺序和语义分项。不能把奖励门槛概括成“所有独立评价分项都按同一门槛清零”。

## 公开评价代码的三个具体边界

1. **异常与科学错误混合。** `compute_structured_metrics` 的异常分支返回整组 0。ClearEval 应保留技术失败状态与已知分项，不能直接移植这段异常处理。
2. **动作锚点缺少阶段身份。** `pair_by_action_sequence` 对相同动作作贪心顺序匹配。它避免同一参考位置反复被匹配，却不自动解释重复操作的对象与阶段，也不能替代自由文本的来源提取。
3. **Tau 需要额外诊断。** 该函数生成的匹配对中参考索引严格递增，`_kendall_tau_from_pairs` 又只对这些保留的索引计算。因此只要保留至少两对，Tau 就为 1；没有进入匹配的乱序操作不会出现在该 Tau 中。

第三条是针对所读实现的静态推导，不是新跑出的实验。例如预测动作 A,C,B,D 对参考 A,B,C,D，按该实现可保留 A、C 的单调锚点，其 Tau 仍为 1。代码另有 strict 和 LCS 指标，不能因此声称整套 SCORE 没有顺序检测能力。它说明 **Tau 不能单独作为“已经正确识别所有顺序错误”的验证证据**。

## ClearEval 应提取什么

借用动作锚点与可分解评价的思路；添加答案内来源、操作实例、阶段与真实前后依赖。保存原始 SR/SP，补充语义覆盖单列。不要要求所有既有自由文本先满足作者生成范式的四种标签，或以文字行数相等代替必要功能完整。

“结构化步骤＋顺序”已有明确先例。可检验差异应落在中文真实答案、合法拆合、完整多路线、来源适用性和局部未知的评分影响上，且必须与简单翻译/替换编码器作消融比较。

## 其他方法的细节适用边界

| 方法 | 可以移用的具体部分 | 未替我们解决的部分 |
|---|---|---|
| [PEG / X-WLP](https://aclanthology.org/2021.eacl-main.187/) | 显式片段上的实体、操作和跨句关系 | ClearEval 通道需要哪些事实；完整图标注的人力成本 |
| [跨动作 MSTG](https://aclanthology.org/2021.acl-long.525/) | 材料流与隐含参数关联 | 核心孵育范围、累计总量的领域计分约定 |
| [E5 模型卡](https://huggingface.co/intfloat/multilingual-e5-base) | 多语言候选召回、明确输入前缀 | 可用余弦阈值及步骤必要性；0.7 不可直接迁移 |
| [AlignScore](https://aclanthology.org/2023.acl-long.634/) | 有方向的上下文—陈述支持 | 独立操作次数；其最大值聚合本身不约束重复覆盖 |
| [AIS](https://aclanthology.org/2023.cl-4.2/) | 先判断可解释，再判断来源支持 | 不完整答案的正确补全；该任务不允许为被评答案补事实 |
| [HeidelTime](https://aclanthology.org/S10-1071/) | 时间表达定位、数值规范化 | 洗涤属于哪一阶段、累计和可选分支如何进入 EGES |
| [Ollama Schema](https://docs.ollama.com/capabilities/structured-outputs) | 限制输出字段和类型 | 关系是否正确、评分职责是否合理 |
| [LangExtract 输出文档](https://github.com/google/langextract/blob/main/docs/examples/output_schema.md) | 来源定位设计 | Ollama provider 自定义 Schema 支持；目前该 provider 不支持 |

本地可用便携 Python 的依赖版本记录在 [LOCAL_EVIDENCE.json](LOCAL_EVIDENCE.json)。Qwen3-Embedding 的官方 transformers 下限高于当前环境；尚未验证安装及推理。PEG 旧训练环境和完整外部评价流水线均不应直接覆盖当前环境。先移用所需数据表示与算法片段，再决定是否引入额外依赖。
