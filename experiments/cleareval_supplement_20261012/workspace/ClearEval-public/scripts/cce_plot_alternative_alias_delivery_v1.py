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

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.text import Text

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
R2 = BASE / 'optimizer_round2_20261010'
OUT = R2 / 'four_hour_extension_20261010/figures_alternatives_v1'
METRICS = ['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def bind(p):
    return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def write(p,o):
    p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def finite(x):
    return type(x) in (int,float) and math.isfinite(x)

def csvwrite(p,rows):
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def load():
    alias=R2/'legacy_alternative_alias_v1/actual_01'
    paths=[alias/'paired_results.json',alias/'summary.json',alias/'verification.json']
    rows=[];pairs=[];configs={}
    six=read(paths[0]);assert len(six)==6
    assert read(alias/'verification.json')['status']=='pass'
    assert read(alias/'summary.json')['posthoc_complete_pairs']==6
    for p in six:
        label='q'+str(p['question_id'])+' / '+('Reasoner' if 'reasoner' in p['pair_id'] else 'Chat')
        if not p['original_pair_complete']:label+='*'
        pairs.append(dict(pair_id=p['pair_id'],question_id=p['question_id'],label=label,batch='legacy_six_alias_posthoc',original_complete=p['original_pair_complete'],complete=p['complete_numeric_pair'],formal_eligible=False,expert_confirmed=False))
        for m in METRICS:
            a,b=p['baseline_'+m],p['alternative_'+m]
            delta=b-a if finite(a) and finite(b) else None
            assert delta==p['delta_'+m]
            rows.append(dict(**pairs[-1],metric=m,baseline=a,alternative=b,delta=delta,source_json=str(paths[0]),source_field='baseline_/alternative_/delta_'+m))
    for name,label in [('local_alternative_q248_v1','q248 / source-guided'),('local_alternative_q2_v1','q2 / natural'),('local_alternative_q1_v1','q1 / natural')]:
        folder=BASE/'judges'/name
        path=folder/'paired_results.json';paths.extend([path,folder/'development_summary.json'])
        p,=read(path)
        complete=all(finite(p['metrics'][m][k]) for m in ['Com','Cor','Eff','IA','HV'] for k in ['baseline','alternative'])
        assert complete==(read(folder/'development_summary.json')['complete_candidate_cce_pairs']==1)
        pair=dict(pair_id=p['pair_id'],question_id=p['question_id'],label=label,batch=name,original_complete=complete,complete=complete,formal_eligible=False,expert_confirmed=False)
        pairs.append(pair)
        for m in METRICS:
            a,b=p['metrics'][m]['baseline'],p['metrics'][m]['alternative']
            delta=b-a if finite(a) and finite(b) else None
            saved=p['metrics'][m]['delta']
            assert delta==saved or (finite(delta) and finite(saved) and abs(delta-saved)<1e-12)
            rows.append(dict(**pair,metric=m,baseline=a,alternative=b,delta=delta,source_json=str(path),source_field='metrics.'+m))
    for name in ['local_alternative_development','local_alternative_q248_v1','local_alternative_q2_v1','local_alternative_q1_v1']:
        folder=BASE/'judges'/name;paths.extend([folder/'plan.json',folder/'local_config_snapshot.json'])
        models=read(folder/'local_config_snapshot.json')['models']
        configs[name]=next(m for m in models if m['name']=='local_qwen3_8b')
    assert len(pairs)==9 and len(rows)==144 and sum(p['complete'] for p in pairs)==7
    assert len({p['question_id'] for p in pairs})==6
    assert sum(not p['original_complete'] and p['complete'] for p in pairs)==1
    return pairs,rows,paths,configs

def draw(pairs,rows,out):
    # Visual inheritance from the repository paired-dot figure. Asset boxplots
    # and benchmark mean/SD bars are not valid for shared-baseline case pairs.
    metrics=['c_param','co_order','Com','Cor','Eff','sr']
    titles=['Parameter completeness','Order correctness','Com','Cor','Eff','SR (original)']
    fig,axs=plt.subplots(2,3,figsize=(183/25.4,178/25.4))
    fig.subplots_adjust(left=.21,right=.97,bottom=.13,top=.84,wspace=.33,hspace=.30)
    for i,(ax,m,title) in enumerate(zip(axs.flat,metrics,titles)):
        ax.set_title(chr(97+i)+'  '+title,loc='left',fontweight='bold')
        scale=3 if m in ['c_param','co_order'] else 1
        ax.set_xlim(-.06*scale,1.05*scale);ax.set_ylim(8.65,-.65)
        ax.set_xticks([0,1,2,3] if scale==3 else [0,.5,1])
        ax.set_yticks(range(9),[p['label'] if i%3==0 else 'q'+str(p['question_id']) for p in pairs])
        ax.tick_params(axis='y',length=0,labelsize=6.4)
        ax.spines['left'].set_visible(False)
        ax.axhspan(5.5,6.5,color='#f4f4f4',zorder=0)
        for y in [5.5,6.5,7.5]:ax.axhline(y,color='#cccccc',lw=.6,ls='--')
        for y,p in enumerate(pairs):
            row=next(r for r in rows if r['pair_id']==p['pair_id'] and r['metric']==m)
            a,b=row['baseline'],row['alternative']
            if not finite(a) and not finite(b):
                ax.text(.99,y,'NA (both)',transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=6.2,color=BLACK)
                continue
            if finite(a) and finite(b):ax.plot([a,b],[y-.12,y+.12],color=GREY,lw=.7,zorder=1)
            for v,dy,mark,color,face in [(a,-.12,'o',CATEGORICAL[0],'white'),(b,.12,'s',CATEGORICAL[3],CATEGORICAL[3])]:
                if finite(v):ax.scatter(v,y+dy,s=14,marker=mark,edgecolors=color,facecolors=face,lw=.75,zorder=3)
                else:ax.text(.99,y+dy,'NA',transform=ax.get_yaxis_transform(),ha='right',va='center',fontsize=6.2,color=BLACK)
    fig.suptitle('Alternative-route candidates: numerical contrasts, not validated equivalence',y=.975,fontsize=8.7)
    fig.text(.5,.938,'Historical Qwen3:8b evaluations; 9 candidate pairs across 6 tasks; 7 complete CCE pairs',ha='center',fontsize=7)
    fig.legend([Line2D([],[],marker='o',ls='',mec=CATEGORICAL[0],mfc='white'),Line2D([],[],marker='s',ls='',color=CATEGORICAL[3])],['Baseline answer','Alternative answer'],ncol=2,loc='upper center',bbox_to_anchor=(.58,.921))
    fig.text(.5,.075,'q21–23: six pairs share three baselines. *Existing co_chemical → co_chem field alias restored.',ha='center',fontsize=6.5)
    fig.text(.5,.050,'Shaded q248 is a separate source-guided batch; dashed lines separate other frozen batches.',ha='center',fontsize=6.5)
    fig.text(.5,.025,'No pooled mean or causal route claim. NA retained; expert-confirmed pairs = 0.',ha='center',fontsize=6.5)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();bounds=fig.bbox
    bad=[];sizes=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text():continue
        sizes.append(t.get_fontsize());bb=t.get_window_extent(renderer)
        if bb.x0<bounds.x0-1 or bb.y0<bounds.y0-1 or bb.x1>bounds.x1+1 or bb.y1>bounds.y1+1:bad.append(t.get_text())
    assert not bad,bad
    assert min(sizes)>=5
    with mpl.rc_context({'savefig.bbox':None}):
        for ext in ['pdf','svg','png']:fig.savefig(out/('alternative_route_pairs.'+ext),dpi=300,bbox_inches=None)
    plt.close(fig)
    return {'all_text_within_canvas':True,'minimum_font_pt':min(sizes),'width_mm':183,'height_mm':178,'raster_dpi':300,'individual_pairs':9,'visual_review':'pending actual view_image'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=OUT);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    pairs,rows,paths,configs=load();before=[bind(x) for x in paths]
    csvwrite(a.out/'all_pair_components.csv',rows);csvwrite(a.out/'pair_status.csv',pairs)
    write(a.out/'source_model_configs.json',configs)
    qa=draw(pairs,rows,a.out)
    assert before==[bind(x) for x in paths]
    command=[sys.executable,*sys.argv]
    caption='''# 替代路线候选：历史配置的数值恢复

图中保留9个候选对、6个任务，7对有完整CCE。q21–23的六对共享三个基线，全部采用历史Qwen3:8b批次及本轮明确字段别名恢复；q22/Chat的原失败仍保留，只把原已给出的co_chemical字段显式映射到原评分接口co_chem，未补写分数或理由。原八条成功返回的16指标保持逐值相同。

q248为独立的来源构建替代批次，以灰底和虚线隔开；q2和q1也分别保留，不因CCE不完整而删除。不同批次虽均记为Qwen3:8b，输出预算和参考/合同不同，不能合并均值或声称同一因果对照。此图未接入当前67返回的后验处理器。

六面板分别呈现c_param、co_order、Com、Cor、Eff、SR的两臂原值，蓝圆为基线，橙方为替代答案。其余10指标及所有差值保存在all_pair_components.csv（9×16=144行），不足处为NA而非0。两臂均有限时才连线。科学适用/合理替代资格仍未获专家确认（0），数值完整不等于实验路线可互换。

统计单位是固定候选答案对，不是独立生物重复；基线共享，不进行均值、误差条、显著性检验、多重比较或置信区间。无训练/测试划分、随机种子或新模型请求。图为条件性开发诊断，不能代替独立确认。

## English caption

Nine candidate alternative-route pairs across six exposed tasks are retained; seven have complete numerical CCE values. The six q21–23 pairs share three baselines and use the historical Qwen3:8b batch with an explicit existing-field alias replay. The asterisk identifies the previously failed q22/Chat record whose existing co_chemical field was mapped to co_chem; no score or explanation was imputed and its original failure was retained. The separate source-guided q248 batch is shaded; q2 and q1 remain visible with their missing components. Different batch contracts and output budgets are not pooled. Points show individual baseline and alternative values, with lines only for finite pairs. All 16 metrics and missing values are supplied as CSV. These are conditional numerical comparisons, not expert-confirmed route equivalence or isolated causal route effects.

## 图设计和检查

采用quantitative grid及仓库既有配对点图语义：每个面板是一类不同判项或CCE分项。已检查skill的PairedBoxScatter与BarComparison资产；其箱线/均值SD/显著性统计不适合共享基线的单个开发案例，因此继承点、连线、分面语义并沿用本仓库字体/导出基线。183 mm双栏，300 dpi PNG，SVG保留文本，PDF嵌入字体。原架构图及旧替代图未改。程序已核144个原值/差值、9对分母、全部源文件前后hash及画布文字边界；实际PNG目视检查另存visual_review.json。
'''
    (a.out/'CAPTION_zh_en.md').write_text(caption,encoding='utf8')
    (a.out/'EXECUTION.md').write_text('# Actual execution\n\nWorking directory: `'+str(ROOT)+'`.\n\n```text\n'+' '.join(command)+'\n```\n\nExit status is recorded by the caller; no scorer, model or embedding was invoked.\n',encoding='utf8')
    write(a.out/'provenance.json',{'status':'rendered_from_actual_saved_results','actual_command':command,'script':bind(Path(__file__)),'inputs':before,'outputs':[bind(x) for x in sorted(a.out.iterdir()) if x.is_file()],'pairs':9,'tasks':6,'complete_CCE_pairs':7,'posthoc_alias_subset_complete_pairs':6,'expert_confirmed_pairs':0,'new_model_calls':0,'new_score_calculations':0,'only_saved_pair_deltas_checked':True,'raw_or_original_results_changed':False,'current67_processor_used':False,'qa':qa})
    print(json.dumps({'status':'rendered','out':str(a.out),'pairs':9,'complete_CCE_pairs':7,'rows':len(rows),'qa':qa}))

if __name__=='__main__':main()

