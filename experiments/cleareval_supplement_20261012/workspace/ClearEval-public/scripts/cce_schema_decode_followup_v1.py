"""Frozen 5-development/15-follow-up experiment with schema-constrained decoding.

The existing v2 prompt and typed schema are unchanged. Only the local transport's
format parameter changes from 'json' to the already supplied typed schema.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import copy
import hashlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import cce_alternative_development as helper
import cce_stability_remediation_v2 as dev

BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'judges/schema_decode_followup_v1'
OLD = BASE / 'judges/local_extraction_holdout_v1'
DEV_CASES = BASE / 'judges/local_extraction_dev_v2/cases.json'
LEDGER = BASE / 'judges/request_ledger.jsonl'
MODEL = 'local_qwen3_8b'
ORIGINAL_CONTRACT = 'c27211dc7513d3ac24ee211ce3950eb1a1d0b553e87b0374b93190fc7dfe56ae'


def require(ok, reason):
    if not ok: raise ValueError(reason)


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': j.filehash(path)}


def count():
    return sum(r.get('event') == 'request_started' for r in j.ledger_rows(LEDGER))


def area(stage):
    return OUT / stage


def run_area(stage):
    return area(stage) / 'sealed/run'


def arguments(stage, allow=False):
    return SimpleNamespace(out=run_area(stage), cases=area(stage) / 'sealed/cases.json',
        model_config=OUT / 'local_config_snapshot.json', models=[MODEL],
        question_file=j.HIST, demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None, ledger=LEDGER, total_budget=300, external_request_count=0,
        max_calls=5 if stage == 'development' else 15, max_attempts=1, repeats=1,
        temperature=0.0, max_output_tokens=8192, timeout_seconds=600, allow_api=allow)


def record(command, stage=None, **extra):
    path = OUT / 'actual_commands.json'
    rows = j.read(path) if path.exists() else []
    argv = [sys.executable, 'scripts/cce_schema_decode_followup_v1.py', command]
    if stage: argv += ['--stage', stage]
    if command == 'run': argv += ['--allow-local-calls']
    rows.append({'utc': j.now(), 'argv': argv, 'cwd': str(ROOT),
        'script_sha256': j.filehash(__file__), 'package_requests': count(), **extra})
    j.save(path, rows)


def validate():
    plan = j.read(OUT / 'plan.json')
    for group in ('frozen_inputs', 'protected_originals'):
        for b in plan[group]:
            require(j.filehash(b['path']) == b['sha256'], group + '_changed:' + Path(b['path']).name)
    return plan


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists():
        validate(); record('prepare', status='frozen_plan_reused', new_requests=0)
        print(j.canonical({'status': 'frozen_plan_reused', 'new_requests': 0})); return
    before = count()
    require(before + 20 <= 300, 'insufficient_budget_for_complete_matrix')
    require(not list(OUT.glob('*/sealed/run/attempts/*/request_receipt.json')), 'existing_request_prevents_prepare')
    dev.frozen_plan()
    schema_path = OUT / 'format_schema.json'
    schema_path.write_bytes((dev.OUT / 'final_output_schema.json').read_bytes())
    schema = j.read(schema_path)
    require(j.filehash(schema_path) == j.filehash(dev.OUT / 'final_output_schema.json'), 'schema_bytes_changed')
    def no_defaults(value):
        if isinstance(value, dict):
            require('default' not in value and 'const' not in value and 'enum' not in value, 'schema_injects_values')
            for v in value.values(): no_defaults(v)
        elif isinstance(value, list):
            for v in value: no_defaults(v)
    no_defaults(schema)
    (OUT / 'local_config_snapshot.json').write_bytes((OLD / 'local_config_snapshot.json').read_bytes())
    matrix = []; files = [schema_path, OUT / 'local_config_snapshot.json', Path(__file__).resolve(),
        ROOT / 'scripts/cce_judges.py', ROOT / 'scripts/cce_stability_remediation_v2.py',
        ROOT / 'scripts/cce_alternative_development.py', dev.OUT / 'plan.json',
        dev.OUT / 'inherited_v1_prompt_edits.json', dev.OUT / 'prompt_edits.json',
        dev.OUT / 'rubric_extraction_examples_removed.txt', dev.OUT / 'final_output_schema.json',
        BASE / 'human_review/private/identity_manifest.csv', BASE / 'human_review/selection.json',
        BASE / 'human_review/reviewer/review_items.csv', ROOT / 'scripts/cce_validation.py',
        DEV_CASES, OLD / 'sealed/cases.json', OLD / 'frozen_judge_contract.json']
    for stage, source, expected in [('development', DEV_CASES, [f'A{i:02}' for i in range(1, 6)]),
                                     ('holdout_followup', OLD / 'sealed/cases.json', [f'A{i:02}' for i in range(6, 21)])]:
        dest = area(stage) / 'sealed/cases.json'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes()); files.append(dest)
        cases = j.read(dest)['cases']
        require([c['anonymous_answer_id'] for c in cases] == expected, 'fixed_selection_changed')
        for case in cases:
            original = helper.exact_runner_prompt(case)
            prompt = dev.transform(original)
            for key in ('specific_question', 'model_response'):
                require(original.count(case[key]) == prompt.count(case[key]) == 1, 'full_input_changed')
            require(prompt.endswith(dev.reference_suffix(case)), 'reference_context_changed')
            bound = len(prompt.encode('utf-8')) + 8192 + 256
            require(bound <= 40960, 'context_bound_exceeded')
            path = dest.parent / 'prompts' / (case['anonymous_answer_id'] + '.txt')
            path.parent.mkdir(exist_ok=True); path.write_text(prompt, encoding='utf-8'); files.append(path)
            matrix.append({'stage': stage, 'anonymous_answer_id': case['anonymous_answer_id'],
                'question_id': case['question_id'], 'case_id': case['case_id'], 'judge': MODEL,
                'repeat_index': 0, 'attempt': 1,
                'input_sha256': j.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                    'protocol': case['model_response'], 'references': case['references']}),
                'answer_sha256': case['answer_sha256'], 'question_sha256': case['question_sha256'],
                'prompt_path': str(path), 'prompt_sha256': j.filehash(path),
                'references_sha256': j.digest(case['references']), 'conservative_context_bound': bound})
    contract = j.read(OLD / 'frozen_judge_contract.json')
    files += [ROOT / p for p in contract['files']]
    delta = {'intervention': 'local_format_json_to_exact_existing_typed_schema',
        'prompt_changed_from_development_v2': False, 'typed_schema_changed': False,
        'decoder_schema_source': bind(dev.OUT / 'final_output_schema.json'),
        'default_values_or_forced_scientific_choices': False, 'nullable_scores_preserved': True,
        'full_question_answer_reference_changes': False, 'loader_changes': False,
        'EGES_formula_changes': False, 'scientific_rubric_changes': False,
        'evidence': [{'url': 'https://docs.ollama.com/capabilities/structured-outputs',
            'accessed_date': '2026-10-09', 'claim': 'The local format parameter accepts a JSON schema object.'},
            {'local_file': bind(ROOT / 'models/Ollama_LLM.py'), 'claim': 'Existing adapter accepts dictionary format and passes it to /api/generate.'}],
        'scope': 'Technical output-contract intervention; it may affect scientific values, which still require expert review.',
        'prior_exposure': 'Original holdout technical failures and existence of a follow-up technical failure known; no holdout scientific values used for schema selection.'}
    j.save(OUT / 'config_delta.json', delta); files.append(OUT / 'config_delta.json')
    plan = {'status': 'frozen_before_generation', 'created_utc': j.now(), 'matrix': matrix,
        'planned_development_requests': 5, 'planned_holdout_followup_requests': 15,
        'planned_maximum_requests': 20, 'package_requests_before': before,
        'expected_package_requests_after_maximum': before + 20, 'total_budget': 300,
        'max_attempts': 1, 'repeats': 1, 'primary_trial_rule': 'repeat_index=0',
        'continuation_gate': 'Run all 5 fixed development cases once. Run all 15 follow-up cases only if all 5 development outputs pass the unchanged original technical validator. No scientific-value gate, sample replacement, or retry.',
        'no_holdout_adaptive_tuning': True, 'original_5_plus_15_selection_unchanged': True,
        'independent_holdout_accuracy_claim': False, 'new_expert_fields': 0, 'formal_eligible': False,
        'frozen_inputs': [bind(p) for p in dict.fromkeys(files)],
        'protected_originals': j.read(BASE / 'judges/holdout_failure_audit_v1/verification.json')['protected_input_hashes']}
    j.save(OUT / 'plan.json', plan); validate()
    require(count() == before, 'preparation_made_generation_request')
    record('prepare', status='completed', new_requests=0)
    print(j.canonical({'status': 'prepared', 'development_cells': 5, 'followup_cells': 15,
        'package_requests': before, 'new_requests': 0, 'plan_sha256': j.filehash(OUT / 'plan.json')}))


@contextlib.contextmanager
def wrapper(stage):
    old_runtime, old_contract, old_models, old_adapter = j.runtime, j.contract, j.model_configs, j.make_adapter
    schema = j.read(OUT / 'format_schema.json')
    cases = j.read(area(stage) / 'sealed/cases.json')['cases']
    by_qid = {c['question_id']: c for c in cases}
    by_prompt = {hashlib.sha256((area(stage) / 'sealed/prompts' / (c['anonymous_answer_id'] + '.txt')).read_text(encoding='utf-8').encode()).hexdigest(): c for c in cases}
    def models(args):
        result = old_models(args)
        require(len(result) == 1 and result[0]['public']['format'] == 'json', 'unexpected_original_format')
        result[0]['public']['format'] = schema
        return result
    def runtime(args):
        runner, api, registry = old_runtime(args)
        previous = runner.evaluate_response_with_teacher
        async def evaluate(teacher, question, answer, model_space, meta, template):
            case = by_qid[meta['question_id']]
            require(question == case['specific_question'] and answer == case['model_response'], 'runtime_case_changed')
            class Teacher:
                model_name = teacher.model_name
                async def _acall(self, prompt):
                    revised = dev.transform(prompt)
                    expected = (area(stage) / 'sealed/prompts' / (case['anonymous_answer_id'] + '.txt')).read_text(encoding='utf-8')
                    require(revised + dev.reference_suffix(case) == expected, 'runtime_prompt_changed')
                    return await teacher._acall(revised)
            result = await previous(Teacher(), question, answer, model_space, meta, template)
            result['prompt_variant_provenance'] = {'variant': 'existing_v2_prompt_schema_constrained_decode',
                'original_runner_prompt_hash_scope': 'pretransform original rubric', 'raw_return_modified': False}
            return result
        runner.evaluate_response_with_teacher = evaluate
        return runner, api, registry
    def contract(args, runner, registry, current_models):
        original_models = copy.deepcopy(current_models)
        for model in original_models: model['public']['format'] = 'json'
        original = old_contract(args, runner, registry, original_models)
        require(j.digest(original) == ORIGINAL_CONTRACT, 'underlying_original_contract_drift')
        current = old_contract(args, runner, registry, current_models)
        return {**current, 'prompt_variant': {'id': 'existing_v2_prompt_schema_constrained_decode',
            'plan_sha256': j.filehash(OUT / 'plan.json'), 'wrapper_sha256': j.filehash(__file__),
            'typed_schema_sha256': j.filehash(OUT / 'format_schema.json'),
            'rubric_variant_sha256': j.filehash(dev.OUT / 'rubric_extraction_examples_removed.txt'),
            'scope': 'Fixed 5 development then 15 technical follow-up cases; no original result modification.'}}
    def adapter(public, api_type):
        require(public['format'] == schema, 'adapter_format_changed')
        api = old_adapter(public, api_type)
        generate = api.client.client.generate
        def checked_generate(**kwargs):
            require(kwargs.get('format') == schema, 'actual_transport_schema_changed')
            prompt_hash = hashlib.sha256(kwargs['prompt'].encode()).hexdigest()
            require(prompt_hash in by_prompt, 'actual_transport_prompt_changed')
            case = by_prompt[prompt_hash]
            path = area(stage) / 'sealed/transport_checks' / (case['anonymous_answer_id'] + '.json')
            j.save(path, {'case_id': case['case_id'], 'prompt_raw_utf8_sha256': prompt_hash,
                'actual_format_digest': j.digest(kwargs['format']), 'actual_format_is_frozen_schema': True,
                'model': kwargs['model'], 'stream': kwargs['stream'], 'think': kwargs.get('think'),
                'options_before_original_num_ctx_injection': kwargs['options'],
                'upstream_num_ctx': public['num_ctx'], 'raw_payload_or_result_modified': False})
            return generate(**kwargs)
        api.client.client.generate = checked_generate
        return api
    j.runtime, j.contract, j.model_configs, j.make_adapter = runtime, contract, models, adapter
    try: yield
    finally: j.runtime, j.contract, j.model_configs, j.make_adapter = old_runtime, old_contract, old_models, old_adapter


def gate(stage):
    if stage == 'development': return
    summary = j.read(run_area('development') / 'summary.json')
    require(summary['successful_trials'] == 5 and summary['failed_trials'] == 0,
            'prespecified_development_gate_not_passed')
    trials = [j.read(p) for p in (run_area('development') / 'trials').glob('*.json')]
    require(len(trials) == 5 and all(r['status'] == 'success' and r['actual_api_request_made'] and
        r['attempt'] == 1 and r['repeat_index'] == 0 for r in trials), 'development_gate_missing_real_returns')


def preflight(stage):
    validate(); gate(stage); before = count()
    with wrapper(stage), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, _, _, _, cases, contract = j.preflight(arguments(stage))
    require(count() == before, 'preflight_made_request')
    j.save(area(stage) / 'preflight_verification.json', {'status': 'pass', 'cases': len(cases),
        'contract_sha256': j.digest(contract), 'schema_in_transport_contract': True,
        'generation_requests': 0, 'source_plan_sha256': j.filehash(OUT / 'plan.json')})
    record('preflight', stage, status='completed', new_requests=0)
    print(j.canonical({'status': 'preflight_pass', 'stage': stage, 'cases': len(cases), 'new_requests': 0}))


async def run(stage):
    validate(); gate(stage)
    before = len(list(run_area(stage).glob('attempts/*/request_receipt.json')))
    with wrapper(stage): await j.run(arguments(stage, True))
    validate()
    after = len(list(run_area(stage).glob('attempts/*/request_receipt.json')))
    require(after <= (5 if stage == 'development' else 15), 'stage_budget_exceeded')
    record('run', stage, status='completed_runner_return', new_requests=after-before, batch_receipts=after)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'preflight', 'run'])
    parser.add_argument('--stage', choices=['development', 'holdout_followup'])
    parser.add_argument('--allow-local-calls', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare': prepare()
    else:
        require(args.stage is not None, 'stage_required')
        if args.command == 'preflight': preflight(args.stage)
        else:
            require(args.allow_local_calls, 'local_calls_flag_required')
            asyncio.run(run(args.stage))
