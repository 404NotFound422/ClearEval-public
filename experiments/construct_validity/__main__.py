"""Offline-first command line; all inference is explicit and loopback only."""
import argparse
import json
from pathlib import Path
import sys

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="ClearEval construct-validity development workflow")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("prepare","audit","legacy-replay"):
        p=sub.add_parser(name)
        p.add_argument("--workspace",type=Path,required=True)
        p.add_argument("--out",type=Path,required=True)
    for name in ("preflight","run","analyze"):
        p=sub.add_parser(name)
        p.add_argument("--study",type=Path,required=True)
        if name=="run":
            p.add_argument("--max-new",type=int,required=True)
            p.add_argument("--phase",action="append",choices=["generate","judge","control","extract"])
    p=sub.add_parser("review-export")
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    for name in ("review-import", "review-extraction-import"):
        p=sub.add_parser(name)
        p.add_argument("--package",type=Path,required=True)
        p.add_argument("--ratings",type=Path,required=True)
        p.add_argument("--out",type=Path,required=True)
    for name in ("compare-objectives", "guard-comparison"):
        p=sub.add_parser(name)
        p.add_argument("--input",type=Path,required=True)
        p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("plan-judges")
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--judges",type=Path,required=True)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("formal-readiness")
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="prepare":
        from .study import prepare
        result=prepare(args.workspace,args.out)
    elif args.command=="audit":
        from .audit import run_audit
        result=run_audit(args.workspace/"ClearEval-public",args.out)
    elif args.command=="preflight":
        from .study import preflight
        result=preflight(args.study)
    elif args.command=="run":
        if not 1<=args.max_new<=28: raise ValueError("Batch limit must be 1..28")
        from .local_runner import run
        result=run(args.study,args.max_new,args.phase)
    elif args.command=="analyze":
        from .analysis import summarize
        result=summarize(args.study)
    elif args.command=="legacy-replay":
        from .legacy_adapter import replay_guards
        result=replay_guards(args.workspace,args.out)
    elif args.command=="review-export":
        from .review import export_review
        from .review_html import create_html
        result=export_review(args.study,args.out)
        create_html(args.out)
    elif args.command=="review-import":
        from .review import import_ratings
        result=import_ratings(args.package,args.ratings,args.out)
    elif args.command=="review-extraction-import":
        from .review import import_extraction_references
        result=import_extraction_references(args.package,args.ratings,args.out)
    elif args.command=="compare-objectives":
        from .contract import read,save
        from .comparisons import compare_adjudicated_candidates
        data=read(args.input)
        result=compare_adjudicated_candidates(data["a"],data["b"])
        save(args.out,result)
    elif args.command=="guard-comparison":
        from .contract import read,save
        from .comparisons import same_information_guards
        result=same_information_guards(read(args.input))
        save(args.out,result)
    elif args.command=="plan-judges":
        from .contract import read
        from .comparisons import freeze_judge_comparison
        result=freeze_judge_comparison(args.study,read(args.judges),args.out,args.repeats)
    elif args.command=="formal-readiness":
        from .readiness import formal_readiness
        result=formal_readiness(args.workspace,args.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
