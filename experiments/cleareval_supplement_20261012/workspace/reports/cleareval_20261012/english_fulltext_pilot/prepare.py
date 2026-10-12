"""Prepare traceable full-text English representations from saved translations.

No generative requests. New translations of framing text are author annotations.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(r"C:\ClearEval")
HERE = Path(__file__).resolve().parent
R3 = ROOT / "ClearEval-public/artifacts/cce_validation/optimizer_round3_20261011"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


# Read in complete context; preserve scientific claims and contradictions.
# Keys are zero-based source line indices. These are translations, not corrections.
FRAMING = {
    "R3C04": {
        0: "Line 1 (selected fluorescence/labeling strategy + clearing method): **[NeuN + Alexa Fluor 647 (somata), β-III Tubulin (TUJ1) + Alexa Fluor 647 (axons/dendrites), TO-PRO-3 (whole-brain nuclear staining)] + iDISCO+ (DBE RI matching)**  ",
        1: "Rationale for selection: iDISCO+ is suitable for rapid, highly transparent clearing and light-sheet imaging of an intact adult mouse whole brain (~10×8×6 mm); organic-solvent dehydration/delipidation produces high transparency and good contrast of fiber-tract trajectories. TO-PRO-3 and Alexa Fluor 647 signals are relatively robust in the iDISCO+ workflow, making them suitable for constructing whole-brain three-dimensional morphological maps of neuronal somata and neurites.",
        3: "**Protocol Steps:**",
        5: "1 Pretreatment and dehydration (Dehydration)  ",
        13: "2 Bleaching / heme removal (Bleaching, which can substantially reduce whole-brain background)  ",
        16: "3 Rehydration (Rehydration)  ",
        23: "4 Permeabilization / blocking (Permeabilization & Blocking)  ",
        27: "5 Whole-brain immunolabeling with primary antibodies (Whole-brain immunolabeling, primary)  ",
        31: "6 Washing (Wash after primary)  ",
        35: "7 Whole-brain immunolabeling with secondary antibodies (Secondary, far-red)  ",
        38: "8 Washing (Wash after secondary)  ",
        42: "9 Nuclear staining (TO-PRO-3, whole-brain nuclear localization to assist registration / regional delineation)  ",
        46: "10 Dehydration again (Dehydration before clearing)  ",
        54: "11 Delipidation / pre-clearing treatment (Delipidation with DCM)  ",
        58: "12 RI matching (Refractive index matching, DBE)  ",
        62: "13 Storage and pre-imaging treatment (Storage & pre-imaging)  ",
    },
    "R3C07": {
        1: "**Chosen Labeling:** [tdTomato (endogenous fluorescence), β-III Tubulin (TUJ1) + Alexa Fluor (647)]",
        2: '**Justification:** FDISCO (Fluorescence-preserved 3D Imaging of Solvent-Cleared Organs) is a rapid organic-solvent-based clearing method. Whole-brain clearing can be completed in approximately 2 days, meeting the requirement for "imaging as soon as possible". It preserves fluorescent proteins better than iDISCO+/uDISCO (low temperature and alkaline conditions suppress fluorescence quenching), and published studies have demonstrated good preservation of endogenous tdTomato signals. FDISCO uses THF for dehydration/delipidation followed by BABB as the RI-matching solution (RI≈1.56), is compatible with light-sheet microscopy, and permits some tissue shrinkage (FDISCO shrinkage is approximately 35–40%; uniform shrinkage does not affect projection tracing). Labeling strategy: ① preserve endogenous tdTomato fluorescence to trace long-range projection neurons; ② perform whole-brain immunostaining of the fixed brain before clearing (iDISCO-style whole-mount), using an anti-β-III Tubulin (TUJ1) antibody + Alexa Fluor 647 secondary antibody to label the axonal cytoskeleton. Alexa Fluor 647 has excellent stability in organic solvents. The two channels (tdTomato ~590 nm; AF647 ~647 nm) are well separated spectrally and are suitable for dual-channel light-sheet imaging.',
        8: "**1 Sample pretreatment (Post-fixation wash)**",
        11: "**2 Permeabilization before whole-brain immunostaining**",
        15: "**3 Blocking**",
        18: "**4 Primary antibody incubation (β-III Tubulin / TUJ1)**",
        22: "**5 Secondary antibody incubation (Alexa Fluor 647)**",
        27: "**6 Dehydration (THF gradient dehydration)**",
        34: "**7 Delipidation (BABB pretreatment)**",
        37: "**8 Refractive index matching (RI Matching)**",
        41: "**9 Pre-imaging treatment and storage**",
    },
    "R3C06": {
        1: "**Chosen Labeling:** [GFP (endogenous), MAP2 + Alexa Fluor 488, DAPI]  ",
    },
}

case_file = R3 / "confirmation_qwen_01/cases.json"
translation_file = ROOT / "reports/cleareval_20261012/step_language_probe/translations.json"
cases = read(case_file)["cases"]
translations = read(translation_file)
numbers = lambda text: Counter(re.findall(r"\d+(?:\.\d+)?", text))
checks, records = [], []


def check(name, okay):
    checks.append({"name": name, "passed": bool(okay)})
    if not okay:
        raise AssertionError(name)


for case in cases:
    aid = case["anonymous_answer_id"]
    original = case["model_response"]
    check("source identity:"+aid, sha(original) == case["answer_sha256"])
    local_trans = {x["source"]["text"]: x for x in translations if x["answer_id"] == aid}
    english_lines, alignment = [], []
    original_offset = english_offset = 0
    used = []
    for index, line in enumerate(original.splitlines(keepends=True)):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        new_body = body
        kind = "verbatim"
        # A short repeated operation may be a substring of a longer one.
        # Bind the longest saved source first, then verify every saved index is used.
        for src, tr in sorted(local_trans.items(), key=lambda item: len(item[0]), reverse=True):
            if src in body:
                check(f"unique translation occurrence:{aid}:{index}", body.count(src) == 1)
                new_body = body.replace(src, tr["english_body_original_metadata"], 1)
                kind = "reused_saved_author_step_translation"
                used.append(tr["step_index"])
                break
        metadata_language_changes = []
        if "即刻成像" in new_body:
            new_body = new_body.replace("即刻成像", "image immediately")
            metadata_language_changes.append({"source": "即刻成像", "english": "image immediately",
                                               "origin": "new_author_translation_of_nonnumeric_metadata"})
        if index in FRAMING.get(aid, {}):
            check(f"framing not an operation translation:{aid}:{index}", kind == "verbatim")
            new_body = FRAMING[aid][index]
            kind = "new_author_framing_translation"
        check(f"numbers retained:{aid}:{index}", numbers(body) == numbers(new_body))
        new_line = new_body+ending
        alignment.append({"unit_id": f"L{index+1:04d}", "line_index": index,
                          "source_start": original_offset, "source_end": original_offset+len(line),
                          "english_start": english_offset, "english_end": english_offset+len(new_line),
                          "source": line, "english": new_line, "translation_kind": kind,
                          "metadata_language_changes": metadata_language_changes,
                          "expert_verified": False})
        english_lines.append(new_line)
        original_offset += len(line)
        english_offset += len(new_line)
    english = "".join(english_lines)
    check("all step translations used:"+aid, sorted(used) == sorted(x["step_index"] for x in local_trans.values()))
    check("no untranslated CJK:"+aid, not re.search(r"[\u4e00-\u9fff]", english))
    check("whole document numbers:"+aid, numbers(original) == numbers(english))
    check("whole source reconstructed:"+aid, "".join(x["source"] for x in alignment) == original)
    check("whole English reconstructed:"+aid, "".join(x["english"] for x in alignment) == english)
    folder = HERE / "documents" / aid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "original.txt").write_text(original, encoding="utf-8", newline="")
    (folder / "english_author.txt").write_text(english, encoding="utf-8", newline="")
    (folder / "question.txt").write_text(case["specific_question"], encoding="utf-8", newline="")
    write(folder / "alignment.json", alignment)
    records.append({"answer_id": aid, "case_id": case["case_id"], "question_id": case["question_id"],
                    "generator": case["generator_model"], "original_sha256": sha(original),
                    "english_sha256": sha(english), "original_path": str(folder/"original.txt"),
                    "english_path": str(folder/"english_author.txt"),
                    "alignment_path": str(folder/"alignment.json"),
                    "reused_translated_steps": len(used),
                    "new_author_framing_lines": sum(x["translation_kind"] == "new_author_framing_translation" for x in alignment),
                    "original_cjk_characters": len(re.findall(r"[\u4e00-\u9fff]", original)),
                    "English_is_verbatim": original == english,
                    "historical_exposure_note": "Already exposed in previous development; historical forbid_development_use flag no longer indicates an unexposed holdout.",
                    "translation_is_independent_Qwen_trial": False, "expert_verified": False})

plan = {"created_utc": datetime.now(timezone.utc).isoformat(),
        "study": "fulltext_English_author_reuse_development_pilot",
        "scope": "Full-text route recognition, segmentation and raw SR/SP; no fresh Cor/EGES inference",
        "natural_answers": 8, "tasks": sorted({c["question_id"] for c in cases}),
        "generators": sorted({c["generator_model"] for c in cases}),
        "representations": ["original", "english_author"],
        "threshold": .7, "encoder": "unchanged all-mpnet-base-v2",
        "control_types": ["renumber_operations", "merge_adjacent_operations", "delete_reported_core_operations"],
        "control_bases": ["R3C04", "R3C07"],
        "control_scope": "step-metric diagnostic; not completed full-CCE E2",
        "translation_policy": "Reuse 55 saved translated step bodies; author translates framing and one native-label word; all original scientific choices retained",
        "translation_quality_status": "mechanical checks plus author reading, not expert or independent translator verification",
        "new_generative_requests": 0, "primary_scores_overwritten": False,
        "reference_selection": "Recognize route on each full text; use fixed task/method-compatible complete versions; max SR then same-version SP then fixed order",
        "human_budget": {"experts": 1, "development": 5, "holdout": 15},
        "hypotheses": ["English can change matches while retaining reported choices", "Full-text translation can also change parser output, unlike step-only replacement", "Deletion response and merge invariance must be checked separately from score increases"],
        "new_Qwen_batch": "Prepared separately; not authorized against exhausted historical cap"}
write(HERE/"documents.json", records)
write(HERE/"plan.json", plan)
write(HERE/"preparation_checks.json", {"passed": all(c["passed"] for c in checks), "checks": checks,
                                       "new_model_calls": 0, "not_a_translation_accuracy_estimate": True})
inputs = [case_file, translation_file, Path(__file__), HERE/"plan.json", HERE/"documents.json",
          R3/"confirmation_inputs_01/selected_step_details.json", R3/"confirmation_qwen_01/steps.json",
          ROOT/"ClearEval-public/scripts/cce_validation.py"]
inputs += [Path(row[k]) for row in records for k in ("original_path", "english_path", "alignment_path")]
write(HERE/"frozen_inputs.json", {"inputs": [binding(p) for p in inputs],
                                 "ledger": binding(ROOT/"ClearEval-public/artifacts/cce_validation/judges/request_ledger.jsonl"),
                                 "budget": read(ROOT/"ClearEval-public/artifacts/cce_validation/budget.json"),
                                 "frozen_before_scoring": True})
print(json.dumps({"prepared_answers": len(records), "tasks": plan["tasks"], "generators": plan["generators"],
                  "reused_step_translations": sum(r["reused_translated_steps"] for r in records),
                  "new_framing_lines": sum(r["new_author_framing_lines"] for r in records),
                  "checks": len(checks), "new_model_calls": 0}, ensure_ascii=False))
