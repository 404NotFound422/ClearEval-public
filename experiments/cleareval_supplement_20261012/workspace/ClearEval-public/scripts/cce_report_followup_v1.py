"""Compose follow-up results over the byte-preserved v4 main scoring report."""
from pathlib import Path
from collections import Counter
import json
import re
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_judges as j
BASE = ROOT / 'artifacts/cce_validation'
HIST = BASE / 'historical_reports/expanded_tasks_v4_before_followup'
OUT = BASE / 'followup_experiments_v1'
Q2 = BASE / 'judges/local_alternative_q2_v1'
E4 = BASE / 'judges/stability_remediation_plan_v1'
Q248 = BASE / 'judges/local_alternative_q248_v1'
Q1 = BASE / 'judges/local_alternative_q1_v1'


def write(path, text):
    path.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    q2 = j.read(Q2 / 'development_summary.json')
    e4 = j.read(E4 / 'development_summary.json')
    pair = j.read(Q2 / 'paired_results.json')[0]['metrics']
    assert q2['new_requests_this_batch'] == 2 and e4['new_requests'] == 6
    assert j.read(Q2 / 'review.json')['status'] == 'pass_technical_provenance_and_numeric_replay_not_scientific_validation'
    assert j.read(E4 / 'analysis_verification.json')['status'] == 'pass'
    ledger = [r for r in j.ledger_rows(BASE / 'judges/request_ledger.jsonl') if r.get('event') == 'request_started']
    used = len(ledger)
    optional = j.read(Q248 / 'development_summary.json') if (Q248 / 'development_summary.json').exists() else None
    q1 = j.read(Q1 / 'development_summary.json') if (Q1 / 'development_summary.json').exists() else None
    new_calls = 8 + (optional['new_requests_this_batch'] if optional else 0) + (q1['new_requests_this_batch'] if q1 else 0)
    assert used == 77 + new_calls, 'An additional live batch must be accounted for explicitly before publishing current totals'
    old_ledger = j.ledger_rows(HIST / 'request_ledger_at_77.jsonl')
    assert len(old_ledger) == 77 and ledger[:77] == old_ledger
    main_index = j.read(HIST / 'current_run_index.json')
    frozen_main_input_n = len(main_index['input_sha256'])
    frozen_hashes = {p.name: j.filehash(p) for p in HIST.iterdir() if p.is_file() and p.name != 'snapshot_manifest.json'}
    j.save(HIST / 'snapshot_manifest.json', {'status': 'byte_preserved_before_followup_requests', 'files_sha256': frozen_hashes, 'ledger_requests': 77})
    for rel, sha in main_index['input_sha256'].items():
        path = HIST / 'request_ledger_at_77.jsonl' if rel == 'judges/request_ledger.jsonl' else BASE / rel
        assert j.filehash(path) == sha, rel
    extra_zh = ''
    extra_en = ''
    task_n = 4
    phase_label = 'q2 自然存档路线比较与 Llama 提示词干预'
    next_work = 'q248／q1 的条件性第二路线开发比较'
    if optional:
        task_n += 1
        phase_label += '，并完成 q248 来源指导的路线编辑配对'
        next_work = 'q1 的条件性第二路线开发比较'
        qm = j.read(Q248 / 'paired_results.json')[0]['metrics']
        extra_zh = f"\nq248 另完成源引导的下游路线编辑批次：{optional['technical_successful_cases']} 份技术成功、{optional['technical_completed_candidate_pairs']} 对技术完成、{optional['complete_candidate_cce_pairs']} 对完整数值 CCE。FDISCO 基线至 PEGASOS 编辑稿的 SR 为 {qm['sr']['baseline']:.6f}→{qm['sr']['alternative']:.6f}，Com 为 {qm['Com']['baseline']:.6f}→{qm['Com']['alternative']:.6f}，Cor 均为 1；Eff／IA 为 {qm['Eff']['baseline']:.6f}→{qm['Eff']['alternative']:.6f}，HV 为 {qm['HV']['baseline']:.6f}→{qm['HV']['alternative']:.6f}，s_label 均为 0。这些是保留模型实际提取的原公式输出，不是实验效果。该变体由既有作者参考构建，属于源引导开发材料；不能当作新增自然存档答案，也不能以参考相关的步骤覆盖证明科学有效性。两份返回的 RI／时长还需结合原文直接核查，路线与整例复制筛查通过不等于提取正确。详见 [q248 完整结果](judges/local_alternative_q248_v1/README.md)与[逐判项](judges/local_alternative_q248_v1/paired_results.json)。\n"
        extra_en = f" An additional source-guided q248 pair produced {optional['technical_completed_candidate_pairs']} technically complete pair and {optional['complete_candidate_cce_pairs']} complete numeric CCE pair. SR increased from {qm['sr']['baseline']:.6f} to {qm['sr']['alternative']:.6f} and Com from {qm['Com']['baseline']:.6f} to {qm['Com']['alternative']:.6f}, while Eff and IA decreased from {qm['Eff']['baseline']:.6f} to {qm['Eff']['alternative']:.6f}; HV decreased from {qm['HV']['baseline']:.6f} to {qm['HV']['alternative']:.6f}. These retain the actual model extractions and do not establish experimental performance or extraction fidelity. It is not an additional naturally archived route answer, and source-derived coverage is not independent scientific validation."
        if (Q248 / 'review/independent_review.json').exists():
            assert j.read(Q248 / 'review/independent_review.json')['status'] == 'pass_identity_numerical_replay_with_extraction_limitations'
            extra_zh += '\nq248 局部独立核查已重放原 EGES，并发现两份返回均写入原答案未明示的 RI=1.48，时间提取也有原文依据问题。PEGASOS 的已知数值阶段合计 154 h，另有未知 brief rinse；返回 192 h 不能据此验证，154 h 也不能直接当作完整精确时间的专家纠正值。s_trans 使用冻结方法／组织 RI 代理，提取出的 1.48 未参与该项，不能把 s_trans 差异归因于这个错误。两份 s_label=0 来自当前通用文本目标匹配后取最小值，部分兼容证据仍未知；MAP2 推荐不是题干强制标签，也不是此零分的直接原因。变体八个作者操作中，保存操作虽明确出现，其最高相似度为 0.653706，低于 0.7，故 SR/SP 为 7/8；brief rinse 已匹配。不能把这个阈值未匹配解释为生物学步骤被遗漏。原提取与分数均保留，[独立核查](judges/local_alternative_q248_v1/review/independent_review.json)不计作专家回传。\n'
            extra_en += ' A local review found unsupported RI and time extractions in both returns. The reagent RI extraction did not drive s_trans, which used the frozen method/tissue proxy. The source-guided storage operation was present but failed the 0.7 matching threshold (maximum similarity 0.653706), yielding 7/8 coverage; this was not a demonstrated omitted operation. These checks retained the original outputs and were not expert labels.'
    if q1:
        task_n += 1
        phase_label += '及 q1 自然存档路线配对'
        next_work = '固定 15 份留出的盲处理准备与自动提取封存'
        q1m = j.read(Q1 / 'paired_results.json')[0]['metrics']
        extra_zh += f"\nq1 的 iDISCO+／uDISCO 两份自然答案也完成同配置全文重评：2 份技术成功、1 对技术完成、完整数值 CCE 对为 0。SR 为 {q1m['sr']['baseline']:.6f}／{q1m['sr']['alternative']:.6f}，SP 为 {q1m['sp']['baseline']:.6f}／{q1m['sp']['alternative']:.6f}，Com 为 {q1m['Com']['baseline']:.6f}／{q1m['Com']['alternative']:.6f}，Cor 均为 1；两份 s_label 为 NA，Eff／IA／HV 保持 NA。uDISCO 仅对作者第 03–11 项做条件性清除范围投影，初洗与去膜为未确认的起点前提，保存保留为持续条件；全脑活动标记适用性及作者版本差异没有被自动解决。[逐判项](judges/local_alternative_q1_v1/paired_results.json)。\n"
        extra_zh += '\nq1 独立核查定位了两份时间提取与原答案不符、以及 uDISCO 无答案依据的 RI 值，保留原输出。uDISCO 的 SR/SP=0 来自所有参考最大相似度低于 0.7：原答案是英文，有 16 个非空解析段，最高相似度 0.660069；编码与模型输出均无截断。不能将零匹配解释为无步骤，也不能仅凭这个数值判定所有操作科学无效。iDISCO+ 有 32 个解析段，参考匹配 6/9、生成匹配 2/32。[独立核查](judges/local_alternative_q1_v1/review.md)。\n'
        extra_en += f" The q1 iDISCO+/uDISCO natural-answer pair also completed technically, with Com {q1m['Com']['baseline']:.6f}/{q1m['Com']['alternative']:.6f} and unresolved Eff/IA/HV in both answers. The uDISCO projection retained nine author clearing operations and unconfirmed start prerequisites. Its English answer contained 16 nonempty segments without truncation, but maximum step similarity was 0.660069, below 0.7; zero matching cannot be interpreted as an empty protocol. Direct time and RI extraction discrepancies were retained in a separate local review."
    target_statement = ('开发性比较已覆盖 6 个不同任务（5 个自然答案任务＋1 个来源指导编辑任务），但 6–8 个科学适用性已确认的完整替代对目标仍未完成。' if task_n >= 6 else '6–8 个不同任务的合格完整替代路线尚未完成。')
    zh = f"""# v4 后续真实实验结果

新增 {phase_label}，共 {new_calls} 次真实请求；累计 {used}/300，剩余 {300-used}。v4 主评分仍为 6 题、77 份存档答案、38 份暂定 CCE；本轮诊断没有覆盖或替换这些主评分。

q2 的 FDISCO／iDISCO+ 两份全文使用同一 Qwen 配置和共同参考输入重新提取、评分，2/2 技术成功，1 对技术完成。SR 为 {pair['sr']['baseline']:.6f}／{pair['sr']['alternative']:.6f}，SP 为 {pair['sp']['baseline']:.6f}／{pair['sp']['alternative']:.6f}，Com 为 {pair['Com']['baseline']:.6f}／{pair['Com']['alternative']:.6f}，Cor 均为 1。两份 s_label 均为 NA，因此 Eff、IA、HV 也为 NA，完整 CCE 对为 0。FDISCO 返回的三种核染名称缺少目标信息；iDISCO+ 的部分标记—荧光组合在冻结兼容性证据中为 UNKNOWN。这些是不同的缺口，不归为完整步骤参考缺失。原返回、原 EGES 重放、NA 传播及实际提示一致性已核查。[逐答案](judges/local_alternative_q2_v1/per_case.json)、[配对值](judges/local_alternative_q2_v1/paired_results.json)、[独立核查](judges/local_alternative_q2_v1/review.md)。

本次自然路线比较覆盖第 4 个不同任务。此前的 5 对完整数值比较仍仅来自 q21–23；q2 增加技术配对，未增加完整 CCE 对。不同生成模型的两份自然答案只支持描述性比较，不能解释为方法替换的纯因果效应。正式合理路线确认均为 0。
{extra_zh}
Llama 在两个固定答案上完成 3 次新提示词重复，共 6 次真实请求，probe 就是其中 q2 repeat 0，没有另算第七次。只替换末尾已填写的输出示例及两处指向文字，评分规则、完整输入、FDISCO v2 参考、模型、加载器及 EGES 不变。完整示例复制与路线误识别均从 6/6 降至 0/6；但新六次均漏提原文明示的 GFP、加入原文未出现的 c-Fos，且试剂 RI 与明示 DBE RI 不同。32 个分项组均无重复波动，16 个题间比较指标无严格排名翻转。数值 CCE 可计算 6/6，并不消除上述直接矛盾。[逐观测](judges/stability_remediation_plan_v1/per_observation.json)、[旧新配对变化](judges/stability_remediation_plan_v1/paired_prompt_effects.json)、[核验](judges/stability_remediation_plan_v1/analysis_verification.json)。

这项干预在暴露过的开发材料上支持末尾示例会影响输出的判断，但不能证明它是全部错误的唯一原因。较早的章节例子保留，剩余错误的机制尚未单独检验。本批只有一个 judge 家族；旧 Qwen 不是新提示词下的重复或对照。原双家族 E4 结果保留原版本。论文可以报告重复性、直接提取矛盾与提示词敏感性，不能据此宣称评分可靠或有预测效度。

[新增图 PNG](figures_followup_v1/followup_results.png)、[SVG](figures_followup_v1/followup_results.svg)、[PDF](figures_followup_v1/followup_results.pdf)、[逐图数据](figures_followup_v1/followup_results.csv)。图的 A 面板只含 q2 自然答案，B 面板为两题各三重复，六次请求不作为六个独立任务。

人工仍为一位专家、5 开发＋15 留出共用，实际回传 0；本轮直接文本核对不是专家标签。湿实验真实测量仍为 0。CUBIC-HV q1／q2 已建立条件性来源关联但未激活评分，uDISCO 来源恢复单列记录。{target_statement}目前参与已运行开发路线比较的不同题号为 {task_n}，科学适用性仍须独立确认。主评分的全队列 Q* 仍为空，不能建立正式全模型排名。
"""
    methods = """## Additional full-text development experiments

We prespecified one archived q2 answer per route using the fixed model order, without selecting on newly obtained scores. Both full answers were evaluated with the same frozen Qwen configuration (temperature 0, 8,192 output tokens, 40,960 context, one attempt) and identical supplied evidence. To fit the conservative context bound, we moved duplicate provenance metadata to hash-bound full references while preserving all 16 step texts, IDs, ordering, conditions, applicability clauses and unknowns. Steps were parsed and scored using the unchanged core; extraction and rubric judgments came from new calls. This cross-generator natural-answer comparison is descriptive.

After diagnosing complete worked-example copying in the original Llama batch, we froze a two-answer, three-repeat intervention matrix. The final combined worked output was replaced by a schema without scientific defaults, with two matching cross-reference edits. The original loader, rubric criteria, model settings, complete answers and references were retained. The q2 repeat-zero probe was reused exactly in the six-call matrix after passing prespecified format, route and full-example-copy screens. These screens did not assert scientific accuracy. All six calls had separate request receipts; old responses were retained. Earlier section examples remained unchanged. This is a post-diagnosis development intervention with one judge family, not a new same-prompt two-family comparison.

## Additional observed results

The q2 pair completed technically, with SR 0.714286/0.444444, SP 0.750000/0.214286, Com 0.885714/0.777778 and Cor 1.0/1.0 for FDISCO/iDISCO+, respectively. Both labeling components were unresolved, propagating NA to Eff, IA and HV. Thus technical completion added a fourth task to natural-route development comparisons without adding a complete CCE pair. No missing value was imputed.

In six new Llama calls, whole-example copying and declared-route mismatches fell from six to zero. However, all six omitted explicitly declared GFP, introduced c-Fos absent from the answer, and returned a reagent RI inconsistent with the explicit DBE RI. These are literal answer contradictions, not a substitute for the expert audit. All 32 component groups again had zero within-answer range, and no strict rank flip occurred across the two answers. Repeatability therefore coexisted with extraction errors. The final-example intervention improved selected output behaviors but did not establish evaluator accuracy or eliminate all sources of contamination.
""" + extra_en + "\n"
    write(OUT / 'RESULTS_zh.md', zh.replace('](judges/', '](../judges/').replace('](figures_', '](../figures_'))
    write(OUT / 'Methods_Results_en.md', methods)
    write(BASE / 'RESULTS_zh.md', zh + '\n---\n\n以下为 77 次请求时冻结的 v4 主评分报告；其“本轮”指主评分组合阶段。\n\n' + (HIST / 'RESULTS_zh.md').read_text(encoding='utf-8-sig'))
    historical_methods = (HIST / 'Methods_Results_en.md').read_text(encoding='utf-8-sig').replace(
        'Recorded model requests remain 77; q1 scoring, composition, analysis and this report added none.',
        f'The frozen v4 main-scoring stage recorded 77 model requests; q1 scoring and composition added none. Subsequent development experiments added {new_calls} requests, bringing the current package total to {used}; these are described below.')
    write(BASE / 'Methods_Results_en.md', historical_methods + '\n' + methods)
    abstract = (HIST / 'Abstract_en.md').read_text(encoding='utf-8-sig')
    abstract = abstract.replace('Repeated local evaluation was numerically stable, but rubric-copy extraction failures prevented reliability claims.', 'Repeated local evaluation was numerically stable. A six-call prompt intervention removed whole-example copying and route mismatches but retained explicit labeling and RI extraction errors in all six returns. A new natural-route pair completed technically but retained NA for effectiveness and joint scores.')
    write(BASE / 'Abstract_en.md', abstract)
    status = f"""# ClearEval r2 当前状态：v4 主评分＋后续实验

本阶段新增 {new_calls} 次真实模型请求，累计 {used}/300，剩余 {300-used}。q2 两份原答案全文重评完成，技术配对 1、完整 CCE 对 0；s_label 的实际未知值保留并传播。Llama 两题×三重复实际完成：完整示例复制和路线误识别 6→0，但六次仍存在标记和 RI 的直接原文矛盾；32 个分项组重复波动均为 0。零波动不支持准确性或可靠性结论。

原 v4 主评分保持 6 题、13 模型、77 份真实存档答案、38 份暂定 CCE，正式合格为 0；全队列 Q* 为空。旧受控实验 15 对、旧双家族稳定性 12 观测及固定 5 份开发提取继续按原版本保留。新增诊断不替换主评分或旧失败。

目前已运行开发路线比较涉及 {task_n} 个不同题号，正式合理替代确认 0。{target_statement}专家安排仍 1 人、5 开发＋15 留出，回传 0；湿实验真实数据 0。来源恢复不计作专家回传。

新增逐答案、来源、真实命令和论文段落见 [RESULTS_zh.md](RESULTS_zh.md)、[机器入口](current_run_index.json)、[命令](commands.md)。旧 v4 报告和 77 次请求账本已[独立保存](historical_reports/expanded_tasks_v4_before_followup/snapshot_manifest.json)。复现报告用 `python scripts/cce_report.py`。

下一项可运行工作是{next_work}；必须区分来源步骤覆盖、初始标记前提与科学合理性确认。其余专家与湿实验依赖继续待定，不阻断独立计算。
"""
    write(BASE / 'STATUS.md', status)
    budget = j.read(HIST / 'budget.json')
    budget.update(attempts_recorded=used, remaining_request_capacity=300-used, model_attempts=dict(Counter(r['model'] for r in ledger)), ledger_sha256=j.filehash(BASE / 'judges/request_ledger.jsonl'))
    j.save(BASE / 'budget.json', budget)
    dependencies = j.read(HIST / 'remaining_dependencies.json')
    dependencies.update(alternative_routes=f'{task_n} different tasks have development route comparisons; source-guided and natural answers distinguished; formal reasonable-route confirmation 0. Numerical task coverage is not confirmed scientific applicability.',
        evaluator_validity='Final-example intervention removed whole-example/route-copy flags in six new calls but retained explicit marker and RI contradictions in all six. Old two-family and new one-family configurations are not pooled.',
        next_independent_work=next_work + '；同一配置完成全文重新提取与配对。已完成的 q248 来源指导编辑不再列为未运行；专家、科学适用性及湿实验依赖分列。')
    j.save(BASE / 'remaining_dependencies.json', dependencies)
    index = main_index
    index.update(report_stage='expanded_tasks_v4_with_followup_v1', main_scoring_stage='expanded_tasks_v4', request_attempts=used,
        new_model_requests=new_calls, main_scoring_new_model_requests=0, followup_summary='followup_experiments_v1/summary.json',
        followup_alternative_q2={'path': 'judges/local_alternative_q2_v1', 'summary': q2},
        followup_prompt_intervention={'path': 'judges/stability_remediation_plan_v1', 'summary': e4},
        frozen_main_report_snapshot='historical_reports/expanded_tasks_v4_before_followup',
        followup_figure='figures_followup_v1/followup_results.png')
    oldsha = index['input_sha256'].pop('judges/request_ledger.jsonl')
    index['input_sha256']['historical_reports/expanded_tasks_v4_before_followup/request_ledger_at_77.jsonl'] = oldsha
    sources = [Q2 / 'development_summary.json', Q2 / 'paired_results.json', Q2 / 'review.json', E4 / 'development_summary.json', E4 / 'analysis_verification.json', E4 / 'independent_review.json', BASE / 'judges/request_ledger.jsonl', BASE / 'figures_followup_v1/plot_run.json', BASE / 'figures_followup_v1/figure_visual_qa.json']
    if optional:
        index['followup_source_guided_q248'] = {'path': 'judges/local_alternative_q248_v1', 'summary': optional}
        sources += [Q248 / 'development_summary.json', Q248 / 'paired_results.json']
        if (Q248 / 'review/independent_review.json').exists():
            sources.append(Q248 / 'review/independent_review.json')
    if q1:
        index['followup_natural_q1'] = {'path': 'judges/local_alternative_q1_v1', 'summary': q1}
        sources += [Q1 / 'development_summary.json', Q1 / 'paired_results.json', Q1 / 'review.json']
    index['input_sha256'].update({str(p.relative_to(BASE)).replace('\\', '/'): j.filehash(p) for p in sources})
    j.save(BASE / 'current_run_index.json', index)
    # Retain the full original configuration instead of replacing it with an index.
    resolved = j.read(HIST / 'resolved_config_current.yaml')
    resolved['followup_v1'] = {'q2_plan': 'judges/local_alternative_q2_v1/plan.json',
        'prompt_intervention_plan': 'judges/stability_remediation_plan_v1/plan.json',
        'q248_source_guided_plan': 'judges/local_alternative_q248_v1/plan.json' if optional else None,
        'q1_conditional_plan': 'judges/local_alternative_q1_v1/plan.json' if q1 else None,
        'package_requests': used, 'main_scoring_configuration_unchanged': True}
    j.save(BASE / 'resolved_config_current.yaml', resolved)
    summary = {'status': 'actual_followup_results', 'new_requests': new_calls, 'package_requests': used,
        'main_scored_answers': 77, 'main_candidate_CCE': 38, 'main_scores_unchanged': True,
        'alternative_development_distinct_tasks': task_n, 'formal_alternative_pairs': 0,
        'q2': q2, 'prompt_intervention': e4, 'q248_source_guided': optional, 'q1_natural_conditional': q1, 'expert_returns': 0}
    j.save(OUT / 'summary.json', summary)
    command_lines = ["& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' artifacts/cce_validation/judges/stability_remediation_plan_v1/probe.py probe --allow-local-call",
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' artifacts/cce_validation/judges/stability_remediation_plan_v1/probe.py remaining --allow-local-call",
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_stability_remediation_v1.py",
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_plot_followup_v1.py",
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_report_followup_v1.py"]
    command_doc = '# 后续已执行命令\n\nq2 的完整实际 argv 与成功记录见 [执行日志](judges/local_alternative_q2_v1/execution_commands.json)。下列命令均有真实结果文件；probe 属于六格矩阵，不额外计数。\n\n```powershell\n' + '\n'.join(command_lines) + '\n```\n\n'
    if optional:
        command_doc += 'q248 的实际命令与回执见 [执行目录](judges/local_alternative_q248_v1/README.md)。\n\n'
    if q1:
        command_doc += 'q1 的实际命令与回执见 [执行目录](judges/local_alternative_q1_v1/README.md)。\n\n'
    write(BASE / 'commands.md', command_doc + '以下为 v4 主评分阶段已执行命令。\n\n' + (HIST / 'commands.md').read_text(encoding='utf-8-sig'))
    write(ROOT.parent / 'STATUS.md', '# ClearEval r2 执行入口\n\n' + status.split('\n', 1)[1].replace('](RESULTS_zh.md)', '](ClearEval-public/artifacts/cce_validation/RESULTS_zh.md)').replace('](current_run_index.json)', '](ClearEval-public/artifacts/cce_validation/current_run_index.json)').replace('](commands.md)', '](ClearEval-public/artifacts/cce_validation/commands.md)').replace('](historical_reports/', '](ClearEval-public/artifacts/cce_validation/historical_reports/'))
    outputs = ['STATUS.md', 'RESULTS_zh.md', 'Methods_Results_en.md', 'Abstract_en.md', 'commands.md', 'current_run_index.json', 'resolved_config_current.yaml', 'remaining_dependencies.json', 'budget.json', 'followup_experiments_v1/summary.json']
    broken, link_count = [], 0
    for rel in outputs:
        if not rel.endswith('.md'):
            continue
        path = BASE / rel
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            link_count += 1
            if not (path.parent / link.split('#')[0]).exists():
                broken.append({'document': rel, 'target': link})
    assert not broken, broken
    j.save(BASE / 'report_verification_followup_v1.json', {'status': 'pass', 'checked_local_links': link_count,
        'main_input_hashes_verified_against_historical_snapshot': frozen_main_input_n, 'main_scoring_rows_unchanged': True,
        'report_script_sha256': j.filehash(__file__), 'inputs_sha256': {str(p.relative_to(BASE)): j.filehash(p) for p in sources},
        'outputs_sha256': {rel: j.filehash(BASE / rel) for rel in outputs}, 'actual_command': [sys.executable, 'scripts/cce_report_followup_v1.py']})
    j.save(BASE / 'report_generation.json', {'version': 'expanded_tasks_v4_with_followup_v1', 'status': 'complete_pass',
        'package_requests': used, 'followup_new_requests': new_calls, 'main_scoring_new_requests': 0,
        'frozen_main_report_generation': 'historical_reports/expanded_tasks_v4_before_followup/report_generation.json',
        'verification': 'report_verification_followup_v1.json', 'generator': {'path': 'scripts/cce_report_followup_v1.py', 'sha256': j.filehash(__file__)},
        'dispatcher': {'path': 'scripts/cce_report.py', 'sha256': j.filehash(ROOT / 'scripts/cce_report.py')},
        'input_sha256': {str(p.relative_to(BASE)): j.filehash(p) for p in sources},
        'output_sha256': {rel: j.filehash(BASE / rel) for rel in outputs}})
    print(j.canonical({'status': 'pass', 'package_requests': used, 'new_requests': new_calls, 'local_links': link_count, 'main_candidate_CCE_unchanged': 38}))


if __name__ == '__main__':
    main()
