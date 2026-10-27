# ClearEval Evidence-Preserving Scoring Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不伪造证据、参数、参考时长或分数的前提下，使可判分的 ClearEval 指标获得可复算数值，并为真实不可判分项保留有依据的 NA。

**Architecture:** 保留 component35 及已经独立验收的 14 个分支修订。以原始回答和参考原文为唯一事实源，在参数私有工厂中依次完成阶段/成员证明、参考操作变体、原始材料义务、真实评审、原公式聚合。先修复分母和证据链，再调用模型；任何完整域失败都不得转成点值。

**Tech Stack:** 现有 Python 3、`pathlib`/JSON/CSV、`pytest`、真实归档回执、项目内 `frozen_result_projection_v2.py`、本地 Ollama `qwen3.8:27b-q4_K_M`。不新增依赖，不把旧主表回写为“已接受”。

## Global Constraints

- 工作根：`R=C:\ClearEval\ClearEval-runtime-4b42b5a`；研究根：`H=R\research\evaluator-research-cycle-20261018`；解析根：`E=H\execution_alignment_resolution_20261024_v1`。
- 输出根：`O=C:\ClearEval\deliverables\cleareval_repair_20261025_232451`。历史回答、参考原文、原始回执、历史结果均不改写。
- 保持 185 份回答、193 个预声明参考分支、17 项指标、3145 行的身份；不得按分数选择参考或删除参考分支。
- `c_param` 只衡量实际参数写全程度，科学正确性由其他指标负责。不同参数值可以明确存在，但不得宣称科学等价或替代。
- Com/Co/Eff/IA 原公式不变；Bio-SR/SP 与 EA 分开；过夜固定 8h。
- 真正缺必要输入或参考证据时允许 NA。不得用 0、均值、满分、任意点值填充 UNKNOWN/NA，也不得把全量程区间冒充改善。
- 有限区间必须由完整域证明；多参考的全部分支、条件和来源必须保留，不能先按高分选分支再合并。
- 只有终止且通过来源归属、完整查询覆盖、严格槽域和重放校验的真实评审才能进入评分。不得编辑或过滤原始模型回执来制造合格证据。
- `EXPAND_106` 的大结果只能经 `runtime/frozen_result_projection_v2.py` 投影，不能整读。
- 不伪造专家标签，不写论文正文，不宣称专家正确性或发表就绪，不自行 git commit。
- 使用 `C:\ProgramData\anaconda3\python.exe -X utf8 -B`；子进程测试在 `H` 下运行并移除 `PYTHONPATH`，避免同名模块遮蔽。
- 本计划是暂停后的恢复方案，不授权把 `O\parameter_scope148\validated_preparation_v1` 当作已验收评分。

## 当前证据与暂停点

- `O\merge_stage1\scores185` 是候选主表：185 回答、193 分支、3145 行，所有分支正常执行通过；52 份全点值、101 份完整但含区间、32 份含不可用指标。
- 相对 component35，`c_param` 不可用回答由 9 降为 7；`s_time` 仍有 25 个不可用。024 的 TIME 为真实 3.0，022 保留有理由的 NA，不能为了维持旧点值而回退校验。
- 033 三个分支恢复完整多来源参数证据，170 的引文和 JSON 表示已修复，139 的 61 个查询经 6 次本地真实评审后得到 `c_param=3`。这些修订只涉及已声明分支，其他叶指标、Co、Eff、EA 和原公式已复验。
- 阶段主表是 component35 加 14 个已验证分支修订，不是统一新评分器的全 193 回放。171 份仍消费历史参数合同，不能声称全部旧合同已统一。
- 早期新增回归 20 项通过；后来相关套件记录为 103 passed、3 failed。当前 `tests/test_uniform_normal_repairs.py` 有 36 个测试，新加入的 6 项验收尚未通过，不能宣称当前全绿。
- `O\parameter_scope148\validated_preparation_v1` 未生成评分，但当前世界/分母不完整，不能作为正确准备产物使用。独立审查和本地复核均发现 R017/R018 的参数细项丢失、材料措辞被改写、精确介质证明被覆盖。
- `O\parameter_scope005` 的异常回执没有被消费；005 在旧基线已有 `c_param=2`，不应为升分放宽引文范围。
- 当前没有运行中的后台任务。DeepSeek V4.1 Flash 独立审查已完成，别名是 `deepseek/deepseek-flash`；其 Critical/Important 发现必须先处理，不能以模型配置失败掩盖问题。

