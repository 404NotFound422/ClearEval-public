"""Offline numerical cross-check of v7 using frozen cached-vector dot products.

Uses original route/segmentation functions but never Encoder, score_steps, judges,
network, or inference. Separately recomputes similarity maxima and CCE algebra.
"""
from __future__ import annotations
import hashlib
import json
import math
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_validation as core
import cce_expand_references_v5 as helpers

ART = ROOT / 'artifacts/cce_validation'
DEST = ART / 'expanded_references_v7'
OLD = ART / 'expanded_references_v6'
load, sha = helpers.load, helpers.sha


def deny(*args, **kwargs):
    raise RuntimeError('v7 verification forbids network and model requests')


def main():
    socket.create_connection = deny; socket.socket.connect = deny
    import numpy as np
    plan = load(DEST / 'plan.json'); run = load(DEST / 'run.json')
    verification = load(DEST / 'verification.json')
    assert run['plan_sha256'] == sha(DEST / 'plan.json')
    for group in [plan['input_sha256'], run['output_sha256'], verification['used_vectors']]:
        for path, expected in group.items():
            assert sha(path) == expected, path
    refs = load(DEST / 'references.json')['references']
    previous_refs = load(OLD / 'references.json')['references']
    assert refs[:len(previous_refs)] == previous_refs
    references = {r['reference_id']: r for r in refs}
    new_references = [r for r in refs if r['reference_id'] in plan['new_reference_ids']]
    assert {q for r in new_references for q in r['question_ids']} == {21, 22, 23}
    originals, archive_accesses = {}, []
    for model in plan['models']:
        ap = ROOT / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json'
        sp = ROOT / 'dataset/Q+AR/result' / f'evaluation_results_{model}_1-shot.json'
        answers, aaccess = helpers.authorized_records(ap)
        scores, saccess = helpers.authorized_records(sp)
        archive_accesses += [aaccess, saccess]
        for qid, answer in answers.items():
            originals[model + '__q' + str(qid)] = (answer, scores[qid])
    assert len(originals) == 77
    by_basename = {}
    for path, expected in verification['used_vectors'].items():
        name = Path(path).name
        if name in by_basename:
            assert by_basename[name][1] == expected
        by_basename[name] = (Path(path), expected)
    vectors = {}
    def vector(text, identity):
        name = core.digest([identity, text]) + '.npy'
        if name not in vectors:
            path, expected = by_basename[name]
            assert sha(path) == expected
            value = np.load(path, allow_pickle=False)
            assert value.shape == (768,) and np.isfinite(value).all()
            assert abs(float(np.linalg.norm(value)) - 1.) < 1e-5
            vectors[name] = value
        return vectors[name]

    checks, threshold_counts = [], []
    for threshold in [.6, .7, .8]:
        tag = f't{round(threshold * 100):03d}'
        rows = load(ART / f'expanded_references_v7_{tag}_per_answer.json')
        old = {r['answer_id']: r for r in load(ART / f'expanded_references_v6_{tag}_per_answer.json')}
        details = {r['answer_id']: r for r in load(DEST / f'{tag}_step_matches.json')}
        cfg = load(ART / f'expanded_references_v7_{tag}_resolved_config.json')
        grid = load(DEST / f'{tag}_grid.json')
        assert len(rows) == 77 and len(grid) == 78
        assert {r['answer_id'] for r in rows} == set(originals)
        assert sum(r['answer_sha256'] is None for r in grid) == 1
        reused, new, numeric, missing = 0, 0, 0, 0
        for row in rows:
            aid = row['answer_id']; answer, archive = originals[aid]; detail = details[aid]
            assert hashlib.sha256(answer['model_response'].encode('utf-8')).hexdigest() == row['answer_sha256']
            assert hashlib.sha256(answer['specific_question'].encode('utf-8')).hexdigest() == row['question_sha256']
            assert archive['evaluation']['meta_data']['sample_info'] == answer['specific_question']
            assert core.partial_scores(archive) == {k: row[k] for k in core.partial_scores(archive)}
            parsed = core.segment(answer['model_response'])
            route, declaration = core.selected_route(answer['model_response'], refs)
            assert detail['generated_steps'] == parsed and detail['route_id'] == route
            assert detail['declared_route'] == declaration and row['route_id'] == route
            pool = [r for r in refs if int(answer['question_id']) in r['question_ids'] and r['route_id'] == route]
            sr = sp = None
            if pool:
                candidates = []
                for order, ref in enumerate(pool):
                    if parsed:
                        rv = np.asarray([vector(s['text'], cfg['encoder']) for s in ref['steps']])
                        gv = np.asarray([vector(s['text'], cfg['encoder']) for s in parsed])
                        matrix = rv @ gv.T
                        rmax, gmax = matrix.max(axis=1), matrix.max(axis=0)
                        rsr = float(np.count_nonzero(rmax >= threshold) / len(rmax))
                        rsp = float(np.count_nonzero(gmax >= threshold) / len(gmax))
                    else:
                        matrix = None; rmax = gmax = []
                        rsr = rsp = 0.
                    candidates.append((rsr, rsp, -order, ref, matrix, rmax, gmax))
                chosen = max(candidates, key=lambda x: x[:3])
                sr, sp, _, ref, matrix, rmax, gmax = chosen
                assert row['reference_id'] == detail['reference_id'] == ref['reference_id']
                assert detail['candidate_reference_ids'] == [r['reference_id'] for r in pool]
                assert detail['reference_n'] == len(ref['steps']) and detail['generated_n'] == len(parsed)
                if parsed:
                    assert detail['generated_max_similarity'] == [float(v) for v in gmax]
                    assert len(detail['matches']) == len(ref['steps'])
                    for index, match in enumerate(detail['matches']):
                        assert match['reference_index'] == index
                        assert match['reference_text'] == ref['steps'][index]['text']
                        assert match['generated_index'] == int(matrix[index].argmax())
                        assert match['generated_text'] == parsed[match['generated_index']]['text']
                        assert match['similarity'] == float(rmax[index])
                        assert match['matched'] == bool(rmax[index] >= threshold)
                numeric += 1
            else:
                assert detail['step_missing_reason'] == row['step_missing_reason'] == 'reference_insufficient'
                assert row['reference_id'] is None
                missing += 1
            assert row['sr'] == detail['sr'] == sr and row['sp'] == detail['sp'] == sp
            com = .4 * sr + .6 * row['c_param'] / 3 if sr is not None and row['c_param'] is not None else None
            dims = [com, row['Cor'], row['Eff']]
            complete = all(x is not None for x in dims)
            assert row['Com'] == com
            assert row['IA'] == (min(dims) if complete else None)
            assert row['HV'] == (math.prod(dims) if complete else None)
            assert all(row[k] == old[aid][k] for k in helpers.RAW)
            assert row['formal_eligible'] is False
            if aid in plan['target_answer_ids']:
                assert row['reference_id'] in plan['new_reference_ids'] and old[aid]['sr'] is None
                assert row['config_hash'] == core.digest(cfg); new += 1
            else:
                assert row == old[aid]; reused += 1
            checks.append({'answer_id': aid, 'threshold': threshold, 'source_identity': True,
                'original_core_segmentation_and_route': True, 'cached_dot_product_SR_SP': True,
                'matches_and_reference_order': True, 'archived_components_unchanged': True,
                'CCE_algebra_and_NA': True, 'exact_old_object_reused': aid not in plan['target_answer_ids']})
        assert (new, reused) == (4, 73)
        threshold_counts.append({'threshold': threshold, 'actual_answers': len(rows),
            'numeric_SR_SP': numeric, 'reference_NA': missing, 'new': new, 'exact_reuse': reused})
    new_paths = verification['new_embedding_paths']
    assert all(Path(p).parent.resolve() == (DEST / 'embedding_cache').resolve() for p in new_paths)
    assert len(new_paths) == len(set(new_paths)) == verification['new_embeddings']
    for path, expected in plan['cached_vectors_read_only'].items():
        assert sha(path) == expected
    report = {'status': 'pass', 'review_kind': 'separate_cached_dot_product_and_algebra_implementation_not_expert_review',
        'verified_utc': datetime.now(timezone.utc).isoformat(), 'checks': checks, 'threshold_counts': threshold_counts,
        'answer_threshold_records': len(checks), 'actual_answers': 77, 'thresholds': 3,
        'new_reference_ids': plan['new_reference_ids'], 'new_embeddings': len(new_paths),
        'existing_cache_files_unchanged': len(plan['cached_vectors_read_only']),
        'unique_cached_vectors_read': len(vectors), 'archive_accesses': archive_accesses,
        'holdout_records_decoded': 0, 'new_judge_requests': 0, 'new_vector_inference': 0,
        'expert_labels_added': 0, 'formal_eligible': False,
        'limits': 'Original core route/segment and original partial_scores reused; similarity matching and CCE arithmetic recomputed separately. Source applicability requires the separate source-scope review.',
        'input_sha256': {str(p): sha(p) for p in [Path(__file__), DEST / 'plan.json', DEST / 'run.json', DEST / 'verification.json', DEST / 'references.json']},
        'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv])}
    assert len(checks) == 231
    target = DEST / 'independent_numeric_review.json'
    assert not target.exists(), 'Do not overwrite an existing independent review.'
    core.write(target, report)
    print(json.dumps({'status': 'pass', 'records': len(checks), 'new_requests': 0,
        'counts': threshold_counts, 'review_sha256': sha(target)}))


if __name__ == '__main__':
    main()
