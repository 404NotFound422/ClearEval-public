"""Offline, metadata-only attribution of the frozen holdout technical failures.

No returned text, extracted scientific values, score values, repairs or calls are
exported. The original loader validation slice is executed on sealed responses.
"""
from __future__ import annotations
import collections
import csv
import hashlib
import json
import re
import socket
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import evaluator_integrity as integrity

BASE = ROOT / 'artifacts/cce_validation'
SOURCE = BASE / 'judges/local_extraction_holdout_v1'
RUN = SOURCE / 'sealed/run'
OUT = BASE / 'judges/holdout_failure_audit_v1'
LEDGER = BASE / 'judges/request_ledger.jsonl'
EXPERT = BASE / 'human_review/reviewer/review_items.csv'
CONTRACT = 'c27211dc7513d3ac24ee211ce3950eb1a1d0b553e87b0374b93190fc7dfe56ae'
EXT = {'method_name', 'marker_dict', 'clearing_total_time_hours', 'reagent_ri_value',
       'sample_ri_value', 'protocol_time_hours', 'reasoning', 'method_stages',
       'schema_version', 'field_support'}
METRICS = {'c_step', 'c_param', 'co_order', 'co_method', 'co_param', 'co_chem',
           'co_chemical', 'C_step', 'C_param', 'Co_order', 'Co_method', 'Co_param', 'Co_chem'}
KEYS = EXT | METRICS | {'scores', 'extraction', 'completeness', 'correctness',
       'total_weighted_score', 'total_completeness_score', 'total_correctness_score',
       'critical_warnings', 'score', 'max_score', 'description', 'meta_data',
       'visualization_data', 'overall_score', 'completeness_critical_warnings'}


def blocked_network(*args, **kwargs):
    raise RuntimeError('network_disabled_for_offline_audit')


socket.create_connection = blocked_network
socket.socket.connect = blocked_network
socket.socket.connect_ex = blocked_network


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def rawsha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def require(condition, category):
    if not condition:
        raise RuntimeError(category)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + '\n', encoding='utf-8')


def kind(value):
    if value is None: return 'null'
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, dict): return 'object'
    if isinstance(value, list): return 'array'
    if isinstance(value, str): return 'string'
    if isinstance(value, (float, int)): return 'number'
    return 'non_JSON_type'


def safe_key(key):
    return key if key in KEYS else 'unrecognized_key_sha256:' + rawsha(str(key))


def safe_path(path):
    return '.'.join(safe_key(p) for p in path.split('.'))


