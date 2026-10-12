"""Plot terminal v11 E2 analyzer outputs only; draft-check never reads the batch.

No scorer, converter, provider, source answer, or embedding module is imported.
"""
from __future__ import annotations
import argparse, copy, csv, hashlib, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
SOURCE = BASE/'grounded_controls_v11'
OUT = BASE/'grounded_controls_v11_figures_v1'
METRICS = ['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time','sr','sp','Com','Cor','Eff','IA','HV']
PLOT_METRICS = ['Com','Cor','c_param','co_order','sr','sp']
CONDITIONS = ['necessary_step_deletion','necessary_parameter_deletion','deterministic_equivalent_representation','evidence_supported_order_conflict','adjacent_entry_merge']
LABELS = ['Step deletion','Parameter deletion','Numbering equivalence','Order conflict','Adjacent-entry merge']
FILES = ['completion_summary.json','analysis_verification.json','observations.json','observations.csv','per_pair.json','per_pair.csv']
BLUE, ORANGE = '#0072B2', '#D55E00'
def require(ok, reason):
    if not ok: raise ValueError(reason)
def finite(v): return type(v) in (float,int) and math.isfinite(v)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p): return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v): Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def table(p,rows):
    with Path(p).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def validate_values(summary,verification,observations,pairs):
    require(summary['phase']=='E2' and summary['status']=='experiment_complete_not_scientific_validation','E2_NOT_COMPLETE')
    require(summary['planned_observations']==summary['actual_observations']==21 and summary['pending']==0,'NOT_ALL_21_TERMINAL')
    require(verification['status']=='pass' and verification['all_planned_terminal'] is True and verification['terminal_observations']==21,'ANALYSIS_NOT_VERIFIED')
    require(len(observations)==21 and len({r['case_id'] for r in observations})==21,'OBSERVATION_DENOMINATOR')
    require({r['anonymous_answer_id'] for r in observations}=={f'E2_{i:02}' for i in range(1,22)},'ANONYMOUS_ID_DENOMINATOR')
    require(all(r['status'] in ['success','failed'] for r in observations),'PENDING_OBSERVATION')
    require(sum(r['status']=='success' for r in observations)==summary['technical_successes'],'TECHNICAL_COUNT')
    require(sum(r['status']=='failed' for r in observations)==summary['technical_failures'],'FAILURE_COUNT')
    require(sum(r['complete_numeric_CCE'] for r in observations)==summary['complete_numeric_CCE'],'NUMERIC_COUNT')
    require(len(pairs)==15 and len({p['pair_id'] for p in pairs})==15 and summary['planned_pairs']==15,'PAIR_DENOMINATOR')
    require({(p['condition'],p['question_id']) for p in pairs}=={(c,q) for c in CONDITIONS for q in [2,21,22]},'FIVE_BY_THREE_GRID')
    idx={r['case_id']:r for r in observations}
    for k in METRICS:
        require(sum(finite(r['metrics'][k]) for r in observations)==summary['component_coverage'][k],'COVERAGE_MISMATCH:'+k)
    for p in pairs:
        a,b=(idx[p[k]] for k in ['baseline_case_id','variant_case_id'])
        require(p['same_frozen_configuration'] is True,'PAIR_CONFIG_CHANGED')
        both=a['status']==b['status']=='success'
        require(p['both_arms_technical_complete']==both,'PAIR_TECHNICAL_STATE')
        require(p['pair_state']==('available' if both else 'failed_arm'),'PAIR_STATUS')
        for arm,r in [('baseline',a),('variant',b)]:
            require(p[arm+'_status']==r['status'],'ARM_STATUS')
            for k in METRICS: require(p[arm+'_'+k]==r['metrics'][k],'ARM_VALUE_MISMATCH')
        for k in METRICS:
            av,bv=p['baseline_'+k],p['variant_'+k]
            available=finite(av) and finite(bv) and (k in ['sr','sp'] or both)
            require(p['available_'+k] is available,'PAIR_AVAILABILITY')
            require((available and finite(p['delta_'+k]) and math.isclose(p['delta_'+k],bv-av,abs_tol=1e-12)) or (not available and p['delta_'+k] is None),'PAIR_DELTA_NA_MISMATCH')
    require(sum(p['both_arms_technical_complete'] for p in pairs)==summary['technical_complete_pairs'],'TECHNICAL_PAIR_COUNT')
    require(sum(p['complete_numeric_pair'] for p in pairs)==summary['complete_numeric_pairs'],'NUMERIC_PAIR_COUNT')
    return sorted(pairs,key=lambda p:(CONDITIONS.index(p['condition']),[2,21,22].index(p['question_id'])))
