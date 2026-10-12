"""Bind real expert returns to one frozen suggestion version per selected answer.

The existing extraction/EGES bridge is unchanged. This wrapper has no model path.
Original forms are immutable templates; use separately returned copies.
"""
from __future__ import annotations
import argparse
import contextlib
import csv
import hashlib
import io
import json
import socket
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_rescore_extractions as bridge

BASE = ROOT / 'artifacts/cce_validation'
HUMAN = BASE / 'human_review'
OUT = HUMAN / 'versioned_review_v1'
FORM = HUMAN / 'reviewer/review_items.csv'
CORRECTIONS = HUMAN / 'expert_extraction_corrections.json'
ITEMS = set(bridge.ITEM_ROOTS)
GROUPS = {
    'development_v4': {'version': 'original_development_v4_dev_v2',
        'auto': HUMAN / 'rescoring/v4_dev_v2/auto_inputs.json',
        'packets': HUMAN / 'rescoring/v4_dev_v2/reviewer', 'ids': [f'A{i:02}' for i in range(1, 6)]},
    'holdout_prompt_v2': {'version': 'development_prompt_v2_technical_followup',
        'auto': BASE / 'judges/holdout_remediation_v2/sealed/guarded_auto/auto_inputs.json',
        'packets': BASE / 'judges/holdout_remediation_v2/sealed/reviewer', 'ids': [f'A{i:02}' for i in range(6, 21)]}}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def csvwrite(path, data, fields):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(data)


def no_network(*args, **kwargs):
    raise RuntimeError('Version guard is offline; model/network calls are forbidden')


def verify_binding(record):
    require(sha(record['path']) == record['sha256'], 'Frozen file changed: ' + record['path'])


def prepare(args):
    require(not (OUT / 'manifest.json').exists(), 'Frozen manifest exists; use preflight, not prepare')
    template = rows(FORM)
    require(len(template) == 160 and len({(r['answer_id'], r['item']) for r in template}) == 160, 'Original 160-item identity changed')
    require(not any(r['expert_decision'].strip() or r['reviewer_id'].strip() for r in template), 'Original template already has expert content')
    records, groups = [], {}
    for gid, spec in GROUPS.items():
        auto = read(spec['auto']); config = auto['scoring_config']
        auto_rows = {r['answer_id']: r for r in auto['records']}
        require(set(auto_rows) <= set(spec['ids']), 'Unexpected automatic answer identity')
        groups[gid] = {'version': spec['version'], 'answer_ids': spec['ids'],
            'auto_inputs': bind(spec['auto']), 'config_hash': auto['config_hash'],
            'judge_contract_sha256': config['judge_contract_sha256'], 'packets_dir': str(spec['packets']),
            'identity_verification': bind(spec['auto'].parent / 'identity_verification.json')}
        for aid in spec['ids']:
            path = spec['packets'] / f'{aid}.json'; packet = read(path)
            require(packet['answer_id'] == aid, 'Packet identity mismatch')
            require(bridge.rawsha(packet['answer_text']) == packet['answer_sha256'], 'Packet answer hash mismatch')
            require(bridge.rawsha(packet['task_text']) == packet['question_sha256'], 'Packet question hash mismatch')
            record = auto_rows.get(aid)
            if record:
                require(record['answer_sha256'] == packet['answer_sha256'] and record['question_sha256'] == packet['question_sha256'], 'Packet/auto input identity mismatch')
                require(record['extraction_sha256'] == packet['extraction_sha256'] == bridge.human.digest(packet['extraction']), 'Suggestion differs from selected actual extraction')
            else:
                require(aid == 'A15' and packet['extraction'] is None, 'Unexpected missing automatic record')
            records.append({'answer_id': aid, 'split': 'audit_dev' if gid == 'development_v4' else 'audit_holdout',
                'group': gid, 'version': spec['version'], 'packet': bind(path),
                'answer_sha256': packet['answer_sha256'], 'question_sha256': packet['question_sha256'],
                'auto_available': record is not None,
                'auto_config_hash': record['config_hash'] if record else None,
                'trial_id': record['trial_id'] if record else None,
                'trial': bind(record['trial_path']) if record else None,
                'extraction_sha256': record['extraction_sha256'] if record else None,
                'status': 'actual_suggestion_pending_expert' if record else 'failed_auto_pending_no_faithful_pair'})
    require(len(records) == 20 and sum(r['auto_available'] for r in records) == 19, 'Expected 5+14 actual extractions and A15 pending')
    manifest = {'schema': 'versioned-review-package-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'expert_budget': 1, 'development_answers': 5, 'holdout_answers': 15, 'review_items': 160,
        'selection': bind(HUMAN / 'selection.json'), 'original_form_template': bind(FORM),
        'original_correction_template': bind(CORRECTIONS),
        'wrapper': bind(__file__), 'bridge': bind(ROOT / 'scripts/cce_rescore_extractions.py'),
        'original_return_code': bind(ROOT / 'scripts/cce_human_wetlab.py'),
        'groups': groups, 'records': records,
        'policy': 'One fixed version per answer: original five development suggestions and all fifteen prompt-v2 holdout suggestions, including failed A15. No best-of-version selection; old holdout/schema suggestions are historical.',
        'acknowledgement_policy': 'Each real receipt binds this manifest byte hash plus explicit reviewed answer IDs, one reviewer and date. The manifest binds packet/auto/config/trial/extraction hashes. Recheck actual bytes before any forwarding.',
        'expert_returns_at_preparation': 0, 'new_model_requests': 0, 'formal_eligible': False}
    save(OUT / 'manifest.json', manifest)
    manifest_hash = sha(OUT / 'manifest.json')
    save(OUT / 'receipt_template.json', {'schema': 'expert-version-receipt-v1',
        'package_manifest_sha256': manifest_hash, 'reviewer_id': '', 'review_date': '',
        'reviewed_answer_ids': [], 'version_confirmed': False})
    save(OUT / 'received_receipts.json', {'records': []})
    print(json.dumps({'status': 'version_package_frozen', 'manifest_sha256': manifest_hash,
        'answers': 20, 'actual_auto': 19, 'missing_auto_ids': ['A15'], 'expert_acknowledgements': 0, 'new_requests': 0}))


