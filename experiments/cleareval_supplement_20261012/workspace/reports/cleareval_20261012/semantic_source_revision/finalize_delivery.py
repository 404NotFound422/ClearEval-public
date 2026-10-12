"""Validate current deliverables, render the report, and update navigation."""
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote
from markdown_it import MarkdownIt
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b

# Save the exact final implementations and annotation builders used for replay.
code=OUT/'code_snapshot';code.mkdir(exist_ok=True)
scripts=[ROOT/'scripts/cce_selected_method_source_v1.py',ROOT/'scripts/cce_semantic_ledger_replay_v1.py',
    OUT/'run_method_candidate.py',OUT/'build_source_annotations.py',OUT/'joint_readout.py',
    OUT/'audit_source_dependencies.py',OUT/'build_delivery.py',Path(__file__)]
for path in scripts:shutil.copyfile(path,code/path.name)
for filename in ['method_candidate_02/plan.json','semantic_04/plan.json','joint_with_optional_bleach/manifest.json']:
    plan=b.read(OUT/filename)
    for key in ['entrypoint','candidate','annotations','config','label_policy','label_scorer','scores','identity','original_analysis','optional_bleach_sensitivity']:
        if key in plan:
            binding=plan[key];assert b.bind(binding['path'])==binding,(filename,key)

executions=[('中文方法候选，32 返回',b.read(OUT/'method_candidate_02/execution.json')['command']),
    ('最终来源账本',b.read(OUT/'source_annotations_v3.execution.json')['command']),
    ('最终来源辅助复算，32 返回',b.read(OUT/'semantic_04/execution.json')['command']),
    ('准备可选步骤分支',[sys.executable,str(OUT/'build_delivery.py'),'--data-only']),
    ('条件联合分析及精确枚举',b.read(OUT/'joint_with_optional_bleach/manifest.json')['command']),
    ('参考来源依赖图',b.read(OUT/'joint/source_dependency_audit.json')['command']),
    ('示例、检查与图形',b.read(OUT/'delivery_verification.json')['command']),
    ('报告与当前状态',[sys.executable,str(Path(__file__))])]
lines=['# 实际命令与产物','',
    '以下均已执行，新增本地/API 评价请求为 0。Python 解释器使用本项目便携环境。',
    '当前最终数值入口为 semantic_04；semantic_03 的数值相同，已有联合分析精确复用，并保存等值检查。',
    '原始来源、模型返回和原 SR/SP 不被覆盖。重新计算不同规则请指定新输出目录。','']
for title,command in executions:
    quoted='& '+' '.join("'"+str(v).replace("'","''")+"'" for v in [command[0],'-X','utf8',*command[1:]])
    lines.extend([title+'：','','```powershell',quoted,'```',''])
lines.extend(['过程记录：',
    '- semantic_01 在部分转换记录缺 numeric 时停止，保留计划和当时代码；semantic_02 修复接线。',
    '- semantic_03 增加未分句父步骤依据：C01 主时间 34.375→34.5 h，CCE 不变。',
    '- semantic_04 澄清 TUJ1 不必然是确定克隆；只改来源解释，全部数值不变。',
    '- 交付检查曾预期 C08 两个时间分相同；实际得到 2.570991 与 3，拒绝不变性假设并补做完整联合分析。',
    '- 早期历史方法与语义候选的原计划、结果及已有快照保留；当前可重现命令指向上面的最终版本。',''])
(OUT/'commands.md').write_text('\n'.join(lines),encoding='utf-8')

