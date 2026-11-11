# 文献证据补充（2026-11-11）

将证据层固定版本中的 **119 篇文献**转换为 ClearEval 已有的
`Text / Text_Reference`、`TextN / TextN_Reference` 格式，写入
[`KnowledgeBase/article_chunk`](../../article_chunk/) 的 `Evidence_*_result.json`。
其中方法类 44 篇、应用类 48 篇、综述类 27 篇，119 个 DOI 互不重复。

原有 18 份按方法汇总的文件保留，因此该目录现在有 137 个 JSON 文件。
119 是此次转换的来源文献数，不是相对旧库净新增的文献数；旧方法汇总未统一登记 DOI，
可能与本次逐篇文献卡交叉，不能把 137 个文件当作 137 篇独立论文或实验。

## 阅读方法

- `General_Description` 给出文献身份和类型；`TOC_Method_Name` 只采用来源明确登记的方法名。
- 组织、时间、形变、荧光及保存记录放入对应原有字段；实验、处理、测量、比较和结果放入
  `Application`，每条文字开头保留来源字段名，避免混淆操作条件与实验结果。
- `TextN` 是证据层结构化内容的逐字段文字呈现，**不是论文原文逐字引句**，不新增科学结论。
  整条记录中的单位、分组、样本数、未知值和限制一起保留；`null` 仅表示来源中的空值。
- `TextN_Reference` 给出 DOI、固定版本中的文件、JSON pointer 和 SHA-256；来源位于下述附件。
- `Note` 中的样本范围、更正、版本选择和强制组合要求必须一起阅读。引用相同 sample_id
  不意味着该样本的所有条件都能推广到每个结果；结果级和图版级绑定仍优先。
- 综述保留二手证据性质，不能将其引用的原始研究当成此次重新阅读过的独立实验。

## 来源及状态

固定 GitHub 提交：`5e3a711befb3952a2e39f4d53fc9c9f1a7ac0d22`，
源目录 `TOCAgentProject/KnowledgeBase/evidence_expansion_20261019`。
已将本地索引及校验清单的 Git blob 身份与远端核对一致；归档内 2,331 个文件逐个校验。

[`source_release.zip`](source_release.zip) 保存完整冻结版本，包括当前记录、必需伴随材料、
更正、原有历史材料和来源定位。**归档存在不等于全部内容当前有效**：
以其中 `active_index.json`、每篇 `version_selection.json` 及其必需支持材料为准。
历史材料仅供追溯；转换排除了明确被替代的主张，并采用已登记的 current/effective/reviewed 视图。

原来源中 9 篇为 default eligible，110 篇为 candidate_pending_gates。
这些状态在每篇 `Note` 和清单中原样保留；本次入库不改变其准入状态。
119 篇之外的目录记录、部分完成材料及未闭合材料未生成证据卡。
这次仅扩充文献资料，不改评分知识库数值、题目、答案、评分规则或历史分数。
现有评分及 KB-RAG 入口不会因为增加这些文件就自动使用候选证据。

[`manifest.json`](manifest.json) 提供每篇卡片、文献类型、DOI、来源状态、选定文件、
必需支持文件、逐条指针和卡片哈希；[`papers.csv`](papers.csv) 是便于浏览的清单。
自动字段归类不替代科学复审，无法直接归入现有类别的内容仍可在完整来源附件中查阅。

## 复现及校验

在仓库根目录运行（Python 标准库即可）：

```sh
python scripts/import_literature_evidence.py --check
python -m unittest discover -s tests -p test_literature_import.py
```

第一条核对完整来源包并逐字重建所有卡片和清单；去掉 `--check` 可重新生成。
回归检查覆盖格式、119篇身份、来源状态、全部指针、M009 已替代主张、历史根排除、
REV_38159104 模态更正和空值语义。校验通过说明转换可回放，不代表新增湿实验验证。
