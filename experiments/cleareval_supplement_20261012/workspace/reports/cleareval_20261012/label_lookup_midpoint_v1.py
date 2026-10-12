"""Offline, source-bound lookup correction and duration-midpoint replay.

The new entry point selects an explicitly declared tissue scope. It does not
overwrite frozen scoring code/results or fill null cells in the knowledge base.
All numerical equations and saved direct scores/SR/SP are reused unchanged.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reconstruct_examples as prior
from cce_grounded_offline_scoring_v1 import runtime, derive

SCOPE_FIELDS = ['大类', '亚类', '结构/细胞类型']
MARKER_FIELDS = ['推荐标志物 1', '推荐标志物 2']
MAP2_SCOPE = {'大类': '中枢神经', '亚类': '神经元结构', '结构/细胞类型': '神经元(通用)'}
EGES = ['s_method', 's_label', 's_trans', 's_time']
PRESERVED = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem', 'sr', 'sp', 'Com', 'Cor']


def midpoint(lo, hi):
    assert all(type(v) in (int, float) and math.isfinite(v) for v in (lo, hi))
    assert 0 <= lo <= hi
    return (lo + hi) / 2


def lookup(runner, rows, marker, fluor, scope=None):
    """Retain every exact-identity row and select scope before reading values."""
    norm = runner._normalize_name
    exact = {norm(marker)}
    matches = [(i, row) for i, row in enumerate(rows)
               if any(norm(row.get(f, '')) in exact for f in MARKER_FIELDS)]
    if not matches:
        aliases = runner._expand_marker_candidates(marker)
        matches = [(i, row) for i, row in enumerate(rows)
                   if any(norm(row.get(f, '')) in aliases for f in MARKER_FIELDS)]
    column = runner._map_fluor_to_tissue_col(fluor)
    records = [{'row_index_zero_based': i,
                'scope': {k: row.get(k) for k in SCOPE_FIELDS},
                'markers': {k: row.get(k) for k in MARKER_FIELDS},
                'column': column, 'cell': row.get(column)} for i, row in matches]
    selected = [r for r in records if scope is None or r['scope'] == scope]
    trace = {'marker': marker, 'fluorophore': fluor, 'requested_scope': scope,
             'matching_rows': records, 'selected_rows': selected,
             'policy': 'select declared scope before reading cell; no max-value or last-row selection'}
    if not selected or column is None:
        return {**trace, 'value': None, 'status': 'NO_MATCHING_ROW_OR_COLUMN'}
    if len({tuple(r['scope'].values()) for r in selected}) > 1:
        return {**trace, 'value': None, 'status': 'SCOPE_SELECTION_REQUIRED'}
    known = {r['cell'] for r in selected if r['cell'] in (0, 1)}
    if len(known) > 1:
        return {**trace, 'value': None, 'status': 'CONFLICTING_AUTHORED_VALUES'}
    value = bool(next(iter(known))) if known else None
    return {**trace, 'value': value,
            'status': 'TABLE_REPORTED' if value is not None else 'CELL_UNKNOWN'}


def main():
    runner, registry = runtime()
    source_path = HERE / 'llm_decomposition.json'
    source = prior.read(source_path)
    bound = [source_path, prior.REPO/'OEQ_run_grading_new.py',
             prior.REPO/'evaluation_contract.py', prior.REPO/'KnowledgeBase/tissue.json',
             prior.REPO/'KnowledgeBase/time_kb.json',
             prior.REPO/'KnowledgeBase/method_fluro_compati.json',
             HERE/'REPORT_zh.md', HERE/'LLM_DECOMPOSITION_zh.md', HERE/'verification.json']
    for case in source['results']:
        bound += [Path(case['source_document']['path']), Path(case['baseline_v7']['path'])]
    before = [prior.bind(p) for p in bound]
    for binding in [source['original_scoring_function'], source['time_function'], *source['knowledge_inputs']]:
        assert prior.bind(binding['path']) == binding
    old_lookup = runner._get_marker_fluor_compat
    rows = runner.TISSUE_KB
    checks = []
    map_trace = lookup(runner, rows, 'MAP2', 'Alexa Fluor 647', MAP2_SCOPE)
    assert old_lookup('MAP2', 'Alexa Fluor 647') is None
    assert map_trace['value'] is True and len(map_trace['selected_rows']) == 1
    assert lookup(runner, list(reversed(rows)), 'MAP2', 'Alexa Fluor 647', MAP2_SCOPE)['value'] is True
    assert lookup(runner, rows, 'MAP2', 'Alexa Fluor 647')['status'] == 'SCOPE_SELECTION_REQUIRED'
    checks += ['old MAP2 lookup reproduces None', 'selected generic-neuron row returns true',
               'row reversal preserves selected result', 'undeclared conflicting scopes are exposed']
    row = copy.deepcopy(rows[map_trace['selected_rows'][0]['row_index_zero_based']])
    col = map_trace['selected_rows'][0]['column']
    for cell, expected in [(0, False), (1, True), (None, None)]:
        row[col] = cell
        assert lookup(runner, [row], 'MAP2', 'Alexa Fluor 647', MAP2_SCOPE)['value'] is expected
    checks.append('synthetic known-zero, known-one and unknown cells retain their meanings')
    zero, one = copy.deepcopy(row), copy.deepcopy(row)
    zero[col], one[col] = 0, 1
    assert lookup(runner, [zero, one], 'MAP2', 'Alexa Fluor 647', MAP2_SCOPE)['status'] == 'CONFLICTING_AUTHORED_VALUES'
    checks.append('contradictory values are reported, never maximized')
    results = []
    for case in source['results']:
        post = prior.read(case['baseline_v7']['path'])
        quant = copy.deepcopy(case['endpoint_replays'][0]['quantitative_data'])
        question = registry.questions[str(case['question_id'])]
        targets = runner.QUESTION_META_KB[question['question_id']]['marker_query_targets']
        scope_choice = None
        if case['id'] == 'FPC03':
            matching_target = next(t for t in targets if t['marker_name'] == 'MAP2'
                                  and t['structure_or_cell_subtype'] == MAP2_SCOPE['结构/细胞类型'])
            scope_choice = {'scope': MAP2_SCOPE, 'fixed_question_target': matching_target,
                'basis': 'The fixed question requests sparse brain-neuron morphology and dendrites, without a CA1-specific requirement. Its registered targets explicitly include the generic-neuron MAP2 row.',
                'author': 'current assistant scope annotation, not independent expert',
                'lookup': map_trace}

        def selected_lookup(marker, fluor):
            if scope_choice and runner._normalize_name(marker) == 'map2':
                return lookup(runner, rows, marker, fluor, scope_choice['scope'])['value']
            return old_lookup(marker, fluor)

        lo, hi = case['reported_core_hours']
        point = sum(midpoint(op['hours_lower'], op['hours_upper']) * op['repeat_count']
                    for op in case['operations'] if op['included_in_core_time'])
        assert point == midpoint(lo, hi)
        replays = []
        runner._get_marker_fluor_compat = selected_lookup
        try:
            for hours in sorted({lo, point, hi}):
                q = {**quant, 'total_time_hours': hours}
                effects = runner.calculate_effectiveness_score(q,
                    post['numeric']['user_preference_vector'], runner.MODEL_SPACE_SIGNED,
                    case['proposed_original_marker_dict'], targets)
                components = {**post['metrics'], **{k: effects[k] for k in EGES}}
                metrics = derive(components, {k: post['metrics'][k] for k in ['sr', 'sp']}, True)
                assert all(math.isclose(metrics[k], post['metrics'][k], abs_tol=1e-12) for k in PRESERVED)
                replays.append({'time_hours': hours, 'quantitative_data': q,
                    'original_equation_results': effects, 'metrics': metrics})
        finally:
            runner._get_marker_fluor_compat = old_lookup
        main = next(r for r in replays if r['time_hours'] == point)
        assert all(main['metrics'][k] is not None for k in ['Com','Cor','Eff','IA','HV'])
        if case['id'] == 'FPC07':
            for prior_endpoint in case['endpoint_replays']:
                actual = next(r for r in replays if r['time_hours'] == prior_endpoint['time_hours'])
                assert actual['original_equation_results'] == prior_endpoint['original_function_results']
                assert actual['metrics'] == prior_endpoint['derived_metrics']
            assert lo <= point <= hi < main['original_equation_results']['time_computation']['min_hours']
        results.append({'id': case['id'], 'question_id': case['question_id'],
            'answer_sha256': case['answer_sha256'], 'source_document': case['source_document'],
            'baseline_v7': case['baseline_v7'], 'fixed_question': question,
            'scope_selection': scope_choice, 'marker_dict': case['proposed_original_marker_dict'],
            'time_policy': 'arithmetic midpoint of each explicit closed duration range before nonlinear scoring',
            'time_source_qualification': case['qualification'], 'core_time_interval': [lo, hi],
            'point_core_time_hours': point, 'point_result': main, 'all_replays': replays,
            'Eff_interval': [min(r['metrics']['Eff'] for r in replays), max(r['metrics']['Eff'] for r in replays)],
            'direct_scores_rejudged': False, 'SR_SP_changed': False,
            'is_new_independent_evaluator_trial': False, 'expert_confirmed': False})
        checks.append(case['id'] + ': saved direct scores, original SR/SP, Com and Cor preserved')
    assert before == [prior.bind(p) for p in bound]
    checks += ['FPC07 endpoint replay exactly reproduces previous values',
               'all bound original inputs, code, KB and frozen results remain unchanged',
               'both reconstructed examples have complete numerical point scores']
    payload = {'version': 'source-scoped-label-lookup-and-time-midpoint-v1',
        'new_local_or_API_model_requests': 0, 'source_bindings': before,
        'entrypoint': prior.bind(__file__), 'results': results, 'checks_passed': checks,
        'scope': 'Two existing answers; current-assistant source decomposition plus declared lookup scope and midpoint convention. No new model/expert trial or global rescore.',
        'lookup_policy_change': 'FPC03 selects the generic-neuron MAP2 row by declared scope instead of the accidental last-row index.',
        'midpoint_is_empirical_median': False, 'score_equations_changed': False,
        'complete_point_CCE_count': len(results)}
    (HERE/'label_lookup_midpoint.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(HERE/'label_lookup_midpoint.json'),
        'checks_passed': len(checks), 'new_model_requests': 0,
        'results': [{'id': r['id'], 'hours': r['point_core_time_hours'],
                     'metrics': r['point_result']['metrics']} for r in results]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
