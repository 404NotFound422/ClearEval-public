"""Offline, single-judge analysis of the unchanged 15-slot Qwen continuation.

No import reads experiment output. The analyze command needs an explicit ROOT
invocation. Existing per-cell replay, conversion and numerical rules are reused;
this module never creates a trial, requests a model, or changes a returned value.
"""
from __future__ import annotations
import argparse
import copy
import statistics
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_qwen_only_stability_continuation_v1 as continuation
old = continuation.old
j = old.j
stats = old.old_stability
METRICS = stats.METRICS
CATEGORIES = stats.CATEGORIES
VERSION = 'qwen-only-stability-analysis-v1'
require = old.require


def collect(source_out):
    """Read each real terminal from its actual location; no synthetic trial."""
    plan, cases, items, contract = continuation.validate(source_out)
    require(len(items) == 15 and plan['planned_observations'] == 15, 'FIFTEEN_SLOTS')
    dispositions = {key: sum(i['disposition'] == key for i in items) for key in
                    ['reuse_original_terminal', 'user_cancelled_no_retry', 'unrequested_eligible']}
    require(dispositions == {'reuse_original_terminal': 3, 'user_cancelled_no_retry': 1,
                             'unrequested_eligible': 11}, 'FIXED_CONTINUATION_DISPOSITIONS')
    observations, bindings, replays = [], [], 0
    for item in items:
        row = item['source_cell']; disposition = item['disposition']
        location = Path(plan['source_out']) if disposition != 'unrequested_eligible' else source_out
        terminal = location / 'run/trials' / (row['planned_trial_id'] + '.json')
        if disposition == 'user_cancelled_no_retry':
            require(not terminal.exists(), 'CANCELLED_CELL_MUST_NOT_BE_RELABELED_TERMINAL')
        if terminal.exists():
            value = j.read(terminal)
            require(value['phase'] == 'E4' and value['anonymous_answer_id'] == row['anonymous_answer_id']
                    and value['actual_request_made'] is True and type(value['repeat_index']) is int
                    and type(value['attempt']) is int and value['attempt'] == 1,
                    'TERMINAL_PHASE_ANSWER_REQUEST_IDENTITY')
        rows, cell_bindings, cell_replays = old.read_observations(
            location, plan, cases, [row], {continuation.QWEN: contract})
        observed = rows[0]
        if disposition == 'reuse_original_terminal':
            require(observed['status'] == 'success', 'FROZEN_THREE_SUCCESS_REFERENCES')
        if disposition == 'user_cancelled_no_retry':
            require(observed['status'] == 'pending' and cell_replays == 0, 'CANCELLED_NOT_REPLAYED')
            # This is an analysis status. The original reserved/nonterminal
            # experiment slot and all of its files remain unchanged.
            observed['status'] = 'user_cancelled_no_retry'
            observed['failure_stage'] = None
        observed.update(original_batch_reused=observed['reused'],
                        reused=disposition == 'reuse_original_terminal',
                        continuation_disposition=disposition,
                        source_output_directory=str(location),
                        original_success_reference=disposition == 'reuse_original_terminal',
                        cancelled_by_user=disposition == 'user_cancelled_no_retry',
                        model_failure=observed['status'] == 'failed',
                        technical_executable=observed['status'] == 'success',
                        reserved_request_metadata=item['reservation'],
                        deterministic_step_source='verified_frozen_step_inputs',
                        deterministic_steps_are_not_judge_returns=True)
        observations.append(observed); bindings.extend(cell_bindings); replays += cell_replays
    return plan, observations, bindings, replays


def summarize(observations):
    """Original within-group descriptive statistics on the single-judge grid."""
    ids = list(old.base.IDS); model = continuation.QWEN
    lookup = {(r['anonymous_answer_id'], r['judge'], r['repeat_index']): r for r in observations}
    require(len(observations) == len(lookup) == 15 and set(lookup) ==
            {(a, model, r) for a in ids for r in range(3)}, 'EXACT_FIVE_BY_THREE_GRID')
    require(all(r['status'] in ['success', 'failed', 'pending', 'user_cancelled_no_retry'] for r in observations),
            'UNKNOWN_OBSERVATION_STATE')
    within = []
    for aid in ids:
        for metric in METRICS:
            rr = [lookup[aid, model, repeat] for repeat in range(3)]
            values = [r[metric] for r in rr]
            require(all(v is None or stats.finite(v) for v in values), 'NONFINITE_METRIC')
            if metric not in ['sr', 'sp']:
                require(all(r['status'] == 'success' or r[metric] is None for r in rr),
                        'NON_SUCCESS_JUDGE_METRIC_NOT_NA')
            valid = [v for v in values if stats.finite(v)]; n = len(valid)
            spread = max(valid) - min(valid) if n >= 2 else None
            within.append({'anonymous_answer_id': aid, 'judge': model, 'metric': metric,
                'category': stats.category(metric), 'counts_as_direct_judge_stability': metric in stats.DIRECT,
                'fixed_step_values_not_new_judge_observations': metric in ['sr', 'sp'],
                'new_judge_numeric_observations': 0 if metric in ['sr', 'sp'] else n,
                'planned_n': 3, 'finite_n': n, 'coverage': 'complete_three' if n == 3 else 'partial' if n else 'no_finite',
                'values_by_repeat': values, 'statuses_by_repeat': [r['status'] for r in rr],
                'mean': statistics.mean(valid) if n else None,
                'sample_sd': statistics.stdev(valid) if n >= 2 else None,
                'min': min(valid) if n else None, 'max': max(valid) if n else None,
                'range': spread, 'nonzero_range': spread > stats.TOL if spread is not None else None,
                'complete_three_nonzero_range': spread > stats.TOL if n == 3 else None})
    require(len(within) == 80, 'EIGHTY_METRIC_GROUPS')
    categories = []
    for category in CATEGORIES:
        group = [r for r in within if r['category'] == category]
        categories.append({'category': category, 'planned_groups': len(group),
            'complete_three_groups': sum(r['finite_n'] == 3 for r in group),
            'partial_groups': sum(0 < r['finite_n'] < 3 for r in group),
            'no_finite_groups': sum(r['finite_n'] == 0 for r in group),
            'range_evaluable_groups': sum(r['range'] is not None for r in group),
            'nonzero_range_groups': sum(r['nonzero_range'] is True for r in group),
            'strict_complete_three_nonzero_range_groups': sum(r['complete_three_nonzero_range'] is True for r in group),
            'judge_stability_evidence': category != 'deterministic_steps',
            'direct_judge_stability_evidence': category == 'direct_judge'})
    return within, categories


