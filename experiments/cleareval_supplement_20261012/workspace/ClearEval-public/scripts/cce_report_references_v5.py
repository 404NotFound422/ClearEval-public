"""Publish completed v5 reference and fixed-holdout metadata without opening heldout content."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
HIST = BASE / 'historical_reports/followup_at_89'
V5 = BASE / 'expanded_references_v5'
ANA = BASE / 'analysis_expanded_references_v5'
HOLD = BASE / 'judges/local_extraction_holdout_v1'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write(p, text):
    Path(p).write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    analysis = read(ANA / 'analysis_run.json')
    hold = read(HOLD / 'completion_summary.json')
    assert analysis['status'] == 'pass'
    assert read(V5 / 'run.json')['status'] == 'complete_pass'
    qa = read(BASE / 'figures_expanded_references_v5/figure_visual_qa.json')
    assert qa['status'] == 'pass'
    for name, digest in qa['files_sha256'].items():
        assert sha(BASE / 'figures_expanded_references_v5' / name) == digest
    attachment_check = read(HOLD / 'attachment_verification.json')
    assert attachment_check['status'] == 'pass' and attachment_check['attachments'] == 15
    assert attachment_check['expert_fields_empty'] and attachment_check['original_160_row_form_unchanged']
    for item in attachment_check['packet_bindings']:
        assert sha(item['path']) == item['sha256']
    assert hold['selected_cells'] == 15 and hold['expert_returns'] == hold['faithful_corrections'] == 0
    assert hold['pending_cells'] + hold['successful_cells'] + hold['failed_cells'] == 15
    assert hold['numeric_CCE'] == 0 and hold['references_covered'] == 0
    rows = read(BASE / 'expanded_references_v5_t070_per_answer.json')
    delta = next(r for r in rows if r['answer_id'] == 'openai_deepseek-chat__q1')
    thresholds = []
    for t in ('060', '070', '080'):
        row = next(r for r in read(BASE / f'expanded_references_v5_t{t}_per_answer.json')
                   if r['answer_id'] == delta['answer_id'])
        thresholds.append({k: row[k] for k in ('threshold', 'sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV')})
    ledger = [r for r in (json.loads(x) for x in (BASE / 'judges/request_ledger.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip())
              if r.get('event') == 'request_started']
    oldledger = [json.loads(x) for x in (HIST / 'request_ledger_at_89.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert ledger[:89] == oldledger
    used = len(ledger)
    assert used == 89 + hold['new_requests'] == hold['package_requests']
    assert 0 <= hold['new_requests'] <= 15
    snapshot = read(HIST / 'snapshot_manifest.json')
    for rel, digest in snapshot['files_sha256'].items():
        assert sha(HIST / rel) == digest, rel
    joint = read(ANA / 'joint_summary.json')
    assert joint['revised_full_fixed_cohort']['common_n'] == 0
    assert joint['pilot_participating_subset']['common_n'] == 5
    assert analysis['old_component_rows_verified'] == 77
    ref = read(V5 / 'references.json')
    ref_count = len(ref['references']) if isinstance(ref, dict) else len(ref)
    family_n = len({r.get('family_id') for r in rows if r.get('family_id') and r.get('sr') is not None})
    n = analysis['numeric_CCE']
    failure_categories = hold.get('failure_reason_categories', {})
    failure_zh = '、'.join(f'{key} {value} 份' for key, value in failure_categories.items()) or '无'
    failure_en = ', '.join(f'{key}: {value}' for key, value in failure_categories.items()) or 'none'
    matrix = '\n'.join(f"| {r['threshold']:.1f} | {r['sr']:.6f} | {r['sp']:.6f} | {r['Com']:.6f} | {r['IA']:.6f} | {r['HV']:.6f} |" for r in thresholds)
    zh = f"""# 当前补充结果：v5 条件性参考扩展与固定留出提取

主评分仍为 6 题、13 个固定模型、77 份真实存档答案；新加入有作者原文的 q1 uDISCO 清除范围参考后，暂定步骤分数和完整数值 CCE 均由 38 增至 {n}，其余 {77-n} 份缺口保留。新增评分不调用 judge，77 份原参数完整性、Correctness 和 EGES 均逐行保留。65 行原对象复用，11 行只刷新 uDISCO 路线识别元数据且仍缺适用题目参考，1 行获得新评分；其余 76 行数值及 NA 经原 core 核对不变。[主逐答案 CSV](expanded_references_v5_t070_per_answer.csv)、[JSON](expanded_references_v5_t070_per_answer.json)、[参考与执行证据](expanded_references_v5/README.md)。