cycles={'new_model_calls':0,'author_source_analysis':True,'cycles':[
    {'phenomenon':'Explicit Chinese selected method discarded','hypothesis':'Selection context was underrecognized',
     'test':'Same candidate across 32 archived returns plus positive/negative selection examples',
     'observed':'Only C04 method and transparency components recovered; all old finite values unchanged',
     'next':'Validate on unexposed wording in a future real evaluator batch'},
    {'phenomenon':'Resolvable target-fluor relations withheld','evidence':'Exact original answer spans and marker/fluor role definitions',
     'test':'Author source decomposition plus the existing label scorer',
     'observed':'Four additional label values; three additional complete single-value CCE records',
     'limit':'This is source-assisted analysis, not new automatic/expert accuracy'},
    {'phenomenon':'Canonical split moved a trailing Time field next to storage',
     'test':'Compare original parent step, mapping, and both time interpretations',
     'observed':'C01 time interpretation changes; all resulting CCE vectors in the declared scenarios are equal'},
    {'phenomenon':'TUJ1 parenthesis was overread as proof of clone identity',
     'primary_source':'https://www.ptglab.com/products/TUBB3-specific-Antibody-CL488-66375.htm',
     'counterexample':'Product uses TUBB3-specific/TUJ1 target label but reports clone 1F8G10',
     'observed':'Corrected metadata interpretation; no score changed'},
    {'phenomenon':'An optional bleach remained implicit in an already complete CCE record',
     'hypothesis':'Omitting the optional 12 h might leave the time score invariant',
     'test':'Evaluate 20 and 32 hours using the same original time function and KB',
     'observed':'2.5709906743058366 versus 3.0; invariance rejected',
     'next':'Cross both source branches with the other answer branches; completed in joint_with_optional_bleach'},
    {'phenomenon':'Scalar model ordering could depend on source branches',
     'test':'8 main and 32 total declared source/scope combinations, fixed paired tasks',
     'observed':'Mean-HV ordering changes; both models remain nondominated in all enumerated scenarios',
     'limit':'Two exposed tasks with shared source family, no population uncertainty inference'}]}
b.save(OUT/'research_cycles.json',cycles)

effort={'new_experts':0,'expert_budget_unchanged':{'experts':1,'development':5,'holdout':15},
    'new_expert_returns':0,'detailed_assistant_source_annotations':5,'additional_optional_branch_readout':1,
    'new_complete_reference_protocols_built':0,'prior_reference_reuse':True,'new_KB_numeric_cells':0,
    'author_reading_elapsed_time_measured':False,'independent_new_evaluator_calls':0,
    'new_wetlab_measurements':0,'not_an_expert_accuracy_estimate':True}
b.save(OUT/'effort_and_reference_reuse.json',effort)

