"""Create independent source-extracted supplement v2 references; preserve v1 inputs.

Only author-reported post-fixation tissue processing is represented. These are
development coverage references, not expert-confirmed biological necessities.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "artifacts/cce_validation/reference_recovery"
RECOVERED = RECOVERY / "recovered_supplements"
OUT = RECOVERY / "supplement_bound"
V1 = RECOVERY / "references_two_source_development.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def filehash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    primary_paths = [V1, RECOVERY / "references.json", ROOT / "artifacts/cce_validation/pilot_per_answer.json",
                     ROOT / "artifacts/cce_validation/two_source_t070_per_answer.json"]
    protected = {str(path): filehash(path) for path in primary_paths if path.exists()}
    v1 = load(V1)
    old = {reference["route_id"]: reference for reference in v1["references"]}
    assert set(old) == {"FDISCO", "PEGASOS"}
    assert all(len(reference["steps"]) == 7 for reference in old.values())
    recovery = load(RECOVERED / "official_object_recovery_manifest.json")
    objects = {row["label"]: row for row in recovery}
    for row in recovery:
        assert row["status"] == "recovered_verified_original_bytes" and row["indexed_md5_match"]
        assert filehash(Path(row["output_path"])) == row["sha256"]
    pages = load(RECOVERED / "extracted_page_manifest.json")["pages"]
    evidence = {}
    for evidence_id, filename, number in [
        ("FDISCO_TABLE_S1_P12", "aau8355_SM.pdf", 12),
        ("PEGASOS_TABLE_S1_P1", "41422_2018_49_MOESM20_ESM.pdf", 1),
        ("PEGASOS_DATA_S1_P1", "41422_2018_49_MOESM21_ESM.pdf", 1),
        ("PEGASOS_DATA_S1_P2", "41422_2018_49_MOESM21_ESM.pdf", 2),
    ]:
        page = next(row for row in pages if Path(row["pdf"]).name == filename and row["pdf_page_one_based"] == number)
        text_path = Path(page["text_path"])
        assert filehash(text_path) == page["text_sha256"]
        text = text_path.read_text(encoding="utf-8")
        evidence[evidence_id] = {**page, "extracted_text_start": 0, "extracted_text_end": len(text),
                                 "offset_unit": "Unicode code points in UTF-8 decoded extracted text; [start,end)",
                                 "visually_checked_page_render": True}
    # Storage is stated in the main article, not in FDISCO Table S1.
    main_path = RECOVERY / "fdisco_primary_passage.txt"
    main_text = main_path.read_text(encoding="utf-8")
    for evidence_id, first, last, anchor in [
        ("FDISCO_MAIN_CLEARING_P1", "FDISCO clearing consisted", "For bone clearing", "sec[title='FDISCO clearing procedure']/p[1]"),
        ("FDISCO_MAIN_STORAGE_P3", "After FDISCO clearing", "As tissue transparency", "sec[title='FDISCO clearing procedure']/p[3], first sentence"),
    ]:
        start = main_text.index(first)
        end = main_text.index(last, start)
        evidence[evidence_id] = {"source_path": old["FDISCO"]["source_path"],
                                 "source_sha256": filehash(Path(old["FDISCO"]["source_path"])),
                                 "source_anchor": anchor, "extracted_text_path": str(main_path),
                                 "extracted_text_sha256": filehash(main_path), "extracted_text_start": start,
                                 "extracted_text_end": end,
                                 "offset_unit": "Unicode code points in UTF-8 decoded extracted text; [start,end)"}
    save(OUT / "evidence_manifest.json", {"evidence": evidence, "original_objects": recovery,
         "scope": "Source-page evidence, not expert review or wet-lab confirmation"})
    save(OUT / "v1_frozen_references_snapshot.json", v1)

    def step(route, branch, number, text, anchors, module, timing_status):
        return {"step_id": f"{route}-V2-{branch}-{number:02}", "text": text,
                "source_anchor": " + ".join(anchors), "module": module, "required": True,
                "required_scope": "author-reported branch coverage; biological necessity not validated",
                "timing_status": timing_status}

    references = []
    for route in ("FDISCO", "PEGASOS"):
        for branch, qids in (("WHOLE_BRAIN", [2, 248]), ("BLOCK_3MM_UNTIMED", [21, 22, 23])):
            whole = branch == "WHOLE_BRAIN"
            timing = "author_table_whole_brain" if whole else "not_reported_for_3mm_no_interpolation"
            if route == "FDISCO":
                texts = []
                for concentration in (50, 70, 80, 100):
                    duration = " for 12 hours" if whole else ""
                    texts.append(f"Incubate the fixed tissue in {concentration}% (vol/vol) THF in water, adjusted to pH 9.0 with triethylamine, at 4 degrees C{duration} with gentle shaking in the dark.")
                texts.append("Repeat incubation in fresh 100% THF twice more, 12 hours each, for three incubations in total, at 4 degrees C with gentle shaking in the dark." if whole else
                             "Repeat incubation in fresh 100% THF at 4 degrees C with gentle shaking in the dark to complete dehydration.")
                texts.append("Transfer the dehydrated tissue to pure DBE for refractive index matching and clearing at 4 degrees C for 3 hours with gentle shaking in the dark." if whole else
                             "Transfer the dehydrated tissue to pure DBE for refractive index matching and clearing at 4 degrees C with gentle shaking in the dark.")
                texts.append("Store the cleared tissue in DBE in an airtight glass chamber at 4 degrees C in the dark until imaging.")
                steps = [step(route, branch, i + 1, text,
                              ["FDISCO_TABLE_S1_P12", "FDISCO_MAIN_CLEARING_P1"] if i < 6 else ["FDISCO_MAIN_STORAGE_P3"],
                              "dehydration" if i < 5 else "ri_matching" if i == 5 else "storage",
                              timing if i < 6 else "no_fixed_storage_duration") for i, text in enumerate(texts)]
                obj = objects["FDISCO_supplement"]
                anchors = ["FDISCO_TABLE_S1_P12", "FDISCO_MAIN_CLEARING_P1", "FDISCO_MAIN_STORAGE_P3"]
                unresolved = ["The 3 mm block-specific number of 100% THF incubations is unreported; absence of a number is not a missing operation."] if not whole else []
                unresolved += ["Shortened timings in the table note are an author option, not a mandatory extra step.",
                               "Long-storage re-clearing is conditional and is not added to every initial-imaging sequence."]
            else:
                texts = ["Incubate the fixed soft tissue in 25% (weight/volume) Quadrol at 37 degrees C with shaking (approximately 100 rpm) for 2 days, refreshing the medium daily." if whole else
                         "Incubate the fixed soft tissue in 25% (weight/volume) Quadrol at 37 degrees C with shaking (approximately 100 rpm); refresh the medium daily during multi-day treatment."]
                for concentration, hours in ((30, 4), (50, 6), (70, 24)):
                    duration = f" for {hours} hours" if whole else ""
                    texts.append(f"Immerse the tissue in {concentration}% (vol/vol) tert-butanol with 3% (weight/volume) Quadrol at 37 degrees C with shaking (approximately 100 rpm){duration}.")
                texts.append("Transfer the tissue to tB-PEG dehydration solution at 37 degrees C with shaking (approximately 100 rpm) for 2 days, refreshing the medium daily." if whole else
                             "Transfer the tissue to tB-PEG dehydration solution at 37 degrees C with shaking (approximately 100 rpm); refresh the medium daily during multi-day treatment.")
                texts.append("Briefly rinse the tissue with BB-PEG clearing medium before clearing.")
                texts.append("Immerse the tissue in BB-PEG clearing medium at 37 degrees C with shaking (approximately 100 rpm) until transparent; the adult-brain table recommends 1 day." if whole else
                             "Immerse the tissue in BB-PEG clearing medium at 37 degrees C with shaking (approximately 100 rpm) until transparent.")
                texts.append("Preserve the cleared tissue in the clearing medium at room temperature, covered with aluminum foil.")
                modules = ["decolorization", "delipidation", "delipidation", "delipidation", "dehydration", "ri_medium_rinse", "ri_matching", "storage"]
                steps = [step(route, branch, i + 1, text,
                              ["PEGASOS_DATA_S1_P1", "PEGASOS_DATA_S1_P2"] if i < 5 else ["PEGASOS_DATA_S1_P2"],
                              modules[i], timing if i < 5 or i == 6 else "qualitative_duration_only" if i == 5 else "no_fixed_storage_duration") for i, text in enumerate(texts)]
                obj = objects["PEGASOS_Data_S1"]
                anchors = ["PEGASOS_TABLE_S1_P1", "PEGASOS_DATA_S1_P1", "PEGASOS_DATA_S1_P2"]
                unresolved = ["A brief BB-PEG rinse is an explicitly reported tissue action; separating it follows the declared operation-level development granularity, not expert necessity validation.",
                              "Optional ammonium treatment is conditional on heavy coloration/non-perfusion and is not added for these already fixed brain tasks.",
                              "Optional immunolabeling, prior perfusion/fixation, hard-tissue decalcification, and reagent preparation are outside the step scope.",
                              "The reagent-air-exposure tip is not counted as a mandatory tissue operation."]
            reference = {
                "reference_id": f"{route}_SUPPLEMENT_V2_{branch}", "route_id": route,
                "route_aliases": old[route]["route_aliases"], "question_ids": qids,
                "steps": steps, "source_path": obj["output_path"], "source_sha256": obj["sha256"],
                "source_url": "https://doi.org/" + obj["doi"], "supplement_url": obj["source_url"],
                "family_id": old[route]["family_id"], "status": "source_extracted",
                "human_confirmation": None, "formal_eligible": False,
                "source_scope": "author-reported post-fixation procedure coverage, not validated biological necessity",
                "completeness_status": "supplement-bound author-procedure development candidate; expert confirmation pending",
                "evidence_manifest_path": str(OUT / "evidence_manifest.json"), "evidence_ids": anchors,
                "source_pages": [{"evidence_id": a, "pdf_page_one_based": evidence[a].get("pdf_page_one_based"),
                                  "source_anchor": evidence[a].get("source_anchor")} for a in anchors],
                "v1_reference_id": old[route]["reference_id"], "v1_step_count": 7,
                "applicability": {"species": "mouse", "tissue": "fixed adult whole brain" if whole else "fixed brain block, approximately 3 mm",
                    "question_ids": qids, "initial_fixation_complete": True,
                    "source_sample_class_support": "direct adult-brain class in author table" if whole else "general fixed brain/soft-tissue procedure; exact 3 mm applicability pending",
                    "exact_3mm_schedule_supported": False if not whole else None,
                    "timing_policy": timing, "unknown_timing_is_not_a_missing_step": True,
                    "endpoint_scope": "clearing/RI matching/storage only; labeling preparation excluded",
                    "outcomes_pending": ["task-specific chosen labels", "weak sparse signal retention", "long-term reimaging", "six-month preservation", "morphology/distortion targets"],
                    "remaining_review": unresolved + ["No direct 3 mm timing interpolation from 1 mm FDISCO or 1-2 mm PEGASOS slice schedules.",
                                                      "Expert granularity/applicability confirmation remains pending."]},
                "unknown_parameters": ["3mm-specific dwell times"] + (["3mm-specific repeat count"] if route == "FDISCO" else []) if not whole else [],
                "frozen": True, "freeze_scope": "independent supplement-derived v2 development candidate; preserve v1 historical scores",
            }
            references.append(reference)
    for route in old:
        groups = [set(reference["question_ids"]) for reference in references if reference["route_id"] == route]
        assert not (groups[0] & groups[1])
        assert set.union(*groups) == {2, 21, 22, 23, 248}
    for question in (2, 21, 22, 23, 248):
        assert len([reference for reference in references if question in reference["question_ids"]]) == 2
    bundle = {"schema_version": "source-extracted-supplement-v2", "references": references,
              "source_family_n": 2, "route_n": 2, "reference_branch_n": 4,
              "expert_confirmed_n": 0, "new_model_calls": 0, "formal_eligible": False,
              "original_v1_reference_path": str(V1), "original_v1_reference_sha256": protected[str(V1)],
              "evidence_manifest_path": str(OUT / "evidence_manifest.json"),
              "granularity_rule": "One separately stated tissue action per item; staged concentrations keep existing separate entries; repeated-incubation action keeps existing aggregate repeat item; frequency/temperature/light conditions attach to the associated action.",
              "unknown_parameter_rule": "No exact 3mm duration or repeat number is inferred, interpolated, or treated as missing; source author-program coverage remains provisional."}
    save(OUT / "references_supplement_v2.json", bundle)
    for question in (2, 21, 22, 23, 248):
        save(OUT / f"question_{question}_references.json", {**bundle, "references": [reference for reference in references if question in reference["question_ids"]]})

    differences = [
        ("FDISCO", "01-06", "FDISCO_TABLE_S1_P12", "whole-brain parameters", "V1 intentionally omitted tissue-specific dwell times.", "Author table directly identifies the mouse brain/CNS/embryo schedule and three total 100% THF incubations.", "Whole-brain v2 adds table parameters; repeated incubation remains one aggregate repeat operation.", "q2,q248"),
        ("FDISCO", "01-06", "FDISCO_TABLE_S1_P12", "unresolved block scale", "V1 used a shared fixed-brain candidate.", "Separate 1 mm mouse slice and whole-brain columns do not specify a 3 mm block schedule.", "Block v2 carries no exact dwell time or repeat number; absence is not a missing action.", "q21,q22,q23"),
        ("FDISCO", "all clearing", "FDISCO_TABLE_S1_P12", "reagent/condition clarification", "V1 includes cold THF treatment and pH adjustment.", "Table footnote confirms all clearing stages are cold; pH adjustment belongs to THF and not DBE.", "Keep pH binding to THF only; no new operation.", "all scoped questions"),
        ("FDISCO", "07", "FDISCO_MAIN_STORAGE_P3", "source attribution", "V1 storage is supported by main text.", "Table S1 does not include storage.", "Preserve storage with explicit main-text anchor; do not misattribute it to the supplement.", "all scoped questions"),
        ("FDISCO", "conditional", "FDISCO_TABLE_S1_P12", "optional timing", "V1 does not impose a half-time variant.", "Author footnote permits shorter timing rather than requiring an additional action.", "Do not make the optional shortened condition a new mandatory reference step.", "all scoped questions"),
        ("PEGASOS", "01-05,06", "PEGASOS_DATA_S1_P2", "scale-specific schedules", "V1 has a shared soft-tissue schedule and at least one day for clearing.", "Supplement distinguishes adult brain from 1-2 mm brain slices, with a shorter slice clearing recommendation.", "Whole-brain v2 uses adult-brain values; do not universalize the V1 lower bound to slices or infer 3 mm times.", "whole-brain q2/q248; 3mm q21/q22/q23 pending"),
        ("PEGASOS", "01", "PEGASOS_DATA_S1_P1 + PEGASOS_DATA_S1_P2", "bound condition", "V1 decolorization omits replacement and shaking details.", "Data S1 reports shaking and daily medium refresh during decolorization.", "Attach stated conditions/frequency to the operation; do not add a detached parameter step.", "all scoped questions; exact 3mm time unknown"),
        ("PEGASOS", "05", "PEGASOS_DATA_S1_P1 + PEGASOS_DATA_S1_P2", "bound condition", "V1 dehydration lacks complete temperature/shaking/refresh specification.", "Data S1 binds dehydration to the warm shaker; adult-brain table includes daily medium refresh.", "Bind conditions and multi-day refresh to dehydration; retain unknown 3mm dwell time.", "all scoped questions; exact 3mm time unknown"),
        ("PEGASOS", "before old06", "PEGASOS_DATA_S1_P2", "new explicit tissue action", "V1 transfers directly into clearing medium.", "Procedure 7 expressly reports a brief clearing-medium rinse before immersion.", "V2 separates this rinse as a new operation under the declared granularity rule: 7 to 8 steps, author coverage only.", "all scoped development branches"),
        ("PEGASOS", "old06/new07", "PEGASOS_DATA_S1_P2", "bound condition and endpoint", "V1 states transfer and transparency endpoint.", "Data S1 binds immersion to warm shaking until transparent; adult-brain and slice timing are recommendations.", "Attach stated conditions; keep transparency as the reported qualitative endpoint without adding performance thresholds.", "all scoped questions; exact 3mm time unknown"),
        ("PEGASOS", "old07/new08", "PEGASOS_DATA_S1_P2", "storage condition", "V1 records room-temperature storage only.", "Storage is in clearing medium covered by aluminum foil; long term is not assigned a number of months.", "Add the reported light-protection condition; do not infer six-month efficacy or expiry.", "all scoped questions"),
        ("PEGASOS", "excluded", "PEGASOS_DATA_S1_P1", "scope boundary", "Current tasks begin after fixation and exclude label preparation.", "Supplement includes prior perfusion/fixation, hard-tissue-only decalcification, and optional labeling/conditional decolorization.", "Do not count already-completed or irrelevant/conditional branches as universal required steps.", "all scoped questions"),
        ("PEGASOS", "materials", "PEGASOS_DATA_S1_P1", "catalog identity", "Main text has a separately recorded author correction.", "Data S1 materials list directly confirms PEG-MMA500 catalog 447943.", "Source metadata confirmation; not a new tissue-processing step.", "all scoped questions"),
        ("PEGASOS", "reagent tip", "PEGASOS_DATA_S1_P2", "optional reagent condition", "V1 has no reagent-exposure operation.", "Procedure 7 contains an author observation about clearing-medium exposure before use.", "Do not convert this reagent tip into a universally required tissue step.", "all scoped questions"),
        ("both", "applicability", "FDISCO_TABLE_S1_P12 + PEGASOS_DATA_S1_P2", "remaining scientific limits", "V1 expert/applicability confirmation is pending.", "Recovered schedules identify source sample classes, not all requested labeling, morphology or long-storage outcomes.", "Attachment-access gap is resolved; 3 mm schedule, task outcomes and expert necessity/granularity confirmation remain pending.", "all scoped questions"),
    ]
    rows = [dict(zip(("route", "affected_v1_steps", "evidence_id", "difference_type", "v1_state", "new_source_evidence", "v2_handling", "task_scope"), row)) for row in differences]
    save(RECOVERED / "supplement_source_differences.json", {"compared_v1_path": str(V1), "compared_v1_sha256": protected[str(V1)],
         "expert_confirmation": None, "formal_eligible": False, "attachment_availability_gap_resolved": True,
         "reference_scientific_applicability_gap_resolved": False, "differences": rows})
    write_csv(RECOVERED / "supplement_source_differences.csv", rows)
    save(OUT / "construction_run.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
         "command": subprocess.list2cmdline([sys.executable, *sys.argv]), "script_sha256": filehash(Path(__file__)),
         "protected_v1_inputs_before": protected, "protected_v1_inputs_unchanged": all(filehash(Path(path)) == sha for path, sha in protected.items()),
         "new_model_calls": 0, "expert_labels_added": 0, "expert_minutes": None,
         "reference_branches": [{"reference_id": ref["reference_id"], "question_ids": ref["question_ids"], "step_n": len(ref["steps"])} for ref in references],
         "question_reference_count": {str(q): sum(q in ref["question_ids"] for ref in references) for q in (2, 21, 22, 23, 248)},
         "output_manifest_sha256": filehash(OUT / "references_supplement_v2.json"), "formal_eligible": False})
    assert all(filehash(Path(path)) == sha for path, sha in protected.items())
    print(json.dumps({"ready": str(OUT / "references_supplement_v2.json"),
                      "branches": len(references), "step_counts": [len(ref["steps"]) for ref in references],
                      "v1_inputs_unchanged": True, "new_model_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
