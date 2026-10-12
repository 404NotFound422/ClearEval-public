"""Exploratory formula-domain bounds, separate from the unchanged main CCE.

Known provisional scores are held fixed. Unknown normalized EGES components
range over [0,1]. These are algebraic outer bounds, not attainable biological
ranges, imputations, confidence intervals, or scientific validation.
"""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cce_round2_runner as runner
import cce_analysis as original

EGES=['s_method','s_label','s_trans','s_time']
OUT=runner.BASE/'partial_cce_domain_bounds_v1'

def bounds(row):
    m=row['metrics']
    result={'anonymous_answer_id':row['anonymous_answer_id'],'question_id':row['question_id'],
        'status':row['status'],'main_metrics_unchanged':{k:m[k] for k in ['Com','Cor','Eff','IA','HV']},
        'formal_eligible':False,'scope':'conditional_formula_domain_with_known_provisional_scores_held_fixed',
        'scientific_attainability_of_unknown_values':'not_established','confidence_interval':False,
        'imputation':False,'joint_main_question_set_changed':False}
    if row['status']!='success' or not all(original.finite(m[k]) and 0<=m[k]<=1 for k in ['Com','Cor']):
        return {**result,'bound_status':'not_computed_without_success_and_valid_Com_Cor','bounds':None}
    for key in EGES:
        if m[key] is not None and not original.valid_raw(key,m[key]):
            raise ValueError('OUT_OF_DOMAIN_NO_CLAMP:'+row['anonymous_answer_id']+':'+key)
    norm={k:(None if m[k] is None else m[k]/original.MAXIMA[k]) for k in EGES}
    if norm['s_method'] is not None:norm['s_method']=(norm['s_method']+1)/2
    known=math.fsum(v for v in norm.values() if v is not None)
    missing=[k for k,v in norm.items() if v is None]
    low=known/4;high=(known+len(missing))/4
    c,r=m['Com'],m['Cor']
    values={'Eff':[low,high],'IA':[min(c,r,low),min(c,r,high)],'HV':[c*r*low,c*r*high]}
    for key in values:
        if m[key] is not None and not all(math.isclose(v,m[key],abs_tol=1e-12,rel_tol=0) for v in values[key]):
            raise ValueError('COMPLETE_RESULT_MUST_COLLAPSE_TO_SAVED_VALUE:'+key)
    return {**result,'bound_status':'outer_bounds_only','known_normalized_components':norm,
        'unknown_components':missing,'bounds':values}

def main():
    source=runner.DEFAULT_OUT
    summary=runner.j.read(source/'completion_summary.json')
    runner.require(summary['actual_observations']==5 and summary['pending']==0,'WAIT_FOR_ALL_FIVE_TERMINAL')
    runner.validate(source)
    for row in runner.j.read(source/'matrix.json'):runner.terminal_identity(source,row)
    verification=runner.j.read(source/'analysis_verification.json')
    runner.require(verification['status']=='pass' and verification['all_five_terminal'],'VERIFIED_ORIGINAL_REPLAY_REQUIRED')
    runner.verify_bindings(verification['bindings'])
    runner.require(not OUT.exists(),'EXPLORATORY_OUTPUT_ALREADY_EXISTS')
    rows=[bounds(r) for r in runner.j.read(source/'per_answer.json')]
    inputs=[source/'per_answer.json',source/'completion_summary.json',source/'analysis_verification.json',
        Path(__file__),Path(original.__file__),ROOT/'results/oeq_metrics.py',ROOT/'evaluation_contract.py']
    report={'status':'exploratory_algebraic_diagnostic_not_primary_CCE','post_hoc':True,
        'known_scores_are_provisional_not_ground_truth':True,'source_applicability_still_unconfirmed':True,
        'fixed_answer_denominator':5,'new_model_requests':0,'new_judge_scores':0,'new_bootstrap_draws':0,
        'inputs':[runner.bind(p) for p in inputs],'rows':rows,
        'formula':'For k known normalized component sum K and m unknown components: Eff=[K/4,(K+m)/4]. IA and HV apply their original monotone formulas to these endpoints.',
        'not_a_ranking':'No cross-task dominance or model ranking is computed. Main NA values and Q* are unchanged.',
        'actual_command':[sys.executable,*sys.argv]}
    runner.j.save(OUT/'diagnostic.json',report)
    print(runner.j.canonical({'status':report['status'],'rows':len(rows),'new_model_requests':0}))

if __name__=='__main__':main()
