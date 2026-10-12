"""Source-bound optimizer stage comparison; zero calls and no frozen edits.

Finalization requires all five v3 trials and the complete independent v3 fact
review. Preflight checks earlier completed inputs without publishing a final v3
comparison. Numeric availability is never interpreted as factual correctness.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,io,json,math,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'optimizer_stage_comparison_v1'
INVENTORY=BASE/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json'
INVENTORY_SHA='0dd8cb9dedcfcd41ec754011bb276f88d92229e7fbd5b83e410c52a687220b82'
IDS=['A01','A02','A03','A04','A05']
METRICS=['c_param','co_order','co_method','co_param','co_chem','s_method','s_label','s_trans','s_time']
STAGES=[('model_probe_v1',None,'仅换为27B的模型对照'),('grounded_development_v1','v1','来源约束 v1'),
        ('grounded_development_v2','v2','来源约束 v2'),('grounded_development_v3','v3','来源约束 v3')]
LEDGER=ROOT/'artifacts/cce_validation/judges/request_ledger.jsonl'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def digest(x):return rawsha(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def ratio(n,d):return '不可同口径比较' if n is None else f'{n}/{d}'
def csvsave(p,rows):
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def verify_bindings(entries,used):
    for entry in entries:
        p=Path(entry['path']);require(p.exists() and sha(p)==entry['sha256'],'BOUND_SOURCE_CHANGED:'+str(p));used.append(p)

def numeric_counts(rows,grounded):
    key='component_gated_proposals' if grounded else 'original_numeric_proposals'
    return {metric:sum(r.get('status')=='success' and finite(r.get(key,{}).get(metric)) for r in rows) for metric in METRICS}

def summarize_facts(version,summary,rows):
    require(summary['status']=='complete' and summary['fixed_answers']==5 and len(rows)==5,'FACT_REVIEW_NOT_COMPLETE_FIVE')
    require([r['anonymous_answer_id'] for r in rows]==IDS,'FACT_REVIEW_FIXED_IDS')
    require([summary[k] for k in ['explicit_names_denominator','core_duration_denominator','explicit_relation_denominator','ambiguity_group_denominator']]==[16,31,3,2],'FACT_DENOMINATORS_CHANGED')
    names=collections.Counter(r['status'] for c in rows for r in c['names'])
    durations=[r for c in rows for r in c['core_duration_components']]
    available=sum(c['conversion_available'] for c in rows)
    require(names==collections.Counter(summary['name_states']) and len(durations)==31,'FACT_NAMES_OR_COMPONENTS_DISAGREE')
    require(available==summary['auditable_conversions'],'FACT_CONVERSION_COUNT_DISAGREES')
    literal_key='literal_source_numeric_value_retained'
    bound_key='record_bound_numeric_retained' if version=='v3' else 'v2_record_bound_numeric_retained'
    if version=='v1':
        # The v1 batch has no valid conversion. Unknown facts are unavailable,
        # not factual absences and not rescued by a separate raw diagnostic.
        require(available==0,'V1_NEEDS_EXPLICIT_REPRESENTATION_REVIEW_IF_CONVERSIONS_EXIST')
        literal=0;bound=0
    else:
        literal=sum(r.get(literal_key) is True for r in durations)
        bound=sum(r.get(bound_key) is True for r in durations)
        require(literal==summary['literal_numeric_components_retained'],'LITERAL_RETENTION_SUMMARY_MISMATCH')
        skey='record_bound_numeric_components_retained' if version=='v3' else 'v2_record_bound_numeric_components_retained'
        require(bound==summary[skey],'RECORD_BOUND_RETENTION_SUMMARY_MISMATCH')
    unavailable=sum(r['status']=='unavailable' for r in durations)
    edges=sum(r['edge_retained'] is True for c in rows for r in c['relations'])
    projections=sum(r['exact_legacy_projection_retained'] is True for c in rows for r in c['relations'])
    ambiguity=collections.Counter(a['status'] for c in rows for a in c['ambiguities'])
    require(edges==summary['exact_endpoint_edges_retained'] and projections==summary['exact_relation_projections_retained'],'RELATION_SUMMARY_DISAGREES')
    require(ambiguity==collections.Counter(summary['ambiguity_states']),'AMBIGUITY_SUMMARY_DISAGREES')
    return {'comparable_source_bound_inventory':True,'valid_conversions':available,'names_exact':names['exact'],'names_contained_only':names['contained-only'],
        'names_missing':names['missing'],'names_unavailable':names['unavailable'],'literal_numeric_components':literal,'record_bound_numeric_components':bound,
        'components_unavailable':unavailable,'initial_scope_retained':sum(r.get('initial_scope_preserved') is True for r in durations),
        'dye_endpoint_edges':edges,'dye_legacy_projections':projections,'ambiguity_explicitly_retained':ambiguity['explicit_ambiguity_retained'],
        'ambiguity_states':dict(ambiguity),'primary_time_numeric':sum(finite(c['time_scope_comparison']['returned_primary_total_hours']) for c in rows),
        'known_numeric_with_primary_NA':sum(c['conversion_available'] and c['time_scope_comparison']['returned_primary_total_hours'] is None and
            all(r.get(literal_key) is True for r in c['core_duration_components']) for c in rows),
        'legacy_only':{'duration_states':summary.get('legacy_only',{}).get('v1_short_quote_duration_states',summary['core_duration_states']),
            'not_used_for_primary_literal_or_record_retention':True},'not_expert_gold':True}

def noncomparable_facts():
    return {'comparable_source_bound_inventory':False,'valid_conversions':None,'names_exact':None,'names_contained_only':None,'names_missing':None,'names_unavailable':None,
        'literal_numeric_components':None,'record_bound_numeric_components':None,'components_unavailable':None,'initial_scope_retained':None,
        'dye_endpoint_edges':None,'dye_legacy_projections':None,'ambiguity_explicitly_retained':None,'ambiguity_states':None,'primary_time_numeric':None,
        'known_numeric_with_primary_NA':None,'reason':'Legacy model-only extraction lacks the same source-bound record schema; do not impute zero or treat numeric output as fact coverage.'}

def validate_terminal_fact_gate(completion,fact_summary,per_answer,fact_rows):
    require(completion.get('actual_observations',completion.get('planned_observations'))==5 and
        fact_summary.get('status')=='complete' and fact_summary.get('fixed_answers')==5,'V3_TERMINAL_FACT_GATE_NOT_PASSED')
    require(len(per_answer)==len(fact_rows)==5 and [r.get('anonymous_answer_id') for r in per_answer]==IDS and
        [r.get('anonymous_answer_id') for r in fact_rows]==IDS,'V3_TERMINAL_FIXED_FIVE_ROWS_REQUIRED')
    require(all(r.get('status') in ['success','failed'] for r in per_answer),'V3_NONTERMINAL_ROWS')

def load_stage(spec,inventory,source_cases,ledger):
    name,version,label=spec;folder=BASE/name;used=[]
    paths={k:folder/(k+'.json') for k in ['completion_summary','per_answer','cases','matrix','expected_contract','plan']}
    require(all(p.exists() for p in paths.values()),'STAGE_NOT_READY:'+name)
    data={k:read(p) for k,p in paths.items()};used+=list(paths.values());summary=data['completion_summary'];rows=data['per_answer'];cases=data['cases']['cases'];matrix=data['matrix']
    require(len(rows)==len(cases)==len(matrix)==5,'STAGE_NOT_FIXED_FIVE:'+name)
    require([c['anonymous_answer_id'] for c in cases]==IDS and [r['anonymous_answer_id'] for r in rows]==IDS,'STAGE_ORDER_CHANGED:'+name)
    require(all(r['status'] in ['success','failed'] for r in rows),'NONTERMINAL_STAGE:'+name)
    successes=sum(r['status']=='success' for r in rows);counts=numeric_counts(rows,version is not None)
    require(successes==summary.get('technical_successes',summary.get('successes')),'TECH_COUNT_MISMATCH:'+name)
    if version:require(counts==summary['per_component_numeric'],'NUMERIC_COUNT_MISMATCH:'+name)
    complete=sum(all(finite(r.get('component_gated_proposals' if version else 'original_numeric_proposals',{}).get(m)) for m in METRICS) and r['status']=='success' for r in rows)
    require(complete==summary.get('complete_numeric_after_component_gates',summary.get('complete_numeric')),'COMPLETE_NUMERIC_COUNT_MISMATCH')
    verify_bindings(summary.get('bound_observations',[]),used)
    per_case=[];requests=[]
    for case,row in zip(cases,rows):
        aid=case['anonymous_answer_id'];original=source_cases[aid]
        require(all(case[k]==original[k] for k in ['case_id','question_id','specific_question','model_response','references']),'FULL_SOURCE_CHANGED:'+name+':'+aid)
        cell=next(c for c in matrix if c['anonymous_answer_id']==aid);tid=cell['planned_trial_id']
        require(row['trial_id']==tid and digest(cell['identity'])==tid,'TRIAL_IDENTITY_MISMATCH')
        tp=folder/'run/trials'/f'{tid}.json';rp=folder/'run/attempts'/f'{tid}_1/request_receipt.json';trial=read(tp);receipt=read(rp);used += [tp,rp]
        require(trial['identity']==cell['identity'] and trial['status']==row['status'] and trial['attempt']==1,'ACTUAL_TRIAL_NOT_BOUND')
        require(receipt==ledger.get(receipt['request_id']) and receipt['trial_id']==tid and receipt['attempt']==1,'RECEIPT_NOT_IN_REAL_LEDGER')
        require(receipt['package_request_index']==row['request_index'],'REQUEST_INDEX_MISMATCH');requests.append(receipt['package_request_index'])
        per_case.append({'anonymous_answer_id':aid,'question_id':case['question_id'],'source_answer_sha256':rawsha(case['model_response']),
            'source_question_sha256':rawsha(case['specific_question']),'trial_id':tid,'technical_status':row['status'],'failure_stage':row.get('failure_stage'),
            'numeric_available':{m:finite(row.get('component_gated_proposals' if version else 'original_numeric_proposals',{}).get(m)) and row['status']=='success' for m in METRICS},
            'complete_numeric':row['status']=='success' and all(finite(row.get('component_gated_proposals' if version else 'original_numeric_proposals',{}).get(m)) for m in METRICS)})
    facts=noncomparable_facts();fact_rows=None
    if version:
        fd=folder/('independent_fact_audit_'+version);fs=read(fd/'summary.json');fact_rows=read(fd/'per_answer.json');used += [fd/'summary.json',fd/'per_answer.json']
        require(Path(fs['batch_out']).resolve()==folder.resolve(),'FACT_REVIEW_WRONG_BATCH')
        verify_bindings(fs['inputs'],used);facts=summarize_facts(version,fs,fact_rows)
        for current,fact in zip(per_case,fact_rows):
            require(current['trial_id']==fact['actual_trial']['trial_id'] and current['source_answer_sha256']==fact['source_answer_sha256'],'FACT_ROW_NOT_ACTUAL_SOURCE_TRIAL')
        if version=='v2':
            add=BASE/'grounded_v2_failure_diagnostics_v1/legacy_checker_addendum.json';a=read(add);used.append(add)
            require(a['successful_conversion_initial_components_literal_retained']==facts['literal_numeric_components'] and a['successful_conversion_initial_components_record_bound']==facts['record_bound_numeric_components'],'V2_LEGACY_ADDENDUM_DISAGREES')
            verify_bindings([a['formal_checker_summary']],used);facts['legacy_only']['clarification']=bind(add)
    raw_layer={'names_literal':None,'initial_components_literal':None,'comparable_across_all_versions':False,'status':'not_standardized_in_this_comparison'}
    if version=='v1':
        diagnostic=BASE/'grounded_failure_diagnostics_v1/summary_5of5.json';d=read(diagnostic);used.append(diagnostic)
        require(d['status']=='complete' and d['completed_trials']==5,'V1_RAW_DIAGNOSTIC_NOT_COMPLETE')
        verify_bindings(d['failure_traces'],used);traces=[read(entry['path']) for entry in d['failure_traces']]
        require([t['anonymous_answer_id'] for t in traces]==IDS,'V1_RAW_IDS_CHANGED')
        require(all(t['trial_id']==r['trial_id'] for t,r in zip(traces,rows)),'V1_RAW_DIAGNOSTIC_TRIAL_MISMATCH')
        raw_layer={'names_literal':sum(n['status']=='exact' for t in traces for n in t['remaining_field_diagnostics']['raw_names_literal_inventory_diagnostic']),
            'initial_components_literal':sum(t['duration_field_diagnostics']['literal_source_numeric_core_components_retained'] for t in traces),
            'comparable_across_all_versions':False,'status':'independent_raw_diagnostic_not_a_valid_conversion','source':bind(diagnostic)}
    if version is None:
        audit=folder/'independent_review.json';a=read(audit);used.append(audit);verify_bindings(a['source_bindings'],used)
        raw_layer.update(status='legacy_extraction_review_no_same_record_schema',reasoning_value_conflicts=a['direct_numeric_reasoning_conflicts'],
            matches_initial_core_sum=a['matches_declared_initial_core_time_sum'],source=bind(audit))
    semantic_addenda=[]
    if version=='v3':
        methodological=BASE/'grounded_v3_failure_diagnostics_v1/methodological_addendum_v1/addendum.json'
        require(methodological.exists(),'V3_INTRINSIC_METHOD_ADDENDUM_REQUIRED')
        md=read(methodological);require(md['status']=='complete_read_only_methodological_addendum' and md['new_model_calls']==0,'V3_METHOD_ADDENDUM_NOT_READY')
        verify_bindings(md['inputs'],used);used.append(methodological)
        # Independent read-only diagnoses supplement, but never rewrite, the
        # frozen checker. An exact source span can still be a non-atomic name.
        for aid in IDS:
            diagnostic=BASE/'grounded_v3_failure_diagnostics_v1'/f'{aid}_trace.json'
            if not diagnostic.exists():continue
            d=read(diagnostic);row=next(r for r in rows if r['anonymous_answer_id']==aid)
            require(d['anonymous_answer_id']==aid and d['trial_id']==row['trial_id'],'V3_SEMANTIC_ADDENDUM_WRONG_TRIAL')
            diagnostic_calls=d.get('new_model_requests',d.get('verification',{}).get('new_model_requests'))
            require(diagnostic_calls==0,'V3_ADDENDUM_NOT_READ_ONLY')
            verify_bindings(d.get('inputs',[]),used);used.append(diagnostic)
            semantic_addenda.append({'anonymous_answer_id':aid,'trial_id':row['trial_id'],'source':bind(diagnostic),
                'role':'Independent semantic-input diagnosis; does not change frozen checker or numeric outputs.'})
    return {'stage':name,'label_zh':label,'backend_version':version,'planned_cases':5,'technical_successes':successes,'technical_failures':5-successes,
        'complete_numeric':complete,'component_numeric':counts,'facts':facts,'raw_layer':raw_layer,'request_indices':requests,
        'semantic_addenda':semantic_addenda,
        'new_requests_actual':len(requests),'per_case':per_case,'contract':data['expected_contract'],'inputs':[bind(p) for p in dict.fromkeys(used)]}

def required_v3_ready():
    p=BASE/'grounded_development_v3';need=[p/n for n in ['completion_summary.json','per_answer.json','independent_fact_audit_v3/summary.json','independent_fact_audit_v3/per_answer.json']]
    missing=[str(x) for x in need if not x.exists()]
    require(not missing,'FINAL_REPORT_REQUIRES_COMPLETE_V3_INDEPENDENT_FACT_REVIEW:'+','.join(missing))
    validate_terminal_fact_gate(read(need[0]),read(need[2]),read(need[1]),read(need[3]))

def assemble(include_v3):
    require(sha(INVENTORY)==INVENTORY_SHA,'FROZEN_INVENTORY_CHANGED');inventory=read(INVENTORY)
    source=inventory['source_cases'];require(sha(source['path'])==source['sha256'],'FIXED_SOURCE_CASES_CHANGED')
    originals={c['anonymous_answer_id']:c for c in read(source['path'])['cases']}
    ledger={r['request_id']:r for r in [json.loads(line) for line in LEDGER.read_text(encoding='utf8').splitlines() if line.strip()]}
    if include_v3:required_v3_ready()
    stages=[load_stage(s,inventory,originals,ledger) for s in (STAGES if include_v3 else STAGES[:3])]
    baseline=stages[0]['contract']
    for stage in stages[1:]:
        require(all(stage['contract'][k]==baseline[k] for k in ['files','demands','scoring_version','source_registry_sha256']),'ORIGINAL_SCIENCE_CONTRACT_CHANGED')
        left=stage['contract']['models'][0];right=baseline['models'][0]
        require(left['name']==right['name'] and {k:v for k,v in left['settings'].items() if k!='format'}=={k:v for k,v in right['settings'].items() if k!='format'},'MODEL_SETTINGS_CHANGED_BEYOND_DECLARED_DECODER')
    inputs=[bind(INVENTORY),bind(source['path'])]
    for stage in stages:inputs+=stage.pop('inputs');stage.pop('contract')
    indexed={x['path']:x for x in inputs}
    return stages,list(indexed.values())

def render(stages,inputs):
    require(len(stages)==4,'FINAL_REPORT_REQUIRES_FOUR_COMPLETED_STAGES')
    final=OUT/'final';require(not final.exists(),'FINAL_ALREADY_EXISTS_USE_NEW_REPORT_VERSION');final.mkdir(parents=True)
    stage_rows=[];metric_rows=[]
    for s in stages:
        f=s['facts'];stage_rows.append({'stage':s['stage'],'cases':5,'technical_successes':s['technical_successes'],'technical_failures':s['technical_failures'],
            'complete_numeric':s['complete_numeric'],'structurally_accepted_source_conversions':f['valid_conversions'],'names_exact_of_16':f['names_exact'],
            'names_unavailable_of_16':f['names_unavailable'],'literal_components_of_31':f['literal_numeric_components'],'record_bound_components_of_31':f['record_bound_numeric_components'],
            'components_unavailable_of_31':f['components_unavailable'],'dye_edges_of_3':f['dye_endpoint_edges'],'dye_projection_of_3':f['dye_legacy_projections'],
            'explicit_ambiguity_of_2':f['ambiguity_explicitly_retained'],'source_comparable':f['comparable_source_bound_inventory']})
        metric_rows += [{'stage':s['stage'],'metric':m,'finite_n':s['component_numeric'][m],'fixed_denominator':5,'accuracy_claimed':False} for m in METRICS]
    result={'status':'complete_development_stage_description_not_scientific_validation','fixed_answers':5,'independent_answers':5,'stages':stages,
        'fixed_inventory_denominators':{'names':16,'initial_time_components':31,'dye_pairs':3,'ambiguity_groups':2},
        'new_analysis_calls':0,'expert_labels_created':0,'comparison_is_single_factor':False,'confirmation_set_used':False,'original_human_holdout_science_used':False,
        'inputs':inputs,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]}
    save(final/'comparison.json',result);csvsave(final/'stage_summary.csv',stage_rows);csvsave(final/'component_numeric.csv',metric_rows)
    lines=['# 优化开发阶段：同五份存档答案的真实版本对照','',
        '各版本使用同一组已暴露开发答案、同一27B模型和原评分函数。提示、输出结构、投影策略与门控存在多项变化，属于连续开发版本比较，不能解释为单因素因果试验，也不是独立任务或来源的泛化验证。','',
        '| 版本 | 技术成功/5 | 完整数值/5 | 通过结构/跨度门控的转换/5 | 名称精确/不可审（各/16） | 字面时间/31 | 记录绑定/不可审时间（各/31） | 染料关系端点/投影（各/3） | 明确歧义/2 |',
        '|---|---:|---:|---:|---:|---:|---:|---|---:|']
    for s in stages:
        f=s['facts'];lines.append(f"| {s['label_zh']} | {s['technical_successes']}/5 | {s['complete_numeric']}/5 | {ratio(f['valid_conversions'],5)} | {ratio(f['names_exact'],16)} / {ratio(f['names_unavailable'],16)} | {ratio(f['literal_numeric_components'],31)} | {ratio(f['record_bound_numeric_components'],31)} / {ratio(f['components_unavailable'],31)} | {ratio(f['dye_endpoint_edges'],3)} / {ratio(f['dye_legacy_projections'],3)} | {ratio(f['ambiguity_explicitly_retained'],2)} |")
    lines += ['','分项数值覆盖的分母均为原五份答案；已知零计为数值，NA 和失败不补零。这里的“数值可用”仅表示返回或程序计算结果存在，**不代表来源输入有效、源文忠实或科学正确**。整行字段误当原子名称时，即使旧函数产生 0，也不能称为有来源支持的已知零。','',
        '| 版本 | '+' | '.join(METRICS)+' |','|---|'+'---:|'*len(METRICS)]
    for s in stages:lines.append('| '+s['label_zh']+' | '+' | '.join(f"{s['component_numeric'][m]}/5" for m in METRICS)+' |')
    lines += ['','原始提及与有效转换分开：','',
        '| 版本 | 原始层名称 | 原始层初始时间 | 口径 |','|---|---:|---:|---|']
    for s in stages:
        raw=s['raw_layer'];lines.append(f"| {s['label_zh']} | {ratio(raw['names_literal'],16)} | {ratio(raw['initial_components_literal'],31)} | {raw['status']} |")
    lines += ['','原始层未做同口径完整审计的单元显示不可比较，不补 0。v1 独立 raw 检查中的字面提及不使失败转换重新有效，也不成为原 EGES 的修正输入。模型对照没有同样的 source-span 记录结构，其16/31/3/2覆盖不能与 grounded 版本直接相减。','',
        'v2 的 18 个初始时间数值同时通过字面与记录绑定检查；旧 summary 的 `span_present_numeric_mismatch` 是沿用短动作 quote 包含条件的历史诊断，不能改述为18个数值丢失。旧 JSON 不改，解释见[版本化补充](../../grounded_v2_failure_diagnostics_v1/legacy_checker_addendum.md)。','',
        'v3 的 `independent_literal_cue_concerns=0` 只表示有限字面线索检查未报警，不确认原子名称或原生信号的语义。A02 的整行名称错误可同时通过这项检查并产生数学上的标签零分；该零值保留在数值表内，但不是已经证实的来源有效零分。见[独立方法学补充](../../grounded_v3_failure_diagnostics_v1/methodological_addendum_v1/README.md)。','',
        '初始时间组件留存与最终无条件总时是不同问题：后续条件操作、未知阶段/范围或缺失组件仍可使总时为 NA。名称包含不等于原子名称精确身份；三组染料关系的端点出现、关系可投影与专家认定也分别记录。原生信号 typed identity 不加入三组染料关系分母。','',
        '没有新增专家真值，原人工5+15留出与确认集未用于本表。每个阶段只有五个基础答案；子字段和派生指标有依赖，不能当成独立样本量。技术通过率或自动事实覆盖的变化，不能证明评价器准确性提高。','',
        '[机器可读对照与来源哈希](comparison.json) · [阶段表 CSV](stage_summary.csv) · [分项 CSV](component_numeric.csv)','']
    if stages[-1]['semantic_addenda']:
        lines += ['独立语义输入诊断与冻结 checker 并列保存；这些诊断不会把技术成功或数学重放改称事实忠实。','']
        for item in stages[-1]['semantic_addenda']:
            aid=item['anonymous_answer_id'];lines.append(f'- [{aid} 的真实输入/返回诊断](../../grounded_v3_failure_diagnostics_v1/{aid}_trace.json)')
        lines.append('')
    (final/'RESULTS_zh.md').write_text('\n'.join(lines),encoding='utf8')
    g1,g2,g3=stages[1:]
    english=(f"On the same five exposed development answers, the source-bound v1, v2 and v3 implementations completed {g1['technical_successes']}/5, {g2['technical_successes']}/5 and {g3['technical_successes']}/5 technically, respectively. "
        f"Among conversions passing structural and source-span gates, exact inventory-name retention was {g1['facts']['names_exact']}/16, {g2['facts']['names_exact']}/16 and {g3['facts']['names_exact']}/16; verified source-record duration retention was {g1['facts']['record_bound_numeric_components']}/31, {g2['facts']['record_bound_numeric_components']}/31 and {g3['facts']['record_bound_numeric_components']}/31. "
        "Unavailable conversions remain unavailable. These are iterative development comparisons involving multiple changes, not a single-factor intervention or an independent generalization test. Numeric availability, successful arithmetic replay and exact source strings do not establish faithful semantic extraction or scientific correctness. The fixed inventory is model-reviewed source evidence rather than expert gold, and the legacy model-only output is not directly comparable under the same source-bound schema.")
    (final/'paper_boundary_en.md').write_text(english+'\n',encoding='utf8')
    print(json.dumps({'status':result['status'],'stages':4,'output':str(final),'new_analysis_calls':0}))

def preflight():
    stages,inputs=assemble(False);ready=True;reason=None
    try:required_v3_ready()
    except (ValueError,KeyError) as exc:ready=False;reason=str(exc)
    save(OUT/'preparation_verification.json',{'status':'earlier_inputs_verified_not_final_report','earlier_stages':3,'earlier_actual_trials':15,
        'v3_final_gate_ready':ready,'v3_gate_reason':reason,'inputs':inputs,'source_hashes_verified':True,'same_five_fulltexts':True,
        'v2_literal_and_record_bound_retention':{'literal':stages[2]['facts']['literal_numeric_components'],'record_bound':stages[2]['facts']['record_bound_numeric_components']},
        'new_model_calls':0,'final_report_created':False,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]})
    print(json.dumps({'status':'earlier_inputs_verified_not_final_report','earlier_actual_trials':15,'v3_final_gate_ready':ready,'new_model_calls':0}))

def self_check():
    tests=[]
    def check(name,value):require(value,'SYNTHETIC_CHECK:'+name);tests.append({'name':name,'pass':True,'synthetic_only':True})
    rows=[{'status':'success','component_gated_proposals':{m:0 for m in METRICS}}, {'status':'failed','component_gated_proposals':{m:2 for m in METRICS}},
        {'status':'success','component_gated_proposals':{m:None for m in METRICS}}]
    check('known_zero_counted_failure_and_NA_not_counted',all(v==1 for v in numeric_counts(rows,True).values()))
    check('bool_not_a_numeric_score',not finite(True));check('NaN_not_a_numeric_score',not finite(float('nan')))
    check('noncomparable_model_output_not_imputed_zero',all(noncomparable_facts()[k] is None for k in ['names_exact','literal_numeric_components','dye_endpoint_edges']))
    fictional_rows=[{'anonymous_answer_id':aid,'status':'success'} for aid in IDS]
    validate_terminal_fact_gate({'actual_observations':5},{'status':'complete','fixed_answers':5},fictional_rows,fictional_rows)
    check('complete_synthetic_terminal_gate_passes',True)
    for label,summary,rows_for_gate in [('pending_fact_review',{'status':'pending','fixed_answers':5},fictional_rows),
                                      ('four_answer_review',{'status':'complete','fixed_answers':5},fictional_rows[:4])]:
        try:validate_terminal_fact_gate({'actual_observations':5},summary,rows_for_gate,fictional_rows)
        except ValueError:check(label+'_rejected',True)
        else:raise ValueError('SYNTHETIC_INCOMPLETE_GATE_ACCEPTED:'+label)
    # Independent count fixture: old containment status is deliberately wrong
    # for the new representation; explicit literal and record flags control it.
    duration={'status':'span_present_numeric_mismatch','literal_source_numeric_value_retained':True,'v2_record_bound_numeric_retained':True,'initial_scope_preserved':True}
    check('legacy_containment_not_numeric_omission',duration['literal_source_numeric_value_retained'] and duration['v2_record_bound_numeric_retained'] and duration['status']=='span_present_numeric_mismatch')
    check('conditional_NA_can_coexist_with_known_components',all(x['literal_source_numeric_value_retained'] for x in [duration]*6) and not finite(None))
    save(OUT/'software_checks.json',{'status':'pass_for_synthetic_statistics_only','tests':tests,'new_model_calls':0,'script_sha256':sha(__file__),'actual_command':[sys.executable,*sys.argv]})
    print(json.dumps({'status':'pass_for_synthetic_statistics_only','synthetic_checks':len(tests),'new_model_calls':0}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['preflight','self-check','finalize']);args=parser.parse_args()
    if args.action=='preflight':preflight()
    elif args.action=='self-check':self_check()
    else:
        stages,inputs=assemble(True);render(stages,inputs)
