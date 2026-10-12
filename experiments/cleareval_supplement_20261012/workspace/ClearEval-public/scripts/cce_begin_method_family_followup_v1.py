"""Preserve the 136-request report and freeze an additive development work plan."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'method_family_followup_v1'
SNAP = BASE / 'historical_reports/before_method_family_at_136'

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    verification = read(BASE / 'report_verification_references_v7.json')
    manifest_path = SNAP / 'snapshot_manifest.json'
    if manifest_path.exists():
        manifest = read(manifest_path)
        for row in manifest['files']:
            assert sha(SNAP / row['relative_path']) == row['sha256']
        print(json.dumps({'status':'reuse_verified_snapshot','files':len(manifest['files'])}))
        return
    for rel, expected in {**verification['input_sha256'], **verification['output_sha256']}.items():
        p = Path(rel) if Path(rel).is_absolute() else BASE / rel
        assert sha(p) == expected, str(p)
    names = [*verification['output_sha256'], 'report_verification_references_v7.json',
             'report_generation.json', 'judges/request_ledger.jsonl']
    rows = []
    for name in names:
        src, dest = BASE / name, SNAP / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        assert src.read_bytes() == dest.read_bytes()
        rows.append({'relative_path':name,'original_path':str(src),'sha256':sha(src)})
    save(manifest_path, {'status':'byte_preserved','requests':136,'files':rows,
                        'scope':'Before approved method-family, output-contract and representation follow-up.'})
    save(OUT / 'plan.json', {
        'version':'method_family_followup_v1', 'status':'development_work_plan',
        'prior_requests':136, 'package_limit':300, 'remaining_before_work':164,
        'immediate_planned_judge_requests':5, 'judge_batch':'A01-A05 x local_qwen3_8b x one attempt',
        'no_automatic_holdout_run':True, 'expert_plan':{'experts':1,'development':5,'holdout':15},
        'prior_report_snapshot':str(manifest_path),'prior_report_snapshot_sha256':sha(manifest_path),
        'scientific_core_sha256':sha(ROOT/'scripts/cce_validation.py'),
        'expert_form_sha256':sha(BASE/'human_review/reviewer/review_items.csv'),
        'workstreams':[
            'Full-source method/version reference construction; no score-dependent source selection.',
            'Fixed77 answers/13 generators, same-method whole-reference max SR, SP and all candidates; conditional scope explicit.',
            'Paired step rescoring with identical frozen configuration; adaptive and baseline-fixed references.',
            'Versioned output-contract fix, offline validation then5 actual development requests only.',
            'Separate lexical operation-segmentation development diagnostic, unchanged BioProBench threshold and weights.'
        ],
        'constraints':['No changed old scientific outputs or formulas.','No fabricated expert returns.',
                       'No heldout scientific tuning.','No pooling best outputs across prompt versions.',
                       'No promotion of conditional source matching to scientific applicability.'],
        'actual_prepare_command':[sys.executable,'scripts/cce_begin_method_family_followup_v1.py']})
    print(json.dumps({'status':'prepared','snapshot_files':len(rows),'new_requests':0}))

if __name__ == '__main__': main()
