"""Separate Qwen-only scheduler over an unchanged, stopped E4 source plan.

No import performs I/O. Prepare requires a new ROOT amendment. Run requires a
separate ROOT authorization. The original E4 plan and interrupted cell remain
unchanged; this script never retries a reserved cell or schedules another judge.
"""
from __future__ import annotations
import argparse, asyncio, copy, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_round2_followup_runner_v11 as old
j = old.j
budget = old.budget
QWEN = old.base.MODEL
VERSION = 'qwen-only-stability-continuation-v1'
DEFAULT_SOURCE = old.BASE/'grounded_stability_v11'
DEFAULT_OUT = old.BASE/'grounded_stability_qwen_only_v1'
SOURCE_NAMES = ['plan.json','matrix.json','expected_contract.json','cases.json','step_inputs.json','model_config.json']

def require(ok, reason):
    if not ok: raise ValueError(reason)

def bind(p): return old.bind(p)

def save_once(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n')

def dependencies(source):
    return [Path(__file__),Path(old.__file__),Path(old.base.__file__),Path(old.grounded.__file__),Path(old.scoring.__file__),
            Path(budget.__file__),budget.AUTH,*[source/n for n in SOURCE_NAMES]]

def qwen_rows(matrix):
    rows = [r for r in matrix if r['judge'] == QWEN]
    require(len(rows)==15 and {(r['anonymous_answer_id'],r['repeat_index']) for r in rows} ==
            {(a,k) for a in old.base.IDS for k in range(3)}, 'FIXED_QWEN_FIFTEEN_REQUIRED')
    for r in rows:
        require(r['reuse'] is None and type(r['repeat_index']) is int and type(r['attempt']) is int and r['attempt']==1
                and r['identity']['judge']==QWEN and r['identity']['phase']=='E4'
                and r['identity']['repeat_index']==r['repeat_index'] and r['planned_trial_id']==j.digest(r['identity']),
                'QWEN_SOURCE_CELL_IDENTITY')
    return rows

def receipt_rows(tid, ledger):
    rows = [r for r in ledger if r.get('trial_id')==tid]
    require(len(rows)<=1, 'DUPLICATE_SOURCE_RESERVATION')
    if rows:
        r=rows[0]
        require(r['model']==QWEN and r['phase']=='E4' and type(r['attempt']) is int and r['attempt']==1,
                'RESERVATION_IDENTITY')
    return rows

def classify(source, row, ledger):
    tid=row['planned_trial_id']; trial=source/'run/trials'/f'{tid}.json'
    receipt=source/'run/attempts'/f'{tid}_1/request_receipt.json'
    entries=receipt_rows(tid,ledger)
    if trial.exists():
        t=old.terminal_identity(source,row)
        require(t['phase']=='E4' and t['anonymous_answer_id']==row['anonymous_answer_id']
                and t['actual_request_made'] is True and type(t['repeat_index']) is int
                and type(t['attempt']) is int and t['attempt']==1, 'SOURCE_TERMINAL_METADATA')
        return {'disposition':'reuse_original_terminal','original_status':t['status'],
                'source_trial':bind(trial),'reservation':entries[0]}
    if entries:
        if receipt.exists(): require(j.read(receipt)==entries[0], 'SOURCE_RECEIPT_LEDGER_MISMATCH')
        return {'disposition':'user_cancelled_no_retry','original_status':'reserved_nonterminal',
                'source_trial':None,'reservation':entries[0]}
    require(not receipt.exists() and not (source/'run/attempts'/f'{tid}_1').exists(), 'UNRESOLVED_LOCAL_ATTEMPT')
    return {'disposition':'unrequested_eligible','original_status':'unrequested','source_trial':None,'reservation':None}

def prepare(args):
    require(not args.out.exists(), 'NEW_OUTPUT_ONLY')
    amendment=j.read(args.amendment)
    require(amendment.get('status')=='approved_for_qwen_only_continuation' and amendment.get('authorized_by')=='root_agent'
            and amendment.get('original_process_stopped') is True and amendment.get('forbid_other_evaluators') is True
            and amendment.get('allowed_judges')==[QWEN] and amendment.get('phase')=='E4'
            and amendment.get('max_new_requests')==11 and amendment.get('retry_reserved_cells') is False,
            'EXPLICIT_ROOT_QWEN_ONLY_AMENDMENT_REQUIRED')
    old.base.verify_required(amendment['bindings'],dependencies(args.source))
    original_plan,cases,matrix,contracts=old.validate(args.source)
    require(original_plan['phase']=='E4' and original_plan['planned_observations']==30, 'ORIGINAL_E4_PLAN_REQUIRED')
    ledger=budget.counts()['requests']; rows=qwen_rows(matrix); frozen=[]
    for row in rows: frozen.append({'source_cell':copy.deepcopy(row),**classify(args.source,row,ledger)})
    counts={k:sum(x['disposition']==k for x in frozen) for k in ['reuse_original_terminal','user_cancelled_no_retry','unrequested_eligible']}
    require(counts=={'reuse_original_terminal':3,'user_cancelled_no_retry':1,'unrequested_eligible':11}, 'SOURCE_STATE_CHANGED_REVIEW_REQUIRED')
    cancelled=[x['source_cell']['planned_trial_id'] for x in frozen if x['disposition']=='user_cancelled_no_retry']
    require(amendment.get('cancelled_trial_ids')==cancelled, 'CANCELLED_TRIAL_NOT_EXPLICITLY_BOUND')
    require(all(x['original_status']=='success' for x in frozen if x['disposition']=='reuse_original_terminal'),
            'ACTUAL_SOURCE_STATUS_CHANGED_REVIEW_REQUIRED')
    budget.guard('E4',11,600)
    args.out.mkdir(parents=True)
    for n in ['cases.json','step_inputs.json','model_config.json']:
        (args.out/n).write_bytes((args.source/n).read_bytes())
    save_once(args.out/'expected_contract.json',{QWEN:contracts[QWEN]})
    save_once(args.out/'matrix.json',frozen)
    bound=dependencies(args.source)+[args.amendment,*[args.out/n for n in ['cases.json','step_inputs.json','model_config.json','expected_contract.json','matrix.json']]]
    for item in frozen:
        if item['source_trial']:
            bound.append(Path(item['source_trial']['path']))
            bound.extend(Path(b['path']) for b in j.read(item['source_trial']['path'])['bound_artifacts'])
        elif item['reservation']:
            p=args.source/'run/attempts'/f"{item['source_cell']['planned_trial_id']}_1"
            bound.extend(x for x in p.iterdir() if x.is_file())
    plan={'status':'frozen_before_continuation','version':VERSION,'phase':'E4','source_out':str(args.source.resolve()),
          'models':[QWEN],'planned_observations':15,'repeats':3,'fixed_answers':5,'max_attempts':1,
          'planned_new_requests':11,**counts,'original_batch_still_incomplete':True,'original_plan_not_modified':True,
          'cancelled_cells_not_technical_failures_or_successes':True,'no_cross_judge_claim':True,
          'scientific_acceptance':False,'root_amendment':bind(args.amendment),
          'frozen_inputs':[bind(p) for p in dict.fromkeys(bound)],'actual_command':[sys.executable,*sys.argv]}
    save_once(args.out/'plan.json',plan)
    print(j.canonical({'status':'prepared_qwen_only_no_calls',**counts,'new_model_requests':0}))

def validate(out):
    p=j.read(out/'plan.json')
    require(p['status']=='frozen_before_continuation' and p['models']==[QWEN] and p['planned_observations']==15
            and p['planned_new_requests']==11 and p['max_attempts']==1,'CONTINUATION_PLAN_CHANGED')
    old.base.verify_bindings(p['frozen_inputs']); source=Path(p['source_out'])
    _,cases,matrix,contracts=old.validate(source)
    rows=j.read(out/'matrix.json'); require([r['source_cell'] for r in rows]==qwen_rows(matrix),'ORIGINAL_SUBSET_CHANGED')
    require(j.read(out/'expected_contract.json')=={QWEN:contracts[QWEN]},'FULL_QWEN_CONTRACT_CHANGED')
    require((out/'cases.json').read_bytes()==(source/'cases.json').read_bytes()
            and (out/'step_inputs.json').read_bytes()==(source/'step_inputs.json').read_bytes(),'SOURCE_OR_STEPS_CHANGED')
    ledger=budget.counts()['requests']
    for item in rows:
        row=item['source_cell']; tid=row['planned_trial_id']
        if item['disposition']!='unrequested_eligible':
            require(classify(source,row,ledger)=={k:item[k] for k in ['disposition','original_status','source_trial','reservation']},
                    'FROZEN_ORIGINAL_STATE_CHANGED')
        else:
            require(not (source/'run/trials'/f'{tid}.json').exists()
                    and not (source/'run/attempts'/f'{tid}_1').exists(),'OLD_SCHEDULER_RESTARTED')
    return p,cases,rows,contracts[QWEN]

def current_qwen_contract(out):
    # E2 selection asks the unchanged original factory for Qwen only. No Llama metadata/query/transport.
    contracts,_=old.model_contracts(out/'model_config.json','E2')
    require(set(contracts)=={QWEN},'OTHER_JUDGE_CONTRACT_FORBIDDEN')
    return contracts[QWEN]

def preflight(args):
    plan,_,_,expected=validate(args.out)
    require(current_qwen_contract(args.out)==expected,'QWEN_FULL_RUNTIME_CONTRACT_DRIFT')
    value={'status':'pass','phase':'E4','models':[QWEN],'planned_observations':15,'new_model_requests':0,
           'bindings':[bind(args.out/n) for n in ['plan.json','matrix.json','expected_contract.json']]+[bind(__file__)]}
    save_once(args.out/'preflight.json',value)
    print(j.canonical({'status':'pass','new_model_requests':0}))

async def execute_qwen(out,row,case,public):
    require(row['judge']==QWEN and row['identity']['judge']==QWEN and row['identity']['phase']=='E4'
            and type(row['repeat_index']) is int and type(row['attempt']) is int and row['attempt']==1,
            'ONLY_QWEN_TRANSPORT_ALLOWED')
    require(public['model']==j.read(out/'expected_contract.json')[QWEN]['models'][0]['settings']['model'],
            'QWEN_TRANSPORT_MODEL_CHANGED')
    return await old.execute_cell(out,'E4',row,case,public)

async def run(args):
    require(args.allow_local_calls,'EXPLICIT_LOCAL_CALL_FLAG_REQUIRED')
    plan,cases,items,contract=validate(args.out);pre=j.read(args.out/'preflight.json')
    require(pre['status']=='pass' and pre['models']==[QWEN],'QWEN_PREFLIGHT_REQUIRED')
    old.base.verify_bindings(pre['bindings']); approval=j.read(args.run_authorization)
    require(approval.get('status')=='approved_for_local_run' and approval.get('authorized_by')=='root_agent'
            and approval.get('phase')=='E4' and approval.get('allowed_judges')==[QWEN]
            and approval.get('forbid_other_evaluators') is True,'ROOT_QWEN_ONLY_RUN_AUTHORIZATION')
    old.base.verify_required(approval['bindings'],[args.out/n for n in ['plan.json','matrix.json','expected_contract.json','preflight.json']]+[Path(__file__)])
    require(type(args.max_new_calls) is int and 1<=args.max_new_calls<=11,'MAX_NEW_CALLS_LIMIT')
    require(current_qwen_contract(args.out)==contract,'QWEN_FULL_RUNTIME_CONTRACT_DRIFT')
    ledger=budget.counts()['requests'];pending=[]
    for item in items:
        if item['disposition']!='unrequested_eligible': continue
        row=item['source_cell'];tid=row['planned_trial_id'];terminal=args.out/'run/trials'/f'{tid}.json'
        if terminal.exists(): old.terminal_identity(args.out,row)
        else:
            require(not receipt_rows(tid,ledger) and not (args.out/'run/attempts'/f'{tid}_1').exists(),
                    'RESERVED_OR_LOCAL_NONTERMINAL_NO_RETRY')
            pending.append(row)
    indexed={c['case_id']:c for c in cases};made=0
    for row in pending[:args.max_new_calls]:
        validate(args.out);budget.guard('E4',1,600)
        await execute_qwen(args.out,row,indexed[row['case_id']],contract['models'][0]['settings']);made+=1
    print(j.canonical({'status':'qwen_only_run_ended','new_model_requests':made,'original_batch_still_incomplete':True}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','preflight','run'])
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE);p.add_argument('--out',type=Path,default=DEFAULT_OUT)
    p.add_argument('--amendment',type=Path);p.add_argument('--run-authorization',type=Path)
    p.add_argument('--allow-local-calls',action='store_true');p.add_argument('--max-new-calls',type=int,default=1)
    a=p.parse_args();a.source=a.source.resolve();a.out=a.out.resolve()
    if a.action=='prepare':prepare(a)
    elif a.action=='preflight':preflight(a)
    else:asyncio.run(run(a))

if __name__=='__main__':main()
