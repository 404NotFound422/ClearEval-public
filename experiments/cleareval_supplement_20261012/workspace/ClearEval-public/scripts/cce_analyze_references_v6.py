"""Update numeric analysis for the frozen v6 reference delta; reuse unchanged draws."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import math
import csv
from collections import Counter

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_analysis as a

BASE = ROOT / 'artifacts/cce_validation'
OLD = BASE / 'analysis_expanded_references_v5'
OUT = BASE / 'analysis_expanded_references_v6'
FIG = BASE / 'figures_expanded_references_v6'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def task_bootstrap(summary, index, repeats=2000, seed=20261008):
    """Synchronize original task draws across all models; never invent source families."""
    qs, models = summary['common_question_ids'], summary['model_cohort']
    assert qs
    rng = a.np.random.default_rng(seed)
    draws, values, front_counts = [], {m: {k: [] for k in a.SUMMARY_METRICS} for m in models}, Counter()
    for rep in range(repeats):
        selected = [qs[int(i)] for i in rng.choice(len(qs), len(qs), replace=True)]
        means = {m: {k: math.fsum(index[m][q][k] for q in selected) / len(selected)
                     for k in a.SUMMARY_METRICS} for m in models}
        _, front = a.matrix_and_pareto(means)
        front_counts.update(front)
        for m, scores in means.items():
            draws.append({'replicate': rep, 'model': m, 'question_draws': len(selected), **scores})
            for k, value in scores.items():
                values[m][k].append(value)
    return {'status': 'degenerate_single_task' if len(qs) == 1 else 'descriptive_task_resampling',
            'unit': 'synchronized original task', 'seed': seed, 'repeats_completed': repeats,
            'task_count': len(qs), 'common_question_ids': qs,
            'reason': 'Different models select different source routes for the same task; the unchanged source-family bootstrap remains unresolved. Task resampling is reported separately.',
            'limitation': 'One task gives identical draws and zero-width intervals; frequencies describe only this task and provide no cross-task uncertainty estimate.',
            'percentile_intervals': {m: {k: [float(x) for x in a.np.quantile(v, [.025, .975])]
                                         for k, v in fields.items()} for m, fields in values.items()},
            'nondominance_frequency': {m: front_counts[m] / repeats for m in models}}, draws


def main():
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    files = [BASE / f'expanded_references_v6_t{t}_per_answer.json' for t in ('060', '070', '080')]
    primary = a.load(files[1])
    previous = a.load(BASE / 'expanded_references_v5_t070_per_answer.json')
    assert len(primary) == len(previous) == 77
    original = {r['answer_id']: r for r in previous}
    old_fields = ['answer_sha256', 'question_sha256', 'c_step', 'c_param', 'co_order',
                  'co_method', 'co_param', 'co_chem', 's_method', 's_label', 's_trans',
                  's_time', 'Cor', 'Eff', 'historical_Com']
    for r in primary:
        assert all(r.get(k) == original[r['answer_id']].get(k) for k in old_fields), r['answer_id']
    frozen = a.load(BASE / 'cohort_frozen.json')
    models = frozen['models']
    bindings = BASE / 'inventory/answer_score_bindings.json'
    old_run = a.load(OLD / 'analysis_run.json')
    for p in (bindings, BASE / 'cohort_frozen.json'):
        prior = next(v for k, v in old_run['inputs_sha256'].items() if Path(k).name == p.name)
        assert sha(p) == prior, str(p)
    archived = a.archive_rows(a.load(bindings))
    pilot = a.project_pilot(primary)
    assert all(r['formula_check'] == 'pass' for r in pilot)
    revised = a.revised_full_rows(archived, pilot)
    old_pilot = a.project_pilot(previous)
    prior_summaries = a.load(OLD / 'joint_summary.json')
    analyses = {'historical_legacy': prior_summaries['historical_legacy']}
    reused = ['historical_legacy: unchanged archived bindings and frozen model cohort']
    a.save(OUT / 'historical_legacy.json', analyses['historical_legacy'])
    for suffix in ('means.csv', 'dominance.csv', 'bootstrap_draws.csv'):
        shutil.copy2(OLD / f'historical_legacy_{suffix}', OUT / f'historical_legacy_{suffix}')
    configs = [
        ('revised_full_fixed_cohort', revised, models, 'revised_CCE_partial_archived_components', False),
        ('pilot_fixed_cohort', pilot, models, 'development_provisional_archive_linked', False),
        ('formal_fixed_cohort', pilot, models, 'formal_confirmed', True),
        ('pilot_participating_subset', pilot, ['gemini-3-flash', 'gemini-3-pro'],
         'development_provisional_archive_linked_subset', False),
    ]
    for name, rows, cohort, scope, formal in configs:
        summary, index = a.common_summary(rows, cohort, scope=scope, denominator=253, formal=formal)
        if name == 'pilot_participating_subset':
            assert [r for r in pilot if r['model'] in cohort] == [r for r in old_pilot if r['model'] in cohort]
            prior = prior_summaries[name]
            assert all(summary[k] == prior[k] for k in summary)
            summary['bootstrap'] = prior['bootstrap']
            shutil.copy2(OLD / f'{name}_bootstrap_draws.csv', OUT / f'{name}_bootstrap_draws.csv')
            reused.append(name + ': all selected input rows and summary fields unchanged')
        else:
            boot, draws = a.family_bootstrap(summary, index, 2000, 20261008)
            summary['bootstrap'] = boot
            a.write_csv(OUT / f'{name}_bootstrap_draws.csv', draws,
                        ['replicate', 'model', 'question_draws', *a.SUMMARY_METRICS])
        summary['limitation'] = prior_summaries[name]['limitation']
        if name in ('revised_full_fixed_cohort', 'pilot_fixed_cohort') and summary['common_n']:
            if name == 'pilot_fixed_cohort':
                assert summary['means'] == analyses['revised_full_fixed_cohort']['means']
                summary['task_bootstrap'] = analyses['revised_full_fixed_cohort']['task_bootstrap']
                shutil.copy2(OUT / 'revised_full_fixed_cohort_task_bootstrap_draws.csv',
                             OUT / f'{name}_task_bootstrap_draws.csv')
            else:
                summary['task_bootstrap'], task_draws = task_bootstrap(summary, index)
                a.write_csv(OUT / f'{name}_task_bootstrap_draws.csv', task_draws)
        analyses[name] = summary
        a.save(OUT / f'{name}.json', summary)
        a.write_csv(OUT / f'{name}_means.csv', [
            {'model': m, 'numeric_scope': scope, 'common_n': summary['common_n'], **v}
            for m, v in summary['means'].items()], ['model', 'numeric_scope', 'common_n', *a.SUMMARY_METRICS])
        a.write_csv(OUT / f'{name}_dominance.csv', [
            {'dominator': x, 'dominated': y, 'dominates': v}
            for x, row in summary['dominance_matrix'].items() for y, v in row.items()],
            ['dominator', 'dominated', 'dominates'])
    a.save(OUT / 'joint_summary.json', analyses)
    a.save(OUT / 'revised_full_numeric_rows.json', revised)
    a.write_csv(OUT / 'revised_full_numeric_rows.csv', revised)
    a.write_csv(OUT / 'pilot_numeric_rows.csv', pilot)
    cov = a.coverage_rows(archived, models, 253, 'historical_legacy_cstep')
    cov += a.coverage_rows(pilot, models, 253, 'development_provisional_archive_linked')
    a.write_csv(OUT / 'component_coverage.csv', cov)
    a.write_csv(OUT / 'revised_component_coverage.csv',
                a.coverage_rows(revised, models, 253, 'revised_CCE_partial_archived_components'))
    a.plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.labelsize': 8,
        'xtick.labelsize': 7, 'ytick.labelsize': 7, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.spines.top': False, 'axes.spines.right': False})
    a.plot_coverage(cov, models, 253, FIG)
    a.sensitivity_analysis(files, models, 253, OUT, FIG)
    # Plot the measured step-task denominator, not the 253-task archive scaffold.
    projection_summary = {**analyses['revised_full_fixed_cohort'],
                          'evaluated_question_n': len({r['question_id'] for r in primary})}
    a.projections(projection_summary, 'fixed13_common_task_cce_projections', FIG,
                  'Provisional fixed 13-model CCE; one common task; scientific applicability pending')
    with (FIG / 'threshold_sensitivity.csv').open(encoding='utf-8-sig', newline='') as fh:
        plotted = list(csv.DictReader(fh))
    fig, axes = a.plt.subplots(1, 2, figsize=(9.7, 3.5), constrained_layout=True)
    for ax, metric in zip(axes, ('sr', 'sp')):
        for i, model in enumerate(models):
            rr = sorted([r for r in plotted if r['metric'] == metric and r['model'] == model],
                        key=lambda r: float(r['threshold']))
            if not rr:
                continue
            assert len({r['n'] for r in rr}) == 1
            ax.plot([float(r['threshold']) for r in rr], [float(r['available_item_mean']) for r in rr],
                    marker=a.MARKERS[i % len(a.MARKERS)], color=a.COLORS[i % len(a.COLORS)],
                    label=f"{model.removeprefix('openai_')} (n={rr[0]['n']})", markersize=4)
        ax.set(xlabel='Cosine threshold', ylabel='Within-model mean ' + metric.upper(), ylim=(-.03, 1.03))
        ax.set_xticks([.6, .7, .8])
        ax.grid(color='#DDDDDD', linewidth=.5)
    axes[-1].legend(fontsize=6, frameon=False, loc='upper left', bbox_to_anchor=(1.01, 1))
    fig.suptitle('Within-model paired threshold curves; answer sets differ across models\nDevelopment diagnostic; not a common-task model ranking', fontsize=9)
    a.plot_save(fig, FIG / 'threshold_sensitivity')
    threshold_joint = []
    for path in files:
        threshold_rows = a.project_pilot(a.load(path))
        summary, _ = a.common_summary(threshold_rows, models, scope='development_fixed13_threshold_comparison', denominator=253)
        assert summary['common_question_ids'] == analyses['revised_full_fixed_cohort']['common_question_ids']
        threshold_joint.append({'threshold': threshold_rows[0]['threshold'], **summary})
    a.save(OUT / 'common_cohort_threshold_sensitivity.json', threshold_joint)
    a.write_csv(OUT / 'common_cohort_threshold_sensitivity.csv', [
        {'threshold': s['threshold'], 'model': m, 'common_question_ids': '|'.join(s['common_question_ids']),
         'common_n': s['common_n'], 'nondominated_3d': m in s['empirical_nondominated'], **v}
        for s in threshold_joint for m, v in s['means'].items()])
    figure_reuse = {}
    for stem, key in [('historical_legacy_cce_projections', 'historical_legacy'),
                      ('formal_cce_projections', 'formal_fixed_cohort'),
                      ('development_cce_projections', 'pilot_participating_subset')]:
        assert analyses[key] == prior_summaries[key], key
        for ext in ('csv', 'png', 'svg', 'pdf'):
            src = BASE / 'figures_expanded_references_v5' / f'{stem}.{ext}'
            dst = FIG / src.name
            shutil.copy2(src, dst)
            assert sha(src) == sha(dst)
            figure_reuse[str(dst.relative_to(BASE))] = {'source': str(src.relative_to(BASE)), 'sha256': sha(src)}
    metrics = ['sr', 'sp', *a.SUMMARY_METRICS]
    changed = [r['answer_id'] for r in primary
               if any(r.get(k) != original[r['answer_id']].get(k) for k in metrics)]
    expected = ['glm4.7-thinking__q2', 'glm4.7-unthinking__q2', 'glm4.7-unthinking__q248',
                'openai_deepseek-chat__q2', 'openai_deepseek-chat__q248',
                'openai_deepseek-reasoner__q2', 'openai_deepseek-reasoner__q248']
    assert sorted(changed) == sorted(expected), changed
    for r in primary:
        if r['answer_id'] not in changed:
            assert r == original[r['answer_id']], r['answer_id']
    curve = []
    for path in files:
        for row in a.load(path):
            if row['answer_id'] in changed:
                curve.append({k: row.get(k) for k in ['answer_id', 'threshold', 'sr', 'sp', *a.SUMMARY_METRICS]})
    fig, axes = a.plt.subplots(1, 3, figsize=(9.2, 3.4), constrained_layout=True,
                               gridspec_kw={'width_ratios': [1.05, 1.4, 1.4]})
    counts = [sum(a.finite(r.get('sr')) for r in previous), sum(a.finite(r.get('sr')) for r in primary)]
    axes[0].bar(['Prior pool', '+ q2/q248'], counts, color=['#87939C', '#397C9F'])
    axes[0].set_ylim(0, 80)
    axes[0].set_ylabel('Answers with provisional step scores')
    axes[0].set_title('A  Coverage (77 answers)', loc='left')
    for x, n in enumerate(counts):
        axes[0].text(x, n + 1.5, str(n), ha='center')
    labels = ['GLM think q2', 'GLM no-think q2', 'GLM no-think q248', 'DS Chat q2',
              'DS Chat q248', 'DS Reason q2', 'DS Reason q248']
    thresholds = [0.6, 0.7, 0.8]
    for ax, metric, letter in zip(axes[1:], ['sr', 'sp'], ['B', 'C']):
        values = [[next(r[metric] for r in curve if r['answer_id'] == aid and r['threshold'] == t)
                   for t in thresholds] for aid in expected]
        im = ax.imshow(values, aspect='auto', cmap='Blues', vmin=0, vmax=1)
        ax.set_xticks(range(3), [str(t) for t in thresholds])
        ax.set_yticks(range(7), labels if metric == 'sr' else [''] * 7)
        ax.set_xlabel('Cosine threshold')
        ax.set_title(f'{letter}  New-answer {metric.upper()}', loc='left')
        for y, vals in enumerate(values):
            for x, val in enumerate(vals):
                ax.text(x, y, f'{val:.2f}', ha='center', va='center',
                        color='white' if val > .5 else '#172B39', fontsize=7)
    fig.colorbar(im, ax=axes[1:], shrink=.72, label='Step matching score')
    fig.suptitle('Development reference expansion; initial prerequisites and applicability pending', fontsize=9)
    a.plot_save(fig, FIG / 'udisco_reference_expansion')
    a.plt.close(fig)
    a.write_csv(FIG / 'udisco_reference_expansion.csv', [
        {'panel': 'A', 'pool': 'v5', 'count': counts[0], 'denominator': 77},
        {'panel': 'A', 'pool': 'v6', 'count': counts[1], 'denominator': 77},
        *[{'panel': 'B/C', **row} for row in curve]])
    summary = {
        'status': 'pass', 'actual_answers': len(primary), 'numeric_steps': sum(a.finite(r.get('sr')) for r in pilot),
        'numeric_CCE': sum(all(a.finite(r.get(k)) for k in a.DIMENSIONS) for r in pilot),
        'formal_answers': sum(r.get('formal_eligible') is True for r in pilot),
        'numeric_delta_answer_ids': changed, 'old_component_rows_verified': 77,
        'full_grid_expected': 13 * 253, 'full_archive_rows': len(revised),
        'full_grid_missing_answers': 13 * 253 - len(revised),
        'full_cohort_common_n': analyses['revised_full_fixed_cohort']['common_n'],
        'unchanged_bootstrap_reuse': reused, 'figure_reuse': figure_reuse, 'new_model_requests': 0,
        'command': [sys.executable, 'scripts/cce_analyze_references_v6.py'],
        'script_sha256': sha(__file__), 'analysis_library_sha256': sha(ROOT / 'scripts/cce_analysis.py'),
        'inputs_sha256': {str(p.relative_to(BASE)): sha(p) for p in
            [*files, bindings, BASE / 'cohort_frozen.json', OLD / 'joint_summary.json', OLD / 'analysis_run.json']},
    }
    a.save(OUT / 'analysis_run.json', summary)
    (OUT / 'README.md').write_text(
        '# v6 numerical analysis\n\nThe original archived parameter, correctness and EGES components are unchanged in all 77 rows. '
        'Only affected coverage and common-set analyses were refreshed. Historical and prespecified Gemini bootstrap draws '
        'were reused after matching their actual inputs. No new model calls were made.\n\n'
        'Source applicability remains provisional. The fixed 13-model common set now contains only q2. '
        'Its separate synchronized task bootstrap is degenerate; the original source-family bootstrap remains pending because routes differ across models. '
        'Conditional uDISCO references do not establish initial prerequisites, whole-brain activity-label compatibility or axonal-label coverage. '
        'A zero SR denotes this matcher output; it does not mean that the answer has no operations.\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['status', 'actual_answers', 'numeric_steps', 'numeric_CCE',
          'numeric_delta_answer_ids', 'full_cohort_common_n', 'new_model_requests']}))


if __name__ == '__main__':
    main()
