"""Second-round local-request limits under explicit user authorization."""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j

OUT=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
AUTH=OUT/'authorization.json'
AUTH_SHA='03b0dc55ec21ac3f94094e581a7a87605617222e5068fd291b01ebe4bfc990b6'
LEDGER=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
ROUND='optimizer_round2_20261010'
LIMITS={'development':30,'E2':21,'E4':30,'confirmation':16}

def require(ok,why):
    if not ok:raise ValueError(why)

def authorization():
    require(j.filehash(AUTH)==AUTH_SHA,'USER_AUTHORIZATION_BYTES_CHANGED')
    a=j.read(AUTH)
    require(a['phase_new_request_limits']==LIMITS and a['starting_package_requests']==294
        and a['new_package_limit']==394 and a['max_attempts_per_cell']==1,'AUTHORIZATION_SCOPE_CHANGED')
    return a

def counts():
    a=authorization();raw=LEDGER.read_bytes();prefix=(OUT/'ledger_at_authorization.jsonl').read_bytes()
    require(j.filehash(OUT/'ledger_at_authorization.jsonl')==a['historical_ledger_sha256'] and raw.startswith(prefix),
        'PREVIOUS_LEDGER_PREFIX_CHANGED')
    rows=j.ledger_rows(LEDGER);requests=[r for r in rows if r.get('event')=='request_started']
    own=[r for r in requests if r.get('round_id')==ROUND]
    require(len(requests)==294+len(own),'UNREGISTERED_OTHER_REQUEST_IN_NEW_ROUND')
    require([r['package_request_index'] for r in own]==list(range(295,295+len(own))),'ROUND_LEDGER_ORDER')
    require(len({r['request_id'] for r in requests})==len(requests),'DUPLICATE_REQUEST_ID')
    return {'package':len(requests),'round':len(own),
        'phase':{k:sum(r.get('phase')==k for r in own) for k in LIMITS},'requests':requests}

def time_remaining():
    a=authorization()
    return (datetime.fromisoformat(a['deadline_utc'])-datetime.now(timezone.utc)).total_seconds()

def guard(phase,planned_new=1,transport_seconds=0):
    require(phase in LIMITS,'UNAUTHORIZED_PHASE')
    a=authorization();c=counts()
    require(type(planned_new) is int and planned_new>=0,'INVALID_PLANNED_COUNT')
    require(time_remaining()>transport_seconds+30,'AUTHORIZED_DEADLINE_INSUFFICIENT')
    require(c['phase'][phase]+planned_new<=LIMITS[phase],'PHASE_CALL_LIMIT')
    require(c['round']+planned_new<=a['authorized_new_local_requests'] and
        c['package']+planned_new<=a['new_package_limit'],'ROUND_OR_PACKAGE_CALL_LIMIT')
    return {k:v for k,v in c.items() if k!='requests'}

def reserve(phase,trial_id,model,transport_seconds):
    """One ledger reservation immediately before one real transport invocation."""
    with j.ledger_lock(LEDGER):
        c=guard(phase,1,transport_seconds)
        request_id=j.digest({'trial_id':trial_id,'attempt':1})
        require(all(r.get('request_id')!=request_id for r in j.ledger_rows(LEDGER)),
            'CELL_ALREADY_RESERVED_NO_RETRY')
        row={'event':'request_started','request_id':request_id,'trial_id':trial_id,
            'attempt':1,'model':model,'started_utc':j.now(),'package_request_index':c['package']+1,
            'round_id':ROUND,'phase':phase,'authorization_sha256':AUTH_SHA}
        with LEDGER.open('a',encoding='utf8') as f:f.write(j.canonical(row)+'\n')
    return row

if __name__=='__main__':
    c=counts();print(j.canonical({k:v for k,v in c.items() if k!='requests'}))
