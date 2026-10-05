"""
aggregate_rag_baseline.py
=========================
Reporting view for the inference-time KB-RAG / self-check baseline (Section 4.5).
Uses the shared protocol-level aggregation in results/oeq_metrics.py, then
adds the Effectiveness sub-scores (S_method / S_label / S_trans / S_time) and the delta
vs each model's own 1-shot baseline -- so we can see WHERE grounding helps (esp. S_label).

Reads dataset/Q+AR/result_scoring_v2/evaluation_results_{model}_{setting}.json.
Reports paired deltas on common valid IDs and retains the old min-of-means diagnostic.
Writes results/rag_baseline_summary_scoring_v2.csv without changing historical tables.

Usage:
  python results/aggregate_rag_baseline.py
  python results/aggregate_rag_baseline.py --result-dir dataset/Q+AR/result
"""
import argparse
import json
import os
import csv
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from .oeq_metrics import paired_deltas
    from .aggregate_oeq import aggregate_file as checked_aggregate
except ImportError:
    from results.oeq_metrics import paired_deltas
    from results.aggregate_oeq import aggregate_file as checked_aggregate

MODELS = ['openai_gpt-5.2-fast', 'openai_qwen3-max', 'openai_qwen3-14b']
SETTINGS = [
    ('1-shot', '{m}_1-shot'),
    ('1-shot+KB-RAG', '{m}_1-shot+KB-RAG'),
    ('1-shot+KB-RAG+self-check', '{m}_1-shot+KB-RAG+self-check'),
]


def aggregate_file(path):
    """Return normalized averages + derived indices; failed runs retain their coverage."""
    agg = checked_aggregate(path, model_name="rag-condition")
    return {
        'n': agg['sample_count'], 'total_items': agg['total_items'],
        'coverage': agg['coverage'], 'n_excluded': len(agg['excluded_items']),
        'aggregation_version': agg['aggregation_version'],
        **{key: value * 100 if value is not None else None for key, value in agg['indices'].items()},
        **{key: agg[key] for key in SCOPE_FIELDS},
    }


SCOPE_FIELDS = ('scoring_contract_sha256', 'scoring_contract', 'provenance_status',
                'scoring_status_counts', 'score_interpretation_counts',
                'scientific_status_counts', 'reporting_note', 'workflow_diagnostics_summary', 'robustness_summary')


def checked_pair(baseline, treatment, baseline_stats, treatment_stats):
    """Different settings may have different hashes; their scoring basis must match."""
    left = baseline_stats.get('scoring_contract')
    right = treatment_stats.get('scoring_contract')
    left_hash = baseline_stats.get('scoring_contract_sha256')
    right_hash = treatment_stats.get('scoring_contract_sha256')
    if bool(left_hash) != bool(right_hash):
        raise ValueError("Cannot pair versioned and unversioned scoring runs")
    if left_hash and right_hash:
        if left is not None and right is not None:
            basis = lambda contract: {key: value for key, value in contract.items()
                                      if key not in ('model', 'setting')}
            if basis(left) != basis(right):
                raise ValueError("Cannot pair different scoring contract versions")
        elif left_hash != right_hash:
            raise ValueError("Cannot establish compatible scoring contract versions without manifests")
    return paired_deltas(baseline, treatment)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--result-dir', default='dataset/Q+AR/result_scoring_v2')
    ap.add_argument('--models', nargs='+', default=MODELS)
    ap.add_argument('--csv', default='results/rag_baseline_summary_scoring_v2.csv')
    args = ap.parse_args()

    rows = []
    for model in args.models:
        base_items = None
        base_stats = None
        for label, tmpl in SETTINGS:
            token = tmpl.format(m=model)
            path = os.path.join(args.result_dir, f'evaluation_results_{token}.json')
            if not os.path.exists(path):
                continue
            agg = aggregate_file(path)
            agg['model'] = model
            agg['setting'] = label
            with open(path, encoding='utf-8') as f:
                items = json.load(f)
            if isinstance(items, dict):
                items = [items]
            if label == '1-shot':
                base_items = items
                base_stats = agg
            agg.update(checked_pair(base_items, items, base_stats, agg) if base_items is not None else
                       {'n_paired': 0, 'd_I_A': None, 'd_s_label': None})
            rows.append(agg)

    # ---- print table ----
    hdr = f"{'model':<22} {'setting':<26} {'n':>4} {'Com':>6} {'Cor':>6} {'Eff':>6} {'I_A':>6} " \
          f"{'Smeth':>6} {'Slabel':>7} {'Strans':>7} {'Stime':>6} {'dI_A':>6} {'dSlab':>7}"
    print('Automated estimates are not scientific certification; paired runs must share a scoring basis.')
    print(hdr)
    print('-' * len(hdr))
    def fmt(value, width=6):
        return f'{value:{width}.1f}' if value is not None else f"{'--':>{width}}"
    for r in rows:
        d_ia = f"{r['d_I_A']:+6.1f}" if r['d_I_A'] is not None else f"{'--':>6}"
        d_sl = f"{r['d_s_label']:+7.1f}" if r['d_s_label'] is not None else f"{'--':>7}"
        print(f"{r['model']:<22} {r['setting']:<26} {r['n']:>4} {fmt(r['Com'])} {fmt(r['Cor'])} "
              f"{fmt(r['Eff'])} {fmt(r['I_A'])} {fmt(r['s_method'])} {fmt(r['s_label'], 7)} "
              f"{fmt(r['s_trans'], 7)} {fmt(r['s_time'])} {d_ia} {d_sl}")

    # ---- csv ----
    cols = ['model', 'setting', 'n', 'total_items', 'coverage', 'n_excluded',
            'Com', 'Cor', 'Eff', 'I_A', 'I_A_min_of_means',
            's_method', 's_label', 's_trans', 's_time', 'n_paired', 'd_I_A', 'd_s_label',
            'aggregation_version', *SCOPE_FIELDS]
    os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
    with open(args.csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows({key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                          if isinstance(value, (dict, list)) else value
                          for key, value in row.items()} for row in rows)
    print(f"\nWrote {len(rows)} rows -> {args.csv}")


if __name__ == '__main__':
    main()
