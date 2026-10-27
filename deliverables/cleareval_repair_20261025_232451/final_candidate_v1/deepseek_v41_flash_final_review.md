# 第五次独立只读复审：148 真实评分结果与最终候选表

**结论：WITH FIXES（工程上可计算性通过；作为最终候选仍需补齐全量回归证据）。**
没有 Critical；属于 Important 的只有一项证据门槛问题（全量当前回归尚未完成，且被 pin 的 54 项日志早于本轮新增的 run_v42/entry40/apply_v4）。其余为 Minor。专家正确性未评估；真实 NA 仍然存在。

边界：未修改文件、未调用模型/编码器、未做 git 变更、未重复运行完整 pytest；仅做只读 JSON/hash 核验、小范围重算与独立重放。

---

## Strengths（独立复现，不引用自述）

1. **计数独立成立。** `scores185/rows185.json` 重算：185 答案、193 分支、17 指标，状态 `COMPLETE_POINT=52`、`COMPLETE_WITH_INTERVALS=102`、`HAS_UNAVAILABLE=31` → bounded **154**（基线 153），point **52**；`metrics3145.csv` 为 3146 行（表头+3145）。与基线逐答案比较，**唯一改变状态的答案是 EXPAND_148**（`HAS_UNAVAILABLE → COMPLETE_WITH_INTERVALS`）；`c_param` 由 7 不可用降为 6（`015,012,024,184,161,130`），`Com` 7→6、`IA` 31→30，其余指标可用性分布不变。没有第二个答案被顺带“点亮”。
2. **148 数值域可复算。** 两分支 `c_param=2`、`[2,2]`；答案级 `Com=[0.4444444444444444,0.8]`（分支 `[0.5,0.8]`、`[0.4444,0.65]`）、`IA=[0.4444444444444444,0.5977772491345605]`（分支 `[0.5,0.5977]`、`[0.4444,0.5977]`）、`Eff=0.5977772491345605`、`Co=1.0`。我用 `aggregate_score_bounds_v3.evaluate(components, certificates, protocol_sha256)` 独立重算：Com/IA/Eff 与存档完全相等；Co 数值 1.0 相等（v3 仅多补 `bounds/interval_policy` 字段）。其余 14 个节点与基线逐值相同。
3. **真实回执链完整、严格、可重放。** 7 个批次（3+4），块大小 `[12,12,10]`、`[12,12,12,3]`，`qwen3.8:27b-q4_K_M`、seed 20261018、temperature 0、num_ctx 131072；每批 `actual_judge_calls=1`、`RESPONSE_TERMINAL`、`automatic_retries=0`、`done_reason='stop'`、`raw.txt == message.content`、review 键集合恰等于该块查询集合。我用 `reader.audit(target, sources)` 对两分支各重放一次：3/4 origins、34/39 查询、`ALL_TARGET_QUERIES_SOURCE_BOUND`，且 `target_response` 与 packet 完全一致。
4. **分支隔离成立。** 两分支 34/39 查询中 **30 个 query id 重合**，但目标 payload 不同；把 A 分支的 origins 用于 B 分支目标会被拒绝（`TARGET_QUERY_SUBSET_INCOMPLETE`），消费按 `(input_id, branch)`/目标 payload 进行，没有全局去重或共享回执。
5. **严格槽域与原生重放成立。** 10 个世界 `strict_slots_all_valid=True`；世界槽数 2018 `34/33/33/32`、2019 `37/36/36/36/35/35`；每世界 reviews 覆盖全部 slot。我独立重跑 `entry.parameter.revalidate_parameter_graph(result, case, source, request)`（2018）：component 与存档一致、`[2,2]`、native 重放通过。
6. **编号迁移是显式且不可任意绕过。** 基线 6579 个 pin：0 缺失、**恰好 1 个变化**（`recipe_scope.py`，`bf83359b… → bff81712…`），其余 6578 个与当前文件逐字节一致。after 哈希同时出现在 `preparation_v5`(312 pins)、`accepted_v2`(432)、`normal_v2/loaded_code_sha256.json`(622) 与 `merged193`(6601 pins，全部匹配当前文件)。`resolve_prior_pins` 强制 `before==基线 pin`、`sha(path)==after`、每份 supporting pin 与每个 root 的 `loaded_code_sha256.json` 一致（`apply_common_source_revisions_v4.py:76-96`）；测试对 6 类反例逐一要求精确错误码（`test_revision_code_migration_requires_matching_evidence_pins`），集成测试重跑合并并断言 191 行不变、仅两分支节点变化为 `[Com, IA, c_param]`。
7. **合并是增量而非全量重算。** 193 条记录中恰好 2 条 `result_sha256` 被替换（148 两分支，指向 `normal_v2`），191 条保留且 sha 不变（`merged193/execution_provenance193.json`：2 reexecuted / 191 retained）。`validate` 对 14 个独立指标逐项要求与基线相等，`shared_source_exact=True`，`case` 仅 `reference.file.path` 不同（file sha 相等），`request/execution_scope` 逐值相同。
8. **未把 EA 混入 17 指标。** `METRICS` 恰为 17 项，`rows185` 无 `label_review`、无 `ea_*`；EA 独立表可用性与基线完全相同（`ea_r 2/98/85`、`ea_p 2/100/83`、`ea_f1 2/92/91`），148 的 EA 行逐值不变。`test_run42…` 的 EA 容忍项仅为：新增 carrier 三字段、`original_repeated_container_references`、`internal_prior_issued_plan_entries`（均整数诊断），同时强制五元输入 digest、逐字段 digest、纯结果 digest、`ea_identity`、原 callable/runtime、carrier 不变量与 Co/Eff 相等。
9. **候选表自我标注正确。** `scores185/summary.json`：`current_accepted_main_table_updated=false`、`new_model_calls=0`、`expert_accuracy_or_publication_readiness_evaluated=false`；`scores185/manifest.json` 6/6 校验通过；`scores185/input_sha256.json` 198 pins 全部匹配；`merged193` 6601 pins 全部匹配。

