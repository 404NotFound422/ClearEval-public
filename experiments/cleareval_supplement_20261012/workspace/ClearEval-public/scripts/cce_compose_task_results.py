"""Compose frozen v3 and reviewed q1 observations without rescoring or changing rows."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as core

ROOT, ART = core.ROOT, core.OUT
DEST = ART / 'expanded_tasks_v4'
Q1 = ART / 'q1_extension_v1'
RAW = ('c_step', 'c_param', 'co_order', 'co_method', 'co_param', 'co_chem',
       's_method', 's_label', 's_trans', 's_time', 'Cor', 'Eff', 'historical_Com')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    sources = {}
    def load(path):
        path = Path(path).resolve()
        sources[str(path)] = sha(path)
        return core.read(path)

    models = load(ART / 'cohort_frozen.json')['models']
    assert len(models) == 13 and len(set(models)) == 13
    reviewed = load(Q1 / 'review.json')
    assert reviewed['status'] == 'complete_pass_for_current_q1_observations_with_explicit_driver_boundary_limits'
    concordance = load(Q1 / 'core_concordance.json')
    assert concordance['pass'] and concordance['compared_observations'] == concordance['matching_observations'] == 36
    assert not concordance['mismatches']
    for path, expected in concordance['source_files'].items():
        assert sha(path) == expected, path
        sources[path] = expected
    core_path = ROOT / 'scripts/cce_validation.py'
    assert sha(core_path) == concordance['core_sha256']
    sources[str(core_path)] = sha(core_path)
    sources[str(Path(__file__).resolve())] = sha(__file__)
    assert load(ART / 'score_batch_verification_idisco.json')['status'] == 'pass'
    old_refs = load(ART / 'reference_recovery/idisco_plus_2016/references_expanded_v3.json')['references']
    q1_refs = load(Q1 / 'references.json')['references']
    assert len(old_refs) == 5 and len(q1_refs) == 1
    assert q1_refs[0]['question_ids'] == [1]
    previous_idisco = next(r for r in old_refs if r['route_id'] == 'iDISCO+')
    assert previous_idisco['steps'] == q1_refs[0]['steps']
    refs = old_refs + q1_refs
    assert len({r['reference_id'] for r in refs}) == 6
    assert {(r['route_id'], tuple(r['route_aliases'])) for r in old_refs} == {(r['route_id'], tuple(r['route_aliases'])) for r in refs}

    products, checks, batches = {}, [], []
    archive_cache = {}
    for threshold in (.6, .7, .8):
        suffix = f't{round(threshold*100):03d}'
        old_path = ART / f'supplement_v2_idisco_{suffix}_per_answer.json'
        q1_path = Q1 / f'{suffix}_per_answer.json'
        old, addition = load(old_path), load(q1_path)
        cfg0 = load(ART / f'supplement_v2_idisco_{suffix}_resolved_config.json')
        cfg1 = load(Q1 / f'{suffix}_resolved_config.json')
        run0 = load(ART / f'supplement_v2_idisco_{suffix}_run.json')
        assert cfg0['run_setting']['actual_threshold'] == cfg1['actual_threshold'] == threshold
        assert cfg0['resolved']['adapter_sha256'] == sha(core_path)
        assert cfg0['run_setting']['segmentation_version'] == cfg1['parser_version']
        assert run0['encoder'] == cfg1['encoder']
        for path, expected in cfg0['run_setting']['batch_input_sha256'].items():
            assert sha(path) == expected, path
            sources[path] = expected
        assert len(old) == 65 and len(addition) == 13
        assert {r['model'] for r in addition} == set(models)
        assert {int(r['question_id']) for r in old} == {2, 21, 22, 23, 248}
        assert all(int(r['question_id']) == 1 for r in addition)
        present = [r for r in addition if r['answer_sha256'] is not None]
        absent = [r for r in addition if r['answer_sha256'] is None]
        assert len(present) == 12 and len(absent) == 1
        assert absent[0]['answer_id'] == 'gemini-3-flash__q1' and absent[0]['step_missing_reason'] == 'answer_missing'
        rows = old + present
        assert len(rows) == len({r['answer_id'] for r in rows}) == 77
        assert len({(r['model'], r['question_id']) for r in rows}) == 77
        for r in rows:
            assert r['threshold'] == threshold and not r['formal_eligible']
            source_refs = old_refs if int(r['question_id']) != 1 else q1_refs
            if r['model'] not in archive_cache:
                ap, sp = Path(r['answer_source']), Path(r['score_source'])
                archive_cache[r['model']] = (
                    {int(a['question_id']): a for a in load(ap)},
                    {int(s['question_id']): s for s in load(sp)})
            answers, scores = archive_cache[r['model']]
            a = answers[int(r['question_id'])]
            assert core.digest(a['model_response']) == r['answer_sha256']
            assert core.digest(a['specific_question']) == r['question_sha256']
            old_route, _ = core.selected_route(a['model_response'], source_refs)
            union_route, _ = core.selected_route(a['model_response'], refs)
            assert old_route == union_route == r.get('route_id')
            old_pool = [v['reference_id'] for v in source_refs if int(r['question_id']) in v['question_ids'] and v['route_id'] == old_route]
            union_pool = [v['reference_id'] for v in refs if int(r['question_id']) in v['question_ids'] and v['route_id'] == union_route]
            assert old_pool == union_pool
            assert (r.get('reference_id') in union_pool) if r['sr'] is not None else not union_pool
            assert bool(core.segment(a['model_response']))
            saved = core.partial_scores(scores[int(r['question_id'])])
            assert all(saved[k] == r[k] for k in RAW)
            expected_com = None if r['sr'] is None else .4*r['sr']+.6*r['c_param']/3
            assert expected_com is None and r['Com'] is None or math.isclose(expected_com, r['Com'], abs_tol=1e-12)
            if expected_com is not None:
                assert math.isclose(r['IA'], min(r[k] for k in ('Com','Cor','Eff')), abs_tol=1e-12)
                assert math.isclose(r['HV'], math.prod(r[k] for k in ('Com','Cor','Eff')), abs_tol=1e-12)
            else:
                assert r['IA'] is None and r['HV'] is None
            checks.append({'answer_id': r['answer_id'], 'threshold': threshold,
                           'full_text_and_stem_identity': True, 'archived_components_preserved': True,
                           'original_core_route_and_candidate_pool_unchanged': True,
                           'route_id': union_route, 'compatible_reference_ids': union_pool,
                           'source_config_hash': r['config_hash']})
        config = {'schema_version': 'frozen-batch-composition-v1', 'threshold': threshold,
                  'source_per_answer_files': [str(old_path), str(q1_path)],
                  'source_config_hashes': [core.digest(cfg0), core.digest(cfg1)],
                  'encoder': run0['encoder'], 'core_sha256': sha(core_path),
                  'scoring_action': 'reuse exact existing rows; no new score calculation',
                  'row_config_hash_policy': 'preserved per original batch, never replaced by composition hash',
                  'reference_file': str(DEST / 'references.json'),
                  'union_candidate_pool_verified_for_actual_answers': True,
                  'q1_driver_limits': concordance['implementation_boundaries'],
                  'formal_eligible': False}
        # Verify row-level config identities without substituting a universal configuration.
        assert {r['config_hash'] for r in old} == {config['source_config_hashes'][0]}
        assert {r['config_hash'] for r in present} == {config['source_config_hashes'][1]}
        base = ART / f'expanded_tasks_v4_{suffix}'
        products[Path(str(base)+'_per_answer.json')] = rows
        products[Path(str(base)+'_resolved_config.json')] = config
        products[DEST / f'{suffix}_grid.json'] = old + addition
        batches.append({'threshold': threshold, 'per_answer_path': str(Path(str(base)+'_per_answer.json')),
                        'config_path': str(Path(str(base)+'_resolved_config.json')), 'grid_n': len(old)+len(addition),
                        'actual_answer_n': len(rows), 'old_answer_n': len(old), 'added_answer_n': len(present),
                        'step_numeric_n': sum(r['sr'] is not None for r in rows),
                        'joint_numeric_n': sum(r['HV'] is not None for r in rows),
                        'reference_insufficient_n': sum(r['step_missing_reason']=='reference_insufficient' for r in rows),
                        'answer_missing_n': len(absent), 'old_and_added_rows_deep_equal': True})
    products[DEST / 'references.json'] = {'schema_version': 'frozen-batch-reference-union-v1', 'references': refs,
        'scope': 'exact union for provenance and actual-case compatible-pool verification; not a rescoring batch'}
    products[DEST / 'verification.json'] = {'status': 'pass', 'rows_checked': len(checks), 'checks': checks,
        'source_checks': 'input hashes, text/stem identities, exact rows, route/pool invariance, raw archive components, CCE arithmetic',
        'new_embeddings': 0, 'new_model_requests': 0, 'new_expert_labels': 0}
    plan = {'schema_version': 'frozen-batch-composition-v1', 'input_sha256': sources,
            'models': models, 'question_ids': [1,2,21,22,23,248],
            'thresholds': [.6,.7,.8], 'missing_answer_policy': 'retain in 78-cell grid, exclude from 77-real-answer file',
            'changes_to_input_rows': 'none', 'score_configuration_policy': 'two original configurations with same encoder/core/threshold/weights; q1 observed core concordance, not global driver equivalence',
            'exploratory_comparison_models': ['gemini-3-flash','gemini-3-pro'],
            'formal_eligible': False}
    products[DEST / 'plan.json'] = plan
    if (DEST / 'run.json').exists():
        prior = core.read(DEST / 'run.json')
        assert core.read(DEST / 'plan.json') == plan, 'Input or composition code changed: use a new version'
        assert all(sha(p) == h for p,h in prior['output_sha256'].items())
        print('Reused complete unchanged frozen composition; 0 new scoring/requests.')
        return
    assert not any(p.exists() for p in products), 'Partial composition requires inspection, not overwrite'
    for path, obj in products.items():
        core.write(path, obj)
        if path.name.endswith('_per_answer.json'):
            core.table(path.with_suffix('.csv'), obj)
    outputs = {str(p): sha(p) for p in products}
    outputs.update({str(p.with_suffix('.csv')): sha(p.with_suffix('.csv')) for p in products if p.name.endswith('_per_answer.json')})
    result = {'completed_utc': datetime.now(timezone.utc).isoformat(), 'status': 'complete_pass',
              'actual_command': subprocess.list2cmdline([sys.executable, *sys.argv]),
              'composition_plan_sha256': sha(DEST / 'plan.json'), 'batches': batches,
              'reference_branches': len(refs), 'reference_families': sorted({r['family_id'] for r in refs}),
              'fixed_model_n': len(models), 'task_n': 6, 'q1_actual_core_concordance': '36/36',
              'new_scoring_rows': 0, 'new_model_requests': 0, 'new_embeddings': 0,
              'new_expert_labels': 0, 'formal_eligible_n': 0, 'output_sha256': outputs}
    core.write(DEST / 'run.json', result)
    print(json.dumps({k: v for k,v in result.items() if k!='output_sha256'}, ensure_ascii=True, indent=2))

if __name__ == '__main__':
    main()
