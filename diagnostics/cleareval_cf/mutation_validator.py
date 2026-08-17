"""ClearEval counterfactual-validity overlay -- mutation proposal validator (Task 2).

Validates a ``mutation_proposals.jsonl`` manifest against the task's hard
requirements and writes ``reports/MUTATION_VALIDATION.md``:

1. **Schema + lifecycle**: records load through the registry (role ``blind``
   for the full corpus) -> schema-validated; Gold guard enforced; every
   record must be ``PENDING_REVIEW`` with empty ``reviewer_ids`` and
   ``adjudication_status == PENDING``.
2. **Balance**: 24 EQUIVALENT, 48 degrading; degrading pairs exactly 8 per
   mutation_family.
3. **Split containment**: pair's seed in exactly one split side; question_id
   matches the seed record.
4. **Span integrity**: re-applying the declared original/mutated spans to the
   seed ``response_text`` reproduces the mutated text exactly (offsets +
   slice self-consistency), and a masked comparison proves there are **no
   undeclared differences** (the mutation changes ONLY declared fields).
   EQUIVALENT pairs additionally require ``changed_field_paths`` empty and
   the ``surface_edits`` to reproduce the same mutated text.
5. **Evidence spot-check**: every ``kb:<file>:<key>`` evidence id resolves to
   a real KB file + row (time_kb rows by ``method|tier`` incl. the
   ``UNSUPPORTED:tier`` gate; method_ri_ref / method_fluro_compati by method;
   tissue_ri by tissue key).  Evidence-backed families (METHOD_FLUOROPHORE,
   SAMPLE_METHOD_OR_RI_SCOPE, CLEARING_TIME) must carry at least one evidence
   id.
6. **Fallbacks used**: mirrored from the build report (MUTATION_BUILD.md) so
   the final validation doc lists every documented fallback.

Stdlib-only, offline, deterministic.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

try:  # run as `python -m diagnostics.cleareval_cf.mutation_validator`
    from .mutation_builder import apply_edits, region_of
    from .mutation_registry import MutationRegistry, BlindSplitAccessError
    from .schemas import (
        AdjudicationStatus,
        ExpectedRelation,
        MutationFamily,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        ValidationError,
    )
except ImportError:  # run as `python diagnostics/cleareval_cf/mutation_validator.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mutation_builder import apply_edits, region_of  # type: ignore
    from mutation_registry import BlindSplitAccessError, MutationRegistry  # type: ignore
    from schemas import (  # type: ignore
        AdjudicationStatus,
        ExpectedRelation,
        MutationFamily,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        ValidationError,
    )

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
KB_ROOT = os.path.join(REPO_ROOT, "KnowledgeBase")

DEFAULT_VALIDATION_REPORT = os.path.join(PKG_DIR, "reports", "MUTATION_VALIDATION.md")
DEFAULT_BUILD_REPORT = os.path.join(PKG_DIR, "reports", "MUTATION_BUILD.md")

# Families whose whole point is an evidence-backed KB contradiction.
EVIDENCE_REQUIRED_FAMILIES = {
    MutationFamily.METHOD_FLUOROPHORE_CONFLICT,
    MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT,
    MutationFamily.CLEARING_TIME_OUT_OF_RANGE,
}

FAMILIES = [
    MutationFamily.CLEARING_TIME_OUT_OF_RANGE,
    MutationFamily.METHOD_FLUOROPHORE_CONFLICT,
    MutationFamily.REQUIRED_INFORMATION_OMISSION,
    MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT,
    MutationFamily.STEP_ORDER_OR_CHEMISTRY_CONFLICT,
    MutationFamily.TARGET_MARKER_MISMATCH,
]

_EVIDENCE_ID_RE = re.compile(r"^kb:([A-Za-z0-9_.\-]+):(.*)$")


# ---------------------------------------------------------------------------
# Span-integrity primitives
# ---------------------------------------------------------------------------


def reconstruct_mutated(seed_text: str, proposal: MutationProposal) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Re-apply declared spans; returns (mutated_text, [(m_start, m_end, text)])."""
    edits = [
        (s.start, s.end, m.text)
        for (s, m) in zip(proposal.original_text_spans, proposal.mutated_text_spans)
    ]
    return apply_edits(seed_text, edits)


