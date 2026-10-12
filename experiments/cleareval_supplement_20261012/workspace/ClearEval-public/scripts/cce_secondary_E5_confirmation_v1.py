"""Eight metadata-fixed additions for a secondary common-task analysis.

Uses the frozen seven-cell execution implementation with an explicit eight-ID
adapter. No old file is edited. Preparation freezes dependencies before archive
export; only run --allow-local-calls can issue requests. No retry or new gate.
"""
from __future__ import annotations
import argparse, asyncio, copy, csv, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_generation_confirmation_v2 as core
import cce_generation_confirmation_runtime_v2 as original_runtime

base,j,g,budget=core.base,core.j,core.g,core.budget
write,writebytes,bind,require=core.write,core.writebytes,core.bind,core.require
IDS=['FPC%02d'%i for i in range(9,17)]
OUT=budget.OUT/'secondary_E5_confirmation_v1'
SELECTION=budget.OUT/'secondary_E5_coverage_selection_v1/selection_metadata.json'
FIRST=core.OUT
STEPS=ROOT/'artifacts/cce_validation/method_family_steps_v1'
EXPORTER=core.dev.recovery.exporter
GENERATOR='cce_generation_order_only_v1'
PROCESSOR='cce_fieldwise_scoring_v3'
FIXED={
    'metadata':'f15323d7699dcdedeaa9f210447b2f23ffc73b9f9e68095a96f8a436e21a3393',
    'core':'4232f46816d1e891525a4b2a24e9190a18d1cb6cf1bda1af17f5ceabc67b3e6e',
    'runtime':'c4459599def7c51442ed1f0b33f7fa0996710bafd4b25e60738eb25112ce69a5',
    'generator':'cdd9769413bd05b7307feb1fd9a64aae00195bd15db8d1e2d78c952e59c0f3b8',
    'processor':'91d6dace49137e639e79acd0615977adead24dce6fda9328059c883e8ec470ce',
    'first_plan':'6a10ab9063662efa52aa264b1e96798f731b0c0669605c73496e2588a1b8e215',
}


def configured():
    core.IDS=list(IDS)  # In-process adapter only; frozen source bytes stay intact.
    gen=core.generator(GENERATOR);fw=core.processor(PROCESSOR)
    for key,path in [('metadata',SELECTION),('core',core.__file__),('runtime',original_runtime.__file__),
                     ('generator',gen.__file__),('processor',fw.__file__),('first_plan',FIRST/'plan.json')]:
        require(j.filehash(path)==FIXED[key],'FIXED_DEPENDENCY_CHANGED:'+key)
    return gen,fw


def selected_metadata():
    value=j.read(SELECTION)
    require([r['confirmation_id'] for r in value['selection']]==IDS and value['selected_count']==8,'FIXED_EIGHT_METADATA')
    require(value['chosen_generator_models']==['openai_qwen3-14b','openai_qwen3-32b']
        and value['potential_common_question_ids']==[1,2,21,22,248],'FIXED_SECONDARY_COHORT')
    base.verify_bindings(value['metadata_inputs'])
    require(len({r['answer_sha256'] for r in value['selection']})==8,'DUPLICATE_SELECTED_ANSWER')
    require(all(r['eligibility'] and not r['exclusion_reasons'] and r['existing_SR_SP_finite'] for r in value['selection']),'ORIGINAL_ELIGIBILITY_REQUIRED')
    return value