def csv_agrees(path,rows,keys):
    with Path(path).open(encoding='utf-8-sig',newline='') as f: actual=list(csv.DictReader(f))
    require(len(actual)==len(rows),'CSV_DENOMINATOR')
    for a,b in zip(actual,rows):
        for key in keys:
            val=b[key];expected='' if val is None else str(val)
            require(a[key]==expected,'CSV_JSON_DIFFER:'+key)
def load_terminal():
    paths=[SOURCE/f for f in FILES];bindings=[bind(p) for p in paths]
    summary,verification,obs,_,pairs,_=[read(p) if p.suffix=='.json' else None for p in paths]
    require(verification['science_acceptance_not_implied'] is True,'ANALYSIS_SCOPE_CHANGED')
    # Verify original analyzer metadata hashes without following raw/case/receipt links.
    allowed={'plan.json','matrix.json','observations.json','completion_summary.json'}
    require({Path(b['path']).name for b in verification['bindings']}==allowed,'VERIFICATION_BINDING_SET')
    for b in verification['bindings']:
        p=Path(b['path']).resolve();require(p.parent==SOURCE.resolve() and p.name in allowed,'OUT_OF_SCOPE_BINDING')
        require(sha(p)==b['sha256'],'ANALYSIS_BINDING_CHANGED');bindings.append(bind(p))
    plan=read(SOURCE/'plan.json')
    require(plan['phase']=='E2' and plan['candidate_version']=='source_bound_extraction_v11' and plan['planned_observations']==21
        and plan['planned_pairs']==15 and plan['planned_new_requests']==21 and plan['planned_reused_observations']==0,'V11_E2_PLAN_CHANGED')
    ordered=validate_values(summary,verification,obs,pairs)
    csv_agrees(SOURCE/'observations.csv',obs,['anonymous_answer_id','case_id','status',*METRICS])
    csv_agrees(SOURCE/'per_pair.csv',pairs,['pair_id','condition','question_id',*['delta_'+k for k in METRICS],*['available_'+k for k in METRICS]])
    return summary,verification,obs,ordered,bindings
def pair_table(pairs,metrics):
    return [{'pair_id':p['pair_id'],'condition':p['condition'],'question_id':p['question_id'],'baseline_case_id':p['baseline_case_id'],'variant_case_id':p['variant_case_id'],
        'baseline_status':p['baseline_status'],'variant_status':p['variant_status'],'metric':k,'baseline':p['baseline_'+k],'variant':p['variant_'+k],
        'paired_available':p['available_'+k],'delta_variant_minus_baseline':p['delta_'+k],
        'same_frozen_configuration':p['same_frozen_configuration'],'both_arms_technical_complete':p['both_arms_technical_complete'],
        'complete_numeric_pair':p['complete_numeric_pair'],'reference_switch':p['adaptive_vs_fixed_baseline_reference']['reference_switch']} for p in pairs for k in metrics]
def style():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':11,'axes.labelsize':9,'xtick.labelsize':8,'ytick.labelsize':8,
        'axes.linewidth':.8,'svg.fonttype':'none','pdf.fonttype':42,'ps.fonttype':42,'savefig.facecolor':'white'})
    return plt,matplotlib
def export(fig,out,name):
    from matplotlib.text import Text
    fig.canvas.draw();renderer=fig.canvas.get_renderer();outside=[]
    for obj in fig.findobj(match=Text):
        if obj.get_visible() and obj.get_text().strip():
            bb=obj.get_window_extent(renderer)
            if not (fig.bbox.x0-1<=bb.x0<=bb.x1<=fig.bbox.x1+1 and fig.bbox.y0-1<=bb.y0<=bb.y1<=fig.bbox.y1+1):outside.append(obj.get_text())
    require(not outside,'TEXT_OUTSIDE_CANVAS:'+repr(outside))
    for ext in ['png','svg','pdf']:fig.savefig(out/f'{name}.{ext}',dpi=300)
