# OEQ 改进与人工审核入口（2026-10-05）

本分支交付评价器代码、测试和运行说明。主线是组织光透明开放题的多答案兼容、关键错误识别和需求级答案匹配。现有公式保留，新增来源、实体角色、局部条件范围、未知传播、固定输入重复评分和受审目标数据的验证。

## 开始人工审核

完整审核表保存在本地未分发材料中；使用者配置审核材料目录后打开：

    <本地审核材料目录>/scientific_review_form.html

下载与源码分发不同：完整答案及机器审核记录继续保留在上述本机材料目录，本 Git 分支没有包含它们。审核表有 12 个问题、24 份完整真实答案，可保存草稿和导出 JSON。先独立阅读题目与完整答案，再打开机器辅助证据；表单会记录辅助暴露，机器输出不算独立专家标签。

先审核原题 97 和 172：题目要求的阶段范围、科学必要条件、允许的单方法替代，以及每份完整方案是否满足这些条件。其余问题可逐步继续。同目录的 independent_scientific_review_packet.json 是原始审核包，domain_comparison_contract.json 是公平对照约定。

这 24 份答案已经用于开发修正，不能再作为未暴露确认集。独立科学金标准目前为 0；科学有效性、多解接受优势和正式领域比较仍待独立审核。多目标关系需要可比且有来源的目标值和独立关系标签；不评价成像结果。

## 底层代码

- OEQ_run_grading_new.py：正常开放题入口，benchmark 评分与保存、续跑、诊断输入接入。
- oeq_quantity_audit.py、extract_clearing_time.py：原文定位、数量角色、重复时长和范围/复合动作检查。
- oeq_robustness.py、oeq_fidelity_impact.py：抽取忠实性、未知状态、人工参考与评分影响接口。
- oeq_workflow_diagnostics.py、experiments/construct_validity/：单方法候选、要求范围、来源条件与目标关系诊断。
- oeq_score_stability.py、experiments/judge_reliability.py：冻结输入、重复评分记录与可比性。
- tests/：机械反例、主流程和恢复检查。

--robustness-inputs 可读取绑定原题原答的人工抽取和目标数据。软件不会生成专家标签或目标测量，也不会把格式违规或缺证据自动提升为关键科学错误。

## 验证与运行前提

提交前，在本机完整工件环境运行了离线检查：764 项，763 通过、1 跳过，0 失败、0 错误；在线模型调用为 0。记录见 [离线复验摘要](verification_test_summary.json)。这些是工程检查，科学验证仍待独立标签。

本分支包含来源注册信息及检查规则；原始文献全文、HTML 和 PDF 工件保留在本地来源包中。相对路径和 SHA-256 见 [外部来源工件清单](external_source_artifacts.json)。在新的 clone 中运行依赖实际来源的检查或正常 benchmark 前，先恢复匹配的 KnowledgeBase/primary_sources/ 工件。缺文件或哈希不匹配会失败；仅 clone 本源码分支不能声称已经复验上述完整工件结果。

来源包是本地未分发材料。将匹配工件恢复到当前 checkout 的 `KnowledgeBase/primary_sources/`，并核对工件清单的哈希。来源规则仍待专家审核；知识库补充由用户证据层完成。

固定需求向量绑定旧题快照。使用匹配版本预检：

    python OEQ_run_grading_new.py --preflight-only --question-file dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json --model-config config/local_ollama.example.json

真实 API 配置由本地 config/config.yaml 提供，或显式指定无密钥的本地 Ollama 示例配置。安装仓库已有依赖，在恢复来源工件的 checkout 中运行离线检查：

    python -B -m unittest discover -s tests

更完整的使用方式见 [运行说明](../oeq_development_runbook_zh.md)。科学未知保留为 U，不应无限重调教师来覆盖它。GitHub 分支发布与服务器生产部署分别核对。
