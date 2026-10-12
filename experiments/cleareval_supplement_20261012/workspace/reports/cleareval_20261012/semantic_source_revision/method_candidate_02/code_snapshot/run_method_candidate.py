"""Transfer a source-anchoring correction uniformly over the 32 archived returns."""
import copy
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
DEST=args.out
sys.path.insert(0,str(ROOT/'scripts'))
import cce_selected_method_source_v1 as method_scope
import cce_scoped_midpoint_scorer_v1 as b
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES
from cce_scales_source_key_alias_v1 import source_key_alias
source=OUT.parent/'typed_label_transfer/time_heading_candidate_01/results.json'
rows=b.read(source);runner,registry=b.runtime();checks=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
for text,want in [('所选透明方法：iDISCO+',True),('第1行（所选荧光/标记策略 + 透明方法）：[DAPI] + iDISCO+',True),
    ('所选透明方法：不采用 iDISCO+',False),('候选透明方法：iDISCO+',False),
    ('所选透明方法：iDISCO+ or CUBIC',False),('所选透明方法：iDISCO+或CUBIC',False),
    ('所选透明方法：CUBIC或者iDISCO+',False),('所选透明方法：CUBIC',False)]:
    check(text,method_scope.chinese_selection_header(text,'iDISCO+')==want)
plan={'entrypoint':b.bind(__file__),'candidate':b.bind(method_scope.__file__),'input':b.bind(source),
    'new_model_calls':0,'new_author_per_answer_annotations':0,'preserve_raw_SR_SP_and_direct_scores':True}
if (DEST/'plan.json').exists():assert b.read(DEST/'plan.json')==plan
else:b.save(DEST/'plan.json',plan)
(DEST/'code_snapshot').mkdir(parents=True,exist_ok=True)
for script in [Path(__file__),Path(method_scope.__file__)]:
    (DEST/'code_snapshot'/script.name).write_bytes(script.read_bytes())
results=[]
for row in rows:
    post=b.read((row.get('lexical_post') or row['source_record'])['path'])
    doc=b.read(row['source_document']['path']);metric=copy.deepcopy(row['final_candidate_metrics'])
    decision=method_scope.selected_method(post['conversion'],doc) if post.get('conversion') else None
    quantitative=copy.deepcopy(post.get('numeric',{}).get('quantitative_data'))
    numeric=None
    if decision and decision['changed']:
        quantitative['method_name']=decision['method_name']
        with source_key_alias():
            numeric=runner.calculate_effectiveness_score(quantitative,post['numeric']['user_preference_vector'],runner.MODEL_SPACE_SIGNED,{},[])
        metric=derive({**{k:metric[k] for k in DIRECT+EGES},
            **{k:numeric[k] for k in ['s_method','s_trans','s_time']}},{k:metric[k] for k in ['sr','sp']},True)
    check('direct_and_steps:'+row['cell_id'],all(metric[k]==row['final_candidate_metrics'][k] for k in DIRECT+['sr','sp','Com','Cor']))
    check('old_finite_values:'+row['cell_id'],all(metric[k]==v for k,v in row['final_candidate_metrics'].items() if b.finite(v)))
    result={**row,'method_candidate_metrics':metric,'method_selection_decision':decision,
        'method_candidate_quantitative_data':quantitative,'method_numeric_derivation':numeric,
        'method_changes':{k:{'before':row['final_candidate_metrics'][k],'after':v} for k,v in metric.items() if v!=row['final_candidate_metrics'][k]}}
    results.append(result)
b.save(DEST/'results.json',results)
b.save(DEST/'verification.json',{'checks':checks,'checks_passed':len(checks)})
b.save(DEST/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0})
print(json.dumps({'changed':[{k:r[k] for k in ['cell_id','method_changes']} for r in results if r['method_changes']],
    'checks_passed':len(checks),'new_model_calls':0},ensure_ascii=False,indent=2))
