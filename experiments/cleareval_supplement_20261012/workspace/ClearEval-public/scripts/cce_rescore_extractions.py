"""Offline extraction-to-EGES bridge with immutable trial/configuration bindings.

No model transport is created. build-auto reuses real trials; identity checks the
unaltered extraction; rescore accepts only the existing expert-return contract.
"""
import argparse, ast, copy, csv, hashlib, json, math, pathlib, re, sys, types

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
import cce_judges as judges
import cce_human_wetlab as human

BASE = ROOT / 'artifacts/cce_validation'
DEFAULT_OUT = BASE / 'human_review/rescoring/v3_guarded'
EGES = ['s_method', 's_label', 's_trans', 's_time']
QUALITATIVE = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem', 'Cor']
DEPENDENCIES = {'s_method': {'method_name', 'method_stages'},
    's_label': {'method_name', 'method_stages', 'marker_dict'},
    's_trans': {'method_name', 'method_stages'},
    's_time': {'method_name', 'method_stages', 'clearing_total_time_hours'}}

def read(path): return judges.read(path)
def save(path, value): judges.save(path, value)
def rawsha(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()
def equal(a, b):
    if a is None or b is None: return a is b
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)

def require(condition, message):
    if not condition: raise ValueError(message)

def runtime():
    args = types.SimpleNamespace(question_file=judges.HIST,
        demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json', demand_manifest=None)
    runner, _, registry = judges.runtime(args)
    return runner, registry

def verify_contract(contract, registry):
    for path, expected in contract['files'].items():
        require(judges.filehash(ROOT / path) == expected, 'Frozen judge dependency changed: ' + path)
    require(judges.filehash(ROOT / 'KnowledgeBase/source_registry.json') == contract['source_registry_sha256'], 'Source registry changed')
    require(registry.provenance == contract['demands'], 'Fixed historical task/demand binding changed')

def build_auto(args):
    runner, registry = runtime()
    preflight = read(args.contract)
    contract = preflight.get('contract', preflight)
    verify_contract(contract, registry)
    cases = {c['case_id']: c for c in read(args.cases)['cases']}
    step_data = {r['case_id']: r for r in read(args.steps)}
    trials = [read(p) | {'source_file': str(p)} for p in sorted(args.trials.glob('*.json'))]
    with args.identities.open(encoding='utf-8-sig', newline='') as stream:
        identities = list(csv.DictReader(stream))
    config = {'scope': 'offline_same_legacy_EGES_reviewed_extraction_bridge',
        'judge_contract': contract, 'judge_contract_sha256': judges.digest(contract),
        'step_source_file': str(args.steps), 'step_source_sha256': judges.filehash(args.steps),
        'case_source_file': str(args.cases), 'case_source_sha256': judges.filehash(args.cases),
        'identity_file': str(args.identities), 'identity_file_sha256': judges.filehash(args.identities),
        'bridge_source_sha256': judges.filehash(__file__),
        'human_contract_source_sha256': judges.filehash(ROOT / 'scripts/cce_human_wetlab.py'),
        'trial_selection': {'judge': args.judge, 'repeat_index': 0, 'condition': 'baseline', 'status': 'success'},
        'trial_source_manifest': {str(pathlib.Path(t['source_file']).resolve()): judges.filehash(t['source_file']) for t in trials},
        'step_reference_policy': 'Preserve original per-answer SR/SP/reference and qualitative proposals; rescore only extraction-dependent EGES',
        'raw_text_hash_format': 'raw-utf8-sha256', 'extraction_hash_format': 'cce_human_wetlab.digest sorted-json-default-separators'}
    config_hash = judges.digest(config)
    records, pending = [], []
    for identity in identities:
        candidates = []
        for trial in trials:
            if trial.get('status') != 'success' or trial.get('repeat_index') != 0 or trial.get('judge') != args.judge:
                continue
            case = cases.get(trial['case_id'])
            if not case or case.get('condition') != 'baseline': continue
            if rawsha(case['model_response']) != identity['answer_sha256'] or rawsha(case['specific_question']) != identity['question_sha256']:
                continue
            require(str(case['question_id']) == identity['question_id'], 'Question ID/hash inconsistency')
            expected = judges.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                'protocol': case['model_response'], 'references': case.get('references')})
            require(trial['identity']['input_sha256'] == expected, 'Trial is not bound to exact case/reference input')
            require(trial['identity']['contract_sha256'] == config['judge_contract_sha256'], 'Trial contract differs')
            require(trial['references_sha256'] == judges.digest(case.get('references')), 'Trial reference differs')
            candidates.append((trial, case))
        if not candidates:
            pending.append({'answer_id': identity['answer_id'], 'split': identity['split'],
                'reason': 'No exact successful baseline extraction in the selected frozen trial source; no historical reasoning reconstructed'})
            continue
        require(len(candidates) == 1, 'More than one baseline matches the fixed trial rule')
        trial, case = candidates[0]
        step = step_data[case['case_id']]
        require(step['input_sha256'] == identity['answer_sha256'], 'Step score text binding differs')
        extraction = copy.deepcopy(trial['evaluation']['extraction'])
        runner.validate_teacher_extraction(extraction)
        records.append({'answer_id': identity['answer_id'], 'split': identity['split'],
            'question_id': int(identity['question_id']), 'answer_sha256': identity['answer_sha256'],
            'question_sha256': identity['question_sha256'], 'config_hash': config_hash,
            'extraction': extraction, 'extraction_sha256': human.digest(extraction),
            'case_id': case['case_id'], 'trial_id': trial['trial_id'], 'trial_path': trial['source_file'],
            'trial_file_sha256': judges.filehash(trial['source_file']),
            'judge_input_sha256': trial['identity']['input_sha256'],
            'references_sha256': trial['references_sha256'],
            'sr': step['sr'], 'sp': step['sp'], 'reference_id': step['reference_id'],
            'step_config_sha256': step.get('step_config_sha256'),
            'original_numeric_proposals': trial['preserved_numeric_proposals'],
            'original_quantitative_data': trial['evaluation']['quantitative_data'],
            'extraction_origin': 'actual_prespecified_repeat0_local_baseline_request',
            'new_model_requests': 0})
    obj = {'status': 'actual_auto_records_bound_with_pending_cases', 'scoring_config': config,
        'config_hash': config_hash, 'records': records, 'pending_answers': pending,
        'expert_labels_added': 0, 'new_model_requests': 0}
    destination = args.out / 'auto_inputs.json'
    if destination.exists():
        require(read(destination) == obj, 'Existing auto input/configuration changed; use a new output directory')
    else: save(destination, obj)
    print(judges.canonical({'status': obj['status'], 'actual_auto_records': len(records), 'pending_answers': len(pending), 'new_model_requests': 0}))

