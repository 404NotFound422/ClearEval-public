"""Public v11 input loader and offline operation-coverage scope replay.

Only development five, the complete E2 21 and the Qwen 15-slot continuation
are accessible. No generation, repair of failed raw, or confirmation access.
load_public_records() is also the input iterator for a separately versioned
unified converter; returning a failure's committed raw does not promote it.
"""
from __future__ import annotations
import argparse, contextlib, copy, csv, io, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_operation_coverage_scope_diagnostic_v1 as scope
import cce_posthoc_components_followup_v11 as chain
import cce_qwen_only_stability_continuation_v1 as continuation

base, g, j, scoring = scope.base, scope.g, scope.j, scope.scoring
OUT = base.BASE / 'operation_coverage_scope_batch_v1'
QWEN_ANALYSIS = base.BASE / 'grounded_stability_qwen_only_analysis_v1/actual_01'
SCOPE_SHA = '71cbce69df5cf9dcdb2d12dd31daa3acc98ca2827ff1943da2380a6448be1626'
VERSION = 'public-v11-operation-coverage-batch-v1'
require, bind = scope.require, scope.bind


def unique_bindings(rows):
    indexed = {}
    for r in rows:
        p = str(Path(r['path']).resolve())
        require(p not in indexed or indexed[p]['sha256'] == r['sha256'], 'CONFLICTING_INPUT_BINDINGS')
        indexed[p] = {'path': p, 'sha256': r['sha256']}
    return list(indexed.values())


def common_record(cohort, case, row, checked, bindings):
    t = checked['trial']; e = t['evaluation']; meta = e['grounded_extraction_v11']
    return {'cohort': cohort, 'case': case, 'doc': checked['doc'], 'step': row['step'],
        'raw': checked['raw'], 'original_conversion': meta['conversion'],
        'original_numeric': e['numeric_result'], 'original_metrics': e['metrics'],
        'status': t['status'], 'failure_stage': e['failure_stage'],
        'failure_records': copy.deepcopy(meta['conversion_errors']),
        'cell_id': row.get('cell_id', row['anonymous_answer_id']), 'trial_id': t['trial_id'],
        'anonymous_answer_id': row['anonymous_answer_id'], 'judge': row['identity']['judge'],
        'repeat_index': row['identity']['repeat_index'], 'source_row': row,
        'paths': unique_bindings([*bindings, *checked['provenance']]),
        'first_failure_replay': checked.get('first_failure_replay'),
        'original_status_preserved': True, 'new_model_observation': False}


