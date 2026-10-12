"""Plot actual q1 step scores at all frozen thresholds; no scores are recalculated."""
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as c
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    dest = c.OUT / 'figures_expanded_tasks_v4'
    paths = [c.OUT / f'q1_extension_v1/t{int(t*100):03d}_per_answer.json' for t in (.6,.7,.8)]
    sets = [c.read(p) for p in paths]
    cases = [r['answer_id'] for r in sets[1] if r['sr'] is not None]
    assert len(cases) == 11
    rows = [r for batch in sets for r in batch if r['answer_id'] in cases]
    assert len(rows) == 33
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,
                         'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig, axes = plt.subplots(1,2,figsize=(9.0,5.3),sharey=True)
    colors, markers, offsets = ['#56B4E9','#0072B2','#D55E00'], ['o','s','^'], [-.18,0,.18]
    for ax, metric in zip(axes, ['sr','sp']):
        for batch,t,col,marker,offset in zip(sets,[.6,.7,.8],colors,markers,offsets):
            by_id = {r['answer_id']:r for r in batch}
            ax.scatter([by_id[key][metric] for key in cases], [i+offset for i in range(len(cases))],
                       s=25,marker=marker,color=col,label=f'Threshold {t:.1f}',zorder=3)
        ax.set_xlim(-.035,1.035)
        ax.set_ylim(len(cases)-.55,-.55)
        ax.set_xticks([0,.25,.5,.75,1])
        ax.set_xlabel(metric.upper())
        ax.grid(axis='x',alpha=.22)
    axes[0].set_yticks(range(len(cases)),[x.removesuffix('__q1').removeprefix('openai_') for x in cases])
    axes[0].set_title('A  Reference-step recall (SR)',loc='left',fontweight='bold')
    axes[1].set_title('B  Generated-step precision (SP)',loc='left',fontweight='bold')
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.62,.935),
               ncol=3, frameon=False, fontsize=7)
    fig.suptitle('q1: the same 11 source-scored archived answers at three thresholds',fontsize=10,y=.975)
    fig.text(.02,.055,'Conditional iDISCO+ reference; development observations, no expert calibration.\n'
             'Flash: archived answer missing. DeepSeek Chat: compatible reference missing (both excluded here).\n'
             'The two Chinese GPT answers contain parsed operations but match zero reference steps at every threshold.',
             fontsize=7,va='bottom')
    fig.subplots_adjust(left=.235,right=.98,top=.84,bottom=.22,wspace=.15)
    for extension in ['png','svg','pdf']:
        fig.savefig(dest/f'q1_step_thresholds.{extension}',dpi=300)
    plt.close(fig)
    fields = ['answer_id','model','question_id','threshold','sr','sp','Com','Cor','Eff','IA','HV','reference_id','config_hash']
    c.table(dest/'q1_step_thresholds.csv',[{k:r.get(k) for k in fields} for r in rows])
    c.write(dest/'q1_plot_run.json',{'status':'complete','actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),
        'script_sha256':c.filehash(__file__),'inputs':{str(p):c.filehash(p) for p in paths},
        'plotted_answers':11,'plotted_answer_threshold_rows':33,'new_model_requests':0,
        'scope':'per-question descriptive sensitivity, not independent model quality inference'})

if __name__ == '__main__':
    main()
