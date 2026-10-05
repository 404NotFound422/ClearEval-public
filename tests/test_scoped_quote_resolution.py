import unittest
from copy import deepcopy
from experiments.construct_validity.fidelity import audit_extraction, audit_field, quote_span_candidates
from experiments.construct_validity.contract import validate_extraction
from oeq_scientific import build_context, apply_assessment


def support(text, offset=None):
    span={"quote":text} if offset is None else {"start":offset,"end":offset+len(text),"quote":text}
    return dict(kind="EXPLICIT",raw_value=text,transform="IDENTITY",spans=[span])


def row(quote, operation="wash", duration="10 minutes", phase=None):
    missing=dict(kind="MISSING",raw_value=None,spans=[])
    return dict(id="s1",branch="main",phase=phase,operation=operation,duration_text=duration,
                quote=quote,assertion=dict(polarity="AFFIRMED"),field_support={
                    "phase":deepcopy(missing) if phase is None else support(phase),
                    "operation":support(operation),"duration_text":support(duration)})


def extraction(record):
    return dict(schema_version="extraction-grounding-v2",branches=[dict(id="main",mode="SERIAL",sample_id="main",spans=[])],
                labels=[],steps=[record],ri=[],limitations="")


def audit(value,text):
    return audit_extraction(value,text,field_scope_policy="diagnostic")


