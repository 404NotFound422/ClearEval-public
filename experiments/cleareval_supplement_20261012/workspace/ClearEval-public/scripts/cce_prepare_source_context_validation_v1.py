"""Prepare exact development comparisons without invoking a model.

Five unchanged successful baselines are reused. Only K1/K2 require future calls.
The proposal changes no authorization, ledger, old score, or reference step.
"""
import argparse
import copy
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_round2_runner_v11 as transport
import cce_round3_runner_v2 as runner
import cce_posthoc_components_v7 as processor

j = transport.j
R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
OLD = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010/grounded_development_v11'
CASES = ROOT / 'artifacts/cce_validation/optimizer_20261010/grounded_development_v7/cases.json'
STEPS = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010/step_inputs_v1/development.json'
AUDIT = R3 / 'problem_cycles/development_rubric_evidence_cycle01'
INPUTS = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bind(p):
    p = Path(p).resolve()
    return {'path': str(p), 'sha256': digest(p.read_bytes())}


def read_bytes(p, expected=None):
    p = Path(p).resolve()
    data = p.read_bytes()
    sha = digest(data)
    if expected is not None:
        assert sha == expected, str(p)
    INPUTS[str(p)] = sha
    return data


def read(p, expected=None):
    return json.loads(read_bytes(p, expected).decode('utf-8-sig'))


def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(data)


