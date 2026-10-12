"""Uniform offline public40 + Codex12 + terminal first7 fieldwise replay.

Original statuses, raw files, frozen scorers, and primary results are preserved.
There is no transport/reservation entry point. A new output is mandatory.
"""
import argparse,contextlib,copy,hashlib,importlib,io,json,sys,types
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_operation_coverage_scope_batch_v1 as public
import cce_codex_fieldwise_replay_v3 as codex
import cce_generation_confirmation_v2 as confirmation
import cce_fieldwise_scoring_v4 as fw4
import cce_fieldwise_scoring_v3 as fw3
j=codex.j;base=codex.base;g=codex.g
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'

def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):p=Path(p);return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def quiet(fn,*args):
 with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return fn(*args)
def component_function(module,scorer):
 return types.FunctionType(module.independent_processing.__code__,{**vars(module),'fw':scorer},name='independent_processing_'+scorer.VERSION)

def load_records():
 records=[];bindings=[]
 for r in quiet(public.load_public_records):
  records.append({**r,'baseline_scorer':fw4,'component_module':codex,'baseline_metrics':None})
  bindings+=r['paths']
 plan,cases,_=codex.extension.validate(codex.extension.OUT);matrix=read(codex.extension.OUT/'matrix.json')
 require(len(matrix)==12,'CODEX_TWELVE')
 fw4saved=read(R/'fieldwise_scoring_v4/actual_execution_01/cells.json')
 old={r['cell_id']:r['after_metrics'] for r in fw4saved if r['cohort']=='Codex'}
 bindings += [bind(R/'fieldwise_scoring_v4/actual_execution_01/cells.json')]
 for row in matrix:
  case=next(c for c in cases if c['case_id']==row['case_id']);terminal,raw,doc,chain=codex.verified_terminal(row,case);bindings+=chain
  records.append({'cohort':'Codex','cell_id':row['cell_id'],'anonymous_answer_id':row['anonymous_answer_id'],'status':terminal['status'],
   'case':case,'doc':doc,'step':row['step'],'raw':raw,'baseline_scorer':fw4,'component_module':codex,'baseline_metrics':old[row['cell_id']],'paths':chain})
 out=R/'generation_confirmation_v2';matrix=read(out/'matrix.json');plan=read(out/'plan.json')
 require(len(matrix)==7 and plan['planned']==7,'FIRST_SEVEN_ONLY')
 # All planned terminals must be present before loading their scientific text.
 trials=[]
 for row in matrix:
  t=read(out/'run/trials'/f"{row['planned_trial_id']}.json")
  require(t['status'] in ['success','partial_components','failed'] and t['trial_id']==row['planned_trial_id'] and t['identity']==row['identity'],'FIRST7_TERMINAL_IDENTITY')
  require(type(t['attempt']) is int and t['attempt']==1 and t['actual_request_made'] is True,'FIRST7_ACTUAL_SINGLE_ATTEMPT')
  trials.append(t)
 p,cases,checked_matrix,contract=quiet(confirmation.validate,out)
 require(matrix==checked_matrix,'MATRIX_CHANGED')
 bindings += plan['frozen_inputs']+[bind(out/n) for n in ['plan.json','matrix.json','cases.json','expected_contract.json']]
 ledger=j.ledger_rows(base.budget.LEDGER)
 for row,case,t in zip(matrix,cases,trials):
  tid=row['planned_trial_id'];at=out/'run/attempts'/f'{tid}_1';base.verify_bindings(t['bound_artifacts'])
  rec=read(at/'request_receipt.json');require(rec['trial_id']==tid and rec['request_id']==t['request_id'] and type(rec['attempt']) is int and rec['attempt']==1,'FIRST7_RECEIPT_IDENTITY')
  require(rec['phase']=='confirmation' and rec['model']==row['identity']['judge'],'FIRST7_PHASE_MODEL')
  matched=[v for v in ledger if v.get('request_id')==rec['request_id']]
  require(matched==[rec],'FIRST7_EXACT_LEDGER_RECEIPT')
  raw=(at/'raw_response.txt').read_bytes().decode('utf8');provider=read(at/'provider_response.json')
  require(provider['response']==raw,'FIRST7_PROVIDER_RAW_BYTES')
  require(base.validate_provider(provider,contract['models'][0]['settings'])==raw,'FIRST7_COMPLETED_PROVIDER')
  doc=read(row['assets']['source_document']['path']);saved=read(at/'component_result.json')
  require(saved['metrics']==t['metrics'] and saved['raw_sha256']==g.rawsha(raw),'FIRST7_SAVED_METRICS_RAW')
  base.verify_bindings(row['step']['provenance']);require(all(t['metrics'][k]==row['step'][k] for k in ['sr','sp']),'FIRST7_ORIGINAL_STEPS')
  chain=t['bound_artifacts']+[bind(out/'run/trials'/f'{tid}.json')]+list(row['assets'].values())+row['step']['provenance'];bindings+=chain
  records.append({'cohort':'first7_posthoc','cell_id':row['anonymous_answer_id'],'anonymous_answer_id':row['anonymous_answer_id'],'status':t['status'],
   'case':case,'doc':doc,'step':row['step'],'raw':raw,'baseline_scorer':fw3,'component_module':confirmation.components,'baseline_metrics':t['metrics'],'paths':chain})
 return records,public.unique_bindings(bindings)

