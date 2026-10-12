"""Reuse verified deterministic SR/SP for the original dev5 and E2 21 only.

No judge, encoder, embedding, confirmation input or human return is accessed.
References and hashes retain each case's original supplied reference context.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import socket
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_validation as core
import cce_analyze_grounded_stability_dev_v1 as original

ART=ROOT/'artifacts/cce_validation'
OLD=ART/'optimizer_20261010'
OUT=ART/'optimizer_round2_20261010/step_inputs_v1'
DEV_CASES=OLD/'grounded_development_v7/cases.json'
E2=OLD/'grounded_controls_v1'
BOUND={}


def deny(*args,**kwargs):raise RuntimeError('NO_NETWORK_JUDGE_OR_ENCODER_ALLOWED')
socket.create_connection=deny
socket.socket.connect=deny
core.Encoder.__init__=deny
j.runtime=deny
def rawsha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def bind(p):
    p=Path(p).resolve();b={'path':str(p),'sha256':j.filehash(p)};BOUND[str(p)]=b;return b
def read(p):bind(p);return j.read(p)
def verify(b):
    assert j.filehash(b['path'])==b['sha256'],'CHANGED_SOURCE:'+b['path']
    BOUND[str(Path(b['path']).resolve())]=b
def same(a,b):return a is None and b is None or isinstance(a,(int,float)) and isinstance(b,(int,float)) and abs(a-b)<=1e-12
def refs_rows(obj):return obj['references'] if isinstance(obj,dict) else obj
def output(p,obj):
    with p.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def validate_step(case,step):
    answer_hash=rawsha(case['model_response']);question_hash=rawsha(case['specific_question'])
    assert case.get('answer_sha256',answer_hash)==answer_hash
    assert case.get('question_sha256',question_hash)==question_hash
    generated=core.segment(case['model_response'])
    assert generated==step['generated_steps'],'FULL_TEXT_SEGMENTATION_CHANGED'
    assert len(generated)==step['generated_n']
    refs=case['references'];route,_=core.selected_route(case['model_response'],refs)
    compatible=[r for r in refs if int(case['question_id']) in r['question_ids'] and r['route_id']==route]
    assert step['candidate_reference_ids']==[r['reference_id'] for r in compatible]
    selected=[r for r in compatible if r['reference_id']==step['reference_id']]
    assert len(selected)==1 and len(compatible)==1,'UNEXPECTED_MULTIPLE_REFERENCE_REUSE'
    ref=selected[0];rt=[r['text'] if isinstance(r,dict) else r for r in ref['steps']]
    assert len(rt)==step['reference_n']==len(step['matches'])
    for index,m in enumerate(step['matches']):
        assert m['reference_index']==index and m['reference_text']==rt[index]
        assert m['generated_text']==generated[m['generated_index']]['text']
        assert m['matched']==(m['similarity']>=.7)
    assert len(step['generated_max_similarity'])==len(generated)
    sr=sum(m['similarity']>=.7 for m in step['matches'])/len(rt)
    sp=sum(v>=.7 for v in step['generated_max_similarity'])/len(generated) if generated else 0.
    assert same(sr,step['sr']) and same(sp,step['sp']),'STORED_STEP_COUNTS_DISAGREE'
    source=bind(ref['source_path']);assert source['sha256']==ref['source_sha256']
    return answer_hash,question_hash,ref,source


def row(case,step,encoder,config_sha,provenance):
    ah,qh,ref,source=validate_step(case,step)
    return {'sr':step['sr'],'sp':step['sp'],'answer_sha256':ah,'question_sha256':qh,
        'question_id':case['question_id'],'references_sha256':j.digest(case['references']),
        'reference_id':step['reference_id'],'candidate_reference_ids':step['candidate_reference_ids'],
        'selected_reference_sha256':j.digest(ref),'threshold':.7,'encoder':encoder,
        'adapter_version':core.VERSION,'adapter_sha256':j.filehash(core.__file__),
        'step_config_sha256':config_sha,'step_config_hash_kind':'source_config_file_bytes',
        'original_step_config_object_digest':step.get('step_config_sha256'),
        'reference_n':step['reference_n'],'generated_n':step['generated_n'],
        'step_missing_reason':step.get('step_missing_reason'),'reference_status':ref['status'],
        'formal_eligible':False,'reuse_kind':'verified_deterministic_step_values_not_judge_reuse',
        'provenance':list({x['path']:x for x in [*provenance,source]}.values())}


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not any((OUT/n).exists() for n in ['development.json','E2.json','summary.json']),'REFUSE_OVERWRITE'
    source_bind=read(original.STEP_BINDING)
    for k in ['config','matches','per_answer']:verify(source_bind[k])
    cfg=read(source_bind['config']['path']);runpath=ART/'supplement_v2_t070_run.json';run=read(runpath)
    assert run['config_hash']==core.digest(cfg)
    encoder=run['encoder'];assert encoder['model']=='all-mpnet-base-v2' and encoder['max_seq_length']==384
    weights=core.ASSETS/'assets/all-mpnet-base-v2/model.safetensors'
    if not weights.exists():weights=weights.with_name('pytorch_model.bin')
    assert bind(weights)['sha256']==encoder['weights_sha256']
    devcases=read(DEV_CASES)['cases'];assert len(devcases)==5
    # Execute the original source-chain verifier itself; it never loads an encoder.
    devsteps=original.verify_step_sources(devcases)
    devscores={r['answer_id']:r for r in read(source_bind['per_answer']['path'])}
    devrefs=read(cfg['inputs']['complete_reference_manifest'])
    refindex={r['reference_id']:r for r in refs_rows(devrefs)}
    devprov=[bind(p) for p in [DEV_CASES,original.STEP_SOURCE,original.STEP_BINDING,
        Path(original.__file__),Path(core.__file__),runpath,Path(cfg['inputs']['complete_reference_manifest'])]]
    devprov += [source_bind[k] for k in ['config','matches','per_answer']]
    development={}
    for c in devcases:
        s=devsteps[c['case_id']];old=devscores[s['answer_id']]
        assert rawsha(c['specific_question'])==old['question_sha256']
        assert rawsha(c['model_response'])==old['answer_sha256']
        assert s['step_config_sha256']==core.digest(cfg)
        assert old['threshold']==.7 and old['config_hash']==run['config_hash']
        for ref in c['references']:assert ref==refindex[ref['reference_id']],'DEV_REFERENCE_CONTEXT_CHANGED'
        development[c['case_id']]=row(c,s,encoder,source_bind['config']['sha256'],devprov)
    plan=read(E2/'plan.json')
    for item in plan['frozen_inputs']:verify(item)
    config=read(E2/'step_config.json');verification=read(E2/'analysis_verification.json')
    assert verification['status']=='pass' and verification['all_21_answers_and_15_pairs_retained'] is True
    assert verification['raw_projection_and_receipt_hash_checks'] is True
    assert verification['same_pair_contracts_checked']==15
    verify(verification['original_step_source'])
    assert Path(verification['original_step_source']['path']).resolve()==(E2/'step_results.json').resolve()
    assert config['threshold']==.7 and config['encoder']==encoder
    assert config['adapter_sha256']==j.filehash(core.__file__)
    assert config['references_file_sha256']==j.filehash(E2/'references.json')
    cases=read(E2/'cases.json')['cases'];steps={r['case_id']:r for r in read(E2/'step_results.json')}
    per={r['case_id']:r for r in read(E2/'per_answer.json')};refs=read(E2/'references.json')
    refs_index={r['reference_id']:r for r in refs_rows(refs)}
    assert len(cases)==len(steps)==len(per)==21
    assert {c['case_id'] for c in cases}==set(steps)==set(per)
    e2prov=[bind(E2/n) for n in ['cases.json','step_results.json','step_config.json','references.json',
        'per_answer.json','analysis_verification.json','plan.json']]+[bind(Path(core.__file__))]
    e2out={}
    for c in cases:
        cid=c['case_id'];s=steps[cid];p=per[cid]
        assert s['original_core_full_text_reparsed'] is True
        assert s['answer_sha256']==p['source_full_answer_sha256']==rawsha(c['model_response'])
        assert p['question_sha256']==rawsha(c['specific_question'])
        assert s['references_sha256']==p['references_sha256']==j.digest(c['references'])
        assert p['step_config_sha256']==j.filehash(E2/'step_config.json')
        assert p['original_step_result']==s['step_result']
        assert all(same(p['candidate_raw_and_derived'][m],s['step_result'][m]) for m in ['sr','sp'])
        for ref in c['references']:assert ref==refs_index[ref['reference_id']],'E2_REFERENCE_CONTEXT_CHANGED'
        e2out[cid]=row(c,s['step_result'],encoder,p['step_config_sha256'],e2prov)
    # Source check only: old analysis/steps are unchanged, no numerical scorer is called.
    for item in list(BOUND.values()):assert j.filehash(item['path'])==item['sha256']
    output(OUT/'development.json',development);output(OUT/'E2.json',e2out)
    output(OUT/'summary.json',{'status':'verified_deterministic_step_reuse_ready','created_utc':datetime.now(timezone.utc).isoformat(),
        'phase_counts':{'development':5,'E2':21},'threshold':.7,'encoder':encoder,
        'development_original_verifier_called':'cce_analyze_grounded_stability_dev_v1.verify_step_sources',
        'case_question_answer_reference_hashes_checked':26,'full_text_segmentations_reparsed':26,
        'reference_and_generated_max_threshold_counts_rechecked':26,
        'selected_reference_candidates_per_case':1,'new_judge_requests':0,'new_embeddings':0,
        'judge_trials_reused':0,'source_files_modified':False,'confirmation_or_human_inputs_read':False,
        'scientific_expert_validation':False,'scope':'Existing original core/.7/all-mpnet-base-v2 on exact dev5/E2 21 inputs only; deterministic reuse survives judge failure.',
        'hash_algorithms':{'text':'raw UTF8 SHA256','references':'cce_judges.digest: sorted compact UTF8 JSON SHA256'},
        'source_bindings':list(BOUND.values()),'outputs':{n:bind(OUT/n) for n in ['development.json','E2.json']},
        'script':bind(Path(__file__)),'actual_command':[sys.executable,*sys.argv]})
    print(j.canonical({'status':'verified_deterministic_step_reuse_ready','development':5,'E2':21,
        'output_paths':{n:str(OUT/n) for n in ['development.json','E2.json','summary.json']},
        'summary_sha256':j.filehash(OUT/'summary.json'),'new_calls':0,'new_embeddings':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['build']);parser.parse_args();build()