def case_and_step(meta,obj,refidx,original,config):
    require(g.rawsha(obj['model_response'])==meta['answer_sha256'] and g.rawsha(obj['specific_question'])==meta['question_sha256'],'SELECTED_SOURCE_BYTES_CHANGED')
    require(original['answer_sha256']==meta['answer_sha256'] and original['question_sha256']==meta['question_sha256'],'ORIGINAL_STEP_SOURCE_CHANGED')
    require(int(original['question_id'])==int(meta['question_id']) and original['reference_id']==meta['existing_selected_reference_id']
        and original['reference_id'] in meta['candidate_reference_ids'],'ORIGINAL_SELECTED_REFERENCE_CHANGED')
    require(config['threshold']==.7 and config['encoder']['model']=='all-mpnet-base-v2','ORIGINAL_SR_SP_CONFIGURATION')
    sr,sp=float(original['sr']),float(original['sp'])
    require(all(core.dev.finite(x) and 0<=x<=1 for x in [sr,sp]),'EXISTING_SR_SP_NOT_FINITE')
    refs=[copy.deepcopy(refidx[rid]) for rid in meta['candidate_reference_ids']]
    aid=meta['confirmation_id'];case=dict(case_id='secondary_'+aid,anonymous_answer_id=aid,question_id=int(meta['question_id']),
        specific_question=obj['specific_question'],model_response=obj['model_response'],references=refs,
        answer_sha256=meta['answer_sha256'],question_sha256=meta['question_sha256'],formal_eligible=False,expert_confirmation=None)
    step=dict(sr=sr,sp=sp,answer_sha256=meta['answer_sha256'],question_sha256=meta['question_sha256'],question_id=case['question_id'],
        reference_id=original['reference_id'],candidate_reference_ids=meta['candidate_reference_ids'],references_sha256=j.digest(refs),
        reference_catalog_file_sha256=config['references_sha256'],threshold=config['threshold'],encoder=config['encoder'],
        adapter_sha256=config['core_sha256'],step_config_sha256=j.filehash(STEPS/'t070_resolved_config.json'),
        reuse_kind='exact_original_SR_SP_no_new_encoder_no_new_reference_qualification',
        provenance=[bind(STEPS/n) for n in ['t070_per_answer.csv','t070_resolved_config.json','references.json','verification.json']])
    return case,step


