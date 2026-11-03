"""Import expert decisions by review ID and exact reviewed text, never by score."""
import csv,gzip,hashlib,json
from copy import deepcopy
from pathlib import Path

def load(csv_path,review_path):
    raw=Path(csv_path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with gzip.open(review_path,'rt',encoding='utf8') as f:rows=json.load(f)['rows']
    expected={r['review_id']:r for r in rows};decisions=[];seen=set()
    with Path(csv_path).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            old=expected[row['review_id']]
            assert row['review_id'] not in seen,'Duplicate review ID'
            seen.add(row['review_id'])
            for key in ['id','owner','group_id','candidate_text']:
                assert row[key].replace('\r\n','\n').strip()==old[key].replace('\r\n','\n').strip(),(row['review_id'],key)
            assert row['user_decision'] in ['确认正确','确认错误']
            decisions.append(dict(**{k:old[k] for k in ['review_id','id','field','candidate_ids','reference_links','owner','group_id']},
                state='PASS' if row['user_decision']=='确认正确' else 'FAIL',notes=row['user_notes'],
                reviewed_candidate_text=row['candidate_text'],source=str(csv_path),source_sha256=digest))
    return decisions

def recalculate(packet):
    for mode in ['written','occurrence']:
        pairs=packet[mode]['pairs'];m=packet[mode]['metrics']
        for p in pairs:
            states=p['correctness_checks'].values()
            state='FAIL' if 'FAIL' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'PASS'
            p.update(checks=deepcopy(p['correctness_checks']),verification=state,
                     correctness_status='REVIEW' if state=='UNKNOWN' else state)
        a=sum(p['count'] for p in pairs if p['correctness_status']=='PASS')
        u=sum(p['count'] for p in pairs if p['correctness_status']=='REVIEW')
        m.update(confirmed_correct_credit=a,correctness_review_credit=u,
                 explicit_wrong_credit=sum(p['count'] for p in pairs if p['correctness_status']=='FAIL'))
        for name,den in [('Bio_SR',m['N_R']),('Bio_SP',m['N_C'])]:
            lo=a/den if den and packet['scope_complete'] else None
            hi=(a+u)/den if den and packet['scope_complete'] else None
            m['correctness_'+name+'_lower']=lo;m['correctness_'+name+'_upper']=hi
            m['correctness_'+name]=lo if not u else None
    return packet

def apply(packet,case,decisions):
    p=deepcopy(packet);p['human_adjudications']=[]
    for d in decisions:
        if d['id']!=case['id'] or not any(x['branch']==case['branch'] for x in d['reference_links']):continue
        changed=0;field=d['field']
        for mode in ['written','occurrence']:
            for pair in p[mode]['pairs']:
                if pair['candidate'] not in d['candidate_ids'] or field not in pair['correctness_checks']:continue
                pair.setdefault('machine_correctness_checks',deepcopy(pair['correctness_checks']))
                pair['correctness_checks'][field]=d['state']
                pair.setdefault('human_review_ids',[]).append(d['review_id']);changed+=1
        assert changed,(d['review_id'],'no linked checks')
        p['human_adjudications'].append(deepcopy(d))
        if field.startswith('declared_recipe:'):
            name=field.split(':',1)[1];a=p['correctness_recipe_audit'][name]
            a['machine_status']=a['status'];a['status']=d['state'];a['human_review_id']=d['review_id']
            for f in p['formulation_results']:
                if f['name']==name:f.update(machine_status=f['status'],status=d['state'],human_review_id=d['review_id'])
    return recalculate(p)
