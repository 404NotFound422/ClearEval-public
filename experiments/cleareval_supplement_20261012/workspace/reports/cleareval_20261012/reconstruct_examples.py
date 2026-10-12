"""Record the current assistant's two source readings and run original math offline.

The semantic decisions below were made by the assistant after reading the full
answers. This script binds those decisions to literal spans; it is not an LLM
extractor and makes no model request. Published/frozen scores are not changed.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = Path(r'C:\ClearEval\ClearEval-public')
OUT = REPO / 'artifacts/cce_validation'
R2 = OUT / 'optimizer_round2_20261010'
R3 = OUT / 'optimizer_round3_20261011'
sys.path[:0] = [str(REPO), str(REPO / 'scripts')]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def span(text, line):
    lines = text.splitlines(keepends=True)
    start = sum(map(len, lines[:line-1]))
    quote = lines[line-1].rstrip('\r\n')
    return {'line': line, 'start': start, 'end': start+len(quote), 'quote': quote}


# Explicit author/model annotations, not inferred by the numerical script.
ANNOTATIONS = {
    'FPC03': {
        'core': [(n, 1, 1, 'core') for n in [8, 9, 10, 11, 12, 20, 21, 22]]
                + [(n, 24, 24, 'core') for n in [25, 26, 27]],
        'labeling': [(15, 2, 2, 'labeling'), (16, 1, 1, 'labeling_wash'),
                     (17, 1, 1, 'labeling_wash')],
        'other_lines': [(3, '3D is a spatial expression, not a duration'),
                        (30, 'storage lower bound one week, no finite upper bound'),
                        (31, 'imaging procedure without a reported duration')],
        'marker_dict': {'GFP': '', 'Alexa Fluor 647': 'MAP2'},
        'relations': [
            {'fluorophore': 'GFP', 'marker': '', 'source_line': 2,
             'basis': 'Declared endogenous reporter; no self-target relation added.'},
            {'fluorophore': 'Alexa Fluor 647', 'marker': 'MAP2', 'source_line': 15,
             'basis': 'The answer explicitly states anti-MAP2 antibody (Alexa Fluor 647 conjugated).'}],
        'qualification': 'Exact sum of reported core durations under the registered exclusion of labeling and storage.',
    },
    'FPC07': {
        'core': [(n, 3, 3, 'core') for n in [7, 8, 9, 10, 19]]
                + [(11, .5, .5, 'core'), (20, 12, 24, 'core_typical_window')],
        'labeling': [(14, 24, 24, 'labeling'), (15, 1, 1, 'labeling_wash'),
                     (16, 1, 1, 'labeling_wash')],
        'other_lines': [(3, 'General method claim of 3-5 days, not an additional operation'),
                        (23, 'Long-term storage with no numerical duration')],
        'marker_dict': {'tdTomato': '', 'Alexa Fluor 647': 'F-actin'},
        'relations': [
            {'fluorophore': 'tdTomato', 'marker': '', 'source_line': 2,
             'basis': 'Selected fluorescence identity; no self-target relation added.'},
            {'fluorophore': 'Alexa Fluor 647', 'marker': 'F-actin',
             'source_lines': [3, 14],
             'basis': 'Same answer explicitly describes Phalloidin conjugated to Alexa Fluor 647 and identifies its target as F-actin. Phalloidin is the labeling reagent, not a second independently selected fluorophore.'}],
        'qualification': 'Reported typical timing scenario only. Until-transparent stopping condition prevents interpreting 12-24 h as guaranteed actual bounds.',
    },
}


def main():
    from cce_grounded_offline_scoring_v1 import runtime, derive
    runner, registry = runtime()
    old_rows = {x['anonymous_answer_id']: x for x in read(R2 / 'first7_historical_availability_audit_v1/per_answer.json')}
    results = []
    checks = []
    for cid, ann in ANNOTATIONS.items():
        source_path = R2 / 'generation_confirmation_v2/source_documents' / (cid+'.json')
        doc = read(source_path)
        text = doc['text']
        assert hashlib.sha256(text.encode('utf-8')).hexdigest() == doc['answer_sha256']
        old = old_rows[cid]
        assert old['answer_sha256'] == doc['answer_sha256']
        post_path = R3 / 'uniform_v7/actual_01/cells/first7_posthoc' / cid / 'posthoc.json'
        post = read(post_path)
        saved = post['numeric']
        records = []
        for line, lo, hi, role in sorted(ann['core'] + ann['labeling']):
            records.append({'source': span(text, line), 'phase': role,
                'repeat_count': 1, 'hours_lower': lo, 'hours_upper': hi,
                'included_in_core_time': role.startswith('core'),
                'decision': 'Use each separately written operation once; no inferred repeats.'})
        for rec in records:
            s = rec['source']
            assert text[s['start']:s['end']] == s['quote']
        core = [sum(r[k] for r in records if r['included_in_core_time'])
                for k in ['hours_lower','hours_upper']]
        all_pre_storage = [sum(r[k] for r in records) for k in ['hours_lower','hours_upper']]
        assert core == ([80,80] if cid == 'FPC03' else [27.5,39.5])
        assert all_pre_storage == ([84,84] if cid == 'FPC03' else [53.5,65.5])
        relations = copy.deepcopy(ann['relations'])
        for rel in relations:
            lines = rel.get('source_lines', [rel.get('source_line')])
            rel['source_spans'] = [span(text, n) for n in lines]
        quant = copy.deepcopy(saved['quantitative_data'])
        demand = copy.deepcopy(saved['user_preference_vector'])
        qid = old['question_id']
        meta = runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]
        endpoint_scores = []
        for hours in sorted(set(core)):
            q = {**quant, 'total_time_hours': hours}
            effects = runner.calculate_effectiveness_score(q, demand, runner.MODEL_SPACE_SIGNED,
                ann['marker_dict'], meta.get('marker_query_targets') or [])
            components = {**post['metrics'], **{k: effects[k] for k in ['s_method','s_label','s_trans','s_time']}}
            metrics = derive(components, {'sr': post['metrics']['sr'], 'sp': post['metrics']['sp']}, True)
            assert metrics['Com'] == post['metrics']['Com']
            assert math.isclose(metrics['Cor'], post['metrics']['Cor'], abs_tol=1e-12)
            endpoint_scores.append({'time_hours': hours, 'quantitative_data': q,
                'original_function_results': effects, 'derived_metrics': metrics})
        if len(endpoint_scores) == 2:
            # Both endpoints are on the lower side of the saved KB window;
            # monotonicity validates endpoint extrema on this stated scenario.
            window = endpoint_scores[0]['original_function_results']['time_computation']
            assert core[1] < window['min_hours']
        table = {k: None if any(x['derived_metrics'][k] is None for x in endpoint_scores)
                 else [min(x['derived_metrics'][k] for x in endpoint_scores), max(x['derived_metrics'][k] for x in endpoint_scores)]
                 for k in ['s_method','s_label','s_trans','s_time','Com','Cor','Eff','IA','HV']}
        checks.append({'id': cid, 'literal_operations': len(records), 'all_span_and_sum_checks_passed': True})
        results.append({'id': cid, 'question_id': qid, 'answer_sha256': doc['answer_sha256'],
            'source_document': bind(source_path), 'baseline_v7': bind(post_path),
            'semantic_author': 'current assistant; author decomposition, not independent expert',
            'core_scope': 'initial clearing and RI; exclude labeling and its local washes, storage, imaging',
            'operations': records, 'other_claims': [{'source': span(text,n), 'interpretation': why} for n,why in ann['other_lines']],
            'relations': relations, 'proposed_original_marker_dict': ann['marker_dict'],
            'reported_core_hours': core, 'reported_all_pre_storage_hours': all_pre_storage,
            'qualification': ann['qualification'], 'old_saved_time_hours': old['historical_input_from_saved_reasoning']['time_hours'],
            'saved_v7_metrics': post['metrics'], 'endpoint_replays': endpoint_scores,
            'conditional_numeric_ranges': table,
            'direct_scores_rejudged': False, 'frozen_primary_modified': False,
            'KB_or_formula_modified': False, 'scientific_accuracy_established': False})
    result = {'scope': 'current-assistant explicit reconstruction plus original-function conditional replay',
        'not_a_new_frozen_Qwen_trial': True, 'new_local_or_API_model_requests': 0,
        'new_expert_records': 0, 'current_assistant_semantic_readings': 2,
        'code': bind(__file__), 'original_scoring_function': bind(REPO/'OEQ_run_grading_new.py'),
        'time_function': bind(REPO/'evaluation_contract.py'),
        'knowledge_inputs': [bind(REPO/'KnowledgeBase'/x) for x in ['time_kb.json','tissue.json','method_fluro_compati.json']],
        'results': results, 'checks': checks}
    (HERE/'llm_decomposition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases': 2, 'actual_new_model_requests': 0, 'output': str(HERE/'llm_decomposition.json'),
        'results': [{k:x[k] for k in ['id','reported_core_hours','reported_all_pre_storage_hours','conditional_numeric_ranges']} for x in results]},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
