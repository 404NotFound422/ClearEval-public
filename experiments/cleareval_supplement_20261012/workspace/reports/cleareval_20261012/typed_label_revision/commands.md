# 本轮已成功执行的命令

以下均为离线计算，不发送本地/API 模型请求。PowerShell 工作目录为 `C:\ClearEval\ClearEval-public`。未完成的候选评价请求不列为已执行命令。

```powershell
$taskPython = 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe'
$taskReport = 'C:\ClearEval\reports\cleareval_20261012'

& $taskPython -X utf8 "$taskReport\typed_label_revision\prepare_evidence.py"

& $taskPython -X utf8 scripts\cce_typed_label_scorer_v2.py --baseline "$taskReport\scorer_revision\with_decomposition\results.json" --config "$taskReport\scorer_revision\config.json" --policy "$taskReport\typed_label_revision\policy_with_sources.json" --source-index "$taskReport\missing_score_diagnosis\evidence.json" --decompositions "$taskReport\llm_decomposition.json" --out "$taskReport\typed_label_revision\with_pair_sources"

& $taskPython -X utf8 scripts\cce_typed_label_scorer_v2.py --baseline "$taskReport\scorer_revision\with_decomposition\results.json" --config "$taskReport\scorer_revision\config.json" --policy "$taskReport\typed_label_revision\policy_with_sources.json" --source-index "$taskReport\missing_score_diagnosis\evidence.json" --decompositions "$taskReport\llm_decomposition.json" --additional-label-annotations "$taskReport\typed_label_revision\author_label_annotations.json" --out "$taskReport\typed_label_revision\with_author_labels"

& $taskPython -X utf8 "$taskReport\typed_label_revision\verify_and_readout.py"
& $taskPython -X utf8 "$taskReport\typed_label_revision\time_branch_readout.py"
& $taskPython -X utf8 "$taskReport\typed_label_revision\joint_readout.py"

& $taskPython -X utf8 scripts\cce_qualitative_correctness_candidate_v1.py --cases artifacts\cce_validation\optimizer_round2_20261010\grounded_development_v11\cases.json --out "$taskReport\typed_label_revision\qualitative_prompt_pending"

& $taskPython -X utf8 "$taskReport\typed_label_revision\plot_results.py"
& $taskPython -X utf8 "$taskReport\typed_label_revision\render_and_check.py"
```

首层 `rules_only` 使用当时的 v2 入口及 `policy.json`，命令与上面相同但未传 `--additional-label-annotations`，policy 指向 `policy.json`，out 指向 `rules_only`。原入口副本保存在 [entrypoint_snapshot.py](rules_only/entrypoint_snapshot.py)，哈希对应该阶段 execution_manifest；当前同名仓库入口已为 v2.1。旧结果继续保留，不用新脚本覆盖该阶段产物。

恢复时先读取各 summary、manifest 和 STATUS，输入与配置未变则复用成功结果。仅查看当前产物可执行：

```powershell
Get-Content -LiteralPath 'C:\ClearEval\reports\cleareval_20261012\typed_label_revision\with_time_branches\summary.json' -Encoding UTF8
Get-Content -LiteralPath 'C:\ClearEval\reports\cleareval_20261012\typed_label_revision\joint\summary.json' -Encoding UTF8
```