def completion(observations, within, categories, replays):
    counts = {s: sum(r['status'] == s for r in observations) for s in
              ['success', 'failed', 'pending', 'user_cancelled_no_retry']}
    return {'status': 'all_slots_accounted_not_scientific_validation' if counts['pending'] == 0 else
                     'partial_slots_not_scientific_validation',
        'version': VERSION, 'phase': 'E4', 'judge': continuation.QWEN,
        'planned_observations': 15, 'answer_denominator': 5, 'repeats': 3, 'within_groups': 80,
        'technical_successes': counts['success'], 'model_or_pipeline_failures': counts['failed'],
        'user_cancelled_no_retry': counts['user_cancelled_no_retry'], 'pending': counts['pending'],
        'completed_model_attempts': counts['success'] + counts['failed'],
        'accounted_slots': 15 - counts['pending'], 'all_slots_accounted': counts['pending'] == 0,
        'original_success_references': sum(r['original_success_reference'] for r in observations),
        'continuation_new_terminal_attempts': sum(r['continuation_disposition'] == 'unrequested_eligible'
            and r['status'] in ['success', 'failed'] for r in observations),
        'complete_numeric_CCE': sum(r['complete_numeric_CCE'] for r in observations),
        'component_coverage': {m: sum(stats.finite(r[m]) for r in observations) for m in METRICS},
        'raw_conversion_and_numeric_replays': replays,
        'strict_complete_three_groups': sum(r['finite_n'] == 3 for r in within),
        'strict_complete_three_direct_judge_groups': sum(r['finite_n'] == 3 and r['category'] == 'direct_judge' for r in within),
        'category_summary': categories, 'independent_answer_count': 5,
        'metric_groups_are_not_independent_answers': True, 'cancellation_is_not_model_failure': True,
        'cached_steps_not_judge_stability_success': True, 'cross_judge_comparison': False,
        'original_two_judge_batch_completed': False, 'scientific_acceptance': False,
        'source_fact_acceptance': 'requires_separate_review', 'expert_returns': 0,
        'new_model_requests_from_analysis': 0}


def analyze(args):
    require(args.root_authorized, 'ROOT_TRIGGER_REQUIRED')
    require(not args.report_out.exists(), 'NEW_ANALYSIS_SNAPSHOT_ONLY')
    plan, rows, bindings, replays = collect(args.source)
    within, categories = summarize(rows); summary = completion(rows, within, categories, replays)
    # Validate the original source and continuation identity again after replay.
    continuation.validate(args.source)
    require(replays == summary['technical_successes'], 'ALL_SUCCESSES_REPLAYED')
    dependencies = [Path(__file__), Path(continuation.__file__), Path(old.__file__),
                    Path(old.base.__file__), Path(old.grounded.__file__), Path(old.scoring.__file__),
                    Path(stats.__file__), *[args.source / n for n in
                    ['plan.json', 'matrix.json', 'expected_contract.json', 'cases.json', 'step_inputs.json']],
                    Path(plan['root_amendment']['path'])]
    unique_bindings = {str(b['path']): b for b in [*[old.bind(p) for p in dependencies], *bindings]}
    summary['bound_actual_artifacts'] = list(unique_bindings.values())
    args.report_out.mkdir(parents=True)
    for name, values in [('observations', rows), ('within', within), ('category_summary', categories),
                         ('deterministic_steps', [r for r in within if r['category'] == 'deterministic_steps'])]:
        old.write_table(args.report_out, name, values)
    j.save(args.report_out / 'completion_summary.json', summary)
    j.save(args.report_out / 'analysis_verification.json', {'status': 'pass',
        'planned_observations': 15, 'accounted_slots': summary['accounted_slots'],
        'all_slots_accounted': summary['all_slots_accounted'], 'technical_successes': summary['technical_successes'],
        'successful_raw_numeric_replays': replays, 'cancelled_cells_not_success_or_model_failure': True,
        'original_frozen_functions_used': True, 'within_groups': 80, 'cross_judge_comparison': False,
        'bindings': [old.bind(args.report_out / n) for n in
                     ['observations.json', 'within.json', 'completion_summary.json']],
        'new_model_requests': 0, 'scientific_acceptance': False})
    j.save(args.report_out / 'actual_commands.json', {'argv': sys.argv, 'python': sys.executable,
        'utc': j.now(), 'new_model_requests': 0, 'source_input_modified': False})
    print(j.canonical({k: v for k, v in summary.items() if k not in ['bound_actual_artifacts', 'category_summary']}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['analyze'])
    p.add_argument('--source', type=Path, default=continuation.DEFAULT_OUT)
    p.add_argument('--report-out', type=Path, required=True)
    p.add_argument('--root-authorized', action='store_true')
    args = p.parse_args(); args.source = args.source.resolve(); args.report_out = args.report_out.resolve()
    analyze(args)


if __name__ == '__main__':
    main()