def development_records():
    out = base.DEFAULT_OUT
    summary = j.read(out / 'completion_summary.json'); verification = j.read(out / 'analysis_verification.json')
    require(summary['status'] == 'experiment_complete_not_scientific_validation'
        and summary['planned_observations'] == summary['actual_observations'] == 5
        and summary['pending'] == 0 and verification['status'] == 'pass'
        and verification['all_five_terminal'] is True, 'DEVELOPMENT_COMPLETE_ANALYSIS_REQUIRED')
    base.verify_required(verification['bindings'], [out / n for n in
        ['plan.json', 'matrix.json', 'per_answer.json', 'completion_summary.json']])
    base.verify_bindings(summary['bound_observations'])
    plan, cases, matrix, contract = base.validate(out)
    require(g.VERSION == plan['candidate_version'] == 'source_bound_extraction_v11', 'ORIGINAL_V11_REQUIRED')
    ext = contract['round2_extraction']
    require(ext['module_sha256'] == j.filehash(g.__file__) and ext['runner_sha256'] == j.filehash(base.__file__)
        and ext['score_adapter_sha256'] == j.filehash(scoring.__file__) and ext['version'] == g.VERSION,
        'ORIGINAL_DEVELOPMENT_CODE_CHAIN')
    a, runner, _, registry = base.readonly_runtime(); m = contract['models'][0]; public = m['settings']
    actual = j.contract(a, runner, registry, [{'name': m['name'], 'family': m['family'], 'public': public}])
    old = j.read(base.BASE_CONTRACT)
    require(all(actual[k] == contract[k] == old[k] for k in base.SCIENCE_KEYS)
        and actual['models'] == contract['models'] and m['name'] == base.MODEL, 'ORIGINAL_DEVELOPMENT_SCIENCE')
    bound = unique_bindings([*plan['frozen_inputs'], *summary['bound_observations'],
        *[bind(out / n) for n in ['plan.json', 'matrix.json', 'expected_contract.json', 'cases.json',
            'step_inputs.json', 'completion_summary.json', 'analysis_verification.json', 'per_answer.json']]])
    old_rows = j.read(out / 'per_answer.json'); records = []
    require(len(old_rows) == len(matrix) == len(cases) == 5, 'DEVELOPMENT_FIVE_DENOMINATOR')
    for case, row, observed in zip(cases, matrix, old_rows):
        t = base.terminal_identity(out, row); tid = row['planned_trial_id']; attempt = out / 'run/attempts' / f'{tid}_1'
        payload = j.read(row['assets']['payload']['path'])
        identity = {'case_id': case['case_id'], 'input_sha256': j.digest({'question': case['specific_question'],
            'question_id': case['question_id'], 'protocol': case['model_response'], 'references': case['references']}),
            'judge': base.MODEL, 'repeat_index': 0, 'contract_sha256': j.digest(contract),
            'payload_sha256': j.digest(payload), 'round_id': base.budget.ROUND}
        require(row['identity'] == t['identity'] == identity and type(t['attempt']) is int and t['attempt'] == 1
            and type(t['identity']['repeat_index']) is int and t['actual_request_made'] is True
            and t['anonymous_answer_id'] == row['anonymous_answer_id'] == case['anonymous_answer_id'], 'DEV_COMPLETE_IDENTITY')
        receipt = j.read(attempt / 'request_receipt.json')
        require(receipt['phase'] == 'development' and receipt['event'] == 'request_started'
            and type(receipt['attempt']) is int and receipt['attempt'] == 1
            and receipt['round_id'] == base.budget.ROUND and receipt['authorization_sha256'] == base.budget.AUTH_SHA,
            'DEV_RECEIPT_PHASE_IDENTITY')
        doc = j.read(row['assets']['source_document']['path']); prompt = Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
        require(prompt == g.make_prompt(case, doc) and (attempt / 'prompt.txt').read_bytes() == prompt.encode('utf8'), 'DEV_ACTUAL_PROMPT_BYTES')
        require(payload == base.payload_for(prompt, g.schema_for_document(doc), public)
            == j.read(attempt / 'http_request_payload.json'), 'DEV_ACTUAL_HTTP_PAYLOAD')
        base.verify_required(t['bound_artifacts'], [attempt / n for n in ['request_receipt.json', 'prompt.txt',
            'http_request_payload.json', 'provider_response.json', 'raw_source_bound_content.txt', 'raw_source_bound_receipt.json']])
        provider = j.read(attempt / 'provider_response.json'); raw = (attempt / 'raw_source_bound_content.txt').read_bytes().decode('utf8')
        sidecar = j.read(attempt / 'raw_source_bound_receipt.json')
        require(provider.get('response') == raw and sidecar['raw_response_sha256'] == g.rawsha(raw)
            and sidecar['raw_text_file_sha256'] == j.filehash(attempt / 'raw_source_bound_content.txt')
            and sidecar['source_document'] == row['assets']['source_document'] and sidecar['raw_text_unchanged'] is True,
            'DEV_PROVIDER_RAW_SOURCE_CHAIN')
        e = t['evaluation']; meta = e['grounded_extraction_v11']
        require(meta['raw_return_modified'] is False and meta['legacy_parser_fallback_used'] is False, 'DEV_RAW_NOT_REPAIRED')
        # This fixed public v11 development batch has five actual successes.
        require(t['status'] == 'success' and e['technical_status'] == 'SUCCESS' and e['failure_stage'] is None, 'DEV_ACTUAL_SUCCESS_REQUIRED')
        base.validate_provider(provider, public)
        cv = g.convert(raw, doc)
        base.verify_required(t['bound_artifacts'], [attempt / 'source_bound_conversion.json', attempt / 'numeric_result.json'])
        require(cv == meta['conversion'] == j.read(attempt / 'source_bound_conversion.json'), 'DEV_ORIGINAL_CONVERSION_REPLAY')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            numeric = scoring.score_conversion(case, cv, base.BACKEND, row['step'])
        require(numeric == e['numeric_result'] == j.read(attempt / 'numeric_result.json') and numeric['metrics'] == e['metrics'], 'DEV_ORIGINAL_NUMERIC_REPLAY')
        require(observed['trial_id'] == tid and observed['status'] == t['status'] and observed['metrics'] == e['metrics'], 'DEV_OLD_ANALYSIS_MATCH')
        checked = {'trial': t, 'raw': raw, 'doc': doc, 'provenance': [bind(out / 'run/trials' / (tid + '.json')),
            *t['bound_artifacts'], *row['assets'].values(), *row['step']['provenance']]}
        records.append(common_record('development', case, row, checked, bound))
    return records