def load_auto(args):
    auto = read(args.auto_inputs)
    config = auto['scoring_config']
    require(judges.digest(config) == auto['config_hash'], 'Auto scoring configuration hash mismatch')
    require(judges.filehash(__file__) == config['bridge_source_sha256'], 'Bridge implementation changed')
    require(judges.filehash(ROOT / 'scripts/cce_human_wetlab.py') == config['human_contract_source_sha256'], 'Human return contract implementation changed')
    for kind in ['step_source', 'case_source', 'identity_file']:
        pathkey = kind + '_file' if kind != 'identity_file' else kind
        hashkey = kind + '_sha256' if kind != 'identity_file' else kind + '_sha256'
        require(judges.filehash(config[pathkey]) == config[hashkey], kind + ' input changed')
    runner, registry = runtime()
    verify_contract(config['judge_contract'], registry)
    cases = {c['case_id']: c for c in read(config['case_source_file'])['cases']}
    steps = {r['case_id']: r for r in read(config['step_source_file'])}
    with pathlib.Path(config['identity_file']).open(encoding='utf-8-sig', newline='') as stream:
        identities = {r['answer_id']: r for r in csv.DictReader(stream)}
    require(len({r['answer_id'] for r in auto['records']}) == len(auto['records']), 'Duplicate auto answer identity')
    for record in auto['records']:
        require(record['config_hash'] == auto['config_hash'], 'Auto row configuration differs')
        expected_trial_sha = config['trial_source_manifest'].get(str(pathlib.Path(record['trial_path']).resolve()))
        require(expected_trial_sha is not None and expected_trial_sha == record['trial_file_sha256'], 'Trial path/hash absent from frozen source manifest')
        require(judges.filehash(record['trial_path']) == record['trial_file_sha256'], 'Source trial changed')
        require(human.digest(record['extraction']) == record['extraction_sha256'], 'Auto extraction changed')
        c = cases[record['case_id']]
        require(rawsha(c['model_response']) == record['answer_sha256'], 'Original answer changed')
        require(rawsha(c['specific_question']) == record['question_sha256'], 'Original question changed')
        validate_source_binding(record, read(record['trial_path']), c, steps[record['case_id']],
                                identities[record['answer_id']], config, auto['config_hash'])
    return auto, runner, registry, cases


