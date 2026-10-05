"""Counterexamples for the versioned evaluator; no model/network."""
import itertools
from pathlib import Path
import tempfile
import unittest

from experiments.construct_validity.contract import (
    STATES, adjudicate, anchors, combine, duration_bounds, evaluate_formula,
    parse_json, read, ri_diagnostic, save, time_diagnostic, validate_extraction)
from experiments.construct_validity.local_runner import local_origin, run_job
from experiments.construct_validity.materials import requirement


def proposal(status="SATISFIED", basis="PROTOCOL_TEXT", sources=(), quote="CD31"):
    return {"requirements":[{"id":"H","status":status,"basis":basis,
            "evidence_ids":list(sources),"quotes":[quote] if quote else [],"reason":"test basis"}],"limitations":"fixture only"}


class LogicTests(unittest.TestCase):
    def test_critical_failure_cannot_be_compensated(self):
        for tail in itertools.product(STATES, repeat=3):
            self.assertEqual(combine(["VIOLATED",*tail]), "VIOLATED")

    def test_unknown_or_missing_never_pass_conjunction(self):
        for s in ("UNDER_SPECIFIED","UNRESOLVED"):
            self.assertEqual(combine([s,"SATISFIED"]), s)

    def test_all_satisfied_only_way_conjunction_passes(self):
        for values in itertools.product(STATES,repeat=3):
            self.assertEqual(combine(values)=="SATISFIED",set(values)=={"SATISFIED"})

    def test_do_not_stitch_different_routes(self):
        formula = {"any":[{"all":["A_marker","A_clear"]},{"all":["B_marker","B_clear"]}]}
        values = {"A_marker":"SATISFIED","A_clear":"VIOLATED","B_marker":"VIOLATED","B_clear":"SATISFIED"}
        self.assertEqual(evaluate_formula(formula,values),"VIOLATED")
        values["B_marker"]="SATISFIED"
        self.assertEqual(evaluate_formula(formula,values),"SATISFIED")

    def test_unknown_alternative_is_not_rejected(self):
        self.assertEqual(combine(["VIOLATED","UNRESOLVED"],"any"),"UNRESOLVED")

    def test_empty_rules_and_invalid_states_rejected(self):
        for values in ([],["UNKNOWN"],[None]):
            with self.assertRaises(ValueError): combine(values)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.req = [requirement("H","Identify HEV","SCIENTIFIC",["E_HEV"])]
        self.cards = [{"id":"E_HEV"},{"id":"E_FDISCO"}]

    def test_irrelevant_existing_citation_does_not_establish_identity(self):
        result=adjudicate(proposal(basis="SUPPLIED_EVIDENCE",sources=["E_FDISCO"]),self.req,"CD31",self.cards)
        self.assertEqual(result["proposed_overall"],"SATISFIED")
        self.assertEqual(result["overall"],"UNRESOLVED")
        self.assertIn("SOURCE_OUTSIDE_REQUIREMENT_SCOPE",result["requirements"][0]["guards"])

    def test_preservation_claim_alone_cannot_support_science(self):
        result=adjudicate(proposal(quote="preserve DiI"),self.req,"preserve DiI",self.cards)
        self.assertEqual(result["overall"],"UNRESOLVED")

    def test_scope_check_is_not_semantic_truth(self):
        result=adjudicate(proposal(basis="SUPPLIED_EVIDENCE",sources=["E_HEV"]),self.req,"CD31",self.cards)
        self.assertEqual(result["overall"],"UNRESOLVED")
        self.assertIn("LEGACY_JUDGMENT_STRUCTURE_ONLY",result["requirements"][0]["guards"])
        self.assertEqual(result["scientific_validation"],"PENDING_INDEPENDENT_REFERENCE")

    def test_unknown_source_id_is_technical_error(self):
        with self.assertRaises(ValueError):
            adjudicate(proposal(basis="SUPPLIED_EVIDENCE",sources=["NONEXISTENT"]),self.req,"CD31",self.cards)

    def test_task_quote_not_in_protocol_is_rejected(self):
        with self.assertRaises(ValueError):
            adjudicate(proposal(),self.req,"DAPI only",self.cards)

    def test_missing_detail_not_forced_to_failure(self):
        result=adjudicate(proposal("UNDER_SPECIFIED","MISSING",quote=""),self.req,"DAPI only",self.cards)
        self.assertEqual(result["overall"],"UNDER_SPECIFIED")

    def test_text_boundary_needs_no_external_evidence(self):
        req=[requirement("H","no joining","TEXT")]
        result=adjudicate(proposal(quote="no joining"),req,"no joining",[])
        self.assertEqual(result["overall"],"SATISFIED")

    def test_no_guard_ablation_uses_same_proposal(self):
        result=adjudicate(proposal(),self.req,"CD31",self.cards,evidence_guard=False)
        self.assertEqual(result["overall"],"SATISFIED")

    def test_missing_basis_does_not_pass(self):
        result=adjudicate(proposal(basis="MISSING"),self.req,"CD31",self.cards)
        self.assertEqual(result["overall"],"UNDER_SPECIFIED")

    def test_optional_failure_not_used_as_necessary(self):
        req=[requirement("H","core","TEXT"),{**requirement("OPT","optional","TEXT"),"necessary":False}]
        v=proposal()
        v["requirements"].append({**v["requirements"][0],"id":"OPT","status":"VIOLATED"})
        self.assertEqual(adjudicate(v,req,"CD31",[])["overall"],"SATISFIED")

    def test_omitted_requirement_is_rejected(self):
        with self.assertRaises(ValueError):
            adjudicate(proposal(),self.req+[requirement("OTHER","other")],"CD31",self.cards)


