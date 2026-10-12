"""Render current r2 reports after the isolated iDISCO+ source extension.

This writer never invokes a scorer, evaluator, network request, or old report
generator. Inputs are actual artifacts; preceding reports are snapshotted once.
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/cce_validation"
HIST = OUT / "historical_reports/supplement_v2_before_idisco"
PREFIX = "supplement_v2_idisco"
ANALYSIS = "analysis_supplement_v3"
FIGURES = "figures_supplement_v3"
SOURCE = "reference_recovery/idisco_plus_2016"
REFERENCE = SOURCE + "/references_expanded_v3.json"
REPORTS = ["STATUS.md", "RESULTS_zh.md", "Methods_Results_en.md", "Abstract_en.md", "commands.md"]
METADATA = ["current_run_index.json", "resolved_config_current.yaml", "remaining_dependencies.json", "budget.json", "report_generation.json", "reference_recovery/reference_construction_current.json"]
INPUTS = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name, required=True, default=None):
    p = OUT / name
    if not p.exists():
        if required:
            raise FileNotFoundError("Required completed input is absent: " + str(p))
        return default
    INPUTS[str(name).replace("\\", "/")] = sha(p)
    return json.loads(p.read_text(encoding="utf-8-sig"))


def textread(name):
    p = OUT / name
    INPUTS[str(name).replace("\\", "/")] = sha(p)
    return p.read_text(encoding="utf-8-sig")


def save(name, data):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data.strip()+"\n" if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def snapshot():
    manifest = HIST / "snapshot_manifest.json"
    if manifest.exists():
        d = json.loads(manifest.read_text(encoding="utf-8"))
        for name, h in d["files"].items():
            if sha(HIST/name) != h:
                raise ValueError("Historical snapshot changed: "+name)
        return d
    files = {}
    for name in REPORTS + METADATA:
        p, q = OUT/name, HIST/name
        raw = p.read_bytes()
        q.parent.mkdir(parents=True,exist_ok=True)
        if q.exists() and q.read_bytes() != raw:
            raise ValueError("Unregistered historical bytes differ: "+name)
        if not q.exists():
            q.write_bytes(raw)
        assert sha(p)==sha(q)
        files[name]=sha(q)
    d={"scope":"supplement_v2_before_idisco_current_reports_and_metadata", "files":files,
       "byte_identical_at_capture":True,"created_utc":datetime.now(timezone.utc).isoformat(),
       "command":subprocess.list2cmdline([sys.executable,*sys.argv]),"old_result_batches_modified":False}
    manifest.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return d


def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def fmt(v):
    return f"{v:.6f}" if finite(v) else "NA"


def table(headers, rows):
    return "\n".join(["| "+" | ".join(headers)+" |", "| "+" | ".join(["---"]*len(headers))+" |"]+["| "+" | ".join(map(str,r))+" |" for r in rows])


def executed_commands():
    names=[f"{PREFIX}_t0{t}_run.json" for t in (60,70,80)]+[
        ANALYSIS+"/analysis_run.json", "common_set_gaps_v3/summary.json", "score_batch_verification_idisco.json",
        SOURCE+"/expansion_run.json", SOURCE+"/execution_run.json", SOURCE+"/publisher_attachments/retrieval_manifest.json",
        ANALYSIS+"/reference_expansion_summary.json", FIGURES+"/idisco_plot_run.json",
        "controls/supplement_v3_route_filter_diagnostic_summary.json",
        ANALYSIS+"/figure_visual_qa.json", "human_review/review_impact_addendum/summary.json",
        "controls/whole_brain_task_prescreen/audit.json", "inventory/partial_score_q29/audit.json"]
    records=[]
    def collect(d, name):
        if not isinstance(d,dict): return
        for key in ("command","actual_command"):
            command=d.get(key)
            if isinstance(command,str):
                records.append({"source":name,"command":command,"status":d.get("status","completed_artifact_present")})
            elif isinstance(command,dict) and command.get("argv"):
                argv=command["argv"]
                if command.get("executable") and argv[0]!=command["executable"]: argv=[command["executable"],*argv]
                records.append({"source":name,"command":subprocess.list2cmdline(argv),"status":d.get("status","completed_artifact_present")})
    for name in names:
        d=read(name,False)
        if d is not None: collect(d,name)
    seen=set(); result=[]
    for r in records:
        key=r["command"]
        if key not in seen:
            seen.add(key);result.append(r)
    diag_command=SOURCE+'/review/q248_route_only_diagnostic/actual_command.ps1'
    if (OUT/diag_command).exists() and (OUT/SOURCE/'review/q248_route_only_diagnostic/summary.json').exists():
        result.append({'source':diag_command,'command':textread(diag_command).strip(),'status':'completed_offline_diagnostic_summary_present'})
    return result


def build():
    INPUTS.clear()
    batches={t:read(f"{PREFIX}_t0{t}_per_answer.json") for t in (60,70,80)}
    runs={t:read(f"{PREFIX}_t0{t}_run.json") for t in (60,70,80)}
    pilot=batches[70]
    if any(len(rows)!=65 for rows in batches.values()): raise ValueError("Expected three complete 65-answer offline batches")
    refs_obj=read(REFERENCE); refs=refs_obj["references"] if isinstance(refs_obj,dict) else refs_obj
    config=read(f"{PREFIX}_t070_resolved_config.json")
    old=read("supplement_v2_t070_per_answer.json"); oldmap={r["answer_id"]:r for r in old}
    newmap={r["answer_id"]:r for r in pilot}
    if set(oldmap)!=set(newmap): raise ValueError("Reference comparison has different answer IDs")
    added=[r for r in pilot if finite(r.get("sr")) and not finite(oldmap[r["answer_id"]].get("sr"))]
    old_numeric=[r for r in pilot if finite(oldmap[r["answer_id"]].get("sr"))]
    changes={m:sum((r.get(m)!=oldmap[r["answer_id"]].get(m)) if not(finite(r.get(m)) and finite(oldmap[r["answer_id"]].get(m))) else abs(r[m]-oldmap[r["answer_id"]][m])>1e-12 for r in old_numeric) for m in ("sr","sp","Com","Cor","Eff","IA","HV","c_param")}
    # Existing raw quality components must remain unchanged in this source-only extension.
    immutable=["c_param","Cor","Eff","co_order","co_method","co_param","co_chem","s_method","s_label","s_trans","s_time"]
    original_components_unchanged=all(r.get(k)==oldmap[r['answer_id']].get(k) for r in pilot for k in immutable)
    assert original_components_unchanged
    numeric=sum(finite(r.get("sr")) for r in pilot)
    numeric_cce=sum(all(finite(r.get(m)) for m in ("Com","Cor","Eff","IA","HV")) for r in pilot)
    formal=sum(bool(r.get("formal_eligible")) for r in pilot)
    fixed=read(ANALYSIS+"/revised_full_fixed_cohort.json")
    subset=read(ANALYSIS+"/pilot_participating_subset.json")
    gaps=read("common_set_gaps_v3/summary.json")
    thresholds=read(ANALYSIS+"/threshold_sensitivity.json")
    coverage=read(ANALYSIS+"/dataset_coverage_metadata.json")
    verification=read("score_batch_verification_idisco.json")
    if verification.get("status") in ("pending","running","failed") or verification.get("all_passed") is False:
        raise ValueError("New score batch verification is not complete")
    source=read(SOURCE+"/source_manifest.json")
    construction=read(SOURCE+"/reference_construction_v1.json")
    source_qa=read(SOURCE+"/validation.json")
    source_review=read(SOURCE+"/review/source_applicability_audit.json")
    if source_review.get('candidate_review',{}).get('verdict')!='ready_for_conditional_development_scoring_not_scientific_validation':
        raise ValueError('Final isolated candidate source review is not ready')
    recovered=read("reference_recovery/recovered_supplements/official_object_recovery_manifest.json")
    original_version_effect=read("reference_recovery/supplement_bound/reference_version_effects.json")
    route_v2=read("controls/supplement_v2_route_filter_diagnostic_summary.json")["overall"]
    route_v3=read("controls/supplement_v3_route_filter_diagnostic_summary.json")["overall"]
    effects=read(ANALYSIS+"/reference_expansion_summary.json")
    new_language=read(ANALYSIS+"/new_idisco_answers.json")
    figure_qa=read(ANALYSIS+"/figure_visual_qa.json")
    e2=read("judges/local_controls_supplement_v2/development_summary.json")
    controls=read("judges/local_controls_supplement_v2/control_summary.json")
    cmap={r["condition"]:r for r in controls}
    e4=read("judges/local_stability_supplement_v2/development_summary.json")
    alt=read("judges/local_alternative_development/development_summary.json")
    e3=read("human_review/rescoring/v4_dev_v2/summary.json")
    identity=read("human_review/rescoring/v4_dev_v2/identity_verification.json")
    read("human_review/rescoring/v4_dev_v2/actual_na_and_integrity_audit.json")
    lineage=read("human_review/lineage/summary.json")
    human=read("human_review/review_status.json")
    local=read("human_review/local_step_audit/summary.json")
    impact=read("human_review/review_impact_addendum/summary.json")
    prescreen=read("controls/whole_brain_task_prescreen/audit.json")
    q29=read("inventory/partial_score_q29/audit.json")
    local_verify=read("judges/local_v2_verification.json")
    wet=read("wetlab/wetlab_status.json")
    # q248 is a separately generated diagnostic and never updates the main table.
    q248_path=OUT/SOURCE/'review/q248_route_only_diagnostic/summary.json'
    q248=read(q248_path.relative_to(OUT).as_posix())
    ledger=[json.loads(x) for x in textread("judges/request_ledger.jsonl").splitlines() if x.strip()]
    calls=len(ledger); budget_limit=config["budget"]["default_max_additional_api_requests"]
    returned=sum(r["reviewed_items"] for r in human["splits"].values())
    reviewed_answers=sum(r["reviewed_answers_any_item"] for r in human["splits"].values())
    means=subset["means"]; flash=means["gemini-3-flash"]; pro=means["gemini-3-pro"]
    count=gaps["state_counts"]
    routes=sorted({r["route_id"] for r in refs}); families=sorted({r["family_id"] for r in refs})
    recovered_n=sum(x.get("status")=="recovered_verified_original_bytes" for x in recovered)+1
    changed_table=table(["本轮新增候选答案","SR","SP","Com","Cor","Eff"],[[r["answer_id"],*[fmt(r.get(m)) for m in ("sr","sp","Com","Cor","Eff")]] for r in added])
    q248_table=table(["q248 独立路线诊断","route-only SR","route-only SP"],[[r['answer_id'],fmt(r['route_only_sr']),fmt(r['route_only_sp'])] for r in q248['results']])
    cjk=[r for r in new_language if r['threshold']==0.7 and r['generated_cjk_steps']>0]
    language_note='；'.join(f"{r['model']} 解析 {r['generated_n']} 步，其中中文 {r['generated_cjk_steps']} 步，最大相似度 {r['maximum_pair_similarity']:.7f}" for r in cjk)
    example=newmap['openai_qwen3-14b__q2']
    mean_table=table(["预先指定模型","Com","Cor","Eff","IA","HV"],[[m,*[fmt(v[k]) for k in ("Com","Cor","Eff","IA","HV")]] for m,v in means.items()])
    control_table=table(["条件（冻结 v2）","完整对","ΔSR","ΔCom","ΔCor","ΔEff","ΔIA","ΔHV"],[[r["condition"],r["complete_pairs"],*[fmt(r.get("mean_delta_"+m)) for m in ("sr","Com","Cor","Eff","IA","HV")]] for r in controls])
    old_step_change_note=("SR 和 SP 均未变" if changes['sr']==0 and changes['sp']==0 else f"SR 有 {changes['sr']} 份变化，SP 有 {changes['sp']} 份变化")
    first=(f"本轮新恢复 iDISCO+ 2016 官方出版方附件，建立 q2 的 9 步条件性开发参考，并以冻结原答案完成 0.6/0.7/0.8 三阈值各 {len(pilot)} 份离线重算。"
           f"主阈值新增 {len(added)} 份 SR/SP 数值，当前 {numeric}/{len(pilot)} 份步骤分数和 {numeric_cce} 份候选 CCE 有数值，正式合格 {formal} 份。"
           f"旧 {len(old_numeric)} 份有分答案的 {old_step_change_note}；原参数完整性、Correctness 和 EGES 保持不变。"
           "来源补齐改变了可评价覆盖，没有证明模型改进；本轮没有新模型请求。")
    common=(f"固定 {fixed['cohort_size']} 模型×{gaps['question_count']} 题共 {gaps['expected_cells']:,} 格：缺答 {count['answer_missing']}、新步骤评分未运行 {count['revised_steps_not_run']:,}、筛选后参考不足 {count['screened_reference_insufficient']}、暂定 CCE 数值 {count['provisional_CCE_numeric']}。"
            f"数值 Q*={len(gaps['numeric_common_question_ids'])}，正式 Q*={len(gaps['formal_common_question_ids'])}。未运行不等于参考不存在，不能将局部可评分行变成全队列排名。")
    source_note=(f"当前 {len(refs)} 个来源参考分支来自 {len(routes)} 个路线、{len(families)} 个来源家族；累计恢复 {recovered_n} 份官方 PDF。"
                 "原 FDISCO/PEGASOS 四分支字节保留，3 mm 专属时程/重复次数仍未知。新增 iDISCO+ 论文 supplement 的完整已固定后作者流程为 28 操作，评分只取题干要求的 9 个透明/RI/保存操作；上游免疫为条件前提，不假定题干已完成，也不扩大评分分母。"
                 "同包 April 2016 Bench 与论文补充方法有参数差异，分别记录而不拼接。新 PDF 已核 DOI、标题、PII、SHA 和 7 页图像；它与另一个 NIHMS 附件不声称字节等同。所有来源均为 source_extracted，专家确认仍为 0。")
    q248_note=("q248 要求保留原生 tdTomato 荧光，2016 免疫信号/组织自发荧光证据不能替代这一要求。新增 iDISCO+ 主参考分支不绑定 q248，该路线主 SR/Com/CCE 的对应缺失保持不变；原 FDISCO/PEGASOS 的 q248 绑定不变。"
               + (f"独立路线步骤诊断已经生成，结果见 [{q248_path.name}]({q248_path.relative_to(OUT).as_posix()})；它不计科学覆盖或合理替代路线。" if q248 else "独立路线步骤诊断尚待完成；不提前计数。"))
    deletion=cmap["necessary_step_deletion"]; param=cmap["necessary_parameter_deletion"]; order=cmap["evidence_supported_order_conflict"]; equiv=cmap["deterministic_equivalent_representation"]; merge=cmap["adjacent_entry_merge"]
    e2_note=(f"E2 保留 supplement v2 冻结批：{e2['technical_successful_cases']} 份实际全文评价、{e2['complete_candidate_cce_pairs']} 对完整候选比较，3 份源答案、2 个任务家族、1 个来源家族。"
             "基线和编辑后全文使用同一冻结配置重新解析、提取、评分。输入显式仅含 FDISCO v2，追加 iDISCO+ 不改变它们，因此复用而不机械新增请求；旧 v1 不叠加为独立案例。"
             f"RI/保存联合模块删除仅 {deletion['negative_sr']}/{deletion['n_sr']} 对降低 SR（平均 {fmt(deletion['mean_delta_sr'])}），明确时间删除 {param['negative_c_param']}/{param['n_c_param']} 对降低 c_param，顺序冲突 {order['negative_co_order']}/{order['n_co_order']} 对降低 co_order、{order['negative_Cor']}/{order['n_Cor']} 对降低 Cor。"
             f"顺序条件却有 {order['negative_c_param']} 对 c_param 下降；相邻条目合并 SR 为下降/不变/上升各 {merge['negative_sr']}/{merge['zero_sr']}/{merge['positive_sr']} 对，反映粒度与提取敏感性。")
    e4_note=(f"E4 保留 supplement v2 的 {e4['actual_observations']} 个真实观测（两答案×两本地评价家族×三次），{e4['successful_exact_reused_observations']} 条精确复用＋{e4['new_requests_this_batch']} 次当时新增调用。"
             f"16 项指标、64 个重复分项组中有波动 {e4['component_groups_with_variation']} 组，32 个评价器×指标排名记录中严格翻转 {e4['strict_rank_flip_metrics']} 项。"
             f"Llama {e4['rubric_example_copies']}/6 次复制量表示例且路线错误；Qwen 6/6 无该标记。零波动不是忠实提取或可靠性证明。")
    e3_note=(f"E3 保留 v4_dev_v2 的 {e3['actual_auto_records']} 份真实开发提取与 {e3['guarded_identity_replay_pass']} 份原函数 identity 复核，{e3['pending_auto_answers']} 份留出仍待自动提取。"
             f"路线/marker/总时间有实际字段的判项为 {e3['direct_route_marker_total_time_item_rows']}，组织/尺度 {e3['tissue_scale_partial_schema_rows']} 项仅有原文及 sample_ri，旧 schema 没有组织身份/尺寸字段，不能称 20 项完整抽取。"
             "protocol_time_hours 均为 null；A01 真实 s_label=NA 使 Eff/IA/HV 为 NA，其他已知分项保留。原需求、科学证据选择及代码/输入 hash 固定，纠错后原 EGES 重算入口可用；identity 软件复核不是专家纠错效果。")
    human_note=(f"新增人工计划仍为一位专家、5 开发＋15 留出共用，原 20 答案/160 判项当前已回传 {returned} 项。历史 {lineage['original_answers_hash_bound']} 份答案已绑定 {lineage['versions']} 个 Git 历史版本，0..5 旧约定已找到，但完整人评量表、专家身份及 signed scale 映射仍待确认。"
                f"10 个定向开发步骤判项 reviewed={local['reviewed_rows']}；E1/E3 开发及留出的完整预定核查分母均为 0，误差比例和纠错影响为 NA，不把空分母或 bookkeeping 的 0 当零错误率。")
    alt_note=(f"两来源替代开发批保留 {alt['technical_successful_cases']}/{alt.get('planned_cases',9)} 份技术成功和 {alt['complete_candidate_cce_pairs']}/{alt.get('candidate_pairs',6)} 对完整描述比较，正式合格仍为 {alt['formal_completed_pairs']}。"
              "partial co_chemical 未自动映射为 co_chem。6 候选对仅3个题号/1任务家族、跨生成模型且共享基线，不满足6–8个不同任务的合格替代路线要求。"
              f"新增元数据预筛覆盖 {prescreen['questions_screened_by_existing_tier']} 个历史T04任务，q1/q13/q14/q15仅为后续来源绑定线索；未读取留出答案或按分数挑选，未计新任务分数。")
    methods=("ClearEval's original parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring (EGES) were retained. "
             "BioProBench Step Recall/Precision used all-mpnet-base-v2 and cosine threshold 0.7, with 0.6/0.8 sensitivity checks. "
             "References were filtered by task scope and declared route; maximum SR, then SP and frozen order resolved multiple candidates. "
             "Com=0.4 SR+0.6 c_param/3; SP remained separate. IA=min(Com,Cor,Eff) and zero-reference HV=Com×Cor×Eff were computed per answer before averaging. "
             "Missing components propagated to dependent metrics without imputing unknowns as zero. The 13-generator cohort, historical task demand, original answers and quality components stayed fixed. "
             "The two-Gemini five-question subset was prespecified and was not expanded by selecting newly favorable scores. Synchronized source-family bootstrap used 2,000 draws; dominance tolerance was 1e-12.")
    figs=[]
    for stem in ("development_cce_projections","threshold_sensitivity","idisco_reference_expansion","coverage","dataset_category_coverage"):
        p=f"{FIGURES}/{stem}.png"
        if (OUT/p).exists(): figs.append(f"[{stem}]({p})")
    figs += ["[E2 冻结 v2 图](figures_supplement_v2/controls_supplement_v2.png)","[E4 冻结 v2 图](figures_supplement_v2/stability_supplement_v2.png)","[替代开发 v2 图](figures_supplement_v2/alternative_development_pairs.png)"]
    commands=executed_commands()
    dependencies={
        "expert_review":"One expert, 5 development + 15 holdout, shared across step and extraction audits; no returned expert labels. Zero completed-review denominators imply NA rates/effects.",
        "reference_validation":"Three source families, five source-extracted task branches; expert completeness/applicability pending. iDISCO+ q2 is conditional on immunolabeling; q248 native tdTomato remains unsupported. Exact 3 mm schedules remain unknown.",
        "source_conflicts":"2016 article supplement and April Bench differ; selected configuration preserved, no invented consensus.",
        "alternative_routes":"Only five complete descriptive candidate pairs from three question IDs in one task family. New metadata-only task leads require separate source binding and frozen case matrix.",
        "cohort_coverage":count,"common_numeric_questions":gaps['numeric_common_question_ids'],"common_formal_questions":gaps['formal_common_question_ids'],
        "extraction_effect":"Five actual identity replays are software verification; expert-corrected selection/score effects and holdout audits remain pending.",
        "historical_human_scale":"Archived 0..5 convention does not establish the original full rubric, expert provenance or signed-scale mapping.",
        "historical_q29":"Two intact raw score blocks located but raw/stored co_chem conflict and incomplete identity prevent silent repair.",
        "evaluator_validity":"Frozen local diagnostic judges are not the unavailable historical evaluator; Llama rubric-copy failures invalidate a reliability claim.",
        "wetlab":wet['remaining_minimum_inputs'],"source_retrieval":"Relevant FDISCO/PEGASOS and iDISCO+ supplemental sources now read; no longer a blanket attachment-access blocker."}
    budget={"limit":budget_limit,"attempts_recorded":calls,"remaining_request_capacity":budget_limit-calls,"model_attempts":dict(collections.Counter(r['model'] for r in ledger)),"retries_counted":True,"reused_observations_count_as_new_requests":False,"expert_budget":{"experts":1,"development":5,"holdout":15,"returned_answers_any_item":reviewed_answers,"returned_items":returned},"reference_construction_separate":True,"ledger_sha256":sha(OUT/'judges/request_ledger.jsonl')}
    outputs={}
    outputs["RESULTS_zh.md"]=f"""# ClearEval r2 当前补充结果：supplement v3（iDISCO+ 来源扩展）

