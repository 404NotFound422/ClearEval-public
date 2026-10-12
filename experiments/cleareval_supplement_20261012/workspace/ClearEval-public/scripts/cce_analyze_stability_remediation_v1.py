"""Analyze the frozen final-example intervention without changing any returns."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import cce_alternative_development as helper

BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'judges/stability_remediation_plan_v1'
RUN = OUT / 'run'
OLD = BASE / 'judges/local_stability_supplement_v2'
METRICS = helper.METRICS


def table(path, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding='utf-8-sig')


def main():
    plan = j.read(OUT / 'plan.json')
    for name, sha in plan['frozen_files'].items():
        assert j.filehash(OUT / name) == sha, name
    for path, sha in plan['protected_input_sha256'].items():
        assert j.filehash(path) == sha, path
    cases = {c['case_id']: c for c in j.read(OUT / 'cases.json')['cases']}
    steps = {r['case_id']: r for r in j.read(OLD / 'step_results.json')}
    old = {(r['case_id'], r['repeat_index']): r for r in j.read(OLD / 'per_observation.json') if r['judge'] == 'local_llama3_8b'}
    trials = [j.read(p) for p in sorted((RUN / 'trials').glob('*.json'))]
    matrix = {(r['case_id'], r['repeat_index']) for r in plan['matrix']}
    assert len(trials) == 6 and {(t['case_id'], t['repeat_index']) for t in trials} == matrix
    ledger = j.ledger_rows(BASE / 'judges/request_ledger.jsonl')
    entries = {r['request_id']: r for r in ledger if r.get('event') == 'request_started'}
    original_example = j.read(OUT / 'original_final_example.json')
    records, flat, paired = [], [], []
    input_files = {str(OUT / 'plan.json'): j.filehash(OUT / 'plan.json'), str(OLD / 'step_results.json'): j.filehash(OLD / 'step_results.json')}
    for t in trials:
        c = cases[t['case_id']]
        qid, rep = t['question_id'], t['repeat_index']
        expected_input = j.digest({'question': c['specific_question'], 'question_id': qid, 'protocol': c['model_response'], 'references': c['references']})
        assert t['full_text_input_sha256'] == expected_input
        assert t['references_sha256'] == j.digest(c['references'])
        assert t['trial_id'] == j.digest(t['identity']) and t['attempt'] == 1
        attempt = RUN / 'attempts' / f"{t['trial_id']}_1"
        receipt = j.read(attempt / 'request_receipt.json')
        assert entries[receipt['request_id']] == receipt and receipt['trial_id'] == t['trial_id']
        assert j.filehash(attempt / 'prompt.txt') == t['prompt_sha256'] == plan['frozen_files'][f'q{qid}_proposed_prompt.txt']
        provider = j.read(attempt / 'provider_response.json')
        e = t['evaluation']
        raw = e['teacher_generation']['content']
        assert provider['response'] == raw
        obj = json.loads(raw)
        ext = e.get('extraction')
        assert obj['extraction'] == ext
        values = j.proposals(e)
        assert values == t['preserved_numeric_proposals']
        step = steps[t['case_id']]['step_result']
        assert old[(t['case_id'], rep)]['input_sha256'] == expected_input
        values.update(sr=step['sr'], sp=step['sp'])
        values['Com'] = .4 * values['sr'] + .6 * values['c_param'] / 3 if values['sr'] is not None and values['c_param'] is not None else None
        dims = [values[k] for k in ('Com', 'Cor', 'Eff')]
        values['IA'] = min(dims) if all(v is not None for v in dims) else None
        values['HV'] = math.prod(dims) if all(v is not None for v in dims) else None
        # These are literal answer contradictions, not an expert-wide accuracy audit.
        label_quote = '**Chosen Labeling:** [GFP (内源)]' if qid == 2 else '**Chosen Labeling:** [GFP (内源), DAPI]'
        ri_quote = 'DBE, RI = 1.562' if qid == 2 else 'DBE (Refractive Index = 1.56)'
        expected_ri = 1.562 if qid == 2 else 1.56
        assert label_quote in c['model_response'] and ri_quote in c['model_response']
        marker_text = j.canonical(ext['marker_dict']).casefold()
        assert 'c-fos' not in c['specific_question'].casefold() + c['model_response'].casefold()
        flags = {'unsupported_cfos_literal': 'c-fos' in marker_text,
                 'explicit_gfp_label_absent_from_marker_dict': 'gfp' not in marker_text,
                 'reagent_RI_disagrees_with_explicit_DBE_RI': ext.get('reagent_ri_value') != expected_ri}
        rec = {'question_id': qid, 'repeat_index': rep, 'case_id': t['case_id'], 'trial_id': t['trial_id'],
               'technical_success': t['status'] == 'success', 'request_index': receipt['package_request_index'],
               'full_old_example_copy': obj == original_example, 'old_extraction_copy': ext == original_example['extraction'],
               'route_matches_explicit_FDISCO': ext.get('method_name') == 'FDISCO', 'extraction': ext,
               'literal_contradiction_flags': flags, 'answer_evidence': {'label_quote': label_quote, 'RI_quote': ri_quote, 'explicit_RI': expected_ri},
               'metrics': values, 'formal_eligible': False, 'expert_confirmation': None,
               'prompt_sha256': t['prompt_sha256'], 'judge_contract_sha256': t['identity']['contract_sha256'],
               'raw_response_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'done_reason': provider.get('done_reason'),
               'prompt_tokens': provider.get('prompt_eval_count'), 'output_tokens': provider.get('eval_count')}
        records.append(rec)
        flat.append({k: rec[k] for k in ['question_id', 'repeat_index', 'trial_id', 'request_index', 'technical_success', 'full_old_example_copy', 'old_extraction_copy', 'route_matches_explicit_FDISCO']} | flags | values)
        for metric in METRICS:
            before, after = old[(t['case_id'], rep)]['candidate_raw_and_derived'][metric], values[metric]
            paired.append({'question_id': qid, 'repeat_index': rep, 'metric': metric, 'old_prompt_value': before,
                           'new_prompt_value': after, 'delta': after - before if before is not None and after is not None else None,
                           'comparison': 'prompt intervention; same answer, reference, model and numeric pipeline', 'formal_eligible': False})
        for p in [RUN / 'trials' / (t['trial_id'] + '.json'), attempt / 'prompt.txt', attempt / 'provider_response.json', attempt / 'request_receipt.json']:
            input_files[str(p)] = j.filehash(p)
    assert len({r['request_index'] for r in records}) == 6
    assert len({r['judge_contract_sha256'] for r in records}) == 1
    spreads = []
    for qid in (2, 21):
        rs = [r for r in records if r['question_id'] == qid]
        for metric in METRICS:
            vals = [r['metrics'][metric] for r in rs if r['metrics'][metric] is not None]
            spreads.append({'question_id': qid, 'metric': metric, 'actual_repeats': len(rs), 'finite_repeats': len(vals),
                            'mean': statistics.mean(vals) if vals else None, 'sample_sd': statistics.stdev(vals) if len(vals) > 1 else None,
                            'range': max(vals) - min(vals) if vals else None, 'distinct_extractions': len({j.digest(r['extraction']) for r in rs})})
    flips = []
    for metric in METRICS:
        deltas = []
        for rep in range(3):
            pair = {r['question_id']: r['metrics'][metric] for r in records if r['repeat_index'] == rep}
            deltas.append(pair[2] - pair[21] if pair[2] is not None and pair[21] is not None else None)
        signs = [None if d is None else 1 if d > 1e-12 else -1 if d < -1e-12 else 0 for d in deltas]
        flips.append({'metric': metric, 'question_2_minus_21': deltas, 'directions': signs, 'strict_rank_flip': -1 in signs and 1 in signs})
    summary = {'status': 'six_actual_requests_completed', 'source_answers': 2, 'judge_families': 1, 'repeats': 3,
               'new_requests': 6, 'request_indices': sorted(r['request_index'] for r in records),
               'package_request_count_at_analysis': len(entries), 'technical_successes': sum(r['technical_success'] for r in records),
               'old_full_example_copies': sum(json.loads(r['raw_teacher_content']) == original_example for r in old.values()), 'new_full_example_copies': sum(r['full_old_example_copy'] for r in records),
               'old_route_mismatches': sum(r['explicit_route_mismatch'] for r in old.values()), 'new_route_mismatches': sum(not r['route_matches_explicit_FDISCO'] for r in records),
               'literal_contradiction_counts': {k: sum(r['literal_contradiction_flags'][k] for r in records) for k in records[0]['literal_contradiction_flags']},
               'variable_component_groups': sum(r['range'] is not None and r['range'] > 1e-12 for r in spreads),
               'component_groups': len(spreads), 'strict_rank_flip_metrics': sum(r['strict_rank_flip'] for r in flips),
               'complete_numeric_CCE_observations': sum(all(r['metrics'][k] is not None for k in ('Com', 'Cor', 'Eff')) for r in records),
               'formal_eligible': False, 'formal_completed_observations': 0, 'expert_labels_added': 0,
               'scientific_accuracy_claim': False, 'scope': 'Post-diagnosis prompt intervention on two exposed development answers; old Qwen is not a same-prompt comparison.'}
    for name, obj in [('per_observation.json', records), ('paired_prompt_effects.json', paired), ('repeat_components.json', spreads), ('rank_flips.json', flips), ('development_summary.json', summary)]:
        j.save(OUT / name, obj)
    table(OUT / 'per_observation.csv', flat)
    table(OUT / 'paired_prompt_effects.csv', paired)
    table(OUT / 'repeat_components.csv', spreads)
    j.save(OUT / 'analysis_verification.json', {'status': 'pass', 'six_distinct_actual_receipts': True,
        'same_new_contract_all_six': True, 'exact_transmitted_prompts': True, 'unchanged_source_answers_and_references': True,
        'old_inputs_byte_unchanged': True, 'raw_returns_not_repaired': True, 'input_sha256': input_files,
        'analysis_script_sha256': j.filehash(__file__), 'actual_command': [sys.executable, 'scripts/cce_analyze_stability_remediation_v1.py']})
    print(j.canonical(summary))


if __name__ == '__main__':
    main()
