"""Author source-ledger replay for three unresolved time examples.

Finite ranges use the already authorized midpoint convention. Source-declared
discrete alternatives stay separate. No averaging optional routes or choosing
the route with the highest score. No new judge observations.
"""
import copy
import csv
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(r'C:\ClearEval\ClearEval-public')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
from cce_grounded_offline_scoring_v1 import DIRECT, EGES, derive

rows = b.read(OUT/'with_author_labels/results.json')
source_index = {r['cell_id']:r for r in b.read(OUT.parent/'missing_score_diagnosis/evidence.json')['records']}
runner, registry = b.runtime()

# Author interpretation of operation membership, fixed independently of scores.
fp02_core = {**{f'{section}.{i}':[1,1] for section,n in [(1,6),(3,5),(9,6)] for i in range(1,n+1)},
             '10.1':[.5,.5], '10.2':[.5,.5], '11.1':[2,2], '11.2':[2,2]}
specs = {
    'FPC02': {
        'basis':'Original clearing-time scope includes dehydration, rehydration transitions, delipidation and RI matching. Bleaching is explicitly optional; retain both branches. Labeling preparation, staining, staining washes and storage are excluded.',
        'scenarios':[('without_optional_bleaching', fp02_core),
                     ('with_optional_bleaching', {**fp02_core,'2.1':[12,12]})]},
    'FPC04': {
        'basis':'Sections 1–4 are explicitly permeabilization/blocking/immunostaining and their washes. Core clearing is sections 5–7. Section 8 is imaging preparation and 9 is storage/re-imaging. Do not count the six-month storage or imaging equilibration as first-pass core treatment.',
        'scenarios':[('reported_core', {**{f'5.{i}':[1,1] for i in range(1,7)},
                        '6.1':[.5,.75], '7.1':[2,4], '7.2':[12,12]})]},
    'FPC05': {
        'basis':'CUBIC-L steps 1.2/1.3 are serial; the stated 48–72 h is their combined duration, not an additional incubation. Step 1.4 is a wash removing the delipidation reagent before a different phase. Its two stated schedules remain separate. Sections 2–6 are labeling preparation/staining/washes. Sections 8–9 are storage and repeat imaging, excluded from initial core time.',
        'scenarios':[(name,{'1.2':[24,24], '1.3':[24,48], '1.4':wash,
                          '7.1':[12,24], '7.2':[24,48]})
                     for name,wash in [('six_30min_transition_washes',[3,3]),('two_6h_transition_washes',[12,12])]]}
}
annotations, conditional_rows = [], []
for row in rows:
    name = row['cell_id']
    if name not in specs:
        continue
    spec = specs[name]
    binding = source_index[name]['source_document']
    assert b.bind(binding['path']) == binding
    doc = b.read(binding['path'])
    operation_lines = {}
    for line in doc['text'].splitlines():
        match = re.match(r'^(\d+\.\d+)\s',line)
        if match:
            assert match[1] not in operation_lines
            operation_lines[match[1]] = line
    annotation = {'cell_id':name,'answer_sha256':doc['answer_sha256'],'source_document':binding,
        'semantic_author':'current_Codex_assistant_author_annotation', 'expert_validated':False,
        'basis':spec['basis'],'new_model_calls':0,'scenarios':[]}
    time_results = []
    qid = row['question_id']
    demand = registry.get(qid,registry.questions[str(qid)]['question'])
    for scenario_id, included in spec['scenarios']:
        assert set(included)<=set(operation_lines)
        ledger = []
        for operation_id,line in operation_lines.items():
            start = doc['text'].index(line)
            span = {'start':start,'end':start+len(line),'quote':line}
            b.verify_span(doc['text'],span)
            ledger.append({'operation_id':operation_id,'included_in_core':operation_id in included,
                'hours_lower_upper':included.get(operation_id), 'source':span,
                'excluded_reason':None if operation_id in included else 'outside this core-time scenario; see annotated phase basis'})
        bounds = [sum(v[i] for v in included.values()) for i in [0,1]]
        midpoint = sum(bounds)/2
        annotation['scenarios'].append({'scenario_id':scenario_id,'operation_ledger':ledger,
            'core_hours_bounds':bounds,'core_hours_midpoint':midpoint})
        effect = runner.calculate_effectiveness_score({**row['quantitative_data'],'total_time_hours':midpoint},
                                                       demand,runner.MODEL_SPACE_SIGNED,{},[])
        checkpoints = set(bounds+[midpoint])
        for boundary in ['min_hours','max_hours']:
            value = effect['time_computation'].get(boundary)
            if b.finite(value) and bounds[0]<=value<=bounds[1]:
                checkpoints.add(value)
        sensitivity = []
        for hours in sorted(checkpoints):
            computed = runner.calculate_effectiveness_score({**row['quantitative_data'],'total_time_hours':hours},
                                                            demand,runner.MODEL_SPACE_SIGNED,{},[])
            sensitivity.append({'hours':hours,'s_time':computed['s_time']})
        time_results.append({'scenario_id':scenario_id,'hours_bounds':bounds,'midpoint_hours':midpoint,
            's_time':effect['s_time'],'original_time_computation':effect['time_computation'],
            'range_sensitivity':sensitivity})
    annotations.append(annotation)
    previous = copy.deepcopy(row['metrics'])
    row['time_branch_version'] = 'source-bound-author-time-scenarios-v1'
    row['before_time_branch_metrics'] = previous
    row['before_time_branch_derivation'] = copy.deepcopy(row.get('time_derivation'))
    row['source_bound_time_scenarios'] = time_results
    row['time_branch_author_annotation'] = annotation
    if len(time_results)==1:
        row['metrics'] = derive({**{k:previous[k] for k in DIRECT+EGES},'s_time':time_results[0]['s_time']},
                               {k:previous[k] for k in ['sr','sp']},True)
        row['time_derivation'] = {'decision':'author_source_ledger_finite_range_midpoint',
            'hours':time_results[0]['midpoint_hours'],'bounds_hours':time_results[0]['hours_bounds'],'issues':[]}
        row['time_formula'] = time_results[0]['original_time_computation']
        row['time_sensitivity'] = time_results[0]['range_sensitivity']
        row['quantitative_data']['total_time_hours'] = time_results[0]['midpoint_hours']
    else:
        row['time_derivation'] = {'decision':'source_declared_discrete_alternatives_preserved',
            'hours':None, 'issues':['source_alternatives_produce_different_time_scores'],
            'scenarios':time_results}
    row['remaining_dependencies']['time'] = row['time_derivation']['issues']
    label_scenarios = [(a['scenario_id'],a['metrics']['s_label']) for a in row.get('conditional_CCE',[])] or [('reported_label',previous['s_label'])]
    row['conditional_CCE'] = []
    for time,label in itertools.product(time_results,label_scenarios):
        metrics = derive({**{k:previous[k] for k in DIRECT+EGES},'s_time':time['s_time'],'s_label':label[1]},
                         {k:previous[k] for k in ['sr','sp']},True)
        row['conditional_CCE'].append({'time_scenario':time['scenario_id'],'label_scenario':label[0],'metrics':metrics})
        conditional_rows.append({'cell_id':name,'time_scenario':time['scenario_id'],'label_scenario':label[0],
            'midpoint_core_hours':time['midpoint_hours'], 'core_hours_lower':time['hours_bounds'][0],
            'core_hours_upper':time['hours_bounds'][1], **metrics})
    row['complete_numeric_CCE'] = b.complete(row['metrics'])
    assert all(row['metrics'][k]==previous[k] for k in DIRECT+['sr','sp','Com','Cor','s_method','s_label','s_trans'])

