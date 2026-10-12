"""Zero-HTTP code checks for the unfrozen grounded E4 revision."""
from __future__ import annotations
import ast
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_stability_dev_v1 as e
import cce_analyze_grounded_stability_dev_v1 as a

OUT=e.OUT.parent/'grounded_stability_design_v1/revision_checks'

def main():
    results=[]
    def check(name,ok):
        if not ok:raise AssertionError(name)
        results.append({'check':name,'pass':True})
    for p in [Path(e.__file__),Path(a.__file__)]:compile(p.read_text(encoding='utf8'),str(p),'exec')
    check('both_scripts_compile',True)
    cases=e.j.read(e.dev.old.OUT/'cases.json')['cases'];steps=a.verify_step_sources(cases)
    check('five_original_SR_SP_bindings',len(steps)==5)
    for case in cases:
        aid=case['anonymous_answer_id'];p=e.grounded.OUT/'prompts'/f'{aid}.txt'
        doc=e.j.read(e.grounded.OUT/'source_documents'/f'{aid}.json')
        check('model_visible_LF_prompt_'+aid,p.read_text(encoding='utf8')==e.grounded.make_prompt(case,doc))
    source=Path(e.__file__).read_text(encoding='utf8')
    tree=ast.parse(source)
    prompt_byte_reads=[n.lineno for n in ast.walk(tree) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='read_bytes' and 'prompts' in (ast.get_source_segment(source,n) or '')]
    check('no_prompt_raw_byte_decode',not prompt_byte_reads)
    check('provider_raw_bytes_remain',"(attempt/'raw_source_bound_content.txt').read_bytes().decode('utf8')" in source)
    if not e.SELECTION.exists():
        try:e.selected_backend()
        except ValueError as exc:check('missing_root_selection_rejected','selection_missing' in str(exc))
        else:raise AssertionError('unselected_backend_accepted')
    check('root_integration_gate_enforced',all(t in source for t in ['independent_full_HTTP_integration_review_missing',
        'repeat_trial_sidecar_routing_pass','root_E2_terminal_sequence_gate_missing','selected_for_development_E4']))
    maxima={'c_param':3,'co_order':3,'co_method':2,'co_param':2,'co_chem':1,'s_method':2.5,'s_label':6,'s_trans':3,'s_time':3}
    step={'sr':6/7,'sp':.5};full=a.derived(maxima,step,True)
    check('unchanged_Com_Cor_Eff_formulas',a.same(full['Com'],.4*6/7+.6) and full['Cor']==full['Eff']==1)
    failed=a.derived(maxima,step,False)
    check('failure_keeps_independent_steps_only',len(failed)==16 and failed['sr']==step['sr'] and failed['sp']==step['sp']
        and all(failed[k] is None for k in a.METRICS if k not in ['sr','sp']))
    check('legacy_all_metrics_gated_available',all(v is None for v in a.legacy_all_metrics_gated(failed,False).values()))
    partial=a.derived({**maxima,'s_label':None},step,True)
    check('partial_label_only_gates_dependents',partial['Com']==full['Com'] and partial['Cor']==1 and all(partial[k] is None for k in ['s_label','Eff','IA','HV']))
    rows=[];models=['QWEN_SYNTHETIC','LLAMA_SYNTHETIC']
    for aid in e.IDS:
        for model in models:
            for repeat in range(3):
                values=dict(maxima);success=True
                if aid=='A01' and model==models[0] and repeat<2:success=False
                if aid=='A02' and model==models[1]:success=False
                if aid=='A03' and model==models[0] and repeat==0:values['s_label']=None
                if aid=='A04' and model==models[0]:values['c_param']=repeat+1
                rows.append({'anonymous_answer_id':aid,'judge':model,'repeat_index':repeat,'technical_pipeline_complete':success,**a.derived(values,step,success)})
    stats=a.summarize(rows,e.IDS,models);w=stats['within'];b=stats['between'];p=stats['same_repeat_pairs']
    check('full_160_80_240_grid',(len(w),len(b),len(p))==(160,80,240))
    check('singleton_ranges_are_NA',all(r['range'] is None and r['sample_sd'] is None and r['nonzero_range'] is None for r in w if r['finite_n']<2))
    check('complete_partial_absent_denominators',(sum(r['finite_n']==3 for r in w),sum(0<r['finite_n']<3 for r in w),sum(r['finite_n']==0 for r in w))==(128,18,14))
    check('within_ranges_finite_slots_with_separate_source',sum(r['range'] is not None for r in w)==132 and sum(r['nonzero_range'] is True for r in w)==4)
    check('fixed_steps_never_count_as_new_judge_returns',all(r['new_judge_numeric_observations']==0 and not r['counts_as_direct_judge_stability'] for r in w if r['metric'] in ['sr','sp']))
    check('between_complete_mean_denominator',sum(r['both_complete_three'] for r in b)==48)
    check('same_repeat_finite_denominator',sum(r['both_finite'] for r in p)==166)
    check('shared_CCE_answers_by_repeat',[r['common_n'] for r in stats['common_numeric_by_repeat']]==[2,3,4])
    check('shared_all_six_CCE_answers',stats['common_numeric_all_six']['common_answer_ids']==['A04','A05'])
    legacy_rows=[{k:r[k] for k in ['anonymous_answer_id','judge','repeat_index']}|a.legacy_all_metrics_gated({k:r[k] for k in a.METRICS},r['technical_pipeline_complete']) for r in rows]
    legacy=a.summarize(legacy_rows,e.IDS,models)
    check('legacy_failed_allNA_convention_retained',(sum(r['finite_n']==3 for r in legacy['within']),sum(0<r['finite_n']<3 for r in legacy['within']),sum(r['finite_n']==0 for r in legacy['within']))==(124,20,16))
    # Reuse the prior independent routing fixture, adapting its namespace for
    # the new explicit backend metadata key; execute the current wrapper AST.
    prior=OUT.parent.parent/'grounded_stability_design_review_v1/review.py'
    fixture_source=prior.read_text(encoding='utf8')
    old="'integrity':SimpleNamespace(parse_judge_object=json.loads),'OUT':root,'RUN':run,'require':require}"
    new="'integrity':SimpleNamespace(parse_judge_object=json.loads),'OUT':root,'RUN':run,'require':require,'EXTRA_KEY':'grounded_extraction_v2'}"
    check('fixture_adaptation_exactly_one_namespace',fixture_source.count(old)==1)
    namespace={'__file__':str(prior),'__name__':'independent_fixture_import_only'}
    exec(compile(fixture_source.replace(old,new),str(prior),'exec'),namespace)
    namespace['OUT']=OUT/'routing_fixture';route=namespace['synthetic_sidecar_fixture']()
    check('actual_trial_sidecar_routing_25_synthetic',route['status']=='pass' and route['unique_actual_trial_sidecars']==25)
    OUT.mkdir(parents=True,exist_ok=True)
    e.j.save(OUT/'synthetic_statistics.json',stats);e.j.save(OUT/'synthetic_routing.json',route)
    result={'status':'offline_software_checks_pass_not_generation_approval','created_utc':e.j.now(),
        'checks':results,'new_model_requests':0,'new_embeddings':0,'HTTP_requests':0,'real_ledger_reads_or_writes':0,
        'prepare_preflight_run_analyze_executed':False,'selection_manifest_exists':e.SELECTION.exists(),
        'experiment_output_exists':e.OUT.exists(),'scientific_accuracy_claimed':False,'pre_generation_approved':False,
        'scripts':[e.parent.bind(Path(e.__file__)),e.parent.bind(Path(a.__file__)),e.parent.bind(__file__)],
        'old_independent_fixture_source':e.parent.bind(prior),'step_bindings':[e.parent.bind(p) for p in a.frozen_source_paths()],
        'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd())}
    e.j.save(OUT/'software_checks.json',result)
    print(e.j.canonical({'status':result['status'],'checks':len(results),'new_model_requests':0,'output':str(OUT)}))

if __name__=='__main__':main()