def _masked(text: str, spans: List[Tuple[int, int]]) -> str:
    spans = sorted(spans, key=lambda p: p[0])
    parts: List[str] = []
    prev = 0
    for a, b in spans:
        if a < prev:
            raise ValidationError(f"overlapping spans in masked comparison: {a} < {prev}")
        parts.append(text[prev:a])
        parts.append("\u0000")  # placeholder token covering the declared span
        prev = b
    parts.append(text[prev:])
    return "".join(parts)


def detect_undeclared_edits(seed_text: str, proposal: MutationProposal) -> bool:
    """True if seed->mutated has any difference NOT covered by declared spans.

    Uses a masked comparison: mask out every declared original span (and the
    corresponding mutated span), then require the residuals to be identical.
    """
    mutated, _ = reconstruct_mutated(seed_text, proposal)
    if len(proposal.original_text_spans) != len(proposal.mutated_text_spans):
        return True
    try:
        masked_orig = _masked(seed_text, [(s.start, s.end) for s in proposal.original_text_spans])
        masked_mut = _masked(mutated, [(m.start, m.end) for m in proposal.mutated_text_spans])
    except ValidationError:
        return True
    return masked_orig != masked_mut


def check_span_integrity(seed_text: str, proposal: MutationProposal) -> Tuple[bool, str]:
    """Full span-integrity check for one proposal."""
    for s in proposal.original_text_spans:
        if seed_text[s.start:s.end] != s.text:
            return False, (
                f"original span {s.start}..{s.end} does not slice the seed text: "
                f"declared {s.text!r} vs actual {seed_text[s.start:s.end]!r}"
            )
    # schema-level TextSpan.validate() checks length; we re-verify the mutated
    # coordinates here against the reconstruction.
    mutated, mspans = reconstruct_mutated(seed_text, proposal)
    if mutated == seed_text:
        return False, "mutation is a no-op: mutated text equals the seed text"
    for (ms, me, nt), m in zip(mspans, proposal.mutated_text_spans):
        if (ms, me) != (m.start, m.end):
            return False, (
                f"mutated span offsets mismatch: reconstruction {ms}..{me} "
                f"vs declared {m.start}..{m.end}"
            )
        if mutated[ms:me] != m.text or m.text != nt:
            return False, "mutated span text does not match the reconstructed text"
    if detect_undeclared_edits(seed_text, proposal):
        return False, "undeclared differences detected between seed and mutated text"
    return True, "ok"


def check_equivalent(seed_text: str, proposal: MutationProposal) -> Tuple[bool, str]:
    """EQUIVALENT contract: empty changed_field_paths + all edits in surface_edits.

    The surface edits must correspond 1:1 to the span edits (every declared
    span change is mirrored in surface_edits and vice versa), and the span
    reconstruction must not be a no-op.
    """
    if proposal.changed_field_paths:
        return False, "EQUIVALENT pair must have empty changed_field_paths"
    if not proposal.surface_edits:
        return False, "EQUIVALENT pair must record surface_edits"
    if len(proposal.surface_edits) != len(proposal.original_text_spans):
        return False, "surface_edits must correspond 1:1 to the declared span edits"
    for e, os_, ms_ in zip(
        proposal.surface_edits, proposal.original_text_spans, proposal.mutated_text_spans
    ):
        if e.original_text != os_.text or e.mutated_text != ms_.text:
            return False, "a surface edit does not match its declared span edit"
    mutated, _ = reconstruct_mutated(seed_text, proposal)
    if mutated == seed_text:
        return False, "EQUIVALENT mutation is a no-op"
    return True, "ok"


