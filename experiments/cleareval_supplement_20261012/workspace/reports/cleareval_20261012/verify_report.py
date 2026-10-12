"""Verify saved report numbers and render local HTML; no model or network calls."""
from __future__ import annotations
import csv
import hashlib
import html
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import sys
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = Path(r'C:\ClearEval\ClearEval-public')
OUT = REPO/'artifacts/cce_validation'
R2 = OUT/'optimizer_round2_20261010'
R3 = OUT/'optimizer_round3_20261011'
P = R3/'source_context_validation_proposal_01'
CHECKS = []
SOURCES = {}
FORMULA_RECORDS = []


def check(ok, name):
    CHECKS.append({'check': name, 'passed': bool(ok)})
    if not ok:
        raise AssertionError(name)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    path = Path(path).resolve()
    row = {'path': str(path), 'sha256': sha(path)}
    if HERE not in path.parents:
        SOURCES[str(path)] = row
    return row


def read(path):
    bind(path)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    bind(path)
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def finite(x):
    return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)


def same(a,b):
    return (a is None and b is None) or (finite(a) and finite(b) and math.isclose(a,b,abs_tol=1e-12,rel_tol=1e-12))


def formula(identity, m):
    com = .4*m['sr']+.6*m['c_param']/3 if all(finite(m.get(k)) for k in ['sr','c_param']) else None
    ck = ['co_order','co_method','co_param','co_chem']
    cor = sum(m[k]/s for k,s in zip(ck,[3,2,2,1]))/4 if all(finite(m.get(k)) for k in ck) else None
    ek = ['s_method','s_label','s_trans','s_time']
    eff = ((m['s_method']/2.5+1)/2+m['s_label']/6+m['s_trans']/3+m['s_time']/3)/4 if all(finite(m.get(k)) for k in ek) else None
    joint = [com,cor,eff]
    calculated = {'Com':com,'Cor':cor,'Eff':eff,'IA':min(joint) if all(map(finite,joint)) else None,
        'HV':math.prod(joint) if all(map(finite,joint)) else None}
    for k,v in calculated.items():
        check(same(v,m.get(k)), f'formula:{identity}:{k}')
    FORMULA_RECORDS.append({'id':identity,'metrics':m,'recomputed':calculated})


def binding(row):
    if isinstance(row,dict) and isinstance(row.get('path'),str) and row.get('sha256'):
        p=Path(row['path'])
        check(p.is_file(), 'source_exists:'+str(p))
        check(sha(p)==row['sha256'], 'source_sha:'+str(p))
        bind(p)


def csv_metrics(row):
    keys=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']
    return {k:float(row[k]) if row.get(k) not in [None,'','null','NA'] else None for k in keys}


