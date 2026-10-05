"""Selection scope and alternative acceptance controls; engineering, not scientific gold."""
import unittest
from oeq_scientific import _method_audit
from experiments.construct_validity.answer_matching import summarize_answer_matching


def method_audit(text,names=("CUBIC",),quote_only=False):
    branch=dict(id="main",mode="SERIAL",sample_id="main",spans=[])
    declarations=[]
    for name in names:
        start=text.index(name)
        span={"quote":name} if quote_only else dict(start=start,end=start+len(name),quote=name)
        declarations.append(dict(name=name,branch="main",span=span))
    return _method_audit(dict(method_declarations=declarations),dict(branches=[branch],steps=[]),
                         dict(method_keys=["CUBIC","FDISCO"]),text)


class SelectionScopeTests(unittest.TestCase):
    def test_other_negative_method_does_not_negate_selected_method(self):
        for text in ["Use CUBIC; do not use FDISCO.","Use CUBIC. Do not use FDISCO.",
                     "Do not use FDISCO; choose CUBIC."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"SATISFIED")

    def test_other_conditional_consideration_is_not_selected(self):
        self.assertEqual(method_audit("Use CUBIC; if needed, consider FDISCO.")["status"],"SATISFIED")

    def test_selected_method_own_negative_or_condition_remains_unresolved(self):
        for text in ["Do not use CUBIC; use FDISCO.","If ready, use CUBIC; do not use FDISCO.",
                     "I might choose CUBIC.","If needed, choose CUBIC."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"UNRESOLVED")

    def test_generic_controls_are_not_dropped_at_semicolon_or_newline(self):
        for text in ["Do not perform the following; choose CUBIC.",
                     "If the sample is ready; choose CUBIC.",
                     "If the sample is ready:\nchoose CUBIC."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"UNRESOLVED")

    def test_generic_condition_survives_blank_and_ordinary_lines(self):
        for text in ["If ready:\n\nChoose CUBIC.","If ready:\nFirst prepare the sample.\nChoose CUBIC."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"UNRESOLVED")

    def test_other_candidate_condition_cannot_enter_current_candidate(self):
        text="If ready;\nChoose CUBIC."
        branches=[dict(id="A",mode="ALTERNATIVE",sample_id="a",spans=[dict(start=0,end=9,quote=text[:9])]),
                  dict(id="B",mode="ALTERNATIVE",sample_id="b",spans=[dict(start=10,end=len(text),quote=text[10:])])]
        start=text.index("CUBIC")
        result=_method_audit(dict(method_declarations=[dict(name="CUBIC",branch="B",span=dict(start=start,end=start+5,quote="CUBIC"))]),
                  dict(branches=branches,steps=[]),dict(method_keys=["CUBIC","FDISCO"]),text)
        current=result["declarations"][0]
        self.assertEqual(current["guards"],[])
        self.assertNotIn("If ready",current["assertion_context"])
        self.assertEqual(result["status"],"UNDER_SPECIFIED")  # A declaration remains absent.

    def test_negative_parameter_or_skip_does_not_hide_second_selected_method(self):
        for text in ["Use CUBIC; use FDISCO without heating.","Use CUBIC; do not skip FDISCO."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"UNRESOLVED")

    def test_omitted_second_affirmed_selection_is_unresolved(self):
        for text in ["Use CUBIC; use FDISCO.","Choose CUBIC.\nChoose FDISCO."]:
            with self.subTest(text=text):self.assertEqual(method_audit(text)["status"],"UNRESOLVED")

    def test_two_bound_selected_methods_are_not_one_method(self):
        self.assertEqual(method_audit("Use CUBIC; use FDISCO.",("CUBIC","FDISCO"))["status"],"VIOLATED")

    def test_markdown_choose_and_select_are_bound_without_claiming_finality(self):
        for text in ["*Decision:* I will choose **CUBIC**.","We select **CUBIC**."]:
            result=method_audit(text)
            self.assertEqual(result["status"],"SATISFIED")
            self.assertTrue(result["declarations"][0]["selected_role_established"])
            self.assertEqual(result["selection_finality"],"NOT_CERTIFIED")

    def test_repeated_name_resolves_only_one_supported_selection_occurrence(self):
        result=method_audit("I will choose **CUBIC**.\nCUBIC is mentioned for comparison.",quote_only=True)
        self.assertEqual(result["status"],"SATISFIED")
        self.assertEqual(result["declarations"][0]["span"]["start"],len("I will choose **"))

    def test_unselected_example_does_not_establish_selection(self):
        self.assertEqual(method_audit("Example: choose CUBIC.")["status"],"UNRESOLVED")


def requirement(rid,*,necessary=True,route=None):
    value=dict(id=rid,kind="TEXT",text=rid,necessary=necessary,evidence_ids=[])
    if route is not None:value.update(scope="ROUTE",route_id=route)
    return value


def summary(reqs,statuses,routes,overall):
    records=[dict(id=r["id"],effective_status=statuses[r["id"]],guards=[]) for r in reqs]
    return summarize_answer_matching(reqs,records,[dict(route_id=k,status=v) for k,v in routes.items()],overall,"a"*64)


class AnswerMatchingSummaryTests(unittest.TestCase):
    def test_failure_in_other_alternative_does_not_block_valid_candidate(self):
        reqs=[requirement("a",route="A"),requirement("b",route="B")]
        value=summary(reqs,{"a":"SATISFIED","b":"VIOLATED"},{"A":"SATISFIED","B":"VIOLATED"},"SATISFIED")
        self.assertEqual(value["contract_status"],"SATISFIED")
        self.assertEqual(value["matched_declared_candidate_ids"],["A"])
        self.assertEqual(value["candidate_necessary_failures"]["B"],["b"])
        self.assertEqual(value["global_necessary_failures"],[])

    def test_required_failure_stays_visible_independent_of_numeric_mean(self):
        value=summary([requirement("chem")],{"chem":"VIOLATED"},{},"VIOLATED")
        self.assertEqual(value["global_necessary_failures"],["chem"])
        self.assertFalse(value["numerical_mean_overrides_failure"])
        self.assertIsNone(value["scientific_accuracy"])

    def test_optional_failure_does_not_become_required_failure(self):
        reqs=[requirement("required"),requirement("optional",necessary=False)]
        value=summary(reqs,{"required":"SATISFIED","optional":"VIOLATED"},{},"SATISFIED")
        self.assertEqual(value["global_necessary_failures"],[])
        self.assertEqual(value["optional_requirement_failures"],["optional"])

    def test_unknown_is_pending_and_not_error_detection(self):
        value=summary([requirement("r")],{"r":"UNRESOLVED"},{},"UNRESOLVED")
        self.assertEqual(value["pending_necessary_requirement_ids"],["r"])
        self.assertEqual(value["global_necessary_failures"],[])

    def test_missing_requirement_or_route_cannot_fabricate_full_match(self):
        reqs=[requirement("a",route="A")]
        with self.assertRaises(ValueError):summary(reqs,{"a":"SATISFIED"},{},"SATISFIED")
        with self.assertRaises(ValueError):summarize_answer_matching(reqs,[],[],"SATISFIED","a"*64)


if __name__=="__main__":unittest.main()
