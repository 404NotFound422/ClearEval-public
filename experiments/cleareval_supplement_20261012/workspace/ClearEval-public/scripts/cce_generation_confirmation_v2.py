"""Prospective evaluation of the seven previously selected, unrequested answers."""
from pathlib import Path
import argparse
import asyncio
import importlib
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_generation_completion_runner_v1 as dev
import cce_codex_fieldwise_replay_v2 as components
j,base,g,budget=dev.j,dev.base,dev.g,dev.budget
candidate,extension=dev.candidate,dev.extension
OLD=budget.OUT/'fieldwise_confirmation_v1'
OUT=budget.OUT/'generation_confirmation_v2'
IDS=['FPC%02d'%i for i in range(2,9)]
write,writebytes,bind,require=dev.write,dev.writebytes,dev.bind,dev.require


def processor(name):
    require(name in ['cce_fieldwise_scoring_v2','cce_fieldwise_scoring_v3'],'REGISTERED_PROCESSOR')
    return importlib.import_module(name)


def generator(name):
    require(name in ['cce_generation_completion_candidate_v1','cce_generation_order_only_v1'],'REGISTERED_GENERATOR')
    return importlib.import_module(name)


def processor_files(module):
    seen=set();paths=[]
    def visit(m):
        path=Path(m.__file__).resolve()
        if path in seen:return
        seen.add(path);paths.append(path)
        for value in vars(m).values():
            if hasattr(value,'__file__') and isinstance(getattr(value,'__name__',None),str) and value.__name__.startswith('cce_'):
                visit(value)
    visit(module)
    return paths


def prepare(a):
    global candidate
    candidate=generator(a.generator)
    require(not a.out.exists(),'NEW_OUTPUT_DIRECTORY_REQUIRED')
    extension.install();budget.guard('confirmation',7,600)
    fw=processor(a.processor)
    contract,models=base.science_contract(OLD/'model_config.json',True)
    old_plan=j.read(OLD/'plan.json');base.verify_bindings(old_plan['frozen_inputs'])
    old_matrix=j.read(OLD/'matrix.json')
    started={r['trial_id'] for r in budget.counts()['requests']}
    selected=[r for r in old_matrix if r['anonymous_answer_id'] in IDS]
    require([r['anonymous_answer_id'] for r in selected]==IDS,'ORIGINAL_SEVEN_ORDER')
    require(all(r['planned_trial_id'] not in started for r in selected),'SEVEN_MUST_BE_UNREQUESTED')
    paths=dev.dependencies(contract)+processor_files(fw)+[Path(__file__),Path(candidate.__file__),Path(components.__file__),Path(components.partial.__file__),OLD/'plan.json',OLD/'matrix.json']
    # This record precedes this entrypoint's first selected-answer-body read.
    write(a.out/'preexport_freeze.json',dict(created_utc=j.now(),processor=a.processor,generator=a.generator,
        generation_candidate=candidate.CANDIDATE_VERSION,ids=IDS,
        frozen_inputs=[bind(p) for p in dict.fromkeys(paths)],
        prior_FPC01_excluded_as_exposed_development=True,source_scope='new answers on previously exposed tasks; no claim of new-task generalization'))
    _,all_cases,_,_=dev.recovery.validate(OLD)
    cases=[c for c in all_cases if c['anonymous_answer_id'] in IDS]
    contract['prospective_generation_confirmation']=dict(candidate=candidate.CANDIDATE_VERSION,
        processor=a.processor,processor_version=fw.VERSION,component_processing=bind(components.__file__),
        generation_intervention='ordered schema; original prompt' if a.generator=='cce_generation_order_only_v1' else 'ordered schema plus compact non-repetition instruction',max_attempts=1,
        all_selected_answers_retained=True,prior_exposed_FPC01_not_confirmation=True)
    write(a.out/'expected_contract.json',contract);write(a.out/'cases.json',dict(cases=cases))
    writebytes(a.out/'model_config.json',(OLD/'model_config.json').read_bytes())
    matrix=[];assets=[]
    for case,old in zip(cases,selected):
        aid=case['anonymous_answer_id'];doc=g.document(case['model_response'],g.source_id_for_case(case))
        require(g.rawsha(case['model_response'])==old['step']['answer_sha256'],'ORIGINAL_ANSWER_BYTES')
        require(g.rawsha(case['specific_question'])==old['step']['question_sha256'],'ORIGINAL_QUESTION_BYTES')
        spec=candidate.schema_for_document(doc);prompt=candidate.make_prompt(case,doc)
        payload=candidate.payload_for(prompt,spec,models[0]['public'])
        bound=len(prompt.encode('utf8'))+8192+256
        require(bound<=models[0]['public']['num_ctx'],'FULL_CONTEXT_LIMIT:'+aid)
        files={k:a.out/folder/(aid+suffix) for k,folder,suffix in [('source_document','source_documents','.json'),('schema','schemas','.json'),('payload','request_payloads','.json'),('prompt','prompts','.txt')]}
        for k,v in [('source_document',doc),('schema',spec),('payload',payload)]:write(files[k],v)
        writebytes(files['prompt'],prompt.encode('utf8'))
        order=candidate.format_order_manifest(j.read(files['payload']))
        identity=dict(case_id=case['case_id'],anonymous_answer_id=aid,
            input_sha256=j.digest(dict(question=case['specific_question'],question_id=case['question_id'],protocol=case['model_response'],references=case['references'])),
            judge=base.MODEL,repeat_index=0,attempt=1,phase='confirmation',round_id=budget.ROUND,
            contract_sha256=j.digest(contract),payload_sha256=j.digest(payload),ordered_payload_sha256=order['ordered_payload_sha256'])
        matrix.append(dict(anonymous_answer_id=aid,case_id=case['case_id'],identity=identity,planned_trial_id=j.digest(identity),
            assets={k:bind(v) for k,v in files.items()},step=old['step'],order_manifest=order,context_bound=bound,
            original_unrequested_trial_id=old['planned_trial_id']))
        assets.extend(files.values())
    write(a.out/'matrix.json',matrix)
    pre=j.read(a.out/'preexport_freeze.json')
    write(a.out/'plan.json',dict(status='frozen_before_generation',ids=IDS,phase='confirmation',planned=7,max_attempts=1,
        processor=a.processor,generator=a.generator,deadline_utc=extension.DEADLINE,
        frozen_inputs=pre['frozen_inputs']+[bind(p) for p in [a.out/n for n in ['preexport_freeze.json','expected_contract.json','cases.json','model_config.json','matrix.json']]+assets],
        actual_prepare_command=[sys.executable,*sys.argv],new_model_requests=0))
    validate(a.out);print(j.canonical(dict(status='prepared',planned=7,plan=bind(a.out/'plan.json'),new_model_requests=0)))


