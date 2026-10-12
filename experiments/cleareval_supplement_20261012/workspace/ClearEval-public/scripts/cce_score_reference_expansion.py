"""Frozen reference-expansion batch using the unchanged source-bound scorer.

Preserves the completed first-source pilot, its configuration, and successful judge
trials. New reference inputs get new score and configuration identities.
"""
from pathlib import Path
import argparse
import copy
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as scorer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threshold', type=float, default=.7)
    parser.add_argument('--tag', default='two_source_t070')
    args = parser.parse_args()
    root, out = scorer.ROOT, scorer.OUT
    reference_path = out / 'reference_recovery/references_two_source_development.json'
    references = scorer.read(reference_path)['references']
    assert len(references) == 2
    config = copy.deepcopy(scorer.read(out / 'pilot_resolved_config.json'))
    config['inputs']['complete_reference_manifest'] = str(reference_path)
    config['resolved'].update(reference_digest=scorer.digest(references),
                             adapter_sha256=scorer.filehash(root / 'scripts/cce_validation.py'))
    config['run_setting'].update(actual_threshold=args.threshold, batch_driver_sha256=scorer.filehash(__file__),
                                 batch_scope='two_source_development_expansion_supplement_completeness_pending')
    config_hash = scorer.digest(config)
    cohort = scorer.read(out / 'cohort_frozen.json')
    qids = [2,21,22,23,248]
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
            row = scorer.build_row(model, answer, scores.get(str(answer['question_id']), {}), step, ap, sp, args.threshold, config_hash)
            row['numeric_scope'] = 'two_source_development_provisional_archive_linked'
            rows.append(row)
            details.append({'answer_id': row['answer_id'], **step})
    assert len(rows) == 65 and all(r['formal_eligible'] is False for r in rows)
    scorer.write(out / (args.tag + '_resolved_config.json'), config)
    scorer.write(out / (args.tag + '_references.json'), {'references': references})
    scorer.write(out / (args.tag + '_per_answer.json'), rows)
    scorer.table(out / (args.tag + '_per_answer.csv'), rows)
    scorer.write(out / (args.tag + '_step_matches.json'), details)
    run = {'config_hash': config_hash, 'encoder': encoder.identity, 'answer_n': len(rows),
           'tasks': qids, 'models': cohort['models'], 'step_scored': sum(r['sr'] is not None for r in rows),
           'source_extracted_route_candidates': 2, 'new_api_calls': 0, 'formal_eligible': False,
           'scope': config['run_setting']['batch_scope'],
           'command': f'{sys.executable} scripts/cce_score_reference_expansion.py --threshold {args.threshold} --tag {args.tag}'}
    scorer.write(out / (args.tag + '_run.json'), run)
    print(f"{args.tag}: {len(rows)} answers; {run['step_scored']} provisional SR/SP values; 0 new requests.")


if __name__ == '__main__':
    main()
