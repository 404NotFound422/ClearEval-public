"""ClearEval counterfactual-validity overlay -- shared schemas (Task 1).

This module defines the data contracts for the counterfactual-validity
diagnostic suite under ``diagnostics/cleareval_cf/``.  It is stdlib-only
(no network, no third-party imports) and is intentionally *isolated*:
it never imports, reads, or modifies any production ClearEval code or
data, and nothing in it encodes ClearEval gold labels, expert labels,
mutation labels, or scorer thresholds.

Contents
--------
- Enums: ScenarioType, MutationFamily, ExpectedRelation, ComponentId,
  SeverityLevel, ReviewStatus, AdjudicationStatus, ScreeningStatus,
  EvidenceStatus, NextAction.
- Dataclasses: TextSpan, SurfaceEdit, SeedCandidate, MutationProposal,
  SplitManifest, DiagnosticAuditResult.
- (De)serialization + validation for every dataclass (``to_dict`` /
  ``from_dict`` / ``validate``), plus JSONL read/write helpers with
  schema validation on load.
- ``BlindSplitAccessError``: raised by the split guard in
  ``seed_selector.py`` when role="development" code tries to touch
  blind-listed files or seed ids.

Validation contract
-------------------
- Every ``from_dict`` call validates and raises ``ValidationError``
  (a ``ValueError`` subclass) on malformed records; a record is never
  returned partially constructed.
- ``review_status`` is enforced at schema level: ``APPROVED_GOLD``
  requires non-empty ``reviewer_ids`` **and**
  ``adjudication_status == ADJUDICATED``.  (The registry in a later
  task re-enforces this invariant; it is defined here first.)
- All records that *propose* a mutation must carry
  ``review_status = PENDING_REVIEW`` -- nothing in this suite ever
  fabricates an ``APPROVED_GOLD`` record.

Determinism note
----------------
``to_dict`` emits plain dicts; JSON output (see ``seed_selector.py``)
uses ``sort_keys=True`` + explicit UTF-8/LF so files are byte-identical
across runs.  Enum values serialize as their string ``.value``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ValidationError(ValueError):
    """Raised when a schema record fails validation."""


class BlindSplitAccessError(Exception):
    """Raised by the split guard when role="development" code attempts to
    open a blind-listed seed id or a file whose name references a
    blind-listed seed id.

    This is the hard blind-split isolation guarantee: development-role
    tools (e.g. seed/quality review) must never see blind-seed content
    before the blind set is unblinded.
    """


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScenarioType(str, Enum):
    """Question-level scenario class assigned by ``seed_selector.py``.

    - ERROR_CORRECTION: question text matches the error/correction regex
      (``错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在``).
    - COMPLEX_GENERATION: not an error-correction question and the
      marker panel has >= 4 targets.
    - SIMPLE_GENERATION: everything else.
    """

    SIMPLE_GENERATION = "SIMPLE_GENERATION"
    COMPLEX_GENERATION = "COMPLEX_GENERATION"
    ERROR_CORRECTION = "ERROR_CORRECTION"


class MutationFamily(str, Enum):
    """The six mutation families the overlay is allowed to generate."""

    REQUIRED_INFORMATION_OMISSION = "REQUIRED_INFORMATION_OMISSION"
    STEP_ORDER_OR_CHEMISTRY_CONFLICT = "STEP_ORDER_OR_CHEMISTRY_CONFLICT"
    TARGET_MARKER_MISMATCH = "TARGET_MARKER_MISMATCH"
    METHOD_FLUOROPHORE_CONFLICT = "METHOD_FLUOROPHORE_CONFLICT"
    SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT = "SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT"
    CLEARING_TIME_OUT_OF_RANGE = "CLEARING_TIME_OUT_OF_RANGE"


class ExpectedRelation(str, Enum):
    """Expected effect of a mutation on evaluator scores."""

    EQUIVALENT = "EQUIVALENT"
    DEGRADED = "DEGRADED"
    HARD_FAIL = "HARD_FAIL"


class ComponentId(str, Enum):
    """Evaluator score components that a mutation/audit finding can touch.

    COMPLETENESS/CORRECTNESS are the judge-scored axes;
    S_METHOD/S_LABEL/S_TRANS/S_TIME are the deterministic effectiveness
    axes; MULTIPLE is used when a finding spans more than one component.
    """

    COMPLETENESS = "COMPLETENESS"
    CORRECTNESS = "CORRECTNESS"
    S_METHOD = "S_METHOD"
    S_LABEL = "S_LABEL"
    S_TRANS = "S_TRANS"
    S_TIME = "S_TIME"
    MULTIPLE = "MULTIPLE"


class SeverityLevel(str, Enum):
    """Expected severity of a mutation's impact (documented convention):

    - NONE      -- expected no score impact (EQUIVALENT mutations).
    - MINOR     -- small, localized degradation (e.g. one sub-score).
    - MODERATE  -- clear degradation on one or two components.
    - CRITICAL  -- expected HARD_FAIL territory (zeroed/blocked path).
    """

    NONE = "NONE"
    MINOR = "MINOR"
    MODERATE = "MODERATE"
    CRITICAL = "CRITICAL"


class ReviewStatus(str, Enum):
    """Lifecycle status of a mutation proposal.

    PENDING_REVIEW is the ONLY status this suite ever writes; the suite
    must never fabricate APPROVED_GOLD records.  APPROVED_GOLD is
    reserved for human-reviewed manifests (see Gold guard in
    ``MutationProposal.validate``).
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED_GOLD = "APPROVED_GOLD"


