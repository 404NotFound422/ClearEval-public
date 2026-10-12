"""Offline sealing and ASSISTED attachments for the frozen holdout batch.

Only run after the coordinator confirms the whole run has terminated. No model
transport, retries, field correction, reference addition or tuning is performed.
All raw returns and numeric replay products remain in the sealed directory.
"""
from __future__ import annotations
import argparse
import collections
import contextlib
import copy
import io
import json
import os
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
import cce_extraction_holdout_v1 as preparation
import cce_rescore_extractions as bridge

j = preparation.judges
OUT, SEALED, RUN = preparation.OUT, preparation.SEALED, preparation.RUN
AUTO = SEALED / 'guarded_auto'
REVIEWER = SEALED / 'reviewer'
FORM = preparation.HUMAN / 'reviewer/review_items.csv'
BEFORE_89 = preparation.BASE / 'historical_reports/followup_at_89/snapshot_manifest.json'


def require(ok, category):
    if not ok: raise RuntimeError(category)


def bind(path):
    return preparation.binding(path)


def save(path, obj):
    j.save(path, obj)


def relative(target, directory):
    return Path(os.path.relpath(target, directory)).as_posix()


def finalize(args):
    require(args.run_finished and args.run_exit_code == 0, 'coordinator_run_completion_required')
    plan = preparation.validate_frozen()
    require((RUN / 'summary.json').exists(), 'whole_run_summary_missing')
    require(BEFORE_89.exists(), 'pre_run_89_archive_missing')
    review_sha_before = j.filehash(FORM)
    labels = preparation.csvread(FORM)
    require(len(labels) == 160 and not any(r.get('expert_decision', '').strip() for r in labels), 'expert_return_state_changed')
    cases = {r['case_id']: r for r in j.read(SEALED / 'cases.json')['cases']}
    matrix = {r['case_id']: r for r in plan['matrix']}
    require(len(matrix) == 15 and len(cases) == plan['ready_cells'], 'fixed_cell_count_changed')
    identities = {r['answer_id']: r for r in preparation.csvread(SEALED / 'identity_manifest.csv')}
    ledger = [r for r in j.ledger_rows(preparation.LEDGER) if r.get('event') == 'request_started']
    ledger_by_request = {r['request_id']: r for r in ledger}
    require(len(ledger_by_request) == len(ledger), 'duplicate_ledger_request_id')
    preflight = j.read(RUN / 'preflight.json')
    require(preflight['contract_sha256'] == preparation.EXPECTED_CONTRACT, 'executed_contract_differs')
    runner, registry, contract, settings = preparation.dev.frozen_runtime()
    require(j.digest(contract) == preparation.EXPECTED_CONTRACT, 'current_contract_drift')
    input_bindings = [bind(OUT / 'plan.json'), bind(RUN / 'preflight.json'), bind(RUN / 'summary.json'), bind(BEFORE_89), bind(FORM)]
    trials = {r['case_id']: (p, r) for p in sorted((RUN / 'trials').glob('*.json')) for r in [j.read(p)]}
    require(set(trials) <= set(matrix), 'unexpected_trial_case')
    receipts = [(p, j.read(p)) for p in sorted((RUN / 'attempts').glob('*/request_receipt.json'))]
    receipt_by_trial = {}
    for path, receipt in receipts:
        require(receipt['trial_id'] not in receipt_by_trial and receipt['attempt'] == 1, 'duplicate_or_retried_holdout_request')
        require(ledger_by_request.get(receipt['request_id']) == receipt, 'receipt_ledger_mismatch')
        receipt_by_trial[receipt['trial_id']] = (path, receipt)
    planned_trial_ids = {r['planned_trial_id'] for r in matrix.values() if r['planned_trial_id']}
    require(set(receipt_by_trial) <= planned_trial_ids, 'unplanned_request_in_batch')
    require(len(receipts) <= 15, 'holdout_budget_exceeded')
    technical, checks = [], []
    attempted = successful = failed = 0
    for cid, cell in matrix.items():
        aid = cell['answer_id']; case = cases.get(cid)
        receipt_pair = receipt_by_trial.get(cell['planned_trial_id'])
        actual = trials.get(cid)
        if receipt_pair: attempted += 1
        status = 'pending_not_attempted'; failure = cell.get('reason_category')
        if receipt_pair and actual is None:
            status, failure = 'failed', 'attempt_return_not_recorded'; failed += 1
        if actual:
            path, trial = actual
            require(case is not None, 'trial_for_nonready_cell')
            identity = {'case_id': cid, 'input_sha256': cell['input_sha256'], 'judge': 'local_qwen3_8b', 'repeat_index': 0, 'contract_sha256': preparation.EXPECTED_CONTRACT}
            require(trial['identity'] == identity and trial['trial_id'] == j.digest(identity) == cell['planned_trial_id'], 'trial_identity_mismatch')
            require(trial['attempt'] == 1 and trial['full_text_input_sha256'] == cell['input_sha256'], 'trial_attempt_or_full_input_mismatch')
            require(trial['references_sha256'] == j.digest([]) and case['references'] == [], 'reference_context_changed')
            require(trial['repeat_index'] == 0 and trial['judge'] == 'local_qwen3_8b', 'judge_or_repeat_changed')
            require(receipt_pair is not None and trial['actual_api_request_made'], 'trial_without_actual_request')
            receipt_path, receipt = receipt_pair
            attempt_dir = receipt_path.parent
            prompt_file = attempt_dir / 'prompt.txt'
            prompt = preparation.dev.capture(runner, case)
            require(preparation.rawsha(case['model_response']) == cell['answer_raw_utf8_sha256'] and preparation.rawsha(case['specific_question']) == cell['question_raw_utf8_sha256'], 'original_text_hash_mismatch')
            require(prompt_file.read_text(encoding='utf-8') == prompt and j.filehash(prompt_file) == trial['prompt_sha256'], 'actual_prompt_mismatch')
            context = j.read(attempt_dir / 'context_check.json')
            require(context['conservative_context_bound'] == cell['conservative_context_bound'] <= 40960 and context['max_output_tokens'] == 8192, 'actual_context_mismatch')
            evaluation = trial.get('evaluation', {})
            provider_file = attempt_dir / 'provider_response.json'
            if provider_file.exists():
                provider = j.read(provider_file)
                generation = evaluation.get('teacher_generation') or {}
                if generation.get('technical_status') == 'VALID':
                    require(provider.get('response') == generation['content'], 'provider_return_binding_mismatch')
                elif isinstance(generation.get('raw_content'), str):
                    require(provider.get('response') == generation['raw_content'], 'failed_provider_raw_binding_mismatch')
                else:
                    # Original adapter rejects invalid provider output before a
                    # generation content record exists; retain its raw/error pair.
                    require((attempt_dir / 'provider_error.json').exists(), 'failed_provider_error_receipt_missing')
                    input_bindings.append(bind(attempt_dir / 'provider_error.json'))
                input_bindings.append(bind(provider_file))
            if trial['status'] == 'success':
                require(provider_file.exists() and trial['new_extraction_available'], 'successful_trial_raw_return_missing')
                parsed = runner.parse_judge_object(evaluation['teacher_generation']['content'].strip())
                returned = parsed.get('extraction')
                if not returned:
                    allowed = ['marker_dict', 'clearing_total_time_hours', 'method_name', 'reagent_ri_value', 'sample_ri_value', 'protocol_time_hours', 'method_stages', 'reasoning']
                    returned = {k: parsed[k] for k in allowed if k in parsed}
                require(returned == evaluation['extraction'], 'saved_extraction_not_original_return')
                require(j.digest(evaluation['extraction']) == trial['extraction_sha256'], 'extraction_digest_mismatch')
                require(j.proposals(evaluation) == trial['preserved_numeric_proposals'], 'original_numeric_proposal_binding_mismatch')
                require(registry.get(case['question_id'], case['specific_question']) == evaluation['user_preference_vector'], 'fixed_demand_mismatch')
                successful += 1; status = 'success'; failure = None
            else:
                failed += 1; status = 'failed'
                failure = evaluation.get('failure_stage') or evaluation.get('_error_type') or 'technical_failure_unclassified'
            checks.append({'answer_id': aid, 'trial_id': trial['trial_id'], 'status': status,
                'full_input_prompt_receipt_provider_and_contract_bound': True,
                'returned_extraction_identity_checked': trial['status'] == 'success',
                'request_index': receipt['package_request_index']})
            input_bindings += [bind(path), bind(receipt_path), bind(prompt_file), bind(attempt_dir / 'context_check.json')]
        technical.append({'answer_id': aid, 'case_id': cid, 'status': status, 'reason_category': failure})
    require(attempted == len(receipts), 'request_count_mismatch')
    pending = 15 - successful - failed
    require(pending >= 0, 'completion_count_inconsistent')
    AUTO.mkdir(parents=True, exist_ok=True)
    # The existing guarded bridge writes numerical data only below sealed/.
    bridge_args = types.SimpleNamespace(contract=OUT / 'frozen_judge_contract.json', cases=SEALED / 'cases.json',
        steps=SEALED / 'step_availability.json', trials=RUN / 'trials', identities=SEALED / 'identity_manifest.csv',
        judge='local_qwen3_8b', out=AUTO)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        bridge.build_auto(bridge_args)
        bridge.identity(types.SimpleNamespace(auto_inputs=AUTO / 'auto_inputs.json', out=AUTO))
    auto = j.read(AUTO / 'auto_inputs.json')
    records = {r['answer_id']: r for r in auto['records']}
    identity = j.read(AUTO / 'identity_verification.json')
    require(len(records) == successful and identity['actual_source_extractions'] == successful, 'guarded_auto_count_mismatch')
    require(not successful or identity['status'] == 'pass', 'guarded_identity_failed')
    scores = j.read(AUTO / 'auto_scores.json')['records']
    require(all(r['sr'] is None and r['sp'] is None and r['Com'] is None and r['IA'] is None and r['HV'] is None for r in scores), 'unsupported_step_or_joint_numeric_result')
    na_instances = collections.Counter(); na_answers = collections.Counter()
    for r in scores:
        categories = []
        for reason in r.get('na_reasons', {}).values():
            category = reason.get('category') or 'cause_classification_pending'
            na_instances[category] += 1; categories.append(category)
        for category in set(categories): na_answers[category] += 1
    REVIEWER.mkdir(parents=True, exist_ok=True)
    packet_bindings = []; rows = []
    for cell in plan['matrix']:
        aid = cell['answer_id']; ident = identities[aid]
        original_packet_path = preparation.HUMAN / 'reviewer' / (aid + '.json')
        original = j.read(original_packet_path)
        require(preparation.rawsha(original['task_text']) == ident['question_sha256'] and preparation.rawsha(original['answer_text']) == ident['answer_sha256'], 'anonymous_original_text_mismatch')
        record = records.get(aid)
        # Preserve the actual extraction exactly; no correction or source filling.
        packet = {'answer_id': aid, 'split': 'audit_holdout', 'review_mode': 'ASSISTED',
            'read_original_text_before_machine_suggestions': True,
            'task_text': original['task_text'], 'answer_text': original['answer_text'],
            'question_sha256': ident['question_sha256'], 'answer_sha256': ident['answer_sha256'],
            'references': [], 'reference_status': 'no_current_question_bound_complete_reference',
            'source_family_status': 'unmapped_not_independent_source_confirmation',
            'extraction': copy.deepcopy(record['extraction']) if record else None,
            'extraction_status': 'actual_automatic_suggestion_not_expert_confirmed' if record else 'pending_no_successful_automatic_extraction',
            'extraction_sha256': record['extraction_sha256'] if record else None,
            'schema_boundary': 'Legacy flat extraction does not certify tissue identity/dimensions, complete field coverage, factual entailment, or source applicability. Inspect original task and answer.',
            'expert_decision': '', 'source_location': '', 'correction_or_basis': '', 'reviewer_id': '', 'review_date': '', 'review_status': 'not_reviewed',
            'original_text_packet': relative(original_packet_path, REVIEWER), 'shared_expert_form': relative(FORM, REVIEWER)}
        require(not any(k in packet for k in ['model', 'model_name', 'generator_model', 'judge', 'scores', 'Com', 'Cor', 'Eff', 'IA', 'HV']), 'anonymous_packet_forbidden_metadata')
        if record: require(packet['extraction'] == record['extraction'], 'expert_suggestion_modified')
        destination = REVIEWER / (aid + '.json')
        if destination.exists(): require(j.read(destination) == packet, 'existing_packet_changed')
        else: save(destination, packet)
        packet_bindings.append(bind(destination))
        rows.append(f"| {aid} | [原题与完整答案]({relative(original_packet_path, REVIEWER)}) | [真实自动建议]({aid}.json) |")
    (REVIEWER / 'README.md').write_text('''# 一位专家：固定15份留出附件

先打开“原题与完整答案”，再查看机器建议。ASSISTED表示允许查看自动提取，不是独立盲评。模型身份和评价总分不在这些附件中；自动建议未经专家确认，不能当作已审无误。

仅在[原20份共用填写表](''' + relative(FORM, REVIEWER) + ''')对应匿名ID的既有行填写。原160行结构不变，不需新增完整CCE打分。填写成立／不成立／证据不足、原文位置、必要修正或依据、审阅者和日期；未审项保持空白。机器建议没有预填到结论栏。

| 匿名ID | 先阅读 | 后核查 |
|---|---|---|
''' + '\n'.join(rows) + '''

当前未提供这些题目的完整相容路线参考；来源家族也未映射。关键提取可以据原文局部核查，步骤/来源不足则保留需补来源。只纠正忠实性错误，不修正答案本身的实验选择，不补未报告参数。自动失败的条目明确待定，不伪造提取。此目录以外的sealed运行数据含模型身份和数值结果，不属于专家审阅入口。
''', encoding='utf-8')
    require(j.filehash(FORM) == review_sha_before, 'original_expert_form_changed')
    require(not any(AUTO.glob('*faithful*')) and not (AUTO / 'reviewed_no_change.json').exists(), 'unexpected_faithful_artifact')
    receipt_ids = [r['package_request_index'] for _, r in receipts]
    summary = {'status': 'completed_actual_run_offline_binding_and_anonymous_attachments',
        'selected_cells': 15, 'attempted_cells': attempted, 'successful_cells': successful, 'failed_cells': failed, 'pending_cells': pending,
        'new_requests': len(receipts), 'package_requests': len(ledger), 'request_indices': sorted(receipt_ids),
        'identity_verified_cells': identity['actual_source_extractions'], 'expert_returns': 0, 'faithful_corrections': 0,
        'numeric_CCE': 0, 'source_family_unmapped': 15, 'references_covered': 0,
        'reviewer_attachment_dir': str(REVIEWER), 'reviewer_entry': str(REVIEWER / 'README.md'), 'anonymous_attachment_count': len(packet_bindings),
        'failure_reason_categories': dict(collections.Counter(r['reason_category'] for r in technical if r['status'] == 'failed')),
        'NA_reason_component_instances': dict(na_instances), 'NA_reason_answer_counts': dict(na_answers),
        'step_joint_NA_reason': {'reference_insufficient_cells': 15},
        'expert_form_unchanged_rows': 160, 'expert_fields_prefilled': False, 'source_family_independence_confirmed': False,
        'scope': 'Frozen holdout automatic processing; metadata-only reporting, no scientific validity inference or tuning from results',
        'new_model_requests_during_finalization': 0, 'formal_eligible': False}
    save(SEALED / 'technical_identity_checks.json', {'status': 'pass', 'cells': checks, 'input_bindings': input_bindings,
        'guarded_bridge_identity': bind(AUTO / 'identity_verification.json'), 'packet_bindings': packet_bindings,
        'expert_form_original_sha256': review_sha_before, 'finalizer': bind(Path(__file__)), 'new_model_requests': 0})
    save(OUT / 'attachment_verification.json', {'status': 'pass', 'attachments': len(packet_bindings), 'full_original_text_hashes_match': True,
        'actual_successful_extractions_preserved': successful, 'failed_or_pending_extractions_not_fabricated': failed+pending,
        'explicit_generator_judge_score_metadata_hidden': True, 'expert_fields_empty': True, 'original_160_row_form_unchanged': True,
        'packet_bindings': packet_bindings, 'new_model_requests': 0})
    log = j.read(OUT / 'execution_commands.json')
    argv = log['planned_not_executed'].pop('run', preparation.command_arguments('run'))
    root_command = "& '" + str(preparation.PY) + "' " + ' '.join("'" + str(x).replace("'", "''") + "'" for x in argv)
    root_command += " *> 'artifacts/cce_validation/judges/local_extraction_holdout_v1/sealed/run_console.log'"
    if not any(x['stage'] == 'run' for x in log['actually_executed']):
        log['actually_executed'].append({'stage': 'run', 'argv': argv, 'shell_command': root_command,
            'executed_by': 'root coordinator', 'coordinator_reported_session': 73891, 'exit_code': 0,
            'stdout_stderr': 'sealed/run_console.log', 'model_requests': len(receipts), 'request_indices': sorted(receipt_ids),
            'command_provenance': 'Coordinator supplied actual argv and PowerShell redirection; actual receipts independently bound to ledger.'})
    log['actually_executed'].append({'stage': 'finalize', 'argv': ['scripts/cce_finalize_holdout_v1.py', 'finalize', '--run-finished', '--run-exit-code', '0'], 'model_requests': 0})
    log.update({'new_requests': len(receipts), 'package_requests_at_completion': len(ledger), 'pre_run_89_archive': bind(BEFORE_89),
        'status': 'completed_run_and_offline_attachments', 'raw_output_reporting': 'sealed; no answer, field value, or score printed'})
    save(OUT / 'execution_commands.json', log)
    save(OUT / 'completion_summary.json', summary)
    preparation.validate_frozen()
    print(j.canonical(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['finalize'])
    parser.add_argument('--run-finished', action='store_true')
    parser.add_argument('--run-exit-code', type=int)
    args = parser.parse_args()
    try:
        finalize(args)
    except Exception as exc:
        # Do not expose values or raw exception messages from sealed objects.
        import traceback
        frames = [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name} for f in traceback.extract_tb(exc.__traceback__)]
        save(OUT / 'finalization_failure.json', {'status': 'offline_finalization_incomplete', 'exception_type': type(exc).__name__,
            'code_frames': frames, 'new_model_requests': 0, 'no_retry_or_data_correction_performed': True})
        print(j.canonical({'status': 'offline_finalization_incomplete', 'exception_type': type(exc).__name__, 'code_frames': frames, 'new_model_requests': 0}))
        sys.exit(1)