---

## Critical

无。

## Important

**I-1 最终代码的全量回归门槛尚未闭合，且被 pin 的“54 passed”日志早于本轮新代码。**
- 证据：`review_snapshot_v1/full_regression54.log` 为 112 字节，mtime **23:10**；`run_v42.py` 23:44、`component_entry_v40.py` 23:51、`apply_common_source_revisions_v4.py` 与测试文件 10:25。该日志不可能覆盖这些文件。
- 但 `consume_parameter_reference_scope_v1.py:203-208` 把这份 54 日志与 `deepseek_v41_flash_review_v4.md` 一起 pin 进 `accepted_v2/input_and_code_sha256.json`，作为“已通过完整回归”的授权证据；这只对参数评审时的代码状态成立（参数模块 ≤22:49、planner 22:47，日志 23:10 覆盖），对最终合并代码不成立。
- 本轮新代码的专项证据是有的：`test_run42_full_normal148_scores_and_invariants` 日志 10:01（396s，晚于 run_v42/entry40），代码迁移单测 10:25、集成 10:27，`integrity_current.log` 10:38 显示 **37 passed**；但 `full_regression_current.log` 在我复核时只有 **12 个点**（进行中），没有最终结果。
- 影响：数值本身已被我独立复算并通过，故这不是评分错误，而是**证据门槛标注过强**：候选表被 pin 的“完整回归”不是最终代码的完整回归。
- 最小修复：在**当前最终代码**上跑完全量套件，落盘并 pin 新日志（替换或并列 54 日志），在 `merged193/scores185` 的输入 pins 中显式区分“参数评审门槛日志”和“最终代码全量回归日志”；未完成前不得把该表称为 final/promoted。

> 说明：若按项目“先全量回归、再真实评审/合并”的字面门槛，本项即构成“尚不可作为最终候选”；若仅判断数值与证据链是否可算、可复核，则已通过。

## Minor

1. **c_param=2 是“桶级不变量”，不是叶子全解析点。** 每世界 `present/unresolved` 为 2018 `21/3`（n=34）、2019 `24/1`（n=37）；`point_invariant_over_outer_set=True` 但 `bounds_endpoints_jointly_source_certified=False`、`unknown_items_filled=False`。即按原始分级公式在所有补全上取值为 2（`CORE_SHA` 固定），并非 34 个叶子都判清。引用 `c_param=2` 时应同时给出 `present/unresolved/denominator`，不要写成“全部判定完成”。
2. **Com/IA 是多分支外联合凸包，不是单世界可达端点。** 148 的分支区间分别为 Com `[0.5,0.8]`/`[0.4444,0.65]`、IA `[0.5,0.5977]`/`[0.4444,0.5977]`，答案级取 `min/max`；`joint_endpoint_attainability_certified=False`。不要表述为“同一世界同时达到 0.444 与 0.8”。
3. **`differences_from_accepted_snapshot.json` 的“accepted snapshot”是原始基准快照，不是 `merge_stage1` 阶段表。** 它列出 689 条相对原始快照的差异（`collect_uniform_normal185_v5.py:127-128` 指向 `current_benchmark185_uniform_bio_parameter2_20261025_v1`），容易被误读为本轮漂移；本轮漂移的权威证据是 rows 级 sha 与 `execution_provenance193.json`（2/191）。建议改名或加字段说明。
4. **合并 pins 未包含 loaded-code/support 清单文件本身。** `resolve_prior_pins` 读取 `preparation_v5/input_and_code_sha256.json`、`accepted_v2/input_and_code_sha256.json` 与各 root 的 `loaded_code_sha256.json`，但只把**其中列出的路径**加入 `pins`，清单文件自身未入 pin；`consume_parameter_reference_scope_v1.py` 只出现在 `accepted_v2` 的 432 pins 中，不在 `normal_v2/loaded_code` 与 `merged193` pins 中（它不参与 run_v42 的 normal 路径，故合理，但应写明）。风险有限：未声明修订的文件必须与基线逐字节一致，且 result 可原生重放；建议把三份清单文件本身也 pin 上。
5. **EA 容忍的两个整数诊断没有对应证据工件。** `original_repeated_container_references` 与 `internal_prior_issued_plan_entries` 只断言“整数且 ≥0”后剔除，没有 pin 的证明说明为何变化；由于五元输入 digest、逐字段 digest、纯结果 digest 都被强制，它们无法改变 EA 数值，但建议在回执里加一项 `diagnostic_provenance` 说明来源，避免被读成任意豁免。
6. **`full_regression54.log` 只有 112 字节**（仅一行 `54 passed`），作为授权证据信息量过低；应保留 pytest 完整输出或至少 `--durations`/收集列表，防止“日志内容与代码状态”不可比对。
7. **30 个重合 query id 的隔离目前靠“每分支独立 target + payload sha”保证**，已验证跨分支复用会被拒；建议在 `consume_parameter_reference_scope_v1` 或 `reader` 中加一条显式断言（origin 的 target payload sha 必须属于本分支 target），把“不得全局去重”写成代码而不是依赖调用顺序。

