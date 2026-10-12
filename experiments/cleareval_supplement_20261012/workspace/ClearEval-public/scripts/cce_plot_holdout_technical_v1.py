"""Plot only frozen holdout technical outcomes, without reading heldout content."""
from pathlib import Path
import csv
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_analysis as a

BASE = ROOT / 'artifacts/cce_validation'
SOURCE = BASE / 'judges/holdout_failure_audit_v1/summary.json'
OUT = BASE / 'figures_followup_after104'


def main():
    s = a.load(SOURCE)
    assert s['actual_trials'] == 15 and s['failed_original_gates_reproduced'] == 8
    assert s['successful_cells'] + s['failed_cells'] == 15
    causes = s['technical_failure_classifications']
    assert sum(causes.values()) == 8
    OUT.mkdir(exist_ok=True)
    a.plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.labelsize': 8,
        'xtick.labelsize': 8, 'ytick.labelsize': 8, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = a.plt.subplots(1, 2, figsize=(7.4, 3.1), constrained_layout=True)
    labels = ['Loadable output', 'Rejected output']
    vals = [s['successful_cells'], s['failed_cells']]
    colors = ['#3D8595', '#BD7253']
    axes[0].bar(labels, vals, color=colors)
    axes[0].set_ylim(0, 16)
    axes[0].set_ylabel('Answers (15 fixed attempts)')
    axes[0].set_title('A  Technical completion', loc='left')
    for x, v in enumerate(vals):
        axes[0].text(x, v + .3, str(v), ha='center')
    names = ['Missing extraction fields', 'Nested score-key casing', 'Duplicate JSON key']
    keys = ['missing_extraction_fields', 'missing_score_record', 'provider_completed_but_adapter_duplicate_JSON_key']
    counts = [causes[k] for k in keys]
    axes[1].barh(names, counts, color=['#BD7253', '#C99A53', '#7B718D'])
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, 5)
    axes[1].set_xlabel('Answers (8 rejected outputs)')
    axes[1].set_title('B  First failing check', loc='left')
    for y, v in enumerate(counts):
        axes[1].text(v + .08, y, str(v), va='center')
    fig.suptitle('Frozen holdout: technical outcomes; expert fidelity review pending', fontsize=9)
    a.plot_save(fig, OUT / 'holdout_technical_outcomes')
    a.plt.close(fig)
    rows = [{'panel': 'A', 'category': label, 'count': value, 'denominator': 15}
            for label, value in zip(labels, vals)]
    rows += [{'panel': 'B', 'category': name, 'count': count, 'denominator': 8}
             for name, count in zip(names, counts)]
    a.write_csv(OUT / 'holdout_technical_outcomes.csv', rows)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    a.save(OUT / 'technical_plot_run.json', {
        'status': 'generated_awaiting_visual_check', 'data_rows': len(rows),
        'scope': 'Technical first-failure categories; not scientific accuracy or population error rates.',
        'secondary_faults_not_added_to_exclusive_counts': True,
        'all_15_provider_returns_finished_stop': s['finish_reason_counts'] == {'stop': 15},
        'source': str(SOURCE), 'source_sha256': sha(SOURCE), 'script_sha256': sha(__file__),
        'files_sha256': {p.name: sha(p) for p in OUT.glob('holdout_technical_outcomes.*')},
        'actual_command': [sys.executable, 'scripts/cce_plot_holdout_technical_v1.py'],
        'new_model_requests': 0})
    print(json.dumps({'status': 'generated', 'rows': len(rows), 'new_model_requests': 0}))


if __name__ == '__main__':
    main()
