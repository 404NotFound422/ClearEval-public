"""Offline input binding and provenance for reproducible OEQ grading."""
import copy
import hashlib
import json
import math
from pathlib import Path

SCORING_VERSION = "cleareval-fixed-demand-v4-marker-identity"
TIME_POLICY = "kb-window-asymmetric-median-0.20-under-0.10-over-v1"
DEMAND_AXES = (
    "fluorescence_protein_preservation", "dye_permeability", "clearing_challenge",
    "geometry_preference", "operational_economy", "safety_compatibility",
)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class FixedDemandRegistry:
    """Bind the existing demand table to an explicit, immutable question snapshot.

    A binding records reproducibility, not expert approval of its scientific values.
    New/revised questions require their own reviewed vectors and binding manifest.
    """
    def __init__(self, question_file, demand_file, manifest_file=None):
        manifest_file = manifest_file or str(demand_file) + ".manifest.json"
        manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
        questions = json.loads(Path(question_file).read_text(encoding="utf-8"))
        self.vectors = json.loads(Path(demand_file).read_text(encoding="utf-8"))
        if manifest.get('hash_format') != 'canonical-json-sha256-v1':
            raise ValueError('Demand manifest must declare hash_format=canonical-json-sha256-v1')
        # Stable across JSON whitespace and Windows/Linux checkout line endings.
        self.provenance = {"questions_sha256": json_hash(questions),
                           "demand_vectors_sha256": json_hash(self.vectors),
                           "hash_format": 'canonical-json-sha256-v1',
                           "demand_manifest_sha256": sha256_file(manifest_file)}
        for field in ("questions_sha256", "demand_vectors_sha256"):
            if manifest.get(field) != self.provenance[field]:
                raise ValueError(f"Fixed-demand version mismatch: {field}. Use the question snapshot "
                                 "bound in the manifest, or audit revised vectors and create a new binding.")
        self.questions = {str(q["question_id"]): q for q in questions}
        if len(self.questions) != len(questions):
            raise ValueError("Duplicate question IDs in the selected snapshot")
        if self.questions.keys() != self.vectors.keys():
            raise ValueError("Question IDs and fixed-demand IDs do not match")
        for qid, vector in self.vectors.items():
            for axis in DEMAND_AXES:
                for field in ("target", "weight"):
                    try:
                        value = vector[axis][field]
                        if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
                            raise ValueError("invalid numeric value")
                    except (KeyError, TypeError, ValueError):
                        raise ValueError(f"Invalid demand value: question {qid}, {axis}.{field}") from None
        self.provenance["binding_note"] = manifest.get("binding_note", "")

    def get(self, qid, question_text):
        question = self.questions.get(str(qid))
        if question is None or question["question"] != question_text:
            raise ValueError(f"Question {qid} text does not match the selected snapshot; "
                             "question_id alone is not a valid cache key.")
        return copy.deepcopy(self.vectors[str(qid)])


def ensure_manifest(output_path, contract):
    """Refuse to append to unversioned or incompatible files. Never overwrite them."""
    manifest_path = Path(str(output_path) + ".manifest.json")
    digest = json_hash(contract)
    expected = {"contract_sha256": digest, "contract": contract}
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if saved != expected:
            raise ValueError(f"Run manifest mismatch: {manifest_path}. Select a new output directory.")
    elif Path(output_path).exists():
        raise ValueError(f"Unversioned output already exists: {output_path}. Select a new output directory.")
    else:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return digest


def time_score_details(actual, row, tier):
    """Score and explain the same KB window. Preserve the established asymmetric rule."""
    details = {"policy": TIME_POLICY, "source": "time_kb.json", "requested_tier": tier,
               "actual_hours": actual, "min_hours": None, "max_hours": None,
               "median_hours": None, "tau_hours": None, "delta_hours": None,
               "tau_under_fraction": 0.20, "tau_over_fraction": 0.10}
    if not row:
        return 0.0, {**details, "status": "missing_kb"}
    try:
        low, high, median = (float(row[key]) for key in
                             ("clearing_time_min_h", "clearing_time_max_h", "clearing_time_median_h"))
    except (KeyError, TypeError, ValueError):
        return 0.0, {**details, "status": "invalid_kb"}
    if not all(math.isfinite(v) for v in (low, high, median)) or not 0 <= low <= median <= high or median <= 0:
        return 0.0, {**details, "status": "invalid_kb"}
    details.update(min_hours=low, max_hours=high, median_hours=median)
    if not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual <= 0:
        # Keep the legacy numerical score, but explicitly distinguish extraction failure.
        details["actual_hours"] = actual if isinstance(actual, (int, float)) and math.isfinite(actual) else None
        return 0.0, {**details, "status": "missing_or_invalid_time"}
    delta = max(low - actual, actual - high, 0.0)
    tau = (0.10 if actual > high else 0.20) * median
    score = 3.0 * math.exp(-0.5 * (delta / tau) ** 2)
    return score, {**details, "status": "scored", "delta_hours": delta, "tau_hours": tau}


def time_reasoning(details):
    return (f"Time deviation score. Act: {details['actual_hours']} h; "
            f"KB Ref Range: [{details['min_hours']}, {details['max_hours']}] h; "
            f"median={details['median_hours']} h; tau={details['tau_hours']} h; "
            f"delta={details['delta_hours']} h; tier={details['requested_tier']}; "
            f"status={details['status']}; policy={details['policy']}")
