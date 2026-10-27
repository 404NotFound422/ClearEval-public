"""Execute the seven predeclared local review batches exactly once."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
RESEARCH = Path('C:/ClearEval/ClearEval-runtime-4b42b5a/research/evaluator-research-cycle-20261018')
sys.path.insert(0, str(RESEARCH))
from execution_alignment_resolution_20261024_v1.runtime import minimal_instance_review_v2 as minimal

BRANCHES = ('CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', 'CUBIC_2019_IMMERSION_L_R_PLUS')
EXPECTED_COUNTS = ([12, 12, 10], [12, 12, 12, 3])


def preflight():
    jobs = []
    settings = None
    plan_hashes = {}
    for branch in BRANCHES:
        path = (ROOT / 'plan_v1' / branch / 'plan.json').resolve()
        plan = minimal.transport.legacy.verify(path)
        assert plan['parameter_module'] == 'execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1.normal_candidate'
        assert plan['full_request_count'] == 1 and plan['all_source_worlds_retained']
        assert plan['original_answer_not_regenerated'] and not plan['automatic_retry']
        assert not plan['reused_reviews'] and not plan['reused_review_sources']
        assert plan['maximum_new_encoder_calls'] == plan['maximum_new_canonical_calls'] == 0
        assert plan['maximum_new_judge_calls'] == len(plan['schedule'])
        assert plan['partition']['chunk_query_counts'] == EXPECTED_COUNTS[len(plan_hashes)]
        if settings is None:
            settings = plan['model_settings']
        assert plan['model_settings'] == settings
        plan_hashes[branch] = minimal.sha(path)
        for job in plan['schedule']:
            assert job['answer_id'] == 'EXPAND_148'
            assert job['maximum_new_judge_calls'] == 1
            assert job['maximum_new_encoder_calls'] == job['maximum_new_canonical_calls'] == 0
            jobs.append((branch, path, job))
    assert len(jobs) == 7 and settings is not None
    assert settings['seed'] == 20261018 and settings['temperature'] == 0 and settings['context'] == 131072
    import local_judge
    model = local_judge.verified_model()
    assert (local_judge.MODEL, local_judge.DIGEST, local_judge.CONTEXT) == (
        settings['model'], settings['model_digest'], settings['context'])
    assert model['digest'] == settings['model_digest']
    report = ROOT.parent / 'review_snapshot_v1/deepseek_v41_flash_review_v4.md'
    regression = ROOT.parent / 'review_snapshot_v1/full_regression54.log'
    assert '**结论：ACCEPT**' in report.read_text(encoding='utf-8')
    assert '54 passed' in regression.read_text(encoding='utf-8')
    return jobs, settings, plan_hashes, {
        'status': 'AUTHORIZED_FOR_REAL_LOCAL_REVIEW_NOT_SCORING',
        'independent_review': str(report), 'independent_review_sha256': minimal.sha(report),
        'full_regression': str(regression), 'full_regression_sha256': minimal.sha(regression),
        'full_regression_tests': 54, 'model_settings': settings, 'plan_sha256': plan_hashes,
        'driver_sha256': minimal.sha(__file__), 'maximum_new_judge_calls': len(jobs),
        'maximum_new_encoder_calls': 0, 'maximum_new_canonical_calls': 0,
        'automatic_retry': False, 'consume_truncated_responses': False,
        'accepted_for_scoring': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    jobs, settings, plan_hashes, authorization = preflight()
    if not args.execute:
        print(json.dumps({'status': 'PREFLIGHT_ONLY_NO_MODEL_CALL', 'batches': len(jobs),
            'model': settings['model'], 'plan_sha256': plan_hashes}, ensure_ascii=False))
        return
    output = ROOT / 'actual_v1'
    assert not output.exists()
    minimal.save(output / 'authorization.json', authorization)
    completed_records = []
    try:
        for branch, plan_path, job in jobs:
            iid = job['input_id']
            actual = output / branch / iid
            print(json.dumps({'event': 'BATCH_START', 'branch': branch, 'input_id': iid}, flush=True))
            minimal.transport.legacy.run(plan_path, iid, actual)
            completed = minimal.read(actual / 'completed.json')
            assert completed['input_id'] == iid
            terminal = (completed['status'] == 'RESPONSE_TERMINAL'
                and completed['actual_judge_calls'] == 1 and completed['response_saved']
                and completed['automatic_retry'] is False and completed['call_failure'] is None)
            record = {'branch': branch, 'input_id': iid,
                'run_id': completed['run_id'], 'transport_terminal': terminal,
                'status': completed['status'], 'actual_judge_calls': completed['actual_judge_calls'],
                'call_failure': completed['call_failure'], 'response_saved': completed['response_saved'],
                'model_score_generated': False, 'accepted_for_scoring': False,
                'full_origin_audit_required': True}
            minimal.save(output / 'batches' / (branch + '_' + iid + '.json'), record)
            completed_records.append(record)
            print(json.dumps({'event': 'BATCH_END', **record}, ensure_ascii=False, flush=True))
            if not terminal:
                raise RuntimeError('BATCH_NOT_ACCEPTED_FOR_CONSUMPTION:' + iid)
    except Exception as error:
        minimal.save(output / 'failure.json', {'type': type(error).__name__, 'reason': str(error),
            'accepted_for_scoring': False})
        if not (output / 'execution.json').exists():
            minimal.save(output / 'execution.json', {'status': 'INCOMPLETE_NOT_CONSUMED',
                'actual_judge_calls': sum(row['actual_judge_calls'] for row in completed_records),
                'batches': completed_records, 'new_score_generated': False,
                'accepted_for_scoring': False, 'automatic_retry': False})
        raise
    minimal.save(output / 'execution.json', {
        'status': 'ALL_BATCHES_TERMINAL_NOT_CONSUMED', 'actual_judge_calls': len(completed_records),
        'batches': completed_records, 'all_response_terminal': True,
        'new_score_generated': False, 'accepted_for_scoring': False,
        'next_step': 'AUDIT_FULL_ORIGINS_AND_CONSUME', 'automatic_retry': False,
        'new_encoder_calls': 0, 'new_canonical_calls': 0})
    print(json.dumps(minimal.read(output / 'execution.json'), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
