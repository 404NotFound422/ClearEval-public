# OEQ 评估器改进、知识库审计与运行说明

本轮完善评估器，不运行正式基准或重算模型排名。专家一致性及独立科学标签由用户后续完成。默认场景每份方案只选一种透明方法；单方法内的依赖步骤、完整的单方法替代方案，与自行串联多种透明方法分开。多方法拼接只作为异常输出处理。

## 已针对既有报告加强的地方

| 既有薄弱项 | 当前改进 | 可以证明的范围 |
|---|---|---|
| 未知兼容性给满分，SeeDB/SeeDB2、CD3/CD31、染料编号误匹配 | 精确方法/标记身份、显式未知和诊断覆盖计数 | 查表和身份错误反例已复现并修复；数值仍是启发式 |
| 合法 JSON /真实引文无法证明原答案被忠实读取 | 严格解析；字段、原文 offset、否定、单位、浓度基准、步骤/储存作用域绑定 | 字段读取和传递的机械错误可定位；独立人工忠实标注接口保留 |
| 引用存在或白名单就允许科学结论 | 来源身份、原文、版本更正、支持关系与适用范围分层；独立 checker 的冻结结果与主裁判分开 | 不以真实引用或来源 ID 冒充科学支持；真实来源与专家审核仍区分 |
| 软分平均掩盖关键必要条件，合理替代被单一参考惩罚 | 全局必要条件 AND；各完整单方法路线内部 AND、路线之间 OR；另作可行性与多目标比较 | 显式需求代数通过；并未证明超越 BioProBench 的科学检出率 |
| 开放题教师超时、格式错误，结果汇总混淆失败和未决 | 标准库真实 Ollama HTTP、正确 num_predict、显式超时/截断；保留技术失败和原始返回；技术完成单列 | 本地真实生产入口使用受控传输已验证；服务器真实调用结果另见运行工件 |
| 裁判重复、缓存、不同家族输入不受控 | 请求由冻结材料重建；生成到抽取/评审依赖再次校验；独立 invocation、缓存和失败分母；跨家族冻结计划 | 模拟回放不计真实模型重复；稳定性不能由一次成功证明 |
| RAG 只按题号取卡，缺卡/解析失败静默为空 | 绑定全题干元数据、单题需求、实际加载的 KB、来源登记和卡片 checksum；缺卡/旧版/错配明确拒绝 | 真实 builder→生产 loader 往返及版本变化回归已验证 |
| 正常配置加载导入所有供应商，Ollama 分支误落入 unsupported | 延迟加载所选供应商、JSON/YAML 配置、规范化模型名字、--model-config、--preflight-only | 无需为本地 Ollama 安装其他供应商 SDK；缺少 SDK 不产生伪造响应 |

已有对比中的主要问题包括：ClearEval OEQ 未得到有效教师评分，以及同证据 ERR 对照中的明确判定覆盖不足。本次修复前者的运行和解析环节、后者的证据/未决/失败可审查性。没有新的独立科学标签，不能宣称已在科学正确性或关键错误检出率上超过 BioProBench。旧报告与新开发结果不可混为一轮。

## 知识库的实际审计

当前知识库有 126 条时间记录、18 种 RI 方法参考、17 种方法兼容性记录，以及 18 个文献摘要 JSON。

- FlyClear 在 RI 参考方法集合中，但没有方法—荧光团兼容性行。缺失保留为未知。
- 5 条时间记录的排除标记标志与文字范围冲突：BoneClear 的 T07A/T07B，以及 SWITCH 的 T01/T03/T10。评分诊断将其标记为 time_scope_conflict；不擅改原时间窗口。
- 748 个兼容性数值单元未提供逐格独立来源及校准绑定。它们可用于启发式诊断，不是实验保持率或成功概率。
- `method_ri_ref.json` 使用组织 native RI 的启发式参照，不是透明液 RI；不得把 SeeDB2G/S 的液体值直接填入组织参照表。MACS 的错误期刊元数据已更正，RI 数值没有改动。
- FRUIT 摘要身份本来就是 FRUIT。新增 source_registry 保留 FRUIT、SeeDB2 原论文、2018 方案及更正通知的真实身份与关系，防止旧来源别名被默认为同一方法/版本。
- 实际 primary_sources 获取、哈希和解析状态以其清单为准。来源原文被保存，不等于所有适用性或科学推论已经通过专家审核。

