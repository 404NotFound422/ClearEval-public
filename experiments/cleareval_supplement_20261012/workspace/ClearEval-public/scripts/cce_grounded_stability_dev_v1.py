"""DRAFT: fixed five-source grounded E4; no automatic preparation or generation.

Thirty observations retain failed cells. Exact reuse of all five development
repeat-zero trials is allowed only after complete input/HTTP/configuration proof.
This orchestration does not change the frozen extractor or scientific functions.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, copy, importlib, io, json, shutil, sys, urllib.request
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_grounded_development_v2 as dev
import cce_grounded_extraction_v2 as grounded
import cce_output_contract_v1 as parent
import evaluator_integrity as integrity

DESIGN=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_stability_design_v1'
OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_stability_dev_v1'
RUN=OUT/'run'
LLAMA_CONFIG=ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1/local_config_snapshot.json'
MODELS=[dev.MODEL,'local_llama3_8b'];IDS=list(parent.IDS)
require=parent.require
BACKEND_VERSION='v2' # Import-only compatibility; selection explicitly chooses the version before freeze.
EXTRA_KEY='grounded_extraction_v2'
CONTEXT_BY_BACKEND={'v2':40960,'v3':40960,'v4':98304,'v5':98304,'v6':98304,'v7':98304}
NUM_CTX=CONTEXT_BY_BACKEND[BACKEND_VERSION]
CONTEXT_CONFIGURATION=OUT.parent/'grounded_v4_design_v1/context_configuration.json'
SELECTION=OUT.parent/'grounded_stability_selection_v1/selection.json'
ANALYZER=ROOT/'scripts/cce_analyze_grounded_stability_dev_v1.py'


SCIENCE_KEYS=('files','demands','source_registry_sha256','scoring_version')
BUDGET_AMENDMENT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_v5_design_v1/budget_allocation_amendment.json'

def same_science(left,right,reason='original_science_changed'):
    for key in SCIENCE_KEYS:
        require(key in left and key in right and left[key]==right[key],reason+':'+key)

def budget_allocation():
    """Dated root allocation; original <=25-dev criterion is explicitly amended."""
    value=j.read(BUDGET_AMENDMENT)
    expected={'starting_requests':217,'global_limit':300,'original_development_total':25,
        'development_total':30,'v5_new_requests':5,'E2_new_requests':21,'E4_new_requests':25,
        'primary_confirmation_new_requests':16,'blind_subagent_assessments':16,
        'required_exact_reuse':5,'after_E4_reserve':32,'max_attempts':1,'max_total_if_all_phases_run':300}
    require(value.get('status')=='approved_before_v5_generation' and value.get('selected_by')=='root_agent'
        and bool(value.get('created_utc')),'root_dated_v5_allocation_required')
    require(all(type(value.get(k)) is int and value[k]==v for k,v in expected.items()),'v5_allocation_numbers_changed')
    require(value.get('fresh30_fallback_allowed') is False and value.get('technical_scientific_acceptance_unchanged') is True
        and bool(value.get('original_G01_development_clause_deviation')),'v5_allocation_deviation_or_stop_policy_missing')
    for key in ['original_budget','original_acceptance','reuse_software_proof']:
        entry=value[key];require(j.filehash(entry['path'])==entry['sha256'],'allocation_binding_changed:'+key)
    return value

def allocation_dependencies():
    if BACKEND_VERSION=='v7':
        value=v7_budget_allocation()
        return [V7_BUDGET_AMENDMENT,*[Path(value[k]['path']) for k in ['original_budget','original_acceptance','previous_allocation']],
                *[Path(item['path']) for item in value['completed_v6_evidence']]]
    if BACKEND_VERSION=='v6':
        value=v6_budget_allocation()
        return [V6_BUDGET_AMENDMENT,*[Path(value[k]['path']) for k in ['original_budget','original_acceptance','previous_allocation']],
                *[Path(item['path']) for item in value['completed_v5_evidence']]]
    value=budget_allocation()
    return [BUDGET_AMENDMENT,*[Path(value[k]['path']) for k in ['original_budget','original_acceptance','reuse_software_proof']]]

def v5_budget_guard(phase,used,remaining_new,reused=None):
    value=budget_allocation();require(phase in ['E2','E4'],'unknown_allocation_phase')
    cap=value[phase+'_new_requests'];reserve=value['after_E4_reserve']+(value['E4_new_requests'] if phase=='E2' else 0)
    require(type(used) is int and type(remaining_new) is int and 0<=remaining_new<=cap,'v5_request_cap_exceeded')
    if phase=='E4':require(reused==value['required_exact_reuse'],'v5_requires_five_exact_reuses_no_fresh30_fallback')
    require(used+remaining_new+reserve<=value['global_limit'],'v5_confirmation_reserve_would_be_consumed')
    return {'phase':phase,'max_new_requests':cap,'reserved_after_phase':reserve,
        'global_limit':300,'required_exact_reuse':5 if phase=='E4' else 0,'fresh30_fallback_allowed':False,
        'budget_allocation_amendment':parent.bind(BUDGET_AMENDMENT)}

def verify_selected_dev_allocation():
    allocation=v7_budget_allocation() if BACKEND_VERSION=='v7' else v6_budget_allocation() if BACKEND_VERSION=='v6' else budget_allocation();plan=j.read(dev.OUT/'plan.json')
    binding=parent.bind(selected_allocation_path())
    require(plan.get('budget_allocation_amendment')==binding and binding in plan.get('frozen_inputs',[]),
        'selected_dev_did_not_freeze_allocation_before_generation')
    from datetime import datetime
    require(datetime.fromisoformat(allocation['created_utc'])<=datetime.fromisoformat(plan['created_utc']),
        'allocation_not_prospective_to_selected_plan')


V6_BUDGET_AMENDMENT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_v6_design_v1/budget_allocation_amendment.json'

def selected_allocation_path():
    return V7_BUDGET_AMENDMENT if BACKEND_VERSION=='v7' else V6_BUDGET_AMENDMENT if BACKEND_VERSION=='v6' else BUDGET_AMENDMENT

def v6_budget_allocation():
    value=j.read(V6_BUDGET_AMENDMENT)
    expected={'starting_requests':222,'global_limit':300,'original_development_total':25,
        'previous_development_total':30,'development_total':35,'v6_new_requests':5,
        'E2_new_requests':21,'E4_new_requests':25,'primary_confirmation_new_requests':16,
        'blind_subagent_assessments':8,'blind_answers':8,'blind_replicates_per_answer':1,
        'required_exact_reuse':5,'after_E2_reserve':49,'after_E4_reserve':24,
        'max_attempts':1,'max_total_if_all_phases_run':297,'unallocated_calls':3}
    require(value.get('status')=='approved_before_v6_generation' and value.get('selected_by')=='root_agent'
        and bool(value.get('created_utc')),'root_dated_v6_allocation_required')
    require(all(type(value.get(k)) is int and value[k]==v for k,v in expected.items()),'v6_allocation_numbers_changed')
    require(value.get('fresh30_fallback_allowed') is False and value.get('unallocated_calls_authorize_retries') is False
        and value.get('technical_scientific_acceptance_unchanged') is True
        and bool(value.get('original_G01_development_clause_deviation'))
        and bool(value.get('optional_blind_design_deviation')),'v6_allocation_deviation_or_stop_policy_missing')
    for item in [*[value[k] for k in ['original_budget','original_acceptance','previous_allocation']],
                 *value['completed_v5_evidence']]:
        require(j.filehash(item['path'])==item['sha256'],'v6_allocation_binding_changed:'+item['path'])
    return value

def v6_budget_guard(phase,used,remaining_new,reused=None):
    value=v6_budget_allocation();require(phase in ['E2','E4'],'unknown_allocation_phase')
    cap=value[phase+'_new_requests'];reserve=value['after_'+phase+'_reserve']
    require(type(used) is int and type(remaining_new) is int and 0<=remaining_new<=cap,'v6_request_cap_exceeded')
    if phase=='E4':require(reused==5,'v6_requires_five_exact_reuses_no_fresh30_fallback')
    # The three unallocated calls cannot be silently consumed by this schedule.
    require(used+remaining_new+reserve<=value['max_total_if_all_phases_run'],'v6_reserved_or_unallocated_calls_would_be_consumed')
    return {'phase':phase,'max_new_requests':cap,'reserved_after_phase':reserve,'global_limit':300,
        'allocated_end_ceiling':297,'unallocated_calls':3,'unallocated_calls_authorize_retries':False,
        'required_exact_reuse':5 if phase=='E4' else 0,'fresh30_fallback_allowed':False,
        'budget_allocation_amendment':parent.bind(V6_BUDGET_AMENDMENT)}


V7_BUDGET_AMENDMENT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_v7_design_v1/budget_allocation_amendment.json'

def v7_budget_allocation():
    value=j.read(V7_BUDGET_AMENDMENT)
    expected={'starting_requests':227,'global_limit':300,'original_development_total':25,
        'previous_development_total':35,'development_total':40,'v7_new_requests':5,
        'E2_new_requests':21,'E4_new_requests':25,'primary_confirmation_new_requests':16,
        'blind_subagent_assessments':0,'blind_answers':0,'blind_replicates_per_answer':0,
        'required_exact_reuse':5,'after_E2_reserve':41,'after_E4_reserve':16,
        'max_attempts':1,'max_total_if_all_phases_run':294,'unallocated_calls':6}
    require(value.get('status')=='approved_before_v7_generation' and value.get('selected_by')=='root_agent'
        and bool(value.get('created_utc')),'root_dated_v7_allocation_required')
    require(all(type(value.get(k)) is int and value[k]==v for k,v in expected.items()),'v7_allocation_numbers_changed')
    require(value.get('fresh30_fallback_allowed') is False and value.get('unallocated_calls_authorize_retries') is False
        and value.get('technical_scientific_acceptance_unchanged') is True
        and value.get('optional_blind_execution_allowed') is False
        and value.get('post_confirmation_blind_reactivation_allowed') is False
        and value.get('last_development_iteration_in_this_allocation') is True
        and bool(value.get('original_G01_development_clause_deviation'))
        and bool(value.get('optional_blind_design_deviation')),'v7_allocation_deviation_or_stop_policy_missing')
    for item in [*[value[k] for k in ['original_budget','original_acceptance','previous_allocation']],
                 *value['completed_v6_evidence']]:
        require(j.filehash(item['path'])==item['sha256'],'v7_allocation_binding_changed:'+item['path'])
    return value

def v7_budget_guard(phase,used,remaining_new,reused=None):
    value=v7_budget_allocation();require(phase in ['E2','E4'],'unknown_allocation_phase')
    cap=value[phase+'_new_requests'];reserve=value['after_'+phase+'_reserve']
    require(type(used) is int and type(remaining_new) is int and 0<=remaining_new<=cap,'v7_request_cap_exceeded')
    if phase=='E4':require(reused==5,'v7_requires_five_exact_reuses_no_fresh30_fallback')
    require(used+remaining_new+reserve<=value['max_total_if_all_phases_run'],'v7_reserved_or_unallocated_calls_would_be_consumed')
    return {'phase':phase,'max_new_requests':cap,'reserved_after_phase':reserve,'global_limit':300,
        'allocated_end_ceiling':294,'unallocated_calls':6,'unallocated_calls_authorize_retries':False,
        'optional_blind_execution_allowed':False,'post_confirmation_blind_reactivation_allowed':False,
        'required_exact_reuse':5 if phase=='E4' else 0,'fresh30_fallback_allowed':False,
        'budget_allocation_amendment':parent.bind(V7_BUDGET_AMENDMENT)}

def selected_budget_guard(phase,used,remaining_new,reused=None):
    helper=v7_budget_guard if BACKEND_VERSION=='v7' else v6_budget_guard if BACKEND_VERSION=='v6' else v5_budget_guard
    return helper(phase,used,remaining_new,reused)

def configure_context(version,primary_config=None):
    global NUM_CTX,CONTEXT_CONFIGURATION
    require(version in CONTEXT_BY_BACKEND,'explicit_supported_backend_context_required')
    expected=CONTEXT_BY_BACKEND[version]
    if version in ['v4','v5','v6','v7']:
        CONTEXT_CONFIGURATION=ROOT/'artifacts/cce_validation/optimizer_20261010'/f'grounded_{version}_design_v1/context_configuration.json'
    if primary_config is not None:
        rows=primary_config['models'];require(len(rows)==1 and rows[0]['name']==MODELS[0],'selected_primary_model_changed')
        require(rows[0]['num_ctx']==expected,'selected_primary_context_changed')
    if version in ['v4','v5','v6','v7']:
        meta=j.read(CONTEXT_CONFIGURATION)
        require(meta['selected_by']=='root_agent' and meta['num_ctx']==expected and meta['new_generation_requests']==0,'prospective_selected_context_required')
        require(getattr(dev,'NUM_CTX',None)==expected and getattr(grounded,'CONFIGURED_NUM_CTX',None)==expected,'selected_module_context_mismatch')
    NUM_CTX=expected;return expected

def combined_model_config(primary_config):
    """Only the explicitly selected v4 capacity changes; all other bytes' values survive."""
    config=copy.deepcopy(primary_config);configure_context(BACKEND_VERSION,config)
    original=next(x for x in j.read(LLAMA_CONFIG)['models'] if x['name']==MODELS[1]);secondary=copy.deepcopy(original)
    if BACKEND_VERSION in ['v4','v5','v6','v7']:secondary['num_ctx']=NUM_CTX
    require(secondary['num_ctx']==NUM_CTX,'two_model_families_must_share_selected_context')
    require({k:v for k,v in secondary.items() if k!='num_ctx'}=={k:v for k,v in original.items() if k!='num_ctx'},'second_model_changed_beyond_explicit_context')
    config['models'].append(secondary)
    if BACKEND_VERSION in ['v4','v5','v6','v7']:
        metadata=j.read(CONTEXT_CONFIGURATION)
        for row in config['models']:
            recorded=next(x for x in metadata['models'] if x['local_model_name']==row['model_name'])
            require(row['model_digest']==recorded['digest'] and min(recorded['native_context_metadata'].values())>=NUM_CTX,'prospective_native_context_or_digest_mismatch')
        require(metadata['models'][1]['details']['quantization_level']=='F16','prospective_second_family_not_F16')
    return config

