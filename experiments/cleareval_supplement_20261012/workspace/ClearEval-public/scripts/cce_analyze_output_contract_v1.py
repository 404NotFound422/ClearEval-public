"""Offline actual-return audit of the fixed output-contract development experiment.

Reads five exposed development cases in three separate versions. No held-out
scientific returns, model generation, output repair, or expert labels are used.
"""
from __future__ import annotations
import collections
import contextlib
import io
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_output_contract_v1 as exp
import cce_judges as j
import evaluator_integrity as integrity

OUT=exp.OUT/'analysis'
BASE=ROOT/'artifacts/cce_validation/judges'
DIRECT=['c_param','co_order','co_method','co_param','co_chem']
EGES=['s_method','s_label','s_trans','s_time']
METRICS=DIRECT+EGES+['Cor','Eff']
TOL=1e-12
INPUTS={}


def require(ok,why):
    if not ok:raise ValueError(why)


def bind(path):
    path=Path(path).resolve();INPUTS[str(path)]=j.filehash(path);return path


def read(path):return j.read(bind(path))


def text(path):return bind(path).read_text(encoding='utf-8')


def finite(x):return not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x)


def same(a,b):return (a is None and b is None) or (finite(a) and finite(b) and abs(a-b)<=TOL)


class Pairs(list):pass


def duplicates(raw):
    """Preserve every member pair; report metadata without selecting a scientific value."""
    try:obj=json.loads(raw,object_pairs_hook=Pairs)
    except ValueError:return [],False
    found=[]
    def walk(value,path):
        if isinstance(value,Pairs):
            grouped=collections.defaultdict(list)
            for k,v in value:grouped[k].append(v)
            for key,values in grouped.items():
                key_path=path+'/'+key.replace('~','~0').replace('/','~1')
                if len(values)>1:
                    found.append({'parent_json_pointer':path,'key_sha256':exp.rawsha(key),
                        'occurrences':len(values),'distinct_serialized_values':len({j.canonical(v) for v in values}),
                        'all_repeated_values_equal':all(v==values[0] for v in values),
                        'scientific_value_selected':False})
                for v in values:walk(v,key_path)
        elif isinstance(value,list):
            for n,v in enumerate(value):walk(v,path+'/'+str(n))
    walk(obj,'')
    return found,True


def quote_span(source,quote):
    starts=[m.start() for m in re.finditer(re.escape(quote),source)]
    return [{'quote':quote,'start_codepoint':s,'end_codepoint':s+len(quote),
             'quote_sha256':exp.rawsha(quote)} for s in starts]


