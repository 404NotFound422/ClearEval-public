"""Repeat all 67 rows under v2, preserving the full v1 snapshot."""
import argparse,json,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_posthoc_uniform_replay_v1 as original
import cce_posthoc_components_v2 as components
import cce_posthoc_scoring_v2 as scorer
io=original.io

def main():
    # Reuse the exact uniform input/metric comparison procedure. Its function
    # globals are private; no old module or output is modified.
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    deps=[io.bind(p) for p in [__file__,original.__file__,scorer.__file__,components.__file__,
        scorer.boundary.__file__,scorer.boundary.previous.__file__,scorer.boundary.concentration.__file__]]
    execute=types.FunctionType(original.main.__code__,{**vars(original),'scorer':scorer,
        'components':components,'__file__':__file__},name='uniform_replay_v2')
    execute()
    prior=io.R/'posthoc_uniform_scoring_v1/actual_execution_01/cells.json'
    before={(r['cohort'],r['cell_id']):r for r in io.read(prior)}
    after=io.read(args.out/'cells.json');rows=[]
    for r in after:
        old=before[r['cohort'],r['cell_id']]
        assert r['status']==old['status']
        if r.get('cancelled_no_raw'):continue
        assert r['raw_sha256']==old['raw_sha256']
        diff={k:{'v1':old['posthoc_metrics'][k],'v2':r['posthoc_metrics'][k]} for k in original.METRICS if old['posthoc_metrics'][k]!=r['posthoc_metrics'][k]}
        rows.append({'cohort':r['cohort'],'cell_id':r['cell_id'],'changes':diff,
            'full_conversion_v1':old['posthoc_full_conversion'],'full_conversion_v2':r['posthoc_full_conversion']})
    io.base.verify_bindings(deps+[io.bind(prior)])
    io.save(args.out/'v1_comparison.json',{'all67_same_v2_configuration':True,'rows':rows,
        'changed_numeric_rows':[r for r in rows if r['changes']],
        'full_conversion_changes':[r for r in rows if r['full_conversion_v1']!=r['full_conversion_v2']],
        'original_v1':io.bind(prior),'new_model_calls':0})
    io.save(args.out/'implementation_addendum.json',{'status':'pass','additional_implementation_bindings':deps,
        'exact_old_uniform_procedure_reused':True,'same_named_source_boundary_applies_to_entities_and_endpoints':True,
        'old_v1_snapshot_not_overwritten':True,'actual_command':[sys.executable,*sys.argv],
        'new_model_calls':0,'outputs':[io.bind(args.out/n) for n in ['summary.json','verification.json','v1_comparison.json']]})
    print(json.dumps({'changed_numeric_rows':[r for r in rows if r['changes']]}))
if __name__=='__main__':main()
