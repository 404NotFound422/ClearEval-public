"""Original numeric scoring for a committed source-bound conversion; no judge call.

The caller must verify the frozen converter, raw-to-conversion replay, source
records and deterministic step evidence before using this adapter. Its outputs
are derived diagnostics, never raw model returns or expert validation.
"""
from __future__ import annotations
import contextlib
import io
import math
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_judges as j
import evaluator_integrity as integrity

DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']
EGES = ['s_method', 's_label', 's_trans', 's_time']
METRICS = DIRECT + EGES + ['sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']
TOL = 1e-12


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def same(a, b):
    return a is None and b is None or finite(a) and finite(b) and abs(a - b) <= TOL


def definition():
    return {
        'version': 'grounded-offline-scoring-v1',
        'method': 'unchanged original calculate_effectiveness_score and selected backend component gates',
        'Com': '.4*original_SR+.6*c_param/3',
        'Cor': 'mean(co_order/3,co_method/2,co_param/2,co_chem)',
        'Eff': 'mean((s_method/2.5+1)/2,s_label/6,s_trans/3,s_time/3)',
        'IA': 'min(Com,Cor,Eff)', 'HV': 'Com*Cor*Eff',
        'missing': 'unknown dependent components remain NA; no imputation or best-repeat selection',
        'step_reuse': 'verified full-text original SR/SP are deterministic inputs, not new judge observations',
        'technical_failure': 'retain independently verified SR/SP; judge-dependent metrics remain NA',
        'new_model_requests': 0, 'expert_truth': False, 'formal_eligible': False,
    }


def derive(components, step, technical_success):
    require(set(['sr', 'sp']) <= set(step), 'ORIGINAL_STEP_VALUES_REQUIRED')
    require(all(step[k] is None or finite(step[k]) and 0 <= step[k] <= 1 for k in ['sr', 'sp']), 'STEP_VALUE_RANGE')
    if not technical_success:
        return {key: step[key] if key in ['sr', 'sp'] else None for key in METRICS}
    values = {key: components.get(key) for key in DIRECT + EGES}
    require(all(value is None or finite(value) for value in values.values()), 'NONFINITE_COMPONENT')
    values.update(sr=step['sr'], sp=step['sp'])
    values['Com'] = .4 * values['sr'] + .6 * values['c_param'] / 3 if finite(values['sr']) and finite(values['c_param']) else None
    values['Cor'] = sum(values[key] / maximum for key, maximum in zip(DIRECT[1:], [3, 2, 2, 1])) / 4 if all(finite(values[key]) for key in DIRECT[1:]) else None
    values['Eff'] = ((values['s_method'] / 2.5 + 1) / 2 + values['s_label'] / 6 + values['s_trans'] / 3 + values['s_time'] / 3) / 4 if all(finite(values[key]) for key in EGES) else None
    joint = [values[key] for key in ['Com', 'Cor', 'Eff']]
    values['IA'] = min(joint) if all(finite(value) for value in joint) else None
    values['HV'] = math.prod(joint) if all(finite(value) for value in joint) else None
    return {key: values[key] for key in METRICS}


def runtime():
    args = SimpleNamespace(question_file=j.HIST,
        demand_file=ROOT / 'dataset/Q+AR/src/demand_vectors_all.json', demand_manifest=None)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        runner, _, registry = j.runtime(args)
    return runner, registry


def score_conversion(case, conversion, backend, step):
    """Replay original numerical functions after a caller-verified conversion."""
    ground = backend.grounded
    source = conversion['source_audit']['source_binding']
    require(source['source_id'] == ground.source_id_for_case(case), 'CONVERSION_QUESTION_ANSWER_BINDING')
    require(source['answer_sha256'] == ground.rawsha(case['model_response']), 'CONVERSION_ANSWER_BINDING')
    require(source['enumerator_version'] == ground.VERSION, 'CONVERSION_VERSION_BINDING')
    payload = conversion['legacy_runner_payload']
    require(integrity.parse_judge_object(conversion['legacy_runner_content']) == payload, 'PROJECTION_SERIALIZATION_MISMATCH')
    extraction = payload['extraction']
    require(extraction == conversion['legacy_projection']['extraction'], 'PROJECTION_EXTRACTION_MISMATCH')
    integrity.validate_legacy_extraction(extraction)
    integrity.validate_score_proposals(payload['scores'])
    runner, registry = runtime()
    demand = registry.get(case['question_id'], case['specific_question'])
    meta = runner.QUESTION_META_KB[registry.questions[str(case['question_id'])]['question_id']]
    # The unchanged original runner's extraction-to-quantitative-data mapping.
    quantitative = {'method_name': extraction['method_name'],
        'tissue_ri_value': meta.get('tissue_ri_value'),
        'total_time_hours': extraction['clearing_total_time_hours'],
        'sample_tier': meta.get('tissue_tier_code')}
    for source_key, target_key in [('reagent_ri_value', 'reagent_ri_value'),
                                  ('protocol_time_hours', 'protocol_time_hours'),
                                  ('method_stages', 'method_stages')]:
        if source_key in extraction:
            quantitative[target_key] = extraction[source_key]
    replay = runner.calculate_effectiveness_score(quantitative, demand, runner.MODEL_SPACE_SIGNED,
        extraction['marker_dict'], meta.get('marker_query_targets') or [])
    proposal_container = {'scores': {**payload['scores'],
        'effectiveness': {key: {'score': replay[key]} for key in EGES}}}
    original = j.proposals(proposal_container)
    require(all(same(original[key], replay[key]) for key in EGES), 'ORIGINAL_EGES_PROPOSAL_MAPPING')
    gated, notes = backend.gate_components(original, conversion, replay)
    values = derive(gated, step, True)
    return {'status': 'original_formula_replayed_not_scientific_validation',
        'raw_response_sha256': conversion['raw_response_sha256'],
        'source_binding': source, 'quantitative_data': quantitative,
        'user_preference_vector': demand, 'original_EGES_replay': replay,
        'raw_original_numeric_proposals': original, 'component_gated_proposals': gated,
        'component_gate_notes': notes, 'metrics': values,
        'complete_numeric_CCE': all(finite(values[key]) for key in ['Com', 'Cor', 'Eff', 'IA', 'HV']),
        'evidence_state': backend.evidence_state(conversion),
        'source_fact_acceptance': 'requires_separate_source_fact_review',
        'step_values_are_reused_not_new_judge_observations': True,
        'new_model_requests': 0, 'formal_eligible': False, 'expert_confirmed': False}
