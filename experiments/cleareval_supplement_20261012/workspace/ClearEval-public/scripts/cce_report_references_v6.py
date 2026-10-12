"""Publish verified v6 results and the completed 12-call development intervention."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
HIST = BASE / 'historical_reports/references_v5_at_104'
ANA = BASE / 'analysis_expanded_references_v6'
REM = BASE / 'judges/stability_remediation_v2/analysis'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write(p, text):
    Path(p).write_text(text.strip() + '\n', encoding='utf-8')


def main():
    ar = read(ANA / 'analysis_run.json')
    joint = read(ANA / 'joint_summary.json')
    current = joint['revised_full_fixed_cohort']
    facts = read(REM / 'report_facts.json')
    hold = read(BASE / 'judges/local_extraction_holdout_v1/completion_summary.json')
    audit = read(BASE / 'judges/holdout_failure_audit_v1/summary.json')
    prescreen = read(BASE / 'reference_recovery/holdout_source_prescreen_v1/audit.json')
    run = read(BASE / 'expanded_references_v6/run.json')
    refs = read(BASE / 'human_review/reference_construction_v4/summary.json')
    rows = read(BASE / 'expanded_references_v6_t070_per_answer.json')
    step_dir = BASE / 'holdout_source_steps_v1'
    step_summary = read(step_dir / 'summary.json')
    assert read(step_dir / 'independent_review.json')['status'] == 'pass'
    assert step_summary['actual_answers'] == 15 and step_summary['numeric_steps_primary'] == 1
    assert step_summary['reference_insufficient_primary'] == 14 and step_summary['complete_CCE_added'] == 0
    assert step_summary['new_embeddings'] == 9 and step_summary['new_model_requests'] == 0
    step_values = [next(r for r in read(step_dir / f't{t}_per_answer.json')
                        if r['anonymous_answer_id'] == 'A06') for t in ('060','070','080')]
    assert [(r['sr'], r['sp']) for r in step_values] == [(.25,.2),(0.,0.),(0.,0.)]
    changed = set(ar['numeric_delta_answer_ids'])
    added = [r for r in rows if r['answer_id'] in changed]
    ledger_path = BASE / 'judges/request_ledger.jsonl'
    ledger = [json.loads(x) for x in ledger_path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    ledger = [r for r in ledger if r.get('event') == 'request_started']
    old = [json.loads(x) for x in (HIST / 'request_ledger_at_104.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert ledger[:104] == old and len(ledger) == 104 + facts['actual_requests'] == facts['package_requests']
    used = len(ledger)
    assert used == 116 and facts['success_cells'] == 12 and facts['failed_cells'] == 0
    assert ar['status'] == 'pass' and ar['numeric_CCE'] == 46 and len(added) == 7
    assert current['common_question_ids'] == ['2'] and current['common_n'] == 1
    assert current['task_bootstrap']['repeats_completed'] == 2000
    assert joint['formal_fixed_cohort']['common_n'] == 0
    assert run['other_70_numeric_NA_unchanged_each_threshold'] and run['new_judge_requests'] == 0
    assert refs['current_main_branches'] == 9 and refs['current_main_source_families'] == 4
    assert sha(ROOT / 'scripts/cce_validation.py') == 'd272393ecbba84495e0430d01c0b52c4f69a6d9502147bdb071371dfed2bdc20'
    assert sha(BASE / 'human_review/reviewer/review_items.csv') == '7ae708d91938b7e60737298261234e483caee4b50475ee20219cb188667ff5aa'
    assert read(BASE / 'human_review/expert_extraction_corrections.json') == []
    for rel, digest in read(HIST / 'snapshot_manifest.json')['files_sha256'].items():
        assert sha(HIST / rel) == digest, rel
    qa = read(BASE / 'figures_expanded_references_v6/figure_visual_qa.json')
    assert qa['status'] == 'pass'
    for name, digest in qa['files_sha256'].items():
        assert sha(BASE / 'figures_expanded_references_v6' / name) == digest, name
    assert read(BASE / 'expanded_references_v6/review_analysis_v6.json')['status'] == 'pass_numeric_analysis_with_publication_scope_cautions'
    metrics = ('sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV')
    new_table = '\n'.join('| ' + r['answer_id'] + ' | ' + ' | '.join(f'{r[k]:.6f}' for k in metrics) + ' |' for r in added)
    front = ', '.join(m.removeprefix('openai_') for m in current['empirical_nondominated'])
    threshold = read(ANA / 'common_cohort_threshold_sensitivity.json')
    assert [len(x['empirical_nondominated']) for x in threshold] == [6, 5, 4]
    diff = facts['cross_family_disagreements']
    assert facts['groups_with_nonzero_range'] == facts['strict_rank_flip_groups'] == 0
    assert diff['groups_with_any_disagreement'] == 10 and diff['disagreeing_finite_pairs'] == 30
    for model, flags in facts['literal_flags_by_model'].items():
        for key in ('native_GFP_missing', 'cFos_injected', 'RI_missing', 'RI_numeric_contradiction'):
            assert flags[key] == {'flagged': 0, 'evaluable': 6}, (model, key)
    zh = f"""# ClearEval r2 当前真实结果（116 次请求）

