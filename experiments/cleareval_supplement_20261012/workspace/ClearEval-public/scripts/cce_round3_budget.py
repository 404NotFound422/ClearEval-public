"""Twelve-hour, forty-request budget. Reads do not start evaluation requests."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j

ROUND = 'optimizer_round3_20261011'
OUT = ROOT / 'artifacts/cce_validation' / ROUND
AUTH = OUT / 'authorization.json'
AUTH_SHA = 'e901928d16710615532f0ed83bbf8455c15c8280382b213886e831f532b875c8'
LEDGER = ROOT / 'artifacts/cce_validation/judges/request_ledger.jsonl'
LIMITS = {'development': 8, 'E2': 24, 'confirmation': 8}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def authorization():
    require(j.filehash(AUTH) == AUTH_SHA, 'Authorization record changed; reconcile it before spending requests')
    a = j.read(AUTH)
    require(a['phase_new_request_limits'] == LIMITS and a['starting_package_requests'] == 388
            and a['new_package_limit'] == 428 and a['authorized_new_local_requests'] == 40,
            'Request limits differ from this round')
    return a


def counts():
    a = authorization()
    prefix = (OUT / 'ledger_at_authorization.jsonl').read_bytes()
    require(j.filehash(OUT / 'ledger_at_authorization.jsonl') == a['historical_ledger_sha256']
            and LEDGER.read_bytes().startswith(prefix), 'Historical ledger changed')
    requests = [r for r in j.ledger_rows(LEDGER) if r.get('event') == 'request_started']
    own = [r for r in requests if r.get('round_id') == ROUND]
    require(len(requests) == 388 + len(own), 'New requests outside this round need reconciliation')
    require(len({r['request_id'] for r in requests}) == len(requests), 'Duplicate request ledger ID')
    require([r['package_request_index'] for r in own] == list(range(389, 389 + len(own))),
            'Package request indices are not contiguous')
    return {'package': len(requests), 'round': len(own),
            'phase': {k: sum(r.get('phase') == k for r in own) for k in LIMITS},
            'requests': requests}


def time_remaining():
    return (datetime.fromisoformat(authorization()['deadline_utc']) - datetime.now(timezone.utc)).total_seconds()


def guard(phase, planned_new=1, transport_seconds=0):
    require(phase in LIMITS, 'Unallocated phase')
    require(type(planned_new) is int and planned_new >= 0, 'Invalid planned count')
    a = authorization()
    c = counts()
    require(time_remaining() > transport_seconds + 30, 'Not enough authorized time for this request')
    require(c['phase'][phase] + planned_new <= LIMITS[phase], 'Phase request limit reached')
    require(c['round'] + planned_new <= 40 and c['package'] + planned_new <= 428,
            'Round or package request limit reached')
    return {k: v for k, v in c.items() if k != 'requests'}


def reserve(phase, trial_id, model, transport_seconds):
    """Reserve exactly once immediately before the real local request."""
    require('llama' not in model.lower(), 'Llama is not an authorized evaluator')
    with j.ledger_lock(LEDGER):
        c = guard(phase, 1, transport_seconds)
        request_id = j.digest({'round_id': ROUND, 'trial_id': trial_id, 'attempt': 1})
        require(all(r.get('request_id') != request_id for r in j.ledger_rows(LEDGER)),
                'Trial already reserved; inspect its actual process/result before resuming')
        row = {'event': 'request_started', 'request_id': request_id, 'trial_id': trial_id,
               'attempt': 1, 'model': model, 'started_utc': j.now(),
               'package_request_index': c['package'] + 1, 'round_id': ROUND, 'phase': phase,
               'authorization_sha256': AUTH_SHA}
        with LEDGER.open('a', encoding='utf8') as stream:
            stream.write(j.canonical(row) + '\n')
    return row


def snapshot():
    a, c = authorization(), counts()
    result = {'round_id': ROUND, 'package_limit': 428, 'attempts_recorded': c['package'],
              'round_limit': 40, 'round_attempts': c['round'],
              'remaining_request_capacity': 428 - c['package'], 'phase_attempts': c['phase'],
              'phase_limits': LIMITS, 'remaining_phase_capacity': {k: LIMITS[k] - c['phase'][k] for k in LIMITS},
              'automatic_retries': False, 'deadline_utc': a['deadline_utc'],
              'ledger': {'path': str(LEDGER), 'sha256': j.filehash(LEDGER)},
              'authorization': {'path': str(AUTH), 'sha256': AUTH_SHA},
              'human_budget': {'experts': 1, 'development': 5, 'holdout': 15},
              'old_unused_six_not_added_to_new_forty': True}
    result['currently_phase_schedulable_requests'] = sum(result['remaining_phase_capacity'].values())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-snapshot', action='store_true')
    args = parser.parse_args()
    state = snapshot()
    if args.write_snapshot:
        j.save(ROOT / 'artifacts/cce_validation/budget.json', state)
        j.save(OUT / 'budget_snapshot.json', state)
    print(j.canonical({**state, 'new_model_calls': 0, 'seconds_remaining': time_remaining()}))
