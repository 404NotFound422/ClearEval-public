"""Offline grounded E4 analysis: 30 fixed cells and 160/80/240 metric slots.

This module neither queries a service nor repairs a returned observation. The
selected backend, original scoring code, deterministic steps and these analysis
rules are bound by the batch before generation.
"""
from __future__ import annotations
import argparse
import contextlib
import csv
import io
import math
from pathlib import Path
import statistics
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_output_contract_v1 as parent
import cce_grounded_stability_dev_v1 as exp

OUT=exp.OUT/'analysis'
STEP_SOURCE=parent.DEV/'step_results.json'
STEP_BINDING=parent.DEV/'step_source_binding.json'
PRIOR_DEFINITION=ROOT/'scripts/cce_analyze_identity_stability_dev_v1.py'
CATEGORIES={'direct_judge':['c_param','co_order','co_method','co_param','co_chem'],
    'computed_EGES':['s_method','s_label','s_trans','s_time'],
    'deterministic_steps':['sr','sp'],'derived':['Com','Cor','Eff','IA','HV']}
METRICS=[m for group in CATEGORIES.values() for m in group]
DIRECT=CATEGORIES['direct_judge'];EGES=CATEGORIES['computed_EGES'];TOL=1e-12
require=parent.require

def finite(v):return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v)
def same(a,b):return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=TOL
def category(metric):return next(k for k,v in CATEGORIES.items() if metric in v)

def definition():
    return {'version':'grounded-stability-analysis-v1','fixed_answers':5,'models':2,'repeats':3,
        'metric_categories':CATEGORIES,'within_groups':160,'between_groups':80,'same_repeat_metric_pairs':240,
        'tolerance':TOL,'failed_pipeline_rule':'Retain independently verified SR/SP as deterministic_step_reuse; unavailable judge/EGES/derived values remain NA. Keep legacy_all_metrics_gated separately.',
        'component_gate':'Selected development backend gate_components; known-zero label handling preserved.',
        'within_rule':'Retain all slots; range and sample SD require at least two finite real repeats; complete-three separate.',
        'between_rule':'Same-repeat difference requires both finite; mean comparison requires both complete-three.',
        'Com':'.4*original_SR+.6*c_param/3','Cor':'mean(co_order/3,co_method/2,co_param/2,co_chem)',
        'Eff':'mean((s_method/2.5+1)/2,s_label/6,s_trans/3,s_time/3)','IA':'min(Com,Cor,Eff)','HV':'Com*Cor*Eff',
        'joint_dependency':'Any unknown input keeps dependent CCE value NA; no best-repeat selection or imputation.',
        'comparison_population':'Common finite CCE answers per same repeat; all-six-complete common set additionally reported.',
        'independent_sample_count':5,'metric_slots_are_independent_samples':False,'new_model_requests':0,
        'fixed_step_stability':'SR/SP are reused fixed-text/cache evidence, not new judge returns; any zero range is excluded from direct-judge stability.',
        'prior_definition_source':parent.bind(PRIOR_DEFINITION),'formal_eligible':False}

def frozen_source_paths():
    binding=j.read(STEP_BINDING);config=j.read(binding['config']['path'])
    return [Path(__file__),PRIOR_DEFINITION,STEP_SOURCE,STEP_BINDING,
        ROOT/'scripts/cce_validation.py',Path(config['inputs']['complete_reference_manifest']),
        *[Path(binding[k]['path']) for k in ['config','matches','per_answer']]]

