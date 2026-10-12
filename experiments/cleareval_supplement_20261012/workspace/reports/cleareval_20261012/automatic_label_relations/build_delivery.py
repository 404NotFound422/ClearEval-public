"""Write the observed source-relation results and preserve the negative iterations."""
import csv,hashlib,json,re,sys
from pathlib import Path
from datetime import datetime,timezone
from markdown_it import MarkdownIt
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent;BASE=OUT.parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
runner,registry=b.runtime()
can=b.read(OUT/'canonical32_03/results.json');old=b.read(OUT/'archived67_03/results.json')
summaries={co:b.read(OUT/(co+'_03')/'summary.json') for co in ['canonical32','archived67']}
validation=b.read(OUT/'validation.json')
assert validation['checks_passed']==222
byid={r['cell_id']:r for r in can+old}
external=b.read(BASE/'semantic_source_revision/external_state.json')
for ref in [external['budget']['ledger'],*external['human_inputs'],external['wetlab_source']]:assert b.bind(ref['path'])==ref
b.save(OUT/'external_state.json',{**external,'checked_utc':datetime.now(timezone.utc).isoformat(),
    'new_model_calls':0,'authorization_for_new_pairs':'requested_but_not_received'})

def fmt(x):
    if x is None:return 'NA'
    if abs(x)>0 and abs(x)<.000001:return f'{x:.4g}'
    return f'{x:.6f}'.rstrip('0').rstrip('.')

examples=['R3C03__r0','R3C04__r0','R3C05__r0','A03','FPC08','FPC09','FPC16']
for cid in examples:
    r=byid[cid];d=b.read(r['source_document']['path']);dest=OUT/'examples'/cid;dest.mkdir(parents=True,exist_ok=True)
    original_path=Path(r['source_document']['path']).parent.parent/'original_source_documents'/Path(r['source_document']['path']).name
    original=b.read(original_path) if original_path.exists() else d
    (dest/'submitted_answer.txt').write_bytes(original['text'].encode('utf-8'))
    (dest/'scoring_source.txt').write_bytes(d['text'].encode('utf-8'))
    (dest/'question.txt').write_bytes(registry.questions[str(r['question_id'])]['question'].encode('utf-8'))
    b.save(dest/'evidence.json',{**r,'original_source':b.bind(original_path) if original_path.exists() else r['source_document']})
    metrics='\n'.join('| '+k+' | '+fmt(v)+' |' for k,v in r['metrics'].items())
    relations='\n'.join('| '+x['fluorophore']+' | '+(x['marker'] or '不需要外部 marker')+' | '+x['basis']+' |' for x in r['proposal']['relations'])
    text=f'''# {cid}：从原文到分数

[题目](question.txt) → [原提交全文](submitted_answer.txt) → [实际提取来源](scoring_source.txt) → [逐条关系、原文位置和查表记录](evidence.json)。

本例的处理决定为 `{r['decision']}`。原 LLM 返回保存在 [post_record]({r['post_record']['path'].replace(chr(92),'/')})；它的直接分数和原 SR/SP 均沿用。候选只从全文所选列表提取标签关系，调用原 EGES 分通道函数，再用原公式聚合；未重新请求模型。

| 染料或信号 | 靶标/角色 | 来源解释 |
|---|---|---|
{relations}

| 分项 | 实际候选值 |
|---|---:|
{metrics}

缺项、候选不适用原因和每个来源区间均见 evidence.json。NA 没有改成 0；FPC08 的 0 来自原靶标匹配函数的实际输出。完整数值结果与科学有效性分别判断，旧 LLM Correctness 也不代表本轮认可其理由。
'''
    (dest/'README_zh.md').write_text(text,encoding='utf-8')