def error_metadata(exc):
    """Never export str(exc); match known validator messages to structural codes."""
    msg = str(exc)
    result = {'error_type': type(exc).__name__, 'category': 'other_validation_error', 'fields': []}
    prefixes = {
        'Missing teacher score: ': 'missing_score_record',
        'Missing teacher score group: ': 'missing_score_group',
        'Unknown teacher score needs reasoning: ': 'null_score_without_reasoning',
        'Invalid teacher score: ': 'invalid_score_range_or_type',
        'Unknown teacher group needs null total: ': 'non_null_total_with_unknown_component',
        'Invalid teacher total: ': 'invalid_group_total_range_or_type',
        'Teacher extraction missing required fields: ': 'missing_extraction_fields',
        'Unknown extraction fields: ': 'unknown_extraction_fields',
        'Duplicate JSON key: ': 'duplicate_JSON_key',
    }
    for prefix, category in prefixes.items():
        if msg.startswith(prefix):
            result.update(category=category, fields=[safe_path(f.strip()) for f in msg[len(prefix):].split(',')])
            return result
    exact = {
        'Teacher extraction must be an object': ('extraction_not_object', ['extraction']),
        'Teacher scores must be an object': ('scores_not_object', ['scores']),
        'Teacher marker_dict must map strings to strings': ('marker_map_value_type', ['marker_dict']),
        'Teacher method_name must be a string or explicit null': ('extraction_field_type', ['method_name']),
        'protocol_time_hours must be finite nonnegative hours array or null': ('extraction_field_type_or_domain', ['protocol_time_hours']),
        'Extraction reasoning must be text': ('extraction_field_type', ['reasoning']),
        'method_stages must be nonempty array or explicit null': ('extraction_field_type', ['method_stages']),
        'Method stage requires text id, method_name and exact quote': ('method_stage_schema', ['method_stages']),
        'Duplicate method stage ID': ('duplicate_stage_id', ['method_stages']),
        'Unsupported flat extraction schema_version': ('unsupported_schema_version', ['schema_version']),
        'field_support must be an object': ('extraction_field_type', ['field_support']),
        'Judge JSON root must be an object': ('JSON_root_not_object', []),
        'Incomplete or unsupported JSON fence': ('incomplete_or_unsupported_fence', []),
        'Judge content must be text': ('content_not_string', []),
        'Unpaired unicode surrogate': ('invalid_unicode', []),
    }
    if msg in exact:
        result['category'], result['fields'] = exact[msg]
    elif msg.startswith('Invalid JSON: '):
        result['category'] = 'invalid_JSON_syntax'
        cause = exc.__cause__
        if isinstance(cause, json.JSONDecodeError):
            result.update(json_line=cause.lineno, json_column=cause.colno, json_offset=cause.pos)
    elif msg.startswith('Non-finite JSON number'):
        result['category'] = 'nonfinite_JSON_number'
    else:
        for key in EXT:
            if msg == 'Teacher ' + key + ' must be finite, nonnegative, or explicit null':
                result.update(category='extraction_field_type_or_domain', fields=[key])
    return result


def schema_types(parsed, scores, extraction):
    result = {'root_type': kind(parsed), 'root_fields': {safe_key(k): kind(v) for k, v in parsed.items()},
              'extraction_type': kind(extraction), 'scores_type': kind(scores)}
    if isinstance(extraction, dict):
        result['extraction_fields'] = {safe_key(k): kind(v) for k, v in extraction.items()}
        if isinstance(extraction.get('marker_dict'), dict):
            result['marker_map_entry_types'] = sorted({kind(k) + ' -> ' + kind(v) for k, v in extraction['marker_dict'].items()})
        if isinstance(extraction.get('protocol_time_hours'), list):
            result['protocol_time_array_element_types'] = sorted({kind(v) for v in extraction['protocol_time_hours']})
    if isinstance(scores, dict):
        groups = {}
        for group in ['completeness', 'correctness']:
            value = scores.get(group)
            groups[group] = {'type': kind(value)}
            if isinstance(value, dict):
                groups[group]['field_types'] = {safe_key(k): kind(v) for k, v in value.items()}
                groups[group]['score_record_types'] = {
                    key: {safe_key(k): kind(v) for k, v in value[key].items()}
                    for key in sorted(METRICS & set(value)) if isinstance(value[key], dict)}
        result['score_groups'] = groups
    return result


