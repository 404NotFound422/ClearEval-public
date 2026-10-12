"""Execute a prepared source-context comparison only after additional authorization.

The existing Round 3 request/processing function is reused unchanged with a
separate budget object. Old modules and their global namespaces are not mutated.
"""
import argparse
import asyncio
import copy
import csv
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_prepare_source_context_validation_v1 as prep
import cce_round3_runner_v2 as original
import cce_posthoc_components_v7 as processor

j = original.j
ROUND = 'source_context_validation_20261012'
PHASE = 'source_context'
LEDGER = ROOT / 'artifacts/cce_validation/judges/request_ledger.jsonl'


def save(path, obj):
    original.save_once(path, obj)


class ApprovedBudget:
    ROUND = ROUND

    def __init__(self, out):
        self.out = out
        self.path = out / 'additional_authorization.json'

    def authorization(self):
        if not self.path.exists():
            raise ValueError('ADDITIONAL_TEN_CALL_AUTHORIZATION_NOT_RECEIVED; no request made')
        a = j.read(self.path)
        assert a['status'] == 'explicit_user_approval_recorded'
        assert a['user_reply'].strip()
        assert (a['starting_package_requests'], a['authorized_new_requests'], a['new_package_limit']) == (428,10,438)
        assert a['max_attempts'] == 1 and a['automatic_retries'] is False
        assert a['execution_seal_sha256'] == j.filehash(self.out / 'execution_seal.json')
        start, end = (datetime.fromisoformat(a[k]) for k in ['start_utc','deadline_utc'])
        assert 0 < (end-start).total_seconds() <= 7200
        assert end <= datetime.fromisoformat('2026-10-12T02:43:01+00:00')
        return a

    def counts(self):
        prefix = (self.out / 'baseline_ledger_snapshot.jsonl').read_bytes()
        assert LEDGER.read_bytes().startswith(prefix), 'HISTORICAL_LEDGER_CHANGED'
        requests = [r for r in j.ledger_rows(LEDGER) if r.get('event') == 'request_started']
        own = [r for r in requests if r.get('round_id') == ROUND]
        assert len(requests) == 428 + len(own), 'OTHER_NEW_REQUESTS_REQUIRE_RECONCILIATION'
        assert len({r['request_id'] for r in requests}) == len(requests)
        assert [r['package_request_index'] for r in own] == list(range(429,429+len(own)))
        return {'package':len(requests), 'round':len(own), 'requests':requests}

    def guard(self, seconds=0):
        a, c = self.authorization(), self.counts()
        assert c['round'] < 10 and c['package'] < 438, 'AUTHORIZED_REQUEST_LIMIT_REACHED'
        remaining = (datetime.fromisoformat(a['deadline_utc'])-datetime.now(timezone.utc)).total_seconds()
        assert remaining > seconds + 30, 'AUTHORIZED_TIME_INSUFFICIENT_FOR_REQUEST'
        return c

    def reserve(self, phase, trial_id, model, seconds):
        assert phase == PHASE and model == 'qwen3.8:27b-q8_0-local'
        with j.ledger_lock(LEDGER):
            c = self.guard(seconds)
            assert not any(r['trial_id'] == trial_id for r in c['requests']), 'NO_AUTOMATIC_RETRY'
            request = {'event':'request_started',
                'request_id':j.digest({'round_id':ROUND,'trial_id':trial_id,'attempt':1}),
                'trial_id':trial_id,'attempt':1,'model':model,'started_utc':j.now(),
                'package_request_index':c['package']+1,'round_id':ROUND,'phase':phase,
                'authorization_sha256':j.filehash(self.path)}
            with LEDGER.open('a',encoding='utf-8') as f:
                f.write(j.canonical(request)+'\n')
        return request


def bound_functions(out):
    budget = ApprovedBudget(out)
    # Function code and scientific processing are unchanged. Only the explicit
    # authorization/counting scope differs from the exhausted Round 3 scope.
    environment = {**vars(original), 'budget':budget}
    execute = types.FunctionType(original.execute_cell.__code__, environment, name='execute_source_context_cell')
    terminal = types.FunctionType(original.terminal.__code__, environment,
        name='read_source_context_terminal', argdefs=original.terminal.__defaults__)
    return budget, execute, terminal


