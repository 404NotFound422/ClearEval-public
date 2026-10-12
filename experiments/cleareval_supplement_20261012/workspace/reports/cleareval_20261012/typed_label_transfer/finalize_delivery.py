"""Verify the delivered result, refresh current navigation, and preserve history."""
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote
from markdown_it import MarkdownIt
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
rows=b.read(OUT/'time_heading_candidate_01/results.json')
assert len(rows)==32
for cohort,count in [('E2_canonical_qwen_01',24),('confirmation_qwen_01',2)]:
    assert sum(b.complete(r['final_candidate_metrics']) for r in rows if r['cohort']==cohort)==count
assert sum(r['lexical_full_conversion'] for r in rows if r['cohort']=='confirmation_qwen_01')==7
assert all(r['new_model_calls']==0 for r in rows)
verified=b.read(OUT/'scope_candidate_02/verification.json')
for binding in verified['source_bindings']:
    assert b.bind(binding['path'])==binding
budget=b.read(R3/'source_context_validation_proposal_01/budget_snapshot.json')
assert b.bind(budget['ledger']['path'])==budget['ledger']
assert budget['attempts_recorded']==438 and budget['remaining_request_capacity']==0

# Check current external inputs rather than trusting the preceding status prose.
external=b.read(R3/'external_dependencies_check_01.json')
human=ROOT/'artifacts/cce_validation/human_review/reviewer/review_items.csv'
with human.open(encoding='utf-8-sig',newline='') as f:human_rows=list(csv.DictReader(f))
fields=list(external['expert_nonempty_fields'])
nonempty={key:sum(bool(r.get(key,'').strip()) for r in human_rows) for key in fields}
human_bindings=[b.bind(x['path']) for x in external['human_input_bindings']]
wet_path=Path(external['wetlab_measurements']['path'])
with wet_path.open(encoding='utf-8-sig',newline='') as f:wet_rows=list(csv.DictReader(f))
assert not any(nonempty.values()) and len(wet_rows)==0
b.save(OUT/'external_state.json',{'budget':budget,'ledger_unchanged':True,'new_model_calls':0,
    'expert_rows':len(human_rows),'expert_nonempty_fields':nonempty,'human_inputs':human_bindings,
    'wetlab_data_rows':len(wet_rows),'wetlab_source':b.bind(wet_path)})

# Preserve source snapshots when a stage's entry point was explicitly revised.
for phase in ['actual_01','scope_candidate_02','lexical_candidate_02','time_heading_candidate_01']:
    plan=b.read(OUT/phase/'plan.json')
    for key,value in plan.items():
        if isinstance(value,dict) and 'path' in value and 'sha256' in value:
            assert b.bind(value['path'])==value,(phase,key)
old=b.read(OUT/'scope_candidate_01/plan.json')
assert b.bind(OUT/'scope_candidate_01/entrypoint_snapshot.py')['sha256']==old['entrypoint']['sha256']
assert b.bind(OUT/'scope_candidate_01/scope_module_snapshot.py')['sha256']==old['scope_candidate']['sha256']
old=b.read(OUT/'lexical_candidate_01/plan.json')
assert b.bind(OUT/'lexical_candidate_01/entrypoint_snapshot.py')['sha256']==old['entrypoint']['sha256']
pending=b.read(OUT/'qualitative_canonical_pending/manifest.json')
assert len(pending['observations'])==10 and pending['new_model_requests']==0
for observation in pending['observations']:
    for key in ['source','mapping','payload','schema']:assert b.bind(observation[key]['path'])==observation[key]

links=[]
for filename in ['REPORT_zh.md','commands.md']:
    body=(OUT/filename).read_text(encoding='utf-8')
    for match in re.finditer(r'\]\(([^)]+)\)',body):
        link=match[1]
        if link.startswith(('http://','https://','#')):continue
        path=(OUT/unquote(link.split('#')[0])).resolve()
        assert path.exists(),(filename,link)
        links.append({'from':filename,'target':str(path)})
