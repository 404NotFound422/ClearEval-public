#!/usr/bin/env python3
"""Read-only package hashes and expected omissions; never run a provider."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check():
    manifest = json.loads((ROOT / 'PACKAGE_MANIFEST.json').read_text())
    failures = []
    for rel, expected in manifest['files'].items():
        path = ROOT / rel
        if not path.is_file() or sha(path) != expected:
            failures.append(rel)
    vendor = json.loads((ROOT / 'VENDOR_MANIFEST.json').read_text())
    expected_missing = {item['path_relative_to_candidate_root']: item['sha256']
        for item in json.loads((ROOT / 'MISSING_LOCAL_FILES.json').read_text())['files']}
    missing, changed = [], []
    for rel, expected in vendor['files'].items():
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
        elif sha(path) != expected:
            changed.append(rel)
    unexpected_missing = sorted(set(missing) - set(expected_missing))
    restored = sorted(set(expected_missing) - set(missing))
    return {'package_status': 'PASS' if not failures and not changed and not unexpected_missing else 'FAIL',
        'package_files_checked': len(manifest['files']), 'package_hash_failures': failures,
        'vendor_files_present': len(vendor['files']) - len(missing),
        'expected_vendor_omissions': len(expected_missing), 'vendor_files_missing': len(missing),
        'vendor_hash_failures': changed, 'unexpected_missing_vendor_files': unexpected_missing,
        'locally_restored_vendor_files': restored,
        'vendor_snapshot_complete': not missing and not changed,
        'formal_pipeline_validated': False, 'model_calls': 0, 'encoder_calls': 0}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete-vendor', action='store_true',
        help='Return exit code 2 while original vendor files are absent; do not weaken the original manifest.')
    args = parser.parse_args()
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['package_status'] != 'PASS':
        return 1
    if args.require_complete_vendor and not result['vendor_snapshot_complete']:
        return 2
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
