"""Draft E4 report renderer; actual plots require verified 30-cell v7 results.

No scoring, model call, new threshold or inferential statistic. Draft checks use
only fictional values and public design metadata, never partial actual results.
"""
from __future__ import annotations
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT)]
import cce_analyze_grounded_stability_dev_v1 as analysis

BASE = ROOT/'artifacts/cce_validation/optimizer_20261010'
SOURCE = BASE/'grounded_stability_dev_v1'
OUT = BASE/'grounded_stability_v7_report_v1'
DESIGN = BASE/'grounded_stability_design_v1/v7_draft/draft_plan.json'
STYLE = ROOT/'scripts/cce_plot_step_threshold_diagnostic_v1.py'
IDS = [f'A{i:02d}' for i in range(1, 6)]
CATEGORIES = analysis.CATEGORIES
METRICS = analysis.METRICS
COLORS = ['#0072B2', '#D55E00', '#009E73']
TITLES = {'direct_judge': 'Direct judge scores', 'computed_EGES': 'Computed EGES',
          'deterministic_steps': 'Fixed SR/SP evidence (not new judge observations)', 'derived': 'Derived CCE indices'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def csv_rows(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)


def check_tables(observations, models, tables):
    require(len(models) == len(set(models)) == 2, 'TWO_MODELS_REQUIRED')
    stats = analysis.summarize(observations, IDS, models)
    for key in ['within', 'between', 'same_repeat_pairs', 'category_summary', 'common_numeric_by_repeat', 'common_numeric_all_six']:
        require(stats[key] == tables[key], 'ORIGINAL_STATISTICS_REPLAY_DIFFERS:'+key)
    require([len(stats[k]) for k in ['within', 'between', 'same_repeat_pairs']] == [160, 80, 240], 'METRIC_SLOT_DENOMINATORS')
    for row in stats['within']:
        require((row['range'] is None) == (row['finite_n'] < 2), 'SINGLETON_OR_ABSENT_RANGE_IS_NOT_NA')
        if row['metric'] in ['sr', 'sp']:
            require(row['new_judge_numeric_observations'] == 0 and not row['counts_as_direct_judge_stability'], 'FIXED_STEPS_COUNTED_AS_JUDGE_STABILITY')
    return stats


def load_actual(source=SOURCE):
    """Only render invokes this gate. No actual input is read by draft-check."""
    source = Path(source); folder = source/'analysis'
    required = [source/n for n in ['plan.json', 'matrix.json', 'reuse_manifest.json', 'reuse_decision.json', 'expected_contract.json', 'analysis_definition.json']]
    required += [folder/(n+'.json') for n in ['completion_summary', 'analysis_verification', 'observations', 'within', 'between',
        'same_repeat_pairs', 'category_summary', 'common_numeric_by_repeat', 'common_numeric_all_six', 'fixed_step_evidence']]
    require(all(p.is_file() for p in required), 'ACTUAL_E4_TERMINAL_ANALYSIS_NOT_READY')
    data = {p.stem: read(p) for p in required}
    plan, summary, verified = (data[k] for k in ['plan', 'completion_summary', 'analysis_verification'])
    require(plan['selected_backend_version'] == summary['selected_backend'] == 'v7', 'V7_ACTUAL_BACKEND_REQUIRED')
    require(plan['new_requests_planned'] == 25 and plan['reused_observations'] == 5 and plan['planned_observations'] == 30, 'FROZEN_25_NEW_PLUS_5_REUSE_REQUIRED')
    require(summary['status'] == 'complete_development_diagnostic_not_scientific_validation' and summary['actual_observations'] == 30 and summary['unique_base_answers'] == 5, 'ACTUAL_THIRTY_TERMINAL_REQUIRED')
    require(verified.get('status') == 'pass' and verified.get('all_30_terminal_cells_retained') is True, 'ACTUAL_ANALYSIS_VERIFICATION_REQUIRED')
    require([verified[k] for k in ['within_groups', 'between_groups', 'same_repeat_pairs']] == [160, 80, 240], 'VERIFIED_DENOMINATORS_CHANGED')
    require(verified['script'] == bind(analysis.__file__), 'ANALYZER_CODE_CHANGED')
    require(data['analysis_definition']['metric_categories'] == CATEGORIES and data['analysis_definition']['tolerance'] == analysis.TOL, 'FROZEN_METRIC_DEFINITION_CHANGED')
    dependencies = []
    for item in [*plan['frozen_inputs'], *plan['reused_original_files'], *summary['frozen_actual_files'], *verified['frozen_inputs']]:
        text = item['path'].lower().replace('\\', '/')
        require(not any(x in text for x in ['sealed_confirmation', 'identity_key', 'identity_manifest', 'confirmation_manifest', '/human_review/private/']), 'UNEXPECTED_PROTECTED_INPUT_DEPENDENCY')
        require(sha(item['path']) == item['sha256'], 'SOURCE_BINDING_DRIFT:'+item['path'])
        dependencies.append(Path(item['path']))
    models = summary['models']; rows = data['observations']; matrix = data['matrix']
    require(len(matrix) == len(rows) == 30 and {r['trial_id'] for r in rows} == {m['planned_trial_id'] for m in matrix}, 'ACTUAL_MATRIX_IDENTITY_MISMATCH')
    lookup = {r['trial_id']: r for r in rows}
    for cell in matrix:
        row = lookup[cell['planned_trial_id']]
        require(row['status'] in ['success', 'failed'] and (row['anonymous_answer_id'], row['judge'], row['repeat_index']) == (cell['anonymous_answer_id'], cell['judge'], cell['repeat_index']), 'TERMINAL_GRID_CHANGED')
        path = source/'run/trials'/f"{cell['planned_trial_id']}.json"
        trial = read(path); dependencies.append(path)
        require(trial['status'] == row['status'] and trial['identity'] == cell['identity'] and trial['attempt'] == 1, 'TERMINAL_SOURCE_CHANGED')
        if row['status'] == 'failed':
            require(all(row[k] is None for k in METRICS if k not in ['sr', 'sp']), 'FAILED_JUDGE_COMPONENT_NOT_NA')
        require(row['exact_prior_observation_reused'] == (cell['disposition'] == 'exact_prior_observation_reused'), 'REUSE_IDENTITY_CHANGED')
    require(sum(r['exact_prior_observation_reused'] for r in rows) == summary['exact_reused_observations'] == 5, 'FIVE_EXACT_REUSES_REQUIRED')
    require(len(data['reuse_manifest']) == 5 and data['reuse_decision']['reuse_all_five'] is True, 'ALL_FIVE_STATUS_BLIND_REUSE_PROOF_REQUIRED')
    stats = check_tables(rows, models, data)
    require(summary['per_component_numeric'] == {k: sum(analysis.finite(r[k]) for r in rows) for k in METRICS}, 'METRIC_COVERAGE_COUNT_CHANGED')
    require(summary['technical_successes'] == sum(r['technical_pipeline_complete'] for r in rows) and summary['technical_successes'] + summary['technical_failures'] == 30, 'TECHNICAL_DENOMINATOR_CHANGED')
    require(summary['deterministic_step_zero_range_counts_as_judge_stability_success'] is False, 'STEP_STABILITY_MISINTERPRETATION')
    data['stats'] = stats
    data['models'] = models
    data['bindings'] = [bind(p) for p in dict.fromkeys([*required, *dependencies, Path(__file__), Path(analysis.__file__), STYLE])]
    return data


def plot_panels(data, kind):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.titlesize': 10,
        'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'axes.linewidth': .8,
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42, 'savefig.facecolor': 'white'})
    fig, axes = plt.subplots(4, 5, figsize=(16, 12.5))
    fig.subplots_adjust(left=.065, right=.985, bottom=.095, top=.865, wspace=.36, hspace=.75)
    title = 'Repeated-score variation within each judge' if kind == 'within' else 'Matched-repeat differences between judges'
    fig.suptitle(title, x=.065, y=.979, ha='left', fontsize=17, fontweight='bold')
    fig.text(.065, .948, '5 fixed development answers × 2 judges × 3 repeats; 25 new requests + 5 exact prior observations', fontsize=10)
    if kind == 'within':
        handles = [Line2D([], [], marker='o', color=COLORS[0], ls='', label='Primary judge'), Line2D([], [], marker='s', color=COLORS[1], ls='', label='Secondary judge'),
                   Line2D([], [], marker='o', color='#555555', ls='', label='Filled: 3/3 finite'), Line2D([], [], marker='o', mfc='white', color='#555555', ls='', label='Open: 2/3 finite'),
                   Line2D([], [], marker='x', color='#888888', ls='', label='×: range NA (label gives finite n)')]
    else:
        handles = [Line2D([], [], marker=m, color=COLORS[i], ls='', label=f'Repeat {i}') for i, m in enumerate(['o', '^', 's'])]
        handles += [Line2D([], [], marker='x', color='#888888', ls='', label='×: pair unavailable (not zero)')]
    fig.legend(handles=handles, ncol=len(handles), loc='upper left', bbox_to_anchor=(.058, .927), frameon=False, fontsize=9)
    for category_index, (category, metrics) in enumerate(CATEGORIES.items()):
        for metric_index in range(5):
            ax = axes[category_index, metric_index]
            if metric_index >= len(metrics):
                ax.set_visible(False); continue
            metric = metrics[metric_index]
            if metric_index == 0:
                pos = ax.get_position(); fig.text(.065, pos.y1+.026, TITLES[category], fontsize=11, fontweight='bold')
            group = [r for r in data['within' if kind == 'within' else 'same_repeat_pairs'] if r['metric'] == metric]
            values = [r['range'] if kind == 'within' else r['llama_minus_qwen'] for r in group]
            finite_values = [abs(v) for v in values if analysis.finite(v)]
            cap = max(finite_values, default=0) or 1
            ax.set_xlim(-.5, 4.5); ax.set_ylim(-.20*cap if kind == 'within' else -1.25*cap, 1.25*cap)
            ax.set_xticks(range(5), labels=IDS); ax.yaxis.set_major_locator(MaxNLocator(4))
            ax.set_title(f'{metric}  |  available {len(finite_values)}/{10 if kind == "within" else 15}', loc='left', pad=7)
            ax.spines[['top', 'right']].set_visible(False); ax.grid(axis='y', color='#DDDDDD', lw=.65, zorder=0)
            ax.axhline(0, color='#666666', lw=.8, zorder=1)
            if kind == 'within':
                ax.set_yticks([t for t in ax.get_yticks() if 0 <= t <= 1.25*cap])
            if category == 'deterministic_steps': ax.set_facecolor('#F3F3F3')
            for row in group:
                aid = row['anonymous_answer_id']; index = IDS.index(aid)
                series = data['models'].index(row['judge']) if kind == 'within' else row['repeat_index']
                x = index + ([-.13, .13][series] if kind == 'within' else [-.22, 0, .22][series])
                value = row['range'] if kind == 'within' else row['llama_minus_qwen']
                marker = ['o', 's'][series] if kind == 'within' else ['o', '^', 's'][series]
                if analysis.finite(value):
                    face = 'white' if kind == 'within' and row['finite_n'] == 2 else COLORS[series]
                    ax.plot(x, value, marker=marker, ms=4.5, ls='', mfc=face, mec=COLORS[series], mew=1.1, zorder=3)
                else:
                    ax.plot(x, .035, marker='x', color='#888888', ms=4, ls='', transform=ax.get_xaxis_transform(), zorder=3)
                    if kind == 'within': ax.text(x, .095, str(row['finite_n']), transform=ax.get_xaxis_transform(), fontsize=7, ha='center', color='#777777')
            if metric_index == 0: ax.set_ylabel('Raw score range' if kind == 'within' else 'Secondary − primary')
    fig.text(.065, .049, 'Metric panels retain their original units; axis ranges can differ. NA is shown separately, never imputed as zero.', fontsize=9)
    fig.text(.065, .022, 'Descriptive development diagnostic only. SR/SP reuse is not judge stability; 160/80/240 metric slots are not independent answers.', fontsize=9)
    fig.canvas.draw()
    return fig


