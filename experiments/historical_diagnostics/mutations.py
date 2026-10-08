"""Pure deterministic text controls extracted from the 2026-09-29 experiment.

These transformations produce textual inputs, not scientifically validated
failure labels. They do not run a model, load weights, or compute GEN scores.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

VARIANTS = (
    "identity",
    "reverse_steps",
    "duplicate_steps",
    "drop_alternating_steps",
    "multiply_parameters_by_10",
)

# Preserve the original experiment's unit vocabulary, boundaries and formatting.
PARAMETER_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)(\s*(?:°C|mL|ml|µL|μL|uL|mM|µM|μM|"
    r"minutes?|mins?|hours?|hrs?|seconds?|secs?|%|×g))(?=\b|\s|[.,;)]|$)",
    re.IGNORECASE,
)


def mutate_steps(steps: Sequence[str], variant: str) -> dict[str, Any]:
    """Return a new prediction plus edit metadata; leave ``steps`` unchanged.

    ``parameters_changed`` here counts numerical replacements in this variant.
    Historical metric fixtures repeat the reference's regex-hit annotation in
    every variant; see their ``legacy_parameter_annotation`` field.
    """
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise TypeError("steps must be a sequence of strings")
    if any(not isinstance(step, str) for step in steps):
        raise TypeError("every step must be a string")
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant!r}")

    reference = list(steps)
    replacements = 0
    if variant == "identity":
        prediction = reference.copy()
    elif variant == "reverse_steps":
        prediction = reference[::-1]
    elif variant == "duplicate_steps":
        prediction = reference + reference
    elif variant == "drop_alternating_steps":
        prediction = reference[::2]
    else:

        def replace(match: re.Match[str]) -> str:
            nonlocal replacements
            replacements += 1
            return f"{float(match[1]) * 10:g}" + match[2]

        prediction = [PARAMETER_PATTERN.sub(replace, step) for step in reference]

    return {
        "prediction": prediction,
        "parameters_changed": replacements,
        "text_changed": prediction != reference,
    }


def all_variants(steps: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Build all five controls without inference or metric computation."""
    return {variant: mutate_steps(steps, variant) for variant in VARIANTS}
