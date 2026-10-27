# ClearEval `final_candidate_v1` 复现与边界说明

## 当前状态

- 185 题、193 个预声明参考分支、17 项主指标、3145 行评分数据均保留。
- 本轮完整评分能力目标已经由实际表达到：`all_17_bounded=154`，上一轮为 153。
- 当前完整统一回归为 **64 passed in 1709.33s**；根目录完整性基线为 **37 passed in 1.43s**。
- 这是“阶段基线 + 148 两个已验证参考分支”的增量候选，**不是全 193 分支统一新后端重放，也不是 promoted 的原始 accepted 主表**。`scores185/summary.json` 继续保留 `current_accepted_main_table_updated=false`。
- 独立关闭复核已给出限定 **ACCEPT**，见 `acceptance/closure_review.md` 和 `acceptance/summary.json`。此前 `WITH FIXES` 报告和生成时的 PENDING 字段保留为历史，不单独代表当前验收状态。
- 工程可算性不等于专家正确性、评分有效性或发表就绪；这些未在本轮验证。

## 实际评分变化

| 项目 | 上一轮 `merge_stage1` | 本轮 `final_candidate_v1` |
|---|---:|---:|
| 完整点值或有界区间 `all_17_bounded` | 153 | **154** |
| 全部 17 项均为点值 `all_17_point` | 52 | **52** |
| 至少一项不可用 | 32 | **31** |
| `c_param` 不可用 | 7 | **6** |
| 正常管线分支 | 193 PASS | 193 PASS |
| 本轮重放 / 保留分支 | 14 / 179（上一轮修订时） | **2 / 191** |

只有 `EXPAND_148` 的 `c_param、Com、IA` 三个指标发生变化。其他答案的评分域和非本轮来源标记保持一致；191 个未重放分支的原始结果记录及 SHA 未改变。`reexecuted_in_latest_revision` 描述本轮执行，不会抹除上一轮修订历史。

`EXPAND_148` 两个参考分支都得到：

- `c_param = 2`，完整点值区间 `[2,2]`。
- 2018 分支：`Com=[0.5,0.8]`，`IA=[0.5,0.5977772491345605]`。
- 2019 分支：`Com=[0.4444444444444444,0.6499999999999999]`，`IA=[0.4444444444444444,0.5977772491345605]`。
- 答案级保留所有参考分支的外联合：`Com=[0.4444444444444444,0.8]`，`IA=[0.4444444444444444,0.5977772491345605]`。未按分数选择分支。

因此 148 从“含不可用”变为“完整但含区间”，**没有变成全点值题**。`c_param=2` 是原分级公式在完整补全域上的桶级不变量，不表示每个叶子都已判清；世界仍保留 `present/unresolved/denominator`，且 `unknown_items_filled=false`。`Com/IA` 的端点也未宣称可在同一世界联合达到，`joint_endpoint_attainability_certified=false`。

逐世界明细见 `validation148.json`；两分支数值和公式由 `validation/validate148.py` 实际重放验证。

## 真实评审与拒绝证据

本轮只消费 `parameter_scope148/actual_v2` 的七次真实本地评审：

