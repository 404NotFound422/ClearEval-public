"""Offline adapters call production APIs; private expectations never enter compute()."""
from copy import deepcopy
import json
from experiments.construct_validity import fidelity
from experiments.construct_validity.contract import adjudicate, digest
from experiments.construct_validity.evidence import (
    SCHEMA as EVIDENCE_SCHEMA, check_scientific_support, scope_leaves, validate_cards)
from experiments.construct_validity.execution_identity import (
    execution_identity, information_hash, repeat_diagnostic)
from experiments.construct_validity.objectives import compare_candidates
from evaluator_integrity import JudgeFormatError, parse_judge_object

VERSION = 'evaluator-development-adapters-v2'


def _support(protocol, raw, *, span=None):
    if span is None:
        start = protocol.index(raw)
        span = {'start': start, 'end': start + len(raw), 'quote': raw}
    return {'kind': 'EXPLICIT', 'raw_value': raw, 'transform': 'IDENTITY',
            'spans': [span]}


def extraction_probe(data):
    # Public task contract is the only source of required-field coverage.
    return fidelity.audit_facts(deepcopy(data['proposed_facts']), data['protocol'],
        deepcopy(data.get('task', {}).get('required_fields')))


def json_probe(data):
    try:
        parsed = parse_judge_object(data['text'])
        if 'allowed_fields' in data and set(parsed) - set(data['allowed_fields']):
            raise JudgeFormatError('Unknown field in declared input schema')
        return {'status': 'VALID', 'parsed': parsed}
    except JudgeFormatError as exc:
        message = str(exc)
        reason = ('DUPLICATE_KEY' if 'Duplicate JSON key' in message else
                  'NON_FINITE_JSON' if 'Non-finite' in message else
                  'UNKNOWN_FIELD' if 'Unknown field' in message else 'INVALID_JSON')
        return {'status': 'INVALID', 'reason': reason, 'error': message}


def _source_card(source, indexed_sources):
    text = source['text']
    url = 'https://example.org/synthetic/' + source['id']
    scope = {}
    # Include only literally present fields. Other metadata remains unaudited.
    for key, value in [('method', source['method']), ('method_version', source['version']),
                       ('scale', source.get('scope', {}).get('scale')),
                       ('probe', source.get('scope', {}).get('probe'))]:
        if isinstance(value, str) and value in text:
            scope[key] = value
    correction = []
    if source.get('superseded_by') in indexed_sources:
        replacement = indexed_sources[source['superseded_by']]
        correction = [{'url': 'https://example.org/synthetic/' + replacement['id'],
                       'version': replacement['version'], 'text': replacement['text'],
                       'sha256': fidelity.text_hash(replacement['text'])}]
    return {'schema_version': EVIDENCE_SCHEMA, 'id': source['id'],
            'identity': {'url': url, 'version': source['version'],
                         'publication_status': 'CORRECTED' if correction else 'CURRENT',
                         'correction_chain': correction},
            'source_document': {'url': url, 'version': source['version'],
                                'text': text, 'sha256': fidelity.text_hash(text)},
            'passages': [{'id': 'P', 'start': 0, 'end': len(text), 'quote': text,
                          'sha256': fidelity.text_hash(text)}],
            'applicability': scope,
            'scope_support': {k: _support(text, str(v)) for k, v in scope_leaves(scope).items()},
            'fixture_origin': 'SYNTHETIC_ENGINEERING_ONLY'}


def source_probe(data):
    sources = {s['id']: s for s in data['sources']}
    source = sources[data['source_id']]
    card = _source_card(source, sources)
    audits = validate_cards([card])
    identity_issues = []
    for field in ('method', 'version'):
        actual = source[field]
        proposed = data['claimed_source'][field]
        try:
            fidelity.audit_field(proposed, _support(source['text'], actual), source['text'])
        except ValueError as exc:
            identity_issues.append({'field': field, 'error': str(exc)})
    try:
        quote = data['quote']
        start = source['text'].find(quote)
        quote_audit = fidelity.validate_span(source['text'],
            {'start': start, 'end': start + len(quote), 'quote': quote})
        quote_status = 'PRESENT'
    except ValueError as exc:
        quote_audit, quote_status = {'error': str(exc)}, 'ABSENT'
    context = deepcopy(card['applicability'])
    if data.get('task_scope') is not None:
        for key in ('scale', 'probe'):
            if key in data['task_scope']:
                context[key] = data['task_scope'][key]
    if data.get('required_version') is not None:
        context['method_version'] = data['required_version']
    requirement = {'id': 'source-check', 'text': data['claim'], 'kind': 'SCIENTIFIC',
                   'necessary': True, 'evidence_ids': [card['id']], 'applicability': context,
                   'protocol_fields': []}
    check = {'source_id': card['id'], 'passage_ids': ['P'], 'claim': data['claim'],
             'relation': 'NOINFO', 'applicability': context, 'protocol_bindings': {}}
    record = {'status': 'SATISFIED', 'evidence_ids': [card['id']], 'evidence_checks': [check]}
    scientific = check_scientific_support(record, requirement, [card], data['protocol'])
    mismatch = 'SOURCE_OBJECT_VERSION_SIZE_OR_CONDITIONS_MISMATCH' in scientific['guards']
    result = {'source_identity': 'CONFLICT' if identity_issues else 'MATCHED',
              'quote_authenticity': quote_status, 'entailment': 'UNRESOLVED',
              'applicability': 'SCOPE_MISMATCH' if data.get('task_scope') and mismatch else 'UNRESOLVED',
              'identity_issues': identity_issues, 'source_audit': audits,
              'quote_audit': quote_audit, 'evidence_audit': scientific,
              'scientific_validation': 'PENDING_USER_EXPERT'}
    if data.get('required_version') is not None:
        result['version_status'] = ('SUPERSEDED' if mismatch and
                                    card['identity']['correction_chain'] else 'UNRESOLVED')
    return result