def e2_records():
    verified = chain.verify_batch(chain.BATCHES['E2'], 'E2')
    cases = {c['case_id']: c for c in verified['cases']}
    bound = [*verified['bindings'], *verified['plan']['frozen_inputs']]
    return [common_record('E2', cases[r['case_id']], r, c, bound)
        for r, c in zip(verified['matrix'], verified['checked'])]


def qwen_records():
    out = continuation.DEFAULT_OUT; summary = j.read(QWEN_ANALYSIS / 'completion_summary.json')
    verification = j.read(QWEN_ANALYSIS / 'analysis_verification.json')
    require(summary['status'] == 'all_slots_accounted_not_scientific_validation' and summary['planned_observations'] == 15
        and summary['technical_successes'] == 14 and summary['user_cancelled_no_retry'] == 1
        and summary['pending'] == 0 and verification['status'] == 'pass'
        and verification['all_slots_accounted'] is True, 'QWEN_ACTUAL_FOURTEEN_AND_CANCELLED_ANALYSIS_REQUIRED')
    base.verify_required(verification['bindings'], [QWEN_ANALYSIS / n for n in ['observations.json', 'completion_summary.json']])
    base.verify_bindings(summary['bound_actual_artifacts'])
    plan, cases, items, contract = continuation.validate(out)
    require(len(items) == 15, 'QWEN_FIFTEEN_DENOMINATOR')
    bound = unique_bindings([*plan['frozen_inputs'], *summary['bound_actual_artifacts'],
        *[bind(QWEN_ANALYSIS / n) for n in ['completion_summary.json', 'analysis_verification.json', 'observations.json']]])
    indexed = {c['case_id']: c for c in cases}; observations = j.read(QWEN_ANALYSIS / 'observations.json')
    observed = {r['trial_id']: r for r in observations}; require(len(observed) == len(items), 'QWEN_OBSERVATION_IDENTITY')
    records = []
    for item in items:
        row = item['source_cell']; case = indexed[row['case_id']]; old = observed[row['planned_trial_id']]
        location = Path(plan['source_out']) if item['disposition'] != 'unrequested_eligible' else out
        if item['disposition'] == 'user_cancelled_no_retry':
            require(old['status'] == 'user_cancelled_no_retry' and not (location / 'run/trials' / (row['planned_trial_id'] + '.json')).exists(), 'CANCELLED_STATUS_CHANGED')
            doc = j.read(row['assets']['source_document']['path'])
            metrics = {m: old[m] for m in scoring.METRICS}
            require(metrics == scoring.derive({}, row['step'], False), 'CANCELLED_STEPS_OR_NA_CHANGED')
            record = {'cohort': 'Qwen_repeats', 'case': case, 'doc': doc, 'step': row['step'], 'raw': None,
                'original_conversion': None, 'original_numeric': None, 'original_metrics': metrics,
                'status': 'user_cancelled_no_retry', 'failure_stage': None, 'failure_records': [],
                'cell_id': row['cell_id'], 'trial_id': row['planned_trial_id'], 'anonymous_answer_id': row['anonymous_answer_id'],
                'judge': row['judge'], 'repeat_index': row['repeat_index'], 'source_row': row,
                'paths': bound, 'original_status_preserved': True, 'new_model_observation': False}
        else:
            checked = chain.verify_cell(location, 'E4', row, case, contract)
            require(old['status'] == checked['trial']['status'] == 'success'
                and all(scoring.same(old[m], checked['trial']['evaluation']['metrics'][m]) for m in scoring.METRICS), 'QWEN_ORIGINAL_ANALYSIS_MATCH')
            record = common_record('Qwen_repeats', case, row, checked, bound)
        record['continuation_disposition'] = item['disposition']; records.append(record)
    return records


