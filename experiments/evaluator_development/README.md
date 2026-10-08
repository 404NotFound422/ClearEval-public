# 评估器开发材料

单方法边界：每个完整候选仅采用一个透明方法；前处理、脱水、透明、匹配、成像与存储可为同一方法内正常步骤。A/B表示两个独立单方法替代。自行串联透明方法及分支拼接只作为历史错误输出/工程负例识别，不作为合理科学方案或主要研究命题。

此目录提供新的合成方案、来源合同和可证伪假设。它不含正式评估结果、历史被评模型输出、19 个开发片段重评或独立科学标签。

- [开发计划](../../docs/evaluator_development_plan_zh.md)：文献/工具覆盖、领域失效猜测、优化和多轮迭代。
- [hypotheses.json](hypotheses.json)：6 条待验证假设及关联 case。
- [fixtures.json](fixtures.json)：44 个机械合同案例，含完整合成流程与原文定位。
- 科学审核统一保持 PENDING_USER_EXPERT。来源身份/语法/状态代数通过不等于科学正确。

## 格式合同

顶层：
- schema_version=evaluator-development-fixtures-v1
- scope=offline-engineering-only
- science_labels=PENDING_USER_EXPERT
- sources：synthetic source 的 text、身份、版本、scope、origin_references。
- cases：id、hypothesis_ids、kind、input、expected、scientific_limit。

所有 source 标注 origin_type=SYNTHETIC。origin_references 说明真实领域动机，不能把这些重新编写的合成文字当论文引文。真实 FRUIT 与 SeeDB2 的身份及 SeeDB2 更正链在计划中单独核验。

每个 case 的 expected 是隐藏工程 oracle。运行器不得把 expected/annotation/fixture_ids 提供给候选 adapter。人工预设 judgment 仅用于检验状态组合与工程 guard；不是独立专家科学标签或自动裁判质量真值。

| kind | 数量 | input | expected |
|---|---:|---|---|
| extraction_fidelity | 9 | 完整 protocol、task、proposed_facts；每个 fact 有 field/value/quote/start/end/scope，另可有 polarity/unit/basis | FAITHFUL/UNFAITHFUL、mismatch_fields、隐藏 annotation |
| strict_json | 3 | text、可选 allowed_fields；protocol/task 只说明合成场景，不进入 JSON 文本 | INVALID 与原因；重复key、NaN、未知字段 |
| source_layers | 5 | synthetic sources、claimed_source、source_id、quote、claim、可选 task_scope/required_version | source_identity、quote_authenticity、entailment、applicability及version_status分别记录 |
| requirements | 10 | requirements、protocol、预设 judgment、cards=[]、可选 formula、task | overall 四态；科学项仍为 PENDING_INDEPENDENT_REFERENCE |
| pareto | 13 | a/b 数值合同、task/scenario/constraints/objectives；protocols 提供对应完整合成流程 | 明确关系，不包含真实性能结论 |
| replay | 4 | 固定 payload、planned_count、attempts或changed_payload | 独立调用/缓存/失败数量与哈希隔离等机械不变量 |

字符定位采用 Unicode 字符索引，区间为[start,end)，必须精确得到 quote。当前材料均为 BMP/ASCII 文本，Python 字符与 Windows/JavaScript 索引相同；后续加入补充平面字符时应由统一 Unicode codepoint 工具重新定位，不能直接复用 UTF-16 偏移。

extraction_fidelity 必须同时检查字段含义和原文作用域；只验证 quote 是 substring 会让 DiI→DiD、否定丢失、百分比basis或存储/处理scope错配漏过。expected.annotation 不应成为 adapter 输入。

source_layers 的 PRESENT 仅指文字存在。源 allowlist 和文字存在均不能自动使 entailment/applicability 通过。真实科学 entailment 的模型 proposal 与人工标签必须分开；合成 case 中未提供语义审核，所以保持 UNRESOLVED。

requirements 使用 kind=TEXT/SCIENTIFIC、necessary 布尔及 scope=GLOBAL/ROUTE；ROUTE 另有 route_id。GLOBAL 必要项 AND 完整路线 OR 是最低机械合同。case req_06 与 req_08 故意给出不安全 OR formula：运行器应仍阻止绕过必要全局/串行项。失败替代分支不能拼成满足方案；完整A满足可以在B失败时通过。软建议不能因名称为“推荐”而外推为科学必要条件。