---

### Task 0: 冻结可用主表并隔离无效实验

**Files:**
- Read: `O\merge_stage1\scores185\summary.json`、`O\merge_stage1\remaining\summary.json`
- Read: `O\parameter_scope148\validated_preparation_v1\summary.json`
- Create: `O\parameter_scope148\INVALIDATION.json`
- Create: `O\review_snapshot_v1\manifest.json`

**Interfaces:**
- 后续只能把 `O\merge_stage1` 当作阶段候选，不得把 148 的未评审准备结果当分数。

- [ ] 写失败检查：遍历 148 当前准备世界，断言若存在 `MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES`，则不得宣称所有世界完整。

```python
for world in prepared['binding']['worlds']:
    if any(m['gaps'] == ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']
           for m in prepared['binding']['parent_action_requirement_binding']['operation_mappings']):
        assert not all(w['complete_applicability'] for w in prepared['binding']['worlds'])
```

- [ ] 运行该检查并记录当前失败，不修改旧产物。将旧准备标为 `PREPARATION_REJECTED_MISSING_OPERATION_ITEMS`，记录缺失的 RI 操作细项、被改写的材料措辞及 `model_score_generated=false`。
- [ ] 为冻结快照的每个文件记录原路径和 SHA256。后续任何新评审都必须使用新版本目录，不能覆盖这份审查证据。

### Task 1: 修复变体延迟展开、来源写痕与闭包合同

**Files:**
- Modify: `E\parameter_operation_variant_scope_v1\apply.py`
- Modify: `E\parameter_private_reference_scope_v1\rebind.py`
- Modify: `E\parameter_private_reference_scope_v1\units.py`
- Test: `R\tests\test_uniform_normal_repairs.py`

**Interfaces:**
- `rebind()` 保留多模板未决状态，直到 `operation_variants.apply()` 消费。
- `operation_variants.apply()` 只在已存在 `reference_operation_variant_assignment` 时幂等返回；资源超限或不支持的变体必须保持不可评分。
- `units.binding_namespace()` 只接受模块级 `compile_binding`，不允许意外闭包污染。

- [ ] 先修测试夹具并运行失败测试：真实闭包不能靠给只读 `__closure__` 赋值制造。

```python
def outer():
    marker = None
    def native():
        return marker
    return native
native = outer()
assert native.__closure__ is not None
```

- [ ] 保留 deferred gap：多模板操作不得在世界尚未展开时标为完整。变体已生成后才移除对应 gap。

```python
if mapping['gaps'] == ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']:
    gaps.append({**gap, 'deferred_reference_operation_variants': True,
                 'parent_gaps': ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']})
```

- [ ] 修改提前返回和资源限制：只有已分配变体的世界才可幂等返回；没有可用变体或超限时，`complete_applicability=False`、`denominator=None`。

```python
if all(world.get('reference_operation_variant_assignment') for world in binding['worlds']):
    return binding
if required_world_count > max_template_worlds:
    out = deepcopy(binding)
    for world in out['worlds']:
        world['complete_applicability'] = False
        world['denominator'] = None
    out['reference_operation_variant_audit'] = {
        'version': VERSION, 'status': 'RESOURCE_LIMIT',
        'required_world_count': required_world_count, 'no_world_chosen': True}
    return out
```

- [ ] 投影改为先构造候选副本、通过 `bound_phase_set` 后才提交；拒绝时不得留下 phase/identity 写痕。保留 `operation ⊆ raw_text` 和原始坐标检查。
- [ ] 原生闭包闸门：`assert native.__closure__ is None, 'PRIVATE_BINDING_NATIVE_MUST_BE_MODULE_LEVEL'`。
- [ ] 运行 `pytest tests/test_uniform_normal_repairs.py -k 'operation_variants or rejected_reference_projection or native_binding' -q`，必须全部通过；任一失败则停止后续模型调用。

### Task 2: 用原始材料义务重建 CUBIC 世界，不改变评分措辞

**Files:**
- Create: `E\parameter_cubic_route_scope_v1\apply.py`
- Modify: `E\parameter_joint_reference_scope_v1\normal_candidate.py`
- Test: `R\tests\test_uniform_normal_repairs.py`

