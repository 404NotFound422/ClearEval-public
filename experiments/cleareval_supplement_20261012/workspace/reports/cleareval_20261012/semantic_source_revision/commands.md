# 实际命令与产物

以下均已执行，新增本地/API 评价请求为 0。Python 解释器使用本项目便携环境。
当前最终数值入口为 semantic_04；semantic_03 的数值相同，已有联合分析精确复用，并保存等值检查。
原始来源、模型返回和原 SR/SP 不被覆盖。重新计算不同规则请指定新输出目录。

中文方法候选，32 返回：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\run_method_candidate.py' '--out' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\method_candidate_02'
```

最终来源账本：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\build_source_annotations.py' '--out' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\source_annotations_v3.json'
```

最终来源辅助复算，32 返回：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\ClearEval-public\scripts\cce_semantic_ledger_replay_v1.py' '--baseline' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\method_candidate_02\results.json' '--metric-key' 'method_candidate_metrics' '--annotations' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\source_annotations_v3.json' '--config' 'C:\ClearEval\reports\cleareval_20261012\scorer_revision\config.json' '--policy' 'C:\ClearEval\reports\cleareval_20261012\typed_label_revision\policy_with_sources.json' '--out' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\semantic_04'
```

准备可选步骤分支：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\build_delivery.py' '--data-only'
```

条件联合分析及精确枚举：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\joint_readout.py'
```

参考来源依赖图：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\audit_source_dependencies.py'
```

示例、检查与图形：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\build_delivery.py'
```

报告与当前状态：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' '-X' 'utf8' 'C:\ClearEval\reports\cleareval_20261012\semantic_source_revision\finalize_delivery.py'
```

过程记录：
- semantic_01 在部分转换记录缺 numeric 时停止，保留计划和当时代码；semantic_02 修复接线。
- semantic_03 增加未分句父步骤依据：C01 主时间 34.375→34.5 h，CCE 不变。
- semantic_04 澄清 TUJ1 不必然是确定克隆；只改来源解释，全部数值不变。
- 交付检查曾预期 C08 两个时间分相同；实际得到 2.570991 与 3，拒绝不变性假设并补做完整联合分析。
- 早期历史方法与语义候选的原计划、结果及已有快照保留；当前可重现命令指向上面的最终版本。
