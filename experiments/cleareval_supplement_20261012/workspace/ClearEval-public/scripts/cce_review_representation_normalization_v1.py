"""Independent read-only audit: surface units, original cached vectors and scores.

Only the 21 exposed development control texts are parsed. No generation, embedding
inference, biological protocol edits, or holdout scientific output is performed.
"""
from __future__ import annotations
import collections
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[key]='2'
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import cce_validation as core

BASE=ROOT/'artifacts/cce_validation'
SRC=BASE/'representation_normalization_v1'
OLD=BASE/'judges/local_controls_supplement_v2'
OUT=SRC/'independent_review'
INPUTS={}


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    p=Path(path).resolve();INPUTS[str(p)]=sha(p);return p


def read(path):return json.loads(bind(path).read_text(encoding='utf-8-sig'))


def whitespace(text):return ' '.join(text.split())


def reconstruct_units(steps,pattern):
    stream=whitespace(' '.join(s['text'] if isinstance(s,dict) else s for s in steps))
    boundary=re.compile(pattern,re.ASCII)
    slices=[0,*[m.end() for m in boundary.finditer(stream)],len(stream)]
    units=[]
    for left,right in zip(slices,slices[1:]):
        chunk=stream[left:right];value=chunk.strip()
        if not value:continue
        start=left+len(chunk)-len(chunk.lstrip())
        units.append({'text':value,'normalized_stream_start':start,'normalized_stream_end':start+len(value)})
    require(whitespace(' '.join(x['text'] for x in units))==stream,'reconstructed_nonwhitespace_content_or_order_changed')
    require(all(stream[x['normalized_stream_start']:x['normalized_stream_end']]==x['text'] for x in units),'unit_offset_binding')
    return units,stream


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=read(SRC/'plan.json');execution=read(SRC/'execution.json');summary=read(SRC/'summary.json')
    for path,h in plan['inputs'].items():require(sha(bind(path))==h,'frozen_source_hash:'+Path(path).name)
    for name,h in execution['outputs'].items():require(sha(bind(SRC/name))==h,'executed_output_hash:'+name)
    require(plan['thresholds']==[.6,.7,.8] and plan['primary_threshold']==.7,'frozen_thresholds')
    cases=read(OLD/'cases.json')['cases'];references=read(OLD/'references.json')['references']
    old_steps={r['case_id']:r['step_result'] for r in read(OLD/'step_results.json')}
    old_pairs=read(OLD/'paired_results.json')
    stored_rows=read(SRC/'per_case.json');stored_pairs=read(SRC/'paired_results.json')
    stored_units={r['case_id']:r for r in read(SRC/'units.json')}
    require(len(cases)==len(stored_units)==21 and len(old_pairs)==15 and len(stored_rows)==63 and len(stored_pairs)==45,'actual_matrix_size')
    require(len({c['case_id'] for c in cases})==21 and {c['question_id'] for c in cases}=={2,21,22},'case_identity')
    ledger=BASE/'judges/request_ledger.jsonl';ledger_before=sha(ledger)
    cache_manifest={**execution['cached_vectors'],**execution['new_vectors']}
    require(len(execution['new_vectors'])==0 and len(execution['cached_vectors'])==85,'actual_cache_counts')
    cache_by_name={}
    for path,h in cache_manifest.items():
        require(sha(bind(path))==h,'saved_cache_vector_hash')
        name=Path(path).name
        if name in cache_by_name:require(sha(path)==sha(cache_by_name[name]),'duplicate_cache_filename_content_disagreement')
        cache_by_name[name]=Path(path)
    class ReadOnlyEncoder(core.Encoder):
        def __init__(self):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                super().__init__()
            self.used={}
            def never_generate(*args,**kwargs):raise AssertionError('embedding_inference_forbidden')
            self.model.encode=never_generate
        def encode(self,texts):
            values=[]
            for text in texts:
                name=core.digest([self.identity,text])+'.npy'
                require(name in cache_by_name,'required_executed_vector_not_in_manifest')
                path=cache_by_name[name];vector=self.np.load(path,allow_pickle=False)
                require(vector.shape==(768,) and self.np.isfinite(vector).all(),'invalid_saved_vector')
                self.used[str(path)]=sha(path);values.append(vector)
            return self.np.asarray(values)
    encoder=ReadOnlyEncoder()
    require(encoder.identity==read(OLD/'step_config.json')['encoder'],'original_encoder_identity')
    refs=[];ref_checks=[]
    for ref in references:
        units,stream=reconstruct_units(ref['steps'],plan['boundary_regex'])
        refs.append({**ref,'steps':units})
        check={'reference_id':ref['reference_id'],'original_step_count':len(ref['steps']),
               'reconstructed_step_count':len(units),'original_text_order_preserved':True,
               'normalized_stream_sha256':core.digest(stream)}
        expected=next(x for x in summary['reference_unit_counts'] if x['reference_id']==ref['reference_id'])
        require(check['original_step_count']==expected['before_n']==7 and check['reconstructed_step_count']==expected['after_n']==7 and
                check['normalized_stream_sha256']==expected['normalized_stream_sha256'],'seven_reference_steps_binding')
        ref_checks.append(check)
    index={(r['case_id'],r['threshold']):r for r in stored_rows};rebuilt={};case_checks=[];numeric_checks=[]
    for case in cases:
        cid=case['case_id'];raw=case['model_response'];original=core.segment(raw)
        require(core.digest(raw)==case['answer_sha256']==stored_units[cid]['full_answer_sha256'],'full_answer_hash')
        require(original==old_steps[cid]['generated_steps']==stored_units[cid]['original_segments'],'original_fulltext_segmentation_identity')
        units,stream=reconstruct_units(original,plan['boundary_regex'])
        require(units==stored_units[cid]['normalized_units'] and core.digest(stream)==stored_units[cid]['stream_sha256'],'normalized_units_and_offsets')
        require(''.join(''.join(x['text'].split()) for x in original)==''.join(''.join(x['text'].split()) for x in units),'all_nonwhitespace_characters_in_order')
        route,declared=core.selected_route(raw,refs)
        candidates=[r for r in refs if case['question_id'] in r['question_ids'] and r['route_id']==route]
        require(candidates,'applicable_reference_missing')
        rebuilt[cid]={'units':units,'stream':stream}
        case_checks.append({'case_id':cid,'original_n':len(original),'normalized_n':len(units),
                            'fulltext_hash_and_original_segments_exact':True,'all_nonwhitespace_text_and_order_preserved':True,
                            'normalized_offset_spans_exact':True,'semantic_parameter_attachment_verified':False})
        for delta in plan['thresholds']:
            candidates_scored=[(encoder.score(r,units,delta),r,n) for n,r in enumerate(candidates)]
            score,ref,_=max(candidates_scored,key=lambda x:(x[0]['sr'],x[0]['sp'],-x[2]))
            stored=index[cid,delta]
            require(all(stored[k]==v for k,v in score.items()),'original_core_cached_score_replay:'+cid)
            require(stored['reference_id']==ref['reference_id'] and stored['declared_route']==declared and
                    stored['normalized_entry_n']==len(units) and stored['original_entry_n']==len(original),'selected_source_and_nN')
            require(stored['old_primary_sr']==old_steps[cid]['sr'] and stored['old_primary_sp']==old_steps[cid]['sp'],'historical_numbers_not_replaced')
            numeric_checks.append({'case_id':cid,'threshold':delta,'reference_id':ref['reference_id'],
                'reference_n':score['reference_n'],'generated_n':score['generated_n'],'SR':score['sr'],'SP':score['sp'],
                'all_match_indices_texts_similarities_threshold_flags_gmax_exact':True})
    pairs_by={(p['pair_id'],p['threshold']):p for p in stored_pairs};pair_checks=[]
    for pair in old_pairs:
        for delta in plan['thresholds']:
            b=index[pair['baseline_case_id'],delta];v=index[pair['variant_case_id'],delta];saved=pairs_by[pair['pair_id'],delta]
            same_units=[x['text'] for x in rebuilt[b['case_id']]['units']]==[x['text'] for x in rebuilt[v['case_id']]['units']]
            same_stream=rebuilt[b['case_id']]['stream']==rebuilt[v['case_id']]['stream']
            expected={'baseline_sr':b['sr'],'variant_sr':v['sr'],'delta_sr':v['sr']-b['sr'],
                'baseline_sp':b['sp'],'variant_sp':v['sp'],'delta_sp':v['sp']-b['sp'],
                'baseline_n':b['generated_n'],'variant_n':v['generated_n'],'same_reference':b['reference_id']==v['reference_id'],
                'same_normalized_unit_texts':same_units,'same_full_normalized_stream':same_stream,
                'old_primary_delta_sr':pair['delta_sr'],'old_primary_delta_sp':pair['delta_sp']}
            require(all(saved[k]==v for k,v in expected.items()),'paired_actual_arithmetic_or_identity')
            if pair['condition']=='adjacent_entry_merge':
                require(same_units and same_stream and expected['delta_sr']==expected['delta_sp']==0 and expected['same_reference'],'merge_unit_invariance_not_reproduced')
            pair_checks.append({'pair_id':pair['pair_id'],'question_id':pair['question_id'],'condition':pair['condition'],
                'threshold':delta,**expected})
    primary=[p for p in pair_checks if p['threshold']==.7]
    by_condition={}
    for condition in sorted({p['condition'] for p in primary}):
        group=[p for p in primary if p['condition']==condition]
        by_condition[condition]={'pairs':len(group),'sr_changes':sum(abs(p['delta_sr'])>1e-12 for p in group),
                                 'sp_changes':sum(abs(p['delta_sp'])>1e-12 for p in group)}
    require(by_condition==summary['primary_by_condition'],'condition_summary_mismatch')
    require(len(encoder.used)==85,'not_all_85_executed_vectors_consumed')
    require(sha(ledger)==ledger_before,'offline_review_made_request')
    require(all(sha(p)==h for p,h in INPUTS.items()),'source_changed_during_review')
    report={'status':'pass','review_scope':'Independent software/numeric review, not expert or semantic validation.',
        'actual_original_answers':21,'underlying_development_questions':[2,21,22],
        'actual_original_pairs':15,'merge_pairs':3,'other_pairs':12,'thresholds':[.6,.7,.8],
        'cached_core_score_replays':63,'paired_arithmetic_replays':45,'references':ref_checks,
        'all_nonwhitespace_operations_and_order_preserved_for_21':True,'merge_same_units_and_scores_at_all_thresholds':True,
        'primary_by_condition':by_condition,'cached_vectors_read_and_verified':len(encoder.used),'new_vectors':0,
        'new_judge_requests':0,'expert_confirmation':False,'frozen_original_inputs_unchanged':True,
        'limitations':['Only previously exposed English surface forms in three source answers. No new independent sample.',
            'Content/order preservation applies to the operation stream already selected by the original segmenter, not all raw-answer characters or omitted headings. Original segmenter completeness is not certified.',
            'The identical merged-unit result follows from identical normalized streams and fixed splitting; it is not semantic extraction accuracy.',
            'Parameter-to-operation attachment and wider language behavior were not scientifically reviewed.',
            'No order-sensitive metric is added; deletion/parameter cases retain their actual limited responses.',
            'Old full-pipeline scores and the main/holdout segmenter were not replaced.'],
        'case_checks':case_checks,'cached_score_checks':numeric_checks,'pair_checks':pair_checks,
        'input_sha256':INPUTS,'cached_vectors_sha256':encoder.used,'ledger_sha256_before_after_review':ledger_before,
        'actual_command':[sys.executable,'scripts/cce_review_representation_normalization_v1.py'],
        'reviewer_script_sha256':sha(__file__)}
    (OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 表示归一化独立核验','',
        '结论：软件与数值核验通过，无阻断问题。这里不是专家确认，也没有恢复或修改实验方案。', '',
        '从 21 份原全文重新调用原 segmenter，独立按冻结词面边界重建单位与位置；原 segmenter 已选中操作流的全部非空白字符及顺序保持。此结论不包含原 segmenter 排除的标题/内容，也不证明原 segmenter 提取完整。两份参考各 7 步保持。读取并核对 85 个实际缓存向量，禁止新 embedding 推理；通过原 Encoder.score 复算三阈值共 63 行，匹配索引、文本、相似度、阈值标记、gmax、SR/SP 与保存结果全部一致。', '',
        '原配对总数为 15：3 个合并对和其他 12 对，三阈值共 45 行。3 个合并对的规范化单位在两侧确实相同，q2/q21/q22 分别 9/11/16 个；三阈值 SR/SP 差值均为 0。它说明这三份特定表示变化可消除，不能推断任意语言或任意写法可靠。', '',
        '其他结果均保留：主阈值中，等义表示与顺序对没有 SR/SP 变化；步骤删除仅 1/3 的 SR 改变；参数删除 SR 均不变、SP 仅 1/3 改变。参数是否正确附着操作仍待人工检查。', '',
        '[完整审计记录与输入/缓存哈希](review.json)。原主评分、judge 输出和留出没有改动；新增 judge、向量、专家标签均为 0。', '',
        '实际命令：', '', '```powershell',
        "& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_review_representation_normalization_v1.py",'```','']
    (OUT/'review.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':'pass','cases':21,'cached_scores':63,'pairs':15,'pair_threshold_rows':45,
        'cached_vectors':85,'new_vectors':0,'new_judge_requests':0,'review_sha256':sha(OUT/'review.json')},ensure_ascii=True))


if __name__=='__main__':main()
