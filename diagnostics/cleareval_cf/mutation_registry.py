"""ClearEval counterfactual-validity overlay -- mutation registry (Task 2).

The registry is the split-aware, Gold-guarded gateway for mutation
proposal manifests.  It re-uses the schema-level contracts and the
split guard from Tasks 1, and *re-enforces* at runtime the invariants
that the schema also enforces at construction time:

1. **Gold guard (load + promote):**
   - ``load``: any ``APPROVED_GOLD`` record must carry non-empty
     ``reviewer_ids`` **and** ``adjudication_status == ADJUDICATED``.
     A forged manifest that manages to carry an APPROVED_GOLD record
     without a human review trail is rejected at load time.
   - ``promote_to_gold``: the only sanctioned way to turn a
     PENDING_REVIEW proposal into APPROVED_GOLD.  It **refuses**
     unless the caller supplies non-empty ``reviewer_ids`` and an
     adjudication-evidence note.  Nothing in this suite fabricates
     APPROVED_GOLD records -- every record written by the builder is
     ``PENDING_REVIEW`` with empty ``reviewer_ids`` and
     ``adjudication_status == PENDING``.

2. **Split guard (development vs blind):**
   - The manifest written by ``mutation_builder`` legitimately contains
     proposals for all 24 seeds (16 development + 8 blind).  In role
     ``"development"`` the registry **raises BlindSplitAccessError** if
     any proposal references a blind-listed seed id -- development-role
     code can never see blind pairs.  Blind access is an explicit
     opt-in ``role="blind"`` (one-directional by design, matching the
     Task 1 guard).
   - Development-role code may inspect *its own* proposal subset without
     the blind content leaking.

3. **Balance / introspection helpers** (used by validator + report):
   ``counts_by_family()``, ``counts_by_split()``,
   ``counts_by_expected_relation()``, ``per_seed_families()``.

This module is stdlib-only and offline (no network, no third-party
imports).  It never encodes ClearEval gold labels, expert labels,
mutation labels, or scorer thresholds.
"""

from __future__ import annotations

import collections
import os
from typing import Any, Dict, List, Optional

try:  # run as `python -m diagnostics.cleareval_cf.mutation_registry`
    from .schemas import (
        AdjudicationStatus,
        BlindSplitAccessError,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        ValidationError,
        load_mutation_proposals,
        load_seed_candidates,
    )
    from .seed_selector import load_split_manifest
except ImportError:  # run as `python diagnostics/cleareval_cf/mutation_registry.py`
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from schemas import (  # type: ignore
        AdjudicationStatus,
        BlindSplitAccessError,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        ValidationError,
        load_mutation_proposals,
        load_seed_candidates,
    )
    from seed_selector import load_split_manifest  # type: ignore

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))

DEFAULT_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates.jsonl")
DEFAULT_PROPOSALS_PATH = os.path.join(PKG_DIR, "manifests", "mutation_proposals.jsonl")
DEFAULT_SPLIT_PATH = os.path.join(PKG_DIR, "manifests", "split_manifest.json")