def verify_package():
    manifest = read(OUT / 'manifest.json')
    expected_sources = {'selection': HUMAN / 'selection.json', 'original_form_template': FORM,
        'original_correction_template': CORRECTIONS, 'wrapper': Path(__file__),
        'bridge': ROOT / 'scripts/cce_rescore_extractions.py',
        'original_return_code': ROOT / 'scripts/cce_human_wetlab.py'}
    for key, path in expected_sources.items():
        require(manifest[key] == bind(path), 'Fixed package source/path changed: ' + key)
    require(manifest['expert_budget'] == 1 and manifest['development_answers'] == 5 and
        manifest['holdout_answers'] == 15 and manifest['review_items'] == 160 and
        manifest['formal_eligible'] is False, 'Fixed review scope changed')
    require(set(manifest['groups']) == set(GROUPS), 'Fixed version groups changed')
    expected_records = []
    for gid, spec in GROUPS.items():
        group = manifest['groups'][gid]
        require(group['version'] == spec['version'] and group['answer_ids'] == spec['ids'] and
            group['packets_dir'] == str(spec['packets']) and group['auto_inputs'] == bind(spec['auto']),
            'Fixed group version, answer IDs or automatic source changed')
        require(group['identity_verification'] == bind(spec['auto'].parent / 'identity_verification.json'), 'Identity verification source changed')
        # Existing guard rebinds exact real trial/configuration. It does not generate or score.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            auto, _, _, _ = bridge.load_auto(types.SimpleNamespace(auto_inputs=Path(group['auto_inputs']['path'])))
        require(auto['config_hash'] == group['config_hash'] and
            auto['scoring_config']['judge_contract_sha256'] == group['judge_contract_sha256'], 'Frozen automatic configuration differs')
        actual = {r['answer_id']: r for r in auto['records']}
        require(set(actual) == set(spec['ids']) - ({'A15'} if gid == 'holdout_prompt_v2' else set()), 'Actual automatic identity set changed')
        for aid in spec['ids']:
            path = spec['packets'] / f'{aid}.json'; packet = read(path); record = actual.get(aid)
            require(packet['answer_id'] == aid and bridge.rawsha(packet['answer_text']) == packet['answer_sha256'] and
                bridge.rawsha(packet['task_text']) == packet['question_sha256'], 'Actual packet identity changed')
            if record:
                require(record['answer_sha256'] == packet['answer_sha256'] and record['question_sha256'] == packet['question_sha256'] and
                    record['extraction_sha256'] == packet['extraction_sha256'] == bridge.human.digest(packet['extraction']), 'Actual packet/automatic version differs')
            else:
                require(aid == 'A15' and packet['extraction'] is None, 'Only A15 may lack an automatic extraction')
            expected_records.append({'answer_id': aid, 'split': 'audit_dev' if gid == 'development_v4' else 'audit_holdout',
                'group': gid, 'version': spec['version'], 'packet': bind(path),
                'answer_sha256': packet['answer_sha256'], 'question_sha256': packet['question_sha256'],
                'auto_available': record is not None, 'auto_config_hash': record['config_hash'] if record else None,
                'trial_id': record['trial_id'] if record else None, 'trial': bind(record['trial_path']) if record else None,
                'extraction_sha256': record['extraction_sha256'] if record else None,
                'status': 'actual_suggestion_pending_expert' if record else 'failed_auto_pending_no_faithful_pair'})
    require(manifest['records'] == expected_records, 'Manifest record metadata differs from actual frozen packet/auto/config/trial/extraction')
    return manifest