def verify_step_sources(cases):
    """Validate existing five-answer SR/SP source chain; no encoder is loaded."""
    rows={r['case_id']:r for r in j.read(STEP_SOURCE)};binding=j.read(STEP_BINDING)
    for key in ['config','matches','per_answer']:
        item=binding[key];require(j.filehash(item['path'])==item['sha256'],'original_step_source_changed:'+key)
    config=j.read(binding['config']['path'])
    require(config['completeness']['primary_threshold']==.7 and config['run_setting']['actual_threshold']==.7,'original_step_threshold_changed')
    require(j.filehash(ROOT/'scripts/cce_validation.py')==config['resolved']['adapter_sha256'],'original_step_core_changed')
    require(j.filehash(config['inputs']['complete_reference_manifest'])==config['run_setting']['reference_file_sha256'],'original_step_reference_file_changed')
    matched=j.read(binding['matches']['path'])
    if isinstance(matched,dict):matched=matched.get('answers',matched.get('results',[]))
    scored=j.read(binding['per_answer']['path']);out={}
    for case in cases:
        cid=case['case_id'];step=rows[cid]
        require(step['input_sha256']==case['answer_sha256'] and step['reference_id'] in [r['reference_id'] for r in case['references']],'original_step_input_or_reference_changed')
        a=[r for r in matched if r.get('answer_id')==step['answer_id']];b=[r for r in scored if r.get('answer_id')==step['answer_id']]
        require(len(a)==len(b)==1 and j.digest(b[0])==step['source_score_row_sha256'],'original_step_score_row_binding')
        require(all(same(step[k],a[0][k]) and same(step[k],b[0][k]) for k in ['sr','sp']),'original_step_values_changed')
        out[cid]=step
    require(len(out)==5,'fixed_five_step_source_count');return out

def derived(components,step,technical_success):
    if not technical_success:return {k:step[k] if k in ['sr','sp'] else None for k in METRICS}
    values={k:components.get(k) for k in DIRECT+EGES}
    require(all(v is None or finite(v) for v in values.values()),'nonfinite_component')
    values.update(sr=step['sr'],sp=step['sp'])
    values['Com']=.4*values['sr']+.6*values['c_param']/3 if finite(values['sr']) and finite(values['c_param']) else None
    values['Cor']=sum(values[k]/m for k,m in zip(DIRECT[1:],[3,2,2,1]))/4 if all(finite(values[k]) for k in DIRECT[1:]) else None
    values['Eff']=((values['s_method']/2.5+1)/2+values['s_label']/6+values['s_trans']/3+values['s_time']/3)/4 if all(finite(values[k]) for k in EGES) else None
    joint=[values[k] for k in ['Com','Cor','Eff']]
    values['IA']=min(joint) if all(finite(v) for v in joint) else None
    values['HV']=math.prod(joint) if all(finite(v) for v in joint) else None
    return {k:values[k] for k in METRICS}

def legacy_all_metrics_gated(values,technical_success):
    return dict(values) if technical_success else {k:None for k in METRICS}

