"""Synthetic registration contracts only; no scientific gold or model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from oeq_scientific import _cards
from experiments.construct_validity.evidence import (
    _identity, check_scientific_support, make_entailment_verification, validate_cards,
)
from experiments.construct_validity.task_state import propose_task_state
from tests.test_evidence_fidelity import source_fixture


class RegisteredScientificSupportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.card, self.req, self.protocol, self.assessment = source_fixture()
        self.source = {k: deepcopy(v) for k, v in self.card.items() if k != "source_document"}
        document = self.card["source_document"]
        self.body = document["text"].encode("utf-8")
        self.source["snapshot"] = dict(text_path="body.txt", text_sha256=hashlib.sha256(self.body).hexdigest(),
                                       identity_url=document["url"], version=document["version"])
        self.source["scientific_validation"] = None
        (self.root / "body.txt").write_bytes(self.body)
        (self.root / "KnowledgeBase").mkdir()

    def load(self):
        (self.root / "KnowledgeBase/source_registry.json").write_text(
            json.dumps({"sources": [self.source]}), encoding="utf-8")
        return _cards(self.root)

    def check(self, cards):
        return check_scientific_support(self.assessment["requirements"][0], self.req, cards, self.protocol)

    def reseal(self, proof):
        proof["input_sha256"] = _identity(proof["input"])
        proof["id"] = _identity({k: v for k, v in proof.items() if k != "id"})

    def test_registered_frozen_support_reaches_existing_checker_without_authenticating_truth(self):
        cards = self.load()
        for key in ("applicability", "scope_support", "entailment_verifications"):
            self.assertEqual(cards[0][key], self.card[key])
        self.assertIsNone(cards[0]["scientific_validation"])
        self.assertEqual(cards[0]["entailment_verifications"][0]["scientific_validation"], "PENDING_USER_REFERENCE")
        audit = validate_cards(cards)["E"]
        self.assertEqual(audit["status"], "BOUND")
        self.assertEqual(audit["origin_authentication"], "SUPPLIED_SNAPSHOT_NOT_INDEPENDENTLY_AUTHENTICATED")
        result = self.check(cards)
        self.assertEqual(result["guards"], [])
        self.assertFalse(result["certified_truth"])
        cards[0]["applicability"]["method"] = "mutated"
        self.assertEqual(self.source["applicability"]["method"], "M")

    def test_missing_registered_fields_remain_empty_and_unbound(self):
        for key in ("applicability", "scope_support", "entailment_verifications"):
            del self.source[key]
        cards = self.load()
        self.assertEqual(cards[0]["applicability"], {})
        self.assertEqual(cards[0]["scope_support"], {})
        self.assertEqual(cards[0].get("entailment_verifications", []), [])
        guards = self.check(cards)["guards"]
        self.assertIn("SOURCE_APPLICABILITY_UNBOUND", guards)
        self.assertIn("SEPARATE_ENTAILMENT_CHECK_UNBOUND", guards)

    def test_snapshot_bytes_identity_version_and_path_are_checked(self):
        baseline = deepcopy(self.source)
        for changes in ({"text_sha256": "0" * 64}, {"version": "v2"},
                        {"identity_url": "https://example.org/other"},
                        {"text_path": "../body.txt"}, {"version": None}):
            with self.subTest(changes=changes):
                self.source = deepcopy(baseline)
                self.source["snapshot"].update(changes)
                with self.assertRaises(ValueError):
                    self.load()

    def test_registered_structural_errors_are_not_silently_discarded(self):
        baseline = deepcopy(self.source)
        for key, value in (("applicability", "APPLICABLE"), ("scope_support", []),
                           ("entailment_verifications", {}), ("entailment_verifications", [None])):
            with self.subTest(key=key, value=value):
                self.source = deepcopy(baseline)
                self.source[key] = value
                with self.assertRaises(ValueError):
                    self.load()

    def test_proof_artifact_source_binding_and_provenance_are_checked(self):
        baseline = deepcopy(self.source)
        mutations = ("artifact_hash", "source_hash", "source_id", "source_version", "provenance", "raw_relation", "duplicate")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.source = deepcopy(baseline)
                proof = self.source["entailment_verifications"][0]
                if mutation == "artifact_hash":
                    proof["scientific_validation"] = "changed"
                elif mutation.startswith("source_"):
                    field = {"source_hash": "source_sha256", "source_id": "source_id", "source_version": "source_version"}[mutation]
                    proof["input"][field] = "different"
                    self.reseal(proof)
                elif mutation == "provenance":
                    proof["verifier"]["revision"] = ""
                    self.reseal(proof)
                elif mutation == "raw_relation":
                    proof["raw_result"]["relation"] = "REFUTES"
                    self.reseal(proof)
                else:
                    self.source["entailment_verifications"].append(deepcopy(proof))
                with self.assertRaises(ValueError):
                    self.load()

    def test_proof_input_shape_and_citation_ids_are_checked(self):
        baseline = deepcopy(self.source)
        for field, value in (("hypothesis", None), ("applicability", "APPLICABLE"),
                             ("passage_ids", "P"), ("passage_ids", ["P", "P"]),
                             ("passage_ids", ["UNKNOWN"])):
            with self.subTest(field=field, value=value):
                self.source = deepcopy(baseline)
                proof = self.source["entailment_verifications"][0]
                proof["input"][field] = value
                self.reseal(proof)
                with self.assertRaises(ValueError):
                    self.load()

    def test_scope_support_must_match_fulltext(self):
        self.source["scope_support"]["method"]["spans"][0]["start"] = 0
        with self.assertRaises(ValueError):
            self.load()

    def test_scope_outside_cited_rationale_stays_unbound(self):
        quote = "Synthetic M v1 preserves S"
        passage = dict(id="P", start=0, end=len(quote), quote=quote, sha256=hashlib.sha256(quote.encode()).hexdigest())
        self.source["passages"] = [passage]
        self.card["passages"] = [deepcopy(passage)]
        proof = make_entailment_verification(self.card, ["P"], self.req["text"], self.req["applicability"],
                    lambda data: {"relation": "SUPPORTS"}, verifier_id="SYNTHETIC_CHECKER",
                    verifier_revision="fixture-v1", response_origin="SYNTHETIC_ENGINEERING_FIXTURE")
        self.source["entailment_verifications"] = [proof]
        self.assessment["requirements"][0]["evidence_checks"][0]["verification_id"] = proof["id"]
        result = self.check(self.load())
        self.assertTrue(any(g.startswith("SOURCE_SCOPE_OUTSIDE_CITED_RATIONALE:") for g in result["guards"]))
        self.assertFalse(result["certified_truth"])

    def test_task_provisional_status_is_separate_from_scientific_scope(self):
        question = dict(question_id="arbitrary", question="Please distinguish T/B cells.",
                        applicability={"method": "M"})
        result = propose_task_state(question, evidence_ids=["E"])
        req = result["requirements"][0]
        self.assertEqual(req["kind"], "SCIENTIFIC")
        self.assertEqual(req["applicability_status"], "APPLICABLE")
        self.assertEqual(req["applicability"], {})
        self.assertIsNone(result["scientific_gold"])
        self.assertEqual(req["literal_rule"]["state_audit"]["applicability_status"], "APPLICABLE")
        record = deepcopy(self.assessment["requirements"][0])
        record["id"] = req["id"]
        self.assertIn("REQUIREMENT_APPLICABILITY_UNBOUND", check_scientific_support(record, req, self.load(), self.protocol)["guards"])


if __name__ == "__main__":
    unittest.main()