def paired_figure(plt,pairs,out):
    from matplotlib.lines import Line2D
    fig,axes=plt.subplots(2,3,figsize=(12.2,10.7));fig.subplots_adjust(left=.17,right=.925,bottom=.105,top=.875,wspace=.46,hspace=.27)
    fig.suptitle('Controlled full-text comparisons: v11 E2',fontsize=15,fontweight='bold',y=.975)
    fig.text(.5,.942,'15 pairs from 3 base answers; all 21 terminal observations retained',ha='center',fontsize=10)
    fig.legend([Line2D([],[],marker='o',linestyle='',color=BLUE,markerfacecolor='white'),Line2D([],[],marker='s',linestyle='',color=ORANGE),Line2D([],[],color='#888888')],
        ['Baseline','Edited answer','Available within-pair comparison'],loc='upper center',bbox_to_anchor=(.5,.922),ncol=3,frameon=False,fontsize=9)
    for panel,(ax,k) in enumerate(zip(axes.flat,PLOT_METRICS)):
        scale=3 if k in ['c_param','co_order'] else 1
        n=sum(p['available_'+k] for p in pairs)
        ax.set_title(f'{chr(97+panel)}  {k.upper() if k in ["sr","sp"] else k}   ({n}/15 comparable)',loc='left',fontweight='bold')
        ax.set_xlim(-.045*scale,1.045*scale);ax.set_ylim(14.75,-.8);ax.set_xticks([0,1,2,3] if scale==3 else [0,.25,.5,.75,1])
        ax.set_yticks(range(15),[f'{LABELS[i//3]}\nq{p["question_id"]}' if i%3==0 else f'q{p["question_id"]}' for i,p in enumerate(pairs)] if panel%3==0 else [f'q{p["question_id"]}' for p in pairs])
        ax.tick_params(axis='y',length=0);ax.grid(axis='x',color='#dddddd',linewidth=.6);ax.spines[['top','right','left']].set_visible(False)
        ax.set_xlabel('Original metric scale')
        for y,p in enumerate(pairs):
            a,b=p['baseline_'+k],p['variant_'+k]
            if p['available_'+k]:ax.plot([a,b],[y-.12,y+.12],color='#888888',lw=1,zorder=1)
            for arm,val,col,mark,offset in [('B',a,BLUE,'o',-.12),('V',b,ORANGE,'s',.12)]:
                if finite(val):
                    require(0<=val<=scale,'PLOT_SCALE_VIOLATION:'+k)
                    ax.scatter(val,y+offset,s=23,color=col,marker=mark,facecolors='white' if arm=='B' else col,linewidths=1.1,zorder=3)
                else:
                    status=p['baseline_status' if arm=='B' else 'variant_status']
                    ax.text(1.06,y+offset,f'{arm}:F' if status=='failed' else f'{arm}:NA',transform=ax.get_yaxis_transform(),va='center',fontsize=6.8,color=col)
            if y in [2,5,8,11]:ax.axhline(y+.5,color='#bbbbbb',lw=.7)
    fig.text(.5,.055,'F = failed judge arm; NA = unavailable metric after a successful arm. Neither is plotted at zero.',ha='center',fontsize=9)
    fig.text(.5,.028,'Known SR/SP survive judge failure; these are deterministic step results, not successful judge assessments.',ha='center',fontsize=9)
    export(fig,out,'paired_components');plt.close(fig)
def coverage_figure(plt,obs,pairs,out):
    from matplotlib.colors import ListedColormap
    import numpy as np
    fig,axes=plt.subplots(1,2,figsize=(11.2,9.7),gridspec_kw={'width_ratios':[1.1,1]});fig.subplots_adjust(left=.105,right=.955,bottom=.09,top=.87,wspace=.43)
    fig.suptitle('Metric availability without replacing NA by zero',fontsize=15,fontweight='bold',y=.976)
    fig.text(.5,.94,'Fixed denominators: 21 observations and 15 pairs; counts are descriptive, not independent samples',ha='center',fontsize=9.5)
    ax=axes[0];yy=np.arange(len(METRICS));observed=[sum(finite(r['metrics'][k]) for r in obs) for k in METRICS];paired=[sum(p['available_'+k] for p in pairs) for k in METRICS]
    ax.barh(yy-.18,observed,height=.33,color=BLUE,label='Finite observations / 21');ax.barh(yy+.18,paired,height=.33,color=ORANGE,label='Comparable pairs / 15')
    for y,a,b in zip(yy,observed,paired):ax.text(a+.3,y-.18,f'{a}/21',va='center',fontsize=8);ax.text(b+.3,y+.18,f'{b}/15',va='center',fontsize=8)
    ax.set_yticks(yy,METRICS);ax.invert_yaxis();ax.set_xlim(0,26);ax.set_xticks([0,5,10,15,21]);ax.set_xlabel('Actual count');ax.set_title('a  Coverage by metric',loc='left',fontweight='bold')
    ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False,loc='lower right',fontsize=8);ax.grid(axis='x',alpha=.16)
    ax=axes[1];chosen=['Eff','IA','HV'];obs=sorted(obs,key=lambda r:r['anonymous_answer_id']);states=[]
    for r in obs:states.append([2 if finite(r['metrics'][k]) else 0 if r['status']=='success' else 1 for k in chosen])
    ax.imshow(states,cmap=ListedColormap(['#ffffff','#dddddd','#cce5ef']),vmin=0,vmax=2,aspect='auto',interpolation='none')
    for y,r in enumerate(obs):
        for x,k in enumerate(chosen):
            value=r['metrics'][k];text=f'{value:.3g}' if finite(value) else 'F' if r['status']=='failed' else 'NA'
            ax.text(x,y,text,ha='center',va='center',fontsize=8)
    ax.set_xticks(range(3),chosen);ax.xaxis.tick_top();ax.set_yticks(range(21),[f'{r["anonymous_answer_id"]} / q{r["question_id"]}' for r in obs]);ax.tick_params(length=0)
    ax.set_title('b  All observations: joint-score availability',loc='left',fontweight='bold',pad=26)
    for y in range(22):ax.axhline(y-.5,color='#bbbbbb',lw=.4)
    fig.text(.5,.04,'Finite values (including genuine zero) retain their values. White NA = unresolved; gray F = failed judge arm.',ha='center',fontsize=9)
    export(fig,out,'metric_coverage');plt.close(fig)