---

## 独立计数与来源/数值域核验

| 项 | 独立结果 | 与自述一致性 |
|---|---|---|
| 答案/分支/行 | 185 / 193 / 3145（csv 3146 行含表头） | 一致 |
| all_17_point | 52 | 一致 |
| all_17_bounded | 154（基线 153，增量恰为 `EXPAND_148`） | 一致 |
| 含 NA 答案 | 31（基线 32） | 一致 |
| c_param 不可用 | 6（015,012,024,184,161,130） | 一致 |
| 148 c_param | 两分支 `[2,2]`，点 2 | 一致 |
| 148 Com / IA | `[0.4444,0.8]` / `[0.4444,0.5977]` | 一致 |
| 148 其他 14 节点 | 与基线逐值相同 | 一致 |
| 批次/查询 | 7 批，`[12,12,10]`+`[12,12,12,3]`，34/39 唯一查询 | 一致 |
| 回执设置 | qwen3.8:27b-q4_K_M / 20261018 / 0 / 131072，0 重试，`stop`，raw==content | 一致 |
| 世界 | 4 + 6，槽数 `34/33/33/32`、`37/36/36/36/35/35`，10/10 strict | 一致 |
| 代码迁移 | 6579 基线 pin 仅 1 变化；before/after 与 v5/accepted_v2/normal_v2/merged 全部一致 | 一致 |
| 合并 | 193 记录，2 替换、191 保留；独立指标 14 项逐值不变；变化节点 `[c_param,Com,IA]` | 一致 |
| 组合版本 | 17 种，v40 仅 2 分支；parameter_basis 170 archived + 15 current | 支持“非统一后端” |

**来源/数值域：** 148 的输入 `case/execution_scope/request` 与基线逐值相同（仅 `reference.file.path` 不同、file sha 相同）；回执由独立 `reader.audit` 重放且 target_response 逐值一致；`c_param` 由 10 个世界的原始分级公式在补全外层集合上取不变量；`Com/IA` 由原公式重算一致；`Co/Eff` 与 14 个独立节点未变；没有 0/均值/满分/全量程填充（Com `[0.444,0.8]`、IA `[0.444,0.598]` 均非全量程，EA 也未变）。

---

## Verdict

**WITH FIXES。**

- **工程可计算性：通过。** 154/52/31/6、148 的 `[2,2]`、Com/IA、7 个回执、分支隔离、严格槽域、原生重放、双账本/节点守恒、编号迁移与 191 行保留，均已独立复现；未发现会少评、错父操作、丢世界、错误接受不完整回执或无法消费的路径。
- **专家正确性：未评估，也不应据此宣称。** 该表是可用性/可算性候选，不是专家准确率或发表就绪证明。
- **真实 NA 仍在：** 31 个答案至少一项不可用；`c_param` 6、`s_time` 25、coverage/sp 各 2、bio_sr/bio_sp 各 2、`s_label` 3、`co_order` 1。没有任何一项被 0/均值/满分补齐。
- **最终候选资格：** 数值与证据链可以支持“增量候选”（基线 191 + 经验证 2 分支，非全 193 统一新后端）；但项目门槛要求的“当前最终代码全量回归”尚未完成（日志仅部分点），且被 pin 的 54 日志早于 run_v42/entry40/apply_v4。完成全量回归并把新日志与公式/EA 证据一起 pin 后，可将结论升级为 ACCEPT；在此之前，只能作为**待门槛闭合的候选**，不应写入主表或宣称最终。
