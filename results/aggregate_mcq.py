"""Aggregate per-model MCQ checkpoints into the released statistics file."""

import json
import re
from pathlib import Path


CHECKPOINT_DIR = Path("dataset/MCQ/model_response")
OUTPUT_FILE = Path("results/mcq_stats_20260222.jsonl")

MCQ_DIMENSION_MAPPING = {
    "Tissue Features & Labeling Sites": "Tissues & Markers (Tissue/Site)",
    "Marker Features & Targets": "Tissues & Markers (Marker/Target)",
    "Reagent Names & Abbreviations": "Reagents (Name/Abbr)",
    "Reagent Functions & Applications": "Reagents (Func/App)",
    "Method Names & Categories": "Method (Name/Cat)",
    "Method Characteristics & Applications": "Method (Char/App)",
    "Method Selection": "Method (Selection)",
    "Protocol Steps & Parameters": "Method (Protocol/Param)",
    "Full-Process Design": "Method (Full Design)",
}


def resolve_repo_path(path: Path) -> Path:
    """Resolve an artifact path when called from the repository root or results/."""
    for candidate in (path, Path("..") / path):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Artifact path not found: {path}")


def extract_answer(text):
    """Extract an A-H answer choice from a model's response."""
    if not text:
        return None
    patterns = (
        r"\[([A-H])\]",
        r"\(([A-H])\)",
        r"The answer is ([A-H])",
        r"选项([A-H])",
        r"^([A-H])$",
        r"(?i)answer:?\s*([A-H])",
        r"([A-H])是正确选项",
        r"([A-H]) is correct",
    )
    for pattern in patterns:
        match = re.search(pattern, str(text))
        if match:
            return match.group(1).upper()
    return None


def aggregate_checkpoint(checkpoint_file: Path):
    dimension_stats = {
        label: {"correct": 0, "total": 0}
        for label in MCQ_DIMENSION_MAPPING.values()
    }
    seen_questions = set()

    with checkpoint_file.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {checkpoint_file}:{line_number}: {exc}"
                ) from exc

            question_id = entry.get("question_id")
            if question_id in seen_questions:
                continue
            seen_questions.add(question_id)

            specific = (
                entry.get("specific")
                or entry.get("knowledge_point")
                or entry.get("category")
            )
            if specific not in MCQ_DIMENSION_MAPPING:
                continue

            label = MCQ_DIMENSION_MAPPING[specific]
            counts = dimension_stats[label]
            counts["total"] += 1
            if extract_answer(entry.get("solution", "")) == entry.get("answers"):
                counts["correct"] += 1

    if not sum(counts["total"] for counts in dimension_stats.values()):
        return None

    return {
        label: counts["correct"] / counts["total"] if counts["total"] else 0
        for label, counts in dimension_stats.items()
    }


def aggregate_mcq():
    checkpoint_dir = resolve_repo_path(CHECKPOINT_DIR)
    output_file = OUTPUT_FILE if Path("results").is_dir() else Path(OUTPUT_FILE.name)

    results = []
    for checkpoint_file in sorted(checkpoint_dir.glob("checkpoint_*.jsonl")):
        model = checkpoint_file.stem.removeprefix("checkpoint_")
        stats = aggregate_checkpoint(checkpoint_file)
        if stats is not None:
            results.append({"model": model, "stats": stats})

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="\n") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"Aggregated {len(results)} models -> {output_file}")


if __name__ == "__main__":
    aggregate_mcq()
