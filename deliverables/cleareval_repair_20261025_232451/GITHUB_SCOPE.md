# 本轮 GitHub 交付范围

## 用途

本目录用于共享 ClearEval 本轮代码、实际评分表和可审查证据，不是一个脱离原冻结环境即可重跑全部流程的独立运行包。

实际结果为：185 题、193 个参考分支、3145 行主指标；`all_17_bounded=154`、`all_17_point=52`、31 题含 NA、`c_param` 6 题不可用。148 两个参考分支的 `c_param=2`、`[2,2]`。这些数值表示工程可算性，不表示专家正确性或发表就绪，也没有把原始 accepted 主表标记为已更新。

## 包含

- `final_candidate_v1/`：完整 53 文件交付目录，包括主评分表、独立 EA 表、剩余 NA、复现说明、独立审查、验收摘要及总 manifest。
- `parameter_scope148/actual_v2/`：七次真实本地评审的请求、原始响应和回执；无自动重试。
- `parameter_scope148/plan_v1/`：两分支完整查询分区、包装请求及子集证明。
- `parameter_scope148/accepted_v2/`：汇总、来源合并证明、review_sources 和输入/代码 pin；不包含大型参数图文件。
- `parameter_scope148/normal_v2/`：两个正式分支的执行摘要、记录和代码/输入 pin；不包含大型完整结果图。
- `merge_stage1/`：上一轮评分表及合并基线的必要记录与 pin。
- `review_snapshot_v1/`：参数评审时的独立审查、旧回归日志及快照清单。
- 失败/拒绝证据：`actual_v1`、旧准备的 `INVALIDATION.json`。
- 本目录外、按原相对路径暂存的本轮代码：`parameter_operation_variant_scope_v1`、`parameter_private_reference_scope_v1`、`parameter_cubic_route_scope_v1`、`parameter_joint_reference_scope_v1`、`parameter_route_role_scope_v1/recipe_scope.py`、`runtime` 的 148 准备/消费/component40/run_v42/apply_v4，以及 `tests/test_uniform_normal_repairs.py` 和本轮计划文档。

## 未包含

- 工作区中约 182488 个未跟踪的历史实验文件、其他研究目录、缓存和本地 `.superpowers/` 状态。
- `accepted_v2` 约 330 MB 的完整包、`normal_v2` 约 219 MB 的完整输出，以及 `preparation_v5` 约 60 MB 的完整准备目录。只保留上述较小的审计证据和 pin。
- 原始回答、参考原文和旧主表的任何改写；没有通过排除这些文件来修改其内容。

这些排除是发布范围限制，不是对本地原始文件的删除或缩减。大型原始结果仍保留在原工作区。

## 复现边界

代码和证据中的绝对路径、哈希及来源引用均按原环境保留，没有为了上传而重写：

- `C:/ClearEval/ClearEval-runtime-4b42b5a`
- `C:/ClearEval/deliverables/cleareval_repair_20261025_232451`

完整重放仍需要原冻结工作区、原始回答/参考、基线完整结果、完整参数包和准备输入。仅凭本 GitHub 目录不能重跑全部 64 项测试或重新生成 154 题结果；也不应把缺失大型输入解释为评分失败。

原环境中的验证为：统一回归 64 passed、完整性基线 37 passed、DeepSeek 限定 ACCEPT。测试并非在上传裁剪后的目录中重新执行。`final_candidate_v1/manifest.json` 可用于核对交付目录内部 53 个文件的字节一致性；指向外部原始环境的 pin 仍需在原环境中验证。

## 结果语义

- `c_param=2` 是完整补全外域上的分级桶不变量，不代表所有叶子都已判清。
- Com/IA 为保留所有参考分支的外界区间，未证明端点在同一世界联合可达。
- 未使用 0、均值、满分或全量程区间伪造数值。
- 本轮是基线加两个已验证分支的增量候选，不是全 193 统一新后端重放，也不是 promoted 主表。
