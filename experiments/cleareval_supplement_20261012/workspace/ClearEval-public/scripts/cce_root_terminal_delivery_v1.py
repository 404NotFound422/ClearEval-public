"""Record root adjudication and completed bounded execution; no scientific calls."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OPT = BASE / 'optimizer_20261010'
OUT = OPT / 'root_terminal_delivery_v1'
PYTHON = r'C:\ClearEval\review_artifacts\bioprobench_2026-09-29\python_portable\python.exe'

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def bind(p):
    return {'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}

def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

def main():
    assert not OUT.exists(), 'No overwrite of terminal delivery'
    now = datetime.now(timezone.utc)
    assert now < datetime(2026,10,10,2,43,tzinfo=timezone.utc), 'Authorized extension expired'
    paths = {
        'standard': OPT/'validation_design_v1/acceptance_matrix.json',
        'recommendations': OPT/'root_final_decision_preparation_v1/post_primary_revision03/recommendations.json',
        'step_diagnostic': OPT/'root_final_decision_preparation_v1/post_primary_revision03/primary_C05_C07_step_diagnostic.json',
        'primary': OPT/'grounded_confirmation_v3/completion_summary.json',
        'primary_verification': OPT/'grounded_confirmation_v3/verification.json',
        'source_audit': OPT/'grounded_confirmation_v3_source_audit_v1/snapshot_20261010T022731_396103Z_terminal16/summary.json',
        'report_manifest': OPT/'manuscript_supplement_v7_final_v1/actual/render_manifest.json',
        'independent_report_check': OPT/'manuscript_supplement_v7_final_v1/independent_delivery_check.json',
        'requirements': OPT/'r2_completion_audit_v1/revision03/audit.json',
        'acceptance_metadata': OPT/'acceptance_evidence_audit_v1/revision03/audit.json',
        'status': OPT/'STATUS.json',
    }
    data = {k:read(p) for k,p in paths.items()}
    assert data['primary']['actual_terminal_observations'] == 16
    assert data['primary_verification']['status'] == 'pass'
    assert data['primary_verification']['attempt1_only'] is True
    assert data['source_audit']['technical_success_observations'] == 4
    assert data['source_audit']['failed_observations'] == 12
    assert data['report_manifest']['scientific_acceptance_established'] is False
    assert data['report_manifest']['new_model_requests'] == 0
    standards = {r['check_id']:r for r in data['standard']['checks']}
    proposals = {r['check_id']:r for r in data['recommendations']['clauses']}
    assert all(proposals[k]['original_clause'] == v for k,v in standards.items())
    # Root reviewed the unchanged clauses, completed analyses, source audits,
    # actual figures and all recommendations before selecting these outcomes.
    decisions = {k:'incomplete' for k in standards}
    decisions.update({k:'pass' for k in ['T01','P03','S01','S02','A01']})
    decisions.update({k:'fail' for k in ['F02','C05','G01']})
    decisions['G02']='unknown'
    rows=[]
    for k, clause in standards.items():
        proposal=proposals[k]
        rows.append({'check_id':k,'original_clause':clause,'root_outcome':decisions[k],
            'scope':proposal['recommendation_scope'],'evidence':proposal['evidence'],
            'limits_or_remaining':proposal['limits_or_remaining'],
            'evidence_bindings':proposal['evidence_bindings']})
    counts=dict(Counter(decisions.values()))
    assert counts == {'pass':5,'incomplete':11,'fail':3,'unknown':1}
    OUT.mkdir()
    review={'status':'root_terminal_review_complete_goals_not_achieved',
        'created_utc':now.isoformat(),'reviewed_by':'root_agent','counts':counts,'rows':rows,
        'scientific_acceptance_established':False,'all_user_goals_complete':False,
        'P03_scope':'Published final frozen v7 dev/E2/E4/primary components; no blanket certification of historical candidates.',
        'F03_scope':'Candidate accounting is complete, but observed unaccounted explicit mentions and incomplete semantic coverage prevent acceptance.',
        'historical_revision02_and_revision03_metadata_unchanged':True,
        'inputs':{k:bind(p) for k,p in paths.items()},'new_model_requests':0,'new_score_runs':0,
        'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'root_review.json',review)
    lines=['# ROOT 最终阶段审阅','',
        '冻结 v7 本轮：5 项通过、11 项未完成、3 项失败、1 项无法充分核实。执行结束不等于全部目标完成。',
        '原 20 条款对象不变；中期 revision02 和元数据 revision03 原样保留，当前裁定以本文件及 root_review.json 为准。','',
        '| 条款 | 当前裁定 | 证据与范围 |','|---|---|---|']
    for r in rows:
        lines.append(f"| {r['check_id']} | {r['root_outcome']} | {r['evidence']} {r['limits_or_remaining']} |")
    lines += ['', 'P03 通过仅针对最终冻结 v7 四阶段已发布分项的原函数、数值与 NA 重放；没有把来源语义正确纳入公式重放结论。S01/S02/A01 通过分别表示诊断或执行报告完成，不能解释为科学验证通过。',
        '', 'F03 候选清点已完成，但明确遗漏及语义覆盖边界仍未消除，故不授予完整覆盖通过。F02、C05、G01 的反例不能由后续报告完成抵消。',
        '', '[逐条机器记录及哈希](root_review.json) · [原条款](../validation_design_v1/acceptance_matrix.json) · [独立建议](../root_final_decision_preparation_v1/post_primary_revision03/README.md)','']
    (OUT/'ROOT_REVIEW_zh.md').write_text('\n'.join(lines),encoding='utf8')
    save(OUT/'PRIMARY_PHASE_CLOSED.json',{'created_utc':now.isoformat(),
        'status':'execution_analysis_and_reporting_closed_not_scientific_acceptance',
        'planned_cells':16,'terminal_cells':16,'technical_successes':4,'failures':12,
        'complete_CCE':0,'common_complete_answers':0,'common_answer_denominator':8,
        'user_authorized_deadline_utc':'2026-10-10T02:43:00+00:00',
        'root_review':bind(OUT/'root_review.json'),'optional_blind_authorized':False,
        'retries_or_confirmation_driven_tuning_authorized':False,'new_model_calls':0,
        'goal_complete':False,'old_deadline_stop_executed':False,'partial_observer_executed':False})
    commands=[
        ['scripts/cce_grounded_confirmation_v3.py','run','--allow-local-calls'],
        ['scripts/cce_grounded_confirmation_v3.py','analyze'],
        ['scripts/cce_report_grounded_confirmation_v3.py','render'],
        ['artifacts/cce_validation/optimizer_20261010/grounded_confirmation_v3_source_audit_v1/audit_terminal.py','--terminal-authorized'],
        ['scripts/cce_final_acceptance_revision03.py','build'],
        ['scripts/cce_report_optimizer_v7_final_v1.py','render'],
        ['scripts/cce_optimizer_status_v2.py'],
    ]
    save(OUT/'actual_commands.json',{'cwd':str(ROOT),'commands':[[PYTHON,*c] for c in commands],
        'all_listed_commands_actually_completed':True,'listed_terminal_exit_codes':[0]*len(commands),
        'not_a_claim_that_every_historical_attempt_succeeded':True,
        'source_audit_first_attempt_exit_code':1,
        'source_audit_failure_record':str(OPT/'grounded_confirmation_v3_source_audit_v1/failed_execution_01.json'),
        'source_audit_inspector_only_fix_record':str(OPT/'grounded_confirmation_v3_source_audit_v1/revision03_nullable_scope_diff.patch'),
        'primary_run_session':45480,'primary_analyze_session':63587,
        'root_delivery_actual_command':[sys.executable,*sys.argv]})
    handoff='''# 延期内执行与最终交付

本轮延期范围内的 16 格确认、原分析、独立来源核查、图表和中英文论文补充均已实际完成。整体目标尚未达到，不能宣称评价器完善或科学验收通过。新截止为 2026-10-10 02:43 UTC（北京时间 10:43）；本交付在期限内生成。

| 阶段 | 全部终态 | 技术成功/失败 | 完整数值 |
|---|---:|---:|---:|
| 冻结 v7 开发 | 5 | 5 / 0 | 0/5（九项直接量表/EGES） |
| E2 受控文本 | 21 | 16 / 5 | 1/21；两端完整配对 0/15 |
| E4 重复评价 | 30 | 15 / 15 | 0/30 |
| 主确认 | 16 | 4 / 12 | CCE 0/16；共同完整答案 0/8 |

E4 包含 5 次精确复用及 25 次新请求。全包账本计次为 294/300；未分配的 6 次不自动成为重试授权。原开发 40 次超过原 25 次阶段上限的偏离保留。

主确认的 12 次失败分为 7 次来源转换失败和 5 次达到 8192 输出上限的截断 JSON。成功的 4 次也不等于事实全正确：4 条关系中 2 条获原局部门接受、1 条引用缺端点、1 条 unknown。5 份截断返回的主张总数未知。原始返回、失败、数值和配置均未为通过验收而改写。

主确认 SR/SP 有 14/16 格可算；Com 3/16、Cor 4/16、Eff/IA/HV 均 0/16。答案 C05 的 NA 来自任务范围内参考池为空；答案 C07 的真实零来自两个参考版本均未达到冻结阈值，不等于语义上没有操作。这里的答案编号 C05 与验收条款 C05 是两个不同对象。

稳定性方面，69/160 个组有三次有限观测，极差均为零；五项直接评分单列为 25/50 组可算。跨评价器直接评分 0/25 组、0/75 对可比较，一致性仍为 NA。确定性 SR/SP 的相同结果不提供独立模型一致性证据。

这批结果支持论文报告评价器的失败类型、数值可用性和表示敏感性，不能支持评价器已完善、跨模型可互换、独立任务泛化或湿实验有效性。最终条款裁定为 5 通过、11 未完成、3 失败、1 未知；通过项的范围详见 ROOT 审阅。

交付入口：

- [统一中英文 Results、摘要、逐分项表](../manuscript_supplement_v7_final_v1/actual/INDEX.md)；[独立终检](../manuscript_supplement_v7_final_v1/independent_delivery_check.md)。
- [ROOT 逐条裁定](ROOT_REVIEW_zh.md)；[实际命令](actual_commands.json)。
- [主确认逐答案 CSV](../grounded_confirmation_v3/observations.csv)；[图](../grounded_confirmation_v3_report_v1/actual/per_answer_cce.png)；[中文结果](../grounded_confirmation_v3_report_v1/RESULTS_TERMINAL_zh.md)。
- [来源失败排查全过程](../grounded_confirmation_v3_source_audit_v1/EXECUTION.md)；[失败分层解释](../grounded_confirmation_v3_report_v1/source_failure_addendum_v1/ADDENDUM_zh.md)。
- [C05 NA 与 C07 真零诊断](../root_final_decision_preparation_v1/post_primary_revision03/primary_C05_C07_step_diagnostic.json)。
- [E2 受控结果](../grounded_controls_v7_report_v1/RESULTS_FINAL_zh.md)；[E4 稳定性结果](../grounded_stability_v7_report_v1/RESULTS_FINAL_zh.md)。
- [已发表方法及采用边界](../PUBLISHED_METHODS_ADDENDUM_zh.md)。

剩余事项不仅是专家核查。已知未修复项包括无来源支持的关系断言、无损合并后丢失 8 个有限时长绑定、显式候选遗漏、部分参数/阶段/时间依赖对应未核完，以及跨评价器直接评分没有有限配对。旧请求 1–136 的全字段证据覆盖和整个历史留出访问边界仍不能充分核实。旧 3211 份存档未做步骤评分；固定 13 模型的来源家族 bootstrap 尚未运行，其共同聚类定义未冻结。

一位专家 5 开发＋15 留出的真实回传仍为 0，模型审计不代替专家。实际湿实验观察为 0；现有 42 项规划情景不当作实验观察或效果验证。参考完整性与任务适用性仍需分开登记，不能把条件性路线覆盖当正式参考建设完成。

后续开发应先在原开发范围验证更紧凑的来源绑定输出、显式端点约束、窄操作引用与时长绑定，再检查多语言步骤表示和阈值的响应。提高输出上限只是待测假设，不能保证解决截断或语义问题。当前确认结果不得用于调参后仍宣称同一批前瞻确认；任何后续模型试验需另行冻结范围与预算，本次延期不授权追加。
'''
    (OUT/'HANDOFF_zh.md').write_text(handoff,encoding='utf8')
    # Preserve previous navigational bytes before linking the completed delivery.
    old=OUT/'previous_navigation';old.mkdir()
    navigation=[BASE/'CURRENT_RESULTS_INDEX.md',BASE/'STATUS.md',ROOT.parent/'STATUS.md',OPT/'RESULTS_zh.md']
    for i,p in enumerate(navigation):
        (old/f'{i}_{p.name}').write_bytes(p.read_bytes())
    current='''# 当前结果索引

2026-10-10：冻结 v7 的开发、E2、E4 与 16 格主确认均已实际分析。账本计次 294/300；本轮执行结束，全部研究目标尚未达成。

- [最终交付、未达标项和后续依赖](optimizer_20261010/root_terminal_delivery_v1/HANDOFF_zh.md)。
- [中英文论文补充、摘要与分项表](optimizer_20261010/manuscript_supplement_v7_final_v1/actual/INDEX.md)。
- [ROOT 20 条验收](optimizer_20261010/root_terminal_delivery_v1/ROOT_REVIEW_zh.md)：5 通过、11 未完成、3 失败、1 未知。
- [状态及逐阶段计数](STATUS.md)；[主确认真实逐答案结果](optimizer_20261010/grounded_confirmation_v3/observations.csv)。
- [失败排查与实际命令](optimizer_20261010/grounded_confirmation_v3_source_audit_v1/EXECUTION.md)。
- [原 192 次阶段历史入口](historical_reports/before_optimizer_at_192/CURRENT_RESULTS_INDEX.md)：主 50/77 与条件方法池 66/77 单列，不与 v7 混合。

专家回传 0、实际湿实验观察 0，完整主确认 CCE 0/16；这些缺口没有补零或伪造。
'''
    (BASE/'CURRENT_RESULTS_INDEX.md').write_text(current,encoding='utf8')
    links={BASE/'STATUS.md':'optimizer_20261010/root_terminal_delivery_v1/HANDOFF_zh.md',
        ROOT.parent/'STATUS.md':'ClearEval-public/artifacts/cce_validation/optimizer_20261010/root_terminal_delivery_v1/HANDOFF_zh.md',
        OPT/'RESULTS_zh.md':'root_terminal_delivery_v1/HANDOFF_zh.md'}
    for p,link in links.items():
        note=f'\n\n## 本轮终态交付（2026-10-10）\n\n16 格主确认已全部分析：4 成功、12 失败、完整 CCE 0/16；此前“运行中”的段落为历史记录。E2/E4/主确认原分析、真实图表、来源审计和统一论文补充均完成。最终 20 条裁定为 5 通过、11 未完成、3 失败、1 未知；整体目标尚未达成。参见[完整交付与依赖]({link})。没有追加请求或重试。\n'
        with p.open('a',encoding='utf8') as f:f.write(note)
    manifest={'status':'root_terminal_delivery_written','created_utc':now.isoformat(),
        'outputs':[bind(p) for p in sorted(OUT.iterdir()) if p.is_file()],
        'navigation_outputs':[bind(p) for p in navigation],
        'script':bind(Path(__file__)),'actual_command':[sys.executable,*sys.argv],
        'new_model_requests':0,'new_score_runs':0,'scientific_acceptance_established':False}
    save(OUT/'manifest.json',manifest)
    print(json.dumps({'status':manifest['status'],'counts':counts,'handoff':str(OUT/'HANDOFF_zh.md'),'new_model_requests':0},ensure_ascii=False))

if __name__=='__main__':
    main()
