# 评估器开发计划与验证边界

单方法边界：每个完整候选仅采用一个透明方法；前处理、脱水、透明、匹配、成像与存储可为同一方法内正常步骤。A/B表示两个独立单方法替代。自行串联透明方法及分支拼接只作为历史错误输出/工程负例识别，不作为合理科学方案或主要研究命题。

状态：开发计划、已实现工程接口及离线开发验证记录；不包含正式基准评估结果，不包含独立专家科学标签。
日期：2026-10-02（Asia/Shanghai）。
适用源码：当前隔离工作区；历史输出、19 个开发片段及已有模型分数均不得充当本计划的新真值。

## 1. 用户目标与范围

本轮只完善评估器，并用受控开发实验验证它的工程行为。六方面保留完整接口：
1. 专家一致性与科学判断：准备样本/答案/来源/评估器版本绑定和需求级标签格式；独立专家标注、科学正确性与一致性分析由用户后续负责。
2. JSON 抽取忠实性：验证自动结构是否保持原文实体、否定、单位、范围与分支，并追踪抽取差异对下游结论的影响。
3. 多解与关键变化：接受满足同一显式需求结构的完整替代路线，发现关键语义变化；不把文本相似性当科学正确性。
4. 稳定性：固定输入的重复记录、缓存与失败恢复；准备受控重复裁判/跨家族运行接口。离线工程回放不能证明真实裁判稳定。
5. 同信息对照：各工具与策略使用相同任务、答案和可用来源；比较可审查的机械行为。科学准确率需要独立科学标签。
6. 多目标关系：在硬约束与可比性检查之后区分支配、取舍、相同、信息不足及不可比。

不得运行正式 MCQ/OEQ 基准、重评历史被评模型、发布新的 CCE 科学准确性结论或把已有 19 个片段当独立标签。合成 fixture 的 oracle 仅来自其明示合同或输入保持变换。完整合成流程使用虚构试剂/方法，是软件材料，不是可执行湿实验建议。

## 2. 已发表工具与可用实现覆盖矩阵

| 工具/机制 | 典型使用场景及可复用内容 | 覆盖范围 | 组织光透明领域仍缺的条件 |
|---|---|---|---|
| BERTScore | 候选与参考的上下文词元相似性；保留为描述性文本对照 | 措辞/参考接近程度 | 多条有效化学路线、否定、单位和条件适用性不能由相似性单独证明 |
| ALCE | 带引用问答；引用质量与断言支持检查 | 引用定位、引用支持研究机制 | 方法身份、版本更正、组织/标签/尺度/物镜条件；存在引文不等于科学适用 |
| RAGAs | RAG 上下文忠实性；拆断言再查能否从上下文推出 | 给定上下文支持 | 原答案抽取是否忠实、上下文本身过期/错配、硬约束及多目标关系 |
| RefChecker / RAGChecker | claim/triple extraction、检查与聚合，可借鉴可定位断言和双向覆盖 | 断言粒度与上下文检查 | 抽取器误差和生物适用条件需要单列；reference recall 不应直接惩罚合理替代 |
| Pydantic strict / Outlines | 类型/额外字段验证及约束解码 | JSON 语法/结构 | 合法 JSON 不能证明 probe、negation、step、basis 的原文含义正确 |
| Instructor source-context validator | 原文 context 中验证引用；保存失败/重试 | 原文定位、恢复记录 | substring 只证明存在，不能证明字段含义、引用蕴含和适用性 |
| MT-Bench / LLM-as-a-judge | 开放式助手回答与人类偏好；研究位置和篇幅偏差 | 裁判受控运行设计 | 稳定与偏好接近不是组织光透明科学准确性证据 |
| pymoo feasibility-first / Pareto | 先处理数值约束可行性再比较多目标向量 | 已定义数值目标的关系逻辑 | 目标方向、单位、测量条件、未知值及科学适用性仍须先审核 |

