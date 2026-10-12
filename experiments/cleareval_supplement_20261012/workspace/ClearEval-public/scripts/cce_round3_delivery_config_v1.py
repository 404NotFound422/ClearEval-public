"""Snapshot the executed round configuration and budget; no model requests."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_round3_runner_v2 as runner
import cce_round3_budget as budget

R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'


def main(args):
    out = Path(args.out).resolve()
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    conf = runner.j.read(R3 / 'confirmation_configuration_freeze.json')
    analysis = runner.j.read(R3 / 'confirmation_analysis_implementation_freeze.json')
    runner.base.verify_bindings(conf['bindings'] + analysis['bindings'])
    e2 = runner.j.read(R3 / 'E2_canonical_readout_complete_01/summary.json')
    confirm = runner.j.read(R3 / 'confirmation_readout_complete_01/summary.json')
    assert e2['observed'] == 24 and confirm['planned_answers'] == 8
    snap = budget.snapshot()
    assert snap['round_attempts'] == 40 and snap['attempts_recorded'] == 428
    assert snap['phase_attempts'] == {'development': 8, 'E2': 24, 'confirmation': 8}
    files = ['authorization.json', 'confirmation_configuration_freeze.json',
        'confirmation_analysis_implementation_freeze.json', 'E2_canonical_qwen_01/plan.json',
        'E2_canonical_qwen_01/model_config.json', 'confirmation_qwen_01/plan.json',
        'confirmation_inputs_01/source_identity_manifest.json',
        'problem_cycles/context_capacity_cycle01/adapter_freeze.json',
        'E2_canonical_readout_complete_01/summary.json', 'confirmation_readout_complete_01/summary.json']
    config = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'executed_configuration_snapshot_not_a_new_scoring_configuration',
        'execution_prompt_revision': 'r2', 'round_id': R3.name,
        'judge': conf['public_model'],
        'model_name_interpretation': 'Local alias; service family is qwen35. No independent public Qwen3.8 release identity is asserted.',
        'candidate': conf['candidate'], 'processor': conf['processor'],
        'full_answer_reparse_and_reextract': True,
        'raw_step_metrics': {'encoder': 'sentence-transformers/all-mpnet-base-v2', 'threshold': .7,
            'matching': 'independent maximum cosine similarity; no one-to-one assignment or order constraint',
            'reference_choice': 'compatible task and method-family versions; maximum SR, then SP, then fixed version order',
            'same_complete_reference_for_SR_and_SP': True, 'computed_from_original_full_answer': True,
            'canonical_judge_representation_does_not_replace_raw_SR_SP': True},
        'original_formulas': {'Com': '0.4*SR+0.6*c_param/3',
            'Cor': '(co_order/3+co_method/2+co_param/2+co_chem)/4',
            'Eff': '((s_method/2.5+1)/2+s_label/6+s_trans/3+s_time/3)/4',
            'IA': 'min(Com,Cor,Eff) per answer, then mean',
            'HV': 'Com*Cor*Eff per answer, then mean; reference point (0,0,0)'},
        'secondary': {'role_module': conf['secondary_role_module'],
            'applicability_module': conf['secondary_applicability_module'],
            'changes_only': ['s_label', 'Eff', 'IA', 'HV'], 'replaces_primary': False,
            'biological_validity': 'pending_expert_evidence'},
        'design': {'development_calls': 8, 'controlled': {'tasks': [2,21,22], 'answers': 12,
            'conditions': ['baseline','numbering','merge','necessary_step_deletion'], 'repeats': 2, 'calls': 24},
            'confirmation': {'tasks': [1,2,23,248], 'answers': 8, 'repeats': 1, 'calls': 8,
                'joint_models': ['openai_claude-sonnet-4.6','openai_qwen3-max'], 'joint_planned_tasks': [23,248],
                'scope': 'answer-level confirmation within registered exclusions; task/source families exposed'},
            'expert': {'experts': 1, 'development': 5, 'holdout': 15, 'shared_step_extraction_review': True}},
        'resampling': {'draws': 2000, 'seed': 20261011, 'independent_unit': 'task',
            'synchronous_across_models_conditions_and_repeats': True,
            'quantile': 'inverse empirical CDF', 'E2_exact_ordered_draws': 27,
            'confirmation_exact_draws': 'n^n on actual common complete support; zero means not estimable',
            'interpretation': 'descriptive sensitivity, not population confidence intervals'},
        'runtime': {'attempts_per_slot': 1, 'automatic_retries': False,
            'context_capacity': 'actual tokenizer certificate; full input preserved; R3C02 proxy-overflow decision corrected before first confirmation call'},
        'budget': snap, 'new_model_calls_by_snapshot': 0,
        'reference_qualification': 'conditional; expert scientific applicability confirmation pending',
        'overall_research_goal_complete': False,
        'source_bindings': [runner.bind(R3 / name) for name in files] + [runner.bind(__file__)]}
    # JSON is also valid YAML 1.2; avoid an extra serializer changing saved values.
    runner.save_once(out / 'resolved_config.yaml', config)
    runner.save_once(out / 'budget_snapshot.json', snap)
    runner.save_once(out / 'verification.json', {'status': 'pass', 'all_frozen_bindings_unchanged': True,
        'actual_command': [sys.executable, *sys.argv], 'new_model_calls': 0,
        'outputs': [runner.bind(out / p) for p in ['resolved_config.yaml', 'budget_snapshot.json']]})
    print(json.dumps({'status': 'pass', 'out': str(out), 'round_requests': snap['round_attempts'], 'new_model_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    main(parser.parse_args())
