"""Display all saved confirmation results without changing scoring or support."""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_round3_runner_v2 as runner
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

PANELS = [
    ('primary', [('sr', 1, 'SR'), ('sp', 1, 'SP'), ('Com', 1, 'Com'),
                 ('Cor', 1, 'Cor'), ('Eff', 1, 'Eff'), ('IA', 1, 'IA'), ('HV', 1, 'HV')]),
    ('secondary', [('s_label', 6, 'Label/6'), ('Eff', 1, 'Eff'), ('IA', 1, 'IA'), ('HV', 1, 'HV')])]


def display(value):
    if value is None:
        return 'NA'
    if value == 0:
        return '0'
    if 0 < value < .005:
        return '<.01'
    return f'{value:.2f}'


def main(args):
    source, out = Path(args.source).resolve(), Path(args.out).resolve()
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    verification = runner.j.read(source / 'verification.json')
    runner.base.verify_bindings(verification['source_bindings'] + verification['output_bindings'])
    summary = runner.j.read(source / 'summary.json')
    rows = sorted(runner.j.read(source / 'per_answer.json'), key=lambda r: r['anonymous_answer_id'])
    assert len(rows) == 8 and summary['status'] == 'completed_all_eight_planned_slots'
    plotted = []
    for scope, fields in PANELS:
        for row in rows:
            for key, divisor, _ in fields:
                value = row[scope + '_metrics'][key]
                assert value is None or runner.finite(value)
                scaled = None if value is None else value / divisor
                assert scaled is None or 0 <= scaled <= 1
                plotted.append({'answer_id': row['anonymous_answer_id'], 'question_id': row['question_id'],
                    'generator_model': row['model'], 'scope': scope, 'metric': key,
                    'raw_value': value, 'display_divisor': divisor, 'display_value': scaled})
    out.mkdir(parents=True)
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
        'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    labels = [r['anonymous_answer_id'] + ' / q' + str(r['question_id']) for r in rows]
    for gray in [False, True]:
        fig = plt.figure(figsize=(7.2, 4.9))
        gs = fig.add_gridspec(1, 3, width_ratios=[7, 4, .2],
            left=.16, right=.94, bottom=.25, top=.80, wspace=.20)
        axes = [fig.add_subplot(gs[0, i]) for i in [0, 1]]
        ca = fig.add_subplot(gs[0, 2])
        cmap = plt.get_cmap('Greys' if gray else 'Blues').copy()
        cmap.set_bad('#DDDDDD')
        for axis, (scope, fields) in zip(axes, PANELS):
            matrix = np.array([[np.nan if r[scope + '_metrics'][key] is None else
                r[scope + '_metrics'][key] / divisor for key, divisor, _ in fields] for r in rows])
            im = axis.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect='auto')
            axis.set_xticks(range(len(fields)), [f[2] for f in fields])
            axis.set_yticks(range(len(rows)), labels if scope == 'primary' else [])
            for i in range(len(rows)):
                for j in range(len(fields)):
                    val = matrix[i, j]
                    axis.text(j, i, display(float(val) if math.isfinite(val) else None),
                        ha='center', va='center', fontsize=7.5,
                        color='white' if val > .62 else 'black')
            axis.set_title('A  Original primary' if scope == 'primary' else 'B  Secondary candidate',
                           loc='left', fontsize=9, pad=10)
            for boundary in [1.5, 3.5, 5.5]:
                axis.axhline(boundary, color='black', linewidth=.6)
        fig.colorbar(im, cax=ca, ticks=[0, .5, 1])
        fig.suptitle('Frozen confirmation: all 8 archived answers', fontsize=11, y=.97)
        fig.text(.16, .89, '4 tasks, 4 generators; one evaluation per answer. Grey cells are NA.', fontsize=8)
        fig.text(.16, .17, 'Primary complete CCE: ' + str(summary['primary_complete_CCE']) + '/8; '
            'secondary: ' + str(summary['secondary_complete_CCE']) + '/8.', fontsize=8)
        fig.text(.16, .12, 'Only Claude and Qwen Max share the prespecified q23/q248 support.', fontsize=7.5)
        fig.text(.16, .075, 'Raw SR/SP retained. Label/6 is display scaling; secondary scores are not primary scores.', fontsize=7)
        fig.text(.16, .035, 'Availability is not accuracy. These single calls do not estimate evaluator repeatability.', fontsize=7)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for axis in [*axes, ca]:
            bb = axis.get_tightbbox(renderer)
            assert bb.x0 >= 0 and bb.y0 >= 0 and bb.x1 <= fig.bbox.width and bb.y1 <= fig.bbox.height
        stem = 'confirmation_per_answer_grayscale' if gray else 'confirmation_per_answer'
        for ext in (['png'] if gray else ['pdf', 'svg', 'png']):
            fig.savefig(out / (stem + '.' + ext), dpi=300, facecolor='white')
        plt.close(fig)
    runner.save_once(out / 'plotted_values.json', plotted)
    with (out / 'plotted_values.csv').open('x', encoding='utf8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(plotted[0]))
        writer.writeheader()
        writer.writerows(plotted)
    runner.save_once(out / 'verification.json', {'status': 'numeric_and_layout_checks_pass',
        'actual_command': [sys.executable, *sys.argv], 'source_bindings': [runner.bind(__file__),
            runner.bind(source / 'per_answer.json'), runner.bind(source / 'summary.json')],
        'outputs': [runner.bind(p) for p in sorted(out.iterdir())], 'new_model_calls': 0,
        'scores_changed': False, 'all_eight_answers_displayed': True, 'raster_dpi': 300})
    print(json.dumps({'out': str(out), 'answers': len(rows), 'new_model_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    main(parser.parse_args())
