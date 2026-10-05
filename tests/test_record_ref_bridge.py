import json
from copy import deepcopy
from pathlib import Path
import unittest
from oeq_scientific import build_context, apply_assessment
from experiments.construct_validity.compact_grounding import SCHEMA, build_compact_prompt_view

PROTOCOL = "Chosen Method: MACS\n# Processing\n1. Record the named action (Time: 24 h)\n2. Record a separate action (Time: 12 h)\n"

def proposal(context, selected=("R001",)):
    return {"extraction":{"schema_version":SCHEMA,"protocol_sha256":context["protocol_sha256"],
        "branches":[{"id":"main","mode":"SERIAL","sample_id":"main","spans":[]}],
        "steps":[{"id":"S"+str(i),"record_id":r,"branch":"main"} for i,r in enumerate(selected)],
        "labels":[],"ri":[],"limitations":""},
        "assessment":{"schema_version":"judgment-grounding-v2","requirements":[
            {"id":r["id"],"status":"SATISFIED","basis":"PROTOCOL_TEXT","evidence_ids":[],
             "quotes":[PROTOCOL],"reason":"Literal development proposal","evidence_checks":[]}
             for r in context["requirements"]],"limitations":""},"objectives":{},
        "method_declarations":[{"name":"MACS","branch":"main","span":{"quote":"MACS"}}]}

class RecordReferenceBridgeTests(unittest.TestCase):
    def context(self, question=None, study=None):
        return build_context(question or {},PROTOCOL,workspace=Path("absent"),study_context=study)
    def test_prompt_has_one_lossless_source_and_no_duplicate_question_scope(self):
        c=self.context({"question":"Already fixed tissue."})
        context,view=c["prompt"].split("\nCONTEXT_JSON\n",1)[1].split("\nSOURCE_RECORD_VIEW\n",1)
        self.assertNotIn("source_record_catalog",json.loads(context))
        self.assertNotIn("scope",json.loads(context))
        self.assertEqual("".join(x["quote"] for x in json.loads(view)["segments"]),PROTOCOL)
    def test_expansion_preserves_first_raw_and_reports_omitted_candidate(self):
        c=self.context();raw=proposal(c);before=deepcopy(raw)
        result=apply_assessment(raw,c,PROTOCOL)
        self.assertEqual(raw,before)
        self.assertEqual(result["extraction_reference_audit"]["raw_payload"],before["extraction"])
        self.assertTrue(result["extraction_reference_audit"]["coverage"]["omitted_record_ids"])
        self.assertFalse(result["extraction_fidelity"]["completeness_certified"])
        self.assertIsNone(result["scientific_gold"])
    def test_stale_alias_binding_is_rejected_before_assessment(self):
        c=self.context();raw=proposal(c);raw["extraction"]["protocol_sha256"]="0"*64
        with self.assertRaises(ValueError):apply_assessment(raw,c,PROTOCOL)
    def test_explicit_frozen_requirements_are_not_augmented(self):
        r={"id":"FROZEN","kind":"TEXT","necessary":True,"evidence_ids":[],"text":"Frozen requirement","literal_rule":{"type":"LITERAL_REQUIRED","text":"MACS"}}
        c=self.context({"question":"Please include fixation."},{"requirements":[r],"cards":[]})
        self.assertEqual([x["id"] for x in c["requirements"]],["FROZEN"])
    def test_required_unfinished_action_does_not_pass_from_teacher_assertion(self):
        c=self.context({"question":"Fixation has not been completed. Please include fixation."})
        result=apply_assessment(proposal(c),c,PROTOCOL)
        row=next(x for x in result["requirement_results"] if x["id"]=="TASK_INITIAL_FUNCTION_INITIAL_FIXATION")
        self.assertEqual(row["effective_status"],"UNRESOLVED")
        self.assertEqual(row["verification"]["execution_obligation"],"REQUIRED")
    def test_completion_alone_is_not_a_blanket_repetition_prohibition(self):
        c=self.context({"question":"Already fixed tissue."})
        self.assertNotIn("FIXATION_SCOPE",[r["id"] for r in c["requirements"]])

if __name__=="__main__":unittest.main()
