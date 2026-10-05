# 评估器字段与来源防线开发记录

本记录是实现审查和离线合成工程验证，不包含真实方案评分、BioProBench重跑、模型科学能力比较或专家一致性统计。用户负责后续专家核验。没有自动创建科学真标签。

## 已接入的机制

- `contract.adjudicate` 保留 proposed/effective 判定和每条 guard。全局必要条件与完整单方法替代路线合取；调用方的自定义 OR 只能增加条件，不能绕过关键条件或拼接不同路线的半个答案。旧科学判断结构不再自动授权决定性状态。
- `contract.validate_extraction` 调用 `fidelity.audit_extraction`，每个事实字段绑定原文字符位置、原值和 EXPLICIT/DERIVED/INFERRED/MISSING 类型；保留否定、条件、顺序、重复操作、分支和样本身份。字段不能借用另一个分支中的相同词。旧提取结果保持原样，标记为结构诊断。
- `fidelity.audit_facts` 被离线开发入口调用，核对字段值、否定极性、阶段、数值与单位相邻绑定、体积/质量浓度基准。阶段别名是公开有限词表；未识别范围保持未决。显式 required_fields 只检查声明字段是否出现；没有该合同不能声称完整性成立。
- `evidence.validate_cards` 区分书目身份、带 hash 的全文快照、不可变引文定位与范围字段绑定。`check_scientific_support` 再核对要求级声明、版本/尺寸/对象/条件和原方案上下文。来源白名单、真实引文存在或范围匹配均不足以自动通过。
- `make_entailment_verification` 只接受显式提供的独立检查阶段适配器，固定其输入、原始关系输出与来源。主判定必须引用与当前要求、引文、范围和更正全文一致的冻结结果。NOINFO 不能改写成 REFUTES；检查器输出仍不是独立科学真值。
- 审阅包绑定方案、任务、要求、证据和公式版本。空模板、没有作者或未填暴露声明不会成为人工标注；人工字段参考与科学判定接口分开。匿名 HTML 显示严格来源格式中的链接、引文和更正文，采用 textContent 且不自动联网。

## 真实知识库来源处理

`KnowledgeBase/source_registry.json` 登记了六条真实来源的 DOI、标题、URL、版本关系。MACS、FDISCO、FRUIT 三篇官方 HTML 已保存原页面字节快照并用标准库 HTMLParser 提取正文；SeeDB2 2018 协议与更正通知的官方 PDF 已保存并用隔离的已发表 pypdf 6.19.0 提取逐页文字。五份正文均记录原始文件 hash、文本 hash 和真实定位，适用范围与独立蕴涵检查仍待审核。2016 研究论文目前只有书目记录，其 snapshot 保持 null。

| 来源 | 落地处理 | 尚缺 |
|---|---|---|
| [MACS 原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC7175264/) | 更正旧 RI 表的期刊书目信息为 Advanced Science；保留数值 | 已保存原始正文与逐字定位；定量参数及适用范围仍待审阅 |
| [FDISCO 原论文](https://www.science.org/doi/10.1126/sciadv.aau8355) | 登记原始方法身份；已有 article_chunk 仅保留提取文件 hash | 已保存正文及逐字定位；版本条件、对象和标签支持仍需分别核验 |
| [FRUIT 原论文](https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2015.00019/full) | PMC4338786明确归FRUIT；现有FRUIT_result.json身份与内容未替换成SeeDB2 | 已保存原文正文；旧误名绑定仍须显式迁移，不能更换标题后沿用推断 |
| [SeeDB2 2016 论文](https://www.sciencedirect.com/science/article/pii/S2211124716301784) | 独立于FRUIT和2018协议登记 | 研究论文快照与具体用途定位 |
| [SeeDB2 2018 协议](https://bio-protocol.org/en/bpdetail?id=3046&type=0) | 登记e3046与更正链；G/S不能当作唯一通用液体 | 已保存13页官方协议PDF和实际解析文字；time_kb旧SEEDB2_PROTOCOL_2015未自动改年或验证全部时间标量 |
| [SeeDB2 更正](https://bio-protocol.org/en/bpdetail?id=3095&type=0) | e3095仅关联e3046；PBS库存与工作液的更正分别记录 | 已保存1页完整官方更正PDF与实际解析文字；对当前具体声明的影响待审核 |

SeeDB2 HTML 请求失败及官方 PDF 下载成功的日志分别保留。PDF解析工具从官方 PyPI wheel 获取，校验官方元数据中的 SHA256并隔离解压，记录工具版本、wheel hash和实际源码树hash；没有系统pip安装。HTML和PDF正文均由原始文件机械提取，没有助手改写；PDF布局、字体或阅读顺序误差仍须对照原件审阅。

`method_ri_ref.json` 与 `tissue_ri.json` 的既有数值没有变化。解释改为未校准的旧组织 RI 启发式；它们不等于溶剂折射率、科学适用性或成功概率。缺少知识库条目是 NOINFO，不是实验不可行的证据。

## 工程验证与局限

本次定向验证包括37个字段/证据/人工接口合成测试，以及47个既有契约与审阅流程测试，均通过。它们覆盖错误标签、有引文但字段不忠实、未保留否定、v/v与w/v混淆、跨阶段温度、跨分支借词、更正全文不可见、真范围但假蕴涵、未决冒充违例、全局必要条件被OR绕过、即使机械来源绑定齐备也不认证多方法组合等反例。所有检查在本机使用标准库与合成适配器；没有调用真实模型。

这些通过结果不证明真实方案科学正确、不证明提取完整，也不能宣称已改善相对BioProBench的科学性能。引用关系检查阶段可能有误判；有限词表不能解决所有语义、角色或条件关系。正式科学结论仍须用户提供按版本对齐的原文审阅、适用范围和独立人工参考。