## 题干版本必须明确

当前 `dataset/Q+AR/src/question_final.json` 与已有固定需求向量不是同一绑定版本。运行前检查将其拒绝，避免相同题号静默配错。

已有向量绑定的是 `dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json`。在这个版本上可以测试完整流程；若评测修订题干，需要独立的新需求文件及其绑定 manifest，不能只修改 hash 或自动挪用旧向量。

## 先检查，再运行

在服务器仓库根目录执行。下列为已绑定题干版、本地模型的流程命令；不会调用 GitHub 配置里的 API。

```powershell
python OEQ_run_grading_new.py --preflight-only --question-file dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json --model-config config/local_ollama.example.json
```

如果通过，使用新的输出目录执行受控开发样本：

```powershell
python OEQ_run_grading_new.py --question-file dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json --model-config config/local_ollama.example.json --models ollama_local --teacher ollama_teacher --qids 5 --shot-types 1-shot --gen-concurrency 1 --eval-concurrency 1 --response-dir review_artifacts/local_oeq_dev/responses --score-dir review_artifacts/local_oeq_dev/scores
```

这是可用命令说明，本轮没有用它运行正式全基准。`--eval-only` 可在严格题干绑定下复用同目录的已有开发答案；`--no-evaluation` 只生成。若使用用户私有 GitHub 配置，明确指定 `--model-config config/config.yaml` 及配置中的模型/教师名字，并先检查相应供应商依赖。

新输出除了 result JSON，还生成 `<result>.diagnostics.json`，包含技术完成/失败、未知分项、完整诊断覆盖及 Com/Cor/Eff/I_A 连续诊断。连续诊断与所有必要条件满足的证书分开。科学未知不应导致同一已完成教师输出被无限重调；技术失败保留。

## 开发实验与恢复

```powershell
python -B -m experiments.evaluator_development verify --fixtures experiments/evaluator_development/fixtures.json --out <new-round-directory> --label <round-label>
python -B -m experiments.evaluator_development verify --fixtures experiments/evaluator_development/fixtures.json --out <same-round-directory> --label <same-round-label> --resume --max-seconds 172800
```

172800 秒是预算上限，不是已经运行 48 小时的结果。源码或材料变化必须建新轮目录；已经完成的记录不可被覆盖，缓存和假传输不计真实重复。

```powershell
python -B -m experiments.construct_validity plan-judges --study <fixed-development-study> --judges <declared-local-judges.json> --repeats 3 --out <new-comparison-directory>
python -B -m experiments.construct_validity guard-comparison --input <identical-public-bundle.json> --out <new-result.json>
python -B -m experiments.construct_validity compare-objectives --input <candidates-with-evaluation-context.json> --out <new-result.json>
```

多目标公共入口重新计算候选的需求级可行性，不能由手填 SATISFIED 跳过必要条件。实际目标值/范围必须由输入提供，软件不创造科学性能。

专家入口：`review-export`、`review-import`、`review-extraction-import`。包绑定题干、答案、要求、来源、代码和裁判版本；未填写模板不计标签。专家一致性与正式科学比较留给用户，不填造统计。

开发计划、原始来源检查、逐轮失败和源码哈希分别见 `evaluator_development_plan_zh.md`、`evidence_source_checks_zh.md` 与开发运行工件。本次已获授权交付 GitHub 独立审核分支；人工审核入口见 oeq_review_20261005/README_zh.md。已有正式结果保留。