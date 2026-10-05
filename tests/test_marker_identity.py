"""Offline checks for a source-verified clone-to-target recognition relation."""
import unittest
import json
from pathlib import Path

import OEQ_run_grading_new as scorer
from verified_marker_aliases import same_verified_target


class MarkerIdentityTests(unittest.TestCase):
    def test_production_matcher_uses_verified_identity_without_partial_clone_matches(self):
        self.assertTrue(scorer._match_marker_to_targets('MECA-79 (HEV)', [{'marker_name': 'PNAd'}]))
        self.assertTrue(scorer._match_marker_to_targets('MECA‑79', [{'marker_name': 'PNAd'}]))
        self.assertFalse(scorer._match_marker_to_targets('MECA-790', [{'marker_name': 'PNAd'}]))
        self.assertFalse(scorer._match_marker_to_targets('MECA-32', [{'marker_name': 'PNAd'}]))

    def test_clone_annotations_do_not_change_target_recognition(self):
        for name in ('MECA-79', 'MECA-79 (HEV)', 'MECA-79 (anti-HEV, PNAd相关糖链)',
                     'MECA79', 'MECA-79（HEV）', 'MECA‑79', 'MECA  79'):
            with self.subTest(name=name):
                self.assertTrue(same_verified_target(name, 'PNAd'))

    def test_generic_vessels_and_other_clones_are_not_pnad(self):
        for name in ('HEV', 'CD31', 'endothelium', 'MECA-32', 'MECA-790', 'MECA-79a'):
            with self.subTest(name=name):
                self.assertFalse(same_verified_target(name, 'PNAd'))

    def test_identity_mapping_does_not_change_dye_mapping(self):
        self.assertFalse(same_verified_target('Alexa Fluor 647', 'PNAd'))
        self.assertFalse(same_verified_target('MECA-79', 'CD31'))


    def test_shared_numeric_prefix_does_not_establish_marker_identity(self):
        self.assertFalse(scorer._match_marker_to_targets('CD3', [{'marker_name': 'CD31'}]))
        self.assertFalse(scorer._match_marker_to_targets('CD31', [{'marker_name': 'CD3'}]))
        self.assertTrue(scorer._match_marker_to_targets('CD31 (endothelium)', [{'marker_name': 'CD31'}]))

    def test_actual_qwen_pnad_expansion_conflict_is_not_rescued_by_alias_stripping(self):
        marker = "PNAd (P-Selectin Adhesion Molecule)"
        self.assertFalse(same_verified_target(marker, "PNAd"))
        self.assertIsNone(scorer._match_marker_to_targets(marker, [{"marker_name": "PNAd"}]))
        coverage = scorer._marker_target_coverage([("Alexa Fluor 594", marker)], {"marker_name": "PNAd"})
        self.assertIsNone(coverage["matched"])
        self.assertEqual(coverage["status"], "UNKNOWN_IDENTITY_CONFLICT")
        self.assertIsNone(coverage["scientific_satisfaction"])
        # Use the complete actual teacher extraction, not just the conflicting token.
        markers = {"Alexa Fluor 594": marker, "Alexa Fluor 488": "CD3", "DAPI": ""}
        result = scorer.calculate_effectiveness_score(
            {"method_name": "MACS", "tissue_ri_value": 1.51, "total_time_hours": 120,
             "sample_tier": "T03_SMALL_WHOLE_SAMPLE_1_5MM", "reagent_ri_value": 1.53},
            {}, {}, markers, [{"marker_name": "PNAd"}, {"marker_name": "CD31 / PECAM1"}])
        actual_coverage = result["marker_coverage_audit"]["reference_targets"][0]
        self.assertIsNone(actual_coverage["matched"])
        self.assertEqual(actual_coverage["status"], "UNKNOWN_IDENTITY_CONFLICT")
        self.assertIsNone(result["s_marker_fluor_compat"])
        self.assertNotEqual(result["s_label"], 6)


    def test_actual_q79_optional_cd3_mismatch_does_not_zero_conflicted_hev_identity(self):
        question_path = Path(scorer.__file__).parent / "dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json"
        question = next(item for item in json.loads(question_path.read_text(encoding="utf-8"))
                        if item["question_id"] == 79)
        # Frozen Qwen Q8 teacher extraction; no invented marker pair or timing value.
        extraction = {"method_name": "MACS", "clearing_total_time_hours": 120,
                      "reagent_ri_value": 1.53, "sample_ri_value": None,
                      "marker_dict": {"Alexa Fluor 594": "PNAd (P-Selectin Adhesion Molecule)",
                                      "Alexa Fluor 488": "CD3", "DAPI": ""}}
        data = {"method_name": extraction["method_name"], "tissue_ri_value": 1.51,
                "total_time_hours": extraction["clearing_total_time_hours"],
                "sample_tier": question["tissue_hierarchy_from_tissue_xlsx"]["tissue_tier_code"],
                "reagent_ri_value": extraction["reagent_ri_value"]}
        result = scorer.calculate_effectiveness_score(data, {}, {}, extraction["marker_dict"],
                                                     question["marker_query_targets"])
        self.assertIsNone(result["s_target_match"])
        self.assertIsNone(result["s_label"])
        self.assertIsNone(result["total_effectiveness_score"])
        self.assertEqual(result["marker_coverage_audit"]["reference_targets"][0]["status"],
                         "UNKNOWN_IDENTITY_CONFLICT")
        # With no conflict, an explicitly different selected marker can remain a zero diagnostic.
        missing = scorer.calculate_effectiveness_score(data, {}, {}, {"Alexa Fluor 488": "CD3"},
                                                      question["marker_query_targets"])
        self.assertEqual(missing["s_target_match"], 0)
        self.assertEqual(missing["s_label"], 0)

    def test_legitimate_parenthetical_alias_and_clone_remain_lexically_matched(self):
        for marker, target in (("CD31 (PECAM1)", "CD31 / PECAM1"),
                               ("PNAd (peripheral node addressin)", "PNAd"),
                               ("MECA-79 (HEV)", "PNAd")):
            with self.subTest(marker=marker):
                self.assertTrue(scorer._match_marker_to_targets(marker, [{"marker_name": target}]))
                coverage = scorer._marker_target_coverage([("Alexa Fluor 647", marker)], {"marker_name": target})
                self.assertTrue(coverage["matched"])
                self.assertEqual(coverage["status"], "LEXICAL_ALIAS_MATCH")
                self.assertIsNone(coverage["scientific_satisfaction"])

    def test_dye_numbers_do_not_match_longer_prefixes(self):
        for mapper in (scorer._map_fluor_to_tissue_col, scorer._map_fluor_to_method_key):
            with self.subTest(mapper=mapper.__name__):
                self.assertIsNone(mapper('Alexa Fluor 6470'))
                self.assertIsNone(mapper('Cy50'))
                self.assertIsNotNone(mapper('Alexa Fluor 647'))
                self.assertEqual(mapper('Alexa Fluor 647 (antibody conjugate)'), mapper('Alexa Fluor 647'))


if __name__ == '__main__':
    unittest.main()
