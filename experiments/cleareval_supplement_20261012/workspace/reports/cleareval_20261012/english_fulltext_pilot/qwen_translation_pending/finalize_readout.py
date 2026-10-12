"""Attach explicit author source-review judgments to raw translation observations.

Reviewer is the current assistant. These are not expert returns or new model calls.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE))
import score_translations as s
import cce_representation_repair_v3 as existing_normalizer

def span(value,quote):
    start=value.index(quote)
    return {"start":start,"end":start+len(quote),"quote":quote}

def main():
    results=s.read(HERE/"scoring/results.json")
    execution=s.read(HERE/"execution_summary.json")
    assert len(results)==len(execution["terminals"])==8
    reviews=[];readout=[];reuse=[]
    for r in results:
        aid=r["answer_id"];a=r["translation_audit"]
        source=s.text(r["source"]["path"]);english=s.text(r["translation"]["path"])
        assert a["same_numbered_unit_sequence"]
        operational=[p for p in a["unit_pairs"] if "." in p["unit_id"]]
        assert all(p["number_tokens_equal"] and p["time_signatures_equal"] for p in operational)
        findings=[]
        if aid=="R3C04":
            assert a["english_only_number_tokens"]=={"3":1} and a["source_only_number_tokens"]=={}
            findings.append({"kind":"number_token_flag_resolved_by_source_review","source":span(source,"三维"),"translation":span(english,"3D"),
                             "judgment":"Semantically intended dimensional descriptor; no new experimental numerical parameter.","material_parameter_change":False})
            # These headings are compressed in all four actual Qwen returns.
            findings.append({"kind":"heading_modifier_compression","source":span(source,"二抗全脑免疫标记"),"translation":span(english,"Secondary, far-red"),
                             "judgment":"Whole-brain immunolabeling modifier is omitted in this heading; the shared specimen context and secondary-antibody operation remain. Not strict verbatim preservation; flag for source review.","main_scoring_repaired":False})
            findings.append({"kind":"heading_modifier_compression","source":span(source,"再次脱水"),"translation":span(english,"Dehydration before clearing"),
                             "judgment":"Explicit again is compressed in the heading. Earlier and later workflow positions remain; translated scientific equivalence has not been expert-adjudicated.","main_scoring_repaired":False})
        if a["CJK_remaining"]:
            assert r["request_id"]=="T06_R3C07_renumber_operations" and a["CJK_remaining"]==4
            findings.append({"kind":"untranslated_selected_label","source":span(source,"内源荧光"),"translation":span(english,"内源荧光"),
                             "judgment":"Incomplete full-English translation. Label is before Protocol Steps and is not encoded by this step scorer. Separate offline intervention demonstrates no effect on this SR/SP drop.",
                             "whole_text_English_complete":False,"local_impact":"label translation only; do not erase observed SR/SP"})
        review={"request_id":r["request_id"],"reviewer":"current_assistant_source_review","expert_verified":False,
                "blind_to_scores":False,"source":r["source"],"translation":r["translation"],
                "scope":"Read complete baseline sources/translations and all variant differences; inspect numeric/time unit alignment, repeats, simultaneous incubations, optional clauses, and retained scientific claims.",
                "numbered_structure_retained":True,"operational_number_and_time_checks_pass":True,
                "whole_text_has_no_remaining_CJK":a["CJK_remaining"]==0,
                "findings":findings,"source_scientific_errors_corrected_by_reviewer":False,
                "operation_content_review":"No material operation, numerical, repeat, or branch alteration identified in this assistant review; this is not an expert accuracy estimate.",
                "display_status":"observed_raw_SRSP_retained_with_local_fidelity_notes",
                "uniform_full_English_experiment_eligible":a["CJK_remaining"]==0,
                "whole_document_semantically_lossless_claimed":False}
        reviews.append(review)
        score=r["selected"]["score"]
        readout.append({"request_id":r["request_id"],"answer_id":aid,"question_id":r["question_id"],"condition":r["condition"],
                        "sr":score["sr"],"sp":score["sp"],"reference_hits":score["reference_hits"],"reference_n":score["reference_n"],
                        "generated_hits":score["generated_hits"],"generated_n":score["generated_n"],
                        "whole_text_has_no_remaining_CJK":a["CJK_remaining"]==0,"operation_numeric_time_check":True,
                        "translation_note":"source three-dimensional to 3D; heading compression" if aid=="R3C04" else ("untranslated pre-protocol label" if a["CJK_remaining"] else "no material operation change identified by assistant"),
                        "reference_id":r["selected"]["reference_id"],"reference_source":r["selected"]["source_path"],"reference_url":r["selected"]["source_url"],
                        "source_path":r["source"]["path"],"translation_path":r["translation"]["path"],"raw_response_path":str(HERE/"returns"/r["request_id"]/"http_response.json"),
                        "new_full_CCE_judgment":False,"expert_verified":False})
        view=existing_normalizer.canonicalize_full_text(source)
        reuse.append({"request_id":r["request_id"],"answer_id":aid,"condition":r["condition"],"source":r["source"],
                      "evaluation_view_sha256":view["evaluation_view_sha256"],"removed_structural_prefix_n":len(view["removed_structural_prefixes"]),
                      "nonformat_content_and_order_exact":view["nonformat_content_and_order_exact"]})
    by={(r["answer_id"],r["condition"]):r for r in reuse}
    reuse_pairs=[{"answer_id":aid,"original_and_renumbered_same_existing_view":by[aid,"baseline"]["evaluation_view_sha256"]==by[aid,"renumber_operations"]["evaluation_view_sha256"]} for aid in ["R3C04","R3C07"]]
    s.write(HERE/"fidelity_review.json",reviews)
    s.write(HERE/"reviewed_readout.json",readout)
    s.csvwrite(HERE/"RESULTS_PER_TRANSLATION.csv",readout)
    s.write(HERE/"existing_normalizer_reuse_check.json",{"implementation":s.bind(Path(existing_normalizer.__file__)),"rows":reuse,"pairs":reuse_pairs,
                                                        "scope":"actual offline reuse check on the eight Chinese input documents; no new model requests",
                                                        "interpretation":"An English action/title grammar cannot be assumed to canonicalize Chinese source numbering. This is a scope limit of the existing candidate, not evidence for dropping arbitrary leading numbers."})
    pairs=s.read(HERE/"scoring/pairs.json")
    reviewed_pairs=[]
    review_by={r["request_id"]:r for r in reviews}
    result_by={(r["answer_id"],r["condition"]):r for r in results}
    for p in pairs:
        base=result_by[p["answer_id"],"baseline"];variant=result_by[p["answer_id"],p["condition"]]
        reviewed_pairs.append({**p,"translation_validity":"assistant_reviewed_with_local_notes_expert_pending",
                               "both_full_texts_have_no_remaining_CJK":all(review_by[x["request_id"]]["whole_text_has_no_remaining_CJK"] for x in [base,variant]),
                               "raw_pair_not_erased":True})
    s.write(HERE/"reviewed_pairs.json",reviewed_pairs)
    summary={"status":"eight_authorized_translation_requests_completed","requested":8,"started":8,"returned":8,"schema_valid":8,
             "normal_stop":sum(t["model_response_metadata"]["done_reason"]=="stop" for t in execution["terminals"]),
             "automatic_retries":0,"generation_wall_seconds_sum":sum(t["wall_seconds"] for t in execution["terminals"]),
             "output_tokens_sum":sum(t["model_response_metadata"]["eval_count"] for t in execution["terminals"]),
             "full_texts_without_remaining_CJK":sum(x["whole_text_has_no_remaining_CJK"] for x in reviews),
             "operational_numeric_time_checks_pass":8,"actual_raw_pairs":6,"pairs_without_remaining_CJK_in_either_fulltext":sum(p["both_full_texts_have_no_remaining_CJK"] for p in reviewed_pairs),
             "new_full_CCE_judgments":0,"new_expert_records":0,"fresh_repeat_trials":0,
             "reference_switches":sum(p["reference_switched"] for p in pairs),"new_package_count":446,
             "main_formula_encoder_threshold_changed":False,"fidelity_source_review":"current assistant, unblinded, not expert or independent validation",
             "baseline_sr_reproduces_author_translation":[x["sr"] for x in readout if x["condition"]=="baseline"],
             "residual_failures":["C04 deleting late core operations leaves SR unchanged",
                                  "C07 renumber then retranslate yields SR 4/7 to 0 through different wording crossing the .7 threshold",
                                  "C04 three section titles are counted as operations by the unchanged parser",
                                  "C07 one label is not fully translated","merged granularity changes SP numerator and denominator"],
             "outputs_are_development_evidence":True,"overall_paper_goal_complete":False}
    s.write(HERE/"FINAL_SUMMARY.json",summary)
    s.write(HERE/"readout_execution.json",{"command":subprocess.list2cmdline([sys.executable,"-X","utf8",*sys.argv]),"finished_utc":datetime.now(timezone.utc).isoformat(),"new_generative_requests":0})
    print(json.dumps({"returned":8,"full_texts_without_remaining_CJK":summary["full_texts_without_remaining_CJK"],"operational_numeric_time_checks_pass":8,
                      "paired_observations":6,"new_package_count":446,"existing_normalizer_pairs":reuse_pairs},ensure_ascii=False))

if __name__=="__main__":main()
