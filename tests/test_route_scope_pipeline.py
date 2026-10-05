"""Synthetic source-scope pipeline controls, with no model or native answers.

The four-bit oracle certifies only the explicit declaration contract below.
Neither a passing control nor the opaque sample_id certifies scientific validity,
sample identity, operation classification, or real protocol completeness.
"""
from copy import deepcopy
from pathlib import Path
import unittest

from oeq_scientific import apply_assessment, build_context
from experiments.construct_validity.compact_grounding import (
    SCHEMA, build_compact_prompt_view,
)


ROUTES = ("alpha", "beta")
DECLARATIONS = ("DECLARE_F1", "DECLARE_F2")
METHOD = "FORMAL_METHOD"
QUESTION = {
    "question": (
        "Each complete alternative uses one FORMAL_METHOD and must explicitly "
        "declare both DECLARE_F1 and DECLARE_F2. Accept any complete alternative."
    ),
}


def declaration_present(mask, route_index, declaration_index):
    """Independent contract oracle: bits 0/1 are alpha, bits 2/3 are beta."""
    return bool(mask & (1 << (2 * route_index + declaration_index)))


def route_complete(mask, route_index):
    return all(declaration_present(mask, route_index, index) for index in (0, 1))


def exact_span(protocol, start, end):
    return {"start": start, "end": end, "quote": protocol[start:end]}


def synthetic_case(mask):
    """Build raw original text, record_refs, and a frozen declaration contract."""
    blocks, cursor, branches = [], 0, []
    for route_index, route in enumerate(ROUTES):
        lines = [
            "## Alternative " + route,
            "Chosen Method: " + METHOD,
            "### Records",
            "1. RECORD_BASELINE (Time: 1 h)",
        ]
        for index, token in enumerate(DECLARATIONS):
            if declaration_present(mask, route_index, index):
                lines.append(str(index + 2) + ". " + token + " (Time: 1 h)")
        block = "\n".join(lines) + "\n\n"
        blocks.append(block)
        branches.append({
            "id": route,
            "mode": "ALTERNATIVE",
            "sample_id": "opaque-unverified-key",
            "spans": [{"start": cursor, "end": cursor + len(block), "quote": block}],
        })
        cursor += len(block)
    protocol = "".join(blocks)
    requirements = [
        {
            "id": route + "_" + token,
            "kind": "TEXT",
            "necessary": True,
            "evidence_ids": [],
            "text": "Within complete alternative " + route + ", explicitly declare " + token,
            "scope": "ROUTE",
            "route_id": route,
            "literal_rule": {"type": "LITERAL_REQUIRED", "text": token},
        }
        for route in ROUTES for token in DECLARATIONS
    ]
    context = build_context(
        QUESTION,
        protocol,
        workspace=Path(__file__).parent / "absent_synthetic_workspace",
        study_context={
            "requirements": requirements,
            "cards": [],
            "method_keys": [METHOD],
            "route_methods": {route: METHOD for route in ROUTES},
            "extraction_mode": "record_refs",
        },
    )
    view = build_compact_prompt_view(context["source_record_catalog"])
    steps = []
    for segment in view["segments"]:
        if not segment["id"].startswith("R"):
            continue
        route = next(
            branch["id"] for branch in branches
            if branch["spans"][0]["start"] <= segment["start"]
            < segment["end"] <= branch["spans"][0]["end"]
        )
        steps.append({"id": "S" + str(len(steps)), "record_id": segment["id"], "branch": route})
    declarations = []
    for branch in branches:
        region = branch["spans"][0]
        start = protocol.index(METHOD, region["start"], region["end"])
        declarations.append({
            "name": METHOD, "branch": branch["id"],
            "span": exact_span(protocol, start, start + len(METHOD)),
        })
    # Deliberately propose SATISFIED even for a deleted local declaration.
    # The pipeline must verify the immutable contract and reject borrowed support.
    raw = {
        "extraction": {
            "schema_version": SCHEMA,
            "protocol_sha256": context["protocol_sha256"],
            "branches": branches,
            "steps": steps,
            "labels": [],
            "ri": [],
            "limitations": "Synthetic declaration control only.",
        },
        "assessment": {
            "schema_version": "judgment-grounding-v2",
            "requirements": [
                {
                    "id": requirement["id"],
                    "status": "SATISFIED",
                    "basis": "PROTOCOL_TEXT",
                    "evidence_ids": [],
                    "quotes": [requirement["literal_rule"]["text"]],
                    "reason": "Synthetic proposal, subject to route-local verification.",
                    "evidence_checks": [],
                }
                for requirement in requirements
            ],
            "limitations": "No scientific or sample identity claim.",
        },
        "objectives": {},
        "method_declarations": declarations,
    }
    return context, raw, protocol


