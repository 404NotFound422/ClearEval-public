"""CLI never contacts a teacher unless run-loopback is explicitly authorized."""
import argparse
import json
from pathlib import Path

from .analysis import analyze
from .execution import import_external, run
from .io import read
from .prepare import load_cases, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--study', required=True)
    p.add_argument('--cases')
    p.add_argument('--builder')
    p.add_argument('--candidate-dir')
    p.add_argument('--judges', required=True)
    p.add_argument('--processors')
    p.add_argument('--prompt')
    p.add_argument('--prompt-builder')
    p.add_argument('--label', required=True)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--code-path', action='append', default=[])
    p.add_argument('--dependency', action='append', default=[])
    r = commands.add_parser('run-loopback')
    r.add_argument('--round', required=True)
    r.add_argument('--max-calls', type=int, required=True)
    r.add_argument('--allow-model-requests', action='store_true')
    r.add_argument('--acknowledge-failures', action='store_true')
    r.add_argument('--retry-failed', action='store_true')
    r.add_argument('--max-seconds', type=float, default=172800)
    e = commands.add_parser('import-external')
    e.add_argument('--round', required=True)
    e.add_argument('--trial-id', required=True)
    e.add_argument('--response', required=True)
    e.add_argument('--receipt', required=True)
    a = commands.add_parser('analyze')
    a.add_argument('--round', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        cases = load_cases(args.cases, args.builder, args.candidate_dir)
        result = {'round': str(prepare(args.study, cases=cases, judges=read(args.judges),
            prompt=Path(args.prompt).read_bytes().decode('utf-8') if args.prompt else '', label=args.label,
            repeats=args.repeats, processors=read(args.processors) if args.processors else None,
            builder=args.builder, code_paths=args.code_path, prompt_builder=args.prompt_builder, dependencies=args.dependency))}
    elif args.command == 'run-loopback':
        result = run(args.round, max_calls=args.max_calls, allow_model_requests=args.allow_model_requests,
            acknowledge_failures=args.acknowledge_failures, retry_failed=args.retry_failed,
            max_seconds=args.max_seconds)
    elif args.command == 'import-external':
        record = import_external(args.round, args.trial_id, args.response, read(args.receipt))
        result = {'trial_id': record['id'], 'status': record['technical_status'],
                  'actual_revision': record['actual_revision']}
    else:
        summary = analyze(args.round)
        # Raw candidates, prompts and teacher outputs stay beside the source data.
        result = {'round_id': summary['round_id'], 'planned_trials': summary['planned_trials'],
            'recorded_attempts': summary['recorded_attempts'],
            'independent_families_observed': summary['independent_families_observed'],
            'scientific_accuracy': None}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
