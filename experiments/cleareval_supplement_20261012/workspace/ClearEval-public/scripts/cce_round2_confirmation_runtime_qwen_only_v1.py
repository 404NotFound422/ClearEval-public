"""Unfrozen round-two confirmation runtime; all source access requires root release.

Eight fixed answers x one Qwen judge; the second evaluator remains pending, one attempt; no selection or approval writer.
Partial bounds are deliberately absent: the original scoring adapter retains NA.
Only draft/private software checks are authorized while this file is developed.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_confirmation_qwen_only_v1 as gate
import cce_grounded_offline_scoring_v1 as scoring
j = gate.j
budget = gate.budget
require = gate.require
bind = gate.bind
GATE_SHA256 = '81dfded9b50cee1c106621f49564568c54dca154d1643e2722c5d8857074ea32'
VERSION = 'round2-confirmation-qwen-only-runtime-v1'


def import_path(path):
    p = Path(path).resolve(); name = '_confirmation_bound_' + j.filehash(p)[:20]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, p)
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def load_runtime(paths):
    require(j.filehash(gate.__file__) == GATE_SHA256, 'RELEASE_CONTROLLER_CHANGED')
    backend = import_path(paths['development_backend']); followup = import_path(paths['followup_backend'])
    require(Path(backend.grounded.__file__).resolve() == paths['converter']
            and Path(followup.base.__file__).resolve() == paths['development_backend']
            and Path(followup.grounded.__file__).resolve() == paths['converter']
            and Path(backend.scoring.__file__).resolve() == paths['numeric_adapter']
            and paths['numeric_adapter'] == Path(scoring.__file__).resolve(), 'BOUND_BACKEND_IMPLEMENTATION_MISMATCH')
    return backend, followup


def read_source_preparation(out):
    plan = j.read(out / 'source_release_plan.json'); preparation = j.read(out / 'source_preparation.json')
    require(plan['status'] == 'frozen_before_confirmation_metadata_unsealing'
            and plan['planned_answers'] == 8 and plan['planned_observations'] == 8 and plan['max_attempts'] == 1,
            'AUTHORIZED_EIGHT_SOURCE_PLAN_REQUIRED')
    gate.verify(plan['root_release']); gate.verify_bindings(plan['frozen_inputs'])
    require(preparation['status'] == 'eight_sources_exported_not_generated_runtime_not_implemented'
            and preparation['actual_source_count'] == 8 and preparation['answer_replacements'] == 0,
            'SOURCE_EXPORT_NOT_COMPLETE')
    gate.verify_bindings(preparation['bindings'], [out / 'source_release_plan.json', out / 'unsealing_receipt.json',
        out / 'cases.json', out / 'reference_selections.json', out / 'source_access_receipt.json',
        out / 'audit_identity/source_identity_manifest.json'])
    cases = j.read(out / 'cases.json')['cases']
    require([c['anonymous_answer_id'] for c in cases] == gate.IDS and len({c['answer_sha256'] for c in cases}) == 8,
            'FIXED_EIGHT_SOURCE_IDENTITIES_REQUIRED')
    for c in cases:
        require(c['case_id'] == c['anonymous_answer_id'] and c['question_id'] in gate.family.QIDS
                and gate.rawsha(c['model_response']) == c['answer_sha256']
                and gate.rawsha(c['specific_question']) == c['question_sha256'], 'SOURCE_FULL_TEXT_IDENTITY_CHANGED')
    return plan, preparation, cases


class LocalEncoder(gate.family.core.Encoder):
    def __init__(self, out):
        original = gate.family.core.OUT; gate.family.core.OUT = out
        try:
            super().__init__()
        finally:
            gate.family.core.OUT = original
        self.memo = {}; self.used = []; self.new = []
        self.roots = [*gate.family.CACHES, gate.family.DEST / 'embedding_cache', self.cache]

    def encode(self, texts):
        result = []
        for text in texts:
            key = gate.family.core.digest([self.identity, text]) + '.npy'
            if key not in self.memo:
                found = [p / key for p in self.roots if (p / key).exists()]
                if found:
                    path = found[0]
                    require(all(j.filehash(p) == j.filehash(path) for p in found), 'CONFLICTING_CACHED_VECTOR')
                    vector = self.np.load(path, allow_pickle=False); origin = 'reused'
                else:
                    path = self.cache / key
                    vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
                    self.np.save(path, vector); self.new.append(str(path)); origin = 'new_local_vector'
                require(vector.shape == (768,) and self.np.isfinite(vector).all(), 'INVALID_LOCAL_VECTOR')
                self.memo[key] = vector
                self.used.append({**bind(path), 'text_sha256': gate.rawsha(text), 'origin': origin})
            result.append(self.memo[key])
        return self.np.asarray(result)


def deterministic_steps(out, cases, refs, paths):
    encoder = None; init_error = None; full = []; exports = {}
    step_config = {'threshold': .7, 'encoder': 'all-mpnet-base-v2',
        'bindings': [bind(paths[k]) for k in ['reference_catalog', 'reference_projection', 'method_family_policy',
            'step_core', 'step_scorer', 'encoder_manifest', 'reference_policy']], 'formula': 'unchanged original SR and SP'}
    for c in cases:
        _, _, version, pool = gate.family.resolve(c, refs)
        try:
            if pool and encoder is None and init_error is None:
                try:
                    encoder = LocalEncoder(out)
                except Exception as exc:
                    init_error = type(exc).__name__ + ':' + str(exc)
            if pool:
                require(encoder is not None, 'LOCAL_ENCODER_UNAVAILABLE:' + str(init_error))
            # No compatible pool returns NA before an encoder is needed.
            result = gate.family.score(c, refs, encoder, .7)
        except Exception as exc:
            result = {'sr': None, 'sp': None, 'reference_id': None, 'all_candidates': [],
                'missing_reason': 'local_step_failure:' + type(exc).__name__ + ':' + str(exc)}
        require(all(result[k] is None or scoring.finite(result[k]) and 0 <= result[k] <= 1 for k in ['sr', 'sp']),
                'ORIGINAL_STEP_SCORE_RANGE')
        full.append({'anonymous_answer_id': c['anonymous_answer_id'], **result})
        exports[c['case_id']] = {'sr': result['sr'], 'sp': result['sp'], 'question_id': c['question_id'],
            'answer_sha256': c['answer_sha256'], 'question_sha256': c['question_sha256'],
            'references_sha256': j.digest(c['references']), 'reference_id': result.get('reference_id'),
            'candidate_reference_ids': [r['reference_id'] for r in pool], 'missing_reason': result.get('missing_reason'),
            'threshold': .7, 'encoder': encoder.identity if encoder else {'model': 'all-mpnet-base-v2', 'not_loaded': True},
            'step_config_sha256': j.digest(step_config), 'source': 'original_deterministic_step_scoring',
            'formal_eligible': False}
    usage = {'new_embeddings': len(encoder.new) if encoder else 0,
        'reused_embeddings': sum(x['origin'] == 'reused' for x in encoder.used) if encoder else 0,
        'used': encoder.used if encoder else [], 'encoder_failure': init_error, 'new_judge_requests': 0}
    for name, value in [('full_step_results.json', full), ('step_inputs.json', exports), ('step_configuration.json', step_config),
                        ('embedding_usage.json', usage)]:
        gate.save_once(out / name, value)
    gate.save_once(out / 'step_verification.json', {'status': 'pass', 'primary_threshold': .7,
        'original_SR_SP': True, 'fixed_answers': 8, 'unknown_not_imputed': True,
        'numeric_steps': sum(scoring.finite(s['sr']) for s in exports.values()),
        'bindings': [bind(out / name) for name in ['cases.json', 'full_step_results.json', 'step_inputs.json',
            'step_configuration.json', 'embedding_usage.json']] + step_config['bindings'], **usage})
    return exports


def prepare(args):
    out = args.out
    require(not (out / 'plan.json').exists() and not (out / 'run').exists(), 'NO_RUNTIME_OVERWRITE_OR_PARTIAL_UNFROZEN_RUN')
    release, paths, final, _, refs, _ = gate.release_gate(args.release)
    gate.verify_bindings(final['bindings'], [Path(__file__)])
    source_plan, _, cases = read_source_preparation(out)
    require(source_plan['root_release'] == bind(args.release), 'SOURCE_AND_RUNTIME_RELEASE_DIFFER')
    backend, followup = load_runtime(paths)
    require(backend.grounded.VERSION == final['candidate_version'], 'SELECTED_CANDIDATE_VERSION')
    actual, models = followup.model_contracts(paths['model_config'], 'E2')
    expected = j.read(paths['E4_contract'])
    require(actual == expected, 'FINAL_E4_FULL_MODEL_SCIENCE_CONTRACT_CHANGED')
    budget.guard('confirmation', 8, 600)
    steps = deterministic_steps(out, cases, refs, paths)
    gate.save_once(out / 'expected_contract.json', expected)
    (out / 'model_config.json').write_bytes(paths['model_config'].read_bytes())
    _, _, _, registry = backend.readonly_runtime()
    matrix = []; generated = []
    for c in cases:
        aid = c['anonymous_answer_id']; source_assets = {}; local_error = None
        try:
            registry.get(c['question_id'], c['specific_question'])
            doc = backend.grounded.document(c['model_response'], backend.grounded.source_id_for_case(c))
            require(doc['text'] == c['model_response'] and ''.join(u['text'] for u in doc['units']) == c['model_response'],
                    'SOURCE_DOCUMENT_NOT_LOSSLESS')
            schema = backend.grounded.schema_for_document(doc); prompt = backend.grounded.make_prompt(c, doc)
            docp = out / 'source_documents' / (aid + '.json'); sp = out / 'schemas' / (aid + '.json'); pp = out / 'prompts' / (aid + '.txt')
            gate.save_once(docp, doc); gate.save_once(sp, schema)
            pp.parent.mkdir(parents=True, exist_ok=True); pp.write_bytes(prompt.encode('utf8'))
            source_assets = {'source_document': bind(docp), 'schema': bind(sp), 'prompt': bind(pp)}
            generated += [docp, sp, pp]
        except Exception as exc:
            local_error = {'stage': 'LOCAL_SOURCE_PREPARATION', 'type': type(exc).__name__, 'reason': str(exc),
                           'actual_request_made': False, 'source_text_unchanged': True}
        for model in models:
            public = model['public']; name = model['name']; assets = dict(source_assets); error = local_error
            payload = None; bound = None
            if not error:
                payload = backend.payload_for(prompt, schema, public)
                p = out / 'request_payloads' / (aid + '__' + name + '.json'); gate.save_once(p, payload)
                assets['payload'] = bind(p); generated.append(p)
                bound = len(prompt.encode('utf8')) + public['max_output_tokens'] + 256
                if bound > public['num_ctx']:
                    error = {'stage': 'LOCAL_CONTEXT_LIMIT', 'reason': 'SOURCE_AND_REFERENCE_NOT_TRUNCATED',
                             'actual_request_made': False, 'conservative_context_bound': bound}
            identity = {'case_id': c['case_id'], 'input_sha256': j.digest({'question': c['specific_question'],
                'question_id': c['question_id'], 'protocol': c['model_response'], 'references': c['references']}),
                'judge': name, 'repeat_index': 0, 'contract_sha256': j.digest(expected[name]),
                'payload_sha256': j.digest(payload) if payload is not None else None,
                'phase': 'confirmation', 'round_id': budget.ROUND}
            matrix.append({'anonymous_answer_id': aid, 'case_id': c['case_id'], 'question_id': c['question_id'],
                'judge': name, 'repeat_index': 0, 'attempt': 1, 'identity': identity, 'planned_trial_id': j.digest(identity),
                'reuse': None, 'step': steps[c['case_id']], 'assets': assets,
                'conservative_context_bound': bound, 'local_pre_request_failure': error})
    gate.save_once(out / 'matrix.json', matrix)
    deps = [Path(__file__), Path(gate.__file__), args.release, out / 'source_preparation.json', out / 'cases.json',
        out / 'reference_selections.json', out / 'source_release_plan.json', out / 'expected_contract.json', out / 'model_config.json',
        out / 'matrix.json', out / 'step_inputs.json', out / 'step_verification.json', *generated]
    deps += [Path(b['path']) for b in j.read(out / 'source_preparation.json')['bindings']]
    deps += list(paths.values())
    deps += [Path(b['path']) for b in j.read(out / 'step_verification.json')['bindings']]
    deps += [Path(b['path']) for b in j.read(out / 'embedding_usage.json')['used']]
    plan = {'status': 'frozen_before_generation', 'version': VERSION, 'phase': 'confirmation',
        'candidate_version': final['candidate_version'], 'root_release': bind(args.release),
        'planned_answers': 8, 'planned_observations': 8, 'planned_new_requests_upper_bound': 8,
        'planned_reused_observations': 0, 'max_attempts': 1, 'repeats': 1, 'models': gate.MODELS,
        'scope': gate.SCOPE, 'no_post_confirmation_tuning': True, 'all_statuses_retained': True,
        'second_evaluator_pending': True, 'cross_judge_goal_complete': False,
        'starting_counts': {k: v for k, v in budget.counts().items() if k != 'requests'},
        'frozen_inputs': [bind(p) for p in dict.fromkeys(Path(p).resolve() for p in deps)],
        'local_pre_request_failure_cells': sum(r['local_pre_request_failure'] is not None for r in matrix),
        'formal_eligible': False, 'expert_returns': 0}
    gate.save_once(out / 'plan.json', plan); record(out, 'prepare', new_model_requests=0)
    return {'status': 'prepared_eight_not_generated', 'planned_observations': 8, 'new_model_requests': 0}


def validate(out):
    plan = j.read(out / 'plan.json')
    require(plan['status'] == 'frozen_before_generation' and plan['phase'] == 'confirmation'
            and plan['planned_answers'] == 8 and plan['planned_observations'] == 8
            and plan['max_attempts'] == plan['repeats'] == 1 and plan['planned_reused_observations'] == 0,
            'FROZEN_CONFIRMATION_SCOPE_CHANGED')
    gate.verify_bindings(plan['frozen_inputs'], [Path(__file__), Path(gate.__file__)])
    gate.verify(plan['root_release'])
    release = j.read(plan['root_release']['path']); paths = {k: gate.verify(v) for k, v in release['assets'].items()}
    backend, followup = load_runtime(paths)
    _, _, cases = read_source_preparation(out); indexed = {c['case_id']: c for c in cases}
    steps = j.read(out / 'step_inputs.json'); matrix = j.read(out / 'matrix.json'); contracts = j.read(out / 'expected_contract.json')
    require(len(matrix) == 8 and [(r['anonymous_answer_id'], r['judge']) for r in matrix]
            == [(aid, model) for aid in gate.IDS for model in gate.MODELS], 'FIXED_EIGHT_QWEN_MATRIX_CHANGED')
    require(contracts == j.read(paths['E4_contract']), 'CONFIRMATION_FINAL_E4_CONTRACT_CHANGED')
    for row in matrix:
        c = indexed[row['case_id']]; s = steps[c['case_id']]
        require(row['step'] == s and s['answer_sha256'] == c['answer_sha256'] and s['question_sha256'] == c['question_sha256']
                and s['references_sha256'] == j.digest(c['references']) and s['threshold'] == .7,
                'EXACT_SOURCE_STEP_REFERENCE_BINDING')
        require(row['planned_trial_id'] == j.digest(row['identity']) and row['repeat_index'] == 0
                and row['attempt'] == 1 and row['reuse'] is None
                and row['identity']['contract_sha256'] == j.digest(contracts[row['judge']]), 'CELL_IDENTITY_CHANGED')
        require(row['identity']['input_sha256'] == j.digest({'question': c['specific_question'], 'question_id': c['question_id'],
                'protocol': c['model_response'], 'references': c['references']}), 'CELL_INPUT_CHANGED')
        gate.verify_bindings(list(row['assets'].values()))
        if 'source_document' in row['assets']:
            doc = j.read(row['assets']['source_document']['path'])
            require(doc == backend.grounded.document(c['model_response'], backend.grounded.source_id_for_case(c)), 'DOCUMENT_DRIFT')
            schema = backend.grounded.schema_for_document(doc)
            require(schema == j.read(row['assets']['schema']['path']), 'PER_SOURCE_SCHEMA_DRIFT')
            prompt = Path(row['assets']['prompt']['path']).read_bytes().decode('utf8')
            payload = backend.payload_for(prompt, schema, contracts[row['judge']]['models'][0]['settings'])
            require(j.read(row['assets']['payload']['path']) == payload and row['identity']['payload_sha256'] == j.digest(payload),
                    'FROZEN_HTTP_PAYLOAD_DRIFT')
    return plan, cases, matrix, contracts, backend, followup


def preflight(args):
    plan, cases, matrix, contracts, backend, followup = validate(args.out)
    actual, models = followup.model_contracts(args.out / 'model_config.json', 'E2')
    require(actual == contracts, 'ACTUAL_LOCAL_DIGEST_OR_CONTRACT_DRIFT')
    indexed = {c['case_id']: c for c in cases}
    for r in matrix:
        if 'prompt' in r['assets']:
            doc = j.read(r['assets']['source_document']['path'])
            require(backend.grounded.make_prompt(indexed[r['case_id']], doc)
                    == Path(r['assets']['prompt']['path']).read_bytes().decode('utf8'), 'ACTUAL_FULL_PROMPT_REPLAY')
    value = {'status': 'pass', 'phase': 'confirmation', 'planned_observations': 8,
        'actual_model_metadata': models, 'science_acceptance': False, 'new_model_requests': 0,
        'bindings': [bind(args.out / n) for n in ['plan.json', 'matrix.json', 'expected_contract.json']] + [bind(__file__)]}
    if (args.out / 'preflight.json').exists():
        require(j.read(args.out / 'preflight.json') == value, 'PREFLIGHT_DRIFT')
    else:
        gate.save_once(args.out / 'preflight.json', value)
    record(args.out, 'preflight', new_model_requests=0)
    return {'status': 'pass', 'new_model_requests': 0}


def record(out, action, **details):
    path = out / 'actual_commands.json'; rows = j.read(path) if path.exists() else []
    rows.append({'utc': j.now(), 'action': action, 'actual_command': [sys.executable, *sys.argv],
                 'runtime_sha256': j.filehash(__file__), **details}); j.save(path, rows)


def run_gate(args):
    state = validate(args.out); pre = j.read(args.out / 'preflight.json')
    require(pre.get('status') == 'pass', 'PREFLIGHT_REQUIRED'); gate.verify_bindings(pre['bindings'])
    approval = j.read(args.run_authorization)
    require(approval.get('status') == 'approved_for_local_run' and approval.get('authorized_by') == 'root_agent'
            and approval.get('phase') == 'confirmation' and approval.get('no_post_confirmation_tuning') is True,
            'EXPLICIT_ROOT_CONFIRMATION_RUN_AUTHORIZATION')
    expected = [args.out / n for n in ['plan.json', 'matrix.json', 'expected_contract.json', 'preflight.json']]
    gate.verify_bindings(approval['bindings'], [*expected, Path(__file__), Path(gate.__file__), args.integration_review])
    review = j.read(args.integration_review)
    require(review.get('status') == 'pass' and review.get('reviewed_by') == 'root_agent'
            and review.get('root_reviewed') is True and review.get('formal_mode') is True,
            'ROOT_REVIEWED_FORMAL_SERIALIZED_HTTP_INTEGRATION_REQUIRED')
    gate.verify_bindings(review['bindings'], [*expected, Path(__file__), Path(gate.__file__)])
    result_path = gate.verify(review['integration_result']); result = j.read(result_path)
    require(result.get('status') == 'pass' and result.get('formal_mode') is True
            and result.get('planned_observations') == 8 and result.get('real_model_requests') == 0,
            'ACTUAL_FORMAL_HTTP_SOFTWARE_INTEGRATION_REQUIRED')
    gate.verify_bindings(result['bindings'], [*expected, Path(__file__), Path(gate.__file__)])
    actual, _ = state[5].model_contracts(args.out / 'model_config.json', 'E2')
    require(actual == state[3], 'RUN_MODEL_OR_SCIENTIFIC_CONTRACT_DRIFT')
    return state


def local_failure_trial(out, row):
    reason = row['local_pre_request_failure']; require(reason is not None, 'NO_FROZEN_LOCAL_FAILURE')
    tid = row['planned_trial_id']; attempt = out / 'run/attempts' / (tid + '_1')
    require(not attempt.exists() and all(r['trial_id'] != tid for r in budget.counts()['requests']), 'LOCAL_FAILURE_HAS_REQUEST_TRACE')
    value = {'trial_id': tid, 'identity': row['identity'], 'case_id': row['case_id'], 'anonymous_answer_id': row['anonymous_answer_id'],
        'judge': row['judge'], 'repeat_index': 0, 'attempt': 1, 'phase': 'confirmation', 'status': 'failed',
        'actual_request_made': False, 'request_id': None, 'failure_stage': reason['stage'], 'local_pre_request_failure': reason,
        'metrics': scoring.derive({}, row['step'], False), 'terminal_utc': j.now(),
        'bound_artifacts': [bind(out / n) for n in ['plan.json', 'matrix.json', 'cases.json', 'step_inputs.json']]}
    gate.save_once(out / 'run/trials' / (tid + '.json'), value)
    return value


def terminal(out, row, followup):
    tid = row['planned_trial_id']; path = out / 'run/trials' / (tid + '.json'); t = j.read(path)
    require(t.get('trial_id') == tid == j.digest(row['identity']) and t.get('identity') == row['identity']
            and t.get('case_id') == row['case_id'] and t.get('anonymous_answer_id') == row['anonymous_answer_id']
            and t.get('judge') == row['judge'] and t.get('phase') == 'confirmation'
            and type(t.get('repeat_index')) is int and t['repeat_index'] == row['repeat_index'] == 0
            and type(t.get('attempt')) is int and t['attempt'] == row['attempt'] == 1
            and type(t.get('actual_request_made')) is bool, 'CONFIRMATION_TERMINAL_IDENTITY')
    if t.get('actual_request_made') is False:
        require(row['local_pre_request_failure'] is not None and t['local_pre_request_failure'] == row['local_pre_request_failure']
                and t['trial_id'] == tid and t['identity'] == row['identity'] and t['case_id'] == row['case_id']
                and t['judge'] == row['judge'] and t['attempt'] == 1 and t['status'] == 'failed'
                and t['request_id'] is None and t['metrics'] == scoring.derive({}, row['step'], False), 'LOCAL_TERMINAL_IDENTITY')
        require(t['local_pre_request_failure'].get('actual_request_made') is False
                and t.get('failure_stage') == row['local_pre_request_failure'].get('stage')
                and t['failure_stage'] in ['LOCAL_SOURCE_PREPARATION', 'LOCAL_CONTEXT_LIMIT'],
                'LOCAL_TERMINAL_FAILURE_STAGE')
        gate.verify_bindings(t['bound_artifacts'])
        require(not (out / 'run/attempts' / (tid + '_1')).exists()
                and all(r['trial_id'] != tid for r in budget.counts()['requests']), 'LOCAL_FAILURE_HAS_REAL_REQUEST')
        return t
    require(not row['local_pre_request_failure'], 'INELIGIBLE_CONTEXT_WAS_SENT')
    value = followup.terminal_identity(out, row)
    attempt = out / 'run/attempts' / (tid + '_1')
    receipt = j.read(attempt / 'request_receipt.json')
    require(receipt['phase'] == 'confirmation' and receipt['round_id'] == budget.ROUND
            and receipt.get('trial_id') == tid and receipt.get('model') == row['judge']
            and type(receipt.get('attempt')) is int and receipt['attempt'] == 1
            and receipt.get('request_id') == j.digest({'trial_id': tid, 'attempt': 1})
            and value['request_id'] == receipt['request_id'], 'CONFIRMATION_PHASE_RECEIPT')
    evaluation = value['evaluation']; stage = evaluation.get('failure_stage'); failed = value['status'] == 'failed'
    require(evaluation.get('technical_status') == ('FAILED' if failed else 'SUCCESS')
            and ((isinstance(stage, str) and bool(stage)) if failed else stage is None)
            and ('failure_stage' not in value or value['failure_stage'] == stage), 'CONFIRMATION_FAILURE_STAGE')
    if failed:
        failure_path = attempt / 'failure.json'
        gate.verify_bindings(value['bound_artifacts'], [failure_path])
        failure = j.read(failure_path)
        require(failure.get('stage') == stage and failure.get('actual_request_reserved') is True,
                'CONFIRMATION_FAILURE_SIDECAR_MISMATCH')
    else:
        require(not (attempt / 'failure.json').exists(), 'SUCCESS_WITH_FAILURE_SIDECAR')
    return value


async def run(args):
    require(args.allow_local_calls, 'EXPLICIT_LOCAL_CALL_FLAG_REQUIRED')
    require(type(args.max_new_calls) is int and 1 <= args.max_new_calls <= 8, 'MAX_NEW_CALLS_LIMIT')
    plan, cases, matrix, contracts, backend, followup = run_gate(args)
    indexed = {c['case_id']: c for c in cases}; started = {r['trial_id'] for r in budget.counts()['requests']}
    for row in matrix:
        p = args.out / 'run/trials' / (row['planned_trial_id'] + '.json')
        if p.exists():
            terminal(args.out, row, followup)
        else:
            require(row['planned_trial_id'] not in started
                    and not (args.out / 'run/attempts' / (row['planned_trial_id'] + '_1')).exists(), 'RESERVED_OR_PARTIAL_CELL_NO_RETRY')
    made = 0
    for row in matrix:
        if (args.out / 'run/trials' / (row['planned_trial_id'] + '.json')).exists():
            continue
        if row['local_pre_request_failure']:
            local_failure_trial(args.out, row); continue
        if made >= args.max_new_calls:
            break
        validate(args.out); budget.guard('confirmation', 1, 600)
        await followup.execute_cell(args.out, 'confirmation', row, indexed[row['case_id']], contracts[row['judge']]['models'][0]['settings'])
        made += 1
    record(args.out, 'run', new_model_requests=made)
    return {'status': 'run_pass_ended_without_retry', 'new_model_requests': made, 'planned_observations': 8}


def local_observation(row, trial):
    metrics = scoring.derive({}, row['step'], False)
    return {'anonymous_answer_id': row['anonymous_answer_id'], 'case_id': row['case_id'], 'question_id': row['question_id'],
        'judge': row['judge'], 'repeat_index': 0, 'trial_id': row['planned_trial_id'], 'status': 'failed',
        'failure_stage': trial['failure_stage'], 'reused': False, 'actual_request_made': False,
        'technical_executable': False, 'complete_numeric_CCE': False, 'metrics': metrics, **metrics,
        'formal_eligible': False, 'source': 'verified_pre_request_local_failure'}


def analyze(args):
    plan, cases, matrix, contracts, backend, followup = validate(args.out)
    local = {}; normal = []; bindings = []
    for row in matrix:
        p = args.out / 'run/trials' / (row['planned_trial_id'] + '.json')
        if p.exists():
            t = terminal(args.out, row, followup)
            if t.get('actual_request_made') is False:
                local[row['planned_trial_id']] = local_observation(row, t); bindings += [bind(p), *t['bound_artifacts']]; continue
        normal.append(row)
    rows, bound, replays = followup.read_observations(args.out, plan, cases, normal, contracts)
    values = {r['trial_id']: r for r in rows}; values.update(local)
    rows = [values[r['planned_trial_id']] for r in matrix]; bindings += bound
    indexed = {(r['anonymous_answer_id'], r['judge']): r for r in rows}
    common = [aid for aid in gate.IDS if all(indexed[(aid, m)]['complete_numeric_CCE'] for m in gate.MODELS)]
    mean_keys = ['sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']
    common_means = {m: {k: sum(indexed[(aid, m)][k] for aid in common) / len(common) if common else None for k in mean_keys}
                    for m in gate.MODELS}
    terminal_count = sum(r['status'] != 'pending' for r in rows); successes = sum(r['status'] == 'success' for r in rows)
    actual_requests = sum(r['planned_trial_id'] in {q['trial_id'] for q in budget.counts()['requests']} for r in matrix)
    followup.write_table(args.out, 'observations', rows); followup.write_table(args.out, 'per_answer', rows)
    summary = {'status': 'experiment_complete_not_scientific_validation' if terminal_count == 8 else 'partial_experiment_not_scientific_validation',
        'phase': 'confirmation', 'scope': gate.SCOPE, 'planned_answers': 8, 'planned_observations': 8,
        'actual_observations': terminal_count, 'pending': 8 - terminal_count, 'technical_successes': successes,
        'technical_failures': terminal_count - successes, 'actual_new_requests': actual_requests, 'reused_observations': 0,
        'local_pre_request_failures': len(local), 'complete_numeric_CCE': sum(r['complete_numeric_CCE'] for r in rows),
        'component_coverage': {k: sum(scoring.finite(r[k]) for r in rows if r['status'] != 'pending') for k in scoring.METRICS},
        'common_answer_ids': common, 'common_n': len(common), 'common_means': common_means,
        'common_aggregation': 'equal_weight_over_common_answer_ids_not_qid_macro_average',
        'raw_conversion_and_numeric_replays': replays, 'bound_observations': bindings,
        'source_fact_acceptance': 'requires_separate_source_review_not_software_success',
        'formal_eligible': False, 'expert_returns': 0, 'new_model_requests_from_analysis': 0,
        'no_unseen_task_or_source_family_independence_claim': True,
        'second_evaluator_pending': True, 'cross_judge_goal_complete': False,
        'common_aggregation_is_single_judge_finite_answer_subset': True}
    j.save(args.out / 'completion_summary.json', summary)
    j.save(args.out / 'analysis_verification.json', {'status': 'pass', 'all_planned_terminal': terminal_count == 8,
        'planned_observations': 8, 'terminal_observations': terminal_count, 'fixed_answers': 8,
        'successful_raw_numeric_replays': replays, 'failure_SR_SP_retained_other_metrics_NA': True,
        'common_empty_means_NA': all(v is None for m in common_means.values() for v in m.values()) if not common else None,
        'bindings': [bind(args.out / n) for n in ['plan.json', 'matrix.json', 'expected_contract.json', 'observations.json', 'completion_summary.json']],
        'new_model_requests': 0})
    record(args.out, 'analyze', new_model_requests=0, actual_observations=terminal_count)
    return {k: v for k, v in summary.items() if k not in ['bound_observations', 'common_means']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['draft', 'prepare', 'preflight', 'run', 'analyze'])
    p.add_argument('--out', type=Path, default=gate.OUT); p.add_argument('--release', type=Path, default=gate.DESIGN / 'final_release.json')
    p.add_argument('--run-authorization', type=Path); p.add_argument('--integration-review', type=Path)
    p.add_argument('--allow-local-calls', action='store_true'); p.add_argument('--max-new-calls', type=int, default=1)
    a = p.parse_args(); a.out = a.out.resolve(); require(a.out.is_relative_to(gate.BASE), 'ROUND2_OUTPUT_ONLY')
    a.run_authorization = a.run_authorization or a.out / 'root_run_authorization.json'
    a.integration_review = a.integration_review or a.out / 'root_integration_review.json'
    if a.action == 'draft':
        result = {'status': 'code_only_not_prepared', 'version': VERSION, 'release_controller_sha256': GATE_SHA256,
            'planned_answers': 8, 'planned_observations': 8, 'max_attempts': 1, 'models': gate.MODELS,
            'dynamic_selected_backend': True, 'generation_allowed_without_root_release': False,
            'original_scoring_and_no_partial_bounds': True, 'actual_new_calls': 0}
    elif a.action == 'run':
        result = asyncio.run(run(a))
    else:
        result = globals()[a.action](a)
    print(j.canonical(result))


if __name__ == '__main__':
    main()