def draft_check():
    out = OUT/'draft'; require(not (out/'draft_check.json').exists(), 'DRAFT_CHECK_ALREADY_RECORDED')
    plan = read(DESIGN)
    require(plan['selected_backend_draft'] == 'v7' and plan['planned_observations'] == 30 and plan['new_request_bounds'] == [25, 25], 'PUBLIC_DESIGN_SCOPE_CHANGED')
    models = ['FICTIONAL_PRIMARY', 'FICTIONAL_SECONDARY']; rows = []
    for ai, aid in enumerate(IDS):
        for mi, model in enumerate(models):
            for repeat in range(3):
                values = {m: (0.5 if m in ['sr', 'sp'] else float(repeat+mi)) for m in METRICS}
                if ai == 1 and repeat > 0: values['c_param'] = None
                if ai == 2: values['co_order'] = None
                if ai == 3 and repeat == 2: values['co_param'] = None
                rows.append({'anonymous_answer_id': aid, 'judge': model, 'repeat_index': repeat, **values})
    stats = analysis.summarize(rows, IDS, models); check_tables(rows, models, stats)
    tests = []
    def check(name, ok): require(ok, name); tests.append({'name': name, 'pass': True})
    within = {(r['anonymous_answer_id'], r['judge'], r['metric']): r for r in stats['within']}
    check('singleton_range_and_SD_remain_NA', within['A02', models[0], 'c_param']['range'] is None and within['A02', models[0], 'c_param']['sample_sd'] is None)
    check('zero_finite_group_retained_with_NA', within['A03', models[0], 'co_order']['finite_n'] == 0 and within['A03', models[0], 'co_order']['range'] is None)
    check('partial_two_separate_from_complete_three', within['A04', models[0], 'co_param']['finite_n'] == 2 and within['A04', models[0], 'co_param']['coverage'] == 'partial')
    check('deterministic_zero_not_judge_stability', all(r['range'] == 0 and r['new_judge_numeric_observations'] == 0 for r in stats['within'] if r['category'] == 'deterministic_steps'))
    check('160_80_240_full_slot_grid', [len(stats[k]) for k in ['within', 'between', 'same_repeat_pairs']] == [160, 80, 240])
    changed = copy.deepcopy(stats); changed['within'][0]['range'] += 1
    try: check_tables(rows, models, changed)
    except ValueError: check('changed_statistics_rejected', True)
    else: require(False, 'CHANGED_STATISTICS_ACCEPTED')
    try: load_actual(OUT/'NEVER_ACTUAL_PRIVATE_MISSING')
    except ValueError as exc: check('render_rejects_missing_terminal_evidence_before_output', str(exc) == 'ACTUAL_E4_TERMINAL_ANALYSIS_NOT_READY')
    else: require(False, 'MISSING_EVIDENCE_ACCEPTED')
    import matplotlib.pyplot as plt
    for kind in ['within', 'between']:
        fig = plot_panels({'models': models, **stats}, kind)
        check(kind+'_fictional_canvas_drawn_without_result_export', len(fig.axes) == 20)
        plt.close(fig)
    save(out/'draft_check.json', {'status': 'pass_draft_software_only_wait_actual_E4', 'checks': tests,
        'actual_command': [sys.executable, *sys.argv], 'script': bind(__file__),
        'inputs': [bind(DESIGN), bind(analysis.__file__), bind(STYLE)], 'actual_E4_results_read': False,
        'actual_figures_exported': False, 'new_model_requests': 0, 'new_embeddings': 0,
        'existing_frozen_code_or_results_modified': False, 'render_gate': 'Actual 30 terminal cells, exact5 reuse, analysis verification pass, source hashes and original statistics replay required.'})
    print(json.dumps({'status': 'draft_check_pass', 'checks': len(tests), 'actual_render': False}))


