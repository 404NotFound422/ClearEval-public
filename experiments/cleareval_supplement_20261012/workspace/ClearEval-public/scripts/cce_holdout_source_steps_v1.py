"""Offline anonymous holdout SR/SP only; prepare/run require explicit reference paths.

Uses unchanged cce_validation.score_steps and Encoder.score. Never imports a judge
driver, reads judge returns, or combines SR/SP with original score components.
Creation of this script does not authorize running the fixed heldout cases.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cce_validation as core

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/cce_validation'
CASES=ART/'judges/local_extraction_holdout_v1/sealed/cases.json'
SELECTION=ART/'human_review/selection.json'
DEST=ART/'holdout_source_steps_v1'
CACHE=ART/'embedding_cache'
MODEL=core.ASSETS/'assets/all-mpnet-base-v2'
THRESHOLDS=(0.6,0.7,0.8)
VERSION='holdout-source-steps-v1'
sha=core.filehash
read=core.read
write=core.write

def check(ok,message):
    if not ok: raise ValueError(message)

def package_versions():
    return {k:importlib.metadata.version(k) for k in ['numpy','torch','sentence-transformers','transformers','tokenizers']}

def validate_cases(payload):
    """Only anonymous question + original answer fields leave this boundary."""
    cases=payload['cases']
    check(len(cases)==15,'The original fixed 15 cases are required; no subsetting.')
    normalized=[]
    for c in cases:
        aid=c['anonymous_answer_id']
        check(re.fullmatch(r'A\d{2}',aid) is not None,'Non-anonymous answer identity.')
        check(c['split']=='audit_holdout' and c['condition']=='baseline','Only original holdout baseline cases accepted.')
        check(isinstance(c['specific_question'],str) and isinstance(c['model_response'],str),'Full original texts required.')
        check(core.digest(c['specific_question'])==c['question_sha256'],'Question hash mismatch.')
        check(core.digest(c['model_response'])==c['answer_sha256'],'Answer hash mismatch.')
        normalized.append({k:c[k] for k in ['anonymous_answer_id','case_id','question_id','specific_question','model_response','answer_sha256','question_sha256']})
    check(len({c['anonymous_answer_id'] for c in normalized})==15,'Duplicate anonymous identity.')
    return normalized

def source_path(p):
    p=Path(p);p=(ROOT/p).resolve() if not p.is_absolute() else p.resolve()
    # A reference must not cause discovery of arbitrary judge/score/credential files.
    parts=[x.lower() for x in p.parts]
    check('judges' not in parts,'Judge directories are not valid source documents.')
    check(not any(x in parts for x in ['.git','.aws','.codex','.agents']),'Protected metadata is not a source.')
    check(p.is_relative_to(ROOT) or p.is_relative_to(ROOT.parent/'literature'),'Reference source outside the project/literature roots.')
    check(p.is_file(),'Missing source file: '+str(p))
    return p

def validate_references(payload,cases):
    refs=payload['references'];check(isinstance(refs,list),'references must be a list.')
    qids={int(c['question_id']) for c in cases}
    ids=[]
    for r in refs:
        for k in ['reference_id','route_id','question_ids','steps','status','source_path','family_id']:
            check(k in r,'Missing core reference field: '+k)
        check(r['steps'] and isinstance(r['steps'],list),'An empty/partial route must not be presented as a complete step reference.')
        check(r['question_ids'] and all(isinstance(q,int) and q in qids for q in r['question_ids']),'Reference bindings must be explicit fixed holdout qids only.')
        for s in r['steps']:
            check(isinstance(s,str) and bool(s.strip()) or isinstance(s,dict) and isinstance(s.get('text'),str) and bool(s['text'].strip()),'Invalid source step text.')
        source_path(r['source_path']);ids.append(r['reference_id'])
    check(len(ids)==len(set(ids)),'Duplicate reference ID.')
    return refs

def verify_files(hashes):
    for p,h in hashes.items(): check(Path(p).is_file() and sha(p)==h,'Frozen input/output drift: '+p)

def prepare(args):
    # root must explicitly select the reviewed candidate file and supporting manifests.
    refs_path=source_path(args.references)
    manifests=[source_path(p) for p in args.source_manifest]
    check(not (DEST/'run.json').exists(),'A completed immutable run already exists.')
    if (DEST/'plan.json').exists():
        old=read(DEST/'plan.json');verify_files(old['input_sha256'])
        check(old['references_path']==str(refs_path),'Existing plan reference path differs.')
        check(old['source_manifests']==[str(p) for p in manifests],'Existing plan source manifests differ.')
        check(old['runtime_packages']==package_versions(),'Runtime package drift.')
        print('Existing unchanged preparation reused; no case scoring or embeddings.');return
    cases=validate_cases(read(CASES));refs=validate_references(read(refs_path),cases)
    check(MODEL.is_dir(),'Preinstalled local encoder missing; no download permitted.')
    weights=MODEL/'model.safetensors'
    if not weights.exists():weights=MODEL/'pytorch_model.bin'
    check(weights.is_file(),'Preinstalled model weights missing.')
    cfg=read(MODEL/'sentence_bert_config.json')
    identity={'model':'all-mpnet-base-v2','weights_sha256':sha(weights),'max_seq_length':cfg['max_seq_length']}
    cache_files=sorted(CACHE.glob('*.npy'))
    files=[Path(__file__),ROOT/'scripts/cce_validation.py',ROOT/'results/oeq_metrics.py',CASES,SELECTION,refs_path,*manifests]
    files += [source_path(r['source_path']) for r in refs]
    files += sorted(p for p in MODEL.rglob('*') if p.is_file())
    files += cache_files
    hashes={str(p.resolve()):sha(p) for p in dict.fromkeys(files)}
    plan={'schema':VERSION,'status':'prepared_not_scored','created_utc':datetime.now(timezone.utc).isoformat(),
      'cases_path':str(CASES),'references_path':str(refs_path),'source_manifests':[str(p) for p in manifests],
      'anonymous_case_order':[c['anonymous_answer_id'] for c in cases],
      'case_identities':[{k:c[k] for k in ['anonymous_answer_id','case_id','question_id','answer_sha256','question_sha256']} for c in cases],
      'thresholds':list(THRESHOLDS),'core_version':core.VERSION,'encoder_identity':identity,
      'runtime_packages':package_versions(),'reference_ids':[r['reference_id'] for r in refs],
      'reference_digest':core.digest(refs),'input_sha256':hashes,
      'read_only_cache':str(CACHE),'frozen_existing_cache_sha256':{str(p.resolve()):sha(p) for p in cache_files},
      'local_write_cache':str(DEST/'embedding_cache'),
      'reference_acceptance':'Explicit root-supplied file after source review; passing structural checks is not scientific validation.',
      'rules':'Unchanged core.score_steps, full original answer, no filtering/translation/manual step replacement; all 15 at all three thresholds.',
      'selection_policy':'Original sealed cases order/identities retained; no original judge output, scores or extraction read; no reference selection based on scores.',
      'cache_policy':'Only frozen original cache files may be reused; missing vectors from preinstalled local MPNet are written only to this new directory. No download.',
      'source_family_independence':'not established; post-freeze source preparation and prior catalog exposure retained',
      'formal_eligible':False,'expert_confirmed':False,'new_judge_requests':0,'new_embeddings_during_prepare':0,
      'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd())}
    write(DEST/'plan.json',plan)
    print(json.dumps({'status':'prepared_not_scored','answers':15,'references':len(refs),'plan_sha256':sha(DEST/'plan.json'),'new_judge_requests':0}))

class LocalEncoder(core.Encoder):
    """Inherits score unchanged; lazy offline model and a separate write cache."""
    def __init__(self,plan):
        for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='2'
        for k in ['HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY']:os.environ[k]='1'
        import numpy as np
        self.np=np;self.model=None;self.identity=plan['encoder_identity']
        self.frozen=plan['frozen_existing_cache_sha256'];self.cache=DEST/'embedding_cache'
        self.memo={};self.access=[];self.new=[]
        self.cache_manifest_path=DEST/'local_cache_manifest.json'
        self.local=read(self.cache_manifest_path) if self.cache_manifest_path.exists() else {}
    def ensure_model(self):
        if self.model is not None:return
        for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='2'
        for k in ['HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY']:os.environ[k]='1'
        import torch
        torch.set_num_threads(2)
        import torch._library.utils
        torch._library.utils.get_source=lambda stacklevel:'cce-local-encoder:0'
        from sentence_transformers import SentenceTransformer
        self.model=SentenceTransformer(str(MODEL),device='cpu',local_files_only=True)
        check(self.model.max_seq_length==self.identity['max_seq_length'],'Encoder maximum sequence length changed.')
    def encode(self,texts):
        self.ensure_model();vectors=[]
        for text in texts:
            key=core.digest([self.identity,text])+'.npy'
            if key not in self.memo:
                original=(CACHE/key).resolve();local=self.cache/key
                if str(original) in self.frozen:
                    check(sha(original)==self.frozen[str(original)],'Original cache vector drift.')
                    path=original;origin='reused_frozen_original';vec=self.np.load(path,allow_pickle=False)
                elif key in self.local:
                    m=self.local[key]
                    check(m['encoder_identity']==self.identity and m['text_sha256']==core.digest(text),'Local cache identity mismatch.')
                    check(local.exists() and sha(local)==m['sha256'],'Local cache vector drift.')
                    path=local;origin='reused_prior_local_inference';vec=self.np.load(path,allow_pickle=False)
                else:
                    check(not local.exists(),'Untracked vector in new cache; refuse to silently reuse or overwrite.')
                    self.cache.mkdir(parents=True,exist_ok=True)
                    vec=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                    path=local;self.np.save(path,vec);origin='new_local_inference';self.new.append(str(path))
                    self.local[key]={'sha256':sha(path),'text_sha256':core.digest(text),'encoder_identity':self.identity}
                    write(self.cache_manifest_path,self.local)
                check(vec.shape==(768,) and self.np.isfinite(vec).all(),'Invalid embedding vector.')
                self.memo[key]=vec
                self.access.append({'path':str(path),'sha256':sha(path),'text_sha256':core.digest(text),'origin':origin})
            vectors.append(self.memo[key])
        return self.np.asarray(vectors)

def score_all(cases,refs,encoder,plan_digest):
    """Pure original-core scoring over fixed texts; usable with synthetic fixtures."""
    rows=[];details=[];review=[]
    for threshold in THRESHOLDS:
        for c in cases:
            answer={k:c[k] for k in ['question_id','specific_question','model_response']}
            step=core.score_steps(answer,refs,encoder,threshold)
            check(step['generated_steps']==core.segment(c['model_response']),'Unexpected parser modification.')
            identity={k:c[k] for k in ['anonymous_answer_id','case_id','question_id','answer_sha256','question_sha256']}
            rows.append({**identity,'threshold':threshold,'sr':step['sr'],'sp':step['sp'],
              'route_id':step['route_id'],'reference_id':step['reference_id'],
              'reference_n':step.get('reference_n'),'generated_n':step.get('generated_n',len(step['generated_steps'])),
              'step_missing_reason':step['step_missing_reason'],'source_family_id':step.get('family_id'),
              'source_path':step.get('source_path'),'source_url':step.get('source_url'),
              'plan_sha256':plan_digest,'formal_eligible':False,'expert_confirmed':False})
            details.append({**identity,'threshold':threshold,'step_result':step,'formal_eligible':False})
            if threshold==0.7:
                ref=next((r for r in refs if r['reference_id']==step['reference_id']),None)
                review.append({'anonymous_answer_id':c['anonymous_answer_id'],'question_id':c['question_id'],
                  'specific_question':c['specific_question'],'reference_id':step['reference_id'],
                  'source_path':step.get('source_path'),'source_url':step.get('source_url'),
                  'source_scope_conditions':{k:v for k,v in ref.items() if any(term in k.lower() for term in ['condition','scope','eligib','limitation','assumption','initial','label','applicab'])} if ref else None,
                  'generated_steps':step['generated_steps'],
                  'automatic_candidate_pairs':[{'reference_index':m['reference_index'],'reference_text':m['reference_text'],
                    'generated_index':m['generated_index'],'generated_text':m['generated_text'],
                    'expert_match_decision':'','expert_note':''} for m in step.get('matches',[])],
                  'reference_absence_reason':step['step_missing_reason'],'expert_reference_applicability':'','expert_note':'',
                  'notice':'Automated candidate attachment; no expert decisions prefilled. No model identity, aggregate metric, similarity value or correctness inference displayed.'})
    check(len(rows)==45 and len(details)==45 and len(review)==15,'Incomplete fixed 15 x 3 batch.')
    return rows,details,review

def run(args):
    plan=read(DEST/'plan.json');verify_files(plan['input_sha256'])
    check(plan['thresholds']==list(THRESHOLDS) and plan['core_version']==core.VERSION,'Frozen configuration mismatch.')
    check(plan['runtime_packages']==package_versions(),'Runtime package drift.')
    if (DEST/'run.json').exists():
        old=read(DEST/'run.json');check(old['plan_sha256']==sha(DEST/'plan.json'),'Completed run plan drift.')
        verify_files(old['output_sha256']);verify_files(old['used_vector_sha256'])
        print('Verified unchanged completed anonymous step run; no new inference.');return
    cases=validate_cases(read(CASES));refs=validate_references(read(plan['references_path']),cases)
    check([c['anonymous_answer_id'] for c in cases]==plan['anonymous_case_order'],'Case order drift.')
    check(core.digest(refs)==plan['reference_digest'],'Reference pool drift.')
    encoder=LocalEncoder(plan);rows,details,review=score_all(cases,refs,encoder,sha(DEST/'plan.json'))
    verify_files(plan['input_sha256'])
    outputs=[]
    for t in THRESHOLDS:
        tag=f't{round(t*100):03d}'
        rr=[r for r in rows if r['threshold']==t]
        for ext in ['json','csv']:
            path=DEST/f'{tag}_per_answer.{ext}'
            if ext=='json':write(path,rr)
            else:core.table(path,rr)
            outputs.append(path)
        path=DEST/f'{tag}_matches.json';write(path,[r for r in details if r['threshold']==t]);outputs.append(path)
        path=DEST/f'{tag}_resolved_config.json'
        write(path,{'threshold':t,'core_version':core.VERSION,'core_sha256':sha(ROOT/'scripts/cce_validation.py'),
          'encoder_identity':encoder.identity,'plan_sha256':sha(DEST/'plan.json'),
          'references_sha256':sha(plan['references_path']),'formal_eligible':False,'metric_scope':'SR/SP only; full original answer parsing; no original score components'});outputs.append(path)
    path=DEST/'reviewer/candidate_pairs.json';write(path,review);outputs.append(path)
    path=DEST/'reviewer/README.md';path.write_text('自动步骤匹配候选附件，供同一专家审阅；未填入专家结论。源参考条件仍待确认。附件隐藏模型元数据、SR/SP 总分、相似度和机器匹配判定；原固定 15 份答卷及人审入口未更改。没有原始 Correctness、EGES 或参数评分。\n',encoding='utf-8');outputs.append(path)
    path=DEST/'embedding_access.json';write(path,encoder.access);outputs.append(path)
    if encoder.cache_manifest_path.exists():outputs.append(encoder.cache_manifest_path)
    path=DEST/'source_manifest.json';write(path,{'reference_file':{'path':plan['references_path'],'sha256':sha(plan['references_path'])},
      'supporting_manifests':[{'path':p,'sha256':sha(p)} for p in plan['source_manifests']],
      'references':[{'reference_id':r['reference_id'],'question_ids':r['question_ids'],'route_id':r['route_id'],'family_id':r['family_id'],
        'source_path':str(source_path(r['source_path'])),'source_sha256':sha(source_path(r['source_path'])),'source_url':r.get('source_url'),
        'formal_eligible':False} for r in refs]});outputs.append(path)
    counts={str(t):{'answers':15,'numeric':sum(r['sr'] is not None for r in rows if r['threshold']==t),'reference_NA':sum(r['step_missing_reason']=='reference_insufficient' for r in rows if r['threshold']==t)} for t in THRESHOLDS}
    primary=[r for r in rows if r['threshold']==0.7]
    summary={'status':'completed_provisional_source_step_matching','actual_answers':15,'thresholds':list(THRESHOLDS),
      'numeric_steps_primary':sum(r['sr'] is not None for r in primary),
      'reference_insufficient_primary':sum(r['step_missing_reason']=='reference_insufficient' for r in primary),
      'evaluator_failure_primary':sum(r['step_missing_reason']=='evaluator_failure' for r in primary),
      'reference_ids':sorted({r['reference_id'] for r in refs}),
      'family_ids':sorted({r['family_id'] for r in refs}),
      'selected_reference_ids_primary':sorted({r['reference_id'] for r in primary if r['reference_id'] is not None}),
      'selected_family_ids_primary':sorted({r['source_family_id'] for r in primary if r['source_family_id'] is not None}),
      'new_embeddings':len(encoder.new),'reused_embeddings':sum(x['origin']!='new_local_inference' for x in encoder.access),
      'new_model_requests':0,'new_local_embedding_inferences':len(encoder.new),
      'complete_CCE_added':0,'expert_returns':0,'formal_eligible':0,
      'plan_sha256':sha(DEST/'plan.json'),'threshold_counts':counts,
      'meaning':'Automatic SR/SP only. Offline embedding inferences counted separately from judge/generation requests. Does not add complete CCE or establish scientific eligibility/independent source holdout.'}
    path=DEST/'summary.json';write(path,summary);outputs.append(path)
    run_record={'status':'completed_provisional_source_step_matching','created_utc':datetime.now(timezone.utc).isoformat(),
      'plan_sha256':sha(DEST/'plan.json'),'threshold_counts':counts,'answers':15,'actual_core_calls':45,
      'new_judge_requests':0,'new_local_vectors_this_run':len(encoder.new),
      'unique_vectors_used':len(encoder.access),'reused_frozen_original_vectors':sum(x['origin']=='reused_frozen_original' for x in encoder.access),
      'reused_prior_local_vectors':sum(x['origin']=='reused_prior_local_inference' for x in encoder.access),
      'used_vector_sha256':{x['path']:x['sha256'] for x in encoder.access},
      'output_sha256':{str(p):sha(p) for p in outputs},'formal_eligible':False,'expert_labels_added':0,
      'heldout_judge_or_scientific_scores_read':0,'archive_model_metadata_read':0,
      'selection_and_expert_forms_unchanged':True,'cparam_correctness_EGES_combinations':'not read or calculated',
      'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd()),'summary_sha256':sha(DEST/'summary.json')}
    write(DEST/'run.json',run_record)
    print(json.dumps({'status':run_record['status'],'answers':15,'threshold_counts':counts,
      'new_judge_requests':0,'new_local_vectors_this_run':len(encoder.new)}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare',help='Freeze only after root approves exact source references.')
    p.add_argument('--references',required=True,type=Path)
    p.add_argument('--source-manifest',required=True,type=Path,action='append')
    p.set_defaults(func=prepare)
    r=sub.add_parser('run',help='Execute the pre-approved immutable plan offline.')
    r.set_defaults(func=run)
    args=parser.parse_args();args.func(args)

if __name__=='__main__':main()
