"""Offline terminal E4 audit. All 30 cells are required; no generation or repair."""
from __future__ import annotations
import argparse
import collections
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import socket
import statistics
import sys
import textwrap

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_identity_stability_dev_v1 as exp
import cce_output_contract_v1 as parent
import cce_judges as j
import evaluator_integrity as integrity

BATCH=exp.OUT
OUT=BATCH/'analysis'
STEP_SOURCE=parent.DEV/'step_results.json'
STEP_BINDING=parent.DEV/'step_source_binding.json'
REVIEW=ROOT/'artifacts/cce_validation/human_review/versioned_review_v1/manifest.json'
EXAMPLE=ROOT/'artifacts/cce_validation/judges/stability_remediation_plan_v1/original_final_example.json'
CATEGORIES={'direct_judge':['c_param','co_order','co_method','co_param','co_chem'],
    'computed_EGES':['s_method','s_label','s_trans','s_time'],
    'deterministic_steps':['sr','sp'],'derived':['Com','Cor','Eff','IA','HV']}
METRICS=[m for group in CATEGORIES.values() for m in group]
DIRECT=CATEGORIES['direct_judge'];EGES=CATEGORIES['computed_EGES']
TOL=1e-12
INPUTS={}

def deny(*args,**kwargs):raise RuntimeError('Offline E4 analysis forbids network calls')
socket.create_connection=deny
socket.socket.connect=deny
socket.socket.connect_ex=deny

def require(ok,why):
    if not ok:raise ValueError(why)

def bind(path,expected=None):
    path=Path(path).resolve();h=j.filehash(path)
    if expected is not None:require(h==expected,'input_byte_mismatch:'+str(path))
    INPUTS[str(path)]=h;return path

def read(path):return j.read(bind(path))
def text(path):return bind(path).read_text(encoding='utf8')
def finite(v):return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v)
def same(a,b):return (a is None and b is None) or (finite(a) and finite(b) and abs(a-b)<=TOL)
def category(metric):return next(k for k,values in CATEGORIES.items() if metric in values)

