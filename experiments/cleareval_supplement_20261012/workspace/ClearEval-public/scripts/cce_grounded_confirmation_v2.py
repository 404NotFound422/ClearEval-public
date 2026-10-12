"""Prospective primary confirmation controller: eight sealed answers, two judges.

Only ``draft`` and synthetic checks are presently authorized.  Every real-source
read is behind an externally authored root release and the pre-unsealing rule
freeze.  No command creates its own selection, release or integration approval.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import cce_output_contract_v1 as parent
import cce_method_family_steps_v1 as family
import cce_confirmation_reference_design_v1 as projection
import cce_grounded_offline_scoring_v1 as numeric
import evaluator_integrity as integrity

BASE = ROOT / 'artifacts/cce_validation/optimizer_20261010'
DESIGN = BASE / 'confirmation_design_v2'
OUT = BASE / 'grounded_confirmation_v2'
RUN = OUT / 'run'
RELEASE = DESIGN / 'final_release.json'
LEDGER = parent.LEDGER
BUDGET_ALLOCATION = BASE/'grounded_v6_design_v1/budget_allocation_amendment.json'
PRIMARY_PHASE_CEILING = 289
ALLOCATED_COMBINED_CEILING = 297
GLOBAL_CEILING = 300
VERSION = 'grounded_confirmation_v2'
PROJECTION = 'complete_scientific_json_with_lossless_provenance_sidecar'
REFERENCE_REVISION = projection.OUT / 'revision_02'
IDS = [f'C{i:02d}' for i in range(1, 9)]
SAFE_KEYS = {'anonymous_answer_id', 'question_id', 'specific_question', 'model_response', 'references'}
SOURCE_KEYS = {'confirmation_id', 'question_id', 'specific_question', 'model_response',
               'question_sha256', 'answer_sha256', 'source_kind', 'expert_confirmation', 'formal_eligible'}
ASSETS = {'budget_allocation_amendment', 'converter', 'schema', 'development_backend', 'development_plan', 'development_completion',
    'development_fact_summary', 'development_fact_verification', 'fact_checker', 'fact_checker_freeze',
    'final_configuration', 'model_config', 'model_contract', 'development_contract', 'reference_policy', 'reference_catalog',
    'reference_projection', 'reference_integrity_amendment', 'projection_script', 'method_family_policy', 'step_core', 'step_scorer',
    'encoder_manifest', 'numeric_adapter', 'blind_packet_policy_freeze',
    'E2_completion', 'E2_per_answer', 'E2_matrix', 'E2_verification', 'E2_contract',
    'E4_completion', 'E4_observations', 'E4_matrix', 'E4_verification', 'E4_contract'}
require = parent.require
bind = parent.bind
rawsha = projection.rawsha


def verify(binding):
    path = Path(binding['path']).resolve()
    require(j.filehash(path) == binding['sha256'], 'BINDING_DRIFT:' + str(path))
    return path


def forbidden_metadata_path(path):
    text = str(path).lower().replace('\\', '/')
    return any(x in text for x in ['sealed_confirmation', 'confirmation_manifest', 'identity_key', '/human_review/'])


def save_once(path, value):
    path = Path(path)
    if path.exists():
        require(j.read(path) == value, 'IMMUTABLE_FILE_DIFFERS:' + str(path))
    else:
        j.save(path, value)


def record(action, **details):
    path = OUT / 'actual_commands.json'
    rows = j.read(path) if path.exists() else []
    rows.append({'utc': j.now(), 'action': action, 'actual_argv': [sys.executable, *sys.argv],
                 'cwd': str(Path.cwd()), 'script_sha256': j.filehash(__file__), **details})
    j.save(path, rows)


def import_bound(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def terminal_binding_shape(binding):
    return (isinstance(binding, dict) and isinstance(binding.get('path'), str) and bool(binding['path'])
            and isinstance(binding.get('sha256'), str) and len(binding['sha256']) == 64
            and all(char in '0123456789abcdef' for char in binding['sha256'].lower()))


def verify_nested_terminal_bindings(value, label):
    """Verify concrete embedded metadata bindings, without opening sealed data.

    These hashes cover files exported by the stage analyzer. This does not
    re-execute the experiment, certify its science, or recursively interpret
    arbitrary JSON files referenced by those bindings.
    """
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            require(terminal_binding_shape(value), 'TERMINAL_BINDING_SHAPE:' + label)
            require(not forbidden_metadata_path(value['path']), 'PROTECTED_NESTED_METADATA:' + label)
            verify(value)
        for key, child in value.items():
            verify_nested_terminal_bindings(child, label + '.' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            verify_nested_terminal_bindings(child, label + '[' + str(index) + ']')


def verify_terminal_metadata(paths):
    dev = j.read(paths['development_completion'])
    require(dev.get('actual_observations') == 5 and dev.get('planned_observations') == 5,
            'ACTUAL_FIVE_DEVELOPMENT_REQUIRED')
    facts = j.read(paths['development_fact_summary'])
    require(facts.get('status') == 'complete' and facts.get('fixed_answers') == 5,
            'ALL_FIVE_FACT_REVIEW_REQUIRED_NOT_SUCCESS_SELECTION')
    factcheck = j.read(paths['development_fact_verification'])
    require(str(factcheck.get('status', '')).startswith('pass'), 'FACT_REVIEW_VERIFICATION_REQUIRED')
    development_contract = j.read(paths['development_contract'])
    e4_contract = j.read(paths['E4_contract'])
    require(e4_contract == j.read(paths['model_contract']), 'PRIMARY_MODELS_MUST_BE_FROZEN_E4_MODELS')
    primary = development_contract['models']
    require(len(primary) == 1 and primary[0] in e4_contract['models'], 'DEVELOPMENT_PRIMARY_MODEL_DIFFERENT')
    for contract_path in ['development_contract', 'E2_contract', 'E4_contract']:
        contract = j.read(paths[contract_path]); variant = contract['source_bound_variant']
        require(variant.get('grounded_script_sha256') == j.filehash(paths['converter']) and
                variant.get('schema_sha256') == j.filehash(paths['schema']), 'STAGES_MUST_SHARE_FINAL_CONVERTER_AND_SCHEMA')
        require_scientific_contract(contract, development_contract)
    require(j.read(paths['E2_contract'])['models'] == primary, 'E2_PRIMARY_MODEL_DIFFERENT')
    for stage, count, rows_key, matrix_key, verification_key in [
        ('E2', 21, 'E2_per_answer', 'E2_matrix', 'E2_verification'),
        ('E4', 30, 'E4_observations', 'E4_matrix', 'E4_verification')]:
        summary = j.read(paths[stage + '_completion'])
        rows, matrix, check = j.read(paths[rows_key]), j.read(paths[matrix_key]), j.read(paths[verification_key])
        actual_key = 'bound_actual_artifacts' if stage == 'E2' else 'frozen_actual_files'
        actual_bindings = summary.get(actual_key)
        require(isinstance(actual_bindings, list) and bool(actual_bindings)
                and all(terminal_binding_shape(item) for item in actual_bindings),
                'TERMINAL_ACTUAL_BINDINGS_REQUIRED:' + stage)
        if stage == 'E2':
            require(terminal_binding_shape(check.get('original_step_source')), 'TERMINAL_STEP_BINDING_REQUIRED:E2')
        else:
            frozen = check.get('frozen_inputs')
            require(isinstance(frozen, list) and bool(frozen) and all(terminal_binding_shape(item) for item in frozen),
                    'TERMINAL_FROZEN_BINDINGS_REQUIRED:E4')
        verify_nested_terminal_bindings(summary, stage + '.completion')
        verify_nested_terminal_bindings(check, stage + '.verification')
        require(len(rows) == len(matrix) == count and check.get('status') == 'pass', stage + '_NOT_COMPLETE')
        require(all(r['status'] in ['success', 'failed'] for r in rows), stage + '_NONTERMINAL_ROW')
        require({r['trial_id'] for r in rows} == {r['planned_trial_id'] for r in matrix}, stage + '_MATRIX_MISMATCH')
        if stage == 'E2':
            require(summary.get('actual_terminal_answers') == 21 and summary.get('planned_pairs') == 15
                    and check.get('all_21_answers_and_15_pairs_retained') is True, 'E2_DENOMINATORS')
        else:
            require(summary.get('actual_observations') == 30 and check.get('all_30_terminal_cells_retained') is True,
                    'E4_DENOMINATORS')



def verify_budget_allocation(path):
    path=Path(path).resolve()
    require(path==BUDGET_ALLOCATION.resolve(),'V6_BUDGET_ALLOCATION_PATH_MISMATCH')
    value=j.read(path)
    expected={'starting_requests':222,'global_limit':300,'original_development_total':25,
        'previous_development_total':30,'development_total':35,'v6_new_requests':5,
        'E2_new_requests':21,'E4_new_requests':25,'primary_confirmation_new_requests':16,
        'blind_subagent_assessments':8,'blind_answers':8,'blind_replicates_per_answer':1,
        'required_exact_reuse':5,'after_E2_reserve':49,'after_E4_reserve':24,
        'max_attempts':1,'max_total_if_all_phases_run':297,'unallocated_calls':3}
    require(value.get('status')=='approved_before_v6_generation' and value.get('selected_by')=='root_agent'
        and bool(value.get('created_utc')),'PROSPECTIVE_V6_BUDGET_APPROVAL_REQUIRED')
    require(all(type(value.get(k)) is int and value[k]==v for k,v in expected.items()),'V6_ALLOCATION_SCOPE_CHANGED')
    require(value.get('fresh30_fallback_allowed') is False and value.get('unallocated_calls_authorize_retries') is False
        and value.get('technical_scientific_acceptance_unchanged') is True
        and bool(value.get('original_G01_development_clause_deviation'))
        and bool(value.get('optional_blind_design_deviation')),'V6_ALLOCATION_DEVIATION_OR_STOP_POLICY_MISSING')
    for item in [*[value[k] for k in ['original_budget','original_acceptance','previous_allocation']],
                 *value['completed_v5_evidence']]:
        require(not forbidden_metadata_path(item['path']),'PROTECTED_PATH_IN_BUDGET_BINDING')
        verify(item)
    return value

def release_gate():
    """Do not hash, open, glob or parse the sealed source files in this gate."""
    require(RELEASE.exists(), 'ROOT_FINAL_RELEASE_MISSING')
    release = j.read(RELEASE)
    require(release.get('status') == 'released_for_primary_confirmation' and release.get('selected_by') == 'root_agent',
            'ROOT_FINAL_RELEASE_REQUIRED')
    require(release.get('configuration_frozen_before_confirmation') is True and
            release.get('no_post_confirmation_tuning') is True, 'FINAL_CONFIG_NOT_CLOSED')
    assets = release['assets']
    require(ASSETS <= set(assets), 'REQUIRED_RELEASE_ASSETS_MISSING')
    require(not any(forbidden_metadata_path(b['path']) for b in assets.values()), 'SEALED_PATH_IN_METADATA_ASSETS')
    paths = {k: verify(b) for k, b in assets.items()}
    verify_budget_allocation(paths['budget_allocation_amendment'])
    require(paths['projection_script'] == Path(projection.__file__).resolve() and
            paths['step_scorer'] == Path(family.__file__).resolve() and
            paths['step_core'] == Path(family.core.__file__).resolve() and
            paths['numeric_adapter'] == Path(numeric.__file__).resolve(), 'CODE_IMPORT_RELEASE_MISMATCH')
    require(paths['reference_projection'] == (REFERENCE_REVISION/'projected_all_references.json').resolve()
            and paths['reference_integrity_amendment'] == (REFERENCE_REVISION/'integrity_amendment.json').resolve(),
            'VERSIONED_REFERENCE_REVISION_AND_INTEGRITY_AMENDMENT_REQUIRED')
    final = j.read(paths['final_configuration'])
    require(final.get('status') == 'frozen_before_confirmation' and final.get('num_ctx') == 98304,
            'PROSPECTIVE_SHARED_98304_CONFIGURATION_REQUIRED')
    bound = {str(Path(x['path']).resolve()): x['sha256'] for x in final['bindings']}
    for item in final['bindings']:
        require(not forbidden_metadata_path(item['path']), 'SEALED_INPUT_IN_FINAL_CONFIG'); verify(item)
    for key in ['budget_allocation_amendment', 'converter', 'schema', 'development_backend', 'fact_checker', 'fact_checker_freeze',
                'model_config', 'model_contract', 'development_contract', 'reference_catalog', 'reference_projection',
                'reference_integrity_amendment', 'projection_script',
                'method_family_policy', 'step_core', 'step_scorer', 'encoder_manifest', 'numeric_adapter']:
        require(bound.get(str(paths[key])) == assets[key]['sha256'], 'FINAL_CONFIG_BINDING_MISSING:' + key)
    policy = j.read(paths['reference_policy'])
    require(policy.get('status') == 'frozen_before_confirmation' and policy.get('prompt_projection') == PROJECTION
            and policy.get('projection_roundtrip_exact') is True and policy.get('shared_value_encoding') is False,
            'COMPLETE_SCIENTIFIC_POOL_POLICY_REQUIRED')
    require(policy.get('primary_threshold') == .7 and policy.get('encoder') == 'all-mpnet-base-v2'
            and policy.get('selection') == family.policy()['selection'], 'ORIGINAL_STEP_SELECTION_CHANGED')
    for key in ['reference_catalog', 'reference_projection', 'reference_integrity_amendment', 'projection_script', 'method_family_policy', 'step_core', 'step_scorer']:
        require(policy.get(key) == assets[key], 'REFERENCE_POLICY_BINDING_MISSING:' + key)
    require(j.read(paths['method_family_policy']) == family.policy(), 'METHOD_FAMILY_POLICY_DRIFT')
    freeze = j.read(paths['blind_packet_policy_freeze'])
    require(freeze.get('status') == 'frozen_before_primary_unsealing' and freeze.get('frozen_by') == 'root_agent',
            'BLIND_PACKET_RULES_MUST_PRECEDE_UNSEALING')
    freeze_bound = {str(Path(x['path']).resolve()): x['sha256'] for x in freeze['bindings']}
    for item in freeze['bindings']:
        require(not forbidden_metadata_path(item['path']), 'SEALED_PATH_IN_PACKET_RULES'); verify(item)
    for key in ['budget_allocation_amendment', 'converter', 'schema', 'reference_policy']:
        require(freeze_bound.get(str(paths[key])) == assets[key]['sha256'], 'BLIND_SCIENCE_NOT_PREBOUND:' + key)
    require(bound.get(str(Path(__file__).resolve())) == j.filehash(__file__), 'PRIMARY_CODE_NOT_PREBOUND')
    verify_terminal_metadata(paths)
    inputs = release.get('confirmation_inputs', [])
    require(len(inputs) == 8 and [x.get('anonymous_answer_id') for x in inputs] == IDS, 'FIXED_EIGHT_RELEASE_IDENTITIES')
    require(len({str(Path(x['path']).resolve()) for x in inputs}) == 8, 'DUPLICATE_RELEASE_SOURCE_PATH')
    for item in inputs:
        path = Path(item['path'])
        require('sealed_confirmation' in str(path).lower() and path.name == item['anonymous_answer_id'] + '.json',
                'RELEASE_SOURCE_MUST_BE_ONE_EXPLICIT_CXX_FILE')
        require(isinstance(item.get('sha256'), str) and len(item['sha256']) == 64, 'SEALED_EXPECTED_HASH_REQUIRED')
    return release, paths


def load_backend(paths):
    backend = import_bound(paths['development_backend'], 'confirmation_selected_development_backend')
    ground = backend.grounded
    require(j.filehash(ground.__file__) == j.filehash(paths['converter']), 'BACKEND_CONVERTER_DIFFERS')
    require(ground.schema() == j.read(paths['schema']), 'CONVERTER_SCHEMA_DIFFERS')
    return backend


def projected_catalog(paths):
    refs = j.read(paths['reference_catalog'])['references']
    expected = j.read(paths['reference_projection'])
    require(isinstance(expected, list) and len(refs) == len(expected) == 11, 'FROZEN_ELEVEN_REFERENCE_CATALOG')
    actual = []
    for ref in refs:
        value, sidecar = projection.project_reference(ref)
        require(projection.restore_reference(value, sidecar) == ref, 'REFERENCE_LOSSLESS_ROUNDTRIP')
        actual.append(value)
    require(actual == expected, 'FROZEN_SCIENTIFIC_PROJECTION_DIFFERS')
    policy = j.read(paths['reference_policy'])
    require(policy.get('prompt_reference_allowed_fields') == sorted({k for r in expected for k in r}),
            'VALIDATION_KEY_UNION_DIFFERS_NO_FIELDS_MAY_BE_DROPPED')
    require(len({x['reference_id'] for x in refs}) == 11, 'REFERENCE_ID_COLLISION')
    return refs, {x['reference_id']: x for x in expected}


def clean_source(item, value):
    require(set(value) == SOURCE_KEYS, 'SOURCE_SCHEMA_NOT_EXACT_PUBLIC_CONSTRUCTION_SCHEMA')
    require(value['confirmation_id'] == item['anonymous_answer_id'] and value['confirmation_id'] in IDS, 'SOURCE_ID_MISMATCH')
    require(type(value['question_id']) is int and value['question_id'] in family.QIDS, 'QUESTION_OUTSIDE_EXPOSED_QIDS')
    require(value['source_kind'] == 'archived_generated_answer' and value['formal_eligible'] is False
            and value['expert_confirmation'] is None, 'SOURCE_PROVENANCE_MISMATCH')
    require(all(isinstance(value[k], str) and value[k].strip() for k in ['specific_question', 'model_response']), 'EMPTY_SOURCE_TEXT')
    require(rawsha(value['specific_question']) == value['question_sha256'] and rawsha(value['model_response']) == value['answer_sha256'],
            'RAW_UTF8_SOURCE_HASH_MISMATCH')
    aid = item['anonymous_answer_id']
    return {'anonymous_answer_id': aid, 'case_id': aid, 'question_id': value['question_id'],
            'specific_question': value['specific_question'], 'model_response': value['model_response'],
            'question_sha256': value['question_sha256'], 'answer_sha256': value['answer_sha256']}


def pool_for(case, refs, byid):
    method, declared, version, pool = family.resolve(case, refs)
    return [copy.deepcopy(byid[r['reference_id']]) for r in pool], {
        'comparison_method_id': method, 'declared_route_text': declared, 'version_selection': version,
        'candidate_reference_ids': [r['reference_id'] for r in pool], 'candidate_count': len(pool),
        'scientific_task_applicability_confirmed': False, 'formal_eligible': False}


def context_check(prompt, public):
    bound = len(prompt.encode('utf8')) + public['max_output_tokens'] + 256
    return {'prompt_utf8_bytes': len(prompt.encode('utf8')), 'conservative_context_bound': bound,
        'configured_num_ctx': public['num_ctx'], 'max_output_tokens': public['max_output_tokens'],
        'fits': bound <= public['num_ctx'], 'truncation_permitted': False}


def public_models(paths):
    models = j.read(paths['model_contract'])['models']
    require(len(models) == 2 and len({m['name'] for m in models}) == 2, 'TWO_FROZEN_MODELS_REQUIRED')
    final = j.read(paths['final_configuration'])
    families = final.get('verified_model_families', {})
    require(set(families) == {m['name'] for m in models} and len(set(families.values())) == 2,
            'TWO_VERIFIED_LOCAL_FAMILIES_REQUIRED_NOT_ALIAS_INFERENCE')
    for model in models:
        settings = model['settings']
        require(settings['transport_kind'] == 'ollama_loopback' and settings['num_ctx'] == final['num_ctx'] == 98304
            and settings['max_output_tokens'] == 8192 and settings['temperature'] == 0
            and settings['timeout_seconds'] == 600
            and (settings['enable_thinking'] is False or settings['enable_thinking'] is None), 'FROZEN_GENERATION_SETTINGS')
        # Preserve the exact frozen transport value. False explicitly disables
        # thinking; None leaves the original request option unspecified. These
        # are not interchangeable, and bool-like 0/strings must not pass.
        require(settings['format'] == j.read(paths['schema']), 'MODEL_DECODER_SCHEMA_DIFFERS')
    return models


def arguments(paths, allow=False):
    return SimpleNamespace(out=RUN, cases=OUT/'cases.json', model_config=paths['model_config'],
        models=[m['name'] for m in public_models(paths)], question_file=j.HIST,
        demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json', demand_manifest=None,
        # A future allowance is not an actual past external request. Lower only
        # this phase's ceiling so the original ledger index stays actual used+1.
        ledger=LEDGER, total_budget=PRIMARY_PHASE_CEILING, external_request_count=0, max_calls=16, max_attempts=1,
        repeats=1, temperature=0., max_output_tokens=8192, timeout_seconds=600, allow_api=allow)


def request_count():
    return sum(r.get('event') == 'request_started' for r in j.ledger_rows(LEDGER))


def budget_guard(start, own, remaining):
    require(request_count() == start + own, 'UNPLANNED_PARALLEL_REQUESTS')
    require(start + own + remaining <= PRIMARY_PHASE_CEILING, 'PRIMARY_ALLOCATED_PHASE_CEILING')
    require(start + own + remaining + 8 <= ALLOCATED_COMBINED_CEILING, 'ALLOCATED_PRIMARY_PLUS_BLIND_CEILING')
    require(start + own + remaining + 8 <= GLOBAL_CEILING, 'COMBINED_PRIMARY_PLUS_RESERVED_BLIND_BUDGET')


class LocalEncoder(family.core.Encoder):
    """Unchanged core score/encoder; new writes stay in this batch's cache."""
    def __init__(self):
        original = family.core.OUT
        family.core.OUT = OUT
        try:
            super().__init__()
        finally:
            family.core.OUT = original
        self.memo, self.used, self.new = {}, [], []
        self.roots = [*family.CACHES, family.DEST/'embedding_cache', self.cache]

    def encode(self, texts):
        result = []
        for text in texts:
            key = family.core.digest([self.identity, text]) + '.npy'
            if key not in self.memo:
                found = [p/key for p in self.roots if (p/key).exists()]
                if found:
                    path = found[0]
                    require(all(j.filehash(p) == j.filehash(path) for p in found), 'CONFLICTING_CACHED_VECTOR')
                    vector = self.np.load(path, allow_pickle=False); origin = 'reused'
                else:
                    path = self.cache/key
                    vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                    self.np.save(path, vector); self.new.append(str(path)); origin = 'new_local_vector'
                require(vector.shape == (768,) and self.np.isfinite(vector).all(), 'INVALID_LOCAL_VECTOR')
                self.memo[key] = vector
                self.used.append({**bind(path), 'text_sha256': rawsha(text), 'origin': origin})
            result.append(self.memo[key])
        return self.np.asarray(result)


