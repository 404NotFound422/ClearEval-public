"""Read-only primary confirmation report. Draft checks never access real answers.

Render consumes the original completed analysis, not source text or a new judge.
No release, scoring, threshold selection, imputation, or inferential statistic.
"""
from __future__ import annotations
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT)]
import cce_grounded_offline_scoring_v1 as numeric

BASE = ROOT/'artifacts/cce_validation/optimizer_20261010'
SOURCE = BASE/'grounded_confirmation_v3'
OUT = BASE/'grounded_confirmation_v3_report_v1'
PRIMARY = ROOT/'scripts/cce_grounded_confirmation_v3.py'
MODULE = ROOT/'scripts/cce_grounded_extraction_v7.py'
BACKEND = ROOT/'scripts/cce_grounded_development_v7.py'
SCHEMA = BASE/'grounded_extraction_v7/schema.json'
STYLE = ROOT/'scripts/cce_plot_step_threshold_diagnostic_v1.py'
DOCS = [BASE/'grounded_v7_design_v1/primary_analysis_readonly_v1/README.md',
        BASE/'grounded_v7_design_v1/primary_analysis_supplement_v1/README.md']
IDS = [f'C{i:02d}' for i in range(1, 9)]
CATEGORIES = {'direct_judge': numeric.DIRECT, 'computed_EGES': numeric.EGES,
              'deterministic_steps': ['sr', 'sp'], 'derived': ['Com', 'Cor', 'Eff', 'IA', 'HV']}
METRICS = numeric.METRICS
PLOT_METRICS = ['Com', 'Cor', 'Eff', 'HV']
DEPENDENCIES = {'Com': ['sr', 'c_param'], 'Cor': ['co_order', 'co_method', 'co_param', 'co_chem'],
                'Eff': numeric.EGES, 'IA': ['Com', 'Cor', 'Eff'], 'HV': ['Com', 'Cor', 'Eff']}
COLORS = ['#0072B2', '#D55E00']


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def safe_path(path):
    """Never follow source-text/identity descriptors, including during rendering."""
    path = Path(path).resolve(); text = str(path).lower().replace('\\', '/')
    require(not any(s in text for s in ['sealed_confirmation', 'identity_key', 'identity_manifest',
        'confirmation_manifest', '/human_review/', '/source_documents/', '/prompts/']), 'PROTECTED_SOURCE_PATH')
    require(path.name not in ['cases.json', 'blind_input_records.json', 'prepared_inputs.json']
            and not re.fullmatch(r'C\d{2}\.json', path.name), 'SOURCE_TEXT_FILE_NOT_NEEDED_FOR_REPORT')
    return path


def read(path):
    return json.loads(safe_path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def bind(path):
    return {'path': str(safe_path(path)), 'sha256': sha(path)}


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def csv_rows(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()} for row in rows)


def verify(item, tracked):
    path = safe_path(item['path'])
    require(sha(path) == item['sha256'], 'SOURCE_BINDING_DRIFT:'+str(path))
    tracked[str(path)] = item['sha256']; return path