{first}

{changed_table}

表中 0 是实际评分值，不是未知补零。{language_note}；两份在三个阈值均为0，不能解释为没有操作。新增7份的参考及生成步骤截断均为0。English all-mpnet-base-v2 对中文步骤的语义匹配仍未经独立跨语言验证。[逐答案]({PREFIX}_t070_per_answer.csv)、[语言诊断]({ANALYSIS}/new_idisco_answers.csv)、[新三批核验](score_batch_verification_idisco.json)。

联合结果示例：Qwen3-14B 的 q2 具有 SR={fmt(example['sr'])}、SP={fmt(example['sp'])}、Com={fmt(example['Com'])}、Cor={fmt(example['Cor'])}、Eff={fmt(example['Eff'])}，逐答案 IA={fmt(example['IA'])}、HV={fmt(example['HV'])}。较高的 Eff 不消除 Cor 短板。这是继承存档分项的开发性描述，不是新评价器校准或科学真值。

{source_note} [来源与边界]({SOURCE}/README.md)、[版本差异]({SOURCE}/source_version_differences.md)、[独立代理审阅]({SOURCE}/review/source_applicability_audit.md)。{q248_note}

{q248_table}

上表4份只作同声明路线的数值诊断，不计主科学覆盖、CCE或新模型请求；其中0匹配的答案也解析到17个操作。