# ---------------------------------------------------------------------------
# Evidence spot-check
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Any:
    import json

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class EvidenceChecker:
    """Loads KB files once and resolves ``kb:file:key`` evidence ids."""

    def __init__(self, kb_root: str = KB_ROOT) -> None:
        self.kb_root = kb_root
        self._cache: Dict[str, Any] = {}
        self._tier_token_cache: Dict[str, set] = {}

    def _file(self, name: str) -> Any:
        if name not in self._cache:
            path = os.path.join(self.kb_root, name)
            if not os.path.isfile(path):
                raise ValidationError(f"evidence KB file not found: {path}")
            self._cache[name] = _load_json(path)
        return self._cache[name]

    def spot_check(self, evidence_ids: List[str]) -> List[str]:
        """Return a list of unresolved evidence ids (empty = all resolved)."""
        unresolved: List[str] = []
        for eid in evidence_ids:
            ok = False
            try:
                ok = self._resolve_one(eid)
            except (ValidationError, KeyError, TypeError) as exc:  # noqa: PERF203
                ok = False
            if not ok:
                unresolved.append(eid)
        return unresolved

    def _resolve_one(self, eid: str) -> bool:
        m = _EVIDENCE_ID_RE.match(eid)
        if not m:
            return False
        fname, key = m.group(1), m.group(2)
        data = self._file(fname)
        if fname == "time_kb.json":
            method, _, tier = key.partition("|")
            lookup = data.get("lookup", {})
            rows = lookup.get(method, {})
            if not tier:
                return False
            if tier.startswith("UNSUPPORTED:"):
                tier_name = tier.split(":", 1)[1]
                if method not in lookup:
                    return False
                # UNSUPPORTED means: the (method, tier) row must NOT resolve
                return _resolve_time_row(rows, tier_name, self._tier_token_cache) is None
            return _resolve_time_row(rows, tier, self._tier_token_cache) is not None
        if fname == "method_fluro_compati.json":
            return any(row.get("method") == key for row in data)
        if fname == "method_ri_ref.json":
            return key in data.get("ri_ref", {})
        if fname == "tissue_ri.json":
            tissues = data.get("tissue_ri_database", {})
            if key == "default_ri":
                return "default_ri" in tissues
            for group in tissues.get("tissues", {}).values():
                if isinstance(group, dict) and key in group:
                    return True
            return False
        return False


def _non_tier_tokens(tier: str) -> set:
    return {tok for tok in tier.split("_") if not re.fullmatch(r"T\d+[A-Z0-9]*", tok)}


def _resolve_time_row(rows: Dict[str, Any], tier: str, cache: Dict[str, set]) -> Optional[Any]:
    if tier in rows:
        return rows[tier]
    key = tier
    if key not in cache:
        cache[key] = _non_tier_tokens(key)
    for row_tier in rows:
        rt = row_tier
        if rt not in cache:
            cache[rt] = _non_tier_tokens(rt)
        if len(cache[key] & cache[rt]) >= 2:
            return rows[rt]
    return None


# ---------------------------------------------------------------------------
# Full validation
# ---------------------------------------------------------------------------


class ValidationResults:
    def __init__(self) -> None:
        self.problems: List[str] = []
        self.record_problems: Dict[str, List[str]] = collections.defaultdict(list)
        self.family_counts: "collections.Counter[str]" = collections.Counter()
        self.family_degrading: "collections.Counter[str]" = collections.Counter()
        self.relation_counts: "collections.Counter[str]" = collections.Counter()
        self.split_counts: "collections.Counter[str]" = collections.Counter()
        self.n_span_fail = 0
        self.n_evidence_fail = 0
        self.per_pair_rows: List[List[str]] = []

    def add_pair_problem(self, pair_id: str, msg: str) -> None:
        self.record_problems[pair_id].append(msg)
        self.problems.append(f"{pair_id}: {msg}")


