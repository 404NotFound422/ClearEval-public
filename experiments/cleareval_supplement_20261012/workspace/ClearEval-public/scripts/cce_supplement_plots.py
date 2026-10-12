"""Plot actual reference-version sensitivity and provisional alternative-answer pairs."""
from pathlib import Path
import csv
import json
import math
import sys
import collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cce_validation import ROOT, OUT, read, write, table, filehash


def formats(fig, path):
    for extension in ['png', 'svg', 'pdf']:
        fig.savefig(path.with_suffix('.' + extension), dpi=300, facecolor='white')
    plt.close(fig)


def current_controls(output):
    source = OUT / 'judges/local_controls_supplement_v2/paired_results.json'
    pairs = read(source)
    assert len(pairs) == 15 and all(p['technical_pipeline_complete'] for p in pairs)
    conditions = [
        ('necessary_step_deletion', 'RI / storage deletion'),
        ('necessary_parameter_deletion', 'Duration deletion'),
        ('deterministic_equivalent_representation', 'Numbering'),
        ('evidence_supported_order_conflict', 'Order conflict'),
        ('adjacent_entry_merge', 'Adjacent-step merge'),
    ]
    metrics = [('sr', 'SR', 1), ('sp', 'SP', 1), ('c_param', 'Parameter / 3', 3),
               ('co_order', 'Order / 3', 3), ('Com', 'Com', 1), ('Cor', 'Cor', 1),
               ('Eff', 'Eff', 1), ('IA', 'IA', 1), ('HV', 'HV', 1)]
    colors = {2: '#0072B2', 21: '#D55E00', 22: '#009E73'}
    markers = {2: 'o', 21: 's', 22: '^'}
    offsets = {2: -.12, 21: 0, 22: .12}
    fig, axes = plt.subplots(3, 3, figsize=(11, 9.3), sharex=True, sharey=True)
    rows = []
    for ax, (metric, title, divisor) in zip(axes.flat, metrics):
        ax.axvline(0, color='#555555', lw=.8)
        for index, (key, label) in enumerate(conditions):
            selected = [p for p in pairs if p['condition'] == key]
            assert len(selected) == 3
            for pair in selected:
                qid = pair['question_id']
                delta = pair['delta_' + metric]
                value = delta / divisor
                ax.plot([0, value], [index + offsets[qid]] * 2,
                        color=colors[qid], lw=.8, alpha=.6)
                ax.scatter(value, index + offsets[qid], color=colors[qid],
                           marker=markers[qid], s=25, label=f'q{qid}' if index == 0 else None,
                           zorder=3)
                rows.append({'pair_id': pair['pair_id'], 'question_id': qid,
                             'condition': key, 'metric': metric,
                             'baseline_raw': pair['baseline_' + metric],
                             'variant_raw': pair['variant_' + metric], 'delta_raw': delta,
                             'normalization_divisor': divisor, 'plotted_delta': value,
                             'formal_eligible': False})
        ax.set_title(title, fontsize=10)
        ax.set_xlim(-.8, .4)
        ax.set_xticks([-.8, -.4, 0, .4])
        ax.set_yticks(range(5), [label for _, label in conditions])
        ax.grid(axis='x', alpha=.16)
    axes[0, 0].invert_yaxis()
    axes[0, 2].legend(loc='lower right', fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel('Variant minus paired baseline')
    fig.suptitle('Full-text controls rescored with supplement-bound references', y=.98, fontsize=12)
    fig.text(.5, .023, '15 pairs; 3 source answers; 2 task families; 1 source family. Same frozen judge and reference configuration.\nEach point is one actual pair; repeated baselines are shared. Candidate applicability awaits expert review.',
             ha='center', fontsize=8)
    fig.subplots_adjust(left=.18, right=.98, top=.925, bottom=.12, wspace=.18, hspace=.28)
    target = output / 'controls_supplement_v2'
    table(target.with_suffix('.csv'), rows)
    formats(fig, target)
    return source, len(rows)


def current_stability(output):
    source = OUT / 'judges/local_stability_supplement_v2/per_observation.json'
    observations = read(source)
    assert len(observations) == 12
    metrics = ['Com', 'Cor', 'Eff', 'IA', 'HV']
    colors = {'local_qwen3_8b': '#0072B2', 'local_llama3_8b': '#D55E00'}
    judges = sorted({r['judge'] for r in observations}, reverse=True)
    # Use actual identifiers and stable label order; model family is a plotted variable.
    fig, axes = plt.subplots(1, 5, figsize=(11.5, 4.35), sharey=True)
    rows = []
    for ax, metric in zip(axes, metrics):
        for qindex, qid in enumerate([2, 21]):
            for jindex, judge in enumerate(judges):
                selected = sorted([r for r in observations if r['question_id'] == qid and r['judge'] == judge], key=lambda r:r['repeat_index'])
                assert len(selected) == 3
                # Three horizontal positions reveal every repeat even if values coincide.
                xvalues = [qindex + (jindex - .5) * .28 + (r['repeat_index'] - 1) * .055 for r in selected]
                yvalues = [r[metric] for r in selected]
                color = '#0072B2' if 'qwen' in judge else '#D55E00'
                ax.plot(xvalues, yvalues, color=color, lw=.8, alpha=.65)
                ax.scatter(xvalues, yvalues, color=color, marker='o' if 'qwen' in judge else 's',
                           s=24, label='Qwen3 8B' if 'qwen' in judge else 'Llama3 8B')
                for r, x, y in zip(selected, xvalues, yvalues):
                    rows.append({'trial_id': r['trial_id'], 'question_id': qid, 'judge': judge,
                                 'repeat_index': r['repeat_index'], 'metric': metric,
                                 'score': y, 'plot_x': x, 'exact_reused': r['exact_reused'],
                                 'explicit_route_mismatch': r['explicit_route_mismatch'],
                                 'rubric_example_copy': r['extraction_exactly_copies_rubric_example'],
                                 'formal_eligible': False})
        ax.set_title(metric)
        ax.set_xticks([0, 1], ['q2', 'q21'])
        ax.set(xlim=(-.35, 1.35), ylim=(-.04, 1.04))
        ax.grid(axis='y', alpha=.16)
    axes[0].set_ylabel('Provisional score')
    handles, labels = axes[-1].get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    fig.legend(unique.values(), unique.keys(), loc='upper center', bbox_to_anchor=(.5, .89), ncol=2, frameon=False)
    fig.suptitle('Repeated values are stable; extraction validity is not established', y=.98, fontsize=11)
    fig.text(.5, .025, '12 observations = 2 exact reuses + 10 new requests; 2 answers; 2 judge families; 3 repeats.\nLlama copied the rubric extraction example and assigned the wrong route in 6/6 observations. No formal results.',
             ha='center', fontsize=8)
    fig.subplots_adjust(left=.065, right=.985, top=.71, bottom=.23, wspace=.2)
    target = output / 'stability_supplement_v2'
    table(target.with_suffix('.csv'), rows)
    formats(fig, target)
    return source, len(rows)


def main():
    output = OUT / 'figures_supplement_v2'
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    old_path = OUT / 'two_source_t070_per_answer.json'
    new_path = OUT / 'supplement_v2_t070_per_answer.json'
    old = {r['answer_id']: r for r in read(old_path)}
    current = read(new_path)
    rows = []
    for r in current:
        a = old[r['answer_id']]
        assert a['answer_sha256'] == r['answer_sha256'] and a['question_sha256'] == r['question_sha256']
        assert all(a[k] == r[k] for k in ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem', 's_method', 's_label', 's_trans', 's_time', 'Cor', 'Eff'])
        if a['sr'] is None or r['sr'] is None:
            continue
        row = {'answer_id': r['answer_id'], 'model': r['model'], 'question_id': r['question_id'],
               'source_family': r.get('family_id'),
               'formal_eligible': False, 'comparison_scope': 'same_answer_different_source_reference_versions'}
        for metric in ['sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']:
            row['v1_' + metric], row['v2_' + metric] = a[metric], r[metric]
            row['delta_' + metric] = r[metric] - a[metric]
        rows.append(row)
    assert len(rows) == 20
    fig, axes = plt.subplots(1, 3, figsize=(10, 4.15))
    for ax, metric in zip(axes, ['sr', 'sp', 'Com']):
        ax.plot([0, 1], [0, 1], color='#888888', lw=.8, linestyle='--', zorder=1)
        for route, color, marker in [('FDISCO', '#0072B2', 'o'), ('PEGASOS', '#D55E00', 's')]:
            subset = [r for r in rows if (r['source_family'] or '').startswith(route + '_')]
            ax.scatter([r['v1_' + metric] for r in subset], [r['v2_' + metric] for r in subset],
                       color=color, marker=marker, s=42, alpha=.7, label=route, zorder=2)
        changed = sum(abs(r['delta_' + metric]) > 1e-12 for r in rows)
        ax.set_title(f'{metric.upper() if metric != "Com" else metric}: {changed}/20 changed')
        ax.set(xlim=(-.04, 1.04), ylim=(-.04, 1.04), xlabel='Main-text candidate v1')
        ax.set_aspect('equal', adjustable='box')
        ax.grid(alpha=.13)
    axes[0].set_ylabel('Supplement-bound candidate v2')
    axes[-1].legend(loc='lower right', fontsize=8)
    fig.suptitle('Reference updates change scores for unchanged answers', y=.975, fontsize=11)
    fig.text(.5, .025, '20 provisional answers; 5 questions; 2 source families. Overlapping points are retained.\nParameter completeness, Cor and Eff unchanged; no expert-confirmed reference.', ha='center', fontsize=8)
    fig.subplots_adjust(left=.075, right=.985, top=.84, bottom=.22, wspace=.28)
    path = output / 'reference_version_effects'
    table(path.with_suffix('.csv'), rows)
    formats(fig, path)
    changes = {metric: {'changed_n': sum(abs(r['delta_' + metric]) > 1e-12 for r in rows),
                        'mean_delta': sum(r['delta_' + metric] for r in rows) / len(rows)}
               for metric in ['sr', 'sp', 'Com', 'IA', 'HV']}
    write(OUT / 'reference_recovery/supplement_bound/reference_version_effects.json', {
        'compared_answers': len(rows), 'answer_and_question_identity_unchanged': True,
        'original_c_param_correctness_EGES_unchanged': True, 'metrics': changes,
        'inputs': {str(p): filehash(p) for p in [old_path, new_path]},
        'formal_eligible': False, 'new_model_requests': 0})

    pair_path = OUT / 'judges/local_alternative_development/paired_results.json'
    pairs = read(pair_path)
    summary_path = pair_path.parent / 'development_summary.json'
    summary = read(summary_path)
    metrics = ['Com', 'Cor', 'Eff', 'IA', 'HV']
    plotted = []
    fig, axes = plt.subplots(1, len(metrics), figsize=(11, 4.6), sharey=True)
    for ax, metric in zip(axes, metrics):
        ax.axvline(0, color='#555555', lw=.8)
        for index, pair in enumerate(pairs):
            complete = pair['technical_pipeline_complete']
            value = pair.get('delta_' + metric) if complete else None
            label = f"q{pair['question_id']} / {'Chat' if 'deepseek-chat' in pair['pair_id'] else 'Reasoner'}"
            color = '#0072B2' if 'deepseek-chat' in pair['pair_id'] else '#D55E00'
            if value is None:
                ax.text(0, index, 'unpaired' if metric == metrics[0] else '—', ha='center', va='center', fontsize=7, color='#666666', bbox={'facecolor':'white','edgecolor':'none','pad':1})
            else:
                ax.plot([0, value], [index, index], color=color, lw=1.3)
                ax.scatter([value], [index], color=color, s=24, zorder=3)
            plotted.append({'pair_id': pair['pair_id'], 'question_id': pair['question_id'],
                            'label': label, 'metric': metric, 'delta_alternative_minus_baseline': value,
                            'technical_pair_complete': complete, 'formal_eligible': False})
        ax.set_title(metric)
        ax.set_xlim(-.8, .4)
        ax.set_xticks([-.8, -.4, 0, .4])
        ax.grid(axis='x', alpha=.15)
        ax.set_xlabel('Alternative − baseline')
    axes[0].set_yticks(range(len(pairs)), [f"q{p['question_id']} / {'Chat' if 'deepseek-chat' in p['pair_id'] else 'Reasoner'}" for p in pairs])
    axes[0].invert_yaxis()
    fig.suptitle('Provisional FDISCO / PEGASOS answer comparisons', y=.97, fontsize=11)
    fig.text(.5, .025, f"{summary['technical_completed_candidate_pairs']}/6 complete pipeline pairs shown; 0 confirmed route pairs. Known partial fields retained separately.\n9 source answers, 3 questions, 1 task family; shared baselines and different generators. No causal route effect.", ha='center', fontsize=8)
    fig.subplots_adjust(left=.16, right=.985, top=.83, bottom=.24, wspace=.22)
    path = output / 'alternative_development_pairs'
    table(path.with_suffix('.csv'), plotted)
    formats(fig, path)
    control_source, control_rows = current_controls(output)
    stability_source, stability_rows = current_stability(output)
    write(output / 'supplement_plot_run.json', {
        'command': f'{sys.executable} scripts/cce_supplement_plots.py',
        'inputs': {str(p): filehash(p) for p in [old_path, new_path, pair_path, summary_path, control_source, stability_source]},
        'script_sha256': filehash(__file__), 'new_model_requests': 0,
        'reference_version_answers': len(rows), 'alternative_plot_rows': len(plotted),
        'technical_complete_pairs': summary['technical_completed_candidate_pairs'],
        'confirmed_route_pairs': 0, 'control_plot_rows': control_rows,
        'stability_plot_rows': stability_rows, 'visual_qa': 'pending_image_inspection'})
    print({'reference_metric_changes': changes, 'alternative_complete_pairs': summary['technical_completed_candidate_pairs'], 'output': str(output)})


if __name__ == '__main__':
    main()
