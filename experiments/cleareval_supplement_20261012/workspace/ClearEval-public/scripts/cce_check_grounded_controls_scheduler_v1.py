"""Unfrozen E2 code smoke checks. Does not call prepare/preflight/run/analyze."""
from __future__ import annotations
import ast
import importlib
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_controls_v1 as candidate

def main():
    checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append({'check':name,'pass':True})
    before=candidate.parent.request_count()
    output_existed=candidate.OUT.exists()
    source=Path(candidate.__file__).read_text(encoding='utf8')
    tree=ast.parse(source)
    compile(source,str(candidate.__file__),'exec')
    declared={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    check('four_scheduler_entrypoints_present',{'prepare','preflight','run','analyze'}<=declared)
    cases,pairs=candidate.inputs()
    check('fixed_full_text_population',len(cases)==21 and len(pairs)==15)
    check('three_questions_only',{c['question_id'] for c in cases}=={2,21,22})
    v3_files=candidate.backend_files('v3')
    check('v3_backend_paths_explicit',v3_files['development'].name=='cce_grounded_development_v3.py'
        and v3_files['grounded'].name=='cce_grounded_extraction_v3.py' and v3_files['fact_checker'].name=='cce_audit_grounded_facts_v3.py')
    try:candidate.backend_files('latest')
    except ValueError:check('implicit_unversioned_backend_rejected',True)
    else:raise AssertionError('implicit_backend_accepted')
    config=candidate.j.read(candidate.SOURCE/'step_config.json')
    check('unchanged_original_core_encoder_threshold',config['adapter_sha256']==candidate.j.filehash(candidate.core.__file__)
        and config['encoder']['model']=='all-mpnet-base-v2' and config['threshold']==.7)
    check('unchanged_original_reference_file',config['references_file_sha256']==candidate.j.filehash(candidate.SOURCE/'references.json'))
    if not candidate.SELECTION.exists():
        try:candidate.selection()
        except ValueError as error:
            check('missing_internal_selection_rejected',str(error)=='root_candidate_selection_missing_no_prepare_or_generation')
        else:raise AssertionError('missing_selection_was_accepted')
    # Pure serializer expectation: no server lookup or generation is exercised.
    original_read=candidate.j.read
    schema={'type':'object','properties':{'dummy':{'type':'string'}},'additionalProperties':False}
    def memory_read(path):
        if Path(path)==candidate.OUT/'schema.json':return schema
        return original_read(path)
    candidate.j.read=memory_read
    try:
        public={'model':'synthetic-local-model','enable_thinking':False}
        payload=candidate.expected_http_payload(public,'synthetic complete prompt')
        check('full_HTTP_expectation',payload=={'model':'synthetic-local-model','prompt':'synthetic complete prompt',
            'options':{'num_predict':8192,'temperature':0.,'num_ctx':40960},'stream':False,'format':schema,'think':False})
        check('nullable_thinking_does_not_add_flag','think' not in candidate.expected_http_payload({'model':'synthetic-local-model','enable_thinking':None},'synthetic'))
    finally:candidate.j.read=original_read
    grounded_v3=importlib.import_module('cce_grounded_extraction_v3')
    draft_before=candidate.bind(Path(grounded_v3.__file__))
    payloads,_=candidate.build_grounded_inputs(grounded_v3)
    check('all21_v3_full_inputs_constructed',len(payloads)==21 and all(p['reuse_trial'] is False and p['reextract_edited_full_text'] for p in payloads))
    measured_path=candidate.BASE/'optimizer_20261010/grounded_controls_design_v1/context_probe_v3_snapshot.json'
    measured=original_read(measured_path);lookup={r['case_id']:r for r in measured['matrix']}
    check('v3_prompts_equal_measured_context_snapshot',all(p['prompt_sha256']==lookup[p['external_metadata']['case_id']]['prompt_raw_sha256'] for p in payloads)
        and draft_before in measured['inputs'] and measured['over_limit']==0)
    check('all21_v3_source_reconstructions_exact',all(''.join(u['text'] for u in p['source_document']['units'])==c['model_response'] for c,p in zip(cases,payloads)))
    doc,synthetic=grounded_v3.synthetic_fixture();raw=grounded_v3.canonical(synthetic);conversion=grounded_v3.convert(raw,doc)
    check('v3_conversion_interface_compatible',all(k in conversion for k in ['raw_response_sha256','source_audit','legacy_projection','legacy_runner_payload','legacy_runner_content'])
        and conversion['raw_response_sha256']==grounded_v3.rawsha(raw))
    check('v3_conversion_preserves_raw_and_direct_scores',conversion['raw_content_preserved']==raw and conversion['legacy_runner_payload']['scores']==synthetic['scores'])
    check('v3_component_gate_input_interface',all(k in conversion['legacy_projection']['component_input_state'] for k in candidate.EGES))
    check('v3_draft_unchanged_during_checks',draft_before==candidate.bind(Path(grounded_v3.__file__)))
    oldsteps={r['case_id']:r['step_result'] for r in original_read(candidate.SOURCE/'step_results.json')}
    maxima={'c_param':3,'co_order':3,'co_method':2,'co_param':2,'co_chem':1,
        's_method':2.5,'s_label':6,'s_trans':3,'s_time':3}
    for c in cases:
        values=candidate.derive_primary(oldsteps[c['case_id']],maxima)
        check('original_SR_Com_'+c['case_id'],abs(values['Com']-(.4*oldsteps[c['case_id']]['sr']+.6))<1e-12
            and values['Cor']==1 and values['Eff']==1)
        empty=candidate.derive_primary(oldsteps[c['case_id']],{k:None for k in maxima})
        check('NA_dependency_'+c['case_id'],all(empty[k] is None for k in ['Com','Cor','Eff','IA','HV'])
            and empty['sr']==oldsteps[c['case_id']]['sr'] and empty['sp']==oldsteps[c['case_id']]['sp'])
    check('frozen_experiment_output_not_created',candidate.OUT.exists()==output_existed)
    out=candidate.BASE/'optimizer_20261010/grounded_controls_design_v1/scheduler_code_checks_v3_snapshot.json'
    value={'status':'pass','scope':'Code-only smoke checks; no frozen experiment or HTTP integration review',
        'checked_at_utc':candidate.j.now(),'checks':checks,'actual_model_requests':0,'new_embeddings':0,
        'prepare_preflight_run_analyze_executed':False,'scheduler_output_existed_before':output_existed,
        'scheduler_output_exists_after':candidate.OUT.exists(),'selection_manifest_exists':candidate.SELECTION.exists(),
        'v3_candidate_status':'current_draft_snapshot_not_final_selection','final_backend_frozen':False,
        'ledger_before':before,'ledger_after':candidate.parent.request_count(),
        'ledger_note':'Read-only snapshots; any concurrent other-agent requests are not attributed to these code checks.',
        'inputs':[candidate.bind(Path(candidate.__file__)),candidate.bind(Path(__file__)),draft_before,candidate.bind(measured_path),
            candidate.bind(Path(candidate.core.__file__)),*[candidate.bind(p) for p in v3_files.values()],
            *[candidate.bind(candidate.SOURCE/name) for name in ['cases.json','pairs.json','step_results.json','step_config.json','references.json']]],
        'actual_command':[sys.executable,*sys.argv],'cwd':str(ROOT),'scientific_accuracy_claimed':False}
    candidate.j.save(out,value)
    print(candidate.j.canonical({'status':'pass','checks':len(checks),'actual_model_requests':0,'out':str(out)}))

if __name__=='__main__':main()