- 模型 `qwen3.8:27b-q4_K_M`；digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`。
- seed `20261018`、temperature `0`、context `131072`；无自动重试、无截断回执被消费。
- 2018：34 个目标查询，3 批 `12+12+10`，4 个完整世界，槽数 `[34,33,33,32]`。
- 2019：39 个目标查询，4 批 `12+12+12+3`，6 个完整世界，槽数 `[37,36,36,36,35,35]`。
- 每批均为 `RESPONSE_TERMINAL`、`done_reason=stop`、`actual_judge_calls=1`；raw、request、response 和回执哈希已核对。
- 两分支有 30 个相同查询 ID，但目标 payload 不同。查询去重和回执合并按 `(input_id, branch)`/目标 payload 隔离，不能全局去重或跨分支共享。独立复核已验证跨分支输入会被拒绝。
- `accepted_v2` 的多来源消费、严格槽域、参数 apply 和原生图重放通过；随后 `normal_v2` 才完成两个正常管线分支。

`actual_v1` 因 `json.dumps(..., flush=True)` 驱动错误在首次模型调用前停止：`actual_judge_calls=0`，其输出未被消费。`preparation_v2`、`preparation_v3` 和 `parameter_scope148/INVALIDATION.json` 所列旧准备同样未用于评分。上述文件保留原样，未通过编辑原始回执制造合格证据。

`accepted_v2` 内的 `full_normal_pipeline_executed=false`、`accepted_for_scoring=false` 是生成该包时的状态；后续验收来自 `normal_v2`、正式合并及本轮回归，而不是回写旧包。`actual_v2/execution.json` 的 `ALL_BATCHES_TERMINAL_NOT_CONSUMED` 同样是消费前状态。

本轮后续离线重放、合并、汇总及验证脚本没有新的评分模型或编码器调用。独立代码审查使用 DeepSeek Flash，与评分调用分开计数。

## 合并与代码迁移

`apply_common_source_revisions_v4.py` 只接受预声明的 `(input_id, branch)` 和指标闭包。148 的允许闭包为 `c_param → Com → IA`，其他叶指标、Co、Eff 和 EA 数值域不变。

基线 6579 个 pin 中只有以下代码文件不同：

```text
parameter_route_role_scope_v1/recipe_scope.py
before bf83359be7a40e994c520285627ac23c4c1b1dcb4a3cb6d72915a9338c27cd20
after  bff81712540fdec2730e6558b8086f4412bf7cc2641bebddc95004923d03b5c9
```

`affected148.json` 显式声明这一迁移。合并器要求：基线 pin 等于 before、当前文件等于 after、`preparation_v5` 和 `accepted_v2` 的支持 pin 等于 after、正式回放的 loaded-code pin 也等于 after。其余 6578 个 pin 逐项原样校验。未声明、前后哈希不符、支持证据缺失或冲突声明都会失败。

没有改写旧基线、临时回退代码或忽略哈希。`apply_common_source_revisions_v3.py` 保持历史版本，SHA256 为：

```text
c6da151fdcb04435ab30a659684edc17af32497d046cec87651bc82a00cb4c36
```

`review_snapshot_v1/recipe_scope.py` 与上述基线 before 不同，未被冒充为旧版证据。

## 验收证据

- `normal_v2/summary.json`：两分支 PASS，零新增评分/编码器调用。
- `merged193/summary.json`：193 PASS，2 个重放、191 个保留。
- `scores185/summary.json`、`rows185.json`、`metrics3145.csv`：主评分表及实际计数。
- `ea185/`：独立 EA 表；未将 EA 混入 17 项主指标，也未替换 Bio-SR/SP。
- `validation148.json`：EA 五元输入、实际 callable/runtime、纯结果哈希、诊断差异来源、Com/IA 原公式及参数世界语义。
- `remaining/` 与 `remaining_reasons.json`：剩余 NA、原始原因、结果路径和 SHA。
- `full_regression_current.log`：当前代码 **64 passed**；`test_collection_current.log`：**64 tests collected**。
- `integrity_current.log`：**37 passed**。
- `run42_ea_equivalence_test_v2.log`（位于 `parameter_scope148/`）：148 正常管线集成测试通过。
- `run42_focused_v2.log`：5 项 focused 测试通过。
- `code_migration_unit_green_v3.log`：迁移与六条负控制通过。
- `code_migration_integration_v1.log`：真实 193 分支合并测试通过。
- `deepseek_v41_flash_final_review.md`：独立数值/来源审查的原始 `WITH FIXES` 结论，未直接改成 ACCEPT。
- `acceptance/evidence.json`、`acceptance/input_and_code_sha256.json`：将“参数评审旧门槛”与“最终代码新门槛”分开，并包含支持清单自身、公式/EA 证据及新回归日志。生成时共 6838 条 pin，已逐条重算。

`validation148.json` 中的 `SEPARATE_PENDING_GATE_AT_GENERATION` 记录其生成时状态；后续完整回归及独立关闭复核以 `acceptance/` 为准。

`differences_from_accepted_snapshot.json` 比较的是原始 benchmark snapshot，**不是本轮相对 `merge_stage1` 的差异清单**。本轮变化应看 `rows185.json` 与 `merged193/execution_provenance193.json`。

## 复现命令

在 Git Bash 中使用已有 Python，不安装新依赖。以下输出使用新目录；不要覆盖历史回答、参考、raw response、旧主表或本轮证据。

```bash
R=C:/ClearEval/ClearEval-runtime-4b42b5a
H="$R/research/evaluator-research-cycle-20261018"
E="$H/execution_alignment_resolution_20261024_v1"
O=C:/ClearEval/deliverables/cleareval_repair_20261025_232451
PY=/c/ProgramData/anaconda3/python.exe
NORMAL="$O/parameter_scope148/normal_replay_v2"
OUT="$O/final_candidate_replay_v1"
test ! -e "$NORMAL" && test ! -e "$OUT"
cd "$H"

