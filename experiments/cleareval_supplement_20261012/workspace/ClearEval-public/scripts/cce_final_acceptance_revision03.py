"""Prospective revision03 evidence update, never a new scientific acceptance rule.

draft-check reads original public criteria/audits/code only. build is reserved for
root after all actual E2/E4/primary terminal analyses. No source-text re-opening.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT = BASE/'final_acceptance_update_v1'
CRITERIA = BASE/'validation_design_v1/acceptance_matrix.json'
PRIOR_A = BASE/'acceptance_evidence_audit_v1/revision02/audit.json'
PRIOR_R = BASE/'r2_completion_audit_v1/revision02/audit.json'
NEW_A = BASE/'acceptance_evidence_audit_v1/revision03'
NEW_R = BASE/'r2_completion_audit_v1/revision03'
CODE = [ROOT/'scripts'/n for n in ['cce_grounded_controls_v1.py', 'cce_analyze_grounded_stability_dev_v1.py', 'cce_grounded_confirmation_v3.py']]

STAGES = {
    'E2': {'summary': 'grounded_controls_v1/completion_summary.json',
           'verification': 'grounded_controls_v1/analysis_verification.json',
           'matrix': 'grounded_controls_v1/matrix.json', 'rows': 'grounded_controls_v1/per_answer.json',
           'pairs': 'grounded_controls_v1/paired_results.json', 'conditions': 'grounded_controls_v1/condition_summary.json'},
    'E4': {'summary': 'grounded_stability_dev_v1/analysis/completion_summary.json',
           'verification': 'grounded_stability_dev_v1/analysis/analysis_verification.json',
           'matrix': 'grounded_stability_dev_v1/matrix.json', 'rows': 'grounded_stability_dev_v1/analysis/observations.json',
           'within': 'grounded_stability_dev_v1/analysis/within.json', 'between': 'grounded_stability_dev_v1/analysis/between.json',
           'matched': 'grounded_stability_dev_v1/analysis/same_repeat_pairs.json',
           'reuse': 'grounded_stability_dev_v1/reuse_manifest.json'},
    'primary': {'summary': 'grounded_confirmation_v3/completion_summary.json',
           'verification': 'grounded_confirmation_v3/verification.json', 'matrix': 'grounded_confirmation_v3/matrix.json',
           'rows': 'grounded_confirmation_v3/observations.json', 'plan': 'grounded_confirmation_v3/plan.json',
           'ledger_snapshot': 'grounded_confirmation_v3/primary_ledger_at_completion.jsonl'}}


def require(ok, reason):
    if not ok: raise ValueError(reason)


def guard(path):
    path = Path(path).resolve(); s = str(path).lower().replace('\\', '/')
    require(not any(x in s for x in ['sealed_confirmation', 'confirmation_manifest', 'identity_key', 'identity_manifest',
        '/human_review/', '/source_documents/', '/prompts/', '/run/attempts/']), 'PROTECTED_OR_RAW_SOURCE_ACCESS_DENIED')
    require(path.name not in ['cases.json', 'blind_input_records.json'] and not re.fullmatch(r'C\d{2}\.json', path.name), 'SOURCE_TEXT_NOT_NEEDED')
    return path


def sha(path): return hashlib.sha256(guard(path).read_bytes()).hexdigest()
def bind(path): return {'path': str(guard(path)), 'sha256': sha(path)}
def read(path): return json.loads(guard(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')


def original_inputs():
    criteria, a, r = read(CRITERIA), read(PRIOR_A), read(PRIOR_R)
    require(criteria['check_count'] == len(criteria['checks']) == len(a['rows']) == 20, 'ORIGINAL_TWENTY_REQUIRED')
    require([x['original_clause'] for x in a['rows']] == criteria['checks'], 'CRITERIA_NOT_IDENTICAL')
    outcomes = {x['check_id']: x['outcome'] for x in a['rows']}
    require(outcomes['F02'] == outcomes['G01'] == 'fail' and outcomes['G02'] == 'unknown', 'HISTORICAL_LIMITATION_CHANGED')
    require(a['actual_development_requests'] == 40 and a['actual_expert_returns'] == 0, 'INHERITED_SCOPE_CHANGED')
    require(len(a['F02_mechanical_counterexamples']) == 2 and a['structured_relations_denominator'] == 5
            and a['fixed_relation_inventory_denominator'] == 3, 'ASSERTED_AND_FIXED_RELATION_DENOMINATORS_MUST_DIFFER')
    return criteria, a, r


def mapping(criteria):
    groups = {'T01': ['development'], 'T02': ['E2', 'E4', 'primary'], 'T03': ['E2', 'E4', 'primary'],
        'F01': ['development'], 'F02': ['development'], 'F03': ['development'], 'F04': ['development'],
        'P01': ['development'], 'P02': ['development', 'E2', 'E4', 'primary'], 'P03': ['E2', 'E4', 'primary'],
        'C01': ['E2'], 'C02': ['E2'], 'C03': ['E2'], 'C04': ['E2'], 'C05': ['E2'],
        'S01': ['E4'], 'S02': ['E4'], 'A01': ['primary'], 'G01': ['budget'], 'G02': ['access_boundary']}
    extra = {
        'development': ['grounded_development_v7/completion_summary.json', 'grounded_development_v7/independent_fact_audit_v7/summary.json',
            'grounded_v7_stage_report_v1/verification.json', 'grounded_v7_failure_diagnostics_v1/actual_source_findings_addendum.json',
            'grounded_v7_failure_diagnostics_v1/all_asserted_relations_source_audit_v1/summary.json'],
        'budget': ['grounded_v7_design_v1/budget_allocation_amendment.json', STAGES['primary']['ledger_snapshot']],
        'access_boundary': ['root_search_scope_audit_20261010.md']}
    rows = []
    for clause in criteria['checks']:
        cid = clause['check_id']; paths = []
        for g in groups[cid]: paths += list(STAGES[g].values()) if g in STAGES else extra[g]
        rows.append({'check_id': cid, 'original_clause': clause, 'source_groups': groups[cid],
            'public_source_paths': [str(BASE/p) for p in dict.fromkeys(paths)],
            'automatic_scientific_pass_allowed': False,
            'evidence_update_policy': 'Append actual terminal counts/NA and preserve original outcome until a separate criterion-specific review; no software-to-science promotion.'})
    return rows


def draft_check():
    criteria, prior, r2 = original_inputs(); rows = mapping(criteria)
    require([r['original_clause'] for r in rows] == criteria['checks'], 'CLAUSE_REWRITE')
    require(len({r['check_id'] for r in rows}) == 20, 'DUPLICATE_MAPPING')
    require(all(not r['automatic_scientific_pass_allowed'] for r in rows), 'AUTOMATIC_SCIENTIFIC_PASS')
    for path in [BASE/'validation_design_v1/sealed_confirmation/C01.json', ROOT/'artifacts/cce_validation/human_review/sealed/cases.json']:
        try: guard(path)
        except ValueError: pass
        else: require(False, 'PROTECTED_PATH_ACCEPTED')
    payload = {'status': 'draft_mapping_only_no_revision03_final_state', 'criteria': bind(CRITERIA),
        'prior_acceptance': bind(PRIOR_A), 'prior_r2': bind(PRIOR_R), 'rows': rows,
        'r2_requirements_verbatim': r2['requirement_matrix'],
        'prior_clause_outcomes': {r['check_id']: r['outcome'] for r in prior['rows']},
        'future_outputs': [str(NEW_A/'audit.json'), str(NEW_R/'audit.json')],
        'stage_source_schema': STAGES, 'fixed_phase_denominators': {'E2': [21, 15], 'E4': [30, 160, 80, 240], 'primary': [8, 16]},
        'counterexamples_must_survive': ['F02 two unsupported raw explicit relations even though projection rejected',
            'G01 development25 original versus40 actual prospectively amended', 'G02 access evidence is incomplete'],
        'unchanged_external_dependencies': {'expert_returns': 0, 'wetlab_observations': 0,
            'archived_answers_not_step_scored_in_full_cohort': 3211, 'fixed13_source_family_bootstrap_rows': 0},
        'scope_of_external_counts': 'Inherited prior-audit facts; no protected expert packet or wet-lab observation newly accessed.',
        'actual_command': [sys.executable, *sys.argv], 'script': bind(__file__), 'read_only_code_schema': [bind(p) for p in CODE],
        'checks': {'original20_exact': True, 'r2_original_terms_retained': True, 'F02_G01_G02_preserved': True,
            'protected_paths_rejected_without_access': True, 'no_final_status_written': True},
        'new_model_requests': 0, 'actual_confirmation_sources_read': False}
    save(OUT/'draft/mapping.json', payload)
    print(json.dumps({'status': 'draft_mapping_checks_pass', 'clauses': 20, 'final_revision03_written': False}))


def terminal_evidence():
    data = {}; bindings = []
    for name, paths in STAGES.items():
        require(all((BASE/p).is_file() for p in paths.values()), 'WAIT_FOR_ACTUAL_TERMINAL_OUTPUTS:'+name)
        data[name] = {k: read(BASE/p) for k, p in paths.items() if k != 'ledger_snapshot'}
        bindings += [bind(BASE/p) for p in paths.values()]
    e2, e4, primary = (data[k] for k in ['E2', 'E4', 'primary'])
    for name, n in [('E2', 21), ('E4', 30), ('primary', 16)]:
        stage = data[name]; rows = stage['rows']; matrix = stage['matrix']
        require(stage['verification']['status'] == 'pass' and len(rows) == len(matrix) == n, 'ACTUAL_TERMINAL_VERIFICATION:'+name)
        require(all(r['status'] in ['success', 'failed'] for r in rows), 'NONTERMINAL_CELL:'+name)
        require(len({r['trial_id'] for r in rows}) == n and {r['trial_id'] for r in rows} == {r['planned_trial_id'] for r in matrix}, 'MATRIX_IDENTITY:'+name)
    require(e2['summary']['status'] == 'experiment_complete' and e2['summary']['selected_backend_version'] == 'v7'
        and e2['summary']['actual_terminal_answers'] == 21 and len(e2['pairs']) == 15
        and e2['verification']['all_21_answers_and_15_pairs_retained'] is True
        and e2['summary']['all_pairs_same_contract'] is True, 'ACTUAL_E2_21_15_REQUIRED')
    require(e4['summary']['selected_backend'] == 'v7' and e4['summary']['actual_observations'] == 30
        and e4['summary']['exact_reused_observations'] == len(e4['reuse']) == 5
        and e4['summary']['planned_new_requests'] == 25
        and [len(e4[k]) for k in ['within', 'between', 'matched']] == [160, 80, 240]
        and e4['verification']['all_30_terminal_cells_retained'] is True, 'ACTUAL_E4_SCOPE_REQUIRED')
    ps = primary['summary']; plan = primary['plan']
    require(ps['actual_answers'] == 8 and ps['actual_terminal_observations'] == 16
        and primary['verification']['all_16_terminal_cells_retained'] is True
        and primary['verification']['all_8_answers_retained'] is True
        and plan['version'] == 'grounded_confirmation_v3' and plan['no_post_confirmation_tuning'] is True
        and plan['optional_blind_execution_allowed'] is False and plan['post_confirmation_blind_reactivation_allowed'] is False, 'ACTUAL_PRIMARY_SCOPE_REQUIRED')
    require(len(primary['verification']['terminal_cells']) == 16, 'LOCAL_FAILURE_CELLS_MUST_REMAIN')
    require(ps['common_n'] != 0 or (ps['common_means'] == {} and ps['common_answer_ids'] == []), 'EMPTY_COMMON_SET_IMPUTED')
    ledger_path = BASE/STAGES['primary']['ledger_snapshot']; ledger = [json.loads(line) for line in ledger_path.read_text(encoding='utf8').splitlines() if line.strip()]
    reservations = [r for r in ledger if r.get('event') == 'request_started']
    require(len(reservations) == len({r['request_id'] for r in reservations}) <= 300, 'GLOBAL_BUDGET_SNAPSHOT_INVALID')
    # Strip long bindings from summaries; the original metadata files stay bound above.
    summaries = {name: {k: v for k, v in d['summary'].items() if k not in ['bound_actual_artifacts', 'frozen_actual_files']} for name, d in data.items()}
    return {'stage_summaries': summaries, 'fixed_matrix_terminal_counts': {k: len(v['rows']) for k, v in data.items()},
        'E2_all_15_pair_statuses': [{k: v for k, v in p.items() if k in ['pair_id', 'condition', 'baseline_case_id', 'variant_case_id', 'both_arms_technical_complete', 'complete_numeric_pair', 'baseline_status', 'variant_status', 'response_observations']} for p in e2['pairs']],
        'primary_local_failed_without_receipt': sum(t['status'] == 'failed' and not t['actual_request_made'] and t['receipt'] is None for t in primary['verification']['terminal_cells']),
        'budget_reservation_count_at_primary_completion': len(reservations),
        'budget_reservation_count_is_not_automatically_actual_provider_invocation_count': True,
        'sources': bindings, 'independent_raw_scientific_reaudit_performed': False,
        'scope': 'Actual original terminal analysis metadata; original analyzers own full-source/HTTP/numeric replay. No new criterion-specific scientific adjudication.'}


def build():
    require(not (NEW_A/'audit.json').exists() and not (NEW_R/'audit.json').exists(), 'REVISION03_ALREADY_EXISTS')
    draft = read(OUT/'draft/mapping.json')
    for item in [draft['criteria'], draft['prior_acceptance'], draft['prior_r2'], *draft['read_only_code_schema']]:
        require(bind(item['path']) == item, 'DRAFT_BOUND_INPUT_CHANGED')
    criteria, a, r = original_inputs(); evidence = terminal_evidence(); now = datetime.now(timezone.utc).isoformat()
    prior_a = copy.deepcopy(a)
    a.update(status='completed_revision03_terminal_evidence_update_not_scientific_certification', created_utc=now,
        previous_audit=bind(PRIOR_A), revision='revision03_actual_followup_terminal_evidence',
        followup_metadata_at_audit=evidence, current_terminal_evidence=evidence,
        criterion_specific_outcomes_inherited_not_automatically_reclassified=True,
        candidate_overall_acceptance='not_established_F02_and_original_G01_fail', scientific_acceptance_established=False,
        ledger_snapshot_requests=evidence['budget_reservation_count_at_primary_completion'],
        actual_command=[sys.executable, *sys.argv], script=bind(__file__), new_model_calls=0,
        status_note='All three actual phases are terminal; full denominators/failures/NA updated. Prior criterion outcomes remain explicit until separately source-reviewed; software or execution completion does not establish scientific acceptance.')
    byid = {x['check_id']: x for x in draft['rows']}
    for row in a['rows']:
        row['revision02_assessment_retained_as_historical'] = True
        row['revision03_terminal_evidence_groups'] = byid[row['check_id']]['source_groups']
        row['revision03_new_evidence_available'] = any(x in STAGES for x in row['revision03_terminal_evidence_groups'])
        row['criterion_outcome_changed_by_this_metadata_update'] = False
    require([x['original_clause'] for x in a['rows']] == criteria['checks'], 'ORIGINAL_CRITERIA_CHANGED')
    require(a['F02_mechanical_counterexamples'] == prior_a['F02_mechanical_counterexamples'], 'COUNTEREXAMPLE_REMOVED')
    r['revision02_followup_snapshot'] = r['new_candidate_followup_status']
    r.update(status='completed_readonly_requirement_evidence_audit_revision03', created_utc=now,
        revision='revision03_actual_v7_followup_terminal_evidence', previous_audit=bind(PRIOR_R),
        actual_command=[sys.executable, *sys.argv], current_terminal_evidence=evidence,
        new_candidate_followup_status={'candidate': 'v7', 'E2': 'actual_all21_terminal_15_pairs_reported',
            'E4': 'actual_all30_terminal_exact5_reuse_160_80_240_reported', 'primary_confirmation': 'actual_all16_terminal_8_answers_reported',
            'optional_blind': 'prospectively_disabled_not_executed', 'scientific_acceptance_established': False},
        original_requirement_rows_unchanged=True, inherited_historical_evidence_recomputed=False,
        preserved_unresolved={'expert_returns': 0, 'wetlab_observations': 0, 'unscored_archived_answers': 3211,
            'fixed13_source_family_bootstrap_rows': 0, 'F02': 'original_raw_unsupported_relations_remain',
            'G01': 'original_development25_vs_actual40_deviation_remains', 'G02': 'access_visibility_limitation_remains'},
        overall='Actual follow-up execution and original analysis are complete with their observed failures and NA. Original scientific acceptance, expert/wet evidence, full-library step coverage and fixed13 source-family bootstrap remain unestablished or incomplete.')
    r['observed_optimizer_snapshot'] = {'source': 'actual_primary_completion_ledger_snapshot',
        'budget_reservation_count': evidence['budget_reservation_count_at_primary_completion'], 'current_process_liveness_claim': False}
    require(r['requirement_matrix'] == read(PRIOR_R)['requirement_matrix'], 'R2_ORIGINAL_TERMS_CHANGED')
    for item in evidence['sources']: require(bind(item['path']) == item, 'SOURCE_CHANGED_DURING_UPDATE')
    save(NEW_A/'audit.json', a); save(NEW_R/'audit.json', r)
    for target, name in [(NEW_A, '20 条验收'), (NEW_R, 'r2 完成性')]:
        text = f'# {name} revision03：真实终态证据更新\n\nE2 21 全文/15 对、E4 30 观察/160+80+240 指标格、主确认 8 答案/16 格均已实际终态，并通过原分析核验。实际成功、失败、完整数值、逐分项 NA 和共同集见 audit.json 的 current_terminal_evidence。\n\n原条款和既有评判保留，新增事实是各阶段真实执行与分析结束；本次不以元数据验证自动宣布事实标准通过。F02 原输出无支持关系、G01 原开发 25→40 偏离、G02 访问审计局限均未消除。专家 0、湿实验 0、全量 3211 未跑、固定 13 模型来源家族 bootstrap 0 继续单列。\n\n旧评判段落明确为 revision02 历史快照，不能把其中 pending 当作当前批次仍未执行；当前执行状态见顶层新证据。仍须按各条实际来源完成必要科学审阅，不把软件 green checks 当 science pass。\n\n本次没有读取封存答案、identity、confirmation_manifest 或专家留出，也未重做模型/向量/评分。全部当前源 SHA 与实际命令见 audit.json。\n'
        (target/'README.md').write_text(text, encoding='utf8')
    print(json.dumps({'status': 'revision03_terminal_evidence_written_no_scientific_reclassification', 'acceptance': bind(NEW_A/'audit.json'), 'r2': bind(NEW_R/'audit.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['draft-check', 'build']); args = parser.parse_args()
    draft_check() if args.action == 'draft-check' else build()