output = OUT/'with_time_branches'
b.save(output/'results.json',rows)
b.save(output/'time_annotations.json',{'results':annotations,'new_model_requests':0,'expert_records':0})
actual = [r for r in rows if r.get('source_record')]
summary = {'saved_returns':len(actual),'complete_single_CCE':sum(r['complete_numeric_CCE'] for r in actual),
    's_label_available':sum(r['metrics']['s_label'] is not None for r in actual),
    's_time_available':sum(r['metrics']['s_time'] is not None for r in actual),
    'fully_numeric_conditional_vectors':sum(b.complete(r) for r in conditional_rows),
    'conditional_answers':sorted({r['cell_id'] for r in conditional_rows}),
    'new_model_requests':0,'time_deleted_controls_imputed':False,
    'interpretation':'Conditional vectors are source alternatives, not additional independent answers or replacement primary scores.'}
b.save(output/'summary.json',summary)
b.save(output/'manifest.json',{'entrypoint':b.bind(__file__),'input':b.bind(OUT/'with_author_labels/results.json'),
    'source_index':b.bind(OUT.parent/'missing_score_diagnosis/evidence.json'),
    'original_scorer':b.bind(ROOT/'OEQ_run_grading_new.py'),'time_kb':b.bind(ROOT/'KnowledgeBase/time_kb.json')})
for filename, values in [('conditional_CCE.csv',conditional_rows),('per_answer.csv',[
        {'cohort':r['cohort'],'cell_id':r['cell_id'],'question_id':r['question_id'],**r['metrics']} for r in actual])]:
    with (output/filename).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
assert all(b.complete(r) for r in conditional_rows)
assert all(next(r for r in actual if r['cell_id']==f'E2_{i:02d}__local_qwen27b_q8_development__r0')['metrics']['s_time'] is None for i in [3,7,11])
print(json.dumps({'summary':summary,'conditional':conditional_rows},ensure_ascii=False,indent=2))
