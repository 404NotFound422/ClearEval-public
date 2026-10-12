"""Offline, fixed-cohort E5 analysis; no model, converter, or embedding calls.

Reads metadata and committed numerical outputs only. Answer/prompt/raw files are
hashed for provenance without decoding their scientific content. The original
common_summary performs joint common-task aggregation and 3-D Pareto comparison.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import numpy as np
import cce_analysis as original
import cce_grounded_offline_scoring_v1 as numeric

R2 = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010'
SELECTION = R2 / 'secondary_E5_coverage_selection_v1/selection_metadata.json'
ADDENDUM = SELECTION.with_name('resampling_addendum.md')
FIRST = R2 / 'generation_confirmation_v2'
SECOND = R2 / 'secondary_E5_confirmation_v1'
STEPS = ROOT / 'artifacts/cce_validation/method_family_steps_v1'
FIXED_SELECTION_SHA = 'f15323d7699dcdedeaa9f210447b2f23ffc73b9f9e68095a96f8a436e21a3393'
MODELS = ['openai_qwen3-14b', 'openai_qwen3-32b']
QIDS = [1, 2, 21, 22, 248]
REPEATS, SEED = 2000, 20261010
TERMINAL = {'success', 'partial_components', 'failed'}
METRICS = list(numeric.METRICS)
JOINT = list(original.SUMMARY_METRICS)
SCOPE = 'secondary_coverage_directed_previously_exposed_tasks_conditional_references'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')


def csvwrite(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False, separators=(',', ':'))
                if isinstance(v, (dict, list)) else v for k, v in row.items()})


def verify_bindings(records):
    for record in records:
        require(sha(record['path']) == record['sha256'], 'BOUND_FILE_CHANGED:' + record['path'])


def fixed_metadata():
    require(sha(SELECTION) == FIXED_SELECTION_SHA, 'FIXED_SELECTION_CHANGED')
    meta = read(SELECTION)
    cohort = meta['fixed_secondary_cohort']
    require(meta['chosen_generator_models'] == MODELS and meta['potential_common_question_ids'] == QIDS,
        'FIXED_MODELS_AND_TASKS')
    require(len(cohort) == 10 and {(r['model'], r['question_id']) for r in cohort}
        == set(itertools.product(MODELS, QIDS)), 'TEN_FIXED_ANSWERS')
    policy = meta['secondary_E5_analysis']
    require(policy['bootstrap']['replicates'] == REPEATS
        and policy['bootstrap']['synchronized_across_models'] is True, 'PRESPECIFIED_BOOTSTRAP')
    # The addendum fixes seed and exact enumeration before export; it is bound in outputs.
    addendum = ADDENDUM.read_text(encoding='utf8')
    require('20261010' in addendum and 'K^K' in addendum, 'PREDECLARED_SEED_AND_EXACT_ENUMERATION')
    verify_bindings(meta['metadata_inputs'])
    return meta


def batch_metadata(folder, expected_ids):
    if not (folder / 'plan.json').exists():
        return None
    plan, matrix, contract = (read(folder / n) for n in ['plan.json', 'matrix.json', 'expected_contract.json'])
    require(plan['ids'] == expected_ids and [r['anonymous_answer_id'] for r in matrix] == expected_ids,
        'BATCH_MATRIX_IDENTITY')
    require(plan['max_attempts'] == 1 and plan['phase'] == 'confirmation', 'ONE_ATTEMPT_CONFIRMATION')
    require(plan['generator'] == 'cce_generation_order_only_v1'
        and plan['processor'] == 'cce_fieldwise_scoring_v3', 'FINAL_GENERATOR_PROCESSOR')
    verify_bindings(plan['frozen_inputs'])
    for row in matrix:
        require(row['planned_trial_id'] == digest(row['identity'])
            and row['identity']['contract_sha256'] == digest(contract), 'TRIAL_CONTRACT_HASH')
    commands = [{'binding': bind(p), 'record': read(p)} for p in sorted((folder / 'run_commands').glob('*.json'))]
    return {'plan': plan, 'matrix': matrix, 'contract': contract,
        'source_batch': str(folder), 'execution_commands': commands,
        'bindings': [bind(folder / n) for n in ['plan.json', 'matrix.json', 'expected_contract.json']]
            + [x['binding'] for x in commands]}


def collect(meta):
    batches = {str(FIRST): batch_metadata(FIRST, ['FPC%02d' % i for i in range(2, 9)]),
               str(SECOND): batch_metadata(SECOND, ['FPC%02d' % i for i in range(9, 17)])}
    available = [b for b in batches.values() if b]
    if len(available) == 2:
        keys = ['files', 'demands', 'source_registry_sha256', 'scoring_version', 'models',
                'prospective_generation_confirmation']
        require(all(available[0]['contract'][k] == available[1]['contract'][k] for k in keys),
            'BATCH_SCIENCE_OR_EVALUATOR_MISMATCH')
    with (STEPS / 't070_per_answer.csv').open(encoding='utf-8-sig', newline='') as stream:
        original_steps = {r['answer_id']: r for r in csv.DictReader(stream)}
    catalog = read(STEPS / 'references.json')['references']
    refs = {r['reference_id']: r for r in catalog}
    rows, evidence = [], []
    for meta_row in meta['fixed_secondary_cohort']:
        aid = meta_row['confirmation_id']
        folder = FIRST if aid in ['FPC03', 'FPC06'] else SECOND
        batch = batches[str(folder)]
        old = original_steps[meta_row['answer_id']]
        require(old['answer_sha256'] == meta_row['answer_sha256']
            and old['question_sha256'] == meta_row['question_sha256']
            and int(old['question_id']) == meta_row['question_id']
            and old['reference_id'] == meta_row['existing_selected_reference_id'], 'ARCHIVED_STEP_IDENTITY:' + aid)
        steps = {'sr': float(old['sr']), 'sp': float(old['sp'])}
        values = numeric.derive({}, steps, False)
        selected = refs[old['reference_id']]
        row = dict(anonymous_answer_id=aid, answer_id=meta_row['answer_id'], model=meta_row['model'],
            generator_model=meta_row['model'], generator_family='Qwen', question_id=meta_row['question_id'],
            answer_sha256=meta_row['answer_sha256'], question_sha256=meta_row['question_sha256'],
            selection_origin=meta_row['selection_origin'], source_batch=str(folder), status='not_prepared',
            actual_request_made=False, terminal=False, identity_eligible=False,
            formal_eligible=False, expert_confirmed=False, reference_id=old['reference_id'],
            family_id=selected.get('family_id'), method_family_id=selected.get('method_family_id'),
            candidate_reference_ids=meta_row['candidate_reference_ids'],
            candidate_source_family_ids=sorted({refs[x]['family_id'] for x in meta_row['candidate_reference_ids']}),
            missing_reason='batch_not_prepared', **values)
        if batch:
            cell = next(r for r in batch['matrix'] if r['anonymous_answer_id'] == aid)
            step = cell['step']
            require(all(step[k] == meta_row[k] for k in ['answer_sha256', 'question_sha256'])
                and step['reference_id'] == old['reference_id']
                and all(step[k] == steps[k] for k in ['sr', 'sp']), 'FROZEN_STEP_IDENTITY:' + aid)
            tid = cell['planned_trial_id']
            at = folder / 'run/attempts' / (tid + '_1')
            tp, rp = folder / 'run/trials' / (tid + '.json'), at / 'request_receipt.json'
            row.update(status='unstarted', missing_reason='no_terminal_yet', trial_id=tid,
                judge=cell['identity']['judge'], input_sha256=cell['identity']['input_sha256'],
                references_sha256=step['references_sha256'], source_document=cell['assets']['source_document'],
                request_payload=cell['assets']['payload'])
            receipt = read(rp) if rp.exists() else None
            if receipt:
                require(receipt['trial_id'] == tid and receipt['attempt'] == 1
                    and receipt['phase'] == 'confirmation' and receipt['model'] == cell['identity']['judge'],
                    'RECEIPT_IDENTITY:' + aid)
                row.update(actual_request_made=True, status='reserved_nonterminal', receipt=bind(rp))
            if tp.exists():
                t = read(tp)
                require(t['status'] in TERMINAL and t['trial_id'] == tid and t['identity'] == cell['identity']
                    and t['anonymous_answer_id'] == aid and t['attempt'] == 1
                    and t['actual_request_made'] is True and receipt is not None
                    and t['request_id'] == receipt['request_id'], 'TERMINAL_IDENTITY:' + aid)
                verify_bindings(t['bound_artifacts'])
                require(set(t['metrics']) == set(METRICS), 'SIXTEEN_METRICS:' + aid)
                require(all(t['metrics'][k] == steps[k] for k in ['sr', 'sp']), 'RAW_SR_SP_CHANGED:' + aid)
                expected = numeric.derive(t['metrics'], steps, t['status'] != 'failed')
                require(all(numeric.same(expected[k], t['metrics'][k]) for k in METRICS), 'ORIGINAL_DERIVED_FORMULA:' + aid)
                row.update(**t['metrics'], status=t['status'], terminal=True, identity_eligible=True,
                    failure_stage=t['failure_stage'], error=t['error'], trial=bind(tp), missing_reason=None)
                raw = at / 'raw_response.txt'
                row['raw_response'] = bind(raw) if raw.exists() else None
                row['raw_response_note'] = 'UTF8 returned response string bytes; not raw HTTP bytes' if raw.exists() else 'no saved model response'
                evidence.extend([bind(tp), *t['bound_artifacts']])
                for k in METRICS:
                    if row[k] is not None:
                        require(original.finite(row[k]), 'NONFINITE_METRIC:' + aid + ':' + k)
        row['complete_CCE'] = all(original.finite(row[k]) for k in JOINT)
        row['missing_metrics'] = [k for k in METRICS if not original.finite(row[k])]
        rows.append(row)
    return rows, catalog, available, evidence


def component_summary(rows):
    result = []
    for metric in METRICS:
        by = {m: {str(r['question_id']): r for r in rows if r['model'] == m and original.finite(r[metric])
                    and (r['identity_eligible'] or metric in ['sr', 'sp'])} for m in MODELS}
        common = original.qsort(set.intersection(*(set(x) for x in by.values())))
        common = [q for q in common if len({by[m][q]['question_sha256'] for m in MODELS}) == 1]
        result.append(dict(metric=metric, common_question_ids=common, common_n=len(common), question_denominator=5,
            per_model_numeric_n={m: len(by[m]) for m in MODELS},
            common_means={m: math.fsum(by[m][q][metric] for q in common) / len(common) for m in MODELS} if common else {},
            independent_CCE_conclusion_allowed=False,
            deterministic_step_reuse_not_new_judge_observation=metric in ['sr', 'sp']))
    return result


def draws_summary(draws, models):
    count = len(draws) // len(models)
    values = {m: {k: [] for k in JOINT} for m in models}
    dominated = {a: {b: 0 for b in models} for a in models}
    front_counts = Counter()
    for i in range(0, len(draws), len(models)):
        current = draws[i:i + len(models)]
        require(len({tuple(r['question_draws']) for r in current}) == 1, 'DRAW_NOT_SYNCHRONIZED')
        means = {r['model']: {k: r[k] for k in JOINT} for r in current}
        dm, front = original.matrix_and_pareto(means)
        front_counts.update(front)
        for m in models:
            for k in JOINT:
                values[m][k].append(means[m][k])
            for b in models:
                dominated[m][b] += int(dm[m][b])
    return dict(draw_count=count,
        percentile_intervals={m: {k: [float(x) for x in np.quantile(values[m][k], [.025, .975])]
            for k in JOINT} for m in models},
        bootstrap_means={m: {k: math.fsum(values[m][k]) / count for k in JOINT} for m in models},
        nondominance_frequency={m: front_counts[m] / count for m in models},
        dominance_frequency={a: {b: dominated[a][b] / count for b in models} for a in models})


def task_bootstrap(common, by_model):
    qs, models = common['common_question_ids'], common['model_cohort']
    n = len(qs)
    info = dict(unit='synchronized task', repeats_requested=REPEATS, seed=SEED,
        question_ids=qs, task_count=n, new_model_requests=0, exact_enumeration_count=n ** n if n else 0,
        status='pending_no_complete_common_tasks' if n == 0 else 'degenerate_single_task' if n == 1 else 'descriptive_small_fixed_task_set',
        limitation='Coverage-selected, exposed tasks and provisional references; exact enumeration only audits Monte Carlo approximation, not scientific accuracy or generalization.')
    if not n:
        return info, [], []
    require(n <= 5, 'EXACT_ENUMERATION_SCOPE')
    rng = np.random.default_rng(SEED)
    def generate(indexes, kind):
        out = []
        for i, idx in enumerate(indexes):
            selected = [qs[int(x)] for x in idx]
            for model in models:
                means = {k: math.fsum(by_model[model][q][k] for q in selected) / n for k in JOINT}
                out.append(dict(kind=kind, replicate=i, model=model, question_draws=selected, **means))
        return out
    mc = generate(rng.integers(0, n, size=(REPEATS, n)), 'task_monte_carlo')
    exact = generate(itertools.product(range(n), repeat=n), 'task_exact_ordered_enumeration')
    ms, es = draws_summary(mc, models), draws_summary(exact, models)
    error = dict(
        percentile_endpoint_absolute_error={m: {k: [abs(a - b) for a, b in zip(ms['percentile_intervals'][m][k], es['percentile_intervals'][m][k])]
            for k in JOINT} for m in models},
        bootstrap_mean_absolute_error={m: {k: abs(ms['bootstrap_means'][m][k] - es['bootstrap_means'][m][k]) for k in JOINT} for m in models},
        nondominance_frequency_absolute_error={m: abs(ms['nondominance_frequency'][m] - es['nondominance_frequency'][m]) for m in models},
        dominance_frequency_absolute_error={a: {b: abs(ms['dominance_frequency'][a][b] - es['dominance_frequency'][a][b]) for b in models} for a in models})
    info.update(monte_carlo=ms, exact=es, monte_carlo_vs_exact=error,
        exact_probability_per_ordered_draw=1 / n ** n,
        percentile_definition='numpy.quantile linear, matching original family bootstrap',
        convergence_acceptance_test_performed=False)
    return info, mc, exact


def overlap_diagnostic(catalog, common_qids):
    families = {str(q): sorted({r['family_id'] for r in catalog if q in r.get('question_ids', [])}) for q in QIDS}
    adjacency = {q: {p for p in families if p != q and set(families[p]) & set(families[q])} for q in families}
    unseen, groups = set(families), []
    while unseen:
        todo, found = [min(unseen, key=int)], set()
        while todo:
            q = todo.pop()
            if q not in found:
                found.add(q)
                todo.extend(adjacency[q] - found)
        unseen -= found
        groups.append(original.qsort(found))
    restricted = [original.qsort(set(group) & set(common_qids)) for group in groups]
    restricted = [group for group in restricted if group]
    return dict(status='degenerate_single_overlap_block' if len(restricted) == 1 else
        'pending_no_common_tasks' if not restricted else 'descriptive_overlap_components',
        fixed_task_allowed_source_families=families, fixed_task_components=groups,
        common_set_components=restricted, resampling_performed=False,
        definition='Connect tasks sharing any source family in the frozen full catalog question_ids; connected components are a conservative overlap diagnostic, not a claimed unique source-family mapping or scientific applicability.')


def analyze(destination):
    require(not destination.exists(), 'NEW_VERSIONED_OUTPUT_REQUIRED')
    captured = datetime.now(timezone.utc).isoformat()
    meta = fixed_metadata()
    rows, catalog, batches, evidence = collect(meta)
    common, by_model = original.common_summary(rows, MODELS, scope=SCOPE, denominator=5, formal=False)
    formal, _ = original.common_summary(rows, MODELS, scope=SCOPE, denominator=5, formal=True)
    bootstrap, mc, exact = task_bootstrap(common, by_model)
    family, family_draws = original.family_bootstrap(common, by_model, REPEATS, SEED)
    family['mapping_evidence'] = [{k: r[k] for k in ['model', 'question_id', 'reference_id', 'family_id']} for r in rows]
    family['scientific_reference_eligibility'] = 'provisional; expert-qualified=0'
    components = component_summary(rows)
    summary = dict(status='complete' if all(r['terminal'] for r in rows) else 'partial_pending', captured_utc=captured,
        planned_answers=10, fixed_generator_models=MODELS, generator_family_count=1,
        evaluator_judges=sorted({r['judge'] for r in rows if 'judge' in r}), fixed_question_ids=QIDS,
        terminal_answers=sum(r['terminal'] for r in rows), statuses=dict(Counter(r['status'] for r in rows)),
        actual_requests=sum(r['actual_request_made'] for r in rows), complete_CCE=sum(r['complete_CCE'] for r in rows),
        metric_coverage={k: sum(original.finite(r[k]) for r in rows) for k in METRICS},
        common_n=common['common_n'], common_question_ids=common['common_question_ids'],
        conditional_means=common['means'], empirical_nondominated=common['empirical_nondominated'],
        task_bootstrap_status=bootstrap['status'], family_bootstrap_status=family['status'],
        formal_common_n=formal['common_n'], expert_qualified=0, new_model_requests=0, new_embeddings=0,
        numeric_scope=SCOPE, original_13_model_cohort_unchanged=True,
        scientific_accuracy_validated=False, raw_model_outputs_not_reinterpreted=True)
    inputs = [bind(p) for p in [SELECTION, ADDENDUM, Path(__file__), Path(original.__file__), Path(numeric.__file__),
        STEPS / 't070_per_answer.csv', STEPS / 't070_resolved_config.json', STEPS / 'references.json']]
    inputs += [x for batch in batches for x in batch['bindings']] + evidence
    unique = list({(x['path'], x['sha256']): x for x in inputs}.values())
    destination.mkdir(parents=True)
    for name, value in [('summary', summary), ('per_answer', rows), ('common_joint', common), ('formal_common_joint', formal),
        ('component_common_sets', components), ('task_bootstrap', bootstrap), ('source_family_bootstrap', family),
        ('source_overlap_diagnostic', overlap_diagnostic(catalog, common['common_question_ids']))]:
        write(destination / (name + '.json'), value)
    csvwrite(destination / 'per_answer.csv', rows)
    csvwrite(destination / 'component_common_sets.csv', components)
    for name, values in [('task_bootstrap_draws', mc), ('task_exact_draws', exact), ('source_family_bootstrap_draws', family_draws)]:
        write(destination / (name + '.json'), values)
        csvwrite(destination / (name + '.csv'), values)
    commands = dict(argv=[sys.executable, *sys.argv], generated_utc=captured, new_model_requests=0,
        operations='Read immutable metadata/terminal metrics; verify hashes and original derived formula; aggregate and resample saved values. No raw JSON extraction replay, no new SR/SP or EGES calculation.')
    write(destination / 'actual_commands.json', commands)
    write(destination / 'source_execution_commands.json', [dict(source_batch=b['source_batch'],
        prepare_command=b['plan'].get('actual_prepare_command'), run_commands=b['execution_commands']) for b in batches])
    write(destination / 'verification.json', dict(status='pass', bindings=unique, original_SR_SP_unchanged=True,
        original_derived_formula_checked=True, raw_to_conversion_or_EGES_replay_performed=False,
        fixed_ten_rows=True, synchronized_task_draws=True, exact_enumeration_completed=len(exact) // 2,
        completeness_status=summary['status'], no_live_ledger_dependency=True,
        note='Software/numerical provenance checks; not expert scientific acceptance. Bound raw files are hashed without decoding their text.'))
    table = '\n'.join('| {anonymous_answer_id} | {model} | {question_id} | {status} | {sr:.6g} | {sp:.6g} | {complete_CCE} |'.format(**r) for r in rows)
    prose = f'''# 固定双生成器、五任务的次要联合分析

这是按参考覆盖选择的次要分析，两个生成器同属 Qwen 家族。全部 10 份答案保留；任务已在开发中暴露，参考仍未获专家确认。它不替代原固定 13 模型结果，也不作为原随机确认群体的估计。

截至 {captured}，终态 {summary['terminal_answers']}/10，完整数值 CCE {summary['complete_CCE']}/10；共同有限任务 Q*={common['common_question_ids']}，共 {common['common_n']}/5。正式科学资格共同集为 0。未完成或缺失项保持 NA。

| 匿名 ID | 生成器 | qid | 状态 | 原 SR | 原 SP | 完整数值 CCE |
|---|---|---:|---|---:|---:|---|
{table}

联合结果复用原 common_summary：先逐答案得到 IA=min(Com,Cor,Eff)、HV=Com×Cor×Eff，再在同一 Q* 上取均值；三维均值用于帕累托支配，容差 1e-12。不能用三维均值的最小值或乘积替代平均 IA/HV。各分项自己的共同集另表显示，不能拼成完整 CCE。

任务 bootstrap 为预定 2,000 次、种子 20261010；同一抽题索引同步用于两个生成器，原答案分数不变，新增模型调用为 0。当前状态：{bootstrap['status']}。K≤5 时枚举 K^K 有序有放回抽样，最多 3,125 种，仅核对蒙特卡洛近似误差，不增加独立任务或消除选择偏差。

来源家族重采样状态：{family['status']}。只接受实际选定来源支持且跨生成器一致的任务→家族映射；不同路线不能虚构统一映射。全目录的来源重叠连通块另列为保守依赖诊断，单块退化不是稳健性证据。

逐答案表保留 trial、raw、来源文档、原始答案/题干及参考的路径或哈希；`verification.json` 绑定此次读取的真实文件，`actual_commands.json` 保存命令。没有解析答案正文调参，也没有重新生成、重做步骤匹配或重算 EGES。技术成功、有限数值和科学有效性分开报告。
'''
    (destination / 'README_zh.md').write_text(prose, encoding='utf8')
    write(destination / 'output_manifest.json', {'files': [bind(p) for p in sorted(destination.iterdir()) if p.is_file()]})
    print(json.dumps(dict(out=str(destination), **summary), ensure_ascii=False))


def self_check(destination):
    """Numerical counterexamples only; no production results or source answers."""
    require(not destination.exists(), 'NEW_SOFTWARE_OUTPUT_REQUIRED')
    checks = []
    def check(name, condition):
        checks.append({'check': name, 'pass': bool(condition)})
        require(condition, name)
    rows = []
    # Averages have a different IA/HV from the minimum/product of averages.
    for model in MODELS:
        for q, xyz in [(1, [.1, .9, .5]), (2, [.9, .1, .5])]:
            rows.append(dict(model=model, question_id=q, question_sha256='q'+str(q), identity_eligible=True,
                formal_eligible=False, family_id='one', Com=xyz[0], Cor=xyz[1], Eff=xyz[2],
                IA=min(xyz), HV=math.prod(xyz), **{k: None for k in METRICS if k not in JOINT}))
    common, by = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5)
    check('original_common_two_tasks', common['common_n'] == 2)
    check('per_task_IA_not_min_mean', common['means'][MODELS[0]]['IA'] == .1)
    check('per_task_HV_not_product_mean', math.isclose(common['means'][MODELS[0]]['HV'], .045))
    info, mc, exact = task_bootstrap(common, by)
    check('2000_synchronized_two_model_draws', len(mc) == 4000 and all(mc[i]['question_draws'] == mc[i+1]['question_draws'] for i in range(0, len(mc), 2)))
    check('K_power_K_exact_count', len(exact) == 8 and info['exact_enumeration_count'] == 4)
    check('exact_bootstrap_mean_preserves_empirical_mean', all(math.isclose(info['exact']['bootstrap_means'][m][k], common['means'][m][k]) for m in MODELS for k in JOINT))
    check('seed_reproducibility', task_bootstrap(common, by)[1] == mc)
    formal, _ = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5, formal=True)
    check('finite_not_formally_eligible', formal['common_n'] == 0)
    rows[-1]['Eff'] = rows[-1]['IA'] = rows[-1]['HV'] = None
    partial, pb = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5)
    pi, pm, pe = task_bootstrap(partial, pb)
    check('missing_metric_not_zero', partial['common_question_ids'] == ['1'])
    check('one_task_degenerate', pi['status'] == 'degenerate_single_task' and len(pe) == 2 and len({tuple(d[k] for k in JOINT) for d in pm}) == 1)
    rows[-2]['Eff'] = rows[-2]['IA'] = rows[-2]['HV'] = None
    empty, eb = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5)
    ei, em, ee = task_bootstrap(empty, eb)
    check('empty_common_pending', empty['common_n'] == 0 and not em and not ee and ei['status'].startswith('pending'))
    rows[-2].update(Eff=.5, IA=.1, HV=.045, family_id='different')
    partial, pb = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5)
    fam, fd = original.family_bootstrap(partial, pb, REPEATS, SEED)
    check('inconsistent_families_pending', fam['status'] == 'pending_source_family_map_missing_or_inconsistent' and not fd)
    rows[-2]['question_sha256'] = 'wrong'
    badq, _ = original.common_summary(rows, MODELS, scope='software_fixture', denominator=5)
    check('different_stems_not_paired', badq['common_n'] == 0)
    values = numeric.derive(dict(c_param=0, co_order=0, co_method=0, co_param=0, co_chem=0,
        s_method=-2.5, s_label=0, s_trans=0, s_time=0), dict(sr=0, sp=0), True)
    check('known_zero_preserved', all(values[k] == 0 for k in JOINT))
    failed = numeric.derive(values, dict(sr=.4, sp=.6), False)
    check('failed_known_steps_only', failed['sr'] == .4 and failed['sp'] == .6 and all(failed[k] is None for k in JOINT))
    write(destination / 'verification.json', dict(status='pass', checks=checks, script=bind(__file__),
        original_analysis=bind(original.__file__), numeric_adapter=bind(numeric.__file__),
        scope='Synthetic numerical analysis only; production archive collector not exercised here.',
        new_model_requests=0, new_embeddings=0, actual_command=[sys.executable, *sys.argv]))
    print(json.dumps({'status': 'pass', 'checks': len(checks), 'out': str(destination)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['analyze', 'self-check'])
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    (analyze if a.action == 'analyze' else self_check)(a.out.resolve())


if __name__ == '__main__':
    main()
