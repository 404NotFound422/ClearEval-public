"""Build the current handoff from completed, version-bound local result files."""
from __future__ import annotations
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
sys.dont_write_bytecode = True
import cce_round2_budget as budget
import cce_judges as io
import cce_plot_four_hour_evidence_v1 as files

R = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010'
DELIVERY = R / 'four_hour_extension_20261010/delivery'
DIRECT = ['c_param','co_order','co_method','co_param','co_chem']
NAMES = {'development':'开发5份', 'E2':'受控全文', 'Qwen_repeats':'Qwen真实重复', 'Codex':'Codex真实重复',
         'first7_posthoc':'首7份确认', 'secondary8_posthoc':'追加8份确认'}


def complete(row):
    return all(files.finite(row[key]) for key in ['Com','Cor','Eff'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uniform', type=Path, required=True)
    p.add_argument('--joint', type=Path, required=True)
    p.add_argument('--partial', type=Path, required=True)
    p.add_argument('--out', type=Path, default=DELIVERY / 'current_readout_v2')
    args = p.parse_args()
    assert not args.out.exists()
    paths = [args.uniform / x for x in ['summary.json','cells.json','verification.json','implementation_addendum.json']]
    paths += [args.joint / x for x in ['summary.json','per_answer.json','verification.json']]
    paths += [args.partial / x for x in ['summary.json','per_answer_bounds.json','verification.json']]
    paths += [R / 'four_hour_extension_20261010/authorization.json', budget.AUTH, budget.LEDGER,
              R / 'grounded_controls_v11/per_pair.json', R / 'grounded_controls_v11/cases.json',
              R / 'legacy_alternative_alias_v1/actual_01/summary.json',
              ROOT / 'artifacts/cce_validation/reference_recovery/development_binding_followup_v1/alternative_coverage_facts.json',
              ROOT / 'artifacts/cce_validation/wetlab/wetlab_status.json',
              ROOT / 'artifacts/cce_validation/human_review/CURRENT_REVIEW_ENTRY.md']
    bindings = [files.bind(path) for path in paths]
    uniform = io.read(args.uniform / 'summary.json')
    cells = io.read(args.uniform / 'cells.json')
    joint = io.read(args.joint / 'summary.json')
    joint_rows = io.read(args.joint / 'per_answer.json')
    partial = io.read(args.partial / 'summary.json')
    auth = io.read(R / 'four_hour_extension_20261010/authorization.json')
    counts = {key: value for key, value in budget.counts().items() if key != 'requests'}
    assert counts['package'] <= 394 and counts['round'] <= 100
    actual = [r for r in cells if not r.get('cancelled_no_raw')]
    assert len(actual) == uniform['raw_returns'] == 67
    assert len(cells) == 68 and len(joint_rows) == 10
    stable = DIRECT + ['Com','Cor','sr','sp']
    assert all(all(r['posthoc_metrics'][key] == r['frozen_fw3_metrics'][key] for key in stable) for r in actual)
    table = []
    for cohort, summary in uniform['cohorts'].items():
        group = [r for r in actual if r['cohort'] == cohort]
        table.append(dict(cohort=cohort, name=NAMES[cohort], raw=len(group), planned=summary['planned_slots'],
                          frozen_fw3_CCE=sum(complete(r['frozen_fw3_metrics']) for r in group),
                          posthoc_CCE=sum(complete(r['posthoc_metrics']) for r in group),
                          posthoc_label=sum(files.finite(r['posthoc_metrics']['s_label']) for r in group),
                          posthoc_time=sum(files.finite(r['posthoc_metrics']['s_time']) for r in group),
                          original_status_counts=summary['original_status_counts']))
    e2 = [r for r in actual if r['cohort'] == 'E2']
    by_anonymous = {r['anonymous_answer_id']:r for r in e2}
    source_cases = io.read(R / 'grounded_controls_v11/cases.json')['cases']
    lookup = {case['case_id']:by_anonymous[case['anonymous_answer_id']] for case in source_cases}
    assert len(lookup) == len(by_anonymous) == 21
    pairs = io.read(R / 'grounded_controls_v11/per_pair.json')
    pair_rows = []
    for pair in pairs:
        a, b = [lookup[pair[key]] for key in ['baseline_case_id','variant_case_id']]
        values = dict(pair_id=pair['pair_id'], question_id=pair['question_id'], condition=pair['condition'],
                      complete_CCE_pair=complete(a['posthoc_metrics']) and complete(b['posthoc_metrics']))
        for metric in a['posthoc_metrics']:
            left, right = a['posthoc_metrics'][metric], b['posthoc_metrics'][metric]
            values.update({f'baseline_{metric}':left, f'variant_{metric}':right,
                           f'delta_{metric}':right-left if files.finite(left) and files.finite(right) else None})
        pair_rows.append(values)
    assert len(pair_rows) == 15
    aliases = io.read(R / 'legacy_alternative_alias_v1/actual_01/summary.json')
    alternative_original = io.read(ROOT / 'artifacts/cce_validation/reference_recovery/development_binding_followup_v1/alternative_coverage_facts.json')['summary']
    alternative_total = dict(candidate_pairs=alternative_original['actual_pairs'],
                             original_numeric_pairs=alternative_original['numeric_cce_complete_pairs'],
                             posthoc_numeric_pairs=alternative_original['numeric_cce_complete_pairs'] + aliases['posthoc_complete_pairs'] - aliases['original_complete_pairs'],
                             alias_subset_pairs=6, alias_subset_numeric_pairs=aliases['posthoc_complete_pairs'],
                             source_guided_q248_numeric_pairs=1, expert_confirmed_pairs=0,
                             scope='Historical configurations only; nine raw alias returns form six of the nine inventory pairs; do not pool with current Qwen27b')
    wet = io.read(ROOT / 'artifacts/cce_validation/wetlab/wetlab_status.json')
    output = dict(status='current_completed_computations_with_scientific_dependencies',
                  generated_utc=datetime.now(timezone.utc).isoformat(), overall_research_goal_complete=False,
                  deadline_utc=auth['deadline_utc'], calls=counts,
                  calls_added_in_four_hour_window=counts['package']-auth['starting_counts']['package'],
                  uniform_processor=uniform['scorer_version'], uniform_raw_returns=67, cancelled_slots=1,
                  all67_direct_Com_Cor_SR_SP_equal_frozen_fw3=True, cohorts=table,
                  E2_actual_pairs=15, E2_complete_CCE_pairs=sum(r['complete_CCE_pair'] for r in pair_rows),
                  secondary_E5=joint, partial_joint=partial,
                  legacy_alias_replay=aliases, alternative_inventory=alternative_total, wetlab=wet, expert_answers_returned=0,
                  current_readout_not_new_model_observations=True)
    args.out.mkdir(parents=True)
    io.save(args.out / 'summary.json', output)
    files.csvwrite(args.out / 'cohorts.csv', table)
    files.csvwrite(args.out / 'E2_all_pairs.csv', pair_rows)
    lines = ['# 本轮最终统一处理的真实数值', '',
             f"处理器：`{uniform['scorer_version']}`。同一配置处理67份已有返回，另保留1个取消槽；新增模型请求0。",
             '五个直接评分、Com、Cor、SR/SP逐值等于冻结fw3；提取来源修复影响的EGES与联合值单独列示。', '',
             '|数据组|实际返回/计划|冻结fw3完整CCE|本版完整CCE|本版label可用|本版time可用|',
             '|---|---:|---:|---:|---:|---:|']
    for row in table:
        lines.append(f"|{row['name']}|{row['raw']}/{row['planned']}|{row['frozen_fw3_CCE']}|{row['posthoc_CCE']}|{row['posthoc_label']}|{row['posthoc_time']}|")
    lines += ['',f"E2完整CCE配对为{output['E2_complete_CCE_pairs']}/15；所有15对的可得分项及原SR/SP仍逐对保留。",
              '',f"固定两生成器五题的后验完整CCE为{joint['complete_CCE']}/10，共同完整题集为{joint['common_question_ids']}（{joint['common_n']}/5）。",
              f"完整题集的任务bootstrap状态：`{joint['task_bootstrap_status']}`；来源家族状态：`{joint['family_bootstrap_status']}`。",
              '形式资格仍继承条件性标记false，不能把formal Q*=0解释成来源一律不适用。', '',
              '|生成器|平均Com|平均Cor|平均Eff允许外界|平均逐题IA允许外界|平均逐题HV允许外界|',
              '|---|---:|---:|---|---|---|']
    for model, values in partial['mean_bounds'].items():
        intervals = [f"[{values[key][0]:.6f}, {values[key][1]:.6f}]" for key in ['Eff','IA','HV']]
        lines.append(f"|{model}|{values['Com'][0]:.6f}|{values['Cor'][0]:.6f}|"+'|'.join(intervals)+'|')
    lines += ['', '允许外界来自未知归一化分项原范围，不是置信区间，不替代缺失点值。IA/HV逐答案求界后平均。',
              '两个生成器Com与Cor方向相反，因此在本两模型五题队列中必互不支配；此条件性结论不依赖未知Eff的中点。', '',
              f"历史替代路线总计{alternative_total['candidate_pairs']}对、数值完整{alternative_total['posthoc_numeric_pairs']}对；其中别名恢复子批6对均完整，另q248一对完整，q1/q2仍缺项。这个历史盘点不与当前67份评分合并。", '',
              f"台账{counts['package']}/394，本轮{counts['round']}/100，四小时新增{output['calls_added_in_four_hour_window']}次。",
              f"分阶段已用：{counts['phase']}。没有因离线回放、绘图或重采样再调用模型。",
              '一位专家5＋15仍回传0/20；湿实验真实观察0。原始状态、失败、取消和旧分数都保留。', '',
              '[逐组CSV](cohorts.csv) · [全部15对当前分项](E2_all_pairs.csv) · [完整摘要](summary.json) · [输入来源与命令](verification.json)', '']
    (args.out / 'README_zh.md').write_text('\n'.join(lines), encoding='utf8')
    assert bindings == [files.bind(Path(row['path'])) for row in bindings]
    io.save(args.out / 'verification.json', dict(status='pass', bindings=bindings, script=files.bind(Path(__file__)),
                  actual_command=[sys.executable,*sys.argv], all67_direct_and_step_metrics_unchanged=True,
                  same_processor_every_cell=True, expert_returns_not_inferred=True, new_model_requests=0))
    print(json.dumps(dict(status='completed', out=str(args.out), cohorts=table,
                          E2_pairs=output['E2_complete_CCE_pairs'], E5_complete=joint['complete_CCE'],
                          E5_common=joint['common_n'], calls=counts), ensure_ascii=False))


if __name__ == '__main__':
    main()
