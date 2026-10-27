"""Consume complete, source-bound parameter reviews without changing other leaves."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import traceback

if __package__:
    from .component39_joint_scope_v1.router import namespace as router_namespace
    from ..parameter_joint_reference_scope_v1 import normal_candidate as joint
    from ..parameter_partial_transport_subset_v1 import normal_adapter as partial_adapter, reader as partial_reader
    from ..parameter_atomic_multisource_v2 import normal_adapter as multi_adapter
    from ..parameter_atomic_multisource_v1 import reader as origin_reader
    from ..parameter_contract_dispatch_v1 import dispatch
    from .uniform_normal_runner_v1 import criteria_loader as C
else:
    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE.parents[1]))
    from execution_alignment_resolution_20261024_v1.runtime.component39_joint_scope_v1.router import namespace as router_namespace
    from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
    from execution_alignment_resolution_20261024_v1.parameter_partial_transport_subset_v1 import normal_adapter as partial_adapter, reader as partial_reader
    from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import normal_adapter as multi_adapter
    from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v1 import reader as origin_reader
    from execution_alignment_resolution_20261024_v1.parameter_contract_dispatch_v1 import dispatch
    from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C

NATIVE = joint.parameter.native_backend
PARTIAL = partial_adapter.namespace(NATIVE, declared_policy_version=partial_reader.VERSION)
MULTI = multi_adapter.namespace(PARTIAL, declared_policy_version=multi_adapter.reader.VERSION)
API = dispatch.wrap(router_namespace(NATIVE, PARTIAL, MULTI))
SOURCE_POLICY = multi_adapter.reader.VERSION
BRANCHES = ('CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', 'CUBIC_2019_IMMERSION_L_R_PLUS')
read, save, sha = C.read, C.save, C.sha


def full_origin(plan, job, actual):
    actual = Path(actual).resolve()
    completed = read(actual / 'completed.json')
    started = read(actual / 'started.json')
    assert completed['input_id'] == started['input_id'] == job['input_id']
    assert completed['run_id'] == started['run_id']
    assert completed['status'] == 'RESPONSE_TERMINAL' and completed['call_failure'] is None
    assert completed['actual_judge_calls'] == 1 and completed['response_saved']
    assert completed['automatic_retry'] is False
    spec = {'review_directory': str(actual / 'review'), 'model_settings': plan['model_settings'],
        'run_id': started['run_id'], 'payload_sha256': job['payload_sha256'],
        'transport_policy': origin_reader.FULL}
    origin = origin_reader._origin(spec)
    prefix = origin['prefix']
    assert origin['whole_provider_response_complete'] is True
    assert prefix['root_json_closed'] and not prefix['missing_query_ids']
    assert prefix['complete_query_count'] == len(origin['actual_wrapped']['payload']['queries'])
    assert origin['actual_provider_receipt']['done_reason'] == 'stop'
    assert origin['actual_provider_receipt']['automatic_retries'] == 0
    return origin


def consume_branch(plan_path, actual_root, baseline_root, output):
    plan_path, actual_root, output = Path(plan_path).resolve(), Path(actual_root).resolve(), Path(output).resolve()
    assert not output.exists()
    plan = C.read(plan_path)
    assert plan['version'] == 'bounded-independent-query-batches-for-complete-reference-target-v1'
    source_dir = Path(plan['partition']['source_directory'])
    branch = source_dir.name
    case, source, request = [read(source_dir / (name + '.json'))
        for name in ('case', 'execution_scope', 'request')]
    prepared = read(source_dir / 'prepared_parameter.json')
    fresh = API.prepare(case, source, request)
    assert fresh == prepared and fresh['status'] == 'PREPARED'
    assert len(fresh['requests']) == 1
    key, target = next(iter(fresh['requests'].items()))
    assert key == plan['partition']['full_target_payload_sha256']
    assert len(plan['schedule']) == len(plan['partition']['chunk_query_counts'])
    assert sum(plan['partition']['chunk_query_counts']) == len(target['payload']['queries']) == plan['partition']['original_query_count']
    assert all(0 < count <= 12 for count in plan['partition']['chunk_query_counts'])
    origins = [full_origin(plan, job, actual_root / job['input_id']) for job in plan['schedule']]
    sources = [origin['source_spec'] for origin in origins]
    certificate = multi_adapter.reader.audit(target, sources, declared_policy_version=SOURCE_POLICY)
    assert certificate['complete_target_query_count'] == len(target['payload']['queries'])
    assert certificate['origin_count'] == len(plan['schedule'])
    assert certificate['single_provider_response_claimed'] is False
    review_sources = {key: {multi_adapter.POLICY_FIELD: SOURCE_POLICY, 'sources': sources}}
    records = read(Path(baseline_root) / 'records193.json')
    record = next(row for row in records if row['input_id'] == 'EXPAND_148' and row['branch'] == branch)
    result_path = Path(record['result_path'])
    result_path = result_path if result_path.is_absolute() else C.RES.parent / result_path
    assert sha(result_path) == record['result_sha256']
    original = read(result_path)
    before = C.digest(original)
    assert [case, source, request] == [read(result_path.parent / (name + '.json'))
        for name in ('case', 'execution_scope', 'request')]
    packet = API.consume(case, source, request, prepared, normal_result=original, review_sources=review_sources)
    assert packet['complete_target_query_coverage'] is True
    assert packet['single_provider_response_claimed'] is False
    assert packet['actual_private_core_consumption']['global_core_fallback_used'] is False
    assert len(packet['world_observations']) == fresh['source_world_count']
    assert all(world['strict_slots_all_valid'] for world in packet['actual_private_core_consumption']['worlds'])
    assert [world['world_id'] for world in packet['world_observations']] == [world['world_id'] for world in fresh['binding']['worlds']]
    for observed, expected in zip(packet['world_observations'], fresh['binding']['worlds']):
        assert observed['slots'] == expected['slots']
    component = packet['component']
    bounds = component.get('bounds')
    assert component['status'] in ('VALID', 'UNKNOWN') and component['complete_bounds_available'] is True
    assert isinstance(bounds, list) and len(bounds) == 2
    assert all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 3 for value in bounds)
    assert bounds[0] <= bounds[1]
    if component['status'] == 'VALID':
        assert component['value'] == bounds[0] == bounds[1]
    applied = API.apply(original, packet, case=case, source=source, original_request=request)
    assert C.digest(original) == before
    assert all(applied['components'][key] == value for key, value in original['components'].items() if key != 'c_param')
    assert applied['aggregates'] == original['aggregates']
    assert applied.get('execution_alignment') == original.get('execution_alignment')
    assert applied.get('supplementary_components') == original.get('supplementary_components')
    checked = API.revalidate_parameter_graph(applied, case, source, request)
    assert checked['packet']['component'] == packet['component']
    assert checked['packet']['world_observations'] == packet['world_observations']
    assert checked['packet']['consumer_receipts'] == packet['consumer_receipts']
    assert checked['packet']['atomic_multi_origin_certificate_sha256'] == packet['atomic_multi_origin_certificate_sha256']
    assert checked['packet']['actual_private_core_consumption'] == packet['actual_private_core_consumption']
    assert checked['packet']['normal_dependency_graph_sha256'] == C.digest(applied['dependency_graph'])
    if component['status'] == 'UNKNOWN':
        assert checked['certificate'] is not None and checked['certificate']['bounds'] == bounds
    for name, value in [('prepared_parameter.json', prepared), ('review_sources.json', review_sources),
            ('certificate.json', certificate), ('packet.json', packet), ('applied.json', applied),
            ('revalidation.json', checked)]:
        save(output / name, value)
    summary = {'status': 'PASS', 'input_id': 'EXPAND_148', 'branch': branch,
        'actual_judge_calls': len(sources), 'actual_review_run_ids': [source['run_id'] for source in sources],
        'origin_query_counts': [len(origin['actual_wrapped']['payload']['queries']) for origin in origins],
        'target_queries': certificate['complete_target_query_count'],
        'strict_worlds': len(packet['world_observations']), 'all_strict_slots_valid': True,
        'parameter_status': component['status'], 'parameter_grade': component.get('value'),
        'parameter_bounds': bounds, 'parameter_reason': component.get('reason'),
        'other_12_leaf_nodes_Co_Eff_EA_supplementary_exact': True,
        'native_revalidation_passed': True, 'disjoint_complete_query_partition_verified': True,
        'failed_full_response_consumed': False, 'new_model_calls_in_validation': 0,
        'new_encoder_calls': 0, 'full_normal_pipeline_executed': False,
        'accepted_for_normal_replay': True, 'accepted_for_scoring': False,
        'baseline_result_path': str(result_path), 'baseline_result_sha256': record['result_sha256'],
        'review_sources': 'review_sources.json', 'review_sources_sha256': sha(output / 'review_sources.json')}
    save(output / 'summary.json', summary)
    C.capture_code_pins()
    pins = dict(C.PINS)
    pins.update(C.CODE_PINS)
    for source_pins in [plan['source_sha256'], *[origin['source_files'] for origin in origins]]:
        for path, expected in source_pins.items():
            assert pins.setdefault(path, expected) == expected
    pins[str(Path(__file__).resolve())] = sha(__file__)
    save(output / 'input_and_code_sha256.json', pins)
    save(output / 'manifest.json', {str(path.relative_to(output)): sha(path)
        for path in output.rglob('*') if path.is_file()})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--plans-root', type=Path, required=True)
    parser.add_argument('--actual-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    staging = output.with_name(output.name + '_incomplete')
    assert not output.exists() and not staging.exists()
    branches = []
    try:
        execution = read(args.actual_root / 'execution.json')
        assert execution['status'] == 'ALL_BATCHES_TERMINAL_NOT_CONSUMED'
        assert execution['actual_judge_calls'] == 7 and execution['all_response_terminal'] is True
        assert execution['automatic_retry'] is False
        records = read(args.baseline_root / 'records193.json')
        assert len(records) == 193 and all(record['status'] == 'PASS' for record in records)
        for branch in BRANCHES:
            summary = consume_branch(args.plans_root / branch / 'plan.json',
                args.actual_root / branch, args.baseline_root, staging / branch)
            branches.append({**summary, 'review_sources': branch + '/review_sources.json'})
        assert len(branches) == 2
        summary = {'status': 'PASS', 'input_id': 'EXPAND_148',
            'actual_judge_calls': sum(branch['actual_judge_calls'] for branch in branches),
            'target_queries': sum(branch['target_queries'] for branch in branches),
            'origin_query_counts': [count for branch in branches for count in branch['origin_query_counts']],
            'strict_worlds': sum(branch['strict_worlds'] for branch in branches),
            'all_strict_slots_valid': all(branch['all_strict_slots_valid'] for branch in branches),
            'parameter_status_by_branch': {branch['branch']: branch['parameter_status'] for branch in branches},
            'parameter_grade_by_branch': {branch['branch']: branch['parameter_grade'] for branch in branches},
            'parameter_bounds_by_branch': {branch['branch']: branch['parameter_bounds'] for branch in branches},
            'other_12_leaf_nodes_Co_Eff_EA_supplementary_exact': all(
                branch['other_12_leaf_nodes_Co_Eff_EA_supplementary_exact'] for branch in branches),
            'native_revalidation_passed': all(branch['native_revalidation_passed'] for branch in branches),
            'disjoint_complete_query_partition_verified': True,
            'failed_full_response_consumed': False, 'new_model_calls_in_validation': 0,
            'new_encoder_calls': 0, 'full_normal_pipeline_executed': False,
            'accepted_for_normal_replay': True, 'accepted_for_scoring': False,
            'main_table_promoted': False, 'baseline_root': str(args.baseline_root.resolve()),
            'branches': branches}
        save(staging / 'summary.json', summary)
        pins = {}
        for branch in branches:
            for path, expected in read(staging / branch['branch'] / 'input_and_code_sha256.json').items():
                assert pins.setdefault(path, expected) == expected
        for path in [args.actual_root / 'execution.json', args.actual_root / 'authorization.json',
                args.actual_root.parent / 'run_actual_v2.py',
                args.actual_root.parent.parent / 'review_snapshot_v1/deepseek_v41_flash_review_v4.md',
                args.actual_root.parent.parent / 'review_snapshot_v1/full_regression54.log']:
            pins[str(path.resolve())] = sha(path)
        save(staging / 'input_and_code_sha256.json', pins)
        save(staging / 'manifest.json', {str(path.relative_to(staging)): sha(path)
            for path in staging.rglob('*') if path.is_file()})
        staging.rename(output)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    except Exception as error:
        save(staging / 'failure.json', {'type': type(error).__name__, 'reason': str(error),
            'traceback': traceback.format_exc(), 'accepted_for_scoring': False})
        save(staging / 'summary.json', {'status': 'INCOMPLETE_NOT_ACCEPTED',
            'accepted_for_scoring': False, 'branches_completed': [branch['branch'] for branch in branches],
            'main_table_promoted': False})
        raise


if __name__ == '__main__':
    main()
