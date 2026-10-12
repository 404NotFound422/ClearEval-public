"""Offline identity, numeric and literal checks of the fixed development v2 run."""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import math
from pathlib import Path
import socket
import statistics
import sys
import textwrap

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import cce_stability_remediation_v2 as prepared
from cce_alternative_development import METRICS
import evaluator_integrity as integrity

BASE = ROOT / 'artifacts/cce_validation/judges'
BATCH = BASE / 'stability_remediation_v2'
OUT = BATCH / 'analysis'
RUN = BATCH / 'run'
OLD = BASE / 'local_stability_supplement_v2'
V1 = BASE / 'stability_remediation_plan_v1'
MODELS = prepared.MODELS
TOL = 1e-12


def no_network(*args, **kwargs):
    raise RuntimeError('offline_analysis_network_disabled')


socket.create_connection = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network


def require(ok, why):
    if not ok: raise ValueError(why)


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def equal(a, b):
    return a is None and b is None or finite(a) and finite(b) and abs(a-b) <= TOL


def table(name, rows):
    if not rows: return
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
    writer.writeheader(); writer.writerows(rows)
    (OUT / name).write_text(stream.getvalue(), encoding='utf-8-sig')


def save(name, obj):
    j.save(OUT / name, obj)


def evidence(case):
    qid = case['question_id']
    label = '**Chosen Labeling:** [GFP (内源)]' if qid == 2 else '**Chosen Labeling:** [GFP (内源), DAPI]'
    ri = 'DBE, RI = 1.562' if qid == 2 else 'DBE (Refractive Index = 1.56)'
    value = 1.562 if qid == 2 else 1.56
    require(label in case['model_response'] and ri in case['model_response'], 'fixed_development_literal_evidence_missing')
    require('c-fos' not in (case['specific_question'] + case['model_response']).casefold(), 'cfos_literal_has_source_support')
    return {'label_quote': label, 'RI_quote': ri, 'explicit_RI': value,
        'label_start': case['model_response'].index(label), 'RI_start': case['model_response'].index(ri),
        'scope': 'Two exposed development answers, literal support only; not an expert scientific-validity audit.'}


def literal_flags(ext, technical, ev):
    keys = ['native_GFP_missing', 'cFos_injected', 'RI_missing', 'RI_numeric_contradiction', 'route_missing', 'route_contradiction']
    if not technical or not isinstance(ext, dict):
        return {**{k: None for k in keys}, 'RI_state': 'not_evaluable_technical_failure', 'marker_state': 'not_evaluable_technical_failure'}
    markers = ext.get('marker_dict')
    require(isinstance(markers, dict), 'successful_extraction_marker_schema_invalid')
    marker_text = j.canonical(markers).casefold()
    ri = ext.get('reagent_ri_value')
    missing = ri is None
    require(missing or finite(ri), 'successful_RI_not_finite_or_null')
    mismatch = not equal(ri, ev['explicit_RI']) if not missing else False
    route = ext.get('method_name')
    return {'native_GFP_missing': 'gfp' not in marker_text, 'cFos_injected': 'c-fos' in marker_text,
        'RI_missing': missing, 'RI_numeric_contradiction': mismatch,
        'RI_state': 'absent_or_null' if missing else 'numeric_contradiction' if mismatch else 'matches_explicit_value',
        'marker_state': 'empty_object' if not markers else 'reported_object',
        'route_missing': route in [None, ''], 'route_contradiction': route not in [None, '', 'FDISCO']}


def derive(proposals, step, technical):
    if not technical: return {m: None for m in METRICS}
    result = dict(proposals)
    result.update(sr=step['sr'], sp=step['sp'])
    result['Com'] = .4*result['sr'] + .6*result['c_param']/3 if finite(result['sr']) and finite(result['c_param']) else None
    dims = [result[k] for k in ('Com', 'Cor', 'Eff')]
    result['IA'] = min(dims) if all(finite(v) for v in dims) else None
    result['HV'] = math.prod(dims) if all(finite(v) for v in dims) else None
    return {m: result[m] for m in METRICS}


