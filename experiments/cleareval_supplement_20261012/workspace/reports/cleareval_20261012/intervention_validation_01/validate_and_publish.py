"""Check the recorded evidence and update local planning/navigation files."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DAY = HERE.parent
WORKSPACE = Path(r"C:\ClearEval")
sys.path.insert(0, str(DAY / "english_fulltext_pilot/qwen_translation_pending"))
import score_translations as io


def main():
    checks = []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        assert condition, name
    for b in io.read(HERE / "plan.json")["inputs"]:
        check("input unchanged " + b["path"], io.bind(b["path"]) == b)
    inventory = io.read(HERE / "decomposition_inventory.json")
    bridge = io.read(HERE / "operation_bridge_results.json")
    for b in inventory["bindings"] + bridge["bindings"]:
        check("source binding " + b["path"], io.bind(b["path"]) == b)
    summary = io.read(HERE / "SUMMARY.json")
    structure = io.read(HERE / "structure_results.json")
    check("reported canonical equality count", sum(r["same_exact_proposed_request_content"] for r in structure) == summary["equal_canonical_input_pairs"] == 8)
    for row in structure:
        for kind in ["original", "renumber"]:
            prefix = HERE / "structural_views" / (row["answer_id"] + "_" + kind)
            src = io.text(str(prefix) + ".txt")
            text = io.text(str(prefix) + "_view.txt")
            mapping = io.read(str(prefix) + "_mapping.json")
            recovered = text
            for e in sorted(mapping["edits"], key=lambda e: e["view_start"], reverse=True):
                check("actual view edit " + row["answer_id"] + kind + str(e["view_start"]), recovered[e["view_start"]:e["view_end"]] == e["new"])
                recovered = recovered[:e["view_start"]] + e["old"] + recovered[e["view_end"]:]
            check("exact source roundtrip " + row["answer_id"] + kind, recovered == src)
    negative = io.read(HERE / "content_controls.json")
    check("nineteen distinguished content controls", len(negative) == 19 and all(r["distinguished"] for r in negative))
    headings = io.read(HERE / "heading_counterexamples.json")
    check("heading failures retained", sum(not r["passes"] for r in headings) == summary["heading_challenge_failures"] == 4)
    matrix = io.read(HERE / "fixed_matrix_ablations.json")
    check("phase-only failure preserved", all(r["phase_masked_reference_hits"] == 3 and r["phase_masked_one_sentence_capacity"] == 2 for r in matrix if r["answer_id"] == "R3C04"))
    for r in bridge["results"]:
        chosen = r["candidate_selected"]
        check("bridge formula " + r["answer_id"], chosen["sr"] == chosen["reference_hits"]/chosen["reference_n"] and chosen["sp"] == chosen["generated_hits"]/chosen["generated_n"])
        check("bridge counts " + r["answer_id"], r["raw_generated_n"] - len(r["excluded_parser_entries"]) == chosen["generated_n"])
    check("seven reusable conversions without accuracy claim", inventory["directly_available_conversions"] == 7 and inventory["source_bound_resolved_operations"] == 169)
    time = io.read(HERE / "time_relation_checks.json")
    cumulative = next(r for r in time if r.get("ablation"))
    check("original cumulative provenance used", cumulative["initial_duration"] == 48 and cumulative["source_cumulative_hours"] == 72 and cumulative["with_relation_hours"] == 158 and cumulative["keep_initial_only_hours"] == 134 and cumulative["add_initial_and_total_hours"] == 206)
    check("old time scenarios reproduced", sorted(r["recomputed_hours"] for r in time if "recomputed_hours" in r) == [20, 32, 33.5, 72, 158])
    cor = io.read(HERE / "cor_static_checks.json")
    check("Cor lack of behavioral evidence retained", cor["actual_round_requests"] == 0 and len(cor["pairs"]) == 5 and all(r["extra_label_instruction_added"] and r["observed_new_Cor_effect"] is None for r in cor["pairs"]))
    old = io.read(HERE / "revision_01/SUMMARY.json")
    check("initial failure retained", old["equal_canonical_input_pairs"] == 7)
    check("not claimed whole-pipeline efficacy", not summary["whole_pipeline_efficacy_confirmed"] and summary["new_model_requests"] == summary["new_expert_records"] == 0)
    for f in [HERE / "REPORT_zh.md", HERE / "COMMANDS.md"]:
        for target in re.findall(r"\]\(([^)]+)\)", f.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                check("report link " + target, (f.parent / target).exists())
    now = datetime.now(timezone(timedelta(hours=8)))
    stamp = now.strftime("%Y%m%d_%H%M%S")
    update_plan(stamp)
    update_navigation()
    io.write(HERE / "validation.json", {"verified": True, "meaning": "Artifact, arithmetic and source consistency only; scientific negative results remain negative.",
             "checks": checks, "check_count": len(checks), "completed_utc": datetime.now(timezone.utc).isoformat(),
             "command": subprocess.list2cmdline([sys.executable, "-X", "utf8", *sys.argv]), "new_model_requests": 0})
    outputs = [io.bind(p) for p in sorted(HERE.rglob("*")) if p.is_file() and p.name != "delivery_manifest.json" and "__pycache__" not in p.parts]
    io.write(HERE / "delivery_manifest.json", {"outputs": outputs, "file_count": len(outputs), "new_model_requests": 0,
             "current_plan": io.bind(WORKSPACE / "refine-logs/EXPERIMENT_PLAN.md"), "current_tracker": io.bind(WORKSPACE / "refine-logs/EXPERIMENT_TRACKER.md"),
             "navigation": [io.bind(WORKSPACE / "STATUS.md"), io.bind(DAY / "README.md")]})
    print(json.dumps({"evidence_verified": True, "checks": len(checks), "bound_files": len(outputs), "new_model_requests": 0, "whole_pipeline_efficacy_confirmed": False}))


def update_plan(stamp):
    folder = WORKSPACE / "refine-logs"
    marker = "实际有效性核查后的修订"
    for name in ["EXPERIMENT_PLAN", "EXPERIMENT_TRACKER"]:
        path = folder / (name + ".md")
        text = path.read_text(encoding="utf-8")
        if marker in text:
            continue
        first, body = text.split("\n", 1)
        note = "2026-10-12，" + marker + "：8/8 开发文本编号对的提议翻译输入已相同，19/19 内容变化保留；初版 7/8 的失败已存档。旧标题规则在 6 个定向结构例中误删 4 个实际操作，不升级为主规则。7/8 旧转换、169 条来源记录已核对；C04/C07 的 36/19 条记录已与真实译文对接。C04 只加阶段仍删除前后 3/9，句级容量也不足；优先接入现有事实做对象/实例匹配。旧 Cor 提示有标签说明混杂且实际 0 次，重做独立因素设计后才运行。[完整证据](../reports/cleareval_20261012/intervention_validation_01/REPORT_zh.md)。新增生成调用 0，仍 446/446；以下未注明完成的实验仍待执行。"
        updated = first + "\n\n" + note + "\n" + body
        if name == "EXPERIMENT_TRACKER":
            changes = {
                "R01": ("限定范围开发离线验证完成", "8/8 输入相同，初版 7/8 已留档；尚无新翻译返回"),
                "R02": ("19 内容反例和 8 结构例完成", "内容变化未抹去；构造反例不作自然数据准确率"),
                "R03": ("旧规则挑战失败，暂不升级主配置", "6 例中 4 例误删实际操作；改用已有操作身份核对"),
                "R04": ("已有分解核对和两份译文对接完成", "7/8 转换共 169 条记录；C04/C07 对接 36/19 条；不是专家金标"),
                "R07": ("阶段/句级容量消融完成，核心覆盖仍待实现", "阶段限制仍 3/9；句级一对一漏掉低相似度的真实操作"),
                "R08": ("旧时间来源与五个分支复核完成", "累计原始值应沿 original_duration_ref 读取；不计新增提取"),
                "R09": ("5 对提示静态核对完成", "旧两条件同时增加标签说明，不能独立归因于 Cor 职责"),
            }
            lines = []
            for line in updated.splitlines():
                if line.startswith("| R"):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if cells[0] in changes:
                        cells[6], cells[7] = changes[cells[0]]
                        line = "| " + " | ".join(cells) + " |"
                lines.append(line)
            updated = "\n".join(lines) + "\n"
            updated = updated.replace("首先启动的三个工作单元为 R01、R02、R04，均先复用本地数据、无需新增生成调用。R09 的 prompt 核对可同步推进，但本计划不启动并行代理或新模型请求。", "R01、R02 的开发对照、R04 的旧记录复用和 R09 静态核对已实际完成。下一项是 R07 的对象/实例匹配验证，并重新冻结 R10 的独立因素矩阵；本轮没有新模型请求。")
        version = folder / (name + "_" + stamp + ".md")
        version.write_text(updated, encoding="utf-8")
        path.write_bytes(version.read_bytes())


def update_navigation():
    marker = "2026-10-12 改进措施实际核查"
    for path, link in [(WORKSPACE / "STATUS.md", "reports/cleareval_20261012/intervention_validation_01/REPORT_zh.md"), (DAY / "README.md", "intervention_validation_01/REPORT_zh.md")]:
        original = path.read_bytes()
        text = original.decode("utf-8-sig")
        if marker in text:
            continue
        backup = HERE / "navigation_before"
        backup.mkdir(exist_ok=True)
        (backup / ("STATUS.md" if path.name == "STATUS.md" else "day_README.md")).write_bytes(original)
        first, body = text.split("\n", 1)
        entry = marker + "：8/8 规范化输入对相同，19/19 内容变化保留；旧标题规则 6 个挑战中 4 个误删。7/8 旧转换共 169 条来源记录可读取，C04/C07 操作清单与真实译文的对接已跑通。仅阶段限制仍使 C04 删除前后均为 3/9；句级一对一不能找回低于阈值的真实操作。Cor 旧提示存在处理混杂且实际 0 次。初版失败和诊断修正已保留，原 SR/SP 与 CCE 不改。新增调用、编码、专家记录均 0，仍 446/446；完整管线有效性尚未确认。[实际结果与证据](" + link + ")。"
        path.write_text(first.rstrip("\r") + "\n\n" + entry + "\n" + body, encoding="utf-8")


if __name__ == "__main__":
    main()
