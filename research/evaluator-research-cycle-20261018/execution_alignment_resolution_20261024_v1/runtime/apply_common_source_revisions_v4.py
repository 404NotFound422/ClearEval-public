"""Merge declared normal revisions, with replay of derived source projections."""
import argparse
import json
from pathlib import Path
from collections import Counter
if __package__:
    from . import collect_uniform_normal185_v4 as collect
    from . import normal_revision_equivalence_v1 as eq
else:
    import collect_uniform_normal185_v4 as collect
    import normal_revision_equivalence_v1 as eq
from execution_alignment_resolution_20261024_v1.phase_heading_frame_resolution_20261025_v1 import producer as shared_source
from execution_alignment_resolution_20261024_v1.purpose_measurement_alternative_context_20261025_v1 import producer as measurement_source
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import producer as metadata_source,source_entry
from execution_alignment_resolution_20261024_v1.scope import producer_v6,producer_v7,producer_v9,producer_v10,producer_v11,producer_v12,producer_v13,producer_v14
from execution_alignment_resolution_20261024_v1.runtime.aggregate_score_bounds_v1 import DEPENDENCIES

read, save, sha = collect.read, collect.save, collect.sha
key = lambda row: (row['input_id'], row['branch'])
LITERAL_FIELDS = ('id', 'branch', 'number', 'phase', 'raw_text', 'operation',
                  'reagent_text', 'source', 'parameters', 'parameter_mentions',
                  'scoring_text', 'repetition_text', 'endpoint_conditions')
IMMUTABLE_SOURCE_FIELDS = ('id', 'branch', 'number', 'raw_text', 'source',
                           'scoring_text', 'parameters', 'parameter_mentions')
INDEPENDENT = ('co_order', 'co_method', 'co_param', 'co_chem', 's_method',
               's_label', 's_trans', 'Co')
PROJECTION_POLICY = 'REPLAY_DECLARED_SOURCE_PROJECTION_V1'
CAUSE_CLOSURE_POLICY = 'DECLARED_REVISION_CAUSE_TO_ORIGINAL_AGGREGATE_DEPENDENCIES_V1'
PROJECTORS = (producer_v6,producer_v7,producer_v9,producer_v10,producer_v11,
              producer_v12,producer_v13,producer_v14,shared_source,measurement_source,metadata_source)
PARAMETER_CAUSES = frozenset({
    'EXPLICIT_COMPLETE_TARGET_ATOMIC_MULTI_ORIGIN_REAL_OBSERVATIONS',
    'ACTUAL_PRIVATE_PARAMETER_CORE_INTERFACE', 'EXACT_SOURCE_QUOTE_PROJECTION',
    'CANONICAL_JSON_MAIN_SOURCE_BINDING', 'COMPLETE_RECIPE_CARRIER_AND_PHASE_WORLD_SCOPES'})
CAUSE_LEAF_METRICS = {
    **{cause: frozenset({'c_param'}) for cause in PARAMETER_CAUSES},
    'SOURCE_METADATA_VIEW_PURE_RECIPE_OR_LITERAL_COUNT': frozenset({
        's_time', 'cleareval_coverage', 'cleareval_sp_eligible', 'bio_sr', 'bio_sp'}),
    'CANONICAL_JSON_AND_PROJECTION_REPLAY': frozenset()}


def resolve_changed_metrics(causes, declared_metrics=None):
    if not isinstance(causes, (list, tuple)) or not causes:
        raise AssertionError('REVISION_CAUSES_REQUIRED')
    allowed = set()
    for cause in causes:
        if cause not in CAUSE_LEAF_METRICS:
            raise AssertionError('UNREGISTERED_REVISION_CAUSE:' + str(cause))
        allowed.update(CAUSE_LEAF_METRICS[cause])
    for parent, children in DEPENDENCIES.items():
        if allowed.intersection(children):
            allowed.add(parent)
    if allowed.intersection(('Co', 'Com', 'Eff')):
        allowed.add('IA')
    if declared_metrics is not None:
        declared = set(declared_metrics)
        assert declared <= set(collect.METRICS), 'INVALID_DECLARED_COMPONENT_CLOSURE'
        assert declared == allowed, 'REVISION_CAUSE_METRIC_CLOSURE_MISMATCH'
    return allowed


