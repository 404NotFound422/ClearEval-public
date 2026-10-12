"""Offline route-filter diagnostic on all three frozen RI/storage deletion pairs.

The full-text judge runs already exist. This changes only the step comparison
pool, does not rerun a judge, and never replaces the primary paired CCE results.
"""
from pathlib import Path
import math
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as c

SOURCE = c.OUT / 'judges/local_controls_supplement_v2'
DEST = c.OUT / 'controls/paired_route_ablation_v3'


def equal(a, b):
    return a == b if a is None or b is None else math.isclose(a, b, abs_tol=1e-12)


def main():
    files = [SOURCE / n for n in ('cases.json', 'paired_results.json', 'step_results.json', 'step_config.json')]
    files += [c.OUT / 'reference_recovery/idisco_plus_2016/references_expanded_v3.json',
              Path(c.__file__), Path(__file__)]
    hashes = {str(p): c.filehash(p) for p in files}
    cases = {r['case_id']: r for r in c.read(files[0])['cases']}
    pairs = [p for p in c.read(files[1]) if p['condition'] == 'necessary_step_deletion']
    frozen_steps = {r['case_id']: r for r in c.read(files[2])}
    step_config = c.read(files[3])
    refs = c.read(files[4])['references']
    assert len(pairs) == 3 and sorted(p['question_id'] for p in pairs) == [2, 21, 22]
    assert step_config['adapter_sha256'] == c.filehash(c.__file__)
    plan = {'scope': 'offline_step_filter_diagnostic_on_existing_full_text_controls',
            'selection': 'All frozen necessary_step_deletion pairs, in their original order; no effect-based selection.',
            'pair_ids': [p['pair_id'] for p in pairs], 'threshold': .7,
            'reference_collection_sha256': hashes[str(files[4])],
            'input_sha256': hashes, 'new_judge_requests': 0, 'expert_confirmation': None,
            'primary_CCE_modified': False, 'formal_eligible': False}
    if (DEST / 'plan.json').exists():
        assert c.read(DEST / 'plan.json') == plan, 'Frozen diagnostic plan changed'
    else:
        c.write(DEST / 'plan.json', plan)
    encoder = c.Encoder()
    assert encoder.identity == step_config['encoder']
    records, details, paired = [], [], []
    for pair in pairs:
        sides = {}
        for side in ('baseline', 'variant'):
            case = cases[pair[side + '_case_id']]
            assert c.digest(case['model_response']) == case['answer_sha256']
            old = frozen_steps[case['case_id']]
            assert old['answer_sha256'] == case['answer_sha256']
            filtered = c.score_steps(case, refs, encoder, .7)
            assert filtered['generated_steps'] == old['step_result']['generated_steps']
            for metric in ('sr', 'sp'):
                assert equal(filtered[metric], old['step_result'][metric])
                assert equal(filtered[metric], pair[side + '_' + metric])
            candidates = [(i, r) for i, r in enumerate(refs) if case['question_id'] in r['question_ids']]
            scored = [(encoder.score(r, filtered['generated_steps'], .7), r, i) for i, r in candidates]
            result, chosen, index = max(scored, key=lambda x: (x[0]['sr'], x[0]['sp'], -x[2]))
            record = {'pair_id': pair['pair_id'], 'side': side, 'case_id': case['case_id'],
                'question_id': case['question_id'], 'answer_sha256': case['answer_sha256'],
                'question_sha256': case['question_sha256'], 'declared_route': filtered['route_id'],
                'filtered_reference_id': filtered['reference_id'],
                'filtered_sr': filtered['sr'], 'filtered_sp': filtered['sp'],
                'unfiltered_reference_id': chosen['reference_id'], 'unfiltered_route': chosen['route_id'],
                'unfiltered_sr': result['sr'], 'unfiltered_sp': result['sp'],
                'unfiltered_borrows_other_route': chosen['route_id'] != filtered['route_id'],
                'parsed_step_n': len(filtered['generated_steps']),
                'primary_filtered_values_exactly_reproduced': True, 'formal_eligible': False}
            records.append(record)
            details.append({'case_id': case['case_id'], 'filtered': filtered,
                            'unfiltered': result, 'unfiltered_reference_id': chosen['reference_id'],
                            'all_candidate_results': [{'reference_id': r['reference_id'], 'score': s, 'fixed_index': i}
                                                       for s, r, i in scored]})
            sides[side] = record
        row = {'pair_id': pair['pair_id'], 'question_id': pair['question_id'], 'formal_eligible': False}
        for setting in ('filtered', 'unfiltered'):
            for metric in ('sr', 'sp'):
                for side in ('baseline', 'variant'):
                    row[f'{setting}_{side}_{metric}'] = sides[side][f'{setting}_{metric}']
                row[f'{setting}_delta_{metric}'] = sides['variant'][f'{setting}_{metric}'] - sides['baseline'][f'{setting}_{metric}']
        row['delta_sr_difference_unfiltered_minus_filtered'] = row['unfiltered_delta_sr'] - row['filtered_delta_sr']
        row['unfiltered_baseline_reference'] = sides['baseline']['unfiltered_reference_id']
        row['unfiltered_variant_reference'] = sides['variant']['unfiltered_reference_id']
        row['any_cross_route_selection'] = any(r['unfiltered_borrows_other_route'] for r in sides.values())
        paired.append(row)
    assert all(c.filehash(p) == hashes[str(p)] for p in files)
    c.write(DEST / 'per_case.json', records)
    c.table(DEST / 'per_case.csv', records)
    c.write(DEST / 'step_details.json', details)
    c.write(DEST / 'paired_results.json', paired)
    c.table(DEST / 'paired_results.csv', paired)
    summary = {'scope': plan['scope'], 'pairs': len(paired), 'full_texts': len(records),
        'filtered_deletion_sr_drop_pairs': sum(r['filtered_delta_sr'] < 0 for r in paired),
        'unfiltered_deletion_sr_drop_pairs': sum(r['unfiltered_delta_sr'] < 0 for r in paired),
        'pairs_with_cross_route_selection': sum(r['any_cross_route_selection'] for r in paired),
        'pairs_with_different_deletion_sr_delta': sum(not equal(r['filtered_delta_sr'], r['unfiltered_delta_sr']) for r in paired),
        'all_old_filtered_values_reproduced': True, 'protected_inputs_unchanged': True,
        'new_judge_requests': 0, 'new_independent_control_pairs': 0, 'formal_eligible': False,
        'scientific_limitation': 'Source candidates and edit necessity lack expert confirmation. This is not a new full-pipeline judge experiment or proof that another route is task-compatible.',
        'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
        'input_sha256': hashes, 'plan_sha256': c.filehash(DEST / 'plan.json')}
    c.write(DEST / 'summary.json', summary)
    lines = ['# 既有删除变体上的路线筛选诊断', '',
        '事先固定取原 v2 全文受控实验中全部三个 RI/保存模块删除对，仅离线比较步骤参考筛选。原 judge 全文配对和 CCE 不改写，没有新增独立实验或请求。', '',
        '| 题号 | 筛选后 ΔSR | 不筛选 ΔSR | 发生跨路线选择 |', '|---|---:|---:|---|',
        *[f"| {r['question_id']} | {r['filtered_delta_sr']:.6f} | {r['unfiltered_delta_sr']:.6f} | {r['any_cross_route_selection']} |" for r in paired], '',
        '六份文本的原解析及筛选 SR/SP 均精确重现。参考候选和编辑必要性仍待专家确认；不筛选的数值只用于诊断，不回填缺失或 CCE。', '',
        '[逐对数据](paired_results.csv) · [逐文本](per_case.csv) · [步骤相似度](step_details.json) · [冻结规则](plan.json)', '',
        '实际命令：', '', '```powershell', summary['command'], '```', '']
    (DEST / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print({k: v for k, v in summary.items() if k not in ('input_sha256', 'scientific_limitation')})


if __name__ == '__main__':
    main()