def table(name,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=fields);w.writeheader()
    for row in rows:w.writerow({k:j.canonical(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    (OUT/(name+'.csv')).write_text(s.getvalue(),encoding='utf-8-sig')
    j.save(OUT/(name+'.json'),rows)

def original_gate(parsed,source):
    begin=source.index('        scores_block = llm_output.get("scores", {})')
    end=source.index('        validate_score_proposals(scores_block)',begin)+len('        validate_score_proposals(scores_block)')
    ns={'__builtins__':{'any':any},'llm_output':parsed,'validate_teacher_extraction':integrity.validate_legacy_extraction,
        'validate_score_proposals':integrity.validate_score_proposals}
    exec(compile(textwrap.dedent(source[begin:end]),'<original-field-gate-E4>','exec'),ns)
    return ns['extraction'],ns['scores_block']

def derived(proposals,step,success):
    # Independent step evidence is retained separately, not made into a successful
    # full pipeline by filling failed observations with known deterministic scores.
    if not success:return {k:None for k in METRICS}
    values={k:proposals[k] for k in DIRECT+EGES+['Cor','Eff']}
    values.update(sr=step['sr'],sp=step['sp'])
    values['Com']=.4*values['sr']+.6*values['c_param']/3 if finite(values['sr']) and finite(values['c_param']) else None
    joint=[values[k] for k in ['Com','Cor','Eff']]
    values['IA']=min(joint) if all(finite(v) for v in joint) else None
    values['HV']=math.prod(joint) if all(finite(v) for v in joint) else None
    return {k:values[k] for k in METRICS}

def bind_review_package():
    manifest=read(REVIEW);paths=set()
    def visit(node):
        if isinstance(node,dict):
            if 'path' in node and 'sha256' in node:bind(node['path'],node['sha256']);paths.add(node['path'])
            for value in node.values():visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(manifest)
    require(manifest['development_answers']==5 and manifest['holdout_answers']==15 and manifest['review_items']==160,'human_selection_changed')
    # Referenced held-out auto/trial files were byte hashed only, never decoded.
    return {'manifest_sha256':j.filehash(REVIEW),'bound_files':len(paths),'fixed_answers':20,'development':5,
        'holdout':15,'original_form_rows':160,'heldout_scientific_records_decoded':0,
        'expert_packet_versions_unchanged':True,'development_group':manifest['groups']['development_v4']['version']}

def prepare():
    exp.validate();OUT.mkdir(parents=True,exist_ok=True)
    files=[BATCH/'plan.json',BATCH/'matrix.json',BATCH/'reuse_manifest.json',BATCH/'cases.json',
        BATCH/'preflight_verification.json',BATCH/'expected_scientific_contract.json',STEP_SOURCE,STEP_BINDING,REVIEW,EXAMPLE,
        Path(__file__),ROOT/'scripts/cce_analyze_output_identity_v2.py',ROOT/'OEQ_run_grading_new.py',ROOT/'evaluator_integrity.py']
    frozen=[{'path':str(p.resolve()),'sha256':j.filehash(p)} for p in files]
    plan={'schema':'identity-stability-terminal-analysis-v1','created_utc':j.now(),
        'scope':'Rules implement the prior frozen E4 matrix/metric/NA plan; this analysis manifest does not claim a pre-generation timestamp.',
        'required_terminal_trials':30,'reused_observations':5,'new_requests_expected':25,'fixed_ids':exp.IDS,'judges':exp.MODELS,
        'metric_categories':CATEGORIES,'within_groups':160,'between_groups':80,'same_repeat_metric_pairs':240,'tolerance':TOL,
        'failed_pipeline_rule':'All 16 analysis metrics NA; original deterministic SR/SP evidence retained separately, no successful output substituted.',
        'within_rule':'All judge/answer/metric groups, including no finite observations. Range requires at least two; complete three distinguished from partial.',
        'between_rule':'Same-repeat differences require both finite. Three-repeat mean comparison only if both judges have all three finite observations.',
        'no_best_repeat_selection':True,'same_prompt_versions_only':True,'expert_packets_unchanged':True,'frozen_inputs':frozen}
    target=OUT/'analysis_plan.json'
    if target.exists():
        old=j.read(target)
        require(old['frozen_inputs']==frozen and old['metric_categories']==CATEGORIES,'analysis_plan_already_frozen_different')
    else:j.save(target,plan)
    j.save(OUT/'prepare_execution.json',{'utc':j.now(),'argv':[sys.executable,'scripts/cce_analyze_identity_stability_dev_v1.py','prepare'],
        'cwd':str(ROOT),'new_requests':0,'status':'prepared','plan_sha256':j.filehash(target),'script_sha256':j.filehash(__file__)})
    print(j.canonical({'status':'analysis_prepared','new_requests':0,'requires_terminal_trials':30,'within_groups':160,'between_groups':80}))

def analyze():
    exp.validate()
    plan=read(OUT/'analysis_plan.json')
    for item in plan['frozen_inputs']:bind(item['path'],item['sha256'])
    matrix=read(BATCH/'matrix.json');cases={c['case_id']:c for c in read(BATCH/'cases.json')['cases']}
    expected={x['planned_trial_id']:x for x in matrix}
    trial_paths=list((exp.RUN/'trials').glob('*.json'))
    if len(trial_paths)!=30:
        print(j.canonical({'status':'pending_complete_matrix','present_trial_files':len(trial_paths),'required':30,'completion_written':False,'new_requests':0}));return 2
    trials={p.stem:(p,read(p)) for p in trial_paths}
    require(set(trials)==set(expected),'actual_trials_not_exact_frozen_matrix')
    require(all(t['status'] in ['success','failed'] for p,t in trials.values()),'nonterminal_trial_status')
    calls=read(BATCH/'actual_execution_commands.json')
    require(any(r.get('argv',[])[-2:]==['run','--allow-local-calls'] and r.get('status')=='runner_returned' for r in calls),'runner_terminal_record_required')
    run_files={str(p):j.filehash(p) for p in exp.RUN.rglob('*') if p.is_file()}
    ledger_sha=j.filehash(bind(parent.LEDGER));ledger=[x for x in j.ledger_rows(parent.LEDGER) if x.get('event')=='request_started']
    receipts={x['request_id']:x for x in ledger}
    require(len(receipts)==len(ledger),'global_request_id_duplicate')
    contract=read(BATCH/'expected_scientific_contract.json');reuse={r['trial_id']:r for r in read(BATCH/'reuse_manifest.json')}
    for relative,h in contract['files'].items():bind(ROOT/relative,h)
    human_package=bind_review_package()
    steps={r['case_id']:r for r in read(STEP_SOURCE)}
    source_binding=read(STEP_BINDING)
    for k in ['config','matches','per_answer']:bind(source_binding[k]['path'],source_binding[k]['sha256'])
    source_step_rows=read(source_binding['matches']['path'])
    if isinstance(source_step_rows,dict):source_step_rows=source_step_rows.get('answers',source_step_rows.get('results',[]))
    source_score_rows=read(source_binding['per_answer']['path'])
    for cid,case in cases.items():
        s=steps[cid]
        require(s['input_sha256']==case['answer_sha256'] and s['reference_id'] in [r['reference_id'] for r in case['references']],'deterministic_step_binding')
        originals=[r for r in source_step_rows if r.get('answer_id')==s['answer_id']]
        original_scores=[r for r in source_score_rows if r.get('answer_id')==s['answer_id']]
        require(len(originals)==1 and len(original_scores)==1 and j.digest(original_scores[0])==s['source_score_row_sha256'],'original_step_row_binding')
        require(all(same(s[k],originals[0][k]) for k in ['sr','sp']),'original_step_values_changed')
        require(all(same(s[k],original_scores[0][k]) for k in ['sr','sp']),'original_score_values_changed')
    original_example=read(EXAMPLE)
    old_reasons={r['reasoning'] for g in original_example.get('scores',{}).values() if isinstance(g,dict)
        for r in g.values() if isinstance(r,dict) and isinstance(r.get('reasoning'),str)}
    source=text(ROOT/'OEQ_run_grading_new.py')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,_,registry=j.runtime(exp.args())
    observations=[];reason_records=[];indices=[];new_indices=[];recomputed_n=0;failure_counts=collections.Counter()
    for cell in matrix:
        tid=cell['planned_trial_id'];path,t=trials[tid];cid=t['case_id'];case=cases[cid];aid=case['anonymous_answer_id'];qid=case['question_id']
        model=next(m for m in contract['models'] if m['name']==cell['identity']['judge'])
        single={**contract,'models':[model]};ih=j.digest({'question':case['specific_question'],'question_id':qid,'protocol':case['model_response'],'references':case['references']})
        require(t['identity']==cell['identity'] and t['trial_id']==j.digest(cell['identity']),'trial_planned_identity')
        require(t['identity']['contract_sha256']==j.digest(single) and t['pipeline_config_sha256']==j.digest({**contract,'models':[]}),'per_judge_contract_identity')
        require(t['full_text_input_sha256']==t['identity']['input_sha256']==ih and t['references_sha256']==j.digest(case['references']),'full_input_identity')
        require(parent.rawsha(case['model_response'])==case['answer_sha256'] and parent.rawsha(case['specific_question'])==case['question_sha256'],'raw_input_identity')
        require(t['judge']==model['name'] and t['repeat_index']==cell['identity']['repeat_index'] and t['attempt']==1 and t['actual_api_request_made'],'actual_single_attempt')
        attempt=exp.RUN/'attempts'/f'{tid}_1';receipt=read(attempt/'request_receipt.json')
        require(receipt==receipts.get(receipt['request_id']) and receipt['trial_id']==tid and receipt['model']==t['judge'] and receipt['attempt']==1,'ledger_receipt_identity')
        require(sum(r['trial_id']==tid for r in ledger)==1,'trial_retried')
        indices.append(receipt['package_request_index'])
        reused=tid in reuse
        if reused:
            require(j.filehash(path)==reuse[tid]['original_trial_sha256']==j.filehash(bind(reuse[tid]['reused_from'])),'exact_reused_trial_bytes')
            for item in reuse[tid]['original_files']:
                sourcep=bind(item['path'],item['sha256']);target=exp.RUN/sourcep.relative_to(exp.identity.RUN);bind(target,item['sha256'])
        else:new_indices.append(receipt['package_request_index'])
        require(read(attempt/'result.json')==t,'attempt_result_trial_identity')
        prompt=text(attempt/'prompt.txt');frozen=text(BATCH/'prompts'/f'{aid}_prompt.txt')
        require(prompt==frozen and j.filehash(attempt/'prompt.txt')==t['prompt_sha256'],'actual_prompt_identity')
        require(all(prompt.count(case[k])==1 for k in ['specific_question','model_response']) and prompt.endswith(parent.v2.reference_suffix(case)),'complete_prompt_payload')
        context=read(attempt/'context_check.json')
        require(context['conservative_context_bound']==len(prompt.encode('utf8'))+8192+256<=40960,'no_prompt_truncation_bound')
        provider_path=attempt/'provider_response.json';provider=read(provider_path) if provider_path.exists() else None
        error_path=attempt/'provider_error.json';provider_error=read(error_path) if error_path.exists() else None
        exc=integrity.JudgeFormatError('saved provider envelope error') if provider is None and provider_error and provider_error.get('error_type')=='JudgeFormatError' else (RuntimeError('saved provider exception') if provider_error else None)
        diagnostic=parent.classify(provider,exc);evaluation=t.get('evaluation') or {};generation=evaluation.get('teacher_generation') or {}
        raw=provider.get('response') if isinstance(provider,dict) else None
        if isinstance(raw,str):
            require(raw==generation.get('content')==generation.get('raw_content'),'unmodified_primary_raw_return')
            require((generation.get('metadata') or {}).get('provider_response')==provider,'provider_metadata_sidecar_identity')
        values=j.proposals(evaluation);require(values==t['preserved_numeric_proposals'],'original_numeric_proposals')
        full=t['status']=='success' and evaluation.get('technical_status')=='VALID' and not evaluation.get('_error')
        extraction=None;raw_scores=None;strict_pass=False
        if diagnostic['technical_pass']:
            parsed=integrity.parse_judge_object(raw);extraction,raw_scores=original_gate(parsed,source);strict_pass=True
        if full:
            require(strict_pass and extraction==evaluation['extraction'] and j.digest(extraction)==t['extraction_sha256'],'successful_strict_extraction_identity')
            require(raw_scores==evaluation['legacy_diagnostics']['raw_teacher_scores'],'direct_score_map_identity')
            demand=registry.get(qid,case['specific_question']);meta=runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]
            quant={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
            for k in ['reagent_ri_value','protocol_time_hours','method_stages']:
                if k in extraction:quant[k]=extraction[k]
            require(quant==evaluation['quantitative_data'] and demand==evaluation['user_preference_vector'],'original_EGES_inputs')
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):effects=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,extraction['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(same(effects[k],values[k]) for k in EGES),'original_EGES_replay')
            for k in DIRECT:
                group='completeness' if k=='c_param' else 'correctness'
                require(raw_scores[group][k]['score']==values[k],'raw_direct_score_identity')
            cor=sum(values[k]/m for k,m in zip(DIRECT[1:],[3,2,2,1]))/4 if all(finite(values[k]) for k in DIRECT[1:]) else None
            eff=((values['s_method']/2.5+1)/2+values['s_label']/6+values['s_trans']/3+values['s_time']/3)/4 if all(finite(values[k]) for k in EGES) else None
            require(same(cor,values['Cor']) and same(eff,values['Eff']),'original_aggregation_replay');recomputed_n+=1
        else:failure_counts[diagnostic.get('failure_code') or evaluation.get('failure_stage') or 'UNCLASSIFIED']+=1
        copied_reasons=0;own_prompt_reasons=0
        if strict_pass:
            for metric in DIRECT:
                group='completeness' if metric=='c_param' else 'correctness';reason=raw_scores[group][metric].get('reasoning')
                copied=isinstance(reason,str) and reason in old_reasons
                in_prompt=isinstance(reason,str) and len(reason.strip())>=12 and reason in prompt
                copied_reasons+=copied;own_prompt_reasons+=in_prompt
                reason_records.append({'anonymous_answer_id':aid,'judge':t['judge'],'repeat':t['repeat_index'],'metric':metric,
                    'reason_sha256':parent.rawsha(reason) if isinstance(reason,str) else None,'exact_old_example_match':copied,
                    'exact_own_prompt_substring':in_prompt,'semantic_fidelity_verified':False})
        step=steps[cid];metrics=derived(values,step,full)
        row={'anonymous_answer_id':aid,'question_id':qid,'case_id':cid,'judge':t['judge'],'repeat_index':t['repeat_index'],
            'trial_id':tid,'request_index':receipt['package_request_index'],'exact_prior_observation_reused':reused,
            'status':t['status'],'full_pipeline_success':full,'strict_structure_pass':strict_pass,
            'failure_layer':diagnostic.get('failure_layer'),'failure_code':diagnostic.get('failure_code'),
            'original_failure_stage':evaluation.get('failure_stage'),'provider_done':provider.get('done') if provider else None,
            'provider_finish_reason':provider.get('done_reason') if provider else None,'output_tokens':provider.get('eval_count') if provider else None,
            'input_sha256':ih,'prompt_sha256':t['prompt_sha256'],'contract_sha256':t['identity']['contract_sha256'],
            'extraction_sha256':t['extraction_sha256'],'original_EGES_recomputed':full,
            'original_step_evidence':{k:step[k] for k in ['sr','sp','reference_id','step_config_sha256','input_sha256']},
            'original_numeric_proposals':values,**metrics,
            'numeric_NA_reasons':{k:'technical_pipeline_failure' if not full else 'original_upstream_component_unknown' for k,v in metrics.items() if v is None},
            'exact_full_old_extraction_example_copy':extraction==original_example.get('extraction') if strict_pass else None,
            'direct_reasons_exact_old_example_matches':copied_reasons if strict_pass else None,
            'direct_reasons_exact_own_prompt_substrings':own_prompt_reasons if strict_pass else None,
            'formal_eligible':False,'expert_confirmation':None,'semantic_fidelity_verified':False}
        observations.append(row)
    require(len(set(indices))==30 and len(new_indices)==25,'actual_request_denominators')
    require(sum(r['exact_prior_observation_reused'] for r in observations)==5,'five_exact_reuses')
    within=[];between=[];paired=[]
    lookup={(r['anonymous_answer_id'],r['judge'],r['repeat_index']):r for r in observations}
    for aid in exp.IDS:
        for model in exp.MODELS:
            for metric in METRICS:
                values=[lookup[aid,model,repeat][metric] for repeat in range(3)];valid=[v for v in values if finite(v)];n=len(valid)
                spread=max(valid)-min(valid) if n>=2 else None
                within.append({'anonymous_answer_id':aid,'judge':model,'metric':metric,'category':category(metric),'planned_n':3,
                    'finite_n':n,'coverage':'complete_three' if n==3 else 'partial' if n else 'no_finite',
                    'values_by_repeat':values,'mean':statistics.mean(valid) if n else None,'sample_sd':statistics.stdev(valid) if n>=2 else None,
                    'min':min(valid) if n else None,'max':max(valid) if n else None,'range':spread,
                    'nonzero_range':spread>TOL if spread is not None else None,'complete_three_nonzero_range':spread>TOL if n==3 else None})
        for metric in METRICS:
            a=[lookup[aid,exp.MODELS[0],r][metric] for r in range(3)];b=[lookup[aid,exp.MODELS[1],r][metric] for r in range(3)]
            deltas=[bv-av if finite(av) and finite(bv) else None for av,bv in zip(a,b)];finite_deltas=[v for v in deltas if finite(v)]
            complete=all(finite(v) for v in a+b);mean_delta=statistics.mean(b)-statistics.mean(a) if complete else None
            for repeat,(av,bv,d) in enumerate(zip(a,b,deltas)):
                paired.append({'anonymous_answer_id':aid,'metric':metric,'category':category(metric),'repeat_index':repeat,
                    'qwen_value':av,'llama_value':bv,'both_finite':finite(d),'llama_minus_qwen':d,'different':abs(d)>TOL if finite(d) else None})
            between.append({'anonymous_answer_id':aid,'metric':metric,'category':category(metric),'planned_paired_repeats':3,
                'qwen_finite_n':sum(finite(v) for v in a),'llama_finite_n':sum(finite(v) for v in b),
                'finite_same_repeat_pairs':len(finite_deltas),'paired_deltas_llama_minus_qwen':deltas,
                'different_same_repeat_pairs':sum(abs(v)>TOL for v in finite_deltas),
                'any_same_repeat_difference':any(abs(v)>TOL for v in finite_deltas) if finite_deltas else None,
                'max_abs_paired_delta':max(abs(v) for v in finite_deltas) if finite_deltas else None,
                'both_complete_three':complete,'complete_qwen_mean':statistics.mean(a) if complete else None,
                'complete_llama_mean':statistics.mean(b) if complete else None,'complete_mean_delta_llama_minus_qwen':mean_delta,
                'complete_mean_difference':abs(mean_delta)>TOL if complete else None})
    require(len(within)==160 and len(between)==80 and len(paired)==240,'all_metric_groups_retained')
    per_model=[]
    for model in exp.MODELS:
        rr=[r for r in observations if r['judge']==model]
        per_model.append({'judge':model,'planned_observations':15,'actual_observations':len(rr),'technical_successes':sum(r['full_pipeline_success'] for r in rr),
            'technical_failures':sum(not r['full_pipeline_success'] for r in rr),'complete_numeric_CCE':sum(all(finite(r[k]) for k in ['Com','Cor','Eff']) for r in rr),
            'complete_numeric_16':sum(all(finite(r[k]) for k in METRICS) for r in rr),
            'full_example_copies':sum(r['exact_full_old_extraction_example_copy'] is True for r in rr),
            'example_copy_evaluable':sum(r['strict_structure_pass'] for r in rr)})
    grouped=[]
    for cat in CATEGORIES:
        ww=[r for r in within if r['category']==cat];bb=[r for r in between if r['category']==cat];pp=[r for r in paired if r['category']==cat]
        grouped.append({'category':cat,'within_planned_groups':len(ww),'within_complete_three':sum(r['finite_n']==3 for r in ww),
            'within_partial':sum(0<r['finite_n']<3 for r in ww),'within_no_finite':sum(r['finite_n']==0 for r in ww),
            'within_range_evaluable':sum(r['range'] is not None for r in ww),'within_nonzero_range':sum(r['nonzero_range'] is True for r in ww),
            'within_complete_nonzero_range':sum(r['complete_three_nonzero_range'] is True for r in ww),
            'maximum_evaluable_range':max((r['range'] for r in ww if r['range'] is not None),default=None),
            'between_planned_groups':len(bb),'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in bb),
            'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in bb),
            'between_both_complete_three':sum(r['both_complete_three'] for r in bb),
            'between_complete_mean_different':sum(r['complete_mean_difference'] is True for r in bb),
            'planned_same_repeat_metric_pairs':len(pp),'finite_same_repeat_metric_pairs':sum(r['both_finite'] for r in pp),
            'different_same_repeat_metric_pairs':sum(r['different'] is True for r in pp)})
    summary={'status':'complete','actual_observations':30,'exact_reused_observations':5,'new_requests_this_batch':25,
        'new_request_indices':sorted(new_indices),'reused_request_indices':sorted(set(indices)-set(new_indices)),
        'package_requests_at_analysis':len(ledger),'technical_successful_observations':sum(r['full_pipeline_success'] for r in observations),
        'technical_failed_observations':sum(not r['full_pipeline_success'] for r in observations),
        'failed_cells':[{'anonymous_answer_id':r['anonymous_answer_id'],'judge':r['judge'],'repeat_index':r['repeat_index'],
            'request_index':r['request_index'],'failure_code':r['failure_code'],'reused':r['exact_prior_observation_reused']} for r in observations if not r['full_pipeline_success']],
        'failure_reason_categories':dict(failure_counts),'judges':per_model,'categories':grouped,'metric_categories':CATEGORIES,
        'within_groups':160,'within_complete_three':sum(r['finite_n']==3 for r in within),
        'within_partial':sum(0<r['finite_n']<3 for r in within),'within_no_finite':sum(r['finite_n']==0 for r in within),
        'within_range_evaluable':sum(r['range'] is not None for r in within),'within_nonzero_range':sum(r['nonzero_range'] is True for r in within),
        'within_complete_nonzero_range':sum(r['complete_three_nonzero_range'] is True for r in within),
        'between_groups':80,'between_any_pair_evaluable':sum(r['finite_same_repeat_pairs']>0 for r in between),
        'between_any_pair_different':sum(r['any_same_repeat_difference'] is True for r in between),
        'between_both_complete_three':sum(r['both_complete_three'] for r in between),
        'between_complete_mean_different':sum(r['complete_mean_difference'] is True for r in between),
        'same_repeat_metric_pairs':240,'finite_same_repeat_metric_pairs':sum(r['both_finite'] for r in paired),
        'different_same_repeat_metric_pairs':sum(r['different'] is True for r in paired),'tolerance':TOL,
        'no_best_repeat_selection':True,'no_mixed_prompt_versions':True,'human_review_package':human_package,
        'formal_eligible_observations':0,'expert_returns_added':0,'analysis_new_requests':0,
        'semantic_fidelity_verified':False,'full_example_copy_is_not_accuracy':True,
        'scope':'Five exposed development answers; same identity_v2 prompt, two judges, three observations each. Failures retained; no holdout science access.'}
    require(j.filehash(parent.LEDGER)==ledger_sha,'analysis_modified_ledger')
    require(all(j.filehash(p)==h for p,h in run_files.items()),'frozen_run_files_changed')
    require(all(j.filehash(p)==h for p,h in INPUTS.items()),'input_changed_during_analysis')
    for name,rows in [('observations',observations),('within',within),('between',between),('same_repeat_pairs',paired),('reason_copy_diagnostics',reason_records),('category_summary',grouped)]:table(name,rows)
    j.save(OUT/'completion_summary.json',summary)
    verification={'status':'pass','terminal_actual_trials_bound':30,'actual_new_requests_bound':25,'exact_reuses_bound':5,
        'original_EGES_success_replays':recomputed_n,'direct_score_records_checked':recomputed_n*5,
        'strict_raw_return_checks':30,'planned_matrix_exact':True,'all_160_within_and_80_between_groups_retained':True,
        'same_repeat_pairs_retained':240,'human_review_package':human_package,'input_sha256':INPUTS,
        'all_bound_inputs_unchanged':True,'run_files_byte_unchanged':len(run_files),'ledger_snapshot_sha256':ledger_sha,
        'step_scores_reused_no_encoder':True,'heldout_scientific_records_decoded':0,'new_requests':0,
        'original_parser_EGES_contract_unchanged':True,'audit_type':'software/data identity, not scientific correctness'}
    j.save(OUT/'analysis_verification.json',verification)
    lines=['# 固定开发集 E4：完整名称提示下的实际重复诊断','',
        f"30 格均已终态：5 个原 Qwen repeat 0 精确复用，25 次新请求；技术成功 {summary['technical_successful_observations']}/30、失败 {summary['technical_failed_observations']}/30。全包账本在分析时为 {len(ledger)} 次。失败原样保留，未取最佳重复替换。",'',
        '| 评价器 | 成功 / 15 | 失败 / 15 | CCE 三维齐全 / 15 |', '|---|---:|---:|---:|']
    for r in per_model:lines.append(f"| {r['judge']} | {r['technical_successes']} | {r['technical_failures']} | {r['complete_numeric_CCE']} |")
    lines+=['',f"组内 160 组全部保留：完整三次 {summary['within_complete_three']}、部分有效 {summary['within_partial']}、全 NA {summary['within_no_finite']}；可计算范围 {summary['within_range_evaluable']} 组，其中非零 {summary['within_nonzero_range']} 组。仅 1 次有效时范围为 NA，不伪称零波动。",'',
        f"跨评价器 80 组中，至少一对同 repeat 可比较 {summary['between_any_pair_evaluable']} 组，其中有差异 {summary['between_any_pair_different']} 组。逐 repeat 指标配对共 240 格（每指标 5 答案 × 3 次），双方有值 {summary['finite_same_repeat_metric_pairs']} 格，差异 {summary['different_same_repeat_metric_pairs']} 格。双方均完整三次的均值可比较 {summary['between_both_complete_three']} 组，其中均值不同 {summary['between_complete_mean_different']} 组。容差均为 1e-12；部分重复和完整均值不混用。",'',
        '| 指标层 | 组内完整 / 部分 / 全 NA | 非零范围 / 可算范围 | 跨评价器有差异 / 有效组 | 完整均值不同 / 有效组 |',
        '|---|---:|---:|---:|---:|']
    for r in grouped:lines.append(f"| {r['category']} | {r['within_complete_three']} / {r['within_partial']} / {r['within_no_finite']} | {r['within_nonzero_range']} / {r['within_range_evaluable']} | {r['between_any_pair_different']} / {r['between_any_pair_evaluable']} | {r['between_complete_mean_different']} / {r['between_both_complete_three']} |")
    lines+=['','直接评分 5 项、原函数 EGES 4 项、确定性 SR/SP 2 项、派生指标 5 项分层报告。SR/SP 来自同一固定答案与 FDISCO v2 参考的既有离线结果，不是新 judge 的独立返回；失败管线的 16 指标统一 NA，原 step 证据单独保留。Com=0.4×SR+0.6×c_param/3，IA 为三维最小值，HV 为乘积；任一输入未知则保持 NA。','',
        '重复的单位为同一答案上的观测，不是 30 份独立答案。提示版本相同，未混入旧提示、v1 版本或按成败择优。完整实例/理由字符串复制只做字面诊断，不验证语义忠实性；技术成功、零波动或实例不再复制均不能证明科学正确。','',
        f"全部 {recomputed_n} 份成功记录重放原 EGES 与 Cor/Eff，通过原输入、receipt、实传 prompt 和合同绑定。人审包原 5+15、160 行及既定版本不变，没有新增专家标签；全体 formal=false。",'',
        '[30 次观测](observations.json)、[160 组内组](within.json)、[80 跨评价器组](between.json)、[240 同 repeat 指标对](same_repeat_pairs.json)、[字面实例/理由复制](reason_copy_diagnostics.json)、[核验与输入哈希](analysis_verification.json)。','']
    (OUT/'RESULTS_zh.md').write_text('\n'.join(lines),encoding='utf8')
    j.save(OUT/'actual_execution.json',{'utc':j.now(),'argv':[sys.executable,'scripts/cce_analyze_identity_stability_dev_v1.py','analyze'],
        'cwd':str(ROOT),'status':'complete','exit_code':0,'new_requests':0,'script_sha256':j.filehash(__file__),
        'analysis_plan_sha256':j.filehash(OUT/'analysis_plan.json'),'summary_sha256':j.filehash(OUT/'completion_summary.json'),
        'verification_sha256':j.filehash(OUT/'analysis_verification.json')})
    print(j.canonical({k:summary[k] for k in ['status','actual_observations','technical_successful_observations','technical_failed_observations',
        'new_requests_this_batch','within_complete_three','within_partial','within_no_finite','within_nonzero_range','between_any_pair_different','between_both_complete_three','between_complete_mean_different','analysis_new_requests']}))
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','analyze']);arguments=parser.parse_args()
    if arguments.action=='prepare':prepare()
    else:raise SystemExit(analyze())
