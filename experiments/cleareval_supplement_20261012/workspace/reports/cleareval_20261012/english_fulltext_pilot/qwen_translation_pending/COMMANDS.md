# 实际执行与恢复

以下命令在 `C:\ClearEval` 的 PowerShell 执行。用户于本轮以“好的，继续”批准上一轮提出的 8 次／2 小时方案；[授权记录](authorization.json)保存范围、起止时间和输入绑定。最晚截止 UTC 2026-10-12 15:03:22，北京时间 23:03:22。全部请求于 UTC 13:20:20 完成。

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\qwen_translation_pending\run_translation.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\qwen_translation_pending\score_translations.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\qwen_translation_pending\mechanism_checks.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\qwen_translation_pending\finalize_readout.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\qwen_translation_pending\verify_and_publish.py'
```

首次执行 `run_translation.py` 因授权记录的 PowerShell 中文编码问题在任何生成请求之前退出。修正记录后执行成功，没有重新发送任何失败的模型请求。[问题记录](execution_issue_01.json)与修正前记录均保留。每份请求的实际命令、进程、输出、用时、输入和返回文件可从 `execution_records/`、`returns/<request_id>/started.json` 和 `terminal.json` 追溯。

评分和机制对照全部离线。机制对照新增生成请求 0、新编码向量 0，复用已经生成的向量。[机制执行记录](mechanism_checks/execution.json) · [来源核查执行记录](readout_execution.json)。

恢复时先读 [FINAL_SUMMARY.json](FINAL_SUMMARY.json) 和 [RESULTS_zh.md](RESULTS_zh.md)。8 个请求已有终态，应复用 `returns`；不要重新运行 `prepare_qwen.py` 或修改冻结 payload。相同输入与配置下，`score_translations.py` 会复用逐份成功评分。历史目录名 `qwen_translation_pending` 保留以维持来源路径，其当前状态已经是“8 次执行完成”。原 `plan.json` 的待批状态是执行前冻结快照，最新状态以授权、执行总结和 446/446 预算为准。

本批授权不包含仍单独待定的 `qualitative_execution_03`，也不自动转给下一轮实验。