def main():
    plan = prepared.frozen_plan()
    require(any(x['command'] == 'run' and x['status'] == 'completed_runner_return' for x in j.read(BATCH / 'actual_execution_commands.json')), 'run_not_confirmed_finished')
    OUT.mkdir(parents=True, exist_ok=True)
    ledger_path = BASE / 'request_ledger.jsonl'
    ledger_before = j.filehash(ledger_path)
    ledger = [r for r in j.ledger_rows(ledger_path) if r.get('event') == 'request_started']
    ledger_map = {r['request_id']: r for r in ledger}
    require(len(ledger_map) == len(ledger), 'duplicate_request_ids')
    frozen_before = {str(p): j.filehash(p) for p in RUN.rglob('*') if p.is_file()}
    cases = {c['case_id']: c for c in j.read(BATCH / 'cases.json')['cases']}
    steps = {r['case_id']: r for r in j.read(OLD / 'step_results.json')}
    evs = {cid: evidence(c) for cid, c in cases.items()}
    original_example = j.read(V1 / 'original_final_example.json')
    preflight = j.read(RUN / 'preflight.json')
    verified_plan = j.read(BATCH / 'preflight_verification.json')
    require(preflight['contract_sha256'] == verified_plan['contract_sha256'] == j.digest(preflight['contract']), 'runtime_contract_changed')
    expected = {r['planned_trial_id']: r['identity'] for r in verified_plan['planned_trials']}
    trials = {t['trial_id']: (p, t) for p in sorted((RUN / 'trials').glob('*.json')) for t in [j.read(p)]}
    receipts = {r['trial_id']: (p, r) for p in sorted((RUN / 'attempts').glob('*/request_receipt.json')) for r in [j.read(p)]}
    require(set(trials) == set(receipts) == set(expected) and len(trials) == 12, 'terminal_actual_matrix_not_twelve_exact_cells')
    runner, _, registry = j.runtime(prepared.run_args())
    source = (ROOT / 'OEQ_run_grading_new.py').read_text(encoding='utf-8')
    begin = source.index('        scores_block = llm_output.get("scores", {})')
    end = source.index('        validate_score_proposals(scores_block)', begin) + len('        validate_score_proposals(scores_block)')
    validation = compile(textwrap.dedent(source[begin:end]), '<unchanged_original_validation>', 'exec')
    rows, replay_checks = [], []
    input_hashes = {str(BATCH / 'plan.json'): j.filehash(BATCH / 'plan.json'), str(OLD / 'step_results.json'): j.filehash(OLD / 'step_results.json')}
    for trial_id, (path, trial) in trials.items():
        case = cases[trial['case_id']]; qid = case['question_id']; cid = case['case_id']
        receipt_path, receipt = receipts[trial_id]; attempt = receipt_path.parent
        require(trial['identity'] == expected[trial_id] and j.digest(trial['identity']) == trial_id, 'trial_identity_mismatch')
        require(receipt == ledger_map[receipt['request_id']] and receipt['trial_id'] == trial_id and receipt['attempt'] == trial['attempt'] == 1, 'ledger_receipt_mismatch')
        require(receipt['model'] == trial['judge'] and trial['actual_api_request_made'], 'actual_model_or_request_mismatch')
        expected_input = j.digest({'question': case['specific_question'], 'question_id': qid, 'protocol': case['model_response'], 'references': case['references']})
        require(trial['full_text_input_sha256'] == expected_input and trial['references_sha256'] == j.digest(case['references']), 'full_input_reference_mismatch')
        prompt = BATCH / f'q{qid}_v2_prompt.txt'
        require((attempt/'prompt.txt').read_bytes() == prompt.read_bytes() and j.filehash(prompt) == trial['prompt_sha256'], 'transmitted_prompt_mismatch')
        require(j.read(attempt/'result.json') == trial, 'attempt_trial_difference')
        context = j.read(attempt/'context_check.json')
        # The frozen .txt has platform newlines; the runner guards the actual
        # in-memory prompt string, read_text restores its LF representation.
        sent_utf8_bytes = len(prompt.read_text(encoding='utf-8').encode('utf-8'))
        require(context['conservative_context_bound'] == sent_utf8_bytes + 8192 + 256 <= 40960 and context['max_output_tokens'] == 8192, 'transmitted_context_mismatch')
        evaluation = trial.get('evaluation') or {}; generation = evaluation.get('teacher_generation') or {}
        provider_path = attempt/'provider_response.json'
        provider = j.read(provider_path) if provider_path.exists() else {}
        raw = provider.get('response'); technical = trial['status'] == 'success' and evaluation.get('technical_status') == 'VALID'
        if generation.get('technical_status') == 'VALID': require(raw == generation.get('content'), 'provider_generation_mismatch')
        elif isinstance(generation.get('raw_content'), str): require(raw == generation['raw_content'], 'failed_provider_raw_mismatch')
        elif provider_path.exists(): require((attempt/'provider_error.json').exists(), 'failed_provider_error_missing')
        parsed = None
        if isinstance(raw, str):
            try: parsed = integrity.parse_judge_object(raw)
            except integrity.JudgeFormatError: pass
        extraction = evaluation.get('extraction') if technical else None
        numeric = j.proposals(evaluation)
        require(numeric == trial['preserved_numeric_proposals'], 'preserved_numeric_proposals_mismatch')
        if technical:
            require(isinstance(parsed, dict), 'successful_raw_does_not_parse')
            ns = {'__builtins__': {'any': any}, 'llm_output': parsed,
                  'validate_teacher_extraction': integrity.validate_legacy_extraction, 'validate_score_proposals': integrity.validate_score_proposals}
            exec(validation, ns)
            require(ns['extraction'] == extraction and j.digest(extraction) == trial['extraction_sha256'], 'raw_extraction_identity_mismatch')
            raw_scores = evaluation.get('legacy_diagnostics', {}).get('raw_teacher_scores')
            require(raw_scores == ns['scores_block'], 'returned_score_block_changed')
            demand = registry.get(qid, case['specific_question'])
            meta = runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]
            quant = {'method_name': extraction['method_name'], 'tissue_ri_value': meta.get('tissue_ri_value'),
                'total_time_hours': extraction['clearing_total_time_hours'], 'sample_tier': meta.get('tissue_tier_code')}
            for key in ('reagent_ri_value', 'protocol_time_hours', 'method_stages'):
                if key in extraction: quant[key] = extraction[key]
            require(quant == evaluation['quantitative_data'] and demand == evaluation['user_preference_vector'], 'fixed_EGES_inputs_changed')
            effects = runner.calculate_effectiveness_score(quant, demand, runner.MODEL_SPACE_SIGNED, extraction['marker_dict'], meta.get('marker_query_targets') or [])
            for metric in ('s_method', 's_label', 's_trans', 's_time'):
                require(equal(effects[metric], numeric[metric]), 'original_EGES_replay_mismatch:' + metric)
        else:
            require(all(value is None for value in numeric.values()), 'failed_trial_numeric_values_not_NA')
        step = steps[cid]['step_result']
        require(steps[cid]['answer_sha256'] == hashlib.sha256(case['model_response'].encode('utf-8')).hexdigest(), 'frozen_step_original_answer_mismatch')
        require(steps[cid]['references_sha256'] == j.digest(case['references']), 'fixed_step_reference_mismatch')
        values = derive(numeric, step, technical)
        flags = literal_flags(extraction, technical, evs[cid])
        record = {'version': 'extraction_examples_removed_v2', 'case_id': cid, 'question_id': qid, 'judge': trial['judge'],
            'repeat_index': trial['repeat_index'], 'trial_id': trial_id, 'request_index': receipt['package_request_index'],
            'technical_success': technical, 'failure_stage': evaluation.get('failure_stage'),
            'full_old_example_copy': parsed == original_example if parsed is not None else None,
            'old_extraction_copy': extraction == original_example['extraction'] if technical else None,
            'literal_flags': flags, 'extraction': extraction, 'metrics': values,
            'metric_NA_reasons': {m: 'technical_failure' if not technical else 'upstream_component_unknown' for m in METRICS if values[m] is None},
            'original_step_evidence': {'sr': step['sr'], 'sp': step['sp'], 'step_config_sha256': steps[cid]['step_config_sha256']},
            'answer_evidence': evs[cid], 'formal_eligible': False, 'expert_confirmation': None,
            'input_sha256': expected_input, 'prompt_sha256': trial['prompt_sha256'], 'judge_contract_sha256': trial['identity']['contract_sha256'],
            'provider_response_sha256': j.filehash(provider_path) if provider_path.exists() else None,
            'finish_reason': provider.get('done_reason'), 'prompt_tokens': provider.get('prompt_eval_count'), 'output_tokens': provider.get('eval_count')}
        rows.append(record)
        replay_checks.append({'trial_id': trial_id, 'receipt_prompt_input_config_bound': True,
            'raw_extraction_and_proposal_identity': technical, 'four_original_EGES_components_replayed': technical,
            'failed_all_metrics_NA': not technical and all(v is None for v in values.values())})
        for p in [path, receipt_path, prompt, attempt/'prompt.txt', attempt/'context_check.json', attempt/'result.json', provider_path]:
            if p.exists(): input_hashes[str(p)] = j.filehash(p)
    rows.sort(key=lambda r: (r['judge'], r['question_id'], r['repeat_index']))
    require(len({r['request_index'] for r in rows}) == 12 and all(sum(x['judge']==m for x in rows)==6 for m in MODELS), 'judge_matrix_count_mismatch')
    history = []
    for folder, filename, version in [(OLD, 'per_observation.json', 'original_rubric_two_family_v2'), (V1, 'per_observation.json', 'final_schema_only_v1')]:
        p = folder / filename; input_hashes[str(p)] = j.filehash(p)
        for old in j.read(p):
            cid = old['case_id']; technical = old.get('technical_pipeline_complete', old.get('technical_success', False))
            old_trial_path = Path(old['source_trial_path']) if 'source_trial_path' in old else V1/'run/trials'/f"{old['trial_id']}.json"
            old_trial = j.read(old_trial_path)
            input_hashes[str(old_trial_path)] = j.filehash(old_trial_path)
            case = cases[cid]
            expected_input = j.digest({'question':case['specific_question'],'question_id':case['question_id'],
                'protocol':case['model_response'],'references':case['references']})
            require(old_trial['full_text_input_sha256'] == expected_input and old_trial['references_sha256'] == j.digest(case['references']), 'historical_full_input_or_reference_mismatch')
            raw = (old_trial.get('evaluation',{}).get('teacher_generation') or {}).get('content')
            if 'raw_teacher_content' in old: require(raw == old['raw_teacher_content'], 'historical_raw_return_changed')
            obj = integrity.parse_judge_object(raw) if raw else None
            ext = old.get('extraction')
            require(not technical or ext == old_trial['evaluation']['extraction'], 'historical_extraction_changed')
            old_metrics = old.get('candidate_raw_and_derived', old.get('metrics'))
            reconstructed = derive(j.proposals(old_trial['evaluation']), steps[cid]['step_result'], technical)
            require(all(equal(reconstructed[m],old_metrics[m]) for m in METRICS), 'historical_numeric_record_mismatch')
            history.append({'version': version, 'case_id': cid, 'question_id': old['question_id'],
                'judge': old.get('judge', 'local_llama3_8b'), 'repeat_index': old['repeat_index'], 'trial_id': old['trial_id'],
                'technical_success': technical, 'full_old_example_copy': obj == original_example if obj is not None else old.get('full_old_example_copy'),
                'old_extraction_copy': ext == original_example['extraction'] if technical else None,
                'literal_flags': literal_flags(ext, technical, evs[cid]),
                'metrics': old_metrics, 'formal_eligible': False,
                'history_only_not_new_configuration_repeat': True})
    all_versions = history + rows
    spreads, ranks, family = [], [], []
    index = {(r['judge'], r['question_id'], r['repeat_index']): r for r in rows}
    for model in MODELS:
        for qid in (2, 21):
            subset = [index[(model, qid, rep)] for rep in range(3)]
            for metric in METRICS:
                vals = [r['metrics'][metric] for r in subset if finite(r['metrics'][metric])]
                spreads.append({'judge': model, 'question_id': qid, 'metric': metric, 'planned_repeats': 3,
                    'actual_observations': len(subset), 'technical_successes': sum(r['technical_success'] for r in subset), 'finite_n': len(vals),
                    'mean': statistics.mean(vals) if vals else None, 'sample_sd': statistics.stdev(vals) if len(vals)>1 else None,
                    'range': max(vals)-min(vals) if vals else None, 'nonzero_range': len(vals)>1 and max(vals)-min(vals)>TOL,
                    'distinct_successful_extractions': len({j.digest(r['extraction']) for r in subset if r['technical_success']})})
        for metric in METRICS:
            delta = [index[(model,2,rep)]['metrics'][metric]-index[(model,21,rep)]['metrics'][metric]
                if all(finite(index[(model,q,rep)]['metrics'][metric]) for q in (2,21)) else None for rep in range(3)]
            signs = [None if d is None else 1 if d>TOL else -1 if d < -TOL else 0 for d in delta]
            ranks.append({'judge': model, 'metric': metric, 'planned_pairs': 3, 'finite_pair_n': sum(d is not None for d in delta),
                'q2_minus_q21': delta, 'directions': signs, 'strict_rank_flip': -1 in signs and 1 in signs})
    for qid in (2,21):
        for metric in METRICS:
            delta = [index[(MODELS[0],qid,rep)]['metrics'][metric]-index[(MODELS[1],qid,rep)]['metrics'][metric]
                if all(finite(index[(m,qid,rep)]['metrics'][metric]) for m in MODELS) else None for rep in range(3)]
            vals = [v for v in delta if v is not None]
            disagreements = sum(abs(v)>TOL for v in vals)
            family.append({'question_id': qid, 'metric': metric, 'direction': 'Qwen_minus_Llama', 'planned_pairs': 3,
                'finite_pair_n': len(vals), 'paired_deltas': delta, 'mean_delta': statistics.mean(vals) if vals else None,
                'mean_absolute_delta': statistics.mean(abs(v) for v in vals) if vals else None,
                'disagreeing_finite_pairs': disagreements, 'any_disagreement': disagreements>0})
    require((len(spreads),len(ranks),len(family)) == (64,32,32), 'analysis_group_count_mismatch')
    paired = []
    old_index = {(r['version'],r['judge'],r['question_id'],r['repeat_index']):r for r in history}
    for r in rows:
        for version in ('original_rubric_two_family_v2','final_schema_only_v1'):
            old = old_index.get((version,r['judge'],r['question_id'],r['repeat_index']))
            if old is None: continue
            for metric in METRICS:
                a,b=old['metrics'][metric],r['metrics'][metric]
                paired.append({'before_version':version,'after_version':r['version'],'judge':r['judge'],
                    'question_id':r['question_id'],'repeat_index':r['repeat_index'],'metric':metric,
                    'before':a,'after':b,'delta':b-a if finite(a) and finite(b) else None,
                    'scope':'Same development answer across different prompt configurations; not same-config repeats'})
    flags_by_model = {}; copies_by_model = {}; version_summary = []
    for version, model in sorted({(r['version'],r['judge']) for r in all_versions}):
        group=[r for r in all_versions if r['version']==version and r['judge']==model]
        counts={key: {'flagged':sum(r['literal_flags'][key] is True for r in group),
                     'evaluable':sum(r['literal_flags'][key] is not None for r in group)}
                for key in ('native_GFP_missing','cFos_injected','RI_missing','RI_numeric_contradiction','route_missing','route_contradiction')}
        full={'copies':sum(r['full_old_example_copy'] is True for r in group),
              'parse_evaluable':sum(r['full_old_example_copy'] is not None for r in group)}
        version_summary.append({'version':version,'judge':model,'observations':len(group),
            'technical_successes':sum(r['technical_success'] for r in group),'literal_flags':counts,'full_example_copies':full})
        if version=='extraction_examples_removed_v2': flags_by_model[model]=counts; copies_by_model[model]=full
    success=sum(r['technical_success'] for r in rows)
    facts={'actual_requests':len(receipts),'success_cells':success,'failed_cells':len(rows)-success,
        'repeat_metric_groups':len(spreads),'repeat_groups_with_at_least_two_finite_values':sum(r['finite_n']>=2 for r in spreads),
        'groups_with_nonzero_range':sum(r['nonzero_range'] for r in spreads),
        'rank_groups':len(ranks),'rank_groups_with_finite_pairs':sum(r['finite_pair_n']>0 for r in ranks),
        'strict_rank_flip_groups':sum(r['strict_rank_flip'] for r in ranks),
        'cross_family_groups':len(family),'cross_family_disagreements':{
            'definition':'A group is one question x metric; disagreement means any same-repeat finite Qwen/Llama pair differs by more than 1e-12.',
            'groups_with_any_disagreement':sum(r['any_disagreement'] for r in family),
            'groups_with_at_least_one_finite_pair':sum(r['finite_pair_n']>0 for r in family),
            'disagreeing_finite_pairs':sum(r['disagreeing_finite_pairs'] for r in family),
            'total_finite_pairs':sum(r['finite_pair_n'] for r in family),'planned_pairs':96},
        'literal_flags_by_model':flags_by_model,'full_example_copies_by_model':copies_by_model,
        'technical_successes_by_model':{m:sum(r['technical_success'] for r in rows if r['judge']==m) for m in MODELS},
        'complete_candidate_CCE_cells':sum(all(finite(r['metrics'][k]) for k in ('Com','Cor','Eff')) for r in rows),
        'metric_NA_counts':{m:sum(r['metrics'][m] is None for r in rows) for m in METRICS},
        'package_requests':len(ledger),'request_indices':sorted(r['request_index'] for r in rows),
        'analysis_new_requests':0,'formal_eligible_cells':0,'expert_returns':0,
        'scope':'Two exposed development answers, one clearing-reference source family; prompt-version intervention, not held-out accuracy or independent scientific validation.'}
    require(j.filehash(ledger_path)==ledger_before and all(j.filehash(p)==h for p,h in frozen_before.items()), 'analysis_modified_frozen_run_or_ledger')
    prepared.frozen_plan()
    for name,obj in [('per_observation.json',rows),('historical_versions.json',history),('version_summary.json',version_summary),
        ('repeat_components.json',spreads),('rank_flips.json',ranks),('cross_family_comparison.json',family),
        ('paired_prompt_effects.json',paired),('report_facts.json',facts),('development_summary.json',facts)]:save(name,obj)
    flat=[{k:r[k] for k in ('version','case_id','question_id','judge','repeat_index','trial_id','request_index','technical_success','failure_stage','full_old_example_copy','old_extraction_copy')}|r['literal_flags']|r['metrics'] for r in rows]
    table('per_observation.csv',flat);table('repeat_components.csv',spreads);table('paired_prompt_effects.csv',paired)
    table('rank_flips.csv',[{**r,'q2_minus_q21':j.canonical(r['q2_minus_q21']),'directions':j.canonical(r['directions'])} for r in ranks])
    table('cross_family_comparison.csv',[{**r,'paired_deltas':j.canonical(r['paired_deltas'])} for r in family])
    figure_rows=[{'version':r['version'],'judge':r['judge'],'question_id':r['question_id'],'repeat_index':r['repeat_index'],
        'technical_success':r['technical_success'],'metric':m,'value':r['metrics'][m]} for r in all_versions for m in METRICS]
    table('figure_data_all_versions.csv',figure_rows)
    verification={'status':'pass','actual_trials':len(rows),'exact_matrix_receipts':len(receipts),
        'actual_transmitted_prompts_match_frozen':True,'all_raw_returns_preserved':True,'source_answers_references_unchanged':True,
        'successful_original_EGES_identity_replays':success,'failed_all_metric_NA_cells':len(rows)-success,
        'original_SR_SP_evidence_reused_not_recomputed_or_edited':True,'frozen_run_files_unchanged':len(frozen_before),
        'no_holdout_scientific_fields_read':True,'new_model_requests':0,'ledger_sha256_before':ledger_before,'ledger_sha256_after':j.filehash(ledger_path),
        'per_trial_checks':replay_checks,'input_sha256':input_hashes,'script_sha256':j.filehash(__file__),
        'actual_command':[sys.executable,'scripts/cce_analyze_stability_remediation_v2.py']}
    save('analysis_verification.json',verification)
    save('run.json',{'status':'completed','completed_utc':j.now(),'cwd':str(ROOT),
        'argv':verification['actual_command'],'script_sha256':j.filehash(__file__),'analysis_new_requests':0,
        'report_facts_sha256':j.filehash(OUT/'report_facts.json'),'verification_sha256':j.filehash(OUT/'analysis_verification.json')})
    short_models = {'local_qwen3_8b':'Qwen3','local_llama3_8b':'Llama3'}
    chinese_rows=[]; english_rows=[]
    for m in MODELS:
        f=flags_by_model[m]
        counts=[f[k]['flagged'] for k in ('native_GFP_missing','cFos_injected','RI_missing','RI_numeric_contradiction')]
        denom=f['native_GFP_missing']['evaluable']
        chinese_rows.append(f"| {short_models[m]} | {facts['technical_successes_by_model'][m]}/6 | "+' | '.join(str(x) for x in counts)+f' | {denom} |')
        english_rows.append(f"{short_models[m]}: {facts['technical_successes_by_model'][m]}/6 technically valid; GFP missing / c-Fos injected / RI missing / reported RI contradiction = "+'/'.join(str(x) for x in counts)+f' (evaluable n={denom}).')
    cf=facts['cross_family_disagreements']
    (OUT/'README.md').write_text(f'''# 开发提取示例消融 v2：真实结果

本批12次真实请求中{success}次技术成功、{12-success}次失败；新增请求索引为{min(facts['request_indices'])}–{max(facts['request_indices'])}，全包台账{len(ledger)}。分析新增请求0。每份原文、实传prompt、provider返回、配置身份和receipt/ledger均已绑定；原EGES四分项对技术成功记录逐条身份重算通过。正式有效条目和专家回传均为0。

| 评价模型 | 技术成功 | 漏原生GFP | 注入c-Fos | RI缺失/null | 明确数值RI矛盾 | 字面核查分母 |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(chinese_rows)+f'''

RI缺失与明确数值矛盾互斥计数；技术失败不计为正确，也不填为假。字面检查仅依据两份已暴露开发答案中的明确标记与RI文字，不代表完整科学正确性。c-Fos检查沿用v1的字面`c-fos`匹配，未扩展别名或反推未报告信息。

64个模型内“答案×分项”组中，{facts['repeat_groups_with_at_least_two_finite_values']}组至少有2个有限值，{facts['groups_with_nonzero_range']}组range超过1e-12。32个题间排名组中，{facts['strict_rank_flip_groups']}组出现正负号互换。32个跨模型组中，{cf['groups_with_at_least_one_finite_pair']}组具有同repeat有限值对，其中{cf['groups_with_any_disagreement']}组至少一对差值超过1e-12；逐对为{cf['disagreeing_finite_pairs']}/{cf['total_finite_pairs']}，计划总分母96。缺失值不补0。数值稳定不能证明提取准确。

候选Com/Cor/Eff同时有值的观测为{facts['complete_candidate_CCE_cells']}/12，全部仍为开发描述。SR/SP复用原两份完整答案的冻结来源结果；失败管线的16指标统一NA，独立step证据另存而不填回。Com=0.4×SR+0.6×c_param/3；IA为三维最小值，HV为乘积，任一维未知则联合指标NA。

历史两模型原提示、v1 Llama及本次v2分别列于[版本汇总](version_summary.json)；不能合并为同配置重复或新增独立答案。本次只移除三处提取事实示例，不能把结果归因为整套提示词优化；2答案、1清除来源家族不足以建立泛化可靠性。留出字段及科学内容未被读取、未用于本实验。

入口：[报告事实](report_facts.json)、[逐观测](per_observation.csv)、[64组重复](repeat_components.csv)、[32组排名](rank_flips.csv)、[32组跨模型](cross_family_comparison.csv)、[不同提示版本配对](paired_prompt_effects.csv)、[绘图长表](figure_data_all_versions.csv)、[核验](analysis_verification.json)、[实际命令](commands.md)。
''',encoding='utf-8')
    (OUT/'RESULTS_en.md').write_text(f'''# Development extraction-example ablation v2

Twelve real local requests yielded {success} technically valid and {12-success} failed observations. All transmitted prompts, full inputs, provider returns and receipts were identity-bound, and the original four EGES components were replayed for every technically valid observation. The package ledger contains {len(ledger)} requests; this offline analysis added zero.

'''+ '\n\n'.join(english_rows)+f'''

Missing/null RI and a reported numeric RI contradiction are disjoint; technical failures are unevaluable, not false flags. These checks concern explicit wording in two previously exposed development answers, not comprehensive scientific validity. The c-Fos check retains the v1 literal `c-fos` definition without alias expansion.

There were {facts['groups_with_nonzero_range']} nonzero-range groups among {facts['repeat_groups_with_at_least_two_finite_values']} within-model groups with at least two finite values (64 planned groups), and {facts['strict_rank_flip_groups']} strict rank-flip groups (32 planned). Cross-family disagreements occurred in {cf['groups_with_any_disagreement']}/{cf['groups_with_at_least_one_finite_pair']} evaluable question-by-metric groups and {cf['disagreeing_finite_pairs']}/{cf['total_finite_pairs']} finite same-repeat pairs (96 planned pairs). Technical failures remain NA; finite repeat stability does not establish extraction accuracy.

The original two-family prompt, v1 Llama and v2 are separate configurations. Their observations are not pooled as same-configuration repeats. All results remain developmental, with zero expert confirmations and zero formally eligible observations. Two exposed answers from one clearing-reference source family do not establish general reliability. No holdout scientific field was read or used. See [report facts](report_facts.json), [version summary](version_summary.json), [verification](analysis_verification.json) and [command](commands.md).
''',encoding='utf-8')
    (OUT/'commands.md').write_text('''# Actual offline analysis

Executed from `C:\\ClearEval\\ClearEval-public`:

```powershell
& 'C:\\ClearEval\\review_artifacts\\bioprobench_2026-09-29\\python_portable\\python.exe' scripts/cce_analyze_stability_remediation_v2.py
```

The execution and hashes are recorded in [run.json](run.json). This script disables network connections, makes no generation requests, preserves all frozen inputs/returns and does not read holdout scientific fields. The preceding real model command is recorded separately in [actual_execution_commands.json](../actual_execution_commands.json).
''',encoding='utf-8')
    print(j.canonical(facts))


if __name__=='__main__':main()
