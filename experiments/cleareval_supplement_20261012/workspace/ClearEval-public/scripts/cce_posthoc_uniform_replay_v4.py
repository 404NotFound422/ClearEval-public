"""Uniform v4 replay: unchanged 67-return cohort, label-only source repair."""
import argparse,csv,json,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_posthoc_uniform_replay_v1 as original
import cce_posthoc_components_v4 as components
import cce_posthoc_scoring_v4 as scorer
io=original.io

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    deps=[io.bind(x) for x in [__file__,original.__file__,components.__file__,scorer.__file__,
        scorer.previous.__file__,scorer.source_binding.__file__,scorer.boundary.__file__,
        scorer.boundary.concentration.__file__,scorer.boundary.syntax.__file__,scorer.boundary.attached.__file__,
        scorer.time_scope.__file__,scorer.time_scope.scope.__file__,scorer.time_scope.phase_scope.__file__,
        scorer.time_scope.wash_scope.__file__,scorer.target_scope.__file__,scorer.labels.__file__,components.isolation.__file__]]
    review=io.R/'label_source_binding_review_v1/revision03/review.json'
    checked=io.read(review)
    io.require(checked['status']=='pass','INDEPENDENT_SOURCE_REVIEW_REQUIRED')
    io.require(checked['module_sha256']==io.bind(scorer.source_binding.__file__)['sha256'],'SOURCE_REVIEW_HASH_MISMATCH')
    deps.append(io.bind(review))
    isolation_review=io.R/'label_source_binding_review_v1/isolation_review/review.json'
    ir=io.read(isolation_review)
    io.require(ir['status']=='pass' and ir['module_sha256']==io.bind(components.isolation.__file__)['sha256'],'ISOLATION_REVIEW_REQUIRED')
    deps.append(io.bind(isolation_review))
    integration_review=io.R/'label_source_binding_review_v1/isolation_integration/review.json'
    integrated=io.read(integration_review)
    io.require(integrated['status']=='pass','LABEL_ONLY_INTEGRATION_REVIEW_REQUIRED')
    io.base.verify_bindings(integrated['bindings'])
    deps.append(io.bind(integration_review))
    execute=types.FunctionType(original.main.__code__,{**vars(original),'scorer':scorer,
        'components':components,'__file__':__file__},name='uniform_replay_v4')
    execute()
    prior=io.R/'posthoc_uniform_scoring_v3/actual_execution_01/cells.json'
    before={(r['cohort'],r['cell_id']):r for r in io.read(prior)}
    after=io.read(args.out/'cells.json');comparisons=[];witnesses=[];flat=[];applied=[]
    stable=list(scorer.numeric.DIRECT)+['sr','sp','Com','Cor','s_method','s_trans','s_time']
    for row in after:
        old=before[row['cohort'],row['cell_id']]
        assert row['status']==old['status']
        if row.get('cancelled_no_raw'):
            assert row['posthoc_metrics']==old['posthoc_metrics'];continue
        assert row['raw_sha256']==old['raw_sha256']
        assert all(row['posthoc_metrics'][k]==old['posthoc_metrics'][k] for k in stable),(row['cell_id'],'NON_LABEL_CHANGE')
        diff={k:{'v3':old['posthoc_metrics'][k],'v4':row['posthoc_metrics'][k]}
            for k in original.METRICS if old['posthoc_metrics'][k]!=row['posthoc_metrics'][k]}
        comparisons.append({'cohort':row['cohort'],'cell_id':row['cell_id'],'changes':diff})
        processed=io.read(row['posthoc_record']['path'])
        relevant=processed['component_scoring_audit'] if processed['full_conversion_success'] else [c for c in processed['component_scoring_audit'] if 'label' in c['dependency_view_names']]
        assert len(relevant)<=1
        calculation=relevant[0] if relevant else None
        witness={'cohort':row['cohort'],'cell_id':row['cell_id'],'anonymous_answer_id':row['anonymous_answer_id'],
          'question_id':row['question_id'],'raw_sha256':row['raw_sha256'],'original_status':row['status'],
          'original_frozen_metrics':row['original_metrics'],'v3_metrics':old['posthoc_metrics'],'v4_metrics':row['posthoc_metrics'],
          'label_dependency_calculation_available':bool(relevant),'calculation':calculation,
          'label_view_failure':processed.get('views',{}).get('label',{}).get('error'),
          'posthoc_record':row['posthoc_record'],'unsupported_KB_values_not_filled':True}
        witnesses.append(witness)
        if calculation:
            for proposal in (calculation.get('source_binding_candidate') or {}).get('applied',[]):applied.append({'cohort':row['cohort'],'cell_id':row['cell_id'],**proposal})
        for channel in [*scorer.labels.CHANNELS,'s_label']:
            flat.append({'cohort':row['cohort'],'cell_id':row['cell_id'],'channel':channel,
              'calculation_available':calculation is not None,
              'value':(calculation['after']['channels'].get(channel) if channel!='s_label' else calculation['after']['s_label']) if calculation else None})
    io.base.verify_bindings(deps+[io.bind(prior)])
    io.save(args.out/'v3_comparison.json',{'all67_same_v4_configuration':True,'rows':comparisons,
      'changed_numeric_rows':[r for r in comparisons if r['changes']],
      'unchanged_numeric_rows':sum(not r['changes'] for r in comparisons),
      'stable_fields_all67':stable,'stable_fields_exactly_equal':True,'original_v3':io.bind(prior),'new_model_calls':0})
    io.save(args.out/'label_source_witnesses.json',witnesses)
    io.save(args.out/'source_binding_applications.json',applied)
    for cohort in dict.fromkeys(r['cohort'] for r in witnesses):io.save(args.out/'label_witnesses_by_batch'/f'{cohort}.json',[r for r in witnesses if r['cohort']==cohort])
    with (args.out/'label_channels.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    io.save(args.out/'implementation_addendum.json',{'status':'pass','additional_implementation_bindings':deps,
      'old_v3_snapshot_not_overwritten':True,'all67_label_views_audited':True,
      'label_view_unavailable_not_filled':True,'stable_fields_all67':stable,
      'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,
      'outputs':[io.bind(args.out/n) for n in ['summary.json','verification.json','v3_comparison.json','label_source_witnesses.json','source_binding_applications.json','label_channels.csv']]})
    print(json.dumps({'changed_numeric_rows':[r for r in comparisons if r['changes']],'applied_source_bindings':len(applied)}))
if __name__=='__main__':main()
