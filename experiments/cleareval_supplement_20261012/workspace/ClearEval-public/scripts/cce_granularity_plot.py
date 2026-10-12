"""Plot the existing three paired granularity diagnostics; no model calls."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/cce_validation"
METRICS = ("SR", "SP", "Com", "Eff", "IA", "HV")
COLORS = ("#0072B2", "#D55E00", "#009E73")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def delta_label(value):
    if value == 0:
        return "0"
    if abs(value) < 0.0001:
        return f"{value:+.2e}"
    return f"{value:+.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ART / "judges/local_granularity/paired_results.json")
    parser.add_argument("--output", type=Path, default=ART / "figures/granularity_sensitivity")
    args = parser.parse_args()
    source = args.input.resolve()
    paths = [source, source.with_suffix(".csv"), source.parent / "summary_granularity.json",
             source.parent / "per_case_results.json", source.parent / "reuse_manifest.json"]
    hashes = {str(path): digest(path) for path in paths}
    pairs = sorted(load(source), key=lambda row: row["question_id"])
    summary = load(paths[2])
    cases = {row["case_id"]: row for row in load(paths[3])}
    reuse = load(paths[4])["reused_trials"]
    assert len(pairs) == len({row["question_id"] for row in pairs}) == 3
    assert summary["new_actual_requests_this_stage"] == 3
    assert summary["reused_actual_baseline_observations"] == len(reuse) == 3
    assert all(row["identity_unchanged"] and row["full_text_reference_and_judge_config_match"] for row in reuse)
    assert {row["judge"] for row in cases.values()} == {"local_qwen3_8b"}
    assert len({row["reference_id"] for row in cases.values()}) == 1
    assert all(row["formal_eligible"] is False for row in cases.values())
    source_csv = {int(row["question_id"]): row for row in csv.DictReader(source.with_suffix(".csv").open(encoding="utf-8-sig", newline=""))}
    plotted = []
    for pair in pairs:
        for key in ("baseline_reused", "same_judge_configuration", "same_step_configuration", "same_references",
                    "operation_sequence_and_parameters_verbatim_preserved"):
            assert pair[key] is True, key
        baseline, variant = cases[pair["baseline_case_id"]], cases[pair["variant_case_id"]]
        assert baseline["trial_id"] == pair["baseline_trial_id"] and variant["trial_id"] == pair["variant_trial_id"]
        for key in ("references_sha256", "judge_contract_sha256", "step_config_sha256"):
            assert baseline[key] == variant[key], key
        for metric in METRICS:
            b, v, delta = (pair[prefix + metric] for prefix in ("baseline_", "variant_", "delta_"))
            assert all(isinstance(value, (int, float)) and math.isfinite(value) for value in (b, v, delta))
            assert math.isclose(v - b, delta, abs_tol=1e-12)
            assert math.isclose(float(source_csv[pair["question_id"]]["delta_" + metric]), delta, abs_tol=1e-12)
            assert baseline[metric] == b and variant[metric] == v
            plotted.append({
                "question_id": pair["question_id"], "metric": metric, "baseline": b, "merged": v, "delta": delta,
                "baseline_case_id": pair["baseline_case_id"], "variant_case_id": pair["variant_case_id"],
                "baseline_trial_id": pair["baseline_trial_id"], "variant_trial_id": pair["variant_trial_id"],
                "baseline_entries": pair["baseline_generated_n"], "merged_entries": pair["variant_generated_n"],
                "baseline_reused": True, "new_requests_for_pair": 1, "same_judge_configuration": True,
                "same_step_configuration": True, "same_references": True,
                "operation_sequence_and_parameters_verbatim_preserved": True,
                "judge": "local_qwen3_8b", "reference_id": baseline["reference_id"],
                "scope": pair["scope"], "scientific_confirmation": pair["scientific_confirmation"],
                "formal_eligible": False, "input_sha256": hashes[str(source)],
            })

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 11, "axes.labelsize": 10,
                         "xtick.labelsize": 9, "ytick.labelsize": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "svg.fonttype": "none"})
    fig, axes = plt.subplots(2, 3, figsize=(11.4, 7.6), sharey=True)
    fig.subplots_adjust(left=.085, right=.98, bottom=.245, top=.82, hspace=.42, wspace=.20)
    fig.suptitle("Adjacent-entry merging: sensitivity of evaluation scores", x=.085, y=.97,
                 ha="left", fontsize=15, fontweight="bold")
    fig.text(.085, .917, "Development diagnostic: 3 Gemini Pro answers, 1 source family; local Qwen3-8B evaluator", fontsize=10)
    fig.text(.085, .883, "3 new full-text calls + 3 exactly reused baseline observations; identical judge, step and reference settings", fontsize=9)
    labels = [f"q{row['question_id']}\n{row['baseline_generated_n']} → {row['variant_generated_n']} entries" for row in pairs]
    for panel, (ax, metric) in enumerate(zip(axes.flat, METRICS)):
        ax.axhline(0, color="#666666", linewidth=.8)
        for index, (row, color) in enumerate(zip(pairs, COLORS)):
            value = row["delta_" + metric]
            ax.vlines(index, 0, value, color=color, linewidth=2)
            ax.scatter(index, value, color=color, marker=("o", "s", "^")[index], s=50, zorder=3)
            negative = value < -0.0001
            ax.annotate(delta_label(value), (index, value), xytext=(10, 0) if negative else (0, 9),
                        textcoords="offset points", ha="left" if negative else "center",
                        va="center" if negative else "bottom", fontsize=9, color="#222222")
        ax.set_title(f"{chr(65 + panel)}  {metric}", loc="left", fontweight="bold")
        ax.set_xticks(range(3), labels)
        ax.set_xlim(-.45, 2.45)
        ax.set_ylim(-.30, .205)
        ax.set_yticks([-.25, -.125, 0, .125])
        ax.grid(axis="y", color="#DDDDDD", linewidth=.6)
        ax.set_axisbelow(True)
        if panel % 3 == 0:
            ax.set_ylabel("Merged − baseline")
    fig.text(.085, .155, "Each point is one paired answer; all panels use the same delta scale. Tiny nonzero changes are annotated explicitly.", fontsize=9)
    fig.text(.085, .117, "Operation sequence and parameter text are unchanged. Score changes measure representation/evaluation sensitivity.", fontsize=9)
    fig.text(.085, .079, "No quality improvement claim; no expert or wet-lab validation. SP invariance was not a prespecified hypothesis.", fontsize=9)
    fig.text(.085, .041, "Source: judges/local_granularity/paired_results.json; development reference applicability remains pending.", fontsize=8)

    prefix = args.output.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(prefix.with_suffix("." + extension), dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    with prefix.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(plotted[0]))
        writer.writeheader()
        writer.writerows(plotted)
    assert hashes == {str(path): digest(path) for path in paths}
    run = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": subprocess.list2cmdline([sys.executable, *sys.argv]),
        "script_sha256": digest(Path(__file__)), "inputs": hashes,
        "rows": len(plotted), "paired_answers": 3, "source_family_n": 1,
        "new_requests_in_source_stage": 3, "exactly_reused_observations": 3,
        "model_requests_from_plotting": 0, "formal_eligible": False,
        "metric_summary": {metric: {"mean_delta": math.fsum(row["delta_" + metric] for row in pairs) / 3,
                                    "changed_pairs": sum(abs(row["delta_" + metric]) > 1e-12 for row in pairs)} for metric in METRICS},
        "checks": {"input_json_csv_and_case_values_agree": True, "paired_delta_arithmetic": True,
                   "matching_configuration_and_reference_hashes": True, "exact_reuse_manifest_verified": True,
                   "source_inputs_unchanged": True, "visual_qa": "pending_view_image"},
        "figure_files": {extension: {"path": str(prefix.with_suffix("." + extension)),
                                     "sha256": digest(prefix.with_suffix("." + extension))} for extension in ("png", "svg", "pdf", "csv")},
    }
    save(prefix.with_name(prefix.name + "_run.json"), run)
    print(json.dumps(run["metric_summary"], indent=2))


if __name__ == "__main__":
    main()
