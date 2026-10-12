"""Refresh the human-readable r2 status and manuscript supplement from real artifacts."""
from pathlib import Path
import collections
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import ROOT,OUT,read,write,table,filehash

def optional(path,default=None):
    return read(path) if Path(path).exists() else default

def put(name,text):
    (OUT/name).write_text(text.strip()+'\n',encoding='utf-8')

def main():
    if (OUT/'optimizer_round2_20261010/four_hour_extension_20261010/delivery/current_readout_v3/summary.json').exists():
        from cce_finalize_four_hour_delivery_v3 import main as four_hour_v5_main
        return four_hour_v5_main(publish=True)
    if (OUT/'optimizer_round2_20261010/four_hour_extension_20261010/delivery/current_readout_v2/summary.json').exists():
        from cce_finalize_four_hour_delivery_v2 import main as four_hour_v4_main
        return four_hour_v4_main(publish=True)
    if (OUT/'optimizer_round2_20261010/four_hour_extension_20261010/delivery/current_readout_v1/summary.json').exists():
        from cce_finalize_four_hour_delivery_v1 import main as four_hour_main
        return four_hour_main(publish=True)
    if (OUT/'method_family_followup_v1/plan.json').exists():
        from cce_report_method_family_v1 import main as method_family_main
        return method_family_main(publish=True)
    if (OUT/'analysis_expanded_references_v7/analysis_run.json').exists() and (OUT/'judges/schema_decode_followup_v1/completion_summary.json').exists():
        from cce_report_references_v7 import main as references_v7_main
        return references_v7_main()
    if (OUT/'analysis_expanded_references_v6/analysis_run.json').exists() and (OUT/'judges/stability_remediation_v2/analysis/report_facts.json').exists():
        from cce_report_references_v6 import main as references_v6_main
        return references_v6_main()
    if (OUT/'analysis_expanded_references_v5/analysis_run.json').exists() and (OUT/'judges/local_extraction_holdout_v1/completion_summary.json').exists():
        from cce_report_references_v5 import main as references_v5_main
        return references_v5_main()
    if (OUT/'followup_experiments_v1/summary.json').exists():
        from cce_report_followup_v1 import main as followup_v1_main
        return followup_v1_main()
    if (OUT/'expanded_tasks_v4/run.json').exists():
        from cce_report_expanded_tasks_v4 import main as expanded_tasks_v4_main
        return expanded_tasks_v4_main()
    if (OUT/'supplement_v2_idisco_t070_per_answer.json').exists():
        from cce_report_supplement_v3 import main as supplement_v3_main
        return supplement_v3_main()
    if (OUT/'supplement_v2_t070_per_answer.json').exists():
        from cce_report_supplement_v2 import main as supplement_main
        return supplement_main()
    pilot=read(OUT/'pilot_per_answer.json')
    joint=read(OUT/'analysis/pilot_participating_subset.json')
    e2=read(OUT/'controls/full_pipeline_status.json')
    e4=read(OUT/'judges/local_stability/cce_stability_summary.json')
    human=read(OUT/'human_review/archive_audit.json')
    ledger=[json.loads(x) for x in (OUT/'judges/request_ledger.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    calls=len(ledger); model_calls=dict(collections.Counter(x['model'] for x in ledger))
    write(OUT/'budget.json',{'limit':300,'attempts_recorded':calls,'remaining_request_capacity':300-calls,'model_attempts':model_calls,'retries_counted':True,'reused_observations_count_as_new_requests':False,'expert_budget':{'experts':1,'development':5,'holdout':15,'returned':0},'reference_construction_separate':True})
    step=read(OUT/'pilot_step_matches.json')
    gaps=[{'answer_id':s['answer_id'],'declared_route':s['declared_route'],'reason':s['step_missing_reason']} for s in step if s.get('step_missing_reason')]
    table(OUT/'reference_gap_pilot.csv',gaps)
    write(OUT/'remaining_dependencies.json',{
        'expert_review':'One expert, 5 development + 15 holdout candidates; no labels returned. Source applicability/step interpretation still pending.',
        'human_archive':'Confirm authentic provenance/rubric of conflicting historic labels; s_method mapping unresolved; machine-adjusted labels not independent gold.',
        'complete_references':'2 source-extracted development candidates, 0 expert-confirmed routes. PEGASOS main-text operations and 6 archived answers are bound; Table S1/Data S1 downloads failed, completeness and specific task applicability remain pending. See reference_recovery/pegasos_source_review.md.',
        'controlled_validation_remaining':'6 real-answer alternative-route candidate pairs / 9 unique answers are frozen; confirmed eligible=0, completed=0. The future same-configuration matrix needs 9 requests after reference/applicability confirmation. Three full-pipeline granularity pairs are complete; total completed controls=15.',
        'holdout':'15 selected extraction-review candidates lack complete step references; source-family independence cannot yet be established.',
        'primary_evaluator':'Historical evaluator/settings unavailable; local substitute explicitly diagnostic. Llama copies rubric example in 6/6 observations.',
        'wetlab':'No donor-level observations or final endpoint, meaningful difference, variance, routes/design; planned only.',
        'external_api':'2 connection errors; escalation rejected for payload/destination approval. No retry after rejection; local results available.'})
    language={'scope':'first_source_pilot','scored_answers':sum(s['sr'] is not None for s in step),'generated_steps':sum(s.get('generated_n',0) for s in step),
        'generated_cjk_steps':sum(s.get('generated_cjk_steps',0) for s in step),'generated_truncated_steps':sum(s.get('generated_truncated',0) for s in step),
        'reference_truncations_across_scored_answers':sum(s.get('reference_truncated',0) for s in step),
        'encoder_scope':'Original English all-mpnet-base-v2 baseline; mixed-language values are diagnostic, not validated cross-language matching.',
        'development_change':'Bilingual segmentation and full-width protocol-header colon repaired after software audit; no human held-out labels used; source/task families exposed are marked development.'}
    write(OUT/'language_and_truncation_audit.json',language)
    expanded_step=optional(OUT/'two_source_t070_step_matches.json',[])
    expanded_language={**language,'scope':'two_source_development_expansion',
        'scored_answers':sum(s['sr'] is not None for s in expanded_step),
        'generated_steps':sum(s.get('generated_n',0) for s in expanded_step),
        'generated_cjk_steps':sum(s.get('generated_cjk_steps',0) for s in expanded_step),
        'generated_truncated_steps':sum(s.get('generated_truncated',0) for s in expanded_step),
        'reference_truncations_across_scored_answers':sum(s.get('reference_truncated',0) for s in expanded_step)}
    write(OUT/'two_source_language_and_truncation_audit.json',expanded_language)
    means=joint['means'];flash=means['gemini-3-flash'];pro=means['gemini-3-pro']
    control={x['condition']:x for x in e2['conditions']}
    delete=control['necessary_step_deletion']
    plot_n=len(list((OUT/'figures').glob('*.png')))
    order_path=OUT/'judges/local_order_conflicts/paired_order_summary.json'
    order=optional(order_path)
    expanded=optional(OUT/'two_source_t070_per_answer.json',[])
    granularity=optional(OUT/'judges/local_granularity/paired_results.json',[])
    expanded_n=sum(r['sr'] is not None for r in expanded)
    total_pairs=12+len(granularity)
    write(OUT/'reference_recovery/reference_construction_current.json',{
        'scope':'two_source_development_candidates_not_expert_confirmed',
        'source_extracted_route_candidates':2,'source_families':2,'expert_confirmed_routes':0,
        'pilot_numeric_answer_links':expanded_n,'new_pegasos_answer_links':6,
        'task_families':3,'question_ids':[2,21,22,23,248],
        'expert_minutes':None,'reference_construction_separate_from_20_answer_budget':True,
        'workload_ledger':'../human_review/reference_construction_ledger.csv',
        'first_source_snapshot':'reference_construction_ledger.json',
        'expert_review_package_scope':'The unchanged five development cases bind to the FDISCO-only pilot; no new expert labels or PEGASOS expert validation.',
        'remaining':'Confirm completeness and task applicability of both candidates; FDISCO Table S1 and PEGASOS Table S1/Data S1 remain unavailable.'})
    expansion_note=f'第二来源扩展已将 PEGASOS 2018 固定软组织分支的主文操作与 6 份真实 DeepSeek 答案绑定。三阈值均重算全部 65 份，暂定 SR/SP 数值由 14 增至 {expanded_n}，45 份仍待参考；第一来源的成功结果和分数原样保留。当前全库扩展表为 3,288 行，20 份有暂定 CCE，Cor/Eff 仍为 3,287 行。固定 13 模型 Q* 仍为 0，预先指定的双 Gemini 五题子集结果不变，其重采样仍仅含一个来源家族。[扩展逐答案表](two_source_t070_per_answer.csv)、[扩展全库表](analysis_two_source/revised_full_numeric_rows.csv)、[联合分析](analysis_two_source/joint_summary.json)'
    expansion_limit='PEGASOS 候选保留 source_extracted 身份：Table S1 和 Data S1 已定位但读取失败，专家完整性及具体双标记适用性尚未确认。主文的一个月保存定量来自肠组织，不能升级为脑块六个月有效性证据，也没有把一个月改成 s_time 失效上限。已核对 2019 年作者勘误；原参数完整性、Cor 和 EGES 公式未改变。[来源复核](reference_recovery/pegasos_source_review.md)、[作者勘误](https://www.nature.com/articles/s41422-019-0180-5)'
    granularity_note='新增 3 对相邻条目合并诊断，精确复用 3 条规范编号基线，仅新增 3 次 Qwen 请求。操作、参数和顺序逐字保持；SP 三对均上升，SR 只在 q22 上升 0.142857。q2 的提取时长从 60 变为 192 小时，使 Eff/IA 下降 0.25；这里记录提取的表示敏感性，未将任何一个时长裁定为专家真值。三对均无步骤截断，c_param 与 Correctness 不变。不能把 SP 上升写成方案改善。[逐对结果](judges/local_granularity/paired_results.csv)、[粒度图](figures/granularity_sensitivity.png)'
    expanded_route=optional(OUT/'controls/two_source_route_filter_diagnostic_summary.json')
    expanded_route_note=''
    if expanded_route:
        expanded_route_note='双来源无筛选诊断进一步发现：两份明确声明 PEGASOS 的答案（DeepSeek Chat q21/q23）从 FDISCO 参考借得 SR=0.142857，而相容参考下均为 0。另有 13 份参考不足答案在无筛选分支得到正 SR。所有诊断值单列，主 NA 不填回；这支持报告相容筛选的作用，但不证明全部适用判定已获验证。[双来源筛选对照](controls/two_source_route_filter_diagnostic.csv)'
    route_diagnostic=optional(OUT/'controls/route_filter_diagnostic_summary.json')
    route_note=''
    route_note_en=''
    if route_diagnostic:
        rd=route_diagnostic['overall']
        route_note=f"独立取消路线筛选诊断覆盖 65 份原答案：原有 14 份的 SR/SP 不变；其余 51 份主结果仍为参考不足，但无筛选分支有 {rd['main_missing_with_positive_unfiltered_sr_n']} 份得到正 SR。这说明相似度数值本身不能代替适用参考；这些诊断值未写回 CCE，也未增加科学覆盖。当前只有一条参考，因此 max-SR 选择退化，不能据此验证多路线筛选准确性。[诊断表](controls/route_filter_diagnostic.csv)"
        route_note_en=f"An offline route-filter ablation preserved SR/SP for all 14 main evaluable answers. Of the other 51 answers, {rd['main_missing_with_positive_unfiltered_sr_n']} received positive SR after removing the route filter, but their main reference-insufficient status remained unchanged. These algorithmic values did not add scientific coverage or enter CCE. With only one candidate reference, this diagnostic cannot validate selection among multiple routes. [Data: controls/route_filter_diagnostic.csv.]"
    order_note='顺序冲突补充对照仍在运行；完成后见 judges/local_order_conflicts。' if order is None else '另以统一编号的自然答案操作序列构建 3 对有原文先后关系依据的顺序冲突：基线与变体各自重新评价，共 6 次新请求。三对 co_order 均为 3→3、Cor 为 1→1，未响应；SR/SP 不变符合其无序匹配定义。操作和参数多重集完全保留，编号和文本顺序一致。[配对结果](judges/local_order_conflicts/paired_order_results.csv)。初始九对加这三对，共完成十二对，仍只有三个源答案、两个任务家族和一个来源家族，不能把十二对当作十二个独立样本。'
    put('RESULTS_zh.md',f'''# ClearEval r2 补充实验实际结果（2026-10-09）

本轮已打通真实原文—存档答案—SR/SP—CCE 数值入口，完成开发性受控比较和当前本地评价器的真实重复。主要发现是：步骤指标对阈值和表述敏感；IA 的最小值汇总可掩盖未触及瓶颈的退化；评价器重复一致仍可能复制量表示例。参考适用性、新专家核查与历史评委设置尚未完全确认，以下均不替代正式全队列结论。

## 真实数据与第一条路线

固定 13 个可识别的 1-shot 生成模型，共 3,288 份存档答案。所有答案逐字匹配修订前题干，0 份匹配当前题干。3,287 条完整旧分数的 Cor 与 EGES 复算逐项等于原函数；另 1 条评分失败。旧分数缺少答案散列和完整评价设置，按“文件名模型＋qid＋逐字题干”连接后仍标历史描述性结果。[盘点](inventory/REPORT.md)、[公式检查](implementation_checks.json)

首条来源为 Qi 等的 FDISCO 原文，DOI [10.1126/sciadv.aau8355](https://doi.org/10.1126/sciadv.aau8355)，原始 XML、章节位置和 SHA256 已保存。参考恢复为固定后任务范围的 7 个操作，未把固定等初始条件重新计分，状态为 source_extracted，尚无专家确认。q2 两份真实答案在阈值 0.7 下的 SR 为 0.142857、0.857143，SP 为 0.750000、0.777778；匹配明细可追溯到原答案偏移。[参考快照](pilot_references.json)、[逐答案表](pilot_per_answer.csv)、[对应来源](reference_recovery/answer_source_links.json)

首轮覆盖 q2、q21、q22、q23、q248，13 模型共 65 份答案；其中 14 份可进行第一来源参考下的 SR/Com 计算，51 份保留参考不足。五题对应 3 个任务家族，首轮同属 1 个来源家族。[首轮全库逐答案表](analysis/revised_full_numeric_rows.csv)

{expansion_note}

{expansion_limit}

## 受控全文评价

3 份自然基线与 9 份变体均通过相同本地 Qwen3:8b 配置重新提取和判分，形成 9 对完整管线比较。每份全文、变体标识、编辑偏移、输入与配置散列、原始模型回执均已保存。SR/SP 使用重新解析的编辑全文；参数完整性、Correctness 与 EGES 使用这次真实提取/评分，未沿用基线 JSON。上游 cce_eligible=false 仍保留，结果身份为本地替代评价器的开发性数值诊断。[配对表](controls/full_pipeline_pairs.csv)、[运行记录](judges/EXECUTION.md)

删除 RI/保存模块后，2/3 对 SR 下降，1/3 无响应；平均 ΔSR={delete['mean_delta_sr']:.6f}、ΔCom={delete['mean_delta_Com']:.6f}、ΔHV={delete['mean_delta_HV']:.6f}，三对 ΔIA 均为 0。因为 Eff 仍是更低维度，Com 下降尚未改变 min 汇总。这是 HV 补充 IA 的开发性实例，不是全域效果证明。删除的是联合模块，不能写成单一原子步骤检出率。[对应图](figures/full_pipeline_controls.png)

删除全部明确处理时长后，三份 c_param 均仍为 3；这保留了评价器未响应的结果，不能据此宣称参数缺失检出成功。确定性编号变化的三对 SR/SP 完全相同，但一例 Eff/IA 有小幅变化；全组平均 ΔEff={control['deterministic_equivalent_representation']['mean_delta_Eff']:.6f}，不能将其概括为完整 CCE 严格不变。{order_note}

{granularity_note}

当前累计 {total_pairs} 对全文比较仍来自 3 份源答案、2 个任务家族和 1 个来源家族。另已冻结 6 对替代路线候选、9 份真实答案，资格确认和全文运行均为 0；补充与专家确认后计划 9 次同配置请求，不能把待运行矩阵计入完成数。[替代路线待运行矩阵](controls/alternative_route_waiting_matrix.json)

## 评价稳定性与提取风险

两份开发答案 × 两个本地家族 × 三次，共 12 个真实管线观测；其中 2 条 Qwen baseline 原始请求预先指定为 repeat0，另 10 条来自新请求。temperature=0，数值重复极差为 0。与此同时，Llama 的 6/6 次 extraction 与 rubric 末尾示例完整字典一致，全部把原文声明路线 FDISCO 提为 CUBIC。跨家族数值差异因此保留为失败诊断，不作为两个有效评价器的一致性结论。重复一致不等于提取忠实，更不等于科学有效。[真实观测](judges/local_stability/cce_per_observation.csv)、[示例复制证据](judges/local_stability/scientific_failure_flags.json)、[稳定性图](figures/local_judge_stability.png)

## CCE、阈值与覆盖

固定 13 模型的新 CCE 共同可评分集为空，不能发布这一队列的新排名。预先选定的双 Gemini 开发子集共同五题：Flash 的平均 CCE=({flash['Com']:.6f}, {flash['Cor']:.6f}, {flash['Eff']:.6f})，IA={flash['IA']:.6f}，HV={flash['HV']:.6f}；Pro=({pro['Com']:.6f}, {pro['Cor']:.6f}, {pro['Eff']:.6f})，IA={pro['IA']:.6f}，HV={pro['HV']:.6f}。Pro 在这个小型开发子集构成三维非支配点；它不能替代固定全队列结果。[共同题集与汇总](analysis/joint_summary.json)

已完成 2,000 次同步来源家族重采样，但只有一个来源家族，重采样退化，零宽区间和 100% 入选频率不支持泛化可靠性。阈值 0.6/0.7/0.8 下，Flash 平均 SR=0.942857/0.571429/0；Pro=0.914286/0.571429/0，显示强阈值敏感性。编码器为原 BioProBench English baseline；中文解析已修复，中文嵌入匹配仍需开发验证。[阈值结果](analysis/threshold_sensitivity.json)、[语言与截断](language_and_truncation_audit.json)

{route_note}

{expanded_route_note}

原分类覆盖实际包含 2,588 道 MCQ（Domain Knowledge 1,350、Task Scenario 705、NER 533）和 253 道开放题。category、knowledge_point、specific 分别沿用原字段，不重编为一棵层级树。[覆盖数据](analysis/dataset_coverage.csv)、[覆盖图](figures/dataset_category_coverage.png)

## 人工与湿实验边界

恢复 240 份历史标签（20 题×12 模型），原题/答案均与历史存档匹配。人评两个版本中 co_method 197、co_chem 214、s_method 218、s_label 167、s_trans 220 份分项不同；姓名和日期均未恢复。summary 的 s_label/s_trans 各 240 条带机器调整记录，不能当独立专家金标；人工 s_method 未擅自映射，未构造人工 E/CCE。[逐项可比性](human_review/subitem_comparability.csv)

新人工仍为 1 位专家、5 开发＋15 留出预选，步骤与提取共用，160 个专家判项均为空。15 份留出候选缺完整步骤参考，因此不能声称来源家族独立留出已完成。完整参考建设另列，PEGASOS 新增候选的来源阅读计入独立工作量，未伪造专家确认。第二路线尚未形成合格完整配对；待完成补充完整性、版本选择与适用性确认，不能把这些缺口统称为缺原文。[来源可用性审计](reference_recovery/source_availability_audit.md)。E3 忠实提取修正与配对影响入口已运行，在无回传时返回待定。湿实验仅完成 42 个明确标为假设的功效情景、随机分组入口、空数据模板及供体级分析入口；真实测量行数为 0。[人工入口](human_review/EXPERT_RETURN_CONTRACT.md)、[湿实验计划](wetlab/WETLAB_PLAN.md)

## 当前预算与复现

已记录 {calls} 次模型请求尝试，上限 300，剩余额度 {300-calls}；离线计算及复用不重复计数。图表已输出 {plot_n} 组 PNG/SVG/PDF 和逐图 CSV。所有步骤来源、冻结配置、实际命令与待补依赖保存在本目录。[命令](commands.md)、[状态](STATUS.md)、[预算](budget.json)
''')
    put('Methods_Results_en.md',f'''# Supplementary Methods and Results — development execution

## Methods

We retained ClearEval's parameter-completeness scale, four correctness subscales, and Evidence-Grounded Effectiveness Scoring (EGES). Step Recall and Step Precision followed the cosine-threshold rule in the [BioProBench implementation](https://github.com/YuyangSunshine/bioprobench/blob/main/Metrics/GEN.py), using the locally cached all-mpnet-base-v2 encoder at delta=0.7. Completeness was 0.4 SR + 0.6 c_param/3; SP was reported separately. Correctness and effectiveness retained their existing normalization and equal-weight aggregation. IA=min(Com,Cor,Eff) and HV=Com*Cor*Eff, relative to (0,0,0), were computed per answer before averaging. Development calculations considered only route-compatible source-extracted reference candidates, whose completeness and applicability remained pending; SR, SP, and fixed reference order resolved ties. Unknown components remained missing.

The prespecified cohort comprised all 13 identifiable archived 1-shot generators. We matched archived question text exactly to the pre-revision snapshot and retained evidence/settings limitations for inherited scores. A primary-source FDISCO route was recovered for development, with seven task-scoped operations and explicit exclusions for completed initial conditions. Five question IDs represented three task families. A second PEGASOS main-text candidate was subsequently bound to six archived answers; its supplementary schedules and expert completeness/applicability confirmation remained pending. All 65 answers were rescored at each threshold under the expanded frozen reference collection, preserving the successful first-source batch. The [published correction](https://www.nature.com/articles/s41422-019-0180-5) to the PEG reagent catalog identifier was checked. Neither candidate was treated as expert-confirmed evidence. Step segmentation retained associated parameters, excluded pure headings, and was repaired for bilingual operations using development material. The [encoder card](https://huggingface.co/sentence-transformers/all-mpnet-base-v2) identifies English usage and a 384-word-piece default limit; actual language and truncation counts are reported separately.

For controlled evaluation, three archived answers each received one module-deletion, duration-deletion, and deterministic-numbering variant. Every baseline and edited full text was evaluated afresh with the same frozen local Qwen3:8b configuration and fixed task demands; each answer was also segmented and matched again. Cached results were reused only when their full input and configuration identities matched. The original numerical functions and upstream scientific-eligibility flags were retained. Two development answers were evaluated three times by each of two local model families at temperature zero. Two existing baseline requests were prespecified as the first Qwen repeats; the remaining ten observations required fresh requests. These experiments characterize current substitute evaluators, not the historical evaluator.

Common-question CCE comparison used a fixed model cohort. We performed 2,000 synchronized source-family bootstrap draws, retaining all questions within sampled families and weighting questions equally. Threshold sensitivity used 0.6, 0.7, and 0.8 with common evaluable inputs. Single-source resampling was explicitly identified as degenerate. One expert was assigned five development and fifteen held-out review candidates shared between step and extraction audits; no returned expert labels were synthesized. Reference construction was counted separately.

## Results

We recovered 3,288 archived answers across 13 models; all matched the historical question snapshot and none matched the revised snapshot. The original Cor and EGES values were reproduced for 3,287 complete archived score records. The five-question pilot contained 65 answers. The first-source batch yielded 14 provisional SR/SP values; adding the second source candidate increased this to 20, leaving 45 unresolved. This was a numerical coverage expansion, not confirmation of route completeness or scientific validity. The fixed 13-model revised-CCE common set remained empty, prohibiting a revised full-cohort ranking. [Data: pilot_per_answer.csv; two_source_t070_per_answer.csv; analysis_two_source/revised_full_numeric_rows.csv.]

All 12 baseline/variant full-text calls in the initial control batch completed, yielding nine pairs. Removing the RI/storage module reduced SR in two of three pairs, with mean delta SR={delete['mean_delta_sr']:.6f}, delta Com={delete['mean_delta_Com']:.6f}, and delta HV={delete['mean_delta_HV']:.6f}. IA remained unchanged in all three pairs because Eff remained the limiting dimension. This illustrates the complementary information supplied by HV in this development set. Removing explicit durations did not lower c_param in any of the three pairs. Deterministic numbering preserved SR/SP exactly but caused a small downstream effectiveness change in one pair. Nonresponses and adverse responses were retained. [Data: controls/full_pipeline_pairs.csv.]

An additional three source-supported order-conflict pairs were constructed from canonically numbered natural-answer operations. Both baselines and variants received fresh evaluations, adding six requests. Operation and parameter multisets were identical, and document order agreed with numbering. The order score remained 3 in all six answers, and Cor remained 1 in all three pairs. SR/SP were unchanged, as expected from order-insensitive matching. Together, the twelve pairs derive from three distinct answers representing two task families and one source family; the additional diagnostic does not add independent source families. [Data: judges/local_order_conflicts/paired_order_results.csv.]

All 12 repeated local pipeline observations were technically completed. Within each answer-by-evaluator group, the observed numerical range was zero. However, all six Llama extractions exactly matched the rubric's example extraction and assigned CUBIC to answers explicitly declaring FDISCO. These results demonstrate repeatable extraction failure rather than scientific validity. Cross-family score differences are therefore diagnostic observations, not agreement estimates between validated evaluators. [Data: judges/local_stability/scientific_failure_flags.json and cce_per_observation.csv.]

Three further full-pipeline granularity pairs merged adjacent numbered entries while preserving every operation, parameter and their order. The three identical canonical baseline trials were reused and only three new judge requests were made. SP increased in all three pairs, and SR increased in one. In q2, the extracted processing time changed from 60 to 192 hours and Eff/IA decreased by 0.25. This was an extraction observation, not a verified correction of either time. These pairs bring the completed control total to fifteen, still based on three source answers. Six additional alternative-route candidate pairs are frozen but remain unqualified and unexecuted pending reference confirmation. [Data: judges/local_granularity/paired_results.csv; controls/alternative_route_waiting_matrix.json.]

In the prespecified two-Gemini development subset, five-question mean IA/HV were {flash['IA']:.6f}/{flash['HV']:.6f} for Flash and {pro['IA']:.6f}/{pro['HV']:.6f} for Pro. Pro was nondominated in this subset. Both models had mean SR=0.571429 at delta=0.7 and zero at delta=0.8. Only one source family supported this analysis, so the bootstrap was degenerate and did not establish ranking generalizability. Historical human-label versions also disagreed in five subscales, and machine-adjusted label records were not used as independent gold standards. New expert correction effects and wet-lab outcomes remain pending. [Data: analysis/joint_summary.json; analysis/threshold_sensitivity.json; human_review/archive_audit.json.]

{route_note_en}

With both reference candidates present, unrestricted max-SR selected FDISCO for two answers explicitly declaring PEGASOS, increasing their SR from 0 to 0.142857. Thirteen of the remaining 45 reference-insufficient answers also received positive unrestricted SR, without changing their primary missing status. These findings illustrate the behavior of compatibility filtering; the source candidates and language matching still require validation. [Data: controls/two_source_route_filter_diagnostic.csv.]
''')
    put('Abstract_en.md',f'''# Development supplement abstract — provisional, not a replacement for the final paper abstract

Tissue optical-clearing protocol generation requires domain knowledge, complete procedural specification, and choices compatible with fixed experimental requirements. We integrated BioProBench step recall and precision into ClearEval while retaining parameter completeness, correctness, and Evidence-Grounded Effectiveness Scoring (EGES). We recovered 3,288 archived answers from 13 models. Two source-extracted reference candidates supported provisional numerical scoring of 20 of 65 answers in a five-question development set. Fifteen full-pipeline controlled pairs from three source answers revealed both responsive and nonresponsive cases: module deletion reduced completeness and hypervolume in two of three pairs while leaving the minimum-based application index unchanged; none of three order-conflict pairs lowered the order score; and regrouping unchanged steps altered extracted time and effectiveness. Twelve actual evaluator observations showed numerical repeatability, yet six extractions from one local evaluator exactly copied the rubric example. These findings identify complementary roles for component reporting and joint summaries, and distinguish repeatability from extraction validity. Strong threshold and representation sensitivity, incomplete route coverage, and pending expert review currently prevent a revised full-cohort ranking. Wet-lab outcomes remain unmeasured.
''')
    put('STATUS.md',f'''# ClearEval r2 — 2026-10-09

状态：已完成两来源候选评分扩展、15对全文受控比较和本地评价重复；完整参考建设、适用性确认、专家回传及湿实验尚未完成。完整新模型排名未成立（固定13模型Q*=0）。

| 阶段 | 已运行真实产物 | 数量/边界 |
|---|---|---|
| A | two_source_t070_per_answer.csv、参考/配置快照、原文hash | 5题×13模型=65；暂定SR/SP由14增至20；2来源候选/3任务家族；45份待参考 |
| E1/E3 | human_review/ | 240历史标签核对；1专家5+15材料；0新回传 |
| E2 | controls/、judges/local_order_conflicts/、judges/local_granularity/ | 初始9对＋顺序3对＋合并3对＝15对；共21次新评分、另复用3条基线；3答案/2任务家族/1来源家族；全部开发性 |
| E4 | judges/local_stability/ | 2答案×2家族×3=12真实观测；6次示例复制失败保留 |
| E5 | analysis_two_source/、figures/、figures_two_source/ | 全库3288行中20份暂定CCE；3阈值；双Gemini共同集仍为2000次单来源退化重采样；主目录{plot_n}图，扩展目录10组重算图 |
| E6 | wetlab/ | 42假设功效情景；实际测量0；planned |

{expansion_note}

{expansion_limit}

{granularity_note}

{expanded_route_note}

预算：新增请求尝试 {calls}/300，剩余容量 {300-calls}；详见 budget.json 和 judges/request_ledger.jsonl。成功请求按全文、参考、模型配置和代码散列复用，不把公式重算当重复。原 checkout 的已有修改保留，新增代码位于 scripts/cce_*.py。

剩余工作与依赖：专家真实回传；两条候选参考的完整性及适用条件确认，尤其PEGASOS补充材料尚未读取；完整替代路线比较已冻结6候选对/9份真实答案，但合格与完成均为0，待条件满足后按同配置执行；历史人工量表/版本身份；湿实验设计输入与真实供体数据。15份留出预选暂缺步骤参考，不宣称来源家族独立。原5份开发材料仍绑定FDISCO-only批次，新增PEGASOS来源复核未计为专家回传或人工验证。具体清单见 remaining_dependencies.json 和 reference_recovery/source_availability_audit.md；当前参考工作汇总见 reference_recovery/reference_construction_current.json。

下一条离线恢复命令（复用现有结果，不发模型请求）：

```powershell
Set-Location C:\\ClearEval\\ClearEval-public
& 'C:\\ClearEval\\review_artifacts\\bioprobench_2026-09-29\\python_portable\\python.exe' scripts/cce_report.py
```

专家回传后的实际入口见 human_review/EXPERT_RETURN_CONTRACT.md；模型请求复现命令见 judges/EXECUTION.md。外部Qwen提权重试被自动审批拒绝：需要具体全文内容和接收方的明确授权；拒绝后未再发送，后续实验使用本机loopback。
''')
    put('commands.md','''# 已实际执行的命令

工作目录 `C:\\ClearEval\\ClearEval-public`。以下评分、校验和统计均已运行成功；外部传输失败单独记录于 judges/controls，不作为成功科学结果。

```powershell
$pyExe = 'C:\\ClearEval\\review_artifacts\\bioprobench_2026-09-29\\python_portable\\python.exe'
& $pyExe scripts/cce_validation.py --help
& $pyExe scripts/cce_prepare.py references
& $pyExe scripts/cce_validation.py score --qids 2 --models gemini-3-flash gemini-3-pro --tag first_route
& $pyExe scripts/cce_validation.py score --qids 2 21 22 23 248 --tag pilot
& $pyExe scripts/cce_validation.py score --qids 2 21 22 23 248 --threshold 0.6 --tag pilot_t060
& $pyExe scripts/cce_validation.py score --qids 2 21 22 23 248 --threshold 0.8 --tag pilot_t080
& $pyExe scripts/cce_validation.py check
& $pyExe scripts/cce_prepare.py controls
& $pyExe scripts/cce_prepare.py score-controls
& $pyExe scripts/cce_finalize_controls.py
& $pyExe scripts/cce_finalize_stability.py
& $pyExe scripts/cce_analysis.py
& $pyExe scripts/cce_analysis.py --supplement-only
& $pyExe scripts/cce_route_diagnostic.py
& $pyExe scripts/cce_recover_pegasos.py
& $pyExe scripts/cce_score_reference_expansion.py --threshold 0.7 --tag two_source_t070
& $pyExe scripts/cce_score_reference_expansion.py --threshold 0.6 --tag two_source_t060
& $pyExe scripts/cce_score_reference_expansion.py --threshold 0.8 --tag two_source_t080
& $pyExe scripts/cce_prepare_alternative_pairs.py
& $pyExe scripts/cce_granularity_plot.py
& $pyExe scripts/cce_analysis.py --pilot artifacts/cce_validation/two_source_t070_per_answer.json --sensitivity-files artifacts/cce_validation/two_source_t060_per_answer.json artifacts/cce_validation/two_source_t070_per_answer.json artifacts/cce_validation/two_source_t080_per_answer.json --out artifacts/cce_validation/analysis_two_source --figures artifacts/cce_validation/figures_two_source
& $pyExe scripts/cce_verify.py
& $pyExe scripts/cce_report.py
```

first_route 为初次贯通记录，其初始参考保存在 reference_recovery/initial_q2_reference_snapshot.json。首轮可审计结果采用 pilot 系列，第二来源扩展另存 two_source 系列；各自保留 resolved_config.json/references.json 快照，未覆盖首轮成功结果。解析修订见 implementation_review.md。同一编码器下未变文本的成功嵌入缓存被复用。两来源筛选诊断的实际完整命令见 [独立运行记录](controls/two_source_route_filter_diagnostic.md)；来源公开补充下载的连接失败见 [下载记录](reference_recovery/pegasos_sources/public_download_manifest.json)。

真实本地 E2/E4 调用、成功缓存与预算命令见 [judges/EXECUTION.md](judges/EXECUTION.md)；新增三对合并的实际命令与精确基线复用见 [合并实验记录](judges/local_granularity/EXECUTION.md)。人工核查及湿实验已经执行的命令见 [human_review/EXECUTION.md](human_review/EXECUTION.md)。这些文档保留实际参数与成功/待定边界。
''')
    print(json.dumps({'report_updated':True,'model_request_attempts':calls,'remaining_request_capacity':300-calls,'plots':plot_n,'formal_eligible':False}))

if __name__=='__main__':main()
