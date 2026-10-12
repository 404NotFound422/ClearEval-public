"""Verified inputs for 67 completed raw returns and one original cancellation."""
from pathlib import Path
import cce_fieldwise_public_posthoc_replay_v1 as previous
import cce_secondary_E5_confirmation_v1 as secondary

def load_records():
    records,bindings=previous.load_records()
    require,read,bind=previous.require,previous.read,previous.bind
    for row in records:
        if 'original_metrics' in row:continue
        if row['cohort']=='Codex':
            terminals=[Path(p['path']) for p in row['paths'] if Path(p['path']).name=='terminal.json']
            require(len(terminals)==1,'CODEX_ORIGINAL_TERMINAL_UNIQUE')
            row['original_metrics']=read(terminals[0])['metrics']
        else:row['original_metrics']=row['baseline_metrics']
    out=secondary.OUT
    matrix=read(out/'matrix.json')
    require(len(matrix)==8,'ADDITIONAL_EIGHT')
    trials=[]
    for row in matrix:
        t=read(out/'run/trials'/f"{row['planned_trial_id']}.json")
        require(t['status'] in ['success','partial_components','failed'],'ALL_EIGHT_TERMINAL')
        require(t['trial_id']==row['planned_trial_id'] and t['identity']==row['identity'],'SECONDARY_TRIAL_IDENTITY')
        require(type(t['attempt']) is int and t['attempt']==1 and t['actual_request_made'] is True,'SECONDARY_ACTUAL_ATTEMPT')
        trials.append(t)
    plan,cases,verified_matrix,contract=previous.quiet(secondary.validate,out)
    require(verified_matrix==matrix,'SECONDARY_MATRIX_CHANGED')
    bindings+=plan['frozen_inputs']+[bind(out/n) for n in ['plan.json','matrix.json','cases.json','expected_contract.json']]
    ledger=previous.j.ledger_rows(previous.base.budget.LEDGER)
    for row,case,t in zip(matrix,cases,trials):
        tid=row['planned_trial_id'];at=out/'run/attempts'/f'{tid}_1'
        previous.base.verify_bindings(t['bound_artifacts'])
        receipt=read(at/'request_receipt.json')
        require(receipt['trial_id']==tid and receipt['request_id']==t['request_id'] and type(receipt['attempt']) is int and receipt['attempt']==1,'SECONDARY_RECEIPT')
        require(receipt['phase']=='confirmation' and receipt['model']==row['identity']['judge'],'SECONDARY_MODEL_PHASE')
        require([x for x in ledger if x.get('request_id')==receipt['request_id']]==[receipt],'SECONDARY_LEDGER_RECEIPT')
        raw=(at/'raw_response.txt').read_bytes().decode('utf8');provider=read(at/'provider_response.json')
        require(provider['response']==raw and previous.base.validate_provider(provider,contract['models'][0]['settings'])==raw,'SECONDARY_PROVIDER_RAW')
        doc=read(row['assets']['source_document']['path']);saved=read(at/'component_result.json')
        require(doc==previous.g.document(case['model_response'],previous.g.source_id_for_case(case)),'SECONDARY_SOURCE_DOCUMENT')
        require(saved['metrics']==t['metrics'] and saved['raw_sha256']==previous.g.rawsha(raw),'SECONDARY_SAVED_COMPONENT')
        previous.base.verify_bindings(row['step']['provenance'])
        require(all(t['metrics'][k]==row['step'][k] for k in ['sr','sp']),'SECONDARY_ORIGINAL_STEPS')
        chain=t['bound_artifacts']+[bind(out/'run/trials'/f'{tid}.json')]+list(row['assets'].values())+row['step']['provenance']
        bindings+=chain
        records.append({'cohort':'secondary8_posthoc','cell_id':row['anonymous_answer_id'],
            'anonymous_answer_id':row['anonymous_answer_id'],'status':t['status'],'case':case,'doc':doc,
            'raw':raw,'step':row['step'],'baseline_scorer':previous.fw3,
            'component_module':previous.confirmation.components,'baseline_metrics':t['metrics'],
            'original_metrics':t['metrics'],'paths':chain})
    require(len(records)==68 and sum(r['raw'] is not None for r in records)==67,'EXACT_67_RETURNS_PLUS_CANCELLATION')
    return records,previous.public.unique_bindings(bindings)
