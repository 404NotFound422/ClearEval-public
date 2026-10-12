"""Prepare/preflight the fixed fifteen holdout inputs without generation.

Answer and prompt text remain in sealed execution files. Console and public
readiness records contain only identities/hashes, counts and reason categories.
The original cce_judges runner is the separately invoked execution entry.
"""
from __future__ import annotations
import argparse
import contextlib
import csv
import io
import json
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
import cce_judges as judges
import cce_extraction_dev_v2 as dev

BASE = ROOT / 'artifacts/cce_validation'
HUMAN = BASE / 'human_review'
OUT = BASE / 'judges/local_extraction_holdout_v1'
SEALED = OUT / 'sealed'
RUN = SEALED / 'run'
LEDGER = BASE / 'judges/request_ledger.jsonl'
REFERENCES = BASE / 'expanded_tasks_v4/references.json'
TASK = ROOT.parent / 'ClearEval_Codex_Experiments_v1_20261008'
EXPECTED_CONTRACT = 'c27211dc7513d3ac24ee211ce3950eb1a1d0b553e87b0374b93190fc7dfe56ae'
PY = ROOT.parent / 'review_artifacts/bioprobench_2026-09-29/python_portable/python.exe'


def require(ok, category):
    if not ok: raise ValueError(category)


def binding(path):
    return {'path': str(Path(path).resolve()), 'sha256': judges.filehash(path)}


def save(name, obj):
    judges.save(OUT / name, obj)