class ScopedQuoteResolutionTests(unittest.TestCase):
    def test_unique_record_binds_globally_repeated_duration(self):
        text="wash 10 minutes; store 10 minutes"
        result=audit(extraction(row("wash 10 minutes")),text)
        duration=result["facts"][0]["fields"]["duration_text"]
        self.assertEqual(duration["status"],"GROUNDED")
        self.assertEqual(duration["spans"][0]["start"],5)
        self.assertEqual(len(duration["candidate_spans"]),2)
        self.assertTrue(result["scoring_eligible"])

    def test_explicit_occurrence_anchors_repeated_record(self):
        text="wash 10 minutes; wash 10 minutes"
        value=extraction(row("wash 10 minutes"))
        value["steps"][0]["field_support"]["operation"]=support("wash",17)
        result=audit(value,text)
        fields=result["facts"][0]["fields"]
        self.assertEqual(fields["duration_text"]["spans"][0]["start"],22)
        self.assertEqual(result["facts"][0]["record_anchor"]["start"],17)
        self.assertTrue(result["scoring_eligible"])

    def test_unanchored_repeated_record_abstains_without_fake_offsets(self):
        text="wash 10 minutes; wash 10 minutes"
        result=audit(extraction(row("wash 10 minutes")),text)
        item=result["facts"][0]["fields"]["operation"]
        self.assertEqual(item["spans"],[])
        self.assertEqual(item["status"],"REVIEW_REQUIRED")
        self.assertFalse(result["scoring_eligible"])
        self.assertEqual(result["validated"]["steps"][0]["field_support"]["operation"]["spans"],[{"quote":"wash"}])

    def test_same_record_twice_cannot_choose_first_short_term(self):
        text="wash 10 minutes then store 10 minutes"
        value=extraction(row(text))
        result=audit(value,text)
        item=result["facts"][0]["fields"]["duration_text"]
        self.assertEqual(item["spans"],[])
        self.assertEqual(item["status"],"REVIEW_REQUIRED")

    def test_two_explicit_fields_cannot_borrow_different_record_occurrences(self):
        text="wash 10 minutes; wash 10 minutes"
        value=extraction(row("wash 10 minutes"))
        value["steps"][0]["field_support"]["operation"]=support("wash",0)
        value["steps"][0]["field_support"]["duration_text"]=support("10 minutes",22)
        result=audit(value,text)
        self.assertFalse(result["scoring_eligible"])
        self.assertIn("FIELD_RECORD_OCCURRENCE_CONFLICT",[i["code"] for i in result["issues"]])

    def test_ambiguous_branch_is_preserved_and_blocks_fact_certification(self):
        text="MACS: wash 10 minutes; MACS comparison"
        value=extraction(row("wash 10 minutes"))
        value["branches"][0]["spans"]=[{"quote":"MACS"}]
        result=validate_extraction(value,text,field_scope_policy="diagnostic")
        branch=result["branches"][0]
        self.assertEqual(branch["spans"],[{"quote":"MACS"}])
        self.assertEqual(branch["resolved_spans"],[])
        self.assertEqual(branch["location_status"],"REVIEW_REQUIRED")
        self.assertFalse(result["scoring_eligible"])
        self.assertIn("BRANCH_LOCATION_UNPROVEN",[i["code"] for i in result["field_audit"]["issues"]])

    def test_resolved_short_branch_is_not_expanded(self):
        text="MACS: wash 10 minutes"
        value=extraction(row("wash 10 minutes"))
        value["branches"][0]["spans"]=[{"quote":"MACS"}]
        result=audit(value,text)
        self.assertFalse(result["scoring_eligible"])
        self.assertEqual(result["validated"]["branches"][0]["resolved_spans"][0]["end"],4)

    def test_parent_heading_can_resolve_duplicate_heading_term(self):
        text="## processing\nwash 10 minutes\n## comparison\nprocessing discussion"
        result=audit(extraction(row("wash 10 minutes",phase="processing")),text)
        item=result["facts"][0]["fields"]["phase"]
        self.assertEqual(item["status"],"GROUNDED")
        self.assertEqual(item["spans"][0]["start"],3)
        self.assertEqual(item["scope_binding"]["rule"],"EXPLICIT_PARENT_HEADING_REGION_V1")

    def test_explicit_offsets_never_fall_back_to_search(self):
        value=extraction(row("wash 10 minutes"))
        value["steps"][0]["field_support"]["operation"]=support("wash",1)
        with self.assertRaisesRegex(ValueError,"offset/quotation mismatch"):
            audit(value,"wash 10 minutes")

    def test_value_paraphrase_and_case_mismatch_remain_hard_errors(self):
        for value, quote in [("Nuclei","nuclei"),("Wash with PBS","Wash the fixed sample with PBS")]:
            record=row(quote,operation=value,duration=None)
            record["field_support"]["operation"]=support(quote)
            record["field_support"]["operation"]["raw_value"]=value
            record["field_support"]["duration_text"]=dict(kind="MISSING",raw_value=None,spans=[])
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,"no bound original text"):
                audit(extraction(record),quote)

    def test_overlapping_locations_are_not_globally_unique(self):
        ref=quote_span_candidates("aaaa",{"quote":"aaa"})
        self.assertEqual([s["start"] for s in ref["candidate_spans"]],[0,1])
        self.assertIsNone(ref["resolved_span"])

    def test_null_missing_field_cannot_hide_ambiguous_support(self):
        for text in ("wash", "wash; wash"):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,"Null must"):
                audit_field(None,dict(kind="MISSING",raw_value=None,spans=[{"quote":"wash"}]),
                            text,field_scope_policy="diagnostic")

    def test_sidecar_collects_hard_errors_and_ambiguities_without_certification(self):
        from oeq_scientific import diagnose_assessment
        text="wash 10 minutes; wash 10 minutes; nuclei"
        value=extraction(row("wash 10 minutes",operation="Wash"))
        value["steps"][0]["field_support"]["operation"]=support("wash")
        value["steps"][0]["field_support"]["operation"]["raw_value"]="Wash"
        second=row("nuclei",operation="Nuclei",duration=None)
        second["id"]="s2"
        second["field_support"]["operation"]=support("nuclei")
        second["field_support"]["operation"]["raw_value"]="Nuclei"
        second["field_support"]["duration_text"]=dict(kind="MISSING",raw_value=None,spans=[])
        value["steps"].append(second)
        diag=diagnose_assessment(dict(extraction=value),text)
        self.assertEqual(len(diag["hard_errors"]),2)
        self.assertEqual(diag["ambiguous_locations"],2)
        self.assertFalse(diag["certification"])
        self.assertNotIn("effective_status",diag)
        with self.assertRaises(ValueError):audit(value,text)

    def test_strict_policy_still_requires_explicit_offsets(self):
        with self.assertRaisesRegex(ValueError,"Span needs"):
            audit_extraction(extraction(row("wash 10 minutes")),"wash 10 minutes")

    def test_absent_quote_and_extra_span_key_remain_hard_errors(self):
        for span in ({"quote":"absent"},{"quote":"wash","unknown":True}):
            with self.subTest(span=span),self.assertRaises(ValueError):
                quote_span_candidates("wash",span)

    def _method(self,text):
        requirement=dict(id="M",kind="TEXT",necessary=True,evidence_ids=[],text="selected method",literal_rule=dict(type="METHOD_IDENTITY_SINGLE"))
        context=build_context({},text,study_context={"requirements":[requirement],"method_keys":["MACS"]})
        raw=dict(extraction=extraction(row("wash 10 minutes")),assessment=dict(schema_version="judgment-grounding-v2",limitations="",requirements=[
            dict(id="M",status="SATISFIED",basis="PROTOCOL_TEXT",evidence_ids=[],quotes=[text],reason="original",evidence_checks=[])]),
            objectives={},method_declarations=[dict(name="MACS",branch="main",span={"quote":"MACS"})])
        return apply_assessment(raw,context,text)

    def test_one_exact_selected_occurrence_accepts_repeated_comparison_name(self):
        result=self._method("Chosen Method: MACS\nwash 10 minutes\nCompare MACS")
        self.assertEqual(result["method_identity"]["status"],"SATISFIED")
        self.assertEqual(result["method_identity"]["declarations"][0]["name_span"]["start"],15)

    def test_active_use_cannot_disambiguate_repeated_method_against_explicit_other_choice(self):
        result=self._method("Comparison MACS\nUse MACS\nChosen Method: CUBIC\nwash 10 minutes")
        self.assertEqual(result["method_identity"]["status"],"UNRESOLVED")

    def test_resolved_method_location_metadata_agrees_with_bound_span(self):
        result=self._method("Chosen Method: MACS\nwash 10 minutes\nCompare MACS")
        declared=result["method_identity"]["declarations"][0]
        self.assertEqual(declared["quote_resolution"]["resolved_span"]["start"],declared["name_span"]["start"])
        self.assertEqual(declared["quote_resolution"]["rule"],"UNIQUE_EXPLICIT_SELECTED_METHOD_OCCURRENCE")

    def test_unique_active_name_cannot_hide_other_explicit_chosen_method(self):
        result=self._method("Use MACS\nChosen Method: CUBIC\nwash 10 minutes")
        self.assertEqual(result["method_identity"]["status"],"UNRESOLVED")

    def test_literal_rule_never_chooses_occurrence_for_ambiguous_extraction(self):
        from tests.test_oeq_scientific import literal_case
        _,raw,original=literal_case()
        text=original+"; MACS RI = 1.53"
        raw["extraction"]["ri"][0]["field_support"]["solution"]=support("MACS")
        raw["extraction"]["ri"][0]["field_support"]["value_text"]=support("1.53")
        previous,_,_=literal_case()
        context=build_context({},text,study_context={"requirements":previous["requirements"],"cards":previous["cards"]})
        result=apply_assessment(raw,context,text)
        self.assertEqual(result["technical_status"],"VALID")
        self.assertEqual(result["requirement_results"][0]["effective_status"],"UNRESOLVED")
        self.assertFalse(result["extraction_fidelity"]["scoring_eligible"])

    def test_selected_label_field_on_same_line_is_not_another_selected_method(self):
        for separator in (";", "\uFF1B"):
            result=self._method("Chosen Method: MACS"+separator+" Chosen Labeling: DAPI\nwash 10 minutes")
            self.assertEqual(result["method_identity"]["status"],"SATISFIED")

    def test_two_explicit_selections_abstain_even_for_same_method_name(self):
        result=self._method("Chosen Method: MACS\nwash 10 minutes\nChosen Method: MACS")
        self.assertEqual(result["method_identity"]["status"],"UNRESOLVED")
        self.assertIsNone(result["method_identity"]["declarations"][0]["span"])


if __name__ == "__main__":
    unittest.main()
