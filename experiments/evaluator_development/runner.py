"""Resumable offline engineering verification with immutable inputs and attempts."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from experiments.construct_validity.contract import digest, file_hash, read, save
from . import probes

VERSION = 'evaluator-development-runner-v2'
ROOT = Path(__file__).resolve().parents[2]
CODE_FILES = (
    'evaluator_integrity.py',
    'experiments/construct_validity/contract.py',
    'experiments/construct_validity/fidelity.py',
    'experiments/construct_validity/evidence.py',
    'experiments/construct_validity/objectives.py',
    'experiments/construct_validity/execution_identity.py',
    'experiments/evaluator_development/__init__.py',
    'experiments/evaluator_development/__main__.py',
    'experiments/evaluator_development/probes.py',
    'experiments/evaluator_development/runner.py',
)


def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _code_hashes():
    return {name: file_hash(ROOT / name) for name in CODE_FILES}


def _atomic_unique(path, value):
    # Frozen snapshots and result records are created once and never replaced.
    save(path, value, immutable=True)


def _append(path, value):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _alive(pid):
    if type(pid) is not int or pid < 1:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied stays conservative.
        try:
            exit_code = wintypes.DWORD()
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _lock(out, manifest_hash):
    path = out / 'active_lock.json'
    if path.exists():
        previous = read(path)
        if _alive(previous.get('pid')):
            raise ValueError('A recorded process is still live; resume the same handle instead of starting a duplicate.')
        if previous.get('manifest_sha256') != manifest_hash:
            raise ValueError('Stale lock differs from frozen manifest.')
        path.unlink()
    token = uuid.uuid4().hex
    _atomic_unique(path, {'pid': os.getpid(), 'token': token, 'started_at': timestamp(),
                          'manifest_sha256': manifest_hash})
    return path, token


def _diff(expected, actual, prefix=''):
    differences = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [{'field': prefix, 'expected': expected, 'observed': actual}]
        for key, value in expected.items():
            if key == 'annotation':
                continue  # Hidden reference, never an observed adapter output.
            child = prefix + ('.' if prefix else '') + key
            if key not in actual:
                differences.append({'field': child, 'expected': value, 'observed': 'ABSENT'})
            else:
                differences.extend(_diff(value, actual[key], child))
    elif actual != expected:
        differences.append({'field': prefix, 'expected': expected, 'observed': actual})
    return differences


def _check_record(record, manifest, case):
    checksum = record.get('record_sha256')
    body = {k: v for k, v in record.items() if k != 'record_sha256'}
    if not checksum or digest(body) != checksum:
        raise ValueError('Saved result checksum differs: ' + case['id'])
    if (record.get('manifest_sha256') != digest(manifest)
            or record.get('public_input_sha256') != digest({'kind': case['kind'], 'input': case['input']})
            or record.get('hidden_expected_sha256') != digest(case['expected'])):
        raise ValueError('Saved case result does not match the frozen input: ' + case['id'])

def _summary(out, manifest, cases):
    results = []
    for case in cases:
        path = out / 'case_results' / (case['id'] + '.json')
        if not path.exists():
            continue
        record = read(path)
        _check_record(record, manifest, case)
        results.append(record)
    passed = sum(r['comparison']['passed'] for r in results)
    return {'runner_version': VERSION, 'label': manifest['label'], 'manifest_sha256': digest(manifest),
            'scope': 'OFFLINE_ENGINEERING_ONLY', 'model_calls': 0,
            'scientific_validation': 'PENDING_USER_EXPERT',
            'planned_cases': len(cases), 'completed_cases': len(results), 'passed_cases': passed,
            'failed_cases': len(results) - passed, 'pending_cases': len(cases) - len(results),
            'all_cases_completed': len(results) == len(cases),
            'all_mechanical_contracts_passed': len(results) == len(cases) and passed == len(cases),
            'failures': [{'id': r['case_id'], 'kind': r['kind'], 'differences': r['comparison']['differences']}
                         for r in results if not r['comparison']['passed']],
            'kind_counts': dict(Counter(r['kind'] for r in results)),
            'interpretation': 'Mechanical contracts only; fake/cache runs do not establish judge stability or scientific accuracy.'}


def verify(args):
    fixtures = Path(args.fixtures).resolve()
    suite = read(fixtures)
    if suite.get('scope') != 'offline-engineering-only':
        raise ValueError('This runner accepts offline engineering fixtures only.')
    cases = suite['cases']
    ids = [c['id'] for c in cases]
    if (len(ids) != len(set(ids)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+', i) for i in ids)):
        raise ValueError('Unique safe case identifiers required.')
    if args.max_cases is not None and args.max_cases < 1:
        raise ValueError('--max-cases must be positive.')
    if args.max_seconds is not None and not 0 < args.max_seconds <= 172800:
        raise ValueError('--max-seconds must be positive and at most 172800.')
    out = Path(args.out).resolve()
    current = {'runner_version': VERSION, 'adapter_version': probes.VERSION, 'label': args.label,
               'fixture_schema': suite['schema_version'], 'fixtures_path': str(fixtures),
               'fixtures_sha256': file_hash(fixtures), 'files': _code_hashes(),
               'scope': 'OFFLINE_ENGINEERING_ONLY', 'model_calls': 0,
               'scientific_validation': 'PENDING_USER_EXPERT'}
    manifest_path = out / 'manifest.json'
    if args.resume:
        if not manifest_path.exists():
            raise ValueError('--resume requires a frozen run manifest.')
        manifest = read(manifest_path)
        if manifest != current:
            raise ValueError('Frozen source/input/config differs; choose a new round directory.')
    else:
        if out.exists() and any(out.iterdir()):
            raise ValueError('New round requires an empty output directory; use --resume for identical frozen inputs.')
        out.mkdir(parents=True, exist_ok=True)
        manifest = current
        _atomic_unique(manifest_path, manifest)
        _atomic_unique(out / 'fixtures.snapshot.json', suite)
    manifest_hash = digest(manifest)
    lock, token = _lock(out, manifest_hash)
    invocation_id = uuid.uuid4().hex
    ledger_path = out / 'events.jsonl'
    processed = 0
    started = time.monotonic()
    (out / 'case_results').mkdir(exist_ok=True)
    try:
        _append(ledger_path, {'event': 'INVOCATION_STARTED', 'at': timestamp(), 'pid': os.getpid(),
                             'invocation_id': invocation_id, 'manifest_sha256': manifest_hash})
        for case in cases:
            path = out / 'case_results' / (case['id'] + '.json')
            if path.exists():
                saved = read(path)
                _check_record(saved, manifest, case)
                continue
            if ((args.max_cases is not None and processed >= args.max_cases) or
                    (args.max_seconds is not None and time.monotonic() - started >= args.max_seconds)):
                break
            if file_hash(fixtures) != manifest['fixtures_sha256'] or _code_hashes() != manifest['files']:
                raise ValueError('Frozen inputs changed during execution; stop and create a new round.')
            attempt_id = uuid.uuid4().hex
            public_hash = digest({'kind': case['kind'], 'input': case['input']})
            _append(ledger_path, {'event': 'CASE_STARTED', 'at': timestamp(), 'case_id': case['id'],
                                 'attempt_id': attempt_id, 'invocation_id': invocation_id,
                                 'public_input_sha256': public_hash, 'manifest_sha256': manifest_hash})
            # Only kind/input/context go into adapters. Expected is used after
            # production computation, exclusively for a mechanical comparison.
            try:
                observed = probes.compute(case['kind'], case['input'], {'files': manifest['files']})
                technical = 'COMPLETED'
            except Exception as exc:
                observed = {'adapter_error': type(exc).__name__, 'message': str(exc)}
                technical = 'ADAPTER_ERROR'
            differences = _diff(case['expected'], observed)
            record = {'case_id': case['id'], 'kind': case['kind'], 'attempt_id': attempt_id,
                      'invocation_id': invocation_id, 'completed_at': timestamp(),
                      'manifest_sha256': manifest_hash, 'public_input_sha256': public_hash,
                      'hidden_expected_sha256': digest(case['expected']), 'technical_status': technical,
                      'observed': observed, 'comparison': {'passed': not differences, 'differences': differences},
                      'scientific_limit': case['scientific_limit'], 'model_calls': 0}
            record['record_sha256'] = digest(record)
            _atomic_unique(path, record)
            _append(ledger_path, {'event': 'CASE_COMPLETED', 'at': timestamp(), 'case_id': case['id'],
                                 'attempt_id': attempt_id, 'invocation_id': invocation_id,
                                 'result_sha256': file_hash(path), 'technical_status': technical,
                                 'mechanical_passed': not differences})
            processed += 1
        summary = _summary(out, manifest, cases)
        _atomic_unique(out / ('summary.' + invocation_id + '.json'), summary)
        _append(ledger_path, {'event': 'INVOCATION_ENDED', 'at': timestamp(), 'invocation_id': invocation_id,
                             'new_cases': processed, 'completed_cases': summary['completed_cases'],
                             'failed_cases': summary['failed_cases'], 'model_calls': 0})
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 0 if summary['failed_cases'] == 0 else 1
    finally:
        if lock.exists() and read(lock).get('token') == token:
            lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline evaluator development; no model calls or benchmark scoring.')
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('verify', help='Verify frozen synthetic mechanical contracts.')
    command.add_argument('--fixtures', default='experiments/evaluator_development/fixtures.json')
    command.add_argument('--out', required=True)
    command.add_argument('--label', required=True)
    command.add_argument('--resume', action='store_true')
    command.add_argument('--max-cases', type=int)
    command.add_argument('--max-seconds', type=float)
    args = parser.parse_args(argv)
    try:
        return verify(args)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'status': 'REFUSED', 'reason': str(exc), 'model_calls': 0}), file=sys.stderr)
        return 2