def record(action,**details):
    path=OUT/'actual_commands.json';rows=j.read(path) if path.exists() else []
    rows.append({'utc':j.now(),'action':action,'argv':[sys.executable,*sys.argv],'cwd':str(Path.cwd()),
        'script_sha256':j.filehash(__file__),**details});j.save(path,rows)

def selected_backend():
    """Internal root choice after complete five-case facts; never self-promote."""
    global dev,grounded,BACKEND_VERSION,EXTRA_KEY
    require(SELECTION.exists(),'root_E4_candidate_selection_missing')
    chosen=j.read(SELECTION)
    require(chosen.get('status')=='selected_for_development_E4' and chosen.get('approved_for_e4') is True
        and chosen.get('selected_by')=='root_agent' and bool(chosen.get('decision_reason')),'root_E4_candidate_not_selected')
    version=chosen.get('backend_version');require(version in CONTEXT_BY_BACKEND,'unsupported_selected_backend')
    bound={str(Path(r['path']).resolve()):r['sha256'] for r in chosen.get('bindings',[])}
    scripts=[ROOT/'scripts'/f'cce_grounded_development_{version}.py',ROOT/'scripts'/f'cce_grounded_extraction_{version}.py']
    for path in scripts:require(bound.get(str(path.resolve()))==j.filehash(path),'selected_backend_script_missing_or_stale:'+str(path))
    dev=importlib.import_module(f'cce_grounded_development_{version}')
    grounded=importlib.import_module(f'cce_grounded_extraction_{version}')
    require(Path(dev.grounded.__file__).resolve()==Path(grounded.__file__).resolve() and dev.MODEL==MODELS[0],'selected_development_backend_mismatch')
    BACKEND_VERSION=version;EXTRA_KEY='grounded_extraction_'+version
    configure_context(version,j.read(dev.OUT/'model_config.json'))
    checker=ROOT/'scripts'/f'cce_audit_grounded_facts_{version}.py'
    facts=dev.OUT/f'independent_fact_audit_{version}'
    paths=[*scripts,checker,*[grounded.OUT/n for n in ['schema.json','plan.json','software_probes.json']],
        *[dev.OUT/n for n in ['plan.json','expected_contract.json','matrix.json','completion_summary.json','per_answer.json','model_config.json']],
        facts/'summary.json',facts/'per_answer.json']
    if version in ['v4','v5','v6','v7']:paths.append(CONTEXT_CONFIGURATION)
    if version in ['v5','v6','v7']:
        paths.extend(allocation_dependencies());verify_selected_dev_allocation()
    for path in paths:require(path.exists() and bound.get(str(path.resolve()))==j.filehash(path),'selected_candidate_evidence_missing_or_stale:'+str(path))
    dev_summary=j.read(dev.OUT/'completion_summary.json')
    require(dev_summary['actual_observations']==5,'five_development_observations_required')
    fact_summary=j.read(facts/'summary.json')
    require(fact_summary['status']=='complete' and fact_summary['fixed_answers']==5,'complete_five_fact_review_required')
    require(Path(fact_summary['batch_out']).resolve()==dev.OUT.resolve(),'fact_review_is_not_selected_development_batch')
    for item in [*dev_summary.get('bound_observations',[]),*fact_summary.get('inputs',[])]:
        require(j.filehash(item['path'])==item['sha256'],'selected_fact_or_actual_observation_source_changed')
        paths.append(Path(item['path']))
    source_matrix=j.read(dev.OUT/'matrix.json');require(len(source_matrix)==5 and {r['anonymous_answer_id'] for r in source_matrix}==set(IDS),'selected_fixed_five_changed')
    for cell in source_matrix:
        path=dev.RUN/'trials'/f"{cell['planned_trial_id']}.json"
        trial=j.read(path);require(trial['status'] in ['success','failed'] and trial['identity']==cell['identity'],'selected_development_not_terminal')
    return chosen,paths

