"""Draft final manuscript delivery from explicitly allowlisted PUBLIC metadata only.

No model, encoder, numerical scoring, source text, trial, receipt, ledger, or
confirmation input is read. Original analyzers own full-source verification.
Rendering requires actual completed analyses and a separate root authorization.
"""
from __future__ import annotations
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation/optimizer_20261010'
OUT = BASE / 'manuscript_supplement_v7_final_v1'
SCRIPT = Path(__file__).resolve()
PUBLIC = {
    'dev': 'grounded_development_v7/completion_summary.json',
    'dev_verification': 'grounded_v7_stage_report_v1/verification.json',
    'facts': 'grounded_development_v7/independent_fact_audit_v7/summary.json',
    'relations': 'grounded_v7_failure_diagnostics_v1/all_asserted_relations_source_audit_v1/summary.json',
    'relations_verification': 'grounded_v7_failure_diagnostics_v1/all_asserted_relations_source_audit_v1/verification.json',
    'c05_mechanism': 'root_review_preparation_v1/C05_mechanism_addendum/evidence.json',
    'e2': 'grounded_controls_v1/completion_summary.json',
    'e2_verification': 'grounded_controls_v1/analysis_verification.json',
    'e4': 'grounded_stability_dev_v1/analysis/completion_summary.json',
    'e4_verification': 'grounded_stability_dev_v1/analysis/analysis_verification.json',
    'primary': 'grounded_confirmation_v3/completion_summary.json',
    'primary_verification': 'grounded_confirmation_v3/verification.json',
    'acceptance': 'acceptance_evidence_audit_v1/revision03/audit.json',
    'requirements': 'r2_completion_audit_v1/revision03/audit.json',
}
DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']
EGES = ['s_method', 's_label', 's_trans', 's_time']
DERIVED = ['Com', 'Cor', 'Eff', 'IA', 'HV']
METRICS = ['sr', 'sp', *DIRECT, *EGES, *DERIVED]
SOURCE_CODE = [ROOT/'scripts'/p for p in [
    'cce_report_grounded_confirmation_v3.py',
    'cce_analyze_grounded_stability_dev_v1.py',
    'cce_final_acceptance_revision03.py']]
AUTH = OUT/'root_render_authorization.json'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def public_path(key):
    require(key in PUBLIC, 'NOT_AN_ALLOWLISTED_PUBLIC_METADATA_KEY')
    path = BASE / PUBLIC[key]
    require(path.resolve() == path.absolute(), 'PUBLIC_PATH_REDIRECTION_NOT_ALLOWED')
    return path


