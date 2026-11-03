"""Compare frozen real-pilot representations and matching policies."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from .operations import field_score, containment

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text(encoding='utf8'))


def dump(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def assignment(scores, threshold, ordered=False):
    n, m = scores.shape
    gains = scores - threshold
    if ordered:
        dp = np.zeros((n + 1, m + 1))
        for i in range(n):
            for j in range(m):
                dp[i + 1, j + 1] = max(dp[i, j + 1], dp[i + 1, j], dp[i, j] + max(0, gains[i, j]))
        matches = []
        i, j = n, m
        while i and j:
            if gains[i - 1, j - 1] > 0 and abs(dp[i, j] - dp[i - 1, j - 1] - gains[i - 1, j - 1]) < 1e-9:
                matches.append((i - 1, j - 1))
                i, j = i - 1, j - 1
            elif dp[i - 1, j] >= dp[i, j - 1]:
                i -= 1
            else:
                j -= 1
        return sorted(matches)
    padded = np.concatenate([gains, np.zeros((n, n))], axis=1)
    rr, cc = linear_sum_assignment(-padded)
    return [(int(i), int(j)) for i, j in zip(rr, cc) if j < m and gains[i, j] > 0]


def metrics(rows):
    positive = [r for r in rows if r['gold_candidates']]
    absent = [r for r in rows if not r['gold_candidates']]
    accepted = [r for r in rows if r['accepted']]
    tp = sum(r['selected_correct'] for r in rows)
    return {'reference_n': len(rows), 'positive_n': len(positive), 'absent_n': len(absent),
            'recall_at_1': sum(r['rank'] == 1 for r in positive) / len(positive),
            'recall_at_3': sum(r['rank'] is not None and r['rank'] <= 3 for r in positive) / len(positive),
            'recall_at_5': sum(r['rank'] is not None and r['rank'] <= 5 for r in positive) / len(positive),
            'mrr': sum(1 / r['rank'] if r['rank'] else 0 for r in positive) / len(positive),
            'accepted': len(accepted), 'true_accepted': tp,
            'precision': tp / len(accepted) if accepted else None,
            'recall': tp / len(positive),
            'false_accept_absent': sum(r['accepted'] for r in absent),
            'false_accept_absent_rate': sum(r['accepted'] for r in absent) / len(absent) if absent else None,
            'unavailable_rows': sum(r['top_candidate'] is None for r in rows)}


def calibrate(rows):
    available = [r['top_score'] for r in rows if r['top_candidate'] is not None]
    if not available:
        return 2.0
    # Candidate operating points are fixed by development top scores; > accepts.
    candidates = sorted({s - 1e-8 for s in available} | {max(available) + 1e-8})
    positives = sum(bool(r['gold_candidates']) for r in rows)
    options = []
    for t in candidates:
        accepted = [r for r in rows if r['top_candidate'] is not None and r['top_score'] > t]
        tp = sum(r['top_candidate'] in r['gold_candidates'] for r in accepted)
        fp, fn = len(accepted) - tp, positives - tp
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0
        options.append((f1, t))
    return max(options)[1]


def functional_role(op):
    materials = set(op['primary_materials'])
    if 'dcm' in materials:
        return 'delipidation'
    if materials & {'methanol', 'ethanol', 'thf', 'tert_butanol'}:
        return 'dehydration'
    if materials & {'dbe', 'babb', 'babb_d4', 'babb_d10', 'babb_d15', 'bb_peg'}:
        return 'ri_matching'
    return op['phase']


def diagnostic_score(a, b):
    if functional_role(a) != functional_role(b) or b['phase'] in {'labeling', 'pretreatment', 'storage', 'mounting'}:
        return -1.0
    va, vb = list(a['concentrations'].values()), list(b['concentrations'].values())
    concentration = max(0, 1 - abs(va[0] - vb[0]) / 100) if len(va) == len(vb) == 1 else .7
    am, bm = set(a['primary_materials']), set(b['primary_materials'])
    chemical = len(am & bm) / len(am | bm) if am and bm else 0
    return .2 * (a['action'] == b['action']) + .6 * concentration + .2 * chemical


def main():
    locks = read('experiment_lock.json')
    for name, digest in locks['sha256'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    inp, annotations, nodes = read('inputs.json'), read('annotations.json'), read('operations.json')
    vectors = {}
    for model in ('mpnet', 'biosimcse'):
        v = np.load(HERE / 'predictions' / f'{model}.npz', allow_pickle=False)
        vectors[model] = dict(zip(v['ids'].tolist(), v['embeddings']))
    raw_rows, matrices, gold_capacities, metadata = [], {}, {}, {}
    for c in inp['cases']:
        cid = c['id']
        rids = [cid + ':R:' + s['id'] for s in c['reference_steps']]
        cids = [cid + ':C:' + s['id'] for s in c['candidate_steps']]
        short_r, short_c = [nodes[k]['id'] for k in rids], [nodes[k]['id'] for k in cids]
        gold = annotations['correspondences'][cid]
        gold_matrix = np.array([[float(j in gold[i]) for j in short_c] for i in short_r])
        gold_capacities[cid] = len(assignment(gold_matrix, .5))
        metadata[cid] = {'method': c['method'], 'references': short_r, 'candidates': short_c,
                         'positive_references': sum(bool(v) for v in gold.values()), 'gold_one_to_one_capacity': gold_capacities[cid],
                         'candidate_chinese_n': sum(nodes[k]['contains_chinese'] for k in cids)}
        for model in vectors:
            for representation in ('raw', 'context', 'typed', 'ledger'):
                name = model + '_' + representation
                matrix = np.array([[vectors[model][r + '|' + representation] @ vectors[model][q + '|' + representation] for q in cids] for r in rids])
                if representation == 'ledger':
                    for i, rid in enumerate(rids):
                        for j, qid in enumerate(cids):
                            if not all(nodes[k]['ledger_nominal']['action'] and nodes[k]['ledger_nominal']['primary_materials'] for k in [rid, qid]):
                                matrix[i, j] = -2
                matrices.setdefault(name, {})[cid] = matrix
        for variant in ('identity', 'joint', 'strict'):
            matrices.setdefault('typed_fields_' + variant, {})[cid] = np.array([[field_score(nodes[r]['typed'], nodes[q]['typed'], variant) for q in cids] for r in rids])
        for variant in ('raw', 'nominal'):
            matrices.setdefault('ledger_fields_' + variant, {})[cid] = np.array([[field_score(nodes[r]['ledger_' + variant], nodes[q]['ledger_' + variant], 'joint')
                if all(nodes[k]['ledger_' + variant]['action'] and nodes[k]['ledger_' + variant]['primary_materials'] for k in [r, q]) else -2 for q in cids] for r in rids])

    for method, case_matrices in matrices.items():
        for cid, matrix in case_matrices.items():
            md, gold = metadata[cid], annotations['correspondences'][cid]
            for i, rid in enumerate(md['references']):
                order = sorted([j for j in range(len(md['candidates'])) if matrix[i, j] > -1], key=lambda j: (-matrix[i, j], j))
                top = md['candidates'][order[0]] if order else None
                top_score = float(matrix[i, order[0]]) if order else -2
                rank = next((n + 1 for n, j in enumerate(order) if md['candidates'][j] in gold[rid]), None)
                raw_rows.append({'method': method, 'case': cid, 'reference': rid, 'gold_candidates': gold[rid],
                                 'top_candidate': top, 'top_score': top_score, 'rank': rank,
                                 'accepted': top is not None and top_score > .7,
                                 'selected_correct': top in gold[rid] and top_score > .7})
    results = {}
    for method, case_matrices in matrices.items():
        group = [r for r in raw_rows if r['method'] == method]
        fixed = metrics(group)
        calibrated_rows = []
        thresholds, global_rows, ordered_rows, match_details = {}, [], [], {}
        for cid, matrix in case_matrices.items():
            thresholds[cid] = calibrate([r for r in group if r['case'] != cid])
            t = thresholds[cid]
            for row in (r for r in group if r['case'] == cid):
                q = dict(row)
                q['accepted'] = q['top_candidate'] is not None and q['top_score'] > t
                q['selected_correct'] = q['accepted'] and q['top_candidate'] in q['gold_candidates']
                calibrated_rows.append(q)
            md = metadata[cid]
            gold = annotations['correspondences'][cid]
            details = {}
            for label, ordered, out in [('global', False, global_rows), ('ordered', True, ordered_rows)]:
                pairs = assignment(matrix, t, ordered=ordered)
                decisions = [{'reference': md['references'][i], 'candidate': md['candidates'][j], 'score': float(matrix[i, j]),
                              'correct': md['candidates'][j] in gold[md['references'][i]]} for i, j in pairs]
                details[label] = decisions
                out.append({'case': cid, 'accepted': len(decisions), 'correct': sum(d['correct'] for d in decisions),
                            'false_on_absent': sum(not gold[d['reference']] for d in decisions), 'gold_capacity': gold_capacities[cid]})
            match_details[cid] = details
        def match_summary(items):
            accepted, correct, capacity = (sum(r[k] for r in items) for k in ('accepted', 'correct', 'gold_capacity'))
            return {'accepted': accepted, 'correct': correct, 'gold_capacity': capacity,
                    'precision': correct / accepted if accepted else None, 'capacity_recall': correct / capacity,
                    'false_on_absent': sum(r['false_on_absent'] for r in items)}
        per_case = {cid: metrics([r for r in group if r['case'] == cid]) for cid in metadata}
        results[method] = {'fixed_threshold': fixed, 'loco_calibrated': metrics(calibrated_rows),
                           'thresholds': thresholds, 'global_loco': match_summary(global_rows), 'ordered_loco': match_summary(ordered_rows),
                           'case_macro_recall_at_1': sum(v['recall_at_1'] for v in per_case.values()) / len(per_case),
                           'per_case': per_case, 'matches': match_details}

    extraction = {}
    for side in ('reference', 'candidate'):
        chosen = [n for n in nodes.values() if n['side'] == side]
        extraction[side] = {}
        for language in ('all', 'chinese', 'non_chinese'):
            subset = [n for n in chosen if language == 'all' or n['contains_chinese'] == (language == 'chinese')]
            extraction[side][language] = {'n': len(subset)}
            for version in ('raw', 'nominal'):
                extraction[side][language][version] = {
                    'model_has_Action': sum(n['ledger_' + version + '_action_count'] > 0 for n in subset),
                    'adapter_has_action': sum(n['ledger_' + version]['action'] is not None for n in subset),
                    'adapter_has_material': sum(bool(n['ledger_' + version]['primary_materials']) for n in subset),
                    'usable_action_and_material': sum(bool(n['ledger_' + version]['action'] and n['ledger_' + version]['primary_materials']) for n in subset)}
            extraction[side][language]['typed'] = {'usable_action_and_material': sum(bool(n['typed']['action'] and n['typed']['primary_materials']) for n in subset)}

    conditions = []
    for p in annotations['explicit_condition_pairs']:
        a = nodes[p['case'] + ':R:' + p['reference']]['typed'][p['field']]
        b = nodes[p['case'] + ':C:' + p['candidate']]['typed'][p['field']]
        conditions.append({**p, 'reference_value': a, 'candidate_value': b, 'predicted': containment(a, b)})

    cid = 'EXPAND_026'
    md = metadata[cid]
    diag = np.array([[diagnostic_score(nodes[cid + ':R:' + r]['typed'], nodes[cid + ':C:' + q]['typed']) for q in md['candidates']] for r in md['references']])
    diag_pairs = assignment(diag, .5)
    diagnostic = [{'reference': md['references'][i], 'candidate': md['candidates'][j], 'score': float(diag[i, j]),
                   'same_material': nodes[cid + ':R:' + md['references'][i]]['typed']['primary_materials'] == nodes[cid + ':C:' + md['candidates'][j]]['typed']['primary_materials'],
                   'duration': containment(nodes[cid + ':R:' + md['references'][i]]['typed']['duration'], nodes[cid + ':C:' + md['candidates'][j]]['typed']['duration']),
                   'target_match': annotations['diagnostic_targets_EXPAND_026'].get(md['references'][i]) == md['candidates'][j]} for i, j in diag_pairs]

    span_checks = 0
    for node in nodes.values():
        op, text = node['typed'], node['text']
        spans = op['material_spans'] + op['concentration_spans']
        spans += [op[k]['evidence'] for k in ('duration', 'temperature') if op[k].get('evidence')]
        for ev in spans:
            assert text[ev['start']:ev['end']] == ev['text']
            span_checks += 1
    output = {'stage': 'development_pilot', 'cases': metadata, 'methods': results, 'extraction': extraction,
              'condition_checks': conditions, 'diagnostic_EXPAND_026': diagnostic,
              'verification': {'source_span_checks': span_checks, 'input_and_code_hashes_valid': True},
              'calibration': 'Leave-one-case/method-out top-score F1 calibration; deterministic ties choose higher threshold. Representation rules are pilot-developed, so this is cross-case calibration, not a fully independent benchmark.'}
    dump('results.json', output)
    with (HERE / 'retrieval_rows.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(raw_rows[0]))
        writer.writeheader()
        writer.writerows(raw_rows)
    dump('similarity_matrices.json', {m: {c: matrix.tolist() for c, matrix in cases.items()} for m, cases in matrices.items()})
    print(json.dumps({'methods': {k: {'R1': v['fixed_threshold']['recall_at_1'], 'R3': v['fixed_threshold']['recall_at_3'],
        'macro_R1': v['case_macro_recall_at_1'], 'loco': v['loco_calibrated'], 'global': v['global_loco']} for k, v in results.items()},
        'extraction': extraction, 'conditions_correct': sum(p['expected'] == p['predicted'] for p in conditions),
        'condition_n': len(conditions), 'diagnostic': diagnostic, 'spans': span_checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
