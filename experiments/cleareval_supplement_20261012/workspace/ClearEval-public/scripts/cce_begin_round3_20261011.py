"""Record the resumed twelve-hour experiment; no model request is made."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'optimizer_round3_20261011'
OLD = BASE / 'optimizer_round2_20261010'
START = '2026-10-11T14:43:01+00:00'
DEADLINE = '2026-10-12T02:43:01+00:00'
LEDGER = BASE / 'judges/request_ledger.jsonl'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')


def main():
    if (OUT / 'authorization.json').exists():
        print(json.dumps({'status': 'existing_authorization_reused', 'deadline_not_reset': True,
                          'authorization_sha256': sha(OUT / 'authorization.json'), 'new_model_calls': 0}))
        return
    ledger_bytes = LEDGER.read_bytes()
    requests = [json.loads(s) for s in ledger_bytes.decode('utf8').splitlines() if s.strip()]
    requests = [r for r in requests if r.get('event') == 'request_started']
    if len(requests) != 388 or len({r['request_id'] for r in requests}) != 388:
        raise ValueError('Reconcile actual request ledger before authorizing a new round')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(DEADLINE):
        raise ValueError('Twelve-hour window has already ended')
    manifest_path = OLD / 'four_hour_extension_20261010/delivery/canonical_delivery_manifest_v3.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    preserved = []
    for entry in manifest['current_files']:
        source = Path(entry['path']).resolve()
        if not source.is_relative_to(WORKSPACE) or sha(source) != entry['sha256']:
            raise ValueError('Prior delivery changed; inspect before preserving: ' + str(source))
        dest = OUT / 'prior_delivery_snapshot' / source.relative_to(WORKSPACE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        preserved.append({'source': str(source), 'snapshot': str(dest), 'sha256': sha(dest)})
    save(OUT / 'prior_delivery_snapshot/manifest.json', {'source_manifest': str(manifest_path),
         'source_manifest_sha256': sha(manifest_path), 'files': preserved,
         'purpose': 'Preserve v5 navigation and budget before the new round; scientific results remain in place'})
    (OUT / 'ledger_at_authorization.jsonl').write_bytes(ledger_bytes)
    proposal = OLD / 'four_hour_extension_20261010/delivery/NEXT_PHASE_SCOPE_PENDING.md'
    auth = {
        'status': 'resumed_user_authorization_recorded_before_new_calls',
        'user_reply': '继续，你有１２个小时的时间完成',
        'interpretation': 'Continue the immediately preceding proposed 40-call round; user replaces its four-hour duration with twelve hours.',
        'prior_proposal': {'path': str(proposal), 'sha256': sha(proposal)},
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'start_utc': START, 'deadline_utc': DEADLINE, 'time_limit_hours': 12,
        'start_note': 'First clock observation after the resumption; all organization and delivery time is included.',
        'starting_package_requests': 388, 'previous_package_limit': 394,
        'authorized_new_local_requests': 40, 'new_package_limit': 428,
        'old_remaining_capacity_included_not_added': 6,
        'phase_new_request_limits': {'development': 8, 'E2': 24, 'confirmation': 8},
        'max_attempts_per_cell': 1, 'automatic_retries': False,
        'stop_at_first_time_or_call_limit': True, 'phase_transfer_automatic': False,
        'preferred_evaluator': 'qwen3.8:27b-q8_0-local', 'llama_as_evaluator_allowed': False,
        'local_only': True, 'original_formulas_and_raw_SR_SP_preserved': True,
        'expert_budget': {'experts': 1, 'development': 5, 'holdout': 15},
        'missing_expert_or_wetlab_not_blocking_independent_work': True,
        'historical_ledger_sha256': sha(LEDGER),
        'actual_command': [sys.executable, *sys.argv], 'new_model_calls_by_this_command': 0,
    }
    save(OUT / 'authorization.json', auth)
    save(OUT / 'plan.json', {
        'status': 'offline_development_in_progress', 'authorization_sha256': sha(OUT / 'authorization.json'),
        'stages': ['source_role_repair_and_uniform_replay', 'representation_and_rubric_evidence_repair',
                   'frozen_fulltext_paired_and_repeated_validation', 'new_answer_confirmation',
                   'joint_analysis_figures_and_bilingual_delivery'],
        'planned_request_limits': auth['phase_new_request_limits'], 'new_calls_at_start': 0,
        'overall_goal_complete': False, 'scientific_improvement_not_presumed': True,
        'prior_latest_development': str(OLD / 'posthoc_uniform_scoring_v6/README_zh.md'),
    })
    save(BASE / 'budget.json', {
        'round_id': 'optimizer_round3_20261011', 'package_limit': 428,
        'attempts_recorded': 388, 'round_limit': 40, 'round_attempts': 0,
        'remaining_request_capacity': 40, 'phase_attempts': {k: 0 for k in auth['phase_new_request_limits']},
        'phase_limits': auth['phase_new_request_limits'], 'remaining_phase_capacity': auth['phase_new_request_limits'],
        'currently_phase_schedulable_requests': 40, 'automatic_retries': False,
        'deadline_utc': DEADLINE, 'ledger': {'path': str(LEDGER), 'sha256': sha(LEDGER)},
        'authorization': {'path': str(OUT / 'authorization.json'), 'sha256': sha(OUT / 'authorization.json')},
        'human_budget': {'experts': 1, 'development': 5, 'holdout': 15, 'received_last_verified': 0},
        'previous_round_calls': 94, 'old_unused_six_not_added_to_new_forty': True,
    })
    print(json.dumps({'status': 'round3_started', 'deadline_utc': DEADLINE,
          'package_requests': 388, 'round_requests': 0, 'package_limit': 428,
          'authorization_sha256': sha(OUT / 'authorization.json'), 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
