"""Independent v7 five-case development runner, initially code-only and unfrozen.

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
import cce_grounded_extraction_v7 as grounded
import evaluator_integrity as integrity
import cce_grounded_development_v6 as previous_batch

OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_development_v7'
RUN=OUT/'run';MODEL=model_probe.MODEL
PREVIOUS=previous_batch.OUT
FACT_INVENTORY=OUT.parent/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json'
FACT_CHECKER=OUT.parent/'fact_audit_checker_v6'
V7_FACT_CHECKER=OUT.parent/'fact_audit_checker_v7'
DEVELOPMENT_DECISION=OUT.parent/'grounded_v7_design_v1/root_decision.json'
PREVIOUS_DIAGNOSIS=OUT.parent/'grounded_v6_failure_diagnostics_v1/summary_5of5.json'
EXPECTED_STARTING_REQUESTS=227
CONTEXT_CONFIGURATION=OUT.parent/'grounded_v7_design_v1/context_configuration.json'
NUM_CTX=98304
BUDGET_AMENDMENT=OUT.parent/'grounded_v7_design_v1/budget_allocation_amendment.json'
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']
require=parent.require

class SourceBoundConversionError(ValueError):
    """Do not submit rejected raw source-bound JSON to the legacy parser."""

def previous_completed():
    """Preserve all prior v6 results; require actual completion, not improvement."""
    paths=[PREVIOUS/'completion_summary.json',PREVIOUS/'per_answer.json',
        PREVIOUS/'plan.json',PREVIOUS/'matrix.json',PREVIOUS/'expected_contract.json',
        PREVIOUS/'independent_fact_audit_v6/summary.json',
        PREVIOUS/'independent_fact_audit_v6/per_answer.json',
        PREVIOUS/'independent_fact_audit_v6/inventory_verification.json',
        FACT_CHECKER/'freeze.json',FACT_CHECKER/'software_probes.json',FACT_INVENTORY,
        Path(previous_batch.__file__),ROOT/'scripts/cce_audit_grounded_facts_v6.py',
        PREVIOUS_DIAGNOSIS,DEVELOPMENT_DECISION]
    require(all(p.exists() for p in paths),'previous_actual_analysis_and_fact_review_required_before_v7_freeze')
    summary=j.read(PREVIOUS/'completion_summary.json');facts=j.read(PREVIOUS/'independent_fact_audit_v6/summary.json')
    require(summary['status']=='experiment_complete_not_scientific_validation' and summary['planned_observations']==5,'previous_actual_five_not_complete')
    require(facts['status']=='complete' and facts['fixed_answers']==5,'previous_fact_review_not_complete')
    decision=j.read(DEVELOPMENT_DECISION)
    require(decision.get('status')=='selected_for_five_case_development' and
        decision.get('selected_by')=='root_agent' and decision.get('candidate_version')=='source_bound_extraction_v7',
        'v7_development_decision_not_ready')
    decision_bindings={str(Path(r['path']).resolve()):r['sha256'] for r in decision.get('bindings',[])}
    for path in [Path(grounded.__file__),PREVIOUS/'completion_summary.json',
                 PREVIOUS/'independent_fact_audit_v6/summary.json',PREVIOUS_DIAGNOSIS]:
        require(decision_bindings.get(str(path.resolve()))==j.filehash(path),'v7_decision_binding_missing_or_stale:'+str(path))
    matrix=j.read(PREVIOUS/'matrix.json');require(len(matrix)==5 and {c['anonymous_answer_id'] for c in matrix}==set(parent.IDS),'previous_fixed_five_changed')
    ledger={r['request_id']:r for r in j.ledger_rows(parent.LEDGER)}
    for cell in matrix:
        trial=PREVIOUS/'run/trials'/f"{cell['planned_trial_id']}.json"
        receipt=PREVIOUS/'run/attempts'/f"{cell['planned_trial_id']}_1/request_receipt.json"
        require(trial.exists() and receipt.exists(),'previous_actual_terminal_trial_missing')
        t=j.read(trial);r=j.read(receipt)
        require(t['status'] in ['success','failed'] and t['identity']==cell['identity'],'previous_trial_not_terminal')
        require(r==ledger[r['request_id']] and r['package_request_index']<=EXPECTED_STARTING_REQUESTS,'previous_request_receipt_mismatch')
        paths += [trial,receipt]
    for binding in summary.get('bound_observations',[]):
        require(j.filehash(binding['path'])==binding['sha256'],'previous_actual_artifact_changed')
    for entry in decision.get('bindings',[]):
        require(j.filehash(entry['path'])==entry['sha256'],'v7_root_decision_binding_changed:'+entry['path'])
    allocation=j.read(BUDGET_AMENDMENT)
    require(allocation['status']=='approved_before_v7_generation' and allocation['global_limit']==300
        and allocation['starting_requests']==227 and allocation['v7_new_requests']==5
        and allocation['max_total_if_all_phases_run']==294 and allocation['development_total']==40
        and allocation['previous_development_total']==35 and allocation['max_attempts']==1
        and allocation['after_E2_reserve']==41 and allocation['after_E4_reserve']==16
        and allocation['required_exact_reuse']==5 and allocation['unallocated_calls']==6
        and allocation['E2_new_requests']==21 and allocation['E4_new_requests']==25
        and allocation['primary_confirmation_new_requests']==16 and allocation['blind_subagent_assessments']==0
        and allocation['blind_answers']==0 and allocation['blind_replicates_per_answer']==0
        and allocation['last_development_iteration_in_this_allocation'] is True
        and allocation['optional_blind_execution_allowed'] is False
        and allocation['post_confirmation_blind_reactivation_allowed'] is False
        and allocation['unallocated_calls_authorize_retries'] is False
        and allocation['fresh30_fallback_allowed'] is False,'v7_budget_allocation_not_approved')
    for entry in [*[allocation[k] for k in ['original_budget','original_acceptance','previous_allocation']],
                  *allocation['completed_v6_evidence']]:
        require(j.filehash(entry['path'])==entry['sha256'],'v7_budget_dependency_changed:'+entry['path'])
        paths.append(Path(entry['path']))
    diagnosis=j.read(PREVIOUS_DIAGNOSIS)
    require(diagnosis['status']=='complete_five_terminal_source_diagnostics' and
        diagnosis['fixed_answers']==5 and len(diagnosis['traces'])==5,'previous_v6_all_five_diagnostics_required')
    for item in diagnosis['traces']:
        require(j.filehash(item['path'])==item['sha256'],'previous_v6_trace_changed')
        paths.append(Path(item['path']))
        for binding in j.read(item['path'])['input_bindings']:
            require(j.filehash(binding['path'])==binding['sha256'],'previous_v6_trace_input_changed')
            paths.append(Path(binding['path']))
    paths.append(BUDGET_AMENDMENT)
    return paths

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
    require(plan['planned_new_requests']==5 and plan['max_attempts']==1 and plan['starting_requests']==EXPECTED_STARTING_REQUESTS,'batch_scope_changed')
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
            transformed=[];errors=[];raw_returns=[]
            cell=next(x for x in j.read(OUT/'matrix.json') if x['anonymous_answer_id']==aid)
            attempt=RUN/'attempts'/f"{cell['planned_trial_id']}_1"
            class Teacher:
                model_name=teacher.model_name
                async def _acall(self,prompt):
                    require(not raw_returns and not transformed and not errors,'second_generation_for_same_case_forbidden')
                    # The unchanged outer runner adds its exact reference suffix.
                    result=await teacher._acall(expected[:-len(suffix)] if suffix else expected)
                    raw=result.get('content')
                    require(isinstance(raw,str),'provider_content_type')
                    raw_returns.append(raw)
                    # The provider's raw text and deterministic projection have
                    # different files and hashes, including on conversion failure.
                    (attempt/'raw_source_bound_content.txt').write_text(raw,encoding='utf8',newline='')
                    j.save(attempt/'raw_source_bound_receipt.json',{'raw_response_sha256':grounded.rawsha(raw),
                        'raw_text_file_sha256':j.filehash(attempt/'raw_source_bound_content.txt'),
                        'source_document_sha256':j.filehash(OUT/'source_documents'/f'{aid}.json'),
                        'raw_text_unchanged':True})
                    try:
                        conversion=grounded.convert(raw,doc)
                        require(conversion['raw_response_sha256']==grounded.rawsha(raw),'conversion_raw_hash_changed')
                        require(conversion['legacy_runner_payload']['scores']==integrity.parse_judge_object(raw)['scores'],'projection_changed_direct_scores')
                    except Exception as exc:
                        error={'stage':'SOURCE_BOUND_CONVERSION','type':type(exc).__name__,
                            'reason':str(exc),'raw_response_sha256':grounded.rawsha(raw),
                            'legacy_parser_fallback_permitted':False}
                        errors.append(error);j.save(attempt/'source_bound_conversion_error.json',error)
                        raise SourceBoundConversionError(str(exc)) from exc
                    transformed.append(conversion)
                    j.save(attempt/'source_bound_conversion.json',conversion)
                    j.save(attempt/'projected_legacy_payload.json',conversion['legacy_runner_payload'])
                    (attempt/'projected_legacy_content.txt').write_text(conversion['legacy_runner_content'],encoding='utf8')
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
            result['grounded_extraction_v7']={'conversion':transformed[0] if transformed else None,
                'conversion_errors':errors,'raw_return_modified':False,'legacy_input_explicitly_projected':bool(transformed),
                'raw_source_bound_content_sha256':grounded.rawsha(raw_returns[0]) if raw_returns else None,
                'raw_return_file':str(attempt/'raw_source_bound_content.txt') if raw_returns else None,
                'legacy_parser_fallback_used':False,
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
        require(all(value[k]==baseline[k] for k in ['files','demands','source_registry_sha256','scoring_version']),'original_science_or_demand_changed')
        value['source_bound_variant']={'version':'grounded_development_v7',
            'plan_sha256':j.filehash(OUT/'plan.json'),'runner_script_sha256':j.filehash(__file__),
            'grounded_script_sha256':j.filehash(grounded.__file__),'schema_sha256':j.filehash(OUT/'schema.json'),
            'raw_output_and_projection_separately_preserved':True}
        if check_contract:require(value==j.read(OUT/'expected_contract.json'),'runtime_contract_drift_before_generation')
        return value
    def adapter(public,api_type):
        api=original_adapter(public,api_type);previous=api.client.client.generate;previous_call=api._acall
        def capture(**kwargs):
            require(kwargs['format']==j.read(OUT/'schema.json'),'decoder_schema_drift')
            kwargs['options']['num_ctx']=public['num_ctx']
            require(kwargs['options'].get('temperature')==0 and kwargs['options'].get('num_predict')==8192,'actual_generation_settings_drift')
            ph=grounded.rawsha(kwargs['prompt']);matches=[r for r in j.read(OUT/'matrix.json') if r['prompt_raw_sha256']==ph]
            require(len(matches)==1,'actual_prompt_not_in_frozen_matrix');cell=matches[0]
            dest=RUN/'attempts'/f"{cell['planned_trial_id']}_1"
            require((dest/'request_receipt.json').exists(),'transport_payload_without_reserved_receipt')
            j.save(dest/'http_request_payload.json',kwargs)
            return previous(**kwargs)
        api.client.client.generate=capture
        async def call(prompt):
            try:return await previous_call(prompt)
            except Exception as exc:
                # Preserve completed malformed JSON as raw input to the strict
                # source-bound converter; it can never bypass that converter.
                recovered=parent.completed_json_failure_payload(api.last_response,exc,api.model_name,public['max_output_tokens'])
                if recovered is None:raise
                return recovered
        api._acall=call
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
    old.validate();model_probe.validate();previous_inputs=previous_completed();before=parent.request_count()
    require(before==EXPECTED_STARTING_REQUESTS,'development_v7_starts_after_completed_grounded_v6')
    context=j.read(CONTEXT_CONFIGURATION)
    require(context['selected_by']=='root_agent' and context['num_ctx']==NUM_CTX and
        context['actual_requests_before_and_after']==EXPECTED_STARTING_REQUESTS and
        context['new_generation_requests']==0,'prospective_context_configuration_required')
    fact_freeze=V7_FACT_CHECKER/'freeze.json';fact_probes=V7_FACT_CHECKER/'software_probes.json'
    require(fact_freeze.exists() and fact_probes.exists(),'v7_fact_checker_must_freeze_before_batch')
    frozen_checker=j.read(fact_freeze);checker_probes=j.read(fact_probes)
    require(frozen_checker['frozen_before_candidate_generation'] and checker_probes['status']=='pass','v7_fact_checker_not_ready')
    require(frozen_checker['grounded_module']['sha256']==j.filehash(grounded.__file__),'v7_fact_checker_grounded_module_drift')
    require(frozen_checker['checker_sha256']==j.filehash(ROOT/'scripts/cce_audit_grounded_facts_v7.py'),'v7_fact_checker_script_drift')
    source_plan=j.read(grounded.OUT/'plan.json')
    require(all(r['fits_configured_context'] for r in source_plan['matrix']) and
        source_plan['configured_num_ctx']==NUM_CTX,'candidate_context_does_not_fit')
    # Root reviews the completed source contract and synthetic probes before freeze.
    probes=grounded.OUT/'software_probes.json';require(probes.exists(),'grounded_software_probes_required')
    check=j.read(probes)
    require(check['status']=='pass' and check['new_model_requests']==0,'grounded_software_probes_not_passed')
    require(check['script_sha256']==j.filehash(grounded.__file__) and
        check['schema_sha256']==j.filehash(grounded.OUT/'schema.json') and
        check['plan_sha256']==j.filehash(grounded.OUT/'plan.json'),'grounded_probes_stale')
    for path,hash_value in source_plan['input_sha256'].items():
        require(j.filehash(path)==hash_value,'grounded_source_plan_binding_changed:'+path)
    fact=FACT_INVENTORY
    require(fact.exists(),'prespecified_source_fact_inventory_required')
    (OUT/'cases.json').write_bytes((old.OUT/'cases.json').read_bytes())
    config=j.read(model_probe.OUT/'model_config.json')
    require(len(config['models'])==1 and config['models'][0]['name']==MODEL,'original_model_config_changed')
    config['models'][0]['num_ctx']=NUM_CTX
    j.save(OUT/'model_config.json',config)
    (OUT/'schema.json').write_bytes((grounded.OUT/'schema.json').read_bytes())
    cases=j.read(OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==parent.IDS,'fixed_five_changed')
    inputs=[Path(__file__),Path(grounded.__file__),grounded.OUT/'plan.json',probes,fact,*previous_inputs,CONTEXT_CONFIGURATION,
        fact_freeze,fact_probes,ROOT/'scripts/cce_audit_grounded_facts_v7.py',
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
        require(len(prompt.encode('utf8'))+8192+256<=NUM_CTX,'context_bound_exceeded')
    plan={'status':'frozen_before_generation','version':'grounded_development_v7','created_utc':j.now(),
        'starting_requests':before,'planned_new_requests':5,'max_attempts':1,'repeats':1,'model':MODEL,
        'intervention':'Versioned v7 narrow candidate, whose exact prompt, registry and source-policy changes are recorded in the separately bound converter plan and root decision. The current proposal preserves the v6 shared schema and original arithmetic, native, coverage, direct-score, EGES, KB, demand and reference functions; no post-return repair is permitted. Context remains 98304, output8192, temperature0 and attempt1. This plan does not claim a single-factor effect or unchanged scientific-input availability.',
        'context_configuration':parent.bind(CONTEXT_CONFIGURATION),'num_ctx':NUM_CTX,
        'budget_allocation_amendment':parent.bind(BUDGET_AMENDMENT),
        'original_development_ceiling_25_preserved_as_historical_not_claimed_unchanged':True,
        'optional_blind_execution_allowed':False,'post_confirmation_blind_reactivation_allowed':False,
        'unallocated_calls':6,'unallocated_calls_authorize_retries':False,
        'v7_development_total_ceiling_under_prospective_allocation':40,
        'old_direct_scales_EGES_demands_and_references_unchanged':True,
        'changes_are_a_bundle_not_single_factor_ablation':True,
        'time_policy':'Use frozen v7 source projection; preserve unknown durations and named legacy comparison. No downstream score-formula repair.',
        'raw_returns_never_repaired_or_replaced':True,'synthetic_probes_not_experimental_success':True,
        'conversion_failure_has_no_legacy_JSON_fallback':True,
        'technical_executable_evidence_unresolved_and_complete_numeric_are_separate':True,
        'all_five_denominator_retained':True,'prior_all_development_failures_retained':True,
        'formal_eligible':False,'human_expert_returns':0,'next_stage_requires_observed_development_review':True,
        'frozen_inputs':[parent.bind(p) for p in dict.fromkeys(inputs)]}
    j.save(OUT/'plan.json',plan);validate();record('prepare',new_requests=0)
    print(j.canonical({'status':'frozen_five_development_cases','new_requests':0,'planned_new_requests':5}))

def preflight():
    validate();before=parent.request_count()
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    require(len(models)==1 and models[0]['name']==MODEL,'model_selection_changed')
    prior=j.read(model_probe.OUT/'expected_contract.json')['models'][0]['settings']
    current=models[0]['public'];require({**current,'format':'json','num_ctx':prior['num_ctx']}==prior and
        current['num_ctx']==NUM_CTX,'model_settings_changed_beyond_schema_and_prospective_context')
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
        'matrix_sha256':j.filehash(OUT/'matrix.json'),'same_model_as_previous_probe':True,
        'context_unchanged_from_v6':True,'num_ctx':NUM_CTX})
    record('preflight',new_requests=0);print(j.canonical({'status':'preflight_pass','planned_calls':5,'new_requests':0}))

def validate_preflight():
    validate();p=j.read(OUT/'preflight_verification.json')
    require(p['status']=='pass','preflight_not_passed')
    for key,path in [('plan_sha256',OUT/'plan.json'),('script_sha256',Path(__file__)),
        ('expected_contract_sha256',OUT/'expected_contract.json'),('matrix_sha256',OUT/'matrix.json')]:
        require(p[key]==j.filehash(path),'preflight_binding_changed:'+key)

async def run():
    validate_preflight();before=parent.request_count()
    review_path=OUT/'pre_generation_review/integration_review.json'
    require(review_path.exists(),'independent_pre_generation_integration_review_required')
    review=j.read(review_path)
    require(review['status']=='pass' and review['actual_model_requests']==0 and
        review['full_schema_actual_HTTP_serialization_pass'],'independent_integration_review_not_passed')
    reviewed={str(Path(r['path']).resolve()):r['sha256'] for r in review['protected_inputs']}
    for path in [Path(__file__),Path(grounded.__file__),OUT/'plan.json',OUT/'expected_contract.json',OUT/'matrix.json']:
        require(reviewed.get(str(path.resolve()))==j.filehash(path),'independent_integration_review_stale:'+str(path))
    matrix=j.read(OUT/'matrix.json');ids={c['planned_trial_id'] for c in matrix}
    own=[r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started' and r.get('trial_id') in ids]
    require(all(r['attempt']==1 for r in own) and len({r['trial_id'] for r in own})==len(own),'retries_or_duplicate_requests_forbidden')
    require(before==EXPECTED_STARTING_REQUESTS+len(own),'unplanned_requests_since_v7_freeze')
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

def evidence_state(conversion):
    if conversion is None:
        return {'state':'unavailable_due_to_technical_failure','unresolved':True,
            'projection_issues':None,'rejected_relations':None,'input_states':None,
            'fact_acceptance':'unavailable_no_valid_conversion'}
    projection=conversion['legacy_projection'];audit=conversion['source_audit']['resolved']
    issues=projection.get('projection_issues',[])
    rejected=[r for r in audit.get('relations',[]) if r.get('projection_allowed') is False]
    states=projection['component_input_state']
    missing=[k for k,v in states.items() if v not in ['available_provisional','original_question_and_KB_path_unchanged']]
    coverage=audit.get('coverage',{})
    incomplete={k:v for k,v in coverage.items() if
        (k in ['entities','time_operations','core_time_operations'] and v!='complete') or (k=='unresolved' and bool(v))}
    unresolved=bool(issues or rejected or missing or incomplete)
    return {'state':'evidence_unresolved' if unresolved else 'evidence_available_provisional_not_fact_confirmed',
        'unresolved':unresolved,'projection_issues':issues,'rejected_relations':rejected,
        'input_states':states,'affected_components':missing,'reported_incomplete_coverage':incomplete,
        'fact_acceptance':'pending_separate_independent_fact_review',
        'structural_pass_implies_fact_pass':False,'scientific_confirmation':False}

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
        payload_path=attempt/'http_request_payload.json'
        payload=j.read(payload_path) if payload_path.exists() else None
        if payload is not None:
            require(payload['format']==j.read(OUT/'schema.json') and payload['options']['num_ctx']==NUM_CTX,'actual_decoder_or_context_changed')
            require(payload['options']['temperature']==0 and payload['options']['num_predict']==8192,'actual_generation_settings_changed')
            require(grounded.rawsha(payload['prompt'])==cell['prompt_raw_sha256'],'actual_http_prompt_changed')
        conversion=(e.get('grounded_extraction_v7') or {}).get('conversion');raw=j.proposals(e)
        checked={k:None for k in raw};notes={};replay=None;sourcecheck=False
        raw_path=attempt/'raw_source_bound_content.txt';provider_path=attempt/'provider_response.json'
        provider=j.read(provider_path) if provider_path.exists() else None
        raw_content=raw_path.read_bytes().decode('utf8') if raw_path.exists() else None
        if raw_content is not None:
            require(provider is not None and provider.get('response')==raw_content,'saved_raw_provider_text_not_exact')
            require(j.read(attempt/'raw_source_bound_receipt.json')['raw_response_sha256']==grounded.rawsha(raw_content),'raw_sidecar_binding_changed')
        if t['status']=='success':
            require(conversion is not None and payload is not None and raw_content is not None,'successful_trial_missing_grounded_conversion_or_transport_evidence')
            doc=j.read(OUT/'source_documents'/f'{aid}.json')
            independently_converted=grounded.convert(raw_content,doc)
            require(independently_converted==conversion,'raw_to_projection_replay_failed')
            require(j.read(attempt/'source_bound_conversion.json')==conversion,'conversion_sidecar_changed')
            require(j.read(attempt/'projected_legacy_payload.json')==conversion['legacy_runner_payload'],'projection_payload_sidecar_changed')
            require((attempt/'projected_legacy_content.txt').read_text(encoding='utf8')==conversion['legacy_runner_content'],'projection_content_sidecar_changed')
            require(e['extraction']==conversion['legacy_projection']['extraction'],'original_runner_received_different_extraction')
            c=cases[t['case_id']];demand=registry.get(c['question_id'],c['specific_question'])
            meta=runner.QUESTION_META_KB[registry.questions[str(c['question_id'])]['question_id']]
            require(demand==e['user_preference_vector'],'demand_drift')
            replay=runner.calculate_effectiveness_score(e['quantitative_data'],demand,runner.MODEL_SPACE_SIGNED,e['extraction']['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(same(replay[k],raw[k]) for k in EGES),'original_EGES_replay_failed')
            require(e['legacy_diagnostics']['raw_teacher_scores']==conversion['legacy_runner_payload']['scores'],'direct_scores_modified')
            checked,notes=gate_components(raw,conversion,replay);sourcecheck=True
            j.save(OUT/'conversion_replays'/f'{aid}.json',independently_converted)
        elif (attempt/'source_bound_conversion_error.json').exists():
            error=j.read(attempt/'source_bound_conversion_error.json')
            require(error['legacy_parser_fallback_permitted'] is False,'legacy_fallback_after_conversion_failure')
            require(not (attempt/'projected_legacy_payload.json').exists(),'failed_conversion_has_projected_payload')
        technical=t['status']=='success' and sourcecheck
        evidence=evidence_state(conversion)
        numeric_count=sum(finite(checked[k]) for k in DIRECT+EGES)
        complete_numeric=numeric_count==len(DIRECT+EGES)
        outcome=('technical_failure' if not technical else 'technical_executable_all_components_NA' if numeric_count==0
            else 'technical_executable_partial_numeric' if not complete_numeric
            else 'technical_executable_complete_numeric_evidence_unresolved' if evidence['unresolved']
            else 'technical_executable_complete_numeric_pending_fact_review')
        rows.append({'anonymous_answer_id':aid,'case_id':t['case_id'],'trial_id':trial,'request_index':receipt['package_request_index'],
            'status':t['status'],'failure_stage':e.get('failure_stage'),
            'technical_executable':technical,'development_outcome':outcome,
            'evidence_state':evidence,'fact_acceptance':evidence['fact_acceptance'],
            'any_numeric_components_available':numeric_count>0,'numeric_component_count':numeric_count,
            'numeric_component_denominator':len(DIRECT+EGES),
            'full_HTTP_payload_recorded':payload is not None,
            'raw_source_bound_content_path':str(raw_path) if raw_content is not None else None,
            'raw_source_bound_content_sha256':grounded.rawsha(raw_content) if raw_content is not None else None,
            'projection_payload_path':str(attempt/'projected_legacy_payload.json') if conversion else None,
            'legacy_JSON_fallback_used':False,
            'grounded_conversion_errors':(e.get('grounded_extraction_v7') or {}).get('conversion_errors'),
            'raw_original_numeric_proposals':raw,'component_gated_proposals':checked,'component_gate_notes':notes,
            'projection_input_states':conversion['legacy_projection']['component_input_state'] if conversion else None,
            'extraction':e.get('extraction'),'time_calculation':conversion['legacy_projection']['time_calculation'] if conversion else None,
            'source_span_and_conversion_replayed':sourcecheck,'original_EGES_replay':replay,
            'complete_numeric_after_component_gates':complete_numeric,
            'formal_eligible':False,'source_fact_inventory_assessment':'pending_separate_independent_review'})
        bindings += [parent.bind(x) for x in [p,*sorted(f for f in attempt.glob('*') if f.is_file())]]
    j.save(OUT/'per_answer.json',rows)
    require(len(rows)==5 and {r['anonymous_answer_id'] for r in rows}==set(parent.IDS),'five_case_denominator_changed')
    summary={'status':'experiment_complete_not_scientific_validation','planned_observations':5,'actual_observations':5,
        'new_requests':len({r['request_index'] for r in rows}),'requests_snapshot':before,
        'technical_successes':sum(r['status']=='success' for r in rows),
        'technical_executable':sum(r['technical_executable'] for r in rows),
        'technical_failures':sum(not r['technical_executable'] for r in rows),
        'technical_executable_all_components_NA':sum(r['technical_executable'] and not r['any_numeric_components_available'] for r in rows),
        'evidence_unresolved':sum(r['evidence_state']['unresolved'] for r in rows),
        'technical_executable_but_evidence_unresolved':sum(r['technical_executable'] and r['evidence_state']['unresolved'] for r in rows),
        'fact_acceptance_status':'pending_separate_independent_fact_review',
        'fact_acceptance_not_inferred_from_technical_or_numeric':'Explicit source inventory review remains separate; unsupported relations and missing known evidence are not passes.',
        'any_numeric_components_available':sum(r['any_numeric_components_available'] for r in rows),
        'source_span_and_conversion_replays':sum(r['source_span_and_conversion_replayed'] for r in rows),
        'complete_numeric_after_component_gates':sum(r['complete_numeric_after_component_gates'] for r in rows),
        'per_component_numeric':{k:sum(finite(r['component_gated_proposals'][k]) for r in rows) for k in DIRECT+EGES},
        'all_component_denominators':5,'new_analysis_requests':0,'scientific_correctness_claimed':False,'human_expert_returns':0,
        'raw_and_projection_separate':True,'conversion_failure_legacy_fallback':False,
        'bound_observations':bindings}
    j.save(OUT/'completion_summary.json',summary)
    require(parent.request_count()==before,'analysis_requested_generation');record('analyze',new_requests=0)
    print(j.canonical({k:v for k,v in summary.items() if k!='bound_observations'}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run','analyze']);p.add_argument('--allow-local-calls',action='store_true');a=p.parse_args()
    if a.action=='run':require(a.allow_local_calls,'run_requires_allow_local_calls');asyncio.run(run())
    else:{'prepare':prepare,'preflight':preflight,'analyze':analyze}[a.action]()