class ExtractionAndTimeTests(unittest.TestCase):
    def test_same_fluorophore_and_null_small_molecule_target_survive(self):
        rows=[{"id":"L1","branch":"main","target":"A","probe":"anti-A","fluorophore":"AF647","channel":None,"quote":"A AF647"},
              {"id":"L2","branch":"main","target":"B","probe":"anti-B","fluorophore":"AF647","channel":None,"quote":"B AF647"},
              {"id":"L3","branch":"main","target":None,"probe":"DAPI","fluorophore":"DAPI","channel":None,"quote":"DAPI"}]
        value=validate_extraction({"labels":rows,"steps":[],"ri":[],"limitations":""},"A AF647; B AF647; DAPI")
        self.assertEqual(len(value["labels"]),3)
        self.assertIsNone(value["labels"][2]["target"])
        self.assertFalse(value["scoring_eligible"])
        self.assertEqual(value["field_audit"]["fidelity_status"],"LEGACY_STRUCTURE_ONLY")

    def test_ambiguous_quote_preserves_all_offsets(self):
        a=anchors("wash\n\nwash","wash")
        self.assertTrue(a["ambiguous_location"])
        self.assertEqual([o["line"] for o in a["occurrences"]],[1,3])

    def test_parallel_times_use_critical_path_and_repeats(self):
        steps=[{"id":"a","after":[],"min_h":2,"max_h":3,"repeat":2},
               {"id":"b","after":[],"min_h":5,"max_h":6},
               {"id":"c","after":["a","b"],"min_h":1,"max_h":2}]
        self.assertEqual(duration_bounds(steps),{"status":"EXPLICIT","min_h":6,"max_h":8})

    def test_overnight_and_missing_topology_remain_unknown(self):
        for step in ({"id":"a","after":[],"min_h":None,"max_h":None,"duration_text":"overnight"},
                     {"id":"a","min_h":3,"max_h":3}):
            self.assertIsNone(duration_bounds([step])["max_h"])

    def test_time_cycles_rejected(self):
        with self.assertRaises(ValueError):
            duration_bounds([{"id":"a","after":["b"]},{"id":"b","after":["a"]}])

    def test_time_requires_exact_tier_and_scope(self):
        row={"method":"M","tier_code":"child","time_scope":"clearing","supported":True,
             "clearing_time_min_h":20,"clearing_time_max_h":40,"clearing_time_median_h":30}
        self.assertIsNone(time_diagnostic(30,[row],"M","parent","clearing")["score"])
        self.assertIsNone(time_diagnostic(30,[row],"M","child","including_labeling")["score"])

    def test_symmetric_tau_agrees_with_declared_policy(self):
        row={"method":"M","tier_code":"T","time_scope":"clearing","supported":True,
             "clearing_time_min_h":20,"clearing_time_max_h":40,"clearing_time_median_h":30}
        a=time_diagnostic(14,[row],"M","T","clearing")
        b=time_diagnostic(46,[row],"M","T","clearing")
        self.assertEqual(a["score"],b["score"])
        self.assertEqual(a["tau_h"],6)
        self.assertFalse(a["probability"])

    def test_method_name_does_not_supply_ri_medium(self):
        self.assertIsNone(ri_diagnostic(None,1.56,1.56)["difference"])

    def test_ri_difference_is_not_compatibility(self):
        r=ri_diagnostic("DBE",1.56,1.56)
        self.assertEqual(r["difference"],0)
        self.assertEqual(r["scientific_compatibility"],"NOT_ESTABLISHED_BY_RI_ALONE")


class ProvenanceAndRunnerTests(unittest.TestCase):
    def test_duplicate_keys_and_nonfinite_values_rejected(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError): parse_json(text)

    def test_immutable_artifacts_reject_changed_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"m.json"
            save(path,{"x":1})
            save(path,{"x":1})
            with self.assertRaises(ValueError): save(path,{"x":2})
            self.assertEqual(read(path),{"x":1})

    def test_external_inference_and_credentials_rejected(self):
        for url in ("https://example.com","http://127.0.0.1@example.com","http://user:pass@127.0.0.1","http://localhost:11434"):
            with self.assertRaises(ValueError): local_origin(url)

    def test_failed_request_retained_and_not_resent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/"materials.json",{"Q":{"root_task_id":"Q","question":"fixture","resource_list":{}}})
            manifest={"origin":"http://127.0.0.1:11434","model":"fixture","model_digest":"fixture",
                      "options":{},"phase_options":{"generate":{}},"manifest_sha256":"fixture","read_timeout_seconds":1,"wall_limit_seconds":2}
            job={"id":"G","phase":"generate","material_id":"Q"}
            calls=[]
            def fail(request):
                calls.append(request)
                raise TimeoutError("synthetic timeout; no request sent")
            result=run_job(root,manifest,job,transport=fail)
            self.assertEqual(result["status"],"TIMEOUT")
            self.assertTrue((root/"attempts/G/a01/request.json").exists())
            with self.assertRaises(ValueError): run_job(root,manifest,job,transport=fail)
            self.assertEqual(len(calls),1)


if __name__ == "__main__":
    unittest.main()

