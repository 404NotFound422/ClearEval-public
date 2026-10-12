"""Join actual full-text judge trials and independent, input-bound SR/SP results."""
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import OUT,read,write,table,digest,mean
from cce_judges import digest as judge_digest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--judge-dir',type=Path,default=OUT/'judges/local_controls')
    args=parser.parse_args()
    cases={c['case_id']:c for c in read(OUT/'controls/cases.json')['cases']}
    steps={s['case_id']:s for s in read(OUT/'controls/step_results.json')}
    scored=[];rejected=[]
    for path in sorted((args.judge_dir/'trials').glob('*.json')):
        trial=read(path);cid=trial['case_id'];case=cases.get(cid);step=steps.get(cid)
        if not case or not step or trial.get('repeat_index')!=0:continue
        expected=judge_digest({'question':case['specific_question'],'question_id':case['question_id'],'protocol':case['model_response'],'references':case.get('references')})
        if trial['full_text_input_sha256']!=expected or step['input_sha256']!=digest(case['model_response']):
            rejected.append({'case_id':cid,'reason':'input_hash_mismatch'});continue
        if trial['status']!='success' or not trial.get('new_extraction_available'):
            rejected.append({'case_id':cid,'reason':'judge_or_extraction_failed'});continue
        numbers=trial['preserved_numeric_proposals'];sr=step['sr'];cp=numbers.get('c_param')
        com=.4*sr+.6*cp/3 if sr is not None and cp is not None else None
        dims=[com,numbers.get('Cor'),numbers.get('Eff')]
        record={'case_id':cid,'base_id':case['base_id'],'condition':case['condition'],'question_id':case['question_id'],
            'judge':trial['judge'],'judge_family':trial['judge_family'],'trial_id':trial['trial_id'],
            'judge_config_sha256':trial['pipeline_config_sha256'],'step_config_sha256':step.get('step_config_sha256'),
            'references_sha256':trial['references_sha256'],'input_sha256':expected,'answer_sha256':step['input_sha256'],
            'numeric_scope':'local_substitute_full_pipeline_development','formal_eligible':False,
            'upstream_cce_eligible':trial['upstream_cce_eligible'],'sr':sr,'sp':step['sp'],'reference_id':step['reference_id'],
            **numbers,'Com':com,'IA':min(dims) if all(x is not None for x in dims) else None,
            'HV':math.prod(dims) if all(x is not None for x in dims) else None,'new_extraction_available':True,'trial_source':str(path)}
        scored.append(record)
    baseline={(r['base_id'],r['judge']):r for r in scored if r['condition']=='baseline'}
    pairs=[]
    for r in scored:
        if r['condition']=='baseline':continue
        b=baseline.get((r['base_id'],r['judge']))
        if not b:continue
        same=all(r[k]==b[k] for k in ['judge_config_sha256','step_config_sha256','references_sha256'])
        if not same:
            rejected.append({'case_id':r['case_id'],'reason':'paired_configuration_mismatch'});continue
        metrics=['sr','sp','c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','Com','Cor','Eff','IA','HV']
        pairs.append({k:r[k] for k in ['case_id','base_id','condition','question_id','judge','numeric_scope','formal_eligible','judge_config_sha256','step_config_sha256']}|
            {'full_pipeline_complete':True,'baseline_trial_id':b['trial_id'],'variant_trial_id':r['trial_id'],
             'different_answer_text':b['answer_sha256']!=r['answer_sha256'],
             **{prefix+k:value for k in metrics for prefix,value in [('baseline_',b.get(k)),('variant_',r.get(k)),('delta_',r[k]-b[k] if r.get(k) is not None and b.get(k) is not None else None)]}})
    summary=[]
    for condition in sorted({c['condition'] for c in cases.values()}-{'baseline'}):
        subset=[p for p in pairs if p['condition']==condition]
        summary.append({'condition':condition,'planned_pairs':sum(c['condition']==condition for c in cases.values()),'completed_pairs':len(subset),
            'sr_decreased':sum(p['delta_sr'] is not None and p['delta_sr']< -1e-12 for p in subset),
            'sr_unchanged':sum(p['delta_sr'] is not None and abs(p['delta_sr'])<=1e-12 for p in subset),
            'c_param_decreased':sum(p['delta_c_param'] is not None and p['delta_c_param']<0 for p in subset),
            **{'mean_delta_'+k:mean([p['delta_'+k] for p in subset if p['delta_'+k] is not None]) for k in ['sr','sp','Com','Cor','Eff','IA','HV']}})
    write(OUT/'controls/full_pipeline_per_case.json',scored);table(OUT/'controls/full_pipeline_per_case.csv',scored)
    write(OUT/'controls/full_pipeline_pairs.json',pairs);table(OUT/'controls/full_pipeline_pairs.csv',pairs)
    table(OUT/'controls/full_pipeline_summary.csv',summary)
    status={'planned_cases':len(cases),'successful_cases':len(scored),'planned_pairs':len(cases)-sum(c['condition']=='baseline' for c in cases.values()),'completed_pairs':len(pairs),'formal_eligible':False,'scope':'development; current local substitute; original numerical functions; same fixed configuration; source applicability awaits review','conditions':summary,'rejected':rejected}
    write(OUT/'controls/full_pipeline_status.json',status)
    print(json.dumps(status,ensure_ascii=True))

if __name__=='__main__':main()