def sequence_gate():
    """Root binds actual terminal E2; structural/numeric success is not required."""
    path=OUT/'pre_generation_review/sequence_gate.json';require(path.exists(),'root_E2_terminal_sequence_gate_missing')
    gate=j.read(path)
    require(gate.get('status')=='e2_terminal_verified' and gate.get('selected_by')=='root_agent'
        and gate.get('selection_sha256')==j.filehash(SELECTION),'root_E2_sequence_gate_invalid')
    bindings=gate['e2_artifacts']
    for item in bindings.values():require(j.filehash(item['path'])==item['sha256'],'E2_terminal_binding_changed')
    summary=j.read(bindings['completion_summary']['path']);rows=j.read(bindings['per_answer']['path'])
    matrix=j.read(bindings['matrix']['path']);contract=j.read(bindings['expected_contract']['path'])
    require(summary['actual_terminal_answers']==21 and summary['planned_pairs']==15 and len(rows)==len(matrix)==21,'E2_21_fulltexts_15_pairs_not_terminal')
    require(all(r['status'] in ['success','failed'] for r in rows),'E2_nonterminal_observation')
    require({r['trial_id'] for r in rows}=={r['planned_trial_id'] for r in matrix},'E2_terminal_matrix_mismatch')
    variant=contract['source_bound_variant']
    require(variant['grounded_script_sha256']==j.filehash(grounded.__file__) and variant['schema_sha256']==j.filehash(grounded.OUT/'schema.json'),'E2_different_selected_backend')
    current=j.read(OUT/'expected_contract.json');q=next(m for m in current['models'] if m['name']==MODELS[0])
    require(contract['models']==[q],'E2_model_changed')
    same_science(contract,current,'E2_original_science_changed')
    for item in summary.get('bound_actual_artifacts',[]):require(j.filehash(item['path'])==item['sha256'],'E2_actual_artifact_changed')
    return gate,path

def args(allow=False):
    decision=j.read(OUT/'reuse_decision.json')
    if BACKEND_VERSION in ['v5','v6','v7']:
        require(decision.get('reuse_all_five') is True and decision.get('planned_new_requests')==25,
            'v5_requires_five_exact_reuses_and_max25_new')
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'model_config.json',
        models=MODELS,question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None,ledger=parent.LEDGER,total_budget=300,external_request_count=0,
        max_calls=decision['planned_new_requests'],max_attempts=1,repeats=3,temperature=0.,
        max_output_tokens=8192,timeout_seconds=600,allow_api=allow)

def scientific_contract(base):
    """Keep the original configuration identity; batch provenance lives outside it."""
    source=j.read(dev.OUT/'expected_contract.json')
    for key in ['files','demands','source_registry_sha256','scoring_version']:
        require(base[key]==source[key],'unchanged_science_required:'+key)
    base['source_bound_variant']=copy.deepcopy(source['source_bound_variant'])
    require({**base,'models':[]}=={**source,'models':[]},'non_model_scientific_contract_drift')
    # This source configuration object identifies the evaluated policy. It does
    # not claim that the new orchestration source file equals the old runner.
    if not j.read(OUT/'reuse_decision.json')['reuse_all_five']:
        require(BACKEND_VERSION not in ['v5','v6','v7'],'v5_fresh30_namespace_forbidden')
        base['observation_namespace']='grounded_stability_development_v1_fresh30'
    return base

