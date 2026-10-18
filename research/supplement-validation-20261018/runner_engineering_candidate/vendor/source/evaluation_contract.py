"""Offline input binding and provenance for reproducible OEQ grading."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

SCORING_VERSION = "cleareval-fixed-demand-v5-integrity"
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



class CurrentDemandRegistry:
    """Deterministic current-task projection; no expert calibration claimed.

    This profile derives values from the selected question rather than rebinding
    historical vectors. It is computed without writing data during preflight.
    """
    def __init__(self, question_file):
        from experiments.evidence_materials import demand_migration as migration
        questions = json.loads(Path(question_file).read_text(encoding="utf-8-sig"))
        self.questions = {str(q["question_id"]): q for q in questions}
        if len(self.questions) != len(questions):
            raise ValueError("Duplicate question IDs in selected snapshot")
        proposals = [migration.derive_question(q) for q in questions]
        for q, proposal in zip(questions, proposals):
            migration.validate_derivation(q, proposal)
        self.proposals = {str(p["question_id"]): p for p in proposals}
        self.vectors = {qid: p["vector"] for qid,p in self.proposals.items()}
        self.provenance = {
            "questions_sha256": json_hash(questions),
            "demand_vectors_sha256": json_hash(self.vectors),
            "requirements_proposals_sha256": json_hash(proposals),
            "derivation_code_sha256": sha256_file(migration.__file__),
            "hash_format": "canonical-json-sha256-v1",
            "demand_profile": "current-proposal",
            "numeric_scale_status": "UNCALIBRATED_PROJECTION_FOR_REVIEW",
            "review_status": "PENDING_USER_EXPERT",
            "scientific_approval": None,
            "binding_note": "Current explicit task text and metadata; original vectors unchanged.",
        }

    def get(self, qid, question_text):
        question = self.questions.get(str(qid))
        if question is None or question["question"] != question_text:
            raise ValueError(f"Question {qid} text does not match selected snapshot")
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


def time_scope_conflict(row):
    """Detect explicit contradictory KB labels, without resolving scientific timing."""
    if not isinstance(row, dict):
        return False
    excluded = row.get("time_excludes_labeling")
    if excluded is not True and not (isinstance(excluded, str) and excluded.strip().casefold() in ("yes", "true")):
        return False
    scope = row.get("time_scope")
    if not isinstance(scope, str):
        return False
    for clause in re.split(r"[;；。\n]", scope):
        positive = re.split(r"(?:不含|不包括|不包含|\bexclud(?:es|ing|ed)?\b)", clause,
                            maxsplit=1, flags=re.IGNORECASE)[0]
        if re.search(r"(?:包括|包含|including|includes?)[^;；。\n]*(?:染色步骤|标记步骤|staining|label[l]?ing)",
                     positive, re.IGNORECASE):
            return True
    return False


def time_reference_evidence_status(row):
    """Source-audit metadata only: never grants calibration or alters arithmetic.

    Applies only to exact inspected reference-row snapshots, never question IDs.
    Changed provenance or windows require a new audit; missing tables are not
    proof that evidence does not exist.
    """
    status = {
        "scientific_score_status": "DIAGNOSTIC_UNVALIDATED" if row else "UNKNOWN",
        "validated_scientific_score": None,
        "reference_evidence_status": "CALIBRATION_NOT_REVIEWED" if row else "MISSING_METHOD_TIER_REFERENCE",
        "phase_applicability_status": "UNVERIFIED",
        "scientific_failure_inference_allowed": False,
    }
    if not row:
        return status
    # Fixed reviewed runtime-row fingerprints include source, scope, window and
    # confidence. Never derive the allowlist from the currently loaded KB.
    try:
        reviewed_row = json_hash(row)
    except (TypeError, ValueError):
        return status
    if reviewed_row == "b97d5b0654c145f6fb2fddd8273449128f1253dca550761db34bbd0f769ce3a5":
        status.update(reference_evidence_status="REQUIRED_TABLE_NOT_RETRIEVED",
            source_audit="remaining_source_audit_20261015/time_ri_audit.json#Q29_TIME",
            reference_evidence_limit="FDISCO main text p10 points to Table S1; exact 500 um schedule and empirical 2/4/8 h calibration unverified.")
    elif reviewed_row == "b9b4d6b871404c623cae8f14925133ee0c2ca3aad5622fc4ef1be6940b61b5df":
        status.update(reference_evidence_status="LOW_CONFIDENCE_EXTRAPOLATION",
            phase_applicability_status="PROVISIONAL_FINAL_MODULE_INTERPRETATION",
            source_audit="remaining_source_audit_20261015/time_ri_audit.json#Q25_TIME",
            reference_evidence_limit="24/48/96 h lacks exact-sample empirical calibration; final-module scope is provisional, not source-validated.")
    return status


def time_score_details(actual, row, tier, *, actual_scope=None, scope_totals=None):
    """Score and explain the same KB window. Preserve the established asymmetric rule."""
    # The audited row is an extrapolated final-solvent-module reference, not
    # a calibrated full-core window. This metadata overlay changes no KB numbers.
    reference_scope = (row or {}).get("reference_scope")
    scope_basis = "structured_reference_scope" if reference_scope else "unstructured_reference_text"
    if ((row or {}).get("method") == "iDISCO+" and
            (row or {}).get("tier_code") == "T09_HUMAN_DENSE_CLINICAL_BLOCK"):
        reference_scope = "final_clearing_module"
        scope_basis = "time_reference_quality_audit_20261015: provisional solvent-module interpretation; exact-sample calibration unvalidated"
    if reference_scope and actual_scope != reference_scope and isinstance(scope_totals, dict):
        selected = scope_totals.get(reference_scope)
        if isinstance(selected, dict):
            _, legacy = time_score_details(actual, row, tier, actual_scope=actual_scope)
            score, aligned = time_score_details(selected.get("total_time_hours"), row, tier,
                                               actual_scope=reference_scope)
            aligned.update(input_actual_scope=actual_scope, input_actual_hours=actual,
                           scope_totals=scope_totals, scope_selection="REFERENCE_MATCHED_EXPLICIT_OPERATIONS",
                           selected_step_ids=selected.get("step_ids", []),
                           historical_unaligned_comparison=legacy)
            return score, aligned
    scope_match = ("MATCH" if actual_scope == reference_scope else "MISMATCH") if actual_scope and reference_scope else "UNVERIFIED"
    evidence_text = " ".join(str((row or {}).get(k, "")) for k in ("notes", "review_rationale", "evidence_location"))
    extrapolated = bool(re.search(r"extrapolat|外推", evidence_text, re.I))
    confidence = (row or {}).get("confidence")
    details = {**time_reference_evidence_status(row),
               "actual_scope": actual_scope or "unspecified_legacy_scope",
               "reference_scope": reference_scope or "unstructured_scope_unverified",
               "scope_match_status": scope_match,
               "reference_scope_text": (row or {}).get("time_scope"),
               "reference_scope_basis": scope_basis,
               "reference_confidence": confidence, "reference_extrapolated": extrapolated,
               "reference_source_url": (row or {}).get("source_url"),
               "scientific_calibration": "NOT_ESTABLISHED_BY_THIS_COMPUTATION",
               "policy": TIME_POLICY, "source": "time_kb.json", "requested_tier": tier,
               "actual_hours": actual, "min_hours": None, "max_hours": None,
               "median_hours": None, "tau_hours": None, "delta_hours": None,
               "tau_under_fraction": 0.20, "tau_over_fraction": 0.10}
    if not row:
        return None, {**details, "status": "missing_kb"}
    try:
        low, high, median = (float(row[key]) for key in
                             ("clearing_time_min_h", "clearing_time_max_h", "clearing_time_median_h"))
    except (KeyError, TypeError, ValueError):
        return None, {**details, "status": "invalid_kb"}
    if not all(math.isfinite(v) for v in (low, high, median)) or not 0 <= low <= median <= high or median <= 0:
        return None, {**details, "status": "invalid_kb"}
    details.update(min_hours=low, max_hours=high, median_hours=median)
    if time_scope_conflict(row):
        return None, {**details, "status": "time_scope_conflict",
                      "time_scope": row.get("time_scope"), "time_excludes_labeling": row.get("time_excludes_labeling")}
    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual < 0:
        # Missing/untrusted time is unknown, never imputed as zero-quality evidence.
        details["actual_hours"] = actual if not isinstance(actual, bool) and isinstance(actual, (int, float)) and math.isfinite(actual) else None
        return None, {**details, "status": "missing_or_invalid_time"}
    delta = max(low - actual, actual - high, 0.0)
    tau = (0.10 if actual > high else 0.20) * median
    score = 3.0 * math.exp(-0.5 * (delta / tau) ** 2)
    details.update(delta_hours=delta, tau_hours=tau, legacy_raw_score=score)
    if scope_match == "MISMATCH":
        return None, {**details, "status": "time_scope_mismatch", "score_qualification": "INCOMPARABLE_SCOPES",
                      "legacy_raw_score_use": "Historical arithmetic only; excluded from current score"}
    conditional = scope_match != "MATCH" or confidence == "low" or extrapolated
    return score, {**details, "status": "scored", "score_qualification": "CONDITIONAL" if conditional else "SCOPE_ALIGNED",
                   "conditional_reasons": (["scope_alignment_unverified"] if scope_match != "MATCH" else []) +
                       (["low_confidence_reference"] if confidence == "low" else []) +
                       (["extrapolated_reference"] if extrapolated else [])}


def time_reasoning(details):
    return (f"Time deviation score. Act: {details['actual_hours']} h; "
            f"KB Ref Range: [{details['min_hours']}, {details['max_hours']}] h; "
            f"median={details['median_hours']} h; tau={details['tau_hours']} h; "
            f"delta={details['delta_hours']} h; tier={details['requested_tier']}; "
            f"status={details['status']}; policy={details['policy']}; "
            f"scope={details.get('actual_scope')} vs {details.get('reference_scope')}; "
            f"scope_match={details.get('scope_match_status')}; qualification={details.get('score_qualification')}; "
            f"scientific_score_status={details.get('scientific_score_status')}; "
            f"reference_evidence_status={details.get('reference_evidence_status')}; "
            "not evidence of scientific success or failure")
