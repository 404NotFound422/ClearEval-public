"""Read-only E2 input/reuse audit; writes a draft design, never a frozen run."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_validation as core

BASE=ROOT/'artifacts/cce_validation'
SOURCE=BASE/'judges/controls_contract_v2'
ORIGINAL=BASE/'judges/local_controls_supplement_v2'
FIXED=BASE/'optimizer_20261010/grounded_development_v1'
OUT=BASE/'optimizer_20261010/grounded_controls_design_v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return core.read(p)
def save(name,value):core.write(OUT/name,value)
def key(c):return (int(c['question_id']),c['specific_question'],c['model_response'])

EXPECTATIONS={
 'necessary_step_deletion':{
  'baseline_kind':'natural','edit':'Remove the source-supported RI/storage module, not one atomic step.',
  'prespecified_target':'Measure original SR and Com sensitivity to reference-procedure omission; source necessity remains pending expert review.',
  'not_required':'Do not force original cosine SR to drop in all three pairs: threshold floors and residual lexical matches remain visible.',
  'additional_evidence':'Full-text grounded operation/parameter recall and component availability; v3 one-to-one coverage is a supplement only.'},
 'necessary_parameter_deletion':{
  'baseline_kind':'natural','edit':'Remove all explicit duration annotations and other duration expressions; not a single-parameter deletion.',
  'prespecified_target':'Measure original c_param sensitivity and honest time-input unavailability; retain known components and nulls.',
  'not_required':'Do not assign an invented total, force Eff to decrease when time becomes unknown, or replace c_param with a span count.'},
 'deterministic_equivalent_representation':{
  'baseline_kind':'natural','edit':'Numbered line prefixes become bullets without changing operation content.',
  'prespecified_target':'Representation invariance for unchanged source facts and original score components; document actual deviations.',
  'not_required':'Do not assume repeated model outputs are numerically identical solely because temperature is zero.'},
 'evidence_supported_order_conflict':{
  'baseline_kind':'order_canonical','edit':'Canonicalize the existing operation text, then move the RI/storage operations ahead of dehydration.',
  'prespecified_target':'Measure original co_order response under the source-supported proposed precedence; full scientific necessity remains unconfirmed.',
  'not_required':'Original row/column-max SR/SP are order-blind; do not expect or inject a decrease there.',
  'additional_evidence':'V3 monotonic alignment measures source-text order only, not a new co_order score.'},
 'adjacent_entry_merge':{
  'baseline_kind':'order_canonical','edit':'Merge adjacent entries while preserving operation text and order.',
  'prespecified_target':'Original edit manifest says measure granularity sensitivity, with no prespecified original SR/SP invariance.',
  'not_required':'Do not retroactively replace the original hypothesis with the normalized-candidate zero-delta result.',
  'additional_evidence':'Source fact/operation recall should be compared across representations; original SP denominator may change.'}}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 cases=read(SOURCE/'cases.json')['cases'];pairs=read(SOURCE/'pairs.json');fixed=read(FIXED/'cases.json')['cases'];refs=read(SOURCE/'references.json')['references']
 assert len(cases)==21 and len(pairs)==15 and len({key(c) for c in cases})==21
 assert len({c['model_response'] for c in cases})==21 and Counter(c['question_id'] for c in cases)=={2:7,21:7,22:7}
 for name in ['cases.json','pairs.json','references.json']:
  assert (SOURCE/name).read_bytes()==(ORIGINAL/name).read_bytes()
 lookup={c['case_id']:c for c in cases};matrix=[]
 for i,c in enumerate(cases,1):
  fixedmatch=[x for x in fixed if key(x)==key(c)]
  matrix.append({'position':i,'case_id':c['case_id'],'question_id':c['question_id'],'condition':c['condition'],
   'baseline_kind':'order_canonical' if 'order_canonical_baseline' in c['case_id'] else 'natural' if '__baseline__' in c['case_id'] else None,
   'question_raw_sha256':rawsha(c['specific_question']),'answer_raw_sha256':rawsha(c['model_response']),
   'reference_ids':[r['reference_id'] for r in c['references']],'references_sha256':core.digest(c['references']),
   'source_json_pointer':f'/cases/{i-1}','source_file':str(SOURCE/'cases.json'),
   'fixed_five_exact_input_match':[x['anonymous_answer_id'] for x in fixedmatch],
   'fixed_five_references_equal':all(x['references']==c['references'] for x in fixedmatch) if fixedmatch else None,
   'used_as_baseline_by':[p['pair_id'] for p in pairs if p['baseline_case_id']==c['case_id']],
   'used_as_variant_by':[p['pair_id'] for p in pairs if p['variant_case_id']==c['case_id']]})
 pairrows=[]
 for p in pairs:
  a,b=lookup[p['baseline_case_id']],lookup[p['variant_case_id']]
  assert a['references']==b['references'] and a['specific_question']==b['specific_question'] and a['question_id']==b['question_id']
  pairrows.append({**p,'baseline_kind':EXPECTATIONS[p['condition']]['baseline_kind'],
   'same_question_and_supplied_reference':True,'source_edit_binding':bind(p['source_edit_file']),
   'future_pair_contract_policy':'Both arms use the same final grounded-v2 scientific/model/prompt/projection/reference contract; no old judge return reused.'})
 scopes=[{k:r.get(k) for k in ['reference_id','route_id','family_id','question_ids','source_path','source_sha256','source_url','evidence_manifest_path','source_pages','status','formal_eligible','human_confirmation','applicability','unknown_parameters']}|{'reference_step_n':len(r['steps'])} for r in refs]
 snapshots=[Path(__file__),SOURCE/'cases.json',SOURCE/'pairs.json',SOURCE/'references.json',SOURCE/'step_config.json',SOURCE/'plan.json',
   FIXED/'cases.json',FIXED/'model_config.json',FIXED/'expected_contract.json',
   ROOT/'scripts/cce_validation.py',ROOT/'scripts/cce_judges.py',ROOT/'scripts/cce_grounded_extraction_v1.py',
   BASE/'controls/edits.json',BASE/'controls/order_conflict_edits.json',BASE/'controls/granularity_edits.json']
 reuse={'status':'draft_feasibility_not_reuse_authorization','fixed_five_models':[{k:c[k] for k in ['anonymous_answer_id','case_id','question_id','generator_model']} for c in fixed],
  'exact_full_input_candidates':sum(bool(r['fixed_five_exact_input_match']) for r in matrix),
  'only_candidate':'A02 / Gemini-Pro q21 natural baseline',
  'q2_q22_mismatch':'Fixed-five A01/A03 are Gemini-Flash; E2 uses Gemini-Pro. Same qid is not same answer.',
  'matched_A02':{'question_answer_case_id_and_references_equal':True,
    'demands':'Same qid and full question with the same frozen demand registry; final registry/config hashes must still match.',
    'opaque_source_id':'Final shared source_id_for_case(question,answer) can be identical across batches; exact emitted prompts must still be byte-compared.',
    'future_model_prompt_module_actual_result':'Not yet established by this design; final candidate not frozen here.'},
  'trial_identity_obstacle':{'runner':'grounded_development_v2.source_bound_variant embeds batch plan_sha256 and runner_script_sha256.',
    'identity':'cce_judges hashes the whole per-model contract into trial_id. A new controls wrapper/batch produces a different identity.',
    'cannot_claim':'Input equality alone does not authorize importing a trial under a new contract or changing the technical-success definition.'},
  'root_selected_policy':'21 fresh requests. No cross-batch trial reuse or reinterpretation of failures.',
  'planned_new_requests':21,'planned_reused_model_trials':0,
  'allowed_offline_reuse':'Unchanged original step references, segmentation results and embedding cache may be exactly replayed; original scientific outputs remain immutable.'}
 design={'status':'draft_not_frozen_not_executed','purpose':'Grounded-v2 public development E2 reassessment only',
  'population':{'full_texts':21,'unique_full_texts':21,'base_answers':3,'natural_baselines':3,'canonical_baselines':3,'variants':15,'pairs':15,'qids':[2,21,22],
    'why_not_18':'Three canonical baselines are separate full texts used by both order and merge comparisons; natural baselines serve the other three conditions.'},
  'model':'local_qwen27b_q8_development','num_ctx':40960,'temperature':0,'max_output_tokens':8192,'max_attempts':1,'planned_new_requests':21,
  'same_pair_configuration':'Final grounded-v2 module/schema/direct scales/EGES/KB/demands/encoder/reference scope/threshold are identical across both arms; every edited full answer is newly extracted.',
  'opaque_source_rule':'Call final grounded.source_id_for_case(case); it hashes full question + NUL + full answer, not qid/model/condition. Record real case_id outside model-visible content.',
  'model_visible_metadata_audit':['No natural/variant/condition/model/anonymous-ID labels in SOURCE_ID, prompt envelope or recall pointer IDs.',
    'Reference step/source IDs remain legitimate supplied evidence; do not strip real scientific content to hide a condition.',
    'The edited full text can inherently reveal numbering/deletion; do not modify source text to conceal real inputs.',
    'Capture the exact HTTP prompt and complete decoder schema, not only a locally predicted prompt.',
    'Logs/filenames/ledger may keep true case IDs, but must not be concatenated into the prompt.'],
  'expectations':EXPECTATIONS,
  'score_contract':{'original_step_primary':'core.score_steps on full text, original supplied FDISCO reference, all-mpnet, threshold 0.7.',
    'Com':'.4 * original_SR + .6 * (c_param / 3)','SP':'Original companion precision output; no SP term in current Com.',
    'Cor_Eff':'Original direct scales, signed method normalization, EGES functions and projection availability gates remain explicitly separate.',
    'step_v3':'Supplement-only one-to-one and monotonic source-coverage columns. Never feed them into Com/IA/HV or relabel them original SR/SP.'},
  'failure_and_denominators':'Keep all 21 answers /15 pairs. Technical failures, evidence-unresolved states and numeric availability are separate. Per-component pair deltas require both components available under the same contract; never zero-impute.',
  'formal_eligible':False,'expert_returns':0,'scientific_accuracy_claimed':False,
  'before_prepare_dependencies':['Root confirms final candidate','Final grounded-v2 module/schema/probes/plan stable','Fixed-five v2 actual terminal results and independent fact review completed','Shared opaque SOURCE_ID interface final','Independent E2 full-prompt/schema/failure/Com-boundary probes passed before generation'],
  'reviewed_inputs':[bind(p) for p in snapshots],'new_model_requests':0,'experiment_freeze_performed':False}
 save('design.json',design);save('input_identity_matrix.json',matrix);save('pair_manifest_draft.json',pairrows);save('reference_scope.json',scopes);save('reuse_feasibility.json',reuse)
 core.table(OUT/'input_identity_matrix.csv',[{k:v for k,v in r.items() if k not in ['used_as_baseline_by','used_as_variant_by']} for r in matrix])
 verification={'status':'pass','read_only_source_audit':True,'unique_full_texts':21,'pairs':15,'conditions':dict(Counter(p['condition'] for p in pairs)),
  'baseline_cases':6,'all_pairs_same_question_and_reference':True,'exact_fixed_five_input_matches':1,'planned_trial_reuse':0,'new_model_requests':0,
  'no_sealed_or_human_holdout_read':True,'no_experiment_freeze':True,'source_bindings_unchanged':all(sha(p['path'])==p['sha256'] for p in design['reviewed_inputs'])}
 save('verification.json',verification);save('actual_commands.json',[{'argv':[sys.executable,*sys.argv],'cwd':str(ROOT),'script_sha256':sha(__file__),'action':'draft_design_audit_only','new_model_requests':0}])
 lines=['# Grounded E2 设计草案，尚未冻结或生成','','21 份不同全文 = 3 份自然基线 + 3 份规范编号基线 + 15 份变体。顺序冲突与相邻合并共用规范编号基线；删除步骤、删除时间参数和等价编号使用自然基线。共 3 个基础答案，每类 3 对，共 15 对。',
 '', '| 条件 | 份数/配对 | 使用基线 | 预定检验 |','|---|---:|---|---|',
 '| RI/储存模块删除 | 3 | 自然基线 | 原 SR/Com 的参考覆盖敏感性；不强制所有阈值均下降 |',
 '| 全部时长参数删除 | 3 | 自然基线 | 原 c_param 与时长输入缺失；未知不能补零 |',
 '| 编号改项目符号 | 3 | 自然基线 | 保留事实与评分的表示不变性 |',
 '| 来源支持的顺序冲突 | 3 | 规范编号基线 | 原 co_order 响应；原 SR/SP 不含顺序约束 |',
 '| 相邻条目合并 | 3 | 规范编号基线 | 原定义为粒度敏感性，未预设原 SR/SP 必须不变 |',
 '', '固定五份开发题中仅 A02（Gemini-Pro q21）与本批自然基线的题干、答案、case ID 和参考 JSON 完全相同。A01/q2、A03/q22 为 Gemini-Flash，不能当本批 Gemini-Pro 基线复用。即使 A02 最终模型、提示和来源都一致，新批次计划及 wrapper 哈希仍进入完整合同并改变 trial ID。本轮按 root 决策预留 21 次全新请求，不导入旧成功，也不改失败定义。',
 '', '最终 SOURCE_ID 统一调用模块的 opaque 内容哈希函数，真实 case ID、模型名、baseline/variant 标签只保留在外部台账。仍须在 HTTP 实际请求中检查完整提示、recall pointer ID、decoder schema 和其他元数据入口；来源正文与合法参考信息保留原样。',
 '', '主 Com 固定为 `0.4 × 原 SR + 0.6 × c_param/3`。原 SP 单列，没有 Com 权重。Controlled v3 的一对一及单调覆盖只进补充分析，不替换原 SR，不进入 Com/IA/HV。切片参考保留 3 mm 时程与科学适用性的未知；两分支均仅覆盖清除/RI/储存范围。',
 '', '每份全文重新提取，21/15 分母保留。技术失败、证据未决、完整数值分开统计。所有数值仍是开发诊断，专家回传 0，formal 0。',
 '', '[设计](design.json) · [21 输入核对](input_identity_matrix.csv) · [15 配对](pair_manifest_draft.json) · [参考范围](reference_scope.json) · [复用可行性](reuse_feasibility.json) · [核验](verification.json)']
 (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
 print(json.dumps(verification))

if __name__=='__main__':main()
