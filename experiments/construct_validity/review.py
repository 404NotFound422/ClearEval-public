"""Offline blind packages and immutable rating import. Never sends invitations."""
from copy import deepcopy
import json
from pathlib import Path
import random

from .contract import STATES, anchors, digest, read, save, validate_extraction
from .fidelity import SCHEMA as EXTRACTION_SCHEMA
from .local_runner import verify_manifest


def export_review(study, destination):
    study, destination = Path(study), Path(destination)
    manifest = verify_manifest(study)
    materials, jobs = read(study/"materials.json"), read(study/"jobs.json")
    cases, private, missing = [], {}, []
    for key, item in materials.items():
        if key.startswith("GEN"):
            continue
        protocol = item.get("protocol")
        if protocol is None:
            folder = study/"attempts"/item["generation_job"]/"a01"
            if not (folder/"result.json").exists() or read(folder/"result.json")["status"] != "COMPLETE":
                missing.append(key)
                continue
            protocol = (folder/"content.txt").read_text(encoding="utf-8")
            if digest(protocol) != read(folder/"result.json").get("content_sha256"):
                raise ValueError("Review protocol differs from completed generation")
        rid = "R"+digest({"study":manifest["manifest_sha256"],"material":key})[:12]
        identity = {"protocol_sha256":digest(protocol), "task_sha256":digest(item["question"]),
                    "requirements_sha256":digest(item["requirements"]), "evidence_sha256":digest(item["cards"]),
                    "formula_sha256":digest(item.get("formula")), "contract_version":manifest["version"]}
        cases.append({"review_id":rid,"case_identity":identity,"question":item["question"],"protocol":protocol,
                      "requirements":[{k:r.get(k) for k in ("id","text","kind","necessary","scope","route_id","applicability","protocol_fields")} for r in item["requirements"]],
                      "sources":[{k:c.get(k) for k in ("id","source","url","locator","schema_version","identity","source_document","passages","applicability","scope_support")} for c in item["cards"]]})
        private[rid] = {"material_id":key,"root_task_id":item["root_task_id"],"kind":item["kind"],
                        "protocol_sha256":digest(protocol)}
    random.Random(20260929).shuffle(cases)
    public = {"version":"cv-blind-grounding-v2","cases":cases,
              "instructions":"只按原文与可核验来源独立初评；可质疑暂定要求，不查看自动评分或其他评阅者标签。具体条件未报告不等于科学上必然失败。来源目录供查阅，不是标准答案。"}
    public["package_sha256"] = digest(public)
    save(destination/"public/cases.json",public)
    save(destination/"private/mapping.json",private)
    template = {"package_sha256":public["package_sha256"], "schema_version":"scientific-review-v2",
        "reviewer":{"id":None,"expertise":None,"years_experience":None,"method_familiarity":None,
                    "participated_in_task_design":None,"saw_automatic_judgments":None,"saw_other_raters":None},
        "rating_type":"INDEPENDENT_FIRST_PASS",
        "ratings":[{"review_id":c["review_id"],"case_identity":c["case_identity"],"requirement_id":r["id"],"status":None,
                    "reason":None,"protocol_quotes":[],"evidence_urls":[],"requirement_dispute":None}
                   for c in cases for r in c["requirements"]]}
    save(destination/"public/ratings_template.json",template)
    save(destination/"public/extraction_reference_template.json", {
        "schema_version":"extraction-reference-v2", "package_sha256":public["package_sha256"],
        "reviewer_id":None, "saw_model_extraction":None,
        "references":[{"review_id":c["review_id"], "case_identity":c["case_identity"],
                       "manual_extraction":None, "reason":None} for c in cases],
        "instructions":"Annotate original protocol facts with extraction-grounding-v2 field spans; no scientific scores. Null templates are not labels."})
    tasks = read(study/"tasks.json")
    save(destination/"task_review/tasks_and_draft_requirements.json",tasks)
    save(destination/"task_review/evidence_cards_for_review.json",read(study/"evidence_cards.json"))
    save(destination/"task_review/decisions_template.json",{
        "reviewer_id":None,"decisions":[{"root_task_id":t["root_task_id"],"requirement_id":r["id"],
            "is_necessary":None,"is_atomic":None,"applicability":None,"supported_alternatives":[],
            "source_urls":[],"decision":None,"reason":None} for t in tasks for r in t["requirements"]]})
    readme = """# 独立审阅交接包

先做 task_review：核对必要性、适用范围、原子性和合理替代路线。暂定要求获修改后须新建数据版本，不能更改本轮已冻结输入。

答案盲评只分发 public 目录，每位评阅者分别填写 ratings_template.json；不要分发 private、自动报告或本轮预设期望。填写 reviewer 背景和是否看过自动/他人判定。建议两位领域评阅者分别初评，分歧另开仲裁记录。这里没有向任何人发送材料。

status 使用 SATISFIED / VIOLATED / UNDER_SPECIFIED / UNRESOLVED。理由与来源必填到可审查程度；明确省略必要细节按当前开发规范记 UNDER_SPECIFIED，如不同意规范请填写 requirement_dispute。不要为匹配机器判断改分。

没有作答的行保持 null，可分批导入。导入程序只核验格式、来源身份和原文引用，不认证评阅者身份或专业资格。自动生成的空模板不是专家标签。

导入：在仓库根运行 python -m experiments.construct_validity review-import --package <本目录> --ratings <填写后的JSON> --out <独立导入目录>。

若已经看过本轮自动结论，应如实标注，记录仍可保存为非盲补充审阅，但不进入独立初评主分析。
"""
    (destination/"README_zh.md").write_text(readme,encoding="utf-8")
    # A readable Markdown packet makes review possible without a dedicated app.
    text = ["# 匿名方案审阅材料\n", public["instructions"]]
    for c in cases:
        text.extend(["\n## "+c["review_id"],c["question"],"\n```text\n"+c["protocol"]+"\n```",
                     "\n"+"\n".join(r["id"]+"："+r["text"] for r in c["requirements"])])
    (destination/"public/cases.md").write_text("\n\n".join(text)+"\n",encoding="utf-8")
    status={"exported_cases":len(cases),"missing_generation_cases":missing,"independent_ratings_received":0,
            "package_sha256":public["package_sha256"]}
    save(destination/"export_status.json",status)
    return status


