"""Freeze evaluator and analysis rules before releasing the eight selected answers."""
import sys,json
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
ROLE=R3/'standalone_fluor_role'
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT),str(ROLE)]
import cce_round3_runner_v2 as runner
import cce_canonical_source_candidate_v1 as candidate
import cce_canonical_components_v1 as processor
import cce_posthoc_role_scope_v4 as role_scoring
import applicability_semantics_v3 as applicability

meta=runner.j.read(R3/'confirmation_metadata_freeze.json')
assert meta['selected_count']==8 and meta['answer_bodies_released'] is False
assert runner.j.filehash(R3/'confirmation_metadata_freeze.json')=='47173ac52f2e8ca9f62dd77986500bb0ed08cd6a9cd721a00fa889044b9a1ec5'
primary,_,_,_=runner.validate(R3/'E2_canonical_qwen_01')
reviews=[ROLE/'independent_v4_review_01'/folder/'review.json' for folder in ['fixtures_01','integrated_01','history_01']]
for p in reviews:
    assert p.is_file()
paths=runner.dependencies(candidate,processor,role_scoring,runner.base,runner.budget)
paths += [Path(applicability.__file__),R3/'E2_canonical_qwen_01/model_config.json',
    R3/'confirmation_metadata_freeze.json',ROLE/'independent_v3_review_01/batch_secondary_replay_v1.py',*reviews]
paths += [Path(r['path']) for r in primary['frozen_inputs'] if 'KnowledgeBase' in r['path'] or Path(r['path']).name=='demand_vectors_all.json']
record={
    'created_utc':runner.j.now(),'status':'configuration_and_analysis_frozen_before_selected_body_release',
    'selection':runner.bind(R3/'confirmation_metadata_freeze.json'),
    'selected_answers':8,'tasks':[1,2,23,248],'requests':8,'repeats_per_answer':1,
    'candidate':'cce_canonical_source_candidate_v1','processor':'cce_canonical_components_v1',
    'public_model':primary['public_model'],
    'secondary_role_module':'cce_posthoc_role_scope_v4','secondary_applicability_module':'applicability_semantics_v3',
    'original_metric_functions_and_raw_SRSP':True,
    'answer_body_release_authorized_after_this_record':True,
    'development_use_after_release':False,
    'new_confirmatory_outcomes_cannot_change_this_configuration':True,
    'scientific_reference_selection':'reuse frozen applicable method-family candidates; original full-version max SR then SP tie rule; report candidates and selected source version',
    'reuse_steps':'reuse only identical answer/question/reference/config; otherwise evaluate original full answer using original fixed encoder and threshold',
    'analysis':{
        'technical_success':'complete provider plus full conversion, independently of numeric CCE completeness',
        'numeric_completeness':'report every planned answer, each available metric and exact missing-component reason',
        'primary_secondary':'all original primary outputs retained; secondary s_label/Eff/IA/HV changes separately identified',
        'joint_model_comparison':'Claude Sonnet 4.6 and Qwen3 Max share only q23 and q248; other answers remain per-answer results',
        'common_tasks':'use the actual common complete set, with all planned-task coverage shown; no unmatched-task aggregate ranking',
        'partial_results':'reuse fixed interval arithmetic for bounded unknown components, explicitly identified as bounds not confidence intervals or filled scores',
        'Pareto':'Com,Cor,Eff maximized; exact observed nondominance only on a declared common support',
        'resampling':'if two common tasks have complete joint scores, enumerate all four ordered task-cluster draws and compare the fixed-seed 2000-draw descriptive sensitivity; one task is degenerate; zero tasks means not estimable',
        'independent_unit':'task, not answer, metric, generated sample or bootstrap draw',
        'single_repeat_limitation':'no evaluator repeatability estimate from these eight singleton calls',
        'expert_validation':'pending within the original one-expert 5 development plus 15 holdout budget',
        'scope':'prospective answer-level within registered exclusions on exposed task/source families; not an independent family holdout',
    },
    'bindings':[runner.bind(p) for p in dict.fromkeys(paths)],
    'new_model_calls':0,'new_answer_bodies_read_by_this_command':0,
    'actual_command':[sys.executable,*sys.argv],
}
runner.save_once(R3/'confirmation_configuration_freeze.json',record)
print(json.dumps({'status':record['status'],'bindings':len(record['bindings']),'new_model_calls':0}))