@contextlib.contextmanager
def wrapper(check_contract=False):
    previous_runtime,previous_contract=j.runtime,j.contract
    previous_models,previous_adapter,previous_reserve=j.model_configs,j.make_adapter,j.reserve_request
    cases=j.read(OUT/'cases.json')['cases'];lookup={dev.casekey(c):c for c in cases}
    require(len(lookup)==5,'five_distinct_fulltext_inputs_required')
    active={'cell':None,'request':None};restore=[]
    def reserve(a,trial,attempt,judge):
        matrix=j.read(OUT/'matrix.json');matches=[c for c in matrix if c['planned_trial_id']==trial]
        require(len(matches)==1 and attempt==1,'unplanned_trial_or_retry')
        require(matches[0]['judge']==judge,'reserved_judge_not_planned_model')
        require(matches[0]['disposition']=='new_request_planned','reused_observation_must_not_reserve')
        require(active['request'] is None,'second_request_in_one_evaluation_forbidden')
        if BACKEND_VERSION in ['v5','v6','v7']:selected_budget_guard('E4',parent.request_count(),1,reused=5)
        result=previous_reserve(a,trial,attempt,judge)
        active.update(cell=matches[0],request=result);return result
    def current_attempt(case,model_name):
        cell=active['cell'];require(cell is not None,'no_actual_reserved_trial_for_conversion')
        require(cell['anonymous_answer_id']==case['anonymous_answer_id'] and
            cell['model_name']==model_name,'active_trial_case_or_model_mismatch')
        return RUN/'attempts'/f"{cell['planned_trial_id']}_1"
    def runtime(a):
        runner,api,registry=previous_runtime(a);original=runner.evaluate_response_with_teacher
        restore.append((runner,original))
        async def evaluate(teacher,question,answer,space,meta,template):
            active.update(cell=None,request=None)
            c=lookup[(int(meta['question_id']),question,answer)];aid=c['anonymous_answer_id']
            doc=j.read(OUT/'source_documents'/f'{aid}.json')
            require(doc['source_id']==grounded.source_id_for_case(c) and grounded.rawsha(answer)==doc['answer_sha256'],'runtime_source_identity_changed')
            prompt_path=OUT/'prompts'/f'{aid}.txt'
            prompt_bindings=[entry for entry in j.read(OUT/'plan.json')['frozen_inputs']
                if Path(entry['path']).resolve()==prompt_path.resolve()]
            require(len(prompt_bindings)==1 and j.filehash(prompt_path)==prompt_bindings[0]['sha256'],
                'runtime_frozen_prompt_hash_changed')
            # Prompt reproduction runs synchronously during prepare. Calling
            # make_prompt here would enter helper.asyncio.run inside this loop.
            expected=prompt_path.read_text(encoding='utf8')
            suffix=parent.v2.reference_suffix(c);require(expected.endswith(suffix),'reference_suffix_changed')
            converted=[];errors=[];raw_returns=[]
            class Teacher:
                model_name=teacher.model_name
                async def _acall(self,prompt):
                    require(not raw_returns and not errors and not converted,'second_generation_for_one_cell')
                    result=await teacher._acall(expected[:-len(suffix)] if suffix else expected)
                    raw=result.get('content');require(isinstance(raw,str),'provider_content_type')
                    dest=current_attempt(c,teacher.model_name);raw_returns.append(raw)
                    (dest/'raw_source_bound_content.txt').write_text(raw,encoding='utf8',newline='')
                    j.save(dest/'raw_source_bound_receipt.json',{'raw_response_sha256':grounded.rawsha(raw),
                        'raw_text_file_sha256':j.filehash(dest/'raw_source_bound_content.txt'),
                        'source_document_sha256':j.filehash(OUT/'source_documents'/f'{aid}.json'),'raw_text_unchanged':True})
                    try:
                        value=grounded.convert(raw,doc)
                        require(value['raw_response_sha256']==grounded.rawsha(raw),'conversion_raw_hash_changed')
                        require(value['legacy_runner_payload']['scores']==integrity.parse_judge_object(raw)['scores'],'conversion_changed_scores')
                    except Exception as exc:
                        error={'stage':'SOURCE_BOUND_CONVERSION','type':type(exc).__name__,'reason':str(exc),
                            'raw_response_sha256':grounded.rawsha(raw),'legacy_parser_fallback_permitted':False}
                        errors.append(error);j.save(dest/'source_bound_conversion_error.json',error)
                        raise dev.SourceBoundConversionError(str(exc)) from exc
                    converted.append(value);j.save(dest/'source_bound_conversion.json',value)
                    j.save(dest/'projected_legacy_payload.json',value['legacy_runner_payload'])
                    (dest/'projected_legacy_content.txt').write_text(value['legacy_runner_content'],encoding='utf8')
                    return {**result,'content':value['legacy_runner_content'],'raw_content':raw,
                        'metadata':{**result.get('metadata',{}),'explicit_source_bound_projection':True,
                            'raw_model_content_sha256':grounded.rawsha(raw),
                            'projected_content_sha256':grounded.rawsha(value['legacy_runner_content'])}}
            result=await original(Teacher(),question,answer,space,meta,template)
            if errors:
                result['upstream_status_before_grounded_gate']=result.get('technical_status')
                result.update(technical_status='FAILED',failure_stage='SOURCE_BOUND_CONVERSION',
                    _error='Source-bound contract rejected the raw return: '+errors[0]['reason'],
                    _error_type=errors[0]['type'],cce_eligible=False,official_scores=None)
            dest=current_attempt(c,teacher.model_name) if active['cell'] else None
            result[EXTRA_KEY]={'conversion':converted[0] if converted else None,
                'conversion_errors':errors,'raw_return_modified':False,'legacy_input_explicitly_projected':bool(converted),
                'raw_source_bound_content_sha256':grounded.rawsha(raw_returns[0]) if raw_returns else None,
                'raw_return_file':str(dest/'raw_source_bound_content.txt') if raw_returns else None,
                'legacy_parser_fallback_used':False,'plan_sha256':j.filehash(OUT/'plan.json'),
                'extraction_configuration_plan_sha256':j.filehash(dev.OUT/'plan.json'),
                'orchestration_script_sha256':j.filehash(__file__),'scientific_confirmation':False}
            return result
        runner.evaluate_response_with_teacher=evaluate;return runner,api,registry
    def models(a):
        values=previous_models(a)
        for row in values:
            require(row['public']['transport_kind']=='ollama_loopback','local_only')
            row['public']['format']=j.read(OUT/'schema.json')
        return values
    def contract(a,runner,registry,models):
        value=scientific_contract(previous_contract(a,runner,registry,models))
        if check_contract:require(value==j.read(OUT/'expected_contract.json'),'runtime_contract_drift')
        return value
    def adapter(public,api_type):
        api=previous_adapter(public,api_type);generate=api.client.client.generate;call=api._acall
        def capture(**kwargs):
            cell=active['cell'];require(cell is not None and active['request'] is not None,'HTTP_without_actual_reserved_trial')
            require(kwargs['format']==j.read(OUT/'schema.json'),'decoder_schema_drift')
            kwargs['options']['num_ctx']=public['num_ctx']
            require(kwargs==j.read(OUT/'expected_http_payloads'/f"{cell['anonymous_answer_id']}_{cell['judge']}.json"),'actual_full_HTTP_payload_drift')
            dest=RUN/'attempts'/f"{cell['planned_trial_id']}_1"
            require(j.read(dest/'request_receipt.json')==active['request'],'request_receipt_not_actual_active_cell')
            j.save(dest/'http_request_payload.json',kwargs);return generate(**kwargs)
        api.client.client.generate=capture
        async def caught(prompt):
            try:return await call(prompt)
            except Exception as exc:
                recovered=parent.completed_json_failure_payload(api.last_response,exc,api.model_name,public['max_output_tokens'])
                if recovered is None:raise
                return recovered
        api._acall=caught;return api
    j.runtime,j.contract,j.model_configs,j.make_adapter,j.reserve_request=runtime,contract,models,adapter,reserve
    try:yield
    finally:
        for runner,original in reversed(restore):runner.evaluate_response_with_teacher=original
        j.runtime,j.contract,j.model_configs,j.make_adapter,j.reserve_request=previous_runtime,previous_contract,previous_models,previous_adapter,previous_reserve

def expected_payload(public,prompt):
    """Exercise the existing serializer with a stub, not a network request."""
    require(public['num_ctx']==NUM_CTX,'serialized_model_context_mismatch')
    api=j.make_adapter(public,None);captured=[]
    def stub(**kwargs):
        kwargs['options']['num_ctx']=public['num_ctx'];captured.append(copy.deepcopy(kwargs))
        return {'done':True,'done_reason':'stop','response':'{}','model':'SYNTHETIC_SERIALIZATION_ONLY','eval_count':1,'prompt_eval_count':1}
    api.client.client.generate=stub;api.client._generate(prompt)
    require(len(captured)==1,'one_serialized_HTTP_payload_required');return captured[0]

