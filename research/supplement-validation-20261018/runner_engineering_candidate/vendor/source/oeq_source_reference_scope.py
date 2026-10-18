"""Admission only: reviewed complete single-route references, not scientific scoring.

Reuse existing providers and their locks. No question whitelist, corpus hash registry,
new reference derivation, candidate-dependent selection, or partial denominator.
"""
import json


class UnsupportedReferenceScope(ValueError):
    """Caller must bind a supported reference; this is not a candidate score."""
    status = 'UNSUPPORTED_REFERENCE_SCOPE'


def _reject(reason):
    raise UnsupportedReferenceScope('UNSUPPORTED_REFERENCE_SCOPE: ' + reason)


def _provider(key):
    if key == 'idisco-dec2016-atomic-clearing-v3':
        from oeq_atomic_source_projection import HOME
        from oeq_atomic_alignment import source_reference
        reference = source_reference()  # Existing locked provider; wash4 only.
        rows = [r for r in reference['operations']
                if r['comparison_phase'] in {'clearing', 'ri_matching_storage'}]
        cards = json.loads((HOME / 'requested_clearing_projection_v1.json').read_text())['cards']
        return 'iDISCO+', 'requested_clearing', rows, cards
    if key == 'macs-original2020-serial-three-v1':
        from oeq_macs_atomic_reference import source_reference, _template
        return ('MACS', 'Literal source operations with source-bound conditional execution excluded; candidate wording retained',
                source_reference()['operations'], _template()[0]['cards'])
    if key in {'fdisco2019-atomic-clearing-thf100x2-v3',
               'fdisco2019-atomic-clearing-thf100x3-v3'}:
        from oeq_fdisco_atomic_reference import source_reference, _template
        return 'FDISCO', 'requested_clearing', source_reference(key)['operations'], _template()[0]['cards']
    _reject('unreviewed provider; bind a supported complete reference')


def validate_reference_scope(payload):
    """Fail before slot creation. Existing scope/key declare intent, never prove it.

    Completeness is established by ordered equality to the existing provider's
    selected operations, including phase, context, occurrences and provenance.
    Unknown annotations fail closed rather than being interpreted heuristically.
    Source-card applicability metadata and candidate operations are not examined.
    """
    pair = payload.get('paired_representation', {})
    key = payload.get('reference_id')
    if not isinstance(key, str):
        _reject('one explicit provider key is required')
    route = payload.get('route_id')
    if not isinstance(route, str) or not route.strip():
        _reject('one explicit route_id is required')
    if pair.get('consumer_version') != key:
        _reject('reference_id and consumer provider differ')
    try:
        method, scope, expected, cards = _provider(key)
    except UnsupportedReferenceScope:
        raise
    except (ValueError, OSError, KeyError, ImportError) as exc:
        _reject('provider cannot verify its reference: ' + str(exc))
    if pair.get('method', method) != method or pair.get('scope') != scope:
        _reject('method/scope differs from supported provider scope')
    reference = pair.get('reference', {})
    if reference.get('unresolved_scope_operations'):
        _reject('reference contains unresolved scope operations')
    # New route/context declarations cannot silently override provider semantics.
    for obj in (payload, pair, reference):
        if 'route_id' in obj and obj['route_id'] != route:
            _reject('conflicting route identity')
        if 'routes' in obj or 'execution_context' in obj or 'source_context' in obj:
            _reject('unreviewed route/context declaration requires binding')
        if 'route_count' in obj and obj['route_count'] != 1:
            _reject('multiple routes unsupported')
        if 'method' in obj and obj['method'] != method:
            _reject('conflicting method declaration')
        if 'reference_scope' in obj and obj['reference_scope'] != 'REVIEWED_COMPLETE_REFERENCE':
            _reject('only REVIEWED_COMPLETE_REFERENCE is supported')
    if 'scope' in reference and not (method == 'MACS' and reference['scope'] ==
            'Three sequential original reagent treatments; no invented times/storage or scientific necessity'):
        _reject('unreviewed reference scope declaration')
    if 'reference_id' in reference and reference['reference_id'] != key:
        _reject('conflicting reference provider')
    rows = reference.get('operations')
    if not isinstance(rows, list) or len(rows) != len(expected):
        _reject('incomplete or expanded reference; fragments/multiple routes unsupported')
    checked = []
    for row in rows:
        if not isinstance(row, dict):
            _reject('malformed reference operation')
        # Legacy providers emit branch=main even for a renamed selected task route.
        if row.get('route_id', route) != route:
            _reject('multiple or conflicting operation routes')
        checked.append({k: v for k, v in row.items() if k != 'route_id'})
    if checked != expected:
        _reject('operations/context/provenance differ from complete provider reference')
    supplied = payload.get('provided_sources', [])
    if not isinstance(supplied, list) or any(not isinstance(c, dict) for c in supplied):
        _reject('malformed source cards')
    fields = ('id', 'identity', 'source_document', 'passages')
    project = lambda values: [{k: c.get(k) for k in fields} for c in values]
    if project(supplied) != project(cards):
        _reject('source documents/passages differ from reviewed provider provenance')
    return {'status': 'SUPPORTED_REFERENCE_SCOPE', 'provider': key, 'method': method,
            'route_id': route, 'reference_scope': 'REVIEWED_COMPLETE_REFERENCE',
            'operation_count': len(rows), 'scientific_certified': False}
