"""Add a research-only status entry while retaining exact prior navigation bytes."""
from pathlib import Path
import hashlib
import json

ROOT = Path(r"C:\ClearEval")
HERE = Path(__file__).resolve().parent
backup = HERE / "navigation_before"
backup.mkdir(exist_ok=True)
updates = [
    (ROOT / "STATUS.md", "STATUS.md",
     "2026-10-12 细节技术调研续记：按用户暂停修补、先深入研究的要求，完成 10 个真实失败问题的逐项诊断、26 条核心一手来源核对和最小改造/证伪设计。区分已修复的 MAP2 范围索引、标签通道适用性、仍未验证的操作实例覆盖与 Cor 职责因素。最近似已发表工作为 ICLR 2026 Thoth/SCORE，已明确可借鉴部分与公开评价代码边界。当前交付为研究文档；未实现新评分器、未新增实验或请求、未恢复执行窗口，全包仍 438/438。原 SR/SP 和评分产物未改变，论文总目标仍未完成。[细节主报告](reports/cleareval_20261012/technical_modules_review/CASES_zh.md) · [验证计划](reports/cleareval_20261012/technical_modules_review/VALIDATION_PLAN.md) · [完整研究交付](reports/cleareval_20261012/technical_modules_review/README.md)。"),
    (ROOT / "reports/cleareval_20261012/README.md", "README.md",
     "2026-10-12 细节技术调研：[十个真实失败问题的原因、文献适用性与最小模块](technical_modules_review/CASES_zh.md) · [具体验证计划](technical_modules_review/VALIDATION_PLAN.md) · [最近似工作审计](technical_modules_review/PRIOR_ART_AUDIT.md) · [研究交付导航](technical_modules_review/README.md)。26 条核心来源，逐问题区分工程错误、语义误解与测量定义；新评分和模型请求均为 0。"),
]
records = []
for path, name, entry in updates:
    old = path.read_bytes()
    snapshot = backup / name
    if not snapshot.exists():
        snapshot.write_bytes(old)
    text = old.decode("utf-8-sig")
    if entry not in text:
        head, separator, tail = text.partition("\n")
        newline = "\r\n" if "\r\n" in text else "\n"
        updated = head.rstrip("\r") + newline + newline + entry + newline + tail
        path.write_text(updated, encoding="utf-8", newline="")
    records.append({"path": str(path), "before_sha256": hashlib.sha256(old).hexdigest(),
                    "snapshot": str(snapshot), "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE / "navigation_updates.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"updated_navigation_files": len(records), "new_model_calls": 0}, ensure_ascii=False))