pareto 先比任务/场景与所有显式 scope/basis/direction/units，再检查硬约束可行性和缺值，最后比较同方向区间。时间 h/min 是明示可换算的同量单位；未知浓度basis不能擅自转换。交叠区间保持 UNRESOLVED。数字完全合成，不是文献提取或实测。

replay 中 FAKE_CALL 只代表离线 adapter 调用，实际模型调用数应为0；CACHE 不算新的独立重复。失败后成功重试增加 attempt，不增加 repeat，也不能抹去首次失败。changed_payload 必须导致新cache key；真实模型稳定性另须固定输入重复运行。

## 材料校验与实验记录

材料自校验只证明 JSON 可读取、ID 唯一、source 均为 synthetic、fixture/hypothesis 引用吻合，以及提供的 quote/span 确实指向 protocol。它不能证明 adapter 行为已通过，更不能证明科学效果。

运行器应写逐case实际结果、结果与隐藏oracle比较、适配器可见输入哈希、首次失败、重试和缓存来源。不得直接把expected复制到actual。未实现adapter时明确 UNSUPPORTED/PENDING，不算通过。

开始实际开发运行前固定代码、材料、来源和适配器配置；每轮新目录/manifest。开发入口采用以下合同；是否已验证须查看实际 CLI help、逐case输出和 manifest，不以此命令示例充当执行证据。

从仓库根目录运行，使用当前环境的 Python；`--out` 可指定新的本地运行目录：

```powershell
python -B -m experiments.evaluator_development verify --fixtures experiments/evaluator_development/fixtures.json --out evaluator-development-runs/round01 --label round01 --max-cases 20 --max-seconds 600
python -B -m experiments.evaluator_development verify --fixtures experiments/evaluator_development/fixtures.json --out evaluator-development-runs/round01 --label round01 --resume
```

同一round只能在代码/fixture/来源和配置冻结的条件下继续；已完成case不重做。改变任一输入或实现使用新round目录。--max-seconds 是单次执行预算，可配置最长172800秒（48小时）作为运行上限，不强行消耗预算；本材料不宣称已运行48小时，离线工程回放不是科学验证完成。verify 默认不发送模型请求，实际模型调用数必须明确为0。正式benchmark入口保持关闭。

## 迭代和专家边界

先复现旧机制机械失败，再每轮只改有证据支持的机制，并保留之前失败的回归例及未使用完整模板。长时间任务通过live handle和append-only ledger恢复；观测超时不等于任务终止，不能据此另启副本。

工程层要验证抽取/版本/分支/约束/可比性/缓存/失败记录，科学层由用户专家后续审核：真实来源适用范围、完整替代路线、关键错误、必要条件依据、实际多目标关系，以及专家一致性。不得用44个合成cases或旧19个片段代替这些标签。

## 已实际执行的开发验证（2026-10-02）

每轮均完成 44 个新合成案例，模型调用为 0，科学验证仍为 PENDING_USER_EXPERT。完整输出保存在本地未分发的 `evaluator-development-runs/` 档案中，逐 case 的 observed 由核心 API 实际计算后再与隐藏工程合同比较。下表保留历史档案标识；源码 clone 不包含这些旧运行记录，可用上面的命令在新的本地目录复现工程合同。

| 实际轮次 | PASS / FAIL | 观察与改动 | 冻结 manifest / 原始摘要 |
|---|---:|---|---|
| round01-initial | 35 / 9 | 适配器把整个 task 对象传给 required_fields，9 个抽取案例均为 ADAPTER_ERROR；未得到核心抽取结论。 | 本地 `round01-initial/manifest.json`（76bf243064fc…）；`summary.16e73dd52e0b44cf851a81b2f3946489.json` |
| round02-fixed | 44 / 0 | 修正参数为显式 required_fields 列表；该列表来自公开任务合同。7 项后恢复 37 项，首轮失败记录保留。 | 本地 `round02-fixed/manifest.json`（58ab31354821…）；`summary.200cf7589870452fb10c29f549356e3d.json` |
| round03-current | 44 / 0 | 冻结包含额外 fidelity 防护的源码；与 round02 使用相同材料。11 项后恢复 33 项，属于回归检查。 | 本地 `round03-current/manifest.json`（3efb3b9382d9…）；`summary.f70fcb991443443caf4cd90c67316b0d.json` |
| round04-integrity | 44 / 0 | 运行器 v2 增加完成记录校验和与存活进程检查；13 项后恢复 31 项。 | 本地 `round04-integrity/manifest.json`（52e6a09eb557…）；`summary.e6ab14a8596c4178b5352be117217b19.json` |