def deterministic_steps(cases, refs, ground, paths):
    manifest = j.read(paths['encoder_manifest'])
    require(manifest.get('encoder') == 'all-mpnet-base-v2' and manifest.get('bindings'), 'ENCODER_ASSET_MANIFEST_REQUIRED')
    actual_assets = {str(p.resolve()) for p in (family.core.ASSETS/'assets/all-mpnet-base-v2').rglob('*') if p.is_file()}
    require({str(Path(x['path']).resolve()) for x in manifest['bindings']} == actual_assets,
            'ENCODER_MANIFEST_MUST_COVER_EVERY_LOCAL_ASSET')
    for item in manifest['bindings']: verify(item)
    encoder = None; encoder_error = None; results = []; exports = []
    for case in cases:
        try:
            if encoder is None and encoder_error is None:
                try: encoder = LocalEncoder()
                except Exception as exc: encoder_error = type(exc).__name__ + ':' + str(exc)
            require(encoder is not None, 'LOCAL_ENCODER_UNAVAILABLE:' + str(encoder_error))
            result = family.score(case, refs, encoder, .7)
        except Exception as exc:
            result = {'sr': None, 'sp': None, 'reference_id': None, 'all_candidates': [],
                'missing_reason': 'local_step_failure:' + type(exc).__name__ + ':' + str(exc)}
        result = {'anonymous_answer_id': case['anonymous_answer_id'], **result}
        require(result['sr'] is None and result['sp'] is None or all(numeric.finite(result[k]) and 0 <= result[k] <= 1 for k in ['sr', 'sp']), 'STEP_OUTPUT_RANGE')
        results.append(result)
        exports.append({'anonymous_answer_id': case['anonymous_answer_id'], 'source_id': ground.source_id_for_case(case),
            'answer_sha256': rawsha(case['model_response']), 'question_sha256': rawsha(case['specific_question']),
            'references_sha256': j.digest(case['references']), 'sr': result['sr'], 'sp': result['sp'],
            'selected_reference_id': result.get('reference_id'), 'method_family_policy_sha256': j.filehash(paths['method_family_policy']),
            'all_candidate_results': result.get('all_candidates', []), 'missing_reason': result.get('missing_reason'),
            'source': 'deterministic_original_step_scoring', 'formal_eligible': False})
    j.save(OUT/'full_step_results.json', results); j.save(OUT/'deterministic_steps.json', exports)
    usage = {'new_embeddings': len(encoder.new) if encoder else 0,
        'reused_embeddings': sum(x['origin'] == 'reused' for x in encoder.used) if encoder else 0,
        'used': encoder.used if encoder else [], 'encoder_failure': encoder_error, 'new_model_requests': 0}
    j.save(OUT/'embedding_usage.json', usage)
    j.save(OUT/'step_verification.json', {'status': 'pass', 'original_SR_SP': True, 'primary_threshold': .7,
        'encoder': 'all-mpnet-base-v2', 'fixed_answer_denominator': 8,
        'numeric_steps': sum(numeric.finite(r['sr']) for r in exports), 'unknown_not_imputed': True,
        'conditional_coverage_not_task_applicability': True,
        'bindings': [bind(paths[k]) for k in ['step_core', 'step_scorer', 'reference_catalog', 'method_family_policy',
            'reference_policy', 'reference_projection', 'encoder_manifest']] +
            [bind(OUT/n) for n in ['cases.json', 'full_step_results.json', 'deterministic_steps.json', 'embedding_usage.json']],
        'new_model_requests': 0, 'new_embeddings': usage['new_embeddings'], 'reused_embeddings': usage['reused_embeddings']})


