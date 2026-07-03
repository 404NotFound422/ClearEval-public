import json
from pathlib import Path

MAIN_JSON = Path("dataset/Q+AR/result/Machine_vs_Human_Summary.json")

with open(MAIN_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Records: {len(data)}")

bad_totals = 0
for rec in data:
    he = rec["human_evaluation"]["effectiveness"]

    expected_eff = (
        he["s_method"]["score"]
        + he["s_label"]["score"]
        + he["s_trans"]["score"]
        + he["s_time"]["score"]
    )
    if abs(he["total_score"] - round(expected_eff, 2)) > 0.01:
        bad_totals += 1

    expected_overall = (
        rec["human_evaluation"]["completeness"]["total_score"]
        + rec["human_evaluation"]["correctness"]["total_score"]
        + expected_eff
    )
    if abs(rec["human_evaluation"]["overall_total_score"] - round(expected_overall, 2)) > 0.01:
        bad_totals += 1

    assert 0 <= rec["human_evaluation"]["effectiveness"]["s_label"]["score"] <= 6
    assert 0 <= rec["human_evaluation"]["effectiveness"]["s_trans"]["score"] <= 3

print(f"Bad totals: {bad_totals}")
print("All score ranges OK.")
assert bad_totals == 0
