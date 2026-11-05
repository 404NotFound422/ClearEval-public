"""Validate the completed 185-answer result and summarize changes, without rescoring."""
from pathlib import Path
import hashlib,json,math,sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import cleareval_complete_scoring as s
from cleareval_scoring import preparation,scoring_v6
from results.oeq_metrics import protocol_scores

OUT=ROOT/'results/benchmark185/2026-11-05-v6.2'
BASELINE=ROOT/'results/benchmark185/2026-11-03'
HERE=Path(__file__).parent
cases=s.read(s.DEFAULT_INPUT)['cases']
packets=s.read(HERE/'full_retest_checks.json.gz')
rows=s.read(OUT/'scores185.json.gz')
branches=s.read(OUT/'scores193.json.gz')
baseline={r['id']:r for r in s.read(BASELINE/'scores185.json.gz')}
by_id={r['id']:r for r in rows}
assert len(rows)==len(by_id)==185 and len(branches)==len(packets)==len(cases)==193
assert set(by_id)=={c['id'] for c in cases}
assert {(r['id'],r['branch']) for r in packets}=={(c['id'],c['branch']) for c in cases}
for c in cases:assert hashlib.sha256(c['answer'].encode()).hexdigest()==c['answer_sha256']
receipt=s.read(HERE/'run_receipt.json')
assert receipt['version']==scoring_v6.VERSION
assert receipt['verified_sha256']==s.sha(HERE/'full_retest_checks.json.gz')
assert receipt['input_sha256']==s.sha(s.DEFAULT_INPUT)
assert s.sha(s.DEFAULT_VERIFIED)==receipt['verified_sha256']
assert s.read(s.DEFAULT_VERIFIED.with_name('run_receipt.json'))==receipt
for name,digest in receipt['code_sha256'].items():assert s.sha(ROOT/'cleareval_scoring'/name)==digest,name

for row in rows+branches:
    for key,node in row['metrics'].items():
        assert math.isfinite(node['value']),(row['id'],key)
        low,high=node['bounds']
        assert math.isfinite(low) and math.isfinite(high)
        assert low-1e-10<=node['value']<=high+1e-10,(row['id'],key)
    m=row['metrics']
    assert abs(m['IA']['value']-min(m[k]['value'] for k in ['Com','Co','Eff']))<1e-10
    assert abs(m['Co']['value']-sum(m[k]['value']/den for k,den in [('co_order',3),('co_method',2),('co_param',2),('co_chem',1)])/4)<1e-10
for item in s.read(OUT/'evaluations185.json.gz'):
    actual=protocol_scores(item);expected=by_id[item['case_id']]['metrics']
    for key,alias in [('Com','Com'),('Co','Cor'),('Eff','Eff'),('IA','I_A')]:
        assert abs(actual[alias]-expected[key]['value'])<1e-10

reviews=set();retained=[];dilution=Counter();projected=set()
for row in packets:
    p=row['packet'];assert p['version']==scoring_v6.VERSION
    if p['recipe_projected_steps']:projected.add(row['id'])
    reviews.update(d['review_id'] for d in p['human_adjudications'])
    for d in p['human_adjudications']:
        found=[x['correctness_checks'][d['field']] for x in p['written']['pairs']
               if x['candidate'] in d['candidate_ids'] and d['field'] in x['correctness_checks']]
        assert found and all(x==d['state'] for x in found),(row['id'],d['review_id'])
    assert not any(preparation.role(step)=='reagent_preparation' for step in p['logical_candidate_steps'])
    assert p['written']['metrics']['N_C']==len(p['logical_candidate_steps'])
    branch=next(b for b in branches if (b['id'],b['branch'])==(row['id'],row['branch']))
    m=p['written']['metrics'];den=m['N_R']+m['N_C']
    if den:
        assert branch['metrics']['bio_f1']['bounds']==[2*m['confirmed_correct_credit']/den,
                                                      2*(m['confirmed_correct_credit']+m['correctness_review_credit'])/den]
    for mode in ['written','occurrence']:
        m=p[mode]['metrics'];pairs=p[mode]['pairs']
        assert m['confirmed_correct_credit']==sum(x['count'] for x in pairs if x['correctness_status']=='PASS')
        assert m['confirmed_correct_credit']<=m['matched_credit']<=min(m['N_R'],m['N_C'])
        for pair in pairs:
            assert not {'duration','temperature','pH','agitation'}&set(pair['correctness_checks'])
    retained += [dict(id=row['id'],branch=row['branch'],candidate=a['candidate'],stock=a.get('stock'))
                 for a in p['operation_claim_audit'] if a['reason']=='LEGACY_CLAIM_RETAINED_PENDING_BINDING']
    dilution.update(a['status'] for a in p['preparation_dilution_audit'])
assert reviews=={d['review_id'] for d in s.read(s.DEFAULT_INPUT.with_name('adjudications.json'))}
assert not retained,('Unresolved recipe ownership',retained)

fields=['c_step','co_order','co_method','co_param','bio_sr','bio_sp','bio_f1','Com','Co','Eff','IA']
changes=[]
for row in rows:
    before=baseline[row['id']]['metrics'];after=row['metrics']
    delta={key:dict(before=before[key]['value'],after=after[key]['value'],
                    before_status=before[key]['status'],after_status=after[key]['status'])
           for key in fields if before[key]['value']!=after[key]['value'] or before[key]['status']!=after[key]['status']}
    if delta:changes.append(dict(id=row['id'],method=row['method'],changes=delta))
    for key in ['c_param','co_chem','s_method','s_label','s_trans','s_time','Eff']:
        assert before[key]==after[key],(row['id'],key,'Unexpected change outside this repair')
for ident in ['EXPAND_011','EXPAND_012','EXPAND_015']:
    assert all(by_id[ident]['metrics'][key]['value']==0 for key in ['Com','Co','Eff','IA'])
assert [by_id['EXPAND_026']['metrics'][k]['value'] for k in ['co_order','co_method','co_param']]==[0,0,0]

summary=s.read(OUT/'summary.json');old=s.read(BASELINE/'summary.json')
report=dict(version=scoring_v6.VERSION,validation='PASS',answers=185,branches=193,new_model_calls=0,
            answers_unchanged=True,expert_reviews_preserved=len(reviews),projected_answers=len(projected),
            recipe_bindings_to_check=retained,dilution_checks=dict(dilution),changed_answers=len(changes),
            means={k:dict(before=old['means'][k],after=summary['means'][k]) for k in ['bio_sr','bio_sp','bio_f1','Com','Co','Eff','IA']},
            final_statuses=summary['statuses'],provisional_components=summary['provisional_components'],
            changed_cases=changes)
(HERE/'full_retest_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({k:v for k,v in report.items() if k!='changed_cases'},ensure_ascii=False))
