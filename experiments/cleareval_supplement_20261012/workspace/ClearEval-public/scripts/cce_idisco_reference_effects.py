"""Audit and plot the offline iDISCO+ reference expansion on unchanged answers."""
from pathlib import Path
import collections
import json
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as c
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DEST = c.OUT / 'analysis_supplement_v3'
FIG = c.OUT / 'figures_supplement_v3'
METRICS = ['sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']
PRESERVE = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem',
            's_method', 's_label', 's_trans', 's_time', 'Cor', 'Eff']


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    inputs, comparisons, by_threshold, new_rows = {}, [], [], []
    for threshold in (.6, .7, .8):
        tag = f't{round(threshold * 100):03d}'
        oldpath = c.OUT / f'supplement_v2_{tag}_per_answer.json'
        newpath = c.OUT / f'supplement_v2_idisco_{tag}_per_answer.json'
        steppath = c.OUT / f'supplement_v2_idisco_{tag}_step_matches.json'
        inputs.update({str(x): c.filehash(x) for x in (oldpath, newpath, steppath)})
        old = {r['answer_id']: r for r in c.read(oldpath)}
        new = {r['answer_id']: r for r in c.read(newpath)}
        details = {r['answer_id']: r for r in c.read(steppath)}
        assert old.keys() == new.keys() and len(new) == 65
        added, unchanged = [], []
        for key, b in new.items():
            a = old[key]
            assert all(a[k] == b[k] for k in PRESERVE), (key, threshold)
            assert a['answer_sha256'] == b['answer_sha256']
            assert a['question_sha256'] == b['question_sha256']
            if a['sr'] is not None:
                assert all(a[k] == b[k] for k in METRICS)
                assert a['reference_id'] == b['reference_id']
                unchanged.append(key)
            elif b['sr'] is not None:
                assert b['question_id'] == 2 and b['route_id'] == 'iDISCO+'
                added.append(key)
                step = details[key]
                new_rows.append({'threshold': threshold, 'answer_id': key,
                                 'model': b['model'], 'question_id': b['question_id'],
                                 'reference_id': b['reference_id'],
                                 **{k: b[k] for k in METRICS},
                                 **{k: step[k] for k in ['reference_n', 'generated_n',
                                     'reference_truncated', 'generated_truncated', 'generated_cjk_steps']},
                                 'maximum_pair_similarity': max(step['generated_max_similarity'], default=None),
                                 'zero_score_is_not_evidence_of_no_operations': step['generated_n'] > 0 and b['sr'] == 0,
                                 'formal_eligible': False})
            comparisons.append({'answer_id': key, 'threshold': threshold,
                'previous_reference': a['reference_id'], 'current_reference': b['reference_id'],
                'previous_sr': a['sr'], 'current_sr': b['sr'],
                'previous_Com': a['Com'], 'current_Com': b['Com'],
                'newly_numeric': a['sr'] is None and b['sr'] is not None,
                'original_components_unchanged': True,
                'formal_eligible': False})
        by_threshold.append({'threshold': threshold, 'answers': len(new),
                             'previous_numeric': len(unchanged), 'newly_numeric': len(added),
                             'current_numeric': sum(r['sr'] is not None for r in new.values()),
                             'remaining_missing': sum(r['sr'] is None for r in new.values()),
                             'new_answer_ids': added,
                             'old_numeric_metrics_exactly_unchanged': True})
    c.table(DEST / 'reference_expansion_pairs.csv', comparisons)
    c.table(DEST / 'new_idisco_answers.csv', new_rows)
    c.write(DEST / 'new_idisco_answers.json', new_rows)
    summary = {'scope': 'reference_expansion_not_generator_improvement',
               'thresholds': by_threshold, 'compared_rows': len(comparisons),
               'original_components_preserved': PRESERVE,
               'formal_eligible_answers': 0, 'new_model_requests': 0,
               'language_limitation': 'The original English MPNet baseline is retained. Chinese operations with numeric zero matches are not claimed to be absent; no translation or retuning was applied to improve these observed results.',
               'inputs': inputs,
               'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
               'script_sha256': c.filehash(__file__)}
    c.write(DEST / 'reference_expansion_summary.json', summary)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8), gridspec_kw={'width_ratios': [1, 1.7]})
    primary = next(x for x in by_threshold if x['threshold'] == .7)
    axes[0].bar(['Previous', 'Expanded'], [primary['previous_numeric']] * 2,
                label='Unchanged numeric', color='#4477AA', width=.6)
    axes[0].bar(['Previous', 'Expanded'], [0, primary['newly_numeric']],
                bottom=[primary['previous_numeric']] * 2,
                label='New iDISCO+ candidate', color='#228833', width=.6)
    for i, n in enumerate([primary['previous_numeric'], primary['current_numeric']]):
        axes[0].text(i, n + .5, f'{n}/65', ha='center')
    axes[0].set_ylim(0, max(30, primary['current_numeric'] + 7))
    axes[0].set_ylabel('Answers with provisional SR/SP')
    axes[0].set_title('a  Reference coverage at threshold 0.7', loc='left', fontsize=10)
    axes[0].legend(frameon=False, fontsize=8, loc='upper left')
    models = sorted({r['model'] for r in new_rows})
    for j, (t, color) in enumerate(zip((.6, .7, .8), ('#BBBBBB', '#4477AA', '#CC6677'))):
        selected = {r['model']: r for r in new_rows if r['threshold'] == t}
        axes[1].barh([i + (j - 1) * .23 for i in range(len(models))],
                     [selected[m]['sr'] for m in models], height=.21,
                     color=color, label=f'{t:.1f}')
    axes[1].set_yticks(range(len(models)), [m.removeprefix('openai_') for m in models])
    for i, model in enumerate(models):
        if all(r['sr'] == 0 for r in new_rows if r['model'] == model):
            axes[1].text(.015, i, '0 at all thresholds', va='center', fontsize=8, color='#666666')
    axes[1].set_xlim(0, 1.02)
    axes[1].set_xlabel('SR (source-reported clearing scope only)')
    axes[1].set_title('b  Newly scored q2 answers: threshold sensitivity', loc='left', fontsize=10)
    axes[1].legend(title='Threshold', frameon=False, fontsize=8, loc='upper right')
    fig.suptitle('Official iDISCO+ source expansion — development candidates, no expert confirmation', fontsize=11)
    fig.tight_layout(rect=(0, .02, 1, .92))
    stem = FIG / 'idisco_reference_expansion'
    for suffix in ('png', 'svg', 'pdf'):
        fig.savefig(stem.with_suffix('.' + suffix), dpi=220, bbox_inches='tight')
    plt.close(fig)
    c.table(stem.with_suffix('.csv'), new_rows)
    c.write(FIG / 'idisco_plot_run.json', {'command': summary['command'],
        'script_sha256': summary['script_sha256'], 'inputs': inputs,
        'plotted_new_answer_rows': len(new_rows), 'coverage_panel': primary,
        'outputs': {str(stem.with_suffix('.' + e)): c.filehash(stem.with_suffix('.' + e))
                    for e in ('png', 'svg', 'pdf', 'csv')},
        'new_model_requests': 0, 'formal_eligible': False})
    print(json.dumps({'thresholds': by_threshold, 'new_answer_metric_rows': len(new_rows)}))


if __name__ == '__main__':
    main()
