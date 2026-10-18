# 依赖与恢复边界

## 已独立验收的层级

CPython 3.12 标准库足够运行 run_engineering_tests.py 选择的 16 项纯代码 scope 测试、3 项包边界、verify_package.py 和各 --help。原 scope 文件的另 2 项 solvent-reversal 测试依赖未再分发的受锁定原来源资料，详见 TEST_PLAN.json。numpy/scipy 被延迟到实际 matching 函数内部，不能据此认为匹配计算也不需要第三方包。

本包包含 scope 回归实际导入的 18 个 vendor Python 文件，另外保留原 candidate 的 runner、build_input_bindings、representation、matching、providers、schema、scope 源码和完整 VENDOR_MANIFEST。它是最小工程测试闭包，不是所有 runner 分支的完整运行时依赖闭包。

## 未随包附带的运行依赖

- 数学 matching：numpy、scipy，分别在 quantity align / capacity metrics 中使用。
- canonical/structured 验证：jsonschema。
- 本地 encoder：sentence-transformers、torch、transformers、numpy 及其固定传递依赖；还需 providers/requirements.lock.txt、providers/artifacts/model_manifest.json 和模型文件。
- 完整 vendor 源码及数据：逐项见 MISSING_LOCAL_FILES.json。包括 OEQ_run_grading_new、oeq_scientific、oeq_sr_assessment、来源适配器、知识表、输入题集、原证据与 scope contracts 等。对未覆盖函数，完整 legacy 模块还存在延迟导入；必须在恢复后按实际选用路径重新做闭包检查，不能宣称全 legacy CLI 可用。

当前完整候选测试主机可见 numpy 2.3.5、scipy 1.17.0、jsonschema 4.26.0；这些只是观测版本，不是可重复安装锁，也不是 encoder 兼容性验收。此独立包测试使用 -S，不依赖这些已安装包。没有安装/运行任何模型。

固定 encoder 目标仍为 sentence-transformers/all-mpnet-base-v2，revision e8c3b32edf5434bc2275fc9bab85f82640a19130。恢复交接记录中的历史权重 SHA256 为 78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658（437971872 字节）；这是待本地核验目标，不是本包内已存在或已验证的权重。本包不附下载、安装或调用指令，避免把未经核验的环境当成现成执行许可。

## 科学材料与公开来源

真实研究材料只由本地用户从有权使用的恢复包或官方来源取回。固定公开入口可帮助人工核对文献身份，但不能替代原 task evidence、适用性审定、哈希和本地恢复包：

- FDISCO：原证据记录引用 https://pmc.ncbi.nlm.nih.gov/articles/PMC6357753/#sec13
- MACS：原证据记录引用 https://pmc.ncbi.nlm.nih.gov/articles/PMC7175264/

本包没有再分发这些论文全文或协议文本。公开可读不等同于已经确认允许任意再分发，也不证明本地冻结资料与当前网页完全相同。