新增答案为 DeepSeek Chat 的 q1 原存档全文，主阈值 0.7 下 SR={delta['sr']:.6f}、SP={delta['sp']:.6f}、Com={delta['Com']:.6f}，原 Cor={delta['Cor']:.6f}、Eff={delta['Eff']:.6f}，IA={delta['IA']:.6f}、HV={delta['HV']:.6f}。这些值复用原存档分项，不能与后续 Qwen 全文重评的分项混为同一实验。它是 16 段非空英文答案，最高参考匹配相似度约 0.660069，未发生编码截断；主阈值零匹配不表示没有操作，也不证明所有操作科学无效。

| 阈值 | SR | SP | Com | IA | HV |
|---|---|---|---|---|---|
{matrix}

本批只增加条件性清除范围：作者第 03–11 项共 9 个操作；初洗、去膜是尚未确认的起点前提，终末保存是持续条件。全脑活动标记适用性和来源版本冲突仍待确认。当前 {ref_count} 个任务绑定参考分支、{family_n} 个有数值结果的来源家族均保持暂定，正式合格答案仍为 0。来源恢复、机器检查和专家确认分别记账，完整参考建设不占 20 份局部人审名额。[作者原文恢复](reference_recovery/udisco_2016/README.md)、[q1 来源与匹配核查](judges/local_alternative_q1_v1/review.md)、[单列建设台账](human_review/reference_construction_v2/README.md)。

固定 15 份留出完成 {hold['attempted_cells']} 次尝试，{hold['successful_cells']} 份技术成功、{hold['failed_cells']} 份失败、{hold['pending_cells']} 份未运行；实际绑定核验 {hold['identity_verified_cells']} 份。新请求 {hold['new_requests']} 次，全包累计 {used}/300，剩余 {300-used}。使用开发阶段冻结的 Qwen 配置，未按留出返回改提示词、字段规则、阈值或样本。原始全文与返回封存在本地，匿名候选附件仅供同一专家 ASSISTED 审阅；这不是独立盲评。专家回传、忠实字段修正和修正效果仍为待定。[技术完成统计](judges/local_extraction_holdout_v1/completion_summary.json)、[实际命令](judges/local_extraction_holdout_v1/EXECUTION.md)。

失败类别为 {failure_zh}。原始返回均保留，未做别名修补、重试或结果驱动的配置调整；失败项仍可供专家阅读原答案，但没有伪造自动字段。这说明冻结流程在该预设留出集合的技术覆盖有限，报告分母应保留全部 15 份；成功子集不能代表全库提取准确率。

这 15 份的完整步骤参考覆盖为 0，来源家族均未映射，因此本批 SR/SP/Com/IA/HV 不计为已完成，也不能据此声称留出来源家族独立。20 份共享人工名额仍为 5 开发＋15 留出、1 位专家；机器候选不填入专家结论。技术成功只说明得到可加载的返回，不能作为提取准确性结果。[20 份共用审阅入口](human_review/CURRENT_REVIEW_ENTRY.md)。

全库仍有 3,288 份真实存档答案，对应 3,289 个固定模型—题目位置。全模型共同可评分集合 Q* 仍为空，正式排名和正式 Pareto 结论不成立。预先固定的双 Gemini 五题子集、其 IA/HV、三维支配关系及 2,000 次单来源家族重采样与 v4 完全相同；经输入核对复用，未计为新独立观测。单家族重采样的零宽区间仍不能证明泛化。[联合分析](analysis_expanded_references_v5/joint_summary.json)、[全库分项覆盖](analysis_expanded_references_v5/revised_component_coverage.csv)、[阈值比较](analysis_expanded_references_v5/threshold_sensitivity.json)。

论文可据本轮报告“原分项不变时，来源补齐使一份答案由参考不足转为可计算；非空英文答案仍可能得到零步骤匹配”。先前结果继续成立：15 对受控全文比较显示部分删除和顺序冲突未触发评分下降；6 个任务已有开发路线比较（5 个自然答案任务、1 个来源指导编辑任务），科学适用性确认仍为 0；六次 Llama 提示词干预消除完整示例复制，却保留直接提取矛盾，且重复波动仍为零。后者支持把重复性与准确性分开报告。

