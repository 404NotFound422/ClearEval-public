"""Plot technical completion and the predeclared schema-development gate."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'figures_technical_followup_v1'


def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    hold = read(BASE / 'judges/holdout_remediation_v2/completion_summary.json')
    schema = read(BASE / 'judges/schema_decode_followup_v1/completion_summary.json')
    assert hold['paired_transitions'] == {'old_failure_new_success':7,'old_success_new_success':7,'old_failure_new_failure':1,'old_success_new_failure':0}
    assert schema['development_successful'] == 4 and schema['followup_attempted'] == 0
    rows = [{'panel':'A','version':'Original prompt','status':'Loadable','n':7,'denominator':15},
        {'panel':'A','version':'Original prompt','status':'Failed','n':8,'denominator':15},
        {'panel':'A','version':'Development v2 prompt','status':'Loadable','n':14,'denominator':15},
        {'panel':'A','version':'Development v2 prompt','status':'Failed','n':1,'denominator':15},
        {'panel':'B','version':'Schema decoding / development','status':'Loadable','n':4,'denominator':5},
        {'panel':'B','version':'Schema decoding / development','status':'Failed','n':1,'denominator':5},
        {'panel':'B','version':'Schema decoding / follow-up','status':'Not run: gate unmet','n':15,'denominator':15}]
    with (OUT / 'technical_followup.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
    fig,axs=plt.subplots(1,2,figsize=(10,4.2),gridspec_kw={'width_ratios':[1.25,1]},layout='constrained')
    good, bad, pending = '#2679A8','#C55D43','#9299A1'
    ax=axs[0]
    for y,yes,no in [(1,7,8),(0,14,1)]:
        ax.barh(y,yes,color=good,height=.48)
        ax.barh(y,no,left=yes,color=bad,height=.48)
        ax.text(yes/2,y,str(yes),ha='center',va='center',color='white',fontweight='bold')
        ax.text(yes+no/2,y,str(no),ha='center',va='center',color='white',fontweight='bold')
    ax.set(yticks=[1,0],yticklabels=['Original','v2 prompt'],xlim=(0,15),xticks=[0,5,10,15],xlabel='Same 15 original answers',ylim=(-.65,1.8))
    ax.set_title('A  Paired technical completion',loc='left',fontweight='bold')
    ax.text(.03,.97,'7 recovered; 7 retained; 1 still failed',transform=ax.transAxes,va='top',fontsize=9)
    ax=axs[1]
    ax.barh(1,4,color=good,height=.48);ax.barh(1,1,left=4,color=bad,height=.48)
    ax.barh(0,15,color=pending,height=.48)
    ax.text(2,1,'4 / 5 pass',ha='center',va='center',color='white',fontsize=9)
    ax.text(4.5,1,'1',ha='center',va='center',color='white')
    ax.text(7.5,0,'15 not run',ha='center',va='center',color='white')
    ax.set(yticks=[1,0],yticklabels=['Development','Follow-up'],xlim=(0,15),xticks=[0,5,10,15],xlabel='Prespecified schema-decoding matrix',ylim=(-.65,1.8))
    ax.set_title('B  Development gate not met',loc='left',fontweight='bold')
    ax.text(.03,.97,'Conflicting duplicate key rejected',transform=ax.transAxes,va='top',fontsize=9)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=good,label='Loadable'),Patch(color=bad,label='Strict-validator failure'),Patch(color=pending,label='Not run')],loc='outside lower center',ncol=3,frameon=False)
    fig.suptitle('Technical recovery does not establish extraction accuracy',fontsize=12)
    files=[]
    for ext in ('png','svg','pdf'):
        p=OUT/f'technical_followup.{ext}';fig.savefig(p,dpi=300,bbox_inches='tight');files.append(p)
    plt.close(fig)
    manifest={'status':'generated_pending_visual_inspection','data_rows':len(rows),'model_requests':0,
        'actual_command':[sys.executable,'scripts/cce_plot_technical_followup_v1.py'],
        'script_sha256':sha(Path(__file__)),
        'input_sha256':{str(p.relative_to(BASE)):sha(p) for p in [BASE/'judges/holdout_remediation_v2/completion_summary.json',BASE/'judges/schema_decode_followup_v1/completion_summary.json']},
        'files_sha256':{p.name:sha(p) for p in files+[OUT/'technical_followup.csv']}}
    (OUT/'generation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(files),'data_rows':len(rows),'new_model_requests':0}))


if __name__=='__main__':main()
