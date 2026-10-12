"""Audit the original time function on a saved secondary cohort, including numerical underflow."""
from pathlib import Path
import argparse
import csv
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
sys.dont_write_bytecode = True
import cce_grounded_offline_scoring_v1 as scoring
from evaluation_contract import time_score_details
j = scoring.j


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    assert not args.out.exists()
    cohort = j.read(args.source / 'per_answer.json')
    runner, registry = scoring.runtime()
    result = []
    inputs = [{'path': str(args.source / 'per_answer.json'), 'sha256': j.filehash(args.source / 'per_answer.json')},
              {'path': str(j.HIST), 'sha256': j.filehash(j.HIST)}]
    for answer in cohort:
        record = answer['posthoc_record']
        path = Path(record['path'])
        assert j.filehash(path) == record['sha256']
        saved = j.read(path)
        snapshot_qid = registry.questions[str(answer['question_id'])]['question_id']
        fixed_tier = runner.QUESTION_META_KB[snapshot_qid]['tissue_tier_code']
        if saved['processing_status'] == 'full_fieldwise_conversion':
            q = saved['numeric']['quantitative_data']
            assert q['sample_tier'] == fixed_tier
            input_pointer = '/numeric/quantitative_data'
        elif saved['processing_status'] == 'partial_dependency_replay':
            extraction = saved['views']['time']['projected_extraction']
            q = {'method_name': extraction['method_name'], 'total_time_hours': extraction['clearing_total_time_hours'], 'sample_tier': fixed_tier}
            assert saved['views']['time']['component_values']['s_time'] == answer['s_time']
            input_pointer = '/views/time/projected_extraction; tier from unchanged original question metadata mapping'
        else:
            raise ValueError('Unsupported saved processing status: ' + saved['processing_status'])
        identity = runner.method_identity(q['method_name'], runner.MODEL_SPACE_SIGNED, q.get('method_stages'))
        assert identity['status'] == 'RESOLVED_SINGLE'
        key = runner.resolve_method(q['method_name'], runner.TIME_KB_LOOKUP)
        kb = runner._time_kb_row(key, q['sample_tier'])
        score, details = time_score_details(q['total_time_hours'], kb, q['sample_tier'])
        assert score == answer['s_time'] == saved['metrics']['s_time'], answer['anonymous_answer_id']
        assert details['status'] == 'scored', (answer['anonymous_answer_id'], details)
        log10 = (math.log(3) - 0.5 * (details['delta_hours'] / details['tau_hours']) ** 2) / math.log(10)
        row = {'answer': answer['anonymous_answer_id'], 'question_id': answer['question_id'], 'generator': answer['generator_model'],
               'method': q['method_name'], 'method_key': key, 'sample_tier': q['sample_tier'], 'actual_hours': q['total_time_hours'],
               's_time': score, 'log10_mathematical_score': log10,
               'cause': 'floating_point_underflow' if score == 0 else 'inside_reference_window' if score == 3 else 'positive_deviation_penalty',
               'details': details, 'original_KB_row': kb, 'saved_input': record, 'input_pointer': input_pointer}
        result.append(row)
        inputs.append(record)
    assert len(result) == 10
    args.out.mkdir(parents=True)
    j.save(args.out / 'per_answer.json', result)
    columns = ['answer', 'question_id', 'generator', 'method', 'sample_tier', 'actual_hours', 's_time', 'log10_mathematical_score', 'cause']
    with (args.out / 'per_answer.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: r[k] for k in columns} for r in result)
    summary = {'status': 'completed_original_function_diagnostic', 'answers': len(result),
               'counts': {cause: sum(r['cause'] == cause for r in result) for cause in sorted({r['cause'] for r in result})},
               'original_scores_equal': True, 'original_scores_or_KB_modified': False, 'log10_used_in_CCE': False,
               'inputs': inputs, 'script': {'path': str(Path(__file__)), 'sha256': j.filehash(Path(__file__))},
               'actual_command': [sys.executable, *sys.argv], 'new_model_calls': 0}
    j.save(args.out / 'summary.json', summary)
    lines = ['# 当前十份时间分数为什么为0或很小', '',
             '本表逐份读取已保存的统一后验输入，调用原时间函数，并核对原分数完全相同。log10仅解释双精度下溢，不替换任何CCE分数或改参考窗。', '',
             '|答案|方法|总小时|原s_time|数学值log10|原因|', '|---|---|---:|---:|---:|---|']
    for row in result:
        lines.append(f"|{row['answer']}|{row['method']}|{row['actual_hours']:g}|{row['s_time']:.8g}|{row['log10_mathematical_score']:.3f}|{row['cause']}|")
    lines += ['', '数学上原高斯函数对有限时间偏差为正；超过双精度表示范围后返回0。这里的0具有明确数值计算来源，并非将未知字段或异常清零。',
              '这项检查仅确认实际公式及其数值行为，不能证明知识库参考窗对该样本/流程具有科学适用性。特别是清除操作时长与原表时间定义是否一致，仍需按来源核实。',
              '每份原始参考KB行、实际tau与偏差均保存在[详细JSON](per_answer.json)，可直接追查分数来源。', '',
              '[逐答案CSV](per_answer.csv) · [实际命令、输入哈希和检查](summary.json)', '']
    (args.out / 'README_zh.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['status', 'answers', 'counts', 'original_scores_equal', 'new_model_calls']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
