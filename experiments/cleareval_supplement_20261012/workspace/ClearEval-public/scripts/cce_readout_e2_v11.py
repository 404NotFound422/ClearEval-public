"""Read terminal E2 summaries and the E2_09 archived conversions; no rescoring."""
import csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OLD=BASE/'optimizer_20261010/grounded_controls_v1'
NEW=BASE/'optimizer_round2_20261010/grounded_controls_v11'
OUT=BASE/'optimizer_round2_20261010/E2_v11_readout_v1'
inputs=[]
def bind(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def read(p):inputs.append(bind(p));return json.loads(p.read_bytes().decode('utf-8-sig'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def small(version,directory):
    summary=read(directory/'completion_summary.json');rows=read(directory/'per_answer.json')
    row=next(x for x in rows if x.get('control_id',x.get('anonymous_answer_id'))=='E2_09')
    matrix=read(directory/'matrix.json');cell=next(x for x in matrix if x['planned_trial_id']==row['trial_id'])
    attempt=directory/'run/attempts'/(row['trial_id']+'_1')
    cv=read(attempt/'source_bound_conversion.json');raw=read(attempt/'raw_source_bound_content.txt')['grounded_extraction']
    doc=read(directory/'source_documents/E2_09.json');projection=cv['legacy_projection'];resolved=cv['source_audit']['resolved']
    if version=='v7':metrics=row['candidate_raw_and_derived'];replay=row['original_EGES_replay'];notes=row['component_gate_notes']
    else:
        numeric=read(attempt/'numeric_result.json');metrics=row['metrics'];replay=numeric['original_EGES_replay'];notes=numeric['component_gate_notes']
    return {'version':version,'trial_id':row['trial_id'],'case_id':row['case_id'],'input_sha256':cell['identity']['input_sha256'],
        'answer_sha256':doc['answer_sha256'],'technical_status':row['status'],
        'complete_numeric':row.get('complete_numeric',row.get('complete_numeric_CCE')),
        'batch_complete_numeric':summary.get('complete_numeric',summary.get('complete_numeric_CCE')),
        'metrics':metrics,'marker_dict':projection['extraction']['marker_dict'],
        'time_total_hours':projection['time_calculation']['total_hours'],
        'time_contributions':projection['time_calculation']['known_operation_contributions'],
        'time_issues':projection['time_calculation']['issues'],
        'label_dependencies':{k:replay[k] for k in ['s_target_match','s_marker_fluor_compat','s_method_fluor_compat','s_label']},
        'component_gate_notes':notes,'projection_issues':projection['projection_issues'],
        'raw_entities':raw['entities'],'raw_relations':raw['relations'],'raw_intrinsic_signals':raw['intrinsic_signals'],
        'resolved_relations':[{k:x.get(k) for k in ['id','fluor_entity_id','target_entity_id','status','projection_allowed','mechanical_relation_state']} for x in resolved['relations']],
        'intrinsic_gate':[{k:x['identity_policy'].get(k) for k in ['projection_allowed','native_source_cue','affirmative_use_context','literal_identity_collisions','complete_name_occurrence']} for x in resolved['intrinsic_signals']],
        'label_header':[{k:u[k] for k in ['unit_id','start','end','text']} for u in doc['units'] if u['unit_id']=='L0002'],
        'formal_eligible':False}
def fmt(v):return 'NA' if v is None else f'{v:.6g}'
def main():
    if OUT.exists():raise ValueError('NEW_READOUT_ONLY')
    old,new=small('v7',OLD),small('v11',NEW)
    assert old['answer_sha256']==new['answer_sha256'] and old['input_sha256']==new['input_sha256']
    assert old['time_total_hours']==new['time_total_hours']==28 and old['metrics']['s_time']==new['metrics']['s_time']
    summary=read(NEW/'completion_summary.json');pairs=read(NEW/'per_pair.json')
    audit=read(BASE/'optimizer_round2_20261010/E2_source_audit_v11/actual_analysis/summary.json')
    assert summary['actual_observations']==21 and summary['pending']==0 and len(pairs)==15
    wanted=['deterministic_equivalent_representation','adjacent_entry_merge','evidence_supported_order_conflict']
    metrics=['c_param','co_order','co_method','co_param','co_chem','Com','Cor','sr','sp']
    selected=[p for c in wanted for p in pairs if p['condition']==c]
    compact=[{k:p[k] for k in ['pair_id','condition','question_id','baseline_case_id','variant_case_id','baseline_status','variant_status','both_arms_technical_complete']+
        [s+k for k in metrics for s in ['baseline_','variant_','delta_','available_']]} for p in selected]
    OUT.mkdir();save(OUT/'E2_09_evidence.json',{'same_full_input':True,'v7':old,'v11':new})
    save(OUT/'paired_readout.json',compact)
    with (OUT/'paired_readout.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
    labels={wanted[0]:'编号',wanted[1]:'合并',wanted[2]:'改序'}
    lines=[]
    for p in compact:
        values=[f'{fmt(p["baseline_"+k])}→{fmt(p["variant_"+k])}' for k in ['c_param','co_order','Cor','Com','sr','sp']]
        lines.append('| '+labels[p['condition']]+' | q'+str(p['question_id'])+' | '+' | '.join(values)+' |')
    text='''# v11 E2 实际结果读解

本批保留全部 21 观察与 15 对：19/21 技术成功，13/15 两臂技术完成；完整 CCE 0/21 观察、0/15 对。技术成功不等于分项完整或科学适用。以下是终态记录读解，没有重新运行抽取、评分或模型。

## E2_09：时间没有丢失，变化来自标签依赖

旧 v7 与新 v11 的 q22 原答案正文 SHA 和完整输入 SHA 均相同。两版都保留 7 个原核心时间贡献、总计 28h；`s_time` 同为 **4.151689580210213e-87**，并非 NA 或零。Com=0.885714、Cor=0.875、SR=5/7、SP=0.375 也相同。新版本变 NA 的是 `s_label`，继而 Eff、IA、HV 不再可算。

| 项目 | v7 归档 | v11 归档 |
|---|---:|---:|
| s_label | 0 | NA |
| s_time | 4.151689580210213e-87 | 同左 |
| Eff / IA | 0.32796278966132064 | NA |
| HV | 0.2541711619875235 | NA |
| complete_numeric 标记 | true | false |

原文标签标题位于 L0002、字符区间 [26,78)：`Chosen Labeling: [GFP (内源), MAP2 + Alexa Fluor]`（原 Markdown 在证据 JSON 保留）。v7 接受局部 Alexa Fluor→MAP2 和内源 GFP 身份，投影为 `{"Alexa Fluor":"MAP2","GFP":"GFP"}`。虽然未覆盖的名称候选令 label 输入状态仍为 partial，原 EGES 得到 `s_target_match=0`，而兼容性一项 NA；原有 bounded-min 的已知零规则仍保留 `s_label=0`。

v11 的标题 R01 **仍被原局部关系门接受**，并没有丢掉这一明确关系。但它额外报告后文 L0014 的同名 Alexa Fluor 为 `unknown/null target`（R02）。原单值字典投影按同一字面名称合并：同名组中存在未决关系，就把该名称的映射保持空值，不能将某一处已知关系任意推广到所有出现。另一方面，v11 将已选 GFP 分类为 `fluorophore`，并把 L0003 的同名 GFP 另列为 `mentioned`；原 native 门要求 fluorescent_protein 且无同名 usage 冲突，因此内源投影未获允许。原文 native cue 和 affirmative context 都实际为 true，但不是该门的全部条件。

结果投影为 `{"Alexa Fluor":"","GFP":""}`；`s_target_match` 与 `s_marker_fluor_compat` 均 NA，已知的 method–fluor compatibility=4.5 不足以独立确定完整 label 分数。这是**名称类别/多处提及的抽取选择，加上既有单值投影与依赖门**的共同结果，不能简化为“相同答案真的失去标签”或“时间评分退化”。目前没有对这些返回作修补。

旧列名 `candidate_raw_and_derived` 容易误导，但原 analyzer 的 `complete_numeric` 确实由该列的全部分项有限性计算，原 summary 实际计入 1/21，原配对仍为 0/15 完整。故旧数值不是一个未被计数的备用提议；同时 `formal_eligible=false`、fact acceptance pending 和 label partial 仍保留，**不能把旧完整 numeric 称作科学确认**。两版本提示/表示合同不同，历史对比也不是单因素随机实验。

## 编号、合并与改序的实际配对

下表都是原 analyzer 保存的两臂值，9 对均技术完成。编号使用各题自然基线；合并与改序使用各题独立编号标准基线，不能跨基线拼接比较。

| 控制 | 题目 | c_param | co_order | Cor | Com | SR | SP |
|---|---|---|---|---|---|---|---|
'''+ '\n'.join(lines)+'''

编号三对中，q2 的 c_param 3→2、Com 下降 0.2；另两题直接分项不变。三对 SR/SP 均不变，所以 q2 的差异不能归因于步骤分割。

合并三对中，q2 的 co_order 3→2、Cor 下降 1/12；q21/q22 的五个直接评分分项均不变。q21 的 SR 5/7→0、SP 6/11→0 导致 Com 下降 2/7；q22 的 SR 5/7→1 导致 Com 上升 4/35。这些仍是原 SR 对分段粒度的响应，不是本轮 v11 对 BioProBench 的修复。

改序三对的 co_order 均 3→0，Cor 均 0.875→0.625；其余四个直接评分分项和 SR/SP 保持不变。此处方向响应集中在顺序项，比同时改变多项更容易解释，但不能仅凭分数方向证明生物学依赖或理由正确。

固定 C05 q21（E2_15→E2_20）来源审计：两端预定 8 个时长分量均 **8/8** 精确保留，原操作多重集/分组合并核对通过，未删除整篇内容。抽取时长保留与原步骤匹配是不同环节；因此可以同时出现 8/8 保留和原 SR 5/7→0，不能用其中一个覆盖另一个。

## 证据与范围

- [E2_09 小字段证据](E2_09_evidence.json)、[逐对 CSV](paired_readout.csv)、[来源/实际命令](manifest.json)。
- [原 v11 完整分析](../grounded_controls_v11/completion_summary.json)、[来源审计](../E2_source_audit_v11/actual_analysis/summary.json)。
- [六分项配对图](../grounded_controls_v11_figures_v1/actual_01/paired_components.png)、[21 观察覆盖图](../grounded_controls_v11_figures_v1/actual_01/metric_coverage.png)。
- [实际论文报告](../manuscript_report_v2/v11_E2_actual_01/report_summary.json)。

代码依据：旧 E2 analyzer `cce_grounded_controls_v1.py:710` 起；已知零保留 `cce_grounded_development_v7.py:362` 起；同名映射合并/未决传播 `cce_grounded_extraction_v7.py:1137` 起；native 类型与同名 usage 条件 `cce_grounded_extraction_v7.py:760` 起。v11 沿用这些原科学门；本读解不修改任何代码、评分、参考或失败状态。未读取 E4 活批或确认材料，新增调用/向量/评分回放均 0。
'''
    (OUT/'E2_V11_READOUT_zh.md').write_text(text,encoding='utf8')
    for p in [ROOT/'scripts/cce_grounded_controls_v1.py',ROOT/'scripts/cce_grounded_development_v7.py',ROOT/'scripts/cce_grounded_extraction_v7.py',ROOT/'scripts/cce_round2_followup_runner_v11.py']:inputs.append(bind(p))
    assert all(bind(Path(b['path']))==b for b in inputs)
    save(OUT/'manifest.json',{'status':'read_only_terminal_evidence','actual_command':[sys.executable,*sys.argv],'script':bind(Path(__file__)),
        'inputs':list({b['path']:b for b in inputs}.values()),'outputs':[bind(p) for p in OUT.iterdir() if p.is_file()],
        'source_unchanged':True,'new_model_calls':0,'new_embeddings':0,'converter_calls':0,'score_calls':0,
        'E4_or_confirmation_read':False,'C05_counts':audit['C05']})
    print(json.dumps({'status':'complete','out':str(OUT),'E2_09_time_unchanged':True,'new_model_calls':0}))
if __name__=='__main__':main()