def load_public_records(cohorts=('development', 'E2', 'Qwen_repeats')):
    """Return verified source inputs, including failed raw and an uncooked cancel.

    No root confirmation, secret sample or expert contents are read. This
    function does not apply either a label correction or the scope correction.
    Every successful original conversion and full numeric object is replayed.
    """
    require(j.filehash(scope.__file__) == SCOPE_SHA, 'LOCKED_SCOPE_IMPLEMENTATION_CHANGED')
    require(len(cohorts) == len(set(cohorts)) and set(cohorts) <= {'development', 'E2', 'Qwen_repeats'}, 'PUBLIC_COHORTS_ONLY')
    chain.safe_reads()
    result = []
    loaders = {'development': development_records, 'E2': e2_records, 'Qwen_repeats': qwen_records}
    for name in cohorts:
        result.extend(loaders[name]())
    require(len({r['trial_id'] for r in result}) == len(result), 'DUPLICATE_PUBLIC_TRIAL')
    base.verify_bindings(unique_bindings([p for r in result for p in r['paths']]))
    return result


def write_table(out, stem, rows):
    scope.save_once(out / (stem + '.json'), rows)
    if rows:
        with (out / (stem + '.csv')).open('x', encoding='utf8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader()
            for row in rows: w.writerow({k: j.canonical(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def replay(out):
    require(not out.exists(), 'NEW_OUTPUT_ONLY')
    out.mkdir(parents=True)
    scope.save_once(out / 'execution_intent.json', {'actual_command': [sys.executable, *sys.argv],
        'script': bind(__file__), 'scope_script': bind(scope.__file__), 'new_model_requests': 0})
    records = load_public_records(); cells = []; metric_rows = []; changed = []; errors = []
    for r in records:
        cell = {k: r[k] for k in ['cohort', 'cell_id', 'anonymous_answer_id', 'trial_id', 'judge', 'repeat_index', 'status', 'failure_stage']}
        cell.update(original_metrics=r['original_metrics'], posthoc_metrics=copy.deepcopy(r['original_metrics']),
            original_time_hours=None, posthoc_time_hours=None, original_time_issues=[], posthoc_time_issues=[],
            changed_record_count=0, changed_metrics=[], replay_status='original_non_success_retained',
            error=None, original_failure_preserved=r['status'] != 'success')
        if r['status'] == 'success':
            try:
                result = scope.diagnose(r['raw'], r['doc'], r['case'], r['step'], r['original_conversion'], r['original_numeric'])
                folder = out / 'cells' / r['cohort'] / r['cell_id']
                scope.write_result(folder, result, r['paths'])
                cell.update({k: result['summary'][k] for k in ['original_time_hours', 'posthoc_time_hours',
                    'original_time_issues', 'posthoc_time_issues', 'changed_record_count', 'changed_metrics']})
                cell.update(posthoc_metrics=result['posthoc_numeric']['metrics'], replay_status='original_exact_then_scope_replayed')
                if cell['changed_record_count'] or cell['changed_metrics']:
                    changed.append({**cell, 'record_audit': bind(folder / 'record_audit.json'), 'result_summary': bind(folder / 'summary.json')})
            except Exception as exc:
                cell['replay_status'] = 'verification_error'; cell['error'] = {'type': type(exc).__name__, 'reason': str(exc)}
                cell['posthoc_metrics'] = None; errors.append(cell)
        cells.append(cell)
        for m in scoring.METRICS:
            value = None if cell['posthoc_metrics'] is None else cell['posthoc_metrics'][m]
            metric_rows.append({'cohort': r['cohort'], 'cell_id': r['cell_id'], 'trial_id': r['trial_id'], 'original_status': r['status'],
                'metric': m, 'original': r['original_metrics'][m], 'posthoc': value,
                'changed': None if cell['posthoc_metrics'] is None else not scoring.same(r['original_metrics'][m], value),
                'replay_status': cell['replay_status']})
    aggregates = []
    for cohort in ['development', 'E2', 'Qwen_repeats']:
        rr = [c for c in cells if c['cohort'] == cohort]
        counts = {'cohort': cohort, 'planned_denominator': len(rr), 'original_successes': sum(c['status'] == 'success' for c in rr),
            'original_failures': sum(c['status'] == 'failed' for c in rr), 'cancelled_no_retry': sum(c['status'] == 'user_cancelled_no_retry' for c in rr),
            'verification_errors': sum(c['error'] is not None for c in rr), 'changed_cells': sum(bool(c['changed_metrics']) for c in rr),
            'changed_record_cells': sum(c['changed_record_count'] > 0 for c in rr)}
        for side in ['original', 'posthoc']:
            counts[side + '_total_hours_finite'] = sum(scoring.finite(c[side + '_time_hours']) for c in rr)
            counts[side + '_s_time_finite'] = sum(c[side + '_metrics'] is not None and scoring.finite(c[side + '_metrics']['s_time']) for c in rr)
            counts[side + '_complete_CCE'] = sum(c[side + '_metrics'] is not None and all(scoring.finite(c[side + '_metrics'][m]) for m in ['Com', 'Cor', 'Eff', 'IA', 'HV']) for c in rr)
        aggregates.append(counts)
    inputs = unique_bindings([p for r in records for p in r['paths']]); base.verify_bindings(inputs)
    write_table(out, 'cells', cells); write_table(out, 'metric_comparison', metric_rows)
    write_table(out, 'cohort_summary', aggregates); scope.save_once(out / 'all_changes.json', changed)
    scope.save_once(out / 'errors.json', errors)
    summary = {'status': 'complete_posthoc_scope_application' if not errors else 'incomplete_due_to_verification_errors',
        'version': VERSION, 'cohorts': aggregates, 'planned_slots': len(cells), 'metric_rows': len(metric_rows),
        'original_failures_and_cancelled_retained': True, 'new_model_requests': 0, 'new_embedding_requests': 0,
        'original_success_conversion_and_numeric_exact_replay': not errors, 'original_scientific_formulas_unchanged': True,
        'derived_coverage_dataflow_changed': True, 'scientific_accuracy_confirmed': False,
        'original_raw_and_results_modified': False, 'protected_inputs': inputs,
        'implementation': [bind(__file__), bind(scope.__file__), bind(chain.__file__), bind(continuation.__file__)],
        'actual_command': [sys.executable, *sys.argv]}
    scope.save_once(out / 'summary.json', summary)
    print(j.canonical({'status': summary['status'], 'cohorts': aggregates, 'new_model_requests': 0}))
    require(not errors, 'BATCH_REPLAY_ERRORS_RETAINED')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=['replay'])
    parser.add_argument('--out', type=Path, required=True); args = parser.parse_args()
    out = args.out.resolve(); require(out.is_relative_to(OUT.resolve()), 'NEW_BATCH_NAMESPACE_ONLY')
    replay(out)


if __name__ == '__main__': main()