新增 7 份真实存档答案的条件性步骤评分已完成：固定 6 题、13 模型的 77 份答案中，暂定完整 CCE 从 39 增至 46，参考不足从 38 减为 31。每个阈值的另外 70 行完整对象原样复用；全部 77 行原参数完整性、Correctness 和 EGES 不变。三个阈值共核对 231 行，本批新增 judge 请求和嵌入向量均为 0。[逐答案 CSV](expanded_references_v6_t070_per_answer.csv)、[来源与执行说明](expanded_references_v6/README.md)、[实际命令](expanded_references_v6/EXECUTION.md)。

| 新可评分答案 | SR | SP | Com | Cor | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|---:|---:|
{new_table}

新增 q2/q248 uDISCO 参考仅覆盖作者来源中的清除范围。q2 的标记完成及全神经元结构覆盖未确认；q248 的后固定、第二轴突标记和双信号兼容未确认。初洗、去膜属于未确认起点前提；终末保存作为持续条件。全脑流程没有外推到 q21–23 的 3 mm 脑块。9 个任务绑定条件分支来自 4 个来源家族，正式适用性确认仍为 0；增加分支不等于增加独立来源或合格替代路线。[来源绑定](reference_recovery/udisco_development_bindings_v2/task_bindings.json)、[单列参考建设台账](human_review/reference_construction_v4/README.md)。

**新的联合结果。** 固定 13 模型首次在 q2 有共同数值 CCE，即暂定 Q*={{q2}}。该单题三维非支配集合为 {front}。阈值 0.6/0.7/0.8 使用相同 q2，非支配模型数分别为 6/5/4。不能把该结果表述为全基准正式排名；正式共同集仍为空。同题各模型选中的参考属于 3 个来源家族，原单一家族映射不一致，来源家族 bootstrap 继续待定。另行实际完成 2,000 次同步任务重采样（13 模型共 26,000 行）；只有一题，所有抽样相同，零宽区间和入选频率不提供跨任务不确定性。[联合结果与支配矩阵](analysis_expanded_references_v6/joint_summary.json)、[同题阈值比较](analysis_expanded_references_v6/common_cohort_threshold_sensitivity.csv)、[独立软件核查](expanded_references_v6/review_analysis_v6_README.md)。

全库保留 3,288 份答案、3,289 个预定位置；实际新步骤评分仍仅覆盖上述 6 题，不能把全库统计框架当作已运行 253 题。预定双 Gemini 五题子集的逐题 IA/HV、三维支配和旧 2,000 次单家族重采样输入未变，按字节复用。各模型阈值曲线使用各自跨设置共同答案，样本数不同；仅作模型内敏感性，不用于横向排名。[全库分项覆盖](analysis_expanded_references_v6/revised_component_coverage.csv)。

**新的评价器干预。** 两份已暴露开发答案 × Qwen/Llama 两家族 × 三重复，12 次真实调用全部技术成功，主试次固定 repeat 0，没有重试。相对 v1 仅再移除三处带具体事实的提取示例；同一完整问题、答案、参考、科学规则、评分函数与模型配置保持不变。Llama 的 GFP 漏提、c-Fos 误加和明确 RI 数值矛盾，从原提示与 v1 的各 6/6 降至 v2 各 0/6；Qwen 原提示和 v2 对应旗标均为 0/6。两模型本次 RI 缺失也各为 0/6。这里的 6 次来自两份答案的三重复，不能当作六份独立答案，更不能把指定字面矛盾消失解释为全面准确。

64 个模型内“答案×指标”组的重复范围均为零，32 个题间排名组无严格翻转；跨模型却有 10/32 个“题目×指标”组存在差异，同 repeat 数值对为 30/96。实际提示词、原始返回、回执、台账和原 EGES 重算已核对。论文可以报告提取示例干预减少指定矛盾，同时保留“重复稳定不等于准确、跨评价器差异仍存在”的结论。此为开发干预，未作为留出配置回改，不能与旧提示或 v1 合并为同配置重复。[逐观测与核验](judges/stability_remediation_v2/analysis/README.md)、[各版本分列](judges/stability_remediation_v2/analysis/version_summary.json)。