[参考扩展图](figures_expanded_references_v5/udisco_reference_expansion.png)、[SVG](figures_expanded_references_v5/udisco_reference_expansion.svg)、[PDF](figures_expanded_references_v5/udisco_reference_expansion.pdf)、[逐图数据](figures_expanded_references_v5/udisco_reference_expansion.csv)、[覆盖图](figures_expanded_references_v5/coverage.png)、[阈值图](figures_expanded_references_v5/threshold_sensitivity.png)、[CCE 三投影](figures_expanded_references_v5/development_cce_projections.png)。

本批已核对附件身份、来源台账与论文证据链接。尚待同一专家回传和完整路线适用性确认；湿实验真实测量仍为 0，现有计划、42 个假设功效情景和分析入口保留。正式人评一致性和经核查字段修正影响只在真实回传后运行。下面保留 89 次请求时的阶段报告，其数量属于当时快照，不替代上述当前统计。

---

"""
    write(BASE / 'RESULTS_zh.md', zh + (HIST / 'RESULTS_zh.md').read_text(encoding='utf-8-sig'))
    english = f"""# Current supplementary Methods and Results

We retained the fixed 13-model, six-task cohort and all 77 archived answers. A frozen reference update added a conditional nine-operation uDISCO clearing projection from the author protocol. Initial washing and meningeal removal remained unconfirmed starting prerequisites; terminal storage remained a continuing condition. Whole-brain activity-label applicability and source-version discrepancies were not resolved by this projection. The same original SR/SP core and thresholds 0.6, 0.7 and 0.8 were applied, preserving all archived parameter, correctness and EGES components. Sixty-five row objects were reused, eleven received route-identification metadata updates without numeric changes, and one acquired step and joint scores. All other 76 numeric/NA rows were verified unchanged. No new judge calls were used for this reference update.

Provisional step and complete numeric CCE coverage increased from 38 to {n} of 77 answers. At the primary threshold, the added archived q1 answer had SR {delta['sr']:.6f}, SP {delta['sp']:.6f}, Com {delta['Com']:.6f}, Cor {delta['Cor']:.6f}, Eff {delta['Eff']:.6f}, IA {delta['IA']:.6f} and HV {delta['HV']:.6f}. These values use archived components, distinct from the later local-judge natural-route diagnostic. The English answer contained 16 nonempty segments; maximum reference similarity was approximately 0.660069 without truncation. Zero matching therefore did not imply an empty protocol. Across the full archive, the fixed-cohort common set remained empty. The prespecified Gemini subset, three-dimensional dominance relation and 2,000 single-family bootstrap draws were reused after verifying unchanged inputs. The single-family bootstrap remained degenerate and offered no generalization evidence.

After freezing the development configuration, we attempted {hold['attempted_cells']} of the 15 prespecified holdout answers using the unchanged local Qwen contract, one attempt per answer. There were {hold['successful_cells']} technical successes, {hold['failed_cells']} failures and {hold['pending_cells']} unrun cells. Failure categories were {failure_en}. Raw returns were retained separately without retries or post-hoc schema repair, and anonymized suggestions were prepared for the same expert under ASSISTED review. Holdout returns were not used to modify the prompt, field definitions, matching threshold or selection. No expert conclusions or faithful corrections were fabricated. All 15 lacked an active complete reference and had unmapped source families, so this step added no SR/SP or joint-score results and did not establish source-family independence. Technical completion is not extraction accuracy. The batch used {hold['new_requests']} new requests, bringing the package total to {used}/300.

Earlier full-text controls, the two-family stability batch, six-task alternative-route development comparisons and subsequent one-family prompt intervention remain separately versioned. Removing the final worked example eliminated whole-example copying and route mismatches in six Llama returns, while explicit labeling and RI contradictions persisted in all six despite zero repeat variation. Expert correction effects, scientifically confirmed alternative-route acceptance and wet-lab outcomes remain unresolved.

Current numerical evidence: [per-answer scores](expanded_references_v5_t070_per_answer.csv), [joint analysis](analysis_expanded_references_v5/joint_summary.json), [holdout completion](judges/local_extraction_holdout_v1/completion_summary.json). The following historical Methods/Results describe the frozen 89-request stage and are retained for provenance.

---

"""
    write(BASE / 'Methods_Results_en.md', english + (HIST / 'Methods_Results_en.md').read_text(encoding='utf-8-sig'))
    abstract = f"""# Draft abstract: supplementary development evidence

