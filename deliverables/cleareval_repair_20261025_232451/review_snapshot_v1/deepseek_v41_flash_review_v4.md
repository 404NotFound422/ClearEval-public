# DeepSeek V4.1 Flash 第四次独立复审（只读）

**结论：ACCEPT**（仅指 `preparation_v5` + `plan_v1` 可进入真实本地模型评审；不宣称分数、真实回执、完整消费或完整 54 项回归已验证）。
未修改文件，未调用评分模型，未执行任何批次；真实模型调用仍为 0。

## 本次实测哈希（manifest 旧值不作依据）

```
0c4446f20d8f36ce09c92af9559181f287125612cdc2aaf1a2d031af7841ceb2  parameter_private_reference_scope_v1/units.py
499add8a6f02d4c26e1cd4cddde22ddd182e20cf32735d1f96e65793136275de  parameter_private_reference_scope_v1/rebind.py
acbb34fac77327510dabe6c8b201c301372e3095d3aa083c42db53f08466e4b3  parameter_operation_variant_scope_v1/apply.py
9da78f08e63b34d28b6b5d441bd3f07397ea0d93e9aef044eae2cfb416a29a79  parameter_cubic_route_scope_v1/apply.py
457a0461476c93d1b23209fb547b3f5fe28010b3bd4ae0b2740e78145f823ab5  parameter_joint_reference_scope_v1/normal_candidate.py
5724dc57bbe6b61a55f291000d7a799e578b3a5983eb16d7e6592a142ea78e23  runtime/prepare_parameter_reference_scope_v1.py
```

## 已独立验证的事实

1. **依赖 pin：312/312 通过。** `preparation_v5/input_and_code_sha256.json` 全部 312 条按当前文件重算 SHA256 一致（0 缺失、0 不符）；`preparation_v5/manifest.json` 12/12 一致。六个实现文件都在 pin 内，且与上表哈希一致。
2. **C-1 已关闭：v5 由冻结代码可复现。** `runtime/prepare_parameter_reference_scope_v1.verify_plan()` 在两分支上实跑通过；它内部重跑 `joint.prepare` 并断言 `fresh == source_dir/prepared_parameter.json`，同时校验归档回答 pin、协议一致、目标请求 sha 与分区。
3. **分块计划完整且防篡改。** 2018：34 查询 → `[12,12,10]`，4 世界；2019：39 查询 → `[12,12,12,3]`，6 世界；合计 7 个计划批次，`new_model_calls=0`。`verify_plan` 断言分块互斥且按序覆盖全部目标查询、每块 ≤12 且 `denominator==len(ids)`、每块是目标请求的精确子集并有独立 subset proof、块请求与 proof 均被 pin。三种只读篡改模拟均被拒绝：请求文件哈希变化、块少一个查询、计划被截掉一个批次且自洽改写计数。恢复后 verify_plan 仍通过。
4. **入参与 v4/基线逐值相同。** `case.json`、`execution_scope.json`、`request.json` 在两分支与 `parameter_remaining/EXPAND_148` 及 `preparation_v4` 解析后完全相等（字节差异仅为序列化）；`prepared_parameter.json` 的 `requests` 与 v4 相等，binding/world_plan 因新增 `applicability_basis`、`private_typed_rebind.status`、marker 字段而变化，属预期。
5. **REQUIRED 优先级已关闭。** `operation_variants/apply.py:44` 现为 `elif disposition=='REQUIRED_FOR_ACTUAL_DECLARED_DILUTION' or DILUTION.search(reference.operation)`。函数级复现：`disposition=REQUIRED` + 参考文本仅为 `Immerse in 1:1 CUBIC-R at room temperature.` → required conditional 包含 `C18:HALF_R:concentration:transition_dilution`、conditional=[]、basis=ACTUAL_FORMULATION_APPLICABILITY_AUDIT；NOT_AN_ACTUAL 仍排除；无裁定且参考文本含 dilution 时仍保留。
6. **缓存重放与伪造拒绝已关闭。** 合法 `units.project(projected)` 返回同一对象语义、proofs 完全相同（6 份）。改投影前身份、行 `comparison_phase`、成员私有证明，各自重算私有摘要后仍全部抛 `PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED`。无 marker 时为 UNRESOLVED、INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE、queries=0；无 marker 且删除全部私有字段仍被 CUBIC 幂等早退前的 proof 覆盖门禁拒绝。
7. **缓存重入不增世界、且按当前裁定重算。** 2018：`variants.apply(fresh.binding)` 返回同一对象，4 世界、`[34,33,33,32]` 不变；2019：6 世界、`[37,36,36,36,35,35]` 不变。注入 `afa=NOT_AN_ACTUAL...` 后重建仍 4 世界、分母 `[33,32,33,32]`、R017 稀释槽 `[1,0,1,0]`、basis 全为 ACTUAL_FORMULATION_APPLICABILITY_AUDIT，未出现 16 世界式笛卡尔膨胀。缓存域不完整或重复均失败关闭。
8. **v5 准备包内容独立复核。** 2018：PREPARED，4 世界，分母 `[34,33,33,32]`，34 去重查询；ledger 21/covered 21/conditional 0/missing 0/criterion 不一致 0；每世界 slot 与 query 同集且 query id 均存在；rebind=COMPLETE，proofs 6；cubic/variant 均 COMPLETE；basis 全为 REFERENCE_REQUIRED_PROCEDURE_SPECIFICATION。2019：PREPARED，6 世界，分母 `[37,36,36,36,35,35]`，39 去重查询；28/28 覆盖、0 缺失、0 criterion 不一致。half-R 稀释细项只出现在 HALF_R 世界，required conditional id 指向 original_slot_ids，并记录参考原文；148 没有已批准的实际配方豁免。
9. **消费接口结构上可承接 7 个分块回执（未执行）。** `parameter_atomic_multisource_v1.reader.audit()` 以完整目标请求为 target，逐来源校验 subset 证明并要求目标查询全覆盖，冲突观测拒绝；partial origin 要求单次已保存调用、无重试、raw 与 response 一致、物理请求与 wrapped 相符。`parameter_atomic_multisource_v2/normal_adapter.py` 是分块回执→完整目标→既有 hybrid 消费的入口。以上仅为代码契约核验，没有真实回执，不能写成已验证。