**留出审计新增结果。** 冻结的 15 份原尝试仍为 7 次可载入、8 次失败。离线复现的首个失败原因是缺少提取字段 4 次、嵌套字段大小写不符 3 次、重复 JSON 键 1 次；全部 provider 正常结束，不能统称网络/API失败。失败维持 NA，未修补或重跑。技术可载入也不代表提取忠实。[失败证据](judges/holdout_failure_audit_v1/README.md)。

来源预筛确认 15 个题号与已知开发题不同，但有 4 份属于同开发方法家族的来源候选、另有 3 份 CUBIC 版本待定。候选关系不能证明答案确实来自同一论文，也不能支持来源家族独立。0/15 当前参考绑定不等于 15 份全部没有原文。Ce3D 原文与精确 SI 入口已核对，SI 尚未取回；主文的特定淋巴结体积、一般厚度讨论与题干尺度分别保留。CUBICpath 2017 为 A13 的鼠肺块恢复 6 条来源操作，但标记、洗涤、保存及起点仍有缺口，保持未激活，不拼造完整路线。[来源预筛](reference_recovery/holdout_source_prescreen_v1/README.md)、[候选措辞独立核查](reference_recovery/holdout_source_prescreen_review_v1/README.md)、[Ce3D](reference_recovery/ce3d_2017_holdout_v1/README.md)、[CUBIC 来源范围](reference_recovery/cubic_holdout_source_scope_v1/README.md)。

前期已完成的 15 对全文受控比较与 6 个任务的开发路线比较保留原结果。6 个任务为 5 个自然答案任务及 1 个来源指导编辑任务；科学适用性已确认的完整替代路线任务仍为 0，尚未达到 6–8 个合格任务的要求。旧人工 240 条记录按版本与分项对齐，方法尺度依据未恢复，机器改写项不当作独立人评。湿实验真实观测为 0；计划、42 个假设功效情景、随机化和分析入口保留。详情及既有图表见 [89 次请求阶段报告](historical_reports/followup_at_89/RESULTS_zh.md)，此前 104 次状态另有[原字节快照](historical_reports/references_v5_at_104/snapshot_manifest.json)。

本轮新增 12 次本地模型请求，全包 {used}/300，余额 {300-used}。一位专家、5 开发＋15 留出安排和原 160 项表格不变；真实回传与忠实修正均为 0。完整参考建设另计人时，未知时留空，不占 20 份局部核查名额。剩余正式 E1/E3、合理替代路线确认及湿实验效果均保持待定。[统一人工入口](human_review/CURRENT_REVIEW_ENTRY.md)、[剩余依赖](remaining_dependencies.json)、[实际命令](commands.md)。

当前图表均附 SVG/PDF/PNG 和数据：[参考覆盖与逐答案阈值](figures_expanded_references_v6/udisco_reference_expansion.png)、[13 模型单题 CCE 三投影](figures_expanded_references_v6/fixed13_common_task_cce_projections.png)、[模型内阈值曲线](figures_expanded_references_v6/threshold_sensitivity.png)、[留出技术失败](figures_followup_after104/holdout_technical_outcomes.png)、[提取示例干预](figures_followup_after104/stability_remediation_v2.png)。
"""
    step_zh = """新增的留出来源扩展已真实完成：15 份原全文 × 三个既定阈值共 45 行，A06/q146 得到一份条件性作者分支 SR/SP，其余 14 份保持参考不足。主阈值 0.7 下 SR=SP=0；0.6 下为 0.25/0.20，0.8 下均为零。该答案含 5 个非空英文段落，4 个来源操作完整保留，均未截断，最大相似度 0.618121；零匹配不等于无操作或科学无效。新增 9 个本地 MPNet 向量、0 个 judge 请求，未新增完整 CCE。原 15 次 judge 的空参考配置与科学输出仍保持原状，此结果属于另行冻结的后补来源步骤诊断。[逐答案、来源和实际命令](holdout_source_steps_v1/README.md)、[独立软件核验](holdout_source_steps_v1/independent_review.json)。

ClearSee 2015 官方全文已恢复并核对，只有未限定壁染料的 q146 激活。q145 明确要求 SCRI Renaissance2200，作者 Calcofluor White 来源不足以支撑该限定，仍为 NA；这不意味着 SCRI 不兼容。确切幼苗长度、整幼苗双通道和任务目标满足仍待确认。参考选择在看步骤结果前冻结，未删除壁染操作或调整阈值。[激活范围](reference_recovery/clearsee_holdout_step_activation_v1/README.md)。

