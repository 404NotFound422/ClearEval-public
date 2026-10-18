"""Exact zero identification only; no unknown-score imputation or estimation."""
import math
from copy import deepcopy
from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import COSINE_ENDPOINT_ROUNDOFF

VERSION = 'exact-zero-aggregate-v1'
DIMENSIONS = ('Com', 'Cor', 'Eff')


def exact_zero_bound(values, bounds):
    """Identify min/product zero only on explicit finite nonnegative domains.

    Bounds are caller-proven contracts, not observations or statistical CIs.
    Reject incomplete/invalid domains even when another coordinate is zero.
    Complete inputs remain the responsibility of the existing arithmetic path.
    """
    if set(values) != set(DIMENSIONS) or set(bounds) != set(DIMENSIONS):
        raise ValueError('Expected explicit Com, Cor, Eff values and bounds')
    def number(x):
        return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)
    for key in DIMENSIONS:
        bound = bounds[key]
        if not isinstance(bound, (tuple, list)) or len(bound) != 2:
            raise ValueError('Missing finite domain: ' + key)
        low, high = bound
        if not number(low) or not number(high) or not 0 <= low <= high:
            raise ValueError('Invalid nonnegative finite domain: ' + key)
        value = values[key]
        if value is not None and (not number(value) or not low <= value <= high):
            raise ValueError('Known value outside domain: ' + key)
    unknown = [key for key in DIMENSIONS if values[key] is None]
    zeros = [key for key in DIMENSIONS if values[key] == 0]
    identified = bool(unknown and zeros)
    return {'schema_version': VERSION,
            'status': 'DERIVED_EXACT_BOUND' if identified else 'NOT_IDENTIFIED',
            'IA': 0.0 if identified else None, 'HV': 0.0 if identified else None,
            'IA_bounds': [0.0, 0.0] if identified else None,
            'HV_bounds': [0.0, 0.0] if identified else None,
            'known_zero_dimensions': zeros, 'unknown_dimensions': unknown,
            'input_bounds': deepcopy(bounds), 'inputs_imputed': False,
            'basis': 'min and product equal zero with a known exact zero and finite nonnegative remaining dimensions'}


def resolve_practical_exact_zero(calculated):
    """Narrow practical hook; never infer a nonnegative domain for unknown Com.

    Raw continuous Com may be negative. Existing compose_cce domain guards and
    all complete-input results are retained byte-for-byte as data structures.
    Cor/Eff [0,1] are enforced by compose_cce's normalized input contract.
    """
    result = deepcopy(calculated)
    values = {key: calculated[key] for key in DIMENSIONS}
    if (all(value is not None for value in values.values())
            or values['Com'] is None
            or 'Com_aggregation_domain' in calculated.get('aggregate_missing_reasons', {})):
        return result
    proof = exact_zero_bound(values, {'Com': [0, 1 + 0.4 * COSINE_ENDPOINT_ROUNDOFF],
                                     'Cor': [0, 1], 'Eff': [0, 1]})
    if proof['status'] == 'DERIVED_EXACT_BOUND':
        if calculated['IA'] is not None or calculated['HV'] is not None:
            raise ValueError('Partial-input aggregate already has a point value')
        result.update(IA=proof['IA'], HV=proof['HV'], aggregate_resolution=proof)
        # Preserve original missing-component reasons: identified aggregate is
        # not complete component assessment or scientific certification.
    return result
