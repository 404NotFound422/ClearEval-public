"""Verify only the three new iDISCO-reference score batches; preserve old 585-row audit."""
import argparse
import json
import pathlib
import sys

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import cce_verify_score_batches as original

BASE = ROOT/'artifacts/cce_validation'
SETTINGS = [('supplement_v2_idisco_t070', .7), ('supplement_v2_idisco_t060', .6), ('supplement_v2_idisco_t080', .8)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--out', type=pathlib.Path, default=BASE/'score_batch_verification_idisco.json')
    args = p.parse_args()
    old = [BASE/'score_batch_verification.json', BASE/'score_batch_verification_commands.md']
    preserved = {str(path): original.file_hash(str(path)) for path in old}
    files = [BASE/(tag+suffix) for tag, _ in SETTINGS for suffix in
             ['_resolved_config.json','_references.json','_per_answer.json','_step_matches.json','_run.json']]
    missing = [str(path) for path in files if not path.is_file()]
    report = {'status': 'pending_new_batches' if missing else 'ready_not_verified',
              'batches_expected': 3, 'rows_expected': 195, 'batches_verified': 0, 'rows_verified': 0,
              'new_model_requests': 0, 'expert_labels_added': 0, 'missing_files': missing,
              'scope': 'Fresh input/parser/threshold/arithmetic verification of only new iDISCO-reference batches, using the existing verifier implementation. No new embeddings or model calls; no scientific or expert confirmation.',
              'preserved_old_audit_sha256': preserved,
              'wrapper': original.bind(__file__), 'original_verifier': original.bind(original.__file__),
              'actual_command': {'executable': sys.executable, 'argv': sys.argv}, 'batches': [], 'failures': []}
    if not args.preflight and not missing:
        for tag, threshold in SETTINGS:
            try:
                report['batches'].append(original.verify_batch(tag, threshold))
                print(tag+': 65 rows verified', flush=True)
            except Exception as exc:
                report['failures'].append({'tag': tag, 'type': type(exc).__name__, 'message': str(exc)})
        report['batches_verified'] = len(report['batches'])
        report['rows_verified'] = sum(b['row_n'] for b in report['batches'])
        report['numeric_field_comparisons'] = report['rows_verified'] * len(original.NUMERIC)
        report['status'] = 'pass' if len(report['batches']) == 3 and not report['failures'] else 'failed'
    for path, sha in preserved.items():
        original.require(original.file_hash(path) == sha, 'Old 585-row verification was changed')
    original.scorer.write(args.out, report)
    print(json.dumps({k: report[k] for k in ['status','batches_verified','rows_verified','new_model_requests']}))
    if report['status'] == 'failed':
        raise SystemExit(1)
    if not args.preflight and missing:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
