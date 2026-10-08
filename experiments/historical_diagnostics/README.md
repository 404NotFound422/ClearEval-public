# Historical diagnostic experiments

本包保存近期三个实验中的必要数字与出处，使用 Python 标准库离线重新汇总。
无需 API、Ollama、模型权重、论文全文、Office 或第三方 Python 包。

从仓库根目录运行（Python 3.10+）：

```sh
python -B -m experiments.historical_diagnostics
python -B -m experiments.historical_diagnostics --json
python -B -m unittest discover -s experiments/historical_diagnostics -p 'test_*.py'
```

也可直接运行 `python -B experiments/historical_diagnostics/summarize.py`，结果相同。

CLI先核验4份fixture的SHA-256及大小，再检查字段、数值范围、配对差值、
变体共用题号和分母。校验失败返回退出码2；成功返回0并输出重新计算的摘要。
`source_manifest.json`保存原文件SHA-256及`review_artifacts/...`相对来源标识。
原文件未随包发布，CLI只验证随包数字的一致性；哈希不代表科学效度验证。

## 数据范围

| Fixture | 冻结数据与口径 |
|---|---|
| `selfcheck_pairs.csv` | 9/23归档、9/24复核的12个开发配对，每侧一次自动评价；2升、3降、7平，平均差+0.003480012分，量表0–100。3对实际请求相同仍出现+12.50、−6.226599、0分差。相同请求是原归档检查结果，本包不含长请求文本。 |
| `component_probes.json` | 9/24直接执行评分组件的12条件、11个不同结构输入；C0=A1。输入与六个组件数值保留，不把组件测试称为完整方案通过。条件文案沿用历史记录；推荐靶点是否同时必需，仍需按题意审定。 |
| `gen_step_metrics.json` | 9/29同60份参考的5个确定性文本变体，共300份已保存评分输入。原文、倒序、重复的SR/SP均1；删交替步骤为0.692173701/1；参数×10实际改变37/60份，改变的37份仍为1/1。 |
| `protocol_judgments.csv` | 9/30报告的19片段×2模型=38次开发裁判，加ERR14例×2=28次，共66调用。主要对照使用同13例；D05缺乏直接阴性依据，保留其记录但排除主对照。引用校验后的满足、违反、未决、技术失败分别保留。 |

19片段来自3篇论文、4个相关任务族；标签由助手草拟，独立专家标签0。
替代路线属于放宽方法清单的开发任务。ERR是把原版提示迁移到相同任务、片段
和证据的对照，既不是官方ERR测试集成绩，也不能据此宣称整体科学准确率。
本包不增加置信区间或湿实验成功率；未决与技术失败各自计数。

## 纯函数文本对照

`mutations.py`从原`prepare_metric_controls.py`提取确定性逻辑，接收独立字符串
步骤序列，不访问文件、网络或模型，不改变输入：

```python
from experiments.historical_diagnostics.mutations import all_variants

controls = all_variants(["Mix the sample.", "Wait 2 hours."])
assert controls["multiply_parameters_by_10"]["prediction"][1] == "Wait 20 hours."
```

原步骤序列、逆序、重复、保留下标0/2/4等步骤、关联单位数值乘10，均沿用旧版
逻辑；数值模式并不识别所有科学参数，零值等情况也可能替换后文本不变。
这只是文本扰动，不自动产生经专家审定的实验失败标签。

纯函数的`parameters_changed`计数该变体实际执行的数值替换。
历史fixture中的同名字段沿用旧记录：它是参考文本的参数正则命中次数，在每个
变体中重复保存；真正的数值编辑仅发生在`multiply_parameters_by_10`。
是否改变文本以`text_changed`为准，不能将未改变的23份计为指标漏检。

## 与当前评估器的区别

这些是旧版本运行保存的分数及判定；CLI重新汇总数字，不重新调用当前ClearEval
评估器，不重新计算GEN语义嵌入，也不把旧缺陷自动归为当前代码仍存在的问题。
GEN旧运行使用BioProBench提交`cf00fecd62583b98350cc48e26a29c92d3f21e5d`、
MPNet revision `e8c3b32edf5434bc2275fc9bab85f82640a19130`及0.7阈值。
复算这些数字不需要下载上游实现；重新进行模型或科学验证应新建独立批次。

仅发布精简数字、组件结构输入和来源索引；原始长请求/响应、流式输出、论文
全文、语义模型、运行缓存和文档渲染产物均留在本地。
