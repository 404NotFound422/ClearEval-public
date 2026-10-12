"""Uniform posthoc typed-ID + fw5 replay; no model, transport or embedding.

Reads only historical public40, Codex12 and the authorized terminal first7.
The original cancelled Qwen slot is retained separately without creating raw.
"""
import argparse, collections, csv, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_fieldwise_public_posthoc_replay_v1 as inputs
import cce_namespace_fw5_component_replay_v1 as processing
import cce_namespace_fieldwise_v5 as processor

METRICS=list(inputs.base.scoring.METRICS)
require,read,bind,save,quiet=inputs.require,inputs.read,inputs.bind,inputs.save,inputs.quiet

def complete(metrics):
 return all(inputs.base.scoring.finite(metrics[k]) for k in ['Com','Cor','Eff'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 require(not a.out.exists(),'NEW_OUTPUT_REQUIRED')
 records,bindings=inputs.load_records()
 require(len(records)==60 and sum(x['raw'] is not None for x in records)==59,'FIXED_59_PLUS_CANCELLED')
 saved_path=inputs.R/'fieldwise_scoring_v4/actual_execution_01/cells.json'
 saved={(r['cohort'],r['cell_id']):r for r in read(saved_path)};bindings.append(bind(saved_path))
 implementation_paths=[__file__,inputs.__file__,processing.__file__,processor.__file__,processing.namespace.__file__,
   processor.namespace_fw3.__file__,processor.fw4.__file__,processor.fw5.__file__,processor.fw5.duration_scope.__file__,
   inputs.codex.__file__,inputs.public.__file__,inputs.confirmation.__file__]
 implementations=[bind(p) for p in implementation_paths]
 a.out.mkdir(parents=True);cells=[];flat=[]
 for r in records:
  common={k:r[k] for k in ['cohort','cell_id','anonymous_answer_id','status']}
  if r['raw'] is None:
   cells.append({**common,'cancelled_no_raw':True,'original_status_preserved':True})
   continue
  baseline=quiet(inputs.component_function(r['component_module'],r['baseline_scorer']),r['raw'],r['doc'],r['case'],r['step'])
  if r['baseline_metrics'] is not None:
   require(baseline['metrics']==r['baseline_metrics'],'SAVED_BASELINE_MISMATCH:'+r['cell_id'])
  old=saved.get((r['cohort'],r['cell_id']))
  if old:
   require(baseline['metrics']==old['after_metrics'],'EXISTING_FW4_MISMATCH:'+r['cell_id'])
   fw3metrics=old['before_metrics'];fw4metrics=old['after_metrics']
  else:
   require(r['cohort']=='first7_posthoc','UNKNOWN_COHORT')
   fw3metrics=baseline['metrics'];fw4metrics=None
  result=quiet(processing.independent_processing,r['raw'],r['doc'],r['case'],r['step'])
  require(result['raw_sha256']==baseline['raw_sha256']==inputs.g.rawsha(r['raw']),'RAW_HASH_CHANGED')
  require(all(result['metrics'][k]==r['step'][k] for k in ['sr','sp']),'SR_SP_CHANGED')
  if r['cohort']=='E2' and r['anonymous_answer_id'] in ['E2_03','E2_07','E2_11']:
   require(result['metrics']['s_time'] is None,'TRUE_DELETION_IMPUTED')
  changes={k:{'baseline':baseline['metrics'][k],'posthoc':result['metrics'][k]} for k in METRICS if baseline['metrics'][k]!=result['metrics'][k]}
  changes_fw3={k:{'fw3':fw3metrics[k],'posthoc':result['metrics'][k]} for k in METRICS if fw3metrics[k]!=result['metrics'][k]}
  destination=a.out/'cells'/r['cohort']/r['cell_id']
  save(destination/'baseline_replay.json',baseline);save(destination/'posthoc.json',result)
  cell={**common,'raw_sha256':result['raw_sha256'],'original_status_preserved':True,
    'baseline_processor':r['baseline_scorer'].VERSION,'posthoc_processor':processor.VERSION,
    'fw3_metrics':fw3metrics,'existing_fw4_metrics':fw4metrics,'baseline_metrics':baseline['metrics'],
    'posthoc_metrics':result['metrics'],'changes_vs_baseline':changes,'changes_vs_fw3':changes_fw3,
    'baseline_full_conversion':baseline['full_conversion_success'],'posthoc_full_conversion':result['full_conversion_success'],
    'posthoc_full_failure':result.get('full_conversion_or_scoring_failure'),'source_bindings':r['paths']}
  cells.append(cell)
  for k in METRICS:
   flat.append({**common,'metric':k,'fw3':fw3metrics[k],'existing_fw4':fw4metrics[k] if fw4metrics else None,
    'existing_fw4_available':fw4metrics is not None,'posthoc_namespace_fw5':result['metrics'][k],
    'changed_from_fw3':k in changes_fw3,'changed_from_baseline':k in changes})
  print(json.dumps({'cohort':r['cohort'],'cell':r['cell_id'],'changed':changes,'full':result['full_conversion_success']}),flush=True)
 bycohort={}
 for cohort in dict.fromkeys(x['cohort'] for x in cells):
  group=[x for x in cells if x['cohort']==cohort];raws=[x for x in group if not x.get('cancelled_no_raw')]
  bycohort[cohort]={'planned_slots':len(group),'actual_raw_returns':len(raws),
   'original_status_counts':dict(collections.Counter(x['status'] for x in group)),
   'full_conversions':{version:sum(x[version+'_full_conversion'] for x in raws) for version in ['baseline','posthoc']},
   'coverage':{version:{k:sum(inputs.base.scoring.finite(x[version+'_metrics'][k]) for x in raws) for k in METRICS} for version in ['fw3','baseline','posthoc']},
   'complete_CCE':{version:sum(complete(x[version+'_metrics']) for x in raws) for version in ['fw3','baseline','posthoc']},
   'changed_vs_baseline':[x['cell_id'] for x in raws if x['changes_vs_baseline']],
   'changed_vs_fw3':[x['cell_id'] for x in raws if x['changes_vs_fw3']]}
 inputs.base.verify_bindings(bindings+implementations)
 save(a.out/'cells.json',cells)
 with (a.out/'metric_comparison.csv').open('x',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 summary={'status':'completed_uniform_posthoc_not_prospective_validation','planned_slots':60,'raw_returns':59,
   'cancelled_no_raw_retained':1,'metric_comparison_rows':len(flat),'cohorts':bycohort,
   'posthoc_processor':processor.VERSION,'raws_and_original_statuses_unchanged':True,
   'original_confirmation_scores_not_overwritten':True,'new_model_calls':0,'new_embeddings':0,
   'true_duration_deletion_cells_still_NA':['E2_03','E2_07','E2_11'],
   'comparison_scope':'fw3 all59; existing fw4 historical40+Codex12 only; same new namespace+fw5 all59'}
 save(a.out/'summary.json',summary)
 save(a.out/'verification.json',{'status':'pass','input_bindings':bindings,'implementations':implementations,
   'saved_baseline_values_replayed_exactly':True,'all_59_raw_sources_verified':True,
   'original_SR_SP_unchanged':True,'all_original_failures_and_cancelled_slot_retained':True,
   'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,'new_embeddings':0,
   'outputs':[bind(p) for p in a.out.rglob('*') if p.is_file()]})
 print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
