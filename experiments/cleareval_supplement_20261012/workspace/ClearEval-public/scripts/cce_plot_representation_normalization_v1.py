"""Report actual development-only representation results without changing scores."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/cce_validation/representation_normalization_v1'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    source=OUT/'summary.json'; h=sha(source); summary=read(source)
    rows=summary['primary_granularity_pairs']
    assert len(rows)==3 and all(r['same_normalized_unit_texts'] for r in rows)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,2,figsize=(9.0,4.7),sharey=True)
    fig.subplots_adjust(left=.09,right=.98,bottom=.28,top=.76,wspace=.22)
    fig.suptitle('Step-boundary normalization removes observed merge sensitivity',x=.09,y=.96,ha='left',fontsize=13,weight='bold')
    fig.text(.09,.875,'Three existing development pairs; same text content, encoder, threshold 0.7 and references',fontsize=9)
    plot_rows=[]
    for ax,metric,label in zip(axes,('sr','sp'),('A   SR','B   SP')):
        ax.axhline(0,color='#555555',linewidth=.7)
        for i,r in enumerate(rows):
            for offset,key,color,legend in [(-.16,'old_primary_delta_'+metric,'#D55E00','Original entries'),
                                           (.16,'delta_'+metric,'#0072B2','Lexical boundaries')]:
                v=r[key]
                ax.bar(i+offset,v,width=.28,color=color,label=legend if i==0 else None,zorder=2)
                ax.scatter(i+offset,v,color=color,s=20,zorder=3)
                ax.annotate(f'{v:+.3f}' if v else '0',(i+offset,v),xytext=(0,-12 if v<0 else 6),
                    textcoords='offset points',ha='center',fontsize=9)
                plot_rows.append({'question_id':r['question_id'],'metric':metric,'configuration':legend,
                    'delta_merged_minus_baseline':v,'threshold':.7,'source_sha256':h})
        ax.set_title(label,loc='left',fontsize=11,weight='bold')
        ax.set_xticks(range(3),[f"q{r['question_id']}" for r in rows])
        ax.set_ylim(-.86,.45);ax.set_yticks([-.75,-.5,-.25,0,.25]);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Merged minus baseline');axes[1].legend(loc='lower right',fontsize=8,frameon=False)
    fig.text(.09,.16,'Normalization preserves the operation-text stream and recovers identical units for these pairs.',fontsize=9)
    fig.text(.09,.115,'This is a surface-form development diagnostic, not semantic extraction accuracy or independent validation.',fontsize=8)
    fig.text(.09,.07,'0 new judge calls; 85 cached vectors reused; original scoring configuration remains unchanged.',fontsize=8)
    for ext in ('png','svg','pdf'):fig.savefig(OUT/f'paired_merge_normalization.{ext}',dpi=300,bbox_inches='tight')
    plt.close(fig)
    with (OUT/'paired_merge_normalization.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(plot_rows[0]));w.writeheader();w.writerows(plot_rows)
    table='\n'.join(f"| q{r['question_id']} | {r['baseline_sr']:.4f} | {r['baseline_sr']+r['old_primary_delta_sr']:.4f} | {r['variant_sr']:.4f} | {r['baseline_n']} |" for r in rows)
    (OUT/'README.md').write_text(f'''# 步骤条目合并：已运行的开发性修复诊断

在21份既有公开开发全文、15个原配对上运行了新的词面边界规范化，三个阈值各21份步骤结果。主阈值0.7时，3个相邻条目合并对的SR/SP变化均归零；没有修改操作文字或顺序，也没有调整阈值、权重或编码器。两份作者参考仍各7步。新增judge请求0、新增向量0，复用85个缓存向量。

| 题目 | 原基线SR | 原合并后SR | 新规则合并后SR | 新规则基线与合并后步数 |
|---|---:|---:|---:|---:|
{table}

新规则先用原分割器提取操作文本，再连接成保留全部非空白内容的文本流，在标点或闭合参数括号之后、明确英语操作开头之前重新确定边界。21份输入中，原分割器已选中的操作文本均保持内容与顺序；这不等于原分割器提取了全文所有标题和段落。三个合并对的操作文本流相同，恢复的编码单元也相同。因此本结果证明这些既有词面变体的表示敏感性可以消除，不能据此声称语义提取准确、中文/任意写法稳健或专家核查通过。参数是否仍正确附着于所属操作尚需核查。

其他主阈值配对也已实际运行：3个等义表示变化SR/SP均不变；3个顺序变化SR/SP仍不变；3个步骤删除对仅1个SR下降；参数删除3对SR均不变、1个SP变化。这些无响应均保留。此修复不会赋予SR顺序判断能力，也没有解决阈值以下的连续变化或参数正确性判定。

使用的是既有Gemini-Pro q2/q21/q22公开开发控制，不能统称既定A01–A05五份人工开发答案，也不是新增15个独立案例。没有重新调用judge；旧完整管线观测保留，本轮只重算步骤分项。该规则未替换主BioProBench配置，未进入留出分析。

[逐对CSV](paired_results.csv) · [逐答案详细匹配](per_case.json) · [原分段及新边界](units.json) · [配置](plan.json) · [执行与输入哈希](execution.json) · [图PNG](paired_merge_normalization.png)

实际命令（均exit 0，工作目录为仓库）：

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_representation_normalization_v1.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_representation_normalization_v1.py run
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_plot_representation_normalization_v1.py
```
''',encoding='utf-8')
    assert sha(source)==h
    save(OUT/'plot_run.json',{'status':'pass','actual_command':[sys.executable,*sys.argv],
        'input_sha256':{str(source):h},'plot_rows':len(plot_rows),'visual_qa':'pending_view_image',
        'outputs':{p.name:sha(p) for p in OUT.glob('paired_merge_normalization.*')},'new_judge_requests':0})
    print(json.dumps({'status':'pass','plot_rows':len(plot_rows),'formats':['png','svg','pdf','csv']}))

if __name__=='__main__':main()