def import_ratings(package, ratings_path, output):
    package, output = Path(package), Path(output)
    public = read(package/"public/cases.json")
    if digest({k:v for k,v in public.items() if k != "package_sha256"}) != public["package_sha256"]:
        raise ValueError("Public review package changed")
    ratings = read(ratings_path)
    if ratings.get("package_sha256") != public["package_sha256"]:
        raise ValueError("Ratings belong to another package")
    if ratings.get("rating_type") not in {"INDEPENDENT_FIRST_PASS","ADJUDICATION","SUPPLEMENTARY"}:
        raise ValueError("Unknown rating type")
    reviewer = ratings.get("reviewer",{})
    for key in ("id","expertise","method_familiarity"):
        if not isinstance(reviewer.get(key),str) or not reviewer[key].strip():
            raise ValueError("Missing reviewer background: "+key)
    for key in ("participated_in_task_design","saw_automatic_judgments","saw_other_raters"):
        if type(reviewer.get(key)) is not bool:
            raise ValueError("Reviewer disclosure missing: "+key)
    independent = (ratings["rating_type"]=="INDEPENDENT_FIRST_PASS"
                   and not any(reviewer[k] for k in ("participated_in_task_design","saw_automatic_judgments","saw_other_raters")))
    cases = {c["review_id"]:c for c in public["cases"]}
    valid_ids = {(c["review_id"],r["id"]) for c in public["cases"] for r in c["requirements"]}
    seen, accepted = set(), []
    for row in ratings.get("ratings",[]):
        key = (row.get("review_id"),row.get("requirement_id"))
        if key not in valid_ids or key in seen:
            raise ValueError("Unknown or duplicate review target")
        seen.add(key)
        if row.get("status") is None:
            continue
        if public.get("version") == "cv-blind-grounding-v2" and row.get("case_identity") != cases[key[0]]["case_identity"]:
            raise ValueError("Rating task/answer/requirements/evidence versions differ")
        if row["status"] not in STATES or not isinstance(row.get("reason"),str) or not row["reason"].strip():
            raise ValueError("Missing rating or rationale")
        if (not isinstance(row.get("protocol_quotes"),list) or not isinstance(row.get("evidence_urls"),list)
                or any(not isinstance(url,str) or not url.strip() for url in row.get("evidence_urls",[]))):
            raise ValueError("Invalid rating citations")
        for quote in row["protocol_quotes"]:
            anchors(cases[key[0]]["protocol"],quote)
        accepted.append(deepcopy(row))
    if not accepted:
        raise ValueError("Empty template is not a completed review")
    # Same reviewer cannot silently replace prior first-pass labels for same item.
    for path in output.glob("*/ratings.json"):
        previous=read(path)
        if previous["reviewer"]["id"]==reviewer["id"] and previous["rating_type"]==ratings["rating_type"] and previous["package_sha256"]==ratings["package_sha256"]:
            old={(r["review_id"],r["requirement_id"]):r for r in previous["ratings"] if r.get("status") is not None}
            for row in accepted:
                key=(row["review_id"],row["requirement_id"])
                if key in old and old[key]!=row:
                    raise ValueError("Prior rating differs; use a separately identified adjudication record")
    folder=output/digest(ratings)
    save(folder/"ratings.json",ratings)
    status={"accepted":len(accepted),"unrated":len(valid_ids)-len(accepted),
            "independent_by_disclosure":independent,"reviewer_identity_authenticated":False,
            "rating_type":ratings["rating_type"],"source_sha256":digest(ratings)}
    save(folder/"import_status.json",status)
    return status



