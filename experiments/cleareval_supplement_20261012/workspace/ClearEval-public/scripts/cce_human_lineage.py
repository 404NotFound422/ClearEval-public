"""Read-only Git-source lineage and descriptive historical-scale comparisons."""
import argparse, collections, csv, hashlib, io, json, pathlib, statistics, subprocess, sys

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/cce_validation/human_review/lineage'
SUMMARY = 'dataset/Q+AR/result/Machine_vs_Human_Summary.json'
EXPORT = 'dataset/Q+AR/result/human_evaluation_scores.json'
COMMITS = ['025f43f', 'f939560', '603f4a9', '3e56968', '09c7564']
BLOCKS = {'completeness': ['c_step', 'c_param'],
          'correctness': ['co_order', 'co_method', 'co_param', 'co_chem'],
          'effectiveness': ['s_method', 's_label', 's_trans', 's_time']}

def sha(data):
    return hashlib.sha256(data.encode('utf-8') if isinstance(data, str) else data).hexdigest()

def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout

def git_source(commit, path):
    full = git('rev-parse', commit).decode().strip()
    blob = git('rev-parse', full + ':' + path).decode().strip()
    raw = git('show', full + ':' + path)
    return raw, {'commit': full, 'path': path, 'blob_sha1': blob,
        'file_sha256': sha(raw), 'bytes': len(raw)}

def read(path): return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def csvsave(path, rows):
    if not rows: return
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
    writer.writeheader(); writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding='utf-8-sig')

def binding(row):
    return str(row['question_id']), sha(row['specific_question']), sha(row['model_response'])

