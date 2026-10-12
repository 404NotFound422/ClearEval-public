"""Task-only metadata prescreen, without reading any model answer or score."""
import collections
import csv
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/cce_validation'
QUESTIONS = ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
REFS = BASE/'reference_recovery/supplement_bound/references_supplement_v2.json'
IDS = BASE/'human_review/private/identity_manifest.csv'
OUT = BASE/'controls/whole_brain_task_prescreen'


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def rawsha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def read(p):
    return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))


def spans(text, patterns):
    parts = []
    for m in re.finditer(r'[^。；\n]+[。；]?', text):
        if any(re.search(p, m.group()) for p in patterns):
            parts.append({'start': m.start(), 'end': m.end(), 'quote': m.group()})
    return parts


def main():
    questions = read(QUESTIONS)
    refs = read(REFS)['references']
    identities = list(csv.DictReader(IDS.open(encoding='utf-8-sig')))
    holdout = {int(r['question_id']) for r in identities if r['split'] == 'audit_holdout'}
    dev = {int(r['question_id']) for r in identities if r['split'] == 'audit_dev'}
    by_qid = {int(q['question_id']): q for q in questions}
    def metadata_group(q):
        m = q['tissue_hierarchy_from_tissue_xlsx']
        return 'metadata_group:' + m.get('tissue_tier_code', '') + '|' + m.get('tissue_inferred', '')
    held_groups = {metadata_group(by_qid[qid]) for qid in holdout}
    protected_same_group = {int(q['question_id']) for q in questions if metadata_group(q) in held_groups}
    whole_refs = [r for r in refs if r['applicability']['tissue'] == 'fixed adult whole brain']
    assert len(whole_refs) == 2
    # All selection conditions are task/source metadata, never generated routes or scores.
    rows = []
    for q in questions:
        if q['tissue_hierarchy_from_tissue_xlsx'].get('tissue_tier_code') != 'T04_WHOLE_MOUSE_BRAIN_5_12MM':
            continue
        qid = int(q['question_id'])
        if qid in holdout:
            rows.append({'question_id': qid, 'status': 'excluded_fixed_holdout', 'formal_eligible': False})
            continue
        if qid in protected_same_group:
            rows.append({'question_id': qid, 'status': 'excluded_holdout_metadata_family', 'formal_eligible': False})
            continue
        text = q['question']
        fixed = bool(re.search(r'已(?:完成[^。；\n]{0,22})?固定|已完成[^。；\n]{0,22}后固定', text))
        is_block = bool(re.search(r'脑组织块|脑胶质瘤组织块|脑肿瘤组织块', text))
        whole = bool(re.search(r'全脑|(?<!完)整脑|完整(?:的)?(?:成年)?(?:小鼠)?(?:大脑|脑组织)', text)) and not is_block
        localized_tumor = '脑胶质瘤组织' in text and not whole
        native = '内源' in text
        troubleshooting = '修正' in text or '失败' in text
        same_scope = '仅列出透明处理' in text and 'RI' in text and '保存' in text
        gaps = ['Actual selected labeling strategy and method-target-fluorophore applicability are not established by task metadata.',
                'No complete second route or expert applicability has been confirmed for this task.']
        if '成年' not in text:
            gaps.append('Adult age is not explicit in the task; the source adult-brain class is not automatically an exact age binding.')
        if qid in dev:
            status = 'existing_development_task_not_new'
        elif is_block:
            status = 'brain_block_not_direct_whole_brain_schedule'
            gaps.append('The T04 tier includes blocks; whole-brain source timings cannot be copied solely because the tier matches.')
        elif localized_tumor:
            status = 'complete_tumor_is_not_explicit_complete_brain'
            gaps.append('The task says complete glioma tissue, not a complete brain; the substring inside the Chinese phrase is not whole-brain evidence.')
        elif not fixed:
            status = 'initial_fixation_not_explicit'
            gaps.append('Post-fixation source entry conditions are not explicitly supplied.')
        elif troubleshooting:
            status = 'prior_treatment_state_requires_resolution'
            gaps.append('Task contains a prior failed treatment; restarting from fixed tissue versus rescuing already treated tissue must be resolved.')
        elif native:
            status = 'native_signal_constraint_requires_route_specific_evidence'
            gaps.append('Native reporter preservation is distinct from antibody amplification; iDISCO+ cannot be promoted from immunolabel evidence alone.')
        elif whole and same_scope:
            status = 'fixed_whole_brain_clearing_scope_candidate_labels_pending'
        else:
            status = 'task_scope_or_sample_boundary_requires_review'
        rows.append({'question_id': qid, 'question_sha256': rawsha(text),
            'status': status, 'existing_development': qid in dev,
            'tissue_metadata': q['tissue_hierarchy_from_tissue_xlsx'],
            'metadata_family': metadata_group(q), 'adult_age_explicit': '成年' in text,
            'task_marker_targets': [t['marker_name'] for t in q['marker_query_targets']],
            'task_target_paths': sorted({t.get('query_path', '') for t in q['marker_query_targets']}),
            'initial_fixation_explicit': fixed, 'whole_brain_scope_explicit': whole,
            'brain_block_explicit': is_block, 'localized_tumor_not_whole_brain': localized_tumor,
            'native_reporter_constraint_present': native,
            'prior_treatment_or_troubleshooting': troubleshooting,
            'requested_clearing_RI_storage_only': same_scope,
            'task_evidence': spans(text, [r'样本', r'已固定', r'已完成', r'内源', r'仅列出透明处理']),
            'possible_source_scope_only': [r['reference_id'] for r in whole_refs] if whole and fixed else [],
            'source_scope_match_is_not_complete_route_compatibility': True,
            'missing_evidence': gaps, 'confirmed_route_pairs': 0, 'formal_eligible': False})
    assert not any(r['question_id'] in holdout and 'task_evidence' in r for r in rows)
    first = sorted(r['question_id'] for r in rows if r['status'] == 'fixed_whole_brain_clearing_scope_candidate_labels_pending')
    by_status = collections.defaultdict(list)
    for row in rows:
        by_status[row['status']].append(row['question_id'])
    report = {'scope': 'metadata-only prescreen for future different-task alternative-route discovery; not scored cases or confirmed compatibility',
        'questions_screened_by_existing_tier': len(rows), 'source_reference_candidates': [r['reference_id'] for r in whole_refs],
        'selection_rule': 'All historical T04 tasks, ascending qid; exclude fixed holdout; distinguish actual whole brain from blocks; explicit fixation and requested scope; classify prior treatment and native-reporter requirements before any answer/score read.',
        'no_model_answer_files_read': True, 'no_score_files_read': True, 'holdout_answers_read': 0,
        'fixed_holdout_question_ids_excluded': sorted(holdout), 'original_20_answer_selection_changed': False,
        'new_model_requests': 0, 'new_expert_labels': 0, 'confirmed_eligible_route_pairs': 0,
        'initial_scope_candidates_before_label_applicability_review': first,
        'status_question_ids': dict(by_status),
        'not_independent_family_claim': 'Distinct qids may be related variants: q1/3/4 activation, q13–16 amyloid, q157–160 circuit, q189–192 metastasis. Existing tissue groups/source families, not qid count alone, determine dependence.',
        'next_safe_action': 'Bind source evidence for the selected task target/label constraints, then inspect archived declared routes without selecting on scores. Do not append new qids to the frozen references or call models until input/scope/matrix are separately frozen.',
        'source_task_scope_consistency': [{'reference_id': r['reference_id'], 'source_scope': r['source_scope'],
            'endpoint_scope': r['applicability']['endpoint_scope'], 'outcomes_pending': r['applicability']['outcomes_pending'],
            'human_confirmation': r['human_confirmation'], 'formal_eligible': r['formal_eligible']} for r in refs],
        'inputs': [{'path': str(p.resolve()), 'sha256': sha(p)} for p in [QUESTIONS, REFS, IDS, pathlib.Path(__file__)]],
        'rows': rows, 'actual_command': {'executable': sys.executable, 'argv': sys.argv}}
    # Source-text keyword locations are leads only: they do not establish a
    # compatible protocol, and a negative lexical search is not scientific refutation.
    source_root = ROOT.parent/'literature/tissue_optical_clearing/fulltext_txt'
    leads = []
    for prefix in ['005_', '009_', '011_', '015_', '019_', '022_', '040_']:
        for source in sorted(source_root.glob(prefix+'*.txt')):
            source_text = source.read_text(encoding='utf-8-sig')
            pattern = re.compile(r'amyloid|5xFAD|6E10|Congo|immediate.early|c.?fos', re.I)
            hits = [{'line_one_based': i, 'keywords': sorted(set(m.group() for m in pattern.finditer(line)))}
                    for i,line in enumerate(source_text.splitlines(), 1) if pattern.search(line)]
            amyloid_lines = [h for h in hits if any(re.search(r'amyloid|5xFAD|6E10|Congo', k, re.I) for k in h['keywords'])]
            leads.append({'path': str(source.resolve()), 'sha256': sha(source),
                'amyloid_keyword_line_count': len(amyloid_lines), 'keyword_locations': hits,
                'status': 'keyword_pointer_only_not_task_applicability_or_complete_reference'})
    report['source_keyword_location_leads'] = leads
    report['candidate_specific_next_sources'] = {
        'q1': '2016 iDISCO+ paper directly concerns immediate-early-gene activity mapping; confirm the exact selected target/label branch and obtain a complete compatible second route before any paired claim.',
        'q13_q14_q15': 'Whole-brain size alone cannot transfer FDISCO/PEGASOS/iDISCO applicability. Check disease/amyloid-specific sources: local ScaleS 2015, SOLID 2024 and CUBIC-HV 2020 keyword locations are search leads only; no new route is reconstructed here.'}
    OUT.mkdir(parents=True, exist_ok=True)
    protection = {'scope': 'protective task/source-family exclusion using metadata only; no answer or score inspected',
        'candidate_question_ids': first,
        'candidate_identity_overlap_with_fixed_holdout': sorted(set(first) & holdout),
        'candidate_metadata_family_overlap_with_fixed_holdout': sorted({metadata_group(by_qid[q]) for q in first} & held_groups),
        'allowed_for_further_development_metadata_and_source_binding': first,
        'not_permission_to_run_judges_or_claim_compatible_routes': True,
        'fixed_holdout_must_remain_unexposed': [{k:r[k] for k in ['answer_id','question_id','task_family_id','source_family_id']}
            for r in identities if r['split'] == 'audit_holdout'],
        'all_question_ids_sharing_fixed_holdout_metadata_families_protected': sorted(protected_same_group),
        'candidate_development_exposure': [{'question_id': q, 'metadata_family': metadata_group(by_qid[q]),
            'already_excluded_from_holdout_by_original_brain_group_rule': True,
            'prospective_source_papers': ['10.1126/sciadv.aau8355','10.1038/s41422-018-0049-z','10.1016/j.cell.2016.05.007'],
            'source_binding_status': 'candidate_only_not_confirmed'} for q in first],
        'source_family_independence_confirmed': False,
        'reason': 'All 15 saved holdout source_family_id values are unmapped. Different tissue metadata groups are protective strata, not proof of source-paper independence. If a later holdout reference uses any development-exposed paper, flag that family collision before analysis; do not inspect or adapt on its answer now.',
        'original_selection_and_labels_changed': False, 'new_model_requests': 0, 'new_expert_labels': 0,
        'inputs': report['inputs']}
    assert not protection['candidate_identity_overlap_with_fixed_holdout']
    assert not protection['candidate_metadata_family_overlap_with_fixed_holdout']
    (OUT/'holdout_protection.json').write_text(json.dumps(protection,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report['holdout_protection'] = {'path': str((OUT/'holdout_protection.json').resolve()),
        'sha256': sha(OUT/'holdout_protection.json'), 'source_family_independence_confirmed': False}
    (OUT/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# 额外整脑任务的预先条件筛查', '',
        '只读取历史题干、组织/marker 元数据和既有参考范围，不读取模型答案或分数，不增加人工 20 份，未生成新 protocol。全体候选均未确认完整路线适用，合格替代路线对仍为 0。', '',
        '固定规则为：T04 历史题目全取，排除固定留出，按题号排序；区分整脑与脑块、固定状态、原生报告信号和失败处理后的初始状态。T04 标签本身不足以证明整脑来源适用。', '',
        '**样本与输出范围可先进入后续来源绑定、但标记适用仍待核：** '+', '.join('q'+str(q) for q in first)+'。这不是“已明确科学相容”的标签。', '',
        '| 状态 | 题号 |','|---|---|']
    lines += ['| '+k+' | '+', '.join('q'+str(q) for q in v)+' |' for k,v in by_status.items()]
    lines += ['', 'q1/3/4、q13–16、q157–160、q189–192 分别含相关任务变体，不能将题号数当成独立任务/来源家族数。当前 q21/22/23 的 6 对仅覆盖 3 个题目。未来新增候选需要按任务独立记录，不能仅靠增加生成模型重复凑成 6–8 个不同任务。', '',
        '后续优先：q1 可先绑定 2016 iDISCO+ 的 IEG 任务证据，但仍需第二条完整相容路线；q13–15 不能仅凭整脑尺度继承现有 FDISCO/PEGASOS。JSON 记录了本地 iDISCO 2014、PEGASOS 2018、FDISCO 2019、ScaleS 2015、SOLID 2024、iDISCO+ 2016、CUBIC-HV 2020 的疾病/marker 关键词位置和源散列。ScaleS/SOLID/CUBIC-HV 只作为 amyloid 来源定位线索；词命中不等于该任务实验支持，未命中也不是科学反证。', '',
        'q1、q13、q14、q15 与固定 15 份留出的题号和现有 metadata family 均无重叠，属于原先已排除留出的整脑开发范围，可继续做开发来源绑定。必须保持未暴露的 15 个题号为：'+', '.join('q'+str(q) for q in sorted(holdout))+'；同 metadata family 的其他题目也保护性排除。全部 15 份 source_family 仍为 unmapped，故不能宣称与新来源独立；将来若绑定同一篇开发来源，应先标明家族暴露冲突。细表见 [holdout_protection.json](holdout_protection.json)。', '',
        '现有 FDISCO/PEGASOS 四分支的 endpoint_scope 一致：clearing/RI matching/storage only，标记准备不计步骤。因此 q2 的同范围 iDISCO+ clearing-only 候选可保持评价范围一致；但这不确认其标记适用或预先免疫状态。q248 及其他硬性原生报告信号任务不能从免疫放大来源直接推定 iDISCO+ 满足原生保留要求。', '',
        '下一步先绑定任务标签/目标与具体来源，再查看已有声明路线；本次不把预筛候选加入冻结参考 question_ids，不运行分数，不改留出。完整题干 hash、原文位置、逐题未决项和实际命令见 [audit.json](audit.json)。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'metadata_tasks':len(rows),'initial_scope_candidates':first,'confirmed_pairs':0,'new_model_requests':0}))


if __name__ == '__main__':
    main()
