"""Validate and aggregate distributed historical fixtures, using stdlib only."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

PACKAGE = Path(__file__).resolve().parent
FIXTURES = {
    "fixtures/selfcheck_pairs.csv",
    "fixtures/component_probes.json",
    "fixtures/gen_step_metrics.json",
    "fixtures/protocol_judgments.csv",
}
VARIANTS = (
    "identity", "reverse_steps", "duplicate_steps",
    "drop_alternating_steps", "multiply_parameters_by_10",
)
MODELS = ("qwen3:8b", "qwen3:14b")
STATES = {"SATISFIED", "VIOLATED", "UNDER_SPECIFIED", "UNRESOLVED"}
EXPECTED_COUNTS = {
    "selfcheck_pairs": 12, "component_conditions": 12, "component_unique_inputs": 11,
    "gen_reference_ids": 60, "gen_variants": 5, "gen_scoring_inputs": 300,
    "development_judge_attempts": 38, "err_attempts": 28, "total_protocol_calls": 66,
    "protocol_cases_per_model": 19, "matched_cases_per_model": 13,
    "independent_expert_labels": 0,
}


class ValidationError(ValueError):
    """A fixture violates the frozen package contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def number(value: Any, label: str, lower: float, upper: float) -> float:
    require(not isinstance(value, bool), f"{label}: boolean is not a score")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"{label}: expected a number") from exc
    require(math.isfinite(result) and lower <= result <= upper,
            f"{label}: expected a finite value in [{lower}, {upper}]")
    return result


def boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    require(value in ("True", "False"), f"{label}: expected True or False")
    return value == "True"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path, fields: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and set(reader.fieldnames) == fields,
                f"{path.name}: unexpected CSV fields")
        rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows),
            f"{path.name}: malformed CSV row")
    return rows


def verify_package(package: Path) -> dict[str, Any]:
    manifest = read_json(package / "source_manifest.json")
    require(manifest["schema_version"] == 1, "Unsupported manifest version")
    require(set(manifest["fixtures"]) == FIXTURES, "Unexpected fixture list")
    require(manifest["expected_counts"] == EXPECTED_COUNTS, "Unexpected frozen denominator contract")
    require(len(manifest["protocol_source_references"]) == 3,
            "Protocol comparison requires three source-paper references")
    for relative, recorded in manifest["fixtures"].items():
        data = (package / relative).read_bytes()
        require(len(data) == recorded["bytes"], f"{relative}: size mismatch")
        require(hashlib.sha256(data).hexdigest() == recorded["sha256"],
                f"{relative}: SHA-256 mismatch")
    for original in manifest["original_sources"]:
        identifier = original["source_id"]
        require(identifier.startswith("review_artifacts/") and "\\" not in identifier
                and ".." not in identifier.split("/"), "Invalid original-source identifier")
        require(len(original["sha256"]) == 64
                and all(c in "0123456789abcdef" for c in original["sha256"]),
                "Invalid original-source SHA-256")
    return manifest


def summarize_selfcheck(package: Path) -> dict[str, Any]:
    fields = {"pair_id", "question_id", "historical_generator", "IA_before", "IA_after",
              "change_points", "same_protocol_sha256", "actual_request_payloads_equal"}
    rows = read_csv(package / "fixtures/selfcheck_pairs.csv", fields)
    require(len(rows) == 12 and len({r["pair_id"] for r in rows}) == 12,
            "Selfcheck requires 12 distinct pairs")
    changes, identical = [], []
    for row in rows:
        require(row["question_id"].isdigit(), "Selfcheck question_id must be numeric")
        before = number(row["IA_before"], "IA_before", 0, 100)
        after = number(row["IA_after"], "IA_after", 0, 100)
        change = number(row["change_points"], "change_points", -100, 100)
        require(math.isclose(after - before, change, abs_tol=1e-9),
                f"{row['pair_id']}: difference does not match saved scores")
        same_text = boolean(row["same_protocol_sha256"], "same_protocol_sha256")
        same_request = boolean(row["actual_request_payloads_equal"], "actual_request_payloads_equal")
        require(not same_request or same_text, "Identical request requires identical protocol")
        changes.append(change)
        if same_request:
            identical.append({"pair_id": row["pair_id"], "question_id": int(row["question_id"]),
                              "change_points": change})
    counts = {"increased": sum(x > 0 for x in changes),
              "decreased": sum(x < 0 for x in changes), "unchanged": sum(x == 0 for x in changes)}
    require(counts == {"increased": 2, "decreased": 3, "unchanged": 7},
            "Unexpected historical selfcheck distribution")
    require({r["pair_id"] for r in identical} == {"PAIR_01", "PAIR_06", "PAIR_10"},
            "Unexpected identical-request pairs")
    mean = statistics.mean(changes)
    require(math.isclose(mean, 0.0034800123922753556, abs_tol=1e-12),
            "Unexpected historical selfcheck mean")
    return {"pairs": 12, **counts, "mean_change_points": mean,
            "identical_request_pairs": identical,
            "scope": "Fixed historical development pairs, one automatic evaluation per side; not causal selfcheck efficacy or success probability."}


