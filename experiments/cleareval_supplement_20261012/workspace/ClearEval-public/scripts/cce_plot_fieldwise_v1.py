"""Plot actual fieldwise replay tables without recomputing scores or calling models."""
from __future__ import annotations
import argparse, csv, hashlib, json, math, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_plot_round2_controls_v11 as style


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def bind(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def table(path, rows):
    with path.open('w', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); source = args.source.resolve(); out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [source / p for p in ['cohort_summary.json', 'paired_results.json', 'cells.json', 'run_config.json']]
    bindings = [bind(p) for p in paths]
    summaries, all_pairs, cells, config = [read(p) for p in paths]
    pairs = [p for p in all_pairs if p['processing'] == 'revised']
    ids = list(dict.fromkeys(p['pair_id'] for p in sorted(pairs, key=lambda p: (style.CONDITIONS.index(p['condition']), p['question_id']))))
    assert len(ids) == 15 and len([c for c in cells if c['cohort'] == 'E2']) == 21
    plt, mpl = style.style()
    names = {'development': 'Development', 'E2': 'Controlled answers', 'Qwen_repeats': 'Qwen repeat returns'}
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    fig.subplots_adjust(left=.26, right=.88, bottom=.20, top=.79)
    for i, row in enumerate(summaries):
        n = row['actual_raw_returns']
        before, after = row['original_complete_CCE'], row['revised_complete_CCE']
        ax.barh(i-.16, before/n, .28, color=style.ORANGE, hatch='//', label='v11 before repair' if i == 0 else None)
        ax.barh(i+.16, after/n, .28, color=style.BLUE, label='Fieldwise processing' if i == 0 else None)
        ax.text(before/n+.025, i-.16, f'{before}/{n}', va='center', fontsize=9)
        ax.text(after/n+.025, i+.16, f'{after}/{n}', va='center', fontsize=9)
    ax.set_yticks(range(3), [names[r['cohort']] for r in summaries]); ax.invert_yaxis()
    ax.set_xlim(0, 1.08); ax.set_xticks([0, .25, .5, .75, 1]); ax.set_xlabel('Fraction with complete numeric CCE')
    ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('Scoring availability on the same actual returns', fontsize=12, y=.97)
    fig.legend(loc='upper center', bbox_to_anchor=(.56, .90), ncol=2, frameon=False, fontsize=9)
    fig.text(.5, .025, '40 stored returns; 0 new requests. One cancelled repeat has no return and is reported separately.', ha='center', fontsize=8)
    style.export(fig, out, 'availability_restored'); plt.close(fig)
    metrics = ['Com', 'Cor', 'Eff', 'sr', 'c_param', 'co_order']
    labels = dict(zip(style.CONDITIONS, ['Step deletion', 'Parameter deletion', 'Numbering', 'Order conflict', 'Entry merge']))
    fig, axes = plt.subplots(2, 3, figsize=(10.8, 9.5))
    fig.subplots_adjust(left=.17, right=.95, bottom=.10, top=.86, wspace=.42, hspace=.30)
    fig.suptitle('Controlled comparisons after fieldwise processing', fontsize=13, y=.98)
    fig.text(.5, .942, '15 pairs from 3 exposed base answers; baseline and variant use the same processing', ha='center', fontsize=9)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], marker='o', linestyle='', color=style.BLUE, markerfacecolor='white'),
                Line2D([], [], marker='s', linestyle='', color=style.ORANGE)], ['Baseline', 'Edited answer'],
               loc='upper center', bbox_to_anchor=(.5, .923), frameon=False, ncol=2, fontsize=9)
    plotted = []
    for panel, (ax, metric) in enumerate(zip(axes.flat, metrics)):
        rows = [next(p for p in pairs if p['pair_id'] == pid and p['metric'] == metric) for pid in ids]
        finite = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        n = sum(finite(p['baseline']) and finite(p['variant']) for p in rows)
        scale = 3 if metric in ['c_param', 'co_order'] else 1
        ax.set_title(f'{chr(97+panel)}  {metric.upper() if metric == "sr" else metric} ({n}/15 pairs)', loc='left', fontweight='bold', fontsize=10)
        ax.set_xlim(-.05*scale, 1.05*scale); ax.set_ylim(14.8, -.8)
        ax.set_xticks([0, 1, 2, 3] if scale == 3 else [0, .25, .5, .75, 1])
        ticks = [f'{labels[p["condition"]]} / q{p["question_id"]}' if panel % 3 == 0 else f'q{p["question_id"]}' for p in rows]
        ax.set_yticks(range(15), ticks); ax.tick_params(axis='y', length=0)
        ax.set_xlabel('Original metric scale'); ax.grid(axis='x', color='#dddddd', lw=.5)
        ax.spines[['top', 'right', 'left']].set_visible(False)
        for y, p in enumerate(rows):
            a, b = p['baseline'], p['variant']
            if finite(a) and finite(b): ax.plot([a, b], [y-.12, y+.12], color='#888888', lw=.8)
            for val, marker, color, offset, arm in [(a, 'o', style.BLUE, -.12, 'B'), (b, 's', style.ORANGE, .12, 'V')]:
                if finite(val):
                    ax.scatter(val, y+offset, s=20, marker=marker, edgecolors=color, facecolors='white' if arm == 'B' else color, zorder=3)
                elif not finite(a) and not finite(b):
                    if arm == 'B': ax.text(1.065, y, 'B,V:NA', transform=ax.get_yaxis_transform(), fontsize=7, va='center', color='#555555')
                else:
                    ax.text(1.065, y+offset, arm+':NA', transform=ax.get_yaxis_transform(), fontsize=7, va='center', color=color)
            plotted.append(p)
    fig.text(.5, .045, 'NA remains missing. SR is unchanged. Pairs share base answers; no independence or significance is implied.', ha='center', fontsize=8)
    fig.text(.5, .024, 'These are posthoc processing repairs on actual model returns, awaiting expert review.', ha='center', fontsize=8)
    style.export(fig, out, 'controlled_pairs'); plt.close(fig)
    table(out/'availability_restored.csv', summaries); table(out/'controlled_pairs.csv', plotted)
    assert bindings == [bind(p) for p in paths]
    meta = {'actual_command': [sys.executable, *sys.argv], 'inputs': bindings, 'script': bind(Path(__file__)),
            'new_model_requests': 0, 'scores_recomputed': False, 'PNG_dpi': 300,
            'formats': ['PNG', 'SVG', 'PDF'], 'canvas_text_boundary_check': 'pass', 'visual_review': 'pending',
            'error_bars': 'None: descriptive counts and paired individual values, not independent population estimates.'}
    (out/'provenance.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    (out/'CAPTION.md').write_text('These figures compare v11 processing before repair with revised fieldwise processing of the same actual returns. The zero complete-CCE counts refer to this v11 batch, not the historical ClearEval corpus. Complete CCE requires finite Com, Cor, and Eff. The repeat denominator is 14 actual returns; one cancelled slot remains in the 15-slot experiment record. Development and repeat rows overlap in answer identity and must not be pooled as independent answers. Controlled comparisons retain all 15 pairs and all missing values. All original SR/SP values and scoring formulas are retained. No new judge request, significance test, or scientific validity claim is made. Error bars are not applicable to these descriptive counts and individual paired values.\n', encoding='utf8')
    print(json.dumps({'status': 'rendered', 'out': str(out)}))


if __name__ == '__main__': main()
