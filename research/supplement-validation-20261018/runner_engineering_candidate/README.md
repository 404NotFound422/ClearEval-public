# ClearEval 独立工程候选包（2026-10-18）

这是可以单独运行基础工程测试的最小代码闭包，供本地 Codex 继续审查和接手。状态是 EXPERIMENTAL_ENGINEERING_CANDIDATE；不是完整实验运行包、已恢复 v8、科学验收版或新的模型结果。

## 立即可运行

在本目录执行，无需安装第三方包、无需恢复 archive、无需模型或凭据：

    python -S -B verify_package.py
    python -S -B run_engineering_tests.py
    python -S -B runner.py --help
    python -S -B runner.py inventory-check --help
    python -S -B runner.py prepare --help
    python -S -B runner.py verify --help
    python -S -B runner.py execute --help
    python -S -B build_input_bindings.py --help

-S 禁止加载 site-packages，-B 不生成字节码。实际验收使用 CPython 3.12；未验证其他 Python 版本与平台。

默认目标执行原 18 项范围/表示回归中的 16 项纯代码测试，加 3 项包边界测试，共 19 项。另 2 项 solvent-reversal 测试会读取受锁定的 iDISCO 来源资料，未随包附带，明确显示 NOT RUN；不能计入通过数。原 18 项测试文件逐字保留，选择清单及两项所需原文件在 TEST_PLAN.json。测试中的短字面文本是解析器输入，源提供器被 mock 的测试只检验 runner 的 scope 门；不构成真实题集、科学 gold、论文复刻或新执行记录。没有新增模型、encoder 或 judge 调用，也没有新的实验分数。

## 功能边界

- 已验收：本包 hash 清单、16 项纯代码回归、3 项包边界回归、所有入口的 --help。
- inventory-check：代码保留，读取用户本地原始 pairs/inventory，仅做原文哈希与记录目录检查。没有在本包复跑真实数据；不是参考适用性审定或科学评分。
- prepare / verify / execute：只验收帮助页。原 verify_vendor 保持不变，本包故意缺少完整 vendor 内容，正式调用会被阻断。缺项不是成功；不得删除、缩小或跳过原清单以伪造通过。
- build_input_bindings：仅验收 --help。实际绑定还需完整 vendor、原始问题/需求表、问题绑定 manifest，以及对象/路线和证据审查。
- providers：仅提供未执行源码。没有模型、安装脚本、依赖锁、权重、现成运行许可或凭据。
- 原 tests/test_runner.py 的 13 项 archive 集成测试未打包；其来源 hash 在 PROVENANCE.json。完整候选上的结果不能替代此最小包的验收。

直接运行全部发现命令 python -S -B -m unittest discover -s tests -v，在未恢复来源材料时会有 2 个预期缺文件 ERROR；这不属于本包通过目标。需要复跑原 18 项 scope 测试时，先按 TEST_PLAN.json 恢复受锁定的原文件，再运行其中的 full_original_scope_command。不要用 mock 或伪造文献数据绕过这两项。

## 文件与来源

PROVENANCE.json 逐项记录原样复制源码的 SHA256。VENDOR_MANIFEST.json 与冻结候选完全相同，未修改其 94 条原校验项；其中本包保留 19 项，75 项未附。MISSING_LOCAL_FILES.json 列出每个缺项的相对路径、预期 SHA256、用途、运行路径关联、精确来源与下一动作。75/75 缺项均已与下述用户此前附件中的具体成员逐字节 SHA256 核对，不是推定附件拥有或要求另找未知资料。PACKAGE_MANIFEST.json 校验这个独立包；它不会取代原 vendor 清单。

代码公开基线：
- [ClearEval-public 主分支固定基线](https://github.com/404NotFound422/ClearEval-public/tree/a7961f468d8f1a8c28f9cc928199b26fba334883)
- [此前研究说明快照](https://github.com/404NotFound422/ClearEval-public/blob/3bc06c6b5ffe0bd32ff6d25fc74d181442a5934a/research/supplement-validation-20261018/README.md)

本候选仍含恢复包的新增研究代码，并不声称可只从上述旧公开基线重建全部 vendor。恢复包与本候选未发现独立 LICENSE；本包不新增或推定开源授权。源码来源由用户恢复包和逐文件 hash 记录，原有权利不变。论文/协议全文、真实问题集、真实 raw、带私有绝对路径的证据文件与运行凭据均不在包内。

## 缺项来自哪些此前附件

以下是用户在 2026-10-16 已交付材料的准确文件名；本公共仓库不重新附带其私有/受限内容：

- ClearEval_固定输入修复包_第1部分_共4部分.zip
- ClearEval_固定输入修复包_第3部分_共4部分.zip
- ClearEval_固定输入修复包_第4部分_共4部分.zip
- ClearEval_方案生成范围修订与报告差异_20261016.zip（其中包含程序增量补丁.zip）

每个目标文件使用哪个附件、哪一层 ZIP、哪个成员路径，都在 MISSING_LOCAL_FILES.json 的 verified_sources 字段；没有公开私人 Library ID。无需为了纯工程测试取回这些附件。若本地已没有附件，应先重新取得已交付的正确附件，不能把 clone 旧公开 main 当作相同研究版本。

当前原 verify_vendor 对整个历史快照一律校验，其中包括新 runner 不执行的 5 个旧覆盖模块，以及由旧 runtime 导入耦合的题集/合同 fixture；75 项并不等于每次新实验都科学上需要 75 项。下一步应审查并重构独立的最小 runtime manifest，保留历史快照校验，而非盲目下载全部旧档案或擅自删锁。详见 RUNTIME_GAP_AUDIT.md。

## 本地接手顺序

1. 先运行上述无依赖测试并核对 VERIFICATION.json。任何缺失、失败或 hash 不同都先停止。
2. 先阅读 RUNTIME_GAP_AUDIT.md 与 MISSING_LOCAL_FILES.json，确认选用的正式执行路径并准备最小 runtime 拆分；本包未实施该重构。若需要复现现有完整候选，按 verified_sources 的准确附件名、嵌套 ZIP 和成员路径定位原文件，放到 candidate 根目录对应路径并核对 SHA256；不应要求先下载所有旧输出。保留原 vendor 字节，真实资料留在本地；不同版本、重新抓取网页或虚构样本不能替代冻结证据。
3. 运行 python -S -B verify_package.py --require-complete-vendor。本公开包预期返回 2，明确表示完整 vendor 未恢复。所有文件回填且 hash 一致后才可能返回 0，但这也只是完整性检查。
4. 再修复/确认本地完整执行依赖与输入契约。原始问题/回答、六轴 demand、metadata、单一 evaluation_object/route、原题绑定 task evidence、可审查 reference constructor，以及 encoder/judge 配置须全部真实且冻结。20 项候选不是旧 B20，不能据此默认已批准。
5. 按原 runner.prepare 的输入结构构建本地 manifest，再做完整集成和独立复核。此包不提供伪造的可执行 manifest。prepare 的输出仍是 PREPARED_NOT_APPROVED_OR_EXECUTED。
6. 模型正式执行留在本地：先核验真实模型依赖、固定 revision/权重和执行文件 hash，建立绑定最终 plan/code 的本地明确许可与预算，再执行。不要为了通过而安装替代模型、制造 embedding 或复用旧 raw 为新结果。

同样应保留 INPUT_SCOPE_UNSUPPORTED：真正未知当前阶段、混合范围和冲突仍为技术阻断，不得计算成真实缺步或科学失败。

有关依赖层级、缺失模块及模型核验边界，见 DEPENDENCIES.md。
