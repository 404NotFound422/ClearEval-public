"""Read-only paired v1/v2 development audit; no output repair or model requests."""
from __future__ import annotations
import collections
import contextlib
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_output_identity_v2 as exp
import cce_output_contract_v1 as parent
import cce_analyze_output_contract_v1 as audit
import cce_judges as j
import evaluator_integrity as integrity

OUT=exp.OUT/'analysis'
INPUTS={}
DIRECT=audit.DIRECT
EGES=audit.EGES
METRICS=audit.METRICS


def require(ok,why):
    if not ok:raise ValueError(why)


def bind(path):
    path=Path(path).resolve();INPUTS[str(path)]=j.filehash(path);return path


def read(path):return j.read(bind(path))


def text(path):return bind(path).read_text(encoding='utf-8')


def marker_pairs_without_repair(raw):
    try:obj=json.loads(raw,object_pairs_hook=audit.Pairs)
    except ValueError:return None
    def unique(parent_obj,key):
        if not isinstance(parent_obj,audit.Pairs):return None
        items=[v for k,v in parent_obj if k==key]
        return items[0] if len(items)==1 else None
    markers=unique(unique(obj,'extraction'),'marker_dict')
    return list(markers) if isinstance(markers,audit.Pairs) else None


def main():
    plan=exp.validate();exp.require_probes();OUT.mkdir(exist_ok=True)
    ledger_sha=j.filehash(exp.LEDGER)
    ledger={r['request_id']:r for r in j.ledger_rows(exp.LEDGER) if r.get('event')=='request_started'}
    cases={c['case_id']:c for c in read(exp.OUT/'cases.json')['cases']}
    parent_trace=read(parent.OUT/'analysis/A04_name_collision_trace.json')
    parent_reasons=read(parent.OUT/'analysis/reason_copy_diagnostics.json')
    original_example=read(ROOT/'artifacts/cce_validation/judges/stability_remediation_plan_v1/original_final_example.json')
    old_reasons={record['reasoning'] for group in original_example['scores'].values() if isinstance(group,dict)
                 for record in group.values() if isinstance(record,dict) and isinstance(record.get('reasoning'),str)}
    for p in [Path(__file__),ROOT/'scripts/cce_analyze_output_contract_v1.py',exp.OUT/'plan.json',
              exp.OUT/'software_probes.json',parent.OUT/'analysis/analysis_verification.json']:
        bind(p)
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        runner,_,registry=j.runtime(exp.arguments())
    rows=[];reason_rows=[];indices=[];a04=[];version_contracts={}
    for version,batch in [('output_contract_v1',parent.OUT),('output_identity_v2',exp.OUT)]:
        pre=read(batch/'preflight_verification.json');contract=read(batch/'run/preflight.json')['contract']
        version_contracts[version]=j.digest(contract)
        require(version_contracts[version]==pre['contract_sha256'],'contract_hash')
        expected={x['identity']['case_id']:x for x in pre['planned_trials']}
        for relative,h in contract['files'].items():require(j.filehash(bind(ROOT/relative))==h,'old_scoring_file_changed')
        trials={t['case_id']:(p,t) for p in (batch/'run/trials').glob('*.json') for t in [read(p)]}
        require(set(trials)==set(cases),'five_actual_cases_not_exact')
        for cid,case in cases.items():
            path,t=trials[cid];aid=case['anonymous_answer_id'];qid=case['question_id']
            require(t['identity']==expected[cid]['identity'] and t['trial_id']==j.digest(t['identity']),'trial_planned_identity')
            require(t['repeat_index']==0 and t['attempt']==1 and t['judge']==parent.MODEL and t['actual_api_request_made'],'one_actual_request')
            full_hash=j.digest({'question':case['specific_question'],'question_id':qid,
                'protocol':case['model_response'],'references':case['references']})
            require(t['full_text_input_sha256']==t['identity']['input_sha256']==full_hash,'unchanged_full_input')
            require(t['references_sha256']==j.digest(case['references']),'unchanged_references')
            require(parent.rawsha(case['model_response'])==case['answer_sha256'] and
                    parent.rawsha(case['specific_question'])==case['question_sha256'],'original_raw_hashes')
            attempt=batch/'run/attempts'/f"{t['trial_id']}_1"
            receipt=read(attempt/'request_receipt.json')
            require(receipt==ledger[receipt['request_id']] and receipt['trial_id']==t['trial_id'],'actual_ledger_receipt')
            actual_prompt=text(attempt/'prompt.txt');frozen_prompt=text(batch/'prompts'/f'{aid}_prompt.txt')
            require(actual_prompt==frozen_prompt and j.filehash(attempt/'prompt.txt')==t['prompt_sha256'],'actual_frozen_prompt')
            for key in ('specific_question','model_response'):require(actual_prompt.count(case[key])==1,'full_text_not_exactly_once')
            require(actual_prompt.endswith(parent.v2.reference_suffix(case)),'same_reference_payload')
            if version=='output_identity_v2':
                prior=text(parent.OUT/'prompts'/f'{aid}_prompt.txt')
                require(actual_prompt.count(exp.INSTRUCTION)==1 and actual_prompt.replace(exp.INSTRUCTION,'',1)==prior,'single_added_instruction_only')
                indices.append(receipt['package_request_index'])
            context=read(attempt/'context_check.json')
            require(context['conservative_context_bound']==len(actual_prompt.encode('utf-8'))+8192+256<=40960,'actual_prompt_no_truncation_guard')
            provider=read(attempt/'provider_response.json');raw=provider['response'];e=t.get('evaluation') or {}
            generation=e.get('teacher_generation') or {}
            require(raw in (generation.get('content'),generation.get('raw_content')),'raw_metadata_not_preserved')
            diagnostic=parent.classify(provider)
            duplicated,json_complete=audit.duplicates(raw)
            structural=diagnostic['technical_pass']
            full=t['status']=='success' and e.get('technical_status')=='VALID' and not e.get('_error')
            values=j.proposals(e);require(values==t['preserved_numeric_proposals'],'numeric_proposals_binding')
            replay=False;marker_schema_audit=[]
            pairs=marker_pairs_without_repair(raw)
            # Raw pairs are ONLY inspected for identity metadata; they never feed a scorer.
            pair_metadata=None if pairs is None else [{'key':k,'key_sha256':parent.rawsha(k),
                'target_value_sha256':j.digest(v),'source_literal_key_occurrences':case['model_response'].count(k),
                'source_case_insensitive_occurrences':case['model_response'].casefold().count(k.casefold())} for k,v in pairs]
            if structural:
                obj=integrity.parse_judge_object(raw);extraction,raw_scores=parent.core_gate(obj)
                if full:
                    require(extraction==e['extraction'] and j.digest(extraction)==t['extraction_sha256'] and
                        raw_scores==e['legacy_diagnostics']['raw_teacher_scores'],'strict_parsed_scientific_identity')
                    demand=registry.get(qid,case['specific_question'])
                    meta=runner.QUESTION_META_KB[registry.questions[str(qid)]['question_id']]
                    quant={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),
                        'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
                    for key in ('reagent_ri_value','protocol_time_hours','method_stages'):
                        if key in extraction:quant[key]=extraction[key]
                    require(quant==e['quantitative_data'] and demand==e['user_preference_vector'],'EGES_quantitative_input_binding')
                    effects=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,
                        extraction['marker_dict'],meta.get('marker_query_targets') or [])
                    require(all(audit.same(effects[k],values[k]) for k in EGES),'original_EGES_replay')
                    for k in DIRECT:
                        group='completeness' if k=='c_param' else 'correctness'
                        require(values[k]==raw_scores[group][k]['score'],'direct_score_identity')
                    replay=True
                for k in DIRECT:
                    group='completeness' if k=='c_param' else 'correctness';reason=raw_scores[group][k].get('reasoning')
                    reason_rows.append({'version':version,'anonymous_answer_id':aid,'field':k,
                        'reason_sha256':parent.rawsha(reason) if isinstance(reason,str) else None,
                        'exact_old_final_example_match':reason in old_reasons if isinstance(reason,str) else False,
                        'exact_own_prompt_match':isinstance(reason,str) and len(reason.strip())>=12 and reason in actual_prompt,
                        'semantic_fidelity_verified':False})
            else:require(not full and all(values[k] is None for k in METRICS),'strict_failure_not_NA')
            if aid=='A04':
                explicit_names=['Alexa Fluor 488','Alexa Fluor 647']
                source_spans={n:audit.quote_span(case['model_response'],n) for n in explicit_names}
                require(all(source_spans.values()),'fixed_A04_full_name_evidence_missing')
                name_keys=[k for k,v in pairs] if pairs is not None else []
                a04.append({'version':version,'anonymous_answer_id':aid,'answer_sha256':case['answer_sha256'],
                    'source_complete_name_spans':source_spans,'raw_marker_member_pairs':pair_metadata,
                    'numbered_name_retained_as_exact_output_key':{n:n in name_keys for n in explicit_names},
                    'generic_key_occurrences':name_keys.count('Alexa Fluor'),'duplicate_metadata':duplicated,
                    'structural_validator_pass':structural,'full_pipeline_success':full,
                    'raw_return_sha256':parent.rawsha(raw),'provider_finish_reason':provider.get('done_reason'),
                    'output_tokens':provider.get('eval_count'),
                    'complete_names_are_directly_available_from_source':True,
                    'target_assignment_verified':False,
                    'target_assignment_boundary':'Distinct source names do not authorize assigning each suffix to a specific target from order or co-occurrence. No mapping has been repaired or certified.',
                    'schema_insufficiency_proven':False})
            na={k:'technical_pipeline_failure' if not full else 'original_upstream_component_unknown' for k in METRICS if values[k] is None}
            row={'version':version,'anonymous_answer_id':aid,'question_id':qid,'trial_id':t['trial_id'],
                'request_index':receipt['package_request_index'],'input_sha256':full_hash,
                'structural_validator_pass':structural,'full_pipeline_success':full,
                'fully_numeric_original_components':full and all(audit.finite(values[k]) for k in METRICS),
                'failure_layer':diagnostic['failure_layer'],'failure_code':diagnostic['failure_code'],
                'original_runner_failure_stage':e.get('failure_stage'),'duplicate_metadata':duplicated,
                'provider_done':provider.get('done'),'provider_finish_reason':provider.get('done_reason'),
                'output_tokens':provider.get('eval_count'),'complete_json_syntax':json_complete,
                'five_direct_scores':{k:values[k] for k in DIRECT},'preserved_numeric_proposals':{k:values[k] for k in METRICS},
                'numeric_NA_reasons':na,'original_EGES_identity_replay_pass':replay,
                'raw_marker_identity_metadata_no_value_repair':pair_metadata,
                'target_relations_expert_verified':False,'formal_eligible':False,'expert_confirmation':None}
            rows.append(row)
    require(sorted(indices)==list(range(142,147)),'new_requests_not_expected_five')
    summaries=[]
    for version in version_contracts:
        rs=[r for r in rows if r['version']==version];rr=[r for r in reason_rows if r['version']==version]
        summaries.append({'version':version,'actual_observations':5,'structural_passes':sum(r['structural_validator_pass'] for r in rs),
            'full_pipeline_successes':sum(r['full_pipeline_success'] for r in rs),
            'fully_numeric_original_components':sum(r['fully_numeric_original_components'] for r in rs),
            'failed_answer_ids':[r['anonymous_answer_id'] for r in rs if not r['full_pipeline_success']],
            'reason_records':len(rr),'exact_old_final_example_reason_matches':sum(r['exact_old_final_example_match'] for r in rr),
            'exact_own_prompt_reason_matches':sum(r['exact_own_prompt_match'] for r in rr)})
    pairs=[]
    for aid in parent.IDS:
        a=next(r for r in rows if r['anonymous_answer_id']==aid and r['version']=='output_contract_v1')
        b=next(r for r in rows if r['anonymous_answer_id']==aid and r['version']=='output_identity_v2')
        require(a['input_sha256']==b['input_sha256'],'paired_input_identity')
        pairs.append({'anonymous_answer_id':aid,'question_id':a['question_id'],'same_input_sha256':a['input_sha256'],
            'before_trial_id':a['trial_id'],'after_trial_id':b['trial_id'],
            'before_structural_pass':a['structural_validator_pass'],'after_structural_pass':b['structural_validator_pass'],
            'before_full_pipeline_success':a['full_pipeline_success'],'after_full_pipeline_success':b['full_pipeline_success'],
            'metric_deltas':{k:b['preserved_numeric_proposals'][k]-a['preserved_numeric_proposals'][k]
                if audit.finite(a['preserved_numeric_proposals'][k]) and audit.finite(b['preserved_numeric_proposals'][k]) else None for k in METRICS},
            'NA_is_not_zero':True,'different_prompt_versions_not_repeats':True})
    identical_marker_pairs=(a04[0]['raw_marker_member_pairs']==a04[1]['raw_marker_member_pairs'])
    current=summaries[-1]
    summary={'status':'complete','actual_new_requests':5,'actual_request_indices':sorted(indices),'package_requests_at_analysis':len(ledger),
        'structural_passes':current['structural_passes'],'full_pipeline_successes':current['full_pipeline_successes'],
        'fully_numeric_original_components':current['fully_numeric_original_components'],'five_case_structural_gate_passed':current['structural_passes']==5,
        'version_summaries':summaries,'A04_marker_member_pairs_identical_between_versions':identical_marker_pairs,
        'A04_source_full_names_preserved_in_v2_keys':all(a04[-1]['numbered_name_retained_as_exact_output_key'].values()),
        'no_automatic_E2_E4_calls':True,'analysis_new_requests':0,'formal_eligible':False,'expert_returns':0,
        'interpretation':'Generic identity-preservation instruction did not eliminate the A04 generic-key collision in this development run. The result remains a strict failure; no scientific output was selected or repaired.',
        'scientific_target_mapping_verified':False,'expert_review_packet_versions_changed':False,
        'coarse_future_budget_only':{'E2_max_new_calls':21,'E4_max_new_calls':30,'combined_max':51,
            'conditional_package_upper_bound':len(ledger)+51,'remaining_to_300_if_all_executed':300-len(ledger)-51,
            'status':'not_authorized_by_this_run_gate_and_not_executed'}}
    for name,obj in [('completion_summary.json',summary),('per_observation.json',rows),('paired_v1_v2.json',pairs),
                     ('A04_identity_comparison.json',{'versions':a04,'identical_raw_marker_member_pair_metadata':identical_marker_pairs}),
                     ('reason_copy_diagnostics.json',reason_rows)]:j.save(OUT/name,obj)
    require(j.filehash(exp.LEDGER)==ledger_sha,'analysis_modified_ledger');exp.validate()
    require(all(j.filehash(p)==h for p,h in INPUTS.items()),'input_changed_during_analysis')
    j.save(OUT/'analysis_verification.json',{'status':'pass','input_sha256':INPUTS,'ledger_snapshot_sha256':ledger_sha,
        'actual_trials_verified':10,'new_trial_receipt_prompt_identity_checks':5,
        'strict_raw_return_replays':10,'original_EGES_success_replays':sum(r['original_EGES_identity_replay_pass'] for r in rows),
        'original_core_and_lexicon_bytes_unchanged':True,'single_generic_prompt_insertion_verified_for_all_five':True,
        'no_value_selection_from_duplicate_objects':True,'new_requests':0,'tolerance':1e-12})
    lines=['# 完整名称规则 v2：真实开发配对结果','',
        '请求 142–146 已终态，全包 146 次。v1 和 v2 均为结构通过 4/5、全管线成功 4/5、原数值分项齐全 4/5。A04 再次失败，未追加重试，也未开始 E2/E4。', '',
        'A04 原答案正文的两个完整名称仍未成为返回键；输出重复同一个泛称键，两个值相同。v1/v2 的原始 marker 成员对元数据一致。provider 正常 stop，本次 701 tokens；原严格 parser 在 JSON_PARSE 拒绝。完整名称可以从原文获得，但这不等于每个名称与每个靶标的对应关系已经核实。没有按出现顺序补配靶标，没有把重复对象修成合法提取。', '',
        '因此，这次通用身份提示没有修复该开发例。不能宣称科学有效性提高，也不能把此失败直接当成同一真实荧光团多靶标超出字典表达能力的证明。未知靶标关系、提取语义忠实度和专家核查仍待定。', '',
        '| 匿名 ID | v1 结构 | v2 结构 | v2 c_param | v2 co_order | v2 co_method | v2 co_param | v2 co_chem |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for pair in pairs:
        r=next(r for r in rows if r['version']=='output_identity_v2' and r['anonymous_answer_id']==pair['anonymous_answer_id'])
        lines.append('| '+r['anonymous_answer_id']+' | '+('通过' if pair['before_structural_pass'] else '失败')+' | '+('通过' if pair['after_structural_pass'] else '失败')+' | '+' | '.join('NA' if r['five_direct_scores'][k] is None else str(r['five_direct_scores'][k]) for k in DIRECT)+' |')
    lines += ['', '两版是不同提示条件，按真实试次分别保存；没有挑选最优版本或合并成重复样本。成功记录原 EGES 输入、固定需求、原函数及输出逐项重放；失败分项继续 NA。现有专家附件未更新。', '',
        '[逐次结果](per_observation.json)、[真实成对变化](paired_v1_v2.json)、[A04 原始名称身份对照](A04_identity_comparison.json)、[严格回放与全部来源哈希](analysis_verification.json)、[终态汇总和后续粗预算](completion_summary.json)。', '',
        '实际离线命令：', '', '```powershell',
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_analyze_output_identity_v2.py", '```', '']
    (OUT/'RESULTS_zh.md').write_text('\n'.join(lines),encoding='utf-8')
    j.save(OUT/'execution.json',{'utc':j.now(),'argv':[sys.executable,'scripts/cce_analyze_output_identity_v2.py'],
        'cwd':str(ROOT),'status':'completed','new_requests':0,'script_sha256':j.filehash(__file__),
        'summary_sha256':j.filehash(OUT/'completion_summary.json')})
    print(j.canonical(summary))


if __name__=='__main__':main()
