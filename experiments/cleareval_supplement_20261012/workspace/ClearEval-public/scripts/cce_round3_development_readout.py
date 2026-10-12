"""Read actual paired development returns; do not alter scores or judge inputs."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']

def read(p): return json.loads(Path(p).read_text(encoding='utf8'))
def binding(p): return {'path': str(Path(p).resolve()), 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def number(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
def delta(a, b): return b-a if number(a) and number(b) else None

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a=ap.parse_args()
    pointer=read(a.batch/'latest_analysis.json')
    obs_path=Path(pointer['observations']['path'])
    assert binding(obs_path)==pointer['observations']
    rows=read(obs_path)
    assert len({x['case_id'] for x in rows})==len(rows), 'This development panel expects one new return per answer'
    ix={x['case_id']:x for x in rows}
    proposal_path=R3/'representation_repair/proposed_request_matrix.json'
    proposal=read(proposal_path)
    old_path=R3/'uniform_v7/actual_01/cells.json'
    old={x['anonymous_answer_id']:x for x in read(old_path) if x['cohort']=='E2'}
    grouped={}
    for c in proposal['cells']: grouped.setdefault(c['pair_id'],{})[c['arm']]=c
    paired=[]
    for pid, cells in grouped.items():
        b,v=(ix[cells[k]['source_case_id']] for k in ('baseline','variant'))
        ob,ov=(old[cells[k]['source_anonymous_answer_id']] for k in ('baseline','variant'))
        bm,vm=b['metrics'],v['metrics']
        available=all(number(m[k]) for m in (bm,vm) for k in DIRECT)
        paired.append({'pair_id':pid,'question_id':b['question_id'],'condition':cells['variant']['condition'],
            'baseline_trial_id':b['trial_id'],'variant_trial_id':v['trial_id'],
            'baseline_status':b['status'],'variant_status':v['status'],
            'both_observed':all(x['status']!='pending' for x in (b,v)),
            'both_technical_success':all(x['status']=='success' for x in (b,v)),
            'both_complete_numeric_CCE':all(x['complete_numeric_CCE'] for x in (b,v)),
            'direct_values_available':available,
            'direct_values_identical':all(bm[k]==vm[k] for k in DIRECT) if available else None,
            'baseline_metrics':bm,'variant_metrics':vm,
            'delta':{k:delta(bm[k],vm[k]) for k in bm},
            'previous_baseline_metrics':ob['posthoc_metrics'],'previous_variant_metrics':ov['posthoc_metrics'],
            'previous_delta':{k:delta(ob['posthoc_metrics'][k],ov['posthoc_metrics'][k]) for k in bm},
            'same_primary_SRSP_as_previous':all(x['metrics'][k]==o['posthoc_metrics'][k]
                for x,o in [(b,ob),(v,ov)] for k in ['sr','sp'])})
    summary={'status':'actual_development_readout','planned_pairs':len(paired),
        'observed_pairs':sum(x['both_observed'] for x in paired),
        'technical_success_pairs':sum(x['both_technical_success'] for x in paired),
        'direct_available_pairs':sum(x['direct_values_available'] for x in paired),
        'direct_invariant_pairs':sum(x['direct_values_identical'] is True for x in paired),
        'complete_CCE_pairs':sum(x['both_complete_numeric_CCE'] for x in paired),
        'original_SRSP_unchanged':all(x['same_primary_SRSP_as_previous'] for x in paired),
        'development_exposed_cases':True,'scientific_accuracy_not_established':True,
        'old_and_new_prompt_differ':True,'within_each_pair_same_configuration':True,
        'new_model_calls_by_this_script':0,
        'inputs':[binding(p) for p in [__file__,proposal_path,old_path,obs_path,a.batch/'plan.json']]}
    a.out.mkdir(parents=True,exist_ok=False)
    for name,value in [('paired_results.json',paired),('summary.json',summary)]:
        (a.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__': main()