def summarize(observations,ids,models):
    """Pure statistics. Counts are slots, never independent sample sizes."""
    lookup={(r['anonymous_answer_id'],r['judge'],r['repeat_index']):r for r in observations}
    require(len(observations)==len(lookup)==30 and set(lookup)=={(a,m,r) for a in ids for m in models for r in range(3)},'complete_30_cell_grid_required')
    within=[];between=[];paired=[]
    for aid in ids:
        for model in models:
            for metric in METRICS:
                values=[lookup[aid,model,r][metric] for r in range(3)];valid=[v for v in values if finite(v)];n=len(valid)
                spread=max(valid)-min(valid) if n>=2 else None
                within.append({'anonymous_answer_id':aid,'judge':model,'metric':metric,'category':category(metric),
                    'counts_as_direct_judge_stability':metric in DIRECT,
                    'fixed_step_values_not_new_judge_observations':metric in ['sr','sp'],
                    'new_judge_numeric_observations':0 if metric in ['sr','sp'] else n,
                    'planned_n':3,'finite_n':n,'coverage':'complete_three' if n==3 else 'partial' if n else 'no_finite',
                    'values_by_repeat':values,'mean':statistics.mean(valid) if n else None,
                    'sample_sd':statistics.stdev(valid) if n>=2 else None,'min':min(valid) if n else None,'max':max(valid) if n else None,
                    'range':spread,'nonzero_range':spread>TOL if spread is not None else None,
                    'complete_three_nonzero_range':spread>TOL if n==3 else None})
        for metric in METRICS:
            a=[lookup[aid,models[0],r][metric] for r in range(3)];b=[lookup[aid,models[1],r][metric] for r in range(3)]
            deltas=[bv-av if finite(av) and finite(bv) else None for av,bv in zip(a,b)];valid=[d for d in deltas if finite(d)]
            complete=all(finite(v) for v in a+b);mean_delta=statistics.mean(b)-statistics.mean(a) if complete else None
            for repeat,(av,bv,d) in enumerate(zip(a,b,deltas)):
                paired.append({'anonymous_answer_id':aid,'metric':metric,'category':category(metric),'repeat_index':repeat,
                    'qwen_value':av,'llama_value':bv,'both_finite':finite(d),'llama_minus_qwen':d,'different':abs(d)>TOL if finite(d) else None})
            between.append({'anonymous_answer_id':aid,'metric':metric,'category':category(metric),'planned_paired_repeats':3,
                'counts_as_direct_judge_stability':metric in DIRECT,
                'fixed_step_values_not_new_judge_observations':metric in ['sr','sp'],
                'qwen_finite_n':sum(finite(v) for v in a),'llama_finite_n':sum(finite(v) for v in b),
                'finite_same_repeat_pairs':len(valid),'paired_deltas_llama_minus_qwen':deltas,
                'different_same_repeat_pairs':sum(abs(d)>TOL for d in valid),'any_same_repeat_difference':any(abs(d)>TOL for d in valid) if valid else None,
                'max_abs_paired_delta':max(abs(d) for d in valid) if valid else None,'both_complete_three':complete,
                'complete_qwen_mean':statistics.mean(a) if complete else None,'complete_llama_mean':statistics.mean(b) if complete else None,
                'complete_mean_delta_llama_minus_qwen':mean_delta,'complete_mean_difference':abs(mean_delta)>TOL if complete else None})
    require((len(within),len(between),len(paired))==(160,80,240),'metric_slot_count_changed')
    grouped=[]
    for cat in CATEGORIES:
        ww=[r for r in within if r['category']==cat];bb=[r for r in between if r['category']==cat];pp=[r for r in paired if r['category']==cat]
        grouped.append({'category':cat,'within_planned_groups':len(ww),'within_complete_three':sum(r['finite_n']==3 for r in ww),
            'within_partial':sum(0<r['finite_n']<3 for r in ww),'within_no_finite':sum(r['finite_n']==0 for r in ww),
            'within_range_evaluable':sum(r['range'] is not None for r in ww),'within_nonzero_range':sum(r['nonzero_range'] is True for r in ww),
            'within_complete_nonzero_range':sum(r['complete_three_nonzero_range'] is True for r in ww),
            'between_planned_groups':len(bb),'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in bb),
            'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in bb),
            'between_both_complete_three':sum(r['both_complete_three'] for r in bb),
            'between_complete_mean_different':sum(r['complete_mean_difference'] is True for r in bb),
            'planned_same_repeat_metric_pairs':len(pp),'finite_same_repeat_metric_pairs':sum(r['both_finite'] for r in pp),
            'different_same_repeat_metric_pairs':sum(r['different'] is True for r in pp)})
    common=[]
    for repeat in range(3):
        eligible=[aid for aid in ids if all(finite(lookup[aid,m,repeat][k]) for m in models for k in ['Com','Cor','Eff'])]
        common.append({'repeat_index':repeat,'common_answer_ids':eligible,'common_n':len(eligible),'planned_answers':5,
            'model_means':{m:{k:statistics.mean(lookup[a,m,repeat][k] for a in eligible) if eligible else None for k in ['Com','Cor','Eff','IA','HV']} for m in models}})
    all_six=[aid for aid in ids if all(finite(lookup[aid,m,r][k]) for m in models for r in range(3) for k in ['Com','Cor','Eff'])]
    common_all={'common_answer_ids':all_six,'common_n':len(all_six),'planned_answers':5,
        'model_means':{m:{k:statistics.mean(lookup[a,m,r][k] for a in all_six for r in range(3)) if all_six else None for k in ['Com','Cor','Eff','IA','HV']} for m in models},
        'repeat_observations_are_not_independent_answers':True}
    return {'within':within,'between':between,'same_repeat_pairs':paired,'category_summary':grouped,
        'common_numeric_by_repeat':common,'common_numeric_all_six':common_all}