{common} [逐格状态](common_set_gaps_v3/cell_status.csv)、[全量历史/新覆盖分析]({ANALYSIS}/joint_summary.json)。q29 已找到两个完整 raw 数值块，但 co_chem 与后存层 0/1 冲突、身份不完整；未选择有利层、未修原分或补 Cor/Eff。[只读核查](inventory/partial_score_q29/audit.json)。

{mean_table}

预先指定两 Gemini 子集仍有 {subset['common_n']} 题；该子集非支配模型为 {', '.join(subset['empirical_nondominated'])}，不构成固定全队列排名。2,000 次同步来源家族 bootstrap 仅含 {subset['bootstrap']['source_family_count']} 个家族，状态 {subset['bootstrap']['status']}；零宽区间和单一频率不能支撑推广。阈值比较按每指标三阈值共同有限值交集，SR 的共同分母为 {thresholds['common_finite_pairs_by_metric']['sr']}。[共同题集]({ANALYSIS}/pilot_participating_subset.json)、[阈值]({ANALYSIS}/threshold_sensitivity.json)。

{e2_note}

{control_table}

均值表显示六位小数，0.000000 不等于严格为零。等价编号的平均 ΔEff={equiv['mean_delta_Eff']:.9g}，因此不称完整 CCE 严格不变。[逐对](judges/local_controls_supplement_v2/paired_results.csv)。

