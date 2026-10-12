"""Public development E2: unchanged identity-v2 prompt, 21 full texts /15 pairs.

The immutable original controls, core step scorer, reference scope, scientific
rubric and strict parser are reused. No held-out answers or judge outputs are
read. Preparation and probes make no model requests; preflight reads loopback
metadata only. Generation requires a separately authorized run command.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import contextlib
import io
import math
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_output_identity_v2 as identity
import cce_output_contract_v1 as parent
import cce_judges as j
import cce_alternative_development as helper
import cce_validation as core
import evaluator_integrity as integrity

BASE = ROOT/'artifacts/cce_validation'
SOURCE = BASE/'judges/local_controls_supplement_v2'
OUT = BASE/'judges/controls_contract_v2'
RUN = OUT/'run'
LEDGER = parent.LEDGER
METRICS, MAXIMA = helper.METRICS, helper.MAXIMA
check = parent.require
CACHE_ROOTS = [BASE/'embedding_cache', SOURCE/'embedding_cache',
              BASE/'judges/local_alternative_development/embedding_cache',
              BASE/'judges/local_alternative_q1_v1/embedding_cache',
              BASE/'expanded_references_v6/embedding_cache',
              BASE/'expanded_references_v7/embedding_cache',
              BASE/'method_family_steps_v1/embedding_cache']


def bind(path):
    return parent.bind(path)


def key(case):
    """Full strings are the lookup key; hashes are independently recorded."""
    return (int(case['question_id']), case['specific_question'], case['model_response'])


def index_cases(cases):
    lookup = {key(c): c for c in cases}
    check(len(lookup) == len(cases), 'ambiguous_full_text_identity')
    return lookup


def arguments(allow=False):
    return SimpleNamespace(out=RUN, cases=OUT/'cases.json', model_config=OUT/'local_config_snapshot.json',
        models=[parent.MODEL], question_file=j.HIST, demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None, ledger=LEDGER, total_budget=300, external_request_count=0,
        max_calls=21, max_attempts=1, repeats=1, temperature=0.0, max_output_tokens=8192,
        timeout_seconds=600, allow_api=allow)


def record(command, **details):
    path = OUT/'actual_execution_commands.json'
    history = j.read(path) if path.exists() else []
    history.append({'utc':j.now(), 'argv':[sys.executable, 'scripts/cce_controls_contract_v2.py', command]
        + (['--allow-local-calls'] if command == 'run' else []), 'cwd':str(ROOT),
        'script_sha256':j.filehash(__file__), 'package_requests_snapshot':parent.request_count(), **details})
    j.save(path, history)


def validate():
    identity.validate()
    plan = j.read(OUT/'plan.json')
    for entry in plan['frozen_inputs'] + plan['protected_originals']:
        check(j.filehash(entry['path']) == entry['sha256'], 'frozen_file_changed:'+str(entry['path']))
    check(plan['planned_new_requests'] == 21 and plan['planned_pairs'] == 15, 'batch_shape_changed')
    return plan


def identity_variant():
    """Exactly the existing identity-v2 prompt/adapter provenance, no new rule."""
    return {'id':'output_identity_v2', 'plan_sha256':j.filehash(identity.OUT/'plan.json'),
        'script_sha256':j.filehash(identity.__file__),
        'generic_identity_rule_sha256':j.filehash(identity.OUT/'marker_identity_rule.txt'),
        'parent_contract_script_sha256':j.filehash(parent.__file__),
        'schema_sha256':j.filehash(identity.OUT/'final_output_schema.json'),
        'same_parent_adapter_provenance':True}


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'plan.json').exists():
        validate(); record('prepare', status='frozen_plan_reused', new_requests=0)
        print(j.canonical({'status':'frozen_plan_reused', 'new_requests':0})); return
    check(not list(RUN.glob('attempts/*/request_receipt.json')), 'existing_requests_prevent_prepare')
    identity.validate(); before = parent.request_count()
    check(before+21 <= 300, 'insufficient_package_budget')
    for name in ['cases.json', 'pairs.json', 'references.json']:
        (OUT/name).write_bytes((SOURCE/name).read_bytes())
    (OUT/'local_config_snapshot.json').write_bytes((identity.OUT/'local_config_snapshot.json').read_bytes())
    cases = j.read(OUT/'cases.json')['cases']; pairs = j.read(OUT/'pairs.json')
    lookup = index_cases(cases)
    check(len(cases) == 21 and len(pairs) == 15, 'original_controls_shape_changed')
    check(Counter(c['question_id'] for c in cases) == {2:7,21:7,22:7}, 'fixed_development_questions_changed')
    ids = {c['case_id'] for c in cases}
    check(len(ids) == 21 and all(p[s+'_case_id'] in ids for p in pairs for s in ['baseline','variant']), 'invalid_pair_identity')
    check(len({core.digest(c['model_response']) for c in cases}) == 21, 'distinct_full_text_count_changed')
    step_config = j.read(SOURCE/'step_config.json')
    check(step_config['adapter_sha256'] == j.filehash(core.__file__) and step_config['threshold'] == .7,
          'original_core_or_threshold_changed')
    weights = core.ASSETS/'assets/all-mpnet-base-v2/model.safetensors'
    if not weights.exists(): weights = weights.with_name('pytorch_model.bin')
    check(j.filehash(weights) == step_config['encoder']['weights_sha256'], 'local_encoder_weights_changed')
    (OUT/'step_config.json').write_bytes((SOURCE/'step_config.json').read_bytes())
    files = [OUT/n for n in ['cases.json','pairs.json','references.json','local_config_snapshot.json','step_config.json']]
    fixed_five = index_cases(j.read(identity.OUT/'cases.json')['cases'])
    matrix = []
    for position, case in enumerate(cases, 1):
        check(core.digest(case['model_response']) == case['answer_sha256'], 'answer_hash_changed')
        check(core.digest(case['specific_question']) == case['question_sha256'], 'question_hash_changed')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            original = helper.exact_runner_prompt(case)
        revised = identity.transform(original)
        check(revised.replace(identity.INSTRUCTION,'',1) == parent.transform(original), 'unexpected_identity_transform')
        check(revised.count(identity.INSTRUCTION) == 1, 'identity_rule_count')
        check(revised.endswith(parent.v2.reference_suffix(case)), 'reference_suffix_changed')
        for field in ['specific_question','model_response']:
            check(original.count(case[field]) == revised.count(case[field]) == 1, 'full_text_changed_or_duplicated')
        existing = fixed_five.get(key(case)); overlap = None
        if existing:
            p = identity.OUT/'prompts'/f"{existing['anonymous_answer_id']}_prompt.txt"
            check(revised == p.read_text(encoding='utf-8'), 'existing_identity_prompt_not_byte_identical')
            overlap = bind(p)
        bound = len(revised.encode('utf-8'))+8192+256
        check(bound <= 40960, 'conservative_context_bound_exceeded')
        prompt = OUT/'prompts'/f'{position:02d}_prompt.txt'; prompt.parent.mkdir(exist_ok=True)
        prompt.write_text(revised, encoding='utf-8'); files.append(prompt)
        matrix.append({'position':position, 'case_id':case['case_id'], 'question_id':case['question_id'],
            'condition':case['condition'], 'question_sha256':case['question_sha256'],
            'answer_sha256':case['answer_sha256'], 'question_raw_utf8_sha256':parent.rawsha(case['specific_question']),
            'answer_raw_utf8_sha256':parent.rawsha(case['model_response']),
            'input_sha256':j.digest({'question':case['specific_question'],'question_id':case['question_id'],
                'protocol':case['model_response'],'references':case['references']}),
            'references_sha256':j.digest(case['references']), 'prompt_path':str(prompt),
            'prompt_sha256':j.filehash(prompt), 'prompt_raw_utf8_sha256':parent.rawsha(revised),
            'prompt_canonical_string_sha256':j.digest(revised), 'conservative_context_bound':bound,
            'existing_fixed_five_prompt_identity_check':overlap})
    policy = {'version':'controls_contract_v2', 'prompt_version':'output_identity_v2_unmodified',
        'population':'All existing 21 public development control texts and all 15 original pairs.',
        'lookup':'Exact (question_id, full question, full answer); never first matching qid.',
        'new_requests':21, 'cross_version_trial_reuse':0, 'repeat_index':0, 'max_attempts':1,
        'old_fixed_five_gate':'The existing 4/5 outcome remains unchanged; this independent E2 diagnostic is not a holdout gate.',
        'strict_parser':'Original duplicate-key, schema and score-range checks; no JSON/key/alias repair.',
        'raw_failures':'Retain invalid trials, raw provider responses, and missing metrics. No replacement request.',
        'step_scoring':'Unchanged core.score_steps on each edited full answer, original supplied FDISCO references, threshold 0.7.',
        'scientific_scoring':'Original c_param, Correctness, KB, normalization and EGES; no marker alias or knowledge-base changes.',
        'pair_rule':'Both sides newly judged with the same contract and same full reference JSON. Deltas require technical completion on both sides; missing stays NA.',
        'numeric_rule':'Preserve recognized numeric proposals separately from technical/formal eligibility; never zero-impute failure.',
        'scope':'Development controlled sensitivity only. No held-out/human packet replacement, no scientific accuracy or formal eligibility claim.',
        'formal_eligible':False, 'expert_returns':0}
    j.save(OUT/'policy.json', policy); files.append(OUT/'policy.json')
    j.save(OUT/'package_ledger_snapshot.json', {'created_utc':j.now(), 'requests_started':before,
        'source_path':str(LEDGER), 'snapshot_sha256':j.filehash(LEDGER),
        'live_ledger_may_grow_independently':True, 'total_budget':300})
    files.append(OUT/'package_ledger_snapshot.json')
    protected = [SOURCE/n for n in ['cases.json','pairs.json','references.json','step_config.json','step_results.json','plan.json']]
    protected += [identity.OUT/n for n in ['plan.json','cases.json','local_config_snapshot.json','final_output_schema.json',
        'rubric_identity_preserved.txt','marker_identity_rule.txt','software_probes.json','preflight_verification.json']]
    protected += [ROOT/'scripts'/n for n in ['cce_validation.py','cce_judges.py','cce_output_identity_v2.py',
        'cce_output_contract_v1.py','cce_stability_remediation_v2.py','cce_alternative_development.py']]
    protected += [weights]
    files.append(Path(__file__).resolve())
    plan = {'status':'frozen_before_generation','version':'controls_contract_v2','created_utc':j.now(),
        'matrix':matrix,'planned_distinct_full_texts':21,'planned_pairs':15,'source_answers':3,
        'question_ids':[2,21,22],'condition_counts':dict(Counter(p['condition'] for p in pairs)),
        'judge':parent.MODEL,'planned_new_requests':21,'repeats':1,'max_attempts':1,
        'temperature':0,'max_output_tokens':8192,'num_ctx':40960,'timeout_seconds':600,
        'step_threshold':.7,'step_encoder':step_config['encoder'],'cross_version_trial_reuse':0,
        'package_requests_snapshot':before,'total_budget':300,'formal_eligible':False,
        'expert_confirmation':None,'no_heldout_scientific_output_access':True,'no_expert_packet_replacement':True,
        'fixed_five_gate_unchanged':True,'identity_variant':identity_variant(),
        'frozen_inputs':[bind(p) for p in dict.fromkeys(files)],
        'protected_originals':[bind(p) for p in dict.fromkeys(protected)],
        'run_not_executed_command':[sys.executable,'scripts/cce_controls_contract_v2.py','run','--allow-local-calls']}
    j.save(OUT/'plan.json',plan); validate()
    check(parent.request_count() == before,'prepare_made_request')
    record('prepare',status='completed',new_requests=0,plan_sha256=j.filehash(OUT/'plan.json'))
    write_readme()
    print(j.canonical({'status':'prepared_not_executed','full_texts':21,'pairs':15,'new_requests':0,
        'context_bounds':[min(r['conservative_context_bound'] for r in matrix),max(r['conservative_context_bound'] for r in matrix)],
        'package_requests_snapshot':before,'same_existing_identity_prompts':sum(bool(r['existing_fixed_five_prompt_identity_check']) for r in matrix)}))


@contextlib.contextmanager
def wrapper():
    old_runtime, old_contract, old_adapter = j.runtime, j.contract, j.make_adapter
    cases = j.read(OUT/'cases.json')['cases']; lookup = index_cases(cases)
    matrix = {c['case_id']:c for c in j.read(OUT/'plan.json')['matrix']}; restore = []
    def runtime(args):
        runner, api, registry = old_runtime(args)
        previous = runner.evaluate_response_with_teacher; restore.append((runner,previous))
        async def evaluate(teacher, question, answer, space, meta, template):
            case = lookup.get((int(meta['question_id']),question,answer))
            check(case is not None,'runtime_full_text_identity_not_frozen')
            class Teacher:
                model_name = teacher.model_name
                async def _acall(self,prompt):
                    revised = identity.transform(prompt)
                    cell = matrix[case['case_id']]
                    expected = Path(cell['prompt_path']).read_text(encoding='utf-8')
                    check(revised+parent.v2.reference_suffix(case) == expected,'runtime_prompt_not_frozen')
                    return await teacher._acall(revised)
            result = await previous(Teacher(),question,answer,space,meta,template)
            provider = ((result.get('teacher_generation') or {}).get('metadata') or {}).get('provider_response')
            if provider is not None: result['output_contract_diagnostic'] = parent.classify(provider)
            result['prompt_variant_provenance'] = {'variant':'output_identity_v2',
                'plan_sha256':j.filehash(identity.OUT/'plan.json'),
                'parent_output_contract_script_sha256':j.filehash(parent.__file__),
                'raw_return_modified':False,'lexicon_or_EGES_modified':False,
                'orchestration_batch':'controls_contract_v2','batch_plan_sha256':j.filehash(OUT/'plan.json'),
                'case_lookup':'exact_question_id_question_answer'}
            return result
        runner.evaluate_response_with_teacher = evaluate
        return runner,api,registry
    def contract(args,runner,registry,models):
        original = old_contract(args,runner,registry,models)
        check(original['files'] == j.read(parent.DEV/'frozen_judge_contract.json')['files'],'original_scoring_files_drift')
        actual = {**original,'output_identity_variant':identity_variant(),
            'controls_reassessment_batch':{'id':'controls_contract_v2','plan_sha256':j.filehash(OUT/'plan.json'),
                'script_sha256':j.filehash(__file__),'fresh_trials_for_all_21_full_texts':True}}
        preflight = OUT/'preflight_verification.json'
        if preflight.exists():
            check(j.digest(actual) == j.read(preflight)['contract_sha256'],'preflight_contract_drift')
        return actual
    def adapter(public,api_type):
        check(public['transport_kind']=='ollama_loopback' and public['format']=='json','unexpected_transport')
        api = old_adapter(public,api_type); previous = api._acall
        async def call(prompt):
            try: return await previous(prompt)
            except Exception as exc:
                recovered = parent.completed_json_failure_payload(api.last_response,exc,api.model_name,public['max_output_tokens'])
                if recovered is None: raise
                return recovered
        api._acall = call
        return api
    j.runtime,j.contract,j.make_adapter = runtime,contract,adapter
    try: yield
    finally:
        for runner,previous in reversed(restore): runner.evaluate_response_with_teacher=previous
        j.runtime,j.contract,j.make_adapter=old_runtime,old_contract,old_adapter


class ScopedEncoder(core.Encoder):
    def __init__(self):
        super().__init__(); self.used={}; self.new=set(); self.reused=set()
    def encode(self,texts):
        values=[]; destination=OUT/'embedding_cache'; destination.mkdir(exist_ok=True)
        for text in texts:
            name=core.digest([self.identity,text])+'.npy'
            source=next((p/name for p in CACHE_ROOTS+[destination] if (p/name).exists()),None)
            if source is None:
                source=destination/name
                value=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                self.np.save(source,value);self.new.add(name)
            else:
                value=self.np.load(source)
                if name not in self.new:self.reused.add(name)
            self.used[name]=bind(source);values.append(value)
        return self.np.asarray(values)


def replay_steps():
    encoder=ScopedEncoder(); config=j.read(OUT/'step_config.json')
    check(encoder.identity==config['encoder'],'encoder_identity_changed')
    old={r['case_id']:r for r in j.read(SOURCE/'step_results.json')}; results=[]
    for c in j.read(OUT/'cases.json')['cases']:
        step=core.score_steps(c,c['references'],encoder,.7)
        check(step==old[c['case_id']]['step_result'],'unchanged_original_step_result_not_reproduced:'+c['case_id'])
        results.append({'case_id':c['case_id'],'answer_sha256':c['answer_sha256'],
            'step_config_sha256':core.digest(config),'references_sha256':j.digest(c['references']),
            'step_result':step,'original_step_result_exactly_reproduced':True})
    j.save(OUT/'step_results.json',results)
    usage={'encoder':encoder.identity,'new_embeddings':len(encoder.new),'reused_embeddings':len(encoder.reused),
        'used_vectors':list(encoder.used.values()),'model_requests':0,'network_downloads':0,
        'original_cache_modified':False,'old_21_complete_step_results_exactly_reproduced':True}
    j.save(OUT/'embedding_usage.json',usage)
    return results,usage


def self_check():
    plan=validate(); before=parent.request_count(); checks=[]
    cases=j.read(OUT/'cases.json')['cases']; matrix={c['case_id']:c for c in plan['matrix']}
    class Captured(BaseException): pass
    async def actual_runtime_probes(runner):
        for case in cases:
            class CaptureOnly:
                model_name='offline_control_prompt_capture_no_model'
                async def _acall(self,prompt): raise Captured(prompt)
            try:
                await runner.evaluate_response_with_teacher(CaptureOnly(),case['specific_question'],case['model_response'],
                    runner.MODEL_SPACE_SIGNED,{'question_id':case['question_id']},None)
            except Captured as captured:
                full=str(captured)+parent.v2.reference_suffix(case)
                check(parent.rawsha(full)==matrix[case['case_id']]['prompt_raw_utf8_sha256'],'captured_prompt_hash_mismatch')
                checks.append({'kind':'actual_runtime_prompt_capture','case_id':case['case_id'],
                    'exact_full_text_lookup':True,'frozen_full_prompt_sha256_matches':True,'model_calls':0})
            else: raise AssertionError('runtime_did_not_reach_capture_adapter')
        case=cases[0]
        try:
            await runner.evaluate_response_with_teacher(CaptureOnly(),case['specific_question'],case['model_response']+'\nUNFROZEN',
                runner.MODEL_SPACE_SIGNED,{'question_id':case['question_id']},None)
        except ValueError as exc: check(str(exc)=='runtime_full_text_identity_not_frozen','unexpected_lookup_rejection')
        else: raise AssertionError('unfrozen_same_qid_answer_accepted')
        checks.append({'kind':'unfrozen_same_qid_full_text_rejected','passed':True})
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        runner,_,_=j.runtime(arguments());asyncio.run(actual_runtime_probes(runner))
    # Same original strict parser: never repair duplicate keys, even same-value keys.
    try: integrity.parse_judge_object('{"SYNTHETIC_KEY":1,"SYNTHETIC_KEY":1}')
    except integrity.JudgeFormatError: checks.append({'kind':'original_duplicate_key_rejection','passed':True})
    else: raise AssertionError('duplicate_parser_changed')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()): steps,usage=replay_steps()
    check(len(steps)==21,'step_probe_count')
    checks.append({'kind':'original_step_full_text_replay','cases':21,'complete_results_byte_equal':True})
    check(parent.request_count()==before,'offline_probe_made_request');validate()
    j.save(OUT/'software_probes.json',{'status':'pass','checks':checks,'new_requests':0,
        'plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'identity_parent_probes':bind(identity.OUT/'software_probes.json'),
        'step_results':bind(OUT/'step_results.json'),'embedding_usage':bind(OUT/'embedding_usage.json'),
        'new_embeddings':usage['new_embeddings'],'reused_embeddings':usage['reused_embeddings'],
        'scope':'Software/identity checks only, not scientific or expert evidence.'})
    record('self-check',status='completed',new_requests=0,checks=len(checks),
        new_embeddings=usage['new_embeddings'],reused_embeddings=usage['reused_embeddings'])
    print(j.canonical({'status':'offline_checks_pass','checks':len(checks),'new_requests':0,
        'new_embeddings':usage['new_embeddings'],'reused_embeddings':usage['reused_embeddings']}))


def require_probes():
    p=j.read(OUT/'software_probes.json')
    check(p['status']=='pass' and p['plan_sha256']==j.filehash(OUT/'plan.json') and p['script_sha256']==j.filehash(__file__),
          'current_offline_probes_required')
    for name in ['step_results','embedding_usage']:
        check(j.filehash(p[name]['path'])==p[name]['sha256'],'offline_probe_artifact_changed:'+name)
    for row in j.read(OUT/'embedding_usage.json')['used_vectors']:
        check(j.filehash(row['path'])==row['sha256'],'cached_vector_changed')


def preflight():
    plan=validate();require_probes();before=parent.request_count()
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(arguments())
    check(len(models)==1 and models[0]['name']==parent.MODEL,'wrong_judge')
    matrix=[];prior={r['trial_id'] for r in j.ledger_rows(LEDGER) if r.get('event')=='request_started'}
    for case in cases:
        cell={'case_id':case['case_id'],'input_sha256':case['input_sha256'],'judge':parent.MODEL,
            'repeat_index':0,'contract_sha256':j.digest(contract)}
        trial=j.digest(cell)
        check(trial not in prior,'new_e2_trial_collides_with_previous_request')
        matrix.append({'case_id':case['case_id'],'identity':cell,'planned_trial_id':trial,'attempt':1})
    check(len(matrix)==len({r['planned_trial_id'] for r in matrix})==21,'unique_trial_matrix_changed')
    check(parent.request_count()==before,'metadata_preflight_made_generation');validate()
    j.save(OUT/'preflight_verification.json',{'status':'pass','planned_trials':matrix,'new_requests':0,
        'plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'contract_sha256':j.digest(contract),'local_metadata_only':True,'generation_endpoint_called':False,
        'all_21_are_new_trial_identities':True,'full_prompt_hashes':plan['matrix']})
    record('preflight',status='completed',new_requests=0,contract_sha256=j.digest(contract))
    write_readme()
    print(j.canonical({'status':'preflight_pass','planned_calls':21,'pairs':15,'new_requests':0,'contract_sha256':j.digest(contract)}))


async def run():
    validate();require_probes();pre=j.read(OUT/'preflight_verification.json')
    check(pre['status']=='pass' and pre['plan_sha256']==j.filehash(OUT/'plan.json') and pre['script_sha256']==j.filehash(__file__),
          'current_metadata_preflight_required')
    before=len(list(RUN.glob('attempts/*/request_receipt.json')))
    with wrapper(): await j.run(arguments(True))
    validate();after=len(list(RUN.glob('attempts/*/request_receipt.json')))
    check(after<=21,'batch_request_limit_exceeded')
    record('run',status='completed_runner_return',new_requests=after-before,batch_receipts=after)


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def analyze():
    plan=validate();require_probes();before=parent.request_count()
    cases=j.read(OUT/'cases.json')['cases'];pairs=j.read(OUT/'pairs.json')
    steps={r['case_id']:r for r in j.read(OUT/'step_results.json')}
    # Steps were actually reparsed/recomputed in the offline probe using the exact
    # same full texts/config. Hash-verify those unchanged scientific inputs here.
    expected={r['case_id']:r for r in j.read(OUT/'preflight_verification.json')['planned_trials']}
    prompts={r['case_id']:r for r in plan['matrix']}
    trials=[j.read(p) for p in sorted((RUN/'trials').glob('*.json'))]
    indexed={r['case_id']:r for r in trials};check(len(indexed)==len(trials),'duplicate_case_trials')
    check(set(indexed)<=set(expected),'unexpected_trial_case')
    records=[];runtime_checks=[]
    for case in cases:
        cid=case['case_id'];trial=indexed.get(cid);step=steps[cid]['step_result'];evaluation=trial.get('evaluation',{}) if trial else {}
        raw=j.proposals(evaluation)
        if trial:
            check(trial['identity']==expected[cid]['identity'] and trial['trial_id']==expected[cid]['planned_trial_id'],'trial_identity_drift')
            check(trial['judge']==parent.MODEL and trial['repeat_index']==0 and trial['attempt']==1,'trial_configuration_drift')
            check(trial['full_text_input_sha256']==prompts[cid]['input_sha256'] and trial['references_sha256']==prompts[cid]['references_sha256'],'trial_scientific_input_drift')
            check(trial['preserved_numeric_proposals']==raw,'numeric_proposals_changed')
            attempt=RUN/'attempts'/f"{trial['trial_id']}_1"
            if trial['actual_api_request_made']:
                prompt=(attempt/'prompt.txt').read_text(encoding='utf-8')
                check(parent.rawsha(prompt)==prompts[cid]['prompt_raw_utf8_sha256'],'actual_full_prompt_changed')
                check(j.filehash(attempt/'prompt.txt')==prompts[cid]['prompt_sha256'],'actual_full_prompt_file_hash_changed')
                runtime_checks.append({'case_id':cid,'prompt':bind(attempt/'prompt.txt'),
                    'raw_utf8_sha256':parent.rawsha(prompt),'frozen_full_prompt_matches':True})
        complete=bool(trial and trial['status']=='success' and trial['actual_api_request_made'] and trial['new_extraction_available'])
        com=.4*step['sr']+.6*raw['c_param']/3 if finite(step['sr']) and finite(raw['c_param']) else None
        dims=[com,raw['Cor'],raw['Eff']];numeric=all(finite(x) for x in dims)
        values={**raw,'sr':step['sr'],'sp':step['sp'],'Com':com,
            'IA':min(dims) if numeric else None,'HV':math.prod(dims) if numeric else None}
        extraction=evaluation.get('extraction');method=extraction.get('method_name') if isinstance(extraction,dict) else None
        records.append({'case_id':cid,'source_case_id':case['source_case_id'],'question_id':case['question_id'],
            'condition':case['condition'],'base_id':case['base_id'],'generator_model':case['generator_model'],
            'answer_sha256':case['answer_sha256'],'question_sha256':case['question_sha256'],
            'full_text_input_sha256':prompts[cid]['input_sha256'],'references_sha256':prompts[cid]['references_sha256'],
            'reference_id':step.get('reference_id'),'reference_source_path':step.get('source_path'),
            'reference_source_url':step.get('source_url'),'step_config_sha256':steps[cid]['step_config_sha256'],
            'judge_config_sha256':trial.get('pipeline_config_sha256') if trial else None,
            'trial_id':trial.get('trial_id') if trial else None,
            'trial_source':str(RUN/'trials'/f"{trial['trial_id']}.json") if trial else None,
            'status':trial.get('status') if trial else 'not_run','technical_pipeline_complete':complete,
            'complete_numeric_proposals':numeric,'technical_and_numeric_complete':complete and numeric,
            'candidate_raw_and_derived':values,'candidate_normalized_items':{k:((v/MAXIMA[k]+1)/2 if k=='s_method' else v/MAXIMA[k]) if v is not None else None for k,v in raw.items() if k in MAXIMA},
            'candidate_na_reasons':{k:step.get('step_missing_reason') if k in ['sr','sp'] else 'upstream_absent_or_dependency_missing' for k,v in values.items() if v is None},
            'extraction':extraction,'extraction_status':evaluation.get('meta_data',{}).get('extraction_status'),
            'scientific_failure_flags':{'declared_route':step.get('route_id'),'extracted_route':method,
                'extraction_missing':not isinstance(extraction,dict),'extracted_route_missing':not bool(method),
                'explicit_route_mismatch':bool(method and method.lower().replace('-','')!='fdisco'),
                'interpretation':'Literal software observation, not expert scientific judgment.'},
            'raw_judgments':evaluation.get('legacy_diagnostics',{}),
            'failure_details':{k:evaluation.get(k) for k in ['_error','_error_type','failure_stage'] if k in evaluation},
            'upstream_integrity':evaluation.get('integrity'),'upstream_cce_eligible':evaluation.get('cce_eligible'),
            'official_scores':evaluation.get('official_scores'),'official_scores_field_present':'official_scores' in evaluation,
            'formal_eligible':False,'formal_scores':{k:None for k in ['sr','sp','Com','Cor','Eff','IA','HV']},
            'formal_na_reasons':['reference_task_applicability_and_controlled_edit_scientific_necessity_pending_expert'],
            'numeric_scope':'same_identity_v2_public_development_control_diagnostic_not_main_result'})
    byid={r['case_id']:r for r in records};results=[]
    for pair in pairs:
        a,b=(byid[pair[s+'_case_id']] for s in ['baseline','variant'])
        same=all(a[k]==b[k] and a[k] is not None for k in ['judge_config_sha256','step_config_sha256','references_sha256','question_sha256'])
        complete=same and a['technical_pipeline_complete'] and b['technical_pipeline_complete']
        row={**pair,'same_frozen_configuration':same,'technical_pipeline_complete':complete,
            'complete_numeric_pair':complete and a['complete_numeric_proposals'] and b['complete_numeric_proposals'],
            'judge_config_sha256':a['judge_config_sha256'],'step_config_sha256':a['step_config_sha256'],
            'references_sha256':a['references_sha256'],'formal_eligible':False,'formal_complete':False,
            'scope':'Original pair newly reevaluated with unchanged identity-v2 prompt; not a new independent pair.'}
        for metric in METRICS:
            av,bv=a['candidate_raw_and_derived'][metric],b['candidate_raw_and_derived'][metric]
            row.update({'baseline_'+metric:av,'variant_'+metric:bv,
                'delta_'+metric:bv-av if complete and finite(av) and finite(bv) else None})
        results.append(row)
    conditions=[]
    for condition in sorted({r['condition'] for r in results}):
        group=[r for r in results if r['condition']==condition]
        row={'condition':condition,'planned_pairs':len(group),
            'technical_completed_pairs':sum(r['technical_pipeline_complete'] for r in group),
            'complete_numeric_pairs':sum(r['complete_numeric_pair'] for r in group),'formal_completed_pairs':0}
        for metric in METRICS:
            vals=[r['delta_'+metric] for r in group if finite(r['delta_'+metric])]
            row.update({'n_'+metric:len(vals),'mean_delta_'+metric:sum(vals)/len(vals) if vals else None,
                'negative_'+metric:sum(v < -1e-12 for v in vals),'zero_'+metric:sum(abs(v)<=1e-12 for v in vals),
                'positive_'+metric:sum(v > 1e-12 for v in vals)})
        conditions.append(row)
    receipts=[j.read(p) for p in RUN.glob('attempts/*/request_receipt.json')]
    planned_ids={r['planned_trial_id'] for r in expected.values()}
    check(all(r['trial_id'] in planned_ids and r['attempt']==1 for r in receipts),'unplanned_request_receipt')
    ledger=[r for r in j.ledger_rows(LEDGER) if r.get('event')=='request_started' and r.get('trial_id') in planned_ids]
    check(len(receipts)==len(ledger)<=21,'request_accounting_mismatch')
    summary={'status':'analysis_complete' if len(trials)==21 else 'partial_batch_analysis',
        'planned_full_texts':21,'actual_trial_count':len(trials),'controlled_pairs':15,
        'source_answers':3,'question_ids':[2,21,22],'new_requests_this_batch':len(ledger),
        'cross_version_trial_reuse':0,'technical_successful_cases':sum(r['technical_pipeline_complete'] for r in records),
        'complete_numeric_proposal_cases':sum(r['complete_numeric_proposals'] for r in records),
        'technical_and_numeric_complete_cases':sum(r['technical_and_numeric_complete'] for r in records),
        'technical_completed_pairs':sum(r['technical_pipeline_complete'] for r in results),
        'complete_candidate_cce_pairs':sum(r['complete_numeric_pair'] for r in results),
        'invalid_cases_retained':sum(r['status']=='failed' for r in records),
        'missing_trials':21-len(trials),'request_receipts_without_trial_result':sum(r['trial_id'] not in {t['trial_id'] for t in trials} for r in receipts),
        'all_pairs_same_frozen_configuration':all(r['same_frozen_configuration'] for r in results),
        'condition_counts':dict(Counter(r['condition'] for r in results)),
        'formal_completed_pairs':0,'expert_returns':0,'formal_eligible':False,
        'original_fixed_five_4_of_5_gate_unchanged':True,'heldout_calls_or_changes':0,
        'scientific_accuracy_validated':False,'package_requests_in_ledger':parent.request_count(),
        'step_replay':bind(OUT/'software_probes.json'),'plan':bind(OUT/'plan.json')}
    for name,value in [('per_case.json',records),('paired_results.json',results),('control_summary.json',conditions),('development_summary.json',summary)]:j.save(OUT/name,value)
    core.table(OUT/'per_case.csv',[{k:r[k] for k in ['case_id','question_id','condition','status','technical_pipeline_complete',
        'complete_numeric_proposals','reference_id','formal_eligible','trial_id','judge_config_sha256','step_config_sha256']}
        |r['candidate_raw_and_derived'] for r in records])
    core.table(OUT/'paired_results.csv',results);core.table(OUT/'control_summary.csv',conditions)
    j.save(OUT/'verification.json',{'status':'pass','plan':bind(OUT/'plan.json'),
        'actual_full_prompt_checks':runtime_checks,'actual_trial_count':len(trials),
        'all_planned_trials_present':len(trials)==21,'receipt_count':len(receipts),
        'same_pair_configurations':[{'pair_id':r['pair_id'],'same':r['same_frozen_configuration']} for r in results],
        'original_step_results_exact_replay':bind(OUT/'software_probes.json'),
        'unchanged_identity_v2_transform_and_strict_parser':True,'formal_eligible':False})
    check(parent.request_count()==before,'analysis_made_request');validate()
    record('analyze',status=summary['status'],new_requests=0,summary_sha256=j.filehash(OUT/'development_summary.json'))
    write_readme();print(j.canonical(summary))


def write_readme():
    plan=j.read(OUT/'plan.json')
    summary=j.read(OUT/'development_summary.json') if (OUT/'development_summary.json').exists() else None
    lines=['# E2: unchanged identity-v2 controlled full-pipeline reassessment','',
        'Scope: 21 existing public development full texts, 15 original pairs, Qwen3:8b, one attempt per text. '
        'All 21 trial identities are new; no old baseline or successful judgment is substituted. '
        'Repeated question IDs are resolved by exact (qid, full question, full answer).','',
        'The prompt transformation is the frozen output_identity_v2 function. Original model settings, '
        'strict parsing, score scales, KB, EGES, step segmentation, threshold 0.7 and supplied FDISCO references are unchanged. '
        'Every edit is evaluated as a full answer. All failures and missing values remain visible.','',
        'The earlier fixed-five result remains 4/5. This separate development diagnostic does not authorize or replace '
        'held-out calls or human materials, and it cannot establish scientific extraction accuracy. Formal eligibility and expert returns remain zero.','',
        ('Generation not executed by preparation or metadata preflight.' if summary is None else
         f"Actual requests: {summary['new_requests_this_batch']}; technical cases: {summary['technical_successful_cases']}/21; "
         f"technical pairs: {summary['technical_completed_pairs']}/15; numeric complete pairs: {summary['complete_candidate_cce_pairs']}/15."),'',
        f"Frozen plan SHA256: `{j.filehash(OUT/'plan.json')}`.",'',
        '[Plan](plan.json) · [Actual prompt hashes](plan.json) · [Offline probes](software_probes.json) · '
        '[Metadata preflight](preflight_verification.json) · [Actual command receipts](actual_execution_commands.json)','',
        '```powershell']
    for command in ['prepare','self-check','preflight','run','analyze']:
        argv=[sys.executable,'scripts/cce_controls_contract_v2.py',command]+(['--allow-local-calls'] if command=='run' else [])
        lines.append('& '+' '.join("'"+s.replace("'","''")+"'" for s in argv))
    lines += ['```','','The run command is a separate scheduled action. Source controls and previous results remain unchanged.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','self-check','preflight','run','analyze'])
    parser.add_argument('--allow-local-calls',action='store_true');args=parser.parse_args()
    if args.command=='run':
        check(args.allow_local_calls,'run_requires_explicit_allow_local_calls');asyncio.run(run())
    else: {'prepare':prepare,'self-check':self_check,'preflight':preflight,'analyze':analyze}[args.command]()
