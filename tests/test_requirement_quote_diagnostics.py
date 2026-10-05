"""Engineering quotation diagnostics; no independent scientific reference."""
from copy import deepcopy
import unittest

from experiments.construct_validity.contract import JUDGMENT_SCHEMA, adjudicate


def requirement(key, kind="TEXT"):
    return {"id": key, "kind": kind, "necessary": True,
            "text": "Engineering requirement " + key, "evidence_ids": []}


def judgment(key, quotes, status="SATISFIED"):
    return {"id": key, "status": status, "basis": "PROTOCOL_TEXT", "evidence_ids": [],
            "quotes": quotes, "reason": "Engineering fixture only", "evidence_checks": []}


def value(rows):
    return {"schema_version": JUDGMENT_SCHEMA, "requirements": rows,
            "limitations": "Not a scientific success test"}


class RequirementQuoteDiagnosticsTests(unittest.TestCase):
    def test_invalid_quote_is_local_preserved_and_has_no_invented_source_span(self):
        protocol = "Use M. Wash."
        raw = value([judgment("bad", ["The source says M is compatible."]), judgment("good", ["Wash."])])
        result = adjudicate(raw, [requirement("bad"), requirement("good")], protocol, [], quotation_policy="diagnostic")
        bad, good = result["requirements"]
        self.assertEqual(raw["requirements"][0]["quotes"], bad["quotes"])
        self.assertEqual(bad["effective_status"], "UNRESOLVED")
        self.assertEqual(good["effective_status"], "SATISFIED")
        self.assertEqual(bad["anchors"], [])
        self.assertIsNone(bad["protocol_quote_audits"][0]["source_span"])
        self.assertEqual(bad["protocol_quote_audits"][0]["occurrences"], [])
        self.assertEqual(set(bad["guards"]), {"INVALID_PROTOCOL_QUOTATION", "MISSING_DECISIVE_PROTOCOL_ANCHOR"})
        self.assertEqual(result["overall"], "UNRESOLVED")
        self.assertEqual(result["scientific_validation"], "PENDING_INDEPENDENT_REFERENCE")

    def test_one_valid_quote_does_not_sanitize_another_invalid_quote(self):
        raw = value([judgment("r", ["Wash", "Invented source sentence"])])
        result = adjudicate(raw, [requirement("r")], "Wash", [], quotation_policy="diagnostic")
        row = result["requirements"][0]
        self.assertEqual(row["effective_status"], "UNRESOLVED")
        self.assertEqual(len(row["anchors"]), 1)
        self.assertEqual(row["protocol_quote_audits"][0]["source_span"], {"start": 0, "end": 4, "quote": "Wash"})
        self.assertIsNone(row["protocol_quote_audits"][1]["source_span"])
        self.assertNotIn("MISSING_DECISIVE_PROTOCOL_ANCHOR", row["guards"])

    def test_empty_or_absent_decisive_quotes_do_not_terminate_other_requirements(self):
        for quotes in ([], [""], ["   "]):
            with self.subTest(quotes=quotes):
                result = adjudicate(value([judgment("r", quotes)]), [requirement("r")], "Wash", [], quotation_policy="diagnostic")
                row = result["requirements"][0]
                self.assertEqual(row["effective_status"], "UNRESOLVED")
                self.assertIn("MISSING_DECISIVE_PROTOCOL_ANCHOR", row["guards"])
                if quotes:
                    self.assertIsNone(row["protocol_quote_audits"][0]["source_span"])
                    self.assertEqual(row["protocol_quote_audits"][0]["reason"], "EMPTY_QUOTATION")

    def test_evidence_ablation_cannot_restore_decisive_invalid_anchor_proposal(self):
        for state in ("SATISFIED", "VIOLATED"):
            for guard in (True, False):
                with self.subTest(state=state, evidence_guard=guard):
                    result = adjudicate(value([judgment("r", ["Elsewhere"], state)]), [requirement("r")], "Wash", [],
                                        quotation_policy="diagnostic", evidence_guard=guard)
                    self.assertEqual(result["requirements"][0]["proposed_status"], state)
                    self.assertEqual(result["requirements"][0]["effective_status"], "UNRESOLVED")

    def test_existing_unknown_states_remain_unknown_with_visible_quote_guard(self):
        for state in ("UNRESOLVED", "UNDER_SPECIFIED"):
            result = adjudicate(value([judgment("r", ["Elsewhere"], state)]), [requirement("r")], "Wash", [], quotation_policy="diagnostic")
            self.assertEqual(result["requirements"][0]["effective_status"], state)
            self.assertIn("INVALID_PROTOCOL_QUOTATION", result["requirements"][0]["guards"])

    def test_scientific_requirement_cannot_pass_invalid_quote_even_without_evidence_guard(self):
        result = adjudicate(value([judgment("science", ["Source statement"])]), [requirement("science", "SCIENTIFIC")],
                            "Wash", [], quotation_policy="diagnostic", evidence_guard=False)
        self.assertEqual(result["requirements"][0]["effective_status"], "UNRESOLVED")
        self.assertEqual(result["overall"], "UNRESOLVED")
        self.assertEqual(result["scientific_validation"], "PENDING_INDEPENDENT_REFERENCE")

    def test_nontext_quotes_unknown_source_schema_and_bad_polarities_are_still_technical_failures(self):
        base = value([judgment("r", ["Wash"])])
        nontext = deepcopy(base); nontext["requirements"][0]["quotes"] = [42]
        source = deepcopy(base); source["requirements"][0]["evidence_ids"] = ["UNKNOWN"]
        schema = deepcopy(base); schema["requirements"][0]["unknown"] = True
        state = deepcopy(base); state["requirements"][0]["status"] = "MAYBE"
        for raw in (nontext, source, schema, state):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                adjudicate(raw, [requirement("r")], "Wash", [], quotation_policy="diagnostic")

    def test_strict_default_retains_original_failures_and_output_shape(self):
        for quotes in ([], [""], ["Elsewhere"]):
            with self.subTest(quotes=quotes), self.assertRaises(ValueError):
                adjudicate(value([judgment("r", quotes)]), [requirement("r")], "Wash", [])
        result = adjudicate(value([judgment("r", ["Wash"])]), [requirement("r")], "Wash", [])
        self.assertEqual(result["requirements"][0]["effective_status"], "SATISFIED")
        self.assertNotIn("protocol_quote_audits", result["requirements"][0])
        self.assertNotIn("quotation_policy", result)

    def test_repeated_real_quote_retains_ambiguity_without_choosing_a_location(self):
        result = adjudicate(value([judgment("r", ["Wash"])]), [requirement("r")], "Wash then Wash", [], quotation_policy="diagnostic")
        audit = result["requirements"][0]["protocol_quote_audits"][0]
        self.assertTrue(audit["ambiguous_location"])
        self.assertIsNone(audit["source_span"])
        self.assertEqual(len(audit["occurrences"]), 2)

    def test_unknown_policy_is_not_a_silent_relaxation(self):
        with self.assertRaisesRegex(ValueError, "quotation policy"):
            adjudicate(value([judgment("r", ["Wash"])]), [requirement("r")], "Wash", [], quotation_policy="allow")


if __name__ == "__main__":
    unittest.main()
