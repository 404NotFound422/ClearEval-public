"""Descriptive fixed-five v5/v6/v7 mechanical fact retention; no model calls."""
from __future__ import annotations
import argparse,ast,csv,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'grounded_v7_stage_report_v1/figures/revision_03'
VERSIONS=['v5','v6','v7']
METRICS=[('technical','Technical completion',5),('names','Exact names',16),('initial_time','Initial time components',31),('relations','Explicit pair projections',3),('ambiguities','Explicit ambiguities',2)]
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def need(v,m):
    if not v:raise ValueError(m)
def save(p,x):
    with Path(p).open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def counts(summary,facts):
    need(summary['actual_observations']==facts['fixed_answers']==5,'FIXED_FIVE_REQUIRED')
    need([facts[k] for k in ['explicit_names_denominator','core_duration_denominator','explicit_relation_denominator','ambiguity_group_denominator']]==[16,31,3,2],'DENOMINATOR_DRIFT')
    vals={'technical':summary['technical_successes'],'names':facts['name_states'].get('exact',0),'initial_time':facts['core_initial_scope_retained'],
        'relations':facts['exact_relation_projections_retained'],'ambiguities':facts['ambiguity_states'].get('explicit_ambiguity_retained',0)}
    need(facts['core_initial_scope_retained']<=facts['record_bound_numeric_components_retained']<=facts['literal_numeric_components_retained']<=31,'TIME_RETENTION_HIERARCHY')
    for key,_,den in METRICS:need(type(vals[key]) is int and 0<=vals[key]<=den,'COUNT_OUT_OF_RANGE:'+key)
    return vals
def self_check():
    f={'fixed_answers':5,'explicit_names_denominator':16,'core_duration_denominator':31,'explicit_relation_denominator':3,'ambiguity_group_denominator':2,
        'name_states':{'exact':10},'core_initial_scope_retained':20,'record_bound_numeric_components_retained':21,'literal_numeric_components_retained':22,
        'exact_relation_projections_retained':1,'ambiguity_states':{'explicit_ambiguity_retained':1}}
    need(counts({'actual_observations':5,'technical_successes':3},f)=={'technical':3,'names':10,'initial_time':20,'relations':1,'ambiguities':1},'SOFTWARE_COUNT_MAPPING')
    caught=False
    try:counts({'actual_observations':5,'technical_successes':6},f)
    except ValueError:caught=True
    need(caught,'INVALID_TECHNICAL_COUNT_NOT_REJECTED')
    OUT.mkdir(parents=True,exist_ok=True)
    save(OUT/'plot_software_checks.json',{'status':'pass','checks':2,'real_results_read':False,'figure_created':False,'new_model_calls':0,'script':bind(__file__),'actual_command':[sys.executable,*sys.argv]})
    print(json.dumps({'status':'plot_software_checks_pass','real_results_read':False,'figure_created':False,'new_model_calls':0}))
