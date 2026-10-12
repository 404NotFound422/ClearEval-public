"""Start a time-bounded evaluator optimization stage from the verified 192-call state."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'optimizer_20261010'
SNAPSHOT=BASE/'historical_reports/before_optimizer_at_192'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    if (OUT/'plan.json').exists():
        print(json.dumps({'status':'existing_stage_preserved','plan':str(OUT/'plan.json')}));return
    previous=read(BASE/'report_verification_method_family_v1.json')
    for path,h in previous['input_sha256'].items():
        if sha(path)!=h:raise ValueError('previous_input_changed:'+path)
    for path,h in previous['output_sha256'].items():
        if sha(BASE/path)!=h:raise ValueError('previous_output_changed:'+path)
    ledger=BASE/'judges/request_ledger.jsonl'
    rows=[json.loads(s) for s in ledger.read_text(encoding='utf-8').splitlines() if s.strip()]
    if len(rows)!=192:raise ValueError('optimizer_must_start_from_192_actual_requests')
    files=[BASE/name for name in previous['output_sha256']]
    files += [BASE/'report_generation.json',BASE/'report_verification_method_family_v1.json',ledger,
              BASE/'method_family_followup_v1/integration_review.json',ROOT/'scripts/cce_report.py',
              ROOT/'scripts/cce_report_method_family_v1.py']
    records=[]
    for p in files:
        name=Path('scripts')/p.name if p.parent==ROOT/'scripts' else p.relative_to(BASE)
        target=SNAPSHOT/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)!=sha(p):raise ValueError('snapshot_collision:'+str(target))
        if not target.exists():shutil.copyfile(p,target)
        records.append({'source':str(p),'relative_path':name.as_posix(),'sha256':sha(target)})
    save(SNAPSHOT/'snapshot_manifest.json',{'status':'byte_preserved','files':records,'requests':192})
    started=datetime.fromtimestamp(1791565080,tz=timezone.utc)
    plan={
        'stage':'optimizer_20261010','status':'active','user_goal':'Optimize the benchmark evaluator through real iterative experiments; after maturity use subagents as explicitly identified model evaluation sources for sampled archived-answer retesting.',
        'goal_started_utc':started.isoformat(),'deadline_utc':(started+timedelta(hours=9)).isoformat(),
        'time_limit_hours':9,'starting_requests':192,'whole_package_request_limit':300,
        'remaining_at_start':108,'budget':{'development_including_model_only_probe':25,'full_control_batch':21,'two_family_repeats':30,'confirmation_eight_answers_two_sources':16,'reserved':16},
        'first_batch':{'kind':'model_only_comparison','model':'qwen3.8:27b-q8_0-local','fixed_n':5,'max_attempts':1,
                       'prompt':'unchanged_output_identity_v2','format':'json','temperature':0,'max_output_tokens':8192,'num_ctx':40960},
        'invariants':['Preserve historical scores, original BioProBench baseline, c_param/Correctness scales and EGES functions.',
                      'Version every new extraction or matching policy and record all actual requests and failures.',
                      'No selection of best repeated result; no fabricated labels or quiet edits of prior references.',
                      'Do not tune on the original 15 human-review holdout answers or the prospectively frozen automatic confirmation set.',
                      'Unresolved source relations remain unresolved, with coverage and NA tracked so abstention cannot masquerade as an improvement.',
                      'Subagent assessments are model-generated evaluations, not human expert returns or independently verified biological truth.'],
        'success_assessment':'Pre-register operational checks before candidate generation, including structural success, source-span validity, explicit-information retention, behavior on valid controls, repeat stability, coverage and prospectively frozen confirmation. Failed expected effects remain failures; coarse rubric changes are required only when a justified boundary is crossed.',
        'workstreams':['source-bound extraction and deterministic quantitative assembly','action/object and parameter evidence for step matching','frozen controlled/stability/confirmation experiment design','model-only capacity comparison'],
        'human_budget':{'experts':1,'development':5,'holdout':15,'actual_returns':0,'unchanged':True},
        'previous_verified_report':str(SNAPSHOT/'CURRENT_RESULTS_INDEX.md'),
        'actual_command':[sys.executable,*sys.argv],'new_generation_requests':0}
    save(OUT/'plan.json',plan)
    save(OUT/'STATUS.json',{'status':'active','requests':192,'next':'Freeze and execute the five-case local model-only comparison; prepare grounded extraction and independent controls in parallel.','deadline_utc':plan['deadline_utc']})
    (BASE/'STATUS.md').write_text('# ClearEval 当前优化阶段\n\n用户授权的九小时评估器优化已启动。起始实际请求192/300，后续以全局账本为准。\n\n当前计划：[optimizer_20261010/plan.json](optimizer_20261010/plan.json)，动态进度：[optimizer_20261010/STATUS.json](optimizer_20261010/STATUS.json)。\n\n此前192次结果已逐字封存于[历史快照](historical_reports/before_optimizer_at_192/CURRENT_RESULTS_INDEX.md)，原主50/77及条件性66/77均保留。旧报告生成器只接受192次账本，新阶段应从本计划与真实试次继续。\n\n本阶段依次比较模型能力、来源绑定提取、步骤匹配证据、完整受控配对、真实重复和固定抽样确认。所有失败保留，原专家5＋15核查包不改；模型评测不冒充专家结论。\n',encoding='utf-8')
    (ROOT.parent/'STATUS.md').write_text('# ClearEval 当前状态\n\n九小时优化阶段进行中，见[当前状态](ClearEval-public/artifacts/cce_validation/STATUS.md)。\n\n起始192/300次请求；旧结果已封存，新结果按版本独立验证。\n',encoding='utf-8')
    print(json.dumps({'status':'optimizer_started','snapshot_files':len(records),'requests':192,'deadline_utc':plan['deadline_utc'],'new_calls':0}))


if __name__=='__main__':main()