{alt_note} [原替代开发结果](judges/local_alternative_development/development_summary.json)、[后续任务预筛](controls/whole_brain_task_prescreen/audit.json)。

{e4_note} [分项与完整观测](judges/local_stability_supplement_v2/development_summary.json)。E2/E3/E4 明确 FDISCO-only、替代批明确 FDISCO/PEGASOS 的冻结输入与新路线集合分离；没有把旧结果升级为新的模型调用或独立案例。[实际输入复用审计](completion_audit.json)。

{human_note} {e3_note} [E1/E3 分母及影响](human_review/review_impact_addendum/summary.json)、[实际提取与 identity](human_review/rescoring/v4_dev_v2/summary.json)、[人工版本谱系](human_review/lineage/summary.json)。

本轮三来源无筛选 max-SR 诊断中，{route_v3['main_missing_with_positive_unfiltered_sr_n']}/{route_v3['main_sr_missing_n']} 个参考不足答案得到正 SR，另 {route_v3['main_missing_with_zero_unfiltered_sr_n']} 个为0；原 {route_v3['paired_main_numeric_n']} 个有分答案中 SR 改变 {route_v3['paired_sr_changed_n']} 份，SP 改变 {route_v3['paired_sp_changed_n']} 份。主 NA 全部保留，不把放宽筛选的数值当新增适用覆盖。[当前 v3 诊断](controls/supplement_v3_route_filter_diagnostic_summary.json)。历史两来源 v2 的对应数字为 {route_v2['main_missing_with_positive_unfiltered_sr_n']}/{route_v2['main_sr_missing_n']}，不与本轮混算。此前 v1→v2 共同 {original_version_effect['compared_answers']} 答案中 SR 改变 {original_version_effect['metrics']['sr']['changed_n']} 份、SP 改变 {original_version_effect['metrics']['sp']['changed_n']} 份；本轮 v2→v3 的旧有分行保持如首段所列。

