"""Independent post-hoc component replay of the original public v9 development batch.

No model calls, retries, source edits, or revised ordinal interpretation.  The
original v9 validate/terminal functions and frozen scientific dependencies must
pass before the candidate adapter receives an envelope.  A separate root review
authorization is mandatory for the real replay command.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import csv
import io
import inspect
import json
import socket
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_runner_v9 as backend
import cce_partial_components_v1 as partial
j = backend.j
ground = backend.grounded
BASE = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010'
BATCH = BASE / 'grounded_development_v9'
OUT = BASE / 'explicit_posthoc_component_replay_v9'
VERSION = 'explicit-posthoc-components-original-v9-v1'
IDS = ['A01', 'A02', 'A03', 'A04', 'A05']


def require(value, message):
    if not value:
        raise ValueError(message)


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': j.filehash(path)}


def exact_int(value, expected):
    return type(value) is int and value == expected


def safe_reads():
    """Install process-wide no-network/protected-body guards for this CLI."""
    def denied(*args, **kwargs):
        raise AssertionError('POSTHOC_NETWORK_FORBIDDEN')
    original_connect = socket.socket.connect
    def guarded_connect(sock, address):
        caller = inspect.currentframe().f_back
        if caller.f_code.co_name == '_fallback_socketpair' and Path(caller.f_code.co_filename).name == 'socket.py' and address[0] in ['127.0.0.1', '::1'] and address[1] != 11434:
            return original_connect(sock, address)  # Windows asyncio self-pipe only.
        return denied(sock, address)
    socket.create_connection = denied
    socket.socket.connect = guarded_connect
    def audit(event, args):
        if event != 'open' or not args or not isinstance(args[0], (str, bytes)):
            return
        path = str(Path(args[0]).resolve()).lower().replace('\\', '/')
        require(not any(x in path for x in ['/sealed', '/human_review/', 'identity_key',
            '/confirmation_sampling_v1/sealed_metadata', '/grounded_confirmation']), 'PROTECTED_BODY_ACCESS_FORBIDDEN')
        if path.endswith('/judges/request_ledger.jsonl') and len(args) > 1:
            mode = args[1]
            require(mode is None or not any(x in str(mode) for x in 'wa+'), 'LEDGER_WRITE_FORBIDDEN')
    sys.addaudithook(audit)


def verify_science(contract):
    require(ground.VERSION == 'source_bound_extraction_v9', 'ORIGINAL_V9_BACKEND_REQUIRED')
    ext = contract['round2_extraction']
    require(ext['version'] == ground.VERSION and ext['module_sha256'] == j.filehash(ground.__file__)
        and ext['runner_sha256'] == j.filehash(backend.__file__)
        and ext['score_adapter_sha256'] == j.filehash(backend.scoring.__file__)
        and exact_int(ext['max_attempts'], 1), 'ORIGINAL_V9_CONVERTER_RUNNER_SCORER_BINDING')
    require(len(contract['models']) == 1 and contract['models'][0]['name'] == backend.MODEL, 'ORIGINAL_SINGLE_MODEL_REQUIRED')
    model = contract['models'][0]
    a, runner, _, registry = backend.readonly_runtime()
    actual = j.contract(a, runner, registry, [{'name': model['name'], 'family': model['family'], 'public': model['settings']}])
    require(all(actual[k] == contract[k] for k in backend.SCIENCE_KEYS + ['models']), 'ORIGINAL_SCIENCE_OR_MODEL_IDENTITY_CHANGED')
    require(all(contract[k] == j.read(backend.BASE_CONTRACT)[k] for k in backend.SCIENCE_KEYS), 'HISTORICAL_SCIENCE_CONTRACT_CHANGED')
    return {'original_v9_module': bind(ground.__file__), 'original_v9_runner': bind(backend.__file__),
        'original_numeric_adapter': bind(backend.scoring.__file__), 'science_keys_verified': backend.SCIENCE_KEYS,
        'original_ordinal_policy_retained': True, 'new_service_query': False,
        'model_identity': copy.deepcopy(contract['models'])}


def verify_cell(batch, row, case, contract):
    """Actual source chain, without trusting self-reported success or pass flags."""
    batch = Path(batch)
    trial = backend.terminal_identity(batch, row)  # original receipt/ledger/hash chain
    tid = row['planned_trial_id']; attempt = batch / 'run/attempts' / f'{tid}_1'
    require(exact_int(row['attempt'], 1) and exact_int(trial['attempt'], 1), 'EXACT_INTEGER_ATTEMPT_REQUIRED')
    require(exact_int(row['identity']['repeat_index'], 0) and trial['actual_request_made'] is True, 'ORIGINAL_REAL_REPEAT_ZERO_REQUIRED')
    require(trial['anonymous_answer_id'] == row['anonymous_answer_id'] == case['anonymous_answer_id'], 'ANONYMOUS_IDENTITY_CHANGED')
    expected_identity = {'case_id': case['case_id'], 'input_sha256': j.digest({'question': case['specific_question'],
        'question_id': case['question_id'], 'protocol': case['model_response'], 'references': case['references']}),
        'judge': backend.MODEL, 'repeat_index': 0, 'contract_sha256': j.digest(contract),
        'payload_sha256': j.digest(j.read(row['assets']['payload']['path'])), 'round_id': backend.budget.ROUND}
    require(row['identity'] == expected_identity, 'FULL_FROZEN_IDENTITY_CHANGED')
    receipt_path = attempt / 'request_receipt.json'; receipt = j.read(receipt_path)
    require(exact_int(receipt['attempt'], 1) and receipt['event'] == 'request_started'
        and receipt['round_id'] == backend.budget.ROUND and receipt['phase'] == 'development'
        and receipt['authorization_sha256'] == backend.budget.AUTH_SHA
        and receipt['request_id'] == j.digest({'trial_id': tid, 'attempt': 1}), 'REAL_ORIGINAL_REQUEST_RECEIPT_REQUIRED')
    require(exact_int(receipt['package_request_index'], receipt['package_request_index']), 'PACKAGE_REQUEST_INDEX_TYPE')
    backend.verify_required(trial['bound_artifacts'], [receipt_path, attempt / 'http_request_payload.json', attempt / 'prompt.txt'])
    doc = j.read(row['assets']['source_document']['path']); public = contract['models'][0]['settings']
    prompt = Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
    require(ground.make_prompt(case, doc) == prompt, 'ORIGINAL_V9_FULL_PROMPT_REBUILD_FAILED')
    require((attempt / 'prompt.txt').read_bytes() == prompt.encode('utf8'), 'TRANSMITTED_PROMPT_BYTES_CHANGED')
    require(j.read(attempt / 'http_request_payload.json') == backend.payload_for(prompt, ground.schema_for_document(doc), public), 'ACTUAL_HTTP_SCIENTIFIC_PAYLOAD_CHANGED')
    e = trial['evaluation']; require(e['technical_status'] == ('SUCCESS' if trial['status'] == 'success' else 'FAILED'), 'TECHNICAL_STATUS_CONFLICT')
    if trial['status'] == 'failed':
        failure_path = attempt / 'failure.json'; backend.verify_required(trial['bound_artifacts'], [failure_path])
        failure = j.read(failure_path)
        require(failure['stage'] == e['failure_stage'] and failure in e['grounded_extraction_v9']['conversion_errors'], 'ORIGINAL_FAILURE_STAGE_OR_RECORD_CHANGED')
        require(e['metrics'] == backend.scoring.derive({}, row['step'], False), 'OLD_FAILED_METRICS_CHANGED')
    else:
        require(e['failure_stage'] is None, 'SUCCESS_WITH_FAILURE_STAGE')
    require(e['grounded_extraction_v9']['raw_return_modified'] is False and e['grounded_extraction_v9']['legacy_parser_fallback_used'] is False,
        'RAW_MODIFICATION_OR_FALLBACK_NOT_ALLOWED')
    provider_path = attempt / 'provider_response.json'; raw_path = attempt / 'raw_source_bound_content.txt'
    provider = None; raw = None; raw_receipt = None
    if provider_path.exists():
        backend.verify_required(trial['bound_artifacts'], [provider_path]); provider = j.read(provider_path)
    if raw_path.exists():
        raw_receipt_path = attempt / 'raw_source_bound_receipt.json'
        backend.verify_required(trial['bound_artifacts'], [raw_path, raw_receipt_path])
        raw = raw_path.read_bytes().decode('utf8'); raw_receipt = j.read(raw_receipt_path)
        require(isinstance(provider, dict) and provider.get('response') == raw, 'PROVIDER_RAW_TEXT_MISMATCH')
        require(raw_receipt['raw_response_sha256'] == ground.rawsha(raw) and raw_receipt['raw_text_file_sha256'] == j.filehash(raw_path)
            and raw_receipt['source_document'] == row['assets']['source_document'] and raw_receipt['raw_text_unchanged'] is True,
            'RAW_SIDECAR_SOURCE_BINDING_CHANGED')
    elif isinstance(provider, dict):
        require(not isinstance(provider.get('response'), str), 'MISSING_COMMITTED_RAW_TEXT')
    first_failure_replay = {'status': 'not_applicable_success'}
    if trial['status'] == 'failed' and e['failure_stage'] != 'PROVIDER_TRANSPORT':
        expected_stage = e['failure_stage']
        replay_stage = 'PROVIDER_COMPLETION'; reproduced = None
        try:
            backend.validate_provider(provider, public)
            replay_stage = 'SOURCE_BOUND_CONVERSION'; original_cv = ground.convert(raw, doc)
            replay_stage = 'ORIGINAL_OFFLINE_NUMERIC_SCORING'
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                backend.scoring.score_conversion(case, original_cv, backend.BACKEND, row['step'])
        except Exception as exc:
            reproduced = {'stage': replay_stage, 'type': type(exc).__name__, 'reason': str(exc)}
        require(reproduced is not None and all(reproduced[k] == failure[k] for k in ['stage', 'type', 'reason']), 'ORIGINAL_FIRST_FAILURE_NOT_REPRODUCED')
        first_failure_replay = {'status': 'original_first_failure_reproduced', **reproduced}
    elif trial['status'] == 'failed':
        first_failure_replay = {'status': 'transport_not_reinvoked; original_bound_failure_retained', 'stage': e['failure_stage']}
    if trial['status'] == 'success':
        require(raw is not None and provider is not None, 'SUCCESS_MISSING_PROVIDER_OR_RAW')
        backend.validate_provider(provider, public)
        original_cv = ground.convert(raw, doc)
        backend.verify_required(trial['bound_artifacts'], [attempt / 'source_bound_conversion.json', attempt / 'numeric_result.json'])
        require(original_cv == e['grounded_extraction_v9']['conversion'] == j.read(attempt / 'source_bound_conversion.json'), 'ORIGINAL_V9_SUCCESS_CONVERSION_DRIFT')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            original_numeric = backend.scoring.score_conversion(case, original_cv, backend.BACKEND, row['step'])
        require(original_numeric == e['numeric_result'] == j.read(attempt / 'numeric_result.json') and original_numeric['metrics'] == e['metrics'], 'ORIGINAL_SUCCESS_NUMERIC_DRIFT')
    envelope = None
    if raw is not None:
        envelope = {'upstream_technical_status': trial['status'], 'upstream_failure': copy.deepcopy(e['grounded_extraction_v9']['conversion_errors']),
            'actual_request_made': trial['actual_request_made'], 'planned_identity': row['identity'], 'trial_identity': trial['identity'],
            'request_receipt': receipt, 'http_request_payload': j.read(attempt / 'http_request_payload.json'),
            'expected_http_payload': j.read(row['assets']['payload']['path']), 'expected_public_model': public,
            'raw_response_sha256': raw_receipt['raw_response_sha256'], 'source_document_sha256': j.digest(doc), 'provider_response': provider}
    return {'trial': trial, 'doc': doc, 'raw': raw, 'envelope': envelope, 'first_failure_replay': first_failure_replay,
        'provenance': [bind(batch / 'run/trials' / f'{tid}.json'), *trial['bound_artifacts'], *row['assets'].values(), *row['step']['provenance']],
        'checks': ['original_terminal_identity_and_actual_ledger_receipt', 'typed_attempt_repeat_and_anonymous_identity',
            'full_input_contract_payload_identity', 'original_v9_full_prompt_rebuild', 'transmitted_prompt_bytes',
            'provider_raw_sidecar_bound_files', 'failure_status_and_original_NA_retained', 'success_original_numeric_and_conversion_replay']}


def verify_batch(batch, software_only=False):
    batch = Path(batch).resolve()
    require(software_only or batch == BATCH.resolve(), 'ONLY_ORIGINAL_V9_PUBLIC_DEVELOPMENT_ALLOWED')
    plan, cases, matrix, contract = backend.validate(batch)
    require(plan['candidate_version'] == ground.VERSION and plan['status'] == 'frozen_before_generation', 'ORIGINAL_V9_PLAN_REQUIRED')
    backend.verify_required(plan['frozen_inputs'], [backend.__file__, ground.__file__, backend.scoring.__file__,
        batch / 'cases.json', batch / 'step_inputs.json', batch / 'expected_contract.json', batch / 'matrix.json'])
    require([c['anonymous_answer_id'] for c in cases] == IDS and [r['anonymous_answer_id'] for r in matrix] == IDS, 'FIXED_FIVE_DENOMINATOR')
    science = verify_science(contract)
    ver = j.read(batch / 'analysis_verification.json'); summary = j.read(batch / 'completion_summary.json')
    require(ver['status'] == 'pass' and ver['all_five_terminal'] is True and exact_int(ver['terminal_observations'], 5), 'OLD_REAL_ANALYSIS_NOT_COMPLETE')
    backend.verify_required(ver['bindings'], [batch / 'plan.json', batch / 'matrix.json', batch / 'per_answer.json', batch / 'completion_summary.json'])
    require(summary['status'] == 'experiment_complete_not_scientific_validation' and exact_int(summary['actual_observations'], 5)
        and exact_int(summary['planned_observations'], 5) and exact_int(summary['pending'], 0), 'OLD_COMPLETE_BATCH_REQUIRED')
    backend.verify_bindings(summary['bound_observations'])
    checks = [verify_cell(batch, r, c, contract) for r, c in zip(matrix, cases)]
    previous = j.read(batch / 'per_answer.json')
    require(len(previous) == 5, 'OLD_PER_ANSWER_DENOMINATOR')
    for old, row, checked in zip(previous, matrix, checks):
        require(old['anonymous_answer_id'] == row['anonymous_answer_id'] and old['trial_id'] == row['planned_trial_id']
            and old['status'] == checked['trial']['status'] and old['metrics'] == checked['trial']['evaluation']['metrics'], 'OLD_ANALYSIS_ROW_BINDING')
    return {'plan': plan, 'cases': cases, 'matrix': matrix, 'contract': contract, 'science': science, 'checks': checks,
        'source_bindings': [bind(batch / name) for name in ['plan.json', 'matrix.json', 'expected_contract.json', 'analysis_verification.json',
            'completion_summary.json', 'per_answer.json', 'cases.json', 'step_inputs.json']], 'software_only': software_only}


def perform_replay(verified, destination):
    destination = Path(destination).resolve(); require(not destination.exists(), 'REFUSE_OVERWRITE_POSTHOC_OUTPUT')
    rows = []; full = []; protected = list(verified['source_bindings']) + list(verified['plan']['frozen_inputs'])
    for case, matrix, checked in zip(verified['cases'], verified['matrix'], verified['checks']):
        protected.extend(checked['provenance'])
        trial = checked['trial']; old = trial['evaluation']['metrics']
        if checked['envelope'] is None:
            audit = {'shared_gate': {'pass': False, 'reason': 'NO_COMMITTED_RAW_RETURN'}, 'metrics': backend.scoring.derive({}, matrix['step'], False),
                'whole_technical_success': False, 'raw_content_preserved': None, 'new_model_requests': 0}
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                audit = partial.audit_components(checked['raw'], checked['doc'], case, backend, matrix['step'], checked['envelope'])
        require(not audit['whole_technical_success'] or trial['status'] == 'success', 'FAILED_OBSERVATION_PROMOTED')
        if trial['status'] == 'success':
            require(all(backend.scoring.same(old[k], audit['metrics'][k]) for k in backend.scoring.METRICS), 'VALID_ORIGINAL_RESULT_CHANGED')
        full.append({'anonymous_answer_id': case['anonymous_answer_id'], 'trial_id': trial['trial_id'], 'original_status': trial['status'],
            'source_chain_checks': checked['checks'], 'first_failure_replay': checked['first_failure_replay'], 'provenance': checked['provenance'], 'audit': audit})
        for metric in backend.scoring.METRICS:
            new = audit['metrics'][metric]
            rows.append({'anonymous_answer_id': case['anonymous_answer_id'], 'trial_id': trial['trial_id'], 'metric': metric,
                'original_status': trial['status'], 'original_value': old[metric], 'posthoc_component_value': new,
                'newly_available': old[metric] is None and backend.scoring.finite(new),
                'unchanged': backend.scoring.same(old[metric], new), 'new_model_observation': False, 'expert_truth': False})
    unique = {x['path']: x for x in protected}; backend.verify_bindings(list(unique.values()))
    destination.mkdir(parents=True)
    j.save(destination / 'full_component_audits.json', full); j.save(destination / 'component_comparison.json', rows)
    with (destination / 'component_comparison.csv').open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {'status': 'posthoc_component_replay_not_new_evaluation', 'version': VERSION, 'software_only': verified['software_only'],
        'denominator': 5, 'metric_rows': len(rows), 'original_successes': sum(c['trial']['status'] == 'success' for c in verified['checks']),
        'original_failures': sum(c['trial']['status'] == 'failed' for c in verified['checks']),
        'newly_available_counts': {m: sum(r['newly_available'] for r in rows if r['metric'] == m) for m in backend.scoring.METRICS},
        'new_model_requests': 0, 'failed_observation_promoted': False, 'formal_eligible': False, 'expert_confirmed': False,
        'source_and_original_outputs_unchanged': True, 'original_v9_ordinal_policy_retained': True,
        'scientific_correctness_established': False, 'science_verification': verified['science'],
        'protected_bindings': list(unique.values()), 'implementation_bindings': [bind(__file__), bind(partial.__file__)],
        'actual_command': [sys.executable, *sys.argv]}
    j.save(destination / 'summary.json', summary)
    return summary


def review_gate(path):
    approval = j.read(path)
    require(approval.get('status') == 'approved_for_explicit_posthoc_v9_component_replay' and approval.get('reviewed_by') == 'root_agent'
        and approval.get('new_model_requests') == 0 and approval.get('original_status_preserved') is True, 'ROOT_REPLAY_REVIEW_REQUIRED')
    required = [Path(__file__), Path(partial.__file__), OUT / 'draft/execution_02/software_verification.json',
        BATCH / 'plan.json', BATCH / 'analysis_verification.json', BATCH / 'matrix.json', BATCH / 'expected_contract.json']
    backend.verify_required(approval['bindings'], required)
    return approval


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['describe', 'replay'])
    p.add_argument('--review-approval', type=Path); p.add_argument('--out', type=Path, default=OUT / 'actual_replay')
    args = p.parse_args(); safe_reads()
    if args.action == 'describe':
        print(j.canonical({'version': VERSION, 'backend': bind(backend.__file__), 'converter': bind(ground.__file__),
            'only_real_batch': str(BATCH), 'actual_replay_executed': False, 'new_model_requests': 0})); return
    require(args.review_approval is not None, 'ROOT_REPLAY_REVIEW_REQUIRED')
    require(args.out.resolve().is_relative_to(OUT.resolve()), 'INDEPENDENT_POSTHOC_OUTPUT_REQUIRED')
    review_gate(args.review_approval)
    result = perform_replay(verify_batch(BATCH), args.out)
    print(j.canonical({k: result[k] for k in ['status', 'denominator', 'new_model_requests', 'original_successes', 'original_failures', 'newly_available_counts']}))


if __name__ == '__main__':
    main()