**Interfaces:**
- 新函数 `apply(binding, protocol, original_manifest, max_template_worlds=4096)` 返回同一 binding 结构及 `cubic_route_audit`。
- 调用顺序固定为 `typed_rebind.rebind` → `operation_variants.apply` → CUBIC 原始 route 编译；其他方法继续原路径。
- `compile_shared_items()` 只消费有来源证明的 route 项；每项保留原 `criterion/dimension/subject/original_slot_ids`。

- [ ] 先运行当前失败的原文/分母验收：2018 必须为 4 个完整世界且每个 32 个细项；2019 必须为 9 个完整世界且每个 35 个细项。`criterion == 原始细项.criterion` 对每个来源 ID 成立。

```python
assert observed['worlds'] == 4
assert observed['fine_counts'] == [32, 32, 32, 32]
assert observed['complete'] == observed['worlds']
```

- [ ] 对每个共享原始项调用 `recipe_scope.bind()`，保留返回的实际父操作及 `reference_operation_ids`。任一失败必须保留不可评分状态，不能删除原材料义务来得到完整世界。
- [ ] 用原始条目构造 route 项，经现有 `compile_shared_items()` 生成槽位。替换的是编译视图，不是原始账本；不得出现 `Urea，ddH2O 配制` 这类错误成分，也不得把 `CUBIC-L` 改成 `actual formulation R001`。

```python
item = {
    'criterion': shared['original_slot']['criterion'],
    'dimension': shared['original_slot']['dimension'],
    'subject': shared['original_slot'].get('subject'),
    'original_slot_ids': [shared['original_slot']['id']],
    'scope_unit': 'ROUTE',
    'actual_operation_ids': proof['actual_parent_ids'],
    'scope_binding_proof': {
        'source_scope_id': 'cubic-original-route:' + digest(
            [origin, proof['actual_parent_ids'], proof['reference_operation_ids']]),
        'source_refs': exact_parent_spans,
        'source_role_or_name_proof': proof,
        'parameter_values_used_to_select_applicability': False,
    },
}
compiled = compile_shared_items([item], world['units'], protocol, original_manifest)
```

- [ ] 世界重建时仅移除编译生成的 MATERIAL/ROUTE 视图，再以原始 route 槽位替换。保留 OPERATION 槽、所有参考操作变体、条件细项和原账本。`denominator == len(world['slots'])` 只能在无 gap 时成立。
- [ ] 验收全部来源 ID：编译覆盖集合与显式条件集合的并集必须覆盖原始细项账本，而不是把缺失条件静默删除。

```python
original = {item['id']: item['criterion'] for item in binding['original_full_fine_item_ledger']}
covered = {origin for world in binding['worlds'] for slot in world['slots']
           for origin in slot['original_slot_ids']}
conditional = {oid for world in binding['worlds']
               for assignment in world['reference_operation_variant_assignment'].values()
               for oid in assignment['conditional_original_item_ids']}
assert set(original) <= covered | conditional
for world in binding['worlds']:
    for slot in world['slots']:
        for origin in slot['original_slot_ids']:
            assert slot['criterion'] == original[origin]
```

- [ ] 运行 `pytest tests/test_uniform_normal_repairs.py -k 'cubic_preparation or joint_reference_scope_prepares or operation_variants' -q`。4/9 世界、32/35 细项、原始措辞、条件出处全部通过才进入下一任务。

### Task 3: 保留精确介质证明并复核替代配方边界

**Files:**
- Modify: `E\parameter_private_reference_scope_v1\units.py`
- Modify: `E\parameter_private_reference_scope_v1\rebind.py`
- Modify: `E\parameter_route_role_scope_v1\recipe_scope.py`
- Test: `R\tests\test_uniform_normal_repairs.py`

**Interfaces:**
- `apply_typed()` 合并证明，不删除已存在的 `rule/source_evidence`。
- `_alternative_recipe_scope()` 只在原评分义务允许不同值/可验证库存、来源属于 CUBIC、动作及阶段相容时使用；`different_named_medium_not_equated=True` 不得被解释为科学等价。

- [ ] 合并而非替换介质证明，保留原 `source` 和 `raw_text`，仅添加本参数私有投影证据。