def render():
    data = load_actual(); dest = OUT/'actual'
    require(not dest.exists(), 'ACTUAL_REPORT_EXISTS_USE_SEPARATE_VERSION')
    dest.mkdir(parents=True)
    figures = []
    import matplotlib.pyplot as plt
    captions = {
        'within': '**Within-judge repeated-score variation.** Each metric panel displays the original raw range for each of five fixed answers and each judge. Filled symbols have three finite repeats, open symbols two. A grey × denotes an unavailable range (fewer than two finite repeats); its label is the finite count. Failures remain in the planned denominator. Row groups distinguish direct scores, computed EGES, deterministic SR/SP, and derived CCE. Grey SR/SP panels reuse fixed-text evidence and their zero ranges are not judge stability successes. The 160 groups are dependent metric slots, not 160 answers; no uncertainty intervals or new inferential tests are used.',
        'between': '**Cross-judge differences at matched repeats.** Points are the original secondary-minus-primary score at repeats 0, 1 and 2 for each of five answers. A pair is numeric only when both values are finite. Grey × symbols retain unavailable pairs separately from zero. The 240 matched metric slots form 80 answer-by-metric groups, not 240 independent observations. Axes retain each metric’s raw units. Deterministic SR/SP comparisons are fixed evidence, while EGES and CCE are dependent computed quantities. This plot neither establishes scientific correctness nor selects a best repeat.'}
    for kind, stem in [('within', 'within_repeat_ranges'), ('between', 'matched_judge_differences')]:
        fig = plot_panels(data, kind)
        for ext in ['png', 'svg', 'pdf']:
            path = dest/f'{stem}.{ext}'; fig.savefig(path, dpi=300); figures.append(path)
        plt.close(fig)
        csv_path = dest/f'{stem}.csv'; csv_rows(csv_path, data['within' if kind == 'within' else 'same_repeat_pairs']); figures.append(csv_path)
        caption = dest/f'{stem}_caption.md'; caption.write_text(captions[kind]+'\n\nModel order: '+json.dumps(data['models'] if 'models' in data else data['completion_summary']['models'])+'\n', encoding='utf8'); figures.append(caption)
    for name in ['observations', 'between', 'category_summary', 'common_numeric_by_repeat', 'fixed_step_evidence']:
        csv_rows(dest/(name+'.csv'), data[name])
    summary = data['completion_summary']; lines = ['# E4 v7 真实重复评价结果', '',
        f"固定5答案、2 judge、3 repeats，共30格；新请求 {summary['new_requests_this_batch']}/25，精确复用5份。技术完成 {summary['technical_successes']}/30，技术失败 {summary['technical_failures']}/30；完整CCE {summary['complete_numeric_CCE']}/30。", '',
        '| 类别 | within完整3次 / 计划 | within可算range | 非零range | cross至少1对有限 / 计划 | cross至少1次不同 |',
        '|---|---:|---:|---:|---:|---:|']
    for r in data['category_summary']:
        lines.append(f"| {r['category']} | {r['within_complete_three']}/{r['within_planned_groups']} | {r['within_range_evaluable']} | {r['within_nonzero_range']} | {r['between_any_pair_evaluable']}/{r['between_planned_groups']} | {r['between_any_pair_different']} |")
    lines += ['', '直接judge稳定性仅对应 direct_judge 行。SR/SP是5份固定答案的确定性证据，不把20个within步骤展示格的零波动当作模型稳定成功。EGES与衍生指标存在依赖，分项不是独立样本。', '',
        '未知和失败不补0；少于2个有限重复的range/SD为NA。跨judge同repeat差值要求两值均有限；三次均值差只有双方各3次完整才可用。未新增ICC、统计检验、阈值或评分公式。', '',
        '图表为开发诊断，不是专家或湿实验验证。完整科学适用性和人工事实验收按原状态保留；5答案不可外推全库。PNG实际目视检查尚待完成，SVG/PDF仅为同画布导出。']
    (dest/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf8')
    require(all(sha(x['path']) == x['sha256'] for x in data['bindings']), 'SOURCE_CHANGED_DURING_RENDER')
    save(dest/'source_and_command.json', {'status': 'rendered_actual_verified_E4_descriptive_only', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'actual_command': [sys.executable, *sys.argv], 'input_bindings': data['bindings'],
        'outputs': [bind(p) for p in sorted(dest.iterdir()) if p.is_file()], 'new_model_requests': 0, 'new_embeddings': 0,
        'score_recomputation': False, 'original_statistics_replayed': True, 'metric_slots_are_independent_samples': False,
        'new_ICC_or_threshold': False, 'expert_accuracy_claimed': False,
        'PNG_visual_review': 'pending_view_image', 'SVG_PDF_visual_status': 'same_canvas_exports_not_separately_rendered'})
    print(json.dumps({'status': 'actual_report_rendered', 'output': str(dest), 'visual_review': 'pending'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['draft-check', 'render']); args = parser.parse_args()
    if args.action == 'draft-check': draft_check()
    else: render()
