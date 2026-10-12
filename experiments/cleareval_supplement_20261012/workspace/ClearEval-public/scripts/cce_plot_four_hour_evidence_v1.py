"""Render stored E2 pairs and E4 direct scores; no new scoring or requests."""
# Academic Figure Skill Typography Baseline — COPY VERBATIM, place at TOP of script
import matplotlib as mpl
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans"],
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 8,
    "figure.titlesize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "legend.frameon": False,
})
# Academic Figure Skill Nature/Cell/Science Color Palette -- COPY VERBATIM
CATEGORICAL = ["#2166AC", "#B2182B", "#1B7837", "#F1A340", "#762A83", "#666666"]
CATEGORICAL_EXTENDED = [
    "#2166AC", "#B2182B", "#1B7837", "#F1A340", "#762A83", "#666666",
    "#4393C3", "#D6604D", "#5AAE61", "#B35806", "#9970AB", "#999999",
]
DIVERGING   = ["#2166AC", "#F7F7F7", "#B2182B"]
SEQUENTIAL  = ["#F7FBFF", "#6BAED6", "#08306B"]
ACCENT_RED  = "#B2182B"
GREY        = "#999999"
BLACK       = "#222222"
# Academic Figure Skill Export Baseline — COPY VERBATIM
mpl.rcParams.update({
    "pdf.fonttype": 42,         # TrueType font embedding
    "svg.fonttype": "none",     # editable text in SVG
    "savefig.bbox": "tight",    # trim whitespace
    "savefig.dpi": 300,
})

def save_cns_figure(fig, filename):
    """Standard Academic Figure Skill export: vector PDF + 300dpi PNG preview."""
    fig.savefig(f"{filename}.pdf", bbox_inches="tight", dpi=300)
    fig.savefig(f"{filename}.png", bbox_inches="tight", dpi=300)

