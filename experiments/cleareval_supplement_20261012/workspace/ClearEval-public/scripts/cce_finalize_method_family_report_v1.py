"""Verify the published local report and retire the earlier active checkpoint."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
STAGE = BASE / 'method_family_followup_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def main():
    verification_path = BASE / 'report_verification_method_family_v1.json'
    verification = read(verification_path)
    require(verification['status'] == 'pass' and verification['publish'] and not verification['draft'], 'canonical_report_not_published')
    require(verification['actual_command'][1:] == ['scripts/cce_report.py'], 'actual_dispatcher_command_not_recorded')
    for path, expected in verification['input_sha256'].items():
        require(sha(path) == expected, 'report_input_changed:' + path)
    for name, expected in verification['output_sha256'].items():
        require(sha(BASE / name) == expected, 'report_output_changed:' + name)
    require(sha(ROOT / 'scripts/cce_report_method_family_v1.py') == verification['generator_sha256'], 'report_generator_changed')
    historical_dispatcher = BASE / 'historical_reports/before_method_family_at_136/cce_report_dispatcher_before.py'
    require(sha(historical_dispatcher) == '1e7e8856be0dcc433fb5ae385a3558bb3438400ddbcbbccd7200fa215386e6e7', 'dispatcher_backup_changed')
    require(sha(ROOT / 'scripts/cce_validation.py') == 'd272393ecbba84495e0430d01c0b52c4f69a6d9502147bdb071371dfed2bdc20', 'original_core_changed')
    require(sha(BASE / 'human_review/reviewer/review_items.csv') == '7ae708d91938b7e60737298261234e483caee4b50475ee20219cb188667ff5aa', 'expert_template_changed')
    ledger_path = BASE / 'judges/request_ledger.jsonl'
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    require(len(ledger) == 192 and all(row['event'] == 'request_started' for row in ledger), 'request_count_changed')
    require(sha(ledger_path) == sha(BASE / 'ledger_snapshot.jsonl'), 'live_ledger_differs_from_report_snapshot')
    activity = read(STAGE / 'activity.json')
    activity.update(status='completed_frozen_development_followup_scientific_dependencies_pending',
                    requests=192, remaining=108, in_progress=[],
                    completed=['method_family_steps_v1', 'representation_normalization_v1',
                               'output_contract_v1', 'output_identity_v2', 'controls_contract_v2',
                               'identity_stability_dev_v1', 'independent_reviews', 'canonical_report_integration'],
                    current_report='artifacts/cce_validation/CURRENT_RESULTS_INDEX.md',
                    overall_goal_complete=False, human_expert_returns=0,
                    resume_command='python scripts/cce_report.py')
    (STAGE / 'activity.json').write_text(json.dumps(activity, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    result = {
        'status': 'pass', 'actual_command': [sys.executable, *sys.argv],
        'report_verification_sha256': sha(verification_path),
        'verified_inputs': len(verification['input_sha256']),
        'verified_outputs': len(verification['output_sha256']),
        'report_local_links_checked': verification['actual_local_links_checked'],
        'dispatcher_sha256': sha(ROOT / 'scripts/cce_report.py'),
        'prior_dispatcher_sha256': sha(historical_dispatcher),
        'generator_sha256': verification['generator_sha256'],
        'requests': 192, 'new_model_requests': 0, 'expert_returns': 0,
        'original_scoring_core_and_human_template_unchanged': True,
        'computational_followup_complete': True, 'overall_scientific_goal_complete': False,
        'activity_sha256': sha(STAGE / 'activity.json'),
        'review_scope': 'Root inspected the generator, Chinese/English results, figures, source boundaries, A01/A04 traces, and independent numerical reviews. This is an AI software/evidence audit, not expert scientific confirmation.'
    }
    (STAGE / 'integration_review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
