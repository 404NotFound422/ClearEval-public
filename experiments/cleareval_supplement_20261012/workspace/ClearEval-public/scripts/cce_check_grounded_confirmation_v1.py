"""Synthetic-only software checks for the unfrozen primary confirmation draft."""
from __future__ import annotations
import asyncio
import ast
import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_grounded_confirmation_v1 as c


def main():
    results = []
    def check(name, value):
        if not value: raise AssertionError(name)
        results.append({'check': name, 'pass': True})
    def rejected(name, fn):
        try: fn()
        except (ValueError, AssertionError, FileNotFoundError, RuntimeError): check(name, True)
        else: raise AssertionError('Expected rejection: ' + name)
    c.DESIGN.mkdir(parents=True, exist_ok=True)
    def no_network(*args, **kwargs): raise AssertionError('SYNTHETIC_CHECK_NETWORK_FORBIDDEN')
    # Windows asyncio itself creates a local socketpair. Block provider HTTP and
    # metadata entry points, while permitting that event-loop implementation.
    with patch.object(socket, 'create_connection', no_network), patch.object(urllib.request.OpenerDirector, 'open', no_network), \
         patch.object(c.j, 'model_configs', side_effect=no_network), \
         tempfile.TemporaryDirectory(prefix='synthetic_primary_', dir=c.DESIGN) as tmp:
        tmp = Path(tmp)
        # Public constructor schema; these strings are synthetic and not sealed inputs.
        source = {'confirmation_id': 'C01', 'question_id': 2, 'specific_question': 'Synthetic software question.',
            'model_response': 'Chosen Method: FDISCO\r\n1. Store the inert demonstration object.\r\n',
            'source_kind': 'archived_generated_answer', 'expert_confirmation': None, 'formal_eligible': False}
        source.update(question_sha256=c.rawsha(source['specific_question']), answer_sha256=c.rawsha(source['model_response']))
        case = c.clean_source({'anonymous_answer_id': 'C01'}, source)
        check('source_exact_UTF8_CRLF_preserved', case['model_response'] == source['model_response'])
        check('source_external_caseID_only', case['case_id'] == 'C01' and 'generator_model' not in case)
        rejected('reject_extra_identity_metadata', lambda: c.clean_source({'anonymous_answer_id': 'C01'}, {**source, 'generator_model': 'hidden'}))
        rejected('reject_wrong_raw_hash', lambda: c.clean_source({'anonymous_answer_id': 'C01'}, {**source, 'answer_sha256': '0'*64}))
        rejected('reject_unexposed_qid', lambda: c.clean_source({'anonymous_answer_id': 'C01'}, {**source, 'question_id': 999}))
        rejected('reject_boolean_qid', lambda: c.clean_source({'anonymous_answer_id': 'C01'}, {**source, 'question_id': True}))
        rejected('reject_wrong_anonymous_identity', lambda: c.clean_source({'anonymous_answer_id': 'C02'}, source))
        check('forbidden_metadata_paths_include_all_protected_classes', all(c.forbidden_metadata_path(x) for x in ['x/sealed_confirmation/C01.json', 'x/confirmation_manifest.json', 'x/identity_key.json', 'x/human_review/cases.json']))
        with patch.object(c, 'RELEASE', tmp/'absent_release.json'):
            rejected('missing_release_fails_before_any_source_read', c.release_gate)
        ref = {'reference_id': 'R1', 'steps': [{'step_id': 's1', 'text': 'Synthetic inert action.', 'required_scope': {'unknown': None}}],
            'version_id': 'v1', 'initial_state': None, 'prerequisites': ['Unknown synthetic precondition'],
            'task_scope_bindings': [{'question_id': 2, 'formal_eligible': False}], 'future_scientific_field': {'value': 0},
            'target_answer_bindings': [{'model_name': 'hidden-construction-only'}], 'source_path': 'C:/synthetic/source.txt'}
        projected, audit = c.projection.project_reference(ref)
        check('projection_exact_roundtrip', c.projection.restore_reference(projected, audit) == ref)
        check('projection_retains_unknown_new_scientific_fields', projected['future_scientific_field'] == {'value': 0} and projected['initial_state'] is None)
        check('projection_preserves_version_prerequisites_taskscope', all(projected[k] == ref[k] for k in ['version_id', 'prerequisites', 'task_scope_bindings']))
        check('construction_identity_only_in_external_sidecar', 'target_answer_bindings' not in projected and audit['moved_provenance'])
        refs = [{**ref, 'reference_id': 'R1', 'comparison_method_id': 'FDISCO', 'question_ids': [2], 'protocol_version': 'AUTHOR_v1', 'version_aliases': ['AUTHOR_v1']},
                {**ref, 'reference_id': 'R2', 'version_id': 'v2', 'comparison_method_id': 'FDISCO', 'question_ids': [2], 'protocol_version': 'AUTHOR_v2', 'version_aliases': ['AUTHOR_v2']}]
        byid = {r['reference_id']: c.projection.project_reference(r)[0] for r in refs}
        pool, selection = c.pool_for(case, refs, byid)
        check('generic_method_keeps_all_same_method_versions', [r['reference_id'] for r in pool] == ['R1', 'R2'])
        check('pool_objects_equal_frozen_projection', pool == list(byid.values()))
        exact = {**case, 'model_response': 'Chosen Method: FDISCO AUTHOR_v2\nSynthetic.'}
        check('explicit_version_constrains_pool', [r['reference_id'] for r in c.pool_for(exact, refs, byid)[0]] == ['R2'])
        check('unknown_method_pool_remains_empty', c.pool_for({**case, 'model_response': 'Chosen Method: UNKNOWN_ROUTE\nSynthetic.'}, refs, byid)[0] == [])
        check('wrong_qid_no_cross_task_fallback', c.pool_for({**case, 'question_id': 21}, refs, byid)[0] == [])
        public = {'transport_kind': 'ollama_loopback', 'model': 'SYNTHETIC_MODEL', 'host': 'http://127.0.0.1:11434',
            'model_digest': 'synthetic', 'max_output_tokens': 8192, 'num_ctx': 98304, 'temperature': 0,
            'enable_thinking': False, 'format': {'type': 'object'}, 'timeout_seconds': 600}
        boundary = 'x'*(98304-8192-256)
        check('context_exact_bound_fits', c.context_check(boundary, public)['fits'])
        check('context_one_byte_over_rejects_not_truncates', not c.context_check(boundary+'x', public)['fits'])
        check('context_utf8_counts_bytes', c.context_check('\u4e2d', public)['prompt_utf8_bytes'] == 3)
        failed = c.numeric.derive({}, {'sr': .25, 'sp': 0}, False)
        check('failed_judge_retains_known_steps_including_zero', failed['sr'] == .25 and failed['sp'] == 0)
        check('failed_judge_dependents_are_NA', all(failed[k] is None for k in c.numeric.METRICS if k not in ['sr', 'sp']))
        partial = c.numeric.derive({'c_param': 3, 'co_order': 3, 'co_method': 2, 'co_param': 2, 'co_chem': 1,
            's_method': 2.5, 's_label': None, 's_trans': 3, 's_time': 3}, {'sr': 1, 'sp': 1}, True)
        check('NA_dependency_preserves_independent_Com_Cor', partial['Com'] == 1 and partial['Cor'] == 1 and partial['Eff'] is None and partial['IA'] is None)
        check('sixteen_metrics_are_named_not_sample_count', len(c.numeric.METRICS) == 16 and len(set(c.numeric.METRICS)) == 16)
        # Exercise the actual summary expressions with unequal answers per qid.
        # The hand-calculated answer mean must not become a qid macro-average.
        source_tree = ast.parse(Path(c.__file__).read_text(encoding='utf8'))
        summary_fn = next(node for node in source_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'analyze')
        selected = [node for node in summary_fn.body if isinstance(node, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id in ['common', 'means', 'common_qid_counts'] for t in node.targets)]
        synthetic_cases = {aid: {'question_id': 2 if index < 2 else 21} for index, aid in enumerate(c.IDS)}
        synthetic_observations = []
        for judge in ['J1', 'J2']:
            for index, aid in enumerate(c.IDS):
                value = ([.2, .4, .9] if judge == 'J1' else [.4, .6, .8])[index] if index < 3 else 1
                synthetic_observations.append({'anonymous_answer_id': aid, 'judge': judge,
                    'complete_numeric_CCE': index < 3 or (index == 3 and judge == 'J1'),
                    'metrics': {metric: value for metric in ['Com', 'Cor', 'Eff', 'IA', 'HV']}})
        context = {'IDS': c.IDS, 'cases': synthetic_cases, 'judges': ['J1', 'J2'], 'observations': synthetic_observations}
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), '<actual_summary_expressions>', 'exec'), context)
        check('common_denominator_is_paired_anonymous_answers', context['common'] == ['C01', 'C02', 'C03'])
        check('summary_is_per_answer_not_qid_macro_average', all(abs(context['means']['J1'][key] - .5) < 1e-12 and
              abs(context['means']['J2'][key] - .6) < 1e-12 for key in ['Com', 'Cor', 'Eff', 'IA', 'HV']))
        check('common_qid_distribution_counts_answers_once_not_judges', context['common_qid_counts'] == {'2': 2, '21': 1})
        previous_tree = ast.parse((c.DESIGN/'revision_02_summary_snapshot/cce_grounded_confirmation_v1.py').read_text(encoding='utf8'))
        previous_fn = next(node for node in previous_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'analyze')
        def original_assignments(fn):
            return [ast.dump(node) for node in fn.body if isinstance(node, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id in ['common', 'means'] for t in node.targets)]
        check('common_set_and_all_CCE_mean_formulas_unchanged', original_assignments(summary_fn) == original_assignments(previous_fn))
        with patch.object(c, 'request_count', return_value=268):
            c.budget_guard(268, 0, 16); check('budget_boundary_reserves_primary16_plus_blind16', True)
        with patch.object(c, 'request_count', return_value=269):
            rejected('budget_rejects_combined_301', lambda: c.budget_guard(269, 0, 16))
        with patch.object(c, 'request_count', return_value=269):
            rejected('budget_detects_unplanned_parallel_request', lambda: c.budget_guard(268, 0, 15))
        frozen_contract = {'files': {'core.py': 'stable'}, 'demands': {'version': 'fixed'},
            'source_registry_sha256': 'registry-v1', 'scoring_version': 'original-v1'}
        c.require_scientific_contract(copy.deepcopy(frozen_contract), frozen_contract)
        check('all_four_scientific_contract_fields_equal_pass', True)
        for field in frozen_contract:
            changed = copy.deepcopy(frozen_contract); changed[field] = 'DRIFT'
            rejected('scientific_contract_rejects_' + field + '_drift',
                lambda changed=changed: c.require_scientific_contract(changed, frozen_contract))
        with patch.object(c, 'public_models', return_value=[{'name': 'SYNTHETIC_JUDGE_1'}, {'name': 'SYNTHETIC_JUDGE_2'}]), \
             patch.object(c, 'LEDGER', tmp/'boundary_private_ledger.jsonl'):
            actual_args = c.arguments({'model_config': tmp/'unused_synthetic_config.json'})
            check('budget_future_reserve_not_counted_as_actual_external_requests',
                  actual_args.external_request_count == 0 and actual_args.total_budget == 284)
            first = c.j.reserve_request(actual_args, 'SYNTHETIC_FIRST', 1, 'SYNTHETIC_JUDGE_1')
            check('first_actual_private_request_index_is_1_not_17', first['package_request_index'] == 1)
            with c.LEDGER.open('w', encoding='utf8') as stream:
                for i in range(283): stream.write(c.j.canonical({'event': 'request_started', 'request_id': 'prior_'+str(i)})+'\n')
            last = c.j.reserve_request(actual_args, 'SYNTHETIC_LAST_PRIMARY', 1, 'SYNTHETIC_JUDGE_1')
            check('primary_capacity_last_actual_index_284', last['package_request_index'] == 284)
            rejected('primary_capacity_stops_before_using_blind16_reserve',
                lambda: c.j.reserve_request(actual_args, 'SYNTHETIC_FORBIDDEN_285', 1, 'SYNTHETIC_JUDGE_1'))
        check('primary_projection_uses_versioned_revision_02', c.REFERENCE_REVISION.name == 'revision_02')
        check('integrity_amendment_is_required_release_asset', 'reference_integrity_amendment' in c.ASSETS)
        p = tmp/'immutable.json'; c.save_once(p, {'a': 1}); c.save_once(p, {'a': 1})
        rejected('write_once_rejects_postfreeze_change', lambda: c.save_once(p, {'a': 2}))

        # True asyncio.run execution, real original Ollama serialization, synthetic
        # provider only. No real service, original ledger, encoder or source input.
        real_adapter = c.j.make_adapter
        scores = {'synthetic_direct': 1}
        expected_raw = json.dumps({'scores': scores, 'synthetic': 'line\r\nend'}, ensure_ascii=False)
        class Ground:
            VERSION = 'SYNTHETIC_ONLY'
            rawsha = staticmethod(c.rawsha)
            @staticmethod
            def source_id_for_case(x): return 'SRC_' + c.rawsha(x['specific_question']+'\0'+x['model_response'])[:24]
            @staticmethod
            def make_prompt(*args): raise AssertionError('ASYNC_PROMPT_REBUILD_FORBIDDEN')
            @staticmethod
            def convert(raw, doc):
                value = json.loads(raw)
                if value.get('bad_span'): raise ValueError('SYNTHETIC_SPAN_REJECTED')
                payload = {'scores': value['scores'], 'extraction': {'synthetic': True}}
                return {'raw_response_sha256': c.rawsha(raw), 'legacy_runner_payload': payload,
                    'legacy_runner_content': json.dumps(payload), 'legacy_projection': {'extraction': payload['extraction']}}
        class Runner:
            MODEL_SPACE_SIGNED = {}; _log_teacher_response = staticmethod(lambda *args, **kwargs: None)
            async def evaluate_response_with_teacher(self, teacher, *args):
                try:
                    value = await teacher._acall('ORIGINAL_RUBRIC_CAPTURED_EARLIER')
                    return {'technical_status': 'VALID', 'extraction': json.loads(value['content'])['extraction']}
                except Exception as exc:
                    return {'technical_status': 'FAILED', '_error': str(exc)}
        backend = SimpleNamespace(grounded=Ground)
        provider = {'raw': expected_raw, 'raise_transport': False, 'drift': False}
        actual_payloads = []
        def fake_adapter(settings, api_type):
            api = real_adapter(settings, None)
            def response(**kwargs):
                actual_payloads.append(copy.deepcopy(kwargs))
                if provider['raise_transport']: raise RuntimeError('SYNTHETIC_TRANSPORT_FAILURE')
                obj = {'done': True, 'done_reason': 'stop', 'response': provider['raw'], 'model': 'SYNTHETIC_MODEL', 'eval_count': 1}
                api.last_response = obj
                return obj
            # The real serializer remains; only the eventual provider is a stub.
            api.client.client.generate = response
            if provider['drift']:
                original_call = api._acall
                async def drift_call(prompt): return await original_call(prompt + 'DRIFT')
                api._acall = drift_call
            return api
        with patch.object(c, 'OUT', tmp/'primary'), patch.object(c, 'RUN', tmp/'primary/run'), \
             patch.object(c, 'LEDGER', tmp/'private_ledger.jsonl'), \
             patch.object(c, 'arguments', return_value=SimpleNamespace(ledger=tmp/'private_ledger.jsonl', total_budget=284, external_request_count=0)), \
             patch.object(c.j, 'make_adapter', side_effect=fake_adapter):
            case['references'] = []; doc = {'source_id': Ground.source_id_for_case(case), 'text': case['model_response'], 'answer_sha256': c.rawsha(case['model_response'])}
            c.j.save(c.OUT/'source_documents/C01.json', doc)
            pp = c.OUT/'prompts/C01.txt'; pp.parent.mkdir(parents=True, exist_ok=True)
            prompt = 'SYNTHETIC_PROMPT\nFull inert source supplied here.\n'
            pp.write_text(prompt, encoding='utf8', newline='')
            def make_cell(index):
                cell = {'planned_trial_id': 'synthetic_'+str(index), 'judge': 'SYNTHETIC_JUDGE',
                    'identity': {'cell': index}, 'prompt_raw_sha256': c.rawsha(prompt)}
                c.j.save(c.OUT/'expected_http_payloads'/f"{cell['planned_trial_id']}.json", c.expected_payload(public, prompt))
                return cell
            cell = make_cell(1)
            success = asyncio.run(c.execute_cell(cell, case, public, backend, Runner(), None, {}))
            check('real_async_loop_success_no_nested_asyncio_run', success['status'] == 'success')
            check('actual_HTTP_payload_and_full_schema_captured', actual_payloads[-1]['format'] == public['format'] and actual_payloads[-1]['options']['num_ctx'] == 98304)
            d = c.RUN/'attempts/synthetic_1_1'
            check('raw_provider_text_exact_bytes', (d/'raw_source_bound_content.txt').read_bytes().decode('utf8') == expected_raw)
            check('raw_and_projection_separate', (d/'projected_legacy_payload.json').exists() and success['raw_return_modified'] is False)
            check('success_real_receipt_bound_private_ledger', c.j.read(d/'request_receipt.json') == c.j.ledger_rows(c.LEDGER)[0])
            provider['raw'] = json.dumps({'scores': scores, 'bad_span': True})
            failure = asyncio.run(c.execute_cell(make_cell(2), case, public, backend, Runner(), None, {}))
            check('conversion_rejection_is_failed_without_JSON_fallback', failure['status'] == 'failed' and failure['legacy_parser_fallback_used'] is False)
            check('conversion_rejection_preserves_raw_and_no_projection', (c.RUN/'attempts/synthetic_2_1/raw_source_bound_content.txt').exists() and not (c.RUN/'attempts/synthetic_2_1/projected_legacy_payload.json').exists())
            provider['raw'] = expected_raw; provider['raise_transport'] = True
            transport = asyncio.run(c.execute_cell(make_cell(3), case, public, backend, Runner(), None, {}))
            check('transport_failure_retained_as_actual_request', transport['status'] == 'failed' and transport['actual_api_request_made'])
            provider['raise_transport'] = False
            before = len(c.j.ledger_rows(c.LEDGER))
            overflow = asyncio.run(c.execute_cell(make_cell(4), case, {**public, 'num_ctx': 1}, backend, Runner(), None, {}))
            check('context_overflow_terminal_zero_request', overflow['status'] == 'failed' and not overflow['actual_api_request_made'] and overflow['local_failure_reason'])
            check('context_overflow_does_not_reserve_budget', len(c.j.ledger_rows(c.LEDGER)) == before)
            provider['drift'] = True
            drift = asyncio.run(c.execute_cell(make_cell(5), case, public, backend, Runner(), None, {}))
            check('payload_drift_fails_before_provider_dispatch', drift['status'] == 'failed' and not drift['actual_api_request_made'])
            check('pre_dispatch_reservation_conservatively_counted_not_called_actual', drift['budget_reservation_made'] and not (c.RUN/'attempts/synthetic_5_1/request_receipt.json').exists())
            check('five_synthetic_cells_preserved_including_failures', len(list((c.RUN/'trials').glob('*.json'))) == 5)
            check('no_attempt2_created', all(p.name.endswith('_1') for p in (c.RUN/'attempts').iterdir()))
    result = {'status': 'pass', 'scope': 'synthetic_software_only_not_pre_generation_authorization',
        'checks': results, 'check_count': len(results), 'actual_asyncio_run_fixture': True,
        'real_serializer_with_synthetic_provider': True, 'new_model_requests': 0, 'new_embeddings': 0,
        'actual_ledger_accessed': False, 'sealed_or_human_inputs_read': False,
        'prior_fixture_attempt': 'The first harness denied Windows asyncio internal socketpair creation before any cell ran; narrowed the guard to HTTP/metadata plus create_connection. No experiment request or sealed read occurred.',
        'revision_fixture_initial_attempt': 'The new capacity-boundary correctly raised RuntimeError at request285; added that expected exception class to the rejection-check helper. This used only a private synthetic ledger.',
        'script': c.bind(__file__), 'runner': c.bind(c.__file__), 'actual_argv': [sys.executable, *sys.argv]}
    c.j.save(c.DESIGN/'software_checks.json', result)
    print(c.j.canonical({k: v for k, v in result.items() if k != 'checks'}))


if __name__ == '__main__': main()