原始工具文献与实现：
- [BERTScore 原论文](https://arxiv.org/abs/1904.09675)、[官方实现](https://github.com/Tiiiger/bert_score)：用于文本生成相似性，不能外推为本领域科学验证。
- [ALCE 原论文](https://aclanthology.org/2023.emnlp-main.398/)、[官方实现](https://github.com/princeton-nlp/ALCE)：引用质量的研究机制可复用。
- [RAGAs 原论文](https://aclanthology.org/2024.eacl-demo.16/)、[官方实现](https://github.com/explodinggradients/ragas)：上下文忠实性与独立科学正确性分开。
- [RefChecker 原论文](https://arxiv.org/abs/2405.14486)、[官方实现](https://github.com/amazon-science/RefChecker)；[RAGChecker 原论文](https://arxiv.org/abs/2408.08067)、[官方实现](https://github.com/amazon-science/RAGChecker)。实现可用性及版本须在运行 manifest 中记录；归档仓库不作为强制新依赖。
- [Pydantic strict](https://docs.pydantic.dev/latest/concepts/strict_mode/)、[额外字段规则](https://docs.pydantic.dev/latest/api/config/)、[Outlines 1.0 输出类型](https://dottxt-ai.github.io/outlines/1.0.0/features/core/output_types/)、[Instructor 验证与重试](https://python.useinstructor.com/concepts/retrying/)：属于工程结构能力，不是已发表的科学评估结论。
- [LLM-as-a-judge 原论文](https://arxiv.org/abs/2306.05685)：报告的通用助手偏差提示应做位置/篇幅对照，不保证本领域适用。
- [pymoo feasibility-first](https://pymoo.org/constraints/feas_first.html)、[实现引用与原论文入口](https://pymoo.org/references.html)：复用明确数值比较原理，科学值不由算法创造。

采取“先使用现有机制，边界不足处增加合同层”的方案。此表是能力覆盖分析，尚未宣称任何工具在本任务上的实测失效或胜出。模型工具适配器可选，不应让离线工程验证依赖下载权重或外部 API。

## 3. 组织光透明原始证据及外推边界

| 方法 | 已核验身份 | 可用于设计开发案例的来源事实 | 不能自动推导的科学标签 |
|---|---|---|---|
| MACS | 2020，DOI 10.1002/advs.201903185，PMC7175264 | 论文区分切片与整成年鼠脑；为大样本引入 R0→R1→R2；考察亲脂染料 | 任意尺寸都必须所有步骤、所有亲脂标签都相同效果、任意替代路线都失败 |
| FRUIT | 2015，DOI 10.3389/fnana.2015.00019，PMC4338786 | SeeDB 衍生果糖/尿素体系；黏度、尺度、灌注与 DiI 保持相关 | 将 FRUIT 文献身份标成 SeeDB2；将作者展示范围推广到任意组织/标签 |
| SeeDB2 | 2016，DOI 10.1016/j.celrep.2016.02.057 | 折射率与浸液物镜匹配；后续作者方案分 G/S | 把薄切片推荐提升为普遍硬禁止，或认为透明就能达到任何物镜分辨率 |
| FDISCO | 2019，DOI 10.1126/sciadv.aau8355，PMC6357753 | 低温、pH、脱水→RI matching；时间依组织/尺度 | 参数偏离必然发生已知科学失效；荧光蛋白保持等于任意 DiI/DiD 保持 |

来源：
- [MACS 原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC7175264/)。
- [FRUIT 原论文](https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2015.00019/full)。PMC4338786 不是 SeeDB2，来源身份需要修正，不能直接替换论文内容而不更新绑定。
- [SeeDB2 原论文](https://www.sciencedirect.com/science/article/pii/S2211124716301784)、[2018 作者方案](https://bio-protocol.org/en/bpdetail?id=3046&type=0)。
- [SeeDB2 更正通知](https://bio-protocol.org/en/bpdetail?id=3095&type=0)：原 PBS recipe 为 10x，应明确稀释到 1x。真实的旧版本引文与当前正确版本必须分开记录。
- [FDISCO 原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC6357753/)。

以上事实仅为失效假设的原始出处。fixture 使用带 synthetic 标记的重新编写文字与显式任务合同；不得伪装成真实论文引文、独立专家标签或实测组织效果。DiI 与 DiD 在软件实体层保持不同，不能由字符串接近或同为亲脂染料自动建立科学兼容性。

## 4. 第一性原理与六条可证伪假设

可靠结论至少需要：输入身份正确→原答案忠实读取→条件及逻辑保持→来源身份/原文位置/版本正确→引用支持与任务适用性分别判断→必要条件不被补偿→可比目标按正确方向比较。每一层保留 proposed 与 effective 状态，未知和技术失败不映射为科学零分。

### H1 参考相似性不能单独接受多解或捕获关键变化

失效猜测：有效路线改变大量词语；错误否定/单位/顺序改变少量词语。
优化：需求级结构、完整分支及 scoped 条件；文本指标仅为独立描述列。
实验：固定完整合成方案，构造同义表述/格式变化、否定翻转、路线名称替换和不完整分支拼接。
机械预期：等价的显式需求结构不因名称/表面措辞变化被拒；否定翻转可定位；两条失败路线不能互相借满足项。
证伪：若允许来源/任务合同完全相同的等价方案而实现仍拒绝，或拼接后得到满足，则优化失败。
科学边界：合成同需求结构不证明真实替代路线可接受。

### H2 合法 JSON 不保证抽取忠实

失效猜测：probe 混淆、否定丢失、百分比 basis 丢失、处理/存储温度合并、步骤作用域与分支误归属。
优化：原文 span、明确字段解释、scope、polarity、unit/basis；原始返回及每次修复可追踪。
实验：在新建完整方案中分别进行 DiI→DiD、否定翻转、vol%→w/v、储存温度改动、处理温度改动、相同数字不同段落和缺失字段变化。
机械预期：4 °C 与 277.15 K 仅在明确转换中等价；vol% 与 w/v 不自动等价；缺信息保持 UNDER_SPECIFIED。
证伪：引用仍在文本中但抽取字段已改义，却继续通过忠实验证。
科学边界：faithful 不等于 scientifically correct；人工结构标注也不是独立科学标签。

### H3 引用真实、蕴含与适用性是不同层

失效猜测：引用身份错配、断章取义、范围外推及旧版本可使“有引用”误被当作充分支持。
优化：source_identity、quote_authenticity、entailment、applicability 和 correction/version 链独立状态；不以 source allowlist 代替蕴含。
实验：相同引用分别改 source ID/版本/样本范围；真实出处中的旧版本参数与 synthetic 更正源同时提供。
机械预期：身份冲突被拒；文字存在仅使 quote 层通过；未提供语义审核不自动通过 entailment；过期条目不通过当前版本合同。
证伪：只给真实 quote 或 allowlist 就得出科学 SATISFIED。
科学边界：真实论文范围外参数应“与来源不一致/待审核”，不能自动称为实际失败。

### H4 必要条件不能被平均分补偿，建议不能被提升为硬条件

失效猜测：高软分掩盖明确硬约束违反；来源推荐被误当普遍必要条件。
优化：user hard、已审核 scientific necessary、recommendation、soft objective 分开；全局必要项 AND 完整路线 OR。
实验：九项满足一项硬违反；完全相同文本分别配置为 hard/recommendation；缺信息与明确否定分开。
机械预期：VIOLATED 不能靠其他分项通过；建议偏离不产生硬失败；UNDER_SPECIFIED 与 UNRESOLVED 保留。
证伪：平均补偿、默认补值、某分支满足替另一分支补全。
科学边界：只有明示任务硬约束和已审核科学必要项可以可靠 gate。

### H5 Pareto 判断前须可行且可比

失效猜测：目标方向、单位、尺度或缺值未检查时出现伪支配；样本收缩的价值依任务目标变化。
优化：先硬约束可行性，再校验 objectives direction/unit/basis/scope 和 provenance，最后作数值关系比较。
实验：交换 A/B、等价时间单位、同名不同 measurement_scope、一优一劣、缺一个目标、硬约束违反。
机械预期：支配关系可反向；一优一劣为取舍；缺信息为未决；不同 scope 为不可比；不可行方案不靠软优势获胜。
证伪：任何一项不可比或缺值仍宣布支配。
科学边界：合成目标值只证明比较逻辑，不证明真实性能或合理科学取舍。

### H6 相同输入、重复记录与技术失败应可审计

失效猜测：缓存键缺任务/来源/裁判配置，重试掩盖首次失败，或失败被丢出分母；偏好裁判受名称/篇幅/位置影响。
优化：冻结输入 bundle 与配置哈希；每次 attempt/repeat 独立身份；原始返回、解析失败及重试追加保存；缓存不算独立重复。
实验：固定 fake adapter 返回、解析异常、超时、断点恢复；改变任务/来源/裁判版本观察缓存隔离；实际模型重复/跨家族实验另行由 runner 保持同输入受控开展。
机械预期：缓存可追踪但不增加独立调用数；失败保留；终止状态由 live handle 与完成记录验证。
证伪：换证据命中旧缓存、成功重试删除失败、观察超时导致同一任务重复启动。
科学边界：离线回放不能证明模型稳定，稳定也不能证明科学准确。

## 5. 材料、接口及同信息对照

材料位于 experiments/evaluator_development/：
- hypotheses.json：假设、来源、优化、可证伪条件、科学边界。
- fixtures.json：synthetic source text、完整 candidate text、任务合同、分支/全局要求及 expected 机械不变量。
- README.md：声明格式和材料使用约定。

fixture 预期是测试合同，不是 scientific reference。各 case 保留来源、物种/尺度/标签等模拟 scope；真实文献只放在 origin_references，不是合成 source 的真实性凭据。
比较 old/simple/rule/new adapter 时提供完全相同的 task、answer、source bundle、允许的版本及 scope，记录 adapter 可见字段和 bundle hash。不能让某个 adapter额外看到 held-out expected 或专家标签。
开发集与保留测试按完整任务/来源模板分组，不能把同模板改写随机拆成看似独立样本。统计首先报告 case failure、错误层、运行失败与未知比例；不得报告科学 accuracy 或正式模型排名。

## 6. 多轮迭代与最长 48 小时可恢复流程

| 阶段 | 行动 | 产出与进入下一轮条件 |
|---|---|---|
| Round 0 | 冻结源码、文献身份、工具版本、fixture schema；先复现已有机制的机械失效 | manifest、逐 case 原始结果；没有失败不能宣称现有工具已失效 |
| Round 1 | 修正抽取、strict schema、scope/否定/单位与source layers；逐机制开关对照 | 修改前后同输入结果、错误归因、负例仍保持未决 |
| Round 2 | 验证全局 AND/完整分支 OR、硬约束和可比目标；增加新失败的反例 | branch 混合和伪支配不能通过；预期科学状态保持待审核 |
| Round 3 | 重复记录、缓存隔离、错误/超时注入、断点恢复；保留模板回归 | 每次 attempt 可审计，恢复不改已冻结 bundle |
| 后续 | 新失败→修订假设→一项优化→同信息对照→保留测试；必要时增加裁判开发实验 | 失败原因及限制有证据；正式benchmark始终不启动 |

48 小时是可能需要的运行上限，不是必须耗满的时长，不是稳定性或正确性的证据。持续实验必须：
1. 每个 run 使用唯一目录、冻结 manifest、明确开始/截止时间（Asia/Shanghai）、case ID、repeat ID、adapter/config hash。
2. append-only attempt ledger 保存开始/原始输出/技术失败/结束状态；完成记录在输入哈希及输出完整性验证后产生。
3. 中断后先检查同一 live process/session/handle 和 ledger。仅观察超时不启动新副本；终止已确认后才恢复未完成项。
4. 在固定 bundle 下恢复；任何答案、来源、fixture 或代码变更生成新 revision/run，禁止把新旧结果合并成一次固定输入实验。
5. 失败例转为明确回归合同，同时保留未用过的完整模板；一次新失败后仅修改有证据支持的机制，避免按预期反写通过。
6. 每轮记录完成数量、失败层、未知数、缓存命中、真实调用/回放数量及剩余工作；不得把 cached/fake 运行计作真实重复评分。

## 7. 完成审计与用户专家工作

工程完成须有当前源码及 runner 输出直接证明：
- JSON strict、原文span、实体/否定/单位/scope/步骤/版本/分支机械合同覆盖；
- 身份、quote、entailment、applicability 四层状态分离；
- global hard constraints 与完整 alternatives 不拼接，recommendation 不升级；
- 可行性/可比性/未知值先于 Pareto；交换关系与单位转换对照通过；
- manifest 与缓存键覆盖任务、答案、来源、要求、代码和裁判配置，失败与重试可恢复；
- 同信息对照不泄漏 expected，运行不触发正式 benchmark；
- 实际完成项目与待审核科学事项分别列出。文档/绿色测试不能为未覆盖项背书。

用户专家后续负责：独立来源适用范围审核、抽取忠实人工标注、完整替代路线科学标签、关键错误等级、必要条件依据、实际多目标关系、同输入裁判科学正确性与一致性。
工具只准备可填写接口与绑定；不得填造标签、以开发oracle充当独立专家或声称已完成专家一致性。当前目标是让上述专家验证可执行且不会被工程缺陷污染。

## 8. 实际轮次与可审查结果

以下为已经执行的离线工程验证；不把轮次数或耗时作为科学有效性证据。每轮模型调用为 0、科学标签为 PENDING_USER_EXPERT。详见[开发记录](../experiments/evaluator_development/README.md#已实际执行的开发验证2026-10-02)。

| 实际轮次 | PASS / FAIL | 观察与改动 | 冻结 manifest / 原始摘要 |
|---|---:|---|---|
| round01-initial | 35 / 9 | 适配器把整个 task 对象传给 required_fields，9 个抽取案例均为 ADAPTER_ERROR；未得到核心抽取结论。 | [76bf243064fc…](../../evaluator-development-runs/round01-initial/manifest.json) / [summary](../../evaluator-development-runs/round01-initial/summary.16e73dd52e0b44cf851a81b2f3946489.json) |
| round02-fixed | 44 / 0 | 修正参数为显式 required_fields 列表；该列表来自公开任务合同。7 项后恢复 37 项，首轮失败记录保留。 | [58ab31354821…](../../evaluator-development-runs/round02-fixed/manifest.json) / [summary](../../evaluator-development-runs/round02-fixed/summary.200cf7589870452fb10c29f549356e3d.json) |
| round03-current | 44 / 0 | 冻结包含额外 fidelity 防护的源码；与 round02 使用相同材料。11 项后恢复 33 项，属于回归检查。 | [3efb3b9382d9…](../../evaluator-development-runs/round03-current/manifest.json) / [summary](../../evaluator-development-runs/round03-current/summary.f70fcb991443443caf4cd90c67316b0d.json) |
| round04-integrity | 44 / 0 | 运行器 v2 增加完成记录校验和与存活进程检查；13 项后恢复 31 项。 | [52e6a09eb557…](../../evaluator-development-runs/round04-integrity/manifest.json) / [summary](../../evaluator-development-runs/round04-integrity/summary.e6ab14a8596c4178b5352be117217b19.json) |

首轮 9 项均为接口参数错误 `Required fields must be explicit unique identifiers`：适配器传入整个 task 对象，核心要求公开 required_fields 列表。第二轮修正该映射；该失败不是模型质量、已发表工具或科学算法失效。第三轮在同材料上验证更严格的核心防护，但旧轮已有 44 PASS，不能声称因此测得性能提升。第四轮验证运行器记录完整性、恢复与进程锁；新源码保持旧结果不变。

独立正常流程/身份/比较冻结测试共 13 项实际通过。其 G→E→J 固定假传输用于验证工程流程和来源可追踪性，真实模型调用为 0；raw chunks、parsed 或 invocation 缺失/错配与内容自行重算 hash 均不能留下已完成认证。同信息 guard 对照不接收私有专家标签；数值比较先从 requirement 重新计算可行性。完整 E2E 夹具使用一项单透明方法及正常处理步骤，MG 为生成任务材料、M 为消费其输出的评估材料。

新增源码必须在最终冻结轮次再验证；前四轮不可修改或合并。用户专家工作、真实裁判重复稳定性、独立科学准确性和实际组织效果均未因这些测试而完成。

旧重复裁判入口另有真实接口失配：成功新 scorer 返回诊断结构，旧恢复路径读取不存在的根分数。首次失败日志保留；生产读取层现分开技术完成、数字完整、数字未知和显式失败，`None` 不触发重试且不填零。数值统计明确为 legacy 描述，科学准确率保持未知。自足合成归档验证 16 个相关测试与完整 226 个测试通过，见[兼容性记录](../experiments/evaluator_development/README.md#旧重复裁判入口的真实兼容性修复)。专家统计仍只从显式导入的评价读取；本次没有新增独立专家标签或正式模型排名。