def render(args):
    require(args.root_authorized,'ROOT_RENDER_AUTHORIZATION_REQUIRED')
    out=args.out.resolve();require(out.is_relative_to(OUT.resolve()) and not out.exists(),'NEW_SNAPSHOT_ONLY')
    summary,verification,obs,pairs,bindings=load_terminal()
    out.mkdir(parents=True);plt,matplotlib=style();paired_figure(plt,pairs,out);coverage_figure(plt,obs,pairs,out)
    table(out/'paired_components.csv',pair_table(pairs,PLOT_METRICS));table(out/'all_pair_components.csv',pair_table(pairs,METRICS))
    coverage=[{'anonymous_answer_id':r['anonymous_answer_id'],'case_id':r['case_id'],'question_id':r['question_id'],'trial_status':r['status'],'failure_stage':r['failure_stage'],
        'metric':k,'value':r['metrics'][k],'finite':finite(r['metrics'][k]),'deterministic_step_component':k in ['sr','sp']} for r in obs for k in METRICS]
    table(out/'metric_coverage.csv',coverage)
    caption=f'''# v11 E2 paired figures

Paired components show all 15 planned comparisons (five edit categories × three base answers), using the unchanged original analyzer values. Blue circles are the specified baseline; orange squares are its edited full-text answer. A gray connector appears only for an available two-arm comparison. Missing values are indicated in a separate gutter, never replaced with zero. F marks a failed judge arm; NA marks an unavailable metric despite a successful arm. SR/SP remain the original independently verified step components and may be finite when a judge fails. No new score, threshold, statistic, uncertainty interval, or reference selection is computed.

The coverage figure retains all 21 observations: three natural baselines, three canonical numbered baselines, and 15 edited variants. They arise from three exposed development answers, not 21 independent tasks. The figure gives availability out of 21 observations and 15 pairs, and displays Eff/IA/HV for every observation, including all failed and unresolved cells. Baselines are reused across their designated pairs; the paired rows are not independent samples. The control edits do not establish expert-confirmed biological necessity or correct order.

Actual technical success: {summary['technical_successes']}/21. Complete numeric CCE: {summary['complete_numeric_CCE']}/21 observations and {summary['complete_numeric_pairs']}/15 pairs. No claim of scientific acceptance follows from a terminal or verified analysis. Existing architecture figures are untouched.

中文：全部 21 观察、15 配对保留；连线仅表示两臂有可比较结果。失败及 NA 不作为零分。SR/SP 是原步骤评分，不能冒充 judge 成功。该图只描述公开开发控制的数值响应，不将标题中的“必要”视作专家金标。
'''
    (out/'CAPTION.md').write_text(caption,encoding='utf8')
    require(all(sha(b['path'])==b['sha256'] for b in bindings),'SOURCE_CHANGED_DURING_RENDER')
    outputs=[bind(p) for p in sorted(out.iterdir()) if p.is_file()]
    save(out/'source_and_command.json',{'status':'rendered_existing_analysis_not_scientific_acceptance','created_utc':datetime.now(timezone.utc).isoformat(),
        'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd()),'script':bind(__file__),'inputs':bindings,'outputs':outputs,
        'style_precedent':bind(ROOT/'scripts/cce_plot_step_threshold_diagnostic_v1.py'),'matplotlib_version':matplotlib.__version__,
        'observation_denominator':21,'pair_denominator':15,'base_answer_denominator':3,'input_bytes_unchanged':True,
        'new_model_requests':0,'new_embeddings':0,'score_recomputation':False,'error_bars':False,'architecture_figure_modified':False})
    save(out/'visual_qa.json',{'canvas_text_boundary_check':'pass','PNG_visual_review':'pending_view_image',
        'SVG_PDF':'same_canvas_exports_not_separately_rendered','minimum_font_pt':6.8,'PNG_dpi':300,'actual_scientific_results':True})
    print(json.dumps({'status':'rendered','out':str(out),'observations':21,'pairs':15,'visual_review':'pending_view_image'}))
