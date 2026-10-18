"""Single OEQ reporting contract. All indices are fractions in [0, 1].

Only complete, finite score rows enter a mean; failures remain in coverage.
The application index is mean(min(Com_i, Cor_i, Eff_i)), at protocol level.
"""
import math
from collections import Counter

AGGREGATION_VERSION = "oeq-mean-of-protocol-minima-v2"
METRIC_BLOCKS = {
    "completeness": {"c_step": 2, "c_param": 3},
    "correctness": {"co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1},
    "effectiveness": {"s_method": 2.5, "s_label": 6, "s_trans": 3, "s_time": 3},
}
MAX_SCORES = {key: val for block in METRIC_BLOCKS.values() for key, val in block.items()}


def protocol_scores(item):
    """Return a complete score row, or raise ValueError with the exclusion reason."""
    ev = item.get("evaluation")
    if not isinstance(ev, dict) or ev.get("_error"):
        raise ValueError("evaluation_error")
    scores = ev.get("scores", {})
    raw = {}
    for block, metrics in METRIC_BLOCKS.items():
        for key, maximum in metrics.items():
            try:
                value = scores[block][key]["score"]
                if isinstance(value, bool):
                    raise ValueError("boolean score")
                value = float(value)
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"missing_or_invalid:{key}") from None
            minimum = -maximum if key == "s_method" else 0
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"out_of_range:{key}")
            raw[key] = value
    norm = {key: value / MAX_SCORES[key] for key, value in raw.items()}
    norm["s_method"] = (norm["s_method"] + 1) / 2
    com = 0.4 * norm["c_step"] + 0.6 * norm["c_param"]
    cor = sum(norm[key] for key in METRIC_BLOCKS["correctness"]) / 4
    eff = sum(norm[key] for key in METRIC_BLOCKS["effectiveness"]) / 4
    return {"raw": raw, "Com": com, "Cor": cor, "Eff": eff,
            "I_A": min(com, cor, eff), **{key: norm[key] for key in METRIC_BLOCKS["effectiveness"]}}


def valid_protocols(items):
    """Index complete rows by question ID, excluding *all* duplicate-ID entries."""
    counts = Counter(str(item.get("question_id")) for item in items)
    valid, excluded = {}, []
    for index, item in enumerate(items):
        qid = item.get("question_id")
        key = str(qid)
        try:
            if qid is None:
                raise ValueError("missing_question_id")
            if counts[key] != 1:
                raise ValueError("duplicate_question_id")
            valid[key] = protocol_scores(item)
        except ValueError as exc:
            excluded.append({"index": index, "question_id": qid, "reason": str(exc)})
    return valid, excluded


def aggregate_items(items):
    items = items if isinstance(items, list) else [items]
    valid, excluded = valid_protocols(items)
    rows = list(valid.values())
    n = len(rows)
    averages = {}
    for key, maximum in MAX_SCORES.items():
        avg = math.fsum(row["raw"][key] for row in rows) / n if n else None
        averages[key] = avg
        # Preserve the historical signed _norm field for existing dimension plots.
        averages[key + "_norm"] = avg / maximum if avg is not None else None
    indices = {key: math.fsum(row[key] for row in rows) / n if n else None
               for key in ("Com", "Cor", "Eff", "I_A", *METRIC_BLOCKS["effectiveness"])}
    indices["I_A_min_of_means"] = min(indices[key] for key in ("Com", "Cor", "Eff")) if n else None
    return {
        "aggregation_version": AGGREGATION_VERSION,
        "average_scores": averages,
        "indices": indices,
        "application_index": indices["I_A"],
        "sample_count": n,
        "total_items": len(items),
        "coverage": n / len(items) if items else 0.0,
        "excluded_items": excluded,
    }


def paired_deltas(baseline, treatment):
    """Mean treatment-minus-baseline on the same valid IDs, in percentage points."""
    base, _ = valid_protocols(baseline)
    changed, _ = valid_protocols(treatment)
    common = sorted(base.keys() & changed.keys())
    # A reused ID is not enough to establish a matched scenario after a stem revision.
    base_meta = {str(item.get('question_id')): item.get('evaluation', {}).get('meta_data', {})
                 for item in baseline if isinstance(item.get('evaluation'), dict)}
    changed_meta = {str(item.get('question_id')): item.get('evaluation', {}).get('meta_data', {})
                    for item in treatment if isinstance(item.get('evaluation'), dict)}
    for qid in common:
        for field in ('sample_info', 'question_sha256'):
            left, right = base_meta[qid].get(field), changed_meta[qid].get(field)
            if left is not None and right is not None and left != right:
                raise ValueError(f'Cannot pair question {qid}: {field} differs between conditions')
    return {
        "n_paired": len(common),
        **{"d_" + key: 100 * math.fsum(changed[qid][key] - base[qid][key] for qid in common) / len(common)
           if common else None for key in ("I_A", "s_label")},
    }