def validate_manifest(
    proposals_path: str,
    seeds_path: str,
    split_path: str,
    kb_root: str = KB_ROOT,
    build_report_path: str = DEFAULT_BUILD_REPORT,
    validation_report_path: str = DEFAULT_VALIDATION_REPORT,
) -> Dict[str, Any]:
    """Run the full validation and write ``MUTATION_VALIDATION.md``."""
    registry = MutationRegistry(
        role="blind",  # full-corpus manifest includes blind seeds by design
        seed_path=seeds_path,
        proposals_path=proposals_path,
        split_path=split_path,
    )
    seeds = {s.seed_id: s for s in registry.seeds}  # role=blind -> all 24 seeds
    proposals = registry.load_proposals()
    checker = EvidenceChecker(kb_root)
    res = ValidationResults()

    for p in proposals:
        res.family_counts[p.mutation_family.value] += 1
        res.relation_counts[p.expected_relation.value] += 1
        res.split_counts[registry.split_of(p.seed_id)] += 1
        if p.expected_relation is not ExpectedRelation.EQUIVALENT:
            res.family_degrading[p.mutation_family.value] += 1

        # lifecycle: all PENDING_REVIEW
        if p.review_status is not ReviewStatus.PENDING_REVIEW:
            res.add_pair_problem(p.pair_id, f"review_status must be PENDING_REVIEW, got {p.review_status.value}")
        if p.reviewer_ids:
            res.add_pair_problem(p.pair_id, "reviewer_ids must be empty for a proposal manifest")
        if p.adjudication_status is not AdjudicationStatus.PENDING:
            res.add_pair_problem(p.pair_id, f"adjudication_status must be PENDING, got {p.adjudication_status.value}")

        # question_id consistency
        seed = seeds.get(p.seed_id)
        if seed is None:
            res.add_pair_problem(p.pair_id, f"seed {p.seed_id} not in seed manifest")
            continue
        if seed.question_id != p.question_id:
            res.add_pair_problem(p.pair_id, f"question_id {p.question_id} != seed's {seed.question_id}")

        # span integrity
        ok, msg = check_span_integrity(seed.response_text, p)
        if not ok:
            res.n_span_fail += 1
            res.add_pair_problem(p.pair_id, f"span integrity: {msg}")
        if p.expected_relation is ExpectedRelation.EQUIVALENT:
            ok, msg = check_equivalent(seed.response_text, p)
            if not ok:
                res.add_pair_problem(p.pair_id, f"EQUIVALENT contract: {msg}")

        # evidence
        if (
            p.expected_relation is not ExpectedRelation.EQUIVALENT
            and p.mutation_family in EVIDENCE_REQUIRED_FAMILIES
            and not p.supporting_rule_or_evidence_ids
        ):
            res.add_pair_problem(p.pair_id, "evidence-backed family must carry supporting_rule_or_evidence_ids")
        unresolved = checker.spot_check(p.supporting_rule_or_evidence_ids)
        if unresolved:
            res.n_evidence_fail += 1
            res.add_pair_problem(p.pair_id, f"unresolved evidence ids: {unresolved}")

        res.per_pair_rows.append(
            [
                p.pair_id,
                p.seed_id,
                p.mutation_family.value,
                p.expected_relation.value,
                p.mutation_operator_version,
                "Y" if p.changed_field_paths else "-",
                str(len(p.original_text_spans)),
                "ok" if ok else "FAIL",
            ]
        )

    # family balance (degrading only)
    for fam in FAMILIES:
        got = res.family_degrading[fam.value]
        if got != 8:
            res.problems.append(f"family balance: {fam.value} has {got} degrading pairs (expected 8)")

    relation_problems = {}
    if res.relation_counts.get("EQUIVALENT", 0) != 24:
        relation_problems["24 EQUIVALENT"] = res.relation_counts.get("EQUIVALENT", 0)
    degrading_total = res.relation_counts.get("DEGRADED", 0) + res.relation_counts.get("HARD_FAIL", 0)
    if degrading_total != 48:
        res.problems.append(f"degrading total {degrading_total} != 48")
    if res.relation_counts.get("EQUIVALENT", 0) != 24:
        res.problems.append(f"EQUIVALENT total {res.relation_counts.get('EQUIVALENT', 0)} != 24")
    if len(proposals) != 72:
        res.problems.append(f"total proposals {len(proposals)} != 72")

    # split containment
    dev_ids = set(registry.split.development_seed_ids)
    blind_ids = set(registry.split.blind_seed_ids)
    if dev_ids & blind_ids:
        res.problems.append("split manifest has overlapping dev/blind seed ids")
    unknown = {p.seed_id for p in proposals} - (dev_ids | blind_ids)
    if unknown:
        res.problems.append(f"proposals reference seeds outside the split: {sorted(unknown)}")

    # fallbacks mirror from the build report
    fallbacks = _read_fallbacks(build_report_path)

    valid = not res.problems
    _write_validation_report(
        validation_report_path,
        res=res,
        proposals_path=proposals_path,
        seeds_path=seeds_path,
        split_path=split_path,
        n_proposals=len(proposals),
        fallbacks=fallbacks,
        valid=valid,
    )
    return {
        "valid": valid,
        "problems": res.problems,
        "n_proposals": len(proposals),
        "family_degrading": dict(res.family_degrading),
        "family_all": dict(res.family_counts),
        "relations": dict(res.relation_counts),
        "split": dict(res.split_counts),
        "n_span_fail": res.n_span_fail,
        "n_evidence_fail": res.n_evidence_fail,
        "record_problems": {k: v for k, v in res.record_problems.items()},
        "fallbacks": fallbacks,
        "report_path": validation_report_path,
    }


