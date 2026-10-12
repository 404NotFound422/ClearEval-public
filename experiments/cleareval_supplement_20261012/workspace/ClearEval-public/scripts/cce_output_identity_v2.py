"""One generic marker-identity prompt intervention on the frozen output-contract v1.

Only the original five exposed development answers are included. No schema, label
dictionary, score range, EGES, parsing, or post-generation normalization changes.
"""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import difflib
import io
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_output_contract_v1 as parent
import cce_judges as j
import cce_alternative_development as helper
import evaluator_integrity as integrity

OUT=ROOT/'artifacts/cce_validation/judges/output_identity_v2'
RUN=OUT/'run'
LEDGER=parent.LEDGER
ANCHOR='3.1 荧光标记字典 (marker_dict)\n'
INSTRUCTION=(
    '\n[MARKER IDENTITY PRESERVATION]\n'
    'For marker_dict keys, preserve the complete identity explicitly written in MODEL_PROTOCOL, '
    'including stated numeric suffixes and other distinguishing qualifiers. If a summary uses '
    'a generic family name but the body explicitly distinguishes complete names, do not collapse '
    'those distinct names to the generic family key. Do not infer, complete, or replace names '
    'from examples or prior knowledge. A generic name alone is not evidence of a specific member. '
    'Do not infer a target assignment from order, co-occurrence, or a shared generic family. '
    'When the same complete identity has an unresolved target relationship, preserve the original '
    'uncertainty rules and describe the ambiguity in extraction.reasoning rather than inventing '
    'a mapping or duplicating a key.\n\n'
)


def require(ok,why):
    if not ok:raise ValueError(why)


def arguments(allow=False):
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'local_config_snapshot.json',
        models=[parent.MODEL],question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None,ledger=LEDGER,total_budget=300,external_request_count=0,max_calls=5,
        max_attempts=1,repeats=1,temperature=0.0,max_output_tokens=8192,timeout_seconds=600,allow_api=allow)


def record(command,**details):
    p=OUT/'actual_execution_commands.json';rows=j.read(p) if p.exists() else []
    argv=[sys.executable,'scripts/cce_output_identity_v2.py',command]
    if command=='run':argv+=['--allow-local-calls']
    rows.append({'utc':j.now(),'argv':argv,'cwd':str(ROOT),'script_sha256':j.filehash(__file__),
        'package_requests_snapshot':parent.request_count(),**details})
    j.save(p,rows)


def validate():
    parent.validate_plan()
    plan=j.read(OUT/'plan.json')
    for entry in plan['frozen_inputs']+plan['protected_originals']:
        require(j.filehash(entry['path'])==entry['sha256'],'frozen_input_changed:'+Path(entry['path']).name)
    return plan


def extend(text):
    require(text.count(ANCHOR)==1,'identity_rule_anchor_not_unique')
    return text.replace(ANCHOR,ANCHOR+INSTRUCTION,1)