def prepare():
    release, paths = release_gate()
    require(not (OUT/'prepared_inputs.json').exists(), 'ALREADY_PREPARED_VALIDATE_EXISTING_NO_REUNSEAL')
    before = request_count(); budget_guard(before, 0, 16)
    backend = load_backend(paths); models = public_models(paths); refs, byid = projected_catalog(paths)
    plan = {'status': 'frozen_before_primary_unsealing', 'version': VERSION, 'created_utc': j.now(),
        'final_release': bind(RELEASE), 'reference_policy': bind(paths['reference_policy']),
        'final_configuration': bind(paths['final_configuration']), 'blind_packet_policy_freeze': bind(paths['blind_packet_policy_freeze']),
        'frozen_inputs': [bind(__file__), *release['assets'].values()], 'expected_sealed_inputs': release['confirmation_inputs'],
        'planned_answers': 8, 'planned_observations': 16, 'max_attempts': 1, 'repeats': 1,
        'starting_requests': before, 'reserved_future_blind_assessments': 8, 'combined_budget': 300,
        'allocated_combined_budget':297,'primary_phase_ceiling':289,'unallocated_calls':3,
        'budget_allocation_amendment':bind(paths['budget_allocation_amendment']),
        'all_statuses_retained': True, 'no_post_confirmation_tuning': True, 'expert_returns': 0, 'formal_eligible': False}
    save_once(OUT/'plan.json', plan)
    save_once(OUT/'unsealing_receipt.json', {'utc': j.now(), 'plan': bind(OUT/'plan.json'),
        'release': bind(RELEASE), 'first_source_read_follows_this_receipt': True})
    cases = []; access = []; contexts = []
    for item in release['confirmation_inputs']:
        path = verify(item)  # First sealed bytes, after all gates and immutable plan.
        case = clean_source(item, j.read(path)); case['references'], selection = pool_for(case, refs, byid)
        case['input_sha256'] = j.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                                       'protocol': case['model_response'], 'references': case['references']})
        aid = case['anonymous_answer_id']; cases.append(case)
        access.append({'anonymous_answer_id': aid, **bind(path), 'read_after_plan': bind(OUT/'plan.json')})
        j.save(OUT/'reference_selections'/f'{aid}.json', selection)
        doc = backend.grounded.document(case['model_response'], backend.grounded.source_id_for_case(case))
        require(doc['text'] == case['model_response'] and ''.join(x['text'] for x in doc['units']) == case['model_response'], 'DOCUMENT_NOT_LOSSLESS')
        prompt = backend.grounded.make_prompt(case, doc)
        j.save(OUT/'source_documents'/f'{aid}.json', doc)
        pp = OUT/'prompts'/f'{aid}.txt'; pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_text(prompt, encoding='utf8', newline='')
        # All judges receive identical full bytes; no model-specific compression.
        contexts += [{'anonymous_answer_id': aid, 'judge': model['name'], **context_check(prompt, model['settings'])} for model in models]
    require(len(cases) == 8 and len({(c['question_id'], c['specific_question'], c['model_response']) for c in cases}) == 8, 'FIXED_EIGHT_DISTINCT_INPUTS')
    j.save(OUT/'cases.json', {'cases': cases})
    j.save(OUT/'blind_input_records.json', [{k: c[k] for k in SAFE_KEYS} for c in cases])
    j.save(OUT/'source_access_receipt.json', access); j.save(OUT/'context_checks.json', contexts)
    deterministic_steps(cases, refs, backend.grounded, paths)
    files = [p for p in OUT.rglob('*') if p.is_file() and 'embedding_cache' not in p.parts and p.name not in ['actual_commands.json', 'prepared_inputs.json']]
    j.save(OUT/'prepared_inputs.json', {'status': 'prepared_after_authorized_unsealing', 'plan': bind(OUT/'plan.json'),
        'bindings': [bind(p) for p in files], 'no_generation_requests': True})
    require(request_count() == before, 'PREPARATION_GENERATED_REQUEST')
    record('prepare', new_requests=0, actual_sources=8, local_context_failure_cells=sum(not x['fits'] for x in contexts))


