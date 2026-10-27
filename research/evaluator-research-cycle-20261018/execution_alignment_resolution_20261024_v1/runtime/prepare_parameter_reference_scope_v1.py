"""Bounded independent query batches for one complete source-world target."""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from . import minimal_instance_review_v2 as minimal
    from ..parameter_atomic_multisource_v1 import reader as multi
    from ..parameter_joint_reference_scope_v1 import normal_candidate as joint
    from parameter_execution_unit_contract_20261025_v1.source_units import digest
else:
    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE.parents[1]))
    from execution_alignment_resolution_20261024_v1.runtime import minimal_instance_review_v2 as minimal
    from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v1 import reader as multi
    from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
    from parameter_execution_unit_contract_20261025_v1.source_units import digest

read, sha, save = minimal.read, minimal.sha, minimal.save
VERSION = 'bounded-independent-query-batches-for-complete-reference-target-v1'
PARAMETER_MODULE = joint.__name__
PARTITION = 'COMPLETE_DISJOINT_ORDERED_QUERY_PARTITION_WITH_FULL_PROTOCOL_AND_INDEPENDENT_SCHEMA'


def verify_plan(plan_path):
    plan_path = Path(plan_path).resolve()
    plan = minimal.transport.legacy.verify(plan_path)
    assert plan['version'] == VERSION and plan['parameter_module'] == PARAMETER_MODULE
    assert plan['full_request_count'] == 1 and plan['source_world_count'] > 0
    assert plan['maximum_new_judge_calls'] == len(plan['schedule'])
    assert plan['maximum_new_encoder_calls'] == plan['maximum_new_canonical_calls'] == 0
    assert plan['automatic_retry'] is False and plan['new_model_calls'] == 0
    assert plan['all_source_worlds_retained'] and plan['original_answer_not_regenerated']
    assert plan['reused_reviews'] == [] and plan['reused_review_sources'] == {}
    partition = plan['partition']
    assert partition['kind'] == PARTITION
    source_dir = Path(partition['source_directory']).resolve()
    case, source, request = [read(source_dir / (name + '.json'))
        for name in ('case', 'execution_scope', 'request')]
    archive = Path(case['source_binding']['path'])
    assert sha(archive) == case['source_binding']['sha256']
    original = read(archive)[case['source_binding']['record_index']]
    assert original['model_response'] == case['protocol']
    fresh = joint.prepare(case, source, request)
    saved = read(source_dir / 'prepared_parameter.json')
    assert fresh == saved and fresh['status'] == 'PREPARED'
    assert len(fresh['requests']) == 1
    key, expected_target = next(iter(fresh['requests'].items()))
    target = read(partition['full_target_request_path'])
    assert target == expected_target and key == partition['full_target_payload_sha256']
    assert key == digest(target['payload']) == target['source_payload_sha256']
    assert plan['source_world_count'] == fresh['source_world_count']
    target_ids = [query['id'] for query in target['payload']['queries']]
    assert partition['original_query_ids'] == target_ids
    assert len(target_ids) == partition['original_query_count']
    assert target['payload']['protocol'] == case['protocol']
    observed = []
    counts = []
    for job in plan['schedule']:
        assert job['answer_id'] == case['case_id']
        assert Path(job['source_directory']).resolve() == source_dir
        assert job['maximum_new_judge_calls'] == 1
        assert job['maximum_new_encoder_calls'] == job['maximum_new_canonical_calls'] == 0
        request_path = Path(job['request']).resolve()
        wrapped = read(request_path)
        minimal.cache.validate_wrapped(wrapped)
        assert job['payload_sha256'] == wrapped['source_payload_sha256']
        assert plan['source_sha256'][str(request_path)] == sha(request_path)
        ids = [query['id'] for query in wrapped['payload']['queries']]
        assert ids and len(ids) <= 12 and len(ids) == wrapped['payload']['denominator']
        assert wrapped['payload']['protocol'] == target['payload']['protocol']
        proof = multi.partial.subset.prove(wrapped, target)
        assert proof == read(job['subset_proof_path'])
        assert proof['query_ids'] == ids
        observed.extend(ids)
        counts.append(len(ids))
    assert len(observed) == len(set(observed))
    assert observed == target_ids, 'COMPLETE_TARGET_QUERY_PARTITION_CHANGED'
    assert counts == partition['chunk_query_counts']
    assert minimal.transport.legacy.verify(plan_path) == plan
    return {'status': 'PREPARED_NOT_RUN', 'input_id': case['case_id'],
        'full_target_queries': len(target_ids), 'chunk_query_counts': counts,
        'disjoint_complete_query_partition': True, 'source_worlds': fresh['source_world_count'],
        'planned_judge_calls': len(counts), 'new_model_calls': 0,
        'model_score_generated': False, 'plan_sha256': sha(plan_path)}


