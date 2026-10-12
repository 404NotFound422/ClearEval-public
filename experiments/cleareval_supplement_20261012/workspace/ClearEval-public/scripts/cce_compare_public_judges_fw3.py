"""Descriptive comparison of existing public-five fw3 values; no rescoring."""
from __future__ import annotations
import argparse, csv, hashlib, json, math, statistics, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
Q=R2/'fieldwise_scoring_v3/actual_execution_01'
C=R2/'codex_fieldwise_replay_v3/2026-10-10T110127.772156_0000'
OUT=R2/'e4_cross_source_fw3_v1'
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']
AGG=['Com','Cor','Eff','IA','HV']
METRICS=DIRECT+EGES+['sr','sp']+AGG
CATEGORIES={'direct_primary':DIRECT,'EGES_derived_components':EGES,'aggregate_derived':AGG}
TOL=1e-12
BINDINGS={}

def binding(p):
    p=Path(p).resolve(); return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def retain(p):
    b=binding(p);BINDINGS[b['path']]=b;return b
def load(p):
    retain(p);return json.loads(Path(p).read_text(encoding='utf8'))
def verify(bs):
    for b in bs:
        assert binding(b['path'])=={'path':str(Path(b['path']).resolve()),'sha256':b['sha256']},b['path']
        BINDINGS[str(Path(b['path']).resolve())]={'path':str(Path(b['path']).resolve()),'sha256':b['sha256']}
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def csvsave(p,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else ('NA' if v is None else v) for k,v in row.items()})
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def stats(values):
    ok=[v for v in values if finite(v)];n=len(ok)
    return {'planned_n':len(values),'finite_n':n,'na_n':len(values)-n,'values':values,
        'mean_all_finite':statistics.mean(ok) if n else None,
        'range':max(ok)-min(ok) if n>=2 else None,
        'sample_sd':statistics.stdev(ok) if n>=2 else None,
        'range_evaluable':n>=2,'nonzero_range':max(ok)-min(ok)>TOL if n>=2 else None,
        'all_planned_finite':n==len(values)}
def raw_record(scores,metric):return scores['completeness' if metric=='c_param' else 'correctness'][metric]

def evidence(row,cv,wire,raw_path,raw_hash):
    scores=[]
    for m in DIRECT:
        r=raw_record(wire['scores'],m)
        assert r['score']==row['metrics'][m],(row['cell_id'],m,'raw-to-retained mismatch')
        scores.append({'source':row['source'],'answer_id':row['answer_id'],'cell_id':row['cell_id'],
            'repeat':row['repeat'],'metric':m,'raw_score':r['score'],'retained_score':row['metrics'][m],
            'raw_reasoning':r.get('reasoning'),'raw_path':raw_path,'raw_sha256':raw_hash,
            'json_pointer':'/scores/'+('completeness' if m=='c_param' else 'correctness')+'/'+m})
    time=cv['legacy_projection']['time_calculation']
    ops=cv['source_audit']['resolved']['operations']
    inventory=cv['source_audit']['inventory']
    unresolved=[r for r in inventory if (r['kind']=='duration' and r.get('coverage_state') not in ['covered','classified'])
        or r.get('coverage_state','').startswith('uncovered')]
    return scores,{'source':row['source'],'answer_id':row['answer_id'],'cell_id':row['cell_id'],'repeat':row['repeat'],
        'total_hours':time['total_hours'],'s_time':row['metrics']['s_time'],'issues':time['issues'],
        'candidate_bounds_hours':time.get('candidate_bounds_hours'),
        'initial_scope_candidate_bounds_hours':time.get('initial_scope_candidate_bounds_hours'),
        'known_operation_contributions':time.get('known_operation_contributions'),
        'coverage_scopes':time.get('coverage_scopes'),'time_calculation':time,
        'raw_coverage':wire['grounded_extraction'].get('coverage'),
        'resolved_coverage':cv['source_audit']['resolved']['coverage'],
        'operations':ops,'unresolved_inventory':unresolved,
        'source_binding':cv['source_audit']['source_binding'],'raw_path':raw_path,'raw_sha256':raw_hash}