def _read_fallbacks(build_report_path: str) -> List[Dict[str, str]]:
    """Parse the fallback table from MUTATION_BUILD.md (best effort)."""
    fallbacks: List[Dict[str, str]] = []
    if not os.path.isfile(build_report_path):
        return fallbacks
    with open(build_report_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    in_table = False
    for line in lines:
        if line.startswith("## Fallbacks used"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip("| ").split("|")]
            if cells and cells[0] == "seed_id":
                continue
            if cells and re.fullmatch(r"-{3,}", cells[0]):
                continue  # markdown separator row
            if len(cells) == 4 and re.fullmatch(r"SEED-\d{3}", cells[0]):
                fallbacks.append(
                    {"seed_id": cells[0], "family": cells[1], "operator": cells[2], "note": cells[3]}
                )
    return fallbacks


def _write_validation_report(
    report_path: str,
    res: ValidationResults,
    proposals_path: str,
    seeds_path: str,
    split_path: str,
    n_proposals: int,
    fallbacks: List[Dict[str, str]],
    valid: bool,
) -> None:
    lines: List[str] = []
    lines.append("# MUTATION_VALIDATION -- proposal manifest validation report (Task 2)")
    lines.append("")
    lines.append(f"- proposals  : `{os.path.basename(proposals_path)}` ({n_proposals} records)")
    lines.append(f"- seeds      : `{os.path.basename(seeds_path)}`")
    lines.append(f"- split      : `{os.path.basename(split_path)}`")
    lines.append(f"- validated  : {'**PASS**' if valid else '**FAIL**'} ({len(res.problems)} problem(s))")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- total proposals : {n_proposals}")
    lines.append(f"- by relation     : {dict(sorted(res.relation_counts.items()))}")
    lines.append(f"- by split        : {dict(sorted(res.split_counts.items()))}")
    lines.append("")
    lines.append("## Family balance (degrading pairs; each must be exactly 8)")
    lines.append("")
    lines.append("| family | degrading count | expected |")
    lines.append("|---|---|---|")
    for fam in FAMILIES:
        got = res.family_degrading[fam.value]
        lines.append(f"| {fam.value} | {got} | 8 |")
    lines.append("")
    lines.append("| family | all-record count |")
    lines.append("|---|---|")
    for fam in FAMILIES:
        lines.append(f"| {fam.value} | {res.family_counts[fam.value]} |")
    lines.append("")
    lines.append("## Span integrity + per-pair log")
    lines.append("")
    lines.append("| pair_id | seed_id | family | relation | operator ver | changed_fields | spans | span_ok |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in res.per_pair_rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(f"- span-integrity failures : {res.n_span_fail}")
    lines.append(f"- evidence failures       : {res.n_evidence_fail}")
    lines.append("")
    lines.append("## Fallbacks used (mirrored from MUTATION_BUILD.md)")
    lines.append("")
    if not fallbacks:
        lines.append("None -- all degrading pairs used their primary span operator.")
    else:
        lines.append("| seed_id | family | operator | note |")
        lines.append("|---|---|---|---|")
        for fb in fallbacks:
            lines.append(f"| {fb['seed_id']} | {fb['family']} | {fb['operator']} | {fb['note']} |")
    lines.append("")
    lines.append("## Violations")
    lines.append("")
    if not res.problems:
        lines.append("None.")
    else:
        for prob in res.problems:
            lines.append(f"- {prob}")
    lines.append("")
    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutation_validator",
        description="ClearEval counterfactual-validity overlay: validate the proposals manifest.",
    )
    parser.add_argument("--proposals", default=os.path.join(PKG_DIR, "manifests", "mutation_proposals.jsonl"))
    parser.add_argument("--seeds", default=os.path.join(PKG_DIR, "manifests", "seed_candidates.jsonl"))
    parser.add_argument("--split", default=os.path.join(PKG_DIR, "manifests", "split_manifest.json"))
    parser.add_argument("--kb-root", default=KB_ROOT)
    parser.add_argument("--build-report", default=DEFAULT_BUILD_REPORT)
    parser.add_argument("--report", default=DEFAULT_VALIDATION_REPORT)
    args = parser.parse_args(argv)

    summary = validate_manifest(
        proposals_path=args.proposals,
        seeds_path=args.seeds,
        split_path=args.split,
        kb_root=args.kb_root,
        build_report_path=args.build_report,
        validation_report_path=args.report,
    )
    print(f"valid        : {summary['valid']}")
    print(f"proposals    : {summary['n_proposals']}")
    print(f"families     : {summary['family_degrading']}")
    print(f"relations    : {summary['relations']}")
    print(f"span fails   : {summary['n_span_fail']}  evidence fails: {summary['n_evidence_fail']}")
    print(f"fallbacks    : {len(summary['fallbacks'])}")
    print(f"report       : {summary['report_path']}")
    for prob in summary["problems"][:20]:
        print("  !", prob)
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