def replay(args):
 require(not args.out.exists(),'NEW_OUTPUT_REQUIRED');require(args.scorer in ['cce_fieldwise_scoring_v5','cce_fieldwise_scoring_v6'],'SCORER_EXPLICIT_POSTHOC_NAMESPACE')
 scorer=importlib.import_module(args.scorer);args.out.mkdir(parents=True)
 records,bindings=load_records();require(len(records)==60 and sum(r['raw'] is not None for r in records)==59,'PUBLIC_DENOMINATOR')
 cells=[];functions={}
 for r in records:
  common={k:r[k] for k in ['cohort','cell_id','anonymous_answer_id','status']}
  if r['raw'] is None:
   cells.append({**common,'cancelled_no_raw':True,'original_status_preserved':True});continue
  key=(r['component_module'].__name__,r['baseline_scorer'].__name__)
  functions.setdefault(key,component_function(r['component_module'],r['baseline_scorer']))
  newkey=(r['component_module'].__name__,scorer.__name__);functions.setdefault(newkey,component_function(r['component_module'],scorer))
  before=quiet(functions[key],r['raw'],r['doc'],r['case'],r['step']);after=quiet(functions[newkey],r['raw'],r['doc'],r['case'],r['step'])
  if r['baseline_metrics'] is not None:require(before['metrics']==r['baseline_metrics'],'ORIGINAL_NUMERIC_REPLAY:'+r['cell_id'])
  require(before['raw_sha256']==after['raw_sha256']==g.rawsha(r['raw']),'RAW_IDENTITY')
  for k in base.scoring.DIRECT+['s_method','s_trans','s_label','sr','sp','Com','Cor']:
   require(before['metrics'][k]==after['metrics'][k],'NON_TIME_VALUE_CHANGED:'+r['cell_id']+':'+k)
  if r['cohort']=='E2' and r['anonymous_answer_id'] in ['E2_03','E2_07','E2_11']:require(after['metrics']['s_time'] is None,'TRUE_TIME_DELETION_FILLED')
  diffs={k:{'before':before['metrics'][k],'after':after['metrics'][k]} for k in base.scoring.METRICS if before['metrics'][k]!=after['metrics'][k]}
  cell={**common,'original_status_preserved':True,'baseline_processor':r['baseline_scorer'].VERSION,'posthoc_processor':scorer.VERSION,
   'raw_sha256':g.rawsha(r['raw']),'before_metrics':before['metrics'],'after_metrics':after['metrics'],'changed_metrics':diffs,
   'before_full_conversion':before['full_conversion_success'],'after_full_conversion':after['full_conversion_success'],
   'source_bindings':r['paths']}
  target=args.out/'cells'/r['cohort']/r['cell_id'];save(target/'before.json',before);save(target/'after.json',after)
  cells.append(cell);print(json.dumps({'cohort':r['cohort'],'cell':r['cell_id'],'changed':diffs}),flush=True)
 bycohort={}
 for cohort in dict.fromkeys(r['cohort'] for r in cells):
  rows=[r for r in cells if r['cohort']==cohort and not r.get('cancelled_no_raw')]
  bycohort[cohort]={'actual_raw_returns':len(rows),'original_status_counts':dict(Counter(r['status'] for r in rows)),
   'coverage':{p:{k:sum(base.scoring.finite(r[p+'_metrics'][k]) for r in rows) for k in base.scoring.METRICS} for p in ['before','after']},
   'complete_CCE':{p:sum(all(base.scoring.finite(r[p+'_metrics'][k]) for k in ['Com','Cor','Eff']) for r in rows) for p in ['before','after']},
   'changed_cells':[r['cell_id'] for r in rows if r['changed_metrics']]}
 implementations=[bind(p) for p in [__file__,scorer.__file__,scorer.previous.__file__,scorer.duration_scope.__file__,public.__file__,codex.__file__,confirmation.__file__,confirmation.components.__file__]]
 base.verify_bindings(bindings+implementations)
 save(args.out/'cells.json',cells)
 summary={'status':'completed_uniform_posthoc_replay','actual_raw_returns':59,'cancelled_no_raw_retained':1,'new_model_calls':0,
  'baseline_note':'public40 and Codex12 use fw4; first7 use their frozen fw3; all rows use the same new selected posthoc scorer',
  'posthoc_scorer':scorer.VERSION,'cohorts':bycohort,'changed_cells':[r['cell_id'] for r in cells if r.get('changed_metrics')],
  'all_non_time_metrics_unchanged':True,'original_statuses_and_raw_preserved':True,'primary_results_overwritten':False,
  'confirmation_is_posthoc_not_new_prospective_validation':True,'true_time_deletions_still_NA':['E2_03','E2_07','E2_11'],
  'input_bindings':bindings,'implementations':implementations,'actual_command':[sys.executable,*sys.argv]}
 save(args.out/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in ['input_bindings','implementations']},ensure_ascii=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scorer',required=True);p.add_argument('--out',type=Path,required=True);replay(p.parse_args())