content=MarkdownIt('commonmark').enable('table').render((OUT/'REPORT_zh.md').read_text(encoding='utf-8'))
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ClearEval：后续32份真实返回</title>
<style>body{font:16px/1.8 "Microsoft YaHei",system-ui,sans-serif;color:#172b3a;max-width:1180px;margin:36px auto;padding:0 24px}
h1{font-size:28px;line-height:1.4}p{margin:18px 0}a{color:#086698}img{width:100%;height:auto}
table{border-collapse:collapse;width:100%;font-size:14px;margin:22px 0}th,td{border:1px solid #ccd4dc;padding:10px;text-align:left;vertical-align:top}th{background:#edf3f7}
code{background:#edf3f7;padding:2px 4px}pre{overflow:auto;background:#edf3f7;padding:18px}
@media print{body{font-size:11pt;max-width:none;padding:0}tr,img{break-inside:avoid}a{color:inherit}}</style><body>'''+content+'</body></html>'
(OUT/'REPORT_zh.html').write_text(html,encoding='utf-8')

audit={'previous_goal_turn_classification':'progress','this_goal_turn_classification':'progress',
    'evidence':['actual_01/summary.json','scope_candidate_02/readout.json','lexical_candidate_02/summary.json',
        'time_heading_candidate_01/summary.json','qualitative_canonical_pending/manifest.json'],
    'goal_complete':False,'new_model_calls':0,'expert_validation_received':False,
    'achieved_in_this_stage':['fixed label-rule transfer','complete controlled paired readout',
        'two literal-boundary repairs','title and wash time-scope corrections','descriptive repeat and resampling analysis',
        'five complete trace examples','paired qualitative development inputs prepared'],
    'remaining_explicit_requirements':['new qualitative judging rule actual validation',
        'controlled component anomalies and SR/SP granularity sensitivity',
        'remaining confirmation extraction dependencies','updated cross-evaluator stability',
        'expert 5+15 review','complete common-support confirmation analysis',
        'source-family dependence analysis','wet-lab empirical data'],
    'not_counted_as_complete':['all expected controlled effects','scientific extraction accuracy',
        'independent prospective validation of post-hoc fixes','all CCE scores or all task-package goals']}
b.save(OUT/'completion_audit.json',audit)

# Current navigation is updated only after the result and input audit passes.
marker='2026-10-12 后续 32 返回复算续记'
note=marker+'：复用 24 份规范化受控返回和 8 份原确认返回，固定标签规则使受控完整 CCE 0→18/24；已报告核心操作范围、重复通道、名称边界和标题/清洗范围候选进一步得到 24/24 与 2/8。确认批完整结构转换 5→7/8；原 SR/SP、旧直接分数及 EGES 公式保留。18 个完整成对观测中，编号全部不变，删除三题 HV 均下降，但 q2 Cor 上升、q22 Com 不响应和合并导致的原 SR/SP 漂移仍在。108 个基础分项重复组均有限且零极差；改善的是覆盖，不是新证实随机波动降低。三题重采样 2,000 次与 27 精确枚举已保存。定性 Correctness 已接入规范化全文并准备 5 组、10 份请求，尚未调用。全包仍 438/438，专家与湿实验无新增数据；整体目标未完成。'
navigation=[
    (Path(r'C:\ClearEval\STATUS.md'),'reports/cleareval_20261012/typed_label_transfer/REPORT_zh.md'),
    (ROOT/'artifacts/cce_validation/STATUS.md','../../../reports/cleareval_20261012/typed_label_transfer/REPORT_zh.md'),
    (R3/'STATUS.md','../../../../reports/cleareval_20261012/typed_label_transfer/REPORT_zh.md')]
status_records=[]
for index,(path,relative) in enumerate(navigation):
    body=path.read_text(encoding='utf-8')
    if marker not in body:
        backup=OUT/'status_before_update'/f'{index}_STATUS.md'
        backup.parent.mkdir(exist_ok=True);backup.write_bytes(path.read_bytes())
        title,rest=body.split('\n',1)
        path.write_text(title+'\n\n'+note+f' [本轮完整交付]({relative})。下面保留各历史阶段记录。\n'+rest,encoding='utf-8')
        status_records.append({'updated':b.bind(path),'before':b.bind(backup)})
readme=OUT.parent/'README.md';body=readme.read_text(encoding='utf-8')
if marker not in body:
    backup=OUT/'status_before_update/report_README.md';backup.write_bytes(readme.read_bytes())
    title,rest=body.split('\n',1)
    text='\n\n- **'+marker+'：** [详细报告](typed_label_transfer/REPORT_zh.md) · [浏览版](typed_label_transfer/REPORT_zh.html) · [逐答案表](typed_label_transfer/time_heading_candidate_01/per_answer.csv) · [实际命令](typed_label_transfer/commands.md)。受控完整 CCE 24/24，原确认批 2/8；确认结构转换 7/8。18 个完整成对观测、明确保留的反例、五个流程实例与整体未完成项均已记录。新增请求 0；以下较早的“编号未解决”仅指旧设置。\n'
    readme.write_text(title+text+rest,encoding='utf-8')
    status_records.append({'updated':b.bind(readme),'before':b.bind(backup)})
b.save(OUT/'navigation_update.json',{'updates':status_records,'current_result':b.bind(OUT/'time_heading_candidate_01/results.json')})
b.save(OUT/'delivery_verification.json',{'source_files_verified':len(verified['source_bindings']),
    'local_links_verified':len(links),'links':links,'prepared_request_packets':10,'new_model_calls':0,
    'figures_visually_inspected':True,'visual_check':'PNG axes, legends, counts and task points inspected; no clipping observed.',
    'original_ledger_unchanged':True,'complete_CCE_counts':{'controlled':24,'confirmation':2},
    'goal_completion_proven':False})
b.save(OUT/'delivery_execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0})
files=[b.bind(path) for path in sorted(OUT.rglob('*')) if path.is_file() and path.name!='delivery_manifest.json']
b.save(OUT/'delivery_manifest.json',{'files':files,'new_model_calls':0,'goal_complete':False})
print(json.dumps({'source_files_verified':len(verified['source_bindings']),'links':len(links),
    'bound_delivery_files':len(files),'expert_nonempty_fields':nonempty,'wetlab_rows':len(wet_rows),
    'model_calls':438,'new_model_calls':0,'goal_complete':False},ensure_ascii=False))
