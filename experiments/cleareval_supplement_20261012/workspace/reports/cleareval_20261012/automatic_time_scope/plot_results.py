"""Publication artifacts from observed conditional results; ranges are not CIs."""
import csv,json,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,
    'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
rows=b.read(OUT/'threshold_01/joint.json');dest=OUT/'figures';dest.mkdir(exist_ok=True)
models=['openai_claude-sonnet-4.6','openai_qwen3-max'];names=['Claude Sonnet 4.6','Qwen3-Max'];colors=['#9A4F16','#1769A4']
thresholds=[.6,.7,.8];pairs=[('Com','Cor'),('Com','Eff'),('Cor','Eff')];data=[]
fig,axes=plt.subplots(3,3,figsize=(10.5,8.0),layout='constrained')
for rownum,t in enumerate(thresholds):
    scenes=[r for r in rows if r['threshold']==t]
    for col,(x,y) in enumerate(pairs):
        ax=axes[rownum,col]
        for m,label,color in zip(models,names,colors):
            xs=[r['joint']['means'][m][x] for r in scenes];ys=[r['joint']['means'][m][y] for r in scenes]
            nondom=all(m in r['joint']['empirical_nondominated'] for r in scenes)
            ax.plot([min(xs),max(xs)],[min(ys),max(ys)],color=color,lw=2)
            ax.scatter(xs,ys,color=color,s=34,marker='o' if nondom else 'x',alpha=.75,zorder=3)
        ax.set(xlabel='Mean '+x,ylabel='Mean '+y,xlim=(.54,.84),ylim=(.68,.8) if y=='Cor' else (.54,.67))
        ax.grid(alpha=.18);ax.set_title(f'{chr(65+3*rownum+col)}  threshold = {t:.1f}')
fig.suptitle('CCE projections on the same two tasks (8 time branches per threshold)\nMarkers use the three-dimensional Pareto set: circle = nondominated; cross = dominated',fontsize=11)
handles=[Line2D([0],[0],marker='o',color=c,label=n,lw=1.5) for n,c in zip(names,colors)]
fig.legend(handles=handles,loc='outside lower center',ncol=2,frameon=False)
for ext in ['svg','pdf','png']:fig.savefig(dest/('cce_threshold_projections.'+ext),dpi=300)
plt.close(fig)

fig,ax=plt.subplots(figsize=(8.2,4.9),layout='constrained')
styles={14.:'o',17.:'s',18.:'^',21.:'D'}
for r in rows:
    side=-.016 if r['C08_hours']==20 else .016
    offset={14.:-.006,17.:-.002,18.:.002,21.:.006}[r['C05_hours']]
    color='#1769A4' if r['C08_hours']==20 else '#A64A13'
    ax.scatter(r['threshold']+side+offset,r['delta_mean_HV_Claude_minus_Qwen'],marker=styles[r['C05_hours']],color=color,s=38,zorder=3)
    data.append({'threshold':r['threshold'],'scenario_id':r['scenario_id'],'C05_hours':r['C05_hours'],'C08_hours':r['C08_hours'],
        'delta_mean_HV_Claude_minus_Qwen':r['delta_mean_HV_Claude_minus_Qwen'],
        **{m+'_'+k:v for m in models for k,v in r['joint']['means'][m].items()},
        'nondominated_3D':'|'.join(r['joint']['empirical_nondominated'])})
ax.axhline(0,color='#5A6570',lw=1);ax.grid(axis='y',alpha=.2)
ax.set(xticks=thresholds,xlabel='SR/SP matching threshold',ylabel='Mean per-answer HV: Claude minus Qwen',xlim=(.56,.84))
ax.set_title('Observed branch sensitivity; 4 answers / 2 paired tasks\nOffsets distinguish branches; no confidence interval or population inference',fontsize=11)
legend=[Line2D([0],[0],marker='o',color=c,ls='',label=f'C08 = {h} h') for h,c in [(20,'#1769A4'),(32,'#A64A13')]]
legend += [Line2D([0],[0],marker=m,color='#4D5660',ls='',label=f'C05 = {int(h)} h') for h,m in styles.items()]
ax.legend(handles=legend,loc='lower center',ncol=3,frameon=False,fontsize=8)
for ext in ['svg','pdf','png']:fig.savefig(dest/('hv_threshold_branches.'+ext),dpi=300)
plt.close(fig)
with (dest/'figure_data.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
b.save(dest/'manifest.json',{'command':[sys.executable,*sys.argv],'inputs':[b.bind(__file__),b.bind(OUT/'threshold_01/joint.json')],
    'files':[b.bind(p) for p in sorted(dest.iterdir()) if p.is_file() and p.name!='manifest.json'],
    'point_scope':'same four saved generator answers; derived conditional means, not new observations',
    'ranges':'explicit source timing branches; not confidence intervals','pareto':'same 3D front carried to all 2D projections'})
print(json.dumps({'figure_sets':2,'formats':['svg','pdf','png'],'data_rows':len(data)},ensure_ascii=False))
