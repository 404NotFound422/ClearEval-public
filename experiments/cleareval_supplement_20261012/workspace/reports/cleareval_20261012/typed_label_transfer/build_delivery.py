"""Create descriptive figures and inspectable examples from actual replay files."""
import csv
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rows=b.read(OUT/'time_heading_candidate_01/results.json');byid={r['cell_id']:r for r in rows}
pairs=b.read(OUT/'scope_candidate_02/controlled_pairs.json')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none',
    'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(10.8,4.0),layout='constrained')
labels=['Archived\nprimary','Fixed typed\nlabel transfer','Final scope\ncandidate']
x=np.arange(3);width=.34
for offset,values,denom,color,name in [(-width/2,[0,18,24],24,'#23779b','Controlled returns (n=24)'),
                                     (width/2,[0,0,2],8,'#bf7738','Later confirmation returns (n=8)')]:
    bars=axes[0].bar(x+offset,100*np.array(values)/denom,width,color=color,label=name)
    for bar,value in zip(bars,values):
        axes[0].text(bar.get_x()+bar.get_width()/2,bar.get_height()+2,f'{value}/{denom}',ha='center',fontsize=9)
axes[0].set(xticks=x,xticklabels=labels,ylabel='Complete numerical CCE (%)',ylim=(0,124),yticks=[0,25,50,75,100],
    title='A  Coverage on the same saved returns')
axes[0].legend(frameon=False,fontsize=8,loc='upper left')
conditions=['numbering','merge','necessary_step_deletion']
positions={2:-.12,21:0,22:.12}
plot_rows=[]
for q,color,marker in [(2,'#23779b','o'),(21,'#bf7738','s'),(22,'#408563','^')]:
    vals=[next(p['delta_HV'] for p in pairs if p['question_id']==q and p['condition']==c and p['repeat_index']==0) for c in conditions]
    axes[1].plot(np.arange(3)+positions[q],vals,marker=marker,linestyle='none',color=color,label=f'Task q{q}',markersize=7)
    for c,v in zip(conditions,vals):plot_rows.append({'question_id':q,'condition':c,'delta_HV':v,'identical_archived_repeats':2})
axes[1].axhline(0,color='#65737c',lw=.8)
axes[1].set(xticks=np.arange(3),xticklabels=['Numbering','Merge','Module deletion'],ylabel='HV: variant minus baseline',
    title='B  Actual paired response by task',xlim=(-.45,2.45),ylim=(-.135,.072))