其余来源复核保留具体缺口：整鼠 PEGASOS Methods 分支虽完整恢复，循环起点、身体范围和版本冲突未决，未激活；三份 iDISCO+ 的原文与附件已在，但目标器官/版本适用证据不足。MACS 未得 FFPE 分支，TDE 2015 未得目标蠕虫分支；FOCM 有整器官分支，仍不能直接绑定本厚肿瘤任务。BoneClear 原始方法附件未得。来源建设 v4 共 20 条元数据记录，其中主评分仍 9 分支/4 家族；新增 1 条留出条件分支单列，不能把记录总数当作独立来源数。[四份共享方法来源](reference_recovery/holdout_shared_sources_v1/README.md)、[MACS/TDE/FOCM](reference_recovery/holdout_macs_focm_tde_source_review_v1/README.md)、[ClearSee/BoneClear](reference_recovery/clearsee_boneclear_source_recovery_v1/README.md)、[建设台账](human_review/reference_construction_v4/README.md)。

"""
    zh = zh.replace('新增 7 份真实存档答案的条件性步骤评分已完成：', step_zh + '新增 7 份真实存档答案的条件性步骤评分已完成：', 1)
    zh = zh.replace('0/15 当前参考绑定不等于 15 份全部没有原文。', '原 judge 批次的 0/15 参考配置不等于 15 份全部没有原文；上述独立条件步骤扩展现为 1/15。')
    zh = zh.replace('实际新步骤评分仍仅覆盖上述 6 题，不能把全库统计框架当作已运行 253 题。', '主比较的步骤评分范围仍为上述 6 题，另有独立 q146 来源步骤诊断；不能把全库统计框架当作已运行 253 题。')
    zh += '\n15 份留出材料的来源状态、审阅深度及未决项已汇总，区分原始0/15、后补条件1/15和正式科学验证0：[来源总表](reference_recovery/holdout_source_review_completion_v1/README.md)、[逐份CSV](reference_recovery/holdout_source_review_completion_v1/per_answer_source_review.csv)。A18仅有次级肾片范围线索，未被表述为完整路线已核实。\n'
    write(BASE / 'RESULTS_zh.md', zh)
    english = f"""# Supplementary Methods and Results: current development evidence

We retained the prespecified 13-model, one-shot cohort, original question identities and all 77 available answers for six tasks. Conditional author-derived uDISCO clearing references were extended to q2 and q248 without transferring whole-brain schedules to 3-mm blocks. Initial preparation, labeling completion and task-specific marker compatibility remained unresolved. Nine task-bound conditional branches represented four source families, not nine independent methods. The original BioProBench encoder and thresholds 0.6, 0.7 and 0.8, route filtering and tie-breaking were retained. All archived parameter-completeness, correctness and EGES components were preserved. Across 231 answer-threshold rows, seven answers acquired reference scores at each threshold and the remaining 70 row objects were reused unchanged. No judge calls or new embeddings were required. Provisional complete CCE coverage increased from 39/77 to 46/77; 31 answers retained reference-related NA values.

The full archive contained 3,288 answers for 3,289 expected model-task positions. Only six tasks had revised step scores. The fixed 13-model provisional common set first became nonempty, containing q2 alone. At threshold 0.7 its three-dimensional nondominated set comprised {front}. On the same task, thresholds 0.6, 0.7 and 0.8 yielded six, five and four nondominated models. IA and HV were computed per answer before aggregation. These are single-task conditional results, not a validated benchmark ranking. Selected routes for q2 represented three source families, preventing the original unique-family mapping; source-family bootstrap results remained pending. We separately computed 2,000 synchronized task bootstrap replicates for all 13 models. With one task, all 26,000 model-replicate rows were identical to their task estimates and uncertainty intervals were degenerate. The previously specified two-Gemini, five-task summary and its 2,000 single-family draws were reused after input and byte verification. Within-model threshold curves used different paired answer sets across models and were not interpreted as between-model comparisons.

A separate frozen development intervention removed three residual fact-filled extraction examples after the earlier final-schema intervention. Scientific rubric criteria, full inputs, reference context, original loader, formulas, temperature and model settings were unchanged. The complete two-answer by two-judge-family by three-repeat matrix required 12 new local requests, all technically successful, without retries; repeat zero was prespecified for primary results. Llama's missing native-GFP, injected c-Fos and explicit numerical-RI contradictions each decreased from 6/6 in the original and final-schema-only versions to 0/6 in the new version. Corresponding Qwen flags were 0/6 before and after; both judges had zero missing-RI flags in the new version. Six observations represent two answers repeated three times, not six independent answers. All 64 within-judge answer-metric groups had zero repeat range, and none of 32 ranking groups showed a strict flip. Nevertheless, 10/32 cross-family question-metric groups differed, comprising 30/96 same-repeat numeric pairs. Thus the intervention reduced specified literal contradictions while leaving evaluator differences; it did not establish comprehensive extraction or scientific accuracy. Prompt versions were kept separate and the frozen holdout was not reconfigured.