def validate_source_binding(record, trial, case, step, identity, config, config_hash):
    """Rebind mutable row values directly to already hash-verified source objects."""
    require(record['config_hash'] == config_hash, 'Row configuration differs')
    for key in ('answer_sha256', 'question_sha256', 'split'):
        require(record[key] == identity[key], 'Identity manifest mismatch: ' + key)
    require(record['question_id'] == int(identity['question_id']) == int(case['question_id']), 'Question ID mismatch')
    require(record['case_id'] == trial['case_id'] == trial['identity']['case_id'] == case['case_id'], 'Case identity mismatch')
    require(record['trial_id'] == trial['trial_id'], 'Trial identity mismatch')
    require(trial['status'] == config['trial_selection']['status'] and
            trial['judge'] == config['trial_selection']['judge'] and
            trial['repeat_index'] == config['trial_selection']['repeat_index'] and
            case['condition'] == config['trial_selection']['condition'], 'Trial selection differs')
    expected_input = judges.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                                   'protocol': case['model_response'], 'references': case.get('references')})
    require(record['judge_input_sha256'] == trial['identity']['input_sha256'] == expected_input, 'Judge input mismatch')
    require(trial['identity']['contract_sha256'] == config['judge_contract_sha256'], 'Trial configuration mismatch')
    require(record['references_sha256'] == trial['references_sha256'] == judges.digest(case.get('references')), 'Reference context mismatch')
    require(record['extraction'] == trial['evaluation']['extraction'], 'Extraction differs from actual trial')
    require(record['original_numeric_proposals'] == trial['preserved_numeric_proposals'], 'Numeric proposals differ from actual trial')
    require(record['original_quantitative_data'] == trial['evaluation']['quantitative_data'], 'Quantitative data differ from actual trial')
    require(step['input_sha256'] == record['answer_sha256'], 'Step source text mismatch')
    for key in ('sr', 'sp', 'reference_id', 'step_config_sha256'):
        require(record[key] == step.get(key), 'Step source value mismatch: ' + key)


ITEM_ROOTS = {
    'extraction_method_route': {'method_name', 'method_stages', 'reagent_ri_value'},
    'extraction_tissue_scale': {'sample_ri_value'},
    'extraction_target_marker_relation': {'marker_dict'},
    'extraction_time_stage_unit': {'clearing_total_time_hours', 'protocol_time_hours'},
}


