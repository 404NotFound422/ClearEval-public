"""Summarize the already frozen 0.6/0.7/0.8 step sensitivity, without tuning.

No embeddings, judges, reference edits or new match rules are used. These three
development cases cannot establish which threshold has better scientific accuracy.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
SOURCE=BASE/'step_representation_v1/paired_results.csv'
OUT=BASE/'step_threshold_diagnostic_v1'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    rows=list(csv.DictReader(SOURCE.open(encoding='utf-8-sig',newline='')))
    selected=[r for r in rows if r['condition']=='necessary_step_deletion' and r['mode']=='original_biopro_baseline']
    assert len(selected)==9
    assert {(int(r['question_id']),float(r['threshold'])) for r in selected}=={(q,t) for q in [2,21,22] for t in [.6,.7,.8]}
    result=[]
    for r in selected:
        assert r['same_configuration_and_reference']=='True' and r['full_text_reparsed_both_arms']=='True'
        b,v,d=map(float,[r['baseline_sr'],r['variant_sr'],r['delta_sr']])
        assert abs(v-b-d)<1e-12
        result.append({'pair_id':r['pair_id'],'question_id':int(r['question_id']),
            'threshold':float(r['threshold']),'baseline_sr':b,'variant_sr':v,'delta_sr':d,
            'reference_steps':int(r['reference_n']),
            'baseline_reference_hits':round(b*int(r['reference_n'])),
            'variant_reference_hits':round(v*int(r['reference_n'])),
            'baseline_sp':float(r['baseline_sp']),'variant_sp':float(r['variant_sp']),
            'delta_sp':float(r['delta_sp']),'baseline_case_id':r['baseline_case_id'],
            'variant_case_id':r['variant_case_id'],'full_text_reparsed_both_arms':True})
    summary=[]
    for threshold in [.6,.7,.8]:
        subset=[r for r in result if r['threshold']==threshold]
        summary.append({'threshold':threshold,'pairs':len(subset),'SR_decreased':sum(r['delta_sr']<-1e-12 for r in subset),
            'SR_unchanged':sum(abs(r['delta_sr'])<=1e-12 for r in subset),
            'SR_increased':sum(r['delta_sr']>1e-12 for r in subset),
            'SP_increased':sum(r['delta_sp']>1e-12 for r in subset)})
    OUT.mkdir(parents=True,exist_ok=True)
    save(OUT/'per_pair.json',result)
    with (OUT/'per_pair.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    audit={'status':'complete','source':{'path':str(SOURCE),'sha256':sha(SOURCE)},
        'original_main_threshold':.7,'threshold_selection_changed':False,
        'threshold_sensitivity_was_prespecified':True,'unique_development_base_answers':3,
        'summary':summary,'actual_utc':datetime.now(timezone.utc).isoformat(),
        'actual_command':[sys.executable,*sys.argv],'cwd':str(ROOT),'script_sha256':sha(Path(__file__)),
        'new_model_requests':0,'new_embedding_calls':0,'expert_accuracy_claimed':False}
    save(OUT/'summary.json',audit)
    lines=['# 原SR的阈值敏感性：原因诊断，不重新选择主阈值','',
        '复用已冻结的0.6/0.7/0.8结果。三个基础答案均为开发暴露案例，九行是三个阈值下的重复计算，不是九个独立案例。原主阈值仍为0.7。','',
        '| 阈值 | q2 SR：原→删步 | q21 SR：原→删步 | q22 SR：原→删步 | SR下降配对 |','|---|---|---|---|---|']
    for threshold in [.6,.7,.8]:
        subset={r['question_id']:r for r in result if r['threshold']==threshold}
        cells=[f"{subset[q]['baseline_reference_hits']}/7 → {subset[q]['variant_reference_hits']}/7" for q in [2,21,22]]
        count=next(r['SR_decreased'] for r in summary if r['threshold']==threshold)
        lines.append('| '+str(threshold)+' | '+' | '.join(cells)+f' | {count}/3 |')
    lines += ['',
        '解释：0.7下两个案例在删除之前就没有命中被删操作的对应参考，因此删除后SR不再下降。0.6把这些边界附近的相似度重新计为命中，三对均下降；0.8则出现明显的低分地板，三对都不变。','',
        '这说明阈值是观察到的无响应的一项原因，不足以证明0.6更准确。降低阈值同时扩大可匹配集合，可能接受动作不同但术语相近的步骤；是否为真实正确匹配仍需原文关系与专家局部核查。不能为了这三对都下降就更改主设置。','',
        'SP在部分删步案例反而上升，源于生成步骤分母和被删未匹配内容变化；该方向不能解释为方案质量提高。完整性仍由原SR和原c_param共同计算，不能把此表当成新一轮完整Com评分。','',
        '[逐配对SR/SP及命中数](per_pair.csv) · [配置与实际命令](summary.json) · [原始冻结结果](../step_representation_v1/paired_results.csv)','']
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'status':'complete','summary':summary,'main_threshold_unchanged':.7,'new_model_requests':0},ensure_ascii=False))

if __name__=='__main__':main()