def draft_check(args):
    # Synthetic values test only the plotting contract; no real batch path is read.
    obs=[]
    for i in range(21):
        values={k:0.0 for k in METRICS};status='failed' if i==6 else 'success'
        if status=='failed':values={k:0.0 if k in ['sr','sp'] else None for k in METRICS}
        obs.append({'anonymous_answer_id':f'E2_{i+1:02}','case_id':f'synthetic_{i}','status':status,'metrics':values,'complete_numeric_CCE':status=='success'})
    pairs=[]
    for i in range(15):
        a,b=obs[i%3],obs[i+6];both=b['status']=='success'
        p={'pair_id':str(i),'condition':CONDITIONS[i//3],'question_id':[2,21,22][i%3],'baseline_case_id':a['case_id'],'variant_case_id':b['case_id'],
            'baseline_status':a['status'],'variant_status':b['status'],'both_arms_technical_complete':both,'same_frozen_configuration':True,'pair_state':'available' if both else 'failed_arm','complete_numeric_pair':both}
        for k in METRICS:
            avail=both or k in ['sr','sp'];p.update({'baseline_'+k:a['metrics'][k],'variant_'+k:b['metrics'][k],'available_'+k:avail,'delta_'+k:0.0 if avail else None})
        pairs.append(p)
    summary={'phase':'E2','status':'experiment_complete_not_scientific_validation','planned_observations':21,'actual_observations':21,'pending':0,'technical_successes':20,'technical_failures':1,
        'planned_pairs':15,'technical_complete_pairs':14,'complete_numeric_pairs':14,'complete_numeric_CCE':20,'component_coverage':{k:sum(finite(o['metrics'][k]) for o in obs) for k in METRICS}}
    ver={'status':'pass','all_planned_terminal':True,'terminal_observations':21};validate_values(summary,ver,obs,pairs)
    checks=[{'name':'complete_synthetic_grid_and_known_zero','pass':True}]
    for label,kind in [('pending_batch','pending'),('NA_delta_replaced_by_zero','delta'),('missing_pair','pair'),('lost_observation','obs'),('changed_configuration','config'),('wrong_available_flag','available')]:
        s,v,o,p=copy.deepcopy((summary,ver,obs,pairs))
        if kind=='pending':s['pending']=1
        elif kind=='delta':p[0]['delta_Com']=0
        elif kind=='pair':p.pop()
        elif kind=='obs':o.pop()
        elif kind=='config':p[0]['same_frozen_configuration']=False
        else:p[0]['available_Com']=True
        rejected=False
        try:validate_values(s,v,o,p)
        except (ValueError,KeyError):rejected=True
        require(rejected,'DRAFT_NEGATIVE_ACCEPTED:'+label);checks.append({'name':label,'pass':rejected})
    out=OUT/'draft';out.mkdir(parents=True,exist_ok=True)
    save(out/'checks.json',{'status':'pass','checks':checks,'actual_command':[sys.executable,*sys.argv],'script':bind(__file__),
        'real_batch_reads':0,'figures_rendered':0,'model_calls':0,'score_calls':0,'scope':'synthetic metadata contract checks only; not layout QA or scientific validation'})
    print(json.dumps({'status':'pass','checks':len(checks),'real_batch_reads':0,'figures_rendered':0}))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft-check','render']);p.add_argument('--out',type=Path,default=OUT/'actual_01');p.add_argument('--root-authorized',action='store_true');args=p.parse_args()
    globals()[args.action.replace('-','_')](args)
if __name__=='__main__':main()
