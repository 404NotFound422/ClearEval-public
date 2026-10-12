"""Read saved v3/v4 metrics; no conversion, scoring, model or raw-text read."""
import argparse,collections,csv,hashlib,json,math,sys
from pathlib import Path
METRICS=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']
STABLE=[x for x in METRICS if x not in ['s_label','Eff','IA','HV']]
INPUTS=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
 INPUTS.append({'path':str(p.resolve()),'sha256':sha(p)})
 return json.loads(p.read_text(encoding='utf8'))
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def full(m):return all(finite(m[k]) for k in ['Com','Cor','Eff'])
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def fmt(x):return 'NA' if x is None else f'{x:.6g}' if isinstance(x,(int,float)) else str(x)
def validate(folder):
 s=load(folder/'summary.json');v=load(folder/'verification.json');a=load(folder/'implementation_addendum.json')
 assert s['status']=='completed_uniform_posthoc_not_new_confirmation'
 assert v['status']=='pass' and a['status']=='pass' and a['all67_label_views_audited'] is True
 assert s['planned_slots']==68 and s['raw_returns']==67 and s['cancelled_no_raw']==1
 p=folder/'cells.json';b=next(x for x in v['outputs'] if Path(x['path']).resolve()==p.resolve())
 assert sha(p)==b['sha256']
 cells=load(p);assert len(cells)==68
 return s,{(x['cohort'],x['cell_id']):x for x in cells}