VALID_ROLES = ("development", "blind")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class MutationRegistry:
    """Split-aware, Gold-guarded access to seed + mutation-proposal manifests.

    ``role`` selects the split posture (``development`` or ``blind``;
    default ``development``).  In development role:

    - ``seeds`` returns only the development-split seeds (blind seed
      content is filtered out -- never leaked);
    - ``load_proposals()`` raises :class:`BlindSplitAccessError` if the
      proposals manifest references any blind-listed seed id.

    In ``blind`` role everything is accessible (one-directional guard).
    """

    def __init__(
        self,
        role: str = "development",
        seed_path: str = DEFAULT_SEED_PATH,
        proposals_path: str = DEFAULT_PROPOSALS_PATH,
        split_path: str = DEFAULT_SPLIT_PATH,
    ) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"unknown role {role!r}; expected {VALID_ROLES}")
        self.role = role
        self.seed_path = seed_path
        self.proposals_path = proposals_path
        self.split_path = split_path

        self.split = self._load_split()
        self._all_seeds = load_seed_candidates(seed_path)
        # Split containment: every loaded seed must belong to exactly one
        # split side (registered seed ids vs manifest contents).
        dev = set(self.split.development_seed_ids)
        blind = set(self.split.blind_seed_ids)
        self._seed_id_to_split: Dict[str, str] = {}
        for seed in self._all_seeds:
            if seed.seed_id in dev:
                split_name = "development"
            elif seed.seed_id in blind:
                split_name = "blind"
            else:
                raise ValidationError(
                    f"seed {seed.seed_id} in {seed_path} is not listed in the "
                    f"split manifest ({split_path}); every seed must be in "
                    "exactly one split side"
                )
            # Dev/blind disjointness is guaranteed by SplitManifest.validate();
            # re-checked below for belt-and-suspenders.
            self._seed_id_to_split[seed.seed_id] = split_name
        overlap = dev & blind
        # schema-level SplitManifest.validate() guarantees disjoint lists; this
        # is a belt-and-suspenders double check.
        if overlap:
            raise ValidationError(f"split overlap between dev and blind: {sorted(overlap)}")

        # Proposals are loaded lazily (loading in development role may raise).
        self._proposals: Optional[List[MutationProposal]] = None

    # -- loading -----------------------------------------------------------------

    def _load_split(self) -> Any:
        return load_split_manifest(self.split_path)

    @property
    def seeds(self) -> List[SeedCandidate]:
        """Seeds visible under the registry's role (dev-only in dev role)."""
        if self.role == "development":
            return [s for s in self._all_seeds if self.split_of(s.seed_id) == "development"]
        return list(self._all_seeds)

    @property
    def all_seed_ids(self) -> List[str]:
        return [s.seed_id for s in self._all_seeds]

    def split_of(self, seed_id: str) -> str:
        if seed_id not in self._seed_id_to_split:
            raise ValidationError(f"seed_id {seed_id!r} not present in {self.seed_path}")
        return self._seed_id_to_split[seed_id]

    def is_blind_seed(self, seed_id: str) -> bool:
        return self.split_of(seed_id) == "blind"

    def load_proposals(self) -> List[MutationProposal]:
        """Load + validate the proposals manifest under this role.

        Re-enforces the Gold guard on every record and the split guard
        (development role refuses manifests that reference blind seeds).
        """
        if self._proposals is not None:
            return self._proposals
        proposals = load_mutation_proposals(self.proposals_path)
        for prop in proposals:
            self._enforce_gold_guard(prop)
            # Split containment of the pair's seed.
            if prop.seed_id not in self._seed_id_to_split:
                raise ValidationError(
                    f"{self.proposals_path}: pair {prop.pair_id} references seed "
                    f"{prop.seed_id!r} which is not a listed seed"
                )
        if self.role == "development":
            bad = sorted({p.seed_id for p in proposals if self.is_blind_seed(p.seed_id)})
            if bad:
                raise BlindSplitAccessError(
                    "development-role load of mutation proposals refused: manifest "
                    f"references blind-listed seed id(s) {bad}"
                )
        self._proposals = proposals
        return proposals

    def _enforce_gold_guard(self, prop: MutationProposal) -> None:
        """Runtime Gold guard: APPROVED_GOLD needs a review trail.

        Even though the schema constructor already guarantees this, a
        manifest is data -- it could be hand-edited -- so the registry
        re-verifies it at load time.
        """
        if prop.review_status is ReviewStatus.APPROVED_GOLD:
            if not prop.reviewer_ids:
                raise ValidationError(
                    f"{self.proposals_path}: pair {prop.pair_id} is APPROVED_GOLD "
                    "but reviewer_ids is empty (Gold requires human review ids)"
                )
            if prop.adjudication_status is not AdjudicationStatus.ADJUDICATED:
                raise ValidationError(
                    f"{self.proposals_path}: pair {prop.pair_id} is APPROVED_GOLD "
                    "but adjudication_status is not ADJUDICATED"
                )

    def load_proposals_any_role(self) -> List[MutationProposal]:
        """Force-load all proposals regardless of role (for tooling only).

        NOT for development workflow use -- it intentionally bypasses the
        split guard and should only be called by the builder/validator,
        which run in blind role for the full corpus.
        """
        if self._proposals is not None:
            return self._proposals
        proposals = load_mutation_proposals(self.proposals_path)
        for prop in proposals:
            self._enforce_gold_guard(prop)
            if prop.seed_id not in self._seed_id_to_split:
                raise ValidationError(
                    f"{self.proposals_path}: pair {prop.pair_id} references unknown "
                    f"seed {prop.seed_id!r}"
                )
        self._proposals = proposals
        return proposals

    # -- Gold promotion -----------------------------------------------------------

    def promote_to_gold(
        self,
        pair_id: str,
        reviewer_ids: List[str],
        adjudication_evidence: str,
    ) -> MutationProposal:
        """Promote a PENDING_REVIEW proposal to APPROVED_GOLD.

        Refuses (raises ``ValidationError``) unless:
        - ``reviewer_ids`` is a non-empty list of non-empty ids;
        - ``adjudication_evidence`` is a non-empty human-authored note;
        - the pair exists and is currently PENDING_REVIEW (Gold must be
          created from a PENDING proposal, not by editing a Gold record).
        """
        proposals = self.load_proposals()  # role-aware (dev role blocks blind manifests)
        target = None
        for prop in proposals:
            if prop.pair_id == pair_id:
                target = prop
                break
        if target is None:
            raise ValidationError(f"pair {pair_id} not found in {self.proposals_path}")
        if target.review_status is ReviewStatus.APPROVED_GOLD:
            raise ValidationError(
                f"pair {pair_id} is already APPROVED_GOLD; refusing to re-promote/forge"
            )
        if not isinstance(reviewer_ids, list) or not reviewer_ids:
            raise ValidationError(
                "promote_to_gold requires non-empty reviewer_ids (human review trail)"
            )
        if any(not isinstance(r, str) or not r for r in reviewer_ids):
            raise ValidationError("reviewer_ids must be non-empty strings")
        if not isinstance(adjudication_evidence, str) or not adjudication_evidence.strip():
            raise ValidationError(
                "promote_to_gold requires adjudication evidence (non-empty note)"
            )
        promoted = MutationProposal(
            pair_id=target.pair_id,
            seed_id=target.seed_id,
            question_id=target.question_id,
            scenario_type=target.scenario_type,
            mutation_family=target.mutation_family,
            mutation_operator_version=target.mutation_operator_version,
            changed_field_paths=list(target.changed_field_paths),
            original_text_spans=list(target.original_text_spans),
            mutated_text_spans=list(target.mutated_text_spans),
            surface_edits=list(target.surface_edits),
            expected_relation=target.expected_relation,
            expected_affected_components=list(target.expected_affected_components),
            expected_location=target.expected_location + f" | gold_note: {adjudication_evidence.strip()}",
            expected_severity=target.expected_severity,
            supporting_rule_or_evidence_ids=list(target.supporting_rule_or_evidence_ids),
            review_status=ReviewStatus.APPROVED_GOLD,
            reviewer_ids=[r for r in reviewer_ids],
            adjudication_status=AdjudicationStatus.ADJUDICATED,
        )
        promoted.validate()  # schema-level Gold guard runs again here
        idx = proposals.index(target)
        proposals[idx] = promoted
        self._proposals = proposals
        return promoted

    # -- balance / introspection ----------------------------------------------------

    def counts_by_family(self) -> Dict[str, int]:
        proposals = self.load_proposals()  # role-aware (dev role blocks blind manifests)
        return dict(collections.Counter(p.mutation_family.value for p in proposals))

    def counts_by_split(self) -> Dict[str, int]:
        proposals = self.load_proposals()  # role-aware
        counter: "collections.Counter[str]" = collections.Counter()
        for p in proposals:
            counter[self.split_of(p.seed_id)] += 1
        return dict(counter)

    def counts_by_expected_relation(self) -> Dict[str, int]:
        proposals = self.load_proposals()  # role-aware
        return dict(collections.Counter(p.expected_relation.value for p in proposals))

    def per_seed_families(self) -> Dict[str, List[str]]:
        """Families used by the degrading proposals of each seed."""
        proposals = self.load_proposals()  # role-aware
        out: Dict[str, List[str]] = {}
        for p in proposals:
            if p.expected_relation.value == "EQUIVALENT":
                continue
            out.setdefault(p.seed_id, []).append(p.mutation_family.value)
        for sid in out:
            out[sid] = sorted(out[sid])
        return out

    # -- persistence -----------------------------------------------------------------

    def save_proposals(self, path: str) -> None:
        """Persist the (possibly promoted) proposal set.

        Uses the deterministic JSONL writer so the file stays
        byte-identical across reruns when nothing changed.
        """
        from .schemas import write_mutation_proposals

        write_mutation_proposals(path, self.load_proposals_any_role())


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: print registry introspection for the real manifests."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="mutation_registry",
        description="ClearEval counterfactual-validity overlay: registry introspection.",
    )
    parser.add_argument(
        "--role", choices=list(VALID_ROLES), default="blind",
        help="split role for introspection (default blind; development role raises "
             "BlindSplitAccessError on the full 72-record manifest by design)",
    )
    parser.add_argument("--proposals", default=DEFAULT_PROPOSALS_PATH)
    parser.add_argument("--seeds", default=DEFAULT_SEED_PATH)
    parser.add_argument("--split", default=DEFAULT_SPLIT_PATH)
    args = parser.parse_args(argv)

    reg = MutationRegistry(
        role=args.role,
        seed_path=args.seeds,
        proposals_path=args.proposals,
        split_path=args.split,
    )
    print(f"role          : {args.role}")
    print(f"seeds in role : {len(reg.seeds)} (dev-only {len(reg.seeds)} of {len(reg.all_seed_ids)})")
    print(f"by family     : {reg.counts_by_family()}")
    print(f"by relation   : {reg.counts_by_expected_relation()}")
    print(f"by split      : {reg.counts_by_split()}")
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(main())
