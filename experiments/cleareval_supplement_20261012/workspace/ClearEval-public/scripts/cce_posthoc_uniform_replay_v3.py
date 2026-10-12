"""Uniform 67-return v3 replay with explicit source/target zero witnesses."""
import argparse,collections,csv,json,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_posthoc_uniform_replay_v1 as original
import cce_posthoc_components_v3 as components
import cce_posthoc_scoring_v3 as scorer
io=original.io

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    deps=[io.bind(x) for x in [__file__,original.__file__,components.__file__,scorer.__file__,
        scorer.previous.__file__,scorer.boundary.__file__,scorer.boundary.concentration.__file__,
        scorer.boundary.syntax.__file__,scorer.boundary.attached.__file__,
        scorer.time_scope.__file__,scorer.time_scope.scope.__file__,scorer.time_scope.phase_scope.__file__,
        scorer.time_scope.wash_scope.__file__,
        scorer.target_scope.__file__,scorer.labels.__file__]]
    execute=types.FunctionType(original.main.__code__,{**vars(original),'scorer':scorer,
        'components':components,'__file__':__file__},name='uniform_replay_v3')
    execute()
    prior=io.R/'posthoc_uniform_scoring_v2/actual_execution_01/cells.json'
    before={(r['cohort'],r['cell_id']):r for r in io.read(prior)}
    after=io.read(args.out/'cells.json');comparisons=[];witnesses=[];flat=[]
    for row in after:
        old=before[row['cohort'],row['cell_id']]
        assert row['status']==old['status']
        if row.get('cancelled_no_raw'):continue
        assert row['raw_sha256']==old['raw_sha256']
        diff={k:{'v2':old['posthoc_metrics'][k],'v3':row['posthoc_metrics'][k]}
            for k in original.METRICS if old['posthoc_metrics'][k]!=row['posthoc_metrics'][k]}
        comparisons.append({'cohort':row['cohort'],'cell_id':row['cell_id'],'changes':diff})
        processed=io.read(row['posthoc_record']['path'])
        if processed['full_conversion_success']:
            relevant=processed['component_scoring_audit']
            assert len(relevant)==1
        else:
            relevant=[c for c in processed['component_scoring_audit'] if 'label' in c['dependency_view_names']]
        assert len(relevant)<=1
        witness={'cohort':row['cohort'],'cell_id':row['cell_id'],'anonymous_answer_id':row['anonymous_answer_id'],
          'question_id':row['question_id'],'raw_sha256':row['raw_sha256'],
          'original_frozen_metrics':row['original_metrics'],'v2_metrics':old['posthoc_metrics'],'v3_metrics':row['posthoc_metrics'],
          'label_dependency_calculation_available':bool(relevant),
          'label_view_failure':processed.get('views',{}).get('label',{}).get('error'),
          'original_status':row['status'],'calculation':relevant[0] if relevant else None,
          'posthoc_record':row['posthoc_record'],'unsupported_values_not_filled':True}
        witnesses.append(witness)
        calculation=witness['calculation']
        for channel in [*scorer.labels.CHANNELS,'s_label']:
            v=lambda part: calculation[part]['channels'].get(channel) if channel!='s_label' else calculation[part]['s_label']
            flat.append({'cohort':row['cohort'],'cell_id':row['cell_id'],'channel':channel,
              'calculation_available':calculation is not None,
              'before_target_fix':v('before') if calculation else None,
              'after_target_fix':v('after') if calculation else None,
              'known_zero_removed':bool(calculation and v('before')==0 and v('after') is None)})
    io.base.verify_bindings(deps+[io.bind(prior)])
    io.save(args.out/'v2_comparison.json',{'all67_same_v3_configuration':True,
      'rows':comparisons,'changed_numeric_rows':[r for r in comparisons if r['changes']],
      'unchanged_numeric_rows':sum(not r['changes'] for r in comparisons),'original_v2':io.bind(prior),'new_model_calls':0})
    io.save(args.out/'label_source_witnesses.json',witnesses)
    for cohort in dict.fromkeys(r['cohort'] for r in witnesses):
        io.save(args.out/'label_witnesses_by_batch'/f'{cohort}.json',[r for r in witnesses if r['cohort']==cohort])
    with (args.out/'label_channels.csv').open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    io.save(args.out/'implementation_addendum.json',{'status':'pass','additional_implementation_bindings':deps,
      'unchanged_uniform_input_procedure_reused':True,'old_v2_snapshot_not_overwritten':True,
      'all67_label_views_audited':True,'label_view_unavailable_not_filled':True,
      'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,
      'outputs':[io.bind(args.out/n) for n in ['summary.json','verification.json','v2_comparison.json','label_source_witnesses.json','label_channels.csv']]})
    print(json.dumps({'changed_numeric_rows':[r for r in comparisons if r['changes']],
      'known_zero_to_NA_channel_rows':sum(x['known_zero_removed'] for x in flat)}))
if __name__=='__main__':main()
