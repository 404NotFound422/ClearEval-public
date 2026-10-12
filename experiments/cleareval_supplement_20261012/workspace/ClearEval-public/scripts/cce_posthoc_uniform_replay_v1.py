"""Same posthoc configuration for all 67 returns; frozen originals retained."""
import argparse,collections,csv,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_posthoc_replay_inputs_v1 as loader
import cce_posthoc_components_v1 as components
import cce_posthoc_scoring_v1 as scorer
io=loader.previous
METRICS=list(io.base.scoring.METRICS)
STABLE=list(io.base.scoring.DIRECT)+['sr','sp','Com','Cor']
def complete(m):return all(io.base.scoring.finite(m[k]) for k in ['Com','Cor','Eff'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    io.require(not args.out.exists(),'NEW_OUTPUT_REQUIRED')
    args.out.mkdir(parents=True)
    io.save(args.out/'execution_intent.json',{'actual_command':[sys.executable,*sys.argv],
        'script':io.bind(__file__),'scorer':io.bind(scorer.__file__),'new_model_calls':0})
    records,bindings=loader.load_records()
    prior_path=io.R/'namespace_fw5_uniform_replay_v1/actual_execution_01/cells.json'
    prior={(r['cohort'],r['cell_id']):r for r in io.read(prior_path)};bindings.append(io.bind(prior_path))
    implementations=[io.bind(p) for p in [__file__,loader.__file__,components.__file__,scorer.__file__,
        scorer.boundary.__file__,scorer.boundary.first.__file__,scorer.boundary.namespace.__file__,
        scorer.frozen_fw3.__file__,scorer.fw4.__file__,scorer.fw6.__file__,scorer.fw6.noncore_scope.__file__,
        scorer.fw6.previous.__file__,scorer.fw6.duration_scope.__file__,scorer.alias.__file__,
        components.original.__file__,io.__file__,loader.secondary.__file__]]
    cells=[];flat=[]
    for r in records:
        common={k:r[k] for k in ['cohort','cell_id','anonymous_answer_id','status']}
        if r['raw'] is None:
            cells.append({**common,'cancelled_no_raw':True,'original_metrics':r['original_metrics'],
                'posthoc_metrics':r['original_metrics'],'original_status_preserved':True});continue
        old=prior.get((r['cohort'],r['cell_id']))
        if old:
            io.require(old['raw_sha256']==io.g.rawsha(r['raw']),'PRIOR_RAW_IDENTITY')
            fw3=old['fw3_metrics'];fw4=old['existing_fw4_metrics'];baseline=old['baseline_metrics']
        else:
            io.require(r['cohort']=='secondary8_posthoc','UNEXPECTED_ADDED_COHORT')
            previous=io.quiet(io.component_function(r['component_module'],r['baseline_scorer']),r['raw'],r['doc'],r['case'],r['step'])
            io.require(previous['metrics']==r['baseline_metrics'],'FROZEN_SECONDARY_FW3_REPLAY')
            fw3=baseline=previous['metrics'];fw4=None
            io.save(args.out/'cells'/r['cohort']/r['cell_id']/'frozen_fw3_replay.json',previous)
        result=io.quiet(components.independent_processing,r['raw'],r['doc'],r['case'],r['step'])
        io.require(result['raw_sha256']==io.g.rawsha(r['raw']),'RAW_CHANGED')
        io.require(all(result['metrics'][k]==baseline[k] for k in STABLE),'DIRECT_COM_COR_STEPS_CHANGED:'+r['cell_id'])
        io.require(all(result['metrics'][k]==r['step'][k] for k in ['sr','sp']),'ORIGINAL_STEPS_CHANGED')
        if r['cohort']=='E2' and r['anonymous_answer_id'] in ['E2_03','E2_07','E2_11']:
            io.require(result['metrics']['s_time'] is None,'TRUE_TIME_DELETION_FILLED')
        diff=lambda m:{k:{'before':m[k],'after':result['metrics'][k]} for k in METRICS if m[k]!=result['metrics'][k]}
        target=args.out/'cells'/r['cohort']/r['cell_id']/'posthoc.json';io.save(target,result)
        cell={**common,'original_status_preserved':True,'raw_sha256':result['raw_sha256'],
            'question_id':r['case']['question_id'],'original_metrics':r['original_metrics'],
            'frozen_fw3_metrics':fw3,'existing_fw4_metrics':fw4,'comparison_baseline_metrics':baseline,
            'posthoc_metrics':result['metrics'],'changes_from_original':diff(r['original_metrics']),
            'changes_from_fw3':diff(fw3),'changes_from_comparison_baseline':diff(baseline),
            'posthoc_full_conversion':result['full_conversion_success'],
            'posthoc_failure':result.get('full_conversion_or_scoring_failure'),'posthoc_record':io.bind(target),
            'source_bindings':r['paths']}
        cells.append(cell)
        for k in METRICS:
            flat.append({**common,'metric':k,'original_frozen':r['original_metrics'][k],'fw3':fw3[k],
                'existing_fw4':fw4[k] if fw4 else None,'fw4_available':fw4 is not None,'final_posthoc':result['metrics'][k],
                'changed_from_original':r['original_metrics'][k]!=result['metrics'][k],
                'changed_from_fw3':fw3[k]!=result['metrics'][k]})
        print(json.dumps({'cohort':r['cohort'],'cell':r['cell_id'],'full':result['full_conversion_success'],
            'changes':cell['changes_from_comparison_baseline']}),flush=True)
    cohorts={}
    for name in dict.fromkeys(r['cohort'] for r in cells):
        group=[r for r in cells if r['cohort']==name];rows=[r for r in group if not r.get('cancelled_no_raw')]
        versions={'original':'original_metrics','fw3':'frozen_fw3_metrics','posthoc':'posthoc_metrics'}
        cohorts[name]={'planned_slots':len(group),'actual_raw_returns':len(rows),
            'original_status_counts':dict(collections.Counter(x['status'] for x in group)),
            'coverage':{v:{k:sum(io.base.scoring.finite(x[key][k]) for x in rows) for k in METRICS} for v,key in versions.items()},
            'complete_CCE':{v:sum(complete(x[key]) for x in rows) for v,key in versions.items()},
            'posthoc_full_conversions':sum(x['posthoc_full_conversion'] for x in rows),
            'changed_from_fw3':[x['cell_id'] for x in rows if x['changes_from_fw3']],
            'unchanged_from_comparison_baseline':[x['cell_id'] for x in rows if not x['changes_from_comparison_baseline']]}
    io.base.verify_bindings(bindings+implementations)
    io.save(args.out/'cells.json',cells)
    with (args.out/'metric_comparison.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    summary={'status':'completed_uniform_posthoc_not_new_confirmation','scorer_version':scorer.VERSION,
        'planned_slots':68,'raw_returns':67,'cancelled_no_raw':1,'comparison_rows':len(flat),'cohorts':cohorts,
        'direct_Com_Cor_SR_SP_unchanged_vs_fieldwise_baseline':True,'same_configuration_all67':True,
        'original_frozen_metrics_retained_all67':True,'original_statuses_and_raw_unchanged':True,
        'old52_fw3_and_fw4_comparisons_separate':True,'confirmed_scientific_accuracy':False,
        'time_phase_semantics_remain_separately_auditable':True,'new_model_calls':0,'new_embeddings':0,
        'true_time_deletions_still_NA':['E2_03','E2_07','E2_11']}
    io.save(args.out/'summary.json',summary)
    io.save(args.out/'verification.json',{'status':'pass','implementations':implementations,'input_bindings':bindings,
        'all67_source_chains_verified':True,'original_SR_SP_retained':True,'direct_Com_Cor_stable':True,
        'all_original_failures_and_cancelled_slot_retained':True,'actual_command':[sys.executable,*sys.argv],
        'new_model_calls':0,'new_embeddings':0,'outputs':[io.bind(p) for p in args.out.rglob('*') if p.is_file()]})
    print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
