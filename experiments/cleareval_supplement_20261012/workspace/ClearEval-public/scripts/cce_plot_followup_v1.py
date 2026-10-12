"""Plot the actual q2 route pair and the six-call prompt intervention."""
from pathlib import Path
import csv
import io
import json
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_judges as j
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'figures_followup_v1'
OUT.mkdir(exist_ok=True)
PAIR = BASE / 'judges/local_alternative_q2_v1/paired_results.json'
NEW = BASE / 'judges/stability_remediation_plan_v1/per_observation.json'
OLD = BASE / 'judges/local_stability_supplement_v2/per_observation.json'
EXAMPLE = BASE / 'judges/stability_remediation_plan_v1/original_final_example.json'
pair = j.read(PAIR)[0]
new = j.read(NEW)
old = [r for r in j.read(OLD) if r['judge'] == 'local_llama3_8b']
assert len(new) == len(old) == 6
assert pair['technical_pipeline_complete'] and pair['same_frozen_configuration']
assert all(pair['metrics'][m][s] is None for m in ['Eff', 'IA', 'HV'] for s in ['baseline', 'alternative'])
rows = []
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.labelsize': 9, 'svg.fonttype': 'none', 'pdf.fonttype': 42})
fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), gridspec_kw={'width_ratios': [1, 1.25]})
ax = axes[0]
labels = ['SR', 'SP', 'Com', 'Cor']
colors = ['#0072B2', '#D55E00']
for i, metric in enumerate(labels):
    key = metric.lower() if metric in ['SR', 'SP'] else metric
    a, b = [pair['metrics'][key][s] for s in ['baseline', 'alternative']]
    ax.plot([a, b], [i, i], color='#999999', linewidth=1, zorder=1)
    for side, value, color, shift in [('baseline', a, colors[0], -.075), ('alternative', b, colors[1], .075)]:
        ax.scatter(value, i + shift, s=35, color=color, zorder=3, marker='o' if side == 'baseline' else 's')
        ax.text(value, i + shift - .15 if side == 'baseline' else i + shift + .20, f'{value:.3f}', fontsize=8, ha='center', va='center', color=color)
        rows.append({'panel': 'A', 'item': metric, 'condition': side, 'value': value, 'denominator': 1, 'unit': 'answer_score'})
ax.set(yticks=range(4), yticklabels=labels, xlim=(-.06, 1.1), ylim=(3.6, -.6), xlabel='Score (0–1)')
ax.set_title('A  q2: two archived route answers', loc='left', fontsize=10, pad=13)
ax.grid(axis='x', alpha=.2)
for side, color, marker, label in [('baseline', colors[0], 'o', 'Flash / FDISCO'), ('alternative', colors[1], 's', 'Claude / iDISCO+')]:
    ax.scatter([], [], color=color, marker=marker, label=label)
ax.legend(loc='upper left', bbox_to_anchor=(-.03, -.15), frameon=False, fontsize=8)
ax.text(0, -.38, 'Both answers: label compatibility NA\nEff, IA and HV therefore remain NA.', transform=ax.transAxes, fontsize=8, va='top')
for m in ['Eff', 'IA', 'HV']:
    for side in ['baseline', 'alternative']:
        rows.append({'panel': 'A', 'item': m, 'condition': side, 'value': None, 'denominator': 1, 'unit': 'answer_score'})

ax = axes[1]
checks = [
    ('Whole example copied', sum(json.loads(r['raw_teacher_content']) == j.read(EXAMPLE) for r in old), sum(r['full_old_example_copy'] for r in new)),
    ('Wrong declared route', sum(r['explicit_route_mismatch'] for r in old), sum(not r['route_matches_explicit_FDISCO'] for r in new)),
    ('Explicit GFP omitted', sum('gfp' not in j.canonical(r['extraction']['marker_dict']).casefold() for r in old), sum(r['literal_contradiction_flags']['explicit_gfp_label_absent_from_marker_dict'] for r in new)),
    ('Unsupported c-Fos', sum('c-fos' in j.canonical(r['extraction']['marker_dict']).casefold() for r in old), sum(r['literal_contradiction_flags']['unsupported_cfos_literal'] for r in new)),
    ('Explicit DBE RI differs', sum(r['extraction']['reagent_ri_value'] != (1.562 if r['question_id'] == 2 else 1.56) for r in old), sum(r['literal_contradiction_flags']['reagent_RI_disagrees_with_explicit_DBE_RI'] for r in new)),
]
for i, (label, before, after) in enumerate(checks):
    for condition, value, offset, color in [('Original prompt', before, -.18, '#777777'), ('Final schema prompt', after, .18, '#0072B2')]:
        ax.barh(i + offset, value, height=.3, color=color, label=condition if i == 0 else None)
        ax.text(value + .08, i + offset, str(value), va='center', fontsize=8)
        rows.append({'panel': 'B', 'item': label, 'condition': condition, 'value': value, 'denominator': 6, 'unit': 'actual_requests'})
ax.set(yticks=range(len(checks)), yticklabels=[x[0] for x in checks], xlim=(0, 6.65), ylim=(4.65, -.65), xticks=[0, 2, 4, 6], xlabel='Flagged requests / 6')
ax.set_title('B  Llama prompt intervention', loc='left', fontsize=10, pad=13)
ax.legend(loc='upper left', bbox_to_anchor=(-.03, -.15), frameon=False, fontsize=8)
ax.text(0, -.38, '2 fixed answers × 3 real repeats per prompt.\nZero component variation in both versions.', transform=ax.transAxes, fontsize=8, va='top')
for ax in axes:
    ax.spines[['top', 'right']].set_visible(False)
fig.subplots_adjust(left=.065, right=.98, top=.90, bottom=.32, wspace=.68)
for ext in ['png', 'svg', 'pdf']:
    fig.savefig(OUT / f'followup_results.{ext}', dpi=220, bbox_inches='tight')
plt.close(fig)
stream = io.StringIO(newline='')
w = csv.DictWriter(stream, fieldnames=list(rows[0]))
w.writeheader(); w.writerows(rows)
(OUT / 'followup_results.csv').write_text(stream.getvalue(), encoding='utf-8-sig')
j.save(OUT / 'plot_run.json', {'status': 'generated_pending_visual_inspection', 'data_rows': len(rows),
    'sources': {str(p): j.filehash(p) for p in [PAIR, NEW, OLD, EXAMPLE]}, 'script_sha256': j.filehash(__file__),
    'new_model_requests': 0, 'comparison_scope': 'Development only; different q2 generator answers; prompt intervention is one judge family, not new two-family stability.',
    'actual_command': [sys.executable, 'scripts/cce_plot_followup_v1.py']})
print(j.canonical({'status': 'generated', 'data_rows': len(rows), 'output': str(OUT)}))