def validate_correction_gate(corrections, labels, packets):
    lookup = {(r['answer_id'], r['item']): r for r in labels}
    require(len(lookup) == len(labels), 'Duplicate review answer/item rows')
    for correction in corrections:
        item = correction['item']; path = correction['field_path'].split('.')
        require(item in ITEM_ROOTS and path[0] in ITEM_ROOTS[item], 'Review item does not authorize this extraction field')
        root = path[0]
        nested_ok = (len(path) == 1 or
                     root == 'marker_dict' and len(path) == 2 and bool(path[1]) or
                     root == 'protocol_time_hours' and len(path) == 2 and path[1].isdigit() or
                     root == 'method_stages' and len(path) in (2, 3) and path[1].isdigit() and
                     (len(path) == 2 or path[2] in {'id', 'method_name', 'quote'}))
        require(nested_ok, 'Nested extraction field path is not permitted')
        reviewed = lookup.get((correction['answer_id'], item), {})
        require(reviewed.get('expert_decision') == '不成立' and reviewed.get('review_status') == 'reviewed', 'No confirmed reviewed extraction error')
        require(bool(reviewed.get('reviewer_id')) and bool(reviewed.get('review_date')) and bool(reviewed.get('source_location', '').strip()), 'Missing review identity/date/source_location')
        require(correction.get('reviewer_id') == reviewed['reviewer_id'] and correction.get('review_date') == reviewed['review_date'], 'Correction reviewer/date differs')
        # Explicit code-point offsets resolve repeated quotations unambiguously.
        location = re.fullmatch(r'(answer_text|task_text):(\d+):(\d+)', reviewed['source_location'].strip())
        require(location is not None, 'source_location must be answer_text:start:end or task_text:start:end')
        kind, start, end = location[1], int(location[2]), int(location[3])
        original = packets[correction['answer_id']][kind]
        require(0 <= start < end <= len(original) and correction.get('source_quote') == original[start:end], 'Source quote/position does not match original text')


def trans_na_cause(status):
    # This legacy status combines unresolved method and absent KB evidence.
    # It cannot distinguish answer omission, extraction failure, or reference gaps.
    if status == 'missing_kb_or_unresolved_method':
        return None, True
    return None, True


def reviewed_no_change_ids(labels, packets, auto_ids):
    """A real completed, affirmative four-item return may support scoped zero change."""
    by_answer = {}
    for row in labels:
        if row['item'] in ITEM_ROOTS:
            require(row['item'] not in by_answer.setdefault(row['answer_id'], {}), 'Duplicate extraction review item')
            by_answer[row['answer_id']][row['item']] = row
    accepted = []
    for answer_id, items in by_answer.items():
        if answer_id not in auto_ids or set(items) != set(ITEM_ROOTS): continue
        if not all(r.get('expert_decision') == '成立' and r.get('review_status') == 'reviewed' for r in items.values()): continue
        identities = {(r.get('reviewer_id'), r.get('review_date')) for r in items.values()}
        require(len(identities) == 1 and all(all(v) for v in identities), 'Completed no-change review needs consistent reviewer/date')
        for row in items.values():
            match = re.fullmatch(r'(answer_text|task_text):(\d+):(\d+)', row.get('source_location', '').strip())
            require(match is not None, 'No-change review requires verifiable source offsets')
            start, end = int(match[2]), int(match[3])
            require(0 <= start < end <= len(packets[answer_id][match[1]]), 'No-change source offset outside original text')
        accepted.append(answer_id)
    return sorted(accepted)


def validate_packet_bindings(packets, originals):
    for aid, record in originals.items():
        require(aid in packets and packets[aid]['answer_id'] == aid, 'Anonymous packet identity mismatch')
        packet = packets[aid]
        for text_key, hash_key in [('answer_text','answer_sha256'), ('task_text','question_sha256')]:
            require(rawsha(packet[text_key]) == packet[hash_key] == record[hash_key], 'Reviewer packet text/source mismatch: ' + text_key)

