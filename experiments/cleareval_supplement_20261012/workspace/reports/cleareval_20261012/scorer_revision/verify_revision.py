"""Verify revised scorer artifacts without reusing their reported aggregates."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def full(m):return all(m[k] is not None for k in ['Com','Cor','Eff','IA','HV'])
checks=[]
details={}
for mode in ['rules_only','with_decomposition']:
    rows=read(HERE/mode/'results.json')
    summary=read(HERE/mode/'summary.json')
    manifest=read(HERE/mode/'execution_manifest.json')
    assert len(rows)==68
    for key in ['entrypoint','config','cells','original_scorer','knowledge_base']:
        record=manifest[key]
        assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256']
    for r in rows:
        if r.get('source_record'):
            b=r['source_record'];assert hashlib.sha256(Path(b['path']).read_bytes()).hexdigest()==b['sha256']
        for key in ['c_param','co_order','co_method','co_param','co_chem','sr','sp','Com','Cor','s_method','s_trans']:
            assert r['metrics'][key]==r['baseline_metrics'][key],(mode,r['cell_id'],key)
        if full(r['baseline_metrics']):assert r['metrics']==r['baseline_metrics'],r['cell_id']
    n_before=sum(full(r['baseline_metrics']) for r in rows)
    n_after=sum(full(r['metrics']) for r in rows)
    assert n_before==summary['complete_before']==8
    assert n_after==summary['complete_after']==(9 if mode=='rules_only' else 10)
    actual=[r for r in rows if r['status']!='no_saved_return']
    assert len(actual)==67
    details[mode]={'planned_slots':len(rows),'saved_returns':len(actual),
        'complete_before':n_before,'complete_after':n_after,
        'missing_components':{k:sum(r['metrics'][k] is None for r in actual)
                              for k in ['Com','Cor','Eff','s_method','s_label','s_trans','s_time']}}
    checks.append(mode+': all saved-score inputs and original code/KB hashes verified')
    checks.append(mode+': all 11 reused components unchanged in every slot')
    checks.append(mode+': all 8 previously complete score vectors exactly preserved')
    checks.append(mode+': coverage counts independently recomputed')
reference={r['id']:r['point_result']['metrics'] for r in read(HERE.parent/'label_lookup_midpoint.json')['results']}
rows=read(HERE/'with_decomposition/results.json')
for cid,m in reference.items():
    found=next(r for r in rows if r['cohort']=='first7_posthoc' and r['cell_id']==cid)
    assert found['metrics']==m
checks.append('general scorer exactly reproduces both earlier manually explained examples')
output={'status':'PASS','checks':checks,'results':details,'new_model_requests':0,
        'scope':'hashes, numerical reproducibility and regression coverage; not expert scientific validation'}
(HERE/'verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(output,ensure_ascii=False,indent=2))