def original_summary(rows, judges):
    """Same descriptive aggregates as original analyze; no new estimand."""
    require(len(rows) == 16 and len(judges) == len(set(judges)) == 2, 'FIXED_SIXTEEN_GRID')
    require({(r['anonymous_answer_id'], r['judge']) for r in rows} == {(a, j) for a in IDS for j in judges}, 'MISSING_OR_DUPLICATE_CELL')
    for row in rows:
        values = row['metrics']
        require(set(values) == set(METRICS), 'SIXTEEN_METRICS_REQUIRED')
        require(all(x is None or numeric.finite(x) for x in values.values()), 'NA_OR_FINITE_ONLY')
        require(row['status'] in ['success', 'failed'], 'ALL_CELLS_MUST_BE_TERMINAL')
        require(row['judge_attempt_failed'] == (row['status'] == 'failed'), 'FAILURE_FLAG_CHANGED')
        complete = all(numeric.finite(values[k]) for k in ['Com', 'Cor', 'Eff', 'IA', 'HV'])
        require(row['complete_numeric_CCE'] == complete, 'COMPLETE_CCE_FLAG_CHANGED')
        if row['status'] == 'failed':
            require(all(values[k] is None for k in METRICS if k not in ['sr', 'sp']), 'FAILED_JUDGE_VALUE_MUST_BE_NA')
        require(all(numeric.same(values[k], v) for k, v in numeric.derive(values, values, row['status'] == 'success').items()), 'ORIGINAL_DERIVED_FORMULA_MISMATCH')
    common = [a for a in IDS if all(any(r['anonymous_answer_id'] == a and r['judge'] == j and r['complete_numeric_CCE'] for r in rows) for j in judges)]
    means = {j: {m: sum(r['metrics'][m] for r in rows if r['judge'] == j and r['anonymous_answer_id'] in common)/len(common)
                 for m in ['Com', 'Cor', 'Eff', 'IA', 'HV']} for j in judges} if common else {}
    qids = {a: {r['question_id'] for r in rows if r['anonymous_answer_id'] == a} for a in IDS}
    require(all(len(v) == 1 for v in qids.values()), 'QUESTION_ID_DIFFERS_BETWEEN_JUDGES')
    return {'actual_answers': 8, 'actual_terminal_observations': 16, 'planned_observations': 16,
        'actual_requests': sum(r['actual_request_made'] for r in rows),
        'technical_successes': sum(r['status'] == 'success' for r in rows),
        'technical_failures': sum(r['status'] == 'failed' for r in rows),
        'complete_numeric_CCE': sum(r['complete_numeric_CCE'] for r in rows),
        'per_metric_numeric': {m: sum(numeric.finite(r['metrics'][m]) for r in rows) for m in METRICS},
        'all_observation_denominators': 16, 'answer_observation_units': 8, 'metrics_are_not_independent_samples': True,
        'common_answer_ids': common, 'common_n': len(common), 'common_means': means,
        'common_question_id_counts': {str(q): sum(q in qids[a] for a in common) for q in sorted({next(iter(qids[a])) for a in common})}}


def check_summary(rows, judges, summary):
    actual = original_summary(rows, judges)
    for key, value in actual.items():
        require(summary.get(key) == value, 'ORIGINAL_SUMMARY_DIFFERS:'+key)
    return actual


