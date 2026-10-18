# 完整运行时缺口审计：不是“再下载全部旧档案”

本包满足 19 项默认工程测试的依赖闭包。正式 prepare/execute 的最小依赖清单尚未从恢复的历史快照中拆开；因此当前原 verify_vendor 的 75 个缺项不能被解释为 75 个都属于每个新实验必需的科学材料。

## 已确证的过宽校验

runner 在模块导入时明确预载 representation/ 与 matching/ 的 5 个覆盖模块；同名原副本仍在 VENDOR_MANIFEST 中，verify_vendor 逐项要求其字节存在。对这个新入口而言，以下原副本仅保留历史快照完整性，不是实际导入实现：

- vendor/source/oeq_simple_representation.py
- vendor/source/oeq_simple_time.py
- vendor/source/oeq_atomic_alignment.py
- vendor/source/oeq_capacity_matching.py
- vendor/source/oeq_quantity_assignment.py

本包没有删改原校验，也未把不完整 vendor 宣布为完整。此结论只针对新 runner 的预载路径，不推广至旧 CLI。

## 仍在真实运行路径内的历史耦合

- OEQ_run_grading_new 模块导入时直接读取 6 张 KnowledgeBase 表及 dataset/Q+AR/src/question_final.json；这些不随本包。更少的新案例输入并不会自动解除旧题集的导入要求。
- 同一 native 模块导入 sample_scope_runtime，后者的 SCOPE 构造会读取 contract/fixtures/contracts.json 与 questions.json。名称叫 fixture 不代表可以现在删掉；这是需重构的显式依赖。
- runner.calculate 调用 integration_qualification.demand_status，后者每次读取 integration_archived_demands.json。它比对原题+向量是否与历史审查一致，而非一个新的模型输出。
- source_reference() 会读取 iDISCO 来源锁、锁定的派生参考和原协议文本。两项 solvent-reversal 测试确实依赖这些字节，不能用 mock 锁或伪造材料把它们计入独立通过。
- 多种方法的来源适配器/证据当前全部在全局 vendor 清单中，即使某次只选择一种方法也会被先校验。不能只凭文件名断言某份证据永不需要。
- vendor 某些旧函数有清单外的延迟 legacy imports。完整 vendor 校验通过仍不等于所有旧 CLI/所有 reference constructor 都可执行；必须针对最终选定功能重新审查闭包。

## 精确获取来源

MISSING_LOCAL_FILES.json 的每一项均给出目标相对路径、预期 SHA256、用途与 verified_sources。来源为用户此前交付的固定输入修复包第1/3/4部分及方案生成范围增量附件的准确成员；所有 75 项均已逐字节匹配。文件名、嵌套 ZIP 和成员路径足以定位，无需公开私人下载 URL 或 Library 标识。

那些材料不在本次公共工程包中。该映射不代表论文全文已获公共再分发许可，也不代表当前网页能重建相同冻结证据。原文/真实题集/带私有路径的证据应只在用户有权使用的本地环境处理。

## 最小修复建议（未实施、未验收）

1. 保留历史快照 VENDOR_MANIFEST，不把删条目冒充修复。
2. 为新 runner 单独建立经过独立审查的运行时 manifest，分开实际调用代码、必要查表/评分契约与按 reference constructor 选择的真实外部证据。
3. 将不依赖新案例的历史题集/合同初始化与新评分函数解耦；未知或缺证据仍明确阻断，不默认转成零分。
4. 对每个受支持 constructor 在无旧父目录依赖的干净环境验证输入→canonical→matching→structured/direct→结果和 receipt 的完整链，确认来源锁、预算与许可仍生效。
5. 最后冻结真实输入、模型环境和执行许可。当前包不宣称完成此重构，也不自动运行模型。
