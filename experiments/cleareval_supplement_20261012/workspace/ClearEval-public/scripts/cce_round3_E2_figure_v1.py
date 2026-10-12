"""Publication figure from completed frozen controlled-panel results; no inference."""
import argparse, csv, json, math, statistics, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_round3_runner_v2 as runner
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

FIELDS = [('c_param', 3, 'Cpar/3'), ('co_order', 3, 'Order/3'), ('co_method', 2, 'Method/2'),
          ('co_param', 2, 'Param/2'), ('co_chem', 1, 'Chem'), ('sr', 1, 'SR'), ('sp', 1, 'SP'),
          ('Com', 1, 'Com'), ('Cor', 1, 'Cor')]
CONDITIONS = [('numbering', 'numbering'), ('merge', 'merge'), ('necessary_step_deletion', 'deletion')]


def main(args):
    source, secondary, out = [Path(x).resolve() for x in [args.source, args.secondary, args.out]]
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    verification = runner.j.read(source / 'verification.json')
    runner.base.verify_bindings(verification['source_bindings'] + verification['output_bindings'])
    summary = runner.j.read(source / 'summary.json')
    assert summary['status'] == 'complete' and summary['observed'] == 24
    pairs = runner.j.read(source / 'paired_results.json')
    side = runner.j.read(secondary / 'summary.json')
    sv = runner.j.read(secondary / 'verification.json')
    runner.base.verify_bindings(sv['input_bindings'] + sv['outputs'])
    cells = runner.j.read(secondary / 'cells.json')
    assert len(cells) == side['planned_slots'] == 24
    table, labels = [], []
    for q in sorted({r['question_id'] for r in pairs}):
        for condition, label in CONDITIONS:
            matched = [r for r in pairs if r['question_id'] == q and r['condition'] == condition]
            assert len(matched) == 2 and all(r['observed_pair'] for r in matched)
            row = {'question_id': q, 'condition': condition, 'repeats': 2}
            for key, divisor, _ in FIELDS:
                values = [r['deltas'][key] for r in matched]
                row[key + '_raw_mean_delta'] = statistics.mean(values) if all(runner.finite(v) for v in values) else None
                row[key + '_display_delta'] = row[key + '_raw_mean_delta'] / divisor if row[key + '_raw_mean_delta'] is not None else None
            table.append(row)
            labels.append(f'q{q} / {label}')
    matrix = np.array([[r[k + '_display_delta'] if r[k + '_display_delta'] is not None else np.nan for k, _, _ in FIELDS] for r in table])
    coverage = {'primary': [sum(runner.finite(c['primary_metrics'][k]) for c in cells) for k in ['s_label', 's_time']] + [sum(c['original_complete_CCE'] for c in cells)],
                'secondary': [sum(runner.finite(c['secondary_metrics'][k]) for c in cells) for k in ['s_label', 's_time']] + [sum(c['secondary_complete_CCE'] for c in cells)]}
    out.mkdir(parents=True)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'], 'font.size': 8,
        'axes.labelsize': 8, 'xtick.labelsize': 7, 'ytick.labelsize': 7, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    for gray in [False, True]:
        fig = plt.figure(figsize=(7.2, 5.9))
        gs = fig.add_gridspec(2, 2, width_ratios=[1, .035], height_ratios=[3.1, 1], left=.195, right=.94, bottom=.10, top=.88, hspace=.43, wspace=.04)
        a = fig.add_subplot(gs[0, 0]); color_axis = fig.add_subplot(gs[0, 1]); b = fig.add_subplot(gs[1, 0])
        cmap = LinearSegmentedColormap.from_list('signed_delta', ['#555555', '#FFFFFF', '#BBBBBB'] if gray else ['#0072B2', '#FFFFFF', '#D55E00'])
        cmap.set_bad('#CCCCCC')
        im = a.imshow(matrix, cmap=cmap, vmin=-1, vmax=1, aspect='auto', interpolation='nearest')
        a.set_xticks(range(len(FIELDS)), [v[2] for v in FIELDS])
        a.set_yticks(range(len(labels)), labels)
        for i in range(len(labels)):
            for j in range(len(FIELDS)):
                val = matrix[i, j]
                label = 'NA' if not math.isfinite(val) else ('0' if abs(val) < 1e-12 else f'{val:+.2f}')
                a.text(j, i, label, ha='center', va='center', fontsize=7, color='white' if abs(val) > .65 else 'black')
        for y in [2.5, 5.5]: a.axhline(y, color='black', linewidth=.8)
        a.axvline(4.5, color='black', linewidth=.8)
        a.axvline(6.5, color='black', linewidth=.8)
        a.set_title('A  Paired change: edited answer minus baseline', loc='left', fontsize=9, pad=8)
        cb = fig.colorbar(im, cax=color_axis, ticks=[-1, -.5, 0, .5, 1]); cb.ax.tick_params(labelsize=7)
        positions = np.arange(3)
        for offset, scope, color, hatch in [(-.18, 'primary', '#555555' if gray else '#0072B2', ''),
                                            (.18, 'secondary', '#BBBBBB' if gray else '#D55E00', '//')]:
            bars = b.bar(positions + offset, coverage[scope], .34, color=color, hatch=hatch, edgecolor='black', linewidth=.4,
                         label='Original primary' if scope == 'primary' else 'Applicable-channel secondary')
            for bar, count in zip(bars, coverage[scope]): b.text(bar.get_x() + bar.get_width()/2, count + .6, str(count), ha='center', fontsize=7)
        b.set_xticks(positions, ['Label score', 'Time score', 'Complete CCE'])
        b.set(ylim=(0, 27), ylabel='Available / 24')
        b.set_yticks([0, 8, 16, 24]); b.spines[['top', 'right']].set_visible(False)
        b.set_title('B  Numeric availability on the same 24 calls', loc='left', fontsize=9, pad=8)
        b.legend(loc='upper right', fontsize=7, frameon=False, ncol=1, bbox_to_anchor=(1.02, 1.03))
        fig.suptitle('Controlled validation: 3 exposed tasks, 2 calls per full answer', fontsize=10, y=.985)
        fig.text(.195, .94, 'Direct components are scaled for display; original SR/SP and scoring formulas are retained.', fontsize=7)
        fig.text(.195, .025, 'Paired deltas average two repeats. Counts are availability, not accuracy. No population CI is implied.', fontsize=7)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for axis in [a, b, color_axis]:
            bb = axis.get_tightbbox(renderer)
            assert bb.x0 >= 0 and bb.y0 >= 0 and bb.x1 <= fig.bbox.width and bb.y1 <= fig.bbox.height
        stem = 'controlled_validation_grayscale' if gray else 'controlled_validation'
        for ext in (['png'] if gray else ['pdf', 'svg', 'png']): fig.savefig(out / (stem + '.' + ext), dpi=300, facecolor='white')
        plt.close(fig)
    runner.save_once(out / 'plotted_deltas.json', table)
    runner.save_once(out / 'plotted_availability.json', coverage)
    with (out / 'plotted_deltas.csv').open('x', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    runner.save_once(out / 'verification.json', {'status': 'numeric_and_layout_checks_pass', 'size_inches': [7.2, 5.9],
        'raster_dpi': 300, 'fonts_minimum_pt': 7, 'new_model_calls': 0, 'grayscale_rendered': True,
        'source_bindings': [runner.bind(__file__), runner.bind(source / 'summary.json'), runner.bind(source / 'paired_results.json'),
            runner.bind(secondary / 'cells.json'), runner.bind(secondary / 'summary.json')],
        'outputs': [runner.bind(p) for p in sorted(out.iterdir()) if p.is_file()],
        'actual_command': [sys.executable, *sys.argv]})
    print(json.dumps({'status': 'rendered', 'out': str(out), 'new_model_calls': 0}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--secondary', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    main(p.parse_args())
