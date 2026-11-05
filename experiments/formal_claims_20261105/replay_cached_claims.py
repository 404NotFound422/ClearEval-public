"""Patch claims for explicitly selected cases, reusing frozen V5 alignments."""
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import cleareval_complete_scoring as scorer
from cleareval_scoring import scoring_v6
BASELINE_VERIFIED=ROOT/'dataset/benchmark185/2026-11-03/verified_checks.json.gz'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case-id',action='append',required=True)
    args=ap.parse_args()
    ids=set(args.case_id)
    receipt=scorer.read(BASELINE_VERIFIED.with_name('run_receipt.json'))
    assert receipt['input_sha256']==scorer.sha(scorer.DEFAULT_INPUT)
    cases=[c for c in scorer.read(scorer.DEFAULT_INPUT)['cases'] if c['id'] in ids]
    assert {c['id'] for c in cases}==ids,'Unknown requested case'
    # This path only changes recipe attribution. Numeric stock-name repairs
    # require a targeted rematch and cannot silently reuse an older alignment.
    import re
    for c in cases:
        assert not re.search(r'\b(?:CUBIC[-\s]*R|reagent\s*)\d{2,}\b',c['answer'],re.I), 'Use targeted rematching for numeric stock names'
    cached={(r['id'],r['branch']):r['packet'] for r in scorer.read(BASELINE_VERIFIED)}
    previous={(r['input_id'],b['branch']):b['metrics'] for r in scorer.read(scorer.DEFAULT_PREVIOUS) for b in r['branches']}
    policy=scorer.read(scorer.POLICY_PATH)
    rows=[]
    for c in cases:
        key=(c['id'],c['branch']);old=cached[key]
        new=scoring_v6.apply_to_cached_packet(c,old)
        before=scorer.correctness(c,old,previous[key],policy)
        after=scorer.correctness(c,new,previous[key],policy)
        changed=[]
        for mode in ['written','occurrence']:
            a=old[mode]['pairs'];b=new[mode]['pairs']
            assert [(p['candidate'],p['reference'],p['count']) for p in a]==[(p['candidate'],p['reference'],p['count']) for p in b]
            changed += [dict(mode=mode,candidate=x['candidate'],before=x['correctness_status'],after=y['correctness_status'])
                        for x,y in zip(a,b) if x['correctness_status']!=y['correctness_status']]
        rows.append(dict(id=c['id'],branch=c['branch'],matched_pairs=len(old['written']['pairs']),
            changed_pair_states=changed,
            recipe_conflicts=[dict(candidate=a['candidate'],stock=a['stock']) for a in new['operation_claim_audit'] if a['status']=='FAIL'],
            preserved_human_reviews=len(new['human_adjudications']),
            correctness={k:{'before':before[k]['value'],'after':after[k]['value'],
                            'before_status':before[k]['status'],'after_status':after[k]['status']} for k in ['co_method','co_param']}))
    report=dict(version=scoring_v6.VERSION,selected_cases=sorted(ids),branches=len(rows),
                scope='recipe_patch_on_cached_alignment',alignment_runs=0,new_model_calls=0,full_benchmark_rescored=False,
                baseline_sha256=scorer.sha(BASELINE_VERIFIED),rows=rows)
    path=Path(__file__).with_name('cached_claim_replay.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