def prepare(source_dir, output, *, chunk_size=12, cache_index=None):
    source_dir, output = Path(source_dir).resolve(), Path(output).resolve()
    assert not output.exists()
    assert type(chunk_size) is int and 1 <= chunk_size <= 12
    exact_output = output / 'exact_target'
    exact = minimal.prepare(source_dir, exact_output, PARAMETER_MODULE, cache_index=cache_index)
    assert len(exact['schedule']) == 1 and exact['maximum_new_judge_calls'] == 1
    assert not exact['reused_reviews'] and not exact['reused_review_sources']
    target_job = exact['schedule'][0]
    target_path = Path(target_job['request']).resolve()
    target = read(target_path)
    key = target_job['payload_sha256']
    assert key == target['source_payload_sha256'] == digest(target['payload'])
    ids = [query['id'] for query in target['payload']['queries']]
    groups = [ids[index:index + chunk_size] for index in range(0, len(ids), chunk_size)]
    pins = dict(exact['source_sha256'])
    schedule = []
    for number, query_ids in enumerate(groups, 1):
        chunk_id = source_dir.name + '_CHUNK_' + str(number).zfill(2)
        wrapped = multi.project_request(target, query_ids)
        proof = multi.partial.subset.prove(wrapped, target)
        request_path = (output / 'prepared' / chunk_id / 'request.json').resolve()
        proof_path = (output / 'proofs' / (chunk_id + '.json')).resolve()
        save(request_path, wrapped)
        save(proof_path, proof)
        pins[str(request_path)] = sha(request_path)
        pins[str(proof_path)] = sha(proof_path)
        schedule.append({**target_job, 'input_id': chunk_id, 'request': str(request_path),
            'payload_sha256': wrapped['source_payload_sha256'], 'subset_proof_path': str(proof_path),
            'maximum_new_judge_calls': 1})
    exact_plan_path = exact_output / 'plan.json'
    pins[str(exact_plan_path.resolve())] = sha(exact_plan_path)
    pins[str(Path(__file__).resolve())] = sha(__file__)
    plan = {**exact, 'version': VERSION, 'schedule': schedule,
        'source_sha256': pins, 'maximum_new_judge_calls': len(schedule),
        'full_request_count': 1, 'new_model_calls': 0,
        'parameter_module': PARAMETER_MODULE,
        'partition': {'kind': PARTITION, 'source_directory': str(source_dir),
            'full_target_request_path': str(target_path), 'full_target_payload_sha256': key,
            'original_query_ids': ids, 'original_query_count': len(ids),
            'chunk_query_counts': [len(group) for group in groups]},
        'failed_or_truncated_response_consumed': False,
        'queries_removed_to_reduce_calls': False}
    save(output / 'plan.json', plan)
    audit = verify_plan(output / 'plan.json')
    assert plan == minimal.transport.legacy.verify(output / 'plan.json')
    print(json.dumps(audit, ensure_ascii=False), flush=True)
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'verify'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--chunk-size', type=int, default=12)
    parser.add_argument('--cache-index', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.source, args.output, chunk_size=args.chunk_size, cache_index=args.cache_index)
    else:
        print(json.dumps(verify_plan(args.plan), ensure_ascii=False))


if __name__ == '__main__':
    main()