def requirements_probe(data):
    return adjudicate(deepcopy(data['judgment']), deepcopy(data['requirements']),
                      data['protocol'], deepcopy(data.get('cards', [])), data.get('formula'))


def pareto_probe(data):
    a, b = deepcopy(data['a']), deepcopy(data['b'])
    # Naming adaptation only; comparison is always the production comparator.
    for candidate in (a, b):
        for objective in candidate.get('objectives', {}).values():
            if 'basis' in objective:
                objective['measurement_basis'] = objective.pop('basis')
    return compare_candidates(a, b)


def _identity(bundle, context):
    judge = bundle.get('judge', {})
    visible = {k: deepcopy(v) for k, v in bundle.items() if k not in {'judge', 'evaluator_version'}}
    request = {'model': str(judge.get('family', 'FAKE')) + ':' + str(judge.get('version', 'v1')),
               'messages': [{'role': 'user', 'content': json.dumps(visible, ensure_ascii=False, sort_keys=True)}],
               'format': 'json', 'options': {'temperature': judge.get('temperature', 0)}}
    material = {'question': bundle.get('task'), 'requirements': bundle.get('requirements', []),
                'cards': bundle.get('sources', []), 'resource_list': {}}
    manifest = {'files': context.get('files', {}), 'provider': 'offline-fake',
                'model_digest': str(judge.get('version', 'v1')),
                'model_family': str(judge.get('family', 'FAKE'))}
    identity = execution_identity(request, material, bundle.get('protocol'), manifest, {'phase': 'judge'})
    identity['adapter_version'] = bundle.get('evaluator_version')
    return request, identity


def replay_probe(data, context):
    request, identity = _identity(data['payload'], context)
    if 'changed_payload' in data:
        changed_request, changed_identity = _identity(data['changed_payload'], context)
        return {'same_cache_key': digest(identity) == digest(changed_identity),
                'original_identity': identity, 'changed_identity': changed_identity,
                'scientific_validation': 'PENDING_USER_EXPERT', 'model_calls': 0}
    ledger, outputs, fake_calls = [], {}, 0
    for item in data['attempts']:
        origin = item['origin']
        record = {k: deepcopy(v) for k, v in item.items() if k not in {'status', 'raw'}}
        record.update(payload_sha256=digest(request),
                      visible_information_sha256=information_hash(request),
                      execution_origin='CACHE' if origin == 'CACHE' else 'MOCK',
                      response_cache_hit=origin == 'CACHE', invocation_id=item['attempt_id'])
        if origin == 'CACHE':
            cached = outputs.get(item.get('cached_from'))
            if cached is None:
                record.update(status='CACHE_MISS', error='No completed originating invocation')
            else:
                record.update(status='COMPLETE', parsed=deepcopy(cached))
        else:
            fake_calls += 1
            raw = item.get('raw', '{"status":"UNRESOLVED"}')
            record['raw_response'] = raw
            try:
                parsed = parse_judge_object(raw)
                record.update(status='COMPLETE', parsed=parsed)
                outputs[item['attempt_id']] = parsed
            except JudgeFormatError as exc:
                record.update(status='PARSE_FAILURE', error=str(exc))
        ledger.append(record)
    final_repeats = {}
    for record in ledger:
        final_repeats[record['repeat_id']] = record
    diagnostic = repeat_diagnostic(list(final_repeats.values()), data['planned_count'])
    return {'recorded_count': len(ledger), 'recorded_attempts': len(ledger),
            'independent_adapter_calls': fake_calls, 'cache_count': sum(r['response_cache_hit'] for r in ledger),
            'repeat_count': len(final_repeats), 'first_failure_retained': any(r['status'] != 'COMPLETE' for r in ledger),
            'technical_failures': sum(r['status'] != 'COMPLETE' for r in ledger),
            'ledger': ledger, 'repeat_diagnostic': diagnostic,
            'scientific_validation': 'PENDING_USER_EXPERT', 'model_calls': 0}


def compute(kind, data, context):
    """Only public input is accepted. This function never sees case.expected."""
    adapters = {'extraction_fidelity': extraction_probe, 'strict_json': json_probe,
                'source_layers': source_probe, 'requirements': requirements_probe, 'pareto': pareto_probe}
    if kind == 'replay':
        return replay_probe(data, context)
    if kind not in adapters:
        raise ValueError('Unsupported fixture adapter: ' + kind)
    return adapters[kind](deepcopy(data))
