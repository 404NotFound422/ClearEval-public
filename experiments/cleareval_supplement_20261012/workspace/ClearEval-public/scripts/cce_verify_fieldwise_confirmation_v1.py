"""Replay completed confirmation outputs from their saved raw responses; no requests."""
from __future__ import annotations
import argparse, contextlib, io, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_fieldwise_confirmation_v1 as batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=batch.OUT)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan, cases, matrix, contract = batch.validate(args.batch)
    results = []
    for case, row in zip(cases, matrix):
        tid = row['planned_trial_id']
        folder = args.batch / 'run' / 'attempts' / f'{tid}_1'
        trial = args.batch / 'run' / 'trials' / f'{tid}.json'
        item = {'anonymous_answer_id': row['anonymous_answer_id'], 'status': 'not_terminal', 'numerical_replay': 'not_performed'}
        if trial.exists():
            result = batch.j.read(trial)
            batch.base.verify_bindings(result.get('bound_artifacts', []))
            item['status'] = result['status']
            if result['status'] == 'success':
                doc = batch.j.read(row['assets']['source_document']['path'])
                raw = (folder/'raw_response.txt').read_bytes().decode('utf8')
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    conversion, numeric = batch.fw.evaluate(raw, doc, case, row['step'])
                item['conversion_exact'] = conversion == batch.j.read(folder/'conversion.json')
                item['numeric_exact'] = numeric == batch.j.read(folder/'numeric.json')
                item['metrics_exact'] = numeric['metrics'] == result['metrics']
                item['numerical_replay'] = 'pass' if all(item[k] for k in ['conversion_exact', 'numeric_exact', 'metrics_exact']) else 'mismatch'
            elif (folder/'retained_direct_components.json').exists():
                doc = batch.j.read(row['assets']['source_document']['path'])
                raw = (folder/'raw_response.txt').read_bytes().decode('utf8')
                metrics, details = batch.recover_direct(raw, doc, row['step'])
                item['metrics_exact'] = metrics == result['metrics']
                item['numerical_replay'] = 'retained_direct_pass' if item['metrics_exact'] else 'mismatch'
        results.append(item)
    report = {'new_requests': 0, 'rows': results,
              'full_replay_pass': sum(r['numerical_replay'] == 'pass' for r in results),
              'retained_direct_replay_pass': sum(r['numerical_replay'] == 'retained_direct_pass' for r in results),
              'mismatches': sum(r['numerical_replay'] == 'mismatch' for r in results),
              'plan': batch.bind(args.batch/'plan.json'), 'script': batch.bind(Path(__file__)),
              'actual_command': [sys.executable, *sys.argv]}
    batch.base.verify_bindings(plan['frozen_inputs'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k: report[k] for k in ['new_requests', 'full_replay_pass', 'retained_direct_replay_pass', 'mismatches']}))
    return 1 if report['mismatches'] else 0


if __name__ == '__main__': sys.exit(main())
