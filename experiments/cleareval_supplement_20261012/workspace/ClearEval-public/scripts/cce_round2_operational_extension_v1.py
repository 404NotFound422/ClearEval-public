"""Additive deadline authorization; frozen scientific runners and AUTH stay unchanged.

No root approval is created here. A signed-by-root metadata record and its exact
SHA are required before patching only the in-process clock and reservation writer.
"""
from __future__ import annotations
import argparse,runpy,sys,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_budget as budget
j=budget.j
OUT=budget.OUT/'operational_extension_v1'
DEADLINE='2026-10-10T10:21:00+00:00'
OLD_DEADLINE='2026-10-10T08:51:00+00:00'
TARGETS={'confirmation':ROOT/'scripts/cce_round2_confirmation_runtime_qwen_only_v1.py',
    'subagent':ROOT/'scripts/cce_round2_subagent_judge_v3.py'}
ALLOWED_MODELS={'local_qwen27b_q8_development','codex_subagent_backend_unobserved'}
ALLOWED_ACTIONS={'confirmation':{'run','preflight','analyze'},
    'subagent':{'reserve','record-dispatch','import-result','mark-missing','status'}}
def require(ok,why):
    if not ok:raise ValueError(why)
def bind(p):return {'path':str(Path(p).resolve()),'sha256':j.filehash(p)}
def verify(b):
    require(isinstance(b,dict) and set(b)=={'path','sha256'},'EXACT_BINDING')
    p=Path(b['path']).resolve();require(j.filehash(p)==b['sha256'],'BOUND_FILE_CHANGED:'+str(p));return p