The 15 prespecified holdout attempts remained seven loadable outputs and eight failures. Offline first-failure checks identified four missing-extraction-field cases, three nested-key casing cases and one duplicate-JSON-key case. All provider returns terminated normally, so these failures should not be attributed collectively to API or network unavailability. No failed response was repaired or retried. Source-side prescreening found four same-development-method-family candidates and three unresolved CUBIC-version cases. These associations neither establish exact article derivation nor validate family independence. A source-first CUBICpath mouse-lung candidate remained inactive because its full task scope was unresolved; the exact Ce3D supplement could not be recovered. Active complete holdout reference coverage remained zero.

The earlier 15 full-text controlled pairs and six-task development alternative-route comparisons are preserved under their original configurations. Scientifically confirmed alternative-route task coverage remains zero. One expert is still assigned the same five development and 15 holdout answers, with no returned conclusions or faithful-field corrections. Full reference construction is logged separately. Wet-lab observations remain unavailable; plans and hypothetical power scenarios are not biological results. The package has used {used}/300 requests. Formal accuracy, correction effects and wet-lab conclusions remain pending.

Evidence: [per-answer scores](expanded_references_v6_t070_per_answer.csv), [common-set analysis](analysis_expanded_references_v6/joint_summary.json), [stability intervention](judges/stability_remediation_v2/analysis/README.md), [holdout audit](judges/holdout_failure_audit_v1/README.md), [previous detailed Methods/Results](historical_reports/followup_at_89/Methods_Results_en.md).
"""
    step_en = """A subsequent source-only extension was frozen before scoring all 15 original holdout answers at the three existing thresholds. Only q146 was bound to a four-operation ClearSee author branch; 14 answers retained reference-related NA values. SR/SP were 0.25/0.20 at 0.6 and 0/0 at 0.7 and 0.8. The answer contained five nonempty English segments, with no truncation and maximum similarity 0.618121. This zero match is not evidence of absent operations or scientific invalidity. The extension computed nine local vectors and made no judge requests or complete-CCE additions. The original judge batch and expert forms were unchanged. q145 was not bound because its required SCRI Renaissance2200 dye was not established by the recovered Calcofluor White branch. Exact size, whole-seedling dual-channel performance and scientific target satisfaction remained unresolved. Whole-body PEGASOS and other source reviews retained explicit version, initial-state and specimen gaps rather than forcing task bindings. [Source-step results and execution](holdout_source_steps_v1/README.md), [separate construction ledger](human_review/reference_construction_v4/README.md).

"""
    english = english.replace('A separate frozen development intervention', step_en + 'A separate frozen development intervention', 1)
    english = english.replace('Only six tasks had revised step scores.', 'The main comparison included revised step scoring for six tasks; the separate conditional holdout extension is described below.')
    english = english.replace('Active complete holdout reference coverage remained zero.', 'The original judge batch retained zero references. The later conditional q146 step extension is reported separately and adds no scientifically confirmed complete task route.')
    write(BASE / 'Methods_Results_en.md', english)
    write(BASE / 'Abstract_en.md', """# Draft abstract: supplementary development evidence

Fixed-sample tissue-clearing protocol generation requires matching specimen scale and labeling to procedural requirements and imaging goals. ClearEval evaluates parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring (EGES). We added source-bound Step Recall and Step Precision while retaining the original components. Across 77 archived answers from 13 models and six tasks, conditional references from four source families yielded 46 provisional complete CCE values. The fixed-model common set comprised one task; its nondominated set contained six, five and four models across thresholds 0.6, 0.7 and 0.8. Single-task resampling provided no cross-task uncertainty evidence. Fifteen full-text controlled pairs exposed score nonresponses and segmentation sensitivity. A twelve-call, two-judge development intervention removed specified labeling and RI extraction contradictions, although 10/32 cross-judge metric groups differed despite zero within-judge repeat variation. Fifteen frozen holdout attempts yielded seven loadable outputs, with the eight failures attributable to output-contract checks. A separate conditional source extension enabled one holdout step diagnosis; its nonempty English answer received zero matching at the default threshold. These findings distinguish numerical repeatability, literal extraction fidelity and scientific validity. Expert correction effects, confirmed alternative-route applicability and wet-lab outcomes remain unresolved.
""")
    status = f"""# ClearEval r2 当前状态

最新来源扩展：15份原全文×3阈值已计算；q146获得一份条件性SR/SP，其余14份参考不足。主阈值SR=SP=0，0.6下为0.25/0.20；5个非空英文段落未截断。9个新本地向量、0judge、0新增完整CCE，原留出judge配置不变。[来源步骤与核验](holdout_source_steps_v1/README.md)。

本轮新增 7 份真实步骤评分：固定 6 题、13 模型、77 答案中暂定 CCE 46/77，原参数完整性、Correctness、EGES 全部保留。13 模型暂定共同集为 q2 一题；主阈值前沿 5 模型，三阈值前沿 6/5/4。2,000 次同步任务重采样因单题完全退化；正式共同集仍为空。

