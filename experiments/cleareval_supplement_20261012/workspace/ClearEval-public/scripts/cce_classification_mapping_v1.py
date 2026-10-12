"""Source-backed construct mapping from existing public labels and templates.

No model calls, automatic relabeling, protected packets, or scoring changes.
MCQ item stems/answers are not used; exposed QAR stems are an explicit six-ID list.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv, hashlib, json, sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'optimizer_20261010/classification_mapping_v1'
PACK=ROOT.parent/'ClearEval_Codex_Experiments_v1_20261008'
INPUTS={}
EXPOSED={1,2,21,22,23,248}
AXES=['category','knowledge_point','specific']

def rawsha(x):return hashlib.sha256(x.encode('utf8')).hexdigest()
def read(path):
    path=Path(path);raw=path.read_bytes()
    INPUTS[str(path.resolve())]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    return raw
def load(path):return json.loads(read(path).decode('utf-8-sig'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def table(name,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)
def ptr(k):return str(k).replace('~','~0').replace('/','~1')
def span(text,quote):
    start=text.index(quote);assert text[start:start+len(quote)]==quote
    return {'quote':quote,'start':start,'end':start+len(quote)}

# Interpretation of existing design labels; not new item-level expert annotation.
SPEC={
 'Reagent Functions & Applications':('reagent_function_application','试剂功能/应用选项','reagent function, use or constituent role',['Reagent Function & Application','Mechanism of Action','Reagent Name']),
 'Method Characteristics & Applications':('method_property_application','方法性质/适用陈述选项','method properties and stated applications',['Method Feature','Method Feature[Fluorescence_Compatibility]','Method Feature[Time_Consumption]','Method Feature[Tissue_Deformation]','Method Advantages & Limitations','Cross-Method Comparison','Improvements of Method']),
 'Method Names & Categories':('method_identity_category','方法名称/类别选项','method name or class',['Clearing Method Name','Method Classification']),
 'Marker Features & Targets':('marker_property_target','标记物性质/靶点选项','marker properties or marker/target association',['Marker Feature','specific labeling object','Dyes Name','Target Name']),
 'Protocol Steps & Parameters':('protocol_information','流程信息/步骤参数选项','source-described operation, order or parameter',['Method Detail Extraction','Specific Steps Identification']),
 'Method Selection':('method_selection','方法选择选项','method choice under stated task constraints',['Protocol Selection','Cross-Method Comparison']),
 'Reagent Names & Abbreviations':('reagent_identity','试剂名称/缩写选项','reagent name and abbreviation',['Reagent Common Name','Reagent Name']),
 'Tissue Features & Labeling Sites':('tissue_property_target','组织性质/标记位点选项','tissue properties or tissue/target association',['Tissue Name','Target Name','Tissue Types and Properties','specific labeling object']),
 'Full-Process Design':('design_option_selection','流程设计选项选择','provided design or route-combination option',['Experimental Design']),
 'Tissue & Marker Names':('tissue_marker_identity','组织/标记实体选项','tissue or marker identity',['Tissue Name','Dyes Name','Target Name']),
 'Result Analysis & Troubleshooting':('failure_scenario_option_selection','故障情境解释/修订选项选择','provided interpretation or corrective option',['Result Analysis and Optimization'])}
CATEGORIES={
 'Named Entity Recognition':('select_source_information','在给定信息中辨识并选择'),
 'Domain Knowledge Evaluation':('select_domain_statement','判断并选择领域知识陈述'),
 'Task Scenario Questions':('select_scenario_appropriate_option','根据给定情境选择选项')}
TEMPLATE_BEHAVIOR={
 'Clearing Method Name':('source_entity_recognition','method name'),
 'Reagent Name':('source_entity_recognition','reagent identity'),
 'Tissue Name':('source_entity_recognition','tissue identity'),
 'Dyes Name':('source_entity_recognition','marker identity'),
 'Target Name':('source_entity_recognition','target identity'),
 'Method Detail Extraction':('source_protocol_information_retrieval','protocol parameter'),
 'Specific Steps Identification':('source_step_order_retrieval','operation order'),
 'Method Classification':('method_category_knowledge','method category'),
 'Method Feature':('method_property_knowledge','method chemistry/properties'),
 'Method Feature[Tissue_Deformation]':('method_property_knowledge','morphology retention property'),
 'Method Feature[Time_Consumption]':('method_property_knowledge','reported time property'),
 'Method Feature[Fluorescence_Compatibility]':('method_label_compatibility_judgment','method/label compatibility statement'),
 'Method Advantages & Limitations':('method_property_knowledge','method advantages/limitations'),
 'Cross-Method Comparison':('method_comparison','methods under stated requirement'),
 'Improvements of Method':('method_version_comparison','stated version difference'),
 'Reagent Function & Application':('reagent_function_knowledge','reagent function/application'),
 'Reagent Common Name':('reagent_identity_association','reagent name/abbreviation'),
 'Mechanism of Action':('reagent_mechanism_knowledge','mechanism statement'),
 'specific labeling object':('marker_target_association','marker/target association'),
 'Marker Feature':('marker_property_knowledge','marker properties'),
 'Tissue Types and Properties':('tissue_constraint_knowledge','tissue property/labeling challenge'),
 'Protocol Selection':('scenario_method_option_selection','method option under requirements'),
 'Experimental Design':('scenario_design_option_selection','provided design/label/route option'),
 'Result Analysis and Optimization':('failure_scenario_option_selection','provided causal explanation or revision option')}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    design=read(PACK/'EXPERIMENT_DESIGN.md').decode('utf8')
    read(BASE/'optimizer_20261010/r2_completion_audit_v1/audit.json')
    read(ROOT/'results/aggregate_mcq.py')
    mcq_path=ROOT/'dataset/MCQ/final/all_mcq_data.jsonl'
    basic_path=ROOT/'dataset/MCQ/basic_question/class_basic_question_all_in_one.json'
    taxonomy_path=ROOT/'dataset/MCQ/class_knowledge_point.json'
    taxonomy=load(taxonomy_path);base=load(basic_path)
    templates=[];unstructured=[]
    def collect(x,p=''):
        if isinstance(x,dict):
            if 'basic_question_id' in x:templates.append((p,x))
            else:
                for k,v in x.items():collect(v,p+'/'+ptr(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):collect(v,p+'/'+str(i))
        elif isinstance(x,str) and p.startswith('/0/'):
            unstructured.append({'source_pointer':p,'text_sha256':rawsha(x),'reason':'No basic_question_id or structured category in source; do not assign a category from prose.'})
    collect(base)
    tax_leaves=defaultdict(list)
    def leaves(x,p):
        if isinstance(x,dict):
            for k,v in x.items():
                if k!='note':leaves(v,p+'/'+ptr(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,str):tax_leaves[v].append(p+'/'+str(i))
                else:leaves(v,p+'/'+str(i))
    for i,x in enumerate(taxonomy):leaves(x,'/'+str(i))
    template_rows=[]
    for pointer,t in templates:
        k=t.get('knowledge_point');behavior,obj=TEMPLATE_BEHAVIOR.get(k,('unmapped','unmapped'))
        q=t.get('question','');assert isinstance(q,str) and q
        template_rows.append({'basic_question_id':t['basic_question_id'],'original_category':t.get('category'),
          'original_knowledge_point':k,'original_specific':t.get('specific'),
          'task_behavior':behavior,'evaluation_object':obj,'answer_form':'provided_option_choice',
          'mapping_status':'template_text_supported' if behavior!='unmapped' else 'unmapped',
          'source_path':str(basic_path),'source_pointer':pointer,'template_text_sha256':rawsha(q),
          'source_behavior_evidence':q,'exact_taxonomy_leaf_pointers':tax_leaves.get(k,[]),
          'template_to_final_item_lineage':'not_recoverable_from_final_metadata_no_basic_question_id',
          'closed_choice_not_open_generation_or_open_diagnosis':True,'expert_validation':False})
    assert len(template_rows)==45 and len({x['basic_question_id'] for x in template_rows})==45
    save('template_behavior_mapping.json',template_rows);table('template_behavior_mapping.csv',template_rows)

    # Parse each MCQ record only to project a strict metadata whitelist. Do not use stems/options/answers.
    projected=[];joint=defaultdict(list);observed_fields=Counter()
    for line,raw in enumerate(read(mcq_path).decode('utf-8-sig').splitlines(),1):
        if not raw.strip():continue
        obj=json.loads(raw);observed_fields.update(obj.keys())
        r={k:obj.get(k) for k in ['question_id',*AXES]}
        r.update(source_line=line,source_path=str(mcq_path),metadata_sha256=rawsha(json.dumps(r,ensure_ascii=False,sort_keys=True)))
        projected.append(r);joint[tuple(r[k] for k in AXES)].append(r)
    assert len(projected)==2588 and len({r['question_id'] for r in projected})==2588
    assert all(type(count) is int and 0<=count<=len(projected) for count in observed_fields.values())
    class_rows=[];label_counts=Counter()
    for i,(labels,rows) in enumerate(sorted(joint.items()),1):
        cat,k,spec=labels;rule=SPEC.get(spec);category_rule=CATEGORIES.get(cat)
        status='declared_label_mapping_not_item_stem_validated' if rule and category_rule else 'unmapped'
        candidates=[t for t in template_rows if rule and t['original_knowledge_point'] in rule[3]]
        # Exact category matches are shown first; no final-to-template join is claimed.
        candidates=sorted(candidates,key=lambda t:(t['original_category']!=cat,t['basic_question_id']))
        mapping_id=f'MCQ_CLASS_{i:02d}'
        row={'mapping_id':mapping_id,'question_type':'MCQ','category':cat,'knowledge_point':k,'specific':spec,
          'question_count':len(rows),'denominator':len(projected),'category_indicated_behavior':category_rule[0] if category_rule else 'unmapped',
          'task_behavior':rule[0] if rule else 'unmapped','behavior_zh':rule[1] if rule else '未映射',
          'evaluation_object':rule[2] if rule else 'unmapped','observed_score_object':'selected answer option vs existing key',
          'mapping_status':status,'template_support_ids':[t['basic_question_id'] for t in candidates],
          'template_support_is_semantic_design_support_not_item_lineage':True,
          'source_path':str(mcq_path),'source_lines':[r['source_line'] for r in rows],
          'source_question_ids':[r['question_id'] for r in rows],
          'sample_scale':'unmapped_no_structured_field','marker_condition':'unmapped_no_structured_field',
          'reference_coverage':'unmapped_no_item_reference_field','expert_validated_mapping':False}
        class_rows.append(row);label_counts[spec]+=len(rows)
        for r in rows:r['mapping_id']=mapping_id;r['mapping_status']=status
    save('mcq_classification_mapping.json',class_rows);table('mcq_classification_mapping.csv',class_rows)
    table('mcq_item_metadata.csv',sorted(projected,key=lambda r:r['source_line']))
    assert len(class_rows)==30 and sum(r['question_count'] for r in class_rows)==2588

    # Only the six already exposed development tasks. Never open the full QAR corpus or protected packets.
    case_paths=[BASE/'judges'/x/'cases.json' for x in ['local_alternative_development','local_alternative_q1_v1','local_alternative_q2_v1','local_alternative_q248_v1']]
    questions={};question_sources={}
    for p in case_paths:
        for i,c in enumerate(load(p)['cases']):
            qid=int(c['question_id']);assert qid in EXPOSED
            text=c['specific_question']
            if qid in questions:assert questions[qid]==text
            else:questions[qid]=text;question_sources[qid]={'source_path':str(p),'source_pointer':f'/cases/{i}/specific_question'}
    assert set(questions)==EXPOSED
    scored=load(BASE/'method_family_steps_v1/t070_per_answer.json')
    assert len(scored)==77 and {int(r['question_id']) for r in scored}==EXPOSED
    exposed=[]
    for qid in sorted(EXPOSED):
        text=questions[qid];rows=[r for r in scored if int(r['question_id'])==qid]
        assert all(r['question_sha256']==rawsha(text) for r in rows),'qid-only join forbidden'
        spans={'protocol_output':span(text,'请仅输出 protocol'),
               'requested_scope':span(text,'透明处理、RI 匹配和保存/成像前处理步骤')}
        if '3 mm' in text:scale='brain_tissue_block';spans['scale']=span(text,'3 mm')
        elif '全脑' in text:scale='whole_brain';spans['scale']=span(text,'全脑')
        elif '整脑' in text:scale='whole_brain';spans['scale']=span(text,'整脑')
        else:scale='unmapped'
        if 'tdTomato 内源示踪信号' in text:
            marker='specific_native_reporter_preservation_plus_structure';spans['label_requirement']=span(text,'tdTomato 内源示踪信号')
        elif '内源荧光' in text:
            marker='weak_endogenous_reporter_plus_structure';spans['label_requirement']=span(text,'内源荧光')
        else:
            marker='label_strategy_to_be_selected';spans['label_requirement']=span(text,'自行选择合适的荧光/标记策略')
        exposed.append({'question_id':qid,'original_question_type_source_container':'Q+AR archived open tasks',
          'original_category':'unmapped_not_present_in_exposed_case_metadata','task_behavior':'scope_delimited_protocol_generation',
          'secondary_behavior':'label_and_method_selection_under_task_constraints',
          'evaluation_object':'generated clearing/RI/storage/pre-imaging text, its parameters, consistency and evidence-grounded choices',
          'required_scope':'clearing/RI/storage/pre-imaging; not upstream labeling or full experimental execution',
          'mapping_status':'public_task_instruction_supported','sample_scale':scale,'marker_condition':marker,
          'source_question_sha256':rawsha(text),**question_sources[qid],'evidence_spans':spans,
          'archived_answers':len(rows),'candidate_reference_available_answers':sum(r['candidate_count']>0 for r in rows),
          'numeric_step_answers':sum(r['sr'] is not None for r in rows),
          'conditional_reference_ids':sorted({ref for r in rows for ref in r['candidate_reference_ids']}),
          'formal_eligible_answers':sum(bool(r['formal_eligible']) for r in rows),
          'scope_is_not_scientific_applicability_confirmation':True,'expert_validation':False})
    save('exposed_qar_mapping.json',exposed);table('exposed_qar_mapping.csv',exposed)

    # Reuse aggregate-only historical coverage. No QAR original question/answer file is opened.
    agg_path=BASE/'analysis_expanded_tasks_v4/dataset_coverage.csv'
    aggregated=list(csv.DictReader(read(agg_path).decode('utf-8-sig').splitlines()))
    for axis in AXES:
        actual=Counter(str(r[axis]) if r[axis] not in (None,'') else 'MISSING' for r in projected)
        previous={r['value']:int(r['count']) for r in aggregated if r['dataset']=='MCQ final' and r['field']==axis}
        assert dict(actual)==previous,'original_axis_counts_changed:'+axis
    qar_aggregate=[r for r in aggregated if r['dataset']=='QAR historical']
    save('qar_existing_aggregate_metadata.json',qar_aggregate)
    meta=load(BASE/'analysis_expanded_tasks_v4/dataset_coverage_metadata.json')
    qar_total=meta['qar_historical']['question_rows'];assert qar_total==253
    crossings=[]
    for fields in [('category','task_behavior'),('knowledge_point','evaluation_object'),('specific','task_behavior')]:
        counter=Counter()
        for r in class_rows:counter[tuple(r[k] for k in fields)]+=r['question_count']
        for values,n in sorted(counter.items()):crossings.append({'dataset':'MCQ final','unit':'question','axes':list(fields),'values':list(values),'count':n,'denominator':2588,'status':'original_label_design_mapping'})
    counter=Counter((r['task_behavior'],r['sample_scale'],r['marker_condition']) for r in exposed)
    for values,n in sorted(counter.items()):crossings.append({'dataset':'exposed QAR','unit':'distinct_question','axes':['behavior','sample_scale','marker_requirement'],'values':list(values),'count':n,'denominator':6,'status':'six_exposed_stems_only'})
    for r in exposed:crossings.append({'dataset':'exposed QAR archived answers','unit':'answer','axes':['question_id','reference_availability'],'values':[r['question_id'],'conditional_candidate_exists'],
      'count':r['candidate_reference_available_answers'],'denominator':r['archived_answers'],'status':'conditional_metadata_not_formal_reference'})
    table('cross_distributions.csv',crossings);save('cross_distributions.json',crossings)
    unknown=[
      {'scope':'MCQ final','item':'exact final-item to basic-template lineage','count':2588,'denominator':2588,'reason':'Final schema has no basic_question_id; support templates are design evidence, not recovered item lineage.'},
      {'scope':'MCQ final','item':'independently reviewed item-level task behavior','count':2588,'denominator':2588,'reason':'No item-stem review or new expert labels; mappings use existing classification axes.'},
      {'scope':'MCQ final','item':'sample-scale metadata','count':2588,'denominator':2588,'reason':'No structured scale field in final metadata; no inference from stems.'},
      {'scope':'MCQ final','item':'marker-condition metadata','count':2588,'denominator':2588,'reason':'No structured marker condition field; knowledge topic is not a marker requirement.'},
      {'scope':'MCQ final','item':'item reference-coverage metadata','count':2588,'denominator':2588,'reason':'No explicit per-item complete protocol reference field in inspected final schema.'},
      {'scope':'MCQ base','item':'unstructured template entries','count':len(unstructured),'denominator':45+len(unstructured),'reason':'Kept separate from 45 structured-ID templates; no prose-only reclassification.'},
      {'scope':'QAR historical','item':'task behavior beyond six exposed IDs','count':qar_total-len(exposed),'denominator':qar_total,'reason':'Only existing aggregate metadata used for remaining tasks; protected and unexposed scientific contents not inspected.'},
      {'scope':'QAR historical','item':'scale/marker/reference joint coverage outside exposed six','count':qar_total-len(exposed),'denominator':qar_total,'reason':'Aggregate marginals cannot recover joint distributions or record-level joins.'},
      {'scope':'all','item':'expert-confirmed construct mapping','count':0,'denominator':None,'reason':'This artifact documents source-backed interpretation, not new expert gold.'}]
    save('unmapped_items.json',unknown);table('unmapped_items.csv',unknown)
    save('unstructured_template_metadata.json',unstructured)
    clauses=[{'line':i+1,'text':line} for i,line in enumerate(design.splitlines()) if any(s in line for s in ['原分类—任务行为—评价对象','程序输出题型','不同轴不自动','完整性对应必要操作'])]
    save('mapping_policy.json',{'version':'classification_mapping_v1','status':'source_supported_interpretation_for_author_review','original_design_clauses':clauses,
      'axes_not_reclassified':AXES,'axes_not_assumed_hierarchy':True,'item_stems_or_answers_used_for_MCQ':False,
      'MCQ_specific_rules':{k:{'behavior':v[0],'label_zh':v[1],'object':v[2],'supporting_template_knowledge_points':v[3]} for k,v in SPEC.items()},
      'MCQ_category_rules':CATEGORIES,'template_rules':TEMPLATE_BEHAVIOR,'exposed_qar_ids':sorted(EXPOSED),
      'closed_choice_is_not_open_protocol_generation':True,'closed_fault_option_is_not_open_root_cause_diagnosis':True,
      'no_upstream_protocol_restoration':True,'taxonomy_versions_kept_separate':True,'new_expert_labels':0})
    summary={'status':'completed_source_traced_mapping_with_explicit_unknowns','created_utc':datetime.now(timezone.utc).isoformat(),
      'actual_command':[sys.executable,*sys.argv],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'MCQ':{'items':2588,'original_category_count':len({r['category'] for r in projected}),
        'original_knowledge_point_count':len({r['knowledge_point'] for r in projected}),'specific_count':len(SPEC),
        'observed_joint_label_combinations':len(class_rows),'label_design_mapped_items':sum(r['question_count'] for r in class_rows if r['mapping_status']!='unmapped'),
        'expert_validated_behavior_items':0,'structured_base_templates':len(template_rows),'template_text_supported':sum(r['mapping_status']!='unmapped' for r in template_rows),
        'unstructured_templates_separate':len(unstructured),'final_item_template_exact_links':0,
        'Full_Process_Design_closed_choice_items':label_counts['Full-Process Design'],
        'Result_Analysis_Troubleshooting_closed_choice_items':label_counts['Result Analysis & Troubleshooting'],
        'structured_fields_observed':dict(observed_fields)},
      'QAR':{'historical_aggregate_question_denominator':qar_total,'exposed_stem_mapped_questions':len(exposed),
        'exposed_ids':sorted(EXPOSED),'not_stem_mapped_questions':qar_total-len(exposed),'existing_answer_rows_in_exposed_scope':len(scored),
        'conditional_numeric_step_answers':sum(r['numeric_step_answers'] for r in exposed),
        'formal_eligible_answers':sum(r['formal_eligible_answers'] for r in exposed),
        'whole_QAR_source_text_opened':False,'scope':'Only public six; no new generalization to remaining247'},
      'new_model_calls':0,'new_expert_labels':0,'sealed_or_human_holdout_content_read':False,
      'frozen_scoring_or_design_modified':False,'inputs':INPUTS,
      'validation':{'all_MCQ_ids_unique':True,'all_original_counts_reconciled':True,'all_45_template_ids_unique':True,
        'six_question_raw_hashes_equal_all_corresponding77_score_metadata':True,'all_exposed_source_offsets_roundtrip':True,
        'joint_distributions_not_derived_from_unpaired_marginals':True}}
    assert summary['MCQ']['label_design_mapped_items']==2588
    assert summary['QAR']['conditional_numeric_step_answers']==66
    save('summary.json',summary)
    outputs=['mapping_policy.json','mcq_classification_mapping.json','mcq_classification_mapping.csv',
        'mcq_item_metadata.csv','template_behavior_mapping.json','template_behavior_mapping.csv',
        'exposed_qar_mapping.json','exposed_qar_mapping.csv','cross_distributions.json','cross_distributions.csv',
        'unmapped_items.json','unmapped_items.csv','unstructured_template_metadata.json','qar_existing_aggregate_metadata.json','summary.json']
    save('verification.json',{'status':'pass_metadata_and_source_checks_not_expert_validation',
        'actual_command':[sys.executable,*sys.argv],'new_model_calls':0,
        'checks':summary['validation'],
        'MCQ_three_axes_equal_preexisting_coverage_counts':True,
        'MCQ_field_presence_only_integer_counts':all(type(n) is int for n in observed_fields.values()),
        'no_item_question_options_answers_in_projected_MCQ_outputs':True,
        'all_inputs_outside_protected_packet_namespaces':all(not any(s in p.lower().replace('\\','/') for s in ['sealed_confirmation','identity_key','/human_review/']) for p in INPUTS),
        'output_bindings':[{'path':str(OUT/name),'sha256':hashlib.sha256((OUT/name).read_bytes()).hexdigest()} for name in outputs]})
    md=['# 原分类、任务行为与评价对象映射','',
      '已基于原分类字段和基础题模板完成独立映射：**2,588道MCQ、30个实际分类组合、45份结构化基础模板**。另保留30条无结构ID模板。没有调用模型、读取封存确认或专家留出正文，也没有修改评分或原分类。','',
      '这里的“映射”是来源可追溯的设计解释，不是逐题专家标签。最终MCQ没有basic_question_id，故不伪造它与模板的逐题连接；category、knowledge_point、specific保持三个独立轴。','',
      '| 原specific | 实际题数 | 对应行为/评价对象 |','|---|---:|---|']
    for key,rule in SPEC.items():md.append(f'| {key} | {label_counts[key]} | {rule[1]}；{rule[2]} |')
    md += ['', '**71道 Full-Process Design 是设计选项选择，不能计为开放生成完整protocol。8道 Result Analysis & Troubleshooting 是解释/修订选项选择，不能据此声称开放根因诊断能力。** 原模板确有这些行为的直接文字，但题目标签与模板的语义支持不同于逐题血缘连接。','',
      '公开开发QAR的6个题干均明确要求选择标记/方法并输出限定范围的protocol。范围是透明处理、RI、保存/成像前处理，不能升级为完整上游实验设计。6个题干哈希已与77条既有结果逐行绑定；其中66条有条件步骤数值、正式资格0。三个完整脑与三个脑组织块任务分别列尺度/标记要求及来源span。','',
      '其余247个QAR仅复用原253题的聚合组织字段，不读原题/答案、不补行为标签。MCQ缺结构化尺度、标记条件和完整参考字段，三项各保留2,588条unmapped；已有聚合边际无法重建这些交叉分布。该缺失不表示题干一定未提及，而是本次可合法复用的结构化证据不足。','',
      '原评分观察对象保持：MCQ为所选答案与原键的吻合；生成任务的完整性、Correctness与EGES分别对应所要求操作/参数表达、原逻辑/冲突判项、证据支持的选择适配。步骤匹配和数值可计算不能直接证明实验有效或覆盖全部领域能力。','',
      '## 文件与复现','',
      '- [30个分类组合映射](mcq_classification_mapping.csv)及[逐题纯元数据](mcq_item_metadata.csv)','- [45个模板证据](template_behavior_mapping.json)，含原JSON位置、文本SHA与原taxonomy叶节点链接；无强制跨版本合并','- [公开6题映射与逐字段span](exposed_qar_mapping.json)','- [可用交叉分布](cross_distributions.csv)及[未映射项](unmapped_items.csv)','- [规则与原设计行号](mapping_policy.json)及[运行摘要/全部输入哈希](summary.json)','',
      '```powershell',f"& '{sys.executable}' scripts/cce_classification_mapping_v1.py",'```','',
      '后续作者可以核对或补充候选映射；在取得原样本级元数据或真实专家核查前，不将缺失条件、模板支持或统计覆盖写成金标能力验证。','']
    (OUT/'README.md').write_text('\n'.join(md),encoding='utf8')
    print(json.dumps({'status':summary['status'],'MCQ_items':2588,'joint_combinations':30,'templates':45,
       'unstructured_templates':len(unstructured),'exposed_QAR':6,'unmapped_QAR':247,
       'summary_sha256':hashlib.sha256((OUT/'summary.json').read_bytes()).hexdigest(),'new_model_calls':0},ensure_ascii=True))

if __name__=='__main__':main()