links=[]
for path in [OUT/'REPORT_zh.md',OUT/'commands.md',*sorted((OUT/'examples').glob('*/README_zh.md'))]:
    for match in re.finditer(r'\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        target=match[1]
        if target.startswith(('https://','http://','#')):continue
        resolved=(path.parent/unquote(target.split('#')[0])).resolve()
        assert resolved.exists(),(path,target)
        links.append({'from':str(path),'to':str(resolved)})
content=MarkdownIt('commonmark').enable('table').render((OUT/'REPORT_zh.md').read_text(encoding='utf-8'))
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ClearEval 来源语义与条件联合分析</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;max-width:1200px;margin:36px auto;padding:0 24px;line-height:1.75;color:#202733}
table{border-collapse:collapse;width:100%;font-size:.9em;margin:1.2em 0}th,td{border:1px solid #d8dee7;padding:8px;text-align:left;vertical-align:top}th{background:#eef3f7}
a{color:#145aa0}img{max-width:100%;height:auto}code{font-family:Consolas,monospace}pre{white-space:pre-wrap;background:#f3f5f7;padding:14px;overflow-wrap:anywhere}
@media print{body{font-size:10pt;max-width:none;margin:0;padding:0}tr,img{break-inside:avoid}}</style><body>'''+content+'</body></html>'
(OUT/'REPORT_zh.html').write_text(html,encoding='utf-8')

audit={'previous_goal_turn_classification':'progress','this_goal_turn_classification':'progress','goal_complete':False,
    'new_model_calls':0,'evidence':['method_candidate_02/results.json','semantic_04/summary.json',
        'joint_with_optional_bleach/summary.json','joint/source_dependency_audit.json','REPORT_zh.md'],
    'achieved_in_this_stage':['generic Chinese method-header correction','explicit source semantic ledger and three new point CCE records',
        'two additional answers with conditional complete CCE','optional-branch counterexample and paired joint readout',
        'source-dependence representation','exact two-task reweighting','eight full-flow examples'],
    'remaining_explicit_requirements':['actual evaluation of the qualitative Correctness candidate',
        'unexposed automatic extraction validation','controlled deletion and raw SR/SP granularity anomalies',
        'updated cross-evaluator stability','expert 5+15 review','enough independent source blocks for uncertainty',
        'wet-lab empirical data if that validation claim is pursued'],
    'not_counted_as_complete':['all controlled expected effects','automatic 5/8 coverage','independent scientific accuracy',
        'all task-package goals','stable scalar model ranking']}
b.save(OUT/'completion_audit.json',audit)

marker='2026-10-12 来源语义与条件联合续记'
paragraph=marker+'：同一 32 返回离线复用。中文已选方法修复恢复 R3C04 方法/透明度分；5 份助手来源账本使原确认批单值完整 CCE 2→5/8，另 2 份有完整条件结果；自动候选仍 2/8，受控 24/24 原值不变。发现原步骤分句的 Time 归属问题，以及 R3C08 可选漂白 20/32 h 导致时间分 2.570991/3 的真实差异。两生成模型 q23/q248 的 32 个来源/范围场景中均非支配，但平均 HV 排序随分支变化；每场景精确枚举 4 个任务重抽组合，两题共享 FDISCO 形成一个来源依赖块。8 个全流程示例、逐答案分数、实际命令已交付。新增模型调用 0，仍 438/438；新 Cor 实测、跨评价器、专家和湿实验仍未完成。'
navigation=[(Path(r'C:\ClearEval\STATUS.md'),'reports/cleareval_20261012/semantic_source_revision/REPORT_zh.md'),
    (ROOT/'artifacts/cce_validation/STATUS.md','../../../reports/cleareval_20261012/semantic_source_revision/REPORT_zh.md'),
    (ROOT/'artifacts/cce_validation/optimizer_round3_20261011/STATUS.md','../../../../reports/cleareval_20261012/semantic_source_revision/REPORT_zh.md')]
updates=[]
for i,(path,target) in enumerate(navigation):
    old=path.read_text(encoding='utf-8-sig')
    if marker not in old:
        backup=OUT/'status_before_update'/f'{i}_STATUS.md';backup.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,backup)
        first,sep,rest=old.partition('\n')
        path.write_text(first+'\n\n'+paragraph+' [详细结果]('+target+')。\n'+rest,encoding='utf-8')
        updates.append({'path':str(path),'before':b.bind(backup),'after':b.bind(path)})
index=OUT.parent/'README.md';text=index.read_text(encoding='utf-8-sig')
if marker not in text:
    shutil.copyfile(index,OUT/'status_before_update/reports_README.md')
    first,sep,rest=text.partition('\n')
    index.write_text(first+'\n\n- **'+marker+'：** [详细报告](semantic_source_revision/REPORT_zh.md) · [浏览版](semantic_source_revision/REPORT_zh.html) · [逐答案表](semantic_source_revision/semantic_04/per_answer.csv) · [实际命令](semantic_source_revision/commands.md)。来源辅助单值 CCE 5/8，另 2 份条件结果；自动候选仍 2/8。条件联合排名、来源依赖和八个完整流程均已记录，新增调用 0。\n'+rest,encoding='utf-8')
b.save(OUT/'navigation_update.json',{'updates':updates,'latest_scores':b.bind(OUT/'semantic_04/results.json')})
verification=b.read(OUT/'delivery_verification.json')
verification.update(local_links_verified=len(links),local_links=links,
    figure_visual_inspection='PNG viewed after correcting crowded ticks and legend; no clipping or overlaps observed',
    finalization_command=[sys.executable,*sys.argv])
b.save(OUT/'delivery_verification.json',verification)
files=[b.bind(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts]
b.save(OUT/'delivery_manifest.json',{'files':files,'new_model_calls':0,'goal_complete':False})
print(json.dumps({'files':len(files),'local_links_verified':len(links),'source_files_verified':verification['source_files_verified'],
    'goal_complete':False,'new_model_calls':0,'status_files_updated':len(updates)},ensure_ascii=False))
