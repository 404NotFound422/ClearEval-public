"""Read-only seven-answer historical/current availability trace. No rescoring."""
import ast
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
BATCH=R2/'generation_confirmation_v2'
OUT=R2/'first7_historical_availability_audit_v1'
DIAG=R2/'confirmation_source_diagnostic_v1/generation_confirmation_v2/2026-10-10T112407.927071_0000'
STEPS=ROOT/'artifacts/cce_validation/method_family_steps_v1/t070_per_answer.csv'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rawsha(t):return hashlib.sha256(t.encode('utf8')).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def oldnum(s):return None if s in ('','None','null') else float(s)

def main():
    if OUT.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    matrix=read(BATCH/'matrix.json'); assert [r['anonymous_answer_id'] for r in matrix]==['FPC%02d'%i for i in range(2,9)]
    cases={r['anonymous_answer_id']:r for r in read(BATCH/'cases.json')['cases']}
    with STEPS.open(encoding='utf-8-sig',newline='')as f:steps=list(csv.DictReader(f))
    finds={r['answer_id']:r for r in read(DIAG/'source_interpretation_v1/source_findings.json')['answers']}
    timefile=ROOT/'dataset/Q+AR/model_response/clearing_time_stats.json';time_stats=read(timefile)
    rows=[];bindings=[bind(p)for p in [Path(__file__),STEPS,BATCH/'matrix.json',BATCH/'cases.json',BATCH/'expected_contract.json',BATCH/'plan.json',timefile,DIAG/'source_interpretation_v1/source_findings.json']]
    for cell in matrix:
        aid=cell['anonymous_answer_id'];case=cases[aid];step=cell['step']
        old=[r for r in steps if r['answer_sha256']==step['answer_sha256'] and r['question_sha256']==step['question_sha256']];assert len(old)==1;old=old[0]
        assert rawsha(case['model_response'])==step['answer_sha256'] and rawsha(case['specific_question'])==step['question_sha256']
        archive_path=Path(old['answer_source']);archive=read(archive_path)
        answers=[(i,r)for i,r in enumerate(archive)if r['question_id']==case['question_id']];assert len(answers)==1
        answer_index,answer=answers[0];assert answer['specific_question']==case['specific_question'] and answer['model_response']==case['model_response']
        score_path=Path(old['score_source']);scores=read(score_path)
        scored=[(i,r)for i,r in enumerate(scores)if r['question_id']==case['question_id']];assert len(scored)==1
        score_index,score=scored[0];ev=score['evaluation'];assert ev['meta_data']['sample_info']==case['specific_question']
        es=ev['scores']['effectiveness']; time_reason=es['s_time']['reasoning'];old_hours=float(re.search(r'Act:\s*([\d.]+)',time_reason).group(1))
        marker_reason=es['s_label']['reasoning'];marker=ast.literal_eval(marker_reason.split('marker_dict=',1)[1])
        tid=cell['planned_trial_id'];tp=BATCH/'run/trials'/(tid+'.json');at=BATCH/'run/attempts'/(tid+'_1')
        trial=read(tp);component=read(at/'component_result.json');doc=read(Path(cell['assets']['source_document']['path']))
        assert doc['text']==case['model_response'] and trial['identity']==cell['identity']
        assert trial['metrics']==component['metrics'] and all(trial['metrics'][k]==step[k]for k in ['sr','sp'])
        rawpath=at/'raw_response.txt';assert rawsha(rawpath.read_bytes().decode('utf8'))==component['raw_sha256']
        diagpath=DIAG/(aid+'_diagnostic.json');diag=read(diagpath);assert diag['original_metrics']==trial['metrics']
        cv=component.get('conversion');find=finds[aid];assert find['original_metrics']==trial['metrics']
        time=diag['time_diagnostic']['time_calculation']
        old_metrics={k:oldnum(old[k])for k in ['sr','sp','c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','Com','Cor','Eff','IA','HV','historical_Com']}
        assert all(old_metrics[k]==es[k]['score'] for k in ['s_method','s_label','s_trans','s_time'])
        lp=cv.get('label_occurrence_projection')if cv else None
        label=None if lp is None else {'original_legacy_dictionary_view':lp['original_marker_dict'],
            'supported_local_dictionary_view':lp['supported_local_dictionary_view'],
            'explicit_label_uncertainties':lp['explicit_label_uncertainties'],
            'pairs':[{k:p.get(k)for k in ['pair_id','kind','fluor_literal','marker_literal','raw_relation_status','original_local_gate_allowed','scope']}for p in lp['pairs']],
            'channels':component['numeric']['occurrence_label_calculation']['channels'],
            'zero_witnesses':component['numeric']['occurrence_label_calculation']['zero_witnesses']}
        r={'anonymous_answer_id':aid,'answer_id':old['answer_id'],'generator':old['model'],'question_id':case['question_id'],
            'answer_sha256':step['answer_sha256'],'question_sha256':step['question_sha256'],
            'exact_current_and_original_archive_question_answer_equal':True,
            'historical_score_link':'same file/model/qid/exact stem; score file has no answer hash or source-span extraction',
            'historical_evaluator_identity':'not recorded in these old evaluation records; not inferred from generator name',
            'historical_raw_extraction_available':False,'historical_evaluation_top_fields':list(ev),
            'original_answer_record_index':answer_index,'original_score_record_index':score_index,
            'historical_metrics_with_same_SR_SP':old_metrics,'historical_complete_CCE':all(finite(old_metrics[k])for k in ['Com','Cor','Eff','IA','HV']),
            'historical_effectiveness_saved_reasoning':{k:{'score':es[k]['score'],'reasoning':es[k]['reasoning']}for k in ['s_method','s_label','s_trans','s_time']},
            'historical_input_from_saved_reasoning':{'method_name':ev['meta_data']['target_method'],'time_hours':old_hours,'marker_dict':marker,
                'source_support':'No per-operation or per-relation source trace retained; numeric availability is not evidence of supported extraction'},
            'separate_clearing_time_stats_hours':time_stats[old['model']][str(case['question_id'])],
            'separate_stats_equal_saved_EGES_input':time_stats[old['model']][str(case['question_id'])]==old_hours,
            'current_status':trial['status'],'current_metrics':trial['metrics'],'current_complete_CCE':all(finite(trial['metrics'][k])for k in ['Com','Cor','Eff','IA','HV']),
            'current_time':{k:time.get(k)for k in ['total_hours','candidate_bounds_hours','issues','known_operation_contributions','initial_plus_at_most_one_conditional_execution_envelope_hours','scientific_total_confirmed']},
            'current_numeric_method_input':component.get('numeric',{}).get('quantitative_data',{}).get('method_name') if cv else component['views']['method'].get('projected_extraction',{}).get('method_name'),
            'current_label':label,'current_partial_label_error':component.get('views',{}).get('label',{}).get('error'),
            'current_duplicate_ids':component.get('duplicate_ids'),
            'current_diagnostic_categories':find['categories'],'current_source_conclusion_zh':find['conclusion_zh'],
            'scope_note':'Current bounds are preserved diagnostics conditional on phase/schedule labels, not independently validated actual hours.',
            'source_chain':[bind(p)for p in [archive_path,score_path,STEPS,tp,at/'request_receipt.json',at/'component_result.json',rawpath,Path(cell['assets']['source_document']['path']),diagpath]],
            'pointers':{'legacy':f'/{score_index}/evaluation/scores/effectiveness','current':'/metrics','source_diagnostic':'/time_diagnostic/time_calculation'}}
        rows.append(r);bindings.extend(r['source_chain'])
    OUT.mkdir();write(OUT/'per_answer.json',rows)
    compact=[]
    for r in rows:
        compact.append({'anonymous_answer_id':r['anonymous_answer_id'],'answer_id':r['answer_id'],'question_id':r['question_id'],
            'old_time_hours':r['historical_input_from_saved_reasoning']['time_hours'],'old_s_time':r['historical_metrics_with_same_SR_SP']['s_time'],
            'new_s_time':r['current_metrics']['s_time'],'candidate_bounds_not_gold':json.dumps(r['current_time']['candidate_bounds_hours']),
            'old_s_label':r['historical_metrics_with_same_SR_SP']['s_label'],'new_s_label':r['current_metrics']['s_label'],
            'old_Com':r['historical_metrics_with_same_SR_SP']['Com'],'new_Com':r['current_metrics']['Com'],
            'old_Cor':r['historical_metrics_with_same_SR_SP']['Cor'],'new_Cor':r['current_metrics']['Cor'],
            'old_Eff':r['historical_metrics_with_same_SR_SP']['Eff'],'new_Eff':r['current_metrics']['Eff'],
            'historical_complete':r['historical_complete_CCE'],'current_complete':r['current_complete_CCE'],
            'source_reasons':';'.join(r['current_diagnostic_categories'])})
    with (OUT/'per_answer.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
    summary={'status':'completed_readonly_seven_answer_trace','answers':7,'historical_CCE_finite':sum(r['historical_complete_CCE']for r in rows),'frozen_fw3_CCE_finite':sum(r['current_complete_CCE']for r in rows),
        'current_component_coverage':{k:sum(finite(r['current_metrics'][k])for r in rows)for k in rows[0]['current_metrics']},
        'old_separate_time_stats_match_n':sum(r['separate_stats_equal_saved_EGES_input']for r in rows),
        'same_answer_question_join_verified':7,'historical_score_answer_hash_present':0,'new_scoring_calls':0,'new_model_calls':0,
        'not_single_factor_causal_comparison':True,'posthoc_fixes_not_substituted_for_frozen_comparison':True,
        'bindings':list({x['path']:x for x in bindings}.values()),'actual_command':[sys.executable,*sys.argv]}
    write(OUT/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items()if k!='bindings'},ensure_ascii=True))

if __name__=='__main__':main()
