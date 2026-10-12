"""Independent complete-batch post-hoc component replay of original v11 E2/E4.

No real return may be opened before the original complete-batch analysis gate.
Fixed fresh matrices only: E2 21 cells/15 pairs; E4 5 x 2 x 3 = 30 cells.
Failures stay failures. Original v11 source semantics and partial module 4b9ab8
are mandatory. No model, embedding, source repair, retry or stability reanalysis.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import csv
import io
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_followup_runner_v11 as followup
import cce_partial_components_v1 as partial
from cce_posthoc_components_v9 import safe_reads
base = followup.base
ground = followup.grounded
j = followup.j
BASE = followup.BASE
OUT = BASE / 'explicit_posthoc_components_followup_v11'
BATCHES = {'E2': BASE / 'grounded_controls_v11', 'E4': BASE / 'grounded_stability_v11'}
PARTIAL_SHA = '4b9ab8d2462101349a6c5e91044fd83dc3f7add8d37732e8758341d1a863133e'
VERSION = 'posthoc-original-v11-followup-components-v1'
METRICS = followup.scoring.METRICS


def require(value, why):
    if not value: raise ValueError(why)


def exact(value, expected): return type(value) is int and value == expected
def bind(path): return {'path': str(Path(path).resolve()), 'sha256': j.filehash(path)}


def complete_metadata_gate(batch, phase):
    """Only public aggregate/plan metadata here: never open trial or raw files."""
    n = {'E2': 21, 'E4': 30}.get(phase)
    require(n is not None, 'PHASE_MUST_BE_E2_OR_E4')
    plan = j.read(batch / 'plan.json'); summary = j.read(batch / 'completion_summary.json')
    verification = j.read(batch / 'analysis_verification.json')
    require(plan['phase'] == summary['phase'] == phase and plan['status'] == 'frozen_before_generation', 'PHASE_OR_FROZEN_PLAN_CHANGED')
    require(summary['status'] == 'experiment_complete_not_scientific_validation'
        and exact(summary['planned_observations'], n) and exact(summary['actual_observations'], n)
        and exact(summary['pending'], 0), 'WHOLE_ORIGINAL_BATCH_NOT_TERMINAL')
    require(verification['status'] == 'pass' and verification['all_planned_terminal'] is True
        and exact(verification['planned_observations'], n) and exact(verification['terminal_observations'], n), 'ORIGINAL_COMPLETE_ANALYSIS_REQUIRED')
    require(exact(plan['planned_observations'], n) and exact(plan['planned_new_requests'], n)
        and exact(plan['planned_reused_observations'], 0) and plan['reuse_mode'] == 'fresh'
        and exact(plan['max_attempts'], 1), 'ONLY_CURRENT_FRESH_MATRIX_SUPPORTED')
    require(plan['candidate_version'] == ground.VERSION == 'source_bound_extraction_v11', 'ONLY_ORIGINAL_V11')
    return plan, summary, verification


def verify_science(contracts, phase):
    require(j.filehash(partial.__file__) == PARTIAL_SHA, 'REVIEWED_PARTIAL_ALGORITHM_CHANGED')
    names = [base.MODEL] if phase == 'E2' else followup.MODEL_NAMES
    require(set(contracts) == set(names), 'MODEL_SET_CHANGED')
    a, runner, _, registry = base.readonly_runtime()
    old = j.read(base.BASE_CONTRACT)
    for name in names:
        contract = contracts[name]; ext = contract['round2_extraction']
        require(ext['version'] == ground.VERSION and ext['module_sha256'] == j.filehash(ground.__file__)
            and ext['runner_sha256'] == j.filehash(followup.__file__)
            and ext['score_adapter_sha256'] == j.filehash(followup.scoring.__file__) and exact(ext['max_attempts'], 1), 'ORIGINAL_V11_CODE_CHAIN_CHANGED')
        require(len(contract['models']) == 1 and contract['models'][0]['name'] == name, 'MODEL_CONTRACT_IDENTITY')
        m = contract['models'][0]; public = m['settings']
        require(public['num_ctx'] == 98304 and public['max_output_tokens'] == 8192 and public['temperature'] == 0
            and public['timeout_seconds'] == 600 and public['transport_kind'] == 'ollama_loopback', 'ORIGINAL_MODEL_PARAMETERS_CHANGED')
        require(public['enable_thinking'] is (False if name == base.MODEL else None), 'ORIGINAL_THINKING_CONFIG_CHANGED')
        actual = j.contract(a, runner, registry, [{'name': name, 'family': m['family'], 'public': public}])
        require(all(actual[k] == contract[k] == old[k] for k in base.SCIENCE_KEYS), 'ORIGINAL_SCIENCE_DEPENDENCIES_CHANGED')
        require(actual['models'] == contract['models'], 'MODEL_METADATA_CHANGED')
    return {'original_converter': bind(ground.__file__), 'original_followup': bind(followup.__file__),
        'original_development_backend': bind(base.__file__), 'original_numeric_adapter': bind(followup.scoring.__file__),
        'partial_adapter': bind(partial.__file__), 'science_keys': base.SCIENCE_KEYS, 'service_queried': False}


def verify_cell(batch, phase, row, case, contract):
    require(row['reuse'] is None, 'REUSE_UNSUPPORTED_IN_CURRENT_FRESH_REPLAY')
    trial = followup.terminal_identity(batch, row)
    tid = row['planned_trial_id']; attempt = batch / 'run/attempts' / f'{tid}_1'
    require(trial['phase'] == phase and exact(trial['attempt'], 1) and exact(row['attempt'], 1), 'PHASE_ATTEMPT_IDENTITY')
    require(exact(trial['repeat_index'], row['repeat_index']) and exact(row['identity']['repeat_index'], row['repeat_index'])
        and type(row['repeat_index']) is int and row['repeat_index'] in (range(1) if phase == 'E2' else range(3)), 'TYPED_REPEAT_IDENTITY')
    require(trial['anonymous_answer_id'] == row['anonymous_answer_id'] == case['anonymous_answer_id']
        and trial['actual_request_made'] is True, 'ANONYMOUS_IDENTITY_OR_REQUEST_FLAG')
    payload = j.read(row['assets']['payload']['path'])
    expected = {'case_id': case['case_id'], 'input_sha256': j.digest({'question': case['specific_question'], 'question_id': case['question_id'],
        'protocol': case['model_response'], 'references': case['references']}), 'judge': row['judge'], 'repeat_index': row['repeat_index'],
        'contract_sha256': j.digest(contract), 'payload_sha256': j.digest(payload), 'round_id': followup.budget.ROUND, 'phase': phase}
    require(row['identity'] == expected and trial['identity'] == expected, 'COMPLETE_INPUT_SCIENCE_MODEL_IDENTITY')
    receipt_path = attempt / 'request_receipt.json'; receipt = j.read(receipt_path)
    require(receipt['event'] == 'request_started' and exact(receipt['attempt'], 1) and receipt['phase'] == phase
        and receipt['round_id'] == followup.budget.ROUND and receipt['model'] == row['judge']
        and receipt['authorization_sha256'] == followup.budget.AUTH_SHA
        and receipt['request_id'] == j.digest({'trial_id': tid, 'attempt': 1}), 'ACTUAL_PHASE_MODEL_REQUEST_RECEIPT')
    require(type(receipt['package_request_index']) is int, 'PACKAGE_INDEX_TYPE')
    base.verify_required(trial['bound_artifacts'], [receipt_path, attempt / 'http_request_payload.json', attempt / 'prompt.txt'])
    doc = j.read(row['assets']['source_document']['path']); public = contract['models'][0]['settings']
    prompt = Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
    require(prompt == ground.make_prompt(case, doc), 'ORIGINAL_V11_FULL_PROMPT_REPLAY')
    require((attempt / 'prompt.txt').read_bytes() == prompt.encode('utf8'), 'TRANSMITTED_PROMPT_BYTES')
    require(j.read(attempt / 'http_request_payload.json') == payload == base.payload_for(prompt, ground.schema_for_document(doc), public), 'ORIGINAL_HTTP_PAYLOAD')
    e = trial['evaluation']; meta = e['grounded_extraction_v11']
    require(e['technical_status'] == ('SUCCESS' if trial['status'] == 'success' else 'FAILED'), 'TECHNICAL_STATUS_CONFLICT')
    require(meta['raw_return_modified'] is False and meta['legacy_parser_fallback_used'] is False, 'RAW_MODIFICATION_OR_FALLBACK')
    failure = None
    if trial['status'] == 'failed':
        base.verify_required(trial['bound_artifacts'], [attempt / 'failure.json']); failure = j.read(attempt / 'failure.json')
        require(failure in meta['conversion_errors'] and failure['stage'] == e['failure_stage'], 'ORIGINAL_FAILURE_RECORD')
        require(e['metrics'] == followup.scoring.derive({}, row['step'], False), 'ORIGINAL_FAILED_NA_CHANGED')
    else: require(e['failure_stage'] is None, 'SUCCESS_WITH_FAILURE')
    provider_path = attempt / 'provider_response.json'; raw_path = attempt / 'raw_source_bound_content.txt'
    provider = None; raw = None; sidecar = None
    if provider_path.exists():
        base.verify_required(trial['bound_artifacts'], [provider_path]); provider = j.read(provider_path)
    if raw_path.exists():
        sidepath = attempt / 'raw_source_bound_receipt.json'; base.verify_required(trial['bound_artifacts'], [raw_path, sidepath])
        raw = raw_path.read_bytes().decode('utf8'); sidecar = j.read(sidepath)
        require(isinstance(provider, dict) and provider.get('response') == raw, 'PROVIDER_RAW_TEXT')
        require(sidecar['raw_response_sha256'] == ground.rawsha(raw) and sidecar['raw_text_file_sha256'] == j.filehash(raw_path)
            and sidecar['source_document'] == row['assets']['source_document'] and sidecar['raw_text_unchanged'] is True, 'RAW_SIDECAR_SOURCE_IDENTITY')
    elif isinstance(provider, dict): require(not isinstance(provider.get('response'), str), 'UNCOMMITTED_PROVIDER_RAW')
    first = {'status': 'not_applicable_success'}
    if failure and failure['stage'] != 'PROVIDER_TRANSPORT':
        stage = 'PROVIDER_COMPLETION'; reproduced = None
        try:
            base.validate_provider(provider, public); stage = 'SOURCE_BOUND_CONVERSION'; cv = ground.convert(raw, doc)
            stage = 'ORIGINAL_OFFLINE_NUMERIC_SCORING'
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                followup.scoring.score_conversion(case, cv, followup.BACKEND, row['step'])
        except Exception as exc: reproduced = {'stage': stage, 'type': type(exc).__name__, 'reason': str(exc)}
        require(reproduced is not None and all(reproduced[k] == failure[k] for k in reproduced), 'ORIGINAL_FIRST_FAILURE_NOT_REPRODUCED')
        first = {'status': 'original_first_failure_reproduced', **reproduced}
    elif failure: first = {'status': 'transport_not_reinvoked_original_bound_failure_retained', 'stage': failure['stage']}
    if trial['status'] == 'success':
        require(raw is not None and provider is not None, 'SUCCESS_MISSING_RAW')
        base.validate_provider(provider, public); cv = ground.convert(raw, doc)
        base.verify_required(trial['bound_artifacts'], [attempt / 'source_bound_conversion.json', attempt / 'numeric_result.json'])
        require(cv == meta['conversion'] == j.read(attempt / 'source_bound_conversion.json'), 'ORIGINAL_SUCCESS_CONVERSION')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            numeric = followup.scoring.score_conversion(case, cv, followup.BACKEND, row['step'])
        require(numeric == e['numeric_result'] == j.read(attempt / 'numeric_result.json') and numeric['metrics'] == e['metrics'], 'ORIGINAL_SUCCESS_NUMERIC_RESULT')
    envelope = None if raw is None else {'upstream_technical_status': trial['status'], 'upstream_failure': copy.deepcopy(meta['conversion_errors']),
        'actual_request_made': trial['actual_request_made'], 'planned_identity': row['identity'], 'trial_identity': trial['identity'],
        'request_receipt': receipt, 'http_request_payload': j.read(attempt / 'http_request_payload.json'), 'expected_http_payload': payload,
        'expected_public_model': public, 'raw_response_sha256': sidecar['raw_response_sha256'], 'source_document_sha256': j.digest(doc), 'provider_response': provider}
    return {'trial': trial, 'raw': raw, 'doc': doc, 'envelope': envelope, 'first_failure_replay': first,
        'provenance': [bind(batch / 'run/trials' / f'{tid}.json'), *trial['bound_artifacts'], *row['assets'].values(), *row['step']['provenance']]}


def verify_batch(batch, phase, software_only=False):
    batch = Path(batch).resolve()
    require(software_only or batch == BATCHES[phase].resolve(), 'ONLY_FROZEN_V11_FOLLOWUP_PATH')
    plan, summary, verification = complete_metadata_gate(batch, phase)
    # No trial/raw access above this line. Original gates execute only now.
    base.verify_required(verification['bindings'], [batch / 'plan.json', batch / 'matrix.json', batch / 'observations.json', batch / 'completion_summary.json'])
    base.verify_bindings(summary['bound_observations'])
    original = followup.validate(batch); require(original[0] == plan, 'PLAN_CHANGED_DURING_READ')
    _, cases, matrix, contracts = original; science = verify_science(contracts, phase)
    base.verify_required(plan['frozen_inputs'], [followup.__file__, base.__file__, ground.__file__, followup.scoring.__file__,
        batch / 'cases.json', batch / 'step_inputs.json', batch / 'pairs.json', batch / 'matrix.json', batch / 'expected_contract.json'])
    expected_cases, expected_steps, expected_pairs = followup.checked_inputs(phase)
    require(cases == expected_cases and j.read(batch / 'step_inputs.json') == expected_steps and j.read(batch / 'pairs.json') == expected_pairs,
        'ORIGINAL_SOURCE_STEP_OR_PAIR_SELECTION_CHANGED')
    names = [base.MODEL] if phase == 'E2' else followup.MODEL_NAMES
    expected_cells = [(c['case_id'], name, repeat) for c in cases for name in names for repeat in range(1 if phase == 'E2' else 3)]
    require([(r['case_id'], r['judge'], r['repeat_index']) for r in matrix] == expected_cells and all(r['reuse'] is None for r in matrix), 'FULL_ORDERED_FRESH_MATRIX')
    index = {c['case_id']: c for c in cases}; checked = [verify_cell(batch, phase, r, index[r['case_id']], contracts[r['judge']]) for r in matrix]
    observations = j.read(batch / 'observations.json'); require(len(observations) == len(matrix), 'ORIGINAL_ANALYSIS_DENOMINATOR')
    for old, row, record in zip(observations, matrix, checked):
        t = record['trial']; require(old['trial_id'] == t['trial_id'] and old['case_id'] == row['case_id']
            and old['anonymous_answer_id'] == row['anonymous_answer_id'] and old['judge'] == row['judge']
            and exact(old['repeat_index'], row['repeat_index']) and old['status'] == t['status'] and old['metrics'] == t['evaluation']['metrics'], 'OLD_ANALYSIS_CELL_IDENTITY')
    require(sum(r['trial']['status'] == 'success' for r in checked) == summary['technical_successes'], 'ORIGINAL_STATUS_COUNT')
    if phase == 'E2':
        replayed_pairs = followup.pair_results(observations, expected_pairs, expected_steps)
        require(replayed_pairs == j.read(batch / 'per_pair.json'), 'ORIGINAL_PAIR_ANALYSIS_CHANGED')
    paths = ['plan.json', 'matrix.json', 'expected_contract.json', 'cases.json', 'pairs.json', 'step_inputs.json', 'analysis_verification.json', 'completion_summary.json', 'observations.json']
    if phase == 'E2': paths.append('per_pair.json')
    return {'phase': phase, 'batch': str(batch), 'plan': plan, 'cases': cases, 'matrix': matrix, 'contracts': contracts,
        'pairs': expected_pairs, 'checked': checked, 'science': science, 'software_only': software_only,
        'bindings': [bind(batch / p) for p in paths]}


def pair_comparisons(cells, pairs):
    bycase = {x['case_id']: x for x in cells}; rows = []
    for pair in pairs:
        a, b = (bycase[pair[k]] for k in ['baseline_case_id', 'variant_case_id'])
        same = all(a[k] == b[k] and a[k] is not None for k in ['judge', 'contract_sha256', 'question_sha256', 'references_sha256', 'step_config_sha256', 'partial_adapter_sha256'])
        require(same, 'PAIRED_POSTHOC_CONFIGURATION_CHANGED')
        for m in METRICS:
            av, bv = a['posthoc_metrics'][m], b['posthoc_metrics'][m]
            oa, ob = a['original_metrics'][m], b['original_metrics'][m]
            both_original = a['original_status'] == b['original_status'] == 'success'
            old_ok = followup.scoring.finite(oa) and followup.scoring.finite(ob) and (both_original or m in ['sr', 'sp'])
            new_ok = followup.scoring.finite(av) and followup.scoring.finite(bv)
            rows.append({'pair_id': pair['pair_id'], 'condition': pair['condition'], 'question_id': pair['question_id'], 'metric': m,
                'baseline_case_id': a['case_id'], 'variant_case_id': b['case_id'], 'original_baseline_status': a['original_status'],
                'original_variant_status': b['original_status'], 'both_original_technical_success': both_original,
                'same_adapter_and_frozen_pair_configuration': same, 'original_baseline_value': oa, 'original_variant_value': ob,
                'original_pair_delta': ob-oa if old_ok else None, 'posthoc_baseline_value': av, 'posthoc_variant_value': bv,
                'posthoc_component_pair_available': new_ok, 'posthoc_pair_delta': bv-av if new_ok else None,
                'failed_observation_promoted': False, 'new_model_observation': False, 'scientific_accuracy_established': False})
    require(len(rows) == 15 * len(METRICS), 'ALL_FIFTEEN_PAIRS_AND_METRICS_REQUIRED')
    return rows


def write_table(out, name, rows):
    j.save(out / (name + '.json'), rows)
    if rows:
        with (out / (name + '.csv')).open('w', encoding='utf8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader()
            for r in rows: w.writerow({k: j.canonical(v) if isinstance(v, (dict, list)) else v for k, v in r.items()})


def replay(verified, out):
    out = Path(out).resolve(); require(not out.exists(), 'REFUSE_OVERWRITE_POSTHOC_REPLAY')
    index = {c['case_id']: c for c in verified['cases']}; cells = []; full = []; comparison = []
    protected = [*verified['bindings'], *verified['plan']['frozen_inputs']]
    for row, checked in zip(verified['matrix'], verified['checked']):
        case = index[row['case_id']]; t = checked['trial']; old = t['evaluation']['metrics']; protected += checked['provenance']
        if checked['envelope'] is None:
            audit = {'shared_gate': {'pass': False, 'reason': 'NO_COMMITTED_RAW'}, 'whole_technical_success': False,
                'metrics': followup.scoring.derive({}, row['step'], False), 'raw_content_preserved': None}
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                audit = partial.audit_components(checked['raw'], checked['doc'], case, base, row['step'], checked['envelope'])
        require(not audit['whole_technical_success'] or t['status'] == 'success', 'FAILED_TRIAL_PROMOTED')
        if t['status'] == 'success': require(all(followup.scoring.same(old[m], audit['metrics'][m]) for m in METRICS), 'SUCCESS_SIXTEEN_ORIGINAL_VALUES_CHANGED')
        cell = {'cell_id': row['cell_id'], 'anonymous_answer_id': row['anonymous_answer_id'], 'case_id': row['case_id'], 'trial_id': t['trial_id'],
            'judge': row['judge'], 'repeat_index': row['repeat_index'], 'phase': verified['phase'], 'original_status': t['status'],
            'original_failure_stage': t['evaluation']['failure_stage'], 'original_metrics': old, 'posthoc_metrics': audit['metrics'],
            'contract_sha256': row['identity']['contract_sha256'], 'question_sha256': row['step']['question_sha256'],
            'references_sha256': row['step']['references_sha256'], 'step_config_sha256': row['step']['step_config_sha256'],
            'partial_adapter_sha256': PARTIAL_SHA, 'new_model_observation': False, 'failed_observation_promoted': False}
        cells.append(cell); full.append({'cell_id': row['cell_id'], 'first_failure_replay': checked['first_failure_replay'],
            'original_status': t['status'], 'provenance': checked['provenance'], 'audit': audit})
        for m in METRICS:
            v = audit['metrics'][m]; comparison.append({'cell_id': row['cell_id'], 'anonymous_answer_id': row['anonymous_answer_id'],
                'judge': row['judge'], 'repeat_index': row['repeat_index'], 'metric': m, 'original_status': t['status'],
                'original_value': old[m], 'posthoc_component_value': v, 'newly_available': old[m] is None and followup.scoring.finite(v),
                'unchanged': followup.scoring.same(old[m], v), 'new_model_observation': False})
    pair_rows = pair_comparisons(cells, verified['pairs']) if verified['phase'] == 'E2' else []
    unique = {r['path']: r for r in protected}; base.verify_bindings(list(unique.values()))
    out.mkdir(parents=True); write_table(out, 'cells', cells); write_table(out, 'component_comparison', comparison)
    j.save(out / 'full_component_audits.json', full)
    if verified['phase'] == 'E2': write_table(out, 'pair_component_comparison', pair_rows)
    summary = {'status': 'complete_posthoc_component_diagnostic_not_new_evaluation', 'version': VERSION, 'phase': verified['phase'],
        'software_only': verified['software_only'], 'denominator': len(cells), 'metric_rows': len(comparison),
        'original_successes': sum(c['original_status'] == 'success' for c in cells), 'original_failures': sum(c['original_status'] == 'failed' for c in cells),
        'all_successful_original_sixteen_metrics_unchanged': True, 'all_failed_statuses_retained': True,
        'newly_available_counts': {m: sum(r['newly_available'] for r in comparison if r['metric'] == m) for m in METRICS},
        'planned_pairs': 15 if verified['phase'] == 'E2' else None, 'pair_metric_rows': len(pair_rows),
        'E4_stability_statistics_recomputed': False, 'new_model_requests': 0, 'scientific_accuracy_established': False,
        'formal_eligible': False, 'expert_confirmed': False, 'original_v11_source_policy_retained': True,
        'protected_bindings': list(unique.values()), 'science': verified['science'],
        'implementation_bindings': [bind(__file__), bind(partial.__file__)], 'actual_command': [sys.executable, *sys.argv]}
    j.save(out / 'summary.json', summary); return summary


def review_gate(path, phase):
    approval = j.read(path); batch = BATCHES[phase]
    require(approval.get('status') == 'approved_for_explicit_posthoc_v11_followup_components'
        and approval.get('reviewed_by') == 'root_agent' and approval.get('phase') == phase
        and exact(approval.get('new_model_requests'), 0) and approval.get('original_status_preserved') is True, 'ROOT_POSTHOC_REVIEW_REQUIRED')
    base.verify_required(approval['bindings'], [Path(__file__), Path(partial.__file__), OUT / 'draft/software_verification.json',
        batch / 'plan.json', batch / 'analysis_verification.json', batch / 'matrix.json', batch / 'expected_contract.json', batch / 'completion_summary.json'])


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['describe', 'replay'])
    p.add_argument('--phase', choices=['E2', 'E4'], required=True); p.add_argument('--review-approval', type=Path); p.add_argument('--out', type=Path)
    a = p.parse_args(); safe_reads()
    if a.action == 'describe':
        print(j.canonical({'version': VERSION, 'phase': a.phase, 'batch': str(BATCHES[a.phase]), 'new_model_requests': 0, 'replay_executed': False})); return
    require(a.review_approval is not None, 'ROOT_POSTHOC_REVIEW_REQUIRED'); review_gate(a.review_approval, a.phase)
    out = (a.out or OUT / a.phase / 'actual_replay').resolve(); require(out.is_relative_to(OUT.resolve()), 'INDEPENDENT_OUTPUT_NAMESPACE')
    result = replay(verify_batch(BATCHES[a.phase], a.phase), out)
    print(j.canonical({k: result[k] for k in ['phase', 'denominator', 'original_successes', 'original_failures', 'newly_available_counts', 'new_model_requests']}))


if __name__ == '__main__': main()
