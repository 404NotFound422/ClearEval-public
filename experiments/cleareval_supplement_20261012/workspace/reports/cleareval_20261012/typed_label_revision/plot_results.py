"""Standalone figures from saved offline readouts; no fabricated observations."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT=Path(__file__).resolve().parent
dest=OUT/'figures';dest.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,
                    'axes.spines.top':False,'axes.spines.right':False})

stages=['Before revision','Typed applicability','+ Pair sources','+ Author labels']
label=[11,49,55,64];complete=[10,40,44,48]
# Check plotted counts against actual stage summaries.
for i,phase in enumerate(['rules_only','with_pair_sources','with_author_labels'],start=1):
    d=json.loads((OUT/phase/'summary.json').read_text(encoding='utf-8'))
    assert d['labels_available_after']==label[i] and d['complete_after']==complete[i]
fig,ax=plt.subplots(figsize=(9.3,4.3),layout='constrained')
x=np.arange(4)
for values,offset,color,title in [(label,-.19,'#0072B2','Available label score'),
                                  (complete,.19,'#D55E00','Complete CCE')]:
    bars=ax.bar(x+offset,values,width=.36,color=color,label=title)
    ax.bar_label(bars,padding=3,fmt='%d')
ax.set_xticks(x,stages);ax.set_ylim(0,75);ax.set_yticks([0,20,40,60,67]);ax.set_ylabel('Saved evaluator returns (out of 67)')
ax.set_title('Post-hoc scoring coverage on 40 distinct answer texts',loc='left',pad=15)
ax.legend(loc='upper left',frameon=False,ncol=2)
fig.text(.02,-.055,'67 returns include repeated judgments and edited controls. No new evaluator requests.',fontsize=9)
for ext in ['png','pdf','svg']:fig.savefig(dest/('scoring_coverage.'+ext),dpi=200,bbox_inches='tight')
plt.close(fig)

joint=json.loads((OUT/'joint/common_joint.json').read_text(encoding='utf-8'))
fig,axes=plt.subplots(1,3,figsize=(11,4),layout='constrained')
colors=['#0072B2','#D55E00'];markers=['o','s']
for ax,(xkey,ykey) in zip(axes,[('Com','Cor'),('Com','Eff'),('Cor','Eff')]):
    for i,(model,m) in enumerate(joint['means'].items()):
        label=model.replace('openai_','')+' (3-D nondominated)'
        ax.scatter(m[xkey],m[ykey],s=100,c=colors[i],marker=markers[i],label=label,zorder=3)
    ax.set(xlabel=xkey,ylabel=ykey,xlim=(0,1),ylim=(0,1));ax.set_aspect('equal')
    ax.grid(alpha=.18)
fig.suptitle('Same 3-D Pareto set in each projection | common tasks: q21, q22, q248',fontsize=12)
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='outside lower center',ncol=2,frameon=False)
for ext in ['png','pdf','svg']:fig.savefig(dest/('joint_projections.'+ext),dpi=200,bbox_inches='tight')
plt.close(fig)
(dest/'figure_data.json').write_text(json.dumps({'coverage':{'stages':stages,'label':label,'complete':complete,'denominator':67},
    'joint':joint},ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved two figures as PNG, PDF, SVG and the exact plotting data.')