def main():
    plan=exp.validate_plan();exp.require_probes();OUT.mkdir(exist_ok=True)
    ledger_before=j.filehash(exp.LEDGER)
    ledger={r['request_id']:r for r in j.ledger_rows(exp.LEDGER) if r.get('event')=='request_started'}
    cases={c['case_id']:c for c in read(exp.OUT/'cases.json')['cases']}
    matrix={c['case_id']:c for c in plan['matrix']}
    new_pre=read(exp.OUT/'preflight_verification.json')
    new_contract=read(exp.RUN/'preflight.json')['contract']
    require(j.digest(new_contract)==new_pre['contract_sha256'],'new_contract_mismatch')
    expected_new={r['identity']['case_id']:r for r in new_pre['planned_trials']}
    old_reuse=read(exp.DEV/'reuse_manifest.json')
    original_example=read(BASE/'stability_remediation_plan_v1/original_final_example.json')
    old_rubric=text(ROOT/'prompts/eval_oeq_teacher_rubric.txt')
    exemplars=[]
    for group in ('completeness','correctness'):
        for field,record in original_example['scores'][group].items():
            if isinstance(record,dict) and isinstance(record.get('reasoning'),str):
                exemplars.append({'field':field,'reason':record['reasoning'],'origin':'original_final_worked_example'})
    # Generic section placeholders are recorded separately from worked scientific reasons.
    for reason in re.findall(r'"reasoning"\s*:\s*"([^"\n]+)"',old_rubric):
        if not any(x['reason']==reason for x in exemplars):
            exemplars.append({'field':None,'reason':reason,'origin':'original_section_or_extraction_placeholder'})
    for p in [Path(__file__),exp.OUT/'plan.json',exp.OUT/'software_probes.json',exp.OUT/'diagnostic_summary.json',
              ROOT/'OEQ_run_grading_new.py',ROOT/'evaluator_integrity.py',ROOT/'scripts/cce_judges.py']:
        bind(p)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        runner,_,registry=j.runtime(exp.arguments())
    for relative,expected in new_contract['files'].items():
        require(j.filehash(bind(ROOT/relative))==expected,'actual_scoring_dependency_mismatch:'+relative)
    versions=[('original_rubric_dev',exp.DEV/'trials',exp.DEV),
              ('v2_prompt_schema_decode',BASE/'schema_decode_followup_v1/development/sealed/run/trials',
               BASE/'schema_decode_followup_v1/development/sealed/run'),
              ('canonical_output_contract_v1',exp.RUN/'trials',exp.RUN)]
    rows=[];reason_rows=[];bind_checks=[];new_indices=[];a04_trace=None
    for version,trial_dir,run_dir in versions:
        trials={r['case_id']:(p,r) for p in trial_dir.glob('*.json') for r in [read(p)]}
        require(set(trials)==set(cases) and len(trials)==5,'fixed_five_version_matrix:'+version)
        for cid,case in cases.items():
            path,t=trials[cid];aid=case['anonymous_answer_id'];qid=case['question_id']
            require(t['identity']['case_id']==cid and t['trial_id']==j.digest(t['identity']),'trial_identity')
            require(t['judge']==exp.MODEL and t['repeat_index']==0 and t['attempt']==1 and t['actual_api_request_made'],'actual_one_attempt')
            expected_input=j.digest({'question':case['specific_question'],'question_id':qid,
                                     'protocol':case['model_response'],'references':case['references']})
            require(t['full_text_input_sha256']==t['identity']['input_sha256']==expected_input==matrix[cid]['input_sha256'],'input_version_pair_identity')
            require(t['references_sha256']==j.digest(case['references']),'reference_identity')
            require(exp.rawsha(case['model_response'])==case['answer_sha256'] and exp.rawsha(case['specific_question'])==case['question_sha256'],'original_raw_text_identity')
            actual_run_dir=run_dir
            reused=False
            if version=='original_rubric_dev' and aid=='A02':
                source=next(r for r in old_reuse if r['answer_id']=='A02')
                source_path=Path(source['source_trial']['path'])
                require(j.filehash(bind(source_path))==j.filehash(path)==source['source_trial']['sha256'],'original_A02_exact_reuse')
                actual_run_dir=source_path.parents[1];reused=True
            attempt=actual_run_dir/'attempts'/f"{t['trial_id']}_1"
            receipt=read(attempt/'request_receipt.json')
            require(receipt==ledger[receipt['request_id']] and receipt['trial_id']==t['trial_id'] and receipt['model']==t['judge'],'receipt_ledger_binding')
            prompt=text(attempt/'prompt.txt');provider=read(attempt/'provider_response.json')
            require(j.filehash(attempt/'prompt.txt')==t['prompt_sha256'],'actual_prompt_sha')
            for key in ('specific_question','model_response'):
                require(prompt.count(case[key])==1,'original_full_text_not_exactly_once')
            require(prompt.endswith(exp.v2.reference_suffix(case)),'actual_reference_prompt_suffix')
            if version=='canonical_output_contract_v1':
                require(t['identity']==expected_new[cid]['identity'],'planned_new_identity')
                require(prompt==text(exp.OUT/'prompts'/f'{aid}_prompt.txt'),'new_prompt_not_frozen')
                new_indices.append(receipt['package_request_index'])
                context=read(attempt/'context_check.json')
                require(context['conservative_context_bound']==len(prompt.encode('utf-8'))+8192+256<=40960,'actual_context_bound')
            raw=provider['response'];e=t.get('evaluation') or {};generation=e.get('teacher_generation') or {}
            primary_raw_preserved=raw in (generation.get('content'),generation.get('raw_content'))
            if not primary_raw_preserved:
                require(version!='canonical_output_contract_v1' and t['status']=='failed' and
                        generation.get('failure_code')=='PROVIDER_EXCEPTION',
                        'unexpected_raw_provider_not_preserved_in_generation')
            diagnostic=exp.classify(provider)
            duplicate_info,json_syntax_complete=duplicates(raw)
            structural=diagnostic['technical_pass']
            full_pipeline=(t['status']=='success' and e.get('technical_status')=='VALID' and not e.get('_error'))
            values=j.proposals(e)
            require(values==t['preserved_numeric_proposals'],'saved_numeric_proposals')
            direct={k:values[k] for k in DIRECT}
            replay=False;raw_score_map={};effect_status={};extraction_sha=None
            if structural:
                parsed=integrity.parse_judge_object(raw)
                extraction,raw_score_map=exp.core_gate(parsed)
                if full_pipeline:
                    require(extraction==e['extraction'] and raw_score_map==e['legacy_diagnostics']['raw_teacher_scores'],'actual_parsed_values_binding')
                    extraction_sha=j.digest(extraction)
                    require(extraction_sha==t['extraction_sha256'],'actual_extraction_hash')
                    demand=registry.get(qid,case['specific_question'])
                    meta=runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]
                    quant={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),
                           'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
                    for key in ('reagent_ri_value','protocol_time_hours','method_stages'):
                        if key in extraction:quant[key]=extraction[key]
                    require(quant==e['quantitative_data'] and demand==e['user_preference_vector'],'original_EGES_input_identity')
                    effects=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,
                        extraction['marker_dict'],meta.get('marker_query_targets') or [])
                    require(all(same(effects[k],values[k]) for k in EGES),'original_EGES_replay')
                    effect_status={k:v for k,v in effects.items() if k.startswith('_s_') and ('status' in k or 'source' in k)}
                    for k in DIRECT:
                        group='completeness' if k=='c_param' else 'correctness'
                        require(raw_score_map[group][k]['score']==values[k],'five_direct_score_raw_identity')
                    correct=[values[k]/m if values[k] is not None else None for k,m in zip(DIRECT[1:],[3,2,2,1])]
                    cor=sum(correct)/4 if all(v is not None for v in correct) else None
                    eff=[(values['s_method']/2.5+1)/2 if values['s_method'] is not None else None,
                         values['s_label']/6 if values['s_label'] is not None else None,
                         values['s_trans']/3 if values['s_trans'] is not None else None,
                         values['s_time']/3 if values['s_time'] is not None else None]
                    eff=sum(eff)/4 if all(v is not None for v in eff) else None
                    require(same(cor,values['Cor']) and same(eff,values['Eff']),'original_normalized_aggregation')
                    replay=True
                for field in DIRECT:
                    group='completeness' if field=='c_param' else 'correctness'
                    reason=raw_score_map[group][field].get('reasoning')
                    copies=[x for x in exemplars if reason==x['reason']]
                    reason_rows.append({'version':version,'anonymous_answer_id':aid,'field':field,
                        'reason_present':isinstance(reason,str) and bool(reason.strip()),
                        'reason_sha256':exp.rawsha(reason) if isinstance(reason,str) else None,
                        'reason_characters':len(reason) if isinstance(reason,str) else None,
                        'exact_historical_example_match':bool(copies),
                        'example_match_origins':[x['origin'] for x in copies],
                        'exact_reason_present_in_own_prompt':bool(isinstance(reason,str) and len(reason.strip())>=12 and reason in prompt),
                        'semantic_fidelity_or_unique_reasoning_certified':False})
            else:
                require(not full_pipeline and all(values[k] is None for k in METRICS),'failed_trial_not_NA')
            if version=='canonical_output_contract_v1' and aid=='A04':
                source=case['model_response']
                names=['Alexa Fluor 488','Alexa Fluor 647','different Alexa Fluor']
                spans={n:quote_span(source,n) for n in names}
                require(all(spans.values()),'development_name_distinction_evidence_missing')
                # Record exactly the duplicate generic name and equality metadata;
                # never choose a value or repair the failed extraction.
                generic_count=len(re.findall(r'"Alexa Fluor"\s*:',raw))
                require(generic_count==2 and len(duplicate_info)==1 and
                        duplicate_info[0]['parent_json_pointer']=='/extraction/marker_dict' and
                        duplicate_info[0]['all_repeated_values_equal'],'A04_observed_duplicate_changed')
                a04_trace={'anonymous_answer_id':aid,'answer_sha256':case['answer_sha256'],
                    'provider_response_sha256':j.filehash(attempt/'provider_response.json'),
                    'raw_return_sha256':exp.rawsha(raw),'source_name_spans':spans,
                    'generic_duplicate_key':'Alexa Fluor','generic_key_count':generic_count,
                    'generic_key_raw_spans':quote_span(raw,'"Alexa Fluor"'),
                    'duplicate_values_equal':True,'source_numbered_names_retained_as_output_keys':{
                        n:bool(re.search(r'"'+re.escape(n)+r'"\s*:',raw)) for n in names[:2]},
                    'original_header_generic_labels':'Header itself repeats the generic Alexa Fluor name; body explicitly names two numbered fluorophores.',
                    'conclusion':'The returned mapping failed to retain two distinguishable body names and repeated their generic family name. This case does not demonstrate that one actual fluorophore must map to multiple distinct targets under the current schema.',
                    'boundary':'No automatic suffix-to-target assignment, no raw-output repair, no claim that prompt cleanup solves identity normalization or reason faithfulness.'}
            missing={k:('technical_pipeline_failure' if not full_pipeline else 'upstream_component_unknown') for k in METRICS if values[k] is None}
            if full_pipeline:
                for issue in e.get('integrity',{}).get('issues',[]):
                    if issue.get('code')=='UNKNOWN_COMPONENT' and issue.get('component') in missing:
                        missing[issue['component']]='original_runner_UNKNOWN_COMPONENT; specific scientific cause not inferred'
            rows.append({'version':version,'anonymous_answer_id':aid,'question_id':qid,'case_id':cid,
                'trial_id':t['trial_id'],'trial_path':str(path),'request_index':receipt['package_request_index'],
                'reused_original_actual_trial':reused,'structural_validator_pass':structural,
                'full_pipeline_success':full_pipeline,'fully_numeric_original_components':full_pipeline and all(finite(values[k]) for k in METRICS),
                'failure_layer':diagnostic['failure_layer'],'failure_code':diagnostic['failure_code'],
                'original_runner_failure_stage':e.get('failure_stage'),'provider_done':provider.get('done'),
                'raw_preserved_in_primary_generation_record':primary_raw_preserved,
                'provider_finish_reason':provider.get('done_reason'),'output_tokens':provider.get('eval_count'),
                'complete_standard_json_syntax':json_syntax_complete,'duplicate_metadata':duplicate_info,
                'five_direct_scores':direct,'preserved_numeric_proposals':{k:values[k] for k in METRICS},
                'numeric_NA_reasons':missing,'original_EGES_identity_replay_pass':replay,
                'EGES_reference_status_metadata':effect_status,'extraction_sha256':extraction_sha,
                'input_sha256':expected_input,'judge_contract_sha256':t['identity']['contract_sha256'],
                'formal_eligible':False,'expert_confirmation':None})
            bind_checks.append({'version':version,'anonymous_answer_id':aid,'trial_receipt_prompt_raw_bound':True,
                'same_original_question_answer_references_across_versions':True,'EGES_replayed_if_pipeline_success':replay,
                'strict_failed_record_not_repaired':not structural})
    require(sorted(new_indices)==list(range(137,142)),'new_actual_indices_not_137_to_141')
    summaries=[]
    for version,_,_ in versions:
        rs=[r for r in rows if r['version']==version];reasons=[r for r in reason_rows if r['version']==version]
        summaries.append({'version':version,'fixed_answers':5,'actual_pipeline_observations':5,
            'structural_passes':sum(r['structural_validator_pass'] for r in rs),
            'full_pipeline_successes':sum(r['full_pipeline_success'] for r in rs),
            'fully_numeric_original_components':sum(r['fully_numeric_original_components'] for r in rs),
            'failed_answer_ids':[r['anonymous_answer_id'] for r in rs if not r['full_pipeline_success']],
            'numeric_NA_answer_ids':[r['anonymous_answer_id'] for r in rs if r['numeric_NA_reasons']],
            'direct_reason_records_examined':len(reasons),
            'direct_reasons_exact_historical_example_matches':sum(r['exact_historical_example_match'] for r in reasons),
            'c_param_exact_historical_example_matches':sum(r['field']=='c_param' and r['exact_historical_example_match'] for r in reasons),
            'direct_reasons_exact_own_prompt_matches':sum(r['exact_reason_present_in_own_prompt'] for r in reasons)})
    paired=[]
    for cid,case in cases.items():
        versions_by={r['version']:r for r in rows if r['case_id']==cid}
        paired.append({'anonymous_answer_id':case['anonymous_answer_id'],'question_id':case['question_id'],
            'same_full_input_reference_sha256':matrix[cid]['input_sha256'],
            'versions':{version:{k:r[k] for k in ('trial_id','request_index','structural_validator_pass','full_pipeline_success',
                'fully_numeric_original_components','failure_layer','five_direct_scores','numeric_NA_reasons','judge_contract_sha256')}
                for version,r in versions_by.items()},
            'interpretation':'Three different prompt/decoder/adapter versions; never pooled as repeats or selected per answer for best outcome.'})
    current=next(s for s in summaries if s['version']=='canonical_output_contract_v1')
    summary={'status':'complete','new_generation_requests':5,'analysis_new_requests':0,'actual_request_indices':sorted(new_indices),
        'package_requests_at_analysis':len(ledger),'fixed_development_answers':5,'structural_gate_passed':current['structural_passes']==5,
        'structural_passes':current['structural_passes'],'full_pipeline_successes':current['full_pipeline_successes'],
        'fully_numeric_original_components':current['fully_numeric_original_components'],
        'failure_answer_ids':current['failed_answer_ids'],'version_summaries':summaries,
        'no_holdout_followup_or_retries':True,'original_five_plus_fifteen_expert_selection_unchanged':True,
        'existing_expert_packet_versions_unchanged':True,'scientific_fidelity_verified':False,'expert_returns':0,'formal_eligible':False,
        'interpretation':'Prompt-format cleanup did not eliminate repeated generic marker keys in A04. Failure attribution and raw metadata are now preserved at the generated-JSON layer; no automatic value choice was made.',
        'causal_boundary':'Combined prompt changes, decoder differences versus schema history, and adapter provenance are separate configurations. Five development observations do not isolate a single prompt sentence or establish general superiority.'}
    for name,obj in [('per_observation.json',rows),('technical_paired_versions.json',paired),('reason_copy_diagnostics.json',reason_rows),
                     ('A04_name_collision_trace.json',a04_trace),('completion_summary.json',summary)]:j.save(OUT/name,obj)
    require(j.filehash(exp.LEDGER)==ledger_before,'offline_analysis_modified_ledger');exp.validate_plan()
    require(all(j.filehash(p)==h for p,h in INPUTS.items()),'analysis_input_changed')
    j.save(OUT/'analysis_verification.json',{'status':'pass','input_sha256':INPUTS,'ledger_snapshot_sha256':ledger_before,
        'actual_new_trials_verified':5,'historical_development_trials_verified':10,'all_version_observations':15,
        'binding_checks':bind_checks,'new_requests':0,'tolerance':TOL,'strict_duplicate_parser_unchanged':True,
        'all_current_pipeline_successes_original_EGES_replayed':all(r['original_EGES_identity_replay_pass'] for r in rows if r['version']=='canonical_output_contract_v1' and r['full_pipeline_success'])})
    lines=['# 输出契约 v1：真实五份开发结果','',
        f"本批请求 137–141，真实完成 5 次，全包 {len(ledger)} 次。结构校验 {current['structural_passes']}/5，全管线成功 {current['full_pipeline_successes']}/5，原数值分项齐全 {current['fully_numeric_original_components']}/5。没有追加重试、留出调用或专家标签。",'',
        '| 版本 | 结构通过 | 全管线成功 | 原数值分项齐全 |',
        '|---|---:|---:|---:|']
    for s in summaries:lines.append(f"| {s['version']} | {s['structural_passes']}/5 | {s['full_pipeline_successes']}/5 | {s['fully_numeric_original_components']}/5 |")
    lines += ['', '原版 5 份包含 A02 的精确真实 trial 复用；不是本次新增调用。三版保留各自结果，不按每份挑最佳版本，也不作为同配置重复。', '',
        'A04 再次因 marker_dict 重复键被拒绝。这次两个泛称键及其值都相同，不能写成“不同值冲突”。provider 正常 stop，输出 572 tokens。原答案标题重复泛称 Alexa Fluor，但正文明确区分 Alexa Fluor 488、Alexa Fluor 647；返回未保留数字后缀，重复泛称键。现有证据指向身份名称未保留，不能用本例证明同一种实际荧光团必须对应多个不同靶标、因而字典结构必然不足。没有替答案补配靶标或修返回。', '',
        '新适配保留原 provider 原文和 metadata，并由原严格 parser 在 JSON_PARSE 拒绝这份返回。故障定位更准确；本次负结果表明 canonical 字段和移除示例仍不足以保证唯一键或忠实提取。5/5 预设结构门未过，没有自动后续批次。', '',
        '| 匿名 ID | c_param | co_order | co_method | co_param | co_chem |',
        '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['version']=='canonical_output_contract_v1':
            lines.append('| '+r['anonymous_answer_id']+' | '+' | '.join('NA' if r['five_direct_scores'][k] is None else str(r['five_direct_scores'][k]) for k in DIRECT)+' |')
    lines += ['', '理由核查仅比较完整字符串与历史实例/本次实传提示是否相等；不是语义忠实度认证。各版可核查理由数量和精确复制次数见 JSON，失败返回不经宽松解析恢复评分。', '',
        '[逐次真实值和 NA](per_observation.json)、[三版成对记录](technical_paired_versions.json)、[理由诊断](reason_copy_diagnostics.json)、[A04 名称碰撞来源与偏移](A04_name_collision_trace.json)、[输入哈希与重放验证](analysis_verification.json)。', '',
        '实际离线命令：', '', '```powershell',
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_output_contract_v1.py", '```', '',
        '现有专家审阅附件版本不变；本批新提取不会替代原建议版本。', '']
    (OUT/'RESULTS_zh.md').write_text('\n'.join(lines),encoding='utf-8')
    j.save(OUT/'execution.json',{'utc':j.now(),'argv':[sys.executable,'scripts/cce_analyze_output_contract_v1.py'],
        'cwd':str(ROOT),'status':'completed','new_requests':0,'script_sha256':j.filehash(__file__),
        'result_sha256':j.filehash(OUT/'completion_summary.json')})
    print(j.canonical(summary))


if __name__=='__main__':main()
