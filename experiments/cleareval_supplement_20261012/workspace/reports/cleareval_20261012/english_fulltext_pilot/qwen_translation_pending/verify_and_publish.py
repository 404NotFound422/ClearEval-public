"""Verify this completed batch from saved evidence, then update local navigation."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from urllib.parse import unquote

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PILOT = HERE.parent
DAY = PILOT.parent
WORKSPACE = Path(r"C:\ClearEval")
REPO = WORKSPACE / "ClearEval-public"
R3 = REPO / "artifacts/cce_validation/optimizer_round3_20261011"
sys.path.insert(0, str(HERE))
import score_translations as s
import numpy as np

checks = []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


def bound(binding):
    check("unchanged " + binding["path"], s.bind(binding["path"]) == binding)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-7)


def main():
    auth = s.read(HERE / "authorization.json")
    bound(auth["prepared_freeze"])
    check("exact approved reply", auth["user_reply"] == "好的，继续")
    for name, key in [(HERE / "freeze.json", "inputs"),
                      (PILOT / "execution_freeze.json", "inputs"),
                      (PILOT / "run_01/completion.json", "outputs"),
                      (R3 / "confirmation_inputs_01/source_bindings.json", "bindings")]:
        for binding in s.read(name)[key]:
            bound(binding)
    ledger = REPO / "artifacts/cce_validation/judges/request_ledger.jsonl"
    previous = (HERE / "ledger_before_execution.jsonl").read_bytes()
    current = ledger.read_bytes()
    check("previous ledger snapshot matches frozen digest",
          hashlib.sha256(previous).hexdigest() == s.read(HERE / "freeze.json")["ledger_before"]["sha256"])
    check("original ledger byte prefix preserved", current.startswith(previous))
    rows = [json.loads(line) for line in current.decode("utf-8-sig").splitlines() if line]
    added = [json.loads(line) for line in current[len(previous):].decode("utf-8").splitlines() if line]
    check("446 request starts, exactly eight added", len(rows) == 446 and len(added) == 8 and all(r["event"] == "request_started" for r in rows))
    check("new indices and scope", [r["package_request_index"] for r in added] == list(range(439, 447)) and all(r["round_id"] == "fulltext_english_translation_20261012" for r in added))
    check("unique added requests and one attempt each", len({r["request_id"] for r in added}) == 8 and all(r["attempt"] == 1 for r in added))
    budget = s.read(REPO / "artifacts/cce_validation/budget.json")
    check("budget 446 of 446", budget["attempts_recorded"] == budget["package_limit"] == 446 and budget["remaining_request_capacity"] == 0)
    bound(budget["authorization"])
    bound(budget["ledger"])
    config = s.read(HERE / "scoring/summary.json")["config"]
    check("original threshold", config["threshold"] == .7)
    for key in ["core", "family", "script", "baseline_results"]:
        bound(config[key])
    preflight = s.read(HERE / "runtime_preflight.json")
    check("saved local model digest", preflight["model"]["digest"] == "ea6892d079c639acf4812dee100eca284199c3ae3fb4ffd9e5a5ae8641ae73ba")
    results = s.read(HERE / "scoring/results.json")
    result_by = {r["request_id"]: r for r in results}
    records = s.read(HERE / "reviewed_readout.json")
    reviewed = {r["request_id"]: r for r in records}
    execution = s.read(HERE / "execution_summary.json")
    check("eight distinct translations and readouts", len(results) == len(result_by) == len(reviewed) == len(execution["terminals"]) == 8)
    vector_bindings = {}
    for path in (HERE / "scoring/executions").glob("*.json"):
        record = s.read(path)
        for binding in record["used_vectors"] + record["new_vector_files"]:
            vector_bindings[binding["path"]] = binding
    for binding in vector_bindings.values():
        bound(binding)
    cache = {Path(b["path"]).name: Path(b["path"]) for b in vector_bindings.values()}
    identity = s.read(PILOT / "run_01/encoder_provenance.json")["identity"]

    def vectors(texts):
        return np.asarray([np.load(cache[s.core.digest([identity, text]) + ".npy"]) for text in texts])

    for item in s.read(HERE / "matrix.json"):
        rid = item["request_id"]
        terminal_path = HERE / "returns" / rid / "terminal.json"
        terminal = s.read(terminal_path)
        check("terminal included in execution " + rid, terminal in execution["terminals"])
        for key in ["payload", "source", "translation", "raw_response", "response_content"]:
            bound(terminal[key])
        request = terminal["request"]
        check("ledger and payload bound " + rid, request in added and request["authorization_sha256"] == s.bind(HERE / "authorization.json")["sha256"] and request["payload_sha256"] == item["payload"]["sha256"])
        start, finish = map(datetime.fromisoformat, [request["started_utc"], terminal["finished_utc"]])
        check("within authorized window " + rid, datetime.fromisoformat(auth["start_utc"]) <= start <= finish <= datetime.fromisoformat(auth["deadline_utc"]))
        raw = s.read(terminal["raw_response"]["path"])
        content = s.text(terminal["response_content"]["path"])
        english = s.text(terminal["translation"]["path"])
        parsed = json.loads(content)
        check("unmodified raw response to English " + rid, raw["response"] == content and parsed == {"english_text": english.rstrip("\n")} and raw["done"] and raw["done_reason"] == "stop" and raw["model"] == preflight["model"]["name"])
        r = result_by[rid]
        bound(r["terminal"])
        check("per-answer saved score " + rid, r == s.read(HERE / "scoring" / (rid + ".json")))
        check("score identity " + rid, r["calculation_identity"] == s.core.digest([config, s.bind(terminal_path), terminal["translation"]]))
        check("full translation reparsed " + rid, r["generated_steps"] == s.core.segment(english))
        gt = [step["text"] for step in r["generated_steps"]]
        for candidate in r["all_candidates"]:
            score = candidate["score"]
            matrix = np.asarray(candidate["similarity_matrix"])
            rt = [m["reference_text"] for m in score["matches"]]
            check("cache reproduces matrix " + rid + candidate["reference_id"], np.allclose(vectors(rt) @ vectors(gt).T, matrix, rtol=0, atol=1e-6))
            rh = sum(float(v) >= .7 for v in matrix.max(axis=1))
            gh = sum(float(v) >= .7 for v in matrix.max(axis=0))
            check("raw SR SP arithmetic " + rid + candidate["reference_id"], score["reference_hits"] == rh and score["generated_hits"] == gh and matrix.shape == (score["reference_n"], score["generated_n"]) and close(score["sr"], rh / len(rt)) and close(score["sp"], gh / len(gt)))
            check("source artifact exists " + rid + candidate["reference_id"], Path(candidate["source_path"]).is_file())
        chosen = max(r["all_candidates"], key=lambda c: (c["score"]["sr"], c["score"]["sp"], -c["fixed_order"]))
        check("whole-version selection " + rid, chosen == r["selected"])
        check("readout preserves actual score " + rid, all(reviewed[rid][key] == chosen["score"][key] for key in ["sr", "sp", "reference_hits", "reference_n", "generated_hits", "generated_n"]))
        check("machine audit reproducible " + rid, r["translation_audit"] == s.audit(s.text(r["source"]["path"]), english))
    by = {(r["answer_id"], r["condition"]): r for r in results}
    pairs = s.read(HERE / "reviewed_pairs.json")
    check("six actual pairs", len(pairs) == 6)
    for p in pairs:
        base = by[p["answer_id"], "baseline"]["selected"]
        variant = by[p["answer_id"], p["condition"]]["selected"]
        for metric in ["sr", "sp"]:
            delta = variant["score"][metric] - base["score"][metric]
            check("paired delta " + p["answer_id"] + p["condition"] + metric, close(p["delta_" + metric], delta) and close(p["locked_delta_" + metric], delta))
        check("no reference switch " + p["answer_id"] + p["condition"], base["reference_id"] == variant["reference_id"] and not p["reference_switched"])
    fidelity = s.read(HERE / "fidelity_review.json")
    for review in fidelity:
        for finding in review["findings"]:
            for side in ["source", "translation"]:
                if side in finding:
                    span = finding[side]
                    check("source review quote " + review["request_id"] + side + str(span["start"]), s.text(review[side]["path"])[span["start"]:span["end"]] == span["quote"])
        audit = result_by[review["request_id"]]["translation_audit"]
        check("operational numeric and time audit " + review["request_id"], audit["same_numbered_unit_sequence"] and all(u["number_tokens_equal"] and u["time_signatures_equal"] for u in audit["unit_pairs"] if u["unit_id"] != "HEADER"))
    check("seven CJK-free full texts, no expert claims", sum(r["whole_text_has_no_remaining_CJK"] for r in fidelity) == 7 and not any(r["expert_verified"] or r["blind_to_scores"] for r in fidelity))
    with (HERE / "RESULTS_PER_TRANSLATION.csv").open(encoding="utf-8-sig", newline="") as f:
        csvrows = list(csv.DictReader(f))
    check("eight CSV rows", len(csvrows) == 8)
    for row in csvrows:
        check("CSV raw score " + row["request_id"], all(close(float(row[k]), reviewed[row["request_id"]][k]) for k in ["sr", "sp"]))
    mechanism = s.read(HERE / "mechanism_checks/verification.json")
    check("offline mechanism checks passed", mechanism["passed"] and all(c["passed"] for c in mechanism["checks"]) and mechanism["new_generative_requests"] == mechanism["new_local_vectors"] == 0)
    bound(mechanism["ledger_after"])
    bound(mechanism["plan"])
    factorial = s.read(HERE / "mechanism_checks/numbering_wording_factorial.json")
    for row in factorial:
        bound(row["document"])
        check("factorial full text reparsed " + row["condition"], s.core.segment(s.text(row["document"]["path"])) == row["generated_steps"])
    for left, right in [(0, 1), (2, 3), (3, 4)]:
        check("wording isolation " + str((left, right)), [x["text"] for x in factorial[left]["generated_steps"]] == [x["text"] for x in factorial[right]["generated_steps"]] and all(factorial[left]["score"][k] == factorial[right]["score"][k] for k in ["sr", "sp"]))
    hierarchy = s.read(HERE / "mechanism_checks/hierarchy_diagnostic.json")
    check("eight separate heading diagnostics", len(hierarchy) == 8 and all(not r["main_score_replaced"] and r["removed_heading_n"] == (3 if r["answer_id"] == "R3C04" else 0) for r in hierarchy))
    summary = s.read(HERE / "FINAL_SUMMARY.json")
    check("summary scope and request count", summary["started"] == summary["returned"] == summary["schema_valid"] == 8 and summary["new_package_count"] == 446 and summary["new_full_CCE_judgments"] == summary["new_expert_records"] == summary["fresh_repeat_trials"] == 0 and not summary["overall_paper_goal_complete"])
    check("summary token and wall totals", summary["output_tokens_sum"] == sum(t["model_response_metadata"]["eval_count"] for t in execution["terminals"]) and close(summary["generation_wall_seconds_sum"], sum(t["wall_seconds"] for t in execution["terminals"])))
    for doc in [HERE / "RESULTS_zh.md", HERE / "COMMANDS.md", HERE / "README.md"]:
        for target in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                check("local report link " + doc.name + " " + target, (doc.parent / unquote(target.split("#")[0])).exists())
    publish_navigation()
    s.write(HERE / "delivery_verification.json", {
        "passed": True, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]),
        "checks": checks, "check_count": len(checks), "new_generative_requests": 0,
        "limitations": "Provenance and arithmetic verification; not expert scientific validity or fresh holdout evidence.",
        "ledger": s.bind(ledger), "navigation": [s.bind(WORKSPACE / "STATUS.md"), s.bind(DAY / "README.md")]
    })
    manifest = [s.bind(p) for p in sorted(HERE.rglob("*")) if p.is_file() and p.name != "delivery_manifest.json" and "__pycache__" not in p.parts]
    s.write(HERE / "delivery_manifest.json", {"created_utc": datetime.now(timezone.utc).isoformat(), "outputs": manifest, "file_count": len(manifest), "scope": "Completed eight-request batch and local report delivery; excludes this manifest itself."})
    print(json.dumps({"passed": True, "checks": len(checks), "bound_files": len(manifest), "new_generative_requests": 0, "total_requests": 446, "paper_goal_complete": False}))


def publish_navigation():
    marker = "2026-10-12 Qwen 全文翻译 8 次实测完成"
    entries = {
        WORKSPACE / "STATUS.md": marker + "：8/8 正常返回并解析，无重试，全包 446/446。C04/C07 英文基线 SR 分别为 1/3、4/7；C07 改编号重译后 SR=0，离线交叉对照定位到译文措辞跨越 0.7 阈值，非本批 JSON 失败。C04 删除仍为 1/3，三个标题误分步仅影响 SP 分母；另列结构候选未替换主分数。8/8 操作数字和时间检查通过，7/8 全文无中文；来源核查为助手非盲审，非专家认证。本批没有新增完整 CCE、随机重复、专家或湿实验结果，论文总体目标仍未完成。此前下方“8 次待批、438/438”为历史状态。" + "[本批结果及逐例排查](reports/cleareval_20261012/english_fulltext_pilot/qwen_translation_pending/RESULTS_zh.md) · [真实逐答案表](reports/cleareval_20261012/english_fulltext_pilot/qwen_translation_pending/RESULTS_PER_TRANSLATION.csv) · [实际命令](reports/cleareval_20261012/english_fulltext_pilot/qwen_translation_pending/COMMANDS.md)。",
        DAY / "README.md": marker + "：[完整结果与三个排查示例](english_fulltext_pilot/qwen_translation_pending/RESULTS_zh.md) · [真实逐答案表](english_fulltext_pilot/qwen_translation_pending/RESULTS_PER_TRANSLATION.csv) · [实际命令](english_fulltext_pilot/qwen_translation_pending/COMMANDS.md)。全部 JSON 成功，但 C07 改编号重译后 SR 从 4/7 降至 0；已完成措辞与编号交叉隔离、中文标签隔离及标题结构候选核查。原 SR/SP 全部保留。总账 446/446；此前“8 次待批”为历史记录。本批不新增完整 CCE、随机重复或专家结果。"
    }
    backup = HERE / "navigation_before"
    backup.mkdir(exist_ok=True)
    for path, entry in entries.items():
        original = path.read_bytes()
        saved = backup / ("STATUS.md" if path.name == "STATUS.md" else "day_README.md")
        if not saved.exists():
            saved.write_bytes(original)
        text = original.decode("utf-8-sig")
        if marker not in text:
            first, remainder = text.split("\n", 1)
            path.write_text(first.rstrip("\r") + "\n\n" + entry + "\n" + remainder, encoding="utf-8")
        check("latest local navigation " + path.name, marker in path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    main()