axes[1].legend(frameon=False,fontsize=9,loc='lower right')
folder=OUT/'figures';folder.mkdir(exist_ok=True)
for extension in ['png','pdf','svg']:fig.savefig(folder/('coverage_and_paired_HV.'+extension),dpi=220)
plt.close(fig)
with (folder/'paired_HV_plot_data.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(plot_rows[0]));writer.writeheader();writer.writerows(plot_rows)

case_lookup={}
for cohort in {r['cohort'] for r in rows}:
    payload=b.read(ROOT/'artifacts/cce_validation/optimizer_round3_20261011'/cohort/'cases.json')
    cases=payload['cases'] if isinstance(payload,dict) else payload
    case_lookup.update({c['case_id']:c for c in cases})
examples=[]
for identifier in ['R3E2_Q002_necessary_step_deletion__r0','R3E2_Q021_merge__r0','R3C06__r0','R3C08__r0','R3C04__r0']:
    row=byid[identifier];case=case_lookup[row['case_id']]
    dest=OUT/'examples'/identifier;dest.mkdir(parents=True,exist_ok=True)
    (dest/'original_answer.txt').write_text(case['model_response'],encoding='utf-8')
    (dest/'question.txt').write_text(case['specific_question'],encoding='utf-8')
    b.save(dest/'source_trace.json',row)
    b.save(dest/'original_case.json',case)
    b.save(dest/'metrics.json',row['final_candidate_metrics'])
    check_sha=hashlib.sha256(case['model_response'].encode('utf-8')).hexdigest()
    assert check_sha==row['original_answer_sha256']
    metrics=row['final_candidate_metrics']
    def value(x):return 'NA' if x is None else f'{x:.9g}' if isinstance(x,float) else str(x)
    lines=['# '+identifier,'','这是一份真实存档答案的候选评分演示，未调用新模型，也不是专家核查。','',
        '1. 输入：[题目](question.txt) · [原始完整答案](original_answer.txt) · [原始案例与参考](original_case.json)。',
        '2. 原文、规范化全文、真实返回及各阶段处理文件均在 [完整来源链](source_trace.json) 中按路径和 SHA-256 绑定。',
        '3. 原始 SR/SP 来自提交的答案；直接评分取自同一份存档评价器返回。',
        '4. 标签按角色适用性和有来源的查表规则处理；时间按原文记录、原 prompt 的核心范围及本轮候选解释处理。',
        '5. 原公式合成 Com、Cor、Eff，再计算 IA=min(Com,Cor,Eff)、HV=Com×Cor×Eff。','',
        '| 指标 | 实际值 |','|---|---:|']
    lines += [f'| {k} | {value(v)} |' for k,v in metrics.items()]
    time=row.get('final_time_interpretation') or {}
    lines += ['','已报告核心时间：'+value(time.get('hours'))+' h。',
        '时间依据、每项贡献、排除理由、旧判项和未决项见来源链中的 `final_time_interpretation`；标签依据见 `lexical_label_derivation`。',
        '','来源链保留所有原始 NA。只有满足声明口径的分项才得到候选新值；原始直接判断没有被自动填满。']
    (dest/'README_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    examples.append({'cell_id':identifier,'source_trace':b.bind(dest/'source_trace.json'),'original_answer':b.bind(dest/'original_answer.txt')})

# Save the failed entry point for the first lexical orchestration attempt. It
# failed while passing a newly converted record, not while calling a provider.
failed_plan=b.read(OUT/'lexical_candidate_01/plan.json')
snapshot=(OUT/'run_lexical_candidate.py').read_text(encoding='utf-8')
snapshot=snapshot.replace('import argparse\n','').replace(
    "parser=argparse.ArgumentParser(description=__doc__)\nparser.add_argument('--out',type=Path,default=OUT/'lexical_candidate_02')\nDEST=parser.parse_args().out",
    "DEST=OUT/'lexical_candidate_01'")
snapshot=snapshot.replace("    scoring_row={**row,'metrics':post['metrics']}\n    if post.get('conversion'):\n        scoring_row['quantitative_data']=post['numeric']['quantitative_data']\n    staged=typed.replay_row(scoring_row,post,policy,config,runner,registry,doc=doc)",
    "    staged=typed.replay_row({**row,'metrics':post['metrics']},post,policy,config,runner,registry,doc=doc)")
snapshot=snapshot.replace("{**scoring_row,'metrics':metric}","{**row,'metrics':metric}").replace("    b.save(DEST/'records'/(row['cell_id']+'.json'),result)\n",'')
assert hashlib.sha256(snapshot.encode('utf-8')).hexdigest()==failed_plan['entrypoint']['sha256']
(OUT/'lexical_candidate_01/entrypoint_snapshot.py').write_bytes(snapshot.encode('utf-8'))
b.save(OUT/'lexical_candidate_01/failure.json',{'exception':'KeyError: quantitative_data','stage':'passing a newly full-converted formerly partial record into typed replay',
    'fixed_in':'../lexical_candidate_02','new_model_calls':0,'successful_final_run':'../lexical_candidate_02/execution.json',
    'entrypoint_snapshot_matches_failed_plan':True})
b.save(OUT/'examples/manifest.json',{'examples':examples,'new_model_calls':0})
b.save(OUT/'delivery_build_execution.json',{'command':[sys.executable,*sys.argv],'figure_source':b.bind(OUT/'scope_candidate_02/controlled_pairs.json'),
    'candidate_source':b.bind(OUT/'time_heading_candidate_01/results.json'),'new_model_calls':0})
print(json.dumps({'examples':len(examples),'figure_formats':['png','pdf','svg'],'failed_attempt_reconstructed':True}))
