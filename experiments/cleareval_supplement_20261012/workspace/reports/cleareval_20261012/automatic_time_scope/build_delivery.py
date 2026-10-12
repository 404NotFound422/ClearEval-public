"""Source-bound documentation of automatic time, conditional CCE and sensitivity."""
import csv,hashlib,json,re,sys
from pathlib import Path
from datetime import datetime,timezone
from markdown_it import MarkdownIt
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent;BASE=OUT.parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
can=b.read(OUT/'canonical32_04/results.json');old=b.read(OUT/'archived67_04/results.json')
rows={r['cell_id']:r for r in can+old};validation=b.read(OUT/'validation.json')
joint=b.read(OUT/'joint_01/summary.json');threshold=b.read(OUT/'threshold_01/summary.json')
assert validation['checks_passed']==666 and all(r['passed'] for r in validation['checks'])
external=b.read(BASE/'automatic_label_relations/external_state.json')
for ref in [external['budget']['ledger'],*external['human_inputs'],external['wetlab_source']]:assert b.bind(ref['path'])==ref
b.save(OUT/'external_state.json',{**external,'checked_utc':datetime.now(timezone.utc).isoformat(),'new_model_calls':0})
def fmt(v):
    if v is None:return 'NA'
    if v and abs(v)<1e-6:return f'{v:.5g}'
    return f'{v:.6f}'.rstrip('0').rstrip('.')
def esc(v):return str(v).replace('|','\\|').replace('\n',' ')
example_ids=['R3C01__r0','R3C02__r0','R3C03__r0','R3C04__r0','R3C05__r0','R3C07__r0','R3C08__r0','FPC07','FPC13']
examples=[];example_inputs=[]
for cid in example_ids:
    r=rows[cid];source=Path(r['source_document']['path']);doc=b.read(source)
    opath=source.parent.parent/'original_source_documents'/source.name
    orig=b.read(opath) if opath.exists() else doc
    dest=OUT/'examples'/cid;dest.mkdir(parents=True,exist_ok=True)
    (dest/'submitted_answer.txt').write_text(orig['text'],encoding='utf-8')
    (dest/'scoring_source.txt').write_text(doc['text'],encoding='utf-8')
    casepath=source.parent.parent/'cases.json';cases=b.read(casepath)['cases']
    identity=next(x for x in cases if x['anonymous_answer_id']==cid.replace('__r0',''))
    assert hashlib.sha256(orig['text'].encode('utf-8')).hexdigest()==identity['answer_sha256']
    assert hashlib.sha256(identity['specific_question'].encode('utf-8')).hexdigest()==identity['question_sha256']
    (dest/'question.txt').write_text(identity['specific_question'],encoding='utf-8')
    b.save(dest/'evidence.json',{'result':r,'case_source':b.bind(casepath),'original_source':b.bind(opath) if opath.exists() else r['source_document']})
    example_inputs.append(b.bind(casepath));ledger=r['time_candidate_ledger']
    operation_table=[]
    for op in ledger['operations']:
        choices=op.get('duration',{}).get('options',[])
        explanation=op['scope'].get('basis',op['scope'].get('reason',''))
        choices_text='；'.join(str(x['bounds_hours'])+' × '+str(x['count']) for x in choices)
        operation_table.append('| '+op['operation_id']+' | '+esc(op['scope']['role'])+' | '+esc(op['source']['quote'][:125])+' | '+esc(choices_text or '—')+' | '+esc(explanation)+' |')
    sc='\n'.join('| '+s['scenario_id']+' | '+fmt(s['hours'])+' | '+fmt(s['metrics']['s_time'])+' | '+fmt(s['metrics']['Eff'])+' | '+fmt(s['metrics']['IA'])+' | '+fmt(s['metrics']['HV'])+' |' for s in r['conditional_time_results'])
    m=r['metrics'];mt='\n'.join('| '+k+' | '+fmt(v)+' |' for k,v in m.items())
    text=f'''# {cid}：实际评测全流程

[原题](question.txt) → [原提交全文](submitted_answer.txt) → [评分使用的全文](scoring_source.txt) → [来源、标签查表、时间账本和全部分数](evidence.json)。原提交答案与题干哈希均核对一致。

1. 本例复用真实模型返回：[已有解析/判分记录]({r['post_record']['path'].replace(chr(92),'/')})。本轮没有新增模型调用。
2. 标签关系沿用上一阶段自动来源规则及原 EGES 查表函数；原 SR/SP、参数完整性、四项直接 Correctness 判断保持不变。
3. 时间账本逐条保存来源、原阶段标签、修订后的计入范围、时间单位、重复次数、分支和未知项。时间公式接收分支内的总核心孵育小时数；不包括前处理、抗体/染色、成像和储存。显式试剂转换中的洗涤不能仅因出现 PBS 就删去。
4. 有限范围取中点；明确的 `or` 和可选步骤分别计算。这里的单一无分支时间为 **{fmt(ledger['hours'])} h**；`candidate_point_applied={r['candidate_point_applied']}`。完整的有限分支如下。没有有限分支时保留具体缺项，不填零。

| 分支 | 核心小时 | s_time | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|
{sc}

5. 每份答案按原公式计算 Com、Cor、Eff，随后 IA=min(CCE)、HV=Com×Cor×Eff。下表是结果文件保留的逐答案值。若候选没有唯一点而原结果有值，则该值仍属原先的来源解释，不能把它读成新确认的无条件分数；C08 就是这种情况。

| 分项 | 数值 |
|---|---:|
{mt}

**逐操作的取值路径**

下表摘录原文前 125 个字符方便阅读；完整文本、字符区间、分支内实际贡献、累计总量与重复解释在 evidence.json 中。

| 操作 | 计分范围 | 原文摘录 | 候选小时范围 × 次数 | 范围依据 |
|---|---|---|---|---|
{chr(10).join(operation_table)}

未决项：`{esc(json.dumps(ledger['issues'],ensure_ascii=False))}`。本例属于已暴露材料的开发复算；原 LLM Cor 理由、参考科学适用性和未核字段仍需单独评价。
'''
    (dest/'README_zh.md').write_text(text,encoding='utf-8');examples.append(f'[{cid}](examples/{cid}/README_zh.md)')

