# 实际执行与复核命令

以下均已实际执行；固定输出目录的命令不会覆盖成功结果。早期回放须使用对应 code_snapshot，当前脚本不代表早期规则。

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\canonical32_01'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\archived67_01'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\canonical32_02'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\archived67_02'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\canonical32_03'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\archived67_03'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\canonical32_04'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\archived67_04'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\validate.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\joint_readout.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\threshold_readout.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\plot_results.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\build_delivery.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_time_scope\verify_delivery.py'
```

下次继续前先执行 verify_delivery.py；输入与配置未变时复用现有结果。新模型请求须以 qualitative_execution_03 的实际授权和固定矩阵为准，本页不声称该批已执行。
