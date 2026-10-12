"""Read-only independent identity/numerical audit of the three new local batches.

This invokes no model, embedding model, or network transport. Prompt capture
raises before transport. Scientific validity and expert confirmation are outside
this software audit.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import cce_alternative_development as capture
import cce_validation as parsing

BASE = ROOT / "artifacts/cce_validation/judges"
MAXIMA = {"c_param": 3, "co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1,
          "s_method": 2.5, "s_label": 6, "s_trans": 3, "s_time": 3}


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def filehash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def texthash(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def digest(x):
    return texthash(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def close(a, b):
    return a is None and b is None or a is not None and b is not None and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def derive(e):
    scores = e.get("legacy_diagnostics", {}).get("scores", {})
    out = {}
    for block, fields in [("completeness", ["c_param"]), ("correctness", ["co_order", "co_method", "co_param", "co_chem"]),
                          ("effectiveness", ["s_method", "s_label", "s_trans", "s_time"])]:
        for k in fields:
            v = scores.get(block, {}).get(k, {}).get("score")
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (-MAXIMA[k] if k == "s_method" else 0) <= v <= MAXIMA[k]:
                v = None
            out[k] = v
    cor_keys = ["co_order", "co_method", "co_param", "co_chem"]
    out["Cor"] = sum(out[k] / MAXIMA[k] for k in cor_keys) / 4 if all(out[k] is not None for k in cor_keys) else None
    eff_keys = ["s_method", "s_label", "s_trans", "s_time"]
    out["Eff"] = ((out["s_method"] / 2.5 + 1) / 2 + out["s_label"] / 6 + out["s_trans"] / 3 + out["s_time"] / 3) / 4 if all(out[k] is not None for k in eff_keys) else None
    return out


def main():
    ledger = [json.loads(s) for s in (BASE / "request_ledger.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    starts = [x for x in ledger if x.get("event") == "request_started"]
    ledger_index = defaultdict(list)
    for r in starts:
        ledger_index[r["trial_id"]].append(r)
    assert len({r["request_id"] for r in starts}) == len(starts), "Duplicate global request IDs"
    batches, unique_ids, all_trial_checks = [], set(), []
    expected = {"local_controls_supplement_v2": (21, 21, 0, 21),
                "local_stability_supplement_v2": (12, 12, 0, 10),
                "local_alternative_development": (9, 8, 1, 9)}
    cached_prompts = {}
    for name, (n, good, bad, new_count) in expected.items():
        folder = BASE / name
        plan = read(folder / "plan.json")
        cases = {c["case_id"]: c for c in read(folder / "cases.json")["cases"]}
        steps = {s["case_id"]: s for s in read(folder / "step_results.json")}
        contract = read(folder / "preflight.json")["contract"]
        for path, sha in contract["files"].items():
            assert filehash(ROOT / path) == sha, "Current scoring dependency changed: " + path
        for path, sha in plan.get("frozen_files", {}).items():
            assert filehash(folder / path) == sha
        if "case_file_sha256" in plan:
            assert filehash(folder / "cases.json") == plan["case_file_sha256"]
            assert filehash(folder / "references.json") == plan["reference_file_sha256"]
        for source in plan.get("source_files", []):
            assert filehash(source["path"]) == source["sha256"]
        observations_name = "per_observation.json" if name == "local_stability_supplement_v2" else "per_case.json"
        observations = read(folder / observations_name)
        by_trial = {r["trial_id"]: r for r in observations}
        trials = [read(p) for p in (folder / "trials").glob("*.json")]
        assert len(trials) == n and sum(t["status"] == "success" for t in trials) == good and sum(t["status"] == "failed" for t in trials) == bad
        assert len(by_trial) == n and all(not r["formal_eligible"] for r in observations)
        reuse = read(folder / "reuse_manifest.json") if (folder / "reuse_manifest.json").exists() else []
        reused_ids = {r["trial_id"] for r in reuse}
        assert len(reused_ids) == n - new_count
        for r in reuse:
            assert r["successful_exact_reuse"] and r["status"] == "success"
            assert filehash(r["source_trial_path"]) == r["source_trial_sha256"] == filehash(folder / "trials" / (r["trial_id"] + ".json"))
        batch_request_ids = set()
        for t in trials:
            c, r = cases[t["case_id"]], by_trial[t["trial_id"]]
            inp = digest({"question": c["specific_question"], "question_id": c["question_id"], "protocol": c["model_response"], "references": c["references"]})
            assert t["full_text_input_sha256"] == inp and t["references_sha256"] == digest(c["references"])
            assert c["answer_sha256"] == texthash(c["model_response"]) and c["question_sha256"] == texthash(c["specific_question"])
            assert all(c["question_id"] in ref["question_ids"] for ref in c["references"])
            if name != "local_alternative_development":
                assert len(c["references"]) == 1 and c["references"][0]["route_id"] == "FDISCO"
            one_model = next(m for m in contract["models"] if m["name"] == t["judge"])
            one_contract_sha = digest({**contract, "models": [one_model]})
            identity = {"case_id": c["case_id"], "input_sha256": inp, "judge": t["judge"], "repeat_index": t["repeat_index"], "contract_sha256": one_contract_sha}
            assert t["identity"] == identity and t["trial_id"] == digest(identity)
            assert t["pipeline_config_sha256"] == digest({**contract, "models": []})
            assert t["attempt"] == 1 and len(ledger_index[t["trial_id"]]) == 1
            attempt = folder / "attempts" / f"{t['trial_id']}_1"
            receipt = read(attempt / "request_receipt.json")
            assert receipt == ledger_index[t["trial_id"]][0]
            assert receipt["request_id"] == digest({"trial_id": t["trial_id"], "attempt": 1})
            batch_request_ids.add(receipt["request_id"])
            unique_ids.add(t["trial_id"])
            assert filehash(attempt / "prompt.txt") == t["prompt_sha256"]
            prompt = (attempt / "prompt.txt").read_text(encoding="utf-8")
            if inp not in cached_prompts:
                cached_prompts[inp] = capture.exact_runner_prompt(c)
            assert prompt == cached_prompts[inp]
            context = read(attempt / "context_check.json")
            public = one_model["settings"]
            bound = len(prompt.encode("utf-8")) + public["max_output_tokens"] + 256
            assert context["conservative_context_bound"] == bound <= public["num_ctx"]
            assert context["max_output_tokens"] == public["max_output_tokens"]
            assert read(attempt / "result.json") == t
            provider = read(attempt / "provider_response.json")
            assert provider["done"] and provider["done_reason"] == "stop" and provider["eval_count"] < public["max_output_tokens"]
            payload = json.loads(provider["response"])
            e = t["evaluation"]
            values = derive(e)
            assert all(close(t["preserved_numeric_proposals"][k], v) for k, v in values.items())
            if t["status"] == "success":
                assert payload["scores"] == e["legacy_diagnostics"]["raw_teacher_scores"]
                assert json.loads(e["teacher_generation"]["content"]) == payload
                assert payload["extraction"] == e["extraction"]
                for block in ["completeness", "correctness"]:
                    for item, val in payload["scores"][block].items():
                        if isinstance(val, dict) and "score" in val:
                            assert val["score"] == e["legacy_diagnostics"]["scores"][block][item]["score"]
                assert e["official_scores"] is None and e["cce_eligible"] is False
            else:
                assert name == "local_alternative_development" and c["case_id"] == "openai_deepseek-chat__q22__alternative_development"
                assert "co_chem" not in payload["scores"]["correctness"] and "co_chemical" in payload["scores"]["correctness"]
                assert "correctness.co_chem" in e["_error"] and all(v is None for v in values.values())
                assert not r["technical_pipeline_complete"]
                assert r["partial_diagnostic_numeric"]["c_param"] == payload["scores"]["completeness"]["c_param"]["score"]
                assert all(r["partial_diagnostic_numeric"][k] is None for k in ["co_chem", "Cor", "Eff", "IA", "HV"])
                partial_rows = [x for x in read(folder / "partial_return_fields.json") if x["case_id"] == c["case_id"]]
                alias_row = next(x for x in partial_rows if x["field"] == "co_chemical")
                assert alias_row["contract_key_recognized"] is False and alias_row["not_substituted_into_trial"] is True
                assert next(x for x in partial_rows if x["field"] == "co_chem")["raw_value"] is None
            s = steps[c["case_id"]]["step_result"]
            assert parsing.segment(c["model_response"]) == s["generated_steps"]
            assert s["reference_id"] in {ref["reference_id"] for ref in c["references"]}
            assert s["generated_truncated"] == 0 and s["reference_truncated"] == 0
            assert all(m["matched"] == (m["similarity"] >= .7) for m in s["matches"])
            assert close(s["sr"], sum(m["matched"] for m in s["matches"]) / s["reference_n"])
            assert close(s["sp"], sum(v >= .7 for v in s["generated_max_similarity"]) / s["generated_n"])
            nums = r["candidate_raw_and_derived"]
            for key, val in values.items():
                assert close(nums[key], val)
            assert close(nums["sr"], s["sr"]) and close(nums["sp"], s["sp"])
            com = .4 * s["sr"] + .6 * values["c_param"] / 3 if s["sr"] is not None and values["c_param"] is not None else None
            dims = [com, values["Cor"], values["Eff"]]
            assert close(nums["Com"], com)
            assert close(nums["IA"], min(dims) if all(v is not None for v in dims) else None)
            assert close(nums["HV"], math.prod(dims) if all(v is not None for v in dims) else None)
            assert r["official_scores"] is None and all(v is None for v in r["formal_scores"].values())
            all_trial_checks.append({"batch": name, "trial_id": t["trial_id"], "case_id": c["case_id"], "judge": t["judge"],
                                     "repeat_index": t["repeat_index"], "status": t["status"], "exact_reused": t["trial_id"] in reused_ids,
                                     "request_id": receipt["request_id"], "input_sha256": inp, "references_sha256": digest(c["references"]),
                                     "judge_contract_sha256": one_contract_sha, "actual_prompt_text_sha256": texthash(prompt),
                                     "provider_response_sha256": filehash(attempt / "provider_response.json"), "checks_passed": True})
        assert len(batch_request_ids) == n
        if name != "local_stability_supplement_v2":
            paired = read(folder / "paired_results.json")
            by_case = {r["case_id"]: r for r in observations}
            assert len(paired) == (15 if name == "local_controls_supplement_v2" else 6)
            assert sum(p["technical_pipeline_complete"] for p in paired) == (15 if name == "local_controls_supplement_v2" else 5)
            for p in paired:
                variant_key = "variant_case_id" if "variant_case_id" in p else "alternative_case_id"
                a, z = by_case[p["baseline_case_id"]], by_case[p[variant_key]]
                assert all(a[k] == z[k] for k in ["references_sha256", "question_sha256", "judge_config_sha256", "step_config_sha256"])
                for metric in capture.METRICS:
                    av, zv = a["candidate_raw_and_derived"][metric], z["candidate_raw_and_derived"][metric]
                    delta = zv - av if p["technical_pipeline_complete"] and av is not None and zv is not None else None
                    assert close(p["delta_" + metric], delta)
        batches.append({"batch": name, "observations": n, "technical_successes": good, "technical_failures": bad,
                        "new_requests": new_count, "exact_reused_observations": len(reused_ids), "all_checks_passed": True,
                        "formal_eligible": False, "summary_file_sha256": filehash(folder / "development_summary.json")})
    assert len(unique_ids) == 40, "Expected 21 controls + 10 new stability + 9 alternatives; reused controls counted once"
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "all_passed": True,
              "scope": "Independent software identity/numerical audit only; no expert or scientific validity confirmation",
              "model_requests_made_by_verifier": 0, "verified_observation_records": len(all_trial_checks),
              "unique_real_requests_verified": len(unique_ids), "exact_reused_records": 2,
              "global_ledger_requests_at_verification": len(starts), "batches": batches,
              "alternative_failed_schema_preserved_without_alias_repair": True,
              "original_Cor_Eff_and_CCE_formulas_preserved": True, "formal_and_official_NA_preserved": True,
              "trial_checks": all_trial_checks, "verifier_script_sha256": filehash(__file__)}
    (BASE / "local_v2_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BASE / "local_v2_verification.md").write_text(
        "# Independent local-v2 software verification\n\nAll checks passed. No model or embedding requests were made.\n\n"
        "- E2 v2: 21 real successes, 15 complete provisional pairs.\n"
        "- E4 v2: 12 real observations, including exactly 2 reused control observations and 10 new requests.\n"
        "- Alternative development: 8 successes and 1 unrepaired missing-co_chem schema failure; 5/6 complete provisional pairs.\n"
        "- 42 observation records map to 40 distinct real request IDs, each appearing exactly once in the global ledger.\n"
        "- Full answer/question/reference inputs, frozen contract dependencies, actual full prompts, context/output bounds, raw provider scores, original Cor/Eff formulas, CCE derivations, pair deltas, and NA preservation were checked.\n"
        "- Current parser was reapplied to each distinct full answer without embeddings; stored step segmentation and matching-count SR agreed.\n\n"
        "Formal eligibility remains zero. The audit does not validate scientific applicability or extraction fidelity; the retained Llama example-copy failures remain failures.\n\n"
        "Actual command (completed with exit code 0):\n\n```powershell\n"
        "& 'C:\\ClearEval\\review_artifacts\\bioprobench_2026-09-29\\python_portable\\python.exe' scripts/cce_verify_local_v2.py\n```\n",
        encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["all_passed", "verified_observation_records", "unique_real_requests_verified", "exact_reused_records", "global_ledger_requests_at_verification", "model_requests_made_by_verifier"]}))


if __name__ == "__main__":
    main()
