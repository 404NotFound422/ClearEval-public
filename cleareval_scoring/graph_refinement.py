"""Post-hoc pilot refinement: material-state transitions and principal purpose.

Motivated by CUBIC initial/refresh swaps and Ce3D degassing confusion.
No case-ID or gold-label lookup in feature construction/scoring. Frozen first
round results are preserved; these are additional development results.
"""
from copy import deepcopy
import csv
import json
from pathlib import Path
import re

import numpy as np

from .operations import field_score
from .binding import bind_operation
from .evaluate import assignment, calibrate, metrics

HERE = Path(__file__).resolve().parent


def graph_features(sequence):
    output = []
    previous = None
    for index, node in enumerate(sequence):
        op = bind_operation(node)
        text = node['text']
        if op.get('stock_fraction_ranking_feature') is not None:
            stock_values = [op['concentrations'][k] for k in op['primary_materials'] if k in op['concentrations']]
            if len(stock_values) == 1:
                op['stock_fraction_ranking_feature'] = stock_values[0] / 100
                op['stock_origin'] = 'explicit_percent_of_named_stock'
        degas = bool(re.search(r'degas|de.?bubble|脱泡|去气泡|脱气', text, re.I))
        transfer = bool(re.search(r'\b(?:transfer|transition)\b.*\binto\b|转入', text, re.I))
        if transfer and op['primary_materials'] and op['action'] not in ('store', 'mount'):
            op['action'] = 'incubate'
            op['action_origin'] = 'destination_contact_in_compound_operation'
        if degas and not transfer:
            purpose = 'degassing'
        elif op['action'] in ('store', 'mount', 'wash', 'rehydrate'):
            purpose = op['action']
        else:
            purpose = 'medium_contact'
        if purpose == 'wash' and op['phase'] not in {'labeling', 'pretreatment'}:
            op['phase'] = 'washing'
        same_state = False
        if previous:
            old = previous['features']
            same_state = (old['primary_materials'] == op['primary_materials'] and bool(op['primary_materials'])
                          and old['concentrations'] == op['concentrations']
                          and old.get('stock_fraction_ranking_feature') == op.get('stock_fraction_ranking_feature')
                          and previous['purpose'] == purpose == 'medium_contact')
        explicit_continue = bool(re.search(r'\bfresh\b|\brefresh\b|\bcontinue\b|新鲜|新液|继续|再置换|更换', text, re.I))
        mode = 'continuation' if same_state or explicit_continue else 'entry'
        # An explicit change from a diluted input to a full stock is an entry into a new state.
        if re.search(r'half.*\bfull\b', text, re.I):
            mode = 'entry'
        entry = {'features': op, 'purpose': purpose, 'contact_mode': mode,
                 'previous_node': index - 1 if previous else None,
                 'input_medium_state': previous['features']['primary_materials'] if previous else [],
                 'same_medium_state_as_previous': same_state,
                 'explicit_continuation': explicit_continue}
        output.append(entry)
        previous = entry
    return output


def score(a, b):
    if a['purpose'] != b['purpose'] and 'degassing' in (a['purpose'], b['purpose']):
        return -1.0
    first, second = a['features'], b['features']
    s = field_score(first, second, 'joint')
    # Clearing and RI matching often share a medium and a compound purpose.
    # Use overlapping purpose for correspondence, retain original phase for correctness review.
    if first['phase'] != second['phase'] and {first['phase'], second['phase']} <= {'clearing', 'ri_matching'}:
        s += .35
    if a['purpose'] == b['purpose'] == 'medium_contact' and a['contact_mode'] != b['contact_mode']:
        s -= .10
    if a['purpose'] == b['purpose'] == 'wash' and a['input_medium_state'] and b['input_medium_state']:
        if not set(a['input_medium_state']) & set(b['input_medium_state']):
            s -= .10
    return s


def main():
    nodes = json.loads((HERE / 'operations.json').read_text(encoding='utf8'))
    data = json.loads((HERE / 'inputs.json').read_text(encoding='utf8'))
    gold = json.loads((HERE / 'annotations.json').read_text(encoding='utf8'))['correspondences']
    original = json.loads((HERE / 'results.json').read_text(encoding='utf8'))
    graphs, matrices, rows = {}, {}, []
    for case in data['cases']:
        cid = case['id']
        rids = [s['id'] for s in case['reference_steps']]
        cids = [s['id'] for s in case['candidate_steps']]
        ref = graph_features([nodes[cid + ':R:' + k] for k in rids])
        cand = graph_features([nodes[cid + ':C:' + k] for k in cids])
        matrix = np.array([[score(a, b) for b in cand] for a in ref])
        matrices[cid] = matrix
        graphs[cid] = {'reference_ids': rids, 'candidate_ids': cids, 'reference': ref, 'candidate': cand}
        for i, rid in enumerate(rids):
            order = sorted([j for j in range(len(cids)) if matrix[i, j] > -1], key=lambda j: (-matrix[i, j], j))
            top = cids[order[0]] if order else None
            val = float(matrix[i, order[0]]) if order else -2
            rows.append({'case': cid, 'reference': rid, 'gold_candidates': gold[cid][rid],
                         'top_candidate': top, 'top_score': val,
                         'rank': next((n + 1 for n, j in enumerate(order) if cids[j] in gold[cid][rid]), None),
                         'accepted': top is not None and val > .7, 'selected_correct': top in gold[cid][rid] and val > .7})
    details, thresholds = {}, {}
    for cid, matrix in matrices.items():
        t = calibrate([r for r in rows if r['case'] != cid])
        thresholds[cid] = t
        details[cid] = {}
        for variant, ordered in [('global', False), ('ordered', True)]:
            matches = assignment(matrix, t, ordered=ordered)
            pairs = []
            for i, j in matches:
                rid, qid = graphs[cid]['reference_ids'][i], graphs[cid]['candidate_ids'][j]
                pairs.append({'reference': rid, 'candidate': qid, 'score': float(matrix[i, j]), 'correct': qid in gold[cid][rid]})
            details[cid][variant] = pairs
    summary = {}
    for variant in ('global', 'ordered'):
        pairs = [p for c in details.values() for p in c[variant]]
        correct = sum(p['correct'] for p in pairs)
        capacity = sum(c['gold_one_to_one_capacity'] for c in original['cases'].values())
        summary[variant] = {'accepted': len(pairs), 'correct': correct, 'gold_capacity': capacity,
                             'precision': correct / len(pairs) if pairs else None, 'capacity_recall': correct / capacity,
                             'false_on_absent': sum(not gold[cid][p['reference']] for cid, ds in details.items() for p in ds[variant])}
    out = {'stage': 'post_hoc_pilot_development_refinement',
           'changes': ['explicit principal purpose distinguishes degassing from clearing contact',
                       'medium-state edges distinguish entry from continuation',
                       'compound destination transfer contributes contact action',
                       'overlapping clearing/RI purpose used for correspondence only',
                       'explicit percentage of a named stock updates stock fraction',
                       'core washes retain wash purpose and preceding medium state',
                       'principal contact distinguished from removal purpose',
                       'numeric fields exclude material names and embedded identifiers'],
           'retrieval': metrics(rows), 'assignment': summary, 'thresholds': thresholds, 'matches': details, 'graphs': graphs}
    (HERE / 'graph_refinement_results.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    with (HERE / 'graph_refinement_rows.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'retrieval': out['retrieval'], 'assignment': summary,
                      'wrong': {cid: [p for p in ds['global'] if not p['correct']] for cid, ds in details.items() if any(not p['correct'] for p in ds['global'])}}, indent=2))


if __name__ == '__main__':
    main()
