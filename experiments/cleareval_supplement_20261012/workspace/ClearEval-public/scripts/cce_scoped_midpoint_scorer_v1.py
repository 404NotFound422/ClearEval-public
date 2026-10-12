"""Reusable offline CCE scorer: task-scoped lookup, midpoint policy, source ledger.

Accepts archived judge decompositions and optional explicit source-bound semantic
decompositions. It never calls a model, chooses a best repeat, edits raw returns,
or changes the original SR/SP, direct scales, or EGES numerical equations.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from cce_grounded_offline_scoring_v1 import runtime, derive, DIRECT, EGES
import cce_target_catalog_role_fix_v2 as catalog
import cce_label_occurrence_diagnostic_v1 as occurrence
from cce_scales_source_key_alias_v1 import source_key_alias

VERSION = 'cce-scoped-midpoint-scorer-v1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def finite(x):
    return type(x) in (float, int) and math.isfinite(x)


def complete(metrics):
    return all(finite(metrics.get(k)) for k in ['Com','Cor','Eff','IA','HV'])


def time_input(calculation, saved_hours):
    """A declared finite range is a point convention, not missing information."""
    bounds = calculation.get('candidate_bounds_hours')
    issues = calculation.get('issues', [])
    if finite(saved_hours):
        return {'hours': saved_hours, 'bounds_hours': [saved_hours, saved_hours],
                'decision': 'existing_source_bound_scalar', 'issues': issues}
    if (isinstance(bounds, list) and len(bounds) == 2
            and all(finite(x) for x in bounds) and 0 <= bounds[0] <= bounds[1]
            and set(issues) <= {'nonunique_duration_range'}
            and calculation.get('mode') == 'serial'):
        contributions = calculation.get('known_operation_contributions', [])
        ids = calculation.get('included_operation_ids', [])
        if ids and set(ids) == {r['operation_id'] for r in contributions}:
            sums = [sum(r[k] for r in contributions) for k in ['lower_hours','upper_hours']]
            if all(math.isclose(a,b,abs_tol=1e-10) for a,b in zip(sums,bounds)):
                return {'hours': sum(bounds)/2, 'bounds_hours': bounds,
                        'decision': 'explicit_duration_range_midpoint',
                        'resolved_issues': issues, 'issues': [],
                        'operation_contributions': contributions}
    return {'hours': None, 'bounds_hours': bounds,
            'decision': 'source_semantic_resolution_needed', 'issues': issues}


@contextlib.contextmanager
def task_lookup(runner, targets, preferences):
    """Resolve compatibility scope without changing target-match arithmetic."""
    oldmatch = runner._match_marker_to_targets
    oldcompat = runner._get_marker_fluor_compat
    trace = []

    def match(marker, query_targets, fluor_name=None):
        return oldmatch(marker, catalog.expanded_targets(query_targets), fluor_name=fluor_name)

    def compat(marker, fluor):
        requested = preferences.get(runner._normalize_name(marker))
        selected_targets = targets
        if requested:
            scope = requested['scope']
            selected_targets = [t for t in targets if all(
                t.get(a) == scope[b] for a,b in catalog.SCOPE_KEYS.items())]
            if not selected_targets:
                raise ValueError('Declared tissue scope is absent from fixed question targets')
        result = catalog.marker_scope_lookup(runner, marker, fluor, selected_targets)
        result['declared_task_scope'] = requested
        result['legacy_last_row_value'] = oldcompat(marker, fluor)
        trace.append(result)
        return result['value']

    runner._match_marker_to_targets = match
    runner._get_marker_fluor_compat = compat
    try:
        yield trace
    finally:
        runner._match_marker_to_targets = oldmatch
        runner._get_marker_fluor_compat = oldcompat


def verify_span(text, span):
    if text[span['start']:span['end']] != span['quote']:
        raise ValueError('Source quote does not match the bound answer')


def semantic_projection(annotation, doc):
    """Use recorded LLM/author semantic decisions without another regex judge."""
    if annotation['answer_sha256'] != doc['answer_sha256']:
        raise ValueError('Semantic decomposition belongs to a different answer')
    pairs = []
    mapping = annotation['proposed_original_marker_dict']
    for index, relation in enumerate(annotation['relations']):
        spans = relation['source_spans']
        if not spans:
            raise ValueError('Relation has no source evidence')
        for span in spans:
            verify_span(doc['text'], span)
        fluor, marker = relation['fluorophore'], relation['marker']
        if mapping.get(fluor) != marker:
            raise ValueError('Relation and proposed projection disagree')
        pairs.append({'pair_id': 'semantic:'+str(index),
            'fluor_literal': fluor, 'marker_literal': marker or None,
            'kind': 'supported_relation' if marker else 'source_native_fluor_key_only',
            'evidence': spans, 'semantic_basis': relation['basis']})
    if {p['fluor_literal'] for p in pairs} != set(mapping):
        raise ValueError('Projection drops a declared label')
    operations = annotation['operations']
    for operation in operations:
        verify_span(doc['text'], operation['source'])
    included = [op for op in operations if op['included_in_core_time']]
    if not included:
        raise ValueError('No declared core operations')
    bounds = [sum(op[k]*op['repeat_count'] for op in included)
              for k in ['hours_lower','hours_upper']]
    if bounds != annotation['reported_core_hours']:
        raise ValueError('Operation ledger and total time disagree')
    if not all(finite(x) for x in bounds) or not 0 <= bounds[0] <= bounds[1]:
        raise ValueError('Cannot take a midpoint of an open duration interval')
    projection = {'pairs': pairs, 'supported_local_dictionary_view': mapping,
                  'lossless_single_value_projection': True, 'explicit_label_uncertainties': []}
    time = {'hours': sum(bounds)/2, 'bounds_hours': bounds,
            'decision': 'source_bound_semantic_operation_ledger',
            'qualification': annotation['qualification'], 'operations': operations,
            'semantic_author': annotation['semantic_author'], 'issues': []}
    return projection, time


@source_key_alias()
def score_record(post, question_id, config, runner, registry, annotation=None, doc=None):
    """One entry for any bound answer; no answer-ID branches or score overrides."""
    saved = post['numeric']
    old = post['metrics']
    conversion = post['conversion']
    quantitative = copy.deepcopy(saved['quantitative_data'])
    demand = saved['user_preference_vector']
    meta = runner.QUESTION_META_KB[registry.questions[str(question_id)]['question_id']]
    targets = meta['marker_query_targets']
    projection = conversion['label_occurrence_projection']
    time = time_input(conversion['legacy_projection']['time_calculation'], quantitative['total_time_hours'])
    if annotation:
        if annotation['question_id'] != question_id:
            raise ValueError('Question mismatch in semantic decomposition')
        projection, time = semantic_projection(annotation, doc)
    quantitative['total_time_hours'] = time['hours']
    preferences = config.get('task_marker_scopes', {}).get(str(question_id), {})
    with task_lookup(runner, targets, preferences) as lookup_trace:
        label = occurrence.score_label_occurrences(projection, runner, quantitative, demand, targets)
        original = runner.calculate_effectiveness_score(quantitative, demand,
            runner.MODEL_SPACE_SIGNED, {}, targets)
    # Direct judgments and unaffected original components are reused by identity.
    components = {k: old[k] for k in DIRECT + EGES}
    components['s_label'] = label['s_label']
    components['s_time'] = original['s_time']
    for key in ['s_method', 's_trans']:
        if finite(old[key]) and (not finite(original[key]) or not math.isclose(old[key], original[key], abs_tol=1e-12)):
            raise ValueError('Unchanged input does not reproduce original '+key)
    metrics = derive(components, {k: old[k] for k in ['sr','sp']}, True)
    if any(metrics[k] != old[k] for k in DIRECT + ['sr','sp','Com','Cor']):
        raise AssertionError('A reused metric changed')
    sensitivity = []
    bounds = time.get('bounds_hours')
    if finite(time['hours']) and isinstance(bounds,list) and all(finite(x) for x in bounds):
        times = {bounds[0], time['hours'], bounds[1]}
        for key in ['min_hours', 'max_hours']:
            boundary = original['time_computation'].get(key)
            if finite(boundary) and bounds[0] <= boundary <= bounds[1]:
                times.add(boundary)
        for hours in sorted(times):
            effect = runner.calculate_effectiveness_score({**quantitative,'total_time_hours':hours},
                demand, runner.MODEL_SPACE_SIGNED, {}, targets)
            one = derive({**components, 's_time':effect['s_time']},
                {k: old[k] for k in ['sr','sp']}, True)
            sensitivity.append({'time_hours':hours, 's_time':effect['s_time'], 'Eff':one['Eff']})
    return {'version': VERSION, 'metrics':metrics, 'complete_numeric_CCE':complete(metrics),
        'baseline_metrics':old, 'quantitative_data':quantitative,
        'time_derivation':time, 'time_formula':original['time_computation'],
        'time_sensitivity':sensitivity, 'label_derivation':label,
        'compatibility_lookup_trace':lookup_trace,
        'semantic_decomposition_applied':bool(annotation),
        'semantic_author':annotation['semantic_author'] if annotation else 'saved judge decomposition',
        'remaining_dependencies':{'time':time['issues'],
            'label_relations':projection.get('explicit_label_uncertainties',[]),
            'compatibility':[x for x in lookup_trace if x['value'] is None]},
        'new_model_requests':0, 'new_expert_records':0,
        'direct_scores_rejudged':False, 'SR_SP_changed':False,
        'raw_judge_status_changed':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--decompositions', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    config, cells = read(args.config), read(args.cells)
    runner, registry = runtime()
    annotations = {}
    if args.decompositions:
        annotations = {r['answer_sha256']:r for r in read(args.decompositions)['results']}
    manifest = {'version':VERSION, 'entrypoint':bind(__file__), 'config':bind(args.config),
        'cells':bind(args.cells), 'decompositions':bind(args.decompositions) if args.decompositions else None,
        'original_scorer':bind(ROOT/'OEQ_run_grading_new.py'),
        'knowledge_base':bind(ROOT/'KnowledgeBase/tissue.json'),
        'scope':'archived-return offline engineering replay; repeated cells are not independent answers',
        'planned_cells':len(cells), 'new_model_requests':0}
    save(args.out/'execution_manifest.json', manifest)
    results = []
    for cell in cells:
        row = {k:cell[k] for k in ['cohort','cell_id','anonymous_answer_id','question_id'] if k in cell}
        row['original_status'] = cell['status']
        if 'posthoc_record' not in cell:
            row.update(status='no_saved_return', baseline_metrics=cell['posthoc_metrics'],
                metrics=cell['posthoc_metrics'], complete_numeric_CCE=False)
            results.append(row)
            continue
        source = cell['posthoc_record']
        if bind(source['path']) != source:
            raise ValueError('Archived scoring record changed')
        post = read(source['path'])
        if not post.get('numeric'):
            row.update(status='partial_saved_components_retained', source_record=source,
                baseline_metrics=post['metrics'], metrics=post['metrics'],
                complete_numeric_CCE=complete(post['metrics']),
                remaining_dependencies={'saved_conversion_failure':post.get('full_conversion_or_scoring_failure')},
                changes={})
            save(args.out/'records'/cell['cohort']/(cell['cell_id']+'.json'),row)
            results.append(row)
            continue
        sha = post['numeric']['source_binding']['answer_sha256']
        annotation = annotations.get(sha)
        doc = read(annotation['source_document']['path']) if annotation else None
        if doc and hashlib.sha256(doc['text'].encode('utf-8')).hexdigest() != sha:
            raise ValueError('Answer hash mismatch')
        row.update(score_record(post, cell['question_id'], config, runner, registry, annotation, doc))
        row.update(status='replayed', source_record=source, answer_sha256=sha)
        row['changes'] = {k:{'before':row['baseline_metrics'][k],'after':v}
                          for k,v in row['metrics'].items() if v != row['baseline_metrics'][k]}
        save(args.out/'records'/cell['cohort']/(cell['cell_id']+'.json'),row)
        results.append(row)
    save(args.out/'results.json',results)
    cohorts = {}
    for cohort in sorted({r['cohort'] for r in results}):
        group = [r for r in results if r['cohort']==cohort]
        cohorts[cohort] = {'cells':len(group), 'before':sum(complete(r['baseline_metrics']) for r in group),
                          'after':sum(complete(r['metrics']) for r in group)}
    summary = {'version':VERSION, 'planned_cells':len(results),
        'archived_returns_processed':sum(r['status']!='no_saved_return' for r in results),
        'replayed_returns':sum(r['status']=='replayed' for r in results),
        'partial_saved_components_retained':sum(r['status']=='partial_saved_components_retained' for r in results),
        'no_saved_return':sum(r['status']=='no_saved_return' for r in results),
        'complete_before':sum(complete(r['baseline_metrics']) for r in results),
        'complete_after':sum(complete(r['metrics']) for r in results),
        'previous_complete_lost':[r['cell_id'] for r in results if complete(r['baseline_metrics']) and not complete(r['metrics'])],
        'changed_cells':[{'cohort':r['cohort'],'id':r['cell_id'],'changes':r.get('changes',{})}
                         for r in results if r.get('changes')],
        'time_midpoint_cells':[r['cell_id'] for r in results if r.get('time_derivation',{}).get('decision')=='explicit_duration_range_midpoint'],
        'semantic_decomposition_cells':[r['cell_id'] for r in results if r.get('semantic_decomposition_applied')],
        'cohorts':cohorts, 'new_model_requests':0,'new_expert_records':0,
        'validation_claim':'engineering replay; not a new evaluator stability/generalization trial'}
    save(args.out/'summary.json',summary)
    keys = ['cohort','cell_id','question_id','original_status','complete_numeric_CCE'] + DIRECT + EGES + ['sr','sp','Com','Cor','Eff','IA','HV']
    with (args.out/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
        for r in results:
            writer.writerow({**{k:r.get(k) for k in keys if k not in r['metrics']}, **r['metrics']})
    for key in ['original_scorer','knowledge_base']:
        assert bind(manifest[key]['path']) == manifest[key]
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
