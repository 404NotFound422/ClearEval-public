# 依赖与恢复边界

## 已独立验收的层级

当前工程目标为CPython 3.12下原18项scope测试、3项包边界、verify_package.py和各--help。原来2项solvent-reversal测试所需锁定来源现在已按原hash随包交付，纳入21项目标；实际结果见VERIFICATION.json。numpy/scipy 被延迟到实际 matching 函数内部，不能据此认为匹配计算也不需要第三方包。

本包已补齐原VENDOR_MANIFEST的94项代码/数据；原冻结runner和VENDOR_MANIFEST字节不变。这解决原75项文件缺口，尚不代表所有运行分支的真实模型依赖均已验收。

## 未随包附带的运行依赖

- 数学 matching：numpy、scipy，分别在 quantity align / capacity metrics 中使用。
- canonical/structured 验证：jsonschema。
- 本地 encoder：sentence-transformers、torch、transformers、numpy 及其固定传递依赖；还需 providers/requirements.lock.txt、providers/artifacts/model_manifest.json 和模型文件。
- 原vendor源码及数据现已全部交付，当前MISSING_LOCAL_FILES.json为空。对未覆盖函数，legacy模块仍可能有清单外延迟导入；应按实际选用路径核查，不能推定所有旧CLI可用。

当前完整候选测试主机可见 numpy 2.3.5、scipy 1.17.0、jsonschema 4.26.0；这些只是观测版本，不是可重复安装锁，也不是 encoder 兼容性验收。此独立包测试使用 -S，不依赖这些已安装包。没有安装/运行任何模型。

固定 encoder 目标仍为 sentence-transformers/all-mpnet-base-v2，revision e8c3b32edf5434bc2275fc9bab85f82640a19130。恢复交接记录中的历史权重 SHA256 为 78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658（437971872 字节）；这是待本地核验目标，不是本包内已存在或已验证的权重。本包不附下载、安装或调用指令，避免把未经核验的环境当成现成执行许可。

## 科学材料与公开来源

本次直接附带原75项缺文件及来源归属说明。逐文件路径/hash见DEPENDENCY_RESTORE_MANIFEST.json，来源依据见THIRD_PARTY_SOURCES.md；原文与派生证据保持原锁字节。来源齐全不等于每个新题都适用，仍需正式manifest绑定。
