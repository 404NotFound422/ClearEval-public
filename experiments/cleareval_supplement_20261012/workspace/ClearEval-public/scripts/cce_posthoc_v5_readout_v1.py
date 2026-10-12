"""Read saved v4/v5 results only; no conversion or scoring."""
import csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
DELIVERY=R2/'four_hour_extension_20261010/delivery'
METRICS=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']
STABLE=[x for x in METRICS if x not in ['s_label','Eff','IA','HV']]
def load(p):return json.loads(p.read_text(encoding='utf8'))
def bind(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def full(m):return all(m[k] is not None for k in ['Com','Cor','Eff'])
def main():
 out=DELIVERY/'v5_difference_matrix_v1/actual_01';assert not out.exists();out.mkdir(parents=True)
 before=R2/'posthoc_uniform_scoring_v4/actual_execution_01';after=R2/'posthoc_uniform_scoring_v5/actual_execution_01'
 bindings=[];datasets=[]
 for folder in [before,after]:
  for name in ['summary.json','verification.json','implementation_addendum.json','cells.json']:bindings.append(bind(folder/name))
  assert load(folder/'verification.json')['status']=='pass'
  datasets.append({(r['cohort'],r['cell_id']):r for r in load(folder/'cells.json')})
 aa,bb=datasets;assert aa.keys()==bb.keys() and len(aa)==68
 rows=[];long=[]
 for key,a in aa.items():
  b=bb[key];am,bm=a['posthoc_metrics'],b['posthoc_metrics']
  assert all(a.get(k)==b.get(k) for k in ['status','raw_sha256','question_id','cancelled_no_raw'])
  assert all(am[k]==bm[k] for k in STABLE)
  rows.append({'cohort':key[0],'cell_id':key[1],'original_status':b['status'],'qid':b.get('question_id'),'raw_sha256':b.get('raw_sha256'),'cancelled':b.get('cancelled_no_raw',False),'before_metrics':am,'after_metrics':bm,'complete_v4':full(am),'complete_v5':full(bm),'changed_metrics':[k for k in METRICS if am[k]!=bm[k]],'posthoc_record':b.get('posthoc_record')})
  long += [{'cohort':key[0],'cell_id':key[1],'metric':k,'v4':am[k],'v5':bm[k],'changed':am[k]!=bm[k]} for k in METRICS]
 cohorts={}
 for c in dict.fromkeys(r['cohort'] for r in rows):
  rr=[r for r in rows if r['cohort']==c]
  cohorts[c]={'planned_slots':len(rr),'actual_returns':sum(not r['cancelled'] for r in rr),'complete_v4':sum(r['complete_v4'] for r in rr),'complete_v5':sum(r['complete_v5'] for r in rr),'changed_cells':[r['cell_id'] for r in rr if r['changed_metrics']]}
 summary={'status':'completed_saved_v4_v5_comparison','planned_slots':68,'raw_returns':67,'cancelled':1,'cohorts':cohorts,'changed_cells':sum(bool(r['changed_metrics']) for r in rows),'changed_metric_cells':sum(r['changed'] for r in long),'unchanged_fields':STABLE,'new_model_calls':0,'new_scoring_calls':0,'all_original_status_raw_preserved':True,'inputs':bindings,'actual_command':[sys.executable,*sys.argv]}
 save(out/'summary.json',summary);save(out/'per_cell.json',rows)
 with (out/'per_metric.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(long[0]));w.writeheader();w.writerows(long)
 lines=['# 统一后验 v5 对 v4：native 输入契约修复','',
 '同一 67 份原返回和 1 个取消槽全部保留。v5 只将适配器新增的 native reporter 自环改为荧光键/空 marker；原公式、KB、原返回、原技术状态不变。真实显式 marker 关系与 unknown 记录不删除。',
 '', '| 集合 | 实际返回 / 计划槽 | 完整 CCE v4 → v5 |','|---|---:|---:|']
 for c,x in cohorts.items():lines.append(f"| {c} | {x['actual_returns']}/{x['planned_slots']} | {x['complete_v4']} → {x['complete_v5']} |")
 lines += ['',f"共 {summary['changed_cells']} 个槽的 {summary['changed_metric_cells']} 个指标单元变化，仅可能为 label/Eff/IA/HV；另外 12 个指标全部逐值不变。",
 '', '空 marker 不向 target/marker 列表追加贡献；仍计算 method×fluor。混合输入中的明确 marker 继续提供前两通道。若整个通道没有贡献，原 nullable_min 返回 None，不自行赋 6。A05 的整体 5.1 由 AF647→TUJ1 的 (6,6,5.1) 与 native key-only 的 method 5.4 联合产生，不能说只有 native 即得 5.1。',
 '', '固定 E5 十份中，FPC06/FPC16 的 native 自环零消失，label 从 0 变 NA；剩余 FPC14/FPC15 的零由明确 F-actin 关系按原目标规则产生，绝非 GFP 自环。FPC03/FPC13 已恢复来源的关系仍受实际 MAP2 适用 scope 空格限制，不能通过给 native 自环添兼容值解决。',
 '', '这是看过返回后的软件输入编码修正，不是新评价调用、前瞻确认或科学准确性验证。原 v4 数值保留。完整 CCE 向量与完整提取图谱不能混称。',
 '', '[逐槽 JSON](per_cell.json) / [全部 68×16 指标 CSV](per_metric.csv) / [来源与实际命令](summary.json)。']
 (out/'README_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
 print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
