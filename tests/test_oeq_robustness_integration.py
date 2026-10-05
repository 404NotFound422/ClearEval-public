"""Main OEQ integration, fixed SDK fixtures only; no provider requests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import OEQ_run_grading_new as runner
from benchmark_scoring import _record_hash
from evaluation_contract import json_hash
from experiments.construct_validity.fidelity import text_hash
from oeq_robustness import INPUT_VERSION, SET_VERSION, is_report_complete, select_bundle
from oeq_objective_bridge import build_relation_binding
from results.aggregate_oeq import aggregate_file

import test_oeq_benchmark_integration as fixturebench
CURRENT, PROTOCOL, teacher_payload = fixturebench.CURRENT, fixturebench.PROTOCOL, fixturebench.teacher_payload
from test_oeq_fidelity_impact import inventory, reported, support
from test_oeq_objective_bridge import candidate
from test_oeq_scientific import req, payload
from oeq_scientific import build_context


class RobustnessMainFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved={name:getattr(runner,name) for name in (
            "QUESTION_FILE","DEMAND_PROFILE","DEMAND_FILE","DEMAND_MANIFEST","OEQ_SCORE_DIR","OEQ_OUTPUT_DIR")}
        runner.DEMAND_PROFILE="current-proposal"
        runner.configure_question_snapshot(CURRENT)
        self.qid=runner._QUESTION_LIST[0]["question_id"]
        self.question=runner.fixed_demands().questions[str(self.qid)]
        self.helper=fixturebench.BenchmarkActualCliTests()
        self.helper.qid=self.qid

    def tearDown(self):
        for name,value in self.saved.items():setattr(runner,name,value)
        runner.configure_question_snapshot(self.saved["QUESTION_FILE"])

    def bundle(self, protocol=PROTOCOL, **extra):
        return {"schema_version":INPUT_VERSION,"question_sha256":json_hash(self.question),
                "protocol_sha256":text_hash(protocol),**extra}

    def inputs_file(self,directory,bundle):
        path=Path(directory)/"robustness.json"
        path.write_text(json.dumps({"schema_version":SET_VERSION,"entries":[bundle]}),encoding="utf-8")
        return path

    async def test_default_scores_and_explicit_missing_reference_reports_reach_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            self.assertTrue(is_report_complete(ev))
            self.assertFalse(ev["robustness_diagnostics"]["imaging_results_evaluated"])
            self.assertEqual(ev["robustness_diagnostics"]["fidelity_comparison"]["status"],"UNAVAILABLE")
            self.assertEqual(ev["robustness_diagnostics"]["stability"]["independent_repeats"],0)
            summary=aggregate_file(path)["robustness_summary"]
            self.assertEqual(summary["report_count"],1)
            self.assertEqual(summary["independent_candidate_reference_count"],0)
            self.assertEqual(summary["independent_objective_relation_count"],0)
            self.assertEqual(summary["answer_matching_contract_status_counts"],{"UNRESOLVED":1})
            self.assertEqual(summary["answers_with_global_necessary_failure"],0)

    async def test_self_rehashed_sidecar_is_rejected_then_rebuilt_with_zero_extra_judge_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args),0)
                rows=json.loads(path.read_text(encoding="utf-8"))
                ev=rows[0]["evaluation"]
                before=deepcopy(ev["scores"])
                ev["robustness_diagnostics"]["candidate_diagnostics"]["status"]="SATISFIED"
                ev["robustness_diagnostics_sha256"]=json_hash(ev["robustness_diagnostics"])
                ev["benchmark_record_sha256"]=_record_hash(ev)
                self.assertFalse(is_report_complete(ev))
                path.write_text(json.dumps(rows),encoding="utf-8")
                with self.assertRaises(ValueError):aggregate_file(path)
                self.assertEqual(await runner.main(args+["--eval-only"]),0)
            after=json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(sdk.calls,["candidate","judge"])
            self.assertEqual(after["evaluation"]["scores"],before)
            self.assertTrue(is_report_complete(after["evaluation"]))
            self.assertEqual(len(after["previous_attempts"]),1)

    async def test_wrong_binding_rejected_before_teacher(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            bad=self.bundle();bad["protocol_sha256"]="x"*64
            inputs=self.inputs_file(tmp,bad)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertNotEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
            self.assertEqual(sdk.calls,["candidate"])

    async def test_complete_candidate_contract_runs_in_numeric_main_flow(self):
        protocol="CUBIC: clearing 24 h. "+"Synthetic offline declaration. "*20
        context=build_context(self.question,protocol,
                   study_context={"requirements":[req(rule={"type":"LITERAL_REQUIRED","text":"clearing"})]})
        raw=payload(context,"CUBIC: clearing 24 h")
        reference={"question_sha256":json_hash(self.question),"protocol_sha256":text_hash(protocol),
                   "context_sha256":context["context_sha256"],"target":"REVIEWED_REQUIREMENT_CONTRACT",
                   "label":"SATISFIED","independence":"INDEPENDENT","assistance":"NONE",
                   "reviewer_id":"synthetic-independent-reviewer","record_id":"synthetic-r"}
        bundle=self.bundle(protocol,candidate_assessment={"context":context,"proposal":raw,
                                                         "independent_reference":reference})
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp,protocol=protocol)
            inputs=self.inputs_file(tmp,bundle)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            diag=ev["robustness_diagnostics"]["candidate_diagnostics"]
            self.assertEqual(diag["assessment"]["overall"],"SATISFIED")
            self.assertEqual(ev["robustness_diagnostics"]["answer_matching_diagnostics"]["contract_status"],"SATISFIED")
            self.assertEqual(diag["independent_reference_count"],1)
            self.assertIsNone(diag["scientific_accuracy"])
            self.assertTrue(is_report_complete(ev))

    async def test_objective_pair_units_and_independent_reference_reach_main_stats(self):
        records=[candidate("A",time=2),candidate("B",time=180,unit="min")]
        for record in records:record["task_id"]=json_hash(self.question)
        records[0]["protocol_sha256"]=text_hash(PROTOCOL)
        bind=build_relation_binding(records,required_constraints=["complete_contract"])
        reference={**bind,"label":"A_DOMINATES","independence":"INDEPENDENT",
                   "annotation_pass":"FIRST_PASS","assistance":"NONE",
                   "reviewer_id":"synthetic-blind-reviewer","provenance":{"record_id":"synthetic-label"}}
        bundle=self.bundle(objective_comparison={"candidate_records":records,
               "required_constraints":["complete_contract"],"independent_relation":reference})
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            inputs=self.inputs_file(tmp,bundle)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            diag=ev["robustness_diagnostics"]["objective_diagnostics"]
            self.assertEqual(diag["relationship"],"A_DOMINATES")
            self.assertEqual(aggregate_file(path)["robustness_summary"]["independent_objective_relation_count"],1)
            self.assertTrue(is_report_complete(ev))

    async def test_manual_inventory_replays_existing_formulas_and_freezes_teacher_scores(self):
        ctime=reported("/clearing_total_time_hours",24,"NUMBER",
                      support(PROTOCOL,"48 hours","TIME_TO_HOURS"),unit="h")
        mtime=deepcopy(ctime);mtime["value"]=48
        auto=inventory(PROTOCOL,[ctime])
        manual=inventory(PROTOCOL,[mtime],role="MANUAL_REFERENCE")
        manual_flat=teacher_payload()["extraction"]
        def wrong_teacher():
            p=teacher_payload();p["extraction"]["clearing_total_time_hours"]=24
            return p
        bundle=self.bundle(candidate_inventory=auto,manual_inventory=manual,manual_extraction=manual_flat)
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp,payload_factory=wrong_teacher)
            inputs=self.inputs_file(tmp,bundle)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
                self.assertEqual(await runner.main(args+["--robustness-inputs",str(inputs),"--eval-only"]),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            report=ev["robustness_diagnostics"]
            self.assertEqual(report["fidelity_comparison"]["extraction_agreement"],"DISAGREEMENT")
            impact=report["extraction_score_impact"]
            self.assertEqual(impact["status"],"AVAILABLE",impact.get("reason"))
            self.assertFalse(impact["frozen_violations"])
            self.assertEqual(impact["score_differences"]["/effectiveness/s_time"]["candidate"],
                             ev["scores"]["effectiveness"]["s_time"]["score"])
            self.assertEqual(sdk.calls,["candidate","judge"])
            self.assertTrue(is_report_complete(ev))
            downgraded=deepcopy(ev)
            downgraded["robustness_diagnostics"]["extraction_score_impact"]={"status":"UNAVAILABLE"}
            downgraded["robustness_diagnostics_sha256"]=json_hash(downgraded["robustness_diagnostics"])
            downgraded["benchmark_record_sha256"]=_record_hash(downgraded)
            self.assertFalse(is_report_complete(downgraded))

    async def test_invalid_manual_flat_is_rejected_before_teacher(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            inputs=self.inputs_file(tmp,self.bundle(manual_extraction={"method_name":"CUBIC"}))
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertNotEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
            self.assertEqual(sdk.calls,["candidate"])

    async def test_top_level_rehash_and_changed_originals_cannot_forge_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            top=deepcopy(ev)
            top["robustness_diagnostics"]["scientific_accuracy"]=1.0
            top["robustness_diagnostics_sha256"]=json_hash(top["robustness_diagnostics"])
            top["benchmark_record_sha256"]=_record_hash(top)
            self.assertFalse(is_report_complete(top))
            other=deepcopy(ev)
            other["robustness_original_input"]["protocol"]+=" different answer"
            other["robustness_diagnostics"]["protocol_sha256"]=text_hash(
                other["robustness_original_input"]["protocol"])
            other["robustness_diagnostics_sha256"]=json_hash(other["robustness_diagnostics"])
            other["benchmark_record_sha256"]=_record_hash(other)
            self.assertFalse(is_report_complete(other))

    def test_imaging_target_and_context_tamper_rejected_before_requests(self):
        records=[candidate("A"),candidate("B",time=2)]
        for r in records:r["task_id"]=json_hash(self.question)
        records[0]["protocol_sha256"]=text_hash(PROTOCOL)
        records[0]["objectives"]["elapsed_time"]["outcome_type"]="IMAGE_RESOLUTION"
        inputs={"schema_version":SET_VERSION,"entries":[self.bundle(
                objective_comparison={"candidate_records":records})]}
        with self.assertRaises(ValueError):select_bundle(inputs,self.question,PROTOCOL)
        inputs["entries"][0]=self.bundle(candidate_assessment={"context":{},"proposal":{}})
        with self.assertRaises(ValueError):select_bundle(inputs,self.question,PROTOCOL)


    async def test_required_failure_reaches_numeric_output_and_stats_separately(self):
        protocol="CUBIC: repeat fixation 1 h. "+"Synthetic offline declaration. "*20
        context=build_context(self.question,protocol,study_context={"requirements":[
            req(rid="NO_REPEAT",rule={"type":"NO_REPEAT_FIXATION"})]})
        raw=payload(context,"CUBIC: repeat fixation 1 h")
        row=raw["extraction"]["steps"][0]
        row.update(phase=None,operation="repeat fixation",duration_text="1 h")
        row["field_support"]={name:(dict(kind="MISSING",raw_value=None,spans=[]) if value is None else
            dict(kind="EXPLICIT",raw_value=value,transform="IDENTITY",spans=[{"quote":value}]))
            for name,value in [("phase",None),("operation","repeat fixation"),("duration_text","1 h")]}
        bundle=self.bundle(protocol,candidate_assessment={"context":context,"proposal":raw})
        with tempfile.TemporaryDirectory() as tmp:
            sdk,args,path,_=self.helper.fixture(tmp,protocol=protocol)
            inputs=self.inputs_file(tmp,bundle)
            with patch.dict("sys.modules",{"ollama":SimpleNamespace(Client=sdk)}):
                self.assertEqual(await runner.main(args+["--robustness-inputs",str(inputs)]),0)
            ev=json.loads(path.read_text(encoding="utf-8"))[0]["evaluation"]
            matching=ev["robustness_diagnostics"]["answer_matching_diagnostics"]
            self.assertEqual(matching["contract_status"],"VIOLATED")
            self.assertEqual(matching["global_necessary_failures"],["NO_REPEAT"])
            self.assertIsNone(matching["scientific_accuracy"])
            summary=aggregate_file(path)["robustness_summary"]
            self.assertEqual(summary["answers_with_global_necessary_failure"],1)
            self.assertEqual(summary["answer_matching_contract_status_counts"],{"VIOLATED":1})

if __name__=="__main__":unittest.main()