def validate(out):
    global candidate
    plan=j.read(out/'plan.json');base.verify_bindings(plan['frozen_inputs'])
    candidate=generator(plan['generator'])
    require(plan['ids']==IDS and plan['phase']=='confirmation' and plan['max_attempts']==1,'FIXED_PLAN')
    cases=j.read(out/'cases.json')['cases'];matrix=j.read(out/'matrix.json');contract=j.read(out/'expected_contract.json')
    require([c['anonymous_answer_id'] for c in cases]==[r['anonymous_answer_id'] for r in matrix]==IDS,'FIXED_ORDER')
    for c,r in zip(cases,matrix):
        require(g.rawsha(c['model_response'])==r['step']['answer_sha256'] and g.rawsha(c['specific_question'])==r['step']['question_sha256'],'ANSWER_QUESTION_HASH')
        require(j.digest(c['references'])==r['step']['references_sha256'],'ORIGINAL_REFERENCE_IDENTITY')
        require(j.digest(r['identity'])==r['planned_trial_id'] and r['identity']['contract_sha256']==j.digest(contract),'TRIAL_IDENTITY')
        payload=j.read(r['assets']['payload']['path']);doc=j.read(r['assets']['source_document']['path'])
        require(doc==g.document(c['model_response'],g.source_id_for_case(c)),'SOURCE_DOCUMENT')
        require(payload==candidate.payload_for(candidate.make_prompt(c,doc),candidate.schema_for_document(doc),contract['models'][0]['settings']),'COMPLETE_FROZEN_PROMPT')
        require(candidate.format_order_manifest(payload)==r['order_manifest'],'ACTUAL_REQUEST_ORDER')
    return plan,cases,matrix,contract


