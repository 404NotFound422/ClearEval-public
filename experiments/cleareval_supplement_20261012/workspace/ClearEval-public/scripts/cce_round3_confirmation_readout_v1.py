"""All eight frozen confirmation slots, with joint comparison on declared common tasks.

Offline analysis only. Original metrics and secondary applicability results remain
separate; singleton judge calls do not estimate evaluator repeatability.
"""
from __future__ import annotations
import argparse, collections, csv, itertools, json, random, statistics, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_round3_runner_v2 as runner
import cce_partial_joint_identifiability_v1 as partial
from cce_round3_E2_readout_v2 import quantile

R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
MODELS = ['openai_claude-sonnet-4.6', 'openai_qwen3-max']
TASKS = [23, 248]
JOINT = ['Com', 'Cor', 'Eff', 'IA', 'HV']
SEED = 20261011


def complete(metrics):
    return all(runner.finite(metrics[k]) for k in JOINT)


def mean_bounds(rows):
    return {m: {k: [statistics.mean(r['bounds'][k][i] for r in rows if r['model'] == m)
                    for i in [0, 1]] for k in JOINT} for m in MODELS}


def dominance(means):
    pairs = {a: {b: partial.dominance(means[a], means[b]) for b in MODELS if b != a} for a in MODELS}
    identified = {}
    for model in MODELS:
        incoming = [pairs[other][model]['state'] for other in MODELS if other != model]
        identified[model] = {
            'guaranteed_nondominated': all(s == 'cannot_dominate' for s in incoming),
            'not_ruled_out_as_nondominated': not any(s == 'dominates_for_every_admissible_completion' for s in incoming)}
    return pairs, identified


def task_samples(index, task_ids):
    if not task_ids:
        return {'status': 'not_estimable_zero_common_complete_tasks'}, []
    rng = random.Random(SEED)
    draws = {'bootstrap_2000': [tuple(rng.choice(task_ids) for _ in task_ids) for _ in range(2000)],
             'exact_ordered': list(itertools.product(task_ids, repeat=len(task_ids)))}
    records = []
    for kind, samples in draws.items():
        for replicate, draw in enumerate(samples):
            means = {m: {k: statistics.mean(index[m, q][k] for q in draw) for k in JOINT} for m in MODELS}
            _, identified = dominance({m: {k: [v, v] for k, v in means[m].items()} for m in MODELS})
            for m in MODELS:
                records.append({'draw_kind': kind, 'replicate': replicate, 'model': m,
                                'task_draws': list(draw), 'mean_scores': means[m],
                                'nondominated': identified[m]['guaranteed_nondominated']})
    result = {'status': 'degenerate_one_task' if len(task_ids) == 1 else 'descriptive_two_task_sensitivity',
              'task_ids': task_ids, 'seed': SEED, 'independent_unit': 'task',
              'quantile_definition': 'inverse empirical CDF; no linear interpolation',
              'population_confidence_interval': False}
    for kind in draws:
        result[kind] = {}
        for m in MODELS:
            rr = [r for r in records if r['draw_kind'] == kind and r['model'] == m]
            result[kind][m] = {'draws': len(rr), 'nondominance_frequency': statistics.mean(r['nondominated'] for r in rr),
                'metrics': {k: {'mean': statistics.mean(r['mean_scores'][k] for r in rr),
                    'percentile_2_5': quantile([r['mean_scores'][k] for r in rr], .025),
                    'percentile_97_5': quantile([r['mean_scores'][k] for r in rr], .975)} for k in JOINT}}
    return result, records