def summarize_components(package: Path) -> dict[str, Any]:
    data = read_json(package / "fixtures/component_probes.json")
    require(data["schema_version"] == 1, "Unsupported component version")
    rows = data["records"]
    require(len(rows) == 12 and len({r["id"] for r in rows}) == 12,
            "Components require 12 distinct condition IDs")
    fingerprints = set()
    for row in rows:
        require(isinstance(row["markers"], dict) and isinstance(row["quantitative_data"], dict),
                "Component markers and quantitative_data must be objects")
        require(type(row["question_id"]) is int, "Component question_id must be an integer")
        for field, upper in [("s_target_match", 6), ("s_marker_fluor_compat", 6),
                             ("s_method_fluor_compat", 6), ("s_label", 6),
                             ("s_trans", 3), ("s_time", 3)]:
            number(row[field], f"{row['id']}.{field}", 0, upper)
        inputs = {k: row[k] for k in ("question_id", "markers", "quantitative_data")}
        fingerprints.add(json.dumps(inputs, sort_keys=True, ensure_ascii=False))
    require(len(fingerprints) == 11, "Components require 11 unique structural inputs")
    scores = {r["id"]: r["s_label"] for r in rows}
    for key, expected in {"A0": 5.1, "A1": 5.4, "A2": 6, "A3": 0, "C0": 5.4, "C1": 6}.items():
        require(math.isclose(scores[key], expected, abs_tol=1e-12), f"{key}: unexpected S_label")
    return {"conditions": 12, "unique_inputs": 11, "label_scores_out_of_6": scores,
            "scope": data["scope"],
            "condition_label_note": "Conditions preserve historical wording; a recommended target is not independently established as jointly mandatory."}


