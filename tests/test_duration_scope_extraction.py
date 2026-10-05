import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "extract_clearing_time.py"
spec = importlib.util.spec_from_file_location("duration_module", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DurationScopeTests(unittest.TestCase):
    def test_r16_twice_one_hour(self):
        line = ("1.7 Wash twice with 100% (vol/vol) methanol for 1 hour to remove H2O2."
                "(Temperature: RT, Time: 1 hours)")
        self.assertEqual(m.parse_time_to_hours(line), 2)
        audit = m.audit_duration_scope(line)
        self.assertEqual((audit["repeats"]["count"],
                          audit["per_repeat"]["hours"],
                          audit["total"]["hours"]), (2, 1, 2))

    def test_r16_step_5_5_twice_each_one_hour(self):
        previous = ("5.4 Incubation with 80% (vol/vol) methanol in distilled water "
                    "for 1 hour, protected from light.(Temperature: RT, Time: 1 hours)")
        line = ("5.5 Incubation with 100% (vol/vol) methanol twice, each for 1 hour, "
                "protected from light.(Temperature: RT, Time: 1 hours)")
        following = ("5.6 Incubation with 66% (vol/vol) Dichloromethane (DCM) in "
                     "Methanol for 3 hours, protected from light."
                     "(Temperature: RT, Time: 3 hours)")
        self.assertTrue(previous and following)
        self.assertEqual(m.parse_time_to_hours(line), 2)
        audit = m.audit_duration_scope(line)
        self.assertEqual(audit["repeats"]["count"], 2)
        self.assertEqual(audit["per_repeat"]["hours"], 1)
        self.assertEqual(audit["total"]["hours"], 2)
    def test_r16_each_15_minutes_with_total_metadata(self):
        previous = ("5.6 Incubation with 66% (vol/vol) Dichloromethane (DCM) in "
                    "Methanol for 3 hours.(Temperature: RT, Time: 3 hours)")
        line = ("5.7 Incubation with 100% (vol/vol) Dichloromethane (DCM) twice, "
                "each for 15 minutes to remove lipids, protected from light."
                "(Temperature: RT, Time: 0.5 hours)")
        following = "6 Refractive Index Matching and Storage"
        self.assertTrue(previous and following)
        self.assertEqual(m.parse_time_to_hours(line), 0.5)
        audit = m.audit_duration_scope(line)
        self.assertEqual(audit["per_repeat"]["hours"], 0.25)
        self.assertEqual(audit["metadata"]["hours"], 0.5)

    def test_r16_total_window_not_multiplied(self):
        previous = ("4.1 Incubation with DAPI diluted 1:1000 in PBS for 24 hours."
                    "(Temperature: RT, Time: 24 hours)")
        line = ("4.2 Wash with PBS for 6 hours, changing solution every 2 hours, "
                "protected from light.(Temperature: RT, Time: 6 hours)")
        following = "5 Dehydration for Clearing"
        self.assertTrue(previous and following)
        self.assertEqual(m.parse_time_to_hours(line), 6)
        audit = m.audit_duration_scope(line)
        self.assertEqual(audit["interval"]["hours"], 2)
        self.assertIsNone(audit["repeats"])

    def test_equivalent_7_days_168_hours_not_added(self):
        line = ("3.1 Primary Antibody Incubation with Guinea Pig anti-Insulin "
                "for 7 days.(Temperature: RT, Time: 168 hours)")
        self.assertEqual(m.parse_time_to_hours(line), 168)

    def test_conflict_is_unknown(self):
        line = ("Incubation with methanol twice, each for 1 hour."
                "(Temperature: RT, Time: 3 hours)")
        self.assertEqual(m.audit_duration_scope(line)["status"], "AMBIGUOUS")
        self.assertIsNone(m.parse_time_to_hours(line))

    def test_utf8_chinese(self):
        self.assertEqual(m.parse_time_to_hours(
            "脱水：甲醇孵育2小时。(Temperature: RT, Time: 2小时)"), 2)


    def test_explicit_total_not_multiplied_by_repeats(self):
        self.assertEqual(m.parse_time_to_hours("Wash twice for 1 hour total."), 1)

    def test_multiple_operation_durations_are_not_silently_dropped(self):
        self.assertIsNone(m.parse_time_to_hours("Incubate for 1 hour, then wash for 2 hours."))

    def test_interval_change_count_is_not_operation_repeat(self):
        text = "Wash for 6 hours, changing solution every 2 hours for 3 changes."
        self.assertEqual(m.parse_time_to_hours(text), 6)
        self.assertEqual(m.audit_duration_scope(text)["interval"]["hours"], 2)

    def test_repeat_after_duration_retains_exact_witness(self):
        text = "Wash for 1 hour, twice."
        audit = m.audit_duration_scope(text)
        self.assertEqual(m.parse_time_to_hours(text), 2)
        start, end = audit["total"]["span"]
        self.assertLess(start, end)
        self.assertEqual(text[start:end], audit["total"]["quote"])

    def test_metadata_outside_range_is_unknown(self):
        self.assertIsNone(m.parse_time_to_hours("Incubate for 2-3 hours.(Temperature: RT, Time: 10 hours)"))

    def test_open_repetition_is_unknown(self):
        self.assertIsNone(m.parse_time_to_hours("Incubate for 1 hour and repeat until complete."))

    def test_legacy_range_without_metadata_still_uses_midpoint(self):
        self.assertEqual(m.parse_time_to_hours("Incubate for 2-3 hours."), 2.5)



    def test_compound_duration_is_not_partially_certified(self):
        text = "Incubate for 1 hour 45 minutes."
        self.assertIsNone(m.parse_time_to_hours(text))
        self.assertEqual(m.audit_duration_scope(text)["status"], "AMBIGUOUS")

    def test_time_unit_prefix_is_not_a_duration(self):
        self.assertIsNone(m.parse_time_to_hours("Incubate for 1 hourly cycle."))


if __name__ == "__main__":
    unittest.main()

