"""Report the completed real v4 development batch without changing old results."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation/optimizer_20261010'
OUT = BASE / 'grounded_v4_stage_report_v1'
LEDGER = ROOT / 'artifacts/cce_validation/judges/request_ledger.jsonl'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    require(not OUT.exists(), 'Preserve existing report; use a new version.')
    ledger_before = sha(LEDGER)
    ledger = {r['request_id']: r for r in map(json.loads, LEDGER.read_text(encoding='utf8').splitlines())}
    inputs = []
    versions = []
    original_cases = None
    original_contract = None
    for version in ['v3', 'v4']:
        folder = BASE / ('grounded_development_' + version)
        paths = [folder / n for n in ['completion_summary.json', 'per_answer.json', 'cases.json', 'matrix.json', 'expected_contract.json']]
        paths += [folder / ('independent_fact_audit_' + version) / n for n in ['summary.json', 'per_answer.json']]
        summary, rows, cases, matrix, contract, facts, fact_rows = map(read, paths)
        cases = cases['cases']
        require(summary['actual_observations'] == facts['fixed_answers'] == len(rows) == len(fact_rows) == 5, 'Five-case denominator changed.')
        require(facts['status'] == 'complete', 'Fact review not complete.')
        require([facts[k] for k in ['explicit_names_denominator', 'core_duration_denominator', 'explicit_relation_denominator', 'ambiguity_group_denominator']] == [16, 31, 3, 2], 'Inventory changed.')
        if original_cases is None:
            original_cases, original_contract = cases, contract
        else:
            require(cases == original_cases, 'Full question/answer/reference input changed.')
            require(all(contract[k] == original_contract[k] for k in ['files', 'demands', 'scoring_version', 'source_registry_sha256']), 'Original science contract changed.')
            old = original_contract['models'][0]
            new = contract['models'][0]
            require(old['name'] == new['name'], 'Model changed.')
            require({k: v for k, v in old['settings'].items() if k not in ['format', 'num_ctx']} ==
                    {k: v for k, v in new['settings'].items() if k not in ['format', 'num_ctx']}, 'Other generation settings changed.')
        for binding in summary.get('bound_observations', []) + facts.get('inputs', []):
            require(sha(binding['path']) == binding['sha256'], 'Bound result changed: ' + binding['path'])
            inputs.append(Path(binding['path']))
        terminals = []
        for cell, row in zip(matrix, rows):
            trial_id = cell['planned_trial_id']
            trial_path = folder / 'run/trials' / (trial_id + '.json')
            receipt_path = folder / 'run/attempts' / (trial_id + '_1/request_receipt.json')
            trial, receipt = read(trial_path), read(receipt_path)
            require(trial['identity'] == cell['identity'] and trial['status'] == row['status'] and trial['attempt'] == 1, 'Trial identity changed.')
            require(receipt == ledger[receipt['request_id']] and receipt['trial_id'] == trial_id, 'Request is not in the actual ledger.')
            terminals.append({'answer': row['anonymous_answer_id'], 'status': row['status'], 'request_index': row['request_index'],
                              'errors': row.get('grounded_conversion_errors', []), 'trial_id': trial_id})
            inputs += [trial_path, receipt_path]
        require(sum(r['status'] == 'success' for r in rows) == summary['technical_successes'], 'Success count changed.')
        versions.append({'version': version, 'technical_successes': summary['technical_successes'],
                         'complete_numeric': summary['complete_numeric_after_component_gates'],
                         'names': facts['name_states'], 'duration_retained': facts['record_bound_numeric_components_retained'],
                         'relation_projection_retained': facts['exact_relation_projections_retained'],
                         'ambiguities': facts['ambiguity_states'], 'num_ctx': contract['models'][0]['settings']['num_ctx'],
                         'terminal_observations': terminals})
        inputs += paths
    amendment = BASE / 'confirmation_reference_design_v1/revision_02/integrity_amendment.json'
    access_note = BASE / 'root_search_scope_audit_20261010.md'
    inputs += [amendment, access_note]
    require(sha(LEDGER) == ledger_before, 'Read-only report changed ledger.')
    result = {'status': 'actual_development_comparison_not_accepted_candidate', 'versions': versions,
              'T01_v4': 'failed_3_of_5_valid', 'original_acceptance_criteria_changed': False,
              'new_model_requests': 0, 'expert_labels_created': 0, 'same_five_full_inputs': True,
              'single_factor_ablation': False, 'v4_indirect_context_justification_hash_chain': 'broken_disclosed_not_restored',
              'inputs': [{'path': str(p.resolve()), 'sha256': sha(p)} for p in dict.fromkeys(inputs)],
              'actual_command': [sys.executable, *sys.argv], 'script_sha256': sha(__file__)}
    OUT.mkdir(parents=True)
    (OUT / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    text = '''# v4 真实开发结果

v4 五份已全部结束：3 份技术成功、2 份来源转换失败，完整 CCE 数值仍为 0/5。原 T01 未通过，不能提升为合格最终候选。

| 固定同五份答案 | v3 | v4 |
|---|---:|---:|
| 技术成功 | 4/5 | 3/5 |
| 完整数值 | 0/5 | 0/5 |
| 有效转换中名称精确保留 | 8/16 | 8/16 |
| 有效转换中初始时间分量原值与记录绑定 | 25/31 | 19/31 |
| 三组明确关系的投影保留 | 3/3 | 0/3 |
| 明确歧义保留 | 0/2 | 1/2 |

v4 原始返回包含 16/16 个名称字面值；这不使两份失败转换成为有效数据。模型把大部分证据指向候选短片段，导致完整名称或关系所需上下文不足。A03 的实际首错是 MAP2 后配对分隔符与身份后缀规则冲突；A05 的完整名称只引用了 Tubulin 片段。A01 的初始操作范围均为 unknown，A02/A04 的前处理标题未通过窄词法门控。各问题仍须区分程序误拒、模型遗漏、错误关系和真实未知。

对论文的意义：增加来源引用并未在这一批自动改善有效覆盖；精确引用位置与事实粒度、关系支持、执行范围是不同检查。结果支持继续检验字段专用引用形式与明确范围定义，不支持宣称评估器已完善。五份均为反复使用的开发答案，不能推断独立泛化。

v4 同时改变提取方案与上下文长度（40960→98304），其余模型生成设置及原评分科学合同经实际核对不变；因此不作单因素归因。实际调用为 213–217，每份一次，失败未替换。分析命令见机器可读比较及原批 actual_commands.json。

旧参考设计摘要的间接哈希链缺口见[完整性说明](../confirmation_reference_design_v1/revision_02/INTEGRITY_AMENDMENT.md)；检索范围偏离见[访问记录](../root_search_scope_audit_20261010.md)。这两项限制没有通过报告重写消除。专家回传仍为 0。

[逐答案实际结果](../grounded_development_v4/per_answer.json) · [冻结事实核查](../grounded_development_v4/independent_fact_audit_v4/summary.json) · [逐字段诊断](../grounded_v4_failure_diagnostics_v1/README.md) · [实际回执核验与来源](comparison.json)
'''
    (OUT / 'RESULTS_zh.md').write_text(text, encoding='utf8')
    print(json.dumps({'status': result['status'], 'new_model_requests': 0, 'output': str(OUT)}))


if __name__ == '__main__':
    main()
