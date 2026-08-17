"""Schema-level tests for diagnostics/cleareval_cf/schemas.py (Task 1).

Offline: only stdlib + the overlay's own modules.  These tests pin the
validation contracts (enum membership, seed/pair id formats, TextSpan
self-verification, the Gold guard, split-isolation invariants) that
later tasks (mutation operator, registry) build on.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from diagnostics.cleareval_cf.schemas import (  # noqa: E402
    AdjudicationStatus,
    BlindSplitAccessError,
    ComponentId,
    DiagnosticAuditResult,
    EvidenceStatus,
    ExpectedRelation,
    MutationFamily,
    MutationProposal,
    NextAction,
    ReviewStatus,
    ScenarioType,
    SeedCandidate,
    SeverityLevel,
    SplitManifest,
    SurfaceEdit,
    TextSpan,
    ValidationError,
    load_seed_candidates,
    write_seed_candidates,
)


def _seed_dict(**overrides):
    d = {
        "seed_id": "SEED-001",
        "question_id": 1,
        "scenario_type": "SIMPLE_GENERATION",
        "source_model": "openai_gpt-5.2-fast",
        "source_file": "dataset/Q+AR/model_response/from_openai_gpt-5.2-fast_1-shot.json",
        "response_text": "1、荧光/标记策略：免疫荧光标记 NeuN。2、组织透明方法：CUBIC。",
        "question_mode": "APPLICATION_PROTOCOL_DESIGN",
        "sample_tier": "T04_WHOLE_MOUSE_BRAIN_5_12MM",
        "clearing_method_family": "CUBIC",
        "labeling_requirement": "IMMUNOLABELING",
        "n_marker_targets": 2,
        "cce_scores": {
            "completeness": {
                "c_step": {"score": 1, "max_score": 2},
                "c_param": {"score": 3, "max_score": 3},
                "total_weighted_score": 4.0,
            },
            "correctness": {
                "co_order": {"score": 3, "max_score": 3},
                "co_method": {"score": 2, "max_score": 2},
                "co_param": {"score": 1, "max_score": 2},
                "co_chem": {"score": 1, "max_score": 1},
                "total_weighted_score": 7.0,
            },
            "effectiveness": {
                "s_method": {"score": 1.63, "max_score": 2.5},
                "s_label": {"score": 3.9, "max_score": 6},
                "s_trans": {"score": 2.8, "max_score": 3},
                "s_time": {"score": 3.0, "max_score": 3},
                "total_weighted_score": 11.33,
            },
            "total": 22.33,
        },
        "screening_status": "PENDING_SCREENING",
    }
    d.update(overrides)
    return d


def _proposal_dict(**overrides):
    d = {
        "pair_id": "MUT-001",
        "seed_id": "SEED-001",
        "question_id": 1,
        "scenario_type": "SIMPLE_GENERATION",
        "mutation_family": "CLEARING_TIME_OUT_OF_RANGE",
        "mutation_operator_version": "v1.0",
        "changed_field_paths": ["protocol.steps[3].time_hours"],
        "original_text_spans": [
            {"path": "protocol.steps[3].time_hours", "start": 0, "end": 3, "text": "2 天"}
        ],
        "mutated_text_spans": [
            {"path": "protocol.steps[3].time_hours", "start": 0, "end": 3, "text": "9 天"}
        ],
        "surface_edits": [],
        "expected_relation": "DEGRADED",
        "expected_affected_components": ["S_TIME"],
        "expected_location": "clearing step incubation time",
        "expected_severity": "MODERATE",
        "supporting_rule_or_evidence_ids": ["KB-RULE-007"],
        "review_status": "PENDING_REVIEW",
        "reviewer_ids": [],
        "adjudication_status": "PENDING",
    }
    d.update(overrides)
    return d


class SeedCandidateSchemaTests(unittest.TestCase):
    def test_round_trip(self):
        cand = SeedCandidate.from_dict(_seed_dict())
        cand.validate()
        self.assertEqual(SeedCandidate.from_dict(cand.to_dict()), cand)
        self.assertEqual(cand.scenario_type, ScenarioType.SIMPLE_GENERATION)
        self.assertEqual(cand.screening_status.value, "PENDING_SCREENING")

    def test_bad_seed_id_rejected(self):
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(seed_id="SEED-1"))
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(seed_id="seed-001"))

    def test_bad_enum_rejected(self):
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(scenario_type="NONSENSE"))
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(clearing_method_family="NOT_A_FAMILY"))
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(labeling_requirement="CHEMICAL"))

    def test_missing_field_rejected(self):
        d = _seed_dict()
        del d["response_text"]
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(d)

    def test_empty_response_rejected(self):
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(response_text="   "))

    def test_cce_scores_must_be_complete(self):
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(_seed_dict(cce_scores={"completeness": {}}))
        bad = _seed_dict()
        bad["cce_scores"]["correctness"]["total_weighted_score"] = None
        with self.assertRaises(ValidationError):
            SeedCandidate.from_dict(bad)


class TextSpanSurfaceEditTests(unittest.TestCase):
    def test_valid_span(self):
        span = TextSpan.from_dict({"path": "p", "start": 3, "end": 7, "text": "abcd"})
        self.assertEqual(span.to_dict()["text"], "abcd")

    def test_invalid_offsets_rejected(self):
        with self.assertRaises(ValidationError):
            TextSpan.from_dict({"path": "p", "start": 5, "end": 5, "text": "x"})
        with self.assertRaises(ValidationError):
            TextSpan.from_dict({"path": "p", "start": -1, "end": 2, "text": "ab"})

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValidationError):
            TextSpan.from_dict({"path": "p", "start": 0, "end": 5, "text": "longer"})

    def test_surface_edit_must_change_text(self):
        with self.assertRaises(ValidationError):
            SurfaceEdit.from_dict({"path": "p", "original_text": "abc", "mutated_text": "abc"})


class MutationProposalTests(unittest.TestCase):
    """Includes the hard Gold guard: APPROVED_GOLD requires non-empty
    reviewer_ids AND adjudication_status == ADJUDICATED."""

    def test_round_trip_pending_review(self):
        prop = MutationProposal.from_dict(_proposal_dict())
        self.assertEqual(MutationProposal.from_dict(prop.to_dict()), prop)
        self.assertEqual(prop.review_status, ReviewStatus.PENDING_REVIEW)
        self.assertEqual(prop.adjudication_status, AdjudicationStatus.PENDING)

    def test_pending_review_allows_empty_reviewers(self):
        # Every manifest record this suite writes must be PENDING_REVIEW;
        # empty reviewer_ids is legal there.
        MutationProposal.from_dict(_proposal_dict()).validate()

    def test_gold_requires_reviewers(self):
        with self.assertRaises(ValidationError) as ctx:
            MutationProposal.from_dict(_proposal_dict(review_status="APPROVED_GOLD"))
        self.assertIn("reviewer_ids", str(ctx.exception))

    def test_gold_requires_adjudication(self):
        with self.assertRaises(ValidationError) as ctx:
            MutationProposal.from_dict(
                _proposal_dict(
                    review_status="APPROVED_GOLD",
                    reviewer_ids=["reviewer-a"],
                    adjudication_status="PENDING",
                )
            )
        self.assertIn("ADJUDICATED", str(ctx.exception))

    def test_gold_ok_when_complete(self):
        prop = MutationProposal.from_dict(
            _proposal_dict(
                review_status="APPROVED_GOLD",
                reviewer_ids=["reviewer-a"],
                adjudication_status="ADJUDICATED",
            )
        )
        prop.validate()

    def test_bad_family_rejected(self):
        with self.assertRaises(ValidationError):
            MutationProposal.from_dict(_proposal_dict(mutation_family="DELETE_EVERYTHING"))

    def test_bad_relation_rejected(self):
        with self.assertRaises(ValidationError):
            MutationProposal.from_dict(_proposal_dict(expected_relation="BETTER"))

    def test_expected_components_must_be_nonempty(self):
        with self.assertRaises(ValidationError):
            MutationProposal.from_dict(_proposal_dict(expected_affected_components=[]))

    def test_multi_component_allowed(self):
        prop = MutationProposal.from_dict(
            _proposal_dict(expected_affected_components=["S_TIME", "CORRECTNESS", "MULTIPLE"])
        )
        self.assertIn(ComponentId.S_TIME, prop.expected_affected_components)

    def test_severity_enum(self):
        for sev in ("NONE", "MINOR", "MODERATE", "CRITICAL"):
            MutationProposal.from_dict(_proposal_dict(expected_severity=sev)).validate()
        with self.assertRaises(ValidationError):
            MutationProposal.from_dict(_proposal_dict(expected_severity="SEVERE"))


class DiagnosticAuditResultTests(unittest.TestCase):
    def _audit_dict(self, **overrides):
        d = {
            "evidence_status": "SUFFICIENT",
            "relation": "DEGRADED",
            "affected_component": "S_TIME",
            "violation_type": "time_out_of_range",
            "location": "protocol.steps[3]",
            "reason_code": "T-OOR-01",
            "supporting_kb_or_rule_ids": ["KB-RULE-007"],
            "minimal_next_action": "LOCAL_EDIT",
            "rationale": "Incubation time exceeds the KB range for the method/tier.",
        }
        d.update(overrides)
        return d

    def test_round_trip(self):
        r = DiagnosticAuditResult.from_dict(self._audit_dict())
        self.assertEqual(DiagnosticAuditResult.from_dict(r.to_dict()), r)
        r.validate()

    def test_enum_values(self):
        for st in ("SUFFICIENT", "INSUFFICIENT", "OUT_OF_SCOPE"):
            DiagnosticAuditResult.from_dict(self._audit_dict(evidence_status=st)).validate()
        for rel in ("EQUIVALENT", "DEGRADED", "HARD_FAIL"):
            DiagnosticAuditResult.from_dict(self._audit_dict(relation=rel)).validate()
        for act in ("NO_CHANGE", "LOCAL_EDIT", "EVIDENCE_REQUIRED", "BACKTRACK", "ABSTAIN"):
            DiagnosticAuditResult.from_dict(self._audit_dict(minimal_next_action=act)).validate()

    def test_bad_enums_rejected(self):
        with self.assertRaises(ValidationError):
            DiagnosticAuditResult.from_dict(self._audit_dict(evidence_status="MAYBE"))
        with self.assertRaises(ValidationError):
            DiagnosticAuditResult.from_dict(self._audit_dict(affected_component="SOMETHING"))

    def test_rationale_required(self):
        with self.assertRaises(ValidationError):
            DiagnosticAuditResult.from_dict(self._audit_dict(rationale=""))


class SplitManifestTests(unittest.TestCase):
    def _manifest_dict(self, **overrides):
        d = {
            "development_seed_ids": ["SEED-001", "SEED-002"],
            "blind_seed_ids": ["SEED-003", "SEED-004"],
            "split_seed": 20260817,
            "created_from": "a" * 64,
            "frozen_prompt_sha256": None,
        }
        d.update(overrides)
        return d

    def test_round_trip(self):
        m = SplitManifest.from_dict(self._manifest_dict())
        self.assertEqual(SplitManifest.from_dict(m.to_dict()), m)
        m.validate()

    def test_overlap_rejected(self):
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(
                self._manifest_dict(
                    development_seed_ids=["SEED-001", "SEED-003"],
                    blind_seed_ids=["SEED-003", "SEED-004"],
                )
            )

    def test_empty_lists_rejected(self):
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(self._manifest_dict(development_seed_ids=[]))
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(self._manifest_dict(blind_seed_ids=[]))

    def test_created_from_must_be_64_hex(self):
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(self._manifest_dict(created_from="zz" * 32))
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(self._manifest_dict(created_from="abc"))

    def test_frozen_prompt_sha256_null_or_64hex(self):
        SplitManifest.from_dict(self._manifest_dict(frozen_prompt_sha256="b" * 64)).validate()
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(self._manifest_dict(frozen_prompt_sha256="short"))

    def test_bad_seed_id_format_rejected(self):
        with self.assertRaises(ValidationError):
            SplitManifest.from_dict(
                self._manifest_dict(development_seed_ids=["SEED-1"])
            )


class JsonlHelperTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_seed_jsonl_round_trip(self):
        path = os.path.join(self.tmpdir.name, "seeds.jsonl")
        records = [SeedCandidate.from_dict(_seed_dict(seed_id=f"SEED-{i:03d}")) for i in range(1, 4)]
        write_seed_candidates(path, records)
        loaded = load_seed_candidates(path)
        self.assertEqual(loaded, records)
        # byte-stability: sort_keys + ensure_ascii=False + LF
        with open(path, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\r\n", raw)

    def test_corrupt_line_rejected_with_line_number(self):
        path = os.path.join(self.tmpdir.name, "bad.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json_dumps_ok() + "\n")
            fh.write("{not json}\n")
        with self.assertRaises(ValidationError) as ctx:
            load_seed_candidates(path)
        self.assertIn(":2:", str(ctx.exception))

    def test_validation_error_reports_line(self):
        path = os.path.join(self.tmpdir.name, "bad2.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('{"seed_id": "NOPE", "question_id": 1}\n')
        with self.assertRaises(ValidationError) as ctx:
            load_seed_candidates(path)
        self.assertIn(":1:", str(ctx.exception))


def json_dumps_ok():
    import json

    return json.dumps(_seed_dict(), ensure_ascii=False, sort_keys=True)


class ErrorClassTests(unittest.TestCase):
    def test_blind_split_access_error_is_exception(self):
        self.assertTrue(issubclass(BlindSplitAccessError, Exception))


if __name__ == "__main__":
    unittest.main()