class AdjudicationStatus(str, Enum):
    PENDING = "PENDING"
    ADJUDICATED = "ADJUDICATED"


class ScreeningStatus(str, Enum):
    """Lifecycle of a seed candidate before it becomes a mutation source.

    Every record emitted by ``seed_selector.py`` carries
    PENDING_SCREENING; REVIEWED is reserved for later human screening
    stages.
    """

    PENDING_SCREENING = "PENDING_SCREENING"
    REVIEWED = "REVIEWED"


class EvidenceStatus(str, Enum):
    """Evidence posture of a diagnostic audit finding."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class NextAction(str, Enum):
    """Minimal next action prescribed by a diagnostic audit finding."""

    NO_CHANGE = "NO_CHANGE"
    LOCAL_EDIT = "LOCAL_EDIT"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    BACKTRACK = "BACKTRACK"
    ABSTAIN = "ABSTAIN"


# Vocabulary shared with the selector so schema validation is strict.
CLEARING_METHOD_FAMILIES = frozenset(
    {
        "CUBIC",
        "PEGASOS",
        "iDISCO",
        "FDISCO",
        "uDISCO",
        "3DISCO",
        "DISCO",
        "MACS",
        "eFLASH",
        "CLARITY",
        "SHANEL",
        "SeeDB",
        "Scale",
        "SWITCH",
        "SOLVENT_BASED",
        "UNKNOWN",
    }
)

LABELING_REQUIREMENTS = frozenset(
    {
        "IMMUNOLABELING",
        "TRANSGENIC",
        "MIXED",
        "UNKNOWN",
    }
)

_SEED_ID_RE = re.compile(r"^SEED-\d{3}$")
# Canonical pair ids are MUT-<NNN>; the development-scoped build prefixes its
# ids DEV-MUT-<NNN> so a dev-scoped manifest can never collide with the
# canonical (blind-scope) numbering (final-review finding #2).
_PAIR_ID_RE = re.compile(r"^(?:DEV-)?MUT-\d{3,}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _enum_value(enum_cls: Any, value: Any, field_name: str) -> str:
    try:
        return enum_cls(value).value
    except (ValueError, TypeError):
        allowed = ", ".join(sorted(m.value for m in enum_cls))
        raise ValidationError(
            f"invalid {field_name}={value!r}; expected one of: {allowed}"
        )


def _enum(value: Any, enum_cls: Any, field_name: str) -> Any:
    """Return the enum member for ``value`` (str or enum member)."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        allowed = ", ".join(sorted(m.value for m in enum_cls))
        raise ValidationError(
            f"invalid {field_name}={value!r}; expected one of: {allowed}"
        )


