"""Offline A04 six-observation identity trace; no output repair or new scores.

The forensic reader preserves duplicate JSON members and their raw offsets.
It is not an alternative scoring parser. Original strict parsing/field validation
is independently invoked and failed trials remain failures.
"""
from __future__ import annotations
import io
import contextlib
import json
from pathlib import Path
import re
import socket
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_identity_stability_dev_v1 as experiment
import cce_judges as j
import cce_output_contract_v1 as parent
import evaluator_integrity as integrity

OUT=experiment.OUT
NAMES=['Alexa Fluor 488','Alexa Fluor 647']
GENERIC='Alexa Fluor'


def check(ok,why):
    if not ok:raise AssertionError(why)


def bind(path):return parent.bind(path)


def no_network(*args,**kwargs):
    raise RuntimeError('A04 forensic trace forbids all network and generation')


def span(text,start,end):
    return {'start_codepoint':start,'end_codepoint_exclusive':end,'text':text[start:end],
            'start_utf8_byte':len(text[:start].encode('utf-8')),
            'end_utf8_byte_exclusive':len(text[:end].encode('utf-8')),
            'line_1based':text.count('\n',0,start)+1}


def literal_spans(text,literal):
    return [span(text,m.start(),m.end()) for m in re.finditer(re.escape(literal),text)]


class ForensicJSON:
    """Retain every object-member occurrence with offsets; never collapse keys."""
    def __init__(self,text):self.text=text;self.decoder=json.JSONDecoder()
    def ws(self,i):
        while i<len(self.text) and self.text[i].isspace():i+=1
        return i
    def parse(self):
        node,end=self.node(0)
        check(self.ws(end)==len(self.text),'forensic_multiple_values')
        return node
    def node(self,i):
        text=self.text;i=self.ws(i);start=i
        if text[i]=='{':
            members=[];i=self.ws(i+1)
            if text[i]=='}':return {'kind':'object','start':start,'end':i+1,'members':members},i+1
            while True:
                kstart=i;key,end=self.decoder.raw_decode(text,i)
                check(isinstance(key,str),'forensic_nonstring_object_key')
                i=self.ws(end);check(text[i]==':','forensic_missing_colon')
                value,i=self.node(i+1)
                members.append({'key':key,'key_start':kstart,'key_end':end,'value':value})
                i=self.ws(i)
                if text[i]=='}':return {'kind':'object','start':start,'end':i+1,'members':members},i+1
                check(text[i]==',','forensic_missing_comma');i=self.ws(i+1)
        if text[i]=='[':
            items=[];i=self.ws(i+1)
            if text[i]==']':return {'kind':'array','start':start,'end':i+1,'items':items},i+1
            while True:
                value,i=self.node(i);items.append(value);i=self.ws(i)
                if text[i]==']':return {'kind':'array','start':start,'end':i+1,'items':items},i+1
                check(text[i]==',','forensic_missing_array_comma');i=self.ws(i+1)
        value,end=self.decoder.raw_decode(text,i)
        return {'kind':'scalar','start':start,'end':end,'value':value},end
    def object_member(self,node,name):
        check(node['kind']=='object','forensic_expected_object')
        matches=[m for m in node['members'] if m['key']==name]
        check(len(matches)==1,'forensic_ambiguous_path:'+name)
        return matches[0]['value']


def audit_spans(text,node):
    if isinstance(node,dict):
        if {'start_codepoint','end_codepoint_exclusive','text'}<=set(node):
            a,b=node['start_codepoint'],node['end_codepoint_exclusive']
            check(text[a:b]==node['text'],'quoted_span_text_mismatch')
            check(len(text[:a].encode('utf-8'))==node['start_utf8_byte'],'span_start_byte_mismatch')
            check(len(text[:b].encode('utf-8'))==node['end_utf8_byte_exclusive'],'span_end_byte_mismatch')
        else:
            for value in node.values():audit_spans(text,value)
    elif isinstance(node,list):
        for value in node:audit_spans(text,value)


