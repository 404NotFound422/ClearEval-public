"""Plot verified five-task v6/v7 partial information, without imputing scores."""
import csv,hashlib,json,math,statistics,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_round3_runner_v2 as runner
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

SOURCE=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/partial_joint_identifiability_posthoc_v1/actual_v6_01'
OUT=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/figures_joint_primary_v6_v7_01'
summary=runner.j.read(SOURCE/'summary.json')
answers=runner.j.read(SOURCE/'per_answer_bounds.json')
assert len(answers)==10 and summary['input_posthoc_complete_CCE']==3 and summary['input_posthoc_common_n']==1
models=summary['fixed_models']; bounds=summary['mean_bounds']
checks=[]
for model in models:
    group=[r for r in answers if r['model']==model]
    assert len(group)==5 and sorted(r['question_id'] for r in group)==summary['fixed_tasks']
    for metric in ['Com','Cor','Eff','IA','HV']:
        for endpoint in [0,1]:
            actual=statistics.mean(r['bounds'][metric][endpoint] for r in group)
            assert math.isclose(actual,bounds[model][metric][endpoint],rel_tol=0,abs_tol=1e-14)
            checks.append({'model':model,'metric':metric,'endpoint':endpoint,'pass':True})
assert bounds[models[0]]['Com'][0]>bounds[models[1]]['Com'][0]
assert bounds[models[0]]['Cor'][0]<bounds[models[1]]['Cor'][0]
OUT.mkdir(parents=True,exist_ok=False)
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],
    'font.size':8,'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':7,
    'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})


def render(grayscale=False):
    colors=['#252525','#808080'] if grayscale else ['#0072B2','#D55E00']
    labels=['Qwen3-14B','Qwen3-32B'];markers=['o','s'];styles=['-','--']
    fig,axes=plt.subplots(1,2,figsize=(7.2,3.4),gridspec_kw={'width_ratios':[1,1.1]})
    fig.subplots_adjust(left=.08,right=.98,bottom=.23,top=.80,wspace=.38)
    a,b=axes
    for i,model in enumerate(models):
        group=[r for r in answers if r['model']==model]
        a.scatter([r['posthoc_input_metrics']['Com'] for r in group],
            [r['posthoc_input_metrics']['Cor'] for r in group],s=17,marker=markers[i],
            facecolors='none',edgecolors=colors[i],alpha=.45,linewidths=.65)
        x,y=bounds[model]['Com'][0],bounds[model]['Cor'][0]
        a.scatter([x],[y],s=50,marker=markers[i],color=colors[i],zorder=4)
        shift=(7,7) if i==0 else (-7,9)
        a.annotate(labels[i]+' mean',(x,y),xytext=shift,textcoords='offset points',
            ha='left' if i==0 else 'right',fontsize=7,color=colors[i])
        for row,metric in enumerate(['HV','IA','Eff']):
            lower,upper=bounds[model][metric];ypos=row+(.15 if i==0 else -.15)
            b.plot([lower,upper],[ypos,ypos],color=colors[i],linestyle=styles[i],linewidth=1.7)
            b.plot([lower,lower],[ypos-.055,ypos+.055],color=colors[i],linewidth=1)
            b.plot([upper,upper],[ypos-.055,ypos+.055],color=colors[i],linewidth=1)
    a.set(xlim=(0,1.03),ylim=(0,1.03),xlabel='Mean completeness (Com)',ylabel='Mean correctness (Cor)')
    a.set_xticks([0,.25,.5,.75,1]);a.set_yticks([0,.25,.5,.75,1])
    a.text(0,-.29,'Filled: five-task means; open: individual answers.\nOpposing means rule out dominance in either direction.',
        transform=a.transAxes,fontsize=7,va='top')
    b.set(xlim=(0,1),ylim=(-.5,2.5),xlabel='Mean score: deterministic outer bounds')
    b.set_xticks([0,.25,.5,.75,1]);b.set_yticks([0,1,2],['HV','IA','Eff'])
    b.text(0,-.29,'Unresolved components vary over their allowed ranges.\nIntervals are not confidence intervals or imputed scores.',
        transform=b.transAxes,fontsize=7,va='top')
    for ax,label,title in zip(axes,['A','B'],['Known Com and Cor','Bounds retaining missing information']):
        ax.text(-.14,1.10,label,transform=ax.transAxes,fontweight='bold',fontsize=10)
        ax.set_title(title,loc='left',fontsize=9,pad=9)
    fig.suptitle('Fixed five-task comparison: 3/10 complete answers; 1/5 common complete tasks',y=.985,fontsize=10)
    handles=[Line2D([0],[0],color=colors[i],linestyle=styles[i],marker=markers[i],markersize=4,label=labels[i]) for i in range(2)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.55,.943),ncol=2,frameon=False,fontsize=8)
    fig.canvas.draw()
    # Check all axes and labels remain inside the fixed-size artifact.
    renderer=fig.canvas.get_renderer();bbox=fig.bbox
    for ax in axes:
        extent=ax.get_tightbbox(renderer)
        assert extent.x0>=0 and extent.y0>=0 and extent.x1<=bbox.width and extent.y1<=bbox.height
    stem='joint_partial_bounds_grayscale' if grayscale else 'joint_partial_bounds'
    formats=['png'] if grayscale else ['pdf','svg','png']
    for ext in formats:
        fig.savefig(OUT/(stem+'.'+ext),dpi=300,facecolor='white')
    plt.close(fig)


render();render(True)
with (OUT/'plotted_mean_bounds.csv').open('x',encoding='utf8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['model','metric','lower','upper','tasks']);writer.writeheader()
    for model in models:
        for metric,(lower,upper) in bounds[model].items():
            writer.writerow({'model':model,'metric':metric,'lower':lower,'upper':upper,'tasks':5})
runner.save_once(OUT/'plotted_answer_points.json',[{'model':r['model'],'question_id':r['question_id'],
    'answer_id':r['anonymous_answer_id'],'Com':r['posthoc_input_metrics']['Com'],'Cor':r['posthoc_input_metrics']['Cor']} for r in answers])
runner.save_once(OUT/'verification.json',{'status':'numeric_and_layout_checks_pass','checks':checks,
    'size_inches':[7.2,3.4],'raster_dpi':300,'vector_formats':['pdf','svg'],
    'font_minimum_pt':7,'redundant_encoding':['color','marker shape','line style'],
    'grayscale_rendered':True,'human_visual_review':'pending_root_image_inspection',
    'skill':'scientific-visualization','no_significance_tests_or_sampling_CIs_appropriate_to_this_fixed_panel':True,
    'source_bindings':[runner.bind(__file__),runner.bind(SOURCE/'summary.json'),runner.bind(SOURCE/'per_answer_bounds.json')],
    'outputs':[runner.bind(p) for p in sorted(OUT.iterdir()) if p.is_file()],
    'new_model_calls':0,'new_embeddings':0,'actual_command':[sys.executable,*sys.argv]})
print(json.dumps({'status':'rendered','out':str(OUT),'numeric_checks':len(checks),'new_model_calls':0}))
