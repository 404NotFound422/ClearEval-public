"""Offline checks for a source-verified clone-to-target recognition relation."""
import unittest

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


if __name__ == '__main__':
    unittest.main()