原数据覆盖图保留 {coverage['mcq_final']['rows']:,} 道 MCQ 和 {coverage['qar_historical']['question_rows']} 道开放题的真实 category/knowledge_point/specific 与组织尺度字段，不虚构新分类。[覆盖 CSV]({ANALYSIS}/dataset_coverage.csv)。湿实验真实测量 {wet['real_measurement_rows']} 行、假设功效情景 {wet['planning_scenarios']} 个；主要终点/效应/方差/最终样本量仍待定，不能宣称 CCE 预测实验效果。[计划](wetlab/WETLAB_PLAN.md)。

图表：{'、'.join(figs)}。本轮检查 {figure_qa['render_sets']} 套，{figure_qa['directly_viewed_renders']} 张新增/变化图实际目视，余8张PNG与先前已核图字节相同。E2/E4/替代图保留冻结 v2 的准确版本身份，不把复制到新目录的旧图当新试验。[图表QA]({ANALYSIS}/figure_visual_qa.json)。

全包实际请求 {calls}/{budget_limit}；本轮来源、离线评分和报告新增请求 0。独立 v2 核验覆盖 {local_verify.get('verified_observation_records','NA')} 个观测与 {local_verify.get('unique_real_requests_verified','NA')} 个不同真实请求＋{local_verify.get('exact_reused_records','NA')} 条复用；新195评分另行核验。专家回传和湿实验效果仍待定。[实际命令](commands.md)、[当前索引](current_run_index.json)、[剩余依赖](remaining_dependencies.json)、[v2 报告快照](historical_reports/supplement_v2_before_idisco/snapshot_manifest.json)。
"""
    outputs["Methods_Results_en.md"]=f"""# ClearEval supplementary methods and results: source extension v3