def load_public(key):
    path = public_path(key)
    require(path.is_file(), 'ACTUAL_ANALYSIS_NOT_READY:'+key)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binding(path):
    return {'path': str(Path(path).resolve()), 'sha256': digest(path)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def count(value, maximum, key):
    require(type(value) is int and 0 <= value <= maximum, 'INVALID_COUNT:'+key)
    return value


def stage_row(name, summary, n, success, failure, complete, requests, reuse, definition):
    success = count(success, n, name+':success')
    failure = count(failure, n, name+':failure')
    require(success+failure == n, 'TERMINAL_COUNT_MISMATCH:'+name)
    complete = count(complete, success, name+':complete_numeric')
    return {'stage': name, 'observation_denominator': n, 'technical_successes': success,
        'technical_failures': failure, 'complete_numeric': complete,
        'complete_numeric_definition': definition, 'actual_new_requests': count(requests, n, name+':requests'),
        'exact_reused_observations': count(reuse, n, name+':reuse'),
        'evidence_unresolved': summary.get('evidence_unresolved')}


def validate(data):
    """Only validate descriptive metadata; never recompute biological scores."""
    for key in ['dev_verification', 'e2_verification', 'e4_verification', 'primary_verification']:
        require(data[key].get('status') == 'pass', 'ORIGINAL_VERIFICATION_REQUIRED:'+key)
    relation_check = data['relations_verification']
    relation_summary = data['relations']
    require(relation_check.get('status') == 'source_bindings_and_all_structured_claim_counts_verified'
        and relation_check.get('all_protected_files_unchanged') is True
        and relation_check.get('source_gate_result_reused_not_rerun') is True
        and relation_check.get('new_model_calls') == 0, 'EXACT_RELATION_SOURCE_VERIFICATION_REQUIRED')
    require(relation_summary.get('status') == 'complete_all_five_structured_relation_claims_source_audit'
        and relation_summary.get('answer_n') == 5
        and type(relation_check.get('relation_csv_rows')) is int
        and relation_check['relation_csv_rows'] == relation_summary['structured_relations']['total_claims']
        and type(relation_check.get('protected_files_unchanged')) is int
        and relation_check['protected_files_unchanged'] > 0
        and relation_check['protected_files_unchanged'] == relation_summary.get('original_protected_files_unchanged'),
        'RELATION_VERIFICATION_SCOPE_OR_COUNTS_MISMATCH')
    d, e, s, p = (data[x] for x in ['dev', 'e2', 'e4', 'primary'])
    require(d.get('status') == 'experiment_complete_not_scientific_validation'
        and d.get('actual_observations') == d.get('planned_observations') == 5, 'DEVELOPMENT_NOT_COMPLETE')
    require(e.get('status') == 'experiment_complete' and e.get('selected_backend_version') == 'v7'
        and e.get('actual_terminal_answers') == e.get('planned_answers') == 21
        and e.get('planned_pairs') == 15 and e.get('all_pairs_same_contract') is True
        and data['e2_verification'].get('all_21_answers_and_15_pairs_retained') is True, 'E2_NOT_COMPLETE')
    require(s.get('status') == 'complete_development_diagnostic_not_scientific_validation'
        and s.get('selected_backend') == 'v7' and s.get('actual_observations') == 30
        and s.get('unique_base_answers') == 5
        and data['e4_verification'].get('all_30_terminal_cells_retained') is True, 'E4_NOT_COMPLETE')
    require((s.get('within_groups'), s.get('between_groups'), s.get('same_repeat_pairs')) == (160, 80, 240), 'E4_GROUP_DENOMINATORS_CHANGED')
    for key in ['within_complete_three', 'within_partial', 'within_no_finite', 'within_range_evaluable', 'within_nonzero_range']:
        count(s[key], 160, key)
    require(s['within_complete_three']+s['within_partial']+s['within_no_finite'] == 160
        and s['within_nonzero_range'] <= s['within_range_evaluable'], 'E4_WITHIN_GROUP_COUNTS_INVALID')
    for key in ['between_both_complete_three', 'between_any_pair_evaluable', 'between_any_pair_different']:
        count(s[key], 80, key)
    require(s['between_any_pair_different'] <= s['between_any_pair_evaluable'], 'E4_BETWEEN_COUNTS_INVALID')
    count(s['finite_same_repeat_pairs'], 240, 'finite_same_repeat_pairs')
    count(s['different_same_repeat_pairs'], s['finite_same_repeat_pairs'], 'different_same_repeat_pairs')
    require(p.get('status') == 'experiment_complete_not_scientific_validation'
        and p.get('actual_answers') == 8 and p.get('actual_terminal_observations') == p.get('planned_observations') == 16
        and data['primary_verification'].get('all_16_terminal_cells_retained') is True
        and data['primary_verification'].get('all_8_answers_retained') is True
        and data['primary_verification'].get('attempt1_only') is True, 'PRIMARY_NOT_COMPLETE')
    count(p['common_n'], 8, 'common_n')
    require(p['common_n'] != 0 or p.get('common_means') == {}, 'EMPTY_COMMON_SET_HAS_MEANS')
    f = data['facts']
    require(f.get('status') == 'complete' and f.get('fixed_answers') == 5
        and (f.get('explicit_names_denominator'), f.get('core_duration_denominator'),
             f.get('explicit_relation_denominator'), f.get('ambiguity_group_denominator')) == (16, 31, 3, 2), 'FIXED_FACT_SCOPE_CHANGED')
    count(f['name_states'].get('exact', 0), 16, 'name_exact')
    count(f['record_bound_numeric_components_retained'], 31, 'initial_components')
    count(f['exact_relation_projections_retained'], 3, 'fixed_relation_projection')
    require(sum(f.get('ambiguity_states', {}).values()) == 2, 'AMBIGUITY_DENOMINATOR_LOST')
    relations = data['relations']['structured_relations']
    require(type(relations['total_claims']) is int and relations['total_claims'] >= 0, 'INVALID_ASSERTED_RELATION_COUNT')
    for key in ['source_gate_supported', 'explicit_unsupported_in_cited_evidence', 'source_support_unresolved']:
        count(relations[key], relations['total_claims'], key)
    require(relations['source_gate_supported']+relations['explicit_unsupported_in_cited_evidence']+
        relations['source_support_unresolved'] == relations['total_claims'], 'ASSERTED_RELATION_DENOMINATOR_LOST')
    require(data['acceptance'].get('revision') == 'revision03_actual_followup_terminal_evidence'
        and data['requirements'].get('revision') == 'revision03_actual_v7_followup_terminal_evidence', 'FINAL_METADATA_ACCEPTANCE_UPDATE_REQUIRED')
    outcomes = {r['check_id']: r['outcome'] for r in data['acceptance']['rows']}
    require(len(outcomes) == 20 and {k: outcomes.get(k) for k in ['F02', 'G01', 'G02']} ==
        {'F02': 'fail', 'G01': 'fail', 'G02': 'unknown'}, 'ORIGINAL_FAILURE_OR_ACCESS_LIMIT_RECLASSIFIED')
    require(data['acceptance'].get('scientific_acceptance_established') is False, 'UNREVIEWED_SCIENTIFIC_ACCEPTANCE_CLAIM')
    c05 = data['c05_mechanism']
    require(c05.get('status') == 'read_only_mechanism_evidence_complete'
        and c05.get('O_reference_available_in_actual_schema_and_prompt') is True
        and c05.get('eight_unique_O_options_verified') is True
        and len(c05.get('lost_finite_duration_operation_ids', [])) == 8
        and c05.get('new_calls') == c05.get('rescored_answers') == 0, 'ROOT_REVIEWED_C05_COUNTEREXAMPLE_MISSING')
    scope = data['requirements']['preserved_unresolved']
    require(scope.get('expert_returns') == 0 and scope.get('wetlab_observations') == 0, 'EXTERNAL_EVIDENCE_STATUS_CHANGED_REVIEW_REQUIRED')
    stages = [
        stage_row('development', d, 5, d['technical_successes'], d['technical_failures'], d['complete_numeric_after_component_gates'], d['new_requests'], 0, 'all five direct and four EGES components finite'),
        stage_row('E2', e, 21, e['technical_complete'], 21-e['technical_complete'], e['complete_numeric'], e['new_model_requests'], e['reused_model_trials'], 'original E2 complete_numeric flag: all 16 reported metrics finite'),
        stage_row('E4', s, 30, s['technical_successes'], s['technical_failures'], s['complete_numeric_16'], s['new_requests_this_batch'], s['exact_reused_observations'], 'all 16 reported metrics finite'),
        stage_row('primary', p, 16, p['technical_successes'], p['technical_failures'], p['complete_numeric_CCE'], p['actual_requests'], 0, 'Com, Cor, Eff, IA and HV all finite'),
    ]
    require(stages[2]['actual_new_requests'] <= s['planned_new_requests'] == 25
        and stages[2]['exact_reused_observations'] == 5, 'E4_REUSE_SCOPE_CHANGED')
    # Local pre-request failures are retained. Terminal observations need not equal provider calls.
    components = []
    for stage, n, values, expected in [
        ('development', 5, d['per_component_numeric'], DIRECT+EGES),
        ('E2', 21, e['per_component_numeric'], METRICS),
        ('E4', 30, s['per_component_numeric'], METRICS),
        ('primary', 16, p['per_metric_numeric'], METRICS)]:
        require(all(k in values for k in expected), 'COMPONENT_METADATA_MISSING:'+stage)
        for metric in expected:
            finite = count(values[metric], n, stage+':'+metric)
            category = 'direct_judge' if metric in DIRECT else 'computed_EGES' if metric in EGES else 'deterministic_steps' if metric in ['sr', 'sp'] else 'derived'
            components.append({'stage': stage, 'metric': metric, 'category': category,
                'finite': finite, 'NA': n-finite, 'denominator': n,
                'known_zero_is_finite_not_NA': True})
    # Cross-version or cross-stage observations are never pooled as independent answers.
    return {'stages': stages, 'components': components, 'criterion_outcomes': outcomes,
        'facts': {'names': [f['name_states'].get('exact', 0), 16],
            'initial_numeric_components': [f['record_bound_numeric_components_retained'], 31],
            'fixed_relation_projection': [f['exact_relation_projections_retained'], 3],
            'ambiguity_states': f['ambiguity_states'], 'all_asserted_relations': relations},
        'E2_pairs': {k: e[k] for k in ['planned_pairs', 'technical_complete_pairs', 'complete_numeric_pairs']},
        'E4_repetition': {k: s[k] for k in ['within_groups', 'within_complete_three', 'within_partial', 'within_no_finite',
            'within_range_evaluable', 'within_nonzero_range', 'between_groups', 'between_both_complete_three',
            'between_any_pair_evaluable', 'between_any_pair_different', 'same_repeat_pairs', 'finite_same_repeat_pairs',
            'different_same_repeat_pairs', 'direct_judge_stability_only']},
        'primary_common_n': p['common_n'], 'external_evidence': scope,
        'budget_reservations_snapshot': data['acceptance'].get('ledger_snapshot_requests'),
        'budget_reservations_are_not_automatically_actual_provider_calls': True,
        'root_reviewed_C05': {'assessment': 'fact_preservation_fail',
            'lost_finite_duration_bindings': len(c05['lost_finite_duration_operation_ids']),
            'available_unique_narrow_O_options_verified': c05['eight_unique_O_options_verified'],
            'scope': 'q21 lossless adjacent merge; source-reference selection and conservative multi-duration binding',
            'criterion_specific_root_review_separate_from_inherited_revision02_outcome': True},
        'historical_scope': 'The completed historical 192-request stage is context only and is not pooled with v7 observations.',
        'scoring_recomputed': False, 'new_model_requests': 0}


def table(rows, columns):
    return '\n'.join(['| '+' | '.join(columns)+' |', '| '+' | '.join(['---']*len(columns))+' |']+
        ['| '+' | '.join(str(r[k]).replace('|', '/') for k in columns)+' |' for r in rows])


def prose(result):
    """Templates render only after all gates, with no placeholder future counts."""
    rows = result['stages']; by = {r['stage']: r for r in rows}; f = result['facts']; e = result['E2_pairs']; s = result['E4_repetition']
    compact = [{k: r[k] for k in ['stage', 'observation_denominator', 'technical_successes', 'technical_failures', 'complete_numeric', 'actual_new_requests', 'exact_reused_observations']} for r in rows]
    t = table(compact, list(compact[0]))
    ctable = table(result['components'], ['stage', 'metric', 'category', 'finite', 'NA', 'denominator'])
    rel = f['all_asserted_relations']; common = result['primary_common_n']
    c05_n = result['root_reviewed_C05']['lost_finite_duration_bindings']
    between_difference_en = (f"{s['between_any_pair_different']}/{s['between_any_pair_evaluable']}" if s['between_any_pair_evaluable'] else 'NA (0 comparable groups)')
    between_difference_zh = (f"{s['between_any_pair_different']}/{s['between_any_pair_evaluable']}" if s['between_any_pair_evaluable'] else 'NA（0个可比较组）')
    repeat_difference_en = (f"{s['different_same_repeat_pairs']}/{s['finite_same_repeat_pairs']}" if s['finite_same_repeat_pairs'] else 'NA (0 comparable groups)')
    repeat_difference_zh = (f"{s['different_same_repeat_pairs']}/{s['finite_same_repeat_pairs']}" if s['finite_same_repeat_pairs'] else 'NA（0个可比较组）')
    direct_en = direct_zh = ''
    direct = s.get('direct_judge_stability_only')
    direct_fields = ('within_planned_groups', 'within_range_evaluable', 'within_nonzero_range',
        'between_planned_groups', 'between_any_pair_evaluable',
        'planned_same_repeat_metric_pairs', 'finite_same_repeat_metric_pairs')
    # Missing descriptive metadata is not a zero; omit this paragraph unless complete.
    if isinstance(direct, dict) and all(k in direct for k in direct_fields):
        direct_en = (f"For the five direct ratings, within-evaluator ranges were evaluable in "
            f"{direct['within_range_evaluable']}/{direct['within_planned_groups']} planned groups, "
            f"with {direct['within_nonzero_range']} nonzero ranges. Cross-evaluator comparison had "
            f"{direct['between_any_pair_evaluable']}/{direct['between_planned_groups']} comparable direct-rating groups "
            f"and {direct['finite_same_repeat_metric_pairs']}/{direct['planned_same_repeat_metric_pairs']} finite matched-repeat pairs. ")
        direct_zh = (f"五项直接评分的组内范围可计算组为 {direct['within_range_evaluable']}/{direct['within_planned_groups']}，"
            f"其中 {direct['within_nonzero_range']} 组范围非零；跨评价器直接评分可比较组为 "
            f"{direct['between_any_pair_evaluable']}/{direct['between_planned_groups']}，"
            f"同重复序号的有限指标对为 {direct['finite_same_repeat_metric_pairs']}/{direct['planned_same_repeat_metric_pairs']}。")
        if direct['between_any_pair_evaluable'] == 0:
            direct_en += 'Cross-evaluator agreement for direct ratings is NA (0 comparable groups), not evidence of agreement. '
            direct_zh += '直接评分的跨评价器一致性为 NA（0个可比较组），不能推断一致。'
        direct_en += 'Reused deterministic SR/SP values do not provide independent evidence of judge agreement.'
        direct_zh += '复用的确定性 SR/SP 不构成评价器一致性的独立证据。'
    boundary_en = ('This is a descriptive evaluation of the frozen evaluator configuration, not an expert accuracy estimate. '
        'The five development answers were repeatedly exposed during bundled revisions. E2 contains 21 text inputs and 15 pairs from three base answers; '
        'E4 contains two evaluators × five answers × three repeats, with five exact reused observations. '
        'The primary phase is within-exposed-task, answer-level automatic confirmation on eight previously reserved answers (16 evaluator cells), '
        'not task- or source-independent generalization. At most one request was permitted per cell. '
        'The historical 192-request stage is retained separately and is not pooled with these observations.')
    boundary_zh = ('这是冻结评价器的描述性评估，不是专家准确率估计。五份开发答案在多项联合修订中反复暴露。'
        'E2 为三个基线答案形成的 21 份文本、15 对；E4 为两评价器×五答案×三重复，含五条精确复用。'
        '主确认是已暴露任务范围内、八份事前保留答案的答案层自动确认（16 格），不是题目或来源独立泛化；每格至多一次请求。'
        '历史 192 次请求阶段单列，不与本轮观察合并。')
    en = f'''# Manuscript supplement: frozen v7 evaluator

{boundary_en}

The five original direct rubric components, EGES functions, and deterministic SR/SP definitions were retained. The v7 bundle displayed source-derived eligible duration/repetition IDs and clarified selection and coverage instructions. This comparison does not isolate a single intervention. The table separates terminal execution, technical validation, and complete numeric availability. NA is retained; a finite zero remains a value. Local failures before a provider request do not become completed model calls.

{t}

Complete numeric definitions differ by stage and are preserved explicitly in stage_summary.csv: development requires all nine direct/EGES components; E2/E4 require all 16 reported metrics; primary requires all five CCE quantities. They are not a common scientific success rate.

On the fixed development inventory, exact names were retained in {f['names'][0]}/{f['names'][1]}, source-bound initial numeric components in {f['initial_numeric_components'][0]}/{f['initial_numeric_components'][1]}, and specified relation projections in {f['fixed_relation_projection'][0]}/{f['fixed_relation_projection'][1]}. Ambiguity states are {json.dumps(f['ambiguity_states'], ensure_ascii=False)}. This limited recall inventory does not measure all-output precision: the separate audit found {rel['source_gate_supported']}/{rel['total_claims']} structured relation claims supported by their cited evidence and {rel['explicit_unsupported_in_cited_evidence']} unsupported claims. Withholding an unsupported projection does not make its raw assertion correct.

E2 retained all {e['planned_pairs']} planned pairs, including {e['technical_complete_pairs']} technically complete pairs and {e['complete_numeric_pairs']} complete-numeric pairs. Independently available deterministic step scores do not establish full-pipeline success. Threshold floors, segmentation denominators, and representation-sensitive scope classification remain relevant mechanisms; no new scoring is performed in this report.

E4 retained {s['within_groups']} within-evaluator metric groups: {s['within_complete_three']} with three finite repeats, {s['within_partial']} partially finite and {s['within_no_finite']} entirely NA. Of {s['within_range_evaluable']} groups with an evaluable range, {s['within_nonzero_range']} had nonzero range. Between evaluators, the count of groups differing in at least one evaluable matched repeat was {between_difference_en}; {s['between_both_complete_three']}/{s['between_groups']} had complete three-repeat means on both sides. Matched-repeat differences were {repeat_difference_en}, out of {s['same_repeat_pairs']} planned metric pairs. These correlated metric groups are not independent answers; direct ratings, derived values, and fixed deterministic step scores remain separated in the original analysis. Agreement does not establish fidelity or accuracy.

{direct_en}

Primary confirmation retained all 16 cells; {by['primary']['technical_successes']} were technically successful and {by['primary']['complete_numeric']} had complete CCE values. The common complete-numeric answer set contained {common}/8 answers. No missing values are imputed and no ranking is inferred from an empty common set.

Original acceptance outcomes remain F02=fail (unsupported raw relation assertions), G01=fail (the original development allowance was exceeded under a recorded amendment), and G02=unknown (access-boundary audit limitation). Execution completion does not erase these findings. Expert returns and wet-laboratory observations remain zero in the current requirement audit. Expert validation, wet-laboratory effectiveness, statistical significance, and full-library coverage are not claimed. Missing wet-laboratory observations do not block this completed computational report. Existing human-review selection and the one-expert 5+15 budget are not expanded or replaced.

A subsequent criterion-specific root review also established a C05 fact-preservation counterexample: lossless adjacent merging of the q21 text changed {c05_n} known finite duration bindings to NA. The sent prompt contained unique narrower operation-ID options for all affected durations, but the model selected broader unit references containing two durations, which the unchanged binder rejected. Thus an expressible narrow reference existed; the observed failure involved reference selection and binding granularity. This later C05 finding is retained separately from inherited revision02 outcomes, and intermediate counts of accepted criteria are not presented as a final acceptance tally.

## Component availability

{ctable}
'''
    zh = f'''# v7 评价器论文补充结果

{boundary_zh}

原五项直接量表、EGES 函数和确定性 SR/SP 定义保留。v7 联合改动包括展示来源导出的可用时长/重复 ID，以及选择和覆盖范围提示澄清；不能归为单因素效果。下表区分技术通过与完整数值。NA 保留，已知零仍是数值；模型请求前的本地失败不计为已经调用模型。

{t}

完整数值定义随阶段保留：开发为九项直接量表/EGES 全部有限，E2/E4 为 16 项全有限，主确认为五项 CCE 全部有限。详细定义在 stage_summary.csv；这些比例不能统一称科学成功率。

固定开发库存保留名称 {f['names'][0]}/{f['names'][1]}、来源绑定初始数值分量 {f['initial_numeric_components'][0]}/{f['initial_numeric_components'][1]}、指定关系投影 {f['fixed_relation_projection'][0]}/{f['fixed_relation_projection'][1]}。两处歧义分类原样为 {json.dumps(f['ambiguity_states'], ensure_ascii=False)}。固定事实召回不是全输出精确率：另一审计中全部 {rel['total_claims']} 条结构化关系有 {rel['source_gate_supported']} 条具所引来源支持、{rel['explicit_unsupported_in_cited_evidence']} 条无支持。拦下投影并不使原始无来源支持的主张成立。

E2 保留 {e['planned_pairs']} 个计划对，其中 {e['technical_complete_pairs']} 对两端技术通过，{e['complete_numeric_pairs']} 对两端完整数值。失败文本仍可能有独立 SR/SP；这不构成全文评价管线成对成功。二值阈值下的起始低值、步骤分母与表示引起的范围判断差异均须结合既有机制诊断解释，本报告不重新评分。

E4 共 {s['within_groups']} 个组内指标组：三次有限 {s['within_complete_three']}、部分有限 {s['within_partial']}、全 NA {s['within_no_finite']}；可计算范围的 {s['within_range_evaluable']} 组中 {s['within_nonzero_range']} 组非零。跨评价器至少一次配对有差异的组为 {between_difference_zh}（分母仅可比较组）；双方均有三次完整观测的均值比较为 {s['between_both_complete_three']}/{s['between_groups']} 组。按重复序号对齐的差异为 {repeat_difference_zh}，计划共 {s['same_repeat_pairs']} 个指标对。指标组相关且不是独立答案；直接评分、派生分与固定步骤分仍须分层，一致不等于忠实或正确。

{direct_zh}

主确认 16 格中技术通过 {by['primary']['technical_successes']}、完整 CCE {by['primary']['complete_numeric']}；双方共同完整答案集为 {common}/8。没有补零、择优重复或由空共同集推排名。

原验收 F02=fail（原输出含无支持关系）、G01=fail（原开发额度超出，后有独立记录的预算修订）、G02=unknown（访问边界审计局限）均保留。终态不等于有效性。当前要求审计中专家回传和湿实验观察均为 0；不宣称科学准确性、湿实验效果、统计显著性或全库覆盖。湿实验缺失不阻塞已完成的计算结果报告；原一位专家、5 开发＋15 留出的选择和预算没有扩充或被自动审计替代。

后续根代理逐条审阅另采纳 C05 事实保留失败：q21 无损相邻合并使 {c05_n} 个已知有限时长绑定变为 NA。实发提示中每个受影响时长均有唯一的较窄 O 操作引用，但模型实际选择含两个时长的宽 UnitRef，原绑定器据此拒绝。这是实际引用选择与保守绑定粒度的共同可观察环节，不是不存在可表达的较窄引用。该 C05 反例与继承的 revision02 状态分开保留，不把中期验收条目总数写成最终验收总数。

## 逐分项数值可用性

{ctable}
'''
    abstract_en = (f'We evaluated a source-bound evaluator for fixed-sample tissue-clearing protocol selection and generation while retaining the original direct rubric, EGES functions, and deterministic step metrics. '
        f'The frozen v7 evaluation included five repeatedly exposed development answers, 21 controlled texts forming 15 pairs, 30 repeated evaluator observations, and 16 automatic confirmation cells from eight reserved answers within exposed tasks. '
        f'Technical successes were {by["development"]["technical_successes"]}/5, {by["E2"]["technical_successes"]}/21, {by["E4"]["technical_successes"]}/30, and {by["primary"]["technical_successes"]}/16, respectively; complete numeric availability remained separately assessed. '
        f'The fixed development inventory retained {f["names"][0]}/16 names, {f["initial_numeric_components"][0]}/31 initial numeric components, and {f["fixed_relation_projection"][0]}/3 specified relations, while a broader structured-relation audit identified {rel["explicit_unsupported_in_cited_evidence"]} unsupported claims. '
        f'{direct_en + " " if direct_en else ""}'
        f'Primary common complete-numeric coverage was {common}/8 answers. These descriptive, bundled-development results preserve failures and NA; they establish neither expert accuracy nor independent-task generalization. No expert or wet-laboratory validation is claimed.')
    abstract_zh = (f'本研究评估用于固定组织透明方案选择与生成的来源绑定评价器，保留原直接量表、EGES 和确定性步骤指标。'
        f'冻结 v7 覆盖五份反复暴露开发答案、形成 15 对的 21 份受控文本、30 次重复评价，以及已暴露任务内八份事前保留答案的 16 格自动确认。'
        f'各阶段技术通过分别为 {by["development"]["technical_successes"]}/5、{by["E2"]["technical_successes"]}/21、{by["E4"]["technical_successes"]}/30 和 {by["primary"]["technical_successes"]}/16，完整数值另列。'
        f'固定库存保留名称 {f["names"][0]}/16、初始数值 {f["initial_numeric_components"][0]}/31、指定关系 {f["fixed_relation_projection"][0]}/3；更广的结构化关系审计仍发现 {rel["explicit_unsupported_in_cited_evidence"]} 条无支持主张。'
        f'{direct_zh}'
        f'主确认共同完整答案集为 {common}/8。结果属于联合开发改动的描述性观察，保留失败与 NA，不证明专家准确性、独立任务泛化或湿实验效果。')
    return {'RESULTS_zh.md': zh, 'Methods_Results_en.md': en,
        'Abstract_zh.md': abstract_zh+'\n', 'Abstract_en.md': abstract_en+'\n'}


def synthetic():
    """Invented metadata only; no source answers or future estimates."""
    zero = {m: 0 for m in METRICS}
    data = {k: {} for k in PUBLIC}
    for key in ['dev_verification', 'e2_verification', 'e4_verification', 'primary_verification']:
        data[key] = {'status': 'pass'}
    data['relations_verification'] = {'status': 'source_bindings_and_all_structured_claim_counts_verified',
        'all_protected_files_unchanged': True, 'source_gate_result_reused_not_rerun': True,
        'new_model_calls': 0, 'relation_csv_rows': 0, 'protected_files_unchanged': 1}
    data['dev'] = dict(status='experiment_complete_not_scientific_validation', actual_observations=5, planned_observations=5,
        technical_successes=2, technical_failures=3, complete_numeric_after_component_gates=0, new_requests=5, per_component_numeric=zero)
    data['e2'] = dict(status='experiment_complete', selected_backend_version='v7', actual_terminal_answers=21, planned_answers=21,
        planned_pairs=15, all_pairs_same_contract=True, technical_complete=2, complete_numeric=0, new_model_requests=21,
        reused_model_trials=0, per_component_numeric=zero, technical_complete_pairs=1, complete_numeric_pairs=0)
    data['e2_verification']['all_21_answers_and_15_pairs_retained'] = True
    data['e4'] = dict(status='complete_development_diagnostic_not_scientific_validation', selected_backend='v7', actual_observations=30,
        unique_base_answers=5, technical_successes=2, technical_failures=28, complete_numeric_16=0, new_requests_this_batch=25,
        planned_new_requests=25, exact_reused_observations=5, per_component_numeric=zero, within_groups=160, within_complete_three=0,
        within_partial=0, within_no_finite=160, within_range_evaluable=0, within_nonzero_range=0, between_groups=80,
        between_both_complete_three=0, between_any_pair_evaluable=0, between_any_pair_different=0, same_repeat_pairs=240,
        finite_same_repeat_pairs=0, different_same_repeat_pairs=0, direct_judge_stability_only={})
    data['e4_verification']['all_30_terminal_cells_retained'] = True
    data['primary'] = dict(status='experiment_complete_not_scientific_validation', actual_answers=8, actual_terminal_observations=16,
        planned_observations=16, technical_successes=2, technical_failures=14, complete_numeric_CCE=0, actual_requests=15,
        per_metric_numeric=zero, common_n=0, common_means={})
    data['primary_verification'].update(all_16_terminal_cells_retained=True, all_8_answers_retained=True, attempt1_only=True)
    data['facts'] = dict(status='complete', fixed_answers=5, explicit_names_denominator=16, core_duration_denominator=31,
        explicit_relation_denominator=3, ambiguity_group_denominator=2, name_states={'exact': 0},
        record_bound_numeric_components_retained=0, exact_relation_projections_retained=0, ambiguity_states={'unavailable': 2})
    data['relations'] = {'status': 'complete_all_five_structured_relation_claims_source_audit', 'answer_n': 5,
        'original_protected_files_unchanged': 1,
        'structured_relations': {'total_claims': 0, 'source_gate_supported': 0,
        'explicit_unsupported_in_cited_evidence': 0, 'source_support_unresolved': 0}}
    data['c05_mechanism'] = {'status': 'read_only_mechanism_evidence_complete',
        'O_reference_available_in_actual_schema_and_prompt': True, 'eight_unique_O_options_verified': True,
        'lost_finite_duration_operation_ids': [f'SYNTH_{i}' for i in range(8)], 'new_calls': 0, 'rescored_answers': 0}
    data['acceptance'] = {'revision': 'revision03_actual_followup_terminal_evidence', 'scientific_acceptance_established': False,
        'rows': [{'check_id': k, 'outcome': v} for k, v in [('F02', 'fail'), ('G01', 'fail'), ('G02', 'unknown')]+[(f'X{i}', 'pending') for i in range(17)]]}
    data['requirements'] = {'revision': 'revision03_actual_v7_followup_terminal_evidence',
        'preserved_unresolved': {'expert_returns': 0, 'wetlab_observations': 0}}
    return data


def draft_check():
    data = synthetic(); result = validate(data); rendered = prose(result)
    checks = []
    def reject(name, mutation):
        changed = copy.deepcopy(data); mutation(changed)
        try: validate(changed)
        except (ValueError, KeyError): checks.append({'id': name, 'passed': True, 'expected': 'reject'})
        else: raise ValueError('SYNTHETIC_BAD_METADATA_ACCEPTED:'+name)
    reject('unfinished_E2', lambda x: x['e2'].update(actual_terminal_answers=20))
    reject('unfinished_E4', lambda x: x['e4'].update(actual_observations=29))
    reject('unfinished_primary', lambda x: x['primary'].update(actual_terminal_observations=15))
    reject('failed_original_verification', lambda x: x['e4_verification'].update(status='fail'))
    reject('F02_erased', lambda x: x['acceptance']['rows'][0].update(outcome='pass'))
    reject('G01_erased', lambda x: x['acceptance']['rows'][1].update(outcome='pass'))
    reject('G02_erased', lambda x: x['acceptance']['rows'][2].update(outcome='pass'))
    reject('empty_common_set_means', lambda x: x['primary'].update(common_means={'invented': 1}))
    reject('negative_finite_count', lambda x: x['primary'].update(per_metric_numeric={**x['primary']['per_metric_numeric'], 'sr': -1}))
    reject('complete_over_success', lambda x: x['dev'].update(complete_numeric_after_component_gates=3))
    reject('fact_denominator_changed', lambda x: x['facts'].update(core_duration_denominator=30))
    reject('within_NA_groups_disappear', lambda x: x['e4'].update(within_no_finite=0))
    reject('between_difference_over_denominator', lambda x: x['e4'].update(between_any_pair_different=1))
    reject('later_C05_counterexample_erased', lambda x: x['c05_mechanism'].update(lost_finite_duration_operation_ids=[]))
    require(result['stages'][3]['actual_new_requests'] == 15, 'LOCAL_FAILURE_MISTAKEN_AS_MODEL_REQUEST')
    checks.append({'id': 'local_failure_retained_no_request', 'passed': True})
    require(result['components'][0]['finite'] == 0 and result['components'][0]['NA'] == 5, 'NA_IMPUTED')
    checks.append({'id': 'NA_retained', 'passed': True})
    # A known zero contributes one finite value; summary metadata never changes its score.
    known_zero = copy.deepcopy(data); known_zero['dev']['per_component_numeric']['c_param'] = 1
    require(validate(known_zero)['components'][0]['finite'] == 1, 'KNOWN_ZERO_LOST')
    checks.append({'id': 'known_zero_counts_as_finite', 'passed': True})
    for forbidden in ['cases', 'raw', 'sealed_confirmation', 'C01.json', 'expert', 'prompt', 'ledger']:
        try: public_path(forbidden)
        except ValueError: checks.append({'id': 'read_denied_'+forbidden, 'passed': True})
        else: raise ValueError('ALLOWLIST_BYPASS')
    require(len(rendered) == 4 and len(result['components']) == 57, 'TEMPLATE_OR_COMPONENT_GRID_INCOMPLETE')
    checks.append({'id': 'four_templates_and_57_component_rows_synthetic_only', 'passed': True})
    # Do not read real future summaries, confirmation rows, or draft source bindings.
    contract = {'status': 'draft_metadata_contract_not_a_result', 'public_input_allowlist': PUBLIC,
        'allowed_future_command': [str(SCRIPT), 'render'], 'root_authorization_path': str(AUTH),
        'required_authorization_fields': {'authorized_by': 'root_agent', 'allow_render': True,
            'script_sha256': 'must equal actual script SHA', 'input_sha256': 'exact key-to-SHA map for every PUBLIC input'},
        'later_root_C05_fact_preservation_failure_retained': True,
        'outputs': ['RESULTS_zh.md', 'Methods_Results_en.md', 'Abstract_zh.md', 'Abstract_en.md', 'INDEX.md',
            'stage_summary.csv', 'component_availability.csv', 'report_facts.json', 'render_manifest.json'],
        'not_read': ['confirmation answer files/identities/manifests', 'raw/model fields/trials/receipts',
            'cases/source/prompt', 'human review/expert content', 'ledger'],
        'no_recursive_binding_follow': True, 'historical_192_not_pooled': True,
        'new_model_requests': 0, 'actual_results_rendered': False}
    save(OUT/'draft/metadata_contract.json', contract)
    save(OUT/'draft/software_probes.json', {'status': 'pass_synthetic_metadata_only', 'checks': checks,
        'check_count': len(checks), 'actual_command': [sys.executable, *sys.argv], 'script': binding(SCRIPT),
        'read_only_interface_code': [binding(p) for p in SOURCE_CODE], 'real_stage_summaries_read': False,
        'real_confirmation_inputs_read': False, 'new_model_requests': 0, 'actual_results_rendered': False})
    print(json.dumps({'status': 'draft_ready_synthetic_checks_pass', 'checks': len(checks),
        'actual_results_rendered': False, 'new_model_requests': 0, 'script_sha256': digest(SCRIPT)}))


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def render():
    require(AUTH.is_file(), 'ROOT_RENDER_AUTHORIZATION_REQUIRED')
    require(AUTH.resolve() == AUTH.absolute(), 'AUTH_PATH_REDIRECTION')
    auth = json.loads(AUTH.read_text(encoding='utf-8-sig'))
    require(auth.get('authorized_by') == 'root_agent' and auth.get('allow_render') is True
        and auth.get('script_sha256') == digest(SCRIPT), 'ROOT_RENDER_AUTHORIZATION_INVALID')
    require(set(auth.get('input_sha256', {})) == set(PUBLIC), 'ALL_PUBLIC_INPUT_HASHES_REQUIRED')
    require(not (OUT/'actual').exists(), 'ACTUAL_DELIVERY_ALREADY_EXISTS_NO_OVERWRITE')
    data = {}; inputs = {}
    for key in PUBLIC:
        path = public_path(key)
        require(path.is_file() and digest(path) == auth['input_sha256'][key], 'AUTHORIZED_METADATA_CHANGED:'+key)
        data[key] = load_public(key); inputs[key] = binding(path)
    # The final acceptance updater must bind these exact public originals. Its
    # other source descriptors are not opened, hashed, or decoded here.
    declared = {str(x['path']).replace('\\', '/').lower(): x['sha256']
        for x in data['acceptance']['current_terminal_evidence']['sources']}
    for key in ['e2', 'e2_verification', 'e4', 'e4_verification', 'primary', 'primary_verification']:
        require(declared.get(inputs[key]['path'].replace('\\', '/').lower()) == inputs[key]['sha256'],
            'ACCEPTANCE_DOES_NOT_BIND_CURRENT_PUBLIC_METADATA:'+key)
    result = validate(data); docs = prose(result)
    # Recheck only the exact allowlist. No nested raw/input/receipt binding is opened.
    require(all(digest(public_path(k)) == v['sha256'] for k, v in inputs.items()), 'METADATA_CHANGED_DURING_RENDER')
    target = OUT/'actual'; target.mkdir(parents=True)
    for name, text in docs.items(): (target/name).write_text(text, encoding='utf8')
    write_csv(target/'stage_summary.csv', result['stages'])
    write_csv(target/'component_availability.csv', result['components'])
    save(target/'report_facts.json', result)
    links = ['# ClearEval v7 manuscript supplement / 论文补充入口', '',
        '公开结果元数据汇总；原分析负责源数据、请求身份和原算式核验。本交付不重新读取答案、不重新评分。', '',
        'Public-result metadata synthesis. Original analyzers own source/identity/formula verification; this delivery performs no new scoring.', '']
    for name in docs: links.append(f'- [{name}]({name})')
    for name in ['stage_summary.csv', 'component_availability.csv', 'report_facts.json']:
        links.append(f'- [{name}]({name})')
    links += ['', '## Original public evidence / 原公开证据', '']
    for key in PUBLIC: links.append(f'- [{key}]({public_path(key).as_posix()})')
    links += ['', 'Terminal execution is not scientific acceptance. F02/G01 failures, the later root-reviewed C05 failure, and G02 unknown remain; expert and wet-laboratory evidence are not fabricated.',
        '终态不等于科学验收；F02/G01 失败、后续根审 C05 失败与 G02 未知保留。没有新增专家标签、湿实验数据或模型调用。', '']
    (target/'INDEX.md').write_text('\n'.join(links), encoding='utf8')
    manifest = {'status': 'metadata_only_manuscript_delivery_rendered', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'script': binding(SCRIPT), 'authorization': binding(AUTH), 'inputs': inputs,
        'outputs': [binding(p) for p in sorted(target.iterdir()) if p.is_file()],
        'actual_command': [sys.executable, *sys.argv], 'all_original_stage_verifications_pass': True,
        'source_text_or_scientific_outputs_read': False, 'recursive_binding_follow': False,
        'scientific_acceptance_established': False, 'new_model_requests': 0,
        'new_scoring_or_embeddings': 0, 'component_rows': len(result['components'])}
    save(target/'render_manifest.json', manifest)
    print(json.dumps({'status': manifest['status'], 'index': str(target/'INDEX.md'), 'new_model_requests': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['draft-check', 'render'])
    args = parser.parse_args()
    draft_check() if args.action == 'draft-check' else render()