def verify_reuse(cases,contract):
    """All-or-none, status-blind proof: failures are not excluded or retried."""
    old=j.read(dev.OUT/'expected_contract.json');q=next(m for m in contract['models'] if m['name']==dev.MODEL)
    one={**contract,'models':[q]};require(one==old,'Qwen_configuration_not_exactly_equal')
    ledger={r['request_id']:r for r in j.ledger_rows(parent.LEDGER)}
    original=j.read(dev.OUT/'matrix.json');require(len(original)==5,'original_five_required')
    rows=[]
    for case in cases:
        aid=case['anonymous_answer_id'];matches=[c for c in original if c['anonymous_answer_id']==aid]
        require(len(matches)==1,'original_AID_mapping_not_unique');cell=matches[0]
        expected={'case_id':case['case_id'],'input_sha256':case['input_sha256'],'judge':dev.MODEL,'repeat_index':0,'contract_sha256':j.digest(one)}
        require(cell['identity']==expected,'original_exact_trial_identity_changed')
        tp=dev.RUN/'trials'/f"{cell['planned_trial_id']}.json";t=j.read(tp)
        require(t['identity']==expected and t['trial_id']==j.digest(expected),'source_trial_identity_changed')
        require(t['status'] in ['success','failed'] and t['attempt']==1 and t['actual_api_request_made'],'original_terminal_one_request_required')
        require(t['full_text_input_sha256']==case['input_sha256'] and t['references_sha256']==j.digest(case['references']),'full_input_or_reference_changed')
        require(t['pipeline_config_sha256']==j.digest({**one,'models':[]}),'original_science_hash_changed')
        attempt=dev.RUN/'attempts'/f"{t['trial_id']}_1";receipt=j.read(attempt/'request_receipt.json')
        require(receipt==ledger.get(receipt['request_id']) and receipt['trial_id']==t['trial_id'],'old_receipt_not_in_ledger')
        require(receipt.get('event')=='request_started' and receipt.get('attempt')==1 and receipt.get('model')==dev.MODEL,
            'old_receipt_not_same_single_model_attempt')
        require(j.read(attempt/'result.json')==t,'attempt_trial_disagreement')
        payload=j.read(attempt/'http_request_payload.json')
        require(payload==j.read(OUT/'expected_http_payloads'/f'{aid}_{dev.MODEL}.json'),'complete_HTTP_payload_not_identical')
        require(payload['prompt']==(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8'),'exact_transmitted_prompt_changed')
        require(j.filehash(attempt/'prompt.txt')==t['prompt_sha256'],'original_prompt_hash_changed')
        require((attempt/'prompt.txt').read_text(encoding='utf8')==payload['prompt'],'prompt_sidecar_payload_disagreement')
        require(j.read(dev.OUT/'source_documents'/f'{aid}.json')==j.read(OUT/'source_documents'/f'{aid}.json'),'source_document_changed')
        provider_path=attempt/'provider_response.json';raw_path=attempt/'raw_source_bound_content.txt'
        doc=j.read(OUT/'source_documents'/f'{aid}.json');e=t.get('evaluation') or {};existing=e.get(EXTRA_KEY) or {}
        missing_return=not provider_path.exists() and not raw_path.exists()
        if missing_return:
            # A request-stage failure is an observation, not a fabricated return.
            # Complete intended HTTP payload, frozen inputs and actual receipt
            # have already passed the common checks above.
            generation=e.get('teacher_generation') or {};error=j.read(attempt/'provider_error.json')
            log=j.read(attempt/'runner_log.json')
            require(t['status']=='failed' and e.get('technical_status')=='FAILED' and
                e.get('failure_stage')=='TEACHER_GENERATION' and generation.get('technical_status')=='FAILED' and
                generation.get('failure_code')=='PROVIDER_EXCEPTION','no_return_not_explicit_provider_failure')
            require(bool(error.get('error_type')) and error['error_type']==generation.get('error_type')==e.get('_error_type'),
                'provider_failure_error_identity_mismatch')
            require(log.get('status')=='teacher_generation_failed' and log.get('detail')=='PROVIDER_EXCEPTION' and
                log.get('content') in ['',None],'provider_failure_runner_log_mismatch')
            require(t.get('actual_returned_model') is None and generation.get('raw_content') in [None,''] and
                generation.get('content') in [None,''] and existing.get('conversion') is None and
                existing.get('conversion_errors',[])==[] and existing.get('raw_return_file') is None and
                existing.get('raw_source_bound_content_sha256') is None and
                not (attempt/'source_bound_conversion.json').exists() and
                not (attempt/'source_bound_conversion_error.json').exists(),
                'no_return_has_fabricated_return_or_conversion')
            return_state='request_attempt_failed_no_provider_return'
        else:
            require(provider_path.exists() and raw_path.exists(),'partial_return_evidence_not_eligible')
            provider=j.read(provider_path)
            require(provider.get('model')==q['settings']['model'] and t['actual_returned_model']==q['settings']['model'],'actual_provider_model_identity_changed')
            raw=raw_path.read_bytes().decode('utf8')
            require(provider.get('response')==raw,'raw_completed_provider_sidecar_mismatch')
            try:replay=grounded.convert(raw,doc)
            except Exception as exc:
                require(t['status']=='failed' and existing.get('conversion') is None,'source_conversion_failure_not_retained')
                error=j.read(attempt/'source_bound_conversion_error.json')
                require(error['reason']==str(exc) and not error['legacy_parser_fallback_permitted'],'source_hard_failure_not_reproducible')
            else:
                require(replay==existing.get('conversion') and replay==j.read(attempt/'source_bound_conversion.json'),'conversion_policy_not_exactly_reproducible')
            return_state='provider_return_preserved_and_conversion_replayed'
        files=[tp,*sorted(p for p in attempt.rglob('*') if p.is_file())]
        rows.append({'anonymous_answer_id':aid,'question_id':case['question_id'],'trial_id':t['trial_id'],'identity':t['identity'],
            'status':t['status'],'reused_from':str(tp),'original_request_id':receipt['request_id'],
            'original_package_request_index':receipt['package_request_index'],'original_files':[parent.bind(p) for p in files],
            'complete_HTTP_payload_equal':True,'source_observation_state':return_state,'returned_model_verified':not missing_return,'all_source_reference_prompt_model_demand_KB_score_conversion_equal':True,
            'failed_observation_retained_without_retry':t['status']=='failed','new_ledger_reservation':False})
    require([r['anonymous_answer_id'] for r in rows]==IDS,'fixed_five_reuse_order_changed');return rows

def copy_reuse(rows):
    for row in rows:
        for entry in row['original_files']:
            source=Path(entry['path']);require(j.filehash(source)==entry['sha256'],'reuse_source_changed')
            dest=RUN/source.relative_to(dev.RUN);dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():require(dest.read_bytes()==source.read_bytes(),'reuse_destination_conflict')
            else:shutil.copyfile(source,dest)

def metadata_show(models):
    """Future preflight only: loopback metadata, never a generation endpoint."""
    from models.Ollama_LLM import LocalOllamaHTTPClient
    rows=[]
    for model in models:
        public=model['public'];client=LocalOllamaHTTPClient(public['host'],4)
        req=urllib.request.Request(public['host'].rstrip('/')+'/api/show',data=json.dumps({'model':public['model']}).encode('utf8'),headers={'Content-Type':'application/json'},method='POST')
        with client.opener.open(req,timeout=10) as response:data=json.load(response)
        context={k:v for k,v in data.get('model_info',{}).items() if k.endswith('.context_length')}
        require(public['num_ctx']==NUM_CTX and context and min(context.values())>=public['num_ctx'],'native_context_insufficient_or_unknown')
        if model['name']==MODELS[1]:require(data.get('details',{}).get('quantization_level')=='F16','second_judge_not_frozen_Llama_F16')
        path=OUT/'model_metadata'/f"{model['name']}_show.json"
        if path.exists():require(j.read(path)==data,'native_model_metadata_changed_since_freeze')
        else:j.save(path,data)
        rows.append({'judge':model['name'],'model':public['model'],'digest':public['model_digest'],'service_version':public['service_version'],
            'native_context_fields':context,'show_response':parent.bind(path),'generation_called':False})
    return rows

def prepare():
    """NOT executed during design; requires the selected completed dev and root review."""
    chosen,selected_paths=selected_backend()
    require(not (OUT/'plan.json').exists(),'use_preflight_for_existing_frozen_plan')
    dev.validate_preflight();require((dev.OUT/'completion_summary.json').exists(),'actual_development_must_be_terminal')
    require(j.read(dev.OUT/'completion_summary.json')['actual_observations']==5,'five_development_observations_required')
    before=parent.request_count()
    allocation=selected_budget_guard('E4',before,25,reused=5) if BACKEND_VERSION in ['v5','v6','v7'] else None
    if BACKEND_VERSION not in ['v5','v6','v7']:require(before+30<=300,'budget_must_cover_no_reuse_fallback')
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['cases.json','schema.json']:(OUT/name).write_bytes((dev.OUT/name).read_bytes())
    config=combined_model_config(j.read(dev.OUT/'model_config.json'));j.save(OUT/'model_config.json',config)
    raw_cases=j.read(OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in raw_cases]==IDS,'fixed_dev_order_changed')
    for c in raw_cases:
        aid=c['anonymous_answer_id']
        for directory,extension in [('source_documents','json'),('prompts','txt')]:
            src=dev.OUT/directory/f'{aid}.{extension}';dst=OUT/directory/src.name;dst.parent.mkdir(exist_ok=True);dst.write_bytes(src.read_bytes())
        doc=j.read(OUT/'source_documents'/f'{aid}.json');text=(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        require(grounded.make_prompt(c,doc)==text,'full_transform_reproduction_failed')
        require(len(text.encode('utf8'))+8192+256<=NUM_CTX,'context_bound_exceeded')
    j.save(OUT/'reuse_decision.json',{'reuse_all_five':True,'planned_new_requests':25,'status':'being_verified_no_scientific_selection'})
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    require([m['name'] for m in models]==MODELS and len({m['family'] for m in models})==2,'two_fixed_model_families_required')
    for c in cases:
        for m in models:j.save(OUT/'expected_http_payloads'/f"{c['anonymous_answer_id']}_{m['name']}.json",expected_payload(m['public'],(OUT/'prompts'/f"{c['anonymous_answer_id']}.txt").read_text(encoding='utf8')))
    try:reuse=verify_reuse(cases,contract);decision={'reuse_all_five':True,'planned_new_requests':25,'proof_failure':None}
    except (ValueError,KeyError,FileNotFoundError) as exc:
        if BACKEND_VERSION in ['v5','v6','v7']:
            j.save(OUT/'reuse_decision.json',{'status':'stopped_exact_reuse_unproven','reuse_all_five':False,
                'planned_new_requests':0,'proof_failure':{'type':type(exc).__name__,'reason':str(exc)},
                'fresh30_fallback_allowed':False,'required_exact_reuse':5,'reserved_confirmation_cells':16 if BACKEND_VERSION=='v7' else 24 if BACKEND_VERSION=='v6' else 32})
            raise ValueError('v5_exact_reuse_proof_failed_stop_no_fresh30:'+str(exc)) from exc
        # No case is picked or discarded by outcome. An incomplete all-five
        # identity proof produces thirty fresh observations and retains history.
        reuse=[];decision={'reuse_all_five':False,'planned_new_requests':30,'proof_failure':{'type':type(exc).__name__,'reason':str(exc)}}
    if BACKEND_VERSION in ['v5','v6','v7']:
        require(len(reuse)==5 and decision['reuse_all_five'] and decision['planned_new_requests']==25,'v5_all_five_reuse_required')
    j.save(OUT/'reuse_decision.json',decision)
    if not decision['reuse_all_five']:
        with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            _,_,_,models,cases,contract=j.preflight(args())
    j.save(OUT/'expected_contract.json',contract);j.save(OUT/'reuse_manifest.json',reuse)
    j.save(OUT/'model_context_verification.json',metadata_show(models))
    matrix=[]
    for repeat in range(3):
        for c in cases:
            for m in contract['models']:
                one={**contract,'models':[m]};ident={'case_id':c['case_id'],'input_sha256':c['input_sha256'],'judge':m['name'],'repeat_index':repeat,'contract_sha256':j.digest(one)}
                old=next((r for r in reuse if r['trial_id']==j.digest(ident)),None)
                matrix.append({'anonymous_answer_id':c['anonymous_answer_id'],'question_id':c['question_id'],'judge':m['name'],'model_name':m['settings']['model'],
                    'repeat_index':repeat,'identity':ident,'planned_trial_id':j.digest(ident),'attempt':1,
                    'disposition':'exact_prior_observation_reused' if old else 'new_request_planned','original_request_id':old['original_request_id'] if old else None})
    require(len(matrix)==len({c['planned_trial_id'] for c in matrix})==30,'thirty_distinct_cells_required')
    require(sum(c['disposition']=='new_request_planned' for c in matrix)==decision['planned_new_requests'],'reuse_cell_count_mismatch')
    j.save(OUT/'matrix.json',matrix);copy_reuse(reuse)
    analysis=importlib.import_module('cce_analyze_grounded_stability_dev_v1')
    analysis.verify_step_sources(cases)
    j.save(OUT/'analysis_definition.json',analysis.definition())
    protected=[Path(__file__),ANALYZER,SELECTION,*selected_paths,*analysis.frozen_source_paths(),Path(grounded.__file__),Path(dev.__file__),dev.OUT/'plan.json',dev.OUT/'expected_contract.json',
        dev.OUT/'completion_summary.json',LLAMA_CONFIG,*[p for p in OUT.rglob('*') if p.is_file() and RUN not in p.parents]]
    plan={'status':'frozen_before_new_generation','version':'grounded_stability_dev_v1','created_utc':j.now(),
        'allocation_guard':allocation,'planned_observations':30,'new_requests_planned':decision['planned_new_requests'],'reused_observations':len(reuse),
        'reused_successes':sum(r['status']=='success' for r in reuse),'reused_failures':sum(r['status']=='failed' for r in reuse),
        'selection':'Fixed original A01-A05, all failures retained; no holdout or confirmation data.',
        'models':MODELS,'repeats':3,'max_attempts':1,'temperature':0,'num_ctx':NUM_CTX,'max_output_tokens':8192,'timeout_seconds':600,
        'primary_rule':'repeat0 never replaced by a later success','request_order':'repeat then fixed A-id then fixed model order',
        'selected_backend_version':BACKEND_VERSION,'selected_backend_module':parent.bind(grounded.__file__),
        'selected_development_module':parent.bind(dev.__file__),'root_selection':parent.bind(SELECTION),
        'scientific_configuration':'Selected grounded development configuration object; new orchestration provenance is separately bound here.',
        'source_configuration_object_sha256':j.digest(j.read(dev.OUT/'expected_contract.json')),
        'different_execution_script_not_claimed_identical':True,'metrics':{'direct':dev.DIRECT,'EGES':dev.EGES,
            'deterministic_step_values':['SR','SP'],'derived':['Com','Cor','Eff','IA','HV'],'tolerance':1e-12,
            'no_failure_imputation':True,'within_all_slots':160,'between_all_slots':80,'same_repeat_all_slots':240,
            'missingness':'Report full-three, partial and no-finite denominators; singleton variation is NA, never zero.',
            'dependence':'SR/SP deterministic and composites/EGES derived; separate from five direct judge scores.',
            'failed_trial_known_steps':'Retain independently verified SR/SP with deterministic_step_reuse; no judge stability success inferred. Legacy all-metrics-gated view separately retained.'},
        'dedicated_analysis_definition':parent.bind(OUT/'analysis_definition.json'),
        'generic_judge_run_statistics_are_execution_diagnostics_only':True,
        'sequence_gate':'Root review and E2 terminal before run; no automatic gate promotion from structural success.',
        'formal_eligible':False,'expert_returns':0,'requests_snapshot':before,
        'frozen_inputs':[parent.bind(p) for p in dict.fromkeys(protected)],
        'reused_original_files':[entry for r in reuse for entry in r['original_files']]}
    j.save(OUT/'plan.json',plan);require(parent.request_count()==before,'prepare_reserved_a_request');record('prepare',new_requests=0)
    print(j.canonical({'status':'prepared_zero_generation','observations':30,'reuse':len(reuse),'planned_new_requests':decision['planned_new_requests']}))

def validate():
    selected_backend()
    plan=j.read(OUT/'plan.json')
    require(plan['selected_backend_version']==BACKEND_VERSION,'frozen_backend_version_changed')
    if BACKEND_VERSION in ['v5','v6','v7']:
        require(plan['new_requests_planned']==25 and plan['reused_observations']==5,'v5_five_reuse_25_new_required')
        require(plan['allocation_guard']['budget_allocation_amendment']==parent.bind(selected_allocation_path()),'selected_frozen_allocation_mismatch')
    for entry in plan['frozen_inputs']+plan['reused_original_files']:
        require(j.filehash(entry['path'])==entry['sha256'],'frozen_binding_changed:'+entry['path'])
    for row in j.read(OUT/'reuse_manifest.json'):
        for entry in row['original_files']:
            target=RUN/Path(entry['path']).relative_to(dev.RUN)
            require(j.filehash(target)==entry['sha256'],'copied_original_not_byte_identical')
    return plan

def preflight():
    plan=validate();before=parent.request_count()
    with wrapper(check_contract=True),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    current=metadata_show(models)
    if plan['reused_observations']:
        require(verify_reuse(cases,contract)==j.read(OUT/'reuse_manifest.json'),'exact_reuse_proof_changed')
    result={'status':'pass','plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'grounded_module_sha256':j.filehash(grounded.__file__),'matrix_sha256':j.filehash(OUT/'matrix.json'),
        'contract_sha256':j.filehash(OUT/'expected_contract.json'),'model_digests_rechecked':current,
        'new_requests':0,'planned_observations':30,'planned_new_requests':plan['new_requests_planned'],'reused_observations':plan['reused_observations']}
    require(parent.request_count()==before,'metadata_preflight_reserved_request');j.save(OUT/'preflight_verification.json',result);record('preflight',new_requests=0)
    print(j.canonical({k:v for k,v in result.items() if k!='model_digests_rechecked'}))

async def run():
    plan=validate();pre=j.read(OUT/'preflight_verification.json')
    require(pre['status']=='pass' and pre['plan_sha256']==j.filehash(OUT/'plan.json') and pre['script_sha256']==j.filehash(__file__),'current_preflight_required')
    gate,gate_path=sequence_gate();review_path=OUT/'pre_generation_review/integration_review.json'
    require(review_path.exists(),'independent_full_HTTP_integration_review_missing')
    review=j.read(review_path)
    require(review.get('status')=='pass' and review.get('reviewed_by')=='root_agent'
        and review.get('actual_model_requests')==0 and review.get('full_schema_actual_HTTP_serialization_pass') is True
        and review.get('repeat_trial_sidecar_routing_pass') is True,'independent_integration_review_not_passed')
    reviewed={str(Path(r['path']).resolve()):r['sha256'] for r in review['protected_inputs']}
    paths=[Path(__file__),ANALYZER,Path(dev.__file__),Path(grounded.__file__),SELECTION,gate_path,
        *[OUT/n for n in ['plan.json','matrix.json','expected_contract.json','analysis_definition.json','preflight_verification.json']]]
    for path in paths:require(reviewed.get(str(path.resolve()))==j.filehash(path),'independent_review_stale:'+str(path))
    matrix=j.read(OUT/'matrix.json');new_ids={c['planned_trial_id'] for c in matrix if c['disposition']=='new_request_planned'}
    own=[r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started' and r['trial_id'] in new_ids]
    require(len(own)==len({r['trial_id'] for r in own}) and all(r['attempt']==1 for r in own),'repeated_E4_request_forbidden')
    before=parent.request_count();require(before==gate['package_requests_after_E2']+len(own),'unscheduled_parallel_requests_after_E2_gate')
    require(before+len(new_ids)-len(own)<=300,'remaining_package_budget_insufficient')
    if BACKEND_VERSION in ['v5','v6','v7']:
        require(len(new_ids)==25 and len(matrix)==30,'v5_E4_fixed_25_new_required')
        selected_budget_guard('E4',before,len(new_ids)-len(own),reused=plan['reused_observations'])
    existing={c['planned_trial_id']:j.read(RUN/'trials'/f"{c['planned_trial_id']}.json") for c in matrix
        if (RUN/'trials'/f"{c['planned_trial_id']}.json").exists()}
    all_terminal=len(existing)==30 and all(r['status'] in ['success','failed'] for r in existing.values())
    if all_terminal:
        record('run',status='runner_returned',new_requests=0,already_terminal_matrix_preserved=True)
        print(j.canonical({'status':'existing_terminal_matrix_preserved','new_requests':0}));return
    require(not any(r['status']=='failed' and not r.get('actual_api_request_made') for r in existing.values()),
        'partial_resume_has_terminal_local_failure_requires_separate_orchestration_review_no_silent_retry')
    with wrapper(check_contract=True):await j.run(args(True))
    validate();record('run',status='runner_returned',new_requests=parent.request_count()-before)

def analyze():
    module=importlib.import_module('cce_analyze_grounded_stability_dev_v1')
    return module.analyze()

def design(version='v4'):
    """Zero-call draft only; no candidate results, selection or actual OUT."""
    global DESIGN,dev,grounded,BACKEND_VERSION,EXTRA_KEY
    require(version in CONTEXT_BY_BACKEND,'explicit_supported_backend_required')
    require(not OUT.exists(),'draft_must_not_touch_an_actual_E4_directory')
    DESIGN=OUT.parent/'grounded_stability_design_v1'/f'{version}_draft'
    dev=importlib.import_module(f'cce_grounded_development_{version}')
    grounded=importlib.import_module(f'cce_grounded_extraction_{version}')
    BACKEND_VERSION=version;EXTRA_KEY='grounded_extraction_'+version;configure_context(version)
    material=grounded.OUT if (grounded.OUT/'plan.json').exists() else grounded.OUT/'draft'
    manifest=material/('plan.json' if (material/'plan.json').exists() else 'draft_manifest.json')
    require(manifest.exists() and (material/'schema.json').exists(),'selected_source_material_not_ready')
    cases=j.read(dev.old.OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==IDS,'fixed_five_selection_changed')
    original_primary=j.read(dev.model_probe.OUT/'model_config.json');primary=copy.deepcopy(original_primary)
    if version in ['v4','v5','v6','v7']:primary['models'][0]['num_ctx']=NUM_CTX
    require({k:v for k,v in primary['models'][0].items() if k!='num_ctx'}=={k:v for k,v in original_primary['models'][0].items() if k!='num_ctx'},'primary_changed_beyond_context')
    model_config=combined_model_config(primary)
    require([m['name'] for m in model_config['models']]==MODELS,'fixed_model_order_changed')
    matrix=[];source_checks=[]
    for case in cases:
        aid=case['anonymous_answer_id'];doc=j.read(material/'source_documents'/f'{aid}.json')
        prompt=(material/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        require(doc['text']==case['model_response'] and grounded.make_prompt(case,doc)==prompt,'draft_prompt_or_source_reproduction_failed')
        bound=len(prompt.encode('utf8'))+8192+256;require(bound<=NUM_CTX,'draft_context_bound_exceeded')
        source_checks.append({'anonymous_answer_id':aid,'answer_sha256':case['answer_sha256'],'question_sha256':case['question_sha256'],
            'references_sha256':j.digest(case['references']),'prompt_text_sha256':grounded.rawsha(prompt),
            'prompt_file_sha256':j.filehash(material/'prompts'/f'{aid}.txt'),'full_text_and_suffix_preserved':True,
            'conservative_context_bound':bound,'fits_40960_diagnostic':bound<=40960,'configured_num_ctx':NUM_CTX})
    for repeat in range(3):
        for case in cases:
            source=next(r for r in source_checks if r['anonymous_answer_id']==case['anonymous_answer_id'])
            for model in model_config['models']:
                matrix.append({'anonymous_answer_id':case['anonymous_answer_id'],'question_id':case['question_id'],
                    'source_case_id':case['case_id'],'judge':model['name'],'model_name':model['model_name'],
                    'repeat_index':repeat,'attempt':1,'source_id':grounded.source_id_for_case(case),
                    **{k:source[k] for k in ['answer_sha256','question_sha256','references_sha256','prompt_text_sha256','prompt_file_sha256']},
                    'disposition':'exact_reuse_candidate_pending_all_five_proof' if repeat==0 and model['name']==dev.MODEL else 'new_request_pending_root_review',
                    'trial_id':None,'new_request_started':False})
    checks=[]
    def check(name,ok=True):require(ok,'draft_check_failed:'+name);checks.append({'check':name,'pass':True})
    def reject(name,call):
        try:call()
        except ValueError as exc:checks.append({'check':name,'pass':True,'rejected':str(exc)});return
        raise ValueError('expected_draft_rejection:'+name)
    check('30_fixed_observations',len(matrix)==30)
    check('unique_AID_model_repeat_slots',len({(r['anonymous_answer_id'],r['judge'],r['repeat_index']) for r in matrix})==30)
    check('5_status_blind_repeat0_reuse_candidates',sum(r['disposition'].startswith('exact_reuse') for r in matrix)==5)
    check('25_other_slots_new_if_exact_reuse_passes',sum(r['disposition'].startswith('new_request') for r in matrix)==25)
    check('no_preinvented_trial_or_request',all(r['trial_id'] is None and not r['new_request_started'] for r in matrix))
    check('v2_v3_still_40960',CONTEXT_BY_BACKEND=={'v2':40960,'v3':40960,'v4':98304,'v5':98304,'v6':98304,'v7':98304})
    bad=copy.deepcopy(primary);bad['models'][0]['num_ctx']=98304
    reject('v2_rejects_98304',lambda:configure_context('v2',bad));reject('v3_rejects_98304',lambda:configure_context('v3',bad));configure_context(version,primary)
    check('two_models_identical_selected_context',all(r['num_ctx']==NUM_CTX for r in model_config['models']))
    original_llama=next(x for x in j.read(LLAMA_CONFIG)['models'] if x['name']==MODELS[1])
    check('Llama_only_context_change',{k:v for k,v in model_config['models'][1].items() if k!='num_ctx'}=={k:v for k,v in original_llama.items() if k!='num_ctx'})
    # Exercise the real serializer, replacing its HTTP client method before any
    # request; these fixture prompts and captures are not experiment returns.
    old_contract=j.read(dev.model_probe.OUT/'expected_contract.json')
    primary_public=copy.deepcopy(old_contract['models'][0]['settings'])
    for row in model_config['models']:
        public=copy.deepcopy(primary_public)
        public.update(model=row['model_name'],model_digest=row['model_digest'],num_ctx=NUM_CTX,
            enable_thinking=row['enable_thinking'],format=grounded.schema())
        captured=expected_payload(public,'SYNTHETIC_ONLY context serializer probe')
        check('actual_serializer_'+row['name'],captured['options']['num_ctx']==NUM_CTX and captured['options']['temperature']==0 and captured['options']['num_predict']==8192 and captured['format']==grounded.schema())
    check('actual_OUT_still_absent',not OUT.exists())
    paths=[Path(__file__),ANALYZER,Path(grounded.__file__),Path(dev.__file__),dev.old.OUT/'cases.json',manifest,
        material/'schema.json',material/'software_probes.json',dev.model_probe.OUT/'model_config.json',LLAMA_CONFIG,
        *[material/'prompts'/f"{c['anonymous_answer_id']}.txt" for c in cases]]
    if version in ['v4','v5','v6','v7']:paths.append(CONTEXT_CONFIGURATION)
    if version in ['v5','v6','v7']:paths.extend(allocation_dependencies())
    plan={'status':'design_only_not_frozen_not_prepared','version':'grounded_stability_design_v1','created_utc':j.now(),
        'new_requests':0,'service_metadata_requests':0,'planned_observations':30,'fixed_development_answers':IDS,
        'families':['qwen','llama'],'selected_backend_draft':version,'supported_selected_backends':list(CONTEXT_BY_BACKEND),
        'selection':'Fixed original five answers; no score-dependent choice. Every failure retained.',
        'final_backend_requires_root_selection_manifest':str(SELECTION),'source_material':str(material),
        'candidate_repeat_zero':5,'exact_reuse_not_yet_proven':True,'new_request_bounds':[25,25] if version in ['v5','v6','v7'] else [25,30],
        'reuse_policy':'All-five status-blind exact proof: trial/receipt, full actual HTTP payload, source/question/reference, demand/KB/rubric/schema/model/settings/converter. Original trial IDs and bytes retained, failed trials included, no new ledger reservation for reuse. For v5/v6/v7 any failed proof stops, with no fresh30 fallback; v5 reserves 32 later cells and v6 reserves 24 plus three unallocated calls; v7 reserves 16 primary calls, disables optional blind and leaves six calls unallocated. Older version policies retain their explicit fresh30 namespace; no best-case cherry-picking.',
        'allocation_guard':selected_budget_guard('E4',253 if version=='v7' else 248 if version=='v6' else 243,25,reused=5) if version in ['v5','v6','v7'] else None,
        'model_configuration':model_config,'run_settings':{'temperature':0,'num_ctx':NUM_CTX,'max_output_tokens':8192,'max_attempts':1,'repeats':3,'timeout_seconds':600},
        'second_family_preflight':'Before actual generation, query tags/show and require the pinned digest, native capacity and Llama F16. The prior metadata is only a bound planning input.',
        'science_vs_orchestration':'Preserve selected dev source_bound_variant identity for scientific contract; keep new batch provenance separate.',
        'analysis_plan':{'metric_count':16,'direct':dev.DIRECT,'EGES':dev.EGES,'deterministic':['SR','SP'],'derived':['Com','Cor','Eff','IA','HV'],
            'within_groups':160,'between_groups':80,'same_repeat_slots':240,'tolerance':1e-12,'singleton_variation':None,
            'failed_trial_known_steps':'Retain source-verified deterministic SR/SP separately; unavailable judge/EGES/derived components remain NA. Legacy all-metrics-gated view separate.',
            'no_best_repeat_selection':True,'scientific_or_expert_validation':False},
        'remaining_before_freeze':['final selected dev5 terminal and fact audit','root backend selection binding selected model config and prospective context metadata','all-five complete HTTP reuse proof','E2 terminal sequence gate','actual native-model metadata recheck','independent full HTTP integration and repeat-sidecar routing'],
        'prepare_executed':False,'preflight_executed':False,'run_executed':False,'sealed_confirmation_or_holdout_scientific_output_read':False,
        'input_sha256':[parent.bind(p) for p in paths],'actual_command':[sys.executable,*sys.argv]}
    j.save(DESIGN/'draft_plan.json',plan);j.save(DESIGN/'draft_matrix.json',matrix);j.save(DESIGN/'draft_model_config.json',model_config)
    j.save(DESIGN/'draft_source_checks.json',source_checks)
    j.save(DESIGN/'draft_verification.json',{'status':'pass_design_only_not_full_HTTP_integration','backend_version':version,'checks':checks,'checks_count':len(checks),
        'actual_command':[sys.executable,*sys.argv],'script_sha256':j.filehash(__file__),'draft_plan_sha256':j.filehash(DESIGN/'draft_plan.json'),
        'draft_matrix_sha256':j.filehash(DESIGN/'draft_matrix.json'),'planned_observations':30,'unproven_reuse_candidates':5,
        'new_requests':0,'service_metadata_requests':0,'actual_OUT_created':False,'selection_written':False})
    (DESIGN/'README.md').write_text('# E4 '+version+' scheduler draft\n\nFixed A01-A05 by two model families by three observations gives 30 cells. Exact reuse retains all five original repeat-zero identities, including failed responses and verified no-return transport failures. Missing HTTP/request/identity evidence blocks reuse. For v5/v6/v7 any proof failure stops: exactly five reused cells and at most 25 new requests are mandatory. v5 reserves 32 later cells; v6 reserves 24 and leaves three calls unallocated; v7 reserves 16 primary calls, disables optional blind and leaves six calls unallocated. Older policies remain explicitly versioned.\n\nv2/v3 keep 40960; v4/v5/v6/v7 use 98304 with separately bound metadata. This is only a zero-call design, not an actual reuse result. Selected dev/fact terminal records, root selection, E2 terminal gate and a new independent HTTP/sidecar integration gate are still required. The dated dev25-to30 and v6 dev30-to35 budget amendments are disclosed G01 deviations. v6 optional blind is 8 x 1, not a repeatability estimate. The v7 allocation prospectively amends dev35-to40 and disables optional blind entirely; it cannot be reactivated after confirmation results.\n',encoding='utf8')
    print(j.canonical({'status':plan['status'],'backend':version,'context':NUM_CTX,'checks':len(checks),'observations':30,'candidate_reuse':5,'new_request_bounds':[25,25] if version in ['v5','v6','v7'] else [25,30],'new_requests':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['design','self-check','prepare','preflight','run','analyze']);p.add_argument('--allow-local-calls',action='store_true');p.add_argument('--backend',choices=list(CONTEXT_BY_BACKEND),default='v4');a=p.parse_args()
    if a.action=='run':require(a.allow_local_calls,'explicit_local_call_flag_required');asyncio.run(run())
    elif a.action in ['design','self-check']:design(a.backend)
    else:{'prepare':prepare,'preflight':preflight,'analyze':analyze}[a.action]()