def seal(out):
    prep.verify(out)
    assert not (out/'execution_seal.json').exists()
    proposal = j.read(out/'proposal.json')
    rows = j.read(out/'matrix.json')
    steps = j.read(out/'steps.json')
    public = j.read(out/'public_model.json')
    schedule = j.read(out/'execution_order.json')['new_request_order']
    byid = {r['observation_id']:r for r in rows}
    execution = []
    for oid in schedule:
        r = byid[oid]
        assert r['needs_new_request'] and r['status'] == 'planned_not_requested'
        identity = {'round_id':ROUND,'phase':PHASE,'case_id':r['case_id'],
            'observation_id':oid,'condition':r['condition'],'repeat_index':0,'attempt':1,
            'input_bundle_sha256':j.filehash(out/'freeze.json'),
            'payload_sha256':r['payload_identity_sha256']}
        # All current prepared prompts are well inside the existing byte-bound
        # admission rule. This is not an asserted native token measurement.
        bound = r['prompt_utf8_bytes'] + public['max_output_tokens'] + 256
        assert bound <= public['num_ctx']
        execution.append({'case_id':r['case_id'],'anonymous_answer_id':oid,'observation_id':oid,
            'question_id':r['question_id'],'repeat_index':0,'identity':identity,
            'planned_trial_id':j.digest(identity),'step':steps[r['case_id']],
            'assets':{'payload':r['payload'],'doc':r['source_document'],'prompt':r['prompt']},
            'fits_context':True,'context_bound':bound})
    save(out/'execution_matrix.json',execution)
    save(out/'plan.json',{'round_id':ROUND,'phase':PHASE,'public_model':public,
        'processor':'cce_posthoc_components_v7','planned_new_requests':10,
        'archived_baselines':5,'proposal':original.bind(out/'proposal.json')})
    required = [Path(__file__),Path(prep.__file__),Path(original.__file__),
        out/'freeze.json',out/'proposal.json',out/'plan.json',out/'execution_matrix.json',
        out/'ANALYSIS_PLAN.md',out/'README_zh.md']
    save(out/'execution_seal.json',{'created_utc':j.now(),'status':'prepared_not_authorized',
        'bindings':[original.bind(p) for p in required],
        'new_model_calls':0,'max_new_requests':10,'automatic_retries':False})
    return {'status':'execution_entry_prepared','new_model_calls':0,'new_slots':10,'cached_baselines':5}


def validate(out):
    prep.verify(out)
    seal_data = j.read(out/'execution_seal.json')
    original.base.verify_bindings(seal_data['bindings'])
    plan, rows = j.read(out/'plan.json'),j.read(out/'execution_matrix.json')
    assert plan['round_id'] == ROUND and plan['phase'] == PHASE and len(rows) == 10
    for r in rows:
        assert r['planned_trial_id'] == j.digest(r['identity'])
        original.base.verify_bindings(list(r['assets'].values()))
        source = next(x for x in j.read(out/'matrix.json') if x['observation_id'] == r['observation_id'])
        assert r['assets']['payload'] == source['payload'] and r['assets']['doc'] == source['source_document']
        assert r['step'] == j.read(out/'steps.json')[r['case_id']]
        assert r['identity']['payload_sha256'] == source['payload_identity_sha256']
    return plan, rows


def budget_snapshot(out):
    b = ApprovedBudget(out)
    a, c = b.authorization(), b.counts()
    return {'round_id':ROUND,'attempts_recorded':c['package'],'package_limit':438,
        'round_attempts':c['round'],'round_limit':10,'remaining_request_capacity':10-c['round'],
        'authorization':original.bind(b.path),'ledger':original.bind(LEDGER),
        'deadline_utc':a['deadline_utc'],'automatic_retries':False,
        'human_budget':{'experts':1,'development':5,'holdout':15}}