confirm='\n'.join('| '+r['cell_id'].replace('__r0','')+' | '+fmt(r['baseline_metrics']['s_label'])+' → '+fmt(r['metrics']['s_label'])+' | '+fmt(r['metrics']['s_time'])+' | '+fmt(r['metrics']['Cor'])+' | '+('完整' if r['complete_numeric_CCE'] else '缺项')+' |' for r in can if r['cell_id'].startswith('R3C'))
report=f'''# ClearEval：自动标签关系修复与定性 Correctness 待执行对照

2026-10-12。新增模型调用 0；全包仍为 438/438。

这轮把上一轮由助手逐答案读出的部分标签关系落实成了通用来源规则。32 份后续返回的标签可计算数由 **28/32 增至 32/32**；24 份受控返回的全部指标仍与上一轮相同。另一批 67 份历史返回的标签可计算数由 **55/67 增至 60/67**，完整 CCE 由 **44/67 增至 48/67**，没有丢失原完整结果。

这些分母包含重复和变体：32 返回对应 20 个提交全文、14 个规范化全文，67 返回对应 40 个全文；两批来源有重叠，不能相加成 99 个独立答案。所有输入均已暴露，结果属于开发复算。新规则本身不接收答案 ID、旧分值或逐答案人工标签；历史批次的输入仍包含此前两份时间来源注释，故不能将历史 48/67 整体称作完全自动、无人工辅助的准确率。

| 队列 | 标签可计算 | 完整数值 CCE | 本轮实际自动应用关系规则 |
|---|---:|---:|---:|
| 后续 24 受控＋8 原确认返回 | 28→32 / 32 | 26→26 / 32 | 31/32；R3C02 沿用旧结果且保留歧义 |
| 历史存档返回 | 55→60 / 67 | 44→48 / 67 | 47/67；其余保留原处理值及未覆盖原因 |

两批的比较起点都是不含逐答案新标签注释的既有处理分支。本轮历史 48/67 与上一轮加入人工来源注释后的 48/67 数字相同，来源路径不同，不能写成“总完成率再次提升到更高值”。[后续逐答案表](canonical32_03/per_answer.csv)、[历史逐答案表](archived67_03/per_answer.csv)、[实际命令](commands.md)均可直接核对。

**实验目标、安排与判定**

E3 的问题是：原文已经清楚声明靶标与染料，但模型抽取中的大小写、角色或括号写法是否让计算遗漏了关系？本轮固定原直接判断、时间分、SR/SP 和 EGES 公式，只比较标签关系的提取与投影。成功条件是来源关系能被保留、原有正确计算不受损，且没有为了补分创造染料或抗体链；不是强求得分提高。

规则读取明确的所选标签列表，将靶标、染料、原生荧光和描述性括号分别保存。`MAP2 + AF488` 支持染料—靶标关系，但本身不指定一抗直接偶联还是由二抗承载；评分不再把完整抗体链当作每条关系的必要输入。`GFP（内源）` 可直接作为信号；若答案另写 `GFP（内源）+AF488` 且正文进行抗 GFP 放大，则保留 AF488→GFP 关系，把“内源”作为描述。两个靶标共用 AF647 时保留两条记录，不覆盖字典键。

`Alexa Fluor (647)` 可按明确数字解析为 AF647。对仅写通用 Alexa Fluor 的列表，只有一个待定通道且实际操作唯一明确某种 AF 染料时，才用正文具体化；仅有 e.g. 示例不作唯一选择，多种实际染料不挑最高分。`β-III Tubulin (TUJ1)` 按原目录完整名称保留，不创造另一个 TUJ1 靶标或推断抗体克隆。

**排查循环与真实负结果**

形式化地看，来源文本 S 经关系提取 E 得到 R，再由既有函数 F 计算标签分 L=F(R)。本轮仅改变 E，固定 F 与其他指标输入。所需检查包括：同义括号写法应保持关系；显式否定/候选不应变成已选；共染料的不同靶标应仍是不同记录；从示例到唯一选择需要额外来源证据。

这一安排借鉴 [CheckList（ACL 2020）](https://aclanthology.org/2020.acl-main.442/) 的行为能力与不变性测试；[WNUT-2020 湿实验实体与关系提取任务](https://aclanthology.org/2020.wnut-1.33/) 将实体识别和关系提取分别评估，也支持将“找到词”与“找对关系”分开检查。两篇文献提供评价设计依据，不证明本项目标签规则的科学准确性，更不替代专家。

| 迭代 | 观察到的实际问题 | 据此修改与验证 |
|---|---|---|
| 第一次自动重放 | 32 批达到 32 个标签值；历史批的 A03 及其重复却丢失 4 个完整 CCE。原因是把 `GFP（内源）` 整段当作靶标查表 | 保存失败结果；将明确的原生荧光描述与靶标名分开，未用旧高分兜底 |
| 第二次重放 | 历史批恢复且新增 4 个完整 CCE；但过粗的“括号内外目录名不同”规则又拒绝 TUJ1 写法，使后续标签覆盖回到 30/32 | 原知识目录已明确列出的整体名称优先保留；未为 TUJ1 另造克隆事实 |
| 第三次重放 | 后续 32/32、历史 60/67 标签可计算；后者完整 48/67，没有原完整值丢失 | 固定最终代码，运行 19 个语义边界例和真实来源/不受影响分项核查，共 222 项通过 |

六次批量执行均为实际离线执行，前三个版本的结果与代码快照保留在 `canonical32_01/02/03` 和 `archived67_01/02/03`。一次核查脚本最初误读历史 `metrics` 而非 `source_assisted_metrics`，定位并改正字段后才进行来源辅助对照，没有改动任何评分产物。最终 4 份、9 条来源辅助关系对应的标签分与本轮自动规则一致；这是同一开发材料的符合性检查，不能写成独立专家 100% 准确率。

**八份原确认答案现在的实际状态**

| 答案 | 标签分（旧→新） | 时间分 | 旧 Cor | 自动完整 CCE |
|---|---:|---:|---:|---|
{confirm}

R3C02 没有在列表中指定 c-Fos/NeuN 各自的具体染料；其旧标签值 3 保留，正文 e.g. 的歧义仍在。因此“32/32 标签有值”不等于 32 份都完成了无歧义的新自动解析。R3C03 的正文确实截断，但所选标签列表完整：旧空投影产生的 0 改为原函数从实际三个通道算出的 3；Cor 与时间仍缺项。没有因为方案截断而把可判的标签分一起清零，也没有补造操作。

**七个可查看完整流程的例子**

| 示例 | 原文→提取→查表→分数 | 问题出现阶段 |
|---|---|---|
| [R3C03](examples/R3C03__r0/README_zh.md) | 所选 NeuN–AF647、βIII–AF488、DAPI → 三条关系 → 标签 3；其余缺项继续保留 | 截断答案的已知标签被空投影掩盖 |
| [R3C04](examples/R3C04__r0/README_zh.md) | 中文“所选”中 NeuN 和 βIII 各对应 AF647，另有 TO-PRO-3 → 标签 3 | 旧 usage=mentioned 与单染料字典不足以表达两个靶标 |
| [R3C05](examples/R3C05__r0/README_zh.md) | EGFP 独立信号＋通用 MAP2–AF；正文实际二抗指定 AF647 → 标签 5.1 | 通用标签与实际操作的同一通道未对齐 |
| [A03](examples/A03/README_zh.md) | GFP（内源）+AF488 → 靶标 GFP 与角色说明分开；MAP2–AF594 继续使用已登记来源支持 → 标签保持 4.2 | 描述性括号混入查表键；本輪回归已修正 |
| [FPC08](examples/FPC08/README_zh.md) | AF488→GFP、AF568→Phalloidin → 原靶标匹配通道给 Phalloidin 0 → s_label=0，Eff≈0.45139 | 这是原目标目录/公式的实际 0，不是缺值清零；是否应接受该替代标记另需科学审查 |
| [FPC09](examples/FPC09/README_zh.md) | `c-Fos (Npas4)` 混合两个分别登记的目录目标 → 候选不判其为别名，保留旧 NA | 原文身份含混，不能靠括号格式创造同义关系 |
| [FPC16](examples/FPC16/README_zh.md) | tdTomato、DiI 均无需外部 marker → 方法兼容通道分别 1.8、1.2 → 标签取 1.2 | 信号可直接存在不意味着与所选方法高度兼容 |

每例均含完整题目、提交全文、实际评分文本、来源位置、查表轨迹、逐分项和聚合结果。原 SR/SP 与旧 LLM 分数逐值保留；本轮不把旧 Cor 当作新定性判据已验证。

**Correctness 的实际成对实验已接好，但尚未调用**

[五组执行包](../qualitative_execution_03/README_zh.md)包含 A01–A05 的 C0/C1 全文请求、随机顺序、冻结配置、来源映射与分析入口。基线和候选将各实际调用一次，共 10 次；仅一条件一次，不能估计新评价器随机稳定性。C1 同时修订 Cor 职责和标签说明，属于成套 prompt 修改，不能作纯 co_param 因果实验。

准备过程真实遇到两个工程问题：原评分器从当前目录打开知识表；本地服务版本由历史 0.40.1 变为 0.40.3。前者已让入口使用仓库工作目录解决，后者已按现场元数据重新冻结两条件，模型身份与生成设置相同。元数据预检和未授权不产生请求的检查已通过，实际请求仍为 0/10，配对仍为 0/5。没有将“请求准备成功”算成“评分成功”。

已向用户提交新增最多 10 次、2 小时、全包 438→448 的额度请求。原因是现有明确调用上限已用完且旧授权窗口已结束；并非技能文件新增的审批要求。人工仍为一位专家 5＋15，不新增专家预算。

**对论文各实验的意义和剩余问题**

| 实验 | 本轮实际意义 | 尚未完成或仍有问题 |
|---|---|---|
| E1 人评与步骤适配 | 本轮继续保留原 SR/SP；来源和自动处理可供同一专家核查 | 专家回传仍为 0；原始步骤合并会改变 SR/SP |
| E2 受控与合理替代路线 | 24 份规范化受控分值全部不变，沿用已完成 18 个配对；标签修复未破坏这些结果 | q2 删除导致旧 Cor 上升，q22 Com 不响应，步骤合并敏感性仍在；6 个完整路线候选不能冒充已确认合格并完成的路线对 |
| E3 局部提取 | 标签覆盖增加，原文与评分链可审查；失败迭代与边界例保留 | 规则仅覆盖明确所选列表及有限正文对齐；时间自动解释、身份冲突、未暴露材料和专家核查仍不足 |
| E4 稳定性 | 新规则对相同来源是确定性处理；受控原重复结果未改变 | 没有新增真实重复或跨家族评测，不能称随机稳定性大幅提升 |
| E5 联合结果/帕累托/重采样 | 本轮没有改变先前已完整的后续点，故复用原受控和条件联合分析 | 自动共同完整题集仍不足；先前依靠来源时间注释的 32 场景仍是条件结果；两题共享 FDISCO 来源形成一个依赖块，不能用重复抽样造出独立来源 |
| E6 湿实验 | 复用已有计划、样本量敏感性、随机化与数据入口 | 真实测量仍为 0；任务包允许无数据时保留计划，不提供湿实验有效性结论 |

上一轮[来源辅助时间与联合分析](../semantic_source_revision/REPORT_zh.md)的 5/8 单值完整 CCE、2 份条件结果与帕累托结果继续保留；本轮自动入口的原确认完整 CCE 仍是 2/8，两者不能混写。当前结果支持“减少可定位的关系提取导致的缺分”，尚不支持“全部评估器优化目标已完成”。
'''
(OUT/'REPORT_zh.md').write_text(report,encoding='utf-8')
md=MarkdownIt('commonmark',{'html':False}).enable('table')
html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ClearEval 自动标签关系修复</title><style>body{font-family:"Microsoft YaHei",sans-serif;max-width:1180px;margin:32px auto;padding:0 24px;line-height:1.75;color:#202733}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #cbd5e1;padding:8px;vertical-align:top}th{background:#edf2f7}a{color:#125f96}pre{white-space:pre-wrap}code{overflow-wrap:anywhere}</style><body>'+md.render(report)+'</body></html>'
(OUT/'REPORT_zh.html').write_text(html,encoding='utf-8')

commands=['# 实际离线命令','', '以下六次批量执行均已实际产生结果。恢复时复用未变输入的成功产物；重跑时使用新输出目录，不能覆盖旧版本。','', '```powershell']
for i in [1,2,3]:
    for co in ['canonical32','archived67']:
        cmd=b.read(OUT/f'{co}_{i:02d}'/'manifest.json')['command']
        commands.append('& '+' '.join("'"+s.replace("'","''")+"'" for s in cmd))
commands.extend(["& '"+sys.executable+"' -X utf8 '"+str(OUT/'validate.py')+"'", "& '"+sys.executable+"' -X utf8 '"+str(Path(__file__))+"'",'```','',
    '前两次执行应使用相应目录 code_snapshot 下的入口和规则文件重建环境，不能用当前规则宣称复现旧版结果。最终入口和规则以 _03 的快照及哈希为准。',
    '', '定性 Cor 执行包的 prepare、元数据 preflight、analyze 及未授权检查已执行；实际生成请求尚未执行。见 [准备说明](../qualitative_execution_03/README_zh.md)。'])
(OUT/'commands.md').write_text('\n'.join(commands)+'\n',encoding='utf-8')
b.save(OUT/'research_cycles.json',{'references':[
    {'title':'Beyond Accuracy: Behavioral Testing of NLP Models with CheckList','url':'https://aclanthology.org/2020.acl-main.442/','supports':'behavior-focused invariance/negative tests, not biological truth'},
    {'title':'WNUT-2020 Task 1 Overview: Extracting Entities and Relations from Wet Lab Protocols','url':'https://aclanthology.org/2020.wnut-1.33/','supports':'separately assess entities and relations in procedural text'}],
    'iterations':[{'stage':i,'canonical32':b.read(OUT/f'canonical32_{i:02d}/summary.json'),'archived67':b.read(OUT/f'archived67_{i:02d}/summary.json')} for i in [1,2,3]],
    'rejected_directions':['Treat full native-signal description as target identity','Reject every parenthetical pair whose inner token has another catalog occurrence','Use the legacy metrics key as the prior source-assisted comparator'],
    'final_validation':b.bind(OUT/'validation.json'),'no_new_knowledge_base_numbers':True})
b.save(OUT/'completion_audit.json',{'goal_complete':False,'previous_goal_turn_classification':'progress','this_goal_turn_classification':'progress',
    'new_model_calls':0,'actual_new_qualitative_pairs':0,'expert_records_added':0,'wetlab_rows_added':0,
    'new_results':summaries,'remaining':['qualitative Correctness paired run','controlled deletion and step granularity anomalies',
    'independent automatic extraction check','cross-evaluator repeats','expert 5+15','eligible complete alternative routes',
    'independent source blocks for uncertainty','wetlab data only if claiming wetlab validation']})

marker='2026-10-12 自动标签关系续记'
paragraph=marker+'：已把明确所选列表与正文唯一 AF 通道的关系解释实现为通用来源规则。后续 32 返回标签覆盖 28→32，24 受控全部分值不变、原确认自动完整仍 2/8；历史 67 返回标签 55→60、完整 CCE 44→48，无原完整结果丢失。历史输入仍含此前时间来源注释，不能将全路径称作纯自动准确率。两个失败规则及修复均保留，222 项实现/来源检查通过。5 组定性 Cor 新请求已准备且现场配置核对成功，实际 0/10；已请求新增 10 次/2 小时，尚未回传。新增模型调用 0、仍 438/438，整体目标未完成。'
nav=[]
for name,path,target in [
    ('workspace_status',ROOT.parent/'STATUS.md','reports/cleareval_20261012/automatic_label_relations/REPORT_zh.md'),
    ('validation_status',ROOT/'artifacts/cce_validation/STATUS.md','../../../reports/cleareval_20261012/automatic_label_relations/REPORT_zh.md'),
    ('round_status',ROOT/'artifacts/cce_validation/optimizer_round3_20261011/STATUS.md','../../../../reports/cleareval_20261012/automatic_label_relations/REPORT_zh.md')]:
    text=path.read_text(encoding='utf-8')
    if marker not in text:
        snapshot=OUT/'status_before_update'/path.relative_to(ROOT.parent)
        snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(path.read_bytes())
        first,rest=text.split('\n',1);path.write_text(first+'\n\n'+paragraph+' [本轮报告]('+target+')。\n'+rest,encoding='utf-8')
    nav.append({'name':name,'updated':b.bind(path)})
index=BASE/'README.md';text=index.read_text(encoding='utf-8')
if marker not in text:
    (OUT/'status_before_update/report_index.md').write_bytes(index.read_bytes())
    first,rest=text.split('\n',1)
    index.write_text(first+'\n\n- **'+marker+'：** [完整报告](automatic_label_relations/REPORT_zh.md) · [浏览版](automatic_label_relations/REPORT_zh.html) · [命令](automatic_label_relations/commands.md)。后续标签 28→32/32；历史标签 55→60/67、完整 CCE 44→48/67。失败迭代、七个实例和待执行 Cor 对照均已记录。新增模型调用 0。\n'+rest,encoding='utf-8')
nav.append({'name':'report_index','updated':b.bind(index)})
b.save(OUT/'navigation_update.json',nav)

links=[]
for path in [OUT/'REPORT_zh.md',OUT/'commands.md',*sorted((OUT/'examples').glob('*/README_zh.md'))]:
    for href in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if href.startswith(('https://','http://')):continue
        target=(path.parent/href).resolve();assert target.exists(),(path,href)
        links.append({'from':str(path),'href':href,'exists':True})
scientific=[ROOT/f for f in ['OEQ_run_grading_new.py','KnowledgeBase/tissue.json','KnowledgeBase/method_fluro_compati.json',
    'KnowledgeBase/source_registry.json','dataset/Q+AR/src/demand_vectors_all.json','scripts/cce_selected_label_source_v1.py',
    'scripts/cce_typed_label_scorer_v2.py','scripts/cce_scoped_midpoint_scorer_v1.py','scripts/cce_grounded_offline_scoring_v1.py',
    'scripts/cce_target_catalog_role_fix_v2.py','scripts/cce_scales_source_key_alias_v1.py']]
b.save(OUT/'scientific_inputs.json',{'bindings':[b.bind(x) for x in scientific]})
b.save(OUT/'delivery_verification.json',{'implementation_and_source_checks':222,'local_links_verified':len(links),'links':links,
    'external_inputs_unchanged':True,'new_model_calls':0,'full_goal_complete':False})
files=[p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts]
b.save(OUT/'delivery_manifest.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'files':[b.bind(x) for x in files],
    'file_count':len(files),'new_model_calls':0,'main_report':'REPORT_zh.md'})
print(json.dumps({'saved_returns':[32,67],'new_complete_historical':4,'new_labels':[4,5],
    'checks':222,'links':len(links),'files':len(files),'new_model_calls':0},ensure_ascii=False))
