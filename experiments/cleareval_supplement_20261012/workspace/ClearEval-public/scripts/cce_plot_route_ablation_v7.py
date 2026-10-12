"""Source-bound publication exports for the v7 offline route-pool diagnostic."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts/cce_validation'
SOURCE = ART / 'controls/paired_route_ablation_v7'
OUT = ART / 'figures_route_ablation_v7'
COLORS = {'filtered': '#0072B2', 'unfiltered': '#D55E00'}
LABELS = {'filtered': 'Route-filtered SR', 'unfiltered': 'Unfiltered max-SR'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    inputs = [SOURCE / name for name in ('summary.json', 'per_case.json', 'paired_results.json', 'saved_result_review.json')]
    frozen_hashes = {str(p): sha(p) for p in inputs}
    summary, cases, pairs, review = [load(p) for p in inputs]
    assert review['status'] == 'pass' and summary['unique_pairs'] == 3 and summary['new_judge_requests'] == 0
    current = [r for r in pairs if r['pool'] == 'v7']
    assert len(current) == 9 and {r['question_id'] for r in current} == {2, 21, 22}
    case_index = {(r['pair_id'], r['threshold'], r['side']): r for r in cases if r['pool'] == 'v7'}
    delta_rows = []
    for pair in current:
        for mode in ('filtered', 'unfiltered'):
            baseline = case_index[pair['pair_id'], pair['threshold'], 'baseline']
            variant = case_index[pair['pair_id'], pair['threshold'], 'variant']
            delta_rows.append({'question_id': pair['question_id'], 'pair_id': pair['pair_id'],
                'threshold': pair['threshold'], 'reference_pool': 'v7', 'setting': mode,
                'baseline_sr': pair[f'{mode}_baseline_sr'], 'deletion_sr': pair[f'{mode}_variant_sr'],
                'delta_sr_deletion_minus_baseline': pair[f'{mode}_delta_sr'],
                'baseline_reference_id': baseline[mode + '_reference_id'],
                'deletion_reference_id': variant[mode + '_reference_id'],
                'unique_pairs_in_experiment': 3, 'thresholds_are_repeated_settings': True,
                'formal_eligible': False})
    paired_rows = []
    for row in delta_rows:
        if row['question_id'] != 2 or row['threshold'] != .7:
            continue
        for condition in ('baseline', 'deletion'):
            paired_rows.append({'question_id': 2, 'threshold': .7, 'setting': row['setting'],
                'condition': condition, 'sr': row[condition + '_sr'],
                'reference_id': row[condition + '_reference_id'], 'unique_pair_id': row['pair_id'],
                'formal_eligible': False})
    table(OUT / 'deletion_delta_by_threshold.csv', delta_rows)
    table(OUT / 'q2_primary_paired_scores.csv', paired_rows)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.linewidth': .8,
        'axes.labelsize': 10, 'xtick.labelsize': 9, 'ytick.labelsize': 9,
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'savefig.facecolor': 'white'})
    exports = []
    fig, axes = plt.subplots(1, 3, figsize=(9.4, 3.65), sharey=True)
    fig.subplots_adjust(left=.095, right=.985, bottom=.245, top=.73, wspace=.2)
    for letter, qid, ax in zip('ABC', [2, 21, 22], axes):
        ax.axhline(0, color='#7A7A7A', linewidth=.8, zorder=0)
        ax.axvline(.7, color='#D8D8D8', linewidth=1, linestyle=':', zorder=0)
        for mode in ('unfiltered', 'filtered'):
            selected = sorted([r for r in delta_rows if r['question_id'] == qid and r['setting'] == mode], key=lambda r: r['threshold'])
            values = [r['delta_sr_deletion_minus_baseline'] for r in selected]
            ax.plot([r['threshold'] for r in selected], values, color=COLORS[mode],
                linestyle='--' if mode == 'unfiltered' else '-', linewidth=1.5,
                marker='s' if mode == 'unfiltered' else 'o', markersize=7.2 if mode == 'unfiltered' else 4.2,
                markerfacecolor='white' if mode == 'unfiltered' else COLORS[mode], markeredgewidth=1.35,
                zorder=2 if mode == 'unfiltered' else 3)
        ax.set(xlim=(.585, .815), ylim=(-.315, .04), xticks=[.6, .7, .8],
            yticks=[-.3, -.2, -.1, 0], xlabel=r'Matching threshold $\delta$')
        ax.set_title(f'{letter}  q{qid}', loc='left', fontsize=11, fontweight='bold', pad=10)
        ax.grid(axis='y', color='#EAEAEA', linewidth=.6, zorder=0)
        if qid == 2:
            ax.annotate('0.0000', xy=(.7, 0), xytext=(0, 7), textcoords='offset points', ha='center', color=COLORS['unfiltered'], fontsize=8)
            ax.annotate('-0.1429', xy=(.7, -1/7), xytext=(7, -12), textcoords='offset points', ha='left', color=COLORS['filtered'], fontsize=8)
        else:
            ax.text(.03, .05, 'Both settings coincide', transform=ax.transAxes, color='#555555', fontsize=8)
    axes[0].set_ylabel(r'$\Delta$SR (deletion $-$ baseline)')
    legend = [Line2D([0], [0], color=COLORS['filtered'], marker='o', markersize=4, label=LABELS['filtered']),
              Line2D([0], [0], color=COLORS['unfiltered'], marker='s', markerfacecolor='white', linestyle='--', label=LABELS['unfiltered'])]
    fig.legend(handles=legend, loc='upper center', bbox_to_anchor=(.53, .87), ncol=2, frameon=False, fontsize=9)
    fig.suptitle('Deletion sensitivity under the frozen v7 reference pool', y=.98, fontsize=12)
    fig.text(.5, .085, 'Three existing pairs; thresholds reuse the same six full texts and do not add independent observations.', ha='center', fontsize=8.3)
    fig.text(.5, .035, 'Step-level development diagnostic. Reference applicability and edit necessity await expert confirmation.', ha='center', fontsize=8, color='#555555')
    for ext in ('png', 'svg', 'pdf'):
        path = OUT / f'deletion_delta_by_threshold.{ext}'
        fig.savefig(path, dpi=300, bbox_inches='tight'); exports.append(path)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 4.0), sharey=True)
    fig.subplots_adjust(left=.085, right=.965, bottom=.23, top=.75, wspace=.32)
    for letter, mode, ax in zip('AB', ('filtered', 'unfiltered'), axes):
        selected = next(r for r in delta_rows if r['question_id'] == 2 and r['threshold'] == .7 and r['setting'] == mode)
        values = [selected['baseline_sr'], selected['deletion_sr']]
        route = 'FDISCO' if mode == 'filtered' else 'uDISCO'
        ax.plot([0, 1], values, color=COLORS[mode], marker='o' if mode == 'filtered' else 's',
            markerfacecolor=COLORS[mode] if mode == 'filtered' else 'white', linewidth=1.8, markersize=6,
            linestyle='-' if mode == 'filtered' else '--', markeredgewidth=1.5)
        for x, value in enumerate(values):
            ax.annotate(f'{value:.4f}', xy=(x, value), xytext=(0, 10), textcoords='offset points', ha='center', color=COLORS[mode], fontsize=10)
        ax.set(xticks=[0, 1], xticklabels=['Baseline', 'Deletion'], xlim=(-.2, 1.2), ylim=(0, 1.02), yticks=[0, .25, .5, .75, 1])
        ax.set_title(f'{letter}  {LABELS[mode]}\nSelected reference: {route}', loc='left', fontsize=10, pad=11)
        ax.text(.5, .08, rf"$\Delta$SR = {selected['delta_sr_deletion_minus_baseline']:.4f}", transform=ax.transAxes, ha='center', color=COLORS[mode], fontsize=10)
        ax.grid(axis='y', color='#EAEAEA', linewidth=.6)
    axes[0].set_ylabel('Step recall (SR)')
    fig.suptitle(r'q2 at $\delta$ = 0.7: changing the reference changes the deletion contrast', fontsize=11, y=.975)
    fig.text(.5, .095, 'One existing pair; the generated answers declare FDISCO in both conditions.', ha='center', fontsize=8.2)
    fig.text(.5, .04, 'The unfiltered result does not establish that uDISCO is a valid alternative for this task.', ha='center', fontsize=8.2, color='#555555')
    for ext in ('png', 'svg', 'pdf'):
        path = OUT / f'q2_primary_paired_scores.{ext}'
        fig.savefig(path, dpi=300, bbox_inches='tight'); exports.append(path)
    plt.close(fig)
    assert all(sha(Path(path)) == value for path, value in frozen_hashes.items())
    manifest = {'status': 'generated_pending_visual_qa', 'input_sha256': frozen_hashes,
        'script_sha256': sha(Path(__file__)), 'actual_command': [sys.executable, 'scripts/cce_plot_route_ablation_v7.py'],
        'cwd': str(ROOT), 'matplotlib_version': matplotlib.__version__, 'new_judge_requests': 0,
        'unique_pairs': 3, 'unique_full_texts': 6, 'thresholds_are_not_independent_pairs': True,
        'uncertainty_intervals': 'not estimated from three development pairs', 'formal_eligible': False,
        'data_rows': {'deletion_delta_by_threshold': len(delta_rows), 'q2_primary_paired_scores': len(paired_rows)},
        'files_sha256': {p.name: sha(p) for p in exports + list(OUT.glob('*.csv'))}}
    (OUT / 'generation.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'generated', 'figure_exports': len(exports), 'csv_rows': len(delta_rows) + len(paired_rows), 'new_judge_requests': 0}))


if __name__ == '__main__':
    main()