def prepare(a):
    require(not a.out.exists(),'NEW_OUTPUT_DIRECTORY_REQUIRED')
    gen,fw=configured();meta=selected_metadata();core.extension.install()
    first_matrix=j.read(FIRST/'matrix.json');started={x['trial_id'] for x in budget.counts()['requests']}
    first_pending=sum(r['planned_trial_id'] not in started for r in first_matrix)
    budget.guard('confirmation',8+first_pending,600)
    contract,models=base.science_contract(FIRST/'model_config.json',True)
    previous=j.read(FIRST/'expected_contract.json')
    require(all(contract[k]==previous[k] for k in base.SCIENCE_KEYS+['models']),'SAME_FINAL_SCIENCE_AND_QWEN_REQUIRED')
    require(previous['prospective_generation_confirmation']['candidate']==gen.CANDIDATE_VERSION
        and previous['prospective_generation_confirmation']['processor']==PROCESSOR,'SAME_FINAL_CANDIDATE_REQUIRED')
    stepfiles=[STEPS/n for n in ['references.json','plan.json','t070_per_answer.csv','t070_resolved_config.json','verification.json','run.json']]
    paths=core.dev.dependencies(contract)+core.processor_files(fw)+[Path(__file__),Path(core.__file__),Path(original_runtime.__file__),
        Path(gen.__file__),Path(core.components.__file__),Path(core.components.partial.__file__),Path(EXPORTER.__file__),SELECTION,
        FIRST/'plan.json',FIRST/'matrix.json',FIRST/'expected_contract.json',FIRST/'model_config.json']+stepfiles
    paths += [Path(x['path']) for x in meta['metadata_inputs']]
    write(a.out/'preexport_freeze.json',dict(status='frozen_before_selected_answer_export',created_utc=j.now(),ids=IDS,
        generator=GENERATOR,processor=PROCESSOR,frozen_inputs=[bind(p) for p in dict.fromkeys(paths)],
        selection_kind=meta['selection_kind'],secondary_E5_analysis=meta['secondary_E5_analysis'],
        answer_bodies_exported_before_this_record=0,remaining_first_seven_reserved_in_budget_guard=first_pending,new_model_requests=0))
    # This is the first selected archive read in this entrypoint.
    refs=j.read(STEPS/'references.json')['references'];refidx={r['reference_id']:r for r in refs}
    config=j.read(STEPS/'t070_resolved_config.json')
    require(config['references_sha256']==j.filehash(STEPS/'references.json') and config['core_sha256']==j.filehash(ROOT/'scripts/cce_validation.py'),'ORIGINAL_STEP_FILES_CHANGED')
    with (STEPS/'t070_per_answer.csv').open(encoding='utf-8-sig',newline='') as f:oldsteps={r['answer_id']:r for r in csv.DictReader(f)}
    cases=[];steps={};locations=[]
    for row in meta['selection']:
        obj,location=EXPORTER.selected_record(ROOT/f"dataset/Q+AR/model_response/from_{row['model']}_1-shot.json",int(row['question_id']))
        case,step=case_and_step(row,obj,refidx,oldsteps[row['answer_id']],config)
        cases.append(case);steps[case['case_id']]=step;locations.append(dict(anonymous_answer_id=row['confirmation_id'],answer_id=row['answer_id'],**location))
    contract['prospective_generation_confirmation']=copy.deepcopy(previous['prospective_generation_confirmation'])
    contract['secondary_E5_confirmation']=dict(selection=bind(SELECTION),ids=IDS,scope=meta['selection_kind'],
        adapter=bind(__file__),prior_random_confirmation_not_replaced=True,expert_qualified=0,max_attempts=1)
    write(a.out/'expected_contract.json',contract);write(a.out/'cases.json',dict(cases=cases));write(a.out/'step_inputs.json',steps)
    write(a.out/'source_identity_manifest.json',locations);writebytes(a.out/'model_config.json',(FIRST/'model_config.json').read_bytes())
    matrix=[];assets=[]
    for case in cases:
        aid=case['anonymous_answer_id'];doc=g.document(case['model_response'],g.source_id_for_case(case))
        spec=gen.schema_for_document(doc);prompt=gen.make_prompt(case,doc);payload=gen.payload_for(prompt,spec,models[0]['public'])
        bound=len(prompt.encode('utf8'))+8192+256;require(bound<=models[0]['public']['num_ctx'],'FULL_CONTEXT_LIMIT:'+aid)
        files={k:a.out/folder/(aid+suffix) for k,folder,suffix in [('source_document','source_documents','.json'),('schema','schemas','.json'),('payload','request_payloads','.json'),('prompt','prompts','.txt')]}
        for k,v in [('source_document',doc),('schema',spec),('payload',payload)]:write(files[k],v)
        writebytes(files['prompt'],prompt.encode('utf8'));order=gen.format_order_manifest(j.read(files['payload']))
        require(order==gen.format_order_manifest(payload),'STORAGE_MUST_PRESERVE_SCHEMA_ORDER')
        identity=dict(case_id=case['case_id'],anonymous_answer_id=aid,input_sha256=j.digest(dict(question=case['specific_question'],question_id=case['question_id'],protocol=case['model_response'],references=case['references'])),
            judge=base.MODEL,repeat_index=0,attempt=1,phase='confirmation',round_id=budget.ROUND,contract_sha256=j.digest(contract),payload_sha256=j.digest(payload),ordered_payload_sha256=order['ordered_payload_sha256'])
        matrix.append(dict(anonymous_answer_id=aid,case_id=case['case_id'],identity=identity,planned_trial_id=j.digest(identity),assets={k:bind(v) for k,v in files.items()},
            step=steps[case['case_id']],order_manifest=order,context_bound=bound,selection_origin='secondary_coverage_directed'))
        assets.extend(files.values())
    write(a.out/'matrix.json',matrix);pre=j.read(a.out/'preexport_freeze.json')
    generated=[a.out/n for n in ['preexport_freeze.json','expected_contract.json','cases.json','step_inputs.json','source_identity_manifest.json','model_config.json','matrix.json']]
    write(a.out/'plan.json',dict(status='frozen_before_generation',ids=IDS,phase='confirmation',planned=8,max_attempts=1,
        processor=PROCESSOR,generator=GENERATOR,deadline_utc=core.extension.DEADLINE,selection_kind=meta['selection_kind'],
        frozen_inputs=pre['frozen_inputs']+[bind(p) for p in generated+assets],secondary_E5_analysis=meta['secondary_E5_analysis'],
        actual_prepare_command=[sys.executable,*sys.argv],new_model_requests=0))
    validate(a.out);print(j.canonical(dict(status='prepared',planned=8,plan=bind(a.out/'plan.json'),new_model_requests=0)))