def declared_code_revisions(selected):
    revisions = {}
    for row in selected:
        for revision in row.get('code_revisions', []):
            assert set(revision) == {'path', 'before_sha256', 'after_sha256', 'supporting_pin_files'}, 'INVALID_CODE_REVISION_CONTRACT'
            assert isinstance(revision['supporting_pin_files'], (list, tuple)), 'INVALID_CODE_REVISION_SUPPORT_PINS'
            path = str(Path(revision['path']).resolve())
            if path in revisions:
                assert revisions[path] == revision, 'CONFLICTING_CODE_REVISION'
            else:
                revisions[path] = revision
    return revisions


def resolve_prior_pins(pins, selected, roots):
    revisions = declared_code_revisions(selected)
    baseline_paths = {str(Path(path).resolve()) for path in pins}
    assert set(revisions) <= baseline_paths, 'CODE_REVISION_NOT_IN_BASELINE'
    resolved = dict(pins)
    for path, pin in pins.items():
        normalized = str(Path(path).resolve())
        revision = revisions.get(normalized)
        if revision is None:
            assert sha(path) == pin, ('PRIOR_PIN_CHANGED', path)
            continue
        assert revision['before_sha256'] == pin, 'CODE_REVISION_BASELINE_PIN_MISMATCH'
        current = sha(path)
        assert current == revision['after_sha256'], 'CODE_REVISION_CURRENT_PIN_MISMATCH'
        for pin_file in revision['supporting_pin_files']:
            assert read(pin_file).get(normalized) == current, 'CODE_REVISION_SUPPORT_PIN_MISMATCH'
        for root in roots:
            evidence = read(Path(root) / 'loaded_code_sha256.json')
            assert evidence.get(normalized) == current, 'CODE_REVISION_REPLAY_PIN_MISMATCH'
        resolved[path] = current
    return resolved


def validate_source_projection(branch, baseline, prior, new, transition):
    assert transition['producer_version'] == metadata_source.VERSION
    assert transition['source_projection_chain'] == [shared_source.VERSION,measurement_source.VERSION,metadata_source.VERSION]
    assert transition['common_projection_reproduced'] is True
    assert transition['current_source_sha256'] == collect.digest(new)
    assert transition['actual_encoder_cells_and_receipts_revalidated_by_normal_consumer'] is True
    baseline_rows = {row['id']: row for row in baseline['all_typed_rows']}
    prior_rows = {row['id']: row for row in prior['all_typed_rows']}
    new_rows = {row['id']: row for row in new['all_typed_rows']}
    assert set(baseline_rows) == set(prior_rows) == set(new_rows), 'SOURCE_OPERATION_IDENTITY_CHANGED'
    for identifier in baseline_rows:
        for field in IMMUTABLE_SOURCE_FIELDS:
            expected = baseline_rows[identifier].get(field)
            assert prior_rows[identifier].get(field) == expected, 'RAW_SOURCE_TEXT_CHANGED'
            assert new_rows[identifier].get(field) == expected, 'RAW_SOURCE_TEXT_CHANGED'
    assert transition['prior_source_sha256'] == collect.digest(prior)
    projected = prior
    for projector in PROJECTORS:
        projected = projector.project_current_source(branch, projected)
    canonical = lambda value: json.loads(json.dumps(value,ensure_ascii=False,allow_nan=False))
    assert canonical(projected) == new, 'DECLARED_SOURCE_PROJECTION_NOT_REPRODUCIBLE'
    return {'status': 'PASS', 'policy': PROJECTION_POLICY,
            'producer_version': metadata_source.VERSION,
            'full_projection_replayed': True, 'raw_source_text_unchanged': True,
            'prior_source_sha256': collect.digest(prior),
            'baseline_projection_history_retained_not_replayed': True,
            'derived_operation_view_not_mistaken_for_raw_answer_edit': True}


