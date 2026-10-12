"""Source-bound, nullable CCE adapter. Archived scores remain explicitly historical.

Run with the existing portable Python from the repository working directory.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from results.oeq_metrics import METRIC_BLOCKS, MAX_SCORES, protocol_scores

OUT = ROOT / 'artifacts/cce_validation'
ASSETS = ROOT.parent / 'review_artifacts/bioprobench_2026-09-29'
VERSION = 'cce-r2-source-bound-v3-unicode-headers'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def digest(value):
    payload=value if isinstance(value,str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def filehash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def table(path, rows, fields=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v for k,v in row.items() if k in fields})

def mean(values):
    return math.fsum(values) / len(values) if values else None

def partial_scores(item):
    """Original scales/normalizations, preserving each known component."""
    ev = item.get('evaluation', {})
    scores = ev.get('scores', ev.get('legacy_diagnostics', {}).get('scores', {}))
    raw, reasons = {}, {}
    for block, metrics in METRIC_BLOCKS.items():
        for key, maximum in metrics.items():
            value = scores.get(block, {}).get(key, {}).get('score')
            if isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and (-maximum if key=='s_method' else 0) <= value <= maximum:
                raw[key] = float(value)
            else:
                raw[key] = None; reasons[key] = 'evaluator_failure'
    norm = {k: ((v/2.5+1)/2 if k=='s_method' else v/MAX_SCORES[k]) if v is not None else None for k,v in raw.items()}
    out = dict(raw)
    for dimension, block in [('Cor','correctness'),('Eff','effectiveness')]:
        vals = [norm[k] for k in METRIC_BLOCKS[block]]
        out[dimension] = mean(vals) if all(v is not None for v in vals) else None
    out['historical_Com'] = .4*norm['c_step']+.6*norm['c_param'] if norm['c_step'] is not None and norm['c_param'] is not None else None
    out['score_missing_reasons'] = reasons
    return out

def segment(text):
    """Fixed line-based operations with continuation parameters; exclude pure headings.

    No translated/rewritten text is fed to the encoder. Source offsets are kept.
    """
    result=[]; offset=0; started=False
    lines=text.splitlines(keepends=True)
    has_protocol=any(re.search(r'protocol\s+steps', x, re.I) for x in lines)
    for line in lines:
        start=offset; offset+=len(line)
        clean=line.strip().replace('**','').replace('__','')
        if re.search(r'^protocol\s+steps\s*[:：]', clean, re.I):
            started=True; continue
        if has_protocol and not started: continue
        if not clean or clean.startswith('```'): continue
        if re.match(r'^(chosen\s+(method|labeling)|justification|rationale)\s*:',clean,re.I): continue
        leaf_number=bool(re.match(r'^\s*\d+\.\d+(?:\.\d+)*[.)]?\s+',clean))
        clean=re.sub(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s+|[-*•]\s+|#+\s*)','',clean)
        if not clean: continue
        # A parameter-only continuation belongs to its preceding operation.
        if result and re.match(r'^[([]?\s*(?:Temperature|Time|Duration|温度|时间)\s*[:：]',clean,re.I):
            result[-1]['text']+=' '+clean; result[-1]['end']=offset
            continue
        # Titles have neither an operation predicate nor bound parameter content.
        operation=bool(re.search(r'\b(incubat\w*|wash\w*|rins\w*|transfer\w*|immerse\w*|place|store\w*|dehydrat\w*|clear\w*|mount\w*|equilibrat\w*|stain\w*|permeabili\w*|block\w*|replace\w*|repeat\w*|add|keep|prepare\w*|image|imaging|soak\w*)\b|孵育|浸泡|洗涤|清洗|漂洗|转移|置于|保存|更换|混合|加入|脱水|脱脂|透化|渗透|封闭|染色|温育|置换|平衡|封片',clean,re.I))
        parameters=bool(re.search(r'\d\s*(?:%|hours?\b|hrs?\b|min\b|days?\b|°|℃|degrees|mL\b|µ|μ|小时|分钟|天)|Temperature:|Time:',clean,re.I))
        imperative=bool(re.match(r'^(?:Incubate|Wash|Rinse|Transfer|Immerse|Place|Store|Mount|Equilibrate|Stain|Replace|Repeat|Add|Keep|Soak)\b|^(?:将|用|置于|转移|更换)',clean,re.I))
        heading=(len(clean.split())<9 and len(re.findall('[\u4e00-\u9fff]',clean))<20 and not parameters and not imperative and not leaf_number and not re.search(r'[.;。]',clean))
        if heading: continue
        if operation or leaf_number or parameters:
            result.append({'text':clean,'start':start,'end':offset})
        elif result and (parameters or line[:1].isspace()):
            result[-1]['text']+=' '+clean; result[-1]['end']=offset
    return result

def selected_route(text, references):
    m=re.search(r'^\s*(?:\*\*)?Chosen\s+Method:\s*(?:\*\*)?\s*([^\r\n]+)',text,re.M|re.I)
    route_text=m.group(1).replace('**','').strip() if m else text[:500]
    found=[]
    for ref in references:
        if any(re.search(r'(?<![a-zA-Z])'+re.escape(alias)+r'(?![a-zA-Z])',route_text,re.I) for alias in ref.get('route_aliases',[ref['route_id']])):
            found.append(ref['route_id'])
    routes=sorted(set(found))
    return (routes[0] if len(routes)==1 else None), route_text

class Encoder:
    def __init__(self):
        for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']: os.environ[k]='2'
        os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
        os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
        import torch
        torch.set_num_threads(2)
        import torch._library.utils
        torch._library.utils.get_source=lambda stacklevel:'cce-local-encoder:0'
        import numpy as np
        from sentence_transformers import SentenceTransformer
        self.np=np
        self.model=SentenceTransformer(str(ASSETS/'assets/all-mpnet-base-v2'),device='cpu')
        self.identity={'model':'all-mpnet-base-v2','weights_sha256':filehash(ASSETS/'assets/all-mpnet-base-v2/model.safetensors') if (ASSETS/'assets/all-mpnet-base-v2/model.safetensors').exists() else filehash(ASSETS/'assets/all-mpnet-base-v2/pytorch_model.bin'),'max_seq_length':self.model.max_seq_length}
        self.cache=OUT/'embedding_cache'; self.cache.mkdir(parents=True,exist_ok=True)
    def encode(self,texts):
        vectors=[]
        for text in texts:
            path=self.cache/(digest([self.identity,text])+'.npy')
            if path.exists(): vec=self.np.load(path)
            else:
                vec=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                self.np.save(path,vec)
            vectors.append(vec)
        return self.np.asarray(vectors)
    def score(self,ref,steps,threshold):
        rt=[s['text'] if isinstance(s,dict) else s for s in ref['steps']]
        gt=[s['text'] for s in steps]
        if not rt: raise ValueError('Empty reference is not a complete route')
        if not gt: return {'sr':0.,'sp':0.,'matches':[],'reference_n':len(rt),'generated_n':0}
        similarities=self.encode(rt) @ self.encode(gt).T
        rmax=similarities.max(axis=1); gmax=similarities.max(axis=0)
        return {'sr':float((rmax>=threshold).mean()),'sp':float((gmax>=threshold).mean()),'reference_n':len(rt),'generated_n':len(gt),
                'matches':[{'reference_index':i,'reference_text':t,'generated_index':int(similarities[i].argmax()),'generated_text':gt[int(similarities[i].argmax())],'similarity':float(rmax[i]),'matched':bool(rmax[i]>=threshold)} for i,t in enumerate(rt)],
                'generated_max_similarity':[float(x) for x in gmax],
                'reference_truncated':sum(len(self.model.tokenizer.encode(t))>self.model.max_seq_length for t in rt),
                'generated_truncated':sum(len(self.model.tokenizer.encode(t))>self.model.max_seq_length for t in gt),
                'generated_cjk_steps':sum(bool(re.search('[\u4e00-\u9fff]',t)) for t in gt)}

def score_steps(answer, references, encoder, threshold=.7):
    text=answer['model_response']; qid=int(answer['question_id'])
    route,declared=selected_route(text,references)
    steps=segment(text)
    compatible=[r for r in references if qid in r['question_ids'] and r['route_id']==route]
    base={'route_id':route,'declared_route':declared,'generated_steps':steps,'reference_id':None,'sr':None,'sp':None,'step_missing_reason':None}
    if not steps and re.search(r'\d+\.\d+\s|Temperature:|Time:|孵育|洗涤|转移|置于',text):
        base['step_missing_reason']='evaluator_failure';base['parser_status']='operation_text_present_but_unparsed';return base
    if not compatible:
        base['step_missing_reason']='reference_insufficient'; return base
    candidates=[(encoder.score(r,steps,threshold),r,i) for i,r in enumerate(compatible)]
    scored,ref,_=max(candidates,key=lambda x:(x[0]['sr'],x[0]['sp'],-x[2]))
    return {**base,**scored,'reference_id':ref['reference_id'],'reference_status':ref['status'],'source_path':ref['source_path'],'source_url':ref.get('source_url'),'family_id':ref['family_id'],
            'candidate_reference_ids':[r['reference_id'] for r in compatible]}

def build_row(model,answer,score,step,answer_path,score_path,threshold,config_hash):
    numbers=partial_scores(score)
    meta=score.get('evaluation',{}).get('meta_data',{})
    stem_match=meta.get('sample_info')==answer['specific_question']
    unbound=None
    if not stem_match:
        unbound=dict(numbers)
        numbers={k:None for k in numbers}
        numbers['score_missing_reasons']={k:'evaluator_failure:score_input_identity_unmatched' for k in MAX_SCORES}
    com=.4*step['sr']+.6*numbers['c_param']/3 if step['sr'] is not None and numbers['c_param'] is not None else None
    dims=[com,numbers['Cor'],numbers['Eff']]
    full=all(v is not None for v in dims)
    return {'answer_id':model+'__q'+str(answer['question_id']),'model':model,'question_id':answer['question_id'],'generation_condition':'1-shot',
        'answer_sha256':digest(answer['model_response']),'question_sha256':digest(answer['specific_question']),
        'answer_source':str(answer_path),'score_source':str(score_path),'score_stem_matches':stem_match,
        'historical_score_binding':'filename_model_qid_exact_stem_no_answer_hash' if stem_match else 'unmatched_or_missing',
        'unbound_historical_scores':unbound,
        'reference_id':step.get('reference_id'),'reference_status':step.get('reference_status'),'source_path':step.get('source_path'),'source_url':step.get('source_url'),
        'family_id':step.get('family_id','question_'+str(answer['question_id'])),'route_id':step.get('route_id'),
        'sr':step['sr'],'sp':step['sp'],**numbers,'Com':com,'IA':min(dims) if full else None,'HV':math.prod(dims) if full else None,
        'threshold':threshold,'config_hash':config_hash,'step_missing_reason':step.get('step_missing_reason'),
        'numeric_scope':'development_provisional_archive_linked','formal_eligible':False,
        'limitation':'Reference applicability awaits review; archive evaluator/evidence/settings and answer hash are not fully recovered.'}

def freeze(references):
    import yaml
    config=yaml.safe_load((ROOT.parent/'ClearEval_Codex_Experiments_v1_20261008/experiment_config.yaml').read_text(encoding='utf-8'))
    paths=sorted((ROOT/'dataset/Q+AR/model_response').glob('from_*_1-shot.json'))
    models=[p.name[len('from_'):-len('_1-shot.json')] for p in paths]
    config['cohort']['resolved_generator_models']=models
    config['completeness'].update(primary_encoder='sentence-transformers/all-mpnet-base-v2',primary_threshold=.7,primary_configuration_status='frozen_development_baseline_pending_expert_validation')
    config['inputs']['complete_reference_manifest']=str(OUT/'reference_recovery/references.json')
    config['resolved']={'adapter_version':VERSION,'adapter_sha256':filehash(__file__),'reference_digest':digest(references),'generation_question_snapshot':'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json','historical_scores_scope':'descriptive_archive_only_without_complete_evaluator_provenance','formal_eligible':False}
    (OUT/'resolved_config.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding='utf-8')
    write(OUT/'cohort_frozen.json',{'models':models,'condition':'1-shot','selection':'all identifiable exact 1-shot archives, no score-dependent exclusion','input_files':{str(p.relative_to(ROOT)):filehash(p) for p in paths}})
    return config,paths

def score_command(args):
    refs=read(args.references)['references']
    OUT.mkdir(parents=True,exist_ok=True)
    config,paths=freeze(refs)
    run_config={**config,'run_setting':{'actual_threshold':args.threshold,'segmentation_version':VERSION,'hash_algorithm':'raw-utf8-sha256 for text; sorted canonical JSON otherwise'}}
    config_hash=digest(run_config)
    qids=set(args.qids or sorted({q for r in refs for q in r['question_ids']}))
    encoder=Encoder(); rows=[];details=[]
    for path in paths:
        model=path.name[len('from_'):-len('_1-shot.json')]
        if args.models and model not in args.models:continue
        sp=ROOT/'dataset/Q+AR/result'/('evaluation_results_'+model+'_1-shot.json')
        scores={str(r['question_id']):r for r in read(sp)} if sp.exists() else {}
        for answer in read(path):
            if answer['question_id'] not in qids: continue
            result=score_steps(answer,refs,encoder,args.threshold)
            row=build_row(model,answer,scores.get(str(answer['question_id']),{}),result,path,sp,args.threshold,config_hash)
            rows.append(row);details.append({'answer_id':row['answer_id'],**result})
            print(json.dumps({k:row[k] for k in ['answer_id','reference_id','sr','sp','Com','Cor','Eff','IA','HV']},ensure_ascii=True),flush=True)
    tag=args.tag
    write(OUT/(tag+'_resolved_config.json'),run_config)
    write(OUT/(tag+'_references.json'),{'references':refs})
    table(OUT/(tag+'_per_answer.csv'),rows);write(OUT/(tag+'_per_answer.json'),rows)
    write(OUT/(tag+'_step_matches.json'),details)
    write(OUT/(tag+'_run.json'),{'config_hash':config_hash,'encoder':encoder.identity,'answer_n':len(rows),'tasks':sorted(qids),'models':sorted({r['model'] for r in rows}),'step_scored':sum(r['sr'] is not None for r in rows),'new_api_calls':0,'scope':'development_provisional_archive_linked'})

def check_command(args):
    import numpy as np
    # Independent reference formula implementation equality on archived complete rows.
    checked=0
    for p in sorted((ROOT/'dataset/Q+AR/result').glob('evaluation_results_*_1-shot.json')):
        for item in read(p):
            try: old=protocol_scores(item)
            except ValueError:continue
            new=partial_scores(item)
            assert abs(old['Cor']-new['Cor'])<1e-12 and abs(old['Eff']-new['Eff'])<1e-12
            checked+=1
    assert partial_scores({'evaluation':{'scores':{'correctness':{'co_chem':{'score':1}}}}})['co_chem']==1
    assert partial_scores({})['Cor'] is None
    parsed=segment('**Chosen Method:** FDISCO\n**Protocol Steps:**\n1 Dehydration\n1.1 Incubate tissue in 50% THF for 12 hours.\n')
    assert len(parsed)==1 and parsed[0]['text']=='Incubate tissue in 50% THF for 12 hours.'
    assert len(segment('1.1 Wash sample in buffer.\nTemperature: 4 degrees C, Time: 2 hours\n'))==1
    assert len(segment('1.1 将样本置于缓冲液中清洗。(Temperature: 4 ℃, Time: 1 hour)\n'))==1
    assert segment('**Protocol Steps：**\n1.1 Apply fixture operation.\n')==segment('**Protocol Steps:**\n1.1 Apply fixture operation.\n')
    mismatch=build_row('test',{'question_id':1,'specific_question':'A','model_response':''},{'evaluation':{'meta_data':{'sample_info':'B'},'scores':{}}},{'sr':1.,'sp':1.},'a','b',.7,'config')
    assert mismatch['Cor'] is None and mismatch['Eff'] is None and mismatch['IA'] is None
    # SR/SP match the original BioProBench function body on deterministic matrices.
    source=ASSETS/'upstream/Metrics/GEN.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compute_step_recall_and_redundancy')
    from sklearn.metrics.pairwise import cosine_similarity
    class Lookup:
        def encode(self,x):return np.asarray(x,dtype=float)
    env={'EMBEDDING_MODEL':Lookup(),'SIMILARITY_THRESHOLD':.7,'cosine_similarity':cosine_similarity}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),env)
    r=[[1,0],[0,1]];g=[[1,0],[.9,.1],[-1,0]]
    sr,sp=env[fn.name](r,g); assert sr==.5 and abs(sp-2/3)<1e-12
    assert min([.2,.8,.9])==.2 and abs(math.prod([.2,.8,.9])-.144)<1e-12
    write(OUT/'implementation_checks.json',{'scope':'implementation_only_not_scientific_validation','archived_formula_equal_rows':checked,'bioprobench_function_sha256':digest(ast.unparse(fn)),'sr_sp_original_function_match':True,'nullable_component_preservation':True})
    print('Implementation checks passed; archived formula rows:',checked)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    score=sub.add_parser('score');score.add_argument('--references',default=str(OUT/'reference_recovery/references.json'));score.add_argument('--qids',nargs='+',type=int);score.add_argument('--models',nargs='+');score.add_argument('--threshold',type=float,default=.7);score.add_argument('--tag',default='pilot');score.set_defaults(func=score_command)
    check=sub.add_parser('check');check.set_defaults(func=check_command)
    args=parser.parse_args();args.func(args)

if __name__=='__main__':main()
