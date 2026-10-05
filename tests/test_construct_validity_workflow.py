"""Blind import, grouped statistics and standalone reviewer-form checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.construct_validity.contract import digest,read,save
from experiments.construct_validity.review import import_ratings
from experiments.construct_validity.review_html import create_html
from experiments.construct_validity.statistics import entropy,paired_cluster_interval,risk_counts,zero_error_design

class StatisticalTests(unittest.TestCase):
    def test_missing_reference_denominator_is_not_zero_error(self):
        self.assertIsNone(risk_counts([])["false_accept"]["value"])

    def test_unknowns_and_failures_remain_visible(self):
        rows=[{"reference":"VIOLATED","prediction":"SATISFIED"},
              {"reference":"VIOLATED","prediction":"UNRESOLVED"},
              {"reference":"VIOLATED","prediction":None}]
        r=risk_counts(rows)
        self.assertEqual(r["false_accept"]["numerator"],1)
        self.assertEqual(r["false_accept"]["denominator"],3)
        self.assertAlmostEqual(r["decisive_coverage"]["value"],1/3)
        self.assertAlmostEqual(r["technical_failure"]["value"],1/3)

    def test_population_interval_requires_independent_reference(self):
        self.assertEqual(paired_cluster_interval([])["status"],"NOT_ESTIMABLE")

    def test_too_few_source_groups_does_not_gain_n_from_variants(self):
        rows=[{"pair_id":str(i),"source_group":"one","a":0,"b":1} for i in range(100)]
        result=paired_cluster_interval(rows,independent_reference=True,grouped_holdout=True)
        self.assertEqual(result["groups"],1)
        self.assertIsNone(result["low"])

    def test_pair_identity_duplicates_rejected(self):
        row={"pair_id":"x","source_group":"one","a":0,"b":1}
        with self.assertRaises(ValueError):
            paired_cluster_interval([row,row],independent_reference=True,grouped_holdout=True)

    def test_equal_source_weighting_not_variant_weighting(self):
        rows=[{"pair_id":str(i),"source_group":str(i),"a":0,"b":float(i>0)} for i in range(10)]
        rows.extend({"pair_id":"extra"+str(i),"source_group":"0","a":0,"b":0} for i in range(50))
        result=paired_cluster_interval(rows,independent_reference=True,grouped_holdout=True,resamples=200)
        self.assertAlmostEqual(result["estimate"],.9)
        again=paired_cluster_interval(rows,independent_reference=True,grouped_holdout=True,resamples=200)
        self.assertEqual(result,again)

    def test_empirical_entropy_is_not_overall_repeat_agreement(self):
        self.assertEqual(entropy(["A","B"]),1)
        self.assertEqual(entropy(["UNKNOWN","UNKNOWN"]),0)
        self.assertIsNone(entropy([]))

    def test_zero_error_design_uses_independent_negative_cases(self):
        self.assertEqual(zero_error_design(.05)["minimum_independent_negatives_if_zero_errors"],59)
        self.assertEqual(zero_error_design(.01)["minimum_independent_negatives_if_zero_errors"],299)


class ReviewTests(unittest.TestCase):
    def fixture(self,root):
        packet={"version":"fixture","cases":[{"review_id":"OPAQUE","question":"fixture",
                    "protocol":"no joining","requirements":[{"id":"R","text":"no joining","kind":"TEXT","necessary":True}],"sources":[]}],
                "instructions":"fixture"}
        packet["package_sha256"]=digest(packet)
        save(root/"package/public/cases.json",packet)
        form={"package_sha256":packet["package_sha256"],
              "reviewer":{"id":"SYNTHETIC_TEST_ONLY","expertise":"fixture","years_experience":None,"method_familiarity":"fixture",
                          "participated_in_task_design":False,"saw_automatic_judgments":False,"saw_other_raters":False},
              "rating_type":"INDEPENDENT_FIRST_PASS",
              "ratings":[{"review_id":"OPAQUE","requirement_id":"R","status":"SATISFIED",
                          "reason":"explicit text","protocol_quotes":["no joining"],"evidence_urls":[],"requirement_dispute":None}]}
        save(root/"package/public/ratings_template.json",form)
        return form

    def submit(self,root,form,name="input.json"):
        path=root/name
        save(path,form)
        return import_ratings(root/"package",path,root/"imports")

    def test_template_without_ratings_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);form["ratings"][0]["status"]=None
            with self.assertRaises(ValueError): self.submit(root,form)

    def test_changed_package_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);form["package_sha256"]="wrong"
            with self.assertRaises(ValueError): self.submit(root,form)

    def test_duplicate_requirement_rating_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);form["ratings"]*=2
            with self.assertRaises(ValueError): self.submit(root,form)

    def test_seen_auto_labels_not_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);form["reviewer"]["saw_automatic_judgments"]=True
            result=self.submit(root,form)
            self.assertFalse(result["independent_by_disclosure"])

    def test_identical_import_is_idempotent_not_new_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root)
            result=self.submit(root,form)
            self.assertEqual(result,self.submit(root,form))
            self.assertEqual(len(list((root/"imports").glob("*/ratings.json"))),1)
            self.assertFalse(result["reviewer_identity_authenticated"])

    def test_changed_first_pass_cannot_silently_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);self.submit(root,form)
            changed=deepcopy(form);changed["ratings"][0]["status"]="VIOLATED"
            with self.assertRaises(ValueError): self.submit(root,changed,"changed.json")
            self.assertEqual(len(list((root/"imports").glob("*/ratings.json"))),1)

    def test_adjudication_preserved_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);self.submit(root,form)
            form["rating_type"]="ADJUDICATION";form["ratings"][0]["status"]="VIOLATED"
            result=self.submit(root,form,"adjudication.json")
            self.assertFalse(result["independent_by_disclosure"])
            self.assertEqual(len(list((root/"imports").glob("*/ratings.json"))),2)

    def test_fabricated_protocol_quote_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);form=self.fixture(root);form["ratings"][0]["protocol_quotes"]=["never present"]
            with self.assertRaises(ValueError): self.submit(root,form)

    def test_review_form_embeds_literal_data_and_no_expected_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);create_html(root/"package")
            html=(root/"package/public/review.html").read_text(encoding="utf-8")
            self.assertIn("application/json",html)
            self.assertIn("textContent",html)
            self.assertNotIn("fetch(",html)
            self.assertNotIn("XMLHttpRequest",html)
            self.assertNotIn('"expected":',html)
            self.assertIn("\\n",html)
            self.assertIn("s.identity?.url||s.url",html)
            self.assertIn("Primary passage",html)
            self.assertIn("correction.text",html)

if __name__=="__main__":
    unittest.main()
