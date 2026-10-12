"""Preserve paired task comparisons when their references have several families."""
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
batch=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/confirmation_qwen_01'
cases={c['anonymous_answer_id']:c for c in b.read(batch/'cases.json')['cases']}
cells=[c for c in b.read(batch/'matrix.json') if str(c['question_id']) in ['23','248']]
answer_families=[];by_question={}
for cell in cells:
    case=cases[cell['anonymous_answer_id']]
    ref=next(r for r in case['references'] if r['reference_id']==cell['step']['reference_id'])
    q=str(case['question_id']);family=ref['family_id']
    by_question.setdefault(q,set()).add(family)
    answer_families.append({'cell_id':cell['anonymous_answer_id'],'question_id':q,
        'generator':case['generator_model'],'reference_id':ref['reference_id'],
        'selected_reference_family':family,'reference_status':case['reference_status']})
questions=sorted(by_question);edges=[]
for i,q in enumerate(questions):
    for t in questions[i+1:]:
        shared=by_question[q]&by_question[t]
        if shared:edges.append({'tasks':[q,t],'shared_selected_reference_families':sorted(shared)})
remaining=set(questions);components=[]
while remaining:
    component={min(remaining)}
    while True:
        grown=component|{t for e in edges if component&set(e['tasks']) for t in e['tasks']}
        if grown==component:break
        component=grown
    remaining-=component;components.append(sorted(component))
result={'scope':'same two-task joint cohort; reference-dependence sensitivity, not a measured correlation model',
    'question_pair_is_the_minimum_unit':True,'answer_reference_membership':answer_families,
    'question_family_sets':{q:sorted(s) for q,s in by_question.items()},'edges':edges,
    'conservative_connected_components':components,'component_n':len(components),
    'cluster_uncertainty_estimable':len(components)>1,
    'result':'One connected component spans both paired tasks through the shared FDISCO source. A family-block bootstrap has no independent block variation to estimate.',
    'task_exact_resampling_remains':'descriptive reweighting of the observed two questions, not family-independent population uncertainty',
    'not_claimed':'A shared reference does not itself prove that observed answer errors are correlated.',
    'source_bindings':[b.bind(batch/'cases.json'),b.bind(batch/'matrix.json')],
    'command':[sys.executable,*sys.argv],'new_model_calls':0}
assert components==[['23','248']]
b.save(OUT/'joint/source_dependency_audit.json',result)
print(json.dumps({k:result[k] for k in ['question_family_sets','edges','conservative_connected_components','cluster_uncertainty_estimable']},ensure_ascii=False,indent=2))