{methods}

An official publisher bundle for Renier et al. (2016; DOI 10.1016/j.cell.2016.05.007) recovered the supplemental author procedure and a distinct April 2016 bench version. Their parameter differences were retained. The source workflow contains 28 post-fixation operations; the q2 scoring branch contains nine clearing/RI/storage operations, consistent with the task's requested output. Prior immunolabeling is a condition, not an asserted completed task state or an extra denominator. The native tdTomato requirement in q248 remains unsupported; route-only diagnostics cannot fill primary SR/Com/CCE. The four preceding FDISCO/PEGASOS branches are unchanged. All {len(refs)} branches from {len(families)} source families remain source-extracted candidates with no expert confirmation. [Source and scope]({SOURCE}/README.md).

Three 65-answer offline batches were completed. At threshold 0.7, {len(added)} answers gained step values, giving {numeric} provisional SR/SP and {numeric_cce} candidate CCE values; formal eligibility remained {formal}. Among {len(old_numeric)} previously numerical answers, SR changed in {changes['sr']} and SP in {changes['sp']}. Original parameter completeness, correctness and EGES were unchanged. These gains reflect added reference coverage, not generator improvement. English-encoder performance on Chinese steps remains a validation limitation. [Per-answer results]({PREFIX}_t070_per_answer.csv).

The fixed 13-model × {gaps['question_count']}-question grid contained {count['answer_missing']} missing answer, {count['revised_steps_not_run']} unrun revised-step cells, {count['screened_reference_insufficient']} screened reference-insufficient cells, and {count['provisional_CCE_numeric']} provisional CCE cells. Numeric and formal common sets contained {len(gaps['numeric_common_question_ids'])} and {len(gaps['formal_common_question_ids'])} questions. No full-cohort ranking is supported. In the prespecified two-Gemini five-question subset, mean IA/HV were {fmt(flash['IA'])}/{fmt(flash['HV'])} for Flash and {fmt(pro['IA'])}/{fmt(pro['HV'])} for Pro. The single-family bootstrap was degenerate. Threshold summaries used metric-specific intersections of finite answers. [Joint analysis]({ANALYSIS}/joint_summary.json).

Removing route filtering produced positive SR for {route_v3['main_missing_with_positive_unfiltered_sr_n']} of {route_v3['main_sr_missing_n']} reference-insufficient answers. It changed SR in {route_v3['paired_sr_changed_n']} of {route_v3['paired_main_numeric_n']} already numerical answers and SP in {route_v3['paired_sp_changed_n']} of {route_v3['paired_main_numeric_n']}. These diagnostic values did not replace primary missing values. Four q248 declared-route diagnostics were also separated from task-compatible coverage because native tdTomato fluorescence preservation was not established. [Current filtering diagnostic](controls/supplement_v3_route_filter_diagnostic_summary.json).

Frozen supplement-v2 controls were reused because their explicit FDISCO-only inputs and configuration did not change. They comprise {e2['technical_successful_cases']} full-text evaluations and {e2['complete_candidate_cce_pairs']} complete candidate pairs from three source answers, not new independent cases. Deleting the RI/storage module reduced SR in {deletion['negative_sr']}/{deletion['n_sr']} pairs; removing times reduced c_param in {param['negative_c_param']}/{param['n_c_param']}; order conflicts reduced co_order in {order['negative_co_order']}/{order['n_co_order']}. Granularity changes could raise or lower SR despite identical operation text. Six alternative candidates yielded {alt['complete_candidate_cce_pairs']} complete descriptive pairs across only three question IDs in one task family, short of 6–8 different-task qualified comparisons. [Frozen controls](judges/local_controls_supplement_v2/control_summary.json).

