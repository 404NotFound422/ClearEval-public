"""Create a new auditable demand proposal from task text; never rebind old vectors."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation_contract import DEMAND_AXES, json_hash

VERSION = "explicit-task-demand-migration-v1"
NEUTRAL = dict(zip(DEMAND_AXES, (0.0, 0.0, 0.6, 1.0, 0.0, 0.0)))
# The numeric scale is a transparent, uncalibrated projection, not a published
# scientific truth. It is separate from the exact task requirements below.
TIER_TARGET = {"T01": 0.2, "T02": 0.2, "T03": 0.6, "T04": 0.6,
               "T05": 0.6, "T06": 1.0, "T07": 1.0, "T08": 1.0,
               "T09": 1.0, "T10": 1.0}
NEGATIVE = re.compile(r"不需要|无需|不用|不要求|没有|不含|without|not\s+required|no\s+need", re.I)
RULES = (
    ("fluorescence_protein_preservation",
     r"(?:内源|遗传|报告|转基因)[^。；;\n]{0,45}(?:GFP|YFP|tdTomato|mCherry|荧光)|(?:GFP|YFP|tdTomato|mCherry)[^。；;\n]{0,35}(?:报告|转基因|内源)",
     1.0, 1.0),
    ("dye_permeability", r"深层抗体渗透|抗体穿透|全组织免疫染色|全器官免疫染色|全组织免疫标记", 0.7, 1.0),
    ("geometry_preference", r"定量形态|体积测量|尺寸测量|细胞计数|图谱配准|禁止形变|不允许形变|保持尺寸不变|严格各向同性", 1.0, 1.0),
    ("operational_economy", r"快速筛选|高通量|最少步骤|(?:必须|要求)[^。；;\n]{0,15}(?:一天|两天|24\s*h|48\s*h)", 1.0, 1.0),
    ("safety_compatibility", r"必须无毒|仅限水性|只用水性|不允许有机溶剂|禁止有机溶剂|必须[^。；;\n]{0,12}物镜兼容", 1.0, 1.0),
)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def index_questions(rows):
    if not isinstance(rows, list):
        raise ValueError("Question snapshot must be a list")
    result = {}
    for row in rows:
        qid = str(row["question_id"])
        if qid in result or not isinstance(row["question"], str):
            raise ValueError("Duplicate question or invalid question text")
        result[qid] = row
    return result


def version_audit(before, current):
    old, new = index_questions(before), index_questions(current)
    changed, counts = [], Counter()
    for qid in sorted(old.keys() & new.keys(), key=int):
        fields = sorted(key for key in old[qid].keys() | new[qid].keys()
                        if old[qid].get(key) != new[qid].get(key))
        if fields:
            changed.append({"question_id": new[qid]["question_id"], "fields": fields,
                            "before_sha256": json_hash(old[qid]), "current_sha256": json_hash(new[qid])})
            counts.update(fields)
    return {"before_count": len(old), "current_count": len(new),
            "added_ids": sorted(new.keys() - old.keys(), key=int),
            "removed_ids": sorted(old.keys() - new.keys(), key=int),
            "changed_records": len(changed), "changed_field_counts": dict(counts),
            "changes": changed}


def clauses(text):
    return [(match.start(), match.end(), match.group())
            for match in re.finditer(r"[^。；;\n]+[。；;]?", text)]


def task_span(start, end, text):
    return {"kind": "TASK_TEXT", "field": "question",
            "start": start, "end": end, "quote": text[start:end]}


def derive_question(question):
    text = question["question"]
    # Generic output instructions name antibody incubation for every task.
    # They do not establish that this scenario requires whole-mount antibodies.
    cut = text.find("请仅输出 protocol")
    scenario = text[:cut] if cut >= 0 else text
    vectors = {axis: {"target": NEUTRAL[axis], "weight": 0.0} for axis in DEMAND_AXES}
    axis_audits = {axis: {"status": "NOT_STATED", "evidence": [], "rule": None}
                   for axis in DEMAND_AXES}
    for axis, pattern, target, weight in RULES:
        for start, end, clause in clauses(scenario):
            if not re.search(pattern, clause, re.I):
                continue
            # Conservative: a negated or completed-label clause is retained as
            # a requirement but never silently turned into a positive demand.
            if NEGATIVE.search(clause):
                continue
            if axis == "dye_permeability" and re.search(r"已完成|已经完成|质控合格|无需重复", clause):
                continue
            vectors[axis] = {"target": target, "weight": weight}
            axis_audits[axis] = {"status": "EXPLICIT_TASK_PATTERN",
                                "evidence": [task_span(start, end, text)],
                                "rule": pattern}
            break
    tier = question.get("tissue_hierarchy_from_tissue_xlsx", {}).get("tissue_tier_code")
    code = tier[:3] if isinstance(tier, str) else None
    if code in TIER_TARGET:
        vectors["clearing_challenge"] = {"target": TIER_TARGET[code], "weight": 0.5}
        axis_audits["clearing_challenge"] = {
            "status": "METADATA_WITH_UNCALIBRATED_SCALE",
            "rule": "TIER_TARGET_UNCALIBRATED_V1",
            "evidence": [{"kind": "METADATA", "pointer": "/tissue_hierarchy_from_tissue_xlsx/tissue_tier_code",
                          "raw_value": tier}]}
    requirements = []
    for start, end, clause in clauses(text):
        if re.search(r"必须|不得|禁止|不能|不应|应保留|不允许|无需重复|已完成|质控合格|必要的标记前处理|不能推断|不跨突触|不预设", clause):
            requirements.append({"id": "task-clause-" + str(start), "text": clause,
                                 "basis": "EXPLICIT_TASK_TEXT", "support": task_span(start, end, text),
                                 "scientific_applicability": None})
    completed = [item for item in requirements if re.search(r"已完成|质控合格|无需重复", item["text"])]
    return {"question_id": question["question_id"], "question_sha256": json_hash(question),
            "vector": vectors, "axis_audits": axis_audits, "requirements": requirements,
            "completed_label_clauses": [item["id"] for item in completed],
            "six_axis_coverage": "PARTIAL_TASK_PROJECTION",
            "unrepresented_requirements_retained": True,
            "label_origin": "ASSISTANT_AUTHORED_RULE_MAPPING_FROM_TASK_TEXT",
            "scientific_approval": None}


def validate_derivation(question, proposal):
    """Engineering audit checks original spans and deterministic values, not science."""
    if proposal != derive_question(question):
        raise ValueError("Demand proposal differs from exact current-task derivation")
    return {"engineering_integrity": "VALID", "scientific_approval": None}


def generate_bundle(before_file, current_file, old_vectors_file, old_manifest_file, out_dir):
    out = Path(out_dir)
    if out.exists():
        raise ValueError("Migration output already exists; refusing overwrite")
    before, current = read(before_file), read(current_file)
    old_vectors, old_manifest = read(old_vectors_file), read(old_manifest_file)
    if (old_manifest.get("questions_sha256") != json_hash(before)
            or old_manifest.get("demand_vectors_sha256") != json_hash(old_vectors)
            or old_manifest.get("hash_format") != "canonical-json-sha256-v1"):
        raise ValueError("Previous vectors do not bind the provided before snapshot")
    if set(index_questions(before)) != set(old_vectors):
        raise ValueError("Previous vector IDs do not match before snapshot")
    proposals = [derive_question(question) for question in current]
    for question, proposal in zip(current, proposals):
        validate_derivation(question, proposal)
    vectors = {str(row["question_id"]): row["vector"] for row in proposals}
    audit = version_audit(before, current)
    audit["derived_vector_changes_vs_previous"] = sum(
        old_vectors.get(qid) != vector for qid, vector in vectors.items())
    audit["old_vectors_used_as_derivation_input"] = False
    out.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
    save("requirements_proposals.json", proposals)
    save("demand_vectors.json", vectors)
    save("version_audit.json", audit)
    manifest = {
        "schema_version": VERSION, "hash_format": "canonical-json-sha256-v1",
        "questions_file": str(Path(current_file).resolve()),
        "questions_sha256": json_hash(current),
        "demand_vectors_file": "demand_vectors.json",
        "demand_vectors_sha256": json_hash(vectors),
        "before_questions_sha256": json_hash(before),
        "previous_vectors_sha256": json_hash(old_vectors),
        "requirements_proposals_sha256": file_hash(out / "requirements_proposals.json"),
        "derivation_code_sha256": file_hash(__file__),
        "derivation_method": "FROM_CURRENT_EXPLICIT_TEXT_AND_TIER_METADATA_NOT_OLD_VECTOR_REBIND",
        "engineering_integrity": "VALIDATED_DETERMINISTIC_SPANS_AND_RULES",
        "numeric_scale_status": "UNCALIBRATED_PROJECTION_FOR_REVIEW",
        "review_status": "PENDING_USER_EXPERT",
        "scientific_approval": None,
        "binding_note": "New current-question proposal; no expert calibration claimed. Do not activate silently.",
    }
    save("demand_vectors.json.manifest.json", manifest)
    return {"out": str(out.resolve()), "question_count": len(current),
            "changed_records": audit["changed_records"],
            "new_vectors_different_from_old": audit["derived_vector_changes_vs_previous"],
            "scientific_approval": None, "default_inputs_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "current", "old-vectors", "old-manifest", "out"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    result = generate_bundle(args.before, args.current, args.old_vectors, args.old_manifest, args.out)
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