async def run(out):
    plan, rows = validate(out)
    budget, execute, terminal = bound_functions(out)
    budget.authorization()  # This precedes all runtime network and new writes.
    cases = {c['case_id']:c for c in j.read(out/'cases.json')['cases']}
    actual, models = original.base.science_contract(out/'model_config.json',True)
    assert models[0]['public'] == plan['public_model'], 'RUNTIME_MODEL_OR_DECODING_CHANGED'
    save(out/'commands'/('runtime_'+j.now().replace(':','_')+'.json'),
        {'created_utc':j.now(),'actual_model':models[0]['public'],'new_generation_requests':0})
    started = {r['trial_id'] for r in budget.counts()['requests']}
    for row in rows:
        if original.terminal_path(out,row).exists():
            terminal(out,row)
        else:
            assert row['planned_trial_id'] not in started, 'STARTED_REQUEST_HAS_NO_TERMINAL; inspect live process before resuming'
    made = 0
    for row in rows:
        if original.terminal_path(out,row).exists():
            continue
        validate(out)
        budget.guard(plan['public_model']['timeout_seconds'])
        await execute(out,row,cases[row['case_id']],plan,processor)
        terminal(out,row)
        made += 1
        state = budget_snapshot(out)
        j.save(out/'budget_snapshot.json',state)
        global_budget = ROOT/'artifacts/cce_validation/budget.json'
        before = out/'global_budget_before_execution.json'
        if not before.exists():
            original.bytes_once(before,global_budget.read_bytes())
        j.save(global_budget,state)
    return {'new_generation_requests_this_run':made,'budget':budget_snapshot(out)}


def analyze(out):
    plan, rows = validate(out)
    budget, _, terminal = bound_functions(out)
    observations = []
    for b in j.read(out/'baseline_per_answer.json'):
        observations.append({**b,'condition':'K0','status':'archived_success_reused','actual_new_request':False})
    pending = []
    for row in rows:
        oid = row['observation_id']
        if not original.terminal_path(out,row).exists():
            pending.append(oid)
            observations.append({'observation_id':oid,'answer_id':oid.split('_')[0],
                'question_id':row['question_id'],'condition':oid.split('_')[1],
                'status':'pending','metrics':None,'actual_new_request':False})
            continue
        t = terminal(out,row)
        assert t['metrics']['sr'] == row['step']['sr'] and t['metrics']['sp'] == row['step']['sp']
        observations.append({'observation_id':oid,'answer_id':oid.split('_')[0],
            'question_id':row['question_id'],'condition':oid.split('_')[1],
            'status':t['status'],'metrics':t['metrics'],'actual_new_request':t['actual_request_made'],
            'terminal':original.bind(original.terminal_path(out,row))})
    lookup = {r['observation_id']:r for r in observations}
    paired = []
    for p in j.read(out/'paired_contrasts.json'):
        left,right = lookup[p['left']],lookup[p['right']]
        observed = left['status'] != 'pending' and right['status'] != 'pending'
        changes = {}
        if observed:
            for metric in original.METRICS:
                a,b = left['metrics'][metric],right['metrics'][metric]
                changes[metric] = {'left':a,'right':b,
                    'delta':b-a if original.finite(a) and original.finite(b) else None,
                    'both_finite':original.finite(a) and original.finite(b)}
        paired.append({**p,'both_observed':observed,'metrics':changes})
    folder = out/'analysis'/j.now().replace(':','_')
    summary = {'status':'all_requests_terminal' if not pending else 'incomplete',
        'archived_baselines':5,'new_terminal':10-len(pending),'new_pending':len(pending),
        'new_status_counts':{s:sum(o['condition']!='K0' and o['status']==s for o in observations)
            for s in ['success','partial','failed','local_failed']},
        'observed_pairs':sum(p['both_observed'] for p in paired),'planned_pairs':10,
        'new_model_calls_by_analysis':0,'scientific_source_claim_audit':'pending',
        'scientific_accuracy_validated':False}
    save(folder/'observations.json',observations)
    save(folder/'paired_results.json',paired)
    save(folder/'summary.json',summary)
    with (folder/'observations.csv').open('x',encoding='utf-8',newline='') as f:
        fields=['observation_id','answer_id','question_id','condition','status',*original.METRICS]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for o in observations:
            writer.writerow({**{k:o[k] for k in fields[:5]},**(o['metrics'] or {})})
    j.save(out/'latest_analysis.json',{'summary':original.bind(folder/'summary.json'),
        'observations':original.bind(folder/'observations.json'),'pairs':original.bind(folder/'paired_results.json')})
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['seal','verify','run','analyze'])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if args.action=='seal': result=seal(out)
    elif args.action=='verify':
        plan,rows=validate(out);result={'status':'pass','new_slots':len(rows),'new_model_calls':0}
    elif args.action=='run': result=asyncio.run(run(out))
    else: result=analyze(out)
    print(j.canonical(result))