confirmation=[]
for r in can:
    if not r['cell_id'].startswith('R3C'):continue
    l=r['time_candidate_ledger'];branch='、'.join(fmt(s['hours']) for s in r['conditional_time_results']) or '无'
    note='自动无分支单值' if r['candidate_point_applied'] else ('沿用原 32 h 点；另列 20/32 h 分支' if r['cell_id']=='R3C08__r0' else '条件分支' if branch!='无' else '原答案截断，仍缺项')
    confirmation.append('| '+r['cell_id'].replace('__r0','')+' | '+fmt(l['hours'])+' | '+branch+' | '+fmt(r['metrics']['Eff'])+' | '+note+' |')
threshold_rows=b.read(OUT/'threshold_01/confirmation.json')
step_table=[]
for cid in sorted({r['cell_id'] for r in threshold_rows}):
    selected=sorted((r for r in threshold_rows if r['cell_id']==cid),key=lambda r:r['threshold'])
    step_table.append('| '+cid.replace('__r0','')+' | '+' | '.join(fmt(r['metrics']['sr'])+' / '+fmt(r['metrics']['sp']) for r in selected)+' |')
report=f'''# ClearEval：自动时间取值、条件联合评分与阈值复核

2026-10-12。本阶段新增模型调用 **0**，实际账本仍为 **438/438**。复用真实答案、已有 Qwen 返回、原 SR/SP 和原 EGES 函数；新增来源时间规则、离线复算、阈值敏感性和可审查的取值账本。

**新增结果与论文意义**

自动时间处理恢复了 R3C01、R3C04、R3C07 的完整数值 CCE，核心时长分别为 **34.5、72、8.5 h**。原 8 份确认答案现在有 **4/8 可由本候选得到无分支完整 CCE**；若保留 C08 原先“执行可选漂白”的单点，结果文件中的完整数值为 **5/8**。C02、C05、C08 另有明确条件下的完整结果，合计 7/8 至少存在一个可计算的条件；截断的 C03 仍未恢复。这里的“原确认”描述样本来源，本轮已使用这些材料开发规则，不能再称独立前瞻确认。

此前笼统的“5/8 单值完整”需要补充上述来源条件。程序能输出数字、来源支持一个唯一执行分支、科学判断正确，是不同的结论。全文、模型返回和旧数值都保留；本轮没有为了唯一化而挑最高分的分支，也没有把未知项清零。

| 实际队列 | 本轮前→后有时间分 | 保留历史点的完整数值 CCE | 本候选支持的无分支完整 CCE |
|---|---:|---:|---:|
| 24 份受控＋8 份原确认返回 | 26→29 / 32 | 26→29 / 32 | 28/32＝24 受控＋4 原确认 |
| 67 份历史返回 | 61→63 / 67 | 48→49 / 67 | 47/67；另两份沿用原冲突读数点 |

两批包含重复、变体和交叉来源，不能相加成 99 个独立样本。32 返回对应 20 个提交全文、14 个规范化全文；历史批次对应 40 个全文。历史输入还保留此前两份来源辅助时间记录，所以整批完成比例不是纯自动准确率。历史新增 FPC02 完整 CCE、FPC04 时间分；其余直接分数和已存在的有限时间分未变。

[后续逐答案结果](canonical32_04/per_answer.csv) · [历史逐答案结果](archived67_04/per_answer.csv) · [逐操作 JSON](canonical32_04/results.json) · [实际命令](commands.md) · [冻结配置](resolved_config.yaml)

**实验设计：把时间表达、操作范围和执行分支分开验证**

计算对象为原 prompt 中用于 EGES 的核心孵育时间。对每条已保存的操作，记录来源区间，判断是否属于核心处理，再解析该操作的持续时间与次数。使用已有模型操作分解作为输入，原文标题、重复句和父步骤用于补足明确关系。相邻正文中的“累计 72 h”替换初始贡献，不作为额外孵育相加；“每 24 h 更换”作为频率，不计成另一个 24 h。

每个确定执行分支分别求和：T_b = Σ n_i × d_i。显式有限范围 [a,b] 使用 (a+b)/2；这是用户允许的范围点值约定。它不适用于“至少”、未知时长、互斥的 `or`、或跨可选路线求平均。缺次数的 `each` 保留待定。非数字 overnight 按原规则 8 h；答案明确写 12 h 时使用 12 h。必需的成像前平衡计入，长期储存不计入。未知的并行排程不擅自作为串行总时长。

来源取值与规则验证的设计参考了 [HeidelTime（SemEval 2010）](https://aclanthology.org/S10-1071/) 对时间表达识别和规范化的区分；规则化并不能代替实验阶段判断。[CheckList（ACL 2020）](https://aclanthology.org/2020.acl-main.442/) 支持按具体行为设计边界、不变性与负向检查；这些文章没有验证本项目的生物学准确率。

本轮通过 **666 项检查**，其中包含 **26 个合成边界例**；校验 **2,071 处来源引用**和 **220 个来源文件绑定**。合成例、算术检查、与助手先前注释的一致性均不冒充独立专家验证。24 份原受控结果的所有分项保持不变。三个主动删除时长的历史对照仍是 NA。

**实际失败与修复过程**

| 版本/现象 | 定位到的原因 | 修复与真实验证 |
|---|---|---|
| `_01`：C01=82.5 h、C04=150 h，错误偏长 | 未识别复数 washes、重复洗涤继承抗体阶段、中文核染标题；把染色清洗当成核心孵育 | 以来源标题和操作角色修复，最终 C01=34.5、C04=72 h；均与先前逐条来源分解一致 |
| `_01`：C02 被输出单一 34.5 h | 可选核染中混合返工的核心转变未独立保留 | 改为“不执行可选部分”34.5 h；执行时有三项核心时长不明，保留已知小计及缺项 |
| `_01/_02`：FPC13 整条路线被算为 134 h | 只读取初始 48 h，遗漏来源中累计达到 72 h 的关系 | 复用可核查的累计来源记录，最终总量 158 h；原时间分完整保留 |
| FPC07 的 Time 字段含逗号及“typically 12–24 h” | 若按逗号截断字段，会丢失有限范围 | 完整字段解析为该操作 18 h、整条路线 33.5 h，与旧来源辅助结果相同 |
| C05 原文有两处二选一时长，C08 有可选漂白 | 原文确实对应多种执行情况，不是 JSON 缺失 | 自动枚举 C05 的 14/17/18/21 h 与 C08 的 20/32 h；不按成绩选分支 |

四轮原始结果、失败数值和当时的代码快照均保留在 `_01` 至 `_04` 目录。最终版本为 `source-time-ledger-v1.3`，以 `_04/code_snapshot` 的文件哈希区分确切实现。

| 原确认答案 | 自动无分支核心小时 | 完整条件分支小时 | 保留结果表的 Eff | 当前解释 |
|---|---:|---|---:|---|
{chr(10).join(confirmation)}

**联合结果、帕累托与重采样：已实际计算**

固定 Claude Sonnet 4.6、Qwen3-Max 和两道共同题 q23、q248，共四份生成答案。每题先算 IA 与 HV，再对题目取平均；帕累托比较平均 Com、Cor、Eff。只接受无分支候选点时，两模型的共同完整题集仍为空；沿用 C08 原分支点后为 q248；显式设置 C05 与 C08 的分支后，两题均可计算。因此本节是条件分析。

自动账本复现了上一阶段全部 **8 个主时间场景**，所有均值逐值相同；没有将另外的作者解释敏感性场景冒称为自动结果。在主阈值 0.7 下，两模型在八种情况均互不支配。C08=32 h 时，C05=14 h 的 Claude−Qwen 平均 HV 差为 **+0.0010626**；C05=17 h 时变为 **−0.0037430**。C08=20 h 时，四种 C05 分支的差均为正。时间分支足以改变 HV 排序，不能只展示一组最有利数值。

两题按模型同步成对重采样的有序抽样只有 (23,23)、(23,248)、(248,23)、(248,248)，共 **2²=4** 个，每个权重 1/4。本轮直接枚举四种，所以八场景共 32 条派生抽样记录；这不是新增 32 个观测，也不需要用 2,000 次 Monte Carlo 近似这四种情况。八个场景下的精确非支配入选频率均为 **Claude 3/4、Qwen 4/4**：这是对这两道已观察题重新赋权的描述，不是“模型总体最优的概率”。任务包的 2,000 次设置仍适用于有足够来源块的一般家族重采样。本例两题共享 FDISCO 参考来源，保守连通分块只有一个，无法估计来源块之间的不确定性；重复 2,000 次不会创造新的来源块。

[八场景结果](joint_01/results.json) · [逐模型均值](joint_01/model_means.csv) · [精确成对抽样](joint_01/exact_draws.json) · [来源依赖](joint_01/source_dependency_audit.json)

**继续完成阈值实验后，发现主结论仍不稳定**

按任务包事先规定的 0.6/0.7/0.8 复用已保存的行/列最大余弦相似度和原受控矩阵。三个设置均采用同一完整参考候选集合，在任务/方法筛选后按最大 SR、最大同参考 SP、固定版本顺序选择。没有新编码、没有新模型请求；主结果的 SR/SP 和阈值 **0.7 原样保留**，敏感性结果单列。

| 原确认答案 | 阈值 0.6：SR / SP | 主阈值 0.7：SR / SP | 阈值 0.8：SR / SP |
|---|---|---|---|
{chr(10).join(step_table)}

最有诊断价值的是 C03：原答案截断到 `Incubation with`，降低阈值后 SR 从 0 变成 **1/3**、SP 从 0 变成 **1**。这表明通用操作开头也能超过较低余弦阈值，SP 不是实验正确率。C04、C07 的中文全文在 0.6 下仍然零命中，先前保存的最大相似度分别仅 0.5071、0.4883，且没有长文本截断。低 SR 不能直接解释为没有对应操作；仅降低阈值同时可能增加不完整短句的命中。

| 阈值 | 相同两题、8 个时间场景的三维帕累托结果 | Claude−Qwen 平均 HV 差的范围 |
|---|---|---:|
| 0.6 | 八场景均为 Qwen 支配 Claude | −0.080442 至 −0.060690 |
| 0.7（主） | 八场景均互不支配 | −0.003743 至 +0.012533 |
| 0.8 | 八场景均互不支配 | −0.059029 至 −0.045792 |

阈值 0.8 时 C01/C02/C08 的所选 iDISCO+ 参考版本改变，按原预设规则发生，未手动挑选。确认队列的分项覆盖在三个阈值均相同，不能用覆盖变化解释上述排序差。共完成 8 答案×3 设置、24 受控返回×3 设置、18 原配对×3 设置；派生行数分别为 24、72、54，不能计作新增实际评价。24 个联合场景均使用相同两题。

受控删除问题也未消失：q2 的旧 Cor 仍增加 1/24；在 0.8 下 ΔSR=0，进而导致 ΔHV=**+0.018087**。q21/q22 删除在 0.7 下 SR 不响应，在 0.6 下分别下降 1/7、2/7。编号变化在全部阈值、两次实际返回均保持各指标不变。结果支持“编号处理已稳定”，不支持“所有删除和语义判项已正确”。

下一步方向是独立验证跨语言和步骤粒度，而非按模型排名调阈值。[Making Monolingual Sentence Embeddings Multilingual using Knowledge Distillation（EMNLP 2020）](https://aclanthology.org/2020.emnlp-main.365/) 提供了跨语言句向量对齐的已发表方案；可作为候选编码器/语义等价检查方向，但尚未在本数据运行，不能称已解决。可行验证应同时包含中文—英文等义步骤、截断通用句、必要步骤删除及步骤拆合，开发后固定，再评估未暴露材料。旧 all-mpnet-base-v2 和原 SR/SP 继续作为基线。

[确认阈值表](threshold_01/confirmation.csv) · [所有候选参考得分](threshold_01/candidates.json) · [受控配对](threshold_01/controlled_pairs.csv) · [24 个条件联合场景](threshold_01/joint.json)

![共同题集三维帕累托的二维投影](figures/cce_threshold_projections.png)

各列投影使用同一个三维非支配集合，图中连线表示明确时间分支范围，不是置信区间。[SVG](figures/cce_threshold_projections.svg) · [PDF](figures/cce_threshold_projections.pdf)

![HV 对阈值与时间分支的敏感性](figures/hv_threshold_branches.png)

[SVG](figures/hv_threshold_branches.svg) · [PDF](figures/hv_threshold_branches.pdf) · [逐图数据](figures/figure_data.csv) · [英文 Methods/Results 与图注](paper_text_en.md)

**各实验还剩什么**

| 实验 | 已形成的真实结果 | 仍待完成的部分 |
|---|---|---|
| E1：专家与步骤适配 | 原 SR/SP、候选完整版本和命中取值保存；新增三阈值复核 | 一位专家 5 开发＋15 留出仍无回传；跨语言匹配和粗细粒度问题尚未通过独立核查 |
| E2：受控验证/合理替代路线 | 原 24 返回、18 配对保持完整；新增 54 条阈值配对派生结果 | q2 Cor 上升、q22 主阈值 Com 不响应仍在；6 个第二路线候选尚无已确认合格并完成的 6–8 对 |
| E3：局部提取 | 标签与时间都可保存原文→关系/范围→数值链，三份确认时间缺分已自动恢复 | 仍依赖保存的模型操作分解；C03 截断、C02 混合步骤时长、原标签示例歧义等未解决；专家核查没有被助手代替 |
| E4：评价稳定性 | 24 原受控分值不变；既有有限重复组零极差结果可复用 | 本轮没有新模型重复、没有新跨评价器试验；不能把确定性后处理称为随机稳定性大幅提高 |
| E5：CCE/帕累托/重采样 | 8 自动时间场景、24 时间×阈值场景、精确 4 种成对抽样完成 | 排名对时间与阈值敏感；共同题只有两道、来源连通块只有一个，无法支持总体优劣与来源级置信区间 |
| E6：湿实验 | 已有样本量敏感性、随机化、模板和分析入口继续保留 | 测量仍为 0；按任务包保持计划状态，不能给出湿实验效果结论 |

Correctness 本轮仍沿用真实旧 LLM 返回。用户要求的“LLM 做结构、逻辑与常识安全审查，数值有效性由 EGES 计算”已落实到[五组配对请求包](../qualitative_execution_03/README_zh.md)，但实际执行仍为 **0/10 请求、0/5 配对**。当前不能把旧 Cor 的定量惩罚理由写成新版定性规则已验证。该包需要尚未回传的新增最多 10 次/2 小时授权；已有明确总调用上限已用完，旧授权窗口已结束。人工预算不变，不使用 Llama 评价器。

**九个可直接复查的全流程示例**

{' · '.join(examples)}

每个示例包含原题、完整真实答案、评分正文、逐操作取值、标签来源及最终 CCE。C01 看父步骤时间只算一次与重复解释；C04 看染色清洗范围；C05/C08 看分支；FPC13 看累计总量；C03 看真实缺项与低阈值误匹配。整体目标仍未完成，本阶段完成的是自动时间候选及可复算的敏感性证据。
'''
(OUT/'REPORT_zh.md').write_text(report,encoding='utf-8')
md=MarkdownIt('commonmark',{'html':False}).enable('table')
html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ClearEval 自动时间与联合结果</title><style>body{font-family:"Microsoft YaHei",sans-serif;max-width:1180px;margin:32px auto;padding:0 24px;line-height:1.75;color:#202733}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #cbd5e1;padding:8px;vertical-align:top}th{background:#edf2f7}a{color:#125f96}img{max-width:100%}pre{white-space:pre-wrap}code{overflow-wrap:anywhere}</style><body>'+md.render(report)+'</body></html>'
(OUT/'REPORT_zh.html').write_text(html,encoding='utf-8')
paper='''# Supplementary Methods and Results: development replay

We separated source-backed duration normalization, operation scope, and execution alternatives. The candidate used saved model operation decompositions and source headings, retaining verbatim source offsets, finite duration bounds, repetition counts, cumulative-duration relationships, and conditional branches. Explicit finite ranges were represented by their midpoint within each branch. Alternative branches were enumerated separately. Missing durations were not imputed as zero, and all original scoring formulas were preserved. We evaluated 26 synthetic boundary cases and replayed two overlapping sets of 32 and 67 archived returns. These sets contain repeated evaluations and controlled variants and are not independent natural-answer samples.

In the 32-return set, available time scores increased from 26 to 29. Twenty-eight returns supported a single unbranched candidate result; the remaining numerically complete return inherited a previously selected optional branch. Among the eight previously designated confirmation answers, four now supported unbranched complete CCE, and a fifth retained its prior branch-specific point. The newly recovered core durations were 34.5, 72, and 8.5 h. All metrics in the 24-return controlled subset were unchanged. In the 67-return historical set, available time scores increased from 61 to 63 and complete numeric CCE from 48 to 49; 47 complete cases had unbranched candidate time results. Three intentional duration-deletion controls remained unresolved. These are post-exposure development results, not independent extraction accuracy or new evaluator-repeatability measurements.

Conditional joint analysis used four archived generator answers on the same two tasks. Eight source-time scenarios were reproduced automatically and matched the prior source-assisted calculations. IA and HV were computed per answer and then averaged. Pareto dominance was evaluated in three-dimensional model-mean CCE space. At the primary step-matching threshold of 0.7, both generators were nondominated in all eight scenarios, but the mean-HV difference (Claude minus Qwen) ranged from -0.003743 to +0.012533. The unbranched-only common set was empty, so all two-task comparisons require the explicit timing assumptions.

Using stored maximum cosine similarities, we additionally evaluated the prespecified thresholds 0.6 and 0.8 without changing primary SR/SP. Coverage was identical across thresholds. At 0.6, Qwen dominated Claude in all eight timing scenarios; both were nondominated at 0.7 and 0.8. A truncated response ending in “Incubation with” changed from SR=SP=0 at 0.7 to SR=1/3 and SP=1 at 0.6, while two Chinese responses remained unmatched. Thus, lowering the threshold did not resolve the observed semantic-matching problem. Correctness scores remained inherited from the original model judgments and do not validate the proposed qualitative-only revision.

For descriptive paired-task reweighting, all four ordered draws from two questions were enumerated, with weight 1/4 each. Nondominance frequencies were 3/4 for Claude and 4/4 for Qwen in each timing scenario; these describe reweighting of the observed tasks, not probabilities of population optimality. The two tasks share a selected FDISCO source and form one conservative connected source block. Consequently, source-block population uncertainty was not estimable, and no confidence interval or population-level model ranking is claimed. Increasing Monte Carlo repetitions would not create independent source information.

Figure 1. Three two-dimensional projections of the same three-dimensional Pareto set on the same two tasks. Rows show matching thresholds 0.6, 0.7 (primary), and 0.8. Circle/cross markers denote nondominated/dominated membership from the three-dimensional comparison. Lines span explicitly enumerated timing scenarios and are not confidence intervals.

Figure 2. Difference in mean per-answer HV across the three matching thresholds and eight timing scenarios. Colors indicate the two C08 timing branches and marker shapes the four C05 branches. Horizontal offsets are visual only. The 24 plotted settings derive from four archived answers and are not independent observations.
'''
(OUT/'paper_text_en.md').write_text(paper,encoding='utf-8')
commands=['# 实际执行与复核命令','','以下均已实际执行；固定输出目录的命令不会覆盖成功结果。早期回放须使用对应 code_snapshot，当前脚本不代表早期规则。','','```powershell']
for index in [1,2,3,4]:
    for co in ['canonical32','archived67']:
        cmd=b.read(OUT/f'{co}_{index:02d}/manifest.json')['command'];commands.append('& '+"'"+cmd[0]+"' -X utf8 "+' '.join("'"+s.replace("'","''")+"'" for s in cmd[1:]))
for script in ['validate.py','joint_readout.py','threshold_readout.py','plot_results.py','build_delivery.py','verify_delivery.py']:
    commands.append("& '"+sys.executable+"' -X utf8 '"+str(OUT/script)+"'")
commands.extend(['```','','下次继续前先执行 verify_delivery.py；输入与配置未变时复用现有结果。新模型请求须以 qualitative_execution_03 的实际授权和固定矩阵为准，本页不声称该批已执行。'])
(OUT/'commands.md').write_text('\n'.join(commands)+'\n',encoding='utf-8')
(OUT/'resolved_config.yaml').write_text('''stage: automatic_time_and_joint_sensitivity_20261012
execution_revision: r2
candidate: source-time-ledger-v1.3
final_replay_suffix: '04'
original_formulas_preserved: true
primary_SR_SP_unchanged: true
primary_encoder: all-mpnet-base-v2
primary_threshold: 0.7
sensitivity_thresholds: [0.6, 0.7, 0.8]
reference_selection: task_route_filter_then_max_SR_same_reference_SP_fixed_order
time_scope: reported_serial_core_incubations
finite_duration_range: midpoint_within_branch
disjunction_and_optional_steps: separate_explicit_branches
overnight_without_numeric_definition_hours: 8
numeric_definition_precedes_default: true
cumulative_total: replace_initial_contribution_do_not_add
recurrence_interval: not_extra_duration
missing_value: null
new_model_calls: 0
new_expert_annotations: 0
actual_human_budget: {experts: 1, development: 5, holdout: 15}
time_branch_scenarios_joint: 8
exact_paired_task_draws_per_scenario: 4
source_connected_blocks: 1
population_CI_claimed: false
formal_independent_confirmation: false
old_Cor_reused_pending_qualitative_revision: true
''',encoding='utf-8')
b.save(OUT/'research_cycles.json',{'references':[
    {'title':'HeidelTime: High Quality Rule-Based Extraction and Normalization of Temporal Expressions','year':2010,'url':'https://aclanthology.org/S10-1071/','supports':'separate recognition and normalization; no laboratory truth claim'},
    {'title':'Beyond Accuracy: Behavioral Testing of NLP Models with CheckList','year':2020,'url':'https://aclanthology.org/2020.acl-main.442/','supports':'behavioral invariance and failure tests'},
    {'title':'Making Monolingual Sentence Embeddings Multilingual using Knowledge Distillation','year':2020,'url':'https://aclanthology.org/2020.emnlp-main.365/','supports':'future multilingual alignment direction, not an executed fix'}],
    'iterations':[{'iteration':i,'canonical32':b.read(OUT/f'canonical32_{i:02d}/summary.json'),'archived67':b.read(OUT/f'archived67_{i:02d}/summary.json')} for i in [1,2,3,4]],
    'next_test':'language-equivalent steps + incomplete generic clauses + deletion + segmentation; frozen development then unexposed audit',
    'rejected_directions':['choose highest scoring time branch','average incompatible alternatives','lower threshold based on model rank','call repeated source-block draws independent evidence'],
    'new_knowledge_base_numbers':False})
b.save(OUT/'completion_audit.json',{'goal_complete':False,'previous_goal_turn_classification':'progress','this_goal_turn_classification':'progress',
    'new_model_calls':0,'actual_new_qualitative_pairs':0,'expert_records_added':0,'wetlab_rows_added':0,
    'new_results':{'time':{co:b.read(OUT/(co+'_04')/'summary.json') for co in ['canonical32','archived67']},'joint':joint,'threshold':threshold},
    'remaining':['qualitative Correctness paired run','cross-language and step granularity validation','controlled deletion anomalies',
        'independent automatic extraction audit','cross-family evaluator repeats','expert 5+15','eligible complete alternative routes',
        'independent source blocks for population uncertainty','wetlab measurements only if claiming wetlab effects']})
marker='2026-10-12 自动时间与阈值联合续记'
paragraph=marker+'：完成来源时间候选和双队列回放。后续32返回时间26→29、完整数值26→29；其中自动无分支完整28/32，原确认4/8，另C08保留原分支点，不能笼统称5/8无条件完整。历史67返回时间61→63、完整48→49，其中无分支完整47。666项检查、2071处来源引用通过，24受控全部指标不变。自动复现8个条件联合场景；继续用0.6/0.7/0.8做24场景敏感性，0.6时Qwen支配Claude、0.7/0.8互不支配，截断C03在0.6获得SR=1/3、SP=1，故不按结果调整主阈值。新增调用0，仍438/438；新版定性Cor实际0/10请求，专家和湿数据仍0。整体目标未完成。'
nav=[]
for name,path,target in [
    ('workspace_status',ROOT.parent/'STATUS.md','reports/cleareval_20261012/automatic_time_scope/REPORT_zh.md'),
    ('validation_status',ROOT/'artifacts/cce_validation/STATUS.md','../../../reports/cleareval_20261012/automatic_time_scope/REPORT_zh.md'),
    ('round_status',ROOT/'artifacts/cce_validation/optimizer_round3_20261011/STATUS.md','../../../../reports/cleareval_20261012/automatic_time_scope/REPORT_zh.md')]:
    previous=path.read_text('utf-8')
    if marker not in previous:
        snapshot=OUT/'status_before_update'/path.relative_to(ROOT.parent);snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(path.read_bytes())
        first,sep,tail=previous.partition('\n');path.write_text(first+'\n\n'+paragraph+f' [结果与九例全流程]({target})。\n'+tail,encoding='utf-8')
    nav.append({'name':name,'path':str(path),'marker':marker})
readme=BASE/'README.md';previous=readme.read_text('utf-8')
if marker not in previous:
    snapshot=OUT/'status_before_update/reports/cleareval_20261012/README.md';snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(readme.read_bytes())
    first,sep,tail=previous.partition('\n');readme.write_text(first+'\n\n'+marker+'：[自动时间、条件联合与阈值报告](automatic_time_scope/REPORT_zh.md)；[HTML](automatic_time_scope/REPORT_zh.html)。无分支完整与继承分支点已区分，原SR/SP保留。\n'+tail,encoding='utf-8')
b.save(OUT/'navigation_updates.json',nav)
inputs=[b.bind(ROOT/'scripts/cce_source_time_ledger_v1.py'),*example_inputs]
for rel in ['canonical32_04/manifest.json','archived67_04/manifest.json','joint_01/manifest.json','threshold_01/manifest.json','figures/manifest.json']:
    v=b.read(OUT/rel);inputs.extend(v.get('inputs',v.get('bindings',[])))
inputs.extend([external['budget']['ledger'],*external['human_inputs'],external['wetlab_source'],
    b.bind(BASE/'automatic_label_relations/external_state.json'),b.bind(BASE/'qualitative_execution_03/analysis/summary.json')])
unique={r['path']:r for r in inputs}
for p,v in unique.items():assert b.bind(p)==v
b.save(OUT/'scientific_inputs.json',{'files':list(unique.values()),'verified':len(unique)})
b.save(OUT/'figure_visual_review.json',{'inspected_pngs':['figures/cce_threshold_projections.png','figures/hv_threshold_branches.png'],
    'visible_checks':['labels and legends readable','no observed cropped content','same 3D front membership in every projection','HV zero and threshold labels visible'],
    'reviewer':'current assistant; visual layout only, not independent scientific review'})
files=[b.bind(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['delivery_manifest.json','delivery_verification.json'] and '__pycache__' not in p.parts]
b.save(OUT/'delivery_manifest.json',{'files':files,'file_count':len(files),'created_utc':datetime.now(timezone.utc).isoformat(),'new_model_calls':0})
print(json.dumps({'files':len(files),'examples':len(example_ids),'scientific_input_files':len(unique),'checks':validation['checks_passed'],'goal_complete':False},ensure_ascii=False))