def joint_analysis(rows, scope):
    group = [r for r in rows if r['model'] in MODELS and r['question_id'] in TASKS]
    assert len(group) == 4 and {(r['model'], r['question_id']) for r in group} == set(itertools.product(MODELS, TASKS))
    index = {(r['model'], r['question_id']): r[scope + '_metrics'] for r in group}
    common = [q for q in TASKS if all(complete(index[m, q]) for m in MODELS)]
    result = {'scope': scope, 'models': MODELS, 'planned_common_tasks': TASKS, 'planned_answers': 4,
              'common_complete_tasks': common, 'common_complete_n': len(common),
              'complete_answers_on_planned_support': sum(complete(v) for v in index.values())}
    if common:
        means = {m: {k: statistics.mean(index[m, q][k] for q in common) for k in JOINT} for m in MODELS}
        pairs, identified = dominance({m: {k: [v, v] for k, v in means[m].items()} for m in MODELS})
        result['complete_support_mean_scores'] = means
        result['complete_support_dominance'] = pairs
        result['complete_support_nondominance'] = identified
    else:
        result['complete_support_mean_scores'] = None
    result['resampling'], draws = task_samples(index, common)
    bound_rows = []
    for r in group:
        metrics = r[scope + '_metrics']
        if all(runner.finite(metrics[k]) for k in ['Com', 'Cor']):
            bounds, channels = partial.bounds(metrics)
            bound_rows.append({'model': r['model'], 'question_id': r['question_id'], 'case_id': r['case_id'],
                               'metrics': metrics, 'bounds': bounds, 'normalized_component_bounds': channels})
    result['partial_bounds'] = {'status': 'all_four_answers_available' if len(bound_rows) == 4 else 'incomplete_Com_Cor_support',
        'available_answers': len(bound_rows), 'planned_answers': 4,
        'interpretation': 'Deterministic outer bounds on the fixed two-task support; neither filled scores nor confidence intervals.'}
    if len(bound_rows) == 4:
        means = mean_bounds(bound_rows)
        pairs, identified = dominance(means)
        result['partial_bounds'].update(mean_bounds=means, dominance=pairs, identified_nondominance=identified)
    return result, bound_rows, draws


