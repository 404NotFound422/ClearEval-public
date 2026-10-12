"""E2 source-bound full-pipeline scheduler; root selection precedes any freeze.

21 fresh development requests, original steps/Com, separate supplements. Merely
importing this module or reading help neither freezes inputs nor requests a model.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import contextlib
import importlib
import io
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_validation as core
import cce_judges as j
import cce_grounded_development_v2 as dev
import cce_grounded_extraction_v2 as grounded
import evaluator_integrity as integrity
import cce_output_contract_v1 as parent
import cce_optimizer_model_probe_v1 as model_probe

BASE=ROOT/'artifacts/cce_validation'
SOURCE=BASE/'judges/controls_contract_v2'
OUT=BASE/'optimizer_20261010/grounded_controls_v1'
RUN=OUT/'run'
SELECTION=BASE/'optimizer_20261010/grounded_candidate_selection_v1/selection.json'
SourceBoundConversionError=dev.SourceBoundConversionError
BACKEND_VERSION='v2' # Import-only default; a root manifest explicitly selects the frozen backend.
EXTRA_KEY='grounded_extraction_v2'
MODEL='local_qwen27b_q8_development'
CONTEXT_BY_BACKEND={'v2':40960,'v3':40960,'v4':98304,'v5':98304,'v6':98304,'v7':98304}
NUM_CTX=CONTEXT_BY_BACKEND[BACKEND_VERSION]
CONTEXT_CONFIGURATION=BASE/'optimizer_20261010/grounded_v4_design_v1/context_configuration.json'
SETTINGS={'model':MODEL,'num_ctx':40960,'temperature':0,'max_output_tokens':8192,
          'max_attempts':1,'repeats':1,'planned_new_requests':21,'planned_reuse':0}
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']

def require(ok,message):
    if not ok:raise ValueError(message)

def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


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

def configure_context(version,model_config=None):
    global NUM_CTX,CONTEXT_CONFIGURATION
    require(version in CONTEXT_BY_BACKEND,'explicit_supported_backend_context_required')
    expected=CONTEXT_BY_BACKEND[version]
    if version in ['v4','v5','v6','v7']:
        CONTEXT_CONFIGURATION=ROOT/'artifacts/cce_validation/optimizer_20261010'/f'grounded_{version}_design_v1/context_configuration.json'
    if model_config is not None:
        models=model_config['models'];require(len(models)==1 and models[0]['name']==MODEL,'selected_development_model_changed')
        require(models[0]['num_ctx']==expected,'selected_development_context_changed')
    if version in ['v4','v5','v6','v7']:
        metadata=j.read(CONTEXT_CONFIGURATION)
        require(metadata['selected_by']=='root_agent' and metadata['num_ctx']==expected and metadata['new_generation_requests']==0,'prospective_selected_context_not_bound')
        require(getattr(dev,'NUM_CTX',None)==expected and getattr(grounded,'CONFIGURED_NUM_CTX',None)==expected,'selected_module_context_mismatch')
        if model_config is not None:
            row=models[0];known=next(x for x in metadata['models'] if x['local_model_name']==row['model_name'])
            require(row['model_digest']==known['digest'] and min(known['native_context_metadata'].values())>=expected,'selected_model_context_metadata_mismatch')
    NUM_CTX=expected;SETTINGS['num_ctx']=expected
    return expected

def inputs():
    """Read only the fixed exposed controls; never accept a caller-selected subset."""
    cases=core.read(SOURCE/'cases.json')['cases'];pairs=core.read(SOURCE/'pairs.json')
    require(len(cases)==21 and len(pairs)==15,'E2_population_must_be_21_and_15')
    require(len({(c['question_id'],c['specific_question'],c['model_response']) for c in cases})==21,'full_text_identity_collision')
    require({c['question_id'] for c in cases}=={2,21,22},'development_scope_changed')
    lookup={c['case_id']:c for c in cases}
    for pair in pairs:
        a,b=(lookup[pair[k]] for k in ['baseline_case_id','variant_case_id'])
        require(a['specific_question']==b['specific_question'] and a['question_id']==b['question_id'] and a['references']==b['references'],'pair_question_or_reference_mismatch')
    return cases,pairs

def build_grounded_inputs(final_grounded_module):
    """In-memory interface only; the caller must first approve final module hashes.

    The final module supplies source_id_for_case, document and make_prompt.
    No baseline result, extraction or provider response is an input here.
    """
    version=final_grounded_module.VERSION.rsplit('_',1)[-1]
    require(version in CONTEXT_BY_BACKEND,'unsupported_prompt_backend')
    context=CONTEXT_BY_BACKEND[version]
    require(getattr(final_grounded_module,'CONFIGURED_NUM_CTX',context)==context,'prompt_module_context_mismatch')
    cases,pairs=inputs();rows=[]
    for c in cases:
        source_id=final_grounded_module.source_id_for_case(c)
        expected='SRC_'+final_grounded_module.rawsha(c['specific_question']+'\0'+c['model_response'])[:24]
        require(source_id==expected and re.fullmatch(r'SRC_[0-9a-f]{24}',source_id),'source_id_must_be_opaque_question_answer_hash')
        document=final_grounded_module.document(c['model_response'],source_id)
        prompt=final_grounded_module.make_prompt(c,document)
        require(document['text']==c['model_response'],'full_answer_document_changed')
        require(document['source_id']==source_id,'source_identity_changed')
        require(''.join(u['text'] for u in document['units'])==c['model_response'],'source_units_not_lossless')
        require(prompt.endswith(parent.v2.reference_suffix(c)),'original_reference_suffix_changed')
        marker='[LOSSLESS INDEXED MODEL_PROTOCOL; concatenate text fields in order]\n'
        if marker in prompt:
            units=[{'unit_id':u['unit_id'],'text':u['text']} for u in document['units']]
            require(prompt.count(marker+final_grounded_module.canonical(units))==1,'indexed_full_text_missing_or_duplicated')
        # These metadata values are external identifiers, never rubric evidence.
        for metadata in [c['case_id'],c.get('base_id'),c.get('generator_model')]:
            if metadata and metadata not in c['specific_question'] and metadata not in c['model_response']:
                require(metadata not in prompt,'model_visible_experiment_metadata:'+metadata)
        require(len(prompt.encode('utf8'))+8192+256<=context,'full_prompt_exceeds_fixed_context')
        rows.append({'external_metadata':{'case_id':c['case_id'],'question_id':c['question_id'],
             'condition':c['condition'],'generator_model':c.get('generator_model')},
            'source_document':document,'actual_full_prompt':prompt,
            'prompt_sha256':final_grounded_module.rawsha(prompt),
            'references_sha256':core.digest(c['references']),
            'reuse_trial':False,'reextract_edited_full_text':True})
    return rows,pairs

def original_steps(case,encoder):
    """Future orchestration calls this on every full answer, with the old core."""
    config=core.read(SOURCE/'step_config.json')
    require(config['threshold']==.7 and encoder.identity==config['encoder'],'original_step_config_changed')
    require(config['adapter_sha256']==core.filehash(core.__file__),'original_core_changed')
    return core.score_steps(case,case['references'],encoder,.7)

def derive_primary(original_step_result,component_gated_values):
    """Only original SR enters Com. Symbolic supplementary values are not inputs."""
    raw={k:component_gated_values.get(k) for k in DIRECT+EGES}
    require(all(v is None or finite(v) for v in raw.values()),'invalid_component_number')
    sr=original_step_result.get('sr');sp=original_step_result.get('sp')
    com=.4*sr+.6*raw['c_param']/3 if finite(sr) and finite(raw['c_param']) else None
    cor=sum(raw[k]/m for k,m in [('co_order',3),('co_method',2),('co_param',2),('co_chem',1)])/4 if all(finite(raw[k]) for k in DIRECT[1:]) else None
    eff=(((raw['s_method']/2.5+1)/2)+raw['s_label']/6+raw['s_trans']/3+raw['s_time']/3)/4 if all(finite(raw[k]) for k in EGES) else None
    complete=all(finite(v) for v in [com,cor,eff])
    return {**raw,'sr':sr,'sp':sp,'Com':com,'Cor':cor,'Eff':eff,
        'IA':min(com,cor,eff) if complete else None,'HV':com*cor*eff if complete else None}

def supplementary_steps_binding():
    """A link and claim boundary only, never an alternative Com input."""
    path=BASE/'optimizer_20261010/step_representation_v3/summary.json'
    return {'path':str(path),'sha256':core.filehash(path),
        'scope':'Independent developmental lexical and source-order coverage supplement',
        'used_in_primary_Com_Cor_Eff_IA_HV':False,'not_original_BioProBench_SR_SP':True}

def bind(path):return parent.bind(path)
def args(allow=False):
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'model_config.json',models=[MODEL],
        question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',demand_manifest=None,
        ledger=parent.LEDGER,total_budget=300,external_request_count=0,max_calls=21,max_attempts=1,repeats=1,
        temperature=0.,max_output_tokens=8192,timeout_seconds=600,allow_api=allow)

def casekey(c):return (int(c['question_id']),c['specific_question'],c['model_response'])

def expected_http_payload(public,prompt,schema_value=None):
    require(public['num_ctx']==NUM_CTX,'selected_HTTP_context_mismatch')
    value={'model':public['model'],'prompt':prompt,'options':{
        'num_predict':8192,'temperature':0.,'num_ctx':public['num_ctx']},'stream':False,
        'format':j.read(OUT/'schema.json') if schema_value is None else schema_value}
    if public.get('enable_thinking') is not None:value['think']=public['enable_thinking']
    return value

def record(action,**extra):
    p=OUT/'actual_commands.json';rows=j.read(p) if p.exists() else []
    rows.append({'utc':j.now(),'argv':[sys.executable,*sys.argv],'action':action,'cwd':str(ROOT),
        'script_sha256':j.filehash(__file__),'package_requests_snapshot':parent.request_count(),**extra});j.save(p,rows)

def backend_files(version):
    require(version in CONTEXT_BY_BACKEND,'root_backend_version_must_be_explicit_v2_v3_v4_v5_v6_or_v7')
    return {name:ROOT/'scripts'/f'{prefix}_{version}.py' for name,prefix in [
        ('development','cce_grounded_development'),('grounded','cce_grounded_extraction'),('fact_checker','cce_audit_grounded_facts')]}

def selection():
    """Internal root decision after five-case facts; never a user approval flow."""
    global dev,grounded,SourceBoundConversionError,BACKEND_VERSION,EXTRA_KEY
    require(SELECTION.exists(),'root_candidate_selection_missing_no_prepare_or_generation')
    chosen=j.read(SELECTION)
    require(chosen.get('status')=='selected_for_development_E2' and chosen.get('approved_for_e2') is True
        and chosen.get('selected_by')=='root_agent' and bool(chosen.get('decision_reason')),'root_candidate_not_selected_for_E2')
    version=chosen.get('backend_version');backend=backend_files(version)
    bound={str(Path(r['path']).resolve()):r['sha256'] for r in chosen.get('bindings',[])}
    module_paths=[backend['development'],backend['grounded']]
    for path in module_paths:require(path.exists() and bound.get(str(path.resolve()))==j.filehash(path),'selected_backend_module_not_approved:'+str(path))
    dev=importlib.import_module(f'cce_grounded_development_{version}')
    grounded=importlib.import_module(f'cce_grounded_extraction_{version}')
    require(Path(dev.grounded.__file__).resolve()==Path(grounded.__file__).resolve() and dev.MODEL==MODEL,'selected_development_backend_or_model_mismatch')
    SourceBoundConversionError=dev.SourceBoundConversionError;BACKEND_VERSION=version;EXTRA_KEY='grounded_extraction_'+version
    configure_context(version,j.read(dev.OUT/'model_config.json'))
    fact_out=dev.OUT/f'independent_fact_audit_{version}'
    paths=[Path(grounded.__file__),grounded.OUT/'schema.json',grounded.OUT/'plan.json',grounded.OUT/'software_probes.json',
        dev.OUT/'plan.json',dev.OUT/'expected_contract.json',dev.OUT/'matrix.json',dev.OUT/'completion_summary.json',
        dev.OUT/'per_answer.json',dev.OUT/'model_config.json',fact_out/'summary.json',fact_out/'per_answer.json',
        Path(dev.__file__),backend['fact_checker']]
    if version in ['v4','v5','v6','v7']:paths.append(CONTEXT_CONFIGURATION)
    if version in ['v5','v6','v7']:
        paths.extend(allocation_dependencies());verify_selected_dev_allocation()
    for path in paths:require(path.exists() and bound.get(str(path.resolve()))==j.filehash(path),'selected_candidate_binding_missing_or_stale:'+str(path))
    dev_summary=j.read(dev.OUT/'completion_summary.json')
    require(dev_summary['actual_observations']==5,'five_case_development_not_complete')
    facts=j.read(fact_out/'summary.json')
    require(facts['status']=='complete' and facts['fixed_answers']==5,'five_case_fact_review_not_complete')
    require(Path(facts['batch_out']).resolve()==dev.OUT.resolve(),'fact_review_is_not_selected_development')
    require(len(j.read(dev.OUT/'per_answer.json'))==5,'five_case_denominator_changed')
    matrix=j.read(dev.OUT/'matrix.json');require(len(matrix)==5 and {r['anonymous_answer_id'] for r in matrix}==set(parent.IDS),'selected_fixed_five_changed')
    for cell in matrix:
        path=dev.RUN/'trials'/f"{cell['planned_trial_id']}.json";trial=j.read(path)
        require(trial['status'] in ['success','failed'] and trial['identity']==cell['identity'],'selected_development_not_terminal')
    for item in [*dev_summary.get('bound_observations',[]),*facts.get('inputs',[])]:
        require(j.filehash(item['path'])==item['sha256'],'selected_actual_or_fact_source_changed')
        paths.append(Path(item['path']))
    dev.validate_preflight() # Read-only file/contract validation; no model/service query.
    # Selection need not falsely assert all five are correct. Its reason records
    # the actual observed limitations; the complete fact review remains bound.
    return chosen,paths

def validate():
    selection();plan=j.read(OUT/'plan.json')
    require(plan['selected_backend_version']==BACKEND_VERSION,'frozen_backend_version_changed')
    for item in plan['frozen_inputs']:require(j.filehash(item['path'])==item['sha256'],'frozen_E2_input_changed:'+item['path'])
    require(plan['planned_new_requests']==21 and plan['planned_pairs']==15 and plan['settings']==SETTINGS,'E2_scope_changed')
    return plan

class CachedEncoder(core.Encoder):
    """No download or new embedding: all original scientific inputs are unchanged."""
    def __init__(self):
        import numpy
        from transformers import AutoTokenizer
        self.np=numpy;self.identity=j.read(SOURCE/'step_config.json')['encoder'];self.used={}
        # The original core also reports tokenizer truncation counts. Retain its
        # exact local tokenizer while all numeric embeddings come from cache.
        tokenizer=AutoTokenizer.from_pretrained(str(core.ASSETS/'assets/all-mpnet-base-v2'),local_files_only=True)
        self.model=SimpleNamespace(tokenizer=tokenizer,max_seq_length=self.identity['max_seq_length'])
        self.available={Path(r['path']).name:r for r in j.read(SOURCE/'embedding_usage.json')['used_vectors']}
    def encode(self,texts):
        rows=[]
        for text in texts:
            name=core.digest([self.identity,text])+'.npy';require(name in self.available,'original_cached_vector_missing_requires_review')
            item=self.available[name];require(j.filehash(item['path'])==item['sha256'],'cached_vector_changed')
            vector=self.np.load(item['path'],allow_pickle=False);require(vector.shape==(768,) and self.np.isfinite(vector).all(),'invalid_cached_vector')
            self.used[name]=item;rows.append(vector)
        return self.np.asarray(rows)

def replay_steps():
    cases,_=inputs();encoder=CachedEncoder();old={r['case_id']:r['step_result'] for r in j.read(SOURCE/'step_results.json')};rows=[]
    for c in cases:
        scored=original_steps(c,encoder);require(scored==old[c['case_id']],'original_full_text_steps_not_exactly_reproduced')
        rows.append({'case_id':c['case_id'],'answer_sha256':grounded.rawsha(c['model_response']),
            'references_sha256':j.digest(c['references']),'step_result':scored,'original_core_full_text_reparsed':True})
    j.save(OUT/'step_results.json',rows)
    j.save(OUT/'embedding_usage.json',{'new_embeddings':0,'reused_embeddings':len(encoder.used),'used_vectors':list(encoder.used.values()),
        'original_cache_modified':False,'network_downloads':0,'new_model_requests':0})

def prepare():
    chosen,dependencies=selection() # Required before making any frozen batch files.
    before=parent.request_count();require(before+21<=300,'insufficient_remaining_package_budget')
    allocation=selected_budget_guard('E2',before,21) if BACKEND_VERSION in ['v5','v6','v7'] else None
    if (OUT/'plan.json').exists():validate();print(j.canonical({'status':'existing_plan_unchanged','new_requests':0}));return
    require(not list(RUN.glob('attempts/*/request_receipt.json')),'generation_already_exists_cannot_prepare')
    probes=j.read(grounded.OUT/'software_probes.json')
    require(probes['status']=='pass' and probes['new_model_requests']==0,'grounded_software_probes_not_passed')
    for key,path in [('script_sha256',Path(grounded.__file__)),('schema_sha256',grounded.OUT/'schema.json'),('plan_sha256',grounded.OUT/'plan.json')]:
        require(probes[key]==j.filehash(path),'grounded_probes_stale')
    data,pairs=build_grounded_inputs(grounded);cases,_=inputs();OUT.mkdir(parents=True,exist_ok=True)
    for name in ['pairs.json','references.json','step_config.json']:(OUT/name).write_bytes((SOURCE/name).read_bytes())
    (OUT/'model_config.json').write_bytes((dev.OUT/'model_config.json').read_bytes())
    (OUT/'schema.json').write_bytes((grounded.OUT/'schema.json').read_bytes())
    indexed=[];files=[Path(__file__),Path(dev.__file__),Path(grounded.__file__),SELECTION,*dependencies,
        *[SOURCE/n for n in ['cases.json','pairs.json','references.json','step_config.json','step_results.json','embedding_usage.json']],
        *[OUT/n for n in ['pairs.json','references.json','step_config.json','model_config.json','schema.json']],
        BASE/'optimizer_20261010/grounded_controls_design_v1/design.json']
    for i,(c,payload) in enumerate(zip(cases,data),1):
        ident=f'E2_{i:02d}';indexed.append({**c,'control_id':ident})
        docpath=OUT/'source_documents'/f'{ident}.json';promptpath=OUT/'prompts'/f'{ident}.txt'
        j.save(docpath,payload['source_document']);promptpath.parent.mkdir(exist_ok=True)
        # Match the unchanged cce_judges prompt-file writer on Windows; raw HTTP
        # content is separately bound after universal-newline text reading.
        promptpath.write_text(payload['actual_full_prompt'],encoding='utf8');files += [docpath,promptpath]
    j.save(OUT/'cases.json',{'cases':indexed});files.append(OUT/'cases.json')
    replay_steps();files += [OUT/'step_results.json',OUT/'embedding_usage.json',Path(core.__file__)]
    plan={'status':'frozen_before_generation','version':'grounded_controls_v1','created_utc':j.now(),'settings':SETTINGS,
        'allocation_guard':allocation,'planned_new_requests':21,'planned_pairs':15,'starting_requests':before,'base_answers':3,'natural_baselines':3,'canonical_baselines':3,'variants':15,
        'all_21_new_trials':True,'cross_batch_reused_trials':0,'root_selection':bind(SELECTION),
        'selected_backend_version':BACKEND_VERSION,'selected_backend_module':bind(grounded.__file__),
        'selected_development_module':bind(dev.__file__),'selected_fact_checker':bind(ROOT/'scripts'/f'cce_audit_grounded_facts_{BACKEND_VERSION}.py'),
        'same_pair_contract_required':True,'full_text_reextraction_both_arms':True,'Com':'.4*original_SR+.6*c_param/3',
        'supplement':supplementary_steps_binding(),'formal_eligible':False,'expert_returns':0,
        'frozen_inputs':[bind(p) for p in dict.fromkeys(files)]}
    j.save(OUT/'plan.json',plan);validate();require(parent.request_count()==before,'prepare_generated_request');record('prepare',new_requests=0)
    print(j.canonical({'status':'prepared','planned_new_requests':21,'new_requests':0}))

def preflight():
    validate();before=parent.request_count()
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    require(len(models)==1 and models[0]['name']==MODEL,'model_scope_changed')
    previous=j.read(dev.OUT/'expected_contract.json')
    require(models[0]['public']==previous['models'][0]['settings'],'model_or_schema_settings_changed_from_selected_dev')
    same_science(contract,previous,'selected_science_or_demands_changed')
    j.save(OUT/'expected_contract.json',contract);matrix=[]
    for c in cases:
        identity={'case_id':c['case_id'],'input_sha256':c['input_sha256'],'judge':MODEL,'repeat_index':0,'contract_sha256':j.digest(contract)}
        path=OUT/'prompts'/f"{c['control_id']}.txt";prompt=path.read_text(encoding='utf8')
        matrix.append({'control_id':c['control_id'],'case_id':c['case_id'],'question_id':c['question_id'],'condition':c['condition'],
            'identity':identity,'planned_trial_id':j.digest(identity),'prompt_file_sha256':j.filehash(path),
            'prompt_raw_sha256':grounded.rawsha(prompt),'source_id':grounded.source_id_for_case(c)})
    require(len(matrix)==21 and len({c['prompt_raw_sha256'] for c in matrix})==21,'full_prompt_identity_collision')
    j.save(OUT/'matrix.json',matrix)
    j.save(OUT/'preflight_verification.json',{'status':'pass','new_model_requests':0,
        'bindings':[bind(p) for p in [Path(__file__),Path(grounded.__file__),OUT/'plan.json',OUT/'matrix.json',OUT/'expected_contract.json',SELECTION]]})
    require(parent.request_count()==before,'preflight_generated_request');record('preflight',new_requests=0)

def validate_preflight():
    validate();check=j.read(OUT/'preflight_verification.json');require(check['status']=='pass','E2_preflight_not_passed')
    for p in check['bindings']:require(j.filehash(p['path'])==p['sha256'],'E2_preflight_drift:'+p['path'])

async def run():
    validate_preflight();plan=j.read(OUT/'plan.json');before=parent.request_count()
    path=OUT/'pre_generation_review/integration_review.json';require(path.exists(),'independent_E2_HTTP_integration_review_required')
    check=j.read(path);require(check['status']=='pass' and check.get('reviewed_by')=='root_agent'
        and check['actual_model_requests']==0 and check['full_schema_actual_HTTP_serialization_pass'],'E2_integration_review_not_passed')
    reviewed={str(Path(p['path']).resolve()):p['sha256'] for p in check['protected_inputs']}
    for p in [Path(__file__),Path(dev.__file__),Path(grounded.__file__),OUT/'plan.json',OUT/'matrix.json',OUT/'expected_contract.json',SELECTION]:
        require(reviewed.get(str(p.resolve()))==j.filehash(p),'E2_integration_review_stale:'+str(p))
    ids={c['planned_trial_id'] for c in j.read(OUT/'matrix.json')}
    own=[r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started' and r.get('trial_id') in ids]
    require(len(own)==len({r['trial_id'] for r in own}) and all(r['attempt']==1 for r in own),'E2_repeat_request_forbidden')
    require(before==plan['starting_requests']+len(own),'unexpected_parallel_requests_since_E2_freeze')
    if BACKEND_VERSION in ['v5','v6','v7']:
        require(len(ids)==21,'v5_E2_fixed_21_required')
        selected_budget_guard('E2',before,len(ids)-len(own))
    with wrapper(check_contract=True):await j.run(args(True))
    validate_preflight();record('run',new_requests=parent.request_count()-before)


# Transport/conversion adapter derived from selected dev backend; independent batch scope.
@contextlib.contextmanager
def wrapper(check_contract=False):
    original_runtime,original_contract,original_models,original_adapter=j.runtime,j.contract,j.model_configs,j.make_adapter
    cases=j.read(OUT/'cases.json')['cases'];lookup={casekey(c):c for c in cases}
    require(len(lookup)==21,'full_text_case_identity_collision');restore=[]
    def runtime(a):
        runner,api,registry=original_runtime(a);previous=runner.evaluate_response_with_teacher;restore.append((runner,previous))
        async def evaluate(teacher,question,answer,space,meta,template):
            c=lookup[(int(meta['question_id']),question,answer)];aid=c['control_id']
            doc=j.read(OUT/'source_documents'/f'{aid}.json')
            require(grounded.rawsha(answer)==doc['answer_sha256'],'runtime_full_answer_changed')
            expected=(OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
            suffix=parent.v2.reference_suffix(c)
            require(expected.endswith(suffix),'reference_evidence_suffix_changed')
            transformed=[];errors=[];raw_returns=[]
            cell=next(x for x in j.read(OUT/'matrix.json') if x['control_id']==aid)
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
            result[EXTRA_KEY]={'conversion':transformed[0] if transformed else None,
                'conversion_errors':errors,'raw_return_modified':False,'legacy_input_explicitly_projected':bool(transformed),
                'raw_source_bound_content_sha256':grounded.rawsha(raw_returns[0]) if raw_returns else None,
                'raw_return_file':str(attempt/'raw_source_bound_content.txt') if raw_returns else None,
                'legacy_parser_fallback_used':False,
                'selected_backend_version':BACKEND_VERSION,
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
        same_science(value,baseline,'original_science_or_demand_changed')
        value['source_bound_variant']={'version':'grounded_controls_v1',
            'selected_backend_version':BACKEND_VERSION,
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
            require(kwargs==expected_http_payload(public,kwargs['prompt']),'actual_full_HTTP_payload_drift')
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

METRICS=['sr','sp',*DIRECT,*EGES,'Com','Cor','Eff','IA','HV']

def anomaly_observations(pair):
    """Prespecified diagnostic flags, never corrected scores or scientific truth."""
    condition=pair['condition'];flags=[]
    target={'necessary_step_deletion':'sr','necessary_parameter_deletion':'c_param','evidence_supported_order_conflict':'co_order'}.get(condition)
    if target:
        value=pair['delta_'+target]
        flags.append({'metric':target,'observation':'unavailable' if value is None else 'expected_direction_decrease' if value < -1e-12 else 'no_response' if abs(value)<=1e-12 else 'opposite_direction_increase',
            'interpretation':'Developmental sensitivity observation; reference necessity/semantic accuracy not confirmed.'})
    if condition=='deterministic_equivalent_representation':
        flags += [{'metric':k,'observation':'unavailable' if pair['delta_'+k] is None else 'invariant' if abs(pair['delta_'+k])<=1e-12 else 'representation_drift'} for k in METRICS]
    if condition=='adjacent_entry_merge':
        flags += [{'metric':k,'observation':'unavailable' if pair['delta_'+k] is None else 'unchanged' if abs(pair['delta_'+k])<=1e-12 else 'observed_granularity_sensitivity',
            'zero_delta_was_not_original_prespecified_requirement':True} for k in ['sr','sp','Com']]
    return flags

def terminal_provenance(trial,cell,case,attempt,receipt,ledger):
    """Validate a terminal observation without requiring a provider to succeed.

    A local failure without a reserved request needs an explicit root-authored
    evidence record. This analyzer never manufactures such a record or fills an
    unrun matrix cell with a failure to make the denominator look complete.
    """
    tid=cell['planned_trial_id'];identity=cell['identity'];judge=identity['judge']
    require(tid==j.digest(identity) and trial.get('trial_id')==tid and trial.get('identity')==identity,
        'E2_terminal_trial_identity_mismatch')
    require(type(trial.get('attempt')) is int and trial['attempt']==1 and type(trial.get('repeat_index')) is int and trial['repeat_index']==0,
        'E2_terminal_attempt_or_repeat_mismatch')
    require(trial.get('case_id')==cell['case_id'] and trial.get('judge')==judge,
        'E2_terminal_case_or_judge_mismatch')
    require(trial.get('status') in ['success','failed'],'E2_terminal_status_invalid')
    require(type(trial.get('actual_api_request_made')) is bool and
        trial['actual_api_request_made']==(receipt is not None),'E2_actual_request_receipt_inconsistent')
    if receipt is not None:
        require(receipt==ledger.get(receipt.get('request_id')) and receipt.get('event')=='request_started'
            and receipt.get('request_id')==j.digest({'trial_id':tid,'attempt':1})
            and receipt.get('trial_id')==tid and receipt.get('attempt')==1 and receipt.get('model')==judge,
            'E2_receipt_trial_attempt_or_judge_mismatch')
        return {'receipt_present':True,'local_unrequested_failure_verified':False,'local_failure_reason':None}
    require(trial['status']=='failed','E2_success_without_request')
    require(not any(row.get('event')=='request_started' and row.get('trial_id')==tid for row in ledger.values()),
        'E2_local_failure_has_reserved_request')
    record_path=attempt/'local_failure_record.json'
    require(record_path.exists(),'E2_local_failure_source_record_required')
    record=j.read(record_path);evaluation=trial.get('evaluation') or {}
    require(record.get('status')=='documented_local_failure_before_request' and record.get('recorded_by')=='root_agent'
        and record.get('trial_id')==tid and record.get('identity')==identity and record.get('attempt')==1
        and record.get('actual_api_request_made') is False,'E2_local_failure_record_identity_mismatch')
    reason=record.get('reason')
    require(isinstance(reason,str) and bool(reason.strip()) and reason==evaluation.get('_error')
        and evaluation.get('technical_status')=='FAILED' and bool(evaluation.get('failure_stage')),
        'E2_local_failure_reason_not_bound_to_trial')
    require(record.get('answer_sha256')==grounded.rawsha(case['model_response']) and
        record.get('question_sha256')==grounded.rawsha(case['specific_question']),
        'E2_local_failure_full_source_mismatch')
    expected={'cases':OUT/'cases.json','source_document':OUT/'source_documents'/f"{cell['control_id']}.json",
        'prompt':OUT/'prompts'/f"{cell['control_id']}.txt",'matrix':OUT/'matrix.json',
        'contract':OUT/'expected_contract.json'}
    require(record.get('source_bindings')=={name:bind(path) for name,path in expected.items()},
        'E2_local_failure_frozen_source_bindings_mismatch')
    evidence=record.get('failure_evidence')
    require(isinstance(evidence,list) and bool(evidence),'E2_local_failure_error_evidence_required')
    for item in evidence:
        path=Path(item['path']).resolve()
        require(path.parent==attempt.resolve() and path.name in ['runner_log.json','local_error.json']
            and j.filehash(path)==item['sha256'],'E2_local_failure_error_evidence_changed')
    require(not any((attempt/name).exists() for name in ['http_request_payload.json','provider_response.json',
        'provider_error.json','raw_source_bound_content.txt']),'E2_unrequested_failure_has_provider_artifacts')
    return {'receipt_present':False,'local_unrequested_failure_verified':True,'local_failure_reason':reason,
        'source_record':bind(record_path)}

def analyze():
    validate_preflight();before=parent.request_count()
    cases={c['case_id']:c for c in j.read(OUT/'cases.json')['cases']};pairs=j.read(OUT/'pairs.json');matrix=j.read(OUT/'matrix.json')
    steps={r['case_id']:r for r in j.read(OUT/'step_results.json')};ledger={r['request_id']:r for r in j.ledger_rows(parent.LEDGER)}
    contract=j.read(OUT/'expected_contract.json');contract_hash=j.digest(contract)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,_,registry=j.runtime(args())
    rows=[];bindings=[];receipts=[]
    for cell in matrix:
        cid=cell['case_id'];ident=cell['control_id'];c=cases[cid];trial_id=cell['planned_trial_id']
        path=RUN/'trials'/f'{trial_id}.json';attempt=RUN/'attempts'/f'{trial_id}_1';receipt_path=attempt/'request_receipt.json'
        t=j.read(path) if path.exists() else None;e=(t or {}).get('evaluation') or {};status=(t or {}).get('status','not_run')
        receipt=j.read(receipt_path) if receipt_path.exists() else None
        provenance=None
        if receipt:
            require(receipt==ledger[receipt['request_id']] and receipt['trial_id']==trial_id and receipt['attempt']==1,'E2_receipt_mismatch')
            receipts.append(receipt)
        if t:
            provenance=terminal_provenance(t,cell,c,attempt,receipt,ledger)
            if (attempt/'prompt.txt').exists():require(j.filehash(attempt/'prompt.txt')==cell['prompt_file_sha256'],'actual_prompt_file_changed')
        payload_path=attempt/'http_request_payload.json';payload=j.read(payload_path) if payload_path.exists() else None
        if payload:
            require(receipt is not None,'HTTP_without_reserved_request')
            require(payload['format']==j.read(OUT/'schema.json') and payload['options']['num_ctx']==NUM_CTX and payload['options']['temperature']==0 and payload['options']['num_predict']==8192,'actual_HTTP_settings_changed')
            require(grounded.rawsha(payload['prompt'])==cell['prompt_raw_sha256'],'actual_HTTP_full_prompt_changed')
            require(payload==expected_http_payload(contract['models'][0]['settings'],payload['prompt']),'actual_full_HTTP_payload_changed')
        extra=e.get(EXTRA_KEY) or {};conversion=extra.get('conversion');raw=j.proposals(e)
        checked={k:None for k in raw};notes={};replay=None;conversion_replayed=False
        rawpath=attempt/'raw_source_bound_content.txt';raw_content=rawpath.read_bytes().decode('utf8') if rawpath.exists() else None
        if raw_content is not None:
            require(j.read(attempt/'provider_response.json')['response']==raw_content,'raw_provider_text_changed')
            require(j.read(attempt/'raw_source_bound_receipt.json')['raw_response_sha256']==grounded.rawsha(raw_content),'raw_content_receipt_changed')
        if status=='success':
            require(receipt is not None and payload is not None and conversion is not None and raw_content is not None,'successful_trial_missing_provenance')
            document=j.read(OUT/'source_documents'/f'{ident}.json')
            require(document['text']==c['model_response'] and document['source_id']==grounded.source_id_for_case(c),'source_document_identity_changed')
            replay_conversion=grounded.convert(raw_content,document)
            require(replay_conversion==conversion and j.read(attempt/'source_bound_conversion.json')==conversion,'source_conversion_not_reproducible')
            require(j.read(attempt/'projected_legacy_payload.json')==conversion['legacy_runner_payload'],'projection_sidecar_changed')
            require((attempt/'projected_legacy_content.txt').read_text(encoding='utf8')==conversion['legacy_runner_content'],'projection_content_changed')
            require(e['extraction']==conversion['legacy_projection']['extraction'],'runner_extraction_changed')
            require(e['legacy_diagnostics']['raw_teacher_scores']==conversion['legacy_runner_payload']['scores'],'direct_scores_changed')
            demand=registry.get(c['question_id'],c['specific_question']);require(e['user_preference_vector']==demand,'demand_vector_changed')
            meta=runner.QUESTION_META_KB[registry.questions[str(c['question_id'])]['question_id']]
            replay=runner.calculate_effectiveness_score(e['quantitative_data'],demand,runner.MODEL_SPACE_SIGNED,e['extraction']['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(dev.same(replay[k],raw[k]) for k in EGES),'original_EGES_replay_failed')
            checked,notes=dev.gate_components(raw,conversion,replay);conversion_replayed=True
            j.save(OUT/'conversion_replays'/f'{ident}.json',replay_conversion)
        if (attempt/'source_bound_conversion_error.json').exists():
            error=j.read(attempt/'source_bound_conversion_error.json')
            require(error['legacy_parser_fallback_permitted'] is False and not (attempt/'projected_legacy_payload.json').exists(),'conversion_error_legacy_fallback')
        technical=status=='success' and conversion_replayed;original_step=steps[cid]['step_result']
        values=derive_primary(original_step,checked);evidence=dev.evidence_state(conversion)
        full_numeric=technical and all(finite(values[k]) for k in METRICS)
        rows.append({'control_id':ident,'case_id':cid,'question_id':c['question_id'],'condition':c['condition'],'status':status,
            'trial_id':trial_id,'request_index':receipt['package_request_index'] if receipt else None,
            'terminal_provenance':provenance,
            'technical_pipeline_complete':technical,'evidence_state':evidence,'complete_numeric':full_numeric,
            'direct_and_EGES_numeric_count':sum(finite(checked[k]) for k in DIRECT+EGES),'direct_and_EGES_denominator':9,
            'raw_original_numeric_proposals':raw,'component_gated_proposals':checked,'component_gate_notes':notes,
            'candidate_raw_and_derived':values,'original_step_result':original_step,
            'step_score_available_independent_of_judge':finite(original_step['sr']) and finite(original_step['sp']),
            'source_full_answer_sha256':grounded.rawsha(c['model_response']),'source_id':cell['source_id'],
            'references_sha256':j.digest(c['references']),'question_sha256':grounded.rawsha(c['specific_question']),
            'judge_contract_sha256':contract_hash,'step_config_sha256':j.filehash(OUT/'step_config.json'),
            'original_EGES_replay':replay,'source_conversion_replayed':conversion_replayed,
            'failure_details':{k:e.get(k) for k in ['failure_stage','_error','_error_type']},'conversion_errors':extra.get('conversion_errors'),
            'fact_acceptance':'pending_separate_control_fact_review' if conversion else 'unavailable_no_valid_conversion',
            'formal_eligible':False,'scientific_accuracy_claimed':False,
            'numeric_NA_reasons':{k:('technical_failure_or_not_run' if not technical and k not in ['sr','sp'] else 'upstream_component_or_dependency_unresolved') for k in METRICS if not finite(values[k])}})
        if t:bindings += [bind(p) for p in [path,*sorted(f for f in attempt.glob('*') if f.is_file())]]
    byid={r['case_id']:r for r in rows};paired=[]
    for p in pairs:
        a,b=(byid[p[k]] for k in ['baseline_case_id','variant_case_id'])
        same=all(a[k]==b[k] and a[k] is not None for k in ['judge_contract_sha256','step_config_sha256','references_sha256','question_sha256'])
        both= same and a['technical_pipeline_complete'] and b['technical_pipeline_complete']
        row={**p,'same_frozen_configuration':same,'both_arms_technical_complete':both,
            'baseline_status':a['status'],'variant_status':b['status'],
            'complete_numeric_pair':both and a['complete_numeric'] and b['complete_numeric'],'formal_eligible':False}
        for metric in METRICS:
            av,bv=a['candidate_raw_and_derived'][metric],b['candidate_raw_and_derived'][metric]
            available=same and finite(av) and finite(bv) and (metric in ['sr','sp'] or both)
            row.update({'baseline_'+metric:av,'variant_'+metric:bv,'delta_'+metric:bv-av if available else None,'available_'+metric:available})
        row['response_observations']=anomaly_observations(row);paired.append(row)
    condition=[]
    for name in sorted({p['condition'] for p in paired}):
        group=[p for p in paired if p['condition']==name];r={'condition':name,'planned_pairs':len(group),
            'both_arms_technical_complete':sum(p['both_arms_technical_complete'] for p in group),'complete_numeric_pairs':sum(p['complete_numeric_pair'] for p in group)}
        for metric in METRICS:
            values=[p['delta_'+metric] for p in group if p['available_'+metric]]
            r.update({f'{metric}_available_pairs':len(values),f'{metric}_negative':sum(v < -1e-12 for v in values),
                f'{metric}_unchanged':sum(abs(v)<=1e-12 for v in values),f'{metric}_positive':sum(v>1e-12 for v in values)})
        condition.append(r)
    require(len(rows)==21 and len(paired)==15 and len(receipts)==len({r['trial_id'] for r in receipts}),'denominator_or_duplicate_request_changed')
    planned_ids={r['planned_trial_id'] for r in matrix};own=[r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started' and r.get('trial_id') in planned_ids]
    require(len(own)==len(receipts)<=21,'request_accounting_mismatch')
    summary={'status':'experiment_complete' if all(r['status'] in ['success','failed'] for r in rows) else 'partial_batch_analysis',
        'selected_backend_version':BACKEND_VERSION,
        'planned_answers':21,'actual_terminal_answers':sum(r['status'] in ['success','failed'] for r in rows),'planned_pairs':15,
        'new_model_requests':len(receipts),'reused_model_trials':0,'technical_complete':sum(r['technical_pipeline_complete'] for r in rows),
        'evidence_unresolved':sum(r['evidence_state']['unresolved'] for r in rows),'complete_numeric':sum(r['complete_numeric'] for r in rows),
        'technical_complete_pairs':sum(p['both_arms_technical_complete'] for p in paired),'complete_numeric_pairs':sum(p['complete_numeric_pair'] for p in paired),
        'per_component_numeric':{k:sum(finite(r['candidate_raw_and_derived'][k]) for r in rows) for k in METRICS},
        'per_component_denominator':21,'condition_results':condition,'all_pairs_same_contract':all(p['same_frozen_configuration'] for p in paired),
        'original_SR_only_in_Com':True,'SP_is_companion_not_Com_term':True,'supplement':supplementary_steps_binding(),
        'fact_acceptance':'pending_independent_control_evidence_review','formal_eligible':False,'expert_returns':0,'scientific_accuracy_claimed':False,
        'new_analysis_requests':0,'bound_actual_artifacts':bindings}
    for name,value in [('per_answer.json',rows),('paired_results.json',paired),('condition_summary.json',condition),('completion_summary.json',summary)]:j.save(OUT/name,value)
    core.table(OUT/'per_answer.csv',[{k:r[k] for k in ['control_id','case_id','question_id','condition','status','technical_pipeline_complete','complete_numeric']}|r['candidate_raw_and_derived'] for r in rows])
    core.table(OUT/'paired_results.csv',paired);core.table(OUT/'condition_summary.csv',condition)
    j.save(OUT/'analysis_verification.json',{'status':'pass','all_21_answers_and_15_pairs_retained':True,'original_step_source':bind(OUT/'step_results.json'),
        'successful_original_EGES_replays':sum(r['source_conversion_replayed'] for r in rows),'same_pair_contracts_checked':15,
        'raw_projection_and_receipt_hash_checks':True,'new_model_requests':0,'formal_eligible':False})
    require(parent.request_count()==before,'analysis_generated_request');validate_preflight();record('analyze',new_requests=0)
    print(j.canonical({k:v for k,v in summary.items() if k not in ['bound_actual_artifacts','condition_results']}))

def draft(version):
    """Offline material inspection; no selection, actual OUT, or service access."""
    global dev,grounded,BACKEND_VERSION,EXTRA_KEY,SourceBoundConversionError
    backend_files(version)
    require(not OUT.exists(),'draft_must_not_write_or_audit_an_actual_E2_batch')
    target=BASE/'optimizer_20261010/grounded_controls_design_v1'/f'{version}_draft'
    dev=importlib.import_module(f'cce_grounded_development_{version}')
    grounded=importlib.import_module(f'cce_grounded_extraction_{version}')
    BACKEND_VERSION=version;EXTRA_KEY='grounded_extraction_'+version;SourceBoundConversionError=dev.SourceBoundConversionError
    configure_context(version)
    data,pairs=build_grounded_inputs(grounded);checks=[]
    def check(name,value=True):require(value,'draft_check_failed:'+name);checks.append({'check':name,'pass':True})
    def rejects(name,call):
        try:call()
        except ValueError as exc:checks.append({'check':name,'pass':True,'rejected':str(exc)});return
        raise ValueError('draft_expected_rejection:'+name)
    check('21_fulltexts_15_pairs',len(data)==21 and len(pairs)==15)
    check('21_unique_prompts',len({r['prompt_sha256'] for r in data})==21)
    check('all_21_fresh_no_reuse',all(not r['reuse_trial'] for r in data))
    check('legacy_context_versions_retained',CONTEXT_BY_BACKEND=={'v2':40960,'v3':40960,'v4':98304,'v5':98304,'v6':98304,'v7':98304})
    original=j.read(model_probe.OUT/'model_config.json');config=__import__('copy').deepcopy(original)
    if version in ['v4','v5','v6','v7']:config['models'][0]['num_ctx']=NUM_CTX
    configure_context(version,config)
    check('primary_only_explicit_context_changed',{k:v for k,v in config['models'][0].items() if k!='num_ctx'}=={k:v for k,v in original['models'][0].items() if k!='num_ctx'})
    bad=__import__('copy').deepcopy(config);bad['models'][0]['num_ctx']=98304
    rejects('v2_cannot_silently_gain_v4_context',lambda:configure_context('v2',bad))
    rejects('v3_cannot_silently_gain_v4_context',lambda:configure_context('v3',bad))
    configure_context(version,config)
    public={'model':config['models'][0]['model_name'],'num_ctx':NUM_CTX,'enable_thinking':False}
    for i,row in enumerate(data,1):
        prompt=row['actual_full_prompt'];payload=expected_http_payload(public,prompt,grounded.schema())
        check(f'HTTP_shape_fulltext_{i:02d}',payload['prompt']==prompt and payload['format']==grounded.schema() and payload['options']=={'num_predict':8192,'temperature':0.,'num_ctx':NUM_CTX})
    rejects('HTTP_wrong_context_rejected',lambda:expected_http_payload({**public,'num_ctx':1},'SYNTHETIC',{}))
    rows=[{**r['external_metadata'],'source_id':r['source_document']['source_id'],'answer_sha256':r['source_document']['answer_sha256'],
        'prompt_sha256':r['prompt_sha256'],'references_sha256':r['references_sha256'],
        'conservative_context_bound':len(r['actual_full_prompt'].encode('utf8'))+8192+256,
        'configured_num_ctx':NUM_CTX,'reuse_trial':False,'actual_request_made':False} for r in data]
    bound=[Path(__file__),Path(dev.__file__),Path(grounded.__file__),SOURCE/'cases.json',SOURCE/'pairs.json',model_probe.OUT/'model_config.json']
    if version in ['v4','v5','v6','v7']:bound.append(CONTEXT_CONFIGURATION)
    if version in ['v5','v6','v7']:bound.extend(allocation_dependencies())
    summary={'status':'draft_only_no_selection_prepare_preflight_or_generation','backend_version':version,'planned_new_requests':21,'planned_pairs':15,'settings':dict(SETTINGS),
        'script_sha256':j.filehash(__file__),'grounded_module_sha256':j.filehash(grounded.__file__),'schema_sha256_canonical':j.digest(grounded.schema()),
        'checks':checks,'checks_count':len(checks),'all_fulltexts_and_references_preserved':True,'new_model_requests':0,'service_metadata_requests':0,
        'actual_run_directory_created':False,'root_selection_created':False,'not_full_HTTP_integration_validation':True,
        'frozen_backend_requirements':['root selected_backend='+version+' and complete five actual dev/fact files','selected development model_config.json and context_configuration.json hashes','E2 independent full HTTP integration after prepare'],
        'allocation_guard':selected_budget_guard('E2',232 if version=='v7' else 227 if version=='v6' else 222,21) if version in ['v5','v6','v7'] else None,
        'bindings':[bind(p) for p in bound],'actual_command':[sys.executable,*sys.argv]}
    j.save(target/'draft_check.json',summary);j.save(target/'input_matrix.json',rows);j.save(target/'draft_model_config.json',config)
    (target/'README.md').write_text('# E2 '+version+' scheduler draft\n\n21 fresh full texts and 15 fixed pairs; all failures retained. No selection, prepare, preflight or generation was performed. v2/v3 stay at 40960; v4/v5/v6/v7 explicitly use 98304. The selected development model configuration and source/schema remain exact.\n\nv5 additionally binds the dated dev25-to30 allocation amendment. Its 21-request phase must preserve 57 later cells (25 E4 plus 32 confirmation). v6 instead binds dev30-to35, retains 49 later cells (25 E4 plus 24 confirmation/optional blind), and cannot spend the three unallocated calls. v7 binds dev35-to40, reserves 41 later cells (25 E4 plus 16 primary), disables optional blind before confirmation and leaves six calls unallocated. The original G01 budget clause was amended, not retrospectively passed. See draft_check.json for actual commands and bindings.\n',encoding='utf8')
    require(not OUT.exists(),'draft_created_actual_E2_directory')
    print(j.canonical({'status':summary['status'],'checks':len(checks),'new_model_requests':0,'context':NUM_CTX,'fulltexts':21,'pairs':15}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['draft','self-check','prepare','preflight','run','analyze'])
    parser.add_argument('--backend',choices=list(CONTEXT_BY_BACKEND),default='v4')
    parser.add_argument('--allow-local-calls',action='store_true');options=parser.parse_args()
    if options.action=='run':require(options.allow_local_calls,'run_requires_allow_local_calls');asyncio.run(run())
    elif options.action in ['draft','self-check']:draft(options.backend)
    else:{'prepare':prepare,'preflight':preflight,'analyze':analyze}[options.action]()
