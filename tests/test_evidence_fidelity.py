"""Synthetic engineering fixtures only: no model, network or scientific labels."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.construct_validity.contract import (
    JUDGMENT_SCHEMA, adjudicate, digest, read, save, validate_extraction)
from experiments.construct_validity.evidence import (
    SCHEMA as EVIDENCE_SCHEMA, make_entailment_verification, scope_leaves, validate_cards)
from experiments.construct_validity.fidelity import (
    SCHEMA as EXTRACTION_SCHEMA, audit_facts, audit_field, text_hash)
from experiments.construct_validity.materials import requirement
from experiments.construct_validity.review import export_review, import_extraction_references, import_ratings


def support(text, raw, start=None, *, kind="EXPLICIT", transform="IDENTITY"):
    if raw is None:
        return {"kind":"MISSING","raw_value":None,"spans":[]}
    start = text.index(raw) if start is None else start
    return {"kind":kind,"raw_value":raw,"transform":transform,
            "spans":[{"start":start,"end":start+len(raw),"quote":raw}]}


def extraction(text="Use DiI"):
    row={"id":"L1","branch":"main","target":None,"probe":"DiI","fluorophore":"DiI","channel":None,
         "quote":text,"assertion":{"polarity":"AFFIRMED"}}
    row["field_support"]={k:support(text,row[k]) for k in ("target","probe","fluorophore","channel")}
    return {"schema_version":EXTRACTION_SCHEMA,
            "branches":[{"id":"main","mode":"SERIAL","sample_id":"sample","spans":[]}],
            "labels":[row],"steps":[],"ri":[],"limitations":"SYNTHETIC ENGINEERING ONLY"}


def source_fixture(relation="SUPPORTS"):
    text="Synthetic M v1 preserves S in 1 to 3 cm at 4 C."
    scope={"objects":["S"],"method":"M","method_version":"v1",
           "size":{"min":1,"max":3,"unit":"cm"},"conditions":{"temperature":"4 C"}}
    card={"schema_version":EVIDENCE_SCHEMA,"id":"E","identity":{"url":"https://example.org/synthetic",
          "version":"v1","publication_status":"CURRENT","correction_chain":[]},
          "source_document":{"text":text,"sha256":text_hash(text),"version":"v1","url":"https://example.org/synthetic"},
          "passages":[{"id":"P","start":0,"end":len(text),"quote":text,"sha256":text_hash(text)}],
          "applicability":scope,"scope_support":{k:support(text,str(v)) for k,v in scope_leaves(scope).items()}}
    context={"objects":["S"],"method":"M","method_version":"v1","size":{"value":2,"unit":"cm"},
             "conditions":{"temperature":"4 C"}}
    req=requirement("H","Synthetic M v1 preserves S.","SCIENTIFIC",["E"],applicability=context,protocol_fields=["method"])
    proof=make_entailment_verification(card,["P"],req["text"],context,lambda data:{"relation":relation},
              verifier_id="SYNTHETIC_CHECKER",verifier_revision="fixture-v1",response_origin="SYNTHETIC_ENGINEERING_FIXTURE")
    card["entailment_verifications"]=[proof]
    protocol="Use M v1 for S at 4 C."
    check={"source_id":"E","passage_ids":["P"],"claim":req["text"],"relation":"SUPPORTS",
           "verification_id":proof["id"],"applicability":deepcopy(context),
           "protocol_bindings":{"method":{"value":"M","support":support(protocol,"M")}}}
    value={"schema_version":JUDGMENT_SCHEMA,"requirements":[{"id":"H","status":"SATISFIED",
           "basis":"SUPPLIED_EVIDENCE","evidence_ids":["E"],"quotes":["Use M"],"reason":"synthetic only",
           "evidence_checks":[check]}],"limitations":"not scientific evidence"}
    return card,req,protocol,value


class FidelityTests(unittest.TestCase):
    def test_field_bound_to_original_not_just_real_quote(self):
        value=extraction()
        value["labels"][0]["probe"]="DiD"
        with self.assertRaises(ValueError): validate_extraction(value,"Use DiI")

    def test_grounded_fields_are_distinct_from_scientific_truth(self):
        value=validate_extraction(extraction(),"Use DiI")
        self.assertTrue(value["scoring_eligible"])
        self.assertEqual(value["field_audit"]["facts"][0]["fields"]["probe"]["kind"],"EXPLICIT")
        self.assertIn("scientific truth",value["validation_scope"])

    def test_null_is_distinct_from_omitted_key(self):
        value=extraction()
        self.assertIsNone(validate_extraction(value,"Use DiI")["labels"][0]["target"])
        del value["labels"][0]["target"]
        with self.assertRaises(ValueError): validate_extraction(value,"Use DiI")

    def test_inferred_is_retained_without_authorizing_facts(self):
        value=extraction()
        value["labels"][0]["probe"]="inferred probe"
        value["labels"][0]["field_support"]["probe"]={"kind":"INFERRED","spans":[]}
        audited=validate_extraction(value,"Use DiI")
        self.assertFalse(audited["scoring_eligible"])
        self.assertEqual(audited["labels"][0]["probe"],"inferred probe")

    def test_negation_context_cannot_be_dropped_by_short_quote(self):
        text="Do not use DiI"
        value=extraction(text)
        value["labels"][0]["quote"]="DiI"
        self.assertFalse(validate_extraction(value,text)["scoring_eligible"])
        value["labels"][0]["assertion"]["polarity"]="NEGATED"
        self.assertTrue(validate_extraction(value,text)["scoring_eligible"])

    def test_condition_context_retained(self):
        text="If compatible, use DiI"
        value=extraction(text)
        self.assertFalse(validate_extraction(value,text)["scoring_eligible"])
        value["labels"][0]["assertion"]["polarity"]="CONDITIONAL"
        self.assertTrue(validate_extraction(value,text)["scoring_eligible"])

    def test_explicit_declared_unit_conversion_and_overnight(self):
        a=audit_field("2 h",support("120 min","120 min",kind="DERIVED",transform="MINUTES_TO_HOURS"),"120 min")
        self.assertEqual(a["status"],"GROUNDED")
        with self.assertRaises(ValueError):
            audit_field("8 h",support("overnight","overnight",kind="DERIVED",transform="MINUTES_TO_HOURS"),"overnight")

    def test_offset_occurrence_is_not_interchangeable(self):
        value=extraction()
        value["labels"][0]["field_support"]["probe"]["spans"][0]["start"]=0
        with self.assertRaises(ValueError): validate_extraction(value,"Use DiI")

    def test_reordering_or_reusing_step_occurrences_requires_review(self):
        text="wash; dry; wash"
        rows=[]
        for i,(operation,start) in enumerate((("wash",0),("dry",6),("wash",11))):
            rows.append({"id":str(i),"branch":"main","phase":None,"operation":operation,"duration_text":None,
                         "quote":operation,"assertion":{"polarity":"AFFIRMED"},
                         "field_support":{"phase":support(text,None),"operation":support(text,operation,start),
                                          "duration_text":support(text,None)}})
        value=extraction("Use DiI")
        value["labels"]=[];value["steps"]=rows
        self.assertTrue(validate_extraction(value,text)["scoring_eligible"])
        value["steps"]=[rows[1],rows[0],rows[2]]
        self.assertFalse(validate_extraction(value,text)["scoring_eligible"])
        value["steps"]=[rows[0],deepcopy(rows[0])]
        value["steps"][1]["id"]="different-id"
        self.assertFalse(validate_extraction(value,text)["scoring_eligible"])

    def test_named_branch_without_original_anchor_rejected(self):
        value=extraction()
        value["branches"]=[{"id":"A","sample_id":"sample","mode":"ALTERNATIVE","spans":[]}]
        value["labels"][0]["branch"]="A"
        with self.assertRaises(ValueError): validate_extraction(value,"Use DiI")

    def test_empty_extraction_does_not_prove_faithfulness(self):
        value=extraction();value["labels"]=[]
        self.assertFalse(validate_extraction(value,"Use DiI")["scoring_eligible"])

    def test_legacy_fields_remain_diagnostic(self):
        value=extraction()
        del value["schema_version"];del value["branches"]
        for row in value["labels"]:
            del row["assertion"];del row["field_support"]
        row["probe"]="not in quote"
        audit=validate_extraction(value,"Use DiI")
        self.assertFalse(audit["scoring_eligible"])
        self.assertEqual(audit["field_audit"]["fidelity_status"],"LEGACY_STRUCTURE_ONLY")


class EvidenceTests(unittest.TestCase):
    def test_complete_binding_remains_model_science_proposal(self):
        card,req,text,value=source_fixture()
        result=adjudicate(value,[req],text,[card])
        self.assertEqual(result["overall"],"SATISFIED")
        self.assertFalse(result["requirements"][0]["evidence_audit"]["certified_truth"])
        self.assertEqual(result["scientific_validation"],"PENDING_INDEPENDENT_REFERENCE")

    def test_true_scope_fake_entailment_does_not_pass(self):
        card,req,text,value=source_fixture("NOINFO")
        result=adjudicate(value,[req],text,[card])
        self.assertEqual(result["overall"],"UNRESOLVED")
        self.assertIn("MAIN_PROPOSAL_DISAGREES_WITH_SEPARATE_ENTAILMENT_CHECK",result["requirements"][0]["guards"])

    def test_self_declared_relation_without_separate_checker_is_unresolved(self):
        card,req,text,value=source_fixture()
        card["entailment_verifications"]=[]
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_check_cannot_be_transferred_to_different_hypothesis(self):
        card,req,text,value=source_fixture()
        value["requirements"][0]["evidence_checks"][0]["claim"]="Different claim"
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_source_document_hash_span_and_version_tampering_rejected(self):
        for change in ("text","span","version"):
            card,req,text,value=source_fixture()
            if change=="text": card["source_document"]["text"]+=" changed"
            elif change=="span": card["passages"][0]["start"]=1
            else: card["identity"]["version"]="v2"
            with self.assertRaises(ValueError): adjudicate(value,[req],text,[card])

    def test_source_scope_itself_must_be_literal(self):
        card,req,text,value=source_fixture()
        card["applicability"]["objects"]=["unmentioned-object"]
        with self.assertRaises(ValueError): validate_cards([card])

    def test_corrected_or_retracted_source_cannot_be_silently_reused(self):
        card,req,text,value=source_fixture()
        card["identity"]["publication_status"]="RETRACTED"
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")
        card,req,text,value=source_fixture()
        card["identity"]["publication_status"]="CORRECTED"
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_scope_does_not_extend_to_other_signal_size_version_or_condition(self):
        for context in ({"objects":["T"]},{"method_version":"v2"},{"size":{"value":30,"unit":"cm"}},
                        {"conditions":{"temperature":"37 C"}}):
            card,req,text,value=source_fixture()
            req["applicability"].update(context)
            value["requirements"][0]["evidence_checks"][0]["applicability"]=deepcopy(req["applicability"])
            self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_joint_serial_methods_require_joint_source_scope(self):
        card,req,text,value=source_fixture()
        req["joint_operations"]=["M","N"]
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_even_bound_synthetic_multi_method_proposal_is_outside_scope(self):
        card,req,text,value=source_fixture()
        source=card["source_document"]["text"]+" Joint operations: M then N."
        card["source_document"].update(text=source,sha256=text_hash(source))
        card["passages"][0].update(end=len(source),quote=source,sha256=text_hash(source))
        card["applicability"]["operations"]=["M","N"]
        card["scope_support"].update({"operations.0":support(source,"M"),"operations.1":support(source,"N")})
        req["joint_operations"]=["M","N"]
        req["applicability"]["operations"]=["M","N"]
        proof=make_entailment_verification(card,["P"],req["text"],req["applicability"],lambda data:{"relation":"SUPPORTS"},
                  verifier_id="SYNTHETIC",verifier_revision="v1",response_origin="SYNTHETIC_ENGINEERING_FIXTURE")
        card["entailment_verifications"]=[proof]
        check=value["requirements"][0]["evidence_checks"][0]
        check.update(verification_id=proof["id"],applicability=deepcopy(req["applicability"]))
        result=adjudicate(value,[req],text,[card])
        self.assertEqual(result["requirements"][0]["evidence_audit"]["guards"],[])
        self.assertEqual(result["overall"],"UNRESOLVED")
        self.assertIn("MULTI_METHOD_COMBINATION_OUT_OF_SCOPE",result["requirements"][0]["guards"])

    def test_decisive_proposal_needs_protocol_quote(self):
        card,req,text,value=source_fixture()
        value["requirements"][0]["quotes"]=[]
        with self.assertRaises(ValueError): adjudicate(value,[req],text,[card])

    def test_noinfo_cannot_be_relabeled_violation(self):
        card,req,text,value=source_fixture("NOINFO")
        value["requirements"][0]["status"]="VIOLATED"
        value["requirements"][0]["evidence_checks"][0]["relation"]="REFUTES"
        self.assertEqual(adjudicate(value,[req],text,[card])["overall"],"UNRESOLVED")

    def test_global_critical_requirement_cannot_be_bypassed_with_or(self):
        reqs=[requirement("CORE","critical","TEXT"),requirement("OTHER","other","TEXT")]
        rows=[{"id":r["id"],"status":s,"basis":"PROTOCOL_TEXT","evidence_ids":[],"quotes":["fixture"],
               "reason":"synthetic"} for r,s in zip(reqs,["VIOLATED","SATISFIED"])]
        result=adjudicate({"requirements":rows,"limitations":"fixture"},reqs,"fixture",[],
                          {"any":["CORE","OTHER"]})
        self.assertEqual(result["requested_overall"],"SATISFIED")
        self.assertEqual(result["overall"],"VIOLATED")

    def test_complete_route_or_cannot_stitch_halves(self):
        reqs=[requirement("G","global","TEXT")]
        for route in ("A","B"):
            reqs.extend(requirement(route+str(i),"route","TEXT",scope="ROUTE",route_id=route) for i in (1,2))
        rows=[{"id":r["id"],"status":s,"basis":"PROTOCOL_TEXT","evidence_ids":[],"quotes":["fixture"],
               "reason":"synthetic"} for r,s in zip(reqs,["SATISFIED","SATISFIED","VIOLATED","VIOLATED","SATISFIED"])]
        value={"requirements":rows,"limitations":"fixture"}
        self.assertEqual(adjudicate(value,reqs,"fixture",[])["overall"],"VIOLATED")
        rows[3]["status"]="SATISFIED"
        self.assertEqual(adjudicate(value,reqs,"fixture",[])["overall"],"SATISFIED")


class ReferenceInterfacesTests(unittest.TestCase):
    def package(self,root):
        materials={"Q":{"root_task_id":"Q","kind":"SYNTHETIC_ENGINEERING_ONLY","question":"fixture",
                       "protocol":"Use DiI","requirements":[requirement("H","literal","TEXT")],"cards":[]}}
        save(root/"study/materials.json",materials)
        save(root/"study/jobs.json",[])
        save(root/"study/tasks.json",[])
        save(root/"study/evidence_cards.json",[])
        with patch("experiments.construct_validity.review.verify_manifest",return_value={"manifest_sha256":"synthetic","version":"fixture"}):
            export_review(root/"study",root/"package")
        return read(root/"package/public/cases.json")

    def test_templates_do_not_count_as_manual_annotations_or_expert_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.package(root)
            form=read(root/"package/public/extraction_reference_template.json")
            form["reviewer_id"]="SYNTHETIC_TEST_ONLY";form["saw_model_extraction"]=False
            save(root/"form.json",form)
            with self.assertRaises(ValueError): import_extraction_references(root/"package",root/"form.json",root/"imports")

    def test_manual_fidelity_import_versions_and_no_scientific_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.package(root)
            form=read(root/"package/public/extraction_reference_template.json")
            form["reviewer_id"]="SYNTHETIC_TEST_ONLY";form["saw_model_extraction"]=True
            form["references"][0]["manual_extraction"]=extraction()
            form["references"][0]["reason"]="synthetic engineering reference"
            save(root/"form.json",form)
            result=import_extraction_references(root/"package",root/"form.json",root/"imports")
            self.assertEqual(result["scientific_labels"],0)
            self.assertFalse(result["independent_by_disclosure"])
            self.assertFalse(result["scientific_agreement_computed"])
            self.assertEqual(result,import_extraction_references(root/"package",root/"form.json",root/"imports"))
            changed=deepcopy(form);changed["references"][0]["case_identity"]["protocol_sha256"]="different"
            save(root/"wrong.json",changed)
            with self.assertRaises(ValueError): import_extraction_references(root/"package",root/"wrong.json",root/"imports")

    def test_scientific_import_cannot_drop_case_version_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.package(root)
            form=read(root/"package/public/ratings_template.json")
            form["reviewer"]={"id":"SYNTHETIC_TEST_ONLY","expertise":"fixture","method_familiarity":"fixture",
                             "participated_in_task_design":False,"saw_automatic_judgments":False,"saw_other_raters":False}
            form["ratings"][0].update(status="SATISFIED",reason="synthetic")
            del form["ratings"][0]["case_identity"]
            save(root/"form.json",form)
            with self.assertRaises(ValueError): import_ratings(root/"package",root/"form.json",root/"imports")



class GenericFactTests(unittest.TestCase):
    def fact(self,text,quote,value,field="temperature",**metadata):
        start=text.index(quote)
        return {"field":field,"value":value,"quote":quote,"start":start,"end":start+len(quote),**metadata}

    def test_quantity_unit_basis_polarity_and_phase_retained(self):
        text="光透明：用 50 vol% X，处理温度 4 °C。\n存储：20 °C。\n标签准备：不添加 DiD。"
        facts=[self.fact(text,"50 vol%",50,"concentration",unit="percent",basis="v/v",scope="processing"),
               self.fact(text,"处理温度 4 °C",4,unit="degC",scope="processing"),
               self.fact(text,"20 °C",20,unit="degC",scope="storage"),
               self.fact(text,"不添加 DiD","DiD","excluded_probe",polarity="negative",scope="label_preparation")]
        result=audit_facts(facts,text)
        self.assertEqual(result["status"],"FAITHFUL")
        self.assertEqual(result["completeness"],"NOT_ESTABLISHED")
        for index,key,wrong,expected in ((0,"basis","w/v","concentration.basis"),
                                          (1,"scope","storage","temperature.scope"),
                                          (3,"polarity","positive","excluded_probe.polarity")):
            modified=deepcopy(facts);modified[index][key]=wrong
            result=audit_facts(modified,text)
            self.assertEqual(result["status"],"UNFAITHFUL")
            self.assertIn(expected,result["mismatch_fields"])

    def test_scope_anchor_from_another_phase_cannot_authorize(self):
        text="processing: 4 °C\nstorage: 20 °C"
        fact=self.fact(text,"4 °C",4,unit="degC",scope="storage")
        fact["scope_support"]=support(text,"storage")
        self.assertIn("temperature.scope",audit_facts([fact],text)["mismatch_fields"])

    def test_numeric_value_and_unit_must_be_bound_together(self):
        text="processing: 50 vol% X for 2 h"
        fact=self.fact(text,"50 vol% X for 2 h",2,"concentration",unit="percent",basis="v/v",scope="processing")
        self.assertIn("concentration.unit",audit_facts([fact],text)["mismatch_fields"])

    def test_declared_required_fields_do_not_create_scientific_completeness(self):
        text="storage: 4 °C"
        fact=self.fact(text,"4 °C",4,unit="degC",scope="storage")
        result=audit_facts([fact],text,["temperature","excluded_probe"])
        self.assertIn("excluded_probe.missing",result["mismatch_fields"])
        self.assertEqual(result["scientific_validation"],"PENDING_USER_EXPERT")
        self.assertEqual(result["completeness"],"DECLARED_FIELD_PRESENCE_ONLY")

    def test_unknown_metadata_stays_unresolved(self):
        text="4 °C"
        fact=self.fact(text,text,4,unit="degC",scope="unknown inferred stage")
        self.assertEqual(audit_facts([fact],text)["status"],"UNRESOLVED")

    def test_named_branch_cannot_borrow_other_alternative_occurrence(self):
        text="Route A: use DiI.\nRoute B: use DiD."
        value=extraction(text)
        value["branches"]=[{"id":name,"mode":"ALTERNATIVE","sample_id":"sample", "spans":[{
            "start":text.index(line),"end":text.index(line)+len(line),"quote":line}]}
            for name,line in (("A","Route A: use DiI."),("B","Route B: use DiD."))]
        row=value["labels"][0];row["branch"]="B";row["quote"]="DiI"
        row["field_support"]={k:support(text,row[k]) for k in ("target","probe","fluorophore","channel")}
        audited=validate_extraction(value,text)
        self.assertFalse(audited["scoring_eligible"])
        self.assertIn("FIELD_OUTSIDE_DECLARED_BRANCH",[i["code"] for i in audited["field_audit"]["issues"]])

    def test_correction_fulltext_is_visible_to_separate_checker(self):
        card,req,text,value=source_fixture()
        correction={"url":"https://example.org/synthetic/correction","version":"erratum-v1",
                    "text":"Synthetic erratum: scope changed."}
        correction["sha256"]=text_hash(correction["text"])
        card["identity"].update(publication_status="CORRECTED",correction_chain=[correction])
        observed=[]
        proof=make_entailment_verification(card,["P"],req["text"],req["applicability"],
              lambda data: observed.append(data) or {"relation":"NOINFO"},
              verifier_id="SYNTHETIC",verifier_revision="v1",response_origin="SYNTHETIC_ENGINEERING_FIXTURE")
        self.assertEqual(observed[0]["corrections"],[correction])
        self.assertEqual(proof["input"]["correction_sha256s"],[correction["sha256"]])
        self.assertEqual(proof["scientific_validation"],"PENDING_USER_REFERENCE")

    def test_checker_without_primary_snapshot_fails_explicitly(self):
        card,req,text,value=source_fixture();del card["source_document"]
        with self.assertRaisesRegex(ValueError,"primary fulltext"):
            make_entailment_verification(card,["P"],req["text"],req["applicability"],lambda data:{"relation":"SUPPORTS"},
                  verifier_id="SYNTHETIC",verifier_revision="v1",response_origin="SYNTHETIC_ENGINEERING_FIXTURE")


if __name__ == "__main__":
    unittest.main()
