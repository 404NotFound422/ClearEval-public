# ClearEval 工程代码与完整历史依赖

**原先省略的75项文件已直接补到本目录的原路径；原VENDOR_MANIFEST共94项现已齐全。** 包含评分主程序、知识表、原题与合同数据、来源证据和scope契约，不需要再寻找旧分卷附件来补这75项。完整性与工程检查的实际验收记录见 [VERIFICATION.json](VERIFICATION.json)。

## 现在能运行什么

在本目录执行，使用CPython 3.12，无需安装模型：

```sh
python -S -B verify_package.py --require-complete-vendor
python -S -B run_engineering_tests.py
python -S -B runner.py --help
```

完整vendor校验目标是94项原hash一致、缺0项、退出码0。默认工程目标现在是原18项scope测试＋3项包边界，共21项；原来因来源未附而没运行的2项已纳入真实来源校验，旧19项结果保留在history/268fc731。

上述是完整性和工程测试。完整科学评分仍需要实际Python/模型依赖、正式输入manifest、证据适用性和一次真实端到端验收；本次没有encoder、judge调用或新科学分数。`prepare/verify/execute`的完整真实流程尚未验收，帮助页通过不替代它。

## 文件直接在哪里

- 主评分源码：`vendor/source/OEQ_run_grading_new.py`、`vendor/source/oeq_scientific.py`。
- 其余75项的准确相对路径、来源与SHA256：见 [DEPENDENCY_RESTORE_MANIFEST.json](DEPENDENCY_RESTORE_MANIFEST.json)。
- 原94项锁定清单：`VENDOR_MANIFEST.json`，字节未改。
- 当前缺失清单：`MISSING_LOCAL_FILES.json`，files为空；只表示这94项齐全。
- 数据来源与使用声明：`THIRD_PARTY_SOURCES.md`。原用户提供文本按原字节重打包；公开来源材料保留对应归属和许可。
- 旧75项省略清单及旧README、测试入口、验证结果：`history/268fc731/`，用于解释旧提交的19项边界，不作为当前缺失状态。

更新前保留本地修改与结果，先核对diff及逐文件SHA；不覆盖本地派生源码，不执行覆盖式重置。RUNTIME_GAP_AUDIT.md保留为268fc731的历史说明，其旧缺失数量不代表当前状态；当前以MISSING空和实际验包结果为准。

## 完整评分下一步

1. 先运行上面的94项校验和21项工程检查，保存实际输出；任何失败先定位，不改原锁以求通过。
2. 按 [DEPENDENCIES.md](DEPENDENCIES.md)配置数学、schema与固定encoder环境，核实际权重、依赖和执行文件hash。模型与凭据不在仓库中。
3. 冻结实际原题原答、对象/路线、六轴需求、同证据参考、量表和失败策略；C候选绑定文件不能代替P20正式manifest。
4. 修复共用pair_inputs范围错误对独立Co/Eff/direct的连带阻断，单独标记scope准备失败。本包未实现这项模块解耦。
5. 使用一个真实输入验收实际提取、编码、裁判、计算、raw和receipt全链，再开展同版V5与共享首遍的V4。正式模型执行留在本地，明确配置预算和运行许可。

[完整实验状态与计划](../CURRENT_STATUS_zh.md)说明V1至V5的实际进度。历史vendor齐全并不保证所有旧CLI或任意reference constructor都已跑通；具体运行路径仍需独立验收。
