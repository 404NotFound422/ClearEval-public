"""Synthetic task text only; no native answers, case labels or scientific gold."""
import hashlib
import unittest
from experiments.construct_validity.contract import digest, validate_requirements
from experiments.construct_validity.task_state import (
    INITIAL_FIXATION as FIX, MEMBRANE_LABEL_DIFFUSION as DIFF,
    PRE_CLEARING_INITIAL_LABEL_QC as QC,
    LYMPHOCYTE_T_B_DISCRIMINATION as TB, propose_task_state,
)

class TaskStateTests(unittest.TestCase):
    def proposal(self, text, **metadata):
        question = dict(question=text, **metadata)
        result = propose_task_state(question, evidence_ids=["synthetic-source"])
        self.assertEqual(result["question_sha256"], digest(question))
        self.assertEqual(result["question_text_sha256"], hashlib.sha256(text.encode("utf-8")).hexdigest())
        for audit in result["functions"].values():
            for span in audit["question_spans"]:
                self.assertEqual(text[span["start"]:span["end"]], span["quote"])
        if result["requirements"]:
            validate_requirements(result["requirements"])
        return result

    def req(self, result, function):
        return next(item for item in result["requirements"] if item["function"] == function)

    def test_not_done_needs_current_plan_instruction(self):
        missing = self.proposal("样本尚未固定。")
        required = self.proposal("样本尚未固定，请在本方案包括固定步骤。")
        self.assertEqual(missing["functions"][FIX]["state"], "EXPLICITLY_NOT_DONE")
        self.assertEqual(missing["functions"][FIX]["execution_obligation"], "UNRESOLVED")
        self.assertTrue(self.req(missing, FIX)["review_required"])
        req = self.req(required, FIX)
        self.assertEqual(req["kind"], "COMPLETENESS")
        self.assertEqual(req["necessity_status"], "REQUIRED")
        self.assertTrue(req["necessary"])

    def test_diffusion_and_qc_instruction_are_separate(self):
        result = self.proposal("膜内扩散尚未完成，请安排完成扩散及初始独立QC后再透明。")
        for function in (DIFF, QC):
            self.assertEqual(self.req(result, function)["necessity_status"], "REQUIRED")
            self.assertTrue(self.req(result, function)["necessary"])
        self.assertEqual(result["functions"][QC]["state"], "UNKNOWN")
        self.assertNotIn(FIX, [item["function"] for item in result["requirements"]])

    def test_done_diffusion_does_not_complete_qc(self):
        result = self.proposal("膜内扩散已完成但初始独立QC尚未完成，请本方案安排初始独立QC后再透明。")
        self.assertEqual(result["functions"][DIFF]["state"], "EXPLICITLY_DONE")
        self.assertFalse(self.req(result, DIFF)["necessary"])
        self.assertEqual(result["functions"][QC]["state"], "EXPLICITLY_NOT_DONE")
        self.assertEqual(self.req(result, QC)["necessity_status"], "REQUIRED")
        self.assertIn("does not prove", result["legacy_completed_label_scope_warning"])

    def test_fixed_modifier_and_negative(self):
        done = self.proposal("两类固定小鼠组织，请分别说明输出。")
        missing = self.proposal("两类未固定小鼠组织，请分别说明输出。")
        self.assertEqual(done["functions"][FIX]["state"], "EXPLICITLY_DONE")
        self.assertFalse(self.req(done, FIX)["necessary"])
        self.assertEqual(missing["functions"][FIX]["state"], "EXPLICITLY_NOT_DONE")
        self.assertEqual(self.req(missing, FIX)["applicability_status"], "UNRESOLVED")

    def test_english_negative_done_and_conditional(self):
        required = self.proposal("The sample is not yet fixed. Please include fixation in this plan.")
        done = self.proposal("The sample is already fixed.")
        conditional = self.proposal("If fixation is needed, this plan should include fixation.")
        self.assertEqual(required["functions"][FIX]["state"], "EXPLICITLY_NOT_DONE")
        self.assertEqual(self.req(required, FIX)["necessity_status"], "REQUIRED")
        self.assertFalse(self.req(done, FIX)["necessary"])
        self.assertEqual(conditional["functions"][FIX]["state"], "CONDITIONAL")
        self.assertEqual(self.req(conditional, FIX)["applicability_status"], "UNRESOLVED")

    def test_english_diffusion_completion_does_not_propagate_to_qc(self):
        result = self.proposal("Membrane label diffusion has been completed but initial independent QC has not been completed. Please include initial independent QC in this plan.")
        self.assertEqual(result["functions"][DIFF]["state"], "EXPLICITLY_DONE")
        self.assertEqual(result["functions"][QC]["state"], "EXPLICITLY_NOT_DONE")
        self.assertFalse(self.req(result, DIFF)["necessary"])
        self.assertEqual(self.req(result, QC)["necessity_status"], "REQUIRED")

    def test_conflicting_states_and_done_execution_tension(self):
        for text in ("样本已固定。样本尚未固定，请本方案包括固定步骤。",
                     "样本已固定，请本方案完成固定步骤。"):
            result = self.proposal(text)
            self.assertEqual(self.req(result, FIX)["necessity_status"], "UNRESOLVED")
            self.assertTrue(self.req(result, FIX)["review_required"])
        result = self.proposal("样本已固定。样本尚未固定。")
        self.assertEqual(result["functions"][FIX]["state"], "CONFLICTING")

    def test_outside_scope_not_authorized(self):
        result = self.proposal("样本尚未固定，固定将在另处执行。")
        self.assertEqual(result["functions"][FIX]["state"], "EXPLICITLY_NOT_DONE")
        self.assertEqual(self.req(result, FIX)["necessity_status"], "NOT_REQUIRED")
        self.assertFalse(self.req(result, FIX)["necessary"])

    def test_t_b_positive_negative_conditional_conflict(self):
        positive = self.proposal("本题要求区分 T/B细胞。")
        negative = self.proposal("本题不要求区分 T/B细胞。")
        conditional = self.proposal("若需区分 T/B细胞，请说明。")
        conflict = self.proposal("本题要求区分 T/B细胞。本题不要求区分 T/B细胞。")
        req = self.req(positive, TB)
        self.assertEqual(req["kind"], "SCIENTIFIC")
        self.assertEqual(req["evidence_ids"], ["synthetic-source"])
        self.assertEqual(req["necessity_status"], "REQUIRED")
        self.assertFalse(self.req(negative, TB)["necessary"])
        for result in (conditional, conflict):
            self.assertEqual(self.req(result, TB)["applicability_status"], "UNRESOLVED")
            self.assertTrue(self.req(result, TB)["review_required"])
        english = self.proposal("This task does not require T and B cell discrimination.")
        self.assertFalse(self.req(english, TB)["necessary"])

    def test_unknown_mentioned_and_metadata_conflict(self):
        unknown = self.proposal("初始独立QC状态未知。")
        self.assertEqual(self.req(unknown, QC)["applicability_status"], "UNRESOLVED")
        conflict = self.proposal("样本已固定。", task_initial_states={FIX: "EXPLICITLY_NOT_DONE"})
        self.assertEqual(conflict["functions"][FIX]["state"], "CONFLICTING")
        self.assertTrue(self.req(conflict, FIX)["review_required"])
        unmentioned = self.proposal("请说明输出格式。", task_initial_states={FIX: "EXPLICITLY_NOT_DONE"}, marker_query_targets=[{"name": "T/B"}])
        self.assertEqual(unmentioned["requirements"], [])
        self.assertEqual(unmentioned["functions"][FIX]["mention_status"], "NOT_MENTIONED")


    def test_leading_condition_survives_comma_without_target_in_antecedent(self):
        samples = (
            ("If needed, please include fixation.", FIX),
            ("If needed, please distinguish T/B cells.", TB),
            ("\u82e5\u6837\u672c\u9700\u8981\u91cd\u505a\uff0c\u8bf7\u672c\u65b9\u6848\u5b89\u6392\u56fa\u5b9a\u6b65\u9aa4\u3002", FIX),
        )
        for text, function in samples:
            with self.subTest(text=text):
                result = self.proposal(text)
                audit = result["functions"][function]
                self.assertEqual(audit["state"], "CONDITIONAL")
                self.assertEqual(self.req(result, function)["necessity_status"], "UNRESOLVED")
                self.assertTrue(self.req(result, function)["review_required"])
                self.assertTrue(any(span["quote"] == text.split(",")[0]
                                    or span["quote"] == text.split("\uff0c")[0]
                                    for span in audit["question_spans"]))

    def test_condition_stops_at_contrast_and_sentence_boundary(self):
        for separator in (", but ", ". "):
            text = "If needed, please include fixation" + separator + "Please include initial independent QC."
            with self.subTest(separator=separator):
                result = self.proposal(text)
                self.assertEqual(self.req(result, FIX)["necessity_status"], "UNRESOLVED")
                self.assertEqual(self.req(result, QC)["necessity_status"], "REQUIRED")

    def test_diffusion_own_qc_does_not_establish_independent_initial_qc(self):
        samples = (
            "Membrane label diffusion has been completed, its QC passed.",
            "Please include membrane label diffusion and its QC.",
            "\u819c\u5185\u6269\u6563\u5df2\u5b8c\u6210\uff0c\u5176\u8d28\u63a7\u5408\u683c\u3002",
        )
        for text in samples:
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(result["functions"][QC]["mention_status"], "NOT_MENTIONED")
                self.assertEqual(result["functions"][QC]["execution_obligation"], "UNRESOLVED")
                self.assertNotIn(QC, [item["function"] for item in result["requirements"]])


    def test_independent_target_label_and_background_verification_without_qc_word(self):
        for text in (
            "\u72ec\u7acb\u5bf9\u7167\u9a8c\u8bc1\u76ee\u6807\u6bb5\u6807\u8bb0\u53ca\u80cc\u666f\u5408\u683c\u3002",
            "Independent control verified target labeling and background passed.",
        ):
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(result["functions"][QC]["state"], "EXPLICITLY_DONE")
                self.assertEqual(self.req(result, QC)["necessity_status"], "NOT_REQUIRED")
                self.assertIsNone(result["functions"][QC]["scientific_truth"])
                self.assertTrue(result["functions"][QC]["provisional"])
                self.assertEqual(result["functions"][DIFF]["mention_status"], "NOT_MENTIONED")

    def test_qc_verification_relation_requires_all_parts_and_preserves_condition(self):
        for text in (
            "Control verified target labeling and background passed.",
            "Independent control verified target labeling.",
            "Independent control verified background passed.",
        ):
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(result["functions"][QC]["mention_status"], "NOT_MENTIONED")
        result = self.proposal("If independent control verified target labeling and background passed, please report it.")
        self.assertEqual(self.req(result, QC)["necessity_status"], "UNRESOLVED")
        self.assertEqual(result["functions"][QC]["state"], "CONDITIONAL")
        requested = self.proposal("Please perform independent control verified target labeling and background passed.")
        self.assertNotEqual(requested["functions"][QC]["state"], "EXPLICITLY_DONE")

    def test_qc_anaphora_requires_unique_explicit_same_sentence_antecedent(self):
        samples = (
            ("Initial independent QC has not been completed",
             "; please include membrane label diffusion and its QC before clearing."),
            ("\u521d\u59cb\u72ec\u7acbQC\u5c1a\u672a\u5b8c\u6210",
             "\uff1b\u8bf7\u5728\u672c\u6b21\u65b9\u6848\u4e2d\u5b89\u6392\u5b8c\u6210\u819c\u5185\u6269\u6563\u53ca\u5176\u8d28\u63a7\u540e\u518d\u8fdb\u884c\u900f\u660e\u5316\u3002"),
        )
        for antecedent, request in samples:
            text = antecedent + request
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(self.req(result, QC)["necessity_status"], "REQUIRED")
                self.assertEqual(self.req(result, DIFF)["necessity_status"], "REQUIRED")
                instructions = result["functions"][QC]["execution_instructions"]
                self.assertEqual(len(instructions), 1)
                reference = instructions[0]
                self.assertEqual(reference["reference_status"], "PROVEN_SINGLE_EXPLICIT_QC_ANTECEDENT")
                span = reference["antecedent_span"]
                self.assertEqual(span["quote"], antecedent)
                self.assertEqual(text[span["start"]:span["end"]], antecedent)
                self.assertIn(span, self.req(result, QC)["question_spans"])

    def test_qc_anaphora_conflict_contrast_unknown_and_scope_stay_unresolved(self):
        request = "; please include membrane label diffusion and its QC before clearing."
        for antecedent in (
            "If initial independent QC has not been completed",
            "Initial independent QC is unknown",
            "Initial independent QC has been completed and has not been completed",
            "Initial independent QC has not been completed, but it will happen elsewhere",
            "Initial independent QC has not been completed and pre-clearing QC has not been completed",
        ):
            with self.subTest(antecedent=antecedent):
                result = self.proposal(antecedent + request)
                self.assertEqual(self.req(result, QC)["necessity_status"], "UNRESOLVED")
                self.assertTrue(self.req(result, QC)["review_required"])
                self.assertEqual(result["functions"][QC]["execution_instructions"][-1]["reference_status"], "UNRESOLVED")
        result = self.proposal("Initial independent QC has not been completed; however, please include membrane label diffusion and its QC before clearing.")
        self.assertEqual(self.req(result, QC)["necessity_status"], "UNRESOLVED")

    def test_qc_anaphora_does_not_cross_full_sentence_boundary(self):
        result = self.proposal("Initial independent QC has not been completed. Please include membrane label diffusion and its QC before clearing.")
        self.assertEqual(self.req(result, QC)["necessity_status"], "UNRESOLVED")
        self.assertEqual(result["functions"][QC]["execution_instructions"], [])

    def test_t_b_ascii_name_boundaries_allow_adjacent_chinese(self):
        samples = (
            ("\u672c\u9898\u4e0d\u8981\u6c42\u533a\u5206T\u4e0eB\u4e9a\u7fa4\u3002", "NOT_REQUIRED"),
            ("\u672c\u9898\u8981\u6c42\u533a\u5206T/B\u7ec6\u80de\u3002", "REQUIRED"),
            ("\u672c\u9898\u8981\u6c42\u533a\u5206T\u7ec6\u80de\u4e0eB\u7ec6\u80de\u3002", "REQUIRED"),
        )
        for text, status in samples:
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(self.req(result, TB)["necessity_status"], status)
        for text in ("Please distinguish AT/B.", "Please distinguish T/Beta.",
                     "Please distinguish AT cells and B cells."):
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(result["functions"][TB]["mention_status"], "NOT_MENTIONED")


    def test_contrast_before_qc_antecedent_does_not_interrupt_its_request(self):
        texts = (
            "\u819c\u5185\u6269\u6563\u5df2\u5b8c\u6210\uff0c\u4f46\u72ec\u7acb\u521d\u59cbQC\u5c1a\u672a\u5b8c\u6210\uff1b\u8bf7\u5b89\u6392\u5176\u8d28\u63a7\u901a\u8fc7\u540e\u518d\u8fdb\u884c\u900f\u660e\u5316\u3002",
            "Membrane label diffusion has been completed, but initial independent QC has not been completed; please schedule its QC before clearing.",
        )
        for text in texts:
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(self.req(result, QC)["necessity_status"], "REQUIRED")
                self.assertEqual(result["functions"][QC]["execution_instructions"][0]["reference_status"], "PROVEN_SINGLE_EXPLICIT_QC_ANTECEDENT")
                self.assertEqual(result["functions"][DIFF]["state"], "EXPLICITLY_DONE")
                self.assertFalse(self.req(result, DIFF)["necessary"])
        conditional = self.proposal("If needed, initial independent QC has not been completed; please schedule its QC before clearing.")
        self.assertEqual(self.req(conditional, QC)["necessity_status"], "UNRESOLVED")

    def test_t_b_or_frame_retains_explicit_goal_exclusion(self):
        for text in (
            "\u672c\u9898\u4e0d\u8981\u6c42\u533a\u5206 T \u6216 B \u7ec6\u80de\u4e9a\u7fa4\u3002",
            "\u672c\u9898\u4e0d\u8981\u6c42\u533a\u5206T\u6216B\u4e9a\u7fa4\u3002",
            "This task does not require us to distinguish T or B cells.",
        ):
            with self.subTest(text=text):
                result = self.proposal(text)
                self.assertEqual(self.req(result, TB)["necessity_status"], "NOT_REQUIRED")
                self.assertFalse(self.req(result, TB)["necessary"])
        for text in ("Please distinguish AT or B.", "Please distinguish T or Beta."):
            with self.subTest(text=text):
                self.assertEqual(self.proposal(text)["functions"][TB]["mention_status"], "NOT_MENTIONED")

if __name__ == "__main__":
    unittest.main()