def once(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(value if isinstance(value,bytes) else (j.canonical(value)+'\n').encode('utf8'))

def validate_extension(path,sha):
    path=Path(path).resolve();require(j.filehash(path)==sha,'EXACT_ROOT_EXTENSION_SHA_REQUIRED');a=j.read(path)
    require(a.get('status')=='approved_additive_operational_extension' and a.get('recorded_by')=='root_agent'
        and a.get('explicit_user_continuation_confirmed') is True and bool(a.get('user_authorization_note')),'ROOT_EXTENSION_APPROVAL_REQUIRED')
    require(a.get('previous_deadline_utc')==OLD_DEADLINE and a.get('deadline_utc')==DEADLINE
        and a.get('deadline_not_rolling_from_execution') is True,'EXACT_PREVIOUSLY_PROPOSED_DEADLINE')
    require(a.get('original_authorization')==bind(budget.AUTH) and j.filehash(budget.AUTH)==budget.AUTH_SHA
        and a.get('budget_module')==bind(budget.__file__) and a.get('wrapper')==bind(__file__),'ORIGINAL_AUTH_OR_FROZEN_CODE_CHANGED')
    require(a.get('authorized_new_local_requests')==100 and a.get('new_package_limit')==394
        and a.get('phase_new_request_limits')==budget.LIMITS and type(a.get('max_attempts_per_cell')) is int
        and a['max_attempts_per_cell']==1 and a.get('no_llama') is True and a.get('no_scientific_or_sampling_change') is True,
        'EXTENSION_MAY_CHANGE_TIME_ONLY')
    require(a.get('allowed_targets')=={k:bind(p) for k,p in TARGETS.items()},'ONLY_TWO_FROZEN_ENTRYPOINTS_ALLOWED')
    require(a.get('starting_package_requests')==354 and a.get('starting_round_requests')==60,'EXTENSION_STARTING_COUNTS')
    prefix=verify(a['ledger_prefix']);raw=prefix.read_bytes()
    require(budget.LEDGER.read_bytes().startswith(raw),'EXTENSION_LEDGER_PREFIX_CHANGED')
    rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    req=[r for r in rows if r.get('event')=='request_started']
    require(len(req)==354 and sum(r.get('round_id')==budget.ROUND for r in req)==60,'EXACT_354_60_PREFIX_REQUIRED')
    c=budget.counts();require(c['package']>=354 and c['round']>=60,'CURRENT_LEDGER_PRECEDES_EXTENSION')
    return a

def install(path,sha):
    """Preserves AUTH, authorization, guard, counts, limits, locking and no retry."""
    a=validate_extension(path,sha)
    def remaining():
        # Revalidate original authorization and the additive record on every guard.
        budget.authorization();require(j.filehash(path)==sha,'EXTENSION_CHANGED_DURING_RUN')
        return (datetime.fromisoformat(a['deadline_utc'])-datetime.now(timezone.utc)).total_seconds()
    def reserve(phase,trial_id,model,transport_seconds):
        require(phase in {'E4','confirmation'} and model in ALLOWED_MODELS,'EXTENSION_NO_NEW_DEVELOPMENT_OR_LLAMA')
        with j.ledger_lock(budget.LEDGER):
            c=budget.guard(phase,1,transport_seconds)
            request_id=j.digest({'trial_id':trial_id,'attempt':1})
            require(all(r.get('request_id')!=request_id for r in j.ledger_rows(budget.LEDGER)),'CELL_ALREADY_RESERVED_NO_RETRY')
            row={'event':'request_started','request_id':request_id,'trial_id':trial_id,
                'attempt':1,'model':model,'started_utc':j.now(),'package_request_index':c['package']+1,
                'round_id':budget.ROUND,'phase':phase,'authorization_sha256':budget.AUTH_SHA,
                'extension_authorization_sha256':sha,'effective_deadline_utc':a['deadline_utc']}
            with budget.LEDGER.open('a',encoding='utf8') as f:f.write(j.canonical(row)+'\n')
        return row
    budget.time_remaining=remaining;budget.reserve=reserve
    return a

def draft():
    require(not (OUT/'amendment_draft.json').exists(),'DRAFT_ALREADY_EXISTS')
    c=budget.counts();require((c['package'],c['round'])==(354,60),'EXPECTED_PAUSED_354_60')
    prefix=OUT/'ledger_at_extension_354.jsonl';once(prefix,budget.LEDGER.read_bytes())
    a={'status':'draft_not_authorized','recorded_by':None,'explicit_user_continuation_confirmed':False,
        'user_authorization_note':'ROOT must record the actual continuation and the earlier 90-minute proposal; no invented quotation.',
        'previous_deadline_utc':OLD_DEADLINE,'deadline_utc':DEADLINE,'deadline_not_rolling_from_execution':True,
        'original_authorization':bind(budget.AUTH),'budget_module':bind(budget.__file__),'wrapper':bind(__file__),
        'authorized_new_local_requests':100,'new_package_limit':394,'phase_new_request_limits':budget.LIMITS,
        'max_attempts_per_cell':1,'no_llama':True,'no_scientific_or_sampling_change':True,
        'starting_package_requests':354,'starting_round_requests':60,'ledger_prefix':bind(prefix),
        'allowed_targets':{k:bind(p) for k,p in TARGETS.items()},
        'receipt_semantics':'authorization_sha256 retains original count/scope authorization; extension_authorization_sha256 supplies additive time authorization',
        'actual_command':[sys.executable,*sys.argv],'new_requests':0}
    once(OUT/'amendment_draft.json',a)
    print(j.canonical({'status':'draft_only','out':str(OUT),'new_requests':0}))

def metadata_check():
    """Only bindings are validated. Does not parse cases, selected bodies or raw."""
    import cce_round2_confirmation_runtime_qwen_only_v1 as runtime
    import cce_round2_subagent_judge_v3 as subagent
    results=[]
    for label,out in [('confirmation',runtime.gate.OUT),('subagent',subagent.OUT)]:
        p=j.read(out/'plan.json');runtime.gate.verify_bindings(p['frozen_inputs'])
        results.append({'target':label,'plan':bind(out/'plan.json'),'frozen_bindings':len(p['frozen_inputs']),
            'status':'original_binding_validator_pass','case_content_parsed':False})
    rel=j.read(runtime.gate.OUT/'source_release_plan.json')['root_release'];runtime.gate.verify(rel)
    release=j.read(rel['path'])
    require(release['assets']['authorization']==bind(budget.AUTH),'PREPARED_ORIGINAL_AUTH_BINDING')
    return {'status':'metadata_bindings_pass','checks':results,'original_AUTH':str(budget.AUTH),'original_AUTH_SHA':budget.AUTH_SHA,
        'full_validate_run_gate_not_executed':'They parse prepared source bodies; unchanged runner executes them before actual dispatch.',
        'new_requests':0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft','metadata-check','execute'])
    p.add_argument('--amendment',type=Path);p.add_argument('--amendment-sha256');p.add_argument('--target',choices=TARGETS)
    args,rest=p.parse_known_args()
    if args.action=='draft':draft();return
    if args.action=='metadata-check':
        result=metadata_check();once(OUT/'metadata_verification.json',result);print(j.canonical(result));return
    require(args.amendment and args.amendment_sha256 and args.target,'EXPLICIT_ROOT_EXTENSION_AND_TARGET_REQUIRED')
    rest=rest[1:] if rest[:1]==['--'] else rest
    require(rest and rest[0] in ALLOWED_ACTIONS[args.target],'NO_NEW_PREPARATION_OR_UNLISTED_ACTION')
    a=install(args.amendment,args.amendment_sha256)
    target=verify(a['allowed_targets'][args.target]);sys.argv=[str(target),*rest]
    runpy.run_path(str(target),run_name='__main__')
if __name__=='__main__':main()
