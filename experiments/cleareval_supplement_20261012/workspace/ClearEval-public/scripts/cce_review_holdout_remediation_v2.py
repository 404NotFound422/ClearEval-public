"""Metadata-only design and provenance review; no original holdout science reads."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];J=ROOT/'artifacts/cce_validation/judges';OUT=J/'holdout_remediation_v2'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
def main():
 plan=read(OUT/'plan.json');pre=read(OUT/'preflight_verification.json');runpre=read(OUT/'sealed/run/preflight.json')
 for group in ['frozen_inputs','protected_originals']:
  for b in plan[group]:assert sha(b['path'])==b['sha256']
 assert len(plan['matrix'])==15 and [c['anonymous_answer_id'] for c in plan['matrix']]==[f'A{i:02}' for i in range(6,21)]
 assert len({r['trial_id'] for r in pre['planned_trials']})==15
 assert all(c['attempt']==1 and c['repeat_index']==0 and c['judge']=='local_qwen3_8b' for c in plan['matrix'])
 assert sha(OUT/'sealed/cases.json')==sha(J/'local_extraction_holdout_v1/sealed/cases.json')
 assert sha(OUT/'local_config_snapshot.json')==sha(J/'local_extraction_holdout_v1/local_config_snapshot.json')
 cases=read(OUT/'sealed/cases.json')['cases'];assert all(c['references']==[] for c in cases)
 by={c['case_id']:c for c in cases}
 for c in plan['matrix']:
  assert hashlib.sha256(by[c['case_id']]['specific_question'].encode('utf-8')).hexdigest()==c['question_sha256']
  assert hashlib.sha256(by[c['case_id']]['model_response'].encode('utf-8')).hexdigest()==c['answer_sha256']
  assert sha(c['prompt_path'])==c['prompt_sha256']
  assert len(Path(c['prompt_path']).read_text(encoding='utf-8').encode('utf-8'))+8192+256==c['conservative_context_bound']<=40960
 assert runpre['contract_sha256']==pre['contract_sha256']
 assert digest(runpre['contract'])==pre['contract_sha256']
 base={k:v for k,v in runpre['contract'].items() if k!='prompt_variant'}
 assert digest(base)==plan['original_contract_sha256']=='c27211dc7513d3ac24ee211ce3950eb1a1d0b553e87b0374b93190fc7dfe56ae'
 summary=read(OUT/'completion_summary.json');comparison=read(OUT/'technical_comparison.json')
 assert len(comparison)==15 and sum(r['new_status']=='success' for r in comparison)==summary['successful_cells']
 assert sum(summary['paired_transitions'].values())==15
 inputs=[J/'holdout_failure_audit_v1/summary.json',J/'holdout_failure_audit_v1/contract_findings.json',
  J/'stability_remediation_v2/final_output_schema.json',J/'stability_remediation_v2/config_delta.json',
  J/'stability_remediation_v2/analysis/report_facts.json',OUT/'plan.json',OUT/'preflight_verification.json',
  ROOT/'scripts/cce_holdout_remediation_v2.py',ROOT/'evaluator_integrity.py',ROOT/'OEQ_run_grading_new.py',
  OUT/'completion_summary.json',OUT/'attachment_verification.json']
 report={'schema':'holdout-remediation-v2-design-and-runner-review-v1','status':'pass_with_declared_scope_limits',
  'review_timing':'Key recommendation and runner review sent to coordinator before/during execution; this durable record also binds the completed technical summary.',
  'new_model_requests':0,'old_holdout_scientific_outputs_read':0,'expert_confirmations':0,
  'recommendation':'Use the already development-tested v2 prompt unchanged on all original15 in a separate version; retain original results and every failure. No nested-key alias repair or returned-data correction.',
  'evidence':{'old_technical_success':7,'old_technical_failure':8,'failure_first_gate_counts':{'missing_score_record':3,'missing_extraction_fields':4,'duplicate_JSON_key_at_adapter':1},
   'old_all_provider_returns_done_stop':True,'development_v2_success':12,'development_v2_total':12,'development_distinct_answers':2,
   'development_distinct_judges':2,'development_repeats_per_answer_judge':3,'development_is_not_12_independent_answers':True},
  'minimum_intervention':{'new_prompt_edits_from_developed_v2':0,'loader_changes':0,'schema_changes':0,
   'scientific_rubric_or_EGES_changes':0,'demand_changes':0,'references_for_each_case':[],
   'full_question_answer_changed':False,'old_success_reused_as_new_trial':False},
  'nested_C_Co_decision':{'include_new_intervention_in_v2':False,
   'reason':'The frozen v2 deliberately retains uppercase section examples. Silently normalizing nested return keys would change acceptance and repair data after observation.',
   'residual_risk':'The prompt still contains local uppercase score examples while the canonical nested contract requires lowercase keys; v2 success must be measured, not assumed.',
   'future_option':'A separate prompt-only consistency intervention could be developed on all fixed A01-A05, with exact diffs and unchanged scientific rules, before any subsequent cohort application.'},
  'preflight_verified':{'fixed_cases':15,'unique_planned_trials':15,'attempts_each':1,'repeat_index':0,
   'same_old_case_file_hash':True,'same_old_model_configuration_hash':True,'all_references_empty':True,
   'conservative_context_bound_min':min(c['conservative_context_bound'] for c in plan['matrix']),
   'conservative_context_bound_max':max(c['conservative_context_bound'] for c in plan['matrix']),
   'output_tokens':8192,'context_capacity':40960,'temperature':0,
   'old_contract_sha256':plan['original_contract_sha256'],'new_contract_sha256':pre['contract_sha256'],
   'frozen_input_hashes_verified':len(plan['frozen_inputs']),'protected_original_hashes_verified':len(plan['protected_originals'])},
  'prespecified_matrix':{'anonymous_ids':[f'A{i:02}' for i in range(6,21)],'judge':'local_qwen3_8b','cells':15,
   'selection':'all originally fixed answers, not only failures','max_new_requests':15,'ledger_at_preparation':116,'planned_batch_end':131,
   'no_retry_no_replacement_no_score_based_gate':True},
  'required_reporting':['all15 technical success/failure/pending with fixed denominator',
   'paired old/new 2x2 technical transitions including regressions','strict JSON, required-field and provider-stage failure categories',
   'actual receipts, transmitted prompt hashes, model/config/input identity and request counts',
   'failed/unknown values remain NA; complete CCE stays unavailable with empty references',
   'new and old prompt versions remain separate; no best-of-version combined score',
   'technical validity and extraction/rubric scientific accuracy reported separately; latter awaits original expert'],
  'completed_technical_outcomes':{k:summary[k] for k in ['successful_cells','failed_cells','pending_cells','new_requests','request_indices','identity_verified_cells','paired_transitions','failure_reason_categories']},
  'schema_constrained_decoding_followup':{'assessment':'Reasonable separate transport-level hypothesis; may improve canonical field presence without changing scientific criteria, but does not guarantee all loader constraints or correctness.',
   'fixed_development_gate':'All5 original development answers; require prespecified5/5 technical success before a separately frozen all15 followup. No holdout-based tuning.',
   'no_silent_schema_or_parser_changes':True,
   'limitations':['The prompt schema is a structure guide, not a full executable replica of all runtime validation rules.',
    'Duplicate JSON keys must still be rejected by the original strict parser; decoder acceptance alone cannot certify uniqueness.',
    'Optional unknown-field restrictions and group-total/null dependencies still require the original loader.',
    'Do not truncate inputs, add defaults, normalize aliases or convert explicit unknown values to known zero.'],
   'actual_schema_followup_results_not_used_for_v2_design':'Subsequent followup is independently owned and reported; no v2 changes based on it.'},
  'formal_eligible':False,'new_independent_holdout_accuracy_evidence':False,
  'source_bindings':[{'path':str(p),'sha256':sha(p)} for p in inputs],
  'review_script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv],'utc':datetime.now(timezone.utc).isoformat()}
 p=J/'holdout_remediation_v2_design_review.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':report['status'],'fixed_cases':15,'protected_originals_verified':len(plan['protected_originals']),'new_model_requests':0,'review_sha256':sha(p)},ensure_ascii=True))
if __name__=='__main__':main()