```python
proof = dict(result.get('primary_medium_proof') or {})
proof.update(basis=VERSION, identity=evidence['actual_primary_identity'],
             reference_action_scope_proof=deepcopy(evidence))
proof.setdefault('source', deepcopy(row['source']))
proof.setdefault('raw_text', row['raw_text'])
result['primary_medium_proof'] = proof
```

- [ ] 用 R003–R005 验证 `route.primary_proof()` 在重绑定前后均通过。任一曾通过的精确名字证据在重绑定后失效，整个准备必须失败，而不是退回较弱证据路径。
- [ ] 对替代配方逐条审计参考 ID、源家族、动作、阶段和原评分义务。不同 CUBIC 配方可以评审写全程度，但不得交换 2018/2019 的参考身份，也不得把 R/R+、R1/R2、L 当作同一配方。
- [ ] 保留非 CUBIC、未命名介质、角色冲突、原文篡改和阶段不完整的负控制。每个完整世界必须能回放其 reference IDs 和来源证明，不能仅凭 `source_family` 放行。
- [ ] 运行 `pytest tests/test_uniform_normal_repairs.py -k 'apply_typed or alternative or declared_material_alias or reference_phase_units' -q`，并再次运行 Task 2 的全部验收。
- [ ] 使用 DeepSeek V4.1 Flash 对新的冻结代码做独立复核，先处理 Critical/Important 问题，再继续真实评审。

### Task 4: 完成 148 的真实参数评审、全链验收和增量合并

