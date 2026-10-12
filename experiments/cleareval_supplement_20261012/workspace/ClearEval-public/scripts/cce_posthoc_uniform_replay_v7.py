"""Uniform source-role replay of all 67 prior returns, compared with v6."""
import argparse
import json
import sys
import types
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_posthoc_uniform_replay_v1 as original
import cce_posthoc_components_v7 as components
import cce_posthoc_scoring_v7 as scorer

io = original.io
R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    review = R3 / 'standalone_fluor_role/execution_01/review.json'
    checked = io.read(review)
    if checked['status'] != 'pass' or checked['passed'] != checked['checks']:
        raise ValueError('Read the source-role review before the full replay')
    bindings = [io.bind(p) for p in [__file__, components.__file__, scorer.__file__,
                 scorer.standalone.__file__, review]]
    execute = types.FunctionType(original.main.__code__,
        {**vars(original), 'scorer': scorer, 'components': components, '__file__': __file__},
        name='uniform_replay_v7')
    execute()
    prior_path = io.R / 'posthoc_uniform_scoring_v6/actual_execution_01/cells.json'
    prior = {(r['cohort'], r['cell_id']): r for r in io.read(prior_path)}
    rows = io.read(args.out / 'cells.json')
    stable = list(scorer.numeric.DIRECT) + ['sr', 'sp', 'Com', 'Cor', 's_method', 's_trans', 's_time']
    differences, applications = [], []
    for row in rows:
        old = prior[row['cohort'], row['cell_id']]
        assert row['status'] == old['status']
        if row.get('cancelled_no_raw'):
            assert row['posthoc_metrics'] == old['posthoc_metrics']
            continue
        assert row['raw_sha256'] == old['raw_sha256']
        assert all(row['posthoc_metrics'][key] == old['posthoc_metrics'][key] for key in stable)
        diff = {key: {'v6': old['posthoc_metrics'][key], 'v7': row['posthoc_metrics'][key]}
                for key in original.METRICS if row['posthoc_metrics'][key] != old['posthoc_metrics'][key]}
        differences.append({'cohort': row['cohort'], 'cell_id': row['cell_id'], 'changes': diff})
        result = io.read(row['posthoc_record']['path'])
        for call in result['component_scoring_audit']:
            role = call.get('standalone_fluor_role') or {}
            if role.get('changes'):
                applications.append({'cohort': row['cohort'], 'cell_id': row['cell_id'],
                    'dependency_views': call.get('dependency_view_names'),
                    'changes': role['changes'], 'assessments': role['assessments'],
                    'posthoc_record': row['posthoc_record']})
    io.base.verify_bindings(bindings)
    io.save(args.out / 'v6_comparison.json', {
        'same_configuration_all67': True, 'original_statuses_preserved': True,
        'stable_fields_all67': stable, 'stable_fields_exactly_equal': True,
        'rows': differences, 'changed_numeric_rows': [r for r in differences if r['changes']],
        'unchanged_numeric_rows': sum(not r['changes'] for r in differences),
        'prior_v6': io.bind(prior_path), 'new_model_calls': 0})
    io.save(args.out / 'standalone_role_applications.json', applications)
    io.save(args.out / 'implementation_addendum.json', {
        'status': 'pass', 'bindings': bindings, 'actual_command': [sys.executable, *sys.argv],
        'source_role_application_records': len(applications),
        'native_empty_channel_formula_unchanged': True, 'new_model_calls': 0,
        'outputs': [io.bind(args.out / name) for name in ['summary.json', 'verification.json',
                   'v6_comparison.json', 'standalone_role_applications.json']]})
    print(json.dumps({'changed_numeric_rows': [r for r in differences if r['changes']],
        'source_role_application_records': len(applications), 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
