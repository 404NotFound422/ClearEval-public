"""Reproduce literature cards from the pinned, reviewed evidence release.

This is a lossless field rendering, not a new scientific adjudication. The
source archive and per-study composition notes must accompany the cards.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

SOURCE_COMMIT = "5e3a711befb3952a2e39f4d53fc9c9f1a7ac0d22"
SOURCE_PREFIX = "KnowledgeBase/evidence_expansion_20261019"
SOURCE_URL = f"https://github.com/404NotFound422/TOCAgentProject/tree/{SOURCE_COMMIT}/{SOURCE_PREFIX}"
INDEX_HASH = "4719c58268a167e2d40bd321830d32887d874f14783044a7e022da3b7059f541"
CHECKSUM_HASH = "8e31a404de6043390e081d9bf5ceebc4b5af20639d8a6c42cdac589cef16204c"
RELEASE_PATH = Path("KnowledgeBase/literature_evidence/2026-11-11")
CATEGORIES = ("Tissue_Types", "Time_Consumption", "Tissue_Deformation",
              "Fluorescence_Compatibility", "Preservation_Stability", "Application", "Note")
HISTORY = {"historical_evidence", "frozen_record", "baseline_scientific_record",
           "frozen_candidate_scientific_record", "historical_record", "revision_history",
           "revision_log", "change_log", "legacy_mapping", "legacy_crosswalk",
           "archived_question_records", "previous_partial_claims", "historical_old_scope",
           "superseded_early_reconstruction_scope", "historical_scope_declaration",
           "legacy_O_trace", "history_check", "historical_provenance"}
WRAPPERS = {"current_evidence_view", "effective_scientific_record", "reviewed_scientific_artifacts"}
SCIENCE = re.compile(
    r"claim|result|observation|finding|evidence_record|scientific_unit|evidence_unit|"
    r"^units$|sample|specimen|tissue|experiment|protocol|processing|operation|"
    r"stage|reagent|formulation|imaging|microscop|marker|antibod|label|fluor|signal|"
    r"time|timing|preserv|stability|storage|deform|shrink|expand|expansion|morpholog|"
    r"quantit|measurement|table|figure|panel|metric|compatib|application|"
    r"scientific_conclusion|purpose|method_context|comparison|^methods$|^branches$|"
    r"research_units|author_records|^records$|readout|equation|opt_acquisition|"
    r"opt_exposure|size_and_depth|spectral|lsfm|donor|analysis_method|statistic", re.I)
CONSTRAINT = re.compile(
    r"scope|limit|caveat|conflict|unknown|missing|gap|boundar|guardrail|"
    r"precedence|correction|non_inference|exclusion|interpretation|"
    r"evidence_policy|evidence_level_policy|metric_separation|version_boundary|"
    r"structured_join_policy|condition_binding|interpretation_rule", re.I)
ADMIN = re.compile(r"sha256|hash|checksum|file|path|query|log|receipt|audit|count$|"
                   r"_complete$|_completed$|review_round|coverage|inventory|manifest|mapping", re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def pointer_part(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def render(value, indent=0):
    """Keep every field of a scientific object, including nulls and qualifiers."""
    if isinstance(value, dict):
        return "\n".join("  " * indent + key + ": " + (
            "\n" + render(child, indent + 1) if isinstance(child, (dict, list))
            else render(child)) for key, child in value.items()) or "{}"
    if isinstance(value, list):
        return "\n".join("  " * indent + f"[{i + 1}] " + render(child, indent + 1)
                         for i, child in enumerate(value)) or "[]"
    if value is None:
        return "null (as recorded in source)"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def category(key):
    if CONSTRAINT.search(key) or re.search(r"field_checks|validation|read_method|^not_claimed$", key):
        return "Note"
    if re.search(r"sample|specimen|tissue_types|donor", key, re.I):
        return "Tissue_Types"
    if re.search(r"time|timing", key, re.I):
        return "Time_Consumption"
    if re.search(r"deform|shrink|expand|morpholog", key, re.I):
        return "Tissue_Deformation"
    if re.search(r"preserv|stability|storage", key, re.I):
        return "Preservation_Stability"
    if re.search(r"fluor|marker|label|antibod|signal|compatib", key, re.I):
        return "Fluorescence_Compatibility"
    return "Application"


def scientific_fields(value, pointer=""):
    """Choose only explicit scientific fields, never recursively revive history."""
    if not isinstance(value, dict):
        return
    if "current_evidence_view" in value:
        yield from scientific_fields(value["current_evidence_view"], pointer + "/current_evidence_view")
        value = {k: v for k, v in value.items() if CONSTRAINT.search(k)}
    if "effective_scientific_record" in value:
        yield from scientific_fields(value["effective_scientific_record"], pointer + "/effective_scientific_record")
    for key, child in value.items():
        ptr = pointer + "/" + pointer_part(key)
        if key in HISTORY or key in {"current_evidence_view", "effective_scientific_record", "table_read_method"}:
            continue
        if key == "base_record" and isinstance(child, dict):
            yield from scientific_fields(child, ptr)
            continue
        if key in {"reviewed_scientific_artifacts", "required_correction_overlays", "components"}:
            entries = enumerate(child) if isinstance(child, list) else child.items()
            for name, entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("content"), (dict, list)):
                    content_pointer = ptr + "/" + pointer_part(name) + "/content"
                    if key == "required_correction_overlays":
                        yield "Note", key, content_pointer, entry["content"]
                    elif isinstance(entry["content"], dict):
                        yield from scientific_fields(entry["content"], content_pointer)
                    elif SCIENCE.search(str(name)):
                        for i, row in enumerate(entry["content"]):
                            if isinstance(row, dict) and row.get("claim_status") == "superseded":
                                continue
                            yield category(str(name)), str(name), content_pointer + f"/{i}", row
            continue
        if not child or not isinstance(child, (str, dict, list)):
            continue
        if CONSTRAINT.search(key) or (SCIENCE.search(key) and not ADMIN.search(key)):
            rows = enumerate(child) if isinstance(child, list) else [(None, child)]
            for number, row in rows:
                if isinstance(row, dict) and str(row.get("claim_status", "")).lower() in {"superseded", "rejected", "withdrawn"}:
                    continue
                yield category(key), key, ptr + ("/" + str(number) if number is not None else ""), row


def load_archive(archive):
    z = zipfile.ZipFile(archive)
    names = z.namelist()
    if len(names) != len(set(names)) or any(n.startswith(("/", "\\")) or ".." in Path(n).parts for n in names):
        raise ValueError("Unsafe or duplicate archive members")
    if sha(z.read("active_index.json")) != INDEX_HASH or sha(z.read("SHA256SUMS.json")) != CHECKSUM_HASH:
        raise ValueError("Source release does not match the pinned GitHub snapshot")
    checksums = json.loads(z.read("SHA256SUMS.json"))
    if set(names) != set(checksums) | {"SHA256SUMS.json"}:
        raise ValueError("Archive inventory differs from the pinned release")
    for name, digest in checksums.items():
        if sha(z.read(name)) != digest:
            raise ValueError(f"Source bytes changed: {name}")
    return z


def make_cards(z):
    records = json.loads(z.read("active_index.json"))["records"]
    catalog = {x["paper_id"]: x for x in json.loads(z.read("catalog/catalog_224.json"))}
    outputs, inventory = {}, []
    for record in records:
        pid = record["paper_id"]
        meta = catalog[pid]
        selection = json.loads(z.read(record["version_selection"]))
        doi = record["doi"]
        references = [f"DOI: https://doi.org/{doi}",
                      f"Evidence-layer structured paraphrase; not a verbatim quotation. Source release: {SOURCE_URL}",
                      f"Local source archive: ../literature_evidence/2026-11-11/source_release.zip; member: {record['version_selection']}"]
        files = record["active_scientific_files"]
        docs = [(f, json.loads(z.read(f["path"]))) for f in files if f["path"].endswith(".json")]
        companions = [f for f in record.get("required_supporting_files", [])
                      if f["path"].endswith(".json") and
                      re.search(r"scientific|semantic|scope_and_precedence", f.get("role", "")) and
                      not re.search(r"historical|nonactive|snapshot", f.get("role", ""))]
        docs += [(f, json.loads(z.read(f["path"]))) for f in companions]
        methods = []
        for _, doc in docs:
            if isinstance(doc, dict):
                for k in ("method_name", "method", "clearing_method"):
                    if isinstance(doc.get(k), str) and doc[k] not in methods:
                        methods.append(doc[k])
        card = {
            "TOC_Method_Name": {"Text": "; ".join(methods) if methods else "Not specified as a single method in the selected evidence records", "Text_Reference": references},
            "General_Description": {"Text": f"{meta['title']} ({meta.get('year', 'year not reported')}). Evidence category: {record['category']}. This card preserves the evidence layer's structured statements and their original field labels; it does not add a new literature review or certify benchmark scoring thresholds.", "Text_Reference": references},
            **{k: [] for k in CATEGORIES},
        }
        policy = (f"Paper {pid}; source coverage: {record['coverage_status']}; source release status: {record['release_status']}; "
                  f"source default_eligible: {str(record['default_eligible']).lower()}. "
                  "Read this study as a whole with its sample, experimental, measurement and limitation fields. "
                  "All selected source files and mandatory support in the accompanying archive apply jointly. "
                  "Import does not promote candidate status, resolve contradictions, or turn review citations into independent primary experiments. "
                  "Application includes source-labelled protocols, comparisons and results; labels within each Text retain their actual role.")
        notes = [(policy, references), ("Selected version and mandatory composition:\n" + render(selection), references)]
        seen, bindings = {}, []
        for file, doc in docs:
            # This selected frozen addendum is an antecedent of the reviewed
            # replacement, not a second set of experiments (same 45 record IDs).
            if pid == "M_N0050" and file['path'].endswith('/frozen_R1_addendum_v1.json'):
                continue
            fields = list(scientific_fields(doc))
            name = Path(file['path']).stem
            if isinstance(doc, list) and SCIENCE.search(name) and not ADMIN.search(name):
                fields += [(category(name), name, f"/{i}", value) for i, value in enumerate(doc)
                           if not (isinstance(value, dict) and value.get("claim_status") == "superseded")]
            if "overlay" in file.get("role", "") or "semantic" in file.get("role", ""):
                fields = [("Note", "Mandatory companion (applies jointly): " + name, "", doc)]
            if re.search(r"supersession|precedence|correction|acceptance|scope_binding", name):
                fields = [("Note", "Source version and scope record (not an additional scientific claim): " + name, "", doc)]
            for group, key, ptr, value in fields:
                if re.search(r"receipt|validation|query_log|review_report|precheck|field_check|reviewer_delta|^independent_review$", name):
                    group = "Note"
                text = key + ":\n" + render(value)
                ref = f"Structured evidence: {file['path']}#{ptr}; SHA-256: {file['sha256']}; DOI: https://doi.org/{doi}"
                identity = (group, text)
                if identity in seen:
                    old = seen[identity]
                    if ref not in old[1]:
                        old[1].append(ref)
                    continue
                pair = (text, [ref])
                seen[identity] = pair
                if group == "Note":
                    notes.append(pair)
                else:
                    card[group].append(pair)
                bindings.append({"category": group, "source_path": file["path"], "json_pointer": ptr, "source_sha256": file["sha256"], "rendered_sha256": sha(text.encode("utf8"))})
        card["Note"] = notes
        for group in CATEGORIES:
            card[group] = [{f"Text{i}": t, f"Text{i}_Reference": refs} for i, (t, refs) in enumerate(card[group], 1)]
        target = f"KnowledgeBase/article_chunk/Evidence_{pid}_result.json"
        outputs[target] = encoded(card)
        inventory.append({"paper_id": pid, "title": meta["title"], "doi": doi,
                          "category": record["category"], "source_release_status": record["release_status"],
                          "source_default_eligible": record["default_eligible"], "card": target,
                          "card_sha256": sha(outputs[target].encode("utf8")),
                          "selected_files": files, "required_supporting_files": record.get("required_supporting_files", []),
                          "version_selection": record["version_selection"], "bindings": bindings,
                          "projected_sections": {g: len(card[g]) for g in CATEGORIES}})
    return outputs, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    archive = args.root / RELEASE_PATH / "source_release.zip"
    with load_archive(archive) as z:
        outputs, inventory = make_cards(z)
    manifest = {"source_commit": SOURCE_COMMIT, "source_url": SOURCE_URL,
                "source_archive_sha256": sha(archive.read_bytes()),
                "source_index_sha256": INDEX_HASH, "source_checksums_sha256": CHECKSUM_HASH,
                "paper_count": len(inventory), "category_counts": dict(Counter(r["category"] for r in inventory)),
                "default_eligible_count": sum(r["source_default_eligible"] for r in inventory),
                "representation": "structured-source field rendering, not verbatim paper quotations",
                "records": inventory}
    outputs[str(RELEASE_PATH / "manifest.json")] = encoded(manifest)
    table = io.StringIO(newline="")
    writer = csv.writer(table, lineterminator="\n")
    writer.writerow(["paper_id", "title", "doi", "category", "source_status",
                     "source_default_eligible", "card", "text_units"])
    for record in inventory:
        writer.writerow([record["paper_id"], record["title"], record["doi"], record["category"],
                         record["source_release_status"], record["source_default_eligible"],
                         record["card"], len(record["bindings"])])
    outputs[str(RELEASE_PATH / "papers.csv")] = "\ufeff" + table.getvalue()
    for relative, content in outputs.items():
        path = args.root / relative
        if args.check:
            if path.read_text(encoding="utf8") != content:
                raise ValueError(f"Generated card differs: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf8", newline="\n")
    print(json.dumps({"status": "PASS", "papers": len(inventory), "categories": manifest["category_counts"],
                      "projected_units": sum(len(r["bindings"]) for r in inventory),
                      "default_eligible": manifest["default_eligible_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
