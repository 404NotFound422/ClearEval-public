# 第六次独立门槛关闭复核（只读）

**Verdict: ACCEPT** —— 仅指工程增量候选（185 答案 / 193 分支 / 3145 行，基线 191 + 经验证 2 分支）。不是专家正确性、不是全 193 统一新后端、不是 promoted、不是主表已更新。

我上次唯一的 Important（I-1：最终代码全量回归未完成、旧 54 日志不能代表最终代码）**已关闭**；未发现新的 Critical/Important。

## 1) 实测检查

**I-1 时间线闭合**
- `full_regression_current.log`：mtime **11:06**，首行 **64 个点**，末行 `64 passed in 1709.33s`（约 10:37 起跑）。
- `test_collection_current.log`：10:56，**64 个用例**，与当前 `tests/test_uniform_normal_repairs.py` 的 64 个 `def test_` **集合完全相等**（无缺、无多、无重名）。
- 全部最终代码/测试 mtime ≤ **10:25**（`apply_common_source_revisions_v4.py`、tests 10:25；run_v42 23:44、entry40 23:51、router 23:40、consume 23:32）。合并 10:28、scores185 10:30 也都在最终代码之后。因此 64 passed 覆盖的是最终代码，且晚于被评分的表。
- `integrity_current.log`：10:38，`37 passed in 1.43s`。
- 我未重复跑 pytest；以上为日志+时间+收集清单核验。

**证据包与 SHA**
- `acceptance/input_and_code_sha256.json`：**6838 条，0 缺失、0 不符**（逐条重算）。
- `acceptance/manifest.json`：`evidence.json`、`input_and_code_sha256.json` 两条均匹配。
- 6838 条中确认包含：三份新日志、`validation148.json`/`validate148.py`/`validation148_driver_v2.log`、四份支持/加载清单**自身**（preparation_v5、accepted_v2、normal_v2/loaded_code、merged193）、scores185/merged193/remaining/ea185 表、run_v42/entry40/router/consume/apply_v4/tests、旧 54 日志与 review v4，且全部按角色分开（`evidence.json.evidence_roles`：`parameter_review_gate_not_final_code` vs `final_code_regression` vs `final_merge` …）。
- `validation148.json` 的 7 个 code pin 全部匹配当前文件（pure_ea_cache、normal_revision_equivalence、aggregate_score_bounds_v3、entry40、scoring_core、tests、validate148.py）。

**数值未变（独立重算）**
- rows185：`COMPLETE_POINT=52`、`COMPLETE_WITH_INTERVALS=102`、`HAS_UNAVAILABLE=31` → bounded **154**；c_param 不可用 **6**；与 `evidence.json.score_counts` 完全一致（185/193/3145/154/52/31/6/2/191）。
- `remaining_reasons.json` 存在并被 pin，给出 31 个含 NA 答案与 46 条缺失叶分支行（c_param 6、s_time 25、coverage/sp 2、bio 2、s_label 3、co_order 1）。
- `validation148.json` 分支字段：`canonical_five_input_sha256`、`input_field_sha256`、`pure_result_sha256_before_receipt`、`result_sha256`；`world_grade_envelopes` 逐世界含 `denominator/present/unresolved/grade_bounds=[2,2]/point_invariant_over_outer_set/unknown_items_filled=false`（2018 21/3/34，2019 24/1/37）；`Com_IA_original_formula_replay_exact=true`、`actual_final_callable_and_runtime_reproduced=true`、`ea_metrics_unchanged=true`、`other_12_leaf_and_Co_Eff_exact=true`。

**Minor 4/5/6 的新增证据**
- Minor 4（支持清单自身）：`acceptance/input_and_code_sha256.json` 已包含四份清单**文件自身**及其 SHA（我逐条核验通过）；`evidence.json.checks.supporting_pin_manifests_themselves_included=true` 有对应落地。
- Minor 5（EA 诊断来源）：`validation148.json.diagnostic_differences` 逐项给出 `path/before/after/code_origin`，例如 `pure_ea_cache_v1/cache.py:29-46`（`original_repeated_container_references`，75/76→0，JSON 树转换前的别名计数）与 `pure_ea_cache_v1/cache.py:203-204`（`internal_prior_issued_plan_entries`，3/2→0，`_ISSUED` 进程历史诊断）；并声明 `ea_identity_only_removes_finite_nonnegative_elapsed_seconds=true`、`raw_pure_result_hash_includes_the_saved_original_elapsed_value=true`。不再是只凭文字豁免。
- Minor 6（收集清单）：`test_collection_current.log` 已 pin，64 名与测试文件 64 defs 完全一致；full 日志 64 点与之一致。

**历史状态未被误读**
- `validation148.json` 的 `full_regression_acceptance="SEPARATE_PENDING_GATE_AT_GENERATION"` 是 **11:04 生成时**的状态；full 回归在 **11:06** 完成，晚于它，故不作为“现在仍缺回归”的证据。
- `acceptance/evidence.json` 的 `status="PENDING_INDEPENDENT_CLOSURE"`、`final_acceptance_granted=false` 是**证据包自述的待独立关闭状态**；本报告即该独立关闭复核。我未修改任何文件，故该字段仍为 PENDING 属预期，不应被写成“已验收”。

## 2) Critical / Important / Minor

- **Critical：无。**
- **Important：无。** I-1 已按上述时间线、收集清单、6838 条 pin 与角色分离关闭。
- **Minor（均不阻断 ACCEPT）：**
 1. `validation148.json` 的 `full_regression_acceptance` 仍是生成时的 PENDING 文本；建议后续加 `superseded_by=final_candidate_v1/full_regression_current.log`，避免读者只看该字段。文件：`final_candidate_v1/validation148.json`（字段级）。
 2. `acceptance/manifest.json` 只 pin 了 `evidence.json` 与 `input_and_code_sha256.json`，manifest 自身未被上层 pin（与既有 manifest 模式一致）；如需完全闭合，可由主线程在上层证据中 pin 该 manifest。
 3. `full_regression_current.log` 仅 114 字节（点行+汇总），逐用例结果依赖 `test_collection_current.log` 与 `integrity_current.log`；建议保留 `-q --durations` 或至少不裁剪收集清单（当前收集清单已足够）。
 4. 两个 EA 诊断的 before/after 差异较大（75/76→0、3/2→0），其正当性由 `code_origin` 与五元输入/逐字段/纯结果哈希保证，而非数值等价；建议在任何摘要中保留“诊断非评分输入”的措辞（`validation148.json` 已有）。
 5. `evidence.json.status` 仍为 `PENDING_INDEPENDENT_CLOSURE`；主线程可在采纳本复核后更新为已独立关闭（我作为只读复核者不修改）。

## 3) 结论

- **门槛已闭合**：最终代码 64 passed（11:06）+ 64 collected（10:56）+ integrity 37 passed（10:38），均晚于最终代码与评分表；旧 54 日志已明确归为“参数评审门槛”，新日志归为“最终代码门槛”；6838 条 pin 逐条重算一致。
- **ACCEPT（限定）**：可作为工程增量候选（基线 191 + 经验证 2 分支，154 bounded / 52 point / 31 NA / 6 c_param NA）。不支持“全 193 统一新后端”“专家正确性”“已 promoted/主表已更新”等表述。
- 未验证项：专家标注与专家正确性、发表就绪性、主表提升；本轮无任何评分模型/编码器调用。