import argparse, csv, hashlib, json, math, sys
from pathlib import Path
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=BASE/'four_hour_extension_20261010/figures_fw3_v1'
CONDITIONS=['necessary_step_deletion','necessary_parameter_deletion','deterministic_equivalent_representation','evidence_supported_order_conflict','adjacent_entry_merge']
LABELS=['Step deletion','Time deletion','Numbering','Order conflict','Entry merge']
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
SHORT=['Completeness','Order','Method','Parameter','Chemistry']

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def bind(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def finite(x):return type(x) in (int,float) and math.isfinite(x)
def write(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def csvwrite(p,rows):
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def export(fig,out,name):
    # Keep the specified print width; all axes and text are laid out inside it.
    fig.canvas.draw()
    from matplotlib.text import Text
    texts=[x for x in fig.findobj(Text) if x.get_visible() and x.get_text()]
    small=[x.get_text() for x in texts if x.get_fontsize()<5]
    assert not small,small
    with mpl.rc_context({'savefig.bbox':None}):
        for ext in ['pdf','svg','png']:fig.savefig(out/(name+'.'+ext),dpi=300,bbox_inches=None)
    plt.close(fig)

def load_pairs():
    cells=read(BASE/'noncore_time_scope_v2/E2_execution_01/cells.json')
    idx={r['case_id']:r for r in cells}
    pairs=read(BASE/'grounded_controls_v11/per_pair.json')
    rows=[]
    for p in sorted(pairs,key=lambda x:(CONDITIONS.index(x['condition']),x['question_id'])):
        a,b=[idx[p[k]] for k in ['baseline_case_id','variant_case_id']]
        for m in a['after_metrics']:
            av,bv=a['after_metrics'][m],b['after_metrics'][m]
            rows.append(dict(pair_id=p['pair_id'],condition=p['condition'],question_id=p['question_id'],
                baseline_case_id=a['case_id'],variant_case_id=b['case_id'],metric=m,baseline=av,variant=bv,
                delta=bv-av if finite(av) and finite(bv) else None,full_CCE_pair=a['after_CCE_complete'] and b['after_CCE_complete']))
    assert len(rows)==240 and len({r['pair_id'] for r in rows})==15
    expected=read(BASE/'noncore_time_scope_v2/E2_execution_01/paired_deltas.json')
    lookup={(r['pair_id'],r['metric']):r['after_delta'] for r in expected}
    assert all(r['delta']==lookup[(r['pair_id'],r['metric'])] for r in rows)
    return rows

def controls(rows,out):
    # Visual mapping follows the existing cce_plot_fieldwise_v1 paired-dot plot.
    metrics=['c_param','co_order','Com','Cor','sr','sp']
    titles=['Parameter completeness','Order correctness','Com','Cor','SR (original)','SP (original)']
    fig,axs=plt.subplots(2,3,figsize=(183/25.4,175/25.4))
    fig.subplots_adjust(left=.20,right=.97,bottom=.09,top=.86,wspace=.32,hspace=.27)
    for i,(ax,m,title) in enumerate(zip(axs.flat,metrics,titles)):
        data=[r for r in rows if r['metric']==m];scale=3 if m in DIRECT[:2] else 1
        ax.set_title(chr(97+i)+'  '+title,loc='left',fontweight='bold')
        ax.set_xlim(-.05*scale,1.04*scale);ax.set_ylim(14.8,-.8)
        ax.set_xticks([0,1,2,3] if scale==3 else [0,.5,1])
        ax.set_yticks(range(15),[(LABELS[CONDITIONS.index(r['condition'])]+' / ' if i%3==0 else '')+'q'+str(r['question_id']) for r in data])
        ax.tick_params(axis='y',length=0,labelsize=6.1)
        ax.spines['left'].set_visible(False)
        for y,r in enumerate(data):
            a,b=r['baseline'],r['variant']
            if finite(a) and finite(b):ax.plot([a,b],[y-.11,y+.11],color=GREY,lw=.65)
            for val,off,shape,color,face in [(a,-.11,'o',CATEGORICAL[0],'white'),(b,.11,'s',CATEGORICAL[3],CATEGORICAL[3])]:
                if finite(val):ax.scatter(val,y+off,s=12,marker=shape,edgecolors=color,facecolors=face,linewidths=.75,zorder=3)
                else:ax.text(.98,y+off,'NA',transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=6)
            if y in [2,5,8,11]:ax.axhline(y+.5,color='#dddddd',lw=.4)
    fig.suptitle('Controlled changes: all 15 pairs from 3 base answers',y=.975)
    fig.legend([Line2D([],[],marker='o',ls='',mec=CATEGORICAL[0],mfc='white'),Line2D([],[],marker='s',ls='',color=CATEGORICAL[3])],['Baseline','Edited full answer'],ncol=2,loc='upper center',bbox_to_anchor=(.58,.95))
    fig.text(.5,.035,'Same processing for both arms. Original SR/SP, direct scores and formulas retained.',ha='center',fontsize=7)
    fig.text(.5,.016,'Descriptive pairs share base answers; no independence or significance is implied.',ha='center',fontsize=7)
    export(fig,out,'controlled_pairs');csvwrite(out/'controlled_pairs_all_16_metrics.csv',rows)

def repeat_figure(within,between,out):
    fig,axes=plt.subplots(1,3,figsize=(183/25.4,98/25.4))
    fig.subplots_adjust(left=.065,right=.98,bottom=.34,top=.81,wspace=.26)
    answers=['A01','A02','A03','A04','A05']
    for panel,ax in enumerate(axes):
        source=['Qwen','Codex',None][panel]
        ax.set_title(['a  Qwen: repeat range','b  Codex: repeat range','c  Codex − Qwen mean'][panel],loc='left',fontweight='bold',fontsize=7.6)
        for y,aid in enumerate(answers):
            for x,m in enumerate(DIRECT):
                if source:
                    r=next(r for r in within if r['source']==source and r['answer_id']==aid and r['metric']==m)
                    val=r['range'];lab=('NA' if val is None else f'{val:g}')+f"\n{r['finite_n']}/{r['planned_n']}"
                else:
                    r=next(r for r in between if r['answer_id']==aid and r['metric']==m)
                    val=r['Codex_minus_Qwen'];lab='NA' if val is None else (f'{val:+g}' if val else '0')
                bg='#e9e9e9' if val is None else ('#f7e5e8' if val else '#eef4fa')
                ax.add_patch(Rectangle((x-.48,y-.48),.96,.96,facecolor=bg,edgecolor='white',lw=.4))
                ax.text(x,y,lab,ha='center',va='center',fontsize=7,color=ACCENT_RED if val else BLACK)
        ax.set_xlim(-.5,4.5);ax.set_ylim(4.5,-.5)
        ax.set_xticks(range(5),SHORT,rotation=45,ha='right',rotation_mode='anchor',fontsize=6.3)
        ax.set_yticks(range(5),answers if panel==0 else ['']*5);ax.tick_params(length=0)
        for s in ax.spines.values():s.set_visible(False)
    fig.suptitle('Finite repeats agree; three direct judgments differ across sources',y=.975)
    fig.text(.5,.918,'Five exposed answers; Qwen 14/15 actual returns, Codex 12/12 returns',ha='center',fontsize=7)
    fig.text(.5,.13,'a,b: range with finite/planned repetitions below; range requires at least two finite values.',ha='center',fontsize=6.7)
    fig.text(.5,.087,'c: all-finite-repetition means, original units; NA is preserved. Codex backend is unobserved.',ha='center',fontsize=6.7)
    fig.text(.5,.044,'Repeated agreement does not establish accuracy. SR/SP are deterministic and are not judge repeats.',ha='center',fontsize=6.7)
    export(fig,out,'repeat_and_cross_source');csvwrite(out/'within_all_metrics.csv',within);csvwrite(out/'between_all_metrics.csv',between)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    paths=[BASE/'noncore_time_scope_v2/E2_execution_01/cells.json',BASE/'noncore_time_scope_v2/E2_execution_01/paired_deltas.json',BASE/'grounded_controls_v11/per_pair.json',BASE/'fieldwise_scoring_v3/actual_execution_01/summary.json']
    folder=BASE/'e4_cross_source_fw3_v1/actual_execution_02'
    paths.extend(folder/n for n in ['within.json','between.json','summary.json'])
    inputs=[bind(x) for x in paths];rows=load_pairs();within,between=read(folder/'within.json'),read(folder/'between.json')
    controls(rows,a.out);repeat_figure(within,between,a.out)
    assert inputs==[bind(x) for x in paths]
    write(a.out/'provenance.json',dict(inputs=inputs,script=bind(Path(__file__)),actual_command=[sys.executable,*sys.argv],new_model_requests=0,numeric_scores_changed=False,formats=['PDF','SVG','PNG'],print_width_mm=183,PNG_dpi=300,minimum_text_pt=6.1,visual_review='pending'))
    print(json.dumps(dict(status='rendered',out=str(a.out),controlled_pairs=15,all_metric_pairs=240,within_groups=len(within),between_groups=len(between))))
if __name__=='__main__':main()
