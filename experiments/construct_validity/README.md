# ClearEval 构念效度开发入口

模块使用 Python 标准库。当前为可审查的开发实现，尚未完成科学验证。原始论文材料、旧评价器和历史结果保持不变。

在 ClearEval-public 目录运行：

~~~powershell
python -B -m unittest discover -s tests -p test_construct_validity*.py -v
python -B -m experiments.construct_validity audit --workspace .. --out ../review_artifacts/new_audit
python -B -m experiments.construct_validity prepare --workspace .. --out ../review_artifacts/new_pilot
python -B -m experiments.construct_validity preflight --study ../review_artifacts/new_pilot
~~~

只有 run 请求本地模型：

~~~powershell
python -B -m experiments.construct_validity run --study ../review_artifacts/new_pilot --max-new 1
~~~

只允许显式回环地址，无需 API key，不下载模型、不重启服务、不调整既有 GPU 进程。冻结本机 qwen3:8b 的权重摘要并用 CPU 推理。28 个计划请求覆盖 6 个开发根任务：复用前次 2 份固定方案、另生成 4 份。重复任务独立编号而输入相同；超时、截断、格式错误留原件，依赖失败保持未提交。

已有批次不可覆盖。改规则、模型、提示或参数须新建目录。2026-09-29 的 transport480 分支只将首响应读取超时从 180 秒改为 480 秒，原失败保留。执行模块必须与冻结快照一致。

只复核已有记录：

~~~powershell
python -B -m experiments.construct_validity analyze --study ../review_artifacts/new_pilot
python -B -m experiments.construct_validity legacy-replay --workspace .. --out ../review_artifacts/legacy_replay
python -B -m experiments.construct_validity review-export --study ../review_artifacts/new_pilot --out ../review_artifacts/blind_review
python -B -m experiments.construct_validity review-import --package ../review_artifacts/blind_review --ratings filled.json --out ../review_artifacts/expert_ratings
python -B -m experiments.construct_validity formal-readiness --workspace .. --out ../review_artifacts/readiness
~~~

人工审阅打开 public/review.html，离线填写后下载 JSON。答案评阅者只收到 public；private 映射、控制期望和自动结果不能一同分发。task_review 单独用于任务要求与证据审阅，空模板不计评分。

audit/prepare 使用本工作区已有快照，单独分发代码必须带输入。analyze 根据冻结请求复算，统计/审阅模块由交付清单另行哈希。来源存在检查不等于科学核验，详见 construct_spec.md、metrics_spec.md、migration_report.md。
