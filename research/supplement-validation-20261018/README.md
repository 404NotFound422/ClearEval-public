# ClearEval V1–V5补充实验：本地执行说明

[现在能运行什么／完整评分还缺什么／本地如何补齐](CURRENT_STATUS_zh.md) 汇总本轮修正、实际可用命令、缺失文件和下一步。

**现在能跑20组格式复现和19项工程测试。完整评分还需恢复必要资料、配置依赖、冻结正式输入manifest，并解除各模块的连带阻断。** 本目录同时提供V1至V5科学目标、规模、执行顺序与统计口径；完整实验尚未完成。

## 实验目标与数据规模

| 项目 | 规模/目标 | 当前状态 | 主要报告项 |
|---|---|---|---|
| V1 人机一致性与局部复核 | 历史20题×12答＝240对；新版6例14问 | 历史分析已有；新版单专家局部复核未回 | 保留旧量尺的分项关联、MAE/Bias及按题聚类区间；新版有序QWK/状态混淆按单专家局部复核口径单列，不估计专家间一致性 |
| V2 抽取与误差传播 | 原5开发＋15留出方案 | 暂停 | 不借其他工程测试宣称完成 |
| V3 定向行为 | 20基础＋78变体＝98输入 | 局部诊断已有；全量材料/专家关系未完成 | 预定方向关系、目标和非目标判项变化、UNKNOWN与失败；工程fixture不计科学样本 |
| V4 同证据对照 | 建议与V5共享20输入做direct/结构化配对 | 历史完成3题；新批次未执行 | 共享数值判项差异、一致率、槽状态及理由差异；不补造direct未输出的指标 |
| V5 同版重复 | 20固定输入×3次完整流程＝60执行 | 当前完整同版批次0/60 | 每题重复原值、均值/SD/极差（适用时）、槽/状态一致性、完整执行率和数值覆盖率 |

V3的78变体为20等义/格式、20遗漏、20关键错误、8合理替代、10证据不足。若采纳共享20输入的建议配置，V4结构化臂预先指定复用V5每题首遍，不增加执行数；另执行20个direct。V4原计划未独立锁定20题硬配额。历史v6、v8分批保留，不合并为本次60次。

## 建议执行顺序

1. 读 [完整实验计划](EXPERIMENT_PLAN_zh.md)，明确采用的样本、规则、版本与尚需研究者决定的事项。C20、P20、原B20不得混用。
2. 先按最新状态页的确切文件路径补齐运行依赖，修复各模块的结果/失败隔离，再以一次真实输入验收完整阶段、字段和raw保存。
3. 在看新分数前冻结样本/证据/provider、模型与编码器版本、prompt/rubric、统计和失败口径。V3预期关系不能由被测评分器自作gold。
4. 执行同版V5的20×3，并以指定首遍开展同证据V4；按冻结结构补齐V3。V1专家判断单独追踪，V2保持暂停。
5. 保存每次实际输入、请求/响应raw、版本、矩阵、判项、失败及重试关系。区分全流程完成、有限数值、合法UNKNOWN/N/A和技术失败，不能读分后改规则、扩样或覆盖失败。

完整Eff的四分量已有公式和主要数据；不能把全部null归因于专家未回。必须核对实际接线、标签口径、参考范围和缺项处理，详见计划第4节。有限诊断分不等于科学效度，合法UNKNOWN也不等于未执行。

## 样本与材料入口

- [C20候选v1](metadata/candidate20_manifest.json)：本批已验格式测试的固定输入来源。3 DEV、17 UNKNOWN，全部有来源审计曝光；不是冻结完整实验样本。只有10例涉及找到provider文件的方法，逐案例完整科学绑定仍未完成。
- [P20候选v3元数据](metadata/proposed20_v3_metadata.json)：20家族建议，iDISCO+ 16、FDISCO 2、MACS 2；9 DEV、11 UNKNOWN。含原公开记录路径/索引/hash、家族、曝光与缺口；未冻结、未审定科学适用性，不由格式脚本自动采用。
- [可复用资料索引](metadata/reusable_asset_index.json)：固定公开commit的资源路径/hash，以及已有操作参考的可用性边界。资料存在不等于题目证据已充分绑定。
- [历史报告索引](metadata/historical_report_index.json)：主稿、题答附件和B07补页的hash与范围；不以报告反造缺失raw。
- [状态摘要](STATUS_zh.md)和[机器可读状态](metadata/experiment_status.json)。

## 附属工具：现在可以直接运行的纯格式复现

详见 [本地安装、输出保存和故障续跑](LOCAL_EXECUTION_zh.md)。Python 3.10+，仅标准库，无账号、模型下载或网络依赖。

从本目录执行：

```sh
python3 -B scripts/reproduce.py
```

脚本从仓库固定公开源文件恢复C20原题原答，校验文件/记录/文本hash，然后构造20组LF空行变体。814条原行逐字不变，只新增172个LF。18格式回归＋6输入完整性测试通过；干净目录已复跑，逐组答案、变体与补丁hash全部一致。0 encoder、0 judge、0科学评分。

全部完整题答/变体与测试结果生成于被忽略的 `build/`；本批不再复制长篇源文本。`reports/expected_format_metrics.json`及实际日志提供工程基线；`PUBLICATION_MANIFEST.json`列出本批文件与来源hash。格式构造不表示科学正确性、专家gold、独立留出或V3整体完成。

## 附属工具：19项工程测试

进入 [runner_engineering_candidate](runner_engineering_candidate/README.md) 后运行：

```sh
python -S -B verify_package.py
python -S -B run_engineering_tests.py
```

CPython 3.12、仅标准库、无需模型。干净目录独立验收为16项纯scope回归＋3项包边界，共19/19；另2项来源依赖测试明确未运行。完整候选31/31属于另一验收范围。本包提供入口源码与工程测试所需依赖；`prepare/verify/execute`仅帮助页通过，正式评分依赖仍未齐。详见[缺项及准确附件成员](runner_engineering_candidate/MISSING_LOCAL_FILES.json)、[运行依赖拆分说明](runner_engineering_candidate/RUNTIME_GAP_AUDIT.md)、[独立验收报告](reports/PORTABLE_ENGINEERING_REVIEW_zh.md)。

## 发布边界

本次新增工程候选源码和明确通过的工程检查；完整科学运行仍待验收。包内不含模型权重/cache、论文全文、私有报告正文、完整原实验请求、账户信息或凭据；不运行GitHub Actions。原公开数据仅以固定commit路径和hash引用；公开可见不自动等于获得第三方再分发许可。无新license授予。自然答案是被评价对象，不是实验操作推荐。


## 发布快照与后续更新

`PUBLICATION_MANIFEST.json`保留为初次提交 `3bc06c6b5ffe0bd32ff6d25fc74d181442a5934a` 的24文件快照。校验该快照时应使用对应提交；本次README、CURRENT_STATUS与工程包增量由 `PUBLICATION_UPDATE_20261018.json` 另行记录，不回写旧快照或旧测试结果。初版STATUS和实验计划中的工程进度是当时快照，当前工程结果以CURRENT_STATUS为准。
