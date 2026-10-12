# 实际执行命令

在 C:\ClearEval 的 PowerShell 执行：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\intervention_validation_01\run_validation.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\intervention_validation_01\reuse_inventory.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\intervention_validation_01\bridge_operations.py'
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\intervention_validation_01\validate_and_publish.py'
```

运行记录分别保存在 execution.json、reuse_execution.json、bridge_execution.json。全部是本地读取、结构变换或离线重算，生成请求 0、编码请求 0。诊断脚本使用已有相似度矩阵，未重新调用编码器。

首次离线运行因 numpy 索引未转换为 JSON 可序列化的整数停止；后续读取旧压缩 wire schema 时，把字段 i 误当为解析后的 id，已按真实格式改正。另发现累计消融使用了已处理过的 prior-stage 值，已沿原始引用纠正。这些问题保存在 execution_issue_01/02/03.json，不属于模型请求失败或模型重试。

revision_01/ 保存第一版候选、7/8 的规范化结果、初版阶段标题缺口和其他诊断；其中初版时间消融数值经来源核对已纠正，当前有效结果见根目录 time_relation_checks.json。原模型返回、旧 SR/SP 和 CCE 均未覆盖。

恢复阅读 REPORT_zh.md、SUMMARY.json 和 validation.json。当前所有模型额度已用完，账本仍 446/446；本轮未发起追加调用。