def load_actual(source=SOURCE):
    """Original analyzer already verified full raw/source replay. Do not reopen it."""
    source = Path(source)
    names = ['plan', 'matrix', 'expected_contract', 'observations', 'completion_summary', 'verification',
             'deterministic_steps', 'step_verification']
    required = [source/(n+'.json') for n in names]
    require(all(p.is_file() for p in required), 'ACTUAL_PRIMARY_TERMINAL_ANALYSIS_NOT_READY')
    data = {n: read(source/(n+'.json')) for n in names}; tracked = {}
    for path in required: verify(bind(path), tracked)
    plan, checked, summary = data['plan'], data['verification'], data['completion_summary']
    require(plan.get('version') == 'grounded_confirmation_v3' and plan.get('status') == 'frozen_before_primary_unsealing', 'FROZEN_PRIMARY_V3_REQUIRED')
    require([plan.get(k) for k in ['planned_answers', 'planned_observations', 'max_attempts', 'repeats']] == [8, 16, 1, 1], 'FROZEN_SCOPE_CHANGED')
    require(checked.get('status') == 'pass' and checked.get('all_16_terminal_cells_retained') is True
            and checked.get('all_8_answers_retained') is True and checked.get('attempt1_only') is True, 'ORIGINAL_ANALYSIS_VERIFICATION_REQUIRED')
    require(summary.get('status') == 'experiment_complete_not_scientific_validation', 'ORIGINAL_TERMINAL_SUMMARY_REQUIRED')
    require(plan.get('no_post_confirmation_tuning') is True and plan.get('optional_blind_execution_allowed') is False
            and plan.get('post_confirmation_blind_reactivation_allowed') is False, 'FINAL_CONFIGURATION_POLICY_CHANGED')
    release = read(verify(plan['final_release'], tracked))
    require(release.get('status') == 'released_for_primary_confirmation' and release.get('selected_by') == 'root_agent'
            and release.get('configuration_frozen_before_confirmation') is True and release.get('no_post_confirmation_tuning') is True, 'ROOT_FINAL_RELEASE_REQUIRED')
    # Metadata assets only. Never follow expected_sealed_inputs / confirmation_inputs.
    for item in plan['frozen_inputs']: verify(item, tracked)
    assets = release['assets']
    for item in assets.values(): verify(item, tracked)
    prototype = read(OUT/'draft/prototype.json')
    for key, expected in prototype['expected_backend_assets'].items():
        verify(expected, tracked)
        require(assets.get(key) == expected, 'FROZEN_V7_BACKEND_DIFFERS:'+key)
    require(any(item == bind(PRIMARY) for item in plan['frozen_inputs']), 'ORIGINAL_ANALYZER_CODE_NOT_BOUND')
    final = read(verify(plan['final_configuration'], tracked))
    require(plan['final_configuration'] == assets['final_configuration'] and final.get('status') == 'frozen_before_confirmation'
            and final.get('num_ctx') == 98304 and final.get('optional_blind_execution_allowed') is False
            and final.get('post_confirmation_blind_reactivation_allowed') is False, 'FINAL_V7_CONFIGURATION_DIFFERS')
    for item in final['bindings']: verify(item, tracked)
    judges = [m['name'] for m in read(assets['model_contract']['path'])['models']]
    require(set(final['verified_model_families']) == set(judges) and len(set(final['verified_model_families'].values())) == 2, 'TWO_VERIFIED_JUDGE_FAMILIES_REQUIRED')
    matrix = data['matrix']; rows = data['observations']; terminals = checked['terminal_cells']
    require(len(matrix) == len(rows) == len(terminals) == 16, 'FIXED_SIXTEEN_TERMINALS')
    require(len({r['trial_id'] for r in rows}) == 16
            and {r['trial_id'] for r in rows} == {r['planned_trial_id'] for r in matrix} == {r['trial_id'] for r in terminals}, 'TERMINAL_MATRIX_IDENTITIES_DIFFER')
    bound_analysis = {str(safe_path(x['path'])): x['sha256'] for x in checked['bindings']}
    for name in ['plan', 'matrix', 'deterministic_steps', 'step_verification', 'observations', 'completion_summary']:
        path = source/(name+'.json'); require(bound_analysis.get(str(path.resolve())) == sha(path), 'ANALYSIS_OUTPUT_NOT_BOUND:'+name)
    bycell = {x['planned_trial_id']: x for x in matrix}; byterminal = {x['trial_id']: x for x in terminals}
    steps = {x['anonymous_answer_id']: x for x in data['deterministic_steps']}
    require(len(data['deterministic_steps']) == len(steps) == 8 and set(steps) == set(IDS), 'EIGHT_STEP_EXPORTS_REQUIRED')
    sv = data['step_verification']
    require(sv.get('status') == 'pass' and sv.get('original_SR_SP') is True and sv.get('primary_threshold') == .7
            and sv.get('encoder') == 'all-mpnet-base-v2' and sv.get('fixed_answer_denominator') == 8, 'ORIGINAL_STEP_CONFIGURATION_REQUIRED')
    # cases.json binding is intentionally left to the original analyzer; no source re-open.
    for item in sv['bindings']:
        if Path(item['path']).name != 'cases.json': verify(item, tracked)
    replays = {}
    for row in rows:
        tid = row['trial_id']; cell = bycell[tid]; term = byterminal[tid]
        require((cell['anonymous_answer_id'], cell['judge'], cell['attempt'], cell['repeat_index']) ==
                (row['anonymous_answer_id'], row['judge'], 1, 0), 'ROW_IDENTITY_DIFFERS')
        require(term['attempt'] == 1 and term['status'] == row['status'] and term['actual_request_made'] == row['actual_request_made'], 'TERMINAL_PROVENANCE_DIFFERS')
        verify(term['trial'], tracked)  # Hash original terminal; never decode its source-bound content.
        require(bound_analysis.get(str(safe_path(term['trial']['path']))) == term['trial']['sha256'], 'TRIAL_NOT_BOUND_BY_ANALYSIS')
        if row['actual_request_made']:
            require(term['receipt'] is not None, 'ACTUAL_REQUEST_RECEIPT_REQUIRED'); rp = verify(term['receipt'], tracked)
            receipt = read(rp); require(receipt['trial_id'] == tid and receipt['attempt'] == 1, 'RECEIPT_IDENTITY_DIFFERS')
        else:
            require(row['status'] == 'failed' and term['receipt'] is None and bool(term['local_failure_reason']), 'LOCAL_FAILURE_REASON_REQUIRED')
        if term['budget_reservation'] is not None: verify(term['budget_reservation'], tracked)
        require(row['step_source'] == 'deterministic_step_reuse' and all(numeric.same(row['metrics'][k], steps[row['anonymous_answer_id']][k]) for k in ['sr', 'sp']), 'STEP_REUSE_VALUES_DIFFER')
        if row['status'] == 'success':
            path = source/'numeric_replays'/f'{tid}.json'; replay = read(path); verify(bind(path), tracked)
            require(replay['status'] == 'original_formula_replayed_not_scientific_validation'
                    and replay['metrics'] == row['metrics'] and replay['evidence_state'] == row['evidence_state'], 'ORIGINAL_NUMERIC_REPLAY_DIFFERS')
            require(replay['source_binding']['enumerator_version'] == 'source_bound_extraction_v7', 'NUMERIC_REPLAY_BACKEND_NOT_V7')
            replays[tid] = replay
    check_summary(rows, judges, summary)
    require(summary['budget_counted_reservations'] == sum(t['budget_reservation'] is not None for t in terminals), 'RESERVATION_COUNT_DIFFERS')
    data.update(judges=judges, byterminal=byterminal, steps=steps, replays=replays,
        bindings=[{'path': p, 'sha256': h} for p, h in tracked.items()])
    return data