新的 12 次开发评价全部技术成功：两模型各 6 次的指定 GFP/c-Fos/RI 矛盾均为 0；64 指标组内无重复波动，跨模型仍有 10/32 组差异。总请求 {used}/300，余 {300-used}，本轮参考评分无请求。

冻结留出仍为 7/15 可载入，8 次失败已归因到字段/JSON契约。来源预筛找到 4 份同方法家族候选，不能据题号不同声称来源独立。原judge参考仍0/15；新条件性步骤参考1/15，完整任务科学验证仍0。Ce3D/BoneClear附件、CUBIC/PEGASOS等任务适用缺口已分别记录。

整体任务尚未完成：一位专家的 5＋15 核查未回传；科学确认的完整替代路线任务仍为 0；旧方法尺度和湿实验真实数据仍缺。原160项人审表不变，完整来源建设单列。

当前[结果与论文意义](RESULTS_zh.md)、[逐答案与配置入口](current_run_index.json)、[实际命令](commands.md)、[共用人审入口](human_review/CURRENT_REVIEW_ENTRY.md)。[104次阶段原字节快照](historical_reports/references_v5_at_104/snapshot_manifest.json)保留。下一条离线恢复命令：`python scripts/cce_report.py`；真实专家回传后按既有合同处理，不能用机器建议代填。
"""
    write(BASE / 'STATUS.md', status)
    write(ROOT.parent / 'STATUS.md', status.replace('](', '](ClearEval-public/artifacts/cce_validation/'))
    deps = read(HIST / 'remaining_dependencies.json')
    deps.update(reference_validation='9 conditional task-bound branches, 4 source families, 0 formal scientific confirmations. Initial preparation, labeling and task-specific compatibility remain unresolved.',
        cohort_coverage={'answer_missing': 1, 'provisional_CCE_numeric': 46, 'screened_reference_insufficient': 31, 'revised_steps_not_run': 3211},
        common_numeric_questions=[2], common_formal_questions=[],
        common_set_inference='Only q2; task bootstrap 2000 is degenerate. Source-family mapping is inconsistent across chosen routes; no full-benchmark revised ranking.',
        evaluator_validity='v2: 12 technical successes, designated literal flags 0/6 per judge, 64 repeat groups range zero; 10/32 cross-family groups disagree. Two exposed development answers only; no accuracy certification.',
        holdout_extraction='Original 7/15 successes and 8 output-contract failures unchanged; original judge reference context remains empty. Separate conditional step extension covers q146 only, not scientific CCE. Four same-method-family candidates do not establish exact shared sources or independence.',
        source_recovery='ClearSee q146 has separate conditional SR/SP only (1/15); q145 explicit-dye requirement remains unbound. PEGASOS whole-body and CUBICpath source candidates inactive; other specimen/version/source gaps documented; full scientific task confirmations 0.',
        next_independent_work='Source-first additional bindings may proceed only when complete task scope is supported; real expert returns enable E1/E3 corrections. Current runnable frozen batches, source checks and report generation are complete.',
        holdout_source_extension={'conditional_step_numeric':1,'reference_NA':14,'complete_CCE_added':0,'new_embeddings':9,'new_judge_requests':0,'formal_eligible':0},
        report_stage='references_v6_remediation_v2_holdout_steps_v1_at_116')
    save(BASE / 'remaining_dependencies.json', deps)
    budget = read(HIST / 'budget.json')
    budget.update(attempts_recorded=used, remaining_request_capacity=300-used,
                  model_attempts=dict(Counter(r['model'] for r in ledger)), ledger_sha256=sha(ledger_path))
    save(BASE / 'budget.json', budget)
    human = (HIST / 'human_review/CURRENT_REVIEW_ENTRY.md').read_text(encoding='utf-8-sig')
    human = human.replace('reference_construction_v2/', 'reference_construction_v4/')
    human = human.replace('这 15 份来源家族尚未映射，步骤参考覆盖为 0',
        '这 15 份中有 4 份同开发方法家族候选、3 份 CUBIC 版本待定；最终来源身份与独立性未确认，原 judge 批次参考为 0/15，新单独条件步骤覆盖为 1/15')
    human += '\n当前说明：回传合同保留原字段与校验规则，其中早期数量和“留出机器建议待补”属于历史状态。当前留出已尝试15份、7份有可载入机器建议、8份失败保留；附件入口以上文为准。新开发提示词干预没有替换留出配置或候选字段。来源建设现有9个条件分支、4家族，均待科学适用性确认。\n'
    human += '\n后补来源步骤附件：[固定15份匹配候选](../holdout_source_steps_v1/reviewer/README.md)。仅A06/q146有条件性作者分支候选，其他14份保持参考不足；不代替原表，不填入专家结论。原judge批次参考不变，新的条件步骤覆盖为1/15，完整任务科学确认仍为0。\n'
    human += '\n[15份来源状态与适用范围](../reference_recovery/holdout_source_review_completion_v1/README.md)供查阅；来源预筛没有填入专家结论。\n'
    write(BASE / 'human_review/CURRENT_REVIEW_ENTRY.md', human)
    commands = """# 本阶段已实际执行的命令

