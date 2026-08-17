"""ClearEval counterfactual-validity overlay -- role-blind DiagnosticAudit runner
(Task 3, deliverable 3).

Runs the DiagnosticAudit prompt (``prompts/diagnostic_audit_v1.txt``) over a
mutation-proposals manifest.  For every pair the runner issues TWO fully
independent, role-blind judge calls -- one for the original protocol text and
one for the mutated text.  Each call's prompt contains ONLY the question text
and ONE protocol text; it never mentions mutations, pairs, seeds, mutation
families, or expected relations, and the two calls share no conversation state
(plain stateless function calls to the judge).

Modes
-----
- ``--online``      : call the repo's teacher model through the production
                      model stack (NEVER used in the test suite -- offline by
                      contract).
- ``--fixtures <p>``: offline mode; inject canned judge outputs from a JSONL
                      fixtures file.  A missing fixture for a case is reported
                      in the coverage section, never imputed.
- default (offline, no fixtures): every case is recorded as
  ``judge_pending`` in coverage -- this is what the "no judge runs yet" state
  of the suite produces.

Split / freeze guard (documented single-revision mechanism)
-----------------------------------------------------------
- ``--split development|blind`` selects the split side.
- development role can never see blind pairs (``BlindSplitAccessError`` via
  the registry / split guard).
- blind role is opt-in AND requires a *frozen* prompt revision: running blind
  with ``split_manifest.frozen_prompt_sha256 == null`` is refused.  Passing
  ``--freeze-prompt`` first (or in the same invocation) writes the sha256 of
  the current ``diagnostic_audit_v1.txt`` into the split manifest -- that is
  the documented one-shot freeze; no prompt tuning happens after blind results
  are produced.

Per-call metadata (recorded on every row): judge model name, prompt file path +
sha256, schema version, operator version, input protocol sha256, timestamp.

Outputs
-------
- ``audit_runs.jsonl``  : one DiagnosticAudit judge call per (pair, side).
- ``cce_scores.jsonl``  : one canonical CCE score per (pair, side).
Both are consumed by ``score_counterfactual_relations.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

try:  # package context
    from .mutation_registry import MutationRegistry, BlindSplitAccessError
    from .mutation_validator import reconstruct_mutated
    from .run_original_cce import (
        CCEScorer,
        calculate_effectiveness_score,
        extract_quantitative,
        make_metadata,
        prompt_meta,
        sha256_bytes,
        sha256_text,
        validate_judge_payload,
        JudgeError,
    )
    from .schemas import (
        DiagnosticAuditResult,
        ExpectedRelation,
        ValidationError,
        load_mutation_proposals,
    )
    from .seed_selector import load_split_manifest
except ImportError:  # script context
    _PKG_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _PKG_DIR)
    from mutation_registry import BlindSplitAccessError, MutationRegistry  # type: ignore
    from mutation_validator import reconstruct_mutated  # type: ignore
    from run_original_cce import (  # type: ignore
        CCEScorer,
        JudgeError,
        calculate_effectiveness_score,
        extract_quantitative,
        make_metadata,
        prompt_meta,
        sha256_bytes,
        sha256_text,
        validate_judge_payload,
    )
    from schemas import (  # type: ignore
        DiagnosticAuditResult,
        ExpectedRelation,
        ValidationError,
        load_mutation_proposals,
    )
    from seed_selector import load_split_manifest  # type: ignore

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))

AUDIT_PROMPT_REL = os.path.join("prompts", "diagnostic_audit_v1.txt")
AUDIT_PROMPT_PATH = os.path.join(PKG_DIR, AUDIT_PROMPT_REL)
PROMPT_VERSION = "diagnostic_audit_v1"  # mirrors the version header line in the file

DEFAULT_SPLIT_PATH = os.path.join(PKG_DIR, "manifests", "split_manifest.json")
DEFAULT_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates.jsonl")
DEFAULT_DEV_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates_development.jsonl")
DEFAULT_PROPOSALS_PATH = os.path.join(PKG_DIR, "manifests", "mutation_proposals.jsonl")
DEFAULT_DEV_PROPOSALS_PATH = os.path.join(PKG_DIR, "manifests", "mutation_proposals_development.jsonl")
DEFAULT_AUDIT_RUNS = os.path.join(PKG_DIR, "manifests", "audit_runs.jsonl")
DEFAULT_CCE_SCORES = os.path.join(PKG_DIR, "manifests", "cce_scores.jsonl")


class FreezeError(Exception):
    """Raised when the blind split cannot be run because the prompt is not frozen."""


def audit_prompt_text() -> str:
    with open(AUDIT_PROMPT_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def current_prompt_sha256() -> str:
    with open(AUDIT_PROMPT_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_audit_prompt(question_text: str, protocol_text: str) -> str:
    """Build the role-blind audit prompt: question + ONE protocol only.

    No mutation family / expected relation / pair / seed / label information can
    ever enter this string -- the runner is the only caller and it passes only
    these two values from the schema-safe prompt template.
    """
    return (
        audit_prompt_text()
        .replace("{{question_text}}", question_text)
        .replace("{{protocol_text}}", protocol_text)
    )


# ---------------------------------------------------------------------------
# Judge abstraction
# ---------------------------------------------------------------------------


class AuditJudge:
    """Protocol for a role-blind DiagnosticAudit judge."""

    def audit(self, question_text: str, protocol_text: str, run_meta: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class FixtureAuditJudge(AuditJudge):
    """Offline judge that injects canned findings from a JSONL fixtures file.

    Fixtures rows must look like::
        {"pair_id": "MUT-001", "side": "original",
         "finding": {<DiagnosticAuditResult fields>}}
    A row may also carry a canned Completeness/Correctness payload under
    ``cce_judge`` (``{"scores": {...}}``) so offline runs can produce full
    mutated-side CCE.  A fixture may instead carry {"status": "judge_failed",
    "error": "..."} to emulate a failed judge call.  Records with no matching
    fixture are reported as ``judge_pending`` by the runner (never imputed).
    """

    def __init__(self, fixtures_path: str) -> None:
        self.fixtures_path = fixtures_path
        self._by_key: Dict[str, Dict[str, Any]] = {}
        self._cc_by_key: Dict[str, Dict[str, Any]] = {}
        if fixtures_path and os.path.isfile(fixtures_path):
            with open(fixtures_path, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    key = (str(row.get("pair_id")), str(row.get("side")))
                    self._by_key[key] = row
                    if isinstance(row.get("cce_judge"), dict):
                        self._cc_by_key[key] = row["cce_judge"]
        self.calls: List[Dict[str, Any]] = []  # recorded role-blind calls

    def cc(self, pair_id: str, side: str) -> Optional[Dict[str, Any]]:
        """Canned Completeness/Correctness payload for (pair, side), if any."""
        fixture = self._by_key.get((str(pair_id), str(side)))
        if fixture is not None and isinstance(fixture.get("cce_judge"), dict):
            return fixture["cce_judge"]
        return self._cc_by_key.get((str(pair_id), str(side)))

    def audit(self, question_text: str, protocol_text: str, run_meta: Dict[str, Any]) -> Dict[str, Any]:
        key = (str(run_meta["pair_id"]), str(run_meta["side"]))
        fixture = self._by_key.get(key)
        self.calls.append({
            "pair_id": run_meta["pair_id"],
            "side": run_meta["side"],
            "question_text": question_text,
            "protocol_text": protocol_text,
            "prompt": build_audit_prompt(question_text, protocol_text),
            "fixture_hit": fixture is not None,
        })
        if fixture is None:
            return {"status": "judge_pending", "instruction": "no fixture for this (pair, side)"}
        if "status" in fixture and fixture["status"] != "ok":
            return {
                "status": fixture.get("status", "judge_failed"),
                "error": fixture.get("error", "fixture supplied failure"),
            }
        try:
            finding = DiagnosticAuditResult.from_dict(fixture.get("finding", {}))
        except (ValidationError, KeyError) as exc:
            return {"status": "parse_failed", "error": str(exc)}
        return {"status": "ok", "finding": finding}


def load_fixtures(path: str) -> FixtureAuditJudge:
    return FixtureAuditJudge(path)


class OnlineAuditJudge(AuditJudge):
    """Online judge through the repo's teacher model (NEVER used in tests)."""

    def __init__(self, teacher_name: str = "openai_gpt-5.2-thinking",
                 config_path: Optional[str] = None,
                 repo_root: str = REPO_ROOT) -> None:
        self.teacher_name = teacher_name
        self.config_path = config_path
        self.repo_root = repo_root

    def audit(self, question_text: str, protocol_text: str, run_meta: Dict[str, Any]) -> Dict[str, Any]:
        from .online_audit import online_audit_call  # lazy; never in tests

        return online_audit_call(
            question_text=question_text,
            protocol_text=protocol_text,
            teacher_name=self.teacher_name,
            config_path=self.config_path,
            repo_root=self.repo_root,
        )