def raw_score(obj, block, metric):
    value = obj.get(block, {}).get(metric, {})
    return value.get('score') if isinstance(value, dict) else value

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    from scipy.stats import pearsonr, spearmanr
    current = read(ROOT / SUMMARY)
    current_by_text = {binding(r): r for r in current}
    assert len(current_by_text) == len(current) == 240
    exported = read(ROOT / EXPORT)
    export_by_id = {(r['model_name'].removesuffix('_1-shot'), str(r['question_id'])): r for r in exported}
    sources, lineage_rows, metadata_snapshots, comparisons, versions = [], [], {}, [], []
    for commit in COMMITS:
        data, source = git_source(commit, SUMMARY)
        rows = json.loads(data.decode('utf-8-sig'))
        sources.append(source)
        assert len(rows) == 240 and len({binding(r) for r in rows}) == 240
        differences = collections.Counter()
        exports_diff = collections.Counter()
        snapshot = []
        for row in rows:
            key = binding(row)
            if key not in current_by_text: raise ValueError('Historical answer/question changed; cannot bind by identifier alone')
            latest = current_by_text[key]
            exported_row = export_by_id[(latest['model_name'], str(latest['question_id']))]
            record = {'historical_model_name': row['model_name'], 'current_model_name': latest['model_name'],
                'question_id': key[0], 'question_sha256': key[1], 'answer_sha256': key[2],
                'binding': 'question_id_and_exact_raw_utf8_question_and_answer_hashes',
                'human_scores': {}, 'archived_machine_scores': {}, 'machine_maxima': {}}
            for block, metrics in BLOCKS.items():
                for metric in metrics:
                    old = raw_score(row['human_evaluation'], block, metric)
                    new = raw_score(latest['human_evaluation'], block, metric)
                    exp = raw_score(exported_row, block, metric)
                    machine = raw_score(row['machine_evaluation'].get('scores', {}), block, metric)
                    maximum = row['machine_evaluation'].get('scores', {}).get(block, {}).get(metric, {}).get('max_score')
                    differences[metric] += old != new
                    exports_diff[metric] += old != exp
                    record['human_scores'][metric] = old
                    record['archived_machine_scores'][metric] = machine
                    record['machine_maxima'][metric] = maximum
                    lineage_rows.append({'source_commit': source['commit'], 'source_blob_sha1': source['blob_sha1'],
                        'source_file_sha256': source['file_sha256'], 'current_model_name': latest['model_name'],
                        'historical_model_name': row['model_name'], 'question_id': key[0],
                        'question_sha256': key[1], 'answer_sha256': key[2], 'metric': metric,
                        'historical_human_score': old, 'current_summary_human_score': new,
                        'current_export_human_score': exp, 'historical_machine_score': machine,
                        'historical_machine_maximum': maximum, 'historical_vs_current_summary_changed': old != new,
                        'historical_vs_export_changed': old != exp, 'human_mapping_applied': False})
            snapshot.append(record)
        metadata_snapshots[commit] = snapshot
        versions.append({'commit': source['commit'], 'hash_bound_answers': len(snapshot),
            'task_count': len({r['question_id'] for r in snapshot}),
            'human_differences_vs_current_summary': dict(differences),
            'human_differences_vs_current_export': dict(exports_diff),
            'human_s_method_observed_range': [min(r['human_scores']['s_method'] for r in snapshot),
                                             max(r['human_scores']['s_method'] for r in snapshot)],
            'machine_s_method_recorded_maxima': sorted({r['machine_maxima']['s_method'] for r in snapshot})})
        for block, metrics in BLOCKS.items():
            for metric in metrics:
                pairs = [(r['archived_machine_scores'][metric], r['human_scores'][metric]) for r in snapshot
                         if isinstance(r['archived_machine_scores'][metric], (int, float)) and isinstance(r['human_scores'][metric], (int, float))]
                machine, human = [p[0] for p in pairs], [p[1] for p in pairs]
                variable = len(set(machine)) > 1 and len(set(human)) > 1
                comparisons.append({'source_commit': source['commit'], 'metric': metric, 'answer_pairs': len(pairs),
                    'distinct_questions': len({r['question_id'] for r in snapshot}),
                    'MAE_original_archived_scale': statistics.mean(abs(m-h) for m, h in pairs),
                    'exact_equal_fraction_original_scale': sum(m == h for m, h in pairs) / len(pairs),
                    'Pearson_original_scale': float(pearsonr(machine, human).statistic) if variable else None,
                    'Spearman_original_scale': float(spearmanr(machine, human).statistic) if variable else None,
                    'scope': 'Historical saved-label descriptive comparison to machine scores in the same Git object; not current evaluator validation',
                    'scale_note': 'Historical operational 0..5 convention; no mapping to current signed semantics' if metric == 's_method' else 'Original archived scale; c_step is not SR',
                    'independent_expert_provenance_confirmed': False})
    evidence = []
    requests = [
        ('f939560', 'validate_smethod_ollama.py', ['(x / 5.0)', '[0, 1, 2, 3, 4, 5]', 'human_score =', 'old_score =']),
        ('f939560', 'compare_teacher_model.py', ['s_method = 5.0 * sim', 'min(5.0, s_method)']),
        ('f939560', 'results/refresh_s_method.py', ['SIGNED method-fit', 'raw score = 2.5', 'OLD s_method:', 'max 5 ->', 'sm["score"] = ns']),
        ('f939560', 'strans_method_suitability_report_v4.py', ['expert_v4 =', 'target_r =', 'for alpha in']),
        ('603f4a9', 'strans_method_suitability_report_v5.py', ['Pearson r', 'EXPERT_SCORES =', '继续调整']),
    ]
    for commit, path, patterns in requests:
        raw, source = git_source(commit, path)
        lines = raw.decode('utf-8-sig').splitlines()
        evidence.append({**source, 'excerpts': [{'line': i, 'text': line} for i, line in enumerate(lines, 1) if any(p in line for p in patterns)]})
    args.out.mkdir(parents=True, exist_ok=True)
    for commit, snapshot in metadata_snapshots.items():
        save(args.out / ('snapshot_' + commit + '.json'), {'scope': 'Metadata, hashes and stored scores only; no protocol reconstruction', 'records': snapshot})
    save(args.out / 'git_sources.json', {'summary_versions': sources, 'scale_and_calibration_evidence': evidence,
        'current_summary_file_sha256': sha((ROOT / SUMMARY).read_bytes()),
        'current_export_file_sha256': sha((ROOT / EXPORT).read_bytes()), 'script_sha256': sha(pathlib.Path(__file__).read_bytes())})
    save(args.out / 'version_summary.json', versions)
    csvsave(args.out / 'per_item_lineage.csv', lineage_rows)
    csvsave(args.out / 'historical_descriptive_comparisons.csv', comparisons)
    original = next(v for v in versions if v['commit'].startswith('025f43f'))
    summary = {'original_answers_hash_bound': original['hash_bound_answers'], 'distinct_questions': original['task_count'],
        'original_human_scores_equal_current_export': all(v == 0 for v in original['human_differences_vs_current_export'].values()),
        'historical_s_method_operational_scale': '0..5 convention explicitly used by archived comparison code',
        'historical_scale_convention_recovered': True, 'original_full_human_rubric_recovered': False,
        'signed_human_mapping': None, 'independent_expert_provenance_confirmed': False,
        'new_expert_labels': 0, 'new_model_requests': 0, 'versions': len(versions)}
    save(args.out / 'summary.json', summary)
    lines = ['# Historical label lineage', '',
        'All 240 records in the original 025f43f Git snapshot bind uniquely to current records by question ID and exact question/answer SHA-256. The model-name difference is the historical `_1-shot` suffix. The original stored human scores match the current standalone export exactly.', '',
        'The current summary changed co_method/co_chem/s_method/s_label/s_trans in 197/214/218/167/220 records. Per-item changes and immutable commit/blob/file identities are recorded separately; later versions are not selected according to their agreement with machine scores.', '',
        'The historical s_method **0..5 operational convention** is recoverable: archived comparison code uses 0..5 bins and the unsigned machine function returns 5 times similarity. A distinct historical migration script changes machine scores to [-2.5,+2.5]. This does not supply an expert-authorized transformation of the human rubric into current signed method-fit semantics. No human score is shifted, and no human Eff/CCE is constructed.', '',
        'The deleted v4 calibration script is available in Git and explicitly blends machine scores while searching a target correlation. The v5 script also declares a target correlation. These records strengthen the existing independence limitation; neither a file label saying expert nor restored provenance establishes independent expert authorship.', '',
        'Historical raw-scale MAE, exact equality, Pearson and Spearman are reported for each saved version against the machine scores stored in the same object. They cover 240 answer pairs sharing 20 questions and are descriptive only. They do not validate the current evaluator or convert old c_step to SR. No historical scoring script was executed.', '',
        'Reproduction: `python scripts/cce_human_lineage.py`. All repository and Git inputs are read only; outputs are confined to this directory. See `git_sources.json`, `version_summary.json`, `per_item_lineage.csv`, and `historical_descriptive_comparisons.csv`.', '']
    (args.out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True))

if __name__ == '__main__':
    main()