Fixed-sample tissue-clearing protocol generation requires matching sample scale and labeling to imaging and preservation goals. ClearEval evaluates procedural requirements and tradeoffs through parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring (EGES). We added source-bound Step Recall and Step Precision while retaining these original components. Across 77 archived answers from 13 models and six tasks, candidate references from {family_n} source families yielded {n} provisional step and complete numeric CCE values. Adding a conditional author-derived uDISCO reference made one previously unresolved answer computable; its nonempty English protocol nevertheless received zero step matching at the primary threshold. The fixed-cohort common set remained empty, preventing a full-model revised-CCE ranking. Fifteen full-text controlled pairs revealed score nonresponses and segmentation sensitivity. Development route comparisons covered six tasks, with scientific applicability confirmation pending. A six-call prompt intervention removed whole-example copying but retained explicit labeling and RI extraction errors despite zero repeat variation. Fifteen fixed holdout attempts yielded {hold['successful_cells']} loadable outputs for assisted expert review, without complete reference coverage or expert corrections. These results expand traceable partial evaluation while distinguishing numerical repeatability, extraction fidelity and scientific validity. Expert correction effects and wet-lab outcomes remain unresolved.
"""
    write(BASE / 'Abstract_en.md', abstract)
    status = f"""# ClearEval r2 当前状态

新增 uDISCO 条件性参考评分已完成：77 份真实存档答案中暂定 CCE 从 38 增至 {n}；77 份原参数完整性、Correctness、EGES 不变。正式合格为 0，13 模型 Q* 仍为空。

固定 15 份留出：{hold['attempted_cells']} 次真实尝试，{hold['successful_cells']} 技术成功、{hold['failed_cells']} 失败、{hold['pending_cells']} 未运行，身份核验 {hold['identity_verified_cells']}。自动建议已封存供同一专家 ASSISTED 审阅；专家回传和忠实修正均为 0。来源参考覆盖 0/15，联合评分继续待定。

本批新增 {hold['new_requests']} 次本地模型请求，累计 {used}/300，剩余 {300-used}。新增参考评分与分析没有 judge 请求。六个任务的开发路线比较、15 对全文受控比较、旧双家族稳定性和六次 Llama 干预保留原版本；重复稳定不能证明提取准确。

真实结果与论文意义见 [RESULTS_zh.md](RESULTS_zh.md)，逐答案、来源与命令见 [机器入口](current_run_index.json) 和 [commands.md](commands.md)。89 次请求时的报告已[按字节归档](historical_reports/followup_at_89/snapshot_manifest.json)。

待补：一位专家的 5 开发＋15 留出局部核查、完整路线适用性确认、旧人评方法尺度依据、真实湿实验数据。湿实验计划和假设敏感性结果已保存。本批附件、来源建设台账及报告链接已核对；真实专家回传后计算对应字段修正影响。[共用审阅入口](human_review/CURRENT_REVIEW_ENTRY.md)。报告恢复命令：`python scripts/cce_report.py`。
"""
    write(BASE / 'STATUS.md', status)
    write(ROOT.parent / 'STATUS.md', status.replace('](', '](ClearEval-public/artifacts/cce_validation/'))
    budget = read(HIST / 'budget.json')
    budget.update(attempts_recorded=used, remaining_request_capacity=300-used,
                  model_attempts=dict(Counter(r['model'] for r in ledger)), ledger_sha256=sha(BASE / 'judges/request_ledger.jsonl'))
    save(BASE / 'budget.json', budget)
    dependencies = read(HIST / 'remaining_dependencies.json')
    dependencies.update(holdout_extraction=f"{hold['successful_cells']}/15 technical successes; real expert review pending; complete references 0/15; source families unmapped.",
        next_independent_work='Current batch metadata, attachments and report links are verified. Resume field-correction effects when real expert returns arrive; retain source gaps separately.',
        reference_validation=f'{ref_count} task-bound branches from {family_n} source families remain source-extracted conditional candidates, not expert-confirmed gold. Initial labeling/prerequisites, whole-brain activity-label applicability and unknown 3 mm schedules remain unresolved.',
        cohort_coverage={'answer_missing': 1, 'provisional_CCE_numeric': n,
                         'screened_reference_insufficient': 77-n, 'revised_steps_not_run': 3211},
        language_matching='English all-mpnet-base-v2 has not received independent local validation. Nonempty Chinese and English answers can score zero without truncation; threshold effects are development diagnostics.',
        extraction_effect=f'Five development auto identity replays and {hold["identity_verified_cells"]} successful holdout auto bindings are software/provenance checks. Expert-corrected effects and all expert conclusions remain pending; 8 holdout technical failures retained.',
        reference_v5='Conditional clearing scope only; initial prerequisites and whole-brain activity-label applicability pending.',
        expert_review='One expert, fixed 5 development + 15 holdout; zero actual returned conclusions and zero faithful corrections.')
    save(BASE / 'remaining_dependencies.json', dependencies)
    commands = """# 本阶段已实际执行的命令