# ---------------------------------------------------------------------------
# Freeze mechanism
# ---------------------------------------------------------------------------


def freeze_prompt(split_path: str, prompt_sha: Optional[str] = None) -> Dict[str, Any]:
    """Write the current prompt sha256 into the split manifest (single freeze).

    The frozen sha256 documents the exact prompt revision used for the blind run
    so no prompt tuning happens after blind results are produced.  Re-freezing
    is REFUSED once a freeze exists (``FreezeError``) -- the freeze is one-shot
    (final-review finding #3), so a stale frozen hash cannot be silently
    overwritten after prompt tuning.
    """
    split = load_split_manifest(split_path)
    if split.frozen_prompt_sha256 is not None:
        raise FreezeError(
            "the prompt is already frozen "
            f"(split_manifest.frozen_prompt_sha256={split.frozen_prompt_sha256[:12]}...); "
            "unfreeze-revise-RE-freeze is not allowed -- the freeze records the single "
            "revision used for the blind run")
    if prompt_sha is None:
        prompt_sha = current_prompt_sha256()
    split.frozen_prompt_sha256 = prompt_sha
    split.validate()
    with open(split_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(split.to_dict(), fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    return {"frozen_prompt_sha256": prompt_sha, "split_path": split_path}


# ---------------------------------------------------------------------------
# CCE scoring driver (independent per side)
# ---------------------------------------------------------------------------


class CCEManager:
    """Frozen-judge payload for a seed's ORIGINAL (production Compatibility + Correctness).

    This is the offline cached judge for seeded originals; the mutated side has
    no frozen record and must be supplied by fixtures or the online teacher.
    """

    @staticmethod
    def seed_judge_payload(seed: Any) -> Dict[str, Any]:
        from .run_original_cce import frozen_effectiveness_to_components

        judge, _eff = frozen_effectiveness_to_components(seed.cce_scores)
        payload: Dict[str, Any] = {"scores": {}}
        for part in ("completeness", "correctness"):
            payload["scores"][part] = {
                sub: {"score": judge[part][sub]["score"], "max_score": judge[part][sub]["max_score"]}
                for sub in judge[part] if sub != "total"
            }
        if judge.get("completeness", {}).get("total") is not None:
            payload["scores"]["completeness"]["total_weighted_score"] = judge["completeness"]["total"]
        if judge.get("correctness", {}).get("total") is not None:
            payload["scores"]["correctness"]["total_weighted_score"] = judge["correctness"]["total"]
        return payload


# ---------------------------------------------------------------------------
# Runner core
# ---------------------------------------------------------------------------


def run_audit(
    role: str,
    split_path: str = DEFAULT_SPLIT_PATH,
    seed_path: str = DEFAULT_SEED_PATH,
    proposals_path: str = DEFAULT_PROPOSALS_PATH,
    judge: Optional[AuditJudge] = None,
    scorer: Optional[CCEScorer] = None,
    audit_runs_path: str = DEFAULT_AUDIT_RUNS,
    cce_scores_path: str = DEFAULT_CCE_SCORES,
    require_frozen_for_blind: bool = True,
    question_text_by_id: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """Run the role-blind audit over the (role-scoped) proposals manifest.

    ``require_frozen_for_blind`` is the guard: blind requires a frozen prompt
    revision (the caller normally passes the CLI result of the freeze check).
    """
    if role not in ("development", "blind"):
        raise ValueError("role must be 'development' or 'blind'")

    # Role-routed seed default: development-role runs open the dev-only seed
    # manifest (no blind content) unless a path is given explicitly; the full
    # manifest stays blind-only opt-in (final-review finding #15).  Proposals
    # are NEVER re-routed here -- a caller that points the dev role at the full
    # 72-record manifest must get a BlindSplitAccessError, not a silent swap.
    if role == "development" and seed_path == DEFAULT_SEED_PATH:
        seed_path = DEFAULT_DEV_SEED_PATH

    split = load_split_manifest(split_path)
    registry = MutationRegistry(
        role=role, seed_path=seed_path, proposals_path=proposals_path, split_path=split_path)
    if role == "blind" and require_frozen_for_blind:
        if not split.frozen_prompt_sha256:
            raise FreezeError(
                "blind split requires a frozen prompt revision; run with --freeze-prompt first "
                "(split_manifest.frozen_prompt_sha256 is null)")
        # a blind run is only valid against the EXACT prompt revision that was
        # frozen -- a blind run under a drift/tuned prompt is refused (finding #3)
        prompt_sha = current_prompt_sha256()
        if split.frozen_prompt_sha256 != prompt_sha:
            raise FreezeError(
                "blind split refused: the frozen prompt revision does not match the current "
                "prompt file (frozen "
                f"{split.frozen_prompt_sha256[:12]}... vs current {prompt_sha[:12]}...); "
                "no prompt tuning may happen after the freeze -- restore the prompt or "
                "unfreeze the split (freeze is one-shot)")

    proposals = registry.load_proposals()  # dev role raises BlindSplitAccessError on blind content
    seeds = {s.seed_id: s for s in registry.seeds}
    if question_text_by_id is None:
        question_text_by_id = _load_question_text()

    judge = judge or FixtureAuditJudge(None)
    scorer = scorer or CCEScorer()

    prompt_sha = current_prompt_sha256()
    prompt_path = AUDIT_PROMPT_REL

    audit_rows: List[Dict[str, Any]] = []
    cce_rows: List[Dict[str, Any]] = []
    coverage: Dict[str, int] = {"total_pairs": len(proposals), "judge_ok": 0, "judge_pending": 0,
                                 "judge_failed": 0, "parse_failed": 0, "cce_ok": 0,
                                 "cce_judge_missing": 0, "cce_judge_failed": 0}

    for prop in proposals:
        seed = seeds[prop.seed_id]
        question_text = question_text_by_id.get(prop.question_id, "")
        sides = [
            ("original", seed.response_text),
            ("mutated", reconstruct_mutated(seed.response_text, prop)[0]),
        ]
        for side, protocol_text in sides:
            # ---- independent role-blind audit call ----
            run_meta = {
                "pair_id": prop.pair_id,
                "seed_id": prop.seed_id,
                "question_id": prop.question_id,
                "side": side,
                "role": role,
                "schema_version": "cleareval_cf.schemas.v1",
                "operator_version": prop.mutation_operator_version,
                "prompt_version": PROMPT_VERSION,
                "prompt_path": prompt_path,
                "prompt_sha256": prompt_sha,
                "input_sha256": sha256_text(protocol_text),
                "question_sha256": sha256_text(question_text),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "judge_model": getattr(judge, "teacher_name", "openai_gpt-5.2-thinking"),
            }
            result = judge.audit(question_text, protocol_text, run_meta)
            row = dict(run_meta)
            row["status"] = result["status"]
            if result["status"] == "ok":
                row["finding"] = result["finding"].to_dict()
                coverage["judge_ok"] += 1
            elif result["status"] == "judge_pending":
                coverage["judge_pending"] += 1
                row.setdefault("instruction", result.get("instruction", ""))
            else:
                coverage[result["status"]] = coverage.get(result["status"], 0) + 1
                row["error"] = result.get("error", "")
            audit_rows.append(row)

            # ---- independent CCE scoring call ----
            judge_cc = None
            if side == "original":
                judge_cc = CCEManager.seed_judge_payload(seed)
            elif hasattr(judge, "cc"):
                judge_cc = judge.cc(prop.pair_id, side)  # canned C+C (offline fixtures)
            score_record = scorer.score_protocol_from_parts(
                protocol_text, prop.question_id, judge_cc=judge_cc, mode="offline")
            score_record = dict(score_record)
            score_record["pair_id"] = prop.pair_id
            score_record["side"] = side
            score_record["seed_id"] = prop.seed_id
            score_record["expected_relation"] = prop.expected_relation.value
            score_record["expected_affected_components"] = [c.value for c in prop.expected_affected_components]
            score_record["question_id"] = prop.question_id
            # per-call metadata contract for scoring/audit runs:
            # teacher model, prompt file path + sha256, operator/schema version,
            # timestamp, input sha256 -- always recorded, never dropped.
            meta = dict(score_record.get("metadata") or {}) if isinstance(score_record.get("metadata"), dict) else {}
            meta["input_sha256"] = sha256_text(protocol_text)
            meta["prompt_path"] = prompt_path
            meta["prompt_sha256"] = prompt_sha
            meta["judge_model"] = getattr(judge, "teacher_name", "openai_gpt-5.2-thinking")
            score_record["metadata"] = meta
            cce_rows.append(score_record)
            if score_record["status"] == "ok":
                coverage["cce_ok"] += 1
            elif score_record["status"] == "judge_missing":
                coverage["cce_judge_missing"] += 1
            else:
                coverage["cce_judge_failed"] += 1

    os.makedirs(os.path.dirname(audit_runs_path), exist_ok=True)
    os.makedirs(os.path.dirname(cce_scores_path), exist_ok=True)
    _write_jsonl(audit_runs_path, audit_rows)
    _write_jsonl(cce_scores_path, cce_rows)
    return {
        "role": role,
        "audit_runs_path": audit_runs_path,
        "cce_scores_path": cce_scores_path,
        "prompt_sha256": prompt_sha,
        "coverage": coverage,
        "n_audit_rows": len(audit_rows),
        "n_cce_rows": len(cce_rows),
    }


def _load_question_text() -> Dict[int, str]:
    path = os.path.join(REPO_ROOT, "dataset", "Q+AR", "src", "question_final.json")
    with open(path, "r", encoding="utf-8") as fh:
        records = json.load(fh)
    return {r["question_id"]: r.get("question", "") for r in records}


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_diagnostic_audit",
        description="ClearEval counterfactual-validity overlay: role-blind DiagnosticAudit runner.")
    parser.add_argument("--split", choices=["development", "blind"], default="development")
    parser.add_argument("--fixtures", default=None, help="offline canned-judge fixtures JSONL")
    parser.add_argument("--online", action="store_true", help="call the teacher over the repo stack (NOT for tests)")
    parser.add_argument("--teacher", default="openai_gpt-5.2-thinking")
    parser.add_argument("--split-manifest", default=DEFAULT_SPLIT_PATH)
    parser.add_argument("--seeds", default=DEFAULT_SEED_PATH)
    parser.add_argument("--proposals", default=DEFAULT_PROPOSALS_PATH)
    parser.add_argument("--audit-runs", default=DEFAULT_AUDIT_RUNS)
    parser.add_argument("--cce-scores", default=DEFAULT_CCE_SCORES)
    parser.add_argument("--freeze-prompt", action="store_true",
                        help="document the current prompt revision into the split manifest before running")
    args = parser.parse_args(argv)

    # development-role CLI defaults route to the dev-scoped manifests (no blind
    # content; final-review finding #15); the full 72-record manifest is
    # reserved for explicit + blind role.
    if args.split == "development":
        if args.seeds == DEFAULT_SEED_PATH:
            args.seeds = DEFAULT_DEV_SEED_PATH
        if args.proposals == DEFAULT_PROPOSALS_PATH:
            args.proposals = DEFAULT_DEV_PROPOSALS_PATH

    if args.split == "blind" and args.freeze_prompt:
        freeze_prompt(args.split_manifest)

    if args.online:
        judge = OnlineAuditJudge(teacher_name=args.teacher)
    else:
        judge = FixtureAuditJudge(args.fixtures)

    try:
        summary = run_audit(
            role=args.split,
            split_path=args.split_manifest,
            seed_path=args.seeds,
            proposals_path=args.proposals,
            judge=judge,
            audit_runs_path=args.audit_runs,
            cce_scores_path=args.cce_scores,
            require_frozen_for_blind=True,
        )
    except FreezeError as exc:
        print(f"blind run refused: {exc}")
        return 2
    except BlindSplitAccessError as exc:
        print(f"development role refused: {exc}")
        return 2

    print(f"role         : {summary['role']} (prompt sha {summary['prompt_sha256'][:12]}...)")
    print(f"audit rows   : {summary['n_audit_rows']}  cce rows: {summary['n_cce_rows']}")
    print(f"coverage     : {summary['coverage']}")
    print(f"audit runs   : {summary['audit_runs_path']}")
    print(f"cce scores   : {summary['cce_scores_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
