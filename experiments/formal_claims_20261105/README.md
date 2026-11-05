# ClearEval V6.2 正式版：配方归属修复与185例复测

2026-11-05。依据本轮授权，完成已复现问题的修复、局部回归、185份原始回答/193个参考分支的完整复测和差异核对。原问题、回答、参考与8项人工裁决保持不变，没有调用新模型。

## 句中配方如何处理

执行操作与配制说明现在使用不同的解析视图，原文保留：

- 配方放在括号、`containing` 从句、`solution/clearing medium` 后，或单独的配制步骤中，都不会仅因增加说明而增加执行步骤分母。
- 用5%工作液处理、括号说明由30%母液配制时，步骤浓度读取5%；母液浓度进入独立配制核验。配制时搅拌/混合的次数不计作样本处理次数。
- 参考展开了配方、回答只写明确的标准试剂名称时，不再要求回答逐项重复配方才能建立步骤对应。
- 同名试剂按实际使用位置绑定；当前步骤的配方优先，后面的定义不倒灌到前面。配制附录仍可供执行步骤引用。
- 洗涤句中的“去除残余试剂”、禁止添加说明、染色液的临时添加物，不再错误改写执行操作或后续原始试剂配方。
- 明确错误的成分、比例及配制算术仍影响相应操作的正确性；只有额外配制说明缺少单位时，保留独立核验记录，不推翻已明确的工作浓度。

同步修复了数字名称截断、CUBIC N/M变体归属、嵌套单位括号、被动语态配制步骤、双重命名配方、共享化学名称词典，以及Bio-F1未传递待定步骤区间的问题。配方检查复用原有知识库及已绑定来源，没有修改原有评分满分和CCE权重。

## 验证结果

- 53项配方/操作/真实案例测试，11项主评分回归，6项入口与结果兼容性检查，合计70项通过；包括正式版本指针和历史V5评分复现。
- 全185例都有数值评分，193个参考分支完整；8项人工裁决保留，未发现剩余的已定位配方归属错误。
- 78个案例使用了配方与执行条件分离；16个案例的评分值或状态发生变化。
- EXPAND_072、074、167写明“30%母液按1:20稀释得到5%”。按两种常见的比例记法，名义浓度分别约为1.43%或1.50%，均与5%不一致，现已检出。
- 原始回答哈希、分项区间、步骤数量、Bio指标、CCE汇总、原有主表接口均通过一致性检查。有效性、时间、标记、参数完整性等未受本轮修复影响的结果继续复用。

| 指标：185例平均值 | 原V5 | V6.2 |
|---|---:|---:|
| bio_sr | 52.25% | 52.32% |
| bio_sp | 38.19% | 38.25% |
| bio_f1 | 42.70% | 42.76% |
| Co | 81.60% | 82.09% |
| IA | 51.66% | 51.64% |

这些是同一批回答经评分程序修复后的数值，不是重新生成回答的模型提升。IA采用Com、Co、Eff的最低项，因此正确性修正不会普遍抬高总分。

当前132例基础分项已确定，50例仍有部分区间，3例原回答未形成最终protocol、按原规则计0。50例中的区间主要涉及时间范围/参考适用性，以及原回答未明确的条件；各分项可重叠。164例总分已不受这些分项区间影响。8条尚不能确定的附加配制核验保持UNKNOWN，独立列示，不新增工作浓度扣分。

发生评分值或状态变化的案例：EXPAND_004、EXPAND_016、EXPAND_017、EXPAND_019、EXPAND_024、EXPAND_072、EXPAND_074、EXPAND_104、EXPAND_120、EXPAND_122、EXPAND_123、EXPAND_138、EXPAND_153、EXPAND_167、EXPAND_168、EXPAND_184。

## 查看结果

- 新版审核页面：`results/benchmark185/2026-11-05-v6.2/完整评分审核.html`
- 全部评分表：`results/benchmark185/2026-11-05-v6.2/185例完整评分.csv`
- 完整机器结果：同目录的`scores185.json.gz`和`scores193.json.gz`
- 本轮差异与校验：`experiments/formal_claims_20261105/full_retest_validation.json`
- 正式步骤检查缓存：`dataset/benchmark185/2026-11-05-v6.2/verified_checks.json.gz`；与本实验目录的`full_retest_checks.json.gz`逐字节一致。
- 版本、代码和输入哈希：同目录的`run_receipt.json`

V6.2已成为正式默认版本，版本指针为`CURRENT_SCORING.json`，发布编号为`cleareval-benchmark-20261105-v6.2`。评分入口、主表、审核页和结果索引统一指向本版。按以下命令复用已验证缓存生成完整评分：

```text
python OEQ_run_grading_new.py --cached-checks
python results/calculate_main_table_score.py
```

局部验证与全量结果校验：

```text
python experiments/formal_claims_20261105/validate_targeted.py
python -m unittest tests.test_complete_scoring tests.test_scoring_release
python experiments/formal_claims_20261105/validate_full_retest.py
```

需要重新计算指定案例时使用`recompute_checks.py --case-id EXPAND_xxx`；本轮已按授权执行`--full-retest`。发布时复用该复测缓存，没有再次运行185例步骤匹配。

原始V5输入和评分结果保留。`python OEQ_run_grading_new.py --legacy-v5`将历史复现结果写入`benchmark-reports/legacy-v5/`。此前V6/V6.1缓存及实验对照作为历史记录保留；`--independent-claims`仍可兼容旧命令，但本版已默认启用该模块。