def analyze(out):
    assert not out.exists(),out;out.mkdir(parents=True)
    qsummary=load(Q/'summary.json');assert qsummary['all_40_by_16_old_metrics_exactly_unchanged'] is True
    verify(qsummary['implementation']+qsummary['input_bindings'])
    csummary=load(C/'summary.json');cverify=load(C/'verification.json')
    assert csummary['planned_slots']==csummary['terminal_at_start']==12 and csummary['pending']==0
    assert cverify['status']=='pass_readonly_source_chain' and cverify['all_12_slots_retained'] is True
    verify(cverify['dependencies']+cverify['input_bindings'])
    observations=[];direct=[];times=[]
    oldcancel=load(R2/'grounded_stability_qwen_only_analysis_v1/actual_01/observations.json')
    for x in load(Q/'cells.json'):
        if x['cohort']!='Qwen_repeats':continue
        metrics=x.get('after_metrics')
        if metrics is None:
            a=next(a for a in oldcancel if a['trial_id']==x['trial_id'])
            metrics={m:a[m] for m in METRICS}
            assert x['status']=='user_cancelled_no_retry' and all(metrics[m] is None for m in DIRECT+EGES+AGG)
        row={'source':'Qwen','answer_id':x['anonymous_answer_id'],'cell_id':x['cell_id'],
            'repeat':int(x['cell_id'].rsplit('__r',1)[1]),'original_status':x['status'],'metrics':metrics}
        observations.append(row)
        if x['status']=='user_cancelled_no_retry':continue
        cvp=Q/'cells/Qwen_repeats'/x['cell_id']/'conversion.json'; cv=load(cvp)
        num=load(cvp.with_name('numeric_result.json'));assert num['metrics']==metrics
        scores,time=evidence(row,cv,cv['wire_payload'],str(cvp),cv['raw_response_sha256'])
        direct+=scores;times.append(time)
    assert len(observations)==15 and sum(r['original_status']=='success' for r in observations)==14
    for x in load(C/'observations.json'):
        row={'source':'Codex','answer_id':x['anonymous_answer_id'],'cell_id':x['cell_id'],'repeat':x['repeat_index'],
            'original_status':x['original_status'],'processing_status':x['processing_status'],'metrics':x['metrics']}
        observations.append(row);verify([x['per_cell']]);p=load(x['per_cell']['path'])
        rawp=next(Path(b['path']) for b in p['source_bindings'] if Path(b['path']).name=='raw_response.txt')
        retain(rawp); raw=rawp.read_bytes().decode('utf8');assert hashlib.sha256(raw.encode('utf8')).hexdigest()==x['raw_sha256']
        wire=json.loads(raw)
        cv=p.get('conversion')
        if cv is None:
            assert x['cell_id']=='A01__codex_unobserved__r1' and x['original_status']=='failed'
            cv=load(Q/'codex_time_view/conversion.json')
            check=load(Q/'codex_time_view/record.json')
            assert check['raw_sha256']==x['raw_sha256'] and check['after_s_time']==x['metrics']['s_time']
        scores,time=evidence(row,cv,wire,str(rawp),x['raw_sha256'])
        direct+=scores;times.append(time)
    for aid in ['A01','A02','A03','A04','A05']:
        q=[x for x in observations if x['source']=='Qwen' and x['answer_id']==aid]
        c=[x for x in observations if x['source']=='Codex' and x['answer_id']==aid]
        assert len(q)==3 and len(c)==(3 if aid in ['A01','A02'] else 2)
        assert len({json.dumps(t['source_binding'],sort_keys=True) for t in times if t['answer_id']==aid})==1
        for m in ['sr','sp']:assert len({x['metrics'][m] for x in q+c})==1
    observations.sort(key=lambda r:(r['source'],r['answer_id'],r['repeat']))
    within=[];cross=[]
    for source in ['Qwen','Codex']:
        for aid in ['A01','A02','A03','A04','A05']:
            rows=[x for x in observations if x['source']==source and x['answer_id']==aid]
            for category,metrics in CATEGORIES.items():
                for metric in metrics:within.append({'source':source,'answer_id':aid,'category':category,'metric':metric,
                    **stats([r['metrics'][metric] for r in rows])})
    for aid in ['A01','A02','A03','A04','A05']:
        for category,metrics in CATEGORIES.items():
            for metric in metrics:
                q=next(r for r in within if r['source']=='Qwen' and r['answer_id']==aid and r['metric']==metric)
                c=next(r for r in within if r['source']=='Codex' and r['answer_id']==aid and r['metric']==metric)
                delta=c['mean_all_finite']-q['mean_all_finite'] if q['finite_n'] and c['finite_n'] else None
                cross.append({'answer_id':aid,'category':category,'metric':metric,
                    'Qwen_planned':q['planned_n'],'Qwen_finite':q['finite_n'],'Qwen_values':q['values'],'Qwen_mean':q['mean_all_finite'],
                    'Codex_planned':c['planned_n'],'Codex_finite':c['finite_n'],'Codex_values':c['values'],'Codex_mean':c['mean_all_finite'],
                    'Codex_minus_Qwen':delta,'absolute_difference':abs(delta) if delta is not None else None,
                    'direction':None if delta is None else ('Codex_higher' if delta>TOL else 'Codex_lower' if delta<-TOL else 'equal_within_tolerance'),
                    'both_at_least_two_finite':q['finite_n']>=2 and c['finite_n']>=2})
    summary={'status':'completed_descriptive_comparison_not_scientific_validation','planned':{'Qwen':15,'Codex':12},
        'original_status_counts':{s:{k:sum(x['source']==s and x['original_status']==k for x in observations)
            for k in ['success','failed','user_cancelled_no_retry']} for s in ['Qwen','Codex']},
        'finite_coverage':{s:{m:sum(x['source']==s and finite(x['metrics'][m]) for x in observations) for m in METRICS} for s in ['Qwen','Codex']},
        'complete_CCE':{s:sum(x['source']==s and all(finite(x['metrics'][m]) for m in ['Com','Cor','Eff']) for x in observations) for s in ['Qwen','Codex']},
        'within':{},'between':{},'tolerance':TOL,'sample_sd_ddof':1,'range_requires_n_at_least':2,
        'cross_mean_policy':'all finite repetitions, no maximum or strict-three selection',
        'unobserved_Codex_model_temperature_decoder':True,'independent_second_model_family_verified':False,
        'availability_not_accuracy_or_variance_improvement':True,'new_model_requests':0,'new_scientific_scores':0,
        'actual_command':[sys.executable,*sys.argv]}
    for category in CATEGORIES:
        summary['within'][category]={}
        for source in ['Qwen','Codex']:
            rows=[r for r in within if r['source']==source and r['category']==category]
            summary['within'][category][source]={'planned_groups':len(rows),'n_ge_2':sum(r['range_evaluable'] for r in rows),
                'singleton':sum(r['finite_n']==1 for r in rows),'zero_finite':sum(r['finite_n']==0 for r in rows),
                'nonzero_range':sum(r['nonzero_range'] is True for r in rows),
                'all_planned_finite':sum(r['all_planned_finite'] for r in rows)}
        rows=[r for r in cross if r['category']==category]
        summary['between'][category]={'planned_groups':len(rows),'at_least_one_each':sum(r['Codex_minus_Qwen'] is not None for r in rows),
            'different_mean':sum(r['absolute_difference'] is not None and r['absolute_difference']>TOL for r in rows),
            'both_n_ge_2':sum(r['both_at_least_two_finite'] for r in rows)}
    save(out/'observations.json',observations);save(out/'within.json',within);save(out/'between.json',cross)
    save(out/'direct_score_evidence.json',direct);save(out/'time_evidence.json',times)
    csvsave(out/'observations.csv',[{k:v for k,v in r.items() if k!='metrics'}|r['metrics'] for r in observations])
    csvsave(out/'within.csv',within);csvsave(out/'between.csv',cross)
    csvsave(out/'direct_comparison.csv',[r for r in cross if r['category']=='direct_primary'])
    csvsave(out/'deterministic_steps.csv',[{k:r[k] for k in ['source','answer_id','cell_id','repeat','original_status']}|{m:r['metrics'][m] for m in ['sr','sp']} for r in observations])
    save(out/'summary.json',summary)
    verify(list(BINDINGS.values()))
    save(out/'verification.json',{'status':'pass','implementation':retain(__file__),'input_bindings':list(BINDINGS.values()),
        'all_27_slots_retained':True,'all_5_shared_answer_source_bindings_equal':True,
        'all_130_returned_direct_fields_match_raw':len(direct)==130,
        'singleton_and_zero_range_sd_remain_NA':True,'no_scientific_rescoring':True,'new_model_requests':0})
    print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT/'actual_execution_01');a=p.parse_args()
    assert a.out.resolve().is_relative_to(OUT.resolve());analyze(a.out.resolve())
