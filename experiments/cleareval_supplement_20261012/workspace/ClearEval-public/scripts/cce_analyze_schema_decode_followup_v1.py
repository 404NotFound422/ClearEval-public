"""Offline technical analysis of the frozen schema-decoding development gate."""
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_schema_decode_followup_v1 as experiment
import cce_judges as j
from evaluator_integrity import parse_judge_object

OUT = experiment.OUT
RUN = experiment.run_area('development')


def require(ok, reason):
    if not ok: raise ValueError(reason)


def main():
    plan = experiment.validate()
    ledger_before = j.filehash(experiment.LEDGER)
    ledger = {r['request_id']: r for r in j.ledger_rows(experiment.LEDGER) if r.get('event') == 'request_started'}
    matrix = {r['case_id']: r for r in plan['matrix'] if r['stage'] == 'development'}
    trials = {r['case_id']: (p, r) for p in (RUN / 'trials').glob('*.json') for r in [j.read(p)]}
    require(set(trials) == set(matrix) and len(matrix) == 5, 'fixed_development_matrix_incomplete')
    contract = j.read(RUN / 'preflight.json')['contract']
    schema = j.read(OUT / 'format_schema.json')
    require(contract['models'][0]['settings']['format'] == schema, 'schema_not_in_executed_contract')
    inputs = [experiment.bind(OUT / 'plan.json'), experiment.bind(RUN / 'preflight.json'),
        experiment.bind(RUN / 'summary.json'), experiment.bind(OUT / 'format_schema.json')]
    rows = []; indices = []
    for cid, cell in matrix.items():
        path, trial = trials[cid]
        identity = {'case_id': cid, 'input_sha256': cell['input_sha256'], 'judge': experiment.MODEL,
            'repeat_index': 0, 'contract_sha256': j.digest(contract)}
        require(trial['identity'] == identity and trial['trial_id'] == j.digest(identity), 'trial_identity_changed')
        require(trial['attempt'] == 1 and trial['actual_api_request_made'], 'not_first_actual_attempt')
        attempt = RUN / 'attempts' / (trial['trial_id'] + '_1')
        receipt = j.read(attempt / 'request_receipt.json')
        require(ledger[receipt['request_id']] == receipt, 'receipt_ledger_mismatch')
        indices.append(receipt['package_request_index'])
        prompt_path = attempt / 'prompt.txt'
        expected = Path(cell['prompt_path']).read_text(encoding='utf-8')
        require(prompt_path.read_text(encoding='utf-8') == expected and j.filehash(prompt_path) == trial['prompt_sha256'], 'actual_full_prompt_changed')
        transport_path = experiment.area('development') / 'sealed/transport_checks' / (cell['anonymous_answer_id'] + '.json')
        transport = j.read(transport_path)
        require(transport['actual_format_is_frozen_schema'] and transport['actual_format_digest'] == j.digest(schema), 'actual_schema_transport_unproven')
        require(transport['prompt_raw_utf8_sha256'] == hashlib.sha256(expected.encode()).hexdigest(), 'transport_prompt_hash_changed')
        provider = j.read(attempt / 'provider_response.json')
        duplicate_groups = []
        def hook(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    # Report only structural equality, never choose a value.
                    duplicate_groups.append({'repeated_values_equal': result[key] == value})
                result[key] = value
            return result
        standard_complete = False
        try:
            json.loads(provider['response'], object_pairs_hook=hook)
            standard_complete = True
        except ValueError:
            pass
        strict_category = None
        try:
            parsed = parse_judge_object(provider['response'])
        except Exception as error:
            strict_category = 'duplicate_JSON_key' if 'Duplicate JSON key:' in str(error) else type(error).__name__
        if trial['status'] == 'success':
            require(strict_category is None and trial['evaluation']['teacher_generation']['content'] == provider['response'], 'successful_raw_return_binding_failed')
            require(j.proposals(trial['evaluation']) == trial['preserved_numeric_proposals'], 'proposal_binding_changed')
        rows.append({'anonymous_answer_id': cell['anonymous_answer_id'], 'question_id': cell['question_id'],
            'status': trial['status'], 'failure_category': strict_category,
            'provider_done': provider.get('done'), 'provider_finish_reason': provider.get('done_reason'),
            'completion_tokens': provider.get('eval_count'), 'standard_json_complete': standard_complete,
            'duplicate_groups': duplicate_groups, 'request_index': receipt['package_request_index'],
            'actual_schema_and_frozen_full_prompt_verified': True})
        inputs += [experiment.bind(p) for p in [path, attempt / 'request_receipt.json', prompt_path,
            transport_path, attempt / 'provider_response.json', attempt / 'context_check.json']]
    success = sum(r['status'] == 'success' for r in rows)
    require(success == 4 and sum(r['failure_category'] == 'duplicate_JSON_key' for r in rows) == 1, 'observed_results_changed')
    failed = next(r for r in rows if r['status'] == 'failed')
    require(failed['duplicate_groups'] == [{'repeated_values_equal': False}], 'conflicting_duplicate_boundary_changed')
    require(not list(experiment.run_area('holdout_followup').glob('attempts/*/request_receipt.json')), 'followup_requests_after_failed_gate')
    try:
        experiment.gate('holdout_followup')
    except ValueError as error:
        require(str(error) == 'prespecified_development_gate_not_passed', 'unexpected_gate_failure')
        gate_blocked = True
    else:
        gate_blocked = False
    require(gate_blocked, 'failed_development_gate_not_enforced')
    require(j.filehash(experiment.LEDGER) == ledger_before, 'offline_analysis_made_request')
    experiment.validate()
    summary = {'status': 'development_complete_followup_not_run_prespecified_gate_failed',
        'development_selected': 5, 'development_attempted': 5, 'development_successful': success,
        'development_failed': 1, 'followup_selected': 15, 'followup_attempted': 0,
        'followup_status': 'not_run_development_gate_not_met', 'new_requests': 5,
        'request_indices': sorted(indices), 'package_requests': len(ledger),
        'actual_schema_transmissions_verified': 5, 'strict_duplicate_key_failures': 1,
        'conflicting_duplicate_groups': 1, 'automatic_value_choice_or_repair': False,
        'decoder_schema_identical_to_existing_typed_prompt_schema': True,
        'original_model_prompt_scoring_formulas_unchanged': True,
        'expert_returns': 0, 'formal_eligible': False, 'new_complete_CCE_claims': 0,
        'interpretation': 'The typed schema did not ensure unique marker keys. Conflicting repeated values cannot be repaired by silently keeping the first or last value. The unchanged strict validator rejected this output.',
        'comparison_scope': 'Five development cases; no independent holdout accuracy inference; not a repeated sample under the original format setting.',
        'new_analysis_model_requests': 0}
    j.save(OUT / 'technical_results.json', rows)
    j.save(OUT / 'completion_summary.json', summary)
    j.save(OUT / 'analysis_verification.json', {'status': 'pass', 'inputs': inputs,
        'protected_original_files_unchanged': len(plan['protected_originals']),
        'frozen_inputs_unchanged': len(plan['frozen_inputs']), 'ledger_sha256': ledger_before,
        'development_gate_reexecuted_and_rejected': True, 'new_requests': 0,
        'analyzer': experiment.bind(Path(__file__))})
    (OUT / 'README.md').write_text('''# 结构化解码：固定开发检验

原 v2 提示词、既有 typed schema、全文、模型和评分函数均不变，仅把本地 transport 的 format 从 json 改为原样 schema 对象。固定 A01–A05 各一次：4 成功、1 失败；请求132–136。

失败由严格 JSON 解析器发现重复标记键，重复值冲突。provider 正常 stop，不是超时或截断。不得通过静默选择首值/末值冒充修复。该 schema 并未保证键唯一性；技术约束也不是科学提取正确性的证据。

事先规定5/5通过才继续15份。实际门槛未过，A06–A20保持未运行，未新增15次调用。原全部输出与专家表保留。

[逐条技术结果](technical_results.json)、[冻结计划](plan.json)、[真实传输与回执核验](analysis_verification.json)、[实际命令](actual_commands.json)。参考[本地结构化输出官方文档](https://docs.ollama.com/capabilities/structured-outputs)。
''', encoding='utf-8')
    commands = j.read(OUT / 'actual_commands.json')
    invocation = {'stage': 'offline_analysis', 'argv': [sys.executable, 'scripts/cce_analyze_schema_decode_followup_v1.py'],
        'new_requests': 0, 'status': 'pass', 'utc': j.now()}
    commands.append(invocation)
    commands.append({'stage': 'followup_preflight_gate_check',
        'argv': [sys.executable, 'scripts/cce_schema_decode_followup_v1.py', 'preflight', '--stage', 'holdout_followup'],
        'actual_exit_code': 1, 'reason': 'prespecified_development_gate_not_passed',
        'coordinator_execution_confirmed': True, 'new_requests': 0})
    j.save(OUT / 'actual_commands.json', commands)
    print(j.canonical(summary))


if __name__ == '__main__': main()
