"""Small software/identity checks. Fixtures below are not scientific observations."""
from pathlib import Path
import hashlib
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import OUT,ROOT,read,write,digest,filehash,score_steps,Encoder
from cce_judges import digest as judge_digest

def main():
    def ref(identity,route):
        return {'reference_id':identity,'route_id':route,'route_aliases':[route],'question_ids':[1],
            'steps':[{'text':'Fixture operation'}],'status':'software_fixture','source_path':'fixture','family_id':'fixture'}
    refs=[ref('a1','ROUTE_A'),ref('a2','ROUTE_A'),ref('a3','ROUTE_A'),ref('b1','ROUTE_B')]
    scores={'a1':(.5,.4),'a2':(.5,.8),'a3':(.5,.8),'b1':(1.,1.)}
    class FakeEncoder:
        def score(self,r,steps,threshold):
            a,b=scores[r['reference_id']];return {'sr':a,'sp':b}
    a={'question_id':1,'model_response':'**Chosen Method:** ROUTE_A\n**Protocol Steps:**\n1.1 Fixture operation.'}
    chosen=score_steps(a,refs,FakeEncoder())
    assert chosen['reference_id']=='a2' and chosen['sr']==.5 and chosen['sp']==.8
    assert chosen['candidate_reference_ids']==['a1','a2','a3']
    unknown=score_steps({**a,'model_response':a['model_response'].replace('ROUTE_A','UNKNOWN_ROUTE')},refs,FakeEncoder())
    assert unknown['sr'] is None and unknown['sp'] is None
    zero=Encoder.score(None,refs[0],[],.7)
    assert zero['sr']==zero['sp']==0
    hashes=[];verified=0
    settings=[('pilot',.7),('pilot_t060',.6),('pilot_t080',.8),('two_source_t070',.7),('two_source_t060',.6),('two_source_t080',.8)]
    settings += [('supplement_v2_t070',.7),('supplement_v2_t060',.6),('supplement_v2_t080',.8)]
    for tag,threshold in settings:
        cfg=read(OUT/(tag+'_resolved_config.json'));h=digest(cfg);hashes.append(h)
        assert cfg['resolved']['adapter_sha256']==filehash(ROOT/'scripts/cce_validation.py')
        assert cfg['run_setting']['actual_threshold']==threshold
        assert cfg['resolved']['reference_digest']==digest(read(OUT/(tag+'_references.json'))['references'])
        if tag.startswith('two_source'):
            assert cfg['run_setting']['batch_driver_sha256']==filehash(ROOT/'scripts/cce_score_reference_expansion.py')
        if tag.startswith('supplement_v2'):
            assert cfg['run_setting']['batch_driver_sha256']==filehash(ROOT/'scripts/cce_score_supplement_references.py')
            for path, expected in cfg['run_setting']['batch_input_sha256'].items():
                assert filehash(Path(path))==expected
        for row in read(OUT/(tag+'_per_answer.json')):
            assert row['config_hash']==h and row['threshold']==threshold
            assert row['formal_eligible'] is False
            verified+=1
    assert len(set(hashes))==len(settings)
    pairs=read(OUT/'controls/full_pipeline_pairs.json')
    assert len(pairs)==9 and all(p['full_pipeline_complete'] and p['different_answer_text'] for p in pairs)
    order_pairs=read(OUT/'judges/local_order_conflicts/paired_order_results.json')
    order_cases={c['case_id']:c for c in read(OUT/'controls/order_conflict_cases.json')['cases']}
    order_trials={t['trial_id']:t for t in [read(p) for p in (OUT/'judges/local_order_conflicts/trials').glob('*.json')]}
    assert len(order_pairs)==3 and len(order_trials)==6
    for pair in order_pairs:
        baseline=order_trials[pair['baseline_trial_id']]
        variant=order_trials[pair['variant_trial_id']]
        assert baseline['pipeline_config_sha256']==variant['pipeline_config_sha256']
        assert baseline['references_sha256']==variant['references_sha256']
        assert baseline['full_text_input_sha256']!=variant['full_text_input_sha256']
        for trial in [baseline,variant]:
            case=order_cases[trial['case_id']]
            expected=judge_digest({'question':case['specific_question'],'question_id':case['question_id'],
                'protocol':case['model_response'],'references':case.get('references')})
            assert expected==trial['full_text_input_sha256']
            assert trial['status']=='success' and trial['actual_api_request_made']
            assert trial['full_text_submitted_for_reextraction'] and trial['new_extraction_available']
    e4=read(OUT/'judges/local_stability/cce_stability_summary.json')
    assert e4['observations']==12 and e4['independent_answers']==2 and e4['explicit_route_mismatches']==6
    granularity_pairs=read(OUT/'judges/local_granularity/paired_results.json')
    granularity_cases={c['case_id']:c for c in read(OUT/'controls/granularity_cases.json')['cases']}
    granularity_trials={t['trial_id']:t for t in [read(p) for p in (OUT/'judges/local_granularity/trials').glob('*.json')]}
    assert len(granularity_pairs)==3 and len(granularity_trials)==6
    for pair in granularity_pairs:
        assert pair['baseline_reused'] and pair['operation_sequence_and_parameters_verbatim_preserved']
        assert pair['same_judge_configuration'] and pair['same_step_configuration'] and pair['same_references']
        baseline=granularity_trials[pair['baseline_trial_id']]
        variant=granularity_trials[pair['variant_trial_id']]
        assert baseline==order_trials[pair['baseline_trial_id']]
        assert baseline['pipeline_config_sha256']==variant['pipeline_config_sha256']
        assert baseline['references_sha256']==variant['references_sha256']
        for trial in [baseline,variant]:
            case=granularity_cases[trial['case_id']]
            assert trial['full_text_input_sha256']==judge_digest({'question':case['specific_question'],
                'question_id':case['question_id'],'protocol':case['model_response'],'references':case.get('references')})
            assert trial['status']=='success' and trial['new_extraction_available']
    waiting=read(OUT/'controls/alternative_route_waiting_matrix.json')
    assert waiting['candidate_pairs']==6 and waiting['completed_pairs']==waiting['confirmed_eligible_pairs']==0
    ledger=[json.loads(x) for x in (OUT/'judges/request_ledger.jsonl').read_text(encoding='utf-8').splitlines() if x]
    request_n=len(ledger)
    assert request_n==len({r['request_id'] for r in ledger}) and 33<=request_n<=300
    assert sorted(r['package_request_index'] for r in ledger)==list(range(1,request_n+1))
    figures=list((OUT/'figures').glob('*.png'))
    for png in figures:
        assert all(png.with_suffix(ext).exists() for ext in ['.svg','.pdf','.csv'])
    write(OUT/'final_software_verification.json',{'scope':'software_fixture_and_artifact_identity_not_scientific_validation','route_filter_and_tie_break':'pass','empty_answer_zero':'pass','unknown_route_na':'pass','threshold_identity_rows_verified':verified,'initial_full_pipeline_pairs_verified':len(pairs),'canonical_order_full_pipeline_pairs_verified':len(order_pairs),'granularity_full_pipeline_pairs_verified':len(granularity_pairs),'full_pipeline_pairs_verified':len(pairs)+len(order_pairs)+len(granularity_pairs),'stability_observations':e4['observations'],'request_ledger_unique_attempts':request_n,'figure_sets_verified':len(figures),'status':'pass'})
    print(f'Software and artifact identity verification passed; {verified} score rows, 15 first-version full-text pairs, {request_n} unique requests.')

if __name__=='__main__':main()
