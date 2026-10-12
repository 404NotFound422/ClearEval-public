"""Frozen five-case development run for source-bound joint extraction and scoring.

The provider JSON is retained unchanged. A separately recorded, deterministic
projection feeds the existing numerical functions; the projection is never
represented as the raw model return or an expert annotation.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, copy, io, math, sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_output_identity_v2 as old
import cce_output_contract_v1 as parent
import cce_optimizer_model_probe_v1 as model_probe
import cce_grounded_extraction_v1 as grounded
import evaluator_integrity as integrity

OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_development_v1'
RUN=OUT/'run';MODEL=model_probe.MODEL
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']
require=parent.require

def args(allow=False):
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'model_config.json',
        models=[MODEL],question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None,ledger=parent.LEDGER,total_budget=300,external_request_count=0,
        max_calls=5,max_attempts=1,repeats=1,temperature=0.,max_output_tokens=8192,
        timeout_seconds=600,allow_api=allow)

def record(action,**details):
    p=OUT/'actual_commands.json';rows=j.read(p) if p.exists() else []
    rows.append({'utc':j.now(),'action':action,'argv':[sys.executable,*sys.argv],
        'cwd':str(ROOT),'script_sha256':j.filehash(__file__),
        'package_requests':parent.request_count(),**details});j.save(p,rows)

def validate():
    old.validate();model_probe.validate();plan=j.read(OUT/'plan.json')
    for item in plan['frozen_inputs']:
        require(j.filehash(item['path'])==item['sha256'],'grounded_frozen_input_changed:'+item['path'])
    require(plan['planned_new_requests']==5 and plan['max_attempts']==1,'batch_scope_changed')
    return plan

def casekey(c):return (int(c['question_id']),c['specific_question'],c['model_response'])

@contextlib.contextmanager
def wrapper(check_contract=False):
    original_runtime,original_contract,original_models,original_adapter=j.runtime,j.contract,j.model_configs,j.make_adapter
    cases=j.read(OUT/'cases.json')['cases'];lookup={casekey(c):c for c in cases}
    require(len(lookup)==5,'full_text_case_identity_collision');restore=[]
    def runtime(a):
        runner,api,registry=original_runtime(a);previous=runner.evaluate_response_with_teacher;restore.append((runner,previous))
        async def evaluate(teacher,question,answer,space,meta,template):
            c=lookup[(int(meta['question_id']),question,answer)];aid=c['anonymous_answer_id']
            doc=j.read(OUT/'source_documents'/f'{aid}.json')
            require(grounded.rawsha(answer)==doc['answer_sha256'],'runtime_full_answer_changed')
            expected=(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
            suffix=parent.v2.reference_suffix(c)
            require(expected.endswith(suffix),'reference_evidence_suffix_changed')
            transformed=[];errors=[]
            class Teacher:
                model_name=teacher.model_name
                async def _acall(self,prompt):
                    # The unchanged outer runner adds its exact reference suffix.
                    result=await teacher._acall(expected[:-len(suffix)] if suffix else expected)
                    raw=result.get('content')
                    require(isinstance(raw,str),'provider_content_type')
                    try:conversion=grounded.convert(raw,doc)
                    except Exception as exc:
                        errors.append({'stage':'SOURCE_BOUND_CONVERSION','type':type(exc).__name__,
                                       'reason':str(exc),'raw_response_sha256':grounded.rawsha(raw)})
                        # Preserve the raw return for upstream diagnostics. The explicit
                        # gate below rejects this trial even if it resembles legacy JSON.
                        return result
                    transformed.append(conversion)
                    return {**result,'content':conversion['legacy_runner_content'],'raw_content':raw,
                        'metadata':{**result.get('metadata',{}),'explicit_source_bound_projection':True,
                            'raw_model_content_sha256':grounded.rawsha(raw),
                            'projected_content_sha256':grounded.rawsha(conversion['legacy_runner_content'])}}
            result=await previous(Teacher(),question,answer,space,meta,template)
            if errors:
                result['upstream_status_before_grounded_gate']=result.get('technical_status')
                result.update(technical_status='FAILED',failure_stage='SOURCE_BOUND_CONVERSION',
                    _error='Source-bound contract rejected the raw return: '+errors[0]['reason'],
                    _error_type=errors[0]['type'],cce_eligible=False,official_scores=None)
            result['grounded_extraction_v1']={'conversion':transformed[0] if transformed else None,
                'conversion_errors':errors,'raw_return_modified':False,'legacy_input_explicitly_projected':bool(transformed),
                'plan_sha256':j.filehash(OUT/'plan.json'),'scientific_confirmation':False}
            return result
        runner.evaluate_response_with_teacher=evaluate;return runner,api,registry
    def models(a):
        rows=original_models(a)
        for row in rows:
            require(row['public']['transport_kind']=='ollama_loopback','local_only')
            row['public']['format']=j.read(OUT/'schema.json')
        return rows
    def contract(a,runner,registry,models):
        value=original_contract(a,runner,registry,models)
        baseline=j.read(model_probe.OUT/'expected_contract.json')
        require(value['files']==baseline['files'] and value['demands']==baseline['demands'],'original_science_or_demand_changed')
        value['source_bound_variant']={'version':'grounded_development_v1',
            'plan_sha256':j.filehash(OUT/'plan.json'),'runner_script_sha256':j.filehash(__file__),
            'grounded_script_sha256':j.filehash(grounded.__file__),'schema_sha256':j.filehash(OUT/'schema.json'),
            'raw_output_and_projection_separately_preserved':True}
        if check_contract:require(value==j.read(OUT/'expected_contract.json'),'runtime_contract_drift_before_generation')
        return value
    def adapter(public,api_type):
        api=original_adapter(public,api_type);previous=api.client.client.generate
        def capture(**kwargs):
            require(kwargs['format']==j.read(OUT/'schema.json'),'decoder_schema_drift')
            kwargs['options']['num_ctx']=public['num_ctx']
            ph=grounded.rawsha(kwargs['prompt']);matches=[r for r in j.read(OUT/'matrix.json') if r['prompt_raw_sha256']==ph]
            require(len(matches)==1,'actual_prompt_not_in_frozen_matrix');cell=matches[0]
            dest=RUN/'attempts'/f"{cell['planned_trial_id']}_1"
            require((dest/'request_receipt.json').exists(),'transport_payload_without_reserved_receipt')
            j.save(dest/'http_request_payload.json',kwargs)
            return previous(**kwargs)
        api.client.client.generate=capture
        return api
    j.runtime,j.contract,j.model_configs,j.make_adapter=runtime,contract,models,adapter
    try:yield
    finally:
        for runner,previous in reversed(restore):runner.evaluate_response_with_teacher=previous
        j.runtime,j.contract,j.model_configs,j.make_adapter=original_runtime,original_contract,original_models,original_adapter

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():validate();print(j.canonical({'status':'frozen_plan_reused','new_requests':0}));return
    require(not list(RUN.glob('attempts/*/request_receipt.json')),'existing_generation_prevents_freeze')
    old.validate();model_probe.validate();before=parent.request_count()
    require(before==197,'development_v1_starts_after_five_model_only_calls')
    source_plan=j.read(grounded.OUT/'plan.json')
    require(all(r['fits_40960'] for r in source_plan['matrix']),'candidate_context_does_not_fit')
    # Root reviews the completed source contract and synthetic probes before freeze.
    probes=grounded.OUT/'software_probes.json';require(probes.exists(),'grounded_software_probes_required')
    check=j.read(probes)
    require(check['status']=='pass' and check['new_model_requests']==0,'grounded_software_probes_not_passed')
    require(check['script_sha256']==j.filehash(grounded.__file__) and
        check['schema_sha256']==j.filehash(grounded.OUT/'schema.json') and
        check['plan_sha256']==j.filehash(grounded.OUT/'plan.json'),'grounded_probes_stale')
    for path,hash_value in source_plan['input_sha256'].items():
        require(j.filehash(path)==hash_value,'grounded_source_plan_binding_changed:'+path)
    fact=OUT.parent/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json'
    require(fact.exists(),'prespecified_source_fact_inventory_required')
    (OUT/'cases.json').write_bytes((old.OUT/'cases.json').read_bytes())
    (OUT/'model_config.json').write_bytes((model_probe.OUT/'model_config.json').read_bytes())
    (OUT/'schema.json').write_bytes((grounded.OUT/'schema.json').read_bytes())
    cases=j.read(OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==parent.IDS,'fixed_five_changed')
    inputs=[Path(__file__),Path(grounded.__file__),grounded.OUT/'plan.json',probes,fact,
        OUT/'cases.json',OUT/'model_config.json',OUT/'schema.json',old.OUT/'plan.json',
        model_probe.OUT/'plan.json',model_probe.OUT/'completion_summary.json',
        OUT.parent/'validation_design_v1/acceptance_matrix.json']
    for c in cases:
        aid=c['anonymous_answer_id']
        for directory,extension in [('source_documents','json'),('prompts','txt')]:
            src=grounded.OUT/directory/f'{aid}.{extension}';dst=OUT/directory/src.name
            dst.parent.mkdir(exist_ok=True);dst.write_bytes(src.read_bytes());inputs += [src,dst]
        doc=j.read(OUT/'source_documents'/f'{aid}.json');prompt=(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        require(doc['text']==c['model_response'],'full_answer_not_exact')
        require(grounded.make_prompt(c,doc)==prompt,'prompt_not_reproducible')
        require(len(prompt.encode('utf8'))+8192+256<=40960,'context_bound_exceeded')
    plan={'status':'frozen_before_generation','version':'grounded_development_v1','created_utc':j.now(),
        'starting_requests':before,'planned_new_requests':5,'max_attempts':1,'repeats':1,'model':MODEL,
        'intervention':'Joint source-bound arrays, exact-span conversion, program time arithmetic, structured decoder, direct-score evidence; model same as preceding model-only probe.',
        'old_direct_scales_EGES_demands_and_references_unchanged':True,
        'changes_are_a_bundle_not_single_factor_ablation':True,
        'time_policy_change':'No numeric overnight convention or collapsed duration range in primary extraction; retain named legacy comparison.',
        'raw_returns_never_repaired_or_replaced':True,'synthetic_probes_not_experimental_success':True,
        'formal_eligible':False,'human_expert_returns':0,'next_stage_requires_observed_development_review':True,
        'frozen_inputs':[parent.bind(p) for p in inputs]}
    j.save(OUT/'plan.json',plan);validate();record('prepare',new_requests=0)
    print(j.canonical({'status':'frozen_five_development_cases','new_requests':0,'planned_new_requests':5}))

def preflight():
    validate();before=parent.request_count()
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    require(len(models)==1 and models[0]['name']==MODEL,'model_selection_changed')
    prior=j.read(model_probe.OUT/'expected_contract.json')['models'][0]['settings']
    current=models[0]['public'];require({**current,'format':'json'}==prior,'model_settings_changed_beyond_schema_format')
    j.save(OUT/'expected_contract.json',contract);matrix=[]
    for c in cases:
        aid=c['anonymous_answer_id'];identity={'case_id':c['case_id'],'input_sha256':c['input_sha256'],
            'judge':MODEL,'repeat_index':0,'contract_sha256':j.digest(contract)}
        prompt=(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        matrix.append({'anonymous_answer_id':aid,'identity':identity,'planned_trial_id':j.digest(identity),
            'prompt_raw_sha256':grounded.rawsha(prompt),'prompt_file_sha256':j.filehash(OUT/'prompts'/f'{aid}.txt')})
    j.save(OUT/'matrix.json',matrix)
    require(parent.request_count()==before,'preflight_requested_generation')
    j.save(OUT/'preflight_verification.json',{'status':'pass','new_requests':0,
        'plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'expected_contract_sha256':j.filehash(OUT/'expected_contract.json'),
        'matrix_sha256':j.filehash(OUT/'matrix.json'),'same_model_as_previous_probe':True})
    record('preflight',new_requests=0);print(j.canonical({'status':'preflight_pass','planned_calls':5,'new_requests':0}))

def validate_preflight():
    validate();p=j.read(OUT/'preflight_verification.json')
    require(p['status']=='pass','preflight_not_passed')
    for key,path in [('plan_sha256',OUT/'plan.json'),('script_sha256',Path(__file__)),
        ('expected_contract_sha256',OUT/'expected_contract.json'),('matrix_sha256',OUT/'matrix.json')]:
        require(p[key]==j.filehash(path),'preflight_binding_changed:'+key)

async def run():
    validate_preflight();before=parent.request_count()
    with wrapper(check_contract=True):await j.run(args(True))
    validate_preflight();record('run',new_requests=parent.request_count()-before)

def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def same(a,b):return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=1e-12

def gate_components(values,conversion,replay):
    result=copy.deepcopy(values);projection=conversion['legacy_projection'];state=projection['component_input_state']
    notes={}
    if state['s_label']!='available_provisional':
        # The old bounded minimum is determined by a retained, supported zero,
        # despite other unknown values; do not replace that defined zero by NA.
        known_zero=replay['s_label']==0 and any(replay[k]==0 for k in
            ['s_target_match','s_marker_fluor_compat','s_method_fluor_compat'])
        if known_zero:notes['s_label']='Original minimum determined by zero from retained projected inputs; incomplete entity coverage remains separately reported.'
        else:result['s_label']=None;notes['s_label']='Partial entity/target projection cannot supply a fully known nonzero label score.'
    eff=[(result['s_method']/2.5+1)/2 if finite(result['s_method']) else None,
         result['s_label']/6 if finite(result['s_label']) else None,
         result['s_trans']/3 if finite(result['s_trans']) else None,
         result['s_time']/3 if finite(result['s_time']) else None]
    result['Eff']=sum(eff)/4 if all(finite(v) for v in eff) else None
    return result,notes

def analyze():
    validate_preflight();before=parent.request_count();ledger={r['request_id']:r for r in j.ledger_rows(parent.LEDGER)}
    cases={c['case_id']:c for c in j.read(OUT/'cases.json')['cases']};rows=[];bindings=[]
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,_,registry=j.runtime(args())
    for cell in j.read(OUT/'matrix.json'):
        aid=cell['anonymous_answer_id'];trial=cell['planned_trial_id'];p=RUN/'trials'/f'{trial}.json'
        require(p.exists(),'incomplete_actual_trial:'+aid);t=j.read(p);e=t.get('evaluation') or {}
        attempt=RUN/'attempts'/f'{trial}_1';receipt=j.read(attempt/'request_receipt.json')
        require(receipt==ledger[receipt['request_id']] and t['identity']==cell['identity'],'trial_receipt_or_identity_changed')
        require(j.filehash(attempt/'prompt.txt')==cell['prompt_file_sha256'],'actual_prompt_changed')
        payload=j.read(attempt/'http_request_payload.json')
        require(payload['format']==j.read(OUT/'schema.json') and payload['options']['num_ctx']==40960,'actual_decoder_or_context_changed')
        require(grounded.rawsha(payload['prompt'])==cell['prompt_raw_sha256'],'actual_http_prompt_changed')
        conversion=(e.get('grounded_extraction_v1') or {}).get('conversion');raw=j.proposals(e)
        checked={k:None for k in raw};notes={};replay=None;sourcecheck=False
        if t['status']=='success':
            require(conversion is not None,'successful_trial_missing_grounded_conversion')
            provider=j.read(attempt/'provider_response.json');doc=j.read(OUT/'source_documents'/f'{aid}.json')
            independently_converted=grounded.convert(provider['response'],doc)
            require(independently_converted==conversion,'raw_to_projection_replay_failed')
            require(e['extraction']==conversion['legacy_projection']['extraction'],'original_runner_received_different_extraction')
            c=cases[t['case_id']];demand=registry.get(c['question_id'],c['specific_question'])
            meta=runner.QUESTION_META_KB[registry.questions[str(c['question_id'])]['question_id']]
            require(demand==e['user_preference_vector'],'demand_drift')
            replay=runner.calculate_effectiveness_score(e['quantitative_data'],demand,runner.MODEL_SPACE_SIGNED,e['extraction']['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(same(replay[k],raw[k]) for k in EGES),'original_EGES_replay_failed')
            require(e['legacy_diagnostics']['raw_teacher_scores']==conversion['legacy_runner_payload']['scores'],'direct_scores_modified')
            checked,notes=gate_components(raw,conversion,replay);sourcecheck=True
            j.save(OUT/'conversion_replays'/f'{aid}.json',independently_converted)
        rows.append({'anonymous_answer_id':aid,'case_id':t['case_id'],'trial_id':trial,'request_index':receipt['package_request_index'],
            'status':t['status'],'failure_stage':e.get('failure_stage'),
            'grounded_conversion_errors':(e.get('grounded_extraction_v1') or {}).get('conversion_errors'),
            'raw_original_numeric_proposals':raw,'component_gated_proposals':checked,'component_gate_notes':notes,
            'projection_input_states':conversion['legacy_projection']['component_input_state'] if conversion else None,
            'extraction':e.get('extraction'),'time_calculation':conversion['legacy_projection']['time_calculation'] if conversion else None,
            'source_span_and_conversion_replayed':sourcecheck,'original_EGES_replay':replay,
            'complete_numeric_after_component_gates':all(finite(checked[k]) for k in DIRECT+EGES),
            'formal_eligible':False,'source_fact_inventory_assessment':'pending_separate_independent_review'})
        bindings += [parent.bind(x) for x in [p,*sorted(f for f in attempt.glob('*') if f.is_file())]]
    j.save(OUT/'per_answer.json',rows)
    summary={'status':'complete','planned_observations':5,'new_requests':5,'requests_snapshot':before,
        'technical_successes':sum(r['status']=='success' for r in rows),
        'source_span_and_conversion_replays':sum(r['source_span_and_conversion_replayed'] for r in rows),
        'complete_numeric_after_component_gates':sum(r['complete_numeric_after_component_gates'] for r in rows),
        'per_component_numeric':{k:sum(finite(r['component_gated_proposals'][k]) for r in rows) for k in DIRECT+EGES},
        'new_analysis_requests':0,'scientific_correctness_claimed':False,'human_expert_returns':0,
        'bound_observations':bindings}
    j.save(OUT/'completion_summary.json',summary)
    require(parent.request_count()==before,'analysis_requested_generation');record('analyze',new_requests=0)
    print(j.canonical({k:v for k,v in summary.items() if k!='bound_observations'}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run','analyze']);p.add_argument('--allow-local-calls',action='store_true');a=p.parse_args()
    if a.action=='run':require(a.allow_local_calls,'run_requires_allow_local_calls');asyncio.run(run())
    else:{'prepare':prepare,'preflight':preflight,'analyze':analyze}[a.action]()
