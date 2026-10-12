# 本轮实际命令

以下命令在 `C:\ClearEval` 的 PowerShell 执行。此目录未发送新 Qwen/其他生成式请求；编码器为已有本地 CPU 模型。

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\prepare.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\prepare_controls.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\run.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\time_readout.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\prepare_qwen.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\analyze.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\verify_delivery.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\english_fulltext_pilot\update_status.py'
```

准备首次发现子串替换/残留中文的问题，失败与修复说明见 [preparation_issue_01.json](preparation_issue_01.json)；修复后准备成功，全部评分在修复后进行。评分、时间复算及请求准备的实际执行记录分别见 [run_01/execution.json](run_01/execution.json)、[time_examples/execution.json](time_examples/execution.json)、[qwen_translation_pending/preparation_execution.json](qwen_translation_pending/preparation_execution.json)。

恢复时先阅读 [REPORT_zh.md](REPORT_zh.md) 和 [summary.json](summary.json)。输入未变时，直接运行 `run.py` 会核验并复用成功结果，不重新执行编码。不要为恢复而重跑准备脚本生成新的时间戳/冻结哈希。后续新 Qwen 请求尚未执行，须使用新的明确计次授权；不要把旧定性 Cor 待批方案混入这 8 个翻译请求。