**Files:**
- Create: `O\parameter_scope148\accepted_v2\`
- Create: `E\runtime\component40_reference_scope_v1\router.py`
- Create: `E\runtime\component_entry_v40.py`
- Create: `E\runtime\uniform_normal_runner_v1\run_v42.py`
- Test: `R\tests\test_uniform_normal_repairs.py`

**Interfaces:**
- 新参数原生后端为 `parameter_joint_reference_scope_v1.normal_candidate`，不再退回仅 metadata 的后端。
- 参数证据依次经 `partial P → multi M → dispatch`；真实私有 `template` 和严格槽域必须由 `strict_core.verify_worlds()` 验证。
- 两分支评审来源按 `(input_id, branch)` 绑定，不能共享或按分选择。

- [ ] 将完整准备保存到 `accepted_v2\prepared\`，检查世界、细项、原始措辞、来源证明和请求 SHA。旧无效准备不得复制为有效证据。
- [ ] 使用固定本地 `qwen3.8:27b-q4_K_M`、seed 20261018、temperature 0。按完整 target payload 的查询分块，小块保持独立 JSON schema，避免输出截断；不得按分数、参考分支或期望结果筛查询。
- [ ] 每个批次都必须 `RESPONSE_TERMINAL`、无自动重试、保存 raw response 和 request/receipt。截断响应不得消费。引文越界、错父操作、错来源跨度的批次必须隔离，不能用编辑回执的方式补救。
- [ ] 真实 `consume/apply/revalidate_parameter_graph` 全部通过：完整去重查询覆盖、全部世界严格槽有效、原参数公式一致、其他 12 个叶指标及 Co/Eff/EA 不变，Com/IA 用原公式重算。
- [ ] 新 runner 只回放已证明的 148 两分支及对照分支，验证所有 17 个完整节点、参考原文、原始回答、JSON 表示和 EA 五输入。成功后才能通过 `apply_common_source_revisions_v3.py` 增量加入阶段主表。
- [ ] 重跑 `collect_uniform_normal185_v5.py`、`collect_execution_alignment185_v1.py`、`export_remaining_cases_v1.py`，输出到新的 `O\final_candidate_v1`，不能覆盖 `merge_stage1`。

### Task 5: 处理剩余真实缺口并统一全量复算

**Files:**
- Modify: `E\runtime\uniform_normal_runner_v1\run_v42.py`
- Read: `E\time_residual_component34_20261025_v1\audit26_v1`、`reference11_v1`
- Read: `O\parameter_remaining`、`O\parameter_scope005\scope_diagnostics_v1.json`
- Create: `O\final_candidate_v1\remaining_reasons.json`

**Interfaces:**
- NA 必须带来源缺失原因，不能为了数值齐全而推断标准时长、原始通道或参考配方。
- 合并只接受已验证的 `(input_id, branch)`；193 个参考分支全部保留。

- [ ] 继续审计 184/130/161 的来源域，优先复用已验证的动作/材料证据。只有完整参数世界和真实评审都成立才产生新点值。
- [ ] 012/015 先审计原始通道和 Bio/步骤完整性；`FINAL_CHANNEL_UNCONFIRMED_ARCHIVE_ONLY` 不得伪装成科学零分。
- [ ] TIME 按 14 个源行未决、11 个参考方法/层级不唯一、1 个有限世界不可评分继续追踪。开放保存、直至透明、必要延长、未写配液时长不得发明为 0h 或标准时长。
- [ ] 005 保留查询粒度问题及旧 `c_param=2`，除非有符合原义务的通用范围修复；不得通过删引文或放宽校验来升分。
- [ ] 用同一入口对 193 分支做离线全量重放，保留 193 顺序和 EA/Bio-SR/SP 分母。验证每个 VALID 为有限数值、区间有限有序、NA 有原始原因，四个聚合按原公式复算。
- [ ] 对同一冻结输入重复离线评分，比较分数、证据域和哈希一致。输出新旧差异的原始文本/参考证据、叶原因和代码版本，不只报 PASS 或均值。

### Task 6: 评分有效性与独立创新验证

**Files:**
- Create: `O\validity_v1\`
- Create: `O\final_candidate_v1\REPRODUCE.md`

**Interfaces:**
- 创新实验与主评分定义分离，未经验证的候选不得混入主表。

- [ ] 在已有 15 题框架上验证事实忠实性、必要步骤删除、参数删除、明确错误、合理替代、证据移除、格式不变性与重复稳定性；不伪造专家金标准。
- [ ] 首先交付“证据来源 + 缺失原因 + 依赖传播”的诊断，区分评分失败、回答漏写、参考不足与真实多解。
- [ ] 评估可复用创新：延迟变体的来源证据图、可逆来源/JSON 证据绑定、联合多来源评审、原始义务不变量。只有独立对照支持时才称为可靠性改进。
- [ ] 可选研究多参考联合约束的端点可达性/区间收缩。每个端点必须可达，不能按分数选参考，并与当前 `joint_endpoint_attainability_certified=False` 明确区分；时间不足时仅保留未验证建议。
- [ ] 在 `REPRODUCE.md` 记录入口、输入 SHA、真实模型调用、拒绝回执、点值/区间/NA/失败计数、剩余历史合同、测试日志和未解决项。明确工程可算性不等于专家正确性或发表就绪。

## 关键复现命令

以下命令只在对应验收已通过、且目标输出目录不存在时执行；失败时保留原目录和原因，不用旧主表顶替。

```bash
cd C:/ClearEval/ClearEval-runtime-4b42b5a
PY=/c/ProgramData/anaconda3/python.exe
"$PY" -X utf8 -B -m pytest tests/test_uniform_normal_repairs.py -q
"$PY" -X utf8 -B -m pytest tests/test_evaluator_integrity.py -q

