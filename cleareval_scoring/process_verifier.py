"""Partial process dependencies: explicit declarations and source-bound relations."""
import re
from .recipe_verifier import CATALOG
def stage(step):
    h=re.sub(r'\([^)]*\)|（[^）]*）','',step.get('heading',''));t=step['text']
    label=bool(re.search(r'immun|stain|label|染色|标记|免疫',h,re.I))
    clear=bool(re.search(r'clear|dehydrat|delipid|refractive|\bRI\b|透明|脱水|脱脂|折射',h,re.I))
    if label and not clear:return 'labeling'
    if label and clear and re.search(r'antibod|block|stain|label|抗体|封闭|染色',t,re.I):return 'labeling'
    if re.search(r'refractive|\bRI\b|折射',h,re.I):return 'ri_matching'
    if re.search(r'dehydrat|脱水',h,re.I):return 'dehydration'
    if clear:return 'clearing'
    return 'other'
def evaluate(case):
    steps=case['candidate_steps'];stages=[stage(s) for s in steps];constraints=[];seen=set()
    for i,s in enumerate(steps):
        h=s.get('heading','')
        m=re.search(r'(?:performed\s+)?before\s+(dehydration|clearing|RI matching|refractive index matching)|(?:脱水|透明|折射率匹配)之前',h,re.I)
        if m and stages[i]=='labeling' and h not in seen:
            seen.add(h);target='dehydration' if re.search(r'dehydrat|脱水',m[0],re.I) else 'ri_matching' if re.search(r'RI|refractive|折射',m[0],re.I) else 'clearing'
            left=[k for k in range(len(steps)) if steps[k].get('heading')==h]
            right=[k for k,x in enumerate(stages) if x==target]
            constraints.append(dict(origin='CANDIDATE_EXPLICIT_PRECEDENCE_VS_NUMBERED_SEQUENCE',before='labeling',after=target,
                                    evidence=h,left=left,right=right))
    # Both bindings are read from the source passages frozen in process_sources.json.
    dependency=CATALOG['process_dependencies'].get(case.get('method'))
    if dependency and dependency['reference_contains'].lower() in case.get('reference_id','').lower():
        left=[i for i,x in enumerate(stages) if x=='labeling']
        right=[i for i,x in enumerate(stages) if x in ('clearing','ri_matching')]
        if left and right:
            constraints.append(dict(origin='SOURCE_DECLARED_LABEL_BEFORE_CLEARING',source_key=case['method'],
                                    source_evidence=dependency['evidence'],
                                    before='labeling',after='clearing',left=left,right=right))
    failed=set();records=[]
    for edge in constraints:
        inversions=[(i,j) for i in edge['left'] for j in edge['right'] if i>j]
        status='FAIL' if inversions else 'PASS' if edge['left'] and edge['right'] else 'UNKNOWN'
        if inversions:failed.update(steps[j]['id'] for i,j in inversions)
        records.append({**{k:v for k,v in edge.items() if k not in ('left','right')},'status':status,
                        'before_ids':[steps[i]['id'] for i in edge['left']],'after_ids':[steps[i]['id'] for i in edge['right']],
                        'violations':[dict(before=steps[i]['id'],after=steps[j]['id']) for i,j in inversions]})
    return dict(constraints=records,failed_candidate_ids=sorted(failed),scope='explicit declarations plus FOCM/Ce3D source relations; not a complete biological DAG')
