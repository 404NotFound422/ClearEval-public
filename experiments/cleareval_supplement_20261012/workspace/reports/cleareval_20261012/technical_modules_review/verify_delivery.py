"""Verify this research delivery, without invoking models or scoring functions."""
from pathlib import Path
import hashlib
import json
import math
import re

HERE = Path(__file__).resolve().parent
checks = []


def check(name, passed, detail=None):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8-sig"))


evidence = read("LOCAL_EVIDENCE.json")
sources = read("SOURCES.json")["sources"]
cards = read("PROBLEM_CARDS.json")["problems"]
source_ids = {s["id"] for s in sources}
check("26 unique core sources", len(sources) == len(source_ids) == 26)
check("10 unique problem cards", len(cards) == len({c["id"] for c in cards}) == 10)
for card in cards:
    check("card references: " + card["id"], set(card["literature"]) <= source_ids)
for src in sources:
    check("source scope: " + src["id"], all(src.get(k) for k in ("status", "read", "use", "limit", "url")))

local_link_count = 0
web_links = set()
for md in HERE.glob("*.md"):
    text = md.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\n]+)\)", text):
        if target.startswith(("https://", "http://")):
            web_links.add(target)
            continue
        if target.startswith("#"):
            continue
        target = re.sub(r":\d+$", "", target.split("#", 1)[0].strip("<>"))
        path = (md.parent / target).resolve()
        # verification.json is the output of this check and is created below.
        exists = path.exists() or path == HERE / "verification.json"
        check(f"local link: {md.name} -> {target}", exists)
        local_link_count += 1

for item in evidence["source_files"]:
    path = Path(item["path"])
    check("input sha256: " + str(path), path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"])

current = evidence["current_cohort_counts"]
archived = evidence["archive_counts"]
check("current complete definitions", current["numeric_complete_including_inherited_points"] == 29 and current["numeric_complete_and_current_time_ledger_unbranched"] == 28)
check("archive complete definitions", archived["saved_returns_with_metrics"] == 67 and archived["numeric_complete_including_inherited_points"] == 49 and archived["numeric_complete_and_current_time_ledger_unbranched"] == 47)
lang = evidence["language_probe_historical"]["rows"]
for aid, sr, sp in (("R3C04", 1/3, 1/3), ("R3C07", 4/7, 1/19)):
    match = [r for r in lang if r["answer_id"] == aid and r["representation"] == "english_body_original_metadata" and r["threshold"] == .7]
    check("language example " + aid, len(match) == 1 and math.isclose(match[0]["sr"], sr) and math.isclose(match[0]["sp"], sp))
pairs = evidence["C07_english_at_0p7_matched_pairs"]
check("C07 shared generated index", len(pairs) == 4 and {p["generated_index"] for p in pairs} == {13})
joint = evidence["joint_historical"]
check("joint cohort and scenarios", joint["actual_generator_answers"] == 4 and len(joint["paired_tasks"]) == 2 and joint["automatic_timing_scenarios"] == 8)
for hours, sign in ((14.0, 1), (17.0, -1)):
    row = next(r for r in joint["values"] if r["C05_hours"] == hours and r["C08_hours"] == 32.0)
    check("HV example sign at C05=" + str(hours), row["delta_HV"] * sign > 0)
check("no new research experiment", all(evidence[k] == 0 for k in ("new_model_calls", "new_embeddings", "new_experimental_observations", "new_expert_records", "new_score_calculations")))

delivery_files = []
for path in sorted(HERE.iterdir()):
    if path.is_file() and path.name != "verification.json":
        delivery_files.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
result = {"scope": "Document/local-input checks, not scientific validation, peer review or new evaluation trials",
          "passed": all(c["passed"] for c in checks), "check_count": len(checks),
          "local_links_checked": local_link_count, "web_links_in_documents": len(web_links),
          "web_links_requeried_by_this_script": False, "new_model_calls": 0,
          "checks": checks, "delivery_files": delivery_files}
(HERE / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ("passed", "check_count", "local_links_checked", "web_links_in_documents", "new_model_calls")}, ensure_ascii=False))
for item in checks:
    if not item["passed"]:
        print("FAIL:", item["check"])
raise SystemExit(0 if result["passed"] else 1)