def recompute(record, extraction, runner, registry, case, mode):
    runner.validate_teacher_extraction(extraction)
    fixed = registry.get(record['question_id'], case['specific_question'])
    snapshot_id = registry.questions[str(record['question_id'])]['question_id']
    meta = runner.QUESTION_META_KB[snapshot_id]
    quantitative = {'method_name': extraction['method_name'], 'tissue_ri_value': meta.get('tissue_ri_value'),
        'total_time_hours': extraction['clearing_total_time_hours'], 'sample_tier': meta.get('tissue_tier_code')}
    for key in ['reagent_ri_value', 'protocol_time_hours', 'method_stages']:
        if key in extraction: quantitative[key] = extraction[key]
    trial = read(record['trial_path'])
    require(fixed == trial['evaluation']['user_preference_vector'], 'Actual trial demand differs from fixed registry')
    effects = runner.calculate_effectiveness_score(quantitative, fixed, runner.MODEL_SPACE_SIGNED,
        extraction['marker_dict'], meta.get('marker_query_targets') or [])
    changed_fields = {k for k in set(extraction) | set(record['extraction'])
        if k not in extraction or k not in record['extraction'] or extraction[k] != record['extraction'][k]}
    original = record['original_numeric_proposals']
    affected = [m for m in EGES if changed_fields & DEPENDENCIES[m]]
    for metric in EGES:
        if metric not in affected:
            require(equal(effects[metric], original[metric]), 'Unaffected EGES component changed: ' + metric)
    if mode == 'identity_replay':
        require(quantitative == record['original_quantitative_data'], 'Identity quantitative inputs differ')
        require(not changed_fields, 'Identity replay received modified extraction')
    raw = {metric: effects[metric] if metric in affected or mode == 'identity_replay' else original[metric] for metric in EGES}
    norm = [(raw['s_method'] / 2.5 + 1) / 2 if raw['s_method'] is not None else None,
        raw['s_label'] / 6 if raw['s_label'] is not None else None,
        raw['s_trans'] / 3 if raw['s_trans'] is not None else None,
        raw['s_time'] / 3 if raw['s_time'] is not None else None]
    eff = sum(norm) / 4 if all(v is not None for v in norm) else None
    com = .4 * record['sr'] + .6 * original['c_param'] / 3 if record['sr'] is not None and original['c_param'] is not None else None
    dims = [com, original['Cor'], eff]
    reasons = {}
    for metric in EGES:
        if raw[metric] is None:
            # Preserve the actual function audit instead of guessing whether a
            # missing extraction represents answer omission or extraction failure.
            trans_category, trans_pending = trans_na_cause(effects.get('_s_trans_status'))
            reasons[metric] = {'category': trans_category if metric == 's_trans' else None,
                'original_status': effects.get('_s_trans_status') if metric == 's_trans' else None,
                'method_identity': effects['method_identity'], 'time_computation': effects['time_computation'] if metric == 's_time' else None,
                'compatibility_audit': effects['compatibility_audit'] if metric == 's_label' else None,
                'cause_classification_pending_when_not_unique': trans_pending if metric == 's_trans' else True}
    return {'answer_id': record['answer_id'], 'split': record['split'], 'question_id': record['question_id'],
        'answer_sha256': record['answer_sha256'], 'question_sha256': record['question_sha256'],
        'config_hash': record['config_hash'], 'extraction_sha256': human.digest(extraction),
        'reference_id': record['reference_id'], 'sr': record['sr'], 'sp': record['sp'],
        **{k: original[k] for k in QUALITATIVE}, **raw,
        **dict(zip(['S_method', 'S_label', 'S_trans', 'S_time'], norm)), 'Com': com, 'Eff': eff,
        'IA': min(dims) if all(v is not None for v in dims) else None,
        'HV': math.prod(dims) if all(v is not None for v in dims) else None,
        'na_reasons': reasons, 'mode': mode, 'changed_extraction_fields': sorted(changed_fields),
        'affected_eges_components': affected, 'source_trial_id': record['trial_id'],
        'qualitative_and_steps_preserved': True, 'formal_eligible': False,
        'upstream_cce_eligible': trial['upstream_cce_eligible'], 'new_model_requests': 0}

