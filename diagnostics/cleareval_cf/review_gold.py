"""ClearEval counterfactual-validity overlay -- expert reviewed-gold records
(Task 3).

Defines a lightweight schema for expert-reviewed counterfactual labels
(``GoldReview``) and JSONL helpers, kept separate from Task 1's ``schemas.py``
so the construction-phase contracts stay untouched.  A set of GoldReview rows
is the "reviewed gold" that turns the provisional (proposal-driven) metrics
into gold-referenced metrics, and drives the 9.3/9.4/9.5 estimators in
``score_counterfactual_relations.py``.

Review workflow discipline (mirrors the suite-wide Gold guard):
- A GoldReview with ``adjudication_status == ADJUDICATED`` must carry a
  non-empty ``reviewer_id`` and a non-empty ``gold_note`` (adjudication
  evidence) -- enforced at validation time, identical in spirit to the
  schemas.MutationProposal Gold guard.
- The suite never fabricates ADJUDICATED records; the delivered
  ``reviewed_gold.jsonl`` stays empty (PENDING_REVIEW) until human reviewers
  and adjudication write real labels, via ``review_package.jsonl`` +
  ``review_gold.assemble_gold``.

Stdlib-only, offline, deterministic serialization (sorted keys, UTF-8, LF).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # package context
    from .schemas import (
        AdjudicationStatus,
        ComponentId,
        ExpectedRelation,
        NextAction,
        ValidationError,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from schemas import (  # type: ignore
        AdjudicationStatus,
        ComponentId,
        ExpectedRelation,
        NextAction,
        ValidationError,
    )

_PAIR_RE = re.compile(r"^(?:DEV-)?MUT-\d{3,}$")


def _enum_or_none(enum_cls: Any, value: Any, field_name: str) -> Optional[Any]:
    if value is None or value == "":
        return None
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        allowed = ", ".join(sorted(m.value for m in enum_cls))
        raise ValidationError(f"invalid {field_name}={value!r}; expected one of: {allowed}")


@dataclass
class GoldReview:
    """One expert-reviewed label row for a counterfactual pair.

    Fields mirror the ``review_package.jsonl`` row so a reviewer file can be
    turned into gold rows 1:1 (``assemble_gold``).
    """

    pair_id: str
    seed_id: str
    question_id: int
    seed_suitable_for_local_counterfactual_testing: Optional[bool] = None
    mutation_scientifically_valid: Optional[bool] = None
    expected_relation: Optional[ExpectedRelation] = None
    affected_component: Optional[ComponentId] = None
    violation_location: str = ""
    hard_fail_status: Optional[bool] = None
    minimal_next_action: Optional[NextAction] = None
    supporting_rule_or_evidence_ids: List[str] = field(default_factory=list)
    reviewer_id: str = ""
    adjudication_status: AdjudicationStatus = AdjudicationStatus.PENDING
    gold_note: str = ""

    def validate(self) -> None:
        if not _PAIR_RE.match(self.pair_id or ""):
            raise ValidationError(f"invalid pair_id {self.pair_id!r}; expected MUT-<NNN> (or DEV-MUT-<NNN>)")
        if not (self.seed_id or "").startswith("SEED-"):
            raise ValidationError(f"invalid seed_id {self.seed_id!r}")
        if not isinstance(self.question_id, int) or isinstance(self.question_id, bool):
            raise ValidationError("question_id must be an int")
        if self.expected_relation is not None:
            _enum_or_none(ExpectedRelation, self.expected_relation, "expected_relation")
        if self.affected_component is not None:
            _enum_or_none(ComponentId, self.affected_component, "affected_component")
        if self.minimal_next_action is not None:
            _enum_or_none(NextAction, self.minimal_next_action, "minimal_next_action")
        if self.adjudication_status is AdjudicationStatus.ADJUDICATED:
            if not (self.reviewer_id or "").strip():
                raise ValidationError("ADJUDICATED gold requires a non-empty reviewer_id")
            if not (self.gold_note or "").strip():
                raise ValidationError("ADJUDICATED gold requires a non-empty gold_note (adjudication evidence)")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "pair_id": self.pair_id,
            "seed_id": self.seed_id,
            "question_id": int(self.question_id),
            "seed_suitable_for_local_counterfactual_testing": self.seed_suitable_for_local_counterfactual_testing,
            "mutation_scientifically_valid": self.mutation_scientifically_valid,
            "expected_relation": self.expected_relation.value if self.expected_relation else None,
            "affected_component": self.affected_component.value if self.affected_component else None,
            "violation_location": self.violation_location,
            "hard_fail_status": self.hard_fail_status,
            "minimal_next_action": self.minimal_next_action.value if self.minimal_next_action else None,
            "supporting_rule_or_evidence_ids": list(self.supporting_rule_or_evidence_ids),
            "reviewer_id": self.reviewer_id,
            "adjudication_status": self.adjudication_status.value,
            "gold_note": self.gold_note,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoldReview":
        if not isinstance(data, dict):
            raise ValidationError("GoldReview must be an object")
        try:
            raw_adj = data["adjudication_status"]
        except KeyError as exc:
            raise ValidationError(f"GoldReview missing field: {exc.args[0]}")
        if str(raw_adj) not in {s.value for s in AdjudicationStatus}:
            allowed = ", ".join(sorted(s.value for s in AdjudicationStatus))
            raise ValidationError(f"invalid adjudication_status={raw_adj!r}; expected one of: {allowed}")
        try:
            g = cls(
                pair_id=str(data["pair_id"]),
                seed_id=str(data["seed_id"]),
                question_id=int(data["question_id"]),
                seed_suitable_for_local_counterfactual_testing=data.get("seed_suitable_for_local_counterfactual_testing"),
                mutation_scientifically_valid=data.get("mutation_scientifically_valid"),
                expected_relation=_enum_or_none(ExpectedRelation, data.get("expected_relation"), "expected_relation"),
                affected_component=_enum_or_none(ComponentId, data.get("affected_component"), "affected_component"),
                violation_location=str(data.get("violation_location") or ""),
                hard_fail_status=data.get("hard_fail_status"),
                minimal_next_action=_enum_or_none(NextAction, data.get("minimal_next_action"), "minimal_next_action"),
                supporting_rule_or_evidence_ids=[str(i) for i in (data.get("supporting_rule_or_evidence_ids") or [])],
                reviewer_id=str(data.get("reviewer_id") or ""),
                adjudication_status=AdjudicationStatus(str(raw_adj)),
                gold_note=str(data.get("gold_note") or ""),
            )
        except KeyError as exc:
            raise ValidationError(f"GoldReview missing field: {exc.args[0]}")
        g.validate()
        return g


def load_gold(path: str) -> List[GoldReview]:
    rows: List[GoldReview] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(GoldReview.from_dict(json.loads(line)))
            except ValidationError as exc:
                raise ValidationError(f"{path}:{lineno}: {exc}")
    return rows


def write_gold(path: str, rows: List[GoldReview]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for g in rows:
            fh.write(json.dumps(g.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def assemble_gold(package_rows: List[Dict[str, Any]],
                  reviewer_id: str,
                  adjudicated: bool = False,
                  gold_note: str = "",
                  expert: str = "A") -> List[GoldReview]:
    """Turn filled review-package rows (one dict per pair) into GoldReview rows.

    ``package_rows`` are the review_package.jsonl rows after an expert fills in
    the ``reviewer_{expert}_*`` label fields (expert "A" or "B"; default "A").
    ONLY the per-expert label keys are read -- the package row also carries the
    *programmatic* proposal expectation under unprefixed names
    (``expected_relation``, ``expected_affected_components``, ...), and those
    must NEVER leak into Gold (final-review finding #1).  Rows whose expert
    label fields are all empty are skipped (and are covered by 9.7 coverage).
    """
    if expert not in ("A", "B"):
        raise ValueError(f"expert must be 'A' or 'B', got {expert!r}")
    prefix = f"reviewer_{expert}_"
    label_keys = (
        "seed_suitable_for_local_counterfactual_testing",
        "mutation_scientifically_valid",
        "expected_relation",
        "affected_cc_component",
        "violation_location",
        "hard_fail_status",
        "minimal_next_action",
        "supporting_rule_or_evidence_ids",
    )
    out: List[GoldReview] = []
    for row in package_rows:
        if row.get("_review_filled") is False:
            continue
        values = {k: row.get(prefix + k) for k in label_keys}
        filled = any(v not in (None, "", []) for v in values.values())
        if not filled:
            continue
        g = GoldReview(
            pair_id=str(row["pair_id"]),
            seed_id=str(row.get("seed_id", "")),
            question_id=int(row.get("question_id", -1)),
            seed_suitable_for_local_counterfactual_testing=values["seed_suitable_for_local_counterfactual_testing"],
            mutation_scientifically_valid=values["mutation_scientifically_valid"],
            expected_relation=_enum_or_none(ExpectedRelation, values["expected_relation"], "expected_relation"),
            affected_component=_enum_or_none(ComponentId, values["affected_cc_component"], "affected_component"),
            violation_location=str(values["violation_location"] or ""),
            hard_fail_status=values["hard_fail_status"],
            minimal_next_action=_enum_or_none(NextAction, values["minimal_next_action"], "minimal_next_action"),
            supporting_rule_or_evidence_ids=[str(i) for i in (values["supporting_rule_or_evidence_ids"] or [])],
            reviewer_id=reviewer_id,
            adjudication_status=AdjudicationStatus.ADJUDICATED if adjudicated else AdjudicationStatus.PENDING,
            gold_note=gold_note,
        )
        g.validate()
        out.append(g)
    return out
