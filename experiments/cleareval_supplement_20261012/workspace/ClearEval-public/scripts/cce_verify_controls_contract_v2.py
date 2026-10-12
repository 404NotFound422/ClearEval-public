"""Read-only deterministic replay of the completed public E2 batch.

Rebuild EGES inputs from each newly returned extraction plus unchanged question
metadata/fixed demands, and invoke the original effectiveness function. This is
an execution-agent verification, not an independent expert or scientific audit.
No model transport is created and no prior score/reference/input is overwritten.
"""
from __future__ import annotations
import contextlib
import io
import math
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_controls_contract_v2 as batch
import cce_judges as j
import evaluator_integrity as integrity

OUT=batch.OUT


def equal(a,b):
    return a==b if a is None or b is None else math.isclose(a,b,rel_tol=0,abs_tol=1e-12)


def no_network(*args,**kwargs):
    raise RuntimeError('Deterministic E2 verification forbids network access')


def main():
    socket.create_connection=no_network
    before=batch.parent.request_count();batch.validate();batch.require_probes()
    plan=j.read(OUT/'plan.json');summary=j.read(OUT/'development_summary.json')
    cases={r['case_id']:r for r in j.read(OUT/'cases.json')['cases']}
    records={r['case_id']:r for r in j.read(OUT/'per_case.json')}
    pairs=j.read(OUT/'paired_results.json')
    trials=[j.read(p) for p in sorted((batch.RUN/'trials').glob('*.json'))]
    batch.check(len(trials)==len(cases)==len(records)==21,'verification_requires_completed_21_trial_batch')
    batch.check(len(pairs)==15 and summary['new_requests_this_batch']==21,'verification_requires_21_requests_15_pairs')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        runner,_,registry=j.runtime(batch.arguments())
    rows=[];inputs=[]
    for trial in trials:
        cid=trial['case_id'];case=cases[cid];record=records[cid];e=trial['evaluation']
        path=batch.RUN/'attempts'/f"{trial['trial_id']}_1"/'provider_response.json'
        provider=j.read(path);inputs.extend([batch.bind(path),batch.bind(batch.RUN/'trials'/f"{trial['trial_id']}.json")])
        row={'case_id':cid,'question_id':case['question_id'],'condition':case['condition'],
             'trial_id':trial['trial_id'],'trial_status':trial['status'],'provider_response':batch.bind(path)}
        if trial['status']!='success':
            raw=j.proposals(e)
            batch.check(all(v is None for v in raw.values()),'invalid_trial_gained_numeric_judge_proposals')
            batch.check(not record['technical_pipeline_complete'],'invalid_trial_promoted')
            row.update(status='invalid_trial_retained_without_EGES_repair',failure_stage=e.get('failure_stage'),
                       eges_recomputed=False,raw_failure_retained=True)
            rows.append(row);continue
        parsed=integrity.parse_judge_object(provider['response'])
        batch.parent.core_gate(parsed)
        extraction=parsed['extraction']
        batch.check(extraction==e['extraction'],'raw_extraction_modified')
        batch.check(parsed['scores']==e['legacy_diagnostics']['raw_teacher_scores'],'raw_direct_scores_modified')
        pref=registry.get(case['question_id'],case['specific_question'])
        snapshot_qid=registry.questions[str(case['question_id'])]['question_id']
        meta=runner.QUESTION_META_KB[snapshot_qid]
        quantitative={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),
                      'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
        for name in ['reagent_ri_value','protocol_time_hours','method_stages']:
            if name in extraction:quantitative[name]=extraction[name]
        targets=meta.get('marker_query_targets') or []
        batch.check(quantitative==e['quantitative_data'],'EGES_quantitative_inputs_not_rebuilt_exactly')
        batch.check(pref==e['user_preference_vector'],'fixed_demand_input_drift')
        calculated=runner.calculate_effectiveness_score(quantitative,pref,runner.MODEL_SPACE_SIGNED,
                                                       extraction['marker_dict'],targets)
        block=e['legacy_diagnostics']['scores']['effectiveness']
        for metric in ['s_method','s_label','s_trans','s_time']:
            batch.check(equal(calculated[metric],block[metric]['score']),'EGES_replay_mismatch:'+cid+':'+metric)
            batch.check(equal(calculated[metric],record['candidate_raw_and_derived'][metric]),'summary_EGES_mismatch')
        batch.check(calculated['time_computation']==block['s_time']['computation'],'time_trace_replay_mismatch')
        batch.check(calculated['marker_coverage_audit']==block['s_label']['coverage_audit'],'coverage_trace_replay_mismatch')
        batch.check(calculated['compatibility_audit']==e['legacy_diagnostics']['compatibility_audit'],'KB_trace_replay_mismatch')
        components=[(calculated['s_method']/2.5+1)/2 if calculated['s_method'] is not None else None,
                    calculated['s_label']/6 if calculated['s_label'] is not None else None,
                    calculated['s_trans']/3 if calculated['s_trans'] is not None else None,
                    calculated['s_time']/3 if calculated['s_time'] is not None else None]
        eff=sum(components)/4 if all(v is not None for v in components) else None
        batch.check(equal(eff,record['candidate_raw_and_derived']['Eff']),'Eff_normalization_mismatch')
        row.update(status='pass',eges_recomputed=True,raw_extraction_unmodified=True,
            raw_direct_judge_scores_unmodified=True,quantitative_input_sha256=j.digest(quantitative),
            fixed_demand_sha256=j.digest(pref),marker_dict_sha256=j.digest(extraction['marker_dict']),
            target_metadata_sha256=j.digest(targets),
            recalculated={k:calculated[k] for k in ['s_method','s_label','s_trans','s_time']}|{'Eff':eff},
            full_compatibility_and_time_audit_equal=True)
        rows.append(row)
    pair_checks=[]
    for pair in pairs:
        a,b=(records[pair[s+'_case_id']] for s in ['baseline','variant'])
        complete=pair['same_frozen_configuration'] and a['technical_pipeline_complete'] and b['technical_pipeline_complete']
        for metric in batch.METRICS:
            av,bv=a['candidate_raw_and_derived'][metric],b['candidate_raw_and_derived'][metric]
            expected=bv-av if complete and batch.finite(av) and batch.finite(bv) else None
            batch.check(equal(pair['delta_'+metric],expected),'pair_delta_mismatch:'+pair['pair_id']+':'+metric)
        pair_checks.append({'pair_id':pair['pair_id'],'same_configuration':pair['same_frozen_configuration'],
            'technical_pipeline_complete':complete,'numeric_CCE_complete':pair['complete_numeric_pair'],
            'all_16_metric_deltas_verified':True,'invalid_dependencies_remain_NA':True})
    batch.check(batch.parent.request_count()==before,'verification_made_model_request')
    receipt={'status':'pass','created_utc':j.now(),'verification_kind':'execution_agent_deterministic_recomputation',
        'independent_expert_review':False,'expert_returns':0,'formal_eligible':False,
        'actual_trials':len(trials),'eges_recomputed_trials':sum(r['eges_recomputed'] for r in rows),
        'invalid_trials_retained':sum(not r['eges_recomputed'] for r in rows),'pair_count':len(pair_checks),
        'all_EGES_values_and_traces_exactly_reproduced':True,'new_judge_requests':0,
        'plan':batch.bind(OUT/'plan.json'),'root_review':batch.bind(OUT/'root_review_record.json'),
        'development_summary':batch.bind(OUT/'development_summary.json'),
        'script':batch.bind(__file__),'scoring_source':batch.bind(ROOT/'OEQ_run_grading_new.py'),
        'new_full_text_extraction_trials':rows,'pair_checks':pair_checks,'input_bindings':inputs,
        'actual_command':[sys.executable,'scripts/cce_verify_controls_contract_v2.py'],
        'limitation':'Reproducibility of unchanged EGES arithmetic on new extracted values, not correctness of extraction, biological applicability, or expert agreement.'}
    j.save(OUT/'eges_recomputation_verification.json',receipt)
    batch.validate()
    print(j.canonical({k:receipt[k] for k in ['status','actual_trials','eges_recomputed_trials','invalid_trials_retained','pair_count','new_judge_requests']}))


if __name__=='__main__':main()