def validate(old, new, allowed_changed_metrics=None, *, causes=None, source_projection=None, job=None, provider_output=None):
    assert old['status'] == new['status'] == 'PASS'
    assert key(old) == key(new)
    for row in (old, new):
        assert row['normal_pipeline_evaluate_called'] is True
        assert row['whole_components_used_as_observations'] is False
    old_folder, new_folder = [Path(r['result_path']).parent for r in (old, new)]
    assert eq.case_identity(read(old_folder/'case.json')) == eq.case_identity(read(new_folder/'case.json'))
    assert read(old_folder/'request.json') == read(new_folder/'request.json')
    sources = [read(p/'execution_scope.json') for p in (old_folder, new_folder)]
    transition = read(new_folder/'common_source_transition.json')
    assert transition['common_projection_reproduced'] is True
    assert transition['actual_encoder_cells_and_receipts_revalidated_by_normal_consumer'] is True
    assert transition['current_source_sha256'] == collect.digest(sources[1])
    assert transition['ordered_encoder_texts_exact'] or transition['source_domain_reindex'] is not None
    projection_proof = None
    if sources[0] != sources[1]:
        assert isinstance(source_projection,dict) and source_projection.get('policy') == PROJECTION_POLICY and job is not None, 'UNDECLARED_SOURCE_PROJECTION'
        prior_path = Path(source_projection['prior_source_path'])
        assert sha(prior_path) == source_projection['prior_source_sha256'], 'REPLAY_PRIOR_SOURCE_CHANGED'
        prior = read(prior_path)
        with source_entry.prepare_branch(job, provider_output) as branch:
            projection_proof = validate_source_projection(branch, sources[0], prior, sources[1], transition)
    else:
        literal = lambda source: [{k: r.get(k) for k in LITERAL_FIELDS} for r in source['all_typed_rows']]
        assert literal(sources[0]) == literal(sources[1]), 'LITERAL_OPERATION_CONTENT_CHANGED'
    result = collect.projection.score_result(new['result_path'], expected_sha256=new['result_sha256'], metrics=collect.METRICS)
    nodes = {k: result['components'][k] if k in collect.COMPONENTS else result['aggregates'][k] for k in collect.METRICS}
    assert {k: collect.digest(v) for k, v in nodes.items()} == new['all17_full_node_sha256']
    assert result['normal_component_composition']['evaluation_origin'] == 'NORMAL_PIPELINE_EVALUATE'
    collect.verify_score_graph(result, nodes)
    allowed = resolve_changed_metrics(causes, allowed_changed_metrics)
    assert sources[0] == sources[1] or projection_proof is not None, 'COMPONENT_ONLY_REVISION_CHANGED_SHARED_SOURCE_WITHOUT_REPLAY'
    independent = set(collect.METRICS) - allowed
    for name in independent:
        assert old['all17'][name] == new['all17'][name], ('INDEPENDENT_SCORE_CHANGED', name)
    return {'original_case_request_reference_and_literal_operations_exact': True,
            'current_shared_source_reproduced_by_normal_runner': True,
            'all17_full_nodes_verified': True,
            'actual_encoder_cells_revalidated': True,
            'changed_score_nodes': [k for k in collect.METRICS if old['all17'][k] != new['all17'][k]],
            'selection_uses_score_direction': False,
            'explicit_component_change_closure': sorted(allowed),
            'causes': list(causes), 'cause_closure_policy': CAUSE_CLOSURE_POLICY,
            'shared_source_exact_for_component_only_revision': sources[0] == sources[1],
            'source_projection_validation': projection_proof}


