"""Append reviewed conditional ScaleS references; replay 77 archived answers offline.

Preparation requires a hash-bound source-scope review. No core.freeze, judge,
network, old-output mutation, answer editing, or score-dependent case selection.
"""
from __future__ import annotations
import argparse
import copy
import json
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
import cce_expand_references_v6 as previous_driver

ART = ROOT / 'artifacts/cce_validation'
DEST = ART / 'expanded_references_v7'
OLD = ART / 'expanded_references_v6'
SOURCE = ART / 'reference_recovery/development_binding_followup_v1'
QIDS = [1, 2, 21, 22, 23, 248]
THRESHOLDS = [.6, .7, .8]
TARGETS = ['glm4.7-thinking__q21', 'glm4.7-thinking__q22',
           'glm4.7-thinking__q23', 'openai_claude-sonnet-4.6__q21']
CACHES = previous_driver.CACHES + [OLD / 'embedding_cache']
RAW, NUMERIC = helpers.RAW, helpers.NUMERIC
sha, load, bind, write = helpers.sha, helpers.load, helpers.bind, core.write


def verify_files(files):
    for path, expected in files.items():
        assert sha(path) == expected, 'Changed frozen file: ' + str(path)


def no_network(*args, **kwargs):
    raise RuntimeError('v7 source expansion forbids network and judge requests')