def validate(out):
    configured();plan=j.read(out/'plan.json')
    require(plan['planned']==8 and plan['ids']==IDS and plan['processor']==PROCESSOR and plan['generator']==GENERATOR,'FIXED_ADDITIONAL_EIGHT')
    return core.validate(out)


def run(a):
    # Actual prompt reconstruction is synchronous: make_prompt internally uses asyncio.run.
    state=validate(a.out);previous_validate=core.validate
    def already_validated(out):
        require(Path(out).resolve()==a.out.resolve(),'VALIDATED_OUTPUT_IDENTITY')
        base.verify_bindings(state[0]['frozen_inputs']);return state
    core.validate=already_validated
    try:
        write(a.out/'runtime_records'/(j.now().replace(':','').replace('+','_')+'.json'),dict(adapter=bind(__file__),plan=bind(a.out/'plan.json'),
            action='Validate eight complete prompts synchronously, then use frozen original async execution.',actual_command=[sys.executable,*sys.argv],new_requests_from_validation=0))
        asyncio.run(core.run(a))
    finally:core.validate=previous_validate


def analyze(a):
    plan,cases,matrix,_=validate(a.out);ledger=budget.counts();rows=[]
    meta={r['confirmation_id']:r for r in j.read(SELECTION)['selection']}
    for case,r in zip(cases,matrix):
        tp=a.out/'run/trials'/(r['planned_trial_id']+'.json');reservations=[x for x in ledger['requests'] if x['trial_id']==r['planned_trial_id']]
        require(len(reservations)<=1,'ONE_ATTEMPT')
        if tp.exists():
            t=j.read(tp);base.verify_bindings(t['bound_artifacts'])
            require(t['trial_id']==r['planned_trial_id'] and t['identity']==r['identity'] and len(reservations)==1
                and t['request_id']==reservations[0]['request_id'],'REAL_REQUEST_TERMINAL_IDENTITY')
            require(reservations[0]['phase']=='confirmation' and reservations[0]['model']==base.MODEL,'REQUEST_MODEL_PHASE')
            row={k:t[k] for k in ['status','metrics','error','failure_stage']}
        else:row=dict(status='reserved_nonterminal' if reservations else 'unstarted',metrics=base.scoring.derive({},r['step'],False))
        require(all(row['metrics'][m]==r['step'][m] for m in ['sr','sp']),'ORIGINAL_SR_SP_RETAINED')
        rows.append(dict(anonymous_answer_id=r['anonymous_answer_id'],trial_id=r['planned_trial_id'],question_id=case['question_id'],
            generator_model=meta[r['anonymous_answer_id']]['model'],actual_request=bool(reservations),**row))
    terminal=all(r['status'] in ['success','partial_components','failed'] for r in rows)
    summary=dict(status='complete' if terminal else 'partial',planned=8,actual_requests=sum(r['actual_request'] for r in rows),
        statuses={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})},
        numeric_coverage={k:sum(core.dev.finite(r['metrics'][k]) for r in rows) for k in base.scoring.METRICS},
        complete_CCE=sum(all(core.dev.finite(r['metrics'][k]) for k in ['Com','Cor','Eff','IA','HV']) for r in rows),
        package_requests=ledger['package'],source_scope=plan['selection_kind'],new_analysis_model_requests=0,formal_eligible=False,expert_confirmed=False)
    dest=a.out/'analysis'/j.now().replace(':','').replace('+','_');write(dest/'observations.json',rows);write(dest/'summary.json',summary)
    write(dest/'verification.json',dict(status='pass',all_eight_slots_preserved=True,plan=bind(a.out/'plan.json'),matrix=bind(a.out/'matrix.json'),
        terminal=terminal,original_SR_SP_retained=True,bindings_and_request_identity_checked=True,numerical_replay_performed=False,new_model_requests=0))
    print(j.canonical(dict(out=str(dest),**summary)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','verify','run','analyze'])
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--ids',nargs='+',choices=IDS);p.add_argument('--allow-local-calls',action='store_true');a=p.parse_args();a.out=a.out.resolve()
    if a.action=='prepare':prepare(a)
    elif a.action=='verify':validate(a.out);print(j.canonical(dict(status='validated_eight',new_model_requests=0)))
    elif a.action=='run':run(a)
    else:analyze(a)
if __name__=='__main__':main()