The unchanged local stability batch contains {e4['actual_observations']} observations (two answers × two judge families × three repeats), including {e4['successful_exact_reused_observations']} exact reuses. All 16 metrics had zero within-group ranges and no strict rank flips, but all six Llama extractions copied the rubric example and mismatched the answer route. Numerical repeatability did not establish fidelity or validity. Five actual development extractions passed identity replays through the original EGES functions; A01 retained a genuine missing label component and dependent Eff/IA/HV missingness. Fifteen holdouts remain pending, and incomplete legacy tissue/size fields are explicit. No expert-corrected effects are available. [Review denominators and effects](human_review/review_impact_addendum/summary.json).

One expert and the original 5-development/15-holdout design remain unchanged. Completed expert-review denominators are zero; error rates and correction effects are NA. Source construction was recorded separately and used no human-review slots. The archived human 0..5 convention does not resolve the original rubric/provenance or signed-scale mapping. The new whole-brain metadata prescreen creates source-binding leads, not scored tasks. No wet-lab measurements are available. Total recorded model requests remain {calls}; the present extension made none. [Current index](current_run_index.json).
"""
    outputs["Abstract_en.md"]=f"""# Draft abstract: supplementary development evidence

Fixed-sample tissue-clearing protocol selection and generation require matching sample scale and labeling with imaging and preservation goals. ClearEval assesses procedure coverage and tradeoffs through parameter completeness and correctness, including omitted operations, missing parameters and order errors, while Evidence-Grounded Effectiveness Scoring relates proposed choices to task-specific evidence. We added source-bound Step Recall and Step Precision without changing those original components. Recovery of an iDISCO+ 2016 supplement added a conditional reference alongside FDISCO/PEGASOS candidates. Across 65 archived answers from 13 models and five tasks, {numeric} yielded provisional step scores and {numeric_cce} candidate CCE values, an increase of {len(added)} answers without new model requests; previously numerical results were unchanged. The fixed 13-model common set remained empty. A prespecified two-model subset gave mean IA/HV of {fmt(flash['IA'])}/{fmt(flash['HV'])} and {fmt(pro['IA'])}/{fmt(pro['HV'])}, with a degenerate single-source-family bootstrap. Frozen controls yielded {e2['complete_candidate_cce_pairs']} descriptive pairs, exposing nonresponse to parameter omissions and order conflicts and sensitivity to step granularity. Local repeats were numerically stable, but rubric-copy extraction failures prevented reliability claims. Expert correction effects, broader qualified alternative-route comparisons and wet-lab outcomes remain pending. These findings support traceable partial evaluation and reveal coverage and evaluator limitations, without establishing formal model rankings or experimental predictive validity.
"""
    outputs["STATUS.md"]=f"""# ClearEval r2 当前状态：supplement v3

{first}

{common}

{source_note} {q248_note}

已完成且输入未变的真实实验继续复用：E2 {e2['complete_candidate_cce_pairs']} 对、E4 {e4['actual_observations']} 观测、E3 {e3['actual_auto_records']} 真实开发提取，替代路线 {alt['complete_candidate_cce_pairs']} 完整描述对；这些保持各自 v2 输入版本，不累计为本轮新实验。人工仍 {returned} 回传判项、15 留出待定；湿实验 {wet['real_measurement_rows']} 真实测量。全包请求 {calls}/{budget_limit}，本轮新增0。

下一项可独立推进工作是把元数据预筛的不同任务与准确来源/标签条件绑定：q1 的 2016 来源绑定和 q13–15 的直接来源核查已开始，尚未计入本批评分。先冻结来源、题号与实际答案，再决定新的离线评分，不把这些线索直接计作合格替代任务。人工回传后用既有 guarded 入口完成成对纠错影响。[预筛](controls/whole_brain_task_prescreen/audit.json)、[E1/E3 当前分母](human_review/review_impact_addendum/summary.json)、[剩余依赖](remaining_dependencies.json)。

