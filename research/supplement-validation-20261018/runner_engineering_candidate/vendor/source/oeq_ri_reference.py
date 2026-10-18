"""Versioned benchmark RI reference policy; never an experimental measurement.

The unknown-sample constant is a user-selected scoring convention. Known keys
and the existing whole-body proxy are resolved by the runner without changing
its keyword order or numerical difference formula.
"""
RI_REFERENCE_VERSION = 'sample-ri-reference-v2-unknown-1.6'
UNKNOWN_SAMPLE_RI_REFERENCE = 1.6


def ri_reference_policy():
    return {'version': RI_REFERENCE_VERSION,
            'unknown_sample_reference': UNKNOWN_SAMPLE_RI_REFERENCE,
            'empty_identity': 'use_unknown_sample_reference',
            'known_table_keys': 'unchanged', 'whole_body_proxy': 'unchanged',
            'interpretation': 'benchmark_reference_not_measurement',
            'comparison': 'sample_reference_vs_method_reference'}


def make_ri_reference(tissue_inferred, resolved_key, table_value=None):
    """Retain the resolver decision; do not infer any measured tissue property."""
    if resolved_key is None:
        value, status, source = UNKNOWN_SAMPLE_RI_REFERENCE, 'default_reference_1_6', 'user_selected_scoring_reference'
        reason = 'empty_sample_identity' if not tissue_inferred else 'unrecognized_sample_identity'
    else:
        value, source = table_value, 'KnowledgeBase/tissue_ri.json'
        # Preserve earlier keyword precedence: an explicit kidney keyword is
        # still a direct table lookup even if the input also says whole body.
        whole_body = resolved_key == 'kidney' and '全身' in tissue_inferred and '肾' not in tissue_inferred
        status = 'whole_body_proxy' if whole_body else 'table_reference'
        reason = 'existing_whole_body_kidney_proxy' if whole_body else 'existing_keyword_table_lookup'
    return {'version': RI_REFERENCE_VERSION, 'value': value, 'status': status,
            'resolved_key': resolved_key, 'source': source, 'reason': reason,
            'sample_identity': tissue_inferred, 'measured': False,
            'interpretation': 'benchmark_reference_not_measurement'}
