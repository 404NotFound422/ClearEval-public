"""Bind author source-claim annotations to actual judge outputs and sources.

Annotations are author judgments, not expert gold or replacement scores. This
entry point checks their identity and completeness, not their scientific truth.
"""
import argparse
import collections
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'consistent_with_bound_source', 'conflicts_with_bound_source',
              'not_supported_by_current_sources', 'not_claimed_or_explicitly_unresolved'}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def bind(p):
    p=Path(p).resolve()
    return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def save(p,obj):
    with p.open('x',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


def main(args):
    out, dest = args.out.resolve(), args.dest.resolve()
    assert not dest.exists()
    packets=read(out/'readout_complete_01/metric_evidence_packets.json')
    lookup={(p['observation_id'],p['metric']):p for p in packets}
    assert len(lookup)==75
    notes=read(args.notes)
    assert notes['reviewer_role']=='author_not_independent_expert'
    prior=read(ROOT/'artifacts/cce_validation/optimizer_round3_20261011/problem_cycles/development_rubric_evidence_cycle01/author_review_notes.json')
    expected={(a+'_'+k,m) for key in prior['metric_notes'] for a,m in [key.split('/')]
              for k in ['K0','K1','K2']}
    actual={(r['observation_id'],r['metric']) for r in notes['planned_priority_reviews']}
    assert actual==expected and len(actual)==len(notes['planned_priority_reviews'])==24
    for b in notes['source_anchors'].values():
        assert bind(b['path'])['sha256']==b['sha256']
    compiled=[]
    for scope,key in [('predeclared_priority','planned_priority_reviews'),('exploratory','exploratory_reviews')]:
        for r in notes[key]:
            p=lookup[(r['observation_id'],r['metric'])]
            assert r['claims']
            for i,c in enumerate(r['claims']):
                assert c['category'] in CATEGORIES and c['source_anchors']
                assert set(c['source_anchors'])<=set(notes['source_anchors'])
                assert c['focus_zh'] and c['basis_zh']
                field=c.get('quoted_field','reasoning')
                assert field in ['reasoning','score_evidence.r']
                quoted=p['reasoning'] if field=='reasoning' else p['score_evidence']['r']
                compiled.append({**c,'claim_id':r['observation_id']+'/'+r['metric']+'/'+str(i+1),
                    'review_scope':scope,'observation_id':r['observation_id'],'metric':r['metric'],
                    'raw_score':p['raw_score'],'saved_primary_score':p['saved_primary_score'],
                    'quoted_field':field,'quoted_context':quoted,
                    'raw_source':p['raw_source'],'metric_packet_source':bind(out/'readout_complete_01/metric_evidence_packets.json'),
                    'expert_adjudicated':False,'replacement_score':None})
    denominators=notes['completeness_denominator_review']
    assert {r['observation_id'] for r in denominators}=={p['observation_id'] for p in packets}
    assert len(denominators)==15
    for r in denominators:
        assert type(r['explicit_numerator_and_denominator']) is bool
        p=lookup[(r['observation_id'],'c_param')]
        r.update({'raw_source':p['raw_source'],'reasoning':p['reasoning'],
                  'score_evidence':p['score_evidence'],'not_a_retroactive_score_error':True})
    summary={'created_utc':datetime.now(timezone.utc).isoformat(),
        'reviewer_role':notes['reviewer_role'],'planned_priority_records':24,
        'exploratory_records':len(notes['exploratory_reviews']),
        'selected_claims':len(compiled),'category_counts':dict(collections.Counter(c['category'] for c in compiled)),
        'counts_scope':'Selected author-annotated claims; not a census of every statement, an error rate, or a scientific accuracy estimate.',
        'explicit_completeness_denominators':sum(r['explicit_numerator_and_denominator'] for r in denominators),
        'completeness_records_reviewed':15,
        'new_expert_judgments':0,'new_model_calls':0,'scores_modified':False,
        'scientific_accuracy_validated':False,'actual_command':[sys.executable,*sys.argv]}
    dest.mkdir(parents=True)
    save(dest/'source_claims.json',compiled)
    save(dest/'completeness_denominators.json',denominators)
    save(dest/'summary.json',summary)
    save(dest/'verification.json',{'status':'pass','scope':'Annotation coverage, allowed categories, source hashes, and exact saved rationale contexts. Author interpretations are not independently verified.',
        'notes':bind(args.notes),'code':bind(__file__),'readout':bind(out/'readout_complete_01/verification.json'),
        'source_anchors':notes['source_anchors'],'outputs':[bind(p) for p in sorted(dest.iterdir())]})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--notes',type=Path,required=True)
    p.add_argument('--dest',type=Path,required=True)
    main(p.parse_args())