def identity(args):
    auto, runner, registry, cases = load_auto(args)
    rows, checks = [], []
    for record in auto['records']:
        result = recompute(record, record['extraction'], runner, registry, cases[record['case_id']], 'identity_replay')
        for metric in EGES + ['Eff']:
            require(equal(result[metric], record['original_numeric_proposals'][metric]), 'Identity score differs: ' + metric)
        rows.append(result)
        checks.append({'answer_id': record['answer_id'], 'source_trial_id': record['trial_id'],
            'all_four_EGES_components_and_Eff_equal_actual_trial': True,
            'same_fixed_demands_and_evidence': True, 'expert_correction_effect': None})
    save(args.out / 'auto_scores.json', {'records': rows})
    save(args.out / 'identity_verification.json', {'status': 'pass' if rows else 'pending_real_auto_extractions',
        'actual_source_extractions': len(rows), 'checks': checks, 'new_model_requests': 0,
        'scope': 'Real-extraction identity replay verifies the software bridge, not expert-reviewed effects or evaluator accuracy'})
    print(judges.canonical({'status': 'identity_replay_equal', 'actual_records': len(rows), 'new_model_requests': 0}))

def rescore(args):
    auto, runner, registry, cases = load_auto(args)
    labels = human.read_csv(args.review)
    packets = {p.stem: read(p) for p in args.packets.glob('A*.json')}
    originals = {r['answer_id']: r for r in auto['records']}
    validate_packet_bindings(packets, originals)
    validate_correction_gate(human.get_records(args.corrections), labels, packets)
    no_change = reviewed_no_change_ids(labels, packets, set(originals))
    no_change_scores = [recompute(originals[aid], originals[aid]['extraction'], runner, registry,
                       cases[originals[aid]['case_id']], 'faithful_reviewed_no_change') for aid in no_change]
    save(args.out / 'reviewed_no_change.json', {
        'status': 'actual_reviewed_no_change_pairs' if no_change else 'needs_completed_affirmative_extraction_review',
        'reviewed_no_change_answers': len(no_change), 'answer_ids': no_change,
        'review_file_sha256': judges.filehash(args.review), 'records': no_change_scores,
        'scope': 'No change within the four prespecified extraction-review items only; unreviewed fields, scientific correctness, steps, and references are not gold.',
        'paired_deltas': [{ 'answer_id': r['answer_id'], 'field': k, 'auto': originals[r['answer_id']]['original_numeric_proposals'].get(k),
            'faithful': r[k], 'delta': 0 if r[k] is not None else None} for r in no_change_scores for k in EGES + ['Eff']],
        'new_model_requests': 0})
    # Revalidate the expert-return gate, quotations, hashes and original values;
    # do not trust a handwritten faithful-inputs file solely because it exists.
    faithful_args = types.SimpleNamespace(review=args.review, corrections=args.corrections,
        auto_extractions=args.auto_inputs, packets=args.packets,
        out=args.out / 'validated_faithful_inputs.json')
    human.faithful_inputs(faithful_args)
    faithful = read(faithful_args.out)
    if args.faithful_inputs and args.faithful_inputs.exists():
        supplied = read(args.faithful_inputs)
        require(supplied == faithful, 'Supplied faithful inputs differ from validated actual expert-return transformation')
    if not faithful.get('applied_corrections'):
        save(args.out / 'faithful_scores.json', {'status': 'reviewed_no_change_in_separate_output' if no_change else 'needs_human_labels', 'records': [],
            'reviewed_no_change_output': 'reviewed_no_change.json',
            'scope': 'This legacy correction branch contains only confirmed-error corrections; never average it as all 20 answers.',
            'expert_corrected_answers': 0, 'paired_expert_effect': None, 'new_model_requests': 0})
        print(judges.canonical({'status': 'needs_human_labels', 'expert_corrected_answers': 0, 'new_model_requests': 0}))
        return
    original = {r['answer_id']: r for r in auto['records']}
    rows = []
    for corrected in faithful['records']:
        base = original[corrected['answer_id']]
        for key in ['answer_sha256', 'question_sha256', 'config_hash', 'trial_id', 'trial_file_sha256']:
            require(corrected[key] == base[key], 'Corrected input binding changed: ' + key)
        require(human.digest(corrected['extraction']) == corrected['extraction_sha256'], 'Corrected extraction hash mismatch')
        rows.append(recompute(base, corrected['extraction'], runner, registry, cases[base['case_id']], 'faithful_reviewed_fields_only'))
    save(args.out / 'faithful_scores.json', {'status': 'reviewed_fields_rescored', 'records': rows,
        'new_model_requests': 0, 'unreviewed_fields_are_not_gold': True})
    print(judges.canonical({'status': 'reviewed_fields_rescored', 'actual_records': len(rows), 'new_model_requests': 0}))