def prepare(args):
    if (DEST / 'plan.json').exists():
        verify_plan()
        print('Reused unchanged v7 preparation; no scoring performed.')
        return
    candidate_path = Path(args.candidate).resolve()
    review_path = Path(args.source_review).resolve()
    review = load(review_path)
    assert review['status'] == 'pass' and review['approved_for_conditional_scoring'] is True
    assert review['candidate_sha256'] == sha(candidate_path)
    assert set(review['target_answer_ids']) == set(TARGETS)
    assert review.get('formal_eligible', False) is False
    if review.get('input_sha256'):
        verify_files(review['input_sha256'])
    old_run, old_plan = load(OLD / 'run.json'), load(OLD / 'plan.json')
    verify_files(old_run['output_sha256'])
    verify_files(old_plan['input_sha256'])
    verify_files(load(OLD / 'verification.json')['used_vectors'])
    previous = load(OLD / 'references.json')['references']
    added = load(candidate_path)['references']
    assert len(previous) == 9 and len(added) > 0
    assert {q for r in added for q in r['question_ids']} == {21, 22, 23}
    for ref in added:
        assert ref['route_id'] == 'ScaleS'
        assert set(ref['route_aliases']) <= {'ScaleS', 'Scale S', 'Scale-S'}
        assert ref['steps'] and all(s['text'].strip() for s in ref['steps'])
        assert ref['status'] == 'source_extracted' and ref['human_confirmation'] is None
        assert ref['formal_eligible'] is False
    refs = previous + added
    assert len({r['reference_id'] for r in refs}) == len(refs)
    assert all(sum(q in r['question_ids'] for r in added) == 1 for q in [21, 22, 23])
    sources, anchors = helpers.collect_source_bindings(refs)
    cohort = load(ART / 'cohort_frozen.json')
    models = cohort['models']; assert len(models) == 13
    protected = {int(r['question_id']) for r in load(ART / 'human_review/selection.json')['selection'] if r['split'] == 'audit_holdout'}
    assert len(protected) == 15 and not protected.intersection(QIDS)
    metadata = load(SOURCE / 'plan.json')['metadata_pool']
    target_metadata = [r for r in metadata if r['answer_id'] in TARGETS]
    assert {r['answer_id'] for r in target_metadata} == set(TARGETS)
    assert all(r['route'] == 'ScaleS' for r in target_metadata)
    DEST.mkdir(parents=True, exist_ok=True)
    assert not (DEST / 'run.json').exists()
    write(DEST / 'references.json', {
        'schema_version': 'conditional-reference-expansion-v7', 'references': refs,
        'scope': 'Nine previous branches unchanged; append source-extracted conditional ScaleS postfixed clearing for q21/q22/q23 only. Exact 3 mm duration, requested label performance and long-term outcome remain unconfirmed.',
        'formal_eligible': False, 'human_confirmation': None})
    # Snapshot current accounting, never bind a changing global ledger as frozen input.
    ledger_path = ART / 'judges/request_ledger.jsonl'
    ledger_bytes = ledger_path.read_bytes()
    snapshot = DEST / 'request_ledger_at_preparation.jsonl'
    if snapshot.exists():
        assert snapshot.read_bytes() == ledger_bytes
    else:
        snapshot.write_bytes(ledger_bytes)
    request_n = sum(json.loads(line).get('event') == 'request_started' for line in ledger_bytes.decode('utf-8-sig').splitlines() if line.strip())
    files = [Path(__file__), ROOT / 'scripts/cce_validation.py',
        ROOT / 'scripts/cce_expand_references_v5.py', ROOT / 'scripts/cce_expand_references_v6.py',
        ROOT / 'results/oeq_metrics.py', ART / 'cohort_frozen.json', ART / 'human_review/selection.json',
        candidate_path, review_path, SOURCE / 'plan.json', DEST / 'references.json', snapshot,
        OLD / 'references.json', OLD / 'plan.json', OLD / 'run.json', OLD / 'verification.json']
    for tag in ['t060', 't070', 't080']:
        files += [ART / f'expanded_references_v6_{tag}_per_answer.json',
                  ART / f'expanded_references_v6_{tag}_resolved_config.json',
                  OLD / f'{tag}_step_matches.json', OLD / f'{tag}_grid.json']
    for model in models:
        files += [ROOT / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json',
                  ROOT / 'dataset/Q+AR/result' / f'evaluation_results_{model}_1-shot.json']
    files += [p for p in (core.ASSETS / 'assets/all-mpnet-base-v2').rglob('*') if p.is_file()]
    cache_hashes = {str(p.resolve()): sha(p) for cache in CACHES for p in cache.glob('*.npy')}
    sources.update(cache_hashes)
    for path in files:
        sources[str(path.resolve())] = sha(path)
    sources.update(review.get('input_sha256', {}))
    plan = {
        'schema_version': 'conditional-reference-expansion-v7',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'input_sha256': sources,
        'models': models, 'question_ids': QIDS, 'thresholds': THRESHOLDS,
        'actual_answer_n': 77, 'grid_n': 78, 'target_answer_ids': TARGETS,
        'target_metadata': target_metadata, 'new_reference_ids': [r['reference_id'] for r in added],
        'source_review': bind(review_path), 'candidate_file': bind(candidate_path),
        'reference_family_count_before': len({r['family_id'] for r in previous}),
        'reference_family_count_after': len({r['family_id'] for r in refs}),
        'candidate_new_numeric_answers': 4,
        'expected_changes_before_scoring': {'exact_row_reuse_if_core_equal': 73, 'new_reference_scored_answers': 4},
        'score_policy': 'Unchanged core.score_steps/build_row; archived c_param/Correctness/EGES/NA remain authoritative. No new judge scores.',
        'reuse_policy': 'Reparse all 77 full answers at every threshold; compare old and new complete core objects and pools; exactly reuse 73 old row objects only after numerical and NA equality.',
        'source_scope': 'Conditional ScaleS postfixed clearing branch only; fixed task/sample identities. Unknown 3 mm-specific timing, label support and six-month effectiveness remain pending. No answer-parameter-based route exclusion.',
        'cache_policy': 'All pre-existing caches read-only; missing normalized vectors inferred offline into expanded_references_v7/embedding_cache only.',
        'cached_vectors_read_only': cache_hashes,
        'protected_holdout_qids': sorted(protected), 'holdout_answers_or_scores_decoded': 0,
        'source_anchor_spans_verified_at_freeze': anchors,
        'new_judge_requests': 0, 'new_expert_labels': 0, 'formal_eligible': False,
        'package_ledger_snapshot': bind(snapshot), 'snapshot_request_count': request_n,
        'budget_accounting': 'Snapshot only; this offline batch makes zero judge/API requests.',
        'actual_prepare_command': subprocess.list2cmdline([sys.executable, *sys.argv])}
    write(DEST / 'plan.json', plan)
    print(json.dumps({'status': 'frozen_before_scoring', 'reference_branches': len(refs),
        'targets': 4, 'actual_answers': 77, 'new_judge_requests': 0, 'plan_sha256': sha(DEST / 'plan.json')}))


def verify_plan():
    plan = load(DEST / 'plan.json')
    verify_files(plan['input_sha256'])
    return plan


class LocalEncoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.cache = DEST / 'embedding_cache'; self.cache.mkdir(exist_ok=True)
        self.used, self.memo, self.new, self.access = {}, {}, [], []

    def encode(self, texts):
        result = []
        for text in texts:
            key = core.digest([self.identity, text]) + '.npy'
            if key not in self.memo:
                paths = [p / key for p in CACHES + [self.cache] if (p / key).exists()]
                if paths:
                    path = paths[0]
                    assert all(sha(p) == sha(path) for p in paths)
                    vector = self.np.load(path, allow_pickle=False)
                    origin = 'reused_existing_vector'
                else:
                    path = self.cache / key
                    vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                    self.np.save(path, vector)
                    self.new.append(str(path)); origin = 'new_local_model_inference'
                assert vector.shape == (768,) and self.np.isfinite(vector).all()
                self.memo[key] = vector; self.used[str(path)] = sha(path)
                self.access.append({'path': str(path), 'sha256': sha(path),
                    'text_sha256': core.digest(text), 'origin': origin})
            result.append(self.memo[key])
        return self.np.asarray(result)


def run(args):
    plan = verify_plan()
    if (DEST / 'run.json').exists():
        record = load(DEST / 'run.json')
        assert record['plan_sha256'] == sha(DEST / 'plan.json')
        verify_files(record['output_sha256'])
        verify_files(load(DEST / 'verification.json')['used_vectors'])
        print('Reused unchanged completed v7; no computations or requests.')
        return
    socket.create_connection = no_network; socket.socket.connect = no_network
    old_refs = load(OLD / 'references.json')['references']
    refs = load(DEST / 'references.json')['references']
    assert refs[:len(old_refs)] == old_refs
    source_files, anchors = helpers.collect_source_bindings(refs)
    old_rows = {r['answer_id']: r for r in load(ART / 'expanded_references_v6_t070_per_answer.json')}
    originals, accesses = {}, []
    for model in plan['models']:
        ap = ROOT / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json'
        sp = ROOT / 'dataset/Q+AR/result' / f'evaluation_results_{model}_1-shot.json'
        answers, aa = helpers.authorized_records(ap); scores, ss = helpers.authorized_records(sp)
        accesses += [{'kind': 'answer', **aa}, {'kind': 'score', **ss}]
        for qid, answer in answers.items():
            aid = model + '__q' + str(qid); saved = old_rows[aid]; score = scores[qid]
            assert core.digest(answer['model_response']) == saved['answer_sha256']
            assert core.digest(answer['specific_question']) == saved['question_sha256']
            assert answer['specific_question'] == score['evaluation']['meta_data']['sample_info']
            assert Path(saved['answer_source']).resolve() == ap.resolve()
            assert Path(saved['score_source']).resolve() == sp.resolve()
            originals[aid] = (answer, score, ap, sp)
    assert len(originals) == 77 and set(originals) == set(old_rows)
    for target in plan['target_metadata']:
        assert all(old_rows[target['answer_id']][key] == target[key] for key in ['answer_sha256', 'question_sha256'])
    encoder = LocalEncoder()
    targets = set(TARGETS); outputs, checks, added, batches = {}, [], [], []
    for threshold in THRESHOLDS:
        tag = f't{round(threshold * 100):03d}'
        old_file = ART / f'expanded_references_v6_{tag}_per_answer.json'
        previous_rows = load(old_file)
        previous_steps = {x['answer_id']: {k: v for k, v in x.items() if k != 'answer_id'} for x in load(OLD / f'{tag}_step_matches.json')}
        assert load(ART / f'expanded_references_v6_{tag}_resolved_config.json')['encoder'] == encoder.identity
        cfg = {'schema_version': 'conditional-reference-expansion-v7', 'actual_threshold': threshold,
            'encoder': encoder.identity, 'parser_version': core.VERSION,
            'adapter_sha256': sha(ROOT / 'scripts/cce_validation.py'), 'driver_sha256': sha(__file__),
            'reference_file': str(DEST / 'references.json'), 'reference_file_sha256': sha(DEST / 'references.json'),
            'reference_digest': core.digest(refs), 'plan_sha256': sha(DEST / 'plan.json'),
            'source_per_answer_file': str(old_file), 'source_per_answer_sha256': sha(old_file),
            'source_config_hashes_preserved_on_exact_reused_rows': sorted({r['config_hash'] for r in previous_rows}),
            'archive_component_policy': plan['score_policy'], 'new_reference_scientific_status': plan['source_scope'], 'formal_eligible': False}
        cfg_hash = core.digest(cfg)
        rows, details = [], []
        categories = {'exact_row_reuse': [], 'new_reference_score': []}
        for saved in previous_rows:
            aid = saved['answer_id']; answer, score, ap, sp = originals[aid]; qid = int(answer['question_id'])
            before = core.score_steps(answer, old_refs, encoder, threshold)
            after = core.score_steps(answer, refs, encoder, threshold)
            assert before == previous_steps[aid], ('Old core changed', aid, threshold)
            replay = core.build_row(saved['model'], answer, score, before, ap, sp, threshold, saved['config_hash'])
            assert all(replay[k] == saved[k] for k in replay if k != 'numeric_scope'), ('Old row changed', aid)
            candidate = core.build_row(saved['model'], answer, score, after, ap, sp, threshold, cfg_hash)
            assert all(candidate[k] == saved[k] for k in RAW), ('Archive component changed', aid)
            bp = helpers.pool(old_refs, qid, before['route_id']); apool = helpers.pool(refs, qid, after['route_id'])
            same_numeric = all(candidate[k] == saved[k] for k in NUMERIC)
            same_na = candidate['step_missing_reason'] == saved['step_missing_reason'] and candidate['score_missing_reasons'] == saved['score_missing_reasons']
            if aid in targets:
                assert not bp and len(apool) == 1 and after['reference_id'] in plan['new_reference_ids']
                assert saved['sr'] is None and candidate['sr'] is not None
                category = 'new_reference_score'; row = candidate
                row['numeric_scope'] = 'v7_conditional_reference_expansion_provisional_archive_linked'
                added.append({'threshold': threshold, 'row': row,
                    'reference_hits': sum(m['matched'] for m in after['matches']), 'reference_n': after['reference_n'],
                    'generated_hits': sum(x >= threshold for x in after.get('generated_max_similarity', [])),
                    'generated_n': after['generated_n'], 'reference_truncated': after.get('reference_truncated'),
                    'generated_truncated': after.get('generated_truncated'), 'generated_cjk_steps': after.get('generated_cjk_steps'),
                    'max_generated_similarity': max(after.get('generated_max_similarity', []), default=None),
                    'new_judge_numeric_scores_used': False, 'prior_reference_reason': saved['step_missing_reason'],
                    'new_reference_reason': row['step_missing_reason']})
            else:
                assert before == after and bp == apool and same_numeric and same_na, ('Non-target changed', aid)
                category = 'exact_row_reuse'; row = copy.deepcopy(saved); assert row == saved
            assert row['formal_eligible'] is False
            rows.append(row); details.append({'answer_id': aid, **after}); categories[category].append(aid)
            checks.append({'answer_id': aid, 'threshold': threshold, 'category': category,
                'original_core_equal_to_saved': True, 'archive_components_unchanged': True,
                'numerics_unchanged': same_numeric, 'NA_reasons_unchanged': same_na,
                'old_candidate_pool': [r['reference_id'] for r in bp], 'new_candidate_pool': [r['reference_id'] for r in apool],
                'old_row_config_hash': saved['config_hash'], 'new_row_config_hash': row['config_hash'],
                'raw_answer_and_stem_bound': True})
        assert {k: len(v) for k, v in categories.items()} == {'exact_row_reuse': 73, 'new_reference_score': 4}
        nsr = sum(r['sr'] is not None for r in rows); ncce = sum(r['HV'] is not None for r in rows)
        assert nsr == sum(r['sr'] is not None for r in previous_rows) + 4
        lookup = {r['answer_id']: r for r in rows}
        grid = [lookup.get(r['answer_id'], r) for r in load(OLD / f'{tag}_grid.json')]
        assert len(grid) == 78 and sum(r['answer_sha256'] is None for r in grid) == 1
        base = ART / f'expanded_references_v7_{tag}'
        outputs[Path(str(base) + '_per_answer.json')] = rows
        outputs[Path(str(base) + '_resolved_config.json')] = cfg
        outputs[DEST / f'{tag}_step_matches.json'] = details; outputs[DEST / f'{tag}_grid.json'] = grid
        batches.append({'threshold': threshold, 'per_answer_path': str(Path(str(base) + '_per_answer.json')),
            'config_path': str(Path(str(base) + '_resolved_config.json')), 'actual_answers': 77,
            'numeric_SR': nsr, 'numeric_candidate_CCE': ncce,
            'reference_insufficient': sum(r['step_missing_reason'] == 'reference_insufficient' for r in rows),
            'missing_grid_slots': 1, 'categories': categories, 'other_73_numeric_and_NA_unchanged': True})
    assert len(checks) == 231 and len(added) == 12
    verification = {'status': 'pass', 'actual_answers': 77, 'thresholds': 3,
        'core_old_and_new_result_comparisons': 231, 'checks': checks,
        'used_vectors': encoder.used, 'vector_access': encoder.access, 'new_embeddings': len(encoder.new),
        'new_embedding_paths': encoder.new, 'cached_vectors_read_only': plan['cached_vectors_read_only'],
        'actual_archive_access': accesses, 'source_files_rehashed': source_files, 'source_spans_verified': anchors,
        'network_disabled': True, 'new_judge_requests': 0, 'holdout_records_decoded': 0, 'expert_labels_added': 0,
        'scope': 'Conditional source coverage and software identity only. No expert validation, label sufficiency or long-term outcome confirmation.'}
    outputs[DEST / 'verification.json'] = verification; outputs[DEST / 'added_answer_results.json'] = added
    assert not any(p.exists() for p in outputs), 'Output exists; do not overwrite.'
    verify_plan(); verify_files(encoder.used)
    for path, obj in outputs.items():
        write(path, obj)
        if path.name.endswith('_per_answer.json'):
            core.table(path.with_suffix('.csv'), obj)
    output_hashes = {str(p): sha(p) for p in outputs}
    output_hashes.update({str(p.with_suffix('.csv')): sha(p.with_suffix('.csv')) for p in outputs if p.name.endswith('_per_answer.json')})
    record = {'status': 'complete_pass', 'completed_utc': datetime.now(timezone.utc).isoformat(),
        'plan_sha256': sha(DEST / 'plan.json'), 'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv]),
        'cwd': str(Path.cwd()), 'batches': batches, 'reference_branches': len(refs),
        'source_families': sorted({r['family_id'] for r in refs}), 'actual_answers': 77, 'task_n': 6, 'model_n': 13,
        'new_numeric_answer_count': 4, 'new_numeric_answer_threshold_observations': 12,
        'other_73_numeric_NA_unchanged_each_threshold': True, 'exact_row_reuse_each_threshold': 73,
        'new_embeddings': len(encoder.new), 'cached_unique_vectors': len(encoder.used),
        'new_judge_requests': 0, 'new_expert_labels': 0, 'formal_eligible_count': 0,
        'budget_snapshot_request_count': plan['snapshot_request_count'],
        'archive_score_used': 'Original historical scores; no fresh judge proposals', 'output_sha256': output_hashes}
    write(DEST / 'run.json', record)
    write(DEST / 'actual_commands.json', {'prepare': plan['actual_prepare_command'], 'run': record['actual_command'], 'cwd': str(Path.cwd()), 'new_judge_requests': 0})
    lines = ['# v7 conditional ScaleS source expansion', '',
        'All 77 full archived answers were reparsed at each of three thresholds. The original core, archived components and prior nine references are unchanged.',
        '', 'Each threshold contains 73 byte-equivalent JSON row objects reused after core/pool/numeric/NA checks, plus four source-bound additions. This is a development source-coverage extension, not scientific confirmation.',
        '', '| Threshold | Numeric SR | Candidate CCE | Reference NA |', '|---:|---:|---:|---:|']
    lines += [f"| {b['threshold']} | {b['numeric_SR']} | {b['numeric_candidate_CCE']} | {b['reference_insufficient']} |" for b in batches]
    lines += ['', 'Exact 3 mm timing, marker compatibility and six-month performance remain unconfirmed. No new task, model answer, expert label or judge request was created.',
        '', '[Plan](plan.json), [references](references.json), [verification](verification.json), [new answer results](added_answer_results.json), [run](run.json), [actual commands](actual_commands.json).']
    (DEST / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'complete_pass', 'actual_answers': 77, 'rows_checked': 231,
        'numeric_SR_by_threshold': [b['numeric_SR'] for b in batches],
        'numeric_CCE_by_threshold': [b['numeric_candidate_CCE'] for b in batches],
        'exact_reuse_each_threshold': 73, 'new_answer_scored': 4,
        'new_judge_requests': 0, 'new_embeddings': len(encoder.new)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run'])
    parser.add_argument('--candidate', default=str(SOURCE / 'candidate_references.json'))
    parser.add_argument('--source-review', default=str(DEST / 'source_scope_review.json'))
    args = parser.parse_args()
    {'prepare': prepare, 'run': run}[args.command](args)