def validate_prepared():
    release, paths = release_gate()
    plan = j.read(OUT/'plan.json')
    require(plan['final_release'] == bind(RELEASE), 'RELEASE_CHANGED_AFTER_UNSEALING')
    for item in plan['frozen_inputs']: verify(item)
    prepared = j.read(OUT/'prepared_inputs.json')
    require(prepared['plan'] == bind(OUT/'plan.json'), 'PREPARED_PLAN_CHANGED')
    for item in prepared['bindings']: verify(item)
    return release, paths, plan


def expected_payload(public, prompt):
    api = j.make_adapter(public, None); captured = []
    def stub(**kwargs):
        kwargs['options']['num_ctx'] = public['num_ctx']; captured.append(copy.deepcopy(kwargs))
        return {'done': True, 'done_reason': 'stop', 'response': '{}', 'model': 'SYNTHETIC_SERIALIZER', 'eval_count': 1}
    api.client.client.generate = stub; api.client._generate(prompt)
    require(len(captured) == 1, 'HTTP_SERIALIZATION_EXPECTED_ONE_PAYLOAD')
    return captured[0]


def require_scientific_contract(current, frozen):
    for key in ['files', 'demands', 'source_registry_sha256', 'scoring_version']:
        require(current[key] == frozen[key], 'ORIGINAL_SCIENTIFIC_CONTRACT_DRIFT:' + key)


