"""Prospective round-two confirmation: release gate and source export only.

Import, --help and draft do not open the private selection manifest or archives.
Only a hash-bound root release after actual development/E2/E4 termination permits
prepare-sources to read the frozen eight selected records. Generation is not yet
implemented here. No command creates an approval or replaces a selected answer.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_budget as budget
import cce_judges as j
import cce_method_family_steps_v1 as family
import cce_confirmation_reference_design_v1 as projection
from cce_expand_references_v5 import object_spans

BASE = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010'
DESIGN = BASE / 'confirmation_qwen_only_draft_v1'
OUT = BASE / 'grounded_confirmation_qwen_only_v1'
SAMPLING = BASE / 'confirmation_sampling_v1'
ARCHIVES = ROOT / 'dataset/Q+AR/model_response'
IDS = [f'R2C{i:02d}' for i in range(1, 9)]
MODELS = ['local_qwen27b_q8_development']
SCIENCE_KEYS = ['files', 'demands', 'source_registry_sha256', 'scoring_version']
VERSION = 'round2-confirmation-qwen-only-release-v1'
SCOPE = 'within-exposed-task prospective answer-level automatic confirmation'
ASSETS = {
    'controller', 'budget_adapter', 'authorization', 'development_backend',
    'followup_backend', 'converter', 'numeric_adapter', 'baseline_science_contract',
    'development_plan', 'development_matrix', 'development_completion',
    'development_verification', 'development_contract', 'development_facts',
    'fact_checker', 'fact_checker_freeze', 'independent_source_review',
    'E2_plan', 'E2_matrix', 'E2_completion', 'E2_verification', 'E2_contract',
    'E4_plan', 'E4_matrix', 'E4_completion', 'E4_verification', 'E4_contract',
    'final_configuration', 'model_config', 'reference_policy', 'reference_catalog',
    'reference_projection', 'projection_script', 'method_family_policy',
    'step_core', 'step_scorer', 'encoder_manifest', 'sampling_summary', 'sampling_policy', 'E4_analyzer', 'E4_scheduler',
}
STAGES = {'development': 5, 'E2': 21, 'E4': 15}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def rawsha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf8')).hexdigest()


def bind(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': j.filehash(p)}


def descriptor(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'PATH_SHA_DESCRIPTOR_REQUIRED')
    require(isinstance(value['path'], str) and Path(value['path']).is_absolute()
            and isinstance(value['sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['sha256']),
            'INVALID_PATH_SHA_DESCRIPTOR')
    return Path(value['path']).resolve()


def public_path(path):
    p = Path(path).resolve()
    parts = {x.lower() for x in p.parts}
    require(not (parts & {'sealed_metadata', 'sealed_confirmation', 'private'})
            and p.name.lower() not in {'confirmation_manifest.json', 'selection_manifest.json', 'identity_key.json'},
            'PROTECTED_INPUT_BEFORE_RELEASE:' + str(p))
    return p


def verify(value, *, public=True):
    p = descriptor(value)
    if public:
        public_path(p)
    require(j.filehash(p) == value['sha256'], 'BOUND_FILE_CHANGED:' + str(p))
    return p


def verify_bindings(rows, required=()):
    require(isinstance(rows, list), 'BINDINGS_LIST_REQUIRED')
    indexed = {}
    for b in rows:
        p = verify(b)
        require(str(p) not in indexed or indexed[str(p)] == b['sha256'], 'CONFLICTING_BINDING')
        indexed[str(p)] = b['sha256']
    for p in required:
        require(indexed.get(str(Path(p).resolve())) == j.filehash(p), 'MISSING_REQUIRED_BINDING:' + str(p))


def save_once(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def verify_standard_terminal_stage(paths, phase, candidate_version, ledger):
    """Check real terminal identities and receipts, including status-blind reuse."""
    n = STAGES[phase]
    summary = j.read(paths[phase + '_completion'])
    verification = j.read(paths[phase + '_verification'])
    plan = j.read(paths[phase + '_plan'])
    matrix = j.read(paths[phase + '_matrix'])
    out = paths[phase + '_plan'].parent
    require(summary.get('status') == 'experiment_complete_not_scientific_validation'
            and summary.get('planned_observations') == summary.get('actual_observations') == n
            and summary.get('pending') == 0, 'PREDECESSOR_INCOMPLETE:' + phase)
    flag = 'all_five_terminal' if phase == 'development' else 'all_planned_terminal'
    require(verification.get('status') == 'pass' and verification.get(flag) is True
            and verification.get('terminal_observations') == n, 'PREDECESSOR_UNVERIFIED:' + phase)
    require(plan.get('status') == 'frozen_before_generation' and plan.get('phase') == phase
            and plan.get('candidate_version') == candidate_version
            and plan.get('planned_observations') == n and plan.get('max_attempts') == 1,
            'PREDECESSOR_PLAN_MISMATCH:' + phase)
    verify_bindings(plan['frozen_inputs'])
    verify_bindings(verification['bindings'], [paths[phase + '_plan'], paths[phase + '_matrix'], paths[phase + '_completion']])
    verify_bindings(summary['bound_observations'])
    required_observations = {str(descriptor(b)) for b in summary['bound_observations']}
    require(isinstance(matrix, list) and len(matrix) == n
            and len({r['planned_trial_id'] for r in matrix}) == n, 'PREDECESSOR_MATRIX_DENOMINATOR:' + phase)
    counts = Counter()
    identities = set()
    for row in matrix:
        identity = row['identity']; tid = row['planned_trial_id']
        require(tid == j.digest(identity), 'TRIAL_DIGEST_MISMATCH')
        judge = row.get('judge', identity.get('judge'))
        repeat = row.get('repeat_index', identity.get('repeat_index'))
        require(identity.get('judge') == judge and identity.get('repeat_index') == repeat, 'MATRIX_IDENTITY_MISMATCH')
        if phase == 'development':
            require(row['anonymous_answer_id'] in [f'A{i:02d}' for i in range(1, 6)]
                    and judge == MODELS[0] and repeat == 0, 'DEVELOPMENT_SCOPE_CHANGED')
        elif phase == 'E2':
            require(judge == MODELS[0] and repeat == 0 and not row.get('reuse'), 'E2_SCOPE_CHANGED')
        else:
            require(row['anonymous_answer_id'] in [f'A{i:02d}' for i in range(1, 6)]
                    and judge in MODELS and repeat in [0, 1, 2], 'E4_SCOPE_CHANGED')
        identities.add((row['anonymous_answer_id'], judge, repeat))
        source = out
        original = row
        if row.get('reuse'):
            reuse = row['reuse']
            require(phase == 'E4' and judge == MODELS[0] and repeat == 0
                    and reuse['qualification'].get('eligible') is True
                    and reuse['qualification'].get('status_blind') is True
                    and all(reuse['qualification']['checks'].values()), 'INVALID_REUSE_QUALIFICATION')
            source = Path(reuse['source_out']).resolve(); original = reuse['source_cell']
            require(source == paths['development_plan'].parent and original['identity'] == identity
                    and original['planned_trial_id'] == tid, 'REUSE_NOT_ORIGINAL_DEVELOPMENT')
        attempt = source / 'run/attempts' / (tid + '_1')
        trial_path = source / 'run/trials' / (tid + '.json')
        require(str(trial_path.resolve()) in required_observations, 'UNBOUND_PREDECESSOR_TRIAL')
        trial = j.read(public_path(trial_path))
        require(trial['trial_id'] == tid and trial['identity'] == identity
                and trial['case_id'] == row['case_id'] and trial['attempt'] == 1
                and trial['status'] in ['success', 'failed'] and trial['actual_request_made'] is True,
                'PREDECESSOR_TRIAL_IDENTITY')
        verify_bindings(trial['bound_artifacts'], [attempt / 'request_receipt.json', attempt / 'http_request_payload.json'])
        receipt = j.read(attempt / 'request_receipt.json')
        require(receipt['trial_id'] == tid and receipt['attempt'] == 1 and receipt['model'] == judge
                and receipt['request_id'] == trial['request_id'] and ledger.get(receipt['request_id']) == receipt,
                'PREDECESSOR_RECEIPT_LEDGER_MISMATCH')
        verify_bindings(list(original['assets'].values()))
        require(j.read(attempt / 'http_request_payload.json') == j.read(original['assets']['payload']['path']),
                'PREDECESSOR_ACTUAL_HTTP_PAYLOAD_CHANGED')
        counts[trial['status']] += 1
    require(len(identities) == n, 'DUPLICATE_PREDECESSOR_CELL')
    require(summary['technical_successes'] == counts['success'] and summary['technical_failures'] == counts['failed'],
            'PREDECESSOR_COUNTS_NOT_ACTUAL')
    return {'phase': phase, 'terminal_observations': n, **dict(counts)}



def verify_terminal_stage(paths, phase, candidate_version, ledger):
    if phase != 'E4':
        return verify_standard_terminal_stage(paths, phase, candidate_version, ledger)
    import cce_analyze_qwen_only_stability_v1 as analysis
    import cce_qwen_only_stability_continuation_v1 as continuation
    require(paths['E4_analyzer'] == Path(analysis.__file__).resolve()
            and paths['E4_scheduler'] == Path(continuation.__file__).resolve(),
            'QWEN_STABILITY_IMPLEMENTATION_BINDING')
    out = paths['E4_plan'].parent
    require(paths['E4_matrix'] == (out / 'matrix.json').resolve()
            and paths['E4_contract'] == (out / 'expected_contract.json').resolve(), 'QWEN_STAGE_PATH_IDENTITY')
    summary = j.read(paths['E4_completion']); verification = j.read(paths['E4_verification'])
    require(summary.get('status') == 'all_slots_accounted_not_scientific_validation'
            and summary.get('planned_observations') == summary.get('accounted_slots') == 15
            and summary.get('pending') == 0 and summary.get('user_cancelled_no_retry') == 1
            and summary.get('completed_model_attempts') == 14
            and summary.get('original_success_references') == 3
            and summary.get('continuation_new_terminal_attempts') == 11
            and summary.get('cross_judge_comparison') is False
            and summary.get('original_two_judge_batch_completed') is False, 'ACTUAL_QWEN_FIFTEEN_SLOT_ACCOUNTING')
    require(verification.get('status') == 'pass' and verification.get('all_slots_accounted') is True
            and verification.get('accounted_slots') == 15, 'QWEN_STABILITY_ANALYSIS_NOT_VERIFIED')
    verify_bindings(verification['bindings'], [paths['E4_completion']])
    verify_bindings(summary['bound_actual_artifacts'], [paths['E4_plan'], paths['E4_matrix'],
        paths['E4_contract'], paths['E4_analyzer'], paths['E4_scheduler']])
    plan, rows, bindings, replays = analysis.collect(out)
    require(j.read(Path(plan['source_out']) / 'plan.json')['candidate_version'] == candidate_version,
            'QWEN_STABILITY_CANDIDATE_VERSION')
    within, categories = analysis.summarize(rows)
    actual = analysis.completion(rows, within, categories, replays)
    require(all(summary.get(k) == v for k, v in actual.items()), 'QWEN_STABILITY_COUNTS_NOT_ACTUAL')
    bound = {str(descriptor(b)): b for b in summary['bound_actual_artifacts']}
    require(all(bound.get(str(descriptor(b))) == b for b in bindings), 'QWEN_STABILITY_TERMINAL_BINDINGS_MISSING')
    return {'phase': 'E4', 'accounted_slots': 15, 'terminal_observations': 14,
            'success': actual['technical_successes'], 'failed': actual['model_or_pipeline_failures'],
            'user_cancelled_no_retry': 1, 'other_evaluator_pending': True,
            'original_thirty_complete': False, 'cross_judge_comparison': False}


def reference_catalog(paths):
    """Same frozen resolve/whole-reference SR->SP->order; never parameter-filter."""
    require(paths['projection_script'] == Path(projection.__file__).resolve()
            and paths['step_scorer'] == Path(family.__file__).resolve()
            and paths['step_core'] == Path(family.core.__file__).resolve(), 'REFERENCE_IMPLEMENTATION_CHANGED')
    policy = j.read(paths['reference_policy'])
    require(policy.get('status') == 'frozen_before_confirmation_unsealing'
            and policy.get('threshold') == .7 and policy.get('encoder') == 'all-mpnet-base-v2'
            and policy.get('pool_rule') == 'unchanged_method_family_resolve'
            and policy.get('selection') == ['maximum_whole_reference_SR', 'maximum_same_reference_SP', 'earliest_frozen_candidate_order']
            and policy.get('prompt_rule') == 'all_resolved_complete_references_same_for_both_judges'
            and policy.get('parameter_based_candidate_exclusion') is False
            and policy.get('retain_all_eight_even_if_reference_pool_empty') is True
            and policy.get('scientific_task_applicability_confirmed') is False,
            'REFERENCE_POLICY_CHANGED')
    for key in ['reference_catalog', 'reference_projection', 'projection_script', 'method_family_policy', 'step_core', 'step_scorer', 'encoder_manifest']:
        require(policy.get(key) == bind(paths[key]), 'REFERENCE_POLICY_BINDING:' + key)
    require(j.read(paths['method_family_policy']) == family.policy(), 'METHOD_FAMILY_POLICY_DIFFERS')
    refs = j.read(paths['reference_catalog'])['references']
    shown = j.read(paths['reference_projection'])
    require(len(refs) == len(shown) == 11 and len({r['reference_id'] for r in refs}) == 11, 'ELEVEN_REFERENCE_CATALOG_REQUIRED')
    actual = []
    for ref in refs:
        p, audit = projection.project_reference(ref)
        require(projection.restore_reference(p, audit) == ref, 'REFERENCE_PROJECTION_NOT_LOSSLESS')
        actual.append(p)
    require(actual == shown, 'FROZEN_REFERENCE_PROJECTION_CHANGED')
    encoder = j.read(paths['encoder_manifest'])
    require(encoder.get('encoder') == 'all-mpnet-base-v2' and encoder.get('bindings'), 'ENCODER_MANIFEST_REQUIRED')
    verify_bindings(encoder['bindings'])
    actual_encoder_files = {str(p.resolve()) for p in (family.core.ASSETS / 'assets/all-mpnet-base-v2').rglob('*') if p.is_file()}
    require({str(descriptor(b)) for b in encoder['bindings']} == actual_encoder_files,
            'ENCODER_MANIFEST_MUST_BIND_ALL_ORIGINAL_ASSETS')
    source_bindings, _ = family.helpers.collect_source_bindings(refs)
    verify_bindings(policy['source_bindings'], [Path(p) for p in source_bindings])
    return refs, {r['reference_id']: r for r in shown}


def release_gate(release_path):
    """Public metadata only. Never hash/open the sealed descriptor at this gate."""
    release_path = public_path(release_path)
    release = j.read(release_path)
    require(release.get('status') == 'approved_for_confirmation_unsealing'
            and release.get('authorized_by') == 'root_agent' and release.get('root_reviewed') is True
            and isinstance(release.get('root_review_note'), str) and bool(release['root_review_note'].strip())
            and release.get('no_post_confirmation_tuning') is True, 'EXPLICIT_ROOT_FINAL_RELEASE_REQUIRED')
    require(set(release.get('assets', {})) == ASSETS, 'EXACT_RELEASE_ASSET_SET_REQUIRED')
    paths = {k: verify(v) for k, v in release['assets'].items()}
    require(paths['controller'] == Path(__file__).resolve() and paths['budget_adapter'] == Path(budget.__file__).resolve()
            and paths['authorization'] == budget.AUTH.resolve(), 'ACTUAL_CONTROLLER_BUDGET_BINDING')
    require(paths['sampling_summary'] == (SAMPLING / 'freeze_summary.json').resolve()
            and paths['sampling_policy'] == (SAMPLING / 'selection_policy.json').resolve(), 'FROZEN_NEW_SAMPLE_REQUIRED')
    final = j.read(paths['final_configuration'])
    require(final.get('status') == 'frozen_before_confirmation_unsealing'
            and final.get('selected_by') == 'root_agent' and final.get('scope') == SCOPE
            and final.get('planned_answers') == 8 and final.get('planned_observations') == 8
            and final.get('max_attempts') == 1 and final.get('repeats') == 1
            and final.get('no_post_confirmation_tuning') is True
            and final.get('models') == MODELS and final.get('decoder_schema') == 'source_specific_per_cell'
            and final.get('source_applicability') == 'conditional_nonformal', 'FINAL_CONFIGURATION_NOT_FROZEN')
    require(final.get('second_evaluator_pending') is True and final.get('cross_judge_goal_complete') is False
            and final.get('allowed_evaluators') == MODELS and final.get('candidate_version') == 'source_bound_extraction_v11',
            'EXPLICIT_QWEN_ONLY_SCOPE_AND_PENDING_SECOND_ARM')
    verify_bindings(final['bindings'], [p for k, p in paths.items() if k != 'final_configuration'])
    summary = j.read(paths['sampling_summary']); policy = j.read(paths['sampling_policy'])
    require(summary.get('selected_count') == 8 and summary.get('forbid_development_use') is True
            and summary.get('selected_bodies_released') is False and summary.get('excluded_selected_intersection') == 0
            and summary.get('historical_unregistered_body_exposure') == 'unknown'
            and summary.get('selection_policy') == bind(paths['sampling_policy'])
            and policy.get('selected_count') == 8 and policy.get('seed') == '20261010_round2', 'PROSPECTIVE_SAMPLE_FREEZE_CHANGED')
    sealed = release.get('sealed_metadata_manifest'); sealed_path = descriptor(sealed)
    require(sealed == summary.get('sealed_metadata_manifest')
            and sealed_path == (SAMPLING / 'sealed_metadata/selection_manifest.json').resolve(),
            'SEALED_MANIFEST_DESCRIPTOR_MISMATCH')
    # No stat/hash/open of sealed_path above or below this point in release_gate.
    current = budget.counts()
    require(current['phase']['confirmation'] == 0, 'CONFIRMATION_ALREADY_STARTED_REQUIRES_PREPARED_REPLAY')
    budget.guard('confirmation', 8, 600)
    ledger = {r['request_id']: r for r in current['requests']}
    stages = [verify_terminal_stage(paths, phase, final['candidate_version'], ledger) for phase in STAGES]
    facts = j.read(paths['development_facts'])
    require(facts.get('status') == 'complete' and facts.get('fixed_answers') == 5
            and facts.get('explicit_names_denominator') == 16 and facts.get('core_duration_denominator') == 31,
            'COMPLETE_FIXED_DEVELOPMENT_FACT_AUDIT_REQUIRED')
    verify_bindings(facts['inputs'], [paths['fact_checker'], paths['fact_checker_freeze']])
    require(re.fullmatch('source_bound_extraction_v[0-9]+', final['candidate_version']) is not None, 'CANDIDATE_VERSION_IDENTITY')
    checker_freeze = j.read(paths['fact_checker_freeze'])
    version_tag = final['candidate_version'].removeprefix('source_bound_extraction_')
    require(checker_freeze.get('status') == 'frozen_before_' + version_tag + '_generation'
            and checker_freeze.get('checker_sha256') == j.filehash(paths['fact_checker'])
            and checker_freeze.get('grounded_module') == bind(paths['converter'])
            and checker_freeze.get('independent_review') == bind(paths['independent_source_review']),
            'FROZEN_CHECKER_CANDIDATE_BINDING')
    for value in checker_freeze.values():
        if isinstance(value, dict) and set(value) == {'path', 'sha256'}:
            verify(value)
    source_review = j.read(paths['independent_source_review'])
    require(source_review.get('status') == 'pass' and source_review.get('module_sha256') == j.filehash(paths['converter']),
            'ACTUAL_INDEPENDENT_SOURCE_SOFTWARE_REVIEW_REQUIRED')
    development = j.read(paths['development_contract']); baseline = j.read(paths['baseline_science_contract'])
    contracts = j.read(paths['E4_contract']); e2 = j.read(paths['E2_contract'])
    require(set(contracts) == set(MODELS) and set(e2) == {MODELS[0]}, 'QWEN_ONLY_FIXED_MODEL_REQUIRED')
    stage_contracts = [('development', development), *[('E2:' + k, v) for k, v in e2.items()],
                       *[('E4:' + k, v) for k, v in contracts.items()]]
    for label, value in stage_contracts:
        require(all(value[k] == baseline[k] for k in SCIENCE_KEYS), 'STAGE_ORIGINAL_SCIENCE_CONTRACT_CHANGED:' + label)
        extraction = value['round2_extraction']
        require(extraction['module_sha256'] == j.filehash(paths['converter'])
                and extraction['score_adapter_sha256'] == j.filehash(paths['numeric_adapter'])
                and extraction['version'] == final['candidate_version'], 'STAGE_EXTRACTION_CONTRACT_DRIFT:' + label)
    configured = j.read(paths['model_config'])['models']
    require([x['name'] for x in configured] == MODELS, 'MODEL_CONFIGURATION_ORDER_CHANGED')
    config_index = {x['name']: x for x in configured}
    for name in MODELS:
        c = contracts[name]
        require(all(c[k] == baseline[k] == development[k] for k in SCIENCE_KEYS), 'ORIGINAL_SCIENCE_CONTRACT_CHANGED')
        require(c['round2_extraction']['module_sha256'] == j.filehash(paths['converter'])
                and c['round2_extraction']['score_adapter_sha256'] == j.filehash(paths['numeric_adapter'])
                and c['round2_extraction']['version'] == final['candidate_version'], 'FINAL_EXTRACTION_CONTRACT_DRIFT')
        require(len(c['models']) == 1 and c['models'][0]['name'] == name, 'MODEL_CONTRACT_IDENTITY')
        p = c['models'][0]['settings']
        require(p['transport_kind'] == 'ollama_loopback' and p['num_ctx'] == 98304
                and p['max_output_tokens'] == 8192 and p['temperature'] == 0 and p['timeout_seconds'] == 600,
                'FROZEN_GENERATION_SETTINGS')
        require((p['enable_thinking'] is False if name == MODELS[0] else p['enable_thinking'] is None), 'THINKING_OPTION_CHANGED')
        require(c['models'][0]['family'] == ('qwen' if name == MODELS[0] else 'llama'), 'MODEL_FAMILY_CHANGED')
        config = config_index[name]
        require(config['type'].lower() == 'ollama' and config['transport'] == 'http'
                and all(config[a] == p[b] for a, b in [('model_name', 'model'), ('model_digest', 'model_digest'),
                    ('host', 'host'), ('num_ctx', 'num_ctx'), ('max_tokens', 'max_output_tokens'), ('temperature', 'temperature')])
                and config['enable_thinking'] is p['enable_thinking'], 'MODEL_CONFIG_CONTRACT_MISMATCH')
    require(contracts[MODELS[0]]['models'] == development['models'] == e2[MODELS[0]]['models'], 'QWEN_ACTUAL_MODEL_CHANGED')
    require(j.read(paths['E4_plan'])['phase'] == 'E4', 'ACTUAL_E4_REQUIRED')
    refs, shown = reference_catalog(paths)
    return release, paths, final, stages, refs, shown


def check_selected_metadata(manifest):
    require(manifest.get('status') == 'frozen_metadata_only_not_released' and manifest.get('no_answer_text_included') is True
            and manifest.get('selected_count') == 8 and manifest.get('new_sample_must_not_enter_development') is True,
            'SEALED_METADATA_SCHEMA_CHANGED')
    rows = manifest['records']
    require([r['confirmation_id'] for r in rows] == IDS and len({r['answer_sha256'] for r in rows}) == 8,
            'FIXED_EIGHT_IDENTITIES_CHANGED')
    counts = Counter(int(r['question_id']) for r in rows)
    require(set(counts) == set(family.QIDS) and max(counts.values()) <= 2, 'SAMPLE_TASK_QUOTA_CHANGED')
    for r in rows:
        require(not r['excluded_reasons'] and r['documented_exclusion_pass'] is True
                and r['prior_compatible_conditional_reference_pool_nonempty'] is True, 'ORIGINAL_EXCLUSION_GATE_FAILED')
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', r['model']) is not None
                and r['answer_id'] == r['model'] + '__q' + str(int(r['question_id'])), 'UNSAFE_OR_CHANGED_ARCHIVE_IDENTITY')
        expected = rawsha('20261010_round2|' + r['answer_id'] + '|' + r['answer_sha256'])
        require(r['selection_hash'] == expected, 'SELECTION_KEY_CHANGED')
    return rows


def selected_record(path, qid):
    """Byte-scan an archive; JSON-decode only the one selected record."""
    data = Path(path).read_bytes(); found = []; skipped = 0
    for start, end in object_spans(data):
        prefix = data[start:min(end, start + 160)]
        match = re.search(rb'(?m)^\s*"question_id"\s*:\s*(\d+)\s*[,}]', prefix)
        require(match is not None, 'NO_SAFE_QID_PREFIX_STOP')
        if int(match.group(1)) != qid:
            skipped += 1
            continue
        value = json.loads(data[start:end])
        require(type(value['question_id']) is int and value['question_id'] == qid, 'SELECTED_QID_DRIFT')
        found.append((value, {'object_byte_start_inclusive': start, 'object_byte_end_exclusive': end,
                             'object_bytes_sha256': rawsha(data[start:end])}))
    require(len(found) == 1, 'SELECTED_ARCHIVE_RECORD_NOT_UNIQUE')
    value, location = found[0]
    return value, {'archive': {'path': str(Path(path).resolve()), 'sha256': rawsha(data)}, **location,
                   'decoded_selected_records': 1, 'skipped_without_JSON_decoding': skipped,
                   'nonselected_answer_bodies_JSON_decoded': 0}


def prepare_sources(release_path, out):
    """First sealed read follows full public gate plus immutable plan/receipt."""
    out = Path(out).resolve()
    require(out.is_relative_to(BASE) and not out.exists(), 'NEW_EMPTY_ROUND2_OUTPUT_REQUIRED')
    release, paths, final, stages, refs, byid = release_gate(release_path)
    plan = {'status': 'frozen_before_confirmation_metadata_unsealing', 'version': VERSION, 'phase': 'confirmation',
            'scope': SCOPE, 'planned_answers': 8, 'planned_observations': 8, 'max_attempts': 1, 'repeats': 1,
            'candidate_version': final['candidate_version'], 'root_release': bind(release_path),
            'frozen_inputs': list(release['assets'].values()), 'sealed_metadata_expected': release['sealed_metadata_manifest'],
            'all_statuses_retained': True, 'empty_reference_pool_does_not_replace_answer': True,
            'no_post_confirmation_tuning': True, 'formal_eligible': False, 'expert_returns': 0,
            'historical_unregistered_body_exposure': 'unknown', 'predecessor_terminal_metadata': stages,
            'second_evaluator_pending': True, 'cross_judge_goal_complete': False, 'allowed_evaluators': MODELS,
            'created_utc': j.now(), 'actual_command': [sys.executable, *sys.argv], 'new_model_requests': 0}
    save_once(out / 'source_release_plan.json', plan)
    save_once(out / 'unsealing_receipt.json', {'utc': j.now(), 'plan': bind(out / 'source_release_plan.json'),
        'release': bind(release_path), 'first_private_manifest_read_follows_this_receipt': True})
    sealed_path = verify(release['sealed_metadata_manifest'], public=False)
    records = check_selected_metadata(j.read(sealed_path))
    cases = []; accesses = []; selections = []; identities = []
    for r in records:
        qid = int(r['question_id']); aid = r['confirmation_id']
        source = ARCHIVES / ('from_' + r['model'] + '_1-shot.json')
        value, access = selected_record(source, qid)
        require(all(isinstance(value.get(k), str) and value[k].strip() for k in ['specific_question', 'model_response']), 'EMPTY_SELECTED_SOURCE')
        require(rawsha(value['model_response']) == r['answer_sha256'] and rawsha(value['specific_question']) == r['question_sha256'],
                'SELECTED_SOURCE_RAW_HASH_CHANGED')
        case = {'anonymous_answer_id': aid, 'case_id': aid, 'question_id': qid,
                'specific_question': value['specific_question'], 'model_response': value['model_response'],
                'answer_sha256': r['answer_sha256'], 'question_sha256': r['question_sha256'],
                'formal_eligible': False, 'expert_confirmation': None}
        method, declared, version, pool = family.resolve(case, refs)
        case['references'] = [copy.deepcopy(byid[x['reference_id']]) for x in pool]
        current_ids = [x['reference_id'] for x in pool]
        selections.append({'anonymous_answer_id': aid, 'comparison_method_id': method, 'declared_route_text': declared,
            'version_selection': version, 'prior_candidate_reference_ids': r['candidate_reference_ids'],
            'current_candidate_reference_ids': current_ids, 'current_candidate_count': len(pool),
            'candidate_pool_changed_since_sampling': current_ids != r['candidate_reference_ids'],
            'retained_regardless_of_current_pool': True, 'scientific_task_applicability_confirmed': False,
            'selection_policy': bind(paths['method_family_policy']), 'source_applicability': 'conditional_nonformal'})
        cases.append(case); accesses.append({'anonymous_answer_id': aid, **access})
        identities.append({'anonymous_answer_id': aid, 'original_answer_id': r['answer_id'], 'generating_model': r['model'],
            'question_id': qid, 'answer_sha256': r['answer_sha256'], 'question_sha256': r['question_sha256'], **access})
    require(len(cases) == 8 and [c['anonymous_answer_id'] for c in cases] == IDS, 'NO_POST_RELEASE_SAMPLE_REPLACEMENT')
    save_once(out / 'cases.json', {'cases': cases})
    save_once(out / 'reference_selections.json', selections)
    save_once(out / 'source_access_receipt.json', accesses)
    save_once(out / 'audit_identity' / 'source_identity_manifest.json', identities)
    save_once(out / 'source_preparation.json', {'status': 'eight_sources_exported_not_generated_runtime_not_implemented',
        'planned_observations': 8, 'actual_source_count': 8, 'new_model_requests': 0, 'new_embeddings': 0,
        'independence_claim': SCOPE, 'unknown_unregistered_historical_exposure': True,
        'current_reference_pools_empty': sum(not r['current_candidate_reference_ids'] for r in selections),
        'answer_replacements': 0, 'old_confirmation_reused': False,
        'bindings': [bind(out / n) for n in ['source_release_plan.json', 'unsealing_receipt.json', 'cases.json',
            'reference_selections.json', 'source_access_receipt.json', 'audit_identity/source_identity_manifest.json']]})
    return {'status': 'sources_exported_only', 'answers': 8, 'new_model_requests': 0, 'runtime_implemented': False}


def design():
    return {'version': VERSION, 'status': 'code_only_release_and_source_export_design_not_prepared',
        'scope': SCOPE, 'planned_answers': 8, 'planned_observations': 8, 'models': MODELS, 'max_attempts': 1,
        'second_evaluator_pending': True, 'cross_judge_goal_complete': False, 'confirmation_budget_cap_unchanged': 16,
        'source_schema': 'source_specific_per_cell_after_release', 'phase_budget': 'confirmation',
        'required_public_assets': sorted(ASSETS), 'release_status': 'approved_for_confirmation_unsealing',
        'read_order': ['verify_all_public_assets', 'verify_root_final_configuration', 'verify_actual_5_21_terminal_and_15_slot_qwen_chain',
            'verify_reference_policy_and_lossless_catalog', 'write_exclusive_plan_and_unsealing_receipt',
            'verify_and_read_original_sealed_metadata', 'decode_exact_selected_archive_objects', 'export_all_eight_without_replacement'],
        'runtime_implemented': False, 'source_reads_in_draft': 0, 'new_model_requests': 0,
        'remaining_before_generation': ['root final release', 'actual source export', 'deterministic .7 SR/SP with original encoder',
            'per-source schema/prompt and 8-cell Qwen-only matrix', 'actual local model metadata preflight',
            'root-reviewed serialized HTTP integration', 'separate root run authorization', 'runtime implementation review']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['draft', 'release-check', 'prepare-sources'])
    parser.add_argument('--release', type=Path, default=DESIGN / 'final_release.json')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    if args.action == 'draft':
        print(j.canonical(design()))
    elif args.action == 'release-check':
        release_gate(args.release)
        print(j.canonical({'status': 'public_release_gate_pass', 'sealed_reads': 0, 'new_model_requests': 0}))
    else:
        print(j.canonical(prepare_sources(args.release, args.out)))


if __name__ == '__main__':
    main()
