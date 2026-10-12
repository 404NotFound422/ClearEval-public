# ClearEval 实验报告与重新分解实证

2026-10-12 细节技术调研：[十个真实失败问题的原因、文献适用性与最小模块](technical_modules_review/CASES_zh.md) · [具体验证计划](technical_modules_review/VALIDATION_PLAN.md) · [最近似工作审计](technical_modules_review/PRIOR_ART_AUDIT.md) · [研究交付导航](technical_modules_review/README.md)。26 条核心来源，逐问题区分工程错误、语义误解与测量定义；新评分和模型请求均为 0。

2026-10-12 自动时间与阈值联合续记：[自动时间、条件联合与阈值报告](automatic_time_scope/REPORT_zh.md)；[HTML](automatic_time_scope/REPORT_zh.html)。无分支完整与继承分支点已区分，原SR/SP保留。

- **2026-10-12 自动标签关系续记：** [完整报告](automatic_label_relations/REPORT_zh.md) · [浏览版](automatic_label_relations/REPORT_zh.html) · [命令](automatic_label_relations/commands.md)。后续标签 28→32/32；历史标签 55→60/67、完整 CCE 44→48/67。失败迭代、七个实例和待执行 Cor 对照均已记录。新增模型调用 0。

- **2026-10-12 来源语义与条件联合续记：** [详细报告](semantic_source_revision/REPORT_zh.md) · [浏览版](semantic_source_revision/REPORT_zh.html) · [逐答案表](semantic_source_revision/semantic_04/per_answer.csv) · [实际命令](semantic_source_revision/commands.md)。来源辅助单值 CCE 5/8，另 2 份条件结果；自动候选仍 2/8。条件联合排名、来源依赖和八个完整流程均已记录，新增调用 0。

- **2026-10-12 后续 32 返回复算续记：** [详细报告](typed_label_transfer/REPORT_zh.md) · [浏览版](typed_label_transfer/REPORT_zh.html) · [逐答案表](typed_label_transfer/time_heading_candidate_01/per_answer.csv) · [实际命令](typed_label_transfer/commands.md)。受控完整 CCE 24/24，原确认批 2/8；确认结构转换 7/8。18 个完整成对观测、明确保留的反例、五个流程实例与整体未完成项均已记录。新增请求 0；以下较早的“编号未解决”仅指旧设置。

2026-10-12，本地交付。

- **最新实际修复与回放：** [完整结果、受控反例与三个全流程实例](typed_label_revision/REPORT_zh.md) · [浏览版](typed_label_revision/REPORT_zh.html) · [最终逐答案表](typed_label_revision/with_time_branches/per_answer.csv) · [实际命令](typed_label_revision/commands.md)。67 份历史返回中，标签分 11→64，完整单值 CCE 10→48；另 3 份答案提供 6 组完整条件 CCE。固定两模型五题子集完整 8/10、共同题 3/5；18 组实现检查通过。新增模型调用 0；定性 Cor 候选已准备，11 份旧 Cor 缺值尚未重新评价。以下条目保留各历史阶段的结果。

- **用户澄清后的职责修正：** [MAP2–AF488、原生 GFP、AF 家族近似与原 prompt 核对](missing_score_diagnosis/SCOPE_CORRECTION_zh.md)。确认原版无后来加入的 `UNCERTAINTY CONTRACT`；当前方法表已有 AF594，另找到直接偶联 MAP2–AF594 的来源。本次更新诊断，尚未按新口径重新评分。
- **缺分原因与待选方案：** [逐项证据、实例和处理选择](missing_score_diagnosis/REPORT_zh.md) · [67 份逐条诊断](missing_score_diagnosis/per_record.csv)。区分关系分解、适用性、查表、时间表达、原始判分 null 和结构引用错误；本轮只诊断，等待用户选择后续方案，没有修改分数。
- **评分器通用化与结论修订：** [完整说明与实际命令](scorer_revision/REPORT_zh.md) · [逐答案结果](scorer_revision/with_decomposition/per_answer.csv)。统一处理 67 份存档返回：完整 CCE 从 8 增至 9，接入前次来源分解后增至 10；原完整 8 份逐值保持一致。通用入口已运行，广泛自动完整覆盖仍未达标。
- **最新更正与单值复算：** [标签查表根因、时长中点与两份完整 CCE](LABEL_LOOKUP_AND_MIDPOINT_zh.md) · [机器结果](label_lookup_midpoint.json)。FPC03 原有兼容值被同名末行的 null 遮蔽，按题目通用神经元范围查询后 Eff=0.3451；FPC07 按 33.5 h 中点复算 Eff=0.2423。两份作者复算都有完整单值，旧报告中的“未得到单值”是此次修正前的结果。
- **完整项目文档：** [浏览版 HTML](REPORT_zh.html) · [可编辑 Markdown](REPORT_zh.md)。覆盖目标、E1–E6 设计安排、各轮改进、真实结果、未完成事项、五个全流程案例，以及旧 CCE 有分而新流程缺项的原因。
- **两份答案的大模型重新分解：** [浏览版 HTML](LLM_DECOMPOSITION_zh.html) · [可编辑 Markdown](LLM_DECOMPOSITION_zh.md)。逐行来源、计入范围和原函数计算；FPC03 核心 80 h，FPC07 典型核心 27.5–39.5 h，后者得到条件性完整 CCE 区间。
- **核对范围：** [说明](QUALITY_CHECK_zh.md) · [实际结果](verification.json)。1,197 项机械检查通过，70 条公式记录、142 个来源文件、54 处本地链接。计数不是科学独立样本数或专家验证数。
- **机器可读材料：** [主要实值和来源](evidence.json) · [两份分解的输入输出](llm_decomposition.json)。
- **实际离线脚本：** [分解注释与原函数复算](reconstruct_examples.py) · [报告核对与 HTML 生成](verify_report.py)。

本次没有新增本地/API 模型请求。两份新语义读解由当前会话模型完成，属于作者分析；未冒称冻结 Qwen 新试次或独立专家核查。冻结主分数、原返回、原状态文件均保留。专家和湿实验依赖仍未完成，论文总目标未宣称完成。
