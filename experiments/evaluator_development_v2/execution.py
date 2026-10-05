"""Budgeted local teacher execution and externally observed call imports."""
from copy import deepcopy
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid

from evaluator_integrity import parse_judge_object
from experiments.construct_validity.contract import adjudicate
from .io import Lock, append, canonical, digest, file_hash, ledger, now, read, save
from .prepare import callable_at, verify
from .metrics import STATES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def loopback(judge):
    base = judge.get('base_url', 'http://127.0.0.1:11434')
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('Only credential-free loopback HTTP is permitted')
    return base.rstrip('/')


def http_json(base, endpoint, payload=None, timeout=600):
    request = urllib.request.Request(base + endpoint,
        data=canonical(payload).encode('utf-8') if payload is not None else None,
        headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def model_revision(base, judge, snapshot=None):
    raw = http_json(base, '/api/tags', timeout=30)
    if snapshot is not None:
        with Path(snapshot).open('xb') as handle:
            handle.write(raw)
    data = json.loads(raw)
    names = {judge['model'], judge['model'] + ':latest'}
    matches = [row['digest'] for row in data['models'] if row.get('name') in names]
    if len(matches) != 1:
        raise ValueError('Teacher model revision cannot be bound uniquely')
    if judge['revision'] not in ('UNKNOWN', matches[0]):
        raise ValueError('Declared model revision differs from local service')
    return matches[0]


def proposal_vector(public, parsed):
    expected = [req['id'] for req in public.get('requirements', [])]
    if not isinstance(parsed, dict):
        raise ValueError('Teacher JSON must be an object')
    assessment = parsed.get('assessment', parsed)
    if not isinstance(assessment, dict):
        raise ValueError('Missing requirement judgment object')
    rows = assessment.get('requirements', [] if not expected else None)
    if not isinstance(rows, list):
        raise ValueError('Missing requirement judgment vector')
    proposed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Requirement state must be an object')
        if row.get('id') in proposed or row.get('status') not in STATES:
            raise ValueError('Duplicate or invalid proposed requirement state')
        proposed[row['id']] = row['status']
    if set(proposed) != set(expected):
        raise ValueError('Proposed requirement identity set differs from frozen task')
    return proposed


def vectors(public, parsed, processors):
    expected = [req['id'] for req in public.get('requirements', [])]
    proposed = proposal_vector(public, parsed)
    assessment = parsed.get('assessment', parsed)
    mechanisms = {}
    for processor in processors:
        if processor.get('entrypoint'):
            function, _ = callable_at(processor['entrypoint'])
            observed = function(deepcopy(public), deepcopy(parsed))
        elif not expected:
            observed = {'requirements': [], 'overall': 'UNRESOLVED',
                        'limitations': 'Structure observation only; no scientific requirement judgment'}
        else:
            observed = adjudicate(deepcopy(assessment), deepcopy(public['requirements']),
                public['protocol'], deepcopy(public.get('source_cards', public.get('cards', []))))
        effective = {row['id']: row.get('effective_status', row.get('status'))
                     for row in observed.get('requirements', observed.get('requirement_results', []))}
        if set(effective) != set(expected) or any(value not in STATES for value in effective.values()):
            raise ValueError('Processor must return a complete four-state vector')
        mechanisms[processor['id']] = {'effective_vector': effective, 'observed': observed,
            'public_input_sha256': digest(public), 'parsed_sha256': digest(parsed)}
    first = processors[0]['id']
    return proposed, mechanisms[first]['effective_vector'], mechanisms


def attempt_records(folder):
    path = Path(folder) / 'events.jsonl'
    events = ledger(path)
    records = []
    for event in events:
        if event.get('kind') == 'ATTEMPT_FINISHED':
            record_path = Path(folder) / event['record']
            if file_hash(record_path) != event['record_sha256']:
                raise ValueError('Saved attempt changed')
            records.append(read(record_path))
    return events, records


def _finish(folder, manifest, trial, started, folder_attempt, response_bytes, actual_revision,
            origin, actual_invocation, processors, public, failure=None):
    record = {**trial, **started, 'completed_at': now(), 'origin': origin,
        'invocation_id': actual_invocation, 'actual_revision': actual_revision,
        'manifest_sha256': manifest['manifest_sha256'], 'technical_status': 'FAILED',
        'proposed_vector': {}, 'effective_vector': {}, 'structure_vector': {}, 'mechanisms': {},
        'parsed_judge_vector_status': 'NOT_ASSESSED', 'technical_stage': 'TRANSPORT', 'failure': failure}
    if response_bytes is not None:
        path = folder_attempt / 'response.json'
        with path.open('xb') as handle:
            handle.write(response_bytes)
        record['response_sha256'] = file_hash(path)
    if failure is None:
        try:
            transport = json.loads(response_bytes)
            record['technical_stage'] = 'TRANSPORT_ENVELOPE_VALIDATION'
            if not isinstance(transport, dict):
                raise ValueError('Teacher response envelope must be an object')
            if origin in ('OLLAMA_ACTUAL', 'TEST_TRANSPORT'):
                record['technical_stage'] = 'MODEL_IDENTITY_VALIDATION'
                judge = next(j for j in read(Path(folder) / 'judges.json') if j['id'] == trial['judge_id'])
                if transport.get('model') not in (judge['model'], judge['model'] + ':latest'):
                    raise ValueError('Returned teacher model differs from frozen configuration')
                record['technical_stage'] = 'GENERATION_COMPLETION'
                record['generation_metadata'] = {k:transport.get(k) for k in
                    ('done','done_reason','eval_count','prompt_eval_count')}
                if transport.get('done') is not True or transport.get('done_reason') != 'stop':
                    code = ('GENERATION_NON_TERMINAL' if transport.get('done') is not True
                            else 'OUTPUT_BUDGET_EXHAUSTED' if transport.get('done_reason') == 'length'
                            else 'UNSUPPORTED_COMPLETION_REASON')
                    record['failure_code'] = code
                    raise ValueError('Teacher response was not terminal stop: '+code)
                content = transport.get('response')
            else:
                content = transport.get('content')
            if not isinstance(content, str) or not content.strip():
                raise ValueError('Teacher returned no content')
            record['technical_stage'] = 'STRUCTURED_PARSE'
            parsed = parse_judge_object(content)
            save(folder_attempt / 'parsed.json', parsed)
            record['technical_stage'] = 'PROPOSAL_VALIDATION'
            proposed = proposal_vector(public, parsed)
            fields = public.get('requested_fields', [key for key in parsed if key != 'requirements'])
            structure = {field: {'present': field in parsed, 'value': parsed.get(field)} for field in fields}
            record.update(proposed_vector=proposed, structure_vector=structure, parsed_judge_vector_status='COMPLETE')
            record['technical_stage'] = 'GROUNDING_VALIDATION'
            proposed, effective, mechanisms = vectors(public, parsed, processors)
            record.update(technical_status='COMPLETE', structure_vector=structure, proposed_vector=proposed,
                          effective_vector=effective, mechanisms=mechanisms, failure=None, technical_stage='COMPLETE')
        except Exception as exc:
            record['failure'] = {'type': type(exc).__name__, 'message': str(exc), 'stage': record['technical_stage']}
            if record.get('failure_code'):
                record['failure']['code'] = record['failure_code']
    for name in ('request.json', 'receipt.json', 'parsed.json', 'tags_before.json', 'tags_after.json'):
        path = folder_attempt / name
        if path.exists():
            record[name.replace('.json', '_sha256')] = file_hash(path)
    save(folder_attempt / 'result.json', record)
    append(Path(folder) / 'events.jsonl', {'kind': 'ATTEMPT_FINISHED', 'at': now(),
        'trial_id': trial['id'], 'record': (folder_attempt / 'result.json').relative_to(folder).as_posix(),
        'record_sha256': file_hash(folder_attempt / 'result.json')})
    return record


def run(folder, *, max_calls, allow_model_requests=False, acknowledge_failures=False,
        retry_failed=False, max_seconds=172800, transport=None):
    """max_calls is the cumulative study inference request ceiling across rounds."""
    folder = Path(folder).resolve()
    manifest = verify(folder)
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
        raise ValueError('An explicit positive inference budget is required')
    if not 0 < max_seconds <= 172800:
        raise ValueError('Wall budget must be in (0, 172800] seconds')
    if transport is None and allow_model_requests is not True:
        raise ValueError('Real requests require explicit caller authorization')
    invocation = uuid.uuid4().hex
    stop = time.monotonic() + max_seconds
    with Lock(folder.parent / '.inference_budget_lock'), Lock(folder / '.run_lock'):
        events, records = attempt_records(folder)
        if any(row['technical_status'] == 'FAILED' for row in records) and not acknowledge_failures:
            return {'status': 'FAILURE_REQUIRES_DIAGNOSIS', 'model_calls_dispatched': 0}
        finished_attempts = {r['attempt_id'] for r in records}
        if any(event.get('kind') == 'ATTEMPT_STARTED' and event['attempt_id'] not in finished_attempts for event in events):
            raise ValueError('Unfinished attempt requires process/transport reconciliation; no duplicate dispatch')
        append(folder / 'events.jsonl', {'kind': 'RUN_STARTED', 'at': now(),
            'invocation_id': invocation, 'max_calls': max_calls,
            'allow_model_requests': allow_model_requests, 'retry_failed': retry_failed})
        used = 0
        for registered in ledger(folder.parent / 'rounds.jsonl'):
            used += sum(event.get('kind') == 'INFERENCE_DISPATCHED'
                        for event in ledger(folder.parent / registered['round_id'] / 'events.jsonl'))
        sent = 0
        cases = {row['id']: row for row in read(folder / 'cases.json')}
        judges = {row['id']: row for row in read(folder / 'judges.json')}
        processors = read(folder / 'processors.json')
        for trial in read(folder / 'trials.json'):
            old = [r for r in records if r['id'] == trial['id']]
            if any(r['technical_status'] == 'COMPLETE' for r in old) or (old and not retry_failed):
                continue
            judge = judges[trial['judge_id']]
            if judge['transport'] != 'OLLAMA_LOOPBACK':
                continue
            if used >= max_calls or time.monotonic() >= stop:
                break
            verify(folder)
            attempt = uuid.uuid4().hex
            started = {'attempt_id': attempt, 'run_invocation_id': invocation, 'started_at': now()}
            target = folder / 'attempts' / trial['id'] / attempt
            target.mkdir(parents=True)
            prompt = (folder / 'prompts' / f"{trial['candidate_id']}.txt").read_bytes().decode('utf-8')
            payload = {'model': judge['model'], 'prompt': prompt, 'stream': False,
                       'think': False, 'format': 'json', 'options': judge['params']}
            save(target / 'request.json', {'payload': payload, 'payload_sha256': digest(payload),
                'prompt_sha256': trial['prompt_sha256'], 'input_sha256': trial['input_sha256']})
            append(folder / 'events.jsonl', {'kind': 'ATTEMPT_STARTED', **started, 'trial_id': trial['id']})
            raw, revision, failure = None, 'UNKNOWN', None
            origin = 'TEST_TRANSPORT' if transport else 'OLLAMA_ACTUAL'
            try:
                base = loopback(judge)
                revision = judge['revision'] if transport else model_revision(base, judge, target / 'tags_before.json')
                append(folder / 'events.jsonl', {'kind': 'INFERENCE_DISPATCHED', 'at': now(),
                    'attempt_id': attempt, 'origin': origin, 'model_call': transport is None})
                used += 1
                sent += int(transport is None)
                raw = (transport(payload) if transport else http_json(base, '/api/generate', payload,
                    timeout=min(judge.get('timeout_seconds', 600), max(1, stop - time.monotonic()))))
                if not isinstance(raw, bytes):
                    raise ValueError('Transport must return raw bytes')
                if transport is None and model_revision(base, judge, target / 'tags_after.json') != revision:
                    raise ValueError('Teacher revision changed during invocation')
            except Exception as exc:
                failure = {'type': type(exc).__name__, 'message': str(exc)}
            record = _finish(folder, manifest, trial, started, target, raw, revision,
                origin, attempt, processors, cases[trial['candidate_id']]['input'], failure)
            records.append(record)
            if record['technical_status'] != 'COMPLETE':
                break
    return {'status': 'STOPPED_OR_BUDGET_COMPLETED', 'model_calls_dispatched': sent}


def import_external(folder, trial_id, response_file, receipt):
    """Import an actual separate Codex call; never invent a provider HTTP request."""
    folder = Path(folder).resolve()
    manifest = verify(folder)
    trial = next(row for row in read(folder / 'trials.json') if row['id'] == trial_id)
    judge = next(row for row in read(folder / 'judges.json') if row['id'] == trial['judge_id'])
    if judge['transport'] != 'EXTERNAL_ACTUAL':
        raise ValueError('This trial is not assigned to an external teacher')
    required = {'invocation_id', 'prompt_sha256', 'input_sha256', 'model', 'family',
                'actual_revision', 'actual_params', 'cache_used', 'origin'}
    if required - set(receipt) or not isinstance(receipt.get('invocation_id'), str) or not receipt['invocation_id'] or receipt['cache_used'] is not False or receipt['origin'] != 'EXTERNAL_ACTUAL':
        raise ValueError('Actual invocation and explicit no-cache evidence are required')
    for key in ('prompt_sha256', 'input_sha256'):
        if receipt[key] != trial[key]:
            raise ValueError('External teacher visible input differs from frozen trial')
    if receipt['model'] != judge['model'] or receipt['family'] != judge['family']:
        raise ValueError('External teacher identity mismatch')
    if judge['revision'] != 'UNKNOWN' and receipt['actual_revision'] != judge['revision']:
        raise ValueError('External revision mismatch')
    if judge.get('params') is not None and receipt['actual_params'] != judge['params']:
        raise ValueError('External parameter condition differs')
    with Lock(folder / '.run_lock'):
        events, records = attempt_records(folder)
        if any(row['id'] == trial_id and row['technical_status'] == 'COMPLETE' for row in records):
            raise ValueError('Trial already completed')
        if any(row['invocation_id'] == receipt['invocation_id'] for row in records):
            raise ValueError('Copied invocation cannot be another independent repeat')
        attempt = uuid.uuid4().hex
        target = folder / 'attempts' / trial_id / attempt
        target.mkdir(parents=True)
        save(target / 'receipt.json', receipt)
        started = {'attempt_id': attempt, 'started_at': now(), 'run_invocation_id': 'EXTERNAL_IMPORT'}
        append(folder / 'events.jsonl', {'kind': 'ATTEMPT_STARTED', **started, 'trial_id': trial_id})
        public = next(row['input'] for row in read(folder / 'cases.json') if row['id'] == trial['candidate_id'])
        raw = Path(response_file).read_bytes()
        return _finish(folder, manifest, trial, started, target, raw,
            receipt['actual_revision'], 'EXTERNAL_ACTUAL', receipt['invocation_id'],
            read(folder / 'processors.json'), public)