## Critical

无。

## Important

无。

## Minor

1. **投影前注解型重放仍被拒（fail-closed，未被管线使用）。** 若 projected 源携带投影前计算的 `explicit_operation_source_projection`，再次 `units.project` 会因投影后重算注解不一致而失败；投影后再注解的顺序可重放。当前管线不持久化 projected 源，不影响 v5；若将来引入持久化，建议将注解与 projection_input_rows 一起纳入 marker，或用投影输入行重算注解。
2. **`cached_complete` 不比对观测变体域与当前候选域。** `assigned()` 只校验既有 receipt 与当前裁定一致，随后可直接返回旧世界集；若未来规则新增变体，可能保留较小世界集。建议要求观测 choice_domains 等于当前 candidates 的参考集合，否则重建。
3. **分组重建以 `group[0]` 为基世界。** 分组键为 execution_assignments+units；若同组世界在 gaps/slots 上另有差异会被首个世界覆盖。148 无此情形，可加组内一致性断言。
4. **`verify_plan` 要求 `reused_reviews==[]`。** 若将来出现合法缓存命中，计划会被判不合格。这是本轮强制新调用的策略，应显式记录，而不是当作通用缓存规则。
5. **分块回执的消费策略需按块声明且两种合同相反。** legacy consume 要求 generation_completed_without_truncation，而 validate_partial_origin 要求 done_reason=='length' 且 done=True。计划本身不记录每块将按 FULL 还是 partial 声明。错声明会 fail-closed；首批真实调用后应把每块实际策略写入回执清单再消费。
6. 既有小项仍未消失：`apply_typed` 覆盖 `primary_medium_proof['basis']`；闭包断言只是无闭包而非模块级；2019 稀释出处措辞与 2018 不同；测试的具体分母/世界数仅为回归钉，不是正确性证据。

## Assessment

- 第三次报告的 C-1 与 Important 均已关闭，并有可复现证据：v5 由冻结代码逐值复现且 312 个依赖 pin 全部一致；分块计划互斥、完整、按序覆盖 34/39 查询且有逐块 subset proof 与请求 pin；REQUIRED 情形无条件保留必评细项；缓存重放/伪造/旁路/重入/域不完整/重复世界均按预期接受或失败关闭；148 两支的 4/6 世界、分母、双账本覆盖、原始 criterion、half-R 条件项出处与最终审计状态均实测成立。
- 未发现会导致少评、错父操作、丢世界、不完整回执被接受或无法消费的 Critical/Important。Minor 1/2/3 建议后续加固，但不构成进入真实评审的阻断。
- **未验证项（不得写成已验证）**：真实模型回执、批次终止性、消费/apply/revalidate 全链、`c_param` 数值或 `all_17_*` 变化、完整 54 项回归。
- 进入真实评审的操作前提：只用 `preparation_v5` + `plan_v1`，按 `plan_v1/<branch>/plan.json` 的 7 个批次逐块执行，回执按实际终止状态声明 FULL/partial 后再消费；任何截断/异常回执按原策略隔离，不放宽槽域或来源校验。

---

主线程说明：此报告由只读 DeepSeek Flash 复审角色返回，主线程保存。完整回归在主线程单独执行，真实评审须同时满足该门槛。
