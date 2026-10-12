"""Assemble the verified ScaleS delta, technical follow-up and route diagnostic."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
HIST = BASE / 'historical_reports/before_holdout_remediation_at_116'
ANA = BASE / 'analysis_expanded_references_v7'
HOLD = BASE / 'judges/holdout_remediation_v2'
SCHEMA = BASE / 'judges/schema_decode_followup_v1'
ABL = BASE / 'controls/paired_route_ablation_v7'
REVIEW = BASE / 'human_review/versioned_review_v1'
LABELS = BASE / 'figures_development_label_coverage_v1'
VERSION = 'references_v7_technical_followup_ablation_at_136'


def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, value): Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def write(p, value): Path(p).write_text(value.strip()+'\n',encoding='utf-8')


def main():
    for r in read(HIST / 'snapshot_manifest.json')['files']:
        assert sha(HIST / r['relative_path']) == r['sha256']
    ledger_path = BASE / 'judges/request_ledger.jsonl'
    ledger = [json.loads(s) for s in ledger_path.read_text(encoding='utf-8').splitlines() if s.strip()]
    ledger = [r for r in ledger if r.get('event') == 'request_started']
    prior = [json.loads(s) for s in (HIST / 'judges/request_ledger.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    assert ledger[:116] == prior and len(ledger) == 136
    assert [r['package_request_index'] for r in ledger] == list(range(1,137))
    assert len({r['request_id'] for r in ledger}) == 136
    assert sha(ROOT / 'scripts/cce_validation.py') == 'd272393ecbba84495e0430d01c0b52c4f69a6d9502147bdb071371dfed2bdc20'
    assert sha(BASE / 'human_review/reviewer/review_items.csv') == '7ae708d91938b7e60737298261234e483caee4b50475ee20219cb188667ff5aa'
    assert read(BASE / 'human_review/expert_extraction_corrections.json') == []
    ar = read(ANA / 'analysis_run.json')
    joint = read(ANA / 'joint_summary.json')
    hold = read(HOLD / 'completion_summary.json')
    schema = read(SCHEMA / 'completion_summary.json')
    ablation = read(ABL / 'summary.json')
    review_gate = read(REVIEW / 'preflight.json')
    assert review_gate['status'] == 'ready_pending_real_expert_returns'
    assert review_gate['actual_auto_records'] == 19 and review_gate['missing_auto_ids'] == ['A15']
    assert review_gate['reviewed_extraction_rows'] == review_gate['version_acknowledgements'] == 0
    assert review_gate['manifest_sha256'] == sha(REVIEW / 'manifest.json')
    assert read(REVIEW / 'received_receipts.json')['records'] == []
    review_check = read(BASE / 'human_review/versioned_review_guard_review_v1/independent_review.json')
    assert review_check['status'] == 'pass' and review_check['no_change_and_correction_receipt_gate_before_bridge']
    assert review_check['real_version_acknowledgements'] == review_check['new_real_expert_labels'] == 0
    for name, expected in review_check['reviewed_files'].items(): assert sha(name) == expected, name
    label_qa = read(LABELS / 'figure_qa.json')
    assert label_qa['status'] == 'pass' and label_qa['counts'] == {'tasks':6,'models':13,'answers':77,'numeric':50,'reference_NA':27,'absent_answers':1}
    for name, expected in label_qa['outputs'].items(): assert sha(LABELS / name) == expected, name
    refs = read(BASE / 'expanded_references_v7/references.json')['references']
    rows = read(BASE / 'expanded_references_v7_t070_per_answer.json')
    targets = set(read(BASE / 'expanded_references_v7/plan.json')['target_answer_ids'])
    added = [r for r in rows if r['answer_id'] in targets]
    assert ar['numeric_CCE'] == ar['numeric_steps'] == 50 and len(rows) == 77 and len(added) == 4
    assert len(refs) == 10 and len({r['family_id'] for r in refs}) == 5
    assert joint['revised_full_fixed_cohort']['common_question_ids'] == ['2']
    assert joint['formal_fixed_cohort']['common_n'] == 0
    assert hold['successful_cells'] == hold['identity_verified_cells'] == 14 and hold['failed_cells'] == 1
    assert hold['paired_transitions'] == {'old_failure_new_success':7,'old_success_new_success':7,'old_failure_new_failure':1,'old_success_new_failure':0}
    assert schema['development_successful'] == 4 and schema['followup_attempted'] == 0
    assert ablation['unique_pairs'] == 3 and ablation['new_judge_requests'] == 0
    assert read(BASE / 'expanded_references_v7/independent_numeric_review.json')['status'] == 'pass'
    assert read(SCHEMA / 'independent_review.json')['status'] == 'pass'
    assert read(BASE / 'figures_expanded_references_v7/figure_visual_qa.json')['status'] == 'pass'
    metrics = ('sr','sp','Com','Cor','Eff','IA','HV')
    result_table = '\n'.join('| '+r['answer_id']+' | '+' | '.join(f'{r[k]:.6f}' for k in metrics)+' |' for r in added)
    zh = f'''# ClearEval r2 当前结果：136 次请求

新增 ScaleS 作者原版补充材料已恢复并完成评分前来源核查。固定6题、13模型、77份存档答案中，条件性完整CCE从46增至50，参考不足从31降至27。三个阈值各73个旧行对象原样复用、4份新增评分；全部77份原参数完整性、Correctness、EGES不变。实际重解析/比较231行，独立缓存点积与CCE算术核验通过，仅新增7个本地向量、0次judge请求。[逐答案CSV](expanded_references_v7_t070_per_answer.csv)、[原始来源与条件范围](reference_recovery/development_binding_followup_v1/README.md)、[实际命令](expanded_references_v7/EXECUTION.md)、[独立数值核验](expanded_references_v7/independent_numeric_review.json)。

| 新可评分答案 | SR | SP | Com | Cor | Eff | IA | HV |
|---|---:|---:|---:|---:|---:|---:|---:|
{result_table}

新参考包含作者报告的7个固定后操作，保存作为持续条件，15个月整脑YFP观测不作为必需操作或3mm双标效果证据。3mm具体时程、部分答案所选弱GFP与MAP2的兼容及六个月目标仍未确认。GLM q21和Claude q21在主阈值均为零SR，但分别有4与20个非空解析段落、均未截断；零匹配不等于答案没有操作。主参考共10个条件分支、5个来源家族，专家适用性确认仍为0。[来源核查](expanded_references_v7/source_scope_review.json)、[来源建设台账](human_review/reference_construction_v5/README.md)。

**受控参考筛选的新发现。** 对既有q2/q21/q22三对、六份完整文本，在三阈值重算旧/新参考池的相容筛选与无筛选max-SR。主阈值下，q2按自身FDISCO参考的SR从6/7降至5/7（Δ=−1/7）；无筛选新池对两份文本都改选uDISCO，SR均8/9（Δ=0），掩盖了删除响应。0.6下相应Δ为−2/7和−1/9；0.8下均0。q21/q22在各阈值均未改变。旧池主阈值无差异结果精确重现并保留，不能只呈现新阳性例子。此为参考池增量诊断，仍只有3个原配对，不是9个独立案例，不修改主CCE，也不代替专家对步骤必要性的确认。[逐对结果与解释](controls/paired_route_ablation_v7/interpretation.md)、[核验](controls/paired_route_ablation_v7/saved_result_review.json)、[图和CSV](figures_route_ablation_v7/README.md)。

**评价输出的技术恢复。** 将已在开发材料测试的v2提示统一应用到原15份全文：14成功、1失败，较原7成功/8失败恢复7份，原成功的7份均保留。14份通过原EGES身份重算。旧批次、旧配置、原始返回、160项专家表全部保留；新版不与旧版拼成最好结果。剩余失败存在重复JSON键且值冲突，不静默取首值或末值。此批只评价技术恢复，不宣称独立留出准确性提高。[真实配对技术结果](judges/holdout_remediation_v2/README.md)、[匿名14份自动建议与1份失败](judges/holdout_remediation_v2/sealed/reviewer/README.md)。

随后独立冻结了仅改变解码器format为既有schema的开发检验。原5份开发答案真实运行4成功/1冲突重复键失败；实际schema传输、全文与回执已核对。预设5/5技术通过才继续15份，门槛未达，后续15份未调用，不能称已运行或算作15次失败。[开发结果与未运行原因](judges/schema_decode_followup_v1/README.md)、[独立核验](judges/schema_decode_followup_v1/independent_review.md)、[技术结果图](figures_technical_followup_v1/technical_followup.png)。本阶段新增15＋5次请求，总136/300，余164。

**联合结果与既有实验。** 固定13模型的暂定共同集仍仅q2；三阈值前沿仍为6/5/4。旧共同答案、分数、2,000次同步任务重采样与预定双Gemini五题子集输入不变，7份bootstrap文件和16项投影图产物按字节复用；单题重采样完全退化，来源家族bootstrap仍因同题跨路线映射未定。不能据此声称全基准排名或跨任务置信度。[全库分项覆盖](analysis_expanded_references_v7/revised_component_coverage.csv)、[共同集和支配矩阵](analysis_expanded_references_v7/joint_summary.json)、[分析独立核验](expanded_references_v7/review_analysis_v7_README.md)。全库仍有3,288份存档答案；主步骤比较覆盖6题，不能把其余题的统计框架当作新步骤计算已完成。

原问答/简答领域分类、样本与尺度分布继续使用[已有覆盖图](figures_expanded_tasks_v4/dataset_category_coverage.png)及[逐图数据](figures_expanded_tasks_v4/dataset_category_coverage.csv)，不重新命名原领域类别。

新增[开发题标记条件与参考覆盖图](figures_development_label_coverage_v1/README.md)以实际生成题干逐字证据为依据：q1/q2允许答案选择标记，q21–23指定弱原生报告和双靶点需求，不能把答案中的GFP/MAP2反推成题干要求；q248明确保留tdTomato，轴突结构靶点仍需方案选择。六题的条件性数值覆盖依次为12/12、13/13、6/13、6/13、7/13、6/13；q1另有一个未存档模型槽位。该图只描述已开发的六题，不代表全253题的标记分布，也不代表科学适用性确认。

前期15对全文受控比较、两评价器真实重复及其非响应结果全部保留。v2开发的12次调用均技术成功、64个重复组范围为0，但10/32跨评价器指标组有差异，重复稳定不等于准确。替代路线覆盖已按真实产物重新核对：6个任务有条件双路线、9个实际配对，8对技术完整覆盖6任务，6对完整数值CCE仅覆盖4任务；q1/q2的Eff/IA/HV缺项独立于专家确认，q248是来源指导改写。科学确认的合理完整替代路线仍为0。[重复调用结果](judges/stability_remediation_v2/analysis/README.md)、[替代路线覆盖事实](reference_recovery/development_binding_followup_v1/alternative_coverage_facts.md)、[此前完整结果](historical_reports/before_holdout_remediation_at_116/RESULTS_zh.md)。

一位专家、5开发＋15留出的共用核查包已就绪，真实回传仍为0。当前建议版本另以不可混用的清单和回执绑定，“无需修正”也需核对实际审阅版本；原160行表未改变。已有A06/q146条件性步骤附件无需重复创建；另14份步骤参考不足。本轮旧量表追查找到额外中间版本，240条身份可绑定但217条方法值已改动；同期论文明确逐专家原表未保留，不能由相同数值范围推出signed尺度映射。BoneClear新增三条正规一手获取途径仍未获得指定Methods附件，具体限制已记录。[人工入口](human_review/CURRENT_REVIEW_ENTRY.md)、[版本绑定](human_review/versioned_review_v1/README.md)、[旧尺度证据](human_review/legacy_scale_followup_v1/README.md)、[BoneClear缺口](reference_recovery/boneclear_primary_followup_v2/README.md)。

湿实验计划、42个假设功效情景、随机分组和真实数据分析入口已具备；真实观测为0。缺少湿实验不阻断最小计算包，也不能据假设功效表宣称生物效果。当前可运行批次已完成；专家核查、来源/任务适用性和旧尺度缺失仍限制正式结论。[逐目标状态](completion_audit_current.json)、[剩余依赖](remaining_dependencies.json)、[实际命令](commands.md)。
'''
    write(BASE / 'RESULTS_zh.md', zh)
    english = '''# Supplementary Methods and Results

We retained the archived 1-shot cohort of 13 generators and six development tasks, containing 77 answers and one missing slot. Step Recall (SR) and Step Precision (SP) used the original all-mpnet-base-v2 encoder at cosine thresholds 0.6, 0.7 and 0.8, with 0.7 fixed as primary. References were filtered by task scope and declared route before maximizing SR, then SP and fixed version order. Archived parameter completeness, correctness and EGES components were unchanged. Completeness was 0.4SR+0.6(c_param/3); correctness retained the original four normalized components. IA and HV were computed per answer before averaging. Unknown inputs remained NA. [Configuration and per-answer data](current_run_index.json).

Recovery of the original ScaleS author supplement added one conditional seven-operation clearing branch for q21–23. Exact 3-mm timing and task-specific labeling and storage outcomes were not established. Four additional archived answers became numerically scorable, increasing provisional complete CCE from 46/77 to 50/77. Across three thresholds, all 77 full answers were reparsed and compared against the old and new reference pools; 73 unchanged row objects per threshold were reused. Only seven local vectors were newly computed. Independent cached-vector arithmetic reproduced the step scores and CCE results. Two new answers received zero SR at the primary threshold despite four and twenty nonempty segments and no truncation. Thus zero matching cannot be equated with absent procedures. Ten conditional branches from five source families remained scientifically unconfirmed. [Source, execution and checks](expanded_references_v7/EXECUTION.md).

A prespecified reference-pool diagnostic reused three deletion pairs from q2, q21 and q22. At the primary threshold, route-filtered q2 SR decreased from 6/7 to 5/7. Unfiltered maximization selected uDISCO for both texts and yielded 8/9 for each, eliminating the deletion response. The corresponding filtered/unfiltered changes were −2/7 and −1/9 at 0.6, and zero for both at 0.8. q21 and q22 were unchanged. The earlier pool's primary-threshold negative result was reproduced and retained. These are three reused pairs across settings, not nine independent experiments; source-reported operation coverage does not establish expert-confirmed necessity. [Paired results and figure data](controls/paired_route_ablation_v7/interpretation.md).

The development-tested v2 prompt was frozen and applied once to all 15 original holdout texts using the same local Qwen model and empty reference context. Fourteen outputs passed the unchanged loader, versus seven under the original prompt. Seven previous failures recovered, seven successes remained successful, and one conflicting duplicate-key failure persisted. All fourteen successful extractions passed same-input EGES replay. Original outputs were preserved and versions were not pooled or selected by score. This post-exposure technical follow-up provides no independent extraction-accuracy certification. [Technical comparison and provenance](judges/holdout_remediation_v2/README.md).

A separate schema-constrained decoding intervention changed only the local format parameter to the existing typed schema. All five fixed development answers were attempted once: four passed and one failed strict parsing because a marker key had conflicting repeated values. The prespecified five-of-five development gate was not met; none of the fifteen subsequent follow-up requests was issued. Actual schema transmission, prompts, provider returns and request receipts were independently verified. Neither intervention repaired returned scientific values or changed scoring formulas. [Schema experiment](judges/schema_decode_followup_v1/README.md).

The full 13-model common set remained q2 alone, with six, five and four nondominated models across thresholds. The unchanged common-answer objects supported byte-exact reuse of seven bootstrap files and sixteen projection assets. Two thousand synchronized one-task draws remain degenerate and provide no cross-task uncertainty estimate. Source-family resampling remains unresolved because selected routes differ across models. The prespecified five-task Gemini comparison is unchanged. Broader component coverage describes 3,288 archived answers, not completed revised step scoring for all 253 tasks. [Joint analyses](analysis_expanded_references_v7/joint_summary.json).

The original domain, specimen and scale coverage plots were retained. An additional panel linked labeling requirements in the six archived generation prompts to conditional numerical reference coverage. It distinguished prompts permitting marker selection from prompts explicitly specifying labeling conditions; marker names chosen in answers were not retroactively attributed to the prompts. The six-task panel is not a labeling census of the full 253-task benchmark and does not certify scientific applicability. [Prompt evidence and figure data](figures_development_label_coverage_v1/README.md).

Previous full-text controls and two-family stability results remain available. Twelve v2 development calls had zero within-judge range in 64 metric groups, while 10/32 cross-family groups differed. Nine actual alternative-route pairs cover six task IDs; eight are technically complete, and six have complete numerical CCE across only four tasks. No pair has expert-confirmed full-task applicability. One expert's fixed five-development/fifteen-holdout review is pending, with no fabricated corrections. A separate manifest and receipt bind both corrections and reviewed-no-change decisions to the machine-suggestion version actually reviewed; the original 160-item form is preserved. Historical method-scale recovery remains unresolved; an additional intermediate file is not an original expert rubric. Wet-lab planning and analysis tools are available, but no biological measurements have been analyzed. Total new requests are 136 of the 300-request cap. [Alternative coverage](reference_recovery/development_binding_followup_v1/alternative_coverage_facts.md), [version-bound review](human_review/versioned_review_v1/README.md), [pending evidence](remaining_dependencies.json).
'''
    write(BASE / 'Methods_Results_en.md', english)
    write(BASE / 'Abstract_en.md', '''# Draft abstract: supplementary development evidence

Fixed-sample tissue-clearing protocol generation requires matching specimen scale and labeling to procedural requirements and imaging goals. ClearEval evaluates parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring (EGES). We added source-bound Step Recall and Step Precision while retaining these components. Across 77 archived answers from 13 models and six tasks, conditional references from five source families yielded 50 provisional complete CCE values. In a three-pair deletion diagnostic, unfiltered reference maximization masked one primary-threshold response by selecting a different route. A frozen prompt intervention improved technical loading of fifteen original texts from seven to fourteen, while a separate schema-decoding development test still failed on a conflicting duplicate key. Earlier repeated judging showed zero within-judge variation but cross-judge differences in 10/32 metric groups. The fixed-model common set remained one task, with six, five and four nondominated models across thresholds; resampling supplied no cross-task uncertainty evidence. These findings distinguish reference coverage, error sensitivity, technical repeatability and scientific validity. Expert correction effects and complete alternative-route applicability remain unconfirmed; wet-lab work remains at the planning stage.
''')
    status = '''# ClearEval r2 当前状态

最新来源评分：ScaleS原版SI已恢复，77份主答案中暂定完整CCE **50/77**（新增4），27份参考NA；每阈值73旧对象完全复用，原c_param/Cor/EGES全部不变。10条件分支/5家族，正式科学确认0。[真实逐答案和命令](expanded_references_v7/EXECUTION.md)。

原15份统一v2技术复评 **14/15成功**，较原7/15恢复7份，无退步；剩余冲突重复键保留失败。独立schema开发5次4成功，预设门槛未过，后续15次未运行。总请求 **136/300，余164**，当前无运行中模型批次。

参考池诊断：主阈值q2自身路线删除ΔSR=−1/7；无筛选改选uDISCO后Δ=0，掩盖删除响应。其余两对不变，旧负结果保留。固定13模型共同集仍只q2，三阈值前沿6/5/4，单题重采样退化；旧成功draw/投影输入未变，已复用。

真实替代路线9对：8技术完整覆盖6题，6数值完整覆盖4题，专家确认0。旧尺度追加查证无可用映射，原逐专家表未保留。共用一专家5+15及160项表未变，真实回传0；来源建设单列。湿实验计划/入口已完成，缺真实数据不阻断计算包。

本轮可运行批次与图表已完成，整体目标仍受真实专家核查及具体来源/适用性证据限制，不能标记科学验证全部完成。[中文结果](RESULTS_zh.md)、[英文Methods/Results](Methods_Results_en.md)、[逐目标状态](completion_audit_current.json)、[数据配置入口](current_run_index.json)、[人审入口](human_review/CURRENT_REVIEW_ENTRY.md)、[已执行命令](commands.md)。下一条离线恢复命令：`python scripts/cce_report.py`；专家回传后使用[版本校验入口](human_review/versioned_review_v1/README.md)按原合同处理，不把空白视为通过。
'''
    write(BASE / 'STATUS.md', status)
    write(ROOT.parent / 'STATUS.md',status.replace('](','](ClearEval-public/artifacts/cce_validation/'))
    deps = read(HIST / 'remaining_dependencies.json')
    deps.update(report_stage=VERSION,
        reference_validation='10 conditional main branches from 5 source families; no expert-confirmed full-task applicability.',
        cohort_coverage={'answer_missing':1,'provisional_CCE_numeric':50,'screened_reference_insufficient':27,'main_revised_steps_not_run':3211},
        holdout_extraction='Original7/15 retained. Separate v2 technical follow-up14/15 with one conflicting duplicate-key failure; no score/version cherry-picking. Schema development4/5, prespecified15 follow-up not run.',
        extraction_effect='5 original development and14 new follow-up successful automatic extractions available; expert corrections/faithful effects pending. Original versions and all failures preserved. Both corrections and reviewed-no-change decisions require a real version receipt bound to the current review manifest.',
        expert_return_version_binding={'manifest':'human_review/versioned_review_v1/manifest.json','preflight':'human_review/versioned_review_v1/preflight.json','real_acknowledgements':0,'original_form_is_immutable_template':True,'missing_auto_pending_ids':['A15']},
        alternative_routes='6 tasks have conditional dual references;9 actual pairs,8 technical pairs across6 tasks,6 complete numerical CCE pairs across4 tasks; zero expert-confirmed reasonable pairs. q1/q2 Eff missing is separate from expert confirmation.',
        historical_human_scale='No authenticated full rubric/mapping recovered. Historical paper states raw per-annotator sheets were not retained; an additional intermediate version does not supply original labels.',
        source_recovery='ScaleS originalSI recovered and conditionally bound to4 development answers; remaining27 main reference gaps retain explicit specimen/version/label boundaries. BoneClear additional legal primary-source attempts did not recover the exact methods PDF.',
        next_independent_work='All currently frozen batches completed. Further source-supported expansions require new applicable evidence; the schema continuation matrix remains deliberately unrun after its prespecified development gate failed. Real expert returns enable local corrected-field analyses.',
        wetlab_is_computational_blocker=False,
        wetlab_scope='Plan, assumption sensitivity, randomization and analysis entry delivered. Real observations required only for biological-effect claims.',
        reference_pool_diagnostic={'pairs':3,'primary_q2_filtered_delta_sr':-1/7,'primary_q2_unfiltered_delta_sr':0,'new_independent_pairs':0,'expert_necessity_confirmation':False})
    save(BASE / 'remaining_dependencies.json', deps)
    audit = {'status':'computational_batches_delivered_scientific_dependencies_pending','overall_goal_complete':False,
        'expert_count':1,'development_review_count':5,'holdout_review_count':15,'actual_expert_returns':0,
        'items':[
            {'goal':'Source-traceable SR/SP and pilot expansion','state':'completed_provisionally','evidence':'expanded_references_v7/EXECUTION.md','counts':'6 tasks,13 models,77 answers,50 numericCCE'},
            {'goal':'Original parameter correctness and EGES preservation','state':'completed_verified','evidence':'expanded_references_v7/independent_numeric_review.json'},
            {'goal':'E1 historical alignment and local review','state':'alignment_audited_expert_review_and_old_scale_pending','evidence':'human_review/legacy_scale_followup_v1/README.md'},
            {'goal':'E2 full-text controlled validation','state':'executed_with_nonresponses_retained','evidence':'controls/paired_route_ablation_v7/interpretation.md'},
            {'goal':'6-8 reasonable complete alternative-route pairs','state':'9_pairs_attempted_8_technical_6_numeric_full_scientific_eligibility_pending','evidence':'reference_recovery/development_binding_followup_v1/alternative_coverage_facts.md'},
            {'goal':'E3 faithful extraction effect','state':'automatic_inputs_and_review_tools_ready_real_corrections_pending','evidence':'human_review/CURRENT_REVIEW_ENTRY.md'},
            {'goal':'Bind expert returns to the actual suggestion version','state':'wrapper_and_offline_preflight_ready_real_receipts_pending','evidence':'human_review/versioned_review_v1/preflight.json'},
            {'goal':'E4 actual repeated judging','state':'completed_bounded_development_matrix','evidence':'judges/stability_remediation_v2/analysis/README.md'},
            {'goal':'Technical follow-up','state':'completed14of15_one_failed_retained_schema_continuation_gate_unmet','evidence':'judges/holdout_remediation_v2/README.md'},
            {'goal':'E5 CCE common-set Pareto sensitivity','state':'computed_provisionally_one_common_task_no_broad_ranking','evidence':'analysis_expanded_references_v7/joint_summary.json'},
            {'goal':'Figures and Chinese/English writing','state':'updated_from_verified_actual_results','evidence':'RESULTS_zh.md'},
            {'goal':'E6 allowed planning scope','state':'plan_and_tools_delivered_no_real_observations','blocks_computational_delivery':False}],
        'missing_results_never_imputed':True,'new_model_requests_this_phase':20,'package_requests':136}
    save(BASE / 'completion_audit_current.json', audit)
    budget = read(HIST / 'budget.json')
    budget.update(attempts_recorded=136,remaining_request_capacity=164,
        model_attempts=dict(Counter(r['model'] for r in ledger)),ledger_sha256=sha(ledger_path))
    save(BASE / 'budget.json',budget)
    human = '''# 一位专家的 20 份共用审阅入口

当前固定 A01–A05 为开发、A06–A20 为留出，共用原 160 行表完成步骤与提取核查。真实专家回传为 0；未填项保持待定。请从[带版本绑定的审阅包](versioned_review_v1/README.md)开始，并用其回执记录实际审阅版本、身份、日期与答案编号。

专家先核开发材料；若据此改变规则，须冻结新配置并将使用过的材料标为开发性结果。当前 15 份机器提取属于技术复评，不作为独立留出准确性验证。

- 开发 5 份采用 [v4_dev_v2 的真实自动提取](rescoring/v4_dev_v2/reviewer/README.md)。
- 留出 15 份统一采用 [holdout_remediation_v2 的匿名附件](../judges/holdout_remediation_v2/sealed/reviewer/README.md)：14 份自动提取成功，A15 技术失败仍有原文可审，自动分数配对保持待定。
- 复制原[共用专家表](reviewer/review_items.csv)作为回传文件，按[原回传合同](EXPERT_RETURN_CONTRACT.md)填写真实判断和原文位置；保留原空模板。版本回执是单独附件，不改变原 160 项，不增加审阅样本。处理回传时用 `--review` 指定填写后的副本。

审阅方式为 ASSISTED：先读原题与原答案，再核对自动建议。附件去除显式模型元数据和分数，原答案正文保留，不能称独立盲评。必须通过版本校验入口处理回传；“无需修正”同样需要对应版本的真实审阅记录。A15 没有自动提取，不能用旧版或其他解码实验填补，也不阻断其他答案处理。

开发的[局部步骤表](local_step_audit/review_rows.csv)包含 10 个候选，只审实际选中条目，未审不计分母，不产完整人工 SR。留出的[15 份来源步骤附件](../holdout_source_steps_v1/reviewer/README.md)只有 A06/q146 有条件性作者分支，其余 14 份参考不足；来源身份与完整任务适用性仍待核。原 judge 批次的参考上下文保持空白，新条件步骤附件单列，不能把它当作原提取的依据。

步骤与提取共用这一位专家的 5＋15；[完整参考建设 v5](reference_construction_v5/README.md)单独记账，主参考为 10 条件分支、5 家族，专家适用性确认 0，未知人时留空。没有真实回传时，忠实字段修正及“已核查无需修正”效果均不计算。

版本入口的[独立软件核验](versioned_review_guard_review_v1/README.md)已完成：错误版本和空回执不能进入重评分，A15 单独待定；隔离测试不是专家意见，也不计作真实纠错效果。

历史版本只用于追溯：[原留出 7 成功/8 失败](../judges/local_extraction_holdout_v1/sealed/reviewer/README.md)、[schema 开发 4 成功/1 失败](../judges/schema_decode_followup_v1/README.md)。schema 未通过预设门槛，后续 15 份未运行。不能跨版本挑选较好结果，也不能把旧版的审阅记录自动转给当前建议。

[当前全部结果](../RESULTS_zh.md)、[逐目标状态](../completion_audit_current.json)。
'''
    write(BASE / 'human_review/CURRENT_REVIEW_ENTRY.md',human)
    write(BASE / 'human_review/README.md', '''# 当前人工核查入口

使用[当前审阅说明](CURRENT_REVIEW_ENTRY.md)和[版本绑定审阅包](versioned_review_v1/README.md)。固定一位专家、5 份开发＋15 份留出，共用原 160 行表；真实回传 0。

当前机器建议为 5 份开发提取与统一 v2 留出复评（14 成功、1 失败）。原留出和独立 schema 解码实验均保留为历史，不混用。步骤附件、字段修正规则、版本回执及原始全文入口都在当前说明中。
''')
    commands = '''# 已实际执行的命令

工作目录 `C:\\ClearEval\\ClearEval-public`。使用 `C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe` 调用以下脚本。所有 run 均已结束；不重复成功输入/配置。

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_holdout_remediation_v2.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_holdout_remediation_v2.py preflight
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_holdout_remediation_v2.py run --allow-local-calls
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_schema_decode_followup_v1.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_schema_decode_followup_v1.py preflight --stage development
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_schema_decode_followup_v1.py run --stage development --allow-local-calls
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_schema_decode_followup_v1.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_plot_technical_followup_v1.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_scales_source_v1.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_references_v7.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_version_guard_v1.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_version_guard_v1.py preflight
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_version_guard_v1.py self-check
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_version_guard_v1.py rescore
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' artifacts/cce_validation/human_review/versioned_review_guard_review_v1/run_synthetic_review.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' artifacts/cce_validation/figures_development_label_coverage_v1/build_figure.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' artifacts/cce_validation/figures_development_label_coverage_v1/finalize_audit.py
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_report.py
```

其中源核脚本只在新评分冻结前执行一次，既有结果请用相应verify命令恢复。schema的 `preflight --stage holdout_followup` 也已实际执行，按预设门槛以exit1拒绝，0请求；不能当作未实现或伪造的成功命令。

审阅版本包装器的 `prepare` 已冻结20份，不应重复准备；`preflight` 与隔离软件检查均完成。这里的 `rescore` 仅使用当前真实空模板，实际返回 `pending_no_real_review`、0 faithful 输出、0新请求，不是已经做过专家纠错分析。真实回传命令及所需独立文件见[版本入口](human_review/versioned_review_v1/README.md)；不要覆盖原空模板。

完整已执行参数和回执分别见 [15份技术复评](judges/holdout_remediation_v2/README.md)、[schema五份实际命令](judges/schema_decode_followup_v1/actual_commands.json)、[v7来源评分与独立核验](expanded_references_v7/EXECUTION.md)、[参考池增量诊断](controls/paired_route_ablation_v7/execution_commands.json)、[图表脚本](figures_route_ablation_v7/README.md)。更早命令与116次状态按原字节保存在[历史快照](historical_reports/before_holdout_remediation_at_116/commands.md)。
'''
    write(BASE / 'commands.md',commands)
    inputs = [BASE / f'expanded_references_v7_t{t}_per_answer.json' for t in ('060','070','080')]
    inputs += [BASE / p for p in ['expanded_references_v7/plan.json','expanded_references_v7/run.json','expanded_references_v7/references.json',
        'expanded_references_v7/verification.json','expanded_references_v7/independent_numeric_review.json','expanded_references_v7/source_scope_review.json',
        'expanded_references_v7/review_analysis_v7.json','analysis_expanded_references_v7/analysis_run.json','analysis_expanded_references_v7/joint_summary.json',
        'analysis_expanded_references_v7/common_cohort_threshold_sensitivity.json','figures_expanded_references_v7/figure_visual_qa.json',
        'judges/holdout_remediation_v2/plan.json','judges/holdout_remediation_v2/completion_summary.json','judges/holdout_remediation_v2/attachment_verification.json',
        'judges/holdout_remediation_v2/technical_comparison.json','judges/holdout_remediation_v2/duplicate_value_audit.json',
        'judges/schema_decode_followup_v1/plan.json','judges/schema_decode_followup_v1/completion_summary.json','judges/schema_decode_followup_v1/analysis_verification.json',
        'judges/schema_decode_followup_v1/independent_review.json','figures_technical_followup_v1/visual_qa.json',
        'controls/paired_route_ablation_v7/summary.json','controls/paired_route_ablation_v7/saved_result_review.json','figures_route_ablation_v7/visual_qa.json',
        'reference_recovery/development_binding_followup_v1/alternative_coverage_facts.json',
        'human_review/reference_construction_v5/summary.json','human_review/reference_construction_v5/source_index.json',
        'human_review/legacy_scale_followup_v1/legacy_scale_followup.json','reference_recovery/boneclear_primary_followup_v2/result.json']]
    inputs += [ledger_path]
    inputs += [REVIEW / p for p in ['manifest.json','preflight.json','receipt_template.json','received_receipts.json','software_fixtures/guard_checks.json']]
    inputs += [BASE / 'human_review/versioned_review_guard_review_v1' / p for p in ['independent_review.json','synthetic_review.json']]
    inputs += [BASE / 'figures_expanded_tasks_v4' / f'dataset_category_coverage.{ext}' for ext in ['png','svg','pdf','csv']]
    inputs += [LABELS / p for p in ['question_label_evidence.json','figure_qa.json','delivery_gap_audit.json','development_label_coverage.csv']]
    inputs += [LABELS / f'development_label_coverage.{ext}' for ext in ['png','svg','pdf']]
    assert all(p.exists() for p in inputs)
    index = read(HIST / 'current_run_index.json')
    bindings = index['input_sha256']
    for p in inputs: bindings[str(p.relative_to(BASE)).replace('\\','/')] = sha(p)
    # All unchanged source bindings are still verified; live accounting is now136.
    for name, expected in bindings.items(): assert sha(BASE / name) == expected, name
    index.update(version=VERSION,report_stage=VERSION,main_scoring_stage='expanded_references_v7',
        primary='expanded_references_v7_t070_per_answer.json',thresholds=[f'expanded_references_v7_t{t}_per_answer.json' for t in ('060','070','080')],
        reference='expanded_references_v7/references.json',plan='expanded_references_v7/plan.json',composition='expanded_references_v7/run.json',
        score_verification='expanded_references_v7/independent_numeric_review.json',analysis='analysis_expanded_references_v7/joint_summary.json',
        reference_construction='human_review/reference_construction_v5/source_index.json',figure_qa='figures_expanded_references_v7/figure_visual_qa.json',
        holdout_technical_followup='judges/holdout_remediation_v2/completion_summary.json',schema_development='judges/schema_decode_followup_v1/completion_summary.json',
        reference_pool_diagnostic='controls/paired_route_ablation_v7/summary.json',request_attempts=136,new_model_requests=20,main_scoring_new_model_requests=0,
        current_review_package='human_review/versioned_review_v1/manifest.json',review_version_preflight='human_review/versioned_review_v1/preflight.json',
        review_version_independent_check='human_review/versioned_review_guard_review_v1/independent_review.json',
        development_label_coverage='figures_development_label_coverage_v1/README.md',delivery_gap_audit='figures_development_label_coverage_v1/delivery_gap_audit.json',
        previous_report_index='historical_reports/before_holdout_remediation_at_116/current_run_index.json',
        actual_counts={'actual_answers':77,'step_numeric':50,'candidate_cce_numeric':50,'formal_eligible':0,'question_ids':[1,2,21,22,23,248],
            'reference_branches':10,'source_families_with_numeric_rows':5,'fixed13_provisional_common_question_ids':[2],'fixed13_formal_common_question_ids':[]},
        input_sha256=bindings)
    save(BASE / 'current_run_index.json',index)
    config = read(HIST / 'resolved_config_current.yaml')
    config.update(version=VERSION,previous_configuration_snapshot='historical_reports/before_holdout_remediation_at_116/resolved_config_current.yaml',
        composition_configuration=read(BASE / 'expanded_references_v7_t070_resolved_config.json'),
        row_configuration_policy='73 exact old objects per threshold retained;4 newly bound ScaleS rows under frozen v7 reference configuration.',
        reference_extension_v7={'plan':index['plan'],'reference':index['reference'],'archived_components_preserved':True},
        holdout_technical_followup={'plan':'judges/holdout_remediation_v2/plan.json','original_outputs_preserved':True,'scientific_accuracy_claim':False},
        schema_development={'plan':'judges/schema_decode_followup_v1/plan.json','continuation_gate_passed':False,'followup_requests':0},
        reference_pool_diagnostic={'plan':'controls/paired_route_ablation_v7/plan.json','primary_CCE_modified':False},
        expert_return_version_guard={'manifest':'human_review/versioned_review_v1/manifest.json','script':'scripts/cce_review_version_guard_v1.py','original_bridge_unchanged':True,'current_auto_inputs':19,'failed_auto_ids':['A15'],'real_receipts':0},
        current_execution={'primary':index['primary'],'reference':index['reference'],'analysis':index['analysis'],'package_requests':136})
    save(BASE / 'resolved_config_current.yaml',config)
    save(BASE / 'current_activity.json',{'status':'completed_current_runnable_batches_external_scientific_dependencies_pending',
        'stage':VERSION,'requests':136,'running_model_batches':0,'overall_goal_complete':False,
        'next_dependency':'Real expert returns or newly applicable source/rubric evidence; wet-lab data not a computational blocker.'})
    docs = [BASE / p for p in ['RESULTS_zh.md','Methods_Results_en.md','Abstract_en.md','STATUS.md','commands.md','human_review/CURRENT_REVIEW_ENTRY.md','human_review/README.md']]
    links = []
    for doc in docs:
        for rel in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if '://' in rel or rel.startswith('#'): continue
            assert (doc.parent / rel.split('#')[0]).resolve().exists(), (doc.name,rel)
            links.append([str(doc.relative_to(BASE)),rel])
    outputs = docs + [BASE / p for p in ['current_run_index.json','resolved_config_current.yaml','remaining_dependencies.json','completion_audit_current.json','budget.json','current_activity.json']]
    verification = {'status':'pass','actual_command':[sys.executable,'scripts/cce_report.py'],
        'generator_sha256':sha(__file__),'dispatcher_sha256':sha(ROOT / 'scripts/cce_report.py'),
        'package_requests':136,'numeric_CCE':50,'fixed13_common_n':1,'new_report_model_requests':0,
        'original_core_and_expert_form_unchanged':True,'snapshot_116_preserved':True,
        'actual_local_links_checked':len(links),'input_sha256':bindings,
        'output_sha256':{str(p.relative_to(BASE)).replace('\\','/'):sha(p) for p in outputs}}
    save(BASE / 'report_generation.json',verification)
    save(BASE / 'report_verification_references_v7.json',verification)
    print(json.dumps({k:verification[k] for k in ['status','package_requests','numeric_CCE','fixed13_common_n','actual_local_links_checked']}))


if __name__=='__main__': main()
