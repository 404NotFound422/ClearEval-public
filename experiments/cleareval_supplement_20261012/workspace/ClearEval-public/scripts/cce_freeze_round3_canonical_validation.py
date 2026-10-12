"""Record the interpretation and analysis of canonical-source validation before calls."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_round3_runner_v2 as runner

R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
batch=R3/'E2_canonical_qwen_01'
plan,cases,matrix,contract=runner.validate(batch)
assert not (batch/'run').exists()
value={
    'created_utc':runner.j.now(),
    'status':'fixed_before_any_new_canonical_E2_request',
    'development_requests_completed':8,
    'development_requests_remaining':0,
    'new_E2_requests_maximum':24,
    'independent_base_task_count':3,
    'repeat_calls_per_original_answer':2,
    'source_intervention':'evaluate the complete canonical text, with frozen original-to-view character mapping',
    'primary_processor':'cce_canonical_components_v1 wrapping unchanged cce_posthoc_components_v7',
    'primary_SRSP':'original edited full text and original all-mpnet-base-v2 score at threshold 0.7',
    'not_changed':['question','references','rubric categories','numeric formulas','source-alignment note',
        'scores-first JSON property order','generation settings','original raw SR and SP'],
    'changed':['model answer-source representation','source IDs and citation offsets regenerated for the complete canonical source'],
    'outside_model_prompt':['original answer IDs and hashes','original documents','original-to-view character mapping'],
    'source_alignment_development_result':{
        'first_pair_c_param':[3,3],'first_pair_co_param':[2,1],
        'aligned_pair_c_param':[3,2],'aligned_pair_co_param':[1,1],
        'interpretation':'prompt-only source alignment did not resolve all direct-score format sensitivity; no gold score established'},
    'prior_analysis_plan':runner.bind(R3/'E2_prospective_analysis_plan_v1.json'),
    'format_invariance_interpretation':'system-level invariance conditional on content-preserving canonicalization; identical model input is constructed and is not independent evidence of intrinsic LLM format robustness',
    'same_payload_repeats':'baseline, numbering and merge produce the same model input within each task; all calls retained, not treated as independent tasks',
    'original_SRSP_implication':'original Com may differ despite equal direct metrics, because original segmentation and SR are deliberately retained',
    'deletion_analysis':'new model outcomes follow the frozen directional plan; scientific necessity remains expert pending',
    'failure_and_missingness':'keep observed values and unresolved components separately; no total-zero substitution, score override or automatic retry',
    'secondary_semantics':'source-role v4 and applicability v3, if independently verified, reported separately from the frozen primary processor',
    'new_confirmation_bodies_used':False,
    'bindings':[runner.bind(batch/'plan.json'),runner.bind(batch/'matrix.json'),
        runner.bind(R3/'canonical_source_v1/software_execution_01/checks.json'),
        runner.bind(R3/'canonical_source_v1/inputs_01/verification.json')],
    'new_model_calls_by_this_command':0,
    'actual_command':[sys.executable,*sys.argv],
}
runner.save_once(R3/'canonical_source_v1/validation_freeze.json',value)
print(json.dumps({'status':'validation_interpretation_frozen','planned_calls':24,'new_model_calls':0}))
