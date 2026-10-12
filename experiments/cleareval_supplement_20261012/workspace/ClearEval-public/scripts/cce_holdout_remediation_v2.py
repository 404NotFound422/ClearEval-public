"""Apply the unchanged, development-tested v2 prompt to all 15 original cases.

This is a separate technical follow-up, not a new untouched holdout. Original
responses are not repaired and original scientific outputs are not inspected.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
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
OLD = BASE / 'judges/local_extraction_holdout_v1'
OUT = BASE / 'judges/holdout_remediation_v2'
SEALED = OUT / 'sealed'
RUN = SEALED / 'run'
LEDGER = BASE / 'judges/request_ledger.jsonl'
MODEL = 'local_qwen3_8b'
OLD_CONTRACT = 'c27211dc7513d3ac24ee211ce3950eb1a1d0b553e87b0374b93190fc7dfe56ae'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def count():
    return sum(r.get('event') == 'request_started' for r in j.ledger_rows(LEDGER))


def bind(path):
    return {'path': str(Path(path).resolve()), 'sha256': j.filehash(path)}


def record(stage, **kwargs):
    path = OUT / 'actual_commands.json'
    records = j.read(path) if path.exists() else []
    records.append({'stage': stage, 'utc': j.now(), 'cwd': str(ROOT),
        'argv': [sys.executable, 'scripts/cce_holdout_remediation_v2.py', stage] +
                (['--allow-local-calls'] if stage == 'run' else []),
        'script_sha256': j.filehash(__file__), 'package_requests': count(), **kwargs})
    j.save(path, records)


def arguments(allow=False):
    return SimpleNamespace(out=RUN, cases=SEALED / 'cases.json',
        model_config=OUT / 'local_config_snapshot.json', models=[MODEL],
        question_file=j.HIST, demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None, ledger=LEDGER, total_budget=300, external_request_count=0,
        max_calls=15, max_attempts=1, repeats=1, temperature=0.0,
        max_output_tokens=8192, timeout_seconds=600, allow_api=allow)


def validate():
    plan = j.read(OUT / 'plan.json')
    for field in ('frozen_inputs', 'protected_originals'):
        for b in plan[field]:
            require(j.filehash(b['path']) == b['sha256'], field + '_changed:' + Path(b['path']).name)
    return plan


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    SEALED.mkdir(exist_ok=True)
    if (OUT / 'plan.json').exists():
        plan = validate()
        record('prepare', status='frozen_plan_reused', new_requests=0)
        print(j.canonical({'status': 'frozen_plan_reused', 'matrix': len(plan['matrix']), 'new_requests': 0}))
        return
    require(not list(RUN.glob('attempts/*/request_receipt.json')), 'existing_request_prevents_prepare')
    before = count()
    require(before + 15 <= 300, 'insufficient_package_budget')
    source_plan = dev.frozen_plan()
    facts = j.read(dev.OUT / 'analysis/report_facts.json')
    # Bind the existing development analysis; do not derive a new intervention
    # from any holdout response. All edits are exactly the prior v2 edits.
    require(j.read(dev.OUT / 'run/summary.json')['successful_trials'] == 12, 'development_v2_incomplete')
    originals = j.read(BASE / 'judges/holdout_failure_audit_v1/verification.json')['protected_input_hashes']
    for b in originals:
        require(j.filehash(b['path']) == b['sha256'], 'original_protected_file_changed')
    for source, target in [(OLD / 'sealed/cases.json', SEALED / 'cases.json'),
                           (OLD / 'local_config_snapshot.json', OUT / 'local_config_snapshot.json'),
                           (OLD / 'sealed/identity_manifest.csv', SEALED / 'identity_manifest.csv'),
                           (OLD / 'sealed/step_availability.json', SEALED / 'step_availability.json')]:
        target.write_bytes(source.read_bytes())
        require(j.filehash(source) == j.filehash(target), 'copy_changed')
    cases = j.read(SEALED / 'cases.json')['cases']
    require(len(cases) == 15 and [c['anonymous_answer_id'] for c in cases] == [f'A{i:02}' for i in range(6, 21)], 'fixed_sample_order_changed')
    require(all(c['references'] == [] for c in cases), 'original_reference_context_changed')
    model = j.read(OUT / 'local_config_snapshot.json')['models']
    require(len(model) == 1 and model[0]['name'] == MODEL and model[0]['host'] == 'http://127.0.0.1:11434', 'not_original_loopback_model')
    matrix = []
    prompts = []
    for case in cases:
        old_prompt = helper.exact_runner_prompt(case)
        prompt = dev.transform(old_prompt)
        require(prompt.endswith(dev.reference_suffix(case)), 'reference_suffix_changed')
        for field in ('specific_question', 'model_response'):
            require(old_prompt.count(case[field]) == prompt.count(case[field]) == 1, 'full_text_changed')
        bound = len(prompt.encode('utf-8')) + 8192 + 256
        require(bound <= 40960, 'context_exceeds_bound_no_truncation')
        path = SEALED / 'prompts' / (case['anonymous_answer_id'] + '.txt')
        path.parent.mkdir(exist_ok=True)
        path.write_text(prompt, encoding='utf-8')
        prompts.append(path)
        matrix.append({'anonymous_answer_id': case['anonymous_answer_id'], 'case_id': case['case_id'],
            'question_id': case['question_id'], 'judge': MODEL, 'repeat_index': 0, 'attempt': 1,
            'input_sha256': j.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                'protocol': case['model_response'], 'references': case['references']}),
            'answer_sha256': case['answer_sha256'], 'question_sha256': case['question_sha256'],
            'prompt_sha256': j.filehash(path), 'prompt_path': str(path),
            'conservative_context_bound': bound, 'prompt_utf8_bytes': len(prompt.encode('utf-8'))})
    delta = {'prompt_intervention': 'exact_existing_extraction_examples_removed_v2',
        'source_development_plan': bind(dev.OUT / 'plan.json'),
        'source_development_facts': bind(dev.OUT / 'analysis/report_facts.json'),
        'new_prompt_edits': 0, 'loader_changes': 0, 'nested_uppercase_alias_repair': False,
        'raw_return_repair': False, 'scientific_rubric_change': False, 'EGES_change': False,
        'full_question_answer_reference_changes': False, 'model_setting_changes': False,
        'original_holdout_results_overwritten': False,
        'residual_contract_ambiguity': 'Uppercase local C/Co examples remain as in the tested v2; technical success is measured, not assumed.',
        'exposure': 'Prior aggregate technical failure categories known; no original holdout scientific values used to select or tune this prompt.',
        'primary_comparison': 'All original 15 technical outcomes, paired by anonymous identity; no best-of-version mixing.',
        'analysis': 'Completion, strict parser/field failures, raw provenance, same-formula identity replay; scientific accuracy awaits the original expert review.',
        'scientific_holdout_claim': False}
    j.save(OUT / 'config_delta.json', delta)
    files = [Path(__file__).resolve(), ROOT / 'scripts/cce_judges.py',
        ROOT / 'scripts/cce_alternative_development.py', ROOT / 'scripts/cce_stability_remediation_v2.py',
        SEALED / 'cases.json', SEALED / 'identity_manifest.csv', SEALED / 'step_availability.json',
        OUT / 'local_config_snapshot.json', OUT / 'config_delta.json',
        OLD / 'plan.json', OLD / 'frozen_judge_contract.json',
        dev.OUT / 'analysis/report_facts.json', dev.OUT / 'plan.json',
        dev.OUT / 'inherited_v1_prompt_edits.json', dev.OUT / 'prompt_edits.json',
        dev.OUT / 'final_output_schema.json', dev.OUT / 'rubric_extraction_examples_removed.txt',
        BASE / 'human_review/selection.json', BASE / 'human_review/reviewer/review_items.csv',
        ROOT / 'scripts/cce_validation.py', *prompts]
    files += [Path(p) for p in j.read(OLD / 'frozen_judge_contract.json')['files']]
    files = [p if p.is_absolute() else ROOT / p for p in files]
    plan = {'status': 'frozen_before_requests', 'created_utc': j.now(), 'matrix': matrix,
        'source_cases': 15, 'planned_requests': 15, 'repeats': 1, 'max_attempts': 1,
        'package_requests_before': before, 'expected_package_requests_after': before + 15,
        'total_budget': 300, 'remaining_after_maximum': 300 - before - 15,
        'selection': 'All 15 original selected answers; same order, full texts and empty reference context. No failure-only selection or result gate.',
        'interpretation': 'Separate technical follow-up using a development-tested prompt, not independent scientific holdout validation.',
        'primary_trial_rule': 'repeat_index=0; all failures retained; no replacement or retry',
        'original_contract_sha256': OLD_CONTRACT,
        'frozen_inputs': [bind(p) for p in dict.fromkeys(files)],
        'protected_originals': originals, 'formal_eligible': False, 'expert_returns': 0}
    j.save(OUT / 'plan.json', plan)
    validate()
    require(count() == before, 'prepare_made_request')
    record('prepare', status='completed', new_requests=0, plan_sha256=j.filehash(OUT / 'plan.json'))
    print(j.canonical({'status': 'prepared', 'cells': 15, 'new_requests': 0, 'package_requests': before,
        'context_bound_min': min(r['conservative_context_bound'] for r in matrix),
        'context_bound_max': max(r['conservative_context_bound'] for r in matrix)}))


@contextlib.contextmanager
def wrapper():
    old_runtime, old_contract = j.runtime, j.contract
    def runtime(args):
        runner, api, registry = old_runtime(args)
        evaluate_original = runner.evaluate_response_with_teacher
        cases = {c['question_id']: c for c in j.read(SEALED / 'cases.json')['cases']}
        async def evaluate(teacher, question, answer, model_space, question_meta, template):
            case = cases[question_meta['question_id']]
            require(question == case['specific_question'] and answer == case['model_response'], 'runtime_full_text_changed')
            class ReplacingTeacher:
                model_name = teacher.model_name
                async def _acall(self, prompt):
                    revised = dev.transform(prompt)
                    expected = (SEALED / 'prompts' / (case['anonymous_answer_id'] + '.txt')).read_text(encoding='utf-8')
                    require(revised + dev.reference_suffix(case) == expected, 'runtime_prompt_not_frozen')
                    return await teacher._acall(revised)
            result = await evaluate_original(ReplacingTeacher(), question, answer, model_space, question_meta, template)
            result['prompt_variant_provenance'] = {'variant': 'existing_development_v2_on_original15',
                'original_runner_prompt_hash_scope': 'pretransform original rubric, not transmitted prompt',
                'transmitted_prompt_hash_location': 'trial.prompt_sha256 and attempt/prompt.txt',
                'raw_model_return_modified': False}
            return result
        runner.evaluate_response_with_teacher = evaluate
        return runner, api, registry
    def contract(args, runner, registry, models):
        original = old_contract(args, runner, registry, models)
        require(j.digest(original) == OLD_CONTRACT, 'original_runtime_contract_drift')
        return {**original, 'prompt_variant': {
            'id': 'existing_development_v2_on_original15', 'plan_sha256': j.filehash(OUT / 'plan.json'),
            'wrapper_sha256': j.filehash(__file__), 'development_plan_sha256': j.filehash(dev.OUT / 'plan.json'),
            'typed_schema_sha256': j.filehash(dev.OUT / 'final_output_schema.json'),
            'rubric_variant_sha256': j.filehash(dev.OUT / 'rubric_extraction_examples_removed.txt'),
            'scope': '15 prespecified technical follow-up cells; original loader and EGES unchanged; no retry or scientific accuracy claim'}}
    j.runtime, j.contract = runtime, contract
    try:
        yield
    finally:
        j.runtime, j.contract = old_runtime, old_contract


def preflight():
    plan = validate()
    before = count()
    with wrapper(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, _, _, models, cases, contract = j.preflight(arguments())
    require(len(models) == 1 and len(cases) == 15, 'preflight_matrix_changed')
    checks = []
    for case in cases:
        identity = {'case_id': case['case_id'], 'input_sha256': case['input_sha256'],
            'judge': MODEL, 'repeat_index': 0, 'contract_sha256': j.digest(contract)}
        checks.append({'identity': identity, 'trial_id': j.digest(identity)})
    require(count() == before, 'preflight_made_request')
    validate()
    j.save(OUT / 'preflight_verification.json', {'status': 'pass', 'planned_trials': checks,
        'contract_sha256': j.digest(contract), 'original_contract_sha256': OLD_CONTRACT,
        'full_inputs_match': True, 'new_generation_requests': 0, 'metadata_loopback_only': True})
    record('preflight', status='completed', new_requests=0, contract_sha256=j.digest(contract))
    print(j.canonical({'status': 'preflight_pass', 'planned_requests': 15, 'package_requests': before,
        'remaining_after_batch': 300 - before - 15, 'contract_sha256': j.digest(contract)}))


async def run():
    validate()
    before = len(list(RUN.glob('attempts/*/request_receipt.json')))
    with wrapper():
        await j.run(arguments(True))
    validate()
    after = len(list(RUN.glob('attempts/*/request_receipt.json')))
    require(after <= 15, 'batch_budget_exceeded')
    record('run', status='completed_runner_return', new_requests=after-before, batch_receipts=after)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'preflight', 'run'])
    parser.add_argument('--allow-local-calls', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
    elif args.command == 'preflight':
        preflight()
    else:
        require(args.allow_local_calls, 'run_requires_allow_local_calls')
        asyncio.run(run())