详细结果见 [RESULTS_zh.md](RESULTS_zh.md)，机器入口为 [current_run_index.json](current_run_index.json)。`python scripts/cce_report.py` 优先检测本阶段结果并进入 v3 生成器；当前实际命令见 [commands.md](commands.md)。[前一阶段报告按字节快照](historical_reports/supplement_v2_before_idisco/snapshot_manifest.json)，原 v1/v2 评分批次不变。
"""
    command_lines=["# 本阶段已实际执行的命令", "", "仅收录已生成实际产物的命令；没有把计划、未运行脚本或模型请求复用计为新执行。前期冻结实验的完整命令见 [v2 命令快照](historical_reports/supplement_v2_before_idisco/commands.md)。", ""]
    for r in commands:
        command_lines += [f"来源 [{r['source']}]({r['source']})；记录状态 `{r['status']}`。", "", "```powershell", r['command'], "```", ""]
    command_lines += ["报告生成命令将在本次成功退出后由 [report_generation.json](report_generation.json) 留存实际参数、脚本及全部输入/输出哈希。此生成器不调用模型，也不触发评分。"]
    outputs['commands.md']='\n'.join(command_lines)
    outputs['remaining_dependencies.json']=dependencies
    outputs['budget.json']=budget
    outputs['reference_recovery/reference_construction_current.json']={
        "scope":"supplement_v3_source_extracted_development_not_expert_gold", "source_extracted_route_candidates":len(routes),"source_families":len(families),
        "task_specific_branches":[{"reference_id":r['reference_id'],"question_ids":r['question_ids'],"steps":len(r['steps']),"status":r['status'],"formal_eligible":False} for r in refs],
        "expert_confirmed_routes":0,"recovered_verified_original_supplements":recovered_n,"reference_manifest":REFERENCE,
        "separate_construction_records":["reference_recovery/supplement_bound/construction_run.json", SOURCE+"/reference_construction_v1.json"],
        "new_source_manifest":SOURCE+"/source_manifest.json","source_conflicts":SOURCE+"/source_version_differences.json",
        "pilot_numeric_answer_links":numeric,"question_ids":runs[70]['tasks'],"expert_minutes":None,"reference_construction_separate_from_20_answer_budget":True,
        "human_confirmation":None,"formal_eligible":False,"remaining":dependencies['reference_validation'],
        "historical_availability_audit":"Early main-text v1 availability prose is historical only; official supplements are now read. Other locally indexed routes still require exact version and task binding."}
    current_config=dict(config)
    current_config['current_execution']={"version":"supplement_v3_idisco","primary_run":f"{PREFIX}_t070_run.json","primary_config_hash":runs[70]['config_hash'],"reference":REFERENCE,"joint_analysis":ANALYSIS,
        "frozen_controls":"judges/local_controls_supplement_v2","frozen_stability":"judges/local_stability_supplement_v2","frozen_extraction":"human_review/rescoring/v4_dev_v2",
        "frozen_input_reuse_reason":"Explicit old route subsets and every actual prompt/reference/input hash are unchanged; adding iDISCO+ to a separate global collection does not alter those prompts.",
        "report_generator":"scripts/cce_report_supplement_v3.py","format_note":"JSON serialization is valid YAML 1.2","formal_eligible":False}
    outputs['resolved_config_current.yaml']=current_config
    outputs['current_run_index.json']={"version":"supplement_v3_idisco","formal_eligible":False,"primary":f"{PREFIX}_t070_per_answer.json","thresholds":[f"{PREFIX}_t0{t}_per_answer.json" for t in (60,70,80)],
        "reference":REFERENCE,"new_source_manifest":SOURCE+"/source_manifest.json","new_source_review":SOURCE+"/review/source_applicability_audit.json","construction":SOURCE+"/reference_construction_v1.json",
        "analysis":ANALYSIS+"/joint_summary.json","gap_audit":"common_set_gaps_v3/summary.json","score_verification":"score_batch_verification_idisco.json",
        "reference_expansion_effects":ANALYSIS+"/reference_expansion_summary.json","language_diagnostic":ANALYSIS+"/new_idisco_answers.json","route_filter_diagnostic":"controls/supplement_v3_route_filter_diagnostic_summary.json","figure_qa":ANALYSIS+"/figure_visual_qa.json",
        "new_numeric_answer_ids":[r['answer_id'] for r in added],"old_numeric_changes":changes,"original_quality_components_unchanged":original_components_unchanged,
        "frozen_controls":{"path":"judges/local_controls_supplement_v2","version":"supplement_v2","summary":e2},
        "frozen_stability":{"path":"judges/local_stability_supplement_v2","version":"supplement_v2","summary":e4},
        "frozen_extraction":{"path":"human_review/rescoring/v4_dev_v2","identity":identity,"summary":e3},
        "frozen_alternatives":{"path":"judges/local_alternative_development","summary":alt},
        "review_impact":"human_review/review_impact_addendum/summary.json","task_prescreen":"controls/whole_brain_task_prescreen/audit.json","q29_partial_audit":"inventory/partial_score_q29/audit.json",
        "q248_diagnostic":q248_path.relative_to(OUT).as_posix() if q248_path else None,"q248_diagnostic_enters_primary_CCE":False,
        "historical_reports":"historical_reports/supplement_v2_before_idisco","prior_v1_reports":"historical_reports/two_source_maintext_v1",
        "request_attempts":calls,"new_model_requests":0,"recorded_commands":commands,"input_sha256":dict(INPUTS)}
    return outputs


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-only',action='store_true')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args(argv)
    if args.snapshot_only:
        data=snapshot()
        print(json.dumps({'status':'snapshot_verified','files':len(data['files']),'path':str(HIST),'reports_refreshed':False}))
        return
    outputs=build()
    if args.check_only:
        print(json.dumps({'status':'render_checked_without_writes','outputs':len(outputs),'input_files':len(INPUTS),'new_model_requests':0}))
        return
    snapshot()
    for name,data in outputs.items(): save(name,data)
    save('report_generation.json',{'status':'completed','version':'supplement_v3_idisco','generated_utc':datetime.now(timezone.utc).isoformat(),
        'command':subprocess.list2cmdline([sys.executable,*sys.argv]),'script_sha256':sha(__file__),'dispatcher_sha256':sha(ROOT/'scripts/cce_report.py'),
        'inputs':dict(INPUTS),'outputs':{name:sha(OUT/name) for name in outputs},'new_model_requests':0,'old_result_batches_modified':False})
    print(json.dumps({'status':'supplement_v3_reports_refreshed','outputs':len(outputs),'requests_in_ledger':outputs['budget.json']['attempts_recorded'],'new_model_requests':0}))


if __name__=='__main__':
    main()