def validate_receipts(receipts, manifest_hash, known_ids):
    """Pure version gate; synthetic audits may call it without touching real cases."""
    accepted = set(); reviewers = set()
    require(isinstance(receipts, list), 'Receipts must be a list')
    for receipt in receipts:
        require(receipt.get('schema') == 'expert-version-receipt-v1', 'Unknown receipt schema')
        require(receipt.get('package_manifest_sha256') == manifest_hash, 'Wrong package manifest version')
        reviewer = receipt.get('reviewer_id', '').strip(); date = receipt.get('review_date', '').strip()
        ids = receipt.get('reviewed_answer_ids')
        require(bool(reviewer) and bool(date) and receipt.get('version_confirmed') is True, 'Blank/unconfirmed receipt is not expert acknowledgement')
        require(isinstance(ids, list) and bool(ids) and len(ids) == len(set(ids)), 'Receipt must list unique reviewed IDs')
        require(set(ids) <= set(known_ids), 'Receipt contains an unselected answer')
        reviewers.add(reviewer)
        for aid in ids:
            key = (aid, reviewer, date)
            require(key not in accepted, 'Duplicate receipt acknowledgement')
            accepted.add(key)
    require(len(reviewers) <= 1, 'Original budget permits one expert only')
    return accepted


def validate_review_version_gate(labels, accepted, template_keys):
    require(len(labels) == len(template_keys), 'Returned copy must retain the original 160 rows')
    keys = [(r['answer_id'], r['item'], r['split']) for r in labels]
    require(len(keys) == len(set(keys)) and set(keys) == set(template_keys), 'Returned answer/item/split identities differ')
    reviewers = {key[1] for key in accepted}
    reviewed_extraction = []
    for row in labels:
        if row.get('reviewer_id', '').strip():
            reviewers.add(row['reviewer_id'].strip())
        touched = row.get('review_status', 'not_reviewed') != 'not_reviewed' or bool(row.get('expert_decision', '').strip())
        if row['item'] in ITEMS and touched:
            key = (row['answer_id'], row.get('reviewer_id', '').strip(), row.get('review_date', '').strip())
            require(key in accepted, 'Reviewed extraction item lacks matching version receipt: ' + row['answer_id'])
            reviewed_extraction.append(row)
    require(len(reviewers) <= 1, 'Returned forms/receipts contain multiple expert identities')
    return reviewed_extraction


def assess(args):
    manifest = verify_package()
    labels = rows(args.review)
    receipt_object = read(args.receipts)
    require(isinstance(receipt_object, dict) and 'records' in receipt_object, 'Use a receipt records file; the blank template is not a returned receipt')
    accepted = validate_receipts(receipt_object['records'], sha(OUT / 'manifest.json'), {r['answer_id'] for r in manifest['records']})
    template_keys = {(r['answer_id'], r['item'], r['split']) for r in rows(FORM)}
    reviewed = validate_review_version_gate(labels, accepted, template_keys)
    corrections = bridge.human.get_records(args.corrections)
    row_lookup = {(r['answer_id'], r['item']): r for r in labels}
    for correction in corrections:
        require(correction.get('item') in ITEMS, 'Only the original extraction-review items may authorize corrections')
        row = row_lookup.get((correction.get('answer_id'), correction.get('item')), {})
        require(row.get('review_status') == 'reviewed' and row.get('expert_decision') == '不成立', 'Correction lacks a real reviewed error')
        require((correction['answer_id'], correction.get('reviewer_id'), correction.get('review_date')) in accepted, 'Correction has no matching version receipt')
        require(correction.get('reviewer_id') == row.get('reviewer_id') and correction.get('review_date') == row.get('review_date'), 'Correction and review identity/date differ')
    return manifest, labels, reviewed, corrections, accepted