class _Validatable:
    """Mixin: to_dict / from_dict / validate / equality helpers."""

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    def validate(self) -> None:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_Validatable":
        raise NotImplementedError

    def __eq__(self, other: Any) -> bool:
        return type(other) is type(self) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"{type(self).__name__}({self.to_dict()!r})"


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str, obj: Any, indent: Optional[int] = None) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(
            obj, fh, ensure_ascii=False, sort_keys=True, indent=indent
        )
        if indent is not None:
            fh.write("\n")


# ---------------------------------------------------------------------------
# TextSpan / SurfaceEdit
# ---------------------------------------------------------------------------


@dataclass
class TextSpan(_Validatable):
    """A byte-agnostic character span inside a protocol text.

    ``start``/``end`` are Python code-point offsets into the original or
    mutated protocol text (the same offsets both sides share when a
    mutation preserves surrounding text; the exact offset convention is
    pinned by the mutation operator in a later task).  ``text`` must
    equal the sliced substring, so the span is self-verifying.
    """

    path: str
    start: int
    end: int
    text: str

    def validate(self) -> None:
        _require(
            isinstance(self.start, int) and not isinstance(self.start, bool),
            f"span start must be an int, got {self.start!r}",
        )
        _require(
            isinstance(self.end, int) and not isinstance(self.end, bool),
            f"span end must be an int, got {self.end!r}",
        )
        _require(0 <= self.start < self.end, f"span must satisfy 0 <= start < end, got {self.start}..{self.end}")
        _require(
            len(self.text) == self.end - self.start,
            f"span text length {len(self.text)} != end-start {self.end - self.start} (path={self.path!r})",
        )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextSpan":
        _require(isinstance(data, dict), f"TextSpan must be an object, got {type(data).__name__}")
        try:
            span = cls(
                path=str(data["path"]),
                start=int(data["start"]),
                end=int(data["end"]),
                text=str(data["text"]),
            )
        except KeyError as exc:
            raise ValidationError(f"TextSpan missing field: {exc.args[0]}")
        span.validate()
        return span


@dataclass
class SurfaceEdit(_Validatable):
    """A grammaticality-only edit, recorded separately from mutations.

    Surface edits change wording/grammar but must not alter protocol
    semantics; they are never expected to change evaluator scores.
    """

    path: str
    original_text: str
    mutated_text: str
    note: str = ""

    def validate(self) -> None:
        _require(isinstance(self.path, str) and self.path, "surface_edit path must be a non-empty str")
        _require(
            isinstance(self.original_text, str) and self.original_text,
            "surface_edit original_text must be a non-empty str",
        )
        _require(
            isinstance(self.mutated_text, str) and self.mutated_text,
            "surface_edit mutated_text must be a non-empty str",
        )
        _require(
            self.original_text != self.mutated_text,
            "surface_edit must actually change the text",
        )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "path": self.path,
            "original_text": self.original_text,
            "mutated_text": self.mutated_text,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurfaceEdit":
        _require(isinstance(data, dict), f"SurfaceEdit must be an object, got {type(data).__name__}")
        try:
            edit = cls(
                path=str(data["path"]),
                original_text=str(data["original_text"]),
                mutated_text=str(data["mutated_text"]),
                note=str(data.get("note", "")),
            )
        except KeyError as exc:
            raise ValidationError(f"SurfaceEdit missing field: {exc.args[0]}")
        edit.validate()
        return edit


# ---------------------------------------------------------------------------
# SeedCandidate
# ---------------------------------------------------------------------------


