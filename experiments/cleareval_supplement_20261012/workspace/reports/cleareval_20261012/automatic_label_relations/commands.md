# 实际离线命令

以下六次批量执行均已实际产生结果。恢复时复用未变输入的成功产物；重跑时使用新输出目录，不能覆盖旧版本。

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\canonical32_01'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\archived67_01'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\canonical32_02'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\archived67_02'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'canonical32' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\canonical32_03'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\replay.py' '--cohort' 'archived67' '--out' 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\archived67_03'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\validate.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\automatic_label_relations\build_delivery.py'
```

前两次执行应使用相应目录 code_snapshot 下的入口和规则文件重建环境，不能用当前规则宣称复现旧版结果。最终入口和规则以 _03 的快照及哈希为准。

定性 Cor 执行包的 prepare、元数据 preflight、analyze 及未授权检查已执行；实际生成请求尚未执行。见 [准备说明](../qualitative_execution_03/README_zh.md)。
