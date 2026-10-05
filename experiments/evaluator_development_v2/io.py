"""Immutable JSON records and hash-chained local ledgers."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        handle.write(canonical(value) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def ledger(path):
    path = Path(path)
    if not path.exists():
        return []
    rows, previous = [], None
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        body = {key: value for key, value in row.items() if key != 'event_sha256'}
        if body.get('previous_sha256') != previous or body.get('index') != len(rows):
            raise ValueError('Ledger chain/order mismatch')
        if row.get('event_sha256') != digest(body):
            raise ValueError('Ledger checksum mismatch')
        rows.append(row)
        previous = row['event_sha256']
    return rows


def append(path, event):
    rows = ledger(path)
    body = {**event, 'index': len(rows), 'previous_sha256': rows[-1]['event_sha256'] if rows else None}
    row = {**body, 'event_sha256': digest(body)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(canonical(row) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    return row


class Lock:
    """Exclusive local lock; no automatic removal of a stale or live process."""
    def __init__(self, path):
        self.path = Path(path)
    def __enter__(self):
        save(self.path, {'pid': os.getpid(), 'started': now()})
        return self
    def __exit__(self, *args):
        self.path.unlink()
