"""Prepare and run an isolated development-only extraction-example ablation.

Prepare captures exact full prompts without generation. Preflight performs only
local model metadata checks. The fixed 12-cell run requires --allow-local-calls.
No holdout response, extraction, score, parser or source file is used or changed.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import difflib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as judges
import cce_alternative_development as helper

BASE = ROOT / 'artifacts/cce_validation/judges'
OUT = BASE / 'stability_remediation_v2'
RUN = OUT / 'run'
OLD = BASE / 'local_stability_supplement_v2'
V1 = BASE / 'stability_remediation_plan_v1'
RUBRIC = ROOT / 'prompts/eval_oeq_teacher_rubric.txt'
LEDGER = BASE / 'request_ledger.jsonl'
MODELS = ['local_qwen3_8b', 'local_llama3_8b']
read, save, filehash = judges.read, judges.save, judges.filehash


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def actual_count():
    return sum(r.get('event') == 'request_started' for r in judges.ledger_rows(LEDGER))


def edits_apply(text, edits):
    for edit in edits:
        require(text.count(edit['old']) == 1, 'exact_replacement_count_' + edit['id'])
        text = text.replace(edit['old'], edit['new'], 1)
    return text


def transform(text):
    text = edits_apply(text, read(OUT / 'inherited_v1_prompt_edits.json'))
    return edits_apply(text, read(OUT / 'prompt_edits.json'))


def reference_suffix(case):
    return ('\n\n[SUPPLIED REFERENCE EVIDENCE]\n' + judges.canonical(case['references']) +
            '\nUse only evidence applicable to the question and declared route; preserve uncertainty.\n')


def run_args(allow=False):
    return SimpleNamespace(out=RUN, cases=OUT / 'cases.json', model_config=OUT / 'local_config_snapshot.json',
        models=MODELS, question_file=judges.HIST, demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None, ledger=LEDGER, total_budget=300, external_request_count=0,
        max_calls=12, max_attempts=1, repeats=3, temperature=0.0, max_output_tokens=8192,
        timeout_seconds=600, allow_api=allow)


def record_command(command, status, **extra):
    path = OUT / 'actual_execution_commands.json'
    history = read(path) if path.exists() else []
    history.append({'utc': judges.now(), 'command': command, 'status': status,
        'cwd': str(ROOT), 'argv': [sys.executable, 'scripts/cce_stability_remediation_v2.py', command] +
        (['--allow-local-calls'] if command == 'run' else []),
        'script_sha256': filehash(__file__), 'package_requests': actual_count(), **extra})
    save(path, history)


def frozen_plan():
    plan = read(OUT / 'plan.json')
    for path, expected in plan['frozen_files'].items():
        require(filehash(path) == expected, 'frozen_input_changed:' + Path(path).name)
    for path, expected in plan['protected_original_files'].items():
        require(filehash(path) == expected, 'protected_original_changed:' + Path(path).name)
    return plan


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists():
        plan = frozen_plan()
        print(judges.canonical({'status': 'existing_frozen_plan_reused', 'planned_cells': len(plan['matrix']), 'new_requests': 0}))
        record_command('prepare', 'existing_frozen_plan_reused', new_requests=0)
        return
    require(not list(RUN.glob('attempts/*/request_receipt.json')), 'existing_request_prevents_prepare')
    before = filehash(LEDGER); count_before = actual_count()
    prior = read(V1 / 'plan.json')
    protected = dict(prior['protected_input_sha256'])
    protected.update({str(V1 / name): expected for name, expected in prior['frozen_files'].items()})
    protected[str(V1 / 'plan.json')] = filehash(V1 / 'plan.json')
    protected[str(V1 / 'analysis_verification.json')] = filehash(V1 / 'analysis_verification.json')
    protected[str(ROOT / 'scripts/cce_analyze_stability_remediation_v1.py')] = filehash(ROOT / 'scripts/cce_analyze_stability_remediation_v1.py')
    for path, expected in protected.items():
        require(filehash(path) == expected, 'historical_input_changed:' + Path(path).name)
    cases = read(OLD / 'cases.json')['cases']
    require(len(cases) == 2 and sorted(c['question_id'] for c in cases) == [2, 21], 'fixed_two_development_answers_missing')
    config = read(OLD / 'local_config_snapshot.json')
    require([m['name'] for m in config['models']] == MODELS, 'historical_two_judge_order_changed')
    for model in config['models']:
        require(model['host'] == 'http://127.0.0.1:11434' and model['max_tokens'] == 8192 and
                model['num_ctx'] == 40960 and model['temperature'] == 0, 'frozen_model_setting_mismatch')
    for source, dest in [(OLD / 'cases.json', 'cases.json'), (OLD / 'local_config_snapshot.json', 'local_config_snapshot.json'),
                         (V1 / 'final_output_schema.json', 'final_output_schema.json'),
                         (V1 / 'prompt_edits.json', 'inherited_v1_prompt_edits.json')]:
        (OUT / dest).write_bytes(source.read_bytes())
        require(filehash(OUT / dest) == filehash(source), 'source_copy_not_byte_identical')
    original = RUBRIC.read_text(encoding='utf-8')
    v1_rubric = (V1 / 'rubric_final_schema.txt').read_text(encoding='utf-8')
    inherited = read(OUT / 'inherited_v1_prompt_edits.json')
    require(edits_apply(original, inherited[:2]) == v1_rubric, 'v1_template_not_reproduced')
    marker_example = '- 示例: {"Alexa fluor 647": "c-fos",  "DAPI": ""}'
    sample_ri_example = '- sample_ri_value: 样本的理论目标 RI 值（如脑组织 ≈ 1.46，骨骼 ≈ 1.56）。'
    start = v1_rubric.index('输出格式 (Output Format for Extraction):')
    end = v1_rubric.index('Now analyze MODEL_PROTOCOL and return one evaluated JSON instance', start)
    extraction_example = v1_rubric[start:end].rstrip()
    edits = [
        {'id': 'extraction_3_1_marker_example', 'old': marker_example,
         'new': '- 字段结构见下方最终 typed schema 的 marker_dict；此处不提供具体标记示例。'},
        {'id': 'extraction_3_4_sample_RI_parenthetical_example', 'old': sample_ri_example,
         'new': '- sample_ri_value: 样本的理论目标 RI 值。字段类型见下方最终 typed schema。'},
        {'id': 'extraction_worked_output_example', 'old': extraction_example,
         'new': '输出格式 (Output Format for Extraction):\n请在最终 JSON 的 "extraction" 字段中输出当前方案对应的提取结果；字段结构和类型遵循下方已有的最终 typed schema。返回结果实例，不返回 schema 本身。'},
    ]
    for edit in edits:
        position = v1_rubric.index(edit['old'])
        edit['source'] = {'path': str(V1 / 'rubric_final_schema.txt'), 'sha256': filehash(V1 / 'rubric_final_schema.txt'),
            'start_codepoint': position, 'end_codepoint': position + len(edit['old']),
            'line': v1_rubric[:position].count('\n') + 1}
    save(OUT / 'prompt_edits.json', edits)
    variant = edits_apply(v1_rubric, edits)
    (OUT / 'rubric_extraction_examples_removed.txt').write_text(variant, encoding='utf-8')
    (OUT / 'rubric_v1_to_v2.diff').write_text(''.join(difflib.unified_diff(
        v1_rubric.splitlines(keepends=True), variant.splitlines(keepends=True),
        fromfile='frozen/v1_final_schema_rubric', tofile='v2/extraction_examples_removed')), encoding='utf-8')
    prefix = v1_rubric[:v1_rubric.index('3.1 荧光标记字典 (marker_dict)')]
    require(variant.startswith(prefix), 'scientific_score_sections_changed')
    preserved_sections = {}
    for title, following in [('3.2 透明方法总耗时', '3.3 透明方法名称'),
                             ('3.3 透明方法名称', '3.4 折射率信息'),
                             ('3.5 参考时间区间', '输出格式 (Output Format for Extraction):')]:
        section = v1_rubric[v1_rubric.index(title):v1_rubric.index(following, v1_rubric.index(title))]
        require(section in variant, 'unchanged_scientific_section_modified')
        preserved_sections[title] = judges.digest(section)
    require(filehash(OUT / 'final_output_schema.json') == filehash(V1 / 'final_output_schema.json'), 'final_typed_schema_changed')
    checks = []
    for case in cases:
        original_prompt = helper.exact_runner_prompt(case)
        v1_prompt = edits_apply(original_prompt, inherited)
        require(v1_prompt == (V1 / f"q{case['question_id']}_proposed_prompt.txt").read_text(encoding='utf-8'), 'frozen_v1_full_prompt_not_reproduced')
        sent = transform(original_prompt)
        for field in ('specific_question', 'model_response'):
            require(original_prompt.count(case[field]) == sent.count(case[field]) == 1, 'full_task_or_answer_changed')
        suffix = reference_suffix(case)
        require(original_prompt.endswith(suffix) and sent.endswith(suffix), 'full_reference_context_changed')
        for label, text in [('original', original_prompt), ('v1', v1_prompt), ('v2', sent)]:
            (OUT / f"q{case['question_id']}_{label}_prompt.txt").write_text(text, encoding='utf-8')
        for model in config['models']:
            bound = len(sent.encode('utf-8')) + model['max_tokens'] + 256
            require(bound <= model['num_ctx'], 'context_bound_exceeded_no_truncation_allowed')
            checks.append({'case_id': case['case_id'], 'question_id': case['question_id'], 'judge': model['name'],
                'full_input_sha256': judges.digest({'question': case['specific_question'], 'question_id': case['question_id'],
                    'protocol': case['model_response'], 'references': case['references']}),
                'question_sha256': judges.digest(case['specific_question']), 'answer_sha256': judges.digest(case['model_response']),
                'references_sha256': judges.digest(case['references']), 'prompt_sha256': filehash(OUT / f"q{case['question_id']}_v2_prompt.txt"),
                'prompt_utf8_bytes': len(sent.encode('utf-8')), 'conservative_context_bound': bound,
                'num_ctx': model['num_ctx'], 'max_output_tokens': model['max_tokens'], 'full_original_task_answer_reference_preserved': True})
    save(OUT / 'offline_context_preflight.json', {'status': 'pass', 'case_judge_checks': checks,
        'checks': len(checks), 'planned_cells': 12, 'new_requests': 0, 'network_or_generation_required': False,
        'same_conservative_byte_guard_as_cce_judges': True})
    delta = {'intervention_id': 'extraction_examples_removed_v2', 'parent_intervention': 'final_schema_only_v1',
        'new_exact_replacements': [e['id'] for e in edits], 'new_replacement_count': len(edits),
        'typed_schema_changed': False, 'uppercase_C_Co_section_examples_changed': False,
        'original_rubric_file_changed': False, 'scientific_judgment_rules_changed': False,
        'original_loader_changed': False, 'EGES_formulas_changed': False, 'fixed_demands_changed': False,
        'full_task_answer_and_reference_changed': False, 'model_settings_changed_from_two_judge_v2': False,
        'preserved_section_hashes': preserved_sections,
        'source_schema_sha256': filehash(V1 / 'final_output_schema.json'),
        'proposed_schema_sha256': filehash(OUT / 'final_output_schema.json'),
        'source_rubric_sha256': filehash(RUBRIC), 'v1_rubric_sha256': filehash(V1 / 'rubric_final_schema.txt'),
        'v2_rubric_sha256': filehash(OUT / 'rubric_extraction_examples_removed.txt'),
        'historical_evidence': {'development_qids': [2, 21], 'literal_flag_source': str(V1 / 'analysis_verification.json'),
            'basis': 'Already-exposed development answers and v1 literal marker/RI contradictions; not holdout scientific values.'},
        'holdout_boundary': 'The eight technical failure classes have been reported separately. This script does not read holdout outputs, fields or scores and does not change any holdout input/configuration/result.'}
    save(OUT / 'config_delta.json', delta)
    files = ['cases.json', 'local_config_snapshot.json', 'final_output_schema.json', 'inherited_v1_prompt_edits.json',
             'prompt_edits.json', 'rubric_extraction_examples_removed.txt', 'rubric_v1_to_v2.diff',
             'offline_context_preflight.json', 'config_delta.json']
    files += [f'q{qid}_{label}_prompt.txt' for qid in (2, 21) for label in ('original', 'v1', 'v2')]
    frozen = {str(OUT / name): filehash(OUT / name) for name in files}
    frozen[str(Path(__file__).resolve())] = filehash(__file__)
    plan = {'status': 'prepared_not_executed', 'created_utc': judges.now(), 'intervention_id': 'extraction_examples_removed_v2',
        'hypothesis': 'Residual fact-filled extraction examples can contaminate extraction after removal of the final worked example; this is a development intervention, not validation on untouched data.',
        'matrix': [{'case_id': c['case_id'], 'question_id': c['question_id'], 'judge': model, 'repeat_index': rep,
                    'attempt': 1, 'stage': 'all_prespecified_without_result_gate'}
                   for rep in range(3) for c in cases for model in MODELS],
        'source_answers': 2, 'judge_families': 2, 'repeats_each': 3, 'planned_total_new_requests': 12,
        'maximum_attempts_each': 1, 'package_requests_at_preparation': count_before,
        'package_requests_after_this_batch_maximum_if_no_other_batches': count_before + 12,
        'new_requests_at_preparation': 0, 'max_output_tokens': 8192, 'num_ctx': 40960, 'temperature': 0,
        'timeout_seconds': 600, 'formal_eligible': False, 'expert_confirmation': None,
        'selection_rule': 'All two already fixed development answers x both frozen judges x all three repeats; no result-based continuation gate, sample replacement, retry, or prompt tuning.',
        'historical_comparison_rule': 'Old two-family v2 and v1 Llama six are distinct prompt-version histories; never pool them as same-configuration repeats or reuse their requests in the new 12-cell matrix.',
        'result_policy': 'Preserve every raw response/receipt, failed/NA outcome, and per-metric availability. Technical pass, literal contradictions, repeat variability and scientific validity are separate endpoints.',
        'holdout_policy': delta['holdout_boundary'], 'frozen_files': frozen, 'protected_original_files': protected,
        'run_command_not_executed': [sys.executable, 'scripts/cce_stability_remediation_v2.py', 'run', '--allow-local-calls']}
    save(OUT / 'plan.json', plan)
    require(filehash(LEDGER) == before and actual_count() == count_before, 'prepare_unexpected_request')
    frozen_plan()
    record_command('prepare', 'completed', new_requests=0, plan_sha256=filehash(OUT / 'plan.json'))
    print(judges.canonical({'status': 'prepared_not_executed', 'planned_cells': 12, 'new_requests': 0,
        'package_requests_at_preparation': count_before, 'conservative_context_bounds': [r['conservative_context_bound'] for r in checks],
        'plan_sha256': filehash(OUT / 'plan.json'), 'config_sha256': filehash(OUT / 'local_config_snapshot.json')}))


@contextlib.contextmanager
def isolated_wrapper():
    original_runtime, original_contract = judges.runtime, judges.contract

    def runtime(arguments):
        runner, api_type, registry = original_runtime(arguments)
        original_evaluate = runner.evaluate_response_with_teacher

        async def evaluate(teacher, question, answer, model_space, question_meta, template):
            case = next(c for c in read(OUT / 'cases.json')['cases'] if c['question_id'] == question_meta['question_id'])
            require(case['specific_question'] == question and case['model_response'] == answer, 'runtime_case_changed')

            class ReplacingTeacher:
                model_name = teacher.model_name

                async def _acall(self, prompt):
                    revised = transform(prompt)
                    require(revised + reference_suffix(case) == (OUT / f"q{case['question_id']}_v2_prompt.txt").read_text(encoding='utf-8'),
                            'runtime_prompt_not_exact_frozen_version')
                    return await teacher._acall(revised)

            result = await original_evaluate(ReplacingTeacher(), question, answer, model_space, question_meta, template)
            result['prompt_variant_provenance'] = {'variant': 'extraction_examples_removed_v2',
                'original_runner_prompt_hash_scope': 'pretransform original rubric, not transmitted prompt',
                'transmitted_prompt_hash_location': 'trial.prompt_sha256 and actual attempt/prompt.txt',
                'raw_model_return_modified': False}
            return result

        runner.evaluate_response_with_teacher = evaluate
        return runner, api_type, registry

    def contract(arguments, runner, registry, models):
        original = original_contract(arguments, runner, registry, models)
        require(original == read(OLD / 'preflight.json')['contract'], 'original_scoring_source_or_model_contract_changed')
        return {**original, 'prompt_variant': {'id': 'extraction_examples_removed_v2',
            'plan_sha256': filehash(OUT / 'plan.json'), 'wrapper_sha256': filehash(__file__),
            'edits_sha256': filehash(OUT / 'prompt_edits.json'), 'inherited_v1_edits_sha256': filehash(OUT / 'inherited_v1_prompt_edits.json'),
            'typed_schema_sha256': filehash(OUT / 'final_output_schema.json'),
            'rubric_variant_sha256': filehash(OUT / 'rubric_extraction_examples_removed.txt'),
            'complete_matrix_cases_sha256': filehash(OUT / 'cases.json'),
            'scope': '12 prespecified development cells; no result gate/retry; original loader and EGES unchanged'}}

    judges.runtime, judges.contract = runtime, contract
    try:
        yield
    finally:
        judges.runtime, judges.contract = original_runtime, original_contract


def preflight():
    plan = frozen_plan(); before = filehash(LEDGER)
    with isolated_wrapper():
        _, _, _, models, cases, contract = judges.preflight(run_args())
    checks = []
    for rep in range(3):
        for case in cases:
            for model in models:
                one = {**contract, 'models': [{'name': model['name'], 'family': model['family'], 'settings': model['public']}]}
                identity = {'case_id': case['case_id'], 'input_sha256': case['input_sha256'],
                    'judge': model['name'], 'repeat_index': rep, 'contract_sha256': judges.digest(one)}
                checks.append({'identity': identity, 'planned_trial_id': judges.digest(identity), 'attempt': 1})
    require(len(checks) == len(plan['matrix']) == 12 and len({c['planned_trial_id'] for c in checks}) == 12, 'planned_trial_identity_invalid')
    require(filehash(LEDGER) == before, 'preflight_unexpected_request')
    frozen_plan()
    save(OUT / 'preflight_verification.json', {'status': 'pass', 'planned_trials': checks,
        'planned_cells': len(checks), 'contract_sha256': judges.digest(contract), 'new_requests': 0,
        'package_requests': actual_count(), 'original_two_judge_settings_exact': True,
        'local_installed_model_metadata_checked': True, 'generation_endpoint_called': False,
        'exact_full_prompts_and_context_checked_offline': True, 'protected_files_unchanged': True})
    record_command('preflight', 'completed', new_requests=0, contract_sha256=judges.digest(contract))


async def run():
    frozen_plan()
    receipts_before = list(RUN.glob('attempts/*/request_receipt.json'))
    require(len(receipts_before) <= 12, 'batch_budget_exceeded')
    with isolated_wrapper():
        await judges.run(run_args(allow=True))
    frozen_plan()
    receipts_after = list(RUN.glob('attempts/*/request_receipt.json'))
    require(len(receipts_after) <= 12, 'batch_budget_exceeded')
    record_command('run', 'completed_runner_return', new_requests=len(receipts_after) - len(receipts_before),
                   actual_batch_receipts=len(receipts_after))


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
        if not args.allow_local_calls:
            raise SystemExit('run requires --allow-local-calls; no model request made')
        asyncio.run(run())
