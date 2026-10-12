"""Execute the prepared five-answer qualitative-Correctness contrast.

Generation uses the existing canonical-source processor and local transport.
Preparation/verification/analysis are offline. New requests require a renewed
ten-call, two-hour authorization because the previous 438-call window is over.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import random
import shutil
import sys
import types
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_round3_runner_v2 as engine
import cce_canonical_components_v1 as processor
import cce_canonical_qualitative_candidate_v1 as candidate
j=engine.j
ROUND='qualitative_correctness_pairs_20261012'
PHASE='qualitative_development'
LEDGER=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
PENDING=ROOT.parent/'reports/cleareval_20261012/typed_label_transfer/qualitative_canonical_pending'
OLD=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_development_v11'
STEPS=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/step_inputs_v1/development.json'
SAVE=engine.save_once


class Budget:
    ROUND=ROUND
    def __init__(self,out):self.out=Path(out);self.path=self.out/'authorization.json'
    def counts(self):
        prefix=(self.out/'ledger_before.jsonl').read_bytes()
        assert LEDGER.read_bytes().startswith(prefix),'Prior request ledger changed'
        requests=[r for r in j.ledger_rows(LEDGER) if r.get('event')=='request_started']
        own=[r for r in requests if r.get('round_id')==ROUND]
        assert len(requests)==438+len(own),'Reconcile any other authorized batch before running this one'
        assert len({r['request_id'] for r in requests})==len(requests)
        assert [r['package_request_index'] for r in own]==list(range(439,439+len(own)))
        return {'package':len(requests),'round':len(own),'requests':requests}
    def authorization(self):
        if not self.path.exists():raise ValueError('RENEWED_TEN_CALL_TWO_HOUR_AUTHORIZATION_REQUIRED; no generation request made')
        a=j.read(self.path)
        assert a['status']=='explicit_user_approval_recorded' and a['user_reply'].strip()
        assert (a['starting_package_requests'],a['authorized_new_requests'],a['new_package_limit'])==(438,10,448)
        assert a['automatic_retries'] is False and a['max_attempts']==1
        assert a['freeze_sha256']==j.filehash(self.out/'freeze.json')
        start,end=(datetime.fromisoformat(a[k]) for k in ['start_utc','deadline_utc'])
        assert start.utcoffset() is not None and end.utcoffset() is not None
        assert 0<(end-start).total_seconds()<=7200
        return a
    def guard(self,seconds=0):
        a,c=self.authorization(),self.counts()
        assert c['package']<448 and c['round']<10,'Request allowance exhausted'
        assert (datetime.fromisoformat(a['deadline_utc'])-datetime.now(timezone.utc)).total_seconds()>seconds+30,'Not enough authorized time for one bounded request'
        return c
    def reserve(self,phase,trial_id,model,seconds):
        assert phase==PHASE and model=='qwen3.8:27b-q8_0-local'
        with j.ledger_lock(LEDGER):
            c=self.guard(seconds)
            assert not any(r['trial_id']==trial_id for r in c['requests']),'A started request is never silently retried'
            request={'event':'request_started','request_id':j.digest({'round_id':ROUND,'trial_id':trial_id,'attempt':1}),
                'trial_id':trial_id,'attempt':1,'model':model,'started_utc':j.now(),
                'package_request_index':c['package']+1,'round_id':ROUND,'phase':phase,
                'authorization_sha256':j.filehash(self.path)}
            with LEDGER.open('a',encoding='utf-8') as f:f.write(j.canonical(request)+'\n')
        return request


def bound_functions(out):
    budget=Budget(out);environment={**vars(engine),'budget':budget}
    execute=types.FunctionType(engine.execute_cell.__code__,environment,name='execute_qualitative_cell')
    terminal=types.FunctionType(engine.terminal.__code__,environment,name='read_qualitative_terminal',argdefs=engine.terminal.__defaults__)
    return budget,execute,terminal


def prepare(out,runtime_public=None):
    assert not out.exists(),'Use a new output directory for a new prepared contrast'
    manifest=j.read(PENDING/'manifest.json')
    for k in ['candidate','control','scope_text','cases']:engine.base.verify_bindings([manifest[k]])
    cases,steps=engine.checked_cases(Path(manifest['cases']['path']),STEPS)
    assert len(cases)==5 and len(manifest['observations'])==10
    ledger=LEDGER.read_bytes();assert len([r for r in j.ledger_rows(LEDGER) if r.get('event')=='request_started'])==438
    out.mkdir(parents=True);engine.bytes_once(out/'ledger_before.jsonl',ledger)
    SAVE(out/'cases.json',{'cases':cases});SAVE(out/'steps.json',steps)
    engine.bytes_once(out/'model_config.json',(OLD/'model_config.json').read_bytes())
    public=manifest['public_model']
    if runtime_public:
        observed=j.read(runtime_public)
        current=observed['public_model']
        assert {k:v for k,v in current.items() if k!='service_version'}=={k:v for k,v in public.items() if k!='service_version'},'Model or generation settings changed; prepare a separately reviewed design'
        SAVE(out/'runtime_metadata_provenance.json',{'observed':engine.bind(runtime_public),'previous_public_model':public,'current_public_model':current,'generation_requests':0})
        public=current
    SAVE(out/'public_model.json',public)
    original_obs={(r['anonymous_answer_id'],r['condition']):r for r in manifest['observations']}
    rng=random.Random(20261012);matrix=[];pairs=[]
    ordered_cases=list(cases);rng.shuffle(ordered_cases)
    for c in ordered_cases:
        aid=c['anonymous_answer_id'];conditions=['C0','C1'];rng.shuffle(conditions)
        eval_doc=candidate.canonical.evaluation_document(c)
        for condition in conditions:
            old=original_obs[aid,condition]
            engine.base.verify_bindings([old[k] for k in ['source','mapping','payload','schema']])
            assert j.read(old['source']['path'])==eval_doc
            payload=j.read(old['payload']['path'])
            maker=candidate.canonical if condition=='C0' else candidate
            assert payload==maker.payload_for(maker.make_prompt(c,eval_doc),maker.schema_for_document(eval_doc),public)
            oid=aid+'_'+condition
            files={k:out/folder/(oid+suffix) for k,folder,suffix in [('payload','request_payloads','.json'),('prompt','prompts','.txt'),('doc','source_documents','.json')]}
            engine.bytes_once(files['payload'],Path(old['payload']['path']).read_bytes())
            engine.bytes_once(files['prompt'],payload['prompt'].encode('utf-8'));SAVE(files['doc'],eval_doc)
            context_bound=len(payload['prompt'].encode('utf-8'))+public['max_output_tokens']+256
            assert context_bound<=public['num_ctx']
            identity={'round_id':ROUND,'phase':PHASE,'case_id':c['case_id'],'condition':condition,
                'observation_id':oid,'repeat_index':0,'attempt':1,'payload_sha256':j.digest(payload),
                'original_steps_sha256':j.digest(steps[c['case_id']])}
            matrix.append({'case_id':c['case_id'],'anonymous_answer_id':oid,'observation_id':oid,
                'answer_id':aid,'question_id':c['question_id'],'condition':condition,'repeat_index':0,
                'planned_trial_id':j.digest(identity),'identity':identity,'step':steps[c['case_id']],
                'assets':{k:engine.bind(p) for k,p in files.items()},'fits_context':True,'context_bound':context_bound,
                'mapping':old['mapping'],'original_document':engine.bind(PENDING/aid/'original_source_document.json'),
                'prepared_input_provenance':old})
        pairs.append({'answer_id':aid,'control':aid+'_C0','candidate':aid+'_C1'})
    SAVE(out/'matrix.json',matrix);SAVE(out/'pairs.json',pairs)
    SAVE(out/'plan.json',{'round_id':ROUND,'phase':PHASE,'public_model':public,
        'processor':'cce_canonical_components_v1','planned_new_requests':10,'base_answers':5,
        'conditions':['C0','C1'],'repeats_per_condition':1,'seed':20261012,
        'old_success_reusable':False,'same_input_except_declared_prompt_scope':True,
        'current_package_limit':438,'proposed_package_limit':448,'proposed_seconds':7200,
        'new_requests_authorized':False,'scientific_status':'five exposed development answers; no prospective confirmation or repeatability estimate',
        'main_endpoint':'criterion/source fidelity plus per-component availability, not a required improvement in score',
        'secondary_endpoint':'full-pipeline extraction/CCE differences; label-role instruction is part of the treatment bundle',
        'scales':[3,2,2,1],'numeric_EGES_and_raw_SR_SP_changed':False,
        'human_budget':{'experts':1,'development':5,'holdout':15},
        'automatic_retries':False,'max_attempts':1})
    science=[ROOT/p for p in j.read(OLD/'expected_contract.json')['files']]
    dependencies=engine.dependencies(engine,processor,candidate)
    freeze_paths=[Path(__file__),*dependencies,*science,ROOT/'KnowledgeBase/source_registry.json',
        ROOT/'dataset/Q+AR/src/demand_vectors_all.json',j.HIST,ROOT/'models/Ollama_LLM.py',
        PENDING/'manifest.json',*sorted(p for p in out.rglob('*') if p.is_file())]
    SAVE(out/'freeze.json',{'created_utc':j.now(),'bindings':[engine.bind(p) for p in dict.fromkeys(freeze_paths)],
        'new_model_calls':0,'status':'prepared_pending_renewed_authorization'})
    assert LEDGER.read_bytes()==ledger
    SAVE(out/'prepare_execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0})
    return verify(out)


def verify(out):
    freeze=j.read(out/'freeze.json');engine.base.verify_bindings(freeze['bindings'])
    plan,rows=j.read(out/'plan.json'),j.read(out/'matrix.json')
    assert len(rows)==10 and len({r['planned_trial_id'] for r in rows})==10
    for row in rows:
        assert row['planned_trial_id']==j.digest(row['identity'])
        engine.base.verify_bindings(list(row['assets'].values())+[row['mapping'],row['original_document']])
    for pair in j.read(out/'pairs.json'):
        left,right=[next(r for r in rows if r['observation_id']==pair[k]) for k in ['control','candidate']]
        a,z=[j.read(r['assets']['payload']['path']) for r in [left,right]]
        assert {k:v for k,v in a.items() if k!='prompt'}=={k:v for k,v in z.items() if k!='prompt'}
        assert j.read(left['assets']['doc']['path'])==j.read(right['assets']['doc']['path']) and left['step']==right['step']
    return {'status':'verified_prepared_not_generated','observations':10,'pairs':5,'new_model_calls':0,
        'authorization_present':(out/'authorization.json').exists()}


def preflight(out):
    verify(out)
    contract,models=engine.base.science_contract(out/'model_config.json',True)
    actual=models[0]['public'];expected=j.read(out/'plan.json')['public_model']
    assert actual==expected,'Local service model identity or settings changed'
    SAVE(out/'runtime_preflight.json',{'created_utc':j.now(),'public_model':actual,
        'contract':contract,'metadata_queries_only':True,'new_generation_requests':0,
        'model_alias_not_asserted_public_release_identity':True})
    return {'status':'local_metadata_matches','new_generation_requests':0,'model':actual['model'],'family':actual['model_details']['family']}


async def run(out,max_calls):
    verify(out);budget,execute,terminal=bound_functions(out)
    budget.authorization()  # No provider query, attempt write or request before approval.
    plan=j.read(out/'plan.json');rows=j.read(out/'matrix.json');cases={c['case_id']:c for c in j.read(out/'cases.json')['cases']}
    _,models=engine.base.science_contract(out/'model_config.json',True)
    assert models[0]['public']==plan['public_model']
    started={r['trial_id'] for r in budget.counts()['requests']}
    for row in rows:
        if engine.terminal_path(out,row).exists():terminal(out,row)
        else:assert row['planned_trial_id'] not in started,'Started request has no terminal: inspect its actual process before resuming'
    made=0
    for row in rows:
        if engine.terminal_path(out,row).exists():continue
        if made>=max_calls:break
        verify(out);budget.guard(plan['public_model']['timeout_seconds'])
        await execute(out,row,cases[row['case_id']],plan,processor);terminal(out,row);made+=1
        auth,count=budget.authorization(),budget.counts()
        state={'round_id':ROUND,'attempts_recorded':count['package'],'package_limit':448,
            'round_attempts':count['round'],'round_limit':10,'remaining_request_capacity':10-count['round'],
            'authorization':engine.bind(budget.path),'ledger':engine.bind(LEDGER),
            'deadline_utc':auth['deadline_utc'],'automatic_retries':False,
            'human_budget':{'experts':1,'development':5,'holdout':15}}
        j.save(out/'budget_snapshot.json',state);j.save(ROOT/'artifacts/cce_validation/budget.json',state)
    return {'new_requests_this_run':made}


def analyze(out):
    verify(out);_,_,terminal=bound_functions(out);observations=[]
    for row in j.read(out/'matrix.json'):
        path=engine.terminal_path(out,row)
        value={k:row[k] for k in ['observation_id','answer_id','case_id','question_id','condition']}
        if path.exists():
            t=terminal(out,row);value.update(status=t['status'],metrics=t['metrics'],trial=engine.bind(path),actual_request_made=t['actual_request_made'])
        else:value.update(status='pending',metrics=None,actual_request_made=False)
        observations.append(value)
    byid={r['observation_id']:r for r in observations};pairs=[]
    for pair in j.read(out/'pairs.json'):
        a,z=[byid[pair[k]] for k in ['control','candidate']];both=a['metrics'] is not None and z['metrics'] is not None
        pairs.append({**pair,'both_observed':both,'changes':{k:{'control':a['metrics'][k],'candidate':z['metrics'][k],
            'delta':z['metrics'][k]-a['metrics'][k] if engine.finite(a['metrics'][k]) and engine.finite(z['metrics'][k]) else None}
            for k in engine.METRICS} if both else {}})
    dest=out/'analysis';dest.mkdir(exist_ok=True)
    j.save(dest/'observations.json',observations);j.save(dest/'pairs.json',pairs)
    summary={'planned_observations':10,'actual_observations':sum(r['status']!='pending' for r in observations),
        'complete_pairs':sum(r['both_observed'] for r in pairs),'new_model_calls_by_analysis':0,
        'criterion_fidelity_audit':'pending until real outputs exist','scientific_accuracy_claimed':False}
    j.save(dest/'summary.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','verify','preflight','run','analyze'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--max-new-calls',type=int,default=10)
    p.add_argument('--runtime-public',type=Path,help='Metadata-only observation with public_model; preparation may bind an updated service version')
    a=p.parse_args();out=a.out.resolve();assert 0<=a.max_new_calls<=10
    runtime_public=a.runtime_public.resolve() if a.runtime_public else None
    # The retained original scorer opens KnowledgeBase paths relative to cwd.
    # Resolve user paths first, then give all legacy imports their repository cwd.
    previous_cwd=Path.cwd()
    try:
        os.chdir(ROOT)
        if a.action=='prepare':result=prepare(out,runtime_public)
        elif a.action=='verify':result=verify(out)
        elif a.action=='preflight':result=preflight(out)
        elif a.action=='analyze':result=analyze(out)
        else:result=asyncio.run(run(out,a.max_new_calls))
    finally:os.chdir(previous_cwd)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