@dataclass
class SeedCandidate(_Validatable):
    """A single (question x model) frozen-response pair selected as a seed.

    Fields are fully described in the selector's documentation
    (``seed_selector.py``); everything here is derived mechanically
    from the frozen data -- no gold/expert/mutation labels are used.
    """

    seed_id: str
    question_id: int
    scenario_type: ScenarioType
    source_model: str
    source_file: str
    response_text: str
    question_mode: str
    sample_tier: str
    clearing_method_family: str
    labeling_requirement: str
    n_marker_targets: int
    cce_scores: Dict[str, Any]
    screening_status: ScreeningStatus = ScreeningStatus.PENDING_SCREENING

    def validate(self) -> None:
        _require(_SEED_ID_RE.match(self.seed_id or ""), f"invalid seed_id {self.seed_id!r}; expected SEED-<NNN>")
        _require(
            isinstance(self.question_id, int) and not isinstance(self.question_id, bool),
            f"question_id must be an int, got {self.question_id!r}",
        )
        _enum(self.scenario_type, ScenarioType, "scenario_type")
        _require(isinstance(self.source_model, str) and self.source_model, "source_model must be a non-empty str")
        _require(isinstance(self.source_file, str) and self.source_file, "source_file must be a non-empty str")
        _require(
            isinstance(self.response_text, str) and self.response_text.strip(),
            "response_text must be a non-empty str",
        )
        _require(isinstance(self.question_mode, str) and self.question_mode, "question_mode must be a non-empty str")
        _require(isinstance(self.sample_tier, str) and self.sample_tier, "sample_tier must be a non-empty str")
        _require(
            self.clearing_method_family in CLEARING_METHOD_FAMILIES,
            f"invalid clearing_method_family {self.clearing_method_family!r}; expected one of {sorted(CLEARING_METHOD_FAMILIES)}",
        )
        _require(
            self.labeling_requirement in LABELING_REQUIREMENTS,
            f"invalid labeling_requirement {self.labeling_requirement!r}; expected one of {sorted(LABELING_REQUIREMENTS)}",
        )
        _require(
            isinstance(self.n_marker_targets, int) and not isinstance(self.n_marker_targets, bool),
            f"n_marker_targets must be an int, got {self.n_marker_targets!r}",
        )
        _validate_cce_scores(self.cce_scores)
        _enum(self.screening_status, ScreeningStatus, "screening_status")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "seed_id": self.seed_id,
            "question_id": self.question_id,
            "scenario_type": self.scenario_type.value,
            "source_model": self.source_model,
            "source_file": self.source_file,
            "response_text": self.response_text,
            "question_mode": self.question_mode,
            "sample_tier": self.sample_tier,
            "clearing_method_family": self.clearing_method_family,
            "labeling_requirement": self.labeling_requirement,
            "n_marker_targets": self.n_marker_targets,
            "cce_scores": _deep_sort(self.cce_scores),
            "screening_status": self.screening_status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeedCandidate":
        _require(isinstance(data, dict), f"SeedCandidate must be an object, got {type(data).__name__}")
        try:
            cand = cls(
                seed_id=str(data["seed_id"]),
                question_id=int(data["question_id"]),
                scenario_type=_enum(data["scenario_type"], ScenarioType, "scenario_type"),
                source_model=str(data["source_model"]),
                source_file=str(data["source_file"]),
                response_text=str(data["response_text"]),
                question_mode=str(data["question_mode"]),
                sample_tier=str(data["sample_tier"]),
                clearing_method_family=str(data["clearing_method_family"]),
                labeling_requirement=str(data["labeling_requirement"]),
                n_marker_targets=int(data["n_marker_targets"]),
                cce_scores=dict(data["cce_scores"]),
                screening_status=_enum(
                    data.get("screening_status", ScreeningStatus.PENDING_SCREENING.value),
                    ScreeningStatus,
                    "screening_status",
                ),
            )
        except KeyError as exc:
            raise ValidationError(f"SeedCandidate missing field: {exc.args[0]}")
        cand.validate()
        return cand


def _validate_cce_scores(cce: Dict[str, Any]) -> None:
    _require(isinstance(cce, dict), "cce_scores must be an object")
    for part in ("completeness", "correctness", "effectiveness", "total"):
        _require(part in cce, f"cce_scores missing part {part!r}")
    for part in ("completeness", "correctness", "effectiveness"):
        p = cce[part]
        _require(isinstance(p, dict), f"cce_scores.{part} must be an object")
        _require("total_weighted_score" in p, f"cce_scores.{part} missing total_weighted_score")
        _require(
            isinstance(p["total_weighted_score"], (int, float)) and not isinstance(p["total_weighted_score"], bool),
            f"cce_scores.{part}.total_weighted_score must be numeric",
        )
    _require(
        isinstance(cce["total"], (int, float)) and not isinstance(cce["total"], bool),
        "cce_scores.total must be numeric",
    )


