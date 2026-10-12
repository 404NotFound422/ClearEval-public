"""Offline reference-pool diagnostic on all six frozen deletion-control texts.

The original v3 diagnostic and full-pipeline judge results remain immutable.
No judge, expert label, answer edit, or scientific eligibility claim is added.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import math
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_validation as core
import cce_expand_references_v5 as helpers

ART = ROOT / 'artifacts/cce_validation'
DEST = ART / 'controls/paired_route_ablation_v7'
OLD = ART / 'controls/paired_route_ablation_v3'
CONTROLS = ART / 'judges/local_controls_supplement_v2'
V7 = ART / 'expanded_references_v7'
OLD_REFS = ART / 'reference_recovery/idisco_plus_2016/references_expanded_v3.json'
THRESHOLDS = [.6, .7, .8]
CACHES = [ART / 'embedding_cache', ART / 'judges/local_alternative_q1_v1/embedding_cache',
    ART / 'expanded_references_v5/embedding_cache', ART / 'expanded_references_v6/embedding_cache',
    V7 / 'embedding_cache']
load, save, sha = core.read, core.write, core.filehash


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def equal(a, b):
    return a == b if a is None or b is None else math.isclose(a, b, rel_tol=0, abs_tol=1e-12)


def verify_hashes(values):
    for path, expected in values.items():
        require(sha(path) == expected, 'frozen_file_changed:' + str(path))


def record(action, **extra):
    path = DEST / 'execution_commands.json'
    records = load(path) if path.exists() else []
    records.append({'utc': datetime.now(timezone.utc).isoformat(), 'action': action,
        'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv]),
        'cwd': str(ROOT), 'driver_sha256': sha(__file__), 'new_judge_requests': 0, **extra})
    save(path, records)


def selected_inputs():
    cases = {r['case_id']: r for r in load(CONTROLS / 'cases.json')['cases']}
    pairs = [p for p in load(CONTROLS / 'paired_results.json') if p['condition'] == 'necessary_step_deletion']
    require(len(pairs) == 3 and sorted(p['question_id'] for p in pairs) == [2, 21, 22], 'original_fixed_pairs_changed')
    require([p['pair_id'] for p in pairs] == load(OLD / 'plan.json')['pair_ids'], 'old_diagnostic_selection_changed')
    return pairs, cases


def design():
    DEST.mkdir(parents=True, exist_ok=True)
    pairs, cases = selected_inputs()
    protected_paths = sorted(p for p in OLD.iterdir() if p.is_file())
    protected_paths += [CONTROLS / n for n in ('cases.json', 'paired_results.json', 'step_results.json', 'step_config.json')]
    protected_paths += [OLD_REFS, Path(core.__file__), ROOT / 'scripts/cce_control_route_ablation.py']
    matrix = []
    for pair in pairs:
        for side in ('baseline', 'variant'):
            case = cases[pair[side + '_case_id']]
            require(core.digest(case['model_response']) == case['answer_sha256'], 'case_answer_hash_mismatch')
            require(core.digest(case['specific_question']) == case['question_sha256'], 'case_question_hash_mismatch')
            matrix.append({'pair_id': pair['pair_id'], 'side': side, 'case_id': case['case_id'],
                'question_id': case['question_id'], 'answer_sha256': case['answer_sha256'],
                'question_sha256': case['question_sha256'],
                'full_input_sha256': core.digest(case), 'generated_steps_sha256': core.digest(core.segment(case['model_response']))})
    obj = {'scope': 'prespecified_incremental_reference_pool_only_diagnostic',
        'selection': 'All three existing necessary_step_deletion pairs; preserve all six full texts without edits or score-dependent selection.',
        'matrix': matrix, 'thresholds': THRESHOLDS, 'primary_threshold': .7,
        'old_diagnostic_actual_thresholds': [.7],
        'new_threshold_scope': 'The .6/.8 runs are newly prespecified sensitivity analyses, not claimed as previous v3 runs.',
        'new_reference_path': str(V7 / 'references.json'),
        'eligibility_rule': 'Use only the frozen v7 references whose question_ids contain the existing question; filtered pool additionally requires the unchanged core selected_route.',
        'selection_rule': 'Max SR, then max SP, then first in frozen reference order, exactly as original diagnostic.',
        'comparison': 'Recompute v3 and v7 pools with unchanged core from each full text at all three thresholds; exactly verify old .7 values; retain unchanged records only after direct equality.',
        'no_new_full_pipeline_pair': True, 'new_independent_control_pairs': 0,
        'primary_CCE_modified': False, 'new_judge_requests': 0, 'expert_confirmations': 0,
        'formal_eligible': False, 'scientific_boundary': 'Unfiltered cross-route similarity is not evidence that the selected alternate route satisfies the task. Source conditions and deletion necessity remain unconfirmed by an expert.',
        'protected_input_sha256': {str(p.resolve()): sha(p) for p in protected_paths}}
    path = DEST / 'design_plan.json'
    if path.exists():
        require(load(path) == obj, 'frozen_design_changed')
    else:
        save(path, obj)
    record('design', status='fixed_six_texts_three_thresholds_no_scoring')
    print(json.dumps({'status': 'design_prepared', 'pairs': 3, 'full_texts': 6,
        'thresholds': THRESHOLDS, 'design_sha256': sha(path), 'new_judge_requests': 0}))


def prepare():
    require((DEST / 'design_plan.json').exists(), 'run_design_first')
    design_obj = load(DEST / 'design_plan.json')
    verify_hashes(design_obj['protected_input_sha256'])
    if (DEST / 'plan.json').exists():
        verify_hashes(load(DEST / 'plan.json')['input_sha256'])
        record('prepare', status='unchanged_frozen_plan_reused')
        return
    require((V7 / 'run.json').exists() and (V7 / 'verification.json').exists(), 'v7_full_freeze_and_scoring_not_ready')
    v7_plan, v7_run = load(V7 / 'plan.json'), load(V7 / 'run.json')
    verify_hashes(v7_plan['input_sha256'])
    verify_hashes(v7_run['output_sha256'])
    verify_hashes(load(V7 / 'verification.json')['used_vectors'])
    old_refs, refs = load(OLD_REFS)['references'], load(V7 / 'references.json')['references']
    new_by_id = {r['reference_id']: r for r in refs}
    require(len(new_by_id) == len(refs), 'duplicate_reference_identity')
    require(all(new_by_id.get(r['reference_id']) == r for r in old_refs), 'old_reference_object_changed')
    require(all(r.get('formal_eligible', False) is False for r in refs), 'unexpected_formal_reference')
    pairs, cases = selected_inputs()
    old_ids = {r['reference_id'] for r in old_refs}
    pools = []
    for qid in [2, 21, 22]:
        old_pool = [r['reference_id'] for r in old_refs if qid in r['question_ids']]
        new_pool = [r['reference_id'] for r in refs if qid in r['question_ids']]
        pools.append({'question_id': qid, 'old_candidate_reference_ids': old_pool,
            'new_candidate_reference_ids': new_pool, 'added_reference_ids': [x for x in new_pool if x not in old_ids]})
    source_bindings, anchors = helpers.collect_source_bindings(refs)
    files = [Path(__file__), ROOT / 'scripts/cce_expand_references_v5.py', DEST / 'design_plan.json',
        V7 / 'references.json', V7 / 'plan.json', V7 / 'run.json', V7 / 'verification.json']
    files += [p for p in (core.ASSETS / 'assets/all-mpnet-base-v2').rglob('*') if p.is_file()]
    source_bindings.update(design_obj['protected_input_sha256'])
    source_bindings.update({str(p.resolve()): sha(p) for p in files})
    cache_hashes = {str(p.resolve()): sha(p) for directory in CACHES for p in directory.glob('*.npy')}
    source_bindings.update(cache_hashes)
    ledger = ART / 'judges/request_ledger.jsonl'
    snapshot = DEST / 'request_ledger_at_preparation.jsonl'
    snapshot.write_bytes(ledger.read_bytes())
    source_bindings[str(snapshot.resolve())] = sha(snapshot)
    ledger_count = sum(json.loads(s).get('event') == 'request_started' for s in snapshot.read_text(encoding='utf-8-sig').splitlines() if s.strip())
    plan = {**design_obj, 'status': 'frozen_before_incremental_scoring',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'driver_sha256': sha(__file__),
        'reference_collection_sha256': sha(V7 / 'references.json'),
        'reference_collection_digest': core.digest(refs), 'reference_branches': len(refs),
        'v7_source_review': v7_plan['source_review'], 'source_anchor_spans_verified': anchors,
        'question_candidate_pools': pools, 'input_sha256': source_bindings,
        'cache_policy': 'Old caches read only; offline missing vectors written only to this diagnostic embedding_cache.',
        'read_only_cache_sha256': cache_hashes, 'ledger_snapshot': bind(snapshot),
        'package_requests_at_preparation': ledger_count,
        'budget_scope': 'Zero judge calls by this offline driver; unrelated concurrent accounting is not asserted unchanged.'}
    save(DEST / 'plan.json', plan)
    record('prepare', status='frozen_before_scoring', plan_sha256=sha(DEST / 'plan.json'))
    print(json.dumps({'status': 'frozen_before_scoring', 'reference_branches': len(refs),
        'plan_sha256': sha(DEST / 'plan.json'), 'new_judge_requests': 0}))


class Encoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.cache = DEST / 'embedding_cache'
        self.cache.mkdir(exist_ok=True)
        self.memo, self.used, self.new = {}, {}, []

    def encode(self, texts):
        vectors = []
        for text in texts:
            key = core.digest([self.identity, text]) + '.npy'
            if key not in self.memo:
                found = [p / key for p in CACHES + [self.cache] if (p / key).exists()]
                if found:
                    path = found[0]
                    require(all(sha(p) == sha(path) for p in found), 'cached_vector_conflict')
                    vector = self.np.load(path, allow_pickle=False)
                else:
                    path = self.cache / key
                    vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                    self.np.save(path, vector)
                    self.new.append(str(path))
                require(vector.shape == (768,) and self.np.isfinite(vector).all(), 'invalid_cached_vector')
                self.memo[key], self.used[str(path)] = vector, sha(path)
            vectors.append(self.memo[key])
        return self.np.asarray(vectors)


def no_network(*args, **kwargs):
    raise RuntimeError('This offline diagnostic forbids network and judge requests')


def score():
    plan = load(DEST / 'plan.json')
    verify_hashes(plan['input_sha256'])
    if (DEST / 'summary.json').exists():
        verify_hashes(load(DEST / 'verification.json')['output_sha256'])
        verify_hashes(load(DEST / 'verification.json')['used_vectors'])
        record('score', status='successful_unchanged_results_reused')
        print(json.dumps({'status': 'reused_verified_results', 'new_judge_requests': 0}))
        return
    socket.create_connection = no_network
    socket.socket.connect = no_network
    encoder = Encoder()
    config = load(CONTROLS / 'step_config.json')
    require(encoder.identity == config['encoder'], 'encoder_identity_changed')
    require(config['adapter_sha256'] == sha(core.__file__), 'original_adapter_changed')
    pairs, cases = selected_inputs()
    old_refs, refs = load(OLD_REFS)['references'], load(V7 / 'references.json')['references']
    old_cases = {r['case_id']: r for r in load(OLD / 'per_case.json')}
    original_steps = {r['case_id']: r['step_result'] for r in load(CONTROLS / 'step_results.json')}
    old_details = {r['case_id']: r for r in load(OLD / 'step_details.json')}
    records, details, comparisons, paired = [], [], [], []
    for threshold in THRESHOLDS:
        tag = f't{round(threshold * 100):03}'
        rows_by_pool = {}
        for pool_name, pool in [('v3', old_refs), ('v7', refs)]:
            rows_by_pool[pool_name] = {}
            for pair in pairs:
                side_rows = {}
                for side in ('baseline', 'variant'):
                    case = cases[pair[side + '_case_id']]
                    filtered = core.score_steps(case, pool, encoder, threshold)
                    require(filtered['generated_steps'] == core.segment(case['model_response']) == original_steps[case['case_id']]['generated_steps'], 'fulltext_parser_drift')
                    require(core.digest(case['model_response']) == case['answer_sha256'], 'input_answer_drift')
                    candidates = [(i, r) for i, r in enumerate(pool) if case['question_id'] in r['question_ids']]
                    scores = [(encoder.score(ref, filtered['generated_steps'], threshold), ref, i) for i, ref in candidates]
                    unfiltered, chosen, index = max(scores, key=lambda item: (item[0]['sr'], item[0]['sp'], -item[2]))
                    row = {'pool': pool_name, 'threshold': threshold, 'pair_id': pair['pair_id'], 'side': side,
                        'case_id': case['case_id'], 'question_id': case['question_id'],
                        'answer_sha256': case['answer_sha256'], 'question_sha256': case['question_sha256'],
                        'declared_route': filtered['route_id'], 'filtered_reference_id': filtered['reference_id'],
                        'filtered_sr': filtered['sr'], 'filtered_sp': filtered['sp'],
                        'unfiltered_reference_id': chosen['reference_id'], 'unfiltered_route': chosen['route_id'],
                        'unfiltered_sr': unfiltered['sr'], 'unfiltered_sp': unfiltered['sp'],
                        'unfiltered_borrows_other_route': chosen['route_id'] != filtered['route_id'],
                        'parsed_step_n': len(filtered['generated_steps']), 'candidate_count': len(candidates),
                        'formal_eligible': False}
                    if pool_name == 'v3' and threshold == .7:
                        old_row = old_cases[case['case_id']]
                        for key in ('filtered_sr', 'filtered_sp', 'unfiltered_sr', 'unfiltered_sp'):
                            require(equal(row[key], old_row[key]), 'old_t070_numeric_not_reproduced:' + key)
                        for key in ('filtered_reference_id', 'unfiltered_reference_id', 'declared_route', 'parsed_step_n'):
                            require(row[key] == old_row[key], 'old_t070_identity_not_reproduced:' + key)
                        require(filtered == old_details[case['case_id']]['filtered'], 'old_t070_full_filtered_result_not_reproduced')
                        require(unfiltered == old_details[case['case_id']]['unfiltered'], 'old_t070_full_unfiltered_result_not_reproduced')
                    records.append(row); side_rows[side] = row; rows_by_pool[pool_name][case['case_id']] = row
                    details.append({'pool': pool_name, 'threshold': threshold, 'case_id': case['case_id'],
                        'filtered': filtered, 'unfiltered': unfiltered, 'unfiltered_reference_id': chosen['reference_id'],
                        'all_candidate_results': [{'reference_id': r['reference_id'], 'score': s, 'fixed_index': i} for s, r, i in scores]})
                pair_row = {'pool': pool_name, 'threshold': threshold, 'pair_id': pair['pair_id'], 'question_id': pair['question_id'], 'formal_eligible': False}
                for mode in ('filtered', 'unfiltered'):
                    for metric in ('sr', 'sp'):
                        for side in ('baseline', 'variant'):
                            pair_row[f'{mode}_{side}_{metric}'] = side_rows[side][f'{mode}_{metric}']
                        a, b = side_rows['variant'][f'{mode}_{metric}'], side_rows['baseline'][f'{mode}_{metric}']
                        pair_row[f'{mode}_delta_{metric}'] = a - b if a is not None and b is not None else None
                a, b = pair_row['unfiltered_delta_sr'], pair_row['filtered_delta_sr']
                pair_row['delta_sr_difference_unfiltered_minus_filtered'] = a - b if a is not None and b is not None else None
                pair_row['any_cross_route_selection'] = any(r['unfiltered_borrows_other_route'] for r in side_rows.values())
                pair_row['unfiltered_baseline_reference'] = side_rows['baseline']['unfiltered_reference_id']
                pair_row['unfiltered_variant_reference'] = side_rows['variant']['unfiltered_reference_id']
                paired.append(pair_row)
        for cid, current in rows_by_pool['v7'].items():
            previous = rows_by_pool['v3'][cid]
            same_metrics = all(equal(current[k], previous[k]) for k in ('filtered_sr', 'filtered_sp', 'unfiltered_sr', 'unfiltered_sp'))
            same_selected = all(current[k] == previous[k] for k in ('filtered_reference_id', 'unfiltered_reference_id', 'declared_route'))
            comparisons.append({'case_id': cid, 'question_id': current['question_id'], 'threshold': threshold,
                'all_four_metrics_unchanged': same_metrics, 'selected_reference_identities_unchanged': same_selected,
                'old_candidate_count': previous['candidate_count'], 'new_candidate_count': current['candidate_count'],
                'filtered_sr_delta_new_minus_old': None if current['filtered_sr'] is None or previous['filtered_sr'] is None else current['filtered_sr'] - previous['filtered_sr'],
                'unfiltered_sr_delta_new_minus_old': current['unfiltered_sr'] - previous['unfiltered_sr'],
                'unfiltered_sp_delta_new_minus_old': current['unfiltered_sp'] - previous['unfiltered_sp'],
                'reuse_status': 'numerically_and_selection_identical_verified' if same_metrics and same_selected else 'incremental_reference_pool_changed_result'})
        for kind, values in [('per_case', records), ('paired_results', paired)]:
            selected = [r for r in values if r['threshold'] == threshold]
            save(DEST / f'{tag}_{kind}.json', selected)
            core.table(DEST / f'{tag}_{kind}.csv', selected)
    verify_hashes(plan['input_sha256'])
    save(DEST / 'per_case.json', records); save(DEST / 'paired_results.json', paired)
    save(DEST / 'step_details.json', details); save(DEST / 'incremental_comparison.json', comparisons)
    summary_rows = []
    for threshold in THRESHOLDS:
        for pool in ('v3', 'v7'):
            ps = [p for p in paired if p['threshold'] == threshold and p['pool'] == pool]
            summary_rows.append({'threshold': threshold, 'pool': pool, 'pairs': len(ps),
                'filtered_deletion_sr_drop_pairs': sum(p['filtered_delta_sr'] is not None and p['filtered_delta_sr'] < 0 for p in ps),
                'unfiltered_deletion_sr_drop_pairs': sum(p['unfiltered_delta_sr'] is not None and p['unfiltered_delta_sr'] < 0 for p in ps),
                'pairs_with_cross_route_selection': sum(p['any_cross_route_selection'] for p in ps),
                'pairs_with_different_deletion_sr_delta': sum(not equal(p['filtered_delta_sr'], p['unfiltered_delta_sr']) for p in ps)})
    summary = {'status': 'completed_offline', 'scope': plan['scope'], 'unique_pairs': 3, 'unique_full_texts': 6,
        'question_ids': [2, 21, 22], 'thresholds': THRESHOLDS, 'primary_threshold': .7,
        'old_actual_thresholds': [.7], 'old_t070_full_step_results_reproduced': True,
        'reference_branches_old': len(old_refs), 'reference_branches_new': len(refs),
        'question_candidate_pools': plan['question_candidate_pools'], 'per_threshold_pool_summary': summary_rows,
        'case_threshold_comparisons': len(comparisons),
        'unchanged_numeric_and_selected_reference_comparisons': sum(r['all_four_metrics_unchanged'] and r['selected_reference_identities_unchanged'] for r in comparisons),
        'changed_numeric_comparisons': sum(not r['all_four_metrics_unchanged'] for r in comparisons),
        'new_judge_requests': 0, 'new_independent_control_pairs': 0, 'expert_confirmations': 0,
        'formal_eligible': False, 'primary_CCE_modified': False, 'protected_inputs_unchanged': True,
        'encoder': encoder.identity, 'used_vector_count': len(encoder.used), 'new_local_vectors': len(encoder.new),
        'plan_sha256': sha(DEST / 'plan.json'), 'scientific_limitation': plan['scientific_boundary']}
    save(DEST / 'summary.json', summary)
    outputs = [p for p in DEST.glob('*.json') if p.name not in ('verification.json', 'execution_commands.json', 'plan.json', 'design_plan.json')]
    outputs += list(DEST.glob('*.csv'))
    save(DEST / 'verification.json', {'status': 'pass', 'input_sha256': plan['input_sha256'],
        'used_vectors': encoder.used, 'new_vectors': encoder.new,
        'output_sha256': {str(p.resolve()): sha(p) for p in outputs},
        'six_full_texts_reparsed': True, 'old_t070_exact_full_result_replay': True,
        'new_judge_requests': 0, 'network_forbidden_during_scoring': True,
        'command': subprocess.list2cmdline([sys.executable, *sys.argv])})
    lines = ['# 删除配对：v7 参考池增量诊断', '',
        '固定复用 q2、q21、q22 三对，共六份原编辑后全文；没有新增独立配对、judge 请求或专家标签。旧 v3 仅 δ=0.7，此次新增预定 δ=0.6/0.8 敏感性分析。', '',
        '| 阈值 | 池 | 筛选后 SR 下降对数 | 未筛选 SR 下降对数 | 跨路线选择对数 |',
        '|---|---|---:|---:|---:|']
    lines += [f"| {r['threshold']} | {r['pool']} | {r['filtered_deletion_sr_drop_pairs']} | {r['unfiltered_deletion_sr_drop_pairs']} | {r['pairs_with_cross_route_selection']} |" for r in summary_rows]
    lines += ['', '每份全文均用原解析器重解析；旧 δ=0.7 的完整筛选和未筛选结果精确重现。新增参考只改变离线候选池，未回填原 CCE；跨路线步骤相似度不能证明任务适用、合理替代或删除必要性。', '',
        '[逐对结果](paired_results.json) · [候选池增量](incremental_comparison.json) · [步骤明细](step_details.json) · [冻结计划](plan.json) · [实际命令](execution_commands.json)', '']
    (DEST / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    record('score', status='completed_offline', case_thresholds=18, new_local_vectors=len(encoder.new))
    print(json.dumps({k: summary[k] for k in ('status', 'unique_pairs', 'unique_full_texts', 'changed_numeric_comparisons', 'new_judge_requests', 'new_local_vectors')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['design', 'prepare', 'score'])
    args = parser.parse_args()
    {'design': design, 'prepare': prepare, 'score': score}[args.action]()
