"""Summarize final uniform-v3 E4 observations without rescoring or new calls."""
import argparse,collections,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts')]
import cce_compare_public_judges_fw3 as old
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
CATEGORIES={**old.CATEGORIES,'deterministic_steps':['sr','sp']}

def checks():
 assert old.stats([None,None])['range'] is None
 assert old.stats([1,None])['sample_sd'] is None
 assert old.stats([0,0,None])['range']==0
 assert old.stats([1,2,None])['finite_n']==2
 assert abs(old.stats([1,2,None])['sample_sd']-2**-.5)<1e-12
 return {'checks':5,'passed':5,'actual_original_stats_reused':True,'new_model_calls':0}

def run(source,out):
 assert not out.exists(),'NEW_OUTPUT_REQUIRED'
 s=old.load(source/'summary.json');v=old.load(source/'verification.json');a=old.load(source/'implementation_addendum.json')
 assert s['status']=='completed_uniform_posthoc_not_new_confirmation' and s['raw_returns']==67
 assert v['status']=='pass' and a['status']=='pass' and a['all67_label_views_audited'] is True
 p=source/'cells.json';declared=next(b for b in v['outputs'] if Path(b['path']).resolve()==p.resolve());old.verify([declared])
 cells=old.load(p);selected={(r['cohort'],r['cell_id']):r for r in cells if r['cohort'] in ['Qwen_repeats','Codex']}
 assert len(selected)==27 and sum(x.get('cancelled_no_raw',False) for x in selected.values())==1
 priorpath=R/'e4_cross_source_fw3_v1/actual_execution_02/observations.json';prior=old.load(priorpath)
 assert len(prior)==27
 observations=[];deltas=[]
 for p in prior:
  cohort='Qwen_repeats' if p['source']=='Qwen' else 'Codex';r=selected[cohort,p['cell_id']]
  assert p['answer_id']==r['anonymous_answer_id'] and p['original_status']==r['status']
  metrics=r['posthoc_metrics']
  assert all(metrics[k]==p['metrics'][k] for k in old.DIRECT+['sr','sp','Com','Cor'])
  cancelled=r.get('cancelled_no_raw',False)
  if cancelled:
   assert r['status']=='user_cancelled_no_retry'
   assert all(metrics[k] is None for k in old.DIRECT+old.EGES+old.AGG)
  else:
   assert r['raw_sha256'] and r['posthoc_record']['sha256']
   old.verify([r['posthoc_record']])
  row={**{k:p[k] for k in ['source','answer_id','cell_id','repeat','original_status']},
      'actual_return':not cancelled,'cancelled_no_raw':cancelled,'metrics':metrics,
      'raw_sha256':r.get('raw_sha256'),'uniform_posthoc_record':r.get('posthoc_record'),
      'same_existing_return_not_new_judgment':True}
  observations.append(row)
  deltas.append({'source':p['source'],'answer_id':p['answer_id'],'cell_id':p['cell_id'],
   'changes':{k:{'fw3':p['metrics'][k],'uniform_v3':metrics[k]} for k in old.METRICS if p['metrics'][k]!=metrics[k]}})
 assert sum(x['actual_return'] for x in observations)==26
 within=[];between=[]
 for source_name in ['Qwen','Codex']:
  for aid in ['A01','A02','A03','A04','A05']:
   rows=[r for r in observations if r['source']==source_name and r['answer_id']==aid]
   assert len(rows)==(3 if source_name=='Qwen' or aid in ['A01','A02'] else 2)
   for category,metrics in CATEGORIES.items():
    for m in metrics:within.append({'source':source_name,'answer_id':aid,'category':category,'metric':m,
     'judge_stability_evidence':category!='deterministic_steps',**old.stats([r['metrics'][m] for r in rows])})
 for aid in ['A01','A02','A03','A04','A05']:
  for category,metrics in CATEGORIES.items():
   for m in metrics:
    q=next(r for r in within if r['source']=='Qwen' and r['answer_id']==aid and r['metric']==m)
    c=next(r for r in within if r['source']=='Codex' and r['answer_id']==aid and r['metric']==m)
    delta=c['mean_all_finite']-q['mean_all_finite'] if q['finite_n'] and c['finite_n'] else None
    between.append({'answer_id':aid,'category':category,'metric':m,'judge_stability_evidence':category!='deterministic_steps',
     'Qwen_planned':q['planned_n'],'Qwen_finite':q['finite_n'],'Qwen_values':q['values'],'Qwen_mean':q['mean_all_finite'],
     'Codex_planned':c['planned_n'],'Codex_finite':c['finite_n'],'Codex_values':c['values'],'Codex_mean':c['mean_all_finite'],
     'Codex_minus_Qwen':delta,'absolute_difference':abs(delta) if delta is not None else None,
     'both_at_least_two_finite':q['finite_n']>=2 and c['finite_n']>=2})
 assert len(within)==160 and len(between)==80
 summary={'status':'completed_uniform_posthoc_descriptive_E4','source_processing_version':s['scorer_version'],
  'planned_slots':27,'actual_returns':26,'cancelled_no_retry':1,'planned_by_source':{'Qwen':15,'Codex':12},
  'original_status_counts':{n:dict(collections.Counter(x['original_status'] for x in observations if x['source']==n)) for n in ['Qwen','Codex']},
  'finite_coverage':{n:{m:sum(old.finite(x['metrics'][m]) for x in observations if x['source']==n) for m in old.METRICS} for n in ['Qwen','Codex']},
  'complete_CCE':{n:sum(all(old.finite(x['metrics'][m]) for m in ['Com','Cor','Eff']) for x in observations if x['source']==n) for n in ['Qwen','Codex']},
  'within_rows':160,'between_rows':80,'within':{},'between':{},'range_requires_n_at_least':2,'sample_sd_ddof':1,'tolerance':old.TOL,
  'cross_mean_policy':'all finite repetitions for same answer/metric; no maximum, no complete-three selection',
  'direct_Com_Cor_SR_SP_exactly_unchanged_from_fw3':True,'deterministic_steps_not_judge_stability':True,
  'scientific_accuracy_validated':False,'independent_judge_family_verified':False,'posthoc_not_new_model_observations':True,
  'new_model_calls':0,'new_scores':0,'actual_command':[sys.executable,*sys.argv]}
 for cat in CATEGORIES:
  summary['within'][cat]={}
  for n in ['Qwen','Codex']:
   rows=[r for r in within if r['category']==cat and r['source']==n]
   summary['within'][cat][n]={'planned_groups':len(rows),'n_ge_2':sum(r['range_evaluable'] for r in rows),
    'singleton':sum(r['finite_n']==1 for r in rows),'zero_finite':sum(r['finite_n']==0 for r in rows),
    'nonzero_range':sum(r['nonzero_range'] is True for r in rows),'all_planned_finite':sum(r['all_planned_finite'] for r in rows)}
  rows=[r for r in between if r['category']==cat]
  summary['between'][cat]={'planned_groups':len(rows),'at_least_one_each':sum(r['Codex_minus_Qwen'] is not None for r in rows),
   'different_mean':sum(r['absolute_difference'] is not None and r['absolute_difference']>old.TOL for r in rows),
   'both_n_ge_2':sum(r['both_at_least_two_finite'] for r in rows)}
 out.mkdir(parents=True)
 for name,value in [('observations',observations),('within',within),('between',between),('fw3_comparison',deltas),('summary',summary)]:old.save(out/(name+'.json'),value)
 old.csvsave(out/'observations.csv',[{k:v for k,v in r.items() if k!='metrics'}|r['metrics'] for r in observations])
 old.csvsave(out/'within.csv',within);old.csvsave(out/'between.csv',between)
 old.verify(list(old.BINDINGS.values()))
 old.save(out/'verification.json',{'status':'pass','input_bindings':list(old.BINDINGS.values()),
  'implementations':[old.binding(__file__),old.binding(old.__file__)],'all27_slots_retained':True,
  'no_raw_or_source_text_read_or_reprocessed':True,'old_statistical_functions_reused':True,
  'original_direct_SRSP_and_states_retained':True,'no_new_model_calls_or_scoring':True})
 print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path);p.add_argument('--out',type=Path);p.add_argument('--self-check',action='store_true');a=p.parse_args()
 if a.self_check:print(json.dumps(checks()))
 else:
  assert a.input is not None and a.out is not None
  run(a.input.resolve(),a.out.resolve())
