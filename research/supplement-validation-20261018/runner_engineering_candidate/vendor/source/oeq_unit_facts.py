"""Literal unit facts and exact scalar equivalence; deliberately no score consumer.

Equivalence applies only to supplied quantities, not to recipe/operation identity,
scientific appropriateness, or the applicability of a source to a sample.
"""
from decimal import Decimal, localcontext
import re

VERSION = 'literal-unit-facts-v1-experimental-unvalidated'

_NUMBER = r'[+−-]?(?:\d+(?:\.\d+)?|\.\d+)'
_QUANTITY = _NUMBER + r'(?:\s*(?:[-–—]|to)\s*' + _NUMBER + r')?'
# SI concentration tokens remain case sensitive. Percent basis is never inferred.
_UNIT = (r'%(?:\s*\(?\s*(?:w/v|v/v|w/w|wt/vol|vol/vol|wt/wt)\s*\)?)?'
         r'|mg/mL|mM|M|°C|℃|K|(?i:hours?|hrs?|h|minutes?|mins?|min|seconds?|secs?|s|days?|d)')
_LITERAL = re.compile(r'(?P<quantity>' + _QUANTITY + r')\s*(?P<unit>' + _UNIT + r')(?![\w/])')
_MENTION = re.compile(r'(?<![\w.+−-])' + _LITERAL.pattern)
_SCALAR = re.compile(_NUMBER)


def _unit_identity(unit):
    if unit.startswith('%'):
        basis = re.sub(r'[\s()]', '', unit[1:])
        basis = {'wt/vol': 'w/v', 'vol/vol': 'v/v', 'wt/wt': 'w/w'}.get(basis, basis)
        return 'concentration', '%', basis or None
    if unit in {'M', 'mM', 'mg/mL'}:
        return 'concentration', unit, None
    if unit in {'°C', '℃', 'K'}:
        return 'temperature', '°C' if unit == '℃' else unit, None
    lower = unit.lower()
    canonical = ('h' if lower in {'h', 'hr', 'hrs', 'hour', 'hours'} else
                 'min' if lower in {'min', 'mins', 'minute', 'minutes'} else
                 's' if lower in {'s', 'sec', 'secs', 'second', 'seconds'} else 'd')
    return 'duration', canonical, None


def extract_unit_facts(text):
    """Additional literal facts; offsets address unchanged input, not rendering."""
    facts = []
    for match in _MENTION.finditer(text):
        # Unsupported grouped/decimal-comma numbers and fractions must not
        # become standalone endpoint facts (e.g. 1,000 mM -> 000 mM).
        # Abstain rather than infer a numeric convention or evaluate a fraction.
        prefix = text[:match.start()]
        if re.search(r'\d(?:[ \t]*[,/][ \t]*|[ \t]+)$', prefix):
            continue
        kind, unit, basis = _unit_identity(match['unit'])
        facts.append(dict(kind=kind, raw=match.group(),
                          start_in_record=match.start(), end_in_record=match.end(),
                          quantity_raw=match['quantity'], unit=unit, percent_basis=basis,
                          scalar=bool(_SCALAR.fullmatch(match['quantity'])),
                          evidence_role='LITERAL_FACT_NOT_SCIENTIFIC_CORRECTNESS'))
    return facts


def _canonical_scalar(text):
    if not isinstance(text, str):
        return None
    match = _LITERAL.fullmatch(text.strip())
    if not match or not _SCALAR.fullmatch(match['quantity']):
        return None
    kind, unit, basis = _unit_identity(match['unit'])
    value = Decimal(match['quantity'].replace('−', '-'))
    if kind != 'temperature' and value < 0:
        return None
    if unit == '%':
        return None if basis is None else ('percent:' + basis, value)
    if unit in {'M', 'mM'}:
        return 'molar', value * (1000 if unit == 'M' else 1)
    if unit == 'mg/mL':
        return 'mass_per_volume', value
    if kind == 'duration':
        return 'seconds', value * {'h': 3600, 'min': 60, 's': 1, 'd': 86400}[unit]
    kelvin = value + Decimal('273.15') if unit == '°C' else value
    return None if kelvin < 0 else ('kelvin', kelvin)


def compare_unit_values(left, right):
    """Pure, exact decimal arithmetic, no scientific tolerance or score mutation.

    Unsupported inputs and mismatched dimensions/bases are unknown/INCOMPARABLE.
    Complex ranges, operation scope, RT and overnight intentionally stay unknown.
    """
    with localcontext() as context:
        context.prec = max(50, len(str(left)) + len(str(right)) + 10)
        a, b = _canonical_scalar(left), _canonical_scalar(right)
        if a is None or b is None:
            return {'status': 'unknown', 'reason': 'UNRESOLVED_OR_UNSUPPORTED'}
        if a[0] != b[0]:
            return {'status': 'unknown', 'reason': 'INCOMPARABLE'}
        return {'status': 'equivalent' if a[1] == b[1] else 'not_equal',
                'reason': 'EXACT_UNIT_CONVERSION_ONLY'}