def preflight(args):
    manifest, labels, reviewed, corrections, accepted = assess(args)
    result = {'status': 'ready_pending_real_expert_returns' if not reviewed else 'real_return_version_gate_pass',
        'manifest_sha256': sha(OUT / 'manifest.json'), 'fixed_answers': 20, 'dev': 5, 'holdout': 15,
        'actual_auto_records': sum(r['auto_available'] for r in manifest['records']),
        'missing_auto_ids': [r['answer_id'] for r in manifest['records'] if not r['auto_available']],
        'original_form_rows': len(labels), 'reviewed_extraction_rows': len(reviewed),
        'version_acknowledgements': len(accepted), 'expert_reviewer_count': len({a[1] for a in accepted}),
        'correction_records': len(corrections), 'faithful_outputs_created': 0, 'new_model_requests': 0,
        'review_input': bind(args.review), 'receipts_input': bind(args.receipts),
        'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv])}
    path = OUT / 'preflight.json'
    if path.exists():
        require(read(path)['manifest_sha256'] == result['manifest_sha256'], 'Existing preflight package differs')
    save(path, result)
    print(json.dumps({k: result[k] for k in ['status', 'fixed_answers', 'actual_auto_records', 'missing_auto_ids', 'reviewed_extraction_rows', 'version_acknowledgements', 'faithful_outputs_created', 'new_model_requests']}))


def rescore(args):
    manifest, labels, reviewed, corrections, accepted = assess(args)
    if not reviewed:
        require(not corrections, 'Corrections without a real expert review')
        print(json.dumps({'status': 'pending_no_real_review', 'faithful_outputs_created': 0, 'new_model_requests': 0}))
        return
    require(Path(args.review).resolve() != FORM.resolve(), 'Return a separate review copy; do not write the frozen original form')
    require(Path(args.corrections).resolve() != CORRECTIONS.resolve() or not corrections, 'Return corrections in a separate file')
    bindings = {r['answer_id']: r for r in manifest['records']}
    deferred = sorted({r['answer_id'] for r in reviewed if not bindings[r['answer_id']]['auto_available']})
    # Run only groups with actual scorable returns. Partial reviews remain pending.
    active = {}
    for gid, group in manifest['groups'].items():
        auto_ids = {aid for aid in group['answer_ids'] if bindings[aid]['auto_available']}
        chosen_corrections = [c for c in corrections if c['answer_id'] in auto_ids]
        affirmative_ids = []
        for aid in auto_ids:
            subset = [r for r in labels if r['answer_id'] == aid and r['item'] in ITEMS]
            if len(subset) == len(ITEMS) and all(r.get('review_status') == 'reviewed' and r.get('expert_decision') == '成立' for r in subset):
                affirmative_ids.append(aid)
        if chosen_corrections or affirmative_ids:
            active[gid] = (group, auto_ids, chosen_corrections)
    if not active:
        print(json.dumps({'status': 'pending_incomplete_or_unavailable_auto', 'missing_auto_ids': deferred,
            'faithful_outputs_created': 0, 'new_model_requests': 0}))
        return
    input_bindings = {str(Path(p).resolve()): sha(p) for p in [args.review, args.receipts, args.corrections, OUT / 'manifest.json']}
    run_id = bridge.judges.digest(input_bindings)[:24]
    run_out = OUT / 'returned_runs' / run_id
    require(not run_out.exists(), 'This exact returned-input run already exists; inspect preserved results, do not overwrite')
    run_out.mkdir(parents=True)
    results = []
    for gid, (group, auto_ids, chosen_corrections) in active.items():
        dest = run_out / gid; dest.mkdir()
        group_labels = [r for r in labels if r['answer_id'] in auto_ids]
        csvwrite(dest / 'review_return.csv', group_labels, list(labels[0]))
        save(dest / 'corrections_return.json', {'records': chosen_corrections})
        forwarded = types.SimpleNamespace(auto_inputs=Path(group['auto_inputs']['path']),
            review=dest / 'review_return.csv', corrections=dest / 'corrections_return.json',
            packets=Path(group['packets_dir']), out=dest, faithful_inputs=None)
        with (dest / 'bridge_console.log').open('w', encoding='utf-8') as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                bridge.rescore(forwarded)
        results.append({'group': gid, 'version': group['version'], 'auto_inputs': group['auto_inputs'],
            'output_dir': str(dest), 'status': 'original_bridge_completed',
            'real_error_correction_records': len(chosen_corrections)})
    save(run_out / 'run.json', {'status': 'completed_real_version_bound_returns', 'input_sha256': input_bindings,
        'groups': results, 'missing_auto_pending_ids': deferred, 'new_model_requests': 0,
        'scope': 'Only actually reviewed extraction fields; no task-quality correction, new expert sample or cross-version best-of mixing.',
        'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv])})
    print(json.dumps({'status': 'completed_real_version_bound_returns', 'groups_forwarded': len(results),
        'missing_auto_pending_ids': deferred, 'new_model_requests': 0}))


def self_check(args):
    expected = 'synthetic-package-A'; ids = {'S01', 'S02'}
    good = {'schema': 'expert-version-receipt-v1', 'package_manifest_sha256': expected,
        'reviewer_id': 'synthetic-one-expert', 'review_date': 'synthetic-day-1',
        'reviewed_answer_ids': ['S01'], 'version_confirmed': True}
    cases = [('blank_receipt', {**good, 'reviewer_id': ''}),
        ('wrong_version', {**good, 'package_manifest_sha256': 'synthetic-package-B'}),
        ('unconfirmed', {**good, 'version_confirmed': False}),
        ('unknown_ID', {**good, 'reviewed_answer_ids': ['OUTSIDE']})]
    checks = []
    for name, bad in cases:
        try:
            validate_receipts([bad], expected, ids)
        except ValueError:
            checks.append({'name': name, 'rejected': True})
        else:
            raise AssertionError(name + ' was accepted')
    two_dates = [good, {**good, 'review_date': 'synthetic-day-2', 'reviewed_answer_ids': ['S02']}]
    require(len(validate_receipts(two_dates, expected, ids)) == 2, 'Same expert split dates should be permitted')
    try:
        validate_receipts([good, {**good, 'reviewer_id': 'synthetic-second-expert', 'reviewed_answer_ids': ['S02']}], expected, ids)
    except ValueError:
        checks.append({'name': 'multiple_experts', 'rejected': True})
    else:
        raise AssertionError('Two experts were accepted')
    synthetic = [{'answer_id': 'S01', 'item': item, 'split': 'synthetic', 'review_status': 'reviewed',
        'expert_decision': '成立', 'reviewer_id': good['reviewer_id'], 'review_date': good['review_date']} for item in ITEMS]
    keys = {(r['answer_id'], r['item'], r['split']) for r in synthetic}
    try:
        validate_review_version_gate(synthetic, set(), keys)
    except ValueError:
        checks.append({'name': 'affirmative_no_change_without_receipt', 'rejected': True})
    else:
        raise AssertionError('Unauthenticated no-change review was accepted')
    require(len(validate_review_version_gate(synthetic, validate_receipts([good], expected, ids), keys)) == 4, 'Version-bound affirmative rows should pass this gate')
    result = {'status': 'pass', 'scope': 'isolated_synthetic_software_only_not_expert_returns',
        'rejection_checks': checks, 'same_expert_multiple_dates': 'pass', 'valid_version_gate': 'pass',
        'real_forms_or_receipts_modified': False, 'new_model_requests': 0,
        'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv])}
    save(OUT / 'software_fixtures/guard_checks.json', result)
    print(json.dumps({'status': 'synthetic_checks_pass', 'rejections': len(checks), 'real_expert_returns_created': 0}))


if __name__ == '__main__':
    socket.create_connection = no_network; socket.socket.connect = no_network
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'preflight', 'rescore', 'self-check'])
    parser.add_argument('--review', type=Path, default=FORM)
    parser.add_argument('--receipts', type=Path, default=OUT / 'received_receipts.json')
    parser.add_argument('--corrections', type=Path, default=CORRECTIONS)
    args = parser.parse_args()
    {'prepare': prepare, 'preflight': preflight, 'rescore': rescore, 'self-check': self_check}[args.command](args)