def run(before,after,out):
 assert not out.exists(),'NEW_OUTPUT_REQUIRED'
 old,aa=validate(before);new,bb=validate(after);assert aa.keys()==bb.keys() and len(aa)==68
 rows=[];long=[];cohorts={};witnesses={}
 for batch in ['first7_posthoc','secondary8_posthoc']:
  for item in load(after/'label_witnesses_by_batch'/f'{batch}.json'):
   witnesses[batch,item['cell_id']]=item
 for key in aa:
  a,b=aa[key],bb[key]
  assert all(a.get(k)==b.get(k) for k in ['cohort','cell_id','anonymous_answer_id','status','raw_sha256','question_id','cancelled_no_raw'])
  am,bm=a['posthoc_metrics'],b['posthoc_metrics'];assert all(am[k]==bm[k] for k in STABLE)
  row={'cohort':key[0],'cell_id':key[1],'anonymous_answer_id':b['anonymous_answer_id'],'question_id':b.get('question_id'),
   'original_status':b['status'],'cancelled_no_raw':b.get('cancelled_no_raw',False),'raw_sha256':b.get('raw_sha256'),
   'v3_label':am['s_label'],'v4_label':bm['s_label'],'v3_complete_CCE':full(am),'v4_complete_CCE':full(bm),
   'v3_full_conversion':a.get('posthoc_full_conversion'),'v4_full_conversion':b.get('posthoc_full_conversion'),
   'changed_metrics':[k for k in METRICS if am[k]!=bm[k]],'v4_record':b.get('posthoc_record')}
  witness=witnesses.get(key,{})
  calc=(witness.get('calculation') or {}).get('after')
  if calc:
   row['label_channels']=calc['channels'];row['zero_witnesses']=calc['zero_witnesses']
   row['explicit_label_uncertainties']=calc['explicit_label_uncertainties']
   row['pair_channels']=[{k:x.get(k) for k in ['pair_id','kind','original_function_input','channels','compatibility_audit']} for x in calc['pair_results']]
  rows.append(row)
  for k in METRICS:
   long.append({'cohort':key[0],'cell_id':key[1],'metric':k,'v3':am[k],'v4':bm[k],
    'changed':am[k]!=bm[k],'both_finite':finite(am[k]) and finite(bm[k]),
    'difference_if_finite':bm[k]-am[k] if finite(am[k]) and finite(bm[k]) else None})
 for cohort in dict.fromkeys(x['cohort'] for x in rows):
  rr=[x for x in rows if x['cohort']==cohort]
  cohorts[cohort]={'planned':len(rr),'raw_returns':sum(not x['cancelled_no_raw'] for x in rr),
   'v3_complete_CCE':sum(x['v3_complete_CCE'] for x in rr),'v4_complete_CCE':sum(x['v4_complete_CCE'] for x in rr),
   'v3_finite_label':sum(finite(x['v3_label']) for x in rr),'v4_finite_label':sum(finite(x['v4_label']) for x in rr),
   'changed_cells':[x['cell_id'] for x in rr if x['changed_metrics']]}
 summary={'status':'completed_saved_metrics_comparison','before_processing_version':old['scorer_version'],
  'after_processing_version':new['scorer_version'],'planned_slots':68,'actual_raw_returns':67,'cancelled':1,
  'changed_cells':sum(bool(x['changed_metrics']) for x in rows),'changed_metric_rows':sum(x['changed'] for x in long),
  'cohorts':cohorts,'all_twelve_other_metrics_exactly_unchanged':True,'original_raw_status_unchanged':True,
  'whole_conversion_and_numeric_complete_separate':True,'new_model_calls':0,'new_scores':0,
  'actual_command':[sys.executable,*sys.argv]}
 out.mkdir(parents=True)
 save(out/'summary.json',summary);save(out/'per_cell.json',rows)
 with (out/'per_metric.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(long[0]));w.writeheader();w.writerows(long)
 slim=[{k:v for k,v in x.items() if k not in ['v4_record','label_channels','zero_witnesses','explicit_label_uncertainties','pair_channels']} for x in rows]
 with (out/'per_cell.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(slim[0]));w.writeheader();w.writerows(slim)
 lines=['# 统一后验 v4 相对 v3 的逐项变化','',
  '这是相同已保存返回的离线数据流修复，不是新增评价。68 个计划槽全部保留：67 份真实返回、1 个用户取消且无返回。原始返回、原状态和十二个非标签依赖指标逐值不变；只允许标签与 Eff/IA/HV 随原公式变化。',
  '', '| 群组 | 实际返回/计划 | v3 完整数值 CCE | v4 完整数值 CCE | 发生数值变化的槽 |','|---|---:|---:|---:|---|']
 for name,c in cohorts.items():lines.append(f"| {name} | {c['raw_returns']}/{c['planned']} | {c['v3_complete_CCE']} | {c['v4_complete_CCE']} | {', '.join(c['changed_cells']) or '无'} |")
 lines+=['','“完整数值 CCE”仅指 Com/Cor/Eff 均有限，不表示原模型整份转换成功、完整事实图谱或科学正确。未知记录与知识库缺项仍显式保留。',
  '','| 关注答案 | v3 标签 | v4 标签 | v3→v4 完整数值 CCE | 原状态 / v4 整份转换 |','|---|---:|---:|---|---|']
 for aid in ['FPC03','FPC13','FPC15','FPC16']:
  r=next(x for x in rows if x['cell_id']==aid)
  lines.append(f"| {aid} | {fmt(r['v3_label'])} | {fmt(r['v4_label'])} | {r['v3_complete_CCE']} → {r['v4_complete_CCE']} | {r['original_status']} / {r['v4_full_conversion']} |")
 lines+=['','FPC03 的已声明端点从不完整引用重绑到唯一原文配对；FPC13 从唯一明确 native 声明恢复来源身份。它们的兼容知识缺项仍不能由引用修复填值。FPC15 只补原文已有 F-actin 端点；若得到 0，是原目标匹配/回退规则的结果，不能称化学不兼容。',
  '','FPC16 仅在标签依赖视图隔离悬空目标；原整份转换失败和 partial 状态不晋升，R001/R002 未决关系仍在。若原 native 目标规则的已知 0 经 nullable_min 吸收未知而得到有限标签，这是原公式可算，不是关系已获证明。',
  '', '[逐槽表](per_cell.json)包含三通道、已知零见证及未决关系；[逐指标 CSV](per_metric.csv)保留全部 68×16 格，没有以零填 NA。原 v3 结果保持不变。',
  '', '实际命令：','', '```text',' '.join(summary['actual_command']),'```']
 (out/'README_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
 save(out/'verification.json',{'status':'pass','inputs':INPUTS,'script':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))},
  'rows':68,'metric_rows':1088,'source_bodies_and_raw_not_read':True,'new_model_calls':0,'new_scores':0})
 print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 run(a.before.resolve(),a.after.resolve(),a.out.resolve())