def tables(data):
    rows = data['observations']; expanded = []
    category = {m: c for c, ms in CATEGORIES.items() for m in ms}
    for row in rows:
        tid = row['trial_id']; term = data['byterminal'][tid]; step = data['steps'][row['anonymous_answer_id']]
        replay = data['replays'].get(tid, {})
        for metric in METRICS:
            value = row['metrics'][metric]; known = numeric.finite(value)
            if known: reason = None
            elif metric in ['sr', 'sp']: reason = 'deterministic_step_not_numeric'
            elif row['status'] == 'failed': reason = 'technical_failure_after_request' if row['actual_request_made'] else 'local_failure_without_request'
            elif metric in DEPENDENCIES: reason = 'dependent_component_unavailable'
            elif metric in numeric.EGES: reason = 'computed_component_withheld_or_unavailable'
            else: reason = 'successful_judge_component_unavailable'
            expanded.append({'anonymous_answer_id': row['anonymous_answer_id'], 'question_id': row['question_id'],
                'judge': row['judge'], 'trial_id': tid, 'status': row['status'], 'actual_request_made': row['actual_request_made'],
                'budget_reservation_made': term['budget_reservation'] is not None, 'local_failure_reason': term['local_failure_reason'],
                'category': category[metric], 'metric': metric, 'value': value, 'is_finite': known, 'known_zero': known and value == 0,
                'missing_classification': reason, 'missing_dependencies': [k for k in DEPENDENCIES.get(metric, []) if not numeric.finite(row['metrics'][k])],
                'step_missing_reason': step.get('missing_reason'), 'selected_reference_id': step.get('selected_reference_id'),
                'step_source': row['step_source'], 'new_judge_numeric_observation': metric in numeric.DIRECT and row['status'] == 'success' and known,
                'complete_numeric_CCE': row['complete_numeric_CCE'], 'evidence_state': row['evidence_state'],
                'component_gate_notes': replay.get('component_gate_notes'), 'source_fact_acceptance': row['source_fact_acceptance'],
                'formal_eligible': row['formal_eligible'], 'observation_pointer': f'observations.json#{tid}/metrics/{metric}',
                'numeric_replay_pointer': f'numeric_replays/{tid}.json' if replay else None,
                'terminal_trial_path': term['trial']['path'], 'terminal_trial_sha256': term['trial']['sha256']})
    require(len(expanded) == 256, 'FIXED_256_METRIC_SLOTS')
    return expanded


