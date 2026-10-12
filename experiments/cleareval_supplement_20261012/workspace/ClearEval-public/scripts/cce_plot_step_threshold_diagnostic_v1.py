"""Render existing 3-answer threshold diagnostics; never recompute a score."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
sys.dont_write_bytecode=True
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'artifacts/cce_validation/optimizer_20261010/step_threshold_diagnostic_v1'
OUT=SOURCE/'figure_v1'
THRESHOLDS=[.6,.7,.8]
QUESTIONS=[2,21,22]
BLUE='#0072B2'
ORANGE='#D55E00'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def bind(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    inputs=[SOURCE/'per_pair.csv',SOURCE/'summary.json']
    input_bindings=[bind(p) for p in inputs]
    summary=json.loads(inputs[1].read_text(encoding='utf8'))
    with inputs[0].open(encoding='utf-8-sig',newline='') as stream:raw=list(csv.DictReader(stream))
    require(len(raw)==9,'expected_nine_paired_threshold_rows')
    rows=[]
    for item in raw:
        row=dict(item)
        for key in ['question_id','reference_steps','baseline_reference_hits','variant_reference_hits']:row[key]=int(item[key])
        for key in ['threshold','baseline_sr','variant_sr','delta_sr']:row[key]=float(item[key])
        require(row['reference_steps']==7,'reference_denominator_changed')
        require(row['full_text_reparsed_both_arms']=='True','both_arm_reparse_flag_missing')
        for arm in ['baseline','variant']:
            require(0<=row[arm+'_reference_hits']<=7,'invalid_hits')
            require(math.isclose(row[arm+'_sr'],row[arm+'_reference_hits']/7,abs_tol=1e-12),'SR_numerator_denominator_mismatch')
        require(math.isclose(row['delta_sr'],row['variant_sr']-row['baseline_sr'],abs_tol=1e-12),'delta_mismatch')
        rows.append(row)
    require({(r['question_id'],r['threshold']) for r in rows}=={(q,t) for q in QUESTIONS for t in THRESHOLDS},'threshold_question_grid_changed')
    require(len({r['baseline_case_id'] for r in rows})==3 and len({r['variant_case_id'] for r in rows})==3,'not_three_paired_answers')
    require(summary['status']=='complete' and summary['unique_development_base_answers']==3,'input_summary_incomplete')
    require(summary['original_main_threshold']==.7 and summary['threshold_selection_changed'] is False,'primary_threshold_changed')
    require(summary['threshold_sensitivity_was_prespecified'] is True,'thresholds_not_prespecified')
    for expected in summary['summary']:
        group=[r for r in rows if r['threshold']==expected['threshold']]
        require(len(group)==expected['pairs']==3,'summary_denominator_mismatch')
        require(sum(r['delta_sr'] < -1e-12 for r in group)==expected['SR_decreased'],'summary_decrease_mismatch')
        require(sum(abs(r['delta_sr'])<=1e-12 for r in group)==expected['SR_unchanged'],'summary_invariance_mismatch')
    rows.sort(key=lambda r:(QUESTIONS.index(r['question_id']),r['threshold']))
    OUT.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,
        'axes.labelsize':10,'xtick.labelsize':10,'ytick.labelsize':9,'axes.linewidth':.8,
        'svg.fonttype':'none','pdf.fonttype':42,'ps.fonttype':42,'savefig.facecolor':'white'})
    fig,axes=plt.subplots(1,3,figsize=(11.4,4.7),sharex=True,sharey=True)
    fig.subplots_adjust(left=.075,right=.975,bottom=.24,top=.72,wspace=.18)
    fig.suptitle('Step-recall sensitivity to the matching threshold',y=.978,fontsize=16,fontweight='bold')
    fig.text(.5,.91,'Gemini-3-Pro: 3 paired development answers, each evaluated at 3 prespecified thresholds',ha='center',fontsize=10.4,color='#444444')
    handles=[Line2D([],[],color=BLUE,linestyle='-',marker='o',markerfacecolor='white',markeredgewidth=1.4,markersize=6,linewidth=1.9,label='Original answer'),
        Line2D([],[],color=ORANGE,linestyle='--',marker='s',markersize=5,linewidth=1.9,label='RI/storage deletion variant'),
        Line2D([],[],color='#777777',linestyle=':',linewidth=1.1,label='Primary threshold (0.7)')]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.864),ncol=3,frameon=False,handlelength=2.8,columnspacing=2.2)
    labels=[]
    for index,(qid,ax) in enumerate(zip(QUESTIONS,axes)):
        group=[r for r in rows if r['question_id']==qid]
        ax.set_title(f'{chr(97+index)}  q{qid}',loc='left',fontweight='bold',pad=11)
        ax.set_xlim(.58,.82);ax.set_ylim(0,1)
        ax.set_xticks(THRESHOLDS,labels=['0.6','0.7','0.8'])
        ax.set_yticks([0,.2,.4,.6,.8,1.0])
        ax.tick_params(direction='out',length=3.5,pad=5)
        ax.set_xlabel('Cosine-similarity threshold',labelpad=11)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',color='#DDDDDD',linewidth=.65,alpha=.8)
        ax.axvline(.7,color='#777777',linestyle=':',linewidth=1.1,zorder=1)
        for arm,color,style,marker,size,level in [('baseline',BLUE,'-','o',7.5,3),('variant',ORANGE,'--','s',4.6,4)]:
            y=[r[arm+'_sr'] for r in group]
            ax.plot(THRESHOLDS,y,color=color,linestyle=style,marker=marker,markersize=size,
                markerfacecolor='white' if arm=='baseline' else color,markeredgewidth=1.4,
                linewidth=1.85,zorder=level,clip_on=False)
            for row,value in zip(group,y):
                count=row[arm+'_reference_hits'];offset=(0,11) if arm=='baseline' else (0,-15)
                if value==1:offset=(-8,-17) if arm=='baseline' else (10,-17)
                if value==0:offset=(-16,11) if arm=='baseline' else (16,11)
                if row['baseline_reference_hits']==row['variant_reference_hits'] and value>0:
                    offset=(-9,11) if arm=='baseline' else (9,-15)
                artist=ax.annotate(f'{count}/7',(row['threshold'],value),xytext=offset,textcoords='offset points',
                    ha='center',va='center',color=color,fontsize=9.5,fontweight='normal',annotation_clip=False,
                    bbox={'facecolor':'white','edgecolor':'none','alpha':.87,'pad':.45},zorder=5)
                labels.append(artist)
    axes[0].set_ylabel('Step recall (SR)',labelpad=10)
    fig.text(.5,.104,'Labels give matched reference steps (n/7).',ha='center',fontsize=9,color='#555555')
    fig.text(.5,.06,'9 paired threshold rows are repeated evaluations of 3 base answers; no uncertainty intervals are implied.',ha='center',fontsize=9,color='#444444')
    fig.text(.5,.02,'Descriptive development diagnostic. The primary threshold remains 0.7; scientific applicability is not established by this plot.',ha='center',fontsize=8.5,color='#444444')
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    require(all(fig.bbox.contains(*a.get_window_extent(renderer).get_points()[0]) and fig.bbox.contains(*a.get_window_extent(renderer).get_points()[1]) for a in labels),'annotation_outside_figure')
    for extension in ['png','svg','pdf']:
        fig.savefig(OUT/f'step_recall_thresholds.{extension}',dpi=300)
    plt.close(fig)
    columns=['question_id','threshold','reference_steps','baseline_reference_hits','variant_reference_hits',
        'baseline_sr','variant_sr','delta_sr','baseline_case_id','variant_case_id']
    with (OUT/'step_recall_thresholds.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows({k:r[k] for k in columns} for r in rows)
    caption='''# Figure caption

**Step-recall sensitivity to prespecified matching thresholds.** Panels show three fixed Gemini-3-Pro development answers (q2, q21, q22). Blue solid lines with circles represent the original answers; orange dashed lines with squares represent the corresponding RI/storage-module deletion variants. Both arms were parsed and scored from their full texts using the unchanged original step matcher. Labels give matched reference steps out of seven; all panels share the SR scale of 0–1. The dotted vertical line marks the unchanged primary threshold of 0.7. Thresholds 0.6 and 0.8 are prespecified sensitivity settings, not newly selected operating thresholds. Lines connect the three evaluated settings and do not represent additional observations.

The deletion reduced SR in 3/3 pairs at 0.6, 1/3 at 0.7, and 0/3 at 0.8. The nine table rows are repeated evaluations of three base-answer pairs, not nine independent samples. No error bars or inferential uncertainty estimates are shown. This is a descriptive development diagnostic of the original matcher, not validation of scientific applicability or expert-confirmed step necessity. Reference-scope limitations and unmatched steps remain as recorded in the source experiment.

**中文说明：** 三个面板对应三个固定开发答案；蓝实线圆点为原答案，橙虚线方点为 RI/储存模块删除变体。n/7 表示匹配的参考步骤数。主阈值 0.7 保持不变；0.6/0.8 为原预设敏感性检查。删除后 SR 下降分别为 3/3、1/3、0/3，反映阈值对可见响应的影响。9 行来自 3 个基础答案的重复阈值计算，不是 9 个独立样本；不据此宣称科学适用性、必要步骤的专家确认或总体误差范围。
'''
    (OUT/'CAPTION.md').write_text(caption,encoding='utf8')
    require([bind(p) for p in inputs]==input_bindings,'frozen_source_changed_during_plotting')
    outputs=[OUT/f'step_recall_thresholds.{extension}' for extension in ['png','svg','pdf','csv']]+[OUT/'CAPTION.md']
    manifest={'status':'generated_from_existing_results','created_utc':datetime.now(timezone.utc).isoformat(),
        'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd()),'script':bind(__file__),
        'inputs':input_bindings,'outputs':[bind(p) for p in outputs],'input_bytes_unchanged':True,
        'python':platform.python_version(),'matplotlib':matplotlib.__version__,'source_rows':9,
        'unique_base_answers':3,'thresholds':THRESHOLDS,'primary_threshold':.7,'primary_threshold_changed':False,
        'reference_denominator':7,'plotted_points':18,'new_model_requests':0,'new_embedding_calls':0,
        'score_recomputation':False,'error_bars':False,'expert_accuracy_claimed':False,
        'annotation_boundary_check':'pass','actual_image_visual_review':'pending_separate_view_image',
        'svg_pdf_visual_status':'same_canvas_exports_not_separately_rendered'}
    save(OUT/'source_and_command.json',manifest)
    print(json.dumps({'status':'generated','output_dir':str(OUT),'source_rows':9,'unique_base_answers':3,
        'new_model_requests':0,'new_embedding_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