def main():
    socket.create_connection=no_network
    before=parent.request_count()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):experiment.validate()
    original_files={}
    def source(path):
        entry=bind(path);original_files[entry['path']]=entry['sha256'];return entry
    source(OUT/'plan.json');source(OUT/'matrix.json');source(OUT/'cases.json')
    source(OUT/'expected_scientific_contract.json');source(ROOT/'evaluator_integrity.py')
    source(ROOT/'OEQ_run_grading_new.py');source(ROOT/'scripts/cce_output_contract_v1.py')
    case_list=j.read(OUT/'cases.json')['cases']
    case_index=next(i for i,c in enumerate(case_list) if c['anonymous_answer_id']=='A04')
    case=case_list[case_index];answer=case['model_response']
    check(parent.rawsha(answer)==case['answer_sha256'],'frozen_A04_answer_hash')
    check(parent.rawsha(case['specific_question'])==case['question_sha256'],'frozen_A04_question_hash')
    header=re.search(r'^\*\*Chosen Labeling:\*\*[^\n]+',answer,re.M)
    check(header is not None,'source_label_header_missing')
    body='Alexa Fluor 488 and Alexa Fluor 647'
    check(answer.count(body)==1,'complete_name_body_phrase_not_unique')
    phrase_start=answer.index(body)
    target_phrase='primary antibodies (anti-GFP and anti-MAP2)'
    check(answer.count(target_phrase)==1,'target_phrase_not_unique')
    target_start=answer.index(target_phrase)
    source_evidence={'cases_file':source(OUT/'cases.json'),'json_pointer':f'/cases/{case_index}/model_response',
        'question_id':case['question_id'],'answer_raw_utf8_sha256':parent.rawsha(answer),
        'source_string_length_codepoints':len(answer),'header_generic_labeling':span(answer,header.start(),header.end()),
        'body_complete_name_list':span(answer,phrase_start,phrase_start+len(body)),
        'body_target_list':span(answer,target_start,target_start+len(target_phrase)),
        'complete_name_occurrences':{name:literal_spans(answer,name) for name in NAMES},
        'generic_only_occurrences':[span(answer,m.start(),m.end()) for m in re.finditer(r'Alexa Fluor(?!\s+\d)',answer)],
        'specific_dye_to_target_assignment_in_these_spans':None,
        'scope_assessment':'The submitted answer names both full dyes together and both targets, but does not explicitly bind either numbered dye to a particular target. No assignment is inferred from ordering, co-occurrence, or generic family names.',
        'not_a_biological_ground_truth_reference':True}
    audit_spans(answer,source_evidence)
    cells=[r for r in j.read(OUT/'matrix.json') if r['anonymous_answer_id']=='A04']
    check(len(cells)==6,'six_A04_cells_required')
    ledger={r['trial_id']:r for r in j.ledger_rows(parent.LEDGER) if r.get('event')=='request_started'}
    rows=[]
    for cell in cells:
        tid=cell['planned_trial_id'];trial_path=experiment.RUN/'trials'/f'{tid}.json'
        trial=j.read(trial_path);source(trial_path)
        check(trial['identity']==cell['identity'] and trial['case_id']==case['case_id'],'matrix_trial_binding')
        attempt=experiment.RUN/'attempts'/f'{tid}_1';provider_path=attempt/'provider_response.json'
        provider=j.read(provider_path);source(provider_path)
        receipt=j.read(attempt/'request_receipt.json');source(attempt/'request_receipt.json')
        check(receipt==ledger[tid] and trial['attempt']==1,'real_request_receipt_binding')
        prompt=(attempt/'prompt.txt').read_text(encoding='utf-8');source(attempt/'prompt.txt')
        check(prompt==(OUT/'prompts/A04_prompt.txt').read_text(encoding='utf-8'),'six_actual_prompts_not_identical')
        raw=provider['response'];reader=ForensicJSON(raw);tree=reader.parse()
        extraction=reader.object_member(tree,'extraction');markers=reader.object_member(extraction,'marker_dict')
        check(markers['kind']=='object','marker_dict_not_object')
        members=[]
        for i,member in enumerate(markers['members']):
            val=member['value'];check(val['kind']=='scalar','marker_member_not_scalar')
            members.append({'member_index_0based':i,'name':member['key'],'value':val['value'],
                'name_json_span':span(raw,member['key_start'],member['key_end']),
                'value_json_span':span(raw,val['start'],val['end'])})
        names=[m['name'] for m in members]
        duplicated={name:names.count(name) for name in dict.fromkeys(names) if names.count(name)>1}
        strict_error=None
        try:
            obj=integrity.parse_judge_object(raw);parent.core_gate(obj)
            strict_pass=True
        except (integrity.JudgeFormatError,ValueError,KeyError,TypeError) as exc:
            strict_pass=False;strict_error={'type':type(exc).__name__,'message':str(exc)}
        check(strict_pass==(trial['status']=='success'),'independent_strict_gate_disagrees_with_trial')
        present=[name for name in NAMES if name in names]
        if strict_pass:
            check(obj['extraction']==trial['evaluation']['extraction'],'successful_raw_extraction_changed')
        if duplicated:
            check(not strict_pass,'duplicate_key_passed_strict_gate')
        self_values=[m['name'] for m in members if m['name'] in NAMES and m['value']==m['name']]
        target_literals={name:[m['member_index_0based'] for m in members
            if re.search(r'(?<![A-Za-z0-9])'+re.escape(name)+r'(?![A-Za-z0-9])',m['name']+' '+str(m['value']))]
            for name in ['GFP','MAP2']}
        row={'anonymous_answer_id':'A04','question_id':case['question_id'],'judge':trial['judge'],
            'repeat_index':trial['repeat_index'],'trial_id':tid,'disposition':cell['disposition'],
            'original_observation_reused':cell['disposition']=='exact_prior_observation_reused',
            'actual_request_index':receipt['package_request_index'],'attempt':trial['attempt'],
            'trial_file':source(trial_path),'provider_response_file':source(provider_path),
            'response_raw_utf8_sha256':parent.rawsha(raw),'prompt_file':source(attempt/'prompt.txt'),
            'strict_structure_pass':strict_pass,'strict_error':strict_error,
            'recorded_trial_status':trial['status'],'recorded_failure_stage':trial['evaluation'].get('failure_stage'),
            'marker_dictionary_json_span':span(raw,markers['start'],markers['end']),
            'ordered_members_preserving_duplicates':members,'duplicate_member_names':duplicated,
            'complete_names_in_member_names':present,'complete_names_missing_from_member_names':[n for n in NAMES if n not in present],
            'complete_name_count':len(present),'expected_complete_name_count':2,
            'generic_member_count':names.count(GENERIC),
            'complete_name_occurrences_anywhere_in_raw_return':{n:literal_spans(raw,n) for n in NAMES},
            'self_identifier_values_for_full_dye_names':self_values,
            'literal_source_target_occurrences_in_marker_dictionary':target_literals,
            'target_assignment_scientifically_correct':None,'target_assignment_source_supported':None,
            'target_assignment_note':'Targets are not adjudicated. Specific numbered-dye mapping is not explicitly supplied by the source answer; neither self-named values nor inferred descriptive targets establish a correct assignment.',
            'provider_done_reason':provider.get('done_reason'),'provider_output_tokens':provider.get('eval_count'),
            'output_budget':8192,'output_budget_exhausted':provider.get('done_reason')=='length' or (isinstance(provider.get('eval_count'),int) and provider['eval_count']>=8192),
            'not_scored_or_repaired_by_forensic_reader':True}
        audit_spans(raw,{k:row[k] for k in ['marker_dictionary_json_span','ordered_members_preserving_duplicates','complete_name_occurrences_anywhere_in_raw_return']})
        rows.append(row)
    qwen=[r for r in rows if r['judge']=='local_qwen3_8b'];llama=[r for r in rows if r['judge']=='local_llama3_8b']
    qwen.sort(key=lambda r:r['repeat_index']);llama.sort(key=lambda r:r['repeat_index'])
    check([r['strict_structure_pass'] for r in qwen]==[False,False,True],'observed_Qwen_pattern_changed')
    check(qwen[0]['original_observation_reused'] and not qwen[1]['original_observation_reused'],'reuse_provenance_changed')
    check(all(r['duplicate_member_names']=={GENERIC:2} and r['complete_name_count']==0 for r in qwen[:2]),'failed_member_pattern_changed')
    check(qwen[2]['complete_name_count']==2 and qwen[2]['generic_member_count']==1,'successful_Qwen_name_pattern_changed')
    check(all(r['strict_structure_pass'] and r['complete_name_count']==2 and len(r['self_identifier_values_for_full_dye_names'])==2 for r in llama),'Llama_name_pattern_changed')
    check(all(not r['literal_source_target_occurrences_in_marker_dictionary']['MAP2'] for r in llama),'Llama_literal_MAP2_observation_changed')
    check(parent.request_count()==before,'trace_made_request')
    for path,digest in original_files.items():check(j.filehash(path)==digest,'original_file_modified')
    result={'status':'pass_for_offline_trace_verification','created_utc':j.now(),
        'scope':'One exposed development answer, two judges, three observations each; not six independent answers.',
        'source_evidence':source_evidence,'observations':rows,
        'findings':{
            'strict_passes':sum(r['strict_structure_pass'] for r in rows),'strict_failures':sum(not r['strict_structure_pass'] for r in rows),
            'full_names_preserved_in_marker_dictionary':sum(r['complete_name_count']==2 for r in rows),
            'Qwen_repeat_0_1':'Both collapse the two named dyes into two occurrences of the generic Alexa Fluor key, causing strict duplicate-key rejection. This identifies the direct structural failure, not why the model generated it.',
            'Qwen_repeat_2':'Passes strict structure and retains BOTH full names, plus one generic Alexa Fluor key. It is not merely a successful output obtained by omitting one of the two full names. Its descriptive target values remain unverified.',
            'Llama_all_repeats':'Both full names are preserved in all three marker_dict outputs, but each is mapped to its own dye name; MAP2 does not occur in marker_dict. Structural/name preservation does not establish correct target extraction.',
            'causal_limits':'The observed mixed generic header and full-name body are an input ambiguity context, not a proven causal mechanism. Same frozen input can yield different outputs. No seed, sampling, context-limit, or biological explanation is inferred.',
            'original_repeat_zero_and_first_repeat_failure_retained':True,'successful_repeat_not_selected_as_replacement':True,
            'target_assignment_correctness':None,'scientific_accuracy_repaired':False},
        'method':'Original strict parser and core field gate replayed. Separate duplicate-preserving forensic reader records ordered raw members and exact codepoint/UTF-8 offsets; never feeds reconstructed objects into scoring.',
        'checks':{'six_matrix_trial_receipt_bindings':True,'six_identical_actual_full_prompts':True,
            'all_source_and_raw_member_spans_roundtrip':True,'strict_gate_matches_recorded_status':True,
            'original_files_unchanged':True,'no_holdout_scientific_output_access':True},
        'input_bindings':[{'path':p,'sha256':h} for p,h in original_files.items()],
        'script':bind(__file__),'actual_command':[sys.executable,'scripts/cce_trace_A04_identity_stability_v1.py'],
        'new_judge_requests':0,'package_requests_snapshot':before,'expert_returns':0,'formal_eligible':False}
    j.save(OUT/'A04_repeat_trace.json',result)
    lines=['# A04：6 次观察的名称与结构对照','',
        '这是同一份公开开发答案在 2 个评价器、各 3 次观察中的对照，不是 6 份独立答案。仅核对原文与原始输出，不修改分数或修补失败。','',
        '原答案正文明确并列 `Alexa Fluor 488 and Alexa Fluor 647`，同时另列 anti-GFP 和 anti-MAP2。摘要只写通用 Alexa Fluor；没有把每个带编号染料明确绑定到某一目标，不能按顺序补出对应关系。完整逐字定位及哈希见 JSON。','',
        '| 评价器 | repeat | 原试验复用 | 严格结构 | 完整名称数 | 输出 marker_dict 成员（保留重复） |',
        '|---|---:|---|---|---:|---|']
    for r in rows:
        members='; '.join(f"{m['name']} → {m['value']}" for m in r['ordered_members_preserving_duplicates'])
        lines.append(f"| {r['judge']} | {r['repeat_index']} | {'是' if r['original_observation_reused'] else '否'} | {'通过' if r['strict_structure_pass'] else '失败：重复键'} | {r['complete_name_count']}/2 | {members} |")
    lines += ['',
        'Qwen repeat 0 和 1 的直接失败原因均为重复通用键 `Alexa Fluor`，两完整名称都未作为 marker_dict 成员名保留。原 repeat 0 是原样复用的真实失败，repeat 1 是本轮新增失败。','',
        'Qwen repeat 2 通过结构检查，而且两个完整名称确实都保留了；它还保留一个通用 Alexa Fluor 成员。因此这次成功不是单纯通过省略一个完整实体消除重复。但其将两染料分别赋给 “dendritic skeleton” 和 “local neuronal structures”，原文未明确给出这两个具体对应，不能据此认定目标提取正确。','',
        'Llama 三次都保留完整名称，却把每个染料映射为它自己的名称，marker_dict 中没有 MAP2。名称覆盖与结构通过都不能证明完成了目标对应提取。','',
        '原文摘要通用名称与正文完整名称并存，是可观察的输入背景；它是否导致模型折叠名称尚未建立因果证据。没有用重复观察推断种子、采样、上下文截断或生物学原因。','',
        '本核查复跑原严格解析器与字段检查，并使用单独的保序、保重复取证读取器记录成员偏移；后者未用于评分或救回失败。所有来源文件哈希保持不变，新增调用 0，专家回传 0，目标对应关系正确性仍为待定。','',
        '[逐条原文定位、输出成员、哈希与核验记录](A04_repeat_trace.json)','',
        '```powershell',f"& '{sys.executable}' scripts/cce_trace_A04_identity_stability_v1.py",'```']
    (OUT/'A04_repeat_trace.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(j.canonical({'status':result['status'],'observations':len(rows),'strict_passes':result['findings']['strict_passes'],
        'strict_failures':result['findings']['strict_failures'],'full_name_preservation':result['findings']['full_names_preserved_in_marker_dictionary'],
        'new_judge_requests':0,'trace_sha256':j.filehash(OUT/'A04_repeat_trace.json')}))


if __name__=='__main__':main()