def plot(data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 12,
        'axes.labelsize': 10, 'xtick.labelsize': 9, 'ytick.labelsize': 9, 'axes.linewidth': .8,
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42, 'savefig.facecolor': 'white'})
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.subplots_adjust(left=.07, right=.98, bottom=.16, top=.81, wspace=.18, hspace=.52)
    fig.suptitle('Primary confirmation: per-answer CCE dimensions', x=.07, y=.973, ha='left', fontsize=17, fontweight='bold')
    fig.text(.07, .936, '8 fixed anonymous answers × 2 judges = 16 terminal observations; at most one request per cell', fontsize=10)
    count = data['completion_summary']['common_n']
    fig.text(.07, .907, f'Common complete CCE set: {count}/8 answers' + ('; no common-set mean is available' if count == 0 else '; original per-answer averages reported separately'), fontsize=10)
    handles = [Line2D([], [], marker=m, color=COLORS[i], ls='', label=['Primary judge', 'Secondary judge'][i]) for i, m in enumerate(['o', 's'])]
    handles.append(Line2D([], [], marker='x', color='#666666', ls='', label='NA shown below score axis (not zero)'))
    fig.legend(handles=handles, ncol=3, loc='upper left', bbox_to_anchor=(.061, .88), frameon=False, fontsize=10)
    index = {(r['anonymous_answer_id'], r['judge']): r for r in data['observations']}
    for metric, ax in zip(PLOT_METRICS, axes.flat):
        values = [r['metrics'][metric] for r in data['observations'] if numeric.finite(r['metrics'][metric])]
        lower, upper = min([0, *values]), max([1, *values])
        ax.set_ylim(lower-.025*(upper-lower), upper+.04*(upper-lower)); ax.set_xlim(-.5, 7.5)
        ax.set_xticks(range(8), labels=IDS); ax.set_ylabel('Original score'); ax.set_title(f'{metric}  |  finite {len(values)}/16', loc='left')
        ax.spines[['top', 'right']].set_visible(False); ax.grid(axis='y', color='#DDDDDD', lw=.65, zorder=0)
        ax.text(-.06, -.21, 'NA', transform=ax.transAxes, ha='right', va='center', fontsize=9, color='#666666')
        for i, aid in enumerate(IDS):
            pair = [index[aid, judge]['metrics'][metric] for judge in data['judges']]
            if all(numeric.finite(v) for v in pair): ax.plot([i-.12, i+.12], pair, color='#BBBBBB', lw=.8, zorder=1)
            for j, value in enumerate(pair):
                x = i+[-.12, .12][j]
                if numeric.finite(value): ax.plot(x, value, marker=['o', 's'][j], color=COLORS[j], ms=5, ls='', zorder=3)
                else: ax.plot(x, -.21, marker='x', color=COLORS[j], ms=5, ls='', transform=ax.get_xaxis_transform(), clip_on=False)
    fig.text(.07, .075, 'Both judge slots are retained for every answer. Lines join only pairs with two finite values; no imputation or error bars.', fontsize=9)
    fig.text(.07, .041, 'Conditional numeric results, not expert accuracy or wet-lab validity. Reused SR/SP are not additional judge observations.', fontsize=9)
    fig.canvas.draw(); return fig