cd C:/ClearEval/ClearEval-runtime-4b42b5a/research/evaluator-research-cycle-20261018
"$PY" -X utf8 -B execution_alignment_resolution_20261024_v1/runtime/uniform_normal_runner_v1/run_v42.py --ids EXPAND_148 --output C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148/normal_v2
"$PY" -X utf8 -B execution_alignment_resolution_20261024_v1/runtime/collect_uniform_normal185_v5.py --input-root C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/merged193 --output C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/scores185
"$PY" -X utf8 -B execution_alignment_resolution_20261024_v1/runtime/collect_execution_alignment185_v1.py --input-root C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/merged193 --output C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/ea185
"$PY" -X utf8 -B execution_alignment_resolution_20261024_v1/runtime/export_remaining_cases_v1.py --table C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/scores185 --normal-root C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/merged193 --output C:/ClearEval/deliverables/cleareval_repair_20261025_232451/final_candidate_v1/remaining
```

## 恢复执行门槛

1. Task 0–3 的新增与受影响测试全部通过，且独立审查的 Critical/Important 问题已处理。
2. Task 4 的真实评审和正常管线均通过，才可更新候选主表。
3. 不把任何 `PREPARED`、局部 `PASS`、完整回执或模型配置成功当作评分正确。
4. 若原始证据不足，交付精确 NA，而不是强行完成“全点值”目标。
5. 恢复建议采用主线程逐步执行，DeepSeek V4.1 Flash 只做冻结版本的独立审查，不并行修改同一文件。

---

## 2026-10-26 11:49 UTC 计费周期暂停检查点

**状态：暂停，不是评分完成或独立审查通过。真实参数评审调用为 0，主表未更新。**

- 已完成的阶段候选仍为 `O\merge_stage1\scores185`：52 道全点值、153 道完整点值或有界区间、32 道含不可用指标。它不是本轮新工厂的全量回放。
- focused 回归实测为 `23 passed, 22 deselected`。完整 45 项套件和第二次 DeepSeek 复审因用户要求收尾而停止，均不得写成通过。
- 第一次独立复审原文保存在 `O\review_snapshot_v1\deepseek_v41_flash_review_v1.log`。其 C1/C2/I1–I6 已按原文核查并修复实现；第二次复审尚无结论，不能视为接受。
- 原 Task 2 的 2018=4×32、2019=9×35 不再作为正确性的预设。修正 half-R 的 REQUIRED_PROCEDURE_SPECIFICATION 条件项，并排除 2019 次日更换绑定预平衡后，当前准备为：
  - 2018：4 个完整世界，分母 `[34,33,33,32]`，34 个去重查询。
  - 2019：6 个完整世界，分母 `[37,36,36,36,35,35]`，39 个去重查询。
  - 这里仍保留义务×实际执行单元的原分母口径；共享 route 只计一次，公共聚合公式不变。
- 当前准备仅在 `O\parameter_scope148\preparation_v4`，状态为 `PREPARED_NOT_SCORED`、`accepted_for_scoring=false`。`preparation_v2`、`preparation_v3` 均有 INVALIDATION，旧分块请求不得执行。
- 新增/修改实现为 `parameter_cubic_route_scope_v1/apply.py`、`parameter_joint_reference_scope_v1/normal_candidate.py`、`parameter_operation_variant_scope_v1/apply.py`、`parameter_private_reference_scope_v1/rebind.py` 和 `units.py`。所有文件保留在当前隔离 worktree，未 commit。
- 缓存重算、缺证明失败关闭、双账本覆盖、参考操作出处、替代介质世代边界、执行单元权重和最终审计一致性均已加入。详细 SHA 和续接说明见 `O\next_cycle_20261026\CHECKPOINT.md` 与 `manifest.json`。

### 下个周期的强制顺序

- [ ] 从头运行完整 45 项回归和 `tests/test_evaluator_integrity.py`；不能用 focused 通过替代完整验证。
- [ ] 恢复第二次 DeepSeek 复审（保留 agent-2 的上下文，模型为 `deepseek/deepseek-flash`），处理所有 Critical/Important；若复审不通过，不进入真实评分。
- [ ] 用 `preparation_v4/source/<branch>` 和 `runtime/minimal_instance_review_v2.prepare()` 重新生成精确缓存计划。参数模块必须为 `execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1.normal_candidate`。不得复用 v2/v3 的请求或计划。
- [ ] 使用 `parameter_atomic_multisource_v1.reader.project_request()` 按每次至多 12 个查询分块。当前预期为 2018 的 12+12+10、2019 的 12+12+12+3，共 7 次本地调用；以重新验证的 payload 为准，不为减少调用而删查询。
- [ ] 只消费终止、完整、引文和来源范围均通过的真实回执。截断或异常回执隔离，不自动重试，不编辑原始回执。
- [ ] 经 multi consume/apply/revalidate、严格世界和正常管线验收后，才创建 `component40_reference_scope_v1`、`component_entry_v40.py`、`run_v42.py`。这些文件目前尚未创建。
- [ ] `apply_common_source_revisions_v3.py` 的 cause→指标闭包仍待实现；已确认不能把 `allowed_changed_metrics=None` 当成任意元数据/参数漂移的许可。参数修订只允许 `c_param,Com,IA`，其他修订按原聚合依赖限制。
- [ ] 只有上述验收完成才增量合并到新目录，再处理其余参数、25 个 TIME 不可用、标签、顺序和原始通道缺口。真实证据不足时保留有理由的 NA，不以全点值为目标伪造数值。