def apply(base, output, affected, roots):
    assert not output.exists()
    plan, prior = [read(base/name) for name in ('plan193.json', 'records193.json')]
    assert len(plan) == len(prior) == 193 and [key(x) for x in plan] == [key(x) for x in prior]
    assert all(x['status'] == 'PASS' for x in prior)
    selected = read(affected)
    rules = {key(x): x for x in selected}
    assert len(rules) == len(selected)
    expected, records = {key(x): x for x in plan}, {key(x): x for x in prior}
    assert set(rules) <= set(records)
    pins = resolve_prior_pins(read(base/'input_and_code_sha256.json'), selected, roots)
    for name in ('plan193.json', 'records193.json', 'summary.json', 'repairs_and_revisions.json', 'revision_plan.json', 'input_and_code_sha256.json'):
        pins[str(base/name)] = sha(base/name)
    pins[str(affected)] = sha(affected)
    history = read(base/'repairs_and_revisions.json')
    applied = set()
    for root in roots:
        declared, rows = [read(root/name) for name in ('plan193.json', 'records193.json')]
        assert [key(x) for x in declared] == [key(x) for x in rows]
        for item, row in zip(declared, rows):
            k = key(row)
            assert item == expected[k] and k in rules and k not in applied
            rule = rules[k]
            proof = validate(records[k], row, rule.get('allowed_changed_metrics'), causes=rule['causes'],
                source_projection=rule.get('source_projection'), job=rule.get('job'),
                provider_output=output/'projection_provider'/k[0]/k[1])
            history.append({'input_id': k[0], 'branch': k[1], 'kind': 'DECLARED_COMMON_SOURCE_REVISION',
                            'causes': rule['causes'], 'initial_record': records[k],
                            'replacement_record': row, 'replacement_root': str(root), 'revision_validation': proof})
            records[k] = row
            applied.add(k)
            print('VERIFIED', *k, flush=True)
        for name in ('data_input_sha256.json', 'loaded_code_sha256.json'):
            for path, pin in read(root/name).items():
                assert path not in pins or pins[path] == pin, ('SHARED_PIN_CONFLICT', path)
                assert sha(path) == pin, ('REPLAY_PIN_CHANGED', path)
                pins[path] = pin
        for name in ('plan193.json', 'records193.json', 'summary.json'):
            pins[str(root/name)] = sha(root/name)
    assert applied == set(rules), 'INCOMPLETE_CAUSE_SELECTED_REPLAY'
    ordered = [records[key(x)] for x in plan]
    for row in ordered:
        assert sha(row['result_path']) == row['result_sha256']
    save(output/'plan193.json', plan)
    save(output/'records193.json', ordered)
    save(output/'repairs_and_revisions.json', history)
    save(output/'revision_plan.json', {'kind': 'SHARED_SOURCE_NORMAL_REPLAY', 'prior_collection': str(base),
                                      'affected_plan': str(affected), 'revisions': selected})
    save(output/'execution_provenance193.json', [
        {'input_id': x['input_id'], 'branch': x['branch'],
         'reexecuted_in_latest_revision': key(x) in applied,
         'retained_verified_unaffected_normal_result': key(x) not in applied} for x in ordered])
    pins[str(Path(__file__).resolve())] = sha(__file__)
    save(output/'input_and_code_sha256.json', pins)
    summary = {'status': 'PASS', 'branches': 193, 'answers': 185,
               'counts': dict(Counter(x['status'] for x in ordered)),
               'reexecuted_branches': len(applied), 'retained_unaffected_normal_branches': 193-len(applied),
               'best_score_selection_used': False, 'historical_score_fallback_used': False,
               'new_model_calls_in_collection': 0, 'new_encoder_calls_in_collection': 0}
    save(output/'summary.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--affected-plan', type=Path, required=True)
    p.add_argument('--revision-root', type=Path, nargs='+', required=True)
    a = p.parse_args()
    apply(a.base.resolve(), a.output.resolve(), a.affected_plan.resolve(), [p.resolve() for p in a.revision_root])