def source_anchor(path, marker):
    text = path.read_text(encoding='utf-8')
    start = text.index(marker)
    return {'path': str(path), 'sha256': sha(path), 'line': text[:start].count('\n') + 1,
            'anchor': marker}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    plan = read(SOURCE / 'plan.json')
    with EXPERT.open(encoding='utf-8-sig', newline='') as stream:
        expert_rows = list(csv.DictReader(stream))
    expert_returns = sum(bool(r.get('expert_decision', '').strip()) for r in expert_rows)
    require(len(expert_rows) == 160 and expert_returns == 0, 'expert_return_state_changed')
    completion = read(SOURCE / 'completion_summary.json')
    require(completion['faithful_corrections'] == completion['numeric_CCE'] == 0, 'original_completion_scope_changed')
    protected = {str(p): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    protected[str(EXPERT)] = sha(EXPERT)
    for record in plan['frozen_files']:
        require(sha(record['path']) == record['sha256'], 'frozen_input_hash_mismatch')
        protected[record['path']] = record['sha256']
    ledger_before = sha(LEDGER)
    ledger = [json.loads(line) for line in LEDGER.read_text(encoding='utf-8').splitlines() if line.strip()]
    started = [r for r in ledger if r.get('event') == 'request_started']
    by_request = {r['request_id']: r for r in started}
    require(len(by_request) == len(started), 'duplicate_ledger_request')
    require(digest(read(SOURCE / 'frozen_judge_contract.json')) == CONTRACT, 'contract_hash_mismatch')
    preflight = read(RUN / 'preflight.json')
    require(preflight['contract_sha256'] == CONTRACT, 'run_contract_mismatch')
    loader = ROOT / 'OEQ_run_grading_new.py'
    loader_text = loader.read_text(encoding='utf-8')
    begin = loader_text.index('        scores_block = llm_output.get("scores", {})')
    end = loader_text.index('        validate_score_proposals(scores_block)', begin) + len('        validate_score_proposals(scores_block)')
    validation_slice = textwrap.dedent(loader_text[begin:end])
    validator_code = compile(validation_slice, str(loader) + ':original_validation_slice', 'exec')
    trials = {r['case_id']: (p, r) for p in sorted((RUN / 'trials').glob('*.json')) for r in [read(p)]}
    receipts = {r['trial_id']: (p, r) for p in sorted((RUN / 'attempts').glob('*/request_receipt.json')) for r in [read(p)]}
    cases = {r['case_id']: r for r in read(SOURCE / 'sealed/cases.json')['cases']}
    require(len(trials) == len(receipts) == len(plan['matrix']) == 15, 'actual_batch_not_exactly_15')
    rows, failures, inputs = [], [], []
    for cell in plan['matrix']:
        path, trial = trials[cell['case_id']]
        receipt_path, receipt = receipts[cell['planned_trial_id']]
        adir = receipt_path.parent
        identity = {'case_id': cell['case_id'], 'input_sha256': cell['input_sha256'],
                    'judge': 'local_qwen3_8b', 'repeat_index': 0, 'contract_sha256': CONTRACT}
        case = cases[cell['case_id']]
        require(rawsha(case['model_response']) == cell['answer_raw_utf8_sha256'] and
                rawsha(case['specific_question']) == cell['question_raw_utf8_sha256'] and
                case['references'] == [], 'frozen_original_text_or_references_mismatch')
        require(trial['identity'] == identity and trial['trial_id'] == digest(identity) == cell['planned_trial_id'], 'trial_identity_mismatch')
        require(trial['attempt'] == receipt['attempt'] == 1 and receipt == by_request[receipt['request_id']], 'request_identity_mismatch')
        require(trial['full_text_input_sha256'] == cell['input_sha256'] and trial['references_sha256'] == digest([]), 'input_or_reference_mismatch')
        require(sha(adir / 'prompt.txt') == trial['prompt_sha256'], 'prompt_hash_mismatch')
        require(read(adir / 'result.json') == trial, 'trial_attempt_result_mismatch')
        context = read(adir / 'context_check.json')
        require(context['conservative_context_bound'] == cell['conservative_context_bound'] <= 40960 and context['max_output_tokens'] == 8192, 'context_mismatch')
        provider = read(adir / 'provider_response.json')
        content = provider.get('response')
        require(isinstance(content, str), 'provider_response_text_missing')
        evaluation = trial['evaluation']; generation = evaluation.get('teacher_generation') or {}
        if generation.get('technical_status') == 'VALID':
            require(content == generation.get('content'), 'provider_generation_content_mismatch')
        elif isinstance(generation.get('raw_content'), str):
            require(content == generation['raw_content'], 'provider_raw_content_mismatch')
        else:
            require((adir / 'provider_error.json').exists(), 'adapter_error_receipt_missing')
        row = {'answer_id': cell['answer_id'], 'trial_id': trial['trial_id'],
               'request_id': receipt['request_id'], 'request_index': receipt['package_request_index'],
               'status': trial['status'], 'recorded_failure_stage': evaluation.get('failure_stage'),
               'recorded_error_type': evaluation.get('_error_type'),
               'provider_response_present': True, 'provider_done': provider.get('done'),
               'finish_reason': provider.get('done_reason') if provider.get('done_reason') in [None, 'stop', 'length', 'max_tokens', 'limit'] else 'other',
               'prompt_tokens': provider.get('prompt_eval_count'), 'completion_tokens': provider.get('eval_count'),
               'response_characters': len(content), 'response_utf8_bytes': len(content.encode('utf-8')),
               'provider_response_sha256': sha(adir / 'provider_response.json'), 'prompt_sha256': trial['prompt_sha256'],
               'identity_and_receipt_bound': True, 'strict_parse_pass': False, 'original_validation_pass': False}
        parse_error = validation_error = None
        try:
            # Grammar completeness is diagnostic only. Never adopt its parsed data.
            json.loads(integrity.strip_json_fence(content))
            row['standard_JSON_syntax_complete'] = True
        except (ValueError, TypeError):
            row['standard_JSON_syntax_complete'] = False
        try:
            parsed = integrity.parse_judge_object(content)
            row['strict_parse_pass'] = True
        except integrity.JudgeFormatError as exc:
            parse_error = exc
            row['parse_error'] = error_metadata(exc)
        if parse_error is None:
            scope = {'__builtins__': {'any': any}, 'llm_output': parsed,
                     'validate_teacher_extraction': integrity.validate_legacy_extraction,
                     'validate_score_proposals': integrity.validate_score_proposals}
            try:
                exec(validator_code, scope)
                row['original_validation_pass'] = True
            except Exception as exc:
                validation_error = exc
                row['validation_error'] = error_metadata(exc)
            if trial['status'] == 'failed':
                row['schema_types'] = schema_types(parsed, scope.get('scores_block'), scope.get('extraction'))
        if trial['status'] == 'success':
            require(row['original_validation_pass'], 'successful_trial_validation_replay_failed')
            row['classification'] = 'successful_original_structure_validation'
        else:
            require(all(v is None for v in trial['preserved_numeric_proposals'].values()), 'failed_trial_has_numeric_proposal')
            row['failed_numeric_proposals_remain_NA'] = True
            if parse_error is not None:
                row['classification'] = 'provider_completed_but_adapter_' + row['parse_error']['category']
                require(evaluation.get('failure_stage') == 'TEACHER_GENERATION', 'parse_failure_stage_not_adapter')
                pe = read(adir / 'provider_error.json')
                row['provider_error_metadata'] = {k: pe.get(k) for k in ['error_type', 'category', 'http_status']}
                require(pe.get('error_type') == type(parse_error).__name__ == evaluation.get('_error_type'), 'adapter_exception_type_mismatch')
                row['failure_reproduced_by_original_gate'] = True
            elif validation_error is not None:
                row['classification'] = row['validation_error']['category']
                require(str(validation_error) == evaluation.get('_error') and type(validation_error).__name__ == evaluation.get('_error_type'), 'saved_validation_error_not_reproduced')
                row['failure_reproduced_by_original_gate'] = True
            else:
                row['classification'] = 'downstream_failure_requires_separate_metadata_audit'
                row['failure_reproduced_by_original_gate'] = False
            if (adir / 'runner_log.json').exists():
                log = read(adir / 'runner_log.json')
                row['runner_log_status'] = log.get('status') if isinstance(log, dict) else 'non_object'
                row['runner_log_sha256'] = sha(adir / 'runner_log.json')
            failures.append(row)
        rows.append(row)
        for p in [path, receipt_path, adir / 'prompt.txt', adir / 'provider_response.json', adir / 'result.json', adir / 'context_check.json']:
            inputs.append({'path': str(p), 'sha256': sha(p)})
        for name in ['runner_log.json', 'provider_error.json']:
            if (adir / name).exists(): inputs.append({'path': str(adir / name), 'sha256': sha(adir / name)})
    require(len(failures) == 8 and all(r['failure_reproduced_by_original_gate'] for r in failures), 'failure_replay_incomplete')
    require(sha(LEDGER) == ledger_before and all(sha(p) == h for p, h in protected.items()), 'protected_input_changed')
    categories = dict(collections.Counter(r['classification'] for r in failures))
    summary = {'status': 'completed_offline_metadata_only_audit', 'selected_cells': 15,
        'actual_trials': len(rows), 'successful_cells': sum(r['status'] == 'success' for r in rows), 'failed_cells': len(failures),
        'identity_bound_cells': len(rows), 'failed_original_gates_reproduced': len(failures),
        'recorded_failure_stages': dict(collections.Counter(r['recorded_failure_stage'] for r in failures)),
        'technical_failure_classifications': categories,
        'all_provider_returns_done': all(r['provider_done'] is True for r in rows),
        'finish_reason_counts': dict(collections.Counter(r['finish_reason'] for r in rows)),
        'failed_standard_JSON_complete': sum(r['standard_JSON_syntax_complete'] for r in failures),
        'failed_strict_parse_pass': sum(r['strict_parse_pass'] for r in failures),
        'failed_completion_token_min': min(r['completion_tokens'] for r in failures),
        'failed_completion_token_max': max(r['completion_tokens'] for r in failures),
        'failure_numeric_proposals_all_NA': all(r['failed_numeric_proposals_remain_NA'] for r in failures),
        'request_index_min': min(r['request_index'] for r in rows), 'request_index_max': max(r['request_index'] for r in rows),
        'package_requests_before': len(started), 'package_requests_after': len(started), 'new_requests': 0,
        'expert_returns': expert_returns, 'faithful_corrections': completion['faithful_corrections'], 'numeric_CCE': completion['numeric_CCE'],
        'holdout_repaired_or_retried': False, 'holdout_fields_or_scores_disclosed': False,
        'original_configuration_changed': False, 'original_expert_form_unchanged': True,
        'scientific_faithfulness_or_rubric_correctness_tested': False,
        'scope': 'Technical structural attribution only; no source independence or scientific-validity claim.'}
    anchors = [source_anchor(ROOT / 'evaluator_integrity.py', 'def parse_judge_object(text):'),
        source_anchor(ROOT / 'evaluator_integrity.py', 'def validate_legacy_extraction(extraction):'),
        source_anchor(ROOT / 'evaluator_integrity.py', 'def validate_score_proposals(scores):'),
        source_anchor(ROOT / 'models/Ollama_LLM.py', '            parse_judge_object(content)'),
        source_anchor(loader, 'async def get_model_response('),
        source_anchor(loader, '        scores_block = llm_output.get("scores", {})'),
        source_anchor(ROOT / 'prompts/eval_oeq_teacher_rubric.txt', '  "C_step": {'),
        source_anchor(ROOT / 'prompts/eval_oeq_teacher_rubric.txt', '  "Co_order": {'),
        source_anchor(ROOT / 'prompts/eval_oeq_teacher_rubric.txt', '      "c_step": {'),
        source_anchor(ROOT / 'prompts/eval_oeq_teacher_rubric.txt', '      "co_chem": {'),
        source_anchor(ROOT / 'prompts/eval_oeq_teacher_rubric.txt', '  "extraction": {')]
    verification = {'status': 'pass', 'checked_trials': 15, 'checked_receipts': 15,
        'checked_failure_original_gates': 8, 'protected_file_count': len(protected),
        'protected_files_unchanged': True, 'ledger_sha256_before': ledger_before,
        'ledger_sha256_after': sha(LEDGER), 'contract_sha256': CONTRACT,
        'network_guard': 'socket connect/create_connection disabled; no model transport imported',
        'validation_slice_sha256': rawsha(validation_slice), 'validation_slice_start_line': loader_text[:begin].count('\n') + 1,
        'source_anchors': anchors, 'inputs': inputs,
        'protected_input_hashes': [{'path': p, 'sha256': h} for p, h in sorted(protected.items())],
        'audit_script': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}}
    save('per_trial_metadata.json', rows)
    save('per_failure_metadata.json', failures)
    save('summary.json', summary)
    save('verification.json', verification)
    nested_upper = [r for r in failures if 'C_step' in r.get('schema_types', {}).get('score_groups', {}).get('completeness', {}).get('field_types', {})]
    save('contract_findings.json', {
        'source_anchors': anchors,
        'established_source_facts': [
            'Section-specific rubric JSON examples use uppercase C_step/C_param and Co_* keys at the example root.',
            'The final complete rubric JSON example uses lowercase keys inside scores.completeness and scores.correctness, with a required extraction object.',
            'The existing loader accepts a legacy uppercase top-level fallback only when scores is absent/falsy; it does not map uppercase keys inside existing nested groups.',
            'The provider adapter applies the same strict parser before returning content to the grading runner; duplicate keys can therefore be labelled TEACHER_GENERATION/PROVIDER_EXCEPTION despite a completed local provider return.'
        ],
        'observed_nested_uppercase_failed_cases': len(nested_upper),
        'observed_nested_uppercase_first_gate_cases': sum(r['classification'] == 'missing_score_record' for r in nested_upper),
        'other_nested_uppercase_cases_first_fail_extraction': sum(r['classification'] == 'missing_extraction_fields' for r in nested_upper),
        'causal_claim': 'Multiple serialization examples and asymmetric fallback are verified code/prompt facts. Their causal contribution to model output is a hypothesis, not an isolated experiment.',
        'not_established': ['Scientific extraction faithfulness', 'Rubric score correctness', 'Absence of later validation errors after the first rejected gate', 'Network-wide availability'],
        'development_only_followup_not_executed': {
            'inputs': 'Use only the already fixed A01-A05 development set; never select cases using holdout outputs.',
            'first_action': 'Independently test canonical nested, legacy top-level, mixed-case nested, missing-extraction and duplicate-key structural fixtures against the unchanged loader.',
            'optional_separate_model_batch': 'Pre-freeze a new configuration on all five development inputs if needed: one consistent output schema, unchanged rubric definitions, demand, EGES formulas, original full answers and original loader. Preserve the prior configuration as baseline.',
            'endpoints': ['Complete required object and field presence', 'Exact structural casing', 'Duplicate-key rejection', 'Technical validity separately from factual faithfulness'],
            'no_holdout_action': 'No alias mapping, correction, retry, rescore, case replacement or parameter selection on the 15 holdout inputs.',
            'calls_in_this_audit': 0,
            'model_followup_started': False,
        }})
    columns = ['answer_id', 'trial_id', 'request_id', 'request_index', 'status', 'recorded_failure_stage',
        'recorded_error_type', 'classification', 'provider_done', 'finish_reason', 'prompt_tokens',
        'completion_tokens', 'response_characters', 'response_utf8_bytes', 'standard_JSON_syntax_complete',
        'strict_parse_pass', 'original_validation_pass', 'identity_and_receipt_bound']
    with (OUT / 'per_trial_metadata.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    save('run.json', {'status': 'completed', 'started_at_utc': started_at,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'cwd': str(ROOT),
        'argv': [sys.executable, 'scripts/cce_audit_holdout_failures_v1.py'],
        'script_sha256': sha(__file__), 'new_requests': 0, 'package_requests': len(started),
        'summary_sha256': sha(OUT / 'summary.json'), 'verification_sha256': sha(OUT / 'verification.json')})
    (OUT / 'commands.md').write_text('''# Actual offline command\n\nExecuted from `C:\\ClearEval\\ClearEval-public` and returned exit code 0:\n\n```powershell\n& 'C:\\ClearEval\\review_artifacts\\bioprobench_2026-09-29\\python_portable\\python.exe' scripts/cce_audit_holdout_failures_v1.py\n```\n\n[run.json](run.json) records the actual invocation, script hash and output hashes. Network connections are disabled in this script. No model transport is imported, no output is repaired, and no trial is rescored. The package ledger remains at 104; the 15 original holdout requests were indices 90–104.\n''', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
