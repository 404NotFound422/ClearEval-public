"""Refresh optimizer progress from actual receipts and terminal trials; no generation.

This is a status index, not a scientific analysis or a process-liveness detector.
Frozen experiment plans, trial outputs and the historical 192-request report are
read only. Pending rows mean no terminal record, not proof that a process runs.
"""
from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'optimizer_20261010'
LEDGER = BASE / 'judges/request_ledger.jsonl'
CORE_SHA = 'd272393ecbba84495e0430d01c0b52c4f69a6d9502147bdb071371dfed2bdc20'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    require(sha(ROOT / 'scripts/cce_validation.py') == CORE_SHA, 'original core changed')
    ledger_bytes = LEDGER.read_bytes()
    ledger = [json.loads(line) for line in ledger_bytes.decode('utf-8').splitlines() if line.strip()]
    requests = [r for r in ledger if r.get('event') == 'request_started']
    by_request = {r['request_id']: r for r in requests}
    require(len(by_request) == len(requests), 'duplicate request IDs')
    require(len({r['package_request_index'] for r in requests}) == len(requests), 'duplicate request indices')
    plan = read(OUT / 'plan.json')
    require(len(requests) <= plan['whole_package_request_limit'], 'budget exceeded')
    stage_dirs = [OUT / 'model_probe_v1'] + sorted(OUT.glob('grounded_development_v*'))
    stages = []
    for directory in stage_dirs:
        if not directory.is_dir() or not (directory / 'matrix.json').exists():
            continue
        matrix = read(directory / 'matrix.json')
        observations = []
        for cell in matrix:
            trial_id = cell['planned_trial_id']
            terminal_path = directory / 'run/trials' / (trial_id + '.json')
            receipt_paths = sorted((directory / 'run/attempts').glob(trial_id + '_*/request_receipt.json'))
            require(len(receipt_paths) <= 1, 'unplanned retry in fixed development batch')
            receipt = read(receipt_paths[0]) if receipt_paths else None
            if receipt:
                require(receipt == by_request.get(receipt['request_id']), 'receipt/ledger mismatch')
                require(receipt['trial_id'] == trial_id, 'receipt trial mismatch')
            terminal = read(terminal_path) if terminal_path.exists() else None
            if terminal:
                require(receipt is not None, 'terminal trial without receipt')
                require(terminal['trial_id'] == trial_id, 'terminal identity mismatch')
                require(terminal['status'] in ['success', 'failed'], 'unexpected terminal status')
            evaluation = terminal.get('evaluation', {}) if terminal else {}
            conversion_errors = []
            for key, value in evaluation.items():
                if key.startswith('grounded_extraction_v') and isinstance(value, dict):
                    conversion_errors.extend(value.get('conversion_errors', []))
            observations.append({
                'anonymous_answer_id': cell.get('anonymous_answer_id'),
                'trial_id': trial_id,
                'request_index': receipt['package_request_index'] if receipt else None,
                'status': terminal['status'] if terminal else 'no_terminal_record',
                'failure_stage': evaluation.get('failure_stage'),
                'conversion_errors': conversion_errors,
                'terminal_sha256': sha(terminal_path) if terminal else None,
                'receipt_sha256': sha(receipt_paths[0]) if receipt else None,
            })
        summary_path = directory / 'completion_summary.json'
        summary = read(summary_path) if summary_path.exists() else None
        technical = sum(r['status'] == 'success' for r in observations)
        complete = sum(r['status'] in ['success', 'failed'] for r in observations)
        if summary:
            require(complete == len(matrix), 'analysis exists before complete observations')
            require(summary.get('technical_successes', summary.get('successes')) == technical, 'analysis/terminal success count mismatch')
        fact_paths = sorted(directory.glob('independent_fact_audit_v*/summary.json'))
        stages.append({
            'name': directory.name,
            'planned_observations': len(matrix),
            'requests_started': sum(r['request_index'] is not None for r in observations),
            'terminal_observations': complete,
            'technical_successes': technical,
            'technical_failures': sum(r['status'] == 'failed' for r in observations),
            'pending_terminal_records': len(matrix) - complete,
            'analyzed': summary is not None,
            'complete_numeric_after_component_gates': summary.get('complete_numeric_after_component_gates', summary.get('complete_numeric')) if summary else None,
            'completion_summary_sha256': sha(summary_path) if summary else None,
            'fact_audit_summary_available': bool(fact_paths),
            'fact_audit_summaries': [{'path': str(p), 'sha256': sha(p)} for p in fact_paths],
            'observations': observations,
        })
    now = datetime.now(timezone.utc).isoformat()
    result = {
        'status': 'active', 'updated_utc': now,
        'requests': len(requests),
        'remaining_requests_under_original_cap': plan['whole_package_request_limit'] - len(requests),
        'ledger_snapshot_sha256': hashlib.sha256(ledger_bytes).hexdigest(),
        'deadline_utc': plan['deadline_utc'],
        'stages': stages,
        'original_core_sha256_verified': CORE_SHA,
        'human_expert_returns': 0,
        'human_return_note': 'No real expert return has been received in this optimization session; model reviews are separate.',
        'process_liveness': 'Not inferred from artifacts; poll the actual session handle before deciding to resume or restart.',
        'next': 'Finish source-bound development and independently review retained facts; then run frozen full controls, two-family repeats and sealed confirmation. Preserve all failed observations.',
    }
    require(LEDGER.read_bytes() == ledger_bytes, 'ledger changed during status snapshot; rerun offline status command')
    save(OUT / 'STATUS.json', result)
    lines = [
        '# ClearEval 当前优化阶段', '',
        f'状态更新时间：{now}。全包实际请求 **{len(requests)}/300**，剩余 **{300-len(requests)}**。', '',
        '[冻结总计划](optimizer_20261010/plan.json) · [动态状态及逐次证据](optimizer_20261010/STATUS.json) · [新增结果解释](optimizer_20261010/RESULTS_zh.md)', '',
        '| 开发批次 | 终态/计划 | 技术成功 | 技术失败 | 分析 |',
        '|---|---:|---:|---:|---|',
    ]
    for stage in stages:
        path = 'optimizer_20261010/' + stage['name']
        link = path + ('/completion_summary.json' if stage['analyzed'] else '/matrix.json')
        lines.append(f"| [{stage['name']}]({link}) | {stage['terminal_observations']}/{stage['planned_observations']} | {stage['technical_successes']} | {stage['technical_failures']} | {'已完成' if stage['analyzed'] else '待终态后运行'} |")
    lines += [
        '', '技术成功表示运行器接受并完成计算，不能据此认定提取忠实或评分正确。来源事实核查、证据未决和数值覆盖单独报告。没有终态记录不等于进程仍在运行；续跑前需核对原会话句柄。', '',
        '五份模型对照已完成独立来源审查：A01、A02存在时间字段与解释冲突；A04具体染料—靶标关系无直接来源支持。来源绑定候选据实际失败迭代，原始返回与失败记录均保留。', '',
        '[步骤匹配 v3 与独立复算](optimizer_20261010/step_representation_v3/README.md)已完成21份全文、15对离线诊断；新增指标独立命名，原BioProBench基线未改。[文献依据](optimizer_20261010/PUBLISHED_METHODS_ADDENDUM_zh.md)已核查。', '',
        '下一阶段：完成提取候选开发，随后在同一冻结配置下运行21份受控全文、两评价器家族真实重复，以及8份封存自动确认。原15份专家留出未用于调参；专家回传仍为0，湿实验结果待真实数据。', '',
        '此前192次结果见[历史快照](historical_reports/before_optimizer_at_192/CURRENT_RESULTS_INDEX.md)。原主50/77及方法族条件66/77保留。旧报告生成器限定192次，不应用于覆盖本阶段。', '',
        '状态恢复命令：`python scripts/cce_optimizer_status_v1.py`（使用已记录的portable Python）；它只核对与更新状态，不发起模型请求。各批运行及分析命令见对应 `actual_commands.json`。', '',
    ]
    (BASE / 'STATUS.md').write_text('\n'.join(lines), encoding='utf-8')
    (ROOT.parent / 'STATUS.md').write_text(
        '# ClearEval 当前状态\n\n九小时优化阶段进行中，见[当前状态](ClearEval-public/artifacts/cce_validation/STATUS.md)。\n\n'
        + f'实际请求{len(requests)}/300。成功和失败均保留；来源绑定提取仍在开发验证，后续受控、重复及封存确认尚待完成。专家回传0。\n', encoding='utf-8')
    commands_path = OUT / 'status_actual_commands.json'
    commands = read(commands_path) if commands_path.exists() else []
    commands.append({'utc': now, 'argv': [sys.executable, *sys.argv], 'cwd': str(ROOT),
                     'script_sha256': sha(Path(__file__)), 'requests_snapshot': len(requests), 'new_model_requests': 0})
    save(commands_path, commands)
    print(json.dumps({'status': 'updated', 'requests': len(requests), 'stages': [
        {k: s[k] for k in ['name', 'terminal_observations', 'technical_successes', 'technical_failures', 'analyzed']} for s in stages],
        'new_model_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
