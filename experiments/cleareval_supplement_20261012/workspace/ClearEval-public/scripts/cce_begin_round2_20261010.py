"""Record the explicit second-round authorization; never invoke generation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys, urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'optimizer_round2_20261010'
LEDGER=BASE/'judges/request_ledger.jsonl'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    assert not (OUT/'authorization.json').exists(),'Authorization already recorded; do not reset deadline'
    rows=[json.loads(x) for x in LEDGER.read_text(encoding='utf8').splitlines() if x.strip()]
    count=sum(r.get('event')=='request_started' for r in rows)
    assert count==294,'Unexpected new request before authorization snapshot'
    now=datetime.now(timezone.utc)
    stop=datetime(2026,10,10,8,51,tzinfo=timezone.utc)
    assert now<stop
    auth={'status':'explicit_user_authorization_recorded_before_new_calls',
        'recorded_utc':now.isoformat(),'user_reply':'批准新一轮 6 小时／100 次',
        'authorized_new_local_requests':100,'starting_package_requests':294,
        'previous_package_limit':300,'new_package_limit':394,
        'time_limit_hours':6,'conservative_start_utc':'2026-10-10T02:51:00+00:00',
        'deadline_utc':stop.isoformat(),
        'start_note':'Conservative minute boundary preceding the first post-approval clock observation at 02:51:43 UTC; not a claim of an exact user-message timestamp.',
        'stop_at_first_time_or_call_limit':True,'organization_time_included':True,
        'phase_new_request_limits':{'development':30,'E2':21,'E4':30,'confirmation':16},
        'allocated_maximum':97,'unallocated_not_retry_authorization':3,
        'exact_reuse_never_counts_as_new':True,'max_attempts_per_cell':1,
        'local_only':True,'preferred_model_alias':'qwen3.8:27b-q8_0-local',
        'preference_user_text':'本地模型尽量调用ｑｗｅｎ３.８',
        'other_family_only_for_required_comparisons_and_bounded_development_checks':True,
        'original_functions_rubrics_weights_demands_preserved':True,
        'expert_budget':{'experts':1,'development':5,'holdout':15,'new_returns_at_start':0},
        'confirmation_policy':'Prospectively freeze eight archived answers, exclude original expert15, previous confirmation8 and registered tuning answers. Do not claim absence of all historical exposure unless evidence establishes it. Unavailable eligible count remains a gap.',
        'old_development_40_over_25_failure_remains':True,
        'no_guarantee_of_expected_scientific_result':True,
        'historical_ledger_sha256':sha(LEDGER),'new_generation_calls_by_this_command':0,
        'actual_command':[sys.executable,*sys.argv]}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'ledger_at_authorization.jsonl').write_bytes(LEDGER.read_bytes())
    sources={
        'original_acceptance':BASE/'optimizer_20261010/validation_design_v1/acceptance_matrix.json',
        'original_inventory':BASE/'optimizer_20261010/validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json',
        'original_scoring':ROOT/'scripts/cce_validation.py',
        'previous_root_review':BASE/'optimizer_20261010/root_terminal_delivery_v1/root_review.json',
        'previous_primary_completion':BASE/'optimizer_20261010/grounded_confirmation_v3/completion_summary.json'}
    auth['preserved_inputs']={k:{'path':str(p),'sha256':sha(p)} for k,p in sources.items()}
    save(OUT/'authorization.json',auth)
    live={}
    for endpoint in ['tags','version','ps']:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/'+endpoint,timeout=10) as response:
            value=json.load(response)
        if endpoint=='tags':
            value={'models':[x for x in value.get('models',[]) if x.get('name') in ['qwen3.8:27b-q8_0-local','llama3-8B:latest']]}
        live[endpoint]=value
    save(OUT/'local_service_readonly_snapshot.json',{'observed_utc':datetime.now(timezone.utc).isoformat(),
        'generation_requests':0,'responses':live,'actual_command':[sys.executable,*sys.argv]})
    plan={'status':'authorized_round_started_candidate_not_yet_frozen','authorization_sha256':sha(OUT/'authorization.json'),
        'development_priority':['compact_strict_source_bound_output','explicit_relation_endpoint_support',
            'lossless_operation_duration_binding','candidate_coverage_and_time_scope_accounting'],
        'primary_development_model':'qwen3.8:27b-q8_0-local',
        'stages':['offline_regression_and_candidate_freeze','Qwen_priority_development_up_to30',
            'one_selected_configuration_fulltext_E2_21','E4_two_families_5answers_3repeats',
            'new_prospective_answer_confirmation_8x2','actual_analysis_and_bilingual_report'],
        'new_candidate_results_available':False,'new_requests':0,'remaining_authorized_new_requests':100,
        'scientific_acceptance_established':False,'all_goals_complete':False,
        'deadline_utc':stop.isoformat(),'no_optional_blind_budget_allocated':True}
    save(OUT/'plan.json',plan)
    status='''# 第二轮优化状态

用户已批准新一轮最多 6 小时、100 次本地调用。原账本 294 次，新总上限 394；截止 2026-10-10 08:51 UTC（北京时间 16:51），时间和计次先到者停止，整理时间包含其中。

开发优先使用本地 `qwen3.8:27b-q8_0-local`；实际服务报告的 family/digest 另存，不以别名推断官方版本。另一模型保留必要跨家族对照。

当前为离线实现与事前冻结阶段，尚无新一轮模型结果或生成调用。旧 v7 的失败和 NA 保留，旧开发 40>25 的偏离不被本次授权抹去。

预算：开发≤30，E2 21，E4≤30，新确认16，合计≤97；余3不自动用于重试。若 E4 精确复用5条，新增最多92，余8同样不授权重试。每格只尝试一次。

参见 [授权](authorization.json)、[计划](plan.json)、[本地服务只读核验](local_service_readonly_snapshot.json) 和 [上一轮完整交付](../optimizer_20261010/root_terminal_delivery_v1/HANDOFF_zh.md)。
'''
    (OUT/'STATUS.md').write_text(status,encoding='utf8')
    old=OUT/'previous_navigation';old.mkdir(exist_ok=True)
    p=ROOT.parent/'STATUS.md';(old/'workspace_STATUS.md').write_bytes(p.read_bytes())
    p.write_text('# ClearEval 当前状态\n\n[第二轮优化](ClearEval-public/artifacts/cce_validation/optimizer_round2_20261010/STATUS.md)已获批：6小时、100次本地调用，截止北京时间16:51。新模型结果尚未产生。\n\n[上一轮交付](ClearEval-public/artifacts/cce_validation/optimizer_20261010/root_terminal_delivery_v1/HANDOFF_zh.md)保留：16格确认4成功12失败，完整CCE0/16，整体目标尚未达成。\n',encoding='utf8')
    print(json.dumps({'status':'round2_authorized_started','starting_requests':count,'new_requests':0,
        'deadline_utc':stop.isoformat(),'authorization_sha256':sha(OUT/'authorization.json')},ensure_ascii=False))

if __name__=='__main__':main()
