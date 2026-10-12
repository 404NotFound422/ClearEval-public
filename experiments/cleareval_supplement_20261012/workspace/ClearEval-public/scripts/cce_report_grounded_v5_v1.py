"""Compare completed real v4/v5 batches; never repair or regenerate a return."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation/optimizer_20261010'
OUT = BASE / 'grounded_v5_stage_report_v1'
LEDGER = ROOT / 'artifacts/cce_validation/judges/request_ledger.jsonl'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def main():
    require(not OUT.exists(), 'Existing report is immutable; use a new version.')
    ledger_bytes = LEDGER.read_bytes()
    ledger = {r['request_id']: r for r in map(json.loads, ledger_bytes.decode('utf8').splitlines())}
    inputs = [Path(__file__)]
    versions = []
    original_cases = original_contract = None
    for version in ['v4', 'v5']:
        folder = BASE / ('grounded_development_' + version)
        paths = [folder / n for n in ['completion_summary.json', 'per_answer.json', 'cases.json', 'matrix.json', 'expected_contract.json']]
        paths += [folder / ('independent_fact_audit_' + version) / n for n in ['summary.json', 'per_answer.json']]
        summary, rows, cases, matrix, contract, facts, fact_rows = map(read, paths)
        require(summary['actual_observations'] == facts['fixed_answers'] == len(rows) == len(matrix) == len(fact_rows) == 5, 'Fixed five changed.')
        require(facts['status'] == 'complete', 'Fact audit incomplete.')
        require([facts[k] for k in ['explicit_names_denominator', 'core_duration_denominator', 'explicit_relation_denominator', 'ambiguity_group_denominator']] == [16, 31, 3, 2], 'Fixed fact inventory changed.')
        if original_cases is None:
            original_cases, original_contract = cases, contract
        else:
            require(cases == original_cases, 'Question, answer, metadata or reference changed.')
            require(all(contract[k] == original_contract[k] for k in ['files', 'demands', 'scoring_version', 'source_registry_sha256']), 'Original scientific contract changed.')
            require(contract['models'][0]['name'] == original_contract['models'][0]['name'], 'Evaluator changed.')
            require({k: v for k, v in contract['models'][0]['settings'].items() if k != 'format'} ==
                    {k: v for k, v in original_contract['models'][0]['settings'].items() if k != 'format'}, 'Generation settings beyond schema changed.')
        for binding in summary.get('bound_observations', []) + facts.get('inputs', []):
            require(sha(binding['path']) == binding['sha256'], 'Result binding changed: ' + binding['path'])
            inputs.append(Path(binding['path']))
        keyed = {r['trial_id']: r for r in rows}
        require(len(keyed) == 5, 'Duplicate output trial identity.')
        terminals = []
        for cell in matrix:
            tid = cell['planned_trial_id']
            row = keyed[tid]
            trial_path = folder / 'run/trials' / (tid + '.json')
            receipt_path = folder / 'run/attempts' / (tid + '_1/request_receipt.json')
            trial, receipt = read(trial_path), read(receipt_path)
            require(trial['trial_id'] == tid and trial['identity'] == cell['identity'] and trial['status'] == row['status'] and trial['attempt'] == 1, 'Trial identity/status mismatch.')
            require(receipt == ledger[receipt['request_id']] and receipt['trial_id'] == tid and receipt['attempt'] == 1, 'Actual receipt not in ledger.')
            require(receipt['package_request_index'] == row['request_index'], 'Request index changed.')
            terminals.append({'answer': row['anonymous_answer_id'], 'status': row['status'],
                'request_index': row['request_index'], 'failure_stage': row['failure_stage'],
                'conversion_errors': row.get('grounded_conversion_errors'),
                'numeric_components': row['numeric_component_count'],
                'complete_numeric': row['complete_numeric_after_component_gates'],
                'values': row['component_gated_proposals'], 'evidence_state': row['evidence_state'],
                'trial_id': tid})
            inputs += [trial_path, receipt_path]
        require(sum(r['status'] == 'success' for r in rows) == summary['technical_successes'], 'Success denominator mismatch.')
        versions.append({'version': version, 'technical_successes': summary['technical_successes'],
            'complete_numeric': summary['complete_numeric_after_component_gates'],
            'name_states': facts['name_states'], 'duration_states': facts['core_duration_states'],
            'names_exact': facts['name_states'].get('exact', 0),
            'duration_retained': facts['record_bound_numeric_components_retained'],
            'initial_scope_retained': facts['core_initial_scope_retained'],
            'relation_edges_retained': facts['exact_endpoint_edges_retained'],
            'relation_projection_retained': facts['exact_relation_projections_retained'],
            'ambiguity_states': facts['ambiguity_states'],
            'ambiguity_retained': facts['ambiguity_states'].get('explicit_ambiguity_retained', 0),
            'raw_name_presence_separate': facts['raw_name_presence_separate'],
            'num_ctx': contract['models'][0]['settings']['num_ctx'],
            'terminal_observations': terminals})
        inputs += paths
    current = versions[-1]
    diagnosis = BASE / 'grounded_v5_failure_diagnostics_v1/summary_5of5.json'
    require(diagnosis.exists(), 'Completed five-answer independent diagnosis required.')
    inputs += [diagnosis, BASE / 'grounded_v5_design_v1/budget_allocation_amendment.json',
        BASE / 'confirmation_reference_design_v1/revision_02/integrity_amendment.json',
        BASE / 'root_search_scope_audit_20261010.md']
    require(LEDGER.read_bytes() == ledger_bytes, 'Ledger changed during offline report; inspect and rerun.')
    technical_pass = current['technical_successes'] == 5
    result = {'status': 'actual_development_comparison_scientific_acceptance_not_established',
        'versions': versions, 'T01_v5': 'pass' if technical_pass else 'fail',
        'inventory_counters_complete': all(current[k] == n for k, n in [('names_exact', 16), ('duration_retained', 31), ('relation_projection_retained', 3), ('ambiguity_retained', 2)]),
        'inventory_counters_are_not_expert_accuracy': True,
        'same_five_full_inputs': True, 'same_generation_settings_except_schema': True,
        'new_model_requests': 0, 'new_expert_labels': 0, 'single_factor_ablation': False,
        'original_G01_development_budget_clause': 'deviated_development25_to30_prospectively_recorded',
        'original_technical_and_scientific_acceptance_unchanged': True,
        'full_objective_complete': False,
        'inputs': [{'path': str(p.resolve()), 'sha256': sha(p)} for p in dict.fromkeys(inputs)],
        'actual_command': [sys.executable, *sys.argv], 'script_sha256': sha(__file__)}
    lines = ['# v5 真实开发结果', '',
        f"五份已全部结束：技术成功 {current['technical_successes']}/5；完整九项数值 {current['complete_numeric']}/5。T01 为 {'通过' if technical_pass else '未通过'}；科学有效性仍未建立。", '',
        '| 固定同五份答案 | v4 | v5 |', '|---|---:|---:|']
    for label, key, den in [('技术成功', 'technical_successes', 5), ('完整九项数值', 'complete_numeric', 5),
            ('有效转换中名称精确保留', 'names_exact', 16), ('时间原值与操作记录绑定', 'duration_retained', 31),
            ('初始范围声明保留', 'initial_scope_retained', 31), ('明确关系投影保留', 'relation_projection_retained', 3),
            ('明确歧义保留', 'ambiguity_retained', 2)]:
        lines.append(f"| {label} | {versions[0][key]}/{den} | {current[key]}/{den} |")
    lines += ['', '| 答案 | 实际请求 | 技术状态 | 数值分项 / 9 | 首个失败阶段 |', '|---|---:|---|---:|---|']
    for row in current['terminal_observations']:
        lines.append(f"| {row['answer']} | {row['request_index']} | {row['status']} | {row['numeric_components']} | {row['failure_stage'] or '无技术失败'} |")
    lines += ['', '对论文的意义：该比较检验来源引用表示及范围规则能否保留明确证据。技术可执行、已知事实覆盖、合法未知和科学正确性分别报告；不能因减少有效样本或增加 NA 而宣称改善。原始返回出现名称不等于转换有效，来源位置精确也不等于语义关系正确。', '',
        '两版使用完全相同的五份题干、答案和参考，模型及生成参数相同（含上下文 98304）；提取提示、schema 和确定性证据规则作为一组修订，不能归因为单一因素。原参数完整性、Correctness、EGES、知识库、需求和核心评分合同经核验未改。五份重复使用的开发答案不能证明泛化。', '',
        '实际生成命令：`python scripts/cce_grounded_development_v5.py run --allow-local-calls`。实际离线分析命令与完整逐次回执见批次 actual_commands.json、冻结独立核查及本报告 comparison.json；任何失败均未替换。', '',
        '预算偏离：原开发 25 次上限前瞻性改为 30，全包 300 不变；原 G01 不能写成无偏离通过。旧参考摘要的间接哈希缺口与检索范围事件仍需披露，见[完整性说明](../confirmation_reference_design_v1/revision_02/INTEGRITY_AMENDMENT.md)和[访问记录](../root_search_scope_audit_20261010.md)。', '',
        '[逐答案结果](../grounded_development_v5/per_answer.json) · [事实核查](../grounded_development_v5/independent_fact_audit_v5/summary.json) · [五份来源诊断](../grounded_v5_failure_diagnostics_v1/README.md) · [真实来源与复核](comparison.json)', '']
    OUT.mkdir(parents=True)
    (OUT / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    (OUT / 'RESULTS_zh.md').write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps({'status': result['status'], 'T01': result['T01_v5'], 'output': str(OUT), 'new_calls': 0}))

if __name__ == '__main__':
    main()