async def run(a):
    require(a.allow_local_calls,'EXPLICIT_RUN_FLAG');p,cases,matrix,contract=validate(a.out);extension.install()
    fw=processor(p['processor']);components.fw=fw  # explicit registered processor for every dependency view
    current,models=base.science_contract(a.out/'model_config.json',True)
    require(all(current[k]==contract[k] for k in base.SCIENCE_KEYS+['models']),'SCIENCE_OR_MODEL_CHANGE')
    selected=IDS if a.ids is None else a.ids;require(set(selected)<=set(IDS) and len(selected)==len(set(selected)),'PLANNED_IDS_ONLY')
    write(a.out/'run_commands'/(j.now().replace(':','').replace('+','_')+'.json'),dict(argv=[sys.executable,*sys.argv],processor=p['processor'],deadline_utc=extension.DEADLINE))
    for case,row in zip(cases,matrix):
        if row['anonymous_answer_id'] not in selected:continue
        tid=row['planned_trial_id'];at=a.out/'run/attempts'/(tid+'_1');tp=a.out/'run/trials'/(tid+'.json')
        if tp.exists():continue
        if any(r['trial_id']==tid for r in budget.counts()['requests']):continue
        if budget.time_remaining()<=630:break
        base.verify_bindings(p['frozen_inputs']);payload=j.read(row['assets']['payload']['path']);doc=j.read(row['assets']['source_document']['path'])
        write(at/'http_request_payload.json',payload)
        receipt=budget.reserve('confirmation',tid,base.MODEL,600);write(at/'request_receipt.json',receipt)
        metrics=base.scoring.derive({},row['step'],False);status='failed';error=None;stage='PROVIDER_TRANSPORT'
        try:
            provider=await asyncio.to_thread(base.invoke_transport,models[0]['public'],payload);write(at/'provider_response.json',provider)
            raw=provider.get('response') if isinstance(provider,dict) else None
            if isinstance(raw,str):writebytes(at/'raw_response.txt',raw.encode('utf8'))
            stage='PROVIDER_COMPLETION';raw=base.validate_provider(provider,models[0]['public'])
            stage='FIELDWISE_PROCESSING';result=components.independent_processing(raw,doc,case,row['step'])
            write(at/'component_result.json',result);metrics=result['metrics']
            status='success' if result['full_conversion_success'] else 'partial_components'
            stage=None
        except Exception as exc:
            error=dict(stage=stage,type=type(exc).__name__,reason=str(exc));write(at/'error.json',error)
        write(tp,dict(trial_id=tid,identity=row['identity'],anonymous_answer_id=row['anonymous_answer_id'],status=status,
            failure_stage=stage,error=error,request_id=receipt['request_id'],attempt=1,actual_request_made=True,
            terminal_utc=j.now(),metrics=metrics,bound_artifacts=[bind(f) for f in sorted(at.iterdir()) if f.is_file()],
            formal_eligible=False,expert_confirmed=False))
        print(j.canonical(dict(id=row['anonymous_answer_id'],status=status,request_index=receipt['package_request_index'])),flush=True)


def analyze(a):
    p,_,matrix,_=validate(a.out);ledger=budget.counts();rows=[]
    for r in matrix:
        tp=a.out/'run/trials'/(r['planned_trial_id']+'.json');reservations=[x for x in ledger['requests'] if x['trial_id']==r['planned_trial_id']]
        require(len(reservations)<=1,'ONE_ATTEMPT')
        if tp.exists():
            t=j.read(tp);base.verify_bindings(t['bound_artifacts'])
            require(t['identity']==r['identity'] and len(reservations)==1 and t['request_id']==reservations[0]['request_id'],'REAL_REQUEST_TERMINAL_IDENTITY')
            row={k:t[k] for k in ['status','metrics','error','failure_stage']}
        else:row=dict(status='reserved_nonterminal' if reservations else 'unstarted',metrics=base.scoring.derive({},r['step'],False))
        rows.append(dict(anonymous_answer_id=r['anonymous_answer_id'],trial_id=r['planned_trial_id'],actual_request=bool(reservations),**row))
    summary=dict(planned=7,actual_requests=sum(r['actual_request'] for r in rows),statuses={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})},
        numeric_coverage={k:sum(dev.finite(r['metrics'][k]) for r in rows) for k in base.scoring.METRICS},
        complete_CCE=sum(all(dev.finite(r['metrics'][k]) for k in ['Com','Cor','Eff','IA','HV']) for r in rows),
        package_requests=ledger['package'],source_scope='prospective answers on previously exposed tasks',new_analysis_model_requests=0,formal_eligible=False,expert_confirmed=False)
    dest=a.out/'analysis'/j.now().replace(':','').replace('+','_');write(dest/'observations.json',rows);write(dest/'summary.json',summary)
    print(j.canonical(dict(out=str(dest),**summary)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','analyze'])
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--processor',default='cce_fieldwise_scoring_v3')
    p.add_argument('--generator',default='cce_generation_order_only_v1')
    p.add_argument('--ids',nargs='+',choices=IDS);p.add_argument('--allow-local-calls',action='store_true');a=p.parse_args()
    if a.action=='prepare':prepare(a)
    elif a.action=='run':asyncio.run(run(a))
    else:analyze(a)


if __name__=='__main__':main()