def main(args):
    batch, out, secondary = [Path(x).resolve() for x in [args.batch, args.out, args.secondary]]
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    plan, cases, matrix, _ = runner.validate(batch)
    assert plan['planned_observations'] == 8 and plan['repeats'] == 1 and len(cases) == 8
    pointer = runner.j.read(batch / 'latest_analysis.json')
    runner.base.verify_bindings(list(pointer.values()))
    verification = runner.j.read(pointer['verification']['path'])
    assert verification['all_planned_terminal'] and verification['status'] == 'pass'
    runner.base.verify_bindings(verification['bindings'])
    observations = runner.j.read(pointer['observations']['path'])
    side_verification = runner.j.read(secondary / 'verification.json')
    assert side_verification['status'] == 'pass' and not side_verification['primary_written']
    runner.base.verify_bindings(side_verification['input_bindings'] + side_verification['outputs'])
    secondary_rows = {r['trial_id']: r for r in runner.j.read(secondary / 'cells.json')}
    input_freeze_path = R3 / 'confirmation_inputs_01/input_freeze.json'
    input_freeze = runner.j.read(input_freeze_path)
    runner.base.verify_bindings(input_freeze['bindings'])
    identity_path = R3 / 'confirmation_inputs_01/source_identity_manifest.json'
    assert runner.bind(identity_path) in input_freeze['bindings']
    identity = {r['case_id']: r for r in runner.j.read(identity_path)}
    steps = runner.j.read(batch / 'steps.json')
    planned = {r['planned_trial_id']: r for r in matrix}
    assert len(observations) == len(secondary_rows) == len(identity) == 8
    assert {r['case_id'] for r in observations} == set(identity)
    assert len(planned) == 8 and {r['trial_id'] for r in observations} == set(planned) == set(secondary_rows)
    rows = []
    for r in observations:
        s = secondary_rows[r['trial_id']]
        assert s['primary_metrics'] == r['metrics'] and s['original_status'] == r['status']
        meta, step = identity[r['case_id']], steps[r['case_id']]
        entry = planned[r['trial_id']]
        terminal = batch / 'run/trials' / (r['trial_id'] + '.json')
        saved = runner.j.read(terminal)
        for key in ['case_id', 'anonymous_answer_id', 'question_id']:
            assert r[key] == entry[key] == meta[key] == s[key]
        # Terminal question identity is held in its frozen identity and case;
        # terminal rows do not duplicate question_id as a top-level field.
        for key in ['case_id', 'anonymous_answer_id', 'trial_id', 'repeat_index']:
            assert r[key] == saved[key] == s[key]
        assert r['repeat_index'] == entry['repeat_index'] == 0
        assert saved['identity'] == entry['identity'] and saved['phase'] == 'confirmation'
        assert saved['metrics'] == r['metrics'] and saved['status'] == r['status']
        assert step['question_id'] == meta['question_id']
        assert step['answer_sha256'] == meta['answer_sha256']
        assert all(r['metrics'][k] == s['secondary_metrics'][k] == step[k] for k in ['sr', 'sp'])
        primary_metrics, secondary_metrics = r['metrics'], s['secondary_metrics']
        rows.append({**{k: r[k] for k in ['case_id', 'anonymous_answer_id', 'question_id', 'trial_id', 'status', 'full_conversion_success']},
            'model': meta['generator_model'], 'answer_source': meta['source'],
            'answer_sha256': meta['answer_sha256'], 'primary_terminal': runner.bind(terminal),
            'secondary_detail': s.get('detail'), 'secondary_replay_reason': s.get('reason'),
            'primary_metrics': primary_metrics, 'secondary_metrics': secondary_metrics,
            'primary_complete_CCE': complete(primary_metrics), 'secondary_complete_CCE': complete(secondary_metrics),
            'primary_missing_components': [k for k in runner.base.scoring.DIRECT + runner.base.scoring.EGES if not runner.finite(primary_metrics[k])],
            'secondary_missing_components': [k for k in runner.base.scoring.DIRECT + runner.base.scoring.EGES if not runner.finite(secondary_metrics[k])],
            'reference_selection': {k: step.get(k) for k in ['reference_id', 'version_id', 'candidate_reference_ids',
                'candidate_version_ids', 'selection_rule', 'reference_status', 'formal_eligible', 'sr', 'sp']}})
    outputs = [('per_answer.json', rows)]
    joint = {}
    for scope in ['primary', 'secondary']:
        result, bounds, draws = joint_analysis(rows, scope)
        joint[scope] = result
        outputs += [(scope + '_joint.json', result), (scope + '_per_answer_bounds.json', bounds), (scope + '_task_resamples.json', draws)]
    summary = {'status': 'completed_all_eight_planned_slots', 'planned_answers': 8,
        'tasks': sorted({r['question_id'] for r in rows}), 'generator_models': sorted({r['model'] for r in rows}),
        'technical_status_counts': dict(collections.Counter(r['status'] for r in rows)),
        'primary_complete_CCE': sum(r['primary_complete_CCE'] for r in rows),
        'secondary_complete_CCE': sum(r['secondary_complete_CCE'] for r in rows),
        'component_coverage': {scope: {k: sum(runner.finite(r[scope + '_metrics'][k]) for r in rows) for k in runner.METRICS} for scope in ['primary', 'secondary']},
        'joint_common_complete_tasks': {scope: joint[scope]['common_complete_tasks'] for scope in joint},
        'limitations': ['Singleton calls cannot estimate evaluator repeatability.',
            'Only Claude Sonnet 4.6 and Qwen3 Max have two prespecified shared tasks.',
            'Task and source families were previously exposed; this is answer-level confirmation within registered exclusions.',
            'Reference qualification and biological correctness await expert evidence.',
            'Primary original and secondary applicability definitions are separate.'],
        'new_model_calls': 0, 'new_embeddings': 0, 'actual_command': [sys.executable, *sys.argv]}
    outputs.append(('summary.json', summary))
    for name, value in outputs:
        runner.save_once(out / name, value)
    with (out / 'per_answer.csv').open('x', encoding='utf8', newline='') as f:
        columns = ['case_id', 'question_id', 'model', 'status', 'scope', *runner.METRICS]
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            for scope in ['primary', 'secondary']:
                writer.writerow({**{k: r[k] for k in columns[:4]}, 'scope': scope, **r[scope + '_metrics']})
    source_bindings = [runner.bind(__file__), runner.bind(partial.__file__), runner.bind(ROOT / 'scripts/cce_round3_E2_readout_v2.py'),
        runner.bind(R3 / 'confirmation_configuration_freeze.json'), runner.bind(R3 / 'E2_resampling_quantile_amendment_receipt_01.json'),
        runner.bind(input_freeze_path), runner.bind(identity_path), runner.bind(batch / 'plan.json'), *pointer.values(),
        *[runner.bind(secondary / name) for name in ['cells.json', 'summary.json', 'verification.json']]]
    runner.save_once(out / 'verification.json', {'status': 'pass', 'source_bindings': source_bindings,
        'output_bindings': [runner.bind(p) for p in sorted(out.glob('*'))], 'all_eight_slots_retained': True,
        'raw_SR_SP_unchanged': True, 'original_bound_math_reused': True, 'new_model_calls': 0})
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--secondary', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    main(p.parse_args())