# 两个分支的正常管线；消费已验证回执，不重新调用评分模型。
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$E/runtime/uniform_normal_runner_v1/run_v42.py" \
  --ids EXPAND_148 --output "$NORMAL"

# 只合并预声明的148两分支及其c_param/Com/IA闭包。
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$E/runtime/apply_common_source_revisions_v4.py" \
  --base "$O/merge_stage1/merged193_v4" \
  --output "$OUT/merged193" \
  --affected-plan "$O/final_candidate_v1/affected148.json" \
  --revision-root "$NORMAL"

# 主表、独立EA表、剩余NA。
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$E/runtime/collect_uniform_normal185_v5.py" \
  --input-root "$OUT/merged193" --output "$OUT/scores185"
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$E/runtime/collect_execution_alignment185_v1.py" \
  --input-root "$OUT/merged193" --output "$OUT/ea185"
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$E/runtime/export_remaining_cases_v1.py" \
  --table "$OUT/scores185" --normal-root "$OUT/merged193" --output "$OUT/remaining"

# 独立重放148的EA与聚合证明。
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B "$O/final_candidate_v1/validation/validate148.py" \
  --output "$OUT/validation148.json"

# 当前完整回归（在H下运行）与完整性基线（在R下运行）。
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B -m pytest "$R/tests/test_uniform_normal_repairs.py" -q
cd "$R"
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
  "$PY" -X utf8 -B -m pytest tests/test_evaluator_integrity.py -q
```

`run_v42` 的评审根固定为已验证的 `accepted_v2`；不要把未经同样验收的新目录直接替换为评分证据。`actual_v2 --execute` 不应在已有输出上重跑；如需全新模型评审，必须新建计划、目录和授权，而不是覆盖现有回执。

## 剩余 NA 与后续工作

`remaining/summary.json` 当前为：52 题全点值、102 题完整但含区间、31 题含不可用。`remaining_reasons.json` 按题去重并保留 46 个缺失叶分支记录。

- `c_param` 6 题：012、015、024、130、161、184。保留 `PARAMETER_NOT_JUDGED_IN_SOURCE_BOUND_PARTIAL_CRITERIA` 与 `FIXED_SLOT_RULE` 的原始分支原因；不完整世界不得生成点值。
- `s_time` 25 题：13 个 `NOMINAL_TIME_HAS_UNRESOLVED_SOURCE_ROWS`、11 个 `EXACT_METHOD_TIER_ROW_NOT_UNIQUE`、1 个 `AT_LEAST_ONE_FINITE_SOURCE_WORLD_NOT_SCORABLE`。开放保存、直至透明、必要延长、未写配液时长和对象不唯一均不编造标准时长。
- Bio-SR/SP 各 2 题、ClearEval coverage/SP 各 2 题：012、015 的原始通道和写入分支域尚未完整可评分，不能伪装成科学零分。
- `s_label` 3 个叶分支：012、102、103。原始 `native_detail` 保留未解决的适用标签组成项；102/103 包括 `method_fluor_compatibility`。
- `co_order` 1 个叶分支：012 的原始评审指出多个替代序列、没有确定的最终工作流，不能臆造顺序分数。

其中 4 个叶节点的顶层 `reason` 为空（012 的 `co_order` 和 `s_label`，102/103 的 `s_label`），`remaining_reasons.json` 明确标记该事实，并保留其嵌套原始评审/assessment 证据；这不是“已证明无法修复”的声明。

下一轮优先顺序：先审计其余参数世界与原始通道，再处理 TIME 的来源行/方法唯一性，随后核查标签组成项和步骤域。只有完整来源域、真实评审和正常回放均成立时才增加数值。

可复用的工程候选包括：延迟变体的来源证据图、跨来源完整查询分区、可逆 JSON/来源绑定、显式代码迁移证明。它们在 148 上得到工程验证，但尚未形成独立对照下的创新性评分有效性结论。多参考区间端点的联合可达性仍是未验证研究方向，不能为缩窄区间而宣称已经证明。

未提交 git commit，未新增依赖，未修改原始回答、参考原文、raw response 或旧主表。
