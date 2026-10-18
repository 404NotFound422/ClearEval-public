"""Presentation-only score provenance. Never computes or replaces adopted scores."""
from copy import deepcopy

VERSION = 'adopted-effectiveness-lineage-v1-20261015'


def build_score_lineage(scores, native, label_audit, projection, preferences, model_space):
    """Keep native legacy diagnostics separate from the practical adopted outputs."""
    identity = native.get('method_identity', {})
    method = identity.get('resolved_key')
    quantitative = projection['quantitative_data']
    time = native.get('time_computation', {})
    components = {}
    for key, score in scores.items():
        value = score['score']
        minimum = -2.5 if key == 's_method' else 0
        components[key] = {
            'adopted_path': ('oeq_practical_scoring.label_effectiveness' if key == 's_label'
                             else 'OEQ_run_grading_new.calculate_effectiveness_score'),
            'adopted_score': value,
            'adopted_score_pointer': 'effectiveness_scores.' + key + '.score',
            'legacy_diagnostic_score': native.get(key),
            'legacy_diagnostic_pointer': 'effectiveness_input.calculation_diagnostics.' + key,
            'min_score': minimum, 'max_score': score['max_score'],
            'normalization_formula': ('(raw_score / 2.5 + 1) / 2' if key == 's_method'
                                      else 'raw_score / max_score'),
            'unknown_reason': (score.get('missing_reason', 'Unknown; inspect source diagnostics')
                               if value is None else None),
        }
    components['s_method']['source_parameters'] = {
        'method_identity': deepcopy(identity), 'user_preference_vector': deepcopy(preferences),
        'signed_method_capabilities': deepcopy(model_space.get(method)),
        'formula': '2.5 * sum(effective_demand * signed_capability) / sum(effective_demand), rounded to 4 decimals',
        'demand_rule': 'target * weight; stronger FP/dye axis doubled, other zeroed; geometry target capped at 1',
        'interpretation': 'Signed frozen-table task fit; negative is allowed, not an invalid score or a correctness-judge verdict',
    }
    components['s_trans']['source_parameters'] = {
        k: deepcopy(v) for k,v in native.items() if k.startswith('_s_trans_')}
    components['s_trans']['interpretation'] = 'Benchmark RI reference proxy, not measured transparency; reported solution RI is not substituted'
    for key in ('s_time', 's_trans'):
        components[key]['score_qualification'] = scores[key].get('score_qualification')
        components[key]['scientific_score_status'] = scores[key].get('scientific_score_status')
        components[key]['display_label'] = scores[key].get('display_label')
    components['s_time']['source_parameters'] = deepcopy(time)
    components['s_time']['input_scope'] = quantitative.get('time_scope')
    components['s_time']['scope_totals'] = deepcopy(quantitative.get('time_scope_totals'))
    components['s_time']['display_labels'] = {
        'score': scores['s_time'].get('display_label', 'Time diagnostic (uncalibrated reference)'), 'max_score': 'Maximum possible time score (points)',
        'actual_hours': 'Hours consumed by the scoring scope',
        'full_core_hours': 'Full core clearing hours (may differ from scoring scope)'}
    if components['s_time']['adopted_score'] is None:
        components['s_time']['unknown_reason'] = time.get('status', 'Native time lookup unavailable')
    label = components['s_label']
    label['source_parameters'] = {
        'components': deepcopy(label_audit.get('components')),
        'aggregation': label_audit.get('aggregation'),
        'specification_penalty': deepcopy(label_audit.get('specification_penalty')),
        'legacy_marker_dict': deepcopy(projection.get('marker_dict')),
        'legacy_projection_guards': deepcopy(projection.get('label_projection', {}).get('guards', [])),
        'legacy_dict_collisions': deepcopy(projection.get('label_projection', {}).get('collisions', [])),
        'legacy_components': {k:native.get(k) for k in ('s_target_match','s_marker_fluor_compat','s_method_fluor_compat')},
    }
    unknown = [k for k in ('s_target_match','s_marker_fluor_compat','s_method_fluor_compat') if native.get(k) is None]
    label['legacy_unknown_reason'] = (
        {'unavailable_legacy_components': unknown,
         'meaning': 'Legacy nullable-min lacks these inputs/lookups. This is not the adopted task-review label path.',
         'projection_records_pointer': 'effectiveness_input.label_diagnostics.projection.records'}
        if native.get('s_label') is None else None)
    if label['adopted_score'] is None:
        label['unknown_reason'] = {'unresolved_applicable_components': deepcopy(label_audit.get('assessment_coverage', {}).get('other_unknown_components', [])),
                                   'details_pointer': 'effectiveness_input.label_diagnostics.components'}
    return {'schema_version': VERSION,
            'semantics': 'Adopted scores and legacy diagnostics are distinct layers, not interchangeable snapshots',
            'legacy_compatibility_key': 'calculation_diagnostics',
            'legacy_diagnostics_unchanged': True,
            'legacy_total_is_not_adopted_total': True,
            'components': components}
