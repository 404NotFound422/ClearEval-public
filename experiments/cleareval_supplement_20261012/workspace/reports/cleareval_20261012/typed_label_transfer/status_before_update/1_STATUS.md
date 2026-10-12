# ClearEval 当前状态

2026-10-12 标签修复离线续记：67 份历史返回、40 个不同全文中，标签可计算 64/67、完整单值 CCE 48/67；另有 3 份答案的 6 组条件 CCE。原始 SR/SP 与旧直接 Cor 判分保留。历史 E2 完整配对 12/15，编号及步骤合并敏感性仍存在；固定两生成模型五题子集完整 8/10、共同题 {21,22,248}。本轮新增模型请求 0，额度仍 438/438；新定性 Cor 候选仅准备完成，11 份旧 Cor 缺值未被填补。作者注释不计专家或新独立评价。[本轮结果、来源与实际命令](../../../reports/cleareval_20261012/typed_label_revision/REPORT_zh.md)。整体研究目标仍未完成；下列旧 v5 数值保留历史含义。

更新UTC：2026-10-10T14:09:25.373672+00:00。四小时授权固定止于2026-10-10 22:23:18北京时间。模型批次已终态；本轮计算和论文交付已完成，科学有效性及外部资料仍有具体缺口，整体目标未全部完成。

最新统一v5已处理67份已有返回。全部五项直接评分、Com、Cor和原SR/SP逐值等于冻结fw3。v3纠正目录匹配，v4恢复明确原文来源；v5继续纠正适配器自行构造的native自环，按原接口保留fluor键而不凭reporter身份制造marker关系。全部历史版本、来源及未知项保留。处理次数含重复与变体，不能算作独立任务。

E2实际21全文、15对；最新0/21完整CCE、0/15双端完整。顺序冲突和时长删除各3/3响应；纯编号漂移、合并敏感和步骤删除SR仅1/3下降仍是论文有效性问题。历史9个替代路线候选有7对完整数值（q21–23子批6对＋q248一对），专家确认0；字段修复子批的9份返回对应6对，不是总体9对。

E4为Qwen14/15实际返回、Codex12/12；直接分可算重复的25/25与19/25组极差均0，跨来源21/25组可比、3组均值不同。最新完整CCE分别3/14与1/12，不能宣称科学准确性大幅提升。

新两生成模型同五题：时间10/10，标签2/10，完整CCE2/10，共同完整题1/5（['22']）。共同完整集完成2000次同步任务抽样及1种有序穷举，全部五题的部分界另完成2000次抽样及3125种穷举；两者分母不同，共同集过小时抽样会退化。来源家族因同题跨模型来源不一致尚未抽样（0行）。两模型Com/Cor方向相反支持小队列的条件性互不支配，不作全库排名。

台账全包388/394，本轮94/100；开发27、E2 21、E4 30、确认16。四小时新增33次（Qwen22、Codex11）；本窗口无Llama，较早3条仅存历史并排除当前验证。总计次余额6，但既定阶段上限只余开发3次；无在途或新计划请求，不自动重试，时间延期未增加调用上限。

仍待：具体标记关系/知识库及适用范围、表示稳健性、来源适用性及独立确认；一位专家5＋15回传0/20；湿实验0观测。现有指标不因缺一项整份清零，native原输入契约问题已由软件修复，不再统称等待专家豁免。

[详细设计、例子、排查与论文问题](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round2_20261010/four_hour_extension_20261010/delivery/REPORT_v5_zh.md) · [最终真实数值](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round2_20261010/four_hour_extension_20261010/delivery/current_readout_v3/README_zh.md) · [英文Methods/Results](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round2_20261010/four_hour_extension_20261010/delivery/MANUSCRIPT_v5_EN.md) · [当前索引](C:/ClearEval/ClearEval-public/artifacts/cce_validation/CURRENT_RESULTS_INDEX.md)。

下一条恢复命令只检查已有交付与台账，不调用模型：

```powershell
Set-Location C:\ClearEval\ClearEval-public
& 'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe' -X utf8 scripts/cce_finalize_four_hour_delivery_v3.py --check
```

[此前入口逐文件存档](C:/ClearEval/ClearEval-public/artifacts/cce_validation/optimizer_round2_20261010/four_hour_extension_20261010/delivery/canonical_v4_before_native_contract_repair/manifest.json)。输入或配置未变的成功结果直接复用。
