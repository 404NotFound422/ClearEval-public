# ClearEval 最小工程包：独立干净目录验收附录

日期：2026-10-18 UTC。结论：**可发布为能够单独运行所列工程检查的最小代码包；不是完整实验执行包。**

## 验收对象与隔离

- 包：`runner_engineering_candidate`，43 个文件
- `PACKAGE_MANIFEST.json` SHA256：`0534aaa5f2f5364635459e8bd293b59a0b9e19e311118a2b1e0570fc1534e80d`
- 对应完整候选 code_freeze：`d795ab8f5ff7a835cd8bfef5326197238bb9ef13962a7b92c2c3942d4ded266b`
- 将包复制至新的临时目录，未复制相邻 recovery/archive 树；移除 PYTHONPATH/PYTHONHOME，使用 CPython 3.12 和 `-S -B`。验收前后 staging 包全部文件哈希一致。

## 独立复测结果

1. `python -S -B run_engineering_tests.py`：**19/19 通过**，由 16 项纯代码 scope 回归与 3 项包边界回归组成。默认目标明确列出另外 2 项来源依赖测试为 NOT RUN，没有计成通过。
2. 另行直接运行原始 18 项 scope 测试：**16 通过、2 ERROR**。两个错误均在真实 `source_reference()` 读取未附的 iDISCO 来源锁时发生；未 mock 来源锁、未制造替代资料。这不属于完整 18 项验收通过。
3. runner 主帮助页、inventory-check/prepare/verify/execute 帮助页，以及 build_input_bindings 帮助页均通过。帮助页通过不证明对应实际流程可执行。
4. 包哈希校验通过；完整 vendor 要求返回预期退出码 **2**。原 `prepare` 在缺少完整 vendor 时继续阻断，且没有创建输出目录。
5. 在独立临时副本中故意改动 runner 源码、错误回填一个 vendor 文件，验包分别拒绝；恢复干净字节后重新通过。原 staging 与完整候选均未因此改变。
6. 19 项目标运行后检查已导入模块：numpy、scipy、jsonschema、torch、transformers、sentence_transformers 均未导入。安装、judge、encoder 和生产评分调用均为 0。

## 来源与缺项

- 31 个原样复制文件逐一与完整冻结候选、PROVENANCE 的 SHA256 对照，全部相同。
- 原 VENDOR_MANIFEST 字节完全不变，仍有 94 项；此包实际保留 19 项、缺少 75 项。缺项相对路径及预期 SHA256 与 MISSING_LOCAL_FILES 声明完全吻合。
- 该 75 项清单是历史完整快照的差集，**不是独立证明每项都为每种新实验的最小运行依赖**。新入口仍有历史初始化、原题需求、查表、来源锁与延迟导入耦合，完整运行闭包尚未拆分验收。
- 本独审核对了缺项和候选的哈希对应；没有再次逐项打开原附件/嵌套 ZIP 验证恢复定位映射。
- 完整候选的 31/31 自带测试、18/18 独立边界和 20 项静态入口审计，属于完整候选环境。不能移植为这个精简包的完整运行结论。

## 发布和后续边界

可以准确表述：“下载代码包后，可在无需第三方依赖和模型的条件下运行 19 项明确列出的工程检查与 CLI 帮助页。”

不能表述：“下载即可运行补充实验”“18 项 scope 全部独立通过”“20 项全部可算”或“已完成端到端/科学验收”。正式运行仍需按所选执行路径恢复并审查必要代码与证据、冻结真实任务输入和模型环境，再取得对应运行许可与预算。

这是对待发布 staging 副本的验收；本独审没有核验远程 GitHub 新提交。模型执行和正式补充实验均未进行。

机读细节与逐项命令输出见 [portable_engineering_review_results.json](portable_engineering_review_results.json)。公开包内的 verify_package.py 和 run_engineering_tests.py 可复跑已交付目标；独立审查脚本未随本批发布。结果中的临时绝对路径替换为 `<isolated-package>`，Python安装路径替换为 `<python-runtime>`。
