"""Recompute the existing fixed two-generator cohort with revised saved scores."""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(r'C:\ClearEval\ClearEval-public')
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import cce_secondary_E5_analysis_v2 as prior
import cce_analysis as analysis

meta = prior.fixed_metadata()
latest = {r['cell_id']:r for r in b.read(OUT/'with_time_branches/results.json') if r.get('source_record')}
with (prior.STEPS/'t070_per_answer.csv').open(encoding='utf-8-sig',newline='') as f:
    steps = {r['answer_id']:r for r in csv.DictReader(f)}
refs = b.read(prior.STEPS/'references.json')['references']
references = {r['reference_id']:r for r in refs}
cohort = []
for item in meta['fixed_secondary_cohort']:
    row,step = latest[item['confirmation_id']],steps[item['answer_id']]
    assert row['answer_sha256']==item['answer_sha256']==step['answer_sha256']
    assert step['question_sha256']==item['question_sha256']
    assert row['question_id']==item['question_id']
    assert all(row['metrics'][k]==float(step[k]) for k in ['sr','sp'])
    ref = references[step['reference_id']]
    cohort.append({'model':item['model'],'answer_id':item['answer_id'],'cell_id':item['confirmation_id'],
        'question_id':item['question_id'],'question_sha256':item['question_sha256'],
        'answer_sha256':item['answer_sha256'],'identity_eligible':True,'formal_eligible':False,
        'family_id':ref['family_id'],'reference_id':ref['reference_id'],
        'source_document':row['source_document'],'complete_CCE':b.complete(row['metrics']),**row['metrics']})
common,by = analysis.common_summary(cohort,prior.MODELS,scope='typed_labels_posthoc_fixed_existing_cohort',denominator=5)
old_cohort = [{**r,**latest[r['cell_id']]['comparison_metrics']} for r in cohort]
old_common,_ = analysis.common_summary(old_cohort,prior.MODELS,scope='prior_scoped_midpoint_same_cohort',denominator=5)
bootstrap,draws,exact = prior.task_bootstrap(common,by)
family,family_draws = analysis.family_bootstrap(common,by,prior.REPEATS,prior.SEED)
dest=OUT/'joint'
components = prior.component_summary(cohort)
for name,value in [('per_answer',cohort),('common_joint',common),('previous_same_cohort',old_common),
                   ('task_bootstrap',bootstrap),('task_draws',draws),('task_exact_draws',exact),
                   ('family_bootstrap',family),('family_draws',family_draws),
                   ('component_common_sets',components),('source_overlap',prior.overlap_diagnostic(refs,common['common_question_ids']))]:
    b.save(dest/(name+'.json'),value)
prior.csvwrite(dest/'per_answer.csv',cohort)
prior.csvwrite(dest/'model_means.csv',[{'model':model,**values} for model,values in common['means'].items()])
prior.csvwrite(dest/'task_exact_draws.csv',exact)
assert all(math.isclose(bootstrap['exact']['bootstrap_means'][m][k],common['means'][m][k],abs_tol=1e-12)
           for m in prior.MODELS for k in prior.JOINT)
assert all(draws[i]['question_draws']==draws[i+1]['question_draws'] for i in range(0,len(draws),2))
summary={'fixed_answers':len(cohort),'complete_before':sum(b.complete(r) for r in old_cohort),
    'complete_after':sum(b.complete(r) for r in cohort),'common_before':old_common['common_question_ids'],
    'common_after':common['common_question_ids'],'means':common['means'],
    'empirical_nondominated':common['empirical_nondominated'],
    'task_bootstrap_repeats':prior.REPEATS,'exact_ordered_samples':bootstrap['exact_enumeration_count'],
    'monte_carlo_nondominance_frequency':bootstrap['monte_carlo']['nondominance_frequency'],
    'exact_nondominance_frequency':bootstrap['exact']['nondominance_frequency'],
    'family_bootstrap_status':family['status'],'new_model_requests':0,
    'formal_result':False,'limitation':'Post-hoc exposed five-task cohort; two generator sizes in one model family; reference applicability/expert validation remains pending.'}
b.save(dest/'summary.json',summary)
b.save(dest/'manifest.json',{'entrypoint':b.bind(__file__),'scores':b.bind(OUT/'with_time_branches/results.json'),
    'frozen_cohort':b.bind(prior.SELECTION),'raw_steps':b.bind(prior.STEPS/'t070_per_answer.csv'),
    'references':b.bind(prior.STEPS/'references.json'),'original_analysis':b.bind(analysis.__file__),
    'prior_bootstrap':b.bind(prior.__file__)})
print(json.dumps(summary,ensure_ascii=False,indent=2))
