"""Reprocess nine saved alternative-route returns with one explicit score-key alias.

No request is sent. Original raw returns and original trial statuses are immutable.
The mapping changes a field identifier only; it never supplies a score or reason.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
sys.dont_write_bytecode = True
import cce_judges as judges
import cce_plot_four_hour_evidence_v1 as io

SOURCE = ROOT / 'artifacts/cce_validation/judges/local_alternative_development'
DEFAULT = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010/legacy_alternative_alias_v1/actual_01'
METRICS = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem', 's_method', 's_label', 's_trans', 's_time',
           'sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']


def normalize_score_key(payload):
    revised = copy.deepcopy(payload)
    correctness = revised.get('scores', {}).get('correctness', {})
    audit = []
    if 'co_chemical' in correctness and 'co_chem' not in correctness:
        item = correctness['co_chemical']
        assert item['max_score'] == 1 and item['score'] in [0, 1]
        assert isinstance(item.get('reasoning'), str) and isinstance(item.get('description'), str)
        correctness['co_chem'] = copy.deepcopy(item)
        audit.append(dict(source_pointer='/scores/correctness/co_chemical',
                          destination_pointer='/scores/correctness/co_chem', original_item=item,
                          action='explicit_identifier_alias_original_item_preserved', score_imputed=False))
    return revised, audit


async def run(args):
    assert not args.out.exists()
    os.chdir(ROOT)
    import OEQ_run_grading_new as runner
    runner.configure_question_snapshot(judges.HIST)
    # The original fixed demand registry is loaded by the existing evaluator.
    registry = runner.fixed_demands()
    source_paths = [SOURCE / name for name in ['cases.json', 'per_case.json', 'paired_results.json', 'step_results.json']]
    originals = judges.read(SOURCE / 'per_case.json')
    cases = judges.read(SOURCE / 'cases.json')
    cases = cases['cases'] if isinstance(cases, dict) else cases
    by_case = {r['case_id']: r for r in cases}
    bindings = [io.bind(path) for path in source_paths]
    results = []
    args.out.mkdir(parents=True)
    for old in originals:
        case = by_case[old['case_id']]
        trial_path = Path(old['trial_source'])
        trial = judges.read(trial_path)
        provider_path = SOURCE / 'attempts' / f"{trial['trial_id']}_{trial['attempt']}" / 'provider_response.json'
        bindings.extend([io.bind(trial_path), io.bind(provider_path)])
        provider = judges.read(provider_path)
        raw = json.loads(provider['response'])
        revised, alias = normalize_score_key(raw)
        logs = []
        runner._log_teacher_response = lambda *items: logs.append(list(items))
        class SavedReturn:
            model_name = 'offline_saved_Qwen3_8b_return'
            calls = 0
            async def _acall(self, prompt):
                self.calls += 1
                return {'content': json.dumps(revised, ensure_ascii=False), 'metadata': {'offline_saved_return': True}}
        saved = SavedReturn()
        evaluation = await runner.evaluate_response_with_teacher(saved, case['specific_question'], case['model_response'],
                                                                 runner.MODEL_SPACE_SIGNED, {'question_id': case['question_id']}, None)
        assert saved.calls == 1
        assert evaluation.get('technical_status') == 'VALID', evaluation
        values = judges.proposals(evaluation)
        values.update({key: old['candidate_raw_and_derived'][key] for key in ['sr', 'sp']})
        values['Com'] = .4 * values['sr'] + .6 * values['c_param'] / 3
        dims = [values[key] for key in ['Com', 'Cor', 'Eff']]
        values['IA'] = min(dims) if all(io.finite(v) for v in dims) else None
        values['HV'] = math.prod(dims) if all(io.finite(v) for v in dims) else None
        differences = {key: dict(before=old['candidate_raw_and_derived'].get(key), after=values.get(key))
                       for key in METRICS if old['candidate_raw_and_derived'].get(key) != values.get(key)}
        if old['status'] == 'success':
            assert not differences, (case['case_id'], differences)
        assert raw['extraction'] == evaluation['extraction']
        assert raw == json.loads(provider['response'])
        row = dict(case_id=case['case_id'], question_id=case['question_id'], generator_model=old['generator_model'],
                   original_trial_status=old['status'], original_trial_id=trial['trial_id'],
                   original_trial=io.bind(trial_path), original_provider=io.bind(provider_path),
                   posthoc_status='offline_reprocessed', aliases=alias, original=old['candidate_raw_and_derived'],
                   metrics=values, differences=differences, new_model_calls=0,
                   extraction_unchanged=True, expert_confirmed=False, formal_eligible=False,
                   scope='Historical Qwen3:8b raw return with explicit schema alias, not a new current-Qwen evaluation')
        judges.save(args.out / 'cells' / (case['case_id'] + '.json'), dict(row=row, evaluation=evaluation, logs=logs))
        results.append(row)
    indexed = {row['case_id']: row for row in results}
    paired = []
    for original_pair in judges.read(SOURCE / 'paired_results.json'):
        a, b = [indexed[original_pair[key]] for key in ['baseline_case_id', 'alternative_case_id']]
        full = all(io.finite(row['metrics'][key]) for row in [a, b] for key in ['Com', 'Cor', 'Eff'])
        paired.append(dict(pair_id=original_pair['pair_id'], question_id=original_pair['question_id'],
                           baseline_case_id=a['case_id'], alternative_case_id=b['case_id'],
                           original_pair_complete=original_pair['technical_pipeline_complete'], complete_numeric_pair=full,
                           same_posthoc_configuration=True, formal_eligible=False,
                           **{f'{prefix}_{key}': row['metrics'][key] for prefix, row in [('baseline', a), ('alternative', b)] for key in METRICS},
                           **{'delta_' + key: b['metrics'][key] - a['metrics'][key]
                              if io.finite(a['metrics'][key]) and io.finite(b['metrics'][key]) else None for key in METRICS}))
    assert len(results) == 9 and len(paired) == 6
    assert sum(bool(row['aliases']) for row in results) == 1
    assert bindings == [io.bind(Path(row['path'])) for row in bindings]
    summary = dict(status='completed_offline_alias_replay', original_requests_reused=9, new_model_calls=0,
                   original_successes=sum(row['original_trial_status'] == 'success' for row in results),
                   posthoc_parsed_returns=len(results), complete_numeric_answers=sum(all(io.finite(row['metrics'][k]) for k in ['Com','Cor','Eff']) for row in results),
                   original_complete_pairs=sum(row['original_pair_complete'] for row in paired),
                   posthoc_complete_pairs=sum(row['complete_numeric_pair'] for row in paired),
                   unchanged_previously_successful_answers=8, remapped_existing_fields=1,
                   score_values_imputed=0, raw_return_or_original_status_modified=False,
                   expert_confirmed_pairs=0, warning='Historical configuration only; no claim that raw judgments/extraction are scientifically correct.')
    for name, value in [('summary', summary), ('per_answer', results), ('paired_results', paired)]:
        judges.save(args.out / (name + '.json'), value)
    io.csvwrite(args.out / 'per_answer.csv', [dict(case_id=r['case_id'], original_trial_status=r['original_trial_status'], **r['metrics']) for r in results])
    io.csvwrite(args.out / 'paired_results.csv', paired)
    judges.save(args.out / 'verification.json', dict(status='pass', sources=bindings, script=io.bind(Path(__file__)),
                 runtime=io.bind(Path(runner.__file__)), question_snapshot=io.bind(judges.HIST),
                 fixed_demand_provenance=registry.provenance, actual_command=[sys.executable, *sys.argv],
                 previously_successful_16_metrics_equal=True, original_extractions_equal=True, new_model_calls=0))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT)
    asyncio.run(run(parser.parse_args()))
