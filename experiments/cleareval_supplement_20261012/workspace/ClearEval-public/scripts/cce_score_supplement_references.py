"""Score frozen supplementary-source candidates while preserving every earlier batch."""
from pathlib import Path
import argparse
import copy
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as scorer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--threshold', type=float, default=.7)
    p.add_argument('--tag', required=True)
    args = p.parse_args()
    if not 0 <= args.threshold <= 1:
        p.error('Threshold must be in [0,1]')
    root, out = scorer.ROOT, scorer.OUT
    reference_path = args.references.resolve()
    references = scorer.read(reference_path)['references']
    assert references and all(r.get('human_confirmation') is None for r in references)
    cohort = scorer.read(out / 'cohort_frozen.json')
    source_files = [out / 'cohort_frozen.json',
                    root / 'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json']
    for model in cohort['models']:
        source_files += [root / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json',
                         root / 'dataset/Q+AR/result' / f'evaluation_results_{model}_1-shot.json']
    config = copy.deepcopy(scorer.read(out / 'pilot_resolved_config.json'))
    config['inputs']['complete_reference_manifest'] = str(reference_path)
    config['resolved'].update(reference_digest=scorer.digest(references),
                             adapter_sha256=scorer.filehash(root / 'scripts/cce_validation.py'))
    config['run_setting'].update(actual_threshold=args.threshold,
        batch_driver_sha256=scorer.filehash(__file__),
        reference_file_sha256=scorer.filehash(reference_path),
        batch_input_sha256={str(path): scorer.filehash(path) for path in source_files},
        batch_scope='supplement_bound_source_extracted_development_pending_expert')
    config_hash = scorer.digest(config)
    qids = [2, 21, 22, 23, 248]
    batch_files = [out / (args.tag + suffix) for suffix in
                   ['_resolved_config.json', '_references.json', '_per_answer.json',
                    '_per_answer.csv', '_step_matches.json', '_run.json']]
    if any(path.exists() for path in batch_files):
        if not all(path.exists() for path in batch_files):
            raise ValueError('Partial batch exists; inspect its artifacts rather than silently overwriting')
        old = scorer.read(batch_files[0])
        if old != config:
            raise ValueError('Frozen batch configuration changed; choose a new batch tag')
        existing = scorer.read(batch_files[2])
        assert len(existing) == 65 and all(r['config_hash'] == config_hash for r in existing)
        assert all(not r['formal_eligible'] for r in existing)
        print(f'{args.tag}: reused unchanged complete 65-answer batch; 0 new requests.')
        return
    rows, details = [], []
    encoder = scorer.Encoder()
    for model in cohort['models']:
        ap = root / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json'
        sp = root / 'dataset/Q+AR/result' / f'evaluation_results_{model}_1-shot.json'
        scores = {str(s['question_id']): s for s in scorer.read(sp)}
        for answer in scorer.read(ap):
            if answer['question_id'] not in qids:
                continue
            step = scorer.score_steps(answer, references, encoder, args.threshold)
            row = scorer.build_row(model, answer, scores.get(str(answer['question_id']), {}),
                                   step, ap, sp, args.threshold, config_hash)
            row['numeric_scope'] = 'supplement_bound_development_provisional_archive_linked'
            rows.append(row)
            details.append({'answer_id': row['answer_id'], **step})
    assert len(rows) == 65 and all(r['formal_eligible'] is False for r in rows)
    scorer.write(batch_files[0], config)
    scorer.write(batch_files[1], {'references': references})
    scorer.write(batch_files[2], rows)
    scorer.table(batch_files[3], rows)
    scorer.write(batch_files[4], details)
    run = {'config_hash': config_hash, 'encoder': encoder.identity, 'answer_n': len(rows),
           'tasks': qids, 'models': cohort['models'],
           'step_scored': sum(r['sr'] is not None for r in rows),
           'source_extracted_reference_versions': len(references),
           'reference_route_families': sorted({r['route_id'] for r in references}),
           'new_api_calls': 0, 'formal_eligible': False,
           'scope': config['run_setting']['batch_scope'],
           'command': ' '.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])}
    scorer.write(batch_files[5], run)
    print(f"{args.tag}: {len(rows)} answers; {run['step_scored']} provisional SR/SP values; 0 new requests.")


if __name__ == '__main__':
    main()
