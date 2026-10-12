"""Update numeric analysis for the frozen v5 reference delta; reuse unchanged draws."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_analysis as a

BASE = ROOT / 'artifacts/cce_validation'
OLD = BASE / 'analysis_expanded_tasks_v4'
OUT = BASE / 'analysis_expanded_references_v5'
FIG = BASE / 'figures_expanded_references_v5'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    files = [BASE / f'expanded_references_v5_t{t}_per_answer.json' for t in ('060', '070', '080')]
    primary = a.load(files[1])
    previous = a.load(BASE / 'expanded_tasks_v4_t070_per_answer.json')
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
        prior = next(v for k, v in old_run['inputs'].items() if Path(k).name == p.name)
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
    figure_reuse = {}
    for stem, key in [('historical_legacy_cce_projections', 'historical_legacy'),
                      ('formal_cce_projections', 'formal_fixed_cohort'),
                      ('development_cce_projections', 'pilot_participating_subset')]:
        assert analyses[key] == prior_summaries[key], key
        for ext in ('csv', 'png', 'svg', 'pdf'):
            src = BASE / 'figures_expanded_tasks_v4' / f'{stem}.{ext}'
            dst = FIG / src.name
            shutil.copy2(src, dst)
            assert sha(src) == sha(dst)
            figure_reuse[str(dst.relative_to(BASE))] = {'source': str(src.relative_to(BASE)), 'sha256': sha(src)}
    metrics = ['sr', 'sp', *a.SUMMARY_METRICS]
    changed = [r['answer_id'] for r in primary
               if any(r.get(k) != original[r['answer_id']].get(k) for k in metrics)]
    assert changed == ['openai_deepseek-chat__q1'], changed
    curve = []
    for path in files:
        row = next(r for r in a.load(path) if r['answer_id'] == changed[0])
        curve.append({k: row.get(k) for k in ['answer_id', 'threshold', 'sr', 'sp', *a.SUMMARY_METRICS]})
    fig, axes = a.plt.subplots(1, 2, figsize=(7.0, 2.9), constrained_layout=True)
    counts = [sum(a.finite(r.get('sr')) for r in previous), sum(a.finite(r.get('sr')) for r in primary)]
    axes[0].bar(['Previous pool', '+ conditional uDISCO'], counts, color=['#87939C', '#397C9F'])
    axes[0].set_ylim(0, 80)
    axes[0].set_ylabel('Answers with provisional step scores')
    axes[0].set_title('A  Reference coverage (77 answers)', loc='left')
    for x, n in enumerate(counts):
        axes[0].text(x, n + 1.5, str(n), ha='center')
    for key, label, color, marker in [('sr', 'SR', '#397C9F', 'o'), ('sp', 'SP', '#C47730', 's')]:
        axes[1].plot([r['threshold'] for r in curve], [r[key] for r in curve],
                     marker=marker, color=color, label=label, markersize=5)
    axes[1].set_xticks([0.6, 0.7, 0.8])
    axes[1].set_ylim(-0.035, 1.05)
    axes[1].set_xlabel('Cosine threshold (primary = 0.7)')
    axes[1].set_ylabel('Step matching score')
    axes[1].set_title('B  Added q1 uDISCO answer', loc='left')
    axes[1].legend(frameon=False)
    fig.suptitle('Development reference expansion; scientific applicability pending', fontsize=9)
    a.plot_save(fig, FIG / 'udisco_reference_expansion')
    a.plt.close(fig)
    a.write_csv(FIG / 'udisco_reference_expansion.csv', [
        {'panel': 'A', 'pool': 'v4', 'count': counts[0], 'denominator': 77},
        {'panel': 'A', 'pool': 'v5', 'count': counts[1], 'denominator': 77},
        *[{'panel': 'B', **row} for row in curve]])
    summary = {
        'status': 'pass', 'actual_answers': len(primary), 'numeric_steps': sum(a.finite(r.get('sr')) for r in pilot),
        'numeric_CCE': sum(all(a.finite(r.get(k)) for k in a.DIMENSIONS) for r in pilot),
        'formal_answers': sum(r.get('formal_eligible') is True for r in pilot),
        'numeric_delta_answer_ids': changed, 'old_component_rows_verified': 77,
        'full_grid_expected': 13 * 253, 'full_archive_rows': len(revised),
        'full_grid_missing_answers': 13 * 253 - len(revised),
        'full_cohort_common_n': analyses['revised_full_fixed_cohort']['common_n'],
        'unchanged_bootstrap_reuse': reused, 'figure_reuse': figure_reuse, 'new_model_requests': 0,
        'command': [sys.executable, 'scripts/cce_analyze_references_v5.py'],
        'script_sha256': sha(__file__), 'analysis_library_sha256': sha(ROOT / 'scripts/cce_analysis.py'),
        'inputs_sha256': {str(p.relative_to(BASE)): sha(p) for p in
            [*files, bindings, BASE / 'cohort_frozen.json', OLD / 'joint_summary.json', OLD / 'analysis_run.json']},
    }
    a.save(OUT / 'analysis_run.json', summary)
    (OUT / 'README.md').write_text(
        '# v5 numerical analysis\n\nThe original archived parameter, correctness and EGES components are unchanged in all 77 rows. '
        'Only affected coverage and common-set analyses were refreshed. Historical and prespecified Gemini bootstrap draws '
        'were reused after matching their actual inputs. No new model calls were made.\n\n'
        'Source applicability remains provisional, and the fixed 13-model common set remains empty. '
        'The conditional uDISCO reference does not establish whole-brain activity-label compatibility. '
        'A zero SR denotes this matcher output; it does not mean that the answer has no operations.\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['status', 'actual_answers', 'numeric_steps', 'numeric_CCE',
          'numeric_delta_answer_ids', 'full_cohort_common_n', 'new_model_requests']}))


if __name__ == '__main__':
    main()