def preflight():
    _, paths, plan = validate_prepared(); before = request_count()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        runner, _, registry = j.runtime(arguments(paths)); actual = j.model_configs(arguments(paths))
    for model in actual: model['public']['format'] = j.read(paths['schema'])
    frozen = public_models(paths)
    require([{ 'name': m['name'], 'family': m['family'], 'settings': m['public']} for m in actual] == frozen, 'ACTUAL_MODELS_DIFFER_FROM_FROZEN_FINAL_MODELS')
    cases = j.cases_from(OUT/'cases.json', registry)
    base = j.contract(arguments(paths), runner, registry, actual)
    previous = j.read(paths['model_contract'])
    require_scientific_contract(base, previous)
    contract = {**base, 'primary_confirmation': {'version': VERSION, 'plan_sha256': j.filehash(OUT/'plan.json'),
        'prepared_inputs_sha256': j.filehash(OUT/'prepared_inputs.json'), 'final_release_sha256': j.filehash(RELEASE),
        'reference_policy_sha256': j.filehash(paths['reference_policy']), 'original_numeric_adapter_sha256': j.filehash(numeric.__file__)}}
    save_once(OUT/'expected_contract.json', contract); matrix = []; backend = load_backend(paths)
    for case in cases:
        aid = case['anonymous_answer_id']; prompt = (OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        doc = j.read(OUT/'source_documents'/f'{aid}.json')
        # This constructor uses asyncio.run internally; it must stay synchronous.
        require(backend.grounded.make_prompt(case, doc) == prompt, 'SYNCHRONOUS_PROMPT_REPLAY_DIFFERS')
        for model in actual:
            single = {**contract, 'models': [{'name': model['name'], 'family': model['family'], 'settings': model['public']}]}
            identity = {'case_id': case['case_id'], 'input_sha256': case['input_sha256'], 'judge': model['name'],
                        'repeat_index': 0, 'contract_sha256': j.digest(single)}
            trial = j.digest(identity); payload = expected_payload(model['public'], prompt)
            save_once(OUT/'expected_http_payloads'/f'{trial}.json', payload)
            matrix.append({'anonymous_answer_id': aid, 'judge': model['name'], 'identity': identity,
                'planned_trial_id': trial, 'prompt_raw_sha256': rawsha(prompt), 'context': context_check(prompt, model['public']),
                'source_id': backend.grounded.source_id_for_case(case), 'attempt': 1, 'repeat_index': 0})
    require(len(matrix) == len({x['planned_trial_id'] for x in matrix}) == 16, 'MATRIX_MUST_HAVE_SIXTEEN_DISTINCT_CELLS')
    save_once(OUT/'matrix.json', matrix)
    files = [Path(__file__), OUT/'plan.json', OUT/'prepared_inputs.json', OUT/'expected_contract.json', OUT/'matrix.json',
             *sorted((OUT/'expected_http_payloads').glob('*.json'))]
    j.save(OUT/'preflight_verification.json', {'status': 'pass', 'new_model_requests': 0, 'bindings': [bind(p) for p in files],
        'context_fit_cells': sum(x['context']['fits'] for x in matrix), 'overlength_cells_will_be_local_failures_not_trimmed': True})
    require(request_count() == before, 'PREFLIGHT_GENERATED_REQUEST'); record('preflight', new_requests=0)


def run_gate():
    _, paths, plan = validate_prepared()
    check = j.read(OUT/'preflight_verification.json'); require(check['status'] == 'pass', 'PREFLIGHT_REQUIRED')
    for item in check['bindings']: verify(item)
    path = OUT/'pre_generation_review/integration_review.json'
    require(path.exists(), 'ROOT_INDEPENDENT_INTEGRATION_REVIEW_REQUIRED')
    review = j.read(path)
    require(review.get('status') == 'pass' and review.get('reviewed_by') == 'root_agent' and
            review.get('actual_model_requests') == 0 and review.get('full_schema_actual_HTTP_serialization_pass') is True,
            'ROOT_INTEGRATION_GATE_NOT_PASSED')
    reviewed = {str(Path(x['path']).resolve()): x['sha256'] for x in review['protected_inputs']}
    for path in [Path(__file__), paths['converter'], paths['development_backend'], paths['numeric_adapter'],
                 OUT/'plan.json', OUT/'prepared_inputs.json', OUT/'expected_contract.json', OUT/'matrix.json']:
        require(reviewed.get(str(path.resolve())) == j.filehash(path), 'ROOT_INTEGRATION_REVIEW_STALE:' + str(path))
    return paths, plan


async def execute_cell(cell, case, public, backend, runner, APIJudge, paths):
    """One terminal observation; no repair, retry or conversion fallback."""
    trial = cell['planned_trial_id']; dest = RUN/'attempts'/f'{trial}_1'; dest.mkdir(parents=True, exist_ok=True)
    prompt = (OUT/'prompts'/f"{case['anonymous_answer_id']}.txt").read_text(encoding='utf8')
    doc = j.read(OUT/'source_documents'/f"{case['anonymous_answer_id']}.json")
    ground = backend.grounded; state = {'request': None, 'dispatched': False, 'conversion': None, 'error': None, 'entered': False}
    api = None; evaluation = {}; started = j.now()
    try:
        # Do not call make_prompt here: its original prompt capturer uses asyncio.run.
        require(rawsha(prompt) == cell['prompt_raw_sha256'] and doc['source_id'] == ground.source_id_for_case(case)
                and doc['text'] == case['model_response'] and doc['answer_sha256'] == rawsha(case['model_response']),
                'FROZEN_PROMPT_OR_FULL_SOURCE_CHANGED')
        check = context_check(prompt, public); j.save(dest/'context_check.json', check)
        require(check['fits'], 'FULL_PROMPT_CONTEXT_EXCEEDED_NO_TRUNCATION')
        api = j.make_adapter(public, APIJudge); generate = api.client.client.generate
        def capture(**kwargs):
            kwargs['options']['num_ctx'] = public['num_ctx']
            require(state['request'] is not None, 'HTTP_WITHOUT_RESERVED_ACTUAL_TRIAL')
            require(kwargs == j.read(OUT/'expected_http_payloads'/f'{trial}.json'), 'ACTUAL_HTTP_FULL_PAYLOAD_DRIFT')
            j.save(dest/'http_request_payload.json', kwargs)
            state['dispatched'] = True
            j.save(dest/'request_receipt.json', state['request'])
            return generate(**kwargs)
        api.client.client.generate = capture
        class Teacher:
            model_name = public['model']
            async def _acall(self, unused_original_prompt):
                require(not state['entered'], 'SECOND_REQUEST_FOR_CELL_FORBIDDEN'); state['entered'] = True
                (dest/'prompt.txt').write_text(prompt, encoding='utf8', newline='')
                state['request'] = j.reserve_request(arguments(paths, True), trial, 1, cell['judge'])
                j.save(dest/'request_reservation.json', state['request'])
                try:
                    try: result = await api._acall(prompt)
                    except Exception as exc:
                        result = parent.completed_json_failure_payload(api.last_response, exc, api.model_name, public['max_output_tokens'])
                        if result is None: raise
                finally:
                    if api.last_response is not None:
                        j.save(dest/'provider_response.json', api.last_response)
                        if isinstance(api.last_response.get('response'), str):
                            (dest/'raw_source_bound_content.txt').write_text(api.last_response['response'], encoding='utf8', newline='')
                    if api.last_error is not None: j.save(dest/'provider_error.json', {'error_type': type(api.last_error).__name__, 'reason': str(api.last_error)})
                raw = result.get('content'); require(isinstance(raw, str), 'PROVIDER_RAW_TEXT_REQUIRED')
                (dest/'raw_source_bound_content.txt').write_text(raw, encoding='utf8', newline='')
                j.save(dest/'raw_source_bound_receipt.json', {'raw_response_sha256': rawsha(raw), 'raw_text_unchanged': True,
                    'raw_text_file_sha256': j.filehash(dest/'raw_source_bound_content.txt'), 'source_document_sha256': j.filehash(OUT/'source_documents'/f"{case['anonymous_answer_id']}.json")})
                try:
                    conversion = ground.convert(raw, doc)
                    require(conversion['legacy_runner_payload']['scores'] == integrity.parse_judge_object(raw)['scores'], 'DIRECT_SCORES_CHANGED')
                    require(conversion['raw_response_sha256'] == rawsha(raw), 'RAW_CONVERSION_HASH_DIFFERS')
                except Exception as exc:
                    state['error'] = {'stage': 'SOURCE_BOUND_CONVERSION', 'type': type(exc).__name__, 'reason': str(exc), 'legacy_parser_fallback_permitted': False}
                    j.save(dest/'source_bound_conversion_error.json', state['error']); raise
                state['conversion'] = conversion; j.save(dest/'source_bound_conversion.json', conversion)
                j.save(dest/'projected_legacy_payload.json', conversion['legacy_runner_payload'])
                (dest/'projected_legacy_content.txt').write_text(conversion['legacy_runner_content'], encoding='utf8', newline='')
                return {**result, 'content': conversion['legacy_runner_content'], 'raw_content': raw,
                    'metadata': {**result.get('metadata', {}), 'explicit_source_bound_projection': True}}
        prior_log = runner._log_teacher_response
        runner._log_teacher_response = lambda *a, **kw: j.save(dest/'runner_log.json', {'args': list(a), 'kwargs': kw})
        try:
            evaluation = await runner.evaluate_response_with_teacher(Teacher(), case['specific_question'], case['model_response'],
                runner.MODEL_SPACE_SIGNED, {'question_id': case['question_id']}, None)
        finally: runner._log_teacher_response = prior_log
    except Exception as exc:
        if state['error'] is None: state['error'] = {'stage': 'LOCAL_PRE_REQUEST' if not state['dispatched'] else 'REQUEST_OR_EVALUATOR', 'type': type(exc).__name__, 'reason': str(exc)}
    if not state['dispatched'] and state['error'] is None:
        state['error'] = {'stage': 'LOCAL_PRE_REQUEST', 'type': 'EvaluatorDidNotDispatch',
            'reason': evaluation.get('_error') or 'Original evaluator did not reach a model request'}
    complete = bool(state['conversion'] is not None and state['error'] is None and evaluation.get('technical_status') == 'VALID' and not evaluation.get('_error'))
    row = {'trial_id': trial, 'identity': cell['identity'], 'anonymous_answer_id': case['anonymous_answer_id'],
        'judge': cell['judge'], 'case_id': case['case_id'], 'question_id': case['question_id'], 'attempt': 1, 'repeat_index': 0,
        'started_utc': started, 'finished_utc': j.now(), 'status': 'success' if complete else 'failed',
        'actual_api_request_made': state['dispatched'], 'budget_reservation_made': state['request'] is not None,
        'local_failure_reason': state['error']['reason'] if not state['dispatched'] and state['error'] else None,
        'error': state['error'], 'evaluation': evaluation, 'conversion': state['conversion'],
        'legacy_parser_fallback_used': False, 'raw_return_modified': False,
        'actual_returned_model': (api.last_response or {}).get('model') if api else None,
        'prompt_raw_sha256': rawsha(prompt), 'references_sha256': j.digest(case['references']), 'formal_eligible': False}
    j.save(dest/'result.json', row); save_once(RUN/'trials'/f'{trial}.json', row)
    return row


async def run():
    paths, plan = run_gate(); backend = load_backend(paths); matrix = j.read(OUT/'matrix.json')
    cases = {c['anonymous_answer_id']: c for c in j.read(OUT/'cases.json')['cases']}
    ids = {r['planned_trial_id'] for r in matrix}; ledger = [r for r in j.ledger_rows(LEDGER) if r.get('event') == 'request_started' and r['trial_id'] in ids]
    require(len(ledger) == len({r['trial_id'] for r in ledger}) and all(r['attempt'] == 1 for r in ledger), 'DUPLICATE_OR_RETRIED_PRIMARY_REQUEST')
    terminal = {p.stem: j.read(p) for p in (RUN/'trials').glob('*.json')}
    require(set(terminal) <= ids, 'UNPLANNED_TRIAL_FILE')
    require({r['trial_id'] for r in ledger} <= set(terminal), 'INTERRUPTED_REQUEST_NEEDS_EXPLICIT_TERMINAL_IMPORT_NEVER_RETRY')
    pending = [c for c in matrix if c['planned_trial_id'] not in terminal]
    budget_guard(plan['starting_requests'], len(ledger), len(pending))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        runner, api_type, registry = j.runtime(arguments(paths)); models = j.model_configs(arguments(paths))
    for model in models: model['public']['format'] = j.read(paths['schema'])
    require([{'name': m['name'], 'family': m['family'], 'settings': m['public']} for m in models] == public_models(paths), 'RUN_MODEL_DRIFT')
    now_contract = j.contract(arguments(paths), runner, registry, models); old_contract = j.read(OUT/'expected_contract.json')
    require(all(now_contract[k] == old_contract[k] for k in now_contract), 'RUN_SCIENTIFIC_CONTRACT_DRIFT')
    before = request_count()
    for cell in pending:
        model = next(m for m in models if m['name'] == cell['judge'])
        row = await execute_cell(cell, cases[cell['anonymous_answer_id']], model['public'], backend, runner, api_type, paths)
        print(j.canonical({'anonymous_answer_id': row['anonymous_answer_id'], 'judge': row['judge'], 'status': row['status'],
            'actual_request': row['actual_api_request_made'], 'package_requests': request_count()}), flush=True)
    record('run', new_budget_reservations=request_count()-before, no_retries=True)


def mark_interrupted(evidence_path):
    """Import an externally documented stopped request; never retry or repair it."""
    _, _, _ = validate_prepared()
    evidence_path = Path(evidence_path); receipt = j.read(evidence_path)
    require(receipt.get('status') == 'request_terminated_without_terminal_record' and
            receipt.get('recorded_by') == 'root_agent' and receipt.get('confirmed_no_active_request') is True
            and bool(receipt.get('reason')), 'ROOT_TERMINATION_EVIDENCE_REQUIRED')
    tid = receipt['trial_id']; found = [x for x in j.read(OUT/'matrix.json') if x['planned_trial_id'] == tid]
    require(len(found) == 1, 'INTERRUPTED_CELL_NOT_IN_MATRIX'); cell = found[0]
    dest = RUN/'attempts'/f'{tid}_1'; require(not (RUN/'trials'/f'{tid}.json').exists(), 'TERMINAL_TRIAL_CANNOT_BE_REPLACED')
    reservation = j.read(dest/'request_reservation.json')
    require(reservation['trial_id'] == tid and reservation['attempt'] == 1 and
            reservation in j.ledger_rows(LEDGER), 'INTERRUPTED_REAL_RESERVATION_MISSING')
    bound = {str(Path(x['path']).resolve()): x['sha256'] for x in receipt['bindings']}
    for path in [OUT/'plan.json', OUT/'matrix.json', dest/'request_reservation.json']:
        require(bound.get(str(path.resolve())) == j.filehash(path), 'TERMINATION_EVIDENCE_BINDING_MISSING')
    for item in receipt['bindings']: verify(item)
    actual = (dest/'request_receipt.json').exists()
    case = next(x for x in j.read(OUT/'cases.json')['cases'] if x['anonymous_answer_id'] == cell['anonymous_answer_id'])
    row = {'trial_id': tid, 'identity': cell['identity'], 'anonymous_answer_id': cell['anonymous_answer_id'],
        'case_id': case['case_id'], 'question_id': case['question_id'], 'judge': cell['judge'], 'attempt': 1, 'repeat_index': 0,
        'status': 'failed', 'actual_api_request_made': actual, 'budget_reservation_made': True,
        'local_failure_reason': None if actual else receipt['reason'],
        'failure_kind': 'externally_documented_interrupted_observation_not_retried', 'termination_evidence': bind(evidence_path),
        'evaluation': {}, 'conversion': None, 'raw_return_modified': False, 'legacy_parser_fallback_used': False,
        'formal_eligible': False, 'finished_utc': j.now()}
    save_once(RUN/'trials'/f'{tid}.json', row); save_once(dest/'result.json', row)
    record('mark-interrupted', new_requests=0, trial_id=tid, evidence=bind(evidence_path))


def analyze():
    _, paths, plan = validate_prepared(); backend = load_backend(paths)
    matrix = j.read(OUT/'matrix.json'); cases = {c['anonymous_answer_id']: c for c in j.read(OUT/'cases.json')['cases']}
    steps = {r['anonymous_answer_id']: r for r in j.read(OUT/'deterministic_steps.json')}
    ledger = {r['request_id']: r for r in j.ledger_rows(LEDGER) if r.get('event') == 'request_started'}
    observations = []; terminals = []; evidence = []
    for cell in matrix:
        aid = cell['anonymous_answer_id']; case = cases[aid]; step = steps[aid]; tid = cell['planned_trial_id']
        path = RUN/'trials'/f'{tid}.json'; require(path.exists(), 'PRIMARY_CELL_NOT_TERMINAL:' + tid)
        trial = j.read(path); dest = RUN/'attempts'/f'{tid}_1'
        require(trial['identity'] == cell['identity'] and trial['attempt'] == 1 and trial['status'] in ['success', 'failed'], 'TRIAL_IDENTITY_OR_STATUS')
        receipt_path = dest/'request_receipt.json'; actual = trial['actual_api_request_made']
        require(actual == receipt_path.exists(), 'ACTUAL_REQUEST_RECEIPT_MISMATCH')
        if actual:
            receipt = j.read(receipt_path)
            require(ledger.get(receipt['request_id']) == receipt and receipt['trial_id'] == tid and receipt['attempt'] == 1, 'ACTUAL_LEDGER_RECEIPT_DIFFERS')
        else: require(trial['status'] == 'failed' and trial.get('local_failure_reason'), 'LOCAL_FAILURE_REQUIRES_REASON')
        reservation_path = dest/'request_reservation.json'
        require(trial.get('budget_reservation_made') == reservation_path.exists(), 'BUDGET_RESERVATION_PROVENANCE')
        if reservation_path.exists():
            reserved = j.read(reservation_path)
            require(ledger.get(reserved['request_id']) == reserved and reserved['trial_id'] == tid, 'RESERVATION_LEDGER_MISMATCH')
        require(step['answer_sha256'] == rawsha(case['model_response']) and step['question_sha256'] == rawsha(case['specific_question'])
            and step['references_sha256'] == j.digest(case['references']), 'STEP_FULL_INPUT_BINDING_DIFFERS')
        conversion = trial.get('conversion'); replay = None
        if trial['status'] == 'success':
            raw = (dest/'raw_source_bound_content.txt').read_bytes().decode('utf8')
            require(j.read(dest/'provider_response.json')['response'] == raw, 'PROVIDER_RAW_NOT_BYTE_PRESERVED')
            require(j.read(dest/'http_request_payload.json') == j.read(OUT/'expected_http_payloads'/f'{tid}.json'), 'ACTUAL_FULL_HTTP_PAYLOAD_DIFFERS')
            doc = j.read(OUT/'source_documents'/f'{aid}.json')
            require(backend.grounded.convert(raw, doc) == conversion == j.read(dest/'source_bound_conversion.json'), 'RAW_CONVERSION_REPLAY_DIFFERS')
            require(trial['evaluation'].get('extraction') == conversion['legacy_projection']['extraction'], 'ORIGINAL_EVALUATOR_EXTRACTION_CHANGED')
            replay = numeric.score_conversion(case, conversion, backend, step)
            values = replay['metrics']; j.save(OUT/'numeric_replays'/f'{tid}.json', replay)
        else: values = numeric.derive({}, step, False)
        observations.append({'anonymous_answer_id': aid, 'question_id': case['question_id'], 'judge': cell['judge'], 'trial_id': tid, 'status': trial['status'],
            'actual_request_made': actual, 'metrics': values, 'step_source': 'deterministic_step_reuse',
            'judge_attempt_failed': trial['status'] != 'success', 'complete_numeric_CCE': all(numeric.finite(values[k]) for k in ['Com', 'Cor', 'Eff', 'IA', 'HV']),
            'evidence_state': replay['evidence_state'] if replay else backend.evidence_state(None),
            'source_fact_acceptance': 'separate_confirmation_evidence_review_required', 'formal_eligible': False})
        terminals.append({'trial_id': tid, 'status': trial['status'], 'attempt': 1, 'actual_request_made': actual,
            'trial': bind(path), 'receipt': bind(receipt_path) if actual else None,
            'budget_reservation': bind(reservation_path) if reservation_path.exists() else None,
            'local_failure_reason': trial.get('local_failure_reason')})
        evidence += [bind(path), *[bind(p) for p in sorted(dest.glob('*')) if p.is_file()]]
    require(len(observations) == len(terminals) == 16, 'SIXTEEN_OBSERVATION_DENOMINATOR')
    j.save(OUT/'observations.json', observations)
    with (OUT/'observations.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        keys = ['anonymous_answer_id', 'question_id', 'judge', 'trial_id', 'status', 'actual_request_made', 'judge_attempt_failed',
                'step_source', 'complete_numeric_CCE', *numeric.METRICS]
        writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
        for row in observations:
            writer.writerow({**{k: row[k] for k in keys if k not in numeric.METRICS}, **row['metrics']})
    judges = [m['name'] for m in public_models(paths)]
    common = [aid for aid in IDS if all(any(r['anonymous_answer_id'] == aid and r['judge'] == judge and r['complete_numeric_CCE'] for r in observations) for judge in judges)]
    means = {judge: {metric: sum(r['metrics'][metric] for r in observations if r['judge'] == judge and r['anonymous_answer_id'] in common)/len(common)
        for metric in ['Com', 'Cor', 'Eff', 'IA', 'HV']} for judge in judges} if common else {}
    common_qid_counts = {str(qid): sum(cases[aid]['question_id'] == qid for aid in common)
        for qid in sorted({cases[aid]['question_id'] for aid in common})}
    j.save(OUT/'completion_summary.json', {'status': 'experiment_complete_not_scientific_validation', 'actual_answers': 8,
        'actual_terminal_observations': 16, 'planned_observations': 16, 'actual_requests': sum(r['actual_request_made'] for r in observations),
        'budget_counted_reservations': sum(r['budget_reservation'] is not None for r in terminals),
        'technical_successes': sum(r['status'] == 'success' for r in observations), 'technical_failures': sum(r['status'] == 'failed' for r in observations),
        'complete_numeric_CCE': sum(r['complete_numeric_CCE'] for r in observations), 'per_metric_numeric': {k: sum(numeric.finite(r['metrics'][k]) for r in observations) for k in numeric.METRICS},
        'all_observation_denominators': 16, 'answer_observation_units': 8, 'metrics_are_not_independent_samples': True,
        'common_answer_ids': common, 'common_n': len(common), 'common_means': means,
        'common_question_id_counts': common_qid_counts,
        'aggregation': 'mean per-answer CCE, IA and HV over common anonymous answers; never IA/HV of mean dimensions; no qid equal-weight macro-average',
        'new_analysis_requests': 0, 'expert_returns': 0, 'formal_eligible': False, 'phase_closed_by_root_separate_release_required': True})
    j.save(OUT/'verification.json', {'status': 'pass', 'terminal_cells': terminals, 'all_16_terminal_cells_retained': True,
        'all_8_answers_retained': True, 'attempt1_only': True, 'new_analysis_requests': 0,
        'bindings': evidence + [bind(OUT/n) for n in ['plan.json', 'matrix.json', 'deterministic_steps.json', 'step_verification.json', 'observations.json', 'completion_summary.json']]})
    (OUT/'primary_ledger_at_completion.jsonl').write_bytes(LEDGER.read_bytes())
    record('analyze', new_requests=0, actual_terminal_observations=16)


def draft():
    """Public metadata/code only. Not an authorization, release or frozen plan."""
    DESIGN.mkdir(parents=True, exist_ok=True)
    ref_paths = {'reference_catalog': projection.CAT,
        'reference_projection': REFERENCE_REVISION/'projected_all_references.json',
        'reference_integrity_amendment': REFERENCE_REVISION/'integrity_amendment.json',
        'projection_script': Path(projection.__file__), 'method_family_policy': family.DEST/'policy.json',
        'step_core': Path(family.core.__file__), 'step_scorer': Path(family.__file__)}
    projected = j.read(ref_paths['reference_projection'])
    # A root-authored future frozen copy is required; this file grants no access.
    j.save(DESIGN/'reference_policy_draft.json', {'status': 'draft_not_frozen', 'prompt_projection': PROJECTION,
        'projection_roundtrip_exact': True, 'shared_value_encoding': False,
        'prompt_reference_allowed_fields': sorted({key for ref in projected for key in ref}),
        'allowed_fields_usage': 'validation key union only; never a field filtering operation',
        'selection': family.policy()['selection'], 'primary_threshold': .7, 'encoder': 'all-mpnet-base-v2',
        'pool_rule': 'original method-family resolve: same method + qid + explicit version; no judge-output feedback',
        'reference_revision': 'revision_02; original overwritten context evidence is transparently documented, not represented as restored',
        'same_complete_scientific_pool_for_all_judges_and_blind': True,
        'scientific_applicability_not_inferred_from_numeric_steps': True,
        **{key: bind(path) for key, path in ref_paths.items()}})
    j.save(DESIGN/'interface_draft.json', {'status': 'code_only_unapproved_not_frozen', 'version': VERSION,
        'script': bind(__file__), 'planned_answers': 8, 'planned_cells': 16, 'source_schema_from_public_builder_only': sorted(SOURCE_KEYS),
        'release_required_asset_roles': sorted(ASSETS), 'future_release': str(RELEASE),
        'prompt_projection': PROJECTION, 'shared_value_encoding': False, 'num_ctx': 98304,
        'model_policy': 'two frozen verified local families, full source and same scientific pool, temperature0/output8192/attempt1',
        'deterministic_exports': ['deterministic_steps.json', 'full_step_results.json', 'step_verification.json', 'embedding_usage.json'],
        'blind_exports': ['blind_input_records.json', 'plan.json', 'matrix.json', 'observations.json', 'verification.json', 'completion_summary.json'],
        'blind_record_exact_keys': sorted(SAFE_KEYS), 'metrics': numeric.METRICS,
        'failure_policy': 'keep all16; local context overflow no request; judge failure retains verified SR/SP; dependent NA not imputed',
        'reserved_future_blind_assessments': 8, 'combined_ceiling': 300,
        'primary_request_ceiling': 289, 'allocated_combined_ceiling':297, 'unallocated_calls':3, 'ledger_external_request_count': 0,
        'future_allowance_is_not_added_to_actual_request_index': True,
        'commands': ['prepare', 'preflight', 'run --allow-local-calls', 'analyze', 'mark-interrupted --evidence ROOT_RECORD'],
        'current_authorization': 'draft_and_synthetic_checks_only', 'sealed_read': False,
        'new_model_requests': 0, 'new_embeddings': 0, 'actual_argv': [sys.executable, *sys.argv]})
    (DESIGN/'README.md').write_text('''# Primary confirmation 草稿

本目录只是未冻结的实现与接口；没有读取 sealed8、manifest、identity key 或人工15，没有请求模型或计算向量。

最终 release 必须由 root 在开发事实审查、E2 21全文/15对、E4 30观察终态之后创建。release 与 final_configuration 必须逐文件绑定代码、完整11分支目录、lossless科学投影、原 all-mpnet/segment/SR/SP/.7、模型/KB/demand/量表和事先冻结的盲评包规则。源码不能给自己签发批准。

未来 `prepare` 先验证全部公开 metadata gate，保存 immutable plan 与首读 receipt，然后才读取 release 精确列出的8个 Cxx JSON。原身份对照表与确认 manifest 永远不读取。全文按原同方法/version/qid规则获取完整科学 pool；两个 judge 和盲评共享同一 pool，原 whole-reference SR→same-reference SP→冻结顺序确定步骤参考，不按 judge 回答挑选。

`reference_projection` 是已核11对象科学投影列表；逐对象还原原目录精确相等。version、起点、未知、前提、适用条件和完整步骤均保留；构建身份侧车不入 prompt。无 shared 编码、无科学字段截短。

本草稿只绑定 `confirmation_reference_design_v1/revision_02/projected_all_references.json`，并强制绑定同目录 `integrity_amendment.json`。原设计目录曾在 v4 决策已引用后被覆盖；旧 summary 字节未找回，间接证据链问题不能被新版投影掩盖。原 primary 草稿字节保存在 `revision_01_snapshot`。

未来每答案2次全新请求共16 cells，temp0/98304/output8192/attempt1。每次校验序列化HTTP完整payload、schema、prompt与来源；原始provider文本与转换结果分存。转换失败不可转入旧JSON捷径，不重试。超context保留真实local-failure且不扣虚构请求。8行确定性SR/SP独立导出，judge失败保留已知值，其余依赖按NA传播。

预算绑定前瞻v6修订：本阶段累计请求上限289，在原账本锁下保留8个后续Codex盲评位置，已分配合计上限297、全局上限300，3次未分配不授权重试；`external_request_count=0`，未来预留不增加真实 package_request_index。preflight同时核 files、demands、source_registry_sha256、scoring_version。resume只跳过已有终态（包括失败）；有receipt无终态则停止待显式失败导入，绝不重新请求。root独立HTTP integration gate仍是 run 的必需条件。

`observations.json` 固定16行、16分项；8个答案为真实观察对象，分项不是独立样本。技术通过、证据未决、完整CCE分开；无专家gold或科学正确声明。共同集使用同一8答案ID交集，逐答案IA/HV先计算再平均。

当前只允许：`python scripts/cce_grounded_confirmation_v2.py draft`。未执行 prepare/preflight/run/analyze；最终v4事实与完整确认合同尚待root决定。
''', encoding='utf8')
    print(j.canonical({'status': 'code_only_draft', 'new_model_requests': 0, 'sealed_read': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['draft', 'prepare', 'preflight', 'run', 'analyze', 'mark-interrupted'])
    parser.add_argument('--allow-local-calls', action='store_true')
    parser.add_argument('--evidence', type=Path)
    cli = parser.parse_args()
    if cli.action == 'run':
        require(cli.allow_local_calls, 'EXPLICIT_ALLOW_LOCAL_CALLS_REQUIRED'); asyncio.run(run())
    elif cli.action == 'mark-interrupted':
        require(cli.evidence is not None, 'ROOT_TERMINATION_EVIDENCE_PATH_REQUIRED'); mark_interrupted(cli.evidence)
    else: {'draft': draft, 'prepare': prepare, 'preflight': preflight, 'analyze': analyze}[cli.action]()