def import_extraction_references(package, ratings_path, output):
    """Import manual fidelity references only; never compute scientific agreement."""
    package, output = Path(package), Path(output)
    public, form = read(package/"public/cases.json"), read(ratings_path)
    if digest({k:v for k,v in public.items() if k != "package_sha256"}) != public["package_sha256"]:
        raise ValueError("Public review package changed")
    if public.get("version") != "cv-blind-grounding-v2":
        raise ValueError("Legacy review package needs explicit versioned re-export before fidelity references")
    if form.get("schema_version") != "extraction-reference-v2" or form.get("package_sha256") != public["package_sha256"]:
        raise ValueError("Extraction references belong to another schema/package")
    reviewer = form.get("reviewer_id")
    if not isinstance(reviewer,str) or not reviewer.strip() or type(form.get("saw_model_extraction")) is not bool:
        raise ValueError("Manual reference author and exposure disclosure required")
    cases = {c["review_id"]:c for c in public["cases"]}
    seen, accepted = set(), []
    for row in form.get("references",[]):
        rid = row.get("review_id")
        if rid not in cases or rid in seen:
            raise ValueError("Unknown or duplicate extraction reference")
        seen.add(rid)
        if row.get("manual_extraction") is None:
            continue
        case = cases[rid]
        if row.get("case_identity") != case.get("case_identity"):
            raise ValueError("Extraction reference answer/task/evidence version mismatch")
        if not isinstance(row.get("reason"),str) or not row["reason"].strip():
            raise ValueError("Reference annotation rationale required")
        audit = validate_extraction(row["manual_extraction"],case["protocol"])
        if row["manual_extraction"].get("schema_version") != EXTRACTION_SCHEMA or not audit["scoring_eligible"]:
            raise ValueError("Manual reference must contain grounded, non-inferred original fields")
        accepted.append({"review_id":rid, "case_identity":deepcopy(row["case_identity"]), "audit":audit})
    if not accepted:
        raise ValueError("Empty manual reference template is not a completed annotation")
    for path in output.glob("*/references.json"):
        previous = read(path)
        if previous.get("reviewer_id") == reviewer and previous.get("package_sha256") == form["package_sha256"]:
            old = {r["review_id"]:r for r in previous["references"] if r.get("manual_extraction") is not None}
            for row in form["references"]:
                if row.get("manual_extraction") is not None and row["review_id"] in old and row != old[row["review_id"]]:
                    raise ValueError("Prior manual reference differs; use a new explicitly identified revision")
    folder = output/digest(form)
    save(folder/"references.json",form)
    save(folder/"grounding_audits.json",accepted)
    status = {"accepted":len(accepted),"source_sha256":digest(form),"reviewer_identity_authenticated":False,
              "independent_by_disclosure":not form["saw_model_extraction"],
              "scientific_labels":0,"scientific_agreement_computed":False}
    save(folder/"import_status.json",status)
    return status