def _deep_sort(obj: Any) -> Any:
    """Recursively sort dict keys (for stable serialization)."""
    if isinstance(obj, dict):
        return {k: _deep_sort(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_deep_sort(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# MutationProposal
# ---------------------------------------------------------------------------


@dataclass
class MutationProposal(_Validatable):
    """A proposed counterfactual mutation of a seed response.

    IMPORTANT (suite-wide rule): any manifest record that represents a
    mutation proposal must be written with
    ``review_status = PENDING_REVIEW``.  Only human-reviewed manifests
    may carry ``APPROVED_GOLD``, and even then ``reviewer_ids`` must be
    non-empty and ``adjudication_status`` must be ADJUDICATED -- the
    Gold guard below enforces this at schema level.
    """

    pair_id: str
    seed_id: str
    question_id: int
    scenario_type: ScenarioType
    mutation_family: MutationFamily
    mutation_operator_version: str
    changed_field_paths: List[str]
    original_text_spans: List[TextSpan]
    mutated_text_spans: List[TextSpan]
    surface_edits: List[SurfaceEdit]
    expected_relation: ExpectedRelation
    expected_affected_components: List[ComponentId]
    expected_location: str
    expected_severity: SeverityLevel
    supporting_rule_or_evidence_ids: List[str]
    review_status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    reviewer_ids: List[str] = field(default_factory=list)
    adjudication_status: AdjudicationStatus = AdjudicationStatus.PENDING
    # Mutated full text (persisted at build time; the span-integrity validator
    # diffs it against the seed text so undeclared edits are detected for real).
    mutated_text: str = ""
    # Human adjudication evidence (filled only by promote_to_gold; never by the
    # builder).  Kept OUT of expected_location -- a dedicated field, per the
    # final-review finding #19.
    gold_note: str = ""
    # Fallback metadata persisted on the record (mirrors the build report; the
    # validator reads it from the manifest, not from markdown prose).
    operator_fallback_used: bool = False
    operator_fallback_note: str = ""

    def validate(self) -> None:
        _require(_PAIR_ID_RE.match(self.pair_id or ""), f"invalid pair_id {self.pair_id!r}; expected MUT-<NNN> (or DEV-MUT-<NNN> for the development-scoped manifest)")
        _require(_SEED_ID_RE.match(self.seed_id or ""), f"invalid seed_id {self.seed_id!r}; expected SEED-<NNN>")
        _require(
            isinstance(self.question_id, int) and not isinstance(self.question_id, bool),
            f"question_id must be an int, got {self.question_id!r}",
        )
        _enum(self.scenario_type, ScenarioType, "scenario_type")
        _enum(self.mutation_family, MutationFamily, "mutation_family")
        _require(
            isinstance(self.mutation_operator_version, str) and self.mutation_operator_version,
            "mutation_operator_version must be a non-empty str",
        )
        _require(isinstance(self.changed_field_paths, list), "changed_field_paths must be a list")
        for span in self.original_text_spans + self.mutated_text_spans:
            _require(isinstance(span, TextSpan), "text spans must be TextSpan instances")
            span.validate()
        for edit in self.surface_edits:
            _require(isinstance(edit, SurfaceEdit), "surface_edits must be SurfaceEdit instances")
            edit.validate()
        _enum(self.expected_relation, ExpectedRelation, "expected_relation")
        _require(
            isinstance(self.expected_affected_components, list) and self.expected_affected_components,
            "expected_affected_components must be a non-empty list",
        )
        for comp in self.expected_affected_components:
            _enum(comp, ComponentId, "expected_affected_components entry")
        _require(
            isinstance(self.expected_location, str) and self.expected_location,
            "expected_location must be a non-empty str",
        )
        _enum(self.expected_severity, SeverityLevel, "expected_severity")
        _require(
            isinstance(self.supporting_rule_or_evidence_ids, list),
            "supporting_rule_or_evidence_ids must be a list",
        )
        for sid in self.supporting_rule_or_evidence_ids:
            _require(isinstance(sid, str) and sid, "supporting_rule_or_evidence_ids entries must be non-empty str")
        review = _enum(self.review_status, ReviewStatus, "review_status")
        adjudication = _enum(self.adjudication_status, AdjudicationStatus, "adjudication_status")
        _require(isinstance(self.reviewer_ids, list), "reviewer_ids must be a list")
        for rid in self.reviewer_ids:
            _require(isinstance(rid, str) and rid, "reviewer_ids entries must be non-empty str")
        # --- Gold guard (schema-level invariant) ---
        if review is ReviewStatus.APPROVED_GOLD:
            _require(
                len(self.reviewer_ids) > 0,
                "APPROVED_GOLD requires non-empty reviewer_ids (Gold records must be human-reviewed)",
            )
            _require(
                adjudication is AdjudicationStatus.ADJUDICATED,
                "APPROVED_GOLD requires adjudication_status = ADJUDICATED",
            )
        _require(
            isinstance(self.mutated_text, str),
            "mutated_text must be a str (empty when a legacy manifest omits it)",
        )
        _require(isinstance(self.gold_note, str), "gold_note must be a str")
        _require(isinstance(self.operator_fallback_used, bool), "operator_fallback_used must be a bool")
        _require(isinstance(self.operator_fallback_note, str), "operator_fallback_note must be a str")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "pair_id": self.pair_id,
            "seed_id": self.seed_id,
            "question_id": self.question_id,
            "scenario_type": self.scenario_type.value,
            "mutation_family": self.mutation_family.value,
            "mutation_operator_version": self.mutation_operator_version,
            "changed_field_paths": list(self.changed_field_paths),
            "original_text_spans": [s.to_dict() for s in self.original_text_spans],
            "mutated_text_spans": [s.to_dict() for s in self.mutated_text_spans],
            "surface_edits": [e.to_dict() for e in self.surface_edits],
            "expected_relation": self.expected_relation.value,
            "expected_affected_components": [c.value for c in self.expected_affected_components],
            "expected_location": self.expected_location,
            "expected_severity": self.expected_severity.value,
            "supporting_rule_or_evidence_ids": list(self.supporting_rule_or_evidence_ids),
            "review_status": self.review_status.value,
            "reviewer_ids": list(self.reviewer_ids),
            "adjudication_status": self.adjudication_status.value,
            "mutated_text": self.mutated_text,
            "gold_note": self.gold_note,
            "operator_fallback_used": self.operator_fallback_used,
            "operator_fallback_note": self.operator_fallback_note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MutationProposal":
        _require(isinstance(data, dict), f"MutationProposal must be an object, got {type(data).__name__}")
        try:
            prop = cls(
                pair_id=str(data["pair_id"]),
                seed_id=str(data["seed_id"]),
                question_id=int(data["question_id"]),
                scenario_type=_enum(data["scenario_type"], ScenarioType, "scenario_type"),
                mutation_family=_enum(data["mutation_family"], MutationFamily, "mutation_family"),
                mutation_operator_version=str(data["mutation_operator_version"]),
                changed_field_paths=[str(p) for p in data["changed_field_paths"]],
                original_text_spans=[TextSpan.from_dict(s) for s in data["original_text_spans"]],
                mutated_text_spans=[TextSpan.from_dict(s) for s in data["mutated_text_spans"]],
                surface_edits=[SurfaceEdit.from_dict(s) for s in data["surface_edits"]],
                expected_relation=_enum(data["expected_relation"], ExpectedRelation, "expected_relation"),
                expected_affected_components=[
                    _enum(c, ComponentId, "expected_affected_components entry")
                    for c in data["expected_affected_components"]
                ],
                expected_location=str(data["expected_location"]),
                expected_severity=_enum(data["expected_severity"], SeverityLevel, "expected_severity"),
                supporting_rule_or_evidence_ids=[str(i) for i in data["supporting_rule_or_evidence_ids"]],
                # Review fields are REQUIRED on every manifest record: a missing
                # or unknown value must raise ValidationError, never silently
                # default (final-review finding #20).
                review_status=_enum(data["review_status"], ReviewStatus, "review_status"),
                reviewer_ids=[str(r) for r in data["reviewer_ids"]],
                adjudication_status=_enum(data["adjudication_status"], AdjudicationStatus, "adjudication_status"),
                mutated_text=str(data.get("mutated_text", "")),
                gold_note=str(data.get("gold_note", "")),
                operator_fallback_used=(
                    data["operator_fallback_used"] if "operator_fallback_used" in data else False
                ),
                operator_fallback_note=str(data.get("operator_fallback_note", "")),
            )
        except KeyError as exc:
            raise ValidationError(f"MutationProposal missing field: {exc.args[0]}")
        prop.validate()
        return prop


# ---------------------------------------------------------------------------
# SplitManifest
# ---------------------------------------------------------------------------


@dataclass
class SplitManifest(_Validatable):
    """Seed-level development/blind split (seeds are split, never mutations).

    ``created_from`` is the sha256 (hex) of the ``seed_candidates.jsonl``
    bytes; ``frozen_prompt_sha256`` is a placeholder that a later task
    fills once the mutation prompt set is frozen (null until then).
    """

    development_seed_ids: List[str]
    blind_seed_ids: List[str]
    split_seed: int
    created_from: str
    frozen_prompt_sha256: Optional[str] = None

    def validate(self) -> None:
        for lst_name in ("development_seed_ids", "blind_seed_ids"):
            lst = getattr(self, lst_name)
            _require(isinstance(lst, list) and lst, f"{lst_name} must be a non-empty list")
            for sid in lst:
                _require(_SEED_ID_RE.match(sid or ""), f"invalid seed id {sid!r} in {lst_name}")
        _require(
            isinstance(self.split_seed, int) and not isinstance(self.split_seed, bool),
            f"split_seed must be an int, got {self.split_seed!r}",
        )
        _require(_HEX64_RE.match(self.created_from or ""), f"created_from must be a 64-hex sha256, got {self.created_from!r}")
        if self.frozen_prompt_sha256 is not None:
            _require(
                _HEX64_RE.match(self.frozen_prompt_sha256),
                f"frozen_prompt_sha256 must be null or a 64-hex sha256, got {self.frozen_prompt_sha256!r}",
            )
        overlap = set(self.development_seed_ids) & set(self.blind_seed_ids)
        _require(not overlap, f"seed-level split isolation violated; overlapping seed ids: {sorted(overlap)}")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "development_seed_ids": list(self.development_seed_ids),
            "blind_seed_ids": list(self.blind_seed_ids),
            "split_seed": self.split_seed,
            "created_from": self.created_from,
            "frozen_prompt_sha256": self.frozen_prompt_sha256,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitManifest":
        _require(isinstance(data, dict), f"SplitManifest must be an object, got {type(data).__name__}")
        try:
            m = cls(
                development_seed_ids=[str(s) for s in data["development_seed_ids"]],
                blind_seed_ids=[str(s) for s in data["blind_seed_ids"]],
                split_seed=int(data["split_seed"]),
                created_from=str(data["created_from"]),
                frozen_prompt_sha256=data.get("frozen_prompt_sha256"),
            )
        except KeyError as exc:
            raise ValidationError(f"SplitManifest missing field: {exc.args[0]}")
        m.validate()
        return m


# ---------------------------------------------------------------------------
# DiagnosticAuditResult
# ---------------------------------------------------------------------------


@dataclass
class DiagnosticAuditResult(_Validatable):
    """One finding produced by the diagnostic audit of a mutation pair.

    ``affected_component`` is a single ComponentId (MULTIPLE when the
    finding spans components); ``rationale`` is a concise,
    evidence-grounded explanation -- never a chain-of-thought dump.
    """

    evidence_status: EvidenceStatus
    relation: ExpectedRelation
    affected_component: ComponentId
    violation_type: str
    location: str
    reason_code: str
    supporting_kb_or_rule_ids: List[str]
    minimal_next_action: NextAction
    rationale: str

    def validate(self) -> None:
        _enum(self.evidence_status, EvidenceStatus, "evidence_status")
        _enum(self.relation, ExpectedRelation, "relation")
        _enum(self.affected_component, ComponentId, "affected_component")
        _require(
            isinstance(self.violation_type, str) and self.violation_type,
            "violation_type must be a non-empty str",
        )
        _require(isinstance(self.location, str) and self.location, "location must be a non-empty str")
        _require(isinstance(self.reason_code, str) and self.reason_code, "reason_code must be a non-empty str")
        _require(
            isinstance(self.supporting_kb_or_rule_ids, list),
            "supporting_kb_or_rule_ids must be a list",
        )
        for sid in self.supporting_kb_or_rule_ids:
            _require(isinstance(sid, str) and sid, "supporting_kb_or_rule_ids entries must be non-empty str")
        _enum(self.minimal_next_action, NextAction, "minimal_next_action")
        _require(isinstance(self.rationale, str) and self.rationale, "rationale must be a non-empty str")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "evidence_status": self.evidence_status.value,
            "relation": self.relation.value,
            "affected_component": self.affected_component.value,
            "violation_type": self.violation_type,
            "location": self.location,
            "reason_code": self.reason_code,
            "supporting_kb_or_rule_ids": list(self.supporting_kb_or_rule_ids),
            "minimal_next_action": self.minimal_next_action.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiagnosticAuditResult":
        _require(isinstance(data, dict), f"DiagnosticAuditResult must be an object, got {type(data).__name__}")
        try:
            r = cls(
                evidence_status=_enum(data["evidence_status"], EvidenceStatus, "evidence_status"),
                relation=_enum(data["relation"], ExpectedRelation, "relation"),
                affected_component=_enum(data["affected_component"], ComponentId, "affected_component"),
                violation_type=str(data["violation_type"]),
                location=str(data["location"]),
                reason_code=str(data["reason_code"]),
                supporting_kb_or_rule_ids=[str(i) for i in data["supporting_kb_or_rule_ids"]],
                minimal_next_action=_enum(data["minimal_next_action"], NextAction, "minimal_next_action"),
                rationale=str(data["rationale"]),
            )
        except KeyError as exc:
            raise ValidationError(f"DiagnosticAuditResult missing field: {exc.args[0]}")
        r.validate()
        return r


# ---------------------------------------------------------------------------
# JSONL helpers (validated on load)
# ---------------------------------------------------------------------------


def write_jsonl(path: str, records: List[_Validatable]) -> None:
    """Write records as one compact JSON object per line (UTF-8, LF).

    Keys are sorted so the output is byte-identical across runs.
    """
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str, record_cls: Any) -> List[Any]:
    """Read a JSONL file, validating every record.

    Raises ValidationError (with the offending line number) on any
    malformed record -- a manifest is never partially trusted.
    """
    records: List[Any] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}:{lineno}: invalid JSON: {exc}")
            try:
                records.append(record_cls.from_dict(data))
            except ValidationError as exc:
                raise ValidationError(f"{path}:{lineno}: {exc}")
    return records


def load_seed_candidates(path: str) -> List[SeedCandidate]:
    return read_jsonl(path, SeedCandidate)


def write_seed_candidates(path: str, records: List[SeedCandidate]) -> None:
    write_jsonl(path, records)


def load_mutation_proposals(path: str) -> List[MutationProposal]:
    return read_jsonl(path, MutationProposal)


def write_mutation_proposals(path: str, records: List[MutationProposal]) -> None:
    write_jsonl(path, records)


def load_audit_results(path: str) -> List[DiagnosticAuditResult]:
    return read_jsonl(path, DiagnosticAuditResult)


def write_audit_results(path: str, records: List[DiagnosticAuditResult]) -> None:
    write_jsonl(path, records)