def save(p, obj):
    write(p, (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def prepare(out, instructions):
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    cases = read(CASES)['cases']
    assert [c['anonymous_answer_id'] for c in cases] == ['A01','A02','A03','A04','A05']
    steps = read(STEPS)
    cells = read(R3 / 'uniform_v7/actual_01/cells.json')
    contract = read(OLD / 'expected_contract.json')
    public = contract['models'][0]['settings']
    current = read(R3 / 'E2_canonical_qwen_01/plan.json')['public_model']
    assert public == current
    assert public['model'] == 'qwen3.8:27b-q8_0-local'
    assert public['model_digest'] == 'ea6892d079c639acf4812dee100eca284199c3ae3fb4ffd9e5a5ae8641ae73ba'
    assert (public['temperature'], public['max_output_tokens'], public['num_ctx'], public['enable_thinking']) == (0,8192,98304,False)
    qualifications = read(AUDIT / 'execution_01/reference_qualification_candidate.json')
    byref = {r['reference_id']: r for r in qualifications}
    instruction_bytes = read_bytes(instructions)
    instruction = instruction_bytes.decode('utf-8-sig').strip()
    ledger_path = ROOT / 'artifacts/cce_validation/judges/request_ledger.jsonl'
    ledger_bytes = ledger_path.read_bytes()
    ledger = [json.loads(line) for line in ledger_bytes.decode('utf-8-sig').splitlines() if line.strip()]
    ledger_by_id = {x['request_id']: x for x in ledger}
    assert len(ledger_by_id) == 428
    out.mkdir(parents=True)
    write(out / 'baseline_ledger_snapshot.jsonl', ledger_bytes)
    save(out / 'cases.json', {'cases': cases})
    save(out / 'steps.json', steps)
    save(out / 'public_model.json', public)
    write(out / 'model_config.json', read_bytes(OLD / 'model_config.json'))
    write(out / 'evidence_instruction.txt', instruction_bytes)
    matrix, baselines, contrasts = [], [], []
    for case in cases:
        aid, cid = case['anonymous_answer_id'], case['case_id']
        cell = next(x for x in cells if x['cohort'] == 'development' and x['cell_id'] == aid)
        assert cell['status'] == 'success' and cell['posthoc_full_conversion'] is True
        raw_binding, = [b for b in cell['source_bindings'] if b['sha256'] == cell['raw_sha256']]
        raw_path = Path(raw_binding['path'])
        directory = raw_path.parent
        raw = read_bytes(raw_path, raw_binding['sha256']).decode('utf-8')
        def archived(name):
            p = directory / name
            b, = [b for b in cell['source_bindings'] if Path(b['path']) == p]
            return read(p, b['sha256'])
        payload = archived('http_request_payload.json')
        provider = archived('provider_response.json')
        receipt = archived('request_receipt.json')
        trial_path = directory.parents[1] / 'trials' / (directory.name[:-2] + '.json')
        trial_binding, = [b for b in cell['source_bindings'] if Path(b['path']) == trial_path]
        trial = read(trial_path, trial_binding['sha256'])
        assert trial['status'] == 'success' and trial['actual_request_made'] is True
        assert trial['identity']['contract_sha256'] == j.digest(contract)
        assert trial['identity']['payload_sha256'] == j.digest(payload)
        assert ledger_by_id[receipt['request_id']] == receipt
        assert transport.validate_provider(provider, public) == raw
        prompt_bytes = read_bytes(directory / 'prompt.txt')
        assert prompt_bytes.decode('utf-8') == payload['prompt']
        doc = transport.grounded.document(case['model_response'], transport.grounded.source_id_for_case(case))
        assert digest(case['model_response'].encode('utf-8')) == steps[cid]['answer_sha256'] == case['answer_sha256']
        assert digest(case['specific_question'].encode('utf-8')) == steps[cid]['question_sha256']
        assert j.digest(case['references']) == steps[cid]['references_sha256']
        assert payload == transport.payload_for(payload['prompt'], payload['format'], public)
        assert payload['format'] == transport.grounded.schema_for_document(doc)
        posthoc_binding = cell['posthoc_record']
        posthoc = read(posthoc_binding['path'], posthoc_binding['sha256'])
        assert posthoc['metrics'] == cell['posthoc_metrics']
        save(out / 'source_documents' / (aid + '.json'), doc)
        source_notes = []
        for ref in case['references']:
            candidate = byref[ref['reference_id']]
            assert candidate['original_reference_unchanged'] == ref
            for q in candidate['additional_qualification_evidence']:
                source = read_bytes(q['source']['path'], q['source']['sha256']).decode('utf-8-sig')
                span = q['source_span']
                assert source[span['start']:span['end']] == span['quote']
                source_notes.append({'reference_id': ref['reference_id'], **q})
        addition = '\n\n[ADDITIONAL SOURCE QUALIFICATION]\n' + json.dumps(source_notes, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        ledger_addition = '\n\n[RUBRIC EVIDENCE ACCOUNTING]\n' + instruction
        prompts = {'K0': payload['prompt'], 'K1': payload['prompt'] + addition,
                   'K2': payload['prompt'] + addition + ledger_addition}
        save(out / 'additions' / (aid + '.json'), {'source_qualification': addition, 'rubric_evidence_accounting': ledger_addition})
        for condition in ['K0','K1','K2']:
            oid = aid + '_' + condition
            future = copy.deepcopy(payload)
            future['prompt'] = prompts[condition]
            if condition == 'K0':
                write(out / 'request_payloads' / (oid + '.json'), (directory / 'http_request_payload.json').read_bytes())
                write(out / 'prompts' / (oid + '.txt'), prompt_bytes)
            else:
                save(out / 'request_payloads' / (oid + '.json'), future)
                write(out / 'prompts' / (oid + '.txt'), prompts[condition].encode('utf-8'))
            row = {'observation_id': oid, 'answer_id': aid, 'case_id': cid, 'question_id': case['question_id'],
                'condition': condition, 'source_document': bind(out / 'source_documents' / (aid + '.json')),
                'prompt': bind(out / 'prompts' / (oid + '.txt')),
                'payload': bind(out / 'request_payloads' / (oid + '.json')),
                'payload_identity_sha256': j.digest(future), 'step_sha256': j.digest(steps[cid]),
                'status': 'archived_success_reused' if condition == 'K0' else 'planned_not_requested',
                'needs_new_request': condition != 'K0', 'new_calls_made': 0,
                'max_attempts_if_authorized': 1, 'prompt_utf8_bytes': len(prompts[condition].encode('utf-8'))}
            if condition == 'K0':
                row['baseline_provenance'] = {'terminal': trial_binding, 'request_receipt': bind(directory / 'request_receipt.json'),
                    'raw': raw_binding, 'provider': bind(directory / 'provider_response.json'), 'current_scoring': posthoc_binding}
                baselines.append({'observation_id': oid, 'answer_id': aid, 'question_id': case['question_id'],
                    'metrics': cell['posthoc_metrics'], 'original_status': trial['status'],
                    'processing_version': posthoc.get('processing_version'), 'source': row['baseline_provenance'],
                    'new_evaluation': False})
            matrix.append(row)
        contrasts += [{'answer_id': aid, 'contrast': name, 'left': aid + '_' + left, 'right': aid + '_' + right}
                      for name,left,right in [('source_qualification','K0','K1'),('evidence_accounting','K1','K2')]]
    scheduled = [r['observation_id'] for r in matrix if r['needs_new_request']]
    random.Random(20261012).shuffle(scheduled)
    save(out / 'matrix.json', matrix)
    save(out / 'baseline_per_answer.json', baselines)
    save(out / 'paired_contrasts.json', contrasts)
    save(out / 'execution_order.json', {'seed': 20261012, 'new_request_order': scheduled})
    save(out / 'proposal.json', {'status': 'prepared_pending_additional_call_authorization',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'base_tasks': 5, 'planned_observations': 15,
        'archived_successes_reused': 5, 'proposed_new_requests': 10, 'new_requests_made': 0,
        'proposed_package_limit': 438, 'current_package_limit': 428,
        'proposed_time_limit_seconds': 7200, 'existing_deadline_utc': '2026-10-12T02:43:01+00:00',
        'max_attempts': 1, 'automatic_retries': False, 'old_confirmation_used_for_development': False,
        'postprocessor': 'cce_posthoc_components_v7', 'postprocessor_adopted_change': False,
        'reference_steps_SR_SP_formula_or_KB_change': False, 'judge': public,
        'human_budget': {'experts':1,'development':5,'holdout':15},
        'cache_limitation': 'K0 is an archived successful baseline, not a newly randomized contemporaneous observation. Public model identity and decoding settings match exactly; temporal effects are not separately estimated.',
        'inference_scope': 'Development mechanism comparison; no independent validation, stability estimate or demonstrated score accuracy.',
        'prior_design_amendment': 'Honor the user instruction to reuse unchanged successful results. Replace five planned K0 calls with their identity-checked successful returns, reducing new calls from 15 to 10.',
        'actual_prepare_command': [sys.executable,*sys.argv]})
    for path, sha in INPUTS.items():
        assert bind(path)['sha256'] == sha
    assert ledger_path.read_bytes() == ledger_bytes
    code = [bind(p) for p in runner.dependencies(processor, transport)] + [bind(__file__)]
    assets = [bind(p) for p in sorted(out.rglob('*')) if p.is_file()]
    save(out / 'freeze.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
        'input_bindings': [{'path':p,'sha256':h} for p,h in sorted(INPUTS.items())],
        'code_bindings': code, 'asset_bindings': assets,
        'ledger_before_preparation': {'path':str(ledger_path),'sha256':digest(ledger_bytes)},
        'authorization_granted': False, 'new_model_calls': 0})
    result = verify(out)
    save(out / 'preflight.json', result)
    return result


def verify(out):
    freeze = j.read(out / 'freeze.json')
    for b in freeze['input_bindings'] + freeze['code_bindings'] + freeze['asset_bindings']:
        assert bind(b['path']) == b, b['path']
    matrix = j.read(out / 'matrix.json')
    assert len(matrix) == 15 and len({r['observation_id'] for r in matrix}) == 15
    rows = {r['observation_id']: r for r in matrix}
    for aid in ['A01','A02','A03','A04','A05']:
        payloads = {k:j.read(rows[aid+'_'+k]['payload']['path']) for k in ['K0','K1','K2']}
        add = j.read(out / 'additions' / (aid+'.json'))
        assert payloads['K1']['prompt'] == payloads['K0']['prompt'] + add['source_qualification']
        assert payloads['K2']['prompt'] == payloads['K1']['prompt'] + add['rubric_evidence_accounting']
        base = {k:v for k,v in payloads['K0'].items() if k != 'prompt'}
        for condition, p in payloads.items():
            assert {k:v for k,v in p.items() if k != 'prompt'} == base
            row = rows[aid+'_'+condition]
            assert row['step_sha256'] == rows[aid+'_K0']['step_sha256']
            assert Path(row['prompt']['path']).read_bytes().decode('utf-8') == p['prompt']
            assert row['source_document'] == rows[aid+'_K0']['source_document']
            assert row['payload_identity_sha256'] == j.digest(p)
    scheduled = j.read(out/'execution_order.json')['new_request_order']
    assert len(scheduled) == 10 and set(scheduled) == {r['observation_id'] for r in matrix if r['needs_new_request']}
    assert all('metrics' not in r for r in matrix if r['needs_new_request'])
    baselines = j.read(out/'baseline_per_answer.json')
    assert len(baselines) == 5 and all(not b['new_evaluation'] for b in baselines)
    return {'status':'pass','scope':'Actual archived baseline identity and prepared full-input contrasts; no model comparison executed.',
        'prepared_observations':15,'verified_archived_successes':5,'planned_new_requests':10,'paired_contrasts':10,
        'identical_nonprompt_payloads_within_each_answer':True,'full_original_prompts_preserved':True,
        'raw_SR_SP_inputs_reused_unchanged':True,'scoring_or_KB_changes':False,'new_model_calls':0,
        'future_runtime_model_identity_must_be_checked':True,'actual_runtime_token_counts_measured':False,
        'max_prompt_utf8_bytes':max(r['prompt_utf8_bytes'] for r in matrix),
        'created_utc':datetime.now(timezone.utc).isoformat()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','verify'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--instructions', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        assert args.instructions is not None
        result = prepare(args.out.resolve(), args.instructions.resolve())
    else:
        result = verify(args.out.resolve())
    print(json.dumps(result,ensure_ascii=False))
