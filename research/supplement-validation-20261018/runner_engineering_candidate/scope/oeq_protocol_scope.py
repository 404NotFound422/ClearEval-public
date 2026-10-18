"""Versioned protocol-design scope, with explicit frozen-output migration.

This layer never changes a model raw, creates a model result, or rejudges
science. A migrated proposal is a deterministic derivative, not a fresh raw.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

VERSION = 'protocol-design-only-v1-20261016'
CONTRACT_VERSION = 'source-parameter-contract-protocol-only-v1-20261016'
SCOPES = ('protocol-only-v1', 'historical-reference-v3')
EXCLUDED_REQUIREMENTS = frozenset({
    'idisco_solvent_quality_preparation', 'fdisco_peroxide_removal'})
HERE = Path(__file__).resolve().parent

PROMPT = '''
PROTOCOL DESIGN SCOPE protocol-design-only-v1-20261016 (takes precedence over all overlapping source, completeness, correctness and effectiveness instructions).
Evaluate only the requested concrete tissue-processing protocol: selected labeling where required, tissue operations, reagents and working-solution formulations/concentrations, operating pH/temperature/time, sequence, RI matching, and necessary storage/pre-imaging conditions.
Procurement grade, brand/catalog number, reagent manufacture, purification, and solvent-peroxide-removal production procedures are outside the default task. Missing such detail is not a C_param, C_step, Co_method, Co_param, Co_order, Co_chem, or effectiveness defect. Do not rename it an equivalent solvent-quality declaration, safety requirement, prerequisite, or scientific-validity concern to restore a hidden penalty. Source passages about those matters remain background, not task obligations. In particular, idisco_solvent_quality_preparation and fdisco_peroxide_removal must never return to the scored denominator or another metric.
Keep direct operating requirements: inappropriate tissue-exposure concentration, temperature, pH, duration, reagent compatibility, order and genuinely required working-solution ingredients remain evaluable. Neat/100% DBE means working-solution concentration, not supplier purity/grade. Use of freshly prepared working solution is a direct stated solution condition; no production procedure, numerical shelf life, quality test or procurement criterion is required. Do not delete every preparation dimension: named working-solution recipes, carriers and their stated concentrations remain in scope.
Report the exact protocol_scope_version and source_parameter_contract_version supplied in this request. Use only the versioned parameter_slots entries for C_param. Do not import historical judgments as if they were reviewed under this scope.
'''


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def load_contract(scope='protocol-only-v1'):
    if scope not in SCOPES:
        raise ValueError('UNKNOWN_PROTOCOL_TASK_SCOPE')
    name = ('source_parameter_contract_protocol_only.json' if scope == 'protocol-only-v1'
            else 'source_parameter_contract.json')
    return json.loads((HERE / name).read_text())


def _assert_contract_delta(contract):
    historical = load_contract('historical-reference-v3')
    old = {r['id']: r for r in historical['requirements']}
    new = {r['id']: r for r in contract['requirements']}
    if set(old) - set(new) != EXCLUDED_REQUIREMENTS or set(new) - set(old):
        raise ValueError('PROTOCOL_SCOPE_REQUIREMENT_SET_DRIFT')
    for rid, row in new.items():
        changed = {k for k in set(row) | set(old[rid]) if row.get(k) != old[rid].get(k)}
        allowed = ({'criterion', 'requirement_judgment'} if rid in {
            'fdisco_dbe_concentration', 'fdisco_fresh_preparation'} else set())
        if changed - allowed:
            raise ValueError('UNAPPROVED_PROTOCOL_SCOPE_REQUIREMENT_CHANGE: ' + rid)
    background = {r['id']: r for r in contract['background_only_requirements']}
    if background != {rid: old[rid] for rid in EXCLUDED_REQUIREMENTS}:
        raise ValueError('PROTOCOL_SCOPE_BACKGROUND_NOT_PRESERVED')
    if contract['version'] != CONTRACT_VERSION:
        raise ValueError('PROTOCOL_SCOPE_CONTRACT_VERSION_MISMATCH')


def prepare_payload(payload, consumer, scope='protocol-only-v1'):
    """Build a genuinely version-bound future request without model execution."""
    from oeq_source_parameter_slots import build_source_slots
    p = deepcopy(payload)
    if scope == 'historical-reference-v3':
        # Historical replay is intentionally exact, never silently upgraded.
        if build_source_slots(p, load_contract(scope)) != p['parameter_slots']:
            raise ValueError('HISTORICAL_PARAMETER_MANIFEST_MISMATCH')
        return p
    contract = load_contract(scope)
    _assert_contract_delta(contract)
    m = build_source_slots(p, contract)
    m.update(task_scope_version=VERSION, contract_version=CONTRACT_VERSION,
             task_scope='CONCRETE_PROTOCOL_DESIGN_ONLY',
             background_only_requirement_ids=sorted(EXCLUDED_REQUIREMENTS),
             weighting='Equal weight per retained explicit operating parameter; working-solution recipes retained. Procurement/manufacture/purification requirements excluded without replacement.')
    p.update(parameter_slots=m, protocol_scope_version=VERSION,
             source_parameter_contract_version=CONTRACT_VERSION,
             scoring_scope={'version': VERSION, 'excluded_requirement_ids': sorted(EXCLUDED_REQUIREMENTS),
                 'applies_to': ['completeness', 'correctness', 'effectiveness'],
                 'background_is_not_a_scoring_obligation': True,
                 'no_equivalent_quality_requirement': True})
    schema = consumer.extend_schema(p['score_output_schema'], m)
    for key, value in [('protocol_scope_version', VERSION),
                       ('source_parameter_contract_version', CONTRACT_VERSION)]:
        schema['properties'][key] = {'const': value}
        schema['required'].append(key)
    schema['required'] = list(dict.fromkeys(schema['required']))
    p['score_output_schema'] = schema
    return p


def repair_request(text, consumer, scope='protocol-only-v1'):
    head, body = text.split('\nSCORING_INPUT_JSON\n', 1)
    p = prepare_payload(json.loads(body), consumer, scope)
    return (head + (PROMPT if scope == 'protocol-only-v1' else '') +
            '\nSCORING_INPUT_JSON\n' + json.dumps(p, ensure_ascii=False, sort_keys=True,
                                                separators=(',', ':'))), p


def arithmetic(reviews, slots):
    states = [reviews[s['id']]['status'] for s in slots]
    present = states.count('PRESENT')
    unresolved = sum(s not in {'PRESENT', 'MISSING'} for s in states)
    n = len(states)
    key_complete = all(reviews[s['id']]['status'] == 'PRESENT' for s in slots
                       if s['dimension'] in {'medium', 'time_or_endpoint'})
    grade = (None if not n or unresolved else 3 if present / n >= .8
             else 2 if key_complete else 1 if present else 0)
    return {'present': present, 'denominator': n, 'unknown_or_contradicted': unresolved,
            'coverage': present / n if n else None, 'c_param': grade,
            'mechanical_status_count_only': True}


def replay_scoped_proposal(proposal, payload, consumer):
    """Scope-bound consumer for new caller-supplied responses; no old-raw fallback."""
    expected = prepare_payload(payload, consumer)
    if expected != payload:
        raise ValueError('SCOPE_BOUND_REQUEST_DOES_NOT_MATCH_CURRENT_CONTRACT')
    for key in ['protocol_scope_version', 'source_parameter_contract_version']:
        if proposal.get(key) != payload[key]:
            raise ValueError('UNVERSIONED_OR_OLD_RAW_NOT_A_NEW_SCOPE_RESPONSE: ' + key)
    result, audit = consumer.replay(proposal, payload)
    audit.update(protocol_scope_version=VERSION, source_parameter_contract_version=CONTRACT_VERSION,
                 semantic_certification=False, scientific_certified=False)
    return result, audit


def migrate_frozen(raw, payload, consumer, scope='protocol-only-v1'):
    """Validate old input, retain review states, and explicitly derive scope arithmetic.

    A rejected old review stays rejected. Correctness for routes with removed
    obligations is withheld until re-evaluation; raw verdicts remain untouched.
    """
    import jsonschema
    original_raw, original_payload = deepcopy(raw), deepcopy(payload)
    jsonschema.validate(raw, payload['score_output_schema'])
    historical = prepare_payload(payload, consumer, 'historical-reference-v3')
    old_slots = historical['parameter_slots']['slots']
    prepared = prepare_payload(payload, consumer, scope)
    new_slots = prepared['parameter_slots']['slots']
    retained = {s['id'] for s in new_slots}
    removed = [deepcopy(s) for s in old_slots if s['id'] not in retained]
    if any(not {r['id'] for r in s['source_requirements']} <= EXCLUDED_REQUIREMENTS for s in removed):
        raise ValueError('UNAPPROVED_SLOT_REMOVAL')
    before = arithmetic(raw['parameter_slot_review'], old_slots)
    after = arithmetic(raw['parameter_slot_review'], new_slots)
    result = {'migration_version': VERSION, 'scope': scope,
              'input_raw_sha256': digest(raw), 'input_payload_sha256': digest(payload),
              'before': before, 'after': after, 'removed_slots': removed,
              'retained_parameter_slot_review': {sid: deepcopy(r) for sid, r in raw['parameter_slot_review'].items() if sid in retained},
              'archived_correctness': deepcopy(raw['scores']['correctness']),
              'archived_correctness_attribution': deepcopy(raw['correctness_attribution']),
              'historical_consumer_accepted': False, 'consumer_accepted': False,
              'derived_scores': None, 'replay_audit': None,
              'correctness_scope_status': ('NOT_REEVALUATED_UNDER_PROTOCOL_ONLY_SCOPE' if removed else 'HISTORICAL_JUDGMENT_RETAINED_NOT_NEW_REEVALUATION'),
              'scientific_certified': False, 'semantic_certified': False,
              'official_scores': None, 'IA': None,
              'is_fresh_model_attempt': False, 'model_calls': 0, 'encoder_calls': 0,
              'new_extraction_calls': 0, 'frozen_raw_unchanged': True,
              'interpretation': 'DETERMINISTIC_SCOPE_DERIVATIVE_OF_FROZEN_REVIEWS_NOT_NEW_MODEL_OUTPUT'}
    try:
        old_adopted, _ = consumer.replay(raw, payload)
        for group, key in [('completeness', 'c_param'), ('correctness', 'co_method'), ('correctness', 'co_param')]:
            if old_adopted['scores'][group][key]['score'] != raw['scores'][group][key]['score']:
                raise ValueError('HISTORICAL_RAW_REPLAY_GRADE_CONTRADICTION: ' + key)
        result['historical_consumer_accepted'] = True
    except Exception as exc:
        result['historical_consumer_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        result['consumer_failure'] = {'type': 'HistoricalReviewRejected',
                                     'message': 'Scope removal does not cure or bypass historical evidence-validation failure.'}
    else:
        derived = deepcopy(raw)
        derived['parameter_slot_review'] = deepcopy(result['retained_parameter_slot_review'])
        if scope == 'protocol-only-v1':
            derived['protocol_scope_version'] = VERSION
            derived['source_parameter_contract_version'] = CONTRACT_VERSION
        adopted, audit = consumer.replay(derived, prepared)
        if adopted['scores']['completeness']['c_param']['score'] != after['c_param']:
            raise ValueError('SCOPE_ARITHMETIC_CONSUMER_MISMATCH')
        if removed:
            # Never turn old Co judgments into new-scope scientific judgments.
            for key in adopted['scores']['correctness']:
                adopted['scores']['correctness'][key] = {
                    'score': None, 'reasoning': 'Historical judgment has not been re-evaluated under protocol-design-only scope.',
                    'evidence_basis': 'HISTORICAL_RAW_PRESERVED_SEPARATELY',
                    'missing_reason': 'NOT_REEVALUATED_UNDER_PROTOCOL_ONLY_SCOPE'}
        result.update(consumer_accepted=True, derived_scores=adopted['scores'], replay_audit=audit)
    if raw != original_raw or payload != original_payload:
        raise AssertionError('FROZEN_INPUT_MUTATED')
    return result, prepared