def draft_check():
    require(not (OUT/'draft/draft_check.json').exists(), 'DRAFT_CHECK_ALREADY_RECORDED')
    def audit(event, args):
        if event in ['open', 'os.listdir', 'os.scandir'] and args and isinstance(args[0], (str, bytes, Path)):
            text = str(args[0]).lower().replace('\\', '/')
            actual_root = str(SOURCE).lower().replace('\\', '/')
            if (text == actual_root or text.startswith(actual_root+'/')) or any(k in text for k in ['sealed_confirmation', 'identity_key', 'confirmation_manifest']):
                raise PermissionError('DRAFT_FORBIDS_ACTUAL_PRIMARY_AND_SEALED_ACCESS')
    sys.addaudithook(audit)
    judges = ['FICTIONAL_PRIMARY', 'FICTIONAL_SECONDARY']; rows = []; steps = {}; terms = {}; replays = {}
    for i, aid in enumerate(IDS):
        steps[aid] = {'sr': 0 if i == 0 else .5, 'sp': .5, 'missing_reason': None, 'selected_reference_id': 'FICTIONAL_REFERENCE'}
        for ji, judge in enumerate(judges):
            success = ji == 0 and i < 7; local = i == 7
            components = {m: (0 if i == 0 else 1) for m in numeric.DIRECT+numeric.EGES}
            values = numeric.derive(components, steps[aid], success); tid = f'FICTIONAL_{aid}_{ji}'
            row = {'anonymous_answer_id': aid, 'question_id': [1, 2, 21, 22][i % 4], 'judge': judge, 'trial_id': tid,
                'status': 'success' if success else 'failed', 'actual_request_made': not local, 'metrics': values,
                'judge_attempt_failed': not success, 'complete_numeric_CCE': success,
                'step_source': 'deterministic_step_reuse', 'evidence_state': {'unresolved': not success},
                'source_fact_acceptance': 'separate_confirmation_evidence_review_required', 'formal_eligible': False}
            rows.append(row); terms[tid] = {'budget_reservation': None if local else {'synthetic': True},
                'local_failure_reason': 'FICTIONAL_CONTEXT_FAILURE' if local else None,
                'trial': {'path': 'FICTIONAL_NOT_A_FILE', 'sha256': '0'*64}}
            if success: replays[tid] = {'component_gate_notes': []}
    data = {'observations': rows, 'judges': judges, 'steps': steps, 'byterminal': terms, 'replays': replays,
            'completion_summary': original_summary(rows, judges)}
    checks = []
    def check(name, ok): require(ok, name); checks.append({'name': name, 'pass': True})
    check_summary(rows, judges, data['completion_summary']); tab = tables(data)
    check('fixed_16_cells_256_metric_slots', len(tab) == 256 and len(rows) == 16)
    check('seven_success_nine_failure_full_denominator', data['completion_summary']['technical_successes'] == 7 and data['completion_summary']['technical_failures'] == 9)
    check('empty_common_set_has_no_imputed_means', data['completion_summary']['common_n'] == 0 and data['completion_summary']['common_means'] == {})
    check('local_no_request_failures_retained', len([r for r in rows if not r['actual_request_made']]) == 2 and any(r['missing_classification'] == 'local_failure_without_request' for r in tab))
    check('known_zero_is_finite_not_missing', any(r['metric'] == 'Com' and r['known_zero'] and r['missing_classification'] is None for r in tab))
    check('failed_judge_keeps_deterministic_steps', all(numeric.finite(r['value']) and not r['new_judge_numeric_observation'] for r in tab if r['status'] == 'failed' and r['metric'] in ['sr', 'sp']))
    check('only_judge_direct_values_marked_as_new_judge_observations', all(not r['new_judge_numeric_observation'] for r in tab if r['category'] != 'direct_judge'))
    changed = copy.deepcopy(rows); changed[0]['metrics']['HV'] += .1
    try: original_summary(changed, judges)
    except ValueError as exc: check('changed_derived_score_rejected', str(exc) == 'ORIGINAL_DERIVED_FORMULA_MISMATCH')
    else: require(False, 'CHANGED_SCORE_ACCEPTED')
    try: original_summary(rows[:-1], judges)
    except ValueError: check('missing_observation_rejected', True)
    else: require(False, 'MISSING_CELL_ACCEPTED')
    partial = copy.deepcopy(rows); partial[0]['metrics'] = numeric.derive({**partial[0]['metrics'], 's_time': None}, steps['C01'], True); partial[0]['complete_numeric_CCE'] = False
    s = original_summary(partial, judges)
    check('partial_metrics_preserve_Com_but_Eff_HV_NA', partial[0]['metrics']['Com'] == 0 and partial[0]['metrics']['Eff'] is None and partial[0]['metrics']['HV'] is None and s['actual_terminal_observations'] == 16)
    common_rows = copy.deepcopy(rows)
    for row in common_rows:
        if row['anonymous_answer_id'] in ['C01', 'C05'] and row['judge'] == judges[1]:
            row['metrics'] = copy.deepcopy(next(r['metrics'] for r in rows if r['anonymous_answer_id'] == row['anonymous_answer_id'] and r['judge'] == judges[0]))
            row.update(status='success', judge_attempt_failed=False, complete_numeric_CCE=True)
    common_summary = original_summary(common_rows, judges)
    check('common_anonymous_answers_not_unique_tasks', common_summary['common_n'] == 2 and common_summary['common_question_id_counts'] == {'1': 2})
    try: load_actual(OUT/'NEVER_ACTUAL_MISSING')
    except ValueError as exc: check('render_refuses_missing_actual_terminal_outputs', str(exc) == 'ACTUAL_PRIMARY_TERMINAL_ANALYSIS_NOT_READY')
    else: require(False, 'MISSING_TERMINALS_ACCEPTED')
    try: safe_path(BASE/'validation_design_v1/sealed_confirmation/C01.json')
    except ValueError: check('protected_source_rejected_without_access', True)
    else: require(False, 'SOURCE_PATH_ACCEPTED')
    import matplotlib.pyplot as plt
    fig = plot(data); check('fictional_canvas_draw_only_no_real_figure_export', len(fig.axes) == 4); plt.close(fig)
    proto = {'status': 'draft_wait_root_actual_confirmation_complete', 'fixed_answer_ids': IDS,
        'answer_denominator': 8, 'judge_count': 2, 'terminal_cell_denominator': 16, 'metric_slot_denominator': 256,
        'metric_categories': CATEGORIES, 'plot_metrics': PLOT_METRICS, 'score_definitions': numeric.definition(),
        'expected_backend_assets': {'converter': bind(MODULE), 'schema': bind(SCHEMA), 'development_backend': bind(BACKEND), 'numeric_adapter': bind(numeric.__file__)},
        'primary_analyzer': bind(PRIMARY), 'style_baseline': bind(STYLE), 'new_statistics': False,
        'NA_imputation': False, 'actual_source_text_reads': False, 'formal_or_expert_claims': False,
        'render_gate': 'all16terminal + original_analysis_verification_pass + frozen_v7_metadata_bindings + original_numeric_consistency',
        'full_raw_source_replay': 'original primary analyze owns this; renderer does not reopen source text or rerun converter',
        'post_render_PNG_visual_QA_required': True}
    save(OUT/'draft/prototype.json', proto)
    save(OUT/'draft/draft_check.json', {'status': 'pass_draft_software_only_wait_actual_confirmation', 'checks': checks,
        'actual_command': [sys.executable, *sys.argv], 'script': bind(__file__), 'source_schema_and_documentation': [bind(PRIMARY), bind(numeric.__file__), *[bind(p) for p in DOCS]],
        'actual_primary_outputs_read': False, 'actual_Cxx_text_read_or_hashed': False,
        'fake_result_figures_exported': False, 'new_model_requests': 0, 'new_embeddings': 0})
    save(OUT/'draft/completion.json', {'status': 'draft_ready_wait_actual_primary_terminal', 'script': bind(__file__),
        'draft_check': bind(OUT/'draft/draft_check.json'), 'prototype': bind(OUT/'draft/prototype.json'),
        'actual_render_executed': False, 'new_model_requests': 0, 'new_embeddings': 0})
    print(json.dumps({'status': 'draft_check_pass', 'checks': len(checks), 'actual_render': False}))