def table(name,rows):
    j.save(OUT/(name+'.json'),rows)
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row));stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for row in rows:writer.writerow({k:j.canonical(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    (OUT/(name+'.csv')).write_text(stream.getvalue(),encoding='utf-8-sig')

def analyze():
    plan=exp.validate();before=parent.request_count();dev=exp.dev;grounded=exp.grounded
    require(j.read(exp.OUT/'analysis_definition.json')==definition(),'analysis_definition_changed')
    matrix=j.read(exp.OUT/'matrix.json');cases={c['case_id']:c for c in j.read(exp.OUT/'cases.json')['cases']}
    paths=list((exp.RUN/'trials').glob('*.json'));expected={r['planned_trial_id'] for r in matrix}
    if len(paths)!=30:
        print(j.canonical({'status':'pending_complete_matrix','required':30,'present':len(paths),'new_requests':0}));return 2
    require({p.stem for p in paths}==expected,'actual_trials_differ_from_matrix')
    commands=j.read(exp.OUT/'actual_commands.json')
    require(any(r.get('action')=='run' and r.get('status')=='runner_returned' for r in commands),'runner_terminal_record_missing')
    steps=verify_step_sources(list(cases.values()));contract=j.read(exp.OUT/'expected_contract.json')
    reuse={r['trial_id']:r for r in j.read(exp.OUT/'reuse_manifest.json')}
    ledger=[r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started'];receipts={r['request_id']:r for r in ledger}
    require(len(receipts)==len(ledger),'duplicate_global_receipt_id')
    run_bindings=[parent.bind(p) for p in exp.RUN.rglob('*') if p.is_file()]
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,_,registry=j.runtime(exp.args())
    observations=[];new_indices=[];old_indices=[];successful_replays=0
    for cell in matrix:
        tid=cell['planned_trial_id'];trial=j.read(exp.RUN/'trials'/f'{tid}.json');case=cases[trial['case_id']];aid=case['anonymous_answer_id']
        require(trial['status'] in ['success','failed'] and trial['identity']==cell['identity'] and trial['trial_id']==j.digest(cell['identity']),'nonterminal_or_changed_trial')
        model=next(m for m in contract['models'] if m['name']==cell['judge']);one={**contract,'models':[model]}
        inputsha=j.digest({'question':case['specific_question'],'question_id':case['question_id'],'protocol':case['model_response'],'references':case['references']})
        require(trial['identity']['contract_sha256']==j.digest(one) and trial['pipeline_config_sha256']==j.digest({**contract,'models':[]}),'per_model_contract_changed')
        require(trial['full_text_input_sha256']==trial['identity']['input_sha256']==inputsha and trial['references_sha256']==j.digest(case['references']),'source_input_changed')
        require(trial['judge']==cell['judge'] and trial['repeat_index']==cell['repeat_index'] and trial['attempt']==1,'actual_cell_or_attempt_changed')
        attempt=exp.RUN/'attempts'/f'{tid}_1';receiptpath=attempt/'request_receipt.json'
        receipt=j.read(receiptpath) if receiptpath.exists() else None;reused=tid in reuse
        require(bool(receipt)==bool(trial['actual_api_request_made']),'trial_request_flag_disagrees_with_receipt')
        if receipt:
            require(receipt==receipts.get(receipt['request_id']) and receipt['trial_id']==tid and receipt['model']==cell['judge'] and receipt['attempt']==1,'receipt_mismatch')
            require(sum(r['trial_id']==tid for r in ledger)==1,'repeat_request_forbidden')
            (old_indices if reused else new_indices).append(receipt['package_request_index'])
        else:require(not reused and trial['status']=='failed' and not any(r['trial_id']==tid for r in ledger),'unrequested_cell_not_a_retained_local_failure')
        require(j.read(attempt/'result.json')==trial,'attempt_and_trial_disagree')
        promptpath=attempt/'prompt.txt';frozen=(exp.OUT/'prompts'/f'{aid}.txt').read_text(encoding='utf8')
        prompt=promptpath.read_text(encoding='utf8') if promptpath.exists() else None
        if prompt is not None:require(prompt==frozen and j.filehash(promptpath)==trial['prompt_sha256'],'actual_prompt_changed')
        else:require(receipt is None and trial['status']=='failed','requested_observation_missing_actual_prompt')
        doc=j.read(exp.OUT/'source_documents'/f'{aid}.json')
        require(doc['text']==case['model_response'] and doc['source_id']==grounded.source_id_for_case(case) and grounded.make_prompt(case,doc)==frozen,'source_document_or_transform_changed')
        payloadpath=attempt/'http_request_payload.json';payload=j.read(payloadpath) if payloadpath.exists() else None
        if payload is not None:
            require(payload==j.read(exp.OUT/'expected_http_payloads'/f"{aid}_{cell['judge']}.json"),'actual_complete_HTTP_payload_changed')
            require(payload['prompt']==prompt and receipt is not None,'HTTP_prompt_sidecar_disagreement')
        else:require(trial['status']=='failed','successful_observation_missing_actual_HTTP_payload')
        providerpath=attempt/'provider_response.json';provider=j.read(providerpath) if providerpath.exists() else None
        rawpath=attempt/'raw_source_bound_content.txt';raw=rawpath.read_bytes().decode('utf8') if rawpath.exists() else None
        e=trial.get('evaluation') or {};extra=e.get(exp.EXTRA_KEY) or {};conversion=extra.get('conversion')
        if raw is not None:
            require(provider is not None and provider.get('response')==raw,'raw_provider_content_changed')
            require(j.read(attempt/'raw_source_bound_receipt.json')['raw_response_sha256']==grounded.rawsha(raw),'raw_receipt_hash_changed')
        proposal=j.proposals(e);require(proposal==trial['preserved_numeric_proposals'],'original_proposal_record_changed')
        technical=trial['status']=='success' and e.get('technical_status')=='VALID' and not e.get('_error')
        checked={k:None for k in DIRECT+EGES};notes={};effects=None
        if technical:
            require(receipt is not None and payload is not None and raw is not None and conversion is not None and provider.get('done') is True,'successful_trial_missing_complete_raw')
            reconverted=grounded.convert(raw,doc)
            require(reconverted==conversion==j.read(attempt/'source_bound_conversion.json'),'conversion_replay_mismatch')
            require(j.read(attempt/'projected_legacy_payload.json')==conversion['legacy_runner_payload'],'projection_sidecar_changed')
            require((attempt/'projected_legacy_content.txt').read_text(encoding='utf8')==conversion['legacy_runner_content'],'projection_content_changed')
            extraction=conversion['legacy_projection']['extraction']
            require(extraction==e['extraction'] and j.digest(extraction)==trial['extraction_sha256'],'runner_extraction_changed')
            require(e['legacy_diagnostics']['raw_teacher_scores']==conversion['legacy_runner_payload']['scores'],'direct_score_map_changed')
            demand=registry.get(case['question_id'],case['specific_question']);meta=runner.QUESTION_META_KB[registry.questions[str(case['question_id'])]['question_id']]
            quant={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
            for key in ['reagent_ri_value','protocol_time_hours','method_stages']:
                if key in extraction:quant[key]=extraction[key]
            require(quant==e['quantitative_data'] and demand==e['user_preference_vector'],'original_EGES_inputs_changed')
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):effects=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,extraction['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(same(effects[k],proposal[k]) for k in EGES),'original_EGES_replay_failed')
            checked,notes=dev.gate_components(proposal,conversion,effects);successful_replays+=1
        if (attempt/'source_bound_conversion_error.json').exists():
            error=j.read(attempt/'source_bound_conversion_error.json')
            require(not error['legacy_parser_fallback_permitted'] and not (attempt/'projected_legacy_payload.json').exists(),'conversion_failure_used_legacy_fallback')
        values=derived(checked,steps[case['case_id']],technical);evidence=dev.evidence_state(conversion)
        observations.append({'anonymous_answer_id':aid,'question_id':case['question_id'],'case_id':case['case_id'],
            'judge':cell['judge'],'repeat_index':cell['repeat_index'],'trial_id':tid,'request_index':receipt['package_request_index'] if receipt else None,
            'actual_request_reserved':receipt is not None,'actual_HTTP_payload_captured':payload is not None,
            'exact_prior_observation_reused':reused,'status':trial['status'],'technical_pipeline_complete':technical,
            'judge_attempt_failed':not technical,
            'evidence_state':evidence,'fact_acceptance':'pending_independent_E4_fact_review' if conversion else 'unavailable_no_valid_conversion',
            'complete_numeric_16':all(finite(values[k]) for k in METRICS),'complete_numeric_CCE':all(finite(values[k]) for k in ['Com','Cor','Eff']),
            'direct_and_EGES_numeric_count':sum(finite(values[k]) for k in DIRECT+EGES),'direct_and_EGES_denominator':9,
            'original_numeric_proposals':proposal,'component_gated_proposals':checked,'component_gate_notes':notes,
            'original_step_evidence':steps[case['case_id']],'original_EGES_replay':effects,
            'original_failure_stage':e.get('failure_stage'),'error_type':e.get('_error_type'),'error':e.get('_error'),
            'conversion_errors':extra.get('conversion_errors'),'source_conversion_replayed':technical,
            'raw_response_sha256':grounded.rawsha(raw) if raw is not None else None,
            'prompt_sha256':trial['prompt_sha256'],'judge_contract_sha256':trial['identity']['contract_sha256'],**values,
            'metric_value_sources':{k:('deterministic_step_reuse' if k in ['sr','sp'] else
                'judge_raw_direct_score' if k in DIRECT else 'original_EGES_after_grounded_component_gate' if k in EGES else 'original_derived_formula')
                if finite(values[k]) else None for k in METRICS},
            'legacy_all_metrics_gated':legacy_all_metrics_gated(values,technical),
            'numeric_NA_reasons':{k:'technical_pipeline_failure' if not technical else 'component_or_dependency_unresolved' for k,v in values.items() if v is None},
            'formal_eligible':False,'scientific_accuracy_claimed':False})
    require(len(new_indices)<=plan['new_requests_planned'] and len(old_indices)==plan['reused_observations']
        and len(set(new_indices+old_indices))==len(new_indices)+len(old_indices),'actual_request_denominators_changed')
    stats=summarize(observations,exp.IDS,exp.MODELS);within=stats['within'];between=stats['between'];paired=stats['same_repeat_pairs']
    legacy_rows=[{k:r[k] for k in ['anonymous_answer_id','judge','repeat_index','trial_id','status','technical_pipeline_complete']}|r['legacy_all_metrics_gated'] for r in observations]
    legacy_stats=summarize(legacy_rows,exp.IDS,exp.MODELS)
    step_evidence=[{'anonymous_answer_id':case['anonymous_answer_id'],'question_id':case['question_id'],'case_id':case['case_id'],
        **steps[case['case_id']],'independent_of_judge_status':True,'new_step_computations_this_E4':0,
        'repeated_display_is_not_a_new_judge_observation':True,'used_as_judge_stability_success':False} for case in cases.values()]
    summary={'status':'complete_development_diagnostic_not_scientific_validation','actual_observations':30,
        'unique_base_answers':5,'models':exp.MODELS,'selected_backend':exp.BACKEND_VERSION,
        'new_requests_this_batch':len(new_indices),'exact_reused_observations':len(old_indices),
        'planned_new_requests':plan['new_requests_planned'],
        'local_failed_observations_without_request':sum(not r['actual_request_reserved'] for r in observations),
        'new_request_indices':sorted(new_indices),'reused_request_indices':sorted(old_indices),
        'technical_successes':sum(r['technical_pipeline_complete'] for r in observations),
        'technical_failures':sum(not r['technical_pipeline_complete'] for r in observations),
        'evidence_unresolved':sum(r['evidence_state']['unresolved'] for r in observations),
        'complete_numeric_16':sum(r['complete_numeric_16'] for r in observations),
        'complete_numeric_CCE':sum(r['complete_numeric_CCE'] for r in observations),
        'per_component_numeric':{k:sum(finite(r[k]) for r in observations) for k in METRICS},'per_component_denominator':30,
        'within_groups':160,'within_complete_three':sum(r['finite_n']==3 for r in within),
        'within_partial':sum(0<r['finite_n']<3 for r in within),'within_no_finite':sum(r['finite_n']==0 for r in within),
        'within_range_evaluable':sum(r['range'] is not None for r in within),'within_nonzero_range':sum(r['nonzero_range'] is True for r in within),
        'between_groups':80,'between_both_complete_three':sum(r['both_complete_three'] for r in between),
        'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in between),
        'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in between),
        'same_repeat_pairs':240,'finite_same_repeat_pairs':sum(r['both_finite'] for r in paired),
        'different_same_repeat_pairs':sum(r['different'] is True for r in paired),
        'metric_categories':CATEGORIES,'metric_groups_are_not_independent_answers':True,
        'direct_judge_stability_only':next(r for r in stats['category_summary'] if r['category']=='direct_judge'),
        'fixed_step_evidence_answers':5,'fixed_step_evidence_new_computations':0,
        'deterministic_step_zero_range_counts_as_judge_stability_success':False,
        'legacy_all_metrics_gated_comparison':{'description':'Previous convention suppresses all 16 values on a failed trial; retained for comparison, not the new primary component coverage.',
            'within_complete_three':sum(r['finite_n']==3 for r in legacy_stats['within']),
            'within_partial':sum(0<r['finite_n']<3 for r in legacy_stats['within']),
            'within_no_finite':sum(r['finite_n']==0 for r in legacy_stats['within']),
            'per_component_numeric':{k:sum(finite(r[k]) for r in legacy_rows) for k in METRICS}},
        'common_numeric_by_repeat':stats['common_numeric_by_repeat'],'common_numeric_all_six':stats['common_numeric_all_six'],
        'source_fact_acceptance':'pending_independent_E4_fact_review','expert_returns':0,'formal_eligible':False,
        'new_analysis_requests':0,'new_embeddings':0,'frozen_actual_files':run_bindings}
    OUT.mkdir(parents=True,exist_ok=True)
    table('observations',observations)
    table('fixed_step_evidence',step_evidence)
    table('legacy_all_metrics_gated',legacy_rows)
    for name in ['within','between','same_repeat_pairs','category_summary','common_numeric_by_repeat']:table(name,stats[name])
    j.save(OUT/'common_numeric_all_six.json',stats['common_numeric_all_six']);j.save(OUT/'completion_summary.json',summary)
    require(all(j.filehash(r['path'])==r['sha256'] for r in run_bindings),'analysis_changed_actual_run_files')
    exp.validate();require(parent.request_count()==before,'analysis_reserved_request')
    j.save(OUT/'analysis_verification.json',{'status':'pass','all_30_terminal_cells_retained':True,
        'within_groups':160,'between_groups':80,'same_repeat_pairs':240,'original_EGES_replays':successful_replays,
        'step_values_reused_no_encoder':True,'raw_and_projection_replayed_separately':True,
        'actual_commands':[sys.executable,*sys.argv],'script':parent.bind(__file__),
        'frozen_inputs':plan['frozen_inputs'],'new_model_requests':0,'new_embeddings':0,'scientific_accuracy_claimed':False})
    exp.record('analyze',new_requests=0)
    print(j.canonical({k:v for k,v in summary.items() if k not in ['frozen_actual_files','common_numeric_by_repeat','common_numeric_all_six']}));return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['analyze']);p.parse_args()
    raise SystemExit(analyze())