def summarize_gen(package: Path) -> dict[str, Any]:
    data = read_json(package / "fixtures/gen_step_metrics.json")
    require(data["schema_version"] == 1 and set(data["variants"]) == set(VARIANTS),
            "GEN requires the five frozen variants")
    all_ids, parameter_annotations, summary = None, None, {}
    for variant in VARIANTS:
        block = data["variants"][variant]
        rows, recorded = block["records"], block["recorded_summary"]
        require(len(rows) == 60 and len({r["id"] for r in rows}) == 60,
                f"{variant}: requires 60 distinct reference IDs")
        ids = {r["id"] for r in rows}
        require(all_ids is None or ids == all_ids, "GEN variants must use the same reference IDs")
        all_ids = ids
        annotations = {}
        for row in rows:
            number(row["step_recall"], "step_recall", 0, 1)
            number(row["step_precision"], "step_precision", 0, 1)
            require(type(row["text_changed"]) is bool, "GEN text_changed must be boolean")
            require(type(row["parameters_changed"]) is int and row["parameters_changed"] >= 0,
                    "GEN legacy parameter annotation must be a nonnegative integer")
            annotations[row["id"]] = row["parameters_changed"]
        require(parameter_annotations is None or annotations == parameter_annotations,
                "Legacy parameter annotations must agree across variants")
        parameter_annotations = annotations
        changed = [r for r in rows if r["text_changed"]]
        sr = statistics.mean(r["step_recall"] for r in rows)
        sp = statistics.mean(r["step_precision"] for r in rows)
        require(recorded["n"] == 60 and recorded["changed_n"] == len(changed),
                f"{variant}: recorded denominator mismatch")
        require(math.isclose(sr, recorded["step_recall"], abs_tol=1e-12)
                and math.isclose(sp, recorded["step_precision"], abs_tol=1e-12),
                f"{variant}: recorded mean mismatch")
        expected_changed = 0 if variant == "identity" else 37 if variant == "multiply_parameters_by_10" else 60
        require(len(changed) == expected_changed, f"{variant}: unexpected changed count")
        current = {"n": 60, "changed_n": len(changed), "step_recall": sr, "step_precision": sp}
        if changed:
            current["changed_only"] = {field: statistics.mean(r[field] for r in changed)
                                       for field in ("step_recall", "step_precision")}
            require(all(math.isclose(current["changed_only"][field], recorded["changed_only"][field], abs_tol=1e-12)
                        for field in ("step_recall", "step_precision")),
                    f"{variant}: changed-only mean mismatch")
        summary[variant] = current
    return {"reference_ids": 60, "scoring_inputs": 300, "variants": summary,
            "upstream_commit": data["upstream_commit"], "scope": data["scope"],
            "parameter_annotation": data["legacy_parameter_annotation"]}


def summarize_protocols(package: Path) -> dict[str, Any]:
    fields = {"model", "id", "family", "kind", "authored_status", "technical_status",
              "effective_status", "err_status", "err_prediction", "primary_decisive_case"}
    rows = read_csv(package / "fixtures/protocol_judgments.csv", fields)
    require(len(rows) == 38 and set(r["model"] for r in rows) == set(MODELS),
            "Protocol fixtures require two models and 38 development attempts")
    require(len({(r["model"], r["id"]) for r in rows}) == 38, "Duplicate protocol attempt")
    err_attempts, results, case_ids = 0, {}, None
    for model in MODELS:
        selected = [r for r in rows if r["model"] == model]
        ids = {r["id"] for r in selected}
        require(len(selected) == 19 and (case_ids is None or ids == case_ids),
                "Models must use the same 19 cases")
        case_ids = ids
        for row in selected:
            require(row["authored_status"] in STATES, "Unexpected development-label state")
            require(row["technical_status"] in {"COMPLETED", "INVALID_JUDGMENT"}, "Unexpected technical state")
            if row["technical_status"] == "COMPLETED":
                require(row["effective_status"] in STATES, "Completed judgment must have an effective state")
            else:
                require(row["effective_status"] == "", "Invalid judgments cannot count as scientific decisions")
            require(row["err_status"] in {"COMPLETED", "NOT_RUN"}, "Unexpected ERR state")
            require(row["err_prediction"] in {"SATISFIED", "VIOLATED"}
                    if row["err_status"] == "COMPLETED" else row["err_prediction"] == "",
                    "ERR prediction/status mismatch")
            expected_primary = row["authored_status"] in {"SATISFIED", "VIOLATED"} and row["id"] != "D05"
            require(boolean(row["primary_decisive_case"], "primary_decisive_case") == expected_primary,
                    "Matched primary set must exclude D05")
        primary = [r for r in selected if boolean(r["primary_decisive_case"], "primary")]
        negative = [r for r in primary if r["authored_status"] == "VIOLATED"]
        alternatives = [r for r in selected if r["kind"] == "valid_alternative"]
        err = [r for r in selected if r["err_status"] == "COMPLETED"]
        require(len(primary) == 13 and len(negative) == 5 and len(alternatives) == 3 and len(err) == 14,
                f"{model}: unexpected comparison denominator")
        err_attempts += len(err)
        counts = Counter(r["effective_status"] or "TECHNICAL_FAILURE" for r in selected)
        expected = {"UNRESOLVED": 14, "TECHNICAL_FAILURE": 5} if model == "qwen3:8b" else {
            "SATISFIED": 4, "VIOLATED": 1, "UNRESOLVED": 7, "TECHNICAL_FAILURE": 7}
        require(dict(counts) == expected, f"{model}: unexpected effective-state counts")
        comparisons = {}
        for label, field in [("cleareval_development", "effective_status"), ("err_same_evidence", "err_prediction")]:
            comparisons[label] = {"n": 13,
                "decisive": sum(r[field] in {"SATISFIED", "VIOLATED"} for r in primary),
                "agreement_with_authored_labels": sum(r[field] == r["authored_status"] for r in primary),
                "false_accept_in_5_authored_negatives": sum(r[field] == "SATISFIED" for r in negative)}
        results[model] = {"n": 19,
            "effective_states": {state: counts.get(state, 0) for state in ("SATISFIED", "VIOLATED", "UNRESOLVED", "TECHNICAL_FAILURE")},
            "alternative_acceptance": {"accepted": sum(r["effective_status"] == "SATISFIED" for r in alternatives), "n": 3},
            "authored_contradiction_detection": {"detected": sum(r["effective_status"] == "VIOLATED" for r in negative), "n": 5},
            "matched_13": comparisons}
    require(err_attempts == 28, "ERR requires 28 attempts")
    return {"development_judge_attempts": 38, "err_attempts": 28, "total_calls": 66,
            "models": results, "source_papers": 3, "independent_expert_labels": 0,
            "scope": "Correlated, assistant-authored development cases; ERR prompt transfer with identical supplied evidence is not an official ERR benchmark score. D05 is excluded from the 13-case primary comparison."}