def main():
    ledger_path=OUT/'judges/request_ledger.jsonl'
    initial_ledger=sha(ledger_path)
    budget=read(P/'budget_snapshot.json')
    check(budget['attempts_recorded']==budget['package_limit']==438, 'budget_438_of_438')
    check(budget['remaining_request_capacity']==0, 'no_new_request_capacity_consumed')
    binding(budget['ledger'])

    obs=read(P/'readout_complete_01/observations.json')
    check(len(obs)==15,'latest_15_observations')
    for o in obs:
        formula(o['observation_id'],o['metrics'])
        for key in ['raw','saved_processing','doc','terminal']:
            binding(o.get(key))
    for cond in ['K0','K1','K2']:
        group=[o for o in obs if o['observation_id'].endswith('_'+cond)]
        check(len(group)==5 and sum(finite(o['metrics']['Eff']) for o in group)==1, 'latest_one_complete:'+cond)
    for cid in ['A01','A02','A03','A04','A05']:
        group=[o['metrics'] for o in obs if o['observation_id'].startswith(cid+'_')]
        for k in ['sr','sp','Com','s_method','s_label','s_trans','s_time']:
            check(all(same(group[0][k],g[k]) for g in group), 'latest_unchanged:'+cid+':'+k)

    pairs=read(R3/'E2_canonical_readout_complete_01/paired_results.json')
    check(len(pairs)==18,'E2_18_pair_observations')
    unique={}
    for p in pairs:
        for side in ['baseline','variant']:
            tid=p[side+'_trial_id'];m=p[side+'_metrics']
            if tid in unique:check(unique[tid]==m,'E2_same_reused_baseline:'+tid)
            else:unique[tid]=m;formula('E2:'+tid,m)
        for k,v in p['deltas'].items():
            a=p['baseline_metrics'][k];b=p['variant_metrics'][k]
            check(same(b-a if finite(a) and finite(b) else None,v), 'E2_delta:'+p['pair_id']+':'+str(p['repeat_index'])+':'+k)
    check(len(unique)==24,'E2_24_unique_observations')
    check(sum(finite(m['Eff']) for m in unique.values())==0,'E2_main_CCE_zero')
    repeats=read(R3/'E2_canonical_readout_complete_01/repeatability.json')
    check(len(repeats)==108,'E4_108_groups')
    check(sum(x['both_finite'] for x in repeats)==93,'E4_93_both_finite')
    check(sum(x['both_missing'] for x in repeats)==15,'E4_15_both_missing')
    check(all(x['range']==x['sample_SD']==0 for x in repeats if x['both_finite']),'E4_all_finite_zero_range_and_SD')

    deletion=[p for p in pairs if p['condition']=='necessary_step_deletion' and p['repeat_index']==0]
    deletion.sort(key=lambda x:x['question_id'])
    ds=[p['deltas']['Com'] for p in deletion]
    check(all(same(a,b) for a,b in zip(ds,[-2/35,-1/5,0])),'deletion_exact_task_deltas')
    exact=sorted(sum(ds[i] for i in ids)/3 for ids in itertools.product(range(3),repeat=3))
    check(len(exact)==27 and sum(v < -1e-12 for v in exact)==26,'exact_26_of_27_decrease')
    q=lambda p:exact[max(0,math.ceil(p*len(exact))-1)]
    check(same(q(.025),-.2) and same(q(.975),0),'exact_discrete_quantiles')
    check(same(statistics.mean(ds),-3/35),'deletion_mean')

    e5=rows(R2/'secondary_E5_posthoc_analysis_v1/actual_v6_01/per_answer.csv')
    for row in e5:
        formula('E5:'+row['anonymous_answer_id'],csv_metrics(row))
        for key in ['source_document','request_payload','receipt','trial','raw_response','posthoc_record']:
            if row.get(key):binding(json.loads(row[key]))
    check(len(e5)==10 and sum(finite(csv_metrics(x)['Eff']) for x in e5)==3,'E5_three_of_ten')
    models=sorted(set(x['model'] for x in e5))
    complete=[set(x['question_id'] for x in e5 if x['model']==model and finite(csv_metrics(x)['Eff'])) for model in models]
    check(set.intersection(*complete)=={'22'},'E5_common_q22')
    e5means={model:{k:statistics.mean(csv_metrics(x)[k] for x in e5 if x['model']==model) for k in ['Com','Cor']} for model in models}
    check(same(e5means['openai_qwen3-14b']['Com'],.6266666666666667),'E5_all_five_Com_14b')
    check(same(e5means['openai_qwen3-32b']['Cor'],.75),'E5_all_five_Cor_32b')
    check(e5means[models[0]]['Com']>e5means[models[1]]['Com'] and e5means[models[0]]['Cor']<e5means[models[1]]['Cor'],'E5_opposite_known_axes')

    confirm=read(R3/'confirmation_readout_complete_01/per_answer.json')
    check(len(confirm)==8,'confirmation_eight')
    for x in confirm:
        for key in ['primary','secondary']:
            formula(x['anonymous_answer_id']+':'+key,x[key+'_metrics'])
            check(x[key+'_metrics']['s_time'] is None and x[key+'_metrics']['Eff'] is None,'confirmation_missing_time_and_eff:'+x['anonymous_answer_id']+':'+key)
    check(sum(finite(x['primary_metrics']['s_label']) for x in confirm)==3,'confirmation_primary_labels_three')
    check(sum(finite(x['secondary_metrics']['s_label']) for x in confirm)==2,'confirmation_secondary_labels_two')

    first=rows(OUT/'first_route_per_answer.csv')
    for x in first:formula('first:'+x['answer_id'],csv_metrics(x))
    check(len(first)==2,'first_two_answers')
    oldnew=read(R2/'first7_historical_availability_audit_v1/per_answer.json')
    check(len(oldnew)==7 and all(x['historical_complete_CCE'] and not x['current_complete_CCE'] for x in oldnew),'historical_same_seven_7_to_0_fw3')

    reconstruction=read(HERE/'llm_decomposition.json')
    for x in reconstruction['results']:
        binding(x['source_document']);binding(x['baseline_v7'])
        source=read(x['source_document']['path'])['text']
        check(hashlib.sha256(source.encode('utf-8')).hexdigest()==x['answer_sha256'],'reconstruction_answer:'+x['id'])
        for op in x['operations']:
            s=op['source'];check(source[s['start']:s['end']]==s['quote'],'reconstruction_span:'+x['id']+':'+str(s['line']))
        for point in x['endpoint_replays']:
            formula('new_decomposition:'+x['id']+':'+str(point['time_hours']),point['derived_metrics'])
            t=point['original_function_results']['time_computation']
            delta=max(t['min_hours']-point['time_hours'],point['time_hours']-t['max_hours'],0)
            tau=(.1 if point['time_hours']>t['max_hours'] else .2)*t['median_hours']
            expected=3*math.exp(-.5*(delta/tau)**2)
            check(same(expected,point['derived_metrics']['s_time']),'reconstruction_original_time_math:'+x['id']+':'+str(point['time_hours']))

    from markdown_it import MarkdownIt
    md=MarkdownIt('commonmark',{'html':False}).enable('table')
    links=[]
    pages=['REPORT_zh.md','LLM_DECOMPOSITION_zh.md','QUALITY_CHECK_zh.md']
    for filename in pages:
        path=HERE/filename;body=path.read_text(encoding='utf-8')
        check('\ufffd' not in body,'no_replacement_char:'+filename)
        for tok in md.parse(body):
            for child in tok.children or []:
                if child.type=='link_open':
                    href=child.attrGet('href');u=urlsplit(href)
                    if u.scheme in ['https','http']:continue
                    target=(HERE/unquote(u.path)).resolve()
                    check(target.is_file() or target in [HERE/'verification.json',HERE/'evidence.json'],'local_link:'+href)
                    links.append({'page':filename,'href':href,'target':str(target)})
                    if target.is_file() and HERE not in target.parents:bind(target)
        rendered=md.render(body)
        navigation=[]
        def heading(m):
            ident='section-'+str(len(navigation)+1)
            navigation.append((ident,re.sub('<[^>]+>','',m.group(2))))
            return '<h2 id="'+ident+'">'+m.group(2)+'</h2>'
        rendered=re.sub(r'(<h2>)(.*?)(</h2>)',heading,rendered)
        nav=''.join('<a href="#'+i+'">'+t+'</a>' for i,t in navigation)
        title='ClearEval 实验与评测报告' if filename=='REPORT_zh.md' else ('两份真实答案的大模型重新分解' if filename.startswith('LLM') else '核对范围与统计解释')
        css='''body{font:17px/1.85 "Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#172331;margin:0;background:#f6f8fa}main{max-width:1080px;margin:auto;padding:44px 52px;background:white}h1{font-size:30px;line-height:1.5}h2{font-size:23px;border-top:1px solid #dbe3ea;padding-top:30px;margin-top:44px}h3{font-size:20px;margin-top:32px}p{margin:16px 0}a{color:#175e9b;text-decoration:none}a:hover{text-decoration:underline}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.65;margin:24px 0}td,th{border:1px solid #d3dde7;padding:10px 12px;vertical-align:top}th{background:#eaf1f7;text-align:left}tr:nth-child(even){background:#f8fafc}pre{background:#f2f5f8;border:1px solid #dfe6ed;padding:18px;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 Consolas,monospace}code{font-family:Consolas,monospace;overflow-wrap:anywhere}nav{background:#eef4f8;padding:20px 25px;border-radius:6px;margin:25px 0}nav a{display:block;font-size:15px}strong{color:#183d59}@media(max-width:700px){main{padding:22px 16px}body{font-size:16px}table{display:block;overflow-x:auto}}@media print{body{background:white;font-size:11pt}main{padding:0;max-width:none}nav{display:none}h2,h3{break-after:avoid}tr{break-inside:avoid}pre{font-size:9pt}a{color:inherit}}'''
        document='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style></head><body><main><p><a href="REPORT_zh.html">项目报告</a> · <a href="LLM_DECOMPOSITION_zh.html">重新分解实证</a> · <a href="QUALITY_CHECK_zh.html">核对范围</a></p><nav>'+nav+'</nav>'+rendered+'</main></body></html>'
        (HERE/filename.replace('.md','.html')).write_text(document,encoding='utf-8')
    # Link/source checks are integrity checks, not scientific accuracy checks.
    for source in list(SOURCES.values()):
        check(sha(source['path'])==source['sha256'],'input_unchanged:'+source['path'])
    check(sha(ledger_path)==initial_ledger,'request_ledger_unchanged_during_report')
    data={'created_utc':datetime.now(timezone.utc).isoformat(), 'records':FORMULA_RECORDS,
        'latest_observations':obs,'E2_pairs':pairs,'E2_exact_resampling':{'task_deltas':ds,'ordered_means':exact,'decrease_count':26,'draws':27,'discrete_025_975':[q(.025),q(.975)]},
        'E5_five_task_known_means':e5means,'same_seven_old_new':oldnew,
        'new_decomposition':reconstruction,'source_bindings':list(SOURCES.values()),'local_links':links}
    (HERE/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verification={'status':'PASS','scope':'mechanical arithmetic, source identities, literal spans and report links; not scientific gold validation',
        'checks_passed':len(CHECKS),'checks_failed':0,'formula_record_count':len(FORMULA_RECORDS),
        'unique_bound_source_files':len(SOURCES),'local_link_occurrences':len(links),
        'new_local_or_API_model_calls':0,'new_expert_judgments':0,'current_assistant_source_readings':2,
        'ledger_sha256':initial_ledger,'statistical_fallacy_categories_reviewed':11,
        'checks':CHECKS,'report_artifacts':[bind(HERE/x) for x in pages+[x.replace('.md','.html') for x in pages]+['evidence.json','llm_decomposition.json','reconstruct_examples.py','verify_report.py']],
        'actual_command':[sys.executable,'-X','utf8',str(Path(__file__).resolve())]}
    (HERE/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:verification[k] for k in ['status','checks_passed','formula_record_count','unique_bound_source_files','local_link_occurrences','new_local_or_API_model_calls']},ensure_ascii=False))


if __name__=='__main__':main()