def csvread(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def rawsha(text):
    return dev.rawsha(text)


def started_count():
    return sum(r.get('event') == 'request_started' for r in judges.ledger_rows(LEDGER))


def source_excerpt(filename, quote):
    path = TASK / filename; text = path.read_text(encoding='utf-8')
    start = text.index(quote)
    return {'source': binding(path), 'start_codepoint': start, 'end_codepoint': start + len(quote), 'quote': quote}


def command_arguments(command):
    return ['scripts/cce_judges.py', command,
        '--cases', str((SEALED / 'cases.json').relative_to(ROOT)).replace('\\', '/'),
        '--out', str(RUN.relative_to(ROOT)).replace('\\', '/'),
        '--model-config', str((OUT / 'local_config_snapshot.json').relative_to(ROOT)).replace('\\', '/'),
        '--models', 'local_qwen3_8b', '--repeats', '1', '--temperature', '0',
        '--max-output-tokens', '8192', '--max-attempts', '1', '--max-calls', '15', '--timeout-seconds', '600',
        '--ledger', str(LEDGER.relative_to(ROOT)).replace('\\', '/'), '--total-budget', '300'] + (['--allow-api'] if command == 'run' else [])


def runner_args():
    return types.SimpleNamespace(cases=SEALED / 'cases.json', out=RUN,
        model_config=OUT / 'local_config_snapshot.json', models=['local_qwen3_8b'],
        question_file=judges.HIST, demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json', demand_manifest=None,
        ledger=LEDGER, total_budget=300, external_request_count=0, max_calls=15, max_attempts=1, repeats=1,
        temperature=0.0, max_output_tokens=8192, timeout_seconds=600, allow_api=False)


def validate_frozen():
    plan = judges.read(OUT / 'plan.json')
    for record in plan['frozen_files']:
        require(judges.filehash(record['path']) == record['sha256'], 'frozen_input_changed')
    require(judges.digest(judges.read(OUT / 'frozen_judge_contract.json')) == EXPECTED_CONTRACT, 'judge_contract_changed')
    return plan


def prepare():
    OUT.mkdir(parents=True, exist_ok=True); SEALED.mkdir(exist_ok=True)
    if (OUT / 'plan.json').exists():
        plan = validate_frozen()
        print(judges.canonical({'status': 'reused_frozen_preparation', 'selected': 15, 'ready': plan['ready_cells'], 'blocked': plan['blocked_cells'], 'new_requests': 0}))
        return
    require(not list(RUN.glob('attempts/*/request_receipt.json')), 'existing_requests_prevent_prepare')
    selection = judges.read(HUMAN / 'selection.json')
    held = [r for r in selection['selection'] if r['split'] == 'audit_holdout']
    require(len(held) == 15 and len({r['answer_id'] for r in held}) == 15, 'fixed_holdout_selection_invalid')
    require(sum(r['split'] == 'audit_dev' for r in selection['selection']) == 5, 'fixed_development_selection_invalid')
    identities = csvread(HUMAN / 'private/identity_manifest.csv')
    identity_map = {r['natural_answer_id']: r for r in identities}
    require(len(identity_map) == 20, 'identity_manifest_invalid')
    require(set(identity_map) == {r['answer_id'] for r in selection['selection']}, 'selection_natural_identity_mapping_changed')
    expert_rows = csvread(HUMAN / 'reviewer/review_items.csv')
    expert_labels = sum(bool(r.get('expert_decision', '').strip()) for r in expert_rows)
    development = judges.read(HUMAN / 'rescoring/v4_dev_v2/summary.json')
    identity_check = judges.read(HUMAN / 'rescoring/v4_dev_v2/five_answer_identity_verification.json')
    require(development['actual_auto_records'] == 5 and development['guarded_identity_replay_pass'] == 5 and identity_check['status'] == 'pass' and len(identity_check['checks']) == 5, 'development_stage_not_complete')
    runner, registry, contract, settings = dev.frozen_runtime()
    require(judges.digest(contract) == EXPECTED_CONTRACT, 'original_qwen_contract_changed')
    require(settings['max_output_tokens'] == 8192 and settings['num_ctx'] == 40960 and settings['temperature'] == 0, 'model_configuration_changed')
    refs = judges.read(REFERENCES)['references']
    local = judges.read(dev.SOURCE / 'local_config_snapshot.json')
    qwen = next(m for m in local['models'] if m['name'] == 'local_qwen3_8b')
    selected_ids = [identity_map[r['answer_id']]['answer_id'] for r in held]
    source_unmapped = sum(r.get('source_family_id') in [None, '', 'UNKNOWN', 'UNMAPPED'] or 'unmapped' in str(r.get('source_family_id', '')).lower() or 'unknown' in str(r.get('source_family_id', '')).lower() for r in held)
    require(source_unmapped == 15, 'source_family_metadata_changed')
    holdout_identities, ready, matrix, context, steps = [], [], [], [], []
    source_bindings = {}
    archive_cache = {}
    zero_ref_cells = 0
    for selected in held:
        row = identity_map[selected['answer_id']]; aid = row['answer_id']; reason = None
        require(row['split'] == 'audit_holdout' and str(row['question_id']) == str(selected['question_id']) and row['model_name'] == selected['model_name'], 'fixed_selection_identity_mismatch')
        holdout_identities.append(row)
        cid = aid + '__audit_holdout_baseline_v1'
        covered = [r for r in refs if int(row['question_id']) in r.get('question_ids', [])]
        if covered: reason = 'unexpected_current_reference_coverage'
        else: zero_ref_cells += 1
        ap = Path(row['response_path'])
        source_bindings[str(ap)] = binding(ap)
        if judges.filehash(ap) != row['response_file_sha256']: reason = reason or 'archive_hash_mismatch'
        if str(ap) not in archive_cache: archive_cache[str(ap)] = judges.read(ap)
        matches = [r for r in archive_cache[str(ap)] if str(r.get('question_id')) == row['question_id']]
        if len(matches) != 1:
            reason = reason or ('answer_missing' if not matches else 'duplicate_answer_identity')
            answer = None
        else: answer = matches[0]
        if answer is not None:
            if rawsha(answer['model_response']) != row['answer_sha256']: reason = reason or 'answer_hash_mismatch'
            if rawsha(answer['specific_question']) != row['question_sha256']: reason = reason or 'question_hash_mismatch'
            try: registry.get(int(row['question_id']), answer['specific_question'])
            except Exception: reason = reason or 'historical_question_snapshot_mismatch'
        case = None; bound = None; prompt_hash = None
        if answer is not None and reason is None:
            case = {'case_id': cid, 'base_id': aid, 'anonymous_answer_id': aid, 'split': 'audit_holdout',
                'condition': 'baseline', 'question_id': int(row['question_id']),
                'specific_question': answer['specific_question'], 'model_response': answer['model_response'],
                'answer_sha256': row['answer_sha256'], 'question_sha256': row['question_sha256'], 'references': [],
                'formal_eligible': False, 'expert_confirmation': None,
                'scope': 'fixed_holdout_auto_only_sealed_no_tuning_no_synthetic_faithful_correction'}
            prompt = dev.capture(runner, case)
            bound = len(prompt.encode('utf-8')) + 8192 + 256
            prompt_hash = rawsha(prompt)
            if bound > 40960: reason = 'conservative_context_bound_exceeded'
            context.append({'answer_id': aid, 'prompt_raw_utf8_sha256': prompt_hash, 'prompt_utf8_bytes': len(prompt.encode('utf-8')),
                'conservative_context_bound': bound, 'configured_num_ctx': 40960, 'max_output_tokens': 8192, 'template_reserve': 256, 'fits': bound <= 40960})
        input_hash = judges.digest({'question': case['specific_question'], 'question_id': case['question_id'], 'protocol': case['model_response'], 'references': []}) if case else None
        identity = {'case_id': cid, 'input_sha256': input_hash, 'judge': 'local_qwen3_8b', 'repeat_index': 0, 'contract_sha256': EXPECTED_CONTRACT} if case else None
        if reason is None:
            ready.append(case)
            steps.append({'case_id': cid, 'input_sha256': row['answer_sha256'], 'sr': None, 'sp': None, 'reference_id': None,
                'step_config_sha256': judges.digest({'current_references': judges.filehash(REFERENCES), 'applicable_reference_count': 0, 'matching_run': False}),
                'status': 'not_scored_reference_insufficient', 'Com': None, 'IA': None, 'HV': None,
                'reason': 'Current frozen v4 reference collection has no branch for this fixed question; no step matching run or new reference added.'})
        matrix.append({'answer_id': aid, 'case_id': cid, 'split': 'audit_holdout', 'status': 'ready_not_run' if reason is None else 'pending_blocked',
            'reason_category': reason, 'answer_raw_utf8_sha256': row['answer_sha256'], 'question_raw_utf8_sha256': row['question_sha256'],
            'input_sha256': input_hash, 'planned_trial_id': judges.digest(identity) if identity else None,
            'references_sha256': judges.digest([]), 'applicable_current_reference_count': len(covered), 'conservative_context_bound': bound,
            'judge': 'local_qwen3_8b', 'repeat_index': 0, 'max_attempts': 1, 'source_family_id': row.get('source_family_id'),
            'expert_confirmation': None, 'formal_eligible': False})
    require([r['answer_id'] for r in holdout_identities] == selected_ids, 'holdout_order_changed')
    save('sealed/cases.json', {'cases': ready})
    save('sealed/step_availability.json', steps)
    buffer = io.StringIO(newline=''); writer = csv.DictWriter(buffer, fieldnames=list(identities[0])); writer.writeheader(); writer.writerows(holdout_identities)
    (SEALED / 'identity_manifest.csv').write_text(buffer.getvalue(), encoding='utf-8-sig')
    save('sealed/source_bindings.json', list(source_bindings.values()))
    save('local_config_snapshot.json', {'models': [qwen]})
    save('frozen_judge_contract.json', contract)
    save('offline_context_preflight.json', {'checks': context, 'all_checked_fit': all(r['fits'] for r in context), 'new_model_requests': 0})
    save('reference_coverage.json', {'current_reference_file': binding(REFERENCES), 'selected_cells': 15, 'zero_applicable_reference_cells': zero_ref_cells,
        'reference_context': [], 'references_added': 0, 'step_matching_run': False, 'SR_SP_Com_IA_HV': 'not_scored_NA_due_to_reference_insufficient'})
    readiness = {'status': 'development_processed_configuration_frozen_holdout_auto_may_be_prepared',
        'actual_development_auto_records': 5, 'development_guarded_identity_pass': True,
        'expert_labels_current': expert_labels, 'expert_confirmation_required_for_scientific_claims': True,
        'interpretation': 'The package requires development before freezing and running holdout; it does not state an expert-return prerequisite for automatic processing. Expert review remains pending and separate.',
        'source_excerpts': [source_excerpt('HUMAN_REVIEW.md', '先处理 5 份开发，固定配置，再运行并审阅 15 份留出。'),
            source_excerpt('HUMAN_REVIEW.md', '机器建议不预填到专家结论栏，未填写不等于认可。'),
            source_excerpt('EXPERIMENT_DESIGN.md', '人工未返回时继续完成已有条件支持的计算；计算完成与人工确认分别记录。'),
            source_excerpt('EXPERIMENT_DESIGN.md', '若修改配置需要使用留出标签，原留出组改为开发/适配材料，保留修改前输出。')],
        'assisted_expert_review_not_independent_blind_expert_rating': True,
        'task_family_overlap': bool({r['task_family_id'] for r in held} & {r['task_family_id'] for r in selection['selection'] if r['split'] == 'audit_dev'}),
        'source_families_unmapped': 15, 'independent_source_family_holdout_established': False,
        'new_model_requests': 0, 'expert_labels_added': 0}
    save('workflow_readiness.json', readiness)
    files = [HUMAN / 'selection.json', HUMAN / 'private/identity_manifest.csv', HUMAN / 'rescoring/v4_dev_v2/summary.json',
        HUMAN / 'rescoring/v4_dev_v2/five_answer_identity_verification.json', REFERENCES, Path(__file__),
        ROOT / 'scripts/cce_rescore_extractions.py', ROOT / 'scripts/cce_extraction_dev_v2.py',
        TASK / 'HUMAN_REVIEW.md', TASK / 'EXPERIMENT_DESIGN.md']
    files += [OUT / f for f in ['sealed/cases.json', 'sealed/step_availability.json', 'sealed/identity_manifest.csv', 'sealed/source_bindings.json',
        'local_config_snapshot.json', 'frozen_judge_contract.json', 'offline_context_preflight.json', 'reference_coverage.json', 'workflow_readiness.json']]
    files += [Path(p) for p in source_bindings]
    before = started_count()
    plan = {'status': 'prepared_not_run', 'selected_cells': 15, 'ready_cells': len(ready), 'blocked_cells': 15-len(ready),
        'matrix': matrix, 'fixed_selection_unchanged': True, 'selection_uses_new_answers_or_scores': False,
        'judge_contract_sha256': EXPECTED_CONTRACT, 'judge': 'local_qwen3_8b', 'repeats': 1, 'repeat_index': 0, 'max_attempts': 1,
        'max_calls': 15, 'temperature': 0, 'max_output_tokens': 8192, 'num_ctx': 40960, 'timeout_seconds': 600,
        'package_request_count_at_preparation': before, 'expected_package_count_if_all_ready_attempted': before+len(ready), 'package_total_budget': 300,
        'planned_new_requests': len(ready), 'new_requests_during_preparation': 0, 'historical_trial_reuse': 0,
        'reference_context': [], 'references_added': 0, 'source_families_unmapped': 15, 'source_family_independence_confirmed': False,
        'public_reporting': 'completion/failure/NA reason categories and metadata only; no answer text, extracted field values or scores used for tuning',
        'sealed_storage': 'Local filesystem separation and process policy, not encryption or an access-control guarantee. Raw provider returns remain for expert attachments.',
        'expert_review_mode': 'ASSISTED; machine suggestions are not expert conclusions; original task/text should be read first',
        'expert_labels_added': 0, 'formal_eligible': False, 'faithful_corrections_created': 0,
        'guarded_bridge_policy': 'Reuse unchanged cce_rescore_extractions.py only after actual returns, for auto identity binding. Real expert review/corrections are required for any faithful impact; no pending item becomes zero.',
        'blocked_cell_policy': 'Keep every selected cell; do not truncate text, alter configuration, replace answers or tune from holdout results.',
        'frozen_files': [binding(p) for p in files]}
    save('plan.json', plan)
    save('execution_commands.json', {'python': str(PY), 'working_directory': str(ROOT), 'new_requests': 0,
        'actually_executed': [{'stage': 'prepare', 'argv': ['scripts/cce_extraction_holdout_v1.py', 'prepare'], 'model_requests': 0}],
        'planned_not_executed': {'preflight': ['scripts/cce_extraction_holdout_v1.py', 'preflight'], 'run': command_arguments('run')},
        'sealed_runtime_directory': str(RUN), 'no_raw_outputs_in_public_log': True})
    (OUT / 'README.md').write_text('''# 固定15份留出：仅自动提取盲处理准备

名单与顺序来自既有 audit_holdout，未改样本、原文、量表、需求、EGES或Qwen配置。先前5份开发已真实自动处理并完成identity核对；专家仍未回传，自动处理不冒充专家确认。

完整题干/答案仅由代码为传输读取，不在对话或公开日志展示，也不据此调参。当前v4参考对这些题号无覆盖，明确 references=[]，不新增来源，SR/SP/Com/IA/HV为未评分NA。15份来源家族仍未映射，不能称来源独立。

sealed目录存放执行输入及未来原始输出，采用本地目录和流程隔离，不声称已加密。只公开完成/失败/NA原因类别与元数据。以后给同一专家的附件可含原文和真实自动建议，但不得预填专家结论，也不展示模型或最终分数。审阅模式仍为ASSISTED，不称独立盲评。

预设15×1、repeat0、attempt1、最多15次；原Qwen合同、temperature0、8192输出、40960上下文不变。无法精确绑定或超上下文的单元保持pending，不截断或更换答案。当前仅prepare/preflight，不发生成请求。

参见 [冻结计划](plan.json)、[流程原句与就绪依据](workflow_readiness.json)、[参考覆盖](reference_coverage.json)、[上下文检查](offline_context_preflight.json)及[实际/待执行命令](execution_commands.json)。原20份人工名额、160项专家表和5+15划分不变；不创建faithful correction。
''', encoding='utf-8')
    validate_frozen()
    print(judges.canonical({'status': 'prepared_not_run', 'selected': 15, 'ready': len(ready), 'blocked': 15-len(ready),
        'zero_reference_cells': zero_ref_cells, 'context_bound_min': min((r['conservative_context_bound'] for r in context), default=None),
        'context_bound_max': max((r['conservative_context_bound'] for r in context), default=None),
        'package_requests_at_preparation': before, 'planned_new_requests': len(ready), 'new_requests': 0}))


def preflight():
    plan = validate_frozen()
    if not plan['ready_cells']:
        save('preflight_verification.json', {'status': 'no_ready_cells', 'selected': 15, 'ready': 0, 'new_requests': 0}); return
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, _, _, _, cases, contract = judges.preflight(runner_args())
    require(judges.digest(contract) == EXPECTED_CONTRACT, 'live_contract_mismatch')
    require(contract == judges.read(OUT / 'frozen_judge_contract.json'), 'live_contract_mismatch')
    require(len(cases) == plan['ready_cells'] and all(c['references'] == [] for c in cases), 'ready_matrix_mismatch')
    count = started_count()
    result = {'status': 'ready' if plan['blocked_cells'] == 0 else 'ready_subset_with_preserved_pending_cells',
        'selected': 15, 'ready': len(cases), 'blocked': plan['blocked_cells'], 'actual_contract_sha256': EXPECTED_CONTRACT,
        'same_original_Qwen_prompt_model_schema_EGES_contract': True, 'all_ready_context_checks_pass': True,
        'source_family_independence_confirmed': False, 'reference_context': [],
        'package_requests_at_preflight': count, 'planned_maximum_new_requests': len(cases), 'expected_package_count_if_attempted_now': count+len(cases),
        'live_read_only_service_checks': ['/api/tags', '/api/version'], 'model_generation_requests': 0,
        'expert_labels_added': 0, 'formal_eligible': False}
    save('preflight_verification.json', result)
    log = judges.read(OUT / 'execution_commands.json')
    log['actually_executed'].append({'stage': 'preflight', 'argv': ['scripts/cce_extraction_holdout_v1.py', 'preflight'], 'model_requests': 0})
    log['planned_not_executed'].pop('preflight', None)
    save('execution_commands.json', log)
    print(judges.canonical(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'preflight'])
    args = parser.parse_args()
    try:
        {'prepare': prepare, 'preflight': preflight}[args.command]()
    except Exception as exc:
        # No exception text/answer/field/score is emitted into public logs.
        category = str(exc) if isinstance(exc, ValueError) and str(exc).replace('_', '').isalnum() else 'internal_preparation_or_preflight_error'
        save('preparation_failure.json', {'status': 'blocked_without_generation', 'stage': args.command, 'category': category,
            'exception_type': type(exc).__name__, 'new_model_requests': 0})
        print(judges.canonical({'status': 'blocked_without_generation', 'category': category, 'new_model_requests': 0}))
        sys.exit(1)
