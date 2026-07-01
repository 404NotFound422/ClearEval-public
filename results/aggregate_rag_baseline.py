"""
aggregate_rag_baseline.py
=========================
Reporting view for the inference-time KB-RAG / self-check baseline (Section 4.5).
Mirrors results/aggregate_oeq.py + results/calculate_main_table_score.py exactly, then
adds the Effectiveness sub-scores (S_method / S_label / S_trans / S_time) and the delta
vs each model's own 1-shot baseline -- so we can see WHERE grounding helps (esp. S_label).

Reads dataset/Q+AR/result/evaluation_results_{model}_{setting}.json.
Prints a per-model x per-setting table and writes results/rag_baseline_summary.csv.

Usage:
  python results/aggregate_rag_baseline.py
  python results/aggregate_rag_baseline.py --result-dir dataset/Q+AR/result
"""
import argparse
import json
import os

MAX_SCORES = {
    'c_step': 2, 'c_param': 3, 'co_order': 3, 'co_method': 2,
    'co_param': 2, 'co_chem': 1, 's_method': 2.5, 's_label': 6,
    's_trans': 3, 's_time': 3,
}

MODELS = ['openai_gpt-5.2-fast', 'openai_qwen3-max', 'openai_qwen3-14b']
SETTINGS = [
    ('1-shot', '{m}_1-shot'),
    ('1-shot+KB-RAG', '{m}_1-shot+KB-RAG'),
    ('1-shot+KB-RAG+self-check', '{m}_1-shot+KB-RAG+self-check'),
]


def _iter_scores(item):
    """Yield (metric, value) for a single evaluation item, or nothing if it errored."""
    ev = item.get('evaluation', {})
    if not isinstance(ev, dict) or ev.get('_error'):
        return
    scores = ev.get('scores', {})
    for block, metrics in (
        ('completeness', ['c_step', 'c_param']),
        ('correctness', ['co_order', 'co_method', 'co_param', 'co_chem']),
        ('effectiveness', ['s_method', 's_label', 's_trans', 's_time']),
    ):
        blk = scores.get(block, {})
        for m in metrics:
            v = blk.get(m, {}).get('score')
            if v is not None:
                yield m, float(v)


def aggregate_file(path):
    """Return dict of normalized averages + derived indices for one result file, or None."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = data if isinstance(data, list) else [data]
    buckets = {k: [] for k in MAX_SCORES}
    n_graded = 0
    for item in items:
        pairs = list(_iter_scores(item))
        if pairs:
            n_graded += 1
        for m, v in pairs:
            buckets[m].append(v)
    if not any(buckets.values()):
        return None
    norm = {}
    for m, vals in buckets.items():
        avg = sum(vals) / len(vals) if vals else 0.0
        norm[m] = avg / MAX_SCORES[m] if MAX_SCORES[m] else 0.0
    completeness = 0.4 * norm['c_step'] + 0.6 * norm['c_param']
    correctness = (norm['co_order'] + norm['co_method'] + norm['co_param'] + norm['co_chem']) / 4
    effectiveness = max(0.0, (norm['s_method'] + norm['s_label'] + norm['s_trans'] + norm['s_time']) / 4)
    i_a = min(completeness, correctness, effectiveness)
    return {
        'n': n_graded,
        'total_items': len(items),
        'Com': completeness * 100, 'Cor': correctness * 100, 'Eff': effectiveness * 100, 'I_A': i_a * 100,
        's_method': norm['s_method'] * 100, 's_label': norm['s_label'] * 100,
        's_trans': norm['s_trans'] * 100, 's_time': norm['s_time'] * 100,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--result-dir', default='dataset/Q+AR/result')
    ap.add_argument('--csv', default='results/rag_baseline_summary.csv')
    args = ap.parse_args()

    rows = []
    for model in MODELS:
        base = None
        for label, tmpl in SETTINGS:
            token = tmpl.format(m=model)
            path = os.path.join(args.result_dir, f'evaluation_results_{token}.json')
            if not os.path.exists(path):
                continue
            agg = aggregate_file(path)
            if agg is None:
                continue
            agg['model'] = model
            agg['setting'] = label
            if label == '1-shot':
                base = agg
            agg['d_I_A'] = (agg['I_A'] - base['I_A']) if base else None
            agg['d_s_label'] = (agg['s_label'] - base['s_label']) if base else None
            rows.append(agg)

    # ---- print table ----
    hdr = f"{'model':<22} {'setting':<26} {'n':>4} {'Com':>6} {'Cor':>6} {'Eff':>6} {'I_A':>6} " \
          f"{'Smeth':>6} {'Slabel':>7} {'Strans':>7} {'Stime':>6} {'dI_A':>6} {'dSlab':>7}"
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        d_ia = f"{r['d_I_A']:+6.1f}" if r['d_I_A'] is not None else f"{'--':>6}"
        d_sl = f"{r['d_s_label']:+7.1f}" if r['d_s_label'] is not None else f"{'--':>7}"
        print(f"{r['model']:<22} {r['setting']:<26} {r['n']:>4} {r['Com']:>6.1f} {r['Cor']:>6.1f} "
              f"{r['Eff']:>6.1f} {r['I_A']:>6.1f} {r['s_method']:>6.1f} {r['s_label']:>7.1f} "
              f"{r['s_trans']:>7.1f} {r['s_time']:>6.1f} {d_ia} {d_sl}")

    # ---- csv ----
    cols = ['model', 'setting', 'n', 'total_items', 'Com', 'Cor', 'Eff', 'I_A',
            's_method', 's_label', 's_trans', 's_time', 'd_I_A', 'd_s_label']
    os.makedirs(os.path.dirname(args.csv), exist_ok=True)
    with open(args.csv, 'w', encoding='utf-8') as f:
        f.write(','.join(cols) + '\n')
        for r in rows:
            f.write(','.join('' if r.get(c) is None else (f"{r[c]:.3f}" if isinstance(r.get(c), float) else str(r.get(c))) for c in cols) + '\n')
    print(f"\nWrote {len(rows)} rows -> {args.csv}")


if __name__ == '__main__':
    main()