工作目录 `C:\\ClearEval\\ClearEval-public`；使用本机 portable Python。以下命令均已真实执行；run 已完成12格，成功结果按实际输入/配置身份复用，不产生重复成功请求。

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_stability_remediation_v2.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_stability_remediation_v2.py preflight
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_stability_remediation_v2.py run --allow-local-calls
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_stability_remediation_v2.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_references_v6.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_plot_holdout_technical_v1.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_plot_stability_remediation_v2.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_report.py
```

新增参考评分的 prepare/run 及离线核验见 [v6实际执行记录](expanded_references_v6/EXECUTION.md)；[评价器分析执行记录](judges/stability_remediation_v2/analysis/commands.md)、[来源建设台账](human_review/reference_construction_v4/README.md)、[Ce3D来源检查](reference_recovery/ce3d_2017_holdout_v1/README.md)、[CUBIC来源检查](reference_recovery/cubic_holdout_source_scope_v1/README.md)分别保留原命令及哈希。报告生成与分析本身不调用模型。旧命令保存在[104次阶段快照](historical_reports/references_v5_at_104/commands.md)。
"""
    commands += '\n新增独立步骤运行（已执行，新增judge为0）：\n\n```powershell\n& \'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe\' scripts/cce_freeze_clearsee_holdout_v1.py\n& \'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe\' scripts/cce_holdout_source_steps_v1.py run\n```\n\n冻结只执行一次；实际prepare的完整参数及run见[步骤执行记录](holdout_source_steps_v1/README.md)。新来源核查与单独台账见上文对应记录。\n'
    write(BASE / 'commands.md', commands)
    sources = [ANA / 'analysis_run.json', ANA / 'joint_summary.json', ANA / 'common_cohort_threshold_sensitivity.json',
        BASE / 'expanded_references_v6/run.json', BASE / 'expanded_references_v6/plan.json',
        BASE / 'expanded_references_v6/references.json', BASE / 'expanded_references_v6/verification.json',
        BASE / 'expanded_references_v6/review_analysis_v6.json', REM / 'report_facts.json',
        REM / 'analysis_verification.json', BASE / 'judges/stability_remediation_v2/plan.json',
        BASE / 'judges/holdout_failure_audit_v1/summary.json',
        BASE / 'reference_recovery/holdout_source_prescreen_v1/audit.json',
        BASE / 'reference_recovery/holdout_source_prescreen_review_v1/review.json',
        BASE / 'reference_recovery/ce3d_2017_holdout_v1/retrieval_summary.json',
        BASE / 'reference_recovery/cubic_holdout_source_scope_v1/scope_summary.json',
        BASE / 'human_review/reference_construction_v4/summary.json',
        BASE / 'human_review/reference_construction_v4/source_index.json',
        BASE / 'figures_expanded_references_v6/figure_visual_qa.json',
        BASE / 'figures_followup_after104/technical_plot_run.json',
        BASE / 'figures_followup_after104/stability_remediation_v2_qa.json',
        BASE / 'judges/local_extraction_holdout_v1/completion_summary.json', ledger_path,
        *[BASE / f'expanded_references_v6_t{t}_per_answer.json' for t in ('060','070','080')],
        step_dir / 'summary.json', step_dir / 'run.json', step_dir / 'plan.json', step_dir / 'independent_review.json',
        *[step_dir / f't{t}_per_answer.json' for t in ('060','070','080')],
        BASE / 'reference_recovery/clearsee_holdout_step_activation_v1/scope_decision.json',
        BASE / 'reference_recovery/holdout_shared_sources_v1/summary.json',
        BASE / 'reference_recovery/holdout_macs_focm_tde_source_review_v1/review.json',
        BASE / 'reference_recovery/clearsee_boneclear_source_recovery_v1/recovery_completion.json',
        BASE / 'reference_recovery/holdout_source_review_completion_v1/summary.json',
        BASE / 'reference_recovery/holdout_source_review_completion_v1/verification.json']
    assert all(p.exists() for p in sources)
    index = read(HIST / 'current_run_index.json')
    index.update(version='references_v6_remediation_v2_holdout_steps_v1_at_116', report_stage='references_v6_remediation_v2_holdout_steps_v1_at_116',
        main_scoring_stage='expanded_references_v6', primary='expanded_references_v6_t070_per_answer.json',
        thresholds=[f'expanded_references_v6_t{t}_per_answer.json' for t in ('060','070','080')],
        reference='expanded_references_v6/references.json', plan='expanded_references_v6/plan.json',
        composition='expanded_references_v6/run.json', score_verification='expanded_references_v6/verification.json',
        analysis='analysis_expanded_references_v6/joint_summary.json',
        reference_construction='human_review/reference_construction_v4/source_index.json',
        figure_qa='figures_expanded_references_v6/figure_visual_qa.json',
        stability_remediation_v2='judges/stability_remediation_v2/analysis/report_facts.json',
        holdout_failure_audit='judges/holdout_failure_audit_v1/summary.json',
        holdout_source_prescreen='reference_recovery/holdout_source_prescreen_v1/audit.json',
        holdout_source_steps='holdout_source_steps_v1/summary.json',
        holdout_source_step_review='holdout_source_steps_v1/independent_review.json',
        holdout_source_status='reference_recovery/holdout_source_review_completion_v1/summary.json',
        request_attempts=used, new_model_requests=12, main_scoring_new_model_requests=0,
        previous_report_index='historical_reports/references_v5_at_104/current_run_index.json',
        actual_counts={'actual_answers':77,'step_numeric':46,'candidate_cce_numeric':46,'formal_eligible':0,
                       'question_ids':[1,2,21,22,23,248],'reference_branches':9,'source_families_with_numeric_rows':4,
                       'fixed13_provisional_common_question_ids':[2],'fixed13_formal_common_question_ids':[]},
        input_sha256={str(p.relative_to(BASE)).replace('\\','/'):sha(p) for p in sources})
    save(BASE / 'current_run_index.json', index)
    config = read(HIST / 'resolved_config_current.yaml')
    config.update(version=index['version'], previous_configuration_snapshot='historical_reports/references_v5_at_104/resolved_config_current.yaml',
        composition_configuration=read(BASE / 'expanded_references_v6_t070_resolved_config.json'),
        reference_extension_v6={'plan':index['plan'],'reference':index['reference'],'original_archived_components_preserved':True},
        row_configuration_policy='70 prior objects reused unchanged per threshold; 7 newly scored objects bound to frozen v6 reference configuration.',
        stability_remediation_v2={'plan':'judges/stability_remediation_v2/plan.json','configuration':'judges/stability_remediation_v2/local_config_snapshot.json','report_facts':index['stability_remediation_v2'],'development_only':True,'holdout_configuration_changed':False},
        holdout_source_steps_v1={'plan':'holdout_source_steps_v1/plan.json','reference':'reference_recovery/clearsee_holdout_step_activation_v1/references.json','scope':'Separate conditional author-branch SR/SP only; original judge config preserved','scientific_eligibility_pending':True},
        current_execution={'primary':index['primary'],'reference':index['reference'],'analysis':index['analysis'],'package_requests':used})
    save(BASE / 'resolved_config_current.yaml', config)
    save(BASE / 'current_activity.json', {'status':'completed_current_frozen_batches_overall_task_pending',
        'stage':index['version'],'requests':used,'overall_goal_complete':False,'next_dependency':'Real expert return or additional complete source evidence; no pending running model batch.'})
    docs = [BASE / n for n in ('RESULTS_zh.md','Methods_Results_en.md','Abstract_en.md','STATUS.md','commands.md','human_review/CURRENT_REVIEW_ENTRY.md')]
    links = []
    for doc in docs:
        for rel in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if '://' in rel or rel.startswith('#'):
                continue
            target = (doc.parent / rel.split('#')[0]).resolve()
            assert target.exists(), (str(doc),rel)
            links.append({'document':str(doc.relative_to(BASE)), 'target':rel})
    outputs = docs + [BASE / n for n in ('current_run_index.json','resolved_config_current.yaml','remaining_dependencies.json','budget.json','current_activity.json')]
    manifest = {'status':'pass','actual_command':[sys.executable,'scripts/cce_report.py'],
        'generator_sha256':sha(__file__),'dispatcher_sha256':sha(ROOT / 'scripts/cce_report.py'),
        'new_report_model_requests':0,'package_requests':used,'numeric_CCE':46,'fixed13_common_n':1,
        'actual_local_links_checked':len(links),'old_104_snapshot_unchanged':True,'original_scoring_core_unchanged':True,
        'original_expert_form_unchanged':True,'input_sha256':index['input_sha256'],
        'output_sha256':{str(p.relative_to(BASE)).replace('\\','/'):sha(p) for p in outputs}}
    save(BASE / 'report_generation.json',manifest)
    save(BASE / 'report_verification_references_v6.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('status','package_requests','numeric_CCE','fixed13_common_n','actual_local_links_checked','new_report_model_requests')}))


if __name__ == '__main__':
    main()