def main():
    verification=BASE/'grounded_v7_stage_report_v1/verification.json';need(verification.exists(),'WAIT_FOR_V7_REPORT_VERIFICATION')
    v=read(verification);need(v['status']=='pass' and v['csv_rows_checked']==100 and v['source_traces_checked']==5,'V7_REPORT_NOT_VERIFIED')
    for key in ['report','facts','diagnosis','csv','report_markdown']:need(sha(v[key]['path'])==v[key]['sha256'],'VERIFIED_REPORT_CHANGED:'+key)
    need(not (OUT/'development_fact_retention.png').exists(),'IMMUTABLE_FIGURE_USE_NEW_VERSION')
    inputs=[verification];rows=[];baseline_cases=None;first_ast=None;astcheck={}
    for version in VERSIONS:
        folder=BASE/('grounded_development_'+version);sp=folder/'completion_summary.json';fp=folder/('independent_fact_audit_'+version)/'summary.json';cp=folder/'cases.json'
        need(all(p.exists() for p in [sp,fp,cp]),'COMPLETE_VERSION_REQUIRED:'+version)
        s,f=read(sp),read(fp);need(f['status']=='complete','INCOMPLETE_FACTS:'+version);c=read(cp)
        if baseline_cases is None:baseline_cases=c
        else:need(c==baseline_cases,'DIFFERENT_SOURCE_CASES:'+version)
        values=counts(s,f);inputs.extend([sp,fp,cp])
        for b in f['inputs']:need(sha(b['path'])==b['sha256'],'FACT_SOURCE_HASH_CHANGED:'+b['path'])
        checker=ROOT/('scripts/cce_audit_grounded_facts_'+version+'.py');inputs.append(checker)
        tree=ast.parse(checker.read_text(encoding='utf8'));fnames=['source_hours','name_audit','duration_audit','relation_audit','ambiguity_audit','ri_evidence_audit']
        functions={n:ast.dump(next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==n),include_attributes=False) for n in fnames}
        if first_ast is None:first_ast=functions
        astcheck[version]={n:functions[n]==first_ast[n] for n in fnames};need(all(astcheck[version].values()),'QUANTIFICATION_NOT_COMPARABLE:'+version)
        for metric,title,den in METRICS:
            rows.append({'version':version,'metric':metric,'metric_label':title,'numerator':values[metric],'denominator':den,'percent':100*values[metric]/den,
                'source_path':str(sp if metric=='technical' else fp),'source_sha256':sha(sp if metric=='technical' else fp),
                'population':'same_five_repeatedly_exposed_development_answers','counts_are_independent_samples':False,
                'valid_conversion_required_for_fact_numerator':metric!='technical','expert_gold':False})
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'development_fact_retention.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'xtick.labelsize':9,'ytick.labelsize':8,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,3,figsize=(8.2,5.7));colors=['#0072B2','#E69F00','#009E73'];hatches=['','//','..']
    fig.subplots_adjust(left=.08,right=.98,top=.87,bottom=.20,hspace=.55,wspace=.42)
    for i,(metric,title,den) in enumerate(METRICS):
        ax=axes.flat[i];chosen=[next(r for r in rows if r['metric']==metric and r['version']==ver) for ver in VERSIONS]
        bars=ax.bar(range(3),[r['percent'] for r in chosen],width=.60,color=colors,edgecolor='black',linewidth=.5)
        for b,h,r in zip(bars,hatches,chosen):
            b.set_hatch(h);ax.text(b.get_x()+b.get_width()/2,b.get_height()+3,f"{r['numerator']}/{den}",ha='center',va='bottom',fontsize=9)
        ax.set_xticks(range(3),VERSIONS);ax.set_ylim(0,116);ax.set_yticks([0,50,100]);ax.set_ylabel('Retained (%)' if metric!='technical' else 'Completed (%)')
        ax.set_title(chr(65+i)+'  '+title,loc='left',pad=8);ax.spines[['top','right']].set_visible(False)
        ax.set_axisbelow(True);ax.grid(axis='y',color='#dddddd',linewidth=.5)
    note=axes.flat[5];note.axis('off')
    note.text(0,1,'Interpretation',weight='bold',fontsize=10,va='top')
    note.text(0,.84,'Same five answers,\nreused during development\nacross these versions.\n\nValid conversion is required.\nFailures stay in denominators.\n\nComponent counts are not\nindependent answer samples.',fontsize=8.5,va='top',linespacing=1.35)
    fig.suptitle('Development: technical completion and mechanical fact retention',fontsize=12,y=.98)
    caption=('Version bundles, not isolated ablations. Source-based mechanical audit, not expert gold or scientific accuracy.\n'
        'Time: literal value + record binding + initial scope; relations: explicit endpoint projection; ambiguities: explicit retention.\n'
        'Descriptive fixed-set counts only; no inferential error bars or generalization claim. Raw mentions are not fact retention.')
    fig.text(.08,.115,caption,ha='left',va='top',fontsize=8,linespacing=1.5)
    stem=OUT/'development_fact_retention'
    for ext in ['png','pdf','svg']:fig.savefig(stem.with_suffix('.'+ext),dpi=300,facecolor='white')
    plt.close(fig)
    outputs=[stem.with_suffix('.'+x) for x in ['png','pdf','svg','csv']]
    caption_cn='同五份反复暴露的开发答案；版本组合变更，不是单因素消融。技术完成及来源机械保留均不是专家金标或科学正确性。时间计数同时要求原值、操作记录绑定与初始范围；关系计投影，歧义计明确保留；失败不移出固定分母。'
    (OUT/'CAPTION.md').write_text('# Figure scope\n\n'+caption_cn+'\n\n'+caption+'\n\nAll six fixed quantification function ASTs match across v5/v6/v7. Five answers are the sampling units; 16/31/3/2 are within-answer inventory denominators. No confidence interval is claimed from these dependent component counts.\n',encoding='utf8')
    result={'status':'generated_pending_visual_QA','data_rows':len(rows),'versions':VERSIONS,'fixed_answers':5,'fixed_denominators':[5,16,31,3,2],
        'quantification_AST_equal':astcheck,'inputs':[bind(p) for p in inputs],'outputs':[bind(p) for p in outputs],'script':bind(__file__),
        'new_model_calls':0,'expert_labels':0,'independent_generalization_claimed':False,'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'figure_run.json',result);print(json.dumps({'status':result['status'],'rows':len(rows),'png':str(outputs[0]),'new_model_calls':0}))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--self-check',action='store_true');a=ap.parse_args();self_check() if a.self_check else main()
