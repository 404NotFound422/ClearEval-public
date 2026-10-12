"""Use the user's fixed four-hour continuation with the existing request budget."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_budget as budget

START = '2026-10-10T10:23:18+00:00'
DEADLINE = '2026-10-10T14:23:18+00:00'
RECORD = budget.OUT / 'four_hour_extension_20261010' / 'authorization.json'


def install():
    record = json.loads(RECORD.read_text(encoding='utf8'))
    if record['deadline_utc'] != DEADLINE or record['original_authorization_sha256'] != budget.AUTH_SHA:
        raise ValueError('TIME_EXTENSION_RECORD_MISMATCH')
    budget.authorization()
    budget.time_remaining = lambda: (datetime.fromisoformat(DEADLINE) - datetime.now(timezone.utc)).total_seconds()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path)
    args, rest = parser.parse_known_args()
    install()
    target = args.script.resolve()
    if ROOT not in target.parents:
        raise ValueError('EXPECTED_REPOSITORY_SCRIPT')
    sys.argv = [str(target), *(rest[1:] if rest[:1] == ['--'] else rest)]
    runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()
