"""Run explicitly selected cases or the user-authorized full benchmark retest."""
from pathlib import Path
import argparse,json,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import cleareval_complete_scoring as scorer
from cleareval_scoring.scoring_v6 import VERSION

ap=argparse.ArgumentParser(description=__doc__)
choice=ap.add_mutually_exclusive_group(required=True)
choice.add_argument('--case-id',action='append',help='Only run the named cases; repeat for multiple cases')
choice.add_argument('--full-retest',action='store_true',help='Explicitly select the authorized full retest')
args=ap.parse_args()
cases=scorer.read(scorer.DEFAULT_INPUT)['cases']
if args.case_id:cases=[c for c in cases if c['id'] in args.case_id]
if args.case_id and {c['id'] for c in cases}!=set(args.case_id):ap.error('Unknown requested case ID')
decisions=scorer.read(scorer.DEFAULT_INPUT.with_name('adjudications.json'))
started=time.monotonic();packets=[]
for i,c in enumerate(cases,1):
    packets.extend(scorer.verified_packets([c],decisions,independent_claims=True))
    if i%25==0 or i==len(cases):print(json.dumps({'completed_branches':i,'total_branches':len(cases)}),flush=True)
output=Path(__file__).parent/('full_retest_checks.json.gz' if args.full_retest else 'targeted_checks.json.gz');output.parent.mkdir(parents=True,exist_ok=True)
scorer.write_gzip(output,packets)
receipt={'version':VERSION,'input_sha256':scorer.sha(scorer.DEFAULT_INPUT),
         'verified_sha256':scorer.sha(output),'answers':len({c['id'] for c in cases}),'branches':len(cases),
         'adjudications_sha256':scorer.sha(scorer.DEFAULT_INPUT.with_name('adjudications.json')),
         'new_model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),
         'scope':'full_retest' if args.full_retest else 'targeted_retest',
         'code_sha256':{p.name:scorer.sha(p) for p in sorted((ROOT/'cleareval_scoring').glob('*.py'))}}
output.with_name('run_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(receipt,ensure_ascii=False))