def summarize(package: Path = PACKAGE) -> dict[str, Any]:
    manifest = verify_package(package)
    return {"package_id": manifest["package_id"], "fixture_integrity": "PASSED",
            "verified_fixture_files": len(FIXTURES),
            "selfcheck": summarize_selfcheck(package),
            "components": summarize_components(package),
            "gen": summarize_gen(package),
            "protocols": summarize_protocols(package),
            "limitation": "Reaggregates saved historical values. It does not rerun inference, GEN embeddings, current ClearEval scoring, or independent scientific validation."}


def text_summary(result: dict[str, Any]) -> str:
    pair, component, gen, protocol = (result[k] for k in ("selfcheck", "components", "gen", "protocols"))
    lines = [f"Fixture integrity: PASSED ({result['verified_fixture_files']} files)",
        f"Selfcheck: {pair['pairs']} pairs; {pair['increased']} increased, {pair['decreased']} decreased, {pair['unchanged']} unchanged; mean delta {pair['mean_change_points']:+.12f} / 100.",
        "Identical-request deltas: " + ", ".join(f"{r['pair_id']}={r['change_points']:+.6f}" for r in pair["identical_request_pairs"]),
        f"Components: {component['conditions']} conditions / {component['unique_inputs']} unique structural inputs; component scores only.",
        f"GEN: {gen['reference_ids']} references x 5 variants = {gen['scoring_inputs']} scoring inputs."]
    for variant, row in gen["variants"].items():
        lines.append(f"  {variant}: changed {row['changed_n']}/{row['n']}; SR={row['step_recall']:.9f}, SP={row['step_precision']:.9f}")
    lines.append(f"Protocol comparison: {protocol['development_judge_attempts']} development + {protocol['err_attempts']} ERR = {protocol['total_calls']} calls; independent expert labels=0.")
    for model, row in protocol["models"].items():
        states = row["effective_states"]
        lines.append(f"  {model}: satisfied={states['SATISFIED']}, violated={states['VIOLATED']}, unresolved={states['UNRESOLVED']}, technical_failure={states['TECHNICAL_FAILURE']} (n=19).")
        lines.append(f"    Alternatives {row['alternative_acceptance']['accepted']}/3; authored contradictions detected {row['authored_contradiction_detection']['detected']}/5; decisive CE/ERR {row['matched_13']['cleareval_development']['decisive']}/13 vs {row['matched_13']['err_same_evidence']['decisive']}/13.")
    lines.append(result["limitation"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit full JSON summary")
    args = parser.parse_args()
    try:
        result = summarize()
    except (ValidationError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) if args.json else text_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
