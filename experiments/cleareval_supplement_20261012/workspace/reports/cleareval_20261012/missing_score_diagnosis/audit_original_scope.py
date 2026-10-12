"""Capture original/current scoring scope without editing or running a scorer."""
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path("C:/ClearEval/ClearEval-public")
OUT = Path(__file__).resolve().parent / "original_scope_evidence"
OUT.mkdir(exist_ok=True)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def extract(text, start, end):
    lines = text.splitlines()
    a = next(i for i, line in enumerate(lines) if line.startswith(start))
    b = next(i for i in range(a + 1, len(lines)) if lines[i].startswith(end))
    return {"first_line": a + 1, "last_line": b, "text": "\n".join(lines[a:b])}


prompt_name = "prompts/eval_oeq_teacher_rubric.txt"
head = git("rev-parse", "HEAD").decode().strip()
original = git("show", f"{head}:{prompt_name}")
initial = git("show", f"025f43f:{prompt_name}")
current_path = REPO / prompt_name
current = current_path.read_bytes()
diff = git("diff", "--", prompt_name)
scorer = git("show", f"{head}:OEQ_run_grading_new.py").decode("utf-8")
original_text = original.decode("utf-8")
assert "[UNCERTAINTY CONTRACT]" not in original_text
assert "[UNCERTAINTY CONTRACT]" not in initial.decode("utf-8")
assert "[UNCERTAINTY CONTRACT]" in current.decode("utf-8")
assert "50%" in original_text
assert "兼容或未知均给满分" in scorer
assert 'if not marker_str:' in scorer
(OUT / "original_prompt_HEAD.txt").write_bytes(original)
(OUT / "current_prompt_diff.txt").write_bytes(diff)
table_path = REPO / "KnowledgeBase/method_fluro_compati.json"
table_bytes = table_path.read_bytes()
table = json.loads(table_bytes.decode("utf-8"))
values = {row["method"]: row["Alexa Fluor 594"] for row in table if "Alexa Fluor 594" in row}
assert values["FDISCO"] == 0.85
evidence = {
    "date": "2026-10-12", "purpose": "Correction of label semantics and evaluator responsibilities",
    "git_head": head,
    "original_prompt": {"git_path": f"{head}:{prompt_name}", "sha256": sha(original),
                        "uncertainty_contract": False},
    "initial_prompt": {"git_path": f"025f43f:{prompt_name}", "sha256": sha(initial),
                       "uncertainty_contract": False},
    "current_prompt": {"path": str(current_path), "sha256": sha(current),
                       "uncertainty_contract": True},
    "original_marker_extraction": extract(original_text, "3.1 ", "3.2 "),
    "original_co_param": extract(original_text, "2.3 ", "2.4 "),
    "original_label_scoring": extract(scorer, "    # 2. S_label", "    # Shared lookups"),
    "existing_AF594_method_values": {"path": str(table_path), "sha256": sha(table_bytes), "values": values},
    "primary_sources": [
        {"url": "https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-488-map2-antibody-epr19691-neuronal-marker-ab225316",
         "supports": "An anti-MAP2 primary antibody directly conjugated to AF488 exists."},
        {"url": "https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-594-map2-antibody-epr19691-neuronal-marker-ab302832",
         "supports": "An anti-MAP2 primary antibody directly conjugated to AF594 exists; this is not a clearing-method preservation measurement."},
        {"url": "https://www.thermofisher.com/us/en/home/references/molecular-probes-the-handbook/fluorophores-and-their-amine-reactive-derivatives/alexa-fluor-dyes-spanning-the-visible-and-infrared-spectrum.html",
         "supports": "AF dyes support protein conjugation, while individual members have distinct spectral and fluorescence properties."}
    ],
    "new_model_calls": 0, "scores_recomputed": False, "scorer_modified": False,
}
assert current_path.read_bytes() == current
assert table_path.read_bytes() == table_bytes
(OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"git_head": head, "original_contract_absent": True,
                  "initial_contract_absent": True, "current_contract_present": True,
                  "AF594_method_entries": len(values), "new_model_calls": 0,
                  "scores_recomputed": False}, ensure_ascii=False))