def render():
    target = OUT/'actual'; require(not target.exists(), 'ACTUAL_REPORT_ALREADY_EXISTS_NO_OVERWRITE')
    data = load_actual(); rows = tables(data); fig = plot(data)
    target.mkdir(parents=True)
    csv_rows(target/'all_metrics_256.csv', rows)
    csv_rows(target/'cce_dimensions_64.csv', [r for r in rows if r['metric'] in PLOT_METRICS])
    csv_rows(target/'observations_16.csv', [{k: v for k, v in r.items() if k != 'metrics'} | r['metrics'] for r in data['observations']])
    csv_rows(target/'missing_metrics.csv', [r for r in rows if not r['is_finite']])
    coverage = [{'category': c, 'metric': m, 'finite_n': data['completion_summary']['per_metric_numeric'][m], 'denominator': 16,
                 'deterministic_not_new_judge': c == 'deterministic_steps'} for c, ms in CATEGORIES.items() for m in ms]
    csv_rows(target/'metric_coverage.csv', coverage)
    save(target/'common_complete_set.json', {k: data['completion_summary'][k] for k in ['common_answer_ids', 'common_n', 'common_means', 'common_question_id_counts', 'aggregation']})
    for ext in ['png', 'svg', 'pdf']: fig.savefig(target/('per_answer_cce.'+ext), dpi=300)
    import matplotlib.pyplot as plt
    plt.close(fig)
    s = data['completion_summary']
    caption = ('Per-answer conditional Com, Cor, Eff and HV for eight fixed anonymous answers evaluated once by each of two frozen judges. '
        'This is within-exposed-task answer-level automatic confirmation, not unseen-task or source-family validation. '
        'All 16 terminal slots are retained. Blue circles and orange squares identify the primary and secondary judge; '
        'a line joins two finite values for the same answer. Crosses in the separate NA row indicate unavailable values, never zero. '
        f'The common complete CCE set contains {s["common_n"]}/8 answers. '
        'No uncertainty interval, imputation, new threshold, or independent-sample claim is introduced. '
        'SR/SP are reused deterministic inputs. Technical completion and numeric availability are not expert accuracy, task suitability, or wet-lab validation.\n')
    (target/'caption.md').write_text(caption, encoding='utf8')
    judge_lines = '\n'.join(f'- {label}: `{judge}`' for label, judge in zip(['Primary judge', 'Secondary judge'], data['judges']))
    text = f'''# 主确认 v3：真实终态报告

固定 8 答案 × 2 judge = 16 格；技术成功 {s['technical_successes']}/16，失败 {s['technical_failures']}/16，实际请求 {s['actual_requests']}/16，完整数值 CCE {s['complete_numeric_CCE']}/16。
共同完整 CCE 集合 {s['common_n']}/8；为空时原 common_means 为空对象，不补零、不排名。均值沿用原逐答案等权汇总，不是 qid 等权结果。
每格至多一次实际请求；本地未请求失败同样保留。这是已暴露任务内的答案级自动确认（within-exposed-task answer-level automatic confirmation），不构成未见任务或来源家族验证（unseen-task/source-family validation）。

{judge_lines}

图见 per_answer_cce.png/svg/pdf，逐点来源表 cce_dimensions_64.csv；全部 16 指标、256 格及并存缺失原因见 all_metrics_256.csv。NA 不被归并为单一 API 或参考缺失原因。
已知 SR/SP 在 judge 失败时保留；它们不是额外 judge 观测。原 8 份答案不是 16 个独立答案，16 分项也不是独立样本。

此报告未读取原答案文本、封存 Cxx、identity 或 confirmation_manifest。完整原文/HTTP/转换/EGES 重放由已通过的原 analyze 验证，报告核验元数据链、终态来源与原指标一致性。
不能据此宣称专家一致性、科学正确率、真实实验有效性或全题库泛化。本轮 optional blind 已在确认前禁用。

实际命令及源 SHA 见 source_and_command.json；PNG 仍需 root 实际目视验收，SVG/PDF 仅同画布导出。
'''
    (target/'README.md').write_text(text, encoding='utf8')
    for item in data['bindings']: require(sha(item['path']) == item['sha256'], 'INPUT_CHANGED_DURING_RENDER')
    save(target/'source_and_command.json', {'status': 'rendered_from_actual_verified_terminal_analysis',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'actual_command': [sys.executable, *sys.argv],
        'cwd': str(Path.cwd()), 'script': bind(__file__), 'prototype': bind(OUT/'draft/prototype.json'),
        'bindings': data['bindings'], 'actual_answers': 8, 'actual_terminal_cells': 16, 'metric_slots': 256,
        'source_text_reopened': False, 'new_model_requests': 0, 'new_embeddings': 0,
        'original_full_raw_replay_owner': str(PRIMARY), 'scoring_changed': False, 'new_statistics': False,
        'visual_QA': {'PNG': 'pending_actual_view_image', 'SVG_PDF': 'same_canvas_export_not_separately_rendered'},
        'outputs': [bind(p) for p in sorted(target.iterdir()) if p.is_file()]})
    print(json.dumps({'status': 'rendered_pending_PNG_visual_QA', 'terminal_cells': 16, 'metric_slots': 256, 'out': str(target)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['draft-check', 'render']); args = parser.parse_args()
    draft_check() if args.action == 'draft-check' else render()
