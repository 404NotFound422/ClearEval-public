"""Engineering invariants for goal relations and actual request identity."""
from copy import deepcopy
import unittest
from experiments.construct_validity.objectives import compare_candidates
from experiments.construct_validity.execution_identity import (
    execution_identity, public_context, repeat_diagnostic, verify_saved_request,
    compare_judge_inputs)
from experiments.construct_validity.contract import digest


def candidate(identifier, time=2, quality=0.9):
    return {"id":identifier,"task_id":"fixture","scenario":{"tissue":"synthetic"},
            "constraints":{"keep_signal":"SATISFIED"},
            "objectives":{"time":{"min":time,"max":time,"unit":"h","direction":"min","measurement_scope":"complete synthetic processing","measurement_basis":"SYNTHETIC_FIXTURE"},
                          "quality":{"min":quality,"max":quality,"unit":"ratio","direction":"max","measurement_scope":"same synthetic endpoint","measurement_basis":"SYNTHETIC_FIXTURE"}}}


class ObjectiveTests(unittest.TestCase):
    def test_matching_unknown_scopes_cannot_establish_dominance(self):
        for absent in (None, '', {}, {'phase':None}, 'UNKNOWN', 'not reported'):
            with self.subTest(scope=absent):
                a,b=candidate("A",1,0.95),candidate("B",2,0.9)
                for item in (a,b):
                    item["objectives"]["time"]["measurement_scope"]=deepcopy(absent)
                result=compare_candidates(a,b)
                self.assertEqual(result["relationship"],"NOT_COMPARABLE")
                self.assertIn("MISSING_MEASUREMENT_SCOPE:time",result["reasons"])
                self.assertEqual(result["scientific_validation"],"PENDING_USER_EXPERT")
        a,b=candidate("A",1,0.95),candidate("B",2,0.9)
        del b["objectives"]["time"]["measurement_scope"]
        self.assertEqual(compare_candidates(a,b)["relationship"],"NOT_COMPARABLE")

    def test_dominance_antisymmetry_and_tradeoff_symmetry(self):
        a,b=candidate("A",1,0.95),candidate("B",2,0.9)
        self.assertEqual(compare_candidates(a,b)["relationship"],"A_DOMINATES")
        self.assertEqual(compare_candidates(b,a)["relationship"],"B_DOMINATES")
        a["objectives"]["quality"].update(min=0.8,max=0.8)
        for left,right in ((a,b),(b,a)):
            self.assertEqual(compare_candidates(left,right)["relationship"],"TRADEOFF")

    def test_units_equal_but_unknown_or_hard_failure_cannot_be_compensated(self):
        a,b=candidate("A"),candidate("B")
        b["objectives"]["time"].update(min=120,max=120,unit="min")
        b["objectives"]["quality"].update(min=90,max=90,unit="%")
        self.assertEqual(compare_candidates(a,b)["relationship"],"EQUIVALENT")
        a["constraints"]["keep_signal"]="UNRESOLVED"
        self.assertEqual(compare_candidates(a,b)["relationship"],"UNRESOLVED")
        a["constraints"]["keep_signal"]="VIOLATED"
        self.assertEqual(compare_candidates(a,b)["relationship"],"B_ONLY_FEASIBLE")

    def test_missing_values_scope_and_overlapping_intervals(self):
        a,b=candidate("A"),candidate("B")
        del b["objectives"]["quality"]
        self.assertEqual(compare_candidates(a,b)["relationship"],"UNRESOLVED")
        b=candidate("B")
        a["objectives"]["time"].update(min=1,max=3)
        b["objectives"]["time"].update(min=2,max=4)
        self.assertEqual(compare_candidates(a,b)["relationship"],"UNRESOLVED")
        b["scenario"]["tissue"]="different"
        self.assertEqual(compare_candidates(a,b)["relationship"],"NOT_COMPARABLE")

    def test_invalid_numeric_or_semantic_units(self):
        for low,high in ((True,3),(float("nan"),3),(float("inf"),3),(5,2)):
            a,b=candidate("A"),candidate("B")
            a["objectives"]["time"].update(min=low,max=high)
            with self.assertRaises(ValueError): compare_candidates(a,b)
        a,b=candidate("A"),candidate("B")
        b["objectives"]["quality"]["unit"]="brightness-counts"
        self.assertEqual(compare_candidates(a,b)["relationship"],"NOT_COMPARABLE")

    def test_no_hard_constraints_must_be_explicit_and_inputs_unchanged(self):
        a,b=candidate("A"),candidate("B")
        a["constraints"]=b["constraints"]={}
        self.assertEqual(compare_candidates(a,b)["relationship"],"UNRESOLVED")
        a["no_hard_constraints_declared"]=b["no_hard_constraints_declared"]=True
        before=deepcopy((a,b))
        r=compare_candidates(a,b)
        self.assertEqual(r["relationship"],"EQUIVALENT")
        self.assertEqual((a,b),before)
        self.assertEqual(r["scientific_validation"],"PENDING_USER_EXPERT")


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.payload={"model":"fixture-model","messages":[{"role":"user","content":"fixture"}],"options":{"seed":1}}
        self.material={"question":"fixture task","requirements":[],"cards":[]}
        self.manifest={"model_digest":"fixture-revision","model_family":"fixture-family"}
        self.job={"phase":"judge"}
        self.identity=execution_identity(self.payload,self.material,"fixture answer",self.manifest,self.job)
        self.request={"endpoint":"http://127.0.0.1:11434/api/chat","payload":deepcopy(self.payload),
                      "payload_sha256":digest(self.payload),"execution_identity":self.identity}
        self.result={"payload_sha256":digest(self.payload),"execution_identity_sha256":digest(self.identity),
                     "model_digest":"fixture-revision"}

    def test_tampering_and_recomputed_self_hash_cannot_hide_different_actual_input(self):
        self.request["payload"]["messages"][0]["content"]="changed"
        self.request["payload_sha256"]=digest(self.request["payload"])
        self.result["payload_sha256"]=self.request["payload_sha256"]
        with self.assertRaises(ValueError):
            verify_saved_request(self.request,self.result,self.payload,self.identity,self.request["endpoint"])

    def test_revised_evidence_or_model_is_a_distinct_binding(self):
        revised=deepcopy(self.material)
        revised["cards"]=[{"id":"new-card"}]
        r=execution_identity(self.payload,revised,"fixture answer",self.manifest,self.job)
        self.assertNotEqual(r["bindings"],self.identity["bindings"])
        changed=deepcopy(self.manifest)
        changed["model_digest"]="different"
        r=execution_identity(self.payload,self.material,"fixture answer",changed,self.job)
        self.assertNotEqual(r["judge"],self.identity["judge"])

    def test_gold_annotations_rejected_before_rendering(self):
        m={"question":"fixture","requirements":[],"cards":[{"expert_labels":{"R":"SATISFIED"}}]}
        with self.assertRaises(ValueError): public_context(m,"answer")

    def test_one_valid_repeat_or_cached_replay_not_stability(self):
        row={"status":"COMPLETE","execution_origin":"LIVE","response_cache_hit":False,
             "invocation_id":"unique","payload_sha256":"same","visible_information_sha256":"same"}
        self.assertEqual(repeat_diagnostic([row],3)["repetition_status"],"NOT_ESTIMABLE")
        cache={**row,"invocation_id":"another","execution_origin":"RESPONSE_CACHE","response_cache_hit":True}
        r=repeat_diagnostic([row,cache],3)
        self.assertEqual(r["independent_live_complete"],1)
        self.assertEqual(r["repetition_status"],"NOT_ESTIMABLE")
        self.assertEqual(r["response_cache_hits"],1)

    def test_duplicate_invocation_or_changed_payload_not_independent(self):
        row={"status":"COMPLETE","execution_origin":"LIVE","response_cache_hit":False,
             "invocation_id":"same","payload_sha256":"same","visible_information_sha256":"same"}
        self.assertEqual(repeat_diagnostic([row,row],2)["repetition_status"],"NOT_ESTIMABLE")
        other={**row,"invocation_id":"new","payload_sha256":"changed"}
        self.assertEqual(repeat_diagnostic([row,other],2)["repetition_status"],"NOT_ESTIMABLE")
        other={**row,"invocation_id":"new"}
        self.assertEqual(repeat_diagnostic([row,other],2)["repetition_status"],"DESCRIPTIVE_INDEPENDENT_REPETITIONS")

    def test_mock_transport_not_counted_as_live_independent_repetition(self):
        row={"status":"COMPLETE","execution_origin":"TEST_TRANSPORT","response_cache_hit":False,
             "invocation_id":"one","payload_sha256":"same","visible_information_sha256":"same"}
        self.assertEqual(repeat_diagnostic([row,{**row,"invocation_id":"two"}],2)["independent_live_complete"],0)

    def test_cross_family_ready_only_for_identical_visible_information(self):
        other=deepcopy(self.identity)
        other["judge"]["family"]="second-family"
        self.assertTrue(compare_judge_inputs(self.identity,other)["controlled_comparison_ready"])
        other["visible_information_sha256"]="different"
        self.assertFalse(compare_judge_inputs(self.identity,other)["controlled_comparison_ready"])


if __name__ == "__main__":
    unittest.main()
