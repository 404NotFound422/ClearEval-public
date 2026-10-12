"""Plot only frozen, verified method-family t070 step coverage; no score calls."""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
SOURCE=BASE/'method_family_steps_v1'
OUT=BASE/'figures_method_family_steps_v1'
STEM='method_family_sr_matrix'

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
from matplotlib.colors import Normalize
import numpy as np

LABELS={
    'gemini-3-flash':'Gemini 3 Flash',
    'gemini-3-pro':'Gemini 3 Pro',
    'glm4.7-thinking':'GLM-4.7 thinking',
    'glm4.7-unthinking':'GLM-4.7 non-thinking',
    'openai_claude-sonnet-4.6':'Claude Sonnet 4.6',
    'openai_deepseek-chat':'DeepSeek Chat',
    'openai_deepseek-reasoner':'DeepSeek Reasoner',
    'openai_gpt-5.2-fast':'GPT-5.2 fast',
    'openai_gpt-5.2-thinking':'GPT-5.2 thinking',
    'openai_qwen3-14b':'Qwen3 14B',
    'openai_qwen3-235b':'Qwen3 235B',
    'openai_qwen3-32b':'Qwen3 32B',
    'openai_qwen3-max':'Qwen3 Max',
}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,x):Path(path).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    sources=[SOURCE/'t070_per_answer.json',SOURCE/'t070_grid.json',SOURCE/'plan.json',SOURCE/'run.json',SOURCE/'verification.json']
    before={str(p):sha(p) for p in sources}
    answers=read(sources[0]);grid=read(sources[1]);plan=read(sources[2]);run=read(sources[3]);verified=read(sources[4])
    assert run['status']=='complete_pass' and verified['status']=='pass'
    for p in sources[:2]:assert run['output_sha256'][str(p)]==before[str(p)]
    assert run['plan_sha256']==before[str(sources[2])]
    models=plan['models'];qids=plan['qids']
    assert len(models)==13 and qids==[1,2,21,22,23,248] and len(answers)==77 and len(grid)==78
    answer_lookup={(r['model'],r['question_id']):r for r in answers}
    grid_lookup={(r['model'],r['question_id']):r for r in grid}
    assert len(answer_lookup)==77 and len(grid_lookup)==78
    assert set(grid_lookup)=={(m,q) for m in models for q in qids}
    rows=[];counts=collections.Counter();values=np.full((13,6),np.nan)
    for i,m in enumerate(models):
        for k,q in enumerate(qids):
            item=grid_lookup[m,q]
            missing=item['step_missing_reason']=='answer_missing'
            if missing:
                assert (m,q) not in answer_lookup and item['sr'] is None
                status='answer_missing';h=n=None
            else:
                assert item==answer_lookup[m,q]
                assert item['threshold']==.7 and item['formal_eligible'] is False
                h=item.get('reference_hits');n=item.get('reference_n')
                if item['sr'] is None:
                    status='reference_NA'
                    assert item['step_missing_reason'] in ['route_unresolved','explicit_unsupported_version','complete_compatible_reference_missing']
                else:
                    status='numeric_conditional'
                    assert isinstance(h,int) and isinstance(n,int) and 0<=h<=n and n>0
                    assert abs(item['sr']-h/n)<=1e-12
                    values[i,k]=item['sr']
            counts[status]+=1
            rows.append({'model':m,'display_model':LABELS[m],'question_id':q,'answer_id':item['answer_id'],
                'status':status,'sr':item['sr'],'sr_percent':item['sr']*100 if item['sr'] is not None else None,
                'reference_hits':h,'reference_n':n,'reference_id':item.get('reference_id'),
                'version_id':item.get('version_id'),'candidate_count':item.get('candidate_count'),
                'step_missing_reason':item['step_missing_reason'],'task_scope_status':item.get('task_scope_status'),
                'formal_eligible':False,'threshold':.7,'display_definition':'SR percentage and matched reference actions / all reference actions',
                'source_file':str(sources[1]),'source_sha256':before[str(sources[1])]})
    assert counts=={'numeric_conditional':66,'reference_NA':11,'answer_missing':1}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,
        'axes.labelsize':8.2,'axes.titlesize':9.5,'xtick.labelsize':8.1,'ytick.labelsize':8.0,
        'legend.fontsize':7.5,'svg.fonttype':'none','pdf.fonttype':42,'axes.linewidth':.7})
    fig=plt.figure(figsize=(7.2,8.45))
    ax=fig.add_axes([.275,.245,.60,.61])
    cmap=plt.get_cmap('cividis');norm=Normalize(0,1)
    text_artists=[]
    for i,m in enumerate(models):
        for k,q in enumerate(qids):
            item=rows[i*6+k];v=item['sr']
            if item['status']=='numeric_conditional':
                color=cmap(v);label=f'{v*100:.1f}%\n{item["reference_hits"]}/{item["reference_n"]}'
                rgb=np.asarray(color[:3]);linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
                luminance=float(linear @ np.array([.2126,.7152,.0722]))
                ink='white' if luminance<.24 else '#111111';hatch=None
            elif item['status']=='reference_NA':
                color='#e3e5e8';label='NA';ink='#474b52';hatch=None
            else:
                color='#fff8e6';label='No\nanswer';ink='#66521a';hatch='///'
            ax.add_patch(Rectangle((k-.5,i-.5),1,1,facecolor=color,edgecolor='#ffffff',linewidth=1.0,hatch=hatch))
            text_artists.append(ax.text(k,i,label,ha='center',va='center',fontsize=7.6,color=ink,linespacing=1.35))
    ax.set_xlim(-.5,5.5);ax.set_ylim(12.5,-.5)
    ax.set_xticks(range(6),[f'Q{q}' for q in qids]);ax.xaxis.tick_top()
    ax.set_yticks(range(13),[LABELS[m] for m in models])
    ax.tick_params(axis='both',which='both',length=0,pad=7)
    for spine in ax.spines.values():spine.set_visible(False)
    cax=fig.add_axes([.905,.48,.022,.32])
    cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax)
    cb.set_ticks([0,.25,.5,.75,1],labels=['0','25','50','75','100'])
    cb.ax.tick_params(labelsize=7.2,length=2,width=.6)
    cb.set_label('Conditional SR (%)',fontsize=8,labelpad=7);cb.outline.set_linewidth(.6)
    fig.text(.035,.963,'Conditional operation coverage within method families',fontsize=11,fontweight='bold',ha='left')
    fig.text(.035,.934,'Similarity threshold 0.70 | 13 models × 6 fixed questions | archived answers',fontsize=8.1,ha='left')
    fig.text(.275,.891,'Whole reference selected by maximum SR within the allowed method/version scope',fontsize=7.1,ha='left')
    handles=[Patch(facecolor='#e3e5e8',edgecolor='#bfc3c9',label='Reference NA (11)'),
             Patch(facecolor='#fff8e6',edgecolor='#cabd98',hatch='///',label='No answer (1)')]
    fig.legend(handles=handles,ncol=2,frameon=False,loc='upper left',bbox_to_anchor=(.265,.226),handlelength=1.7,columnspacing=2)
    fig.text(.035,.142,'Each numeric cell shows SR (%) and matched reference actions / all reference actions.\n'
        '66 of 77 available answers have conditional numeric coverage; the grid also retains 11 NA and 1 missing answer.\n'
        'NA denotes an unresolved route/version or no complete scope-compatible reference; it is not SR = 0.\n'
        'Reference action sets differ by method/version. Task applicability and expert confirmation remain pending.\n'
        'Zeros are similarity-threshold outcomes and can reflect language or matching limitations.\n'
        'These are conditional step-coverage diagnostics, not scientific accuracy or new judge assessments.',
        fontsize=7.05,ha='left',va='top',linespacing=1.6)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer();bounds=fig.bbox
    all_text=[x for x in fig.findobj(matplotlib.text.Text) if x.get_visible() and x.get_text()]
    clipped=[]
    for artist in all_text:
        box=artist.get_window_extent(renderer)
        if box.x0<bounds.x0-1 or box.y0<bounds.y0-1 or box.x1>bounds.x1+1 or box.y1>bounds.y1+1:
            clipped.append(artist.get_text())
    assert not clipped,('Text outside figure canvas',clipped)
    OUT.mkdir(parents=True,exist_ok=True)
    for extension in ['png','svg','pdf']:
        fig.savefig(OUT/f'{STEM}.{extension}',dpi=400,facecolor='white',bbox_inches='tight',pad_inches=.06)
    plt.close(fig)
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (OUT/f'{STEM}.csv').write_text(stream.getvalue(),encoding='utf-8-sig')
    reread=list(csv.DictReader((OUT/f'{STEM}.csv').open(encoding='utf-8-sig',newline='')))
    assert len(reread)==78
    for original,saved in zip(rows,reread):
        assert saved['model']==original['model'] and int(saved['question_id'])==original['question_id'] and saved['status']==original['status']
        if original['sr'] is not None:
            assert abs(float(saved['sr'])-original['sr'])<=1e-12 and int(saved['reference_hits'])==original['reference_hits'] and int(saved['reference_n'])==original['reference_n']
    assert all(sha(p)==h for p,h in before.items())
    facts={'status':'complete','figure_stem':STEM,'grid_cells':78,'available_answers':77,**dict(counts),
        'read_only_verified_inputs':before,'input_bytes_unchanged':True,'threshold':.7,'models':models,'qids':qids,
        'matrix_csv_rows_checked':78,'numeric_labels_fraction_checked':66,'text_outside_canvas':clipped,
        'inferential_error_bars':False,'new_judge_calls':0,'new_score_computations':0,
        'visual_review_status':'pending_actual_PNG_inspection','script_sha256':sha(__file__),
        'actual_command':[sys.executable,'scripts/cce_plot_method_family_steps_v1.py'],'cwd':str(ROOT),
        'artifacts':{ext:{'path':str(OUT/f'{STEM}.{ext}'),'sha256':sha(OUT/f'{STEM}.{ext}')} for ext in ['png','svg','pdf','csv']}}
    write(OUT/f'{STEM}_qa.json',facts)
    print(json.dumps({k:facts[k] for k in ['status','grid_cells','numeric_conditional','reference_NA','answer_missing','new_judge_calls','text_outside_canvas']},ensure_ascii=False))

if __name__=='__main__':main()