class RouteScopePipelineTests(unittest.TestCase):
    def evaluate(self, context, raw, protocol):
        before = deepcopy(raw)
        result = apply_assessment(raw, context, protocol)
        self.assertEqual(raw, before)
        self.assertEqual(result["extraction_reference_audit"]["raw_payload"], before["extraction"])
        self.assertEqual(result["technical_status"], "VALID")
        self.assertIsNone(result["scientific_gold"])
        self.assertIsNone(result["experimental_success_claim"])
        self.assertIsNone(result["scientific_applicability_decision"]["independent_scientific_validation"])
        self.assertEqual(result["scientific_applicability_decision"]["status"], "UNRESOLVED")
        self.assertFalse(result["extraction_fidelity"]["completeness_certified"])
        coverage = result["extraction_reference_audit"]["coverage"]
        self.assertFalse(coverage["extraction_completeness_certified"])
        self.assertFalse(coverage["scientific_steps_certified"])
        for row in result["requirement_results"]:
            self.assertFalse(row["source_scope"]["sample_identity_certified"])
            self.assertIsNone(row["source_scope"]["scientific_truth"])
            self.assertIsNone(row["verification"]["scientific_truth"])
        return result

    def test_all_sixteen_declaration_masks_follow_independent_complete_route_oracle(self):
        for mask in range(16):
            with self.subTest(mask=format(mask, "04b")):
                context, raw, protocol = synthetic_case(mask)
                result = self.evaluate(context, raw, protocol)
                # Expectations come from the four retained/deleted bits alone.
                expected_routes = {
                    route: "SATISFIED" if route_complete(mask, index) else "UNDER_SPECIFIED"
                    for index, route in enumerate(ROUTES)
                }
                expected_overall = (
                    "SATISFIED" if route_complete(mask, 0) or route_complete(mask, 1)
                    else "UNDER_SPECIFIED"
                )
                self.assertEqual(result["overall"], expected_overall)
                self.assertEqual(result["objectives"]["constraints"]["complete_contract"], expected_overall)
                self.assertEqual(
                    {row["route_id"]: row["status"] for row in result["route_results"]},
                    expected_routes,
                )
                self.assertTrue(all(row["single_method_identity_verified"] for row in result["route_results"]))
                self.assertEqual(result["method_identity"]["status"], "SATISFIED")
                rows = {row["id"]: row for row in result["requirement_results"]}
                for route_index, route in enumerate(ROUTES):
                    region = raw["extraction"]["branches"][route_index]["spans"][0]
                    for declaration_index, token in enumerate(DECLARATIONS):
                        row = rows[route + "_" + token]
                        expected = (
                            "SATISFIED" if declaration_present(mask, route_index, declaration_index)
                            else "UNDER_SPECIFIED"
                        )
                        self.assertEqual(row["proposed_status"], "SATISFIED")
                        self.assertEqual(row["verification"]["status"], expected)
                        self.assertEqual(row["effective_status"], expected)
                        self.assertEqual(row["source_scope"]["scope_status"], "RESOLVED")
                        self.assertEqual(row["source_scope"]["regions"], [region])
                audit = result["extraction_reference_audit"]
                coverage = audit["coverage"]
                self.assertEqual(coverage["candidate_count"], 2 + mask.bit_count())
                self.assertEqual(coverage["selected_count"], 2 + mask.bit_count())
                self.assertEqual(coverage["omitted_record_ids"], [])
                self.assertEqual(
                    coverage["requested_record_ids"],
                    [step["record_id"] for step in raw["extraction"]["steps"]],
                )
                # End-to-end expansion keeps distinct original occurrences and branches.
                facts = result["extraction_fidelity"]["facts"]
                self.assertEqual(len(facts), 2 + mask.bit_count())
                for fact in facts:
                    anchor = fact["record_anchor"]
                    region = next(branch["spans"][0] for branch in raw["extraction"]["branches"]
                                  if branch["id"] == fact["branch"])
                    self.assertEqual(protocol[anchor["start"]:anchor["end"]], anchor["quote"])
                    self.assertLessEqual(region["start"], anchor["start"])
                    self.assertLessEqual(anchor["end"], region["end"])

    def test_complete_second_alternative_is_accepted_without_first_alternative(self):
        context, raw, protocol = synthetic_case(0b1100)
        result = self.evaluate(context, raw, protocol)
        self.assertEqual(result["overall"], "SATISFIED")
        routes = {row["route_id"]: row for row in result["route_results"]}
        self.assertEqual(routes["alpha"]["status"], "UNDER_SPECIFIED")
        self.assertEqual(routes["beta"]["status"], "SATISFIED")
        self.assertTrue(routes["beta"]["single_method_identity_verified"])

    def test_complementary_partial_routes_cannot_borrow_short_quotes(self):
        context, raw, protocol = synthetic_case(0b1001)
        result = self.evaluate(context, raw, protocol)
        rows = {row["id"]: row for row in result["requirement_results"]}
        for requirement_id in ("alpha_DECLARE_F2", "beta_DECLARE_F1"):
            with self.subTest(requirement_id=requirement_id):
                row = rows[requirement_id]
                audit = row["requirement_scope_audit"]
                quote = audit["quote_audits"][0]
                self.assertEqual(row["effective_status"], "UNDER_SPECIFIED")
                self.assertIn("QUOTATION_OUTSIDE_REQUIREMENT_SCOPE", row["guards"])
                self.assertFalse(audit["has_local_decisive_anchor"])
                self.assertEqual(quote["status"], "QUOTATION_OUTSIDE_REQUIREMENT_SCOPE")
                self.assertEqual(len(quote["occurrences"]), 1)
                self.assertEqual(quote["local_occurrences"], [])
                self.assertIsNone(quote["source_span"])
        self.assertEqual(result["overall"], "UNDER_SPECIFIED")
        self.assertTrue(all(row["status"] == "UNDER_SPECIFIED" for row in result["route_results"]))

    def test_whole_protocol_quote_cannot_decide_even_textually_complete_routes(self):
        context, raw, protocol = synthetic_case(0b1111)
        for row in raw["assessment"]["requirements"]:
            row["quotes"] = [protocol]
        result = self.evaluate(context, raw, protocol)
        self.assertEqual(result["overall"], "UNRESOLVED")
        for row in result["requirement_results"]:
            self.assertEqual(row["quotes"], [protocol])
            self.assertEqual(row["verification"]["status"], "SATISFIED")
            self.assertEqual(row["effective_status"], "UNRESOLVED")
            audit = row["requirement_scope_audit"]
            self.assertFalse(audit["has_local_decisive_anchor"])
            self.assertIn("PROTOCOL_WIDE_QUOTATION_NOT_LOCAL", row["guards"])
            self.assertIn("REQUIREMENT_DECISION_NOT_GROUNDED_IN_ITS_ROUTE", row["guards"])
            self.assertEqual(audit["quote_audits"][0]["local_occurrences"], [])
            self.assertIsNone(audit["quote_audits"][0]["source_span"])
        self.assertTrue(all(row["status"] == "UNRESOLVED" for row in result["route_results"]))

    def test_local_anchor_does_not_sanitize_an_additional_whole_protocol_quote(self):
        context, raw, protocol = synthetic_case(0b1111)
        for row in raw["assessment"]["requirements"]:
            row["quotes"].append(protocol)
        result = self.evaluate(context, raw, protocol)
        self.assertEqual(result["overall"], "UNRESOLVED")
        for row in result["requirement_results"]:
            self.assertTrue(row["requirement_scope_audit"]["has_local_decisive_anchor"])
            self.assertEqual(row["requirement_scope_audit"]["status"], "UNRESOLVED")
            self.assertEqual(row["effective_status"], "UNRESOLVED")

    def test_repeated_declarations_keep_the_correct_local_original_anchor(self):
        context, raw, protocol = synthetic_case(0b1111)
        result = self.evaluate(context, raw, protocol)
        self.assertEqual(result["overall"], "SATISFIED")
        for row in result["requirement_results"]:
            quote = row["requirement_scope_audit"]["quote_audits"][0]
            region = row["source_scope"]["regions"][0]
            start = protocol.index(quote["quote"], region["start"], region["end"])
            expected = exact_span(protocol, start, start + len(quote["quote"]))
            self.assertEqual(quote["status"], "ANCHORED_IN_SCOPE")
            self.assertEqual(len(quote["occurrences"]), 2)
            self.assertEqual(quote["local_occurrences"], [expected])
            self.assertEqual(quote["source_span"], expected)
            self.assertTrue(quote["ambiguous_location"])
            self.assertFalse(quote["ambiguous_local_location"])

    def test_empty_named_branch_span_is_rejected_before_assessment(self):
        for route_index in (0, 1):
            with self.subTest(route=ROUTES[route_index]):
                context, raw, protocol = synthetic_case(0b1111)
                raw["extraction"]["branches"][route_index]["spans"] = []
                before = deepcopy(raw)
                with self.assertRaisesRegex(ValueError, "Named alternatives require original branch anchors"):
                    apply_assessment(raw, context, protocol)
                self.assertEqual(raw, before)

    def test_partial_branch_span_cannot_authorize_its_record_references(self):
        for route_index in (0, 1):
            with self.subTest(route=ROUTES[route_index]):
                context, raw, protocol = synthetic_case(0b1111)
                branch = raw["extraction"]["branches"][route_index]
                start = branch["spans"][0]["start"]
                end = protocol.index("1. RECORD_BASELINE", start)
                branch["spans"] = [exact_span(protocol, start, end)]
                with self.assertRaisesRegex(ValueError, "outside assigned branch"):
                    apply_assessment(raw, context, protocol)

    def test_partial_header_regions_are_never_extended_to_omitted_declarations(self):
        context, raw, protocol = synthetic_case(0b1111)
        for branch in raw["extraction"]["branches"]:
            start = branch["spans"][0]["start"]
            end = protocol.index("1. RECORD_BASELINE", start)
            branch["spans"] = [exact_span(protocol, start, end)]
        raw["extraction"]["steps"] = []
        result = self.evaluate(context, raw, protocol)
        self.assertEqual(result["overall"], "UNDER_SPECIFIED")
        self.assertEqual(result["extraction_reference_audit"]["coverage"]["selected_count"], 0)
        self.assertEqual(len(result["extraction_reference_audit"]["coverage"]["omitted_record_ids"]), 6)
        for row in result["requirement_results"]:
            branch = next(branch for branch in raw["extraction"]["branches"]
                          if branch["id"] == row["source_scope"]["route_id"])
            self.assertEqual(row["source_scope"]["regions"], branch["spans"])
            self.assertEqual(row["verification"]["status"], "UNDER_SPECIFIED")
            self.assertEqual(row["effective_status"], "UNDER_SPECIFIED")
            self.assertFalse(row["requirement_scope_audit"]["has_local_decisive_anchor"])

    def test_unresolved_fragment_cannot_be_dropped_from_record_ref_branch_spans(self):
        context, raw, protocol = synthetic_case(0b1111)
        # One exact span plus one repeated quote-only fragment is only partially
        # locatable. The strict record_refs boundary must reject the raw branch.
        raw["extraction"]["branches"][0]["spans"].append({"quote": "### Records"})
        with self.assertRaises(ValueError):
            apply_assessment(raw, context, protocol)


if __name__ == "__main__":
    unittest.main()