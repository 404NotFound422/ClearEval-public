"""Seal the completed second technical batch, without correcting returned data.

Only original technical audit metadata is decoded. New scientific returns are
processed in memory for identity replay and sealed anonymous expert attachments;
no scientific field values or scores are printed or used for prompt selection.
"""
from __future__ import annotations
import argparse,collections,contextlib,copy,csv,io,json,os,socket,sys,textwrap,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_holdout_remediation_v2 as prep
import cce_rescore_extractions as bridge
import cce_audit_holdout_failures_v1 as audit
j=prep.j
OUT,SEALED,RUN=prep.OUT,prep.SEALED,prep.RUN
AUTO=SEALED/'guarded_auto';REVIEWER=SEALED/'reviewer'
HUMAN=prep.BASE/'human_review';FORM=HUMAN/'reviewer/review_items.csv'
SNAPSHOT=prep.BASE/'historical_reports/before_holdout_remediation_at_116/snapshot_manifest.json'
def require(ok,name):
 if not ok:raise RuntimeError(name)
def bind(p):return {'path':str(Path(p).resolve()),'sha256':j.filehash(p)}
def csvread(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def relative(p):return Path(os.path.relpath(p,REVIEWER)).as_posix()
def save(p,v):j.save(p,v)
def finalize(args):
 require(args.run_finished and args.run_exit_code==0,'coordinator_completion_required')
 plan=prep.validate();require((RUN/'summary.json').exists() and SNAPSHOT.exists(),'complete_run_and_snapshot_required')
 frozen={x['path']:x['sha256'] for x in plan['protected_originals']}
 formhash=j.filehash(FORM);labels=csvread(FORM)
 require(len(labels)==160 and not any(r.get('expert_decision','').strip() for r in labels),'expert_state_changed')
 preflight=j.read(RUN/'preflight.json');contract=preflight['contract'];ch=j.digest(contract)
 approved=j.read(OUT/'preflight_verification.json')
 require(ch==preflight['contract_sha256']==approved['contract_sha256'],'executed_contract_mismatch')
 base={k:v for k,v in contract.items() if k!='prompt_variant'}
 require(j.digest(base)==prep.OLD_CONTRACT,'original_contract_changed')
 runner,registry=bridge.runtime();bridge.verify_contract(contract,registry)
 cases={c['case_id']:c for c in j.read(SEALED/'cases.json')['cases']}
 matrix={c['case_id']:c for c in plan['matrix']}
 identities={r['answer_id']:r for r in csvread(SEALED/'identity_manifest.csv')}
 intended={r['identity']['case_id']:r for r in approved['planned_trials']}
 require(len(cases)==len(matrix)==len(intended)==15,'fixed15_matrix_changed')
 receipts={}
 ledger=[r for r in j.ledger_rows(prep.LEDGER) if r.get('event')=='request_started']
 lb={r['request_id']:r for r in ledger};require(len(lb)==len(ledger),'duplicate_global_request')
 for p in RUN.glob('attempts/*/request_receipt.json'):
  r=j.read(p);require(r['attempt']==1 and r['trial_id'] not in receipts,'duplicate_or_retried_request')
  require(lb.get(r['request_id'])==r,'receipt_ledger_identity');receipts[r['trial_id']]=(p,r)
 trials={}
 for p in (RUN/'trials').glob('*.json'):
  t=j.read(p);require(t['case_id'] not in trials,'duplicate_case_trial');trials[t['case_id']]=(p,t)
 require(set(trials)<=set(matrix) and len(receipts)<=15,'unplanned_batch_cell')
 old={r['answer_id']:r for r in j.read(prep.BASE/'judges/holdout_failure_audit_v1/per_trial_metadata.json')}
 require(len(old)==15 and sum(r['status']=='success' for r in old.values())==7,'original_technical_denominator')
 loader=(ROOT/'OEQ_run_grading_new.py').read_text(encoding='utf-8')
 a=loader.index('        scores_block = llm_output.get("scores", {})')
 b=loader.index('        validate_score_proposals(scores_block)',a)+len('        validate_score_proposals(scores_block)')
 validation_slice=textwrap.dedent(loader[a:b]);validation_code=compile(validation_slice,'original_loader_validation_slice','exec')
 technical=[];checks=[];attempted=success=failed=0;provider_meta=[]
 for cid,cell in matrix.items():
  aid=cell['anonymous_answer_id'];case=cases[cid];expected=intended[cid]
  require(case['references']==[],'no_new_reference_context')
  require(bridge.rawsha(case['specific_question'])==cell['question_sha256'] and bridge.rawsha(case['model_response'])==cell['answer_sha256'],'original_text_hash')
  identity={'case_id':cid,'input_sha256':cell['input_sha256'],'judge':prep.MODEL,'repeat_index':0,'contract_sha256':ch}
  tid=j.digest(identity);require(tid==expected['trial_id'] and identity==expected['identity'],'planned_trial_identity')
  receipt_pair=receipts.get(tid);actual=trials.get(cid)
  status='pending_not_attempted';reason=None;metadata={};request_index=None
  if receipt_pair:attempted+=1;request_index=receipt_pair[1]['package_request_index']
  if receipt_pair and not actual:status='failed';reason='attempt_return_not_recorded';failed+=1
  if actual:
   path,t=actual;require(receipt_pair is not None,'trial_without_receipt')
   rp,receipt=receipt_pair;ad=rp.parent
   require(t['identity']==identity and t['trial_id']==tid and t['attempt']==1,'actual_trial_identity')
   require(t['repeat_index']==0 and t['judge']==prep.MODEL and t['actual_api_request_made'],'fixed_judge_repeat')
   require(t['full_text_input_sha256']==cell['input_sha256'] and t['references_sha256']==j.digest([]),'full_input_and_reference')
   require(j.filehash(ad/'prompt.txt')==t['prompt_sha256']==cell['prompt_sha256'],'exact_transmitted_prompt')
   require((ad/'prompt.txt').read_bytes()==Path(cell['prompt_path']).read_bytes(),'frozen_transmitted_prompt_bytes')
   context=j.read(ad/'context_check.json')
   require(context['conservative_context_bound']==cell['conservative_context_bound']<=40960 and context['max_output_tokens']==8192,'actual_context')
   evaluation=t.get('evaluation',{});pf=ad/'provider_response.json'
   provider=j.read(pf) if pf.exists() else None
   metadata={'provider_response_present':provider is not None,'provider_done':provider.get('done') if provider else None,
    'finish_reason':provider.get('done_reason') if provider else None,'completion_tokens':provider.get('eval_count') if provider else None,
    'recorded_failure_stage':evaluation.get('failure_stage'),'original_strict_parser_pass':False,'original_loader_pass':False}
   parsed=None;env=None
   if provider:
    raw=provider.get('response','');generation=evaluation.get('teacher_generation') or {}
    if generation.get('technical_status')=='VALID':require(raw==generation.get('content'),'provider_content_identity')
    elif isinstance(generation.get('raw_content'),str):require(raw==generation['raw_content'],'failed_provider_content_identity')
    else:require((ad/'provider_error.json').exists(),'adapter_error_provenance')
    try:
     parsed=runner.parse_judge_object(raw.strip());metadata['original_strict_parser_pass']=True
     env={'llm_output':parsed,'validate_teacher_extraction':runner.validate_teacher_extraction,'validate_score_proposals':runner.validate_score_proposals}
     exec(validation_code,env);metadata['original_loader_pass']=True
    except Exception as exc:
     error=audit.error_metadata(exc);metadata['validation_error']=error;reason=error['category']
   if t['status']=='success':
    require(provider is not None and metadata['original_loader_pass'] and t['new_extraction_available'],'success_contract')
    require(env['extraction']==evaluation['extraction'],'returned_extraction_not_modified')
    require(j.digest(evaluation['extraction'])==t['extraction_sha256'],'extraction_hash')
    require(j.proposals(evaluation)==t['preserved_numeric_proposals'],'numeric_proposal_binding')
    require(registry.get(case['question_id'],case['specific_question'])==evaluation['user_preference_vector'],'fixed_demand')
    success+=1;status='success';reason=None
   else:
    failed+=1;status='failed';reason=reason or evaluation.get('failure_stage') or 'technical_failure_unclassified'
    require(all(v is None for v in t.get('preserved_numeric_proposals',{}).values()),'failed_numeric_NA')
   checks.append({'answer_id':aid,'trial_id':tid,'status':status,'request_index':request_index,
    'input_prompt_receipt_contract_bound':True,'returned_extraction_identity_checked':status=='success',
    'trial':bind(path),'receipt':bind(rp),'prompt':bind(ad/'prompt.txt'),'provider':bind(pf) if pf.exists() else None})
  technical.append({'answer_id':aid,'old_status':old[aid]['status'],'new_status':status,
   'old_reason_category':old[aid].get('classification') if old[aid]['status']!='success' else None,
   'new_reason_category':reason,'request_index':request_index,**metadata})
 require(attempted==len(receipts),'attempt_count')
 require(set(receipts)<={r['trial_id'] for r in intended.values()},'unplanned_receipts')
 pending=15-success-failed;require(pending>=0,'negative_pending')
 AUTO.mkdir(parents=True,exist_ok=True)
 ba=types.SimpleNamespace(contract=RUN/'preflight.json',cases=SEALED/'cases.json',steps=SEALED/'step_availability.json',
  trials=RUN/'trials',identities=SEALED/'identity_manifest.csv',judge=prep.MODEL,out=AUTO)
 with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
  bridge.build_auto(ba);bridge.identity(types.SimpleNamespace(auto_inputs=AUTO/'auto_inputs.json',out=AUTO))
 auto=j.read(AUTO/'auto_inputs.json');records={r['answer_id']:r for r in auto['records']}
 replay=j.read(AUTO/'identity_verification.json');require(len(records)==success==replay['actual_source_extractions'],'identity_replay_count')
 require(not success or replay['status']=='pass','identity_replay_failed')
 scores=j.read(AUTO/'auto_scores.json')['records']
 require(all(all(r[k] is None for k in ['sr','sp','Com','IA','HV']) for r in scores),'no_step_or_joint_numeric')
 require(not list(AUTO.glob('*faithful*')) and not (AUTO/'reviewed_no_change.json').exists(),'no_expert_impact_fabrication')
 REVIEWER.mkdir(parents=True,exist_ok=True);packets=[];links=[]
 for cell in plan['matrix']:
  aid=cell['anonymous_answer_id'];ident=identities[aid];case=cases[cell['case_id']];record=records.get(aid)
  packet={'answer_id':aid,'split':'audit_holdout','review_mode':'ASSISTED',
   'version':'development_prompt_v2_technical_followup','read_original_text_before_machine_suggestions':True,
   'task_text':case['specific_question'],'answer_text':case['model_response'],
   'question_sha256':ident['question_sha256'],'answer_sha256':ident['answer_sha256'],
   'references':[],'reference_status':'original_empty_reference_context_preserved',
   'source_family_status':'unmapped_not_independent_source_confirmation',
   'extraction':copy.deepcopy(record['extraction']) if record else None,
   'extraction_sha256':record['extraction_sha256'] if record else None,
   'extraction_status':'actual_automatic_suggestion_not_expert_confirmed' if record else 'pending_no_successful_automatic_extraction',
   'expert_decision':'','source_location':'','correction_or_basis':'','reviewer_id':'','review_date':'','review_status':'not_reviewed',
   'original_text_packet':relative(HUMAN/'reviewer'/f'{aid}.json'),'shared_expert_form':relative(FORM),
   'notice':'Separate prompt-version suggestion, not a corrected original return or expert conclusion. Original 15 suggestions remain separately archived.'}
  require(bridge.rawsha(packet['task_text'])==ident['question_sha256'] and bridge.rawsha(packet['answer_text'])==ident['answer_sha256'],'anonymous_fulltext_binding')
  require(not any(k in packet for k in ['model','generator_model','judge','scores','Cor','Eff','IA','HV','Com']),'anonymous_metadata')
  dest=REVIEWER/f'{aid}.json'
  if dest.exists():require(j.read(dest)==packet,'existing_attachment_changed')
  else:save(dest,packet)
  packets.append(bind(dest));links.append(f'| {aid} | [{aid}.json]({aid}.json) | [原题与全文]({relative(HUMAN/"reviewer"/f"{aid}.json")}) |')
 (REVIEWER/'README.md').write_text('# 固定15份：开发提示v2技术后续附件\n\n先读原题和全文，再核查自动建议。ASSISTED不是独立盲评；没有预填专家结论。原版本附件另行保留，不按新旧成功或分数挑选建议。\n\n在[原160行共用表]('+relative(FORM)+')的既有匿名ID填写；注明所审建议版本。技术失败保持提取待定。模型身份和总分不在本入口中。\n\n| 匿名ID | 本版本建议与全文 | 原始文本入口 |\n|---|---|---|\n'+'\n'.join(links)+'\n',encoding='utf-8')
 transitions=collections.Counter()
 for r in technical:
  if r['new_status'] in ['success','failed']:
   transitions['old_'+('success' if r['old_status']=='success' else 'failure')+'_new_'+('success' if r['new_status']=='success' else 'failure')]+=1
 for k in ['old_success_new_success','old_success_new_failure','old_failure_new_success','old_failure_new_failure']:transitions.setdefault(k,0)
 request_indices=sorted(r['package_request_index'] for _,r in receipts.values())
 summary={'status':'completed_separate_technical_followup','selected_cells':15,'attempted_cells':attempted,'successful_cells':success,
  'failed_cells':failed,'pending_cells':pending,'new_requests':len(receipts),'package_requests':len(ledger),
  'package_requests_at_batch_completion':max(request_indices) if request_indices else plan['package_requests_before'],
  'request_indices':request_indices,'identity_verified_cells':replay['actual_source_extractions'],
  'original_successful_cells':7,'original_failed_cells':8,'paired_transitions':dict(transitions),
  'failure_reason_categories':dict(collections.Counter(r['new_reason_category'] for r in technical if r['new_status']=='failed')),
  'expert_returns':0,'faithful_corrections':0,'numeric_CCE':0,'references_covered_in_this_batch':0,'source_family_unmapped':15,
  'reviewer_attachment_dir':str(REVIEWER),'reviewer_entry':str(REVIEWER/'README.md'),'anonymous_attachment_count':15,
  'formal_eligible':False,'scientific_holdout_accuracy_evidence':False,'original_15_preserved':True,
  'new_model_requests_during_finalization':0,'scope':'All15 repeated under frozen development-tested prompt; technical outcomes only. No old/new best-of mixing, no source-step results imported.'}
 save(OUT/'technical_comparison.json',technical)
 fields=list(dict.fromkeys(k for r in technical for k in r))
 with (OUT/'technical_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in technical)
 save(SEALED/'technical_identity_checks.json',{'status':'pass','cells':checks,'guarded_identity':bind(AUTO/'identity_verification.json'),
  'validation_slice_sha256':bridge.rawsha(validation_slice),'packet_bindings':packets,'contract_sha256':ch,'new_model_requests':0})
 require(j.filehash(FORM)==formhash and all(j.filehash(p)==h for p,h in frozen.items()),'original_files_or_form_changed')
 prep.validate()
 save(OUT/'attachment_verification.json',{'status':'pass','attachments':15,'successful_actual_extractions':success,'failed_pending_extractions_not_fabricated':failed+pending,
  'original_fulltext_hashes_verified':15,'identity_replays_passed':success,'expert_fields_empty':True,'original160_form_unchanged':True,
  'original_protected_files_unchanged':len(frozen),'anonymous_metadata_hidden':True,'packet_bindings':packets,'new_model_requests':0})
 shell="& '"+sys.executable+"' 'scripts/cce_holdout_remediation_v2.py' 'run' '--allow-local-calls' *> 'artifacts/cce_validation/judges/holdout_remediation_v2/sealed/run_console.log'"
 save(OUT/'finalization_execution.json',{'status':'completed','run_command_root':shell,'root_session':41162,'run_exit_code':0,
  'run_command_provenance':'coordinator supplied actual argv/redirection; receipts independently bound to ledger',
  'finalizer_command':[sys.executable,*sys.argv],'cwd':str(ROOT),'script':bind(__file__),'pre_run_snapshot':bind(SNAPSHOT),
  'plan':bind(OUT/'plan.json'),'new_model_requests':0,'original_judge_scientific_outputs_decoded':0,'new_scientific_values_publicly_exported':0})
 save(OUT/'completion_summary.json',summary)
 print(j.canonical({k:summary[k] for k in ['status','selected_cells','attempted_cells','successful_cells','failed_cells','pending_cells','new_requests','package_requests','package_requests_at_batch_completion','identity_verified_cells','paired_transitions','failure_reason_categories']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['finalize']);p.add_argument('--run-finished',action='store_true');p.add_argument('--run-exit-code',type=int);args=p.parse_args()
 try:finalize(args)
 except Exception as exc:
  import traceback
  frames=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]
  save(OUT/'finalization_failure.json',{'status':'offline_finalization_incomplete','exception_type':type(exc).__name__,'code_frames':frames,'new_model_requests':0})
  print(j.canonical({'status':'offline_finalization_incomplete','exception_type':type(exc).__name__,'code_frames':frames,'new_model_requests':0}));sys.exit(1)
