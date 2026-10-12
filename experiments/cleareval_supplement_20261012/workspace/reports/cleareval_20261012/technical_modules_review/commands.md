# 本轮实际本地命令

所有命令只读取既有实验输入或写入本轮研究文档。没有调用评价器、加载嵌入模型或导入评分函数。网页文献通过浏览工具查阅，检索主题与阅读范围另见 [SEARCH_LOG.md](SEARCH_LOG.md)。

已执行的本地证据收集：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\technical_modules_review\collect_local_evidence.py'
```

该脚本生成 `LOCAL_EVIDENCE.json`，从已有 JSON 摘录实值、计算文件哈希并读取便携环境的安装版本。其计数不是新增科学观测。

已执行的文档核对，退出码为 0：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\technical_modules_review\verify_delivery.py'
```

核对内容为本地链接、证据文件身份、摘要数值及文献卡关联；结果见 [verification.json](verification.json)。这不是科学准确率测试。文档增补后使用同一命令刷新交付哈希。

已执行的导航更新，退出码为 0：

```powershell
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 'C:\ClearEval\reports\cleareval_20261012\technical_modules_review\update_navigation.py'
```

只向 `STATUS.md` 和当日报告入口添加研究续记；更新前原件保存在 `navigation_before`，前后哈希见 [navigation_updates.json](navigation_updates.json)。既有评分结果没有被导航操作改动。
