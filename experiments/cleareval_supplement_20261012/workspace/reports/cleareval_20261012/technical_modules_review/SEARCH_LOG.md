# 检索与判定记录

2026-10-12。使用原生网页检索、ACL Anthology、会议论文集、作者论文全文、官方源码和软件文档。按 academic-research-suite 的定向深度研究流程执行。本文件整理实际检索主题与阅读范围，非完整 API 请求流水，也不声称达到系统综述的穷尽检索标准。

## 从本地现象提出检索问题

| 本地问题 | 检索主题 | 最相关纳入结果 | 纳入理由 |
|---|---|---|---|
| 中文步骤零命中、相似度不等于覆盖 | multilingual embeddings; structured protocol evaluation; atomic factual evaluation | E5、BGE-M3、Qwen3-Embedding、SCORE、AlignScore、FActScore | 分别覆盖候选召回、动作对齐与证据支持，职责不同 |
| 跨句标签关系与阶段继承 | process-level scientific protocol representation; cross-action relations | PEG/X-WLP、MSTG | 直接研究协议关系而非一般聊天评分 |
| 时间范围、累计、每次与分支 | scientific protocol extraction duration scope repeated operations cumulative temporal relations paper | HeidelTime、MSTG、Temporal Constraint Networks | 识别、关系与计算三层分别处理 |
| 仅有通用残句却命中参考 | attribution interpretability atomic fact support | AIS、FActScore | 先判断答案内容可解释，防止参考反向补全 |
| JSON 有效却返回 null | structured outputs; criterion-based LLM evaluation | Ollama、XGrammar、LangExtract、G-Eval | 区分结构保障与语义/职责 |
| 同方法多版本 max-SR | reference set variation evaluation | References Matter | 检查参考集变化对评价的影响 |
| 重复分数稳定但依据可能不同 | behavioral testing; LLM judge biases; evidence retrieval jitter | CheckList、MT-Bench、EvalEval 2026 片段稳定性 | 分开正确性、重复性和证据身份 |
| 分支改变 HV 和 Pareto | multiverse; specification curve; robust multi-objective optimization | Steegen、Simonsohn、Ehrgott 等 | 连贯场景下的结论边界 |

用户要求进一步细化后，追加的原样检索包括：

```text
scientific protocol extraction duration scope repeated operations cumulative temporal relations paper
HeidelTime 2010 temporal expression extraction normalization durations paper
Learning Latent Structures Cross Action Phrase Relations Wet Lab Protocols implicit arguments temporal causal
```

前期检索按上表主题归纳，未将回忆中的查询字符串伪装成逐条精确日志。

## 深读后的方向变化

1. 找到 SCORE 后，把“结构化分解＋顺序”从潜在创新降为必须对照的已有方法。
2. 读取其评价源码后，明确异常归零、动作锚点和单调锚点 Tau 的实现边界；只针对访问到的代码版本，不外推整篇工作的全部结论。
3. E5 的官方使用说明要求区分检索与对称相似度前缀；其相似度尺度使 MPNET 的 0.7 不能直接迁移。
4. 原生 Ollama 与 LangExtract provider 的 Schema 支持不同，避免为了结构化输出先引入一个反而不支持所需模式的中间层。
5. MAP2 查表通过源码证明是范围索引丢失，不再把它包装成待文献解决的推理难题。
6. 时间文献分别涉及表达规范化、跨动作关系和约束计算，没有找到可直接保证本地“累计至/核心阶段/可选分支”全部正确的现成组件。

## 纳入、排除和访问限制

优先纳入能对应一个明确失败位置的原始论文及作者实现；博客聚合页只作为线索，不作技术结论依据。软件文档与同行评议论文分开。ReGraph、E5、Qwen3-Embedding 按本次核实状态标为预印本/技术报告，不能仅因模型知名而称已同行评议。

SCORE 的 ICLR 2026 身份已由官方会议页确认。最终会议 PDF 访问失败；方法细节采用可访问的 arXiv v1 并明确版本。OpenReview 访问挑战未绕过。公开代码读取 main 分支，未声称已固定 commit 或执行复现。

ACRA/XDL 的完整实验执行路线、机器人依赖和大规模图训练不是本阶段的最小实现；查阅作为范围判断，没有把自动补全缺失操作的目标引入评分输入。Pyramid、SelectiveNet、PlanJudge 等旁支没有作为本轮核心设计的直接证据。没有因为标题相关而声称它们解决当前个案。

此次是问题导向技术综合，26 条核心来源的身份、阅读深度及适用边界见 [SOURCES.json](SOURCES.json)。本地证据与源码输入哈希见 [LOCAL_EVIDENCE.json](LOCAL_EVIDENCE.json)。没有新增实验、独立专家核查、外部模型安装或模型请求。