def self_check(args):
    # Execute the actual nested nullable-min helper in an isolated synthetic
    # software check; no biological case or expert label is created.
    tree = ast.parse((ROOT / 'OEQ_run_grading_new.py').read_text(encoding='utf-8'))
    outer = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'calculate_effectiveness_score')
    inner = next(n for n in outer.body if isinstance(n, ast.FunctionDef) and n.name == 'nullable_min')
    ns = {}; exec(compile(ast.Module(body=[inner], type_ignores=[]), '<actual_nullable_min_fixture>', 'exec'), ns)
    f = ns['nullable_min']
    require(f([None, 0.0, 6.0]) == 0.0, 'Known zero must determine the minimum')
    require(f([None, 6.0]) is None and f([]) is None, 'Unknown nonzero minimum must remain NA')
    save(args.out / 'software_fixtures/nullable_min.json', {'scope': 'isolated_software_fixture_not_scientific_data_or_expert_labels',
        'actual_function_ast_sha256': rawsha(ast.unparse(inner)), 'known_zero_with_unknown': 'pass',
        'unknown_without_zero': 'pass', 'empty': 'pass', 'new_model_requests': 0})
    print('Actual nullable-min isolated software checks passed; zero requests.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build-auto', 'identity', 'rescore', 'self-check'])
    parser.add_argument('--out', type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument('--auto-inputs', type=pathlib.Path, default=DEFAULT_OUT / 'auto_inputs.json')
    parser.add_argument('--identities', type=pathlib.Path, default=BASE / 'human_review/private/identity_manifest.csv')
    parser.add_argument('--cases', type=pathlib.Path, default=BASE / 'controls/cases.json')
    parser.add_argument('--steps', type=pathlib.Path, default=BASE / 'controls/step_results.json')
    parser.add_argument('--trials', type=pathlib.Path, default=BASE / 'judges/local_controls/trials')
    parser.add_argument('--contract', type=pathlib.Path, default=BASE / 'judges/local_controls/preflight.json')
    parser.add_argument('--judge', default='local_qwen3_8b')
    parser.add_argument('--review', type=pathlib.Path, default=BASE / 'human_review/reviewer/review_items.csv')
    parser.add_argument('--corrections', type=pathlib.Path, default=BASE / 'human_review/expert_extraction_corrections.json')
    parser.add_argument('--faithful-inputs', type=pathlib.Path)
    parser.add_argument('--packets', type=pathlib.Path, default=BASE / 'human_review/reviewer')
    args = parser.parse_args()
    {'build-auto': build_auto, 'identity': identity, 'rescore': rescore, 'self-check': self_check}[args.command](args)

if __name__ == '__main__':
    main()
