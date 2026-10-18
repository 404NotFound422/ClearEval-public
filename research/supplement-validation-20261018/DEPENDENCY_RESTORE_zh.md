# 原75项依赖直接补齐说明

此前268fc731工程包有94项原vendor清单，其中19项在仓库、75项省略。本次75项已按原相对路径和原SHA256补齐，完整清单没有删除或缩小。评分主程序与来源资料都在runner_engineering_candidate目录内，不再要求先找旧分卷附件。

文件清单见 [DEPENDENCY_RESTORE_MANIFEST.json](runner_engineering_candidate/DEPENDENCY_RESTORE_MANIFEST.json)，来源与归属见 [THIRD_PARTY_SOURCES.md](runner_engineering_candidate/THIRD_PARTY_SOURCES.md)。当前缺文件清单为空；本地实际新增数量取决于已有文件，请按hash核对。

从runner_engineering_candidate目录运行：

```sh
python -S -B verify_package.py --require-complete-vendor
python -S -B run_engineering_tests.py
```

目标为94项hash匹配、0缺失、完整性校验退出0；默认原18项scope＋3项包边界，共21项。实际独立验收记录见该目录VERIFICATION.json。测试入口和边界条件随完整包更新，原19项版本保留在history/268fc731；runner与原VENDOR_MANIFEST冻结未改。

**还没有完成：** 真实encoder/judge环境、正式20输入manifest和证据适用性、模块独立失败记录、真实端到端科学验收。本次不安装或执行模型，不新增科学分数。既有实验说明保留原发布快照；本次仅交付依赖与工程检查，当前依赖状态以本说明和验包结果为准。

更新只补依赖；保留本地源码修改和已有结果，先核对diff，不覆盖本地派生目录。
