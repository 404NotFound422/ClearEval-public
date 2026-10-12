"""Explain original time scores without changing scores, KB rows or formulas."""
from pathlib import Path
import argparse
import csv
import math
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_offline_scoring_v1 as scoring
from evaluation_contract import time_score_details
j=scoring.j


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cells',type=Path,default=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/fieldwise_replay_v1/actual_04/cells.csv')
    p.add_argument('--out',type=Path,default=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/four_hour_extension_20261010/time_response_audit_v1')
    a=p.parse_args()
    runner,_=scoring.runtime()
    with a.cells.open(encoding='utf-8-sig',newline='') as f: cells=list(csv.DictReader(f))
    results=[]
    for cell in cells:
        if not cell.get('result_path'):continue
        source=Path(cell['result_path'])
        if not source.is_file():continue
        num=j.read(source); q=num['quantitative_data']; method=q['method_name']; tier=q['sample_tier']
        identity=runner.method_identity(method,runner.MODEL_SPACE_SIGNED,q.get('method_stages'))
        key=runner.resolve_method(method,runner.TIME_KB_LOOKUP) if identity['status']=='RESOLVED_SINGLE' else None
        kb=runner._time_kb_row(key or '',tier)
        value,details=time_score_details(q['total_time_hours'],kb,tier)
        stored=num['metrics']['s_time']
        if value!=stored:raise ValueError('ORIGINAL_TIME_REPLAY_MISMATCH:'+cell['cell_id'])
        log10=None
        if details['status']=='scored':
            log10=(math.log(3)-.5*(details['delta_hours']/details['tau_hours'])**2)/math.log(10)
        results.append(dict(cohort=cell['cohort'],cell_id=cell['cell_id'],question_id=cell['question_id'],
            method=method,method_key=key,tier=tier,actual_hours=q['total_time_hours'],
            score=stored,log10_mathematical_score=log10,
            diagnosis='missing_input_or_KB' if stored is None else 'floating_point_underflow' if stored==0
                else 'inside_reference_window' if stored==3 else 'positive_deviation_penalty',
            details=details,KB_row=kb,numeric_result=dict(path=str(source),sha256=j.filehash(source))))
    a.out.mkdir(parents=True,exist_ok=True)
    j.save(a.out/'per_cell.json',results)
    compact=[{k:r[k] for k in ['cohort','cell_id','question_id','method','tier','actual_hours','score','log10_mathematical_score','diagnosis']} for r in results]
    with (a.out/'per_cell.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
    summary=dict(cells=len(results),diagnoses={d:sum(r['diagnosis']==d for r in results) for d in sorted({r['diagnosis'] for r in results})},
        original_formula_replay_mismatches=0,score_or_KB_changed=False,new_model_requests=0,
        inputs=dict(path=str(a.cells),sha256=j.filehash(a.cells)),actual_command=[sys.executable,*sys.argv],
        caution='log10 is an explanatory diagnostic only, never a replacement CCE score. A mathematical zero from floating point underflow differs from missingness or an artificial failure zero.')
    j.save(a.out/'summary.json',summary)
    print(j.canonical(summary))


if __name__=='__main__':main()
