"""Regenerate current r2 reports from supplement-v2 evidence; never call models.

Old human-readable reports are backed up byte-for-byte once. Scientific inputs,
old results, references, and annotations are read-only to this report writer.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/cce_validation'
HIST = OUT / 'historical_reports/two_source_maintext_v1'
REPORTS = ['STATUS.md', 'RESULTS_zh.md', 'Methods_Results_en.md', 'Abstract_en.md', 'commands.md']
INPUTS = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name, default=None):
    path = OUT / name
    if not path.exists():
        return default
    INPUTS[str(path.relative_to(OUT)).replace('\\', '/')] = sha(path)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def textread(name):
    path = OUT / name
    INPUTS[str(name).replace('\\', '/')] = sha(path)
    return path.read_text(encoding='utf-8-sig')


def rebase_markdown(name):
    content = textread(name)
    def replace(match):
        target = match[1]
        if target.startswith(('https:', 'http:', '#')):
            return match[0]
        resolved = ((OUT / name).parent / target).resolve()
        if resolved.is_relative_to(OUT):
            return '](' + str(resolved.relative_to(OUT)).replace('\\', '/') + ')'
        return match[0]
    return re.sub(r'\]\(([^)]+)\)', replace, content)


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value.strip() + '\n', encoding='utf-8')
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def snapshot():
    """Never overwrite a historical snapshot, even after current reports change."""
    manifest = HIST / 'snapshot_manifest.json'
    if manifest.exists():
        old = json.loads(manifest.read_text(encoding='utf-8'))
        for name, expected in old['files'].items():
            if sha(HIST / name) != expected:
                raise ValueError('Historical report snapshot changed: ' + name)
        return old
    HIST.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in REPORTS:
        source, dest = OUT / name, HIST / name
        content = source.read_bytes()
        if dest.exists() and dest.read_bytes() != content:
            raise ValueError('Unregistered historical snapshot exists: ' + name)
        if not dest.exists():
            dest.write_bytes(content)
        hashes[name] = sha(dest)
        if hashes[name] != sha(source):
            raise ValueError('Snapshot copy verification failed: ' + name)
    record = {'scope': 'frozen_two_source_maintext_v1_human_reports',
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'files': hashes, 'byte_identical_at_capture': True,
              'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
              'old_batches_modified': False}
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def fmt(x):
    return 'NA' if x is None else f'{x:.6f}'


def snapshot_legacy_metadata():
    """Archive early availability prose without changing its historical bytes."""
    names = ['reference_recovery/source_availability_audit.md',
             'reference_recovery/source_availability_audit.json',
             'reference_recovery/reference_construction_current.json']
    manifest = HIST / 'metadata_snapshot_manifest.json'
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        for relative, item in data['files'].items():
            if sha(HIST / item['snapshot']) != item['sha256']:
                raise ValueError('Historical metadata snapshot changed: ' + relative)
        return
    files = {}
    for relative in names:
        source = OUT / relative
        dest = HIST / Path(relative).name
        if dest.exists() and dest.read_bytes() != source.read_bytes():
            raise ValueError('Unregistered metadata snapshot exists: ' + str(dest))
        if not dest.exists():
            dest.write_bytes(source.read_bytes())
        files[relative] = {'snapshot': dest.name, 'sha256': sha(dest)}
    manifest.write_text(json.dumps({'scope': 'historical_v1_not_current_coverage', 'files': files,
                                  'byte_identical_at_capture': True}, indent=2) + '\n', encoding='utf-8')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(x) for x in row) + ' |' for row in rows])


def command_records():
    """Copy executed commands and recorded outcomes; do not infer execution."""
    records = []
    sources = [f'supplement_v2_t0{n}_run.json' for n in (60, 70, 80)] + [
        'analysis_supplement_v2/analysis_run.json', 'common_set_gaps_v2/summary.json',
        'reference_recovery/supplement_bound/construction_run.json',
        'controls/supplement_v2_route_filter_diagnostic_summary.json',
        'figures_supplement_v2/supplement_plot_run.json',
        'analysis_supplement_v2/figure_visual_qa.json',
        'human_review/rescoring/v4_dev_v2/execution_offline.json',
        'human_review/rescoring/v4_dev_v2/summary.json']
    sources += [str(p.relative_to(OUT)).replace('\\', '/') for p in (OUT / 'judges').glob('*/execution_commands.json')
                if 'supplement_v2' in p.parent.name or p.parent.name in {'local_alternative_development', 'local_extraction_dev_v2'}]
    sources += [str(p.relative_to(OUT)).replace('\\', '/') for p in (OUT / 'judges/local_extraction_dev_v2').glob('actual*execution*.json')]
    for name in sources:
        data = read(name)
        if not data:
            continue
        if data.get('command'):
            records.append({'source': name, 'command': data['command'],
                            'status': 'recorded_in_completed_artifact'})
        for label, entry in data.items():
            if label.endswith('_argv') and isinstance(entry, list) and data.get('program'):
                stage = label[:-5]
                records.append({'source': name, 'stage': stage,
                                'command': subprocess.list2cmdline([data['program'], *entry]),
                                'status': data.get(stage + '_status', 'exit_' + str(data.get(stage + '_exit_code', 'unknown'))),
                                'exit_code': data.get(stage + '_exit_code')})
            if isinstance(entry, dict) and entry.get('argv'):
                argv = entry['argv']
                if entry.get('executable') and argv[0] != entry['executable']:
                    argv = [entry['executable'], *argv]
                records.append({'source': name, 'stage': label,
                                'command': subprocess.list2cmdline(argv),
                                'status': entry.get('status', 'exit_' + str(entry.get('exit_code', 'unknown'))),
                                'exit_code': entry.get('exit_code')})
        for entry in data.get('commands', []):
            if entry.get('argv'):
                records.append({'source': name, 'command': subprocess.list2cmdline([entry['executable'], *entry['argv']]),
                                'stage': entry.get('stage', ''),
                                'status': 'exit_' + str(entry.get('exit_code', 'unknown')),
                                'exit_code': entry.get('exit_code')})
    return records


def build():
    INPUTS.clear()
    pilot = read('supplement_v2_t070_per_answer.json')
    if not pilot:
        raise ValueError('No supplement-v2 primary results')
    config = read('supplement_v2_t070_resolved_config.json')
    run = read('supplement_v2_t070_run.json')
    subset = read('analysis_supplement_v2/pilot_participating_subset.json')
    fixed = read('analysis_supplement_v2/revised_full_fixed_cohort.json')
    gaps = read('common_set_gaps_v2/summary.json')
    thresholds = read('analysis_supplement_v2/threshold_sensitivity.json')
    effects = read('reference_recovery/supplement_bound/reference_version_effects.json')
    recovered = read('reference_recovery/recovered_supplements/official_object_recovery_manifest.json')
    refs = read('reference_recovery/supplement_bound/construction_run.json')
    route = read('controls/supplement_v2_route_filter_diagnostic_summary.json', {}).get('overall', {})
    alternative = read('judges/local_alternative_development/development_summary.json', {})
    controls = read('judges/local_controls_supplement_v2/development_summary.json', {})
    control_rows = read('judges/local_controls_supplement_v2/control_summary.json', [])
    control_map = {r['condition']: r for r in control_rows}
    e4_path = 'judges/local_stability_supplement_v2/development_summary.json'
    e4 = read(e4_path)
    e4_version = 'supplement_v2' if e4 else 'maintext_v1_historical'
    if not e4:
        e4_path = 'judges/local_stability/cce_stability_summary.json'
        e4 = read(e4_path, {})
    lineage = read('human_review/lineage/summary.json')
    human = read('human_review/review_status.json')
    local = read('human_review/local_step_audit/summary.json')
    # Select the current completed guarded bridge, not a merely prepared batch.
    e3_base = 'human_review/rescoring/v3_guarded'
    candidate_identity = read('human_review/rescoring/v4_dev_v2/identity_verification.json')
    if candidate_identity and candidate_identity.get('status') == 'pass':
        e3_base = 'human_review/rescoring/v4_dev_v2'
    identity = read(e3_base + '/identity_verification.json')
    faithful = read(e3_base + '/faithful_scores.json')
    nochange = read(e3_base + '/reviewed_no_change.json')
    e3_summary = read(e3_base + '/summary.json', {})
    e3_readiness = read(e3_base + '/review_field_readiness.json', {})
    e3_na = read(e3_base + '/actual_na_and_integrity_audit.json', {})
    e3_auto = read(e3_base + '/auto_inputs.json')
    local_verify = read('judges/local_v2_verification.json', {})
    figure_qa = read('analysis_supplement_v2/figure_visual_qa.json', {})
    wet = read('wetlab/wetlab_status.json')
    coverage = read('analysis_supplement_v2/dataset_coverage_metadata.json')
    old_availability = read('reference_recovery/source_availability_audit.json')
    ledger_text = textread('judges/request_ledger.jsonl')
    ledger = [json.loads(s) for s in ledger_text.splitlines() if s.strip()]
    calls = len(ledger)
    budget_limit = config['budget']['default_max_additional_api_requests']
    expert_reviewed = sum(x['reviewed_items'] for x in human['splits'].values())
    returned_answers = sum(x['reviewed_answers_any_item'] for x in human['splits'].values())
    numeric = sum(r.get('sr') is not None for r in pilot)
    formal = sum(bool(r.get('formal_eligible')) for r in pilot)
    means = subset['means']; flash = means['gemini-3-flash']; pro = means['gemini-3-pro']
    count = gaps['state_counts']
    version_metrics = effects['metrics']
    source_n = len({x['doi'] for x in recovered})
    recovered_n = sum(x['status'] == 'recovered_verified_original_bytes' for x in recovered)
    control_complete = controls.get('complete_candidate_cce_pairs', 0)
    control_success = controls.get('technical_successful_cases', 0)
    e4_n = e4.get('actual_observations', e4.get('observations', 0))
    copies = e4.get('rubric_example_copies', e4.get('explicit_route_mismatches', 0))
    e4_note = (f"补充参考 v2 的 {e4_n} 个真实观测来自两份答案×两个本地家族×三次；"
               f"其中 {e4.get('successful_exact_reused_observations', 0)} 条精确复用，{e4.get('new_requests_this_batch', 0)} 次新请求。"
               f"分项重复有波动组数为 {e4.get('component_groups_with_variation', 'NA')}，严格排名翻转指标数为 {e4.get('strict_rank_flip_metrics', 'NA')}。"
               f"Llama 的 {copies}/6 次提取完整复制量表示例且与答案路线不符；零波动不能证明提取忠实或评分可靠。"
               if e4_version == 'supplement_v2' else
               f"当前已完成的稳定性证据仍为主文 v1 历史范围：{e4_n} 个真实观测，Llama {copies}/6 次复制量表示例。v2 运行若在准备或执行中，尚不算完成；旧观测不升级为 v2。")
    e4_en = (f"The supplement-v2 stability batch contained {e4_n} actual observations (two answers, two local evaluator families, three repeats), including {e4.get('successful_exact_reused_observations', 0)} exact reuses and {e4.get('new_requests_this_batch', 0)} new requests. It had {e4.get('component_groups_with_variation', 'NA')} varying component groups and {e4.get('strict_rank_flip_metrics', 'NA')} strict rank-flip metrics. All {copies}/6 Llama observations copied the rubric extraction example and disagreed with the declared route. Numerical repeatability therefore did not establish extraction fidelity or evaluator validity."
              if e4_version == 'supplement_v2' else
              f"Stability evidence remains historical main-text v1: {e4_n} observations, with {copies}/6 Llama rubric-copy failures. No uncompleted v2 observation is counted.")
    control_note = (f"更新参考后，{control_success}/{controls.get('planned_full_texts', 21)} 份全文重新解析、提取、评分，形成 {control_complete}/{controls.get('controlled_pairs', 15)} 对完整候选 CCE 比较。"
                    f"仍只有 {controls.get('source_answers', 3)} 份源答案、{controls.get('task_families', 2)} 个任务家族、{controls.get('source_families', 1)} 个来源家族，正式合格对为 {controls.get('formal_completed_pairs', 0)}。这是原有控制的参考版本重跑，不新增独立案例。"
                    if controls else '补充参考 v2 控制仍待完成；计划与已发请求不计为完整配对。')
    findings = []
    if control_rows:
        delete = control_map['necessary_step_deletion']; parameter = control_map['necessary_parameter_deletion']
        order = control_map['evidence_supported_order_conflict']; equiv = control_map['deterministic_equivalent_representation']
        merge = control_map['adjacent_entry_merge']
        findings = [
            f"RI/保存模块删除仅 {delete['negative_sr']}/{delete['n_sr']} 对 SR 下降，平均 ΔSR={fmt(delete['mean_delta_sr'])}、ΔCom={fmt(delete['mean_delta_Com'])}、ΔIA={fmt(delete['mean_delta_IA'])}、ΔHV={fmt(delete['mean_delta_HV'])}。删除的是联合模块，不能解释为原子步骤检出率。",
            f"明确时长删除后 c_param 下降 {parameter['negative_c_param']}/{parameter['n_c_param']} 对；平均 ΔEff={fmt(parameter['mean_delta_Eff'])}、ΔIA={fmt(parameter['mean_delta_IA'])}。保留无响应结果。",
            f"顺序冲突后 co_order 和 Cor 各下降 {order['negative_co_order']}/{order['n_co_order']}、{order['negative_Cor']}/{order['n_Cor']} 对；c_param 却下降 {order['negative_c_param']}/{order['n_c_param']} 对。步骤无序匹配不变不能验证正确性检出能力。",
            f"等价编号三对的 SR/SP、Com/Cor 均不变；平均 ΔEff={equiv['mean_delta_Eff']:.9g}，因此不声称完整 CCE 严格不变。",
            f"相邻条目合并的 SR 有 {merge['negative_sr']} 对下降、{merge['zero_sr']} 对不变、{merge['positive_sr']} 对上升，平均 ΔSR={fmt(merge['mean_delta_sr'])}、ΔSP={fmt(merge['mean_delta_sp'])}。原操作文本相同，数值变化反映粒度/提取敏感性，不是方案质量改善。"]
    control_table = table(['条件', '完整对', 'ΔSR', 'ΔCom', 'ΔCor', 'ΔEff', 'ΔIA', 'ΔHV'],
                          [[r['condition'], r['complete_pairs'], *[fmt(r.get('mean_delta_' + m)) for m in ['sr', 'Com', 'Cor', 'Eff', 'IA', 'HV']]] for r in control_rows]) if control_rows else ''
    mean_table = table(['预先指定模型', 'Com', 'Cor', 'Eff', 'IA', 'HV'],
                       [[name, *[fmt(values[k]) for k in ['Com', 'Cor', 'Eff', 'IA', 'HV']]] for name, values in means.items()])
    th_rows = [[model, *[fmt(next((r['available_item_mean'] for r in thresholds['summaries'] if r['model'] == model and r['metric'] == 'sr' and r['threshold'] == t), None)) for t in thresholds['thresholds']]] for model in means]
    th_table = table(['模型：平均 SR', *map(str, thresholds['thresholds'])], th_rows)
    e3_extra = ''
    if e3_summary:
        e3_extra = (f" 本批 {e3_summary['new_requests']} 次新请求＋{e3_summary['reused_actual_trials']} 条精确复用，"
                    f"15 份留出仍待自动提取。路线、marker 和总时间的 {e3_summary['direct_route_marker_total_time_item_rows']} 个判项有实际字段；"
                    f"组织/尺度 {e3_summary['tissue_scale_partial_schema_rows']} 项只有原文及 sample_ri，旧 schema 没有组织身份/尺寸字段，不能称 20 项完整抽取。"
                    "五份 protocol_time_hours 都为 null，未用参考时程补齐。A01 的实际 s_label=NA，Eff/IA/HV 随之为 NA，其他已知分项保留，缺失类别仍待审。")
    common_note = f"固定 13 模型×{gaps['question_count']} 题共有 {gaps['expected_cells']:,} 个格：{count['answer_missing']} 个缺答、{count['revised_steps_not_run']:,} 个未运行新步骤评分、{count['screened_reference_insufficient']} 个经本次筛选仍参考不足、{count['provisional_CCE_numeric']} 个暂定 CCE 数值。未运行不等于没有适用参考。数值和正式 Q* 均为空，不能发布固定全队列的新 CCE 排名。"
    source_note = f"已恢复 {recovered_n} 份官方原始 PDF，覆盖 {source_n} 篇来源论文，原始字节与既有 PMC 对象索引 MD5 一致，并保存 SHA256、页码、文本偏移和图像复核记录。当前 {len(refs['reference_branches'])} 个任务分支来自 FDISCO/PEGASOS 两来源，步骤候选为 7/8 项；它们仍是 source_extracted，专家确认为 0。附件缺失已解决，作者程序覆盖不等于生物学必要性或具体任务适用性已确认；3 mm 固定块专属时程/重复次数仍未知，未从整脑时程插值。"
    source_note += f" 早期只读盘点的 {old_availability['counts']['audited_routes']} 个候选路线家族（包含现已纳入的 PEGASOS）均有部分可读本地全文，后续缺口是版本选择、参考建设及具体适用核查，不能一概归为缺原文。早期 source_availability_audit 的 14/51 数值仅属主文 v1 历史，不代表当前覆盖。"
    version_note = f"三阈值 0.6/0.7/0.8 各重算 {len(pilot)} 份既有答案，当前 {numeric} 份 SR/SP 和候选 CCE 有数值、{formal} 份正式合格。与主文 v1 的 {effects['compared_answers']} 份共同数值答案相比，SR {version_metrics['sr']['changed_n']} 份、SP {version_metrics['sp']['changed_n']} 份、Com {version_metrics['Com']['changed_n']} 份变化；原答案、题干、c_param、Cor 和 EGES 均未改变。参考定义本身会改变步骤分数，因此论文需报告参考版本和来源，而非把新分数解释为模型改善。"
    alt_note = f"独立两路线开发批实际新增 {alternative.get('new_requests_this_batch', 0)} 次全文请求，{alternative.get('technical_successful_cases', 0)}/{alternative.get('planned_cases', 9)} 份技术成功，{alternative.get('complete_candidate_cce_pairs', 0)}/{alternative.get('candidate_pairs', 6)} 对描述性候选比较完整，正式合格对为 {alternative.get('formal_completed_pairs', 0)}。1 份失败保留 partial 返回，co_chemical 别名没有自动映射成 co_chem。6 个候选对仅来自 q21/q22/q23、1 个任务家族，且跨生成模型并共享基线，未满足 6–8 个不同任务的合格替代路线要求，不能估计路线因果效应。"
    human_note = f"历史 {lineage['original_answers_hash_bound']} 份答案已绑定 {lineage['versions']} 个 Git 历史版本；旧比较代码明确使用 s_method 的 0..5 约定，但完整原人评量表、独立专家来源及到当前 signed scale 的映射仍未确认。没有据此构造人工 Eff/CCE。新人工仍为一位专家、5 开发＋15 留出共用样本；原 20 答案/160 判项中已回传 {expert_reviewed} 项。局部步骤核查仅建立 10 个开发候选判项，实际 reviewed={local['reviewed_rows']}，15 份留出仍待来源适用与独立性核查；这些定向条目不产生完整人工 SR 或总体误差率。"
    e3_note = f"E3 当前 {e3_base.rsplit('/', 1)[-1]} 已绑定 {identity['actual_source_extractions']} 份真实开发提取，固定原需求、来源和代码 hash 调用原 EGES 函数；四分项及 Eff 的数值/NA 与实际源请求一致。专家纠错答案 {faithful.get('expert_corrected_answers', len(faithful.get('records', [])))}，真实审核无修改答案 {nochange['reviewed_no_change_answers']}；没有回传的项目保持 NA/pending，软件 fixture 不计为专家证据。{e3_extra}"
    route_note = f"v2 无筛选 max-SR 离线诊断中，{route.get('main_sr_missing_n', 'NA')} 份原参考不足答案有 {route.get('main_missing_with_positive_unfiltered_sr_n', 'NA')} 份得到正 SR；{route.get('paired_main_numeric_n', 'NA')} 份已有数值答案中 {route.get('paired_sr_changed_n', 'NA')} 份 SR、{route.get('paired_sp_changed_n', 'NA')} 份 SP 改变。主 NA 与科学覆盖保持不变，不能将放宽筛选所得数值当作新增有效覆盖。"
    figures = ['development_cce_projections', 'threshold_sensitivity', 'reference_version_effects', 'alternative_development_pairs', 'controls_supplement_v2', 'stability_supplement_v2']
    figure_links = []
    for stem in figures:
        path = OUT / 'figures_supplement_v2' / (stem + '.png')
        if path.exists():
            figure_links.append(f'[{stem}](figures_supplement_v2/{stem}.png)')
    current_fig_note = ('当前版本对应图：' + '、'.join(figure_links) +
                       f"。图表核验覆盖 {figure_qa.get('render_sets', 'NA')} 套，{figure_qa.get('new_or_changed_renders_directly_inspected', 'NA')} 张新增/改变图已实际目视；"
                       '其余已核验旧 PNG 镜像按字节复用。旧控制/稳定性图仅为 v1 历史镜像，不能算作本轮 v2 请求图。')
    dependencies = {
        'expert_review': 'One expert, 5 development + 15 holdout shared between steps/extraction; actual returns required. Local 10 development items are purposive and not full manual SR.',
        'reference_validation': 'Three official supplements recovered. Four source-extracted branches from two sources remain candidates, not complete expert gold; 3 mm timing/repetition and task-specific applicability unresolved.',
        'alternative_routes': 'Five complete descriptive candidate pairs from three question IDs in one task family do not satisfy 6–8 different tasks; qualification and independent task coverage pending.',
        'cohort_coverage': count,
        'historical_human_scale': '0..5 archived convention recovered, original full rubric/independent expert provenance/signed-scale mapping still unresolved.',
        'extraction_effect': 'Identity replay is software verification; expert-corrected paired effect remains pending until actual reviewed fields return.',
        'evaluator_validity': 'Local substitute is not the unavailable historical evaluator. Llama rubric-copy failures invalidate interpreting zero variation as reliable evaluation.',
        'wetlab': wet['remaining_minimum_inputs'],
        'external_api': 'Earlier two connection failures retained; no additional external retry attributed to offline or local work.'}
    budget = {'limit': budget_limit, 'attempts_recorded': calls,
              'remaining_request_capacity': budget_limit - calls,
              'model_attempts': dict(collections.Counter(x['model'] for x in ledger)),
              'retries_counted': True, 'reused_observations_count_as_new_requests': False,
              'expert_budget': {'experts': 1, 'development': 5, 'holdout': 15, 'returned_answers_any_item': returned_answers, 'returned_items': expert_reviewed},
              'reference_construction_separate': True, 'ledger_sha256': sha(OUT / 'judges/request_ledger.jsonl')}
    outputs = {}
    outputs['RESULTS_zh.md'] = f'''# ClearEval r2 当前补充结果：supplement v2

{version_note}

## 来源恢复与当前覆盖

{source_note} [原始附件与差异表](reference_recovery/recovered_supplements/SOURCE_RECOVERY.md)、[分支构建](reference_recovery/supplement_bound/construction_run.json)、[版本影响](reference_recovery/supplement_bound/reference_version_effects.json)。

{common_note} [逐格缺口](common_set_gaps_v2/cell_status.csv)、[当前逐答案](supplement_v2_t070_per_answer.csv)。全量实际答案表仍为 3,288 行；旧分数可读并逐项复算的 3,287 行仅作历史描述，不能替代新覆盖。

## 全文受控验证与替代候选

{control_note} 基线与变体使用相同冻结配置，对编辑后的全文重新解析、提取和评分；旧 15 对仅作为主文 v1 历史保存。[当前逐对](judges/local_controls_supplement_v2/paired_results.csv)。

{control_table}

表中均值显示六位小数；0.000000 不等于严格为零，微小变化在下文按实际精度保留。

{chr(10).join('- ' + s for s in findings)}

{alt_note} [实际批次](judges/local_alternative_development/development_summary.json)、[失败字段](judges/local_alternative_development/partial_return_fields.json)。这些结果暴露了当前评价器的无响应与表述敏感性，尚不能支持受控检出能力或合理替代路线接受率的正式声明。

## CCE 联合结果与敏感性

预先指定的双 Gemini 五题开发子集保持不变，按逐题 IA/HV 后取均值，结果如下。

{mean_table}

Pro 在该小型子集为三维非支配点，不能外推为固定全队列排名。2,000 次同步来源家族 bootstrap 仍只有 {subset['bootstrap']['source_family_count']} 个来源家族，零宽区间与 100% 入选频率是退化重采样，不能证明泛化稳定性。

{th_table}

阈值比较逐指标使用三个设置的共同有限值交集，SR/SP/Com/IA/HV 均为 {thresholds['common_finite_pairs_by_metric']['sr']} 答案；仍有强阈值敏感性。English all-mpnet-base-v2 是原基线，中文解析修复不等于跨语言匹配已验证。[分析](analysis_supplement_v2/joint_summary.json)、[阈值](analysis_supplement_v2/threshold_sensitivity.json)。

{route_note} [v2 独立诊断](controls/supplement_v2_route_filter_diagnostic.csv)。

## 评价稳定性与人工核查

{e4_note} [实际汇总]({e4_path})。历史 v1 的 12 个观测另存，不与 v2 相加成独立答案。

{human_note} [历史谱系](human_review/lineage/summary.json)、[局部核查](human_review/local_step_audit/summary.json)。

{e3_note} [原提取重放]({e3_base}/identity_verification.json)、[忠实提取待定]({e3_base}/faithful_scores.json)、[字段就绪边界]({e3_base}/review_field_readiness.json)。

## 数据能力覆盖、湿实验与复现

原分类统计保留 {coverage['mcq_final']['rows']:,} 道 MCQ 与 {coverage['qar_historical']['question_rows']} 道开放题的实际 category、knowledge_point、specific 及组织/尺度元数据，不重编层级。[覆盖 CSV](analysis_supplement_v2/dataset_coverage.csv)。湿实验仅为规划：真实测量 {wet['real_measurement_rows']} 行，{wet['planning_scenarios']} 个明确假设的功效情景，主要终点/效应量/方差/最终样本量仍待定，不能声称 CCE 已预测实验效果。[计划](wetlab/WETLAB_PLAN.md)。

{current_fig_note}

全包实际请求尝试 {calls}/{budget_limit}，精确复用与离线重算不重复计数。独立 v2 软件核验核对 {local_verify.get('verified_observation_records', 'NA')} 个观测对应 {local_verify.get('unique_real_requests_verified', 'NA')} 个不同实际请求＋{local_verify.get('exact_reused_records', 'NA')} 条精确复用，检验通过不等于科学验证。[核验](judges/local_v2_verification.md)、[预算](budget.json)、[实际命令](commands.md)、[当前索引](current_run_index.json)、[剩余依赖](remaining_dependencies.json)。旧五份报告按字节封存于 [历史报告](historical_reports/two_source_maintext_v1/snapshot_manifest.json)。
'''
    outputs['Methods_Results_en.md'] = f'''# Supplementary Methods and Results: current supplement-v2 development execution

## Methods

ClearEval's original parameter-completeness scale, four correctness subscales and Evidence-Grounded Effectiveness Scoring (EGES) were retained. BioProBench SR/SP used all-mpnet-base-v2 and cosine threshold 0.7, with sensitivity settings 0.6 and 0.8. Task/route-compatible candidate references were selected by maximum SR, then SP, then frozen order. Com=0.4 SR+0.6 c_param/3; SP was separate. IA=min(Com,Cor,Eff) and HV=Com×Cor×Eff, relative to zero, were calculated per answer before averaging. Known components were retained when others were missing, without zero imputation. Correctness and EGES formulas, scales and fixed historical task demands were unchanged.

Three official supplementary PDFs were recovered and hash-verified. Four task-specific branches represent two source-extracted route candidates: FDISCO (seven operations) and PEGASOS (eight). Whole-brain and 3 mm block branches are separate; unsupported block-specific schedules were not interpolated. Author-procedure coverage does not establish biological necessity or expert-confirmed applicability. Expert reference confirmation remains pending. [Source evidence](reference_recovery/supplement_bound/evidence_manifest.json).

The fixed cohort contains 13 archived 1-shot generators and 253 historical questions. Five development tasks were rescored under each threshold, with all 65 answers preserved. Human review remains one expert and 5 development plus 15 holdout answers shared by step and extraction audits. Local step candidates are purposive and cannot produce population error rates or full manual SR. Family bootstrap synchronizes source-family draws across models (2,000 replicates); numerical dominance tolerance is 1e-12.

## Results

Twenty of 65 answers had provisional revised CCE values; none was formally eligible. Updating references changed SR in {version_metrics['sr']['changed_n']}/{effects['compared_answers']} and SP in {version_metrics['sp']['changed_n']}/{effects['compared_answers']} mutually evaluable answers, while original text, c_param, correctness and EGES remained unchanged. The 3,289-cell question-by-model grid contained one missing answer, 3,223 unrun revised-step evaluations, 45 screened reference-insufficient cells and 20 provisional numeric cells. Unrun cells do not establish reference insufficiency. Both formal and numeric common sets for the fixed 13-model cohort were empty. [Coverage](common_set_gaps_v2/summary.json).

The prespecified two-Gemini five-question development subset gave Flash mean CCE=({fmt(flash['Com'])},{fmt(flash['Cor'])},{fmt(flash['Eff'])}), IA={fmt(flash['IA'])}, HV={fmt(flash['HV'])}; Pro gave ({fmt(pro['Com'])},{fmt(pro['Cor'])},{fmt(pro['Eff'])}), IA={fmt(pro['IA'])}, HV={fmt(pro['HV'])}. Pro was nondominated only within this small subset. Its bootstrap contained one source family and was degenerate; zero-width intervals and unit inclusion frequencies do not support generalization. Threshold comparisons used metric-specific intersections of finite answers. [Joint analysis](analysis_supplement_v2/pilot_participating_subset.json).

With supplement-v2 references, {control_success} full-text control evaluations produced {control_complete} complete candidate pairs from three source answers, two task families and one source family. The same frozen configuration was used for baseline and edited text, including fresh extraction. These recompute existing controls and are not additional independent cases. Module deletion reduced SR in {control_map.get('necessary_step_deletion', {}).get('negative_sr', 0)}/3 pairs; time deletion reduced c_param in {control_map.get('necessary_parameter_deletion', {}).get('negative_c_param', 0)}/3, and order conflicts reduced co_order in {control_map.get('evidence_supported_order_conflict', {}).get('negative_co_order', 0)}/3. Representation and granularity effects remained diagnostic, not quality improvements. Detailed effects, including nonresponding cases, are retained in the [current control table](judges/local_controls_supplement_v2/control_summary.json).

An additional {alternative.get('new_requests_this_batch', 0)} full-text requests for alternative-route candidates produced {alternative.get('technical_successful_cases', 0)} successful answers and {alternative.get('complete_candidate_cce_pairs', 0)} complete descriptive pairs; formal eligibility remained zero. A failed partial return containing co_chemical was not silently mapped to co_chem. Six proposed pairs shared baselines and covered only three question IDs in one task family, failing the requirement for 6–8 distinct tasks. Cross-generator differences cannot identify a causal route effect. [Candidate comparisons](judges/local_alternative_development/development_summary.json).

Removing route filtering gave positive SR to {route.get('main_missing_with_positive_unfiltered_sr_n', 'NA')} of {route.get('main_sr_missing_n', 'NA')} reference-insufficient answers and changed SR in {route.get('paired_sr_changed_n', 'NA')} of {route.get('paired_main_numeric_n', 'NA')} already numeric answers. Main missing values were preserved and scientific coverage was not increased. [Offline diagnostic](controls/supplement_v2_route_filter_diagnostic_summary.json).

{e4_en} [Actual observations]({e4_path}).

Historical lineage recovered five Git versions for 240 hash-bound answers and an archived 0..5 s_method convention. The original complete human rubric, independent expert provenance and mapping to the current signed scale remain unresolved. The current guarded E3 bridge replayed {identity['actual_source_extractions']} actual development extractions with identical original EGES components and Eff, including missingness; this verifies software identity, not an expert correction effect. Fifteen route/marker/total-time review items have actual fields, while five tissue/scale items have only partial schema support; no tissue identity or dimensions were invented. All five protocol_time_hours fields remain null. A01 retained s_label=NA and therefore Eff/IA/HV=NA, with known components preserved and cause classification pending. New expert labels remain {expert_reviewed}, with {local['reviewed_rows']} reviewed local step items and 15 holdout auto inputs pending. No synthetic labels or software fixtures were counted as scientific observations. [Lineage](human_review/lineage/summary.json), [E3 identity]({e3_base}/identity_verification.json), [field readiness]({e3_base}/review_field_readiness.json).

The dataset inventory contains 2,588 MCQs and 253 open-ended questions, retaining separate original taxonomy fields. Wet-lab observations remain zero; 42 power scenarios are explicitly hypothetical. The package ledger records {calls} actual request attempts against a {budget_limit}-request limit. Offline calculations and exact reuses are not new calls. These results support a reproducible development evaluation and identify sensitivity/failure modes; they do not establish a validated cohort ranking, expert agreement, accepted alternative-route rate or wet-lab predictive validity.
'''
    outputs['Abstract_en.md'] = f'''# Supplementary development abstract

We augmented ClearEval with source-bound Step Recall and Step Precision while retaining parameter completeness, correctness and Evidence-Grounded Effectiveness Scoring. Three recovered official supplements supported four provisional task branches from two source papers. Across 65 archived answers from 13 models and five tasks, 20 yielded provisional revised CCE values. Reference revision changed SR in {version_metrics['sr']['changed_n']}/20 and SP in {version_metrics['sp']['changed_n']}/20 comparable answers without changing original correctness or EGES. The fixed 13-model common set remained empty. In a prespecified two-model five-task subset, mean IA/HV were {fmt(flash['IA'])}/{fmt(flash['HV'])} for Gemini Flash and {fmt(pro['IA'])}/{fmt(pro['HV'])} for Gemini Pro; a single source family made bootstrap inference degenerate. Updated-reference controls yielded {control_complete} descriptive pairs from three source answers, while alternative candidates yielded {alternative.get('complete_candidate_cce_pairs', 0)} complete comparisons across only three question IDs. Nonresponse to missing parameters and order conflicts, plus rubric-copy failures in local evaluator repeats, limited validation claims. Expert correction effects and wet-lab outcomes remain pending. The supplement demonstrates a traceable evaluation workflow and exposes reference, representation and evaluator sensitivity without claiming formal full-cohort ranking or experimental predictive validity.
'''
    outputs['STATUS.md'] = f'''# ClearEval r2 当前状态：supplement v2

最新真实增量：{recovered_n} 份官方附件已恢复；三阈值各 {len(pilot)} 答案重算，{numeric} 个暂定 CCE。参考更新改变 {version_metrics['sr']['changed_n']}/20 份 SR、{version_metrics['sp']['changed_n']}/20 份 SP，而原 c_param/Cor/EGES 不变。对论文的意义是必须报告参考版本及数值敏感性，不能把参考修订造成的分数变化当模型进步。

{control_note}

{alt_note}

{e4_note}

{common_note}

{human_note}

{e3_note}

剩余依赖：四分支的完整性/任务适用与专家确认，3 mm 时程，6–8 个不同任务的合理替代路线，15 份独立留出来源，新人工回传、历史量表 signed 映射及真实湿实验。附件现已恢复，不再列为“下载失败”。无新人工或湿实验数据时保持待定并继续独立离线工作。

下一项可独立推进：对已有 iDISCO+ 答案开展原文版本、任务条件与来源元数据绑定核查，形成可复核清单；该准备工作不自动增加正式参考、评分覆盖或合格配对。

实际请求尝试 {calls}/{budget_limit}；当前机器入口为 [current_run_index.json](current_run_index.json)，详细结果见 [RESULTS_zh.md](RESULTS_zh.md)。恢复报告命令仍为 `python scripts/cce_report.py`，检测到 supplement_v2_t070_per_answer.json 后转入新生成器。实际解释器与既有运行命令见 [commands.md](commands.md)。旧报告与 v1 批次保留，版本重跑不累计为独立案例。
'''
    commands = command_records()
    sections = ['# 实际命令记录：当前 supplement v2',
                '本页转录 run/EXECUTION 实际执行日志中的命令与返回状态；未记录退出码不视为验证成功，计划命令字符串不收录。旧准备快照另行保留，没有凭脚本存在推定执行成功。工作目录为 `C:\\ClearEval\\ClearEval-public`。']
    for item in commands:
        sections.extend([f"## {item['source']} {item.get('stage', '')}",
                         f"记录状态：`{item['status']}`。", '```text\n' + item['command'] + '\n```'])
    execution_sources = ['human_review/EXECUTION.md', 'human_review/lineage/EXECUTION.md',
                         'human_review/local_step_audit/EXECUTION.md', 'human_review/rescoring/v3_guarded/EXECUTION.md',
                         'human_review/rescoring/v4_dev_v2/EXECUTION.md',
                         'judges/local_v2_verification.md', 'judges/local_extraction_dev_v2/EXECUTION.md']
    for name in execution_sources:
        if (OUT / name).exists():
            sections.extend([f'## 已有执行实录：{name}', rebase_markdown(name)])
    sections += ['## 报告恢复', '当前实际调用：\n\n```text\n' + subprocess.list2cmdline([sys.executable, *sys.argv]) + '\n```',
                 '本次报告生成完成后的输入/输出散列见 [report_generation.json](report_generation.json)。旧阶段完整命令页已封存：[主文 v1 命令](historical_reports/two_source_maintext_v1/commands.md)。']
    outputs['commands.md'] = '\n\n'.join(sections)
    outputs['remaining_dependencies.json'] = dependencies
    outputs['budget.json'] = budget
    outputs['reference_recovery/reference_construction_current.json'] = {
        'scope': 'supplement_v2_source_extracted_development_candidates_not_expert_gold',
        'source_extracted_route_candidates': 2, 'source_families': source_n,
        'task_specific_branches': refs['reference_branches'], 'expert_confirmed_routes': 0,
        'recovered_verified_original_supplements': recovered_n,
        'supplement_manifest': 'recovered_supplements/official_object_recovery_manifest.json',
        'reference_manifest': 'supplement_bound/references_supplement_v2.json',
        'pilot_numeric_answer_links': numeric, 'task_families': 3,
        'question_ids': run['tasks'], 'expert_minutes': None,
        'reference_construction_separate_from_20_answer_budget': True,
        'workload_ledger': '../human_review/reference_construction_ledger.csv',
        'expert_review_package_scope': 'Original five development and fifteen holdout identities unchanged; current development extraction uses supplement-v2 evidence, expert labels remain zero.',
        'remaining': 'Expert completeness/applicability and task-specific requirements remain pending; 3 mm block timing/repetition not supported. Official supplementary bytes are recovered.',
        'other_local_routes': old_availability['counts']['routes_with_some_readable_local_fulltext'],
        'historical_availability_audit': 'source_availability_audit.md is a frozen main-text-v1 audit; its 14/51 coverage is superseded, its local availability observations remain historical evidence.'}
    current_config = dict(config)
    current_config['current_execution'] = {'version': 'supplement_v2', 'primary_run': 'supplement_v2_t070_run.json',
        'primary_config_hash': run['config_hash'], 'new_reference_formal_eligible': False,
        'joint_analysis': 'analysis_supplement_v2', 'controls': 'judges/local_controls_supplement_v2',
        'stability_source': e4_path, 'stability_scope': e4_version,
        'report_generator': 'scripts/cce_report_supplement_v2.py',
        'format_note': 'JSON serialization is valid YAML 1.2; original resolved_config.yaml is unchanged.'}
    outputs['resolved_config_current.yaml'] = current_config
    index = {'version': 'supplement_v2', 'formal_eligible': False,
             'primary': 'supplement_v2_t070_per_answer.json',
             'thresholds': [f'supplement_v2_t0{t}_per_answer.json' for t in (60, 70, 80)],
             'reference': 'reference_recovery/supplement_bound/references_supplement_v2.json',
             'source_manifest': 'reference_recovery/recovered_supplements/official_object_recovery_manifest.json',
             'analysis': 'analysis_supplement_v2/joint_summary.json',
             'gap_audit': 'common_set_gaps_v2/summary.json',
             'reference_version_effects': 'reference_recovery/supplement_bound/reference_version_effects.json',
             'route_filter_diagnostic': 'controls/supplement_v2_route_filter_diagnostic_summary.json',
             'controls': {'path': 'judges/local_controls_supplement_v2', 'summary': controls},
             'alternative_candidates': {'path': 'judges/local_alternative_development', 'summary': alternative},
             'stability': {'path': e4_path, 'version': e4_version, 'summary': e4},
             'extraction_identity': {'path': e3_base, 'identity': identity, 'summary': e3_summary,
                                     'pending_auto_answers': len(e3_auto['pending_answers']),
                                     'field_readiness': e3_base + '/review_field_readiness.json'},
             'human_lineage': 'human_review/lineage/summary.json', 'local_step_audit': 'human_review/local_step_audit/summary.json',
             'historical_reports': 'historical_reports/two_source_maintext_v1',
             'historical_source_availability': {'path': 'reference_recovery/source_availability_audit.md',
                 'scope': 'maintext_v1_historical_only_14_51_not_current',
                 'immutable_snapshot': 'historical_reports/two_source_maintext_v1/source_availability_audit.md',
                 'current_construction': 'reference_recovery/reference_construction_current.json'},
             'figure_scope_warning': 'Old E2/E4 mirrors inside figures_supplement_v2 are v1 historical; only explicitly named supplement_v2 figures represent new requests.',
             'request_attempts': calls, 'model_requests_by_report_generator': 0,
             'input_sha256': dict(INPUTS), 'recorded_commands': commands}
    outputs['current_run_index.json'] = index
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-only', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    if args.snapshot_only:
        result = snapshot()
        print(json.dumps({'snapshot': str(HIST), 'verified_files': len(result['files']), 'reports_refreshed': False}))
        return
    outputs = build()
    if args.check_only:
        print(json.dumps({'status': 'report_render_checked_without_writes', 'outputs': list(outputs),
                          'input_files': len(INPUTS), 'requests': outputs['budget.json']['attempts_recorded']}))
        return
    snapshot()
    snapshot_legacy_metadata()
    for name, value in outputs.items():
        save(name, value)
    save('report_generation.json', {'status': 'completed', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
         'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
         'script_sha256': sha(__file__), 'dispatcher_sha256': sha(ROOT / 'scripts/cce_report.py'),
         'inputs': dict(INPUTS), 'outputs': {name: sha(OUT / name) for name in outputs},
         'new_model_requests': 0, 'old_result_batches_modified': False})
    print(json.dumps({'status': 'supplement_v2_reports_refreshed', 'outputs': len(outputs),
                      'request_attempts_in_ledger': outputs['budget.json']['attempts_recorded'], 'new_model_requests': 0}))


if __name__ == '__main__':
    main()