def transform(original):return extend(parent.transform(original))


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():
        validate();record('prepare',status='frozen_plan_reused',new_requests=0)
        print(j.canonical({'status':'frozen_plan_reused','new_requests':0}));return
    require(not list(RUN.glob('attempts/*/request_receipt.json')),'existing_requests_prevent_prepare')
    parent_plan=parent.validate_plan();before=parent.request_count()
    require(before+5<=300,'insufficient_budget')
    require(len(parent_plan['matrix'])==5,'parent_fixed_five_changed')
    for name in ['cases.json','local_config_snapshot.json','final_output_schema.json']:
        (OUT/name).write_bytes((parent.OUT/name).read_bytes())
    cases=j.read(OUT/'cases.json')['cases']
    require([c['anonymous_answer_id'] for c in cases]==parent.IDS,'original_development_selection_changed')
    rubric=(parent.OUT/'rubric_canonical_no_examples.txt').read_text(encoding='utf-8')
    changed=extend(rubric)
    (OUT/'rubric_identity_preserved.txt').write_text(changed,encoding='utf-8')
    (OUT/'marker_identity_rule.txt').write_text(INSTRUCTION,encoding='utf-8')
    (OUT/'rubric_v1_to_v2.diff').write_text(''.join(difflib.unified_diff(rubric.splitlines(keepends=True),
        changed.splitlines(keepends=True),fromfile='frozen/output_contract_v1',tofile='output_identity_v2')),encoding='utf-8')
    require(changed.replace(INSTRUCTION,'',1)==rubric,'more_than_one_prompt_insertion')
    require(not any(s in INSTRUCTION for s in ['Alexa','GFP','MAP2','A04','488','647']),'case_specific_name_or_example_in_rule')
    files=[OUT/n for n in ['cases.json','local_config_snapshot.json','final_output_schema.json',
        'rubric_identity_preserved.txt','marker_identity_rule.txt','rubric_v1_to_v2.diff']]
    matrix=[]
    for case in cases:
        aid=case['anonymous_answer_id'];previous=(parent.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf-8')
        original=helper.exact_runner_prompt(case);revised=transform(original)
        require(revised==extend(previous),'parent_prompt_not_exactly_reproduced')
        require(revised.replace(INSTRUCTION,'',1)==previous,'non_identity_prompt_change')
        for key in ['specific_question','model_response']:
            require(previous.count(case[key])==revised.count(case[key])==1,'full_question_or_answer_changed')
        require(revised.endswith(parent.v2.reference_suffix(case)),'supplied_reference_context_changed')
        bound=len(revised.encode('utf-8'))+8192+256
        require(bound<=40960,'conservative_context_bound_exceeded')
        prompt=OUT/'prompts'/f'{aid}_prompt.txt';prompt.parent.mkdir(exist_ok=True)
        prompt.write_text(revised,encoding='utf-8');files.append(prompt)
        diff=OUT/'prompts'/f'{aid}_v1_to_v2.diff'
        diff.write_text(''.join(difflib.unified_diff(previous.splitlines(keepends=True),revised.splitlines(keepends=True),
            fromfile=aid+'/output_contract_v1',tofile=aid+'/output_identity_v2')),encoding='utf-8');files.append(diff)
        old=next(r for r in parent_plan['matrix'] if r['anonymous_answer_id']==aid)
        matrix.append({**old,'prompt_sha256':j.filehash(prompt),'prompt_raw_utf8_sha256':parent.rawsha(revised),
            'conservative_context_bound':bound,'parent_prompt_sha256':j.filehash(parent.OUT/'prompts'/f'{aid}_prompt.txt'),
            'only_generic_identity_instruction_inserted':True})
    delta={'intervention':'one_generic_marker_identity_preservation_instruction',
        'parent_prompt_version':'output_contract_v1','all_other_prompt_text_byte_equal_after_removing_insertion':True,
        'schema_bytes_unchanged':j.filehash(OUT/'final_output_schema.json')==j.filehash(parent.OUT/'final_output_schema.json'),
        'decoder_and_model_settings_unchanged':True,'five_score_scales_and_EGES_unchanged':True,
        'same_strict_duplicate_parser':True,'same_v1_error_provenance_adapter':True,
        'scientific_lexicon_or_knowledge_base_changes':False,'new_schema_fields':False,
        'case_specific_names_or_examples_in_added_instruction':False,
        'upstream_reason_copying_or_semantic_fidelity_resolved':False,
        'rule_origin':'Exposed development A04 showed distinct full names in body but repeated generic output keys. This informed a general preservation rule, not a held-out accuracy claim.',
        'knowledge_base_boundary':'No lookup/alias changes. If faithfully preserved full names are unresolved by the old knowledge base, the old NA behavior remains; no inferred aliases or target assignments.'}
    j.save(OUT/'config_delta.json',delta);files.append(OUT/'config_delta.json')
    protected=[parent.OUT/'plan.json',parent.OUT/'software_probes.json',parent.OUT/'preflight_verification.json',
        parent.OUT/'analysis/completion_summary.json',parent.OUT/'analysis/A04_name_collision_trace.json',
        ROOT/'scripts/cce_output_contract_v1.py',ROOT/'scripts/cce_judges.py',ROOT/'evaluator_integrity.py',
        ROOT/'OEQ_run_grading_new.py',ROOT/'models/Ollama_LLM.py']
    protected += [Path(e['path']) for e in parent_plan['protected_originals']]
    for p in (parent.RUN).rglob('*'):
        if p.is_file():protected.append(p)
    files += [Path(__file__).resolve(),parent.OUT/'cases.json',parent.OUT/'local_config_snapshot.json',
        parent.OUT/'final_output_schema.json',parent.OUT/'rubric_canonical_no_examples.txt']
    plan={'status':'frozen_before_generation','version':'output_identity_v2','created_utc':j.now(),'matrix':matrix,
        'planned_new_requests':5,'judge':parent.MODEL,'repeats':1,'max_attempts':1,'temperature':0,
        'max_output_tokens':8192,'num_ctx':40960,'timeout_seconds':600,'decoder_format':'json',
        'package_requests_snapshot':before,'total_budget':300,'formal_eligible':False,'expert_confirmation':None,
        'single_prompt_intervention':True,'source_selection':'Exactly the original fixed A01–A05; no selection by scores or success.',
        'technical_gate':'All five must pass the unchanged strict parser/field validator; separately report full-pipeline and numeric availability.',
        'continuation_policy':'No automatic next stage, holdout call or retry. Root reviews this separately frozen five-case development experiment.',
        'no_heldout_scientific_output_access':True,'no_expert_packet_replacement':True,
        'interpretation_limit':'A development identity-preservation intervention; not proof of correct targets, science, or general extraction fidelity.',
        'frozen_inputs':[parent.bind(p) for p in dict.fromkeys(files)],
        'protected_originals':[parent.bind(p) for p in dict.fromkeys(protected)],
        'run_not_executed_command':[sys.executable,'scripts/cce_output_identity_v2.py','run','--allow-local-calls']}
    j.save(OUT/'plan.json',plan);validate()
    require(parent.request_count()==before,'prepare_made_request')
    record('prepare',status='completed',new_requests=0,plan_sha256=j.filehash(OUT/'plan.json'))
    print(j.canonical({'status':'prepared_not_executed','fixed_cases':5,'new_requests':0,
        'context_bounds':[r['conservative_context_bound'] for r in matrix],'package_requests_snapshot':before}))


def self_check():
    plan=validate();before=parent.request_count();checks=[]
    for cell in plan['matrix']:
        aid=cell['anonymous_answer_id'];p=(OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf-8')
        baseline=(parent.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf-8')
        require(p.count(INSTRUCTION)==1 and p.replace(INSTRUCTION,'',1)==baseline,'single_prompt_insertion')
        checks.append({'kind':'actual_prompt_identity','anonymous_answer_id':aid,'single_generic_insertion_only':True})
    obj={'scores':{'completeness':{k:{'score':None,'reasoning':'SYNTHETIC_ONLY'} for k in ['c_step','c_param']},
          'correctness':{k:{'score':None,'reasoning':'SYNTHETIC_ONLY'} for k in ['co_order','co_method','co_param','co_chem']}},
         'extraction':{'method_name':None,'clearing_total_time_hours':None,
                       'marker_dict':{'SYNTHETIC_ID_101':'','SYNTHETIC_ID_102':''}}}
    parsed=integrity.parse_judge_object(j.canonical(obj));parent.core_gate(parsed)
    require(parsed==obj,'synthetic_complete_id_values_modified')
    checks.append({'kind':'synthetic_only','fixture':'two_distinct_full_id_keys','strict_original_gate_accepts':True,'inference_about_model_behavior':False})
    duplicate='{"SYNTHETIC_ID_101":"A","SYNTHETIC_ID_101":"A"}'
    try:integrity.parse_judge_object(duplicate)
    except integrity.JudgeFormatError:checks.append({'kind':'synthetic_only','fixture':'same_full_id_duplicate','strictly_rejected':True})
    else:raise ValueError('strict_duplicate_policy_changed')
    require(j.filehash(OUT/'final_output_schema.json')==j.filehash(parent.OUT/'final_output_schema.json'),'new_schema_shape_changed')
    checks.append({'kind':'schema_byte_identity','same_as_parent':True,'new_fields':False})
    require(parent.request_count()==before,'software_probe_made_request');validate()
    j.save(OUT/'software_probes.json',{'status':'pass','checks':checks,'new_requests':0,
        'synthetic_samples_are_not_scientific_or_expert_evidence':True,'script_sha256':j.filehash(__file__),
        'plan_sha256':j.filehash(OUT/'plan.json'),'parent_11_structure_probes':parent.bind(parent.OUT/'software_probes.json')})
    record('self-check',status='completed',new_requests=0,checks=len(checks))
    print(j.canonical({'status':'offline_checks_pass','checks':len(checks),'new_requests':0}))


@contextlib.contextmanager
def wrapper():
    old_runtime,old_contract,old_adapter=j.runtime,j.contract,j.make_adapter
    cases=j.read(OUT/'cases.json')['cases'];restore=[]
    def runtime(args):
        runner,api,registry=old_runtime(args);previous=runner.evaluate_response_with_teacher;restore.append((runner,previous))
        async def evaluate(teacher,question,answer,space,meta,template):
            case=next(c for c in cases if c['question_id']==meta['question_id'])
            require(question==case['specific_question'] and answer==case['model_response'],'runtime_original_case_changed')
            class Teacher:
                model_name=teacher.model_name
                async def _acall(self,prompt):
                    revised=transform(prompt)
                    expected=(OUT/'prompts'/f"{case['anonymous_answer_id']}_prompt.txt").read_text(encoding='utf-8')
                    require(revised+parent.v2.reference_suffix(case)==expected,'runtime_prompt_not_frozen')
                    return await teacher._acall(revised)
            result=await previous(Teacher(),question,answer,space,meta,template)
            provider=((result.get('teacher_generation') or {}).get('metadata') or {}).get('provider_response')
            if provider is not None:result['output_contract_diagnostic']=parent.classify(provider)
            result['prompt_variant_provenance']={'variant':'output_identity_v2','plan_sha256':j.filehash(OUT/'plan.json'),
                'parent_output_contract_script_sha256':j.filehash(ROOT/'scripts/cce_output_contract_v1.py'),
                'raw_return_modified':False,'lexicon_or_EGES_modified':False}
            return result
        runner.evaluate_response_with_teacher=evaluate;return runner,api,registry
    def contract(args,runner,registry,models):
        original=old_contract(args,runner,registry,models)
        require(original['files']==j.read(parent.DEV/'frozen_judge_contract.json')['files'],'original_scoring_files_drift')
        return {**original,'output_identity_variant':{'id':'output_identity_v2','plan_sha256':j.filehash(OUT/'plan.json'),
            'script_sha256':j.filehash(__file__),'generic_identity_rule_sha256':j.filehash(OUT/'marker_identity_rule.txt'),
            'parent_contract_script_sha256':j.filehash(ROOT/'scripts/cce_output_contract_v1.py'),
            'schema_sha256':j.filehash(OUT/'final_output_schema.json'),'same_parent_adapter_provenance':True}}
    def adapter(public,api_type):
        require(public['transport_kind']=='ollama_loopback' and public['format']=='json','unexpected_transport')
        api=old_adapter(public,api_type);previous=api._acall
        async def call(prompt):
            try:return await previous(prompt)
            except Exception as exc:
                recovered=parent.completed_json_failure_payload(api.last_response,exc,api.model_name,public['max_output_tokens'])
                if recovered is None:raise
                return recovered
        api._acall=call;return api
    j.runtime,j.contract,j.make_adapter=runtime,contract,adapter
    try:yield
    finally:
        for runner,previous in reversed(restore):runner.evaluate_response_with_teacher=previous
        j.runtime,j.contract,j.make_adapter=old_runtime,old_contract,old_adapter


def require_probes():
    p=j.read(OUT/'software_probes.json')
    require(p['status']=='pass' and p['script_sha256']==j.filehash(__file__) and p['plan_sha256']==j.filehash(OUT/'plan.json'),
            'current_software_probes_required')


def preflight():
    validate();require_probes();before=parent.request_count()
    with wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(arguments())
    matrix=[]
    for case in cases:
        identity={'case_id':case['case_id'],'input_sha256':case['input_sha256'],'judge':parent.MODEL,
                  'repeat_index':0,'contract_sha256':j.digest(contract)}
        matrix.append({'anonymous_answer_id':case['anonymous_answer_id'],'identity':identity,
                       'planned_trial_id':j.digest(identity),'attempt':1})
    require(len(matrix)==len({x['planned_trial_id'] for x in matrix})==5,'five_unique_planned_cells')
    require(parent.request_count()==before,'metadata_preflight_made_generation');validate()
    j.save(OUT/'preflight_verification.json',{'status':'pass','planned_trials':matrix,'new_requests':0,
        'plan_sha256':j.filehash(OUT/'plan.json'),'script_sha256':j.filehash(__file__),
        'contract_sha256':j.digest(contract),'local_metadata_only':True,'generation_endpoint_called':False})
    record('preflight',status='completed',new_requests=0,contract_sha256=j.digest(contract))
    print(j.canonical({'status':'preflight_pass','planned_calls':5,'new_requests':0,'contract_sha256':j.digest(contract)}))


async def run():
    validate();require_probes()
    pre=j.read(OUT/'preflight_verification.json')
    require(pre['status']=='pass' and pre['plan_sha256']==j.filehash(OUT/'plan.json') and pre['script_sha256']==j.filehash(__file__),'current_preflight_required')
    before=len(list(RUN.glob('attempts/*/request_receipt.json')))
    with wrapper():await j.run(arguments(True))
    validate();after=len(list(RUN.glob('attempts/*/request_receipt.json')))
    require(after<=5,'call_cap_exceeded')
    record('run',status='completed_runner_return',new_requests=after-before,batch_receipts=after)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','self-check','preflight','run'])
    p.add_argument('--allow-local-calls',action='store_true');args=p.parse_args()
    if args.command=='run':
        require(args.allow_local_calls,'run_requires_explicit_allow_local_calls');asyncio.run(run())
    else:{'prepare':prepare,'self-check':self_check,'preflight':preflight}[args.command]()
