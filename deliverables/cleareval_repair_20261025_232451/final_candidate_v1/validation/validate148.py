"""Revalidate the two EXPAND_148 branches without changing scores or receipts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

H = Path('C:/ClearEval/ClearEval-runtime-4b42b5a/research/evaluator-research-cycle-20261018')
E = H / 'execution_alignment_resolution_20261024_v1'
O = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451')
sys.path.insert(0, str(H))
sys.path.insert(0, str(E / 'runtime'))
from execution_alignment_resolution_20261024_v1.runtime import normal_revision_equivalence_v1 as equivalence
from execution_alignment_resolution_20261024_v1.runtime.phase_world_operational_scope_v2 import execution as final_ea
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry
from execution_alignment_resolution_20261024_v1.runtime import aggregate_score_bounds_v3 as aggregates

CARRIER_FIELDS = ('phase_operation_carrier_audit', 'phase_operation_carrier_audit_sha256',
                  'phase_operation_carrier_private_projection')
DIAGNOSTIC_ORIGINS = {
    'original_repeated_container_references': (
        'pure_ea_cache_v1/cache.py:29-46: repeated Python containers before JSON-tree conversion; '
        'the canonical five inputs, not this alias count, determine the cache key'),
    'internal_prior_issued_plan_entries': (
        'pure_ea_cache_v1/cache.py:203-204: len(shared_phase_worlds_v3._ISSUED) at lookup; '
        'a process-history diagnostic, not one of the five score inputs'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(root, path):
    path = Path(path)
    path = path if path.is_absolute() else root / path
    return json.loads(path.read_text(encoding='utf-8'))


def pure_ea(packet):
    result = copy.deepcopy(packet)
    for key in ('private_ea_execution_receipt', 'ordinary_ea_reuse_receipt',
                'phase_world_operation_carrier_receipt'):
        result.pop(key, None)
    return result


def diagnostic(path, value):
    assert type(value) is int and value >= 0
    return {'path': path, 'value': value, 'code_origin': DIAGNOSTIC_ORIGINS[path.rsplit('/', 1)[-1]]}


def private_projection(packet):
    value = copy.deepcopy(packet)
    removed = [diagnostic('/private_ea_execution_receipt/input_normalization/original_repeated_container_references',
                          value['input_normalization'].pop('original_repeated_container_references'))]
    for key in CARRIER_FIELDS:
        value['final_callable_binding'].pop(key, None)
    for index, lookup in enumerate(value['ordinary_cache_admission_proof']['catalog_lookups']):
        count = lookup.pop('internal_prior_issued_plan_entries')
        removed.append(diagnostic(
            f'/private_ea_execution_receipt/ordinary_cache_admission_proof/catalog_lookups/{index}/internal_prior_issued_plan_entries', count))
    return value, removed


def reuse_projection(packet):
    value = copy.deepcopy(packet)
    assert value['global_cache_context_used'] is False
    assert value['ordinary_17_scores_read_or_reused'] is False
    removed = []
    for index, lookup in enumerate(value['catalog_lookups']):
        count = lookup.pop('internal_prior_issued_plan_entries')
        removed.append(diagnostic(
            f'/ordinary_ea_reuse_receipt/catalog_lookups/{index}/internal_prior_issued_plan_entries', count))
    return value, removed


def compare_receipts(before, after, projector):
    old, old_removed = projector(before)
    new, new_removed = projector(after)
    assert old == new, 'UNDECLARED_RECEIPT_CHANGE'
    assert [x['path'] for x in old_removed] == [x['path'] for x in new_removed]
    differences = []
    for previous, current in zip(old_removed, new_removed):
        assert previous['code_origin'] == current['code_origin']
        differences.append({'path': previous['path'], 'before': previous['value'],
                            'after': current['value'], 'code_origin': previous['code_origin']})
    return differences


def validate_record(row, baseline_row, plan):
    name = row['branch']
    result = read(H, row['result_path'])
    baseline = read(H, baseline_row['result_path'])
    assert sha(row['result_path']) == row['result_sha256']
    old_path = Path(baseline_row['result_path'])
    old_path = old_path if old_path.is_absolute() else H / old_path
    assert sha(old_path) == baseline_row['result_sha256']
    folder = Path(row['result_path']).parent
    case, source, request, times, preparation = [
        read(H, folder / (key + '.json'))
        for key in ('case', 'execution_scope', 'request', 'source_time_facts', 'preparation')]
    baseline_case = read(H, old_path.parent / 'case.json')
    assert source == read(H, old_path.parent / 'execution_scope.json')
    assert request == read(H, old_path.parent / 'request.json')
    assert times == read(H, old_path.parent / 'source_time_facts.json')
    assert sha(case['reference']['file']['path']) == sha(baseline_case['reference']['file']['path'])
    assert case['reference']['file']['sha256'] == baseline_case['reference']['file']['sha256']
    expected_case = copy.deepcopy(baseline_case)
    expected_case['reference']['file']['path'] = case['reference']['file']['path']
    assert case == expected_case
    old_preparation = read(H, old_path.parent / 'preparation.json')
    variables = [p['capacity_input'].get('variable_source_operations', [])
                 for p in (preparation, old_preparation)]
    assert variables[0] == variables[1]
    job = next(r for r in plan if r['input_id'] == 'EXPAND_148' and r['branch'] == name)['job']
    bundle = read(H, job['bundle_path']) if job.get('bundle_path') else {}
    values, _, namespace, fn, facts = final_ea.prepare(
        source, case['protocol'], times, variable_source_operations=variables[0],
        family_id=bundle.get('spec', {}).get('reference_id'))
    assert fn is namespace.calculate is final_ea.E.boundary.ORIGINAL_CALCULATE
    assert fn.__globals__['runtime'] is namespace.runtime
    actual, prior = result['execution_alignment'], baseline['execution_alignment']
    receipt = actual['private_ea_execution_receipt']
    old_receipt = prior['private_ea_execution_receipt']
    assert facts == receipt['final_callable_binding']
    assert receipt['canonical_five_input_sha256'] == old_receipt['canonical_five_input_sha256'] == final_ea.E.digest(values)
    assert receipt['input_field_sha256'] == old_receipt['input_field_sha256'] == {
        key: final_ea.E.digest(value) for key, value in values.items()}
    assert old_receipt['final_callable_binding'] == {
        key: value for key, value in facts.items() if key not in CARRIER_FIELDS}
    new_pure, old_pure = pure_ea(actual), pure_ea(prior)
    assert receipt['pure_result_sha256_before_receipt'] == old_receipt['pure_result_sha256_before_receipt'] == final_ea.E.digest(new_pure)
    assert equivalence.ea_identity(new_pure) == equivalence.ea_identity(old_pure)
    carrier = actual['phase_world_operation_carrier_receipt']
    assert 'phase_world_operation_carrier_receipt' not in prior
    assert carrier['projection_causal_change'] is False
    assert carrier['schema_bound_private_world_projector_used'] is False
    assert carrier['same_original_final_callable_preserved'] is True
    assert carrier['source_values_unchanged'] is True
    assert carrier['canonical_five_input_sha256'] == receipt['canonical_five_input_sha256']
    assert carrier['source_sha256'] == receipt['input_field_sha256']['source']
    assert carrier['projection_domain_proof_sha256'] == facts['phase_operation_carrier_audit_sha256'] == final_ea.E.digest(facts['phase_operation_carrier_audit'])
    differences = compare_receipts(old_receipt, receipt, private_projection)
    differences += compare_receipts(prior['ordinary_ea_reuse_receipt'],
                                    actual['ordinary_ea_reuse_receipt'], reuse_projection)
    assert differences and all(x['before'] != x['after'] for x in differences)
    expected_supplementary = copy.deepcopy(baseline['supplementary_components'])
    label_changes = {}
    for metric in ('ea_p', 'ea_r', 'ea_f1'):
        label_changes[metric] = {'before': expected_supplementary[metric]['metric_version'],
                                 'after': entry.source_entry.VERSION}
        expected_supplementary[metric]['metric_version'] = entry.source_entry.VERSION
    assert result['supplementary_components'] == expected_supplementary
    formula = aggregates.evaluate(
        result['components'], certificates=result['normal_component_aggregate_evidence']['certificates'],
        protocol_sha256=case['protocol_sha256'])
    assert all(result['aggregates'][metric] == formula['aggregates'][metric]
               for metric in ('Com', 'IA'))
    assert all(result['components'][key] == value
               for key, value in baseline['components'].items() if key != 'c_param')
    assert all(result['aggregates'][metric] == baseline['aggregates'][metric]
               for metric in ('Co', 'Eff'))
    worlds = []
    for world in result['components']['c_param']['world_grade_envelopes']:
        grade = world['grade_envelope']
        assert grade['original_complete_state_grading_formula_sha256'] == formula['formula_sha256']
        assert grade['point_invariant_over_outer_set'] is True
        assert grade['unknown_items_filled'] is False
        assert grade['bounds_endpoints_jointly_source_certified'] is False
        worlds.append({'world_id': world['world_id'], 'denominator': grade['denominator'],
                       'present': grade['present'], 'unresolved': grade['unresolved'],
                       'grade_bounds': grade['bounds'], 'point_invariant_over_outer_set': True,
                       'unknown_items_filled': False,
                       'bounds_endpoints_jointly_source_certified': False})
    return {'branch': name, 'result_sha256': row['result_sha256'],
            'canonical_five_input_sha256': receipt['canonical_five_input_sha256'],
            'input_field_sha256': receipt['input_field_sha256'],
            'pure_result_sha256_before_receipt': receipt['pure_result_sha256_before_receipt'],
            'actual_final_callable_and_runtime_reproduced': True,
            'ea_metrics_unchanged': actual['metrics'] == prior['metrics'],
            'carrier_additions': {'fields': list(CARRIER_FIELDS) + ['phase_world_operation_carrier_receipt'],
                                  'projection_causal_change': False,
                                  'schema_bound_private_world_projector_used': False,
                                  'source_values_unchanged': True,
                                  'proof_sha256': carrier['projection_domain_proof_sha256']},
            'diagnostic_differences': differences,
            'all_other_ea_receipt_fields_exact': True,
            'supplementary_version_label_changes_only': label_changes,
            'c_param': {key: result['components']['c_param'][key]
                        for key in ('status', 'value', 'bounds', 'reason')},
            'world_grade_envelopes': worlds,
            'Com_IA_original_formula_replay_exact': True,
            'other_12_leaf_and_Co_Eff_exact': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    baseline_rows = read(H, O / 'merge_stage1/merged193_v4/records193.json')
    plan = read(H, E / 'runtime/uniform_normal_runner_v1/inventory_v3/plan193.json')
    rows = read(H, O / 'parameter_scope148/normal_v2/records193.json')
    assert len(rows) == 2
    records = []
    for row in rows:
        baseline_row = next(r for r in baseline_rows
                            if r['input_id'] == 'EXPAND_148' and r['branch'] == row['branch'])
        records.append(validate_record(row, baseline_row, plan))
    report = {
        'status': 'PASS',
        'scope': 'EXPAND_148_TWO_REFERENCE_BRANCH_EA_AND_AGGREGATE_EVIDENCE',
        'branches': records,
        'new_scoring_model_calls': 0,
        'new_encoder_calls': 0,
        'ea_identity_only_removes_finite_nonnegative_elapsed_seconds': True,
        'raw_pure_result_hash_includes_the_saved_original_elapsed_value': True,
        'diagnostic_fields_are_not_arbitrarily_removed_from_original_artifacts': True,
        'original_result_and_receipt_hashes_reverified': True,
        'parameter_grade_is_bucket_invariant_not_all_leaves_resolved': True,
        'outer_intervals_do_not_claim_joint_endpoint_attainability': True,
        'expert_accuracy_evaluated': False,
        'full_regression_acceptance': 'SEPARATE_PENDING_GATE_AT_GENERATION',
        'code_pins': {str(path): sha(path) for path in (
            E / 'runtime/pure_ea_cache_v1/cache.py',
            E / 'runtime/normal_revision_equivalence_v1.py',
            E / 'runtime/aggregate_score_bounds_v3.py',
            E / 'runtime/component_entry_v40.py',
            Path(aggregates.scoring_core.__file__),
            Path('C:/ClearEval/ClearEval-runtime-4b42b5a/tests/test_uniform_normal_repairs.py'),
            Path(__file__).resolve(),
        )},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': report['status'],
                      'branches': [{'branch': r['branch'],
                                    'worlds': len(r['world_grade_envelopes']),
                                    'diagnostic_differences': len(r['diagnostic_differences']),
                                    'c_param': r['c_param']['value'],
                                    'pure_result_sha256': r['pure_result_sha256_before_receipt']}
                                   for r in records],
                      'code_pin_count': len(report['code_pins']),
                      'output': str(output), 'sha256': sha(output)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