round01→round02 修复的是接口映射错误，不能称为已发表工具或科学算法失效。round03 之前这些 44 例已经通过；新增防护的依据是独立工程反例和代码审查，这一轮只能证明回归未破坏原合同，不能据此量化算法提升。round04 的拒绝篡改检查确实修改了 observed 并保留旧校验和，恢复时拒绝；活进程锁测试使用实际存活 PID 并由第二个 CLI 拒绝重复启动。改变旧轮源码/输入后的恢复也被拒绝。

新增 `tests/test_analysis_identity.py` 和 `tests/test_comparisons.py` 共 13 项实际通过（2.306 秒）。它们调用真实 `run_job`、解析、裁决、analysis 和比较计划冻结，传输只返回合成固定响应。覆盖正常 G→E→J 流程、同信息对照、0 模型调用的比较计划，以及删除原始流/parsed、重写内容并自行重算哈希、重写 request 并自行重算哈希、invocation 不一致、生成依赖完整性。假传输的重复不能估计真实裁判稳定性，分析结果明确 NOT_ESTIMABLE。

这些 E2E 测试初次运行的 9 项 setup ERROR 发生在生成步骤预取自身依赖、尚未到达受测断言；随后夹具拆为生成材料 MG 和依赖输出的评估材料 M，核心也限制生成阶段预取依赖。因此不能把首次 setup 错误说成 9 项身份机制失效，或把最终通过归因于单一改动。最终源码仍须另建冻结轮次，不覆盖前四轮；此记录不宣称已运行 48 小时或完成独立科学验证。

## 旧重复裁判入口的真实兼容性修复

补充开发检查发现：新 OEQ scorer 的成功结果为技术 `VALID` 和 `legacy_diagnostics`，故意没有根 `scores`；旧 `judge_reliability.run_judge` 在成功 canary 后恢复时仍读取根分数，实际报 `missing_or_invalid:c_step`。这是已复现的生产接口失配。首次失败日志作为本地未分发档案 `pilot-compatibility-initial/unittest.log` 保留，未以 mock scorer 隐藏问题。

修复仅增加统一的结果读取层并接到恢复/描述统计：技术完成与完整数字向量分别计数；合法 `VALID` 诊断里某个值为 `None` 时保留数值未知，恢复不重复调用。显式传输/解析失败仍保留并停止继续派发。完整 legacy 数值只经临时描述性视图计算，报告标记 `LEGACY_CONTINUOUS_DIAGNOSTIC`，不写回正式分数；旧归档根分数形状仍可读取为 `ARCHIVED_SCORE_DESCRIPTIVE`。科学准确率保持 `None`，没有值的聚合不填零。

相关测试现在自足：在临时目录生成 12 个已有题目/需求向量同源配对的冻结子集、3 模型×3 设置的小型新合成回答和数字形状；回答与成绩均标 `SYNTHETIC_ONLY`，历史 human provenance 输入为空。未下载大型历史归档，也不新增专家标签。

本地未分发档案 `pilot-compatibility-fixed/judge-tests.log` 记录实际 16 PASS；`pilot-compatibility-fixed/full-tests.log` 记录实际 226 PASS、0 FAIL/ERROR/SKIP。生产 scorer 与 collector 真实执行，仅 provider 固定返回合成响应。集成检查把成功 canary 的时间数值置为 `None` 后恢复：总计仍为 108 次假 provider 调用、108 技术完成、0 失败；数值未知另列，不成为重试理由。固定假响应得到零波动只说明夹具固定，不能证明真实裁判稳定性。
