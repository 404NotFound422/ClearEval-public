"""Plot frozen development-only literal flags and v2 metric agreement."""
from __future__ import annotations
import csv
import io
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE = ROOT / 'artifacts/cce_validation'
SOURCE = BASE / 'judges/stability_remediation_v2/analysis'
OUT = BASE / 'figures_followup_after104'
STEM = 'stability_remediation_v2'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_files = [SOURCE/'version_summary.json', SOURCE/'report_facts.json',
                    SOURCE/'repeat_components.json', SOURCE/'cross_family_comparison.json']
    before = {str(p): j.filehash(p) for p in source_files}
    ledger = BASE/'judges/request_ledger.jsonl'; ledger_before = j.filehash(ledger)
    history = j.read(source_files[0]); facts = j.read(source_files[1])
    within = j.read(source_files[2]); between = j.read(source_files[3])
    assert len(within) == facts['repeat_metric_groups'] == 64
    assert len(between) == facts['cross_family_groups'] == 32
    assert sum(r['nonzero_range'] for r in within) == facts['groups_with_nonzero_range']
    assert sum(r['any_disagreement'] for r in between) == facts['cross_family_disagreements']['groups_with_any_disagreement']
    versions = ['original_rubric_two_family_v2', 'final_schema_only_v1', 'extraction_examples_removed_v2']
    lookup = {r['version']: r for r in history if r['judge'] == 'local_llama3_8b'}
    assert set(versions) <= set(lookup)
    assert all(lookup[v]['observations'] == 6 and lookup[v]['technical_successes'] == 6 for v in versions)
    metrics = [('native_GFP_missing', 'GFP omitted', '#0072B2', ''),
               ('cFos_injected', 'c-Fos injected', '#D55E00', '//'),
               ('RI_numeric_contradiction', 'RI contradicted', '#009E73', '..')]
    rows = []
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8,
        'axes.labelsize': 8.2, 'axes.titlesize': 9.5, 'xtick.labelsize': 7.6,
        'ytick.labelsize': 7.5, 'legend.fontsize': 7.0,
        'svg.fonttype': 'none', 'pdf.fonttype': 42, 'axes.linewidth': .7})
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.65), gridspec_kw={'width_ratios': [1.45, 1]})
    ax = axes[0]; x = np.arange(3); width = .22
    for mi, (metric, label, color, hatch) in enumerate(metrics):
        values = [lookup[v]['literal_flags'][metric]['flagged'] for v in versions]
        denominators = [lookup[v]['literal_flags'][metric]['evaluable'] for v in versions]
        assert denominators == [6, 6, 6]
        positions = x + (mi-1)*width
        ax.bar(positions, values, width=.195, color=color, hatch=hatch, edgecolor='white',
               linewidth=.6, label=label, zorder=3)
        for pos, value, v in zip(positions, values, versions):
            if value == 0:
                ax.scatter(pos, 0, s=15, facecolors='white', edgecolors=color, linewidths=.9, zorder=5, clip_on=False)
            ax.text(pos, value + .12, str(value), ha='center', va='bottom', fontsize=7.3)
            rows.append({'panel':'A','condition':v,'metric':metric,'numerator':value,'denominator':6,
                'fraction':value/6,'unit':'flagged_observations','source_answers':2,'repeats_per_answer':3,
                'models':1,'definition':'Prespecified literal flag; not an accuracy estimate',
                'source_file':str(source_files[0]),'source_sha256':before[str(source_files[0])]})
    ax.set(xticks=x, xticklabels=['Original\nrubric','v1: final\nschema','v2: extraction\nexamples removed'],
           ylabel='Flagged observations (out of 6)', ylim=(0,6.8), yticks=[0,2,4,6], xlim=(-.55,2.55))
    ax.set_title('A  Llama: specified literal contradictions', loc='left', pad=11)
    ax.grid(axis='y',color='#dddddd',linewidth=.5,zorder=0)
    ax.legend(ncol=3,frameon=False,loc='upper center',bbox_to_anchor=(.5,-.23),
              handlelength=1.25,handletextpad=.35,columnspacing=.65)
    ax = axes[1]
    data = [('within_model_nonzero_repeat_range',facts['groups_with_nonzero_range'],len(within),'#777777'),
            ('cross_model_any_paired_difference',facts['cross_family_disagreements']['groups_with_any_disagreement'],len(between),'#CC79A7')]
    for i,(name,n,d,color) in enumerate(data):
        ax.bar(i,n/d*100,width=.53,color=color,zorder=3)
        if n==0: ax.scatter(i,0,s=22,facecolors='white',edgecolors=color,linewidths=1,zorder=5,clip_on=False)
        ax.text(i,n/d*100+3,f'{n}/{d}',ha='center',va='bottom',fontsize=9,fontweight='bold')
        rows.append({'panel':'B','condition':'extraction_examples_removed_v2','metric':name,
            'numerator':n,'denominator':d,'fraction':n/d,'unit':'metric_groups','source_answers':2,
            'repeats_per_answer':3,'models':2,
            'definition':'Range > 1e-12 within a model/answer/metric' if i==0 else 'Any same-repeat finite Qwen-Llama difference > 1e-12 for an answer/metric',
            'source_file':str(source_files[1]),'source_sha256':before[str(source_files[1])]})
    ax.set(xticks=[0,1],xticklabels=['Within model\nnonzero range','Cross-model\nany difference'],
           ylim=(0,100),yticks=[0,25,50,75,100],ylabel='Affected metric groups (%)',xlim=(-.6,1.6))
    ax.set_title('B  v2: distinct agreement checks',loc='left',pad=11)
    ax.grid(axis='y',color='#dddddd',linewidth=.5,zorder=0)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False)
        ax.tick_params(width=.7,length=3)
    fig.suptitle('Development-only extraction-example ablation',x=.08,ha='left',y=.975,fontsize=11,fontweight='bold')
    caption = ('A: 2 exposed answers × 3 repeats per prompt version; six observations are not six independent answers.\n'
               'Specified flags are not accuracy. Missing/null RI is separate (v2: 0/6 for each model).\n'
               'B: Within-model groups = 2 models × 2 answers × 16 metrics; cross-model groups = 2 answers × 16 metrics.\n'
               'All groups are evaluable. Cross-model differences exceed 10⁻¹² in 30/96 same-repeat pairs.')
    fig.text(.08,.035,caption,fontsize=6.9,va='bottom',linespacing=1.5)
    fig.subplots_adjust(left=.08,right=.985,top=.83,bottom=.35,wspace=.48)
    for ext in ('svg','pdf','png'):
        fig.savefig(OUT/f'{STEM}.{ext}',dpi=400,facecolor='white',bbox_inches='tight',pad_inches=.06)
    plt.close(fig)
    stream=io.StringIO(newline=''); writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    (OUT/f'{STEM}.csv').write_text(stream.getvalue(),encoding='utf-8-sig')
    assert len(rows)==11 and all(j.filehash(p)==h for p,h in before.items()) and j.filehash(ledger)==ledger_before
    output_hashes={str(OUT/f'{STEM}.{ext}'):j.filehash(OUT/f'{STEM}.{ext}') for ext in ('svg','pdf','png','csv')}
    j.save(OUT/f'{STEM}_plot_run.json',{'status':'generated_pending_actual_PNG_visual_inspection',
        'completed_utc':j.now(),'plot_data_rows':len(rows),'data_source_hashes':before,
        'output_sha256':output_hashes,'script_sha256':j.filehash(__file__),
        'actual_command':[sys.executable,'scripts/cce_plot_stability_remediation_v2.py'],
        'source_files_unchanged':True,'ledger_unchanged':True,'new_model_requests':0,
        'scope':'Prespecified literal flags and distinct group definitions; 2 development answers, not six independent answers; versions never pooled.'})
    print(j.canonical({'status':'generated','data_rows':len(rows),'output':str(OUT/STEM),'new_model_requests':0}))


if __name__=='__main__':main()
