# 本轮实际命令与恢复

所有成功执行均为离线处理，新模型请求 0。工作目录为 `C:\ClearEval\ClearEval-public`。

```powershell
$py = 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe'
$out = 'C:\ClearEval\reports\cleareval_20261012\typed_label_transfer'
Set-Location C:\ClearEval\ClearEval-public

& $py -X utf8 scripts\cce_typed_label_transfer_v1.py --batches artifacts\cce_validation\optimizer_round3_20261011\E2_canonical_qwen_01 artifacts\cce_validation\optimizer_round3_20261011\confirmation_qwen_01 --config C:\ClearEval\reports\cleareval_20261012\scorer_revision\config.json --policy C:\ClearEval\reports\cleareval_20261012\typed_label_revision\policy_with_sources.json --out "$out\actual_01"

& $py -X utf8 "$out\run_scope_candidate.py" --out "$out\scope_candidate_02"
& $py -X utf8 "$out\verify_readout.py"
& $py -X utf8 "$out\diagnose_conversion.py"
& $py -X utf8 "$out\run_lexical_candidate.py" --out "$out\lexical_candidate_02"
& $py -X utf8 "$out\run_time_heading_candidate.py"
& $py -X utf8 "$out\prepare_qualitative_pairs.py"
& $py -X utf8 "$out\build_delivery.py"
& $py -X utf8 "$out\finalize_delivery.py"
```

同配置已成功产物应直接复用，不必为得到相同结果再次执行整套命令。需要重现时，上述各脚本的 `execution.json` 或相应记录保留实际调用参数；配置改变时使用新版本/新目录，保留对照。

当前最终结果是 [time_heading_candidate_01/results.json](time_heading_candidate_01/results.json) 和 [逐答案 CSV](time_heading_candidate_01/per_answer.csv)。E2 数值与 [scope_candidate_02](scope_candidate_02/readout.json) 一致，直接复用其成对表和重采样；后续时间修订没有改变这 24 份结果。

`scope_candidate_01` 是早期阶段范围实现，其代码快照已按原计划哈希保存。`lexical_candidate_01` 的第一次编排因缺少 `quantitative_data` 输入中断，修复后在 `lexical_candidate_02` 完整执行；原失败记录保留。这些是离线程序运行，不计作模型重试。

下一轮开发请求已经形成 [10 份具体材料](qualitative_canonical_pending/manifest.json)，均为 `prepared_not_requested`。本文没有将旧 438 次预算入口改为可发起新调用的入口；新增计次与时间授权尚未记录。