工作目录为 `C:\\ClearEval\\ClearEval-public`。新增参考评分与原 core 核对的实际命令见 [v5 执行记录](expanded_references_v5/README.md)；15 份留出的真实本地调用和离线封存命令见 [留出执行记录](judges/local_extraction_holdout_v1/EXECUTION.md)。原始调用日志存放 sealed 目录，不在论文中公开字段和分数。

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_references_v5.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_report.py
```

上述分析与本报告生成均不产生模型请求。既有实际命令见 [89 请求时的命令快照](historical_reports/followup_at_89/commands.md)，历史报告中的数字属于其相应阶段。
"""
    write(BASE / 'commands.md', commands)
    source_files = [ANA / 'analysis_run.json', ANA / 'joint_summary.json', ANA / 'threshold_sensitivity.json',
        V5 / 'plan.json', V5 / 'references.json', V5 / 'verification.json', V5 / 'run.json',
        V5 / 'review_final_scores.json', V5 / 'review_analysis_report.json',
        HOLD / 'plan.json', HOLD / 'completion_summary.json', HOLD / 'execution_commands.json', HOLD / 'attachment_verification.json',
        BASE / 'human_review/reference_construction_v2/source_index.json',
        BASE / 'human_review/reference_construction_v2/summary.json',
        BASE / 'judges/request_ledger.jsonl', HIST / 'snapshot_manifest.json',
        BASE / 'figures_expanded_references_v5/figure_visual_qa.json',
        *[BASE / f'expanded_references_v5_t{t}_per_answer.json' for t in ('060', '070', '080')]]
    assert all(p.exists() for p in source_files)
    oldindex = read(HIST / 'current_run_index.json')
    index = {k: oldindex[k] for k in ('frozen_controls', 'frozen_stability', 'frozen_extraction', 'frozen_alternatives',
             'followup_alternative_q2', 'followup_prompt_intervention', 'followup_source_guided_q248', 'followup_natural_q1')}
    index.update(version='expanded_references_v5_plus_holdout_v1', report_stage='expanded_references_v5_plus_holdout_v1',
        main_scoring_stage='expanded_references_v5', formal_eligible=False,
        primary='expanded_references_v5_t070_per_answer.json',
        thresholds=[f'expanded_references_v5_t{t}_per_answer.json' for t in ('060', '070', '080')],
        reference='expanded_references_v5/references.json', plan='expanded_references_v5/plan.json',
        composition='expanded_references_v5/run.json', score_verification='expanded_references_v5/verification.json',
        analysis='analysis_expanded_references_v5/joint_summary.json',
        actual_counts={'actual_answers': 77, 'step_numeric': analysis['numeric_steps'], 'candidate_cce_numeric': n,
                       'formal_eligible': 0, 'question_ids': [1, 2, 21, 22, 23, 248], 'reference_branches': ref_count,
                       'source_families_with_numeric_rows': family_n},
        holdout_completion='judges/local_extraction_holdout_v1/completion_summary.json',
        request_attempts=used, new_model_requests=hold['new_requests'], main_scoring_new_model_requests=0,
        previous_report_index='historical_reports/followup_at_89/current_run_index.json',
        reference_construction='human_review/reference_construction_v2/source_index.json',
        figure_qa='figures_expanded_references_v5/figure_visual_qa.json',
        input_sha256={str(p.relative_to(BASE)).replace('\\', '/'): sha(p) for p in source_files})
    save(BASE / 'current_run_index.json', index)
    config = read(HIST / 'resolved_config_current.yaml')
    config['version'] = index['version']
    config['previous_configuration_snapshot'] = 'historical_reports/followup_at_89/resolved_config_current.yaml'
    config['composition_configuration'] = read(BASE / 'expanded_references_v5_t070_resolved_config.json')
    config['reference_extension_v5'] = {'plan': index['plan'], 'reference': index['reference'],
        'configuration': 'expanded_references_v5_t070_resolved_config.json',
        'original_archived_components_preserved': True}
    config['holdout_v1'] = {'plan': 'judges/local_extraction_holdout_v1/plan.json',
                          'plan_sha256': sha(HOLD / 'plan.json'), 'package_requests': used,
                          'configuration_tuned_on_holdout': False}
    config['row_configuration_hashes_preserved'] = False
    config['row_configuration_policy'] = '65 prior row objects reused; 11 route metadata refreshes and one newly scored row bound to v5 configuration; all original score components preserved.'
    config['current_execution'] = {'primary': index['primary'], 'reference': index['reference'],
                                   'analysis': index['analysis'], 'package_requests': used,
                                   'prior_execution_record': 'historical_reports/followup_at_89/resolved_config_current.yaml'}
    save(BASE / 'resolved_config_current.yaml', config)
    review_path = Path(hold['reviewer_attachment_dir'])
    if not review_path.is_absolute():
        review_path = ROOT / review_path if str(review_path).replace('\\', '/').startswith('artifacts/') else BASE / review_path
    assert review_path.is_dir()
    human = BASE / 'human_review'
    held_review_rel = os.path.relpath(review_path, human).replace('\\', '/')
    human_entry = f"""# 一位专家的 20 份共用审阅入口

固定名额不变：A01–A05 为开发，A06–A20 为留出；步骤对应与提取共用，不新增人审答案。

- 开发 5 份：[真实自动提取附件](rescoring/v4_dev_v2/reviewer/README.md)。
- 留出 15 份：[匿名 ASSISTED 附件]({held_review_rel}/README.md)。先读原题与原答案，再核对机器建议；不要把未填写解释成认可。
- [原 20 份全文与参考访问入口](reviewer/README.md)、[共用专家填写表](reviewer/review_items.csv)。仍是原 160 行，不预填专家结论。
- [回传字段与处理约定](EXPERT_RETURN_CONTRACT.md)。仅使用真实审阅记录计算修正影响；未核项保持待定。
- [完整参考建设单列台账](reference_construction_v2/README.md)。保留原历史记录，专家工时未知处留空，不占用 20 份局部核查预算。

显式模型身份元数据、机器总分与旧人评分数不在匿名附件中展示，原答案正文保留。审阅方式为 ASSISTED，不能称独立盲评。开发与留出分别报告；这 15 份来源家族尚未映射，步骤参考覆盖为 0，因此初始条件、路线与关键字段可先核，来源步骤匹配保持需补来源。完整参考建设与新增路线适用性确认另行记账。

当前专家回传 0、忠实字段修正 0；机器技术成功数量不代表准确性。主报告见 [当前结果](../RESULTS_zh.md)。
"""
    write(human / 'CURRENT_REVIEW_ENTRY.md', human_entry)
    index['human_review_entry'] = 'human_review/CURRENT_REVIEW_ENTRY.md'
    save(BASE / 'current_run_index.json', index)
    outputs = ['STATUS.md', 'RESULTS_zh.md', 'Methods_Results_en.md', 'Abstract_en.md', 'commands.md',
               'current_run_index.json', 'resolved_config_current.yaml', 'remaining_dependencies.json', 'budget.json',
               'human_review/CURRENT_REVIEW_ENTRY.md']
    broken = []
    link_n = 0
    for rel in outputs:
        if not rel.endswith('.md'):
            continue
        path = BASE / rel
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            link_n += 1
            if not (path.parent / target.split('#')[0]).exists():
                broken.append([rel, target])
    assert not broken, broken
    result = {'status': 'pass', 'package_requests': used, 'main_candidate_CCE': n,
        'main_scoring_new_requests': 0, 'holdout_new_requests': hold['new_requests'],
        'checked_local_links': link_n, 'snapshot_files_verified': len(snapshot['files_sha256']),
        'script_sha256': sha(__file__), 'dispatcher_sha256': sha(ROOT / 'scripts/cce_report.py'),
        'inputs_sha256': index['input_sha256'], 'outputs_sha256': {rel: sha(BASE / rel) for rel in outputs},
        'actual_command': [sys.executable, *sys.argv]}
    save(BASE / 'report_verification_references_v5.json', result)
    save(BASE / 'report_generation.json', {'version': index['version'], **result,
         'verification': 'report_verification_references_v5.json', 'generator': 'scripts/cce_report_references_v5.py'})
    save(BASE / 'current_activity.json', {'status': 'completed_stage_reported', 'package_requests': used,
         'primary_candidate_CCE': n, 'primary_actual_answers': 77,
         'holdout_completion_summary': index['holdout_completion'], 'report_verification': 'report_verification_references_v5.json'})
    print(json.dumps({k: result[k] for k in ('status', 'package_requests', 'main_candidate_CCE', 'checked_local_links')}))


if __name__ == '__main__':
    main()
